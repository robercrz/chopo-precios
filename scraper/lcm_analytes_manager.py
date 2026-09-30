# scraper/lcm_analytes_manager.py
r"""
Gestor clínico inteligente de analitos, perfiles y sugeridor de Check-Ups para LCM.
Extrae y cataloga la información analítica de Directorio catalogo maquila 2024.xlsx
y provee lógica de detección de analitos duplicados, sugerencia de paquetes y cotización inteligente.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CATALOG_JSON = PROJECT_ROOT / "config" / "lcm_analitos_catalog.json"
ADICIONALES_JSON = PROJECT_ROOT / "config" / "lcm_adicionales.json"
PROMOTIONS_JSON = PROJECT_ROOT / "config" / "lcm_promotions.json"
EXCEL_PATH = Path(r"C:\Users\pcone\Downloads\Directorio catalogo maquila 2024.xlsx")


def load_analytes_catalog() -> Dict[str, Dict[str, Any]]:
    """Carga el catálogo de analitos y perfiles desde JSON (o genera si existe Excel)."""
    if CATALOG_JSON.exists():
        try:
            with open(CATALOG_JSON, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    # Si no existe el JSON pero existe el Excel local, generarlo
    if EXCEL_PATH.exists():
        try:
            from scripts.parse_lcm_analytes import parse_excel
            parse_excel()
            if CATALOG_JSON.exists():
                with open(CATALOG_JSON, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass

    return {}


def normalize_analyte_name(text: str) -> str:
    """Normaliza nombres de analitos para comparaciones clínicas."""
    t = str(text or "").upper().strip()
    t = re.sub(r"[ÁÀÄÂ]", "A", t)
    t = re.sub(r"[ÉÈËÊ]", "E", t)
    t = re.sub(r"[ÍÌÏÎ]", "I", t)
    t = re.sub(r"[ÓÒÖÔ]", "O", t)
    t = re.sub(r"[ÚÙÜÛ]", "U", t)
    t = re.sub(r"[^A-Z0-9/%\s]", "", t)
    t = re.sub(r"\s+", " ", t)
    return t


def get_analytes_for_study(study_key: str, catalog: Optional[Dict] = None) -> Dict[str, Any]:
    """Obtiene los analitos y detalles clínicos de un estudio o perfil."""
    if catalog is None:
        catalog = load_analytes_catalog()

    # Búsqueda directa por código
    if study_key in catalog:
        return catalog[study_key]

    # Búsqueda por coincidencia de nombre
    norm_search = normalize_analyte_name(study_key)
    for k, item in catalog.items():
        if normalize_analyte_name(item.get("name", "")) == norm_search:
            return item
        if norm_search in normalize_analyte_name(item.get("name", "")):
            return item

    return {
        "code": "",
        "name": study_key,
        "analytes": [],
        "analytes_count": 0,
        "sample_req": "Ayuno de 8 a 12 horas",
        "turnaround": "Mismo Día (MD)",
        "sample_type": "Suero"
    }


def find_overlapping_analytes(selected_studies: List[str], catalog: Optional[Dict] = None) -> List[Dict[str, Any]]:
    """
    Detecta analitos duplicados o solapados entre los estudios seleccionados.
    Ej: Si se selecciona Química 27 y Perfil de Lípidos, avisa que Colesterol y Triglicéridos
    ya están incluidos en la Química.
    """
    if catalog is None:
        catalog = load_analytes_catalog()

    study_data = []
    for s_name in selected_studies:
        info = get_analytes_for_study(s_name, catalog)
        raw_analytes = info.get("analytes", [])
        norm_map = {normalize_analyte_name(a): a for a in raw_analytes}
        study_data.append({
            "study_name": info.get("name") or s_name,
            "raw_analytes": raw_analytes,
            "norm_set": set(norm_map.keys()),
            "norm_map": norm_map
        })

    overlaps = []
    n = len(study_data)
    for i in range(n):
        for j in range(i + 1, n):
            s1 = study_data[i]
            s2 = study_data[j]
            common_keys = s1["norm_set"].intersection(s2["norm_set"])
            if common_keys:
                common_labels = [s1["norm_map"][k] for k in common_keys]
                overlaps.append({
                    "study_1": s1["study_name"],
                    "study_2": s2["study_name"],
                    "overlapping_count": len(common_keys),
                    "overlapping_analytes": common_labels,
                    "is_full_coverage": (s1["norm_set"].issubset(s2["norm_set"]) or s2["norm_set"].issubset(s1["norm_set"])),
                    "covered_study": s1["study_name"] if s1["norm_set"].issubset(s2["norm_set"]) else (s2["study_name"] if s2["norm_set"].issubset(s1["norm_set"]) else None)
                })

    return overlaps


def get_lcm_checkups() -> List[Dict[str, Any]]:
    """
    Retorna el catálogo consolidado de Check-Ups oficiales de LCM
    con sus tarifas empaquetadas y estudios incluidos.
    """
    checkups = [
        {
            "id": "CHK_TIROIDEO",
            "name": "Check Up Tiroideo Esencial",
            "period": "Cuatrimestre Sep - Dic 2026",
            "price_promo": 1050.0,
            "price_regular": 1433.0,
            "savings": 383.0,
            "studies": [
                "Química Sanguínea (30 elementos)",
                "Perfil Tiroideo Completo",
                "Biometría Hemática",
                "Examen General de Orina (EGO)"
            ],
            "keywords": ["TIROID", "QUIMICA", "TSH", "T3", "T4"],
            "description": "El paquete más completo para control metabólico y función tiroidea. Incluye bioquímica de 30 elementos y panel tiroideo completo.",
            "sample_req": "Ayuno de 10 a 12 horas. Muestra de orina reciente en frasco estéril."
        },
        {
            "id": "CHK_ESENCIAL_VIT_D",
            "name": "Check Up Esencial + Vitamina D",
            "period": "Cuatrimestre Sep - Dic 2026",
            "price_promo": 1100.0,
            "price_regular": 1433.0,
            "savings": 333.0,
            "studies": [
                "Química Sanguínea (30 elementos)",
                "Vitamina D (25-OH) Total",
                "Biometría Hemática",
                "Examen General de Orina (EGO)"
            ],
            "keywords": ["VITAMINA D", "QUIMICA", "CALCIFEROL", "25-OH"],
            "description": "Ideal para chequeo integral de inmunidad, fijación de calcio y salud ósea con tarifa preferencial en Vitamina D.",
            "sample_req": "Ayuno de 10 a 12 horas. Primera orina de la mañana."
        },
        {
            "id": "CHK_ESENCIAL",
            "name": "Check Up Esencial (30 Elementos)",
            "period": "Permanente",
            "price_promo": 549.0,
            "price_regular": 750.0,
            "savings": 201.0,
            "studies": [
                "Biometría Hemática",
                "Química Sanguínea (30 elementos)",
                "Examen General de Orina (EGO)"
            ],
            "keywords": ["QUIMICA", "BIOMETRIA", "EGO", "ORINA", "GLUCOSA", "UREA"],
            "description": "Check-up preventivo de rutina más solicitado. Evalúa sistema hematológico, función renal, hepática, lipídica y metabólica general.",
            "sample_req": "Ayuno de 10 a 12 horas. Orina matutina en frasco estéril."
        },
        {
            "id": "CHK_AVANZADO",
            "name": "Check Up Avanzado (40/45 Elementos)",
            "period": "Permanente",
            "price_promo": 890.0,
            "price_regular": 1150.0,
            "savings": 260.0,
            "studies": [
                "Biometría Hemática",
                "Química Sanguínea Avanzada (45 elementos)",
                "Examen General de Orina (EGO)"
            ],
            "keywords": ["QUIMICA 45", "QUIMICA 40", "AVANZADO", "AMILASA", "ELECTROLITOS"],
            "description": "Chequeo extendido que añade electrolitos séricos completos, enzimas pancreáticas y marcadores de hierro y proteínas.",
            "sample_req": "Ayuno de 10 a 12 horas. Muestra de orina en frasco estéril."
        },
        {
            "id": "CHK_INTEGRAL_PLUS",
            "name": "Check Up Integral Plus (50 Elementos c/ HbA1c)",
            "period": "Permanente",
            "price_promo": 998.0,
            "price_regular": 1450.0,
            "savings": 452.0,
            "studies": [
                "Biometría Hemática",
                "Química Sanguínea de 50 elementos c/ HbA1c y CPK",
                "Examen General de Orina (EGO)"
            ],
            "keywords": ["50 ELEMENTOS", "HBA1C", "CPK", "INTEGRAL", "DIABETES"],
            "description": "El chequeo bioquímico más exhaustivo: incluye Química de 50 elementos, Hemoglobina Glicosilada, enzimas cardíacas (CPK) e inmunoglobulinas.",
            "sample_req": "Ayuno de 10 a 12 horas. Orina matutina estéril."
        },
        {
            "id": "CHK_INICIAL",
            "name": "Check Up Inicial Básico (6 Elementos)",
            "period": "Permanente",
            "price_promo": 470.0,
            "price_regular": 620.0,
            "savings": 150.0,
            "studies": [
                "Biometría Hemática",
                "Química Sanguínea (6 elementos)",
                "Examen General de Orina (EGO)"
            ],
            "keywords": ["INICIAL", "QUIMICA 6", "BASICO", "6 ELEMENTOS"],
            "description": "Chequeo preventivo ágil y económico. Ideal para constancias de salud, ingresos escolares y chequeo de primer contacto.",
            "sample_req": "Ayuno de 8 a 10 horas. Muestra de orina matutina."
        },
        {
            "id": "CHK_HOMBRE",
            "name": "Check Up Masculino / Próstata",
            "period": "Permanente / Campaña",
            "price_promo": 955.0,
            "price_regular": 1390.0,
            "savings": 435.0,
            "studies": [
                "Biometría Hemática",
                "Química Sanguínea (30 elementos)",
                "Antígeno Prostático Específico (PSA Total)",
                "Hemoglobina Glicosilada (HbA1c)",
                "Examen General de Orina (EGO)"
            ],
            "keywords": ["PROSTATA", "PSA", "HOMBRE", "MASCULINO"],
            "description": "Enfocado en la salud integral del hombre: función prostática, riesgo cardiovascular y despistaje diabético.",
            "sample_req": "Ayuno de 10 a 12 horas. 48 hrs sin actividad sexual previa ni ciclismo."
        },
        {
            "id": "CHK_MUJER",
            "name": "Check Up Salud Mujer",
            "period": "Permanente / Campaña",
            "price_promo": 1499.0,
            "price_regular": 2100.0,
            "savings": 601.0,
            "studies": [
                "Biometría Hemática",
                "Química Sanguínea (30 elementos)",
                "Examen General de Orina (EGO)",
                "Papanicolaou (Citología Cervicovaginal)",
                "Ultrasonido Pélvico o Mamario"
            ],
            "keywords": ["MUJER", "FEMENINO", "PAPANICOLAOU", "ULTRASONIDO", "MAMA"],
            "description": "Chequeo preventivo ginecológico integral para la mujer con ultrasonido y citología incluidos.",
            "sample_req": "Ayuno de 8 a 10 horas. Presentarse sin sangrado menstrual y sin duchas vaginales 48h antes."
        }
    ]
    return checkups


def suggest_checkups_for_studies(selected_studies: List[str]) -> List[Dict[str, Any]]:
    """
    Analiza la lista de estudios que el usuario quiere cotizar y genera
    recomendaciones inteligentes de Check-Ups existentes en LCM.
    """
    if not selected_studies:
        return []

    checkups = get_lcm_checkups()
    suggestions = []

    # Normalizar nombres seleccionados
    norm_sel = [normalize_analyte_name(s) for s in selected_studies]
    has_quimica = any("QUIMICA" in s for s in norm_sel)
    has_tiroideo = any("TIROID" in s for s in norm_sel)
    has_vitamina_d = any("VITAMINA D" in s or "CALCIFEROL" in s or "25-OH" in s for s in norm_sel)
    has_bh = any("BIOMETR" in s or "HEMATIC" in s for s in norm_sel)
    has_ego = any("ORINA" in s or "EGO" in s for s in norm_sel)
    has_psa = any("PROSTAT" in s or "PSA" in s for s in norm_sel)
    has_hba1c = any("GLICOSILADA" in s or "HBA1C" in s for s in norm_sel)
    has_lipid = any("LIPID" in s or "COLESTEROL" in s or "TRIGLICERID" in s for s in norm_sel)
    has_hormonal = any("HORMONAL" in s for s in norm_sel)

    for chk in checkups:
        chk_id = chk["id"]
        score = 0
        reasons = []

        if chk_id == "CHK_TIROIDEO":
            if has_quimica and has_tiroideo:
                score = 95
                reasons.append("Estás cotizando Química Sanguínea y Perfil Tiroideo: el **Check Up Tiroideo Esencial** los agrupa e incluye Biometría y EGO.")
            elif has_tiroideo:
                score = 70
                reasons.append("Cotizas Perfil Tiroideo: por solo una pequeña diferencia puedes obtener el Check-Up completo con Química de 30 elementos.")

        elif chk_id == "CHK_ESENCIAL_VIT_D":
            if has_quimica and has_vitamina_d:
                score = 95
                reasons.append("Cotizas Química Sanguínea y Vitamina D: este paquete integra ambos estudios con ahorro significativo frente a lista individual.")
            elif has_vitamina_d:
                score = 65
                reasons.append("La Vitamina D está incluida a precio preferencial dentro de este Check-Up cuatrimestral.")

        elif chk_id == "CHK_INTEGRAL_PLUS":
            if (has_quimica and has_hba1c) or any("45" in s or "50" in s for s in norm_sel):
                score = 90
                reasons.append("Para estudios metabólicos avanzados, el **Check Up Integral Plus (50 elementos)** incluye HbA1c y enzimas cardíacas por solo $998.")

        elif chk_id == "CHK_HOMBRE":
            if has_psa and (has_quimica or has_bh):
                score = 95
                reasons.append("Detectamos Antígeno Prostático + Química: el **Check Up Masculino** cubre PSA, HbA1c, Química 30, BH y EGO.")

        elif chk_id == "CHK_ESENCIAL":
            if has_quimica and (has_bh or has_ego):
                score = 85
                reasons.append("Cotizas Química + BH/EGO: el **Check Up Esencial ($549)** te da Química de 30 elementos + BH + EGO al mejor precio.")
            elif has_quimica:
                score = 75
                reasons.append("Si cotizas Química individual, te conviene ofrecer el **Check Up Esencial ($549)** que ya añade BH y EGO.")

        elif chk_id == "CHK_INICIAL":
            if any("3 ELEMENTOS" in s or "4 ELEMENTOS" in s or "6 ELEMENTOS" in s for s in norm_sel):
                score = 80
                reasons.append("Para perfil básico, el **Check Up Inicial ($470)** incluye Química 6 + BH + EGO.")

        if score >= 60:
            suggestions.append({
                "checkup": chk,
                "score": score,
                "reason": " ".join(reasons)
            })

    # Ordenar sugerencias por puntaje
    suggestions.sort(key=lambda x: x["score"], reverse=True)
    return suggestions


def get_lcm_adicionales() -> List[Dict[str, Any]]:
    """
    Retorna los 33 estudios adicionales con tarifa preferencial en Check-Up.
    """
    if ADICIONALES_JSON.exists():
        try:
            with open(ADICIONALES_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data
        except Exception:
            pass

    # Fallback con los estudios adicionales más comunes
    return [
        {"code": "1414", "name": "Vitamina D (25-OH) total", "price_2025": 690.0, "price_bundle": 640.0, "savings": 50.0},
        {"code": "756", "name": "Hemoglobina glicosilada (HbA1c)", "price_2025": 290.0, "price_bundle": 195.0, "savings": 95.0},
        {"code": "1592", "name": "Rayos X tórax PA", "price_2025": 690.0, "price_bundle": 400.0, "savings": 290.0},
        {"code": "1344", "name": "Ultrasonido abdomino-pélvico", "price_2025": 1628.0, "price_bundle": 990.0, "savings": 638.0},
        {"code": "1374", "name": "Ultrasonido pélvico endovaginal", "price_2025": 1190.0, "price_bundle": 830.0, "savings": 360.0},
        {"code": "1352", "name": "Ultrasonido de mama", "price_2025": 1021.0, "price_bundle": 740.0, "savings": 281.0},
        {"code": "1362", "name": "Ultrasonido tiroides", "price_2025": 1021.0, "price_bundle": 740.0, "savings": 281.0},
        {"code": "1347", "name": "Ultrasonido carotídeo (Doppler)", "price_2025": 3003.0, "price_bundle": 1390.0, "savings": 1613.0},
        {"code": "702", "name": "Antígeno prostático específico (PSA)", "price_2025": 420.0, "price_bundle": 290.0, "savings": 130.0},
        {"code": "1407", "name": "Perfil tiroideo 2 (TSH, T3, T4)", "price_2025": 580.0, "price_bundle": 420.0, "savings": 160.0},
        {"code": "1412", "name": "Ácido fólico", "price_2025": 490.0, "price_bundle": 350.0, "savings": 140.0},
        {"code": "1413", "name": "Vitamina B12", "price_2025": 490.0, "price_bundle": 350.0, "savings": 140.0}
    ]


def is_study_covered_by_checkup(study_name: str, checkup: Dict[str, Any]) -> bool:
    """
    Determina si un estudio clínico individual ya está incluido o sustituido
    clínicamente dentro de un Check-Up empaquetado.
    """
    norm_s = normalize_analyte_name(study_name)
    chk_studies = [normalize_analyte_name(s) for s in checkup.get("studies", [])]

    # 1. Químicas sanguíneas (3, 4, 6, 12, 18, 24, 27, 30, 36, 45, 50 elementos)
    if "QUIMICA" in norm_s or "ELEMENTOS" in norm_s:
        if any("QUIMICA" in cs for cs in chk_studies):
            return True

    # 2. Perfil tiroideo (TSH, T3, T4, Tiroideo 2, 3, Completo)
    if "TIROID" in norm_s or any(k in norm_s for k in ["TSH", "T3", "T4"]):
        if any("TIROID" in cs for cs in chk_studies):
            return True

    # 3. Biometría hemática
    if "BIOMETR" in norm_s or "HEMATIC" in norm_s:
        if any("BIOMETR" in cs or "HEMATIC" in cs for cs in chk_studies):
            return True

    # 4. Examen General de Orina / EGO
    if "ORINA" in norm_s or "EGO" in norm_s:
        if any("ORINA" in cs or "EGO" in cs for cs in chk_studies):
            return True

    # 5. Vitamina D
    if "VITAMINA D" in norm_s or "CALCIFEROL" in norm_s or "25-OH" in norm_s:
        if any("VITAMINA D" in cs or "CALCIFEROL" in cs for cs in chk_studies):
            return True

    # 6. Antígeno prostático (PSA)
    if "PROSTAT" in norm_s or "PSA" in norm_s:
        if any("PROSTAT" in cs or "PSA" in cs for cs in chk_studies):
            return True

    # 7. Hemoglobina glicosilada (HbA1c)
    if "GLICOSILADA" in norm_s or "HBA1C" in norm_s:
        if any("GLICOSILADA" in cs or "HBA1C" in cs for cs in chk_studies):
            return True

    # 8. Perfil lipídico (si el Check-Up tiene Química >= 24 o Perfil Lipídico)
    if "LIPID" in norm_s:
        if any("QUIMICA" in cs and any(n in cs for n in ["24", "27", "30", "36", "40", "45", "50"]) for cs in chk_studies):
            return True
        if any("LIPID" in cs for cs in chk_studies):
            return True

    # 9. Papanicolaou / Citología
    if "PAPANICOLAOU" in norm_s or "CITOLOG" in norm_s:
        if any("PAPANICOLAOU" in cs or "CITOLOG" in cs for cs in chk_studies):
            return True

    # Coincidencia directa de subcadena
    for cs in chk_studies:
        if norm_s in cs or cs in norm_s:
            return True

    return False


def filter_studies_covered_by_checkup(
    selected_studies: List[str],
    checkup: Dict[str, Any],
    adicionales_list: Optional[List[Dict[str, Any]]] = None
) -> Tuple[List[str], List[str], List[Dict[str, Any]]]:
    """
    Separa los estudios seleccionados en:
    1. remaining_studies: estudios no cubiertos que siguen sueltos.
    2. removed_studies: estudios cubiertos/sustituidos por el Check-Up.
    3. moved_to_adicionales: estudios que no estaban en el Check-Up pero son adicionales en promoción.
    """
    if adicionales_list is None:
        adicionales_list = get_lcm_adicionales()

    remaining_studies = []
    removed_studies = []
    moved_to_adicionales = []

    for s in selected_studies:
        if is_study_covered_by_checkup(s, checkup):
            removed_studies.append(s)
        else:
            # Revisar si es un estudio adicional que conviene pasar a tarifa preferencial
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

