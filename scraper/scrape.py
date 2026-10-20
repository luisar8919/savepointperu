"""
Scraper diario de ofertas de videojuegos en Amazon.
Basado en C:\\Proyectos\\Scrapper_Amazon\\Amazon.py (reusado tal cual para la
extracción), agrega: cálculo de precio de venta, guardado en Supabase y
aviso por Telegram.

Variables de entorno requeridas (ver .env.example):
  SUPABASE_URL, SUPABASE_SERVICE_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""
import asyncio
import os
import random
import re
import sys
from datetime import datetime

import requests
from playwright.async_api import async_playwright

MARGEN = 1.3  # precio_venta = precio_oferta (lo que de verdad pagás) * MARGEN
DESCUENTO_MINIMO = 20  # % — por debajo de esto no vale la pena mostrarlo como "oferta"
PRECIO_MAX_BARATOS_USD = 35  # para la sección "baratos", sin importar descuento
ESPERA_ENTRE_BUSQUEDAS_SEG = (10, 20)  # pausa aleatoria entre cada búsqueda/página

_FILTRO_PRECIO = f"p_36%3A-{int(PRECIO_MAX_BARATOS_USD * 100)}"  # rh de Amazon, precio en centavos

# Cada tarea: (nombre, url, requiere_descuento). El orden en que se corren se
# mezcla al azar en cada corrida (ver scrapear_ofertas).
TAREAS = [
    ("Ofertas (deals)", "https://www.amazon.com/deals?deals-widget=%7B%22version%22%3A1%2C%22browseNodeId%22%3A%22468642%22%7D", True),
    ("Ofertas (búsqueda)", "https://www.amazon.com/s?i=videogames&bbn=468642&rh=n%3A468642%2Cp_n_deal_type%3A23566065011&dc", True),
    # rh=p_36 es el filtro de precio real de Amazon (lo encontró el usuario
    # probando en el propio sitio) -> mucho más confiable que cortar nosotros
    # mismos al escanear tarjetas. Para PS5 usamos el nodo "Juegos de
    # PlayStation 5" (20972797011), más limpio que una palabra clave; para el
    # resto no encontramos el nodo específico todavía, así que es búsqueda +
    # filtro de precio (algo de ruido de accesorios se cuela igual, se filtra
    # con keywords_accesorios más abajo).
    ("PS5 baratos", f"https://www.amazon.com/s?i=videogames&rh=n%3A20972797011%2C{_FILTRO_PRECIO}&s=price-asc-rank", False),
    ("PS4 baratos", f"https://www.amazon.com/s?k=ps4+games&i=videogames&rh={_FILTRO_PRECIO}&s=price-asc-rank", False),
    ("Switch 2 baratos", f"https://www.amazon.com/s?k=nintendo+switch+2+games&i=videogames&rh={_FILTRO_PRECIO}&s=price-asc-rank", False),
    ("Switch baratos", f"https://www.amazon.com/s?k=nintendo+switch+games&i=videogames&rh={_FILTRO_PRECIO}&s=price-asc-rank", False),
]

HEADERS_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]


def limpiar_precio(texto: str) -> float | None:
    if not texto:
        return None
    numeros = re.sub(r"[^\d.]", "", texto.replace(",", ""))
    try:
        return float(numeros)
    except ValueError:
        return None


def detectar_moneda(texto: str | None) -> str:
    """Amazon muestra precios en la moneda local según la IP (acá, PEN),
    aunque la URL sea amazon.com. No convertimos: guardamos el precio tal
    cual lo vas a pagar, junto con en qué moneda está."""
    if texto and "PEN" in texto.upper():
        return "PEN"
    return "USD"


def calcular_descuento(precio_original, precio_actual):
    if precio_original and precio_actual and precio_original > precio_actual:
        return round((1 - precio_actual / precio_original) * 100)
    return None


def obtener_tasa_pen_a_usd() -> float:
    """Solo para decidir si un precio en soles entra en el tope de $20 de la
    sección "baratos" -> nunca se usa para convertir lo que se guarda o se
    muestra (eso sigue siendo tal cual lo da Amazon)."""
    try:
        r = requests.get("https://open.er-api.com/v6/latest/PEN", timeout=10)
        r.raise_for_status()
        return r.json()["rates"]["USD"]
    except Exception as e:
        print(f"No se pudo obtener tasa PEN->USD, uso 0.27 por defecto: {e}")
        return 0.27


async def scrapear_pagina_resultados(
    page, url: str, requiere_descuento: bool = True, tasa_pen_usd: float = 0.27
) -> list[dict]:
    ofertas = []
    print(f"Navegando a: {url}")
    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(random.randint(2000, 3500))

    for _ in range(5):
        await page.evaluate("window.scrollBy(0, document.body.scrollHeight / 5)")
        await page.wait_for_timeout(random.randint(500, 900))

    contenido = await page.content()
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(contenido, "html.parser")

    tarjetas = soup.select(
        "div[data-component-type='s-search-result'], "
        "div.s-result-item[data-asin]:not([data-asin=''])"
    )
    print(f"Tarjetas encontradas: {len(tarjetas)}")
    agoto_pagina = True

    keywords_juegos = ["game", "games", "ps4", "ps5", "xbox", "nintendo",
                        "switch", "playstation", "edition", "collection", "bundle"]
    # ponytail: filtro por palabras clave en el título, no por categoría real de
    # Amazon -> deja pasar falsos positivos (libros, alfombras gamer, handhelds).
    # Si el ruido molesta, subir a PA-API (trae categoría exacta) o revisar a mano
    # antes de que el pedido se marque "disponible".
    keywords_accesorios = [
        "keyboard", "headset", "headphone", "controller", "charger", "charging",
        "cable", "case", "skin", "cooling", "cooler", "stand", "shelf", "rack",
        "dock", "adapter", "cord", "mouse", "joystick", "mount", "grip",
        "screen protector", "sd card", "memory card", "backpack", "bag", "cover",
    ]

    for tarjeta in tarjetas:
        try:
            asin = tarjeta.get("data-asin", "").strip()
            if not asin:
                continue

            titulo_el = (
                tarjeta.select_one("h2 a span") or
                tarjeta.select_one(".a-size-medium.a-color-base.a-text-normal") or
                tarjeta.select_one("h2 span")
            )
            titulo = titulo_el.get_text(strip=True) if titulo_el else None
            if not titulo:
                continue
            titulo_lower = titulo.lower()
            if not any(kw in titulo_lower for kw in keywords_juegos):
                continue
            if any(kw in titulo_lower for kw in keywords_accesorios):
                continue

            link_el = tarjeta.select_one("h2 a")
            url_producto = (
                "https://www.amazon.com" + link_el["href"]
                if link_el and link_el.get("href", "").startswith("/")
                else (link_el["href"] if link_el else None)
            )

            precio_el = (
                tarjeta.select_one(".a-price .a-offscreen") or
                tarjeta.select_one("span.a-price-whole")
            )
            precio_actual_txt = precio_el.get_text(strip=True) if precio_el else None
            precio_actual = limpiar_precio(precio_actual_txt)
            moneda = detectar_moneda(precio_actual_txt)

            precio_original_el = (
                tarjeta.select_one(".a-price.a-text-price .a-offscreen") or
                tarjeta.select_one("span.a-text-price .a-offscreen")
            )
            precio_original_txt = precio_original_el.get_text(strip=True) if precio_original_el else None
            precio_original = limpiar_precio(precio_original_txt)

            if requiere_descuento:
                if not precio_original:
                    # sin precio de referencia no podemos calcular el % de descuento
                    continue
                descuento_num = calcular_descuento(precio_original, precio_actual)
                if not descuento_num or descuento_num < DESCUENTO_MINIMO:
                    continue
            else:
                # sección "menos de $20": no exige descuento, solo tope de precio.
                # Como la página viene ordenada de más barato a más caro, en
                # cuanto se pasa del tope ya no hace falta seguir revisando.
                if precio_actual is None:
                    continue
                precio_usd_equiv = precio_actual * tasa_pen_usd if moneda == "PEN" else precio_actual
                if precio_usd_equiv > PRECIO_MAX_BARATOS_USD:
                    agoto_pagina = False
                    break
                precio_original = precio_original or precio_actual
                descuento_num = calcular_descuento(precio_original, precio_actual) or 0

            img_el = tarjeta.select_one("img.s-image")
            imagen_url = img_el["src"] if img_el and img_el.get("src") else None

            ofertas.append({
                "asin": asin,
                "titulo": titulo,
                "url_producto": url_producto,
                "imagen_url": imagen_url,
                "moneda": moneda,
                "precio_normal": precio_original,
                "precio_oferta": precio_actual,
                "precio_venta": round(precio_actual * MARGEN, 2),
                "descuento_pct": descuento_num,  # no se guarda en Supabase, solo para ordenar/avisar
                "disponible": True,
                "actualizado_at": datetime.now().isoformat(),
            })
        except Exception as e:
            print(f"Error en tarjeta: {e}")
            continue

    return ofertas, agoto_pagina


async def ejecutar_tarea(page, nombre: str, url: str, requiere_descuento: bool, tasa_pen_usd: float) -> list[dict]:
    """Pagina una búsqueda hasta 3 páginas, o hasta que no haya más resultados,
    o (en modo "barato") hasta que el precio se pase del tope."""
    todas = []
    for n_pagina in range(1, 4):
        url_pag = f"{url}&page={n_pagina}" if n_pagina > 1 else url
        resultado, agoto_pagina = await scrapear_pagina_resultados(
            page, url_pag, requiere_descuento=requiere_descuento, tasa_pen_usd=tasa_pen_usd
        )
        todas.extend(resultado)
        if not resultado:
            break
        await asyncio.sleep(random.uniform(*ESPERA_ENTRE_BUSQUEDAS_SEG))
        if not agoto_pagina:
            break  # modo "barato": ya se pasó del tope de precio
    if not requiere_descuento:
        print(f"{nombre}: {len(todas)} juegos bajo ${PRECIO_MAX_BARATOS_USD}")
    return todas


async def scrapear_ofertas() -> list[dict]:
    tasa_pen_usd = obtener_tasa_pen_a_usd()
    todas_las_ofertas = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled", "--disable-infobars"],
        )
        context = await browser.new_context(
            user_agent=random.choice(HEADERS_POOL),
            viewport={"width": 1366, "height": 768},
            locale="en-US",
            timezone_id="America/New_York",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        # Sin esto Amazon muestra PEN (u otra moneda local) según la IP, aunque
        # la URL sea amazon.com. Este cookie fuerza USD de forma confiable.
        await context.add_cookies([{"name": "i18n-prefs", "value": "USD", "domain": ".amazon.com", "path": "/"}])
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
            window.chrome = { runtime: {} };
        """)
        page = await context.new_page()

        tareas = TAREAS.copy()
        random.shuffle(tareas)
        for i, (nombre, url, requiere_descuento) in enumerate(tareas):
            todas_las_ofertas.extend(
                await ejecutar_tarea(page, nombre, url, requiere_descuento, tasa_pen_usd)
            )
            if i < len(tareas) - 1:
                await asyncio.sleep(random.uniform(*ESPERA_ENTRE_BUSQUEDAS_SEG))

        await browser.close()

    vistos = set()
    unicas = []
    for o in todas_las_ofertas:
        if o["asin"] not in vistos:
            vistos.add(o["asin"])
            unicas.append(o)
    unicas.sort(key=lambda o: o["descuento_pct"], reverse=True)
    return unicas


