import datetime

from behave import given
from django.apps.registry import apps
from django.conf import settings
from django.contrib.auth.models import Group

from comum.models import Ano
from comum.types import PessoaFisicaCadastro, ServidorCadastro
from djtools.new_tests.utils import abrir_debugger, desabilitar_inspecao_js, go_url, habilitar_inspecao_js
from djtools.utils import cache_queryset
from rh.models import CargoEmprego, GrupoCargoEmprego, JornadaTrabalho, Servidor, Setor, Situacao

PessoaFisica = apps.get_model('rh', 'PessoaFisica')
UnidadeOrganizacional = apps.get_model('rh', 'UnidadeOrganizacional')
if 'edu' in settings.INSTALLED_APPS:
    Aluno = apps.get_model('edu', 'Aluno')
    SituacaoMatricula = apps.get_model('edu', 'SituacaoMatricula')
    Diretoria = apps.get_model('edu', 'Diretoria')
    CursoCampus = apps.get_model('edu', 'CursoCampus')
    Modalidade = apps.get_model('edu', 'Modalidade')
    NivelEnsino = apps.get_model('edu', 'NivelEnsino')
# ----------------------------------------------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------------------------------------------


# ----------------------------------------------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------------------------------------------
@given('acesso a página "{url}"')
def step_acessa_pagina(context, url):
    page = context.page
    context.xpath.reset()
    current_url = page.url.rstrip('/')
    # Monta a URL absoluta esperada
    base_url = context.config.server_url.rstrip('/')
    if not url.startswith('/'):
        url = '/' + url
    expected_url = base_url + url
    if current_url == expected_url.rstrip('/'):
        return
    go_url(context, url)


@given('acesso a página ajax "{url}"')
def step_acessa_pagina_ajax(context, url):
    page = context.page
    context.xpath.reset()
    current_url = page.url.rstrip('/')
    # Monta a URL absoluta esperada
    base_url = context.config.server_url.rstrip('/')
    if not url.startswith('/'):
        url = '/' + url
    expected_url = base_url + url
    if current_url == expected_url.rstrip('/'):
        return
    desabilitar_inspecao_js(context)
    go_url(context, url)
    habilitar_inspecao_js(context)


