from djtools.db import models
from django.db.models.aggregates import Max


class AreaVinculacao(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição')
    ordem = models.IntegerField(blank=True, default=1)

    class Meta:
        verbose_name = 'Área de Vinculação'
        verbose_name_plural = 'Áreas de Vinculação'
        ordering = ('ordem',)

    def __str__(self):
        return self.descricao

    def save(self):
        if not self.ordem:
            self.ordem = AreaVinculacao.objects.all().aggregate(Max('ordem')).get('ordem__max', 0) + 1
        super().save()
