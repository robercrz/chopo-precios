import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding='utf-8')
import json

with open('data/lcm/lcm_chopo_matches.json', encoding='utf-8') as f:
    data = json.load(f)

adic = data.get('adicionales', [])
pkgs = data.get('packages', [])

print("--- Comparativa Adicional vs Promo en LCM ---")
for a in adic:
    name = a['name']
    p_reg = a['price_2025']
    p_bundle = a['price_bundle']
    promo_matches = [p for p in pkgs if name.lower() in p.get('package_name', '').lower() or name.lower() in p.get('included_tests', '').lower()]
    for pm in promo_matches:
        p_promo = pm.get('price_promo')
        if p_promo is not None and isinstance(p_promo, (int, float)):
            best = min(p_bundle, p_promo)
            reason = "Promo gana" if p_promo < p_bundle else ("Adicional gana" if p_bundle < p_promo else "Mismo precio")
            print(f"- {name}: Lista ${p_reg} | Adicional ${p_bundle} | Promo ${p_promo} -> MEJOR: ${best} ({reason})")
