from behave import given
from django.apps.registry import apps
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType

Arquivo = apps.get_model('arquivo', 'Arquivo')
TipoArquivo = apps.get_model('arquivo', 'TipoArquivo')
Funcao = apps.get_model('arquivo', 'Funcao')
Processo = apps.get_model('arquivo', 'Processo')
Servidor = apps.get_model('rh', 'Servidor')


@given('os dados básicos para arquivos')
def step_dados_basicos_arquivos(context):
    servidor = Servidor.objects.get(matricula='101013')
    uploader = Servidor.objects.get(matricula='101010')
    from django.core.files import File

    fd = open('/tmp/arquivo.pdf', 'w+')
    fd.write('conteudo')
    fd.close()
    fd = open('/tmp/arquivo.pdf')
    f = File(fd)

    novo_arquivo = Arquivo()
    novo_arquivo.nome = 'arquivo de teste'
    novo_arquivo.objeto = servidor
    novo_arquivo.object_id = servidor.id
    novo_arquivo.upload_por = uploader.get_user()
    novo_arquivo.content_type = ContentType.objects.get_for_model(servidor.__class__)
    novo_arquivo.file = f
    novo_arquivo.save()
    f.close()
    fd.close()

    grupo = Group.objects.get(name='Coordenador de Gestão de Pessoas')
    identificador = Servidor.objects.get(matricula='101011')
    identificador.get_user().groups.add(grupo)
    identificador2 = Servidor.objects.get(matricula='101012')
    identificador2.get_user().groups.add(grupo)
    funcao = Funcao.objects.get_or_create(descricao='Descrição da Função')[0]
    processo = Processo.objects.get_or_create(descricao='Descrição do Processo', funcao=funcao)[0]
    tipo_arquivo = TipoArquivo.objects.get_or_create(descricao='Alteração de férias')[0]
    processo.tipos_arquivos.add(tipo_arquivo)
