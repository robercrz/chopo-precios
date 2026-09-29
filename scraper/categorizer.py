# ============================================================
# scraper/categorizer.py
# Clasificacion automatica de estudios clinicos por especialidad
# ============================================================

from functools import lru_cache
from typing import Optional

# ── Mapa de categorias con keywords (minusculas, sin acentos) ─────────────────
CATEGORY_RULES: list[tuple[str, list[str]]] = [
    ("Hematologia", [
        "biometria", "hemoglobina", "hematocrito", "plaquetas", "leucocitos",
        "eritrocitos", "reticulocitos", "hematies", "serie roja", "serie blanca",
        "diferencial", "formula", "conteo", "sangre", "coagulacion",
        "protrombina", "trombina", "fibrinogeno", "tiempo de sangrado",
        "tiempo parcial", "tromboelastografia",
    ]),
    ("Bioquimica General", [
        "glucosa", "glucemia", "glicemia", "hemoglobina glicosilada", "hba1c",
        "colesterol", "trigliceridos", "lipidos", "lipidico", "hdl", "ldl", "vldl",
        "acido urico", "urea", "nitrogeno ureico", "bun", "creatinina", "depuracion",
        "albumina", "proteinas totales", "globulinas", "bilirrubina", "bilis",
        "fosfatasa alcalina", "transaminasa", "alt", "ast", "alat", "asat",
        "ggt", "gamma gt", "ldh", "deshidrogenasa", "amilasa", "lipasa",
        "capnia", "lactato", "piruvato", "amonio",
    ]),
    ("Tiroides", [
        "tiroides", "tiroideo", "tiroidea", "t3", "t4", "tsh",
        "tiroxina", "triyodotironina", "tiroglobulina", "calcitonina",
        "anticuerpos antitiroideos", "anti-tpo", "anti-tg",
    ]),
    ("Vitaminas y Minerales", [
        "vitamina", "folico", "acido folico", "b12", "cobalamina",
        "zinc", "magnesio", "calcio", "fosforo", "potasio", "sodio",
        "hierro", "ferritina", "transferrina", "saturacion", "cobre",
        "selenio", "manganeso", "cromo", "yodo", "25 hidroxi",
        "calciferol", "retinol", "tocoferol", "biotina", "riboflavina",
    ]),
    ("Hormonas", [
        "hormona", "testosterona", "estradiol", "estriol", "estrogeno",
        "progesterona", "cortisol", "insulina", "prolactina", "lh", "fsh",
        "dhea", "dheas", "androstenediona", "pregnenolona",
        "hormona del crecimiento", "gh", "igf", "somatotropina",
        "parathormona", "pth", "aldosterona", "renina", "ercp",
        "gonadotropina", "hcg", "beta hcg", "embarazo",
    ]),
    ("Infectologia", [
        "vih", "hiv", "sida", "hepatitis", "anti-hbs", "hbsag", "hcv",
        "sifilis", "vdrl", "rpr", "treponema", "toxoplasma", "rubeola",
        "citomegalovirus", "cmv", "ebstein", "epstein", "herpes",
        "covid", "sars-cov", "coronavirus", "influenza", "dengue",
        "zika", "chikungunya", "tuberculosis", "brucella", "brucelosis",
        "salmonela", "listeria", "leptospira", "chagas", "paludismo",
        "malaria", "anticuerpos", "igm", "igg", "iga",
    ]),
    ("Microbiologia", [
        "cultivo", "antibiograma", "sensibilidad", "urocultivo", "hemocultivo",
        "coprocultivo", "exudado", "frotis", "gram", "baciloscopia",
        "parasitoscopia", "parasito", "ameba", "giardia", "helicobacter",
        "heces", "coproparasitologico", "examen general de heces",
        "flora", "levadura", "candida", "hongos",
    ]),
    ("Orina", [
        "orina", "urinalisis", "examen general de orina", "ego",
        "proteinuria", "microalbuminuria", "creatinina urinaria",
        "osmolaridad urinaria", "urocultivo",
    ]),
    ("Oncologia", [
        "cancer", "tumor", "oncologico", "psa", "psa libre", "cea",
        "ca 125", "ca 19-9", "ca 15-3", "alfa fetoproteina",
        "antigeno carcino", "beta 2 microglobulina", "cyfra",
        "nse", "enolasa", "oncologico", "marcador tumoral",
    ]),
    ("Cardiologia", [
        "cardiaco", "troponina", "ck-mb", "creatinkinasa", "cpk",
        "pro-bnp", "bnp", "mioglobina", "homocisteina", "proteina c reactiva",
        "pcr", "fibrinogeno", "dimer", "dimero d",
    ]),
    ("Genetica y Molecular", [
        "genetico", "cromosoma", "dna", "adn", "gen", "mutacion",
        "pcr molecular", "genotipo", "secuenciacion", "hibridacion",
        "cariotipo", "polimorfismo", "farmacogenetica", "brca",
    ]),
    ("Alergias e Inmunologia", [
        "alerg", "ige", "ige total", "alergeno", "inmunoelectroforesis",
        "electroforesis", "inmunoglobulinas", "complemento", "c3", "c4",
        "factor reumatoide", "anca", "ana", "anticuerpo antinuclear",
        "lupus", "artritis", "autoinmune",
    ]),
    ("Endocrinologia", [
        "insulinemia", "resistencia insulina", "homa", "diabetes",
        "obesidad", "sobrepeso", "metabolico", "cortisol",
    ]),
    ("Perfil y Paneles", [
        "perfil", "panel", "paquete", "integral", "completo", "basico",
        "prenatal", "preoperatorio", "preventivo", "check", "ejecutivo",
    ]),
    ("Toxicologia", [
        "toxicologia", "droga", "narcotico", "alcohol", "etanol",
        "metanol", "plomo", "mercurio", "arsenico", "metal pesado",
        "medicamento", "farmaco",
    ]),
    ("Estudios Especiales", [
        "electrocardiograma", "espirometria", "audiometria",
        "densitometria", "tonometria",
    ]),
]

