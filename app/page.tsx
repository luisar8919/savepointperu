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
    <main className="max-w-5xl mx-auto p-6">
      <h1 className="text-2xl font-bold mb-6">Catálogo</h1>
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
        {(productos ?? []).map((p) => (
          <div key={p.id} className="border rounded-lg p-3">
            {p.imagen_url && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={p.imagen_url} alt={p.titulo} className="w-full h-32 object-contain mb-2" />
            )}
            <p className="text-sm font-medium">{p.titulo}</p>
            <p className="text-lg font-bold">
              {SIMBOLOS[p.moneda] ?? p.moneda} {p.precio_venta.toFixed(2)}
            </p>
          </div>
        ))}
        {(!productos || productos.length === 0) && (
          <p className="col-span-full text-gray-500">Sin juegos disponibles por ahora.</p>
        )}
      </div>
    </main>
  );
}
