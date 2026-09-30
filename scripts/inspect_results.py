import sys
sys.stdout.reconfigure(encoding='utf-8')
import json

with open('data/lcm/lcm_chopo_matches.json', encoding='utf-8') as f:
    data = json.load(f)

matches = data['matches']
exact = [m for m in matches if m['match_type'] == 'EXACT']
high = [m for m in matches if m['match_type'] == 'HIGH']
med = [m for m in matches if m['match_type'] == 'MEDIUM']

print("=== EXACT MATCH SAMPLES (174 total) ===")
for m in exact[:8]:
    print(f"[{m['lcm_code']}] {m['lcm_name']} -> Chopo: {m['chopo_name']} | LCM: ${m['lcm_price']} vs Chopo Web: ${m['chopo_price_web']} (Diff: ${m['diff_mxn']})")

print("\n=== HIGH CONFIDENCE MATCH SAMPLES (230 total) ===")
for m in high[:8]:
    print(f"[{m['lcm_code']}] {m['lcm_name']} -> Chopo: {m['chopo_name']} ({m['confidence']}%) | LCM: ${m['lcm_price']} vs Chopo Web: ${m['chopo_price_web']} (Diff: ${m['diff_mxn']})")

print("\n=== TOP ESTUDIOS DONDE LCM ES MAS BARATO QUE CHOPO ===")
lcm_cheap = sorted([m for m in matches if m['diff_mxn'] is not None and m['diff_mxn'] < 0 and m['confidence'] >= 85], key=lambda x: x['diff_mxn'])
for m in lcm_cheap[:12]:
    print(f"- {m['lcm_name']}: LCM ${m['lcm_price']} vs Chopo Web ${m['chopo_price_web']} (Ahorro cliente en LCM: ${abs(m['diff_mxn']):,.2f} / {abs(m['diff_pct'])}%)")

print("\n=== TOP ESTUDIOS DONDE CHOPO ES MAS BARATO QUE LCM ===")
chopo_cheap = sorted([m for m in matches if m['diff_mxn'] is not None and m['diff_mxn'] > 50 and m['confidence'] >= 85], key=lambda x: -x['diff_mxn'])
for m in chopo_cheap[:12]:
    print(f"- {m['lcm_name']}: LCM ${m['lcm_price']} vs Chopo Web ${m['chopo_price_web']} (Chopo es ${m['diff_mxn']:,.2f} más barato / +{m['diff_pct']}%)")

print("\n=== PAQUETES / CHECK-UPS LCM (OCTUBRE) ===")
for pkg in data['packages']:
    print(f"* {pkg['package_name']} ({pkg['category']}) -> Promo: {pkg['price_promo']} | Público: {pkg['price_public']} | Inc: {pkg['included_tests'][:60]}")