def guardar_en_supabase(ofertas: list[dict]) -> None:
    url = os.environ["SUPABASE_URL"].rstrip("/") + "/rest/v1/products"
    headers = {
        "apikey": os.environ["SUPABASE_SERVICE_KEY"],
        "Authorization": f"Bearer {os.environ['SUPABASE_SERVICE_KEY']}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }
    filas = [{k: v for k, v in o.items() if k != "descuento_pct"} for o in ofertas]
    resp = requests.post(f"{url}?on_conflict=asin", json=filas, headers=headers, timeout=30)
    resp.raise_for_status()


def avisar_telegram(mensaje: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("Telegram no configurado, se omite aviso.")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": mensaje}, timeout=15)


def main():
    try:
        ofertas = asyncio.run(scrapear_ofertas())
    except Exception as e:
        avisar_telegram(f"⚠️ Scraper falló: {e}")
        print(f"Error fatal: {e}", file=sys.stderr)
        sys.exit(1)

    if not ofertas:
        avisar_telegram("ℹ️ Scraper corrió, sin ofertas nuevas encontradas.")
        return

    guardar_en_supabase(ofertas)

    top = ofertas[:5]  # ya vienen ordenadas por % de descuento, de mayor a menor
    lineas = [f"🎮 {len(ofertas)} ofertas (≥{DESCUENTO_MINIMO}% off) encontradas hoy:"]
    for o in top:
        lineas.append(f"- {o['titulo'][:50]} (-{o['descuento_pct']}%) → venta {o['moneda']} {o['precio_venta']} (compra {o['moneda']} {o['precio_oferta']})")
    avisar_telegram("\n".join(lineas))


if __name__ == "__main__":
    main()
