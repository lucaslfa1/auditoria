import logging
import os
from threading import BoundedSemaphore, Lock

from psycopg2.extras import DictCursor
from psycopg2.pool import PoolError, ThreadedConnectionPool

logger = logging.getLogger(__name__)

_db_pool: ThreadedConnectionPool | None = None
_pool_lock = Lock()
_pool_semaphore: BoundedSemaphore | None = None
_pool_maxconn = 20


def _read_int_env(name: str, default: int, minimum: int = 1) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return max(minimum, value)


def _read_float_env(name: str, default: float, minimum: float = 0.0) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return max(minimum, value)


def _apply_session_timeouts(conn) -> None:
    """Apply timeout settings after checkout.

    Neon/Supabase poolers may reject startup `options`, so apply these with
    SET SESSION on the established connection instead.
    """
    if not _env_flag("DB_SESSION_TIMEOUTS_ENABLED", True):
        return

    statement_timeout_ms = _read_int_env("DB_STATEMENT_TIMEOUT_MS", 120_000, 1_000)
    lock_timeout_ms = _read_int_env("DB_LOCK_TIMEOUT_MS", 10_000, 1_000)
    idle_timeout_ms = _read_int_env("DB_IDLE_IN_TX_TIMEOUT_MS", 60_000, 1_000)
    previous_autocommit = getattr(conn, "autocommit", False)
    cursor = None
    try:
        conn.autocommit = True
        cursor = conn.cursor()
        cursor.execute(f"SET SESSION statement_timeout = {statement_timeout_ms}")
        cursor.execute(f"SET SESSION lock_timeout = {lock_timeout_ms}")
        cursor.execute(f"SET SESSION idle_in_transaction_session_timeout = {idle_timeout_ms}")
    except Exception as exc:
        logger.warning("Nao foi possivel aplicar timeouts de sessao no banco: %s", exc)
    finally:
        if cursor is not None:
            cursor.close()
        conn.autocommit = previous_autocommit


def _get_connect_timeout_seconds() -> int:
    return _read_int_env(
        "DB_CONNECT_TIMEOUT_SECONDS",
        _read_int_env("DB_CONNECT_TIMEOUT", 5),
        1,
    )


def _get_application_name() -> str:
    return (os.getenv("DB_APPLICATION_NAME", "auditoria_api") or "auditoria_api").strip() or "auditoria_api"


def _env_flag(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def get_database_url() -> str:
    """Return the PostgreSQL URL used by the application.

    Raises RuntimeError em producao quando `DATABASE_URL` esta vazia, para
    evitar fallback silencioso para localhost (BUG-019). Em desenvolvimento,
    o fallback continua disponivel mas emite WARNING explicito.
    """
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        environment = (os.getenv("ENVIRONMENT") or "development").strip().lower()
        if environment == "production":
            raise RuntimeError(
                "DATABASE_URL nao definida em producao. Configure a variavel de "
                "ambiente apontando para o Neon canonico (auditoria-nstech-2) antes "
                "de subir o servico."
            )
        url = "postgresql://postgres:postgres@localhost:5432/auditoria"
        logger.warning(
            "DATABASE_URL nao definida; usando fallback localhost (%s). "
            "Verifique seu .env se nao era a intencao.",
            url,
        )

    if url and "sslmode=" not in url.lower() and "localhost" not in url:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}sslmode=require"

    return url


def _init_pool() -> None:
    """Lazy-initialize the process-local PostgreSQL connection pool."""
    global _db_pool, _pool_maxconn, _pool_semaphore
    if _db_pool is not None:
        return

    dsn = get_database_url()
    try:
        minconn = _read_int_env("DB_POOL_MIN_CONN", 1)
        maxconn = _read_int_env("DB_POOL_MAX_CONN", 20)
        minconn = min(minconn, maxconn)

        keepalive_kwargs = {
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 5,
            "connect_timeout": _get_connect_timeout_seconds(),
            "application_name": _get_application_name(),
        }
        _db_pool = ThreadedConnectionPool(
            minconn, maxconn, dsn, cursor_factory=DictCursor, **keepalive_kwargs
        )
        _pool_maxconn = maxconn
        _pool_semaphore = BoundedSemaphore(maxconn)
        masked = dsn[: dsn.index("://") + 3] + "***@" + dsn.split("@")[-1] if "@" in dsn else "(local)"
        logger.info(
            "Connection pool instanciado com sucesso! min=%s max=%s DSN=%s",
            minconn,
            maxconn,
            masked,
        )
    except Exception as exc:
        logger.error("Erro ao criar pool: %s", exc)
        with open("connection_debug.txt", "w", encoding="utf-8") as handle:
            handle.write(f"DSN: {repr(dsn)}  Error: {exc}")
        raise


