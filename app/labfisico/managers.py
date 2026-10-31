from django.db import models
from django.db.models.query_utils import Q

from labfisico.perms import is_group_admin


class GuacamoleConnectionGroupQueryset(models.query.QuerySet):
    def my_guacamole_connection_groups(self, user):
        if user.is_superuser or is_group_admin(user):
            return self.filter()
        #
        try:
            meu_campus = user.get_vinculo().setor.uo
            return self.filter(Q(campus__isnull=True) | Q(campus=meu_campus))
        except Exception:
            return self.none()


class GuacamoleConnectionGroupManager(models.Manager):
    def get_queryset(self):
        return GuacamoleConnectionGroupQueryset(self.model, using=self._db)

    def my_guacamole_connection_groups(self, user):
        return self.get_queryset().my_guacamole_connection_groups(user)
