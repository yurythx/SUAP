import json
import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from html import unescape as html_unescape

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import transaction
from django.db.models import Q, Sum, UniqueConstraint
from django.http import HttpRequest
from django.template.defaultfilters import linebreaksbr
from django.template.loader import render_to_string

from almoxarifado.models import Empenho
from comum.models import Arquivo, Configuracao, PrestadorServico
from djtools.choices import Meses
from djtools.db import models
from djtools.templatetags.filters import format_, format_money, in_group
from djtools.utils import compare_model_objects, formata_nome_arquivo, send_mail, somar_dias
from documento_eletronico.models import DocumentoStatus, DocumentoTexto, TipoDocumento
from protocolo.models import Processo
from rh.models import Pessoa, PessoaJuridica, Servidor, UnidadeOrganizacional
from suap import nomenclatura
from tesouro_gerencial.models import DocumentoEmpenho

""" Seguro Garantia, Fiança, Caução """
TIPO_GARANTIA_SEGURO = 'SEGURO'
TIPO_GARANTIA_FIANCA = 'FIANCA'
TIPO_GARANTIA_CAUCAO = 'CAUCAO'
TIPO_GARANTIA_SIAFI = 'SIAFI'

TIPO_GARANTIA_CHOICES = [
    [TIPO_GARANTIA_SEGURO, 'Seguro Garantia'],
    [TIPO_GARANTIA_FIANCA, 'Fiança'],
    [TIPO_GARANTIA_CAUCAO, 'Caução'],
    [TIPO_GARANTIA_SIAFI, 'Registro Garantia no SIAFI'],
]

TIPO_TERMO_ADITIVO_MAJORACAO = 'MAJ'
TIPO_TERMO_ADITIVO_SUPRESSAO = 'SUP'

TIPO_TERMO_ADITIVO_CHOICES = [[TIPO_TERMO_ADITIVO_MAJORACAO, 'Majoração'], [TIPO_TERMO_ADITIVO_SUPRESSAO, 'Supressão']]

CONTINUIDADE_CONTINUO = 'CONTINUO'
CONTINUIDADE_POR_ESCOPO = 'ESCOPO'
CONTINUIDADE_INDETERMINADO = 'INDETERMINADO'
CONTINUIDADE_CHOICES = [
    [CONTINUIDADE_CONTINUO, 'Contínuo'],
    [CONTINUIDADE_POR_ESCOPO, 'Por escopo/Não Continuado'],
    [CONTINUIDADE_INDETERMINADO, 'Indeterminado'],
]

NATUREZA_DESPESA = 'DESPESA'
NATUREZA_RECEITA = 'RECEITA'
NATUREZA_RECEITA_DESPESA = 'RECEITA_DESPESA'
NATUREZA_SEM_IMPACTO_FINANCEIRO = 'SEM_IMPACTO_FINANCEIRO'
NATUREZA_CHOICES = [
    [NATUREZA_DESPESA, 'Despesa'],
    [NATUREZA_RECEITA, 'Receita'],
    [NATUREZA_RECEITA_DESPESA, 'Receita e Despesa'],
    [NATUREZA_SEM_IMPACTO_FINANCEIRO, 'Sem impacto financeiro'],
]


class SituacaoOcorrencia:
    SITUACAO_PENDENTE = 'PEN'
    SITUACAO_RESOLVIDA = 'RES'

    SITUACAO_CHOICES = [[SITUACAO_PENDENTE, 'Pendente'], [SITUACAO_RESOLVIDA, 'Resolvida']]


class GatilhoAgenda:
    MAO_OBRA_EXCLUSIVA = 'MOE'
    GATILHO_CHOICES = [
        [MAO_OBRA_EXCLUSIVA, 'Possui dedicação de mão de obra exclusiva?'],
    ]


