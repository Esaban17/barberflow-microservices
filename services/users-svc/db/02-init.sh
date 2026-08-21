#!/bin/sh
# Rol de aplicación de users-svc, con el mínimo privilegio: DML sí, DDL no.
# Va en un .sh y no en un .sql porque el entrypoint de Postgres corre los *.sql
# con psql sin -v, y entonces :'variable' rompería el arranque.
set -e

psql -v ON_ERROR_STOP=1 -v app="$APP_DB_USER" -v pw="$APP_DB_PASSWORD" \
     -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<'EOSQL'
CREATE ROLE :"app" LOGIN PASSWORD :'pw';
-- PG16 ya no concede USAGE sobre public de forma implícita.
GRANT USAGE ON SCHEMA public TO :"app";
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO :"app";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO :"app";
EOSQL
