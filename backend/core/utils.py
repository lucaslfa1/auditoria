"""Utilitarios genericos do nucleo (core).

Centraliza pequenas funcoes reutilizaveis. Hoje contem a normalizacao canonica de
nome de setor em "slug", usada por triagem/classificacao e demais modulos para
comparar setores de forma consistente (sem acentos, minusculo, mapeando nomes
historicos como GRS e as UTIs regionais para o id canonico "uti").

Sem custo de API: so processamento de string em CPU.
"""
import re
import unicodedata

def normalize_sector_slug(sector_name: str) -> str:
    """Centralizes sector normalization rules.
    
    1. Removes accents and standardizes to lowercase.
    2. Maps "grs" or "grs-br" to "uti".
    3. Normalizes all regional UTIs ("uti-rj", "uti-sp", "uti-mg", "uti-bbm") strictly to "uti" 
       for all general modules (Triage, Classification, etc.).
    """
    if not sector_name:
        return ""
        
    normalized = unicodedata.normalize("NFKD", sector_name)
    without_marks = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    slug = re.sub(r"[^\w\s-]", "", without_marks).strip().lower()
    slug = re.sub(r"\s+", "-", slug)

    if slug in ("grs", "grs-br"):
        return "uti"
        
    # Map any "uti-something" to "uti" (e.g., uti-rj, uti-sp, uti-bbm)
    if slug.startswith("uti-"):
        return "uti"

    return slug
