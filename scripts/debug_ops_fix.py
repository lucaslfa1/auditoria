
import database
import json

def check_ops():
    print("--- Verificando Mondelez ---")
    mondelez = database.get_colaboradores_lookup(sector_id="mondelez")
    print(f"Total Mondelez: {len(mondelez)}")
    for op in mondelez[:3]:
        print(f" - {op['name']}")

    print("\n--- Verificando Unilever ---")
    unilever = database.get_colaboradores_lookup(sector_id="logistica_unilever")
    print(f"Total Unilever: {len(unilever)}")
    for op in unilever[:3]:
        print(f" - {op['name']}")

if __name__ == '__main__':
    check_ops()
