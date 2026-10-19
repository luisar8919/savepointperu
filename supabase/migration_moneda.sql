-- Ya no convertimos a USD: guardamos el precio tal cual lo muestra Amazon
-- (según la IP del scraper, puede venir en PEN o en USD) junto con su moneda.
alter table products rename column precio_normal_usd to precio_normal;
alter table products rename column precio_oferta_usd to precio_oferta;
alter table products rename column precio_venta_usd to precio_venta;

alter table products add column moneda text not null default 'USD';
