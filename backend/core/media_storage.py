"""Storage abstraction for media files tracked in ``media_files``.

Backends fisicos suportados (selecionados por MEDIA_STORAGE_BACKEND):
- ``local``      — disco local (dev; raiz em MEDIA_STORAGE_ROOT).
- ``gcs``        — Google Cloud Storage (producao atual no Cloud Run).
- ``azure_blob`` — Azure Blob Storage (deploy na infra Azure do time de
                   engenharia, equivalente ao GCS; exige
                   AZURE_STORAGE_CONNECTION_STRING e, opcionalmente,
                   AZURE_STORAGE_CONTAINER).

O banco guarda apenas metadados/ponteiros (tabela ``media_files``) para os
callers nao dependerem de caminhos especificos de provedor. Os SDKs de nuvem
sao importados de forma LAZY: a imagem so precisa do SDK do backend ativo.
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Iterator, Optional, Tuple

from db.connection import get_connection

logger = logging.getLogger(__name__)

_AUDIO_STREAM_CHUNK_SIZE = 64 * 1024

CLASSIFIED_MEDIA_NAMESPACE = "classified:"
AUDIT_MEDIA_NAMESPACE = "audit:"
_KNOWN_NAMESPACES = (CLASSIFIED_MEDIA_NAMESPACE, AUDIT_MEDIA_NAMESPACE)


class MediaStorageError(RuntimeError):
    """Erro genérico de armazenamento de mídia (upload/download/delete falhou
    em qualquer backend, ou configuração inválida, ex.: backend desconhecido,
    path traversal, connection string Azure ausente)."""
    pass


class MediaNotFoundError(MediaStorageError):
    """Mídia não encontrada no backend nem nos caminhos legados de fallback."""
    pass


def _strip_known_namespace(value: str) -> str:
    for prefix in _KNOWN_NAMESPACES:
        if value.startswith(prefix):
            return value[len(prefix):]
    return value


def classified_media_hash(input_hash: Optional[str]) -> Optional[str]:
    """Build the media_files key for classified/pre-audit media."""
    if input_hash is None:
        return None
    value = _strip_known_namespace(str(input_hash).strip())
    if not value:
        return None
    return f"{CLASSIFIED_MEDIA_NAMESPACE}{value}"


def audit_media_hash(audit_id: Optional[object] = None, input_hash: Optional[str] = None) -> Optional[str]:
    """Build the media_files key reserved for audit-final media."""
    if input_hash is not None:
        value = _strip_known_namespace(str(input_hash).strip())
        if value:
            return f"{AUDIT_MEDIA_NAMESPACE}{value}"
    if audit_id is None or str(audit_id).strip() == "":
        return None
    return f"{AUDIT_MEDIA_NAMESPACE}{audit_id}"


def _get_default_backend() -> str:
    env_backend = os.getenv("MEDIA_STORAGE_BACKEND", "").strip().lower()
    if env_backend:
        return env_backend

    if os.getenv("ENVIRONMENT", "").strip().lower() == "production" or os.getenv("K_SERVICE"):
        return "gcs"
    return "local"


def _get_gcs_bucket_name() -> str:
    name = os.getenv("GCS_BUCKET_NAME", "").strip()
    if not name and os.getenv("K_SERVICE"):
        return "auditoria-nstech-audios"
    return name or "auditoria-nstech-audios"


def _get_azure_container_client():
    """ContainerClient do Azure Blob (import lazy — o SDK so e exigido quando
    MEDIA_STORAGE_BACKEND=azure_blob esta ativo; a imagem GCP atual nao muda.

    Na migração Azure, este e o ponto que sincroniza o app com o Blob Storage:
    configure a connection string no Key Vault/secretRef e mantenha a chave dos
    objetos igual a gravada em `media_files.storage_key`.
    """
    from azure.storage.blob import BlobServiceClient

    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "").strip()
    if not connection_string:
        raise MediaStorageError(
            "MEDIA_STORAGE_BACKEND=azure_blob exige AZURE_STORAGE_CONNECTION_STRING."
        )
    container_name = os.getenv("AZURE_STORAGE_CONTAINER", "").strip() or "auditoria-midia"
    service = BlobServiceClient.from_connection_string(connection_string)
    return service.get_container_client(container_name)


def _local_storage_root() -> Path:
    configured = os.getenv("MEDIA_STORAGE_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path(__file__).resolve().parent.parent / "storage").resolve()


def _clean_relative_path(relative_path: str) -> str:
    clean_relative = str(relative_path or "").strip().replace("\\", "/").lstrip("/")
    if not clean_relative:
        raise MediaStorageError("Caminho de midia vazio.")
    parts = clean_relative.split("/")
    if ".." in parts or ":" in parts[0]:
        raise MediaStorageError("Tentativa de path traversal detectada.")
    return clean_relative


def _resolve_safe_local_path(relative_path: str, *, root: Optional[Path] = None) -> Path:
    storage_root = (root or _local_storage_root()).expanduser().resolve()
    clean_relative = _clean_relative_path(relative_path)
    full_path = (storage_root / clean_relative).resolve()

    try:
        full_path.relative_to(storage_root)
    except ValueError as exc:
        raise MediaStorageError(
            "O caminho final resolve para fora do diretorio de armazenamento local permitido."
        ) from exc

    return full_path


def _legacy_local_roots() -> list[Path]:
    roots = [
        Path(
            os.getenv(
                "CLASSIFIED_AUDIO_STORAGE_DIR",
                str(Path(__file__).resolve().parent.parent / "storage" / "classified_audio"),
            )
        ).expanduser(),
        Path(
            os.getenv(
                "AUDIT_AUDIO_STORAGE_DIR",
                str(Path(__file__).resolve().parent.parent / "storage" / "audits" / "audio"),
            )
        ).expanduser(),
    ]

    unique_roots: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        resolved = root.resolve()
        if resolved not in seen:
            unique_roots.append(resolved)
            seen.add(resolved)
    return unique_roots


def _find_legacy_local_path(fallback_path: Optional[str]) -> Optional[Path]:
    if not fallback_path:
        return None

    for root in _legacy_local_roots():
        try:
            candidate = _resolve_safe_local_path(fallback_path, root=root)
        except MediaStorageError:
            continue
        if candidate.exists():
            return candidate
    return None


def _get_media_record(file_hash: str) -> Optional[tuple[str, str]]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT storage_backend, storage_key FROM media_files WHERE file_hash = %s",
            (file_hash,),
        )
        record = cursor.fetchone()
        if not record:
            return None
        return str(record[0]), str(record[1])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Nao foi possivel consultar media_files para hash=%s: %s", file_hash, exc)
        try:
            conn.rollback()
        except Exception:
            pass
        return None
    finally:
        conn.close()


def store_media(
    file_hash: str,
    content_bytes: bytes,
    original_filename: str,
    content_type: str,
    storage_key: str,
) -> None:
    """Write media bytes to the configured backend and upsert its pointer."""
    if not file_hash:
        raise MediaStorageError("file_hash e obrigatorio.")

    backend = _get_default_backend()

    if backend == "gcs":
        try:
            from google.cloud import storage

            client = storage.Client()
            bucket = client.bucket(_get_gcs_bucket_name())
            blob = bucket.blob(storage_key)
            blob.upload_from_string(content_bytes, content_type=content_type)
        except Exception as exc:  # noqa: BLE001
            logger.error("Falha ao fazer upload para o GCS: %s", exc)
            raise MediaStorageError(f"GCS upload failed: {exc}") from exc
    elif backend == "azure_blob":
        try:
            from azure.storage.blob import ContentSettings

            container = _get_azure_container_client()
            container.upload_blob(
                name=storage_key,
                data=content_bytes,
                overwrite=True,
                content_settings=ContentSettings(content_type=content_type),
            )
        except MediaStorageError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("Falha ao fazer upload para o Azure Blob: %s", exc)
            raise MediaStorageError(f"Azure Blob upload failed: {exc}") from exc
    elif backend == "local":
        try:
            full_path = _resolve_safe_local_path(storage_key)
            full_path.parent.mkdir(parents=True, exist_ok=True)

            temp_path = full_path.with_suffix(f"{full_path.suffix}.tmp")
            temp_path.write_bytes(content_bytes)

            stored = False
            last_error: Optional[PermissionError] = None
            for _ in range(3):
                try:
                    os.replace(temp_path, full_path)
                    stored = True
                    break
                except PermissionError as exc:
                    last_error = exc
                    time.sleep(0.5)
            if not stored:
                temp_path.unlink(missing_ok=True)
                raise PermissionError(f"Nao foi possivel mover o arquivo temporario para {full_path}") from last_error
        except Exception as exc:  # noqa: BLE001
            logger.error("Falha ao salvar localmente: %s", exc)
            raise MediaStorageError(f"Local save failed: {exc}") from exc
    else:
        raise MediaStorageError(
            f"Storage backend desconhecido: {backend} (suportados: local, gcs, azure_blob)"
        )

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO media_files
                (file_hash, storage_backend, storage_key, content_type, size_bytes, original_filename)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (file_hash) DO UPDATE
            SET storage_backend = EXCLUDED.storage_backend,
                storage_key = EXCLUDED.storage_key,
                content_type = EXCLUDED.content_type,
                size_bytes = EXCLUDED.size_bytes,
                original_filename = EXCLUDED.original_filename
            """,
            (file_hash, backend, storage_key, content_type, len(content_bytes), original_filename),
        )
        conn.commit()
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        logger.error("Falha ao registrar media_file no banco: %s", exc)
        raise MediaStorageError(f"Database insert failed: {exc}") from exc
    finally:
        conn.close()


