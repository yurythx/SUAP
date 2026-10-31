from django.contrib import admin
from django import forms
from djtools.contrib.admin import ModelAdminPlus
from edu.forms import AtividadePoloForm
from edu.models import AtividadePolo, HorarioFuncionamentoPolo, Polo, TipoPolo, AtoRegulatorioPolo


class TipoPoloAdmin(ModelAdminPlus):
    list_display = ('descricao',)
    list_display_icons = True


admin.site.register(TipoPolo, TipoPoloAdmin)


class HorarioFuncionamentoPoloInline(admin.TabularInline):
    model = HorarioFuncionamentoPolo
    extra = 3


class AtoRegulatorioPoloInline(admin.TabularInline):
    model = AtoRegulatorioPolo
    extra = 1


class PoloAdmin(ModelAdminPlus):
    list_filter = ('sigla', 'diretoria', 'tipo', 'cidade', 'ativo')
    list_display = ('descricao', 'sigla', 'cidade', 'codigo_censup')
    list_display_icons = True
    search_fields = ('descricao', 'sigla')
    ordering = ('descricao',)
    exclude = ('codigo_academico',)
    inlines = [HorarioFuncionamentoPoloInline, AtoRegulatorioPoloInline]

    def get_inline_instances(self, request, obj=None):
        instances = super().get_inline_instances(request, obj=None)
        if (
            not request.user.is_superuser
            and not request.user.groups.filter(
                name__in=[
                    'Administrador EAD',
                    'Diretor de Avaliação e Regulação do Ensino',
                    'Coordenador de Polo EAD',
                    'Coordenador de Polo EAD Sistêmico',
                ]
            ).exists()
        ):
            return []
        return instances

    def get_queryset(self, request):
        return super().get_queryset(request, Polo.locals)

    def has_change_permission(self, request, obj=None):
        if obj and obj.coordenadorpolo_set.filter(vinculo__user_id=request.user).exists():
            return True
        return super().has_change_permission(request, obj)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['opcoes_acessibilidade'].widget = forms.CheckboxSelectMultiple(attrs={'class': 'checkboxes'})
        form.base_fields['opcoes_acessibilidade'].help_text = None
        form.base_fields['tecnologias_equipamentos'].widget = forms.CheckboxSelectMultiple(attrs={'class': 'checkboxes'})
        form.base_fields['tecnologias_equipamentos'].help_text = None
        return form

    def get_fieldsets(self, request, obj=None):
        fieldsets = (
            (
                'Informações Gerais',
                {
                    'fields': (
                        'tipo',
                        ('descricao', 'sigla'),
                        'cidade',
                        'do_municipio',
                        'diretoria',
                        'ativo',
                        'arquivo_autorizacao',
                    )
                },
            ),
            ('Telefones', {'fields': (('telefone_principal', 'telefone_secundario'),)}),
            ('Endereço', {'fields': (('logradouro', 'numero'), 'complemento', 'bairro', 'cep')}),
            ('Códigos', {'fields': (('codigo_censup', 'codigo_sistec'), ('codigo_sisuab', 'codigo_emec'))}),
            ('Assistência Estudantil', {'fields': ('campus_atendimento',)}),
            ('Infaestrutura', {'fields': ('estrutura_disponivel',)}),
            ('Acessibilidade', {'fields': ('opcoes_acessibilidade', 'rampa_acesso_corrimao', 'equipamentos_eletronicos')}),
            ('Tecnologias e Equipamentos', {'fields': ('tecnologias_equipamentos', 'qtd_computadores_discentes')}),
            ('Matrícula', {'fields': ('tipo_local_matricula', 'especificacao_local_matricula')}),
        )
        if request.user.is_superuser or request.user.has_group_cached(
            ['Administrador Acadêmico', 'Diretor de Avaliação e Regulação do Ensino', 'Coordenador de Polo EAD', 'Coordenador de Polo EAD Sistêmico']
        ):
            return fieldsets
        else:
            return fieldsets[0], fieldsets[1], fieldsets[2]


admin.site.register(Polo, PoloAdmin)


class AtividadePoloAdmin(ModelAdminPlus):
    list_filter = ('polo', 'confirmada')
    list_display = ('nome', 'descricao', 'data_inicio', 'data_fim', 'polo', 'user', 'confirmada')
    search_fields = ('nome', 'descricao')
    ordering = ('data_inicio', 'data_fim')
    list_display_icons = True
    date_hierarchy = 'data_inicio'
    model = AtividadePolo
    form = AtividadePoloForm

    actions = ('confirmar',)

    def confirmar(self, request, queryset):
        queryset.update(confirmada=True)

    def get_queryset(self, request):
        return super().get_queryset(request, AtividadePolo.locals)


admin.site.register(AtividadePolo, AtividadePoloAdmin)
