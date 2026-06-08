import os
import re
from pathlib import Path
from repositories import configuration

tests_dir = Path("tests")

replacements = {
    r"routers\.audit\.database\.obter_fila_revisao_classificacao_por_auditoria": "repositories.classification_review.obter_fila_revisao_classificacao_por_auditoria",
    r"routers\.audit\.database\.attach_audio_to_audit_record": "repositories.audits.attach_audio_to_audit_record",
    r"routers\.audit\.database\.persist_audit_artifacts": "repositories.audits.persist_audit_artifacts",
    r"routers\.system\.database\.queue_audit_for_supervisor_review": "repositories.audits.queue_audit_for_supervisor_review",
    r"routers\.system\.database\.get_audit_by_id": "repositories.audits.get_audit_by_id",
    r"routers\.saved_files\.database\.save_arquivo": "repositories.saved_files.save_arquivo",
    r"routers\.saved_files\.database\.get_arquivo_salvo": "repositories.saved_files.get_arquivo_salvo",
    r"routers\.saved_files\.database\.update_arquivo_salvo": "repositories.saved_files.update_arquivo_salvo",
    r"routers\.saved_files\.database\.update_audit_by_id": "repositories.audits.update_audit_result",
    r"main\.database\.obter_fila_revisao_classificacao_por_hash": "repositories.classification_review.obter_fila_revisao_classificacao_por_hash",
    r"main\.database\.sincronizar_fila_revisao_classificacao": "repositories.classification_review.sincronizar_fila_revisao_classificacao",
    r"main\.database\.corrigir_classificacao_fila_revisao": "repositories.classification_review.corrigir_classificacao_fila_revisao",
    r"main\.database\.get_ligacao_auditada_por_hash": "repositories.audits.get_audit_by_hash",
    r"automation\.database\.listar_fila_revisao_classificacao": "repositories.classification_review.listar_fila_revisao_classificacao",
    r"automation\.database\.persist_audit_artifacts": "repositories.audits.persist_audit_artifacts",
    r"automation\.database\.atualizar_status_fila_revisao_classificacao": "repositories.classification_review.atualizar_status_fila_revisao_classificacao",
    r"telefonia\.database\.obter_fila_revisao_classificacao_por_hash": "repositories.classification_review.obter_fila_revisao_classificacao_por_hash",
    r"telefonia\.database\.atualizar_status_fila_revisao_classificacao": "repositories.classification_review.atualizar_status_fila_revisao_classificacao",
    r"telefonia\.database\.persist_audit_artifacts": "repositories.audits.persist_audit_artifacts",
    r"telefonia\.database\.listar_fila_revisao_classificacao": "repositories.classification_review.listar_fila_revisao_classificacao",
    r"telefonia\.database\.get_config_value": "(lambda *args, **kwargs: configuration.get_config_value(database.get_connection, *args, **kwargs))",
    r"database\.queue_audit_for_supervisor_review": "repositories.audits.queue_audit_for_supervisor_review",
}

for root, _, files in os.walk(tests_dir):
    for f in files:
        if f.endswith(".py"):
            filepath = os.path.join(root, f)
            with open(filepath, "r", encoding="utf-8") as file:
                content = file.read()
            
            new_content = content
            for old, new in replacements.items():
                new_content = re.sub(old, new, new_content)
            
            if new_content != content:
                with open(filepath, "w", encoding="utf-8") as file:
                    file.write(new_content)
                print(f"Updated {filepath}")
