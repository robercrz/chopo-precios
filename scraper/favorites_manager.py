# ============================================================
# scraper/favorites_manager.py
# Gestor robusto de favoritos con triple capa de persistencia:
# 1. Archivo local config/mis_favoritos.json (independiente del scraper)
# 2. Respaldo en base de datos SQLite (db/chopo_prices.db)
# 3. Sincronización transparente con GitHub Gist privado (si se configura en secrets)
# 4. Importación / Exportación manual JSON desde el dashboard
# ============================================================

import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Set
from loguru import logger

CONFIG_DIR = Path(__file__).parent.parent / "config"
CONFIG_DIR.mkdir(exist_ok=True)
FAV_FILE = CONFIG_DIR / "mis_favoritos.json"


def _get_gist_config() -> tuple[Optional[str], Optional[str]]:
    """Obtiene el token y gist_id de st.secrets de forma 100% segura si están disponibles."""
    try:
        import streamlit as st
        if hasattr(st, "secrets"):
            token = st.secrets.get("GITHUB_TOKEN") or st.secrets.get("GH_TOKEN")
            gist_id = st.secrets.get("GIST_ID") or st.secrets.get("FAVORITES_GIST_ID")
            return (str(token).strip() if token else None, str(gist_id).strip() if gist_id else None)
    except Exception:
        pass
    return None, None


def _sync_from_gist(token: str, gist_id: str) -> Optional[List[Dict]]:
    """Descarga los favoritos desde un Gist privado con timeout estricto."""
    import urllib.request
    try:
        url = f"https://api.github.com/gists/{gist_id}"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "Chopo-Favorites-Sync"
            }
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            files = data.get("files", {})
            if "mis_favoritos.json" in files:
                content = files["mis_favoritos.json"].get("content", "[]")
                parsed = json.loads(content)
                if isinstance(parsed, list):
                    return parsed
    except Exception as e:
        logger.debug(f"Gist sync read omitido o no disponible: {e}")
    return None


def _sync_to_gist(token: str, gist_id: Optional[str], favs: List[Dict]) -> Optional[str]:
    """Guarda los favoritos en un Gist privado (creándolo si no existe) con timeout estricto."""
    import urllib.request
    payload_content = json.dumps(favs, indent=2, ensure_ascii=False)
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "User-Agent": "Chopo-Favorites-Sync"
    }

    try:
        if gist_id:
            # Actualizar gist existente
            url = f"https://api.github.com/gists/{gist_id}"
            body = json.dumps({
                "description": "Chopo Mérida - Mis Favoritos Persistentes",
                "files": {"mis_favoritos.json": {"content": payload_content}}
            }).encode("utf-8")
            req = urllib.request.Request(url, data=body, headers=headers, method="PATCH")
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    return gist_id
        else:
            # Crear gist nuevo privado
            url = "https://api.github.com/gists"
            body = json.dumps({
                "description": "Chopo Mérida - Mis Favoritos Persistentes",
                "public": False,
                "files": {"mis_favoritos.json": {"content": payload_content}}
            }).encode("utf-8")
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                new_id = data.get("id")
                logger.info(f"Nuevo Gist de favoritos creado: {new_id}")
                return new_id
    except Exception as e:
        logger.debug(f"Gist sync write omitido: {e}")
    return gist_id


