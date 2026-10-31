from django.contrib import admin
from django.utils.safestring import mark_safe

from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus
from edu.models import AtaEletronica, MembroBanca, ProjetoFinal


class ProjetoFinalAdmin(ModelAdminPlus):
    list_display = 'get_aluno', 'get_ano_letivo', 'get_periodo_letivo', 'tipo', 'orientador', 'titulo', 'get_coorientadores'
    list_display_icons = True
    list_filter = (
        'matricula_periodo__ano_letivo',
        'matricula_periodo__periodo_letivo',
        'tipo',
        'matricula_periodo__aluno__curso_campus__diretoria',
        'matricula_periodo__aluno__curso_campus',
        'orientador',
        'coorientadores_vinculos',
    )
    search_fields = ('matricula_periodo__aluno__matricula', 'matricula_periodo__aluno__pessoa_fisica__nome', 'titulo')
    list_per_page = 15
    export_to_xls = True
    list_xls_display = (
        'get_aluno',
        'get_ano_letivo',
        'get_periodo_letivo',
        'get_curso',
        'tipo',
        'titulo',
        'orientador__pessoa__nome',
        'data_defesa',
        'defesa_online',
        'local_defesa',
        'data_deposito',
        'presidente',
        'examinador_interno',
        'examinador_externo',
        'terceiro_examinador',
        'resultado_data',
        'nota',
        'situacao',
        'documento_url',
        'documento_final_url',
    )

    def get_action_bar(self, request):
        return super(self.__class__, self).get_action_bar(request, True)

    def get_aluno(self, obj):
        return obj.matricula_periodo.aluno

    get_aluno.short_description = 'Aluno'

    def get_ano_letivo(self, obj):
        return obj.matricula_periodo.ano_letivo

    get_ano_letivo.short_description = 'Ano Letivo'

    def get_periodo_letivo(self, obj):
        return obj.matricula_periodo.periodo_letivo

    get_periodo_letivo.short_description = 'Período Letivo'

    def get_curso(self, obj):
        return obj.matricula_periodo.aluno.curso_campus

    get_aluno.short_description = 'Curso'

    def get_coorientadores(self, obj):
        html = ['<ul>']
        for vinculo in obj.coorientadores_vinculos.all():
            html.append(f'<li>{vinculo}</li>')
        html.append('</ul>')
        return mark_safe(''.join(html))

    get_coorientadores.short_description = 'Coorientadores'


admin.site.register(ProjetoFinal, ProjetoFinalAdmin)


class MembroBancaAdmin(ModelAdminPlus):
    list_filter = ('instituicao',)
    list_display = ('nome', 'email', 'instituicao', 'formacao')
    list_display_icons = True
    search_fields = ('nome', 'instituicao')
    ordering = ('nome',)


admin.site.register(MembroBanca, MembroBancaAdmin)


