import datetime
import functools
import logging
import operator
from collections import Counter, OrderedDict
from collections.abc import Iterable, Mapping
from typing import Any

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Exists, OuterRef, QuerySet
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.html import strip_tags
from django.views.decorators.cache import cache_page

from avaliacao_integrada import tasks
from avaliacao_integrada.forms import AvaliacaoExternaForm, EnviarEmailRespondentesForm, FiltroIndicadorForm, RelatorioForm, RelatorioXLSXForm
from avaliacao_integrada.models import Avaliacao, ComissaoCPA, EscalaLikert, Indicador, Iterador, NivelEscalaLikert, Respondente, Resposta, Segmento
from avaliacao_integrada.typing_defs import (
    DadosMontagemFormulario,
    DadosSociedadeCivilToken,
    DadosTokenMinimo,
    DadosUsuarioExterno,
    IteracoesType,
    ObjectKeyType,
    ServicoAnonimo,
)
from avaliacao_integrada.utils import atualizar_parametro_tab
from comum.exceptions import BusinessRuleFailure
from comum.models import Vinculo
from djtools import forms, layout
from djtools.crosstab.bidimensional import TabelaBidimensional
from djtools.forms.fields import DateFieldPlus
from djtools.html.graficos import BarChart, PieChart, StackedGroupedColumnChart
from djtools.utils import JsonResponse, httprr, permission_required, rtr
from edu.models import CursoCampus, Diario, Modalidade, ProfessorDiario
from rh.models import Servidor, UnidadeOrganizacional

logger = logging.getLogger(__name__)


def _assert_dados_montagem(dados_montagem: Mapping[str, Any]) -> None:
    """
    Valida, em tempo de execução, a estrutura mínima esperada para DadosMontagemFormulario.
    Lança ValidationError se algum campo obrigatório estiver ausente.
    """
    from django.core.exceptions import ValidationError

    # "respondente" pode estar ausente no início do fluxo externo:
    # ele é identificado/criado dentro de montar_formulario.
    obrigatorios = ('avaliacao', 'segmento', 'uo', 'user', 'eh_previsualizacao')
    faltantes = [k for k in obrigatorios if k not in dados_montagem]
    if faltantes:
        raise ValidationError(f"Estrutura inválida em 'dados'. Campos obrigatórios ausentes: {', '.join(faltantes)}.")


def check_respondente_segmento(
    avaliacao: Avaliacao,
    tipo_respondente: int,
    dados_sociedade_civil: DadosSociedadeCivilToken,
) -> tuple[bool, dict, str | None, str | None]:
    """
    Verifica divergência entre o segmento selecionado e o segmento
    inferido a partir dos dados do público externo.
    """
    mensagem_aviso = None
    mensagem_erro = None
    segmento_diferente = False

    # --- validação mínima do 'dados' recebido deste fluxo externo ---
    dados_usuario_externo = dados_sociedade_civil.get('dados_usuario_externo')
    if not isinstance(dados_usuario_externo, dict):
        raise ValidationError("Estrutura inválida: esperado 'dados_usuario_externo' como dict em 'dados'.")
    # ----------------------------------------------------------------

    email_fornecido = dados_usuario_externo.get('email')

    logger.debug(f'> Dados fornecidos: {dados_sociedade_civil["dados_usuario_externo"]}')

    # Verifica se foi gerado um público alvo (respondente) com os dados fornecidos pelo usuário externo.
    qs_respondente = avaliacao.obter_respondentes_sociedade_civil(dados_sociedade_civil)

    if qs_respondente.exists():
        segmentos = set(qs_respondente.values_list('segmento__id', flat=True))
        if len(segmentos) > 1:
            segmento_diferente = True
            mensagem_erro = 'Os dados fornecidos não permitem identificar um perfil único, pois apontam para múltiplas possibilidades.'
        else:
            respondente = qs_respondente.values('id', 'segmento__id', 'segmento__descricao', 'finalizado', 'dados_usuario_externo').last()

            # Atualiza o email do respondente com o e-mail fornecido.
            dados_respondente = respondente['dados_usuario_externo']
            dados_sociedade_civil['respondente_id'] = respondente['id']
            dados_respondente['tipo_respondente'] = respondente['segmento__id']

            logger.debug(f'> Respondente identificado, dados: {dados_respondente}')

            # Se o email fornecido é diferente do email existente, atualiza o email do respondente
            if email_fornecido and email_fornecido != dados_respondente['email']:
                logger.debug(
                    f'> Email fornecido {email_fornecido} é diferente do respondente {dados_respondente}: Atualizando o email do respondente.'
                )
                dados_respondente['email'] = email_fornecido
                Respondente.objects.filter(id=respondente['id']).update(dados_usuario_externo=dados_respondente)

            # Se o segmento selecionado no front for diferente do segmento do respondente gerado, então
            # envie mensagem de confirmação para o front
            if tipo_respondente != respondente['segmento__id']:
                segmento_diferente = True

                qs_respostas = Resposta.objects.filter(respondente_id=respondente['id'])

                # Exibe mensagens de aviso dependendo da existência de respostas
                if qs_respostas.exists():
                    mensagem_aviso = (
                        f'Você já iniciou uma avaliação para o segmento {respondente["segmento__descricao"]}.'
                        f'Se sim, clique no botão "OK" para confirmar.'
                        f'Deseja excluí-la e iniciar uma nova para o segmento selecionado? '
                    )
                else:
                    mensagem_aviso = (
                        f'Você já possui um questionário de autoavaliação personalizado para '
                        f'seu perfil (segmento {respondente["segmento__descricao"]}). '
                        f'Deseja excluí-lo e iniciar uma nova avaliação para o segmento selecionado? '
                        f'Se sim, clique no botão "OK" para confirmar.'
                    )
            # Atualiza os dados para gerar um token único por respondente.
            dados_usuario_externo.update(dados_respondente)

    return segmento_diferente, dados_sociedade_civil, mensagem_aviso, mensagem_erro


@layout.servicos_anonimos()
def servicos_anonimos(request: HttpRequest) -> list[ServicoAnonimo]:
    servicos_anonimos = []

    try:
        avaliacos_vigentes = Avaliacao.vigentes()
    except transaction.TransactionManagementError:
        logger.warning('Transação inválida ao carregar serviços anônimos de avaliação integrada.')
        return servicos_anonimos
    for avaliacao in avaliacos_vigentes:
        if avaliacao.possui_segmento_sociedade_civil():
            token = Avaliacao.gerar_token(avaliacao.id)
            servicos_anonimos.append(
                {'categoria': 'Avaliações', 'url': f'/avaliacao_integrada/avaliacao_externa/{token}', 'icone': 'file', 'titulo': avaliacao.nome}
            )
    return servicos_anonimos


