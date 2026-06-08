"""Remove `from repositories import audits` quando o simbolo `audits` nao e usado no arquivo.

Sintoma do refactor pos-MIT: import injetado massivamente como "polyfill" em ~138 arquivos.
Em muitos deles `audits` nunca e referenciado. Este script faz a limpeza segura via AST.

Uso: python backend/scripts/utils/cleanup_orphan_audits_import.py [--apply]
Sem --apply, modo dry-run lista os candidatos. Com --apply, reescreve os arquivos.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "backend"
ORPHAN_LINE = "from repositories import audits"


def _has_orphan_import(tree: ast.AST) -> bool:
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module != "repositories":
            continue
        for alias in node.names:
            if alias.name == "audits" and alias.asname is None and node.level == 0:
                return True
    return False


def _uses_audits_symbol(tree: ast.AST) -> bool:
    """True se algum Name 'audits' for referenciado fora do import top-level."""
    top_import_lines: set[int] = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "repositories":
            for alias in node.names:
                if alias.name == "audits":
                    top_import_lines.add(node.lineno)

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "audits":
            if node.value.lineno not in top_import_lines:
                return True
        if isinstance(node, ast.Name) and node.id == "audits":
            if node.lineno not in top_import_lines:
                return True
        # `from repositories.audits import X` ou `import repositories.audits` tambem cobrem usos validos
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("repositories.audits"):
            return True
    return False


def _strip_orphan_lines(text: str) -> tuple[str, int]:
    lines = text.splitlines(keepends=True)
    new_lines: list[str] = []
    removed = 0
    for line in lines:
        stripped = line.strip()
        if stripped == ORPHAN_LINE:
            removed += 1
            continue
        new_lines.append(line)
    return "".join(new_lines), removed


def scan(apply: bool) -> dict:
    candidates: list[Path] = []
    skipped_used: list[Path] = []
    changed: list[Path] = []

    for path in BACKEND_ROOT.rglob("*.py"):
        parts = path.parts
        if "__pycache__" in parts or "archive" in parts:
            continue

        try:
            source = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue

        if not _has_orphan_import(tree):
            continue

        if _uses_audits_symbol(tree):
            skipped_used.append(path)
            continue

        candidates.append(path)

        if apply:
            new_source, removed = _strip_orphan_lines(source)
            if removed and new_source != source:
                path.write_text(new_source, encoding="utf-8")
                changed.append(path)

    return {
        "candidates": candidates,
        "skipped_used": skipped_used,
        "changed": changed,
        "apply": apply,
    }


def main(argv: list[str]) -> int:
    apply = "--apply" in argv
    result = scan(apply=apply)
    cand = result["candidates"]
    skipped = result["skipped_used"]
    changed = result["changed"]

    print(f"Arquivos com `from repositories import audits` no topo (sem uso real): {len(cand)}")
    print(f"Arquivos com o import mas usando audits (mantidos): {len(skipped)}")
    if apply:
        print(f"Arquivos reescritos: {len(changed)}")
    else:
        print("Modo dry-run. Use --apply para reescrever.")
        for p in cand[:50]:
            print(f"  - {p.relative_to(REPO_ROOT)}")
        if len(cand) > 50:
            print(f"  ... e mais {len(cand) - 50} arquivos")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
