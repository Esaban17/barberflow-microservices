# Imagen de Postgres para Railway (tarea 41): local usa `image: postgres:16-alpine`
# con `./db:/docker-entrypoint-initdb.d:ro` montado por bind-mount (ver
# docker-compose.yml, x-db-common). Railway no soporta bind-mounts de archivos del
# repo hacia un volumen del contenedor en runtime, así que aquí se copian los mismos
# 01-init.sql/02-init.sh DENTRO de la imagen en tiempo de build — el entrypoint
# oficial de postgres los sigue ejecutando igual, en el mismo orden alfabético.
FROM postgres:16-alpine
COPY . /docker-entrypoint-initdb.d/