@layout.inscricao()
def index_inscricoes(request: HttpRequest) -> list[dict[str, Any]]:
    """Retorna inscrições de Avaliação Integrada pendentes para o usuário logado.

    Considera apenas respondentes do vínculo atual cuja avaliação está no
    período de resposta, exibindo ``Iniciar`` ou ``Continuar`` conforme já
    existam respostas registradas.

    Args:
        request: requisição HTTP usada para obter o vínculo do usuário.

    Returns:
        list[dict[str, Any]]: itens com ``url``, ``titulo`` e ``prazo`` para cada respondente pendente.
    """
    inscricoes = []

    respostas = Resposta.objects.filter(respondente_id=OuterRef('id'))
    qs = (
        Respondente.objects.annotate(has_respostas=Exists(respostas))
        .select_related('avaliacao', 'segmento', 'uo')
        .filter(
            user=request.user, finalizado=False, avaliacao__data_inicio__lte=datetime.date.today(), avaliacao__data_termino__gte=datetime.date.today()
        )
        .order_by('percentual_resposta', 'avaliacao__data_inicio', 'avaliacao__data_termino')
    )

    for respondente in qs:
        url = f'/avaliacao_integrada/questionario/{respondente.pk}/'
        if respondente.percentual_resposta == 100:
            titulo = (
                f'Parabéns! Você concluiu 100% da avaliação {respondente.avaliacao} relativo '
                f'ao segmento {respondente.segmento.descricao}, campus {respondente.uo}. '
                f'Agora, para que suas respostas sejam registradas, acesse sua autoavaliaçaõ e clique em "Enviar respostas".'
            )
        elif respondente.has_respostas:
            # A avaliação foi salva parcialmente
            titulo = (
                f'Você ainda<strong> pode editar</strong> as suas respostas '
                f'da avaliação {respondente.avaliacao} relativo '
                f'ao segmento {respondente.segmento.descricao}, campus {respondente.uo}.'
            )
        else:
            # Ainda não há respostas
            titulo = (
                f'<strong>Sua voz é importante</strong>! Responda à '
                f'autoavaliação {respondente.avaliacao} do '
                f'segmento {respondente.segmento.descricao}, campus {respondente.uo}, '
                f'e contribua para a melhoria do nosso campus.'
            )

        inscricoes.append({'url': url, 'titulo': titulo, 'prazo': respondente.avaliacao.data_termino})

    return inscricoes


def get_setores(qvsetores: Iterable[dict]) -> dict[int, dict[str, Any]]:
    """
    Converte um iterável de dicts (valores agregados de setor) em um dicionário
    indexado pelo id do setor.
    """
    setores = {}
    if qvsetores:
        for d in qvsetores:
            setores[d['setor__id']] = {'id': d['setor__id'], 'sigla': d['setor__sigla'], 'nome': d['setor__nome']}
    return setores


@rtr()
@permission_required('avaliacao_integrada.view_avaliacao', 'avaliacao_integrada.change_avaliacao')
def setores_sem_areas_de_vinculacao(request: HttpRequest, avaliacao_id: int) -> dict[str, Any]:
    """Exibe setores sem área de vinculação associada para a avaliação informada."""
    avaliacao = get_object_or_404(Avaliacao, id=avaliacao_id)
    title = 'Servidores associados a setores sem áreas de vinculação'

    qsv_servidores_sem_area = avaliacao.obter_servidores_sem_areas_vinculacao()
    setores_sem_areas = get_setores(qsv_servidores_sem_area)

    return locals()


@rtr()
@permission_required('avaliacao_integrada.view_avaliacao', 'avaliacao_integrada.change_avaliacao')
def avaliacao(request: HttpRequest, pk: int):
    """Tela de detalhes de uma avaliação, com filtros e ações administrativas."""

    obj = get_object_or_404(Avaliacao, id=pk)

    token = Avaliacao.gerar_token(obj.id)
    url_to_share = settings.SITE_URL + reverse('avaliacao_externa', args=(token,))

    title = str(obj)
    respondentes = obj.respondente_set.all()

    qsv_servidores_sem_area = obj.obter_servidores_sem_areas_vinculacao()
    setores_sem_areas = get_setores(qsv_servidores_sem_area)

    uos = UnidadeOrganizacional.objects.suap().filter(pk__in=Respondente.objects.filter(avaliacao=obj).values_list('uo__pk', flat=True).distinct())
    segmentos = Segmento.objects.filter(pk__in=Respondente.objects.filter(avaliacao=obj).values_list('segmento__pk', flat=True).distinct())

    q = request.GET.get('q')
    uo_selecionada = request.GET.get('uo_selecionada')
    segmento_selecionado = request.GET.get('segmento_selecionado')

    pode_ver_quadro_resumo = obj.pode_ver_quadro_resumo(request.user)
    pode_visualizar_questionario_terceiros = obj.pode_visualizar_questionario_terceiros(request.user)
    pode_ver_dados_identificaveis = obj.pode_ver_dados_identificaveis(request.user)
    pode_enviar_email_lembrete = obj.pode_enviar_email_lembrete(request.user)
    pode_gerar_publico_alvo = obj.pode_gerar_publico_alvo(request.user)
    pode_reprocessar_publico_alvo_com_exclusao = obj.pode_reprocessar_publico_alvo_com_exclusao(request.user)

    if pode_gerar_publico_alvo and 'identificar_respondentes' in request.GET:
        if not pode_gerar_publico_alvo:
            raise PermissionDenied('Você não tem permissão para realizar esta ação.')
        if qsv_servidores_sem_area and qsv_servidores_sem_area.count():
            raise BusinessRuleFailure('Impossível realizar está ação, pois existem servidores em setores sem áreas de vinculação associadas.')
        return tasks.reprocessar_publico_alvo(request.user, obj, False)

    if 'excluir_e_identificar_respondentes' in request.GET:
        if not pode_reprocessar_publico_alvo_com_exclusao:
            raise PermissionDenied('Você não tem permissão para realizar esta ação.')
        if qsv_servidores_sem_area and qsv_servidores_sem_area.count():
            raise BusinessRuleFailure('Impossível realizar está ação, pois existem servidores em setores sem áreas de vinculação associadas.')
        return tasks.reprocessar_publico_alvo(request.user, obj, True)

    if q:
        respondentes = (
            respondentes.filter(user__vinculo__pessoa__pessoafisica__nome__icontains=q)
            | respondentes.filter(user__username=q)
            | respondentes.filter(user__vinculo__pessoa__pessoafisica__cpf__icontains=q)
            | respondentes.filter(dados_usuario_externo__cpf=q)
            | respondentes.filter(dados_usuario_externo__nome__icontains=q)
        ).distinct()
    else:
        q = ''

    if uo_selecionada:
        respondentes = (respondentes.filter(uo__pk=uo_selecionada)).distinct()
    else:
        uo_selecionada = None

    if segmento_selecionado:
        respondentes = (respondentes.filter(segmento__pk=segmento_selecionado)).distinct()
    else:
        segmento_selecionado = None

    return locals()


@rtr()
@permission_required('avaliacao_integrada.change_indicador')
def indicador(request: HttpRequest, pk: int):
    """Formulário dinâmico de edição/previsualização de um indicador."""
    obj = get_object_or_404(Indicador, id=pk)
    title = str(obj)
    form = forms.Form()
    fields = obj.get_form_field()
    if len(fields) > 1:
        form.fieldsets = ((obj.nome, {'fields': ([x.name for x in fields],)}),)
    for field in fields:
        form.fields[field.name] = field
    return locals()


