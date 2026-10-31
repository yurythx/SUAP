from datetime import date, datetime

from django.contrib import admin
from django.http import HttpRequest, HttpResponse
from django.template.loader import get_template
from django.urls import path
from django.utils.safestring import mark_safe

from comum.models import Configuracao
from djtools.contrib.admin import ModelAdminPlus
from djtools.templatetags.filters import format_daterange, status
from ferias.forms import FeriasForm, InterrupcaoFeriasForm
from ferias.models import Ferias, InterrupcaoFerias
from rh.models import Funcao, Servidor, Setor, UnidadeOrganizacional


class ServidorUoFilter(admin.SimpleListFilter):
    title = 'Campus'
    parameter_name = 'uo'

    def lookups(self, request, model_admin):
        is_chefe_de_setor = False
        servidor = request.user.get_relacionamento()
        if request.user.eh_servidor:
            is_chefe_de_setor = servidor.eh_chefe_do_setor_hoje(servidor.setor)
        is_rh = request.user.has_perm('rh.change_servidor')
        is_auditor = request.user.has_perm('rh.auditor')

        if is_rh or is_auditor:
            return UnidadeOrganizacional.objects.suap().all().values_list('id', 'sigla')

        if is_chefe_de_setor:
            return UnidadeOrganizacional.objects.suap().filter(id__exact=servidor.campus.id).values_list('id', 'sigla')

    def queryset(self, request, queryset):
        if self.value():
            if UnidadeOrganizacional.objects.suap().filter(pk=request.GET.get('uo')).exists():
                return queryset.filter(servidor__setor__uo__id__exact=self.value())
            else:
                self.used_parameters.pop(self.parameter_name)
        return queryset


class ServidorSetorFilter(admin.SimpleListFilter):
    title = 'Setor'
    parameter_name = 'setor'

    def lookups(self, request, model_admin):
        servidor = request.user.get_relacionamento()
        is_chefe_de_setor = False
        if request.user.eh_servidor:
            is_chefe_de_setor = servidor.eh_chefe_do_setor_hoje(servidor.setor)
        is_rh = request.user.has_perm('rh.change_servidor')
        is_auditor = request.user.has_perm('rh.auditor')
        if is_rh or is_auditor:
            if 'uo' in request.GET:
                return Setor.objects.suap().filter(excluido=False, uo__id__exact=request.GET.get('uo')).values_list('id', 'sigla')
            return Setor.objects.suap().filter(excluido=False).values_list('id', 'sigla')

        if is_chefe_de_setor:
            hoje = datetime.today()
            ids = []
            for funcao in servidor.historico_funcao(hoje, hoje).filter(
                funcao__codigo__in=Funcao.get_codigos_funcao_chefia(), setor_suap__isnull=False
            ):
                for setor in funcao.setor_suap.descendentes:
                    ids.append(setor.id)
            return Setor.objects.suap().filter(id__in=ids).values_list('id', 'sigla')

    def queryset(self, request, queryset):
        if self.value():
            setor = Setor.objects.suap().filter(pk=request.GET.get('setor'))
            if setor.exists():
                servidor = request.user.get_relacionamento()
                eh_chefe_setor = False
                if isinstance(servidor, Servidor):
                    eh_chefe_setor = servidor.eh_chefe_do_setor_hoje(setor[0])

                if eh_chefe_setor:
                    hoje = datetime.today()
                    ids = []
                    for funcao in servidor.historico_funcao(hoje, hoje).filter(
                        funcao__codigo__in=Funcao.get_codigos_funcao_chefia(), setor_suap__isnull=False
                    ):
                        for setor in funcao.setor_suap.descendentes:
                            ids.append(setor.id)
                    return queryset.filter(servidor__setor__id__in=ids)
                return queryset.filter(servidor__setor__id__exact=self.value())
            else:
                self.used_parameters.pop(self.parameter_name)


class IncluirSubSetoresFilter(admin.SimpleListFilter):
    title = 'Subsetores'
    parameter_name = 'incluir_sub_setores'

    SIM = 'SIM'
    NAO = 'NAO'

    def lookups(self, request, model_admin):
        return ((self.SIM, 'Incluir Subsetores'), (self.NAO, 'Não Incluir Subsetores'))

    def queryset(self, request, queryset):
        setor_id = request.GET.get('setor')
        qs_result = queryset
        if self.value() and self.value() == self.NAO:
            qs_result = queryset.filter(servidor__setor__id__exact=setor_id)
        return qs_result


class InterrupcaoInLine(admin.TabularInline):
    model = InterrupcaoFerias
    extra = 1
    form = InterrupcaoFeriasForm


