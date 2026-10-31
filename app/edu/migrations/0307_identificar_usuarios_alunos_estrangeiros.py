from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.apps.registry import Apps


def identificar_usuarios_alunos_estrangeiros(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Aluno = apps.get_model('edu', 'Aluno')
    PessoaFisica = apps.get_model('rh', 'PessoaFisica')
    User = apps.get_model('comum', 'User')

    alunos = Aluno.objects.filter(nacionalidade='Estrangeira').exclude(passaporte='').values_list('pessoa_fisica_id', 'matricula')
    for pessoa_fisica_id, matricula in alunos.iterator():
        PessoaFisica.objects.filter(pk=pessoa_fisica_id).update(eh_estrangeiro=True)
        User.objects.filter(username=matricula).update(eh_estrangeiro=True, is_active=True, is_staff=True)


class Migration(migrations.Migration):
    dependencies = [
        ('edu', '0306_rateioofertaead_tipopolo_and_more'),
    ]

    operations = [
        migrations.RunPython(identificar_usuarios_alunos_estrangeiros, migrations.RunPython.noop),
    ]
