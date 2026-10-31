from django.contrib import admin
from django.contrib.auth.models import Group
from django.utils.safestring import mark_safe

from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus
from djtools.templatetags.filters import status
from eleicao.forms import CandidatoAdminForm, ChapaAdminForm, EditalForm, EleicaoForm
from eleicao.models import Candidato, Chapa, Edital, Eleicao, Voto


class EditalAdmin(ModelAdminPlus):
    search_fields = ('descricao',)
    list_display = ('descricao', 'get_eleicoes', 'get_opcoes')
    list_display_icons = True
    list_filter = (CustomTabListFilter, 'permite_voto_branco_nulo')
    form = EditalForm
    show_count_on_tabs = True
    ordering = ('-id',)

    fieldsets = (
        (None, {'fields': ('descricao',)}),
        (
            'Configuração de Datas',
            {
                'fields': (
                    ('data_inscricao_inicio', 'data_inscricao_fim'),
                    ('data_validacao_inicio', 'data_validacao_fim'),
                    ('data_campanha_inicio', 'data_campanha_fim'),
                    ('data_votacao_inicio', 'data_votacao_fim'),
                    ('data_pre_resultado_inicio', 'data_pre_resultado_fim'),
                    ('data_homologacao_inicio', 'data_homologacao_fim'),
                    ('data_resultado_final',),
                )
            },
        ),
        (
            'Configuração',
            {'fields': ('permite_voto_branco_nulo',)},
        ),
        ('Coordenadores do Edital', {'fields': ('vinculos_coordenadores',)}),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser and not request.user.has_perm('eleicao.add_edital'):
            qs = qs.filter(vinculos_coordenadores=request.user.get_vinculo())
        return qs

    def save_related(self, request, form, formsets, change):
        vinculos_coordenadores_antigos = list(form.instance.vinculos_coordenadores.all())
        super().save_related(request, form, formsets, change)
        vinculos_coordenadores_atuais = list(form.instance.vinculos_coordenadores.all())
        grupo_gerente_eleicao = Group.objects.get(name='Coordenador de Edital')
        for coordenador in vinculos_coordenadores_antigos:
            if not coordenador.vinculos_coordenadores_editais.exists():
                coordenador.user.groups.remove(grupo_gerente_eleicao)

        for coordenador in vinculos_coordenadores_atuais:
            coordenador.user.groups.add(grupo_gerente_eleicao)

    def get_eleicoes(self, obj):
        out = ['<ul>']
        for eleicao in obj.eleicao_set.all():
            link = f'<a class="btn primary" href="/admin/eleicao/eleicao/{eleicao.id:d}/">Editar</a>'
            out.append(f'<li>{eleicao.descricao} {link}</li>')

        out.append('</ul>')
        return mark_safe(''.join(out))

    get_eleicoes.short_description = 'Eleições'

    def get_opcoes(self, obj):
        out = ['<ul class="action-bar">']
        out.append(f'<li><a class="btn success" href="/admin/eleicao/eleicao/add/?edital={obj.id}">Adicionar eleição</a></li>')
        if obj.pode_ver_resultado(self.request.user.get_vinculo()):
            out.append(f'<li><a class="btn" href="/eleicao/exportar_resultado/{obj.id}/">Exportar resultado para XLS</a></li>')
        out.append(f'<li><a class="btn" href="/admin/eleicao/eleicao/?edital__id__exact={obj.id}">Gerenciar eleições</a></li>')
        out.append(f'<li><a class="btn default" href="/eleicao/dashboard_edital/{obj.id}/">Dashboard</a></li>')
        out.append(f'<li><a href="/admin/eleicao/candidato/?eleicao__edital={obj.id:d}" class="btn default">Ver candidatos</a></li>')
        out.append('</ul>')
        return mark_safe(''.join(out))

    get_opcoes.short_description = 'Opções'

    def tab_minhas_eleicoes(self, request, queryset):
        return queryset.filter(vinculos_coordenadores=request.user.get_vinculo())

    tab_minhas_eleicoes.short_description = 'Minhas eleições'

    def get_tabs(self, request):
        return ['tab_any_data', 'tab_minhas_eleicoes']


admin.site.register(Edital, EditalAdmin)


class EleicaoAdmin(ModelAdminPlus):
    search_fields = ('descricao',)
    list_display = ('edital', 'descricao', 'publico', 'get_opcoes')
    list_filter = ('edital', 'campi', 'edital__permite_voto_branco_nulo')
    form = EleicaoForm
    list_display_icons = True
    ordering = ('-id',)

    fieldsets = (
        ('Dados gerais', {'fields': ('edital', 'descricao')}),
        ('Público', {'fields': ('pessoas_relacionadas_eleicao', 'alunos_relacionados_eleicao', 'publico', 'campi')}),
        ('Configurações', {'fields': ('votacao_global', 'resultado_global', ('caracteres_campanha', 'caracteres_recurso'), 'obs_voto')}),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser:
            qs = qs.filter(edital__vinculos_coordenadores=request.user.get_vinculo())

        return qs

    def get_opcoes(self, obj):
        out = ['<ul class="action-bar">']
        voto_qs = Voto.objects.filter(candidato__eleicao=obj)
        vinculo = self.request.user.get_vinculo()
        if obj.pode_homologar(vinculo) and voto_qs.exists():
            out.append(f'<li><a class="btn success" href="/eleicao/validar_votacao/{obj.id:d}/">Validar votação</a></li>')
        out.append(f'<li><a href="/admin/eleicao/candidato/?eleicao={obj.id:d}" class="btn default">Ver candidatos</a></li>')
        out.append(f'<li><a href="/eleicao/ver_publico/{obj.id:d}" class="btn default">Ver público</a></li>')
        if (obj.pode_ver_resultado_final(vinculo) or obj.pode_ver_resultado_preliminar(vinculo)) and voto_qs.exists():
            out.append(f'<li><a href="/eleicao/resultado/{obj.id:d}/" class="btn default">Ver resultados</a></li>')

        out.append('</ul>')
        return mark_safe(''.join(out))

    get_opcoes.short_description = 'Opções'

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        eleicao = form.instance
        eleicao.vinculo_publico_eleicao.set(eleicao.get_publicos())


admin.site.register(Eleicao, EleicaoAdmin)


class ChapaAdmin(ModelAdminPlus):
    list_display = ('nome', 'eleicao', 'get_status', 'get_acoes')
    list_filter = ('eleicao__edital', 'eleicao', 'status')
    form = ChapaAdminForm
    list_display_icons = True
    list_per_page = 50

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser:
            qs = qs.filter(eleicao__edital__vinculos_coordenadores=request.user.get_vinculo())
        return qs

    def get_status(self, obj):
        return mark_safe(status(obj.status))

    get_status.short_description = 'Parecer'

    def get_acoes(self, obj):
        retorno = '-'
        if obj.pode_ser_validado():
            retorno = f'<a class="btn success" href="/eleicao/validar_chapa/{obj.id:d}/">Avaliar</a>'

        return mark_safe(retorno)

    get_acoes.short_description = 'Ações'


admin.site.register(Chapa, ChapaAdmin)


class CandidatoAdmin(ModelAdminPlus):
    list_display = ('get_dados_principais', 'get_dados_auxiliares', 'campus', 'eleicao', 'get_status', 'get_acoes')
    list_filter = ('eleicao__edital', 'eleicao', 'status', 'campus')
    form = CandidatoAdminForm
    list_display_icons = True
    export_to_xls = True
    list_per_page = 50

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser:
            qs = qs.filter(eleicao__edital__vinculos_coordenadores=request.user.get_vinculo())
        return qs

    def get_dados_principais(self, obj):
        return mark_safe(obj.get_info_principal())

    get_dados_principais.short_description = 'Dados Principais'

    def get_dados_auxiliares(self, obj):
        return mark_safe(obj.get_info_auxilar())

    get_dados_auxiliares.short_description = 'Dados Auxiliares'

    def get_status(self, obj):
        return mark_safe(status(obj.status))

    get_status.short_description = 'Parecer'

    def get_acoes(self, obj):
        retorno = '-'
        if obj.eleicao.pode_validar(self.request.user.get_vinculo()) and obj.pode_ser_validado():
            retorno = f'<a class="btn success" href="/eleicao/validar_candidato/{obj.id:d}/">Avaliar</a>'

        return mark_safe(retorno)

    get_acoes.short_description = 'Opções'

    def to_xls(self, request, queryset, processo):
        header = ['#', 'Candidato', 'Matrícula', 'Campus do Candidato no momento da Inscrição', 'Eleição', 'Parecer']
        rows = [header]
        for idx, obj in enumerate(processo.iterate(queryset)):
            row = [
                idx + 1,
                f'{obj.candidato_vinculo.relacionamento.pessoa_fisica.nome} - {obj.candidato_vinculo.relacionamento.__class__._meta.verbose_name}',
                obj.candidato_vinculo.relacionamento.matricula,
                obj.campus,
                obj.eleicao,
                obj.get_status_display(),
            ]
            rows.append(row)
        return rows


admin.site.register(Candidato, CandidatoAdmin)
