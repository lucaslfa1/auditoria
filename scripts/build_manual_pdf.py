"""Gera um PDF do documento tecnico a partir do Markdown.

Pipeline: Markdown -> HTML estilizado (sumario automatico, codigo colorido com
pygments, diagramas Mermaid renderizados, CSS de impressao A4) -> Edge headless
(Chromium) imprime em PDF. Nao precisa de pandoc nem LaTeX.

Pre-requisito: `pip install markdown` (pygments costuma vir no venv).
Os diagramas Mermaid sao renderizados por mermaid.js (CDN) durante a impressao;
sem rede, o bloco cai para o texto-fonte (fallback, nunca fica em branco).

Uso:
    backend/.venv/Scripts/python.exe scripts/build_manual_pdf.py
    backend/.venv/Scripts/python.exe scripts/build_manual_pdf.py <entrada.md> <saida.pdf>
"""
import os
import pathlib
import re
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
<title>Documentacao Tecnica</title>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<script>
  try {
    mermaid.initialize({ startOnLoad: true, theme: 'neutral',
      flowchart: { useMaxWidth: true, htmlLabels: true, curve: 'basis' },
      themeVariables: { fontSize: '13px', primaryColor: '#eef4fb',
        primaryBorderColor: '#0b5cab', lineColor: '#5b7790', fontFamily: 'Segoe UI, Arial' } });
  } catch (e) {}
