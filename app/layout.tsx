import "./globals.css";

export const metadata = { title: "SavePoint Perú" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body className="bg-slate-50 text-slate-900 min-h-screen flex flex-col">
        <header className="border-b bg-white">
          <div className="max-w-6xl mx-auto px-4 py-4 flex items-center gap-2">
            <span className="text-xl">🎮</span>
            <span className="text-lg font-bold tracking-tight">SavePoint Perú</span>
          </div>
        </header>
        <div className="flex-1">{children}</div>
        <footer className="border-t bg-white mt-12">
          <div className="max-w-6xl mx-auto px-4 py-6 text-sm text-slate-500">
            Pago por adelantado · Entrega coordinada manualmente
          </div>
        </footer>
      </body>
    </html>
  );
}
