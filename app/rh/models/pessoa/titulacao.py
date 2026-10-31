from djtools.db import models


class Titulacao(models.ModelPlus):
    CODIGOS_NIVEL_SUPERIOR = ['23', '24', '25', '26', '27', '28', '34', '35', '36', '37', '48', '49', '50']
    nome = models.CharField(max_length=40, blank=True)
    codigo = models.CharField(max_length=4, blank=True, unique=True)
    titulo_masculino = models.CharFieldPlus('Título Masculino', blank=True)
    titulo_feminino = models.CharFieldPlus('Título Feminino', blank=True)

    class Meta:
        db_table = 'titulacao'
        ordering = ['nome']
        verbose_name = 'Titulação'
        verbose_name_plural = 'Titulações'

    def __str__(self):
        return self.nome
