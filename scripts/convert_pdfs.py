import os
from pypdf import PdfReader

def convert_pdf_to_md(pdf_path, md_path):
    print(f"Converting {pdf_path} to {md_path}...")
    try:
        reader = PdfReader(pdf_path)
        text = f"# Critérios de Auditoria: {os.path.basename(pdf_path).replace('.pdf', '')}\n\n"
        for i, page in enumerate(reader.pages):
            page_text = page.extract_text()
            if page_text:
                text += f"## Página {i+1}\n{page_text}\n\n"
        
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(text)
        print(f"Success: {md_path}")
    except Exception as e:
        print(f"Error converting {pdf_path}: {e}")

pdf_dir = "auditoria_criterios"
md_dir = "vertex_knowledge_base/2_Regras_Negocio/Criterios_Markdown"

os.makedirs(md_dir, exist_ok=True)

for file in os.listdir(pdf_dir):
    if file.endswith(".pdf"):
        pdf_path = os.path.join(pdf_dir, file)
        md_name = file.replace("CRITÉRIOS DA AUDITORIA - ", "").replace(" ", "_").replace("&", "E").replace(".pdf", ".md")
        md_path = os.path.join(md_dir, md_name)
        convert_pdf_to_md(pdf_path, md_path)
