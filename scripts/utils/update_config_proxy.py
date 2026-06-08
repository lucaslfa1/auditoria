import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

import database

def main():
    try:
        # Atualiza a configuração HUAWEI_PROXY_IP para o IP da VM em Iowa
        database.update_config("huawei_proxy_ip", "34.171.63.68")
        print("Configuração huawei_proxy_ip atualizada para 34.171.63.68 com sucesso.")
        
    except Exception as e:
        print(f"Erro ao atualizar configuração: {e}")

if __name__ == "__main__":
    main()
