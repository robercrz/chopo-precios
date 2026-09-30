import sqlite3
import json

conn = sqlite3.connect('db/chopo_prices.db')
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM studies')
print('Total studies in Chopo DB:', cur.fetchone()[0])

cur.execute("PRAGMA table_info(studies)")
print('Columns of studies:', [col[1] for col in cur.fetchall()])

cur.execute("SELECT * FROM studies LIMIT 2")
print('Sample row:', cur.fetchone())

cur.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='bundle_details'")
has_bundles = cur.fetchone()[0]
if has_bundles > 0:
    cur.execute('SELECT COUNT(*) FROM bundle_details')
    print('Total bundle_details:', cur.fetchone()[0])
    cur.execute('SELECT bundle_name, study_count, included_studies FROM bundle_details LIMIT 5')
    for b in cur.fetchall():
        print('Bundle:', b[0], 'Count:', b[1], 'Studies:', str(b[2])[:80])

conn.close()
