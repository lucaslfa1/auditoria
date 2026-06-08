
import yaml

def finalize_yaml():
    with open('backend/db/scoring_rules.yaml', 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    
    # 4.1.1 UTI-PRIORITARIO-MOT
    mot_pri = next(a for a in data['alerts'] if a['id'] == 'UTI-PRIORITARIO-MOT')
    weights_mot_pri = {
        "Saudação?": 0.36, "Nome?": 0.37, "Setor/Empresa?": 0.37,
        "Confirmou a senha de segurança?": 1.20,
        "Informou o motivo do contato?": 1.10,
        "Confirmou localização e condição do motorista?": 0.80,
        "Identificou o motivo do alerta?": 1.70,
        "Solicitou vídeo do veículo se necessário?": 0.80,
        "Realizou a despedida padrão com cordialidade?": 1.10,
        "Entonação e cordialidade adequadas?": 1.10,
        "Registrou corretamente o contato no sistema?": 1.10,
        "Utilizou a função mudo corretamente?": 0.0,
        "Evitou silêncios prolongados (>45s)?": 0.0,
        "Finalizou a ligação sem reter a linha (10s)?" : 0.0,
    }
    for c in mot_pri['criteria']:
        if c['label'] in weights_mot_pri: c['weight'] = weights_mot_pri[c['label']]

    # 4.1.2 UTI-PRIORITARIO-CLI
    cli_pri = next(a for a in data['alerts'] if a['id'] == 'UTI-PRIORITARIO-CLI')
    weights_cli_pri = {
        "Saudação?": 0.36, "Nome?": 0.37, "Setor/Empresa?": 0.37,
        "Confirmou com whom está falando?": 1.10,
        "Informou o motivo do contato?": 1.10,
        "Enfatizou suspeita de sinistro?": 1.20,
        "Informou ações adotadas?": 1.70,
        "Informou local do alerta?": 0.80,
        "Confirmou contatos do condutor?": 0.80,
        "Realizou a despedida padrão com cordialidade?": 1.10,
        "Entonação e cordialidade adequadas?": 1.10,
        "Registrou corretamente o contato no sistema?": 0.0, # Excel doesn't have it for CLI
    }
    # Fix typo in my previous check
    for c in cli_pri['criteria']:
        if c['label'] in weights_cli_pri: c['weight'] = weights_cli_pri[c['label']]

    # 4.1.3 UTI-POSICAO-MOT (Excel: all 1.0)
    mot_pos = next(a for a in data['alerts'] if a['id'] == 'UTI-POSICAO-MOT')
    weights_mot_pos = {
        "Saudação?": 0.33, "Nome?": 0.33, "Setor/Empresa?": 0.34,
        "Confirmou a senha de segurança?": 1.00,
        "Informou o motivo do contato?": 1.00,
        "Confirmou localização atual?": 1.00,
        "Orientou forçar posicionamento?": 1.00,
        "Identificou motivo da perda de sinal?": 1.00,
        "Informou riscos operacionais/seguro?": 1.00,
        "Realizou a despedida padrão com cordialidade?": 1.00,
        "Entonação e cordialidade adequadas?": 1.00,
        "Registrou corretamente o contato no sistema?": 1.00,
    }
    for c in mot_pos['criteria']:
        if c['label'] in weights_mot_pos: c['weight'] = weights_mot_pos[c['label']]

    # Ensure all alerts sum to 10.0
    for alert in data['alerts']:
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

    with open('backend/db/scoring_rules.yaml', 'w', encoding='utf-8') as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False)

if __name__ == "__main__":
    finalize_yaml()
