# ruff: noqa: B008
import base64
from datetime import timedelta, datetime, date

import magic
from django.db.models import Q, Sum
from django.conf import settings
from django.db.models import OuterRef, Subquery
from django.http import Http404
from django.shortcuts import get_object_or_404
from ninja import Router
from ninja.params.models import Query
from ninja_jwt.tokens import RefreshToken

from api.schemas.ensino import (
    AlunoDiarioSchema,
    AulaSchema,
    AulaAlunoSchema,
    MensagemResponsavelSchema,
    PerguntaMensagemResponsavelSchema,
    FrequenciaSchema,
    CalendarioAcademicoSchema,
    BoletimSchema,
    DadosAlunoMatriculadoSchema,
    DadosProfessorPortalInstitucionalSchema,
    DadosSiabiSchema,
    DependenteSchema,
    DiarioSchema,
    DisciplinaSchema,
    EtapaDisciplinaSchema,
    ItemConfiguracaoAvaliacaoSchema,
    MaterialSchema,
    MatriculaDiarioSchema,
    MatriculaPeriodoSchema,
    MensagemSchema,
    MensagemStatusEnum,
    MeuDiarioEADSChema,
    MeuDiarioSchema,
    MeuPeriodoSchema,
    MeusDadosAluno,
    PeriodoSchema,
    ProfessorSchema,
    RequisitosConclusaoSchema,
    ResponsavelSchema,
    TokenResponsavelSchema,
    TopicoSchema,
    TrabalhoSchema,
)
from comum.models import Ano, User
from djtools.history import log_view_object
from djtools.ninja.auth import TrustedAppAuth, permission_required
from djtools.ninja.router import delete, get, post
from djtools.templatetags.filters.utils import format_, normalizar
from djtools.utils import mask_nota
from edu.models import (
    Aluno,
    Diario,
    Log,
    MatriculaDiario,
    MatriculaPeriodo,
    MensagemEntrada,
    PeriodoLetivoAtual,
    Professor,
    RegistroExclusao,
    RegistroLeitura,
    CalendarioAcademico,
    CursoCampus,
    MensagemResponsavel,
)
from edu.models.diarios import MaterialAula, MaterialDiario, Trabalho, Aula
from edu.models.diplomas import RegistroEmissaoDiploma
from rh.models import Servidor

router = Router(tags=['Ensino'])
router.api_url_prefix = 'ensino'


def get_aluno(request) -> Aluno:
    """
    Obtém o objeto Aluno com base na requisição.

    Args:
        request: Objeto de requisição HTTP.

    Returns:
        Aluno: Objeto Aluno correspondente ao usuário autenticado.
    """
    return get_object_or_404(Aluno, matricula=request.user.username)


def get_periodo(aluno: Aluno, semestre: str) -> MatriculaPeriodo:
    """
    Obtém o período letivo do aluno com base no semestre fornecido.

    Args:
        aluno (Aluno): Objeto Aluno.
        semestre (str): Semestre no formato "[ano].[período]".

    Returns:
        MatriculaPeriodo: Objeto MatriculaPeriodo correspondente ao semestre do aluno.
    """
    try:
        ano_letivo, periodo_letivo = map(int, semestre.split('.'))
    except ValueError:
        raise Http404('Formato inválido. Por favor, insira o semestre no formato: "[ano].[período]". Exemplo: 2023.1')
    ano = Ano.objects.filter(ano=ano_letivo).first()
    if not ano:
        raise Http404('Ano letivo informado não encontrado.')
    periodo = aluno.get_matricula_periodo(ano_letivo=ano, periodo_letivo=periodo_letivo)
    if periodo is None:
        raise Http404('Nenhum período letivo encontrado para o semestre informado.')
    return periodo


def get_diario(aluno: Aluno, pk: int) -> Diario:
    """
    Obtém o diário do aluno com base no semestre fornecido.

    Args:
        aluno (Aluno): Objeto Aluno.
        pk (int): ID do diário.

    Returns:
        Diario: Objeto Diario correspondente ao semestre.
    """
    qs = Diario.objects.filter(matriculadiario__matricula_periodo__aluno=aluno).distinct()
    return get_object_or_404(qs, pk=pk)


def get_matricula_diario(aluno: Aluno, pk: int) -> MatriculaDiario:
    """
    Obtém a matrícula do diário do aluno com base no ID fornecido.

    Args:
        aluno (Aluno): Objeto Aluno.
        pk (int): ID da matrícula do diário.

    Returns:
        MatriculaDiario: Objeto MatriculaDiario correspondente ao ID.
    """
    return get_object_or_404(MatriculaDiario, matricula_periodo__aluno=aluno, pk=pk)


def get_professor(request) -> Professor:
    """
    Obtém o objeto Professor com base na requisição.

    Args:
        request: Objeto de requisição HTTP.

    Returns:
        Professor: Objeto Professor correspondente ao usuário autenticado.
    """
    return get_object_or_404(Professor, vinculo__user=request.user)


@get(
    router,
    '/periodos/',
    response=list[PeriodoSchema],
    summary='Obtém períodos',
    description='Retorna os semestres letivos do aluno.',
)
def get_periodos(request):
    """
    Retorna os semestres letivos do aluno.

    Args:
        request: Objeto de requisição HTTP.

    Returns:
        list: Lista de objetos de períodos letivos.
    """
    aluno = get_aluno(request=request)

    return aluno.get_matriculas_periodo()


@get(
    router,
    '/diarios/{semestre}/',
    response=list[DiarioSchema],
    summary='Obtém diários',
    description='Recupera os diários do aluno em um semestre letivo.',
)
def get_diarios(request, semestre: str):
    """
    Recupera os diários do aluno em um semestre letivo.

    Args:
        request: Objeto de requisição HTTP.
        semestre (str): Semestre no formato "[ano].[período]".

    Returns:
        list: Lista de objetos de diários.
    """
    aluno = get_aluno(request=request)
    periodo = get_periodo(aluno=aluno, semestre=semestre)

    matricula_diario_qs = periodo.matriculadiario_set.all().order_by('diario__componente_curricular__componente__descricao')
    return matricula_diario_qs