@rtr()
@permission_required('avaliacao_integrada.pode_replicar_indicador')
def replicar_indicador(request: HttpRequest, pk: int):
    """Clona um indicador e seus relacionamentos principais."""
    from copy import copy

    obj = get_object_or_404(Indicador, id=pk)

    # Clonando o objeto
    novo_obj = copy(obj)
    novo_obj.pk = None
    novo_obj.nome = f'{novo_obj.nome} [Replicado]'
    novo_obj.save()

    # Associando os objetos relacionados ao novo objeto
    for subsidio_para in obj.subsidio_para.all():
        subsidio_para.indicador_set.add(novo_obj)
    for segmento in obj.segmentos.all():
        segmento.indicador_set.add(novo_obj)
    for area_vinculacao in obj.areas_vinculacao.all():
        area_vinculacao.indicador_set.add(novo_obj)
    for modalidade in obj.modalidades.all():
        modalidade.indicador_set.add(novo_obj)
    for opcaoresposta in obj.opcaoresposta_set.all():
        nova_opcaoresposta = copy(opcaoresposta)
        nova_opcaoresposta.pk = None
        nova_opcaoresposta.indicador = novo_obj
        nova_opcaoresposta.save()

    # Redirecionando para a página de edição
    return httprr(f'/admin/avaliacao_integrada/indicador/{novo_obj.pk}/change/', 'Indicador replicado com sucesso.')


def montar_formulario(
    request: HttpRequest,
    dados_montagem: DadosMontagemFormulario,
) -> tuple[forms.Form, str | None, IteracoesType, dict[str, Any], int]:
    """
    Monta o formulário da avaliação, agrupando campos por objeto → eixo → dimensão → macroprocesso.

    Retorna:
        (form, url, iteracoes, initial, percentual)
    """
    _assert_dados_montagem(dados_montagem)  # garante estrutura mínima esperada

    # além do agrupado por eixo, macroprocesso e dimensão, as perguntas serão
    # agrupadas por uma seção representando o objeto ao qual as perguntas/criterios
    # se referem.
    # As perguntas relacionadas à instituição serão vinculadas ao objeto None

    logger.debug(f'Montar formulário com os dados: {dados_montagem}')
    initial = {}

    avaliacao = dados_montagem['avaliacao']
    respondente = dados_montagem.get('respondente')
    segmento = dados_montagem['segmento']
    uo = dados_montagem['uo']
    user = dados_montagem['user']
    dados_usuario_externo = dados_montagem.get('dados_usuario_externo')

    form = forms.Form(data=request.POST or None)

    if respondente is None:
        if request.method == 'GET':
            logger.debug(
                f'> Respondente não existe, criando um novo com os dados: '
                f'avaliacao.id = {avaliacao.id}, segmento = {segmento.descricao}'
                f'dados_usuario_externo = {dados_usuario_externo}'
            )
            # `ModelPlus.get_or_create` devolve `(objeto, criado)`: descartar o retorno deixava
            # `respondente` em None e estourava `AttributeError` no primeiro acesso externo.
            respondente, _ = Respondente.get_or_create(user=None, avaliacao=avaliacao, segmento=segmento, dados_usuario_externo=dados_usuario_externo)
        else:
            respondente_id = None
            # Obtem o ID do respondente.
            # Iterando sobre o dicionário para encontrar as chaves que possuem '::'
            for identificador in request.POST:
                if '::' in identificador:
                    # Dividindo a chave pelo delimitador '::'
                    partes = identificador.split('::')

                    # Obtendo o segundo valor da lista resultante
                    respondente_id = partes[1]
                    break

            if respondente_id:
                qs = Respondente.objects.filter(id=respondente_id)
                if qs.exists():
                    respondente = qs.first()

    logger.debug('> Obtendo indicadores ...')
    indicadores = Respondente.get_indicadores(avaliacao, segmento, uo, user, excluir_automatico=False, ignorar_opcionais=False)
    if not indicadores:
        raise ValidationError(
            f'Não foi encontrado um questionário de avaliação para o '
            f'segmento "{segmento.descricao}". Para reportar o problema, '
            f'por favor, use a funcionalidade "Reportar Erro", selecionando '
            f'a área "Desenvolvimento Institucional" e o módulo '
            f'"Avaliação Integrada".'
        )

    # obtendo as respostas previamente fornecidas para inicialização dos fields
    eh_previsualizacao = dados_montagem['eh_previsualizacao']

    if not eh_previsualizacao:
        respostas = Resposta.objects.filter(respondente=respondente).values_list('identificador', 'valor', 'nivel_escala__id', 'nivel_escala__nivel')

        for identificador, valor, nivel_escala_id, nivel_escala_nivel in respostas:
            initial[identificador] = valor
            if nivel_escala_id:
                initial[identificador] = f'{nivel_escala_id}___{nivel_escala_nivel}'

    # lista de objetos a iterar
    objetos: list[ObjectKeyType] = [
        None,
        *list(Respondente.get_modalidades_relacionadas(avaliacao, segmento, uo)),
        *list(Respondente.get_cursos_relacionados(segmento, uo, user)),
        *list(Respondente.get_turmas_relacionadas(avaliacao, segmento, user)),
        *list(Respondente.get_professores_relacionados(avaliacao, segmento, user)),
    ]

    # identificando os indicadores para cada tipo de objeto iterável (None = instituição)
    iteracoes = OrderedDict()

    # mapeia o tipo do objeto iterável para o queryset de indicadores
    indicadores_por_iterador: dict[type[object], QuerySet[Indicador]] = {}

    indicadores_por_iterador[type(None)] = indicadores.exclude(iterador__segmento=segmento)
    indicadores_por_iterador[Modalidade] = indicadores.filter(iterador__segmento=segmento, iterador__objeto=Iterador.MODALIDADE)
    indicadores_por_iterador[CursoCampus] = indicadores.filter(iterador__segmento=segmento, iterador__objeto=Iterador.CURSO)
    indicadores_por_iterador[ProfessorDiario] = indicadores.filter(iterador__segmento=segmento, iterador__objeto=Iterador.PROFESSOR)
    indicadores_por_iterador[Diario] = indicadores.filter(iterador__segmento=segmento, iterador__objeto=Iterador.TURMA)

    # montagem do formulário
    eixo = None
    dimensao = None
    macroprocesso = None

    total = 0
    respondido = 0
    contador = 0
    tem_escala_padrao = False

    for objeto in objetos:
        contador += 1
        indicadores = indicadores_por_iterador[type(objeto)]

        if objeto not in iteracoes:
            iteracoes[objeto] = OrderedDict()

        for indicador in indicadores:
            eixo = indicador.macroprocesso.dimensao.eixo
            dimensao = indicador.macroprocesso.dimensao
            macroprocesso = indicador.macroprocesso

            if eixo not in iteracoes[objeto]:
                iteracoes[objeto][eixo] = OrderedDict()

            if dimensao not in iteracoes[objeto][eixo]:
                iteracoes[objeto][eixo][dimensao] = OrderedDict()

            if macroprocesso not in iteracoes[objeto][eixo][dimensao]:
                iteracoes[objeto][eixo][dimensao][macroprocesso] = []

            if not tem_escala_padrao and indicador.tipo_resposta == Indicador.ESCALA_LIKERT:
                tem_escala_padrao = True

            fields = indicador.get_form_field(respondente, objeto)
            iteracoes[objeto][eixo][dimensao][macroprocesso].append(fields)

            for field in fields:
                identificador = field.name
                if len(fields) > 1:
                    field.aspecto = indicador.aspecto

                field.texto_ajuda = indicador.texto_ajuda

                if not indicador.automatico:
                    total += 1

                if initial.get(identificador):
                    valor = initial[identificador]

                    if '::' in valor:
                        valor = valor.split('::')

                    if isinstance(field, DateFieldPlus):
                        valor = datetime.datetime.strptime(valor, '%Y-%m-%d').date()

                    field.initial = valor

                    if isinstance(field.widget, forms.Textarea) or (valor not in ['', '', None] and not indicador.automatico):
                        respondido += 1

                form.fields[field.name] = field

    if total:
        percentual = int(100 * respondido / total)
    else:
        percentual = 0

    finalizado: bool = respondente.finalizado
    url: str = None
    # Pré-visualização é somente leitura: o template já esconde o botão de envio, mas o
    # `<form>` continua na página e um POST direto gravaria no questionário alheio (#17040).
    if form.is_valid() and not eh_previsualizacao:
        finalizar = '_save_and_finalize' in request.POST

        result = Resposta.processar(respondente, form.cleaned_data, finalizar)
        percentual: int = result['percentual']
        finalizado = result['finalizado']

        if finalizar:
            url = '.'
        else:
            next_url = request.META.get('HTTP_REFERER', '.')
            for eixos in iteracoes.values():
                if eixos:
                    n_eixos = len(eixos)
                    tab = request.GET.get('tab')
                    next_url = atualizar_parametro_tab(next_url, tab, n_eixos)
            url = next_url

    return form, url, iteracoes, initial, percentual, finalizado