def load_media_bytes(file_hash: str, fallback_path: Optional[str] = None) -> Optional[bytes]:
    """Load media bytes by media_files hash, with legacy path fallback."""
    record = _get_media_record(file_hash)
    if record:
        backend, storage_key = record
    elif fallback_path:
        backend = _get_default_backend()
        storage_key = fallback_path
    else:
        return None

    if backend == "gcs":
        try:
            from google.cloud import storage

            client = storage.Client()
            bucket = client.bucket(_get_gcs_bucket_name())
            blob = bucket.blob(storage_key)
            if blob.exists():
                return blob.download_as_bytes()
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to download media from GCS (key=%s): %s", storage_key, exc)
    elif backend == "azure_blob":
        try:
            blob = _get_azure_container_client().get_blob_client(storage_key)
            if blob.exists():
                return blob.download_blob().readall()
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to download media from Azure Blob (key=%s): %s", storage_key, exc)
    elif backend == "local":
        try:
            full_path = _resolve_safe_local_path(storage_key)
        except MediaStorageError as exc:
            logger.warning("Caminho de midia invalido: %s", exc)
            full_path = None

        if full_path is not None and full_path.exists():
            return full_path.read_bytes()

        legacy_path = _find_legacy_local_path(fallback_path)
        if legacy_path is not None:
            return legacy_path.read_bytes()

    return None


