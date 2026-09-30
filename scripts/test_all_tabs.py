# scripts/test_all_tabs.py
"""
Script de auditoría exhaustiva que prueba la ejecución limpia de todas las pestañas
del dashboard con datos reales de la base de datos.
"""

import sys
import io
from pathlib import Path

# Configurar stdout en utf-8 para compatibilidad con Windows y emojis
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.database import init_db, get_latest_prices, get_all_labs, get_price_changes, get_scrape_log
import dashboard.app as app
from dashboard.lcm_comparator import render_lcm_comparator_tab
from dashboard.lcm_smart_cotizador import render_smart_cotizador_tab

def test_tabs():
    print("--- INICIANDO AUDITORÍA INTEGRAL DE PESTAÑAS ---")
    init_db()
    prices = get_latest_prices() or []
    labs = get_all_labs() or []
    changes = get_price_changes(30) or []
    scrape_log = get_scrape_log() or []

    print(f"Datos base cargados: {len(prices)} precios, {len(labs)} labs, {len(changes)} cambios.")

    filters = {
        "search": "",
        "categories": [],
        "price_min": 0,
        "price_max": 25000,
        "only_discount": False,
        "only_favorites": False,
    }

    tabs_to_test = [
        ("⭐ Favoritos", lambda: app.render_favorites_tab(prices)),
        ("🩺 Cotizador Inteligente LCM", lambda: render_smart_cotizador_tab()),
        ("⚖️ Comparativa LCM vs Chopo", lambda: render_lcm_comparator_tab(prices)),
        ("📋 Catálogo", lambda: app.render_catalog_tab(prices, filters)),
        ("🏷️ Descuentos & Promos", lambda: app.render_discounts_tab(prices)),
        ("💼 Paquetes & Estrategia", lambda: app.render_quotation_tab(prices)),
        ("📊 Análisis", lambda: app.render_analysis_tab(prices, filters)),
        ("📈 Historial", lambda: app.render_history_tab(labs)),
        ("🔔 Cambios", lambda: app.render_changes_tab(changes)),
        ("⚙️ Scheduler & Config", lambda: app.render_scheduler_tab()),
        ("🗂️ Logs", lambda: app.render_logs_tab(scrape_log)),
    ]

    passed = 0
    failed = 0

    for name, func in tabs_to_test:
        print(f"Probando {name}...")
        try:
            func()
            print(f"  ✅ {name}: OK")
            passed += 1
        except Exception as e:
            print(f"  ❌ {name}: FALLÓ con error: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n--- RESULTADO DE LA AUDITORÍA: {passed} PASADAS, {failed} FALLADAS ---")
    if failed == 0:
        print("🎉 ¡TODAS LAS PESTAÑAS FUNCIONAN DE MANERA IMPECABLE!")

if __name__ == "__main__":
    test_tabs()