@get(
    router,
    '/diarios/{id_diario}/professores/',
    response=list[ProfessorSchema],
    summary='Obtém professores',
    description='Recupera os professores de um diário.',
)
def get_diario_professores(request, id_diario: int):
    """
    Recupera os professores de um diário.

    Args:
        request: Objeto de requisição HTTP.
        id_diario (int): Id do diário.".

    Returns:
        list: Lista de objetos de professores.
    """
    aluno = get_aluno(request=request)
    diario = get_diario(aluno=aluno, pk=id_diario)
    professores = Professor.objects.filter(professordiario__diario=diario).order_by('vinculo__pessoa__nome').distinct()

    return professores


@get(
    router,
    '/diarios/{id_diario}/alunos/',
    response=list[AlunoDiarioSchema],
    summary='Obtém alunos',
    description='Recupera os alunos de um diário.',
)
def get_diario_alunos(request, id_diario: int):
    """
    Recupera os alunos de um diário.

    Args:
        request: Objeto de requisição HTTP.
        id_diario (int): Id do diário.".

    Returns:
        list: Lista de objetos de alunos.
    """
    aluno = get_aluno(request=request)
    diario = get_diario(aluno=aluno, pk=id_diario)
    alunos = Aluno.objects.filter(matriculaperiodo__matriculadiario__diario=diario).order_by('pessoa_fisica__nome').distinct()

    return alunos


@get(
    router,
    '/diarios/{id_diario}/aulas/',
    response=list[AulaSchema],
    summary='Obtém aulas',
    description='Recupera as aulas de um diário.',
)
def get_diario_aulas(request, id_diario: int):
    """
    Recupera as aulas de um diário.

    Args:
        request: Objeto de requisição HTTP.
        id_diario (int): Id do diário.".

    Returns:
        list: Lista de objetos de aulas.
    """
    aluno = get_aluno(request=request)
    diario = get_diario(aluno=aluno, pk=id_diario)
    request.aluno = aluno

    return diario.get_aulas()


@get(
    router,
    '/diarios/{id_diario}/materiais/',
    response=list[MaterialSchema],
    summary='Obtém materiais',
    description='Recupera os materiais de um diário.',
)
def get_diario_materiais(request, id_diario: int):
    """
    Recupera os materiais de um diário.

    Args:
        request: Objeto de requisição HTTP.
        id_diario (int): Id do diário.".

    Returns:
        list: Lista de objetos de material.
    """
    aluno = get_aluno(request=request)
    diario = get_diario(aluno=aluno, pk=id_diario)
    materiais_qs = MaterialDiario.objects.filter(professor_diario__diario=diario).order_by('-data_vinculacao')

    materiais = []

    for material in materiais_qs:
        materiais.append(
            {
                'id': material.id,
                'data': material.data_vinculacao.strftime('%d/%m/%Y'),
                'descricao': material.material_aula.descricao,
                'url': material.material_aula.get_absolute_url(),
            }
        )

    return materiais


@get(
    router,
    '/materiais/{id_material}/',
    response=MaterialSchema,
    summary='Obtém material',
    description='Recupera o material de um diário.',
)
def get_diario_material(request, id_material: int):
    """
    Recupera o material de um diário.

    Args:
        request: Objeto de requisição HTTP.
        id_material (int): Id do material.".

    Returns:
        material: Material solicitado.
    """
    aluno = get_aluno(request=request)
    material = get_object_or_404(
        MaterialDiario,
        pk=id_material,
        professor_diario__diario__matriculadiario__matricula_periodo__aluno=aluno,
    )

    if material is None:
        return 404, {'message': 'Material não encontrado'}

    return {
        'id': material.material_aula.id,
        'data': material.data_vinculacao.strftime('%d/%m/%Y'),
        'descricao': material.material_aula.descricao,
        'url': material.material_aula.get_absolute_url(),
    }


@get(
    router,
    '/materiais/{id_diario}/{id_material}/pdf/',
    response=str,
    summary='Obtém PDF do material',
    description='Recupera o pdf material de um diário.',
)
def get_diario_material_pdf(request, id_diario: int, id_material: int):
    """
    Recupera o material de um diário.

    Args:
        request: Objeto de requisição HTTP.
        id_material (int): Id do material.".

    Returns:
        material: Material solicitado.
    """
    aluno = get_aluno(request)
    materialaula = get_object_or_404(
        MaterialAula,
        materialdiario__professor_diario__diario__matriculadiario__matricula_periodo__aluno=aluno,
        pk=id_material,
    )
    diario = get_diario(aluno, pk=id_diario)
    descricao = f'O usuário visualizou o {materialaula._meta.verbose_name} #{materialaula.pk}'
    if settings.USE_HISTORY:
        log_view_object(materialaula)
    if settings.USE_EDU_LOG:
        log = Log()
        log.set_up(request.user, Log.VISUALIZACAO, materialaula, descricao)
        log.ref_aluno = aluno.pk
        log.ref_diario = diario.pk
        log.save()
    url = materialaula.get_absolute_url()
    if not url.startswith('http') or not url.startswith('ftp'):
        url = f'{request.scheme}://{request.META["HTTP_HOST"]}{url}'
    return url


@get(
    router,
    '/diarios/{id_diario}/trabalhos/',
    response=list[TrabalhoSchema],
    summary='Obtém trabalhos',
    description='Recupera os trabalhos de um diário.',
)
def get_diario_trabalhos(request, id_diario: int):
    """
    Recupera os trabalhos de um diário.

    Args:
        request: Objeto de requisição HTTP.
        id_diario (int): Id do diário.".

    Returns:
        list: Lista de objetos de trabalho.
    """
    aluno = get_aluno(request=request)
    diario = get_diario(aluno=aluno, pk=id_diario)

    trabalhos = []

    for trabalho in diario.trabalho_set.all():
        url = trabalho.arquivo.url if trabalho.arquivo else None
        if url and (not url.startswith('http') and not url.startswith('ftp')):
            url = f'{settings.SITE_URL}{url}'
        trabalhos.append(
            {
                'id': trabalho.id,
                'titulo': trabalho.titulo,
                'data_solicitacao': trabalho.data_solicitacao.strftime('%d/%m/%Y'),
                'data_limite': trabalho.data_limite_entrega.strftime('%d/%m/%Y') if trabalho.data_limite_entrega else 'Sem data limite',
                'etapa': str(trabalho.etapa),
                'expirado': trabalho.data_limite_entrega < date.today() if trabalho.data_limite_entrega else False,
                'descricao': trabalho.descricao,
                'url': url,
            }
        )

    return trabalhos


