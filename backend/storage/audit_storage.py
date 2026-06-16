"""Armazenamento do áudio das auditorias (Google Cloud Storage ou disco local).

Papel no fluxo: persiste o WAV/áudio original de cada auditoria e devolve o caminho
relativo gravado em `audits.audio_storage_path`. Quando há bucket GCS configurado
(env GCS_BUCKET_NAME, ou o padrão no Cloud Run) o áudio vai para o Cloud Storage;
caso contrário, vai para o diretório local (env AUDIT_AUDIO_STORAGE_DIR ou
backend/audits/audio). Toda gravação faz read-back para confirmar o tamanho antes
de retornar o caminho — evita gravar no DB um ponteiro para um blob órfão/corrompido.

CUSTO DE API: sem custo de IA. Há custo/latência de I/O de armazenamento (GCS ou
disco), nunca chamadas a Azure OpenAI/Speech.
"""

import logging
import os
import re
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class AudioUploadVerificationError(RuntimeError):
    """Upload do audio nao pode ser verificado (size mismatch ou objeto ausente).

    Levantada quando o read-back pos-upload nao confirma que o blob/arquivo
    armazenado contem exatamente os bytes enviados. Garante que o caller
    NAO grave audio_storage_path no DB apontando para um blob orfao.
    """


AUDIO_EXTENSION_BY_MIME = {
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/wave": ".wav",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/ogg": ".ogg",
    "audio/webm": ".webm",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
}
_SAFE_SUFFIXES = set(AUDIO_EXTENSION_BY_MIME.values())
_SAFE_HASH_CHARS = re.compile(r"[^a-z0-9]+")

class CloudStorageFile:
    """Wrapper de um blob no GCS com interface estilo pathlib.Path (exists/unlink/read_bytes).

    Permite ao resto do código tratar áudio no Cloud Storage e áudio em disco de
    forma uniforme. Acessa a rede (Google Cloud Storage) a cada operação.
    """

    def __init__(self, bucket_name, blob_name):
        self.bucket_name = bucket_name
        self.blob_name = blob_name
        self.name = Path(blob_name).name

    def exists(self):
        """True se o blob existe no bucket. Erros de acesso ao GCS são logados e viram False."""
        try:
            from google.cloud import storage
            client = storage.Client()
            bucket = client.bucket(self.bucket_name)
            blob = bucket.blob(self.blob_name)
            return blob.exists()
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"GCS exists error: {e}")
            return False

    def unlink(self, missing_ok=False):
        """Apaga o blob no GCS. Com `missing_ok=False` (padrão), propaga erro de remoção."""
        try:
            from google.cloud import storage
            client = storage.Client()
            bucket = client.bucket(self.bucket_name)
            blob = bucket.blob(self.blob_name)
            if blob.exists():
                blob.delete()
        except Exception:
            if not missing_ok:
                raise

    def read_bytes(self):
        """Baixa e retorna o conteúdo do blob como bytes (acessa o GCS)."""
        from google.cloud import storage
        client = storage.Client()
        bucket = client.bucket(self.bucket_name)
        blob = bucket.blob(self.blob_name)
        return blob.download_as_bytes()

def _get_bucket_name() -> str:
    """Nome do bucket GCS (env GCS_BUCKET_NAME). No Cloud Run sem a env, assume o bucket padrão; vazio = usar disco local."""
    name = os.getenv("GCS_BUCKET_NAME", "").strip()
    if not name and os.getenv("K_SERVICE"):
        # Se estiver rodando no Cloud Run e sem var, assume o padrao
        return "auditoria-nstech-audios"
    return name

def get_audit_audio_storage_root() -> Path:
    """Diretório raiz do áudio em disco (env AUDIT_AUDIO_STORAGE_DIR ou backend/audits/audio).

    Cria o diretório se faltar (retry em PermissionError) e retorna o path absoluto
    resolvido. Usado só quando não há bucket GCS configurado.
    """
    configured = (os.getenv("AUDIT_AUDIO_STORAGE_DIR") or "").strip()
    if configured:
        root = Path(configured).expanduser()
    else:
        root = Path(__file__).resolve().parent / "audits" / "audio"

    for _ in range(3):
        try:
            root.mkdir(parents=True, exist_ok=True)
            break
        except PermissionError:
            import time
            time.sleep(0.1)
    
    return root.resolve()

def _resolve_audio_suffix(original_filename: str | None, mime_type: str | None) -> str:
    original_suffix = Path(original_filename or "").suffix.lower().strip()
    if original_suffix in _SAFE_SUFFIXES:
        return original_suffix
    return AUDIO_EXTENSION_BY_MIME.get(str(mime_type or "").strip().lower(), ".wav")

def _sanitize_hash_fragment(input_hash: str | None) -> str:
    normalized = _SAFE_HASH_CHARS.sub("", str(input_hash or "").strip().lower())
    return normalized[:12] or "semhash"

def _ensure_inside_root(root: Path, candidate: Path) -> Path:
    """Garante (anti path-traversal) que `candidate` está dentro de `root`; levanta ValueError se escapar."""
    resolved_root = root.resolve()
    resolved_candidate = candidate.resolve()
    resolved_candidate.relative_to(resolved_root)
    return resolved_candidate

