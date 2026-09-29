# ============================================================
# db/database.py
# Capa de base de datos SQLite para histórico de precios
# ============================================================

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger

# Ruta de la base de datos (relativa al directorio del proyecto)
DB_PATH = Path(__file__).parent / "chopo_prices.db"


def get_connection() -> sqlite3.Connection:
    """Obtiene una conexión a la base de datos SQLite."""
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row  # Permite acceso por nombre de columna
    conn.execute("PRAGMA journal_mode=WAL")  # Mejor rendimiento concurrente
    return conn


def init_db():
    """Inicializa el esquema de la base de datos."""
    conn = get_connection()
    try:
        with conn:
            conn.executescript("""
                -- Tabla de laboratorios registrados
                CREATE TABLE IF NOT EXISTS labs (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    lab_key     TEXT UNIQUE NOT NULL,
                    lab_name    TEXT NOT NULL,
                    city        TEXT NOT NULL,
                    state       TEXT NOT NULL,
                    url         TEXT,
                    active      INTEGER DEFAULT 1,
                    created_at  TEXT DEFAULT (datetime('now'))
                );

                -- Tabla de estudios (catálogo)
                CREATE TABLE IF NOT EXISTS studies (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    lab_id      INTEGER REFERENCES labs(id),
                    study_name  TEXT NOT NULL,
                    branch      TEXT,
                    sku         TEXT,
                    url         TEXT,
                    UNIQUE(lab_id, study_name, branch)
                );

                -- Tabla de precios históricos (append-only, nunca se modifica)
                CREATE TABLE IF NOT EXISTS price_history (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    study_id    INTEGER REFERENCES studies(id),
                    lab_id      INTEGER REFERENCES labs(id),
                    price       REAL,
                    price_raw   TEXT,
                    price_original     REAL,
                    price_original_raw TEXT,
                    scraped_at  TEXT NOT NULL,
                    created_at  TEXT DEFAULT (datetime('now'))
                );

                -- Vista de precios más recientes por estudio
                DROP VIEW IF EXISTS latest_prices;
                CREATE VIEW latest_prices AS
                    SELECT
                        s.study_name,
                        l.lab_name,
                        l.city,
                        l.state,
                        s.branch,
                        ph.price,
                        ph.price_raw,
                        ph.price_original,
                        ph.price_original_raw,
                        ph.scraped_at,
                        s.url,
                        s.sku
                    FROM price_history ph
                    JOIN studies s ON ph.study_id = s.id
                    JOIN labs l ON ph.lab_id = l.id
                    WHERE ph.id IN (
                        SELECT MAX(id)
                        FROM price_history
                        GROUP BY study_id
                    );

                -- Índices para consultas rápidas
                CREATE INDEX IF NOT EXISTS idx_ph_study_id    ON price_history(study_id);
                CREATE INDEX IF NOT EXISTS idx_ph_scraped_at  ON price_history(scraped_at);
                CREATE INDEX IF NOT EXISTS idx_ph_lab_id      ON price_history(lab_id);

                -- Tabla de estudios favoritos (monitoreados)
                CREATE TABLE IF NOT EXISTS favorites (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    study_name  TEXT NOT NULL,
                    lab_key     TEXT NOT NULL,
                    branch      TEXT,
                    note        TEXT,
                    alert_threshold REAL,
                    created_at  TEXT DEFAULT (datetime('now')),
                    UNIQUE(study_name, lab_key, branch)
                );
            """)

            # Migración automática de columnas para bases de datos existentes
            cols = [r[1] for r in conn.execute("PRAGMA table_info(price_history)").fetchall()]
            if "price_original" not in cols:
                conn.execute("ALTER TABLE price_history ADD COLUMN price_original REAL")
            if "price_original_raw" not in cols:
                conn.execute("ALTER TABLE price_history ADD COLUMN price_original_raw TEXT")

        logger.info(f"Base de datos inicializada: {DB_PATH}")
    finally:
        conn.close()


def upsert_lab(lab_key: str, lab_name: str, city: str, state: str, url: str = None) -> int:
    """Registra o actualiza un laboratorio. Retorna el ID."""
    conn = get_connection()
    try:
        with conn:
            conn.execute("""
                INSERT INTO labs (lab_key, lab_name, city, state, url)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(lab_key) DO UPDATE SET
                    lab_name = excluded.lab_name,
                    city     = excluded.city,
                    state    = excluded.state,
                    url      = excluded.url
            """, (lab_key, lab_name, city, state, url))
        row = conn.execute("SELECT id FROM labs WHERE lab_key = ?", (lab_key,)).fetchone()
        return row["id"]
    finally:
        conn.close()