@get(
    router,
    '/trabalhos/{id_trabalho}/',
    response=TrabalhoSchema,
    summary='Obtém trabalho',
    description='Recupera o trabalho de um diário.',
)
def get_diario_trabalho(request, id_trabalho: int):
    """
    Recupera o trabalho de um diário.

    Args:
        request: Objeto de requisição HTTP.
        id_trabalho (int): Id do trabalho.".

    Returns:
        trabalho: Trabalho solicitado.
    """
    trabalho = Trabalho.objects.filter(id=id_trabalho).first()

    if trabalho is None:
        return 404, {'message': 'Trabalho não encontrado'}

    url = trabalho.arquivo.url if trabalho.arquivo else None
    if url and (not url.startswith('http') and not url.startswith('ftp')):
        url = f'{settings.SITE_URL}{url}'

    return {
        'id': trabalho.id,
        'titulo': trabalho.titulo,
        'data_solicitacao': trabalho.data_solicitacao.strftime('%d/%m/%Y'),
        'data_limite': trabalho.data_limite_entrega.strftime('%d/%m/%Y') if trabalho.data_limite_entrega else 'Sem data limite',
        'etapa': str(trabalho.etapa),
        'expirado': trabalho.data_limite_entrega < date.today() if trabalho.data_limite_entrega else False,
        'descricao': trabalho.descricao,
        'url': url,
    }


@get(
    router,
    '/diarios/{id_diario}/topicos/',
    response=list[TopicoSchema],
    summary='Obtém tópicos',
    description='Recupera os tópicos de um diário.',
)
def get_diario_topicos(request, id_diario: int):
    """
    Recupera os tópicos de um diário.

    Args:
        request: Objeto de requisição HTTP.
        id_diario (int): Id do diário.".

    Returns:
        list: Lista de objetos de tópico.
    """
    aluno = get_aluno(request=request)
    diario = get_diario(aluno=aluno, pk=id_diario)

    return diario.topicodiscussao_set.all()


@get(
    router,
    '/disciplinas/{semestre}/',
    response=list[DisciplinaSchema],
    summary='Obtém disciplinas',
    description='Recupera os dados do aluno nas disciplinas de um semestre letivo.',
)
def get_disciplinas(request, semestre: str):
    """
    Recupera os dados do aluno nas disciplinas de um semestre letivo.

    Args:
        request: Objeto de requisição HTTP.
        semestre (str): Semestre no formato "[ano].[período]".

    Returns:
        list: Lista de objetos de disciplinas.
    """
    aluno = get_aluno(request=request)
    periodo = get_periodo(aluno=aluno, semestre=semestre)

    disciplinas = []

    matricula_diario_qs = periodo.matriculadiario_set.all().order_by('diario__componente_curricular__componente__descricao')

    for matricula_diario in matricula_diario_qs:
        diario = matricula_diario.diario
        componente = diario.componente_curricular.componente

        situacao = matricula_diario.get_situacao_diario_boletim()
        frequencia = matricula_diario.get_percentual_carga_horaria_frequentada()
        qtd_faltas = matricula_diario.get_numero_faltas()
        qtd_avaliacoes = diario.componente_curricular.qtd_avaliacoes
        segundo_semestre = diario.componente_curricular.segundo_semestre

        notas = []

        if qtd_avaliacoes == 2 and segundo_semestre:
            notas.append(
                {
                    'tipo': 'N3',
                    'nota': str(mask_nota(matricula_diario.nota_3)) if matricula_diario.nota_3 else None,
                }
            )
            notas.append(
                {
                    'tipo': 'N4',
                    'nota': str(mask_nota(matricula_diario.nota_4)) if matricula_diario.nota_4 else None,
                }
            )
        elif qtd_avaliacoes == 1:
            notas.append(
                {
                    'tipo': 'N1',
                    'nota': str(mask_nota(matricula_diario.nota_1)) if matricula_diario.nota_1 else None,
                }
            )
        elif qtd_avaliacoes == 2:
            notas.append(
                {
                    'tipo': 'N1',
                    'nota': str(mask_nota(matricula_diario.nota_1)) if matricula_diario.nota_1 else None,
                }
            )
            notas.append(
                {
                    'tipo': 'N2',
                    'nota': str(mask_nota(matricula_diario.nota_2)) if matricula_diario.nota_2 else None,
                }
            )
        else:
            notas.append(
                {
                    'tipo': 'N1',
                    'nota': str(mask_nota(matricula_diario.nota_1)) if matricula_diario.nota_1 else None,
                }
            )
            notas.append(
                {
                    'tipo': 'N2',
                    'nota': str(mask_nota(matricula_diario.nota_2)) if matricula_diario.nota_2 else None,
                }
            )
            notas.append(
                {
                    'tipo': 'N3',
                    'nota': str(mask_nota(matricula_diario.nota_3)) if matricula_diario.nota_3 else None,
                }
            )
            notas.append(
                {
                    'tipo': 'N4',
                    'nota': str(mask_nota(matricula_diario.nota_4)) if matricula_diario.nota_4 else None,
                }
            )

        medias = [
            {'tipo': 'MD', 'nota': str(mask_nota(matricula_diario.get_media_disciplina())) if matricula_diario.get_media_disciplina() else None},
            {
                'tipo': 'MFD',
                'nota': str(mask_nota(matricula_diario.get_media_final_disciplina())) if matricula_diario.get_media_final_disciplina() else None,
            },
            {
                'tipo': 'NAF',
                'nota': str(mask_nota(matricula_diario.nota_final)) if matricula_diario.nota_final else None,
            },
        ]

        disciplinas.append(
            {
                'id': matricula_diario.id,
                'descricao': componente.descricao,
                'sigla': componente.sigla,
                'situacao': situacao,
                'ch_total_aula': diario.get_carga_horaria(),
                'ch_total_relogio': diario.get_carga_horaria_relogio(),
                'ch_cumprida_aula': diario.get_carga_horaria_cumprida(),
                'frequencia': frequencia,
                'qtd_faltas': qtd_faltas,
                'qtd_avaliacoes': qtd_avaliacoes,
                'notas': notas,
                'medias': medias,
            }
        )

    return disciplinas


