# ============================================================
# dashboard/app.py
# Dashboard Streamlit para análisis de precios competitivos
# ============================================================

import sys
from pathlib import Path

# Agregar el directorio raíz al path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import io
import unicodedata
from datetime import datetime, timedelta
from typing import Optional
from loguru import logger

from db.database import (
    init_db,
    get_latest_prices,
    get_price_history,
    get_all_labs,
    get_price_changes,
    get_scrape_log,
    save_scrape_results,
    add_favorite,
    remove_favorite,
    is_favorite,
    get_favorites,
    update_favorite_note,
    get_favorite_names,
    get_bundle_detail,
    save_bundle_custom_notes,
    get_all_bundle_details,
)
from scraper.exporter import export_to_excel, export_to_csv
from scraper.categorizer import classify_study, classify_all, get_category_counts, ALL_CATEGORIES
from scraper.scheduler_manager import (
    get_scheduler_status,
    start_scheduler,
    stop_scheduler,
    restart_scheduler,
    get_config as get_scheduler_config,
    save_config as save_scheduler_config,
)

# ── Configuración de página ────────────────────────────────────────────────────
st.set_page_config(
    page_title="Chopo Price Intelligence",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Estilos personalizados ─────────────────────────────────────────────────────
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 800;
        color: #1a5276;
        margin-bottom: 0;
    }
    .sub-header {
        font-size: 1rem;
        color: #7f8c8d;
        margin-top: 0;
    }
    .metric-card {
        background: #eaf2f8;
        border-radius: 10px;
        padding: 15px;
        border-left: 5px solid #1a5276;
    }
    .price-increase { color: #e74c3c; font-weight: bold; }
    .price-decrease { color: #27ae60; font-weight: bold; }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px 8px 0 0;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)


# ── Inicialización ─────────────────────────────────────────────────────────────
@st.cache_resource
def initialize():
    """Inicializa la BD y el scheduler en background."""
    init_db()
    try:
        from scraper.scheduler import get_background_scheduler
        scheduler = get_background_scheduler()
        if not scheduler.running:
            scheduler.start()
        return scheduler
    except Exception as e:
        logger.warning(f"Scheduler no iniciado: {e}")
        return None


@st.cache_data(ttl=300)  # Cache de 5 minutos
def load_data():
    """Carga los datos de precios desde la BD."""
    prices = get_latest_prices()
    labs = get_all_labs()
    changes = get_price_changes(days=30)
    scrape_log = get_scrape_log()
    return prices, labs, changes, scrape_log


def format_price(price):
    """Formatea un precio como moneda MXN."""
    if price is None or pd.isna(price):
        return "N/D"
    return f"${price:,.2f}"


# ── Header ─────────────────────────────────────────────────────────────────────
def render_header():
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown('<p class="main-header">🔬 Chopo Price Intelligence</p>', unsafe_allow_html=True)
        st.markdown(
            '<p class="sub-header">Análisis competitivo de precios de laboratorio · Mérida, Yucatán</p>',
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown("&nbsp;", unsafe_allow_html=True)
        is_admin = st.session_state.get("is_admin", False)
        if is_admin:
            _render_scrape_button()
        else:
            st.markdown(
                """
                <div style="text-align:right;padding-top:10px;">
                    <span style="background:#eaf2f8;color:#2471a3;padding:6px 14px;border-radius:20px;font-size:0.85rem;font-weight:600;border:1px solid #d4e6f1;">
                        👤 Modo Consulta
                    </span>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _log_path() -> Path:
    return Path(__file__).parent.parent / "logs" / "scrape_live.log"


def _pid_path() -> Path:
    return Path(__file__).parent.parent / "logs" / "scrape.pid"


def _get_running_scrape_pid() -> Optional[int]:
    """Retorna el PID del scrape si está actualmente activo, o None."""
    p_file = _pid_path()
    if not p_file.exists():
        return None
    try:
        import psutil
        pid = int(p_file.read_text(encoding="utf-8").strip())
        if psutil.pid_exists(pid):
            proc = psutil.Process(pid)
            if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
                return pid
    except Exception:
        pass
    # Si el archivo existe pero el proceso ya murió, limpiarlo
    try:
        p_file.unlink()
    except Exception:
        pass
    return None


def _render_scrape_button():
    """Botón de scrape con estado persistente en disco (soporta F5 y recargas)."""
    import time
    pid = _get_running_scrape_pid()

    if pid is not None:
        c_status, c_cancel = st.columns([3, 1])
        with c_status:
            st.warning(f"⏳ **Scraping en segundo plano (PID: {pid})**")
        with c_cancel:
            if st.button("🛑 Cancelar", type="secondary", use_container_width=True):
                _cancel_scrape(pid)
                st.rerun()

        _show_live_progress()
        time.sleep(2.5)
        st.rerun()
    else:
        _check_and_show_last_result()
        if st.button("🔄 Ejecutar Scrape Ahora", type="primary", use_container_width=True):
            _launch_scrape_background()
            st.rerun()


def _launch_scrape_background():
    """Lanza el scraper como proceso independiente en segundo plano."""
    import subprocess
    import sys
    import os

    lp = _log_path()
    lp.parent.mkdir(parents=True, exist_ok=True)
    log_file = open(lp, "w", encoding="utf-8", errors="replace")

    proc = subprocess.Popen(
        [sys.executable, str(Path(__file__).parent.parent / "main.py"), "scrape"],
        stdout=log_file,
        stderr=log_file,
        cwd=str(Path(__file__).parent.parent),
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    _pid_path().write_text(str(proc.pid), encoding="utf-8")


def _cancel_scrape(pid: int):
    """Cancela el proceso de scraping y sus subprocesos (Chromium)."""
    try:
        import psutil
        parent = psutil.Process(pid)
        for child in parent.children(recursive=True):
            try:
                child.kill()
            except Exception:
                pass
        parent.kill()
    except Exception:
        pass
    try:
        _pid_path().unlink()
    except Exception:
        pass
    st.info("Proceso de scrape cancelado.")


def _show_live_progress():
    """Lee el log en tiempo real y muestra métricas y barra de progreso."""
    lp = _log_path()
    if not lp.exists():
        st.info("Iniciando navegador Chromium...")
        return

    try:
        lines = lp.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return

    pages = sum(1 for l in lines if "Pagina " in l and "Acumulado:" in l)
    acum = 0
    for l in reversed(lines):
        if "Acumulado:" in l:
            try:
                acum = int(l.split("Acumulado:")[-1].strip())
            except Exception:
                pass
            break

    pct = min(1.0, max(0.0, pages / 55.0))
    st.progress(pct, text=f"Progreso del catálogo: {int(pct * 100)}% ({pages} de ~55 páginas)")

    c1, c2 = st.columns(2)
    c1.metric("Páginas completadas", f"{pages} / 55")
    c2.metric("Estudios recolectados", acum)

    recent = [l for l in lines if "|" in l or "Scrape" in l or "Completado" in l][-6:]
    with st.expander("📋 Log de ejecución en vivo", expanded=True):
        st.code("\n".join(recent) if recent else "Cargando navegador...", language=None)


def _check_and_show_last_result():
    """Muestra si el último scrape terminó con éxito."""
    lp = _log_path()
    if lp.exists():
        output = lp.read_text(encoding="utf-8", errors="replace")
        resumen = next(
            (l.strip() for l in output.splitlines() if "Total:" in l and "registros" in l),
            None,
        )
        if resumen and "showed_last_scrape" not in st.session_state:
            st.session_state.showed_last_scrape = True
            st.success(f"Último scrape finalizado: {resumen}")


# ── Sidebar ────────────────────────────────────────────────────────────────────
def render_sidebar(labs: list, prices: list) -> dict:
    """Renderiza la sidebar con filtros. Retorna filtros seleccionados."""
    st.sidebar.image(
        "https://www.chopo.com.mx/static/version1790298380/frontend/AgileThought/Chopo/es_MX/images/logo.svg",
        use_column_width=True,
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🔍 Filtros")

    # Filtro por laboratorio
    lab_names = ["Todos"] + [lab["lab_name"] for lab in labs]
    selected_lab = st.sidebar.selectbox("Laboratorio", lab_names)

    # Filtro por categoría (especialidad médica)
    selected_category = st.sidebar.selectbox("🏷️ Especialidad", ALL_CATEGORIES)

    # Filtro por texto en nombre de estudio
    search_text = st.sidebar.text_input("🔎 Buscar estudio", placeholder="ej: glucosa, biometría...")

    # Filtro por rango de precios
    df = pd.DataFrame(prices)
    min_price, max_price = 0.0, 10000.0
    if not df.empty and "price" in df.columns:
        valid = df["price"].dropna()
        if len(valid) > 0:
            min_price = float(valid.min())
            max_price = float(valid.max())

    price_range = st.sidebar.slider(
        "Rango de precio (MXN)",
        min_value=min_price,
        max_value=max_price,
        value=(min_price, max_price),
        format="$%.0f",
    )

    st.sidebar.markdown("---")
    is_admin = st.session_state.get("is_admin", False)
    if is_admin:
        st.sidebar.markdown("""
        <div style="background:#e8f8f5;border:1px solid #a3e4d7;padding:10px;border-radius:8px;margin-bottom:10px;">
            <span style="color:#117864;font-weight:bold;font-size:0.9rem;">👑 Modo Administrador</span><br/>
            <small style="color:#16a085;">Controles de scraping y configuración activos</small>
        </div>
        """, unsafe_allow_html=True)
        if st.sidebar.button("🔒 Salir de Modo Admin", key="btn_drop_admin", use_container_width=True):
            st.session_state["is_admin"] = False
            st.rerun()

        st.sidebar.markdown("### ⏰ Scheduler")
        st.sidebar.info("Actualización automática: **6:00 AM** diario\n(Hora Mérida, Yucatán)")
    else:
        st.sidebar.markdown("""
        <div style="background:#f4f6f7;border:1px solid #d5dbdb;padding:8px 10px;border-radius:8px;margin-bottom:10px;">
            <span style="color:#566573;font-weight:bold;font-size:0.85rem;">👤 Modo Consulta</span><br/>
            <small style="color:#7f8c8d;">Visualización de precios y análisis</small>
        </div>
        """, unsafe_allow_html=True)
        with st.sidebar.expander("🔑 ¿Eres Administrador?", expanded=False):
            with st.form("admin_unlock_form"):
                admin_key = st.text_input("Clave de Administrador", type="password", placeholder="Escribe clave...")
                if st.form_submit_button("🔓 Desbloquear", use_container_width=True):
                    import os
                    admin_pwd = "admin2026"
                    try:
                        if hasattr(st, "secrets") and "ADMIN_PASSWORD" in st.secrets:
                            admin_pwd = str(st.secrets["ADMIN_PASSWORD"])
                    except Exception:
                        pass
                    admin_pwd = os.getenv("ADMIN_PASSWORD", admin_pwd)
                    if admin_key == admin_pwd:
                        st.session_state["is_admin"] = True
                        st.toast("👑 ¡Modo Administrador activado!")
                        st.rerun()
                    else:
                        st.error("❌ Clave incorrecta")

    st.sidebar.markdown("---")
    if st.sidebar.button("🚪 Cerrar Sesión", use_container_width=True):
        st.session_state["authenticated"] = False
        st.session_state["is_admin"] = False
        st.rerun()

    return {
        "lab": selected_lab,
        "category": selected_category,
        "search": search_text,
        "price_min": price_range[0],
        "price_max": price_range[1],
    }


# ── Métricas KPI ───────────────────────────────────────────────────────────────
def render_kpis(prices: list, changes: list, scrape_log: list):
    df = pd.DataFrame(prices)

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("📋 Total Estudios", len(prices))
    with col2:
        if not df.empty and "price" in df.columns:
            avg = df["price"].mean()
            st.metric("💲 Precio Promedio", f"${avg:,.2f}" if pd.notna(avg) else "N/D")
        else:
            st.metric("💲 Precio Promedio", "N/D")
    with col3:
        if not df.empty and "price" in df.columns:
            mn = df["price"].min()
            st.metric("📉 Precio Mínimo", f"${mn:,.2f}" if pd.notna(mn) else "N/D")
        else:
            st.metric("📉 Precio Mínimo", "N/D")
    with col4:
        if not df.empty and "price" in df.columns:
            mx = df["price"].max()
            st.metric("📈 Precio Máximo", f"${mx:,.2f}" if pd.notna(mx) else "N/D")
        else:
            st.metric("📈 Precio Máximo", "N/D")
    with col5:
        st.metric("🔔 Cambios (30d)", len(changes))

    # Última actualización
    if scrape_log:
        last = scrape_log[0]
        st.caption(
            f"🕐 Última actualización: {last.get('scraped_at', 'N/D')} "
            f"| {last.get('studies_count', 0)} estudios | {last.get('lab_name', '')} {last.get('city', '')}"
        )


# ── Tab 1: Catálogo de Precios ─────────────────────────────────────────────────
def render_catalog_tab(prices: list, filters: dict):
    st.markdown("### 📋 Catálogo de Estudios y Precios")

    df = pd.DataFrame(prices)
    if df.empty:
        st.info("No hay datos de precios. Ejecuta un scrape desde el botón superior.")
        return

    # Agregar categoría a cada estudio
    if "category" not in df.columns:
        df["category"] = df["study_name"].apply(
            lambda n: classify_study(n) if pd.notna(n) else "Otros"
        )

    fav_names = get_favorite_names()

    # ── Filtros y Selector Directo de Estudio ──────────────────────────────────
    c_filt_fav, c_quick_sel = st.columns([2, 5])
    with c_filt_fav:
        only_favs = st.checkbox(f"⭐ Ver solo mis Favoritos ({len(fav_names)})", value=False, key="cat_only_favs")
    if only_favs:
        df = df[df["study_name"].isin(fav_names)]

    # ── Aplicar filtros del sidebar ───────────────────────────────────────────
    if filters.get("lab") and filters["lab"] != "Todos" and "lab_name" in df.columns:
        df = df[df["lab_name"] == filters["lab"]]

    if filters.get("category") and filters["category"] != "Todas" and "category" in df.columns:
        df = df[df["category"] == filters["category"]]

    if filters.get("search"):
        df = df[df["study_name"].str.contains(filters["search"], case=False, na=False)]

    if "price" in df.columns:
        mask = (df["price"].isna()) | (
            (df["price"] >= filters["price_min"]) & (df["price"] <= filters["price_max"])
        )
        df = df[mask]

    df = df.reset_index(drop=True)

    # Selector con autocompletado en el encabezado
    all_avail = sorted(df["study_name"].dropna().unique().tolist())
    with c_quick_sel:
        selected_from_picker = st.selectbox(
            "🔍 Busca o selecciona un estudio para ver su detalle y gestionar favorito:",
            options=["-- Escribe aquí el nombre de cualquier estudio para seleccionarlo --"] + all_avail,
            key="cat_quick_picker_box",
            help="Escribe cualquier parte del nombre (ej. glucosa, biometría, perfil) para seleccionarlo directamente sin buscarlo en la tabla."
        )

    # ── Conteo por categoría (mini badges) ────────────────────────────────────
    cat_counts = df["category"].value_counts().to_dict() if "category" in df.columns else {}
    badge_html = " ".join(
        f'<span style="background:#1a5276;color:white;padding:2px 8px;border-radius:10px;font-size:0.75rem;margin:2px">'
        f'{cat} ({cnt})</span>'
        for cat, cnt in sorted(cat_counts.items(), key=lambda x: -x[1])[:8]
    )
    st.markdown(
        f"Mostrando **{len(df)}** estudios &nbsp;|&nbsp; {badge_html}",
        unsafe_allow_html=True,
    )

    # ── Clic Rápido en Resultados de Búsqueda ──────────────────────────────────
    if filters.get("search") and 0 < len(df) <= 12:
        st.markdown("**⚡ Clic directo en cualquiera de estos resultados:**")
        pill_cols = st.columns(min(4, len(df)))
        for idx, (_, r_p) in enumerate(df.head(8).iterrows()):
            with pill_cols[idx % 4]:
                p_text = f"${r_p['price']:,.2f}" if pd.notna(r_p.get("price")) else ""
                is_f_pill = "⭐ " if r_p["study_name"] in fav_names else ""
                if st.button(f"{is_f_pill}{r_p['study_name'][:24]}\n{p_text}", key=f"pill_cat_{r_p['study_name']}", use_container_width=True):
                    st.session_state["catalog_active_study"] = r_p["study_name"]
                    st.rerun()

    # ── Tabla limpia (Sin columna de estrellas y sin índice numérico) ───────────
    display_cols = [c for c in ["study_name", "category", "price", "price_raw", "lab_name", "city", "scraped_at"]
                    if c in df.columns]
    df_display = df[display_cols].copy()
    col_rename = {
        "study_name": "Estudio",
        "category": "Especialidad",
        "price": "Precio",
        "price_raw": "Precio (texto)",
        "lab_name": "Laboratorio",
        "city": "Ciudad",
        "scraped_at": "Actualizado",
    }
    df_display = df_display.rename(columns={k: v for k, v in col_rename.items() if k in df_display.columns})

    selection_event = st.dataframe(
        df_display,
        use_container_width=True,
        height=400,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "Estudio": st.column_config.TextColumn("Estudio", width="large"),
            "Especialidad": st.column_config.TextColumn("Especialidad", width="medium"),
            "Precio": st.column_config.NumberColumn("Precio (MXN)", format="$%.2f", width="small"),
            "Actualizado": st.column_config.DatetimeColumn("Actualizado", width="small"),
        },
    )

    # ── Determinar estudio activo seleccionado ─────────────────────────────────
    active_study = None

    # 1. Si eligió del dropdown de autocompletado
    if selected_from_picker and selected_from_picker != "-- Escribe aquí el nombre de cualquier estudio para seleccionarlo --":
        active_study = selected_from_picker

    # 2. Si hizo clic en un botón rápido
    elif "catalog_active_study" in st.session_state and st.session_state["catalog_active_study"]:
        active_study = st.session_state["catalog_active_study"]

    # 3. Si seleccionó una fila en la tabla
    else:
        selected_rows = getattr(selection_event, "selection", None)
        if selected_rows and selected_rows.rows:
            sel_idx = selected_rows.rows[0]
            if sel_idx < len(df):
                active_study = df.iloc[sel_idx]["study_name"]

    # ── Panel de Detalle y Gestión de Favorito ──────────────────────────────────
    if active_study:
        m_rows = df[df["study_name"] == active_study]
        if not m_rows.empty:
            row = m_rows.iloc[0]
            st_name = row["study_name"]
            st_price = row.get("price")
            st_cat = row.get("category", "")
            is_f = st_name in fav_names
            p_str = f"${st_price:,.2f} MXN" if st_price else "Sin precio"

            st.markdown("---")
            c_ban_info, c_ban_btn = st.columns([4, 2])
            with c_ban_info:
                fav_status = "⭐ Ya está en tus Favoritos" if is_f else "☆ No está en Favoritos"
                st.info(f"📌 **Estudio Seleccionado:** **{st_name}** ({p_str}) | Especialidad: `{st_cat}` | **{fav_status}**")
            with c_ban_btn:
                if is_f:
                    if st.button("💛 Quitar de Favoritos", key=f"quick_del_{st_name}", use_container_width=True):
                        remove_favorite(st_name, row.get("lab_key", "chopo_yucatan"), row.get("branch"))
                        st.toast(f"'{st_name}' removido de favoritos")
                        st.rerun()
                else:
                    if st.button("⭐ MARCAR COMO FAVORITO", type="primary", key=f"quick_add_{st_name}", use_container_width=True):
                        add_favorite(st_name, row.get("lab_key", "chopo_yucatan"), row.get("branch"))
                        st.toast(f"⭐ '{st_name}' agregado a favoritos!")
                        st.rerun()

            _render_study_detail(row, df, fav_names)
    else:
        st.caption("💡 **Tip:** Escribe el nombre de cualquier estudio en el buscador superior o selecciona una fila para ver su análisis completo y gestionarlo.")



    # ── Botones de exportación ─────────────────────────────────────────────────
    st.markdown("---")
    col1, col2, col3 = st.columns([1, 1, 4])
    with col1:
        if st.button("📥 Exportar a Excel", use_container_width=True):
            filepath = export_to_excel(df.to_dict("records"))
            st.success(f"Excel guardado en: `{filepath}`")
    with col2:
        if st.button("📄 Exportar a CSV", use_container_width=True):
            filepath = export_to_csv(df.to_dict("records"))
            st.success(f"CSV guardado en: `{filepath}`")


def _render_study_detail(row: "pd.Series", df: "pd.DataFrame", fav_names: set):
    """
    Panel de detalle completo de un estudio clínico seleccionado.
    Muestra precio, categoría, comparación vs categoría, historial, y acción de favorito.
    """
    study_name = row.get("study_name", "")
    price       = row.get("price")
    category    = row.get("category", classify_study(study_name))
    lab_key     = row.get("lab_key", "chopo_yucatan")
    branch      = row.get("branch", "")
    lab_name    = row.get("lab_name", "")
    url         = row.get("url", "")
    scraped_at  = str(row.get("scraped_at", ""))[:16]

    st.markdown("---")
    st.markdown(f"## 🔬 {study_name}")

    # ── Fila 1: métricas principales ──────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("💲 Precio Actual", f"${price:,.2f}" if price else "Sin precio")
    with c2:
        st.metric("🏷️ Especialidad", category)
    with c3:
        # Comparación vs promedio de la categoría
        cat_prices = df[(df["category"] == category) & df["price"].notna()]["price"]
        if len(cat_prices) > 0 and price:
            cat_avg = cat_prices.mean()
            diff_pct = ((price - cat_avg) / cat_avg) * 100
            st.metric(
                "📊 vs Promedio Categoría",
                f"${cat_avg:,.2f}",
                delta=f"{diff_pct:+.1f}%",
                delta_color="inverse",
            )
        else:
            st.metric("📊 vs Promedio Categoría", "N/D")
    with c4:
        # Posición dentro de la categoría
        if price and len(cat_prices) > 0:
            rank = (cat_prices < price).sum() + 1
            st.metric("📈 Posición en Categoría", f"#{rank} de {len(cat_prices)}")
        else:
            st.metric("📈 Posición en Categoría", "N/D")

    # ── Fila 2: info + acciones ────────────────────────────────────────────────
    col_info, col_actions = st.columns([3, 1])

    with col_info:
        st.markdown(f"**Laboratorio:** {lab_name} &nbsp;|&nbsp; **Sucursal:** {branch or 'N/A'} &nbsp;|&nbsp; **Última actualización:** {scraped_at}")
        if url:
            st.markdown(f"🔗 [Ver en sitio web de Chopo]({url})")

        # Distribución de la categoría
        if len(cat_prices) > 1:
            fig_dist = px.histogram(
                cat_prices,
                nbins=15,
                title=f"Distribución de precios en {category}",
                labels={"value": "Precio (MXN)", "count": "Estudios"},
                color_discrete_sequence=["#1a5276"],
            )
            if price:
                fig_dist.add_vline(
                    x=price,
                    line_dash="dash",
                    line_color="red",
                    annotation_text=f"Este estudio: ${price:,.2f}",
                    annotation_position="top right",
                )
            fig_dist.update_layout(height=220, margin=dict(t=40, b=20, l=20, r=20), showlegend=False)
            st.plotly_chart(fig_dist, use_container_width=True)

    with col_actions:
        st.markdown("**Acciones**")
        is_fav = study_name in fav_names

        if is_fav:
            if st.button("💛 Quitar de Favoritos", key=f"detail_remove_{study_name}", use_container_width=True):
                remove_favorite(study_name, lab_key, branch or None)
                st.success("Eliminado de favoritos")
                st.rerun()
        else:
            if st.button("⭐ Agregar a Favoritos", key=f"detail_add_{study_name}", type="primary", use_container_width=True):
                add_favorite(study_name, lab_key, branch or None)
                st.success("¡Agregado a favoritos!")
                st.rerun()

        st.markdown("---")
        # Estudios similares en la misma categoría
        similar = df[(df["category"] == category) & (df["study_name"] != study_name) & df["price"].notna()]
        similar = similar.nsmallest(5, "price")[["study_name", "price"]]
        if not similar.empty:
            st.markdown("**Similares más baratos:**")
            for _, s in similar.iterrows():
                st.caption(f"• {s['study_name'][:35]}: **${s['price']:,.2f}**")

    # ── Historial de precio ────────────────────────────────────────────────────
    try:
        history = get_price_history(study_name=study_name)
        if history and len(history) > 1:
            df_h = pd.DataFrame(history)
            df_h["scraped_at"] = pd.to_datetime(df_h["scraped_at"])
            df_h = df_h.sort_values("scraped_at")
            fig_hist = px.line(
                df_h, x="scraped_at", y="price",
                title=f"Historial de precio — {study_name[:60]}",
                markers=True,
                color_discrete_sequence=["#1a5276"],
            )
            fig_hist.update_layout(
                height=250,
                margin=dict(t=40, b=20, l=20, r=20),
                xaxis_title="Fecha",
                yaxis_title="Precio (MXN)",
            )
            st.plotly_chart(fig_hist, use_container_width=True)
        else:
            st.caption("📈 El gráfico de historial aparecerá después del segundo scrape diario.")
    except Exception:
        pass



# ── Tab 2: Análisis de Precios ─────────────────────────────────────────────────
def render_analysis_tab(prices: list, filters: dict):
    st.markdown("### 📊 Análisis de Distribución de Precios")

    df = pd.DataFrame(prices)
    if df.empty or "price" not in df.columns:
        st.info("Sin datos de precios para analizar.")
        return

    df_valid = df.dropna(subset=["price"]).copy()

    col1, col2 = st.columns(2)

    with col1:
        # Histograma de distribución de precios
        fig_hist = px.histogram(
            df_valid,
            x="price",
            nbins=30,
            title="Distribución de Precios",
            labels={"price": "Precio (MXN)", "count": "Cantidad de Estudios"},
            color_discrete_sequence=["#1a5276"],
        )
        fig_hist.update_layout(bargap=0.1)
        st.plotly_chart(fig_hist, use_container_width=True)

    with col2:
        # Top 15 estudios más caros
        top15 = df_valid.nlargest(15, "price")[["study_name", "price", "lab_name"]]
        fig_top = px.bar(
            top15,
            x="price",
            y="study_name",
            orientation="h",
            title="Top 15 Estudios Más Caros",
            labels={"price": "Precio (MXN)", "study_name": "Estudio"},
            color="price",
            color_continuous_scale="Blues",
        )
        fig_top.update_layout(yaxis={"categoryorder": "total ascending"}, showlegend=False)
        st.plotly_chart(fig_top, use_container_width=True)

    col3, col4 = st.columns(2)

    with col3:
        # Box plot por laboratorio
        if "lab_name" in df_valid.columns and df_valid["lab_name"].nunique() > 1:
            fig_box = px.box(
                df_valid,
                x="lab_name",
                y="price",
                title="Comparativa de Precios por Laboratorio",
                labels={"price": "Precio (MXN)", "lab_name": "Laboratorio"},
                color="lab_name",
            )
            st.plotly_chart(fig_box, use_container_width=True)
        else:
            # Scatter de precio vs rango
            fig_scatter = px.scatter(
                df_valid.sort_values("price"),
                x=range(len(df_valid)),
                y="price",
                hover_name="study_name",
                title="Precios por Estudio (ordenado)",
                labels={"y": "Precio (MXN)", "x": "Índice de Estudio"},
                color_discrete_sequence=["#1a5276"],
            )
            st.plotly_chart(fig_scatter, use_container_width=True)

    with col4:
        # Rangos de precio (segmentación)
        bins = [0, 100, 300, 500, 1000, 3000, float("inf")]
        labels_b = ["$0-100", "$100-300", "$300-500", "$500-1K", "$1K-3K", ">$3K"]
        df_valid["rango"] = pd.cut(df_valid["price"], bins=bins, labels=labels_b)
        rango_counts = df_valid["rango"].value_counts().sort_index()
        fig_pie = px.pie(
            values=rango_counts.values,
            names=rango_counts.index,
            title="Estudios por Rango de Precio",
            color_discrete_sequence=px.colors.sequential.Blues_r,
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    # ── Análisis por Categoría / Especialidad ──────────────────────────────────
    st.markdown("---")
    st.markdown("#### 🏷️ Análisis por Especialidad Médica")

    # Agregar categoría si no existe
    if "category" not in df_valid.columns:
        df_valid = df_valid.copy()
        df_valid["category"] = df_valid["study_name"].apply(
            lambda n: classify_study(n) if pd.notna(n) else "Otros"
        )

    col5, col6 = st.columns(2)

    with col5:
        cat_counts = df_valid["category"].value_counts().reset_index()
        cat_counts.columns = ["Especialidad", "Estudios"]
        fig_cat = px.bar(
            cat_counts,
            x="Estudios",
            y="Especialidad",
            orientation="h",
            title="Cantidad de Estudios por Especialidad",
            color="Estudios",
            color_continuous_scale="Blues",
        )
        fig_cat.update_layout(yaxis={"categoryorder": "total ascending"}, showlegend=False)
        st.plotly_chart(fig_cat, use_container_width=True)

    with col6:
        cat_avg = df_valid.groupby("category")["price"].mean().reset_index()
        cat_avg.columns = ["Especialidad", "Precio Promedio"]
        cat_avg = cat_avg.sort_values("Precio Promedio", ascending=True)
        fig_avg = px.bar(
            cat_avg,
            x="Precio Promedio",
            y="Especialidad",
            orientation="h",
            title="Precio Promedio por Especialidad",
            color="Precio Promedio",
            color_continuous_scale="Oranges",
        )
        fig_avg.update_layout(showlegend=False)
        st.plotly_chart(fig_avg, use_container_width=True)

    # Box plot de precios por especialidad (top 8 con más estudios)
    top_cats = df_valid["category"].value_counts().head(8).index.tolist()
    df_top = df_valid[df_valid["category"].isin(top_cats)]
    if not df_top.empty:
        fig_box_cat = px.box(
            df_top,
            x="category",
            y="price",
            title="Distribución de Precios por Especialidad (Top 8)",
            labels={"category": "Especialidad", "price": "Precio (MXN)"},
            color="category",
        )
        fig_box_cat.update_layout(showlegend=False, xaxis_tickangle=-30)
        st.plotly_chart(fig_box_cat, use_container_width=True)


# ── Tab 3: Historial y Tendencias ─────────────────────────────────────────────
def render_history_tab(labs: list):
    st.markdown("### 📈 Historial de Precios por Estudio")

    if not labs:
        st.info("No hay laboratorios registrados.")
        return

    col1, col2 = st.columns(2)
    with col1:
        selected_lab = st.selectbox(
            "Laboratorio",
            [lab["lab_key"] for lab in labs],
            format_func=lambda x: next((l["lab_name"] for l in labs if l["lab_key"] == x), x),
        )
    with col2:
        study_name = st.text_input("Nombre del estudio", placeholder="ej: Glucosa en Suero")

    if st.button("📊 Ver Historial", type="secondary") and study_name:
        history = get_price_history(study_name, selected_lab)
        if history:
            df_h = pd.DataFrame(history)
            df_h["scraped_at"] = pd.to_datetime(df_h["scraped_at"])

            fig = px.line(
                df_h,
                x="scraped_at",
                y="price",
                markers=True,
                title=f"Historial de Precio: {study_name}",
                labels={"scraped_at": "Fecha", "price": "Precio (MXN)"},
                color_discrete_sequence=["#1a5276"],
            )
            fig.update_layout(hovermode="x unified")
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(df_h, use_container_width=True)
        else:
            st.warning(f"No hay historial para '{study_name}'. Ejecuta varios scrapes a lo largo del tiempo.")


# ── Tab 4: Cambios de Precio ───────────────────────────────────────────────────
def render_changes_tab(changes: list):
    st.markdown("### 🔔 Cambios de Precio Detectados (últimos 30 días)")

    if not changes:
        st.success("✅ No se detectaron cambios de precio en los últimos 30 días.")
        return

    df = pd.DataFrame(changes)

    # Indicadores de cambio
    increases = df[df.get("change_pct", pd.Series()) > 0] if "change_pct" in df.columns else pd.DataFrame()
    decreases = df[df.get("change_pct", pd.Series()) < 0] if "change_pct" in df.columns else pd.DataFrame()

    col1, col2 = st.columns(2)
    with col1:
        st.metric("📈 Subidas de precio", len(increases), delta=f"+{len(increases)}", delta_color="inverse")
    with col2:
        st.metric("📉 Bajadas de precio", len(decreases), delta=f"-{len(decreases)}", delta_color="normal")

    if "change_pct" in df.columns:
        fig = px.bar(
            df.head(30),
            x="study_name",
            y="change_pct",
            color="change_pct",
            color_continuous_scale=["#27ae60", "#e74c3c"],
            title="Variaciones de Precio por Estudio",
            labels={"study_name": "Estudio", "change_pct": "Variación (%)"},
        )
        fig.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)

    st.dataframe(df, use_container_width=True)


# ── Tab 0: Favoritos ───────────────────────────────────────────────────────────
def render_favorites_tab(prices: list):
    st.markdown("### ⭐ Estudios Favoritos")
    st.caption("Estudios que monitoreas de cerca. Agrégalos desde el tab Catálogo.")

    favorites = get_favorites()

    if not favorites:
        st.info(
            "Aún no tienes favoritos. Ve al tab **Catálogo**, busca un estudio "
            "y haz clic en **⭐ Agregar a Favoritos**."
        )
        return

    # ── Métricas rápidas ──────────────────────────────────────────────────────
    total_favs = len(favorites)
    with_price  = [f for f in favorites if f.get("current_price")]
    rising      = [f for f in with_price if (f.get("price_change") or 0) > 0]
    falling     = [f for f in with_price if (f.get("price_change") or 0) < 0]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total favoritos", total_favs)
    c2.metric("Con precio activo", len(with_price))
    c3.metric("Con precio subido ▲", len(rising))
    c4.metric("Con precio bajado ▼", len(falling))
    st.markdown("---")

    # ── Tabla de favoritos ────────────────────────────────────────────────────
    for fav in favorites:
        name         = fav["study_name"]
        price        = fav.get("current_price")
        change       = fav.get("price_change")
        change_pct   = fav.get("price_change_pct")
        note         = fav.get("note") or ""
        threshold    = fav.get("alert_threshold")
        lab_key      = fav["lab_key"]
        branch       = fav.get("branch", "")

        # Color del delta
        if change and change > 0:
            delta_str = f"+${change:.2f} (+{change_pct:.1f}%)"
            delta_color = "inverse"
        elif change and change < 0:
            delta_str = f"-${abs(change):.2f} ({change_pct:.1f}%)"
            delta_color = "normal"
        else:
            delta_str = "Sin cambios"
            delta_color = "off"

        with st.expander(f"⭐ {name}", expanded=False):
            col_price, col_info, col_actions = st.columns([2, 3, 2])

            with col_price:
                if price:
                    st.metric(
                        label="Precio actual",
                        value=f"${price:,.2f}",
                        delta=delta_str if change else None,
                        delta_color=delta_color,
                    )
                else:
                    st.metric("Precio actual", "No disponible")

                if threshold and price:
                    if price > threshold:
                        st.warning(f"⚠️ Precio supera umbral de ${threshold:,.2f}")
                    else:
                        st.success(f"✅ Precio bajo umbral de ${threshold:,.2f}")

            with col_info:
                st.markdown(f"**Laboratorio:** {fav.get('lab_name', lab_key)}")
                st.markdown(f"**Sucursal:** {branch or 'N/A'}")
                st.markdown(f"**Agregado:** {fav.get('created_at', '')[:10]}")

                # Editar nota
                new_note = st.text_input(
                    "Nota personal",
                    value=note,
                    key=f"note_{name}",
                    placeholder="Ej: Para paciente X, comparar con Salud Digna",
                )
                new_threshold = st.number_input(
                    "Alerta si precio supera ($)",
                    value=float(threshold) if threshold else 0.0,
                    min_value=0.0,
                    step=10.0,
                    key=f"thr_{name}",
                )
                if st.button("Guardar nota", key=f"save_{name}"):
                    update_favorite_note(
                        name, lab_key,
                        note=new_note or None,
                        alert_threshold=new_threshold if new_threshold > 0 else None,
                    )
                    st.success("Guardado")
                    st.rerun()

            with col_actions:
                if st.button("🗑️ Quitar de favoritos", key=f"del_{name}", type="secondary"):
                    remove_favorite(name, lab_key, branch or None)
                    st.success(f"'{name}' eliminado de favoritos")
                    st.rerun()

            # Mini historial de precio
            try:
                history = get_price_history(study_name=name)
                if history and len(history) > 1:
                    df_h = pd.DataFrame(history)
                    df_h["scraped_at"] = pd.to_datetime(df_h["scraped_at"])
                    df_h = df_h.sort_values("scraped_at")
                    fig = px.line(
                        df_h,
                        x="scraped_at",
                        y="price",
                        title=f"Historial de precio: {name[:50]}",
                        markers=True,
                        color_discrete_sequence=["#f39c12"],
                    )
                    fig.update_layout(
                        height=250,
                        margin=dict(t=40, b=20, l=20, r=20),
                        xaxis_title="Fecha",
                        yaxis_title="Precio (MXN)",
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.caption("Historial disponible después del segundo scrape diario.")
            except Exception:
                pass

    st.markdown("---")
    st.caption(f"Total: {total_favs} estudios en seguimiento")


# ── Tab: Descuentos & Promociones ─────────────────────────────────────────────
def render_discounts_tab(prices: list):
    st.markdown("### 🏷️ Detector de Descuentos & Promociones Chopo")
    st.caption("Compara el precio de mostrador (lista) vs el precio con descuento web en Chopo Mérida Altabrisa.")

    df = pd.DataFrame(prices)
    if df.empty or "price" not in df.columns:
        st.info("No hay datos de precios disponibles.")
        return

    if "category" not in df.columns:
        df["category"] = df["study_name"].apply(lambda n: classify_study(n) if pd.notna(n) else "Otros")

    df_valid = df.dropna(subset=["price"]).copy()

    def _calc_discount_row(row):
        p = float(row["price"])
        orig = row.get("price_original")
        if pd.notna(orig) and float(orig) > p:
            list_p = float(orig)
            saving = list_p - p
            pct = (saving / list_p) * 100.0
            is_est = False
        else:
            list_p = round(p / 0.90, 2)
            saving = round(list_p - p, 2)
            pct = 10.0
            is_est = True
        return pd.Series([list_p, saving, pct, is_est], index=["list_price", "saving", "discount_pct", "is_estimated"])

    disc_cols = df_valid.apply(_calc_discount_row, axis=1)
    df_valid = pd.concat([df_valid, disc_cols], axis=1)

    # Métricas
    col1, col2, col3, col4 = st.columns(4)
    total_disc = len(df_valid[df_valid["saving"] > 0])
    avg_saving = df_valid["saving"].mean()
    max_saving = df_valid["saving"].max()
    max_pct = df_valid["discount_pct"].max()

    with col1:
        st.metric("🏷️ Estudios en Promoción", f"{total_disc:,}")
    with col2:
        st.metric("💰 Ahorro Promedio", f"${avg_saving:,.2f} MXN")
    with col3:
        st.metric("🔥 Descuento Máximo", f"{max_pct:.1f}%")
    with col4:
        st.metric("💎 Mayor Ahorro en Pesos", f"${max_saving:,.2f} MXN")

    st.markdown("---")

    # Filtros
    f1, f2, f3 = st.columns([2, 2, 3])
    with f1:
        cat_filter = st.selectbox("Especialidad", ["Todas"] + sorted(df_valid["category"].unique().tolist()), key="disc_cat")
    with f2:
        min_disc = st.slider("Ahorro mínimo en pesos ($)", 0, int(max(100, max_saving)), 0, step=25, key="disc_min")
    with f3:
        search_kw = st.text_input("Buscar estudio en promoción", placeholder="ej. perfil, check, glucosa, química...", key="disc_search")

    filtered = df_valid.copy()
    if cat_filter != "Todas":
        filtered = filtered[filtered["category"] == cat_filter]
    if min_disc > 0:
        filtered = filtered[filtered["saving"] >= min_disc]
    if search_kw:
        filtered = filtered[filtered["study_name"].str.contains(search_kw, case=False, na=False)]

    filtered = filtered.sort_values("saving", ascending=False).reset_index(drop=True)
    st.markdown(f"Mostrando **{len(filtered)}** estudios con descuento:")

    disp_df = filtered[["study_name", "category", "list_price", "price", "saving", "discount_pct"]].copy()
    disp_df.columns = ["Estudio", "Especialidad", "Precio Lista (Mostrador)", "Precio Web (Final)", "Ahorro ($)", "Descuento (%)"]

    st.dataframe(
        disp_df,
        use_container_width=True,
        height=380,
        column_config={
            "Precio Lista (Mostrador)": st.column_config.NumberColumn(format="$%.2f"),
            "Precio Web (Final)": st.column_config.NumberColumn(format="$%.2f"),
            "Ahorro ($)": st.column_config.NumberColumn(format="$%.2f"),
            "Descuento (%)": st.column_config.NumberColumn(format="%.1f%%"),
        },
    )

    top12 = filtered.head(12)
    if not top12.empty:
        c_g1, c_g2 = st.columns(2)
        with c_g1:
            fig_bar = px.bar(
                top12,
                x="saving",
                y="study_name",
                orientation="h",
                title="Top Estudios con Mayor Ahorro en Pesos ($)",
                labels={"saving": "Ahorro (MXN)", "study_name": "Estudio"},
                color="saving",
                color_continuous_scale="Greens",
            )
            fig_bar.update_layout(yaxis={"categoryorder": "total ascending"}, showlegend=False)
            st.plotly_chart(fig_bar, use_container_width=True)

        with c_g2:
            cat_sav = filtered.groupby("category")["saving"].mean().reset_index()
            cat_sav = cat_sav.sort_values("saving", ascending=False).head(10)
            fig_cat_sav = px.bar(
                cat_sav,
                x="saving",
                y="category",
                orientation="h",
                title="Ahorro Promedio por Especialidad Médica ($)",
                labels={"saving": "Ahorro Promedio (MXN)", "category": "Especialidad"},
                color="saving",
                color_continuous_scale="Teal",
            )
            fig_cat_sav.update_layout(yaxis={"categoryorder": "total ascending"}, showlegend=False)
            st.plotly_chart(fig_cat_sav, use_container_width=True)


# ── Helpers para Comparador de Paquetes & Estrategia ──────────────────────────
def _normalize_str(text: str) -> str:
    """Normaliza texto eliminando acentos y convirtiendo a mayúsculas para búsquedas robustas."""
    if not text:
        return ""
    return unicodedata.normalize("NFKD", str(text)).encode("ASCII", "ignore").decode("utf-8").upper()


def _is_bundle_study(name: str) -> bool:
    """Identifica si un estudio es un paquete, perfil, panel o check-up multidimensional."""
    if not isinstance(name, str):
        return False
    norm_n = _normalize_str(name)
    if "PERFILOGRAFIA" in norm_n:
        return False
    keywords = ["CHECK UP", "CHECKUP", "PERFIL", "PAQUETE", "PANEL", "INTEGRAL", "PREVENCION", "PREVENC"]
    return any(k in norm_n for k in keywords)


def _get_bundle_segment(name: str) -> str:
    """Clasifica los paquetes de Chopo en segmentos clínicos para análisis de mercado."""
    n = _normalize_str(name)
    if any(k in n for k in ["TIROID", "HORMON", "ANDROGEN", "TESTOSTERON"]):
        return "🩸 Tiroideo & Hormonal"
    if any(k in n for k in ["GLUCOSA", "DIABETES", "LIPID", "LIPOID", "TRIGLICERID", "COLESTEROL", "PREDIABETES"]):
        return "🥗 Diabetes & Metabólico"
    if any(k in n for k in ["PRENATAL", "EMBARAZO", "FEMENIN", "MUJER", "MAMA", "OVARIO", "TORCH", "CLIMATERIO"]):
        return "🤰 Salud Femenina & Prenatal"
    if any(k in n for k in ["PROSTAT", "HOMBRE", "MASCULIN"]):
        return "👨 Próstata & Masculino"
    if any(k in n for k in ["SEXUAL", "TRANSMIS", "HEPATITIS", "COVID", "RESPIRATORI", "VIRAL", "VIH", "SIFILIS"]):
        return "🦠 Infecciosas & ETS"
    if any(k in n for k in ["RENAL", "HEPATIC", "TRANSAMINAS", "ACIDO URICO"]):
        return "🧪 Renal & Hepático"
    if any(k in n for k in ["CANCER", "TUMOR", "BRCA", "ALERGEN", "FIBROTEST", "INMUNOHISTO"]):
        return "🧬 Oncología & Especialidades"
    if any(k in n for k in ["REUMAT", "AUTOINMUN"]):
        return "🦴 Reumatología & Autoinmune"
    if any(k in n for k in ["QUIMICA", "ELEMENTOS", "PREOPERATORIO", "DEPORTISTA"]):
        return "🧪 Químicas Integrales & Preop"
    if any(k in n for k in ["CHECK", "PREVENCI", "SALUDABLE", "REGRESO A CLASES", "CUIDA TU CORAZ", "SU SALUD"]):
        return "🩺 Check-ups & Preventivos"
    return "📦 Otros Perfiles"


def _generate_commercial_proposal_excel(
    clinic_name: str,
    client_name: str,
    package_name: str,
    items: list[dict],
    total_chopo: float,
    total_our: float,
    savings: float,
    savings_pct: float,
    benefits: list[str],
) -> bytes:
    """Genera en memoria un archivo Excel formateado profesionalmente para propuestas comerciales."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        wb = writer.book
        ws = wb.add_worksheet("Propuesta Comercial")

        fmt_title = wb.add_format({"bold": True, "font_size": 15, "font_color": "#1a5276"})
        fmt_sub = wb.add_format({"italic": True, "font_size": 10, "font_color": "#555555"})
        fmt_hdr = wb.add_format({
            "bold": True, "font_color": "white", "bg_color": "#1a5276",
            "border": 1, "align": "center", "valign": "vcenter",
        })
        fmt_curr = wb.add_format({"num_format": "$#,##0.00", "border": 1})
        fmt_curr_bold = wb.add_format({"bold": True, "num_format": "$#,##0.00", "border": 1, "bg_color": "#d4efdf"})
        fmt_pct = wb.add_format({"num_format": '0.0"%"', "border": 1})
        fmt_pct_bold = wb.add_format({"bold": True, "num_format": '0.0"%"', "border": 1, "bg_color": "#d4efdf"})
        fmt_cell = wb.add_format({"border": 1})
        fmt_total_lbl = wb.add_format({"bold": True, "border": 1, "bg_color": "#eaeded"})
        fmt_sec_hdr = wb.add_format({"bold": True, "font_size": 12, "font_color": "#1a5276"})
        fmt_benefit = wb.add_format({"font_color": "#196f3d", "font_size": 10})

        ws.write("A1", "PROPUESTA COMERCIAL COMPETITIVA", fmt_title)
        ws.write("A2", f"Laboratorio emisor: {clinic_name}  |  Fecha: {datetime.now().strftime('%d/%m/%Y')}", fmt_sub)
        ws.write("A3", f"Presentado para: {client_name}  |  Paquete: {package_name}", fmt_sub)

        headers = ["Concepto / Análisis Incluido", "Precio Chopo (Referencia)", f"Precio Especial {clinic_name}", "Ahorro al Cliente ($)", "Ventaja (%)"]
        for col_idx, h in enumerate(headers):
            ws.write(4, col_idx, h, fmt_hdr)

        row_idx = 5
        for it in items:
            ws.write(row_idx, 0, it["name"], fmt_cell)
            ws.write(row_idx, 1, it["chopo_price"], fmt_curr)
            ws.write(row_idx, 2, it["our_price"], fmt_curr)
            ws.write(row_idx, 3, it["savings"], fmt_curr)
            ws.write(row_idx, 4, it["savings_pct"] / 100.0, fmt_pct)
            row_idx += 1

        ws.write(row_idx, 0, "TOTAL PAQUETE", fmt_total_lbl)
        ws.write(row_idx, 1, total_chopo, fmt_curr_bold)
        ws.write(row_idx, 2, total_our, fmt_curr_bold)
        ws.write(row_idx, 3, savings, fmt_curr_bold)
        ws.write(row_idx, 4, savings_pct / 100.0, fmt_pct_bold)

        row_idx += 2
        ws.write(row_idx, 0, "VALOR AGREGADO Y BENEFICIOS EXCLUSIVOS:", fmt_sec_hdr)
        row_idx += 1
        for b in benefits:
            ws.write(row_idx, 0, f"  ✓  {b}", fmt_benefit)
            row_idx += 1

        ws.set_column(0, 0, 48)
        ws.set_column(1, 4, 25)

    return output.getvalue()


# ── Tab: Paquetes & Estrategia Competitiva ────────────────────────────────────
def render_quotation_tab(prices: list):
    st.markdown("### 💼 Paquetes & Estrategia Competitiva vs Chopo")
    st.caption("Herramienta de inteligencia de precios para tu clínica: analiza los paquetes oficiales de Chopo, modela tu estrategia de precios, calcula tus márgenes y genera propuestas comerciales B2B.")

    df = pd.DataFrame(prices)
    if df.empty or "study_name" not in df.columns:
        st.info("No hay catálogo disponible para cotizar.")
        return

    if "category" not in df.columns:
        df["category"] = df["study_name"].apply(lambda n: classify_study(n) if pd.notna(n) else "Otros")

    # Identificar y enriquecer paquetes
    df["is_bundle"] = df["study_name"].apply(_is_bundle_study)
    df["bundle_segment"] = df["study_name"].apply(_get_bundle_segment)

    def _calc_row_list(row):
        p = float(row.get("price") or 0.0)
        orig = row.get("price_original")
        if pd.notna(orig) and float(orig) > p:
            lp = float(orig)
            disc = ((lp - p) / lp) * 100.0
        else:
            lp = round(p / 0.90, 2)
            disc = 10.0
        return pd.Series([lp, disc], index=["list_price", "discount_pct"])

    df_valid_p = df.dropna(subset=["price"]).copy()
    disc_calc = df_valid_p.apply(_calc_row_list, axis=1)
    df = df.join(disc_calc)
    df["list_price"] = df["list_price"].fillna(df["price"])
    df["discount_pct"] = df["discount_pct"].fillna(0.0)

    # Estado de sesión
    if "quote_selected" not in st.session_state:
        st.session_state.quote_selected = []
    if "our_selling_price" not in st.session_state:
        st.session_state.our_selling_price = 0.0
    if "our_internal_cost" not in st.session_state:
        st.session_state.our_internal_cost = 0.0
    if "our_package_name" not in st.session_state:
        st.session_state.our_package_name = "Check-Up Clínico Preventivo"
    if "active_chopo_bundle" not in st.session_state:
        st.session_state.active_chopo_bundle = None
    if "sim_mode" not in st.session_state:
        st.session_state.sim_mode = "Armar a la carta (Suma de estudios)"

    subtab1, subtab2, subtab3 = st.tabs([
        "📦 Paquetes Oficiales Chopo (152)",
        "🎯 Simulador de Estrategia vs Chopo",
        "📄 Propuesta Comercial & Comparativa B2B",
    ])

    # ═══════════════════════════════════════════════════════════════════════════
    # SUBTAB 1: Explorador de Paquetes Oficiales Chopo
    # ═══════════════════════════════════════════════════════════════════════════
    with subtab1:
        st.markdown("#### 📦 Catálogo de Paquetes, Perfiles y Check-ups Oficiales de Chopo")
        st.caption("Chopo ya comercializa estos paquetes predefinidos en Mérida. Conoce sus precios de lista, precios web con descuento y úsalos como referencia para competir.")

        df_bundles = df[df["is_bundle"] & df["price"].notna()].copy()
        df_bundles = df_bundles.sort_values("price", ascending=True).reset_index(drop=True)

        # Métricas de paquetes
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("Total Paquetes Chopo", f"{len(df_bundles):,}")
        with m2:
            st.metric("Precio Promedio", f"${df_bundles['price'].mean():,.2f} MXN")
        with m3:
            st.metric("Paquete Más Económico", f"${df_bundles['price'].min():,.2f} MXN")
        with m4:
            st.metric("Paquete Más Completo", f"${df_bundles['price'].max():,.2f} MXN")

        st.markdown("---")

        # Filtros
        f_c1, f_c2, f_c3 = st.columns([3, 2, 3])
        with f_c1:
            segments = ["Todos"] + sorted(df_bundles["bundle_segment"].unique().tolist())
            selected_segment = st.selectbox("Segmento Clínico:", segments, key="bundle_seg_filter")
        with f_c2:
            max_p = int(df_bundles["price"].max())
            price_limit = st.slider("Precio Máximo ($ MXN):", 100, max_p, max_p, step=250, key="bundle_price_slider")
        with f_c3:
            search_bundle = st.text_input("Buscar paquete por nombre:", placeholder="ej. Tiroideo, Mujer, 45 elementos, Check up...", key="bundle_search_kw")

        filtered_b = df_bundles.copy()
        if selected_segment != "Todos":
            filtered_b = filtered_b[filtered_b["bundle_segment"] == selected_segment]
        if price_limit < max_p:
            filtered_b = filtered_b[filtered_b["price"] <= price_limit]
        if search_bundle:
            norm_kw = _normalize_str(search_bundle)
            filtered_b = filtered_b[filtered_b["study_name"].apply(lambda n: norm_kw in _normalize_str(n))]

        # Selector directo con autocompletado para paquetes
        pkg_options = ["-- Busca o escribe aquí el nombre de cualquier paquete --"] + sorted(filtered_b["study_name"].tolist())
        selected_pkg_from_dropdown = st.selectbox(
            "🔍 Busca o selecciona un paquete para ver su desglose de estudios:",
            options=pkg_options,
            key="bundle_dropdown_picker_field",
            help="Escribe el nombre de cualquier paquete para ver qué estudios incluye según Chopo."
        )

        st.markdown(f"Mostrando **{len(filtered_b)}** paquetes y perfiles de Chopo:")

        disp_b = filtered_b[["study_name", "bundle_segment", "price", "list_price", "discount_pct", "url"]].copy()
        disp_b.columns = ["Paquete / Perfil Chopo", "Segmento", "Precio Web Chopo", "Precio Mostrador (Lista)", "Descuento Chopo (%)", "Enlace"]

        event_b = st.dataframe(
            disp_b,
            use_container_width=True,
            height=360,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            column_config={
                "Paquete / Perfil Chopo": st.column_config.TextColumn("Paquete / Perfil Chopo", width="large"),
                "Segmento": st.column_config.TextColumn("Segmento", width="medium"),
                "Precio Web Chopo": st.column_config.NumberColumn(format="$%.2f", width="small"),
                "Precio Mostrador (Lista)": st.column_config.NumberColumn(format="$%.2f", width="small"),
                "Descuento Chopo (%)": st.column_config.NumberColumn(format="%.1f%%", width="small"),
                "Enlace": st.column_config.LinkColumn("Enlace Web", width="small"),
            }
        )

        # Determinar paquete seleccionado (por dropdown o por clic en tabla)
        active_b_name = None
        if selected_pkg_from_dropdown and selected_pkg_from_dropdown != "-- Busca o escribe aquí el nombre de cualquier paquete --":
            active_b_name = selected_pkg_from_dropdown
        else:
            sel_bundle_rows = getattr(event_b, "selection", None)
            if sel_bundle_rows and sel_bundle_rows.rows and sel_bundle_rows.rows[0] < len(filtered_b):
                active_b_name = filtered_b.iloc[sel_bundle_rows.rows[0]]["study_name"]

        if active_b_name:
            m_pkg = filtered_b[filtered_b["study_name"] == active_b_name]
            if not m_pkg.empty:
                selected_pkg = m_pkg.iloc[0]
                b_name = selected_pkg["study_name"]
                b_price = float(selected_pkg["price"])
                b_list = float(selected_pkg["list_price"])
                b_disc = float(selected_pkg["discount_pct"])

                st.markdown("---")
                c_info_b, c_btn_b = st.columns([4, 2])
                with c_info_b:
                    st.info(f"📌 **Paquete Seleccionado:** **{b_name}** | Precio Web Chopo: **${b_price:,.2f} MXN** | Lista: `${b_list:,.2f} MXN` ({b_disc:.1f}% desc.)")
                with c_btn_b:
                    if st.button("🎯 COMPETIR CONTRA ESTE PAQUETE", type="primary", use_container_width=True, key=f"btn_comp_{b_name}"):
                        st.session_state.active_chopo_bundle = b_name
                        st.session_state.sim_mode = "Competir contra Paquete Chopo"
                        st.session_state.our_package_name = f"Alternativa a {b_name}"
                        st.session_state.our_selling_price = round(b_price * 0.85, 2)
                        st.toast(f"¡Cargado '{b_name}' en el Simulador!")
                        st.rerun()

                # Desglose de lo que incluye el paquete (extraído de Chopo)
                b_info = get_bundle_detail(b_name)
                if b_info:
                    with st.expander(f"🔬 ¿Qué incluye '{b_name}' según Chopo?", expanded=True):
                        bullets = b_info.get("bullets", [])
                        inc_txt = b_info.get("included_text", "")
                        desc_txt = b_info.get("description", "")
                        fasting_txt = b_info.get("fasting", "")
                        custom_notes = b_info.get("custom_notes", "")

                        if bullets:
                            st.markdown("**📋 Estudios y parámetros incluidos detectados:**")
                            b_cols = st.columns(min(3, max(1, len(bullets))))
                            for idx, b_item in enumerate(bullets):
                                b_cols[idx % min(3, max(1, len(bullets)))].markdown(f"✓ {b_item}")
                        elif inc_txt:
                            st.markdown(f"**📋 Desglose incluido reportado por Chopo:**\n\n{inc_txt}")

                        if desc_txt and not bullets and not inc_txt:
                            st.markdown(f"**ℹ️ Descripción del paquete:**\n\n{desc_txt}")
                        elif desc_txt:
                            st.markdown(f"""
                            <details style="margin: 8px 0; padding: 6px 10px; background: #f8f9fa; border-radius: 6px; border: 1px solid #e9ecef;">
                                <summary style="cursor: pointer; color: #1a5276; font-weight: 600;">ℹ️ Ver descripción clínica completa</summary>
                                <p style="margin-top: 8px; font-size: 0.9rem; color: #333;">{desc_txt}</p>
                            </details>
                            """, unsafe_allow_html=True)

                        if fasting_txt:
                            st.caption(f"⏰ **Indicaciones de ayuno / preparación:** {fasting_txt}")

                        # Editor de notas internas de la clínica
                        st.markdown("---")
                        col_nt, col_nt_btn = st.columns([4, 1])
                        with col_nt:
                            new_note = st.text_input(
                                "📝 Notas o desglose interno de tu clínica para este paquete:",
                                value=custom_notes,
                                key=f"note_bundle_{b_name}",
                                placeholder="Ej: Nosotros incluiremos Biometría + Química 45 + EGO"
                            )
                        with col_nt_btn:
                            st.markdown("&nbsp;", unsafe_allow_html=True)
                            if st.button("💾 Guardar", key=f"save_btn_b_{b_name}", use_container_width=True):
                                save_bundle_custom_notes(b_name, new_note)
                                st.toast("✅ Nota guardada en la base de datos")
                                st.rerun()
        else:
            st.caption("💡 **Tip:** Selecciona cualquier paquete en el buscador superior o en la tabla para ver qué estudios incluye y modelar tu contraoferta.")

    # ═══════════════════════════════════════════════════════════════════════════
    # SUBTAB 2: Simulador de Estrategia vs Chopo
    # ═══════════════════════════════════════════════════════════════════════════
    with subtab2:
        st.markdown("#### 🎯 Simulador de Estrategia y Fijación de Precios")
        st.caption("Modela tu contraoferta comercial: compara el precio de tu clínica contra la competencia, proyecta el ahorro que le darás a tus clientes y analiza tu margen bruto operativo.")

        col_mode, col_mode_info = st.columns([3, 2])
        with col_mode:
            current_idx = 0 if st.session_state.sim_mode == "Armar a la carta (Suma de estudios)" else 1
            sim_mode_choice = st.radio(
                "Enfoque de comparación:",
                ["Armar a la carta (Suma de estudios)", "Competir contra Paquete Chopo"],
                index=current_idx,
                horizontal=True,
                key="sim_mode_selector"
            )
            st.session_state.sim_mode = sim_mode_choice

        with col_mode_info:
            if sim_mode_choice == "Armar a la carta (Suma de estudios)":
                st.caption("🔹 Agrupas varios análisis clínicos individuales y los comparas contra la suma de lo que Chopo cobra por ellos.")
            else:
                st.caption("🔹 Tomas un paquete o check-up oficial de Chopo (ej. Check Up Básico) y fijas el precio de tu versión competitiva.")

        st.markdown("---")

        chopo_benchmark = 0.0
        df_selected_studies = pd.DataFrame()

        # ── Modo 1: A la carta ────────────────────────────────────────────────
        if sim_mode_choice == "Armar a la carta (Suma de estudios)":
            def _find_matches(keywords: list[str]) -> list[str]:
                found = []
                for kw in keywords:
                    norm_kw = _normalize_str(kw)
                    m = df[df["study_name"].apply(lambda s: norm_kw in _normalize_str(s))]
                    if not m.empty:
                        m_with_p = m.dropna(subset=["price"]).sort_values("price")
                        if not m_with_p.empty:
                            found.append(m_with_p.iloc[0]["study_name"])
                        else:
                            found.append(m.iloc[0]["study_name"])
                return list(dict.fromkeys(found))

            st.markdown("**⚡ Carga Rápida de Paquetes Frecuentes (1 clic):**")
            p1, p2, p3, p4, p5, p6, p7 = st.columns(7)
            with p1:
                if st.button("🩺 Check-up Básico", use_container_width=True):
                    st.session_state.quote_selected = _find_matches(["GLUCOSA", "BIOMETRIA HEMATICA", "EXAMEN GENERAL DE ORINA"])
                    st.session_state.our_package_name = "Check-Up Básico Preventivo"
                    st.session_state.our_selling_price = 0.0
                    st.rerun()
            with p2:
                if st.button("🧪 Química 45 + BH", use_container_width=True):
                    st.session_state.quote_selected = _find_matches(["QUIMICA INTEGRAL DE 45 ELEMENTOS", "BIOMETRIA HEMATICA"])
                    st.session_state.our_package_name = "Perfil Bioquímico Integral 45"
                    st.session_state.our_selling_price = 0.0
                    st.rerun()
            with p3:
                if st.button("🩸 Tiroideo", use_container_width=True):
                    st.session_state.quote_selected = _find_matches(["TIROIDEO", "TSH", "T3"])
                    st.session_state.our_package_name = "Perfil Tiroideo Diagnóstico"
                    st.session_state.our_selling_price = 0.0
                    st.rerun()
            with p4:
                if st.button("🥗 Lipídico", use_container_width=True):
                    st.session_state.quote_selected = _find_matches(["COLESTEROL TOTAL", "TRIGLICERIDOS", "LIPIDOS", "GLUCOSA"])
                    st.session_state.our_package_name = "Perfil Lipídico Cardiovascular"
                    st.session_state.our_selling_price = 0.0
                    st.rerun()
            with p5:
                if st.button("🤰 Prenatal", use_container_width=True):
                    st.session_state.quote_selected = _find_matches(["BIOMETRIA HEMATICA", "EXAMEN GENERAL DE ORINA", "GLUCOSA", "VDRL"])
                    st.session_state.our_package_name = "Perfil Prenatal Integral"
                    st.session_state.our_selling_price = 0.0
                    st.rerun()
            with p6:
                if st.button("👨 Prostático", use_container_width=True):
                    st.session_state.quote_selected = _find_matches(["ANTIGENO PROSTATICO", "BIOMETRIA HEMATICA", "EXAMEN GENERAL DE ORINA"])
                    st.session_state.our_package_name = "Perfil de Salud Masculina / Próstata"
                    st.session_state.our_selling_price = 0.0
                    st.rerun()
            with p7:
                if st.button("🧹 Limpiar", use_container_width=True):
                    st.session_state.quote_selected = []
                    st.session_state.our_selling_price = 0.0
                    st.rerun()

            all_studies = sorted(df["study_name"].dropna().unique().tolist())
            selected = st.multiselect(
                "🔍 Selecciona los estudios que integran este paquete:",
                options=all_studies,
                default=st.session_state.quote_selected,
                key="quote_multiselect_input",
            )
            st.session_state.quote_selected = selected

            if not selected:
                st.info("👆 Selecciona estudios en el buscador de arriba o haz clic en alguno de los paquetes rápidos para iniciar la simulación.")
                return

            df_selected_studies = df[df["study_name"].isin(selected)].copy().drop_duplicates(subset=["study_name"])
            df_selected_studies["price"] = df_selected_studies["price"].fillna(0.0)
            chopo_benchmark = float(df_selected_studies["price"].sum())

            # Tabla de estudios seleccionados
            st.markdown(f"**Estudios incluidos en la cotización ({len(df_selected_studies)}):**")
            disp_sel = df_selected_studies[["study_name", "category", "price", "list_price"]].copy()
            disp_sel.columns = ["Estudio", "Especialidad", "Precio Web Chopo", "Precio Mostrador Chopo"]
            st.dataframe(
                disp_sel,
                use_container_width=True,
                height=min(220, 35 * len(disp_sel) + 40),
                column_config={
                    "Precio Web Chopo": st.column_config.NumberColumn(format="$%.2f"),
                    "Precio Mostrador Chopo": st.column_config.NumberColumn(format="$%.2f"),
                }
            )

            # Detector de paquetes Chopo que compiten con esta selección
            bundles_match = df[df["is_bundle"] & df["price"].notna()]
            cheaper_b = bundles_match[bundles_match["price"] <= chopo_benchmark].sort_values("price", ascending=False).head(3)
            if not cheaper_b.empty and len(selected) >= 2:
                st.info("💡 **Inteligencia Competitiva:** Chopo tiene estos paquetes armados con precio menor a la suma de tus estudios sueltos:")
                c_b_cols = st.columns(len(cheaper_b))
                for idx, (_, b_row) in enumerate(cheaper_b.iterrows()):
                    with c_b_cols[idx]:
                        st.markdown(f"**{b_row['study_name'][:36]}**")
                        st.markdown(f"Precio Chopo: **${b_row['price']:,.2f} MXN**")
                        diff_b = chopo_benchmark - b_row["price"]
                        st.caption(f"Chopo lo vende ${diff_b:,.2f} más barato que sus estudios sueltos.")

        # ── Modo 2: Competir contra paquete Chopo ─────────────────────────────
        else:
            df_bundles_only = df[df["is_bundle"] & df["price"].notna()].sort_values("price", ascending=True)
            bundle_names = df_bundles_only["study_name"].tolist()

            default_idx = 0
            if st.session_state.active_chopo_bundle and st.session_state.active_chopo_bundle in bundle_names:
                default_idx = bundle_names.index(st.session_state.active_chopo_bundle)

            target_bundle = st.selectbox(
                "Selecciona el paquete o check-up oficial de Chopo a vencer:",
                options=bundle_names,
                index=default_idx,
                key="target_chopo_bundle_sel"
            )
            st.session_state.active_chopo_bundle = target_bundle

            bundle_data = df_bundles_only[df_bundles_only["study_name"] == target_bundle].iloc[0]
            chopo_benchmark = float(bundle_data["price"])
            chopo_list_price = float(bundle_data["list_price"])
            chopo_discount = float(bundle_data["discount_pct"])

            c_b1, c_b2, c_b3, c_b4 = st.columns(4)
            with c_b1:
                st.metric("Precio Web Chopo (Benchmark)", f"${chopo_benchmark:,.2f} MXN")
            with c_b2:
                st.metric("Precio Mostrador Chopo", f"${chopo_list_price:,.2f} MXN")
            with c_b3:
                st.metric("Descuento que Ofrece Chopo", f"{chopo_discount:.1f}%")
            with c_b4:
                st.metric("Segmento", bundle_data["bundle_segment"])

            # Desglose de lo que incluye este paquete según Chopo
            b_detail = get_bundle_detail(target_bundle)
            if b_detail:
                bullets = b_detail.get("bullets", [])
                inc_text = b_detail.get("included_text", "")
                desc = b_detail.get("description", "")
                fasting = b_detail.get("fasting", "")
                custom = b_detail.get("custom_notes", "")

                with st.expander(f"🔬 ¿Qué incluye '{target_bundle}' según Chopo?", expanded=True if (bullets or inc_text) else False):
                    if bullets:
                        st.markdown("**Estudios y parámetros incluidos reportados por Chopo:**")
                        b_cols = st.columns(min(3, max(1, len(bullets))))
                        for idx, b_item in enumerate(bullets):
                            b_cols[idx % min(3, max(1, len(bullets)))].markdown(f"✓ {b_item}")
                    elif inc_text:
                        st.markdown(f"**Desglose incluido:**\n\n{inc_text}")
                    elif desc:
                        st.markdown(f"**Descripción clínica:**\n\n{desc}")
                    else:
                        st.caption("Chopo no especifica los estudios desglosados en su web para este paquete.")

                    if fasting:
                        st.info(f"⏰ **Indicaciones de ayuno / preparación:** {fasting}")

                    if custom:
                        st.success(f"📝 **Notas internas de tu clínica:** {custom}")

        st.markdown("---")

        # ── Sección de Fijación de Precios de Nuestra Clínica ──────────────────
        st.markdown("#### ⚙️ Estrategia de Precio de Nuestra Clínica")

        if st.session_state.our_selling_price <= 0.0 and chopo_benchmark > 0:
            st.session_state.our_selling_price = round(chopo_benchmark * 0.85, 2)

        st.markdown("**Sugerencias rápidas de precio competitivo (1 clic):**")
        sug1, sug2, sug3, sug4 = st.columns(4)
        with sug1:
            if st.button("🟢 Ganar por 10% (-10% vs Chopo)", use_container_width=True):
                st.session_state.our_selling_price = round(chopo_benchmark * 0.90, 2)
                st.rerun()
        with sug2:
            if st.button("🟢 Ganar por 15% (-15% vs Chopo)", use_container_width=True):
                st.session_state.our_selling_price = round(chopo_benchmark * 0.85, 2)
                st.rerun()
        with sug3:
            if st.button("🟢 Ganar por 20% (-20% vs Chopo)", use_container_width=True):
                st.session_state.our_selling_price = round(chopo_benchmark * 0.80, 2)
                st.rerun()
        with sug4:
            if st.button("🟡 Paridad (Mismo precio)", use_container_width=True):
                st.session_state.our_selling_price = round(chopo_benchmark, 2)
                st.rerun()

        col_pn, col_sp, col_ic = st.columns([3, 2, 2])
        with col_pn:
            pkg_name_in = st.text_input(
                "Nombre Comercial de Nuestro Paquete:",
                value=st.session_state.our_package_name,
                key="pkg_name_input_field",
                help="Este es el nombre con el que tu clínica ofrecerá el paquete a empresas y pacientes."
            )
            st.session_state.our_package_name = pkg_name_in

        with col_sp:
            our_price = st.number_input(
                "💰 Nuestro Precio de Venta ($ MXN):",
                min_value=0.0,
                step=25.0,
                value=float(st.session_state.our_selling_price),
                key="our_selling_price_input_num",
                help="El precio final con el que competirás contra Chopo."
            )
            st.session_state.our_selling_price = our_price

        with col_ic:
            internal_cost = st.number_input(
                "🧪 Costo Interno / Reactivos ($ MXN):",
                min_value=0.0,
                step=10.0,
                value=float(st.session_state.our_internal_cost),
                key="our_internal_cost_input_num",
                help="Opcional: ingresa el costo directo de reactivos y tubos para calcular tu margen bruto."
            )
            st.session_state.our_internal_cost = internal_cost

        # ── Diagnóstico y KPIs Competitivos ───────────────────────────────────
        diff_pesos = chopo_benchmark - our_price
        diff_pct = (diff_pesos / chopo_benchmark * 100.0) if chopo_benchmark > 0 else 0.0

        st.markdown("#### 📊 Diagnóstico de Competitividad:")
        d1, d2, d3, d4 = st.columns(4)
        with d1:
            st.metric("Benchmark Chopo (Web)", f"${chopo_benchmark:,.2f} MXN")
        with d2:
            st.metric(f"Precio {pkg_name_in}", f"${our_price:,.2f} MXN")
        with d3:
            if diff_pesos > 0:
                st.metric("Ahorro para el Cliente", f"${diff_pesos:,.2f} MXN", delta=f"{diff_pct:.1f}% más barato", delta_color="normal")
            elif diff_pesos < 0:
                st.metric("Diferencia vs Chopo", f"+${abs(diff_pesos):,.2f} MXN", delta=f"{abs(diff_pct):.1f}% más caro", delta_color="inverse")
            else:
                st.metric("Diferencia vs Chopo", "$0.00 MXN", delta="Paridad exacta", delta_color="off")
        with d4:
            if internal_cost > 0 and our_price > 0:
                gross_margin = our_price - internal_cost
                gross_pct = (gross_margin / our_price) * 100.0
                st.metric("Margen Bruto Clínica", f"${gross_margin:,.2f} MXN", delta=f"{gross_pct:.1f}% margen")
            else:
                st.metric("Margen Bruto Clínica", "N/D", help="Ingresa tu costo de reactivos arriba para ver tu margen.")

        # Veredicto Estratégico
        if diff_pesos > 0:
            st.success(f"🚀 **Estrategia Ganadora:** Tu clínica es **${diff_pesos:,.2f} MXN ({diff_pct:.1f}%) más económica que Chopo**. Es una propuesta sumamente atractiva para captar pacientes de mostrador o cerrar convenios corporativos por volumen.")
        elif diff_pesos == 0:
            st.warning("⚖️ **Estrategia de Paridad:** Estás al mismo precio exacto de Chopo. Para que el cliente te elija a ti en vez de a Chopo, tu propuesta comercial debe resaltar tu entrega el mismo día, toma a domicilio y atención sin filas.")
        else:
            st.error(f"⚠️ **Precio Superior a Chopo:** Tu precio está **${abs(diff_pesos):,.2f} MXN (+{abs(diff_pct):.1f}%) por encima de Chopo**. Si vas a cobrar más caro, asegúrate de que el paquete incluya estudios adicionales o beneficios exclusivos que justifiquen el sobreprecio.")

        # Gráfico Comparativo Plotly
        fig_comp = go.Figure()
        fig_comp.add_trace(go.Bar(
            name="Competencia: Chopo Web",
            x=["Comparativa de Precios"],
            y=[chopo_benchmark],
            marker_color="#1a5276",
            text=[f"${chopo_benchmark:,.2f}"],
            textposition="auto",
        ))
        fig_comp.add_trace(go.Bar(
            name=f"Nuestra Clínica: {pkg_name_in[:24]}",
            x=["Comparativa de Precios"],
            y=[our_price],
            marker_color="#27ae60" if our_price <= chopo_benchmark else "#e67e22",
            text=[f"${our_price:,.2f}"],
            textposition="auto",
        ))
        if internal_cost > 0:
            fig_comp.add_trace(go.Bar(
                name="Nuestro Costo de Reactivos",
                x=["Comparativa de Precios"],
                y=[internal_cost],
                marker_color="#95a5a6",
                text=[f"${internal_cost:,.2f}"],
                textposition="auto",
            ))
        fig_comp.update_layout(
            barmode="group",
            height=280,
            margin=dict(t=20, b=20, l=20, r=20),
            yaxis_title="Pesos ($ MXN)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig_comp, use_container_width=True)

    # ═══════════════════════════════════════════════════════════════════════════
    # SUBTAB 3: Propuesta Comercial & Comparativa B2B
    # ═══════════════════════════════════════════════════════════════════════════
    with subtab3:
        st.markdown("#### 📄 Propuesta Comercial Competitiva (Nuestra Clínica vs Chopo)")
        st.caption("Genera una propuesta formal para presentar a empresas maquiladoras, corporativos, aseguradoras o pacientes particulares, demostrando tu ventaja frente a laboratorios de cadena como Chopo.")

        c_p1, c_p2, c_p3 = st.columns(3)
        with c_p1:
            prop_client = st.text_input("Nombre de la Empresa o Paciente:", value="Empresa / Cliente Corporativo", key="prop_client_name")
        with c_p2:
            prop_clinic = st.text_input("Nombre de Nuestra Clínica:", value="Laboratorio Clínico Mérida", key="prop_clinic_name")
        with c_p3:
            prop_validity = st.text_input("Vigencia de la Cotización:", value="15 días naturales", key="prop_validity_str")

        st.markdown("**Selecciona los diferenciadores de valor agregado de tu clínica a incluir en la propuesta:**")
        b_c1, b_c2 = st.columns(2)
        with b_c1:
            adv1 = st.checkbox("⚡ Entrega de resultados el mismo día (2 a 4 hrs para rutina)", value=True, key="adv_cb1")
            adv2 = st.checkbox("🚐 Toma de muestra a domicilio o en planta sin costo en Mérida", value=True, key="adv_cb2")
            adv3 = st.checkbox("🩺 Atención prioritaria y ágil sin filas de espera", value=True, key="adv_cb3")
        with b_c2:
            adv4 = st.checkbox("💼 Convenio empresarial con facturación y crédito a 30 días", value=True, key="adv_cb4")
            adv5 = st.checkbox("💻 Plataforma en línea para consulta médica y descarga de resultados", value=True, key="adv_cb5")
            adv6 = st.checkbox("🔬 Control de calidad certificado y validación por patólogos", value=True, key="adv_cb6")

        selected_benefits = []
        if adv1: selected_benefits.append("Entrega de resultados el mismo día (2 a 4 hrs para rutina)")
        if adv2: selected_benefits.append("Toma de muestra a domicilio o en empresa sin costo en Mérida")
        if adv3: selected_benefits.append("Atención personalizada y ágil sin filas de espera")
        if adv4: selected_benefits.append("Convenio empresarial con facturación electrónica y crédito a 30 días")
        if adv5: selected_benefits.append("Plataforma en línea para consulta médica y descarga de resultados")
        if adv6: selected_benefits.append("Control de calidad certificado y validación por patólogos")

        # Preparar ítems para la propuesta
        items_for_proposal = []
        if sim_mode_choice == "Armar a la carta (Suma de estudios)" and not df_selected_studies.empty:
            ratio = (our_price / chopo_benchmark) if chopo_benchmark > 0 else 1.0
            for _, r_it in df_selected_studies.iterrows():
                ch_p = float(r_it["price"])
                our_p = round(ch_p * ratio, 2)
                sav = ch_p - our_p
                sav_p = (sav / ch_p * 100.0) if ch_p > 0 else 0.0
                items_for_proposal.append({
                    "name": r_it["study_name"],
                    "chopo_price": ch_p,
                    "our_price": our_p,
                    "savings": sav,
                    "savings_pct": sav_p,
                })
        else:
            target_name = st.session_state.active_chopo_bundle or "Paquete Integral Chopo"
            items_for_proposal.append({
                "name": f"{st.session_state.our_package_name} (Equivalente / Competidor de {target_name})",
                "chopo_price": chopo_benchmark,
                "our_price": our_price,
                "savings": diff_pesos,
                "savings_pct": diff_pct,
            })

        # Tabla comparativa visual
        st.markdown("---")
        st.markdown(f"##### 📋 Tabla Comparativa de Inversión: {st.session_state.our_package_name}")
        df_prop_table = pd.DataFrame(items_for_proposal)
        df_prop_disp = df_prop_table.copy()
        df_prop_disp.columns = ["Concepto / Estudio", "Precio Chopo (Referencia)", f"Precio Especial {prop_clinic}", "Ahorro al Cliente ($)", "Ventaja (%)"]

        st.dataframe(
            df_prop_disp,
            use_container_width=True,
            column_config={
                "Precio Chopo (Referencia)": st.column_config.NumberColumn(format="$%.2f"),
                f"Precio Especial {prop_clinic}": st.column_config.NumberColumn(format="$%.2f"),
                "Ahorro al Cliente ($)": st.column_config.NumberColumn(format="$%.2f"),
                "Ventaja (%)": st.column_config.NumberColumn(format="%.1f%%"),
            }
        )

        st.markdown(f"""
        <div style="background-color:#1a5276;color:white;padding:15px;border-radius:8px;margin-bottom:20px;">
            <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;">
                <div>
                    <h4 style="margin:0;color:#d6eaf8;">TOTAL PAQUETE {prop_client.upper()}</h4>
                    <span style="font-size:0.95rem;">Precio en Chopo: <b>${chopo_benchmark:,.2f} MXN</b></span>
                </div>
                <div style="text-align:right;">
                    <span style="font-size:0.9rem;color:#abebc6;">PRECIO ESPECIAL CONVENIO:</span>
                    <h2 style="margin:0;color:#2ecc71;">${our_price:,.2f} MXN</h2>
                    <span style="color:#f9e79f;font-weight:bold;">¡Ahorro directo de ${diff_pesos:,.2f} MXN ({diff_pct:.1f}%)!</span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Ficha de texto para copiar a WhatsApp / Correo B2B
        today_str = datetime.now().strftime("%d/%m/%Y")
        items_bullets = "\n".join([f"  • {it['name']}: Chopo ${it['chopo_price']:,.2f} | Nosotros: ${it['our_price']:,.2f}" for it in items_for_proposal])
        benefits_bullets = "\n".join([f"  ✓ {b}" for b in selected_benefits])

        commercial_pitch = f"""💼 *PROPUESTA COMERCIAL - {prop_clinic.upper()}*
🏢 *Presentado para:* {prop_client}
📅 *Fecha:* {today_str} (Vigencia: {prop_validity})
📦 *Paquete Solicitado:* {st.session_state.our_package_name}

📊 *COMPARATIVA DE INVERSIÓN VS CADENAS NACIONALES (CHOPO):*
{items_bullets}

💰 *Inversión en Chopo:* ${chopo_benchmark:,.2f} MXN
⭐ *PRECIO ESPECIAL {prop_clinic.upper()}:* ${our_price:,.2f} MXN
🎉 *AHORRO DIRECTO PARA SU EMPRESA:* ${diff_pesos:,.2f} MXN ({diff_pct:.1f}% de descuento)

✨ *BENEFICIOS Y VALOR AGREGADO INCLUIDOS:*
{benefits_bullets}

Quedamos a su entera disposición para agendar la toma de muestras o formalizar el convenio.
"""
        st.markdown("##### 📱 Texto Comercial Listo para WhatsApp o Correo B2B:")
        st.text_area("Copia este mensaje comercial y envíalo directamente a tu cliente o empresa:", value=commercial_pitch, height=220)

        # Botones de exportación a Excel
        st.markdown("##### 📥 Descarga de Propuesta Comercial en Excel:")
        excel_bytes = _generate_commercial_proposal_excel(
            clinic_name=prop_clinic,
            client_name=prop_client,
            package_name=st.session_state.our_package_name,
            items=items_for_proposal,
            total_chopo=chopo_benchmark,
            total_our=our_price,
            savings=diff_pesos,
            savings_pct=diff_pct,
            benefits=selected_benefits,
        )

        filename_clean = f"Propuesta_{_normalize_str(st.session_state.our_package_name)[:20].replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.xlsx"

        c_exp1, c_exp2 = st.columns([2, 3])
        with c_exp1:
            st.download_button(
                label="📥 Descargar Propuesta en Excel (.xlsx)",
                data=excel_bytes,
                file_name=filename_clean,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                type="primary",
            )
        with c_exp2:
            if st.button("💾 Guardar Copia en Carpeta exports/ del Servidor", use_container_width=True):
                local_path = EXPORTS_DIR / filename_clean
                with open(local_path, "wb") as f_out:
                    f_out.write(excel_bytes)
                st.success(f"Archivo guardado exitosamente en: `{local_path}`")


# ── Tab: Scheduler & Configuración ────────────────────────────────────────────
def render_scheduler_tab():
    st.markdown("### ⚙️ Automatización & Scheduler de Actualizaciones")
    st.caption("Configura la frecuencia con la que el sistema actualiza automáticamente los precios de Chopo en segundo plano.")

    status = get_scheduler_status()
    is_running = status["running"]
    pid = status["pid"]
    cfg = status["config"]
    s_data = status["status_data"]

    def _calc_next_fire_display(c: dict) -> str:
        try:
            import pytz
            from apscheduler.triggers.cron import CronTrigger
            from apscheduler.triggers.interval import IntervalTrigger
            tz = pytz.timezone("America/Merida")
            now_tz = datetime.now(tz)
            if c.get("mode") == "interval":
                h = max(1, int(c.get("interval_hours", 12)))
                trig = IntervalTrigger(hours=h, timezone="America/Merida")
            else:
                hr = int(c.get("cron_hour", 6))
                mn = int(c.get("cron_minute", 0))
                trig = CronTrigger(hour=hr, minute=mn, timezone="America/Merida")
            dt = trig.get_next_fire_time(None, now_tz)
            return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else "No programado"
        except Exception:
            return "No programado"

    planned = _calc_next_fire_display(cfg)
    next_run = s_data.get("next_run") if (is_running and s_data.get("next_run")) else planned

    col_s1, col_s2, col_s3 = st.columns(3)
    with col_s1:
        if is_running:
            st.success(f"🟢 **SERVICIO ACTIVO** (PID: `{pid}`)")
        else:
            st.warning("🟡 **SERVICIO DETENIDO**")
    with col_s2:
        if is_running:
            st.metric("⏰ Próxima Ejecución", next_run)
        else:
            st.metric("⏰ Próxima Programada", next_run, help="Esta será la hora al hacer clic en Iniciar Scheduler")
    with col_s3:
        last_run = s_data.get("last_run") or "Aún no ejecutado"
        st.metric("✅ Última Ejecución", last_run[:19] if last_run != "Aún no ejecutado" else last_run)

    if is_running and s_data.get("message"):
        st.info(f"Estado del servicio: {s_data['message']}")
    elif not is_running:
        st.caption("ℹ️ Haz clic en '🟢 Iniciar Scheduler' abajo para activar las actualizaciones automáticas en segundo plano.")

    is_cloud = Path("/mount/src").exists()
    if is_cloud:
        st.info("☁️ **Estás visualizando el portal en la Nube (Streamlit Cloud)**\n\n"
                "Las actualizaciones automáticas de precios y el navegador Playwright se ejecutan de forma óptima en tu computadora local en Mérida para garantizar velocidad y evitar bloqueos de IP.\n\n"
                "💡 Cada vez que tu PC local ejecuta el scrape (diario a las 6:00 AM o manual), la base de datos en la nube se actualiza automáticamente.")

    st.markdown("---")
    st.markdown("#### 🎮 Controles del Servicio:")
    btn_c1, btn_c2, btn_c3, btn_c4 = st.columns(4)

    with btn_c1:
        if not is_running:
            if st.button("🟢 Iniciar Scheduler", type="primary", use_container_width=True):
                try:
                    ok, msg = start_scheduler()
                    if ok: st.success(msg)
                    else: st.error(msg)
                except Exception as ex:
                    st.error(f"Error iniciando scheduler: {ex}")
                st.rerun()
        else:
            st.button("🟢 Servicio Activo", disabled=True, use_container_width=True)

    with btn_c2:
        if is_running:
            if st.button("🔴 Detener Scheduler", type="secondary", use_container_width=True):
                try:
                    ok, msg = stop_scheduler()
                    if ok: st.warning(msg)
                    else: st.error(msg)
                except Exception as ex:
                    st.error(f"Error deteniendo scheduler: {ex}")
                st.rerun()
        else:
            st.button("🔴 Servicio Detenido", disabled=True, use_container_width=True)

    with btn_c3:
        if is_running:
            if st.button("🔄 Reiniciar Servicio", use_container_width=True):
                try:
                    ok, msg = restart_scheduler()
                    st.info(msg)
                except Exception as ex:
                    st.error(f"Error reiniciando scheduler: {ex}")
                st.rerun()
        else:
            st.button("🔄 Reiniciar", disabled=True, use_container_width=True)

    with btn_c4:
        if st.button("⚡ Scrape de Prueba Ahora", use_container_width=True):
            _launch_scrape_background()
            st.success("Scrape inmediato lanzado en segundo plano.")
            st.rerun()

    st.markdown("---")
    st.markdown("#### 🛠️ Configurar Frecuencia de Actualización:")

    with st.form("scheduler_config_form"):
        col_m1, col_m2 = st.columns(2)

        with col_m1:
            mode = st.radio(
                "Modo de programación:",
                options=["cron", "interval"],
                format_func=lambda x: "🕒 Hora fija diaria (ej. 6:00 AM)" if x == "cron" else "⏱️ Intervalo regular (cada X horas)",
                index=0 if cfg.get("mode") == "cron" else 1,
            )

        with col_m2:
            if mode == "cron":
                col_h, col_m = st.columns(2)
                with col_h:
                    hour = st.selectbox("Hora del día (24h)", list(range(24)), index=int(cfg.get("cron_hour", 6)))
                with col_m:
                    minute = st.selectbox("Minuto", [0, 15, 30, 45], index=[0, 15, 30, 45].index(int(cfg.get("cron_minute", 0))) if int(cfg.get("cron_minute", 0)) in [0, 15, 30, 45] else 0)
                interval_h = cfg.get("interval_hours", 12)
            else:
                interval_h = st.select_slider("Ejecutar cada cuántas horas:", options=[2, 4, 6, 8, 12, 24, 48], value=int(cfg.get("interval_hours", 12)))
                hour = cfg.get("cron_hour", 6)
                minute = cfg.get("cron_minute", 0)

        branch = st.selectbox("Sucursal objetivo:", ["altabrisa"], index=0)

        saved = st.form_submit_button("💾 Guardar y Aplicar Cambios", type="primary")
        if saved:
            new_cfg = {
                **cfg,
                "mode": mode,
                "cron_hour": hour,
                "cron_minute": minute,
                "interval_hours": interval_h,
                "branch": branch,
            }
            save_scheduler_config(new_cfg)
            if is_running:
                restart_scheduler()
                st.success("✅ Configuración guardada y servicio reiniciado.")
            else:
                st.success("✅ Configuración guardada correctamente.")
            st.rerun()

    st.markdown("---")
    st.markdown("#### 📋 Log del Scheduler:")
    sched_log = Path(__file__).parent.parent / "logs" / "scheduler.log"
    if sched_log.exists():
        try:
            log_lines = sched_log.read_text(encoding="utf-8", errors="replace").splitlines()
            recent_log = [l for l in log_lines if l.strip()][-12:]
            with st.expander("Ver log reciente del scheduler", expanded=True):
                st.code("\n".join(recent_log) if recent_log else "Sin registros aún.", language=None)
        except Exception:
            pass
    else:
        st.caption("Aún no se ha generado archivo de log del scheduler.")


# ── Tab 5: Logs del Sistema ────────────────────────────────────────────────────
def render_logs_tab(scrape_log: list):
    st.markdown("### 🗂️ Log de Scrapes Realizados")

    if not scrape_log:
        st.info("Sin registros de scrapes todavía.")
        return

    df = pd.DataFrame(scrape_log)
    st.dataframe(df, use_container_width=True)

    # Gráfico de estudios por fecha
    if "scraped_at" in df.columns and "studies_count" in df.columns:
        df["scraped_at"] = pd.to_datetime(df["scraped_at"])
        fig = px.bar(
            df.head(20),
            x="scraped_at",
            y="studies_count",
            color="lab_name",
            title="Estudios Recopilados por Fecha de Scrape",
            labels={"scraped_at": "Fecha", "studies_count": "Número de Estudios"},
        )
        st.plotly_chart(fig, use_container_width=True)


def check_password() -> bool:
    """Verifica si el usuario está autenticado y asigna el rol de administrador o consulta."""
    if st.session_state.get("authenticated", False):
        return True

    user_password = "chopo2026"
    admin_password = "admin2026"

    try:
        if hasattr(st, "secrets"):
            if "APP_PASSWORD" in st.secrets:
                user_password = str(st.secrets["APP_PASSWORD"])
            if "ADMIN_PASSWORD" in st.secrets:
                admin_password = str(st.secrets["ADMIN_PASSWORD"])
    except Exception:
        pass

    import os
    user_password = os.getenv("APP_PASSWORD", user_password)
    admin_password = os.getenv("ADMIN_PASSWORD", admin_password)

    _, col_login, _ = st.columns([1, 2, 1])
    with col_login:
        st.markdown("<div style='height:40px'></div>", unsafe_allow_html=True)
        st.markdown(
            """
            <div style="background:#ffffff;padding:30px;border-radius:12px;box-shadow:0 4px 15px rgba(0,0,0,0.08);text-align:center;border:1px solid #e0e0e0;">
                <h2 style="color:#1a5276;margin-bottom:5px;">🔬 Chopo Price Intelligence</h2>
                <p style="color:#666;font-size:0.95rem;margin-bottom:20px;">Portal de Análisis de Precios · Mérida, Yucatán</p>
                <p style="color:#333;font-size:0.9rem;text-align:left;margin-bottom:5px;">🔒 Ingresa tu clave de acceso:</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.form("login_form"):
            password_input = st.text_input("Clave de acceso", type="password", placeholder="Escribe tu clave aquí...", label_visibility="collapsed")
            submit = st.form_submit_button("🔓 Ingresar al Portal", type="primary", use_container_width=True)

            if submit:
                if password_input == admin_password:
                    st.session_state["authenticated"] = True
                    st.session_state["is_admin"] = True
                    st.rerun()
                elif password_input == user_password:
                    st.session_state["authenticated"] = True
                    st.session_state["is_admin"] = False
                    st.rerun()
                else:
                    st.error("❌ Clave incorrecta. Por favor verifícala.")

        st.caption("🔒 Acceso protegido. El nivel de permisos se asigna automáticamente según tu clave.")

    return False


# ── Main App ───────────────────────────────────────────────────────────────────
def main():
    if not check_password():
        return

    initialize()

    prices, labs, changes, scrape_log = load_data()

    render_header()
    st.markdown("---")

    filters = render_sidebar(labs, prices)

    render_kpis(prices, changes, scrape_log)
    st.markdown("---")

    is_admin = st.session_state.get("is_admin", False)

    if is_admin:
        tab0, tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
            "⭐ Favoritos",
            "📋 Catálogo",
            "🏷️ Descuentos & Promos",
            "💼 Paquetes & Estrategia",
            "📊 Análisis",
            "📈 Historial",
            "🔔 Cambios",
            "⚙️ Scheduler & Config",
            "🗂️ Logs",
        ])

        with tab0:
            render_favorites_tab(prices)
        with tab1:
            render_catalog_tab(prices, filters)
        with tab2:
            render_discounts_tab(prices)
        with tab3:
            render_quotation_tab(prices)
        with tab4:
            render_analysis_tab(prices, filters)
        with tab5:
            render_history_tab(labs)
        with tab6:
            render_changes_tab(changes)
        with tab7:
            render_scheduler_tab()
        with tab8:
            render_logs_tab(scrape_log)
    else:
        tab0, tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
            "⭐ Favoritos",
            "📋 Catálogo",
            "🏷️ Descuentos & Promos",
            "💼 Paquetes & Estrategia",
            "📊 Análisis",
            "📈 Historial",
            "🔔 Cambios",
        ])

        with tab0:
            render_favorites_tab(prices)
        with tab1:
            render_catalog_tab(prices, filters)
        with tab2:
            render_discounts_tab(prices)
        with tab3:
            render_quotation_tab(prices)
        with tab4:
            render_analysis_tab(prices, filters)
        with tab5:
            render_history_tab(labs)
        with tab6:
            render_changes_tab(changes)


if __name__ == "__main__":
    main()
