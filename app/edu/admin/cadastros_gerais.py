from django import forms
from django.contrib import admin

from comum.models import Configuracao
from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus
from edu.forms import ConfiguracaoLivroForm, FormaIngressoForm
from edu.models import (
    AreaCapes,
    AreaConcentracao,
    AreaCurso,
    AreaCursoFormacaoSuperior,
    Cartorio,
    Cidade,
    ClassificacaoComplementarComponenteCurricular,
    ConfiguracaoLivro,
    Convenio,
    CursoFormacaoSuperior,
    CursoTecnico,
    Deficiencia,
    Disciplina,
    EixoTecnologico,
    Escola,
    FormaIngresso,
    GrupoArquivoObrigatorio,
    GrupoAtuacao,
    HorarioAula,
    HorarioCampus,
    JustificativaDispensaENADE,
    LinhaPesquisa,
    Modalidade,
    ModeloDocumento,
    MotivoAfastamentoSalaAula,
    NaturezaParticipacao,
    NivelEnsino,
    Nucleo,
    NucleoCentralEstruturante,
    OrgaoEmissorRg,
    ParecerAvaliacaoAproveitamentoEstudo,
    Programa,
    SituacaoMatricula,
    SituacaoMatriculaPeriodo,
    TipoAlunoArquivo,
    TipoAtividadeAprofundamento,
    TipoAtividadeComplementar,
    TipoComponente,
    TipoMedidaDisciplinar,
    TipoNadaConsta,
    TipoNEE,
    TipoPremiacao,
    TipoProfessorDiario,
    Turno,
    VinculoProfessorEAD,
    InstituicaoEnsinoSuperior,
    Pais,
    OpcaoAcessibilidadePolo,
    TecnologiaEquipamentoPolo,
)
from rh.models import UnidadeOrganizacional


class SomenteDescricaoModelAdmin(ModelAdminPlus):
    list_display = ('descricao',)
    ordering = ('descricao',)
    search_fields = ('descricao',)
    list_display_icons = True
    export_to_xls = True
    export_to_fixture = True


for cls in (
    NaturezaParticipacao,
    Convenio,
    Nucleo,
    TipoProfessorDiario,
    AreaCurso,
    AreaCapes,
    NucleoCentralEstruturante,
    Disciplina,
    TipoAtividadeComplementar,
    VinculoProfessorEAD,
    AreaConcentracao,
    Programa,
    TipoMedidaDisciplinar,
    TipoPremiacao,
    ClassificacaoComplementarComponenteCurricular,
    TipoNadaConsta,
    GrupoArquivoObrigatorio,
    GrupoAtuacao,
    MotivoAfastamentoSalaAula,
    OpcaoAcessibilidadePolo,
    TecnologiaEquipamentoPolo,
):
    admin.site.register(cls, SomenteDescricaoModelAdmin)


class PaisAdmin(ModelAdminPlus):
    list_display = ('nome', 'codigo', 'sigla')
    ordering = ('nome',)
    list_filter = [CustomTabListFilter]
    search_fields = ('nome', 'codigo', 'sigla')
    show_count_on_tabs = True

    def get_tabs(self, request):
        return ['tab_usados']

    def tab_usados(self, request, queryset):
        return queryset.filter(aluno__isnull=False).distinct()

    tab_usados.short_description = 'Usados'


admin.site.register(Pais, PaisAdmin)


class CidadeAdmin(ModelAdminPlus):
    search_fields = ('nome',)
    list_filter = ('estado',)
    list_display = ('nome', 'estado', 'codigo', 'cep_inicial', 'cep_final')
    list_display_icons = True
    list_per_page = 15
    fieldsets = (
        ('Dados gerais', {'fields': ('nome', 'estado', 'pais')}),
        ('CEP', {'fields': (('cep_inicial', 'cep_final'),)}),
        ('Código', {'fields': (('codigo',),)}),
    )


admin.site.register(Cidade, CidadeAdmin)


class InstituicaoEnsinoSuperiorAdmin(ModelAdminPlus):
    search_fields = ('nome', 'codigo')
    list_filter = ('cidade', 'cidade__estado')
    list_display = ('nome', 'codigo', 'cidade', 'tipo', 'dependencia_administrativa')
    list_display_icons = True
    list_per_page = 15
    fieldsets = (
        ('Dados gerais', {'fields': ('nome', ('codigo', 'cidade'))}),
        (
            'Detalhamento',
            {
                'fields': (
                    'tipo',
                    'dependencia_administrativa',
                )
            },
        ),
    )


admin.site.register(InstituicaoEnsinoSuperior, InstituicaoEnsinoSuperiorAdmin)


class EscolaAdmin(ModelAdminPlus):
    search_fields = ('nome',)
    list_display = ('nome', 'codigo_inep', 'cidade')
    list_filter = (
        'cidade__estado',
        'cidade',
    )
    list_display_icons = True
    list_per_page = 15


admin.site.register(Escola, EscolaAdmin)


class ParecerAvaliacaoAproveitamentoEstudoAdmin(ModelAdminPlus):
    search_fields = ('descricao',)
    list_display = ('descricao', 'apto', 'deferido')
    list_display_icons = True
    list_per_page = 15