@rtr()
def questionario(request: HttpRequest, pk: int) -> dict[str, Any]:
    """
    Fluxo de preenchimento do questionário por um respondente autenticado.
    Monta o pacote de montagem (DadosMontagemFormulario) e delega a construção do formulário.
    """

    respondente = get_object_or_404(Respondente, id=pk)
    segmento = respondente.segmento

    respondente_indentificado = True

    title = respondente.avaliacao.nome

    # Seleciona o texto de orientações conforme o segmento
    texto_orientacoes = respondente.avaliacao.texto_instrucoes_servidores
    if respondente.segmento.pk in Segmento.ALUNOS:
        texto_orientacoes = respondente.avaliacao.texto_instrucoes_alunos
    elif respondente.segmento.pk in Segmento.SOCIEDADE_CIVIL:
        texto_orientacoes = respondente.avaliacao.texto_instrucoes_sociedade_civil

    # Pré-visualização: permitido a quem possui permissão e não é o próprio respondente.
    # `pode_visualizar_questionario_terceiros` é um método: sem os parênteses o operando é o
    # próprio objeto-método, sempre truthy, e a expressão colapsa em "não sou o dono" — o que
    # desliga os dois guardas abaixo justamente para quem não é o dono (#17040).
    eh_previsualizacao = respondente.avaliacao.pode_visualizar_questionario_terceiros(request.user) and request.user != respondente.user

    # Verificação de prazo (usa timezone.localdate para consistência)
    if (datetime.date.today() > respondente.avaliacao.data_termino) and not eh_previsualizacao:
        return httprr('/', 'O prazo para resposta da Avaliação foi expirado.', 'error')

    # Garantia de propriedade do questionário quando não é pré-visualização
    if not eh_previsualizacao:
        if respondente.user != request.user:
            return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    # Pacote tipado para montagem do formulário
    dados_montagem: DadosMontagemFormulario = {
        'avaliacao': respondente.avaliacao,
        'respondente': respondente,
        'segmento': segmento,
        'uo': respondente.uo,
        'user': respondente.user,  # se for público interno; manter
        # Propagado, e não fixo em False: é ele que faz a pré-visualização não carregar as
        # respostas de outra pessoa em `initial` e não gravar por cima delas.
        'eh_previsualizacao': eh_previsualizacao,
        # 'dados_usuario_externo': None,    # não aplicável aqui; opcional no TypedDict
    }
    _assert_dados_montagem(dados_montagem)  # garante estrutura mínima esperada

    message_avaliacao_finalizada = ''
    # Mensagem quando o próprio usuário já finalizou
    if request.user == respondente.user and respondente.finalizado:
        message_avaliacao_finalizada = """
        Sua avaliação foi registrada com sucesso!
        Muito obrigado por dedicar seu tempo para avaliar a nossa instituição.
        Com sua participação, estamos mais próximos de construir uma instituição melhor.
        """
    respondente_possui_area_vinculacao = respondente.possui_area_vinculacao()
    if not respondente_possui_area_vinculacao:
        return httprr(
            '/',
            f'O setor associado ao respondente não está vinculado a '
            f'nenhuma das áreas de vinculação definidas para a avaliação '
            f'"{respondente.avaliacao.nome}". Para reportar o problema. '
            f'por favor, use a funcionalidade "Reportar Erro", selecionando a '
            f'área "Desenvolvimento Institucional" e o módulo '
            f'"Avaliação Integrada".',
            'error',
        )

    message_avaliacao_progresso = ''
    try:
        form, target, iteracoes, initial, percentual, finalizado = montar_formulario(request, dados_montagem)
        if percentual < 100:
            message_avaliacao_progresso = (
                f'<p>O progresso da avaliação está em <strong>{percentual}%</strong>.</p> '
                f'<p>Por favor, continue a preencher os questionários '
                f'restantes para completar.</p>'
            )
            message_return = message_avaliacao_progresso
        else:
            if not finalizado:
                # Mensagem específica para 100% preenchido mas não finalizado
                message_avaliacao_progresso = (
                    '<p>Você completou 100% da avaliação. </p> '
                    '<p>Para finalizar o processo e registrar suas respostas, '
                    'lembre-se de clicar no botão <strong>"Enviar respostas"</strong>.</p>'
                    '<p>Agradecemos a sua participação!</p>'
                )
                message_return = f'As suas respostas foram salvas. {message_avaliacao_progresso}'
            else:
                message_return = 'Avaliação concluída com sucesso! Agradecemos a sua participação.'
        if target:
            return httprr(target, strip_tags(message_return))

    except ValidationError as err:
        return httprr(request.META.get('HTTP_REFERER', '..'), message=f'{err}', tag='warning')
    return locals()


