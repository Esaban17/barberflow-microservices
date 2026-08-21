// Formato local: quetzales y fechas de Guatemala. Se fija la zona horaria a
// propósito para que servidor y navegador rendericen lo mismo.

const TIME_ZONE = "America/Guatemala";

const dateTime = new Intl.DateTimeFormat("es-GT", {
  weekday: "long",
  day: "numeric",
  month: "long",
  hour: "numeric",
  minute: "2-digit",
  timeZone: TIME_ZONE,
});

const time = new Intl.DateTimeFormat("es-GT", {
  hour: "numeric",
  minute: "2-digit",
  timeZone: TIME_ZONE,
});

/** Precio en quetzales: 75 -> "Q75.00". */
export function quetzales(price: number | string): string {
  return `Q${Number(price).toFixed(2)}`;
}

/** ISO-8601 UTC -> "sábado, 22 de agosto, 9:00 a.m." */
export function formatDateTime(isoUtc: string): string {
  return dateTime.format(new Date(isoUtc));
}

/** ISO-8601 UTC -> "9:00 a.m." */
export function formatTime(isoUtc: string): string {
  return time.format(new Date(isoUtc));
}

/** Fecha de hoy en Guatemala como YYYY-MM-DD, para el <input type="date">. */
export function todayInGuatemala(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: TIME_ZONE }).format(new Date());
}
