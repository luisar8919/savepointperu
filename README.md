# TiendaJuegos

Reventa de videojuegos: catálogo web + detección diaria de ofertas en Amazon +
compra/entrega manual.

## Reglas de negocio

- Precio de venta = lo que realmente pagás en Amazon (precio de oferta) × 1.3
  — margen fijo de 30% sobre tu costo real, sin convertir moneda (se muestra
  tal cual Amazon la dé, USD o PEN).
- Solo se guardan ofertas con 20% de descuento o más (`DESCUENTO_MINIMO` en
  `scraper/scrape.py`), ordenadas de mejor a peor.
- Los pedidos pagados se agrupan en lotes hasta llegar a envío gratis + $50 en Amazon.
- Si un lote no se completa en 7 días, el sistema avisa y la decisión (comprar
  suelto / seguir esperando / reembolsar) la tomás vos, caso por caso.
- La compra real en Amazon siempre la confirmás a mano, nunca se dispara sola.
- Entrega estimada = fecha de Amazon + 5 días. Si se pasa, se habilita cancelar/reembolsar.

## Estructura

- `app/` — catálogo web (Next.js + Tailwind).
- `lib/supabase.ts` — cliente de Supabase para el frontend.
- `supabase/schema.sql` — tablas: products, batches, orders, amazon_purchases.
- `scraper/scrape.py` — scraper de ofertas (basado en `../Scrapper_Amazon/Amazon.py`),
  calcula precio de venta, guarda en Supabase y avisa por Telegram.
- `.github/workflows/scrape.yml` — corre el scraper todos los días a las 7am UTC
  + un retraso aleatorio de hasta 60 min.

## Setup

1. Crear proyecto gratis en [supabase.com](https://supabase.com), correr
   `supabase/schema.sql` en el SQL editor.
2. Copiar `.env.example` a `.env.local`, completar con las claves de Supabase.
3. Crear un bot de Telegram con [@BotFather](https://t.me/BotFather), obtener
   `TELEGRAM_BOT_TOKEN`, y tu `TELEGRAM_CHAT_ID` (hablale al bot y consultá
   `https://api.telegram.org/bot<token>/getUpdates`).
4. En GitHub, subir estos 4 valores + los de Supabase (con la service key, no
   la anon key) como *Secrets* del repo, para que el workflow los use.
5. `npm install && npm run dev` para probar el catálogo localmente.
6. Deploy del frontend en Vercel (plan gratis), conectando las mismas env vars.

## Costo

$0/mes usando Vercel Hobby + Supabase free tier + GitHub Actions + Telegram.
Único costo opcional: dominio propio (~$1/mes amortizado).
