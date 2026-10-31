from django.db import models


class MateriaisAtivosManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(ativo=True)
