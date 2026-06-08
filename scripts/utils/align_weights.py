
import yaml
import json
import re

# Mapping YAML Alert ID -> Excel Category Key
ALERT_MAPPING = {
    "UTI-PRIORITARIO-MOT": "ALERTAS PRIORIT",
    "UTI-PRIORITARIO-CLI": "ALERTAS PRIORIT",
    "UTI-POSICAO-MOT": "POSI",
    "UTI-POSICAO-CLI": "POSI",
    "UTI-PARADA-MOT": "PARADA INDEVIDAM",
    "UTI-PARADA-CLI": "PARADA INDEVIDAC",
    "UTI-DESVIO-MOT": "DESVIO DE ROTAM",
    "UTI-DESVIO-CLI": "DESVIO DE ROTAC",
    "UTI-PONTO-APOIO": "POSI",
    "UTI-PRIORITARIO-POLICIA": "ALERTAS PRIORIT",
    "BAS-PRIORITARIO-POLICIA": "ALERTAS PRIORIT",
    "CADASTRO-ANTECEDENTES": "ANTECEDENTESR",
    "UNILEVER-DEVOLUCAO": "DEVOLU",
    "UNILEVER-CABINETS": "CABINETSC",
    "UNILEVER-TRATATIVA": "ATUA",
    "UNILEVER-DISTRIBUICAO": "DISTRIBUI",
    "UNILEVER-LOSSTREE": "LOSS TREEC",
    "LOGISTICA-ESTADIA": "ESTADIAM",
    "LOGISTICA-TEMPERATURA-MOT": "CONT",
    "LOGISTICA-TEMPERATURA-CLI": "CONT",
    "LOGISTICA-DESLIG-TEMP-MOT": "DESLIGAMENTO",
    "LOGISTICA-DESLIG-TEMP-CLI": "DESLIGAMENTO",
    "LOGISTICA-ATRASO-ENTREGA": "ATRASO DE ENTREGAM",
    "LOGISTICA-PARADA": "PARADA INDEVIDA LOG",
    "LOGISTICA-DESVIO": "DESVIO DE ROTA\xa0 LOG",
    "LOGISTICA-ATIVACAO-AE": "ATIVA",
    "LOGISTICA-ATRASO": "ATRASO DE ENTREGAC",
    "LOGISTICA-POSICAO": "POSI",
    "LOGISTICA-TABORDA": "TELEF",
    "LOGISTICA-ATRASO-INICIO": "ATRASO DE ENTREGAM",
    "MONDELEZ-LOGISTICA-REVERSA": "LOGISTICA REVERSAR",
    "MONDELEZ-MONITORAMENTO-I": "MONITORAMENTO",
    "MONDELEZ-MONITORAMENTO-II": "MONITORAMENTO",
    "RECEPTIVO-CHATBOT": "CHATBOTR",
    "CELULA-RECEPTIVO": "TELEF"
}

SUB_FILTER = {
    "UTI-PRIORITARIO-MOT": "Motorista",
    "UTI-PRIORITARIO-CLI": "Cliente",
    "UTI-POSICAO-MOT": "Motorista",
    "UTI-POSICAO-CLI": "Cliente",
    "UTI-PONTO-APOIO": "Ponto de Apoio",
    "UTI-PRIORITARIO-POLICIA": "Policia",
    "BAS-PRIORITARIO-POLICIA": "Policia",
    "LOGISTICA-TEMPERATURA-MOT": "Motorista",
    "LOGISTICA-TEMPERATURA-CLI": "Cliente",
}

