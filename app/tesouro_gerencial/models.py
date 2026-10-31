from decimal import Decimal

from django.db.models import Q, Sum

from contracheques.models import ContraCheque, ContraChequeRubrica
from djtools.db import models
from djtools.templatetags.filters import format_money
from djtools.utils import print_
from rh.models import Situacao, UnidadeOrganizacional


class ContaContabil(models.ModelPlus):
    SEARCH_FIELDS = ['codigo', 'nome']
    codigo = models.CharField('Código', max_length=9, unique=True)
    nome = models.CharField('Nome', max_length=300)

    class Meta:
        verbose_name = 'Conta Contábil'
        verbose_name_plural = 'Conta Contábeis'

    def __str__(self):
        return f'{self.codigo} - {self.nome}'


class ClassificacaoInstitucional(models.ModelPlus):
    SEARCH_FIELDS = ['codigo', 'nome']
    """Referenciado como gestão, ex: 26435 = IFRN"""
    codigo = models.CharField('Código', max_length=5, unique=True)
    nome = models.CharField('Nome', max_length=300)

    class History:
        disabled = True

    class Meta:
        verbose_name = 'Classificação Institucional'
        verbose_name_plural = 'Classificações Institucionais'

    def __str__(self):
        return f'{self.codigo} - {self.nome}'


class UnidadeGestora(models.ModelPlus):
    SEARCH_FIELDS = ['codigo', 'nome']
    codigo = models.CharField('Código', max_length=6, unique=True)
    nome = models.CharField('Nome', max_length=50)
    uo = models.ForeignKeyPlus(UnidadeOrganizacional, related_name='unidade_gestoras', null=True, blank=True)

    class History:
        disabled = True

    class Meta:
        verbose_name = 'Unidade Gestora'
        verbose_name_plural = 'Unidades Gestoras'

    def __str__(self):
        return f'{self.codigo} - {self.nome}'

    @staticmethod
    def get_outros_orgaos():
        return (
            UnidadeGestora.objects.all()
            .exclude(codigo__in=UnidadeOrganizacional.objects.values_list('codigo_ugr', flat=True))
            .values_list('codigo', flat=True)
            .distinct()
        )


class EsferaOrcamentaria(models.ModelPlus):
    codigo = models.CharField('Código', max_length=2, unique=True)
    nome = models.CharField('Nome', max_length=100)

    class Meta:
        verbose_name = 'Esfera Orçamenária'
        verbose_name_plural = 'Esferas Orçamenárias'

    def __str__(self):
        return f'{self.codigo} - {self.nome}'


class AcaoGoverno(models.ModelPlus):
    codigo = models.CharField('Código', max_length=4, unique=True)
    nome = models.CharField('Nome', max_length=200)

    class Meta:
        verbose_name = 'Ação Governo'
        verbose_name_plural = 'Ações Governo'

    def __str__(self):
        return f'{self.codigo} - {self.nome}'


class ProgramaTrabalhoResumido(models.ModelPlus):
    codigo = models.CharField('Código', max_length=6, unique=True)

    class Meta:
        verbose_name = 'Programa de Trabalho Resumido'
        verbose_name_plural = 'Programas de Trabalho Resumido'

    def __str__(self):
        return self.codigo


class PlanoInterno(models.ModelPlus):
    codigo = models.CharField(max_length=11, unique=True)
    nome = models.CharField('Nome', max_length=100, null=True)
    detalhamento = models.CharFieldPlus('detalhamento', max_length=500, null=True, blank=True)

    class Meta:
        verbose_name = 'Plano Interno'
        verbose_name_plural = 'Planos Internos'

    def __str__(self):
        return f'{self.codigo} - {self.nome}'


class FonteRecurso(models.ModelPlus):
    codigo = models.CharField('Código', max_length=10, unique=True)
    nome = models.CharField('Fonte do recurso', max_length=100)

    class Meta:
        verbose_name = 'Fonte de Recurso'
        verbose_name_plural = 'Fontes de Recursos'

    def __str__(self):
        return f'{self.codigo} - {self.nome}'


class NaturezaDespesa(models.ModelPlus):
    SEARCH_FIELDS = ['nome', 'codigo']
    codigo = models.CharField('Código', max_length=6, unique=True)
    nome = models.CharField('Nome', max_length=100)

    class Meta:
        verbose_name = 'Natureza de Despesa'
        verbose_name_plural = 'Naturezas de Despesas'

    def __str__(self):
        return f'{self.codigo} - {self.nome}'


class SubElementoNaturezaDespesa(models.ModelPlus):
    SEARCH_FIELDS = ['codigo_subelemento', 'nome', 'codigo']
    codigo = models.CharField('Código', max_length=8, unique=True)
    codigo_subelemento = models.CharField('Código', max_length=2)
    nome = models.CharField('Nome', max_length=100)
    natureza_despesa = models.ForeignKeyPlus(NaturezaDespesa, verbose_name='Natureza de Despesa')

    class Meta:
        verbose_name = 'Subelemento da Natureza de Despesa'
        verbose_name_plural = 'Subelementos da Natureza de Despesa'
        unique_together = ['codigo_subelemento', 'natureza_despesa']

    def __str__(self):
        return f'{self.natureza_despesa.codigo}.{self.codigo_subelemento} - {self.nome}'

    def save(self, *args, **kwargs):
        self.nome = self.nome or ''
        self.codigo = f'{self.natureza_despesa.codigo}{self.codigo_subelemento}'
        super().save(*args, **kwargs)


class HistoricoImportacao(models.ModelPlus):
    data = models.DateTimeFieldPlus('Data da Importação', auto_now_add=True)

    class Meta:
        verbose_name = 'Histórico de Importação'
        verbose_name_plural = 'Histórico de Importações'


class EventoNotaDotacao(models.ModelPlus):
    ACRESCIMO = [203076, 203079, 203108]
    REDUCAO = [203075, 203078, 203107]
    codigo = models.CharFieldPlus('Código', max_length=6, unique=True)
    nome = models.CharFieldPlus('Nome', max_length=200)

    class Meta:
        verbose_name = 'Evento de Nota de Dotação'
        verbose_name_plural = 'Eventos de Nota de Dotação'

    def __str__(self):
        return f'{self.codigo} - {self.nome}'


class EventoNotaEmpenho(models.ModelPlus):
    INCLUSAO = 401201
    REFORCO = 401202
    ANULACAO = 401203
    codigo = models.CharFieldPlus('Código', max_length=6, unique=True)
    nome = models.CharFieldPlus('Nome', max_length=200)

    class Meta:
        verbose_name = 'Evento de Nota de Empenho'
        verbose_name_plural = 'Eventos de Nota de Empenho'

    def __str__(self):
        return f'{self.codigo} - {self.nome}'


