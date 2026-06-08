from __future__ import annotations
"""Official POP retrieval helpers for audit prompt RAG.

This module is deliberately file-backed and deterministic. The curated
markdown files in ``rag/sources/procedimentos_operacionais`` are the source
for direct prompt injection and for future chunk indexing.
"""


from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
import re
import unicodedata


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCEDIMENTOS_DIR = PROJECT_ROOT / "rag" / "sources" / "procedimentos_operacionais"
DEFAULT_MAX_PROMPT_CHARS = 7000


@dataclass(frozen=True)
class ProcedimentoSection:
    source_path: str
    source_hash: str
    file_stem: str
    frontmatter: dict[str, object]
    title: str
    content: str


@dataclass(frozen=True)
class ProcedimentoChunk:
    source_path: str
    source_hash: str
    setor: str | None
    alert_ids: tuple[str, ...]
    section_title: str
    chunk_index: int
    content: str


SECTOR_FILE_MAP = {
    "cadastro": "cadastro.md",
    "checklist": "checklist.md",
    "mondelez": "mondelez.md",
    "logistica_mondelez": "mondelez.md",
    "unilever": "unilever.md",
    "logistica_unilever": "unilever.md",
    "transferencia": "areas_de_risco.md",
    "distribuicao": "areas_de_risco.md",
    "uti": "areas_de_risco.md",
    "fenix": "areas_de_risco.md",
}

ALERT_FILE_MAP = {
    "CADASTRO-ANTECEDENTES": "cadastro.md",
    "4.2.1": "cadastro.md",
    "CHECKLIST-VEICULO": "checklist.md",
    "4.6.1": "checklist.md",
    "MONDELEZ-LOGISTICA-REVERSA": "mondelez.md",
    "MONDELEZ-MONITORAMENTO-I": "mondelez.md",
    "MONDELEZ-MONITORAMENTO-II": "mondelez.md",
    "4.5.1": "mondelez.md",
    "4.5.2": "mondelez.md",
    "4.5.3": "mondelez.md",
    "UNILEVER-DEVOLUCAO": "unilever.md",
    "UNILEVER-CABINETS": "unilever.md",
    "UNILEVER-TRATATIVA": "unilever.md",
    "UNILEVER-DISTRIBUICAO": "unilever.md",
    "UNILEVER-LOSSTREE": "unilever.md",
    "4.3.1": "unilever.md",
    "4.3.2": "unilever.md",
    "4.3.3": "unilever.md",
    "4.3.4": "unilever.md",
    "4.3.5": "unilever.md",
    "BAS-PRIORITARIO-POLICIA": "areas_de_risco.md",
    "BAS-POLICIAL": "areas_de_risco.md",
    "UTI-PRIORITARIO-POLICIA": "areas_de_risco.md",
    "4.1.10": "areas_de_risco.md",
}

RISK_AREA_ALERTS = {
    "UTI-PRIORITARIO-MOT",
    "UTI-PRIORITARIO-CLI",
    "UTI-POSICAO-MOT",
    "UTI-POSICAO-CLI",
    "UTI-PARADA-MOT",
    "UTI-PARADA-CLI",
    "UTI-DESVIO-MOT",
    "UTI-DESVIO-CLI",
    "UTI-PONTO-APOIO",
    "BAS-PRIORITARIO-POLICIA",
    "BAS-POLICIAL",
    "4.1.1",
    "4.1.2",
    "4.1.3",
    "4.1.4",
    "4.1.5",
    "4.1.6",
    "4.1.7",
    "4.1.8",
    "4.1.9",
    "4.1.10",
}

RISK_AREA_SECTORS = {"transferencia", "distribuicao", "uti", "fenix"}