# ── Normalizacion de texto ────────────────────────────────────────────────────
_ACCENT_MAP = str.maketrans(
    "áéíóúàèìòùâêîôûãõäëïöüÁÉÍÓÚÀÈÌÒÙÂÊÎÔÛÃÕÄËÏÖÜ",
    "aeiouaeiouaeiouaoaeiouAEIOUAEIOUAEIOUAOAEIOU",
)


def _normalize(text: str) -> str:
    """Convierte a minúsculas y quita acentos para comparación."""
    return text.lower().translate(_ACCENT_MAP)


# ── Clasificador principal ────────────────────────────────────────────────────
@lru_cache(maxsize=4096)
def classify_study(study_name: str) -> str:
    """
    Clasifica un estudio en una categoría de especialidad médica.
    Usa búsqueda de keywords en el nombre del estudio.
    Retorna 'Otros' si no hay coincidencia.
    """
    normalized = _normalize(study_name)
    for category, keywords in CATEGORY_RULES:
        for kw in keywords:
            if kw in normalized:
                return category
    return "Otros"


def classify_all(studies: list[dict], name_field: str = "study_name") -> list[dict]:
    """
    Clasifica una lista de estudios.
    Agrega el campo 'category' a cada dict.
    """
    for s in studies:
        name = s.get(name_field, "")
        s["category"] = classify_study(name) if name else "Otros"
    return studies


def get_category_counts(studies: list[dict]) -> dict[str, int]:
    """Cuenta estudios por categoría."""
    counts: dict[str, int] = {}
    for s in studies:
        cat = s.get("category", classify_study(s.get("study_name", "")))
        counts[cat] = counts.get(cat, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: -x[1]))


ALL_CATEGORIES = ["Todas"] + [cat for cat, _ in CATEGORY_RULES] + ["Otros"]


if __name__ == "__main__":
    # Test rapido
    samples = [
        "BIOMETRÍA HEMÁTICA", "TSH ULTRASENSIBLE", "VITAMINA D TOTAL",
        "GLUCOSA EN SUERO", "CULTIVO DE ORINA", "PSA TOTAL",
        "TESTOSTERONA TOTAL", "DENGUE IGM", "PERFIL TIROIDEO",
        "EXAMEN GENERAL DE ORINA", "COLESTEROL TOTAL", "HEMOGLOBINA GLICOSILADA",
    ]
    for s in samples:
        print(f"  {s:<45} -> {classify_study(s)}")
