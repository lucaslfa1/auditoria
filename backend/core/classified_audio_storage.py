"""Storage de áudio classificado (filesystem/`media_files`) para a automação.

Guarda, carrega e faz streaming da mídia que a triagem/classificação produz e
que a automação audita depois; inclui sanitização anti path-traversal da chave
relativa e a limpeza por retenção dos órfãos no filesystem.

Extraído de `core.automation` (concern de mídia, independente do loop de
auditoria). `core.automation` reexporta `load/store/open/cleanup` p/ compat —
callers e testes seguem usando `core.automation.<fn>` (e `routers.telefonia.<fn>` /
`core.huawei_sync.<fn>`, que importam de core.automation).
"""
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Iterator, Optional, Tuple

import db.database as database
from core.classification import get_mime_type

logger = logging.getLogger(__name__)


def get_classified_audio_storage_root() -> Path:
    """Raiz local do storage de mídia classificada.

    Usa `CLASSIFIED_AUDIO_STORAGE_DIR` se setada; senão `backend/storage/classified_audio`.
    Obs.: em produção a mídia vive na tabela `media_files` (banco); o filesystem
    é fallback/legado.
    """
    configured = os.getenv("CLASSIFIED_AUDIO_STORAGE_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[1] / "storage" / "classified_audio"


def _normalize_classified_storage_key(relative_path: object) -> Optional[str]:
    """Sanitiza a chave relativa do storage (anti path-traversal).

    Rejeita caminho absoluto, drive Windows (`C:`) e componentes `.`/`..`.
    Retorna a chave POSIX normalizada ou None quando inválida.
    """
    raw = str(relative_path or "").strip().replace("\\", "/")
    if not raw or raw.startswith("/"):
        return None
    path = PurePosixPath(raw)
    if path.parts and ":" in path.parts[0]:
        return None
    if any(part in {"", ".", ".."} for part in path.parts):
        return None
    return path.as_posix()


def _resolve_classified_local_path(relative_path: object) -> Optional[Path]:
    """Resolve a chave relativa para um Path absoluto DENTRO da raiz do storage.

    Retorna None (com warning) se a chave for inválida ou escapar da raiz.
    """
    storage_key = _normalize_classified_storage_key(relative_path)
    if not storage_key:
        logger.warning("Caminho de midia classificada invalido: %r", relative_path)
        return None

    root = get_classified_audio_storage_root().resolve()
    resolved = (root / storage_key).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        logger.warning("Caminho de midia classificada fora do storage: %r", relative_path)
        return None
    return resolved


def store_classified_audio(input_hash: str, filename: str, audio_bytes: bytes) -> str:
    """Guarda a mídia classificada para ser auditada depois pela automação.

    Efeito colateral: grava em `media_files` (banco) sob a chave namespaced
    `classified:{input_hash}`. Retorna a storage_key relativa
    (`classified_audio/AAAA/MM/{hash16}{ext}`) que vai para o metadata da fila.
    """
    ext = Path(filename).suffix.lower() or ".wav"
    safe_hash = input_hash[:16] if input_hash else "unknown"
    relative = f"{safe_hash}{ext}"

    now = datetime.now()
    date_path = f"{now:%Y}/{now:%m}"
    storage_key = f"classified_audio/{date_path}/{relative}"

    from core.media_storage import classified_media_hash, store_media
    content_type = get_mime_type(filename) or "audio/wav"

    store_media(
        file_hash=classified_media_hash(input_hash) or input_hash,
        content_bytes=audio_bytes,
        original_filename=filename,
        content_type=content_type,
        storage_key=storage_key
    )
    return storage_key


def load_classified_audio(relative_path: str, input_hash: Optional[str] = None) -> Optional[bytes]:
    """Carrega os bytes da mídia classificada do storage.

    Tenta primeiro a chave namespaced `classified:{input_hash}`; cai para o
    `input_hash` cru (legado) e por fim para o `relative_path`, para que linhas
    gravadas antes do namespacing continuem funcionando. Retorna None se não achar.
    """
    from core.media_storage import classified_media_hash, load_media_bytes
    ns_key = classified_media_hash(input_hash)
    if ns_key:
        bytes_data = load_media_bytes(file_hash=ns_key, fallback_path=None)
        if bytes_data is not None:
            return bytes_data
    return load_media_bytes(file_hash=input_hash or relative_path, fallback_path=relative_path)


_AUDIO_STREAM_CHUNK_SIZE = 64 * 1024  # 64 KB por chunk


def open_classified_audio_stream(
    relative_path: str,
    input_hash: Optional[str] = None
) -> Optional[Tuple[Iterator[bytes], Optional[int]]]:
    """Abre o audio classificado em modo streaming.

    Devolve (iterator_de_chunks, content_length) ou None quando o arquivo nao
    existe. Usado pelo router /telefonia/recordings/{hash}/audio para evitar
    carregar WAVs inteiros em memoria ao servir o player.
    """
    from core.media_storage import classified_media_hash, open_media_stream
    ns_key = classified_media_hash(input_hash)
    if ns_key:
        stream = open_media_stream(file_hash=ns_key, fallback_path=None)
        if stream is not None:
            return stream
    return open_media_stream(file_hash=input_hash or relative_path, fallback_path=relative_path)



def cleanup_classified_audio_storage(*, retention_days: int = 30, dry_run: bool = True) -> dict:
    """Remove do filesystem áudios classificados órfãos (sem referência na fila).

    Arquivos ainda referenciados por `fila_revisao_classificacao.metadata.classified_audio_path`
    são SEMPRE preservados. Os não referenciados só são apagados quando mais
    antigos que `retention_days`. Com `dry_run=True` (default) apenas lista os
    candidatos sem apagar. Retorna dict-relatório (referenced/kept/candidates/deleted).
    """
    root = get_classified_audio_storage_root()
    if retention_days < 0:
        raise ValueError("retention_days deve ser maior ou igual a zero")

    if not root.exists():
        return {
            "root": str(root),
            "referenced": 0,
            "kept": 0,
            "candidates": [],
            "deleted": [],
            "dry_run": dry_run,
        }

    referenced_paths = {
        str(Path(relative_path).as_posix())
        for relative_path in database.listar_paths_audio_classificado_fila_revisao()
        if str(relative_path or "").strip()
    }
    cutoff = datetime.now() - timedelta(days=retention_days)
    candidates: list[str] = []
    deleted: list[str] = []
    kept = 0

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = str(path.relative_to(root).as_posix())
        if relative in referenced_paths:
            kept += 1
            continue
        modified_at = datetime.fromtimestamp(path.stat().st_mtime)
        if modified_at > cutoff:
            kept += 1
            continue
        candidates.append(relative)
        if not dry_run:
            path.unlink(missing_ok=True)
            deleted.append(relative)

    return {
        "root": str(root),
        "referenced": len(referenced_paths),
        "kept": kept,
        "candidates": candidates,
        "deleted": deleted,
        "dry_run": dry_run,
        "retention_days": retention_days,
    }
