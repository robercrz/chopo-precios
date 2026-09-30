# ============================================================
# scripts/build_full_2026_promotions.py
# Ingesta completa del historial de promociones LCM 2026
# (Enero a Octubre 2026 + Paquetes Cuatrimestrales + Permanentes)
# ============================================================

import sys
from pathlib import Path
from datetime import date
import json
import re

import openpyxl

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROMOS_DIR = BASE_DIR / "data" / "lcm" / "promos_2026"
OUTPUT_FILE = BASE_DIR / "config" / "lcm_promotions.json"


def parse_price(val):
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val)
    # Buscar patrones como $590, $1,100, 549, 998.00
    m = re.search(r'\$\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?)', s)
    if m:
        try:
            return float(m.group(1).replace(',', ''))
        except Exception:
            pass
    # Buscar solo número
    m2 = re.search(r'([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?)', s)
    if m2:
        try:
            return float(m2.group(1).replace(',', ''))
        except Exception:
            pass
    return None


def clean_text(v):
    if v is None:
        return ""
    return " ".join(str(v).replace("\n", " ").split()).strip()


def build_promotions():
    promotions = []
    today = date.today()

    # ─────────────────────────────────────────────────────────────
    # 1. PROMOCIONES PERMANENTES (Vigentes)
    # ─────────────────────────────────────────────────────────────
    permanentes = [
        {
            "id": "promo_perm_esencial",
            "name": "Check Up Esencial",
            "category": "Promo Permanente",
            "period": "Permanentes",
            "institution": "PROMPERM / PROMOCIONES PERMANENTES",
            "validity_type": "permanent",
            "start_date": "2025-01-01",
            "end_date": None,
            "studies": ["Biometría hemática", "Química Sanguínea (30 elementos)", "Examen general de orina"],
            "price_regular": 750.0,
            "price_promo": 549.0,
            "chopo_equivalent": "CHECK UP BÁSICO QUÍMICA DE 45 ELEMENTOS",
            "notes": "Incluye BH, QS 30 y EGO (Precio ajustado a $549 desde Junio 2026, antes $590)"
        },
        {
            "id": "promo_perm_avanzado",
            "name": "Checkup Avanzado",
            "category": "Promo Permanente",
            "period": "Permanentes",
            "institution": "PROMPERM / PROMOCIONES PERMANENTES",
            "validity_type": "permanent",
            "start_date": "2025-01-01",
            "end_date": None,
            "studies": ["Biometría hemática", "Química Sanguínea (40 elementos)", "Examen general de orina"],
            "price_regular": 1150.0,
            "price_promo": 890.0,
            "chopo_equivalent": "CHECK UP SALUD QUÍMICA DE 45 ELEMENTOS",
            "notes": "Incluye BH, QS 40 y EGO"
        },
        {
            "id": "promo_perm_integral_plus",
            "name": "Checkup Integral Plus",
            "category": "Promo Permanente",
            "period": "Permanentes",
            "institution": "PROMPERM / PROMOCIONES PERMANENTES",
            "validity_type": "permanent",
            "start_date": "2025-01-01",
            "end_date": None,
            "studies": ["Biometría hemática", "Química Sanguínea de 50 elementos c/ HbA1c", "Examen general de orina"],
            "price_regular": 1450.0,
            "price_promo": 998.0,
            "chopo_equivalent": "CHECK UP INTEGRAL Q45",
            "notes": "Incluye BH, QS 50 c/ Hemoglobina Glicosilada y EGO (Ajustado a $998 desde Junio 2026, antes $1,199)"
        },
        {
            "id": "promo_perm_inicial",
            "name": "Check Up Inicial",
            "category": "Promo Permanente",
            "period": "Permanentes",
            "institution": "PROMPERM / PROMOCIONES PERMANENTES",
            "validity_type": "permanent",
            "start_date": "2025-01-01",
            "end_date": None,
            "studies": ["Biometría hemática", "Química Sanguínea (6 elementos)", "Examen general de orina"],
            "price_regular": 620.0,
            "price_promo": 470.0,
            "chopo_equivalent": "QUÍMICA 6 + BIOMETRÍA + EGO",
            "notes": "Paquete básico para chequeo general"
        }
    ]
    promotions.extend(permanentes)

    # ─────────────────────────────────────────────────────────────
    # 2. CUATRIMESTRES HISTÓRICOS Y ACTUAL
    # ─────────────────────────────────────────────────────────────
    # Cuatrimestre 1: Ene - Abr 2026
    cuat1 = [
        {
            "id": "promo_c1_hba1c",
            "name": "Hemoglobina Glicosilada (Cuatrimestral)",
            "category": "Promo Cuatrimestral",
            "period": "Cuatrimestre 1 (Ene - Abr 2026)",
            "institution": "PAQUETES CUATRIMESTRALES",
            "validity_type": "custom_date",
            "start_date": "2026-01-01",
            "end_date": "2026-04-30",
            "studies": ["Hemoglobina glicosilada (HBA1C)"],
            "price_regular": 290.0,
            "price_promo": 245.0,
            "chopo_equivalent": "HEMOGLOBINA GLICOSILADA",
            "notes": "Promoción cuatrimestral Enero a Abril 2026",
            "is_archived": True
        },
        {
            "id": "promo_c1_vitd",
            "name": "Vitamina D (25-OH) Total (Cuatrimestral)",
            "category": "Promo Cuatrimestral",
            "period": "Cuatrimestre 1 (Ene - Abr 2026)",
            "institution": "PAQUETES CUATRIMESTRALES",
            "validity_type": "custom_date",
            "start_date": "2026-01-01",
            "end_date": "2026-04-30",
            "studies": ["Vitamina D (25-OH) total"],
            "price_regular": 690.0,
            "price_promo": 645.0,
            "chopo_equivalent": "25 HIDROXI VITAMINA D TOTAL (CALCIFEROL)",
            "notes": "Promoción cuatrimestral Enero a Abril 2026",
            "is_archived": True
        },
        {
            "id": "promo_c1_tiroideo",
            "name": "Perfil Tiroideo Completo (en Paquete C1)",
            "category": "Promo Cuatrimestral",
            "period": "Cuatrimestre 1 (Ene - Abr 2026)",
            "institution": "PAQUETES CUATRIMESTRALES",
            "validity_type": "custom_date",
            "start_date": "2026-01-01",
            "end_date": "2026-04-30",
            "studies": ["Perfil tiroideo completo"],
            "price_regular": 690.0,
            "price_promo": 645.0,
            "chopo_equivalent": "PERFIL TIROIDEO",
            "notes": "Tarifa especial como adicional a cualquier Check Up en C1",
            "is_archived": True
        }
    ]
    promotions.extend(cuat1)

    # Cuatrimestre 2: May - Ago 2026
    cuat2 = [
        {
            "id": "promo_c2_psa",
            "name": "Antígeno Prostático Específico (PSA) Cuatrimestral",
            "category": "Promo Cuatrimestral",
            "period": "Cuatrimestre 2 (May - Ago 2026)",
            "institution": "PAQUETES CUATRIMESTRALES",
            "validity_type": "custom_date",
            "start_date": "2026-05-01",
            "end_date": "2026-08-31",
            "studies": ["Antígeno prostático específico (PSA) total"],
            "price_regular": 480.0,
            "price_promo": 260.0,
            "chopo_equivalent": "ANTIGENO PROSTATICO TOTAL",
            "notes": "Descuento especial de cuatrimestre May - Ago 2026 ($260)",
            "is_archived": True
        },
        {
            "id": "promo_c2_hormonal_fem",
            "name": "Perfil Hormonal Femenino Cuatrimestral",
            "category": "Promo Cuatrimestral",
            "period": "Cuatrimestre 2 (May - Ago 2026)",
            "institution": "PAQUETES CUATRIMESTRALES",
            "validity_type": "custom_date",
            "start_date": "2026-05-01",
            "end_date": "2026-08-31",
            "studies": ["Perfil hormonal femenino"],
            "price_regular": 1090.0,
            "price_promo": 919.0,
            "chopo_equivalent": "PERFIL HORMONAL",
            "notes": "Tarifa especial cuatrimestral May - Ago 2026 ($919)",
            "is_archived": True
        },
        {
            "id": "promo_c2_salud_sexual",
            "name": "Check Up Salud Sexual (VIH + VDRL)",
            "category": "Promo Cuatrimestral",
            "period": "Cuatrimestre 2 (May - Ago 2026)",
            "institution": "PAQUETES CUATRIMESTRALES",
            "validity_type": "custom_date",
            "start_date": "2026-05-01",
            "end_date": "2026-08-31",
            "studies": ["Ac Anti VIH 1 y 2", "VDRL"],
            "price_regular": 650.0,
            "price_promo": 408.0,
            "chopo_equivalent": "VIH 1 Y 2 + VDRL",
            "notes": "Detección rápida ITS en cuatrimestre 2",
            "is_archived": True
        }
    ]
    promotions.extend(cuat2)

    # Cuatrimestre 3: Sep - Dic 2026 (ACTUAL - Vence 31 Dic)
    cuat3 = [
        {
            "id": "promo_cuat_tiroideo",
            "name": "Check Up Tiroideo Esencial",
            "category": "Promo Cuatrimestral",
            "period": "Cuatrimestre Sep - Dic 2026",
            "institution": "PAQUETES CUATRIMESTRALES",
            "validity_type": "custom_date",
            "start_date": "2026-09-01",
            "end_date": "2026-12-31",
            "studies": ["Perfil tiroideo completo", "Biometría hemática", "Química Sanguínea (30 elementos)", "Examen general de orina"],
            "price_regular": 1433.0,
            "price_promo": 1050.0,
            "chopo_equivalent": "CHECK UP BÁSICO TIROIDEO QUÍMICA DE 45 ELEMENTOS",
            "notes": "Perfil tiroideo completo + Check Up Esencial (Vence 31 dic 2026)"
        },
        {
            "id": "promo_cuat_vitamina_d",
            "name": "Check Up Esencial + Vitamina D",
            "category": "Promo Cuatrimestral",
            "period": "Cuatrimestre Sep - Dic 2026",
            "institution": "PAQUETES CUATRIMESTRALES",
            "validity_type": "custom_date",
            "start_date": "2026-09-01",
            "end_date": "2026-12-31",
            "studies": ["Biometría hemática", "Química Sanguínea (30 elementos)", "Examen general de orina", "Vitamina D (25-OH) total"],
            "price_regular": 1433.0,
            "price_promo": 1100.0,
            "chopo_equivalent": "CHECK UP BÁSICO Q45 + VITAMINA D",
            "notes": "Check Up Esencial con Vitamina D incluida (Vence 31 dic 2026)"
        },
        {
            "id": "promo_cuat_vitd_indiv",
            "name": "Vitamina D (25-OH) Total",
            "category": "Promo Cuatrimestral",
            "period": "Cuatrimestre Sep - Dic 2026",
            "institution": "PAQUETES CUATRIMESTRALES",
            "validity_type": "custom_date",
            "start_date": "2026-09-01",
            "end_date": "2026-12-31",
            "studies": ["Vitamina D (25-OH) total"],
            "price_regular": 690.0,
            "price_promo": 640.0,
            "chopo_equivalent": "25 HIDROXI VITAMINA D TOTAL (CALCIFEROL)",
            "notes": "Precio promocional cuatrimestral (Vence 31 dic 2026)"
        },
        {
            "id": "promo_cuat_rayos_x",
            "name": "Rayos X (50% de Descuento)",
            "category": "Promo Cuatrimestral",
            "period": "Cuatrimestre Sep - Dic 2026",
            "institution": "PAQUETES CUATRIMESTRALES",
            "validity_type": "custom_date",
            "start_date": "2026-09-01",
            "end_date": "2026-12-31",
            "studies": ["Rayos X tórax PA"],
            "price_regular": 690.0,
            "price_promo": 345.0,
            "chopo_equivalent": "TELE DE TORAX O RADIOGRAFIA TORAX PA",
            "notes": "50% de descuento en el resto de Rayos X al cotizar o preguntar (Vence 31 dic 2026)"
        }
    ]
    promotions.extend(cuat3)

    # ─────────────────────────────────────────────────────────────
    # 3. CAMPAÑAS MENSUALES HISTÓRICAS (Enero a Septiembre 2026)
    # ─────────────────────────────────────────────────────────────
    # Enero 2026
    promotions.append({
        "id": "promo_m_ene_salud_mujer",
        "name": "Check Up Salud Mujer Enero",
        "category": "Promo del Mes",
        "period": "Enero 2026",
        "institution": "PROMOMES",
        "validity_type": "custom_date",
        "start_date": "2026-01-01",
        "end_date": "2026-01-31",
        "studies": ["Biometría hemática", "Química Sanguínea (30 elementos)", "Examen general de orina", "Papanicolaou", "Ultrasonido pélvico"],
        "price_regular": 2100.0,
        "price_promo": 1499.0,
        "chopo_equivalent": "CHECK UP MUJER",
        "notes": "Campaña de inicio de año Salud Femenina",
        "is_archived": True
    })
    promotions.append({
        "id": "promo_m_ene_alergenos_inh",
        "name": "Perfil de Alérgenos Inhalatorios",
        "category": "Promo del Mes",
        "period": "Enero 2026",
        "institution": "PROMOMES",
        "validity_type": "custom_date",
        "start_date": "2026-01-01",
        "end_date": "2026-01-31",
        "studies": ["Perfil de alérgenos inhalatorios"],
        "price_regular": 2450.0,
        "price_promo": 1890.0,
        "chopo_equivalent": "PANEL DE ALERGENOS RESPIRATORIOS",
        "notes": "Detección de rinitis y alergias respiratorias",
        "is_archived": True
    })
    promotions.append({
        "id": "promo_m_ene_alergenos_comb",
        "name": "Perfil de Alérgenos Combinado (Alimentos e Inhalatorios)",
        "category": "Promo del Mes",
        "period": "Enero 2026",
        "institution": "PROMOMES",
        "validity_type": "custom_date",
        "start_date": "2026-01-01",
        "end_date": "2026-01-31",
        "studies": ["Perfil de alérgenos inhalatorios", "Perfil de alérgenos alimenticios"],
        "price_regular": 4500.0,
        "price_promo": 3490.0,
        "chopo_equivalent": "PANEL COMPLETO DE ALERGIAS",
        "notes": "Panel integral de alérgenos",
        "is_archived": True
    })

    # Febrero 2026
    promotions.append({
        "id": "promo_m_feb_salud_mujer",
        "name": "Salud Mujer (Febrero)",
        "category": "Promo del Mes",
        "period": "Febrero 2026",
        "institution": "PROMOMES",
        "validity_type": "custom_date",
        "start_date": "2026-02-01",
        "end_date": "2026-02-28",
        "studies": ["Biometría hemática", "Química Sanguínea (30 elementos)", "Examen general de orina"],
        "price_regular": 2100.0,
        "price_promo": 1499.0,
        "chopo_equivalent": "CHECK UP MUJER",
        "notes": "Paquete Salud Mujer",
        "is_archived": True
    })
    promotions.append({
        "id": "promo_m_feb_alergenos",
        "name": "Perfil de Alérgenos Alimenticios",
        "category": "Promo del Mes",
        "period": "Febrero 2026",
        "institution": "PROMOMES",
        "validity_type": "custom_date",
        "start_date": "2026-02-01",
        "end_date": "2026-02-28",
        "studies": ["Perfil de alérgenos alimenticios"],
        "price_regular": 2450.0,
        "price_promo": 1890.0,
        "chopo_equivalent": "PANEL DE ALERGENOS ALIMENTARIOS",
        "notes": "Detección de intolerancias y alergias alimentarias",
        "is_archived": True
    })

    # Marzo 2026
    promotions.append({
        "id": "promo_m_mar_salud_mujer",
        "name": "Salud Mujer (Mes de la Mujer)",
        "category": "Promo del Mes",
        "period": "Marzo 2026",
        "institution": "PROMOMES",
        "validity_type": "custom_date",
        "start_date": "2026-03-01",
        "end_date": "2026-03-31",
        "studies": ["Biometría hemática", "Química Sanguínea (30 elementos)", "Examen general de orina", "Perfil hormonal femenino"],
        "price_regular": 2100.0,
        "price_promo": 1499.0,
        "chopo_equivalent": "CHECK UP MUJER",
        "notes": "Campaña Día Internacional de la Mujer",
        "is_archived": True
    })

    # Abril 2026
    promotions.append({
        "id": "promo_m_abr_pediatrico",
        "name": "Check Up Pediátrico Integral (Mes del Niño)",
        "category": "Promo del Mes",
        "period": "Abril 2026",
        "institution": "PROMOMES",
        "validity_type": "custom_date",
        "start_date": "2026-04-01",
        "end_date": "2026-04-30",
        "studies": ["Biometría hemática", "Examen general de orina", "Coproparasitoscópico (1)", "Grupo sanguíneo y factor Rh"],
        "price_regular": 1150.0,
        "price_promo": 840.0,
        "chopo_equivalent": "CHECK UP INFANTIL",
        "notes": "Campaña infantil Mes del Niño",
        "is_archived": True
    })

    # Mayo 2026
    promotions.append({
        "id": "promo_m_may_madres_vitd",
        "name": "Especial Día de las Madres (Vitamina D)",
        "category": "Promo del Mes",
        "period": "Mayo 2026",
        "institution": "PROMOMES",
        "validity_type": "custom_date",
        "start_date": "2026-05-01",
        "end_date": "2026-05-31",
        "studies": ["Vitamina D (25-OH) total"],
        "price_regular": 690.0,
        "price_promo": 552.0,
        "chopo_equivalent": "25 HIDROXI VITAMINA D TOTAL",
        "notes": "20% de descuento especial por el Día de las Madres (de $690 a $552)",
        "is_archived": True
    })
    promotions.append({
        "id": "promo_m_may_maestros",
        "name": "Descuento Especial Día del Maestro",
        "category": "Convenio Especial",
        "period": "Mayo 2026",
        "institution": "PROMOMES",
        "validity_type": "custom_date",
        "start_date": "2026-05-01",
        "end_date": "2026-05-31",
        "studies": ["Check Up Esencial", "Checkup Avanzado"],
        "price_regular": 590.0,
        "price_promo": 501.50,
        "chopo_equivalent": "DESCUENTO DOCENTE",
        "notes": "15% de descuento en estudios generales para docentes acreditados SEP/UADY/SNTE",
        "is_archived": True
    })

    # Junio 2026 (Día del Padre)
    promotions.append({
        "id": "promo_m_jun_que_padre_1",
        "name": "CHECK UP QUE PADRE 1 (Día del Padre)",
        "category": "Promo del Mes",
        "period": "Junio 2026",
        "institution": "PROMOMES",
        "validity_type": "custom_date",
        "start_date": "2026-06-01",
        "end_date": "2026-06-30",
        "studies": ["Biometría hemática", "Glucosa", "Colesterol", "Triglicéridos", "Antígeno Prostático específico (PSA)", "Hemoglobina Glicosilada (HBA1C)"],
        "price_regular": 990.0,
        "price_promo": 689.0,
        "chopo_equivalent": "CHECK UP HOMBRE BASICO",
        "notes": "Campaña Día del Padre paquete básico",
        "is_archived": True
    })
    promotions.append({
        "id": "promo_m_jun_que_padre_2",
        "name": "CHECK UP QUE PADRE 2 (Día del Padre Integral)",
        "category": "Promo del Mes",
        "period": "Junio 2026",
        "institution": "PROMOMES",
        "validity_type": "custom_date",
        "start_date": "2026-06-01",
        "end_date": "2026-06-30",
        "studies": ["Biometría hemática", "Química Sanguínea (30 elementos)", "Antígeno Prostático específico (PSA)", "Hemoglobina Glicosilada (HBA1C)"],
        "price_regular": 1390.0,
        "price_promo": 955.0,
        "chopo_equivalent": "CHECK UP HOMBRE INTEGRAL",
        "notes": "Campaña Día del Padre paquete completo",
        "is_archived": True
    })
    promotions.append({
        "id": "promo_m_jun_hormonal_masc",
        "name": "Perfil Hormonal Masculino (Clave 1406)",
        "category": "Promo del Mes",
        "period": "Junio 2026",
        "institution": "PROMOMES",
        "validity_type": "custom_date",
        "start_date": "2026-06-01",
        "end_date": "2026-06-30",
        "studies": ["Perfil hormonal masculino"],
        "price_regular": 1190.0,
        "price_promo": 952.0,
        "chopo_equivalent": "PERFIL HORMONAL MASCULINO",
        "notes": "20% de descuento (de $1,190 a $952)",
        "is_archived": True
    })

    # Julio 2026
    promotions.append({
        "id": "promo_m_jul_tiroideo",
        "name": "Perfil Tiroideo Completo (Julio)",
        "category": "Promo del Mes",
        "period": "Julio 2026",
        "institution": "PROMOMES",
        "validity_type": "custom_date",
        "start_date": "2026-07-01",
        "end_date": "2026-07-31",
        "studies": ["Perfil tiroideo completo"],
        "price_regular": 690.0,
        "price_promo": 590.0,
        "chopo_equivalent": "PERFIL TIROIDEO",
        "notes": "Promoción mensual de Julio ($590)",
        "is_archived": True
    })
    promotions.append({
        "id": "promo_m_jul_dengue",
        "name": "Prueba Detección Dengue (Antígeno NS1 + IgG/IgM)",
        "category": "Promo del Mes",
        "period": "Julio 2026",
        "institution": "PROMOMES",
        "validity_type": "custom_date",
        "start_date": "2026-07-01",
        "end_date": "2026-07-31",
        "studies": ["ANTÍGENO NS1 Y AC ANTI-DENGUE IgG IgM"],
        "price_regular": 590.0,
        "price_promo": 472.0,
        "chopo_equivalent": "PRUEBA DUO DENGUE",
        "notes": "20% de descuento por temporada de lluvias y prevención epidemiológica",
        "is_archived": True
    })
    promotions.append({
        "id": "promo_m_jul_hepatitis",
        "name": "Pruebas de Hepatitis A, B y C (Día Mundial)",
        "category": "Promo del Mes",
        "period": "Julio 2026",
        "institution": "PROMOMES",
        "validity_type": "custom_date",
        "start_date": "2026-07-01",
        "end_date": "2026-07-31",
        "studies": ["Perfil de hepatitis"],
        "price_regular": 890.0,
        "price_promo": 712.0,
        "chopo_equivalent": "PANEL HEPATITIS VIRAL",
        "notes": "20% de descuento en el marco del Día Mundial contra la Hepatitis",
        "is_archived": True
    })

    # Agosto 2026
    promotions.append({
        "id": "promo_m_ago_tiroideo",
        "name": "Perfil Tiroideo Completo (Agosto)",
        "category": "Promo del Mes",
        "period": "Agosto 2026",
        "institution": "PROMOMES",
        "validity_type": "custom_date",
        "start_date": "2026-08-01",
        "end_date": "2026-08-31",
        "studies": ["Perfil tiroideo completo"],
        "price_regular": 690.0,
        "price_promo": 590.0,
        "chopo_equivalent": "PERFIL TIROIDEO",
        "notes": "Promoción mensual de Agosto ($590)",
        "is_archived": True
    })
    promotions.append({
        "id": "promo_m_ago_mi_primer_checkup",
        "name": "Mi Primer Check Up En LCM (Regreso a Clases)",
        "category": "Promo del Mes",
        "period": "Agosto 2026",
        "institution": "PROMOMES",
        "validity_type": "custom_date",
        "start_date": "2026-08-01",
        "end_date": "2026-08-31",
        "studies": ["Biometría hemática", "Química Sanguínea (30 elementos)", "Examen general de orina"],
        "price_regular": 750.0,
        "price_promo": 498.0,
        "chopo_equivalent": "CHECK UP ESCOLAR",
        "notes": "Paquete especial regreso a clases por debajo de $500",
        "is_archived": True
    })
    promotions.append({
        "id": "promo_m_ago_dengue",
        "name": "Prueba de Detección de Dengue (Agosto)",
        "category": "Promo del Mes",
        "period": "Agosto 2026",
        "institution": "PROMOMES",
        "validity_type": "custom_date",
        "start_date": "2026-08-01",
        "end_date": "2026-08-31",
        "studies": ["ANTÍGENO NS1 Y AC ANTI-DENGUE IgG IgM"],
        "price_regular": 590.0,
        "price_promo": 472.0,
        "chopo_equivalent": "PRUEBA DUO DENGUE",
        "notes": "20% de descuento por prevención epidemiológica",
        "is_archived": True
    })

    # Septiembre 2026
    promotions.append({
        "id": "promo_m_sep_tiroideo",
        "name": "Perfil Tiroideo Completo (Septiembre)",
        "category": "Promo del Mes",
        "period": "Septiembre 2026",
        "institution": "PROMOMES",
        "validity_type": "custom_date",
        "start_date": "2026-09-01",
        "end_date": "2026-09-30",
        "studies": ["Perfil tiroideo completo"],
        "price_regular": 690.0,
        "price_promo": 530.0,
        "chopo_equivalent": "PERFIL TIROIDEO",
        "notes": "Precio especial en sistema $530 durante el Mes Patrio",
        "is_archived": True
    })
    promotions.append({
        "id": "promo_m_sep_salud_sexual",
        "name": "Check Up Salud Sexual (Septiembre)",
        "category": "Promo del Mes",
        "period": "Septiembre 2026",
        "institution": "PROMOMES",
        "validity_type": "custom_date",
        "start_date": "2026-09-01",
        "end_date": "2026-09-30",
        "studies": ["Ac Anti VIH 1 y 2", "VDRL"],
        "price_regular": 650.0,
        "price_promo": 408.0,
        "chopo_equivalent": "VIH 1 Y 2 + VDRL",
        "notes": "Detección rápida ITS",
        "is_archived": True
    })

    # ─────────────────────────────────────────────────────────────
    # 4. CAMPAÑA OCTUBRE 2026 (Inicia Mañana 1 de Octubre)
    # ─────────────────────────────────────────────────────────────
    octubre = [
        {
            "id": "promo_oct_perfil_tiroideo",
            "name": "Perfil Tiroideo Completo",
            "category": "Promo del Mes",
            "period": "Octubre 2026",
            "institution": "PROMOMES",
            "validity_type": "custom_date",
            "start_date": "2026-10-01",
            "end_date": "2026-10-31",
            "studies": ["Perfil tiroideo completo"],
            "price_regular": 690.0,
            "price_promo": 590.0,
            "chopo_equivalent": "PERFIL TIROIDEO",
            "notes": "Promoción mensual de Octubre 2026 (Inicia mañana 1 Oct)"
        },
        {
            "id": "promo_oct_perfil_femenino",
            "name": "Perfil Hormonal Femenino",
            "category": "Promo del Mes",
            "period": "Octubre 2026",
            "institution": "PROMOMES",
            "validity_type": "custom_date",
            "start_date": "2026-10-01",
            "end_date": "2026-10-31",
            "studies": ["Perfil hormonal femenino"],
            "price_regular": 1090.0,
            "price_promo": 980.0,
            "chopo_equivalent": "PERFIL HORMONAL",
            "notes": "Ginecológico completo del mes de Octubre (Inicia 1 Oct)"
        },
        {
            "id": "promo_oct_us_mama",
            "name": "Ultrasonido de mama",
            "category": "Promo del Mes",
            "period": "Octubre 2026",
            "institution": "PROMOMES",
            "validity_type": "custom_date",
            "start_date": "2026-10-01",
            "end_date": "2026-10-31",
            "studies": ["Ultrasonido de mama"],
            "price_regular": 1021.0,
            "price_promo": 899.0,
            "chopo_equivalent": "ULTRASONIDO MAMARIO",
            "notes": "Mes Rosa / Cáncer de Mama (Inicia 1 Oct)"
        },
        {
            "id": "promo_oct_ca153",
            "name": "ANTÍGENO CARBOHIDRATO 15-3 (CA 15-3)",
            "category": "Promo del Mes",
            "period": "Octubre 2026",
            "institution": "PROMOMES",
            "validity_type": "custom_date",
            "start_date": "2026-10-01",
            "end_date": "2026-10-31",
            "studies": ["ANTÍGENO CARBOHIDRATO 15-3 (CA 15-3)"],
            "price_regular": 696.0,
            "price_promo": 590.0,
            "chopo_equivalent": "ANTIGENO CA 15-3",
            "notes": "Marcador tumoral de mama en descuento (de $696 a $590)"
        },
        {
            "id": "promo_oct_ca125",
            "name": "ANTÍGENO CARBOHIDRATO 125 (CA-125)",
            "category": "Promo del Mes",
            "period": "Octubre 2026",
            "institution": "PROMOMES",
            "validity_type": "custom_date",
            "start_date": "2026-10-01",
            "end_date": "2026-10-31",
            "studies": ["ANTÍGENO CARBOHIDRATO 125 (CA-125)"],
            "price_regular": 696.0,
            "price_promo": 590.0,
            "chopo_equivalent": "ANTIGENO CA 125",
            "notes": "Marcador tumoral ovárico en descuento (de $696 a $590)"
        },
        {
            "id": "promo_oct_cumple",
            "name": "Cumpleañeros del Mes de Octubre",
            "category": "Promo del Mes",
            "period": "Octubre 2026",
            "institution": "PROMOMES",
            "validity_type": "custom_date",
            "start_date": "2026-10-01",
            "end_date": "2026-10-31",
            "studies": ["Check Up Esencial", "Checkup Avanzado"],
            "price_regular": 549.0,
            "price_promo": 466.65,
            "chopo_equivalent": "DESCUENTO DE CUMPLEAÑOS CHOPO",
            "notes": "15% de descuento en el sistema para cumpleañeros de Octubre"
        }
    ]
    promotions.extend(octubre)

    # ─────────────────────────────────────────────────────────────
    # EVALUAR ESTADOS DE VIGENCIA PARA CADA PROMOCIÓN
    # ─────────────────────────────────────────────────────────────
    for p in promotions:
        if p.get("is_archived"):
            p["status"] = "ARCHIVED"
            end_s = p.get("end_date", "")
            p["status_label"] = f"🔴 Finalizada ({end_s})" if end_s else "📜 Archivado en Histórico"
            p["days_left"] = -1
            continue

        v_type = p.get("validity_type", "permanent")
        start_date_str = p.get("start_date")
        end_date_str = p.get("end_date")

        if v_type == "permanent" or (not end_date_str and not start_date_str):
            p["status"] = "PERMANENT"
            p["status_label"] = "🔵 Permanente"
            p["days_left"] = None
            continue

        if start_date_str:
            try:
                start_d = date.fromisoformat(start_date_str)
                if today < start_d:
                    delta_start = (start_d - today).days
                    p["status"] = "UPCOMING"
                    p["days_until_start"] = delta_start
                    if delta_start == 1:
                        p["status_label"] = f"🟡 Inicia Mañana (01/{start_d.strftime('%m/%Y')})"
                    else:
                        p["status_label"] = f"🟡 Inicia en {delta_start} días ({start_d.strftime('%d/%m/%Y')})"
                    if end_date_str:
                        p["days_left"] = (date.fromisoformat(end_date_str) - today).days
                    continue
            except Exception:
                pass

        if end_date_str:
            try:
                end_d = date.fromisoformat(end_date_str)
                delta = (end_d - today).days
                p["days_left"] = delta
                if delta < 0:
                    p["status"] = "EXPIRED"
                    p["status_label"] = f"🔴 Finalizada ({end_d.strftime('%d/%m/%Y')})"
                elif delta <= 3:
                    p["status"] = "EXPIRING_SOON"
                    p["status_label"] = f"🟠 Por vencer ({delta} día{'s' if delta != 1 else ''})"
                else:
                    p["status"] = "ACTIVE"
                    p["status_label"] = f"🟢 Activa (vence {end_d.strftime('%d/%m/%Y')})"
            except Exception:
                p["status"] = "UNKNOWN"
                p["status_label"] = "⚪ Sin fecha válida"

    # Guardar en archivo JSON
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(promotions, f, ensure_ascii=False, indent=2)

    print(f"✅ Se han procesado e indexado con éxito {len(promotions)} promociones y paquetes de LCM para 2026.")
    periods = list({p.get('period') for p in promotions if p.get('period')})
    print(f"Períodos indexados ({len(periods)}):", sorted(periods))


if __name__ == "__main__":
    build_promotions()
