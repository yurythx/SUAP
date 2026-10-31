from datetime import datetime

from django.db import transaction

from conectagov_pen.api_pen_services import get_ciencia_recusa, get_recibo_tramite, get_tramite
from djtools.db import models


class TipoDocumentoPEN(models.ModelPlus):
    """
    Classe que representa todos os tipos de documento do PEN. Ex: Memorando, Ofício, Portaria, RG, CPF, Certidão de Nascimento.
    """

    id_tipo_doc_pen = models.PositiveIntegerField('ID Tipo Documento PEN', unique=True, null=False)
    nome = models.CharFieldPlus('Descrição', null=False, blank=False, max_length=200)
    observacao = models.CharFieldPlus('Observação', max_length=300)

    class Meta:
        ordering = ('nome',)
        verbose_name = 'Tipo de Documento do Tramita Gov.BR'
        verbose_name_plural = 'Tipos de Documentos do Tramita Gov.BR'

    def __str__(self):
        return self.nome


class MapeamentoTiposDocumento(models.ModelPlus):
    tipo_doc_barramento_pen = models.ForeignKeyPlus(
        'conectagov_pen.TipoDocumentoPEN', verbose_name='Tipo de Documento Barramento - PEN', related_name='tipos_doc_pen'
    )
    tipo_doc_suap = models.OneToOneFieldPlus(
        'documento_eletronico.TipoDocumento', verbose_name='Tipo de Documento SUAP - Processo Eletrônico', related_name='tipos_doc_suap'
    )
    tipo_para_recebimento_suap = models.BooleanField(default=False, verbose_name='Tipo para recebimento no SUAP?')

    class Meta:
        ordering = ('tipo_doc_barramento_pen__nome',)
        verbose_name = 'Mapeamento de Tipo de Documento para o Barramento - PEN'
        verbose_name_plural = 'Mapeamentos de Tipos de Documentos para o Barramento - PEN'

    def __str__(self):
        return 'SUAP: ' + self.tipo_doc_suap.nome + ' - Barramento: ' + self.tipo_doc_barramento_pen.nome


class TramiteBarramento(models.ModelPlus):
    """
    Classe que representa  os tramites externos (enviados e recebidos) do SUAP através do barramento (ConectaGOV)
    """

    STATUS_PENDENTE_ENVIO = 1
    STATUS_PENDENTE_RECEBIMENTO = 2
    STATUS_ENVIADO = 3
    STATUS_RECEBIDO = 4
    STATUS_RECUSADO = 5
    STATUS_CANCELADO = 6
    STATUS_CHOICES = [
        [STATUS_PENDENTE_ENVIO, 'Pendente de Envio'],
        [STATUS_PENDENTE_RECEBIMENTO, 'Pendente de Recebimento'],
        [STATUS_ENVIADO, 'Enviado'],
        [STATUS_RECEBIDO, 'Recebido'],
        [STATUS_RECUSADO, 'Recusado'],
        [STATUS_CANCELADO, 'Cancelado'],
    ]

    processo_barramento = models.ForeignKeyPlus(
        'conectagov_pen.ProcessoBarramento', verbose_name='Processo Barramento', related_name='processos_suap_barramento'
    )
    data_hora_encaminhamento = models.DateTimeField('Data de Encaminhamento', auto_now_add=True)

    documentos = models.JSONField(null=True)
    qtd_documentos = models.PositiveIntegerField('Quantidade Documentos', null=True)
    metadados_processo = models.JSONField(null=True)
    status = models.PositiveIntegerField('Status', choices=STATUS_CHOICES)

    retorno_situacao = models.CharFieldPlus('Retorno da situação', null=True, max_length=500)

    id_tramite_barramento = models.PositiveIntegerFieldPlus('Id Tramite Barramento', null=True)

    destinatario_externo_repositorio_id = models.PositiveIntegerFieldPlus('Id Repositório Destinatário', null=True)
    destinatario_externo_repositorio_descricao = models.CharFieldPlus('Descrição Repositório Destinatário', null=True, max_length=500)
    destinatario_externo_estrutura_id = models.CharFieldPlus('Id Estrutura Destinatário', null=True)
    destinatario_externo_estrutura_descricao = models.CharFieldPlus('Descrição Estrutura Destinatário', null=True, max_length=500)

    remetente_externo_repositorio_id = models.PositiveIntegerFieldPlus('Id Repositório Remetente', null=True)
    remetente_externo_repositorio_descricao = models.CharFieldPlus('Descrição Repositório Remetente', null=True, max_length=500)
    remetente_externo_estrutura_id = models.CharFieldPlus('Id Estrutura Remetente', null=True)
    remetente_externo_estrutura_descricao = models.CharFieldPlus('Descrição Estrutura Remetente', null=True, max_length=500)

    # Recibos
    tramite_externo_recibo_envio_json = models.JSONField(null=True)
    tramite_externo_recibo_conclusao_json = models.JSONField(null=True)

    componentes_digitais_a_receber = models.JSONField(null=True)

    class Meta:
        ordering = ('data_hora_encaminhamento',)
        verbose_name = 'Trâmite Externo de Processo Eletrônico'
        verbose_name_plural = 'Trâmites Externos de Processos Eletrônicos'
        permissions = (('pode_tramitar_pelo_barramento', 'Pode Tramitar Processos Eletrônicos pelo Barramento'),)

    def __str__(self):
        if self.processo_barramento.processo:
            return f'º Processo: {self.processo_barramento.processo.numero_protocolo_fisico} - Nº Registro do Trâmite no Barramento: {self.processo_barramento.nre_barramento_pen}'
        else:
            return f' Tramite barramento id: {self.pk}'

    def get_absolute_url(self):
        return f'/admin/conectagov_pen/tramitebarramento/{self.id}/'

    @property
    def foi_recebido_no_destino(self):
        recibo_tramite = get_recibo_tramite(self.id_tramite_barramento)
        if self.status == self.STATUS_RECEBIDO:
            return True
        elif recibo_tramite and 'status_code' in recibo_tramite:
            if recibo_tramite['status_code'] == 200:
                if self.status != self.STATUS_RECEBIDO:
                    self.registrar_recebimento(recibo_tramite['data'])
                return True
        return False

    @property
    def foi_cancelado_automaticamente_pelo_barramento(self):
        """
        Método que verifica se a situação atual do trâmite é 10 = Cancelado Automaticamente pelo Barramento

        :return: boolean
        """
        tramite = get_tramite(self.id_tramite_barramento)
        if 'situacaoAtual' in tramite:
            if tramite.get('situacaoAtual') == 10:
                self.status = self.STATUS_CANCELADO
                self.retorno_situacao = 'Trâmite cancelado automaticamente pelo barramento.'
                self.save()
                return True
        return False

    @property
    def estah_recusado(self):
        if self.status == self.STATUS_RECUSADO:
            return True

    @transaction.atomic()
    def registrar_recebimento(self, recibo_tramite):
        if 'recibo' in recibo_tramite:
            data_recebimento_str = recibo_tramite['recibo']['dataDeRecebimento']
            data_recebimento = datetime.fromisoformat(data_recebimento_str)

        else:
            data_recebimento = datetime.now()
        self.tramite_externo_recibo_conclusao_json = recibo_tramite
        self.status = TramiteBarramento.STATUS_RECEBIDO
        self.save()
        self.tramite_suap_barramento.data_hora_recebimento = data_recebimento
        self.tramite_suap_barramento.save()

    @transaction.atomic()
    def registrar_ciencia_recusa(self):
        try:
            justificativa_recusa = get_tramite(self.id_tramite_barramento)['justificativaDaRecusa']
            get_ciencia_recusa(self.id_tramite_barramento)
            self.retorno_situacao = justificativa_recusa
            self.status = TramiteBarramento.STATUS_RECUSADO
            self.save()
            self.tramite_suap_barramento.processo.colocar_em_tramite()
            self.tramite_suap_barramento.processo.setor_atual = self.tramite_suap_barramento.destinatario_setor
            self.tramite_suap_barramento.processo.save()
            self.tramite_suap_barramento.save()
        except Exception as e:
            raise Exception(f'Erro ao registrar ciência de recusa: {e}')


