import { supabase } from "@/lib/supabase";

export const dynamic = "force-dynamic"; // el catálogo cambia con cada scrape, no debe quedar cacheado

type Product = {
  id: string;
  titulo: string;
  precio_venta: number;
  moneda: string;
  imagen_url: string | null;
};

const SIMBOLOS: Record<string, string> = { USD: "$", PEN: "S/" };

export default async function Catalogo() {
  const { data: productos, error } = await supabase
    .from("products")
    .select("id, titulo, precio_venta, moneda, imagen_url")
    .eq("disponible", true)
    .returns<Product[]>();

  if (error) console.error("Error consultando products:", error);

  return (
    <main className="max-w-6xl mx-auto px-4 py-8">
      <div className="mb-8">
        <h1 className="text-2xl font-bold">Catálogo</h1>
        <p className="text-sm text-slate-500 mt-1">
          Juegos traídos desde Amazon por encargo. Pago por adelantado, entrega coordinada contigo.
        </p>
      </div>

      {productos && productos.length > 0 ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-5">
          {productos.map((p) => (
            <div
              key={p.id}
              className="group bg-white border border-slate-200 rounded-xl overflow-hidden hover:shadow-lg hover:-translate-y-0.5 transition"
            >
              <div className="aspect-square bg-slate-100 flex items-center justify-center overflow-hidden">
                {p.imagen_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={p.imagen_url}
                    alt={p.titulo}
                    className="w-full h-full object-contain group-hover:scale-105 transition"
                  />
                ) : (
                  <span className="text-4xl">🎮</span>
                )}
              </div>
              <div className="p-3">
                <p className="text-sm text-slate-700 line-clamp-2 min-h-[2.5rem]">{p.titulo}</p>
                <p className="text-lg font-bold mt-1">
                  {SIMBOLOS[p.moneda] ?? p.moneda} {p.precio_venta.toFixed(2)}
                </p>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-center py-20">
          <p className="text-4xl mb-3">🕹️</p>
          <p className="text-slate-500">Sin juegos disponibles por ahora, volvé mañana.</p>
        </div>
      )}
    </main>
  );
}
