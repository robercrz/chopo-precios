# ============================================================
# scraper/scheduler_service.py
# Servicio de actualización automática configurable con APScheduler
# ============================================================

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# Path del proyecto
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

CONFIG_FILE = ROOT_DIR / "config" / "scheduler_config.json"
STATUS_FILE = ROOT_DIR / "logs" / "scheduler_status.json"
PID_FILE    = ROOT_DIR / "logs" / "scheduler.pid"
LOG_FILE    = ROOT_DIR / "logs" / "scheduler.log"

DEFAULT_CONFIG = {
    "mode": "cron",           # "cron" (hora fija) o "interval" (cada X horas)
    "cron_hour": 6,          # 6 AM
    "cron_minute": 0,
    "interval_hours": 12,    # Cada 12 horas
    "branch": "altabrisa",
    "lab_key": "chopo_yucatan",
    "enabled": True,
}


def load_config() -> dict:
    """Carga la configuración del scheduler o genera la default."""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        try:
            return {**DEFAULT_CONFIG, **json.loads(CONFIG_FILE.read_text(encoding="utf-8"))}
        except Exception as e:
            logger.warning(f"Error leyendo configuración: {e}, usando default")
    save_config(DEFAULT_CONFIG)
    return DEFAULT_CONFIG


def save_config(config: dict) -> None:
    """Guarda la configuración del scheduler."""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")


def update_status(status: str, last_run: Optional[str] = None, next_run: Optional[str] = None, message: str = "") -> None:
    """Actualiza el archivo de estado del scheduler."""
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    current = {}
    if STATUS_FILE.exists():
        try:
            current = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    current.update({
        "status": status,
        "pid": os.getpid(),
        "updated_at": datetime.now().isoformat(),
        "message": message,
    })
    if last_run:
        current["last_run"] = last_run
    if next_run:
        current["next_run"] = next_run
    STATUS_FILE.write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")


def run_scrape_task(branch: str = "altabrisa", lab_key: str = "chopo_yucatan") -> None:
    """Ejecuta una ronda de scrape automática."""
    now_iso = datetime.now().isoformat()
    logger.info(f"[SCHEDULER SERVICE] Ejecutando scrape programado para {lab_key} ({branch})...")
    update_status("running", last_run=now_iso, message=f"Scrapeando sucursal {branch}...")

    try:
        import asyncio
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

        from scraper.chopo_scraper import run_scrape_sync, LABS_CONFIG
        from db.database import init_db, upsert_lab, save_scrape_results

        init_db()
        lab_cfg = LABS_CONFIG.get(lab_key, {})
        if lab_cfg:
            upsert_lab(
                lab_key=lab_key,
                lab_name=lab_cfg["name"],
                city=lab_cfg["city"],
                state=lab_cfg["state"],
                url=lab_cfg["url"],
            )

        results = run_scrape_sync(lab_key=lab_key, branch_key=branch, headless=True)
        if results:
            saved = save_scrape_results(results)
            msg = f"Completado exitosamente: {saved} estudios guardados en BD."
            logger.success(f"[SCHEDULER SERVICE] {msg}")
            update_status("idle", message=msg)
        else:
            msg = "El scrape finalizó pero no devolvió resultados."
            logger.warning(f"[SCHEDULER SERVICE] {msg}")
            update_status("idle", message=msg)

    except Exception as e:
        msg = f"Error durante la ejecución: {e}"
        logger.error(f"[SCHEDULER SERVICE] {msg}")
        update_status("error", message=msg)


def main():
    """Bucle principal del servicio scheduler."""
    logger.add(LOG_FILE, rotation="1 week", retention="1 month", level="INFO")
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")

    config = load_config()
    logger.info(f"[SCHEDULER SERVICE] Iniciando servicio con PID: {os.getpid()}")
    logger.info(f"[SCHEDULER SERVICE] Configuración: {config}")

    scheduler = BlockingScheduler(timezone="America/Merida")

    branch = config.get("branch", "altabrisa")
    lab_key = config.get("lab_key", "chopo_yucatan")
    mode = config.get("mode", "cron")

    if mode == "interval":
        hours = max(1, int(config.get("interval_hours", 12)))
        trigger = IntervalTrigger(hours=hours)
        desc = f"cada {hours} hora(s)"
    else:
        hour = int(config.get("cron_hour", 6))
        minute = int(config.get("cron_minute", 0))
        trigger = CronTrigger(hour=hour, minute=minute, timezone="America/Merida")
        desc = f"diariamente a las {hour:02d}:{minute:02d} (Hora Mérida)"

    job = scheduler.add_job(
        lambda: run_scrape_task(branch=branch, lab_key=lab_key),
        trigger=trigger,
        id="auto_scraper_job",
        name=f"Actualización automática Chopo ({desc})",
        replace_existing=True,
    )

    import pytz
    tz = pytz.timezone("America/Merida")
    now_tz = datetime.now(tz)
    next_fire = trigger.get_next_fire_time(None, now_tz)
    next_time = next_fire.strftime("%Y-%m-%d %H:%M:%S") if next_fire else "N/D"

    logger.info(f"[SCHEDULER SERVICE] Job configurado {desc}. Próxima ejecución: {next_time}")
    update_status("idle", next_run=next_time, message=f"Programado {desc}")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("[SCHEDULER SERVICE] Servicio detenido.")
        update_status("stopped", message="Servicio detenido")
    finally:
        try:
            PID_FILE.unlink()
        except Exception:
            pass


if __name__ == "__main__":
    main()
