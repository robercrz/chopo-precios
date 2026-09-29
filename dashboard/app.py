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
        _render_scrape_button()


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
    st.sidebar.markdown("### ⏰ Scheduler")
    st.sidebar.info("Actualización automática: **6:00 AM** diario\n(Hora Mérida, Yucatán)")

    st.sidebar.markdown("---")
    st.sidebar.markdown("---")
    if st.sidebar.button("🔒 Cerrar Sesión", use_container_width=True):
        st.session_state["authenticated"] = False
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

    # Agregar indicador de favorito
    fav_names = get_favorite_names()
    df["fav"] = df["study_name"].apply(lambda n: "⭐" if n in fav_names else "")

    # ── Filtro rápido de favoritos ──
    c_filt_fav, c_quick_sel, c_quick_btn = st.columns([2, 4, 2])
    with c_filt_fav:
        only_favs = st.checkbox(f"⭐ Ver solo mis Favoritos ({len(fav_names)})", value=False, key="cat_only_favs")
    if only_favs:
        df = df[df["study_name"].isin(fav_names)]

    with c_quick_sel:
        all_avail = sorted(df["study_name"].dropna().unique().tolist())
        q_pick = st.selectbox(
            "⭐ O busca un estudio aquí para marcarlo con 1 clic:",
            options=["-- Selecciona un estudio para marcar/desmarcar --"] + all_avail,
            key="cat_quick_picker",
            label_visibility="collapsed",
        )
    with c_quick_btn:
        if q_pick and q_pick != "-- Selecciona un estudio para marcar/desmarcar --":
            is_q_f = q_pick in fav_names
            if is_q_f:
                if st.button("💛 Quitar Favorito", key="btn_q_del_top", use_container_width=True):
                    remove_favorite(q_pick, "chopo_yucatan")
                    st.toast(f"'{q_pick}' removido de favoritos")
                    st.rerun()
            else:
                if st.button("⭐ Marcar Favorito", type="primary", key="btn_q_add_top", use_container_width=True):
                    add_favorite(q_pick, "chopo_yucatan")
                    st.toast(f"⭐ '{q_pick}' agregado a favoritos!")
                    st.rerun()
        else:
            st.button("⭐ Selecciona arriba", disabled=True, use_container_width=True)

    # ── Aplicar filtros ────────────────────────────────────────────────────────
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
    st.markdown("")

    # ── Tabla con selección de fila ────────────────────────────────────────────
    display_cols = [c for c in ["fav", "study_name", "category", "price", "price_raw", "lab_name", "city", "scraped_at"]
                    if c in df.columns]
    df_display = df[display_cols].copy()
    col_rename = {
        "fav": "★",
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
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "Precio": st.column_config.NumberColumn("Precio (MXN)", format="$%.2f"),
            "Actualizado": st.column_config.DatetimeColumn("Actualizado"),
            "★": st.column_config.TextColumn("★", help="Muestra ⭐ si ya está en tus favoritos", width="small"),
            "Especialidad": st.column_config.TextColumn("Especialidad", width="medium"),
        },
    )

    # ── Barra de Acción Inmediata al seleccionar fila ───────────────────────────
    selected_rows = getattr(selection_event, "selection", None)
    selected_idx = selected_rows.rows[0] if (selected_rows and selected_rows.rows) else None

    if selected_idx is not None and selected_idx < len(df):
        row = df.iloc[selected_idx]
        st_name = row["study_name"]
        st_price = row.get("price")
        st_cat = row.get("category", "")
        is_f = st_name in fav_names
        p_str = f"${st_price:,.2f} MXN" if st_price else "Sin precio"

        # Banner prominente con botón grande
        st.markdown("---")
        c_ban_info, c_ban_btn = st.columns([4, 2])
        with c_ban_info:
            fav_status = "⭐ Ya está en tus Favoritos" if is_f else "☆ No está en Favoritos"
            st.info(f"📌 **Estudio Seleccionado:** **{st_name}** ({p_str}) | Especialidad: `{st_cat}` | **{fav_status}**")
        with c_ban_btn:
            if is_f:
                if st.button("💛 Quitar de Favoritos", key=f"quick_banner_del_{st_name}", use_container_width=True):
                    remove_favorite(st_name, row.get("lab_key", "chopo_yucatan"), row.get("branch"))
                    st.toast(f"'{st_name}' removido de favoritos")
                    st.rerun()
            else:
                if st.button("⭐ MARCAR COMO FAVORITO", type="primary", key=f"quick_banner_add_{st_name}", use_container_width=True):
                    add_favorite(st_name, row.get("lab_key", "chopo_yucatan"), row.get("branch"))
                    st.toast(f"⭐ '{st_name}' agregado a favoritos!")
                    st.rerun()

        # Panel de Detalle completo
        _render_study_detail(row, df, fav_names)
    else:
        st.caption("💡 **Tip:** Haz clic en cualquier fila de la tabla para seleccionarla y verás aparecer aquí el botón directo para marcarla o desmarcarla.")



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


