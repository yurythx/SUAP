import datetime
from decimal import Decimal

from django.conf import settings

from comum.utils import get_todos_campi, get_uo
from djtools.db import models, transaction
from djtools.templatetags.filters import format_money
from djtools.utils import unused
from materiais.models import Material, MaterialTag
from rh.models import Servidor, UnidadeOrganizacional


@unused
class ProcessoCompra(models.ModelPlus):
    STATUS_AGUARDANDO_VALIDACAO = 1
    STATUS_VALIDADO = 2
    cadastrado_em = models.DateTimeField(auto_now_add=True)
    cadastrado_por = models.CurrentUserField()
    descricao = models.CharField('Descrição', max_length=255)
    observacao = models.TextField('Observação', blank=True)
    status = models.IntegerField(
        default=STATUS_AGUARDANDO_VALIDACAO, choices=[[STATUS_AGUARDANDO_VALIDACAO, 'Aguardando validação'], [STATUS_VALIDADO, 'Validado']]
    )
    data_inicio = models.DateTimeField('Data de Início')
    data_fim = models.DateTimeField('Data de Fim')
    validado_por = models.ForeignKeyPlus('comum.User', null=True, blank=True, on_delete=models.CASCADE, related_name='abc', editable=False)
    validado_em = models.DateTimeField(null=True, blank=True, editable=False)
    tags = models.ManyToManyField('materiais.MaterialTag', blank=True)

    class Meta:
        permissions = (('pode_gerenciar_processocompra', 'Pode gerenciar processos de compra'),)
        verbose_name = 'Processo de Compra'
        verbose_name_plural = 'Processos de Compra'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    @transaction.atomic
    def aplicar_todos_campus(self):
        uos = self.processocompracampus_set.values_list('campus__pk', flat=True)
        for campus in UnidadeOrganizacional.objects.uo().exclude(pk__in=uos):
            ProcessoCompraCampus.objects.create(processo_compra=self, campus=campus, data_inicio=self.data_inicio, data_fim=self.data_fim)

    def __str__(self):
        return self.descricao

    def is_em_periodo_de_inclusao(self):
        return self in ProcessoCompra.get_no_periodo()

    @classmethod
    def get_no_periodo(cls):
        agora = datetime.datetime.now()
        return cls.objects.filter(data_inicio__lte=agora, data_fim__gte=agora)

    @classmethod
    def get_no_periodo_para_mim(cls):
        agora = datetime.datetime.now()
        return cls.objects.filter(data_inicio__lte=agora, data_fim__gte=agora, processocompracampus__campus=get_uo())

    def get_absolute_url(self):
        return f'/compras/processo_compra/{self.pk:d}/'

    def get_itens(self, user=None):
        if user and user.has_perm('compras.pode_gerenciar_processocompra'):
            return self.processocompracampus_set.all()
        else:
            return self.processocompracampus_set.filter(campus__in=get_todos_campi())

    def get_materiais(self):
        materiais_ids = set(
            ProcessoCompraCampusMaterial.objects.filter(processo_compra_campus__processo_compra=self)
            .values_list('material', flat=True)
            .order_by('material')
        )
        return Material.objects.filter(id__in=materiais_ids)

    def get_materiais_sem_cotacao(self):
        materiais_ids = set(
            ProcessoCompraCampusMaterial.objects.filter(processo_compra_campus__processo_compra=self)
            .values_list('material', flat=True)
            .order_by('material')
        )
        return Material.get_sem_cotacao().filter(id__in=materiais_ids)

    def pode_validar(self, user):
        if self.processocompracampus_set.filter(status=self.STATUS_AGUARDANDO_VALIDACAO).exists():
            return False

        if self.status == self.STATUS_VALIDADO:
            return False

        return user.has_perm('compras.pode_gerenciar_processocompra')

    @transaction.atomic
    def validar(self, user):
        # Gravando em ProcessoCompraMaterial
        self.processocompramaterial_set.all().delete()
        for material in self.get_materiais():
            valor_referencia = []
            for c in material.materialcotacao_set.all():
                valor_referencia.append(f'{c.material.id}: {format_money(c.valor)}')

            valor_referencia = ' | '.join(valor_referencia)
            material_tag = material.tags.exists() and material.tags.all()[0] or None
            ProcessoCompraMaterial.objects.create(
                processo_compra=self,
                material=material,
                material_tag=material_tag,
                valor_unitario=material.valor_medio,
                valor_referencia=valor_referencia,
            )

            ProcessoCompraCampusMaterial.objects.filter(processo_compra_campus__processo_compra=self, material=material).update(
                material_tag=material_tag
            )

        # Atualizando os valores dos itens de compra
        for i in ProcessoCompraCampusMaterial.objects.filter(processo_compra_campus__processo_compra=self):
            i.atualizar_valores(atualizar_processo_compra_campus=False)

        for i in self.processocompracampus_set.all():
            i.atualizar_valores()

        # Atualizando as informações de self
        self.status = self.STATUS_VALIDADO
        self.validado_em = datetime.datetime.now()
        self.validado_por = user
        self.save()


