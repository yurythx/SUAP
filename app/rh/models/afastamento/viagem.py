from djtools.db import models


class ConsolidadasManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter().exclude(situacao__in=[4, 17, 1005])


class Viagem(models.ModelPlus):
    SITUACAO_CHOICES = (
        (1, 'Criado'),
        (2, 'Solicitado Passagem'),
        (3, 'Reservado Passagem'),
        (4, 'Cancelado'),
        (6, 'Aprovado pelo Proponente'),
        (7, 'Aprovado pelo Ordenador de Despesa'),
        (8, 'Efetuado a Execução Financeira'),
        (9, 'Prestado Contas'),
        (10, 'Aprovado pelo Proponente - Prest. Contas'),
        (11, 'Aprovado pelo Ordenador de Despesa - Prest. Contas'),
        (15, 'Viagem Encerrada'),
        (17, 'Não Aprovada'),
        (20, 'Viagem não realizada'),
        (1001, 'Em Andamento'),
        (1002, 'Em Prestação de Contas'),
        (1003, 'Prestação de Contas Pendente'),
        (1004, 'Encerrada - realizada'),
        (1005, 'Encerrada - não realizada'),
    )

    codigo_siorg = models.CharFieldPlus('Código Siorg Solicitante', null=False, blank=False)
    nome_siorg = models.CharFieldPlus('Nome Siorg Solicitante', null=False, blank=False)

    servidor = models.ForeignKeyPlus('rh.Servidor', related_name='viagemscdpservidor_set', null=True, on_delete=models.CASCADE)
    vinculo = models.ForeignKeyPlus('comum.Vinculo', related_name='viagemscdpvinculo_set', null=True, on_delete=models.CASCADE)

    nome_proposto = models.CharFieldPlus('Nome do Proposto', null=False, blank=False)

    tipo_proposto = models.CharFieldPlus('Tipo de Proposto', null=False, blank=False)

    numero_pcdp = models.CharFieldPlus('Número PCDP', null=False, blank=False, unique=True)
    motivo_viagem = models.TextField('Motivo da Viagem', blank=True)
    objetivo_viagem = models.TextField('Objetivo da Viagem', blank=True)

    data_inicio_viagem = models.DateFieldPlus('Data Inicial da Viagem', null=False, blank=False, db_index=True)
    data_fim_viagem = models.DateFieldPlus('Data Fim da Viagem', null=False, blank=False, db_index=True)

    quantidade_viagens = models.IntegerField('Quantidade de Viagens', null=True, blank=True)
    quantidade_de_dias_afastamento = models.IntegerField('Quantidade de dias afastados', null=True, blank=True)
    quantidade_de_diarias = models.DecimalFieldPlus('Quantidade de diarias', null=True, blank=True)

    valor_desconto_auxilio_alimentacao = models.DecimalFieldPlus('Valor de desconto do auxílio alimentação', null=True, blank=True)
    valor_desconto_auxilio_transporte = models.DecimalFieldPlus('Valor de desconto do auxílio transporte', null=True, blank=True)

    valor_passagem = models.DecimalFieldPlus('Valor da passagem', null=True, blank=True)
    valor_diaria = models.DecimalFieldPlus('Valor da diária', null=True, blank=True)
    valor_viagem = models.DecimalFieldPlus('Valor da viagem', null=True, blank=True)

    situacao = models.PositiveIntegerField('Situação', choices=SITUACAO_CHOICES)

    consolidadas = ConsolidadasManager()
    objects = models.Manager()

    class Meta:
        verbose_name = 'Viagem'
        verbose_name_plural = 'Viagens'
        permissions = (
            ('pode_ver_relatorios_viagens', 'Pode ver relatórios viagens'),
            ('pode_ver_relatorios_viagens_detalhados', 'Pode ver relatórios viagens detalhados'),
        )

    def __str__(self):
        return 'Viagem de {} - {} (de {} à {}) - {}'.format(
            self.servidor,
            self.objetivo_viagem,
            self.data_inicio_viagem.strftime('%d/%m/%Y'),
            self.data_fim_viagem.strftime('%d/%m/%Y'),
            self.get_situacao_display(),
        )

    def get_absolute_url(self):
        return f'/rh/tela_pcdp/{self.pk:d}/'

    def get_motivo_viagem_truncate(self):
        return self.motivo_viagem[:254]

    @property
    def get_data_emissao_bilhetes(self):
        if self.bilheteviagem_set.all().exists():
            return self.bilheteviagem_set.all().latest('data_emissao').data_emissao
        return None

    @classmethod
    def get_viagens(cls, servidor, data_inicial, data_final):
        return cls.consolidadas.filter(servidor=servidor, data_inicio_viagem__lte=data_final, data_fim_viagem__gte=data_inicial)


class BilheteViagem(models.ModelPlus):
    viagem = models.ForeignKeyPlus('rh.Viagem', null=True, blank=True, verbose_name='Viagem')
    numero = models.CharFieldPlus('Número do Bilhete', null=False, blank=False)
    tipo = models.CharFieldPlus('Tipo', null=False, blank=False)
    data_emissao = models.DateFieldPlus('Data da Emissão', null=True, blank=False, db_index=True)
    status = models.CharFieldPlus('Status', null=False, blank=False)

    class Meta:
        unique_together = ('viagem', 'numero')
        verbose_name = 'Bilhete da Viagem'
        verbose_name_plural = 'Bilhetes das Viagens'

    def __str__(self):
        return f'Bilhete {self.numero} ({self.status})'