@get(
    router,
    '/disciplinas/{disciplina}/etapas/',
    response=list[EtapaDisciplinaSchema],
    summary='Obtém avaliações',
    description='Recupera os dados de avaliação do aluno por etapa de uma disciplina.',
)
def get_disciplinas_etapas(
    request,
    disciplina: int,
):
    """
    Recupera os dados de avaliação do aluno por etapa de uma disciplina.

    Args:
        request: Objeto de requisição HTTP.
        disciplina (int): ID da disciplina.

    Returns:
        list: Lista de objetos de etapas de avaliação.
    """
    aluno = get_aluno(request=request)
    matricula_diario = get_matricula_diario(aluno=aluno, pk=disciplina)

    if aluno != matricula_diario.matricula_periodo.aluno:
        return 403, {'message': 'Acesso não permitido.'}

    etapas = {}

    for atividade in matricula_diario.notaavaliacao_set.all():
        data_avaliacao = ''
        item = atividade.item_configuracao_avaliacao
        configuracao = item.configuracao_avaliacao

        if item.data is not None:
            data_avaliacao = item.data.strftime('%d/%m/%Y')

        if configuracao.etapa not in etapas:
            etapas[configuracao.etapa] = {
                'numero_etapa': configuracao.etapa,
                'avaliacoes': [],
            }

        etapas[configuracao.etapa]['avaliacoes'].append(
            {
                'tipo': item.get_tipo_display(),
                'sigla': item.sigla,
                'forma_calculo': configuracao.get_forma_calculo_display(),
                'data': data_avaliacao,
                'nota': str(mask_nota(atividade.nota)) if atividade.nota else None,
            }
        )

    result = sorted(etapas.values(), key=lambda x: x['numero_etapa'])

    return result


@get(
    router,
    '/mensagens/entrada/{status}/',
    response=list[MensagemSchema],
    summary='Obtém as mensagens do usuário',
    description='Recupera as mensagens do usuário de um status (Lida, Não lida, Lixeira ou Todas).',
)
def get_mensagem_entrada_status(
    request,
    status: MensagemStatusEnum,
):
    """
    Recupera as mensagens do usuário de um status (Lida, Não lida, Lixeira ou Todas).

    Args:
        request: Objeto de requisição HTTP.
        status (MensagemStatusEnum): Status das mensagens.

    Returns:
        list: Lista de objetos de mensagens.
    """
    usuario = get_aluno(request).get_user()

    mensagens = None

    if status == MensagemStatusEnum.lidas:
        mensagens = MensagemEntrada.mensagens_lidas(usuario)
    elif status == MensagemStatusEnum.lixeira:
        mensagens = MensagemEntrada.mensagens_lixeira(usuario)
    elif status == MensagemStatusEnum.nao_lidas:
        mensagens = MensagemEntrada.mensagens_nao_lidas(usuario)
    else:
        mensagens = MensagemEntrada.mensagens_todas(usuario)

    data = []

    for mensagem in mensagens:
        data.append(
            {
                'id': mensagem.id,
                'status': status,
                'assunto': mensagem.assunto,
                'conteudo': mensagem.conteudo,
                'data_envio': mensagem.data_envio.strftime('%d/%m/%Y %H:%M:%S'),
                'remetente': {
                    'id': mensagem.remetente.id,
                    'nome': mensagem.remetente.get_profile().nome,
                    'email': (v := mensagem.remetente.get_vinculo()) and v.email_notificacao or '',
                },
                'destinatarios': [],
                'registro_exclusao': mensagem.registro_exclusao,
                'registro_leitura': mensagem.registro_leitura,
            }
        )

    return data


@post(
    router,
    '/mensagens/registro-leitura/{mensagem_id}/',
    response=bool,
    summary='Registra leitura',
    description='Marca como "Lida" uma mensagem do usuário.',
)
def post_registro_leitura(request, mensagem_id: int):
    """
    Marca como "Lida" uma mensagem do usuário.

    Args:
        request: Objeto de requisição HTTP.
        mensagem_id (int): ID da mensagem.

    Returns:
        bool: True se a mensagem foi marcada como lida, False caso contrário.
    """
    usuario = get_aluno(request).get_user()

    mensagem = MensagemEntrada.objects.filter(pk=mensagem_id).first()

    if mensagem is None:
        return 404, {'message': 'Mensagem não encontrada.'}

    if not mensagem.destinatarios.filter(pk=usuario.pk).exists():
        return 403, {'message': 'Registro de leitura não permitido.'}

    registro = RegistroLeitura(
        mensagem=mensagem,
        destinatario=usuario,
    )
    registro.save()

    return True


@delete(
    router,
    '/mensagens/registro-exclusao/{mensagem_id}/',
    response=bool,
    summary='Registra exclusão',
    description='Move para a "Lixeira" uma mensagem do usuário.',
)
def post_registro_exclusao(request, mensagem_id: int):
    """
    Move para a "Lixeira" uma mensagem do usuário.

    Args:
        request: Objeto de requisição HTTP.
        mensagem_id (int): ID da mensagem.

    Returns:
        bool: True se a mensagem foi movida para a lixeira, False caso contrário.
    """
    usuario = get_aluno(request).get_user()

    mensagem = MensagemEntrada.objects.filter(pk=mensagem_id).first()

    if mensagem is None:
        return 404, {'message': 'Mensagem não encontrada.'}

    if not mensagem.destinatarios.filter(pk=usuario.pk).exists():
        return 403, {'message': 'Registro de leitura não permitido.'}

    registro = RegistroExclusao(
        mensagem=mensagem,
        destinatario=usuario,
    )
    registro.save()

    return True


