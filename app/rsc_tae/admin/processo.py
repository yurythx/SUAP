import datetime
import logging
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import BooleanField, Case, CharField, Exists, F, OuterRef, Prefetch, Q, QuerySet, Subquery, Value, When
from django.http import HttpRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse
from django.utils.formats import number_format
from django.utils.html import format_html
from django.utils.safestring import SafeString, mark_safe
from djtools.contrib.admin import ModelAdminPlus, CustomTabListFilter

from rh.models import Servidor

from rsc_tae.enums import SituacaoDocumentoPreliminar, SituacaoProcesso, TipoDocumentoPreliminar
from rsc_tae.forms import ProcessoRSCTaeAdminForm
from rsc_tae.views._permissoes import PermissoesProcesso
from rsc_tae.views._helpers import _montar_resumo_preenchimento, _rh_sistemico, codigos_situacao_exercicio_externo
from rsc_tae.models import (
    AvaliacaoAnexoRSCTae,
    AvaliacaoProcessoRSCTae,
    DocumentoPreliminarRSCTae,
    OrigemTransicao,
    ProcessoRSCTae,
    RolSaberCompetenciaAnexo,
    RolSaberCompetenciaPreenchimento,
)


logger = logging.getLogger(__name__)


class MarcadorSimNaoListFilter(admin.SimpleListFilter):
    """Base dos filtros Sim/Não que atuam sobre as anotações de marcadores da listagem.

    As subclasses declaram apenas ``title``, ``parameter_name`` e ``lookup_sim`` — um
    ``Q`` que define o lado "Sim"; o lado "Não" é a negação dele. Só é registrado para
    quem pode ver os marcadores (ver ``ProcessoRSCTaeAdmin.get_list_filter``), então as
    anotações de que ele depende sempre existem no queryset.
    """

    lookup_sim: Q

    def lookups(self, request: HttpRequest, model_admin) -> tuple[tuple[str, str], ...]:
        return (('1', 'Sim'), ('0', 'Não'))

    def queryset(self, request: HttpRequest, queryset: QuerySet) -> QuerySet:
        if self.value() == '1':
            return queryset.filter(self.lookup_sim)
        if self.value() == '0':
            return queryset.exclude(self.lookup_sim)
        return queryset


class PcdListFilter(MarcadorSimNaoListFilter):
    """Servidor com deficiência cadastrada no RH (``comum.Vinculo.deficiencia``)."""

    title = 'PCD'
    parameter_name = 'rsc_pcd'
    lookup_sim = Q(_rsc_pcd=True)


class ExercicioExternoListFilter(MarcadorSimNaoListFilter):
    """Servidor em uma das situações configuradas como exercício externo ao órgão."""

    title = 'Exercício externo'
    parameter_name = 'rsc_exercicio_externo'
    lookup_sim = Q(_rsc_situacao_externa__isnull=False)


class Idade60MaisListFilter(MarcadorSimNaoListFilter):
    """Servidor com 60 anos ou mais, pela data de nascimento cadastrada no RH."""

    title = '60 anos ou mais'
    parameter_name = 'rsc_60_mais'
    lookup_sim = Q(_rsc_60_mais=True)


def _badges_marcadores(obj: ProcessoRSCTae) -> SafeString:
    """Badges de PCD / exercício externo / 60+ a partir das anotações de ``_anotar_marcadores``.

    Retorna vazio quando as anotações não existem — o caso de quem não pode vê-las.
    """
    partes = []
    if getattr(obj, '_rsc_pcd', False):
        partes.append(mark_safe('<span class="status status-info" title="Servidor com deficiência cadastrada no RH">PCD</span>'))
    situacao = getattr(obj, '_rsc_situacao_externa', None)
    if situacao:
        partes.append(format_html('<span class="status status-alert" title="Situação funcional: {}">Exercício externo</span>', situacao))
    if getattr(obj, '_rsc_60_mais', False):
        partes.append(mark_safe('<span class="status status-info" title="Servidor com 60 anos ou mais">60+</span>'))
    return mark_safe(' '.join(partes))