@unused
class ProcessoCompraMaterial(models.ModelPlus):
    """
    Classe para guardar histórico de informações sobre cotações do material.
    É preenchido na validação do processo de compra.
    """

    processo_compra = models.ForeignKeyPlus('compras.ProcessoCompra', on_delete=models.CASCADE)
    material = models.ForeignKeyPlus('materiais.Material', on_delete=models.CASCADE)
    material_tag = models.ForeignKeyPlus('materiais.MaterialTag', null=True, on_delete=models.CASCADE)
    valor_unitario = models.DecimalFieldPlus(default=0, editable=False)
    valor_referencia = models.TextField()

    class Meta:
        ordering = ['material_tag', 'material__id']


@unused
class ProcessoCompraCampus(models.ModelPlus):
    STATUS_AGUARDANDO_VALIDACAO = 1
    STATUS_VALIDADO = 2
    processo_compra = models.ForeignKeyPlus('compras.ProcessoCompra', on_delete=models.CASCADE)
    campus = models.ForeignKeyPlus(UnidadeOrganizacional, on_delete=models.CASCADE)
    data_inicio = models.DateTimeField()
    data_fim = models.DateTimeField()
    status = models.IntegerField(
        default=STATUS_AGUARDANDO_VALIDACAO,
        choices=[[STATUS_AGUARDANDO_VALIDACAO, 'Aguardando validação'], [STATUS_VALIDADO, 'Validado']],
        editable=False,
    )
    validado_por = models.ForeignKeyPlus('comum.User', null=True, blank=True, editable=False, on_delete=models.CASCADE)
    validado_em = models.DateTimeField(null=True, blank=True, editable=False)
    valor_total = models.DecimalFieldPlus(default=0, editable=False)

    class Meta:
        ordering = ('processo_compra', 'campus__setor__sigla')
        unique_together = ('processo_compra', 'campus')
        permissions = (('pode_validar_do_seu_campus', 'Pode validar processos de compra do seu campus'),)
        verbose_name = 'Processo Compra Campus'
        verbose_name_plural = 'Processo Compra Campus'

    def __str__(self):
        return f'{self.processo_compra} - {self.campus}'

    def get_absolute_url(self):
        return f'/compras/processo_compra_campus/{self.pk:d}/'

    def atualizar_valores(self):
        self.valor_total = sum(self.get_itens().values_list('valor_total', flat=True))
        ProcessoCompraCampus.objects.filter(pk=self.pk).update(valor_total=self.valor_total)

    def get_valor_total_por_tag(self):
        valores = {}
        for tag in MaterialTag.objects.all():
            itens = self.get_itens().filter(material__tags=tag)
            if itens:
                valores[tag] = sum(i.valor_total for i in itens)
        return valores

    def get_itens(self):
        return self.processocompracampusmaterial_set.filter(material__ativo=True).order_by('material__id')

    def get_materiais_ausentes(self, user):
        """
        Retorna os itens que não foram escolhidos para este campus e que
        foram escolhidos por algum outro do mesmo processo de compra.
        """
        todos = self.processo_compra.get_materiais().values_list('id', flat=True)
        incluidos = self.get_itens().values_list('material', flat=True)
        return Material.objects.filter(id__in=list(set(todos) - set(incluidos)))

    def preencher_materiais_ausentes(self, user):
        """
        Insere a quantidade 1 para todos os materiais presentes no processo de
        compra que não foram inseridos no processo de compra do campus (self).
        """
        for material in self.get_materiais_ausentes(user):
            ProcessoCompraCampusMaterial.objects.create(
                processo_compra_campus=self, material=material, material_tag=material.tags.exists() and material.tags.all()[0] or None, qtd=1
            )

    def estah_no_periodo(self):
        return self.data_inicio <= datetime.datetime.now() <= self.data_fim and self.status == self.STATUS_AGUARDANDO_VALIDACAO

    def estah_validado(self):
        return self.status == self.STATUS_VALIDADO

    def pode_validar(self, user):
        if not self.estah_no_periodo() or self.estah_validado():
            return False

        if self.get_itens().filter(material__in=Material.get_sem_cotacao()).exists():
            return False

        if user.has_perm('compras.pode_gerenciar_processocompra'):
            return True

        return user.has_perm('compras.pode_validar_do_seu_campus')

    def validar(self, user):
        for processo in self.get_itens():
            for cotacao in processo.material.materialcotacao_set.all():
                ProcessoMaterialCotacao.objects.create(processo_compra=self.processo_compra, material=processo.material, cotacao=cotacao)

        self.status = self.STATUS_VALIDADO
        self.validado_em = datetime.datetime.now()
        self.validado_por = user
        self.save()


