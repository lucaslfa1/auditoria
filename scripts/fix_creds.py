import sys
import os
sys.path.append(os.path.abspath('backend'))
import database


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} nao configurado.")
    return value


def update_creds():
    huawei_ak = _required_env("HUAWEI_AK")
    huawei_sk = _required_env("HUAWEI_SK")
    huawei_app_key = _required_env("HUAWEI_APP_KEY")

    conn = database.get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE configuracoes SET valor = %s WHERE chave = 'huawei_ak'", (huawei_ak,))
    cur.execute("UPDATE configuracoes SET valor = %s WHERE chave = 'huawei_sk'", (huawei_sk,))
    cur.execute("UPDATE configuracoes SET valor = %s WHERE chave = 'huawei_app_key'", (huawei_app_key,))
    conn.commit()
    print("Credenciais atualizadas com sucesso!")
    cur.close()
    conn.close()

if __name__ == "__main__":
    update_creds()
