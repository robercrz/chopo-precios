# ============================================================
# scraper/lcm_manager.py
# Gestor de Datos LCM: Modificaciones Manuales, Catálogos Custom
# y Administrador de Paquetes / Promociones con Plazos de Vigencia
# ============================================================

import os
import re
import json
import sqlite3
import unicodedata
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

import pandas as pd
from rapidfuzz import fuzz

BASE_DIR = Path(__file__).parent.parent
CONFIG_DIR = BASE_DIR / "config"
DATA_LCM_DIR = BASE_DIR / "data" / "lcm"
DB_PATH = BASE_DIR / "db" / "chopo_prices.db"

OVERRIDES_FILE = CONFIG_DIR / "lcm_price_overrides.json"
PROMOTIONS_FILE = CONFIG_DIR / "lcm_promotions.json"
ADICIONALES_FILE = CONFIG_DIR / "lcm_adicionales.json"
BASE_MATCHES_FILE = DATA_LCM_DIR / "lcm_chopo_matches.json"



def ensure_dirs():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    DATA_LCM_DIR.mkdir(parents=True, exist_ok=True)


# ── 1. GESTOR DE MODIFICACIONES MANUALES DE PRECIO ────────────────────────────

def load_price_overrides() -> Dict[str, Dict[str, Any]]:
    """
    Carga modificaciones manuales de precio guardadas por clave de estudio LCM.
    Estructura: { "code_or_name": {"price": float, "updated_at": str, "notes": str} }
    """
    ensure_dirs()
    if not OVERRIDES_FILE.exists():
        return {}
    try:
        with open(OVERRIDES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_price_override(study_key: str, study_name: str, new_price: float, notes: str = "") -> bool:
    """Guarda o actualiza el precio manual de un estudio LCM."""
    ensure_dirs()
    overrides = load_price_overrides()
    overrides[str(study_key).strip()] = {
        "study_name": study_name,
        "price": float(new_price),
        "updated_at": datetime.now().isoformat(),
        "notes": notes.strip()
    }
    try:
        with open(OVERRIDES_FILE, "w", encoding="utf-8") as f:
            json.dump(overrides, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def delete_price_override(study_key: str) -> bool:
    """Elimina la modificación manual y restaura el precio original."""
    overrides = load_price_overrides()
    k = str(study_key).strip()
    if k in overrides:
        del overrides[k]
        try:
            with open(OVERRIDES_FILE, "w", encoding="utf-8") as f:
                json.dump(overrides, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False
    return False


# ── 2. GESTOR DE PAQUETES Y PROMOCIONES CON VIGENCIA ──────────────────────────

def load_promotions() -> List[Dict[str, Any]]:
    """Carga la lista de paquetes y promociones con vigencia."""
    ensure_dirs()
    if not PROMOTIONS_FILE.exists():
        # Inicializar con promociones de octubre por defecto si no existe
        init_promos = _get_default_october_promotions()
        save_all_promotions(init_promos)
        return init_promos
    try:
        with open(PROMOTIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_all_promotions(promos: List[Dict[str, Any]]) -> bool:
    ensure_dirs()
    try:
        with open(PROMOTIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(promos, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def add_or_update_promotion(promo_data: Dict[str, Any]) -> bool:
    """Crea o actualiza una promoción con cálculo de plazos y vigencia."""
    promos = load_promotions()
    p_id = promo_data.get("id") or f"promo_{int(datetime.now().timestamp())}"
    promo_data["id"] = p_id
    promo_data["updated_at"] = datetime.now().isoformat()

    # Calcular estado de vigencia
    promo_data = evaluate_promo_validity(promo_data)

    existing_idx = next((i for i, p in enumerate(promos) if p.get("id") == p_id), None)
    if existing_idx is not None:
        promos[existing_idx] = promo_data
    else:
        promos.append(promo_data)

    return save_all_promotions(promos)


def delete_promotion(promo_id: str) -> bool:
    promos = load_promotions()
    filtered = [p for p in promos if p.get("id") != promo_id]
    return save_all_promotions(filtered)


def evaluate_promo_validity(promo: Dict[str, Any]) -> Dict[str, Any]:
    """Calcula si la promoción está Activa, Por Vencer o Vencida según la fecha actual."""
    validity_type = promo.get("validity_type", "permanent")  # permanent, days, month_end, custom_date
    end_date_str = promo.get("end_date")
    today = date.today()

    if validity_type == "permanent" or not end_date_str:
        promo["status"] = "PERMANENT"
        promo["status_label"] = "🔵 Permanente"
        promo["days_left"] = None
        return promo

    try:
        end_d = date.fromisoformat(end_date_str)
        delta = (end_d - today).days

        promo["days_left"] = delta
        if delta < 0:
            promo["status"] = "EXPIRED"
            promo["status_label"] = f"🔴 Vencida hace {abs(delta)} días"
        elif delta <= 3:
            promo["status"] = "EXPIRING_SOON"
            promo["status_label"] = f"🟠 Por vencer ({delta} día{'s' if delta != 1 else ''})"
        else:
            promo["status"] = "ACTIVE"
            promo["status_label"] = f"🟢 Activa (vence {end_d.strftime('%d/%m/%Y')})"
    except Exception:
        promo["status"] = "UNKNOWN"
        promo["status_label"] = "⚪ Sin fecha válida"

    return promo


def _get_default_october_promotions() -> List[Dict[str, Any]]:
    """Promociones base extraídas del archivo de promociones de Octubre."""
    today = date.today()
    end_of_month = (today.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    eom_str = end_of_month.isoformat()

    base = [
        {
            "id": "promo_esencial",
            "name": "Check Up Esencial",
            "category": "Promo Permanente",
            "validity_type": "permanent",
            "end_date": None,
            "studies": ["Biometría hemática", "Química Sanguínea (30 elementos)", "Examen general de orina"],
            "price_regular": 750.0,
            "price_promo": 549.0,
            "chopo_equivalent": "CHECK UP BÁSICO QUÍMICA DE 45 ELEMENTOS",
            "notes": "Incluye BH, QS 30 y EGO"
        },
        {
            "id": "promo_avanzado",
            "name": "Checkup Avanzado",
            "category": "Promo Permanente",
            "validity_type": "permanent",
            "end_date": None,
            "studies": ["Biometría hemática", "Química Sanguínea (40 elementos)", "Examen general de orina"],
            "price_regular": 1150.0,
            "price_promo": 890.0,
            "chopo_equivalent": "CHECK UP SALUD QUÍMICA DE 45 ELEMENTOS",
            "notes": "Incluye BH, QS 40 y EGO"
        },
        {
            "id": "promo_integral_plus",
            "name": "Checkup Integral Plus",
            "category": "Promo Permanente",
            "validity_type": "permanent",
            "end_date": None,
            "studies": ["Biometría hemática", "Química Sanguínea de 50 elementos c/ HbA1c", "Examen general de orina"],
            "price_regular": 1450.0,
            "price_promo": 998.0,
            "chopo_equivalent": "CHECK UP INTEGRAL Q45",
            "notes": "Incluye BH, QS 50 c/ Hemoglobina Glicosilada y EGO"
        },
        {
            "id": "promo_inicial",
            "name": "Check Up Inicial",
            "category": "Promo Permanente",
            "validity_type": "permanent",
            "end_date": None,
            "studies": ["Biometría hemática", "Química Sanguínea (6 elementos)", "Examen general de orina"],
            "price_regular": 620.0,
            "price_promo": 470.0,
            "chopo_equivalent": "QUÍMICA 6 + BIOMETRÍA + EGO",
            "notes": "Paquete básico para chequeo general"
        },
        {
            "id": "promo_tiroideo_esencial",
            "name": "Check Up Tiroideo Esencial",
            "category": "Promo Cuatrimestral",
            "validity_type": "custom_date",
            "end_date": "2026-12-31",
            "studies": ["Perfil tiroideo completo", "Biometría hemática", "Química Sanguínea (30 elementos)", "Examen general de orina"],
            "price_regular": 1433.0,
            "price_promo": 1050.0,
            "chopo_equivalent": "CHECK UP BÁSICO TIROIDEO QUÍMICA DE 45 ELEMENTOS",
            "notes": "Perfil tiroideo completo + Check Up Esencial"
        },
        {
            "id": "promo_perfil_tiroideo",
            "name": "Perfil Tiroideo Completo",
            "category": "Promo del Mes",
            "validity_type": "custom_date",
            "end_date": eom_str,
            "studies": ["Perfil tiroideo completo"],
            "price_regular": 690.0,
            "price_promo": 590.0,
            "chopo_equivalent": "PERFIL TIROIDEO",
            "notes": "Descuento especial de temporada"
        },
        {
            "id": "promo_perfil_femenino",
            "name": "Perfil Hormonal Femenino",
            "category": "Promo del Mes",
            "validity_type": "custom_date",
            "end_date": eom_str,
            "studies": ["Perfil hormonal femenino"],
            "price_regular": 1090.0,
            "price_promo": 980.0,
            "chopo_equivalent": "PERFIL HORMONAL",
            "notes": "Ginecológico completo"
        },
        {
            "id": "promo_vitamina_d",
            "name": "Vitamina D (25-OH) Total",
            "category": "Promo Especial",
            "validity_type": "permanent",
            "end_date": None,
            "studies": ["Vitamina D (25-OH) total"],
            "price_regular": 690.0,
            "price_promo": 640.0,
            "chopo_equivalent": "25 HIDROXI VITAMINA D TOTAL (CALCIFEROL)",
            "notes": "Precio en paquete o adicional"
        },
    ]
    for p in base:
        evaluate_promo_validity(p)
    return base


# ── 2B. GESTOR DE ESTUDIOS ADICIONALES Y MOTOR DE MEJOR PRECIO ────────────

def load_adicionales() -> List[Dict[str, Any]]:
    """Carga los 33 estudios adicionales con precio especial de paquete."""
    ensure_dirs()
    if ADICIONALES_FILE.exists():
        try:
            with open(ADICIONALES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    # Extraer desde BASE_MATCHES_FILE
    if BASE_MATCHES_FILE.exists():
        try:
            with open(BASE_MATCHES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                adicionales = data.get("adicionales", [])
                if adicionales:
                    save_all_adicionales(adicionales)
                    return adicionales
        except Exception:
            pass
    return []


def save_all_adicionales(adicionales: List[Dict[str, Any]]) -> bool:
    ensure_dirs()
    try:
        with open(ADICIONALES_FILE, "w", encoding="utf-8") as f:
            json.dump(adicionales, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def get_adicionales_lookup() -> Dict[str, Dict[str, Any]]:
    """
    Retorna un diccionario indexado tanto por código como por nombre normalizado
    mapeando al estudio adicional y su price_bundle.
    """
    adicionales = load_adicionales()
    lookup = {}
    for a in adicionales:
        code_k = str(a.get("code", "")).strip()
        name_k = clean_medical_text(str(a.get("name", "")))
        if code_k:
            lookup[code_k] = a
        if name_k:
            lookup[name_k] = a
    return lookup


def get_active_promos_lookup() -> Dict[str, Dict[str, Any]]:
    """
    Retorna un diccionario mapeando nombre de estudio a la promoción activa más económica.
    """
    promos = load_promotions()
    active_promos = {}
    for p in promos:
        status = p.get("status")
        if status in ("ACTIVE", "PERMANENT", "EXPIRING_SOON"):
            price = p.get("price_promo")
            if price is None:
                continue
            studies = p.get("studies", [])
            p_name = p.get("name", "")
            all_targets = list(studies) + [p_name]
            for t in all_targets:
                norm_t = clean_medical_text(t)
                if not norm_t:
                    continue
                if norm_t not in active_promos or price < active_promos[norm_t]["price"]:
                    active_promos[norm_t] = {
                        "promo_id": p.get("id"),
                        "promo_name": p_name,
                        "price": float(price),
                        "category": p.get("category", "")
                    }
    return active_promos


def calculate_best_lcm_price(
    study_code: str,
    study_name: str,
    price_list: float,
    with_checkup: bool = False
) -> Dict[str, Any]:
    """
    Aplica la regla comercial de LCM del Mejor Precio Garantizado:
    - Compara Precio de Lista vs Precio Adicional (si aplica con Check-Up) vs Precio Promoción Activa.
    - Respeta SIEMPRE el precio más bajo para el paciente.
    """
    code_k = str(study_code or "").strip()
    name_norm = clean_medical_text(study_name or "")

    adic_lookup = get_adicionales_lookup()
    promo_lookup = get_active_promos_lookup()

    adic_info = adic_lookup.get(code_k) or adic_lookup.get(name_norm)
    if not adic_info and name_norm:
        for k, v in adic_lookup.items():
            if fuzz.token_sort_ratio(name_norm, k) >= 88:
                adic_info = v
                break

    promo_info = promo_lookup.get(name_norm)
    if not promo_info and name_norm:
        for k, v in promo_lookup.items():
            if fuzz.token_sort_ratio(name_norm, k) >= 88:
                promo_info = v
                break

    price_bundle = float(adic_info["price_bundle"]) if (adic_info and adic_info.get("price_bundle") is not None) else None
    price_promo = float(promo_info["price"]) if (promo_info and promo_info.get("price") is not None) else None

    # Candidatos disponibles
    candidates = [("LISTA", price_list, "Precio regular de lista")]

    if with_checkup and price_bundle is not None:
        candidates.append(("ADICIONAL", price_bundle, f"Precio especial al añadir con Check-Up (${price_bundle:,.2f})"))

    if price_promo is not None:
        p_name = promo_info.get("promo_name", "Promoción")
        candidates.append(("PROMOCION", price_promo, f"Precio en promoción '{p_name}' (${price_promo:,.2f})"))

    # Encontrar el menor precio
    sorted_candidates = sorted(candidates, key=lambda x: x[1])
    best_rule, best_price, best_desc = sorted_candidates[0]

    # Explicación
    if best_rule == "PROMOCION":
        if with_checkup and price_bundle is not None and price_promo < price_bundle:
            diff_bundle = price_bundle - price_promo
            explanation = f"🎉 **Aplica Precio Promoción (${price_promo:,.2f})**: Es ${diff_bundle:,.2f} más barato que el precio adicional de paquete (${price_bundle:,.2f})."
        else:
            diff_list = price_list - price_promo
            explanation = f"🎉 **Aplica Precio Promoción (${price_promo:,.2f})**: Ahorro de ${diff_list:,.2f} frente a lista regular (${price_list:,.2f})."
    elif best_rule == "ADICIONAL":
        if price_promo is not None and price_bundle < price_promo:
            diff_promo = price_promo - price_bundle
            explanation = f"💡 **Aplica Precio Adicional (${price_bundle:,.2f})**: Al incluirse en Check-Up, es ${diff_promo:,.2f} más barato que la promo individual (${price_promo:,.2f})."
        else:
            diff_list = price_list - price_bundle
            explanation = f"💡 **Aplica Precio Adicional (${price_bundle:,.2f})**: Descuento especial de Check-Up (Ahorro de ${diff_list:,.2f} frente a lista)."
    else:
        explanation = f"📋 **Precio de Lista Regular (${price_list:,.2f})**"
        if not with_checkup and price_bundle is not None:
            explanation += f" *(Disponible a ${price_bundle:,.2f} si el paciente lo añade a un Check-Up)*."

    savings_mxn = round(price_list - best_price, 2)
    savings_pct = round((savings_mxn / price_list) * 100, 1) if price_list > 0 else 0.0

    return {
        "price_list": price_list,
        "price_bundle": price_bundle,
        "price_promo": price_promo,
        "best_price": best_price,
        "rule": best_rule,
        "explanation": explanation,
        "has_bundle_price": price_bundle is not None,
        "has_promo_price": price_promo is not None,
        "savings_mxn": savings_mxn,
        "savings_pct": savings_pct
    }



# ── 3. DETECTOR INTELIGENTE DE COLUMNAS PARA ARCHIVOS SUBIDOS ─────────────────

def detect_columns(df: pd.DataFrame) -> Dict[str, Optional[str]]:
    """
    Analiza los nombres y tipos de las columnas de un DataFrame subido
    y detecta automáticamente cuáles corresponden a Código, Nombre de Estudio y Precio.
    """
    cols = list(df.columns)
    detected = {
        "code_col": None,
        "name_col": None,
        "price_col": None
    }

    # 1. Buscar código / clave
    code_patterns = [r'clave', r'codigo', r'cve', r'code', r'sku', r'\bid\b', r'\bnum\b']
    for c in cols:
        c_str = str(c).lower().strip().replace(" ", "_")
        if any(re.search(p, c_str) for p in code_patterns):
            detected["code_col"] = c
            break

    # 2. Buscar precio
    price_patterns = [r'precio', r'costo', r'importe', r'publico', r'iva', r'price', r'tarifa', r'monto', r'total']
    for c in cols:
        c_str = str(c).lower().strip().replace(" ", "_")
        if any(re.search(p, c_str) for p in price_patterns):
            detected["price_col"] = c
            break

    # 3. Buscar nombre de estudio (evitando columnas ya detectadas como código o precio)
    name_patterns = [r'nombre', r'estudio', r'descripcion', r'prueba', r'analisis', r'name', r'study', r'concepto']
    for c in cols:
        if c == detected["code_col"] or c == detected["price_col"]:
            continue
        c_str = str(c).lower().strip().replace(" ", "_")
        # Si tiene clave o codigo y ya detectamos clave, saltarla
        if "clave" in c_str or "codigo" in c_str:
            continue
        if any(re.search(p, c_str) for p in name_patterns):
            detected["name_col"] = c
            break

    # Fallback si no hubo coincidencia por regex:
    # Seleccionar columnas basadas en tipos de datos y contenidos
    if not detected["name_col"]:
        for c in cols:
            if c != detected["code_col"] and c != detected["price_col"]:
                if df[c].dtype == object and df[c].astype(str).str.len().mean() > 10:
                    detected["name_col"] = c
                    break

    if not detected["price_col"]:
        for c in cols:
            if c != detected["code_col"] and c != detected["name_col"]:
                # Comprobar si tiene números o formato moneda
                sample = df[c].dropna().astype(str).head(10)
                if any(re.search(r'\d+(\.\d+)?', s) for s in sample):
                    detected["price_col"] = c
                    break

    return detected


# ── 4. CONSOLIDADOR DE DATOS CON OVERRIDES ACTIVOS ────────────────────────────

def get_consolidated_matches() -> Dict[str, Any]:
    """
    Retorna el dataset completo de matching aplicando en tiempo real
    cualquier modificación manual de precio guardada en OVERRIDES_FILE.
    """
    if not BASE_MATCHES_FILE.exists():
        from scripts.build_lcm_matching import build_matching_database
        build_matching_database()

    with open(BASE_MATCHES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    overrides = load_price_overrides()
    if not overrides:
        return data

    matches = data.get("matches", [])
    updated_matches = []
    
    for m in matches:
        m_copy = dict(m)
        code_key = str(m.get("lcm_code", "")).strip()
        name_key = str(m.get("lcm_name", "")).strip()

        # Checar si hay override por clave o nombre
        override_data = overrides.get(code_key) or overrides.get(name_key)
        if override_data:
            new_p = override_data["price"]
            m_copy["lcm_price_original"] = m.get("lcm_price")
            m_copy["lcm_price"] = new_p
            m_copy["is_manually_edited"] = True
            m_copy["manual_edit_notes"] = override_data.get("notes", "")
            m_copy["manual_edit_date"] = override_data.get("updated_at", "")

            # Recalcular diferencias frente a Chopo
            c_web = m_copy.get("chopo_price_web")
            if c_web is not None:
                diff_m = round(new_p - c_web, 2)
                diff_pct = round((diff_m / c_web) * 100, 1) if c_web > 0 else 0.0
                m_copy["diff_mxn"] = diff_m
                m_copy["diff_pct"] = diff_pct
            else:
                m_copy["diff_mxn"] = None
                m_copy["diff_pct"] = None
        else:
            m_copy["is_manually_edited"] = False

        updated_matches.append(m_copy)

    data["matches"] = updated_matches

    # Recalcular métricas consolidadas
    valid_diffs = [m for m in updated_matches if m.get("diff_mxn") is not None]
    lcm_cheaper = sum(1 for m in valid_diffs if m["diff_mxn"] < 0)
    chopo_cheaper = sum(1 for m in valid_diffs if m["diff_mxn"] > 0)
    equal_p = sum(1 for m in valid_diffs if m["diff_mxn"] == 0)

    if "metadata" in data and "price_analysis" in data["metadata"]:
        data["metadata"]["price_analysis"]["lcm_cheaper_count"] = lcm_cheaper
        data["metadata"]["price_analysis"]["lcm_cheaper_pct"] = round(lcm_cheaper / len(valid_diffs) * 100, 1) if valid_diffs else 0
        data["metadata"]["price_analysis"]["chopo_cheaper_count"] = chopo_cheaper
        data["metadata"]["price_analysis"]["chopo_cheaper_pct"] = round(chopo_cheaper / len(valid_diffs) * 100, 1) if valid_diffs else 0
        data["metadata"]["price_analysis"]["equal_price_count"] = equal_p

    return data


# ── 5. PROCESADOR DE CATÁLOGO SUBIDO (CSV / EXCEL) ───────────────────────────

SYNONYMS = [
    (r'\bBIOMETRIA\s+HEMATICA\b', 'CITOMETRIA HEMATICA'),
    (r'\bB\.?H\.?\b', 'CITOMETRIA HEMATICA'),
    (r'\bEXAMEN\s+GENERAL\s+DE\s+ORINA\b', 'EXAMEN GENERAL DE ORINA'),
    (r'\bE\.?G\.?O\.?\b', 'EXAMEN GENERAL DE ORINA'),
    (r'\bQUIMICA\s+CLINICA\b', 'QUIMICA SANGUINEA'),
    (r'\bQUIMICA\s+INTEGRAL\b', 'QUIMICA SANGUINEA'),
    (r'\bSUPER\s+QUIMICA\b', 'QUIMICA SANGUINEA'),
    (r'\bQUIMICA\s+DE\s+(\d+)\s+ELEMENTOS\b', r'QUIMICA SANGUINEA \1 ELEMENTOS'),
    (r'\bQUIMICA\s+(\d+)\b', r'QUIMICA SANGUINEA \1 ELEMENTOS'),
    (r'\bQS\s*(\d+)\b', r'QUIMICA SANGUINEA \1 ELEMENTOS'),
    (r'\bQS\b', 'QUIMICA SANGUINEA'),
    (r'\bHEMOGLOBINA\s+GLICOSILADA\b', 'HEMOGLOBINA GLICOSILADA HBA1C'),
    (r'\bHEMOGLOBINA\s+GLICADA\b', 'HEMOGLOBINA GLICOSILADA HBA1C'),
    (r'\bHBA1C\b', 'HEMOGLOBINA GLICOSILADA HBA1C'),
    (r'\bANTIGENO\s+PROSTATICO\s+ESPECIFICO\b', 'ANTIGENO PROSTATICO PSA'),
    (r'\bANTIGENO\s+PROSTATICO\b', 'ANTIGENO PROSTATICO PSA'),
    (r'\bPSA\s+TOTAL\b', 'ANTIGENO PROSTATICO PSA TOTAL'),
    (r'\bPERFIL\s+TIROIDEO\s+COMPLETO\b', 'PERFIL TIROIDEO'),
    (r'\bPERFIL\s+DE\s+LIPIDOS\b', 'PERFIL LIPIDICO'),
    (r'\bPRUEBAS\s+DE\s+FUNCION\s+HEPATICA\b', 'PERFIL HEPATICO'),
    (r'\bVITAMINA\s+D\s*\(?25[\-\s]?OH\)?\s*(?:TOTAL)?\b', 'VITAMINA D 25 HIDROXI TOTAL'),
    (r'\bRAYOS\s+X\b', 'RADIOGRAFIA RX'),
    (r'\bRX\b', 'RADIOGRAFIA RX'),
    (r'\bULTRASONIDO\b', 'ULTRASONIDO US'),
    (r'\bELECTROCARDIOGRAMA\b', 'ELECTROCARDIOGRAMA ECG'),
]

SPECIMEN_PATTERNS = [
    r'\bEN\s+SUERO\b', r'\bEN\s+SANGRE\b', r'\bEN\s+PLASMA\b', r'\bEN\s+ORINA\b',
    r'\bEN\s+LCR\b', r'\bAL\s+AZAR\b', r'\(Q\)', r'\(IFI\)', r'\(ELISA\)'
]


def strip_accents(s: str) -> str:
    if not s:
        return ""
    return ''.join(c for c in unicodedata.normalize('NFD', str(s)) if unicodedata.category(c) != 'Mn').upper()


def clean_medical_text(text: str, remove_specimen: bool = False) -> str:
    t = strip_accents(text)
    t = re.sub(r'[\(\)\[\]\,\.\-\/\:\;\*\+\t\r\n]', ' ', t)
    t = ' '.join(t.split())
    for pattern, repl in SYNONYMS:
        t = re.sub(pattern, repl, t)
    if remove_specimen:
        for p in SPECIMEN_PATTERNS:
            t = re.sub(p, ' ', t)
    return ' '.join(t.split())


def extract_qs_elements(text: str) -> Optional[int]:
    m = re.search(r'QUIMICA\s+SANGUINEA\s+(\d+)\s+ELEMENTOS', text)
    if m:
        return int(m.group(1))
    m2 = re.search(r'(\d+)\s*ELEMENTOS', text)
    if m2:
        return int(m2.group(1))
    return None


def process_uploaded_catalog(df: pd.DataFrame, code_col: Optional[str], name_col: str, price_col: str) -> Dict[str, Any]:
    """
    Procesa un catálogo subido en CSV/Excel, ejecuta el matching contra Chopo Mérida Altabrisa
    y actualiza la base de datos de comparación.
    """
    ensure_dirs()

    # 1. Cargar catálogo de Chopo desde SQLite
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute("SELECT study_name, price, price_original, url, sku FROM latest_prices")
    chopo_raw = cur.fetchall()
    conn.close()

    chopo_catalog = []
    for row in chopo_raw:
        s_name = row[0]
        norm = clean_medical_text(s_name, remove_specimen=False)
        core = clean_medical_text(s_name, remove_specimen=True)
        elem = extract_qs_elements(norm)
        chopo_catalog.append({
            'name': s_name,
            'norm': norm,
            'core': core,
            'elements': elem,
            'price_web': row[1],
            'price_list': row[2],
            'url': row[3],
            'sku': row[4]
        })

    # 2. Parsear el DataFrame subido
    lcm_studies = []
    for idx, row in df.iterrows():
        name_val = row.get(name_col)
        if not name_val or pd.isna(name_val):
            continue
        name_str = ' '.join(str(name_val).split())
        if not name_str:
            continue

        code_val = row.get(code_col) if code_col else ""
        code_str = str(code_val).strip() if pd.notna(code_val) else f"ROW_{idx+1}"

        price_raw = row.get(price_col)
        p_val = None
        if price_raw is not None and pd.notna(price_raw):
            p_clean = re.sub(r'[\s\$]', '', str(price_raw)).replace(',', '')
            try:
                p_val = float(p_clean)
            except ValueError:
                pass

        if p_val is None:
            continue

        norm = clean_medical_text(name_str, remove_specimen=False)
        core = clean_medical_text(name_str, remove_specimen=True)
        elem = extract_qs_elements(norm)

        lcm_studies.append({
            'code': code_str,
            'name': name_str,
            'norm': norm,
            'core': core,
            'elements': elem,
            'price': p_val
        })

    # 3. Matching Engine
    matches = []
    for lcm in lcm_studies:
        lcm_core = lcm['core']
        lcm_elem = lcm['elements']

        exact_c = None
        for c in chopo_catalog:
            if c['core'] == lcm_core:
                if lcm_elem is not None and c['elements'] is not None and lcm_elem != c['elements']:
                    continue
                exact_c = c
                break

        if exact_c:
            p_web = exact_c['price_web']
            p_list = exact_c['price_list']
            diff_web = round(lcm['price'] - p_web, 2) if p_web is not None else None
            diff_pct = round((diff_web / p_web) * 100, 1) if (diff_web is not None and p_web and p_web > 0) else None
            matches.append({
                'lcm_code': lcm['code'],
                'lcm_name': lcm['name'],
                'lcm_price': lcm['price'],
                'chopo_name': exact_c['name'],
                'chopo_price_web': p_web,
                'chopo_price_list': p_list,
                'chopo_url': exact_c['url'],
                'chopo_sku': exact_c['sku'],
                'match_type': 'EXACT',
                'confidence': 100.0,
                'diff_mxn': diff_web,
                'diff_pct': diff_pct
            })
            continue

        candidates = chopo_catalog
        if lcm_elem is not None:
            cand_filtered = [c for c in chopo_catalog if c['elements'] == lcm_elem]
            if cand_filtered:
                candidates = cand_filtered

        best_score = 0
        best_cand = None
        for c in candidates:
            if lcm_elem is not None and c['elements'] is not None and lcm_elem != c['elements']:
                continue
            s1 = fuzz.token_sort_ratio(lcm_core, c['core'])
            s2 = fuzz.token_set_ratio(lcm_core, c['core'])
            len_ratio = min(len(lcm_core), len(c['core'])) / max(len(lcm_core), len(c['core'])) if max(len(lcm_core), len(c['core'])) > 0 else 1.0
            score = (s1 * 0.55) + (s2 * 0.35) + (len_ratio * 10)
            if score > best_score:
                best_score = score
                best_cand = c

        if best_cand and best_score >= 70:
            m_type = 'HIGH' if best_score >= 85 else 'MEDIUM'
            p_web = best_cand['price_web']
            p_list = best_cand['price_list']
            diff_web = round(lcm['price'] - p_web, 2) if p_web is not None else None
            diff_pct = round((diff_web / p_web) * 100, 1) if (diff_web is not None and p_web and p_web > 0) else None
            matches.append({
                'lcm_code': lcm['code'],
                'lcm_name': lcm['name'],
                'lcm_price': lcm['price'],
                'chopo_name': best_cand['name'],
                'chopo_price_web': p_web,
                'chopo_price_list': p_list,
                'chopo_url': best_cand['url'],
                'chopo_sku': best_cand['sku'],
                'match_type': m_type,
                'confidence': round(best_score, 1),
                'diff_mxn': diff_web,
                'diff_pct': diff_pct
            })
        else:
            matches.append({
                'lcm_code': lcm['code'],
                'lcm_name': lcm['name'],
                'lcm_price': lcm['price'],
                'chopo_name': None,
                'chopo_price_web': None,
                'chopo_price_list': None,
                'chopo_url': None,
                'chopo_sku': None,
                'match_type': 'NO_MATCH',
                'confidence': 0.0,
                'diff_mxn': None,
                'diff_pct': None
            })

    # Cargar paquetes existentes o por defecto para preservarlos
    existing_packages = []
    existing_adicionales = []
    if BASE_MATCHES_FILE.exists():
        try:
            with open(BASE_MATCHES_FILE, "r", encoding="utf-8") as f:
                prev_data = json.load(f)
                existing_packages = prev_data.get("packages", [])
                existing_adicionales = prev_data.get("adicionales", [])
        except Exception:
            pass

    # Estadísticas
    total_parsed = len(matches)
    exact_count = sum(1 for m in matches if m['match_type'] == 'EXACT')
    high_count = sum(1 for m in matches if m['match_type'] == 'HIGH')
    med_count = sum(1 for m in matches if m['match_type'] == 'MEDIUM')
    no_count = sum(1 for m in matches if m['match_type'] == 'NO_MATCH')
    actionable = exact_count + high_count + med_count
    valid_diffs = [m for m in matches if m.get('diff_mxn') is not None]
    lcm_cheaper = sum(1 for m in valid_diffs if m['diff_mxn'] < 0)
    chopo_cheaper = sum(1 for m in valid_diffs if m['diff_mxn'] > 0)

    output_payload = {
        'metadata': {
            'generated_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'lcm_source': 'Subida de Catálogo Usuario (CSV/Excel)',
            'chopo_source_db': 'db/chopo_prices.db (Mérida Altabrisa)',
            'total_lcm_studies': total_parsed,
            'exact_matches': exact_count,
            'high_confidence': high_count,
            'medium_confidence': med_count,
            'no_match': no_count,
            'actionable_matched_count': actionable,
            'actionable_matched_pct': round((actionable / total_parsed) * 100, 1) if total_parsed else 0.0,
            'price_analysis': {
                'total_compared': len(valid_diffs),
                'lcm_cheaper_count': lcm_cheaper,
                'lcm_cheaper_pct': round(lcm_cheaper / len(valid_diffs) * 100, 1) if valid_diffs else 0.0,
                'chopo_cheaper_count': chopo_cheaper,
                'chopo_cheaper_pct': round(chopo_cheaper / len(valid_diffs) * 100, 1) if valid_diffs else 0.0,
                'equal_price_count': sum(1 for m in valid_diffs if m['diff_mxn'] == 0),
            }
        },
        'matches': matches,
        'packages': existing_packages,
        'adicionales': existing_adicionales
    }

    with open(str(BASE_MATCHES_FILE), "w", encoding="utf-8") as f:
        json.dump(output_payload, f, ensure_ascii=False, indent=2)

    return output_payload['metadata']

