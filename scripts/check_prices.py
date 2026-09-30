import sqlite3

conn = sqlite3.connect('db/chopo_prices.db')
cur = conn.cursor()
cur.execute('SELECT study_name, price, price_original FROM latest_prices WHERE study_name LIKE ?', ('%MICA%',))
for r in cur.fetchall():
    print(r)
conn.close()
