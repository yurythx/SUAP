from djtools.db import models


class PadraoVencimento(models.ModelPlus):
    CATEGORIA_DOCENTE = 'docente'
    CATEGORIA_TECNICO_ADMINISTRATIVO = 'tecnico_administrativo'
    CHOICES_CATEGORIA = [[CATEGORIA_DOCENTE, 'Docente'], [CATEGORIA_TECNICO_ADMINISTRATIVO, 'Técnico Administrativo']]

    CHOICES_CLASSE = [['A', 'A'], ['B', 'B'], ['C', 'C'], ['D', 'D'], ['E', 'E']]
    CHOICES_POSICAO_VERTICAL = [[f'{posicao}', f'{posicao}'] for posicao in range(1, 20)]

    categoria = models.CharField(max_length=50, choices=CHOICES_CATEGORIA)
    classe = models.CharField('Classe', max_length=1, choices=CHOICES_CLASSE)
    posicao_vertical = models.CharField('Mérito', max_length=2, choices=CHOICES_POSICAO_VERTICAL)

    class Meta:
        ordering = ['categoria', 'classe', 'posicao_vertical']
        unique_together = ('categoria', 'classe', 'posicao_vertical')
        verbose_name = 'Padrão de Vencimento'
        verbose_name_plural = 'Padrões de Vencimento'

    def __str__(self):
        return f'{self.classe}{self.posicao_vertical}'  # ex: E01