@unused
class ProcessoCompraCampusMaterial(models.ModelPlus):
    cadastrado_em = models.DateTimeField(auto_now_add=True)
    cadastrado_por = models.CurrentUserField()
    processo_compra_campus = models.ForeignKeyPlus('compras.ProcessoCompraCampus', on_delete=models.CASCADE)
    material = models.ForeignKeyPlus('materiais.Material', on_delete=models.CASCADE)
    material_tag = models.ForeignKeyPlus('materiais.MaterialTag', null=True, on_delete=models.CASCADE)
    qtd = models.FloatField()
    valor_unitario = models.DecimalFieldPlus(default=0, editable=False)
    valor_total = models.DecimalFieldPlus(
        default=0, editable=False, help_text='Esse valor vai ser atualizado após o processo de compra ser validado.'
    )

    class Meta:
        unique_together = ('processo_compra_campus', 'material')
        verbose_name = 'Material em processo de compra'
        verbose_name_plural = 'Materiais em processo de compra'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.atualizar_valores()

    def atualizar_valores(self, atualizar_processo_compra_campus=True):
        if self.processo_compra_campus.processo_compra.status == ProcessoCompra.STATUS_VALIDADO:
            return
        self.valor_unitario = self.material.valor_medio
        self.valor_total = Decimal(f'{self.qtd:.2f}') * self.material.valor_medio
        ProcessoCompraCampusMaterial.objects.filter(pk=self.pk).update(valor_unitario=self.valor_unitario, valor_total=self.valor_total)
        if atualizar_processo_compra_campus:
            self.processo_compra_campus.atualizar_valores()


