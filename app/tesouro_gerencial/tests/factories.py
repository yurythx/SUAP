"""Factories do tesouro_gerencial: documentos de execução orçamentária, receitas e classificações."""

from datetime import date
from decimal import Decimal

import factory
from factory.django import DjangoModelFactory

from tesouro_gerencial import models


class ClassificacaoInstitucionalFactory(DjangoModelFactory):
    class Meta:
        model = models.ClassificacaoInstitucional
        django_get_or_create = ('codigo',)

    codigo = '99901'
    nome = 'Instituição de Demonstração'


class UnidadeGestoraFactory(DjangoModelFactory):
    class Meta:
        model = models.UnidadeGestora
        django_get_or_create = ('codigo',)

    codigo = '999001'
    nome = 'Unidade de Demonstração'


class AcaoGovernoFactory(DjangoModelFactory):
    class Meta:
        model = models.AcaoGoverno
        django_get_or_create = ('codigo',)

    codigo = '9991'
    nome = 'Manutenção'


class ProgramaTrabalhoResumidoFactory(DjangoModelFactory):
    class Meta:
        model = models.ProgramaTrabalhoResumido
        django_get_or_create = ('codigo',)

    codigo = '999001'


class PlanoInternoFactory(DjangoModelFactory):
    class Meta:
        model = models.PlanoInterno
        django_get_or_create = ('codigo',)

    codigo = 'DOCCT'
    nome = 'Manutenção'


class FonteRecursoFactory(DjangoModelFactory):
    class Meta:
        model = models.FonteRecurso
        django_get_or_create = ('codigo',)

    codigo = '9990000001'
    nome = 'Demonstração'


class EsferaOrcamentariaFactory(DjangoModelFactory):
    class Meta:
        model = models.EsferaOrcamentaria
        django_get_or_create = ('codigo',)

    codigo = '99'
    nome = 'Demonstração'


class NaturezaDespesaFactory(DjangoModelFactory):
    class Meta:
        model = models.NaturezaDespesa
        django_get_or_create = ('codigo',)

    codigo = '339039'
    nome = 'Serviços de terceiros'


class SubElementoNaturezaDespesaFactory(DjangoModelFactory):
    class Meta:
        model = models.SubElementoNaturezaDespesa
        django_get_or_create = ('codigo_subelemento', 'natureza_despesa')

    codigo_subelemento = '99'
    nome = 'Manutenção'
    natureza_despesa = factory.SubFactory(NaturezaDespesaFactory)


class _DocumentoFactory(DjangoModelFactory):
    """Campos comuns de ``DocumentoBase``: empenho, liquidação e pagamento só diferem no número e no tipo."""

    class Meta:
        abstract = True
        django_get_or_create = ('numero',)

    data_emissao = factory.LazyFunction(date.today)
    unidade_orcamentaria = factory.SubFactory(ClassificacaoInstitucionalFactory)
    observacao = 'Manutenção predial de demonstração'
    favorecido_codigo = '00000000000000'
    favorecido_nome = 'Empresa de Demonstração'
    acao_governo = factory.SubFactory(AcaoGovernoFactory)
    ptres = factory.SubFactory(ProgramaTrabalhoResumidoFactory)
    plano_interno = factory.SubFactory(PlanoInternoFactory)
    fonte_recurso = factory.SubFactory(FonteRecursoFactory)
    esfera_orcamentaria = factory.SubFactory(EsferaOrcamentariaFactory)
    emitente_ug = factory.SubFactory(UnidadeGestoraFactory)
    responsavel_ug = factory.SelfAttribute('emitente_ug')


class DocumentoEmpenhoFactory(_DocumentoFactory):
    class Meta:
        model = models.DocumentoEmpenho

    numero = factory.LazyFunction(lambda: f'{date.today().year}NE900001')
    tipo = 'NE'


class DocumentoLiquidacaoFactory(_DocumentoFactory):
    """Nota de sistema (NS): é a liquidação que as variáveis financeiras somam, não o empenho."""

    class Meta:
        model = models.DocumentoLiquidacao

    numero = factory.Sequence(lambda n: f'{date.today().year}NS{n:06d}')
    tipo = 'NS'


class EventoNotaEmpenhoFactory(DjangoModelFactory):
    """Evento SIAFI do item de empenho: inclusão (padrão), reforço ou anulação (``EventoNotaEmpenho.INCLUSAO/REFORCO/ANULACAO``)."""

    class Meta:
        model = models.EventoNotaEmpenho
        django_get_or_create = ('codigo',)

    codigo = str(models.EventoNotaEmpenho.INCLUSAO)
    nome = factory.LazyAttribute(lambda o: f'Evento {o.codigo}')


class DocumentoEmpenhoItemFactory(DjangoModelFactory):
    class Meta:
        model = models.DocumentoEmpenhoItem
        django_get_or_create = ('documento_empenho', 'subitem', 'evento', 'valor')

    documento_empenho = factory.SubFactory(DocumentoEmpenhoFactory)
    subitem = factory.SubFactory(SubElementoNaturezaDespesaFactory)
    valor = Decimal('12000.00')
    subitem_original = '99'
    evento = None


