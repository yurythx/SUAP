from djtools.contrib import admin

from ..forms import RecursoDadosForm
from ..models import (
    ItemCronogramaElaboracao,
    ItemCronogramaPromocao,
    PDABaseDados,
    RecursoDados,
    TopicoDocumentoPDA,
    Capa,
    ResponsavelGrupoTrabalho,
)


class RecursoDadosInline(admin.TabularInlinePlus):
    model = RecursoDados
    form = RecursoDadosForm
    extra = 0
    fields = ('nome', 'formato', 'url', 'arquivo', 'gerar_csv', 'mimetype', 'id_remoto', 'sincronizado_em')
    readonly_fields = ('sincronizado_em',)
    show_change_link = True


class TopicoDocumentoPDAInline(admin.TabularInlinePlus):
    model = TopicoDocumentoPDA
    extra = 0
    fields = ('titulo', 'ordem', 'data_atualizacao')
    readonly_fields = ('data_atualizacao',)
    show_change_link = True


class CapaInline(admin.StackedInlinePlus):
    model = Capa
    extra = 0
    max_num = 1
    fields = ('nome', 'imagem')
    show_change_link = True


class ResponsavelGrupoTrabalhoInline(admin.TabularInlinePlus):
    model = ResponsavelGrupoTrabalho
    extra = 0
    fields = ('responsavel', 'ativo', 'data_cadastro')
    readonly_fields = ('data_cadastro',)


class PDABaseDadosInline(admin.TabularInlinePlus):
    model = PDABaseDados
    extra = 0
    fields = (
        'base_dados',
        'herdada',
        'em_revisao',
        'submetida_consulta_publica',
        'responsavel_abertura',
        'meta_prazo_abertura',
        'frequencia_atualizacao',
        'data_atualizacao',
    )
    readonly_fields = ('data_atualizacao',)
    show_change_link = True


class ItemCronogramaElaboracaoInline(admin.TabularInlinePlus):
    model = ItemCronogramaElaboracao
    extra = 1
    fields = ('ordem', 'acao', 'atividade', 'responsavel', 'meta_prazo')
    verbose_name = 'Item do Cronograma de Elaboração e Sustentação'
    verbose_name_plural = 'Cronograma de Elaboração e Sustentação do PDA'


class ItemCronogramaPromocaoInline(admin.TabularInlinePlus):
    model = ItemCronogramaPromocao
    extra = 1
    fields = ('ordem', 'produto', 'atividades', 'responsavel', 'data_periodo')
    verbose_name = 'Item do Cronograma de Promoção e Fomento'
    verbose_name_plural = 'Cronograma de Promoção, Fomento, Uso e Reúso das Bases'
