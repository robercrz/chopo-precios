import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding='utf-8')
from scraper.lcm_manager import load_promotions, get_consolidated_matches, detect_columns
import pandas as pd

promos = load_promotions()
print(f"Promotions loaded: {len(promos)}")
for p in promos[:4]:
    print(f"- {p['name']} :: {p['status_label']} :: Promo: ${p['price_promo']}")

data = get_consolidated_matches()
print('Consolidated matches count:', len(data['matches']))

df_test = pd.DataFrame({
    'Clave_Estudio': [1, 2],
    'Nombre del Examen': ['Glucosa', 'Urea'],
    'Precio Publico Con IVA': [120.0, 150.0]
})
print('Detected cols:', detect_columns(df_test))
