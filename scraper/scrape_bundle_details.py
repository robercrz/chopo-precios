# ============================================================
# scraper/scrape_bundle_details.py
# Extractor ligero (requests + bs4) para los detalles y estudios
# incluidos en los 147 paquetes y perfiles de Chopo.
# Se ejecuta una sola vez y guarda en SQLite.
# ============================================================

import sqlite3
import re
import json
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup
from loguru import logger

DB_PATH = Path(__file__).parent.parent / "db" / "chopo_prices.db"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
}


def init_bundle_table():
    """Crea la tabla bundle_details si no existe."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS bundle_details (
            study_name TEXT PRIMARY KEY,
            url TEXT,
            description TEXT,
            included_text TEXT,
            bullets TEXT,
            fasting TEXT,
            custom_notes TEXT,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()


def parse_page_details(html: str) -> dict:
    """Extrae descripción, estudios incluidos, viñetas y ayuno del HTML de Chopo."""
    soup = BeautifulSoup(html, "html.parser")

    # 1. Descripción en overview
    overview = soup.find(class_="overview")
    raw_desc = ""
    bullets = []

    if overview:
        raw_desc = " ".join(overview.get_text().split())
        raw_desc = raw_desc.replace("Ver más", "").strip()

        # Buscar viñetas en párrafos o líneas con *, •, -
        for p in overview.find_all(["p", "div", "li"]):
            txt = p.get_text()
            if any(sym in txt for sym in ["*", "•", "•", "-"]):
                for line in txt.split("\n"):
                    clean_l = line.strip()
                    if clean_l.startswith(("*", "•", "-", "+")):
                        item = clean_l.lstrip("*•-+ ").strip()
                        if item and len(item) > 3 and item not in bullets:
                            bullets.append(item)

    # 2. Buscar respuestas en encabezados H2 (preguntas frecuentes Chopo)
    included_text = ""
    fasting = ""

    for h2 in soup.find_all(["h2", "h3", "h4", "strong"]):
        txt_h2 = h2.get_text().lower()
        if "incluye" in txt_h2 and not included_text:
            sib = h2.find_next_sibling()
            if sib:
                included_text = " ".join(sib.get_text().split()).strip()

        if ("ayuno" in txt_h2 or "preparaci" in txt_h2 or "requisito" in txt_h2) and not fasting:
            sib = h2.find_next_sibling()
            if sib:
                fasting = " ".join(sib.get_text().split()).strip()

    # Si hay viñetas dentro del texto de include_text
    if not bullets and included_text:
        # A veces viene separado por comas o dos puntos
        if ":" in included_text:
            parts = included_text.split(":")[-1]
            split_items = [p.strip() for p in re.split(r"[,;y\.]", parts) if len(p.strip()) > 3]
            if len(split_items) >= 2:
                bullets = split_items[:15]

    return {
        "description": raw_desc[:2000] if raw_desc else "",
        "included_text": included_text[:2000] if included_text else "",
        "bullets": json.dumps(bullets, ensure_ascii=False) if bullets else "",
        "fasting": fasting[:1000] if fasting else "",
    }


def fetch_and_parse(study_name: str, url: str) -> tuple[str, str, dict]:
    """Descarga y procesa un paquete individual."""
    if not url:
        return study_name, url, {}
    try:
        res = requests.get(url, headers=HEADERS, timeout=12)
        if res.status_code == 200:
            parsed = parse_page_details(res.text)
            return study_name, url, parsed
    except Exception as e:
        logger.warning(f"Error descargando {study_name}: {e}")
    return study_name, url, {}


def run_bundle_scraper(max_workers: int = 5, force: bool = False):
    """
    Ejecuta la extracción de detalles para los ~147 paquetes de Chopo.
    Si force=False, solo procesa aquellos que aún no estén en bundle_details.
    """
    init_bundle_table()

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Obtener todos los paquetes
    query = """
        SELECT DISTINCT study_name, url 
        FROM latest_prices 
        WHERE (study_name LIKE '%CHECK%' 
           OR study_name LIKE '%PERFIL%' 
           OR study_name LIKE '%INTEGRAL%' 
           OR study_name LIKE '%PAQUETE%'
           OR study_name LIKE '%PANEL%'
           OR study_name LIKE '%PREVENC%')
           AND url IS NOT NULL
    """
    c.execute(query)
    all_bundles = c.fetchall()

    if not force:
        c.execute("SELECT study_name FROM bundle_details WHERE description != '' OR included_text != ''")
        already_done = set(r[0] for r in c.fetchall())
        pending = [b for b in all_bundles if b[0] not in already_done]
    else:
        pending = all_bundles

    logger.info(f"Total paquetes detectados: {len(all_bundles)} | Pendientes por procesar: {len(pending)}")

    if not pending:
        logger.success("Todos los paquetes ya tienen sus detalles extraídos en la base de datos.")
        conn.close()
        return len(all_bundles), 0

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_and_parse, name, url): name for name, url in pending}
        for fut in as_completed(futures):
            name, url, data = fut.result()
            if data:
                results.append((
                    name,
                    url,
                    data.get("description", ""),
                    data.get("included_text", ""),
                    data.get("bullets", ""),
                    data.get("fasting", ""),
                ))

    # Guardar en SQLite
    c.executemany("""
        INSERT OR REPLACE INTO bundle_details 
        (study_name, url, description, included_text, bullets, fasting)
        VALUES (?, ?, ?, ?, ?, ?)
    """, results)

    conn.commit()
    conn.close()

    logger.success(f"Extracción completada: {len(results)} paquetes procesados y guardados.")
    return len(all_bundles), len(results)


def get_bundle_detail(study_name: str) -> dict:
    """Consulta los detalles guardados de un paquete."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT study_name, url, description, included_text, bullets, fasting, custom_notes
        FROM bundle_details
        WHERE study_name = ?
    """, (study_name,))
    row = c.fetchone()
    conn.close()

    if not row:
        return {}

    bullets_list = []
    if row[4]:
        try:
            bullets_list = json.loads(row[4])
        except Exception:
            bullets_list = [b.strip() for b in row[4].split("\n") if b.strip()]

    return {
        "study_name": row[0],
        "url": row[1],
        "description": row[2] or "",
        "included_text": row[3] or "",
        "bullets": bullets_list,
        "fasting": row[5] or "",
        "custom_notes": row[6] or "",
    }


def save_bundle_custom_notes(study_name: str, notes: str):
    """Permite al usuario guardar notas personalizadas sobre los estudios incluidos."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        UPDATE bundle_details
        SET custom_notes = ?
        WHERE study_name = ?
    """, (notes, study_name))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    total, processed = run_bundle_scraper(max_workers=5, force=False)
    print(f"Total: {total}, Procesados ahora: {processed}")