class ProcessoBarramento(models.ModelPlus):
    processo = models.OneToOneFieldPlus('processo_eletronico.Processo', verbose_name='Processo', related_name='processos_suap_barramento', null=True)
    nre_barramento_pen = models.CharFieldPlus('Número de Registro do Processo no Barramento PEN', null=True)
    criado_no_suap = models.BooleanField('Criado no SUAP', null=False, default=True)

    def get_hashs_documentos_processo(self):
        hashs_documentos = []
        for documento_barramento in DocumentoProcessoBarramento.objects.filter(processo_barramento=self):
            hashs_documentos.append(documento_barramento.hash_para_barramento)
        return hashs_documentos

    def __str__(self):
        return self.nre_barramento_pen or '-'


class DocumentoProcessoBarramento(models.ModelPlus):
    conteudo_arquivo = models.BinaryField(null=True, blank=True, editable=False)
    processo_barramento = models.ForeignKeyPlus(
        'conectagov_pen.ProcessoBarramento', verbose_name='Processo Barramento', related_name='processos_barramento_documentos'
    )
    ordem = models.PositiveIntegerField('Ordem Documento', null=False)
    hash_para_barramento = models.CharFieldPlus('Hash do Documento para Barramento', null=False)
    enviado = models.BooleanField('Enviado', null=False, default=False)
    recebido = models.BooleanField('Recebido', null=False, default=False)

    def __str__(self):
        return 'HASH: ' + self.hash_para_barramento


class HipoteseLegalPEN(models.ModelPlus):
    """
    Classe que representa as Hipoteses Legais cadastradas no PEN - Processo Eletrônico Nacional
    """

    id_hipotese_legal_pen = models.PositiveIntegerField('ID Hipotese Legal - PEN', unique=True, null=False)
    nome = models.CharFieldPlus('Nome', null=True, blank=True, max_length=200)
    descricao = models.TextField('Descrição', null=True, blank=False)
    base_legal = models.CharFieldPlus('Base Legal', null=True, blank=False)
    status = models.BooleanField('Status', default=True)
    hipotese_legal_suap = models.OneToOneFieldPlus('documento_eletronico.HipoteseLegal', null=True, blank=True, verbose_name='Hipótese Legal - SUAP')
    hipotese_padrao = models.BooleanField('Hipotese Padrão', default=False)

    class Meta:
        ordering = ('descricao',)
        verbose_name = 'Hipótese Legal - PEN'
        verbose_name_plural = 'Hipóteses Legais - PEN'

    def __str__(self):
        return f'{self.nome} ({self.base_legal})'

    @classmethod
    def get_hipotese_padrao(cls):
        return cls.objects.filter(hipotese_padrao=True).first()