admin.site.register(ParecerAvaliacaoAproveitamentoEstudo, ParecerAvaliacaoAproveitamentoEstudoAdmin)


class CartorioAdmin(ModelAdminPlus):
    search_fields = ('nome',)
    list_display = ('nome', 'cidade', 'serventia')
    list_filter = (
        'cidade__estado',
        'cidade',
    )
    list_display_icons = True
    list_per_page = 15


admin.site.register(Cartorio, CartorioAdmin)


class AreaCursoFormacaoSuperiorAdmin(ModelAdminPlus):
    search_fields = ('codigo_cine', 'cine')
    list_display = ('codigo_cine', 'cine', 'area_detalhada', 'area_especifica', 'area_geral', 'ativo')
    list_filter = (
        'area_detalhada',
        'area_especifica',
        'area_geral',
        'ativo',
    )
    list_display_icons = True
    list_per_page = 15
    export_to_xls = True
    export_to_fixture = True

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(AreaCursoFormacaoSuperior, AreaCursoFormacaoSuperiorAdmin)


class CursoFormacaoSuperiorAdmin(ModelAdminPlus):
    search_fields = ('codigo', 'descricao')
    list_display = ('codigo', 'descricao', 'area_curso_formacao_superior')
    list_filter = ('area_curso_formacao_superior',)
    list_display_icons = True
    list_per_page = 15


admin.site.register(CursoFormacaoSuperior, CursoFormacaoSuperiorAdmin)


class FormaIngressoAdmin(ModelAdminPlus):
    list_display = ('descricao', 'ativo')
    search_fields = ('descricao',)
    list_filter = ('ativo', 'classificacao_censup')
    list_display_icons = True
    export_to_xls = True
    form = FormaIngressoForm

    fieldsets = (
        ('Dados gerais', {'fields': ('descricao', 'ativo')}),
        ('Classificação', {'fields': (('classificacao_censup', 'classificacao_educacenso'),)}),
        (
            'Programa de Vagas',
            {
                'fields': (
                    ('programa_vaga_etinico', 'racas'),
                    ('programa_vaga_quilombola'),
                    ('programa_vaga_pessoa_deficiencia', 'programa_vaga_escola_publica'),
                    ('programa_vaga_social', 'programa_vaga_outros'),
                )
            },
        ),
    )


admin.site.register(FormaIngresso, FormaIngressoAdmin)


class TurnoAdmin(ModelAdminPlus):
    list_display = ('id', 'descricao')
    ordering = ('descricao',)
    search_fields = ('descricao',)
    list_display_icons = False
    export_to_xls = True


admin.site.register(Turno, TurnoAdmin)


class SituacaoMatriculaAdmin(ModelAdminPlus):
    list_display = ('id', 'descricao', 'ativo')
    ordering = ('descricao',)
    search_fields = ('descricao',)
    list_display_icons = False
    list_filter = ('ativo',)
    exclude = ('codigo_academico',)
    export_to_xls = True


admin.site.register(SituacaoMatricula, SituacaoMatriculaAdmin)


class SituacaoMatriculaPeriodoAdmin(ModelAdminPlus):
    list_display = ('id', 'descricao')
    ordering = ('descricao',)
    search_fields = ('descricao',)
    list_display_icons = False
    exclude = ('codigo_academico',)
    export_to_xls = True


admin.site.register(SituacaoMatriculaPeriodo, SituacaoMatriculaPeriodoAdmin)


class HorarioAulaInline(admin.TabularInline):
    model = HorarioAula
    extra = 3

    def formfield_for_dbfield(self, db_field, **kwargs):
        if db_field.name == 'turno':
            kwargs['widget'] = forms.Select
        return super().formfield_for_dbfield(db_field, **kwargs)

    @property
    def media(self):
        _media = super().media
        _media._js.append('/static/edu/js/HorarioAulaInline.js')
        return _media


class HorarioCampusAdmin(ModelAdminPlus):
    list_display = ('descricao', 'uo', 'ativo', 'eh_padrao')
    list_display_icons = True
    export_to_xls = True

    ordering = ('descricao',)
    search_fields = ('descricao',)
    list_filter = ('uo', 'ativo', 'eh_padrao')
    inlines = [HorarioAulaInline]

    def get_queryset(self, request):
        return super().get_queryset(request, HorarioCampus.locals)

    def get_form(self, request, *args, **kwargs):
        form = super().get_form(request, *args, **kwargs)
        form.base_fields['uo'].queryset = UnidadeOrganizacional.objects.campi()
        return form


admin.site.register(HorarioCampus, HorarioCampusAdmin)


class NivelEnsinoAdmin(ModelAdminPlus):
    list_display = ('id', 'descricao')
    search_fields = ('descricao',)
    list_display_icons = False
    export_to_xls = True


admin.site.register(NivelEnsino, NivelEnsinoAdmin)


class ModalidadeAdmin(ModelAdminPlus):
    list_display = ('descricao', 'id', 'nivel_ensino')
    search_fields = ('descricao',)
    list_filter = ('nivel_ensino',)
    list_display_icons = True
    export_to_xls = True

    def has_add_permission(self, request):
        return False