class Importacao(models.ModelPlus):
    TIPO_MOV_CREDITO = 'Movimentações de crédito'
    TIPO_EXEC_NE = 'Exec NE Emitido, Liquidado e Pago'
    TIPO_RAP = 'RAP PROC N PROC INSCRITOS'
    TIPO_GRU = 'ARRECADAÇÃO POR GRU'
    TIPO_NOTAS_DOTACAO = 'Notas de Dotação'
    TIPO_CHOICES = (
        (TIPO_MOV_CREDITO, TIPO_MOV_CREDITO),
        (TIPO_EXEC_NE, TIPO_EXEC_NE),
        (TIPO_RAP, TIPO_RAP),
        (TIPO_GRU, TIPO_GRU),
        (TIPO_NOTAS_DOTACAO, TIPO_NOTAS_DOTACAO),
    )
    historico = models.ForeignKeyPlus(HistoricoImportacao)
    data_email = models.DateTimeFieldPlus('Data do Email')
    assunto_email = models.CharFieldPlus('Assunto do E-mail')
    tipo = models.CharFieldPlus('Tipo', choices=TIPO_CHOICES)
    qtd = models.IntegerFieldPlus('Quantidade importadas', default=0)

    class Meta:
        verbose_name = 'Importação'
        verbose_name_plural = 'Importações'


class NotaCredito(models.ModelPlus):
    numero = models.CharField('Número', max_length=23, unique=True)
    conta_contabil = models.ForeignKeyPlus(ContaContabil, verbose_name='Conta Contábil', null=True)
    data_emissao = models.DateFieldPlus('Data de Emissão')
    observacao = models.TextField(verbose_name='Observação')
    unidade_orcamentaria = models.ForeignKeyPlus(
        ClassificacaoInstitucional, related_name='unidade_orcamentaria_ci', verbose_name='Unidade Orçamentaria'
    )
    emitente_ci = models.ForeignKeyPlus(ClassificacaoInstitucional, related_name='nc_gerencial_emitente_ci', verbose_name='Gestão Emitente')
    emitente_ug = models.ForeignKeyPlus(UnidadeGestora, related_name='nc_gerencial_emitente_ug', verbose_name='UG Emitente')
    favorecido_ug = models.ForeignKeyPlus(UnidadeGestora, related_name='nc_gerencial_favorecido_ug', verbose_name='UG Favorecida')

    class History:
        disabled = True

    class Meta:
        verbose_name = 'Nota de Crédito'
        verbose_name_plural = 'Notas de Crédito'

    def __str__(self):
        return self.numero

    def get_valor(self):
        return self.itens.aggregate(total=Sum('valor')).get('total')


class NotaCreditoItem(models.ModelPlus):
    nota_credito = models.ForeignKeyPlus(NotaCredito, related_name='itens')
    esfera_orcamentaria = models.ForeignKeyPlus(EsferaOrcamentaria)
    acao_governo = models.ForeignKeyPlus(AcaoGoverno)
    responsavel_ug = models.ForeignKeyPlus(UnidadeGestora)
    ptres = models.ForeignKeyPlus(ProgramaTrabalhoResumido)
    plano_interno = models.ForeignKeyPlus(PlanoInterno)
    fonte_recurso = models.ForeignKeyPlus(FonteRecurso)
    subitem = models.ForeignKeyPlus(SubElementoNaturezaDespesa)
    valor = models.DecimalFieldPlus(default=0)

    naturesa_despesa_original = models.CharFieldPlus(max_length=6)
    grupo_despesa_original = models.CharFieldPlus(max_length=1)

    class History:
        disabled = True

    class Meta:
        verbose_name = 'Item da Nota de Crédito'
        verbose_name_plural = 'Itens da Nota de Crédito'

    def __str__(self):
        return f'Item da NC {self.nota_credito.numero}'


class DocumentoBase(models.ModelPlus):
    # https://portaldatransparencia.gov.br/pagina-interna/605515-dicionario-de-dados-pagamento
    TIPO_NE = 'NE'
    TIPO_RO = 'RO'
    TIPO_NS = 'NS'
    TIPO_OB = 'OB'
    TIPO_DF = 'DF'
    TIPO_DR = 'DR'
    TIPO_GP = 'GP'
    TIPO_GR = 'GR'
    TIPO_GF = 'GF'
    TIPO_NL = 'NL'
    TIPO_CHOICES = (
        (TIPO_NE, 'Nota de Empenho'),
        (TIPO_RO, 'Registro Orçamentário'),
        (TIPO_NS, 'Nota de Sistema'),
        (TIPO_OB, 'Ordem Bancária'),
        (TIPO_DF, 'Documento de Arrecadação da Receita Federal'),
        (TIPO_DR, 'Documento de Arrecadação Municipal/Estadual'),
        (TIPO_GP, 'Guia de Recolhimento da Previdência Social'),
        (TIPO_GR, 'Guia de recolhimento da União'),
        (TIPO_GF, 'Guia FGTS e Informações Previdenciárias'),
        (TIPO_NL, 'Nota de Lançamento'),
    )

    numero = models.CharFieldPlus('Número', max_length=23, unique=True)
    tipo = models.CharFieldPlus('Tipo', max_length=2, choices=TIPO_CHOICES)
    data_emissao = models.DateFieldPlus(verbose_name='Data de Emissão')
    unidade_orcamentaria = models.ForeignKeyPlus(ClassificacaoInstitucional, verbose_name='Unidade Orçamentaria')
    observacao = models.TextField(verbose_name='Observação')
    favorecido_codigo = models.CharFieldPlus(max_length=14)
    favorecido_nome = models.CharFieldPlus()
    acao_governo = models.ForeignKeyPlus(AcaoGoverno)
    ptres = models.ForeignKeyPlus(ProgramaTrabalhoResumido, verbose_name='PTRES')
    plano_interno = models.ForeignKeyPlus(PlanoInterno)
    fonte_recurso = models.ForeignKeyPlus(FonteRecurso, verbose_name='Fonte de recurso')
    esfera_orcamentaria = models.ForeignKeyPlus(EsferaOrcamentaria, verbose_name='Esfera orçamentária')
    emitente_ug = models.ForeignKeyPlus(UnidadeGestora, verbose_name='UG Emitente', related_name='%(app_label)s_%(class)s_emitente_ug')
    responsavel_ug = models.ForeignKeyPlus(UnidadeGestora, verbose_name='UG Responsável', related_name='%(app_label)s_%(class)s_responsavel_ug')

    acao_governo_original = models.CharFieldPlus(max_length=4)
    fonte_recurso_original = models.CharFieldPlus(max_length=10)
    naturesa_despesa_original = models.CharFieldPlus(max_length=6)
    grupo_despesa_original = models.CharFieldPlus(max_length=2)

    class History:
        disabled = False

    class Meta:
        abstract = True


