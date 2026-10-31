CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

CREATE OR REPLACE FUNCTION f_unaccent(text) RETURNS text AS
$func$
SELECT unaccent('unaccent', upper($1))
$func$ LANGUAGE sql IMMUTABLE SET search_path = public, pg_temp;

CREATE COLLATION IF NOT EXISTS ignore_accents_case (
  provider = 'icu',
  locale = 'pt-BR-u-ks-level1',
  deterministic = false
);

SELECT f_unaccent('Ação') AS test;