def align():
    with open('backend/db/scoring_rules.yaml', 'r', encoding='utf-8') as f:
        yaml_data = yaml.safe_load(f)
    
    with open('criterios_pesos_extraidos.json', 'r', encoding='utf-8') as f:
        excel_data = json.load(f)

    for alert in yaml_data['alerts']:
        aid = alert['id']
        exc_cat = ALERT_MAPPING.get(aid)
        if not exc_cat or exc_cat not in excel_data:
            # For Checklist or others without mapping, ensure total is 10.0
            total = sum(c['weight'] for c in alert['criteria'])
            if total > 0 and abs(total - 10.0) > 0.1:
                factor = 10.0 / total
                for c in alert['criteria']:
                    c['weight'] = round(c['weight'] * factor, 2)
            continue
        
        items = excel_data[exc_cat]
        filter_kw = SUB_FILTER.get(aid)
        if filter_kw:
            items = [i for i in items if filter_kw in i['referencia']]
        
        first_set = []
        seen_nums = set()
        for item in items:
            m = re.search(r'(\d+)$', item['referencia'])
            if m:
                num = int(m.group(1))
                if num in seen_nums: break
                seen_nums.add(num)
                first_set.append(item)
        
        if not first_set: first_set = items[:10]

        # Reset all weights to 0.05 (minimal) or 0.0
        # I'll use 0.0 to be strict with Excel
        for c in alert['criteria']:
            c['weight'] = 0.0
        
        excel_remaining = list(first_set)
        
        # Mapping Logic
        # 1. Identificação (Saudação/Nome/Setor)
        id_excel = next((i for i in excel_remaining if 'identificou' in i['pergunta'].lower()), None)
        if id_excel:
            id_yaml = [c for c in alert['criteria'] if any(k in c['label'] for k in ['Saudação', 'Nome', 'Setor'])]
            if id_yaml:
                w_per = round(id_excel['peso'] / len(id_yaml), 3)
                for c in id_yaml: c['weight'] = w_per
                excel_remaining.remove(id_excel)
        
        # 2. Senha
        senha_excel = next((i for i in excel_remaining if 'senha' in i['pergunta'].lower()), None)
        if senha_excel:
            senha_yaml = next((c for c in alert['criteria'] if 'senha' in c['label'].lower()), None)
            if senha_yaml:
                senha_yaml['weight'] = senha_excel['peso']
                excel_remaining.remove(senha_excel)

        # 3. Motivo Contato
        motivo_excel = next((i for i in excel_remaining if 'motivo' in i['pergunta'].lower() and 'contato' in i['pergunta'].lower()), None)
        if motivo_excel:
            motivo_yaml = next((c for c in alert['criteria'] if 'motivo' in c['label'].lower() and 'contato' in c['label'].lower()), None)
            if motivo_yaml:
                motivo_yaml['weight'] = motivo_excel['peso']
                excel_remaining.remove(motivo_excel)

        # 4. Cordialidade / Despedida
        cordial_excel = next((i for i in excel_remaining if 'cordial' in i['pergunta'].lower()), None)
        if cordial_excel:
            cordial_yaml = [c for c in alert['criteria'] if any(k in c['label'].lower() for k in ['despedida', 'cordialidade', 'entonação'])]
            if cordial_yaml:
                w_per = round(cordial_excel['peso'] / len(cordial_yaml), 3)
                for c in cordial_yaml: c['weight'] = w_per
                excel_remaining.remove(cordial_excel)

        # 5. Rest of criteria - Fuzzy match
        for c in alert['criteria']:
            if c['weight'] > 0: continue
            
            best_match = None
            for i in excel_remaining:
                words = [w for w in re.findall(r'\w+', c['label'].lower()) if len(w) > 4]
                if any(w in i['pergunta'].lower() for w in words):
                    best_match = i
                    break
            
            if best_match:
                c['weight'] = best_match['peso']
                excel_remaining.remove(best_match)

        # 6. Check for remaining Excel items and assign to remaining YAML items
        unmapped_yaml = [c for c in alert['criteria'] if c['weight'] == 0]
        if unmapped_yaml and excel_remaining:
             # Distribute remaining Excel weight among unmapped YAML
             rem_weight = sum(i['peso'] for i in excel_remaining)
             w_per = round(rem_weight / len(unmapped_yaml), 3)
             for c in unmapped_yaml: c['weight'] = w_per

        # 7. Normalize to 10.0
        total = sum(c['weight'] for c in alert['criteria'])
        if total > 0:
            factor = 10.0 / total
            for c in alert['criteria']:
                c['weight'] = round(c['weight'] * factor, 2)
            
            new_total = sum(c['weight'] for c in alert['criteria'])
            diff = round(10.0 - new_total, 2)
            if diff != 0:
                highest = max(alert['criteria'], key=lambda x: x['weight'])
                highest['weight'] = round(highest['weight'] + diff, 2)

    with open('backend/db/scoring_rules_final.yaml', 'w', encoding='utf-8') as f:
        yaml.dump(yaml_data, f, allow_unicode=True, sort_keys=False)

if __name__ == "__main__":
    align()
