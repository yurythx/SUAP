import datetime

from djtools.db import models
from djtools.utils import contar_dias_uteis, intervalo_intersecao
from rh.managers import ServidorAfastamentoManager


class AfastamentoSiape(models.ModelPlus):
    LICENCA_TRATAMENTO_SAUDE_EST = '0084'
    LICENCA_TRATAMENTO_SAUDE_INFERIOR_15_DIAS_EST = '0270'
    HIST_CLT_LICENCA_TRATAMENTO_SAUDE = '0181'
    HIST_CLT_LICENCA_TRATAMENTO_SAUDE_1 = '0239'
    LICENCA_TRATAMENTO_SAUDE_CONVENIO_INSS = '0163'
    LICENCA_TRATAMENTO_SAUDE_CONTRIBUICAO_RGPS_15_DIAS = '0162'
    HIST_EST_L1711_52_LICENCA_TRATAMENTO_SAUDE = '0238'

    LICENCAS_TRATAMENTO_SAUDE = [
        LICENCA_TRATAMENTO_SAUDE_EST,
        LICENCA_TRATAMENTO_SAUDE_INFERIOR_15_DIAS_EST,
        HIST_CLT_LICENCA_TRATAMENTO_SAUDE,
        HIST_CLT_LICENCA_TRATAMENTO_SAUDE_1,
        LICENCA_TRATAMENTO_SAUDE_CONVENIO_INSS,
        LICENCA_TRATAMENTO_SAUDE_CONTRIBUICAO_RGPS_15_DIAS,
        HIST_EST_L1711_52_LICENCA_TRATAMENTO_SAUDE,
    ]

    AFASTAMENTOS_MANDATO_ELETIVO = ['0014', '0015', '0016', '0017', '0018', '0019', '0020']
    AFASTAMENTOS_INTERESSE_PARTICULAR = ['0404', '0300', '0284', '0283', '0085']

    AFASTAMENTO_STRICTU_SENSU = '0028'
    LICENCA_CAPACITACAO_3_MESES = '0081'

    FALTAS = 1
    ATRASOS = 2
    LICENCA_INCENTIVADA = 3
    OUTROS = 4

    TIPO_AFASTAMENTO_CHOICES = ((FALTAS, 'Faltas'), (ATRASOS, 'Atrasos'), (LICENCA_INCENTIVADA, 'Licença Incentivada'), (OUTROS, 'Outros'))
    codigo = models.CharField(max_length=4, unique=True, db_index=True)
    sigla = models.CharField(max_length=10)
    nome = models.CharField(max_length=60)
    tipo = models.PositiveIntegerField('Tipos de Afastamentos', choices=TIPO_AFASTAMENTO_CHOICES)
    interrompe_pagamento = models.BooleanField('Interrompe pagamento', default=False, blank=True)
    interrompe_tempo_servico = models.BooleanField('Interrompe tempo de serviço', default=False, blank=True)
    excluido = models.BooleanField('Excluído', default=False)
    #
    # demanda 1062 - afastamentos que suspendem estágio probatório
    # OFÍCIO-CIRCULAR Nº 9/2021/DAJ/COLEP/CGGP/SAA-MEC
    suspende_estagio_probatorio = models.BooleanField('Suspende estágio probatório', default=False, blank=True)

    #
    # FIXME: remover essa redefinição do 'save' caso o atributo 'interrompe_tempo_servico' seja setado no 'extrator'
    def save(self, *args, **kwargs):
        #
        # no caso de novo registro (via extrator do SIAPE, espera-se),
        # seta o atributo interrompe_tempo_servico tendo o mesmo valor de interrompe_pagamento
        if not self.id:
            self.interrompe_tempo_servico = self.interrompe_pagamento
        #
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.codigo} - {self.nome}'

    class Meta:
        verbose_name = 'Afastamentos SIAPE'
        verbose_name_plural = 'Afastamentos SIAPE'


