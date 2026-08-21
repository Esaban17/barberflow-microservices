-- Esquema y semilla de booking_db (tarea 14).
--
-- DATABASE PER SERVICE: `appointments.user_id` es un entero suelto y a propósito NO
-- tiene foreign key. Los usuarios viven en users_db, que es de users-svc, y booking-svc
-- jamás la consulta: para saber si el usuario existe llama a `GET /users/{id}` por HTTP.
--
-- El rol de aplicación se crea en 02-init.sh, no aquí: el entrypoint de Postgres corre
-- los *.sql con psql sin -v y un `:'variable'` reventaría el arranque.

CREATE TABLE services (
	id           serial PRIMARY KEY,
	name         text NOT NULL,
	duration_min int NOT NULL,
	price        numeric(10,2) NOT NULL
);

CREATE TABLE barbers (
	id    serial PRIMARY KEY,
	name  text NOT NULL,
	chair int NOT NULL UNIQUE
);

CREATE TABLE slots (
	id         serial PRIMARY KEY,
	barber_id  int NOT NULL REFERENCES barbers(id),
	service_id int NOT NULL REFERENCES services(id),
	starts_at  timestamptz NOT NULL,
	is_booked  boolean NOT NULL DEFAULT false,
	-- Un barbero no puede tener dos citas a la misma hora.
	UNIQUE (barber_id, starts_at)
);

CREATE INDEX slots_free_idx ON slots (starts_at) WHERE NOT is_booked;

CREATE TABLE appointments (
	id           serial PRIMARY KEY,
	user_id      int NOT NULL,  -- sin FK: vive en la base de otro servicio (ver cabecera)
	slot_id      int NOT NULL REFERENCES slots(id),
	status       text NOT NULL CHECK (status IN ('confirmed', 'cancelled')),
	created_at   timestamptz NOT NULL DEFAULT now(),
	cancelled_at timestamptz
);

CREATE INDEX appointments_user_idx ON appointments (user_id, created_at DESC);

-- Único PARCIAL, no único a secas: lo que hay que impedir es que dos citas CONFIRMADAS
-- compartan horario. Con un UNIQUE sobre la columna, la fila de una cita cancelada
-- (que no se borra) bloquearía para siempre ese horario, y /slots lo seguiría
-- ofreciendo: la web mostraría un horario libre que devuelve 409 al reservarlo.
CREATE UNIQUE INDEX appointments_slot_confirmed_idx
	ON appointments (slot_id) WHERE status = 'confirmed';

CREATE TABLE outbox (
	id             serial PRIMARY KEY,
	appointment_id int NOT NULL REFERENCES appointments(id),
	payload        jsonb NOT NULL,
	status         text NOT NULL CHECK (status IN ('pending', 'sent')),
	attempts       int NOT NULL DEFAULT 0,
	last_error     text,
	created_at     timestamptz NOT NULL DEFAULT now(),
	sent_at        timestamptz
);

CREATE INDEX outbox_pending_idx ON outbox (id) WHERE status = 'pending';

INSERT INTO services (name, duration_min, price) VALUES
	('Corte clásico',      30,  75.00),
	('Corte + barba',      45, 120.00),
	('Afeitado clásico',   30,  65.00),
	('Tinte',              60, 180.00),
	('Perfilado de cejas', 15,  40.00);

INSERT INTO barbers (name, chair) VALUES
	('Marco Ruiz',    1),
	('Diego Cabrera', 2),
	('Luis Herrera',  3);

-- Agenda de los próximos 7 días, de 09:00 a 18:00 UTC, una cita por hora y silla.
-- El servicio rota con la hora, el barbero y el día para que todos los días haya
-- oferta variada sin tener que escribir el producto cartesiano completo.
INSERT INTO slots (barber_id, service_id, starts_at)
SELECT b.id,
       ((h + b.id + d) % 5) + 1,
       (CURRENT_DATE + d + make_interval(hours => h)) AT TIME ZONE 'UTC'
FROM barbers b,
     generate_series(1, 7) AS d,
     generate_series(9, 17) AS h;
