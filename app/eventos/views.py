# Imports nativos do Python
import io
import logging
import math
import operator
import os
import random
from collections import defaultdict
from datetime import date, datetime
from functools import reduce
from io import BytesIO
from urllib.parse import urlencode

import pandas as pd

# Imports de bibliotecas de terceiros
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Case, CharField, Count, Exists, F, OuterRef, Prefetch, Q, Subquery, Sum, Value, When
from django.forms.models import inlineformset_factory
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render, reverse
from django.template.defaultfilters import pluralize, slugify
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_exempt
from django_tables2.columns.base import Column
from django_tables2.columns.datecolumn import DateColumn
from reportlab.lib.pagesizes import letter, mm
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

from comum.forms import CalendarioForm, ConsultaEvento
from comum.models import Ano, Configuracao, Vinculo
from djtools import layout, tasks
from djtools.db import models
from djtools.forms.widgets import IntegerWidget
from djtools.html.calendarios import Calendario
from djtools.html.graficos import ColumnChart, PieChart
from djtools.signals import minhas_acoes
from djtools.tables import get_table
from djtools.templatetags.filters import format_

# Imports de módulos internos
from djtools.utils import (
    JsonResponse,
    XlsResponse,
    documento,
    gerar_documento_impressao,
    httprr,
    permission_required,
    rtr,
    send_mail,
    send_notification,
    serialization,
    somar_dias,
    text_similarity,
)
from eventos.decorators import (
    pode_submeter_trabalho_ao_evento,
    trata_validation_error,
    valida_passo_inscricao,
    verifica_avaliador_logado,
)
from eventos.enums import (
    EtapaPeriodoSubmissao,
    Recomendacao,
    ResultadoAvaliacao,
    SituacaoConvite,
    SituacaoSubmissao,
    TipoPergunta,
    TipoQuestionario,
    TipoSubmissao,
)
from eventos.forms import (
    AdicionarParticipanteEventoForm,
    AnexoEventoForm,
    AreaTematicaForm,
    AtividadeEventoForm,
    AvaliacaoParticipanteForm,
    AvaliadorModalidadeForm,
    ConfiguracaoEventosForm,
    ConsultaParticipanteForm,
    CriterioAvaliacaoForm,
    CriterioAvaliacaoInlineFormSet,
    EditarParticipanteEventoForm,
    EnviarMensagemForm,
    FiltroSubmissaoForm,
    FluxoSubmissaoForm,
    FotoEventoForm,
    ImportarListaPresencaForm,
    ImportarParticipantesForm,
    IndeferirEventoForm,
    InformarAtividadesForm,
    InformarParticipantesForm,
    InternacionalizacaoForm,
    JustificativaForm,
    LoginParticipanteForm,
    MigrarTipoParticipanteForm,
    ModalidadeForm,
    OpcaoRespostaForm,
    PerfilParticipanteForm,
    PerguntaForm,
    RealizarInscricaoEventoAtividadesForm,
    RealizarInscricaoEventoDadosPessoaisForm,
    RealizarInscricaoEventoNacionalidadeForm,
    RelatorioEventosForm,
    RelatorioParticipantesEventosForm,
    SubmeterNovaVersaoForm,
    SubmissaoForm,
    SubstituirAvaliadorSubmissaoForm,
    TipoModalidadeForm,
    TipoParticipanteForm,
    VideoEventoForm,
    VincularAreaTematicaEventoForm,
    VincularAvaliadorSubmissaoForm,
)
from eventos.models import (
    AreaTematica,
    AreaTematicaModalidade,
    AtividadeEvento,
    AvaliacaoSubmissao,
    AvaliadorModalidade,
    Banner,
    CriterioAvaliacao,
    Dimensao,
    Evento,
    FluxoSubmissao,
    FotoEvento,
    HistoricoEvento,
    Internacionalizacao,
    ItemAvaliacao,
    LogProcessamentoSubmissao,
    Modalidade,
    OpcaoResposta,
    Participante,
    Pergunta,
    PublicoAlvoEvento,
    RespostaParticipante,
    Submissao,
    TipoModalidade,
    TipoParticipante,
    VersaoSubmissao,
    VideoEvento,
)
from eventos.utils import ExibirMensagem, Notificar, anexar_tabela_trabalhos_aprovados


@layout.atribuidos_a_mim()
def index_atribuidos_a_mim(request):
    pendencias = []
    if request.user.has_group_cached('Coordenador de Comunicação Sistêmico', ignore_groups_if_superuser=False):
        submissoes_sem_avaliador = Submissao.objects.exclude(versoes__pareceres__isnull=False)
        qtd_submissoes_sem_avaliador = submissoes_sem_avaliador.count()
        if qtd_submissoes_sem_avaliador > 0:
            pks = list(submissoes_sem_avaliador.values_list('modalidade__evento__id', flat=True).distinct())
            pks = ','.join(str(item) for item in pks)
            pendencias.append(
                {
                    'titulo': f'Evento{pluralize(qtd_submissoes_sem_avaliador)}',
                    'subtitulo': 'com trabalho sem avaliador',
                    'qtd': qtd_submissoes_sem_avaliador,
                    'url': f'/admin/eventos/evento/?id__in={pks}',
                }
            )
    return pendencias


@layout.quadro('Eventos', icone='calendar-alt', pode_esconder=True, global_cache=24 * 3600)
def index_quadros_eventos(quadro, request):
    if request.user.has_group_cached(['Servidor', 'Aposentado']):
        participantes_avaliadores = Participante.objects.filter(
            vinculo__user=request.user,
            avaliadormodalidade__avaliador=F('id'),
            avaliadormodalidade__avaliacaosubmissao__data_hora_nota__isnull=True,
        ).distinct()

        for participante in participantes_avaliadores:
            evento = participante.evento
            prazo = (
                evento.fluxos_submissao.filter(
                    etapa__in=[
                        EtapaPeriodoSubmissao.AVALIACAO,
                        EtapaPeriodoSubmissao.REAVALIACAO,
                    ]
                )
                .order_by('-data_fim')
                .first()
            )

            chapeu = 'Prazo indefinido'
            if prazo:
                chapeu = f'Até {prazo.data_fim.strftime("%d/%m/%Y")}'

            quadro.add_item(
                layout.ItemNoticia(
                    grupo='Avaliações de trabalhos pendentes',
                    titulo=evento.nome,
                    url=f'/eventos/autenticar_participante/{evento.id}/Avaliador/',
                    chapeu=chapeu,
                )
            )
    return quadro


@layout.quadro(
    'Calendário de Eventos',
    icone='calendar-alt',
    pode_esconder=True,
    session_cache=8 * 3600,
)
def index_quadros_calendario(quadro, request):
    hoje = date.today()
    primeiro_dia = hoje.replace(day=1)
    ultimo_dia = date(hoje.year, hoje.month, 1) - relativedelta(days=1)

    eventos = (
        Evento.objects.filter(
            deferido=True,
            ativo=True,
            data_inicio__lte=primeiro_dia,
            data_fim__gte=ultimo_dia,
        )
        .only('data_inicio', 'data_fim', 'nome')
        .order_by('data_inicio')
    )
    if eventos.exists():
        cal = Calendario()
        for evento in eventos:
            css = 'info'
            cal.adicionar_evento_calendario(evento.data_inicio, evento.data_fim, evento.nome, css)

        quadro.add_itens(
            [
                layout.ItemCalendario(calendario=cal.formato_mes(hoje.year, hoje.month)),
                layout.ItemAcessoRapido(titulo='Calendário Anual', url='/eventos/calendario_eventos/'),
            ]
        )

    return quadro


@layout.atribuidos_a_meus_grupos()
def index_atribuidos_a_meus_grupos(request):
    pendencias = []
    grupos = request.user.groups.values_list('pk', flat=True)
    dimensoes_sistemicas = Dimensao.objects.filter(grupos_avaliadores_sistemicos__in=grupos).values_list('pk', flat=True)
    dimensoes_locais = Dimensao.objects.filter(grupos_avaliadores_locais__in=grupos).values_list('pk', flat=True)
    if not (dimensoes_sistemicas or dimensoes_locais):
        return pendencias

    eventos_sistemicos = Evento.objects.filter(submetido=True, deferido__isnull=True, dimensoes__in=dimensoes_sistemicas).count()
    eventos_locais = 0
    setor = request.user.get_vinculo().setor
    if setor:
        eventos_locais = Evento.objects.filter(
            campus=setor.uo,
            submetido=True,
            deferido__isnull=True,
            dimensoes__in=dimensoes_locais,
        ).count()
    eventos_nao_avaliados = eventos_sistemicos + eventos_locais
    if eventos_nao_avaliados > 0:
        pendencias.append(
            {
                'titulo': f'Evento{pluralize(eventos_nao_avaliados)}',
                'subtitulo': 'a avaliar',
                'qtd': eventos_nao_avaliados,
                'url': eventos_sistemicos
                and '/admin/eventos/evento/?tab=tab_aguardando_aprovacao'
                or '/admin/eventos/evento/?tab=tab_aguardando_minha_aprovacao',
            }
        )

    return pendencias


@layout.quadro('Comunicado', icone='users', pode_esconder=True, global_cache=24 * 3600)
def index_quadros_banners(quadro, request):
    hoje = datetime.now()
    banner = Banner.objects.filter(data_inicio__lte=hoje, data_termino__gte=hoje).first()
    if banner and bool(Configuracao.get_valor_por_chave('comum', 'quadro_banner')) is True:
        quadro.add_item(layout.ItemTitulo(titulo=banner.titulo))
        quadro.add_item(layout.ItemImagem(titulo=banner.titulo, url=banner.link, path=banner.imagem.url))
        return quadro


@layout.servicos_anonimos()
def servicos_anonimos(request):
    servicos_anonimos = []
    servicos_anonimos.append(
        {
            'categoria': 'Consultas gerais',
            'url': '/eventos/',
            'icone': 'certificate',
            'titulo': 'Eventos',
        }
    )
    return servicos_anonimos


@rtr()
def area_publica_submissao(request):
    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    category = 'Eventos'
    title = 'Submeter trabalho para evento'
    agora = datetime.today()
    eventos = Evento.get_submissoes_abertas()

    return locals()


@rtr()
def area_publica_avaliacao(request):
    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    category = 'Eventos'
    title = 'Avaliar trabalhos de evento'
    agora = datetime.today()
    eventos = Evento.get_avaliacoes_abertas()
    calendario = []

    dia = agora
    while len(calendario) < 7:
        eventos_do_dia = eventos.filter(
            configuracao__evento__fluxos_submissao__etapa__in=[
                EtapaPeriodoSubmissao.AVALIACAO,
                EtapaPeriodoSubmissao.REAVALIACAO,
            ],
            configuracao__evento__fluxos_submissao__data_inicio__lte=dia,
            configuracao__evento__fluxos_submissao__data_fim__gte=dia,
        ).distinct()

        calendario.append((dia.strftime('%d/%m/%Y'), eventos_do_dia))
        dia = somar_dias(dia, 1)

    return locals()


@pode_submeter_trabalho_ao_evento(Evento)
@rtr()
def submeter_trabalho_passo_1(request, evento_id):
    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    evento = get_object_or_404(Evento, pk=evento_id)
    category = f'Evento: {evento.nome}'
    title = 'Submissão de trabalhos'
    areas_tematicas = evento.areas_tematicas.all().distinct()
    return locals()


@pode_submeter_trabalho_ao_evento(Evento)
@rtr()
def submeter_trabalho_passo_2(request, evento_id, area_tematica_id):
    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    evento = get_object_or_404(Evento, pk=evento_id)
    category = f'Evento: {evento.nome}'
    title = 'Submissão de trabalhos'
    area_tematica = get_object_or_404(AreaTematica, pk=area_tematica_id)
    modalidades = evento.modalidade_set.filter(
        areatematicamodalidade__area_tematica__in=[
            area_tematica_id,
        ]
    )
    return locals()


@pode_submeter_trabalho_ao_evento(Evento)
@trata_validation_error
@rtr()
def submeter_trabalho_passo_3(request, evento_id, area_tematica_id, modalidade_id):
    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    evento = get_object_or_404(Evento, pk=evento_id)
    category = f'Evento: {evento.nome}'
    title = 'Submissão de trabalhos'
    area_tematica = get_object_or_404(AreaTematica, pk=area_tematica_id)
    modalidade = get_object_or_404(Modalidade, pk=modalidade_id)
    if area_tematica not in modalidade.areas_tematicas:
        raise ValidationError(
            f'A área temática "{area_tematica.titulo}" não está inclusa nas áreas temáticas da modalidade "{modalidade.tipo.titulo}".'
        )
    if request.POST:
        email_list = request.POST.getlist('emails')
        email_list = list(set(email_list))
        autores = []
        email_nao_inscrito = []
        for email in email_list:
            if email:
                if evento.participantes.filter(
                    email__iexact=email,
                    tipo__tipo_participacao__descricao='Participante',
                ).exists():
                    participante = evento.participantes.filter(email__iexact=email).first()
                    qtd_submissoes = Submissao.objects.filter(
                        modalidade=modalidade,
                        autores_relacionados__participante__email__iexact=email,
                    ).aggregate(num_submissoes=Count('id'))['num_submissoes']
                    if qtd_submissoes > evento.configuracao.submissao_limite_trabalhos_pessoa:
                        raise ValidationError(
                            f'O participante {participante.nome} excedeu a quantidade limite de submissões de trabalho para este evento.'
                        )
                    autores.append(email)
                else:
                    email_nao_inscrito.append(email)
        if len(email_nao_inscrito) > 0:
            raise ValidationError(
                f'A submissão de trabalhos é restrita a participantes do evento. O(s) autor(es) a seguir não está(ão) inscrito(s) no evento na qualidade de Participante: {", ".join(email_nao_inscrito)}'
            )
        if len(autores) > evento.configuracao.submissao_limite_autores:
            raise ValidationError(f'A quantidade de autores informada ({len(autores)}) é maior que o limite máximo de autores por trabalho.')
        if len(autores) == 0:
            raise ValidationError('Nenhum participante inscrito foi localizado com os emails informados.')

        request.session['autores'] = autores
        return redirect(
            reverse(
                'submeter_trabalho_passo_4',
                args=(evento.pk, area_tematica_id, modalidade_id),
            )
        )

    return locals()


@pode_submeter_trabalho_ao_evento(Evento)
@trata_validation_error
@rtr()
def submeter_trabalho_passo_4(request, evento_id, area_tematica_id, modalidade_id):
    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    evento = get_object_or_404(Evento, pk=evento_id)
    category = f'Evento: {evento.nome}'
    title = 'Submissão de trabalhos'
    modalidade = get_object_or_404(Modalidade, pk=modalidade_id)
    area_tematica = get_object_or_404(AreaTematica, pk=area_tematica_id)
    if area_tematica not in modalidade.areas_tematicas:
        raise ValidationError(
            f'A área temática "{area_tematica.titulo}" não está inclusa nas áreas temáticas da modalidade "{modalidade.tipo.titulo}".'
        )
    form = SubmissaoForm(
        request.POST or None,
        request.FILES or None,
        evento=evento,
        area_tematica=area_tematica,
        modalidade=modalidade,
    )
    # Obtém os emails dos autores e os respectivos tipos de autor armazenados na sessão
    email_autores = request.session.get('autores', [])
    autores_tipo = request.session.get('autores_tipo', {})
    autores = evento.participantes.filter(email__in=email_autores, tipo__tipo_participacao__descricao='Participante')
    if request.method == 'POST':
        if form.is_valid():
            autor_correspondente = request.POST.get('autor_correspondente', None)
            form.save(autores, autores_tipo, autor_correspondente)
            Notificar.comprovante_de_submissao(form.instance)
            # Remove os dados armazenados na sessão após a submissão
            request.session.pop('autores', None)
            request.session.pop('autores_tipo', None)
            request.session.modified = True  # Garante que as alterações sejam salvas
            submissao = form.instance
            return redirect(reverse('area_publica_confirmacao_submissao', args=(submissao.pk,)))

    return locals()


@pode_submeter_trabalho_ao_evento(Evento)
@rtr()
def area_publica_confirmacao_submissao(request, submissao_id):
    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    submissao = get_object_or_404(Submissao, pk=submissao_id)
    category = _('Evento')
    title = submissao.modalidade.evento.nome
    return locals()


@rtr()
def reenviar_confirmacao_inscricao(request, evento_id, participante_id):
    participante = get_object_or_404(Participante, pk=participante_id)
    if participante.evento.id != evento_id:
        messages.error(request, 'Participante não foi localizado neste evento.')
    else:
        Notificar.inscricao_no_evento(participante.evento, participante)
        messages.success(request, 'Email com dados de acesso foi enviado ao participante.')
    return redirect(reverse('area_do_participante', args=(participante.evento.pk,)))


@rtr()
def area_do_participante(request, evento_id):
    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    evento = get_object_or_404(Evento, pk=evento_id)
    category = f'Evento: {evento.nome}'
    title = 'Área do participante'
    form_busca = ConsultaParticipanteForm(request.POST or None)
    form_login = LoginParticipanteForm(request.POST or None, evento=evento)
    if form_login.is_valid():
        participante_logado = form_login.autenticar()
        if participante_logado:
            request.session['participante_logado_id'] = participante_logado.pk
            return redirect(reverse('perfil_do_participante', args=(evento.pk,)))
        else:
            messages.error(request, 'Email ou chave de acesso incorretos.')

    if form_busca.is_valid():
        email = form_busca.cleaned_data.get('email')
        cpf = form_busca.cleaned_data.get('cpf')
        participantes = Participante.objects.filter(evento=evento).filter(Q(cpf=cpf) | Q(email=email))
        participante_encontrado_pk = None
        if participantes.exists():
            participante_encontrado_pk = participantes.first().pk
            msg_resultado = 'Participante localizado no evento. Para acessar a área privada, faça login informando email e chave de acesso.'
            form_login = LoginParticipanteForm(request.GET or None, evento=evento, initial={'email': email})
        else:
            msg_resultado = 'Nenhum participante foi localizado com este CPF/Email.'
    return locals()


@rtr()
def autenticar_participante(request, evento_id):
    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    evento = get_object_or_404(Evento, pk=evento_id)
    category = f'Evento: {evento.nome}'
    title = 'Autenticar participante'
    form = LoginParticipanteForm(request.POST or None, evento=evento)
    if form.is_valid():
        participante_logado = form.autenticar()
        if participante_logado:
            request.session['participante_logado_id'] = participante_logado.pk
            request.session['participante_logado_eh_avaliador_de_trabalho'] = participante_logado.tipo.eh_avaliador_de_trabalho()
            redirect_to = request.GET.get('next')
            if redirect_to and redirect_to.startswith('/eventos/'):
                return redirect(redirect_to)
            if participante_logado.tipo.eh_avaliador_de_trabalho():
                return redirect(reverse('listar_trabalhos_submetidos_ao_avaliador', args=(evento.pk,)))
            else:
                return redirect(reverse('perfil_do_participante', args=(evento.pk,)))
        else:
            messages.error(request, 'Login ou chave de acesso incorretos.')
    return locals()


@rtr()
def perfil_do_participante(request, evento_id):
    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    evento = get_object_or_404(Evento, pk=evento_id)
    category = f'Evento: {evento.nome}'
    title = 'Perfil do participante'
    participante_logado_id = request.session.get('participante_logado_id')
    if not participante_logado_id:
        return httprr(
            reverse('autenticar_participante', args=(evento.pk,)),
            'Usuário não autenticado.',
            'error',
        )
    participante_logado = get_object_or_404(Participante, pk=participante_logado_id)
    if participante_logado.evento != evento:
        return httprr(
            reverse('autenticar_participante', args=(evento.pk,)),
            'Você não tem permissão sobre este evento.',
            'error',
        )
    avaliacao_disponivel = evento.get_perguntas_avaliacao().exists()
    avaliacao_realizada = RespostaParticipante.objects.filter(
        participante=participante_logado,
        pergunta__tipo_questionario=TipoQuestionario.AVALIACAO,
    ).exists()
    avaliacoes_respondidas = []
    if avaliacao_realizada:
        respostas_avaliacao = list(
            RespostaParticipante.objects.filter(
                participante=participante_logado,
                pergunta__tipo_questionario=TipoQuestionario.AVALIACAO,
            )
            .select_related('pergunta', 'opcao_resposta')
            .order_by('pergunta__ordem', 'id')
        )
        respostas_por_pergunta = defaultdict(list)
        for resposta in respostas_avaliacao:
            respostas_por_pergunta[resposta.pergunta_id].append(resposta)

        perguntas_avaliacao = list(evento.get_perguntas_avaliacao().order_by('ordem', 'id'))
        respostas = []
        for pergunta in perguntas_avaliacao:
            respostas_pergunta = respostas_por_pergunta.get(pergunta.id, [])
            if not respostas_pergunta:
                valor = ''
            elif pergunta.tipo_pergunta == TipoPergunta.MULTIPLA_ESCOLHA:
                valor = ', '.join([resposta.opcao_resposta.texto for resposta in respostas_pergunta if resposta.opcao_resposta])
            elif pergunta.tipo_pergunta in (TipoPergunta.OBJETIVA, TipoPergunta.ESCALA):
                valor = respostas_pergunta[0].opcao_resposta.texto if respostas_pergunta[0].opcao_resposta else ''
            elif pergunta.numerico:
                valor = respostas_pergunta[0].resposta_numero
            else:
                valor = respostas_pergunta[0].resposta_texto
            respostas.append({'pergunta': pergunta, 'valor': valor})

        avaliacoes_respondidas.append({'respostas': respostas})
    return locals()


