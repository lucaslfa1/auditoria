"""Extração e parsing de documentos (PDF de chat) para auditoria documental.

Separado de ``core/audit.py`` para isolar a extração crua do texto (``pypdf`` na
Fase 1; ``pdfplumber`` é o candidato natural da Fase 2) do parsing/limpeza, e para
permitir testes determinísticos sobre o texto extraído sem depender do binário do
PDF.

Formato primário suportado: export de chat do **Service Cloud** (HTML impresso em
PDF), usado pelos setores Receptivo, Checklist, Operação Taborda e Célula. O parser
limpa artefatos de impressão, conserta palavras quebradas por word-wrap, estrutura
o diálogo por locutor (papéis canônicos ``Operador``/``Cliente``/``Bot`` no prefixo
do texto — convenção já lida pelo front e pelo prompt da IA) e reordena por horário.

⚠️ Fase 1: a associação de respostas curtas do cliente (ex: "2", CPF, senha) ao
turno certo é *best-effort* — o PDF cru já chega com as colunas do chat trocadas.
A reconstrução fiel depende das coordenadas do PDF (Fase 2 / pdfplumber).
"""
from __future__ import annotations

import io
import logging
import re
from datetime import datetime

logger = logging.getLogger(__name__)

# Cabeçalho do Service Cloud: "<Locutor><AAAA-MM-DD> <HH:MM:SS>" (nome colado na data).
_SC_HEADER = re.compile(
    r"^(?P<speaker>.+?)(?P<date>\d{4}-\d{2}-\d{2}) (?P<time>\d{2}:\d{2}:\d{2})\s*$"
)

# Rodapés de impressão do navegador (cabeçalho/rodapé da página HTML→PDF).
_PRINT_TIMESTAMP = re.compile(
    r"\d{1,2}/\d{1,2}/\d{4},?\s+\d{1,2}:\d{2}\s+Service Cloud\s*"
)
_PRINT_FILEURL = re.compile(r"file:///.+?\.html\s+\d+/\d+\s*")

# Read-receipt ("Leitura") que o Service Cloud insere abaixo de cada mensagem lida.
_READ_RECEIPT = re.compile(r"(?m)^[ \t]*Leitura[ \t]*$")

# WhatsApp: "[DD/MM/AAAA HH:MM:SS] Fulano: msg".
_WHATSAPP = re.compile(
    r"\[(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2})\]\s+([^:]+):\s+(.*)"
)

# Sufixos de setor que identificam o atendente (operador) no nome do locutor.
_SECTOR_HINTS = ("célula", "celula", "taborda", "checklist", "receptivo")

# Acima deste comprimento a linha provavelmente bateu na largura da página: uma
# quebra logo a seguir é word-wrap (continuação de palavra), não fim de mensagem.
_WRAP_MIN_LEN = 45


def extract_raw_text(file_content: bytes) -> str:
    """Extrai o texto cru de um PDF.

    Fase 1 usa ``pypdf``. Mantido isolado para que a Fase 2 possa trocar por uma
    extração com coordenadas (``pdfplumber``) sem mexer no parser.
    """
    try:
        import pypdf

        with io.BytesIO(file_content) as fh:
            reader = pypdf.PdfReader(fh)
            return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as exc:  # noqa: BLE001 - extração best-effort; falha vira texto vazio
        logger.warning("Falha ao extrair texto do PDF: %s", exc)
        return ""


def _strip_print_artifacts(text: str) -> str:
    """Remove rodapés de impressão e read-receipts do texto extraído."""
    text = _PRINT_TIMESTAMP.sub("", text)
    text = _PRINT_FILEURL.sub("", text)
    text = _READ_RECEIPT.sub("", text)
    return text


def detect_document_format(text: str) -> str:
    """Classifica o formato do documento: service_cloud | whatsapp | generic."""
    if not text or not text.strip():
        return "generic"
    header_hits = sum(1 for line in text.splitlines() if _SC_HEADER.match(line.strip()))
    if header_hits >= 2:
        return "service_cloud"
    if _WHATSAPP.search(text):
        return "whatsapp"
    return "generic"


def _classify_role(speaker_raw: str, operator_name: str | None) -> str:
    """Mapeia o nome do locutor para um papel canônico (Operador/Cliente/Bot)."""
    speaker = (speaker_raw or "").strip()
    low = speaker.lower()
    if low.startswith("bot") or low.endswith(" bot") or "atendente virtual" in low:
        return "Bot"
    if " - " in speaker:  # ex: "Selma - Célula"
        return "Operador"
    if any(hint in low for hint in _SECTOR_HINTS):
        return "Operador"
    if operator_name and operator_name.strip():
        first = operator_name.strip().split()[0].lower()
        if first and first in low:
            return "Operador"
    return "Cliente"


