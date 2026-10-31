from django.contrib import admin

from djtools.contrib.admin import ModelAdminPlus
from edu.models import Credenciamento
from edu.forms import CredenciamentoForm
from django.utils.safestring import mark_safe


class CredenciamentoAdmin(ModelAdminPlus):
    list_display = (
        'tipo',
        'get_naturezas',
        'tipo_ato',
        'numero_ato',
        'data_ato',
        'orgao',
        'numero_publicacao',
        'data_publicacao',
        'veiculo_publicacao',
        'secao_publicacao',
        'pagina_publicacao',
    )
    list_display_icons = True
    form = CredenciamentoForm
    fieldsets = (
        (
            'Dados gerais',
            {
                'fields': (
                    'tipo',
                    'natureza_participacao',
                )
            },
        ),
        (
            'Ato',
            {
                'fields': (
                    ('tipo_ato', 'orgao'),
                    ('sem_numero', 'numero_ato'),
                    'data_ato',
                )
            },
        ),
        (
            'Publicação',
            {'fields': (('numero_publicacao', 'data_publicacao'), ('veiculo_publicacao', 'secao_publicacao'), 'pagina_publicacao')},
        ),
    )

    def get_naturezas(self, obj):
        html = ['<ul>']
        for np in obj.natureza_participacao.all():
            html.append(f'<li>{np.descricao}</li>')
        html.append('</ul>')
        return mark_safe(''.join(html))

    get_naturezas.short_description = 'Naturezas de participação'


admin.site.register(Credenciamento, CredenciamentoAdmin)
