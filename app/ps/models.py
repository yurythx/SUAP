from djtools.db import models
from rh.models import UnidadeOrganizacional


class OfertaVaga(models.ModelPlus):
    unidade = models.CharField(max_length=255)
    concurso = models.CharField(max_length=255, verbose_name='Concurso')
    curso = models.CharField(max_length=255, verbose_name='Curso')
    turno = models.CharField(max_length=255, null=True, verbose_name='Turno')
    qtd = models.IntegerField(verbose_name='Quantidade', null=True, default=0)
    ano = models.IntegerField(default=2011)
    semestre = models.IntegerField()
    uo = models.ForeignKeyPlus(UnidadeOrganizacional, null=True, on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Oferta de Vaga'
        verbose_name_plural = 'Ofertas de Vagas'

    def __str__(self):
        return f'{self.unidade}, {self.curso}, {self.concurso}, {self.qtd}'


class Inscricao(models.ModelPlus):
    class Meta:
        verbose_name_plural = 'Inscrição'
        verbose_name = 'Inscrições'

    unidade = models.CharField(max_length=255)
    concurso = models.CharField(max_length=255, verbose_name='Concurso')
    curso = models.CharField(max_length=255, verbose_name='Curso')
    turno = models.CharField(max_length=255, null=True, verbose_name='Turno')
    numero = models.CharField(max_length=255, verbose_name='Número')
    cpf = models.CharField(max_length=250, verbose_name='CPF do Candidato')
    candidato = models.CharField(max_length=255, verbose_name='Nome do Candidato')
    nivel = models.CharField(max_length=255, null=True, verbose_name='Nível')
    ano = models.IntegerField()
    semestre = models.IntegerField()
    uo = models.ForeignKeyPlus(UnidadeOrganizacional, null=True, on_delete=models.CASCADE)

    def __str__(self):
        return f'{self.cpf}, {self.candidato}'
