import type { Metadata } from "next";

import { SiteHeader } from "@/components/SiteHeader";

import "./globals.css";

export const metadata: Metadata = {
  title: "BarberFlow — Reservas de barbería",
  description: "Reserva tu corte con los barberos de BarberFlow.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="es" className="h-full antialiased">
      <body className="flex min-h-full flex-col">
        <SiteHeader />
        <main className="mx-auto w-full max-w-4xl flex-1 px-4 py-8">{children}</main>
        <footer className="border-t border-stone-200 px-4 py-4 text-center text-xs text-stone-500">
          BarberFlow · Universidad Galileo · Arquitectura de Componentes y Microservicios
        </footer>
      </body>
    </html>
  );
}
