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

URLS_OBJETIVO = [
    "https://www.amazon.com/deals?deals-widget=%7B%22version%22%3A1%2C%22browseNodeId%22%3A%22468642%22%7D",
    "https://www.amazon.com/s?i=videogames&bbn=468642&rh=n%3A468642%2Cp_n_deal_type%3A23566065011&dc",
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


async def scrapear_pagina_resultados(page, url: str) -> list[dict]:
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

            if not precio_original:
                # sin precio de referencia no podemos calcular precio_venta
                continue

            descuento_num = calcular_descuento(precio_original, precio_actual)
            if not descuento_num or descuento_num < DESCUENTO_MINIMO:
                continue

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

    return ofertas


async def scrapear_multiples_paginas(page, url_base: str, max_paginas: int = 3) -> list[dict]:
    todas = []
    for n_pagina in range(1, max_paginas + 1):
        url = f"{url_base}&page={n_pagina}" if n_pagina > 1 else url_base
        resultado = await scrapear_pagina_resultados(page, url)
        todas.extend(resultado)
        if not resultado:
            break
        await asyncio.sleep(random.uniform(3, 6))
    return todas


async def scrapear_ofertas() -> list[dict]:
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
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
            window.chrome = { runtime: {} };
        """)
        page = await context.new_page()

        for url in URLS_OBJETIVO:
            ofertas = await scrapear_multiples_paginas(page, url, max_paginas=3)
            todas_las_ofertas.extend(ofertas)
            await asyncio.sleep(random.uniform(4, 7))

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