class DocumentoItemBase(models.ModelPlus):
    subitem = models.ForeignKeyPlus(SubElementoNaturezaDespesa)
    valor = models.DecimalFieldPlus(default=0)
    subitem_original = models.CharFieldPlus(max_length=2)

    class History:
        disabled = True

    class Meta:
        abstract = True


class DocumentoEmpenho(DocumentoBase):
    documento_empenho_inicial = models.ForeignKeyPlus('DocumentoEmpenho', null=True, blank=True, related_name='documentos_secundarios')

    class History:
        disabled = True

    class Meta:
        verbose_name = 'Documento de Empenho'
        verbose_name_plural = 'Documentos de Empenho'
        ordering = ['numero']

    def get_valor(self):
        valor = Variavel.get_valor(self.itens.aggregate(Sum('valor')))
        for ne in self.documentos_secundarios.all():
            valor += ne.get_valor()
        return valor

    def get_valor_liquidado(self):
        documento_liquidacao_itens = DocumentoLiquidacaoItem.objects.filter(documento_empenho_inicial=self)
        nss = documento_liquidacao_itens.aggregate(Sum('valor'))
        return Variavel.get_valor(nss)

    def get_valor_pago(self):
        documento_pagamento_itens = DocumentoPagamentoItem.objects.filter(documento_empenho_inicial=self)
        nss = documento_pagamento_itens.aggregate(Sum('valor'))
        return Variavel.get_valor(nss)

    def get_valor_rap(self):
        valor = Decimal(0)
        raps = RAP.objects.filter(numero=self.numero)
        for rap in raps:
            valor += rap.get_valor()

        return valor

    def get_saldo_restante(self):
        return self.get_valor() - self.get_valor_liquidado() - self.get_valor_rap()

    def get_ext_combo_template(self):
        template = f"""
            <h3>{self.numero}</h3>
            <p>Valor: {format_money(self.get_valor())}</p>
            <p>Valor Pago: {format_money(self.get_valor_pago())}</p>
            <p>Valor Liquidado: {format_money(self.get_valor_liquidado())}</p>
            <p>Valor RAP: {format_money(self.get_valor_rap())}</p>
            <p>Saldo Restante: {format_money(self.get_saldo_restante())}</p>
        """
        return template


class DocumentoEmpenhoItem(DocumentoItemBase):
    documento_empenho = models.ForeignKeyPlus('DocumentoEmpenho', related_name='itens')
    evento = models.ForeignKeyPlus(EventoNotaEmpenho, null=True)

    class History:
        disabled = True

    class Meta:
        verbose_name = 'Item do Documento de Empenho'
        verbose_name_plural = 'Itens do Documento de Empenho'
        unique_together = ['documento_empenho', 'subitem', 'evento', 'valor']


class DocumentoLiquidacao(DocumentoBase):
    class History:
        disabled = True

    class Meta:
        verbose_name = 'Documento de Liquidação'
        verbose_name_plural = 'Documentos de Liquidação'

    def get_valor(self):
        return Variavel.get_valor(self.itens.aggregate(Sum('valor')))


class DocumentoLiquidacaoItem(DocumentoItemBase):
    documento_liquidacao = models.ForeignKeyPlus('DocumentoLiquidacao', related_name='itens')
    documento_empenho_inicial = models.ForeignKeyPlus('DocumentoEmpenho')
    evento = models.ForeignKeyPlus(EventoNotaEmpenho, null=True)

    class History:
        disabled = True

    class Meta:
        verbose_name = 'Item do Documento de Liquidação'
        verbose_name_plural = 'Itens do Documento de Liquidação'
        unique_together = ['documento_liquidacao', 'subitem', 'documento_empenho_inicial', 'evento', 'valor']


class DocumentoPagamento(DocumentoBase):
    class History:
        disabled = True

    class Meta:
        verbose_name = 'Documento de Pagamento'
        verbose_name_plural = 'Documentos de Pagamento'

    def get_valor(self):
        return Variavel.get_valor(self.itens.aggregate(Sum('valor')))


class DocumentoPagamentoItem(DocumentoItemBase):
    documento_pagamento = models.ForeignKeyPlus('DocumentoPagamento', related_name='itens')
    documento_empenho_inicial = models.ForeignKeyPlus('DocumentoEmpenho')

    class History:
        disabled = True

    class Meta:
        verbose_name = 'Item do Documento de Pagamento'
        verbose_name_plural = 'Itens do Documento de Pagamento'
        unique_together = ['documento_pagamento', 'subitem', 'documento_empenho_inicial']


class RAP(models.ModelPlus):
    numero = models.CharFieldPlus('Número', max_length=23)
    ano = models.IntegerField()
    unidade_orcamentaria = models.ForeignKeyPlus(
        ClassificacaoInstitucional, related_name='unidade_orcamentaria_rap', verbose_name='Unidade Orçamentaria'
    )
    acao_governo = models.ForeignKeyPlus(AcaoGoverno, related_name='acao_governo_rap')
    ptres = models.ForeignKeyPlus(ProgramaTrabalhoResumido, related_name='ptres_rap', verbose_name='PTRES')
    plano_interno = models.ForeignKeyPlus(PlanoInterno, related_name='plano_interno_rap')
    fonte_recurso = models.ForeignKeyPlus(FonteRecurso, related_name='emitente_ug_rap', verbose_name='Fonte de recurso')
    emitente_ug = models.ForeignKeyPlus(UnidadeGestora, related_name='ug_emitente_rap', verbose_name='UG Emitente')
    responsavel_ug = models.ForeignKeyPlus(UnidadeGestora, related_name='ug_responsavel_rap', verbose_name='UG Responsável')

    acao_governo_original = models.CharFieldPlus(max_length=4)
    fonte_recurso_original = models.CharFieldPlus(max_length=10)
    naturesa_despesa_original = models.CharFieldPlus(max_length=6)
    grupo_despesa_original = models.CharFieldPlus(max_length=1)

    class History:
        disabled = True

    class Meta:
        verbose_name = 'RAP'
        verbose_name_plural = 'RAPs'
        ordering = ['numero', 'ano']
        unique_together = ['numero', 'ano']

    def get_valor(self):
        return Variavel.get_valor(self.itens.aggregate(Sum('valor_nao_proc_liquidado')))