def _acquire_pool_slot() -> None:
    global _pool_semaphore
    if _pool_semaphore is None:
        _pool_semaphore = BoundedSemaphore(_pool_maxconn)

    wait_seconds = _read_float_env("DB_POOL_WAIT_SECONDS", 10.0)
    if not _pool_semaphore.acquire(timeout=wait_seconds):
        raise PoolError(f"connection pool exhausted after waiting {wait_seconds:g}s")


def _release_pool_slot() -> None:
    if _pool_semaphore is None:
        return
    try:
        _pool_semaphore.release()
    except ValueError:
        logger.warning("Tentativa de liberar slot de pool ja liberado.")


def _validate_connection(conn) -> None:
    if not _env_flag("DB_POOL_VALIDATE_ON_CHECKOUT", True):
        return

    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
    finally:
        if cursor is not None:
            cursor.close()
        conn.rollback()


class PooledConnectionContext:
    """
    Compatibility wrapper for legacy repositories.

    Existing code calls ``conn.close()`` directly. In production, close returns
    the native psycopg2 connection to the pool and releases the local semaphore.
    Broken SSL connections are discarded so they are not reused.

    The ``_dirty`` flag tracks whether any statement has been executed since the
    last ``commit()`` or ``rollback()``.  On ``close()`` we only issue a
    ``rollback()`` when *uncommitted* work exists — this prevents the pool
    cleanup from accidentally reverting data that was already committed by a
    shared-connection facade (``_SharedConnection``).
    """

    def __init__(self, conn):
        self._conn = conn
        self._dirty = False

    def close(self):
        global _db_pool
        if self._conn is None:
            return

        conn = self._conn
        self._conn = None
        if _db_pool is None:
            _release_pool_slot()
            return

        close_broken_connection = bool(getattr(conn, "closed", False))
        try:
            if not close_broken_connection and self._dirty:
                conn.rollback()
        except Exception:
            close_broken_connection = True

        try:
            _db_pool.putconn(conn, close=close_broken_connection)
        except Exception:
            # putconn pode falhar (pool fechado durante shutdown, conexao de
            # outro pool apos re-init). Sem este guard a conexao nativa vaza
            # aberta; fechamos direto para devolver o recurso ao SO/Postgres.
            logger.warning("putconn falhou; fechando conexao nativa diretamente.", exc_info=True)
            try:
                conn.close()
            except Exception:
                pass
        finally:
            _release_pool_slot()

    def cursor(self, *args, **kwargs):
        if self._conn is None:
            raise RuntimeError("Tentativa de chamar cursor() em uma conexao do pool ja liberada.")
        self._dirty = True
        return self._conn.cursor(*args, **kwargs)

    def commit(self):
        if self._conn:
            self._conn.commit()
            self._dirty = False

    def rollback(self):
        if self._conn:
            self._conn.rollback()
            self._dirty = False

    def __getattr__(self, name):
        if self._conn is None:
            raise RuntimeError(f"Atributo '{name}' num banco ja devolvido.")
        return getattr(self._conn, name)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


def _create_pg_connection() -> PooledConnectionContext:
    """Checkout a connection from the global pool."""
    global _db_pool
    if _db_pool is None:
        with _pool_lock:
            if _db_pool is None:
                _init_pool()

    _acquire_pool_slot()
    last_error = None
    try:
        for _attempt in range(2):
            conn = _db_pool.getconn()
            try:
                conn.autocommit = False
                _validate_connection(conn)
                _apply_session_timeouts(conn)
                return PooledConnectionContext(conn)
            except Exception as exc:
                last_error = exc
                try:
                    _db_pool.putconn(conn, close=True)
                except Exception:
                    pass
        raise last_error
    except Exception:
        _release_pool_slot()
        raise


def create_connection(db_path: str = ""):
    """Compatibility entrypoint used by repositories."""
    return _create_pg_connection()


def get_connection():
    """Return a pooled PostgreSQL connection."""
    return _create_pg_connection()


def is_production_environment() -> bool:
    return (os.getenv("ENVIRONMENT", "development") or "").strip().lower() == "production"


def close_all_pools():
    """Close and reset the static pool."""
    global _db_pool, _pool_semaphore
    if _db_pool is not None:
        _db_pool.closeall()
        _db_pool = None
    _pool_semaphore = None