def load_all_favorites() -> List[Dict]:
    """
    Carga todos los favoritos combinando:
    1. GitHub Gist (si está configurado)
    2. config/mis_favoritos.json
    3. SQLite en db/chopo_prices.db
    """
    favs_by_name: Dict[str, Dict] = {}

    # 1. Cargar desde config/mis_favoritos.json
    if FAV_FILE.exists():
        try:
            with open(FAV_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                if isinstance(saved, list):
                    for item in saved:
                        if isinstance(item, str):
                            favs_by_name[item] = {
                                "study_name": item,
                                "lab_key": "chopo_yucatan",
                                "branch": "",
                                "note": "",
                                "created_at": str(datetime.now())[:10]
                            }
                        elif isinstance(item, dict) and item.get("study_name"):
                            favs_by_name[item["study_name"]] = item
        except Exception as e:
            logger.debug(f"Error leyendo {FAV_FILE}: {e}")

    # 2. Cargar desde SQLite
    try:
        from db.database import get_favorites
        db_favs = get_favorites()
        for f in db_favs:
            s_name = f.get("study_name")
            if s_name and s_name not in favs_by_name:
                favs_by_name[s_name] = dict(f)
    except Exception as e:
        logger.debug(f"Error leyendo favoritos de SQLite: {e}")

    # 3. Intentar Gist si está configurado en Streamlit secrets
    token, gist_id = _get_gist_config()
    if token and gist_id:
        gist_favs = _sync_from_gist(token, gist_id)
        if gist_favs:
            for item in gist_favs:
                if isinstance(item, dict) and item.get("study_name"):
                    favs_by_name[item["study_name"]] = item
                elif isinstance(item, str):
                    favs_by_name[item] = {
                        "study_name": item,
                        "lab_key": "chopo_yucatan",
                        "branch": "",
                        "note": "",
                        "created_at": str(datetime.now())[:10]
                    }

    return list(favs_by_name.values())


def get_favorite_study_names() -> Set[str]:
    """Retorna un conjunto con solo los nombres de los estudios favoritos."""
    all_favs = load_all_favorites()
    return {f["study_name"] for f in all_favs if f.get("study_name")}


def save_all_favorites(favs: List[Dict]) -> bool:
    """
    Guarda la lista completa de favoritos:
    1. En config/mis_favoritos.json
    2. En SQLite (db/chopo_prices.db)
    3. En GitHub Gist (si está configurado)
    """
    # Normalizar lista
    clean_favs = []
    seen = set()
    for f in favs:
        if isinstance(f, str):
            f = {"study_name": f, "lab_key": "chopo_yucatan", "branch": "", "created_at": str(datetime.now())[:10]}
        if isinstance(f, dict) and f.get("study_name"):
            name = f["study_name"].strip()
            if name not in seen:
                seen.add(name)
                clean_favs.append({
                    "study_name": name,
                    "lab_key": f.get("lab_key", "chopo_yucatan"),
                    "branch": f.get("branch", ""),
                    "note": f.get("note", ""),
                    "created_at": f.get("created_at") or str(datetime.now())[:10],
                    "alert_threshold": f.get("alert_threshold")
                })

    # 1. Guardar en config/mis_favoritos.json
    try:
        with open(FAV_FILE, "w", encoding="utf-8") as out:
            json.dump(clean_favs, out, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error escribiendo {FAV_FILE}: {e}")

    # 2. Guardar en SQLite (manteniendo sincronía exacta)
    try:
        from db.database import get_favorite_names, remove_favorite, add_favorite
        db_names = get_favorite_names()
        clean_names = {item["study_name"] for item in clean_favs}
        for old in db_names - clean_names:
            remove_favorite(old)
        for item in clean_favs:
            add_favorite(item["study_name"], item.get("lab_key", "chopo_yucatan"), item.get("branch"))
    except Exception as e:
        logger.debug(f"Error sincronizando con SQLite: {e}")

    # 3. Guardar en Gist (opcional)
    token, gist_id = _get_gist_config()
    if token:
        _sync_to_gist(token, gist_id, clean_favs)

    return True


def add_favorite_study(study_name: str, lab_key: str = "chopo_yucatan", branch: str = None, note: str = "") -> bool:
    """Agrega un estudio a favoritos."""
    current = load_all_favorites()
    names = {f["study_name"] for f in current if f.get("study_name")}
    if study_name not in names:
        current.append({
            "study_name": study_name,
            "lab_key": lab_key,
            "branch": branch or "",
            "note": note,
            "created_at": str(datetime.now())[:10]
        })
        save_all_favorites(current)
    return True


def remove_favorite_study(study_name: str, lab_key: str = "chopo_yucatan", branch: str = None) -> bool:
    """Elimina un estudio de favoritos."""
    try:
        from db.database import remove_favorite
        remove_favorite(study_name, lab_key, branch)
    except Exception:
        pass

    current = load_all_favorites()
    filtered = [f for f in current if f.get("study_name") != study_name]
    save_all_favorites(filtered)
    return True


def import_favorites_from_json(json_str: str) -> int:
    """
    Importa favoritos desde una cadena JSON (respaldo).
    Retorna el número de favoritos importados.
    """
    try:
        parsed = json.loads(json_str)
        if not isinstance(parsed, list):
            return 0

        current = load_all_favorites()
        favs_by_name = {f["study_name"]: f for f in current if f.get("study_name")}

        added_count = 0
        for item in parsed:
            if isinstance(item, str):
                s_name = item.strip()
                if s_name and s_name not in favs_by_name:
                    favs_by_name[s_name] = {
                        "study_name": s_name,
                        "lab_key": "chopo_yucatan",
                        "branch": "",
                        "note": "",
                        "created_at": str(datetime.now())[:10]
                    }
                    added_count += 1
            elif isinstance(item, dict) and item.get("study_name"):
                s_name = item["study_name"].strip()
                if s_name not in favs_by_name:
                    favs_by_name[s_name] = item
                    added_count += 1

        save_all_favorites(list(favs_by_name.values()))
        return added_count
    except Exception as e:
        logger.error(f"Error importando JSON de favoritos: {e}")
        return 0


def export_favorites_to_json() -> str:
    """Exporta los favoritos actuales en formato JSON legible."""
    favs = load_all_favorites()
    return json.dumps(favs, indent=2, ensure_ascii=False)
