"use client";

import Link from "next/link";

import { clearSession } from "@/lib/api";
import { useSession } from "@/lib/useSession";

const LINKS = [
  { href: "/", label: "Inicio" },
  { href: "/book", label: "Reservar" },
  { href: "/appointments", label: "Mis citas" },
  { href: "/status", label: "Estado" },
] as const;

export function SiteHeader() {
  const session = useSession();

  return (
    <header className="border-b border-stone-200 bg-white">
      <div className="mx-auto flex w-full max-w-4xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
        <Link href="/" className="text-lg font-semibold tracking-tight">
          Barber<span className="text-amber-700">Flow</span>
        </Link>
        <nav className="flex gap-4 text-sm text-stone-600">
          {LINKS.map((link) => (
            <Link key={link.href} href={link.href} className="hover:text-stone-900">
              {link.label}
            </Link>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-3 text-sm">
          {session ? (
            <>
              <span className="text-stone-700">{session.user.full_name}</span>
              <button
                type="button"
                onClick={clearSession}
                className="rounded-md border border-stone-300 px-3 py-1 hover:bg-stone-100"
              >
                Salir
              </button>
            </>
          ) : (
            session === null && (
              <>
                <Link href="/login" className="hover:text-stone-900">
                  Entrar
                </Link>
                <Link
                  href="/register"
                  className="rounded-md bg-stone-900 px-3 py-1 text-white hover:bg-stone-700"
                >
                  Crear cuenta
                </Link>
              </>
            )
          )}
        </div>
      </div>
    </header>
  );
}
