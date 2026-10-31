from djtools.db import models


class Instituicao(models.ModelPlus):
    SEARCH_FIELDS = ['nome']
    PUBLIC_SEARCH = True

    nome = models.CharField('Instituição', max_length=150)
    ativo = models.BooleanField('Ativo', default=True)
    unidade_gestora = models.IntegerField('Unidade Gestora', null=True)
    uasg = models.IntegerField('UASG', null=True)

    class Meta:
        ordering = ['nome']
        verbose_name = 'Instituição'
        verbose_name_plural = 'Instituições'
        unique_together = ('nome',)

    def __str__(self):
        return self.nome
