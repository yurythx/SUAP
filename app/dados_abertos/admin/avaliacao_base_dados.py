from django.contrib import admin
from django.contrib import messages
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from djtools.contrib.admin import ModelAdminPlus

from .permissoes import AcaoDeAlteracaoMixin
from ..models import AvaliacaoBaseDados


@admin.register(AvaliacaoBaseDados)
class AvaliacaoBaseDadosAdmin(AcaoDeAlteracaoMixin, ModelAdminPlus):
    list_display = (
        'base_dados',
        'criterio_matriz',
        'nota',
        'finalizado',
        'data_atualizacao',
    )
    list_filter = (
        'finalizado',
        'criterio_matriz',
    )
    search_fields = (
        'base_dados__titulo',
        'base_dados__nome',
        'criterio_matriz__nome',
    )
    ordering = ('-data_atualizacao',)
    list_display_icons = True
    actions = ['action_finalizar_avaliacoes', 'action_desfazer_finalizacao', 'action_apagar_avaliacoes']

    fieldsets = (
        (
            _('Avaliação'),
            {
                'fields': (
                    'base_dados',
                    'criterio_matriz',
                    'nota',
                    'finalizado',
                )
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

    readonly_fields = (
        'data_cadastro',
        'data_atualizacao',
    )

    @admin.action(description=_('Finalizar avaliações selecionadas'), permissions=('alterar',))
    def action_finalizar_avaliacoes(self, request, queryset):
        qs_pendentes = queryset.filter(finalizado=False)
        pendentes = qs_pendentes.count()
        ja_finalizadas = queryset.count() - pendentes

        if pendentes:
            qs_pendentes.update(finalizado=True, data_atualizacao=timezone.now())
            self.message_user(
                request,
                _('Avaliações finalizadas: %(qtd)s.') % {'qtd': pendentes},
                level=messages.SUCCESS,
            )
        else:
            self.message_user(
                request,
                _('Nenhuma avaliação pendente para finalizar.'),
                level=messages.INFO,
            )

        if ja_finalizadas:
            self.message_user(
                request,
                _('Já estavam finalizadas: %(qtd)s.') % {'qtd': ja_finalizadas},
                level=messages.WARNING,
            )

    @admin.action(description=_('Desfazer finalização das avaliações selecionadas'), permissions=('alterar',))
    def action_desfazer_finalizacao(self, request, queryset):
        qs_finalizadas = queryset.filter(finalizado=True)
        finalizadas = qs_finalizadas.count()
        ja_pendentes = queryset.count() - finalizadas

        if finalizadas:
            qs_finalizadas.update(finalizado=False, data_atualizacao=timezone.now())
            self.message_user(
                request,
                _('Finalizações desfeitas: %(qtd)s.') % {'qtd': finalizadas},
                level=messages.SUCCESS,
            )
        else:
            self.message_user(
                request,
                _('Nenhuma avaliação finalizada para desfazer.'),
                level=messages.INFO,
            )

        if ja_pendentes:
            self.message_user(
                request,
                _('Já estavam pendentes: %(qtd)s.') % {'qtd': ja_pendentes},
                level=messages.WARNING,
            )

    @admin.action(description=_('Apagar avaliações selecionadas'), permissions=('delete',))
    def action_apagar_avaliacoes(self, request, queryset):
        qtd = queryset.count()
        if qtd:
            queryset.delete()
            self.message_user(
                request,
                _('Avaliações apagadas: %(qtd)s.') % {'qtd': qtd},
                level=messages.SUCCESS,
            )
        else:
            self.message_user(
                request,
                _('Nenhuma avaliação para apagar.'),
                level=messages.INFO,
            )
