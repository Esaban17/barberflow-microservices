"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert } from "@/components/Alert";
import {
  api,
  errorMessage,
  saveSession,
  type LoginResponse,
  type User,
} from "@/lib/api";

export default function RegisterPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSending(true);
    const form = new FormData(event.currentTarget);
    const email = form.get("email");
    const password = form.get("password");
    try {
      await api<User>("/api/users/register", {
        method: "POST",
        body: JSON.stringify({
          email,
          password,
          full_name: form.get("full_name"),
          phone: form.get("phone") || undefined,
        }),
      });
      // Entrar de una vez: el usuario recién creado no debería teclear lo mismo otra vez.
      const login = await api<LoginResponse>("/api/users/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      saveSession({ token: login.access_token, user: login.user });
      router.push("/book");
    } catch (caught) {
      setError(
        errorMessage(caught, {
          409: "Ese correo ya tiene cuenta. Entra en su lugar.",
          422: "Revisa los datos: el correo debe ser válido y la contraseña de 8 a 72 caracteres.",
        }),
      );
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="mx-auto max-w-sm space-y-6">
      <h1 className="text-2xl font-semibold">Crear cuenta</h1>
      <form onSubmit={onSubmit} className="space-y-4">
        {error && <Alert>{error}</Alert>}
        <label className="block space-y-1">
          <span className="text-sm text-stone-600">Nombre completo</span>
          <input
            name="full_name"
            required
            autoComplete="name"
            className="w-full rounded-md border border-stone-300 bg-white px-3 py-2"
          />
        </label>
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
          <span className="text-sm text-stone-600">Teléfono (opcional)</span>
          <input
            name="phone"
            type="tel"
            autoComplete="tel"
            placeholder="+502 5555-1234"
            className="w-full rounded-md border border-stone-300 bg-white px-3 py-2"
          />
        </label>
        <label className="block space-y-1">
          <span className="text-sm text-stone-600">Contraseña</span>
          <input
            name="password"
            type="password"
            required
            minLength={8}
            maxLength={72}
            autoComplete="new-password"
            className="w-full rounded-md border border-stone-300 bg-white px-3 py-2"
          />
        </label>
        <button
          type="submit"
          disabled={sending}
          className="w-full rounded-md bg-stone-900 px-4 py-2 text-white hover:bg-stone-700 disabled:opacity-50"
        >
          {sending ? "Creando…" : "Crear cuenta"}
        </button>
        <p className="text-sm text-stone-600">
          ¿Ya tienes cuenta?{" "}
          <Link href="/login" className="underline">
            Entra aquí
          </Link>
          .
        </p>
      </form>
    </div>
  );
}