@get(
    router,
    '/meus-dados-aluno/',
    response=MeusDadosAluno,
    summary='Obtém os dados do aluno',
    description='Recupera os dados do aluno com foco no curso.',
)
def get_meus_dados_aluno(request):
    """
    Recupera os dados do aluno especificos do curso.

    Args:
        request: Objeto de requisição HTTP.

    Returns:
        list: Dados do aluno no curso.
    """
    aluno = get_aluno(request=request)

    diploma = RegistroEmissaoDiploma.objects.filter(aluno=aluno, cancelado=False).order_by('-via')
    emitiu_diploma = diploma.exists()

    dados = {
        'ingresso': f'{format_(aluno.ano_letivo)}/{format_(aluno.periodo_letivo)}',
        'email_academico': format_(aluno.email_academico),
        'email_escolar': format_(aluno.email_google_classroom),
        'cpf': format_(aluno.pessoa_fisica.cpf),
        'periodo_referencia': aluno.periodo_atual or 1,
        'ira': format_(aluno.get_ira()),
        'curso': str(aluno.curso_campus),
        'matriz': str(aluno.matriz),
        'qtd_periodos': aluno.matriz and aluno.matriz.qtd_periodos_letivos or 1,
        'situacao': aluno.get_situacao_sistemica()[1],
        'data_migracao': format_(aluno.data_integralizacao),
        'impressao_digital': aluno.pessoa_fisica.tem_digital(),
        'emitiu_diploma': emitiu_diploma,
        'educasenso': aluno.codigo_educacenso,
    }

    return dados


@get(
    router,
    '/requisitos-conclusao/',
    response=RequisitosConclusaoSchema,
    summary='Obtém os requisitos de conclusão.',
    description='Com base no aluno logado, retorna os dados referentes a conclusão.',
)
def get_requisitos_conclusao(request):
    """
    Recupera os dados referentes a conclusão do aluno.

    Args:
        request: Objeto de requisição HTTP.

    Returns:
        Dados de conclusão.
    """
    aluno = get_aluno(request=request)

    response = RequisitosConclusaoSchema()

    # Estágio
    if aluno.matriz and aluno.matriz.exige_estagio:
        response.pratica_profissional_estagio.ch_esperada = aluno.matriz.ch_minima_estagio
        response.pratica_profissional_estagio.ch_cumprida = aluno.get_ch_pratica_profissional_concluida()
        response.pratica_profissional_estagio.ch_pendente = max(
            response.pratica_profissional_estagio.ch_esperada - response.pratica_profissional_estagio.ch_cumprida, 0
        )

    # CH Esperada
    response.regulares_obrigatorios.ch_esperada = aluno.get_ch_componentes_regulares_obrigatorios_esperada()
    response.regulares_optativos.ch_esperada = aluno.get_ch_componentes_regulares_optativos_esperada()
    response.pratica_componente.ch_esperada = aluno.get_ch_pratica_como_componente_esperada()
    response.visita_tecnica.ch_esperada = aluno.get_ch_visita_tecnica_esperada()
    response.eletivos.ch_esperada = aluno.get_ch_componentes_eletivos_esperada()
    response.seminarios.ch_esperada = aluno.get_ch_componentes_seminario_esperada()
    response.pratica_profissional.ch_esperada = aluno.get_ch_componentes_pratica_profissional_esperada()
    response.tcc.ch_esperada = aluno.get_ch_componentes_tcc_esperada()
    response.atividades_complementares.ch_esperada = aluno.get_ch_atividades_complementares_esperada()
    response.atividades_aprofundamento.ch_esperada = aluno.get_ch_atividade_aprofundamento_esperada()
    response.extensao_componentes.ch_esperada = aluno.get_ch_extensao_componentes_esperada()
    response.extensao_outras_atividades.ch_esperada = aluno.get_ch_extensao_outras_atividades_esperada()
    response.extensao_outros_componentes.ch_esperada = aluno.get_ch_extensao_outros_componentes_esperada()

    response.totais.ch_esperada = aluno.matriz.get_carga_horaria_total_prevista()

    # CH Cumprida
    (
        response.regulares_obrigatorios.ch_cumprida,
        response.regulares_optativos.ch_cumprida,
        response.seminarios.ch_cumprida,
        response.pratica_profissional.ch_cumprida,
        response.tcc.ch_cumprida,
        response.atividades_complementares.ch_cumprida,
        response.atividades_aprofundamento.ch_cumprida,
        response.extensao_componentes.ch_cumprida,
        response.extensao_outras_atividades.ch_cumprida,
        response.extensao_outros_componentes.ch_cumprida,
        response.pratica_componente.ch_cumprida,
        response.visita_tecnica.ch_cumprida,
        response.eletivos.ch_cumprida,
        response.atividades_pratica_profissional.ch_cumprida,
        response.percentual_cumprida,
    ) = aluno.get_ch_componentes_com_percentual_ch_cumprida()

    # Pendente
    (
        response.regulares_obrigatorios.ch_pendente,
        response.regulares_optativos.ch_pendente,
        response.eletivos.ch_pendente,
        response.seminarios.ch_pendente,
        response.pratica_profissional.ch_pendente,
        response.atividades_aprofundamento.ch_pendente,
        response.extensao_componentes.ch_pendente,
        response.extensao_outras_atividades.ch_pendente,
        response.extensao_outros_componentes.ch_pendente,
        response.tcc.ch_pendente,
        response.atividades_complementares.ch_pendente,
        response.pratica_componente.ch_pendente,
        response.visita_tecnica.ch_pendente,
        response.atividades_pratica_profissional.ch_pendente,
        response.totais.ch_pendente,
    ) = aluno.get_ch_pendente(detalhado=True)

    response.totais.ch_cumprida = max(response.totais.ch_esperada - response.totais.ch_pendente, 0)

    return response


@post(
    router,
    'autenticacao/acesso-responsaveis/',
    response=TokenResponsavelSchema,
    auth=False,
    summary='Autentica responsável de aluno menor de idade.',
    description='Retorna o token de um aluno a partir da matrícula e chave de acesso do responsável.',
)
def obtem_token_acesso_responsaveis(request, user_data: ResponsavelSchema = Query(...)):
    """
    Retorna o token de um aluno a partir da matrícula e chave de acesso do responsável.

    Args:
        request: Objeto de requisição HTTP.
        user_data (ResponsavelSchema): Dados do responsável.

    Returns:
        dict: Dicionário contendo o token de acesso.
    """
    matricula = user_data.matricula
    if bool(User.objects.filter(username=matricula, login_attempts__gt=3).exists()):
        return 403, {'message': 'Tentativas excessivas de logins. Por favor efetue o login na página inicial do suap.'}

    aluno = get_object_or_404(Aluno, matricula=matricula)

    if aluno.get_chave_responsavel() != user_data.chave:
        user = get_object_or_404(User, username=matricula)
        tentativas = user.login_attempts + 1
        User.objects.filter(username=matricula).update(login_attempts=tentativas)
        return 401, {'message': 'Credenciais inválidas'}

    refresh = RefreshToken.for_user(aluno.get_user())

    return 200, {'token': str(refresh.access_token)}


