# ============================================================
# dashboard/lcm_comparator.py
# Módulo de Comparativa de Precios: LCM vs Chopo Mérida
# Con Edición Manual de Precios, Subida de Catálogos (XLSX/CSV)
# y Gestor de Paquetes / Promociones con Plazos de Vigencia
# ============================================================

import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional
import io
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

from scraper.lcm_manager import (
    load_price_overrides,
    save_price_override,
    delete_price_override,
    load_promotions,
    add_or_update_promotion,
    delete_promotion,
    archive_promotion,
    unarchive_promotion,
    get_available_periods,
    get_study_price_history,
    detect_columns,
    process_uploaded_catalog,
    get_consolidated_matches,
    load_adicionales,
    calculate_best_lcm_price,
    get_adicionales_lookup,
    get_active_promos_lookup,
)
from scraper.favorites_manager import (
    get_favorite_study_names,
    add_favorite_study,
    remove_favorite_study,
)



DATA_FILE = Path(__file__).parent.parent / "data" / "lcm" / "lcm_chopo_matches.json"


@st.cache_data(ttl=300)
def load_comparison_data() -> Dict[str, Any]:
    """Carga los datos consolidados de matching con modificaciones manuales aplicadas."""
    return get_consolidated_matches()


def format_currency(val: Any, default: str = "N/D") -> str:
    if val is None or pd.isna(val) or str(val).strip() in ("", "None", "nan", "N/D", "N/A"):
        return default
    try:
        clean = float(re.sub(r"[^\d.]", "", str(val)))
        return f"${clean:,.2f}"
    except (ValueError, TypeError):
        return default


def format_pct(val: Any) -> str:
    if val is None or pd.isna(val) or str(val).strip() in ("", "None", "nan", "N/D", "N/A"):
        return "N/D"
    try:
        clean = float(re.sub(r"[^\d.-]", "", str(val)))
        return f"{clean:+.1f}%"
    except (ValueError, TypeError):
        return "N/D"


def format_diff(val: Any) -> str:
    if val is None or pd.isna(val) or str(val).strip() in ("", "None", "nan", "N/D", "N/A"):
        return "N/D"
    try:
        clean = float(re.sub(r"[^\d.-]", "", str(val)))
        return f"${clean:+,.2f}"
    except (ValueError, TypeError):
        return "N/D"


