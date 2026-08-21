#!/bin/bash
# Rol de aplicación de booking-svc con el mínimo privilegio (tarea 14).
#
# Va en un .sh porque el entrypoint de Postgres corre los *.sql con psql SIN -v: un
# `:'variable'` dentro de un .sql rompe el arranque. Aquí sí se puede pasar -v.
#
# El prefijo numérico no es decorativo: los archivos se ejecutan en orden alfabético y
# "init.sh" iría ANTES que "init.sql" ('h' < 'q'), así que el GRANT ... ON ALL TABLES no
# encontraría ninguna tabla. 01-init.sql crea el esquema, 02-init.sh reparte permisos.
set -e

psql -v ON_ERROR_STOP=1 -v pw="$APP_DB_PASSWORD" -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<EOSQL
CREATE ROLE "$APP_DB_USER" LOGIN PASSWORD :'pw';
GRANT CONNECT ON DATABASE "$POSTGRES_DB" TO "$APP_DB_USER";
-- PG16 ya no concede USAGE sobre public de forma implícita.
GRANT USAGE ON SCHEMA public TO "$APP_DB_USER";
-- DML sí; CREATE, ALTER y DROP no: el servicio no puede tocar el esquema.
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "$APP_DB_USER";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "$APP_DB_USER";
EOSQL
