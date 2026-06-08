import sys
import os

# Adicionar o diretório backend ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
from db.connection import get_connection
from database import init_db

def migrate_criteria():
    init_db()
    conn = get_connection()
    c = conn.cursor()

    # Limpar tabelas antigas para evitar duplicidade no seed
    c.execute("DELETE FROM audit_criteria")
    c.execute("DELETE FROM audit_alerts")
    c.execute("DELETE FROM audit_sectors")

    # 1. Inserir Setores
    sectors = [
        ('bas', 'Base de Sinistros (BAS)', 'Tratativas de ocorrência, roubo e acionamento policial.'),
        ('cadastro', 'Cadastro', 'Auditoria de ligações receptivas de antecedentes.'),
        ('logistica_unilever', 'Logística Unilever', 'Loss Tree, Devolução, Atuação Tratativa.'),
        ('logistica', 'Logística Opentech', 'Controle de temperatura, atrasos, estadias.'),
        ('receptivo', 'Célula de Atendimento', 'Atendimento via WhatsApp / Chatbot.'),
    ]
    for s in sectors:
        c.execute("INSERT INTO audit_sectors (id, label, description) VALUES (%s, %s, %s)", s)

    # 2. Inserir Alertas e Critérios
    c.execute("INSERT INTO audit_alerts (id, sector_id, label, context) VALUES (%s, %s, %s, %s)",
              ('BAS-PRIORITARIO', 'bas', 'Alerta Prioritário', 'Tratativa de suspeita de sinistro ou alerta crítico.'))

    bas_criteria = [
        ('BAS-PRIORITARIO', 'Saudação', 'O operador realizou a saudação?', 0.075),
        ('BAS-PRIORITARIO', 'Nome', 'O operador informou o próprio nome?', 0.075),
        ('BAS-PRIORITARIO', 'Setor', 'O operador informou o setor?', 0.075),
        ('BAS-PRIORITARIO', 'Empresa', 'O operador informou a empresa?', 0.075),
        ('BAS-PRIORITARIO', 'Senha de Segurança', 'O operador confirmou a senha de segurança antes de prosseguir?', 2.0),
        ('BAS-PRIORITARIO', 'Motivo do Contato', 'O operador informou claramente o motivo do contato?', 1.03),
        ('BAS-PRIORITARIO', 'Localização', 'O operador confirmou a localização e a condição do motorista?', 1.7),
        ('BAS-PRIORITARIO', 'Cordialidade', 'Realizou a despedida padrão com cordialidade e entonação adequada?', 0.4),
        ('BAS-PRIORITARIO', 'Registro Sistema', 'O operador registrou corretamente o contato no sistema?', 0.2),
    ]
    for cr in bas_criteria:
        c.execute("INSERT INTO audit_criteria (alert_id, label, description, weight) VALUES (%s, %s, %s, %s)", cr)

    c.execute("INSERT INTO audit_alerts (id, sector_id, label, context) VALUES (%s, %s, %s, %s)",
              ('CADASTRO-ANTECEDENTES', 'cadastro', 'Antecedentes Criminais', 'Consulta receptiva sobre status de cadastro e antecedentes.'))
    cad_criteria = [
        ('CADASTRO-ANTECEDENTES', 'Identificação', 'Saudação, nome e empresa.', 0.3),
        ('CADASTRO-ANTECEDENTES', 'Dados Iniciais', 'Solicitou CPF/Placa para iniciar?', 1.6),
        ('CADASTRO-ANTECEDENTES', 'Informação de Processo', 'Informou sobre inquérito/processo/apontamento?', 1.7),
        ('CADASTRO-ANTECEDENTES', 'Documentação', 'Informou qual documento é necessário?', 1.65),
    ]
    for cr in cad_criteria:
        c.execute("INSERT INTO audit_criteria (alert_id, label, description, weight) VALUES (%s, %s, %s, %s)", cr)

    conn.commit()
    conn.close()
    print("Migração de critérios SQL concluída com sucesso!")

if __name__ == "__main__":
    migrate_criteria()
