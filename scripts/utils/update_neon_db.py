import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), "backend"))
import database

def main():
    database.init_db()
    print("Atualizando Neon DB com as credenciais corretas...")
    database.update_config("huawei_proxy_ip", "34.171.63.68")
    database.update_config("huawei_proxy_url", "https://opentech.teledatabrasil.com.br/aicc/auth/c2Authorization.php")
    
    print("Validando...")
    print(f"huawei_proxy_ip: {database.get_config_value('huawei_proxy_ip')}")
    print(f"huawei_proxy_url: {database.get_config_value('huawei_proxy_url')}")

if __name__ == '__main__':
    main()