ALERT_SECTION_HINTS = {
    "CADASTRO-ANTECEDENTES": ("cadastro", "antecedentes"),
    "4.2.1": ("cadastro", "antecedentes"),
    "CHECKLIST-VEICULO": ("checklist", "processo"),
    "4.6.1": ("checklist", "processo"),
    "MONDELEZ-LOGISTICA-REVERSA": ("logistica", "reversa"),
    "MONDELEZ-MONITORAMENTO-I": ("monitoramento", "i"),
    "MONDELEZ-MONITORAMENTO-II": ("monitoramento", "ii"),
    "4.5.1": ("logistica", "reversa"),
    "4.5.2": ("monitoramento", "i"),
    "4.5.3": ("monitoramento", "ii"),
    "UNILEVER-DEVOLUCAO": ("devolucao",),
    "UNILEVER-CABINETS": ("cabinets",),
    "UNILEVER-TRATATIVA": ("atuacao", "tratativa"),
    "UNILEVER-DISTRIBUICAO": ("distribuicao", "unilever"),
    "UNILEVER-LOSSTREE": ("loss", "tree"),
    "4.3.1": ("devolucao",),
    "4.3.2": ("cabinets",),
    "4.3.3": ("atuacao", "tratativa"),
    "4.3.4": ("distribuicao", "unilever"),
    "4.3.5": ("loss", "tree"),
    "UTI-PRIORITARIO-MOT": ("alertas", "prioritarios", "motorista"),
    "UTI-PRIORITARIO-CLI": ("alertas", "prioritarios", "cliente"),
    "UTI-POSICAO-MOT": ("posicao", "motorista"),
    "UTI-POSICAO-CLI": ("posicao", "cliente"),
    "UTI-PARADA-MOT": ("parada", "motorista"),
    "UTI-PARADA-CLI": ("parada", "cliente"),
    "UTI-DESVIO-MOT": ("desvio", "motorista"),
    "UTI-DESVIO-CLI": ("desvio", "cliente"),
    "UTI-PONTO-APOIO": ("ponto", "apoio"),
    "BAS-PRIORITARIO-POLICIA": ("acionamento", "policial"),
    "BAS-POLICIAL": ("acionamento", "policial"),
    "4.1.1": ("alertas", "prioritarios", "motorista"),
    "4.1.2": ("alertas", "prioritarios", "cliente"),
    "4.1.3": ("posicao", "motorista"),
    "4.1.4": ("posicao", "cliente"),
    "4.1.5": ("parada", "motorista"),
    "4.1.6": ("parada", "cliente"),
    "4.1.7": ("desvio", "motorista"),
    "4.1.8": ("desvio", "cliente"),
    "4.1.9": ("ponto", "apoio"),
    "4.1.10": ("acionamento", "policial"),
}


def normalize_lookup(value: object) -> str:
    normalized = unicodedata.normalize("NFD", str(value or "").strip().lower())
    without_accents = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", without_accents).strip()


def _canonical_alert_key(value: object) -> str:
    return str(value or "").strip().upper()


def _parse_frontmatter(raw_text: str) -> tuple[dict[str, object], str]:
    if not raw_text.startswith("---"):
        return {}, raw_text
    end = raw_text.find("\n---", 3)
    if end == -1:
        return {}, raw_text

    frontmatter_text = raw_text[3:end].strip()
    body = raw_text[end + len("\n---") :].lstrip()
    parsed: dict[str, object] = {}
    current_key: str | None = None
    for line in frontmatter_text.splitlines():
        if not line.strip():
            continue
        if line.startswith("  - ") and current_key:
            current = parsed.setdefault(current_key, [])
            if isinstance(current, list):
                current.append(line[4:].strip())
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            current_key = key.strip()
            value = value.strip()
            parsed[current_key] = value if value else []
    return parsed, body


def _relative_source_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT).as_posix())
    except ValueError:
        return str(path.as_posix())


def _split_sections(path: Path) -> list[ProcedimentoSection]:
    raw_text = path.read_text(encoding="utf-8")
    source_hash = sha256(raw_text.encode("utf-8")).hexdigest()
    frontmatter, body = _parse_frontmatter(raw_text)
    matches = list(re.finditer(r"(?m)^##\s+(.+?)\s*$", body))
    if not matches:
        return [
            ProcedimentoSection(
                source_path=_relative_source_path(path),
                source_hash=source_hash,
                file_stem=path.stem,
                frontmatter=frontmatter,
                title=path.stem,
                content=body.strip(),
            )
        ]

    sections: list[ProcedimentoSection] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        content = body[start:end].strip()
        sections.append(
            ProcedimentoSection(
                source_path=_relative_source_path(path),
                source_hash=source_hash,
                file_stem=path.stem,
                frontmatter=frontmatter,
                title=match.group(1).strip(),
                content=content,
            )
        )
    return sections


@lru_cache(maxsize=1)
def load_procedimento_sections() -> tuple[ProcedimentoSection, ...]:
    if not PROCEDIMENTOS_DIR.exists():
        return ()
    sections: list[ProcedimentoSection] = []
    for path in sorted(PROCEDIMENTOS_DIR.glob("*.md")):
        if path.name.startswith("_"):
            continue
        sections.extend(_split_sections(path))
    return tuple(sections)


def _resolve_file_name(sector_id: object, alert_id: object) -> str | None:
    sector_key = normalize_lookup(sector_id).replace(" ", "_")
    alert_key = _canonical_alert_key(alert_id)
    if alert_key in ALERT_FILE_MAP:
        return ALERT_FILE_MAP[alert_key]
    if sector_key in SECTOR_FILE_MAP:
        if sector_key in RISK_AREA_SECTORS and alert_key and alert_key not in RISK_AREA_ALERTS:
            return None
        return SECTOR_FILE_MAP[sector_key]
    return None