@rtr()
def avaliacao_externa(request: HttpRequest, token: str) -> dict[str, Any]:
    """
    Entrada do fluxo para público externo (sociedade civil) via token.

    - Valida vigência e disponibilidade da avaliação para sociedade civil.
    - Exibe formulário de identificação (AvaliacaoExternaForm).
    - Caso o formulário esteja válido:
        * opcionalmente exclui respostas/respondente (quando vier token_respondente de confirmação);
        * verifica conflito de segmento (check_respondente_segmento);
        * emite um novo token atualizado e redireciona para o preenchimento do questionário.
    """
    category = 'Avaliações'
    icon = 'file'
    servicos_anonimos = layout.gerar_servicos_anonimos(request)

    # 1) Obtém estrutura base a partir do token (fluxo sociedade civil)
    dados_sociedade_civil: DadosSociedadeCivilToken = Avaliacao.obter_dados(token) or {}
    avaliacao_id = dados_sociedade_civil.get('avaliacao_id')
    if not avaliacao_id:
        raise PermissionDenied('Avaliação não encontrada ou token inválido/expirado.')

    avaliacao = get_object_or_404(Avaliacao, pk=avaliacao_id)

    # 2) Regras de acesso/tempo
    if not avaliacao.is_vigente():
        raise PermissionDenied('Período de vigência da avaliação encerrado.')

    if not avaliacao.possui_segmento_sociedade_civil():
        raise PermissionDenied('Avaliação não disponível para público externo sociedade civil.')

    title = f'Acessar {avaliacao.nome}'
    texto_orientacoes = avaliacao.texto_instrucoes_sociedade_civil

    # 3) Formulário de identificação do público externo
    form = AvaliacaoExternaForm(avaliacao=avaliacao, token=token, data=request.POST or None)

    if form.is_valid():
        # Atualiza dados do token com o bloco de identificação do público externo
        dados_sociedade_civil['dados_usuario_externo'] = form.cleaned_data.get('dados_usuario_externo')

        # Tipo de respondente informado no form (obrigatório)
        tipo_respondente = int(form.cleaned_data.get('tipo_respondente'))

        # Se veio token_respondente (fluxo de confirmação), excluir respondente/respostas anteriores
        token_respondente = form.cleaned_data.get('token_respondente')
        if token_respondente:
            respondente_id = Avaliacao.obter_dados(token_respondente).get('respondente_id')
            if respondente_id:
                logger.debug(f'Excluindo respondente id={respondente_id} e respostas relacionadas.')
                Resposta.objects.filter(respondente_id=respondente_id).delete()
                Respondente.objects.filter(id=respondente_id).delete()
        else:
            # Verifica conflito de segmento com base nos dados fornecidos
            segmento_diferente, dados_respondente, mensagem_aviso, mensagem_erro = check_respondente_segmento(
                avaliacao,
                tipo_respondente,
                dados_sociedade_civil,  # DadosSociedadeCivilToken (contém dados_usuario_externo)
            )
            if segmento_diferente:
                if mensagem_aviso:
                    messages.add_message(request, messages.WARNING, mensagem_aviso)
                    return locals()
                if mensagem_erro:
                    messages.add_message(request, messages.ERROR, mensagem_erro)
                    return locals()

        # 4) Emite token atualizado e redireciona
        token_atualizado = Avaliacao.gerar_token(avaliacao.id, dados_sociedade_civil)
        return httprr(f'/avaliacao_integrada/avaliacao_externa/{token_atualizado}/{tipo_respondente}/')

    # GET inicial ou POST inválido → renderiza página com o form e contexto
    return locals()


@rtr('avaliacao_integrada/templates/questionario.html')
def questionario_avaliacao_externa(request: HttpRequest, token: str, segmento_id: int) -> dict[str, Any]:
    """Fluxo de preenchimento do questionário para público externo do segmento informado."""
    respondente = None
    respondente_indentificado = False

    # 1) Mantém o dicionário do token separado e tipado
    dados_token: DadosSociedadeCivilToken = Avaliacao.obter_dados(token) or {}

    avaliacao_id = dados_token['avaliacao_id']
    avaliacao = get_object_or_404(Avaliacao, pk=avaliacao_id)
    title = avaliacao.nome
    texto_orientacoes = avaliacao.texto_instrucoes_sociedade_civil

    segmento = get_object_or_404(Segmento, pk=segmento_id)

    if segmento.pk not in Segmento.SOCIEDADE_CIVIL:
        return httprr('..', 'Acesso Negado! Avaliação disponível somente para o segmento sociedade civil!.', 'error')

    # 2) Usa dados_token para identificar o respondente (contrato esperado por obter_respondentes_sociedade_civil)
    qs_respondente = avaliacao.obter_respondentes_sociedade_civil(dados_token)
    if qs_respondente.exists():
        respondente_indentificado = True
        respondente = qs_respondente.first()
        logger.debug(f'> Respondente existe, id = {respondente.id}')

    # 3) Constrói o pacote próprio de montagem do formulário (DadosMontagemFormulario)
    dados_montagem: DadosMontagemFormulario = {
        'avaliacao': avaliacao,
        'segmento': segmento,
        'uo': None,
        'user': request.user,
        'eh_previsualizacao': False,
        # opcional: repassa os dados de usuário externo para inicializações específicas
        'dados_usuario_externo': dados_token.get('dados_usuario_externo'),
    }
    if respondente is not None:
        dados_montagem.update({'respondente': respondente, 'uo': respondente.uo})

    try:
        form, target, iteracoes, initial, percentual, finalizado = montar_formulario(request, dados_montagem)
        if target:
            if target == '..' and respondente_indentificado:
                target = '.'
            elif target == '..' and not respondente_indentificado:
                token = Avaliacao.gerar_token(avaliacao.id)
                target = reverse('avaliacao_externa', args=(token,))
            return httprr(target, 'Avaliação respondida com sucesso.')
    except ValidationError as err:
        return httprr(request.META.get('HTTP_REFERER', '..'), message=f'{err}', tag='warning')
    return locals()


@rtr()
@permission_required('avaliacao_integrada.pode_ver_relatorios')
def relatorio(request: HttpRequest):
    """Tela de filtros e exibição de relatórios (indicadores) da avaliação."""
    title = 'Relatórios'
    form = RelatorioForm(request.GET or None)
    if form.is_valid():
        indicadores = form.processar()
    return locals()


@rtr()
@permission_required('avaliacao_integrada.pode_exportar_respostas')
def relatorio_xlsx(request: HttpRequest):
    """Geração/retorno do relatório em XLSX conforme filtros selecionados."""
    title = 'Relatório em XLSX'
    form = RelatorioXLSXForm(request.GET or None)
    if form.is_valid():
        respostas = form.processar()
        return tasks.relatorio_xlsx(respostas)

    return locals()


