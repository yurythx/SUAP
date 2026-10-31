import datetime
from djtools.db import models


class SubgrupoOcorrencia(models.ModelPlus):
    """
    Subgrupos são classes pertencentes ao SUAP apenas. Esses dados não existem no SIAPE
    e forão incluídos apenas para facilitar a compreensão dos diferentes tipos de ocorrências
    """

    descricao = models.CharField(max_length=40, null=True)

    class Meta:
        db_table = 'subgrupo_ocorrencia'

    def __str__(self):
        return self.descricao


class GrupoOcorrencia(models.ModelPlus):
    codigo = models.CharField(max_length=10, null=True, unique=True)
    nome = models.CharField(max_length=40)
    excluido = models.BooleanField(default=False)

    class Meta:
        db_table = 'grupo_ocorrencia'
        verbose_name = 'Grupo de Ocorrência'
        verbose_name_plural = 'Grupos de Ocorrência'

    def __str__(self):
        return self.nome


class Ocorrencia(models.ModelPlus):
    REDISTRIBUICAO = '02100'
    POSSE_OUTRO_CARGO_INACUMULAVEL = '02122'

    codigo = models.CharField(max_length=5, unique=True)
    nome = models.CharField(max_length=60)
    excluido = models.BooleanField(default=False)
    grupo_ocorrencia = models.ForeignKeyPlus(GrupoOcorrencia, on_delete=models.CASCADE)
    interrompe_pagamento = models.BooleanField(default=False, blank=True)

    class Meta:
        db_table = 'ocorrencia'
        verbose_name = 'Ocorrência'
        verbose_name_plural = 'Ocorrências'

    def __str__(self):
        return self.nome


class ServidorOcorrencia(models.ModelPlus):
    servidor = models.ForeignKeyPlus('rh.Servidor', editable=False, on_delete=models.CASCADE)
    ocorrencia = models.ForeignKeyPlus(Ocorrencia, editable=False, on_delete=models.CASCADE)
    subgrupo = models.ForeignKeyPlus(SubgrupoOcorrencia, null=True, editable=False, on_delete=models.CASCADE)
    diploma_legal = models.ForeignKeyPlus('rh.DiplomaLegal', null=True, editable=False, on_delete=models.CASCADE)
    diploma_legal_data = models.DateField(null=True, editable=False)
    diploma_legal_num = models.CharField(max_length=10, editable=False)
    data = models.DateField(null=True, editable=False, db_index=True)
    data_termino = models.DateField(null=True, blank=True, db_index=True)
    quantidade_dias_ocorrencia = models.PositiveIntegerFieldPlus('Quantidade de dias ocorrência', default=0)

    class Meta:
        db_table = 'servidor_ocorrencia'
        verbose_name = 'Ocorrência de Servidor'
        verbose_name_plural = 'Ocorrências de Servidores'

    def save(self, *args, **kwargs):
        self.quantidade_dias_ocorrencia = self.get_qtde_dias().days
        super().save(*args, **kwargs)

    def __str__(self):
        return (
            '\n'
            + '\n'.join(
                [
                    f'servidor\t: {self.servidor.pessoa_fisica.nome}',
                    f'ocorrencia\t: {self.ocorrencia.nome}',
                    f'grupo_ocorrencia: {self.ocorrencia.grupo_ocorrencia.nome}',
                    f'subgrupo\t: {self.subgrupo and self.subgrupo.descricao or "-"}',
                    f'data\t\t: {self.data}',
                    f'termino\t\t: {self.data_termino}',
                ]
            )
            + '\n\n'
        )

    def get_qtde_dias(self):
        if not self.data_termino:
            return datetime.timedelta(1)

        dt_data = self.data
        dt_termino = self.data_termino

        if isinstance(dt_data, datetime.datetime):
            dt_data = datetime.datetime.date(dt_data)
        if isinstance(dt_termino, datetime.datetime):
            dt_termino = datetime.datetime.date(dt_termino)

        return dt_termino - dt_data

    @classmethod
    def get_afastamentos(cls, servidor, data_inicial, data_final):
        # TODO:
        # Este método poderia receber o `grupo_ocorrencia` como parâmetro, mas
        # teria que tratar os casos onde `data_termino` é `None`.
        return cls.objects.filter(
            servidor=servidor, ocorrencia__grupo_ocorrencia__nome='AFASTAMENTO', data__lte=data_final, data_termino__gte=data_inicial
        )