</script>
<style>
  @page { size: A4; margin: 18mm 16mm 18mm 16mm; }
  html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  body { font-family: "Segoe UI", Calibri, Arial, sans-serif; font-size: 10.5pt;
         line-height: 1.55; color: #1f2a37; }
  h1,h2,h3,h4 { color: #0b3d66; line-height: 1.25; break-after: avoid; }
  h1 { font-size: 21pt; }
  h2 { font-size: 15.5pt; margin: 1.5em 0 .5em; padding-bottom: 5px;
       border-bottom: 2px solid #d7e3ee; }
  h3 { font-size: 12.5pt; margin: 1.15em 0 .4em; color: #14507e; }
  h4 { font-size: 11pt; margin: 1em 0 .3em; }
  p, li { orphans: 3; widows: 3; }
  a { color: #0b5cab; text-decoration: none; }
  strong { color: #102a43; }
  table { border-collapse: collapse; width: 100%; margin: .8em 0; font-size: 9.5pt;
          break-inside: avoid; }
  th, td { border: 1px solid #d2dde7; padding: 6px 9px; text-align: left; vertical-align: top; }
  th { background: #eef3f8; color: #0b3d66; }
  tr:nth-child(even) td { background: #f8fafc; }
  code { font-family: Consolas, "Courier New", monospace; font-size: 9pt;
         background: #eef2f6; padding: 1px 4px; border-radius: 3px; }
  pre { font-family: Consolas, "Courier New", monospace; font-size: 8.6pt;
        line-height: 1.4; background: #f7f9fb; border: 1px solid #e2e8f0;
        border-left: 3px solid #0b5cab; border-radius: 5px; padding: 10px 12px;
        white-space: pre-wrap; overflow-wrap: anywhere; break-inside: avoid; }
  pre code { background: none; padding: 0; font-size: 8.6pt; }
  blockquote { background: #f3f7fb; border-left: 3px solid #9cc3e6; margin: .8em 0;
               padding: 7px 12px; border-radius: 4px; color: #2b3b4a; break-inside: avoid; }
  blockquote p { margin: .2em 0; }
  hr { border: none; border-top: 1px solid #dde5ec; margin: 1.4em 0; }
  /* Capa */
  .cover { height: 245mm; display: flex; flex-direction: column;
           justify-content: center; break-after: page; }
  .cover .rule { width: 64px; height: 4px; background: #0b5cab; margin-bottom: 18px; }
  .cover h1 { font-size: 30pt; margin: 0 0 6px; color: #0b3d66; }
  .cover .sub { font-size: 13pt; color: #44606f; max-width: 80%; }
  .cover .meta { margin-top: 42px; font-size: 10.5pt; color: #33485a; line-height: 1.9; }
  .cover .meta b { color: #0b3d66; }
  /* Sumario */
  .toc-page { break-after: page; }
  .toc-page > h2 { border: none; }
  .toc ul { list-style: none; padding-left: 16px; margin: 3px 0; }
  .toc > ul { padding-left: 0; }
  .toc li { margin: 2px 0; font-size: 10pt; }
  .toc > ul > li { font-weight: 600; margin-top: 6px; color: #0b3d66; }
  .toc > ul > li > ul > li { font-weight: 400; color: #33485a; }
  /* Diagramas Mermaid */
  .mermaid { text-align: center; margin: 14px 0; break-inside: avoid; }
  .figcap { text-align: center; font-size: 8.6pt; color: #64748b; margin-top: -4px; margin-bottom: 12px; }
  /* Mockups de tela (UI) */
  .uiwin { border: 1px solid #c4d0dc; border-radius: 8px; overflow: hidden;
           margin: 12px 0; font-size: 9pt; break-inside: avoid;
           box-shadow: 0 1px 0 #e7edf3; }
  .uiwin .bar { background: #0b3d66; color: #fff; padding: 5px 11px; font-weight: 600; font-size: 9pt; }
  .uiwin .bar .rt { float: right; font-weight: 400; opacity: .85; }
  .uiwin .body { padding: 10px 12px; background: #fff; }
  .uirow { display: flex; gap: 8px; align-items: center; padding: 6px 2px;
           border-bottom: 1px solid #eef2f6; }
  .uirow:last-child { border-bottom: none; }
  .uirow .grow { flex: 1; }
  .uicols { display: flex; gap: 10px; }
  .uicols .col { flex: 1; border: 1px solid #dbe3ea; border-radius: 6px; padding: 9px; background: #fbfdff; }
  .uicols .col h5 { margin: 0 0 6px; font-size: 9pt; color: #0b3d66; }
  .btn { display: inline-block; border: 1px solid #c4d0dc; border-radius: 5px;
         padding: 2px 9px; background: #eef2f6; font-size: 8.5pt; color: #243b53; white-space: nowrap; }
  .btn.primary { background: #0b5cab; color: #fff; border-color: #0b5cab; }
  .tag { display: inline-block; border-radius: 10px; padding: 1px 9px; background: #e6eef6;
         font-size: 8pt; color: #14507e; }
  .tag.on { background: #def7e6; color: #18794e; }
  .field { display: inline-block; border: 1px solid #c4d0dc; border-radius: 5px;
           padding: 2px 8px; background: #fff; color: #6b7b8c; min-width: 86px; font-size: 8.5pt; }
  .muted { color: #64748b; }
  .sel::after { content: " \\25BE"; color: #6b7b8c; }
__PYG__
</style></head>
<body>
  <section class="cover">
    <div class="rule"></div>
    <h1>Documenta&ccedil;&atilde;o T&eacute;cnica</h1>
    <div class="sub">Sistema de Auditoria de Liga&ccedil;&otilde;es &mdash; arquitetura, fluxo, c&oacute;digo e telas.</div>
    <div class="meta">
      <div><b>Vers&atilde;o do sistema documentada:</b> 1.3.203</div>
      <div><b>Data de refer&ecirc;ncia:</b> 2026-06-24</div>
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
    # Blocos ```mermaid viram <div class="mermaid"> para o mermaid.js renderizar.
    text = re.sub(
        r"```mermaid\n(.*?)\n```",
        lambda m: '<div class="mermaid">\n' + m.group(1) + "\n</div>",
        text,
        flags=re.S,
    )
    # A capa substitui o titulo H1 + intro: corta tudo antes da secao 0.
    anchor = "## 0. Sobre este documento"
    if anchor in text:
        text = text[text.index(anchor):]

    md = markdown.Markdown(
        extensions=["tables", "fenced_code", "codehilite", "toc", "sane_lists",
                    "attr_list", "md_in_html"],
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
        return 2

    profile_dir = build_dir / "_browser_profile"
    cmd = [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--no-pdf-header-footer",
        "--run-all-compositor-stages-before-draw",
        f"--user-data-dir={profile_dir}",
        "--virtual-time-budget=15000",
        f"--print-to-pdf={out_pdf}",
        html_path.as_uri(),
    ]
    print("Gerando PDF com:", os.path.basename(browser))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
    if not out_pdf.exists() or out_pdf.stat().st_size == 0:
        cmd[1] = "--headless"
        subprocess.run(cmd, capture_output=True, text=True, timeout=240)

    if out_pdf.exists() and out_pdf.stat().st_size > 0:
        print(f"PDF gerado: {out_pdf} ({out_pdf.stat().st_size / 1024:.0f} KB)")
        return 0
    print("ERRO: PDF nao foi gerado.")
    print(result.stdout[-800:])
    print(result.stderr[-800:])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