@get(
    router,
    'meus-dependentes/',
    response=list[DependenteSchema],
    summary='Alunos dependentes do usuário autenticado.',
    description='Retorna a matrícula, nome e token de autenticação dos dependentes do usuário atenticado',
)
def meus_dependentes(request):
    dependentes = []
    cpf_responsavel = Aluno.objects.filter(matricula=request.user.username).values_list('cpf_responsavel', flat=True).first()
    if cpf_responsavel:
        for aluno in Aluno.objects.filter(cpf_responsavel=cpf_responsavel):
            dependentes.append(
                DependenteSchema(
                    foto=aluno.get_foto_75x100_url_publica(),
                    matricula=aluno.matricula,
                    nome=aluno.pessoa_fisica.nome,
                    chave=aluno.get_chave_responsavel(),
                )
            )
    return dependentes


@get(
    router,
    'meu-calendario-academico/{ano}/{periodo_letivo}/',
    response=CalendarioAcademicoSchema | None,
    summary='Obtém calendário acadêmico do aluno',
    description='Recupera o calendário acadêmico do aluno em ano/semestre',
)
def meu_calendario_academico(request, ano: int, periodo_letivo: int):
    aluno = get_aluno(request=request)
    return CalendarioAcademico.objects.filter(
        diario__matriculadiario__matricula_periodo__aluno=aluno,
        diario__ano_letivo__ano=ano,
        diario__periodo_letivo=periodo_letivo,
    ).first()


@get(
    router,
    '/minhas-aulas/{ano}/{mes}/',
    response=list[AulaAlunoSchema],
    summary='Obtém aulas do aluno em um determinado ano e mês',
    description='Recupera as aulas de um diário.',
)
def aulas_aluno(request, ano: int, mes: int):
    """
    Recupera as aulas assistidas pelo aluno em um determinado ano e mês.

    Args:
        request: Objeto de requisição HTTP.
        ano (int): ano em que a aula ocorreu".
        mes (int): mês em que a aula ocorreu".

    Returns:
        list: Lista de objetos de aulas.
    """
    aluno = get_aluno(request=request)
    inicio = date(ano, mes, 1)
    fim = (inicio + timedelta(days=31)).replace(day=1)
    aulas = Aula.objects.filter(
        professor_diario__diario__matriculadiario__matricula_periodo__aluno_id=aluno.id, data__gte=inicio, data__lt=fim
    ).select_related('professor_diario__diario__componente_curricular__componente')
    request.aluno = aluno

    return aulas


@get(
    router,
    '/mensagens-responsavel/',
    response=list[MensagemResponsavelSchema],
    summary='Obtém as mensagens enviadas para os responsáveis dos alunos',
    description='Recupera as mensagens enviadas para os responsáveis dos alunos',
)
def mensagens_reponsavel(request):
    aluno = get_aluno(request=request)
    return MensagemResponsavel.objects.filter(destinatarios=aluno).order_by('-data_envio')


@post(
    router,
    '/mensagens-responsavel/{id}/registrar-leitura/',
    response=MensagemResponsavelSchema,
    summary='Registra a leitura de uma mensagem para o responsável de aluno.',
    description='Registra a leitura de uma mensagem para o responsável de aluno.',
)
def registrar_leitura_mensagem_responsavel(request, id: int):
    aluno = get_aluno(request=request)
    mensagem = aluno.mensagemresponsavel_set.get(pk=id)
    mensagem.registrar_leitura(aluno, 'Aplicativo', datetime.now())
    mensagem.refresh_from_db()
    return mensagem


@post(
    router,
    '/mensagens-responsavel/{id}/perguntar/',
    response=MensagemResponsavelSchema,
    summary='Registra uma pergunta',
    description='Registra pergunta referente a mensagem a responsável de aluno',
)
def pergunta_mensagem_responsavel(request, id: int, payload: PerguntaMensagemResponsavelSchema):
    aluno = get_aluno(request=request)
    registro = aluno.registroleituraresponsavel_set.get(mensagem_id=id)
    registro.perguntar(payload.pergunta)
    return aluno.mensagemresponsavel_set.get(pk=id)


@get(
    router,
    '/frequencia-periodo-letivo/{ano}/{periodo}/',
    response=FrequenciaSchema,
    summary='Obtém total de aulas e faltas',
    description='Recupera total de aulas e faltas em um determinado periodo letivo',
)
def total_aulas_periodo_letivo(request, ano: int, periodo: int):
    """
    Recupera as aulas assistidas pelo aluno em um determinado ano e mês.

    Args:
        request: Objeto de requisição HTTP.
        ano (int): ano em que as aulas ocorreram.
        periodo (int): período em que as aulas ocorreram.

    Returns:
        list: Lista de objetos de aulas.
    """

    aluno = get_aluno(request=request)
    aulas = Aula.objects.filter(
        professor_diario__diario__matriculadiario__matricula_periodo__aluno_id=aluno.id, professor_diario__diario__ano_letivo__ano=ano
    )
    if aluno.curso_campus.periodicidade == CursoCampus.PERIODICIDADE_ANUAL:
        aulas = aulas.filter(etapa__in=((1, 2) if periodo == 1 else (3, 4)))
    else:
        aulas = aulas.filter(professor_diario__diario__periodo_letivo=periodo)

    total_aulas = aulas.aggregate(Sum('quantidade')).get('quantidade__sum') or 0
    falta_totals = aulas.aggregate(
        total_faltas=Sum(
            'falta__quantidade',
            filter=Q(falta__matricula_diario__matricula_periodo__aluno_id=aluno.id),
        ),
        total_abonos=Sum(
            'falta__quantidade',
            filter=Q(
                falta__matricula_diario__matricula_periodo__aluno_id=aluno.id,
                falta__contabilizar=False,
            ),
        ),
    )
    total_faltas = falta_totals.get('total_faltas') or 0
    total_abonos = falta_totals.get('total_abonos') or 0
    return FrequenciaSchema(
        total_aulas=total_aulas,
        total_faltas=total_faltas,
        total_abonos=total_abonos,
        percentual_frequencia=100 - int((total_faltas - total_abonos) * 100.0 / total_aulas if total_aulas else 100),
    )