admin.site.register(Modalidade, ModalidadeAdmin)


class EixoTecnologicoAdmin(ModelAdminPlus):
    list_display = ('descricao', 'codigo_inep')
    search_fields = ('descricao',)
    list_display_icons = True
    export_to_xls = True


admin.site.register(EixoTecnologico, EixoTecnologicoAdmin)


class CursoTecnicoAdmin(ModelAdminPlus):
    list_display = ('codigo_inep', 'nome', 'eixo_tecnologico', 'excluido')
    search_fields = ('codigo_inep', 'nome')
    list_filter = ('eixo_tecnologico', 'excluido')
    list_display_icons = True
    export_to_xls = True


admin.site.register(CursoTecnico, CursoTecnicoAdmin)


class ModeloDocumentoAdmin(ModelAdminPlus):
    list_filter = ('tipo', 'modalidade', 'ativo')
    list_display = ('descricao', 'tipo', 'modalidade', 'ativo')
    list_display_icons = True
    list_per_page = 15
    export_to_xls = True
    search_fields = ('id', 'tipo', 'descricao')


admin.site.register(ModeloDocumento, ModeloDocumentoAdmin)


class ConfiguracaoLivroAdmin(ModelAdminPlus):
    list_display = ('descricao', 'uo', 'numero_livro', 'numero_folha', 'numero_registro')
    list_filter = (CustomTabListFilter, 'uo', 'modalidades')
    search_fields = ('descricao',)
    list_display_icons = True
    export_to_xls = True
    list_per_page = 15
    form = ConfiguracaoLivroForm

    def get_tabs(self, request):
        return ['tab_suap', 'tab_qacademico', 'tab_sica']

    def tab_suap(self, request, queryset):
        return queryset.exclude(descricao='SICA').filter(codigo_qacademico__isnull=True)

    tab_suap.short_description = 'Suap'

    def tab_qacademico(self, request, queryset):
        return queryset.exclude(descricao='SICA').filter(codigo_qacademico__isnull=False)

    tab_qacademico.short_description = lambda: Configuracao.get_valor_por_chave('edu', 'academico_nome_sistema') or 'Q-Acadêmico'

    def tab_sica(self, request, queryset):
        return queryset.filter(descricao='SICA')

    tab_sica.short_description = 'SICA'


admin.site.register(ConfiguracaoLivro, ConfiguracaoLivroAdmin)


class LinhaPesquisaAdmin(ModelAdminPlus):
    list_display = ('id', 'descricao')
    ordering = ('descricao',)
    search_fields = ('descricao',)
    list_display_icons = True
    export_to_xls = True


admin.site.register(LinhaPesquisa, LinhaPesquisaAdmin)


class TipoComponenteAdmin(ModelAdminPlus):
    list_display = ('descricao',)
    search_fields = ('descricao',)
    ordering = ('descricao',)
    export_to_xls = True
    list_per_page = 15
    list_display_icons = True


admin.site.register(TipoComponente, TipoComponenteAdmin)


class JustificativaDispensaENADEAdmin(ModelAdminPlus):
    list_display = ('descricao', 'ativo')
    list_display_icons = True
    list_per_page = 15


admin.site.register(JustificativaDispensaENADE, JustificativaDispensaENADEAdmin)


class TipoAlunoArquivoAdmin(ModelAdminPlus):
    list_display = ('nome',)
    ordering = ('nome',)
    search_fields = ('nome',)
    list_display_icons = True
    export_to_xls = True


admin.site.register(TipoAlunoArquivo, TipoAlunoArquivoAdmin)


class TipoAtividadeAprofundamentoAdmin(ModelAdminPlus):
    list_display = ('descricao',)
    ordering = ('descricao',)
    list_filter = ('modalidades',)
    search_fields = ('descricao',)
    list_display_icons = True
    export_to_xls = True


admin.site.register(TipoAtividadeAprofundamento, TipoAtividadeAprofundamentoAdmin)


class OrgaoEmissorRgAdmin(ModelAdminPlus):
    list_display = ('nome',)
    ordering = ('nome',)
    search_fields = ('nome',)
    list_display_icons = True
    export_to_xls = True


admin.site.register(OrgaoEmissorRg, OrgaoEmissorRgAdmin)


class DeficienciaAdmin(ModelAdminPlus):
    list_display = ('nome', 'ativo', 'classificacao_censup', 'classificacao_educacenso')
    list_filter = ('ativo', 'classificacao_censup', 'classificacao_educacenso')
    search_fields = ('nome',)
    ordering = ('ativo', 'nome')
    list_display_icons = True


admin.site.register(Deficiencia, DeficienciaAdmin)


class TipoNEEAdmin(ModelAdminPlus):
    list_display = ('nome', 'ativo', 'classificacao_censup', 'classificacao_educacenso')
    list_filter = ('ativo', 'classificacao_censup', 'classificacao_educacenso')
    search_fields = ('nome',)
    ordering = ('ativo', 'nome')
    list_display_icons = True


admin.site.register(TipoNEE, TipoNEEAdmin)
