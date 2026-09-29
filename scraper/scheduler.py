# ============================================================
# scraper/scheduler.py
# Actualización automática diaria con APScheduler
# ============================================================

import sys
from pathlib import Path

# Agregar el directorio raíz al path
sys.path.insert(0, str(Path(__file__).parent.parent))

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime

from loguru import logger
from scraper.chopo_scraper import run_scrape_sync, LABS_CONFIG
from db.database import init_db, save_scrape_results, upsert_lab

# Configurar logs
logger.add(
    Path(__file__).parent.parent / "logs" / "scheduler_{time}.log",
    rotation="1 week",
    retention="1 month",
    level="INFO",
)


def scrape_job(lab_key: str = "chopo_yucatan"):
    """
    Job principal que ejecuta el scrape y guarda en BD.
    Diseñado para ser llamado por APScheduler.
    """
    logger.info(f"[SCHEDULER] Iniciando job de scrape: {lab_key} - {datetime.now().isoformat()}")

    try:
        # Inicializar BD si no existe
        init_db()

        # Registrar el lab
        config = LABS_CONFIG.get(lab_key, {})
        if config:
            upsert_lab(
                lab_key=lab_key,
                lab_name=config["name"],
                city=config["city"],
                state=config["state"],
                url=config["url"],
            )

        # Ejecutar el scrape
        results = run_scrape_sync(lab_key=lab_key, headless=True)

        if results:
            # Guardar en BD
            saved = save_scrape_results(results)
            logger.success(
                f"[SCHEDULER] ✅ Job completado: {saved} estudios guardados para {lab_key}"
            )
        else:
            logger.warning(f"[SCHEDULER] ⚠️ El scrape no retornó resultados para {lab_key}")

    except Exception as e:
        logger.error(f"[SCHEDULER] ❌ Error en job de scrape ({lab_key}): {e}")


def scrape_all_labs():
    """Scrape todos los laboratorios configurados."""
    for lab_key in LABS_CONFIG.keys():
        scrape_job(lab_key=lab_key)


def start_daily_scheduler(hour: int = 6, minute: int = 0):
    """
    Inicia el scheduler en modo blocking (proceso dedicado).
    Por defecto ejecuta a las 6:00 AM diariamente.

    Args:
        hour: Hora de ejecución (formato 24h)
        minute: Minuto de ejecución
    """
    scheduler = BlockingScheduler(timezone="America/Merida")

    # Job diario para todos los laboratorios
    scheduler.add_job(
        scrape_all_labs,
        trigger=CronTrigger(hour=hour, minute=minute),
        id="daily_scrape",
        name="Scrape diario de todos los laboratorios",
        replace_existing=True,
    )

    # Job de prueba: ejecutar inmediatamente al arrancar
    scheduler.add_job(
        scrape_all_labs,
        trigger="date",
        run_date=datetime.now(),
        id="initial_scrape",
        name="Scrape inicial al arrancar",
    )

    logger.info(f"Scheduler iniciado. Próxima ejecución diaria: {hour:02d}:{minute:02d} (Hora Mérida)")
    logger.info("Presiona Ctrl+C para detener")

    try:
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("Scheduler detenido por el usuario")
        scheduler.shutdown()


def get_background_scheduler() -> BackgroundScheduler:
    """
    Retorna un scheduler en background para usar dentro de la app Streamlit.
    """
    scheduler = BackgroundScheduler(timezone="America/Merida")
    scheduler.add_job(
        scrape_all_labs,
        trigger=CronTrigger(hour=6, minute=0),
        id="daily_scrape_bg",
        name="Scrape diario (background)",
        replace_existing=True,
    )
    return scheduler


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Scheduler de scraping Chopo")
    parser.add_argument("--hour", type=int, default=6, help="Hora de ejecución diaria (0-23)")
    parser.add_argument("--minute", type=int, default=0, help="Minuto de ejecución (0-59)")
    parser.add_argument("--now", action="store_true", help="Ejecutar scrape inmediatamente y salir")
    args = parser.parse_args()

    if args.now:
        logger.info("Ejecutando scrape manual inmediato...")
        init_db()
        scrape_all_labs()
        logger.info("Scrape manual completado")
    else:
        start_daily_scheduler(hour=args.hour, minute=args.minute)
