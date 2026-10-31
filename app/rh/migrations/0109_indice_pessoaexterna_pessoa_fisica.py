# O ORM supõe o índice da FK, mas há bancos (o do IFRN, inclusive produção) sem ele: o DELETE da PessoaFisica no
# deduplicar_pessoas checava a FK de rh_pessoaexterna por varredura sequencial (~4 ms por pessoa).

from django.db import migrations

# schema_editor._create_index_name('rh_pessoaexterna', ['pessoa_fisica_id']): o nome que o Django daria ao índice da FK
INDICE = 'rh_pessoaexterna_pessoa_fisica_id_ed6e97e3'

# só cria se não há índice válido e completo começando por pessoa_fisica_id: outra instituição pode tê-lo, com este ou outro nome.
# Parcial (indpred) ou inválido (sobra de CREATE INDEX CONCURRENTLY que falhou) não serve à checagem da FK.
CRIAR_SE_FALTAR = f"""
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_index i
        JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = i.indkey[0]
        WHERE i.indrelid = 'rh_pessoaexterna'::regclass AND a.attname = 'pessoa_fisica_id' AND i.indisvalid AND i.indpred IS NULL
    ) THEN
        CREATE INDEX {INDICE} ON rh_pessoaexterna (pessoa_fisica_id);
    END IF;
END
$$;
"""


class Migration(migrations.Migration):
    dependencies = [
        ('rh', '0108_deduplicacaopessoa'),
    ]

    operations = [
        # sem CONCURRENTLY: ~40 mil linhas, menos de 1 s; atrás do pgbouncer, desiste em 10 s em vez de enfileirar o sistema
        migrations.RunSQL("SET LOCAL lock_timeout = '10s'", migrations.RunSQL.noop),
        migrations.RunSQL(CRIAR_SE_FALTAR, migrations.RunSQL.noop),
    ]