@get(
    router,
    'meu-boletim/{ano_letivo}/{periodo_letivo}/',
    response=list[BoletimSchema],
    summary='Obtém boletim',
    description='Recupera o boletim do aluno de um ano e período letivo.',
)
def meu_boletim(request, ano_letivo: int, periodo_letivo: int):
    """
    Recupera o boletim do aluno de um ano e período letivo.

    Args:
        request: Objeto de requisição HTTP.
        ano_letivo (int): Ano letivo.
        periodo_letivo (int): Período letivo.

    Returns:
        list: Lista de objetos de boletim.
    """
    aluno = get_aluno(request=request)
    return MatriculaDiario.objects.filter(
        matricula_periodo__aluno=aluno,
        matricula_periodo__ano_letivo__ano=ano_letivo,
        matricula_periodo__periodo_letivo=periodo_letivo,
    ).order_by('diario__componente_curricular__componente__descricao')


@get(
    router,
    'meus-diarios/',
    response=list[MeuDiarioSchema],
    summary='Obtém diários abertos do professor',
    description='Recupera os diários abertos do professor de um ano e período letivo.',
)
def meus_diarios_abertos(request):
    """
    Recupera os diários do professor que estão abertos.

    Args:
        request: Objeto de requisição HTTP.

    Returns:
        list: Lista de objetos de diários.
    """
    return diarios_professor(request, 0, 0)


@get(
    router,
    'meus-diarios/{ano_letivo}/{periodo_letivo}/',
    response=list[MeuDiarioSchema],
    summary='Obtém diários do professor',
    description='Recupera os diários do professor de um ano e período letivo.',
)
def meus_diarios(request, ano_letivo: int, periodo_letivo: int):
    """
    Recupera os diários do professor de um ano e período letivo.

    Args:
        request: Objeto de requisição HTTP.
        ano_letivo (int): Ano letivo.
        periodo_letivo (int): Período letivo.

    Returns:
        list: Lista de objetos de diários.
    """
    return diarios_professor(request, ano_letivo, periodo_letivo)


def diarios_professor(request, ano_letivo: int, periodo_letivo: int):
    obj = get_professor(request=request)
    qs = Diario.objects.filter(
        professordiario__professor=obj,
    )
    if ano_letivo and periodo_letivo:
        qs = qs.filter(
            ano_letivo__ano=ano_letivo,
            periodo_letivo=periodo_letivo,
        )
    else:
        qs = qs.filter(calendario_academico__data_fechamento_periodo__gte=date.today())
    return (
        qs.order_by('id')
        .select_related(
            'calendario_academico',
            'componente_curricular',
            'componente_curricular__componente',
            'componente_curricular__componente__nivel_ensino',
            'local_aula',
            'local_aula__predio',
            'local_laboratorio',
            'local_laboratorio__predio',
        )
        .prefetch_related(
            'professordiario_set',
            'horarioauladiario_set',
            'matriculadiario_set',
            'matriculadiario_set__matricula_periodo',
            'professordiario_set__professor',
            'professordiario_set__professor__vinculo',
            'professordiario_set__professor__vinculo__pessoa',
            'professordiario_set__professor__vinculo__pessoa__pessoafisica',
        )
    )


@get(
    router,
    'meus-periodos-letivos/',
    response=list[MeuPeriodoSchema],
    summary='Obtém periodos',
    description='Retorna os períodos letivos do aluno.',
)
def meus_periodos_letivos(request):
    """
    Retorna os períodos letivos do aluno.

    Args:
        request: Objeto de requisição HTTP.

    Returns:
        list: Lista de objetos de períodos letivos.
    """
    get_aluno(request=request)
    obj = PeriodoLetivoAtual.get_instance(request)

    data = []
    for ano_letivo, periodo_letivo in obj.get_periodos():
        data.append({'ano_letivo': ano_letivo, 'periodo_letivo': periodo_letivo})

    return data


@get(
    router,
    'minhas-proximas-avaliacoes/',
    response=list[ItemConfiguracaoAvaliacaoSchema],
    summary='Obtém próximas avaliações',
    description='Recupera as próximas avaliações do aluno.',
)
def minhas_avaliacoes(request):
    """
    Recupera as próximas avaliações do aluno.

    Args:
        request: Objeto de requisição HTTP.

    Returns:
        list: Lista de objetos de avaliações.
    """
    aluno = get_aluno(request=request)
    return aluno.get_avaliacoes()


@get(
    router,
    'minha-turma-virtual/{pk}/',
    response=MatriculaDiarioSchema,
    summary='Obtém turma virtual',
    description='Recupera os dados de aula de um diário do aluno.',
)
def turma_virtual(request, pk: int):
    """
    Recupera os dados de aula de um diário do aluno.

    Args:
        request: Objeto de requisição HTTP.
        pk (int): ID do diário.

    Returns:
        MatriculaDiario: Objeto MatriculaDiario correspondente ao diário.
    """
    aluno = get_aluno(request=request)
    qs = MatriculaDiario.objects.filter(diario__pk=pk, matricula_periodo__aluno=aluno).exclude(
        situacao__in=[MatriculaDiario.SITUACAO_TRANCADO, MatriculaDiario.SITUACAO_TRANSFERIDO, MatriculaDiario.SITUACAO_CANCELADO]
    )
    if qs.exists():
        obj = qs.first()
    else:
        raise Http404('Turma não encontrada.')
    return obj


@get(
    router,
    'minhas-turmas-virtuais/{ano_letivo}/{periodo_letivo}/',
    response=list[MatriculaPeriodoSchema],
    summary='Obtém turmas virtuais',
    description='Recupera os diários do aluno em um ano e período letivo.',
)
def turmas_virtuais(request, ano_letivo: int, periodo_letivo: int):
    """
    Recupera os diários do aluno em um ano e período letivo.

    Args:
        request: Objeto de requisição HTTP.
        ano_letivo (int): Ano letivo.
        periodo_letivo (int): Período letivo.

    Returns:
        list: Lista de objetos de diários.
    """
    obj = get_aluno(request=request)
    qs = obj.matriculaperiodo_set.filter(ano_letivo__ano=ano_letivo, periodo_letivo=periodo_letivo)
    if not qs.exists():
        raise Http404('Período não encontrado.')
    matricula_periodo = qs[0]
    matriculas_diario = matricula_periodo.matriculadiario_set.all()

    return matriculas_diario