def build_audio_storage_relative_path(*, audit_id: int, mime_type: str | None, original_filename: str | None, input_hash: str | None) -> str:
    """Monta o caminho relativo do áudio: AAAA/MM/audit_{id}_{hash12}{.ext} (separador POSIX).

    A extensão vem do nome original ou do MIME; o fragmento de hash é sanitizado
    (12 chars alfanuméricos). Função pura, sem efeitos colaterais.
    """
    suffix = _resolve_audio_suffix(original_filename, mime_type)
    short_hash = _sanitize_hash_fragment(input_hash)
    now = datetime.now()
    return str(Path(f"{now:%Y}") / f"{now:%m}" / f"audit_{audit_id}_{short_hash}{suffix}").replace("\\", "/")

def store_audit_audio_file(*, audit_id: int, audio_bytes: bytes, mime_type: str | None, original_filename: str | None, input_hash: str | None, existing_relative_path: str | None = None) -> dict:
    """Grava os bytes do áudio de uma auditoria (GCS ou disco) e verifica a integridade por tamanho.

    Reaproveita `existing_relative_path` se informado, senão gera um novo via
    build_audio_storage_relative_path. No GCS faz upload + reload e compara o
    tamanho; em disco grava via arquivo .tmp + os.replace atômico e confere o
    st_size. Em qualquer divergência/falha de read-back, apaga o blob/arquivo
    parcial e levanta AudioUploadVerificationError (em disco, PermissionError
    persistente vira erro após 3 tentativas).

    Efeitos: escreve no GCS ou no disco (rede/FS). Retorna dict de metadados
    {audio_storage_path, audio_original_filename, audio_mime_type, audio_size_bytes}
    para o caller gravar em `audits`.
    """
    relative_path = existing_relative_path or build_audio_storage_relative_path(
        audit_id=audit_id,
        mime_type=mime_type,
        original_filename=original_filename,
        input_hash=input_hash,
    )
    
    expected_size = len(audio_bytes)
    bucket_name = _get_bucket_name()
    if bucket_name:
        try:
            from google.cloud import storage
            client = storage.Client()
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(relative_path)
            blob.upload_from_string(audio_bytes, content_type=mime_type or "audio/wav")
        except Exception as e:
            logger.error("Failed to upload to GCS: %s", e)
            raise

        try:
            blob.reload()
            actual_size = int(blob.size or 0)
        except Exception as exc:
            logger.error("Read-back falhou para gs://%s/%s: %s", bucket_name, relative_path, exc)
            try:
                blob.delete()
            except Exception:
                logger.warning("Falha ao limpar blob orfao apos read-back: gs://%s/%s", bucket_name, relative_path)
            raise AudioUploadVerificationError(
                f"Nao foi possivel verificar upload GCS gs://{bucket_name}/{relative_path}"
            ) from exc
        if actual_size != expected_size:
            logger.error(
                "Size mismatch apos upload GCS gs://%s/%s: esperado=%d, observado=%d",
                bucket_name, relative_path, expected_size, actual_size,
            )
            try:
                blob.delete()
            except Exception:
                logger.warning("Falha ao limpar blob com size incorreto: gs://%s/%s", bucket_name, relative_path)
            raise AudioUploadVerificationError(
                f"Size mismatch apos upload GCS (esperado={expected_size}, observado={actual_size})"
            )
    else:
        root = get_audit_audio_storage_root()
        absolute_path = _ensure_inside_root(root, root / relative_path)
        import time
        for _ in range(3):
            try:
                absolute_path.parent.mkdir(parents=True, exist_ok=True)
                break
            except PermissionError:
                time.sleep(0.1)

        temp_path = absolute_path.with_suffix(f"{absolute_path.suffix}.tmp")
        with open(temp_path, "wb") as handle:
            handle.write(audio_bytes)

        stored = False
        last_error = None
        for _ in range(3):
            try:
                os.replace(temp_path, absolute_path)
                stored = True
                break
            except PermissionError as exc:
                last_error = exc
                time.sleep(0.5)
        if not stored:
            temp_path.unlink(missing_ok=True)
            raise PermissionError(f"Nao foi possivel gravar o audio em {absolute_path}") from last_error

        try:
            actual_size = absolute_path.stat().st_size
        except OSError as exc:
            logger.error("Read-back falhou para %s: %s", absolute_path, exc)
            absolute_path.unlink(missing_ok=True)
            raise AudioUploadVerificationError(
                f"Nao foi possivel verificar gravacao local em {absolute_path}"
            ) from exc
        if actual_size != expected_size:
            logger.error(
                "Size mismatch apos gravacao local %s: esperado=%d, observado=%d",
                absolute_path, expected_size, actual_size,
            )
            absolute_path.unlink(missing_ok=True)
            raise AudioUploadVerificationError(
                f"Size mismatch apos gravacao local (esperado={expected_size}, observado={actual_size})"
            )

    return {
        "audio_storage_path": str(Path(relative_path).as_posix()),
        "audio_original_filename": str(original_filename or "").strip() or Path(relative_path).name,
        "audio_mime_type": str(mime_type or "").strip().lower() or "audio/wav",
        "audio_size_bytes": len(audio_bytes),
    }

def resolve_stored_audit_audio_path(relative_path: str | None):
    """Resolve o caminho relativo gravado no DB em um objeto legível (CloudStorageFile no GCS, Path no disco).

    Retorna None se `relative_path` for vazio ou (no modo local) se o path escapar
    da raiz permitida. O objeto retornado expõe exists()/read_bytes() para o caller
    ler o áudio depois.
    """
    if not relative_path:
        return None

    bucket_name = _get_bucket_name()
    if bucket_name:
        return CloudStorageFile(bucket_name, relative_path)

    root = get_audit_audio_storage_root()
    try:
        return _ensure_inside_root(root, root / relative_path)
    except ValueError:
        return None
