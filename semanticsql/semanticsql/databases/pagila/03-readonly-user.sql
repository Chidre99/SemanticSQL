-- Runs after 01-schema.sql and 02-data.sql have populated the `public` schema.
-- Creates a readonly role that the application will use for all queries.

CREATE ROLE readonly_user LOGIN PASSWORD 'readonly_pw';

-- Allow connection to the pagila database
GRANT CONNECT ON DATABASE pagila TO readonly_user;

-- Read on existing schema objects
GRANT USAGE ON SCHEMA public TO readonly_user;
GRANT SELECT ON ALL TABLES    IN SCHEMA public TO readonly_user;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO readonly_user;

-- Catch future tables added by migrations
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES    TO readonly_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON SEQUENCES TO readonly_user;

-- Belt and suspenders: explicitly deny write-y things at the role level
-- (no INSERT/UPDATE/DELETE/TRUNCATE granted; revoke just to be loud about it)
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public FROM readonly_user;