class AtaEletronicaAdmin(ModelAdminPlus):
    list_display = 'get_aluno', 'get_ano_letivo', 'get_periodo_letivo', 'get_tipo', 'get_titulo', 'get_responsaveis', 'get_acoes'
    list_display_icons = True
    list_filter = (
        CustomTabListFilter,
        'projeto_final__matricula_periodo__ano_letivo',
        'projeto_final__matricula_periodo__periodo_letivo',
        'projeto_final__tipo',
        'projeto_final__matricula_periodo__aluno__curso_campus__diretoria',
        'projeto_final__matricula_periodo__aluno__curso_campus',
    )
    search_fields = ('projeto_final__matricula_periodo__aluno__matricula', 'projeto_final__matricula_periodo__aluno__pessoa_fisica__nome')
    list_per_page = 15

    def get_action_bar(self, request):
        return super(self.__class__, self).get_action_bar(request, True)

    def get_aluno(self, obj):
        return obj.projeto_final.matricula_periodo.aluno

    get_aluno.short_description = 'Aluno'

    def get_ano_letivo(self, obj):
        return obj.projeto_final.matricula_periodo.ano_letivo

    get_ano_letivo.short_description = 'Ano Letivo'

    def get_periodo_letivo(self, obj):
        return obj.projeto_final.matricula_periodo.periodo_letivo

    get_periodo_letivo.short_description = 'Período Letivo'

    def get_curso(self, obj):
        return obj.projeto_final.matricula_periodo.aluno.curso_campus

    get_aluno.short_description = 'Curso'

    def get_tipo(self, obj):
        return obj.projeto_final.tipo

    get_tipo.short_description = 'Tipo'

    def get_titulo(self, obj):
        return obj.projeto_final.titulo

    get_titulo.short_description = 'Título'

    def get_resultado(self, obj):
        return obj.projeto_final.resultado

    get_resultado.short_description = 'Resultado'

    def get_responsaveis(self, obj):
        html = []
        html.append('<ul>')
        for assinatura in obj.get_assinaturas():
            html.append(f'<li>{assinatura.vinculo}</li>')
        html.append('</ul>')
        return mark_safe(''.join(html))

    get_responsaveis.short_description = 'Signatários'

    def get_acoes(self, obj):
        html = []
        html.append('<ul class="action-bar">')
        html.append(
            '<li><a target="_blank" class="btn default" href="{}">{}</a></li>'.format(f'/edu/visualizar_ata_eletronica/{obj.pk}/', 'Visualizar Ata')
        )
        assinatura_pendente = obj.get_assinaturas().filter(data__isnull=True).filter(vinculo_id=self.request.user.get_vinculo().id).first()
        if assinatura_pendente:
            html.append(
                '<li><a class="btn popup" href="{}">{}</a></li>'.format(
                    f'/edu/assinar_ata_eletronica/{assinatura_pendente.pk}/', 'Assinar Eletronicamente'
                )
            )
        html.append('</ul>')
        return mark_safe(''.join(html))

    get_acoes.short_description = 'Ações'

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if not request.user.has_group_cached(['Secretário Acadêmico', 'Administrador Acadêmico', 'Estagiário Acadêmico Sistêmico']):
            queryset = queryset.filter(assinaturaataeletronica__vinculo__pessoa__pessoafisica__cpf=request.user.get_profile().cpf)
        return queryset

    def get_tabs(self, request):
        return ['tab_pendentes', 'tab_assinadas']

    def tab_pendentes(self, request, queryset):
        if request.user.has_group_cached(('Secretário Acadêmico', 'Administrador Acadêmico', 'Estagiário Acadêmico Sistêmico')):
            pks = queryset.filter(assinaturaataeletronica__data__isnull=True).values_list('pk', flat=True).distinct()
        else:
            pks = (
                queryset.filter(
                    assinaturaataeletronica__data__isnull=True,
                    assinaturaataeletronica__vinculo__pessoa__pessoafisica__cpf=request.user.get_profile().cpf,
                )
                .values_list('pk', flat=True)
                .distinct()
            )
        return queryset.filter(pk__in=pks)

    tab_pendentes.short_description = 'Pendentes'

    def tab_assinadas(self, request, queryset):
        if request.user.has_group_cached(('Secretário Acadêmico', 'Administrador Acadêmico', 'Estagiário Acadêmico Sistêmico')):
            pks = queryset.filter(assinaturaataeletronica__data__isnull=False).values_list('pk', flat=True).distinct()
        else:
            pks = (
                queryset.filter(
                    assinaturaataeletronica__data__isnull=False,
                    assinaturaataeletronica__vinculo__pessoa__pessoafisica__cpf=request.user.get_profile().cpf,
                )
                .values_list('pk', flat=True)
                .distinct()
            )
        return queryset.filter(pk__in=pks)

    tab_assinadas.short_description = 'Assinadas'


admin.site.register(AtaEletronica, AtaEletronicaAdmin)
