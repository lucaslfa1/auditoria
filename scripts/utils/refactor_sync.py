import re

with open('backend/core/huawei_sync.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Substituir imports
if 'from core.huawei_discovery import HuaweiDiscoveryService' not in content:
    content = content.replace('from core.huawei_obs_client import HuaweiOBSClient', 
                              'from core.huawei_obs_client import HuaweiOBSClient\nfrom core.huawei_discovery import HuaweiDiscoveryService')

# Remover _coerce_huawei_time_ms
content = re.sub(r'def _coerce_huawei_time_ms\(.*?\)(?:.|\n)*?return None\n', '', content)

# Remover _window_date_strings
content = re.sub(r'def _window_date_strings\(.*?\)(?:.|\n)*?return dates\n', '', content)

# Remover _query_time_windows
content = re.sub(r'def _query_time_windows\(.*?\)(?:.|\n)*?return windows\n', '', content)

# Remover _manifest_row_to_interacao
content = re.sub(r'def _manifest_row_to_interacao\(.*?\)(?:.|\n)*?return \{.*?"source": "obs_contact_record",\n    \}\n', '', content)

# Remover _merge_interacoes
content = re.sub(r'def _merge_interacoes\(.*?\)(?:.|\n)*?return list\(merged\.values\(\)\) \+ sem_id\n', '', content)

# Remover _buscar_chamadas_globais
content = re.sub(r'async def _buscar_chamadas_globais\(.*?\)(?:.|\n)*?return list\(chamadas_por_id\.values\(\)\) \+ chamadas_sem_id\n', '', content)

# Remover _buscar_chamadas_obs_manifest
content = re.sub(r'async def _buscar_chamadas_obs_manifest\(.*?\)(?:.|\n)*?return interacoes\n', '', content)

# Atualizar chamadas em _call_duration_is_known e sort_key
content = content.replace('_coerce_huawei_time_ms(', 'HuaweiDiscoveryService._coerce_huawei_time_ms(')

# Atualizar chamadas em _buscar_chamadas_por_regra
content = content.replace('call_key = _resolve_call_key(chamada)', 'call_key = HuaweiDiscoveryService.resolve_call_key(chamada)')

# Atualizar orquestrador
old_orquestrador = '''        # 2. Descobrir chamadas globalmente. A Huawei ignora/omite agentId no
        # querycalls, entao a coleta por operador pode retornar zero ou repetir
        # as mesmas linhas. O manifesto OBS entra como fallback independente da
        # VDN e costuma carregar workNo/countName/caller/called/recordId.
        vdn_interacoes = await _buscar_chamadas_globais(client, begin_ms, end_ms)
        obs_manifest_interacoes = await _buscar_chamadas_obs_manifest(obs_client, begin_ms, end_ms)
        for chamada in vdn_interacoes:
            chamada_call_id = _resolve_call_key(chamada)
            if chamada_call_id:
                call_ids_vdn_unicos.add(chamada_call_id)
        for chamada in obs_manifest_interacoes:
            chamada_call_id = _resolve_call_key(chamada)
            if chamada_call_id:
                call_ids_manifest_unicos.add(chamada_call_id)
        interacoes = _merge_interacoes(vdn_interacoes, obs_manifest_interacoes)
        for chamada in interacoes:
            chamada_call_id = _resolve_call_key(chamada)
            if chamada_call_id:
                call_ids_descobertos_unicos.add(chamada_call_id)'''

new_orquestrador = '''        # 2. Descobrir chamadas globalmente. A Huawei ignora/omite agentId no
        # querycalls, entao a coleta por operador pode retornar zero ou repetir
        # as mesmas linhas. O manifesto OBS entra como fallback independente da
        # VDN e costuma carregar workNo/countName/caller/called/recordId.
        interacoes, call_ids_vdn_unicos, call_ids_manifest_unicos, call_ids_descobertos_unicos = await HuaweiDiscoveryService.fetch_all(
            client, obs_client, begin_ms, end_ms
        )'''
content = content.replace(old_orquestrador, new_orquestrador)

# Remove empty lines
content = re.sub(r'\n{3,}', '\n\n', content)

with open('backend/core/huawei_sync.py', 'w', encoding='utf-8') as f:
    f.write(content)
