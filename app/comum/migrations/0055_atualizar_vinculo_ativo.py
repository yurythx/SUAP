from django.conf import settings
from django.db import migrations


def atualizar_status_ativo_vinculo(apps, schema):
    Servidor = apps.get_model('rh', 'Servidor')
    PessoaExterna = apps.get_model('rh', 'PessoaExterna')
    PessoaJuridica = apps.get_model('rh', 'PessoaJuridica')
    Aluno = apps.get_model('edu', 'Aluno') if 'edu' in settings.INSTALLED_APPS else None
    Vinculo = apps.get_model('comum', 'Vinculo')
    PrestadorServico = apps.get_model('comum', 'PrestadorServico')

    servidores_inativos = Servidor.objects.filter(excluido=True)
    Vinculo.objects.filter(
        tipo_relacionamento__app_label='rh',
        tipo_relacionamento__model='servidor',
        id_relacionamento__in=servidores_inativos
    ).update(ativo=False, skip_history=True)

    alunos_inativos = Aluno.objects.filter(situacao__ativo=False) if Aluno else []
    Vinculo.objects.filter(
        tipo_relacionamento__app_label='edu',
        tipo_relacionamento__model='aluno',
        id_relacionamento__in=alunos_inativos
    ).update(ativo=False, skip_history=True)

    prestadores_inativos = PrestadorServico.objects.filter(ativo=False)
    Vinculo.objects.filter(
        tipo_relacionamento__app_label='comum',
        tipo_relacionamento__model='prestadorservico',
        id_relacionamento__in=prestadores_inativos
    ).update(ativo=False, skip_history=True)

    pessoas_juridicas = PessoaJuridica.objects.all()
    Vinculo.objects.filter(
        tipo_relacionamento__app_label='rh',
        tipo_relacionamento__model='pessoajuridica',
        id_relacionamento__in=pessoas_juridicas
    ).update(ativo=False, skip_history=True)

    pessoas_externas = PessoaExterna.objects.all()
    Vinculo.objects.filter(
        tipo_relacionamento__app_label='rh',
        tipo_relacionamento__model='pessoaexterna',
        id_relacionamento__in=pessoas_externas
    ).update(ativo=False, skip_history=True)


class Migration(migrations.Migration):

    dependencies = [
        ('comum', '0054_vinculo_ativo'),
    ]

    operations = [
        migrations.RunPython(atualizar_status_ativo_vinculo),
    ]
