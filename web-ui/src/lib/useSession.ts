"use client";

import { useEffect, useState } from "react";

import { SESSION_EVENT, getSession, type Session } from "./api";

/**
 * Sesión guardada en el navegador, re-leída en cada login/logout (incluso desde
 * otra pestaña). Devuelve `undefined` mientras no se ha montado el componente,
 * para no parpadear un "inicia sesión" a quien sí la tiene.
 */
export function useSession(): Session | null | undefined {
  const [session, setSession] = useState<Session | null | undefined>(undefined);

  useEffect(() => {
    const sync = () => setSession(getSession());
    sync();
    window.addEventListener(SESSION_EVENT, sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(SESSION_EVENT, sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  return session;
}
