# Chopo Price Intelligence

Sistema de scraping y análisis de precios de laboratorio para **Chopo Mérida, Yucatán**. Diseñado para análisis competitivo de mercado con actualización automática diaria y dashboard profesional.

---

## 🏗️ Arquitectura

```
chopo_scraper/
├── main.py                  # Punto de entrada CLI
├── requirements.txt         # Dependencias Python
├── setup.ps1                # Script de instalación (Windows)
│
├── scraper/
│   ├── chopo_scraper.py     # Motor de scraping (Playwright)
│   ├── exporter.py          # Exportación Excel / CSV
│   └── scheduler.py         # Actualizaciones automáticas (APScheduler)
│
├── db/
│   └── database.py          # Base de datos SQLite + historial
│
├── dashboard/
│   └── app.py               # Dashboard Streamlit
│
├── exports/                 # Archivos Excel/CSV generados
└── logs/                    # Logs del sistema
```

## ⚙️ Stack Técnico

| Componente | Tecnología | Por qué |
|---|---|---|
| **Scraping** | Playwright | Chopo usa Magento 2 con JS dinámico |
| **Base de datos** | SQLite | Sin servidor, historial append-only |
| **Dashboard** | Streamlit + Plotly | UI rápida con gráficos interactivos |
| **Scheduler** | APScheduler | Actualizaciones diarias automáticas |
| **Exportación** | openpyxl + xlsxwriter | Excel con formato profesional |
| **Logging** | loguru | Logs estructurados y rotativos |

## 🚀 Instalación

### Opción 1: Script automático (recomendado)
```powershell
cd "chopo_scraper"
powershell -ExecutionPolicy Bypass -File setup.ps1
```

### Opción 2: Manual
```powershell
# Crear entorno virtual
python -m venv venv
.\venv\Scripts\Activate.ps1

# Instalar dependencias
pip install -r requirements.txt

# Instalar browser para Playwright
python -m playwright install chromium

# Inicializar BD
python main.py init
```

## 📋 Comandos

```powershell
# Ejecutar scrape inmediato
python main.py scrape

# Lanzar dashboard (abre http://localhost:8501)
python main.py dashboard

# Iniciar scheduler diario (6 AM, zona horaria Mérida)
python main.py scheduler

# Exportar datos a Excel
python main.py export

# Solo inicializar BD
python main.py init
```

## 🔬 Cómo Funciona el Scraper

1. **Playwright** abre Chromium (headless) y navega a `chopo.com.mx/yucatan/estudios/`
2. Espera que el JS de Magento 2 cargue los productos
3. Extrae nombres y precios usando 3 estrategias en cascada:
   - JavaScript directo en el DOM
   - JSON del estado de Magento (`text/x-magento-init`)
   - Fallback HTML con BeautifulSoup
4. Maneja **paginación** automáticamente
5. Guarda en SQLite con timestamp para historial
6. El scheduler lo repite a las **6:00 AM** diariamente

## 📊 Dashboard

El dashboard Streamlit incluye 5 pestañas:

- **📋 Catálogo**: Tabla filtrable con todos los estudios y precios actuales
- **📊 Análisis**: Gráficos de distribución, top estudios, segmentación por precio
- **📈 Historial**: Evolución temporal del precio de cualquier estudio
- **🔔 Cambios**: Alertas de subidas/bajadas de precio detectadas
- **🗂️ Logs**: Registro de todos los scrapes ejecutados

## 🏥 Agregar Más Laboratorios

Edita `scraper/chopo_scraper.py`, en `LABS_CONFIG`:

```python
LABS_CONFIG = {
    "chopo_yucatan": { ... },  # Ya configurado
    
    # Agregar nuevo laboratorio:
    "chopo_cdmx": {
        "name": "Chopo Ciudad de México",
        "url": "https://www.chopo.com.mx/cdmx/estudios/",
        "city": "Ciudad de México",
        "state": "CDMX",
    },
    "laboratorio_xyz": {
        "name": "Laboratorio XYZ Mérida",
        "url": "https://www.lab-xyz.com/precios",
        "city": "Mérida",
        "state": "Yucatán",
    },
}
```

## 📝 Notas Técnicas

- La BD SQLite es **append-only** en precios: nunca se borran registros históricos
- El scraper incluye rate-limiting cortés (2 segundos entre páginas)
- Los recursos multimedia se bloquean para acelerar el scraping
- El User-Agent imita un Chrome real para evitar bloqueos

## ⚖️ Uso Ético

- Solo scraping de datos **públicamente disponibles**
- Implementa delays entre requests para no sobrecargar el servidor
- Para uso de análisis de mercado interno
