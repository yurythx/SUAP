from django.contrib import admin
from django.http import HttpResponseRedirect

from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus
from djtools.templatetags.filters import in_group
from edu.models import PlanoEstudo


class PlanoEstudoAdmin(ModelAdminPlus):
    list_display = 'tipo', 'get_ano_periodo_letivo', 'get_matricula', 'get_aluno', 'get_curso', 'data_homologacao', 'numero_ata_homologacao'
    list_display_icons = True
    list_filter = (
        CustomTabListFilter,
        'pedido_matricula__matricula_periodo__ano_letivo',
        'pedido_matricula__matricula_periodo__periodo_letivo',
        'planejamento_concluido',
        'homologado',
        'descumprido',
        'pedido_matricula__matricula_periodo__aluno__curso_campus',
    )
    list_per_page = 15
    search_fields = 'pedido_matricula__matricula_periodo__aluno__matricula', 'pedido_matricula__matricula_periodo__aluno__pessoa_fisica__nome'
    actions = ['avaliar', 'cancelar_avaliacao']

    def get_matricula(self, obj):
        return obj.pedido_matricula.matricula_periodo.aluno.matricula

    get_matricula.short_description = 'Matrícula'

    def get_aluno(self, obj):
        return obj.pedido_matricula.matricula_periodo.aluno

    get_aluno.short_description = 'Aluno'

    def get_curso(self, obj):
        return obj.pedido_matricula.matricula_periodo.aluno.curso_campus

    get_aluno.short_description = 'Curso'

    def get_ano_periodo_letivo(self, obj):
        return f'{obj.pedido_matricula.matricula_periodo.ano_letivo}/{obj.pedido_matricula.matricula_periodo.periodo_letivo}'

    get_ano_periodo_letivo.short_description = 'Ano/Período Letivo'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser:
            ids = []
            ids.extend(
                qs.filter(pedido_matricula__matricula_periodo__aluno__curso_campus__coordenador=request.user.get_vinculo()).values_list(
                    'id', flat=True
                )
            )
            if in_group(request.user, 'Diretor Acadêmico'):
                ids.extend(
                    qs.filter(
                        pedido_matricula__matricula_periodo__aluno__curso_campus__diretoria__setor__uo=request.user.get_vinculo().setor.uo
                    ).values_list('id', flat=True)
                )
            return qs.filter(id__in=ids)
        return qs

    def tab_dispensados(self, request, queryset):
        return queryset.filter(tipo='Dispensa')

    tab_dispensados.short_description = 'Dispensas'

    def tab_aguardando_planejamento(self, request, queryset):
        return queryset.filter(tipo='Planejamento').filter(planejamento_concluido__isnull=True)

    tab_aguardando_planejamento.short_description = 'Aguardando Planejamento'

    def tab_aguardando_avaliacao(self, request, queryset):
        qs1 = queryset.filter(tipo='Planejamento').filter(planejamento_concluido=True).filter(homologado__isnull=True)
        qs2 = queryset.filter(tipo='Dispensa').filter(homologado__isnull=True)
        return qs1 | qs2

    tab_aguardando_avaliacao.short_description = 'Aguardando Avaliação'

    def tab_homologados(self, request, queryset):
        return queryset.filter(homologado=True)

    tab_homologados.short_description = 'Homologados'

    def tab_nao_homologados(self, request, queryset):
        return queryset.filter(homologado=False)

    tab_nao_homologados.short_description = 'Não-Homologados'

    def tab_descumpridos(self, request, queryset):
        return queryset.filter(tipo='Planejamento', planejamento_concluido=True, homologado=True, descumprido=True)

    tab_descumpridos.short_description = 'Descumpridos'

    def get_tabs(self, request):
        return [
            'tab_dispensados',
            'tab_aguardando_planejamento',
            'tab_aguardando_avaliacao',
            'tab_homologados',
            'tab_nao_homologados',
            'tab_descumpridos',
        ]

    def avaliar(self, request, queryset):
        pks = [str(pk) for pk in queryset.values_list('pk', flat=True)]
        url = '/edu/avaliar_plano_estudo/{}/'.format('_'.join(pks))
        return HttpResponseRedirect(url)

    avaliar.short_description = 'Avaliar'

    def cancelar_avaliacao(self, request, queryset):
        queryset.update(
            homologado=None,
            data_homologacao=None,
            observacao_homologacao='',
            numero_ata_homologacao=None,
        )

    cancelar_avaliacao.short_description = 'Cancelar Avaliação'

    def get_actions(self, request):
        actions = super().get_actions(request)
        active = {}
        if request.GET.get('tab'):
            if request.GET.get('tab') == 'tab_aguardando_avaliacao' and (in_group(request.user, 'Diretor Acadêmico') or request.user.is_superuser):
                active['avaliar'] = actions['avaliar']
            if request.GET.get('tab') in ('tab_homologados', 'tab_nao_homologados') and (
                in_group(request.user, 'Diretor Acadêmico') or request.user.is_superuser
            ):
                active['cancelar_avaliacao'] = actions['cancelar_avaliacao']
        return active


admin.site.register(PlanoEstudo, PlanoEstudoAdmin)
