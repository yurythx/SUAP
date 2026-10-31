from djtools.db import models


class RateioOfertaEAD(models.Model):
    class Meta:
        verbose_name = 'Rateio de Oferta EAD'
        verbose_name_plural = 'Rateios de Ofertas EAD'

    # Dados Gerais
    descricao = models.CharField(verbose_name='Descrição')

    # Percentuais de Distribuição
    percentual_gestor_tecnologico = models.IntegerField(verbose_name='Gestor Tecnológico')
    percentual_gestor_oferta = models.IntegerField(verbose_name='Gestor da Oferta')
    percentual_ofertantes_associados = models.IntegerField(verbose_name='Ofertante')
    percentual_receptores = models.IntegerField(verbose_name='Receptores')

    # Pesos para Ofertantes Associados
    peso_ofertantes_associados_ch_presencial_maior_50 = models.IntegerField(verbose_name='Peso para CH Presencial >= 50%')
    peso_ofertantes_associados_ch_presencial_meno_50 = models.IntegerField(verbose_name='Peso para CH Presencial < 50%')

    # Pesos para Receptores
    peso_receptores_ch_presencial_maior_50 = models.IntegerField(verbose_name='Peso para CH Presencial >= 50%')
    peso_receptores_ch_presencial_meno_50 = models.IntegerField(verbose_name='Peso para CH Presencial < 50%')

    def __str__(self):
        return self.descricao


class OfertaEAD(models.Model):
    # Dados Gerais
    descricao = models.CharField(verbose_name='Descrição')

    # Dados do Rateio
    rateio = models.ForeignKeyPlus(RateioOfertaEAD, verbose_name='Rateio')
    gestor_tecnologico = models.ForeignKeyPlus('rh.UnidadeOrganizacional', verbose_name='Gestor Tecnológico')

    class Meta:
        verbose_name = 'Oferta EAD'
        verbose_name_plural = 'Ofertas EAD'

    def __str__(self):
        return self.descricao

    def get_absolute_url(self):
        return f'/edu/ofertaead/{self.pk}/'

    def get_gestores_oferta(self):
        return []

    def get_ofertantes_associados(self):
        return []

    def get_receptores(self):
        return []

    def get_convenios(self):
        return []

    def get_editais(self):
        return []