class RAPItem(models.ModelPlus):
    rap = models.ForeignKeyPlus('RAP', related_name='itens')
    subitem = models.ForeignKeyPlus(SubElementoNaturezaDespesa, related_name='subitem_rap')
    valor_proc_inscrito = models.DecimalFieldPlus(default=0)
    valor_proc_reinscrito = models.DecimalFieldPlus(default=0)
    valor_proc_cancelado = models.DecimalFieldPlus(default=0)
    valor_proc_pago = models.DecimalFieldPlus(default=0)
    valor_nao_proc_inscrito = models.DecimalFieldPlus(default=0)
    valor_nao_proc_reinscrito = models.DecimalFieldPlus(default=0)
    valor_nao_proc_cancelado = models.DecimalFieldPlus(default=0)
    valor_nao_proc_liquidado = models.DecimalFieldPlus(default=0)
    valor_nao_proc_pago = models.DecimalFieldPlus(default=0)

    subitem_original = models.CharFieldPlus(max_length=2)

    class History:
        disabled = True

    class Meta:
        verbose_name = 'Item do RAP'
        verbose_name_plural = 'Itens do RAP'
        ordering = ['rap', 'subitem']

    def __str__(self):
        return f'Item do RAP {self.rap.numero}'


class GRU(models.ModelPlus):
    codigo = models.CharFieldPlus('Código', max_length=10)
    nome = models.CharFieldPlus('Nome')

    class History:
        disabled = True

    class Meta:
        verbose_name = 'GRU'
        verbose_name_plural = 'GRUs'
        ordering = ['codigo']

    def __str__(self):
        return f'{self.codigo} - {self.nome}'


class ReceitaGRU(models.ModelPlus):
    ano = models.IntegerField()
    gru = models.ForeignKeyPlus(GRU)
    emitente_ug = models.ForeignKeyPlus(UnidadeGestora, related_name='ug_emitente_gru', verbose_name='UG Emitente')
    valor = models.DecimalFieldPlus(default=0)

    class History:
        disabled = True

    class Meta:
        verbose_name = 'Receita Arrecadada por GRU'
        verbose_name_plural = 'Receitas Arrecadadas por GRU'
        ordering = ['ano', 'gru', 'emitente_ug']

    def __str__(self):
        return f'{self.gru} - {self.emitente_ug} - {self.valor}'

    def get_valor(self):
        return self.valor


class TipoDocumentoEmpenhoEspecifico(models.ModelPlus):
    descricao = models.CharField('Descrição', max_length=50)
    aplicar_calculo = models.BooleanField('Aplicar a regra sobre o cálculo das variáveis financeiras', default=False)
    observacao = models.TextField(verbose_name='Observação', blank=True)

    class Meta:
        verbose_name = 'Tipo de Documento de Empenho Específico'
        verbose_name_plural = 'Tipos de Documentos de Empenho Específicos'


class DocumentoEmpenhoEspecifico(models.ModelPlus):
    documento_empenho = models.ForeignKeyPlus('DocumentoEmpenho')
    tipo = models.ForeignKeyPlus(TipoDocumentoEmpenhoEspecifico)
    observacao = models.TextField(verbose_name='Observação', blank=True)

    class Meta:
        verbose_name = 'Documento de Empenho Específico'
        verbose_name_plural = 'Documentos de Empenho Específicos'

    def __str__(self):
        return f'Documento de Empenho Específico {self.documento_empenho}/{self.tipo}: {self.observacao}'

    @classmethod
    def get_documento_folha_pagamento(cls, ano):
        """
        Retorna os documentos que estão incluídos na folha de pagamento e não tem como identificar com base nos atributos deles
        """
        documentos_especificos = cls.objects.filter(documento_empenho__data_emissao__year=ano, tipo__aplicar_calculo=True)
        return documentos_especificos

    @classmethod
    def get_documento_folha_pagamento_ids(cls, ano):
        return cls.get_documento_folha_pagamento(ano).values_list('documento_empenho', flat=True)


