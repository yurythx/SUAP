from django.contrib import admin
from django.utils.safestring import mark_safe

from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus
from edu.forms import ConfiguracaoNadaConstaForm, ItemConfiguracaoNadaConstaFormset
from edu.models import ConfiguracaoNadaConsta, ItemConfiguracaoNadaConsta, NadaConsta


class ItemConfiguracaoNadaConstaInline(admin.TabularInline):
    model = ItemConfiguracaoNadaConsta
    formset = ItemConfiguracaoNadaConstaFormset
    exclude = 'setores_responsaveis', 'servidores_responsaveis', 'avaliado_coordenacao_curso', 'cursos'
    extra = 1


class ConfiguracaoNadaConstaAdmin(ModelAdminPlus):
    list_display = 'descricao', 'uo', 'get_modalidades', 'get_responsaveis', 'get_acoes'
    list_filter = ('uo',)
    search_fields = ('descricao',)
    list_per_page = 10
    list_display_icons = True
    inlines = [ItemConfiguracaoNadaConstaInline]
    form = ConfiguracaoNadaConstaForm

    def get_modalidades(self, obj):
        modalidades = obj.modalidades.all()
        if modalidades:
            lista = ['<ul>']
            for modalidade in modalidades:
                lista.append('<li>')
                lista.append(modalidade.descricao)
                lista.append('</li>')
            lista.append('</ul>')
            return mark_safe(''.join(lista))
        else:
            return mark_safe('-')

    get_modalidades.short_description = 'Modalidades'

    def get_responsaveis(self, obj):
        itens = obj.get_itens()
        if itens:
            lista = ['<dl>']
            for item in itens:
                lista.append(f'<dt>{item.tipo_nada_consta.descricao}</dt>')
                lista.append(f'<dd>{item.get_responsaveis()}</dd>')
            lista.append('</dl>')
            return mark_safe(''.join(lista))
        else:
            return mark_safe('-')

    get_responsaveis.short_description = 'Responsáveis'

    def get_acoes(self, obj):
        html = []
        html.append('<ul class="action-bar">')
        html.append(f'<li><a class="btn default popup" href="/edu/informar_responsaveis_nada_consta/{obj.pk}/">Informar Responsáveis</a></li>')
        html.append('</ul>')
        return mark_safe(''.join(html))

    def get_queryset(self, request, *args, manager=None, **kwargs):
        qs = super().get_queryset(request, manager, *args, **kwargs)
        if request.user.has_perm('comum.is_administrador_academico'):
            return qs

        setor = request.user.get_vinculo().setor
        return qs.filter(uo_id=setor.uo_id) if setor else ConfiguracaoNadaConsta.objects.none()

    get_acoes.short_description = 'Ações'


admin.site.register(ConfiguracaoNadaConsta, ConfiguracaoNadaConstaAdmin)


class NadaConstaAdmin(ModelAdminPlus):
    search_fields = 'aluno__matricula', 'aluno__pessoa_fisica__nome'
    list_display = (
        'tipo',
        'aluno',
        'valido',
        'quitado',
        'data_solicitacao',
        'justificativa_solicitacao',
        'data_avaliacao',
        'data_validade',
        'resposavel_avaliacao',
        'get_acoes',
    )
    list_filter = CustomTabListFilter, 'tipo', 'quitado'
    list_per_page = 10
    list_display_icons = True

    def get_queryset(self, request, *args, manager=None, **kwargs):
        qs = super().get_queryset(request, manager, *args, **kwargs)
        if request.user.has_perm('comum.is_administrador_academico'):
            return qs
        else:
            return NadaConsta.objects.sob_responsabilidade(request.user)

    def tab_aguardando_minha_avaliacao(self, request, queryset):
        return queryset.filter(quitado__isnull=True, data_solicitacao__isnull=False)

    tab_aguardando_minha_avaliacao.short_description = 'Aguardando Minha Avaliação'

    def get_tabs(self, request):
        return ['tab_aguardando_minha_avaliacao']

    def get_acoes(self, obj):
        html = []
        html.append('<ul class="action-bar">')
        if obj.pode_avaliar(self.request.user):
            html.append(f'<li><a class="btn primary popup" href="/edu/avaliar_registro_nada_consta/{obj.pk}/">Avaliar</a></li>')
        if obj.pode_revogar(self.request.user):
            html.append(f'<li><a class="btn popup warning" href="/edu/revogar_registro_nada_consta/{obj.pk}/">Revogar</a></li>')
        html.append('</ul>')
        return mark_safe(''.join(html))

    get_acoes.short_description = 'Ações'


admin.site.register(NadaConsta, NadaConstaAdmin)
