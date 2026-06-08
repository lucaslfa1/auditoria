import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "backend"))
import database

def count():
    print(database.get_operator_audit_count_for_month_safe("Caio das Virgens Melo"))

count()
