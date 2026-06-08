import sys
sys.path.append('backend')
from dotenv import load_dotenv
load_dotenv('.env', override=True)

import logging
logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)

from database import init_db

print("Calling init_db...")
init_db()
print("Success!")
