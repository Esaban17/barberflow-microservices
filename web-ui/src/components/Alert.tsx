const TONES = {
  error: "border-red-300 bg-red-50 text-red-800",
  warning: "border-amber-300 bg-amber-50 text-amber-900",
  success: "border-emerald-300 bg-emerald-50 text-emerald-900",
} as const;

/** Aviso corto y visible: errores del BFF, notificación pendiente, confirmaciones. */
export function Alert({
  tone = "error",
  children,
}: {
  tone?: keyof typeof TONES;
  children: React.ReactNode;
}) {
  return (
    <p role="status" className={`rounded-md border px-3 py-2 text-sm ${TONES[tone]}`}>
      {children}
    </p>
  );
}
