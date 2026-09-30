# ============================================================
# scraper/chopo_scraper.py  — v4 FINAL
# Selectores reales verificados, scroll para lazy loading,
# espera correcta de precios JS-renderizados.
# ============================================================

import asyncio
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

LOGS_DIR = Path(__file__).parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# ── Configuracion de laboratorios ──────────────────────────────────────────────
LABS_CONFIG = {
    "chopo_yucatan": {
        "name": "Chopo Merida Yucatan",
        "url": "https://www.chopo.com.mx/yucatan/estudios/",
        "city": "Merida",
        "state": "Yucatan",
    }
}

# ── Sucursales disponibles ─────────────────────────────────────────────────────
KNOWN_BRANCHES = {
    "altabrisa": {
        "name": "Merida Altabrisa",
        "search_term": "Altabrisa Merida Yucatan",
        "storelocatorid": "295",
    },
    # Agrega mas sucursales aqui segun las descubras:
    # "gran_plaza": {
    #     "name": "Merida Gran Plaza",
    #     "search_term": "Gran Plaza Merida Yucatan",
    #     "storelocatorid": "???",
    # },
}


class ChopoScraper:
    """
    Scraper v4 FINAL para Laboratorio Chopo.
    Selectores CSS verificados directamente en el DOM real del sitio.
    """

    def __init__(
        self,
        lab_key: str = "chopo_yucatan",
        branch_key: str = "altabrisa",
        headless: bool = True,
    ):
        self.lab_key = lab_key
        self.branch_key = branch_key
        self.config = LABS_CONFIG[lab_key]
        self.branch_config = KNOWN_BRANCHES.get(branch_key, KNOWN_BRANCHES["altabrisa"])
        self.headless = headless
        self.results: list = []

    async def _screenshot(self, page, name: str) -> None:
        try:
            path = LOGS_DIR / f"{name}_{datetime.now().strftime('%H%M%S')}.png"
            await page.screenshot(path=str(path))
            logger.debug(f"Screenshot: {path.name}")
        except Exception:
            pass

    # ── Seleccion de sucursal ──────────────────────────────────────────────────
    async def _select_branch(self, page) -> bool:
        """
        Selecciona la sucursal escribiendo en el input de Google Places,
        espera el dropdown, selecciona con ArrowDown+Enter, y hace click
        en el boton 'Seleccionar' de la sucursal Chopo correcta.
        """
        branch = self.branch_config
        logger.info(f"Seleccionando sucursal: {branch['name']}")

        try:
            await page.wait_for_selector("#general_branch_selector_search", timeout=10000)
            inp = await page.query_selector("#general_branch_selector_search")
            if not inp:
                return False

            await inp.click()
            await asyncio.sleep(0.3)
            await inp.fill("")

            # Escribir caracter a caracter para activar Google Places
            for char in branch["search_term"]:
                await page.keyboard.type(char)
                await asyncio.sleep(0.1)

            await asyncio.sleep(3.5)  # Esperar autocomplete Google

            # Seleccionar primera sugerencia
            await page.keyboard.press("ArrowDown")
            await asyncio.sleep(0.5)
            await page.keyboard.press("Enter")
            await asyncio.sleep(5)  # Esperar que Chopo calcule sucursales cercanas

            # Hacer click en boton "Seleccionar" de la sucursal correcta
            clicked = await page.evaluate("""
                () => {
                    // Buscar el item de lista que contenga 'Altabrisa'
                    const items = document.querySelectorAll(
                        'li.item, .store-item, [data-storelocatorid], .storelocator__store'
                    );
                    for (const item of items) {
                        if (item.textContent.toLowerCase().includes('altabrisa')) {
                            const btn = item.querySelector('button, a.select, .btn-select');
                            if (btn) { btn.click(); return 'clicked:' + btn.textContent.trim(); }
                            item.click();
                            return 'item_clicked';
                        }
                    }
                    // Fallback: click en primer boton "Seleccionar"
                    for (const btn of document.querySelectorAll('button')) {
                        if (btn.textContent.trim() === 'Seleccionar') {
                            btn.click();
                            return 'fallback_seleccionar';
                        }
                    }
                    return null;
                }
            """)
            logger.info(f"Click en sucursal: {clicked}")
            await asyncio.sleep(5)  # Esperar que se procese la seleccion

            # Verificar que aparecio el mensaje de confirmacion
            confirmed = await page.evaluate("""
                () => {
                    const msg = document.querySelector('.message.success, .success-message, [class*="success"]');
                    const header = document.querySelector('.branch-selector-label, .branch-name, [class*="branch"]');
                    return {
                        success_msg: msg ? msg.textContent.trim() : null,
                        header_text: header ? header.textContent.trim() : document.title,
                    };
                }
            """)
            logger.info(f"Confirmacion: {confirmed}")
            return True

        except Exception as e:
            logger.error(f"Error seleccionando sucursal: {e}")
            return False

    # ── Cerrar overlays ────────────────────────────────────────────────────────
    async def _dismiss_overlays(self, page) -> None:
        await page.evaluate("""
            () => {
                document.body.classList.remove('_has-modal');
                document.body.style.overflow = 'auto';
                document.querySelectorAll('.modals-overlay, .modal-popup._show, .modal-slide._show')
                    .forEach(el => { el.style.display = 'none'; el.classList.remove('_show'); });
                const c = document.querySelector('.cookie-message__container');
                if (c) c.style.display = 'none';
            }
        """)
        await asyncio.sleep(0.3)

    # ── Scroll paso a paso para activar lazy loading ──────────────────────────
    async def _scroll_to_load_all(self, page) -> None:
        """
        Scroll paso a paso simulando un usuario real.
        Esto activa el IntersectionObserver que carga los productos lazy.
        """
        scroll_height = await page.evaluate("document.body.scrollHeight")
        step = 250
        for y in range(0, scroll_height + step, step):
            await page.evaluate(f"window.scrollTo(0, {y})")
            await asyncio.sleep(0.08)

        # Esperar que todos los items carguen
        await asyncio.sleep(2)

        # Verificar cuantos items hay ahora
        count_after = await page.evaluate("""
            () => ({
                names: document.querySelectorAll('.product-name').length,
                prices: document.querySelectorAll('span.catalog-grid-price-final').length,
            })
        """)
        logger.info(f"Tras scroll: {count_after['names']} nombres, {count_after['prices']} precios")

        # Volver arriba
        await page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(0.5)

    async def _wait_and_load_products(self, page) -> int:
        """Espera que los precios JS-asíncronos carguen y activa el lazy loading."""
        try:
            await page.wait_for_selector(
                "span.catalog-grid-price-final, span.catalog-grid-price-Crossed",
                timeout=20000,
            )
            logger.info("Precios detectados correctamente")
        except PlaywrightTimeout:
            logger.warning("Timeout esperando precios, continuando...")

        await self._scroll_to_load_all(page)

        count = await page.evaluate(
            "() => document.querySelectorAll('span.catalog-grid-price-final').length"
        )
        return count

    # ── Extraccion de productos (selectores verificados) ──────────────────────
    async def _extract_products_from_page(self, page) -> list:
        """
        Extrae estudios y precios usando selectores CSS verificados en el DOM real.

        El DOM de Chopo tiene nombres y precios en contenedores SEPARADOS:
          .product-name[]              → array de nombres (en orden)
          span.catalog-grid-price-final[]  → array de precios finales (en orden)
          span.catalog-grid-price-Crossed[] → array de precios originales (en orden)

        Se emparejan por índice posicional.
        """
        await self._wait_and_load_products(page)

        products = await page.evaluate(r"""
            () => {
                const items = [];
                const parsePrice = (text) => {
                    if (!text) return null;
                    const m = text.replace(/[$\s]/g,'').match(/[\d,]+\.?\d*/);
                    return m ? parseFloat(m[0].replace(/,/g,'')) : null;
                };

                // Estrategia 1: contenedor .catalog-grid-item (verificado: 29/pagina)
                // Contiene .catalog-grid-name + span.catalog-grid-price-final
                const containers = document.querySelectorAll('.catalog-grid-item');
                containers.forEach(el => {
                    const nameEl  = el.querySelector('.catalog-grid-name, .product-name');
                    const priceEl = el.querySelector('span.catalog-grid-price-final');
                    const crossEl = el.querySelector('span.catalog-grid-price-Crossed');
                    const linkEl  = el.querySelector('a[href]');
                    if (!nameEl) return;
                    const name = nameEl.textContent.trim().replace(/\s+/g,' ');
                    if (!name || name.length < 2) return;
                    items.push({
                        name,
                        price_raw:          priceEl ? priceEl.textContent.trim() : '',
                        price:              parsePrice(priceEl ? priceEl.textContent : ''),
                        price_original_raw: crossEl ? crossEl.textContent.trim() : '',
                        price_original:     parsePrice(crossEl ? crossEl.textContent : ''),
                        url:                linkEl ? linkEl.href : null,
                    });
                });

                if (items.length > 0) return items;

                // Estrategia 2: zip por indice usando .catalog-grid-name y precios
                const nameEls  = Array.from(document.querySelectorAll('.catalog-grid-name'));
                const priceEls = Array.from(document.querySelectorAll('span.catalog-grid-price-final'));
                const crossEls = Array.from(document.querySelectorAll('span.catalog-grid-price-Crossed'));
                const linkEls  = Array.from(document.querySelectorAll('a[href*="/yucatan/"]'));

                for (let i = 0; i < nameEls.length; i++) {
                    const name = nameEls[i].textContent.trim().replace(/\s+/g,' ');
                    if (!name || name.length < 2) continue;
                    items.push({
                        name,
                        price_raw:          priceEls[i] ? priceEls[i].textContent.trim() : '',
                        price:              parsePrice(priceEls[i] ? priceEls[i].textContent : ''),
                        price_original_raw: crossEls[i] ? crossEls[i].textContent.trim() : '',
                        price_original:     parsePrice(crossEls[i] ? crossEls[i].textContent : ''),
                        url:                linkEls[i] ? linkEls[i].href : null,
                    });
                }

                return items;
            }
        """)

        logger.info(
            f"Pagina: {len(products)} estudios | "
            f"Con precio: {sum(1 for p in products if p.get('price'))}"
        )
        return products

    # ── Obtener total de paginas ───────────────────────────────────────────────
    async def _get_total_pages(self, page) -> int:
        """Detecta el numero total de paginas del catalogo."""
        try:
            info = await page.evaluate(r"""
                () => {
                    // Buscar el texto "1 - 30 de 1538" para calcular paginas
                    const toolbar = document.querySelector('.toolbar-amount, .toolbar-number, .pager .toolbar-number');
                    if (toolbar) {
                        const text = toolbar.textContent;
                        const match = text.match(/de\s+([\d,]+)/i) || text.match(/([\d,]+)\s*(?:Total|total)/);
                        if (match) {
                            const total = parseInt(match[1].replace(/,/g, ''));
                            const perPage = 30;
                            return Math.ceil(total / perPage);
                        }
                    }
                    // Buscar numero mas alto en el paginador
                    let maxPage = 1;
                    document.querySelectorAll('.pages a, .pager a, [class*="page"] a').forEach(a => {
                        const n = parseInt(a.textContent.trim());
                        if (!isNaN(n) && n > maxPage) maxPage = n;
                    });
                    return maxPage;
                }
            """)
            logger.info(f"Total de paginas detectadas: {info}")
            return max(info, 1)
        except Exception:
            return 52  # Fallback: 1538 / 30 = ~52 paginas

    # ── Scrape principal ───────────────────────────────────────────────────────
    async def scrape(self) -> list:
        """
        Scrape completo v4:
        1. Carga la pagina
        2. Selecciona Altabrisa via Google Places
        3. Recarga con precios visibles
        4. Scrape paginado por URL (?p=N) hasta completar todos los estudios
        """
        logger.info(
            f"[v4] Scrape | Lab: {self.config['name']} | Sucursal: {self.branch_config['name']}"
        )
        scraped_at = datetime.now().isoformat()

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=self.headless,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled", "--lang=es-MX"],
            )
            context = await browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="es-MX",
                extra_http_headers={"Accept-Language": "es-MX,es;q=0.9"},
            )
            # Solo bloquear imagenes (no JS, no CSS — Magento las necesita)
            await context.route(
                "**/*.{png,jpg,jpeg,gif,webp,avif,woff,woff2,ttf,eot,otf}",
                lambda route: route.abort(),
            )

            page = await context.new_page()

            try:
                # ── 1. Cargar pagina ───────────────────────────────────────────
                logger.info(f"Cargando: {self.config['url']}")
                await page.goto(self.config["url"], wait_until="domcontentloaded", timeout=30000)
                try:
                    await page.wait_for_load_state("networkidle", timeout=12000)
                except PlaywrightTimeout:
                    pass
                await asyncio.sleep(2)

                # ── 2. Seleccionar sucursal Altabrisa ──────────────────────────
                await self._select_branch(page)

                # ── 3. Recargar para que Magento aplique la sucursal ───────────
                logger.info("Recargando pagina con sucursal activa...")
                await page.reload(wait_until="domcontentloaded", timeout=30000)
                try:
                    await page.wait_for_load_state("networkidle", timeout=15000)
                except PlaywrightTimeout:
                    pass
                await asyncio.sleep(3)
                await self._dismiss_overlays(page)

                # ── 4. Obtener total de paginas ────────────────────────────────
                total_pages = await self._get_total_pages(page)
                logger.info(f"Total de paginas: {total_pages} (~{total_pages * 30} estudios)")

                # ── 5. Pagina 1 ────────────────────────────────────────────────
                p1_products = await self._extract_products_from_page(page)
                all_products = list(p1_products)
                logger.info(f"Pagina 1: {len(p1_products)} estudios")
                await self._screenshot(page, "page_1")

                # ── 6. Paginas 2..N via URL ?p=N ──────────────────────────────
                base_url = self.config["url"].rstrip("/")
                max_pages = min(total_pages, 60)  # Limite de seguridad

                for page_num in range(2, max_pages + 1):
                    page_url = f"{base_url}?p={page_num}"
                    logger.info(f"Pagina {page_num}/{max_pages}: {page_url}")

                    try:
                        await page.goto(page_url, wait_until="domcontentloaded", timeout=25000)
                        try:
                            await page.wait_for_load_state("networkidle", timeout=10000)
                        except PlaywrightTimeout:
                            pass
                        await asyncio.sleep(2)
                        await self._dismiss_overlays(page)

                        page_products = await self._extract_products_from_page(page)
                        if not page_products:
                            logger.warning(f"Pagina {page_num}: sin productos. Deteniendo.")
                            break

                        all_products.extend(page_products)
                        logger.info(
                            f"Pagina {page_num}: +{len(page_products)} | "
                            f"Acumulado: {len(all_products)}"
                        )

                        # Rate limiting respetuoso (1-2s entre paginas)
                        await asyncio.sleep(1.5)

                    except Exception as e:
                        logger.error(f"Error en pagina {page_num}: {e}")
                        break

                # ── 7. Deduplicar y enriquecer ─────────────────────────────────
                seen = set()
                enriched = []
                for p in all_products:
                    name = p.get("name", "").strip()
                    if not name or name in seen:
                        continue
                    seen.add(name)
                    enriched.append({
                        "lab_key": self.lab_key,
                        "lab_name": self.config["name"],
                        "city": self.config["city"],
                        "state": self.config["state"],
                        "branch": self.branch_config["name"],
                        "study_name": name,
                        "price": p.get("price"),
                        "price_raw": p.get("price_raw", ""),
                        "price_original": p.get("price_original"),
                        "price_original_raw": p.get("price_original_raw", ""),
                        "url": p.get("url"),
                        "scraped_at": scraped_at,
                    })

                self.results = enriched
                logger.success(
                    f"[COMPLETADO] {len(enriched)} estudios | "
                    f"Con precio: {sum(1 for e in enriched if e.get('price'))}"
                )

            except Exception as e:
                logger.error(f"Error critico: {e}")
                await self._screenshot(page, "error")
                raise
            finally:
                await browser.close()

        return self.results


def run_scrape_sync(
    lab_key: str = "chopo_yucatan",
    branch_key: str = "altabrisa",
    headless: bool = True,
) -> list:
    """Wrapper sincrono para uso desde main.py y scheduler."""
    scraper = ChopoScraper(lab_key=lab_key, branch_key=branch_key, headless=headless)
    return asyncio.run(scraper.scrape())


if __name__ == "__main__":
    import sys
    branch = "altabrisa"
    headless_mode = "--visible" not in sys.argv
    for arg in sys.argv[1:]:
        if not arg.startswith("--"):
            branch = arg
    results = run_scrape_sync(branch_key=branch, headless=headless_mode)
    print(f"\n[RESULTADO] {len(results)} estudios unicos")
    with_price = [r for r in results if r.get("price")]
    print(f"Con precio: {len(with_price)}")
    for r in results[:10]:
        price_str = f"{r['price_raw']} (antes {r.get('price_original_raw','')})" if r.get("price") else "sin precio"
        print(f"  - {r['study_name']}: {price_str}")
