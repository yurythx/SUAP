from acervo_academico.forms import RotinaImportacaoForm
from acervo_academico.models import RotinaImportacao, ItemRotina
from django.contrib import admin
from django.template.defaultfilters import pluralize
from django.utils.safestring import mark_safe
from djtools.contrib.admin import ModelAdminPlus, DateRangeListFilter
from djtools.templatetags.filters import status, format_


class RotinaImportacaoAdmin(ModelAdminPlus):
    form = RotinaImportacaoForm
    list_display_icons = True
    list_display = (
        'nome_do_projeto',
        'get_campi',
        'data_criacao',
        'ultima_execucao',
        'get_status',
    )
    search_fields = (
        'nome_do_projeto',
        'diretorio_raiz',
    )
    list_filter = ('status',)

    def get_campi(self, obj):
        siglas = sorted(set(obj.itens.values_list('campus__sigla', flat=True)))
        qtd_a_exibir = 3
        html = ''
        for i in range(min(len(siglas), qtd_a_exibir)):
            html += f'<li>{siglas[i]}</li>'
        html = f'<ul>{html}</ul>'
        if qtd_a_exibir < len(siglas):
            diferenca = len(siglas) - qtd_a_exibir
            html += f'<p>+{diferenca} outro{pluralize(diferenca)} camp{pluralize(diferenca, "us,i")}</p>'
        return mark_safe(html)

    get_campi.short_description = 'Campi'

    def get_status(self, obj):
        return status(obj.get_status())

    get_status.short_description = 'Status'
    get_status.admin_order_field = 'status'


admin.site.register(RotinaImportacao, RotinaImportacaoAdmin)


class ItemRotinaAdmin(ModelAdminPlus):
    list_display = ('nome_arquivo', 'campus', 'rotina', 'inicio_execucao', 'get_status', 'detalhes_execucao')
    search_fields = ('nome_arquivo',)
    list_filter = ('rotina', 'campus', 'status', ('inicio_execucao', DateRangeListFilter))
    list_display_icons = True
    export_to_xls = True

    def get_status(self, obj):
        return status(obj.get_status_display())

    get_status.short_description = 'Status'
    get_status.admin_order_field = 'status'

    def to_xls(self, request, queryset, task):
        header = [
            '#',
            'Rotina',
            'Campus',
            'Nome do aluno',
            'Matrícula',
            'Nome do arquivo',
            'URL do arquivo',
            'Início da execução',
            'Status do processamento',
            'Detalhes da execução',
        ]
        rows = [header]
        for idx, item_rotina in enumerate(task.iterate(queryset)):
            row = [
                idx + 1,
                str(item_rotina.rotina),
                format_(item_rotina.campus),
                item_rotina.aluno.get_nome_social_composto() if item_rotina.aluno else '-',
                item_rotina.aluno.matricula if item_rotina.aluno else '-',
                item_rotina.nome_arquivo,
                item_rotina.url_arquivo,
                format_(item_rotina.inicio_execucao),
                item_rotina.get_status_display(),
                format_(item_rotina.detalhes_execucao),
            ]
            rows.append(row)
        return rows


admin.site.register(ItemRotina, ItemRotinaAdmin)
