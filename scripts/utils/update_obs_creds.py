import os
import psycopg2

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
HUAWEI_OBS_AK = os.getenv("HUAWEI_OBS_AK", "").strip()
HUAWEI_OBS_SK = os.getenv("HUAWEI_OBS_SK", "").strip()

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL nao configurado.")
if not HUAWEI_OBS_AK or not HUAWEI_OBS_SK:
    raise RuntimeError("HUAWEI_OBS_AK/HUAWEI_OBS_SK nao configurados.")

try:
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("UPDATE configuracoes SET valor = %s WHERE chave = 'huawei_obs_ak'", (HUAWEI_OBS_AK,))
    cur.execute("UPDATE configuracoes SET valor = %s WHERE chave = 'huawei_obs_sk'", (HUAWEI_OBS_SK,))
    conn.commit()
    print("Credentials updated successfully!")
    conn.close()
except Exception as e:
    print(f"Erro: {e}")