def _section_matches_hints(section_title: str, hints: tuple[str, ...]) -> bool:
    normalized_title = normalize_lookup(section_title)
    return all(normalize_lookup(hint) in normalized_title for hint in hints)


def _score_section(section: ProcedimentoSection, search_text: str) -> int:
    title_tokens = set(normalize_lookup(section.title).split())
    search_tokens = {token for token in normalize_lookup(search_text).split() if len(token) > 2}
    return len(title_tokens & search_tokens)


def find_procedimento_section(
    *,
    sector_id: object = None,
    alert_id: object = None,
    alert_label: object = None,
    alert_context: object = None,
) -> ProcedimentoSection | None:
    file_name = _resolve_file_name(sector_id, alert_id)
    if not file_name:
        return None

    candidates = [section for section in load_procedimento_sections() if section.source_path.endswith(file_name)]
    if not candidates:
        return None

    alert_key = _canonical_alert_key(alert_id)
    hints = ALERT_SECTION_HINTS.get(alert_key)
    if hints:
        for section in candidates:
            if _section_matches_hints(section.title, hints):
                return section

    search_text = " ".join(str(item or "") for item in (alert_id, alert_label, alert_context))
    scored = sorted(((_score_section(section, search_text), section) for section in candidates), key=lambda item: item[0], reverse=True)
    if scored and scored[0][0] > 0:
        return scored[0][1]

    if len(candidates) == 1:
        return candidates[0]
    return None


def _truncate_for_prompt(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars].rsplit("\n", 1)[0].strip()
    return f"{truncated}\n\n[POP truncado para caber no prompt]"


def get_procedimento_prompt_block(
    *,
    sector_id: object = None,
    alert_id: object = None,
    alert_label: object = None,
    alert_context: object = None,
    max_chars: int = DEFAULT_MAX_PROMPT_CHARS,
) -> str:
    section = find_procedimento_section(
        sector_id=sector_id,
        alert_id=alert_id,
        alert_label=alert_label,
        alert_context=alert_context,
    )
    if section is None:
        return ""

    content = _truncate_for_prompt(section.content, max_chars)
    return (
        "=== PROCEDIMENTO OPERACIONAL OFICIAL (RAG) ===\n"
        f"Fonte: {section.source_path}\n"
        f"Secao: {section.title}\n"
        "Use este POP como referencia oficial para interpretar os criterios abaixo.\n"
        "Nao invente criterios fora da lista CRITERIOS. Se houver conflito, o criterio listado e o POP oficial prevalecem sobre calibracoes historicas.\n"
        "Itens marcados como [nao-avaliavel-por-ia] nao devem ser inferidos sem evidencia direta da transcricao.\n\n"
        f"{content}"
    )


def _alert_ids_for_section(section_title: str) -> tuple[str, ...]:
    matches = [
        alert_id
        for alert_id, hints in ALERT_SECTION_HINTS.items()
        if _section_matches_hints(section_title, hints)
    ]
    return tuple(dict.fromkeys(matches))


def build_procedimento_chunks(max_chars: int = 3200) -> list[ProcedimentoChunk]:
    chunks: list[ProcedimentoChunk] = []
    for section in load_procedimento_sections():
        frontmatter_setor = section.frontmatter.get("setor")
        setor = str(frontmatter_setor).strip() if frontmatter_setor else None
        alert_ids = _alert_ids_for_section(section.title)
        paragraphs = [part.strip() for part in re.split(r"\n(?=###\s+)", section.content) if part.strip()]
        if not paragraphs:
            paragraphs = [section.content]

        current = ""
        chunk_index = 0
        for paragraph in paragraphs:
            next_content = f"{current}\n\n{paragraph}".strip() if current else paragraph
            if current and len(next_content) > max_chars:
                chunks.append(
                    ProcedimentoChunk(
                        source_path=section.source_path,
                        source_hash=section.source_hash,
                        setor=setor,
                        alert_ids=alert_ids,
                        section_title=section.title,
                        chunk_index=chunk_index,
                        content=current,
                    )
                )
                chunk_index += 1
                current = paragraph
            else:
                current = next_content
        if current:
            chunks.append(
                ProcedimentoChunk(
                    source_path=section.source_path,
                    source_hash=section.source_hash,
                    setor=setor,
                    alert_ids=alert_ids,
                    section_title=section.title,
                    chunk_index=chunk_index,
                    content=current,
                )
            )
    return chunks
