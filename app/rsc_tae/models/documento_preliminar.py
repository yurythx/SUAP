from djtools.db import models
from django.db.models.functions import Now
from django.utils.translation import gettext_lazy as _

from rsc_tae.enums import SituacaoDocumentoPreliminar, TipoDocumentoPreliminar


class DocumentoPreliminarRSCTae(models.ModelPlus):
    processo = models.ForeignKeyPlus('rsc_tae.ProcessoRSCTae', verbose_name=_('Processo'), on_delete=models.CASCADE)
    tipo = models.PositiveIntegerField(
        _('Tipo de documento'),
        choices=TipoDocumentoPreliminar.get_choices(),
        default=TipoDocumentoPreliminar.DIPLOMA_CERTIFICADO,
    )
    arquivo = models.FileFieldPlus(_('Arquivo'), upload_to='rsc_tae/documentos_preliminares', max_length=255)
    nome_original = models.CharField(_('Nome original'), max_length=255, blank=True)
    data_obtencao_titulacao = models.DateField(_('Data de obtenção da titulação'), null=True, blank=True)

    cadastrado_por_vinculo = models.ForeignKeyPlus(
        'comum.Vinculo',
        verbose_name=_('Cadastrado por (vínculo)'),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='rsc_tae_documentos_preliminares_cadastrados_set',
    )
    data_cadastro = models.DateTimeField(_('Data de cadastro'), auto_now_add=True, db_default=Now())

    class Meta:
        verbose_name = _('Documento preliminar (RSC TAE)')
        verbose_name_plural = _('Documentos preliminares (RSC TAE)')
        ordering = ('-data_cadastro',)

    def __str__(self):
        return self.nome_original or (self.arquivo.name if self.arquivo else 'Documento preliminar')

    @property
    def situacao(self):
        av = getattr(self, 'avaliacao', None)
        return getattr(av, 'situacao', None) or SituacaoDocumentoPreliminar.PENDENTE


class AvaliacaoDocumentoPreliminarRSCTae(models.ModelPlus):
    documento = models.OneToOneFieldPlus(
        'rsc_tae.DocumentoPreliminarRSCTae',
        verbose_name=_('Documento preliminar'),
        on_delete=models.CASCADE,
        related_name='avaliacao',
    )

    situacao = models.PositiveIntegerField(
        _('Situação'),
        choices=SituacaoDocumentoPreliminar.get_choices(),
        default=SituacaoDocumentoPreliminar.PENDENTE,
    )
    observacao = models.TextField(_('Observação'), blank=True)

    avaliado_por_vinculo = models.ForeignKeyPlus(
        'comum.Vinculo',
        verbose_name=_('Avaliado por (vínculo)'),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='rsc_tae_avaliacoes_documento_preliminar_set',
    )
    ip_avaliacao = models.GenericIPAddressField(_('IP da avaliação'), null=True, blank=True)
    user_agent = models.CharField(_('User-Agent'), max_length=255, blank=True)

    data_cadastro = models.DateTimeField(_('Data de cadastro'), auto_now_add=True, db_default=Now())
    data_avaliacao = models.DateTimeField(_('Data de avaliação'), auto_now=True, db_default=Now())
    data_ultima_alteracao = models.DateTimeField(_('Data de última alteração'), auto_now=True, db_default=Now())

    class Meta:
        verbose_name = _('Avaliação do documento preliminar (RSC TAE)')
        verbose_name_plural = _('Avaliações dos documentos preliminares (RSC TAE)')
        ordering = ('-data_avaliacao',)

    def __str__(self):
        return f'Documento {self.documento_id} - {self.get_situacao_display()}'


class DocumentoPreliminarRSCTaeLog(models.ModelPlus):
    ACAO_ENVIO = 1
    ACAO_VALIDACAO = 2
    ACAO_SOLICITAR_CORRECAO = 3
    ACAO_REVALIDACAO = 4

    ACAO_LABELS = (
        (ACAO_ENVIO, 'Envio'),
        (ACAO_VALIDACAO, 'Validação'),
        (ACAO_SOLICITAR_CORRECAO, 'Solicitação de correção'),
        (ACAO_REVALIDACAO, 'Revalidação necessária'),
    )

    processo = models.ForeignKeyPlus('rsc_tae.ProcessoRSCTae', verbose_name=_('Processo'), on_delete=models.CASCADE)
    documento = models.ForeignKeyPlus(
        'rsc_tae.DocumentoPreliminarRSCTae',
        verbose_name=_('Documento'),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    acao = models.PositiveIntegerField(_('Ação'), choices=ACAO_LABELS)
    executado_por_vinculo = models.ForeignKeyPlus(
        'comum.Vinculo',
        verbose_name=_('Executado por (vínculo)'),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='rsc_tae_logs_documento_preliminar_set',
    )
    ip = models.GenericIPAddressField(_('IP'), null=True, blank=True)
    user_agent = models.CharField(_('User-Agent'), max_length=255, blank=True)
    observacao = models.TextField(_('Observação'), blank=True)

    data_cadastro = models.DateTimeField(_('Data de cadastro'), auto_now_add=True, db_default=Now())

    class Meta:
        verbose_name = _('Log do documento preliminar (RSC TAE)')
        verbose_name_plural = _('Logs dos documentos preliminares (RSC TAE)')
        ordering = ('-data_cadastro',)

    def __str__(self):
        return f'Processo {self.processo_id} - {self.get_acao_display()}'
