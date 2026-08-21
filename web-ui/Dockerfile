# ─────────────────────────────────────────────────────────────────────────────
# web-ui — Next.js en modo standalone.
# Multi-stage: las dependencias de build no llegan a la imagen final, que solo
# lleva el servidor compilado y corre como usuario sin privilegios.
# ─────────────────────────────────────────────────────────────────────────────
FROM node:24-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
# `npm ci` respeta el lockfile: el build es reproducible.
RUN npm ci

FROM node:24-alpine AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:24-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
# El usuario `node` (uid 1000) ya viene en la imagen base: nada corre como root.
COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static
USER node
EXPOSE 3000
CMD ["node", "server.js"]