@admin.register(ProcessoRSCTae)
class ProcessoRSCTaeAdmin(ModelAdminPlus):
    form = ProcessoRSCTaeAdminForm
    list_display_icons = True
    list_display = (
        'get_servidor_info',
        'nivel_requisitado',
        'get_prazo',
        'get_resumo_preenchimento',
        'get_acoes',
    )
    search_fields = ProcessoRSCTae.SEARCH_FIELDS
    list_filter = (CustomTabListFilter, 'nivel_requisitado', 'avaliadores')
    show_count_on_tabs = True
    show_tab_any_data = False
    ordering = ('-data_cadastro',)
    readonly_fields = (
        'vinculo',
        'nivel_requisitado',
        'saldo_pontuacao_anterior',
        'processo_anterior',
    )

    def _aba_ativa(self, request) -> str:
        """Aba selecionada. Sem ``?tab=`` o CustomTabListFilter cai na primeira de ``get_all_tabs``."""
        selecionada = request.GET.get('tab')
        if selecionada:
            return selecionada
        abas = self.get_all_tabs(request)
        return abas[0] if abas else ''

    # Abas em que a posição na fila é exibida: a do servidor e as três etapas que têm fila.
    # "Todos" e "Finalizados" ficam de fora — misturam etapas e processos sem fila, onde a coluna
    # seria uma coluna de traços.
    # Aba -> situação cuja fila ela exibe. "Meus processos" mistura etapas (o servidor pode ter
    # processo em qualquer uma), então pede o mapa completo, representado por None.
    SITUACAO_DA_ABA = {
        'tab_meus_processos': None,
        'tab_aguardando_validacao': SituacaoProcesso.AGUARDANDO_VALIDACAO_DOCUMENTO_PRELIMINAR,
        'tab_processos_em_analise': SituacaoProcesso.EM_ANALISE,
        'tab_aguardando_crsc': SituacaoProcesso.AGUARDANDO_CRSC,
    }

    def get_list_display(self, request):
        """Acrescenta a posição na fila nas abas de ``ABAS_COM_POSICAO``."""
        colunas = list(super().get_list_display(request))
        if self._aba_ativa(request) in self.SITUACAO_DA_ABA:
            colunas.insert(colunas.index('get_prazo'), 'get_posicao_fila')
        # Tupla, como a base devolve: o ModelAdminPlus pode prefixar 'show_list_display_icons'.
        return tuple(colunas)

    def _mapa_de_posicoes(self):
        """Fila de cada etapa, calculada UMA vez por requisição e reusada por todas as linhas.

        Sem este cache a coluna faria duas consultas por linha, e nas abas que listam a etapa
        inteira isso seria um N+1. O cache é chaveado pelo próprio ``request`` (o admin já guarda
        ``self._request``), então uma requisição nunca lê o mapa de outra.

        O mapa é montado a partir da etapa INTEIRA, de propósito: se fosse derivado do queryset já
        filtrado da listagem, buscar por nome ou filtrar por nível renumeraria a fila de 1 a N e
        mostraria uma posição falsa.

        Nas abas de etapa só a fila daquela etapa é calculada. "Meus processos" pede o mapa
        completo porque os processos do servidor podem estar em etapas diferentes.
        """
        request = getattr(self, '_request', None)
        situacao = self.SITUACAO_DA_ABA.get(self._aba_ativa(request)) if request else None

        cache = getattr(self, '_cache_posicoes', None)
        if cache is not None and cache['request'] is request and cache['situacao'] == situacao:
            return cache['mapa']

        mapa = ProcessoRSCTae.mapa_de_posicoes(situacao)
        self._cache_posicoes = {'request': request, 'situacao': situacao, 'mapa': mapa}
        return mapa

    @admin.display(description='Posição na fila')
    def get_posicao_fila(self, obj: ProcessoRSCTae):
        """Onde o processo está na fila da etapa atual. ``—`` quando não há fila (ou já acabou)."""
        fila = self._mapa_de_posicoes().get(obj.pk)
        if not fila:
            return '—'
        titulo = (
            'Ordem de entrada nesta etapa, a mesma em que a comissão vê os processos. '
            'É uma referência de fila, não uma garantia de que o atendimento seguirá exatamente essa sequência.'
        )
        return format_html('<span class="status status-info" title="{}">{}º de {}</span>', titulo, fila['posicao'], fila['total'])

    def get_tabs(self, request):
        result = [
            'tab_meus_processos',
            'tab_aguardando_preenchimento',
            'tab_aguardando_validacao',
            'tab_aguardando_correcao',
            'tab_processos_em_analise',
            'tab_aguardando_crsc',
            'tab_processos_finalizados',
            'tab_todos',
        ]
        return result

    @admin.display(description='Meus processos')
    def tab_meus_processos(self, request, queryset):
        """Retorna queryset com os processos do usuário logado (dono)."""
        try:
            vinculo_usuario = request.user.get_vinculo()
        except Exception:
            return queryset.none()
        return queryset.filter(vinculo=vinculo_usuario)

    @admin.display(description='Aguardando preenchimento')
    def tab_aguardando_preenchimento(self, request, queryset):
        return queryset.filter(situacao=SituacaoProcesso.AGUARDANDO_PREENCHIMENTO)

    @admin.display(description='Em análise')
    def tab_processos_em_analise(self, request, queryset):
        return queryset.filter(situacao=SituacaoProcesso.EM_ANALISE)

    @admin.display(description='Aguardando validação')
    def tab_aguardando_validacao(self, request, queryset):
        return queryset.filter(situacao=SituacaoProcesso.AGUARDANDO_VALIDACAO_DOCUMENTO_PRELIMINAR)

    @admin.display(description='Aguardando correção')
    def tab_aguardando_correcao(self, request, queryset):
        return queryset.filter(situacao=SituacaoProcesso.AGUARDANDO_CORRECAO)

    @admin.display(description='Aguardando CRSC')
    def tab_aguardando_crsc(self, request, queryset):
        return queryset.filter(situacao=SituacaoProcesso.AGUARDANDO_CRSC)

    @admin.display(description='Finalizados')
    def tab_processos_finalizados(self, request, queryset):
        return queryset.filter(situacao__in=[SituacaoProcesso.DEFERIDO, SituacaoProcesso.INDEFERIDO])

    @admin.display(description='Todos')
    def tab_todos(self, request, queryset):
        return queryset

    fieldsets = (
        (
            None,
            {
                'fields': (
                    'vinculo',
                    'nivel_requisitado',
                    'avaliadores',
                    'situacao',
                    'avaliacao_motivo_indeferimento',
                )
            },
        ),
        (
            'Informações complementares',
            {
                'fields': (
                    'saldo_pontuacao_anterior',
                    'processo_anterior',
                ),
                'classes': ('collapse',),
            },
        ),
    )

    def _eh_membro_crsc_ativo(self, request):
        """Se o usuário da request é membro ativo da CRSC — cacheado na request (evita uma query por linha da listagem)."""
        if not hasattr(request, '_rsc_tae_eh_membro_crsc_ativo'):
            from rsc_tae.views._helpers import eh_membro_crsc_ativo

            try:
                vinculo_usuario = request.user.get_vinculo()
            except Exception:
                vinculo_usuario = None
            request._rsc_tae_eh_membro_crsc_ativo = eh_membro_crsc_ativo(vinculo_usuario)
        return request._rsc_tae_eh_membro_crsc_ativo

    def _pode_ver_marcadores(self, request) -> bool:
        """Se o usuário pode ver os marcadores de PCD, exercício externo e 60+ — RH sistêmico ou CRSC.

        Deficiência e idade são dados sensíveis e a avaliação é cega: o avaliador designado,
        que também enxerga esta listagem, fica de fora. Cacheado na request como os demais gates.
        """
        if not hasattr(request, '_rsc_tae_pode_ver_marcadores'):
            request._rsc_tae_pode_ver_marcadores = bool(
                request.user.is_superuser or _rh_sistemico(request.user) or self._eh_membro_crsc_ativo(request)
            )
        return request._rsc_tae_pode_ver_marcadores

    def _anotar_marcadores(self, qs: QuerySet[ProcessoRSCTae]) -> QuerySet[ProcessoRSCTae]:
        """Anota PCD, a situação de exercício externo e 60+ do servidor, sem N+1.

        ``Vinculo.relacionamento`` é uma GenericForeignKey, então a situação funcional não
        é alcançável por ``__``: chega-se ao Servidor por subquery em ``id_relacionamento``,
        com guarda de content type — sem ela, um vínculo de outro tipo que tenha o mesmo pk
        de um Servidor produziria falso positivo.

        Sem situações configuradas a lista de códigos é vazia e ninguém é sinalizado.
        """
        codigos = codigos_situacao_exercicio_externo(self._configuracao_rsc())
        # date.today e não timezone.localdate: o projeto roda com USE_TZ=False e localdate()
        # levanta ValueError sobre datetime naive nesse modo
        data_corte_60_anos = datetime.date.today() - relativedelta(years=60)
        return (
            qs.annotate(
                # deficiência é campo do próprio Vinculo, já em select_related — nada de subquery aqui
                _rsc_pcd=Q(vinculo__deficiencia__isnull=False),
                # nascimento_data é alcançável por join direto (Vinculo -> Pessoa -> PessoaFisica); Case
                # em vez de Q puro porque sem data cadastrada o lookup __lte compara com NULL (SQL
                # trivalorado) e um Q viraria None em vez de False
                _rsc_60_mais=Case(
                    When(vinculo__pessoa__pessoafisica__nascimento_data__lte=data_corte_60_anos, then=Value(True)),
                    default=Value(False),
                    output_field=BooleanField(),
                ),
            )
            .alias(
                # alias e não annotate: o valor bruto só serve de insumo para o Case abaixo. Como
                # annotate ele iria também ao SELECT e a subquery correlacionada seria emitida duas
                # vezes por linha (uma na coluna, outra dentro do CASE, que inlina a expressão).
                _rsc_situacao_externa_bruta=Subquery(
                    Servidor.objects.filter(pk=OuterRef('vinculo__id_relacionamento'), situacao__codigo__in=codigos).values('situacao__nome')[:1]
                ),
            )
            .annotate(
                _rsc_situacao_externa=Case(
                    When(vinculo__tipo_relacionamento__model='servidor', then=F('_rsc_situacao_externa_bruta')),
                    default=None,
                    output_field=CharField(),
                )
            )
        )

    def get_list_filter(self, request):
        """Esconde o filtro por avaliador de quem não é da CRSC — a lotação da avaliação é assunto da comissão."""
        list_filter = list(super().get_list_filter(request))
        if not (request.user.is_superuser or self._eh_membro_crsc_ativo(request)) and 'avaliadores' in list_filter:
            list_filter.remove('avaliadores')
        if self._pode_ver_marcadores(request):
            list_filter += [PcdListFilter, ExercicioExternoListFilter, Idade60MaisListFilter]
        return list_filter

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        # Alterar avaliadores pelo admin equivale a remanejar — ato restrito à CRSC
        # (fecha a porta lateral para a sistêmica, que tem change_processorsctae).
        if not (request.user.is_superuser or self._eh_membro_crsc_ativo(request)):
            readonly.append('avaliadores')
        return readonly

    def get_queryset(self, request):
        # Armazena request para uso em métodos de list_display
        self._request = request
        qs = (
            super()
            .get_queryset(request)
            .select_related('nivel_requisitado', 'vinculo', 'vinculo__pessoa')
            .prefetch_related('nivel_requisitado__iq_equivalente')
            .prefetch_related('avaliadores', 'avaliadores__pessoa')
            .prefetch_related(
                Prefetch(
                    'rolsabercompetenciaanexo_set',
                    queryset=RolSaberCompetenciaAnexo.objects.filter(rol_saber_competencia__ativo=True)
                    .select_related('rol_saber_competencia__grupo__requisito')
                    .prefetch_related(
                        Prefetch(
                            'avaliacoes',
                            queryset=AvaliacaoAnexoRSCTae.objects.only('id', 'anexo_id', 'avaliador_vinculo_id'),
                        )
                    )
                    .only(
                        'id',
                        'processo_id',
                        'rol_saber_competencia_id',
                        'pontuacao',
                        'rol_saber_competencia__grupo__pontuacao_unidade',
                        'rol_saber_competencia__grupo__requisito__id',
                    ),
                ),
                Prefetch(
                    'vinculo__rolsabercompetenciapreenchimento_set',
                    queryset=RolSaberCompetenciaPreenchimento.objects.filter(
                        quantidade__gt=0,
                        rol_saber_competencia__ativo=True,
                    ).select_related('rol_saber_competencia'),
                ),
                Prefetch(
                    'avaliacoes_por_avaliador',
                    queryset=AvaliacaoProcessoRSCTae.objects.only(
                        'id',
                        'processo_id',
                        'avaliador_vinculo_id',
                        'finalizada',
                        'data_finalizacao',
                        'resultado',
                        'pontuacao_final',
                        'resposta',
                        'substituido',
                    ),
                ),
            )
        )

        # Anotações para exibir botões da etapa do documento preliminar sem N+1.
        # Importante: considerar sempre o ÚLTIMO documento enviado de CADA tipo obrigatório
        # (diploma/certificado + homologação do estágio probatório) — só conta como
        # existente/validado quando ambos os tipos estão presentes/validados.
        # Evita subqueries aninhadas com OuterRef (podem perder a correlação e sempre retornar False).
        tipo_diploma = TipoDocumentoPreliminar.DIPLOMA_CERTIFICADO
        tipo_homologacao = TipoDocumentoPreliminar.HOMOLOGACAO_ESTAGIO_PROBATORIO
        qs = qs.annotate(
            _doc_diploma_existe=Exists(DocumentoPreliminarRSCTae.objects.filter(processo_id=OuterRef('pk'), tipo=tipo_diploma)),
            _doc_homologacao_existe=Exists(DocumentoPreliminarRSCTae.objects.filter(processo_id=OuterRef('pk'), tipo=tipo_homologacao)),
            _doc_diploma_situacao=Subquery(
                DocumentoPreliminarRSCTae.objects.filter(processo_id=OuterRef('pk'), tipo=tipo_diploma)
                .order_by('-data_cadastro', '-pk')  # desempate
                .values('avaliacao__situacao')[:1]
            ),
            _doc_homologacao_situacao=Subquery(
                DocumentoPreliminarRSCTae.objects.filter(processo_id=OuterRef('pk'), tipo=tipo_homologacao)
                .order_by('-data_cadastro', '-pk')  # desempate
                .values('avaliacao__situacao')[:1]
            ),
        ).annotate(
            _doc_preliminar_existe=Case(
                When(Q(_doc_diploma_existe=True) & Q(_doc_homologacao_existe=True), then=Value(True)),
                default=Value(False),
                output_field=BooleanField(),
            ),
            _doc_preliminar_validado=Case(
                When(
                    Q(_doc_diploma_situacao=SituacaoDocumentoPreliminar.VALIDADO) & Q(_doc_homologacao_situacao=SituacaoDocumentoPreliminar.VALIDADO),
                    then=Value(True),
                ),
                default=Value(False),
                output_field=BooleanField(),
            ),
        )

        # Data de entrada na situação atual resolvida no próprio SELECT: sem ela, get_prazo
        # consultaria o histórico de situações uma vez por linha da listagem.
        qs = ProcessoRSCTae.anotar_sla_data_entrada(qs)

        # Marcadores PCD / exercício externo / 60+: anotados apenas para quem pode vê-los. O gate
        # é estrutural — o dado sensível nem entra no SELECT dos demais papéis.
        if self._pode_ver_marcadores(request):
            qs = self._anotar_marcadores(qs)

        # RH sistêmico: acesso total.
        if request.user.has_perm('rh.eh_rh_sistemico'):
            return qs

        try:
            vinculo_usuario = request.user.get_vinculo()
        except Exception:
            return qs.none()

        # Membro ativo da CRSC: vê todos os processos (valida documentos e delibera).
        from rsc_tae.views._helpers import eh_membro_crsc_ativo

        if eh_membro_crsc_ativo(vinculo_usuario):
            return qs

        # Se for um avaliador com permissão: vê os processos que ele avalia e os próprios processos.
        if request.user.has_perm('rsc_tae.avaliar_processorsctae'):
            return qs.filter(Q(avaliadores=vinculo_usuario) | Q(avaliador_atual=vinculo_usuario) | Q(vinculo=vinculo_usuario)).distinct()

        # Usuário comum: vê apenas o próprio processo.
        return qs.filter(vinculo=vinculo_usuario)

    def get_ordering(self, request):
        # Em toda aba, lista os processos do mais antigo para o mais recente pela data de
        # entrada na situação (aba) atual — expressão canônica do model (compartilhada com
        # Minhas Avaliações). Usa uma expressão autossuficiente (Subquery correlacionada)
        # em vez de um alias anotado porque o ModelAdmin.get_queryset base aplica a
        # ordenação antes das anotações. data_cadastro desempata.
        return [ProcessoRSCTae.expressao_data_entrada_situacao_atual().asc(), 'data_cadastro']

    @admin.display(description='Servidor')
    def get_servidor_info(self, obj: ProcessoRSCTae):
        vinculo = getattr(obj, 'vinculo', None)

        titulacao_atual = None
        try:
            relacionamento = vinculo.relacionamento if vinculo else None
            titulacao_atual = getattr(relacionamento, 'titulacao', None)
        except Exception:
            titulacao_atual = None

        try:
            titulacao_rsc = obj.rsc_equivalente()
        except Exception:
            titulacao_rsc = ''

        titulacao_atual_txt = str(titulacao_atual) if titulacao_atual else '—'
        titulacao_rsc_txt = titulacao_rsc or '—'

        return format_html(
            '<h3 class="mb-4 py-0">{} {}</h3><dl><dl><dt>Atual:</dt><dd>{}</dd><dt>Com RSC:</dt><dd>{}</dd></dl>',
            vinculo.relacionamento,
            _badges_marcadores(obj),
            titulacao_atual_txt,
            titulacao_rsc_txt,
        )

    @admin.display(description='Resumo')
    def get_resumo_preenchimento(self, obj: ProcessoRSCTae):
        """Resumo informativo do progresso do processo (pontuação + itens preenchidos).

        Delega ao cálculo canônico ``_montar_resumo_preenchimento`` (o mesmo usado
        no detalhe do processo) para garantir que a coluna do admin e a tela de
        detalhe nunca divirjam — em especial nos itens temporais, cuja pontuação
        depende da conversão meses → anos pontuáveis (``unidades_pontuaveis``).
        """

        pontos_minimos = getattr(getattr(obj, 'nivel_requisitado', None), 'pontuacao_minima', None) or Decimal('0')
        itens_minimos = getattr(getattr(obj, 'nivel_requisitado', None), 'numero_minimo_itens', None) or 0

        try:
            resumo = _montar_resumo_preenchimento(obj)
            total_pontos = resumo.get('resumo_preenchimento_total_pontos') or Decimal('0')
            itens_preenchidos = resumo.get('resumo_preenchimento_total_itens') or 0
        except Exception:
            total_pontos = Decimal('0')
            itens_preenchidos = 0

        total_pontos_txt = number_format(total_pontos, decimal_pos=2)
        pontos_min_txt = number_format(pontos_minimos, decimal_pos=2) if pontos_minimos and pontos_minimos > 0 else None

        pontos_ok = bool(pontos_minimos and pontos_minimos > 0 and total_pontos >= pontos_minimos)
        pontos_css = 'success' if pontos_ok else 'error'

        if pontos_min_txt:
            pontos_linha = f'{total_pontos_txt} / {pontos_min_txt} pts'
        else:
            pontos_linha = f'{total_pontos_txt} pts'

        itens_ok = bool(itens_minimos and itens_minimos > 0 and itens_preenchidos >= itens_minimos)
        itens_tem_meta = bool(itens_minimos and itens_minimos > 0)
        itens_css = 'success' if itens_ok else 'error'

        if itens_tem_meta:
            itens_linha = f'{itens_preenchidos} / {itens_minimos} itens'
        else:
            itens_linha = f'{itens_preenchidos} itens'

        return format_html(
            '<p class="checklist {pontos_css}">Pontos: {pontos_linha}</p><p class="checklist {itens_css}">Itens: {itens_linha}</p>',
            pontos_css=pontos_css,
            pontos_linha=pontos_linha,
            itens_css=itens_css,
            itens_linha=itens_linha,
        )

    def _configuracao_rsc(self):
        """ConfiguracaoRSCTae cacheada na request — sem isso o SLA custaria uma consulta por linha da listagem.

        Fora do fluxo de listagem (sem ``_request``) devolve None, e get_sla_status busca a
        configuração por conta própria.
        """
        request = getattr(self, '_request', None)
        if request is None:
            return None
        if not hasattr(request, '_rsc_tae_configuracao'):
            from rsc_tae.models import ConfiguracaoRSCTae

            request._rsc_tae_configuracao = ConfiguracaoRSCTae.objects.first()
        return request._rsc_tae_configuracao

    @admin.display(description='Prazo (SLA)')
    def get_prazo(self, obj: ProcessoRSCTae):
        sla = obj.get_sla_status(configuracao=self._configuracao_rsc())
        if not sla:
            return '-'
        dias_restantes = sla['dias_restantes']
        if sla['atrasado']:
            return mark_safe(f'<span class="status status-error" title="Prazo: {sla["dias_sla"]} dias">{abs(dias_restantes)} dia(s) em atraso</span>')
        if sla['alerta']:
            return mark_safe(f'<span class="status status-alert" title="Prazo: {sla["dias_sla"]} dias">{dias_restantes} dia(s) restante(s)</span>')
        return mark_safe(f'<span class="status status-info" title="Prazo: {sla["dias_sla"]} dias">{dias_restantes} dia(s) restante(s)</span>')

    @admin.display(description='Ações')
    def get_acoes(self, obj: ProcessoRSCTae):
        request = getattr(self, '_request', None)
        if not request:
            return '-'

        eh_avaliador, finalizada, pode_recusar_ou_impedir = self._flags_avaliador(request, obj)
        perms = PermissoesProcesso(request, obj).com_dados_avaliador(eh_avaliador=eh_avaliador, finalizada=finalizada)

        acoes = []
        acoes += self._acoes_servidor(obj, perms)
        acoes += self._acoes_avaliador(obj, perms, pode_recusar_ou_impedir)
        acoes += self._acoes_rh(request, obj, perms)
        acoes += self._acoes_documentos(obj, perms)
        acoes += self._acoes_processo_eletronico(request, obj)
        return self._render_acoes(obj, acoes)

    # ---- helpers de ações (coluna do list_display) ----

    def _flags_avaliador(self, request, obj):
        """Retorna (eh_avaliador, avaliacao_finalizada, pode_recusar_ou_impedir) usando os prefetches."""
        try:
            vinculo_usuario = request.user.get_vinculo()
        except Exception:
            vinculo_usuario = None
        if not vinculo_usuario:
            return False, False, False
        if not self._usuario_eh_avaliador(obj, vinculo_usuario):
            return False, False, False
        finalizada, pode_recusar = self._estado_avaliacao(obj, vinculo_usuario)
        return True, finalizada, pode_recusar

    def _usuario_eh_avaliador(self, obj, vinculo_usuario):
        try:
            if any(getattr(v, 'id', None) == vinculo_usuario.id for v in obj.avaliadores.all()):
                return True
        except Exception:
            pass
        return int(getattr(obj, 'avaliador_atual_id', 0) or 0) == int(vinculo_usuario.id)

    def _estado_avaliacao(self, obj, vinculo_usuario):
        try:
            for ap in obj.avaliacoes_por_avaliador.all():
                if getattr(ap, 'avaliador_vinculo_id', None) == vinculo_usuario.id:
                    finalizada = bool(getattr(ap, 'finalizada', False))
                    pode_recusar = not getattr(ap, 'substituido', True) and not finalizada
                    return finalizada, pode_recusar
        except Exception:
            pass
        return False, False

    def _acao(self, label, url_name, css, kwargs, *, target=False, popup=False, primary=False, confirm=None):
        return {
            'label': label,
            'url': reverse(url_name, kwargs=kwargs),
            'css': css,
            'target': target,
            'popup': popup,
            'primary': primary,
            'confirm': confirm,
        }

    def _acoes_servidor(self, obj, perms):
        if perms.eh_dono and obj.situacao in SituacaoProcesso.EDITAVEIS_PELO_SERVIDOR:
            return [self._acao('Preencher', 'rsc_tae:visualizar', 'primary', {'id': obj.pk}, primary=True)]
        return []

    def _acoes_avaliador(self, obj, perms, pode_recusar_ou_impedir):
        acoes = []
        if obj.situacao == SituacaoProcesso.EM_ANALISE and pode_recusar_ou_impedir:
            acoes.append(self._acao('Recusar', 'rsc_tae:recusar_avaliacao', 'danger', {'processo_id': obj.pk}))
            acoes.append(self._acao('Impedimento', 'rsc_tae:declarar_impedimento', 'warning', {'processo_id': obj.pk}))
        if perms.pode_avaliar:
            acoes.append(self._acao('Avaliar', 'rsc_tae:avaliar', 'success', {'processo_id': obj.pk}, primary=True))
        return acoes

    def _acoes_rh(self, request, obj, perms):
        acoes = []
        # Mesmo critério das views (_checar_permissao_validacao/remanejar_avaliador): membro
        # ativo da CRSC — a sistêmica tem definir_avaliador_processorsctae mas não pode agir,
        # então os botões não devem aparecer para ela.
        pode_rh = not perms.eh_dono and self._eh_membro_crsc_ativo(request)
        situacoes_validacao = (
            SituacaoProcesso.AGUARDANDO_VALIDACAO_DOCUMENTO_PRELIMINAR,
            SituacaoProcesso.AGUARDANDO_AVALIADOR,  # legado
        )
        if pode_rh and obj.situacao in situacoes_validacao:
            doc_existe = bool(getattr(obj, '_doc_preliminar_existe', False))
            label = 'Validar processo' if doc_existe else 'Validar processo (doc. pendente)'
            acoes.append(self._acao(label, 'rsc_tae:validar_processo', 'info', {'processo_id': obj.pk}, primary=True))
        if pode_rh and obj.situacao == SituacaoProcesso.EM_ANALISE:
            acoes.append(self._acao('Remanejar avaliador', 'rsc_tae:remanejar_avaliador', 'warning', {'processo_id': obj.pk}))
        if perms.pode_deliberar_crsc:
            acoes.append(self._acao('Deliberação CRSC', 'rsc_tae:deliberar_crsc', 'primary', {'processo_id': obj.pk}, primary=True))
        return acoes

    def _acoes_documentos(self, obj, perms):
        if not perms.pode_ver_resumo_avaliacao:
            return []
        acoes = []
        situacoes_com_resumo = (
            SituacaoProcesso.EM_ANALISE,
            SituacaoProcesso.AGUARDANDO_CRSC,
            SituacaoProcesso.DEFERIDO,
            SituacaoProcesso.INDEFERIDO,
        )
        if obj.situacao in situacoes_com_resumo:
            acoes.append(self._acao('Resumo', 'rsc_tae:resumo_avaliacao', 'default', {'processo_id': obj.pk}, popup=True))
        if obj.situacao in SituacaoProcesso.FINAIS:
            acoes.append(self._acao('Imprimir Relatório', 'rsc_tae:relatorio_avaliacao', 'default', {'processo_id': obj.pk}, target=True))
        if obj.situacao not in SituacaoProcesso.EDITAVEIS_PELO_SERVIDOR:
            acoes.append(self._acao('Processo Completo', 'rsc_tae:processo_completo_pdf', 'default', {'processo_id': obj.pk}, target=True))
        if obj.situacao == SituacaoProcesso.DEFERIDO:
            acoes.append(self._acao('Minuta Portaria', 'rsc_tae:minuta_portaria_pdf', 'default', {'processo_id': obj.pk}, target=True))
        return acoes

    def _acoes_processo_eletronico(self, request, obj):
        """Ação de gerar/ver processo eletrônico — só para finalizados e se o módulo estiver instalado."""
        from django.apps import apps

        if obj.situacao not in SituacaoProcesso.FINAIS or not apps.is_installed('processo_eletronico'):
            return []
        if getattr(obj, 'processo_eletronico_id', None):
            acoes = []
            try:
                url = obj.processo_eletronico.get_absolute_url()
            except Exception:
                url = None
            if url:
                acoes.append({'label': 'Acessar processo eletrônico', 'url': url, 'css': 'default', 'target': False, 'popup': False, 'primary': True})
            if request.user.is_superuser:
                acoes.append(
                    self._acao(
                        'Desvincular eletrônico',
                        'admin:rsc_tae_processorsctae_limpar_processo_eletronico',
                        'danger',
                        {'pk': obj.pk},
                        confirm='Desvincular o processo eletrônico deste RSC-TAE? Ele não será excluído, apenas desvinculado.',
                    )
                )
            return acoes
        if request.user.has_perm('rh.eh_rh_sistemico'):
            return [self._acao('Criar processo eletrônico', 'rsc_tae:criar_processo_eletronico', 'success', {'processo_id': obj.pk}, primary=True)]
        return []

    def _item_ver_avaliadores(self, obj):
        try:
            tem_avaliadores = bool(list(obj.avaliadores.all()))
        except Exception:
            tem_avaliadores = False
        if not tem_avaliadores:
            return None
        return self._acao('Ver avaliadores', 'rsc_tae:ver_avaliadores', 'default', {'processo_id': obj.pk}, popup=True)

    def _render_acoes(self, obj, acoes):
        item_avaliadores = self._item_ver_avaliadores(obj)
        if item_avaliadores:
            acoes = [*acoes, item_avaliadores]
        if not acoes:
            return '-'
        primaria = next((a for a in acoes if a.get('primary')), None)
        secundarias = [a for a in acoes if a is not primaria]
        partes = []
        if primaria:
            partes.append(str(self._html_item(primaria, 'btn ' + primaria['css'])))
        if secundarias:
            partes.append(str(self._html_dropdown(secundarias)))
        return mark_safe(' '.join(partes))

    def _html_item(self, acao, base_class):
        classe = base_class + (' popup' if acao.get('popup') else '')
        if acao.get('confirm'):
            # &#39; delimita a string JS; entidades HTML são decodificadas antes de o onclick rodar.
            # A mensagem (fixa, sem aspas) é escapada por format_html.
            return format_html(
                '<a class="{}" href="{}" onclick="return confirm(&#39;{}&#39;)">{}</a>', classe, acao['url'], acao['confirm'], acao['label']
            )
        if acao.get('target'):
            return format_html('<a class="{}" href="{}" target="_blank" rel="noopener">{}</a>', classe, acao['url'], acao['label'])
        return format_html('<a class="{}" href="{}">{}</a>', classe, acao['url'], acao['label'])

    def _html_dropdown(self, itens: list[dict]) -> SafeString:
        """Menu do Bootstrap 6: os itens ficam direto no ``.menu`` (o teclado só enxerga filhos diretos)."""
        corpo = mark_safe(''.join(str(self._html_item(a, 'dropdown-item menu-item')) for a in itens))
        return format_html(
            '<div class="dropdown rsc-acoes-dropdown">'
            '<button class="btn default dropdown-toggle" type="button" data-bs-toggle="menu" aria-expanded="false">Ações</button>'
            '<div class="dropdown-menu menu">{}</div>'
            '</div>',
            corpo,
        )

    def save_model(self, request, obj, form, change):
        """Grava a mudança de situação por ``transicionar()``, e não pelo save direto do campo.

        Salvar o campo sozinho não cria ``HistoricoSituacaoProcessoRSCTae``, e sem esse registro
        a expressão que ordena as listagens (``expressao_data_entrada_situacao_atual``) cai em
        ``data_cadastro``: o processo aparece no topo da fila da etapa em vez do fim.

        Os demais campos são gravados antes, ainda com a situação antiga — a transição só depois,
        de forma atômica, junto do histórico.
        """
        situacao_anterior = ProcessoRSCTae.objects.filter(pk=obj.pk).values_list('situacao', flat=True).first() if change else None
        if situacao_anterior is None or situacao_anterior == obj.situacao:
            super().save_model(request, obj, form, change)
            return

        destino = obj.situacao
        obj.situacao = situacao_anterior
        super().save_model(request, obj, form, change)
        obj.transicionar(
            destino,
            motivo=f'Alteração de situação pelo formulário do admin ({request.user}).',
            por_vinculo=self._vinculo_do_usuario(request),
            origem=OrigemTransicao.MANUAL,
        )

    def _vinculo_do_usuario(self, request):
        """Vínculo de quem salvou, para o histórico. ``None`` — com registro no log — quando não há.

        A falha não pode derrubar o salvamento, mas engoli-la calada esconderia um problema real
        (usuário sem vínculo, erro de configuração) atrás de uma transição registrada como
        "sistema" no histórico.
        """
        try:
            return request.user.get_vinculo()
        except Exception:
            logger.exception('Não foi possível resolver o vínculo de %s ao salvar um ProcessoRSCTae pelo admin.', request.user)
            return None

    def get_action_bar(self, request, remove_add_button=False):
        items = super().get_action_bar(request, remove_add_button=True)
        if self.has_add_permission(request) and getattr(request.user, 'eh_tecnico_administrativo', False):
            items.append(
                {
                    'url': reverse('rsc_tae:iniciar_processo'),
                    'label': format_html('<span class="fas fa-plus" aria-hidden="true"></span> {}', 'Iniciar seu processo'),
                    'css_class': 'success',
                }
            )
        return items

    def get_urls(self):
        urls = super().get_urls()
        info = self.model._meta.app_label, self.model._meta.model_name
        custom = [
            path(
                'add/',
                self.admin_site.admin_view(self.add_autocreate_view),
                name=f'{info[0]}_{info[1]}_add',
            ),
            path(
                '<int:pk>/limpar-processo-eletronico/',
                self.admin_site.admin_view(self.limpar_processo_eletronico_view),
                name=f'{info[0]}_{info[1]}_limpar_processo_eletronico',
            ),
        ]
        return custom + urls

    def limpar_processo_eletronico_view(self, request, pk):
        """Remove o vínculo do processo RSC-TAE com o processo eletrônico (SET NULL).

        Ação administrativa RESTRITA A SUPERUSUÁRIO (não basta ter change_permission no processo).
        Não exclui o processo eletrônico — apenas desvincula, permitindo gerar um novo. O antigo
        deve ser cancelado/finalizado no módulo Processo Eletrônico.
        """
        if not request.user.is_superuser:
            raise PermissionDenied('Ação restrita a superusuários.')
        processo = get_object_or_404(ProcessoRSCTae, pk=pk)
        destino = reverse('admin:rsc_tae_processorsctae_changelist')
        anterior = processo.processo_eletronico_id
        if not anterior:
            self.message_user(request, 'Este processo não possui processo eletrônico vinculado.', level=messages.WARNING)
            return redirect(destino)
        ProcessoRSCTae.objects.filter(pk=processo.pk).update(processo_eletronico=None)
        self.message_user(
            request,
            f'Vínculo com o processo eletrônico #{anterior} removido. O processo eletrônico não foi excluído — '
            'cancele ou finalize-o no módulo Processo Eletrônico. Um novo poderá ser gerado.',
            level=messages.SUCCESS,
        )
        return redirect(destino)

    def add_autocreate_view(self, request):
        """Redireciona para a view de seleção de nível (RN01)."""
        if not self.has_add_permission(request):
            raise PermissionDenied
        return redirect(reverse('rsc_tae:iniciar_processo'))

    def response_change(self, request, obj):
        resp = super().response_change(request, obj)
        if isinstance(resp, HttpResponseRedirect) and '_continue' not in request.POST and '_addanother' not in request.POST:
            return redirect(reverse('admin:rsc_tae_processorsctae_changelist'))
        return resp
