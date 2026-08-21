import { NextResponse, type NextRequest } from "next/server";

import { ServiceUnavailable, callService } from "./consul";

/**
 * Fábrica de route handlers del BFF: el navegador llama a `/api/<área>/<lo que sea>`
 * y Next reenvía la petición al microservicio, resolviéndolo antes en Consul.
 *
 * Lo que se propaga hacia el servicio destino:
 *  - `Authorization`: el JWT tal cual lo manda el navegador.
 *  - `x-correlation-id`: el del navegador si viene; si no, uno nuevo. Es lo que
 *    permite seguir un request por los tres servicios en los logs.
 */
export function proxyTo(service: string) {
  return async function handler(
    request: NextRequest,
    context: { params: Promise<{ path: string[] }> },
  ): Promise<NextResponse> {
    const { path } = await context.params;
    const correlationId = request.headers.get("x-correlation-id") ?? crypto.randomUUID();

    const headers = new Headers({
      "x-correlation-id": correlationId,
      accept: "application/json",
    });
    const authorization = request.headers.get("authorization");
    if (authorization) headers.set("authorization", authorization);
    const contentType = request.headers.get("content-type");
    if (contentType) headers.set("content-type", contentType);

    const hasBody = request.method !== "GET" && request.method !== "HEAD";
    const body = hasBody ? await request.text() : undefined;

    try {
      const upstream = await callService(
        service,
        `/${path.join("/")}${request.nextUrl.search}`,
        { method: request.method, headers, body },
      );
      const payload = await upstream.text();
      // Solo se reenvía `content-type`. Copiar `content-length`/`content-encoding`
      // del upstream corrompería la respuesta: el cuerpo ya viene descomprimido.
      return new NextResponse(payload, {
        status: upstream.status,
        headers: {
          "content-type": upstream.headers.get("content-type") ?? "application/json",
          "x-correlation-id": correlationId,
        },
      });
    } catch (error) {
      if (error instanceof ServiceUnavailable) {
        // Caso normal cuando un servicio se cae: Consul devuelve lista vacía.
        return NextResponse.json(
          { detail: `${service} no disponible` },
          { status: 503, headers: { "x-correlation-id": correlationId } },
        );
      }
      // Cualquier otro fallo tampoco puede salir como excepción sin manejar.
      return NextResponse.json(
        { detail: `no se pudo contactar a ${service}` },
        { status: 502, headers: { "x-correlation-id": correlationId } },
      );
    }
  };
}
