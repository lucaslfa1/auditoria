import sys
sys.path.append('backend')
from db.connection import create_connection
from repositories.admin_criteria import get_export_format
conn = create_connection()
data = get_export_format(lambda: conn)
for sector in data['sectors']:
    print(f"{sector['id']}: {len(sector['alerts'])} alerts")
conn.close()
