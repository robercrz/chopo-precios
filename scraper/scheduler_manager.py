# ============================================================
# scraper/scheduler_manager.py
# Gestor de control y estado del scheduler para el Dashboard
# ============================================================

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

ROOT_DIR = Path(__file__).parent.parent
CONFIG_FILE = ROOT_DIR / "config" / "scheduler_config.json"
STATUS_FILE = ROOT_DIR / "logs" / "scheduler_status.json"
PID_FILE    = ROOT_DIR / "logs" / "scheduler.pid"

DEFAULT_CONFIG = {
    "mode": "cron",           # "cron" o "interval"
    "cron_hour": 6,
    "cron_minute": 0,
    "interval_hours": 12,
    "branch": "altabrisa",
    "lab_key": "chopo_yucatan",
    "enabled": True,
}


def get_config() -> dict:
    """Retorna la configuración actual."""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        try:
            return {**DEFAULT_CONFIG, **json.loads(CONFIG_FILE.read_text(encoding="utf-8"))}
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()


def save_config(config: dict) -> None:
    """Guarda la configuración."""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")


def get_scheduler_status() -> dict:
    """
    Retorna el estado en tiempo real del scheduler:
    {
        "running": bool,
        "pid": Optional[int],
        "config": dict,
        "status_data": dict,
    }
    """
    config = get_config()
    status_data = {}
    if STATUS_FILE.exists():
        try:
            status_data = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    pid = None
    running = False
    if PID_FILE.exists():
        try:
            import psutil
            val = int(PID_FILE.read_text(encoding="utf-8").strip())
            if psutil.pid_exists(val):
                p = psutil.Process(val)
                if p.is_running() and p.status() != psutil.STATUS_ZOMBIE:
                    pid = val
                    running = True
        except Exception:
            pass

        if not running and PID_FILE.exists():
            try:
                PID_FILE.unlink()
            except Exception:
                pass

    return {
        "running": running,
        "pid": pid,
        "config": config,
        "status_data": status_data,
    }


def start_scheduler() -> tuple[bool, str]:
    """Inicia el servicio del scheduler en un proceso en segundo plano."""
    status = get_scheduler_status()
    if status["running"]:
        return True, f"El scheduler ya está activo (PID {status['pid']})."

    script = str(ROOT_DIR / "scraper" / "scheduler_service.py")
    log_file = open(ROOT_DIR / "logs" / "scheduler.log", "a", encoding="utf-8", errors="replace")

    # En Windows, usar creación de proceso desvinculado (CREATE_NO_WINDOW o detached)
    creationflags = 0
    if sys.platform == "win32":
        creationflags = 0x00000008 | 0x08000000  # DETACHED_PROCESS | CREATE_NO_WINDOW

    try:
        proc = subprocess.Popen(
            [sys.executable, script],
            stdout=log_file,
            stderr=log_file,
            cwd=str(ROOT_DIR),
            creationflags=creationflags,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text(str(proc.pid), encoding="utf-8")
        return True, f"Scheduler iniciado correctamente (PID {proc.pid})."
    except Exception as e:
        return False, f"Error iniciando scheduler: {e}"


def stop_scheduler() -> tuple[bool, str]:
    """Detiene el servicio del scheduler."""
    status = get_scheduler_status()
    if not status["running"]:
        if PID_FILE.exists():
            try: PID_FILE.unlink()
            except: pass
        return True, "El scheduler no estaba en ejecución."

    pid = status["pid"]
    try:
        import psutil
        parent = psutil.Process(pid)
        for child in parent.children(recursive=True):
            try: child.kill()
            except: pass
        parent.kill()
    except Exception as e:
        return False, f"Error deteniendo proceso {pid}: {e}"
    finally:
        if PID_FILE.exists():
            try: PID_FILE.unlink()
            except: pass

    # Actualizar estado a detenido
    if STATUS_FILE.exists():
        try:
            st = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
            st["status"] = "stopped"
            st["message"] = "Servicio detenido por el usuario"
            STATUS_FILE.write_text(json.dumps(st, indent=2, ensure_ascii=False), encoding="utf-8")
        except:
            pass

    return True, f"Scheduler detenido (PID {pid})."


def restart_scheduler() -> tuple[bool, str]:
    """Reinicia el servicio para aplicar cambios de configuración."""
    stop_scheduler()
    return start_scheduler()