@given('os seguintes usuários')
def step_seguintes_usuarios(context):
    # Para Servidores
    setores_suap = cache_queryset(Setor.objects.filter(codigo__isnull=True), 'sigla')
    setores_siape = cache_queryset(Setor.objects.filter(codigo__isnull=False), 'sigla')
    setores_siape = cache_queryset(Setor.objects.filter(codigo__isnull=False), 'sigla')
    situacao_ativo_permanente = Situacao.objects.get(codigo=Situacao.ATIVO_PERMANENTE)
    cargo_emprego = CargoEmprego.objects.get(codigo='01')
    jornada_trabalho = JornadaTrabalho.objects.get(codigo='01')
    # Para aluno
    situacao_matriculado = SituacaoMatricula.objects.get_or_create(descricao='Matriculado', ativo=True)[0]
    # Grupos
    grupos_qs = cache_queryset(Group.objects.all(), 'name')
    nivel_medio = NivelEnsino.objects.get(pk=NivelEnsino.MEDIO)
    modalidade = Modalidade.objects.get_or_create(descricao='Técnico Integrado', defaults={'nivel_ensino': nivel_medio})[0]

    for row in context.table:
        setor_suap = setores_suap[row['Setor']]
        setor_siape = setores_siape[row['Lotação']]
        grupos = row['Grupo'].split(',')
        for grupo_name in grupos:
            grupo = grupos_qs[grupo_name.strip()]
            if grupo_name == 'Aluno':
                diretoria = Diretoria.objects.filter(setor=setor_suap).first()
                if not diretoria:
                    diretoria = Diretoria()
                    diretoria.setor = setor_suap
                    diretoria.save()

                curso = CursoCampus.objects.filter(codigo='TECINFO').first()
                if not curso:
                    curso = CursoCampus()
                    curso.descricao = 'Técnico em Informática'
                    curso.codigo = 'TECINFO'
                    curso.diretoria = diretoria
                    curso.ativo = True
                    curso.modalidade = modalidade
                    curso.save()

                aluno = Aluno.objects.filter(matricula=row['Matrícula']).first()
                if not aluno:
                    ano, _created = Ano.objects.get_or_create(ano='2020')

                    pessoafisica = PessoaFisica.objects.get_or_create(
                        nome=row['Nome'],
                        lattes='http://buscatextual.cnpq.br/buscatextual/visualizacv.do?id=K4758430D7',
                        cpf=row['CPF'],
                        nascimento_data='2010-01-01',
                    )[0]
                    aluno = Aluno.objects.get_or_create(
                        matricula=row['Matrícula'],
                        pessoa_fisica=pessoafisica,
                        ano_letivo=ano,
                        periodo_letivo=1,
                        periodo_atual=1,
                        situacao=situacao_matriculado,
                        ano_let_prev_conclusao=datetime.datetime.now().year,
                        curso_campus=curso,
                    )[0]
                else:
                    pessoafisica = aluno.pessoa_fisica
                    pessoafisica.cpf = row['CPF']
                    pessoafisica.nome = row['Nome']
                    pessoafisica.nascimento_data = '2010-01-01'
                pessoafisica.save()
                aluno.pessoa_fisica.eh_aluno = True
                aluno.pessoa_fisica.save()
                aluno.save()
                v = aluno.get_vinculo()
                if v:
                    v.email_pessoal = row['Email'].split('@')[0] + '_secundario@gmail.com'
                    v.save(update_fields=['email_pessoal'])

                user = aluno.get_user()
                user.set_password(row['Senha'])
                user.is_staff = True
                user.groups.add(grupo)
                user.save()

            else:
                grupo_cargo_emprego = GrupoCargoEmprego.objects.get_or_create(
                    codigo='313', nome='Grupo Saude 1', sigla='X', categoria='tecnico_administrativo', excluido=False
                )[0]

                if grupo_name == 'Auxiliar de Enfermagem':
                    cargo_emprego = CargoEmprego.objects.get_or_create(
                        codigo='701411',
                        nome='AUXILIAR DE ENFERMAGEM',
                        grupo_cargo_emprego=grupo_cargo_emprego,
                        sigla_escolaridade='NI',
                        excluido=False,
                    )[0]

                elif grupo_name == 'Médico':
                    cargo_emprego = CargoEmprego.objects.get_or_create(
                        codigo='701047', nome='MEDICO-AREA', grupo_cargo_emprego=grupo_cargo_emprego, sigla_escolaridade='NS', excluido=False
                    )[0]

                elif grupo_name == 'Odontólogo':
                    cargo_emprego = CargoEmprego.objects.get_or_create(
                        codigo='701064',
                        nome='ODONTOLOGO - 40 HORAS',
                        grupo_cargo_emprego=grupo_cargo_emprego,
                        sigla_escolaridade='NS',
                        excluido=False,
                    )[0]
                elif grupo_name == 'Técnico em Saúde Bucal':
                    cargo_emprego = CargoEmprego.objects.get_or_create(
                        codigo='701241',
                        nome='TECNICO EM HIGIENE DENTAL',
                        grupo_cargo_emprego=grupo_cargo_emprego,
                        sigla_escolaridade='NI',
                        excluido=False,
                    )[0]
                elif grupo_name == 'Enfermeiro':
                    cargo_emprego = CargoEmprego.objects.get_or_create(
                        codigo='701029', nome='ENFERMEIRO-AREA', grupo_cargo_emprego=grupo_cargo_emprego, sigla_escolaridade='NS', excluido=False
                    )[0]
                elif grupo_name == 'Técnico em Enfermagem':
                    cargo_emprego = CargoEmprego.objects.get_or_create(
                        codigo='701233',
                        nome='TECNICO EM ENFERMAGEM',
                        grupo_cargo_emprego=grupo_cargo_emprego,
                        sigla_escolaridade='NI',
                        excluido=False,
                    )[0]
                elif grupo_name == 'Fisioterapeuta':
                    cargo_emprego = CargoEmprego.objects.get_or_create(
                        codigo='701038', nome='FISIOTERAPEUTA', grupo_cargo_emprego=grupo_cargo_emprego, sigla_escolaridade='NI', excluido=False
                    )[0]
                elif grupo_name == 'Psicólogo':
                    cargo_emprego = CargoEmprego.objects.get_or_create(
                        codigo='701060', nome='PSICOLOGO-AREA', grupo_cargo_emprego=grupo_cargo_emprego, sigla_escolaridade='NI', excluido=False
                    )[0]
                elif grupo_name == 'Nutricionista':
                    cargo_emprego = CargoEmprego.objects.get_or_create(
                        codigo='701055',
                        nome='NUTRICIONISTA-HABILITACAO',
                        grupo_cargo_emprego=grupo_cargo_emprego,
                        sigla_escolaridade='NI',
                        excluido=False,
                    )[0]

                pessoa_fisica_dict: PessoaFisicaCadastro = {
                    'nome_registro': row['Nome'],
                    'email': row['Email'],
                    'email_secundario': row['Email'].split('@')[0] + '_secundario@gmail.com',
                    'cpf': row['CPF'],
                }
                dados: ServidorCadastro = {
                    'matricula': row['Matrícula'],
                    'cargo_emprego': cargo_emprego,
                    'setor': setor_suap,
                    'setor_lotacao': setor_siape,
                    'setor_exercicio': setor_siape,
                    'situacao': situacao_ativo_permanente,
                    'jornada_trabalho': jornada_trabalho,
                    'ativo': True,
                    'pessoa_fisica': pessoa_fisica_dict,
                    'data_inicio_exercicio_no_cargo': '2019-03-01',
                }
                servidor = Servidor.update_or_create(dados)['servidor']

                user = servidor.get_user()
                user.set_password(row['Senha'])
                user.is_staff = True
                user.groups.add(grupo)
                user.save()
                servidor.eh_servidor = True
                servidor.save()

                # Servidor.save() pode anular o setor SUAP quando a equivalência
                # entre UOs SIAPE↔SUAP não está configurada no banco de teste.
                # Forçamos a restauração via queryset.update para não re-disparar save().
                if not servidor.setor_id:
                    Servidor.objects.filter(pk=servidor.pk).update(setor=setor_suap)
                    from comum.models import Vinculo
                    from django.contrib.contenttypes.models import ContentType

                    ct = ContentType.objects.get_for_model(Servidor)
                    Vinculo.objects.filter(id_relacionamento=servidor.pk, tipo_relacionamento=ct).update(setor=setor_suap)


@given('a atual página')
def step_atual_pagina(context):
    my_xpath = context.xpath
    my_xpath.reset()
    my_xpath.contexto = ''
    if context.popup:
        context.page = context.popup.pop()
        my_xpath.page = context.page


@given('abro o debugger')
def step_abro_debugger(context):
    abrir_debugger(context)