@rtr()
@permission_required('avaliacao_integrada.pode_ver_relatorio_indicadores')
def exibir_relatorio_indicador(request: HttpRequest, pk: int, pk_avaliacao: int) -> dict[str, Any]:
    """Detalhamento analítico (gráficos e medidas) de um indicador em uma avaliação."""

    def calcular_distribuicao(
        qsrespostas: QuerySet[Resposta],
        lvalores: list[str] | None = None,
        llvalores: Iterable[tuple[str, str]] | None = None,
    ) -> list[dict[str, Any]]:
        """
        lvalores: lista simples (ex.: ['0', '1', '2', ...])
        llvalores: lista/iterável de tuplas (ex.: [('0','Desconheço'), ('9','Não se aplica'), ...])
        """
        total = qsrespostas.count()
        distribuicao_frequencia: list[dict[str, Any]] = []

        if lvalores:
            for valor in lvalores:
                qtd = qsrespostas.filter(valor=valor).count()
                distribuicao_frequencia.append({'qtd': qtd, 'valor': str(valor), 'valor_str': str(valor)})
        elif llvalores:
            for valor, rotulo in llvalores:
                qtd = qsrespostas.filter(valor=valor).count()
                distribuicao_frequencia.append({'qtd': qtd, 'valor': str(valor), 'valor_str': str(rotulo)})

        if total > 0:
            for df in distribuicao_frequencia:
                df['percentual'] = (float(df['qtd']) / float(total)) * 100.0
        else:
            for df in distribuicao_frequencia:
                df['percentual'] = 0.0

        # Mantém ordenação lexicográfica pelo valor (coerente com strings)
        distribuicao_frequencia.sort(key=lambda x: x['valor'])
        return distribuicao_frequencia

    def get_respostas(qsrespostas: QuerySet[Resposta]) -> dict[str, Any]:
        """
        Retorna dicionário com:
          - 'todas' / 'efetivas': lista de tuplas (valor, valor_str)
          - 'todas_resumidas' / 'efetivas_resumidas': conjuntos para sumarização
        """
        qs = qsrespostas.order_by('valor').values(
            'valor',
            'nivel_escala__descricao',
            'indicador__tipo_resposta',
            'indicador__escala',
            'nivel_escala__tipo_criterio',
        )

        drespostas: dict[str, Any] = {'todas': [], 'efetivas': []}

        for resposta_data in qs:
            valor = resposta_data['valor']
            valor_str = resposta_data['valor'] or Resposta.NAO_RESPONDERAM

            if resposta_data['indicador__escala'] and resposta_data['valor']:
                valor_str = resposta_data['nivel_escala__descricao']
                # Exclui “Não se aplica” e “Desconheço” das efetivas
                if not (
                    resposta_data['nivel_escala__tipo_criterio'] == NivelEscalaLikert.CRITERIO_NAO_SE_APLICA
                    or resposta_data['nivel_escala__tipo_criterio'] == NivelEscalaLikert.CRITERIO_DESCONHECO
                ):
                    drespostas['efetivas'].append((valor, valor_str))
            elif (resposta_data['valor'] and resposta_data['indicador__tipo_resposta'] == Indicador.NUMERO_INTEIRO) or (
                resposta_data['valor'] and resposta_data['valor'] not in (Resposta.VALOR_DESCONHECO, Resposta.VALOR_NAO_SE_APLICA)
            ):
                # Para número inteiro ou outros valores válidos (não “desconheço/NSA”)
                drespostas['efetivas'].append((valor, valor_str))

            drespostas['todas'].append((valor, valor_str))

        drespostas['todas_resumidas'] = set(drespostas['todas'])
        drespostas['efetivas_resumidas'] = set(drespostas['efetivas'])
        return drespostas

    def get_valores_originais(lmatriz: Iterable[tuple[str, str]]) -> list[str]:
        return sorted([lista[0] for lista in lmatriz])

    def get_valores_int(lmatriz: Iterable[tuple[str, str]]) -> list[int]:
        return sorted([int(lista[0] or 0) for lista in lmatriz])

    def get_valores_str(lmatriz: Iterable[tuple[str, str]]) -> list[str]:
        return sorted([lista[1] for lista in lmatriz])

    obj = get_object_or_404(Indicador, pk=pk)
    title = f'Detalhamento do Indicador - {obj.aspecto}'
    avaliacao = get_object_or_404(Avaliacao, pk=pk_avaliacao)

    respostas = obj.resposta_set.filter(respondente__avaliacao=avaliacao)
    respondentes = avaliacao.respondente_set

    # Inicializa variáveis usadas no template
    exibir_mensagem = False
    grafico = None
    grafico2 = None
    distribuicao_frequencia_geral: list[dict[str, Any]] = []
    distribuicao_frequencia_efetiva: list[dict[str, Any]] = []
    media = mediana = variancia = desvio_padrao = coeficiente_variacao = 0.0
    moda = 0

    form = FiltroIndicadorForm(data=request.POST or None)
    form.fields['segmentos'].queryset = obj.segmentos

    if form.is_valid():
        respondentes = form.filtrar_respondentes(respondentes)
        respostas = form.filtrar_respostas(respostas)
    else:
        segmentos = obj.segmentos.all()
        respondentes = Respondente.apply_filters(respondentes, segmentos)
        respostas = Resposta.get(respostas, segmentos)

    qtd_respondentes = respondentes.count()
    qtd_respostas = respostas.order_by('respondente').values_list('respondente', flat=True).distinct().count()

    percentual_respostas = (float(qtd_respostas) / float(qtd_respondentes) * 100.0) if qtd_respondentes > 0 else 0.0

    if qtd_respondentes and qtd_respostas:
        if obj.tipo_resposta in [Indicador.ESCALA_LIKERT, Indicador.NUMERO_INTEIRO]:
            if obj.iterador_set.exists() and not request.POST:
                exibir_mensagem = True
            else:
                import numpy

                drespostas = get_respostas(respostas)
                distribuicao_frequencia_geral = calcular_distribuicao(
                    qsrespostas=respostas,
                    llvalores=drespostas['todas_resumidas'],
                )
                distribuicao_frequencia_efetiva = calcular_distribuicao(
                    qsrespostas=respostas,
                    llvalores=drespostas['efetivas_resumidas'],
                )

                pesos = [x['qtd'] for x in distribuicao_frequencia_efetiva]
                if pesos:
                    valores_efetivos_resumo_int = get_valores_int(drespostas['efetivas_resumidas'])

                    # Média ponderada
                    media = float(numpy.average(valores_efetivos_resumo_int, weights=pesos))

                    # Medidas resumo (com base nos valores efetivos “brutos”)
                    valores_efetivos_int = get_valores_int(drespostas['efetivas'])
                    if valores_efetivos_int:
                        mediana = float(round(numpy.median(valores_efetivos_int), 2))
                        variancia = float(round(numpy.var(valores_efetivos_int), 2))
                        desvio_padrao = float(round(numpy.std(valores_efetivos_int), 2))

                        counts = numpy.bincount(valores_efetivos_int)
                        if counts.size > 0:
                            moda = int(numpy.argmax(counts))

                        coeficiente_variacao = float(round((desvio_padrao / media) if media != 0 else 0.0, 2))

                # Gráficos
                id_grafico = 'id_grafico_x'
                grafico = StackedGroupedColumnChart(
                    id_grafico,
                    title='Distribuição de Frequência das Respostas',
                    groups=[x['valor_str'] or 'Não responderam' for x in distribuicao_frequencia_geral],
                    data=[['Total'] + [x['qtd'] for x in distribuicao_frequencia_geral]],
                )
                grafico.id = id_grafico

                id_grafico = 'id_grafico_y'
                grafico2 = PieChart(
                    id_grafico,
                    title='Distribuição de Frequência das Respostas',
                    data=[[x['valor_str'], x['qtd']] for x in distribuicao_frequencia_geral],
                    dataLabels_format='{point.name} ({point.percentage:.2f}%)',
                )
                grafico2.id = id_grafico

        elif obj.tipo_resposta in [Indicador.UNICA_ESCOLHA, Indicador.MULTIPLA_ESCOLHA]:
            qs = respostas.values_list('valor', flat=True)

            # Gera lista de escolhas individuais (descompacta 'a::b::c' em ['a','b','c'])
            lista: list[list[str]] = []
            for x in qs:
                x = (x or '').rstrip(':')
                lista.append(list(x.split('::')) if x else [''])

            plano = functools.reduce(operator.iadd, lista, [])
            ranking_frequencia = Counter(plano).most_common()

            ranking_frequencia_sem_percentual: list[tuple[str, int]] = []
            ranking_frequencia_com_percentual: list[tuple[str, int, float]] = []

            total_resp = respostas.count()
            qtd_itens = 0
            for item, qtd in ranking_frequencia:
                qtd_itens += 1
                item = item or 'Não responderam'
                ranking_frequencia_sem_percentual.append((item, qtd))
                perc = (float(qtd) / float(total_resp) * 100.0) if total_resp > 0 else 0.0
                ranking_frequencia_com_percentual.append((item, qtd, perc))

            id_grafico = 'id_grafico_x'
            if obj.tipo_resposta == Indicador.UNICA_ESCOLHA:
                grafico = PieChart(
                    id_grafico,
                    title='Ranking de Frequência das Respostas',
                    data=ranking_frequencia_sem_percentual,
                    dataLabels_format='{point.name} ({point.percentage:.2f}%)',
                )
                grafico.id = id_grafico
            else:
                grafico = BarChart(id_grafico, title='Ranking de Frequência das Respostas', data=ranking_frequencia_sem_percentual)
                grafico.id = id_grafico
                grafico.div_height = (qtd_itens * 70) if qtd_itens > 6 else 400

        elif obj.tipo_resposta in [Indicador.TEXTO_CURTO, Indicador.TEXTO_LONGO]:
            conjunto_respostas = respostas.order_by('valor').values_list('valor', flat=True).distinct()

            if obj.tipo_resposta == Indicador.TEXTO_CURTO and obj.automatico:
                if obj.nome != 'Data de nascimento':
                    dist = calcular_distribuicao(respostas, list(conjunto_respostas))
                    serie = []
                    total_resp = respostas.count()
                    for cr in dist:
                        cr['percentual'] = (float(cr['qtd']) / float(total_resp) * 100.0) if total_resp > 0 else 0.0
                        serie.append([cr['valor'], float(cr['qtd'])])

                    id_grafico = 'id_grafico_x'
                    grafico = PieChart(
                        id_grafico,
                        title='Ranking de Frequência das Respostas',
                        data=serie,
                        dataLabels_format='{point.name} ({point.percentage:.2f}%)',
                    )
                    grafico.id = id_grafico
                else:
                    import numpy

                    # Filtra anos plausíveis para histograma
                    lista_anos = []
                    for x in conjunto_respostas:
                        try:
                            ano = int((x or '')[:4])
                            if 1930 < ano < 2010:
                                lista_anos.append(ano)
                        except ValueError:
                            continue

                    if lista_anos:
                        distribuicao, faixas = numpy.histogram(lista_anos)
                        distribuicao_por_faixa = []
                        for n in range(distribuicao.size):
                            distribuicao_por_faixa.append(
                                {
                                    'inicio': int(faixas[n]),
                                    'final': int(faixas[n + 1]),
                                    'total': int(distribuicao[n]),
                                }
                            )
                    else:
                        distribuicao_por_faixa = []

    return locals()


