SELECT count(*) AS tables FROM information_schema.tables WHERE table_schema='public';
SELECT to_regclass('public.auth_user') AS auth_user;
SELECT to_regclass('public.comum_vinculo') AS comum_vinculo;
SELECT count(*) AS migs FROM django_migrations;
