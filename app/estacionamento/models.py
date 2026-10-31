from decimal import Decimal

from django.utils.safestring import mark_safe

from comum.models import Municipio
from djtools.db import models


class VeiculoEspecie(models.ModelPlus):
    SEARCH_FIELDS = ['descricao']
    descricao = models.CharField(max_length=20, unique=True)

    class Meta:
        ordering = ['descricao']
        verbose_name = 'Espécie de Veículo'
        verbose_name_plural = 'Espécies de Veículos'

    def __str__(self):
        return self.descricao


class VeiculoTipo(models.ModelPlus):
    SEARCH_FIELDS = ['descricao']
    descricao = models.CharField(max_length=20, unique=True)
    especie = models.ManyToManyField(VeiculoEspecie, through='VeiculoTipoEspecie')

    class Meta:
        ordering = ['descricao']
        verbose_name = 'Tipo de Veículo'
        verbose_name_plural = 'Tipos de Veículos'

    def __str__(self):
        return self.descricao


class VeiculoTipoEspecie(models.ModelPlus):
    SEARCH_FIELDS = ['especie__descricao', 'tipo__descricao']
    tipo = models.ForeignKeyPlus(VeiculoTipo, on_delete=models.CASCADE)
    especie = models.ForeignKeyPlus(VeiculoEspecie, on_delete=models.CASCADE)

    class Meta:
        ordering = ['tipo']
        verbose_name = 'Tipo e Espécie do Veículo'
        verbose_name_plural = 'Tipos e Espécies dos Veículos'

    def __str__(self):
        return f'{self.tipo.descricao} - {self.especie.descricao}'


class VeiculoMarca(models.ModelPlus):
    nome = models.CharField(max_length=20, unique=True)

    class Meta:
        ordering = ['nome']
        verbose_name = 'Marca de Veículo'
        verbose_name_plural = 'Marcas de Veículos'

    def __str__(self):
        return self.nome


class VeiculoModelo(models.ModelPlus):
    nome = models.CharField(max_length=20)
    marca = models.ForeignKeyPlus(VeiculoMarca, on_delete=models.CASCADE)
    tipo_especie = models.ForeignKeyPlus(VeiculoTipoEspecie, verbose_name='Tipo e Espécie', on_delete=models.CASCADE)

    class Meta:
        ordering = ['marca', 'nome']
        verbose_name = 'Modelo de Veículo'
        verbose_name_plural = 'Modelos de Veículos'
        unique_together = ('nome', 'marca')

    def __str__(self):
        return f'{self.marca.nome} {self.nome}'


class VeiculoCor(models.ModelPlus):
    nome = models.CharField(max_length=20, unique=True)

    class Meta:
        ordering = ['nome']
        verbose_name = 'Cor do Veículo'
        verbose_name_plural = 'Cores de Veículos'

    def __str__(self):
        return self.nome


class VeiculoCombustivel(models.ModelPlus):
    nome = models.CharField(max_length=20, unique=True)

    class Meta:
        ordering = ['-nome']
        verbose_name = 'Combustível do Veículo'
        verbose_name_plural = 'Combustíveis de Veículos'

    def __str__(self):
        return self.nome


class Veiculo(models.ModelPlus):
    vinculos_condutores = models.ManyToManyField('comum.Vinculo')
    modelo = models.ForeignKeyPlus(VeiculoModelo, on_delete=models.CASCADE)
    cor = models.ForeignKeyPlus(VeiculoCor, on_delete=models.CASCADE)
    ano_fabric = models.PositiveSmallIntegerField(verbose_name='Ano de Fabricação', blank=True)

    # dados da placa atual do veículo e a cidade de origem
    # placa_localizacao_atual = models.ForeignKeyPlus(Cidade, verbose_name=u'Localização', null=True, blank=True, on_delete=models.CASCADE)
    placa_municipio_atual = models.ForeignKeyPlus(
        Municipio,
        verbose_name='Localização',
        null=True,
        blank=True,
        default=None,
        related_name='veiculo_placa_municipio_anterior_set',
        on_delete=models.CASCADE,
    )
    placa_codigo_atual = models.CharField(max_length=9, verbose_name='Placa', unique=True)
    # localizacao_veiculo_atual = models.ForeignKeyPlus(Estado, verbose_name=u'UF', null=True, blank=True, on_delete=models.CASCADE)

    # dados da placa anterior do veículo e a cidade de origem
    # placa_localizacao_anterior = models.ForeignKeyPlus(Cidade, null=True, blank=True, related_name='veiculo_placa_mun_anterior_set', on_delete=models.CASCADE)
    placa_municipio_anterior = models.ForeignKeyPlus(Municipio, null=True, blank=True, default=None, on_delete=models.CASCADE)
    placa_codigo_anterior = models.CharField(max_length=9, null=True)
    # localizacao_veiculo_anterior = models.ForeignKeyPlus(Estado, null=True, blank=True, related_name='veiculo_local_anterior_set', on_delete=models.CASCADE)

    lotacao = models.PositiveSmallIntegerField(null=True, blank=True)
    odometro = models.PositiveIntegerField(null=True, blank=True)

    combustiveis = models.ManyToManyField(VeiculoCombustivel)

    capacidade_tanque = models.PositiveSmallIntegerField(null=True, blank=True)
    capacidade_gnv = models.PositiveSmallIntegerField(null=True, blank=True)

    chassi = models.CharField(max_length=17, unique=True, null=True)
    renavam = models.CharField(max_length=11, unique=True, null=True)
    potencia = models.PositiveSmallIntegerField(null=True, blank=True)
    cilindrada = models.PositiveSmallIntegerField(null=True, blank=True)

    obs = models.TextField(verbose_name='Observações', null=True, blank=True)
    rendimento_estimado = models.DecimalFieldPlus(
        'Rendimento Estimado', default=Decimal('0.0'), help_text='Estimativa de quantos quilômetros o veículo percorre com um litro de combustível'
    )

    # campus = models.ForeignKeyPlus(Setor, editable=False, on_delete=models.CASCADE)

    class Meta:
        ordering = ['modelo', 'placa_codigo_atual']
        verbose_name = 'Veículo'
        verbose_name_plural = 'Veículos'

    def __str__(self):
        return f'({self.placa_codigo_atual.upper()}) {self.modelo}'

    def get_condutor_principal(self):
        if self.vinculos_condutores.all():
            return self.vinculos_condutores.all()[0].pessoa.nome
        else:
            return '-'

    get_condutor_principal.short_description = 'Condutor Principal'

    def get_telefone_condutor_principal(self):
        if self.vinculos_condutores.all():
            return mark_safe(self.vinculos_condutores.all()[0].pessoa.telefones)
        else:
            return '-'

    get_telefone_condutor_principal.short_description = 'Telefones do Condutor'

    def get_setor_condutor_principal(self):
        if self.vinculos_condutores.all():
            return self.vinculos_condutores.all()[0].setor
        else:
            return '-'

    get_setor_condutor_principal.short_description = 'Setor do Condutor'