@rtr()
@permission_required('avaliacao_integrada.view_comissaocpa')
def lista_emails_comissao(request: HttpRequest, comissao_id: int):
    """Lista e formata e-mails dos membros de uma Comissão CPA."""
    comissao = get_object_or_404(ComissaoCPA, pk=comissao_id)
    title = 'Lista de Emails dos Membros da Comissão'

    emails = ''

    for contador, membro in enumerate(comissao.vinculos_membros.all(), 1):
        emails = emails + membro.email_notificacao + ';'
        if contador % 10:
            emails = emails + '\n'

    return locals()


@permission_required('avaliacao_integrada.view_comissaocpa')
def obter_membros_por_setor(request: HttpRequest, setor_id: str) -> HttpResponse:
    """Endpoint para autocomplete/listagem de vínculos (membros) por setor."""
    lista_vinculos = []
    if request.method == 'GET':
        if setor_id and setor_id != 'Escolha uma opção':
            servidores = Servidor.objects.ativos().filter(vinculos__setores_adicionais__id=setor_id)
            vinculos = Vinculo.objects.filter(servidor_set__in=servidores)
            lista_vinculos = []
            if vinculos.exists():
                for vinculo in vinculos:
                    data = {'model': Vinculo._meta.model, 'pk': vinculo.id, 'fields': {'titulo': str(vinculo)}}
                    lista_vinculos.append(data)
    return HttpResponse(lista_vinculos, content_type='application/json')


@rtr()
@permission_required('avaliacao_integrada.view_escalalikert')
def escalalikert(request: HttpRequest, pk: int) -> dict[str, Any]:
    """Exibe dados de uma escala Likert."""
    escala = get_object_or_404(EscalaLikert, pk=pk)
    return locals()


