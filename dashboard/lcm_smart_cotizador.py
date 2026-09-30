# dashboard/lcm_smart_cotizador.py
r"""
Cotizador Inteligente & Recomendador Clínico de Check-Ups para LCM.
- Analiza estudios seleccionados y desglosa sus analitos (catálogo maquila).
- Detecta solapamientos y duplicidades de analitos para optimizar la orden.
- Sugiere Check-Ups existentes cuando se cotizan estudios afines (ej. Química + Tiroideo).
- Aplica automáticamente la Regla de la Mejor Tarifa para Estudios Adicionales en Check-Up.
- Genera ficha comercial formateada para enviar por WhatsApp al paciente o médico.
"""

import io
import json
import re
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple

import streamlit as st
import pandas as pd

from scraper.lcm_analytes_manager import (
    load_analytes_catalog,
    get_analytes_for_study,
    find_overlapping_analytes,
    suggest_checkups_for_studies,
    get_lcm_checkups,
    get_lcm_adicionales,
    normalize_analyte_name
)

try:
    from scraper.lcm_analytes_manager import (
        filter_studies_covered_by_checkup,
        is_study_covered_by_checkup,
        get_lcm_price_for_study
    )
except ImportError:
    def get_lcm_price_for_study(study_name: str) -> float:
        upper_s = normalize_analyte_name(study_name).upper()
        if "27 ELEMENTOS" in upper_s: return 490.0
        if "18 ELEMENTOS" in upper_s: return 390.0
        if "12 ELEMENTOS" in upper_s: return 320.0
        if "30 ELEMENTOS" in upper_s: return 549.0
        if "36 ELEMENTOS" in upper_s: return 690.0
        if "45 ELEMENTOS" in upper_s: return 850.0
        if "50 ELEMENTOS" in upper_s: return 980.0
        if "6 ELEMENTOS" in upper_s: return 220.0
        if "4 ELEMENTOS" in upper_s: return 180.0
        if "3 ELEMENTOS" in upper_s: return 150.0
        if "TIROIDEO 2" in upper_s: return 670.0
        if "TIROIDEO COMPLETO" in upper_s: return 690.0
        if "BIOMETRIA" in upper_s: return 149.0
        if "ORINA" in upper_s or "EGO" in upper_s: return 114.0
        if "VITAMINA D" in upper_s: return 690.0
        if "LIPID" in upper_s: return 320.0
        if "PSA" in upper_s or "PROSTAT" in upper_s: return 290.0
        return 350.0
    def is_study_covered_by_checkup(study_name: str, checkup: Dict[str, Any]) -> bool:
        norm_s = normalize_analyte_name(study_name)
        chk_studies = [normalize_analyte_name(s) for s in checkup.get("studies", [])]
        if "QUIMICA" in norm_s or "ELEMENTOS" in norm_s:
            if any("QUIMICA" in cs for cs in chk_studies): return True
        if "TIROID" in norm_s or any(k in norm_s for k in ["TSH", "T3", "T4"]):
            if any("TIROID" in cs for cs in chk_studies): return True
        if "BIOMETR" in norm_s or "HEMATIC" in norm_s:
            if any("BIOMETR" in cs or "HEMATIC" in cs for cs in chk_studies): return True
        if "ORINA" in norm_s or "EGO" in norm_s:
            if any("ORINA" in cs or "EGO" in cs for cs in chk_studies): return True
        if "VITAMINA D" in norm_s or "CALCIFEROL" in norm_s or "25-OH" in norm_s:
            if any("VITAMINA D" in cs or "CALCIFEROL" in cs for cs in chk_studies): return True
        if "PROSTAT" in norm_s or "PSA" in norm_s:
            if any("PROSTAT" in cs or "PSA" in cs for cs in chk_studies): return True
        if "GLICOSILADA" in norm_s or "HBA1C" in norm_s:
            if any("GLICOSILADA" in cs or "HBA1C" in cs for cs in chk_studies): return True
        if "LIPID" in norm_s:
            if any("QUIMICA" in cs and any(n in cs for n in ["24", "27", "30", "36", "40", "45", "50"]) for cs in chk_studies): return True
            if any("LIPID" in cs for cs in chk_studies): return True
        if "PAPANICOLAOU" in norm_s or "CITOLOG" in norm_s:
            if any("PAPANICOLAOU" in cs or "CITOLOG" in cs for cs in chk_studies): return True
        for cs in chk_studies:
            if norm_s in cs or cs in norm_s: return True
        return False

    def filter_studies_covered_by_checkup(
        selected_studies: List[str],
        checkup: Dict[str, Any],
        adicionales_list: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[List[str], List[str], List[Dict[str, Any]]]:
        if adicionales_list is None:
            adicionales_list = get_lcm_adicionales()
        remaining_studies = []
        removed_studies = []
        moved_to_adicionales = []
        for s in selected_studies:
            if is_study_covered_by_checkup(s, checkup):
                removed_studies.append(s)
            else:
                norm_s = normalize_analyte_name(s)
                found_adic = None
                for adic in adicionales_list:
                    norm_a = normalize_analyte_name(adic.get("name", ""))
                    if norm_s in norm_a or norm_a in norm_s:
                        found_adic = adic
                        break
                if found_adic:
                    moved_to_adicionales.append(found_adic)
                else:
                    remaining_studies.append(s)
        return remaining_studies, removed_studies, moved_to_adicionales


def _fmt_price_html(val: Any) -> str:
    """Formatea precios usando entidades HTML seguras sin KaTeX math bugs."""
    if val is None or pd.isna(val) or val == "":
        return "N/D"
    try:
        if isinstance(val, str):
            clean = re.sub(r"[^\d.]", "", val)
            num = float(clean) if clean else 0.0
        else:
            num = float(val)
        return f"&#36;{num:,.2f}"
    except Exception:
        return "N/D"


def _clean_html_block(html_str: str) -> str:
    """Limpia la indentación inicial para prevenir bloques de código markdown."""
    lines = html_str.strip().split("\n")
    cleaned = [re.sub(r"^\s{4,}", "", line) for line in lines]
    return "\n".join(cleaned)


def render_smart_cotizador_tab():
    st.markdown("### 🩺 Cotizador Inteligente & Recomendador Clínico LCM")
    st.caption("Inteligencia de empaquetamiento clínico · Detección de analitos oficiales, sugerencias de Check-Ups y optimización de tarifas.")

    # Cargar catálogo de analitos y adicionales
    catalog = load_analytes_catalog()
    checkups_list = get_lcm_checkups()
    adicionales_list = get_lcm_adicionales()

    # ── 1. Barra de Estadísticas Rápidas (Apple / Google Minimal) ─────────────
    total_catalog = len(catalog)
    total_quimicas = len([v for v in catalog.values() if v.get("study_type") == "QUIMICA_SANGUINEA"])
    total_perfiles = len([v for v in catalog.values() if v.get("study_type") == "PERFIL_CLINICO"])
    total_checkups = len(checkups_list)
    total_adicionales = len(adicionales_list)

    strip_html = f"""
    <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:12px; padding:12px 18px; margin-bottom:14px; display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:14px; box-shadow:0 1px 2px rgba(0,0,0,0.03);">
        <div style="display:flex; align-items:center; gap:20px; flex-wrap:wrap;">
            <div>
                <span style="font-size:0.68rem; font-weight:700; color:#64748b; text-transform:uppercase; letter-spacing:0.4px; display:block;">Catálogo Analítico</span>
                <span style="font-size:1.15rem; font-weight:800; color:#0f172a;">{total_catalog} estudios</span>
            </div>
            <div style="width:1px; height:24px; background:#e2e8f0;"></div>
            <div>
                <span style="font-size:0.68rem; font-weight:700; color:#0284c7; text-transform:uppercase; letter-spacing:0.4px; display:block;">Químicas Sanguíneas</span>
                <span style="font-size:1.15rem; font-weight:800; color:#0284c7;">{total_quimicas} paneles</span>
            </div>
            <div style="width:1px; height:24px; background:#e2e8f0;"></div>
            <div>
                <span style="font-size:0.68rem; font-weight:700; color:#7c3aed; text-transform:uppercase; letter-spacing:0.4px; display:block;">Perfiles Clínicos</span>
                <span style="font-size:1.15rem; font-weight:800; color:#7c3aed;">{total_perfiles} perfiles</span>
            </div>
            <div style="width:1px; height:24px; background:#e2e8f0;"></div>
            <div>
                <span style="font-size:0.68rem; font-weight:700; color:#059669; text-transform:uppercase; letter-spacing:0.4px; display:block;">Check-Ups Base</span>
                <span style="font-size:1.15rem; font-weight:800; color:#059669;">{total_checkups} paquetes</span>
            </div>
            <div style="width:1px; height:24px; background:#e2e8f0;"></div>
            <div>
                <span style="font-size:0.68rem; font-weight:700; color:#d97706; text-transform:uppercase; letter-spacing:0.4px; display:block;">Adicionales Promo</span>
                <span style="font-size:1.15rem; font-weight:800; color:#d97706;">{total_adicionales} estudios</span>
            </div>
        </div>
        <div style="background:#ecfdf5; border:1px solid #a7f3d0; border-radius:8px; padding:6px 12px; text-align:right;">
            <span style="font-size:0.68rem; font-weight:700; color:#047857; text-transform:uppercase; letter-spacing:0.3px; display:block;">Regla Activa</span>
            <span style="font-size:0.84rem; font-weight:700; color:#065f46;">Tarifa preferencial en Check-Up</span>
        </div>
    </div>
    """
    st.markdown(_clean_html_block(strip_html), unsafe_allow_html=True)

    # ── Estado de sesión del cotizador ────────────────────────────────────────
    if "cotiz_selected_studies" not in st.session_state:
        st.session_state.cotiz_selected_studies = ["QUÍMICA SANGUÍNEA DE 27 ELEMENTOS", "PERFIL TIROIDEO 2"]
    if "cotiz_base_checkup" not in st.session_state:
        st.session_state.cotiz_base_checkup = None
    if "cotiz_selected_adicionales" not in st.session_state:
        st.session_state.cotiz_selected_adicionales = []
    if "cotiz_patient_name" not in st.session_state:
        st.session_state.cotiz_patient_name = ""
    if "cotiz_sel_version" not in st.session_state:
        st.session_state.cotiz_sel_version = 0

    # Mensaje de confirmación cuando se aplica sugerencia o limpieza
    if st.session_state.get("cotiz_last_applied_msg"):
        st.success(f"🎉 {st.session_state.cotiz_last_applied_msg}")
        st.session_state.cotiz_last_applied_msg = None

    # ── 2. Carga Rápida de Estudios / Perfiles Frecuentes (1 Clic) ────────────
    st.markdown("##### ⚡ Carga Rápida de Perfiles Frecuentes (1 clic):")
    col_q1, col_q2, col_q3, col_q4, col_q5, col_q6, col_q7 = st.columns(7)

    with col_q1:
        if st.button("🦋 Tiroideo + QS", use_container_width=True, help="Química Sanguínea 27 + Perfil Tiroideo 2"):
            st.session_state.cotiz_selected_studies = ["QUÍMICA SANGUÍNEA DE 27 ELEMENTOS", "PERFIL TIROIDEO 2"]
            st.session_state.cotiz_base_checkup = None
            st.session_state.cotiz_selected_adicionales = []
            st.session_state.cotiz_sel_version += 1
            st.rerun()

    with col_q2:
        if st.button("🩺 Check-Up Básico", use_container_width=True, help="Check Up Esencial con Química 30, BH y EGO"):
            st.session_state.cotiz_selected_studies = []
            st.session_state.cotiz_base_checkup = "Check Up Esencial (30 Elementos)"
            st.session_state.cotiz_selected_adicionales = []
            st.session_state.cotiz_sel_version += 1
            st.rerun()

    with col_q3:
        if st.button("☀️ QS + Vitamina D", use_container_width=True, help="Química 27 + Vitamina D"):
            st.session_state.cotiz_selected_studies = ["QUÍMICA SANGUÍNEA DE 27 ELEMENTOS", "VITAMINA D (25-OH) TOTAL", "BIOMETRÍA HEMÁTICA"]
            st.session_state.cotiz_base_checkup = None
            st.session_state.cotiz_selected_adicionales = []
            st.session_state.cotiz_sel_version += 1
            st.rerun()

    with col_q4:
        if st.button("🥗 Diabético / Metab.", use_container_width=True, help="Química 27 + HbA1c + EGO"):
            st.session_state.cotiz_selected_studies = ["QUÍMICA SANGUÍNEA DE 27 ELEMENTOS", "PERFIL DIABÉTICO", "EXAMEN GENERAL DE ORINA"]
            st.session_state.cotiz_base_checkup = None
            st.session_state.cotiz_selected_adicionales = []
            st.session_state.cotiz_sel_version += 1
            st.rerun()

    with col_q5:
        if st.button("👨 Salud Hombre", use_container_width=True, help="Química 27 + PSA + BH + EGO"):
            st.session_state.cotiz_selected_studies = ["QUÍMICA SANGUÍNEA DE 27 ELEMENTOS", "ANTÍGENO PROSTÁTICO ESPECÍFICO (PSA)", "BIOMETRÍA HEMÁTICA"]
            st.session_state.cotiz_base_checkup = None
            st.session_state.cotiz_selected_adicionales = []
            st.session_state.cotiz_sel_version += 1
            st.rerun()

    with col_q6:
        if st.button("🤰 Prenatal", use_container_width=True, help="Perfil Obstétrico completo"):
            st.session_state.cotiz_selected_studies = ["PERFIL OBSTÉTRICO", "BIOMETRÍA HEMÁTICA", "EXAMEN GENERAL DE ORINA"]
            st.session_state.cotiz_base_checkup = None
            st.session_state.cotiz_selected_adicionales = []
            st.session_state.cotiz_sel_version += 1
            st.rerun()

    with col_q7:
        if st.button("🧹 Limpiar", use_container_width=True, help="Vaciar la cotización"):
            st.session_state.cotiz_selected_studies = []
            st.session_state.cotiz_selected_adicionales = []
            st.session_state.cotiz_base_checkup = None
            st.session_state.cotiz_sel_version += 1
            st.rerun()

    st.markdown("---")

    # ── 3. Buscador y Selector Multiestudio ────────────────────────────────────
    all_study_options = []
    for k, v in catalog.items():
        if v.get("study_type") == "QUIMICA_SANGUINEA":
            all_study_options.append(v["name"])
    for k, v in catalog.items():
        if v.get("study_type") == "PERFIL_CLINICO":
            all_study_options.append(v["name"])
    for k, v in catalog.items():
        if v.get("study_type") not in ("QUIMICA_SANGUINEA", "PERFIL_CLINICO") and v["name"] not in all_study_options:
            all_study_options.append(v["name"])

    common_names = [
        "VITAMINA D (25-OH) TOTAL",
        "HEMOGLOBINA GLICOSILADA (HbA1c)",
        "BIOMETRÍA HEMÁTICA",
        "EXAMEN GENERAL DE ORINA",
        "ANTÍGENO PROSTÁTICO ESPECÍFICO (PSA)",
        "PERFIL TIROIDEO 2",
        "PERFIL TIROIDEO COMPLETO",
        "PERFIL DE LÍPIDOS",
        "PERFIL HEPÁTICO",
        "ULTRASONIDO ABDOMINO-PÉLVICO",
        "RAYOS X TÓRAX PA"
    ]
    for cn in common_names:
        if cn not in all_study_options:
            all_study_options.append(cn)

    all_study_options = sorted(list(dict.fromkeys(all_study_options)))

    col_sel_main, col_sel_chk = st.columns([2.5, 1.5])
    with col_sel_main:
        selected_studies = st.multiselect(
            "🔍 Selecciona o escribe los estudios que el paciente solicita:",
            options=all_study_options,
            default=[s for s in st.session_state.cotiz_selected_studies if s in all_study_options],
            key=f"cotiz_multisel_studies_{st.session_state.cotiz_sel_version}",
            help="Escribe el nombre de la química (ej. 27 elementos, 30, 45), perfil tiroideo, lípidos, etc."
        )
        st.session_state.cotiz_selected_studies = selected_studies

    with col_sel_chk:
        chk_names = ["[Ninguno - Cotizar estudios sueltos]"] + [c["name"] for c in checkups_list]
        curr_chk_idx = 0
        if st.session_state.cotiz_base_checkup:
            for idx_c, cn in enumerate(chk_names):
                if st.session_state.cotiz_base_checkup in cn or cn in st.session_state.cotiz_base_checkup:
                    curr_chk_idx = idx_c
                    break

        sel_base_chk = st.selectbox(
            "📦 Check-Up Base contratado (opcional):",
            options=chk_names,
            index=curr_chk_idx,
            key=f"cotiz_chk_base_{st.session_state.cotiz_sel_version}",
            help="Al seleccionar un Check-Up base, se habilitan las tarifas preferenciales en estudios adicionales."
        )
        if sel_base_chk != "[Ninguno - Cotizar estudios sueltos]":
            st.session_state.cotiz_base_checkup = sel_base_chk
        else:
            st.session_state.cotiz_base_checkup = None

    # Si hay un Check-Up base activo, verificar si en selected_studies hay estudios cubiertos por él
    if st.session_state.cotiz_base_checkup and selected_studies:
        act_chk = next((c for c in checkups_list if c["name"] == st.session_state.cotiz_base_checkup), None)
        if act_chk:
            clean_rem, clean_covered, clean_adics = filter_studies_covered_by_checkup(
                selected_studies=selected_studies,
                checkup=act_chk,
                adicionales_list=adicionales_list
            )
            if clean_covered:
                c_warn_col, c_btn_clean = st.columns([3, 1.2])
                with c_warn_col:
                    st.warning(f"⚠️ El Check-Up **'{act_chk['name']}'** ya incluye: **{', '.join(clean_covered)}**. Están repetidos en tus estudios sueltos.")
                with c_btn_clean:
                    st.markdown("&nbsp;", unsafe_allow_html=True)
                    if st.button("🧹 Quitar Duplicados de la Lista", key="btn_clean_manual_dupes", use_container_width=True):
                        st.session_state.cotiz_selected_studies = clean_rem
                        if clean_adics:
                            cur_ad = list(st.session_state.cotiz_selected_adicionales)
                            for ma in clean_adics:
                                if not any(ca.get("name") == ma.get("name") for ca in cur_ad):
                                    cur_ad.append(ma)
                            st.session_state.cotiz_selected_adicionales = cur_ad
                        st.session_state.cotiz_sel_version += 1
                        st.session_state.cotiz_last_applied_msg = f"Se removieron los estudios ya cubiertos por el Check-Up: {', '.join(clean_covered)}."
                        st.rerun()

    if not selected_studies and not st.session_state.cotiz_base_checkup:
        st.info("👆 Selecciona uno o más estudios en el buscador de arriba o haz clic en alguno de los botones rápidos para generar la cotización y ver las sugerencias de Check-Up.")
        return

    # ── 4. Motor Inteligente de Sugerencias de Check-Ups ───────────────────────
    suggestions = suggest_checkups_for_studies(selected_studies)
    if suggestions and not st.session_state.cotiz_base_checkup:
        best_sug = suggestions[0]
        chk_sug = best_sug["checkup"]

        sug_box_html = f"""
        <div style="background:#eff6ff; border:1.5px solid #bfdbfe; border-radius:10px; padding:12px 16px; margin:12px 0 16px 0; box-shadow:0 1px 3px rgba(0,0,0,0.04);">
            <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:12px;">
                <div>
                    <div style="display:flex; align-items:center; gap:8px;">
                        <span style="font-size:1.1rem;">💡</span>
                        <span style="font-weight:800; color:#1e40af; font-size:0.95rem; text-transform:uppercase; letter-spacing:0.4px;">Sugerencia Inteligente de Check-Up LCM</span>
                        <span style="background:#dbeafe; color:#1d4ed8; font-size:0.72rem; font-weight:700; padding:2px 8px; border-radius:12px;">{best_sug['score']}% coincidencia</span>
                    </div>
                    <div style="font-size:0.88rem; color:#1e3a8a; margin-top:6px; line-height:1.4;">
                        {best_sug['reason']}
                    </div>
                    <div style="font-size:0.82rem; color:#475569; margin-top:6px;">
                        <b>Estudios que incluye:</b> {', '.join(chk_sug['studies'])}
                    </div>
                </div>
                <div style="text-align:right; min-width:140px;">
                    <span style="font-size:0.7rem; color:#64748b; display:block;">Tarifa Empaquetada</span>
                    <span style="font-size:1.35rem; font-weight:800; color:#059669;">{_fmt_price_html(chk_sug['price_promo'])}</span>
                    <span style="font-size:0.74rem; color:#dc2626; display:block;">Ahorro: {_fmt_price_html(chk_sug['savings'])}</span>
                </div>
            </div>
        </div>
        """
        st.markdown(_clean_html_block(sug_box_html), unsafe_allow_html=True)

        col_apply_sug, col_sug_dummy = st.columns([2, 3])
        with col_apply_sug:
            if st.button(f"⚡ Aplicar '{chk_sug['name']}' y Sustituir Duplicados", type="primary", use_container_width=True, key=f"btn_apply_{chk_sug['id']}"):
                rem_studies, removed_studies, moved_adics = filter_studies_covered_by_checkup(
                    selected_studies=st.session_state.cotiz_selected_studies,
                    checkup=chk_sug,
                    adicionales_list=adicionales_list
                )
                st.session_state.cotiz_base_checkup = chk_sug["name"]
                st.session_state.cotiz_selected_studies = rem_studies

                # Si se detectaron estudios adicionales (ej. Vitamina D), pasarlos a adicionales
                if moved_adics:
                    current_adics = list(st.session_state.cotiz_selected_adicionales)
                    for ma in moved_adics:
                        if not any(ca.get("name") == ma.get("name") for ca in current_adics):
                            current_adics.append(ma)
                    st.session_state.cotiz_selected_adicionales = current_adics

                st.session_state.cotiz_sel_version += 1
                msg_parts = [f"Check-Up '{chk_sug['name']}' aplicado."]
                if removed_studies:
                    msg_parts.append(f"Se sustituyeron de la lista {len(removed_studies)} estudios duplicados: {', '.join(removed_studies)}.")
                if moved_adics:
                    msg_parts.append(f"Se movieron a adicionales en promoción: {', '.join([m['name'] for m in moved_adics])}.")
                st.session_state.cotiz_last_applied_msg = " ".join(msg_parts)
                st.rerun()

    # ── 5. Detección y Alerta de Analitos Duplicados / Solapados ───────────────
    overlaps = find_overlapping_analytes(selected_studies, catalog)
    if overlaps:
        for ov in overlaps:
            full_txt = f" (¡Cubre completamente a {ov['covered_study']}!)" if ov.get("is_full_coverage") else ""
            overlap_html = f"""
            <div style="background:#fffbeb; border:1px solid #fde68a; border-radius:8px; padding:10px 14px; margin-bottom:10px; font-size:0.84rem; color:#92400e;">
                <div style="display:flex; align-items:center; gap:6px; font-weight:700;">
                    <span>⚠️</span>
                    <span>Analitos Duplicados entre '{ov['study_1']}' y '{ov['study_2']}'{full_txt}</span>
                </div>
                <div style="margin-top:4px; font-size:0.8rem; color:#78350f;">
                    <b>{ov['overlapping_count']} analitos compartidos:</b> {', '.join(ov['overlapping_analytes'])}
                </div>
                <div style="margin-top:3px; font-size:0.75rem; color:#b45309;">
                    💡 <i>Recomendación clínica:</i> Si ya solicitas <b>{ov['study_1']}</b>, no es necesario cobrar por separado los analitos solapados de <b>{ov['study_2']}</b>.
                </div>
            </div>
            """
            st.markdown(_clean_html_block(overlap_html), unsafe_allow_html=True)

    # ── 6. Desglose Clínico de Analitos por Estudio (De Directorio Maquila) ────
    with st.expander("🔬 Desglose Clínico de Analitos & Requisitos de Muestra (Directorio Maquila Oficial)", expanded=True):
        st.caption("Consulta los analitos individuales que integran cada química sanguínea o perfil para asesorar al paciente o médico:")

        for s_name in selected_studies:
            s_info = get_analytes_for_study(s_name, catalog)
            analytes_list = s_info.get("analytes", [])
            code_str = f"Clave {s_info.get('code')}" if s_info.get("code") else "Perfil Clínico"
            sample_req = s_info.get("sample_req") or "Ayuno de 8 a 12 horas."
            sample_type = s_info.get("sample_type") or "Suero / Sangre total"
            turnaround = s_info.get("turnaround") or "Mismo Día (MD)"

            c_head_html = f"""
            <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:10px 14px; margin-bottom:8px;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        <span style="font-weight:700; color:#0f172a; font-size:0.9rem;">{s_info.get('name') or s_name}</span>
                        <span style="background:#e2e8f0; color:#475569; font-size:0.72rem; padding:2px 8px; border-radius:10px; margin-left:6px; font-weight:600;">{code_str}</span>
                        <span style="background:#e0f2fe; color:#0369a1; font-size:0.72rem; padding:2px 8px; border-radius:10px; margin-left:4px; font-weight:600;">{len(analytes_list)} analitos</span>
                    </div>
                    <span style="font-size:0.75rem; color:#64748b;">⏱️ Entrega: <b>{turnaround}</b></span>
                </div>
                <div style="font-size:0.76rem; color:#475569; margin-top:4px;">
                    🩸 <b>Tubo / Muestra:</b> {sample_type} &nbsp;|&nbsp; ⏰ <b>Indicaciones:</b> {sample_req}
                </div>
            """
            st.markdown(_clean_html_block(c_head_html), unsafe_allow_html=True)

            if analytes_list:
                # Renderizar los analitos en chips ordenados
                chips_html = " ".join([
                    f'<span style="background:#ffffff; border:1px solid #cbd5e1; border-radius:14px; padding:2px 9px; font-size:0.74rem; color:#334155; display:inline-block; margin:2px 2px;">{a}</span>'
                    for a in analytes_list
                ])
                st.markdown(_clean_html_block(f'<div style="padding:4px 0 6px 0;">{chips_html}</div></div>'), unsafe_allow_html=True)
            else:
                st.markdown(_clean_html_block('<div style="font-size:0.76rem; color:#94a3b8; font-style:italic; padding-bottom:6px;">Estudio analítico unitario o sin desglose de subcomponentes.</div></div>'), unsafe_allow_html=True)

    # ── 7. Selección de Estudios Adicionales en Promoción (Si hay Check-Up) ────
    selected_adicionales = []
    if st.session_state.cotiz_base_checkup:
        st.markdown("##### 🎁 Estudios Adicionales con Tarifa Preferencial de Check-Up:")
        st.caption("Aprovecha que el paciente contrata un Check-Up para ofrecerle estudios adicionales a precio preferencial:")

        # Crear diccionario de opciones de adicionales
        adic_options = [f"{a['name']} (Tarifa Check-Up: ${_fmt_price_html(a['price_bundle']).replace('&#36;', '')} vs Lista ${_fmt_price_html(a.get('price_2025')).replace('&#36;', '')})" for a in adicionales_list]
        adic_map = {adic_options[i]: adicionales_list[i] for i in range(len(adicionales_list))}

        sel_adic_raw = st.multiselect(
            "Selecciona estudios adicionales para agregar:",
            options=adic_options,
            default=[opt for opt in adic_options if any(a.get("name", "").lower() in opt.lower() for a in st.session_state.cotiz_selected_adicionales)],
            key="multisel_adicionales"
        )
        selected_adicionales = [adic_map[o] for o in sel_adic_raw if o in adic_map]
        st.session_state.cotiz_selected_adicionales = selected_adicionales

    # ── 8. Cálculo de Totales y Resumen Financiero ─────────────────────────────
    st.markdown("---")
    st.markdown("#### 🧮 Resumen de Cotización & Ficha Comercial")

    col_calc1, col_calc2 = st.columns([1.8, 1.2])

    with col_calc1:
        # Calcular montos
        total_quote = 0.0
        total_regular = 0.0
        total_savings = 0.0
        breakdown_rows = []

        # 1. Si hay Check-Up base
        active_chk_data = None
        if st.session_state.cotiz_base_checkup:
            for chk in checkups_list:
                if chk["name"] == st.session_state.cotiz_base_checkup:
                    active_chk_data = chk
                    break

            if active_chk_data:
                p_promo = float(active_chk_data.get("price_promo") or 0.0)
                p_reg = float(active_chk_data.get("price_regular") or p_promo)
                sav = p_reg - p_promo
                total_quote += p_promo
                total_regular += p_reg
                total_savings += sav
                breakdown_rows.append({
                    "Concepto": f"📦 {active_chk_data['name']}",
                    "Tipo": "Check-Up Base",
                    "Precio Cotizado": p_promo,
                    "Precio Regular": p_reg,
                    "Ahorro": sav
                })

        # 2. Estudios sueltos (si no hay checkup o estudios fuera del checkup)
        for s_name in selected_studies:
            # Si hay checkup base y el estudio ya está dentro del checkup, no sumarlo doble
            if active_chk_data and any(normalize_analyte_name(s_name) in normalize_analyte_name(cs) for cs in active_chk_data.get("studies", [])):
                continue

            # Obtener precio público oficial de LCM para este estudio
            s_price = get_lcm_price_for_study(s_name)

            total_quote += s_price
            total_regular += s_price
            breakdown_rows.append({
                "Concepto": s_name,
                "Tipo": "Estudio Individual",
                "Precio Cotizado": s_price,
                "Precio Regular": s_price,
                "Ahorro": 0.0
            })

        # 3. Adicionales seleccionados
        for adic in selected_adicionales:
            p_bundle = float(adic.get("price_bundle") or 0.0)
            p_reg = float(adic.get("price_2025") or p_bundle)
            sav = p_reg - p_bundle
            total_quote += p_bundle
            total_regular += p_reg
            total_savings += sav
            breakdown_rows.append({
                "Concepto": f"➕ {adic['name']}",
                "Tipo": "Adicional en Check-Up",
                "Precio Cotizado": p_bundle,
                "Precio Regular": p_reg,
                "Ahorro": sav
            })

        df_breakdown = pd.DataFrame(breakdown_rows)
        if not df_breakdown.empty:
            st.dataframe(
                df_breakdown.style.format({
                    "Precio Cotizado": lambda x: f"${x:,.2f}",
                    "Precio Regular": lambda x: f"${x:,.2f}",
                    "Ahorro": lambda x: f"${x:,.2f}" if x > 0 else "-"
                }),
                use_container_width=True,
                hide_index=True
            )

    with col_calc2:
        # Tarjeta ejecutiva de Total
        patient_input = st.text_input("Nombre del paciente (opcional):", value=st.session_state.cotiz_patient_name, placeholder="Ej: Lic. Roberto Cruz", key="input_patient_cotiz")
        st.session_state.cotiz_patient_name = patient_input

        total_card_html = f"""
        <div style="background:#ffffff; border:1.5px solid #059669; border-radius:12px; padding:16px 20px; box-shadow:0 2px 4px rgba(0,0,0,0.05); text-align:center;">
            <span style="font-size:0.75rem; font-weight:700; color:#64748b; text-transform:uppercase; letter-spacing:0.5px; display:block;">Total Cotizado al Paciente</span>
            <div style="font-size:2.1rem; font-weight:800; color:#059669; margin:4px 0;">{_fmt_price_html(total_quote)}</div>
            <div style="font-size:0.8rem; color:#64748b; text-decoration:line-through;">Precio regular de lista: {_fmt_price_html(total_regular)}</div>
            <div style="background:#ecfdf5; border:1px solid #bbf7d0; border-radius:6px; padding:4px 10px; margin-top:8px; font-size:0.82rem; font-weight:700; color:#15803d; display:inline-block;">
                🎉 Ahorro Total para el Paciente: {_fmt_price_html(total_savings)}
            </div>
        </div>
        """
        st.markdown(_clean_html_block(total_card_html), unsafe_allow_html=True)

    # ── 9. Ficha Comercial de WhatsApp ────────────────────────────────────────
    st.markdown("##### 📲 Ficha Lista para Enviar por WhatsApp:")
    p_name_display = patient_input.strip() if patient_input.strip() else "Estimado(a) Paciente"
    date_display = datetime.now().strftime("%d de %B de %Y")

    wa_lines = [
        "🔬 *LABORATORIOS CLÍNICOS DE MÉRIDA (LCM)*",
        "📋 *COTIZACIÓN DE ESTUDIOS CLÍNICOS*",
        f"👤 *Paciente:* {p_name_display}",
        f"📅 *Fecha:* {date_display}",
        "----------------------------------------"
    ]

    if active_chk_data:
        wa_lines.append(f"✅ *Check-Up Incluido:*")
        wa_lines.append(f"   • *{active_chk_data['name']}:* ${_fmt_price_html(active_chk_data['price_promo']).replace('&#36;', '')} MXN")
        for st_inc in active_chk_data.get("studies", []):
            wa_lines.append(f"     ✓ {st_inc}")
        wa_lines.append("")

    loose_studies = [r for r in breakdown_rows if r["Tipo"] == "Estudio Individual"]
    if loose_studies:
        wa_lines.append("🧪 *Estudios Solicitados:*")
        for ls in loose_studies:
            wa_lines.append(f"   • {ls['Concepto']}: ${_fmt_price_html(ls['Precio Cotizado']).replace('&#36;', '')} MXN")
        wa_lines.append("")

    if selected_adicionales:
        wa_lines.append("🎁 *Estudios Adicionales (Tarifa Preferencial en Check-Up):*")
        for adic in selected_adicionales:
            wa_lines.append(f"   • {adic['name']}: ${_fmt_price_html(adic['price_bundle']).replace('&#36;', '')} MXN (Antes: ${_fmt_price_html(adic.get('price_2025')).replace('&#36;', '')})")
        wa_lines.append("")

    wa_lines.append("----------------------------------------")
    if total_savings > 0:
        wa_lines.append(f"🎉 *Ahorro Total por Paquete:* ${_fmt_price_html(total_savings).replace('&#36;', '')} MXN")
    wa_lines.append(f"💲 *TOTAL A PAGAR:* ${_fmt_price_html(total_quote).replace('&#36;', '')} MXN")
    wa_lines.append("----------------------------------------")
    wa_lines.append("⏰ *Indicaciones Generales de Preparación:*")
    wa_lines.append("   • Ayuno de 10 a 12 horas.")
    wa_lines.append("   • Si incluye orina, recolectar la primera muestra de la mañana en frasco estéril.")
    wa_lines.append("   • Mantener hidratación adecuada con agua natural.")
    wa_lines.append("----------------------------------------")
    wa_lines.append("📍 *Laboratorios Clínicos de Mérida* · Calidad diagnóstica y confianza.")

    wa_text = "\n".join(wa_lines)

    st.code(wa_text, language="text")

    # Botones de exportación
    c_btn1, c_btn2 = st.columns([1, 1])
    with c_btn1:
        if not df_breakdown.empty:
            buf_xl = io.BytesIO()
            with pd.ExcelWriter(buf_xl, engine="openpyxl") as writer:
                df_breakdown.to_excel(writer, index=False, sheet_name="Cotización LCM")
            buf_xl.seek(0)
            st.download_button(
                "📥 Descargar Cotización en Excel (.xlsx)",
                data=buf_xl,
                file_name=f"Cotizacion_LCM_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
    with c_btn2:
        st.info("💡 Puedes copiar el texto superior directamente y pegarlo en WhatsApp Web para enviarlo al paciente en 1 segundo.")
