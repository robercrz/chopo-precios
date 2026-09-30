import re
import sqlite3
import unicodedata
import openpyxl
import pdfplumber
from rapidfuzz import fuzz, process

def strip_accents(s: str) -> str:
    if not s:
        return ""
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn').upper()

# Medical canonical dictionary / synonyms
SYNONYMS = [
    (r'\bBIOMETRIA\s+HEMATICA\b', 'CITOMETRIA HEMATICA'),
    (r'\bB\.?H\.?\b', 'CITOMETRIA HEMATICA'),
    (r'\bEXAMEN\s+GENERAL\s+DE\s+ORINA\b', 'EXAMEN GENERAL DE ORINA'),
    (r'\bE\.?G\.?O\.?\b', 'EXAMEN GENERAL DE ORINA'),
    (r'\bHEMOGLOBINA\s+GLICOSILADA\b', 'HEMOGLOBINA GLICOSILADA A1C'),
    (r'\bHEMOGLOBINA\s+GLICADA\b', 'HEMOGLOBINA GLICOSILADA A1C'),
    (r'\bHBA1C\b', 'HEMOGLOBINA GLICOSILADA A1C'),
    (r'\bANTIGENO\s+PROSTATICO\s+ESPECIFICO\b', 'ANTIGENO PROSTATICO ESPECIFICO PSA'),
    (r'\bPSA\s+TOTAL\b', 'ANTIGENO PROSTATICO ESPECIFICO PSA'),
    (r'\bPROTEINA\s+C\s+REACTIVA\b', 'PROTEINA C REACTIVA PCR'),
    (r'\bP\.?C\.?R\.?\b', 'PROTEINA C REACTIVA PCR'),
    (r'\bPRUEBAS\s+DE\s+FUNCION\s+HEPATICA\b', 'PERFIL HEPATICO'),
    (r'\bPFH\b', 'PERFIL HEPATICO'),
    (r'\bRAYOS\s+X\b', 'RADIOGRAFIA'),
    (r'\bRX\b', 'RADIOGRAFIA'),
    (r'\bULTRASONIDO\b', 'ULTRASONIDO'),
    (r'\bECOGRAFIA\b', 'ULTRASONIDO'),
    (r'\bELECTROCARDIOGRAMA\s+EN\s+REPOSO\b', 'ELECTROCARDIOGRAMA'),
    (r'\bCOPROPARASITOSCOPICO\s+1\s+MUESTRA\b', 'COPROPARASITOSCOPICO UNICO'),
    (r'\bCPS\b', 'COPROPARASITOSCOPICO'),
    (r'\bREACCIONES\s+FEBRILES\b', 'REACCIONES FEBRILES'),
    (r'\bQUIMICA\s+CLINICA\b', 'QUIMICA SANGUINEA'),
    (r'\bQUIMICA\s+INTEGRAL\b', 'QUIMICA SANGUINEA'),
    (r'\bQS\b', 'QUIMICA SANGUINEA'),
]

def normalize_medical_term(text: str) -> str:
    t = strip_accents(text)
    # clean extra characters
    t = re.sub(r'[\(\)\[\]\,\.\-\/\:\;\*\+]', ' ', t)
    t = ' '.join(t.split())
    # apply synonyms
    for pattern, repl in SYNONYMS:
        t = re.sub(pattern, repl, t)
    t = ' '.join(t.split())
    return t

def extract_elements_count(text: str):
    """Detects numbers of elements in Quimica Sanguinea (e.g. 6, 24, 30, 45, etc.)"""
    m = re.search(r'(\d+)\s*(?:ELEMENTOS|PARAMETROS)', text)
    if m:
        return int(m.group(1))
    return None