def _dewrap_lines(lines: list[str]) -> str:
    """Junta um turno em uma string, consertando palavras quebradas por word-wrap.

    Heurística: se a última linha física é longa (bateu na largura da página) e
    termina em letra, e a próxima linha começa em letra minúscula, junta sem espaço
    (continua a palavra). Caso contrário, junta com espaço. O limiar de comprimento
    evita colar mensagens curtas legítimas (ex: "Bom dia").
    """
    pieces: list[str] = []
    last_len = 0
    last_char = ""
    for raw in lines:
        line = raw.rstrip()
        if not line:
            continue
        if not pieces:
            pieces.append(line)
        elif last_len >= _WRAP_MIN_LEN and last_char.isalpha() and line[:1].islower():
            pieces[-1] = pieces[-1] + line  # cola: continuação de palavra quebrada
        else:
            pieces.append(line)
        last_len = len(line)
        last_char = line[-1:]
    return " ".join(p for p in pieces if p).strip()


def parse_service_cloud(text: str, operator_name: str | None = None) -> list[dict]:
    """Estrutura um export de chat do Service Cloud em segmentos por locutor."""
    text = _strip_print_artifacts(text)

    segments: list[dict] = []
    current_header: tuple[str, str] | None = None  # (speaker_raw, "HH:MM:SS")
    buffer: list[str] = []
    preamble: list[str] = []

    def flush() -> None:
        nonlocal current_header
        if current_header is None:
            return
        speaker_raw, when = current_header
        body = _dewrap_lines(buffer)
        if body:
            role = _classify_role(speaker_raw, operator_name)
            segments.append({"start": when, "end": when, "text": f"{role}: {body}"})
        buffer.clear()

    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            continue
        match = _SC_HEADER.match(line)
        if match:
            flush()
            current_header = (match.group("speaker").strip(), match.group("time"))
        elif current_header is None:
            preamble.append(line)
        else:
            buffer.append(line)
    flush()

    # Linhas órfãs antes do primeiro cabeçalho são, no layout do Service Cloud,
    # falas do cliente cujo cabeçalho ficou em outra coluna.
    if preamble:
        body = _dewrap_lines(preamble)
        if body:
            when = segments[0]["start"] if segments else "00:00:00"
            segments.insert(0, {"start": when, "end": when, "text": f"Cliente: {body}"})

    # Rede de segurança contra a troca de coluna do PDF: ordena cronologicamente.
    segments.sort(key=lambda seg: seg["start"])
    return segments


def parse_whatsapp_log(text: str) -> list[dict]:
    """Parser de export de WhatsApp ("[DD/MM/AAAA HH:MM:SS] Fulano: msg").

    Versão canônica (movida de ``core/audit.py``). Retorna ``[]`` quando o texto
    não está nesse formato, para o dispatcher tentar outro parser.
    """
    if not _WHATSAPP.search(text):
        return []

    segments: list[dict] = []
    current: dict | None = None
    preamble: list[str] = []

    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            continue
        match = _WHATSAPP.match(line)
        if match:
            if preamble:
                segments.append({"start": "00:00", "end": "00:00", "text": "\n".join(preamble)})
                preamble = []
            if current:
                segments.append(current)
            ts, speaker, content = match.group(1), match.group(2), match.group(3)
            try:
                time_str = datetime.strptime(ts, "%d/%m/%Y %H:%M:%S").strftime("%H:%M")
            except ValueError:
                time_str = "00:00"
            current = {"start": time_str, "end": time_str, "text": f"{speaker}: {content}"}
        elif current:
            current["text"] += f"\n{line}"
        else:
            preamble.append(line)

    if preamble:
        segments.append({"start": "00:00", "end": "00:00", "text": "\n".join(preamble)})
    if current:
        segments.append(current)
    return segments


def parse_document(text: str, operator_name: str | None = None) -> list[dict]:
    """Dispatcher: detecta o formato e estrutura o documento em segmentos.

    Fallback genérico devolve um único segmento com o texto limpo, para nunca
    perder conteúdo quando o formato é desconhecido.
    """
    fmt = detect_document_format(text)
    if fmt == "service_cloud":
        segments = parse_service_cloud(text, operator_name)
        if segments:
            return segments
    elif fmt == "whatsapp":
        segments = parse_whatsapp_log(text)
        if segments:
            return segments

    cleaned = _strip_print_artifacts(text).strip()
    return [{"start": "00:00", "end": "00:00", "text": cleaned}] if cleaned else []
