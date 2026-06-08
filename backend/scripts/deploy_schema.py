import sys
from dotenv import load_dotenv

load_dotenv('../.env', override=True)
load_dotenv('.env', override=True)

from db.database import init_db

print("Building tables in the database...")
init_db()
print("Success!")
