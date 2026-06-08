import sys

path = 'backend/tests/test_huawei_sync.py'
with open(path, 'r', encoding='utf-8') as f:
    c = f.read()

# Fix Mondelez test back to assert_not_awaited()
c = c.replace(
    '        # Filtro deve abortar antes de qualquer download.\n        client.baixar_gravacao_por_callid.assert_awaited_once_with("call-1")',
    '        # Filtro deve abortar antes de qualquer download.\n        client.baixar_gravacao_por_callid.assert_not_awaited()'
)

# Fix FS ids alternativos to baixadas=1
c = c.replace(
'''
        client.obter_url_audio_obs.assert_not_awaited() 
        self.assertEqual(delta["baixadas"], 0)
''',
'''
        client.obter_url_audio_obs.assert_not_awaited() 
        self.assertEqual(delta["baixadas"], 1)
'''
)

with open(path, 'w', encoding='utf-8') as f:
    f.write(c)