def save_scrape_results(results: list[dict]) -> int:
    """
    Guarda los resultados del scrape en la BD.
    Retorna el número de registros insertados.
    """
    if not results:
        logger.warning("No hay resultados para guardar")
        return 0

    conn = get_connection()
    inserted = 0
    try:
        with conn:
            for item in results:
                # Asegurar que el lab existe
                lab_row = conn.execute(
                    "SELECT id FROM labs WHERE lab_key = ?", (item["lab_key"],)
                ).fetchone()

                if not lab_row:
                    conn.execute("""
                        INSERT OR IGNORE INTO labs (lab_key, lab_name, city, state)
                        VALUES (?, ?, ?, ?)
                    """, (item["lab_key"], item["lab_name"], item["city"], item["state"]))
                    lab_row = conn.execute(
                        "SELECT id FROM labs WHERE lab_key = ?", (item["lab_key"],)
                    ).fetchone()

                lab_id = lab_row["id"]

                # Upsert del estudio en el catálogo
                conn.execute("""
                    INSERT OR IGNORE INTO studies (lab_id, study_name, branch, sku, url)
                    VALUES (?, ?, ?, ?, ?)
                """, (lab_id, item["study_name"], item.get("branch"), item.get("sku"), item.get("url")))

                study_row = conn.execute(
                    "SELECT id FROM studies WHERE lab_id = ? AND study_name = ? AND (branch = ? OR branch IS NULL)",
                    (lab_id, item["study_name"], item.get("branch"))
                ).fetchone()

                study_id = study_row["id"]

                # Insertar en historial de precios (siempre append)
                conn.execute("""
                    INSERT INTO price_history (study_id, lab_id, price, price_raw, price_original, price_original_raw, scraped_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    study_id,
                    lab_id,
                    item.get("price"),
                    item.get("price_raw"),
                    item.get("price_original"),
                    item.get("price_original_raw"),
                    item.get("scraped_at", datetime.now().isoformat()),
                ))
                inserted += 1

        logger.success(f"Guardados {inserted} registros de precios en la BD")
        return inserted
    except Exception as e:
        logger.error(f"Error guardando en BD: {e}")
        raise
    finally:
        conn.close()


def get_latest_prices(lab_key: Optional[str] = None) -> list[dict]:
    """Obtiene los precios más recientes. Opcionalmente filtrado por laboratorio."""
    conn = get_connection()
    try:
        if lab_key:
            rows = conn.execute("""
                SELECT lp.* FROM latest_prices lp
                JOIN labs l ON lp.lab_name = l.lab_name
                WHERE l.lab_key = ?
                ORDER BY lp.study_name
            """, (lab_key,)).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM latest_prices ORDER BY lab_name, study_name"
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_price_history(study_name: str, lab_key: Optional[str] = None) -> list[dict]:
    """Obtiene el historial completo de precios de un estudio específico."""
    conn = get_connection()
    try:
        if lab_key:
            rows = conn.execute("""
                SELECT ph.price, ph.price_raw, ph.price_original, ph.price_original_raw, ph.scraped_at
                FROM price_history ph
                JOIN studies s  ON ph.study_id = s.id
                JOIN labs l     ON ph.lab_id   = l.id
                WHERE s.study_name = ? AND l.lab_key = ?
                ORDER BY ph.scraped_at
            """, (study_name, lab_key)).fetchall()
        else:
            rows = conn.execute("""
                SELECT ph.price, ph.price_raw, ph.price_original, ph.price_original_raw, ph.scraped_at
                FROM price_history ph
                JOIN studies s  ON ph.study_id = s.id
                WHERE s.study_name = ?
                ORDER BY ph.scraped_at
            """, (study_name,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_all_labs() -> list[dict]:
    """Retorna todos los laboratorios registrados."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM labs WHERE active = 1 ORDER BY lab_name"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_price_changes(days: int = 30) -> list[dict]:
    """
    Detecta cambios de precio en los últimos N días.
    Retorna estudios cuyo precio ha cambiado.
    """
    conn = get_connection()
    try:
        rows = conn.execute("""
            WITH ranked AS (
                SELECT
                    s.study_name,
                    l.lab_name,
                    l.city,
                    ph.price,
                    ph.scraped_at,
                    LAG(ph.price) OVER (
                        PARTITION BY ph.study_id
                        ORDER BY ph.scraped_at
                    ) AS prev_price
                FROM price_history ph
                JOIN studies s ON ph.study_id = s.id
                JOIN labs l    ON ph.lab_id   = l.id
                WHERE ph.scraped_at >= datetime('now', ?)
            )
            SELECT *,
                ROUND((price - prev_price) / prev_price * 100, 2) AS change_pct
            FROM ranked
            WHERE prev_price IS NOT NULL AND price != prev_price
            ORDER BY scraped_at DESC
        """, (f"-{days} days",)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_scrape_log() -> list[dict]:
    """Retorna el log de scrapes realizados."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT
                l.lab_name,
                l.city,
                ph.scraped_at,
                COUNT(*) as studies_count
            FROM price_history ph
            JOIN labs l ON ph.lab_id = l.id
            GROUP BY l.lab_name, l.city, ph.scraped_at
            ORDER BY ph.scraped_at DESC
            LIMIT 50
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── Funciones de Favoritos ─────────────────────────────────────────────────────

def add_favorite(study_name: str, lab_key: str, branch: str = None,
                 note: str = None, alert_threshold: float = None) -> bool:
    """Agrega un estudio a favoritos. Retorna True si fue agregado, False si ya existia."""
    conn = get_connection()
    try:
        with conn:
            conn.execute("""
                INSERT OR IGNORE INTO favorites (study_name, lab_key, branch, note, alert_threshold)
                VALUES (?, ?, ?, ?, ?)
            """, (study_name, lab_key, branch, note, alert_threshold))
        return True
    except Exception:
        return False
    finally:
        conn.close()


def remove_favorite(study_name: str, lab_key: str, branch: str = None) -> bool:
    """Elimina un estudio de favoritos."""
    conn = get_connection()
    try:
        with conn:
            conn.execute("""
                DELETE FROM favorites
                WHERE study_name = ? AND lab_key = ? AND (branch = ? OR branch IS NULL)
            """, (study_name, lab_key, branch))
        return True
    except Exception:
        return False
    finally:
        conn.close()


def is_favorite(study_name: str, lab_key: str, branch: str = None) -> bool:
    """Verifica si un estudio esta en favoritos."""
    conn = get_connection()
    try:
        row = conn.execute("""
            SELECT id FROM favorites
            WHERE study_name = ? AND lab_key = ? AND (branch = ? OR branch IS NULL)
        """, (study_name, lab_key, branch)).fetchone()
        return row is not None
    finally:
        conn.close()


def get_favorites(lab_key: str = None) -> list:
    """Retorna todos los estudios favoritos con su precio actual y variacion."""
    conn = get_connection()
    try:
        query = """
            SELECT
                f.id,
                f.study_name,
                f.lab_key,
                f.branch,
                f.note,
                f.alert_threshold,
                f.created_at,
                lp.price        AS current_price,
                lp.price_raw    AS current_price_raw,
                lp.scraped_at   AS last_updated,
                lp.lab_name,
                -- Precio anterior para calcular variacion
                (
                    SELECT ph2.price
                    FROM price_history ph2
                    JOIN studies s2 ON ph2.study_id = s2.id
                    WHERE s2.study_name = f.study_name
                    ORDER BY ph2.id DESC
                    LIMIT 1 OFFSET 1
                ) AS prev_price
            FROM favorites f
            LEFT JOIN latest_prices lp ON lp.study_name = f.study_name
        """
        params = []
        if lab_key:
            query += " WHERE f.lab_key = ?"
            params.append(lab_key)
        query += " ORDER BY f.created_at DESC"
        rows = conn.execute(query, params).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            if d.get("current_price") and d.get("prev_price"):
                diff = d["current_price"] - d["prev_price"]
                d["price_change"] = diff
                d["price_change_pct"] = (diff / d["prev_price"]) * 100
            else:
                d["price_change"] = None
                d["price_change_pct"] = None
            results.append(d)
        return results
    finally:
        conn.close()


def update_favorite_note(study_name: str, lab_key: str, note: str = None,
                         alert_threshold: float = None) -> bool:
    """Actualiza la nota y/o umbral de alerta de un favorito."""
    conn = get_connection()
    try:
        with conn:
            conn.execute("""
                UPDATE favorites SET note = ?, alert_threshold = ?
                WHERE study_name = ? AND lab_key = ?
            """, (note, alert_threshold, study_name, lab_key))
        return True
    except Exception:
        return False
    finally:
        conn.close()


def get_favorite_names(lab_key: str = None) -> set:
    """Retorna un set con los nombres de todos los favoritos (para lookups rapidos)."""
    conn = get_connection()
    try:
        if lab_key:
            rows = conn.execute(
                "SELECT study_name FROM favorites WHERE lab_key = ?", (lab_key,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT study_name FROM favorites").fetchall()
        return {r["study_name"] for r in rows}
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print(f"Base de datos lista en: {DB_PATH}")
