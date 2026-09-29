# ============================================================
# scraper/exporter.py
# Exportación a Excel (XLSX) con múltiples hojas y formato
# ============================================================

from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from loguru import logger

EXPORTS_DIR = Path(__file__).parent.parent / "exports"
EXPORTS_DIR.mkdir(exist_ok=True)


def export_to_excel(
    data: list[dict],
    history_data: Optional[list[dict]] = None,
    changes_data: Optional[list[dict]] = None,
    filename: Optional[str] = None,
) -> Path:
    """
    Exporta los datos de precios a un archivo Excel (.xlsx) con formato profesional.

    Args:
        data: Lista de precios actuales
        history_data: Historial de precios (opcional)
        changes_data: Cambios de precio detectados (opcional)
        filename: Nombre del archivo (se genera automático si no se especifica)

    Returns:
        Path al archivo generado
    """
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"chopo_precios_{timestamp}.xlsx"

    filepath = EXPORTS_DIR / filename
    logger.info(f"Exportando a Excel: {filepath}")

    df_current = pd.DataFrame(data) if data else pd.DataFrame()
    df_history = pd.DataFrame(history_data) if history_data else pd.DataFrame()
    df_changes = pd.DataFrame(changes_data) if changes_data else pd.DataFrame()

    with pd.ExcelWriter(str(filepath), engine="xlsxwriter") as writer:
        workbook = writer.book

        # ── Formatos ──────────────────────────────────────────────────────────
        header_fmt = workbook.add_format({
            "bold": True, "font_color": "white", "bg_color": "#1a5276",
            "border": 1, "align": "center", "valign": "vcenter",
            "font_size": 11,
        })
        price_fmt = workbook.add_format({
            "num_format": '"$"#,##0.00', "border": 1,
        })
        pct_fmt = workbook.add_format({
            "num_format": '0.00"%"', "border": 1,
        })
        date_fmt = workbook.add_format({
            "num_format": "dd/mm/yyyy hh:mm", "border": 1, "align": "center",
        })
        cell_fmt = workbook.add_format({"border": 1})
        title_fmt = workbook.add_format({
            "bold": True, "font_size": 16, "font_color": "#1a5276",
        })
        subtitle_fmt = workbook.add_format({
            "italic": True, "font_size": 10, "font_color": "#7f8c8d",
        })
        increase_fmt = workbook.add_format({
            "bold": True, "font_color": "#c0392b", "border": 1,  # rojo = subida
        })
        decrease_fmt = workbook.add_format({
            "bold": True, "font_color": "#27ae60", "border": 1,  # verde = bajada
        })

        # ── Hoja 1: Precios Actuales ──────────────────────────────────────────
        if not df_current.empty:
            sheet_name = "Precios Actuales"
            df_current.to_excel(writer, sheet_name=sheet_name, startrow=4, index=False)
            ws = writer.sheets[sheet_name]

            ws.write("A1", "🔬 Chopo Price Intelligence", title_fmt)
            ws.write("A2", f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}", subtitle_fmt)
            ws.write("A3", f"Total estudios: {len(df_current)}", subtitle_fmt)

            # Encabezados formateados
            columns = list(df_current.columns)
            col_widths = {
                "study_name": 45, "lab_name": 25, "city": 15, "state": 12,
                "price": 12, "price_raw": 15, "scraped_at": 20, "url": 40, "sku": 15,
            }
            for col_idx, col_name in enumerate(columns):
                ws.write(4, col_idx, col_name.replace("_", " ").title(), header_fmt)
                width = col_widths.get(col_name, 15)
                ws.set_column(col_idx, col_idx, width)

            # Aplicar formato a celdas de precio
            if "price" in columns:
                price_col_idx = columns.index("price")
                for row_idx in range(len(df_current)):
                    val = df_current.iloc[row_idx].get("price")
                    if pd.notna(val):
                        ws.write(row_idx + 5, price_col_idx, val, price_fmt)

            # Filtros automáticos
            ws.autofilter(4, 0, 4 + len(df_current), len(columns) - 1)
            ws.freeze_panes(5, 0)

            # Gráfico de distribución de precios
            if "price" in df_current.columns:
                prices = df_current["price"].dropna()
                if len(prices) > 0:
                    chart = workbook.add_chart({"type": "column"})
                    # Simplificado: top 20 estudios por precio
                    top20 = df_current.nlargest(20, "price")[["study_name", "price"]]
                    top20_sheet = "Top 20 Precios"
                    top20.to_excel(writer, sheet_name=top20_sheet, startrow=2, index=False)
                    ws_top = writer.sheets[top20_sheet]
                    ws_top.write("A1", "Top 20 Estudios por Precio", title_fmt)

        # ── Hoja 2: Historial de Precios ─────────────────────────────────────
        if not df_history.empty:
            sheet_name = "Historial"
            df_history.to_excel(writer, sheet_name=sheet_name, startrow=3, index=False)
            ws = writer.sheets[sheet_name]
            ws.write("A1", "📊 Historial de Precios", title_fmt)
            ws.write("A2", f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}", subtitle_fmt)
            columns = list(df_history.columns)
            for col_idx, col_name in enumerate(columns):
                ws.write(3, col_idx, col_name.replace("_", " ").title(), header_fmt)
                ws.set_column(col_idx, col_idx, 20)
            ws.autofilter(3, 0, 3 + len(df_history), len(columns) - 1)
            ws.freeze_panes(4, 0)

        # ── Hoja 3: Cambios de Precio ─────────────────────────────────────────
        if not df_changes.empty:
            sheet_name = "Cambios de Precio"
            df_changes.to_excel(writer, sheet_name=sheet_name, startrow=3, index=False)
            ws = writer.sheets[sheet_name]
            ws.write("A1", "⚠️ Cambios de Precio Detectados", title_fmt)
            ws.write("A2", f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}", subtitle_fmt)
            columns = list(df_changes.columns)
            for col_idx, col_name in enumerate(columns):
                ws.write(3, col_idx, col_name.replace("_", " ").title(), header_fmt)
                ws.set_column(col_idx, col_idx, 18)

            # Colorear filas de cambios (rojo = subida, verde = bajada)
            if "change_pct" in columns:
                chg_col = columns.index("change_pct")
                for row_idx, row in df_changes.iterrows():
                    chg = row.get("change_pct", 0)
                    fmt = increase_fmt if (chg or 0) > 0 else decrease_fmt
                    ws.write(row_idx - df_changes.index[0] + 4, chg_col, chg, fmt)

            ws.autofilter(3, 0, 3 + len(df_changes), len(columns) - 1)
            ws.freeze_panes(4, 0)

        # ── Hoja 4: Resumen Estadístico ───────────────────────────────────────
        if not df_current.empty and "price" in df_current.columns:
            sheet_name = "Resumen"
            ws = workbook.add_worksheet(sheet_name)
            ws.write("A1", "📈 Resumen Estadístico", title_fmt)
            ws.write("A2", f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}", subtitle_fmt)

            stats = [
                ("Total de estudios", len(df_current)),
                ("Con precio", int(df_current["price"].notna().sum())),
                ("Sin precio", int(df_current["price"].isna().sum())),
                ("Precio mínimo", df_current["price"].min()),
                ("Precio máximo", df_current["price"].max()),
                ("Precio promedio", df_current["price"].mean()),
                ("Precio mediano", df_current["price"].median()),
            ]
            ws.write(3, 0, "Métrica", header_fmt)
            ws.write(3, 1, "Valor", header_fmt)
            ws.set_column(0, 0, 25)
            ws.set_column(1, 1, 15)

            for i, (metric, value) in enumerate(stats):
                ws.write(i + 4, 0, metric, cell_fmt)
                if isinstance(value, float):
                    ws.write(i + 4, 1, value, price_fmt)
                else:
                    ws.write(i + 4, 1, value, cell_fmt)

            # Por laboratorio si hay varios
            if "lab_name" in df_current.columns:
                ws.write(13, 0, "Por Laboratorio", header_fmt)
                ws.write(13, 1, "Promedio Precio", header_fmt)
                ws.write(13, 2, "Estudios", header_fmt)
                ws.set_column(2, 2, 12)
                by_lab = df_current.groupby("lab_name")["price"].agg(["mean", "count"])
                for i, (lab, row) in enumerate(by_lab.iterrows()):
                    ws.write(14 + i, 0, lab, cell_fmt)
                    ws.write(14 + i, 1, row["mean"], price_fmt)
                    ws.write(14 + i, 2, int(row["count"]), cell_fmt)

    logger.success(f"Excel exportado exitosamente: {filepath}")
    return filepath


def export_to_csv(data: list[dict], filename: Optional[str] = None) -> Path:
    """Exportación rápida a CSV."""
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"chopo_precios_{timestamp}.csv"

    filepath = EXPORTS_DIR / filename
    df = pd.DataFrame(data)
    df.to_csv(str(filepath), index=False, encoding="utf-8-sig")  # utf-8-sig para Excel en Windows
    logger.success(f"CSV exportado: {filepath}")
    return filepath
