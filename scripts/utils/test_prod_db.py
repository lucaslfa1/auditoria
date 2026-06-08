import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), "backend"))
import database

def main():
    database.init_db()
    print("Prod DB Configs:")
    print(f"huawei_proxy_ip: {database.get_config_value('huawei_proxy_ip')}")
    print(f"huawei_ak: {database.get_config_value('huawei_ak')}")
    print(f"huawei_sk: {database.get_config_value('huawei_sk')}")

if __name__ == '__main__':
    main()