def render_lcm_comparator_tab(chopo_prices: list):
    """Pestaña principal de Comparativa de Precios LCM vs Chopo."""
    try:
        data = load_comparison_data()
    except Exception as e:
        st.error(f"Error al cargar datos comparativos de LCM: {e}")
        return

    meta = data.get("metadata", {})
    matches = data.get("matches", [])
    adicionales = data.get("adicionales", [])
    promotions = load_promotions()
    overrides = load_price_overrides()

    is_admin = st.session_state.get("is_admin", False)

    # ── Banner Superior ───────────────────────────────────────────────────────
    st.markdown("""
    <div style="background: linear-gradient(135deg, #1e3a8a 0%, #0284c7 100%); color: white; padding: 22px 26px; border-radius: 12px; margin-bottom: 22px;">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">
            <div>
                <h2 style="margin:0; color:#ffffff; font-size:1.6rem; font-weight:800;">
                    ⚖️ Inteligencia Competitiva: LCM vs Chopo Mérida
                </h2>
                <p style="margin:4px 0 0 0; opacity:0.9; font-size:0.92rem;">
                    Cruce de catálogo general, promociones activas y análisis estratégico de precios frente a Chopo Mérida Altabrisa
                </p>
            </div>
            <div style="text-align: right;">
                <span style="background: rgba(255,255,255,0.2); padding: 5px 14px; border-radius: 20px; font-size: 0.82rem; font-weight:600;">
                    🏢 Laboratorios Clínicos de Mérida
                </span>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Tarjetas KPI Resumen ───────────────────────────────────────────────────
    total_lcm = meta.get("total_lcm_studies", len(matches))
    actionable = meta.get("actionable_matched_count", 0)
    actionable_pct = meta.get("actionable_matched_pct", 0.0)
    p_analysis = meta.get("price_analysis", {})
    lcm_cheaper = p_analysis.get("lcm_cheaper_count", 0)
    lcm_cheaper_pct = p_analysis.get("lcm_cheaper_pct", 0.0)
    active_promos_count = sum(1 for p in promotions if p.get("status") in ("ACTIVE", "PERMANENT", "EXPIRING_SOON"))

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    with kpi1:
        st.metric(
            label="Catálogo LCM Analizado",
            value=f"{total_lcm:,}",
            delta=f"{len(overrides)} modificados" if overrides else None,
            delta_color="off",
            help="Total de estudios en la base de datos LCM (con modificaciones manuales aplicadas)"
        )
    with kpi2:
        st.metric(
            label="Estudios Homologados",
            value=f"{actionable:,}",
            delta=f"{actionable_pct}% de cobertura",
            delta_color="normal",
            help="Estudios de LCM con contraparte directa o de alta similitud en Chopo"
        )
    with kpi3:
        st.metric(
            label="LCM Más Económico",
            value=f"{lcm_cheaper:,}",
            delta=f"{lcm_cheaper_pct}% de los comparados",
            delta_color="normal",
            help="Estudios donde el precio de LCM es menor al precio de descuento web de Chopo"
        )
    with kpi4:
        st.metric(
            label="Promos Activas",
            value=f"{active_promos_count} paquetes",
            delta=f"{len(promotions)} totales configurados",
            delta_color="off",
            help="Promociones y paquetes vigentes configurados con plazos"
        )

    st.markdown("<div style='height:15px'></div>", unsafe_allow_html=True)

    # ── Sub-pestañas ──────────────────────────────────────────────────────────
    subtab1, subtab2, subtab3, subtab4 = st.tabs([
        "🔍 Buscador Cara a Cara & Edición",
        "🎁 Paquetes & Promociones (Plazos)",
        "📊 Matriz Completa & Excel",
        "📤 Subir Catálogo (XLSX / CSV)"
    ])

    # =========================================================================
    # SUBTAB 1: Buscador Cara a Cara & Edición Manual
    # =========================================================================
    with subtab1:
        st.markdown("#### 🎯 Comparador Directo Estudio por Estudio")
        st.caption("Selecciona cualquier estudio del catálogo LCM para ver el contraste directo de precios y ajustar valores si están desfasados.")

        # Opciones para el selectbox
        study_options = []
        study_map = {}
        for m in matches:
            p_lcm_str = f"${m['lcm_price']:,.2f}" if m.get("lcm_price") is not None else "N/D"
            mod_badge = " [✏️ Modificado]" if m.get("is_manually_edited") else ""
            label = f"[{m.get('lcm_code', '')}] {m.get('lcm_name', '')} ({p_lcm_str}){mod_badge}"
            if m.get("match_type") != "NO_MATCH" and m.get("chopo_name"):
                diff_val = m.get("diff_mxn")
                if diff_val is not None:
                    diff_sign = "-" if diff_val < 0 else "+"
                    diff_str = f"LCM {diff_sign}${abs(diff_val):,.2f}"
                    label += f" ── vs Chopo: {m['chopo_name'][:30]}... ({diff_str})"
                else:
                    label += f" ── vs Chopo: {m['chopo_name'][:30]}... (Precio N/D)"
            else:
                label += " ── (Exclusivo LCM / Sin homólogo en Chopo)"
            study_options.append(label)
            study_map[label] = m

        selected_label = st.selectbox(
            "Selecciona o escribe el estudio que deseas comparar o editar:",
            options=study_options,
            index=0 if study_options else None
        )

        if selected_label and selected_label in study_map:
            item = study_map[selected_label]

            # Control de Favorito directo desde el comparador
            fav_study_key = item.get("chopo_name") or item.get("lcm_name")
            user_favs = st.session_state.get("user_favorites_set")
            if user_favs is None:
                user_favs = get_favorite_study_names()
                st.session_state["user_favorites_set"] = user_favs

            is_fav = (item.get("chopo_name") in user_favs) or (item.get("lcm_name") in user_favs)

            c_info_bar, c_fav_btn = st.columns([3.8, 1.2])
            with c_info_bar:
                st.caption(f"📌 Estudio seleccionado: **{item.get('lcm_name')}** · Clave `{item.get('lcm_code')}`")
            with c_fav_btn:
                if is_fav:
                    if st.button("⭐ En Favoritos (Quitar)", key=f"fav_btn_toggle_{item.get('lcm_code')}", use_container_width=True):
                        if item.get("chopo_name"):
                            remove_favorite_study(item["chopo_name"])
                            user_favs.discard(item["chopo_name"])
                        if item.get("lcm_name"):
                            remove_favorite_study(item["lcm_name"])
                            user_favs.discard(item["lcm_name"])
                        st.session_state["user_favorites_set"] = user_favs
                        st.toast(f"'{fav_study_key}' removido de tus favoritos")
                        st.rerun()
                else:
                    if st.button("☆ Agregar a Favoritos", key=f"fav_btn_toggle_{item.get('lcm_code')}", type="primary", use_container_width=True):
                        add_favorite_study(fav_study_key)
                        user_favs.add(fav_study_key)
                        st.session_state["user_favorites_set"] = user_favs
                        st.toast(f"⭐ '{fav_study_key}' agregado a tus favoritos!")
                        st.rerun()

            col_lcm, col_vs, col_chopo = st.columns([5, 1, 5])

            with col_lcm:
                is_mod = item.get("is_manually_edited", False)
                mod_notice = ""
                if is_mod:
                    orig_p = item.get("lcm_price_original", 0)
                    mod_notice = f"""
                    <div style="background:#fef3c7; border:1px solid #fde047; padding:4px 10px; border-radius:6px; font-size:0.75rem; color:#854d0e; margin-top:8px;">
                        ✏️ <b>Precio actualizado manualmente</b> (Original de lista: ${orig_p:,.2f})
                    </div>
                    """

                # Cálculo de Mejor Tarifa (Lista vs Adicional en Check-up vs Promo Activa)
                best_calc = calculate_best_lcm_price(
                    item.get("lcm_code"),
                    item.get("lcm_name"),
                    float(item.get("lcm_price") or 0.0),
                    with_checkup=True
                )

                extra_rates_html = ""
                if best_calc["has_bundle_price"] or best_calc["has_promo_price"]:
                    p_bundle_str = f"${best_calc['price_bundle']:,.2f}" if best_calc["has_bundle_price"] else "N/A"
                    p_promo_str = f"${best_calc['price_promo']:,.2f}" if best_calc["has_promo_price"] else "N/A"
                    extra_rates_html = f"""
                    <div style="display:grid; grid-template-columns: 1fr 1fr; gap:8px; margin-top:8px;">
                        <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:6px; padding:6px 10px;">
                            <span style="font-size:0.7rem; color:#64748b; font-weight:700; display:block;">En Check-Up (Adicional)</span>
                            <span style="font-size:1.05rem; font-weight:800; color:{'#0284c7' if best_calc['has_bundle_price'] else '#94a3b8'};">{p_bundle_str}</span>
                        </div>
                        <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:6px; padding:6px 10px;">
                            <span style="font-size:0.7rem; color:#64748b; font-weight:700; display:block;">Promoción Activa</span>
                            <span style="font-size:1.05rem; font-weight:800; color:{'#16a34a' if best_calc['has_promo_price'] else '#94a3b8'};">{p_promo_str}</span>
                        </div>
                    </div>
                    <div style="background:#ecfdf5; border:1px solid #6ee7b7; border-radius:8px; padding:10px 12px; margin-top:10px;">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <span style="color:#065f46; font-size:0.75rem; font-weight:800; text-transform:uppercase;">💡 Mejor Tarifa LCM</span>
                            <span style="background:#d1fae5; color:#065f46; font-size:0.72rem; font-weight:700; padding:2px 8px; border-radius:10px;">Ahorro: ${best_calc['savings_mxn']:,.2f}</span>
                        </div>
                        <div style="color:#059669; font-size:1.45rem; font-weight:800; margin:2px 0;">
                            ${best_calc['best_price']:,.2f} <small style="font-size:0.8rem; font-weight:600; color:#047857;">MXN</small>
                        </div>
                        <div style="color:#047857; font-size:0.8rem; margin:0; line-height:1.3;">{best_calc['explanation']}</div>
                    </div>
                    """

                st.markdown(f"""
                <div style="background:#f8fafc; border:2px solid #0284c7; border-radius:12px; padding:20px; box-shadow:0 2px 8px rgba(0,0,0,0.05);">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                        <span style="background:#e0f2fe; color:#0369a1; font-weight:700; font-size:0.8rem; padding:4px 10px; border-radius:12px;">
                            LCM · Clave {item.get('lcm_code', 'N/D')}
                        </span>
                        <span style="color:#64748b; font-size:0.82rem; font-weight:600;">Laboratorios Clínicos de Mérida</span>
                    </div>
                    <h3 style="color:#0f172a; margin:0 0 14px 0; font-size:1.15rem; line-height:1.4;">
                        {item.get('lcm_name', 'N/D')}
                    </h3>
                    <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:8px; padding:12px; margin-top:6px;">
                        <span style="color:#64748b; font-size:0.75rem; font-weight:600; text-transform:uppercase;">Precio de Lista Oficial (con IVA)</span>
                        <div style="color:#0284c7; font-size:1.75rem; font-weight:800; margin-top:2px;">
                            {format_currency(item.get('lcm_price'))} <small style="font-size:0.85rem; font-weight:600; color:#64748b;">MXN</small>
                        </div>
                    </div>
                    {extra_rates_html}
                    {mod_notice}
                </div>
                """, unsafe_allow_html=True)


            with col_vs:
                st.markdown("<div style='height:70px'></div><div style='text-align:center; font-size:1.4rem; font-weight:800; color:#94a3b8;'>VS</div>", unsafe_allow_html=True)

            with col_chopo:
                if item.get("match_type") != "NO_MATCH" and item.get("chopo_name"):
                    c_web = item.get("chopo_price_web")
                    c_list = item.get("chopo_price_list")
                    st.markdown(f"""
                    <div style="background:#f8fafc; border:2px solid #64748b; border-radius:12px; padding:20px; box-shadow:0 2px 8px rgba(0,0,0,0.05);">
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                            <span style="background:#f1f5f9; color:#334155; font-weight:700; font-size:0.8rem; padding:4px 10px; border-radius:12px;">
                                Chopo Altabrisa · {item.get('confidence', 0)}% similitud
                            </span>
                            <span style="color:#64748b; font-size:0.82rem; font-weight:600;">Laboratorio Chopo</span>
                        </div>
                        <h3 style="color:#0f172a; margin:0 0 14px 0; font-size:1.15rem; line-height:1.4;">
                            {item.get('chopo_name', 'N/D')}
                        </h3>
                        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:10px; margin-top:10px;">
                            <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:8px; padding:12px;">
                                <span style="color:#16a34a; font-size:0.75rem; font-weight:700; text-transform:uppercase;">Con Descuento Web</span>
                                <div style="color:#16a34a; font-size:1.5rem; font-weight:800; margin-top:2px;">
                                    {format_currency(c_web)}
                                </div>
                            </div>
                            <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:8px; padding:12px;">
                                <span style="color:#64748b; font-size:0.75rem; font-weight:700; text-transform:uppercase;">Precio Mostrador</span>
                                <div style="color:#475569; font-size:1.5rem; font-weight:800; margin-top:2px;">
                                    {format_currency(c_list)}
                                </div>
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown("""
                    <div style="background:#fef2f2; border:2px dashed #f87171; border-radius:12px; padding:25px; text-align:center; height:100%;">
                        <div style="font-size:2rem; margin-bottom:8px;">🔎</div>
                        <h4 style="color:#991b1b; margin:0 0 6px 0;">Sin Homólogo Directo en Chopo</h4>
                        <p style="color:#7f1d1d; font-size:0.88rem; margin:0;">
                            Este estudio es exclusivo de la oferta de LCM o está registrado bajo una prueba compuesta no catalogada individualmente en Chopo Mérida.
                        </p>
                    </div>
                    """, unsafe_allow_html=True)

            # Veredicto y análisis de brecha
            if item.get("match_type") != "NO_MATCH" and item.get("diff_mxn") is not None:
                diff_val = item["diff_mxn"]
                diff_pct = item.get("diff_pct", 0)
                st.markdown("<div style='height:15px'></div>", unsafe_allow_html=True)
                if diff_val < 0:
                    st.success(f"""
                    🎉 **Veredicto Comercial: LCM es más económico**  
                    El paciente ahorra **${abs(diff_val):,.2f} MXN ({abs(diff_pct)}%)** realizándose el estudio en **LCM** en comparación con el precio de descuento web de Chopo Mérida.
                    """)
                elif diff_val > 0:
                    st.warning(f"""
                    ⚠️ **Veredicto Comercial: Chopo ofrece menor precio en canal web**  
                    Chopo está posicionado **${diff_val:,.2f} MXN ({diff_pct}%)** por debajo de LCM en este estudio en su portal web.
                    """)
                else:
                    st.info("🤝 **Veredicto Comercial: Mismo precio exacto** en ambos laboratorios.")

            # ── Panel de Modificación Manual de Precio ────────────────────────
            with st.expander("✏️ ¿El precio de LCM cambió o está desfasado? Modifícalo aquí", expanded=False):
                st.markdown(f"**Estudio a editar:** `{item.get('lcm_code')}` - **{item.get('lcm_name')}**")
                edit_c1, edit_c2 = st.columns([1, 2])
                with edit_c1:
                    cur_p = float(item.get("lcm_price") or 0.0)
                    new_price_val = st.number_input(
                        "Nuevo Precio LCM ($ MXN):",
                        min_value=0.0,
                        max_value=200000.0,
                        value=cur_p,
                        step=10.0,
                        format="%.2f",
                        key=f"edit_p_{item.get('lcm_code')}"
                    )
                with edit_c2:
                    note_val = st.text_input(
                        "Motivo o fecha de actualización:",
                        value=item.get("manual_edit_notes", ""),
                        placeholder="Ej. Actualizado según tarifa vigente septiembre",
                        key=f"note_p_{item.get('lcm_code')}"
                    )

                btn_col1, btn_col2 = st.columns([1, 1])
                with btn_col1:
                    if st.button("💾 Guardar Precio Actualizado", type="primary", use_container_width=True, key=f"btn_save_{item.get('lcm_code')}"):
                        code_key = item.get("lcm_code") or item.get("lcm_name")
                        save_price_override(code_key, item.get("lcm_name", ""), new_price_val, note_val)
                        st.cache_data.clear()
                        st.toast(f"✅ Precio de '{item.get('lcm_name')}' actualizado a ${new_price_val:,.2f}")
                        st.rerun()

                with btn_col2:
                    if item.get("is_manually_edited"):
                        if st.button("🔄 Restaurar Precio Original", type="secondary", use_container_width=True, key=f"btn_res_{item.get('lcm_code')}"):
                            code_key = item.get("lcm_code") or item.get("lcm_name")
                            delete_price_override(code_key)
                            st.cache_data.clear()
                            st.toast("Restaurado al precio original del catálogo.")
                            st.rerun()

    # =========================================================================
    # SUBTAB 2: Paquetes & Promociones con Plazos (Vigencias)
    # =========================================================================
    with subtab2:
        st.markdown("#### 🎁 Gestor de Paquetes, Promociones y Registro Histórico de LCM")
        st.caption("Administra campañas mensuales de Octubre, paquetes cuatrimestrales (vencen 31 de dic), promociones permanentes y consulta el histórico de períodos anteriores.")

        # ── 1. SELECTOR DE PERÍODO / CAMPAÑA Y FILTRO DE ESTATUS ────────────
        col_f1, col_f2 = st.columns([2, 1])
        with col_f1:
            period_options = [
                "🌟 Todos los Períodos (Activas, Futuras y Pasadas)",
                "🍁 Octubre 2026 (Mensual - Inicia Mañana)",
                "🍂 Cuatrimestre Sep - Dic 2026 (Vence 31 Dic)",
                "♾️ Permanentes (Sin Caducidad)",
                "📜 Septiembre 2026",
                "📜 Agosto 2026",
                "📜 Julio 2026",
                "📜 Junio 2026 (Día del Padre)",
                "📜 Mayo 2026 (Día de las Madres)",
                "📜 Cuatrimestre 2 (May - Ago 2026)",
                "📜 Abril 2026 (Día del Niño)",
                "📜 Marzo 2026 (Día de la Mujer)",
                "📜 Febrero 2026",
                "📜 Enero 2026",
                "📜 Cuatrimestre 1 (Ene - Abr 2026)",
                "🗂️ Ver Todo el Histórico de Períodos Anteriores"
            ]
            sel_period = st.selectbox("📅 Seleccionar Campaña / Período a consultar:", period_options, index=0)

        with col_f2:
            status_opts = ["Todos los estatus", "🟢 Solo Vigentes Hoy", "🟡 Próximas (Inician Mañana)", "🟠 Por Vencer (≤ 3 días)", "🔴 Finalizadas / Histórico"]
            sel_stat = st.selectbox("Filtro por estatus:", status_opts, index=0)

        # Banner informativo cuando se consulta el histórico
        if "Histórico" in sel_period or sel_period.startswith("📜"):
            st.info(f"📜 **Vista de Registro Histórico Activa**: Consultando las promociones y paquetes del período **{sel_period}**. Este registro permite auditar las tarifas pasadas de LCM y compararlas con las tarifas actuales.")

        # Filtrar promociones
        filtered_promos = []
        for p in promotions:
            st_code = p.get("status", "ACTIVE")
            p_period = str(p.get("period", ""))
            is_arch = p.get("is_archived", False)

            # Filtro por período
            if sel_period.startswith("🌟"):
                pass
            elif sel_period == "🍁 Octubre 2026 (Mensual - Inicia Mañana)":
                if p_period != "Octubre 2026":
                    continue
            elif sel_period == "🍂 Cuatrimestre Sep - Dic 2026 (Vence 31 Dic)":
                if p_period != "Cuatrimestre Sep - Dic 2026":
                    continue
            elif sel_period == "♾️ Permanentes (Sin Caducidad)":
                if p_period != "Permanentes":
                    continue
            elif sel_period == "🗂️ Ver Todo el Histórico de Períodos Anteriores":
                if not (is_arch or st_code in ("EXPIRED", "ARCHIVED")):
                    continue
            else:
                # Extraer nombre limpio del periodo
                clean_target = sel_period.replace("📜", "").split("(")[0].strip().lower()
                if clean_target not in p_period.lower() and p_period.lower() not in clean_target:
                    continue

            # Filtro por estatus
            if sel_stat == "🟢 Solo Vigentes Hoy" and st_code not in ("ACTIVE", "PERMANENT"):
                continue
            elif sel_stat == "🟡 Próximas (Inician Mañana)" and st_code != "UPCOMING":
                continue
            elif sel_stat == "🟠 Por Vencer (≤ 3 días)" and st_code != "EXPIRING_SOON":
                continue
            elif sel_stat == "🔴 Finalizadas / Histórico" and not (is_arch or st_code in ("EXPIRED", "ARCHIVED")):
                continue

            filtered_promos.append(p)

        # Métricas resumidas del período seleccionado
        if filtered_promos:
            p_prices = [p.get("price_promo") for p in filtered_promos if p.get("price_promo") is not None]
            avg_p = sum(p_prices) / len(p_prices) if p_prices else 0.0
            mc1, mc2, mc3 = st.columns(3)
            with mc1:
                st.metric("Promociones / Paquetes en Vista", len(filtered_promos))
            with mc2:
                st.metric("Precio Promedio Promoción", f"${avg_p:,.2f}" if avg_p > 0 else "N/A")
            with mc3:
                upc_count = sum(1 for p in filtered_promos if p.get("status") == "UPCOMING")
                act_count = sum(1 for p in filtered_promos if p.get("status") in ("ACTIVE", "PERMANENT"))
                st.metric("Estado Campaña", f"{act_count} activas · {upc_count} inician mañana")

            # Renderizar tarjetas en rejilla
            cols = st.columns(2)
            for i, p in enumerate(filtered_promos):
                with cols[i % 2]:
                    st_code = p.get("status", "ACTIVE")
                    st_label = p.get("status_label", "Activa")
                    chopo_eq = p.get("chopo_equivalent", "No especificado")
                    price_promo = p.get("price_promo", 0.0)
                    price_reg = p.get("price_regular")
                    reg_str = f"<span style='font-size:0.8rem; color:#94a3b8; text-decoration:line-through;'>${price_reg:,.2f}</span>" if price_reg else ""
                    studies_str = ", ".join(p.get("studies", [])) if p.get("studies") else "Sin desglose"
                    p_period_badge = p.get("period", "General")

                    if st_code == "UPCOMING":
                        border_color = "#eab308"
                        bg_badge = "#fef9c3"
                        col_badge = "#854d0e"
                    elif st_code in ("ACTIVE", "PERMANENT"):
                        border_color = "#22c55e"
                        bg_badge = "#ecfdf5"
                        col_badge = "#15803d"
                    elif st_code == "EXPIRING_SOON":
                        border_color = "#f97316"
                        bg_badge = "#ffedd5"
                        col_badge = "#9a3412"
                    else:
                        border_color = "#94a3b8"
                        bg_badge = "#f1f5f9"
                        col_badge = "#475569"

                    start_str = p.get("start_date", "")
                    end_str = p.get("end_date", "")
                    dates_info = ""
                    if start_str and end_str:
                        dates_info = f"<span style='font-size:0.75rem; color:#64748b;'>🗓️ Vigencia: <b>{start_str}</b> al <b>{end_str}</b></span>"
                    elif end_str:
                        dates_info = f"<span style='font-size:0.75rem; color:#64748b;'>🗓️ Vence: <b>{end_str}</b></span>"
                    elif st_code == "PERMANENT":
                        dates_info = "<span style='font-size:0.75rem; color:#0284c7;'>♾️ Tarifa permanente sin vencimiento</span>"

                    st.markdown(f"""
                    <div style="background:#ffffff; border:1px solid #e2e8f0; border-top:4px solid {border_color}; border-radius:10px; padding:16px; margin-bottom:14px; box-shadow:0 2px 6px rgba(0,0,0,0.04);">
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                            <span style="font-weight:700; font-size:0.78rem; background:{bg_badge}; color:{col_badge}; padding:2px 8px; border-radius:6px;">{st_label}</span>
                            <span style="background:#e0f2fe; color:#0369a1; font-weight:700; font-size:0.75rem; padding:2px 8px; border-radius:10px;">{p_period_badge}</span>
                        </div>
                        <h4 style="color:#0f172a; margin:6px 0 4px 0; font-size:1.15rem;">{p.get('name')}</h4>
                        <p style="color:#64748b; font-size:0.82rem; margin:0 0 6px 0;"><b>Estudios:</b> {studies_str}</p>
                        <div style="margin-bottom:8px;">{dates_info}</div>
                        <div style="display:flex; justify-content:space-between; align-items:baseline; background:#f8fafc; padding:10px 14px; border-radius:8px;">
                            <div>
                                <span style="font-size:0.72rem; color:#64748b; display:block;">Precio Promoción LCM</span>
                                <span style="font-size:1.5rem; font-weight:800; color:#0284c7;">${price_promo:,.2f}</span> {reg_str}
                            </div>
                            <div style="text-align:right;">
                                <span style="font-size:0.72rem; color:#64748b; display:block;">Contraparte Chopo</span>
                                <span style="font-size:0.82rem; font-weight:700; color:#475569;">{chopo_eq[:28]}</span>
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    if p.get("notes"):
                        st.caption(f"💡 *Nota:* {p.get('notes')}")

                    if is_admin:
                        btn_c1, btn_c2 = st.columns(2)
                        with btn_c1:
                            if not p.get("is_archived"):
                                if st.button("📦 Archivar", key=f"arch_{p.get('id')}", use_container_width=True):
                                    archive_promotion(p.get("id"))
                                    st.toast(f"'{p.get('name')}' archivada en el histórico.")
                                    st.rerun()
                            else:
                                if st.button("🔄 Reactivar", key=f"unarch_{p.get('id')}", use_container_width=True):
                                    unarchive_promotion(p.get("id"))
                                    st.toast(f"'{p.get('name')}' reactivada.")
                                    st.rerun()
                        with btn_c2:
                            if st.button("🗑️ Eliminar", key=f"del_{p.get('id')}", type="secondary", use_container_width=True):
                                delete_promotion(p.get("id"))
                                st.toast("Promoción eliminada.")
                                st.rerun()
        else:
            st.info("No hay promociones registradas para la combinación de período y estatus seleccionada.")

        # ── 2. COMPARATIVA HISTÓRICA DE PRECIOS POR ESTUDIO ─────────────────
        with st.expander("📈 Consultar Evolución de Precios Históricos por Estudio", expanded=False):
            st.caption("Selecciona cualquier estudio para consultar el histórico de precios que ha tenido en Agosto, Septiembre, Octubre 2026, Paquetes Cuatrimestrales y Catálogo General.")
            all_lcm_names = sorted(list({m.get("lcm_name") for m in matches if m.get("lcm_name")}))
            default_study_idx = all_lcm_names.index("Perfil tiroideo") if "Perfil tiroideo" in all_lcm_names else 0
            sel_hist_study = st.selectbox("Selecciona el estudio clínico a auditar:", options=all_lcm_names, index=default_study_idx)

            hist_data = get_study_price_history(sel_hist_study)
            if hist_data:
                df_h = pd.DataFrame(hist_data)
                cols_to_show = ["period", "promo_name", "price", "price_regular", "status_label", "start_date", "end_date"]
                present_cols = [c for c in cols_to_show if c in df_h.columns]
                st.dataframe(
                    df_h[present_cols].rename(columns={
                        "period": "Campaña / Período",
                        "promo_name": "Nombre Registrado",
                        "price": "Precio Promo ($)",
                        "price_regular": "Precio Regular ($)",
                        "status_label": "Estado de Vigencia",
                        "start_date": "Fecha Inicio",
                        "end_date": "Fecha Fin"
                    }),
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info(f"El estudio '{sel_hist_study}' no cuenta con promociones especiales archivadas. Aplica precio de catálogo regular de lista.")

        # ── 3. EXPORTAR PROMOCIONES E HISTORIAL A EXCEL ──────────────────────
        with io.BytesIO() as b:
            with pd.ExcelWriter(b, engine="openpyxl") as writer:
                p_actives = [p for p in promotions if p.get("status") in ("ACTIVE", "PERMANENT", "UPCOMING", "EXPIRING_SOON")]
                if p_actives:
                    pd.DataFrame(p_actives)[["period", "name", "category", "price_promo", "price_regular", "start_date", "end_date", "status_label", "notes"]].to_excel(writer, sheet_name="Promos Vigentes y Octubre", index=False)
                p_hist = [p for p in promotions if p.get("status") in ("EXPIRED", "ARCHIVED") or p.get("is_archived")]
                if p_hist:
                    pd.DataFrame(p_hist)[["period", "name", "category", "price_promo", "price_regular", "start_date", "end_date", "status_label", "notes"]].to_excel(writer, sheet_name="Histórico Períodos", index=False)
                adic_full = load_adicionales()
                if adic_full:
                    pd.DataFrame(adic_full).to_excel(writer, sheet_name="Adicionales en Check-Up", index=False)
            b.seek(0)
            excel_promos_bytes = b.getvalue()

        st.download_button(
            "📥 Descargar Calendario de Promociones e Historial Completo (.xlsx)",
            data=excel_promos_bytes,
            file_name="LCM_Promociones_e_Historial_2026.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

        # ── 4. FORMULARIO DE CREACIÓN DE PROMOCIÓN CON CAMPAÑA / PERÍODO ────
        if is_admin:
            with st.expander("➕ Crear Nueva Promoción o Paquete con Período y Vigencia", expanded=False):
                st.markdown("Configura una nueva promoción asignando su campaña (ej. Noviembre 2026, Buen Fin), fecha de inicio y plazo de finalización.")
                with st.form("create_promo_form"):
                    fc1, fc2, fc3 = st.columns([2, 1, 1])
                    with fc1:
                        new_promo_name = st.text_input("Nombre de la Promoción / Paquete *", placeholder="Ej. Check Up Femenino Rosa, Promo Fin de Semana...")
                    with fc2:
                        new_promo_period = st.text_input("Campaña / Período *", value="Octubre 2026", placeholder="Ej. Octubre 2026, Noviembre 2026, Buen Fin...")
                    with fc3:
                        new_promo_cat = st.selectbox("Categoría:", ["Promo del Mes", "Promo Cuatrimestral", "Promo Permanente", "Promo Fin de Semana", "Flash 48h", "Convenio Especial"])

                    study_names_list = sorted(list({m.get("lcm_name") for m in matches if m.get("lcm_name")}))
                    selected_studies = st.multiselect(
                        "Estudios incluidos en el paquete (puedes seleccionar varios):",
                        options=study_names_list,
                        placeholder="Busca y agrega estudios (ej. Biometría, Glucosa, Tiroideo...)"
                    )

                    pc1, pc2, pc3 = st.columns(3)
                    with pc1:
                        new_promo_price = st.number_input("Precio Promoción ($ MXN) *", min_value=0.0, value=499.0, step=10.0, format="%.2f")
                    with pc2:
                        new_reg_price = st.number_input("Precio Regular / Anterior ($ MXN opcional)", min_value=0.0, value=0.0, step=10.0, format="%.2f")
                    with pc3:
                        new_chopo_eq = st.text_input("Contraparte sugerida en Chopo:", placeholder="Ej. CHECK UP BÁSICO Q45")

                    st.markdown("##### ⏱️ Fechas y Plazo de Vigencia")
                    vc1, vc2 = st.columns([1, 1])
                    with vc1:
                        today_d = date.today()
                        new_start_d = st.date_input("Fecha de Inicio:", value=today_d + timedelta(days=1) if today_d.day == 30 and today_d.month == 9 else today_d)
                    with vc2:
                        duration_mode = st.selectbox(
                            "Tipo de Plazo / Duración:",
                            [
                                "Hasta fin de mes (Mensual)",
                                "Cuatrimestral (Hasta 31 de Diciembre)",
                                "Días específicos (ej. 1, 2, 3, 7 días)",
                                "Fecha límite exacta (calendario)",
                                "1 Año (Anual)",
                                "Permanente (Sin fecha de caducidad)"
                            ]
                        )

                    calculated_end_date = None
                    if duration_mode == "Hasta fin de mes (Mensual)":
                        next_m = (new_start_d.replace(day=28) + timedelta(days=4)).replace(day=1)
                        eom = next_m - timedelta(days=1)
                        calculated_end_date = eom.isoformat()
                        st.caption(f"Vencerá el: **{calculated_end_date}** (fin de mes).")
                    elif duration_mode == "Cuatrimestral (Hasta 31 de Diciembre)":
                        calculated_end_date = f"{new_start_d.year}-12-31"
                        st.caption(f"Vencerá el: **{calculated_end_date}** (cierre de cuatrimestre).")
                    elif duration_mode == "Días específicos (ej. 1, 2, 3, 7 días)":
                        num_days = st.number_input("Número de días de duración:", min_value=1, max_value=365, value=3, step=1)
                        calculated_end_date = (new_start_d + timedelta(days=int(num_days))).isoformat()
                        st.caption(f"Vencerá el: **{calculated_end_date}** ({num_days} días).")
                    elif duration_mode == "Fecha límite exacta (calendario)":
                        exact_d = st.date_input("Fecha límite exacta:", min_value=new_start_d, value=new_start_d + timedelta(days=15))
                        calculated_end_date = exact_d.isoformat()
                    elif duration_mode == "1 Año (Anual)":
                        calculated_end_date = (new_start_d + timedelta(days=365)).isoformat()
                    else:
                        calculated_end_date = None
                        st.caption("Esta promoción no tiene fecha límite y permanecerá activa indefinidamente.")

                    promo_notes = st.text_area("Notas internas o instrucciones de venta:", placeholder="Ej. Aplica solo pago en efectivo o para pacientes de primera vez...")

                    submit_promo = st.form_submit_button("🚀 Crear y Publicar Promoción", type="primary", use_container_width=True)
                    if submit_promo:
                        if not new_promo_name.strip():
                            st.error("Por favor ingresa un nombre para la promoción.")
                        else:
                            v_type = "permanent" if duration_mode.startswith("Permanente") else "custom_date"
                            promo_payload = {
                                "name": new_promo_name.strip(),
                                "period": new_promo_period.strip(),
                                "category": new_promo_cat,
                                "validity_type": v_type,
                                "start_date": new_start_d.isoformat() if v_type != "permanent" else None,
                                "end_date": calculated_end_date,
                                "studies": selected_studies,
                                "price_regular": float(new_reg_price) if new_reg_price > 0 else None,
                                "price_promo": float(new_promo_price),
                                "chopo_equivalent": new_chopo_eq.strip() if new_chopo_eq else "Comparativa abierta",
                                "notes": promo_notes.strip()
                            }
                            add_or_update_promotion(promo_payload)
                            st.success(f"🎉 Promoción '{new_promo_name}' guardada exitosamente.")
                            st.rerun()

        # ── Cotizador Inteligente de Check-Up + Adicionales (Mejor Tarifa) ──
        st.markdown("---")
        st.markdown("### 🧮 Cotizador Inteligente: Check-Up + Estudios Adicionales")
        st.caption("Arma una cotización completa para el paciente. El sistema **aplica automáticamente la regla del mejor precio**: si una promoción de Octubre o cuatrimestral es más barata que el precio adicional, se respeta la promoción; si el precio adicional es menor, aplica el adicional.")

        # Selector de Tarifas a Considerar
        qc1, qc2 = st.columns([2, 1])
        with qc1:
            cotiz_mode = st.selectbox(
                "Tarifas promocionales a considerar en la cotización:",
                [
                    "🍁 Octubre 2026 + Cuatrimestrales + Permanentes (Inician mañana - RECOMENDADO)",
                    "🟢 Solo promociones estrictamente vigentes hoy",
                    "📜 Simular con tarifas de Septiembre 2026",
                    "📜 Simular con tarifas de Agosto 2026",
                    "📜 Simular con tarifas de Julio 2026",
                    "📜 Simular con tarifas de Junio 2026 (Día del Padre)",
                    "📜 Simular con tarifas de Mayo 2026 (Día de las Madres)",
                    "📜 Simular con tarifas de Enero 2026",
                    "📋 Solo precios regulares de catálogo (Sin promociones)"
                ]
            )
        with qc2:
            st.caption("💡 *Tip comercial:* Puedes cotizar ya con las tarifas de Octubre o simular cómo cotizaba en cualquier mes del año 2026.")

        inc_upcoming = True
        target_per = None
        if cotiz_mode.startswith("🍁"):
            inc_upcoming = True
            target_per = None
        elif cotiz_mode.startswith("🟢"):
            inc_upcoming = False
            target_per = None
        elif cotiz_mode.startswith("📜"):
            inc_upcoming = False
            for m_name in ["Septiembre", "Agosto", "Julio", "Junio", "Mayo", "Abril", "Marzo", "Febrero", "Enero"]:
                if m_name in cotiz_mode:
                    target_per = f"{m_name} 2026"
                    break
        elif cotiz_mode.startswith("📋"):
            inc_upcoming = False
            target_per = "NINGUNO"

        base_pkg_opts = [
            "Check Up Esencial LCM ($549.00)",
            "Checkup Avanzado LCM ($890.00)",
            "Checkup Integral Plus LCM ($998.00)",
            "Check Up Inicial LCM ($470.00)",
            "Check Up Tiroideo Esencial LCM ($1,050.00)",
            "[Sin Check-Up Base (Cotizar solo estudios sueltos con mejor tarifa)]"
        ]

        c_quote1, c_quote2 = st.columns([1, 2])
        with c_quote1:
            sel_base_pkg = st.selectbox("1. Selecciona el Check-Up Base:", options=base_pkg_opts)
            base_price = 0.0
            has_checkup = False
            if "549" in sel_base_pkg:
                base_price = 549.0
                has_checkup = True
            elif "890" in sel_base_pkg:
                base_price = 890.0
                has_checkup = True
            elif "998" in sel_base_pkg:
                base_price = 998.0
                has_checkup = True
            elif "470" in sel_base_pkg:
                base_price = 470.0
                has_checkup = True
            elif "1,050" in sel_base_pkg or "1050" in sel_base_pkg:
                base_price = 1050.0
                has_checkup = True

        adic_list = load_adicionales()
        adic_names = [a.get("name") for a in adic_list if a.get("name")]
        all_studies_names = sorted(list({m.get("lcm_name") for m in matches if m.get("lcm_name")}))
        combo_options = adic_names + [n for n in all_studies_names if n not in adic_names]

        with c_quote2:
            default_adics = [a for a in ["Hemoglobina glicosilada", "Vitamina D (25-OH) total"] if a in combo_options]
            sel_adicionales = st.multiselect(
                "2. Selecciona Estudios Adicionales para agregar al paciente:",
                options=combo_options,
                default=default_adics,
                placeholder="Busca estudios (ej. Hemoglobina, Vitamina D, Rayos X, Ultrasonidos, Tiroideo...)"
            )

        if has_checkup or sel_adicionales:
            st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
            quote_rows = []
            total_adicionales_lcm = 0.0
            total_chopo_adicionales_web = 0.0
            total_chopo_adicionales_list = 0.0

            match_by_name = {m.get("lcm_name"): m for m in matches if m.get("lcm_name")}

            for ad_name in sel_adicionales:
                m_info = match_by_name.get(ad_name, {})
                s_code = m_info.get("lcm_code", "")
                p_list = float(m_info.get("lcm_price") or 0.0)

                best_calc = calculate_best_lcm_price(
                    s_code, ad_name, p_list,
                    with_checkup=has_checkup,
                    include_upcoming=inc_upcoming,
                    target_period=target_per
                )
                applied_p = best_calc["best_price"]
                total_adicionales_lcm += applied_p

                c_web = m_info.get("chopo_price_web")
                c_list = m_info.get("chopo_price_list")
                if c_web is not None:
                    total_chopo_adicionales_web += c_web
                if c_list is not None:
                    total_chopo_adicionales_list += c_list

                rule_badge = "🟢 Promo Gana" if best_calc["rule"] == "PROMOCION" else ("💡 Adicional Gana" if best_calc["rule"] == "ADICIONAL" else "📋 Precio Lista")

                quote_rows.append({
                    "Estudio": ad_name,
                    "Precio Lista": p_list,
                    "Tarifa en Check-Up": best_calc["price_bundle"],
                    "Tarifa Promo Activa": best_calc["price_promo"],
                    "Precio Aplicado": applied_p,
                    "Regla / Beneficio": rule_badge
                })

            grand_total_lcm = base_price + total_adicionales_lcm

            chopo_base_web = 0.0
            chopo_base_list = 0.0
            if "Esencial" in sel_base_pkg:
                chopo_base_web = 597.35
                chopo_base_list = 919.00
            elif "Avanzado" in sel_base_pkg:
                chopo_base_web = 915.86
                chopo_base_list = 1409.01
            elif "Integral Plus" in sel_base_pkg:
                chopo_base_web = 1175.85
                chopo_base_list = 1809.00
            elif "Tiroideo" in sel_base_pkg:
                chopo_base_web = 1069.25
                chopo_base_list = 1645.00
            elif "Inicial" in sel_base_pkg:
                chopo_base_web = 549.00
                chopo_base_list = 609.99

            grand_total_chopo_web = chopo_base_web + total_chopo_adicionales_web
            grand_total_chopo_list = chopo_base_list + total_chopo_adicionales_list

            ahorro_vs_chopo_web = grand_total_chopo_web - grand_total_lcm
            ahorro_vs_chopo_list = grand_total_chopo_list - grand_total_lcm

            tot_c1, tot_c2, tot_c3 = st.columns(3)
            with tot_c1:
                st.markdown(f"""
                <div style="background:#f0fdf4; border:2px solid #22c55e; border-radius:12px; padding:16px; text-align:center;">
                    <span style="font-size:0.78rem; font-weight:700; color:#15803d; text-transform:uppercase;">TOTAL COTIZACIÓN LCM</span>
                    <div style="font-size:2.2rem; font-weight:800; color:#16a34a; margin:4px 0;">
                        ${grand_total_lcm:,.2f} <small style="font-size:0.85rem; color:#15803d;">MXN</small>
                    </div>
                    <small style="color:#15803d; font-weight:600;">Check-Up: ${base_price:,.2f} + Adicionales: ${total_adicionales_lcm:,.2f}</small>
                </div>
                """, unsafe_allow_html=True)

            with tot_c2:
                st.markdown(f"""
                <div style="background:#f8fafc; border:1px solid #cbd5e1; border-radius:12px; padding:16px; text-align:center;">
                    <span style="font-size:0.78rem; font-weight:700; color:#475569; text-transform:uppercase;">TOTAL EN CHOPO MÉRIDA</span>
                    <div style="font-size:1.8rem; font-weight:800; color:#334155; margin:4px 0;">
                        ${grand_total_chopo_web:,.2f} <small style="font-size:0.8rem; color:#64748b;">(Web)</small>
                    </div>
                    <small style="color:#64748b; font-weight:600;">En Mostrador Chopo: ${grand_total_chopo_list:,.2f}</small>
                </div>
                """, unsafe_allow_html=True)

            with tot_c3:
                ahorro_label = "Ahorro Paciente" if ahorro_vs_chopo_web >= 0 else "Diferencia"
                color_a = "#15803d" if ahorro_vs_chopo_web >= 0 else "#dc2626"
                bg_a = "#ecfdf5" if ahorro_vs_chopo_web >= 0 else "#fef2f2"
                border_a = "#86efac" if ahorro_vs_chopo_web >= 0 else "#fca5a5"
                st.markdown(f"""
                <div style="background:{bg_a}; border:2px solid {border_a}; border-radius:12px; padding:16px; text-align:center;">
                    <span style="font-size:0.78rem; font-weight:700; color:{color_a}; text-transform:uppercase;">{ahorro_label} en LCM</span>
                    <div style="font-size:2.2rem; font-weight:800; color:{color_a}; margin:4px 0;">
                        ${abs(ahorro_vs_chopo_web):,.2f} <small style="font-size:0.85rem;">MXN</small>
                    </div>
                    <small style="color:{color_a}; font-weight:600;">Frente al mostrador de Chopo: Ahorro de ${abs(ahorro_vs_chopo_list):,.2f}</small>
                </div>
                """, unsafe_allow_html=True)

            if quote_rows:
                st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
                st.markdown("##### 📋 Desglose Detallado de Estudios Adicionales (Regla del Mejor Precio)")
                df_quote = pd.DataFrame(quote_rows)
                st.dataframe(
                    df_quote.style.format({
                        "Precio Lista": lambda x: format_currency(x, "N/D"),
                        "Tarifa en Check-Up": lambda x: format_currency(x, "N/A"),
                        "Tarifa Promo Activa": lambda x: format_currency(x, "N/A"),
                        "Precio Aplicado": lambda x: format_currency(x, "N/D"),
                    }),
                    use_container_width=True,
                    hide_index=True
                )

    # =========================================================================
    # SUBTAB 3: Matriz Completa & Excel
    # =========================================================================
    with subtab3:
        st.markdown("#### 📊 Matriz Consolidada de Estudios Homologados")
        st.caption("Filtra, analiza y exporta los estudios homologados entre LCM y Chopo Mérida Altabrisa con precios en tiempo real y tarifas preferenciales.")

        # Controles de filtrado
        fc1, fc2, fc3 = st.columns([2, 2, 3])
        with fc1:
            verdict_filter = st.selectbox(
                "Filtrar por Veredicto Comercial:",
                [
                    "Todos los estudios",
                    "⭐ Solo Mis Estudios Favoritos",
                    "🟢 Solo donde LCM es más barato",
                    "🔴 Solo donde Chopo es más barato",
                    "💡 Estudios con Tarifa Especial Adicional",
                    "🎁 Estudios en Promoción Activa / Próxima",
                    "✏️ Solo estudios modificados manualmente",
                    "🔎 Sin homólogo en Chopo"
                ]
            )
        with fc2:
            confidence_filter = st.selectbox(
                "Nivel de Confianza del Match:",
                ["Todos los niveles", "Exacto (100%)", "Alta (>=85%)", "Media (70-84%)"]
            )
        with fc3:
            search_query = st.text_input("Buscar estudio por nombre o clave:", placeholder="Ej. Tiroideo, Glucosa, Vitamina, 842...")

        adic_lookup = get_adicionales_lookup()
        promo_lookup = get_active_promos_lookup(include_upcoming=True)

        user_favs_set = st.session_state.get("user_favorites_set")
        if user_favs_set is None:
            user_favs_set = get_favorite_study_names()
            st.session_state["user_favorites_set"] = user_favs_set

        # Construir DataFrame
        df_rows = []
        for m in matches:
            diff_m = m.get("diff_mxn")
            is_mod = m.get("is_manually_edited", False)
            code_k = str(m.get("lcm_code", "")).strip()
            name_norm = str(m.get("lcm_name", "")).strip().upper()

            adic_match = adic_lookup.get(code_k) or adic_lookup.get(name_norm)
            p_bundle = adic_match.get("price_bundle") if adic_match else None

            p_promo_info = promo_lookup.get(name_norm)
            p_promo_val = p_promo_info.get("price") if p_promo_info else None
            p_promo_name = p_promo_info.get("promo_name") if p_promo_info else None
            p_promo_per = p_promo_info.get("period") if p_promo_info else None

            is_study_fav = (m.get("chopo_name") in user_favs_set) or (m.get("lcm_name") in user_favs_set)

            # Aplicar filtro de veredicto
            if verdict_filter == "⭐ Solo Mis Estudios Favoritos":
                if not is_study_fav:
                    continue
            elif verdict_filter == "🟢 Solo donde LCM es más barato":
                if diff_m is None or diff_m >= 0:
                    continue
            elif verdict_filter == "🔴 Solo donde Chopo es más barato":
                if diff_m is None or diff_m <= 0:
                    continue
            elif verdict_filter == "💡 Estudios con Tarifa Especial Adicional":
                if p_bundle is None:
                    continue
            elif verdict_filter == "🎁 Estudios en Promoción Activa / Próxima":
                if p_promo_val is None:
                    continue
            elif verdict_filter == "✏️ Solo estudios modificados manualmente":
                if not is_mod:
                    continue
            elif verdict_filter == "🔎 Sin homólogo en Chopo":
                if m.get("match_type") != "NO_MATCH":
                    continue

            # Aplicar filtro de confianza
            if confidence_filter == "Exacto (100%)" and m.get("match_type") != "EXACT":
                continue
            elif confidence_filter == "Alta (>=85%)" and m.get("match_type") != "HIGH":
                continue
            elif confidence_filter == "Media (70-84%)" and m.get("match_type") != "MEDIUM":
                continue

            # Aplicar búsqueda de texto
            if search_query:
                q = search_query.upper().strip()
                t_lcm = f"{m.get('lcm_code', '')} {m.get('lcm_name', '')}".upper()
                t_chopo = str(m.get('chopo_name') or '').upper()
                if q not in t_lcm and q not in t_chopo:
                    continue

            # Veredicto label
            if diff_m is not None:
                if diff_m < 0:
                    verd = "🟢 LCM más barato"
                elif diff_m > 0:
                    verd = "🔴 Chopo más barato"
                else:
                    verd = "🤝 Igual precio"
            else:
                verd = "⚪ Sin comparativa"

            if is_mod:
                verd += " (✏️ Editado)"

            df_rows.append({
                "Favorito": "⭐ SÍ" if is_study_fav else "",
                "Clave": m.get("lcm_code", ""),
                "Estudio LCM": m.get("lcm_name", ""),
                "Precio Lista LCM": m.get("lcm_price"),
                "Tarifa en Check-Up": p_bundle,
                "Tarifa Promoción": p_promo_val,
                "Campaña Promo": f"{p_promo_name} ({p_promo_per})" if p_promo_name else "N/A",
                "Estudio Chopo Mérida": m.get("chopo_name") or "N/D",
                "Chopo Web": m.get("chopo_price_web"),
                "Chopo Mostrador": m.get("chopo_price_list"),
                "Dif ($)": diff_m,
                "Dif (%)": m.get("diff_pct"),
                "Veredicto": verd,
                "Confianza": f"{m.get('confidence', 0)}%" if (m.get('confidence') or 0) > 0 else "0%"
            })

        table_df = pd.DataFrame(df_rows)

        col_count, col_exp = st.columns([3, 1])
        with col_count:
            st.write(f"Mostrando **{len(table_df):,}** estudios coincidentes con los filtros seleccionados.")
        with col_exp:
            if not table_df.empty:
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                    table_df.to_excel(writer, index=False, sheet_name="LCM vs Chopo")
                buf.seek(0)
                st.download_button(
                    label="📥 Descargar Excel (.xlsx)",
                    data=buf,
                    file_name="Comparativa_Precios_LCM_vs_Chopo.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )

        if not table_df.empty:
            st.dataframe(
                table_df.style.format({
                    "Precio Lista LCM": lambda x: format_currency(x, "N/D"),
                    "Tarifa en Check-Up": lambda x: format_currency(x, "N/A"),
                    "Tarifa Promoción": lambda x: format_currency(x, "N/A"),
                    "Chopo Web": lambda x: format_currency(x, "N/D"),
                    "Chopo Mostrador": lambda x: format_currency(x, "N/D"),
                    "Dif ($)": format_diff,
                    "Dif (%)": format_pct,
                }),
                use_container_width=True,
                height=520,
                hide_index=True
            )
        else:
            st.info("No se encontraron estudios que coincidan con los criterios de filtro.")

    # =========================================================================
    # SUBTAB 4: Subir Catálogo (XLSX / CSV) con Detección Automática
    # =========================================================================
    with subtab4:
        st.markdown("#### 📤 Importador Inteligente de Catálogo LCM (Excel / CSV)")
        st.caption("Sube una lista de precios actualizada en Excel o CSV. El sistema detectará automáticamente las columnas y ejecutará el matching frente a Chopo.")

        uploaded_file = st.file_uploader(
            "Selecciona tu archivo de precios actualizado:",
            type=["xlsx", "xls", "csv"],
            help="Soporta archivos Excel (.xlsx/.xls) y archivos separados por comas (.csv)"
        )

        if uploaded_file is not None:
            try:
                if uploaded_file.name.endswith(".csv"):
                    df_up = pd.read_csv(uploaded_file)
                else:
                    df_up = pd.read_excel(uploaded_file)

                st.success(f"Archivo cargado: **{uploaded_file.name}** con **{len(df_up):,}** filas y **{len(df_up.columns)}** columnas.")

                # Detección inteligente de columnas
                detected = detect_columns(df_up)
                cols_list = list(df_up.columns)

                st.markdown("##### 🔍 Detección y Mapeo de Columnas")
                st.info("El sistema preseleccionó automáticamente las columnas según su encabezado y contenido. Verifica o ajusta si es necesario:")

                mc1, mc2, mc3 = st.columns(3)
                with mc1:
                    code_idx = cols_list.index(detected["code_col"]) if detected["code_col"] in cols_list else 0
                    sel_code_col = st.selectbox(
                        "Columna de Código / Clave (opcional):",
                        options=["[Ninguna]"] + cols_list,
                        index=code_idx + 1 if detected["code_col"] else 0
                    )
                with mc2:
                    name_idx = cols_list.index(detected["name_col"]) if detected["name_col"] in cols_list else 0
                    sel_name_col = st.selectbox(
                        "Columna de Nombre del Estudio *:",
                        options=cols_list,
                        index=name_idx
                    )
                with mc3:
                    price_idx = cols_list.index(detected["price_col"]) if detected["price_col"] in cols_list else 0
                    sel_price_col = st.selectbox(
                        "Columna de Precio Público *:",
                        options=cols_list,
                        index=price_idx
                    )

                # Vista previa
                st.markdown("##### 👁️ Vista Previa de Datos Mapeados (Primeras 5 filas)")
                preview_cols = [c for c in [sel_code_col if sel_code_col != "[Ninguna]" else None, sel_name_col, sel_price_col] if c]
                st.dataframe(df_up[preview_cols].head(5), use_container_width=True)

                st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
                if st.button("🚀 Procesar y Homologar Catálogo con Chopo Mérida", type="primary", use_container_width=True):
                    with st.spinner("Procesando estudios y ejecutando matching clínico inteligente con Chopo..."):
                        final_code_col = sel_code_col if sel_code_col != "[Ninguna]" else None
                        res_meta = process_uploaded_catalog(
                            df=df_up,
                            code_col=final_code_col,
                            name_col=sel_name_col,
                            price_col=sel_price_col
                        )
                        st.cache_data.clear()
                        st.success(f"""
                        🎉 **Catálogo actualizado exitosamente**  
                        - Total de estudios importados: **{res_meta.get('total_lcm_studies', 0):,}**  
                        - Estudios homologados con Chopo: **{res_meta.get('actionable_matched_count', 0):,} ({res_meta.get('actionable_matched_pct', 0)}%)**  
                        - Coincidencias exactas: **{res_meta.get('exact_matches', 0)}**  
                        - Alta confianza: **{res_meta.get('high_confidence', 0)}**
                        """)
                        st.rerun()

            except Exception as ex:
                st.error(f"Error al leer el archivo: {ex}")