# ── Tab: Cotizador de Paquetes ────────────────────────────────────────────────
def render_quotation_tab(prices: list):
    st.markdown("### 💼 Cotizador de Paquetes & Perfiles Clínicos")
    st.caption("Arma cotizaciones para pacientes o empresas, calcula totales con descuento y genera fichas para WhatsApp o Excel.")

    df = pd.DataFrame(prices)
    if df.empty or "study_name" not in df.columns:
        st.info("No hay catálogo disponible para cotizar.")
        return

    if "category" not in df.columns:
        df["category"] = df["study_name"].apply(lambda n: classify_study(n) if pd.notna(n) else "Otros")

    if "quote_selected" not in st.session_state:
        st.session_state.quote_selected = []

    st.markdown("#### ⚡ Paquetes Rápidos Predefinidos (1 clic):")
    p1, p2, p3, p4, p5, p6 = st.columns(6)

    def _find_matches(keywords: list[str]) -> list[str]:
        found = []
        for kw in keywords:
            m = df[df["study_name"].str.contains(kw, case=False, na=False)]
            if not m.empty:
                m_with_p = m.dropna(subset=["price"]).sort_values("price")
                if not m_with_p.empty:
                    found.append(m_with_p.iloc[0]["study_name"])
                else:
                    found.append(m.iloc[0]["study_name"])
        return list(dict.fromkeys(found))

    with p1:
        if st.button("🩺 Check-up Básico", use_container_width=True):
            st.session_state.quote_selected = _find_matches(["GLUCOSA", "BIOMETRÍA HEMÁTICA", "EXAMEN GENERAL DE ORINA"])
            st.rerun()
    with p2:
        if st.button("🥗 Perfil Lipídico", use_container_width=True):
            st.session_state.quote_selected = _find_matches(["COLESTEROL TOTAL", "TRIGLICÉRIDOS", "LÍPIDOS", "GLUCOSA"])
            st.rerun()
    with p3:
        if st.button("🩸 Perfil Tiroideo", use_container_width=True):
            st.session_state.quote_selected = _find_matches(["TIROIDEO", "TSH", "T3", "T4"])
            st.rerun()
    with p4:
        if st.button("🧪 Química 45 Elem.", use_container_width=True):
            st.session_state.quote_selected = _find_matches(["QUÍMICA INTEGRAL DE 45 ELEMENTOS", "BIOMETRÍA HEMÁTICA"])
            st.rerun()
    with p5:
        if st.button("🤰 Perfil Prenatal", use_container_width=True):
            st.session_state.quote_selected = _find_matches(["BIOMETRÍA HEMÁTICA", "EXAMEN GENERAL DE ORINA", "GLUCOSA", "VDRL"])
            st.rerun()
    with p6:
        if st.button("🧹 Limpiar Todo", use_container_width=True):
            st.session_state.quote_selected = []
            st.rerun()

    st.markdown("---")

    all_studies = sorted(df["study_name"].dropna().unique().tolist())
    selected = st.multiselect(
        "🔍 Busca y agrega estudios al paquete a cotizar:",
        options=all_studies,
        default=st.session_state.quote_selected,
        key="quote_multiselect",
    )
    st.session_state.quote_selected = selected

    if not selected:
        st.info("👆 Selecciona uno de los paquetes predefinidos arriba o busca estudios en el cuadro para comenzar a cotizar.")
        return

    df_quote = df[df["study_name"].isin(selected)].copy().drop_duplicates(subset=["study_name"])
    df_quote["price"] = df_quote["price"].fillna(0.0)

    c_list, c_calc = st.columns([3, 2])

    with c_list:
        st.markdown(f"#### 📋 Estudios Seleccionados ({len(df_quote)}):")
        disp_q = df_quote[["study_name", "category", "price"]].copy()
        disp_q.columns = ["Estudio", "Especialidad", "Precio Chopo (MXN)"]
        st.dataframe(
            disp_q,
            use_container_width=True,
            column_config={
                "Precio Chopo (MXN)": st.column_config.NumberColumn(format="$%.2f"),
            }
        )

    with c_calc:
        st.markdown("#### 💰 Resumen Financiero:")
        subtotal = float(df_quote["price"].sum())
        st.metric("Subtotal Suma Individual", f"${subtotal:,.2f} MXN")

        col_d1, col_d2 = st.columns(2)
        with col_d1:
            discount_pct = st.slider("Descuento especial (%)", 0, 50, 10, step=5)
        with col_d2:
            margin_pct = st.slider("Comisión / Margen (%)", 0, 50, 0, step=5)

        discount_amount = subtotal * (discount_pct / 100.0)
        total_after_discount = subtotal - discount_amount
        margin_amount = total_after_discount * (margin_pct / 100.0)
        final_total = total_after_discount + margin_amount

        st.markdown(f"""
        <div style="background-color:#1a5276;color:white;padding:15px;border-radius:8px;text-align:center;">
            <p style="margin:0;font-size:1.1rem;">TOTAL COTIZADO AL PACIENTE</p>
            <h2 style="margin:5px 0 0 0;color:#2ecc71;">${final_total:,.2f} MXN</h2>
            <small style="color:#d6eaf8;">Ahorro otorgado: ${discount_amount:,.2f} ({discount_pct}%)</small>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("#### 💡 Asistente de Ahorro con Paquetes Integrales Chopo:")
    bundles = df[df["category"].str.contains("Perfil|Paneles", case=False, na=False) | df["study_name"].str.contains("INTEGRAL|PERFIL|CHECK", case=False, na=False)].dropna(subset=["price"])
    cheaper_bundles = bundles[bundles["price"] <= subtotal].sort_values("price").head(4)

    if not cheaper_bundles.empty and len(selected) > 1:
        st.info("💡 En lugar de pedir estudios individuales, Chopo ofrece estos paquetes que podrían cubrir la necesidad a menor costo:")
        b_cols = st.columns(min(4, len(cheaper_bundles)))
        for idx, (_, b_row) in enumerate(cheaper_bundles.iterrows()):
            with b_cols[idx]:
                st.markdown(f"**{b_row['study_name'][:38]}**")
                st.markdown(f"Precio: **${b_row['price']:,.2f} MXN**")
                diff = subtotal - b_row['price']
                st.caption(f"Ahorras **${diff:,.2f}** vs sueltos")

    st.markdown("---")
    st.markdown("#### 📄 Ficha para el Paciente / Cliente:")
    w1, w2, w3 = st.columns(3)
    with w1:
        patient_name = st.text_input("Nombre del Paciente", value="Paciente", key="q_pat_name")
    with w2:
        doctor_name = st.text_input("Médico / Clínica", value="Dr. Particular", key="q_doc_name")
    with w3:
        notes = st.text_input("Indicaciones de Ayuno", value="Ayuno de 8 a 12 horas. Presentar primera orina de la mañana.", key="q_notes")

    today_str = datetime.now().strftime("%d/%m/%Y")
    studies_text = "\n".join([f"  • {r['study_name']} - ${r['price']:,.2f}" for _, r in df_quote.iterrows()])
    whatsapp_msg = f"""📋 *COTIZACIÓN DE ESTUDIOS CLÍNICOS*
👤 *Paciente:* {patient_name}
👨‍⚕️ *Solicitante:* {doctor_name}
📅 *Fecha:* {today_str}
📍 *Laboratorio de Referencia:* Chopo Mérida (Altabrisa)

*Estudios solicitados:*
{studies_text}

💰 *Subtotal regular:* ${subtotal:,.2f} MXN
🏷️ *Descuento aplicado:* {discount_pct}% (-${discount_amount:,.2f})
✅ *TOTAL A PAGAR:* ${final_total:,.2f} MXN

📌 *Indicaciones:*
{notes}
"""

    st.text_area("Copia este texto y pégalo directamente en WhatsApp:", value=whatsapp_msg, height=200)

    col_exp, _ = st.columns([2, 5])
    with col_exp:
        quote_dict = df_quote[["study_name", "category", "price"]].to_dict("records")
        if st.button("📥 Exportar Esta Cotización a Excel", use_container_width=True):
            fp = export_to_excel(quote_dict)
            st.success(f"Cotización exportada a: `{fp}`")


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

    st.markdown("---")
    st.markdown("#### 🎮 Controles del Servicio:")
    btn_c1, btn_c2, btn_c3, btn_c4 = st.columns(4)

    with btn_c1:
        if not is_running:
            if st.button("🟢 Iniciar Scheduler", type="primary", use_container_width=True):
                ok, msg = start_scheduler()
                if ok: st.success(msg)
                else: st.error(msg)
                st.rerun()
        else:
            st.button("🟢 Servicio Activo", disabled=True, use_container_width=True)

    with btn_c2:
        if is_running:
            if st.button("🔴 Detener Scheduler", type="secondary", use_container_width=True):
                ok, msg = stop_scheduler()
                if ok: st.warning(msg)
                else: st.error(msg)
                st.rerun()
        else:
            st.button("🔴 Servicio Detenido", disabled=True, use_container_width=True)

    with btn_c3:
        if is_running:
            if st.button("🔄 Reiniciar Servicio", use_container_width=True):
                ok, msg = restart_scheduler()
                st.info(msg)
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
    """Verifica si el usuario está autenticado. Si no, muestra la pantalla de login."""
    if st.session_state.get("authenticated", False):
        return True

    correct_password = "chopo2026"
    try:
        if hasattr(st, "secrets") and "APP_PASSWORD" in st.secrets:
            correct_password = st.secrets["APP_PASSWORD"]
    except Exception:
        pass
    import os
    correct_password = os.getenv("APP_PASSWORD", correct_password)

    _, col_login, _ = st.columns([1, 2, 1])
    with col_login:
        st.markdown("<div style='height:40px'></div>", unsafe_allow_html=True)
        st.markdown(
            """
            <div style="background:#ffffff;padding:30px;border-radius:12px;box-shadow:0 4px 15px rgba(0,0,0,0.08);text-align:center;border:1px solid #e0e0e0;">
                <h2 style="color:#1a5276;margin-bottom:5px;">🔬 Chopo Price Intelligence</h2>
                <p style="color:#666;font-size:0.95rem;margin-bottom:20px;">Portal de Análisis de Precios · Mérida, Yucatán</p>
                <p style="color:#333;font-size:0.9rem;text-align:left;margin-bottom:5px;">🔒 Ingresa la clave de acceso de tu equipo:</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.form("login_form"):
            password_input = st.text_input("Clave de acceso", type="password", placeholder="Escribe la clave aquí...", label_visibility="collapsed")
            submit = st.form_submit_button("🔓 Ingresar al Portal", type="primary", use_container_width=True)

            if submit:
                if password_input == correct_password:
                    st.session_state["authenticated"] = True
                    st.rerun()
                else:
                    st.error("❌ Clave incorrecta. Por favor verifícala.")

        st.caption("🔒 Acceso exclusivo para colaboradores y equipo autorizado.")

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

    tab0, tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
        "⭐ Favoritos",
        "📋 Catálogo",
        "🏷️ Descuentos & Promos",
        "💼 Cotizador de Paquetes",
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


if __name__ == "__main__":
    main()