def test():
    # 1. Load Chopo Studies
    conn = sqlite3.connect('db/chopo_prices.db')
    cur = conn.cursor()
    cur.execute("""
        SELECT study_name, price, price_original, url, sku
        FROM latest_prices
    """)
    chopo_rows = cur.fetchall()
    conn.close()

    chopo_catalog = []
    for row in chopo_rows:
        chopo_catalog.append({
            'name': row[0],
            'name_norm': normalize_medical_term(row[0]),
            'elements': extract_elements_count(row[0]),
            'price_web': row[1],
            'price_list': row[2],
            'url': row[3],
            'sku': row[4]
        })
    print(f"Loaded {len(chopo_catalog)} Chopo studies.")

    # 2. Load LCM PDF studies
    pdf_file = r'data\lcm\ListaGeneral2025 actualizado a marzo de 2025.pdf'
    lcm_studies = []
    with pdfplumber.open(pdf_file) as pdf:
        for p_idx, page in enumerate(pdf.pages):
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if not row or len(row) < 3:
                        continue
                    clave, estudio, precio = row[0], row[1], row[2]
                    if clave == 'CLAVE' or not estudio or not precio:
                        continue
                    p_str = re.sub(r'[\s\$]', '', str(precio)).replace(',', '')
                    try:
                        p_val = float(p_str)
                        lcm_studies.append({
                            'code': str(clave).strip(),
                            'name': ' '.join(str(estudio).split()),
                            'name_norm': normalize_medical_term(str(estudio)),
                            'elements': extract_elements_count(str(estudio)),
                            'price': p_val,
                            'page': p_idx + 1
                        })
                    except ValueError:
                        pass
    print(f"Loaded {len(lcm_studies)} LCM studies from PDF.")

    # 3. Test Matching
    exact_matches = 0
    high_conf = 0   # score >= 85
    med_conf = 0    # score >= 70
    low_conf = 0    # score < 70
    
    samples = []
    chopo_names_norm = [c['name_norm'] for c in chopo_catalog]
    
    for lcm in lcm_studies:
        lcm_norm = lcm['name_norm']
        lcm_elem = lcm['elements']
        
        # Check exact norm match
        exact_found = None
        for c in chopo_catalog:
            if c['name_norm'] == lcm_norm:
                exact_found = c
                break
        
        if exact_found:
            exact_matches += 1
            if len(samples) < 5:
                samples.append(('EXACT', lcm['name'], exact_found['name'], 100, lcm['price'], exact_found['price_web']))
            continue
            
        # Fuzzy match
        # If Quimica Sanguinea, restrict to same number of elements
        candidates = chopo_catalog
        if lcm_elem is not None:
            filtered = [c for c in chopo_catalog if c['elements'] == lcm_elem]
            if filtered:
                candidates = filtered
                
        best_score = 0
        best_match = None
        for c in candidates:
            # Token sort ratio is robust to word reorderings
            score1 = fuzz.token_sort_ratio(lcm_norm, c['name_norm'])
            # Token set ratio handles subsets (e.g. "GLUCOSA" in "GLUCOSA EN SUERO")
            score2 = fuzz.token_set_ratio(lcm_norm, c['name_norm'])
            score = (score1 * 0.6) + (score2 * 0.4)
            if score > best_score:
                best_score = score
                best_match = c
                
        if best_score >= 85:
            high_conf += 1
            if len(samples) < 15:
                samples.append(('HIGH', lcm['name'], best_match['name'], round(best_score, 1), lcm['price'], best_match['price_web']))
        elif best_score >= 70:
            med_conf += 1
            if len(samples) < 25:
                samples.append(('MED', lcm['name'], best_match['name'], round(best_score, 1), lcm['price'], best_match['price_web']))
        else:
            low_conf += 1

    print("\n=== MATCHING RESULTS ===")
    print(f"Total LCM Studies: {len(lcm_studies)}")
    print(f"Exact Normalized Matches: {exact_matches} ({exact_matches/len(lcm_studies)*100:.1f}%)")
    print(f"High Confidence (>=85%): {high_conf} ({high_conf/len(lcm_studies)*100:.1f}%)")
    print(f"Medium Confidence (70-84%): {med_conf} ({med_conf/len(lcm_studies)*100:.1f}%)")
    print(f"Low Confidence / No Match (<70%): {low_conf} ({low_conf/len(lcm_studies)*100:.1f}%)")
    print(f"Total Actionable Matches (>=70%): {exact_matches + high_conf + med_conf} ({(exact_matches + high_conf + med_conf)/len(lcm_studies)*100:.1f}%)")

    print("\n=== SAMPLE MATCHES ===")
    for kind, lcm_n, chopo_n, sc, p_lcm, p_chopo in samples:
        print(f"[{kind} {sc}%] LCM: '{lcm_n}' (${p_lcm}) <===> CHOPO: '{chopo_n}' (${p_chopo})")

if __name__ == '__main__':
    test()