class TipoContrato(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição', max_length=30)

    class Meta:
        verbose_name = 'Tipo de Contrato'
        verbose_name_plural = 'Tipos de Contratos'

    def __str__(self):
        return self.descricao


class SubtipoContrato(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição')
    tipo = models.ForeignKeyPlus(TipoContrato, verbose_name='Tipo de Contrato')

    class Meta:
        verbose_name = 'Subtipo de Contrato'
        verbose_name_plural = 'Subtipos de Contratos'

    def __str__(self):
        return self.descricao


class MotivoConclusaoContrato(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição')

    class Meta:
        verbose_name = 'Motivo de Conclusão de Contrato'
        verbose_name_plural = 'Motivos de Conclusão de Contratos'

    def __str__(self):
        return self.descricao


class TipoLicitacao(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição')

    class Meta:
        verbose_name = 'Tipo de Licitação'
        verbose_name_plural = 'Tipos de Licitação'

    def __str__(self):
        return self.descricao


class ContratoQueryset(models.QuerySet):
    def ativos(self):
        return self.filter(concluido=False, cancelado=False)

    def concluidos(self):
        return self.filter(concluido=True, cancelado=False)

    def proximos_a_vencer(self):
        hoje = datetime.now().date()
        dias_inicio_licitacao = Configuracao.get_valor_por_chave('contratos', 'dias_nova_licitacao') or 90
        return self.ativos().filter(data_vencimento__gte=hoje, data_vencimento__lte=hoje + timedelta(days=int(dias_inicio_licitacao)))

    def proximos_a_vencer_com_garantias(self):
        return self.proximos_a_vencer().filter(garantias__isnull=False)

    def com_vigencia_expirada(self):
        hoje = datetime.now().date()
        return self.ativos().filter(data_vencimento__lt=hoje)

    def com_ocorrencias_expiradas(self):
        hoje = datetime.now()
        return self.ativos().filter(ocorrencias__prazo_resolucao__lt=hoje, ocorrencias__situacao=SituacaoOcorrencia.SITUACAO_PENDENTE)

    def a_serem_aditivados(self):
        daqui_a_30_dias = datetime.now() + timedelta(days=30)
        return self.ativos().filter(continuidade=CONTINUIDADE_CONTINUO, data_vencimento__lt=daqui_a_30_dias).order_by('data_vencimento')

    def a_serem_licitados(self):
        data_5_anos_atras = date.today() - timedelta(5 * 365)
        data_5_anos_mais_prazo_licitacao = date.today() - timedelta(5 * 365)
        return self.filter(data_inicio__range=[data_5_anos_atras, data_5_anos_mais_prazo_licitacao]).order_by('data_fim')


class ContratoManager(models.Manager):
    def get_queryset(self):
        return ContratoQueryset(self.model, using=self._db)

    def ativos(self):
        return self.get_queryset().ativos()

    def concluidos(self):
        return self.get_queryset().concluidos()

    def proximos_a_vencer(self):
        return self.get_queryset().proximos_a_vencer()

    def proximos_a_vencer_com_garantias(self):
        return self.get_queryset().proximos_a_vencer_com_garantias()

    def com_vigencia_expirada(self):
        return self.get_queryset().com_vigencia_expirada()

    def com_ocorrencias_expiradas(self):
        return self.get_queryset().com_ocorrencias_expiradas()

    def a_serem_aditivados(self):
        return self.get_queryset().a_serem_aditivados()

    def a_serem_licitados(self):
        return self.get_queryset().a_serem_licitados()


class BaseLegal(models.ModelPlus):
    titulo = models.CharFieldPlus('Título', max_length=100)
    vigencia = models.PositiveSmallIntegerField('Vigência', help_text='Informe a vigência em meses.', null=True, blank=True)
    prorrogacao = models.PositiveSmallIntegerField(
        'Prorrogação', help_text='Informe a prorrogação em meses, após o término da vigência inicial.', null=True, blank=True
    )
    conformidade_base_legal = models.CharFieldPlus(
        'Conformidade da base legal para contratos administrativos',
        help_text='Informe aqui a conformidade da base legal que será utilizada nos documentos eletrônicos de contratos administrativos.',
        max_length=255,
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = 'Base Legal'
        verbose_name_plural = 'Bases Legais'

    def __str__(self):
        return f'{self.titulo}'

    @property
    def tempo_maximo_prorrogacao(self):
        return (self.vigencia or 0) + (self.prorrogacao or 0)


class Contrato(models.ModelPlus):
    SEARCH_FIELDS = (
        'id',
        'numero',
        'objeto',
        'pregao',
        'processo__numero_processo',
        'processo__numero_processo_eletronico',
        *tuple(f'contratada__{search}' for search in Pessoa.SEARCH_FIELDS),
    )
    tipo = models.ForeignKeyPlus(TipoContrato, verbose_name='Tipo de Contrato', on_delete=models.CASCADE)
    subtipo = models.ForeignKeyPlus(SubtipoContrato, verbose_name='SubTipo de Contrato', on_delete=models.CASCADE, null=True, blank=True)
    numero = models.CharFieldPlus('Número', help_text='No formato: 99999/9999', unique=False)
    valor = models.DecimalFieldPlus('Valor do Contrato')
    valor_executado = models.DecimalFieldPlus('Valor Executado', null=True, blank=True)
    valor_total = models.DecimalFieldPlus('Valor Total', null=True, blank=True)
    valor_previsto_parcela = models.DecimalFieldPlus(null=True, blank=True)

    data_inicio = models.DateFieldPlus('Data de Início', db_column='data_inicio')
    data_fim = models.DateField('Data de Término', db_column='data_fim', null=True, blank=True)
    data_vencimento = models.DateField('Data de Vencimento do Contrato', null=True, blank=True)
    objeto = models.TextField('Objeto de Contrato', max_length=500)
    base_legal = models.ForeignKeyPlus(BaseLegal, null=True, verbose_name='Base Legal', on_delete=models.SET_NULL)
    permite_medicao_sem_empenho = models.BooleanField(
        'Permitir medição sem empenho vinculado?',
        default=False,
        help_text='Caso esta opção seja marcada, será possível registrar o valor executado nas medições sem a necessidade de indicar os empenhos',
    )
    processo = models.ForeignKeyPlus(Processo, null=True, blank=False, verbose_name='Processo', on_delete=models.CASCADE)
    empenho = models.ForeignKeyPlus(Empenho, null=True, verbose_name='Empenho', on_delete=models.CASCADE)
    campi = models.ManyToManyField(
        UnidadeOrganizacional, db_column='campus_id', related_name='contratos', verbose_name=f'{nomenclatura.campi} Atendidos'
    )
    campus_gerenciador = models.ForeignKeyPlus(
        UnidadeOrganizacional, verbose_name=f'{nomenclatura.campus} Gerenciador', null=True, blank=False, on_delete=models.CASCADE
    )
    setores_gerenciadores = models.ManyToManyFieldPlus('rh.setor', verbose_name='Setores Gerenciadores', blank=True)
    vinculo_contratado = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Pessoa Contratada', related_name='contratos', on_delete=models.CASCADE)
    contratada = models.ForeignKeyPlus(PessoaJuridica, null=True, verbose_name='Contratada', on_delete=models.CASCADE)
    qtd_parcelas = models.SmallIntegerField(db_column='qtd_parcelas', verbose_name='Quantidade de Parcelas', default=1)

    arquivo = models.OneToOneField(Arquivo, null=True, on_delete=models.CASCADE)
    arquivo_contrato = models.PrivateFileField(
        verbose_name='Arquivo do Contrato',
        upload_to='contratos/arquivos/',
        filetypes=['pdf'],
        help_text='O formato do arquivo deve ser ".pdf"',
        null=True,
        blank=True,
        max_length=500,
        validators=[
            FileExtensionValidator(
                allowed_extensions=[
                    'pdf',
                ]
            )
        ],
    )
    documento_digital_contrato = models.ForeignKeyPlus(
        'documento_eletronico.DocumentoTexto', verbose_name='Documento Digital do Contrato', null=True, blank=True
    )

    # Licitação
    tipo_licitacao = models.ForeignKeyPlus(TipoLicitacao, verbose_name='Tipo de Licitação', null=True, blank=True, on_delete=models.CASCADE)
    pregao = models.CharField('Número da Licitação', max_length=100, null=True, blank=True)
    estimativa_licitacao = models.DateField('Estimativa para início dos procedimentos para nova Licitação', null=True, blank=True)

    # Conclusao
    data_conclusao = models.DateField('Data de Conclusão', null=True, blank=True)
    concluido = models.BooleanField('Concluído?', default=False)
    motivo_conclusao = models.ForeignKeyPlus(MotivoConclusaoContrato, verbose_name='Motivo de Conclusão', null=True, blank=True)

    # Cancelamento
    cancelado = models.BooleanField('Cancelado?', default=False)
    motivo_cancelamento = models.TextField('Motivo de Cancelamento', blank=True)
    dh_cancelamento = models.DateTimeField('Data/Hora Cancelamento', blank=True, null=True)
    usuario_cancelamento = models.ForeignKeyPlus(
        'comum.User',
        verbose_name='Usuário Cancelamento',
        null=True,
        blank=True,
        editable=False,
        on_delete=models.CASCADE,
    )

    numero_processo = models.CharField('Número Processo', max_length=20, null=True, blank=True)
    numero_empenho = models.CharField(
        verbose_name='Números de Empenhos', help_text='Números de Empenhos separados por vírgula', max_length=100, null=True, blank=True
    )

    # Garantia
    exige_garantia_contratual = models.BooleanField(' Possui exigência de garantia contratual?', default=False)
    documentos_empenho = models.ManyToManyField(DocumentoEmpenho, through='DocumentoEmpenhoContrato')

    continuidade = models.CharFieldPlus('Continuidade', max_length=20, choices=CONTINUIDADE_CHOICES, null=True, blank=True)
    natureza = models.CharFieldPlus('Natureza', max_length=30, choices=NATUREZA_CHOICES, null=True, blank=True)
    mao_obra_exclusiva = models.BooleanField('Possui dedicação de mão de obra exclusiva?', default=False, null=True, blank=True)
    GRAU_RISCO_CHOICES = [(1, 'Grau 1'), (2, 'Grau 2'), (3, 'Grau 3')]
    grau_risco = models.PositiveSmallIntegerField('Grau de risco (1/2/3)', choices=GRAU_RISCO_CHOICES, null=True, blank=True)

    # ComprasGov
    id_comprasgov = models.PositiveIntegerFieldPlus('Identificador no ComprasGov', null=True, blank=True)

    objects = ContratoManager()

    class Meta:
        verbose_name = 'Contrato'
        verbose_name_plural = 'Contratos'
        permissions = (
            ('pode_visualizar_contrato', 'Pode visualizar contrato'),
            ('pode_submeter_arquivo', 'Pode submeter arquivo'),
            ('pode_visualizar_arquivo', 'Pode visualizar aquivo'),
            ('pode_efetuar_medicao', 'Pode efetuar medição'),
            ('pode_gerar_cronograma', 'Pode gerar cronograma'),
            ('pode_visualizar_cronograma', 'Pode visualizar cronograma'),
            ('pode_adicionar_publicacao', 'Pode adicionar publicação'),
            ('pode_excluir_publicacao', 'Pode excluir publicação'),
            ('pode_submeter_publicacao', 'Pode submeter publicação'),
            ('pode_adicionar_anexo', 'Pode adicionar anexo'),
            ('pode_visualizar_anexo', 'Pode visualizar anexo'),
            ('pode_visualizar_publicacao', 'Pode visualizar publicação'),
            ('pode_adicionar_fiscal', 'Pode adicionar fiscal'),
            ('pode_excluir_fiscal', 'Pode exlcuir fiscal'),
            ('pode_aditivar_contrato', 'Pode aditivar contrato'),
            ('pode_cancelar_contrato', 'Pode cancelar contrato'),
            ('pode_submeter_medicao', 'Pode submeter medição'),
            ('pode_adicionar_empenho', 'Pode adicionar empenho'),
            ('pode_encerrar_contrato', 'Pode encerrar contrato'),
        )

    def documentos_texto_tipo_contato_relacionados(self):
        tipo_documento_contrato = TipoDocumento.objects.filter(nome='Contrato', ativo=True).first()
        return self.documentos_texto.filter(data_hora_remocao__isnull=True, documento__modelo__tipo_documento_texto=tipo_documento_contrato).exclude(
            documento__status=DocumentoStatus.STATUS_CANCELADO
        )

    def pode_gerenciar(self, user):
        restringir_por_unidade = Configuracao.get_valor_por_chave('contratos', 'restringir_por_unidade')
        if restringir_por_unidade:
            if user.has_group_cached('Gerente de Contrato') or user.has_group_cached('Operador de Contrato'):
                vinculo = user.get_vinculo()
                setor = vinculo and vinculo.setor
                if not setor:
                    return False
                if self.campus_gerenciador_id == setor.uo_id:
                    if self.setores_gerenciadores.exists():
                        return self.setores_gerenciadores.filter(pk=setor.pk)
                    else:
                        return True
                else:
                    return False
            else:
                return False
        else:
            if user.has_group_cached('Gerente de Contrato'):
                return True
            if not user.has_group_cached('Operador de Contrato'):
                return False
            vinculo = user.get_vinculo()
            setor = vinculo and vinculo.setor
            return bool(setor and self.campus_gerenciador_id == setor.uo_id)

    def __str__(self):
        return f'{self.numero}'

    def get_absolute_url(self):
        return f'/contratos/contrato/{self.id}/'

    def delete(self, *args, **kwargs):
        for obj in PublicacaoContrato.objects.filter(contrato__id=self.id):
            obj.delete()
        for obj in AnexoContrato.objects.filter(contrato__id=self.id):
            obj.delete()
        for obj in Aditivo.objects.filter(contrato__id=self.id):
            obj.delete()

        arquivo = self.arquivo
        super().delete(*args, **kwargs)
        if arquivo:
            arquivo.delete()

    def clean_numero(self):
        padrao = r'^(\d{1,5})/(\d{4})$'
        correspondencia = re.match(padrao, self.numero)

        if correspondencia:
            numero = correspondencia.group(1)
            ano = correspondencia.group(2)
            numero_formatado = numero.zfill(5)
            self.numero = f'{numero_formatado}/{ano}'
        else:
            raise ValidationError('Informe um número de contrato seguindo o formato: 99999/9999.')

    def clean(self):
        self.clean_numero()
        super().clean()

    def save(self, *args, **kwargs):
        if self.pk:
            self.data_vencimento = self.get_data_vencimento()
            self.valor_executado = self.get_valor_executado()
            self.valor_total = self.get_valor_total()
            self.valor_previsto_parcela = self.get_valor_previsto_parcela()
        else:
            self.data_vencimento = self.data_fim
            self.valor_executado = Decimal('0')
            self.valor_total = self.valor
            self.valor_previsto_parcela = Decimal('0')
        super().save(*args, **kwargs)

    @property
    def eh_continuo(self):
        return self.continuidade and self.continuidade == CONTINUIDADE_CONTINUO

    @property
    def possui_arrecadacao_receita(self):
        return self.natureza and self.natureza in [NATUREZA_RECEITA, NATUREZA_RECEITA_DESPESA]

    def get_qtd_dias_total(self):
        return (self.get_data_fim() - self.data_inicio).days if self.get_data_fim() else (datetime.now().date() - self.data_inicio).days

    def get_qtd_dias_executado(self):
        return (date.today() - self.data_inicio).days

    def get_percentual_dias_executado(self):
        qtd_dias_total = self.get_qtd_dias_total()
        if qtd_dias_total == 0:
            return 0

        percentual = int(self.get_qtd_dias_executado() * 100 / qtd_dias_total)
        if percentual > 100:
            return 100
        if percentual < 0:
            return 0
        return percentual

    def get_percentual_executado(self):
        percentual = 0
        if self.valor_total > 0:  # evita divisao por zero
            percentual = Decimal('100') * self.valor_executado / self.valor_total
        return int(percentual)

    def get_valor_total(self):
        return self.valor + self.get_valor_aditivado() + self.get_valor_apostilado()

    def get_valor_executado(self):
        total = Decimal('0')
        cronograma = self.get_cronograma()
        if cronograma:
            for parcela in cronograma.parcelas.all():
                for medicao in parcela.medicoes.all():
                    total += medicao.valor_executado
        return total

    def get_valor_previsto_parcela(self):
        total = Decimal('0')
        cronograma = self.get_cronograma()
        if cronograma:
            for parcela in Parcela.objects.filter(cronograma=cronograma, medicoes__isnull=True, sem_medicao=False):
                total += parcela.valor_previsto
        return total

    def get_saldo_contrato(self):
        return self.valor_total - (self.valor_previsto_parcela + self.valor_executado)

    def get_saldo_atual(self):
        return self.valor_total - (self.valor_executado)

    def get_total_arrecadacao(self):
        return ArrecadacaoReceita.objects.filter(contrato=self).aggregate(total=Sum('valor'))['total'] or 0

    def adicionar_termo_aditivo(self, termo):
        ultimo_termo = self.get_ultimo_termo_aditivo()
        if ultimo_termo:
            termo.ordem = ultimo_termo.ordem + 1
        else:
            termo.ordem = 1
        termo.contrato = self
        termo.save()
        return termo

    def adicionar_fiscal(self, fiscal):
        if not in_group(fiscal.servidor.get_user(), 'Fiscal de Contrato'):
            fiscal.servidor.get_user().groups.add(Group.objects.get(name='Fiscal de Contrato'))
        fiscal.contrato = self
        fiscal.save()
        return fiscal

    def adicionar_anexo(self, anexo):
        anexo.contrato = self
        anexo.save()
        return anexo

    def get_publicacoes_anexo(self):
        return PublicacaoAditivo.objects.filter(aditivo__contrato=self).order_by('aditivo', 'data')

    def adicionar_publicacao(self, publicacao):
        publicacao.contrato = self
        publicacao.save()
        return publicacao

    def get_publicacoes_contrato(self):
        return PublicacaoContrato.objects.filter(contrato=self).order_by('id')

    def get_qtd_documentos_relacionados(self):
        return self.anexos.all().count() + self.documentos_texto.all().count()

    def get_total_empenhado(self):
        total_empenhado = 0
        for documento_empenho in self.documentos_empenho.all():
            total_empenhado += documento_empenho.get_valor()
        return total_empenhado

    def get_total_consumido(self):
        total_consumido = 0
        for documento_empenho in self.documentos_empenho.all():
            total_consumido += documento_empenho.get_valor_pago()
        return total_consumido

    def get_saldo_restante(self):
        saldo_restante = 0
        for documento_empenho in self.documentos_empenho.all():
            saldo_restante += documento_empenho.get_saldo_restante()
        return saldo_restante

    def get_calculos_conta_vinculada(self):
        return (
            self.conta_vinculada_calculos.select_related('medicao', 'medicao__processo', 'usuario')
            .prefetch_related('itens__maodeobra', 'medicao__movimentacoes_conta__conta')
            .order_by('-data_criacao', '-id')
        )

    def get_empenhos(self):
        """
        Retorna todos os documentos_empenho_contrato vinculados, os quais possuem o attr empenho com valores e saldos restantes
        """
        return self.documentos_empenho_contrato.all().order_by('empenho__numero')

    def get_fiscais_atuais(self):
        return self.fiscais.filter(data_exclusao__isnull=True, inativo=False)

    def get_fiscal(self, servidor):
        return self.get_fiscais_atuais().filter(servidor=servidor).select_related('tipo').first()

    def eh_fiscal(self, servidor):
        return self.get_fiscais_atuais().filter(servidor=servidor).exists()

    def eh_gestor_contrato(self, servidor):
        return self.get_fiscais_atuais().filter(servidor=servidor, tipo__eh_gestor_contrato=True).exists()

    def get_uos_as_string(self):
        return ', '.join(self.campi.all().values_list('sigla', flat=True))

    def set_cronograma(self, cronograma):
        cronograma.contrato = self
        cronograma.save()

    def get_cronograma(self):
        return self.cronogramas.all().order_by('-id').prefetch_related('parcelas').first()

    def get_valor_aditivado(self):
        total = Decimal('0')
        for aditivo in self.aditivos.all():
            if aditivo.de_valor and aditivo.valor:  # evita NoneType em aditivo.valor
                if aditivo.tipo_termo_aditivo == TIPO_TERMO_ADITIVO_SUPRESSAO:
                    total = total - aditivo.valor
                else:
                    total += aditivo.valor
        return total

    def get_valor_apostilado(self):
        total = Decimal('0')
        for apostilamento in self.get_apostilamentos():
            if apostilamento.valor:  # evita NoneType em aditivo.valor
                total += apostilamento.valor
        return total

    def get_data_fim(self):
        data = self.data_fim
        for aditivo in self.aditivos.all().order_by('data_fim'):
            if aditivo.de_prazo and aditivo.data_fim:
                data = aditivo.data_fim
        return data

    def get_apostilamentos(self):
        return self.apostilamentos.all()

    def get_proxima_ordem(self):
        ultimo_termo = self.get_ultimo_termo_aditivo()
        return (ultimo_termo.ordem or 0) + 1 if ultimo_termo else 1

    def get_data_vencimento(self):
        data_vencimento = self.data_fim
        ultimo_aditivo = None
        if data_vencimento:
            ultimo_aditivo = self.aditivos.filter(de_prazo=True, data_fim__gt=data_vencimento).order_by('data_fim').last()
        return ultimo_aditivo.data_fim if ultimo_aditivo else data_vencimento

    def get_data_prorrogacao(self):
        if self.eh_continuo:
            data_inicio = self.data_inicio
            if self.base_legal and self.base_legal.tempo_maximo_prorrogacao > 0:
                return data_inicio + relativedelta(years=(self.base_legal.tempo_maximo_prorrogacao // 12))
            else:
                ultimo_aditivo = self.aditivos.filter(de_prazo=True, data_inicio__gt=self.data_inicio).order_by('-data_inicio').last()
                data_inicial = ultimo_aditivo.data_inicio if ultimo_aditivo else data_inicio
                return data_inicial + timedelta(5 * 365)

    def get_aditivos(self):
        return self.aditivos.all().order_by('ordem')

    def get_ultimo_termo_aditivo(self):
        return self.aditivos.order_by('-ordem').first()

    def mesmo_campus(self, request):
        return self.campus_gerenciador_id == request.user.get_vinculo().setor.uo_id

    def is_operador(self, request):
        mesmo_campus = self.mesmo_campus(request)
        pode_gerenciar = self.pode_gerenciar(request.user)
        return (mesmo_campus or pode_gerenciar) and request.user.has_group_cached('Operador de Contrato')

    def pode_executar_acoes_coordenador_gerente(self, request):
        mesmo_campus = self.mesmo_campus(request)
        return request.user.has_group_cached('Coordenador de Contrato Sistêmico') or (
            request.user.has_group_cached('Gerente de Contrato') and mesmo_campus
        )

    def pode_efetuar_medicao(self, request):
        fiscal = None
        if request.user.eh_servidor:
            fiscal = self.get_fiscal(request.user.get_relacionamento())
        return request.user.has_perm('contratos.pode_efetuar_medicao') and fiscal

    def pode_gerenciar_empenho(self, request):
        is_operador = self.is_operador(request)
        pode_executar_acoes_coordenador_gerente = self.pode_executar_acoes_coordenador_gerente(request)
        fiscal = None
        if request.user.eh_servidor:
            fiscal = self.get_fiscal(request.user.get_relacionamento())
        return (is_operador or fiscal or pode_executar_acoes_coordenador_gerente) and not self.cancelado

    def pode_gerenciar_conta(self, request):
        pode_executar_acoes_coordenador_gerente = self.pode_executar_acoes_coordenador_gerente(request)
        pode_efetuar_medicao = self.pode_efetuar_medicao(request)
        return (pode_executar_acoes_coordenador_gerente or pode_efetuar_medicao) and self.mao_obra_exclusiva and not self.cancelado

    def pode_gerenciar_ocorrencia(self, request):
        pode_executar_acoes_coordenador_gerente = self.pode_executar_acoes_coordenador_gerente(request)
        fiscal = None
        if request.user.eh_servidor:
            fiscal = self.get_fiscal(request.user.get_relacionamento())
        return (fiscal or pode_executar_acoes_coordenador_gerente) and not self.cancelado

    def pode_gerenciar_penalidade(self, request):
        is_operador = self.is_operador(request)
        pode_executar_acoes_coordenador_gerente = self.pode_executar_acoes_coordenador_gerente(request)
        fiscal = None
        if request.user.eh_servidor:
            fiscal = self.get_fiscal(request.user.get_relacionamento())
        return (fiscal or is_operador or pode_executar_acoes_coordenador_gerente) and not self.cancelado

    def pode_gerenciar_mao_de_obra(self, request):
        pode_executar_acoes_coordenador_gerente = self.pode_executar_acoes_coordenador_gerente(request)
        fiscal = None
        if request.user.eh_servidor:
            fiscal = self.get_fiscal(request.user.get_relacionamento())
        return (fiscal or pode_executar_acoes_coordenador_gerente) and not self.cancelado

    def pode_gerenciar_agenda_fiscalizacao(self, request):
        pode_executar_acoes_coordenador_gerente = self.pode_executar_acoes_coordenador_gerente(request)
        fiscal = None
        if request.user.eh_servidor:
            fiscal = self.get_fiscal(request.user.get_relacionamento())
        return (fiscal or pode_executar_acoes_coordenador_gerente) and not self.cancelado

    def pode_gerenciar_recebimento_definitivo(self, request: HttpRequest) -> bool:
        pode_executar_acoes_coordenador_gerente = self.pode_executar_acoes_coordenador_gerente(request)
        fiscal = None
        if request.user.eh_servidor:
            fiscal = self.get_fiscal(request.user.get_relacionamento())
        fiscal_eh_gestor = fiscal and fiscal.tipo.eh_gestor_contrato
        return bool((fiscal_eh_gestor or pode_executar_acoes_coordenador_gerente) and not self.cancelado)

    @classmethod
    def get_pendencias(cls, uo):
        contratos_pendentes = {}

        # lista todos os contratos
        contratos = cls.objects.ativos()

        # informou campus?
        if uo:
            contratos = contratos.filter(campi=uo.pk)

        # itera contratos para verificar pendências
        for contrato in contratos:
            pendencias = []

            # anexou arquivo digitalizado (Informações Gerais do Contrato)?
            if not contrato.arquivo:
                pendencias.append('Arquivo digitalizado não anexado')

            # anexou arquivo da Publicação?
            if not contrato.publicacoes.exists():
                pendencias.append('Publicações do contrato não informadas')

            # verificando se alguma publicação está sem anexo
            if contrato.publicacoes.filter(arquivo__isnull=True).exists():
                pendencias.append('Há publicações sem anexo')

            # verificando se algum termo aditivo está sem anexo
            if contrato.aditivos.filter(arquivo__isnull=True).exists():
                pendencias.append('Há termo aditivo sem anexo')

            # verificando se contrato tem fiscal
            if not contrato.fiscais.exists():
                pendencias.append('Contrato sem fiscal definido')

            # verificando se contrato tem cronograma
            if not contrato.cronogramas.exists():
                pendencias.append('Contrato sem cronograma')

            # verificando se parcelas no cronograma
            if contrato.cronogramas.filter(parcelas__isnull=True).exists():
                pendencias.append('Cronograma sem parcelas')

            # se tem pendência, associa mensagens (removendo pendências duplicadas)
            if pendencias:
                contratos_pendentes[contrato] = {'mensagens': set(pendencias)}

        return contratos_pendentes


class TipoPublicacao(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição', max_length=255)

    class Meta:
        verbose_name = 'Tipo de Publicação'
        verbose_name_plural = 'Tipos de Publicações'

    def __str__(self):
        return self.descricao


class PublicacaoContrato(models.ModelPlus):
    contrato = models.ForeignKeyPlus(Contrato, verbose_name='Contrato', related_name='publicacoes', on_delete=models.CASCADE)
    tipo = models.ForeignKeyPlus(TipoPublicacao, verbose_name='Tipo de Publicação', on_delete=models.CASCADE)
    numero = models.CharFieldPlus('Número')
    data = models.DateField()
    descricao = models.CharFieldPlus('Descrição', help_text='Breve descrição sobre o conteúdo da publicação')
    arquivo = models.OneToOneField(Arquivo, null=True, on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Publicação'
        verbose_name_plural = 'Publicações'

    def __str__(self):
        return f'{self.tipo} {self.descricao}'

    def delete(self, *args, **kwargs):
        arquivo = self.arquivo
        super().delete(*args, **kwargs)
        if arquivo:
            arquivo.delete()


class TipoAnexo(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição')

    class Meta:
        verbose_name = 'Tipo de Anexo'
        verbose_name_plural = 'Tipos de Anexos'

    def __str__(self):
        return self.descricao


class TipoFiscal(models.ModelPlus):
    descricao = models.CharFieldPlus(verbose_name='Descrição')
    pode_gerenciar_todas_medicoes_contrato = models.BooleanField(verbose_name='Fiscal pode gerenciar medições de outros fiscais?', default=False)
    eh_gestor_contrato = models.BooleanField(
        verbose_name='É gestor do contrato?', default=False, help_text='Um Fiscal Gestor do Contrato poderá gerar o Termo de Recebimento Definitivo.'
    )

    class Meta:
        verbose_name = 'Tipo de Fiscal'
        verbose_name_plural = 'Tipos de Fiscais'
        ordering = ('descricao',)

    def __str__(self):
        return self.descricao


def anexo_apostilamento_path(instance, filename):
    filename = formata_nome_arquivo(filename)
    return f'contratos/contrato/{instance.contrato.id}/apostilamento/anexo_{instance.id}{filename}'


class Apostilamento(models.ModelPlus):
    REPACTUACAO = 'REPACTUACAO'
    REAJUSTE = 'REAJUSTE'
    DOTACAO = 'DOTACAO'
    OUTROS = 'OUTROS'
    TIPO_CHOICES = [
        (REPACTUACAO, 'Repactuação'),
        (REAJUSTE, 'Reajuste'),
        (DOTACAO, 'Dotação Orçamentária'),
        (OUTROS, 'Outros'),
    ]

    contrato = models.ForeignKeyPlus(Contrato, related_name='apostilamentos', on_delete=models.CASCADE)
    especificacao = models.TextField('Especificação', null=True, blank=True)
    numero = models.CharFieldPlus('Número', help_text='No formato: 99999/9999')
    valor = models.DecimalFieldPlus('Valor', null=True, blank=True)
    data_inicio = models.DateFieldPlus('Data de Início', null=True, blank=True)
    data_fim = models.DateFieldPlus('Data de Vencimento', null=True, blank=True)
    arquivo = models.FileFieldPlus(upload_to=anexo_apostilamento_path)
    numero_processo = models.CharFieldPlus('Número Processo', max_length=20, null=True, blank=True)
    numero_empenho = models.CharFieldPlus('Números de Empenhos', null=True, blank=True, help_text='Números de Empenhos separados por vírgula')
    tipo = models.CharFieldPlus(max_length=20, choices=TIPO_CHOICES, default=OUTROS)

    class Meta:
        verbose_name = 'Apostilamento'
        verbose_name_plural = 'Apostilamentos'

    def __str__(self):
        return f'{self.contrato} - {self.numero}'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.contrato.save()

    def delete(self, *args, **kwargs):
        contrato = self.contrato
        super().delete(*args, **kwargs)
        contrato.save()


class Aditivo(models.ModelPlus):
    contrato = models.ForeignKeyPlus(Contrato, related_name='aditivos', on_delete=models.CASCADE)
    ordem = models.PositiveSmallIntegerField('Ordem', default=0)
    numero = models.CharFieldPlus('Número', help_text='No formato: 99999/9999', unique=False)
    valor = models.DecimalFieldPlus('Valor', null=True, blank=True)
    data_inicio = models.DateFieldPlus('Data de Início', db_column='data_inicio', null=True, blank=True)
    data_fim = models.DateFieldPlus('Data de Vencimento', db_column='data_fim', null=True, blank=True)
    processo = models.ForeignKeyPlus(Processo, related_name='aditivos', null=True, verbose_name='Processo', on_delete=models.CASCADE)
    empenho = models.ForeignKeyPlus(Empenho, related_name='aditivos', null=True, verbose_name='Empenho', on_delete=models.CASCADE)
    arquivo = models.OneToOneField(Arquivo, null=True, on_delete=models.CASCADE)
    de_prazo = models.BooleanField('Aditivo de Prazo', default=False)
    de_valor = models.BooleanField('Aditivo de Valor', default=False)
    de_fiscal = models.BooleanField('Aditivo de Fiscal', default=False)
    de_outro = models.BooleanField('Outros', default=False)
    especificacao = models.TextField('Especificação', null=True, blank=True)
    tipo_termo_aditivo = models.CharFieldPlus('Tipo de Termo de Aditivo', max_length=5, choices=TIPO_TERMO_ADITIVO_CHOICES, null=True, blank=True)
    numero_parcelas = models.PositiveSmallIntegerField('Número de Parcelas', null=True, blank=True)
    numero_processo = models.CharFieldPlus('Número Processo', max_length=20, null=True, blank=True)
    numero_empenho = models.CharFieldPlus('Números de Empenhos', null=True, blank=True, help_text='Números de Empenhos separados por vírgula')

    class Meta:
        verbose_name = 'Termo Aditivo'
        verbose_name_plural = 'Termos Aditivos'
        unique_together = ('contrato', 'ordem')  # Saber se o número é unico ou pode ser repetido no termoo aditivo

    def __str__(self):
        return f'{self.ordem}º Termo ({self.get_tipo()})'

    def save(self, *args, **kwargs):
        if not (self.ordem):
            self.ordem = self.contrato.get_proxima_ordem()
        super().save(*args, **kwargs)
        self.contrato.save()

    def delete(self, *args, **kwargs):
        contrato = self.contrato
        for obj in PublicacaoAditivo.objects.filter(aditivo__id=self.id):
            obj.delete()
        arquivo = self.arquivo
        super().delete(*args, **kwargs)
        if arquivo:
            arquivo.delete()
        contrato.save()

    def adicionar_publicacao(self, publicacao):
        publicacao.aditivo = self
        publicacao.save()
        return publicacao

    def get_tipo(self):
        tipo = []
        if self.de_prazo:
            tipo.append('de Prazo')
        if self.de_valor:
            tipo.append('de Valor')
        if self.de_fiscal:
            tipo.append('de Fiscal')
        if self.de_outro:
            tipo.append('de Outro')
        if len(tipo) == 0:
            tipo = ['Indefinido']

        return ', '.join(tipo)

    def get_fiscais(self):
        return self.contrato.fiscais.filter(termo_aditivo=self)

    def get_qtd_dias_total(self):
        return (self.data_fim - self.data_inicio).days if self.data_fim and self.data_inicio else 0

    def get_qtd_dias_executado(self):
        return (
            (date.today() - self.data_inicio).days
            if self.data_fim and self.data_inicio and date.today() < self.data_fim
            else self.get_qtd_dias_total()
        )

    def get_percentual_dias_executado(self):
        qtd_dias_total = self.get_qtd_dias_total()
        if qtd_dias_total == 0:
            return 0

        percentual = int(self.get_qtd_dias_executado() * 100 / qtd_dias_total)
        if percentual > 100:
            return 100
        if percentual < 0:
            return 0
        return percentual


class MaoDeObra(models.ModelPlus):
    contrato = models.ForeignKeyPlus(Contrato, related_name='maosdeobra', on_delete=models.CASCADE)
    prestador_servico = models.ForeignKeyPlus(PrestadorServico, related_name='maosdeobra', on_delete=models.PROTECT)
    data_nascimento = models.DateFieldPlus('Data de Nascimento')
    categoria = models.CharFieldPlus('Classificação Brasileira de Ocupações - CBO')
    funcao = models.CharFieldPlus('Função')
    escolaridade = models.CharFieldPlus('Escolaridade', max_length=100)
    jornada_trabalho = models.CharFieldPlus('Jornada de Trabalho', max_length=40)
    desligamento = models.DateFieldPlus('Data de Desligamento', null=True)
    campus = models.ForeignKeyPlus(UnidadeOrganizacional, verbose_name=nomenclatura.campus, null=True, blank=True, on_delete=models.CASCADE)

    # Horários
    hora_inicio_jornada = models.TimeFieldPlus('Hora do Início da Jornada', null=True, blank=False)
    hora_fim_jornada = models.TimeFieldPlus('Hora de Fim da Jornada', null=True, blank=False)
    hora_inicio_intervalo = models.TimeFieldPlus('Hora do Início do Intervalo', null=True, blank=False)
    hora_fim_intervalo = models.TimeFieldPlus('Hora de Fim do Intervalo', null=True, blank=False)

    # remuneração
    salario_bruto = models.DecimalFieldPlus('Salário Bruto')
    custo_mensal = models.DecimalFieldPlus('Custo Mensal')
    numero_cct = models.CharFieldPlus('Número da CCT', max_length=50, blank=True)
    inicio_vigencia = models.DateFieldPlus('Data de Início da Vigência', null=True, blank=False)

    data_criacao = models.DateTimeFieldPlus('Data de Criação', null=True, auto_now_add=True)
    data_atualizacao = models.DateTimeFieldPlus('Data da Última Atualização', null=True, auto_now=True)

    class Meta:
        verbose_name = 'Mão-de-Obra'
        verbose_name_plural = 'Mãos-de-Obra'

    def __str__(self):
        return f'{self.contrato} - {self.prestador_servico}'

    def adicionar_anexo(self, anexo):
        anexo.maodeobra = self
        anexo.save()
        return anexo

    @property
    def valor_total_das_verbas(self):
        # Calcula o salário bruto somando todas as verbas salariais associadas a esta Mão de Obra
        salario_bruto = VerbaSalarialMaoDeObra.objects.filter(maodeobra=self).aggregate(Sum('valor'))['valor__sum']
        return salario_bruto or 0


class AnexoMaoDeObra(models.ModelPlus):
    maodeobra = models.ForeignKeyPlus(MaoDeObra, related_name='anexos', on_delete=models.CASCADE)
    descricao = models.CharFieldPlus(verbose_name='Descrição')
    arquivo = models.FileFieldPlus(verbose_name='Arquivo', upload_to='contratos/maodeobra/')
    data = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Anexo'
        verbose_name_plural = 'Anexos'

    def __str__(self):
        return self.descricao


class TipoOcorrencia(models.ModelPlus):
    nome = models.CharFieldPlus('Nome')
    obrigatorio_informar_data_fim = models.BooleanField('Deve informar Data de Fim da Vigência?', default=False)
    ativo = models.BooleanField('Ativo?', default=True)

    class Meta:
        verbose_name = 'Tipo de Ocorrência'
        verbose_name_plural = 'Tipos de Ocorrências'

    def __str__(self):
        return self.nome


class OcorrenciaMaoDeObra(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição')
    maodeobra = models.ForeignKeyPlus(MaoDeObra, related_name='ocorrencias', on_delete=models.PROTECT)
    tipo = models.ForeignKeyPlus(TipoOcorrencia, on_delete=models.PROTECT)
    data_inicio = models.DateFieldPlus('Data de Início da Vigência')
    data_fim = models.DateFieldPlus('Data de Fim da Vigência', null=True, blank=True)
    arquivo = models.FileFieldPlus(verbose_name='Anexo', upload_to='contratos/maodeobra/ocorrencias', null=True, blank=True)

    class Meta:
        verbose_name = 'Ocorrência em Mão-de-Obra'
        verbose_name_plural = 'Ocorrências em Mãos-de-Obra'

    def __str__(self):
        return f'{self.tipo} - {self.maodeobra.prestador_servico}'


class TipoVerbaSalarial(models.ModelPlus):
    nome = models.CharFieldPlus('Nome')
    obrigatorio_informar_data_fim = models.BooleanField('Deve informar Data de Fim da Vigência?', default=False)
    ativo = models.BooleanField('Ativo?', default=True)

    class Meta:
        verbose_name = 'Tipo de Verba Salarial'
        verbose_name_plural = 'Tipos de Verbas Salariais'

    def __str__(self):
        return self.nome


class VerbaSalarialMaoDeObra(models.ModelPlus):
    """
    Classe que representa as informações salariais de uma Mão de Obra
    """

    maodeobra = models.ForeignKeyPlus(MaoDeObra, related_name='verbas_salariais', on_delete=models.PROTECT)
    tipo = models.ForeignKeyPlus(TipoVerbaSalarial, on_delete=models.PROTECT)
    data_inicio = models.DateFieldPlus('Data de Início da Vigência')
    data_fim = models.DateFieldPlus('Data de Fim da Vigência', null=True, blank=True)
    valor = models.DecimalFieldPlus('Valor')

    class Meta:
        verbose_name = 'Verba Salarial'
        verbose_name_plural = 'Verbas Salariais'

    def __str__(self):
        return f'{self.maodeobra.prestador_servico} - {self.tipo.nome} - {self.valor}'


def consulta_susep_path(instance, filename):
    filename = formata_nome_arquivo(filename)
    return f'contratos/contrato/{instance.contrato.id}/consulta_susep/anexo_{instance.id}{filename}'


class Garantia(models.ModelPlus):
    contrato = models.ForeignKeyPlus(Contrato, related_name='garantias', on_delete=models.CASCADE)
    tipo = models.CharFieldPlus('Tipo de Garantia', max_length=20, choices=TIPO_GARANTIA_CHOICES)
    data_inicio = models.DateFieldPlus('Data de Início', null=True, blank=True)
    vigencia = models.DateFieldPlus('Data de Vigência')
    pa_siafi = models.CharFieldPlus('PA do SIAFI', help_text='Lançamento patrimonial (PA) SIAFI')
    valor = models.DecimalFieldPlus()
    consulta_susep = models.FileFieldPlus('Anexo', help_text='Susep, anexos, etc', upload_to=consulta_susep_path, null=True)

    class Meta:
        verbose_name = 'Garantia'
        verbose_name_plural = 'Garantias'

    def __str__(self):
        return f'{self.contrato} - {self.tipo}: {self.vigencia}'


def penalidade_path(instance, filename):
    filename = formata_nome_arquivo(filename)
    return f'contratos/contrato/{instance.contrato.id:d}/penalidade_{filename}'


class Penalidade(models.ModelPlus):
    TIPO_PENALIDADE_ADVERTENCIA = 'Advertência'
    TIPO_PENALIDADE_MULTA = 'Multa'
    TIPO_PENALIDADE_SUSPENSAO = 'Suspensão'

    TIPO_PENALIDADE_CHOICES = [
        [TIPO_PENALIDADE_ADVERTENCIA, 'Advertência'],
        [TIPO_PENALIDADE_MULTA, 'Multa'],
        [TIPO_PENALIDADE_SUSPENSAO, 'Suspensão'],
    ]

    contrato = models.ForeignKeyPlus(Contrato, related_name='penalidades', on_delete=models.CASCADE)
    tipo = models.CharFieldPlus('Tipo', max_length=20, choices=TIPO_PENALIDADE_CHOICES)
    arquivo = models.FileFieldPlus(upload_to=penalidade_path, verbose_name='Arquivo')

    atualizado_por = models.ForeignKeyPlus('comum.Vinculo', null=True, verbose_name='Atualizado Por', on_delete=models.CASCADE)
    atualizado_em = models.DateTimeField('Atualizado em', auto_now=True, null=True, blank=True)

    class Meta:
        verbose_name = 'Penalidade'
        verbose_name_plural = 'Penalidades'
        ordering = ('-atualizado_em',)

    def __str__(self):
        return f'{self.contrato} - {self.tipo}'

    def delete(self, *args, **kwargs):
        arquivo = self.arquivo
        if arquivo:
            arquivo.delete()
        super().delete(*args, **kwargs)


class AnexoContrato(models.ModelPlus):
    contrato = models.ForeignKeyPlus(Contrato, related_name='anexos', on_delete=models.CASCADE)
    tipo = models.ForeignKeyPlus(TipoAnexo, on_delete=models.CASCADE)
    descricao = models.CharFieldPlus('Descrição', help_text='Breve descrição sobre o conteúdo do anexo')
    arquivo = models.OneToOneField(Arquivo, null=True, on_delete=models.CASCADE)
    data = models.DateTimeField(null=True)
    campus = models.ForeignKeyPlus(UnidadeOrganizacional, verbose_name=nomenclatura.campus, on_delete=models.CASCADE, null=True, blank=True)

    class Meta:
        verbose_name = 'Anexo'
        verbose_name_plural = 'Anexos'

    def __str__(self):
        return f'{self.tipo} {self.descricao}'

    def delete(self, *args, **kwargs):
        arquivo = self.arquivo
        super().delete(*args, **kwargs)
        if arquivo:
            arquivo.delete()


class DocumentoTextoContrato(models.ModelPlus):
    contrato = models.ForeignKeyPlus(Contrato, related_name='documentos_texto', on_delete=models.CASCADE)
    documento = models.ForeignKeyPlus('documento_eletronico.DocumentoTexto', verbose_name='Documento')

    # CRIAÇÃO DO VÍNCULO ENTRE DOCUMENTO E CONTRATO
    data_hora_inclusao = models.DateTimeFieldPlus('Data de Inclusão', auto_now_add=True, editable=False)
    usuario_inclusao = models.CurrentUserField(
        verbose_name='Usuário de Inclusão', related_name='%(app_label)s_%(class)s_documentos_processos_criados', null=False, editable=False
    )

    # REMOCÃO LÓGICA DO VÍNCULO ENTRE DOCUMENTO E CONTRATO
    data_hora_remocao = models.DateTimeFieldPlus('Data de Remoção', blank=True, null=True, editable=False)
    usuario_remocao = models.ForeignKeyPlus(
        'comum.User',
        verbose_name='Usuário de Remoção',
        related_name='%(app_label)s_%(class)s_documentos_processos_alterados',
        editable=False,
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'Doc. {self.documento} - Contrato {self.contrato}'


class Fiscal(models.ModelPlus):
    contrato = models.ForeignKeyPlus(Contrato, related_name='fiscais', on_delete=models.CASCADE)
    tipo = models.ForeignKeyPlus(TipoFiscal, on_delete=models.CASCADE)
    servidor = models.ForeignKeyPlus(Servidor, on_delete=models.CASCADE)
    numero_portaria = models.CharFieldPlus('Portaria', max_length=20)
    campus = models.ForeignKeyPlus(UnidadeOrganizacional, verbose_name=nomenclatura.campus, db_column='campus_id', on_delete=models.CASCADE)
    data_nomeacao = models.DateFieldPlus(
        'Data da Nomeação', null=True, blank=True, help_text='Data em que o servidor foi nomeado fiscal do contrato (consultar portaria)'
    )
    data_vigencia = models.DateFieldPlus(
        'Data da Vigência', null=True, blank=True, help_text='Data limite prevista para atuação como fiscal do contrato (consultar portaria)'
    )
    data_exclusao = models.DateFieldPlus('Data da Exclusão', null=True)
    termo_aditivo = models.ForeignKeyPlus(Aditivo, null=True, blank=True, on_delete=models.CASCADE)
    inativo = models.BooleanField('Inativo?', default=False)

    class Meta:
        verbose_name = 'Fiscal'
        verbose_name_plural = 'Fiscais'
        ordering = ('inativo',)

    def __str__(self):
        return f'{self.servidor.pessoa_fisica.nome} ({self.campus!s})'


class PublicacaoAditivo(models.ModelPlus):
    aditivo = models.ForeignKeyPlus(Aditivo, related_name='publicacoes', on_delete=models.CASCADE)
    tipo = models.ForeignKeyPlus(TipoPublicacao, on_delete=models.CASCADE)
    numero = models.CharFieldPlus('Número', max_length=50)
    data = models.DateFieldPlus('Data da Publicação')
    descricao = models.CharFieldPlus('Descrição', max_length=255, help_text='Breve descrição sobre o conteúdo da publicação')
    arquivo = models.OneToOneField(Arquivo, null=True, on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Publicação'
        verbose_name_plural = 'Publicações'

    def __str__(self):
        return f'{self.tipo} {self.descricao}'

    def delete(self, *args, **kwargs):
        arquivo = self.arquivo
        super().delete(*args, **kwargs)
        if arquivo:
            arquivo.delete()


class Cronograma(models.ModelPlus):
    numero = models.CharFieldPlus('Número do Cronograma', max_length=50, null=False)
    nl = models.CharFieldPlus('NL', help_text='Nota de Lançamento', max_length=25, null=True)
    rc = models.CharFieldPlus('RC', max_length=25, help_text='Registro de Contrato', null=True)
    contrato = models.ForeignKeyPlus(Contrato, on_delete=models.CASCADE, related_name='cronogramas')

    class Meta:
        verbose_name = 'Cronograma'
        verbose_name_plural = 'Cronogramas'

    def __str__(self):
        return f'{self.numero}'

    def get_parcelas(self):
        return self.parcelas.order_by('data_prevista_inicio')

    def adicionar_parcela(self, parcela):
        parcela.cronograma = self
        # if self.contrato.get_saldo_contrato() < parcela.valor_previsto:
        parcela.save()
        return parcela

    def delete(self, *args, **kwargs):
        contrato = self.contrato
        super().delete(*args, **kwargs)
        contrato.save()


class Parcela(models.ModelPlus):
    cronograma = models.ForeignKeyPlus(Cronograma, related_name='parcelas', on_delete=models.CASCADE)
    data_prevista_inicio = models.DateField(verbose_name='Data Prevista Início')
    data_prevista_fim = models.DateField(verbose_name='Data Prevista Conclusão')
    valor_previsto = models.DecimalField(decimal_places=2, max_digits=12)
    sem_medicao = models.BooleanField(verbose_name='Parcela Sem Medição', null=True)

    class Meta:
        verbose_name = 'Parcela de Contrato'
        verbose_name_plural = 'Parcelas de Contrato'

    def __str__(self):
        return str(self.valor_previsto)

    def pode_ser_excluida(self):
        return not self.is_medida()

    def valor_executado_parcela(self):
        return self.medicoes.aggregate(valor_executado_parcela=Sum('valor_executado'))['valor_executado_parcela']

    def is_medida(self):
        return self.medicoes.exists()

    def is_not_medida(self):
        return not self.is_medida()

    def get_imrs_pendentes(self):
        return self.imrs.filter(medicoes_imr__isnull=True).order_by('campus')

    def get_medicoes(self, uo=None):
        if uo:
            return self.medicoes.filter(campus=uo)
        else:
            return self.medicoes.all()

    @classmethod
    def get_parcelas_nao_medidas(cls, uo=None):
        # por questão de peformance, apenas as parcelas dos três ultimos meses serão levados em consideracao
        parcelas = (
            Parcela.objects.filter(data_prevista_fim__lt=datetime.today())
            .filter(data_prevista_fim__gt=somar_dias(datetime.today(), -90))
            .filter(cronograma__contrato__concluido=False)
            .filter(cronograma__contrato__cancelado=False)
            .filter(medicoes__isnull=True)
            .order_by('data_prevista_inicio')
        )

        if uo:
            parcelas = parcelas.filter(cronograma__contrato__campi=uo)
        return parcelas

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.cronograma.contrato.save()

    def delete(self, *args, **kwargs):
        contrato = self.cronograma.contrato
        super().delete(*args, **kwargs)
        contrato.save()


class IMR(models.ModelPlus):
    parcela = models.ForeignKeyPlus(Parcela, verbose_name='Parcela', on_delete=models.CASCADE, related_name='imrs')
    campus = models.ForeignKeyPlus(UnidadeOrganizacional, verbose_name=nomenclatura.campus, on_delete=models.CASCADE)
    fiscal = models.ForeignKeyPlus(Fiscal, verbose_name='Fiscal', null=True, on_delete=models.SET_NULL)
    percentual = models.PositiveIntegerFieldPlus(verbose_name='Percentual')
    arquivo = models.FileFieldPlus(verbose_name='Documento', upload_to='contratos/imr/')

    class Meta:
        verbose_name = 'Instrumento de Medição de Resultado (IMR)'
        verbose_name_plural = 'Instrumento de Medição de Resultados (IMRs)'

    def __str__(self):
        return f'IMR: {self.percentual}% - Parcela: {self.parcela} - {nomenclatura.campus}: {self.campus}'


class Medicao(models.ModelPlus):
    PADRAO_TABELA_CONTA_VINCULADA_TERMO_DEFINITIVO = r'<div class="conta-vinculada-medicao".*?</div>\s*'
    PADRAO_TITULO_VALOR_FINAL_NOTA_IMR = r'2\s*-\s*VALOR FINAL DA NOTA APLICANDO O IMR'
    PADRAO_TITULO_DECLARACAO_RECEBIMENTO_DEFINITIVO = r'DECLARA(?:Ç|C)[AÃ]O DE RECEBIMENTO DEFINITIVO'

    parcela = models.ForeignKeyPlus(Parcela, verbose_name='Parcela', related_name='medicoes', on_delete=models.CASCADE)
    data_inicio = models.DateField(verbose_name='Data Efetiva de Início', null=False)
    data_fim = models.DateField(verbose_name='Data Efetiva de Término', null=False)
    data_medicao = models.DateField(verbose_name='Data da Medição', null=False)
    numero_documento = models.CharField(max_length=50, verbose_name='Nº do Documento', null=False)
    valor_executado = models.DecimalField(verbose_name='Valor Executado (R$)', decimal_places=2, max_digits=12, null=False)
    fiscal = models.ForeignKeyPlus(Fiscal, verbose_name='Fiscal', null=False, on_delete=models.CASCADE)
    ocorrencia = models.TextField(max_length=500, verbose_name='Ocorrência(s)', null=False)
    providencia = models.TextField(max_length=500, verbose_name='Providência(s)', null=True)
    arquivo = models.OneToOneField(Arquivo, verbose_name='Arquivo', null=True, on_delete=models.CASCADE)
    processo = models.ForeignKeyPlus(Processo, null=True, verbose_name='Processo', on_delete=models.PROTECT)
    numero_processo = models.CharField('Nº do Processo', max_length=30, null=True, blank=True)
    despacho_documentotexto = models.ForeignKeyPlus(
        'documento_eletronico.DocumentoTexto',
        null=True,
        on_delete=models.PROTECT,
        related_name='medicoes_despacho',
        verbose_name='Despacho - Documento Eletrônico',
    )
    termo_definitivo_documentotexto = models.ForeignKeyPlus(
        'documento_eletronico.DocumentoTexto',
        null=True,
        on_delete=models.PROTECT,
        related_name='medicoes_termo_definitivo',
        verbose_name='Termo de Recebimento Definitivo - Documento Eletrônico',
    )
    campus = models.ForeignKeyPlus(UnidadeOrganizacional, verbose_name=nomenclatura.campus, null=True, blank=True, on_delete=models.CASCADE)
    historico_medicao = models.TextField(verbose_name='Histórico da Medição', null=False, editable=False)
    documentos_empenho_contrato = models.ManyToManyField('DocumentoEmpenhoContrato', through='DocumentoEmpenhoContratoMedicao')
    imr = models.OneToOneField(IMR, verbose_name='IMR', related_name='medicoes_imr', null=True, on_delete=models.SET_NULL)

    class Meta:
        verbose_name = 'Medição'
        verbose_name_plural = 'Medições'

    def save(self, *args, **kwargs):
        is_insert = self.pk is None

        # Rotina que gera o histórico de medição.
        historico_medicao_list = []
        historico_medicao_item = {}
        historico_medicao_item['data_hora_registro'] = format_(datetime.now(), html=False)
        historico_medicao_item['usuario_registro'] = str(self.fiscal)
        if is_insert:
            historico_medicao_item['registro'] = {'Registro': 'Registro criado.'}
            historico_medicao_list.append(historico_medicao_item)
            self.historico_medicao = json.dumps(historico_medicao_list, indent=4)
        else:
            historico_medicao_diff = compare_model_objects(
                model_object_old=Medicao.objects.get(pk=self.pk),
                model_object_new=self,
                use_verbose_name_as_key=True,
                atts_to_ignore=[
                    'Histórico da Medição',
                ],
            )
            # Se a diferenças entre o objeto no banco e o objeto atual...
            if historico_medicao_diff:
                if 'Arquivo' in historico_medicao_diff:
                    historico_medicao_diff['Arquivo'] = 'Arquivo alterado.'
                historico_medicao_item['registro'] = historico_medicao_diff
                historico_medicao_list.append(historico_medicao_item)
                # Se já existe algo no histórico, ele será adicionado a lista pra manter
                # o histórico completo. O registro no topo será o mais recente.
                if self.historico_medicao:
                    historico_medicao_list.extend(json.loads(self.historico_medicao))
                # "ensure_ascii=False" faz com que o registro possa se guardado com os acentos.
                self.historico_medicao = json.dumps(historico_medicao_list, indent=4, ensure_ascii=False)

        super().save(*args, **kwargs)
        self.parcela.cronograma.contrato.save()

    def delete(self, *args, **kwargs):
        contrato = self.parcela.cronograma.contrato
        super().delete(*args, **kwargs)
        contrato.save()

    def recebimento_provisorio_emitido(self) -> bool:
        documento = self.despacho_documentotexto
        return bool(documento and (documento.estah_assinado or documento.estah_finalizado))

    def pode_ser_recebida_definitivamente(self) -> bool:
        if not self.recebimento_provisorio_emitido() or not self.usa_fluxo_recebimento_definitivo_com_documentos():
            return False
        return bool(self.get_documentos_comprobatorios_para_recebimento_definitivo().exists() and self.termo_definitivo_permite_atualizacao())

    def foi_recebida_definitivamente(self):
        if not self.usa_fluxo_recebimento_definitivo_com_documentos():
            return bool(self.termo_definitivo_documentotexto)
        documentos = self.get_documentos_comprobatorios_para_recebimento_definitivo()
        return bool(
            documentos.exists()
            and not documentos.filter(
                Q(recebido_gerente__isnull=True) | Q(recebido_gerente='') | Q(recebido_gerente=MedicaoTipoDocumentoComprobatorio.PENDENTE)
            ).exists()
        )

    def pode_gerar_termo_definitivo(self) -> bool:
        if not self.recebimento_provisorio_emitido():
            return False
        if not self.usa_fluxo_recebimento_definitivo_com_documentos():
            return self.termo_definitivo_permite_atualizacao()
        return bool(self.foi_recebida_definitivamente() and self.termo_definitivo_permite_atualizacao())

    def termo_definitivo_permite_atualizacao(self):
        documento = self.termo_definitivo_documentotexto
        return not bool(documento and (documento.estah_aguardando_assinatura or documento.estah_assinado or documento.estah_finalizado))

    def recebimento_definitivo_iniciado(self):
        if not self.usa_fluxo_recebimento_definitivo_com_documentos():
            return bool(self.termo_definitivo_documentotexto)
        return bool(self.documentos_comprobatorios.filter(data_avaliacao__isnull=False).exists() or self.conta_vinculada_calculos.exists())

    def usa_fluxo_recebimento_definitivo_com_documentos(self) -> bool:
        contrato = self.parcela.cronograma.contrato
        if ContratoTipoDocumentoComprobatorio.objects.filter(contrato=contrato).exists():
            return True
        return bool(self.documentos_comprobatorios.exists())

    def sincronizar_documentos_comprobatorios_com_contrato(self):
        if not self.usa_fluxo_recebimento_definitivo_com_documentos():
            return

        tipos_ids_contrato = list(
            ContratoTipoDocumentoComprobatorio.objects.filter(contrato=self.parcela.cronograma.contrato).values_list(
                'tipo_documento_comprobatorio_id', flat=True
            )
        )
        tipos_ids_medicao = set(self.documentos_comprobatorios.values_list('tipo_documento_comprobatorio_id', flat=True))

        for tipo_id in tipos_ids_contrato:
            if tipo_id in tipos_ids_medicao:
                continue
            MedicaoTipoDocumentoComprobatorio.objects.get_or_create(
                medicao=self,
                tipo_documento_comprobatorio_id=tipo_id,
                defaults={'confirmacao_fiscal': MedicaoTipoDocumentoComprobatorio.NAO_SE_APLICA},
            )

    def get_documentos_comprobatorios_para_recebimento_definitivo(self):
        # O gestor deve reconfirmar todos os documentos informados pelo fiscal,
        # inclusive os marcados como "Não se aplica".
        Medicao.sincronizar_documentos_comprobatorios_com_contrato(self)
        return self.documentos_comprobatorios.all()

    @staticmethod
    def montar_tabela_documentos_comprobatorios(docs_medicao, titulo_coluna_status, status_getter, mensagem_vazia):
        documentos = list(docs_medicao)
        tabela_documentos_comprobatorios = f"""<table border="1" style="border:1px solid #000000; width:100%">
    <tbody>
        <tr>
            <td rowspan="1" style="background-color:#7f7f7f">
            <p style="text-align:left"><span style="color:#ffffff"><span style="font-family:Calibri,serif"><span style="font-size:small"><strong>ITENS (Cadastrados pelo Gestor)</strong></span></span></span></p>
            </td>
            <td colspan="1" style="background-color:#7f7f7f">
            <p style="text-align:center"><span style="color:#ffffff"><span style="font-family:Calibri,serif"><span style="font-size:small"><strong>{titulo_coluna_status}</strong></span></span></span></p>
            </td>
        </tr>
    """
        if documentos:
            for doc in documentos:
                tabela_documentos_comprobatorios += (
                    f'<tr><td>{doc.tipo_documento_comprobatorio.descricao}</td><td><p style="text-align:center">{status_getter(doc)}</p></td></tr>'
                )
        else:
            tabela_documentos_comprobatorios += f'<tr><td colspan="2">{mensagem_vazia}</td></tr>'
        tabela_documentos_comprobatorios += '</tbody></table>'
        return tabela_documentos_comprobatorios

    def limpar_conta_vinculada_recebimento_definitivo(self):
        self.conta_vinculada_calculos.all().delete()
        self.movimentacoes_conta.filter(deposito=True).delete()

    def remover_lancamento_conta_vinculada_recebimento_definitivo(self):
        self.movimentacoes_conta.filter(deposito=True).delete()

    def registrar_estorno_conta_vinculada_por_exclusao(self, fiscal=None, servidor=None):
        movimentacoes = list(self.movimentacoes_conta.select_related('conta').order_by('id'))
        if not movimentacoes:
            return 0

        for movimentacao in movimentacoes:
            if movimentacao.deposito:
                deposito = False
                operacao = 'Estorno de depósito'
            else:
                deposito = True
                operacao = 'Estorno de saque'

            referencia = self.numero_documento or f'medição {self.pk}'
            observacao = (
                f'{operacao} gerado automaticamente pela exclusão da medição {referencia} '
                f'({self.data_inicio.strftime("%d/%m/%Y")} a {self.data_fim.strftime("%d/%m/%Y")}).'
            )
            MovimentacaoContaContrato.objects.create(
                conta=movimentacao.conta,
                medicao=None,
                deposito=deposito,
                valor=movimentacao.valor,
                data=date.today(),
                fiscal=fiscal or movimentacao.fiscal,
                servidor=servidor or movimentacao.servidor,
                observacao=observacao,
            )

        return len(movimentacoes)

    def get_ultimo_calculo_conta_vinculada(self):
        return self.conta_vinculada_calculos.prefetch_related('itens__maodeobra').order_by('-data_criacao', '-id').first()

    def get_calculos_conta_vinculada(self):
        return (
            self.conta_vinculada_calculos.select_related('usuario', 'medicao__processo')
            .prefetch_related('itens__maodeobra', 'medicao__movimentacoes_conta__conta')
            .order_by('-data_criacao', '-id')
        )

    @property
    def tabela_conta_vinculada_termo_definitivo_html(self):
        calculo = self.get_ultimo_calculo_conta_vinculada()
        if not calculo:
            return ''

        movimentacao = self.movimentacoes_conta.filter(deposito=True).order_by('-data', '-id').first()
        itens = [
            {
                'trabalhador': str(item.maodeobra) if item.maodeobra else 'Trabalhador não identificado',
                'salario': format_money(item.salario or Decimal('0.00')),
                'valor_13': format_money(item.valor_13 or Decimal('0.00')),
                'valor_ferias': format_money(item.valor_ferias or Decimal('0.00')),
                'valor_fgts': format_money(item.valor_fgts or Decimal('0.00')),
                'valor_submodulo': format_money(item.valor_submodulo or Decimal('0.00')),
                'total_item': format_money(item.total_item or Decimal('0.00')),
            }
            for item in calculo.itens.all()
        ]
        contexto = {
            'itens': itens,
            'movimentacao': movimentacao,
            'valor_total': format_money(calculo.valor_total or Decimal('0.00')),
        }
        return render_to_string('includes/conta_vinculada_termo_definitivo.html', contexto)

    @staticmethod
    def _indice_texto_visivel_html(html, padrao, inicio=0):
        texto_visivel = []
        mapa_indices = []
        indice = 0
        tamanho = len(html)

        while indice < tamanho:
            caractere = html[indice]
            if caractere == '<':
                fim_tag = html.find('>', indice + 1)
                if fim_tag == -1:
                    indice += 1
                else:
                    indice = fim_tag + 1
                continue
            if caractere == '&':
                fim_entidade = html.find(';', indice + 1)
                if fim_entidade != -1:
                    entidade = html[indice : fim_entidade + 1]
                    texto_entidade = html_unescape(entidade)
                    if texto_entidade != entidade:
                        for caractere_entidade in texto_entidade:
                            texto_visivel.append(caractere_entidade)
                            mapa_indices.append(indice)
                        indice = fim_entidade + 1
                        continue
            texto_visivel.append(caractere)
            mapa_indices.append(indice)
            indice += 1

        texto_visivel = ''.join(texto_visivel)
        posicao_inicio = 0
        for posicao, indice_html in enumerate(mapa_indices):
            if indice_html >= inicio:
                posicao_inicio = posicao
                break
        else:
            return None

        match = re.search(padrao, texto_visivel[posicao_inicio:], flags=re.IGNORECASE)
        if not match:
            return None
        return mapa_indices[posicao_inicio + match.start()]

    @staticmethod
    def _inicio_bloco_html(html, posicao):
        tabela_aberta = html.rfind('<table', 0, posicao)
        tabela_fechada = html.rfind('</table', 0, posicao)
        if tabela_aberta > tabela_fechada:
            return tabela_aberta

        for padrao in (r'<p\b', r'<h[1-6]\b'):
            matches = list(re.finditer(padrao, html[:posicao], flags=re.IGNORECASE))
            if matches:
                return matches[-1].start()
        return posicao

    @staticmethod
    def _fim_bloco_html(html, posicao):
        tabela_aberta = html.rfind('<table', 0, posicao)
        tabela_fechada = html.rfind('</table', 0, posicao)
        if tabela_aberta > tabela_fechada:
            fim_tabela = html.find('</table>', posicao)
            if fim_tabela != -1:
                return fim_tabela + len('</table>')

        match = re.search(r'</(?:p|h[1-6])>', html[posicao:], flags=re.IGNORECASE)
        if match:
            return posicao + match.end()
        return posicao

    @classmethod
    def posicionar_tabela_conta_vinculada_termo_definitivo(cls, corpo, tabela_conta_vinculada):
        corpo = re.sub(cls.PADRAO_TABELA_CONTA_VINCULADA_TERMO_DEFINITIVO, '', corpo or '', flags=re.DOTALL)
        if not tabela_conta_vinculada:
            return corpo

        posicao_quadro_valor_final = cls._indice_texto_visivel_html(corpo, cls.PADRAO_TITULO_VALOR_FINAL_NOTA_IMR)
        posicao_declaracao = cls._indice_texto_visivel_html(
            corpo,
            cls.PADRAO_TITULO_DECLARACAO_RECEBIMENTO_DEFINITIVO,
            inicio=posicao_quadro_valor_final or 0,
        )
        if posicao_declaracao is not None:
            posicao_insercao = cls._inicio_bloco_html(corpo, posicao_declaracao)
            return f'{corpo[:posicao_insercao]}{tabela_conta_vinculada}{corpo[posicao_insercao:]}'

        if posicao_quadro_valor_final is not None:
            posicao_insercao = cls._fim_bloco_html(corpo, posicao_quadro_valor_final)
            return f'{corpo[:posicao_insercao]}{tabela_conta_vinculada}{corpo[posicao_insercao:]}'

        return f'{corpo}{tabela_conta_vinculada}'

    def atualizar_tabela_conta_vinculada_termo_definitivo_documento(self, documento: DocumentoTexto) -> None:
        tabela_conta_vinculada = self.tabela_conta_vinculada_termo_definitivo_html or ''
        corpo_atual = self.posicionar_tabela_conta_vinculada_termo_definitivo(documento.corpo or '', tabela_conta_vinculada)

        documento.corpo = corpo_atual

    def get_update_url(self):
        return f'/contratos/atualizar_medicao/{self.id}/{self.parcela.cronograma.contrato.id}'

    @staticmethod
    def _carregar_overrides_conta_vinculada(per_item_overrides):
        if not per_item_overrides:
            return {}
        try:
            if isinstance(per_item_overrides, str):
                return json.loads(per_item_overrides)
            return per_item_overrides
        except Exception:
            return {}

    @staticmethod
    def _calcular_item_conta_vinculada(maodeobra, percentuais):
        salario = ContaVinculadaCalculo.to_decimal(
            getattr(maodeobra, 'salario_bruto', None) or getattr(maodeobra, 'valor_total_das_verbas', None) or 0
        )
        valor_13 = (salario * percentuais['perc_13']).quantize(Decimal('0.01'))
        valor_ferias = (salario * percentuais['perc_ferias']).quantize(Decimal('0.01'))
        valor_fgts = (salario * percentuais['perc_fgts']).quantize(Decimal('0.01'))
        valor_sub = (salario * percentuais['perc_submodulo']).quantize(Decimal('0.01'))
        total_item = (valor_13 + valor_ferias + valor_fgts + valor_sub).quantize(Decimal('0.01'))
        return {
            'maodeobra_id': maodeobra.id,
            'maodeobra_str': str(maodeobra),
            'salario': str(salario),
            'valor_13': str(valor_13),
            'valor_ferias': str(valor_ferias),
            'valor_fgts': str(valor_fgts),
            'valor_submodulo': str(valor_sub),
            'total_item': str(total_item),
        }

    @staticmethod
    def _aplicar_override_isencao_conta_vinculada(item):
        for campo in ('valor_13', 'valor_ferias', 'valor_fgts', 'valor_submodulo', 'total_item'):
            item[campo] = str(Decimal('0.00'))
        return item

    @staticmethod
    def _aplicar_override_valores_conta_vinculada(item, override, percentuais):
        salario = ContaVinculadaCalculo.to_decimal(override.get('salario', item['salario']))
        item['salario'] = str(salario)
        if override.get('modo') == 'base':
            valores = {
                'valor_13': (salario * percentuais['perc_13']).quantize(Decimal('0.01')),
                'valor_ferias': (salario * percentuais['perc_ferias']).quantize(Decimal('0.01')),
                'valor_fgts': (salario * percentuais['perc_fgts']).quantize(Decimal('0.01')),
                'valor_submodulo': (salario * percentuais['perc_submodulo']).quantize(Decimal('0.01')),
            }
        else:
            valores = {
                'valor_13': ContaVinculadaCalculo.to_decimal(override.get('valor_13', item['valor_13'])),
                'valor_ferias': ContaVinculadaCalculo.to_decimal(override.get('valor_ferias', item['valor_ferias'])),
                'valor_fgts': ContaVinculadaCalculo.to_decimal(override.get('valor_fgts', item['valor_fgts'])),
                'valor_submodulo': ContaVinculadaCalculo.to_decimal(override.get('valor_submodulo', item['valor_submodulo'])),
            }
        total_item = sum(valores.values(), Decimal('0.00')).quantize(Decimal('0.01'))
        for campo, valor in valores.items():
            item[campo] = str(valor)
        item['total_item'] = str(total_item)
        return item

    @staticmethod
    def _aplicar_override_manual_conta_vinculada(item, override):
        manual_valor = override.get('manual_valor')
        if manual_valor is None:
            return item
        item['valor_manual'] = str(manual_valor)
        total_original = ContaVinculadaCalculo.to_decimal(item['total_item'])
        valor_manual = ContaVinculadaCalculo.to_decimal(manual_valor)
        if total_original <= 0:
            return item
        fator = (valor_manual / total_original).quantize(Decimal('0.0000001'))
        for campo in ('valor_13', 'valor_ferias', 'valor_fgts', 'valor_submodulo'):
            item[campo] = str((ContaVinculadaCalculo.to_decimal(item[campo]) * fator).quantize(Decimal('0.01')))
        total_item = sum(
            (ContaVinculadaCalculo.to_decimal(item[campo]) for campo in ('valor_13', 'valor_ferias', 'valor_fgts', 'valor_submodulo')),
            Decimal('0.00'),
        )
        total_item = total_item.quantize(Decimal('0.01'))
        diferenca = valor_manual - total_item
        item['total_item'] = str(total_item + diferenca if diferenca else total_item)
        return item

    @classmethod
    def _aplicar_override_item_conta_vinculada(cls, item, override, percentuais):
        item['modo'] = override.get('modo') or override.get('tipo') or 'automatico'
        item['tipo'] = override.get('tipo') or ('manual' if item['modo'] in ('base', 'manual') else 'automatico')
        item['justificativa'] = override.get('justificativa')
        if item['tipo'] == 'isento':
            return cls._aplicar_override_isencao_conta_vinculada(item)
        if any(chave in override for chave in ('salario', 'valor_13', 'valor_ferias', 'valor_fgts', 'valor_submodulo')):
            return cls._aplicar_override_valores_conta_vinculada(item, override, percentuais)
        if item['tipo'] == 'manual':
            return cls._aplicar_override_manual_conta_vinculada(item, override)
        return item

    def _persistir_calculo_conta_vinculada(self, resultado, contrato, usuario, tipo, justificativa):
        with transaction.atomic():
            self.conta_vinculada_calculos.all().delete()
            calculo = ContaVinculadaCalculo.objects.create(
                medicao=self,
                contrato=contrato,
                usuario=usuario,
                tipo=tipo,
                valor_total=ContaVinculadaCalculo.to_decimal(resultado['totais']['valor_total']),
                justificativa=justificativa,
                dados_json=resultado,
            )
            for item in resultado['itens']:
                ContaVinculadaCalculoItem.objects.create(
                    calculo=calculo,
                    maodeobra_id=item['maodeobra_id'],
                    salario=ContaVinculadaCalculo.to_decimal(item['salario']),
                    valor_13=ContaVinculadaCalculo.to_decimal(item['valor_13']),
                    valor_ferias=ContaVinculadaCalculo.to_decimal(item['valor_ferias']),
                    valor_fgts=ContaVinculadaCalculo.to_decimal(item['valor_fgts']),
                    valor_submodulo=ContaVinculadaCalculo.to_decimal(item['valor_submodulo']),
                    total_item=ContaVinculadaCalculo.to_decimal(item['total_item']),
                    tipo=item.get('tipo', 'automatico'),
                    justificativa=item.get('justificativa'),
                )
        return calculo

    def calcular_conta_vinculada(
        self, maosdeobra_ids=None, usuario=None, tipo='automatico', persist=False, justificativa=None, manual_valor=None, per_item_overrides=None
    ):
        """
        Calcula os valores para conta vinculada por mão de obra desta medição.

        - maosdeobra_ids: lista de ids de `MaoDeObra` para incluir (None = todas do contrato)
        - usuario: usuário que solicita o cálculo (opcional, usado ao persistir)
        - tipo: 'automatico'|'manual'|'isento'
        - persist: se True, cria `ContaVinculadaCalculo` e `ContaVinculadaCalculoItem` associados
        - justificativa: texto opcional armazenado quando persist=True

        Retorna dicionário com itens e totais.
        """
        contrato = self.parcela.cronograma.contrato

        maos = contrato.maosdeobra.all()
        if maosdeobra_ids is not None:
            maos = maos.filter(id__in=maosdeobra_ids)
        percentuais = ContaVinculadaCalculo.obter_percentuais_para_contrato(contrato)
        itens = [Medicao._calcular_item_conta_vinculada(maodeobra, percentuais) for maodeobra in maos]
        total_geral = sum((ContaVinculadaCalculo.to_decimal(item['total_item']) for item in itens), Decimal('0.00'))

        resultado = {
            'itens': itens,
            'totais': {'valor_total': str(total_geral), 'quantidade_itens': len(itens)},
            'percentuais': {
                'perc_13': str(percentuais['perc_13']),
                'perc_ferias': str(percentuais['perc_ferias']),
                'perc_fgts': str(percentuais['perc_fgts']),
                'perc_submodulo': str(percentuais['perc_submodulo']),
                'grau_risco': percentuais['grau_risco'],
            },
        }
        overrides = Medicao._carregar_overrides_conta_vinculada(per_item_overrides)
        novo_total = Decimal('0.00')
        itens_ajustados = []
        for item in resultado['itens']:
            item.setdefault('tipo', 'automatico')
            item.setdefault('modo', 'automatico')
            item.setdefault('justificativa', None)
            override = overrides.get(str(item['maodeobra_id']))
            if isinstance(override, dict):
                item = Medicao._aplicar_override_item_conta_vinculada(item, override, percentuais)
            novo_total += ContaVinculadaCalculo.to_decimal(item['total_item'])
            itens_ajustados.append(item)

        resultado['itens'] = itens_ajustados
        resultado['totais']['valor_total'] = str(novo_total)

        if persist:
            calculo = self._persistir_calculo_conta_vinculada(resultado, contrato, usuario, tipo, justificativa)
            resultado['persistido'] = {'calculo_id': calculo.id}

        return resultado


class MedicaoEletrica(models.ModelPlus):
    medicao = models.OneToOneFieldPlus(Medicao, null=False, unique=True)
    mes_referencia = models.PositiveIntegerFieldPlus('Mês de Referência', choices=Meses.get_choices(), null=False)
    ano_referencia = models.PositiveIntegerFieldPlus('Ano de Referência', null=False)
    consumo_ponta = models.DecimalFieldPlus('Consumo Ponta(kWh)', null=True, max_digits=12, decimal_places=0)
    consumo_fora_ponta = models.DecimalFieldPlus('Consumo Fora de Ponta(kWh)', null=True, blank=False, max_digits=12, decimal_places=0)
    demanda_contratada = models.DecimalFieldPlus('Demanda Contratada(kW)', null=True, blank=True, max_digits=12, decimal_places=0)
    demanda_medida = models.DecimalFieldPlus('Demanda Medida(kW)', null=True, blank=True, max_digits=12, decimal_places=0)
    valor_multa_excedente = models.DecimalFieldPlus('Valor da Multa por Ultrapassagem', default=Decimal('0.0'), null=True, blank=True)

    class Meta:
        verbose_name = 'Medição Elétrica'
        verbose_name_plural = 'Medições Elétricas'

    @property
    def demanda_ultrapassada(self):
        return self.demanda_medida - self.demanda_contratada

    @property
    def percentual_ultrapassado(self):
        return ((self.demanda_medida / self.demanda_contratada) * 100) - 100

    def deve_solicitar_valor_multa(self):
        """
        Verifica se a demanda medida (kW) supera em 5% a demanda contratada (kW)
        """
        return bool(self.demanda_medida and self.demanda_contratada and float(self.demanda_medida) > float(self.demanda_contratada) * 1.05)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.medicao.save()

    def delete(self, *args, **kwargs):
        medicao = self.medicao
        super().delete(*args, **kwargs)
        medicao.save()


def anexo_resposta_ocorrencia_path(instance, filename):
    filename = formata_nome_arquivo(filename)
    return f'contratos/contrato/{instance.contrato.id:d}/ocorrencia/resposta_{instance.id:d}{filename}'


class Ocorrencia(models.ModelPlus):
    data = models.DateTimeField(null=False, auto_now=True)
    contrato = models.ForeignKeyPlus(Contrato, null=False, on_delete=models.CASCADE, related_name='ocorrencias')
    fiscal = models.ForeignKeyPlus(Fiscal, null=True, on_delete=models.CASCADE)
    servidor = models.ForeignKeyPlus(Servidor, null=True, on_delete=models.CASCADE)
    descricao = models.TextField(max_length=1024, verbose_name='Descrição', null=False, blank=False)
    campus = models.ForeignKeyPlus(UnidadeOrganizacional, verbose_name=nomenclatura.campus, null=True, blank=True, on_delete=models.CASCADE)
    arquivo = models.OneToOneField(Arquivo, null=True, on_delete=models.CASCADE)
    prazo_resolucao = models.DateField('Prazo para Resolução', null=True)
    situacao = models.CharField('Situação', max_length=3, choices=SituacaoOcorrencia.SITUACAO_CHOICES, null=True, blank=True)
    anexo_resposta = models.FileFieldPlus(upload_to=anexo_resposta_ocorrencia_path, null=True)
    notificacao_enviada = models.BooleanField(verbose_name='Notificação Enviada?', default=False)

    class Meta:
        verbose_name = 'Ocorrência'
        verbose_name_plural = 'Ocorrências'

    def get_texto_notificacao(self):
        url = f'{settings.SITE_URL}{self.contrato.get_absolute_url()}'
        texto = f"""
            <h1>Notificação de Ocorrência</h1>
            <dl>
                <dt>Descrição da Ocorrência:</dt><dd>{linebreaksbr(self.descricao)}</dd>
            </dl>
            <p class="more-info">Para mais informações, acesse: <a href="{url}">{url}</a></p>
        """
        return texto

    def get_emails_notificar(self):
        emails = [fiscal.servidor.email_institucional for fiscal in self.contrato.get_fiscais_atuais()]
        emails.append(self.contrato.vinculo_contratado.email_notificacao)
        return emails

    def notificar(self):
        titulo = '[SUAP] Contratos: Notificação de Ocorrência'
        emails = self.get_emails_notificar()
        send_mail(titulo, self.get_texto_notificacao(), settings.DEFAULT_FROM_EMAIL, emails)


class TipoDocumentoComprobatorio(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição')
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Tipo de Documento Comprobatório para Medição'
        verbose_name_plural = 'Tipos de Documentos Comprobatórios para Medição'

    def __str__(self):
        return self.descricao


class ContratoTipoDocumentoComprobatorio(models.ModelPlus):
    contrato = models.ForeignKeyPlus(Contrato, null=False, blank=False, on_delete=models.CASCADE)
    tipo_documento_comprobatorio = models.ForeignKeyPlus(TipoDocumentoComprobatorio, null=False, blank=False, on_delete=models.PROTECT)

    class Meta:
        verbose_name = 'Tipo de Documento Comprobatório do Contrato'
        verbose_name_plural = 'Tipos de Documentos Comprobatórios do Contrato'

    def __str__(self):
        return self.contrato.numero + ' - ' + self.tipo_documento_comprobatorio.descricao


class MedicaoTipoDocumentoComprobatorio(models.ModelPlus):
    CONFIRMADO = 1
    NAO_SE_APLICA = 2
    RECEBIDO = 'Recebido'
    PENDENTE = 'Pendente'
    NAO_SE_APLICA_GERENTE = 'NA'
    CONFIMACAO_FISCAL_CHOICES = [
        [CONFIRMADO, 'Sim'],
        [NAO_SE_APLICA, 'Não se aplica'],
    ]
    RECEBIMENTO_GERENTE_CHOICES = [
        (RECEBIDO, 'Recebido'),
        (PENDENTE, 'Pendente'),
        (NAO_SE_APLICA_GERENTE, 'Não se aplica'),
    ]

    medicao = models.ForeignKeyPlus(Medicao, null=False, blank=False, on_delete=models.CASCADE, related_name='documentos_comprobatorios')
    tipo_documento_comprobatorio = models.ForeignKeyPlus(TipoDocumentoComprobatorio, null=False, blank=False, on_delete=models.CASCADE)
    confirmado = models.BooleanField(default=False, verbose_name='Confirmado')
    confirmacao_fiscal = models.PositiveIntegerFieldPlus(
        null=True, blank=True, choices=CONFIMACAO_FISCAL_CHOICES, verbose_name='Incluído no Processo:'
    )
    recebido_gerente = models.CharField(null=True, blank=True, max_length=8, choices=RECEBIMENTO_GERENTE_CHOICES, verbose_name='Recebimento')
    parecer_gerente = models.CharField(null=True, blank=True, max_length=300, verbose_name='Descrição da Pendência')
    data_avaliacao = models.DateTimeField(null=True, blank=True, verbose_name='Data da Avaliação')
    avaliador_gerente = models.ForeignKeyPlus('comum.User', null=True, blank=True, verbose_name='Avaliador', on_delete=models.CASCADE)

    @property
    def confirmacao_fiscal_display(self):
        return self.CONFIMACAO_FISCAL_CHOICES[int(self.confirmacao_fiscal or 0) - 1][1]

    class Meta:
        verbose_name = 'Documento Comprobatório da Medição'
        verbose_name_plural = 'Documentos Comprobatórios da Medição'

    def __str__(self):
        return self.tipo_documento_comprobatorio.descricao


class ArrecadacaoReceita(models.ModelPlus):
    contrato = models.ForeignKeyPlus(Contrato, related_name='arrecadacao_receitas', on_delete=models.CASCADE)
    valor = models.DecimalFieldPlus()
    data = models.DateFieldPlus('Data da Concessão', db_column='data_inicio')
    mes_referencia = models.PositiveIntegerFieldPlus('Mês de Referência', choices=Meses.get_choices(), null=True, blank=True)
    ano_referencia = models.PositiveIntegerFieldPlus('Ano de Referência', null=True, blank=True)

    class Meta:
        verbose_name = 'Arrecadação de Receita'
        verbose_name_plural = 'Arrecadação das Receitas'

    def __str__(self):
        return f'{self.contrato} : {self.valor}'


class ContaContrato(models.ModelPlus):
    contrato = models.ForeignKeyPlus(Contrato, verbose_name='Contrato', related_name='contas', on_delete=models.CASCADE)
    descricao = models.CharFieldPlus('Número')
    data_atualizacao = models.DateTimeFieldPlus('Data/Hora da Última Atualização', auto_now=True)
    fiscal = models.ForeignKeyPlus(Fiscal, verbose_name='Fiscal', null=True, on_delete=models.CASCADE)
    servidor = models.ForeignKeyPlus(
        Servidor,
        verbose_name='Servidor',
        null=True,
        on_delete=models.CASCADE,
        help_text='Servidor responsável pela conta do contrato (gerente de contrato ou coordenador de contrato sistêmico)',
    )
    ativa = models.BooleanField('Ativa?', default=True)

    class Meta:
        verbose_name = 'Conta'
        verbose_name_plural = 'Contas'
        ordering = ('-ativa', 'descricao')

    def __str__(self):
        return f'Conta Vinculada {self.descricao}'

    def get_saldo(self):
        saldo = 0
        for movimentacao in self.movimentacoes_conta.all():
            if movimentacao.deposito:
                saldo += Decimal(f'{float(movimentacao.valor):.2f}')
            else:
                saldo -= Decimal(f'{float(movimentacao.valor):.2f}')
        return saldo


class MovimentacaoContaContrato(models.ModelPlus):
    conta = models.ForeignKeyPlus(ContaContrato, verbose_name='Conta', null=False, on_delete=models.CASCADE, related_name='movimentacoes_conta')
    medicao = models.ForeignKeyPlus(Medicao, verbose_name='Medição', null=True, on_delete=models.CASCADE, related_name='movimentacoes_conta')
    deposito = models.BooleanField('É Depósito?', default=True)
    valor = models.CharFieldPlus('Valor')
    data = models.DateFieldPlus('Data')
    observacao = models.TextField('Observação', null=True, blank=True)
    fiscal = models.ForeignKeyPlus(Fiscal, verbose_name='Fiscal', null=True, on_delete=models.CASCADE)
    servidor = models.ForeignKeyPlus(
        Servidor,
        verbose_name='Servidor',
        null=True,
        on_delete=models.CASCADE,
        help_text='Servidor (gerente de contrato ou coordenador de contrato sistêmico)',
    )
    data_atualizacao = models.DateTimeFieldPlus('Data/Hora da Última Atualização', auto_now=True)
    processo_eletronico = models.ForeignKeyPlus('processo_eletronico.Processo', verbose_name='Processo Eletrônico', null=True, blank=False)

    class Meta:
        verbose_name = 'Movimentação em Conta'
        verbose_name_plural = 'Movimentações em Conta'
        ordering = ('-data', '-id')

    def __str__(self):
        return f'Movimentação em Conta do Contrato: {self.conta.contrato}'


class ContaVinculadaCalculo(models.ModelPlus):
    FONTE_PERCENTUAIS = 'Configuração do Módulo (Gestor Sistêmico)'
    PERCENTUAIS_PADRAO = {
        'conta_vinculada.perc_13': Decimal('8.333333'),
        'conta_vinculada.perc_ferias': Decimal('12.100000'),
        'conta_vinculada.perc_fgts': Decimal('4.0'),
        'conta_vinculada.perc_submodulo_grau1': Decimal('7.39'),
        'conta_vinculada.perc_submodulo_grau2': Decimal('7.60'),
        'conta_vinculada.perc_submodulo_grau3': Decimal('7.82'),
    }
    TIPOS = (
        ('automatico', 'Automático'),
        ('manual', 'Manual'),
        ('isento', 'Isento'),
    )

    medicao = models.ForeignKeyPlus(
        'Medicao', verbose_name='Medição', null=True, blank=True, on_delete=models.CASCADE, related_name='conta_vinculada_calculos'
    )
    contrato = models.ForeignKeyPlus(
        'Contrato', verbose_name='Contrato', null=True, blank=True, on_delete=models.CASCADE, related_name='conta_vinculada_calculos'
    )
    usuario = models.ForeignKeyPlus('comum.User', verbose_name='Usuário', null=True, blank=True, on_delete=models.SET_NULL)
    tipo = models.CharFieldPlus('Tipo', max_length=20, choices=TIPOS, default='automatico')
    valor_total = models.DecimalFieldPlus('Valor Total', null=True, blank=True)
    justificativa = models.TextField('Justificativa', null=True, blank=True)
    dados_json = models.JSONField('Dados do Cálculo', null=True, blank=True)
    data_criacao = models.DateTimeFieldPlus('Data de Criação', auto_now_add=True)

    class Meta:
        verbose_name = 'Cálculo de Conta Vinculada'
        verbose_name_plural = 'Cálculos de Conta Vinculada'

    def __str__(self):
        return f'Cálculo Conta Vinculada {self.pk} - Contrato: {self.contrato}'

    @staticmethod
    def to_decimal(value):
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal('0')

    @classmethod
    def obter_valor_decimal_configuracao(cls, chave, default):
        valor = Configuracao.get_valor_por_chave(app='contratos', chave=chave)
        if valor in (None, ''):
            return cls.to_decimal(default)
        return cls.to_decimal(valor)

    @classmethod
    def obter_percentuais_para_contrato(cls, contrato):
        grau_risco = int(getattr(contrato, 'grau_risco', None) or 1)
        percentuais = {
            'perc_13': cls.obter_valor_decimal_configuracao('conta_vinculada.perc_13', cls.PERCENTUAIS_PADRAO['conta_vinculada.perc_13']),
            'perc_ferias': cls.obter_valor_decimal_configuracao('conta_vinculada.perc_ferias', cls.PERCENTUAIS_PADRAO['conta_vinculada.perc_ferias']),
            'perc_fgts': cls.obter_valor_decimal_configuracao('conta_vinculada.perc_fgts', cls.PERCENTUAIS_PADRAO['conta_vinculada.perc_fgts']),
            'grau_risco': grau_risco,
        }
        chave_submodulo = f'conta_vinculada.perc_submodulo_grau{grau_risco}'
        percentuais['perc_submodulo'] = cls.obter_valor_decimal_configuracao(chave_submodulo, cls.PERCENTUAIS_PADRAO[chave_submodulo])
        for chave in ('perc_13', 'perc_ferias', 'perc_fgts', 'perc_submodulo'):
            if percentuais[chave] > 1:
                percentuais[chave] = percentuais[chave] / Decimal('100')
        return percentuais

    @classmethod
    def formatar_percentual_display(cls, valor):
        percentual = (cls.to_decimal(valor) * Decimal('100')).quantize(Decimal('0.01'))
        return f'{percentual}%'

    @property
    def percentuais_utilizados(self):
        return (self.dados_json or {}).get('percentuais') or {}

    @property
    def percentuais_utilizados_display(self):
        percentuais = self.percentuais_utilizados
        itens = []
        for chave, label in (
            ('perc_13', '13º'),
            ('perc_ferias', 'Férias'),
            ('perc_fgts', 'FGTS'),
            ('perc_submodulo', 'Submódulo 4.1'),
        ):
            valor = percentuais.get(chave)
            if valor in (None, ''):
                continue
            try:
                percentual = (Decimal(str(valor)) * Decimal('100')).quantize(Decimal('0.01'))
            except Exception:
                percentual = Decimal('0.00')
            itens.append(f'{label}: {str(percentual).replace(".", ",")}%')
        return ' | '.join(itens)

    @property
    def justificativa_display(self):
        justificativas_itens = []
        for item in self.itens.all():
            if item.justificativa and item.justificativa not in justificativas_itens:
                justificativas_itens.append(item.justificativa)
        if justificativas_itens:
            return ' | '.join(justificativas_itens)
        return self.justificativa or '-'

    @property
    def usuario_display(self):
        if self.usuario:
            try:
                return self.usuario.get_relacionamento() or self.usuario
            except Exception:
                return self.usuario
        return '-'

    @property
    def contas_relacionadas(self):
        if not self.medicao_id:
            return []

        contas = []
        vistos = set()
        for movimentacao in self.medicao.movimentacoes_conta.all():
            if not movimentacao.deposito or not movimentacao.conta_id or movimentacao.conta_id in vistos:
                continue
            vistos.add(movimentacao.conta_id)
            contas.append(movimentacao.conta)
        return contas

    @property
    def contas_relacionadas_display(self):
        contas = self.contas_relacionadas
        if not contas:
            return '-'
        return ' | '.join(str(conta.descricao) for conta in contas)


class ContaVinculadaCalculoItem(models.ModelPlus):
    calculo = models.ForeignKeyPlus(ContaVinculadaCalculo, verbose_name='Cálculo', related_name='itens', on_delete=models.CASCADE)
    maodeobra = models.ForeignKeyPlus('MaoDeObra', verbose_name='Mão de Obra', null=True, blank=True, on_delete=models.SET_NULL)
    salario = models.DecimalFieldPlus('Remuneração', null=True, blank=True)
    valor_13 = models.DecimalFieldPlus('13º', null=True, blank=True)
    valor_ferias = models.DecimalFieldPlus('Férias +1/3', null=True, blank=True)
    valor_fgts = models.DecimalFieldPlus('Multa FGTS', null=True, blank=True)
    valor_submodulo = models.DecimalFieldPlus('Submódulo', null=True, blank=True)
    total_item = models.DecimalFieldPlus('Total', null=True, blank=True)
    tipo = models.CharFieldPlus('Tipo', max_length=20, choices=ContaVinculadaCalculo.TIPOS, default='automatico')
    justificativa = models.TextField('Justificativa', null=True, blank=True)

    class Meta:
        verbose_name = 'Item de Cálculo de Conta Vinculada'
        verbose_name_plural = 'Itens de Cálculos de Conta Vinculada'

    def __str__(self):
        return f'Item Cálculo {self.pk} - {self.maodeobra}'


class DocumentoEmpenhoContrato(models.ModelPlus):
    SEARCH_FIELDS = ['empenho__numero', 'descricao']
    empenho = models.ForeignKeyPlus(DocumentoEmpenho, verbose_name='Empenhos')
    contrato = models.ForeignKeyPlus(Contrato, verbose_name='Contrato', related_name='documentos_empenho_contrato', on_delete=models.CASCADE)
    descricao = models.TextField('Descrição', blank=True)

    def __str__(self):
        return f'Empenho {self.empenho}'

    def get_ext_combo_template(self):
        return self.empenho.get_ext_combo_template()


class DocumentoEmpenhoContratoMedicao(models.ModelPlus):
    SEARCH_FIELDS = ['empenho__numero', 'descricao']
    documento_empenho_contrato = models.ForeignKeyPlus(DocumentoEmpenhoContrato, verbose_name='Nota de Empenho', on_delete=models.CASCADE)
    medicao = models.ForeignKeyPlus(Medicao, verbose_name='Medição', related_name='documentos_empenho_medicao')
    valor = models.DecimalFieldPlus('Valor')

    def __str__(self):
        return f'R$ {format_money(self.valor)} ({self.documento_empenho_contrato})'


class ItemContrato(models.ModelPlus):
    MATERIAL = 'material'
    SERVICO = 'servico'
    TIPO_CHOICES = [
        (MATERIAL, 'Material'),
        (SERVICO, 'Serviço'),
    ]

    numero_item = models.PositiveIntegerFieldPlus(null=True, blank=False)
    contrato = models.ForeignKeyPlus(Contrato, on_delete=models.CASCADE)
    descricao = models.CharFieldPlus(verbose_name='Descrição', null=True, blank=False)
    grupo = models.CharFieldPlus(max_length=100, null=True, blank=True)
    id_comprasgov = models.PositiveIntegerFieldPlus(null=True)
    quantidade = models.PositiveIntegerFieldPlus()
    tipo = models.CharFieldPlus(max_length=20, choices=TIPO_CHOICES, default='material')
    valor_total = models.DecimalFieldPlus()
    valor_unitario = models.DecimalFieldPlus('Valor Unitário')

    atualizado_por = models.ForeignKeyPlus(
        'comum.Vinculo', null=True, related_name='itens_contrato_atualizados', verbose_name='Atualizado Por', on_delete=models.CASCADE
    )
    atualizado_em = models.DateTimeField('Atualizado em', auto_now=True, null=True, blank=True)

    class Meta:
        verbose_name = 'Item de Contrato'
        verbose_name_plural = 'Itens de Contrato'
        constraints = [UniqueConstraint(fields=['contrato', 'id_comprasgov'], name='unique_contrato__and_id_comprasgov')]

    def __str__(self):
        return self.descricao


class PreConfiguracaoAgenda(models.ModelPlus):
    subtipo = models.ForeignKeyPlus('contratos.SubtipoContrato', verbose_name='Subtipo de contrato', on_delete=models.CASCADE, null=True, blank=True)
    gatilho = models.CharFieldPlus('Gatilho', max_length=3, choices=GatilhoAgenda.GATILHO_CHOICES, null=True, blank=True)
    acao = models.CharFieldPlus('Ação', max_length=600)
    prazo = models.PositiveSmallIntegerField('Prazo', help_text='Dias após início do contrato para execução da ação')
    recorrente = models.BooleanField('Recorrente?', default=False)

    class Meta:
        verbose_name = 'Pré-configuração de agenda'
        verbose_name_plural = 'Pré-configurações de agenda'

    def __str__(self):
        return self.get_gatilho_display()

    def gatilho_ou_subtipo(self):
        return self.get_gatilho_display() or self.subtipo


class Agenda(models.ModelPlus):
    contrato = models.ForeignKeyPlus('contratos.Contrato', related_name='agendas', verbose_name='Contrato', on_delete=models.CASCADE)
    descricao = models.CharFieldPlus('Descrição', max_length=600)
    pre_configuracao = models.ForeignKeyPlus(
        'contratos.PreConfiguracaoAgenda', verbose_name='Pré-configuração', on_delete=models.CASCADE, null=True, blank=True
    )
    data_prevista = models.DateFieldPlus('Data prevista')
    data_execucao = models.DateFieldPlus('Data de execução', null=True, blank=True)
    fiscais = models.ManyToManyField('contratos.Fiscal', verbose_name='Fiscais')

    class Meta:
        verbose_name = 'Agenda'
        verbose_name_plural = 'Agendas'
        ordering = ('contrato', 'data_prevista')

    def __str__(self):
        return self.descricao


class AnexoAgenda(models.ModelPlus):
    agenda = models.ForeignKeyPlus('contratos.Agenda', related_name='anexos', on_delete=models.CASCADE)
    arquivo = models.FileFieldPlus(verbose_name='Arquivo', upload_to='contratos/anexoagenda/')
    data = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Anexo da agenda'
        verbose_name_plural = 'Anexos da agenda'
