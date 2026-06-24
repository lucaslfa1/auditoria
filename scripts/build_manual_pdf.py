"""Gera um PDF do Manual do Sistema a partir do Markdown.

Pipeline: Markdown -> HTML estilizado (sumario automatico + codigo colorido com
pygments) -> Edge headless (Chromium) imprime em PDF. Nao precisa de pandoc nem
LaTeX; usa o Edge que ja vem no Windows.

Pre-requisito: `pip install markdown` (pygments ja costuma vir no venv).

Uso:
    backend/.venv/Scripts/python.exe scripts/build_manual_pdf.py
    backend/.venv/Scripts/python.exe scripts/build_manual_pdf.py <entrada.md> <saida.pdf>

Depois de colar os prints reais no Markdown, basta rodar de novo.
"""
import os
import pathlib
import subprocess
import sys

import markdown
from pygments.formatters import HtmlFormatter

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_MD = ROOT / "docs" / "manual-sistema" / "MANUAL-SISTEMA-AUDITORIA.md"
DEFAULT_PDF = ROOT / "docs" / "manual-sistema" / "MANUAL-SISTEMA-AUDITORIA.pdf"

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]

TEMPLATE = """<!doctype html>
<html lang="pt-br"><head><meta charset="utf-8">
<title>Manual do Sistema de Auditoria</title>
<style>
  @page { size: A4; margin: 18mm 16mm 20mm 16mm; }
  html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  body { font-family: "Segoe UI", Calibri, Arial, sans-serif; font-size: 10.5pt;
         line-height: 1.5; color: #1f2933; }
  h1, h2, h3, h4 { color: #0b3d66; line-height: 1.25; break-after: avoid; }
  h1 { font-size: 20pt; } h2 { font-size: 15pt; margin-top: 1.4em;
       border-bottom: 2px solid #d7e3ee; padding-bottom: 3px; }
  h3 { font-size: 12.5pt; margin-top: 1.1em; } h4 { font-size: 11pt; }
  p, li { orphans: 3; widows: 3; }
  a { color: #0b3d66; text-decoration: none; }
  table { border-collapse: collapse; width: 100%; margin: 0.8em 0; font-size: 9.5pt;
          break-inside: avoid; }
  th, td { border: 1px solid #c5d4e0; padding: 5px 8px; text-align: left;
           vertical-align: top; }
  th { background: #eef3f8; color: #0b3d66; }
  tr:nth-child(even) td { background: #f7fafc; }
  code { font-family: Consolas, "Courier New", monospace; font-size: 9pt;
         background: #eef1f4; padding: 1px 4px; border-radius: 3px; }
  pre { font-family: Consolas, "Courier New", monospace; font-size: 8.5pt;
        line-height: 1.35; background: #f6f8fa; border: 1px solid #d7dee5;
        border-radius: 6px; padding: 10px 12px; white-space: pre-wrap;
        overflow-wrap: anywhere; break-inside: avoid; }
  pre code { background: none; padding: 0; font-size: 8.5pt; }
  blockquote { border-left: 3px solid #9cc0dd; background: #f3f8fc; margin: 0.8em 0;
               padding: 6px 12px; color: #334; break-inside: avoid; }
  blockquote pre { background: #eef3f8; }
  /* Capa */
  .cover { height: 247mm; display: flex; flex-direction: column;
           justify-content: center; break-after: page; }
  .cover .kicker { text-transform: uppercase; letter-spacing: 3px; color: #4a6a85;
                   font-size: 11pt; }
  .cover h1 { font-size: 30pt; margin: 8px 0 4px; }
  .cover .sub { font-size: 13pt; color: #44606f; max-width: 70%; }
  .cover .meta { margin-top: 40px; font-size: 11pt; color: #33485a; }
  .cover .meta b { color: #0b3d66; }
  /* Sumario */
  .toc-page { break-after: page; }
  .toc-page > h2 { border: none; }
  .toc ul { list-style: none; padding-left: 14px; margin: 4px 0; }
  .toc > ul { padding-left: 0; }
  .toc li { margin: 2px 0; font-size: 10pt; }
  .toc > ul > li { font-weight: 600; margin-top: 6px; }
__PYG__
</style></head>
<body>
  <section class="cover">
    <div class="kicker">NSTECH &middot; Documenta&ccedil;&atilde;o do Sistema</div>
    <h1>Manual do Sistema de Auditoria de Liga&ccedil;&otilde;es</h1>
    <div class="sub">Documenta&ccedil;&atilde;o t&eacute;cnica e operacional &mdash; explica&ccedil;&otilde;es, c&oacute;digo e guia das telas.</div>
    <div class="meta">
      <div><b>Vers&atilde;o do documento:</b> 1.0</div>
      <div><b>Data de emiss&atilde;o:</b> 2026-06-24</div>
      <div><b>Classifica&ccedil;&atilde;o:</b> Uso interno</div>
      <div><b>Vers&atilde;o do sistema na emiss&atilde;o:</b> 1.3.203</div>
    </div>
  </section>
  <section class="toc-page">
    <h2>Sum&aacute;rio</h2>
    __TOC__
  </section>
  __BODY__
</body></html>
"""


def find_browser():
    for path in EDGE_CANDIDATES:
        if os.path.exists(path):
            return path
    return None


def main():
    src = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_MD
    out_pdf = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_PDF
    build_dir = src.parent / "_build"
    build_dir.mkdir(parents=True, exist_ok=True)
    html_path = build_dir / "manual.html"

    text = src.read_text(encoding="utf-8")
    # Mermaid nao renderiza no PDF estatico: mostra como texto pre-formatado.
    text = text.replace("```mermaid", "```text")
    # A capa substitui o titulo H1 + intro: corta tudo antes da secao 0.
    anchor = "## 0. Controle do documento"
    if anchor in text:
        text = text[text.index(anchor):]

    md = markdown.Markdown(
        extensions=["tables", "fenced_code", "codehilite", "toc", "sane_lists", "attr_list"],
        extension_configs={"codehilite": {"guess_lang": False, "noclasses": False}},
    )
    body_html = md.convert(text)
    toc_html = md.toc
    pyg_css = HtmlFormatter(style="friendly").get_style_defs(".codehilite")

    html = (
        TEMPLATE.replace("__PYG__", pyg_css)
        .replace("__TOC__", toc_html)
        .replace("__BODY__", body_html)
    )
    html_path.write_text(html, encoding="utf-8")
    print(f"HTML gerado: {html_path}")

    browser = find_browser()
    if not browser:
        print("ERRO: Edge/Chrome nao encontrado. HTML pronto em:", html_path)
        print("Abra o HTML no navegador e use 'Imprimir > Salvar como PDF'.")
        return 2

    profile_dir = build_dir / "_browser_profile"
    cmd = [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--no-pdf-header-footer",
        f"--user-data-dir={profile_dir}",
        "--virtual-time-budget=4000",
        f"--print-to-pdf={out_pdf}",
        html_path.as_uri(),
    ]
    print("Gerando PDF com:", os.path.basename(browser))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if not out_pdf.exists() or out_pdf.stat().st_size == 0:
        # Fallback para a flag headless antiga.
        cmd[1] = "--headless"
        subprocess.run(cmd, capture_output=True, text=True, timeout=180)

    if out_pdf.exists() and out_pdf.stat().st_size > 0:
        kb = out_pdf.stat().st_size / 1024
        print(f"PDF gerado: {out_pdf} ({kb:.0f} KB)")
        return 0
    print("ERRO: PDF nao foi gerado.")
    print(result.stdout[-1000:])
    print(result.stderr[-1000:])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
