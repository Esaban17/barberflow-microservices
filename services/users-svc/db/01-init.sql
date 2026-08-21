-- Esquema y semilla de users_db. El entrypoint de Postgres lo ejecuta como
-- superusuario, y con el prefijo numérico corre antes que 02-init.sh: sin él el
-- glob alfabético pondría "init.sh" antes que "init.sql" ('h' < 'q') y los GRANT
-- se aplicarían sobre una base todavía sin tablas.

-- citext: el email es único sin distinguir mayúsculas, y lo resuelve la BD.
CREATE EXTENSION IF NOT EXISTS citext;

CREATE TABLE users (
    id            serial PRIMARY KEY,
    email         citext      NOT NULL UNIQUE,
    password_hash text        NOT NULL,
    full_name     text        NOT NULL,
    phone         text,
    role          text        NOT NULL DEFAULT 'client'
                              CHECK (role IN ('client', 'barber')),
    created_at    timestamptz NOT NULL DEFAULT now()
);

-- Semilla de la demo. La contraseña en claro de los tres es "demo1234"; el
-- primero es el DEMO_USER_EMAIL/DEMO_USER_PASSWORD del .env (tarea 28). No es un
-- secreto: users-db no recibe esas variables, así que el hash va fijo aquí.
INSERT INTO users (email, password_hash, full_name, phone, role) VALUES
    ('demo@barberflow.local', '$2b$12$i/kxvXTfWqkXRSvWAq5ZfewxO9vkPec9TAkq8rn/UkaQA4ohRpSI2', 'Demo BarberFlow', '+502 5555-0000', 'client'),
    ('ana@barberflow.local',  '$2b$12$UHdU/cNQ30ZiTXg4coC2mephdUk6WMUZTKWRQKWhRcobC97GbPviK', 'Ana López',       '+502 5555-1234', 'client'),
    ('marco@barberflow.local','$2b$12$mdizstHeDY1aHeIq15oGaua7RQChXtcD1kuYBOMkfIHfX3QFGZcVO', 'Marco Ruiz',      '+502 5555-4321', 'barber');
