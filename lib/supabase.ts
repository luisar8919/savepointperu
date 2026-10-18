import { createClient } from "@supabase/supabase-js";

export const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
  {
    global: {
      // el catálogo cambia seguido (scraper diario + pedidos); Next.js cachea
      // fetch() por defecto y servía resultados viejos sin esto
      fetch: (url, options) => fetch(url, { ...options, cache: "no-store" }),
    },
  }
);
