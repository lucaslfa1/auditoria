import db.database as database
import json

conn = database.get_connection()
c = conn.cursor()
c.execute("SELECT metadata_json FROM fila_revisao_classificacao ORDER BY id DESC LIMIT 5")
rows = c.fetchall()
for r in rows:
    if r['metadata_json']:
        meta = json.loads(r['metadata_json'])
        print("huawei_begin_time:", meta.get('huawei_begin_time'), "type:", type(meta.get('huawei_begin_time')))
conn.close()