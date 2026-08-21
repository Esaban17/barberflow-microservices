-- Esquema de notif_db (tarea 20).
--
-- El entrypoint de Postgres corre este archivo como superusuario, así que la tabla
-- queda a su nombre: el rol de aplicación que crea 02-init.sh recibe DML y nunca
-- podrá hacerle DDL (DROP/ALTER).

CREATE TABLE notifications (
	id             serial PRIMARY KEY,
	-- user_id es un entero suelto, SIN foreign key a propósito: los usuarios viven en
	-- la base de users-svc y este servicio jamás la consulta. Es Database per Service,
	-- no un descuido; la integridad la garantiza quien crea la notificación.
	user_id        integer     NOT NULL,
	channel        text        NOT NULL DEFAULT 'log',
	subject        text        NOT NULL,
	body           text        NOT NULL,
	status         text        NOT NULL DEFAULT 'sent',
	-- Correlation id del request que la originó: es lo que permite seguir el viaje
	-- completo usuario -> booking-svc -> notif-svc en los logs.
	correlation_id text        NULL,
	created_at     timestamptz NOT NULL DEFAULT now()
);

-- El historial siempre se pide así: por usuario y de lo más reciente a lo más viejo.
CREATE INDEX notifications_user_created_idx ON notifications (user_id, created_at DESC);