@rtr()
def respondente_externo_check(request: HttpRequest) -> JsonResponse:
    """
    Valida dados fornecidos pelo público externo e verifica possível conflito
    de segmento, retornando orientações (token de respondente) quando necessário.

    Espera método POST com os campos:
      - token: str (obrigatório)
      - tipo_respondente: int (obrigatório)
      - email | matricula | cpf | cnpj: str (opcionais, conforme o segmento)
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Método não permitido'}, status=405)

    dados_fornecidos: dict[str, str] = request.POST.dict()
    token: str | None = dados_fornecidos.pop('token', None)
    if not token:
        return JsonResponse({'error': 'Dados inválidos: token ausente.'}, status=400)

    # Obtém estrutura base a partir do token (sociedade civil)
    dados_token: DadosSociedadeCivilToken = Avaliacao.obter_dados(token) or {}
    avaliacao_id = dados_token.get('avaliacao_id')
    if not avaliacao_id:
        return JsonResponse({'error': 'Token inválido ou expirado.'}, status=400)

    avaliacao = get_object_or_404(Avaliacao, pk=dados_token.get('avaliacao_id'))

    # Constrói dados do usuário externo a partir do POST (apenas campos permitidos)
    campos_permitidos = {'email', 'matricula', 'cpf', 'cnpj', 'tipo_respondente'}
    dados_usuario_externo: DadosUsuarioExterno = {}
    for field, value in dados_fornecidos.items():
        if value and field in campos_permitidos:
            if field == 'tipo_respondente':
                try:
                    dados_usuario_externo['tipo_respondente'] = int(value)
                except ValueError:
                    # Ignora conversão inválida; validará adiante
                    pass
            else:
                dados_usuario_externo[field] = value

    dados_token['dados_usuario_externo'] = dados_usuario_externo

    # Obtém o tipo_respondente para a checagem; valida presença/inteiro
    tipo_respondente = dados_usuario_externo.get('tipo_respondente')
    if not isinstance(tipo_respondente, int):
        try:
            tipo_respondente = int(dados_fornecidos.get('tipo_respondente', ''))
        except TypeError, ValueError:
            return JsonResponse({'error': 'tipo_respondente ausente ou inválido.'}, status=400)

    segmento_diferente, dados_respondente, mensagem_aviso, mensagem_erro = check_respondente_segmento(
        avaliacao,
        tipo_respondente,
        dados_token,
    )

    logger.debug(f'dados_respondente: {dados_respondente}, mensagem_aviso: {mensagem_aviso}')

    if segmento_diferente:
        respondente_id = dados_respondente.get('respondente_id')
        token_respondente = Avaliacao.gerar_token(avaliacao.id, {'respondente_id': respondente_id})
        dados_retorno = {
            'segmento_diferente': True,
            'mensagem_aviso': mensagem_aviso,
            'mensagem_erro': mensagem_erro,
            'token_respondente': token_respondente,
        }
        logger.debug(f'JsonResponse({dados_retorno})')
        return JsonResponse(dados_retorno)

    logger.debug('JsonResponse({"segmento_diferente": False})')
    return JsonResponse({'segmento_diferente': False})


@rtr()
def remover_respostas_avaliacao(request: HttpRequest, token: str):
    """
    Cancela (exclui) as respostas vinculadas ao token informado, quando existentes.

    Fluxo:
      1) Obtém o dicionário de dados associado ao token.
      2) Valida a presença de 'respondente_id'.
      3) Exclui as respostas do respondente.
      4) Redireciona com mensagem de sucesso.

    Observação:
      - Esta ação **não** exclui o objeto Respondente, apenas as respostas.
    """
    dados: DadosTokenMinimo | dict[str, Any] = Avaliacao.obter_dados(token) or {}
    respondente_id = dados.get('respondente_id')
    if not respondente_id:
        # Token inválido/expirado ou sem vínculo com respondente
        raise Http404('Token inválido ou não associado a respostas.')

    respostas_qs = Resposta.objects.filter(respondente_id=respondente_id)
    if not respostas_qs.exists():
        raise Http404('Resposta não encontrada.')

    with transaction.atomic():
        respostas_qs.delete()

    return httprr(',', 'Respostas canceladas com sucesso!')


@rtr()  # usa o template padrão inferido pelo SUAP; o {% render_form %} fará o resto
@permission_required('avaliacao_integrada.pode_enviar_email_lembrete')
def avaliacao_enviar_email(request: HttpRequest, pk: int):
    """
    Exibe (modal) o formulário de e-mail, pré-preenchido com o modelo de lembrete.
    Ao confirmar, envia e-mail HTML para todos os respondentes elegíveis.
    """
    obj = get_object_or_404(Avaliacao, pk=pk)

    # Template HTML de lembrete (padrão)
    titulo_default = f'{obj.nome}'
    data_termino_br = obj.data_termino.strftime('%d/%m/%Y')
    mensagem_default = f"""
        <p>Caro(a) respondente, você ainda não concluiu o preenchimento da <strong>{obj.nome}</strong>,
        que está disponível até <strong>{data_termino_br}</strong>.</p>

        <p>Para participar, acesse o SUAP com sua matrícula e senha e clique no link disponível em
        “Fique Atento!”. É possível, a qualquer momento, clicar no botão “Salvar”, disponível no final
        do formulário, e retomar o preenchimento posteriormente, até o prazo final.</p>

        <p><strong>Lembre-se:</strong> Ao terminar o preenchimento, clique no botão “Enviar Respostas”
        para registrar sua participação.</p>

        <p>Vamos lá! Participe! O prazo está acabando!</p>
    """

    if request.method == 'POST':
        form = EnviarEmailRespondentesForm(request.POST)
        if form.is_valid():
            enviados = obj.enviar_emails(
                titulo=form.cleaned_data['titulo'],
                mensagem_html=form.cleaned_data['mensagem'],
            )
            if enviados > 0:
                messages.success(request, f'E-mail enviado para {enviados} respondente(s) elegíveis.')
            else:
                messages.info(request, 'Nenhum destinatário elegível (não finalizado e com e-mail válido) foi encontrado.')
            return httprr(reverse('avaliacao', args=(obj.pk,)))
    else:
        form = EnviarEmailRespondentesForm(
            initial={
                'titulo': titulo_default,
                'mensagem': mensagem_default,
            }
        )

    # Título do modal e contexto padrão para {% render_form %}
    title = f'Enviar lembrete por e-mail — {obj.nome}'
    return locals()


@rtr()
@permission_required('avaliacao_integrada.pode_ver_quadro_resumo')
@cache_page(60 * 30)  # 30 minutos
def avaliacao_quadro_resumo_bloco(request, pk: int, bloco: str):
    obj = get_object_or_404(Avaliacao, pk=pk)

    # Seleciona o queryset e o título conforme o bloco
    if bloco == 'finalizados':
        titulo = 'Finalizados'
        qs = obj.respondente_set.filter(finalizado=True)
    elif bloco == 'parciais_100':
        titulo = 'Respondido 100% mas não enviados'
        qs = obj.respondente_set.filter(finalizado=False, percentual_resposta=100).distinct()
    elif bloco == 'parciais':
        titulo = 'Parciais'
        qs = obj.respondente_set.filter(finalizado=False, resposta__isnull=False).distinct()
    elif bloco == 'nao_respondidos':
        titulo = 'Não Respondidos'
        qs = obj.respondente_set.filter(finalizado=False, resposta__isnull=True).distinct()
    else:
        raise Http404('Bloco inválido.')

    tabela = TabelaBidimensional(
        titulo,
        qs=qs,
        vertical_key='uo',
        vertical_source=UnidadeOrganizacional,  # Model/Manager/QuerySet
        horizontal_key='segmento',
        horizontal_source=Segmento,
        vertical_header_name='Unidade Organizacional',
        vertical_include_null_value=True,
    )

    # Se TabelaBidimensional já implementa __html__/__str__, basta renderizar direto:
    return HttpResponse(str(tabela))


@rtr()
@permission_required('avaliacao_integrada.pode_exportar_respostas')
def quadro_resumo_xlsx(request: HttpRequest, pk: int):
    """
    Gera um XLSX com uma guia por bloco do Quadro Resumo:
    - Finalizados
    - Respondido 100% mas não enviados
    - Parciais
    - Não Respondidos
    """
    obj = get_object_or_404(Avaliacao, pk=pk)

    blocos = [
        ('Finalizados', obj.respondente_set.filter(finalizado=True)),
        ('Respondido 100% mas não enviados', obj.respondente_set.filter(finalizado=False, percentual_resposta=100).distinct()),
        ('Parciais', obj.respondente_set.filter(finalizado=False, resposta__isnull=False).distinct()),
        ('Não Respondidos', obj.respondente_set.filter(finalizado=False, resposta__isnull=True).distinct()),
    ]

    tabelas = []
    for titulo, qs in blocos:
        tabelas.append(
            TabelaBidimensional(
                titulo,
                qs=qs,
                vertical_key='uo',
                vertical_source=UnidadeOrganizacional,
                horizontal_key='segmento',
                horizontal_source=Segmento,
                vertical_header_name='Unidade Organizacional',
                vertical_include_null_value=True,
            )
        )

    # Retorna o arquivo via task (NamedTemporaryFile + finalize)
    return tasks.exportar_crosstab_xlsx(tabelas)