class Variavel:
    @classmethod
    def get_valor_nss(cls, nes):
        documento_liquidacao_itens = DocumentoLiquidacaoItem.objects.filter(documento_empenho_inicial__in=nes)
        nss = documento_liquidacao_itens.aggregate(Sum('valor'))
        return cls.get_valor(nss)

    @classmethod
    def get_valor_raps(cls, raps):
        raps = raps.aggregate(Sum('itens__valor_nao_proc_liquidado'))
        return cls.get_valor(raps)

    @classmethod
    def get_valor(cls, qs):
        return next(iter(qs.values())) or Decimal(0)

    @classmethod
    def get_valor_folha_pagamento_qs(cls, campus, ano):
        situacoes_estagiario = Situacao.objects.filter(codigo__in=Situacao.situacoes_siape_estagiarios())
        contracheques = ContraCheque.objects.ativos().fita_espelho().filter(ano__ano=ano, bruto__isnull=False).exclude(bruto=0)
        folha_pagamento = contracheques.filter(servidor_setor_lotacao__uo__equivalente__pk=campus.id)
        # Colocar na RE todas as rubricas que não aparecem nos campi exceto estagiários exemplo: aposentados, Exerc. Descent carrei
        if campus.tipo_id == UnidadeOrganizacional.TIPO_REITORIA:
            folha_pagamento = folha_pagamento | contracheques.filter(servidor_setor_lotacao__uo__equivalente__isnull=True).exclude(
                servidor_situacao__in=situacoes_estagiario
            )

        # Colocar estagiários nos campi
        contracheques_estagiarios = contracheques.filter(servidor_situacao__in=situacoes_estagiario, servidor__setor__uo__pk=campus.id)

        folha_pagamento = folha_pagamento | contracheques_estagiarios
        return folha_pagamento

    @classmethod
    def get_valor_folha_pagamento(cls, campus, ano):
        folha_pagamento = cls.get_valor_folha_pagamento_qs(campus, ano)
        return cls.get_valor(folha_pagamento.aggregate(Sum('bruto')))

    @classmethod
    def get_valor_folha_pagamento_ativo(cls, campus, ano):
        situacoes_inativas = [Situacao.APOSENTADOS, 15]  # 15 = 'INSTITUIDOR PENSAO'
        folha_pagamento = cls.get_valor_folha_pagamento_qs(campus, ano)
        folha_pagamento = folha_pagamento.exclude(servidor_situacao__codigo__in=situacoes_inativas)
        return cls.get_valor(folha_pagamento.aggregate(Sum('bruto')))

    @classmethod
    def get_valor_gecc(cls, campus, ano):
        rubricas = ContraChequeRubrica.objects.filter(
            contra_cheque__ano__ano=ano,
            rubrica__codigo__in=['83119', '00066', '82885'],
            contra_cheque__servidor_setor_lotacao__uo__equivalente__pk=campus.id,
        )
        return cls.get_valor(rubricas.aggregate(Sum('valor')))

    @classmethod
    def get_valor_estagiarios(cls, campus, ano):
        situacoes_estagiario = Situacao.objects.filter(codigo__in=Situacao.situacoes_siape_estagiarios())
        contracheques_estagiarios = (
            ContraCheque.objects.ativos()
            .fita_espelho()
            .filter(servidor_situacao__in=situacoes_estagiario, servidor__setor__uo__pk=campus.id, ano__ano=ano, bruto__isnull=False)
            .exclude(bruto=0)
        )
        return cls.get_valor(contracheques_estagiarios.aggregate(Sum('bruto')))

    # total de destaques orçamentários executados
    @classmethod
    def get_DEST_EXEC_qs(cls, campus, ano):
        codigos_outros_orgaos = UnidadeGestora.get_outros_orgaos()
        nes = DocumentoEmpenho.objects.filter(
            Q(responsavel_ug__codigo=campus.codigo_ugr) | Q(responsavel_ug__codigo__in=codigos_outros_orgaos, emitente_ug__codigo=campus.codigo_ug),
            data_emissao__year=ano,
        ).exclude(unidade_orcamentaria__codigo='26435')
        raps = RAP.objects.filter(
            Q(responsavel_ug__codigo=campus.codigo_ugr) | Q(responsavel_ug__codigo__in=codigos_outros_orgaos, emitente_ug__codigo=campus.codigo_ug),
            ano=ano,
        ).exclude(unidade_orcamentaria__codigo='26435')
        return nes, raps

    @classmethod
    def get_DEST_EXEC(cls, campus, ano):
        nes, raps = cls.get_DEST_EXEC_qs(campus, ano)
        return cls.get_valor_nss(nes) + cls.get_valor_raps(raps)

    # total de recursos LOA executados (excluido pessoal e benefícios)
    @classmethod
    def get_LOA_EXEC_qs(cls, campus, ano):
        codigos_outros_orgaos = UnidadeGestora.get_outros_orgaos()
        nes = (
            DocumentoEmpenho.objects.filter(
                Q(responsavel_ug__codigo=campus.codigo_ugr)
                | Q(responsavel_ug__codigo__in=codigos_outros_orgaos, emitente_ug__codigo=campus.codigo_ug),
                unidade_orcamentaria__codigo='26435',
                data_emissao__year=ano,
            )
            .exclude(acao_governo_original__in=['2004', '212B', '216H'])
            .exclude(grupo_despesa_original='1')
        )
        nes = nes.exclude(id__in=DocumentoEmpenhoEspecifico.get_documento_folha_pagamento_ids(ano))
        raps = (
            RAP.objects.filter(
                Q(responsavel_ug__codigo=campus.codigo_ugr)
                | Q(responsavel_ug__codigo__in=codigos_outros_orgaos, emitente_ug__codigo=campus.codigo_ug),
                unidade_orcamentaria__codigo='26435',
                ano=ano,
            )
            .exclude(acao_governo_original__in=['2004', '212B', '216H'])
            .exclude(grupo_despesa_original='1')
        )
        ncs = NotaCredito.objects.filter(conta_contabil__codigo='622220100', data_emissao__year=ano, itens__responsavel_ug__codigo=campus.codigo_ugr)
        geccs = ['GECC', cls.get_valor_gecc(campus, ano)]
        estariarios = ['Estagiários', cls.get_valor_estagiarios(campus, ano)]
        return nes, raps, ncs, geccs, estariarios

    @classmethod
    def get_LOA_EXEC(cls, campus, ano):
        nes, raps, ncs, _geccs, _estariarios = cls.get_LOA_EXEC_qs(campus, ano)
        ncs = ncs.aggregate(Sum('itens__valor'))
        return (
            cls.get_valor_nss(nes)
            + cls.get_valor_raps(raps)
            + cls.get_valor(ncs)
            + cls.get_valor_gecc(campus, ano)
            + cls.get_valor_estagiarios(campus, ano)
        )

    # total de recursos privados captados
    @classmethod
    def get_RECCAPT_qs(cls, campus, ano):
        return ReceitaGRU.objects.filter(
            emitente_ug__codigo=campus.codigo_ug,
            gru__codigo__in=['28812', '28804', '28802', '28838', '28867', '28965', '28976', '28868', '28811', '28849'],
            ano=ano,
        )

    @classmethod
    def get_RECCAPT(cls, campus, ano):
        gru = cls.get_RECCAPT_qs(campus, ano)
        return cls.get_valor(gru.aggregate(Sum('valor')))

    # total de recursos LOA para funcionamento (20RL)
    @classmethod
    def get_20RL_LOA_qs(cls, campus, ano):
        codigos_outros_orgaos = UnidadeGestora.get_outros_orgaos()
        nes = (
            DocumentoEmpenho.objects.filter(
                Q(responsavel_ug__codigo=campus.codigo_ugr)
                | Q(responsavel_ug__codigo__in=codigos_outros_orgaos, emitente_ug__codigo=campus.codigo_ug),
                unidade_orcamentaria__codigo='26435',
                data_emissao__year=ano,
            )
            .filter(acao_governo_original='20RL')
            .exclude(fonte_recurso_original__in=['8250026435', '8250000000'])
        )
        nes = nes.exclude(id__in=DocumentoEmpenhoEspecifico.get_documento_folha_pagamento_ids(ano))
        raps = (
            RAP.objects.filter(
                Q(responsavel_ug__codigo=campus.codigo_ugr)
                | Q(responsavel_ug__codigo__in=codigos_outros_orgaos, emitente_ug__codigo=campus.codigo_ug),
                unidade_orcamentaria__codigo='26435',
                ano=ano,
            )
            .filter(acao_governo_original='20RL')
            .exclude(fonte_recurso_original__in=['8250026435', '8250000000'])
        )
        ncs = NotaCredito.objects.filter(
            conta_contabil__codigo='622220100',
            data_emissao__year=ano,
            itens__responsavel_ug__codigo=campus.codigo_ugr,
            itens__acao_governo__codigo='20RL',
        ).exclude(itens__fonte_recurso__codigo__in=['8250026435', '8250000000'])
        geccs = ['GECC', cls.get_valor_gecc(campus, ano)]
        estariarios = ['Estagiários', cls.get_valor_estagiarios(campus, ano)]
        return nes, raps, ncs, geccs, estariarios

    @classmethod
    def get_20RL_LOA(cls, campus, ano):
        nes, raps, ncs, _geccs, _estariarios = cls.get_20RL_LOA_qs(campus, ano)
        ncs = ncs.aggregate(Sum('itens__valor'))
        return (
            cls.get_valor_nss(nes)
            + cls.get_valor_raps(raps)
            + cls.get_valor(ncs)
            + cls.get_valor_gecc(campus, ano)
            + cls.get_valor_estagiarios(campus, ano)
        )

    # Total de gastos com contratos continuado
    @classmethod
    def get_GCC_qs(cls, campus, ano):
        codigos_outros_orgaos = UnidadeGestora.get_outros_orgaos()
        nes = (
            DocumentoEmpenho.objects.filter(
                Q(responsavel_ug__codigo=campus.codigo_ugr)
                | Q(responsavel_ug__codigo__in=codigos_outros_orgaos, emitente_ug__codigo=campus.codigo_ug),
                unidade_orcamentaria__codigo='26435',
                data_emissao__year=ano,
            )
            .exclude(acao_governo_original__in=['0181', '09HB', '2004', '20TP', '212B', '216H'])
            .exclude(fonte_recurso_original__in=['8250026435', '8250000000'])
        )
        nes = (
            nes.filter(
                naturesa_despesa_original='339030',  # E(Col “S” Natureza Despesa = 339030;Col “U” Subitem 01, 39)
                itens__subitem_original__in=['1', '39'],
            )
            | nes.filter(
                naturesa_despesa_original='339032',  # E(Col “S” Natureza Despesa = 339032;Col “U” Subitem 20)
                itens__subitem_original__in=['20'],
            )
            | nes.filter(
                naturesa_despesa_original='339033',  # E(Col “S” Natureza Despesa = 339033;Col “U” Subitem 01)
                itens__subitem_original__in=['1', '2'],
            )
            | nes.filter(
                naturesa_despesa_original='339037',  # E(Col “S” Natureza Despesa = 339037;Col “U” Subitem 01, 02, 03, 04, 05, 06)
                itens__subitem_original__in=['1', '2', '3', '4', '5', '6'],
            )
            | nes.filter(
                naturesa_despesa_original='339039',  # E(Col “S” Natureza Despesa = 339039;Col “U” Subitem 12, 17, 19, 41, 43, 44, 47 ,58, 65, 69, 75, 78)
                itens__subitem_original__in=['12', '17', '19', '41', '43', '44', '47', '58', '65', '69', '75', '78'],
            )
            | nes.filter(
                naturesa_despesa_original='339040',  # E(Col “S” Natureza Despesa = 339040;Col “U” Subitem 04, 13, 16)
                itens__subitem_original__in=['4', '13', '16'],
            )
        )

        raps = (
            RAP.objects.filter(
                Q(responsavel_ug__codigo=campus.codigo_ugr)
                | Q(responsavel_ug__codigo__in=codigos_outros_orgaos, emitente_ug__codigo=campus.codigo_ug),
                unidade_orcamentaria__codigo='26435',
                ano=ano,
            )
            .exclude(acao_governo_original__in=['0181', '09HB', '2004', '20TP', '212B', '216H'])
            .exclude(fonte_recurso_original__in=['8250026435', '8250000000'])
        )
        raps = (
            raps.filter(
                naturesa_despesa_original='339030',  # E(Col “O” Natureza Despesa = 339030;Col “Q” Subitem 01, 39)
                itens__subitem_original__in=['1', '39'],
            )
            | raps.filter(
                naturesa_despesa_original='339032',  # E(Col “O” Natureza Despesa = 339032;Col “Q” Subitem 20)
                itens__subitem_original__in=['20'],
            )
            | raps.filter(
                naturesa_despesa_original='339033',  # E(Col “O” Natureza Despesa = 339033;Col “Q” Subitem 01)
                itens__subitem_original__in=['1', '2'],
            )
            | raps.filter(
                naturesa_despesa_original='339037',  # E(Col “O” Natureza Despesa = 339037;Col “Q” Subitem 01, 02, 03, 04, 05, 06)
                itens__subitem_original__in=['1', '2', '3', '4', '5', '6'],
            )
            | raps.filter(
                naturesa_despesa_original='339039',  # E(Col “O” Natureza Despesa = 339039;Col “Q” Subitem 12, 17, 19, 41, 43, 44, 47 ,58, 65, 69, 75, 78)
                itens__subitem_original__in=['12', '17', '19', '41', '43', '44', '47', '58', '65', '69', '75', '78'],
            )
            | raps.filter(
                naturesa_despesa_original='339040',  # E(Col “O” Natureza Despesa = 339040;Col “Q” Subitem 04, 13, 16)
                itens__subitem_original__in=['4', '13', '16'],
            )
        )
        return nes, raps

    @classmethod
    def get_GCC(cls, campus, ano):
        nes, raps = cls.get_GCC_qs(campus, ano)
        return cls.get_valor_nss(nes) + cls.get_valor_raps(raps)

    # Total de gastos (LOA)
    @classmethod
    def get_GTO_LOA_qs(cls, campus, ano):
        codigos_outros_orgaos = UnidadeGestora.get_outros_orgaos()
        nes = (
            DocumentoEmpenho.objects.filter(
                Q(responsavel_ug__codigo=campus.codigo_ugr)
                | Q(responsavel_ug__codigo__in=codigos_outros_orgaos, emitente_ug__codigo=campus.codigo_ug),
                unidade_orcamentaria__codigo='26435',
                data_emissao__year=ano,
            )
            .exclude(acao_governo_original__in=['0181', '09HB', '2004', '20TP', '212B', '216H', '2994'])  # adicionado o 2994
            .exclude(fonte_recurso_original__in=['8250026435', '8250000000'])
        )
        nes = nes.exclude(id__in=DocumentoEmpenhoEspecifico.get_documento_folha_pagamento_ids(ano))
        raps = (
            RAP.objects.filter(
                Q(responsavel_ug__codigo=campus.codigo_ugr)
                | Q(responsavel_ug__codigo__in=codigos_outros_orgaos, emitente_ug__codigo=campus.codigo_ug),
                unidade_orcamentaria__codigo='26435',
                ano=ano,
            )
            .exclude(acao_governo_original__in=['0181', '09HB', '2004', '20TP', '212B', '216H', '2994'])  # adicionado o 2994
            .exclude(fonte_recurso_original__in=['8250026435', '8250000000'])
        )
        ncs = (
            NotaCredito.objects.filter(conta_contabil__codigo='622220100', data_emissao__year=ano, itens__responsavel_ug__codigo=campus.codigo_ugr)
            .exclude(itens__acao_governo__codigo='2994')
            .exclude(itens__fonte_recurso__codigo__in=['8250026435', '8250000000'])
        )
        geccs = ['GECC', cls.get_valor_gecc(campus, ano)]
        estariarios = ['Estagiários', cls.get_valor_estagiarios(campus, ano)]
        return nes, raps, ncs, geccs, estariarios

    @classmethod
    def get_GTO_LOA(cls, campus, ano):
        nes, raps, ncs, _geccs, _estariarios = cls.get_GTO_LOA_qs(campus, ano)
        ncs = ncs.aggregate(Sum('itens__valor'))
        return (
            cls.get_valor_nss(nes)
            + cls.get_valor_raps(raps)
            + cls.get_valor(ncs)
            + cls.get_valor_gecc(campus, ano)
            + cls.get_valor_estagiarios(campus, ano)
        )

    # Gastos com servidores
    @classmethod
    def get_fGPE_qs(cls, campus, ano):
        codigos_outros_orgaos = UnidadeGestora.get_outros_orgaos()
        if campus.tipo_id == UnidadeOrganizacional.TIPO_REITORIA:
            nes = DocumentoEmpenho.objects.filter(
                Q(responsavel_ug__codigo=campus.codigo_ugr)
                | Q(responsavel_ug__codigo__in=codigos_outros_orgaos, emitente_ug__codigo=campus.codigo_ug),
                data_emissao__year=ano,
                acao_governo_original='09HB',
            )
            return nes
        return

    @classmethod
    def get_fGPE(cls, campus, ano):
        if campus.tipo_id == UnidadeOrganizacional.TIPO_REITORIA:
            nes = cls.get_fGPE_qs(campus, ano)
            return cls.get_valor_folha_pagamento(campus, ano) + cls.get_valor_nss(nes)
        return cls.get_valor_folha_pagamento(campus, ano)

    # Gastos totais
    @classmethod
    def get_fGTO_qs(cls, campus, ano):
        codigos_outros_orgaos = UnidadeGestora.get_outros_orgaos()
        nes = DocumentoEmpenho.objects.filter(
            Q(responsavel_ug__codigo=campus.codigo_ugr) | Q(responsavel_ug__codigo__in=codigos_outros_orgaos, emitente_ug__codigo=campus.codigo_ug),
            data_emissao__year=ano,
        )
        if campus.tipo_id == UnidadeOrganizacional.TIPO_REITORIA:
            nes = nes.exclude(acao_governo_original__in=['0181', '2004', '20TP', '212B', '216H'])
        else:
            nes = nes.exclude(acao_governo_original__in=['0181', '2004', '20TP', '212B', '216H', '09HB'])
        nes = nes.exclude(id__in=DocumentoEmpenhoEspecifico.get_documento_folha_pagamento_ids(ano))
        raps = RAP.objects.filter(
            Q(responsavel_ug__codigo=campus.codigo_ugr) | Q(responsavel_ug__codigo__in=codigos_outros_orgaos, emitente_ug__codigo=campus.codigo_ug),
            ano=ano,
        ).exclude(acao_governo_original__in=['0181', '09HB', '2004', '20TP', '212B', '216H'])
        ncs = NotaCredito.objects.filter(conta_contabil__codigo='622220100', data_emissao__year=ano, itens__responsavel_ug__codigo=campus.codigo_ugr)
        geccs = ['GECC', cls.get_valor_gecc(campus, ano)]
        estariarios = ['Estagiários', cls.get_valor_estagiarios(campus, ano)]
        return nes, raps, ncs, geccs, estariarios

    @classmethod
    def get_fGTO(cls, campus, ano):
        nes, raps, ncs, _geccs, _estariarios = cls.get_fGTO_qs(campus, ano)
        ncs = ncs.aggregate(Sum('itens__valor'))
        return (
            cls.get_valor_nss(nes)
            + cls.get_valor_raps(raps)
            + cls.get_valor(ncs)
            + cls.get_valor_folha_pagamento(campus, ano)
            + cls.get_valor_gecc(campus, ano)
        )

    # Gastos com outros custeios
    @classmethod
    def get_fGOC_qs(cls, campus, ano):
        codigos_outros_orgaos = UnidadeGestora.get_outros_orgaos()
        nes = (
            DocumentoEmpenho.objects.filter(
                Q(responsavel_ug__codigo=campus.codigo_ugr)
                | Q(responsavel_ug__codigo__in=codigos_outros_orgaos, emitente_ug__codigo=campus.codigo_ug),
                data_emissao__year=ano,
            )
            .exclude(acao_governo_original__in=['2004', '212B', '216H'])
            .exclude(grupo_despesa_original__in=['1', '4'])
        )
        nes = nes.exclude(id__in=DocumentoEmpenhoEspecifico.get_documento_folha_pagamento_ids(ano))
        raps = (
            RAP.objects.filter(
                Q(responsavel_ug__codigo=campus.codigo_ugr)
                | Q(responsavel_ug__codigo__in=codigos_outros_orgaos, emitente_ug__codigo=campus.codigo_ug),
                ano=ano,
            )
            .exclude(acao_governo_original__in=['2004', '212B', '216H'])
            .exclude(grupo_despesa_original__in=['1', '4'])
        )
        ncs = NotaCredito.objects.filter(
            conta_contabil__codigo='622220100',
            data_emissao__year=ano,
            itens__responsavel_ug__codigo=campus.codigo_ugr,
            itens__grupo_despesa_original=3,
        )
        geccs = ['GECC', cls.get_valor_gecc(campus, ano)]
        estariarios = ['Estagiários', cls.get_valor_estagiarios(campus, ano)]
        return nes, raps, ncs, geccs, estariarios

    @classmethod
    def get_fGOC(cls, campus, ano):
        nes, raps, ncs, _geccs, _estariarios = cls.get_fGOC_qs(campus, ano)
        ncs = ncs.aggregate(Sum('itens__valor'))
        return (
            cls.get_valor_nss(nes)
            + cls.get_valor_raps(raps)
            + cls.get_valor(ncs)
            + cls.get_valor_gecc(campus, ano)
            + cls.get_valor_estagiarios(campus, ano)
        )

    # Gastos com investimentos
    @classmethod
    def get_fGCI_qs(cls, campus, ano):
        codigos_outros_orgaos = UnidadeGestora.get_outros_orgaos()
        nes = DocumentoEmpenho.objects.filter(
            Q(responsavel_ug__codigo=campus.codigo_ugr) | Q(responsavel_ug__codigo__in=codigos_outros_orgaos, emitente_ug__codigo=campus.codigo_ug),
            grupo_despesa_original__in='4',
            data_emissao__year=ano,
        )
        raps = RAP.objects.filter(
            Q(responsavel_ug__codigo=campus.codigo_ugr) | Q(responsavel_ug__codigo__in=codigos_outros_orgaos, emitente_ug__codigo=campus.codigo_ug),
            grupo_despesa_original='4',
            ano=ano,
        )
        ncs = NotaCredito.objects.filter(
            conta_contabil__codigo='622220100',
            data_emissao__year=ano,
            itens__responsavel_ug__codigo=campus.codigo_ugr,
            itens__grupo_despesa_original=4,
        )
        return nes, raps, ncs

    @classmethod
    def get_fGCI(cls, campus, ano):
        nes, raps, ncs = cls.get_fGCI_qs(campus, ano)
        ncs = ncs.aggregate(Sum('itens__valor'))
        return cls.get_valor_nss(nes) + cls.get_valor_raps(raps) + cls.get_valor(ncs)

    # Total de gastos correntes
    @classmethod
    def get_fGCO_qs(cls, campus, ano):
        codigos_outros_orgaos = UnidadeGestora.get_outros_orgaos()
        nes = DocumentoEmpenho.objects.filter(
            Q(responsavel_ug__codigo=campus.codigo_ugr) | Q(responsavel_ug__codigo__in=codigos_outros_orgaos, emitente_ug__codigo=campus.codigo_ug),
            data_emissao__year=ano,
        ).exclude(grupo_despesa_original='4')
        if campus.tipo_id == UnidadeOrganizacional.TIPO_REITORIA:
            nes = nes.exclude(acao_governo_original__in=['0181', '2004', '20TP', '212B', '216H'])
        else:
            nes = nes.exclude(acao_governo_original__in=['0181', '09HB', '2004', '20TP', '212B', '216H'])
        nes = nes.exclude(id__in=DocumentoEmpenhoEspecifico.get_documento_folha_pagamento_ids(ano))

        raps = RAP.objects.filter(
            Q(responsavel_ug__codigo=campus.codigo_ugr) | Q(responsavel_ug__codigo__in=codigos_outros_orgaos, emitente_ug__codigo=campus.codigo_ug),
            ano=ano,
        ).exclude(grupo_despesa_original__in='4')
        if campus.tipo_id == UnidadeOrganizacional.TIPO_REITORIA:
            raps = raps.exclude(acao_governo_original__in=['0181', '2004', '20TP', '212B', '216H'])
        else:
            raps = raps.exclude(acao_governo_original__in=['0181', '09HB', '2004', '20TP', '212B', '216H'])

        ncs = (
            NotaCredito.objects.filter(conta_contabil__codigo='622220100', data_emissao__year=ano)
            .filter(itens__responsavel_ug__codigo=campus.codigo_ugr)
            .exclude(itens__grupo_despesa_original=4)
        )
        geccs = ['GECC', cls.get_valor_gecc(campus, ano)]
        estariarios = ['Estagiários', cls.get_valor_estagiarios(campus, ano)]
        return nes, raps, ncs, geccs, estariarios

    @classmethod
    def get_fGCO(cls, campus, ano):
        nes, raps, ncs, _geccs, _estariarios = cls.get_fGCO_qs(campus, ano)
        ncs = ncs.aggregate(Sum('itens__valor'))
        return (
            cls.get_valor_nss(nes)
            + cls.get_valor_raps(raps)
            + cls.get_valor(ncs)
            + cls.get_valor_folha_pagamento_ativo(campus, ano)
            + cls.get_valor_gecc(campus, ano)
        )

    @classmethod
    def exibir(cls):
        campi = UnidadeOrganizacional.objects.uo().order_by('sigla')
        for campus in campi:
            uo_str = f'{campus.sigla} ({campus.codigo_ugr})'
            print_('')
            print_(f'{uo_str: <16} DEST_EXEC \t {format_money(cls.get_DEST_EXEC(campus)): >15}')
            print_(f'{uo_str: <16} LOA_EXEC  \t {format_money(cls.get_LOA_EXEC(campus)): >15}')
            print_(f'{uo_str: <16} RECCAPT   \t {format_money(cls.get_RECCAPT(campus)): >15}')
            print_(f'{uo_str: <16} 20RL_LOA  \t {format_money(cls.get_20RL_LOA(campus)): >15}')
            print_(f'{uo_str: <16} GCC       \t {format_money(cls.get_GCC(campus)): >15}')
            print_(f'{uo_str: <16} GTO_LOA   \t {format_money(cls.get_GTO_LOA(campus)): >15}')
            print_(f'{uo_str: <16} fGPE      \t {format_money(cls.get_fGPE(campus)): >15}')
            print_(f'{uo_str: <16} fGTO      \t {format_money(cls.get_fGTO(campus)): >15}')
            print_(f'{uo_str: <16} fGOC      \t {format_money(cls.get_fGOC(campus)): >15}')
            print_(f'{uo_str: <16} fGCI      \t {format_money(cls.get_fGCI(campus)): >15}')
            print_(f'{uo_str: <16} fGCO      \t {format_money(cls.get_fGCO(campus)): >15}')


