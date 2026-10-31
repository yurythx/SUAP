from django import forms
from django.contrib import admin
from django.utils.html import format_html
from djtools.contrib.admin import ModelAdminPlus, TabularInlinePlus

from rsc_tae.models import CategoriaMembroComissaoRSCTae, ComissaoRSCTae, MembroComissaoRSCTae


class ComissaoRSCTaeAdminForm(forms.ModelForm):
    class Meta:
        model = ComissaoRSCTae
        fields = '__all__'

    def clean_ativa(self):
        ativa = self.cleaned_data.get('ativa')
        if ativa:
            qs = ComissaoRSCTae.objects.filter(ativa=True)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError('Já existe uma comissão ativa. Desative-a antes de ativar outra.')
        return ativa


class MembroComissaoRSCTaeInline(TabularInlinePlus):
    model = MembroComissaoRSCTae
    fields = ('vinculo', 'categoria', 'ativo', 'presidente')
    extra = 1
    verbose_name = 'Membro'
    verbose_name_plural = 'Membros da comissão'


@admin.register(ComissaoRSCTae)
class ComissaoRSCTaeAdmin(ModelAdminPlus):
    form = ComissaoRSCTaeAdminForm
    list_display = (
        'nome',
        'data_inicio',
        'data_fim',
        'get_total_membros',
        'get_ativa',
    )
    list_display_icons = True
    search_fields = ('nome',)
    list_filter = ('ativa',)
    ordering = ('-data_inicio',)
    inlines = [MembroComissaoRSCTaeInline]

    fieldsets = (
        (
            None,
            {
                'fields': ('nome', 'descricao', 'ativa'),
            },
        ),
        (
            'Vigência',
            {
                'fields': ('data_inicio', 'data_fim'),
            },
        ),
    )

    def has_add_permission(self, request):
        if not super().has_add_permission(request):
            return False
        return not ComissaoRSCTae.objects.filter(ativa=True).exists()

    @admin.display(description='Membros', ordering='membros__count')
    def get_total_membros(self, obj):
        total = obj.membros.count()
        return total or '—'

    @admin.display(description='Situação', boolean=False, ordering='ativa')
    def get_ativa(self, obj):
        if obj.ativa:
            return format_html('<span class="status status-success">Ativa</span>')
        return format_html('<span class="status status-default">Inativa</span>')


@admin.register(CategoriaMembroComissaoRSCTae)
class CategoriaMembroComissaoRSCTaeAdmin(ModelAdminPlus):
    """Cadastro das origens de representação na comissão (CONSUP, DIGPE, CIS-PCCTAE, ...).

    Cada categoria cadastrada vira um card no painel da comissão, na ordem definida aqui.
    """

    list_display = ('nome', 'ordem', 'get_total_membros', 'descricao')
    list_display_icons = True
    search_fields = ('nome',)
    ordering = ('ordem', 'nome')

    @admin.display(description='Membros (todas as comissões)')
    def get_total_membros(self, obj: CategoriaMembroComissaoRSCTae) -> int:
        """Conta o histórico inteiro, de propósito — é o número que importa antes de excluir.

        Difere do painel da comissão, que só considera membros ativos da comissão ativa. O rótulo
        diz isso para os dois números não parecerem a mesma métrica em desacordo.
        """
        return obj.membros.count()