class DocumentoLiquidacaoItemFactory(DjangoModelFactory):
    """Item liquidado de um empenho: é por ``documento_empenho_inicial`` que a liquidação volta ao empenho."""

    class Meta:
        model = models.DocumentoLiquidacaoItem
        django_get_or_create = ('documento_liquidacao', 'subitem', 'documento_empenho_inicial', 'evento', 'valor')

    documento_liquidacao = factory.SubFactory(DocumentoLiquidacaoFactory)
    documento_empenho_inicial = factory.SubFactory(DocumentoEmpenhoFactory)
    subitem = factory.SubFactory(SubElementoNaturezaDespesaFactory)
    valor = Decimal('4000.00')
    subitem_original = '99'
    evento = None


class ContaContabilFactory(DjangoModelFactory):
    class Meta:
        model = models.ContaContabil
        django_get_or_create = ('codigo',)

    # A conta de "crédito recebido" que as variáveis financeiras somam nas notas de crédito.
    codigo = '622220100'
    nome = 'Crédito disponível'


class NotaCreditoFactory(DjangoModelFactory):
    class Meta:
        model = models.NotaCredito
        django_get_or_create = ('numero',)

    numero = factory.Sequence(lambda n: f'{date.today().year}NC{n:06d}')
    conta_contabil = factory.SubFactory(ContaContabilFactory)
    data_emissao = factory.LazyFunction(date.today)
    observacao = 'Descentralização de crédito de demonstração'
    unidade_orcamentaria = factory.SubFactory(ClassificacaoInstitucionalFactory)
    emitente_ci = factory.SelfAttribute('unidade_orcamentaria')
    emitente_ug = factory.SubFactory(UnidadeGestoraFactory)
    favorecido_ug = factory.SelfAttribute('emitente_ug')


class NotaCreditoItemFactory(DjangoModelFactory):
    class Meta:
        model = models.NotaCreditoItem
        django_get_or_create = ('nota_credito', 'responsavel_ug', 'acao_governo', 'fonte_recurso', 'subitem')

    nota_credito = factory.SubFactory(NotaCreditoFactory)
    esfera_orcamentaria = factory.SubFactory(EsferaOrcamentariaFactory)
    acao_governo = factory.SubFactory(AcaoGovernoFactory)
    responsavel_ug = factory.SubFactory(UnidadeGestoraFactory)
    ptres = factory.SubFactory(ProgramaTrabalhoResumidoFactory)
    plano_interno = factory.SubFactory(PlanoInternoFactory)
    fonte_recurso = factory.SubFactory(FonteRecursoFactory)
    subitem = factory.SubFactory(SubElementoNaturezaDespesaFactory)
    valor = Decimal('300.00')
    naturesa_despesa_original = '339039'
    grupo_despesa_original = '3'


class RAPFactory(DjangoModelFactory):
    """Restos a pagar: um empenho de ano anterior que ``ano`` traz para a execução corrente."""

    class Meta:
        model = models.RAP
        django_get_or_create = ('numero', 'ano')

    numero = factory.Sequence(lambda n: f'{date.today().year - 1}NE{n:06d}')
    ano = factory.LazyFunction(lambda: date.today().year)
    unidade_orcamentaria = factory.SubFactory(ClassificacaoInstitucionalFactory)
    acao_governo = factory.SubFactory(AcaoGovernoFactory)
    ptres = factory.SubFactory(ProgramaTrabalhoResumidoFactory)
    plano_interno = factory.SubFactory(PlanoInternoFactory)
    fonte_recurso = factory.SubFactory(FonteRecursoFactory)
    emitente_ug = factory.SubFactory(UnidadeGestoraFactory)
    responsavel_ug = factory.SelfAttribute('emitente_ug')


class RAPItemFactory(DjangoModelFactory):
    class Meta:
        model = models.RAPItem
        django_get_or_create = ('rap', 'subitem', 'subitem_original')

    rap = factory.SubFactory(RAPFactory)
    subitem = factory.SubFactory(SubElementoNaturezaDespesaFactory)
    valor_nao_proc_liquidado = Decimal('700.00')
    subitem_original = '99'


class GRUFactory(DjangoModelFactory):
    class Meta:
        model = models.GRU
        django_get_or_create = ('codigo',)

    # Um dos códigos de recolhimento que `Variavel.get_RECCAPT_qs` conta como recurso próprio captado.
    codigo = '28812'
    nome = 'Serviços educacionais'


class ReceitaGRUFactory(DjangoModelFactory):
    class Meta:
        model = models.ReceitaGRU
        django_get_or_create = ('ano', 'gru', 'emitente_ug')

    ano = factory.LazyFunction(lambda: date.today().year)
    gru = factory.SubFactory(GRUFactory)
    emitente_ug = factory.SubFactory(UnidadeGestoraFactory)
    valor = Decimal('1500.00')


class TipoDocumentoEmpenhoEspecificoFactory(DjangoModelFactory):
    class Meta:
        model = models.TipoDocumentoEmpenhoEspecifico
        django_get_or_create = ('descricao',)

    descricao = factory.Sequence(lambda n: f'Tipo específico {n}')
    aplicar_calculo = False


class HistoricoImportacaoFactory(DjangoModelFactory):
    """``data`` é ``auto_now_add``: para uma importação antiga, regrave a data depois com ``update``."""

    class Meta:
        model = models.HistoricoImportacao