def _is_storage_key_shared(file_hash: str, backend: str, storage_key: str) -> bool:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT COUNT(*)
              FROM media_files
             WHERE storage_backend = %s
               AND storage_key = %s
               AND file_hash != %s
            """,
            (backend, storage_key, file_hash),
        )
        return cursor.fetchone()[0] > 0
    finally:
        conn.close()


def delete_media(file_hash: str, fallback_path: Optional[str] = None) -> bool:
    """Delete media metadata and, when safe, the physical object."""
    record = _get_media_record(file_hash)
    if record:
        backend, storage_key = record
    elif fallback_path:
        backend = _get_default_backend()
        storage_key = fallback_path
    else:
        return False

    try:
        is_shared = _is_storage_key_shared(file_hash, backend, storage_key)
    except Exception as exc:  # noqa: BLE001
        logger.error("Erro ao checar compartilhamento do media path: %s", exc)
        is_shared = True

    deleted_physically = False
    if not is_shared and backend == "gcs":
        try:
            from google.cloud import storage

            client = storage.Client()
            bucket = client.bucket(_get_gcs_bucket_name())
            blob = bucket.blob(storage_key)
            if blob.exists():
                blob.delete()
                deleted_physically = True
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to delete media from GCS (key=%s): %s", storage_key, exc)
    elif not is_shared and backend == "azure_blob":
        try:
            blob = _get_azure_container_client().get_blob_client(storage_key)
            if blob.exists():
                blob.delete_blob()
                deleted_physically = True
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to delete media from Azure Blob (key=%s): %s", storage_key, exc)
    elif not is_shared and backend == "local":
        try:
            full_path = _resolve_safe_local_path(storage_key)
            if full_path.exists():
                full_path.unlink()
                deleted_physically = True
        except MediaStorageError:
            pass
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to delete media from local (key=%s): %s", storage_key, exc)

        if not deleted_physically:
            legacy_path = _find_legacy_local_path(fallback_path)
            if legacy_path is not None:
                legacy_path.unlink()
                deleted_physically = True

    if record:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM media_files WHERE file_hash = %s", (file_hash,))
            conn.commit()
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            logger.error("Failed to delete media_file record (hash=%s): %s", file_hash, exc)
        finally:
            conn.close()

    return deleted_physically


def open_media_stream(file_hash: str, fallback_path: Optional[str] = None) -> Optional[Tuple[Iterator[bytes], int]]:
    """Open media as a chunk iterator plus total size."""
    record = _get_media_record(file_hash)
    if record:
        backend, storage_key = record
    elif fallback_path:
        backend = _get_default_backend()
        storage_key = fallback_path
    else:
        return None

    if backend == "gcs":
        try:
            from google.cloud import storage

            client = storage.Client()
            bucket = client.bucket(_get_gcs_bucket_name())
            blob = bucket.blob(storage_key)
            if blob.exists():
                blob.reload()
                handle = blob.open("rb")

                def gcs_iterator() -> Iterator[bytes]:
                    try:
                        while True:
                            chunk = handle.read(_AUDIO_STREAM_CHUNK_SIZE)
                            if not chunk:
                                break
                            yield chunk
                    finally:
                        handle.close()

                return gcs_iterator(), int(blob.size or 0)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to stream media from GCS (key=%s): %s", storage_key, exc)
    elif backend == "azure_blob":
        try:
            blob = _get_azure_container_client().get_blob_client(storage_key)
            if blob.exists():
                downloader = blob.download_blob()

                def azure_iterator() -> Iterator[bytes]:
                    for chunk in downloader.chunks():
                        yield chunk

                return azure_iterator(), int(getattr(downloader, "size", 0) or 0)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to stream media from Azure Blob (key=%s): %s", storage_key, exc)
    elif backend == "local":
        try:
            full_path = _resolve_safe_local_path(storage_key)
        except MediaStorageError as exc:
            logger.warning("Caminho de midia invalido para streaming: %s", exc)
            full_path = None

        if full_path is None or not full_path.exists():
            full_path = _find_legacy_local_path(fallback_path)

        if full_path is not None and full_path.exists():
            size = full_path.stat().st_size
            handle = full_path.open("rb")

            def file_iterator() -> Iterator[bytes]:
                try:
                    while True:
                        chunk = handle.read(_AUDIO_STREAM_CHUNK_SIZE)
                        if not chunk:
                            break
                        yield chunk
                finally:
                    handle.close()

            return file_iterator(), size

    return None
