from django.db import migrations

from djtools.db.migrations.indices import recriar_indices_e_unicidades


class Migration(migrations.Migration):
    """Recria os índices de FK e as UNIQUE que faltam no banco em relação ao state (#17730).

    Não atômica: os índices são criados com CREATE INDEX CONCURRENTLY, sem bloquear escrita.
    O state que o RunPython recebe inclui todas as migrations já aplicadas, de todos os apps,
    por isso basta depender das folhas de comum e rh (as do RemoveInheritance).
    """

    atomic = False

    dependencies = [
        ('comum', '0121_vinculo_search_trgm'),
        ('rh', '0107_importacao_siape_avisos'),
    ]

    operations = [
        migrations.RunPython(recriar_indices_e_unicidades, migrations.RunPython.noop),
    ]
