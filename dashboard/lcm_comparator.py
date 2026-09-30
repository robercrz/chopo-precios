# ============================================================
# dashboard/lcm_comparator.py
# Módulo de Comparativa de Precios: LCM vs Chopo Mérida
# ============================================================

import json
from pathlib import Path
from typing import Dict, List, Any, Optional
import io

import pandas as pd
import streamlit as st


DATA_FILE = Path(__file__).parent.parent / "data" / "lcm" / "lcm_chopo_matches.json"


@st.cache_data(ttl=600)
def load_comparison_data() -> Dict[str, Any]:
    """Carga los datos de matching y comparación LCM vs Chopo."""
    if not DATA_FILE.exists():
        # Fallback si no existe: ejecutar el builder
        from scripts.build_lcm_matching import build_matching_database
        build_matching_database()

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


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
    packages = data.get("packages", [])
    adicionales = data.get("adicionales", [])

    st.markdown("""
    <div style="background: linear-gradient(135deg, #1e3a8a 0%, #0284c7 100%); color: white; padding: 22px 26px; border-radius: 12px; margin-bottom: 22px;">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">
            <div>
                <h2 style="margin:0; color:#ffffff; font-size:1.6rem; font-weight:800;">
                    ⚖️ Inteligencia Competitiva: LCM vs Chopo Mérida
                </h2>
                <p style="margin:4px 0 0 0; opacity:0.9; font-size:0.92rem;">
                    Cruce de catálogo general (Lista 2025) y promociones de Check-ups (Octubre) frente a Chopo Mérida Altabrisa
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
    chopo_cheaper = p_analysis.get("chopo_cheaper_count", 0)

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    with kpi1:
        st.metric(
            label="Catálogo LCM Analizado",
            value=f"{total_lcm:,}",
            help="Total de estudios extraídos de la Lista General Oficial LCM"
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
            label="Check-ups & Paquetes",
            value=f"{len(packages)} promos",
            delta=f"{len(adicionales)} adicionales",
            delta_color="off",
            help="Paquetes y promociones vigentes de LCM Octubre"
        )

    st.markdown("<div style='height:15px'></div>", unsafe_allow_html=True)

    # ── Sub-pestañas ──────────────────────────────────────────────────────────
    subtab1, subtab2, subtab3 = st.tabs([
        "🔍 Buscador Cara a Cara",
        "📦 Paquetes & Check-Ups",
        "📊 Matriz Completa & Excel"
    ])

    # =========================================================================
    # SUBTAB 1: Buscador Cara a Cara
    # =========================================================================
    with subtab1:
        st.markdown("#### 🎯 Comparador Directo Estudio por Estudio")
        st.caption("Selecciona cualquier estudio del catálogo LCM para ver el contraste directo de precios frente a Chopo Mérida Altabrisa.")

        # Opciones para el selectbox
        study_options = []
        study_map = {}
        for m in matches:
            label = f"[{m['lcm_code']}] {m['lcm_name']} (${m['lcm_price']:,.2f})"
            if m["match_type"] != "NO_MATCH":
                diff_str = f"LCM {'-' if m['diff_mxn'] < 0 else '+'}${abs(m['diff_mxn']):,.2f}"
                label += f" ── vs Chopo: {m['chopo_name'][:30]}... ({diff_str})"
            else:
                label += " ── (Exclusivo LCM / Sin homólogo en Chopo)"
            study_options.append(label)
            study_map[label] = m

        selected_label = st.selectbox(
            "Selecciona o escribe el estudio que deseas comparar:",
            options=study_options,
            index=0 if study_options else None
        )

        if selected_label and selected_label in study_map:
            item = study_map[selected_label]
            col_lcm, col_vs, col_chopo = st.columns([5, 1, 5])

            with col_lcm:
                st.markdown(f"""
                <div style="background:#f8fafc; border:2px solid #0284c7; border-radius:12px; padding:20px; box-shadow:0 2px 8px rgba(0,0,0,0.05);">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                        <span style="background:#e0f2fe; color:#0369a1; font-weight:700; font-size:0.8rem; padding:4px 10px; border-radius:12px;">
                            LCM · Clave {item['lcm_code']}
                        </span>
                        <span style="color:#64748b; font-size:0.82rem; font-weight:600;">Laboratorios Clínicos de Mérida</span>
                    </div>
                    <h3 style="color:#0f172a; margin:0 0 14px 0; font-size:1.15rem; line-height:1.4;">
                        {item['lcm_name']}
                    </h3>
                    <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:8px; padding:12px; margin-top:10px;">
                        <span style="color:#64748b; font-size:0.8rem; font-weight:600; text-transform:uppercase;">Precio Público con IVA</span>
                        <div style="color:#0284c7; font-size:1.9rem; font-weight:800; margin-top:2px;">
                            ${item['lcm_price']:,.2f} <small style="font-size:0.85rem; font-weight:600; color:#64748b;">MXN</small>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

            with col_vs:
                st.markdown("<div style='height:70px'></div><div style='text-align:center; font-size:1.4rem; font-weight:800; color:#94a3b8;'>VS</div>", unsafe_allow_html=True)

            with col_chopo:
                if item["match_type"] != "NO_MATCH" and item["chopo_name"]:
                    c_web = item["chopo_price_web"]
                    c_list = item["chopo_price_list"]
                    st.markdown(f"""
                    <div style="background:#f8fafc; border:2px solid #64748b; border-radius:12px; padding:20px; box-shadow:0 2px 8px rgba(0,0,0,0.05);">
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                            <span style="background:#f1f5f9; color:#334155; font-weight:700; font-size:0.8rem; padding:4px 10px; border-radius:12px;">
                                Chopo Altabrisa · {item['confidence']}% coincidencia
                            </span>
                            <span style="color:#64748b; font-size:0.82rem; font-weight:600;">Laboratorio Chopo</span>
                        </div>
                        <h3 style="color:#0f172a; margin:0 0 14px 0; font-size:1.15rem; line-height:1.4;">
                            {item['chopo_name']}
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
            if item["match_type"] != "NO_MATCH" and item["diff_mxn"] is not None:
                diff_val = item["diff_mxn"]
                diff_pct = item["diff_pct"]
                st.markdown("<div style='height:15px'></div>", unsafe_allow_html=True)
                if diff_val < 0:
                    st.success(f"""
                    🎉 **Veredicto Comercial: LCM es más económico**  
                    El paciente ahorra **${abs(diff_val):,.2f} MXN ({abs(diff_pct)}%)** realizándose el estudio en **LCM** en comparación con el precio de descuento web de Chopo Mérida.  
                    *(Frente al precio de mostrador de Chopo, el ahorro para el paciente es todavía mayor).*
                    """)
                elif diff_val > 0:
                    st.warning(f"""
                    ⚠️ **Veredicto Comercial: Chopo ofrece menor precio en canal web**  
                    Chopo está posicionado **${diff_val:,.2f} MXN ({diff_pct}%)** por debajo de la lista general de LCM a través de su descuento en línea.  
                    *Recomendación:* Evaluar incluir este estudio en paquetes promocionales o cupones de fidelización LCM.
                    """)
                else:
                    st.info("🤝 **Veredicto Comercial: Mismo precio exacto** en ambos laboratorios.")

    # =========================================================================
    # SUBTAB 2: Paquetes & Check-Ups
    # =========================================================================
    with subtab2:
        st.markdown("#### 📦 Frente a Frente: Paquetes y Check-Ups de Octubre")
        st.caption("Comparación de paquetes preventivos LCM con los Check-Ups más vendidos de Chopo en Mérida.")

        # Tarjetas de Check-ups estrella
        c1, c2 = st.columns(2)

        with c1:
            st.markdown("""
            <div style="background:#ffffff; border:1px solid #cbd5e1; border-top:4px solid #0284c7; border-radius:10px; padding:18px; margin-bottom:15px; box-shadow:0 2px 6px rgba(0,0,0,0.04);">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="background:#f0fdf4; color:#166534; font-weight:700; font-size:0.75rem; padding:3px 8px; border-radius:10px;">🟢 LCM GANA EN PRECIO</span>
                    <span style="font-weight:700; font-size:0.85rem; color:#64748b;">Promo Permanente</span>
                </div>
                <h3 style="color:#0f172a; margin:8px 0 4px 0; font-size:1.2rem;">Check Up Esencial LCM</h3>
                <p style="color:#64748b; font-size:0.85rem; margin:0 0 10px 0;">Incluye: Biometría hemática + Química Sanguínea (30 elementos) + Examen general de orina</p>
                <div style="display:flex; justify-content:space-between; align-items:baseline; background:#f8fafc; padding:10px 14px; border-radius:8px;">
                    <div>
                        <span style="font-size:0.75rem; color:#64748b; display:block;">Precio Promoción LCM</span>
                        <span style="font-size:1.6rem; font-weight:800; color:#0284c7;">$549.00</span>
                    </div>
                    <div style="text-align:right;">
                        <span style="font-size:0.75rem; color:#64748b; display:block;">Chopo Check Up Básico Q45</span>
                        <span style="font-size:1.1rem; font-weight:700; color:#475569;">Web: $597.35</span>
                        <span style="font-size:0.75rem; color:#94a3b8; display:block;">Lista: $919.00</span>
                    </div>
                </div>
                <div style="margin-top:10px; font-size:0.84rem; color:#15803d; font-weight:600;">
                    ✓ LCM es $48.35 más barato que la web de Chopo (-8.1%) y $370 más barato que su mostrador (-40.3%).
                </div>
            </div>
            """, unsafe_allow_html=True)

            st.markdown("""
            <div style="background:#ffffff; border:1px solid #cbd5e1; border-top:4px solid #0284c7; border-radius:10px; padding:18px; margin-bottom:15px; box-shadow:0 2px 6px rgba(0,0,0,0.04);">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="background:#f0fdf4; color:#166534; font-weight:700; font-size:0.75rem; padding:3px 8px; border-radius:10px;">🟢 LCM GANA EN PRECIO</span>
                    <span style="font-weight:700; font-size:0.85rem; color:#64748b;">Promo Permanente</span>
                </div>
                <h3 style="color:#0f172a; margin:8px 0 4px 0; font-size:1.2rem;">Checkup Integral Plus LCM</h3>
                <p style="color:#64748b; font-size:0.85rem; margin:0 0 10px 0;">Incluye: Biometría hemática + Química Sanguínea 50 elementos c/ HbA1c + Examen general de orina</p>
                <div style="display:flex; justify-content:space-between; align-items:baseline; background:#f8fafc; padding:10px 14px; border-radius:8px;">
                    <div>
                        <span style="font-size:0.75rem; color:#64748b; display:block;">Precio Promoción LCM</span>
                        <span style="font-size:1.6rem; font-weight:800; color:#0284c7;">$998.00</span>
                    </div>
                    <div style="text-align:right;">
                        <span style="font-size:0.75rem; color:#64748b; display:block;">Chopo Check Up Integral Q45</span>
                        <span style="font-size:1.1rem; font-weight:700; color:#475569;">Web: $1,175.85</span>
                        <span style="font-size:0.75rem; color:#94a3b8; display:block;">Lista: $1,809.00</span>
                    </div>
                </div>
                <div style="margin-top:10px; font-size:0.84rem; color:#15803d; font-weight:600;">
                    ✓ LCM es $177.85 más barato que la web de Chopo (-15.1%) y $811 más barato que su mostrador (-44.8%).
                </div>
            </div>
            """, unsafe_allow_html=True)

        with c2:
            st.markdown("""
            <div style="background:#ffffff; border:1px solid #cbd5e1; border-top:4px solid #0284c7; border-radius:10px; padding:18px; margin-bottom:15px; box-shadow:0 2px 6px rgba(0,0,0,0.04);">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="background:#f0fdf4; color:#166534; font-weight:700; font-size:0.75rem; padding:3px 8px; border-radius:10px;">🟢 LCM GANA EN PRECIO</span>
                    <span style="font-weight:700; font-size:0.85rem; color:#64748b;">Promo Cuatrimestral</span>
                </div>
                <h3 style="color:#0f172a; margin:8px 0 4px 0; font-size:1.2rem;">Check Up Tiroideo Esencial LCM</h3>
                <p style="color:#64748b; font-size:0.85rem; margin:0 0 10px 0;">Incluye: Perfil tiroideo completo + Biometría hemática + QS (30 elementos) + EGO</p>
                <div style="display:flex; justify-content:space-between; align-items:baseline; background:#f8fafc; padding:10px 14px; border-radius:8px;">
                    <div>
                        <span style="font-size:0.75rem; color:#64748b; display:block;">Precio Promoción LCM</span>
                        <span style="font-size:1.6rem; font-weight:800; color:#0284c7;">$1,050.00</span>
                        <span style="font-size:0.75rem; color:#94a3b8;">Antes: $1,433.00</span>
                    </div>
                    <div style="text-align:right;">
                        <span style="font-size:0.75rem; color:#64748b; display:block;">Chopo Check Up Tiroideo Q45</span>
                        <span style="font-size:1.1rem; font-weight:700; color:#475569;">Web: $1,069.25</span>
                        <span style="font-size:0.75rem; color:#94a3b8; display:block;">Lista: $1,645.00</span>
                    </div>
                </div>
                <div style="margin-top:10px; font-size:0.84rem; color:#15803d; font-weight:600;">
                    ✓ LCM es competitivo ($1,050 vs $1,069.25 web) y $595 más barato que su mostrador (-36.2%).
                </div>
            </div>
            """, unsafe_allow_html=True)

            st.markdown("""
            <div style="background:#ffffff; border:1px solid #cbd5e1; border-top:4px solid #0284c7; border-radius:10px; padding:18px; margin-bottom:15px; box-shadow:0 2px 6px rgba(0,0,0,0.04);">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="background:#f0fdf4; color:#166534; font-weight:700; font-size:0.75rem; padding:3px 8px; border-radius:10px;">🟢 LCM GANA EN PRECIO</span>
                    <span style="font-weight:700; font-size:0.85rem; color:#64748b;">Promo Octubre</span>
                </div>
                <h3 style="color:#0f172a; margin:8px 0 4px 0; font-size:1.2rem;">Vitamina D (25-OH) Total LCM</h3>
                <p style="color:#64748b; font-size:0.85rem; margin:0 0 10px 0;">Prueba clínica clave individual o adicional a paquete</p>
                <div style="display:flex; justify-content:space-between; align-items:baseline; background:#f8fafc; padding:10px 14px; border-radius:8px;">
                    <div>
                        <span style="font-size:0.75rem; color:#64748b; display:block;">Precio Promo / Adicional LCM</span>
                        <span style="font-size:1.6rem; font-weight:800; color:#0284c7;">$640.00</span>
                        <span style="font-size:0.75rem; color:#94a3b8;">Lista: $690.00</span>
                    </div>
                    <div style="text-align:right;">
                        <span style="font-size:0.75rem; color:#64748b; display:block;">Chopo 25-Hidroxi Vitamina D</span>
                        <span style="font-size:1.1rem; font-weight:700; color:#475569;">Web: $748.15</span>
                        <span style="font-size:0.75rem; color:#94a3b8; display:block;">Lista: $1,151.00</span>
                    </div>
                </div>
                <div style="margin-top:10px; font-size:0.84rem; color:#15803d; font-weight:600;">
                    ✓ LCM es $108.15 más barato que la web de Chopo (-14.5%) y $511 más barato que su mostrador (-44.4%).
                </div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("##### 📋 Listado Completo de Paquetes y Promociones LCM (Octubre)")
        pkg_df = pd.DataFrame(packages)
        if not pkg_df.empty:
            pkg_df_show = pkg_df.rename(columns={
                "category": "Categoría",
                "package_name": "Nombre Paquete",
                "code": "Clave",
                "included_tests": "Estudios Incluidos",
                "price_public": "Precio Lista",
                "price_discount_system": "Precio Sistema",
                "price_promo": "Precio Promoción"
            })
            st.dataframe(
                pkg_df_show[["Categoría", "Nombre Paquete", "Precio Promoción", "Precio Lista", "Estudios Incluidos"]],
                use_container_width=True,
                hide_index=True
            )

    # =========================================================================
    # SUBTAB 3: Matriz Completa & Excel
    # =========================================================================
    with subtab3:
        st.markdown("#### 📊 Matriz Consolidada de Estudios Homologados")
        st.caption("Filtra, analiza y exporta los 778 estudios homologados entre LCM y Chopo Mérida Altabrisa.")

        # Controles de filtrado
        fc1, fc2, fc3 = st.columns([2, 2, 3])
        with fc1:
            verdict_filter = st.selectbox(
                "Filtrar por Veredicto Comercial:",
                ["Todos los estudios", "🟢 Solo donde LCM es más barato", "🔴 Solo donde Chopo es más barato", "🔎 Sin homólogo en Chopo"]
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
            diff_m = m["diff_mxn"]
            # Aplicar filtro de veredicto
            if verdict_filter == "🟢 Solo donde LCM es más barato":
                if diff_m is None or diff_m >= 0:
                    continue
            elif verdict_filter == "🔴 Solo donde Chopo es más barato":
                if diff_m is None or diff_m <= 0:
                    continue
            elif verdict_filter == "🔎 Sin homólogo en Chopo":
                if m["match_type"] != "NO_MATCH":
                    continue

            # Aplicar filtro de confianza
            if confidence_filter == "Exacto (100%)" and m["match_type"] != "EXACT":
                continue
            elif confidence_filter == "Alta (>=85%)" and m["match_type"] != "HIGH":
                continue
            elif confidence_filter == "Media (70-84%)" and m["match_type"] != "MEDIUM":
                continue

            # Aplicar búsqueda de texto
            if search_query:
                q = search_query.upper().strip()
                t_lcm = f"{m['lcm_code']} {m['lcm_name']}".upper()
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

            df_rows.append({
                "Clave": m["lcm_code"],
                "Estudio LCM": m["lcm_name"],
                "Precio LCM": m["lcm_price"],
                "Estudio Chopo Mérida": m["chopo_name"] or "N/D",
                "Chopo Web": m["chopo_price_web"],
                "Chopo Mostrador": m["chopo_price_list"],
                "Dif ($)": diff_m,
                "Dif (%)": m["diff_pct"],
                "Veredicto": verd,
                "Confianza": f"{m['confidence']}%" if m["confidence"] > 0 else "0%"
            })

        table_df = pd.DataFrame(df_rows)

        col_count, col_exp = st.columns([3, 1])
        with col_count:
            st.write(f"Mostrando **{len(table_df):,}** estudios coincidentes con los filtros seleccionados.")
        with col_exp:
            if not table_df.empty:
                # Generar Excel en memoria
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
                    "Precio LCM": "${:,.2f}",
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
