"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { Alert } from "@/components/Alert";
import { api, errorMessage, saveSession, type LoginResponse } from "@/lib/api";

function LoginForm() {
  const router = useRouter();
  const expired = useSearchParams().get("vencida") === "1";
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSending(true);
    const form = new FormData(event.currentTarget);
    try {
      const login = await api<LoginResponse>("/api/users/login", {
        method: "POST",
        body: JSON.stringify({
          email: form.get("email"),
          password: form.get("password"),
        }),
      });
      saveSession({ token: login.access_token, user: login.user });
      router.push("/book");
    } catch (caught) {
      setError(
        errorMessage(caught, { 401: "Correo o contraseña incorrectos." }),
      );
    } finally {
      setSending(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      {expired && !error && <Alert tone="warning">Tu sesión venció, entra de nuevo.</Alert>}
      {error && <Alert>{error}</Alert>}
      <label className="block space-y-1">
        <span className="text-sm text-stone-600">Correo</span>
        <input
          name="email"
          type="email"
          required
          autoComplete="email"
          className="w-full rounded-md border border-stone-300 bg-white px-3 py-2"
        />
      </label>
      <label className="block space-y-1">
        <span className="text-sm text-stone-600">Contraseña</span>
        <input
          name="password"
          type="password"
          required
          autoComplete="current-password"
          className="w-full rounded-md border border-stone-300 bg-white px-3 py-2"
        />
      </label>
      <button
        type="submit"
        disabled={sending}
        className="w-full rounded-md bg-stone-900 px-4 py-2 text-white hover:bg-stone-700 disabled:opacity-50"
      >
        {sending ? "Entrando…" : "Entrar"}
      </button>
      <p className="text-sm text-stone-600">
        ¿No tienes cuenta?{" "}
        <Link href="/register" className="underline">
          Créala aquí
        </Link>
        .
      </p>
    </form>
  );
}

export default function LoginPage() {
  return (
    <div className="mx-auto max-w-sm space-y-6">
      <h1 className="text-2xl font-semibold">Entrar</h1>
      {/* useSearchParams obliga a un límite de Suspense en el App Router. */}
      <Suspense fallback={<p className="text-sm text-stone-500">Cargando…</p>}>
        <LoginForm />
      </Suspense>
    </div>
  );
}
