# ============================================================
# main.py
# Punto de entrada principal del proyecto
# ============================================================
# -*- coding: utf-8 -*-

"""
Chopo Price Intelligence
========================
Sistema de scraping y analisis de precios de laboratorio.

Uso:
    python main.py scrape          # Ejecutar scrape inmediato
    python main.py dashboard       # Lanzar dashboard Streamlit
    python main.py scheduler       # Iniciar scheduler diario
    python main.py init            # Inicializar base de datos
    python main.py export          # Exportar datos a Excel
"""

import sys
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

# Forzar encoding UTF-8 en stdout para compatibilidad Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def cmd_scrape():
    """Ejecuta un scrape inmediato de todos los laboratorios."""
    from db.database import init_db, save_scrape_results, upsert_lab
    from scraper.chopo_scraper import run_scrape_sync, LABS_CONFIG

    print("[*] Chopo Price Intelligence - Scrape Manual")
    print("=" * 50)

    init_db()

    all_results = []
    for lab_key, config in LABS_CONFIG.items():
        print(f"\n[+] Scrapeando: {config['name']} ({config['city']}, {config['state']})")
        print(f"    URL: {config['url']}")

        upsert_lab(
            lab_key=lab_key,
            lab_name=config["name"],
            city=config["city"],
            state=config["state"],
            url=config["url"],
        )

        try:
            results = run_scrape_sync(lab_key=lab_key, headless=True)
            all_results.extend(results)
            print(f"    OK: {len(results)} estudios encontrados")

            if results:
                print(f"\n    Muestra de estudios:")
                for r in results[:5]:
                    name = r.get("study_name", "N/D")
                    price = r.get("price_raw", "N/D")
                    print(f"      - {name}: {price}")
                if len(results) > 5:
                    print(f"      ... y {len(results) - 5} mas")

        except Exception as e:
            print(f"    ERROR: {e}")

    if all_results:
        saved = save_scrape_results(all_results)
        print(f"\n[OK] Total: {saved} registros guardados en la base de datos")
    else:
        print("\n[!] No se encontraron datos. El sitio puede requerir ajustes de selectores.")
        print("    Intenta correr con headless=False para ver el browser:")
        print("    Edita chopo_scraper.py y cambia headless=True a headless=False")

    return len(all_results)


def cmd_dashboard():
    """Lanza el dashboard Streamlit."""
    app_path = BASE_DIR / "dashboard" / "app.py"
    print("[*] Lanzando dashboard en http://localhost:8501")
    print("    Presiona Ctrl+C para detener")
    subprocess.run([
        sys.executable, "-m", "streamlit", "run",
        str(app_path),
        "--server.port", "8501",
        "--server.headless", "false",
        "--browser.gatherUsageStats", "false",
    ])


def cmd_scheduler():
    """Inicia el servicio del scheduler con la configuracion guardada."""
    from scraper.scheduler_service import main as run_scheduler_service
    print("[*] Iniciando scheduler automatico con configuracion guardada...")
    print("    Presiona Ctrl+C para detener")
    run_scheduler_service()


def cmd_init():
    """Inicializa la base de datos."""
    from db.database import init_db, DB_PATH
    init_db()
    print(f"[OK] Base de datos inicializada en: {DB_PATH}")


def cmd_export():
    """Exporta los datos actuales a Excel."""
    from db.database import get_latest_prices, get_price_changes
    from scraper.exporter import export_to_excel

    print("[*] Exportando datos a Excel...")
    prices = get_latest_prices()
    changes = get_price_changes(days=30)

    if not prices:
        print("[!] No hay datos para exportar. Ejecuta primero: python main.py scrape")
        return

    filepath = export_to_excel(prices, changes_data=changes)
    print(f"[OK] Excel exportado: {filepath}")


def print_usage():
    print(__doc__)


COMMANDS = {
    "scrape": cmd_scrape,
    "dashboard": cmd_dashboard,
    "scheduler": cmd_scheduler,
    "init": cmd_init,
    "export": cmd_export,
}


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print_usage()
        print("\nComandos disponibles:")
        for cmd in COMMANDS:
            print(f"  python main.py {cmd}")
        sys.exit(1)

    command = sys.argv[1]
    COMMANDS[command]()
