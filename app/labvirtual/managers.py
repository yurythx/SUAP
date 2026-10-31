from django.db import models
from django.db.models.query_utils import Q


class DesktopPoolQueryset(models.query.QuerySet):
    def my_desktop_pools(self, user):
        if user.is_superuser:
            return self.filter()
        #
        meu_campus = user.get_vinculo().setor.uo
        return self.filter(Q(location__isnull=True) | Q(location=meu_campus))


class DesktopPoolManager(models.Manager):
    def get_queryset(self):
        return DesktopPoolQueryset(self.model, using=self._db)

    def my_desktop_pools(self, user):
        return self.get_queryset().my_desktop_pools(user)
