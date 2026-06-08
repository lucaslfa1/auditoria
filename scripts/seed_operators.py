"""
Script para popular o banco de dados de operadores a partir dos nomes de arquivos
da pasta Ligações/. Extrai nomes de operadores, agent_ids e setores automaticamente.

Uso: python scripts/seed_operators.py
"""

import os
import sys
import re

# Adicionar o diretório backend ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
os.chdir(os.path.join(os.path.dirname(__file__), '..', 'backend'))

from database import init_db, upsert_operator, get_all_operators

# Mapeamento de pastas para setores
FOLDER_TO_SECTOR = {
    "LOGÍSTICA": "logistica",
    "CADASTRO": "cadastro",
    "UNILEVER": "logistica_unilever",
    "MONDELEZ": "mondelez",
    "RAST.-UTI-DIST-BAS": "bas",
}


def extract_operator_from_filename(filename: str, folder_path: str) -> dict:
    """
    Extrai informações do operador a partir do nome do arquivo.
    
    Padrões conhecidos:
    1. ALERTA-TIPO-DATA_Nome_Sobrenome_Setor_Voz.wav
       Ex: ATRASO-MOTORISTA-20251230173926115_Danilo_Alves_Logistica_Voz.wav
    
    2. ALERTA-TIPO-agent-XXXX-DATA-node-ID.wav
       Ex: PARADA-MOT-agent-4218-4_10_2025_10_41_55-node01-1759585314-17302.wav
    
    3. ALERTA-TIPO-DATA_HORA_ID_TELEFONE.mp3
       Ex: PARADA-MOTORISTA-20-08-2025_11-11-04_112790_21995342893.mp3
    """
    result = {
        "name": None,
        "agent_id": None,
        "sector": None,
    }
    
    # Mapeamento de sufixo do filename para setor (PRIORIDADE 1)
    FILENAME_SECTOR_MAP = {
        "_Logistica_": "logistica",
        "_Distribuição_": "distribuicao",
        "_Distribuicao_": "distribuicao",
        "_Fenix_": "bas",
        "_G2L_": "logistica",
        "_Taborda_": "logistica",
        "_Cadastro_": "cadastro",
        "_UTI_": "uti",
        "_Transferencia_": "transferencia",
    }
    
    # PRIORIDADE 1: Detectar setor pelo nome do arquivo (mais preciso)
    for suffix, sector_id in FILENAME_SECTOR_MAP.items():
        if suffix in filename:
            result["sector"] = sector_id
            break
    
    # PRIORIDADE 2: Detectar setor pela pasta (fallback)
    if not result["sector"]:
        for folder_key, sector_id in FOLDER_TO_SECTOR.items():
            if folder_key in folder_path:
                result["sector"] = sector_id
                break
    
    # Padrão 1: Nome no arquivo (formato DATA_Nome_Sobrenome_Setor_Voz)
    # Ex: 20251230173926115_Danilo_Alves_Logistica_Voz.wav
    # Ex: 20260108100935776_Jaqueline_Frazao_de_Souza_Logistica_Voz.wav
    name_match = re.search(r'\d{10,}_([A-Z][a-záàãéêíóôúç]+(?:_[A-Za-záàãéêíóôúç]+)+)_Voz', filename)
    if name_match:
        raw_name = name_match.group(1)
        # Remover sufixos de setor do nome
        for suffix in ["_Logistica", "_Distribuição", "_Distribuicao", "_Fenix", "_G2L", "_Taborda"]:
            raw_name = raw_name.replace(suffix, "")
        result["name"] = raw_name.replace("_", " ").strip()
    
    # Padrão 2: Agent ID
    agent_match = re.search(r'agent-(\d+)', filename)
    if agent_match:
        result["agent_id"] = f"agent-{agent_match.group(1)}"
    
    return result


def scan_ligacoes_folder(base_path: str) -> list[dict]:
    """Escaneia recursivamente a pasta Ligações e extrai dados dos operadores."""
    operators_found = []
    
    for root, dirs, files in os.walk(base_path):
        for file in files:
            if not file.lower().endswith(('.wav', '.mp3', '.ogg', '.m4a')):
                continue
            
            info = extract_operator_from_filename(file, root)
            if info["name"] or info["agent_id"]:
                info["filename"] = file
                info["folder"] = root
                operators_found.append(info)
    
    return operators_found


def main():
    # Inicializar banco de dados (cria tabela operators se não existir)
    init_db()
    
    # Caminho da pasta Ligações
    ligacoes_path = os.path.join(os.path.dirname(__file__), '..', 'Ligações')
    ligacoes_path = os.path.abspath(ligacoes_path)
    
    if not os.path.exists(ligacoes_path):
        print(f"Pasta não encontrada: {ligacoes_path}")
        return
    
    print(f"Escaneando: {ligacoes_path}")
    entries = scan_ligacoes_folder(ligacoes_path)
    
    print(f"\nEncontrados {len(entries)} arquivos de áudio")
    
    # Separar por tipo
    with_name = [e for e in entries if e["name"]]
    with_agent = [e for e in entries if e["agent_id"] and not e["name"]]
    
    print(f"  - Com nome do operador: {len(with_name)}")
    print(f"  - Apenas com agent_id: {len(with_agent)}")
    
    # Popular o banco com operadores identificados por nome
    names_inserted = set()
    for entry in with_name:
        name = entry["name"]
        if name not in names_inserted:
            upsert_operator(
                name=name,
                agent_id=entry.get("agent_id"),
                sector=entry.get("sector"),
                source="filename_seed",
                confidence=0.9
            )
            names_inserted.add(name)
            print(f"  ✅ {name} (setor: {entry.get('sector', '?')}, agent: {entry.get('agent_id', 'N/A')})")
        else:
            # Mesmo operador visto novamente, atualizar
            upsert_operator(
                name=name,
                agent_id=entry.get("agent_id"),
                sector=entry.get("sector"),
                source="filename_seed",
                confidence=0.9
            )
    
    # Mostrar resumo final
    all_ops = get_all_operators()
    print(f"\n{'='*60}")
    print(f"BANCO DE OPERADORES: {len(all_ops)} operadores registrados")
    print(f"{'='*60}")
    for op in all_ops:
        sectors = ", ".join(op["sectors"]) if op["sectors"] else "?"
        agents = ", ".join(op["agent_ids"]) if op["agent_ids"] else "N/A"
        print(f"  {op['name']:30s} | setores: {sectors:20s} | agents: {agents} | visto {op['occurrences']}x")


if __name__ == "__main__":
    main()
