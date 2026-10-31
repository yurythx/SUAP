import base64
import calendar
import codecs
import collections
import csv
import hashlib
import json
import operator
import os
import pickle
import socket
import subprocess
import tempfile
import time
import urllib.parse
import zipfile
from builtins import sorted
from collections import OrderedDict
from contextlib import suppress
from datetime import date, datetime, timedelta
from functools import reduce
from os.path import exists
from typing import Any
from xml.etree import ElementTree

import yaml
from django.apps import apps
from django.apps import apps as apps_django
from django.conf import settings
from django.contrib import messages
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.admin.options import get_content_type_for_model
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.contrib.auth.views import LoginView
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.core.files.storage import default_storage
from django.db import connection, transaction
from django.db.models import Count, Exists, OuterRef, Q, QuerySet, Subquery
from django.db.models.expressions import Case, F, Value, When
from django.db.models.fields import BooleanField
from django.db.models.functions import Coalesce
from django.http import (
    FileResponse,
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
    HttpResponseNotFound,
    HttpResponseRedirect,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.template import Context, Engine, TemplateDoesNotExist, loader
from django.template.defaultfilters import pluralize
from django.template.loader import get_template, render_to_string
from django.urls import reverse_lazy
from django.utils.encoding import force_str
from django.utils.html import strip_spaces_between_tags as minify_html
from django.utils.safestring import mark_safe
from django.utils.text import slugify
from django.views.decorators.csrf import csrf_exempt, requires_csrf_token
from django.views.decorators.http import require_POST
from django.views.defaults import ERROR_PAGE_TEMPLATE
from django.views.static import serve
from sentry_sdk import capture_exception, last_event_id

from comum import signer
from comum.services.icp_edu import ApiICPEDUService
from comum.exceptions import LoginException, UserMustResetPassword
from comum.forms import (
    AdicionarUsuarioGrupoFormFactory,
    AlterarSenhaForm,
    AssinarDocumentoForm,
    AssinarDocumentoICPEduForm,
    AtualizarEmailForm,
    AtualizarFotoPessoaFisicaForm,
    AutenticacaoDoisFatoresForm,
    AutenticarDocumentoForm,
    AuthenticationFormPlus,
    CadastrarAtalhoForm,
    CalendarioForm,
    CancelarReservasPeriodoForm,
    ComentarioForm,
    ConfiguracaoAutomatizacaoGrupoForm,
    ConfiguracaoFormFactory,
    ConfirmarComSenhaForm,
    ContatoEmergenciaForm,
    DeferirDiarioReservaSalaPeriodo,
    DeviceForm,
    EncerrarOcupacaoPrestadorForm,
    ExcluirRegistroForm,
    ExibirQuadrosForm,
    ExtracaoForm,
    FiltrarPorPeriodoForm,
    IndisponibilizacaoSalaBuscarForm,
    InscricaoFiscalForm,
    MacroForm,
    MacroHistoricoPCAForm,
    OcupacaoPrestadorForm,
    RegistrarIndisponibilizacaoSalaForm,
    RejeitarSolicitacaoForm,
    RelatorioSalasDisponiveisForm,
    ReservaInformarOcorrenciaForm,
    ReservaSalaCancelarForm,
    ReuniaoOrgaoColegiadoConsultarForm,
    SalaIndicadoresForm,
    SetorAdicionarTelefoneForm,
    SetorEditarEmailForm,
    SolicitacaoReservaSalaAvaliarForm,
    SolicitacaoReservaSalaCancelarForm,
    SolicitacaoReservaSalaForm,
    SoliticarTrocarSenhaForm,
    TrocarSenhaForm,
    ValidarDocumentoForm,
    VerificarDocumentoForm,
    VincularSetorUsuarioGrupoFormFactory,
)
from comum.html import CalendarioReuniaoOrgaoColegiadoHTML, ReuniaoOrgaoColegiadoView
from comum.models import (
    Ano,
    APIExterna,
    AutenticacaoDoisFatores,
    CategoriaNotificacao,
    Comentario,
    Configuracao,
    ConfiguracaoAutomatizacaoGrupo,
    ContatoEmergencia,
    Device,
    DocumentoControle,
    DocumentoControleHistorico,
    DocumentoControleTipo,
    GerenciamentoGrupo,
    GroupDetail,
    HistoricoUsuarioGrupo,
    IndexLayout,
    IndisponibilizacaoSala,
    InscricaoFiscal,
    ManutencaoProgramada,
    OcupacaoPrestador,
    Pensionista,
    Predio,
    Preferencia,
    PreferenciaNotificacao,
    PrestadorServico,
    Publico,
    RegistroEmissaoDocumento,
    RegistroNotificacao,
    ReservaSala,
    ReuniaoOrgaoColegiado,
    Sala,
    SessionInfo,
    SetorTelefone,
    SolicitacaoReservaSala,
    SubobjetivoDesenvolvimentoSustentavel,
    TrocarSenha,
    User,
    UsuarioGrupo,
    UsuarioGrupoSetor,
    Vinculo,
)
from comum.utils import (
    FLAG_LOG_GERENCIAMENTO_GRUPO,
    get_rss_links,
    get_temas,
    get_uo,
    remote_logout_user,
    tem_permissao_informar_erro,
)
from djtools import documentos, layout
from djtools.html.calendarios import Calendario, CalendarioMix
from djtools.layout import get_quadro_by_name
from djtools.management.permission import GroupPermission
from djtools.middleware.govbr import destino_pos_autenticacao
from djtools.storages import get_temp_storage
from djtools.templatetags.filters import format_
from djtools.utils import (
    CsvResponse,
    JsonResponse,
    PDFResponse,
    decrypt,
    encrypt,
    gera_nomes,
    get_client_ip,
    get_ldap_conf,
    get_real_sql,
    get_remote_session,
    get_session_cache,
    get_view_name_from_url,
    group_required,
    httprr,
    ids_da_query,
    is_ldap_enabled,
    mask_cpf,
    permission_required,
    rtr,
    running_tests,
    somar_dias,
    sync_ldap_user,
)
from rh.deduplicacao.entrada import filtro_mesma_pessoa_por_passaporte
from rh.models import BiometriaSolicitacao, PessoaFisica, Servidor, Setor, Situacao, UnidadeOrganizacional
from suap import nomenclatura

URL_AZURE = 'https://portal.azure.com/#home'


@layout.servicos_anonimos()
def servicos_anonimos(request):
    servicos_anonimos = []

    servicos_anonimos.append({'categoria': 'Sobre o Suap', 'url': '/comum/documentacao/', 'icone': 'question-circle', 'titulo': 'Documentação'})
    servicos_anonimos.append({'categoria': 'Sobre o Suap', 'url': '/comum/design_system/', 'icone': 'code', 'titulo': 'Design System'})
    servicos_anonimos.append({'categoria': 'Acessos', 'url': '/accounts/login/', 'icone': 'lock', 'titulo': 'Login'})
    servicos_anonimos.append({'categoria': 'Acessos', 'url': '/comum/solicitar_trocar_senha/', 'icone': 'key', 'titulo': 'Alterar senha'})

    return servicos_anonimos


@layout.inscricao()
def index_inscricoes(request):
    inscricoes = []
    hoje = datetime.now()
    manutencoes = ManutencaoProgramada.proximas_notificacoes(request.user)
    for manutencao in manutencoes:
        previsao_horario_fim_manutencao = manutencao.data_hora_atualizacao + timedelta(minutes=manutencao.previsao_minutos_inatividade)

        if manutencao.data_hora_atualizacao.date() == hoje.date():
            if previsao_horario_fim_manutencao.date() == hoje.date():
                periodo = (
                    f'Hoje das {manutencao.data_hora_atualizacao.strftime("%H:%M:%S")} às {previsao_horario_fim_manutencao.strftime("%H:%M:%S")}'
                )
            else:
                periodo = f'Hoje das {manutencao.data_hora_atualizacao.strftime("%H:%M:%S")} até {previsao_horario_fim_manutencao.date().strftime("%d/%m/%Y")} às {previsao_horario_fim_manutencao.strftime("%H:%M:%S")}'
        else:
            if manutencao.data_hora_atualizacao.date() == previsao_horario_fim_manutencao.date():
                periodo = f'Em {manutencao.data_hora_atualizacao.strftime("%d/%m/%Y")} das {manutencao.data_hora_atualizacao.strftime("%H:%M:%S")} às {previsao_horario_fim_manutencao.strftime("%H:%M:%S")}'
            else:
                periodo = f'Das {manutencao.data_hora_atualizacao.strftime("%H:%M:%S")} de {manutencao.data_hora_atualizacao.strftime("%d/%m/%Y")} até às {previsao_horario_fim_manutencao.strftime("%H:%M:%S")} de {previsao_horario_fim_manutencao.date().strftime("%d/%m/%Y")}'
        inscricoes.append(
            {
                'url': manutencao.get_absolute_url(),
                'titulo': f'<strong>Manutenção programada</strong>: {manutencao.get_tipo_display().lower()} agendado(a) para <strong>{manutencao.sistema_ou_servico}</strong>.',
                'extra': periodo,
            }
        )
    return inscricoes


@layout.atribuidos_a_mim()
def index_atribuidos_a_mim(request):
    pendencias = []
    if request.user.has_perm('comum.pode_avaliar_solicitacao_reserva_de_sala'):
        solicitacoes_pendentes = request.user.salas_avaliadas.filter(
            solicitacaoreservasala__status=SolicitacaoReservaSala.STATUS_AGUARDANDO_AVALIACAO
        ).count()
        if solicitacoes_pendentes:
            pendencias.append(
                {
                    'titulo': f'Solicitaç{pluralize(solicitacoes_pendentes, "ão,ões")} de Reserva de Salas',
                    'subtitulo': 'aguardando avaliação',
                    'qtd': solicitacoes_pendentes,
                    'url': '/admin/comum/solicitacaoreservasala/?tab=tab_solicitacoes_a_avaliar',
                }
            )

    return pendencias


@layout.quadro('Atalhos', icone='link', pode_esconder=True)
def index_quadros_atalhos(quadro, request):
    itens = []
    for nome, url in request.user.atalho_set.values_list('nome', 'url'):
        itens.append(layout.ItemAcessoRapido(titulo=nome, url=url))
    if itens:
        itens.append(layout.ItemAcessoRapido(titulo='Gerenciar atalhos', url='/admin/comum/atalho/', classe='primary', icone='edit'))
    quadro.add_itens(itens)
    return quadro


@layout.quadro('Minha conta', icone='user', pode_esconder=True, global_cache=8 * 3600)
def index_quadros_minha_conta(quadro, request):
    quadro.add_itens(
        [
            layout.ItemVideo(
                titulo='Você sabia?',
                youtube_id='i3l_zU4jooc',
                layout='vertical',
                descricao='Na página Minha conta, você pode atualizar e controlar todas as suas informações de usuário em poucos cliques?',
                botao='Acessar Minha conta',
                url='/comum/minha_conta/',
            )
        ]
    )
    return quadro


@layout.quadro('E-mail do setor', icone='user', pode_esconder=True, session_cache=8 * 3600)
def index_quadros_email_do_setor(quadro: layout.Quadro, request: HttpRequest) -> layout.Quadro:
    usuario = request.user
    relacionamento = usuario.get_relacionamento()
    if usuario.eh_servidor and relacionamento and usuario.has_group_cached(['Servidor', 'Chefe de Setor']):
        setores_chefia = relacionamento.setores_que_eh_chefe_hoje
        setores_sem_email = setores_chefia.filter(Q(email__isnull=True) | Q(email=''))
        setor_pendente = setores_sem_email.first()
        if setor_pendente:
            quadro.add_itens(
                [
                    layout.ItemVideo(
                        titulo='Você sabia?',
                        youtube_id='KshHCvfl9ws',
                        layout='vertical',
                        descricao='Chefe de setor, é possível cadastrar o e-mail institucional do seu setor aqui no Suap.',
                        botao=f'Informar e-mail para {setor_pendente}',
                        url=f'/comum/setor_editar_email/{setor_pendente.pk}',
                    )
                ]
            )
    return quadro


@layout.quadro('Notícias', icone='rss', pode_esconder=True, global_cache=8 * 3600)
def index_quadros_rss(quadro, request):
    url_rss = Configuracao.get_valor_por_chave('comum', 'url_rss')
    if url_rss:
        try:
            rss_links = get_rss_links(url_rss)
            for rss in rss_links:
                quadro.add_itens(
                    [
                        layout.ItemNoticia(
                            titulo=rss['title'],
                            chapeu=rss['updated'],
                            url=rss['url'],
                        )
                    ]
                )
        except Exception:
            quadro.add_itens(
                [
                    layout.ItemNoticia(
                        titulo='Erro ao carregar notícias',
                        chapeu='',
                        url='#',
                    )
                ]
            )
    return quadro


@layout.quadro('Calendário Administrativo', icone='calendar-alt', pode_esconder=True, session_cache=3600)
def index_quadros_calendario(quadro, request):
    """Preenche o quadro com calendário mensal de eventos do servidor.

    Args:
        quadro: objeto de layout do quadro onde os itens serão adicionados.
        request: requisição HTTP usada para obter o usuário e seus relacionamentos.

    Returns:
        quadro preenchido com os itens de calendário mensal e legendas de eventos.
    """
    hoje = datetime.now()
    relacionamento = request.user.get_relacionamento()
    # o vínculo do login decide, não a pessoa: deduplicada, a mesma pessoa pode ser servidor e aluno
    eh_servidor = request.user.eh_servidor
    if (eh_servidor or request.user.eh_prestador) and relacionamento and relacionamento.setor:
        ano = hoje.year
        mes = hoje.month
        primeiro_dia = date(ano, mes, 1)
        ultimo_dia = date(ano, mes, 1)
        while ultimo_dia.month == primeiro_dia.month:
            ultimo_dia = ultimo_dia + timedelta(days=1)
        ultimo_dia = ultimo_dia - timedelta(days=1)
        cal = Calendario()
        codigos_lc = []
        if 'ponto' in settings.INSTALLED_APPS:
            from ponto.models import Liberacao

            for liberacao in Liberacao.get_liberacoes_calendario(relacionamento.setor.uo, ano, mes):
                if (liberacao.data_inicio.month == mes and liberacao.data_inicio.year == ano) or (
                    liberacao.data_fim.month == mes and liberacao.data_fim.year == ano
                ):
                    cal.adicionar_evento_calendario(
                        liberacao.data_inicio, liberacao.data_fim, liberacao.descricao, liberacao.get_liberacao_css(), liberacao.descricao
                    )

        if 'licenca_capacitacao' in settings.INSTALLED_APPS and eh_servidor:
            from licenca_capacitacao.models import EditalLicCapacitacao, PeriodoPedidoLicCapacitacao

            codigos_lc = EditalLicCapacitacao.get_todos_os_codigos_licenca_capacitacao()
            licencas_servidores = PeriodoPedidoLicCapacitacao.objects.filter(
                pedido__servidor=request.user.get_relacionamento(),
                pedido__aprovado_em_definitivo=True,
                pedido__cancelado_pela_gestao=False,
            )
            licencas_servidores = licencas_servidores.exclude(data_inicio__gt=ultimo_dia).exclude(data_termino__lt=primeiro_dia)
            for licenca in licencas_servidores:
                cal.adicionar_evento_calendario(
                    licenca.data_inicio,
                    licenca.data_termino,
                    'Licença Capacitação',
                    'afastamento',
                )

        if 'ferias' in settings.INSTALLED_APPS and eh_servidor:
            # Preenche calendario se tiver férias no mês, mesmo que o período de férias comece antes ou termine depois do mês
            from ferias.models import Ferias

            data_ini = date(ano, mes, 1)
            data_fim = date(ano, mes, calendar.monthrange(ano, mes)[1])
            periodos = Ferias.get_periodos_pessoa_estava_de_ferias(relacionamento, data_ini, data_fim)
            [cal.adicionar_evento_calendario(periodo_ini, periodo_fim, label, 'ferias', label) for periodo_ini, periodo_fim, label in periodos]

        if (
            'rh' in settings.INSTALLED_APPS
            and eh_servidor
            and request.user.has_group_cached(
                ('Servidor', 'Coordenador de Gestão de Pessoas', 'Coordenador de Gestão de Pessoas Sistêmico', 'Operador de Gestão de Pessoas')
            )
        ):
            from rh.models import CronogramaFolha, ServidorAfastamento

            afastamentos_servidores = ServidorAfastamento.objects.filter(servidor=request.user.get_relacionamento(), cancelado=False).exclude(
                afastamento__codigo__in=codigos_lc
            )

            afastamentos_servidores = afastamentos_servidores.exclude(data_inicio__gt=ultimo_dia).exclude(data_termino__lt=primeiro_dia)

            for afastamento in afastamentos_servidores:
                cal.adicionar_evento_calendario(
                    afastamento.data_inicio,
                    afastamento.data_termino,
                    afastamento.afastamento.nome,
                    'afastamento',
                )

            cronogramafolha = CronogramaFolha.objects.filter(mes=mes, ano__ano=ano).first()
            if cronogramafolha:
                cal.adicionar_evento_calendario(
                    cronogramafolha.data_consulta_previa_folha,
                    cronogramafolha.data_consulta_previa_folha,
                    'Consulta da Prévia da Folha',
                    'extra5',
                    'Data da consulta da Prévia da Folha',
                )
                cal.adicionar_evento_calendario(
                    cronogramafolha.data_fechamento_processamento_folha,
                    cronogramafolha.data_fechamento_processamento_folha,
                    'Fechamento do SIAPE para Processamento da Folha',
                    'extra5',
                    'Data do fechamento do SIAPE para Processamento da Folha',
                )
                cal.adicionar_evento_calendario(
                    cronogramafolha.data_abertura_atualizacao_folha,
                    cronogramafolha.data_abertura_atualizacao_folha,
                    'Abertura do SIAPE para Atualização da Folha',
                    'extra5',
                    'Data da abertura do SIAPE para Atualização da Folha',
                )
                cal.adicionar_evento_calendario(
                    cronogramafolha.data_abertura_proxima_folha,
                    cronogramafolha.data_abertura_proxima_folha,
                    'Abertura da Próxima Folha',
                    'extra5',
                    'Abertura da Próxima Folha',
                )

        quadro.add_itens(
            [
                layout.ItemCalendario(calendario=cal.formato_mes(ano, mes), legenda=cal.legenda_tipos_eventos()),
                layout.ItemAcessoRapido(titulo='Calendário Anual', url='/comum/calendario_administrativo/'),
            ]
        )

    return quadro


@layout.quadro('Calendário de Reuniões de Órgãos Colegiados Superiores', icone='calendar-alt', pode_esconder=True, session_cache=3600)
def index_quadros_calendario_orgaos_colegiados(quadro, request):
    if request.user.has_perm('comum.pode_consultar_calendarios'):
        hoje = datetime.now()
        ano = hoje.year
        mes = hoje.month
        mes_primeiro_dia = date(ano, mes, 1)
        mes_ultimo_dia = date(ano, mes, calendar.monthrange(ano, mes)[1])
        calendario_dados = ReuniaoOrgaoColegiado.obter_calendario_reuniao_orgao_colegiado(data_inicio=mes_primeiro_dia, data_fim=mes_ultimo_dia)
        calendario_html = CalendarioReuniaoOrgaoColegiadoHTML(
            calendario_dados, formato=CalendarioMix.FORMATO_ANUAL, legenda=CalendarioMix.LEGENDA_NO_FINAL
        )
        quadro.add_itens(
            [
                layout.ItemCalendario(calendario=calendario_html),
                layout.ItemAcessoRapido(
                    titulo='Consultar Calendários',
                    url=f'/comum/orgaos_colegiados_reunioes_consultar_calendario/?mes={mes}&ano={ano}&formato=mensal',
                ),
            ]
        )

        if request.user.has_perm('comum.add_reuniaoorgaocolegiado'):
            quadro.add_itens(
                [layout.ItemAcessoRapido(titulo='Cadastrar Reunião', url='/admin/comum/reuniaoorgaocolegiado/add', icone='plus', classe='success')]
            )

    return quadro


@layout.quick_access()
def index_quick_access(request):
    usuario_logado = request.user
    if not request.user or not request.user.is_authenticated:
        return []

    quick_access = []
    relacionamento = usuario_logado.get_relacionamento()

    if usuario_logado.eh_servidor:
        if 'webmail' in settings.ADMIN_QUICK_ACCESS:
            quick_access.append({'titulo': 'Webmail', 'icone': 'envelope', 'url': Configuracao.get_valor_por_chave('comum', 'url_webmail')})

        if 'groups' in settings.ADMIN_QUICK_ACCESS and GerenciamentoGrupo.user_can_manage(usuario_logado):
            quick_access.append({'titulo': 'Gerenciamento de grupos', 'icone': 'users', 'url': '/comum/gerenciamento_grupo/'})

        if 'microsoft_azure' in settings.ADMIN_QUICK_ACCESS and relacionamento.tem_acesso_servicos_microsoft():
            quick_access.append({'titulo': 'Microsoft Azure', 'icone': 'windows fab', 'url': URL_AZURE})

    if 'google_classroom' in settings.ADMIN_QUICK_ACCESS and is_ldap_enabled():
        if (hasattr(relacionamento, 'email_google_classroom') and relacionamento.email_google_classroom) or usuario_logado.has_group_cached(
            'Usuários do Google Classroom'
        ):
            quick_access.append({'titulo': 'Google Sala de Aula', 'icone': 'google fab', 'url': '/ldap_backend/redirecionar_google_classroom/'})

    if 'phones' in settings.ADMIN_QUICK_ACCESS:
        quick_access.append({'titulo': 'Telefones', 'url': '/comum/telefones/', 'icone': 'phone'})

    if 'scdp_siape' in settings.ADMIN_QUICK_ACCESS:
        if usuario_logado.has_perm('rh.pode_gerenciar_extracao_scdp') or usuario_logado.has_perm('rh.pode_gerenciar_extracao_siape'):
            quick_access.append({'titulo': 'Configurações', 'icone': 'cog', 'url': '/comum/admin/'})
    if usuario_logado.is_configurador() and not usuario_logado.is_superuser:
        quick_access.append({'titulo': 'Configurações', 'icone': 'cog', 'url': '/comum/configuracao/'})

    if 'mobile' in settings.ADMIN_QUICK_ACCESS:
        quick_access.append(
            {'titulo': 'SUAP Mobile (Android)', 'url': 'https://play.google.com/store/apps/details?id=br.edu.ifrn.suap.mobile', 'icone': 'mobile'}
        )

    return quick_access


@layout.quadro('Manuais', icone='book', pode_esconder=True, session_cache=24 * 3600)
def index_quadros_manuais(quadro, request):
    if bool(Configuracao.get_valor_por_chave('comum', 'quadro_manuais')) is True:
        if request.user.get_vinculo().eh_funcionario():
            if request.user.has_perm('ae.view_demandaalunoatendida'):
                quadro.add_item(
                    layout.ItemAcessoRapido(
                        titulo='Atividades Estudantis: <strong>Serviço Social</strong>', url='/manuais/ae/servico_social/index.html'
                    )
                )

            if request.user.has_group_cached('Coordenador de Atividades Estudantis'):
                quadro.add_item(
                    layout.ItemAcessoRapido(titulo='Atividades Estudantis: <strong>Coordenação</strong>', url='/manuais/ae/coordenacao/index.html')
                )

            if 'pdi' in settings.INSTALLED_APPS:
                quadro.add_item(
                    layout.ItemAcessoRapido(
                        titulo='Desenvolvimento Institucional: <strong>PDI</strong>', url='/manuais/des_institucional/pdi/index.html'
                    )
                )

            if request.user.has_group_cached('Servidor'):
                if 'projetos' in settings.INSTALLED_APPS:
                    quadro.add_item(
                        layout.ItemAcessoRapido(titulo='Extensão: <strong>Projetos</strong>', url='/manuais/projetos/extensao/index.html')
                    )

                if 'pesquisa' in settings.INSTALLED_APPS:
                    quadro.add_item(
                        layout.ItemAcessoRapido(titulo='Pesquisa: <strong>Projetos</strong>', url='/manuais/projetos/pesquisa/pesquisa/index.html')
                    )
                if 'documento_eletronico' in settings.INSTALLED_APPS:
                    quadro.add_item(
                        layout.ItemAcessoRapido(
                            titulo='Administração: <strong>Documento Eletrônico</strong>', url='/manuais/admin/documento_eletronico/index.html'
                        )
                    )
                if 'processo_eletronico' in settings.INSTALLED_APPS:
                    quadro.add_item(
                        layout.ItemAcessoRapido(
                            titulo='Administração: <strong>Processo Eletrônico</strong>', url='/manuais/admin/processo_eletronico/index.html'
                        )
                    )

            if (
                request.user.has_perm('arquivo.pode_fazer_upload_arquivo')
                or request.user.has_perm('arquivo.pode_identificar_arquivo')
                or request.user.has_perm('arquivo.pode_validar_arquivo')
            ):
                quadro.add_item(layout.ItemAcessoRapido(titulo='Gestão de Pessoas', url='/manuais/rh/index.html'))

    return quadro


@rtr('meus_alertas.html')
@login_required
def meus_avisos(request):
    timeout = 5 * 60

    def index_infos_sessao():
        retorno = []
        for _, data in layout.index_infos_data.send(sender=index, request=request):
            retorno.extend(data)
        return retorno

    infos = get_session_cache(request, 'index_infos_data', index_infos_sessao, timeout)
    return locals()


@rtr('meus_alertas.html')
@login_required
def meus_alertas(request):
    def index_inscricoes_sessao():
        retorno = []
        for _, data in layout.index_inscricoes_data.send(sender=index, request=request):
            retorno.extend(data)
        return retorno

    inscricoes = index_inscricoes_sessao()
    return locals()


@rtr('meus_alertas.html')
@login_required
def minhas_pendencias(request):
    def index_atribuidos_a_mim_sessao():
        retorno = []
        for _, data in layout.index_atribuidos_a_mim_data.send(sender=index, request=request):
            retorno.extend(data)
        return retorno

    atribuidos_a_mim = index_atribuidos_a_mim_sessao()
    return locals()


@rtr('meus_alertas.html')
@login_required
def minhas_pendencias_coletivas(request):
    def index_atribuidos_a_meus_grupos_sessao():
        retorno = []
        for _, data in layout.index_atribuidos_a_meus_grupos_data.send(sender=index, request=request):
            retorno.extend(data)
        return retorno

    atribuidos_a_meus_grupos = index_atribuidos_a_meus_grupos_sessao()
    return locals()


@rtr()
@login_required
def contador_minhas_notificacoes(request):
    return JsonResponse({'contador': RegistroNotificacao.contar_nao_lidas(request.user)})


@rtr()
@login_required
def meu_quadro(request, id_quadro):
    titulo_quadro = base64.b64decode(id_quadro).decode()
    quadro = get_quadro_by_name(titulo_quadro, request)
    if quadro and quadro.get_noticias():
        hash_list = []
        layouts_salvos = IndexLayout.get_layouts_usuario(request)
        for quadro_layout in layouts_salvos.values():
            hash_list.append(quadro_layout.get('hash_quadros'))
        if quadro.get_hash() in hash_list:
            quadro = None
    return locals()


def _carregar_caches_quadros(request: HttpRequest, chaves: list) -> tuple[dict, dict]:
    """Carrega os caches (global e de sessão) dos quadros informados sem varrer o Redis.

    Monta as chaves exatas a partir de ``chaves`` e usa ``get_many``, evitando o
    ``cache.keys('_cache_quadro*')`` (Redis ``KEYS``, O(N) sobre todo o keyspace e
    bloqueante). Retorna dois dicts (global, sessão) só com as chaves existentes.
    """
    if not settings.USE_REDIS:
        return {}, {}
    slugs = [slugify(chave) for chave in chaves]
    global_caches = cache.get_many([f'_cache_quadro_{slug}' for slug in slugs])
    session_caches = cache.get_many([f'_cache_{request.user.username}_quadro_{slug}' for slug in slugs])
    return global_caches, session_caches


def _coluna_do_layout(quadro_layout: dict) -> str:
    """Nome da coluna (esquerda/centro/direita) a partir do número salvo no layout do quadro."""
    return {1: 'esquerda', 2: 'centro'}.get(quadro_layout['coluna'], 'direita')


def _quadros_list_da_coluna(coluna: str, todas_chaves: list, layouts_salvos: dict) -> list:
    """Chaves de quadros pertencentes à ``coluna``; quadros sem layout salvo caem à esquerda."""
    restantes = list(todas_chaves)
    quadros_list = []
    for chave, quadro_layout in layouts_salvos.items():
        if chave not in restantes:
            continue
        restantes.remove(chave)
        visivel = quadro_layout and not quadro_layout.get('escondido', False)
        if visivel and _coluna_do_layout(quadro_layout) == coluna:
            quadros_list.append(chave)
    if coluna == 'esquerda':
        quadros_list.extend(restantes)
    return quadros_list


def _quadro_do_cache(chave: str, request: HttpRequest, global_caches: dict, session_caches: dict):
    """Quadro serializado no cache (global tem precedência sobre a sessão), já desserializado, ou ``None``."""
    slug = slugify(chave)
    pickled = global_caches.get(f'_cache_quadro_{slug}') or session_caches.get(f'_cache_{request.user.username}_quadro_{slug}')
    if pickled:
        return pickle.loads(codecs.decode(pickled.encode(), 'base64'))
    return None


def _quadro_visivel(quadro, layouts_salvos: dict):
    """Oculta (retorna ``None``) o quadro cujas notícias já foram vistas (hash presente no layout do usuário)."""
    if quadro and quadro.get_noticias():
        hashes = [ql.get('hash_quadros') for ql in layouts_salvos.values() if ql.get('hash_quadros')]
        if quadro.get_hash() in hashes:
            return None
    return quadro


@rtr()
@login_required
def meus_quadros_por_coluna(request: HttpRequest, coluna: str) -> dict:
    todas_chaves = layout.chaves_de_quadros_visiveis()
    layouts_salvos = IndexLayout.get_layouts_usuario(request)
    global_caches, session_caches = _carregar_caches_quadros(request, todas_chaves)
    quadros_list = _quadros_list_da_coluna(coluna, todas_chaves, layouts_salvos)
    quadros = []
    for chave in quadros_list:
        quadro = _quadro_do_cache(chave, request, global_caches, session_caches) or get_quadro_by_name(chave, request)
        quadro = _quadro_visivel(quadro, layouts_salvos)
        if quadro:
            quadros.append(quadro)
    return locals()


@rtr()
@login_required
def meus_quadros(request: HttpRequest) -> JsonResponse:
    todas_chaves = layout.chaves_de_quadros_visiveis()
    layouts_salvos = IndexLayout.get_layouts_usuario(request)
    global_caches, session_caches = _carregar_caches_quadros(request, todas_chaves)

    def render_quadro(chave):
        slug = slugify(chave)
        pickled = global_caches.get(f'_cache_quadro_{slug}') or session_caches.get(f'_cache_{request.user.username}_quadro_{slug}')
        quadro_str = ''
        if pickled:
            unpickled = pickle.loads(codecs.decode(pickled.encode(), 'base64'))
            if unpickled and unpickled.get_noticias():
                hashes = [ql.get('hash_quadros') for ql in layouts_salvos.values()]
                if unpickled.get_hash() in hashes:
                    unpickled = None
            quadro_str = minify_html(render_to_string('meu_quadro.html', {'quadro': unpickled}, request).strip())
        return quadro_str, bool(pickled)

    quadros = collections.OrderedDict(esquerda=[], centro=[], direita=[])
    restantes = list(todas_chaves)
    for chave, quadro_layout in layouts_salvos.items():
        if chave not in restantes:
            continue
        restantes.remove(chave)
        if quadro_layout and not quadro_layout.get('escondido', False):
            quadro_str, cached = render_quadro(chave)
            quadros[_coluna_do_layout(quadro_layout)].append([chave, quadro_str, cached])
    for chave in restantes:
        quadro_str, cached = render_quadro(chave)
        quadros['esquerda'].append([chave, quadro_str, cached])
    return JsonResponse(quadros)


@login_required
def painel_controle_secretario_academico(request):
    is_secretario_edu = request.user.has_group_cached('Secretário Acadêmico', ignore_groups_if_superuser=False)

    contexto = {}

    if is_secretario_edu and 'edu' in settings.INSTALLED_APPS:
        from edu.views import contexto_painel_controle

        painel_controle = contexto_painel_controle(request)
        contexto = {
            'periodo_letivo_atual': painel_controle['periodo_letivo_atual'],
            'diretorias_com_pendencia': painel_controle['diretorias_com_pendencia'],
            'painel': painel_controle['painel'],
        }
    return render(request, 'edu/templates/contexto_painel_controle.html', contexto)


def service_worker(request):
    return render(request, 'comum/templates/service_worker.js', content_type='application/javascript')


def push_web_notification(request):
    vapid_public_key = Configuracao.get_valor_por_chave('djtools', 'vapid_public_key')
    return render(
        request, 'comum/templates/push_web_notification.js', content_type='application/javascript', context={'vapid_public_key': vapid_public_key}
    )


@rtr()
@login_required(login_url=None if settings.PUBLIC_INDEX_URL == '/' else settings.PUBLIC_INDEX_URL)
def index(request):
    if request.user.is_superuser and not request.user.get_profile():
        return httprr('/comum/admin/')
    contexto = {}

    # No SETTINGS IGNORE_COMPONENTES_INDEX = True
    # - Possibilita que em localhos o desenvolvedor possa ignorar os
    #   componentes da tela principal que fazem com que demore MUITO renderizar a index
    mostrar_componentes = True
    if getattr(settings, 'IGNORE_COMPONENTES_INDEX', False) and settings.IGNORE_COMPONENTES_INDEX:
        mostrar_componentes = False
    contexto['mostrar_componentes'] = mostrar_componentes

    if mostrar_componentes:
        is_secretario_edu = request.user.has_group_cached('Secretário Acadêmico', ignore_groups_if_superuser=False)
        notificacoes_importantes = []
        esconder_manutencao = request.GET.get('esconder_manutencao', None)
        if esconder_manutencao or request.session.get(f'esconder_manutencao_{esconder_manutencao}'):
            request.session[f'esconder_manutencao_{esconder_manutencao}'] = True
        manutencoes = ManutencaoProgramada.proximas_notificacoes(request.user)
        for manutencao in manutencoes:
            if not request.session.get(f'esconder_manutencao_{manutencao.id}'):
                notificacoes_importantes.append(manutencao.get_mensagem())
        for _, data in layout.index_notificacoes_importantes_data.send(sender=index, request=request):
            notificacoes_importantes.extend(data)
        contexto['is_secretario_edu'] = is_secretario_edu
        contexto['title'] = 'Início'
        contexto['notificacoes_importantes'] = notificacoes_importantes

    return contexto


@rtr()
@login_required()
@permission_required('comum.change_prestadorservico')
def visualizar_publico(request, id):
    publico = get_object_or_404(Publico, pk=id)
    try:
        lista_publico = publico.get_queryset().all()
    except Exception as e:
        return httprr('/admin/comum/publico/', f'Ocorreu um erro ao realizar a consulta: {e!s}', 'error')

    return locals()


@login_required()
def docs(request, path, tipo):
    # é servidor/prestador?
    vinculo = request.user.get_vinculo()
    if not vinculo.eh_servidor() and not vinculo.eh_prestador():
        raise PermissionDenied('Acesso negado.')

    # se não informou qual arquivo abrir sugere index.html
    if len(path) == 0:
        path = 'index.html'

    return serve(request, path, os.path.join(settings.BASE_DIR, f'docs/{tipo}/.build/html/'), False)


@rtr()
@login_required()
def telefones(request):
    title = 'Telefones'
    eh_aluno = request.user.get_vinculo().eh_aluno()
    setores = Setor.objects.suap_ativos().filter(uo__isnull=False).order_by('uo__setor__sigla', 'sigla')
    campi = UnidadeOrganizacional.objects.suap().all().order_by('setor__sigla')
    return locals()


@rtr()
@login_required()
def telefones_csv(request):
    rows = [[nomenclatura.campus, 'Setor Nome', 'Setor Sigla', 'Telefone', 'Ramal']]
    for setortelefone in SetorTelefone.objects.all():
        rows.append([setortelefone.setor.uo, setortelefone.setor.nome, setortelefone.setor.sigla, setortelefone.numero, setortelefone.ramal])

    return CsvResponse(rows)


@rtr()
def admin(request):
    title = 'Administração do SUAP'
    if not (request.user.has_perm('rh.pode_gerenciar_extracao_siape') or request.user.has_perm('rh.pode_gerenciar_extracao_scdp')):
        raise PermissionDenied
    if Configuracao.get_valor_por_chave('comum', 'instituicao_anterior_identificador'):
        codigos_instituicoes = [
            codigo_instituicao.strip()
            for codigo_instituicao in Configuracao.get_valor_por_chave('comum', 'instituicao_anterior_identificador').split(';')
        ]

    superusers = User.objects.filter(is_superuser=True).count()

    # Preferencias
    tres_meses = datetime.now() - timedelta(days=90)
    preferencias = Preferencia.objects.filter(usuario__is_active=True, usuario__last_login__gte=tres_meses).aggregate(
        tema_padrao=Count('pk', filter=Q(tema=Preferencia.PADRAO)),
        tema_dunas=Count('pk', filter=Q(tema=Preferencia.DUNAS)),
        tema_aurora=Count('pk', filter=Q(tema=Preferencia.AURORA)),
        tema_luna=Count('pk', filter=Q(tema=Preferencia.LUNA)),
        tema_govbr=Count('pk', filter=Q(tema=Preferencia.GOVBR)),
        tema_alto_contraste=Count('pk', filter=Q(tema=Preferencia.ALTO_CONSTRASTE)),
        tema_ifs=Count('pk', filter=Q(tema=Preferencia.IFS)),
        tema_modo_daltonismo=Count('pk', filter=Q(tema=Preferencia.MODO_DALTONISMO)),
        somente_via_suap=Count('pk', filter=Q(via_suap=True, via_email=False)),
        somente_via_email=Count('pk', filter=Q(via_suap=False, via_email=True)),
        via_ambos=Count('pk', filter=Q(via_suap=True, via_email=True)),
    )
    tema_padrao = preferencias['tema_padrao']
    tema_dunas = preferencias['tema_dunas']
    tema_aurora = preferencias['tema_aurora']
    tema_luna = preferencias['tema_luna']
    tema_govbr = preferencias['tema_govbr']
    tema_alto_contraste = preferencias['tema_alto_contraste']
    tema_ifs = preferencias['tema_ifs']
    tema_modo_daltonismo = preferencias['tema_modo_daltonismo']
    somente_via_suap = preferencias['somente_via_suap']
    somente_via_email = preferencias['somente_via_email']
    via_ambos = preferencias['via_ambos']
    total_novos_temas = tema_dunas + tema_aurora + tema_luna + tema_govbr + tema_alto_contraste + tema_ifs + tema_modo_daltonismo
    if not tema_padrao and total_novos_temas == 0:
        total_tema = None
    else:
        total_tema = f'{(total_novos_temas * 100) / (tema_padrao + total_novos_temas):.2f}'

    return locals()


@rtr()
@login_required()
def maquinas(request):
    title = 'Situação das Máquinas Ativas'

    if not request.user.is_superuser:
        raise PermissionDenied('Você não tem permissão de acesso a essa página')
    from ponto.models import Maquina

    """
    relatorio = {
        "uo": {'inativas':[], 'ativas':[], 'uo_nome':nome},
    }
    """
    relatorio = {}

    maquinas_sem_log = Maquina.objects.select_related('uo', 'uo__setor').filter(ativo=True, ultimo_log__isnull=True)
    maquinas_com_log = Maquina.objects.select_related('uo', 'uo__setor').filter(ativo=True).exclude(ultimo_log__isnull=True)

    for maquina in maquinas_sem_log:
        if maquina.uo not in relatorio:
            relatorio[maquina.uo] = {'inativas': [], 'ativas': [], 'uo_nome': maquina.uo}
        relatorio[maquina.uo]['inativas'].append(maquina)

    for maquina in maquinas_com_log:
        if maquina.uo not in relatorio:
            relatorio[maquina.uo] = {'inativas': [], 'ativas': [], 'uo_nome': maquina.uo}
        relatorio[maquina.uo]['ativas'].append(maquina)

    return {'title': title, 'relatorio': relatorio, 'qtd_maquinas_com_log': maquinas_com_log.count, 'qtd_maquinas_sem_log': maquinas_sem_log.count}


@rtr()
@login_required()
def configuracao(request, app_label=None):
    title = 'Configuração do Sistema'
    app_labels = [
        name.replace('Configurador', '').strip()
        for name in request.user.groups.all().filter(name__endswith='Configurador').values_list('name', flat=True)
    ]
    if not request.user.is_superuser and not app_labels:
        raise PermissionDenied
    FormClass = ConfiguracaoFormFactory(app_label, only=None if request.user.is_superuser else app_labels)
    form = FormClass(request.POST or None, request.FILES or None)
    if form.is_valid():
        form.save()
        return httprr('.', 'Configuração salva com sucesso.')
    return {'title': title, 'form': form, 'app_labels': app_labels, 'app_label': app_label}


@rtr()
@login_required()
@permission_required('rh.pode_gerenciar_extracao_siape')
def baixar_macro_siape_personalizavel(request: HttpRequest) -> HttpResponse | dict:
    title = 'Baixar macro SIAPE'
    form = MacroForm(request.POST or None)
    if form.is_valid():
        uf = Configuracao.get_valor_por_chave('comum', 'instituicao_estado')
        cod_instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao_identificador')
        if not uf or not cod_instituicao:
            return HttpResponse('Defina UF e o Código da Instituição.')
        t = get_template('comum/templates/baixar_macro_siape.mac')
        template_compilado = t.render({'cod_instituicao': cod_instituicao, 'uf': uf.lower()})

        arquivos_extrator = form.cleaned_data['arquivos_extrator']

        entryscreen = 'unidadeorganizacional1'
        exitscreen = 'historicosetorfim'
        root = ElementTree.fromstring(template_compilado)
        if 'unidadeorganizacional' not in arquivos_extrator:
            entryscreen = f'{arquivos_extrator[0]}1'
            root[0].attrib['entryscreen'] = 'false'
        if 'historicosetor' not in arquivos_extrator:
            exitscreen = f'{arquivos_extrator[-1]}fim'
            root[-1].attrib['exitscreen'] = 'false'

        telas_finais = [f'{tela}fim' for tela in arquivos_extrator]

        for screen in root.iter('screen'):
            if entryscreen and screen.attrib['name'] == entryscreen:
                screen.attrib['entryscreen'] = 'true'
            if exitscreen and screen.attrib['name'] == exitscreen:
                screen.attrib['exitscreen'] = 'true'

            if screen.attrib['name'] in telas_finais and screen.attrib['name'] != exitscreen:
                screen[-1][0].attrib['name'] = telas_finais[telas_finais.index(screen.attrib['name']) + 1].replace('fim', '1')
        response = HttpResponse(ElementTree.tostring(root), content_type='plain/mac')
        response['Content-Disposition'] = 'attachment; filename=macro_siape.mac'
        return response
    return locals()


@rtr()
@login_required()
@permission_required('rh.pode_gerenciar_extracao_siape')
def baixar_macro_siape(request: HttpRequest) -> HttpResponse:
    uf = Configuracao.get_valor_por_chave('comum', 'instituicao_estado')
    cod_instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao_identificador')
    if not uf or not cod_instituicao:
        return HttpResponse('Defina Uf e o código da instituição')
    uf = uf.lower()
    t = get_template('comum/templates/baixar_macro_siape.mac')
    if 'instituicao_anterior' in request.GET:
        cod_instituicao = request.GET['instituicao_anterior']
        t = get_template('comum/templates/baixar_macro_pca.mac')
    if 'extracao_sem_posicionamentos_que_estejam_sem_documento_legal' in request.GET:
        t = get_template('comum/templates/baixar_macro_pca_sem_documento_legal.mac')
    response = HttpResponse(t.render({'cod_instituicao': cod_instituicao, 'uf': uf}), content_type='plain/mac')
    response['Content-Disposition'] = 'attachment; filename=macro_siape.mac'
    return response


@rtr()
@login_required()
@permission_required('rh.pode_gerenciar_extracao_siape')
def baixar_macro_siape_historico_pca(request):
    title = 'Macro para recuperar históricos de PCAs dos servidores'
    form = MacroHistoricoPCAForm(request.POST or None)
    if form.is_valid():
        t = get_template('comum/templates/baixar_macro_historico_pca.mac')
        servidores = form.cleaned_data.get('servidores')
        matriculas = servidores.values_list('matricula_sipe', flat=True)
        primeira_matricula = matriculas[0]
        response = HttpResponse(t.render({'primeira_matricula': primeira_matricula, 'matriculas': matriculas[1:]}), content_type='plain/mac')
        response['Content-Disposition'] = 'attachment; filename=macro_siape.mac'
        return response

    return locals()


@rtr()
@permission_required(['rh.pode_gerenciar_setor_telefone', 'rh.chefe'])
def setor_adicionar_telefone(request, objeto_pk):
    setor = Setor.objects.get(pk=objeto_pk)
    title = f'Editar telefones do setor {setor.sigla} - {setor.nome}'
    form = SetorAdicionarTelefoneForm(request.POST or None)
    if form.is_valid():
        SetorTelefone.objects.create(
            setor=setor, numero=form.cleaned_data['numero'], ramal=form.cleaned_data['ramal'], observacao=form.cleaned_data['observacao']
        )
        return httprr('.', 'Telefone adicionado com sucesso.')
    else:
        return locals()


@rtr()
@permission_required(['rh.pode_gerenciar_setor_telefone', 'rh.chefe'])
def setor_editar_email(request, objeto_pk):
    setor = get_object_or_404(Setor, pk=objeto_pk)

    if not request.user.has_perm('rh.pode_gerenciar_setor_telefone'):
        if not request.user.get_relacionamento().eh_chefe_do_setor_hoje(setor):
            raise PermissionDenied('Você precisa ser chefe do setor.')

    title = f'Editar email do setor {setor.sigla} - {setor.nome}'
    form = SetorEditarEmailForm(request.POST or None, instance=setor)
    if form.is_valid():
        form.save()
        return httprr('.', 'E-mail editado com sucesso.')
    else:
        return locals()


@rtr()
@permission_required(['rh.pode_gerenciar_setor_telefone', 'rh.chefe'])
def setor_remover_telefone(request, objeto_pk):
    telefone = SetorTelefone.objects.get(pk=objeto_pk)

    if not request.user.has_perm('rh.pode_gerenciar_setor_telefone'):
        if not request.user.get_relacionamento().eh_chefe_do_setor_hoje(telefone.setor):
            raise PermissionDenied('Você precisa ser chefe do setor.')

    setor_pk = telefone.setor.pk
    telefone.delete()
    return httprr(f'/comum/setor_adicionar_telefone/{setor_pk}/', 'Telefone removido com sucesso.')


@rtr()
@login_required()
def adicionar_contato_de_emergencia(request: HttpRequest, pessoa_fisica_pk: int) -> HttpResponse | dict:
    pessoa_fisica = get_object_or_404(PessoaFisica, pk=pessoa_fisica_pk)
    title = f'Novo Contato de Emergência de {pessoa_fisica.nome}'
    verificacao_propria = request.user.get_vinculo().eh_servidor() and request.user.get_profile() == pessoa_fisica
    if not request.user.has_perm('comum.add_contatoemergencia') and not verificacao_propria:
        raise PermissionDenied
    form = ContatoEmergenciaForm(request.POST or None)
    form.instance.pessoa_fisica = pessoa_fisica
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            return httprr('..', 'Contato adicionado com sucesso.')
    return locals()


@rtr()
@login_required()
def listar_contatos_de_emergencia(request: HttpRequest, pessoa_fisica_pk: int) -> HttpResponse | dict:
    pessoa_fisica = get_object_or_404(PessoaFisica, pk=pessoa_fisica_pk)
    contatos = ContatoEmergencia.objects.filter(pessoa_fisica=pessoa_fisica)
    title = f'Contatos de Emergência de {pessoa_fisica.nome}'
    verificacao_propria = request.user.get_vinculo().eh_servidor() and request.user.get_profile() == pessoa_fisica
    # Controla a coluna de ações do template; quem gerencia também lista (como change ⇒ view no admin).
    pode_gerenciar_contatos = (
        request.user.has_perm('comum.add_contatoemergencia')
        or request.user.has_perm('comum.change_contatoemergencia')
        or request.user.has_perm('comum.delete_contatoemergencia')
        or verificacao_propria
    )
    if not request.user.has_perm('comum.view_contatoemergencia') and not pode_gerenciar_contatos:
        raise PermissionDenied

    return locals()


@rtr()
@login_required()
def fiscal_concurso(request: HttpRequest) -> HttpResponse | dict:
    servidor = request.user.get_relacionamento()
    if InscricaoFiscal.objects.filter(servidor=servidor):
        return httprr('/', 'Sua inscrição já foi realizada.')
    if request.method == 'POST':
        # O form exclui `servidor`: ele entra pela instância, não por kwarg (#17396).
        form = InscricaoFiscalForm(request.POST, instance=InscricaoFiscal(servidor=servidor))
        if form.is_valid():
            form.save()
            return httprr('/', 'Inscrição realizada com sucesso.')
    else:
        form = InscricaoFiscalForm()
    return locals()


def gerar_cvs(request, id_documentocontroletipo):
    documentocontroletipo = DocumentoControleTipo.objects.get(id=id_documentocontroletipo)
    # `id_relacionamento` é um PositiveIntegerField (o lado "id" da GenericForeignKey), não uma
    # relação: incluí-lo aqui fazia o `select_related` levantar FieldError e a rota devolver 500.
    documentoscontroles = DocumentoControle.objects.select_related(
        'solicitante_vinculo', 'solicitante_vinculo__setor', 'solicitante_vinculo__tipo_relacionamento'
    ).filter(documento_tipo=documentocontroletipo, ativo=True)

    controle_csv = HttpResponse(content_type='text/csv')
    controle_csv['Content-Disposition'] = 'attachment; filename=documento_controle.csv'

    writer = csv.writer(controle_csv)
    writer.writerow(['Tipo do Documento', 'Identificação do Documento', 'Matrícula', 'Nome', nomenclatura.campus, 'Setor'])

    for documentocontrole in documentoscontroles:
        # O campo do model é `solicitante_vinculo`; `vinculo_solicitante` não existe e fazia a
        # rota estourar AttributeError assim que houvesse uma solicitação ativa para listar.
        vinculo = documentocontrole.solicitante_vinculo
        campus = ''
        if vinculo.setor:
            campus = vinculo.setor.uo
            writer.writerow(
                [
                    documentocontroletipo,
                    documentocontrole.documento_id,
                    vinculo.relacionamento.matricula,
                    vinculo.pessoa.nome,
                    campus,
                    vinculo.setor,
                ]
            )

    return controle_csv


def formatar_ref(arquivo_ref):
    campos = []
    posicao = 1
    for linha in arquivo_ref:
        # Iterar o arquivo enviado devolve *bytes*: sem decodificar, `i[41:].split(',')`
        # levantava TypeError e a tela inteira dava 500. `get_itens` já decodificava assim.
        i = linha.decode('latin-1').rstrip('\r\n')
        descricao = i[:40].strip()
        tipo = i[40]
        tamanho_int = sum(int(n) for n in i[41:].split(','))
        campos.append(
            {
                'descricao': descricao,
                'tipo': tipo,
                'tamanho': i[41:],
                'tamanho_int': tamanho_int,
                'inicio': posicao - 1,
                'fim': posicao + tamanho_int - 1,
            }
        )  # tamanho puro
        posicao = posicao + tamanho_int
    return campos


def get_itens(arquivo_txt, ref, busca_texto):
    """
    Retorna listagem de itens/linhas do arquivo siafe que contêm o texto buscado.
    Caso o texto seja vazio, a listagem inteira é retornada
    """
    itens = []
    for linha in arquivo_txt:
        linha_decodificada = linha.decode('latin-1')
        linha_decodificada = linha_decodificada.strip()
        if busca_texto.lower() in linha_decodificada.lower():
            item = {}
            item['conteudo_puro'] = linha_decodificada
            for campo in ref:
                item[campo['descricao']] = linha_decodificada[campo['inicio'] : campo['fim']].strip()
            itens.append(item)

    return itens


###########################################
# VISUALIZAÇÃO DE ARQUIVOS SIAFE ##########
###########################################


@rtr()
@login_required()
def ver_arquivo_siafi(request):
    if request.method == 'POST':
        form = ExtracaoForm(request.POST, request.FILES)
        if form.is_valid():
            arquivo_1 = request.FILES['arquivo_1']
            arquivo_2 = request.FILES['arquivo_2']
            texto = form.cleaned_data['campo_busca'].strip()
            ref = formatar_ref(arquivo_1)
            itens = get_itens(arquivo_2, ref, texto)
            arquivo = arquivo_2.name
            request.session['ref'] = ref
            request.session['itens'] = itens
            request.session['arquivo'] = arquivo
    else:
        form = ExtracaoForm()
        if 'page' in request.GET:
            ref = request.session['ref']
            itens = request.session['itens']
            arquivo = request.session['arquivo']

    return locals()


##################################################################
# Funções para o terminal de chaves, ponto e cadastro de digital #
##################################################################


def get_chave_publica_suap(request):
    """
    Esta view é executada na instalação do terminal de ponto para habilitar o
    acesso SSH sem senha a partir do servidor do SUAP.
    """
    chave_publica = Configuracao.get_valor_por_chave('comum', 'chave_publica')
    response = HttpResponse(chave_publica, content_type='text/plain')
    response['Content-Disposition'] = 'attachment; filename=suap-chave-publica.pub'
    return response


def get_pessoa(request, username, versao=None):
    # Ainda falta desconsiderar as uos caso seja ead
    return get_dump_pessoas(request, username, versao)


def get_pessoas(request: HttpRequest, versao: str | None = None) -> HttpResponse:
    return get_dump_pessoas(request, None, versao)


def _get_arquivo_dump_pessoas(maquina_id: int, versao: str | None, username: str | None) -> str:
    versao_normalizada = versao or 'sem-versao'
    username_normalizado = username or 'todos'
    if len(username_normalizado.encode()) > 64:
        username_normalizado = hashlib.sha1(username_normalizado.encode()).hexdigest()
    # Nome trocado com a linha por vínculo: o zip do dia do deploy (id da PF) não casa com as permissões de chaves.
    nome_arquivo = f'tabela_terminal_vinculos-{maquina_id}-{versao_normalizada}-{username_normalizado}.zip'
    return os.path.join(settings.TEMP_DIR, nome_arquivo)


def _arquivo_dump_do_dia(caminho_arquivo: str) -> bool:
    return (
        exists(caminho_arquivo)
        and zipfile.is_zipfile(caminho_arquivo)
        and datetime.fromtimestamp(os.stat(caminho_arquivo).st_mtime).date() == date.today()
    )


@transaction.atomic
def get_dump_pessoas(request: HttpRequest, username: str | None, versao: str | None = None) -> HttpResponse:
    from ponto.models import Maquina, MaquinaLog, VersaoTerminal

    try:
        m = Maquina.objects.get(ip=get_client_ip(request), ativo=True)
    except Maquina.DoesNotExist:
        raise PermissionDenied('Máquina sem permissões')

    if versao:
        m.versao_terminal = VersaoTerminal.objects.get_or_create(numero=versao)[0]
        m.save()

    arquivo_dump = _get_arquivo_dump_pessoas(m.id, versao, username)
    # Não existe arquivo gerado no dia, então precisa ser criado
    if not _arquivo_dump_do_dia(arquivo_dump):
        dump_file = tempfile.NamedTemporaryFile(delete=False, mode='wb')
        arquivo_dump_temporario = tempfile.NamedTemporaryFile(delete=False).name
        cursor = connection.cursor()

        try:
            cursor.execute('DROP TABLE IF EXISTS tabela_terminal_ponto')
            query = obter_query(versao, username, m.uo_id)
            cursor.execute(query)

            # Gerando o dump
            with cursor.copy('COPY tabela_terminal_ponto TO STDOUT') as copy:
                for data in copy:
                    dump_file.write(data)
            dump_file.close()

            # Removendo tabela temporária
            cursor.execute('DROP TABLE IF EXISTS tabela_terminal_ponto')

            # Compactando o dump
            with zipfile.ZipFile(arquivo_dump_temporario, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                zip_file.write(dump_file.name, 'tabela_terminal.copy')
            os.replace(arquivo_dump_temporario, arquivo_dump)
        finally:
            with suppress(Exception):
                cursor.execute('DROP TABLE IF EXISTS tabela_terminal_ponto')
            dump_file.close()
            if exists(dump_file.name):
                os.remove(dump_file.name)
            if exists(arquivo_dump_temporario):
                os.remove(arquivo_dump_temporario)

    MaquinaLog.objects.create(maquina=m, operacao='comum_get_dump_pessoas')

    response = FileResponse(open(arquivo_dump, 'rb'), content_type='application/zip')
    response['Content-Disposition'] = 'attachment; filename=dump_terminal.zip'
    return response


def obter_query(versao, username, uo_id):
    def ajustar_colunas(sql, versao):
        extras = ''
        if versao and versao >= '1.2.0':
            extras = """
                "pf"."pf_pode_bater_ponto" as "pode_bater_ponto",
                "pf"."pf_senha_ponto" as "senha_ponto",
            """
        query = f'''
            SELECT
              "pf"."pf_id" as "id",
              "pf"."pf_username" as "username",
              "pf"."pf_nome" as "nome",
              "pf"."pf_setor_sigla" as "setor",
              "pf"."pf_campus_sigla" as "campus",
              "pf"."pf_template" as "template",
              "pf"."pf_tem_digital_fraca" as "tem_digital_fraca",
              "pf"."pf_operador_chaves" as "operador_chave",
              "pf"."pf_operador_cadastro" as "operador_cadastro",
              {extras}
              "pf"."exportada"
            FROM ({sql}) as "pf"'''
        return query

    from rh.models import Servidor

    filters_servidores = [Q(ativo=True)]
    filters_prestadores = [Q(ativo=True)]
    filters_aluno = [Q(situacao__ativo=True)]
    if username:
        filters_servidores.append(Q(matricula=username))
        filters_prestadores.append(Q(matricula=username))
        filters_aluno.append(Q(matricula=username))
        campi_ead = UnidadeOrganizacional.objects.suap().filter(tipo=UnidadeOrganizacional.TIPO_CAMPUS_EAD).values_list('id', flat=True)
        filters_aluno.append(Q(curso_campus__diretoria__setor__uo__id__in=campi_ead) | Q(curso_campus__diretoria__setor__uo__id=uo_id))
    else:
        filters_prestadores.append(Q(pessoa_fisica__template__isnull=False))
        filters_aluno.append(Q(curso_campus__diretoria__setor__uo__id=uo_id))

    selects_servidores = {'exportada': True}
    selects_prestadores = {'exportada': True}
    selects_aluno = {'exportada': True, 'pf_operador_cadastro': False, 'pf_operador_chaves': False}

    operadores_chave = (
        User.objects.filter(groups__name__in=['Operador de Chaves', 'Coordenador de Chaves Sistêmico']).values_list('username', flat=True).distinct()
    )
    operadores_cadastro = User.objects.filter(groups__permissions__codename='pode_cadastrar_digital').values_list('username', flat=True).distinct()
    # Quem tem digital fraca entra no terminal legado por senha local, nunca conferida com o SUAP:
    # não sai como operador de cadastro, e o próprio terminal recusa o login dele (#17482).
    eh_operador_cadastro = Case(
        When(matricula__in=operadores_cadastro, pessoa_fisica__tem_digital_fraca=False, then=Value(True)),
        default=Value(False),
        output_field=BooleanField(),
    )

    annotations_servidores = {
        'pf_id': -F('vinculos__id'),  # uma linha por vínculo: o terminal guarda o id; o SUAP o lê em Vinculo.objects.do_terminal
        'pf_username': F('matricula'),
        'pf_nome': F('pessoa_fisica__nome'),
        'pf_template': F('pessoa_fisica__template'),
        'pf_tem_digital_fraca': F('pessoa_fisica__tem_digital_fraca'),
        'pf_setor_sigla': Coalesce(F('setor__sigla'), Value('N/A')),
        'pf_campus_sigla': Coalesce(F('setor__uo__setor__sigla'), Value('N/A')),
        'pf_operador_cadastro': eh_operador_cadastro,
        'pf_operador_chaves': Case(When(matricula__in=operadores_chave, then=Value(True)), default=Value(False), output_field=BooleanField()),
    }

    annotations_prestadores = {
        'pf_id': -F('vinculos__id'),
        'pf_username': F('matricula'),
        'pf_nome': F('pessoa_fisica__nome'),
        'pf_template': F('pessoa_fisica__template'),
        'pf_tem_digital_fraca': F('pessoa_fisica__tem_digital_fraca'),
        'pf_setor_sigla': Coalesce(F('setor__sigla'), Value('N/A')),
        'pf_campus_sigla': Coalesce(F('setor__uo__setor__sigla'), Value('N/A')),
        'pf_operador_cadastro': eh_operador_cadastro,
        'pf_operador_chaves': Case(When(matricula__in=operadores_chave, then=Value(True)), default=Value(False), output_field=BooleanField()),
    }

    annotations_aluno = {
        'pf_id': -F('vinculos__id'),
        'pf_username': F('matricula'),
        'pf_nome': F('pessoa_fisica__nome'),
        'pf_template': F('pessoa_fisica__template'),
        'pf_tem_digital_fraca': F('pessoa_fisica__tem_digital_fraca'),
        'pf_setor_sigla': Coalesce(F('curso_campus__diretoria__setor__sigla'), Value('N/A')),
        'pf_campus_sigla': Coalesce(F('curso_campus__diretoria__setor__uo__sigla'), Value('N/A')),
    }

    if versao and versao >= '1.2.0':
        selects_servidores.update({'pf_pode_bater_ponto': True})
        selects_aluno.update({'pf_pode_bater_ponto': False})
        selects_prestadores.update({'pf_pode_bater_ponto': True})

        annotations_servidores.update({'pf_senha_ponto': F('pessoa_fisica__senha_ponto')})
        annotations_prestadores.update({'pf_senha_ponto': F('pessoa_fisica__senha_ponto')})
        annotations_aluno.update({'pf_senha_ponto': F('pessoa_fisica__senha_ponto')})

    qs_servidores = Servidor.objects.filter(*filters_servidores).exclude(matricula='').exclude(vinculos__user__isnull=True)
    qs_servidores = (
        qs_servidores.annotate(**annotations_servidores)
        .extra(select=selects_servidores)
        .values(*(list(annotations_servidores.keys()) + list(selects_servidores.keys())))
        .distinct()
    )

    qs_prestadores = PrestadorServico.objects.filter(*filters_prestadores).exclude(matricula='').exclude(vinculos__user__isnull=True)
    qs_prestadores = (
        qs_prestadores.annotate(**annotations_prestadores)
        .extra(select=selects_prestadores)
        .values(*(list(annotations_prestadores.keys()) + list(selects_prestadores.keys())))
        .distinct()
    )
    query_servidores = versao and get_real_sql(qs_servidores, remove_order_by=True) or get_real_sql(qs_servidores, remove_order_by=False)
    query_servidores = ajustar_colunas(query_servidores, versao)

    query_prestadores = versao and get_real_sql(qs_prestadores, remove_order_by=True) or get_real_sql(qs_prestadores, remove_order_by=False)
    query_prestadores = ajustar_colunas(query_prestadores, versao)
    query_union = f'{query_servidores} UNION ALL {query_prestadores}'

    if 'edu' in settings.INSTALLED_APPS:
        from edu.models import Aluno

        qs_aluno = Aluno.objects.filter(*filters_aluno).exclude(vinculos__user__isnull=True).annotate(**annotations_aluno)
        qs_aluno = qs_aluno.extra(select=selects_aluno).values(*(list(annotations_aluno.keys()) + list(selects_aluno.keys()))).distinct()
        query_aluno = get_real_sql(qs_aluno)
        query_aluno = ajustar_colunas(query_aluno, versao)
        if versao:
            query_union = f'{query_union} UNION ALL {query_aluno}'

    # O id é a chave primária da tabela do terminal: sendo o do vínculo, a pessoa com mais de um
    # (servidor, prestador, aluno) tem uma linha por matrícula, cada uma batendo ponto no seu.
    return f'CREATE TEMP TABLE tabela_terminal_ponto ON COMMIT DROP AS {query_union}'


@transaction.atomic
def get_fotos_funcionarios(request):
    from ponto.models import Maquina, MaquinaLog

    try:
        m = Maquina.objects.get(ip=get_client_ip(request), ativo=True)
    except Maquina.DoesNotExist:
        raise PermissionDenied('Máquina sem permissões')

    storage = get_temp_storage()

    ARQUIVO_DUMP = 'fotos/fotos_funcionarios.zip'
    # gerado pelo comando fotos_funcionarios
    if not storage.exists(ARQUIVO_DUMP):
        raise Http404

    MaquinaLog.objects.create(maquina=m, operacao='comum_get_fotos_funcionarios')
    try:
        response = FileResponse(storage.open(ARQUIVO_DUMP), content_type='application/zip')
        response['Content-Disposition'] = 'attachment; filename=fotos.zip'
        response['Content-Length'] = storage.size(ARQUIVO_DUMP)
        return response
    except FileNotFoundError:
        raise Http404


@transaction.atomic
def get_fotos_alunos(request: HttpRequest) -> HttpResponse:
    from ponto.models import Maquina, MaquinaLog

    try:
        m = Maquina.objects.get(ip=get_client_ip(request), ativo=True, cliente_refeitorio=True)
    except Maquina.DoesNotExist:
        raise PermissionDenied('Máquina sem permissões')

    storage = get_temp_storage()

    ARQUIVO_DUMP = f'fotos/fotos_alunos_{m.uo.sigla}.zip'
    # gerado pelo comando fotos_alunos
    if not storage.exists(ARQUIVO_DUMP):
        raise Http404

    MaquinaLog.objects.create(maquina=m, operacao='comum_get_fotos_alunos')
    try:
        response = FileResponse(storage.open(ARQUIVO_DUMP), content_type='application/zip')
        response['Content-Disposition'] = 'attachment; filename=fotos.zip'
        response['Content-Length'] = storage.size(ARQUIVO_DUMP)
        return response
    except FileNotFoundError:
        raise Http404


@rtr()
@login_required()
def grupos_usuario(request, usuario_pk):
    usuario = get_object_or_404(User, pk=usuario_pk)
    usuario_logado = request.user
    if usuario_logado != usuario and not GerenciamentoGrupo.user_can_manage(usuario_logado):
        raise PermissionDenied
    title = f'Grupos do Usuário {usuario}'
    grupos = UsuarioGrupo.objects.filter(user=usuario).values_list('group__name', flat=True)
    GROUPS_DICT = {}
    for app in settings.INSTALLED_APPS:
        grupos_da_app = GroupPermission.obter_grupos_por_app_yaml(app)
        if grupos_da_app:
            for nome_grupo in grupos_da_app:
                if nome_grupo in grupos:
                    app_full_name = apps_django.get_app_config(app).get_full_name()
                    if app_full_name not in GROUPS_DICT:
                        GROUPS_DICT[app_full_name] = []
                    objeto_do_grupo = UsuarioGrupo.objects.filter(group__name=nome_grupo, user=usuario)[0]
                    meus_gerenciamentos = usuario_logado.gerenciamento_do_grupo(objeto_do_grupo.group)
                    sou_superusuario = usuario_logado.is_superuser
                    sou_eu_mesmo = usuario_logado == usuario
                    GROUPS_DICT[app_full_name].append(
                        (
                            objeto_do_grupo,
                            meus_gerenciamentos.exists() or sou_superusuario or sou_eu_mesmo,
                            meus_gerenciamentos.filter(eh_local=False).exists() or sou_superusuario or sou_eu_mesmo,
                        )
                    )

    apps = GROUPS_DICT
    apps = collections.OrderedDict(sorted(apps.items()))

    return locals()


@rtr()
def design_system(request):
    title = 'Design System'

    temas = get_temas()
    temas_gerais = temas['temas_gerais']
    temas_gov = temas['temas_gov']
    temas_acessibilidade = temas['temas_acessibilidade']

    tons = [50, 75, 100, 150, 200, 250, 300, 350, 400, 450, 500, 550, 600, 650, 700, 750, 800, 850, 900]
    temas = {
        'Padrão': ['Primary', 'Grey', 'Info', 'Warning', 'Caution', 'Danger', 'Success', 'Violet', 'Lime', 'Pink', 'Cyan', 'Brown', 'Steel'],
        'Aurora': ['Primary', 'Grey', 'Info', 'Warning', 'Caution', 'Danger', 'Success', 'Violet', 'Lime'],
        'Dunas': ['Primary', 'Grey', 'Info', 'Warning', 'Caution', 'Danger', 'Success', 'Violet', 'Lime'],
        'IFs': ['Primary', 'Secondary', 'Grey', 'Info', 'Warning', 'Caution', 'Danger', 'Success'],
        'Luna': ['Primary', 'Grey', 'Info', 'Warning', 'Caution', 'Danger', 'Success', 'Violet', 'Lime', 'Pink', 'Cyan', 'Brown', 'Steel'],
        'GovBR': ['Primary', 'Grey', 'Info', 'Warning', 'Caution', 'Danger', 'Success', 'Violet', 'Lime', 'Pink', 'Cyan'],
        'Alto Contraste': ['Primary', 'Info', 'Warning', 'Caution', 'Danger', 'Success', 'Violet', 'Lime', 'Pink', 'Cyan'],
        'Modo Daltonismo': ['Primary', 'Info', 'Warning', 'Caution', 'Danger', 'Success'],
    }

    return locals()


@rtr()
@login_required()
def maquinas_detalhes(request: HttpRequest, maquina_pk: int) -> dict:
    if not request.user.is_superuser:
        raise PermissionDenied('Você não tem permissão de acesso a essa página')

    def ping(servidor: str) -> bool:
        # Lista de argumentos: nada passa por shell. ``-W 1`` é a espera pela resposta no ping do
        # Linux (iputils); o ``-t 1`` de antes era timeout só no macOS — no Linux é TTL=1, que
        # descartava o pacote no primeiro roteador. O ``timeout`` do ``run`` é a rede de segurança.
        try:
            return subprocess.run(['ping', '-c', '1', '-W', '1', servidor], capture_output=True, timeout=3, check=False).returncode == 0
        except subprocess.TimeoutExpired, FileNotFoundError:
            return False

    from ponto.models import Maquina

    maquina = get_object_or_404(Maquina, pk=maquina_pk)
    maquina_ligada = ping(maquina.ip)
    ultimos_logs = maquina.maquinalog_set.all().order_by('-horario')[0:3]
    return locals()


@rtr()
@login_required()
def alterar_senha(request):
    title = 'Alterar senha'
    pessoa_fisica = request.user.get_profile()

    eh_usuario_autenticado_govbr = request.session.get('autenticou_com_govbr', False)
    if eh_usuario_autenticado_govbr:
        return HttpResponseForbidden('Esta funcionalidade não está disponível para usuário autenticado via Gov.BR')

    vinculo_atual = request.user.get_vinculo()
    # Recuperação de senha usa SÓ o e-mail pessoal — nunca o institucional (mesma senha do SUAP).
    if not vinculo_atual or not vinculo_atual.email_pessoal:
        url = '{}?next={}'.format(
            reverse_lazy('atualizar_email', kwargs={'vinculo_pk': vinculo_atual.pk if vinculo_atual else 0}), reverse_lazy('alterar_senha')
        )
        return httprr(url, 'Antes de alterar sua senha, informe um email secundário.', tag='info')

    email = vinculo_atual.email_pessoal
    form = AlterarSenhaForm(request.POST or None, request=request)
    form.EXTRA_INFO = f"""<strong>Atenção</strong>: Confirme a solicitação de alteração de senha, respondendo o captcha
    abaixo. Você receberá um e-mail em <strong>{email}</strong> com as instruções para criar uma nova senha. Se não receber
    o e-mail, verifique sua caixa de spam ou lixo eletrônico."""
    if form.is_valid():
        obj = TrocarSenha.objects.create(username=request.user.username)
        obj.enviar_email()
        return httprr('/comum/minha_conta/', f'Foi enviado um email para {obj.email} com as instruções para realizar a mudança de senha.')

    return locals()


@rtr()
def solicitar_trocar_senha(request):
    title = 'Alterar senha'
    category = 'Acessos'
    icon = 'key'
    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    form = SoliticarTrocarSenhaForm(request.POST or None)
    if form.is_valid():
        try:
            obj = TrocarSenha.objects.create(username=form.cleaned_data['username'])
        except ValueError:
            # Sem e-mail pessoal cadastrado: a recuperação só vai para o pessoal (nunca o institucional).
            return httprr(
                '/',
                'Você não possui um e-mail pessoal cadastrado para receber as instruções de troca de senha. '
                'Entre em contato com o setor de Gestão de Pessoas (servidores) ou com a secretaria acadêmica (alunos) para cadastrá-lo.',
                tag='error',
            )
        obj.enviar_email()
        return httprr('/', f'Foi enviado um email para {obj.email} com as instruções para realizar a mudança de senha.')
    return locals()


@rtr()
def trocar_senha(request, username, token):
    title = f'Efetuar mudança de senha do usuário {username}'
    if not TrocarSenha.token_valido(username, token):
        messages.error(request, 'Token inválido. Preencha o fomulário abaixo para cadastrar uma nova senha.')
        return httprr('/comum/solicitar_trocar_senha/')

    form = TrocarSenhaForm(request.POST or None, username=username)
    if form.is_valid():
        TrocarSenha.expirar_token(username, token)
        return httprr('/', 'Senha alterada com sucesso.')

    return locals()


#####################################
# Gerenciamento de grupos
#####################################
APP_GROUP_DICT = {}
APP_NAMES_DICT = {}


@rtr()
@login_required()
def grupos_usuarios(request):
    title = 'Grupos de Usuários'

    current_app = request.GET.get('modulo') or None
    campus = request.GET.get('campus') or None
    grupo_escolhido_pk = request.GET.get('grupo') or None

    campus_choices = UnidadeOrganizacional.objects.uo().all()
    grupos_gerenciados = None
    usuarios_grupo = None
    usuarios = User.objects.none()
    contador_dict = {}
    apps = {}
    apps_names = {}

    for app in settings.INSTALLED_APPS_SUAP:
        grupos_da_app = GroupPermission.obter_grupos_por_app_yaml(app)
        if grupos_da_app:
            # `discard`: o grupo gerenciador pode não existir para a app (ver #17387).
            grupos_da_app.discard(GerenciamentoGrupo.NOME_GRUPO_GERENCIADOR_FORMAT.format(app))

            apps[app] = grupos_da_app
            apps_names[apps_django.get_app_config(app).get_full_name()] = app

    grupos_gerenciados = Group.objects.all()
    automatizacoes_grupo = None
    apps = collections.OrderedDict(sorted(apps.items()))
    apps_names = collections.OrderedDict(sorted(apps_names.items()))
    url_filters = '?'
    if any([campus, current_app]):
        if current_app:
            url_filters += f'modulo={current_app}&'

        if campus:
            url_filters += f'campus={campus}&'

        if current_app and grupos_gerenciados:
            grupos_gerenciados = grupos_gerenciados.filter(name__in=apps[current_app])
        if (current_app and campus) and grupos_gerenciados:
            grupos_gerenciados = grupos_gerenciados.filter(user__vinculo__setor__uo__sigla=campus)
            usuarios = usuarios.filter(vinculo__setor__uo__sigla=campus).distinct()

        if list(apps.keys()):
            if current_app and grupos_gerenciados.exists():
                grupos_gerenciados = grupos_gerenciados.distinct()
                if grupo_escolhido_pk and grupo_escolhido_pk.isdigit():
                    grupo_escolhido = grupos_gerenciados.filter(pk=int(grupo_escolhido_pk)).first()
                else:
                    grupo_escolhido = grupos_gerenciados[0]

                if not grupo_escolhido:
                    return httprr('.', 'Grupo escolhido não existe', 'error')

                grupos_gerenciados_pelo_grupo_escolhido = GerenciamentoGrupo.get_grupos_gerenciados_por(grupo_escolhido)
                grupos_que_gerenciam_grupo_escolhido = GerenciamentoGrupo.get_grupos_que_gerenciam(grupo_escolhido)

                for grupo in grupos_gerenciados:
                    qs = grupo.user_set.filter(is_active=True)
                    if campus:
                        qs = qs.filter(vinculo__setor__uo__sigla=campus)
                    contador_dict[grupo] = qs.count()

                usuarios_grupo = grupo_escolhido.usuariogrupo_set.filter(user__is_active=True)
                automatizacoes_grupo = ConfiguracaoAutomatizacaoGrupo.objects.filter(grupo_id=grupo_escolhido.pk)
                if request.method == 'GET':
                    if campus:
                        usuarios_grupo = usuarios_grupo.filter(user__vinculo__setor__uo__sigla=campus)
                ultimo_historico = HistoricoUsuarioGrupo.objects.filter(
                    usuario=OuterRef('user'),
                    grupo=OuterRef('group'),
                    operacao='I',  # I para inclusão
                    removido_em__isnull=True,
                ).order_by('-incluido_em')
                usuarios_grupo = usuarios_grupo.annotate(
                    ultimo_motivo=Subquery(ultimo_historico.values('motivo')[:1]),
                    eh_estagiario=Exists(
                        Servidor.objects.filter(
                            pk=OuterRef('user__vinculo__id_relacionamento'),
                            situacao__codigo__in=Situacao.situacoes_siape_estagiarios(),
                        )
                    ),
                )
                usuarios_grupo = usuarios_grupo.select_related(
                    'user', 'user__vinculo', 'user__vinculo__pessoa', 'user__vinculo__pessoa__pessoafisica'
                ).order_by('user__first_name', 'user__last_name')

    return locals()


@rtr()
@login_required()
def visualizar_menus_do_grupo(request, grupo_pk):
    grupo_escolhido = get_object_or_404(Group, pk=grupo_pk)
    title = f'Menus Visíveis para Grupo: {grupo_escolhido}'

    modulos = grupo_escolhido.permissions.values_list('content_type__app_label', flat=True).distinct('content_type__app_label')
    set_permissions = set()
    for permissao in grupo_escolhido.permissions.all():
        set_permissions.add(f'{permissao.content_type.app_label}.{permissao.codename}')

    retorno = []
    for modulo in modulos:
        if exists(modulo + '/menu.yaml'):
            menu = yaml.safe_load(open(modulo + '/menu.yaml'))
            for key in menu:
                permissions_required = menu[key].get('permissions_required')
                if permissions_required:
                    per = set(permissions_required)
                    if set_permissions.intersection(per):
                        retorno.append({'menu': key, 'url': menu[key]['url']})

                groups_required = menu[key].get('groups_required')
                if groups_required and str(grupo_escolhido) in groups_required:
                    retorno.append({'menu': key, 'url': menu[key]['url']})
    if len(retorno) > 1:
        retorno = sorted(retorno, key=lambda d: d['menu'])
    return locals()


@rtr()
@login_required()
def automatizacao_grupo_listar(request, grupo_pk):
    grupo = get_object_or_404(Group, pk=grupo_pk)
    if not request.user.eh_gerenciador_do_grupo(grupo):
        raise PermissionDenied('Você não tem permissão para automatizar grupos em setores.')
    title = f'Automatização do grupo {grupo} em setores'
    lista = ConfiguracaoAutomatizacaoGrupo.objects.filter(grupo_id=grupo.pk)
    return locals()


@rtr()
@login_required()
def automatizacao_grupo_gerenciar(request, grupo_pk, configuracao_automatizacao_grupo_pk=None):
    """
    View para gerenciar automatização de grupos.
    """
    grupo = get_object_or_404(Group, pk=grupo_pk)
    if not request.user.eh_gerenciador_do_grupo(grupo):
        raise PermissionDenied('Você não tem permissão para automatizar grupos em setores.')

    configuracao_automatizacao_grupo = None
    if configuracao_automatizacao_grupo_pk:
        configuracao_automatizacao_grupo = get_object_or_404(ConfiguracaoAutomatizacaoGrupo, pk=configuracao_automatizacao_grupo_pk)
        title = f'Atualizar automatização do grupo {grupo} em setores'
    else:
        title = f'Adicionar automatização do grupo {grupo} em setores'

    form = ConfiguracaoAutomatizacaoGrupoForm(request.POST or None, grupo=grupo, instance=configuracao_automatizacao_grupo)

    if form.is_valid():
        confirmacao = form.cleaned_data.get('confirmacao')
        if confirmacao:
            with transaction.atomic():
                _nova_configuracao, analise = form.processar(request)

            users_to_update = set()
            for user in analise.get('serao_removidos', []):
                users_to_update.add(user)
            # for user in analise.get('serao_adicionados', []):
            #     users_to_update.add(user)
            # Força o logout dos usuários que foram removidos e adicionados
            # para que eles tenham acesso ao novo grupo
            for user in users_to_update:
                remote_logout_user(user.username)
            messages.success(request, 'Automatização de grupo em setores realizada com sucesso.')
            return redirect('automatizacao_grupo_listar', grupo_pk=grupo.pk)

    context = {
        'title': title,
        'form': form,
        'grupo': grupo,
        'configuracao_automatizacao_grupo': configuracao_automatizacao_grupo,
    }

    return render(request, 'automatizacao_grupo_gerenciar.html', context)


@rtr()
@login_required()
def gerenciamento_grupo(request):
    title = 'Gerenciamento de grupos'

    # filtro por Nome/Sobrenome do servidor
    usuario = request.GET.get('usuario') or None
    current_app = request.GET.get('modulo') or None
    campus = request.GET.get('campus') or None
    grupo_escolhido_pk = request.GET.get('grupo') or None

    campus_choices = UnidadeOrganizacional.objects.suap().all()
    grupos_gerenciados = None
    usuarios_grupo = UsuarioGrupo.objects.none()
    usuarios = User.objects.none()
    contador_dict = {}
    apps_names = {}

    if not GerenciamentoGrupo.user_can_manage(request.user):
        raise PermissionDenied

    if not APP_GROUP_DICT or not APP_NAMES_DICT:
        for app in settings.INSTALLED_APPS_SUAP:
            grupos_da_app = GroupPermission.obter_grupos_por_app_yaml(app)
            if grupos_da_app:
                # Adição do grupo gerenciador que é criado automaticamente
                APP_GROUP_DICT[app] = grupos_da_app
                APP_NAMES_DICT[apps_django.get_app_config(app).get_full_name()] = app
    if request.user.is_superuser:
        grupos_gerenciados = Group.objects.all()
        apps = APP_GROUP_DICT
        apps_names = APP_NAMES_DICT
    else:
        grupos_gerenciados = Group.objects.filter(
            pk__in=GerenciamentoGrupo.objects.filter(grupo_gerenciador__in=request.user.groups.all()).values('grupos_gerenciados')
        )

        apps = {}
        if grupos_gerenciados.exists():
            for g in grupos_gerenciados:
                for app in list(APP_GROUP_DICT.keys()):
                    if g.name in APP_GROUP_DICT[app]:
                        if app not in apps:
                            apps[app] = []
                        apps[app].append(g.name)
                        apps_names[apps_django.get_app_config(app).get_full_name()] = app

    apps = collections.OrderedDict(sorted(apps.items()))
    automatizacoes_grupo = None
    apps_names = collections.OrderedDict(sorted(apps_names.items()))
    url_filters = '?'
    if any([usuario, campus, current_app]):
        if usuario:
            usuarios = User.objects.filter(username=usuario)
            if not usuarios.exists():
                usuarios = User.objects.filter(
                    (Q(vinculo__pessoa__pessoafisica__nome__icontains=usuario) | Q(username__icontains=usuario)) & Q(usuariogrupo__isnull=False)
                ).distinct()
            url_filters += f'usuario={usuario}&'

        if current_app:
            url_filters += f'modulo={current_app}&'

        if campus:
            url_filters += f'campus={campus}&'

        if current_app and grupos_gerenciados:
            grupos_gerenciados = grupos_gerenciados.filter(name__in=apps.get(current_app, []))
        if current_app and usuario and grupos_gerenciados:
            qs_nome = grupos_gerenciados.filter(
                reduce(operator.and_, (Q(user__vinculo__pessoa__nome__icontains=item) for item in usuario.split(' ')))
            )
            qs_username = grupos_gerenciados.filter(user__username__icontains=usuario)
            grupos_gerenciados = (qs_nome | qs_username).distinct()
        if (usuario and campus) or (current_app and campus) and grupos_gerenciados:
            grupos_gerenciados = grupos_gerenciados.filter(user__vinculo__setor__uo__sigla=campus)
            usuarios = usuarios.filter(vinculo__setor__uo__sigla=campus).distinct()

        if list(apps.keys()):
            if current_app and grupos_gerenciados.exists():
                grupos_gerenciados = grupos_gerenciados.distinct()
                if grupo_escolhido_pk and grupo_escolhido_pk.isdigit():
                    grupo_escolhido = grupos_gerenciados.filter(pk=int(grupo_escolhido_pk)).first()
                else:
                    grupo_escolhido = grupos_gerenciados[0]

                    # exclui os superadmin`s das listagens dos grupos (exceto quando o usuário logado for superadmin)
                grupos_gerenciados_pelo_grupo_escolhido = GerenciamentoGrupo.get_grupos_gerenciados_por(grupo_escolhido)
                grupos_que_gerenciam_grupo_escolhido = GerenciamentoGrupo.get_grupos_que_gerenciam(grupo_escolhido)
                for grupo in grupos_gerenciados:
                    qs = grupo.user_set.all()
                    if usuario:
                        qs_nome = qs.filter(reduce(operator.and_, (Q(vinculo__pessoa__nome__icontains=item) for item in usuario.split(' '))))
                        qs_username = qs.filter(username__icontains=usuario)
                        qs = (qs_nome | qs_username).distinct()
                    if campus:
                        qs = qs.filter(vinculo__setor__uo__sigla=campus)
                    contador_dict[grupo] = qs.count()
                if grupo_escolhido:
                    automatizacoes_grupo = ConfiguracaoAutomatizacaoGrupo.objects.filter(grupo_id=grupo_escolhido.pk)
                    usuarios_grupo = grupo_escolhido.usuariogrupo_set.filter(user__is_active=True)

                usuarios_grupo_qs = usuarios_grupo
                if request.method == 'GET':
                    if usuario:
                        usuarios_grupo_qs = usuarios_grupo_qs.filter(
                            reduce(operator.and_, (Q(user__vinculo__pessoa__nome__icontains=item) for item in usuario.split(' ')))
                        )
                        username_grupo_qs = usuarios_grupo.filter(user__username__icontains=usuario)
                        usuarios_grupo = usuarios_grupo_qs | username_grupo_qs
                    if campus:
                        usuarios_grupo = usuarios_grupo.filter(user__vinculo__setor__uo__sigla=campus)
                ultimo_historico = HistoricoUsuarioGrupo.objects.filter(
                    usuario=OuterRef('user'),
                    grupo=OuterRef('group'),
                    operacao='I',  # I para inclusão
                    removido_em__isnull=True,
                ).order_by('-incluido_em')
                usuarios_grupo = usuarios_grupo.annotate(
                    ultimo_motivo=Subquery(ultimo_historico.values('motivo')[:1]),
                    eh_estagiario=Exists(
                        Servidor.objects.filter(
                            pk=OuterRef('user__vinculo__id_relacionamento'),
                            situacao__codigo__in=Situacao.situacoes_siape_estagiarios(),
                        )
                    ),
                )
                usuarios_grupo = usuarios_grupo.select_related(
                    'user', 'user__vinculo', 'user__vinculo__pessoa', 'user__vinculo__pessoa__pessoafisica'
                ).order_by('user__vinculo__pessoa__nome_usual')
                gerenciamento_do_grupo_eh_local = False
                if not request.user.gerenciamento_do_grupo(grupo_escolhido).filter(eh_local=False).exists():
                    gerenciamento_do_grupo_eh_local = True

                apps_com_vinculacao_setores = ['edu', 'etep']
                pode_vincular_setores = False
                if current_app in apps_com_vinculacao_setores:
                    pode_vincular_setores = True
    return locals()


@rtr()
@login_required()
def adicionar_usuario_grupo(request, pk_grupo):
    title = 'Adicionar Usuário ao Grupo'
    grupo = get_object_or_404(Group, pk=pk_grupo)
    if not request.user.eh_gerenciador_do_grupo(grupo):
        raise PermissionDenied('Você não tem permissão para adicionar um usuário nesse grupo.')

    so_local = False
    if not request.user.gerenciamento_do_grupo(grupo).filter(eh_local=False).exists():
        so_local = True
    FormClass = AdicionarUsuarioGrupoFormFactory(request.user, so_local, grupo)
    form = FormClass(data=request.POST or None)
    if form.is_valid():  # somente se for POST
        for user in form.cleaned_data['user']:
            motivo = f'Adicionado(a) ao grupo {grupo}. Motivo: {form.cleaned_data["motivo"]}.'
            if form.cleaned_data.get('prazo'):
                motivo += f'Prazo: {form.cleaned_data["prazo"].strftime("%d/%m/%Y")}'
            HistoricoUsuarioGrupo.objects.create(
                usuario=user, grupo=grupo, operacao='I', motivo=motivo, prazo=form.cleaned_data['prazo'], incluido_por=request.user
            )
            user.groups.add(grupo)
        return httprr('..', 'Usuário(s) adicionado(s) com sucesso.')

    return locals()


@rtr()
@login_required()
def adicionar_setor_usuario_grupo(request, pk_usuario_grupo):
    title = 'Vincular Setores'
    usuario_grupo = UsuarioGrupo.objects.get(pk=pk_usuario_grupo)
    url_origem = request.META.get('HTTP_REFERER')
    if not request.user.eh_gerenciador_do_grupo(usuario_grupo.group):
        raise PermissionDenied('Você não tem permissão para Vincular Setores nesse grupo.')

    FormClass = VincularSetorUsuarioGrupoFormFactory(usuario_grupo)
    form = FormClass(data=request.POST or None)
    if form.is_valid():
        setores_atuais = usuario_grupo.setores.all()
        for setor_atual in setores_atuais:
            if setor_atual not in form.cleaned_data['setores']:
                registro = UsuarioGrupoSetor.objects.filter(usuario_grupo=usuario_grupo, setor=setor_atual)
                registro.delete()

        for setor_form in form.cleaned_data['setores']:
            if setor_form not in setores_atuais:
                registro = UsuarioGrupoSetor()
                registro.usuario_grupo = usuario_grupo
                registro.setor = setor_form
                registro.save()

        return httprr(url_origem, 'Setores vinculados com sucesso.', close_popup=True)
    return locals()


@rtr()
@login_required()
def remover_usuario_grupo(request, pk_usuario_grupo):
    ug = get_object_or_404(UsuarioGrupo, pk=pk_usuario_grupo)
    grupo = ug.group
    usuario = ug.user
    usuario_logado = request.user
    sou_eu_mesmo = usuario_logado == usuario
    if not request.user.eh_gerenciador_do_grupo(grupo) and not sou_eu_mesmo:
        raise PermissionDenied('Você não tem permissão para remover um usuário nesse grupo.')
    if (
        not sou_eu_mesmo
        and not request.user.gerenciamento_do_grupo(grupo).filter(eh_local=False).exists()
        and (usuario.get_relacionamento().setor and request.user.get_relacionamento().setor.uo != usuario.get_relacionamento().setor.uo)
    ):
        raise PermissionDenied(
            f'Você não tem permissão para remover um usuário nesse grupo que não seja {nomenclatura.do_campus}: {request.user.get_relacionamento().setor.uo}.'
        )

    with transaction.atomic():
        ug.setores.clear()  # Avalie se isso dispara sinais; se sim, trate similarmente.
        # Remoção direta sem disparar sinais
        User.groups.through.objects.filter(user_id=usuario.id, group_id=grupo.id).delete()
        ug.delete()

    retorno = request.META.get('HTTP_REFERER', '..')
    if sou_eu_mesmo:
        retorno = '/comum/minha_conta/'
    elif '/remover_usuario_grupo/' in request.META.get('HTTP_REFERER', '..'):
        retorno = 'comum/gerenciamento_grupo/'
    return httprr(retorno, f'Usuário foi removido do grupo {grupo} com sucesso.')


@rtr()
@login_required()
def comentario_add(request, aplicacao, modelo, objeto_id, resposta_id=None):
    title = 'Adicionar Comentário'
    form = ComentarioForm(request.POST or None)
    if request.method == 'POST':
        form = ComentarioForm(request.POST)
        if form.is_valid():
            content_type = ContentType.objects.get(app_label=aplicacao.lower(), model=modelo.lower())
            comentario = Comentario.objects.create(
                texto=form.cleaned_data['texto'], content_type=content_type, object_id=objeto_id, resposta_id=resposta_id
            )
            return httprr('..', 'Comentário adicionado com sucesso.')
    return locals()


@rtr()
@login_required()
def comentario_desconsiderar(request, comentario_id):
    comentario = get_object_or_404(Comentario, pk=comentario_id)

    if comentario.desconsiderado or request.user != comentario.cadastrado_por:
        raise PermissionDenied

    comentario.desconsiderado = True
    comentario.save()
    if request.GET.get('_popup'):
        url = '..'
    else:
        url = request.META.get('HTTP_REFERER', '..')

    return httprr(url, 'Comentário desconsiderado com sucesso.')


@rtr()
@permission_required('comum.add_solicitacaoreservasala')
def sala_visualizar(request, sala_pk):
    sala = get_object_or_404(Sala, pk=sala_pk)
    title = sala
    eh_avaliador = sala.eh_avaliador(request.user)
    return locals()


@rtr()
@permission_required('comum.add_solicitacaoreservasala')
def sala_solicitar_reserva(request, sala_pk):
    solicitacao = SolicitacaoReservaSala()
    sala = get_object_or_404(Sala, pk=sala_pk)
    title = f'Solicitar Reserva: {sala}'
    if not sala.pode_agendar(request.user):
        raise PermissionDenied('Acesso negado.')

    if not sala.is_agendavel():
        msg = 'Sala não está disponível para agendamento.'
        if not sala.avaliadores_de_agendamentos.exists():
            msg = 'Sala não está disponível para agendamento, pois não tem avaliadores.'

        return httprr(request.META.get('HTTP_REFERER', '..'), msg, tag='error')

    calendario = sala.programacao_atual()
    solicitacao.sala = sala
    solicitacao.solicitante = request.user
    solicitacao.data_solicitacao = datetime.now()
    if request.GET.get('solicitacao'):
        solicitacao_clonada = get_object_or_404(SolicitacaoReservaSala, pk=request.GET.get('solicitacao'))
        solicitacao.recorrencia = solicitacao_clonada.recorrencia
        solicitacao.data_inicio = solicitacao_clonada.data_inicio
        solicitacao.data_fim = solicitacao_clonada.data_fim
        solicitacao.hora_inicio = solicitacao_clonada.hora_inicio
        solicitacao.hora_fim = solicitacao_clonada.hora_fim
        solicitacao.justificativa = solicitacao_clonada.justificativa

        form = SolicitacaoReservaSalaForm(
            request.POST or None,
            instance=solicitacao,
            files=request.FILES or None,
            initial={'interessados_vinculos': solicitacao_clonada.interessados_vinculos.all()},
            request=request,
        )
    else:
        solicitacao.recorrencia = SolicitacaoReservaSala.RECORRENCIA_EVENTO_UNICO
        form = SolicitacaoReservaSalaForm(request.POST or None, instance=solicitacao, files=request.FILES or None, request=request)

    if form.is_valid():
        form.save()
        msg = 'Solicitação realizada com sucesso.'
        return httprr('/admin/comum/solicitacaoreservasala/', msg)

    return locals()


@rtr()
@permission_required('comum.view_solicitacaoreservasala')
def sala_agenda_atual(request, sala_pk):
    sala = get_object_or_404(Sala, pk=sala_pk)
    calendario = sala.programacao_atual()
    return locals()


@permission_required('comum.view_solicitacaoreservasala')
def sala_informacoes_complementares(request, sala_pk):
    sala = get_object_or_404(Sala, pk=sala_pk)
    return HttpResponse(sala.informacoes_complementares or '')


@rtr()
@permission_required('comum.view_solicitacaoreservasala')
def sala_ver_solicitacao(request, solicitacao_reserva_pk):
    solicitacao = get_object_or_404(SolicitacaoReservaSala, pk=solicitacao_reserva_pk)
    title = f'Solicitação de Reserva de Sala #{solicitacao.pk}'
    if not solicitacao.pode_ver(request.user):
        raise PermissionDenied

    eh_avaliador = solicitacao.sala.eh_avaliador(request.user)
    reservas = solicitacao.reservasala_set.order_by('data_inicio')
    calendario = solicitacao.sala.programacao_atual(solicitacao)
    return locals()


@require_POST
@permission_required('comum.delete_solicitacaoreservasala')
def sala_excluir_solicitacao(request: HttpRequest, solicitacao_reserva_pk: int) -> HttpResponse:
    solicitacao = get_object_or_404(SolicitacaoReservaSala, pk=solicitacao_reserva_pk)
    if not solicitacao.pode_excluir(request.user):
        raise PermissionDenied

    solicitacao.status = SolicitacaoReservaSala.STATUS_EXCLUIDA
    solicitacao.save()
    return httprr('/admin/comum/solicitacaoreservasala/', 'Reserva de Sala excluída com sucesso.')


@rtr()
@permission_required('comum.pode_avaliar_solicitacao_reserva_de_sala')
def sala_avaliar_solicitacao(request, solicitacao_reserva_pk):
    title = 'Avaliar Agendamento de Sala'
    solicitacao = get_object_or_404(SolicitacaoReservaSala, pk=solicitacao_reserva_pk)
    if not solicitacao.pode_avaliar(request.user):
        raise PermissionDenied

    solicitacao.avaliador = request.user
    solicitacao.data_avaliacao = datetime.now()
    form = SolicitacaoReservaSalaAvaliarForm(request.POST or None, instance=solicitacao)
    if form.is_valid():
        form.save()
        return httprr('..', 'Avaliação realizada com sucesso.')

    return locals()


@rtr()
@login_required()
def sala_cancelar_solicitacao(request: HttpRequest, solicitacao_reserva_pk: int) -> HttpResponse | dict:
    title = 'Cancelar Agendamento de Sala'
    solicitacao = get_object_or_404(SolicitacaoReservaSala, pk=solicitacao_reserva_pk)
    if not solicitacao.pode_cancelar(request.user):
        raise PermissionDenied

    solicitacao.data_cancelamento = datetime.now()
    solicitacao.status = SolicitacaoReservaSala.STATUS_INDEFERIDA
    form = SolicitacaoReservaSalaCancelarForm(request.POST or None, instance=solicitacao, request=request)
    if form.is_valid():
        form.instance.cancelada_por = request.user.get_vinculo()
        form.save()
        return httprr('..', 'Cancelamento realizado com sucesso.')

    return locals()


@rtr()
@permission_required('comum.view_indisponibilizacaosala')
def sala_listar_indisponibilizacoes(request):
    title = 'Registros de Indisponibilizações de Salas'
    eh_avaliador = Sala.eh_avaliador_salas(request.user)
    qualquer = IndisponibilizacaoSala.objects.all()
    em_manutencao = IndisponibilizacaoSala.em_andamento.all()
    tab = request.GET.get('tab')
    if tab == 'qualquer':
        indisponibilizacoes = qualquer
    elif tab == 'em_manutencao':
        indisponibilizacoes = em_manutencao
    else:
        tab = 'qualquer'
        indisponibilizacoes = qualquer

    params = request.GET.dict()
    if 'order_by' in params:
        order_params = params.pop('order_by', '').split('-')
        order_str = order_params[0]
        order_sign = ''
        if len(order_params) > 1:
            order_str = order_params[1]
            order_sign = '-'

        if order_str == 'sala':
            indisponibilizacoes = indisponibilizacoes.order_by(f'{order_sign}sala')
        elif order_str == 'periodo':
            indisponibilizacoes = indisponibilizacoes.order_by(f'{order_sign}data_inicio')

    params = urllib.parse.urlencode(params)
    form = IndisponibilizacaoSalaBuscarForm(request.GET or None, indisponibilizacoes=indisponibilizacoes)
    indisponibilizacoes = form.processar(indisponibilizacoes)
    indisponibilizacoes = indisponibilizacoes.order_by('id')
    return locals()


@rtr()
@permission_required('comum.view_indisponibilizacaosala')
def sala_indicadores(request):
    title = 'Indicadores'
    agendaveis = Sala.objects.filter(agendavel=True)

    form = SalaIndicadoresForm(request.GET or None, request=request, initial={'campus': get_uo(request.user).id})

    if form.is_valid():
        salas = []

        inicio = None
        if form.cleaned_data.get('inicio'):
            inicio = form.cleaned_data['inicio']

        final = None
        if form.cleaned_data.get('final'):
            final = form.cleaned_data['final']

        campus = None
        if form.cleaned_data.get('campus'):
            campus = form.cleaned_data['campus']

        predio = None
        if form.cleaned_data.get('predio'):
            predio = form.cleaned_data['predio']
            agendaveis = agendaveis.filter(predio=predio)

        dias = (final - inicio).days
        agendaveis = agendaveis.filter(predio__uo=campus)

        for sala in agendaveis:
            reservas = ReservaSala.deferidas.filter(sala=sala, data_inicio__gte=inicio, data_fim__lte=final)
            qtd_canceladas = ReservaSala.objects.filter(sala=sala, data_inicio__gte=inicio, data_fim__lte=final, cancelada=True).count()
            qtd_ocorreu = reservas.filter(ocorreu=True).count()
            qtd_nao_ocorreu = reservas.filter(ocorreu=False).count()
            qtd_desconhecido = reservas.filter(ocorreu=None).count()
            duracao = 0
            for reserva in reservas:
                duracao += (reserva.data_fim - reserva.data_inicio).total_seconds()

            tempo_medio = reservas.exists() and duracao / 3600 / dias or 0
            salas.append([sala, tempo_medio, qtd_canceladas, qtd_ocorreu, qtd_nao_ocorreu, qtd_desconhecido])

        salas = sorted(salas, key=lambda tempo_medio: tempo_medio[1])
    return locals()


@rtr()
@permission_required('comum.add_indisponibilizacaosala')
def sala_registrar_indisponibilizacao(request, sala_pk=None):
    title = 'Indisponibilizar Sala'
    eh_avaliador = Sala.eh_avaliador_salas(request.user)
    if not eh_avaliador:
        raise PermissionDenied

    indisponibilizacao = IndisponibilizacaoSala()
    sala = None
    if sala_pk:
        sala = get_object_or_404(Sala, pk=sala_pk)
        if not sala.eh_avaliador(request.user):
            raise PermissionDenied
        indisponibilizacao.sala = sala
        calendario = sala.programacao_atual()

    indisponibilizacao.usuario = request.user
    indisponibilizacao.data = datetime.now()
    form = RegistrarIndisponibilizacaoSalaForm(request.POST or None, instance=indisponibilizacao, request=request)
    if form.is_valid():
        sala = form.cleaned_data.get('sala', None)
        if sala and not sala.eh_avaliador(request.user):
            raise PermissionDenied
        form.save()
        return httprr('..', 'Cadastro realizado com sucesso.')

    return locals()


@rtr()
@permission_required('comum.view_indisponibilizacaosala')
def sala_ver_indisponibilizacao(request, indisponibilizacao_pk):
    title = 'Visualizar Registro de Indisponibilização'
    indisponibilizao = get_object_or_404(IndisponibilizacaoSala, pk=indisponibilizacao_pk)
    calendario = indisponibilizao.sala.programacao_atual()
    return locals()


@require_POST
@permission_required('comum.delete_indisponibilizacaosala')
def sala_excluir_indisponibilizacao(request: HttpRequest, indisponibilizacao_pk: int) -> HttpResponse:
    indisponibilizao = get_object_or_404(IndisponibilizacaoSala, pk=indisponibilizacao_pk)
    if not indisponibilizao.pode_excluir(request.user):
        raise PermissionDenied

    indisponibilizao.delete()
    return httprr('/comum/sala/listar_indisponibilizacoes/', 'Indisponibilização removida com sucesso.')


@rtr()
@permission_required('comum.view_solicitacaoreservasala')
def sala_cancelar_reserva(request, reserva_pk):
    reserva = get_object_or_404(ReservaSala, pk=reserva_pk)
    user = request.user
    if not reserva.pode_cancelar(user):
        raise PermissionDenied

    reserva.cancelada_por = user
    form = ReservaSalaCancelarForm(request.POST or None, instance=reserva)
    if form.is_valid():
        form.cancelar()
        return httprr('..', 'Cancelamento realizado com sucesso.')

    return locals()


@rtr()
@permission_required('comum.view_solicitacaoreservasala')
def sala_informar_ocorrencia_reserva(request, reserva_pk):
    reserva = get_object_or_404(ReservaSala, pk=reserva_pk)
    user = request.user
    if not reserva.sala.eh_avaliador(user):
        raise PermissionDenied

    reserva.cancelada_por = user
    form = ReservaInformarOcorrenciaForm(request.POST or None, instance=reserva)
    if form.is_valid():
        form.save()
        return httprr('..', 'Operação realizada com sucesso.')

    return locals()


@rtr()
@permission_required('comum.view_solicitacaoreservasala')
def sala_cancelar_reservas_periodo(request, sala_pk):
    title = 'Cancelar Reservas por Período'
    sala = get_object_or_404(Sala, pk=sala_pk)
    user = request.user
    if not sala.eh_avaliador(user):
        raise PermissionDenied

    calendario = sala.programacao_atual()
    form = CancelarReservasPeriodoForm(request.POST or None, request=request, sala=sala)
    if form.is_valid():
        form.cancelar()
        return httprr('..', 'Cancelamento realizado com sucesso.')

    return locals()


@rtr()
@permission_required('comum.view_solicitacaoreservasala')
def deferir_reserva_diario(request, diario_pk, dh_inicio, dh_fim):
    Diario = apps.get_model('edu', 'Diario')
    hoje = datetime.now()

    diario = get_object_or_404(Diario, pk=diario_pk)
    sala = diario.local_aula
    solicitante = request.user
    #
    # verificando se o usuário pode agendar
    if sala.pode_agendar(solicitante):
        data_hora_inicio = datetime.strptime(dh_inicio, '%Y-%m-%d_%H-%M')
        data_inicio = data_hora_inicio.date()
        hora_inicio = data_hora_inicio.time()

        data_hora_fim = datetime.strptime(dh_fim, '%Y-%m-%d_%H-%M')
        data_fim = data_hora_fim.date()
        hora_fim = data_hora_fim.time()

        justificativa = (
            f'Diário ({diario.id}) - {diario.componente_curricular.componente.sigla} - {diario.componente_curricular.componente.descricao}'
        )
        recorrencia = SolicitacaoReservaSala.RECORRENCIA_EVENTO_UNICO

        solicitacao = SolicitacaoReservaSala.objects.get_or_create(
            sala=sala,
            solicitante=solicitante,
            data_solicitacao=hoje,
            data_inicio=data_inicio,
            hora_inicio=hora_inicio,
            data_hora_inicio=data_hora_inicio,
            data_fim=data_fim,
            hora_fim=hora_fim,
            data_hora_fim=data_hora_fim,
            recorrencia=recorrencia,
            justificativa=justificativa,
            status=SolicitacaoReservaSala.STATUS_DEFERIDA,
        )[0]
        solicitacao.gerar_reservas()
        solicitacao.data_avaliacao = hoje
        solicitacao.avaliador = solicitante
        solicitacao.save()

        return httprr(request.META.get('HTTP_REFERER', '..'), 'Reserva de sala realizada com sucesso.')
    else:
        return httprr(request.META.get('HTTP_REFERER', '..'), f'Você não tem permissão para reservar a sala {sala}.', tag='error')


@rtr()
@permission_required('comum.view_solicitacaoreservasala')
def deferir_reserva_diario_no_periodo(request, diario_pk):
    try:
        Diario = apps.get_model('edu', 'Diario')
        diario = get_object_or_404(Diario, pk=diario_pk)
        title = f'Deferir Reserva: {diario.gerar_justificativa_reserva_sala()}'

        form = DeferirDiarioReservaSalaPeriodo(request.POST or None, diario=diario)
        if form.is_valid():
            form.processar(request)
            return httprr(request.META.get('HTTP_REFERER', '..'), 'Reserva de sala realizada com sucesso.', close_popup=True)
        return locals()
    except Exception as ex:
        return httprr(
            request.META.get('HTTP_REFERER', '..'),
            f'Houve um erro ao tentar cadastrar uma reserva no período informado: {ex}',
            tag='error',
            close_popup=True,
        )


@rtr()
def autenticar_documento(request):
    from edu.models import RegistroEmissaoCertificadoENEM

    title = 'Verificação de Autenticação de Documento'
    category = 'Autenticação de Documentos'
    icon = 'lock'
    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    initial = {
        'tipo': request.GET.get('tipo'),
        'data_emissao': request.GET.get('data_emissao'),
        'codigo_verificador': request.GET.get('codigo_verificador'),
    }
    form = AutenticarDocumentoForm(request.POST or None, initial=initial)
    if form.is_valid():
        # os registros de emissão de certificado de evento foram removidos e a autenticação regera certificado em tempo de execução
        if form.cleaned_data['tipo'] == 'Certificado de Participação em Evento':
            Participante = apps.get_model('eventos.Participante')
            if Participante:
                codigo_geracao_certificado = '{}{}'.format(
                    form.cleaned_data['data_emissao'].strftime('%d%m%Y'), form.cleaned_data['codigo_verificador'][0:7]
                )
                participante_evento = Participante.objects.filter(codigo_geracao_certificado=codigo_geracao_certificado).first()
                if participante_evento:
                    return HttpResponseRedirect(participante_evento.get_url_download_certificado())
        else:
            registro = form.processar()
            if registro and default_storage.exists(registro.documento.name):
                tmp = tempfile.NamedTemporaryFile(delete=False)
                with registro.documento.open('rb') as f:
                    tmp.write(f.read())
                tmp.close()
                assinaturas = signer.verify(tmp.name)

            if registro:
                is_cancelado = registro.cancelado
                if registro.tipo == 'Carteira Funcional Digital':
                    is_carteira_funcional = True
                    servidor = Servidor.objects.get(pk=registro.modelo_pk)
                if registro.tipo == 'Certificado ENEM':
                    if registro.modelo_pk:
                        registro_enem = RegistroEmissaoCertificadoENEM.objects.get(pk=registro.modelo_pk)
                        is_cancelado = registro_enem.cancelado

                        if is_cancelado:
                            responsavel_cancelamento = registro_enem.responsavel_cancelamento
                            data_cancelamento = registro_enem.data_cancelamento
                            razao_cancelamento = registro_enem.razao_cancelamento

                if registro.tipo == 'ENCCEJA':
                    if registro.modelo_pk:
                        from encceja.models import Solicitacao

                        objeto = Solicitacao.objects.filter(pk=registro.modelo_pk).first()
                        if objeto.cancelada:
                            data_cancelamento = objeto.data_cancelamento
                            razao_cancelamento = objeto.motivo_cancelamento

    return locals()


@rtr()
def baixar_documento(request, pk, codigo_verificador):
    registro = get_object_or_404(RegistroEmissaoDocumento, pk=pk, codigo_verificador=codigo_verificador)
    return registro.as_pdf_response()


@rtr()
@login_required()
@group_required('Reitor, Diretor Geral')
def assinar_documento(request: HttpRequest) -> HttpResponse | dict:
    title = 'Assinar Documento'
    form = AssinarDocumentoForm(request=request, data=request.POST or None, files=request.FILES or None)
    if form.is_valid():
        caminho_arquivo = form.processar()
        with open(caminho_arquivo, 'rb') as file:
            return PDFResponse(file.read(), nome='Assinado.pdf')
    return locals()


@rtr()
@login_required()
@permission_required('comum.change_user')
def assinar_documento_icpedu(request):
    title = 'Assinar Documento (ICP EDU)'
    if not APIExterna.ICPEDU.ativo:
        return httprr(
            '..',
            'O serviço de assinatura ICP EDU está temporariamente indisponível para manutenção. Por favor, tente novamente mais tarde.',
            tag='error',
        )
    form = AssinarDocumentoICPEduForm(request=request, data=request.POST or None, files=request.FILES or None)
    if form.is_valid():
        caminho_arquivo = form.processar()
        with open(caminho_arquivo, 'rb') as file:
            return PDFResponse(file.read(), nome='DocumentoAssinado.pdf', anexo=True)
    return locals()


def jwk(request):
    return JsonResponse({'keys': [json.loads(ApiICPEDUService().api_externa.client_id or '{}')]})


@rtr()
@login_required()
@group_required('Reitor, Diretor Geral')
def verificar_documento(request: HttpRequest) -> HttpResponse | dict:
    title = 'Verificar Documento'
    form = VerificarDocumentoForm(request=request, data=request.POST or None, files=request.FILES or None)
    if form.is_valid():
        try:
            assinaturas = form.processar()
        except Exception:
            return httprr(
                '/comum/verificar_documento/',
                'Problema ao tentar verificar a assinatura deste documento. Verifique se o arquivo não está danificado e tente novamente.',
                'error',
            )
        if assinaturas:
            url = '/comum/verificar_documento/'
            return httprr(url, 'Documento assinado digitalmente por {}.'.format(', '.join(assinatura['cn'] for assinatura in assinaturas)))
        else:
            return httprr('..', 'Assinatura digital não identificada.', tag='error')
    return locals()


@rtr()
def validar_assinatura(request):
    title = 'Validar Assinatura Digital'
    category = 'Autenticação de Documentos'
    icon = 'lock'
    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    form = ValidarDocumentoForm(request=request, data=request.POST or None, files=request.FILES or None)
    if form.is_valid():
        try:
            assinaturas = form.processar()
        except Exception:
            return httprr(
                '/comum/validar_assinatura/',
                'Problema ao tentar verificar a assinatura deste documento. Verifique se o arquivo não está danificado e tente novamente.',
                'error',
            )
    return locals()


@login_required()
def retrair_menu(request):
    request.session['retraido'] = True
    return HttpResponse('OK')


@login_required()
def expandir_menu(request):
    request.session['retraido'] = False
    return HttpResponse('OK')


@rtr(two_factor_authentication=True)
@login_required()
def atualizar_email(request, vinculo_pk):
    title = 'Atualização do E-mail'
    vinculo = get_object_or_404(Vinculo, pk=vinculo_pk)
    if not (
        request.user.get_vinculo().pk == int(vinculo_pk)
        or request.user.has_perm('rh.pode_editar_email_secundario_servidor')
        or request.user.has_perm('rh.pode_editar_email_secundario_prestador')
        or request.user.has_perm('rh.pode_editar_email_institucional')
        or request.user.has_perm('rh.pode_editar_email_academico')
        or request.user.has_perm('rh.pode_editar_email_google_classroom')
    ):
        raise PermissionDenied

    relacionamento = vinculo.relacionamento
    form = AtualizarEmailForm(request.POST or None, request=request, relacionamento=relacionamento)
    if form.is_valid():
        form.save()
        url = request.GET.get('next', '..')
        return httprr(url, 'E-mail atualizado com sucesso.')
    return locals()


@rtr()
@login_required()
def excluir(request, app, model, pks):
    from django.contrib.admin.utils import NestedObjects

    try:
        Model = apps_django.get_model(app, model)
    except Exception:
        return httprr('..', 'Impossível excluir registro.', 'error')

    html = []
    pks = pks.split('_')
    objs = Model.objects.filter(pk__in=pks)
    if hasattr(Model, 'locals'):
        objs = Model.locals.filter(pk__in=pks)

    title = 'Confirmação de Exclusão'

    exclude_pks = []
    for obj in objs:
        if hasattr(obj, 'can_delete') and not obj.can_delete(request.user):
            exclude_pks.append(obj.pk)
        objs = objs.exclude(pk__in=exclude_pks)

    has_perm = request.user.has_perm(f'{app}.delete_{model}')
    if not has_perm:
        return httprr('..', 'Você não tem permissão para excluir o(s) registro(s).', 'error')
    else:
        form = ExcluirRegistroForm(data=request.POST or None, request=request)
        if form.is_valid():
            try:
                sid = transaction.savepoint()
                for obj in objs:
                    obj.delete()
                transaction.savepoint_commit(sid)
            except Exception as e:
                transaction.savepoint_rollback(sid)
                capture_exception(e)
                return httprr('..', f'{e!s}', 'error')
            return httprr(request.GET.get('next', '..'), 'Registro(s) excluído(s) com sucesso.')

        collector = NestedObjects('default')
        collector.collect(objs)
        lista = collector.nested()

        def format_html(obj_or_list, has_child=True):
            if isinstance(obj_or_list, list):
                if obj_or_list:
                    html.append('<ul class="obj-tree">')
                    for i, _obj in enumerate(obj_or_list):
                        has_child = i + 1 < len(obj_or_list) and isinstance(obj_or_list[i + 1], list)
                        if has_child:
                            next_list = obj_or_list[i + 1]
                            if next_list and next_list[0]._meta.verbose_name.endswith('relationship'):
                                has_child = False
                        format_html(_obj, has_child)
                    html.append('</ul>')
            else:
                if not obj_or_list._meta.verbose_name.endswith('relationship'):
                    css = has_child and 'obj-tree-toggler expandido' or ''
                    html.append(
                        f'<li><a href="javascript:void(0)" class="{css}"><strong>{obj_or_list._meta.verbose_name} #{obj_or_list.pk}</strong></a> : {obj_or_list!s}</li>'
                    )

        format_html(lista)
    output = ''.join(html)

    return locals()


@login_required()
def popula_nome_sugerido(request):
    # selecionando a pessoa escolhida
    id = request.POST.get('solicitante_vinculo')
    solicitante_escolhido = Vinculo.objects.get(pk=id)
    nome = solicitante_escolhido.pessoa.nome if solicitante_escolhido else ''

    nomes = gera_nomes(nome)
    choice_nomes = [['', 'Selecione umas das opções']]
    for nome in nomes:
        choice_nomes.append([nome, nome])

    return JsonResponse({'nomes': choice_nomes})


@rtr()
@login_required()
def ver_solicitacao_documento(request, solicitacaodocumento_pk):
    solicitacao = get_object_or_404(DocumentoControle, pk=solicitacaodocumento_pk)
    historico = DocumentoControleHistorico.objects.filter(solicitacao=solicitacao).order_by('-data_historico')
    servidor = solicitacao.solicitante_vinculo.relacionamento
    title = f'Solicitação de {servidor}'
    verificacao_propria = request.user == servidor.get_user()
    is_rh = request.user.has_perm('rh.change_servidor')

    pode_atender_solicitacao = solicitacao.pode_atender_solicitacao(request)
    return locals()


@rtr()
@login_required()
@permission_required('comum.change_documentocontrole')
def marcar_solicitacao_atendida(request: HttpRequest, solicitacaodocumento_pk: int) -> HttpResponse:
    url_retorno = request.META.get('HTTP_REFERER')
    if not url_retorno:
        url_retorno = '/admin/comum/documentocontrole/'
    try:
        solicitacao = get_object_or_404(DocumentoControle, pk=solicitacaodocumento_pk)
        # se for do rh, pode marcar a solicitacão como atendida
        if not solicitacao.pode_atender_solicitacao(request):
            return httprr(url_retorno, 'Somente solicitações não atendidas podem ser marcadas como atendidas.', 'error')
        solicitacao.atender_solicitacao(request)
        return httprr(url_retorno, 'Solicitação atendida com sucesso.')
    except Exception:
        return httprr(url_retorno, 'Erro ao marcar a solicitação como atendida.', 'error')


@rtr()
@login_required()
@permission_required('comum.change_documentocontrole')
def rejeitar_solicitacao(request: HttpRequest, solicitacaodocumento_pk: int) -> HttpResponse | dict:
    try:
        solicitacao = get_object_or_404(DocumentoControle, pk=solicitacaodocumento_pk)
        # se for do rh, pode rejeitar a solicitação, desde que ainda não atendida
        if not solicitacao.pode_rejeitar_solicitacao(request):
            return httprr('..', 'Somente solicitações não atendidas podem ser rejeitadas.', 'error')
        title = f'Rejeitar Solicitação:  {solicitacao}'
        form = RejeitarSolicitacaoForm(request.POST or None)
        if form.is_valid():
            solicitacao.rejeitar_solicitacao(request)
            return httprr('..', 'Solicitação rejeitada com sucesso.')
        return locals()
    except Exception:
        return httprr('.', 'Erro ao rejeitar a solicitação.', 'error')


@rtr()
@permission_required('comum.view_pensionista')
def tela_pensionista(request, matricula_pensionista):
    pensionista = get_object_or_404(Pensionista, matricula=matricula_pensionista)
    title = str(pensionista)
    return locals()


@rtr()
@login_required()
def usuario_historico_grupos(request, usuario_id):
    usuario = get_object_or_404(User, pk=usuario_id)
    if request.user != usuario and not GerenciamentoGrupo.user_can_manage(request.user):
        raise PermissionDenied
    title = f'Histórico - {usuario}'
    registros = LogEntry.objects.filter(object_id=usuario.id, action_flag=FLAG_LOG_GERENCIAMENTO_GRUPO).order_by('-action_time')
    return locals()


@login_required()
@csrf_exempt
def atualiza_layout(request):
    if request.POST:
        titulo = request.POST.get('titulo', '').strip().upper()
        if not titulo:
            raise PermissionDenied('Erro')
        try:
            ordem = int(request.POST.get('ordem', -1))
            coluna = int(request.POST.get('coluna', 0))
        except Exception:
            raise PermissionDenied('Erro')

        quadro = IndexLayout.objects.filter(usuario=request.user, quadro_nome=titulo)

        if quadro.exists():
            quadro = quadro[0]
            qs = IndexLayout.objects.filter(usuario=request.user, quadro_coluna=coluna).exclude(id=quadro.id).order_by('quadro_ordem')
            sobe = qs[:ordem]
            desce = qs[ordem:]

            nova_ordem = 0
            for q in sobe:
                q.quadro_ordem = nova_ordem
                q.save()
                nova_ordem += 1

            quadro.quadro_coluna = coluna
            quadro.quadro_ordem = nova_ordem
            quadro.save()

            nova_ordem = nova_ordem + 1
            for q in desce:
                q.quadro_ordem = nova_ordem
                q.save()
                nova_ordem += 1

    IndexLayout.recarregar_layouts(request)

    return HttpResponse('Ok')


@login_required()
@csrf_exempt
def esconder_quadro(request):
    titulo = request.POST.get('titulo', '').strip().upper()
    if not titulo:
        raise PermissionDenied('Erro')
    qs = IndexLayout.objects.select_for_update().filter(usuario=request.user, quadro_nome=titulo)
    i = qs.first()
    if not i:
        i = IndexLayout(quadro_nome=titulo, quadro_coluna=1, quadro_ordem=1, usuario=request.user)
        i.save()
    qs.update(escondido=True)
    IndexLayout.recarregar_layouts(request)
    return HttpResponseRedirect('/')


@login_required()
@csrf_exempt
def marcar_quadro_como_lido(request, hash):
    titulo = request.POST.get('titulo', '').strip().upper()
    if not titulo:
        raise PermissionDenied('Erro')
    IndexLayout.objects.filter(usuario=request.user, quadro_nome=titulo).update(hash_quadros=hash)
    IndexLayout.recarregar_layouts(request)
    return HttpResponseRedirect('/')


@rtr()
@login_required()
def exibir_quadro(request):
    title = 'Gerenciar Quadros'
    form = ExibirQuadrosForm(request.POST or None, request=request, coluna='esquerda')
    if form.is_valid():
        form.processar(request)
        return httprr('..', 'Atualização exibida com sucesso.')
    return locals()


def atualizar_preferencia(usuario, tema=None):
    preferencias = Preferencia.objects.filter(usuario=usuario)
    if not preferencias.exists():
        preferencia = Preferencia()
        preferencia.usuario = usuario
    else:
        preferencia = preferencias[0]
    if tema:
        preferencia.tema = tema
    preferencia.save()

    return locals()


@rtr()
@login_required()
def acessibilidade(request: HttpRequest) -> dict[str, Any]:
    title = 'Acessibilidade'

    preferencia = Preferencia.objects.filter(usuario=request.user)
    if preferencia.exists():
        preferencia = preferencia[0]
    else:
        preferencia = None

    temas_acessibilidade = get_temas()['temas_acessibilidade']

    return locals()


@rtr()
@login_required()
def temas(request):
    title = 'Seleção de Tema'

    preferencia = Preferencia.objects.filter(usuario=request.user)
    if preferencia.exists():
        preferencia = preferencia[0]
    else:
        preferencia = None

    temas = get_temas()
    temas_gerais = temas['temas_gerais']
    temas_gov = temas['temas_gov']
    temas_acessibilidade = temas['temas_acessibilidade']

    return locals()


@rtr()
@login_required()
def alterar_tema(request):
    tema = request.GET.get('theme') or None

    novo_tema = tema if tema in dict(Preferencia.TEMA_CHOICES) else Preferencia.get_tema_padrao_usuario_autenticado()

    request.session['theme'] = novo_tema

    atualizar_preferencia(usuario=request.user, tema=novo_tema)
    return httprr('/comum/temas/', f'Tema alterado para "{Preferencia.get_tema_description(novo_tema)}" com sucesso.')


@rtr()
@login_required()
def minha_conta(request):
    usuario = get_object_or_404(User, pk=request.user.pk)
    permite_autenticacao_duplo_fator = Configuracao.get_valor_por_chave('comum', 'permite_autenticacao_duplo_fator')

    title_usuario = str(usuario)
    autocadastros = None

    if usuario.get_profile():
        title_usuario = str(usuario.get_profile())
        autocadastros = usuario.get_profile().solicitacoes_biometria.all()
        autocadastros = autocadastros.order_by('-data_cadastro')

    title = 'Minha conta'

    historico_grupos_qs = LogEntry.objects.filter(object_id=usuario.id, action_flag=FLAG_LOG_GERENCIAMENTO_GRUPO).order_by('-action_time')[:6]
    historico_grupos = []
    for registro in historico_grupos_qs:
        historico_usuario = registro.user.vinculo.nome_usual if hasattr(registro.user, 'vinculo') else registro.user
        mensagem = registro.change_message
        mensagem_adicao1 = 'Adicionado(a) ao grupo '
        mensagem_adicao2 = 'Adicionado ao grupo '
        mensagem_remocao1 = 'Removido(a) do grupo '
        mensagem_remocao2 = 'Removido do grupo '
        eh_adicao = False
        if mensagem.startswith('Adicionado'):
            eh_adicao = True
            acao = f'Adicionado por {historico_usuario}'
            grupo = mensagem.replace(mensagem_adicao1, '').replace(mensagem_adicao2, '')
        else:
            acao = f'Removido por {historico_usuario}'
            grupo = mensagem.replace(mensagem_remocao1, '').replace(mensagem_remocao2, '')

        historico_grupos.append(
            {
                'eh_adicao': eh_adicao,
                'data': registro.action_time,
                'acao': acao,
                'grupo': grupo,
            }
        )

    return locals()


@rtr()
@login_required()
def solicitar_autocadastro(request):
    title = 'Solicitação de autocadastro de biometria'

    form = ConfirmarComSenhaForm(request.POST or None, request=request)

    if form.is_valid():
        if form.cleaned_data['confirmar'] is True:
            solicitacao = BiometriaSolicitacao()
            solicitacao.pessoa_fisica = request.user.get_profile()
            solicitacao.save()
            _enviar_codigo_autocadastro(request, solicitacao)
            return httprr('..', 'Solicitação realizada, verifique seu e-mail.')

    return locals()


@login_required()
def autocadastro_reenviar(request, solicitacao_pk):
    solicitacao = get_object_or_404(BiometriaSolicitacao, id=solicitacao_pk)

    if request.user.get_profile() != solicitacao.pessoa_fisica:
        return httprr('..', 'Não foi possível reenviar o código de autorização.', tag='error')

    _enviar_codigo_autocadastro(request, solicitacao)

    return httprr('..', 'O código de autorização foi reenviado.')


def _enviar_codigo_autocadastro(request: HttpRequest, solicitacao: BiometriaSolicitacao) -> bool:
    """Envia o código da solicitação para o e-mail de notificação do vínculo logado."""
    v = request.user.get_vinculo()
    return solicitacao.enviar_email(email=v.email_notificacao if v else None)


@rtr()
@login_required()
def prestador_servico(request, id):
    obj = get_object_or_404(PrestadorServico.objects, id=id)
    title = str(obj)
    hoje = datetime.now().date()
    pode_editar_ocupacao = obj.ativo and (
        request.user.has_perm('comum.change_prestadorservico') and request.user.eh_servidor or request.user.is_superuser
    )
    verificacao_propria = request.user == obj.get_vinculo().user
    pode_ver_professor = request.user.has_perm('edu.view_professor') or verificacao_propria
    if request.user.get_relacionamento() == obj or request.user.has_perm('comum.view_prestadorservico'):
        return locals()
    else:
        raise PermissionDenied


@rtr()
@login_required()
@permission_required('comum.change_prestadorservico')
def ocupacao_prestador(request, prestador_id):
    prestador = get_object_or_404(PrestadorServico.objects, id=prestador_id)

    if not prestador.ativo or not request.user.eh_servidor:
        raise PermissionDenied

    title = f'Vincular Ocupação do Prestador {prestador}'
    pk = request.GET.get('pk', None)
    ocupacao_dict = {'data': request.POST or None, 'prestador': prestador, 'request': request}
    if pk:
        obj = get_object_or_404(OcupacaoPrestador.objects, id=pk)
        if not obj.eh_ativa():
            raise PermissionDenied
        ocupacao_dict['instance'] = obj

    form = OcupacaoPrestadorForm(**ocupacao_dict)
    if form.is_valid():
        form.processar()
        if prestador.tem_ocupacao_ativa():
            prestador.pessoa_fisica.eh_prestador = True
            prestador.pessoa_fisica.save()
            prestador.usuario_externo = False
            prestador.ativo = True
            prestador.save()
            if not prestador.get_vinculo().user.is_active:
                User.objects.filter(id=prestador.get_vinculo().user.id).update(is_active=True, is_staff=True)
            sync_ldap_user(prestador.matricula)
        return httprr('..', 'Ocupação vinculada com sucesso.')
    return locals()


@rtr()
@login_required()
@permission_required('comum.change_prestadorservico')
def alterar_foto_prestador(request, prestador_id):
    prestador = get_object_or_404(PrestadorServico.objects, id=prestador_id)
    title = f'Alterar Foto do Usuário Externo {prestador}'
    vinculo = prestador.get_vinculo()
    pessoa_fisica = vinculo.relacionamento.pessoa_fisica
    if request.method == 'POST':
        form = AtualizarFotoPessoaFisicaForm(data=request.POST or None, files=request.FILES, pessoa_fisica=pessoa_fisica, vinculo=vinculo)
    else:
        form = AtualizarFotoPessoaFisicaForm(pessoa_fisica=pessoa_fisica, vinculo=vinculo)
    if form.is_valid():
        return httprr('..', form.processar(request))
    return locals()


@rtr()
@login_required()
@permission_required('comum.change_prestadorservico')
def encerrar_ocupacao_prestador(request, ocupacao_prestador_id):
    if not request.user.eh_servidor and not request.user.is_superuser:
        raise PermissionDenied
    ocupacao_prestador = get_object_or_404(OcupacaoPrestador.objects, id=ocupacao_prestador_id)
    prestador = ocupacao_prestador.prestador
    hoje = date.today()
    nao_pode_encerrar = False
    if not ocupacao_prestador.eh_ativa():
        nao_pode_encerrar = True
        messages.error(request, f'Não foi possível encerrar a {ocupacao_prestador} do Prestador {prestador} pois a mesma ja se encontra encerrada.')
    else:
        if ocupacao_prestador.data_fim == hoje:
            nao_pode_encerrar = True
            messages.error(request, f'Não foi possível encerrar a {ocupacao_prestador} do Prestador {prestador} por que ela já se encerra hoje.')

    if nao_pode_encerrar:
        return httprr(prestador.get_absolute_url())
    title = f'Encerrar Ocupação {ocupacao_prestador} do Prestador {prestador}'

    form = EncerrarOcupacaoPrestadorForm(request.POST or None)
    if form.is_valid():
        ocupacao_prestador.data_fim = hoje - timedelta(days=1)
        ocupacao_prestador.save()
        LogEntry.objects.log_action(
            user_id=request.user.pk,
            content_type_id=get_content_type_for_model(ocupacao_prestador).pk,
            object_id=ocupacao_prestador.pk,
            object_repr=force_str(ocupacao_prestador),
            action_flag=CHANGE,
            change_message=f'Encerrou Ocupação {ocupacao_prestador} do Prestador {prestador} ',
        )
        sync_ldap_user(prestador.matricula)
        return httprr('..', 'Ocupação encerrada com sucesso.')
    return locals()


@rtr(template='documentacao/docs.html')
def documentacao_view(request):
    documentacao = None
    if not settings.BEHAVE_AUTO_DOC_PATH:
        return httprr('/', 'A configuração não realizada.', 'error')
    try:
        with open(f'{settings.BEHAVE_AUTO_DOC_PATH}/documentacao.json') as fd:
            documentacao_geral = json.loads(fd.read())
    except FileNotFoundError, json.JSONDecodeError:
        return httprr('/', 'A documentação ainda não foi gerada.', 'error')

    documentacao = OrderedDict()
    for app in documentacao_geral['aplicacoes']:
        try:
            with open(f'{settings.BEHAVE_AUTO_DOC_PATH}/{app}/documentacao.json') as fd:
                documentacao_json = json.loads(fd.read())
            for aplicacao in documentacao_json['aplicacoes'].values():
                area = aplicacao['area']
                if documentacao.get(area):
                    documentacao[area].append(aplicacao)
                else:
                    documentacao[area] = [aplicacao]
        except FileNotFoundError, json.JSONDecodeError:
            pass

    documentacao = OrderedDict(sorted(documentacao.items()))
    data_ultima_atualizacao_documentacao = documentacao_geral.get('data_atualizacao')
    return locals()


def documentacao_cenario_view(request, aplicacao, funcionalidade, cenario):
    def atualizar_contexto(contexto, aplicacao, funcionalidade, cenario):
        contexto.update({'proxima_aplicacao': aplicacao, 'proxima_funcionalidade': funcionalidade, 'proximo_cenario': cenario})

    if not settings.BEHAVE_AUTO_DOC_PATH:
        return httprr('/', 'A configuração não realizada.', 'error')
    try:
        apps.get_app_config(aplicacao)
        with open(f'{settings.BEHAVE_AUTO_DOC_PATH}/{aplicacao}/documentacao.json') as fd:
            documentacao = json.loads(fd.read())
    except LookupError, FileNotFoundError:
        return HttpResponseBadRequest('Aplicação inválida ou sem documentação.')
    contexto = {}
    o_aplicacao = documentacao['aplicacoes'].get(aplicacao)
    for o_funcionalidade in o_aplicacao['funcionalidades']:
        if contexto and o_funcionalidade.get('cenarios'):
            atualizar_contexto(
                contexto, o_aplicacao['sigla'], o_funcionalidade['nome'], slugify(next(iter(o_funcionalidade['cenarios'])).get('nome'))
            )
            return render(request, 'comum/templates/documentacao/cenario.html', contexto)
        elif o_funcionalidade['chave'] == funcionalidade:
            for o_cenario in o_funcionalidade['cenarios']:
                if contexto:
                    atualizar_contexto(contexto, o_aplicacao['sigla'], o_funcionalidade['nome'], slugify(o_cenario['nome']))
                    return render(request, 'comum/templates/documentacao/cenario.html', contexto)
                elif o_cenario['chave'] == cenario:
                    app_name = o_funcionalidade.get('app_name')
                    feature_name = slugify(o_funcionalidade.get('nome'))
                    cenario_name = slugify(o_cenario.get('nome'))
                    imagem_workflow = f'workflow/{app_name}/{feature_name}.png'
                    if not os.path.isfile(os.path.join(settings.BEHAVE_AUTO_DOC_PATH, imagem_workflow)):
                        imagem_workflow = ''
                    has_bpmn_workflow = os.path.isfile(f'{app_name}/workflows/{cenario_name}.bpmn')
                    contexto = {
                        'aplicacao_nome': o_aplicacao['nome'],
                        'aplicacao_sigla': o_aplicacao['sigla'],
                        'funcionalidade': o_funcionalidade,
                        'cenario': o_cenario,
                        'workflow': imagem_workflow,
                        'has_bpmn_workflow': has_bpmn_workflow,
                    }

    if contexto:
        return render(request, 'comum/templates/documentacao/cenario.html', contexto)

    return HttpResponseBadRequest('O cenário escolhido não existe na documentação.')


def about_view(request, aplicacao):
    try:
        app_config = apps.get_app_config(aplicacao)
        with open(f'{settings.BEHAVE_AUTO_DOC_PATH}/{aplicacao}/documentacao.json') as fd:
            documentacao = json.loads(fd.read())
    except LookupError, FileNotFoundError:
        return HttpResponseBadRequest('Aplicação inválida ou sem documentação.')
    groups = GroupDetail.objects.filter(app=aplicacao)
    perfis_da_app = groups.filter(app_manager=aplicacao).order_by('group__name')
    perfis_fora_app = groups.exclude(app_manager=aplicacao).order_by('group__name')
    documentacao_aplicacao = documentacao['aplicacoes'][aplicacao]
    has_module_bpmn = os.path.isfile(os.path.join(f'{aplicacao}/workflows/{aplicacao}.bpmn'))
    workflows = [(key, value) for key, value in documentacao_aplicacao['workflows'].items()]
    return render(
        request,
        'comum/templates/documentacao/modulo.html',
        {
            'aplicacao': aplicacao,
            'perfis_da_app': perfis_da_app,
            'perfis_fora_app': perfis_fora_app,
            'app_config': app_config,
            'workflows': workflows,
            'has_module_bpmn': has_module_bpmn,
        },
    )


def about_feature_view(request, aplicacao, funcionalidade):
    try:
        app_config = apps.get_app_config(aplicacao)
        with open(f'{settings.BEHAVE_AUTO_DOC_PATH}/{aplicacao}/documentacao.json') as fd:
            documentacao = json.loads(fd.read())
    except LookupError, FileNotFoundError:
        return HttpResponseBadRequest('Aplicação inválida ou sem documentação.')
    o_aplicacao = documentacao['aplicacoes'][aplicacao]
    funcionalidade_existe = False
    for o_funcionalidade in o_aplicacao['funcionalidades']:
        if o_funcionalidade['chave'] == funcionalidade:
            funcionalidade_existe = True
            break
    if not funcionalidade_existe:
        return HttpResponseBadRequest('Aplicação não possui documentação para esta funcionalidade.')
    has_feature_bpmn = os.path.isfile(os.path.join(f'{aplicacao}/workflows/{slugify(funcionalidade)}.bpmn'))
    workflows = [(key, value) for key, value in o_aplicacao['workflows'].items()]
    context = {
        'aplicacao': o_aplicacao,
        'funcionalidade': o_funcionalidade,
        'app_config': app_config,
        'workflows': workflows,
        'has_feature_bpmn': has_feature_bpmn,
    }
    return render(request, 'comum/templates/documentacao/about_feature.html', context)


def documentacao_imagem_view(request):
    imagem = request.GET.get('i', '')
    aplicacao = request.GET.get('app', '')
    imagem_path = os.path.join(settings.BEHAVE_AUTO_DOC_PATH, aplicacao, imagem)

    if imagem and os.path.exists(imagem_path):
        response = HttpResponse(content_type='image/png')
        with open(imagem_path, 'rb') as fd:
            response.write(fd.read())
        return response
    else:
        return httprr('/', 'Nenhuma imagem encontrada.', 'error')


def documentacao_bpmn_view(request, aplicacao, bpmn):
    return HttpResponse(content=open(os.path.join(f'{aplicacao}/workflows/{bpmn}'), encoding='utf-8').read(), content_type='text/plain')


def login(
    request,
    template_name='comum/templates/login.html',
    redirect_field_name='next',
    authentication_form=AuthenticationFormPlus,
    extra_context=None,
    redirect_authenticated_user=False,
):
    # Verifica se o Login com Gov.BR está habilitado nas configurações do SUAP
    autenticacao_govbr_habilitada = Configuracao.get_valor_por_chave('comum', 'habilitar_autenticacao_govbr')

    if not extra_context:
        extra_context = {}
    extra_context.update(
        {
            'settings': settings,
            'servicos_anonimos': layout.gerar_servicos_anonimos(request),
            'autenticacao_govbr_habilitada': autenticacao_govbr_habilitada,
        }
    )
    was_already_authenticated = request.user.is_authenticated
    try:
        response = LoginView.as_view(
            template_name=template_name,
            redirect_field_name=redirect_field_name,
            form_class=authentication_form,
            extra_context=extra_context,
            redirect_authenticated_user=redirect_authenticated_user,
        )(request)
    except UserMustResetPassword as e:
        return httprr(e.redirect_url, str(e), 'error')
    except LoginException as e:
        return httprr('/', str(e), 'error')

    if request.user.is_authenticated:
        expire_date = datetime.now() + timedelta(days=90)
        try:
            cookie = request.COOKIES.get(settings.SUAP_CONTROL_COOKIE_NAME, '')
            if cookie:
                try:
                    cookie_data = decrypt(cookie)
                except Exception:
                    cookie_data = {}
                usernames = cookie_data.get('usernames', [])
                if request.user.username not in usernames:
                    usernames.append(request.user.username)
            else:
                usernames = [request.user.username]
            suap_control = {'usernames': usernames, 'datetime': expire_date.isoformat()}
            suap_control_dump = encrypt(suap_control)
            response.set_cookie(
                settings.SUAP_CONTROL_COOKIE_NAME,
                suap_control_dump,
                expires=expire_date,
                secure=True,
                samesite='Strict',
            )
            user = request.user
            if user.data_solicitacao_forcar_troca_senha:
                user.data_solicitacao_forcar_troca_senha = None
                user.save()
                messages.error(
                    request,
                    mark_safe(
                        'Por questões de segurança, foi solicitada a alteração da sua senha pelo SUAP. <a href="/admin/comum/senhaexposta/">Saiba mais sobre a solicitação</a>.'
                    ),
                )
            if request.GET.get('next', '/').startswith('/o/authorize/') and not was_already_authenticated:
                url = urllib.parse.urlsplit(request.GET.get('next'))
                client_id = urllib.parse.parse_qs(url.query).get('client_id', ['0'])[0]
                if not apps.get_model('api.AplicacaoOAuth2').objects.filter(client_id=client_id).filter(keep_session=True).exists():
                    request.session.set_expiry(10)
            pessoa = user.get_profile()
            # login do estrangeiro sem CPF: o legado é só o número do passaporte; o novo, a chave ARG-AB123456
            if pessoa and pessoa.passaporte and user.username in (pessoa.passaporte, pessoa.documento_identificador):
                request.session['autenticou_com_passaporte'] = user.username
                request.session.save()
                return httprr('/comum/selecionar_vinculo/')
        except Exception as e:
            if settings.DEBUG:
                raise e
            capture_exception(e)
    return response


def login_exige_captcha(request, username):
    user = User.objects.filter(username=username, login_attempts__gt=3).first()
    if user:
        return HttpResponse('OK')
    else:
        return HttpResponse('ERROR')


def login_exige_duplo_fator(request, username):
    if running_tests():
        return HttpResponse('OK', status=200)

    user = User.objects.filter(username=username).first()
    permite_autenticacao_duplo_fator = Configuracao.get_valor_por_chave('comum', 'permite_autenticacao_duplo_fator')

    if permite_autenticacao_duplo_fator and user and user.autenticacaodoisfatores_habilitada():
        return HttpResponse('OK', status=200)
    return HttpResponse('ERROR')


def _exigencia_govbr_nao_atendida(request, id_confiabilidade_govbr: str) -> str | None:
    """Verifica se a sessão autenticada pelo Gov.BR atende às exigências configuradas no SUAP.

    Args:
        request: Requisição HTTP em curso.
        id_confiabilidade_govbr: Nível de confiabilidade da conta Gov.BR do usuário.

    Returns:
        A mensagem de erro correspondente à exigência não atendida, ou ``None`` quando
        nível de confiabilidade e duplo fator estão de acordo com o exigido.
    """
    nivel_configuracao_exigido = Configuracao.get_valor_por_chave('comum', 'nível_minimo_para_autenticacao_govbr')
    if nivel_configuracao_exigido and int(nivel_configuracao_exigido) > int(id_confiabilidade_govbr):
        return 'O nível de confiabilidade da sua conta Gov.BR não atende ao nível exigido pelo SUAP, para autenticar é necessário que aumente o nível de confiabilidade da sua conta.'

    duplo_fator_exigido = Configuracao.get_valor_por_chave('comum', 'exige_duplo_fator_autenticacao_govbr')
    usuario_utiliza_duplo_fator_govbr = request.session.get('token_govbr', {}).get('decoded_data', {}).get('amr', [])
    if duplo_fator_exigido and not usuario_utiliza_duplo_fator_govbr:
        return mark_safe(
            "O SUAP exige a utilização do Segundo Autenticação do Gov.BR. Para ativar siga <a href='https://www.gov.br/governodigital/pt-br/acessibilidade-e-usuario/atendimento-gov.br/duvidas-na-conta-gov.br/ativar-a-verificacao-em-duas-etapas'>estas orientações.</a>"
        )
    return None


def _redirecionar_para_vinculo_escolhido(request, vinculos_ativos_: list, vinculos_hash: dict, cpf: str, sessao_govbr: dict | None):
    """Autentica o usuário no vínculo escolhido e o encaminha ao destino do login.

    Args:
        request: Requisição HTTP em curso.
        vinculos_ativos_: Dados dos vínculos ativos exibidos na tela.
        vinculos_hash: Mapa de hash do vínculo para o seu id.
        cpf: CPF obtido da autenticação Gov.BR, quando houver.
        sessao_govbr: Dados da autenticação Gov.BR a serem preservados na nova sessão, se houver.

    Returns:
        A resposta de redirecionamento (ou de erro), ou ``None`` quando ainda não há
        vínculo escolhido e a tela de seleção precisa ser exibida.
    """
    unico_vinculo = len(vinculos_ativos_) == 1
    hash_vinculo_selecionado = vinculos_ativos_[0]['vinculo_hash'] if unico_vinculo else request.GET.get('vp', None)
    if not hash_vinculo_selecionado:
        return None
    vinculo = get_object_or_404(Vinculo, pk=vinculos_hash.get(hash_vinculo_selecionado))
    if vinculo != request.user.get_vinculo():
        erro = _autenticar_no_vinculo(request, vinculo, cpf, sessao_govbr)
        if erro:
            return erro
    # Segue para a URL que originou o login (ex.: /o/authorize/ de uma aplicação OAuth2),
    # consumindo o cookie para que ele não interfira em um login posterior.
    response = HttpResponseRedirect(destino_pos_autenticacao(request))
    response.delete_cookie('auth_redirect_url')
    return response


def _autenticar_no_vinculo(request, vinculo, cpf: str, sessao_govbr: dict | None) -> HttpResponseForbidden | None:
    """Autentica o usuário no vínculo escolhido na tela de seleção de vínculo.

    Args:
        request: Requisição HTTP em curso.
        vinculo: Vínculo escolhido pelo usuário.
        cpf: CPF obtido da autenticação Gov.BR, usado para conferir a titularidade do vínculo.
        sessao_govbr: Dados da autenticação Gov.BR a serem preservados na nova sessão, se houver.

    Returns:
        ``HttpResponseForbidden`` quando o vínculo não pertence ao usuário autenticado,
        ``None`` quando a autenticação é efetivada.
    """
    from django.contrib.auth import login

    if cpf and mask_cpf(cpf) != vinculo.pessoa.pessoafisica.cpf:
        return HttpResponseForbidden('Você não tem permissão para acessar este vínculo.')
    request.user = vinculo.user
    request.user.backend = 'djtools.contrib.auth.backends.ModelBackendPlus'
    login(request, vinculo.user)
    if sessao_govbr:
        request.session.update(sessao_govbr)
    messages.success(request, 'Vínculo alterado com sucesso')
    return None


def _dados_vinculo_para_selecao(vinculo, vinculo_hash: str, request) -> dict:
    """Monta os dados de um vínculo exibidos na tela de seleção de vínculo.

    Args:
        vinculo: Vínculo ativo do usuário.
        vinculo_hash: Hash que identifica o vínculo na tela, sem expor o seu id.
        request: Requisição HTTP em curso.

    Returns:
        Dicionário com os dados do vínculo usados pelo template.
    """
    nome_relacionamento = vinculo.relacionamento.__class__.__name__
    if vinculo.eh_usuario_externo():
        nome_relacionamento = 'Usuário Externo'
    return {
        'foto': vinculo.get_foto_150x200_url,
        'nome_pessoa': vinculo.relacionamento.pessoa_fisica.nome,
        'relacionamento': vinculo.relacionamento,
        'nome_relacionamento': nome_relacionamento,
        'vinculo_hash': vinculo_hash,
        'user': vinculo.user,
        'informacao_adicional': vinculo.get_informacao_adicional(),
        'selecionado': vinculo == request.user.get_vinculo(),
    }


@rtr()
@login_required()
def selecionar_vinculo(request):
    """
    Exibe vínculos ativos do usuário após autenticar com Gov.Br, após seleção do vínculo e clicar no botão Entrar é realizada a autenticação para o user daquele vínculo
    """
    title = 'Selecionar vínculo'
    category = 'Acessos'
    servicos_anonimos = layout.gerar_servicos_anonimos(request)
    vinculos_ativos = Vinculo.objects.none()
    vinculo_id = request.GET.get('vinculo_id', None)
    message = None
    cpf = ''
    vinculos_ativos_ = []
    vinculos_hash = {}
    id_confiabilidade_govbr = '0'
    token_govbr = None
    if request.session.get('autenticou_com_govbr'):
        pessoa = request.user.is_authenticated and request.user.get_profile() or None
        cpf = pessoa and pessoa.cpf or mask_cpf(request.user.username)
        if cpf:
            id_confiabilidade_govbr = request.session['confiabilidade_govbr']
            token_govbr = request.session['token_govbr']
            message = _exigencia_govbr_nao_atendida(request, id_confiabilidade_govbr)
            if message:
                messages.error(request, message)
                logout(request)
                return HttpResponseRedirect('/')
        vinculos_ativos = Vinculo.objects.filter(pessoa__pessoafisica__cpf=cpf, user__is_active=True)
    elif request.session.get('autenticou_com_passaporte') and request.user.is_authenticated and request.user.get_profile():
        # pelo par passaporte+país: o mesmo número de outro país é outra pessoa
        vinculos_ativos = Vinculo.objects.filter(
            filtro_mesma_pessoa_por_passaporte(request.user.get_profile(), 'pessoa__pessoafisica__'), user__is_active=True
        )

    # Sem autenticação govbr/passaporte, `vinculos_ativos` é vazio e nada é montado.
    for vinculo in vinculos_ativos:
        vinculo_hash = hashlib.md5(str(vinculo.id).encode()).hexdigest()
        vinculos_hash[vinculo_hash] = vinculo.id
        vinculos_ativos_.append(_dados_vinculo_para_selecao(vinculo, vinculo_hash, request))

    if not vinculos_ativos_:
        message = """
        Você foi deslogado pois não existe um vínculo associado a este usuário. Favor entrar em contato com a
        Coordenação de TI do seu campus para regularizar sua situação.
        """
        messages.error(request, message)
        logout(request)
        return HttpResponseRedirect('/')

    sessao_govbr = (
        {'autenticou_com_govbr': True, 'confiabilidade_govbr': id_confiabilidade_govbr, 'token_govbr': token_govbr}
        if request.session.get('autenticou_com_govbr')
        else None
    )
    response = _redirecionar_para_vinculo_escolhido(request, vinculos_ativos_, vinculos_hash, cpf, sessao_govbr)
    if response:
        return response

    return locals()


def handler500(request):
    """500 error handler which includes ``request`` in the context.

    Templates: `500.html`
    Context: None
    """

    try:  # esta tela não pode quebrar
        servicos_anonimos = layout.gerar_servicos_anonimos(request)
        if request.user.is_authenticated:
            tem_permissao_feedback = None

            full_url = request.build_absolute_uri()
            view = get_view_name_from_url(full_url)
            event_id = last_event_id()
            if all([tem_permissao_informar_erro(request), full_url, view]):
                tem_permissao_feedback = 'pode_comentar'
    except Exception as e:
        messages.error(request, str(e))
    return render(request, '500.html', locals(), status=500)


@requires_csrf_token
def page_not_found(request, exception, template_name='comum/templates/404.html'):
    """
    Default 404 handler.

    Templates: :template:`404.html`
    Context:
        request_path
            The path of the requested URL (e.g., '/app/pages/bad_page/'). It's
            quoted to prevent a content injection attack.
        exception
            The message from the exception which triggered the 404 (if one was
            supplied), or the exception class name
    """
    exception_repr = exception.__class__.__name__
    # Try to get an "interesting" exception message, if any (and not the ugly
    # Resolver404 dictionary)
    try:
        message = exception.args[0]
    except AttributeError, IndexError:
        pass
    else:
        if isinstance(message, str):
            exception_repr = message
    context = {
        'request_path': urllib.parse.quote(request.path),
        'exception': exception_repr,
        'servicos_anonimos': layout.gerar_servicos_anonimos(request),
        'hide_messages': True,
        'exibir_botao_reportar_erro': False,
    }
    try:
        template = loader.get_template(template_name)
        body = template.render(context, request)
        content_type = None  # Django will use 'text/html'.
    except TemplateDoesNotExist:
        if template_name != 'comum/templates/404.html':
            # Reraise if it's a missing custom template.
            raise
        # Render template (even though there are no substitutions) to allow
        # inspecting the context in tests.
        template = Engine().from_string(
            ERROR_PAGE_TEMPLATE
            % {
                'title': 'Not Found',
                'details': 'The requested resource was not found on this server.',
            },
        )
        body = template.render(Context(context))
        content_type = 'text/html'
    return HttpResponseNotFound(body, content_type=content_type)


@requires_csrf_token
def permission_denied(request, exception, template_name='comum/templates/403.html'):
    """
    Permission denied (403) handler.

    Templates: :template:`403.html`
    Context: None

    If the template does not exist, an Http403 response containing the text
    "403 Forbidden" (as per RFC 7231) will be returned.
    """
    try:
        template = loader.get_template(template_name)
        context = {
            'exception': str(exception),
            'servicos_anonimos': layout.gerar_servicos_anonimos(request),
        }
    except TemplateDoesNotExist:
        if template_name != 'comum/templates/403.html':
            # Reraise if it's a missing custom template.
            raise
        return HttpResponseForbidden(
            ERROR_PAGE_TEMPLATE % {'title': '403 Forbidden', 'details': ''},
            content_type='text/html',
        )
    return HttpResponseForbidden(template.render(request=request, context=context))


@requires_csrf_token
def csrf_failure(request, reason=''):
    messages.add_message(request, level=messages.ERROR, message='Tempo excessivo sem atividade. Por favor, tente novamente.')
    return redirect(request.path)


#############################
# Calendário Administrativo #
#############################


@rtr()
@login_required
def calendario_administrativo(request):
    title = f'Calendário Administrativo por {nomenclatura.campus}'
    setor = request.user.get_relacionamento().setor
    if setor is None:
        return httprr('..', 'Seu usuário não possui um setor ativo.', tag='error')
    uo = setor.uo
    ano = Ano.objects.filter(ano=date.today().year).first()
    data_ini = date(ano.ano, 1, 1)
    data_fim = date(ano.ano, 12, 31)
    form = CalendarioForm(request.POST or None)
    pessoa_fisica = request.user.get_profile()
    if form.is_valid():
        if form.cleaned_data.get('ano'):
            ano = form.cleaned_data['ano']
        if form.cleaned_data.get('uo'):
            uo = form.cleaned_data['uo']

    calendario = Calendario()
    calendario.adicionar_tipo_evento('evento', 'Evento/Data Comemorativa')
    if 'ponto' in settings.INSTALLED_APPS:
        from ponto.models import Liberacao

        [
            calendario.adicionar_evento_calendario(
                liberacao.data_inicio, liberacao.data_fim, liberacao.descricao, liberacao.get_liberacao_css(), liberacao.descricao
            )
            for liberacao in Liberacao.get_liberacoes_calendario(uo, ano.ano)
        ]

    if 'ferias' in settings.INSTALLED_APPS and request.user.eh_servidor:
        from ferias.models import Ferias

        periodos = Ferias.get_periodos_pessoa_estava_de_ferias(request.user.get_relacionamento(), data_ini, data_fim)
        for periodo_ini, periodo_fim, label in periodos:
            calendario.adicionar_evento_calendario(periodo_ini, periodo_fim, label, 'ferias', label)

    if 'rh' in settings.INSTALLED_APPS and request.user.eh_servidor:
        from rh.models import ServidorAfastamento

        afastamentos_servidores = ServidorAfastamento.objects.filter(
            servidor=request.user.get_relacionamento(), data_termino__year__lte=ano.ano, cancelado=False
        )

        afastamentos_servidores = afastamentos_servidores.exclude(data_inicio__lt=data_ini).exclude(data_termino__gt=data_fim)
        for afastamento in afastamentos_servidores:
            calendario.adicionar_evento_calendario(
                afastamento.data_inicio,
                afastamento.data_termino,
                afastamento.afastamento.nome,
                'afastamento',
            )

    if 'rh' in settings.INSTALLED_APPS and request.user.has_group_cached(
        ('Servidor', 'Coordenador de Gestão de Pessoas', 'Coordenador de Gestão de Pessoas Sistêmico', 'Operador de Gestão de Pessoas')
    ):
        from rh.models import CronogramaFolha, ServidorAfastamento

        cronogramasfolha = CronogramaFolha.objects.filter(ano=ano)
        css_class = 'extra5'
        for cronogramafolha in cronogramasfolha:
            calendario.adicionar_evento_calendario(
                cronogramafolha.data_consulta_previa_folha,
                cronogramafolha.data_consulta_previa_folha,
                'Consulta da Prévia da Folha',
                css_class,
                'Data da consulta da Prévia da Folha',
            )
            calendario.adicionar_evento_calendario(
                cronogramafolha.data_fechamento_processamento_folha,
                cronogramafolha.data_fechamento_processamento_folha,
                'Fechamento do SIAPE para Processamento da Folha',
                css_class,
                'Data do fechamento do SIAPE para Processamento da Folha',
            )
            calendario.adicionar_evento_calendario(
                cronogramafolha.data_abertura_atualizacao_folha,
                cronogramafolha.data_abertura_atualizacao_folha,
                'Abertura do SIAPE para Atualização da Folha',
                css_class,
                'Data da abertura do SIAPE para Atualização da Folha',
            )
            calendario.adicionar_evento_calendario(
                cronogramafolha.data_abertura_proxima_folha,
                cronogramafolha.data_abertura_proxima_folha,
                'Abertura da Próxima Folha',
                css_class,
                'Abertura da Próxima Folha',
            )

    calendario_ano = calendario.formato_ano(ano.ano)
    return locals()


@rtr()
@login_required
def remote_logout(request: HttpRequest, sessioninfo_pk: int) -> HttpResponse:
    if not (request.user.is_superuser or request.user.has_group_cached('Coordenador de Segurança da Informação')):
        session_info = get_object_or_404(SessionInfo, pk=sessioninfo_pk, device__user=request.user)
    else:
        session_info = get_object_or_404(SessionInfo, pk=sessioninfo_pk)
    get_remote_session(session_info.session_id).delete()
    session_info.expired = True
    session_info.save()
    return httprr('/admin/comum/sessioninfo/', 'Sessão remota deslogada com sucesso.')


@rtr()
@login_required
def remote_logout_all(request):
    qs = SessionInfo.objects.filter(device__user=request.user, expired=False).exclude(session_id=request.session.session_key)
    for session_info in qs:
        try:
            get_remote_session(session_info.session_id).delete()
            session_info.expired = True
            session_info.save()
        except Exception as e:
            raise e
    return httprr('/admin/comum/sessioninfo/', 'Sessões remotas deslogadas com sucesso.')


@rtr()
@login_required
def deactivate_device(request: HttpRequest, device_pk: int) -> HttpResponse:
    if not (request.user.is_superuser or request.user.has_group_cached('Coordenador de Segurança da Informação')):
        device = get_object_or_404(Device, pk=device_pk, user=request.user)
    else:
        device = get_object_or_404(Device, pk=device_pk)

    device.activated = False
    device.save()
    qs = SessionInfo.objects.filter(device=device)
    contador = qs.count()
    for session_info in qs:
        try:
            get_remote_session(session_info.session_id).delete()
        except Exception:
            pass
        session_info.expired = True
        session_info.save()
    return httprr('/admin/comum/device/', f'Dispositivo desativado e {contador} sessões expiradas.')


@rtr()
@login_required
def reactivate_device(request, device_pk):
    if not request.user.is_superuser:
        device = get_object_or_404(Device, pk=device_pk, user=request.user)
    else:
        device = get_object_or_404(Device, pk=device_pk)

    device.activated = True
    device.save()
    return httprr('/admin/comum/device/', 'Dispositivo reativado.')


@rtr()
@login_required
def give_nickname_to_device(request, device_pk):
    if not request.user.is_superuser:
        device = get_object_or_404(Device, pk=device_pk, user=request.user)
    else:
        device = get_object_or_404(Device, pk=device_pk)

    form = DeviceForm(request.POST or None, request=request, instance=device)
    if form.is_valid():
        form.save()
        return httprr('..', 'Apelido concedido com sucesso.')
    return locals()


@rtr()
@login_required
def webmail(request):
    url_webmail = Configuracao.get_valor_por_chave('comum', 'url_webmail')
    return HttpResponseRedirect(url_webmail)


@rtr()
@login_required
def azure(request):
    servidor = request.user.get_relacionamento()
    if not servidor.tem_acesso_servicos_microsoft():
        return HttpResponseForbidden('Usuário não tem acesso a essa página')
    url = URL_AZURE
    return HttpResponseRedirect(url)


@rtr()
@login_required
def google_classroom(request):
    sub_instance = request.user.get_relacionamento()
    if is_ldap_enabled():
        if (hasattr(sub_instance, 'email_google_classroom') and sub_instance.email_google_classroom) or request.user.has_group_cached(
            'Usuários do Google Classroom'
        ):
            return HttpResponseRedirect('/ldap_backend/redirecionar_google_classroom/')
    return HttpResponseForbidden('Usuário não tem acesso a essa página')


@rtr()
@login_required
def documentos_emitidos_suap(request):
    title = 'Meus Documentos SUAP'
    dados = []
    documentos.signal.send(sender=documentos_emitidos_suap, request=request, data=dados)
    areas = {}
    for area, categoria, subcategoria, descricao, url in dados:
        if area not in areas:
            areas[area] = {}
        if categoria not in areas[area]:
            areas[area][categoria] = {}
        if subcategoria not in areas[area][categoria]:
            areas[area][categoria][subcategoria] = []
        areas[area][categoria][subcategoria].append((descricao, url))
    return locals()


@rtr()
@login_required
def minhas_acoes_suap(request):
    title = 'Ações'
    areas = {}
    form = FiltrarPorPeriodoForm(request.GET or None, request=request)
    if form.is_valid():
        from comum.utils import get_acoes_por_periodo

        areas = get_acoes_por_periodo(request, form.cleaned_data['usuario'].user, form.datahora_inicio, form.datahora_fim)

    return locals()


def _notificacoes_nao_lidas_deduplicadas(vinculo: Vinculo) -> QuerySet[RegistroNotificacao]:
    """Retorna queryset deduplicado: uma entrada por objeto_relacionado (a mais recente) + todas sem objeto.

    Ordem total ``(-data, -pk)``: o ``pk`` desempata datas iguais, o que torna ``(data, pk)`` um
    cursor estável para a rolagem infinita (``busca_notificacao``).
    """
    sub = (
        RegistroNotificacao.objects.filter(vinculo=vinculo, lida=False, notificacao__objeto_relacionado=OuterRef('notificacao__objeto_relacionado'))
        .order_by('-data', '-pk')
        .values('id')
    )[:1]
    com_objeto = RegistroNotificacao.objects.filter(lida=False, vinculo=vinculo, id__in=Subquery(sub))
    sem_objeto = RegistroNotificacao.objects.filter(lida=False, vinculo=vinculo, notificacao__objeto_relacionado__isnull=True)
    return (com_objeto | sem_objeto).order_by('-data', '-pk')


@rtr()
@permission_required('comum.view_registronotificacao')
def notificacoes(request: HttpRequest) -> dict[str, Any]:
    """View para exibir notificações do usuário"""
    vinculo = request.user.get_vinculo()
    hoje = datetime.now()

    todas_notificacoes = _notificacoes_nao_lidas_deduplicadas(vinculo)

    notificacoes = list(todas_notificacoes[:10])
    title = 'Notificações não lidas'

    # Abre e marca como lida a primeira notificação LEGÍVEL da lista exibida (#17388): uma travada
    # no topo (ex.: alerta de dispositivo desconhecido, bloqueado por 3 dias) impedia a leitura de
    # todas. A travada continua não lida no topo; sem legível na tela, abre a primeira sem marcar.
    notificacao = next((n for n in notificacoes if n.pode_ler()), notificacoes[0] if notificacoes else None)
    if notificacao and not notificacao.lida and notificacao.pode_ler():
        notificacao.lida = True
        notificacao.save()

    # Extras
    qtd_notificacoes_antigas = RegistroNotificacao.objects.filter(
        vinculo=request.user.get_vinculo(), lida=True, data__lt=somar_dias(datetime.today(), -30)
    ).count()

    return locals()


@rtr()
@permission_required('comum.view_registronotificacao')
def notificacao(request, pk):
    notificacao = get_object_or_404(RegistroNotificacao.objects, pk=pk)
    vinculo = request.user.get_vinculo()
    title = 'Notificação'

    if not notificacao.vinculo == vinculo:
        raise PermissionDenied('Você não tem permissão de acesso a essa notificação.')

    # Seta a Notificação e Marca como Lida
    if not notificacao.lida and notificacao.pode_ler():
        notificacao.lida = True
        notificacao.save()

    if request.GET.get('ajax'):
        return render(request, 'notificacao_artigo.html', locals())

    return locals()


@rtr()
@permission_required('comum.view_registronotificacao')
def busca_notificacao(request: HttpRequest, ultimo_pk: int) -> JsonResponse:
    # Rota de API da rolagem infinita: o fim da lista também é JSON (``itens`` vazio). Devolver
    # ``None`` fazia o ``@rtr()`` renderizar HTML, e o ``$.ajax`` do cabeçalho caía no ``.fail()``.
    # Pagina por cursor, não por posição (#17451): devolve a não lida seguinte ao último item
    # exibido (``ultimo_pk``) na ordem ``(-data, -pk)``. A lista encolhe durante a sessão (a caixa
    # marca a 1ª legível como lida ao abrir), e a posição pulava itens. O cursor pode já estar lido, por
    # isso a busca dele não filtra ``lida``; se ele não é do vínculo (ou foi removido), é fim.
    vinculo = request.user.get_vinculo()
    cursor = RegistroNotificacao.objects.filter(vinculo=vinculo, pk=ultimo_pk).values_list('data', flat=True).first()
    registro = None
    if cursor is not None:
        seguintes = Q(data__lt=cursor) | Q(data=cursor, pk__lt=ultimo_pk)
        registro = _notificacoes_nao_lidas_deduplicadas(vinculo).filter(seguintes).first()
    if registro is None:
        return JsonResponse({'itens': ''})
    html = render(request, 'notificacao_ancora.html', {'notificacao': registro})
    return JsonResponse({'itens': html.content.decode(), 'ultimo_pk': registro.pk})


@permission_required('comum.change_categorianotificacao')
def ativar_categoria_notificacao(request: HttpRequest, pk: int) -> HttpResponse:
    categoria = get_object_or_404(CategoriaNotificacao, pk=pk)
    categoria.ativa = True
    categoria.save()

    return httprr('..', 'A Categoria de Notificações foi ativada com sucesso.')


@permission_required('comum.change_categorianotificacao')
def desativar_categoria_notificacao(request: HttpRequest, pk: int) -> HttpResponse:
    categoria = get_object_or_404(CategoriaNotificacao, pk=pk)
    categoria.ativa = False
    categoria.save()

    return httprr('..', 'A Categoria de Notificações foi desativada com sucesso.')


@login_required()
def atualizar_preferencia_padrao(request):
    url_origem = request.META.get('HTTP_REFERER', '.')
    envio = request.GET.get('envio', 'suap')
    is_ajax = request.GET.get('is_ajax', 'False')

    preferencia = Preferencia.objects.filter(usuario=request.user).first()
    if not preferencia:
        try:
            preferencia = Preferencia.objects.create(usuario=request.user)
        except Exception:  # Pode ocorrer por problema de concorrência
            preferencia = Preferencia.objects.filter(usuario=request.user).first()

    mensagem_erro = 'Não é possível inativar as duas formas de Notificação.'

    if envio == 'suap':
        if preferencia.via_suap:
            if not preferencia.via_email:
                if is_ajax == 'True':
                    return HttpResponseForbidden(mensagem_erro)
                else:
                    return httprr(url_origem, mensagem_erro, 'error')
            else:
                preferencia.via_suap = False
        else:
            preferencia.via_suap = True

    elif envio == 'email':
        if preferencia.via_email:
            if not preferencia.via_suap:
                if is_ajax == 'True':
                    return HttpResponseForbidden(mensagem_erro)
                else:
                    return httprr(url_origem, mensagem_erro, 'error')
            else:
                preferencia.via_email = False
        else:
            preferencia.via_email = True

    preferencia.save()

    return httprr(url_origem, 'Preferência atualizada com sucesso.')


@login_required()
def atualizar_via_suap(request, pk):
    url_origem = request.META.get('HTTP_REFERER', '.')
    preferencia = get_object_or_404(PreferenciaNotificacao, pk=pk, vinculo=request.user.get_vinculo(), categoria__forcar_habilitacao=False)
    if preferencia.via_suap:
        if not preferencia.via_email:
            return httprr(url_origem, 'Não é possível inativar as duas formas de Notificação.', 'error')
        else:
            mensagem = 'Envio via SUAP desativado.'
            preferencia.via_suap = False
    else:
        mensagem = 'Envio via SUAP ativado.'
        preferencia.via_suap = True
    preferencia.save()

    LogEntry.objects.log_action(
        user_id=request.user.pk,
        content_type_id=get_content_type_for_model(preferencia).pk,
        object_id=preferencia.pk,
        object_repr=force_str(preferencia),
        action_flag=CHANGE,
        change_message=mensagem,
    )

    return httprr(url_origem, 'Preferência atualizada com sucesso.')


@login_required()
def ativar_via_suap_em_lote(request: HttpRequest) -> HttpResponse:
    url_origem = request.META.get('HTTP_REFERER', '.')
    ids = ids_da_query(request)
    preferencias = PreferenciaNotificacao.objects.filter(pk__in=ids, vinculo=request.user.get_vinculo(), categoria__forcar_habilitacao=False)
    for preferencia in preferencias:
        preferencia.via_suap = True
        preferencia.save()

        LogEntry.objects.log_action(
            user_id=request.user.pk,
            content_type_id=get_content_type_for_model(preferencia).pk,
            object_id=preferencia.pk,
            object_repr=force_str(preferencia),
            action_flag=CHANGE,
            change_message='Envio via SUAP ativado.',
        )

    return httprr(url_origem, 'Preferências atualizadas com sucesso.')


@login_required()
def desativar_via_suap_em_lote(request: HttpRequest) -> HttpResponse:
    url_origem = request.META.get('HTTP_REFERER', '.')
    ids = ids_da_query(request)
    preferencias = PreferenciaNotificacao.objects.filter(pk__in=ids, vinculo=request.user.get_vinculo(), categoria__forcar_habilitacao=False)
    for preferencia in preferencias:
        if preferencia.via_email:
            preferencia.via_suap = False
            preferencia.save()

            LogEntry.objects.log_action(
                user_id=request.user.pk,
                content_type_id=get_content_type_for_model(preferencia).pk,
                object_id=preferencia.pk,
                object_repr=force_str(preferencia),
                action_flag=CHANGE,
                change_message='Envio via SUAP desativado.',
            )

    return httprr(url_origem, 'Preferências atualizadas com sucesso.')


@login_required()
def atualizar_via_email(request, pk):
    url_origem = request.META.get('HTTP_REFERER', '.')
    preferencia = get_object_or_404(PreferenciaNotificacao, pk=pk, vinculo=request.user.get_vinculo(), categoria__forcar_habilitacao=False)
    if preferencia.via_email:
        if not preferencia.via_suap:
            return httprr(url_origem, 'Não é possível inativar as duas formas de Notificação.', 'error')
        else:
            mensagem = 'Envio via E-mail desativado.'
            preferencia.via_email = False
    else:
        mensagem = 'Envio via E-mail ativado.'
        preferencia.via_email = True
    preferencia.save()

    LogEntry.objects.log_action(
        user_id=request.user.pk,
        content_type_id=get_content_type_for_model(preferencia).pk,
        object_id=preferencia.pk,
        object_repr=force_str(preferencia),
        action_flag=CHANGE,
        change_message=mensagem,
    )

    return httprr(url_origem, 'Preferência atualizada com sucesso.')


@login_required()
def ativar_via_email_em_lote(request: HttpRequest) -> HttpResponse:
    url_origem = request.META.get('HTTP_REFERER', '.')
    ids = ids_da_query(request)
    preferencias = PreferenciaNotificacao.objects.filter(pk__in=ids, vinculo=request.user.get_vinculo(), categoria__forcar_habilitacao=False)
    for preferencia in preferencias:
        preferencia.via_email = True
        preferencia.save()

        LogEntry.objects.log_action(
            user_id=request.user.pk,
            content_type_id=get_content_type_for_model(preferencia).pk,
            object_id=preferencia.pk,
            object_repr=force_str(preferencia),
            action_flag=CHANGE,
            change_message='Envio via E-mail ativado.',
        )

    return httprr(url_origem, 'Preferências atualizadas com sucesso.')


@login_required()
def desativar_via_email_em_lote(request: HttpRequest) -> HttpResponse:
    url_origem = request.META.get('HTTP_REFERER', '.')
    ids = ids_da_query(request)
    preferencias = PreferenciaNotificacao.objects.filter(pk__in=ids, vinculo=request.user.get_vinculo(), categoria__forcar_habilitacao=False)
    for preferencia in preferencias:
        if preferencia.via_suap:
            preferencia.via_email = False
            preferencia.save()

            LogEntry.objects.log_action(
                user_id=request.user.pk,
                content_type_id=get_content_type_for_model(preferencia).pk,
                object_id=preferencia.pk,
                object_repr=force_str(preferencia),
                action_flag=CHANGE,
                change_message='Envio via E-mail desativado.',
            )

    return httprr(url_origem, 'Preferências atualizadas com sucesso.')


@permission_required('comum.view_registronotificacao')
def marcar_como_lida(request, pk):
    registro = get_object_or_404(RegistroNotificacao, pk=pk)

    if registro.vinculo == request.user.get_vinculo() and registro.pode_ler():
        registro.lida = True
        registro.save()
    else:
        raise PermissionDenied('Você não pode marcar esta notificação como lida.')

    RegistroNotificacao.limpar_cache(request.user)
    return HttpResponse('OK')


@permission_required('comum.view_registronotificacao')
def marcar_todas_notificacoes_como_lidas(request):
    url_origem = request.META.get('HTTP_REFERER', '.')
    registros = RegistroNotificacao.objects.filter(vinculo=request.user.get_vinculo(), lida=False, data_permite_marcar_lida__lte=datetime.now())
    registros.update(lida=True)

    RegistroNotificacao.limpar_cache(request.user)
    return httprr(url_origem, 'Todas as suas notificações foram marcadas como lida com sucesso.')


@permission_required('comum.view_registronotificacao')
def excluir_notificacoes_antigas(request):
    url_origem = request.META.get('HTTP_REFERER', '.')
    notificacoes_antigas = RegistroNotificacao.objects.filter(
        vinculo=request.user.get_vinculo(), lida=True, data__lt=somar_dias(datetime.today(), -30)
    )
    notificacoes_antigas.delete()

    RegistroNotificacao.limpar_cache(request.user)
    return httprr(url_origem, 'Todas as suas notificações lidas há mais de um mês foram excluídas.')


@permission_required('comum.view_registronotificacao')
def marcar_como_lida_em_lote(request):
    url_origem = request.META.get('HTTP_REFERER', '.')
    ids = ids_da_query(request)
    for pk in ids:
        registro = get_object_or_404(RegistroNotificacao, pk=pk, vinculo=request.user.get_vinculo())
        if registro.pode_ler():
            registro.lida = True
            registro.save()

    RegistroNotificacao.limpar_cache(request.user)
    return httprr(url_origem, 'Notificações marcadas como lida com sucesso.')


@permission_required('comum.view_registronotificacao')
def marcar_como_nao_lida(request, pk):
    registro = get_object_or_404(RegistroNotificacao, pk=pk)
    if registro.vinculo == request.user.get_vinculo():
        registro.lida = False
        registro.save()
    else:
        raise PermissionDenied('Você não pode marcar esta notificação como não lida.')

    RegistroNotificacao.limpar_cache(request.user)
    return HttpResponse('OK')


@permission_required('comum.view_registronotificacao')
def marcar_como_nao_lida_em_lote(request):
    url_origem = request.META.get('HTTP_REFERER', '.')
    ids = ids_da_query(request)
    for pk in ids:
        registro = get_object_or_404(RegistroNotificacao, pk=pk, vinculo=request.user.get_vinculo())
        registro.lida = False
        registro.save()

    RegistroNotificacao.limpar_cache(request.user)
    return httprr(url_origem, 'Notificações marcadas como não lidas com sucesso.')


@permission_required('comum.view_registronotificacao')
def remover_notificacao(request, pk):
    opcao = request.GET.get('opcao')
    if opcao == '1':  # veio da url de visualizacao da notificacao
        url = '/'
    else:
        url = request.META.get('HTTP_REFERER', '.')
    registro = get_object_or_404(RegistroNotificacao, pk=pk, vinculo=request.user.get_vinculo())
    if registro.vinculo == request.user.get_vinculo():
        if registro.pode_excluir():
            registro.delete()
        else:
            data = format_(registro.data_permite_excluir)
            return httprr(url, f'O registro só poderá excluído em {data}.', 'error')
    else:
        raise PermissionDenied('Você não tem permissão de acesso a essa página.')

    RegistroNotificacao.limpar_cache(request.user)
    return httprr(url, 'A notificação foi removida com sucesso.')


@permission_required('comum.view_registronotificacao')
def remover_notificacoes_em_lote(request):
    url_origem = request.META.get('HTTP_REFERER', '.')
    ids = ids_da_query(request)
    agora = datetime.now()
    for pk in ids:
        registro = get_object_or_404(RegistroNotificacao, pk=pk, vinculo=request.user.get_vinculo())
        if registro.data_permite_excluir <= agora:
            registro.delete()

    RegistroNotificacao.limpar_cache(request.user)
    return httprr(url_origem, 'Notificações removidas com sucesso.')


@rtr()
@permission_required('comum.change_prestadorservico')
def criar_papel_usuario_externo(request, prestador_id):
    usuarioexterno = get_object_or_404(PrestadorServico, pk=prestador_id)
    # Cria o papel e ativa o usuário externo
    usuarioexterno.criar_papel_usuario_externo()

    if usuarioexterno.tem_papel_ativo_usuario_externo():
        return httprr('/admin/comum/prestadorservico/', message='Papel de Usuário Externo Criado com Sucesso.', tag='success')
    return locals()


@group_required('Coordenador de TI sistêmico')
def ativar_usuario_externo(request, pk):
    usuarioexterno = get_object_or_404(PrestadorServico, pk=pk)
    usuarioexterno.ativar()

    if usuarioexterno.ativo:
        return httprr('/admin/comum/prestadorservico/', message='Usuário Externo Ativado com Sucesso.', tag='success')

    return locals()


@rtr()
@group_required('Coordenador de TI sistêmico')
def inativar_usuario_externo(request, pk):
    usuarioexterno = get_object_or_404(PrestadorServico, pk=pk)
    usuarioexterno.inativar()
    if not usuarioexterno.ativo:
        return httprr('/admin/comum/prestadorservico/', message='Usuário Externo Desativado com Sucesso.', tag='success')

    return locals()


@rtr()
@permission_required('comum.view_predio')
def predio(request: HttpRequest, pk: int) -> dict:
    obj = get_object_or_404(Predio, pk=pk)
    obra_original = obj.get_obra_original()
    ampliacoes = obj.get_ampliacoes()
    reformas = obj.get_reformas()
    combates = obj.get_combates_incendio_panico()
    title = str(obj)
    return locals()


@rtr()
@permission_required('comum.view_solicitacaoreservasala')
def salas_disponiveis(request):
    title = 'Listagem de Salas Disponíveis'
    form = RelatorioSalasDisponiveisForm(data=request.GET or None)
    if form.is_valid():
        datas = form.processar()
    return locals()


def robots(request):
    return HttpResponse('User-agent: *\nAllow: /accounts/login/$\nDisallow: /', content_type='text/plain')


@rtr()
@login_required()
def validar_qrcode_2fa_otp(request):
    title = 'Validar Autenticação por Dois Fatores'
    auths_2fa_user = AutenticacaoDoisFatores.objects.filter(usuario=request.user, tipo=AutenticacaoDoisFatores.OTP).first()
    url = '/comum/minha_conta/'
    if (auths_2fa_user is None) or (not auths_2fa_user.ativo):
        return httprr(url, message='A autenticação por Dois Fatores não está habilitada.', tag='alert')
    #
    form = AutenticacaoDoisFatoresForm(request.POST or None, request=request, auths_2fa_user=auths_2fa_user)
    if form.is_valid():
        auths_2fa_user.validar_qrcode()
        auths_2fa_user.save()
        return httprr(url, message='A autenticação por Dois Fatores está ativida.')
    #
    instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')
    img_str_base64 = auths_2fa_user.get_qrcode_image(instituicao)
    return locals()


@rtr()
@login_required()
def habilitar_2fa_suap(request: HttpRequest) -> dict | HttpResponse:
    #
    title = 'Habilitar Autenticação por Dois Fatores'
    # O OneToOne admite um registro por usuário: busca só por ``usuario`` e fixa o ``tipo``, que o
    # interruptor da Minha conta (``ativar_autenticacao_dois_fatores``) cria vazio (#17391).
    auths_2fa_user, _ = AutenticacaoDoisFatores.objects.update_or_create(
        usuario=request.user,
        defaults={'tipo': AutenticacaoDoisFatores.OTP},
    )
    url = '/comum/minha_conta/'
    if auths_2fa_user.ativo and auths_2fa_user.validou_qrcode():
        return httprr(url, message='A autenticação por Dois Fatores está habilitada.', tag='alert')
    #
    form = AutenticacaoDoisFatoresForm(request.POST or None, request=request, auths_2fa_user=auths_2fa_user)
    if form.is_valid():
        auths_2fa_user.ativar()
        auths_2fa_user.save()
        try:
            LogEntry.objects.log_action(
                user_id=request.user.pk,
                content_type_id=get_content_type_for_model(request.user).pk,
                object_id=request.user.pk,
                object_repr=force_str(request.user),
                action_flag=CHANGE,
                change_message='Autenticação por Dois Fatores habilitada.',
            )
        except Exception:
            pass
        return httprr(url, message='A autenticação por Dois Fatores está habilitada.')
    #
    instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')
    img_str_base64 = auths_2fa_user.get_qrcode_image(instituicao)

    return locals()


@login_required()
def remover_2fa_suap(request):
    try:
        AutenticacaoDoisFatores.objects.filter(usuario=request.user, tipo=AutenticacaoDoisFatores.OTP).delete()
        mensagem = 'Autenticação com dois fatores removida com sucesso'
        level = messages.SUCCESS
        try:
            LogEntry.objects.log_action(
                user_id=request.user.pk,
                content_type_id=get_content_type_for_model(request.user).pk,
                object_id=request.user.pk,
                object_repr=force_str(request.user),
                action_flag=CHANGE,
                change_message=mensagem,
            )
        except Exception:
            pass
    except Exception as e:
        capture_exception(e)
        if settings.DEBUG:
            raise e
        mensagem = 'Ocorreu um erro ao remover autenticação com dois fatores'
        level = messages.ERROR
    messages.add_message(request, level=level, message=mensagem)
    return httprr('/comum/minha_conta/')


@login_required()
def desabilitar_2fa_usuario(request, usuario_pk):
    """Permissão: apenas superuser.
    Exibe um formulário para informar o motivo (GET) e, ao enviar (POST),
    remove a autenticação em dois fatores do usuário informado e registra o motivo
    no `change_message` do `LogEntry`.
    """
    if not request.user.is_superuser:
        raise PermissionDenied

    User = apps.get_model('comum', 'User')
    user = get_object_or_404(User, pk=usuario_pk)

    # Se usuário alvo não tem 2FA ativo, não há nada a fazer
    if not user.autenticacaodoisfatores_habilitada():
        messages.add_message(request, messages.INFO, 'O usuário não possui 2FA ativo.')
        return httprr(request.META.get('HTTP_REFERER', '..'))

    from comum.forms import Desabilitar2FAForm

    if request.method == 'GET':
        form = Desabilitar2FAForm(request=request)
        title = f'Desabilitar 2FA - {user}'
        return render(
            request,
            'comum/templates/comum/desabilitar_2fa_usuario.html',
            {'user_target': user, 'title': title, 'form': form},
        )

    # POST: efetua a remoção com motivo via form
    form = Desabilitar2FAForm(request.POST, request=request)
    if not form.is_valid():
        title = f'Desabilitar 2FA - {user}'
        return render(
            request,
            'comum/templates/comum/desabilitar_2fa_usuario.html',
            {'user_target': user, 'title': title, 'form': form},
        )

    motivo = form.cleaned_data.get('motivo', '').strip()
    try:
        AutenticacaoDoisFatores.objects.filter(usuario=user).delete()
        mensagem = f'Autenticação com dois fatores removida para {user.username}'
        if motivo:
            mensagem = f'{mensagem} Motivo: {motivo}'
        level = messages.SUCCESS
        try:
            LogEntry.objects.log_action(
                user_id=request.user.pk,
                content_type_id=get_content_type_for_model(user).pk,
                object_id=user.pk,
                object_repr=force_str(user),
                action_flag=CHANGE,
                change_message=mensagem,
            )
        except Exception:
            pass
    except Exception as e:
        capture_exception(e)
        if settings.DEBUG:
            raise e
        mensagem = 'Ocorreu um erro ao remover autenticação com dois fatores'
        level = messages.ERROR

    messages.add_message(request, level=level, message=mensagem)
    referer = request.META.get('HTTP_REFERER', '') or ''
    # Se o referer for a própria página de desabilitar 2FA (ou estiver ausente),
    # redireciona para o admin de usuários para evitar loop.
    if not referer or f'desabilitar_2fa_usuario/{user.pk}' in referer:
        redirect_url = '/admin/comum/user/'
    else:
        redirect_url = referer

    return httprr(redirect_url)


@login_required()
def ativar_autenticacao_dois_fatores(request):
    try:
        if not AutenticacaoDoisFatores.objects.filter(usuario=request.user).exists():
            # O ``save`` já gera o ``otp_secret_user`` na criação, então o ``tipo`` atribuído no ramo
            # ``if not otp_secret_user`` abaixo nunca rodava e a linha nascia com ``tipo=''`` (#17391).
            AutenticacaoDoisFatores.objects.create(usuario=request.user, tipo=AutenticacaoDoisFatores.OTP)

        if not request.user.autenticacaodoisfatores_habilitada():
            if not request.user.autenticacaodoisfatores.otp_secret_user:
                request.user.autenticacaodoisfatores.otp_secret_user = base64.b32encode(os.urandom(10)).decode('utf-8')
                request.user.autenticacaodoisfatores.tipo = AutenticacaoDoisFatores.OTP
            request.user.autenticacaodoisfatores.ativo = True
            request.user.autenticacaodoisfatores.data_ultima_ativacao = datetime.now()
            request.user.autenticacaodoisfatores.save()
        else:
            request.user.autenticacaodoisfatores.ativo = False
            request.user.autenticacaodoisfatores.data_ultima_desativacao = datetime.now()
            request.user.autenticacaodoisfatores.save()
        return HttpResponse('OK', status=200)
    except Exception as e:
        if settings.DEBUG:
            raise e
        return HttpResponse('ERROR', status=400)


@login_required()
@group_required('Desenvolvedor')
def trigger_error(request):
    return 1 / 0


@login_required()
def suap_logout(request):
    try:
        utiliza_autenticacao_gov_br = Configuracao.get_valor_por_chave('comum', 'habilitar_autenticacao_govbr')
        if utiliza_autenticacao_gov_br and request.session.get('autenticou_com_govbr', False):
            logout(request)
            return HttpResponseRedirect(settings.GOVBR['LOGOUT_URL'])
        logout(request)
    except Exception as e:
        capture_exception(e)
    return redirect('/')


def healthcheck(request):
    data = {'status': 'OK'}
    status = 200
    tempos = {}
    inicio_total = time.perf_counter()

    def _cronometrar(nome, funcao):
        inicio = time.perf_counter()
        try:
            return funcao()
        finally:
            tempos[nome] = round(time.perf_counter() - inicio, 6)

    def _checar_ldap():
        if not is_ldap_enabled():
            return
        conf = get_ldap_conf()
        if not conf:
            raise Exception('Nenhum serviço de LDAP ativo configurado')
        if not conf.has_connectivity():
            raise Exception('Falha na conectividade com o servidor LDAP')

    def _checar_arquivo_status():
        arquivo = f'{settings.BASE_DIR}/deploy/status.txt'
        with open(arquivo) as f:
            if 'healthy' not in f.read():
                raise Exception(f'Arquivo {arquivo} não tem o texto "healthy".')

    try:
        _cronometrar('banco', User.objects.exists)
        ip = get_client_ip(request)
        data['ip'] = ip
        server_alias = getattr(settings, 'SERVER_ALIAS', '')
        if settings.DEBUG and request.GET.get('request') == 'meta':
            data['request.meta'] = {k: str(v) for k, v in request.META.items()}
        _cronometrar('ldap', _checar_ldap)
        _cronometrar('arquivo_status', _checar_arquivo_status)
        data['host'] = server_alias and f'{server_alias} - {socket.gethostname()}' or socket.gethostname()
    except Exception as e:
        data = {'status': 'ERROR', 'detail': str(e)}
        status = 423
    data['tempos'] = tempos
    data['tempo_total'] = round(time.perf_counter() - inicio_total, 6)
    return JsonResponse(data, status=status)


@login_required()
@csrf_exempt
def get_subojetivos_ods_onu(request: HttpRequest) -> JsonResponse:
    options = []
    if request.method == 'GET':
        # Sem objetivo escolhido a lista fica vazia, não "todos": é autocomplete (#17395).
        registros = SubobjetivoDesenvolvimentoSustentavel.objects.filter(ativo=True, objetivo__in=ids_da_query(request))
        if registros.exists():
            for registro in registros:
                options.append({'id': registro.id, 'text': f'{registro.numero} - {registro.descricao}'})
    return JsonResponse({'results': options})


@rtr('calendario_orgao_colegiado_superior.html')
@login_required()
@permission_required('comum.pode_consultar_calendarios')
def orgaos_colegiados_reunioes_consultar_calendario(request):
    title = 'Calendário de Reuniões de Órgãos Colegiados Superiores'
    form = ReuniaoOrgaoColegiadoConsultarForm(request.GET or None)
    form_collapsed = ''
    if form.is_valid():
        form_collapsed = 'collapsed'
        try:
            calendario_dados = ReuniaoOrgaoColegiado.obter_calendario_reuniao_orgao_colegiado(
                data_inicio=form.get_data_inicio(), data_fim=form.get_data_fim()
            )
            eh_formato_mensal = form.eh_formato_mensal()
            calendario_html = CalendarioReuniaoOrgaoColegiadoHTML(
                calendario_dados,
                formato=CalendarioMix.FORMATO_MENSAL if eh_formato_mensal else CalendarioMix.FORMATO_ANUAL,
                legenda=CalendarioMix.LEGENDA_NO_COMECO_DO_MES if eh_formato_mensal else CalendarioMix.LEGENDA_DENTRO_CALENDARIO,
            )
        except Exception as error:
            form.add_error(None, error)
            form_collapsed = ''
    pode_visualizar_listagem = request.user.has_perm('comum.view_reuniaoorgaocolegiado')
    return locals()


@rtr('detalhar_reuniao_orgao_colegiado_superior.html')
@login_required()
@permission_required('comum.pode_consultar_calendarios')
def orgaos_colegiados_detalhar_reuniao(request, reuniao_id):
    title = 'Reunião de Órgão Colegiado Superior'
    reuniao = get_object_or_404(ReuniaoOrgaoColegiado, pk=reuniao_id)
    reuniao_view = ReuniaoOrgaoColegiadoView(reuniao)
    pode_editar = request.user.has_perm('comum.change_reuniaoorgaocolegiado')
    pode_remover = request.user.has_perm('comum.delete_reuniaoorgaocolegiado')
    pode_visualizar_listagem = request.user.has_perm('comum.view_reuniaoorgaocolegiado')
    pode_consultar_calendarios = request.user.has_perm('comum.pode_consultar_calendarios')
    return locals()


@rtr()
@login_required()
def cadastrar_atalho(request):
    title = 'Adicionar atalho'
    url = base64.b64decode(request.GET['url'].encode()).decode()
    initial = {'url': url}
    form = CadastrarAtalhoForm(data=request.POST or None, request=request, initial=initial)
    if form.is_valid():
        form.save()
        return httprr('..', 'Atalho cadastrado com sucesso', close_popup=True)
    return locals()
