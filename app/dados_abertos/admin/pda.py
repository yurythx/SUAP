from django.contrib import admin
from django.db.models import Count
from django.urls import reverse_lazy
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from djtools.contrib.admin import ModelAdminPlus
from djtools.templatetags.tags import icon
from djtools.templatetags.tags.utils import edit_object_icon

from ..models import PlanoDadosAbertos
from .inlines import (
    CapaInline,
    ItemCronogramaElaboracaoInline,
    ItemCronogramaPromocaoInline,
    PDABaseDadosInline,
    TopicoDocumentoPDAInline,
)


@admin.register(PlanoDadosAbertos)
class PlanoDadosAbertosAdmin(ModelAdminPlus):
    list_display = ('titulo', 'get_situacao', 'vigencia_inicio', 'vigencia_fim', 'get_versao', 'bases_qtd', 'data_publicacao')
    search_fields = ('titulo',)
    list_filter = ('situacao', 'data_publicacao')
    list_display_icons = True
    date_hierarchy = 'vigencia_inicio'
    ordering = ('-vigencia_inicio', 'titulo')
    inlines = [
        CapaInline,
        TopicoDocumentoPDAInline,
        PDABaseDadosInline,
        ItemCronogramaElaboracaoInline,
        ItemCronogramaPromocaoInline,
    ]

    fieldsets = (
        (
            _('Informações do PDA'),
            {
                'fields': ('titulo', 'situacao', 'vigencia_inicio', 'vigencia_fim', 'data_publicacao'),
            },
        ),
    )

    @admin.display(description=_('Ações'))
    def show_list_display_icons(self, obj: PlanoDadosAbertos) -> str:
        """Cada ícone só aparece para quem tem a permissão exigida pela tela de destino."""
        out = []
        pode_alterar = self.has_change_permission(self.request, obj)
        if self.has_view_permission(self.request, obj):
            out.append(icon('eye', reverse_lazy('dados_abertos:pda_detalhe', args=[obj.pk]), 'Visualizar'))
        if self.request.user.has_perm('dados_abertos.add_versaopda'):
            out.append(icon('code-branch', reverse_lazy('dados_abertos:criar_versao_pda', args=[obj.pk]), 'Nova versão', extra_class='icon popup'))
        if pode_alterar:
            out.append(
                icon('file-export', reverse_lazy('dados_abertos:gerar_documento_versao_pda', args=[obj.pk]), f'Gerar documento (v{obj.versao_atual})')
            )
            out.append(edit_object_icon(obj, has_perm=True))
        return mark_safe(''.join(out))

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(_bases_qtd=Count('bases_dados', distinct=True))

    @admin.display(description=_('Bases'), ordering='_bases_qtd')
    def bases_qtd(self, obj):
        return getattr(obj, '_bases_qtd', 0)

    @admin.display(description=_('Versão'))
    def get_versao(self, obj):
        return obj.versao_atual

    @admin.display(description=_('Situação'), ordering='situacao')
    def get_situacao(self, obj):
        cores = {
            1: '#6b7280',  # Rascunho
            2: '#d97706',  # Em aprovação
            3: '#2563eb',  # Aguardando publicação
            4: '#16a34a',  # Publicado
            5: '#0d9488',  # Em execução
            6: '#9333ea',  # Em revisão
            7: '#dc2626',  # Encerrado
        }
        label = obj.get_situacao_display()
        cor = cores.get(obj.situacao, '#555')
        return mark_safe(f'<span style="padding:2px 6px;border-radius:10px;background:{cor};color:#fff;font-size:11px;">{label}</span>')