@unused
class ProcessoMaterialCotacao(models.ModelPlus):
    processo_compra = models.ForeignKeyPlus('compras.ProcessoCompra', on_delete=models.CASCADE)
    material = models.ForeignKeyPlus('materiais.Material', on_delete=models.CASCADE)
    cotacao = models.ForeignKeyPlus('materiais.MaterialCotacao', on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Processo de Compra Cotação'
        verbose_name_plural = 'Processos de Compra Cotações'


@unused
class Calendario(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição', max_length=1000)
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Calendário'
        verbose_name_plural = 'Calendários'

    def __str__(self):
        return self.descricao


@unused
class TipoEvento(models.ModelPlus):
    COR_CHOICE = (
        ('alert', 'Amarelo'),
        ('info', 'Azul'),
        ('extra', 'Laranja'),
        ('extra2', 'Roxo'),
        ('success', 'Verde'),
        ('error', 'Vermelho'),
        ('nenhum', 'Nenhum'),
    )
    descricao = models.CharFieldPlus('Descrição', max_length=1000)
    calendario = models.ForeignKeyPlus(Calendario, verbose_name='Calendário', on_delete=models.CASCADE)
    cor = models.CharFieldPlus('Cor', help_text='Informe uma cor para o tipo de evento', choices=COR_CHOICE)
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Tipo de Evento'
        verbose_name_plural = 'Tipos de Evento'

    def __str__(self):
        return self.descricao


@unused
class Evento(models.ModelPlus):
    tipo_evento = models.ForeignKeyPlus(TipoEvento, verbose_name='Tipo de Evento', on_delete=models.CASCADE)
    data_inicio = models.DateFieldPlus('Data de Início')
    data_fim = models.DateFieldPlus('Data de Fim')
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Evento'
        verbose_name_plural = 'Eventos'

    def __str__(self):
        return f'{self.tipo_evento}'


class Nucleo(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição', max_length=1000)
    componentes = models.ManyToManyFieldPlus(Servidor, verbose_name='Servidores Relacionados')
    ativo = models.BooleanField('Ativo', default=True)
    responsavel_vinculo = models.ForeignKeyPlus('comum.Vinculo', null=True, blank=True, verbose_name='Servidor Responsável', on_delete=models.CASCADE)
    setor_responsavel = models.ForeignKeyPlus('rh.Setor', verbose_name='Setor Responsável', null=True, on_delete=models.SET_NULL)
    campus_responsavel = models.ForeignKeyPlus(
        UnidadeOrganizacional,
        verbose_name='Campus Responsável',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='nucleo_campus_responsavel',
    )
    campi_vinculados = models.ManyToManyFieldPlus(
        UnidadeOrganizacional,
        verbose_name='Campi Vinculados',
        related_name='nucleo_campi_vinculados',
    )

    class Meta:
        verbose_name = 'Núcleo'
        verbose_name_plural = 'Núcleos'

    def __str__(self):
        return f'{self.descricao}'

    def get_vinculos_componentes(self):
        vinculos_componentes = []
        for servidor in self.componentes.all():
            vinculos_componentes.append(servidor.get_vinculo())
        return vinculos_componentes


@unused
class TipoProcesso(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição', max_length=1000)
    tipo_calendario = models.ForeignKeyPlus(Calendario, verbose_name='Tipo do Calendário', on_delete=models.CASCADE)
    nucleo_responsavel = models.ForeignKeyPlus(Nucleo, verbose_name='Núcleo Responsável', on_delete=models.CASCADE)
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Tipo de Processo'
        verbose_name_plural = 'Tipos de Processo'

    def __str__(self):
        return self.descricao


@unused
class Processo(models.ModelPlus):
    SITUACAO_PROCESSO = (
        ('Aberto', 'Aberto'),
        ('Suspenso', 'Suspenso'),
        ('Concluído', 'Concluído'),
    )
    tipo_processo = models.ForeignKeyPlus(TipoProcesso, verbose_name='Tipo do Processo', on_delete=models.CASCADE)
    situacao = models.CharFieldPlus('Situação', max_length=30, choices=SITUACAO_PROCESSO)

    class Meta:
        verbose_name = 'Processo de Compra e Contratação'
        verbose_name_plural = 'Processos de Compra e Contratação'

    def __str__(self):
        return f'{self.tipo_processo.descricao} - {self.tipo_processo.tipo_calendario.descricao}'

    def get_campi_solicitantes(self):
        return ', '.join(
            {
                registro.campus_solicitante.sigla
                for registro in SolicitacaoParticipacao.objects.filter(fase__processo=self).order_by('campus_solicitante__sigla')
            }
        )


@unused
class Fase(models.ModelPlus):
    COR_CHOICE = (
        ('alert', 'Amarelo'),
        ('info', 'Azul'),
        ('extra', 'Laranja'),
        ('extra2', 'Roxo'),
        ('success', 'Verde'),
        ('error', 'Vermelho'),
        ('nenhum', 'Nenhum'),
    )
    cor = models.CharFieldPlus('Cor', help_text='Informe uma cor para a fase', choices=COR_CHOICE)
    processo = models.ForeignKeyPlus(Processo, verbose_name='Processo', on_delete=models.CASCADE)
    descricao = models.CharFieldPlus('Descrição', max_length=1000)
    data_inicio = models.DateFieldPlus('Data de Início')
    data_fim = models.DateFieldPlus('Data de Fim')
    fase_inicial = models.BooleanField('É uma fase inicial?', default=False)
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Fase do Processo'
        verbose_name_plural = 'Fases do Processo'

    def __str__(self):
        return '{}: {} - {}'.format(self.processo.tipo_processo.descricao, self.data_inicio.strftime('%d/%m/%Y'), self.data_fim.strftime('%d/%m/%Y'))


@unused
class SolicitacaoParticipacao(models.ModelPlus):
    fase = models.ForeignKeyPlus(Fase, verbose_name='Fase', on_delete=models.CASCADE)
    solicitada_em = models.DateTimeFieldPlus('Solicitada Em')
    solicitada_por = models.ForeignKeyPlus(Servidor, verbose_name='Solicitada Por', on_delete=models.CASCADE)
    campus_solicitante = models.ForeignKeyPlus(UnidadeOrganizacional, verbose_name='Campus Solicitante', on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Solicitação de Participação'
        verbose_name_plural = 'Solicitações de Participação'

    def __str__(self):
        return f'Solicitação do Campus {self.campus_solicitante} para a Fase: {self.fase}'


# Novos modelos para gestão dos processos  de compras
class EtapasProcessoCompra:
    """
    Etapas de um processo de Compra
    """

    ABERTURA_PROCESSO = 'abertura_processo'
    DOCUMENTO_DOD_DFD = 'documento_dod_dfd'
    PORTARIA_EQUIPE_PLANEJAMENTO = 'portaria_equipe_planejamento'
    ESTUDO_TECNICO_PRELIMINAR = 'estudo_tecnico_preliminar'
    PESQUISA_PRECO = 'pesquisa_preco'
    INTENCAO_REGISTRO_PRECO = 'divulgacao_irp'
    AJUSTES_IRP_ARP = 'ajustes_irp_arp'
    TERMO_REFERENCIA = 'termo_referencia'
    IMR = 'imr'
    PLANILHAS_CUSTOS = 'planilhas_custos'
    MAPA_RISCOS = 'mapa_riscos'
    MINUTA_CONTRATO = 'minuta_contrato'
    CERTIFICACAO_PROCESSUAL = 'certificacao_processual'
    EDITAL = 'edital'
    ANALISE_JURIDICA = 'analise_juridica'
    ATENDIMENTO_RECOMENDACOES_JURIDICAS = 'atendimento_recomendacoes_juridicas'
    DIVULGACAO_CERTAME = 'divulgacao_certame'
    SESSAO_PUBLICA = 'sessao_publica'
    ADJUDICACAO_HOMOLOGACAO = 'adjudicacao_homologacao'
    ELABORACAO_ATAS_ARP = 'elaboracao_atas_arp'
    DIVULGACAO_DOU = 'divulgacao_dou'

    ETAPAS_PROCESSO_CHOICES = [
        (ABERTURA_PROCESSO, 'Abertura do Processo'),
        (DOCUMENTO_DOD_DFD, 'Documento de Oficialização da Demanda - DOD/DFD e Previsão no PCA'),
        (PORTARIA_EQUIPE_PLANEJAMENTO, 'Portaria da Equipe de Planejamento'),
        (ESTUDO_TECNICO_PRELIMINAR, 'Estudo Técnico Preliminar - ETP'),
        (PESQUISA_PRECO, 'Pesquisa de Preços, Nota Técnica e Mapa Comparativo'),
        (INTENCAO_REGISTRO_PRECO, 'Divulgação da Intenção de Registro de Preços - IRP'),
        (AJUSTES_IRP_ARP, 'Ajustes após Intenção de Registro de Preços - IRP e Minuta da Ata de Registro de Preços - ARP'),
        (TERMO_REFERENCIA, 'Termo de Referência - TR'),
        (IMR, 'Instrumento de Medição de Resultados - IMR'),
        (PLANILHAS_CUSTOS, 'Planilhas de Custos ou outros documentos acessórios'),
        (MAPA_RISCOS, 'Mapa de Riscos - MR'),
        (MINUTA_CONTRATO, 'Minuta de Contrato'),
        (CERTIFICACAO_PROCESSUAL, 'Certificação Processual, Lista de Verificação, portarias da autoridade competente e do pregoeiro'),
        (EDITAL, 'Edital'),
        (ANALISE_JURIDICA, 'Análise Jurídica - PROJU'),
        (ATENDIMENTO_RECOMENDACOES_JURIDICAS, 'Atendimento às recomendações jurídicas'),
        (DIVULGACAO_CERTAME, 'Divulgação do certame'),
        (SESSAO_PUBLICA, 'Abertura e realização das sessões do certame'),
        (ADJUDICACAO_HOMOLOGACAO, 'Adjudicação e Homologação'),
        (ELABORACAO_ATAS_ARP, 'Elaboração da(s) Ata(s) de Registro de Preços - ARP'),
        (DIVULGACAO_DOU, 'Divulgação do resultado no Diário Oficial da União - DOU'),
    ]

    @classmethod
    def get_display(cls, etapa):
        dict_etapas = dict(cls.ETAPAS_PROCESSO_CHOICES)
        return dict_etapas.get(etapa, etapa)

    @classmethod
    def is_fase_interna(cls, etapa):
        etapas = [e[0] for e in cls.ETAPAS_PROCESSO_CHOICES]
        try:
            idx = etapas.index(etapa)
            return etapas.index(cls.ABERTURA_PROCESSO) <= idx <= etapas.index(cls.ATENDIMENTO_RECOMENDACOES_JURIDICAS)
        except ValueError:
            return False

    @classmethod
    def is_fase_externa(cls, etapa):
        etapas = [e[0] for e in cls.ETAPAS_PROCESSO_CHOICES]
        try:
            idx = etapas.index(etapa)
            return etapas.index(cls.DIVULGACAO_CERTAME) <= idx <= etapas.index(cls.DIVULGACAO_DOU)
        except ValueError:
            return False


class TipoCalendario:
    """
    Tipos de calendário de uma compra (processolicitatorio)
    """

    SISTEMICO = 'sistemico'
    NUCLEO_COMPRAS = 'nucleo_compras'
    CAMPUS = 'campus'
    TIPO_CALENDARIO_CHOICES = [
        (SISTEMICO, 'Sistêmico'),
        (NUCLEO_COMPRAS, 'Núcleo de Compra'),
        (CAMPUS, 'Campus'),
    ]

    @classmethod
    def get_display(cls, tipo):
        dict_tipos = dict(cls.TIPO_CALENDARIO_CHOICES)
        return dict_tipos.get(tipo, tipo)


class TipoCompra:
    CONCURSO = 'CN'
    DISPENSA_LICITACAO = 'DL'
    INEXIGIBILIDADE_LICITACAO = 'IL'
    PREGAO = 'PG'
    CONCORRENCIA = 'CC'
    CONCORRENCIA_INTERNACIONAL = 'CI'

    TIPO_COMPRA_CHOICES = [
        (CONCURSO, 'Concurso'),
        (DISPENSA_LICITACAO, 'Dispensa de Licitação'),
        (INEXIGIBILIDADE_LICITACAO, 'Inexigibilidade de Licitação'),
        (PREGAO, 'Pregão'),
        (CONCORRENCIA, 'Concorrência'),
        (CONCORRENCIA_INTERNACIONAL, 'Concorrência Internacional'),
    ]


class CategoriaCompra(models.ModelPlus):
    SEARCH_FIELDS = ['descricao']
    COR_CHOICES = [
        ('warning', 'Amarelo'),
        ('info', 'Azul'),
        ('extra', 'Laranja'),
        ('success', 'Verde'),
        ('extra2', 'Roxo'),
    ]

    CATEGORIA_CHOICES = [
        ('Material', 'Material'),
        ('Serviços', 'Serviços'),
        ('Serviços com Mão de Obra', 'Serviços com Mão de Obra'),
        ('Engenharia e obras', 'Engenharia e obras'),
        ('Contratações Diretas', 'Contratações Diretas'),
    ]

    descricao = models.CharFieldPlus('Descrição', choices=CATEGORIA_CHOICES)
    cor = models.CharFieldPlus('Cor', help_text='Informe uma cor para a categoria', choices=COR_CHOICES)
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Categoria de Compra'
        verbose_name_plural = 'Categorias de Compras'

    def __str__(self):
        return self.descricao


class Compra(models.ModelPlus):
    if 'processo_eletronico' in settings.INSTALLED_APPS:
        processo = models.ForeignKeyPlus('processo_eletronico.Processo', verbose_name='Processo', on_delete=models.CASCADE, null=True, blank=True)
    etapa_atual = models.CharFieldPlus(
        max_length=50, choices=EtapasProcessoCompra.ETAPAS_PROCESSO_CHOICES, default=EtapasProcessoCompra.ABERTURA_PROCESSO, null=False, blank=False
    )
    objeto = models.TextField(verbose_name='Objeto', blank=False, max_length=500)
    data_abertura = models.DateField(verbose_name='Data de Abertura', null=False, blank=False)
    categoria = models.ForeignKeyPlus(CategoriaCompra, verbose_name='Categoria', on_delete=models.CASCADE, null=True, blank=False)
    data_prevista_fim = models.DateField(verbose_name='Data Prevista de Conclusão', null=False, blank=False)
    tipo_compra = models.CharField(verbose_name='Modalidade', max_length=2, choices=TipoCompra.TIPO_COMPRA_CHOICES, null=True, blank=True)
    tipo_calendario = models.CharFieldPlus(
        max_length=30,
        choices=TipoCalendario.TIPO_CALENDARIO_CHOICES,
        verbose_name='Tipo de Calendário',
        null=False,
        blank=False,
    )
    nucleo_responsavel = models.ForeignKeyPlus(
        Nucleo,
        verbose_name='Núcleo Responsável',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    campus_responsavel = models.ForeignKeyPlus(
        UnidadeOrganizacional,
        verbose_name='Campus Responsável',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='compras_campus_responsavel',
    )
    campi_vinculados = models.ManyToManyFieldPlus(
        UnidadeOrganizacional,
        verbose_name='Campi Vinculados',
        related_name='compras_campi_vinculados',
    )
    concluido = models.BooleanField(verbose_name='Concluído', default=False)
    servidor_conclusao = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Responsável pela Liberação', on_delete=models.CASCADE, null=True)
    data_conclusao = models.DateTimeFieldPlus(verbose_name='Data de Conclusão', null=True, blank=True)

    def __str__(self):
        return f'{self.objeto} - {self.processo}'

    class Meta:
        verbose_name = 'Compra'
        verbose_name_plural = 'Compras'

    def atualizar_etapa_atual(self):
        ultima_etapa = EtapaCompra.objects.filter(compra=self).order_by('-id').first()
        etapa_atual = EtapaCompra.objects.filter(compra=self, data_inicio__lte=datetime.date.today(), data_fim__gte=datetime.date.today()).first()
        if not etapa_atual and ultima_etapa:
            self.etapa_atual = ultima_etapa.etapa
        if etapa_atual and self.etapa_atual != etapa_atual.etapa:
            self.etapa_atual = etapa_atual.etapa
        self.save()

    def pode_registrar_conclusao(self, user):
        tem_permissao = (
            user.has_group_cached('Gerenciador de Compras') or Nucleo.objects.filter(componentes=user.get_vinculo().relacionamento).exists()
        )
        todas_etapas_executadas = not EtapaCompra.objects.filter(compra=self, executada=False).exists()
        return tem_permissao and todas_etapas_executadas and not self.concluido

    def pode_retornar_cronograma(self, user):
        tem_permissao = (
            user.has_group_cached('Gerenciador de Compras') or Nucleo.objects.filter(componentes=user.get_vinculo().relacionamento).exists()
        )
        todas_etapas_executadas = not EtapaCompra.objects.filter(compra=self, executada=False).exists()
        return tem_permissao and todas_etapas_executadas and self.concluido

    def registrar_conclusao(self, user):
        if self.pode_registrar_conclusao(user):
            self.concluido = True
            self.servidor_conclusao = user.get_vinculo()
            self.data_conclusao = datetime.datetime.now()
            self.save()


class EtapaCompra(models.ModelPlus):
    compra = models.ForeignKeyPlus(Compra, verbose_name='Compra', on_delete=models.CASCADE)
    etapa = models.CharFieldPlus(
        choices=EtapasProcessoCompra.ETAPAS_PROCESSO_CHOICES,
        null=False,
        blank=False,
    )
    data_inicio = models.DateFieldPlus(verbose_name='Data de Início', null=False, blank=False)
    data_fim = models.DateFieldPlus(verbose_name='Data de Fim', null=False, blank=False)
    executada = models.BooleanField(verbose_name='Executada', default=False)

    class Meta:
        verbose_name = 'Etapa de Compra'
        verbose_name_plural = 'Etapas de Compras'

    def __str__(self):
        fase = 'Interna' if EtapasProcessoCompra.is_fase_interna(self.etapa) else 'Externa'
        return f'{EtapasProcessoCompra.get_display(self.etapa)} - Fase: {fase}'

    def pode_registrar_execucao(self, user):
        return user.has_group_cached('Gerenciador de Compras') or Nucleo.objects.filter(componentes=user.get_vinculo().relacionamento).exists()


class ComentarioEtapaCompra(models.ModelPlus):
    etapa_compra = models.ForeignKeyPlus('EtapaCompra', related_name='comentarios', on_delete=models.CASCADE)
    vinculo = models.ForeignKeyPlus('comum.Vinculo')
    comentario = models.TextField('Comentário')
    desconsiderado_em = models.DateTimeFieldPlus('Data de Inclusão', null=True)
    data = models.DateTimeFieldPlus('Data de Inclusão', auto_now_add=True, editable=False)

    class Meta:
        ordering = ('-data',)
