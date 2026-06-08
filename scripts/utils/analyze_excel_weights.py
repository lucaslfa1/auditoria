
import json

def analyze_excel_json():
    with open('criterios_pesos_extraidos.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    for cat, items in data.items():
        total_peso = sum(item['peso'] for item in items)
        total_deflator = sum(item['deflator'] for item in items)
        print(f"Category: {cat}")
        print(f"  Total Peso: {total_peso}")
        print(f"  Total Deflator: {total_deflator}")
        print(f"  Count: {len(items)}")
        
        # Check if it's a "GRS & BAS" or similar
        if "UTI" in cat or "GRS" in cat or "PRIORIT" in cat:
             # Just show first few
             for i, item in enumerate(items[:10]):
                 print(f"    {item['pergunta']}: {item['peso']} ({item['deflator']})")

if __name__ == "__main__":
    analyze_excel_json()
