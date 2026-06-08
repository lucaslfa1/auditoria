import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import db.database as database


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} nao configurado no ambiente.")
    return value


def insert_obs_creds():
    ak = _required_env("HUAWEI_OBS_AK")
    sk = _required_env("HUAWEI_OBS_SK")
    bucket = os.getenv("HUAWEI_OBS_BUCKET", "obs-nstech-opentech").strip()

    conn = database.get_connection()
    c = conn.cursor()

    values = [
        ("huawei_obs_ak", ak),
        ("huawei_obs_sk", sk),
        ("huawei_obs_bucket", bucket),
    ]

    for chave, valor in values:
        c.execute(
            """
            INSERT INTO configuracoes(chave, valor)
            VALUES (%s, %s)
            ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor
            """,
            (chave, valor),
        )

    conn.commit()
    print("Credenciais OBS inseridas na tabela configuracoes com sucesso.")

if __name__ == "__main__":
    insert_obs_creds()
