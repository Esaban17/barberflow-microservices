#!/bin/sh
# Rol de aplicación de menor privilegio para notif-svc: DML sí, DDL no.
#
# Va en un .sh y no en un .sql porque el entrypoint de Postgres ejecuta los *.sql con
# psql sin -v, y ahí un :'variable' rompe el arranque.
#
# El prefijo numérico fija el orden real: el entrypoint expande el glob en orden
# alfabético y "init.sh" iría antes que "init.sql", con lo que el GRANT ... ON ALL
# TABLES no encontraría ninguna tabla. Así 01-init.sql crea y 02-init.sh reparte.
set -e

psql -v ON_ERROR_STOP=1 -v role="$APP_DB_USER" -v pw="$APP_DB_PASSWORD" \
	-U "$POSTGRES_USER" -d "$POSTGRES_DB" <<'EOSQL'
CREATE ROLE :"role" LOGIN PASSWORD :'pw';
GRANT USAGE ON SCHEMA public TO :"role";  -- PG16 ya no lo da implícito
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO :"role";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO :"role";
EOSQL
