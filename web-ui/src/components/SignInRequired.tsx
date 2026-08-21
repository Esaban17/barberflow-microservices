import Link from "next/link";

/** Muro para las pantallas con JWT: sin sesión no hay nada que mostrar. */
export function SignInRequired() {
  return (
    <p className="rounded-md border border-stone-300 bg-white px-4 py-3 text-sm text-stone-700">
      Necesitas una cuenta para esto.{" "}
      <Link href="/login" className="underline">
        Entra
      </Link>{" "}
      o{" "}
      <Link href="/register" className="underline">
        crea una
      </Link>
      .
    </p>
  );
}