JUSTIFICATIVA_PROXIMO_EXERCICIO = 'Ferias marcadas para o proximo exercicio em razao de necessidade de servico do setor de trabalho do servidor.'


class FeriasAdmin(ModelAdminPlus):
    comando_cadastrar = '4'

    list_display = (
        'ano',
        'servidor',
        'get_periodo1',
        'get_periodo2',
        'get_periodo3',
        'criado_em',
        'get_setor',
        'get_status',
        'atualiza_pelo_extrator',
        'get_acoes',
    )
    list_filter = ('ano', 'validado', 'cadastrado', 'atualiza_pelo_extrator', ServidorUoFilter, ServidorSetorFilter, IncluirSubSetoresFilter)
    search_fields = ('servidor__pessoa_fisica__nome', 'servidor__matricula')
    list_per_page = 20
    list_display_icons = True
    ordering = ('-ano__ano',)
    form = FeriasForm
    inlines = [InterrupcaoInLine]
    fieldsets = (
        (
            None,
            {
                'fields': (
                    ('servidor'),
                    ('ano'),
                    ('data_inicio_periodo1', 'data_fim_periodo1'),
                    ('data_inicio_periodo2', 'data_fim_periodo2'),
                    ('data_inicio_periodo3', 'data_fim_periodo3'),
                    ('atualiza_pelo_extrator'),
                )
            },
        ),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        eh_chefe_de_setor = False
        if request.user.eh_servidor:
            servidor = request.user.get_relacionamento()
            eh_chefe_de_setor = servidor.eh_chefe_do_setor_hoje(servidor.setor)
        eh_rh = request.user.has_perm('rh.eh_rh_sistemico') or request.user.has_perm('rh.eh_rh_campus')
        eh_auditor = request.user.has_perm('rh.auditor')
        if eh_rh or eh_auditor:
            return qs

        elif eh_chefe_de_setor:
            hoje = datetime.today()
            ids = []
            for funcao in servidor.historico_funcao(hoje, hoje).filter(
                funcao__codigo__in=Funcao.get_codigos_funcao_chefia(), setor_suap__isnull=False
            ):
                for setor in funcao.setor_suap.descendentes:
                    ids.append(setor.id)
            return qs.filter(servidor__setor__id__in=ids)

        return qs.none()

    def get_action_bar(self, request):
        items = super().get_action_bar(request)

        if request.user.has_perm('ferias.pode_gerar_arquivo_batch_ferias'):
            if self.get_current_queryset(request).exists():
                if self.get_current_queryset(request).filter(validado=1):
                    items.append({'url': f'gerar_arquivo_batch_ferias?{request.GET.urlencode()}', 'label': 'Gerar Arquivo Batch'})
        return items

    @staticmethod
    def _datas_batch_ferias(inicio: date | None, fim: date | None) -> str:
        """Início e fim do período no leiaute do batch (``ddmmaaaa`` x 2), ou zeros sem o período."""
        if inicio and fim:
            return inicio.strftime('%d%m%Y') + fim.strftime('%d%m%Y')
        return '0' * 16

    @staticmethod
    def _opcoes_batch_ferias(ferias: Ferias) -> list[str]:
        """Para cada um dos 3 períodos: ``N`` + adiantamento de 70% (``S``/``N``) + gratificação natalina (``S``/``N``)."""
        codigos_adiantamento = ([1, 4, 5, 7], [2, 5, 6, 7], [3, 4, 6, 7])
        return [
            'N' + ('S' if ferias.setenta_porcento in codigos else 'N') + ('S' if ferias.gratificacao_natalina == periodo else 'N')
            for periodo, codigos in enumerate(codigos_adiantamento, start=1)
        ]

    @staticmethod
    def _invade_exercicio_seguinte(ferias: Ferias) -> bool:
        """Se algum período termina depois do exercício das férias (exige justificativa no batch)."""
        ano = ferias.ano.ano
        invade = [ferias.data_fim_periodo1.year > ano]
        if ferias.data_inicio_periodo2 and ferias.data_fim_periodo2:
            invade.append(ferias.data_fim_periodo2.year > ano)
        if ferias.data_inicio_periodo3 and ferias.data_fim_periodo3:
            invade.append(ferias.data_fim_periodo3.year > ano)
        return any(invade)

    def _linha_batch_ferias(self, ferias: Ferias, cod_instituicao: str, justificativa: str) -> str:
        """Linha de cadastro (tipo ``1``) das férias de um servidor no arquivo batch."""
        opcoes1, opcoes2, opcoes3 = self._opcoes_batch_ferias(ferias)
        return (
            '1'
            + cod_instituicao
            + ferias.servidor.matricula.zfill(7)
            + '0'
            + self.comando_cadastrar
            + str(ferias.ano.ano)
            + ferias.data_inicio_periodo1.strftime('%d%m%Y')
            + ferias.data_fim_periodo1.strftime('%d%m%Y')
            + opcoes1
            + self._datas_batch_ferias(ferias.data_inicio_periodo2, ferias.data_fim_periodo2)
            + opcoes2
            + self._datas_batch_ferias(ferias.data_inicio_periodo3, ferias.data_fim_periodo3)
            + opcoes3
            + ' ' * 4
            + justificativa
        )

    def gerar_arquivo_batch_ferias(self, request: HttpRequest) -> HttpResponse:
        uf = Configuracao.get_valor_por_chave_str('comum', 'instituicao_estado').upper()
        cod_instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao_identificador')

        if not uf or not cod_instituicao:
            return HttpResponse('Defina UF e o código da instituição')

        t = get_template('ferias/templates/arquivo_ferias_batch.txt')
        query_set = self.get_current_queryset(request).filter(validado=1)
        count = str(query_set.count()).zfill(7)
        hoje = datetime.now()
        constante_sigla_orgao = f'IF{uf}      '
        linha0 = (
            '0'
            + cod_instituicao
            + '0' * 9
            + hoje.strftime('%m')
            + hoje.strftime('%Y')
            + constante_sigla_orgao
            + ' ' * 32
            + 'PROG-FERIAS'
            + ' ' * 6
            + '\n'
        )
        linhas_ferias = ''
        for ferias in query_set:
            justificativa_ferias = JUSTIFICATIVA_PROXIMO_EXERCICIO if self._invade_exercicio_seguinte(ferias) else ' ' * 240
            linhas_ferias += self._linha_batch_ferias(ferias, cod_instituicao, justificativa_ferias) + '\n'

        linha_fim = '9' + cod_instituicao + '9' * 9 + count + ' ' * 58
        conteudo_arquivo_ferias = linha0 + linhas_ferias + linha_fim

        response = HttpResponse(t.render({'arquivo_batch_ferias': conteudo_arquivo_ferias}), content_type='plain/txt')
        response['Content-Disposition'] = 'attachment; filename=ferias.txt'
        return response

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [path('gerar_arquivo_batch_ferias/', self.admin_site.admin_view(self.gerar_arquivo_batch_ferias))]
        return my_urls + urls

    def get_periodo1(self, obj):
        return mark_safe(format_daterange(obj.data_inicio_periodo1, obj.data_fim_periodo1))

    get_periodo1.admin_order_field = 'data_inicio_periodo1'
    get_periodo1.short_description = 'Período 1'

    def get_periodo2(self, obj):
        if obj.data_inicio_periodo2 and obj.data_fim_periodo2:
            return mark_safe(format_daterange(obj.data_inicio_periodo2, obj.data_fim_periodo2))
        else:
            return ' - '

    get_periodo2.admin_order_field = 'data_inicio_periodo2'
    get_periodo2.short_description = 'Período 2'

    def get_periodo3(self, obj):
        if obj.data_inicio_periodo3 and obj.data_fim_periodo3:
            return mark_safe(format_daterange(obj.data_inicio_periodo3, obj.data_fim_periodo3))
        else:
            return ' - '

    get_periodo3.admin_order_field = 'data_inicio_periodo3'
    get_periodo3.short_description = 'Período 3'

    def get_setor(self, obj):
        return mark_safe(f'{obj.servidor.setor}')

    get_setor.admin_order_field = 'servidor__setor'
    get_setor.short_description = 'Setor'

    def get_status(self, obj):
        return mark_safe(status(obj.get_status()))

    get_status.admin_order_field = 'validado'
    get_status.short_description = 'Situação'

    def get_acoes(self, obj):
        txt = ''
        usuario_logado = self.request.user
        servidor_logado = usuario_logado.get_relacionamento()
        is_reitor = False
        is_rh = usuario_logado.has_perm('rh.change_servidor')
        is_chefe_de_setor = servidor_logado.eh_chefe_de(obj.servidor)

        if servidor_logado.funcao:
            if servidor_logado.funcao_display == 'CD1':
                is_reitor = True

        if not obj.cadastrado:
            if is_reitor or servidor_logado != obj.servidor and (is_rh or is_chefe_de_setor):
                txt += f'<a class="btn popup" href="/ferias/{obj.ano}/{obj.servidor.matricula}/validacao/">Avaliar</a>'

        return mark_safe(txt)

    get_acoes.short_description = 'Ações'


admin.site.register(Ferias, FeriasAdmin)
