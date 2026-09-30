# ============================================================
# dashboard/lcm_comparator.py
# Módulo de Comparativa de Precios: LCM vs Chopo Mérida
# Con Edición Manual de Precios, Subida de Catálogos (XLSX/CSV)
# y Gestor de Paquetes / Promociones con Plazos de Vigencia
# ============================================================

import json
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
    detect_columns,
    process_uploaded_catalog,
    get_consolidated_matches,
)

DATA_FILE = Path(__file__).parent.parent / "data" / "lcm" / "lcm_chopo_matches.json"


@st.cache_data(ttl=300)
def load_comparison_data() -> Dict[str, Any]:
    """Carga los datos consolidados de matching con modificaciones manuales aplicadas."""
    return get_consolidated_matches()


def format_currency(val: Optional[float]) -> str:
    if val is None or pd.isna(val):
        return "N/D"
    return f"${val:,.2f}"


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
                    <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:8px; padding:12px; margin-top:10px;">
                        <span style="color:#64748b; font-size:0.8rem; font-weight:600; text-transform:uppercase;">Precio Actual LCM (con IVA)</span>
                        <div style="color:#0284c7; font-size:1.9rem; font-weight:800; margin-top:2px;">
                            {format_currency(item.get('lcm_price'))} <small style="font-size:0.85rem; font-weight:600; color:#64748b;">MXN</small>
                        </div>
                    </div>
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
        st.markdown("#### 🎁 Gestor de Paquetes y Promociones con Plazos de Vigencia")
        st.caption("Crea, edita y monitorea promociones especiales de LCM con control de vencimiento (días, meses o plazos específicos).")

        # Visualizar Promociones Activas
        st.markdown("##### 🟢 Promociones y Paquetes Vigentes")
        
        # Filtro de estatus
        status_opts = ["Todas las vigencias", "Solo Activas & Permanentes", "Por Vencer", "Vencidas"]
        sel_stat = st.segmented_control("Filtrar por estatus:", status_opts, default="Solo Activas & Permanentes") if hasattr(st, "segmented_control") else st.radio("Filtrar:", status_opts, horizontal=True)

        filtered_promos = []
        for p in promotions:
            st_code = p.get("status", "ACTIVE")
            if sel_stat == "Solo Activas & Permanentes" and st_code not in ("ACTIVE", "PERMANENT", "EXPIRING_SOON"):
                continue
            elif sel_stat == "Por Vencer" and st_code != "EXPIRING_SOON":
                continue
            elif sel_stat == "Vencidas" and st_code != "EXPIRED":
                continue
            filtered_promos.append(p)

        if not filtered_promos:
            st.info("No hay promociones en la categoría seleccionada.")
        else:
            # Renderizar tarjetas en rejilla
            cols = st.columns(2)
            for i, p in enumerate(filtered_promos):
                with cols[i % 2]:
                    st_label = p.get("status_label", "Activa")
                    chopo_eq = p.get("chopo_equivalent", "No especificado")
                    price_promo = p.get("price_promo", 0.0)
                    price_reg = p.get("price_regular")
                    reg_str = f"<span style='font-size:0.8rem; color:#94a3b8; text-decoration:line-through;'>${price_reg:,.2f}</span>" if price_reg else ""
                    studies_str = ", ".join(p.get("studies", [])) if p.get("studies") else "Sin desglose"

                    border_color = "#22c55e" if "Activa" in st_label or "Permanente" in st_label else ("#f97316" if "Por vencer" in st_label else "#ef4444")

                    st.markdown(f"""
                    <div style="background:#ffffff; border:1px solid #e2e8f0; border-top:4px solid {border_color}; border-radius:10px; padding:16px; margin-bottom:14px; box-shadow:0 2px 6px rgba(0,0,0,0.04);">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <span style="font-weight:700; font-size:0.78rem; color:#1e293b;">{st_label}</span>
                            <span style="background:#f1f5f9; color:#475569; font-weight:700; font-size:0.75rem; padding:3px 8px; border-radius:10px;">{p.get('category', 'Promoción')}</span>
                        </div>
                        <h4 style="color:#0f172a; margin:8px 0 4px 0; font-size:1.15rem;">{p.get('name')}</h4>
                        <p style="color:#64748b; font-size:0.82rem; margin:0 0 10px 0;"><b>Estudios:</b> {studies_str}</p>
                        <div style="display:flex; justify-content:space-between; align-items:baseline; background:#f8fafc; padding:10px 14px; border-radius:8px;">
                            <div>
                                <span style="font-size:0.72rem; color:#64748b; display:block;">Precio Promoción LCM</span>
                                <span style="font-size:1.5rem; font-weight:800; color:#0284c7;">${price_promo:,.2f}</span> {reg_str}
                            </div>
                            <div style="text-align:right;">
                                <span style="font-size:0.72rem; color:#64748b; display:block;">Contraparte Chopo</span>
                                <span style="font-size:0.82rem; font-weight:700; color:#475569;">{chopo_eq[:28]}...</span>
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

        # ── Formulario de Creación / Configuración de Plazos ─────────────────
        st.markdown("---")
        with st.expander("➕ Crear Nueva Promoción o Paquete con Plazo de Vigencia", expanded=False):
            st.markdown("Configura una promoción especial asignando plazos de duración automáticos (días, fin de mes, fechas límites o permanente).")

            with st.form("create_promo_form"):
                fc1, fc2 = st.columns([2, 1])
                with fc1:
                    new_promo_name = st.text_input("Nombre de la Promoción / Paquete *", placeholder="Ej. Check Up Femenino Rosa, Promo Fin de Semana...")
                with fc2:
                    new_promo_cat = st.selectbox("Categoría:", ["Promo del Mes", "Promo Cuatrimestral", "Promo Permanente", "Promo Fin de Semana", "Flash 48h", "Convenio Especial"])

                # Selección de estudios
                study_names_list = sorted(list({m.get("lcm_name") for m in matches if m.get("lcm_name")}))
                selected_studies = st.multiselect(
                    "Estudios incluidos en el paquete (puedes seleccionar varios):",
                    options=study_names_list,
                    placeholder="Busca y agrega estudios (ej. Biometría, Glucosa, Tiroideo...)"
                )

                # Precios
                pc1, pc2, pc3 = st.columns(3)
                with pc1:
                    new_promo_price = st.number_input("Precio Promoción ($ MXN) *", min_value=0.0, value=499.0, step=10.0, format="%.2f")
                with pc2:
                    new_reg_price = st.number_input("Precio Regular / Anterior ($ MXN opcional)", min_value=0.0, value=0.0, step=10.0, format="%.2f")
                with pc3:
                    new_chopo_eq = st.text_input("Contraparte sugerida en Chopo:", placeholder="Ej. CHECK UP BÁSICO Q45")

                # Plazos y Vigencia
                st.markdown("##### ⏱️ Configuración del Plazo de Vigencia")
                vc1, vc2 = st.columns([1, 1])
                with vc1:
                    duration_mode = st.selectbox(
                        "Tipo de Plazo / Duración:",
                        [
                            "Días específicos (ej. 1, 2, 3, 7 días)",
                            "Hasta fin de este mes",
                            "Fecha límite exacta (calendario)",
                            "1 Año (Anual)",
                            "Permanente (Sin fecha de caducidad)"
                        ]
                    )

                calculated_end_date = None
                with vc2:
                    today = date.today()
                    if duration_mode == "Días específicos (ej. 1, 2, 3, 7 días)":
                        num_days = st.number_input("Número de días de duración:", min_value=1, max_value=365, value=3, step=1)
                        calculated_end_date = (today + timedelta(days=int(num_days))).isoformat()
                        st.caption(f"Vencerá el: **{calculated_end_date}** ({num_days} días a partir de hoy).")
                    elif duration_mode == "Hasta fin de este mes":
                        eom = (today.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
                        calculated_end_date = eom.isoformat()
                        st.caption(f"Vencerá el último día del mes en curso: **{calculated_end_date}**.")
                    elif duration_mode == "1 Año (Anual)":
                        calculated_end_date = (today + timedelta(days=365)).isoformat()
                        st.caption(f"Vencerá en 1 año: **{calculated_end_date}**.")
                    elif duration_mode == "Fecha límite exacta (calendario)":
                        exact_d = st.date_input("Fecha de finalización:", min_value=today, value=today + timedelta(days=15))
                        calculated_end_date = exact_d.isoformat()
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
                            "category": new_promo_cat,
                            "validity_type": v_type,
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

        # ── Eliminar Promoción Existente ─────────────────────────────────────
        if promotions:
            with st.expander("🗑️ Administrar / Eliminar Promociones Existentes", expanded=False):
                del_opts = {f"{p.get('name')} ({p.get('category')} - {p.get('status_label')})": p.get("id") for p in promotions}
                selected_del = st.selectbox("Selecciona la promoción que deseas eliminar:", options=list(del_opts.keys()))
                if st.button("🗑️ Eliminar Promoción Definitivamente", type="secondary"):
                    promo_id_to_del = del_opts[selected_del]
                    delete_promotion(promo_id_to_del)
                    st.toast("Promoción eliminada.")
                    st.rerun()

    # =========================================================================
    # SUBTAB 3: Matriz Completa & Excel
    # =========================================================================
    with subtab3:
        st.markdown("#### 📊 Matriz Consolidada de Estudios Homologados")
        st.caption("Filtra, analiza y exporta los estudios homologados entre LCM y Chopo Mérida Altabrisa con precios en tiempo real.")

        # Controles de filtrado
        fc1, fc2, fc3 = st.columns([2, 2, 3])
        with fc1:
            verdict_filter = st.selectbox(
                "Filtrar por Veredicto Comercial:",
                [
                    "Todos los estudios",
                    "🟢 Solo donde LCM es más barato",
                    "🔴 Solo donde Chopo es más barato",
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

        # Construir DataFrame
        df_rows = []
        for m in matches:
            diff_m = m.get("diff_mxn")
            is_mod = m.get("is_manually_edited", False)

            # Aplicar filtro de veredicto
            if verdict_filter == "🟢 Solo donde LCM es más barato":
                if diff_m is None or diff_m >= 0:
                    continue
            elif verdict_filter == "🔴 Solo donde Chopo es más barato":
                if diff_m is None or diff_m <= 0:
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
                "Clave": m.get("lcm_code", ""),
                "Estudio LCM": m.get("lcm_name", ""),
                "Precio LCM": m.get("lcm_price"),
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
                    "Precio LCM": lambda x: f"${x:,.2f}" if pd.notna(x) else "N/D",
                    "Chopo Web": lambda x: f"${x:,.2f}" if pd.notna(x) else "N/D",
                    "Chopo Mostrador": lambda x: f"${x:,.2f}" if pd.notna(x) else "N/D",
                    "Dif ($)": lambda x: f"${x:+,.2f}" if pd.notna(x) else "N/D",
                    "Dif (%)": lambda x: f"{x:+.1f}%" if pd.notna(x) else "N/D",
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
