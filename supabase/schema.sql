-- Productos detectados/ofrecidos en el catálogo
create table products (
  id uuid primary key default gen_random_uuid(),
  asin text unique not null,
  titulo text not null,
  url_producto text,
  imagen_url text,
  moneda text not null default 'USD', -- la que muestre Amazon según la IP del scraper, sin convertir
  precio_normal numeric,            -- precio de referencia sin descuento
  precio_oferta numeric,            -- último precio visto en Amazon
  precio_venta numeric,             -- precio_normal * 1.3
  disponible boolean default false,
  actualizado_at timestamptz default now()
);

-- Lotes de compra agrupada
create table batches (
  id uuid primary key default gen_random_uuid(),
  estado text not null default 'abierto', -- abierto | esperando_decision | comprado | cerrado
  creado_at timestamptz default now(),
  vence_at timestamptz default now() + interval '7 days'
);

-- Pedidos de clientes
create table orders (
  id uuid primary key default gen_random_uuid(),
  product_id uuid references products(id),
  batch_id uuid references batches(id),
  cliente_email text not null,
  cantidad int not null default 1,
  precio_cobrado_usd numeric not null,
  estado text not null default 'pagado',
  -- pagado | en_lote | comprado | enviado | entregado | cancelado_reembolsado
  fecha_entrega_estimada date,
  creado_at timestamptz default now()
);

-- Compra real hecha en Amazon por lote
create table amazon_purchases (
  id uuid primary key default gen_random_uuid(),
  batch_id uuid references batches(id),
  fecha_compra timestamptz default now(),
  fecha_entrega_estimada_amazon date,
  tracking_url text
);