@rtr()
@transaction.atomic
def responder_avaliacao_evento(request, evento_id):
    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    evento = get_object_or_404(Evento, pk=evento_id)
    category = f'Evento: {evento.nome}'
    title = 'Responder avaliação'

    participante_logado_id = request.session.get('participante_logado_id')
    if not participante_logado_id:
        params = {'next': request.get_full_path()}
        email = request.GET.get('email')
        if email:
            params['email'] = email
        return redirect(f'{reverse("autenticar_participante", args=(evento.pk,))}?{urlencode(params)}')

    participante_logado = get_object_or_404(Participante, pk=participante_logado_id)
    if participante_logado.evento != evento:
        return httprr(
            reverse('autenticar_participante', args=(evento.pk,)),
            'Você não tem permissão sobre este evento.',
            'error',
        )

    perguntas_avaliacao = evento.get_perguntas_avaliacao().order_by('ordem', 'id')
    if not perguntas_avaliacao.exists():
        messages.warning(request, 'Este evento ainda não possui avaliação configurada.')
        return redirect(reverse('perfil_do_participante', args=(evento.pk,)))

    avaliacao_realizada = RespostaParticipante.objects.filter(
        participante=participante_logado,
        pergunta__tipo_questionario=TipoQuestionario.AVALIACAO,
    ).exists()
    if avaliacao_realizada:
        messages.info(request, 'Você já respondeu a avaliação deste evento.')
        return redirect(reverse('perfil_do_participante', args=(evento.pk,)))

    form = AvaliacaoParticipanteForm(evento=evento, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.processar(participante_logado)
        messages.success(request, 'Avaliação enviada com sucesso.')
        return redirect(reverse('perfil_do_participante', args=(evento.pk,)))

    return locals()


@rtr()
def visualizar_revisoes(request, evento_id, submissao_id):
    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    evento = get_object_or_404(Evento, pk=evento_id)
    category = f'Evento: {evento.nome}'
    title = 'Revisões do trabalho'
    participante_logado_id = request.session.get('participante_logado_id')
    if not participante_logado_id:
        return httprr(
            reverse('autenticar_participante', args=(evento.pk,)),
            'Usuário não autenticado.',
            'error',
        )
    participante_logado = get_object_or_404(Participante, pk=participante_logado_id)
    if participante_logado.evento != evento:
        return httprr(
            reverse('autenticar_participante', args=(evento.pk,)),
            'Você não tem permissão sobre este evento.',
            'error',
        )
    submissao = get_object_or_404(Submissao, pk=submissao_id)
    return locals()


@rtr()
def submeter_nova_versao(request, evento_id, submissao_id):
    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    evento = get_object_or_404(Evento, pk=evento_id)
    category = f'Evento: {evento.nome}'
    title = 'Submeter nova versão'
    participante_logado_id = request.session.get('participante_logado_id')
    if not participante_logado_id:
        return httprr(
            reverse('autenticar_participante', args=(evento.pk,)),
            'Usuário não autenticado.',
            'error',
        )
    participante_logado = get_object_or_404(Participante, pk=participante_logado_id)
    if participante_logado.evento != evento:
        return httprr(
            reverse('autenticar_participante', args=(evento.pk,)),
            'Você não tem permissão sobre este evento.',
            'error',
        )
    submissao = get_object_or_404(Submissao, pk=submissao_id)
    if submissao.situacao != SituacaoSubmissao.CORRECOES_SOLICITADAS:
        return httprr(
            reverse('perfil_do_participante', args=(evento.pk,)),
            'Submissão não está com correções solicitadas.',
            'error',
        )

    versao = submissao.get_ultima_versao()
    form = SubmeterNovaVersaoForm(request.POST or None, request.FILES or None, instance=versao)
    if form.is_valid():
        form.save()
        return httprr(
            reverse('perfil_do_participante', args=(evento.pk,)),
            'Submissão realizada com sucesso.',
            'success',
        )
    return locals()


@rtr()
def atualizar_participante(request, evento_id):
    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    evento = get_object_or_404(Evento, pk=evento_id)
    category = f'Evento: {evento.nome}'
    title = 'Atualizar dados do participante'
    participante_logado_id = request.session.get('participante_logado_id')
    if not participante_logado_id:
        return httprr(
            reverse('autenticar_participante', args=(evento.pk,)),
            'Usuário não autenticado.',
            'error',
        )
    participante_logado = get_object_or_404(Participante, pk=participante_logado_id)
    if participante_logado.evento != evento:
        return httprr(
            reverse('autenticar_participante', args=(evento.pk,)),
            'Você não tem permissão sobre este evento.',
            'error',
        )
    form = PerfilParticipanteForm(request.POST or None, request.FILES or None, instance=participante_logado)
    if form.is_valid():
        form.save()
        return httprr('..', 'Dados do participante atualizado com sucesso.')
    return locals()


@verifica_avaliador_logado(Evento, AvaliacaoSubmissao)
@rtr()
def listar_trabalhos_submetidos_ao_avaliador(request, evento_id):
    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    evento = get_object_or_404(Evento, pk=evento_id)
    category = f'Evento: {evento.nome}'
    title = 'Avaliar trabalhos'
    participante_logado_id = request.session.get('participante_logado_id')
    participante_logado = get_object_or_404(Participante, pk=participante_logado_id)
    submissoes_avaliadas = AvaliacaoSubmissao.objects.filter(avaliador_modalidade__avaliador_id=participante_logado_id, nota__isnull=False).order_by(
        'versao__submissao_id', 'versao_id'
    )
    submissoes_nao_avaliadas = (
        AvaliacaoSubmissao.objects.filter(avaliador_modalidade__avaliador_id=participante_logado_id, nota__isnull=True)
        .exclude(versao__submissao__situacao=SituacaoSubmissao.REMOVIDO_DUPLICIDADE)
        .order_by('versao__submissao_id', 'versao_id')
    )
    return locals()


@transaction.atomic
@verifica_avaliador_logado(Evento, AvaliacaoSubmissao)
@trata_validation_error
@rtr()
def avaliar_trabalhos_submetidos(request, avaliacao_submissao_id):
    title = 'Avaliar trabalhos submetidos'
    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    avaliacao_submissao = get_object_or_404(AvaliacaoSubmissao, pk=avaliacao_submissao_id)
    participante_logado_id = request.session.get('participante_logado_id')
    evento = avaliacao_submissao.avaliador_modalidade.modalidade.evento
    if avaliacao_submissao.avaliador_modalidade.avaliador.id != participante_logado_id:
        messages.error(request, 'Você não tem permissão para avaliar este trabalho.')
        return redirect(evento.get_url_inscricao())

    # Obtém o fluxo atual para determinar os critérios corretos de avaliação
    hoje = date.today()
    fluxo_atual = evento.fluxos_submissao.filter(
        etapa__in=[
            EtapaPeriodoSubmissao.AVALIACAO,
            EtapaPeriodoSubmissao.REAVALIACAO,
            EtapaPeriodoSubmissao.AVALIACAO_PRESENCIAL,
        ],
        data_inicio__lte=hoje,
        data_fim__gte=hoje,
    ).first()

    if not fluxo_atual:
        messages.error(
            request,
            'Avaliação não permitida, pois o período de avaliações deste evento está finalizado.',
        )
        return redirect(evento.get_url_inscricao())

    participante_logado = get_object_or_404(Participante, pk=participante_logado_id)
    items = CriterioAvaliacao.objects.filter(
        modalidade=avaliacao_submissao.avaliador_modalidade.modalidade,
        etapa=fluxo_atual.etapa,
    )
    items_avaliados = ItemAvaliacao.objects.filter(avaliacao=avaliacao_submissao).values('criterio_avaliacao', 'nota')
    items_avaliados = {item['criterio_avaliacao']: item['nota'] for item in items_avaliados}
    recomendacoes = evento.get_recomendacoes_disponiveis()
    if request.POST:
        salvou = False
        try:
            with transaction.atomic():
                nota_total = 0.0
                for campo, valor in request.POST.items():
                    if campo.startswith('nota_'):
                        criterio_avaliacao_id = campo.split('_')[1]
                        criterio_avaliacao = CriterioAvaliacao.objects.get(pk=criterio_avaliacao_id)
                        valor = valor.replace(',', '.')
                        if not (criterio_avaliacao.nota_minima <= float(valor) <= criterio_avaliacao.nota_maxima):
                            raise ValidationError(
                                f'A nota para o critério de avaliação "{criterio_avaliacao.descricao}" deve estar entre {criterio_avaliacao.nota_minima} e {criterio_avaliacao.nota_maxima}.'
                            )

                        ItemAvaliacao.objects.update_or_create(
                            avaliacao=avaliacao_submissao,
                            criterio_avaliacao_id=criterio_avaliacao_id,
                            defaults={'nota': float(valor)},
                        )
                        salvou = True
                        nota_total += float(valor)
                    if campo == 'observacao':
                        AvaliacaoSubmissao.objects.filter(pk=avaliacao_submissao.pk).update(observacao=valor)
                    if campo == 'observacao_interna':
                        AvaliacaoSubmissao.objects.filter(pk=avaliacao_submissao.pk).update(observacao_interna=valor)
                    if campo == 'recomendacao':
                        AvaliacaoSubmissao.objects.filter(pk=avaliacao_submissao.pk).update(recomendacao=valor)

                if evento.estah_em_periodo_avaliacao_presencial():
                    avaliacao_nota_aprovacao = evento.configuracao.avaliacao_nota_aprovacao
                    if nota_total < avaliacao_nota_aprovacao:
                        raise ValidationError(
                            f'A soma das notas atribuídas ({nota_total}) é inferior à nota mínima de aprovação ({avaliacao_nota_aprovacao}).'
                        )
                if salvou:
                    messages.success(request, 'Dados da avaliação salvos com sucesso.')
            return redirect(
                reverse(
                    'listar_trabalhos_submetidos_ao_avaliador',
                    args=(avaliacao_submissao.avaliador_modalidade.modalidade.evento.pk,),
                )
            )
        except ValidationError as e:
            messages.error(request, e)

    return locals()


@transaction.atomic
@verifica_avaliador_logado(Evento, AvaliacaoSubmissao)
@trata_validation_error
@rtr()
def zerar_avaliacao_trabalhos_submetido(request, avaliacao_submissao_id):
    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    avaliacao_submissao = get_object_or_404(AvaliacaoSubmissao, pk=avaliacao_submissao_id)
    participante_logado_id = request.session.get('participante_logado_id')
    evento = avaliacao_submissao.avaliador_modalidade.modalidade.evento
    if avaliacao_submissao.avaliador_modalidade.avaliador.id != participante_logado_id:
        messages.error(request, 'Você não tem permissão para avaliar este trabalho.')
        return redirect(evento.get_url_inscricao())

    # Obtém o fluxo atual para determinar os critérios corretos de avaliação
    hoje = date.today()
    fluxo_atual = evento.fluxos_submissao.filter(
        etapa__in=[
            EtapaPeriodoSubmissao.AVALIACAO,
            EtapaPeriodoSubmissao.REAVALIACAO,
            EtapaPeriodoSubmissao.AVALIACAO_PRESENCIAL,
        ],
        data_inicio__lte=hoje,
        data_fim__gte=hoje,
    ).first()

    if not fluxo_atual:
        messages.error(
            request,
            'Avaliação não permitida, pois o período de avaliações deste evento está finalizado.',
        )
        return redirect(evento.get_url_inscricao())

    participante_logado = get_object_or_404(Participante, pk=participante_logado_id)
    items = CriterioAvaliacao.objects.filter(
        modalidade=avaliacao_submissao.avaliador_modalidade.modalidade,
        etapa=fluxo_atual.etapa,
    )
    if request.POST:
        try:
            with transaction.atomic():
                for criterio_avaliacao in items:
                    ItemAvaliacao.objects.update_or_create(
                        avaliacao=avaliacao_submissao,
                        criterio_avaliacao=criterio_avaliacao,
                        defaults={'nota': float('0.0')},
                    )
                observacao = request.POST.get('observacao')
                observacao_interna = request.POST.get('observacao_interna')
                AvaliacaoSubmissao.objects.filter(pk=avaliacao_submissao.pk).update(
                    observacao=observacao,
                    observacao_interna=observacao_interna,
                    recomendacao=Recomendacao.REJEITAR,
                )
                messages.success(request, 'Dados da avaliação salvos com sucesso.')
            return redirect(
                reverse(
                    'listar_trabalhos_submetidos_ao_avaliador',
                    args=(avaliacao_submissao.avaliador_modalidade.modalidade.evento.pk,),
                )
            )
        except ValidationError as e:
            messages.error(request, e)

    return locals()


@rtr()
def logout_participante(request):
    participante_logado_id = request.session.get('participante_logado_id')
    if participante_logado_id:
        participante_logado = get_object_or_404(Participante, pk=participante_logado_id)
        evento = participante_logado.evento
        request.session['participante_logado_id'] = None
        return httprr(
            f'{evento.get_url_inscricao()}',
            'Você foi desconectado da área privada de eventos.',
        )
    return httprr(
        '/eventos/inscricao/',
        'Você foi desconectado da área privada de eventos.',
    )


@rtr()
def area_publica(request: HttpRequest) -> dict:
    category = 'Consultas'
    title = 'Eventos'
    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    eventos_abertos = Evento.get_inscricoes_abertas()
    total_inscricoes_abertas = eventos_abertos.count()
    total_submissoes_abertas = Evento.get_submissoes_abertas().count()
    total_avaliacoes_abertas = Evento.get_avaliacoes_abertas().count()
    eventos = eventos_abertos | Evento.objects.filter(Q(deferido=True) | Q(finalizado=True))
    form = ConsultaEvento(request.POST or None)
    if form.is_valid():
        ativo = form.cleaned_data.get('ativo')
        nome = form.cleaned_data.get('nome')
        if ativo:
            eventos = eventos.filter(data_fim__gte=date.today())
        if nome:
            eventos = eventos.filter(nome__icontains=nome) | eventos.filter(apresentacao__icontains=nome)
    # Desempate pelo pk: com vários eventos na mesma data de início, a ordem entre eles variava
    # a cada consulta e a paginação repetia ou pulava eventos entre as páginas.
    eventos = eventos.order_by('-data_inicio', '-pk')

    return locals()


@rtr()
def area_publica_inscricao(request):
    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    category = _('Eventos')
    title = _('Realizar inscrição em evento')
    agora = datetime.today()
    eventos = Evento.get_inscricoes_abertas()
    calendario = []
    dia = agora
    while len(calendario) < 7:
        calendario.append(
            (
                dia.strftime('%d/%m/%Y'),
                eventos.filter(data_inicio_inscricoes__lt=dia, data_fim_inscricoes__gte=dia),
            )
        )
        dia = somar_dias(dia, 1)

    return locals()


@rtr()
def area_publica_inscricao_passo_1(request, evento_id):
    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    evento = get_object_or_404(Evento, pk=evento_id)
    category = _('Evento')
    title = evento.nome

    pode_inscrever, mensagem = evento.pode_inscrever()
    if pode_inscrever:
        request.session['dados_inscricao_eventos'] = None
        form = RealizarInscricaoEventoNacionalidadeForm(data=request.POST or None, evento=evento)
        if form.is_valid():
            form_data = {field: serialization.serialize(form.cleaned_data[field]) for field in form.cleaned_data}
            form_data.update({'passo_anterior_requerido': serialization.serialize(1)})
            request.session['dados_inscricao_eventos'] = form_data
            return redirect(reverse('area_publica_inscricao_passo_2', args=(evento.pk,)))

    return locals()


@valida_passo_inscricao(1)
@rtr()
def area_publica_inscricao_passo_2(request, evento_id, vinculo_id=None, publico_alvo_id=None):
    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    evento = get_object_or_404(Evento, pk=evento_id)
    category = _('Evento')
    title = evento.nome

    dados_inscricao_eventos = request.session.get('dados_inscricao_eventos', {})

    def obter_dados_pessoais(vinculo):
        nome = vinculo.pessoa.nome
        email = vinculo.email_pessoal
        telefone = vinculo.pessoa.telefones_pessoais
        return {
            'nome': nome,
            'email': email,
            'telefone': telefone,
        }

    def atualizar_dados_inscricao_eventos(request, chave, valor):
        dados_inscricao_eventos = request.session.get('dados_inscricao_eventos', {})
        dados_inscricao_eventos.update({chave: serialization.serialize(valor)})
        request.session['dados_inscricao_eventos'] = dados_inscricao_eventos

    if vinculo_id:
        vinculo = get_object_or_404(Vinculo, pk=vinculo_id)
        publico_alvo = get_object_or_404(PublicoAlvoEvento, pk=publico_alvo_id)
        atualizar_dados_inscricao_eventos(request, 'vinculo_id', vinculo.pk)
        atualizar_dados_inscricao_eventos(request, 'publico_alvo_id', publico_alvo_id)
        atualizar_dados_inscricao_eventos(request, 'publico_alvo_descricao', publico_alvo.descricao)
        dados_iniciais = obter_dados_pessoais(vinculo)
        form = RealizarInscricaoEventoDadosPessoaisForm(data=request.POST or None, initial=dados_iniciais)
    else:
        # Não informou vinculo
        usuario_externo = request.GET.get('usuario_externo', '0')
        cpf = serialization.deserialize(dados_inscricao_eventos.get('cpf'))
        vinculos_list = []
        exibir_lista_vinculos = False
        # Lista os vinculos possíveis
        publicos_ativos = evento.publico_alvo.filter(ativo=True).values_list('pk', flat=True)
        publicos_permitidos = PublicoAlvoEvento.objects.filter(pk__in=publicos_ativos).values_list('descricao', flat=True)
        if PublicoAlvoEvento.PUBLICO_EXTERNO in publicos_ativos:
            permite_publico_externo = True
        else:
            permite_publico_externo = False
            mensagem = f'Nenhum público-alvo encontrado para o documento informado. Públicos permitidos: {", ".join(publicos_permitidos)}'
        if cpf and usuario_externo != '1':  # Possui cpf e não selecionou usuario_externo
            if publicos_ativos:
                for vinculo in Vinculo.objects.filter(pessoa__pessoafisica__cpf=cpf, ativo=True):
                    if PublicoAlvoEvento.ESTUDANTES in publicos_ativos and vinculo.eh_aluno():
                        vinculos_list.append(
                            {
                                'vinculo': vinculo,
                                'publico_alvo': PublicoAlvoEvento.ESTUDANTES,
                                'publico_alvo_descricao': 'Estudante',
                            }
                        )
                    elif PublicoAlvoEvento.SERVIDORES in publicos_ativos and vinculo.eh_servidor():
                        vinculos_list.append(
                            {
                                'vinculo': vinculo,
                                'publico_alvo': PublicoAlvoEvento.SERVIDORES,
                                'publico_alvo_descricao': 'Servidor',
                            }
                        )
                    elif PublicoAlvoEvento.TERCEIRIZADOS in publicos_ativos and vinculo.eh_prestador():
                        vinculos_list.append(
                            {
                                'vinculo': vinculo,
                                'publico_alvo': PublicoAlvoEvento.TERCEIRIZADOS,
                                'publico_alvo_descricao': 'Terceirizado',
                            }
                        )
                    elif PublicoAlvoEvento.ESTAGIARIOS in publicos_ativos and vinculo.eh_servidor():
                        vinculos_list.append(
                            {
                                'vinculo': vinculo,
                                'publico_alvo': PublicoAlvoEvento.ESTAGIARIOS,
                                'publico_alvo_descricao': 'Estagiário',
                            }
                        )
                    elif (
                        PublicoAlvoEvento.GESTORES in publicos_ativos
                        and vinculo.eh_servidor()
                        and vinculo.relacionamento.historico_funcao().filter(data_fim_funcao__isnull=True).exists()
                    ):
                        vinculos_list.append(
                            {
                                'vinculo': vinculo,
                                'publico_alvo': PublicoAlvoEvento.GESTORES,
                                'publico_alvo_descricao': 'Gestor',
                            }
                        )

                if (len(vinculos_list) > 1) or (len(vinculos_list) == 1 and permite_publico_externo):
                    exibir_lista_vinculos = True

            if len(vinculos_list) == 0 and permite_publico_externo:
                atualizar_dados_inscricao_eventos(request, 'publico_alvo_id', PublicoAlvoEvento.PUBLICO_EXTERNO)
                atualizar_dados_inscricao_eventos(request, 'publico_alvo_descricao', 'Público Externo')
                form = RealizarInscricaoEventoDadosPessoaisForm(data=request.POST or None)
            elif len(vinculos_list) == 1 and not permite_publico_externo:
                vinculo = vinculos_list[0]['vinculo']
                publico_alvo = vinculos_list[0]['publico_alvo']
                atualizar_dados_inscricao_eventos(request, 'vinculo_id', vinculo.pk)
                atualizar_dados_inscricao_eventos(request, 'publico_alvo_id', publico_alvo)
                atualizar_dados_inscricao_eventos(request, 'publico_alvo_descricao', 'Público Externo')
                dados_iniciais = obter_dados_pessoais(vinculo)
                form = RealizarInscricaoEventoDadosPessoaisForm(data=request.POST or None, initial=dados_iniciais)
        elif permite_publico_externo:
            atualizar_dados_inscricao_eventos(request, 'publico_alvo_id', PublicoAlvoEvento.PUBLICO_EXTERNO)
            atualizar_dados_inscricao_eventos(request, 'publico_alvo_descricao', 'Público Externo')
            form = RealizarInscricaoEventoDadosPessoaisForm(data=request.POST or None)

    return locals()


@valida_passo_inscricao(1)
@rtr()
def area_publica_inscricao_passo_2_confirmacao(request, evento_id):
    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    evento = get_object_or_404(Evento, pk=evento_id)
    category = _('Evento')
    title = evento.nome
    dados_inscricao_eventos = request.session.get('dados_inscricao_eventos', {})
    form = RealizarInscricaoEventoDadosPessoaisForm(data=request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            form_data = {field: serialization.serialize(form.cleaned_data[field]) for field in form.cleaned_data}
            dados_inscricao_eventos.update(form_data)
            dados_inscricao_eventos.update({'passo_anterior_requerido': serialization.serialize(2)})
            request.session['dados_inscricao_eventos'] = dados_inscricao_eventos
            return redirect(reverse('area_publica_inscricao_passo_3', args=(evento.pk,)))
        else:
            messages.error(
                request,
                f'Verifique os erros do formulário. Detalhe: {form.errors.as_text()}',
            )
            return redirect(reverse('area_publica_inscricao_passo_2', args=(evento.pk,)))

    return locals()


@valida_passo_inscricao(2)
@rtr()
def area_publica_inscricao_passo_3(request, evento_id):
    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    evento = get_object_or_404(Evento, pk=evento_id)
    category = _('Evento')
    title = evento.nome
    dados_inscricao_eventos = request.session.get('dados_inscricao_eventos', {})
    dados_inscricao_eventos = {key: serialization.deserialize(value) if value else value for key, value in dados_inscricao_eventos.items()}
    cpf = dados_inscricao_eventos['cpf']
    passaporte = dados_inscricao_eventos['passaporte']
    form = RealizarInscricaoEventoAtividadesForm(data=request.POST or None, evento=evento, cpf=cpf, passaporte=passaporte)
    # Verifica se o fieldset 'Atividades do evento' tem campos
    if not any(field in form.fields for field in ('publico_alvo', 'forma_participacao', 'atividades')):
        form.fieldsets = tuple(fs for fs in form.fieldsets if fs[0] != _('Atividades do evento'))

    if request.method == 'POST' and form.is_valid():
        dados_inscricao_eventos = request.session.get('dados_inscricao_eventos', {})
        dados_inscricao_eventos = {key: serialization.deserialize(value) if value else value for key, value in dados_inscricao_eventos.items()}
        form_data = {field: form.cleaned_data[field] for field in form.cleaned_data}
        dados_inscricao_eventos.update(form_data)
        participante = form.processar(dados_inscricao_eventos)
        request.session['dados_inscricao_eventos'] = None
        return redirect(reverse('area_publica_confirmacao_inscricao', args=(participante.pk,)))

    return locals()


@rtr()
def area_publica_confirmacao_inscricao(request, participante_id):
    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    participante = get_object_or_404(Participante, pk=participante_id)
    evento = get_object_or_404(Evento, pk=participante.evento.pk)
    category = _('Evento')
    title = evento.nome

    return locals()


@rtr()
@login_required()
def calendario_eventos(request):
    title = 'Calendário de Eventos por Campus'
    uo = request.user.get_relacionamento().setor and request.user.get_relacionamento().setor.uo
    form = CalendarioForm(request.POST or None, initial={'uo': uo and uo.pk or None})
    # Numa base sem o ``Ano`` do exercício corrente (instalação nova/testes) o ``.get()``
    # estourava ``Ano.DoesNotExist`` (500); o fallback só alimenta o filtro e o calendário.
    ano = Ano.objects.filter(ano=date.today().year).first() or Ano(ano=date.today().year)

    if form.is_valid():
        if form.cleaned_data.get('ano'):
            ano = form.cleaned_data['ano']
        uo = form.cleaned_data['uo']

    eventos = Evento.objects.filter(
        ativo=True,
        deferido=True,
        data_inicio__year__lte=ano.ano,
        data_fim__year__gte=ano.ano,
    )
    if uo:
        eventos = eventos.filter(campus=uo)

    calendario = Calendario(tipos_eventos_default=False)
    calendario.adicionar_tipo_evento('info', 'Evento/Data Comemorativa')
    for evento in eventos:
        css = 'info'
        if uo:
            calendario.adicionar_evento_calendario(evento.data_inicio, evento.data_fim, evento.nome, css)
        else:
            calendario.adicionar_evento_calendario(
                evento.data_inicio,
                evento.data_fim,
                f'{evento.nome} ({evento.campus})',
                css,
            )

    calendario_ano = calendario.formato_ano(ano.ano)
    return locals()


@login_required()
@rtr()
def listar_respostas_participantes(request, evento_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para realizar essa operação neste evento.')
    title = evento.nome
    return locals()


@login_required()
@rtr()
def exportar_respostas_participantes(request, evento_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para exportar respostas.')

    # Perguntas configuradas no evento
    perguntas = Pergunta.objects.filter(evento=evento, tipo_questionario=TipoQuestionario.INSCRICAO).order_by('ordem')

    # Cabeçalho da planilha
    headers = ['Nome', 'E-mail', 'Tipo de Participação']
    headers += [p.titulo for p in perguntas]

    rows = []
    rows.append(headers)

    participantes = Participante.objects.filter(evento=evento).select_related('tipo')
    respostas_participantes = RespostaParticipante.objects.filter(participante__in=participantes, pergunta__in=perguntas).select_related(
        'participante', 'pergunta'
    )

    respostas_por_participante = {}
    for resposta in respostas_participantes:
        participante_id = resposta.participante_id
        pergunta_id = resposta.pergunta_id
        if participante_id not in respostas_por_participante:
            respostas_por_participante[participante_id] = {}
        respostas_por_participante[participante_id][pergunta_id] = resposta.get_respostas()

    for participante in participantes:
        linha = [
            participante.nome,
            participante.email,
            participante.tipo.tipo_participacao.descricao if participante.tipo else '',
        ]

        # Acessar respostas do participante a partir do dicionário em memória
        respostas_do_participante = respostas_por_participante.get(participante.id, {})

        for pergunta in perguntas:
            linha.append(respostas_do_participante.get(pergunta.id, ''))

        rows.append(linha)

    # Retorna resposta como XLS
    return XlsResponse(rows, name=f'respostas_evento_{evento_id}', encoding='utf-8')


@login_required()
@rtr()
def exportar_respostas_avaliacao(request, evento_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para exportar respostas da avaliação.')

    anonimizar = request.GET.get('anonimo') == '1'
    perguntas = list(Pergunta.objects.filter(evento=evento, tipo_questionario=TipoQuestionario.AVALIACAO).order_by('ordem', 'id'))
    if not perguntas:
        return httprr(
            reverse('evento', args=(evento.id,)) + '?tab=avaliacao',
            'Não há perguntas de avaliação configuradas.',
            'warning',
        )

    headers = ['Respondente']
    if not anonimizar:
        headers = ['Nome', 'E-mail', 'Tipo de Participação']
    headers += [pergunta.titulo for pergunta in perguntas]
    rows = [headers]

    respondentes = list(
        Participante.objects.filter(
            evento=evento,
            respostaparticipante__pergunta__tipo_questionario=TipoQuestionario.AVALIACAO,
        )
        .select_related('tipo', 'tipo__tipo_participacao')
        .distinct()
        .order_by('id')
    )
    respondente_index = {participante.id: index for index, participante in enumerate(respondentes, start=1)}

    respostas = list(
        RespostaParticipante.objects.filter(
            participante__in=respondentes,
            pergunta__in=perguntas,
        )
        .select_related('pergunta', 'opcao_resposta')
        .order_by('participante_id', 'pergunta__ordem', 'id')
    )
    respostas_por_participante = defaultdict(lambda: defaultdict(list))
    for resposta in respostas:
        respostas_por_participante[resposta.participante_id][resposta.pergunta_id].append(resposta)

    for participante in respondentes:
        if anonimizar:
            linha = [f'Respondente #{respondente_index[participante.id]}']
        else:
            tipo = participante.tipo.tipo_participacao.descricao if participante.tipo else ''
            linha = [participante.nome, participante.email, tipo]

        respostas_participante = respostas_por_participante.get(participante.id, {})
        for pergunta in perguntas:
            respostas_pergunta = respostas_participante.get(pergunta.id, [])
            if not respostas_pergunta:
                valor = ''
            elif pergunta.tipo_pergunta == TipoPergunta.MULTIPLA_ESCOLHA:
                valor = ', '.join([resposta.opcao_resposta.texto for resposta in respostas_pergunta if resposta.opcao_resposta])
            elif pergunta.tipo_pergunta in (TipoPergunta.OBJETIVA, TipoPergunta.ESCALA):
                valor = respostas_pergunta[0].opcao_resposta.texto if respostas_pergunta[0].opcao_resposta else ''
            elif pergunta.numerico:
                valor = respostas_pergunta[0].resposta_numero
            else:
                valor = respostas_pergunta[0].resposta_texto
            linha.append(valor)
        rows.append(linha)

    sufixo = 'anonimo' if anonimizar else 'identificado'
    return XlsResponse(rows, name=f'avaliacao_evento_{evento_id}_{sufixo}', encoding='utf-8')


@login_required()
@rtr()
def listar_avaliadores_sem_trabalhos(request, evento_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para realizar essa operação neste evento.')
    title = 'Avaliadores sem trabalhos vinculados'

    avaliadores_com_avaliacao = AvaliacaoSubmissao.objects.filter(versao__submissao__modalidade__evento_id=evento_id).values_list(
        'avaliador_modalidade_id', flat=True
    )
    avaliadores_modalidade = (
        AvaliadorModalidade.objects.filter(modalidade__evento_id=evento_id).exclude(id__in=avaliadores_com_avaliacao).order_by('avaliador__nome')
    )
    return locals()


@login_required()
@rtr()
def listar_avaliadores_com_avaliacoes_pendentes(request, evento_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para realizar essa operação neste evento.')
    title = 'Avaliadores com avaliações pendentes'

    avaliacoes_submissao = (
        AvaliacaoSubmissao.objects.filter(versao__submissao__modalidade__evento_id=evento_id, nota__isnull=True)
        .order_by('avaliador_modalidade__avaliador__nome')
        .select_related('avaliador_modalidade__avaliador')
    )

    return locals()


@login_required()
@rtr()
def exibir_informacoes_participante(request, participante_id):
    participante = get_object_or_404(Participante, pk=participante_id)
    if not participante.evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para realizar essa operação neste evento.')
    title = participante.nome
    hash = signing.dumps({'participante_id': participante_id})
    return locals()


@rtr()
@permission_required('eventos.change_evento')
def listar_atividades_participante(request, evento_id, participante_id):
    """
    View otimizada para listar apenas as atividades e modalidades de um participante específico.
    Refatorado do template evento_participantes.html para melhor performance.
    """
    evento = Evento.objects.filter(pk=evento_id).select_related('subtipo').first()
    if not evento:
        raise Http404('Evento não encontrado.')
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão acessar esta página.')

    # Buscar participante com relacionamentos otimizados
    participante = (
        Participante.objects.filter(pk=participante_id, evento=evento)
        .select_related('tipo', 'tipo__tipo_participacao')
        .prefetch_related(
            Prefetch(
                'avaliadormodalidade_set',
                queryset=AvaliadorModalidade.objects.select_related('modalidade', 'modalidade__tipo').prefetch_related('areas_tematicas'),
            ),
            'atividades',
        )
        .first()
    )

    if not participante:
        raise Http404('Participante não encontrado.')

    # Variáveis necessárias pelo template
    title = f'Atividades de {participante.nome}'
    pode_gerenciar = evento.pode_gerenciar(request.user)
    tipo_participante = participante.tipo

    # Verificar se atingiu configurações mínimas (para modalidades de avaliador)
    atingiu_configuracoes_minimas_submissao = evento.atingiu_configuracoes_minimas_para_submissao_trabalhos()

    return locals()


@login_required()
@rtr()
def enviar_qrcode_participante(request, evento_id, pks):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para realizar essa operação neste evento.')
    if not evento.utilizar_qr_code:
        raise PermissionDenied('Este evento não está configurado para utilizar QR Code.')
    pks = pks.split('_')
    for participante in evento.participantes.filter(pk__in=pks):
        Notificar.enviar_qrcode_participante(participante)

    url = request.META.get('HTTP_REFERER', f'/eventos/evento/{evento_id}/?tab=participante')
    return httprr(url, 'QR Codes enviados.', tag='success')


@login_required()
@rtr()
def gerar_etiqueta_participante(request, participante_id):
    participante = get_object_or_404(Participante, pk=participante_id)
    temp_qr_file = participante.gerar_qr_code()
    buffer = BytesIO()

    # Tamanho etiqueta 29mm x 90mm
    etiqueta_size = (90 * mm, 29 * mm)
    c = canvas.Canvas(buffer, pagesize=etiqueta_size)
    _page_width, _page_height = etiqueta_size

    # Configurar a fonte e o tamanho do texto
    c.setFont('Helvetica', 12)

    # Definir a largura e altura da etiqueta
    etiqueta_width = 90 * mm
    etiqueta_height = 29 * mm

    # Definir a área da etiqueta com 12cm de margem do topo e 3cm de margem esquerda
    etiqueta_x = 0 * cm
    etiqueta_y = 0 * cm

    # Desenhar um retângulo como área da etiqueta
    c.rect(etiqueta_x, etiqueta_y, etiqueta_width, etiqueta_height)

    # Redimensionar o QR Code para caber na área da etiqueta (um pouco maior)
    qr_code_width = 27 * mm  # Largura do QR Code
    qr_code_height = 27 * mm  # Altura do QR Code

    # Posicionar o QR Code na área da etiqueta (um pouco mais à esquerda)
    qr_code_x = etiqueta_x + 0.25 * cm
    qr_code_y = etiqueta_y + (etiqueta_height - qr_code_height) / 2

    # Redimensionar o QR Code
    c.drawInlineImage(
        temp_qr_file.name,
        qr_code_x,
        qr_code_y,
        width=qr_code_width,
        height=qr_code_height,
    )

    # Calcular as coordenadas para centralizar verticalmente o texto
    text_y = etiqueta_y + (etiqueta_height - 0.5 * cm) / 2  # Alinhado verticalmente com a etiqueta
    text_x = qr_code_x + qr_code_width + 0.5 * cm  # Espaço entre o QR Code e o texto

    # Desenhar o nome do participante à direita do QR Code
    c.drawString(text_x, text_y, participante.get_nome_curto())

    # Desenhar o tipo do participante ao lado do nome
    c.drawString(text_x, text_y - 0.5 * cm, participante.tipo.tipo_participacao.descricao)

    c.save()
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{participante.id}_etiqueta.pdf"'

    # Fechar o arquivo temporário
    temp_qr_file.close()
    return response


@rtr()
@permission_required('eventos.change_evento')
def evento(request, evento_id):
    evento = Evento.objects.filter(pk=evento_id).select_related('coordenador', 'campus').first()
    if not evento:
        raise Http404('Evento não encontrado;')
    title = evento.nome
    queries = {}
    eh_editavel = evento.ativo and evento.deferido
    eh_organizador = evento.eh_organizador(request.user)
    pode_gerenciar = evento.pode_gerenciar(request.user)
    pode_avaliar = evento.pode_avaliar(request.user)
    pode_finalizar = evento.pode_finalizar(request.user)
    pode_confirmar_presenca = evento.pode_confirmar_presenca(request.user)
    participacoes_inconsistentes = evento.get_participacoes_inconsistentes()

    # Otimização: usar campos desnormalizados
    tem_modalidades = evento.possui_modalidades
    configurou_criterios_avaliacao = evento.possui_configuracao_criterios_completa
    alerta_criterio_faltante = None
    alerta_criterios_desbalanceados = None
    if pode_gerenciar and not configurou_criterios_avaliacao:
        # Modo debug: mostra alertas detalhados
        (
            configurou_criterios_avaliacao,
            alerta_criterio_faltante,
            alerta_criterios_desbalanceados,
        ) = evento.configurou_criterios_avaliacao()

    # Buscar modalidades do banco (sempre buscar para garantir dados atualizados)
    modalidades = Modalidade.objects.filter(evento=evento)

    # Nota: Os flags desnormalizados são mantidos em sincronia automaticamente
    # através de signals (eventos/signals.py). Se houver inconsistência, ela será
    # corrigida automaticamente na próxima mudança ou via comando de management.

    if pode_gerenciar and eh_editavel:
        if 'excluir_anexo' in request.GET:
            evento.anexoevento_set.filter(pk=request.GET['excluir_anexo']).delete()
            return httprr(
                f'/eventos/evento/{evento_id}/?tab=anexos',
                'Anexo excluído com sucesso.',
            )

    perguntas_inscricao = evento.get_perguntas_inscricao().prefetch_related('opcaoresposta_set').order_by('ordem', 'id')
    perguntas_avaliacao = evento.get_perguntas_avaliacao().prefetch_related('opcaoresposta_set').order_by('ordem', 'id')
    avaliacao_tem_perguntas = perguntas_avaliacao.exists()
    avaliacao_configurada_corretamente = evento.perguntas_corretamente_configuradas(TipoQuestionario.AVALIACAO)
    avaliacao_total_respondentes = 0
    avaliacao_relatorio_geral = []
    avaliacao_respostas_individuais = []

    if avaliacao_tem_perguntas and (pode_gerenciar or pode_avaliar):
        respostas_avaliacao = list(
            RespostaParticipante.objects.filter(
                pergunta__evento=evento,
                pergunta__tipo_questionario=TipoQuestionario.AVALIACAO,
            )
            .select_related('pergunta', 'opcao_resposta', 'participante')
            .order_by('participante_id', 'pergunta__ordem', 'id')
        )
        respostas_por_pergunta = defaultdict(list)
        respostas_por_participante = defaultdict(lambda: defaultdict(list))
        for resposta in respostas_avaliacao:
            respostas_por_pergunta[resposta.pergunta_id].append(resposta)
            respostas_por_participante[resposta.participante_id][resposta.pergunta_id].append(resposta)

        respondentes = list(
            Participante.objects.filter(
                evento=evento,
                respostaparticipante__pergunta__tipo_questionario=TipoQuestionario.AVALIACAO,
            )
            .distinct()
            .order_by('id')
        )
        avaliacao_total_respondentes = len(respondentes)
        respondente_index = {participante.id: index for index, participante in enumerate(respondentes, start=1)}

        for pergunta in perguntas_avaliacao:
            respostas_pergunta = respostas_por_pergunta.get(pergunta.id, [])
            item_relatorio = {
                'pergunta': pergunta,
                'tipo_pergunta': pergunta.tipo_pergunta,
                'respostas_textuais': [],
                'contagem_opcoes': [],
            }
            if pergunta.tipo_pergunta in (
                TipoPergunta.SUBJETIVA_LONGA,
                TipoPergunta.SUBJETIVA_CURTA,
            ):
                for resposta in respostas_pergunta:
                    texto = resposta.resposta_numero if pergunta.numerico else resposta.resposta_texto
                    if texto not in (None, ''):
                        item_relatorio['respostas_textuais'].append(texto)
            else:
                opcoes = list(pergunta.opcaoresposta_set.all().order_by('ordem'))
                if len(opcoes) < 2:
                    opcoes = list(evento.opcoes_gerais_de_resposta().order_by('ordem'))
                contagem_por_opcao = defaultdict(int)
                for resposta in respostas_pergunta:
                    if resposta.opcao_resposta_id:
                        contagem_por_opcao[resposta.opcao_resposta_id] += 1
                item_relatorio['contagem_opcoes'] = [(opcao, contagem_por_opcao.get(opcao.id, 0)) for opcao in opcoes]
            avaliacao_relatorio_geral.append(item_relatorio)

        for participante in respondentes:
            respostas = []
            for pergunta in perguntas_avaliacao:
                respostas_participante = respostas_por_participante.get(participante.id, {}).get(pergunta.id, [])
                if not respostas_participante:
                    valor = ''
                elif pergunta.tipo_pergunta == TipoPergunta.MULTIPLA_ESCOLHA:
                    valor = ', '.join([resposta.opcao_resposta.texto for resposta in respostas_participante if resposta.opcao_resposta])
                elif pergunta.tipo_pergunta in (
                    TipoPergunta.OBJETIVA,
                    TipoPergunta.ESCALA,
                ):
                    valor = respostas_participante[0].opcao_resposta.texto if respostas_participante[0].opcao_resposta else ''
                elif pergunta.numerico:
                    valor = respostas_participante[0].resposta_numero
                else:
                    valor = respostas_participante[0].resposta_texto
                respostas.append({'pergunta': pergunta, 'valor': valor})
            avaliacao_respostas_individuais.append(
                {
                    'respondente': respondente_index.get(participante.id, participante.id),
                    'respostas': respostas,
                }
            )

    atividades = evento.atividadeevento_set.order_by('data', 'hora')
    return locals()


@rtr()
@permission_required('eventos.change_evento')
def participantes(request, evento_id):
    evento = Evento.objects.filter(pk=evento_id).select_related('coordenador', 'campus', 'configuracao', 'subtipo').first()
    if not evento:
        raise Http404('Evento não encontrado.')
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão acessar esta página.')

    title = f'Participantes: {evento.nome}'
    pode_gerenciar = evento.pode_gerenciar(request.user)
    eh_editavel = evento.ativo and evento.deferido

    # Otimização: calcular uma vez ao invés de dentro do loop de participantes no template
    atingiu_configuracoes_minimas_submissao = evento.atingiu_configuracoes_minimas_para_submissao_trabalhos()

    # Capturar filtros uma única vez
    publico_alvo_id = request.GET.get('q_publico_alvo', 0)
    inscricao_confirmada = request.GET.get('q_inscricao_confirmada')
    presenca_confirmada = request.GET.get('q_presenca_confirmada')

    # Otimização: Buscar público-alvo com distinct direto
    publico_alvo = (
        PublicoAlvoEvento.objects.filter(participante__evento=evento, participante__publico_alvo__isnull=False)
        .values('id', 'descricao')
        .distinct()
        .order_by('descricao')
    )

    # Otimização: Base queryset otimizado com todos os relacionamentos necessários
    respostas_avaliacao_subquery = RespostaParticipante.objects.filter(
        participante=OuterRef('pk'),
        pergunta__tipo_questionario=TipoQuestionario.AVALIACAO,
    )
    base_participantes_qs = (
        Participante.objects.filter(evento=evento)
        .select_related(
            'publico_alvo',
            'tipo',
            'tipo__tipo_participacao',
            'vinculo',
            'vinculo__user',
            'vinculo__pessoa',
        )
        .prefetch_related(
            Prefetch(
                'avaliadormodalidade_set',
                queryset=AvaliadorModalidade.objects.select_related('modalidade', 'modalidade__tipo').prefetch_related('areas_tematicas'),
            ),
            # Otimização: pré-carregar atividades para cálculo de CH
            'atividades',
        )
        .annotate(
            # Otimização: contar trabalhos avaliados uma vez
            num_trabalhos_avaliados=Count(
                'avaliadormodalidade__avaliacaosubmissao',
                filter=Q(avaliadormodalidade__avaliacaosubmissao__nota__isnull=False),
                distinct=True,
            ),
            # Otimização: calcular carga horária inscrita diretamente
            ch_atividades_soma=Sum('atividades__ch'),
            avaliacao_realizada=Exists(respostas_avaliacao_subquery),
        )
        .order_by('nome')
    )

    # Otimização: Aplicar filtros globais uma vez
    if publico_alvo_id and publico_alvo_id != 'None':
        base_participantes_qs = base_participantes_qs.filter(publico_alvo__id=publico_alvo_id)

    if inscricao_confirmada:
        base_participantes_qs = base_participantes_qs.filter(inscricao_validada=inscricao_confirmada)

    if presenca_confirmada:
        base_participantes_qs = base_participantes_qs.filter(presenca_confirmada=presenca_confirmada)

    # Otimização: Buscar tipos de participante com count em uma query
    tipos_participantes_list = list(evento.tipos_participante.all().order_by('tipo_participacao__descricao'))

    # Otimização: Preparar dicionário de queries por tipo
    queries = {}
    for tipo_participante in tipos_participantes_list:
        query = request.GET.get(f'q{tipo_participante.id}')
        queries[tipo_participante.id] = query

    # Otimização: Processar participantes por tipo usando o queryset base
    tipos_participantes = []
    for tipo_participante in tipos_participantes_list:
        # Clone o queryset base e aplica filtro de tipo
        participantes = base_participantes_qs.filter(tipo=tipo_participante)

        # Aplicar busca específica se houver
        query = queries.get(tipo_participante.id)
        if query:
            participantes = participantes.filter(Q(nome__unaccent__icontains=query) | Q(cpf__startswith=query))

        # Mantém como queryset para compatibilidade com template (.count, .exists)
        tipos_participantes.append((tipo_participante, participantes))

    tem_espacialidades = evento.espacialidades.count() > 1

    # Otimização: Calcular uma vez ao invés de múltiplas vezes no template (evita 134+ queries)
    evento_gera_certificado = evento.gera_certificado
    evento_pode_enviar_certificado = evento.pode_enviar_certificado() if evento_gera_certificado else False
    evento_certificado_bloqueado_por_falta_de_avaliacao_configurada = evento.certificado_bloqueado_por_falta_de_avaliacao_configurada()
    evento_utilizar_qr_code = evento.utilizar_qr_code
    evento_ativo = evento.ativo
    evento_deferido = evento.deferido
    evento_pk = evento.pk
    evento_subtipo_multiplas_atividades = evento.subtipo.multiplas_atividades if evento.subtipo else False
    avaliacao_disponivel = evento.get_perguntas_avaliacao().exists()

    # Otimização: Calcular quantitativo uma vez ao invés de no template (evita query complexa no loop)
    if tem_espacialidades:
        quantitativo_participantes = evento.get_quantitativo_de_participantes_por_forma_de_participacao()
    else:
        quantitativo_participantes = None

    return locals()


@rtr()
@login_required()
def notificar_acesso_participante(request, evento_id, tipo_participante_id, pks):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para notificar avaliadores neste evento.')

    pks = pks.split('_')
    participantes = evento.participantes.filter(tipo=tipo_participante_id, pk__in=pks)
    qtd_emails_enviado = 0
    for participante in participantes:
        if participante.convite_aceito():
            Notificar.notificar_acesso(evento, participante)
            qtd_emails_enviado += 1

    url = request.META.get('HTTP_REFERER', f'/eventos/evento/{evento_id}/')
    if qtd_emails_enviado == 0:
        return httprr(url, 'Nenhum e-mail enviado.', tag='error')

    return httprr(url, f'{qtd_emails_enviado} E-mail(s) enviado(s) com sucesso.')


@rtr()
def responder_convite_por_link(request, evento_id, participante_id, convite_aceito, hash_assinado):
    try:
        if not participante_id == signing.loads(hash_assinado).get('participante_id'):
            raise PermissionDenied('Código de validação do convite não confere.')
    except Exception:
        raise PermissionDenied('Erro ao localizar código de validação do convite.')

    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    evento = get_object_or_404(Evento, pk=evento_id)
    category = 'Evento'
    title = evento.nome
    participante = get_object_or_404(Participante, pk=participante_id)
    status = 'error'
    if participante.evento.id != evento.id:
        mensagem = 'Participante não está vinculado ao evento.'
    elif participante.situacao_convite in [
        SituacaoConvite.ACEITO,
        SituacaoConvite.RECUSADO,
    ]:
        mensagem = 'Esse convite já foi respondido anteriormente.'
    elif convite_aceito:
        participante.situacao_convite = SituacaoConvite.ACEITO
        participante.presenca_confirmada = True
        status = 'success'
        mensagem = ExibirMensagem.convite_aceito(participante)
        participante.save()
        Notificar.notificar_acesso(evento, participante)
    else:
        participante.situacao_convite = SituacaoConvite.RECUSADO
        status = 'success'
        mensagem = ExibirMensagem.convite_recusado(participante)
        participante.save()

    return locals()


@rtr()
@login_required()
def convidar_participante(request, evento_id, tipo_participante_id, pks):
    evento = get_object_or_404(Evento, pk=evento_id)
    tipo_participante = get_object_or_404(TipoParticipante, pk=tipo_participante_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para convidar participantes neste evento.')
    pks = pks.split('_')
    participantes = evento.participantes.filter(tipo=tipo_participante_id, pk__in=pks)
    qtd_emails_enviado = 0
    for participante in participantes:
        Notificar.convidar_participante(evento, participante, tipo_participante)
        participante.situacao_convite = SituacaoConvite.ENVIADO
        participante.save()

        qtd_emails_enviado += 1

    url = request.META.get('HTTP_REFERER', f'/eventos/evento/{evento_id}/')
    if qtd_emails_enviado == 0:
        return httprr(url, 'Nenhum e-mail enviado.', tag='error')

    return httprr(url, f'{qtd_emails_enviado} E-mail(s) enviado(s) com sucesso.')


@rtr()
@login_required()
def vincular_area_tematica_ao_evento(request, evento_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para vincular área temática neste evento.')
    title = 'Vincular área temática ao evento'
    form = VincularAreaTematicaEventoForm(request.POST or None, instance=evento)
    if form.is_valid():
        form.save()
        return httprr('..', 'Áreas temáticas vinculadas com sucesso.')
    return locals()


@rtr()
@login_required()
def vincular_area_tematica_a_modalidade(request, modalidade_id):
    modalidade = get_object_or_404(Modalidade, pk=modalidade_id)
    if not modalidade.evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para vincular área temática neste evento.')
    title = f'Vincular área temática à modalidade: {modalidade.tipo.titulo}'
    areas_tematicas = modalidade.evento.areas_tematicas.all()
    itens_vinculados = AreaTematicaModalidade.objects.filter(modalidade_id=modalidade_id).values('area_tematica_id', 'limite_aprovados')
    itens_vinculados = {item['area_tematica_id']: item['limite_aprovados'] for item in itens_vinculados}
    if request.POST:
        for area_tematica_id in request.POST.getlist('ids'):
            itens_vinculados.pop(int(area_tematica_id), None)
            limite_aprovados = int(request.POST.get(f'limite_aprovados_{area_tematica_id}', 0) or 0)
            AreaTematicaModalidade.objects.update_or_create(
                area_tematica_id=area_tematica_id,
                modalidade_id=modalidade_id,
                defaults={'limite_aprovados': limite_aprovados},
            )

        if itens_vinculados:
            # se ainda existe itens_vinculados no dicionario, significa que o usuario desmarcou um item e ele será excluído
            area_tematica_ids = itens_vinculados.keys()
            AreaTematicaModalidade.objects.filter(modalidade_id=modalidade_id, area_tematica_id__in=area_tematica_ids).delete()

        return httprr('..', 'Área temática vinculada com sucesso.')
    return locals()


@rtr()
@login_required()
def configurar_evento(request, evento_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para vincular área temática a este evento.')
    title = 'Adicionar Configuração ao Evento'
    form = ConfiguracaoEventosForm(request.POST or None, instance=evento.configuracao)
    if form.is_valid():
        form.save(evento)
        return httprr('..', 'Configuração salva com sucesso.')
    return locals()


@rtr()
@login_required()
def vincular_modalidade_avaliador(request, evento_id, avaliador_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    avaliador = get_object_or_404(Participante, pk=avaliador_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para vincular área temática a este evento.')
    title = 'Vincular modalidade ao avaliador'
    form = AvaliadorModalidadeForm(request.POST or None, evento=evento, avaliador=avaliador)
    if form.is_valid():
        form.save()
        return httprr('..', 'Modalidade vinculada ao avaliador com sucesso.')
    return locals()


@rtr()
@login_required()
@csrf_exempt
def vincular_avaliador_a_submissao(request: HttpRequest, submissao_id: int) -> dict | HttpResponse:
    submissao = get_object_or_404(Submissao, pk=submissao_id)
    if not submissao.modalidade.evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para vincular um avaliador a uma submissão neste evento.')
    if submissao.situacao == SituacaoSubmissao.REMOVIDO_DUPLICIDADE:
        raise PermissionDenied('Não é possível vincular avaliadores a um trabalho removido por duplicidade.')
    title = 'Vincular avaliador à submissão'
    form = VincularAvaliadorSubmissaoForm(request.POST or None, submissao=submissao)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return httprr('..', 'Avaliador(es) vinculado(s) à submissão com sucesso.')
    return locals()


@rtr()
@login_required()
@csrf_exempt
def substituir_avaliador_submissao(request, avaliacao_submissao_id):
    avaliacao_submissao = get_object_or_404(AvaliacaoSubmissao, pk=avaliacao_submissao_id)
    if not avaliacao_submissao.versao.submissao.modalidade.evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para alterar um avaliador de uma submissão neste evento.')
    if avaliacao_submissao.estah_avaliado:
        raise PermissionDenied('Não é possível remover um avaliador que já avaliou um trabalho.')
    title = f'Substituir avaliador: {avaliacao_submissao.avaliador_modalidade.avaliador.nome}'
    form = SubstituirAvaliadorSubmissaoForm(request.POST or None, avaliacao_submissao=avaliacao_submissao)
    if form.is_valid():
        evento = avaliacao_submissao.versao.submissao.modalidade.evento
        form.save()
        url = f'/eventos/evento/{evento.id}/?tab=avaliacao_trabalhos'
        if request.GET.get('_popup'):
            url = '..'
        return httprr(url, 'Avaliador alterado com sucesso.')
    return locals()


@rtr()
@login_required()
def remover_avaliador_submissao(request, avaliacao_submissao_id):
    if request.method == 'POST':
        avaliacao_submissao = get_object_or_404(AvaliacaoSubmissao, pk=avaliacao_submissao_id)
        if not avaliacao_submissao.versao.submissao.modalidade.evento.pode_gerenciar(request.user):
            raise PermissionDenied('Você não tem permissão para remover um avaliador de uma submissão neste evento.')
        if avaliacao_submissao.estah_avaliado:
            raise PermissionDenied('Não é possível remover um avaliador que já avaliou um trabalho.')
        evento = avaliacao_submissao.versao.submissao.modalidade.evento
        avaliacao_submissao.delete()
        url = f'/eventos/evento/{evento.id}/?tab=avaliacao_trabalhos'
        return httprr(url, 'Avaliador removido com sucesso.')
    else:
        raise PermissionDenied('Operação inválida.')


@rtr()
@login_required()
def exibir_detalhes_avaliacao(request, submissao_id):
    submissao = get_object_or_404(Submissao, pk=submissao_id)
    if not submissao.modalidade.evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para visualizar detalhes de uma avaliação neste evento.')
    title = 'Detalhes da avaliação'
    return locals()


@rtr()
@login_required()
def listar_detalhes_avaliacao(request, evento_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para listar detalhes das avaliações neste evento.')
    title = 'Listar detalhes da avaliação'
    submissoes = Submissao.objects.filter(modalidade__evento_id=evento_id).order_by('modalidade__tipo__titulo', 'area_tematica__titulo', 'titulo')
    return locals()


@rtr()
@login_required()
def notificar_resultado_avaliacoes(request, evento_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para notificar resultado de avaliação neste evento.')

    if request.POST:
        area_tematica_modalidade_ids = request.POST.getlist('ids')
        notificar_todos = 'notificar_todos' in request.POST
        notificou = Submissao.notificar_resultado_avaliacao(evento, area_tematica_modalidade_ids, notificar_todos)
        if notificou > 0:
            evento.configuracao.registrar_notificacao(request.user)
        messages.success(request, f'{notificou} trabalhos foram notificados por email com sucesso.')

    return httprr(f'/eventos/evento/{evento.id}/?tab=avaliacao_trabalhos')


@rtr()
@login_required()
def listar_resultado_avaliacoes(request, area_tematica_modalidade_id):
    area_tematica_modalidade = get_object_or_404(AreaTematicaModalidade, pk=area_tematica_modalidade_id)
    if not area_tematica_modalidade.modalidade.evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para visualizar o resultado das avaliações neste evento.')
    submissoes = Submissao.listar_resultado(area_tematica_modalidade)

    title = f'Resultados: {area_tematica_modalidade.modalidade.tipo} - {area_tematica_modalidade.area_tematica}'
    return locals()


@csrf_exempt
def get_areas_tematicas_da_modalidade(request, modalidade_id):
    modalidade = get_object_or_404(Modalidade, pk=modalidade_id)
    choice = []
    for area_tematica in modalidade.areas_tematicas:
        choice.append([area_tematica.id, area_tematica.titulo])
    return JsonResponse({'areas_tematicas': choice})


@rtr()
@login_required()
def remover_modalidade_avaliador(request, avaliador_id):
    avaliador_modalidade = get_object_or_404(AvaliadorModalidade, pk=avaliador_id)
    if not avaliador_modalidade.modalidade.evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para remover um a modalidade de um avaliador.')
    tipo_participante_id = avaliador_modalidade.avaliador.tipo.id
    evento = avaliador_modalidade.modalidade.evento
    avaliador_modalidade.delete()
    return httprr(
        f'/eventos/evento/{evento.id}/?tab=avaliador-de-trabalho{tipo_participante_id}#participantes',
        'Modalidade do avaliador removida com sucesso.',
    )


@login_required()
@rtr()
def adicionar_pergunta(request, evento_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para realizar essa operação neste evento.')
    title = 'Adicionar Pergunta ao Formulário de Inscrição do Evento'
    form = PerguntaForm(
        request.POST or None,
        evento=evento,
        tipo_questionario=TipoQuestionario.INSCRICAO,
    )
    if form.is_valid():
        form.save()
        return httprr('..', 'Pergunta adicionada com sucesso.')
    return locals()


@login_required()
@rtr()
def adicionar_pergunta_avaliacao(request, evento_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para realizar essa operação neste evento.')
    title = 'Adicionar Pergunta ao Formulário de Avaliação do Evento'
    form = PerguntaForm(
        request.POST or None,
        evento=evento,
        tipo_questionario=TipoQuestionario.AVALIACAO,
    )
    if form.is_valid():
        pergunta = form.save()
        if pergunta.tipo_pergunta == TipoPergunta.ESCALA and not pergunta.opcaoresposta_set.exists():
            for ordem in range(1, 6):
                OpcaoResposta.objects.create(evento=evento, pergunta=pergunta, ordem=ordem, texto=str(ordem))
        return httprr('..', 'Pergunta de avaliação adicionada com sucesso.')
    return locals()


@login_required()
@rtr()
def editar_pergunta(request, pergunta_id):
    pergunta = get_object_or_404(Pergunta, pk=pergunta_id, tipo_questionario=TipoQuestionario.INSCRICAO)
    if not pergunta.evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para realizar essa operação neste evento.')
    title = 'Editar Pergunta'
    form = PerguntaForm(request.POST or None, instance=pergunta)
    if form.is_valid():
        form.save()
        return httprr('..', 'Pergunta alterada com sucesso.')
    return locals()


@login_required()
@rtr()
def editar_pergunta_avaliacao(request, pergunta_id):
    pergunta = get_object_or_404(Pergunta, pk=pergunta_id, tipo_questionario=TipoQuestionario.AVALIACAO)
    if not pergunta.evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para realizar essa operação neste evento.')
    title = 'Editar Pergunta de Avaliação'
    form = PerguntaForm(
        request.POST or None,
        instance=pergunta,
        tipo_questionario=TipoQuestionario.AVALIACAO,
    )
    if form.is_valid():
        pergunta = form.save()
        if pergunta.tipo_pergunta == TipoPergunta.ESCALA and not pergunta.opcaoresposta_set.exists():
            for ordem in range(1, 6):
                OpcaoResposta.objects.create(
                    evento=pergunta.evento,
                    pergunta=pergunta,
                    ordem=ordem,
                    texto=str(ordem),
                )
        return httprr('..', 'Pergunta de avaliação alterada com sucesso.')
    return locals()


@login_required()
@rtr()
def remover_pergunta(request, pergunta_id):
    pergunta = get_object_or_404(Pergunta, pk=pergunta_id, tipo_questionario=TipoQuestionario.INSCRICAO)
    if not pergunta.evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para realizar essa operação neste evento.')
    evento = pergunta.evento
    pergunta.delete()
    return httprr(f'/eventos/evento/{evento.id}/?tab=inscricoes', 'Pergunta removida com sucesso.')


@login_required()
@rtr()
def remover_pergunta_avaliacao(request, pergunta_id):
    pergunta = get_object_or_404(Pergunta, pk=pergunta_id, tipo_questionario=TipoQuestionario.AVALIACAO)
    if not pergunta.evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para realizar essa operação neste evento.')
    evento = pergunta.evento
    pergunta.delete()
    return httprr(
        f'/eventos/evento/{evento.id}/?tab=avaliacao',
        'Pergunta de avaliação removida com sucesso.',
    )


@login_required()
@rtr()
def adicionar_opcao_resposta(request, evento_id, pergunta_id=None):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para realizar essa operação neste evento.')
    pergunta = None
    if pergunta_id:
        pergunta = get_object_or_404(Pergunta, pk=pergunta_id, tipo_questionario=TipoQuestionario.INSCRICAO)

    title = 'Adicionar Opção de Resposta'
    form = OpcaoRespostaForm(request.POST or None, request.FILES or None, evento=evento, pergunta=pergunta)
    if form.is_valid():
        form.save()
        return httprr('..', 'Opção de resposta adicionada com sucesso.')
    return locals()


@login_required()
@rtr()
def adicionar_opcao_resposta_avaliacao(request, evento_id, pergunta_id=None):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para realizar essa operação neste evento.')
    pergunta = None
    if pergunta_id:
        pergunta = get_object_or_404(Pergunta, pk=pergunta_id, tipo_questionario=TipoQuestionario.AVALIACAO)
    title = 'Adicionar Opção de Resposta da Avaliação'
    form = OpcaoRespostaForm(request.POST or None, request.FILES or None, evento=evento, pergunta=pergunta)
    if form.is_valid():
        form.save()
        return httprr('..', 'Opção de resposta adicionada com sucesso.')
    return locals()


@login_required()
@rtr()
def editar_opcao_resposta(request, opcao_resposta_id):
    opcao_resposta = get_object_or_404(
        OpcaoResposta.objects.filter(Q(pergunta__tipo_questionario=TipoQuestionario.INSCRICAO) | Q(pergunta__isnull=True)),
        pk=opcao_resposta_id,
    )
    if not opcao_resposta.evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para realizar essa operação neste evento.')
    title = 'Editar Opção de Resposta'
    form = OpcaoRespostaForm(request.POST or None, request.FILES or None, instance=opcao_resposta)
    if form.is_valid():
        form.save()
        return httprr('..', 'Opção de resposta alterada com sucesso.')
    return locals()


@login_required()
@rtr()
def editar_opcao_resposta_avaliacao(request, opcao_resposta_id):
    opcao_resposta = get_object_or_404(
        OpcaoResposta.objects.filter(Q(pergunta__tipo_questionario=TipoQuestionario.AVALIACAO) | Q(pergunta__isnull=True)),
        pk=opcao_resposta_id,
    )
    if not opcao_resposta.evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para realizar essa operação neste evento.')
    title = 'Editar Opção de Resposta da Avaliação'
    form = OpcaoRespostaForm(request.POST or None, request.FILES or None, instance=opcao_resposta)
    if form.is_valid():
        form.save()
        return httprr('..', 'Opção de resposta alterada com sucesso.')
    return locals()


@login_required()
@rtr()
def remover_opcao_resposta(request, opcao_resposta_id):
    opcao_resposta = get_object_or_404(
        OpcaoResposta.objects.filter(Q(pergunta__tipo_questionario=TipoQuestionario.INSCRICAO) | Q(pergunta__isnull=True)),
        pk=opcao_resposta_id,
    )
    evento = opcao_resposta.pergunta and opcao_resposta.pergunta.evento or opcao_resposta.evento
    if not evento or not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para realizar essa operação neste evento.')
    opcao_resposta.delete()
    return httprr(
        f'/eventos/evento/{evento.id}/?tab=inscricoes',
        'Opção de resposta removida com sucesso.',
    )


@login_required()
@rtr()
def remover_opcao_resposta_avaliacao(request, opcao_resposta_id):
    opcao_resposta = get_object_or_404(
        OpcaoResposta.objects.filter(Q(pergunta__tipo_questionario=TipoQuestionario.AVALIACAO) | Q(pergunta__isnull=True)),
        pk=opcao_resposta_id,
    )
    evento = opcao_resposta.pergunta and opcao_resposta.pergunta.evento or opcao_resposta.evento
    if not evento or not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para realizar essa operação neste evento.')
    opcao_resposta.delete()
    return httprr(
        f'/eventos/evento/{evento.id}/?tab=avaliacao',
        'Opção de resposta removida com sucesso.',
    )


@rtr()
@login_required()
def adicionar_modalidade(request, evento_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para vincular modalidade a este evento.')
    title = 'Adicionar Modalidade ao Evento'
    form = ModalidadeForm(request.POST or None, request.FILES or None, evento=evento)
    CriterioAvaliacaoFormSet = inlineformset_factory(
        Modalidade,
        CriterioAvaliacao,
        extra=1,
        formset=CriterioAvaliacaoInlineFormSet,
        fields=['etapa', 'descricao', 'nota_minima', 'nota_maxima', 'ordem_desempate'],
        widgets={'nota_minima': IntegerWidget(), 'nota_maxima': IntegerWidget()},
        can_delete=True,
    )
    formset = CriterioAvaliacaoFormSet(request.POST or None, request.FILES or None)
    if form.is_valid() and formset.is_valid():
        form.save(evento)
        formset.instance = form.instance
        formset.save()
        return httprr('..', 'Modalidade adicionada com sucesso.')
    return locals()


@rtr()
@login_required()
def editar_modalidade(request, modalidade_id):
    modalidade = get_object_or_404(Modalidade, pk=modalidade_id)
    if not modalidade.evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para editar uma modalidade neste evento.')
    title = 'Editar Modalidade do Evento'
    form = ModalidadeForm(request.POST or None, request.FILES or None, instance=modalidade)
    if form.is_valid():
        form.save(modalidade.evento)
        return httprr('..', 'Modalidade alterada com sucesso.')
    return locals()


@rtr()
@login_required()
def adicionar_criterio_avaliacao(request, modalidade_id):
    modalidade = get_object_or_404(Modalidade, pk=modalidade_id)
    if not modalidade.evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para adicionar um critério de avaliação a este evento.')
    title = 'Adicionar critério de avaliação'
    form = CriterioAvaliacaoForm(request.POST or None, request.FILES or None, modalidade=modalidade)
    if form.is_valid():
        form.save()
        return httprr('..', 'Critério de avaliação adicionado com sucesso.')
    return locals()


@rtr()
@login_required()
def editar_criterio_avaliacao(request, criterio_avaliacao_id):
    criterio_avaliacao = get_object_or_404(CriterioAvaliacao, pk=criterio_avaliacao_id)
    if not criterio_avaliacao.modalidade.evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para alterar um critério de avaliação neste evento.')
    title = 'Editar critério de avaliação'
    form = CriterioAvaliacaoForm(request.POST or None, request.FILES or None, instance=criterio_avaliacao)
    if form.is_valid():
        form.save()
        return httprr('..', 'Critério de avaliação alterado com sucesso.')
    return locals()


@rtr()
@login_required()
def listar_criterio_avaliacao(request, modalidade_id):
    modalidade = get_object_or_404(Modalidade, pk=modalidade_id)
    pode_gerenciar = modalidade.evento.pode_gerenciar(request.user)
    if not pode_gerenciar:
        raise PermissionDenied('Você não tem permissão para listar critérios de avaliação a este evento.')
    title = 'Critérios de avaliação'
    return locals()


@rtr()
@login_required()
def remover_criterio_avaliacao(request, criterio_avaliacao_id):
    criterio_avaliacao = get_object_or_404(CriterioAvaliacao, pk=criterio_avaliacao_id)
    if not criterio_avaliacao.modalidade.evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para remover um critério de avaliação neste evento.')
    if criterio_avaliacao.possui_itens_avaliados():
        raise PermissionDenied('Não é possível remover um critério de avaliação que possui itens avaliados.')
    evento = criterio_avaliacao.modalidade.evento
    criterio_avaliacao.delete()
    return httprr(
        f'/eventos/evento/{evento.id}/?tab=submissao_trabalhos',
        'Critério de avaliação removido com sucesso.',
    )


@rtr()
@login_required()
def remover_modalidade(request, modalidade_id):
    modalidade = get_object_or_404(Modalidade, pk=modalidade_id)
    if not modalidade.evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para remover uma modalidade neste evento.')
    evento = modalidade.evento
    modalidade.delete()
    return httprr(
        f'/eventos/evento/{evento.id}/?tab=submissao_trabalhos',
        'Modalidade removida com sucesso.',
    )


@rtr()
@login_required()
def deferir(request, evento_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_avaliar(request.user) and not request.user.is_superuser:
        raise PermissionDenied('Você não pode avaliar este evento.')
    url = reverse('evento', args=(evento_id,))
    if evento.inscricao_publica and not evento.tipos_participante.filter(permite_inscricao_direta=True).exists():
        return httprr(
            f'{url}#tipos-de-participantes',
            'É necessário ter, pelo menos, um Tipo de participante com inscrição direta para deferir um evento com inscrição online.',
            tag='error',
        )

    evento.deferir(request.user)
    titulo = '[SUAP] Avaliação de Evento'
    texto = '<h1>Avaliação de Evento</h1>'
    texto += f'<h2>{evento.nome}</h2>'
    texto += f'<p>O evento <strong>{evento.nome}</strong> foi deferido.</p>'
    texto += '<p class="more-info">Para mais informações, acesse: <a href="{0}">{0}</a></p>'.format(evento.get_absolute_url())
    if evento.coordenador:
        send_notification(
            titulo,
            texto,
            settings.DEFAULT_FROM_EMAIL,
            [evento.coordenador.get_vinculo()],
        )
    return httprr(url, 'O evento foi deferido.')


@rtr()
@login_required()
def indeferir(request, evento_id):
    title = 'Indeferir Evento'
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_avaliar(request.user) and not request.user.is_superuser:
        raise PermissionDenied('Você não pode avaliar este evento.')
    form = IndeferirEventoForm(request.POST or None, instance=evento, request=request)
    if form.is_valid():
        evento = form.save()
        titulo = '[SUAP] Avaliação de Evento'
        texto = '<h1>Avaliação de Evento</h1>'
        texto += f'<h2>{evento.nome}</h2>'
        texto += f'<p>O evento <strong>{evento.nome}</strong> foi indeferido.</p>'
        texto += '<p class="more-info">Para mais informações, acesse: <a href="{0}">{0}</a></p>'.format(evento.get_absolute_url())
        if evento.coordenador:
            send_notification(
                titulo,
                texto,
                settings.DEFAULT_FROM_EMAIL,
                [evento.coordenador.get_vinculo()],
            )
        return httprr('..', 'O evento foi indeferido.')
    return locals()


@rtr()
@login_required()
def ativar_evento(request, evento_id):
    title = 'Ativar Evento'
    evento = get_object_or_404(Evento, pk=evento_id)
    if not request.user.is_superuser and not evento.pode_avaliar(request.user):
        raise PermissionDenied('Você não pode ativar este evento.')
    form = JustificativaForm(data=request.POST or None)
    if form.is_valid():
        justificativa = form.cleaned_data['justificativa']
        evento.ativar(justificativa, request.user)
        if evento.coordenador:
            titulo = '[SUAP] Ativação de Evento'
            texto = '<h1>Ativação de Evento</h1>'
            texto += f'<h2>{evento.nome}</h2>'
            texto += f'<p>O evento <strong>{evento.nome}</strong> foi <strong>ativado</strong> por {request.user}.</p>'
            texto += f'<p>Justificativa: <br>{justificativa}</p>'
            texto += '<p class="more-info">Para mais informações, acesse: <a href="{0}">{0}</a></p>'.format(evento.get_absolute_url())
            send_notification(
                titulo,
                texto,
                settings.DEFAULT_FROM_EMAIL,
                [evento.coordenador.get_vinculo()],
            )
        return httprr('..', 'O evento foi ativado.')
    return locals()


@rtr()
@login_required()
def desativar_evento(request, evento_id):
    title = 'Inativar Evento'
    evento = get_object_or_404(Evento, pk=evento_id)
    if not request.user.is_superuser and not evento.pode_avaliar(request.user):
        raise PermissionDenied('Você não pode inativar este evento.')
    form = JustificativaForm(data=request.POST or None)
    if form.is_valid():
        justificativa = form.cleaned_data['justificativa']
        evento.suspender(justificativa, request.user)
        if evento.coordenador:
            titulo = '[SUAP] Inativação de Evento'
            texto = '<h1>Inativação de Evento</h1>'
            texto += f'<h2>{evento.nome}</h2>'
            texto += f'<p>O evento <strong>{evento.nome}</strong> foi <strong>inativado</strong> por {request.user}.</p>'
            texto += f'<p>Justificativa: <br>{justificativa}</p>'
            texto += '<p class="more-info">Para mais informações, acesse: <a href="{0}">{0}</a></p>'.format(evento.get_absolute_url())
            send_notification(
                titulo,
                texto,
                settings.DEFAULT_FROM_EMAIL,
                [evento.coordenador.get_vinculo()],
            )
        return httprr('..', 'O evento foi inativado.')
    return locals()


@rtr()
@login_required()
def submeter(request, evento_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.coordenador or request.user.get_vinculo() != evento.coordenador.get_vinculo():
        raise PermissionDenied('Apenas o coordenador do evento pode submetê-lo.')
    if evento.inscricao_publica and not evento.tipos_participante.filter(permite_inscricao_direta=True).exists():
        url = reverse('evento', args=(evento_id,))
        return httprr(
            f'{url}#tipos-de-participantes',
            'É necessário ter, pelo menos, um Tipo de participante com inscrição direta para submeter um evento com inscrição online.',
            tag='error',
        )
    evento.submeter(request.user)
    return httprr(request.META.get('HTTP_REFERER', '..'), 'O evento foi submetido.')


@rtr()
@login_required()
def cancelar_avaliacao(request, evento_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_avaliar(request.user) and evento.submetido and evento.deferido is not None:
        raise PermissionDenied('Você não pode cancelar a avaliação desse evento.')
    evento.cancelar_avaliacao(request.user)
    return httprr(request.META.get('HTTP_REFERER', '..'), 'A avaliação do evento foi cancelada.')


@rtr()
@login_required()
def cancelar(request, evento_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not request.user.has_group_cached('Coordenador de Comunicação Sistêmico'):
        raise PermissionDenied('Você não tem permissão para cancelar este evento.')
    evento.cancelar(request.user)
    return httprr(request.META.get('HTTP_REFERER', '..'), 'O evento foi cancelado com sucesso.')


@rtr()
@login_required()
def desfazer_cancelamento(request, evento_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not request.user.has_group_cached('Coordenador de Comunicação Sistêmico'):
        raise PermissionDenied('Você não tem permissão para desfazer o cancelamento deste evento.')
    evento.desfazer_cancelamento(request.user)
    return httprr(
        request.META.get('HTTP_REFERER', '..'),
        'O evento teve o cancelamento desfeito com sucesso.',
    )


@rtr()
@login_required()
def desfazer_finalizacao(request, evento_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para desfazer a finalização deste evento.')
    evento.desfazer_finalizacao(request.user)
    return httprr(
        request.META.get('HTTP_REFERER', '..'),
        'O evento teve a finalização desfeita com sucesso.',
    )


@rtr()
@login_required()
def devolver(request, evento_id):
    title = 'Devolver Evento'
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_avaliar(request.user):
        raise PermissionDenied('Você não pode devolver este evento.')
    form = JustificativaForm(data=request.POST or None)
    if form.is_valid():
        justificativa = form.cleaned_data['justificativa']
        evento.devolver(justificativa, request.user)
        titulo = '[SUAP] Devolução de Evento'
        texto = '<h1>devolução de Evento</h1>'
        texto += f'<h2>{evento.nome}</h2>'
        texto += f'<p>O evento <strong>{evento.nome}</strong> foi <strong>devolvido</strong> por {request.user}.</p>'
        texto += f'<p>Justificativa: <br>{justificativa}</p>'
        texto += '<p class="more-info">Para mais informações, acesse: <a href="{0}">{0}</a></p>'.format(evento.get_absolute_url())
        if evento.coordenador:
            send_notification(
                titulo,
                texto,
                settings.DEFAULT_FROM_EMAIL,
                [evento.coordenador.get_vinculo()],
            )
        return httprr('..', 'O evento foi desativado.')
    return locals()


@rtr()
@login_required()
def finalizar(request, evento_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user) or not evento.pode_finalizar(request.user):
        raise PermissionDenied('Você não pode finalizar este evento.')
    evento.finalizar(request.user)
    return httprr(request.META.get('HTTP_REFERER', '..'), 'O evento foi finalizado com sucesso.')


@permission_required('eventos.change_evento')
@rtr()
def relatorio(request):
    title = 'Relatório de Eventos'
    form = RelatorioEventosForm(request.POST or None)
    if form.is_valid():
        eventos = Evento.objects.filter(deferido=True)
        dimensao = form.cleaned_data['dimensao']
        ano = form.cleaned_data['ano']
        campus = form.cleaned_data['campus']
        setor = form.cleaned_data['setor']
        capacitacao = form.cleaned_data['capacitacao']
        possui_cunho_social = form.cleaned_data['possui_cunho_social']
        if dimensao:
            eventos = eventos.filter(dimensoes=dimensao)
        if ano != 'Todos':
            eventos = eventos.filter(
                Q(data_inicio__year__lte=int(ano), data_fim__year__gte=int(ano)) | Q(data_fim__isnull=True, data_inicio__year=int(ano))
            )
        if setor != 'Todos':
            eventos = eventos.filter(setor=int(setor))
        if capacitacao:
            eventos = eventos.filter(capacitacao=True)
        if possui_cunho_social:
            eventos = eventos.filter(possui_cunho_social=True)

        if campus:
            eventos = eventos.filter(campus=campus)
        else:
            dados = eventos.values('campus__nome').annotate(qtd=models.Count('campus__nome')).order_by('campus__nome')
            dados_grafico = []
            for dado in dados:
                dado_grafico = []
                dado_grafico.append(dado['campus__nome'])
                dado_grafico.append(dado['qtd'])
                dados_grafico.append(dado_grafico)

            grafico_campus = PieChart(
                'grafico_campus',
                title='Por Campus',
                subtitle='Quantidade de Eventos por Campus',
                minPointLength=0,
                data=dados_grafico,
            )
        if eventos.exists():
            dados = (
                eventos.filter(natureza__isnull=False)
                .values('natureza__descricao')
                .annotate(qtd=models.Count('natureza__descricao'))
                .order_by('natureza__descricao')
            )
            dados_grafico = []
            for dado in dados:
                dado_grafico = []
                dado_grafico.append(dado['natureza__descricao'])
                dado_grafico.append(dado['qtd'])
                dados_grafico.append(dado_grafico)

            grafico_natureza = PieChart(
                'grafico_natureza',
                title='Por Natureza',
                subtitle='Quantidade de Eventos por Natureza',
                minPointLength=0,
                data=dados_grafico,
            )

            dados = (
                eventos.filter(tipo__isnull=False).values('tipo__descricao').annotate(qtd=models.Count('tipo__descricao')).order_by('tipo__descricao')
            )
            dados_grafico = []
            for dado in dados:
                dado_grafico = []
                dado_grafico.append(dado['tipo__descricao'])
                dado_grafico.append(dado['qtd'])
                dados_grafico.append(dado_grafico)

            grafico_tipo = PieChart(
                'grafico_tipo',
                title='Por Tipo',
                subtitle='Quantidade de Eventos por Tipo',
                minPointLength=0,
                data=dados_grafico,
            )

            dados = (
                eventos.filter(classificacao__isnull=False)
                .values('classificacao__descricao')
                .annotate(qtd=models.Count('classificacao__descricao'))
                .order_by('classificacao__descricao')
            )
            dados_grafico = []
            for dado in dados:
                dado_grafico = []
                dado_grafico.append(dado['classificacao__descricao'])
                dado_grafico.append(dado['qtd'])
                dados_grafico.append(dado_grafico)

            grafico_classificacao = PieChart(
                'grafico_classificacao',
                title='Por Classificação',
                subtitle='Quantidade de Eventos por Classificação',
                minPointLength=0,
                data=dados_grafico,
            )

            dados = (
                eventos.filter(publico_alvo__isnull=False)
                .values('publico_alvo__descricao')
                .annotate(qtd=models.Count('publico_alvo__descricao'))
                .order_by('publico_alvo__descricao')
            )
            dados_grafico = []
            for dado in dados:
                dado_grafico = []
                dado_grafico.append(dado['publico_alvo__descricao'])
                dado_grafico.append(dado['qtd'])
                dados_grafico.append(dado_grafico)

            grafico_publico_alvo = PieChart(
                'grafico_publico_alvo',
                title='Por Público Alvo',
                subtitle='Quantidade de Eventos por Público Alvo',
                minPointLength=0,
                data=dados_grafico,
            )

            items_count = defaultdict(int)
            for evento in eventos.filter(dimensoes__isnull=False).distinct():
                dimensoes = sorted(evento.dimensoes.values_list('descricao', flat=True))
                dimensao_key = ', '.join(dimensoes)
                items_count[dimensao_key] += 1

            dados_grafico = [[key, value] for key, value in items_count.items()]
            grafico_dimensao = ColumnChart(
                'grafico_dimensao',
                title='Por Dimensão',
                subtitle='Quantidade de Eventos por Dimensão',
                minPointLength=0,
                data=dados_grafico,
            )

            # Inicio: Quantidade de eventos com cunho social
            dados = eventos.values('possui_cunho_social').annotate(qtd=models.Count('possui_cunho_social')).order_by('possui_cunho_social')
            dados_grafico = []
            for dado in dados:
                descricao = 'Com Cunho Social' if dado['possui_cunho_social'] else 'Sem Cunho Social'
                dados_grafico.append([descricao, dado['qtd']])

            grafico_cunho_social = PieChart(
                'grafico_cunho_social',
                title='Cunho Social',
                subtitle='Quantidade de eventos com/sem cunho social',
                minPointLength=0,
                data=dados_grafico,
            )

            # Início: Quantidade de eventos por perfil de organizador (alunos, técnico-administrativos e docentes).
            dados = (
                PublicoAlvoEvento.objects.filter(
                    participante__evento__in=eventos,
                    participante__tipo__tipo_participacao__descricao='Organizador',
                )
                .annotate(qtd=Count('participante__evento', distinct=True))
                .values('descricao', 'qtd')
            )
            dados_grafico = []
            for dado in dados:
                dado_grafico = []
                dado_grafico.append(dado['descricao'])
                dado_grafico.append(dado['qtd'])
                dados_grafico.append(dado_grafico)

            grafico_tipo_organizador = PieChart(
                'grafico_tipo_organizador',
                title='Por Perfil de Organizador',
                subtitle='Quantidade de eventos por perfil do organizador',
                minPointLength=0,
                data=dados_grafico,
            )

            # Início: Quantidade de eventos de capacitação por perfil de participante (alunos, técnico-administrativos e docentes).
            dados = (
                PublicoAlvoEvento.objects.filter(
                    participante__evento__in=eventos,
                    participante__evento__capacitacao=True,
                    participante__tipo__tipo_participacao__descricao='Participante',
                )
                .annotate(qtd=Count('participante__evento', distinct=True))
                .values('descricao', 'qtd')
            )
            dados_grafico = []
            for dado in dados:
                dado_grafico = []
                dado_grafico.append(dado['descricao'])
                dado_grafico.append(dado['qtd'])
                dados_grafico.append(dado_grafico)

            grafico_capacitacao_publico_alvo = PieChart(
                'grafico_capacitacao_publico_alvo',
                title='Eventos de Capacitação',
                subtitle='Quantidade de eventos de capacitação por perfil de participante',
                minPointLength=0,
                data=dados_grafico,
            )
            # Início: Carga horária total realizada em eventos de capacitação por perfil de participante (alunos, técnico-administrativos e docentes)
            dados = (
                PublicoAlvoEvento.objects.filter(
                    participante__evento__in=eventos,
                    participante__evento__capacitacao=True,
                    participante__tipo__tipo_participacao__descricao='Participante',
                )
                .values(
                    'descricao',
                    'participante__evento',
                    'participante__evento__carga_horaria',
                )
                .distinct()
            )
            carga_horaria_por_descricao = {}
            for dado in dados:
                descricao = dado['descricao']
                carga_horaria = dado['participante__evento__carga_horaria']
                if descricao in carga_horaria_por_descricao:
                    carga_horaria_por_descricao[descricao] += carga_horaria
                else:
                    carga_horaria_por_descricao[descricao] = carga_horaria

            dados_grafico = []
            for descricao, total_carga_horaria in carga_horaria_por_descricao.items():
                dados_grafico.append([descricao, total_carga_horaria // 3600])  # Convertendo segundos para horas

            grafico_capacitacao_carga_horaria = PieChart(
                'grafico_capacitacao_carga_horaria',
                title='Carga Horária de Eventos de Capacitação',
                subtitle='Carga horária total de eventos de capacitação por perfil de participante',
                minPointLength=0,
                data=dados_grafico,
            )

            # Início: Perfil de palestrantes (internos e externos)
            dados = (
                eventos.filter(
                    participantes__tipo__tipo_participacao__descricao='Palestrante',
                    participantes__publico_alvo__isnull=False,
                )
                .values('participantes__publico_alvo__descricao')
                .annotate(qtd=models.Count('participantes__publico_alvo__descricao'))
                .distinct()
                .order_by('participantes__publico_alvo__descricao')
            )
            interno = 0
            externo = 0
            for dado in dados:
                if dado['participantes__publico_alvo__descricao'] in [
                    'Aluno',
                    'Servidor',
                    'Prestador de Serviços',
                ]:
                    interno += dado['qtd']
                else:
                    externo += dado['qtd']

            dados_grafico = [['Interno', interno], ['Externo', externo]]
            grafico_tipo_palestrante = PieChart(
                'grafico_tipo_palestrante',
                title='Perfil do Palestrante',
                subtitle='Quantidade de eventos por perfil do palestrante',
                minPointLength=0,
                data=dados_grafico,
            )

            # Indicadores:
            total_trabalhos_submetidos = Submissao.objects.filter(modalidade__evento__in=eventos).count()
            total_participantes = Participante.objects.filter(evento__in=eventos).distinct().count()
            razao_trabalhos_participantes = 0
            if total_participantes != 0:
                razao_trabalhos_participantes = total_trabalhos_submetidos / total_participantes

    return locals()


@permission_required('eventos.change_evento')
@rtr()
def relatorio_participantes(request):
    title = 'Relatório de Participantes dos Eventos'
    form = RelatorioParticipantesEventosForm(request.GET or None)
    if form.is_valid():
        eventos = Evento.objects.filter(deferido=True)
        titulo = form.cleaned_data['titulo']
        dimensao = form.cleaned_data['dimensao']
        ano = form.cleaned_data['ano']
        campus = form.cleaned_data['campus']
        if titulo:
            q_filters = [Q(nome__icontains=titulo), Q(apresentacao__icontains=titulo)]
            eventos = eventos.filter(reduce(operator.or_, q_filters))
        if dimensao:
            eventos = eventos.filter(dimensoes=dimensao)
        if ano != 'Todos':
            eventos = eventos.filter(
                Q(data_inicio__year__lte=int(ano), data_fim__year__gte=int(ano)) | Q(data_fim__isnull=True, data_inicio__year=int(ano))
            )
        if campus:
            eventos = eventos.filter(campus=campus)
        participantes = (
            Participante.objects.filter(evento_id__in=eventos.distinct().values_list('id', flat=True))
            .select_related('evento')
            .only(
                'nome',
                'certificado_enviado',
                'evento__nome',
                'evento__data_inicio',
                'evento__data_fim',
                'evento__hora_inicio',
                'evento__hora_fim',
            )
        )
        fields = (
            'nome',
            'certificado_enviado',
            'evento.hora_inicio',
            'evento.hora_fim',
        )
        custom_fields = {
            'nome_evento': Column('Nome do Evento', accessor='evento.nome', order_by='evento.nome'),
            'evento.data_inicio': DateColumn(format='d/m/Y'),
            'evento.data_fim': DateColumn(format='d/m/Y'),
        }

        sequence = [
            'nome',
            'certificado_enviado',
            'nome_evento',
            'evento.data_inicio',
            'evento.hora_inicio',
            'evento.data_fim',
            'evento.hora_fim',
        ]
        table = get_table(
            queryset=participantes,
            fields=fields,
            custom_fields=custom_fields,
            sequence=sequence,
            per_page_field=100,
        )
        if request.GET.get('relatorio', None):
            return tasks.table_export(request.GET.get('relatorio', None), *table.get_params())

    return locals()


@rtr()
@login_required()
def adicionar_participante(request, evento_id, tipo_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    tipo_participante = TipoParticipante.objects.get(pk=tipo_id)
    if not evento.pode_gerenciar(request.user) and not request.user.is_superuser:
        raise PermissionDenied('Você não pode gerenciar este evento.')
    title = f'Adicionar {tipo_participante}'
    participante = Participante(evento=evento)
    publico_alvo = request.POST.get('publico_alvo', None)
    form = AdicionarParticipanteEventoForm(
        request.POST or None,
        request.FILES or None,
        instance=participante,
        tipo_participante=tipo_participante,
        evento=evento,
        publico_alvo=publico_alvo,
    )
    if form.is_valid():
        form.instance.tipo_id = tipo_id
        form.save()
        return httprr('..', f'{tipo_participante} adicionado com sucesso.')
    return locals()


@rtr()
@login_required()
def editar_participante(request, participante_id):
    participante = get_object_or_404(Participante, pk=participante_id)
    if not participante.evento.pode_gerenciar(request.user) and not request.user.is_superuser:
        raise PermissionDenied('Você não pode gerenciar este evento.')
    title = f'Atualizar {participante.tipo}'
    form = EditarParticipanteEventoForm(request.POST or None, request.FILES or None, instance=participante)
    if form.is_valid():
        form.save()
        return httprr('..', f'{participante.tipo} atualizado com sucesso.')
    return locals()


@rtr()
@login_required()
def importar_participantes_evento(request, evento_id, tipo_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    tipo_participante = get_object_or_404(TipoParticipante, pk=tipo_id)
    if not evento.pode_gerenciar(request.user) and not request.user.is_superuser:
        raise PermissionDenied('Você não pode gerenciar este evento.')

    title = f'Importar {tipo_participante.tipo_participacao.descricao}'
    form = ImportarParticipantesForm(
        request.POST or None,
        files=request.FILES or None,
        evento=evento,
        tipo_participante=tipo_participante,
    )
    if form.is_valid():
        form.processar()
        return httprr('..', 'Participantes adicionados com sucesso.')
    return locals()


@login_required()
def exportar_participantes_evento(request, evento_id, tipo_id):
    obj = get_object_or_404(Evento, pk=evento_id)
    qs = obj.participantes.filter(tipo_id=tipo_id)
    rows = [
        [
            '#',
            'Nome',
            'CPF',
            'Tipo',
            'Público Alvo',
            'E-mail',
            'Telefone',
            'Data de Cadastro',
            'Inscrição Confirmada',
            'Presença Confirmada',
            'Certificado Enviado',
            'Carga Horária',
        ]
    ]
    for i, p in enumerate(qs):
        row = [
            format_(i + 1),
            format_(p.nome),
            format_(p.cpf),
            format_(p.tipo),
            format_(p.publico_alvo),
            format_(p.email),
            format_(p.telefone),
            format_(p.data_cadastro),
            format_(p.inscricao_validada, False),
            format_(p.presenca_confirmada, False),
            format_(p.certificado_enviado, False),
            format_(p.carga_horaria, False),
        ]
        rows.append(row)
    return XlsResponse(rows)


@login_required
def confirmar_inscricao(request, evento_id, tipo_participante_id, pks):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user) and not request.user.is_superuser:
        raise PermissionDenied('Você não pode gerenciar este evento.')

    pks = pks.split('_')
    participantes = '0' in pks and evento.participantes.all() or evento.participantes.filter(pk__in=pks)
    participantes = participantes.filter(tipo=tipo_participante_id)
    qtd_inscroes_confirmadas = 0
    for participante in participantes:
        if not participante.inscricao_validada:
            qtd_inscroes_confirmadas += 1

        participante.inscricao_validada = True
        participante.save()
        Notificar.inscricao_no_evento(evento, participante)

    url = request.META.get(
        'HTTP_REFERER',
        f'/eventos/evento/{evento_id}/?tab=participante{tipo_participante_id}#participantes',
    )
    if qtd_inscroes_confirmadas == 0:
        return httprr(url, 'Nenhuma inscrição confirmada.', tag='error')

    return httprr(url, f'{qtd_inscroes_confirmadas} inscrição(ões) confirmada(s) com sucesso.')


@login_required
def confirmar_presenca(request, evento_id, tipo_participante_id, pks):
    return __confirmar_ou_cancelar_presenca(request, evento_id, tipo_participante_id, 'confirmar', pks)


@login_required
def cancelar_presenca(request, evento_id, tipo_participante_id, pks):
    return __confirmar_ou_cancelar_presenca(request, evento_id, tipo_participante_id, 'cancelar', pks)


@login_required
def __confirmar_ou_cancelar_presenca(request, evento_id, tipo_participante_id, acao, pks):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user) and not request.user.is_superuser:
        raise PermissionDenied('Você não pode gerenciar este evento.')

    pks = pks.split('_')
    participantes = evento.participantes.filter(pk__in=pks, tipo=tipo_participante_id, inscricao_validada=True)
    if acao == 'confirmar':
        qtd_presencas = participantes.update(presenca_confirmada=True)
        confirmada_ou_cancelada = 'confirmada'
    else:
        qtd_presencas = participantes.update(presenca_confirmada=False)
        confirmada_ou_cancelada = 'cancelada'

    for participante in participantes.filter(vinculo__isnull=False):
        participante.registrar_ch_extensao()

    url = request.META.get('HTTP_REFERER') or f'/eventos/evento/{evento_id}/'
    if qtd_presencas == 0:
        return httprr(url, f'Nenhuma presença {confirmada_ou_cancelada}.', tag='error')

    return httprr(url, f'{qtd_presencas} presença(s) {confirmada_ou_cancelada}(s) com sucesso.')


@login_required
def enviar_certificados(request, evento_id, tipo_participante_id, pks):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não pode gerenciar este evento.')

    if not evento.gera_certificado:
        raise PermissionDenied('Este evento não está configurado para gerar certificados.')
    if evento.certificado_bloqueado_por_falta_de_avaliacao_configurada():
        return httprr(
            request.META.get(
                'HTTP_REFERER',
                f'/eventos/evento/{evento_id}/?tab=participante{tipo_participante_id}#participantes',
            ),
            'O envio de certificados está bloqueado. Este evento exige avaliação para emissão do certificado, mas nenhuma avaliação pós-evento foi configurada ainda.',
            tag='error',
        )
    if not evento.estah_realizado():
        return httprr(
            request.META.get(
                'HTTP_REFERER',
                f'/eventos/evento/{evento_id}/?tab=participante{tipo_participante_id}#participantes',
            ),
            'O envio de certificados ainda não está disponível, porque o evento não foi encerrado.',
            tag='error',
        )

    pks = pks.split('_')
    participantes = '0' in pks and evento.participantes.all() or evento.participantes.filter(pk__in=pks)
    participantes = participantes.filter(tipo=tipo_participante_id)
    if evento.exigir_avaliacao_para_certificado:
        participantes = participantes.com_avaliacao_realizada()
    qtd_emails_enviado = 0
    qtd_certificados_bloqueados_por_avaliacao = 0
    qtd_emails_avaliacao_enviado = 0
    qtd_certificados_bloqueados_por_falta_presenca = 0
    qtd_certificados_bloqueados_por_outra_regra = 0
    for participante in participantes.select_related('tipo', 'tipo__tipo_participacao'):
        if evento.exigir_avaliacao_para_certificado and not participante.respondeu_avaliacao_evento():
            qtd_certificados_bloqueados_por_avaliacao += 1
            Notificar.enviar_avaliacao_pendente_para_liberacao_certificado(evento, participante)
            qtd_emails_avaliacao_enviado += 1
            continue
        if not participante.presenca_confirmada:
            qtd_certificados_bloqueados_por_falta_presenca += 1
            continue
        if not participante.certificado_esta_disponivel():
            qtd_certificados_bloqueados_por_outra_regra += 1
            continue
        participante.emitir_certificado()
        Notificar.enviar_certificado_evento(participante)
        participante.marcar_certificado_como_enviado()
        qtd_emails_enviado += 1

    url = request.META.get(
        'HTTP_REFERER',
        f'/eventos/evento/{evento_id}/?tab=participante{tipo_participante_id}#participantes',
    )
    motivos_bloqueio = []
    if qtd_certificados_bloqueados_por_avaliacao > 0:
        motivos_bloqueio.append(
            f'{qtd_certificados_bloqueados_por_avaliacao} participante(s) não respondeu(ram) à avaliação obrigatória, e {qtd_emails_avaliacao_enviado} e-mail(s) de orientação foi(ram) enviado(s)'
        )
    if qtd_certificados_bloqueados_por_falta_presenca > 0:
        motivos_bloqueio.append(f'{qtd_certificados_bloqueados_por_falta_presenca} participante(s) está(ão) sem presença confirmada')
    if qtd_certificados_bloqueados_por_outra_regra > 0:
        motivos_bloqueio.append(
            f'{qtd_certificados_bloqueados_por_outra_regra} participante(s) não atende(m) às demais regras de emissão do certificado'
        )

    if qtd_emails_enviado == 0:
        mensagem = 'Nenhum certificado foi emitido.'
        if motivos_bloqueio:
            mensagem = f'{mensagem} {"; ".join(motivos_bloqueio)}.'
        return httprr(url, mensagem, tag='error')
    if motivos_bloqueio:
        return httprr(
            url,
            f'{qtd_emails_enviado} certificado(s) enviado(s) com sucesso. Também houve bloqueios: {"; ".join(motivos_bloqueio)}.',
            tag='warning',
        )

    return httprr(url, f'{qtd_emails_enviado} E-mail(s) enviado(s) com sucesso.')


@login_required
def enviar_avaliacao(request, evento_id, tipo_participante_id, pks):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não pode gerenciar este evento.')

    if not evento.get_perguntas_avaliacao().exists():
        return httprr(
            reverse('participantes', args=(evento.id,)),
            'Este evento não possui avaliação configurada.',
            'warning',
        )

    pks = pks.split('_')
    participantes = '0' in pks and evento.participantes.all() or evento.participantes.filter(pk__in=pks)
    participantes = participantes.filter(tipo=tipo_participante_id)
    qtd_emails_enviado = 0

    for participante in participantes:
        if participante.email:
            Notificar.enviar_avaliacao_evento(evento, participante)
            qtd_emails_enviado += 1

    url = request.META.get(
        'HTTP_REFERER',
        f'/eventos/evento/{evento_id}/?tab=participante{tipo_participante_id}#participantes',
    )
    if qtd_emails_enviado == 0:
        return httprr(url, 'Nenhum e-mail enviado.', tag='error')

    return httprr(url, f'{qtd_emails_enviado} E-mail(s) enviado(s) com sucesso.')


@rtr()
def baixar_certificado(request, evento_id=None, atividade_id=None):
    codigo_geracao_certificado = request.GET.get('hash')
    if codigo_geracao_certificado:
        participante = get_object_or_404(Participante, codigo_geracao_certificado=codigo_geracao_certificado)
        if not participante.certificado_esta_disponivel() or not participante.codigo_geracao_certificado:
            return httprr('/', 'O certificado ainda não está disponível para este participante.', 'error')
        atividades_participante = participante.get_atividades()
        evento = participante.evento
    else:
        evento = get_object_or_404(Evento, pk=evento_id)
        tipo_participante = request.GET.get('tipo-participante')
        if not tipo_participante:
            return httprr(
                f'/eventos/evento/{evento.id}/?tab=detalhamento',
                'Tipo de Participante não informado.',
                'error',
            )
        participante = Participante(nome='Participante Teste', cpf='000.000.000-00', evento=evento)
        atividades_participante = AtividadeEvento.objects.filter(evento=evento).all()
        for i, a in enumerate(atividades_participante):
            a.descricao = f'Atividade de Teste #{i + 1}'
        participante.get_atividades = lambda atividades, confirmadas=None: atividades_participante
        participante.tipo = TipoParticipante.objects.get(pk=tipo_participante)
        participante.codigo_geracao_certificado = 'xxxxxxxxx'

    modelo_certificado = participante.get_modelo_certificado()
    if not modelo_certificado:
        return httprr('..', 'Participante sem modelo de certificado definido.', 'error')

    dados_certificado = participante.get_dados_certificado(atividade_id=atividade_id)
    try:
        caminho_arquivo = gerar_documento_impressao(dados_certificado, io.BytesIO(modelo_certificado.read()))
        if participante.tipo.tipo_participacao.descricao == 'Autor de trabalho':
            trabalhos_aprovados = participante.get_trabalhos_aprovados()
            if trabalhos_aprovados.exists():
                submissoes = {'submissoes': trabalhos_aprovados}
                caminho_arquivo = anexar_tabela_trabalhos_aprovados(submissoes, caminho_arquivo)

    except Exception as e:
        return httprr('/', str(e), 'error')

    if not caminho_arquivo:
        aba = slugify(participante.tipo.tipo_participacao.descricao)
        return httprr(
            f'/eventos/evento/{evento.id}/?tab={aba}',
            'Documento não encontrado.',
            'error',
        )

    nome_arquivo = caminho_arquivo.split('/')[-1]
    try:
        arquivo = open(caminho_arquivo, 'rb')
    except Exception:
        aba = slugify(participante.tipo.tipo_participacao.descricao)
        return httprr(
            f'/eventos/evento/{evento.id}/?tab={aba}',
            'Modelo de certificado não encontrado.',
            'error',
        )

    content_type = caminho_arquivo.endswith('.pdf') and 'application/pdf' or 'application/vnd.ms-word'
    response = HttpResponse(arquivo.read(), content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename={nome_arquivo}'
    arquivo.close()
    os.unlink(caminho_arquivo)
    return response


# enumerar_paginas=False, pdf_response=True, exibe_emissor=True
@documento()
@rtr()
@login_required
def declaracao_avaliador_pdf(request, evento_id, avaliador_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para gerar baixar uma declaração do avaliador neste evento.')
    avaliador = get_object_or_404(Participante, pk=avaliador_id)
    instituicao = str(Configuracao.get_valor_por_chave('comum', 'instituicao'))
    return locals()


@rtr()
def download(request, hash_certificado, atividade_id=None):
    participante = get_object_or_404(Participante, codigo_geracao_certificado=hash_certificado)
    if not participante.certificado_esta_disponivel() or not participante.codigo_geracao_certificado:
        return httprr('/', 'O certificado ainda não está disponível para este participante.', 'error')
    modelo_certificado = participante.get_modelo_certificado()

    if not modelo_certificado:
        return httprr('..', 'Participante sem modelo de certificado definido.', 'error')

    try:
        dados_certificado = participante.get_dados_certificado(atividade_id)
        caminho_arquivo = gerar_documento_impressao(dados_certificado, io.BytesIO(modelo_certificado.read()))
        if participante.tipo.tipo_participacao.descricao == 'Autor de trabalho':
            trabalhos_aprovados = participante.get_trabalhos_aprovados()
            if trabalhos_aprovados.exists():
                submissoes = {'submissoes': trabalhos_aprovados}
                caminho_arquivo = anexar_tabela_trabalhos_aprovados(submissoes, caminho_arquivo)

    except Exception as e:
        return httprr('/', str(e), 'error')

    if not caminho_arquivo:
        aba = slugify(participante.tipo.tipo_participacao.descricao)
        return httprr(
            f'/eventos/evento/{participante.evento_id}/?tab={aba}',
            'Documento não encontrado.',
            'error',
        )

    nome_arquivo = caminho_arquivo.split('/')[-1]
    try:
        arquivo = open(caminho_arquivo, 'rb')
    except Exception:
        aba = slugify(participante.tipo.tipo_participacao.descricao)
        return httprr(
            f'/eventos/evento/{participante.evento_id}/?tab={aba}',
            'Modelo de certificado não encontrado.',
            'error',
        )

    content_type = caminho_arquivo.endswith('.pdf') and 'application/pdf' or 'application/vnd.ms-word'
    response = HttpResponse(arquivo.read(), content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename={nome_arquivo}'
    arquivo.close()
    os.unlink(caminho_arquivo)
    return response


@rtr()
@login_required()
@permission_required('eventos.change_evento')
def adicionar_anexo_evento(request, evento_id):
    obj = get_object_or_404(Evento, pk=evento_id)
    form = AnexoEventoForm(data=request.POST or None, files=request.FILES or None)
    if form.is_valid():
        form.save(obj)
        return httprr('..', 'Anexo adicionado com sucesso')
    return locals()


@rtr()
@login_required()
@permission_required('eventos.change_evento')
def adicionar_foto_evento(request, evento_id):
    obj = get_object_or_404(Evento, pk=evento_id)
    form = FotoEventoForm(data=request.POST or None, files=request.FILES or None)
    if form.is_valid():
        form.save(obj)
        return httprr('..', 'Foto adicionada com sucesso.')
    return locals()


@rtr()
@login_required()
@permission_required('eventos.change_evento')
def adicionar_video_evento(request, evento_id):
    obj = get_object_or_404(Evento, pk=evento_id)
    form = VideoEventoForm(request.POST or None)
    if form.is_valid():
        form.save(obj)
        return httprr('..', 'Vídeo adicionado com sucesso.')
    return locals()


@rtr()
@login_required()
@permission_required('eventos.change_evento')
def remover_foto_evento(request, foto_id):
    obj = get_object_or_404(FotoEvento, pk=foto_id)
    evento = obj.evento
    obj.delete()
    return httprr(f'/eventos/evento/{evento.id}/?tab=fotos', 'Foto removida com sucesso.')


@rtr()
@login_required()
@permission_required('eventos.change_evento')
def remover_video_evento(request, video_id):
    obj = get_object_or_404(VideoEvento, pk=video_id)
    evento = obj.evento
    obj.delete()
    return httprr(f'/eventos/evento/{evento.id}/?tab=videos', 'Vídeo removido com sucesso.')


@login_required
def enviar_link_registro_presenca(request, evento_id, tipo_participante_id, pks):
    evento = get_object_or_404(Evento, pk=evento_id, registrar_presenca_online=True)
    if not evento.pode_gerenciar(request.user) and not request.user.is_superuser:
        raise PermissionDenied('Você não pode gerenciar este evento.')
    if not evento.estah_em_periodo_realizacao():
        raise PermissionDenied('Evento fora do período de realização.')
    pks = pks.split('_')
    participantes = '0' in pks and evento.participantes.all() or evento.participantes.filter(pk__in=pks)
    participantes = participantes.filter(tipo=tipo_participante_id)
    for participante in participantes.filter(inscricao_validada=True, presenca_confirmada=False):
        Notificar.confirmar_presenca_por_link_em_evento(evento, participante)

    url = request.META.get(
        'HTTP_REFERER',
        f'/eventos/evento/{evento_id}/?tab=participante{tipo_participante_id}#participantes',
    )
    return httprr(url, 'Emails enviados com sucesso.')


@login_required
def enviar_link_registro_presenca_atividades(request, evento_id, pks):
    evento = get_object_or_404(Evento, pk=evento_id, registrar_presenca_online=True)
    if not evento.pode_gerenciar(request.user) and not request.user.is_superuser:
        raise PermissionDenied('Você não pode gerenciar este evento.')
    if not evento.estah_em_periodo_realizacao():
        raise PermissionDenied('Evento fora do período de realização.')

    pks = pks.split('_')
    total_emails = 0
    atividades_processadas = []

    for atividade in evento.atividadeevento_set.filter(pk__in=pks):
        participantes = evento.participantes.filter(atividades=atividade, inscricao_validada=True).exclude(pk__in=atividade.participantes.all())

        count_participantes = participantes.count()
        total_emails += count_participantes

        if count_participantes > 0:
            atividades_processadas.append(f'{atividade.descricao} ({count_participantes})')

        for participante in participantes:
            Notificar.confirmar_presenca_por_link_em_atividade(atividade, participante)

    url = request.META.get('HTTP_REFERER', f'/eventos/evento/{evento_id}/?tab=atividades')

    if total_emails == 0:
        return httprr(
            url,
            'Nenhum participante elegível encontrado. Verifique se há participantes com inscrição validada e sem presença confirmada.',
            tag='warning',
        )

    mensagem = f'{total_emails} E-mail(s) enviado(s) com sucesso!\n'
    mensagem += f'Atividades: {" | ".join(atividades_processadas)}\n'
    mensagem += 'Links válidos por 1 HORA. Reenviar email renova a validade.'

    return httprr(url, mensagem)


def confirmar_presenca_por_link_atividade(request, atividade_id, participante_id):
    TEMPO_VALIDADE_LINK_HORAS = 1  # Link válido por 1 hora

    try:
        data_hash = signing.loads(request.GET['hash'])
        if not participante_id == data_hash.get('participante_id'):
            raise PermissionDenied('Código não confere.')

        # Validar se o link ainda está dentro do prazo de 1 hora
        timestamp_envio = data_hash.get('timestamp')
        if timestamp_envio:
            tempo_decorrido = datetime.now().timestamp() - timestamp_envio
            tempo_maximo_segundos = TEMPO_VALIDADE_LINK_HORAS * 3600

            if tempo_decorrido > tempo_maximo_segundos:
                raise PermissionDenied(
                    f'Link expirado. O link é válido por apenas {TEMPO_VALIDADE_LINK_HORAS} hora(s) a partir do envio. Por favor, solicite ao organizador do evento que reenvie o email para renovar o link.'
                )
    except PermissionDenied:
        raise
    except Exception:
        raise PermissionDenied('Erro ao localizar código.')

    atividade = get_object_or_404(AtividadeEvento, pk=atividade_id)
    participante = get_object_or_404(Participante, pk=participante_id)
    atividade.participantes.add(participante)
    atividade.participantes.update(inscricao_validada=True, presenca_confirmada=True)
    url = '/'
    if request.GET.get('next'):
        url = request.META.get('HTTP_REFERER', '/')
    return httprr(url, f'Presença confirmada com sucesso na atividade {atividade.descricao}.')


def confirmar_presenca_por_link(request, evento_id, participante_id):
    try:
        if not participante_id == signing.loads(request.GET['hash']).get('participante_id'):
            raise PermissionDenied('Código não confere.')
    except Exception:
        raise PermissionDenied('Erro ao localizar código.')

    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        if evento.registrar_presenca_online is False:
            raise PermissionDenied('Não é possível registrar presença online neste evento.')
        if not evento.estah_em_periodo_realizacao():
            raise PermissionDenied('Evento fora do período de realização.')

    participante = get_object_or_404(Participante, pk=participante_id)
    participante.presenca_confirmada = True
    participante.save()
    url = '/'
    if request.GET.get('next'):
        url = request.META.get('HTTP_REFERER', '/')
    return httprr(url, f'Presença confirmada com sucesso no evento {evento.nome}.')


@rtr()
@login_required()
def importar_lista_presenca(request, evento_id, tipo_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user) and not request.user.is_superuser:
        raise PermissionDenied('Você não pode gerenciar este evento.')

    title = 'Importar Lista de Presença'
    form = ImportarListaPresencaForm(
        evento,
        tipo_id,
        data=request.POST or None,
        files=request.POST and request.FILES or None,
    )
    if form.is_valid():
        form.processar()
        return httprr('..', 'Presenças atualizadas com sucesso.')
    return locals()


@rtr()
@login_required()
def informar_atividades(request, participante_id):
    participante = get_object_or_404(Participante, pk=participante_id)
    if not participante.evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para realizar essa operação neste evento.')
    title = 'Inscrever Participante'
    form = InformarAtividadesForm(data=request.POST or None, instance=participante)
    if form.is_valid():
        form.save()
        if participante.vinculo_id:
            participante.registrar_ch_extensao()
        return httprr('..', 'Participante inscrito com sucesso.')
    return locals()


@rtr()
@permission_required('eventos.change_evento')
def informar_participantes(request, pk, atividade_id):
    obj = get_object_or_404(Evento, pk=pk)
    title = 'Informar Participantes'
    form = InformarParticipantesForm(data=request.POST or None, files=request.FILES or None)
    if form.is_valid():
        form.processar(atividade_id)
        return httprr('..', 'Participantes informados com sucesso.')
    return locals()


@rtr()
@permission_required('eventos.change_evento')
def lista_participantes(request, pk, atividade_id):
    atividade = get_object_or_404(AtividadeEvento, pk=atividade_id)
    evento = get_object_or_404(Evento, pk=pk)
    title = f'Lista de Presença - {atividade}'
    inscritos = Participante.objects.filter(evento=pk, atividades=atividade_id)
    popup = ''
    q = request.GET.get('q', '')
    if request.GET.get('_popup'):
        popup = '&_popup=1'
    if q:
        inscritos = inscritos.filter(nome__unaccent__icontains=q) | inscritos.filter(cpf__contains=q)
    inscritos = inscritos.order_by('nome')
    pode_gerenciar = request.user.is_superuser or evento.pode_gerenciar(request.user)
    presentes = atividade.participantes.values_list('id', flat=True)
    if request.POST:
        for id in request.POST.getlist('adicionar'):
            atividade.participantes.add(id)
        for id in request.POST.getlist('remover'):
            atividade.participantes.remove(id)
        atividade.participantes.update(inscricao_validada=True, presenca_confirmada=True)
        url = f'/eventos/lista_participantes/{pk}/{atividade_id}/?q={q}{popup}'
        return httprr(url, 'Lista atualizada com sucesso.')
    return locals()


@documento()
@rtr()
@permission_required('eventos.change_evento')
def lista_participantes_pdf(request, pk, atividade_id):
    atividade = get_object_or_404(AtividadeEvento, pk=atividade_id)
    evento = get_object_or_404(Evento, pk=pk)
    q = request.GET.get('q', '')
    tipo = request.GET.get('tipo', '')
    participantes = Participante.objects.filter(evento=pk, atividades=atividade_id)
    if q:
        participantes = participantes.filter(nome__unaccent__icontains=q) | participantes.filter(cpf__contains=q)

    if tipo == 'todos':
        title = f'Lista de Inscritos - {atividade}'
    elif tipo == 'confirmados':
        title = f'Lista Presentes - {atividade}'
        presentes = atividade.participantes.values_list('id', flat=True)
        participantes = participantes.filter(id__in=presentes)
    elif tipo == 'nao_confirmados':
        title = f'Lista Não Presentes - {atividade}'
        presentes = atividade.participantes.values_list('id', flat=True)
        participantes = participantes.exclude(id__in=presentes)

    participantes = participantes.order_by('nome')
    return locals()


@rtr()
@permission_required('eventos.change_evento')
def enviar_mensagem(request, pk):
    obj = get_object_or_404(Evento, pk=pk)
    title = 'Enviar Mensagem'
    pode_gerenciar = request.user.is_superuser or obj.pode_gerenciar(request.user)
    if pode_gerenciar:
        form = EnviarMensagemForm(obj, data=request.POST or None)
        if form.is_valid():
            assunto = form.cleaned_data['assunto']
            mensagem = ''.join([f'<p>{line}</p>' for line in form.cleaned_data['mensagem'].split('\n')])
            titulo = f'[SUAP] Mensagem do Evento - {assunto}'
            html = f'<h1>{obj}</h1>{mensagem}'
            for participante in obj.participantes.all():
                send_mail(
                    titulo,
                    html,
                    settings.DEFAULT_FROM_EMAIL,
                    [participante.email],
                    fail_silently=True,
                )
            return httprr('..', 'Mensagem enviada com sucesso.')
    return locals()


@minhas_acoes.registrar_acao()
def minhas_acoes_eventos(request, data, datahora_inicio, datahora_fim):
    filters_participacao = {}
    filters_organizador = {}
    if datahora_inicio:
        filters_participacao['data_inicio__gte'] = datahora_inicio
        filters_organizador['data_inicio__gte'] = datahora_inicio
    if datahora_fim:
        filters_participacao['data_fim__lte'] = datahora_fim
        filters_organizador['data_fim__lte'] = datahora_fim

    eventos_participante = (
        Evento.objects.filter(
            Q(participantes__cpf=request.user.get_profile().cpf) & Q(participantes__tipo__tipo_participacao__descricao='Participante')
        )
        .filter(**filters_participacao)
        .order_by('data_fim')
    )
    eventos_organizador = (
        Evento.objects.filter(
            Q(participantes__cpf=request.user.get_profile().cpf) & Q(participantes__tipo__tipo_participacao__descricao='Organizador')
        )
        .filter(**filters_organizador)
        .order_by('data_fim')
    )

    for evento in eventos_participante:
        participante = evento.participantes.filter(
            tipo__tipo_participacao__descricao='Participante',
            cpf=request.user.get_profile().cpf,
        ).first()
        titulo = f'{evento.nome} ({participante.get_ch_total()}h)' if participante.get_ch_total() != '-' else evento.nome
        data.append(
            (
                'Eventos',
                'Participação em eventos',
                titulo,
                f'de {evento.data_inicio.strftime("%d/%m/%Y")} a {evento.data_fim.strftime("%d/%m/%Y")}',
                f'{evento.get_absolute_url()}',
            )
        )
    for evento in eventos_organizador:
        participante = evento.participantes.filter(
            tipo__tipo_participacao__descricao='Organizador',
            cpf=request.user.get_profile().cpf,
        ).first()
        titulo = f'{evento.nome} ({participante.get_ch_total()}h)' if participante.get_ch_total() != '-' else evento.nome
        data.append(
            (
                'Eventos',
                'Organização de eventos',
                titulo,
                f'de {evento.data_inicio.strftime("%d/%m/%Y")} a {evento.data_fim.strftime("%d/%m/%Y")}',
                f'{evento.get_absolute_url()}',
            )
        )


@rtr()
@login_required()
def gerar_planilha_autores_aprovados(request, evento_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para gerar esta planilha neste evento.')

    areas_tematica_modalidade = AreaTematicaModalidade.objects.filter(modalidade__evento=evento).order_by('modalidade__tipo', 'area_tematica__titulo')

    headers = [
        'CPF',
        'Nome',
        'E-mail',
        'Perfil',
        'Telefone',
        'Título',
    ]

    data = []

    for area_tematica in areas_tematica_modalidade:
        lista_submissoes_aprovadas = Submissao.listar_resultado(area_tematica, True)
        for item in lista_submissoes_aprovadas:
            submissao = Submissao.objects.get(pk=item['id'])
            for participante in submissao.autores:
                data.append(
                    {
                        'CPF': format_(participante.cpf),
                        'Nome': format_(participante.nome),
                        'E-mail': format_(participante.email),
                        'Perfil': format_(participante.publico_alvo and participante.publico_alvo.descricao),
                        'Telefone': participante.telefone,
                        'Título': format_(submissao.titulo),
                    }
                )

    df = pd.DataFrame(data, columns=headers)

    # Geração do arquivo XLS como resposta
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename=autores_aprovados_evento_{evento_id}.xlsx'

    with pd.ExcelWriter(response, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Autores Aprovados', index=False)

    return response


@documento()
@rtr()
@login_required
def lista_trabalhos_aprovados_pdf(request, evento_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para imprimir a lista de trabalhos aprovados neste evento.')

    trabalhos = []
    areas = AreaTematicaModalidade.objects.filter(modalidade__evento=evento).order_by('modalidade__tipo', 'area_tematica__titulo')
    for area in areas:
        submissoes = Submissao.listar_resultado(area)
        trabalhos.append({'area': area, 'submissoes': submissoes})
    return locals()


@csrf_exempt
def submeter_trabalho_atualizar_tipo_autor(request, evento_id):
    # evento = get_object_or_404(Evento, pk=evento_id)
    if request.method == 'POST':
        autor_id = request.POST.get('autor_id')
        # autor = get_object_or_404(Participante, id=autor_id)
        tipo_autor = request.POST.get('tipo_autor')
        if 'autores_tipo' not in request.session:
            request.session['autores_tipo'] = {}

        request.session['autores_tipo'][autor_id] = tipo_autor
        request.session.modified = True  # Garante que a sessão seja salva
        return JsonResponse({'mensagem': 'Autor alterado com sucesso.'})

    return JsonResponse({'erro': 'Método não permitido.'}, status=405)


@rtr()
@login_required()
def gerar_etiqueta_participante_em_lote(request, evento_id, tipo_participante_id, pks):
    evento = get_object_or_404(Evento, pk=evento_id)
    tipo_participante = get_object_or_404(TipoParticipante, pk=tipo_participante_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para convidar participantes neste evento.')
    pks = pks.split('_')
    participantes_selecionados = evento.participantes.filter(tipo=tipo_participante.id, pk__in=pks)

    if not participantes_selecionados.exists():
        messages.error(request, 'Nenhum participante selecionado para gerar etiquetas.')
        return redirect(f'/eventos/evento/{evento_id}/?tab=participante')

    buffer = BytesIO()
    # Configuração para 20 etiquetas por página: 2 colunas x 10 linhas
    num_columns = 2
    num_rows = 10
    labels_per_page = num_columns * num_rows
    label_height = 25.4 * mm
    horizontal_distance = 106.8 * mm
    left_margin = 3.5 * mm
    top_margin = 12.7 * mm
    _, page_height = letter
    c = canvas.Canvas(buffer, pagesize=letter)
    c.setFont('Helvetica', 8)
    current_label_index = 0
    temp_qr_files = []

    for participante in participantes_selecionados:
        if current_label_index >= labels_per_page:
            c.showPage()
            current_label_index = 0
        col_index = current_label_index % num_columns
        row_index = math.floor(current_label_index / num_columns)
        x_pos = left_margin + (col_index * horizontal_distance)
        y_pos = page_height - top_margin - label_height - (row_index * label_height)
        temp_qr_file = participante.gerar_qr_code()
        temp_qr_files.append(temp_qr_file)
        qr_code_size = 20 * mm
        qr_x = x_pos + 2 * mm
        qr_y = y_pos + (label_height - qr_code_size) / 2
        c.drawInlineImage(temp_qr_file.name, qr_x, qr_y, width=qr_code_size, height=qr_code_size)
        text_x = qr_x + qr_code_size + 3 * mm
        text_y_name = y_pos + label_height - 7 * mm
        text_y_type = y_pos + label_height - 12 * mm
        c.drawString(text_x, text_y_name, participante.get_nome_curto())
        c.drawString(text_x, text_y_type, participante.tipo.tipo_participacao.descricao)
        current_label_index += 1
    c.save()
    buffer.seek(0)

    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="etiquetas_modelo_6181_evento_{evento_id}.pdf"'
    for temp_file in temp_qr_files:
        temp_file.close()

    return response


@rtr()
@login_required()
def adicionar_tipo_participante(request, evento_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para adicionar tipos de participantes neste evento.')
    title = 'Adicionar Tipo de Participante'
    form = TipoParticipanteForm(request.POST or None, request.FILES or None, evento=evento)
    if form.is_valid():
        form.save()
        return httprr('..', 'Tipo de participante adicionado com sucesso.')
    return locals()


@rtr()
@login_required()
def editar_tipo_participante(request, evento_id, tipo_participante_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para adicionar tipos de participantes neste evento.')
    tipo_participante = get_object_or_404(TipoParticipante, pk=tipo_participante_id, evento=evento)
    title = 'Editar Tipo de Participante'
    form = TipoParticipanteForm(
        request.POST or None,
        request.FILES or None,
        evento=evento,
        instance=tipo_participante,
    )
    if form.is_valid():
        form.save()
        return httprr('..', 'Tipo de participante alterado com sucesso.')
    return locals()


@rtr()
@login_required()
def remover_tipo_participante(request, evento_id, tipo_participante_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para adicionar tipos de participantes neste evento.')
    tipo_participante = get_object_or_404(TipoParticipante, pk=tipo_participante_id, evento=evento)
    if tipo_participante.participantes.exists():
        return httprr(
            f'/eventos/evento/{evento.id}/?tab=detalhamento',
            'Tipo de participante não pode ser removido, pois possui participantes associados.',
            'error',
        )

    tipo_participante.delete()
    return httprr(
        f'/eventos/evento/{evento.id}/?tab=detalhamento',
        'Tipo de participante removido com sucesso.',
    )


@rtr()
@login_required()
def adicionar_atividade(request, evento_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para adicionar atividades neste evento.')
    title = 'Adicionar Atividade'
    form = AtividadeEventoForm(request.POST or None, evento=evento)
    if form.is_valid():
        form.save()
        return httprr('..', 'Atividade adicionada com sucesso.')
    return locals()


@rtr()
@login_required()
def editar_atividade(request, evento_id, atividade_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para adicionar atividades neste evento.')
    atividade = get_object_or_404(AtividadeEvento, pk=atividade_id, evento=evento)
    title = 'Editar Atividade'
    form = AtividadeEventoForm(request.POST or None, evento=evento, instance=atividade)
    if form.is_valid():
        form.save()
        return httprr('..', 'Atividade alterada com sucesso.')
    return locals()


@rtr()
@login_required()
def remover_atividade(request, evento_id, atividade_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para adicionar atividades neste evento.')
    atividade = get_object_or_404(AtividadeEvento, pk=atividade_id, evento=evento)
    if atividade.participantes.exists():
        return httprr(
            f'/eventos/evento/{evento.id}/?tab=atividades',
            'Atividade não pode ser removida, pois possui participantes associados.',
            'error',
        )

    atividade.delete()
    return httprr(
        f'/eventos/evento/{evento.id}/?tab=atividades',
        'Atividade removida com sucesso.',
    )


@rtr()
@login_required()
def adicionar_internacionalizacao(request, evento_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para adicionar internacionalizações neste evento.')
    title = 'Adicionar Internacionalização'
    form = InternacionalizacaoForm(request.POST or None, evento=evento)
    if form.is_valid():
        form.save()
        return httprr('..', 'Internacionalização adicionada com sucesso.')
    return locals()


@rtr()
@login_required()
def editar_internacionalizacao(request, evento_id, internacionalizacao_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para adicionar internacionalizações neste evento.')
    internacionalizacao = get_object_or_404(Internacionalizacao, pk=internacionalizacao_id, evento=evento)
    title = 'Editar Internacionalização'
    form = InternacionalizacaoForm(request.POST or None, evento=evento, instance=internacionalizacao)
    if form.is_valid():
        form.save()
        return httprr('..', 'Internacionalização alterada com sucesso.')
    return locals()


@rtr()
@login_required()
def remover_internacionalizacao(request, evento_id, internacionalizacao_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para adicionar internacionalizações neste evento.')
    internacionalizacao = get_object_or_404(Internacionalizacao, pk=internacionalizacao_id, evento=evento)

    internacionalizacao.delete()
    return httprr(
        f'/eventos/evento/{evento.id}/?tab=internacionalizacao',
        'Internacionalização removida com sucesso.',
    )


@login_required()
@rtr('eventos/templates/listar_areas_tematicas.html')
def listar_areas_tematicas(request, evento_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    pode_gerenciar = evento.pode_gerenciar(request.user)
    if not pode_gerenciar:
        raise PermissionDenied('Você não tem permissão para visualizar as áreas temáticas deste evento.')
    title = 'Áreas Temáticas do Evento'
    areas_tematicas = AreaTematica.objects.filter(evento=evento).order_by('titulo')
    return locals()


@login_required()
@rtr()
def adicionar_area_tematica(request, evento_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para realizar essa operação neste evento.')
    title = 'Adicionar área temática ao evento'
    form = AreaTematicaForm(request.POST or None, evento=evento)
    if form.is_valid():
        form.save()
        return httprr('..', 'Área temática adicionada com sucesso.')
    return locals()


@login_required()
@rtr()
def editar_area_tematica(request, evento_id, area_tematica_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para realizar essa operação neste evento.')
    title = 'Editar área temática do evento'
    area_tematica = get_object_or_404(AreaTematica, pk=area_tematica_id, evento=evento)
    form = AreaTematicaForm(request.POST or None, evento=evento, instance=area_tematica)
    if form.is_valid():
        form.save()
        return httprr('..', 'Área temática editada com sucesso.')
    return locals()


@login_required()
@rtr()
def remover_area_tematica(request, evento_id, area_tematica_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para realizar essa operação neste evento.')
    area_tematica = get_object_or_404(AreaTematica, pk=area_tematica_id, evento=evento)
    # if area_tematica.eventos.exists():
    #     return httprr(
    #         reverse('listar_area_tematica', args=(evento.id,)),
    #         'Área temática não pode ser removida, pois possui eventos associados.',
    #         'error',
    #     )
    area_tematica.delete()
    return httprr(
        reverse('listar_area_tematica', args=(evento.id,)),
        'Área temática removida com sucesso.',
    )


@login_required()
@rtr('eventos/templates/listar_tipo_modalidade.html')
def listar_tipo_modalidade(request, evento_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para visualizar os tipos de modalidade deste evento.')
    title = 'Tipos de Modalidade do Evento'
    tipos_modalidade = TipoModalidade.objects.filter(evento=evento).order_by('titulo')
    pode_gerenciar = evento.pode_gerenciar(request.user)
    return locals()


@login_required()
@rtr()
def adicionar_tipo_modalidade(request, evento_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para realizar essa operação neste evento.')
    title = 'Adicionar Tipo de Modalidade ao Evento'
    form = TipoModalidadeForm(request.POST or None, evento=evento)
    if form.is_valid():
        form.save()
        return httprr('..', 'Tipo de modalidade adicionado com sucesso.')
    return locals()


@login_required()
@rtr()
def editar_tipo_modalidade(request, evento_id, tipo_modalidade_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para realizar essa operação neste evento.')
    title = 'Editar Tipo de Modalidade do Evento'
    tipo_modalidade = get_object_or_404(TipoModalidade, pk=tipo_modalidade_id, evento=evento)
    form = TipoModalidadeForm(request.POST or None, evento=evento, instance=tipo_modalidade)
    if form.is_valid():
        form.save()
        return httprr('..', 'Tipo de modalidade editado com sucesso.')
    return locals()


@login_required()
@rtr()
def remover_tipo_modalidade(request, evento_id, tipo_modalidade_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para realizar essa operação neste evento.')
    tipo_modalidade = get_object_or_404(TipoModalidade, pk=tipo_modalidade_id, evento=evento)
    if tipo_modalidade.modalidade_set.exists():
        return httprr(
            reverse('listar_tipo_modalidade', args=(evento.id,)),
            'Tipo de modalidade não pode ser removido, pois possui modalidades associadas.',
            'error',
        )
    tipo_modalidade.delete()
    return httprr(
        reverse('listar_tipo_modalidade', args=(evento.id,)),
        'Tipo de modalidade removido com sucesso.',
    )


@login_required()
@rtr('eventos/templates/fluxo_submissao.html')
def adicionar_fluxo_submissao(request, evento_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para realizar essa operação neste evento.')
    title = 'Adicionar Fluxo de Submissão'
    form = FluxoSubmissaoForm(request.POST or None, request.FILES or None, evento=evento)
    if form.is_valid():
        form.save()
        return httprr('..', 'Fluxo de submissão adicionado com sucesso.')
    return locals()


@login_required()
@rtr()
def editar_fluxo_submissao(request, fluxo_submissao_id):
    fluxo_submissao = get_object_or_404(FluxoSubmissao, pk=fluxo_submissao_id)
    if not fluxo_submissao.evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para realizar essa operação neste evento.')
    title = 'Editar Fluxo de Submissão'
    form = FluxoSubmissaoForm(request.POST or None, request.FILES or None, instance=fluxo_submissao)
    if form.is_valid():
        form.save()
        return httprr('..', 'Fluxo de submissão alterado com sucesso.')
    return locals()


@login_required()
@rtr()
def remover_fluxo_submissao(request, fluxo_submissao_id):
    # TODO: precisa validar se pode excluir
    fluxo_submissao = get_object_or_404(FluxoSubmissao, pk=fluxo_submissao_id)
    if not fluxo_submissao.evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para realizar essa operação neste evento.')
    evento_id = fluxo_submissao.evento.id
    fluxo_submissao.delete()
    return httprr(
        f'/eventos/evento/{evento_id}/?tab=submissao_trabalhos',
        'Fluxo de submissão removida com sucesso.',
    )


@login_required()
@rtr()
def processar_avaliacoes(request, evento_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para processar avaliações neste evento.')

    url = f'/eventos/evento/{evento.id}/?tab=avaliacao_trabalhos'
    mensagem, tag = evento.processar_avaliacoes(usuario=request.user)
    return httprr(url, mensagem, tag)


@rtr()
@login_required()
def processar_resultados_para_avaliacao_presencial(request, evento_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para processar os resultados deste evento.')

    url = f'/eventos/evento/{evento.id}/?tab=avaliacao_trabalhos'
    mensagem, tag = evento.processar_resultados_para_avaliacao_presencial(usuario=request.user)
    return httprr(url, mensagem, tag)


@rtr()
@login_required()
def processar_resultados_finais(request, evento_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para processar os resultados deste evento.')

    url = f'/eventos/evento/{evento.id}/?tab=avaliacao_trabalhos'
    mensagem, tag = evento.processar_resultados_finais(usuario=request.user)
    return httprr(url, mensagem, tag)


@rtr()
@login_required()
def listar_log_processamento_submissao(request, evento_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para visualizar o log de processamento de submissões neste evento.')
    title = 'Log de Processamento das Submissões'
    logs = LogProcessamentoSubmissao.objects.filter(evento=evento).order_by('id')
    return locals()


@rtr()
@login_required()
def remover_log_processamento_submissao(request, evento_id, log_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    log_processamento = get_object_or_404(LogProcessamentoSubmissao, pk=log_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para remover o log de processamento de submissões neste evento.')
    log_processamento.delete()
    return redirect(reverse('evento', args=(evento.pk,)) + '?tab=submissao_trabalhos')


@login_required()
@rtr()
def vincular_avaliadores_automaticamente(request, evento_id):
    """
    Vincula automaticamente submissões a avaliadores para um evento.

    Esta view distribui submissões de forma balanceada entre os avaliadores
    disponíveis, respeitando o limite de avaliadores por trabalho e o número
    máximo de trabalhos por avaliador, se configurado.
    """
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para realizar essa operação neste evento.')

    if not evento.configuracao:
        messages.error(request, 'O evento não possui configurações definidas.')
        return redirect(reverse('evento', args=(evento.pk,)) + '?tab=avaliacao_trabalhos')

    limite_avaliadores_por_trabalho = evento.configuracao.limite_avaliadores
    if limite_avaliadores_por_trabalho <= 0:
        messages.error(
            request,
            'O limite de avaliadores por trabalho deve ser maior que zero nas configurações do evento.',
        )
        return redirect(reverse('evento', args=(evento.pk,)) + '?tab=avaliacao_trabalhos')

    title = 'Vincular avaliadores automaticamente'
    if request.method == 'POST':
        # Submissões que ainda não atingiram o limite de avaliadores
        submissoes_nao_avaliadas = (
            Submissao.objects.filter(modalidade__evento=evento)
            .annotate(num_avaliadores=Count('versoes__pareceres', distinct=True))
            .filter(num_avaliadores__lt=limite_avaliadores_por_trabalho)
            .exclude(situacao='RDU')
        )

        if not submissoes_nao_avaliadas.exists():
            messages.info(request, 'Não há submissões pendentes de vinculação de avaliadores.')
            return redirect(reverse('evento', args=(evento.pk,)) + '?tab=avaliacao_trabalhos')

        avaliadores_disponiveis = AvaliadorModalidade.objects.filter(
            modalidade__evento=evento,
            avaliador__situacao_convite=SituacaoConvite.ACEITO,
        ).distinct()

        if not avaliadores_disponiveis.exists():
            messages.error(
                request,
                'Não há avaliadores disponíveis ou confirmados para este evento.',
            )
            return redirect(reverse('evento', args=(evento.pk,)) + '?tab=avaliacao_trabalhos')

        # Obter a contagem atual de trabalhos vinculados a cada avaliador
        # Obter a contagem atual de trabalhos vinculados para cada avaliador do evento
        avaliadores_com_contagem = defaultdict(int)
        avaliador_ids = avaliadores_disponiveis.values_list('id', flat=True)
        contagens = (
            AvaliacaoSubmissao.objects.filter(
                avaliador_modalidade_id__in=avaliador_ids,
                versao__submissao__modalidade__evento=evento,
            )
            .values('avaliador_modalidade_id')
            .annotate(quantidade=Count('id'))
        )
        for c in contagens:
            avaliadores_com_contagem[c['avaliador_modalidade_id']] = c['quantidade']
        # Garante que todos avaliadores tenham pelo menos 0
        for am_id in avaliador_ids:
            avaliadores_com_contagem.setdefault(am_id, 0)

        # Mapear avaliadores por modalidade e área temática para distribuição
        avaliadores_por_modalidade_area = defaultdict(list)
        for avaliador_modalidade in avaliadores_disponiveis:
            for area_tematica in avaliador_modalidade.areas_tematicas.all():
                key = (avaliador_modalidade.modalidade_id, area_tematica.id)
                avaliadores_por_modalidade_area[key].append(avaliador_modalidade)

        vinculos_criados = 0
        with transaction.atomic():
            for submissao in submissoes_nao_avaliadas:
                avaliadores_ja_vinculados_ids = list(
                    AvaliacaoSubmissao.objects.filter(versao__submissao=submissao).values_list('avaliador_modalidade__id', flat=True)
                )

                avaliadores_elegiveis = []
                key = (submissao.modalidade.id, submissao.area_tematica.id)
                if key in avaliadores_por_modalidade_area:
                    for avaliador_modalidade in avaliadores_por_modalidade_area[key]:
                        if avaliador_modalidade.id not in avaliadores_ja_vinculados_ids:
                            avaliadores_elegiveis.append(avaliador_modalidade)

                # Balanceamento com aleatoriedade em caso de empate
                avaliadores_elegiveis.sort(key=lambda am: avaliadores_com_contagem[am.id])
                avaliadores_para_vincular = []
                usados = set()
                while len(avaliadores_para_vincular) < limite_avaliadores_por_trabalho and avaliadores_elegiveis:
                    # Pega o menor número de trabalhos atribuídos
                    min_count = avaliadores_com_contagem[avaliadores_elegiveis[0].id]
                    empatados = [am for am in avaliadores_elegiveis if avaliadores_com_contagem[am.id] == min_count and am.id not in usados]
                    if not empatados:
                        break
                    random.shuffle(empatados)
                    for am in empatados:
                        if len(avaliadores_para_vincular) < limite_avaliadores_por_trabalho:
                            avaliadores_para_vincular.append(am)
                            usados.add(am.id)
                        else:
                            break
                    avaliadores_elegiveis = [am for am in avaliadores_elegiveis if am.id not in usados]

                # Se ainda não atingiu o limite, buscar avaliadores da mesma modalidade sem filtro de área temática
                if len(avaliadores_para_vincular) < limite_avaliadores_por_trabalho:
                    avaliadores_modalidade_geral = AvaliadorModalidade.objects.filter(
                        modalidade=submissao.modalidade,
                        avaliador__situacao_convite=SituacaoConvite.ACEITO,
                    ).exclude(id__in=[am.id for am in avaliadores_para_vincular] + avaliadores_ja_vinculados_ids)
                    avaliadores_modalidade_geral = list(avaliadores_modalidade_geral)
                    avaliadores_modalidade_geral.sort(key=lambda am: avaliadores_com_contagem[am.id])
                    usados_geral = set()
                    while len(avaliadores_para_vincular) < limite_avaliadores_por_trabalho and avaliadores_modalidade_geral:
                        min_count = avaliadores_com_contagem[avaliadores_modalidade_geral[0].id]
                        empatados = [
                            am for am in avaliadores_modalidade_geral if avaliadores_com_contagem[am.id] == min_count and am.id not in usados_geral
                        ]
                        if not empatados:
                            break
                        random.shuffle(empatados)
                        for am in empatados:
                            if len(avaliadores_para_vincular) < limite_avaliadores_por_trabalho:
                                avaliadores_para_vincular.append(am)
                                usados_geral.add(am.id)
                            else:
                                break
                        avaliadores_modalidade_geral = [am for am in avaliadores_modalidade_geral if am.id not in usados_geral]

                if not avaliadores_para_vincular and limite_avaliadores_por_trabalho > 0:
                    messages.warning(
                        request,
                        f'Não foi possível vincular avaliadores para a submissão "{submissao.titulo}". Verifique se há avaliadores disponíveis para a modalidade e área temática, ou se o limite de avaliadores por trabalho foi atingido.',
                    )
                    continue

                for avaliador_modalidade in avaliadores_para_vincular:
                    if not AvaliacaoSubmissao.objects.filter(
                        avaliador_modalidade=avaliador_modalidade,
                        versao=submissao.get_ultima_versao(),
                    ).exists():
                        AvaliacaoSubmissao.objects.create(
                            avaliador_modalidade=avaliador_modalidade,
                            versao=submissao.get_ultima_versao(),
                        )
                        avaliadores_com_contagem[avaliador_modalidade.id] += 1
                        vinculos_criados += 1

        if vinculos_criados > 0:
            messages.success(
                request,
                f'{vinculos_criados} vínculo(s) de avaliador(es) criado(s) com sucesso.',
            )
        else:
            messages.info(
                request,
                'Nenhum novo vínculo de avaliador foi criado. Todas as submissões já podem ter o número máximo de avaliadores ou não há mais avaliadores disponíveis.',
            )

        return redirect(reverse('evento', args=(evento.pk,)) + '?tab=avaliacao_trabalhos')

    return locals()


@rtr()
@login_required()
def desvincular_avaliadores_automaticamente(request, evento_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para realizar essa operação neste evento.')

    if not evento.configuracao:
        messages.error(request, 'O evento não possui configurações definidas.')
        return redirect(reverse('evento', args=(evento.pk,)) + '?tab=avaliacao_trabalhos')

    title = 'Desvincular avaliadores automaticamente'
    if request.method == 'POST':
        avaliacoes_removidas, _ = AvaliacaoSubmissao.objects.filter(
            versao__submissao__modalidade__evento=evento,
            itemavaliacao__isnull=True,
            nota__isnull=True,
        ).delete()

        if avaliacoes_removidas > 0:
            messages.success(
                request,
                f'{avaliacoes_removidas} vínculo(s) de avaliador(es) removido(s) com sucesso.',
            )
        else:
            messages.info(
                request,
                'Nenhum vínculo de avaliador foi removido. Todos os vínculos possuem pareceres vinculados.',
            )

        return redirect(reverse('evento', args=(evento.pk,)) + '?tab=avaliacao_trabalhos')

    return locals()


@rtr()
@login_required()
def migrar_tipo_participante(request, evento_id):
    evento = get_object_or_404(Evento, pk=evento_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para realizar essa operação neste evento.')
    title = 'Migrar tipo de participante'

    form = MigrarTipoParticipanteForm(request.POST or None, evento=evento)
    if form.is_valid():
        sucesso, erros, qtd_migrados = form.processar_migracao()
        if sucesso:
            messages.success(request, f'{qtd_migrados} participante(s) migrado(s) com sucesso!')
            tipo_destino = form.cleaned_data['tipo_destino']
            tab = slugify(tipo_destino.tipo_participacao.descricao) + str(tipo_destino.id)
            url = reverse('participantes', args=(evento.id,)) + f'?tab={tab}'
            return httprr(url, 'Migração realizada com sucesso!')
        else:
            for erro in erros:
                messages.error(request, erro)

    return locals()


@rtr()
@login_required()
def reenviar_credenciais_acesso(request, evento_id, tipo_participante_id, pks):
    evento = get_object_or_404(Evento, pk=evento_id)
    tipo_participante = get_object_or_404(TipoParticipante, pk=tipo_participante_id)
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para reenviar credenciais de acesso aos participantes deste evento.')
    pks = pks.split('_')
    participantes_selecionados = evento.participantes.filter(tipo=tipo_participante.id, pk__in=pks)

    tab = slugify(tipo_participante.tipo_participacao.descricao) + str(tipo_participante.id)
    url = reverse('participantes', args=(evento.id,)) + f'?tab={tab}'

    if not participantes_selecionados.exists():
        return httprr(
            url,
            'Nenhum participante selecionado para reenviar as credenciais de acesso.',
            'error',
        )

    for participante in participantes_selecionados:
        Notificar.credenciais_acesso(participante)

    messages.success(
        request,
        f'Credenciais de acesso reenviadas com sucesso para {participantes_selecionados.count()} participante(s).',
    )
    return redirect(url)


@rtr()
@login_required()
def analisar_duplicidades(request, evento_id):
    """
    View para analisar submissões duplicadas de um evento.
    Exibe TODAS as submissões similares, incluindo as removidas,
    permitindo ao coordenador ter visão completa do histórico.
    """
    evento = get_object_or_404(Evento, pk=evento_id)

    # Verifica permissão
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para analisar duplicidades deste evento.')

    title = f'Análise de Duplicidades: {evento.nome}'

    # Detecta duplicatas
    grupos_duplicados = evento.detectar_duplicatas()

    # Calcula estatísticas
    total_grupos = len(grupos_duplicados)
    total_submissoes_envolvidas = sum(len(grupo['submissoes']) for grupo in grupos_duplicados)
    total_removidas = sum(1 for grupo in grupos_duplicados for sub in grupo['submissoes'] if sub['removida'])
    total_ativas = total_submissoes_envolvidas - total_removidas

    return locals()


@rtr()
@login_required()
@transaction.atomic
def remover_duplicatas(request: HttpRequest, evento_id: int) -> HttpResponse:
    """
    View para remover submissões duplicadas selecionadas pelo coordenador.
    """
    evento = get_object_or_404(Evento, pk=evento_id)

    # Verifica permissão
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para remover duplicatas deste evento.')

    if request.method != 'POST':
        return httprr(
            f'/eventos/evento/{evento_id}/analisar_duplicidades/',
            'Método não permitido.',
            'error',
        )

    # Pega os IDs das submissões selecionadas
    submissoes_ids = request.POST.getlist('submissoes')
    motivo = request.POST.get('motivo', '').strip()
    # Requisições anteriores à opção de comunicação continuam notificando todos.
    comunicar_ids = set(request.POST.getlist('comunicar_submissoes')) if 'selecionar_comunicacao' in request.POST else set(submissoes_ids)

    if not submissoes_ids:
        return httprr(
            f'/eventos/evento/{evento_id}/analisar_duplicidades/',
            'Nenhuma submissão selecionada.',
            'error',
        )

    if not motivo:
        return httprr(
            f'/eventos/evento/{evento_id}/analisar_duplicidades/',
            'É necessário informar o motivo da remoção.',
            'error',
        )

    # Remove as submissões
    submissoes_removidas = []
    for submissao_id in submissoes_ids:
        try:
            submissao = Submissao.objects.get(pk=submissao_id, modalidade__evento=evento)
            situacao_anterior = submissao.get_situacao_display()

            submissao.situacao = SituacaoSubmissao.REMOVIDO_DUPLICIDADE
            submissao.motivo_remocao = motivo
            submissao.save(update_fields=['situacao', 'motivo_remocao'])

            # Notifica os autores
            if submissao_id in comunicar_ids:
                Notificar.trabalho_removido_duplicidade(submissao)

            # Registra no histórico do evento
            HistoricoEvento.objects.create(
                evento=evento,
                user=request.user,
                descricao=f'Removeu submissão "{submissao.titulo}" por duplicidade. Situação anterior: {situacao_anterior}. Motivo: {motivo}',
            )

            submissoes_removidas.append(submissao.titulo)
        except Submissao.DoesNotExist:
            continue

    if submissoes_removidas:
        messages.success(
            request,
            f'{len(submissoes_removidas)} submissão(ões) removida(s) por duplicidade: {", ".join(submissoes_removidas[:5])}'
            + ('...' if len(submissoes_removidas) > 5 else ''),
        )
    else:
        messages.warning(request, 'Nenhuma submissão foi removida.')

    return redirect(reverse('analisar_duplicidades', args=(evento.id,)))


@rtr()
@login_required()
@transaction.atomic
def restaurar_submissao(request, submissao_id):
    """
    View para restaurar uma submissão removida por duplicidade.
    """
    submissao = get_object_or_404(Submissao, pk=submissao_id)
    evento = submissao.modalidade.evento

    # Verifica permissão
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para restaurar submissões deste evento.')

    if not submissao.pode_restaurar():
        return httprr(
            f'/eventos/evento/{evento.id}/analisar_duplicidades/',
            'Esta submissão não pode ser restaurada.',
            'error',
        )

    # Restaura para situação submetida
    submissao.situacao = SituacaoSubmissao.SUBMETIDO
    submissao_motivo_backup = submissao.motivo_remocao
    submissao.motivo_remocao = None
    submissao.save(update_fields=['situacao', 'motivo_remocao'])

    # Registra no histórico
    HistoricoEvento.objects.create(
        evento=evento,
        user=request.user,
        descricao=f'Restaurou submissão "{submissao.titulo}" que havia sido removida por duplicidade. Motivo anterior: {submissao_motivo_backup}',
    )

    messages.success(request, f'Submissão "{submissao.titulo}" restaurada com sucesso.')
    return redirect(f'/eventos/evento/{evento.id}/analisar_duplicidades/')


@rtr('comparar_submissoes.html')
@login_required()
def comparar_submissoes(request, submissao1_id, submissao2_id):
    # @permission_required('eventos.pode_ver_avaliacoes_evento, eventos.pode_gerenciar_evento')
    """
    Compara duas submissões lado a lado, mostrando as diferenças nos títulos e conteúdos.
    Utiliza a biblioteca difflib nativa do Python para gerar comparações visuais.
    """
    submissao1 = get_object_or_404(Submissao, pk=submissao1_id)
    submissao2 = get_object_or_404(Submissao, pk=submissao2_id)
    title = 'Comparação de submissões'

    # Verifica permissão
    # if not request.user.has_perm('eventos.pode_gerenciar_evento'):
    #    raise PermissionDenied('Você não tem permissão para comparar submissões.')

    # Calcula similaridades
    similaridade_titulo = round(submissao1.calcular_similaridade_titulo(submissao2) * 100, 2)
    similaridade_conteudo = round(submissao1.calcular_similaridade_conteudo(submissao2) * 100, 2)

    # Prepara diff dos conteúdos
    conteudo1 = submissao1.conteudo_extraido or '(Conteúdo não extraído)'
    conteudo2 = submissao2.conteudo_extraido or '(Conteúdo não extraído)'
    conteudo_diff = text_similarity.gerar_diff_lado_a_lado(conteudo1, conteudo2)

    # DEBUG: Imprime uma amostra do diff gerado
    logger = logging.getLogger(__name__)
    if conteudo_diff and 'original' in conteudo_diff:
        sample = str(conteudo_diff['original'])[:500]
        logger.info(f'[DEBUG DIFF] Amostra do diff original gerado: {sample}')

    return locals()


@rtr()
@login_required()
def exibir_log_processamento_extracao(request, submissao_id):
    submissao = get_object_or_404(Submissao, pk=submissao_id)
    evento = submissao.modalidade.evento

    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para ver logs desta submissão.')

    title = 'Log de Processamento de Extração'
    logs = submissao.processamento_extracao if isinstance(submissao.processamento_extracao, list) else []

    return locals()


@rtr()
@login_required()
def listar_log_processamento_extracao(request, evento_id):
    evento = get_object_or_404(Evento, pk=evento_id)

    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para ver logs deste evento.')

    title = 'Log do processamento das extrações de submissões'

    # Busca todas as submissões do evento que possuem resultado de extração não vazio
    submissoes = (
        Submissao.objects.filter(modalidade__evento=evento)
        .exclude(processamento_extracao__isnull=True)
        .values('id', 'titulo', 'processamento_extracao')
    )

    # Filtra e transforma em lista para template
    erros = []
    for s in submissoes:
        proc_list = s.get('processamento_extracao') or []
        # Se for lista, pega o último log; caso contrário, trata como dict antigo
        if isinstance(proc_list, list) and proc_list:
            proc = proc_list[-1]
        elif isinstance(proc_list, dict):
            proc = proc_list
        else:
            proc = {}

        status = proc.get('status')
        if status and status != 'success':
            erros.append({'id': s['id'], 'titulo': s['titulo'], 'processamento': proc})

    return locals()


@rtr()
@login_required()
def buscar_participantes_evento(request, evento_id):
    """
    View para exibir formulário de busca de participantes de um evento por nome ou CPF.
    Exibe lista de participantes encontrados com opções para confirmar/cancelar presença.
    """
    evento = get_object_or_404(Evento, pk=evento_id)

    # Verificar permissão
    if not (evento.pode_gerenciar(request.user) or evento.pode_confirmar_presenca(request.user)):
        raise PermissionDenied('Você não tem permissão para gerenciar este evento.')

    title = 'Consultar participantes'
    participantes_encontrados = None
    query = request.GET.get('q', '').strip()

    if query:
        # Buscar por nome (qualquer parte) ou CPF (formatado ou não)
        participantes = evento.participantes.all()

        # Limpar o CPF de formatação para busca
        cpf_limpo = query.replace('.', '').replace('-', '')

        # Buscar por nome ou CPF
        participantes_nome = participantes.filter(nome__unaccent__icontains=query)
        participantes_cpf = participantes.filter(Q(cpf__contains=query) | Q(cpf__contains=cpf_limpo))

        participantes_encontrados = (
            (participantes_nome | participantes_cpf).distinct().select_related('tipo', 'publico_alvo', 'vinculo', 'vinculo__user').order_by('nome')
        )

    context = {
        'evento': evento,
        'title': title,
        'participantes_encontrados': participantes_encontrados,
        'query': query,
    }
    return render(request, 'eventos/templates/buscar_participantes_evento.html', context)


@login_required()
def processar_presenca_participantes(request):
    """
    Processa a ação de confirmação ou cancelamento de presença
    dos participantes selecionados no formulário de busca.
    """
    if request.method != 'POST':
        # A ação é POST; sem ``evento_id`` não há como reverter ``buscar_participantes_evento``
        # (a rota exige o argumento) e o ``redirect`` sem args estourava ``NoReverseMatch`` (500).
        return redirect('area_publica')

    evento_id = request.POST.get('evento_id')
    acao = request.POST.get('acao')
    pks = request.POST.getlist('ids')

    if not evento_id or not pks:
        messages.error(request, 'Nenhum participante selecionado ou evento não especificado.')
        if evento_id:
            return redirect('buscar_participantes_evento', evento_id=evento_id)
        # Redirecionar para a área pública de eventos ao invés de um evento específico
        return redirect('area_publica')

    evento = get_object_or_404(Evento, pk=evento_id)

    # Verificar permissão
    if not (evento.pode_gerenciar(request.user) or evento.pode_confirmar_presenca(request.user)):
        raise PermissionDenied('Você não tem permissão para gerenciar este evento.')

    participantes = evento.participantes.filter(pk__in=pks, inscricao_validada=True)

    if acao == 'confirmar_presenca':
        qtd_presencas = participantes.update(presenca_confirmada=True)
        msg = f'{qtd_presencas} presença(s) confirmada(s) com sucesso.'
    elif acao == 'cancelar_presenca':
        qtd_presencas = participantes.update(presenca_confirmada=False)
        msg = f'{qtd_presencas} presença(s) cancelada(s) com sucesso.'
    else:
        messages.error(request, 'Ação inválida.')
        return redirect('buscar_participantes_evento', evento_id=evento_id)

    # Registrar CH de extensão para participantes com vínculo
    for participante in participantes.filter(vinculo__isnull=False):
        participante.registrar_ch_extensao()

    messages.success(request, msg)

    # Redirecionar de volta para a consulta com os parâmetros da busca
    query = request.POST.get('query', '')
    return redirect(f'{reverse("buscar_participantes_evento", args=[evento_id])}?q={query}')


def _filtrar_trabalhos(submissoes: models.QuerySet, dados: dict) -> models.QuerySet:
    codigo = dados.get('codigo')
    if codigo:
        return submissoes.filter(id=codigo) if codigo.isdigit() else submissoes.filter(titulo__icontains=codigo)
    filtros = {campo: dados[campo] for campo in ('modalidade', 'area_tematica', 'situacao') if dados.get(campo)}
    resultado = dados.get('resultado_avaliacao')
    if resultado == 'SA':
        filtros['resultado_listagem__isnull'] = True
    elif resultado:
        filtros['resultado_listagem'] = resultado
    return submissoes.filter(**filtros)


def _cards_trabalhos(totais: dict, selecionado: str, divulgar_resultado: bool) -> list[dict]:
    categorias = [
        ('', 'Trabalhos ativos', 'total', 'info'),
        ('SA', 'Sem avaliação', 'sem_avaliacao', 'info'),
        ('PE', 'Avaliação pendente', 'pendentes', 'warning'),
    ]
    if divulgar_resultado:
        categorias.extend([('AP', 'Aprovados', 'aprovadas', 'success'), ('RE', 'Reprovados', 'reprovadas', 'error')])
    return [
        {
            'titulo': titulo,
            'total': totais[chave],
            'url': f'?resultado_avaliacao={codigo}' if codigo else '?',
            'selecionado': selecionado == codigo,
            'classe': classe,
        }
        for codigo, titulo, chave, classe in categorias
    ]


@rtr('eventos/templates/listar_trabalhos.html')
@login_required()
def listar_trabalhos(request: HttpRequest, evento_id: int) -> dict:
    evento = get_object_or_404(Evento, pk=evento_id)
    pode_gerenciar = evento.pode_gerenciar(request.user)
    if not pode_gerenciar:
        raise PermissionDenied('Você não tem permissão para visualizar os trabalhos deste evento.')

    title = 'Trabalhos do Evento'
    modalidades = Modalidade.objects.filter(evento=evento)
    tem_modalidades = modalidades.exists()

    # Áreas temáticas da modalidade
    areas_tematicas_modalidade = AreaTematicaModalidade.objects.filter(modalidade__evento=evento).order_by(
        'modalidade__tipo', 'area_tematica__titulo'
    )

    ultima_versao = VersaoSubmissao.objects.filter(submissao_id=OuterRef('pk')).order_by('-numero').values('pk')[:1]
    pareceres_pendentes = AvaliacaoSubmissao.objects.filter(versao_id=OuterRef('ultima_versao_id'), nota__isnull=True)
    submissoes = (
        Submissao.objects.filter(modalidade__evento=evento)
        .exclude(situacao=SituacaoSubmissao.REMOVIDO_DUPLICIDADE)
        .annotate(ultima_versao_id=Subquery(ultima_versao))
        .annotate(tem_avaliacao_pendente=Exists(pareceres_pendentes))
        .annotate(
            resultado_listagem=Case(
                When(tem_avaliacao_pendente=True, then=Value(ResultadoAvaliacao.PENDENTE)),
                default=F('resultado_avaliacao'),
                output_field=CharField(),
            )
        )
        .order_by('modalidade__tipo__titulo', 'area_tematica__titulo', 'id')
    )
    totais = submissoes.aggregate(
        total=Count('pk'),
        sem_avaliacao=Count('pk', filter=Q(resultado_listagem__isnull=True)),
        pendentes=Count('pk', filter=Q(resultado_listagem=ResultadoAvaliacao.PENDENTE)),
        aprovadas=Count('pk', filter=Q(resultado_listagem=ResultadoAvaliacao.APROVADO)),
        reprovadas=Count('pk', filter=Q(resultado_listagem=ResultadoAvaliacao.REPROVADO)),
    )
    total_submissoes = totais['total']
    divulgar_resultado = evento.pode_divulgar_resultado_final()
    dados_filtro = request.POST if request.method == 'POST' else request.GET
    filtroSubmissaoForm = FiltroSubmissaoForm(dados_filtro or None, evento=evento)
    filtro_selecionado = ''
    if filtroSubmissaoForm.is_valid():
        submissoes = _filtrar_trabalhos(submissoes, filtroSubmissaoForm.cleaned_data)
        filtro_selecionado = filtroSubmissaoForm.cleaned_data.get('resultado_avaliacao', '')
    cards = _cards_trabalhos(totais, filtro_selecionado, divulgar_resultado)
    total_filtrado = submissoes.count()

    submissoes = submissoes.select_related('modalidade', 'modalidade__tipo', 'area_tematica').prefetch_related(
        'modalidade',
        Prefetch('versoes__pareceres', queryset=AvaliacaoSubmissao.objects.select_related('avaliador_modalidade__avaliador')),
    )

    return locals()


@rtr()
@login_required()
def visualizar_trabalho(request: HttpRequest, submissao_id: int) -> dict:
    submissao = get_object_or_404(Submissao, pk=submissao_id)
    evento = submissao.modalidade.evento
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para visualizar os trabalhos deste evento.')

    title = f'Trabalho #{submissao.pk}'
    return locals()


@rtr()
@login_required()
def listar_trabalhos_resumido(request: HttpRequest, area_tematica_modalidade_id: int) -> dict:
    area_tematica_modalidade = get_object_or_404(
        AreaTematicaModalidade.objects.select_related('modalidade__evento', 'modalidade__tipo', 'area_tematica'),
        pk=area_tematica_modalidade_id,
        modalidade__tipo_submissao=TipoSubmissao.TIPO_SUBMISSAO_TEXTO,
    )
    evento = area_tematica_modalidade.modalidade.evento
    if not evento.pode_gerenciar(request.user):
        raise PermissionDenied('Você não tem permissão para visualizar os trabalhos deste evento.')

    title = f'Trabalhos aprovados: {area_tematica_modalidade}'
    submissoes = (
        Submissao.objects.filter(
            modalidade=area_tematica_modalidade.modalidade,
            area_tematica=area_tematica_modalidade.area_tematica,
            resultado_avaliacao=ResultadoAvaliacao.APROVADO,
        )
        .prefetch_related('autores_relacionados__participante')
        .order_by('titulo', 'id')
    )
    return locals()
