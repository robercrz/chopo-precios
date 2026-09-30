import sqlite3
import json
import re
import openpyxl

def test_bundles():
    conn = sqlite3.connect('db/chopo_prices.db')
    cur = conn.cursor()
    
    # Get all Chopo packages and checkups
    cur.execute("""
        SELECT study_name, price, price_original
        FROM latest_prices
        WHERE study_name LIKE '%CHECK%' 
           OR study_name LIKE '%PERFIL%' 
           OR study_name LIKE '%PAQUETE%' 
           OR study_name LIKE '%QUIMICA%'
        ORDER BY study_name
    """)
    chopo_bundles = cur.fetchall()
    
    # Also get bundle details if available
    cur.execute("SELECT study_name, included_text, bullets FROM bundle_details")
    chopo_details = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
    conn.close()

    print(f"Chopo packages/checkups found: {len(chopo_bundles)}")
    for b in chopo_bundles[:15]:
        det = chopo_details.get(b[0], ('', '[]'))
        print(f"- {b[0]} | Web: ${b[1]} | Lista: ${b[2]}")

if __name__ == '__main__':
    test_bundles()