@get(
    router,
    'aluno-resumido/',
    response=list[DadosSiabiSchema],
    ignore_paginate=True,
    summary='Obtém dados resumidos de alunos.',
    description='Obtém dados resumidos de alunos.',
)
@permission_required('edu.pode_sincronizar_dados')
def dados_aluno(request, matricula: str | None = None, ano_conclusao: str | None = None, codigo_curso: str | None = None):
    if matricula:
        aluno = get_object_or_404(Aluno, matricula=matricula)
        return 200, [aluno.get_dados_siabi()]
    elif ano_conclusao and codigo_curso:
        alunos = []
        for aluno in Aluno.objects.filter(ano_conclusao=ano_conclusao, curso_campus__codigo=codigo_curso):
            alunos.append(aluno.get_dados_siabi())
        return 200, alunos
    else:
        return 404, {'message': 'Parâmetros inválidos'}


def meus_diarios_ead(request, pk=None):
    if request.user.eh_aluno:
        aluno_id = Aluno.objects.filter(matricula=request.user.username).values_list('pk', flat=True).first()
        qs = Diario.objects.filter(matriculadiario__matricula_periodo__aluno_id=aluno_id)
    else:
        qs = Diario.objects.filter(professordiario__professor__vinculo=request.user.get_vinculo())
    if pk:
        qs = qs.filter(pk=pk)
    else:
        ano_letivo = qs.order_by('ano_letivo__ano').values_list('ano_letivo__ano', flat=True).last()
        qs = qs.filter(ano_letivo__ano=ano_letivo)
    if pk and not request.user.eh_aluno:
        objs = []
        for obj in qs:
            obj.exibir_alunos = True
            objs.append(obj)
        return objs
    return qs


@get(
    router,
    'meus-diarios-ead/{int:pk}/',
    response=list[MeuDiarioEADSChema],
    summary='Lista um diário de um aluno ou professor EAD',
    description='Lista um diário de um aluno ou professor EAD',
    exclude_none=True,
)
def meus_diarios_ead_com_pk(request, pk: int):
    return meus_diarios_ead(request, pk)


@get(
    router,
    'meus-diarios-ead/',
    response=list[MeuDiarioEADSChema],
    auth=TrustedAppAuth(),
    summary='Lista todos os diarios de um aluno ou professor EAD',
    description='Lista todos os diarios de um aluno ou professor EAD',
    exclude_none=True,
)
def lista_meus_diarios_ead_sem_pk(request):
    return meus_diarios_ead(request)


@get(
    router,
    'aluno-matriculado/',
    response=DadosAlunoMatriculadoSchema,
    summary='Obtém aluno matriculado',
    description='Recupera os dados de um aluno matriculado.',
)
def dados_aluno_matriculado(request, matricula: str):
    if request.user.eh_aluno:
        if request.user.username != matricula:
            return 403, {'message': 'Acesso não permitido.'}
        aluno = get_aluno(request=request)
    else:
        aluno = get_object_or_404(Aluno, matricula=matricula)

    if not aluno.is_matriculado() and not aluno.is_intercambio():
        return 403, {'message': f'Aluno com a matrícula {matricula} não está matriculado e também não está em intercâmbio '}

    matricula_periodo = MatriculaPeriodo.objects.filter(aluno=aluno).latest('id')

    dados_aluno = {}
    dados_aluno['nome'] = normalizar(aluno.get_nome_social_composto())
    dados_aluno['matricula'] = aluno.matricula

    codigo = aluno.curso_campus.codigo.replace('-', '')
    curso = aluno.curso_campus.descricao
    dados_aluno['curso'] = f'{codigo} - {curso}'

    dados_aluno['campus'] = '-'
    if aluno.curso_campus.diretoria and aluno.curso_campus.diretoria.setor.uo.nome:
        dados_aluno['campus'] = aluno.curso_campus.diretoria.setor.uo.nome

    dados_aluno['periodo_atual'] = str(matricula_periodo.aluno.periodo_atual)
    dados_aluno['nascimento'] = aluno.pessoa_fisica.nascimento_data.strftime('%d/%m/%Y') if aluno.pessoa_fisica.nascimento_data else ''
    dados_aluno['cpf'] = aluno.pessoa_fisica.cpf

    dados_aluno['foto_base64'] = ''
    dados_aluno['mime_type'] = ''
    if aluno.foto:
        with aluno.foto.open('rb') as img_file:
            content = img_file.read()
            dados_aluno['foto_base64'] = base64.b64encode(content).decode('utf-8')
            dados_aluno['mime_type'] = magic.from_buffer(content, mime=True)

    return dados_aluno


@get(
    router,
    'portal-professores/',
    response=list[DadosProfessorPortalInstitucionalSchema],
    description='Lista dados públicos de professores para o portal institucional',
)
def portal_professores(request):
    """
    Lista dados públicos de professores para o portal institucional.

    Returns:
        list: Lista de dados dos professores configurados para exibição no portal.
    """
    # Consulta base: professores servidores docentes. Filtra/ordena/dedup pelo e-mail
    # institucional do servidor (relacionamento via GFK → Subquery por id_relacionamento).
    email_institucional = Subquery(Servidor.objects.filter(pk=OuterRef('vinculo__id_relacionamento')).values('email_institucional')[:1])
    qs = (
        Professor.servidores_docentes.filter(vinculo__ativo=True)
        .annotate(email_institucional_docente=email_institucional)
        .filter(email_institucional_docente__isnull=False)
        .exclude(email_institucional_docente='')
    )
    qs = (
        qs.select_related('config_dados_docentes', 'vinculo', 'vinculo__pessoa', 'vinculo__setor', 'vinculo__setor__uo')
        .prefetch_related('materialaula_set')
        .order_by('email_institucional_docente', '-id')
        .distinct('email_institucional_docente')
    )
    return qs
