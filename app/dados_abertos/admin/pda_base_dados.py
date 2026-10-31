from django.contrib import admin, messages
from django.db.models import Count
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from djtools.contrib.admin import ModelAdminPlus

from .permissoes import AcaoDeAlteracaoMixin
from ..models import PDABaseDados


@admin.register(PDABaseDados)
class PDABaseDadosAdmin(AcaoDeAlteracaoMixin, ModelAdminPlus):
    list_display = (
        'pda',
        'base_dados',
        'herdada',
        'em_revisao',
        'submetida_consulta_publica',
        'situacao_lai_formatada',
        'unidade_responsavel_abertura',
        'responsavel_abertura',
        'meta_prazo_abertura',
        'frequencia_atualizacao',
    )
    list_filter = (
        'pda',
        'herdada',
        'em_revisao',
        'submetida_consulta_publica',
        'situacao_lai',
        'frequencia_atualizacao',
    )
    search_fields = (
        'pda__titulo',
        'base_dados__titulo',
        'base_dados__nome',
        'unidade_responsavel_abertura__nome',
        'responsavel_abertura__pessoa_fisica__nome',
    )
    ordering = ('pda', 'base_dados')
    list_display_icons = True
    actions = ('apagar', 'action_reenviar_lai')

    fieldsets = (
        (
            _('Relacionamento PDA x Base de Dados'),
            {
                'fields': (
                    'pda',
                    'base_dados',
                    'herdada',
                    'em_revisao',
                    'submetida_consulta_publica',
                )
            },
        ),
        (
            _('Cronograma de Abertura de Bases'),
            {
                'description': _('Informações exigidas pelo Art. 4º, VI, b da Resolução nº 3/2017 do CGINDA.'),
                'fields': (
                    'unidade_responsavel_abertura',
                    'responsavel_abertura',
                    'meta_prazo_abertura',
                    'frequencia_atualizacao',
                ),
            },
        ),
        (
            _('Auditoria'),
            {
                'fields': (
                    'data_cadastro',
                    'data_atualizacao',
                )
            },
        ),
    )
    readonly_fields = ('data_cadastro', 'data_atualizacao')

    @admin.display(description=_('Situação LAI'), ordering='situacao_lai')
    def situacao_lai_formatada(self, obj):
        """Situação como status do Design System.

        O ``get_situacao_lai_display`` cru não serve em ``list_display``: por ser o acessor gerado
        pelo Django para o campo com choices, ele não tem ``short_description`` e a coluna sai
        rotulada como "method".
        """
        return mark_safe(f'<span class="status {obj.classe_situacao_lai}">{obj.get_situacao_lai_display()}</span>')

    @admin.action(description=_('Apagar base relacionada selecionados'), permissions=('delete',))
    def apagar(self, request, queryset):
        count = queryset.count()
        queryset.delete()
        self.message_user(request, f'{count} bases relacionadas apagadas com sucesso.')

    @admin.action(description=_('Enviar/Reenviar ao LAI (datasets pendentes ou devolvidos)'), permissions=('alterar',))
    def action_reenviar_lai(self, request, queryset):
        from dados_abertos.enums import SituacaoLAI
        from dados_abertos.services.lai_service import enviar_para_analise

        sem_recurso = (
            queryset.filter(situacao_lai__in=(SituacaoLAI.PENDENTE, SituacaoLAI.DEVOLVIDO))
            .annotate(_qtd_recursos=Count('base_dados__recursos'))
            .filter(_qtd_recursos=0)
            .count()
        )
        n = enviar_para_analise(
            queryset,
            autor=request.user.get_vinculo(),
            ip=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
        )
        self.message_user(request, _('%(n)s dataset(s) enviado(s) ao LAI para análise.') % {'n': n})
        if sem_recurso:
            self.message_user(
                request,
                _('%(n)s dataset(s) sem recurso não foram enviados — anexe ao menos um recurso para permitir a prévia dos dados.')
                % {'n': sem_recurso},
                level=messages.WARNING,
            )