class ServidorAfastamento(models.ModelPlus):
    servidor = models.ForeignKeyPlus('rh.Servidor', editable=False, on_delete=models.CASCADE)
    afastamento = models.ForeignKeyPlus(AfastamentoSiape, editable=False, on_delete=models.CASCADE)

    data_inicio = models.DateField(null=True, editable=False, db_index=True)
    data_termino = models.DateField(null=True, blank=True, db_index=True)
    quantidade_dias_afastamento = models.PositiveIntegerFieldPlus('Quantidade de dias afastamento', default=0)
    tem_efeito_financeiro = models.BooleanField('Tem efeito financeiro', null=False, blank=False, default=False)
    cancelado = models.BooleanField('Cancelado', null=False, blank=False, default=False)
    qtd_minuto_afastamento = models.CharFieldPlus('Quantidade de Minutos de Afastamento', null=True, blank=True)

    DESCONSIDERAR_REGRA_30_DIAS_CODIGOS = [
        '0391',
    ]  # código dos afastamentos que podem realizar essa configuração
    desconsiderar_regra_30_dias = models.BooleanField(
        'Desconsiderar regra dos 30 dias?',
        null=False,
        blank=False,
        default=False,
    )

    objects = ServidorAfastamentoManager()

    class Meta:
        unique_together = ('servidor', 'afastamento', 'data_inicio')
        indexes = [models.Index(fields=['servidor', 'afastamento', 'data_inicio'], name='rh_servidorafastamento_indexes')]
        verbose_name = 'Afastamento SIAPE do Servidor'
        verbose_name_plural = 'Afastamentos SIAPE dos Servidores'

    def __str__(self):
        return f'{self.servidor} - {self.afastamento.nome} ({self.data_inicio} à {self.data_termino})'

    def get_absolute_url(self):
        return f'/admin/rh/servidorafastamento/{self.pk}/view/'

    def save(self, *args, **kwargs):
        self.quantidade_dias_afastamento = self.get_qtde_dias().days
        super().save(*args, **kwargs)

    def get_qtde_dias(self):
        if not self.data_termino:
            return datetime.timedelta(1)

        dt_termino = self.data_termino
        dt_inicio = self.data_inicio

        if isinstance(dt_inicio, datetime.datetime):
            dt_inicio = datetime.datetime.date(dt_inicio)
        if isinstance(dt_termino, datetime.datetime):
            dt_termino = datetime.datetime.date(dt_termino)

        return dt_termino - dt_inicio

    def dias_incluindo_ultimo_dia(self):
        return self.get_qtde_dias().days + 1

    def dias_uteis(self, data_inicio=None, data_terminio=None):
        if data_inicio and data_terminio:
            (data_inicio, data_terminio) = intervalo_intersecao(data_inicio, data_terminio, self.data_inicio, self.data_termino)
            return contar_dias_uteis(data_inicio, data_terminio)
        return contar_dias_uteis(self.data_inicio, self.data_termino, self.servidor.setor_exercicio.uo)

    def ch_intervalo(self, data_inicial=None, data_final=None):
        ch = self.servidor.jornada_trabalho.get_jornada_trabalho_diaria()
        dias_uteis = self.dias_uteis(data_inicial, data_final)
        return ch * dias_uteis

    @classmethod
    def get_afastamentos(cls, servidor, data_inicial, data_final):
        return cls.objects.filter(servidor=servidor, data_inicio__lte=data_final, data_termino__gte=data_inicial, cancelado=False)

    def minutos_para_horas(self):
        if self.qtd_minuto_afastamento and self.qtd_minuto_afastamento != '0000':
            return int(self.qtd_minuto_afastamento) / 60
        return 0


class AfastamentoSiapeEfetivoExercicio(models.ModelPlus):
    SEARCH_FIELDS = [
        'afastamentos__codigo',
        'afastamentos__nome',
        'afastamentos__sigla',
    ]

    SITUACAO_ATIVO = 1
    SITUACAO_INATIVO = 2
    CHOICES_SITUACAO = ((SITUACAO_ATIVO, 'Ativo'), (SITUACAO_INATIVO, 'Inativo'))
    dias_efetivo_exercicio = models.PositiveIntegerFieldPlus('Dias de Efetivo Exercício', null=False, blank=False)
    afastamentos = models.ManyToManyFieldPlus(AfastamentoSiape, verbose_name='Afastamentos', blank=True, related_name='afastamentos')
    situacao = models.IntegerFieldPlus('Situação', choices=CHOICES_SITUACAO, default=SITUACAO_ATIVO)

    class Meta:
        verbose_name = 'Afastamento Siape de Efetivo Exercício'
        verbose_name_plural = 'Afastamentos Siape de Efetivo Exercício'

    def codigos_afastamentos(self):
        lista = []
        for a in self.afastamentos.all():
            lista.append(a.codigo)
        return lista
