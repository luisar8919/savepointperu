-- El catálogo es público: cualquiera puede LEER productos disponibles,
-- pero solo el backend (service_key) puede escribir.
alter table products enable row level security;

create policy "Lectura pública de productos disponibles"
  on products for select
  using (disponible = true);