class NotaDotacao(models.ModelPlus):
    numero = models.CharField('Número', max_length=23, unique=True)
    executora_ug = models.ForeignKeyPlus(UnidadeGestora, related_name='notas_dotacao_executora')
    data_emissao = models.DateFieldPlus('Data da Emissão')
    observacao = models.TextField(verbose_name='Observação')
    especie = models.CharFieldPlus(verbose_name='Espécie')
    acao_governo = models.ForeignKeyPlus(AcaoGoverno)
    ptres = models.ForeignKeyPlus(ProgramaTrabalhoResumido)
    grupo_despesa_original = models.CharFieldPlus(max_length=1)
    fonte_recurso = models.ForeignKeyPlus(FonteRecurso)

    class History:
        disabled = True

    class Meta:
        verbose_name = 'Nota de Dotação'
        verbose_name_plural = 'Notas de Dotação'

    def __str__(self):
        return self.numero

    def get_valor(self):
        return self.itens.aggregate(total=Sum('valor')).get('total')


class NotaDotacaoItem(models.ModelPlus):
    nota_dotacao = models.ForeignKeyPlus(NotaDotacao, related_name='itens')
    responsavel_ug = models.ForeignKeyPlus(UnidadeGestora, related_name='notas_dotacao_responsavel')
    detalhamento = models.CharFieldPlus(verbose_name='Detalhamento')
    evento = models.ForeignKeyPlus(EventoNotaDotacao)
    plano_interno = models.ForeignKeyPlus(PlanoInterno)
    valor = models.DecimalFieldPlus(default=0, max_digits=14)
    valor_liquido = models.DecimalFieldPlus(default=0, max_digits=14)

    class History:
        disabled = True

    class Meta:
        verbose_name = 'Item da Nota de Dotação'
        verbose_name_plural = 'Itens da Nota de Dotação'

    def __str__(self):
        return f'Item da ND {self.nota_dotacao.numero}'
