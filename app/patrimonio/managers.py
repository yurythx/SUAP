from __future__ import annotations

from django.db import models
from django.db.models import Q

from comum.utils import get_uo

####################
# Inventário
####################


class InventariosAtivosManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(status__nome='ativo')


class InventariosPendentesManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(status__nome='pendente')


class InventariosBaixadosManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(status__nome='baixado')


class InventariosDepreciaveisQuerySet(models.QuerySet):
    def com_vida_util(self) -> InventariosDepreciaveisQuerySet:
        """Só os bens cujo elemento de despesa tem vida útil: vida útil 0 marca o elemento como não depreciável."""
        return self.filter(entrada_permanente__categoria__vida_util_em_anos__gt=0)


class InventariosDepreciaveisManager(models.Manager.from_queryset(InventariosDepreciaveisQuerySet)):
    def get_queryset(self) -> InventariosDepreciaveisQuerySet:
        return super().get_queryset().filter(Q(status__nome='ativo') | Q(status__nome='pendente'))


class InventariosAtivosGerenciaveisManager(models.Manager):
    """
    Inventários ativos com carga no mesmo campus do usuário autenticado e também os inventários que os responsáveis não tem campus (ou setor)
    """

    def get_queryset(self):
        meu_campus = get_uo()
        return (
            super()
            .get_queryset()
            .filter(Q(status__nome='ativo'), Q(responsavel_vinculo__setor__uo=meu_campus) | Q(responsavel_vinculo__setor__uo=None))
        )
