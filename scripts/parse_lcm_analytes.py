r"""
Script que analiza y extrae el catálogo oficial de analitos y perfiles desde
C:/Users/pcone/Downloads/Directorio catalogo maquila 2024.xlsx
Genera config/lcm_analitos_catalog.json para el Cotizador Inteligente y Sugeridor de Check-Ups.
"""

import sys
import json
import re
from pathlib import Path
import pandas as pd

DOWNLOADS_PATH = Path(r"C:\Users\pcone\Downloads\Directorio catalogo maquila 2024.xlsx")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_JSON = PROJECT_ROOT / "config" / "lcm_analitos_catalog.json"

def clean_analyte(analyte: str) -> str:
    """Limpia y normaliza el nombre de un analito."""
    a = analyte.strip()
    a = re.sub(r"\s+", " ", a)
    # Quitar puntos finales
    a = a.rstrip(".")
    return a

def parse_excel():
    if not DOWNLOADS_PATH.exists():
        print(f"Error: No se encontró el archivo en {DOWNLOADS_PATH}")
        return

    df = pd.read_excel(DOWNLOADS_PATH, header=None)
    print(f"Leyendo Excel con {len(df)} filas...")

    catalog = {}
    quimicas = {}
    perfiles = {}
    paneles_infecciosos = {}

    for idx in range(2, len(df)):
        row = df.iloc[idx]
        code_raw = row[0]
        name_raw = row[1]
        
        if pd.isna(name_raw) or str(name_raw).strip() == "" or str(name_raw).strip() == "nan":
            continue

        code = str(int(code_raw)) if pd.notna(code_raw) and isinstance(code_raw, (int, float)) else str(code_raw or "").strip()
        raw_text = str(name_raw).strip()

        # Separar por saltos de línea
        lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
        main_name = lines[0]
        analytes_text = " ".join(lines[1:]) if len(lines) > 1 else ""

        # Caso especial Química 12
        if "12 ELEMENTOS" in main_name and not analytes_text:
            parts = main_name.split("12 ELEMENTOS")
            main_name = parts[0] + "12 ELEMENTOS"
            analytes_text = parts[1].strip()

        analytes = []
        if analytes_text:
            raw_analytes = [clean_analyte(a) for a in analytes_text.split(",") if clean_analyte(a)]
            analytes = raw_analytes

        sample_req = str(row[2]).strip() if pd.notna(row[2]) and str(row[2]) != "nan" else ""
        turnaround = str(row[3]).strip() if pd.notna(row[3]) and str(row[3]) != "nan" else ""
        sample_type = str(row[4]).strip() if pd.notna(row[4]) and str(row[4]) != "nan" else ""

        # Clasificar tipo de estudio
        study_type = "INDIVIDUAL"
        category = "General"
        upper_name = main_name.upper()

        if "QUÍMICA" in upper_name or "QUIMICA" in upper_name:
            study_type = "QUIMICA_SANGUINEA"
            category = "Bioquímica Clínica"
        elif "PERFIL" in upper_name:
            study_type = "PERFIL_CLINICO"
            if "TIROID" in upper_name: category = "Tiroides / Endocrino"
            elif "LIPID" in upper_name: category = "Lípidos / Cardiovascular"
            elif "HEPATIC" in upper_name: category = "Hígado / Hepático"
            elif "HORMONAL" in upper_name: category = "Hormonal / Ginecología"
            elif "RENAL" in upper_name: category = "Función Renal"
            elif "REUMAT" in upper_name: category = "Reumatología"
            elif "DIABET" in upper_name: category = "Diabetes / Metabólico"
            elif "HIERRO" in upper_name: category = "Hematología / Hierro"
            elif "PREOPERATORIO" in upper_name: category = "Preoperatorio"
            elif "TORCH" in upper_name: category = "Infeccioso / Embarazo"
            else: category = "Perfiles Especiales"
        elif "PANEL" in upper_name:
            study_type = "PANEL_DIAGNOSTICO"
            category = "Biología Molecular / Paneles"
        elif "BIOMETR" in upper_name:
            study_type = "HEMATOLOGIA"
            category = "Hematología"
            if not analytes:
                analytes = [
                    "Eritrocitos", "Hemoglobina", "Hematocrito", "VCM", "HCM", "CHCM",
                    "Leucocitos totales", "Neutrófilos", "Linfocitos", "Monocitos", "Eosinófilos", "Basófilos",
                    "Plaquetas", "Volumen Plaquetario Medio (VPM)"
                ]
        elif "EXAMEN GENERAL DE ORINA" in upper_name or upper_name == "EGO":
            study_type = "UROANALISIS"
            category = "Uroanálisis"
            if not analytes:
                analytes = [
                    "Examen Físico (Color, Aspecto, Densidad)",
                    "Examen Químico (pH, Glucosa, Proteínas, Cetonas, Bilirrubina, Sangre/Hb, Urobilinógeno, Nitritos, Leucocitos)",
                    "Sedimento Microscópico (Células epiteliales, Leucocitos, Eritrocitos, Bacterias, Cristales, Cilindros, Mucus)"
                ]

        entry = {
            "code": code,
            "name": main_name,
            "full_name": raw_text,
            "study_type": study_type,
            "category": category,
            "analytes": analytes,
            "analytes_count": len(analytes),
            "sample_req": sample_req,
            "turnaround": turnaround,
            "sample_type": sample_type
        }

        catalog[code or f"ROW_{idx}"] = entry

        if study_type == "QUIMICA_SANGUINEA":
            quimicas[code] = entry
        elif study_type == "PERFIL_CLINICO":
            perfiles[code] = entry
        elif study_type == "PANEL_DIAGNOSTICO":
            paneles_infecciosos[code] = entry

    print(f"Total estudios procesados: {len(catalog)}")
    print(f"  - Químicas Sanguíneas: {len(quimicas)}")
    print(f"  - Perfiles Clínicos: {len(perfiles)}")
    print(f"  - Paneles Diagnósticos / PCR: {len(paneles_infecciosos)}")

    # Guardar en JSON
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)

    print(f"Archivo guardado exitosamente en: {OUTPUT_JSON}")

if __name__ == "__main__":
    parse_excel()
