from django.contrib.postgres.fields import ArrayField

from dados_abertos.enums import ODS, CoberturaEspacial, EstadoCKAN, GranularidadeEspacial, ObservanciaLegal, SituacaoLAI
from djtools.db import models
from djtools.db.models import ModelPlus
from django.urls import reverse
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _


def reabrir_lai_por_edicao(base) -> None:
    """Reverte para EM_ANALISE as relações LIBERADO da base (invalidação por edição de conteúdo).

    Delega ao ``lai_service`` para que a reabertura entre na linha do tempo como evento. Import
    adiado: o serviço importa os models deste pacote.
    """
    from dados_abertos.services.lai_service import reabrir_por_edicao

    reabrir_por_edicao(base)


class BaseDados(ModelPlus):
    SEARCH_FIELDS = ['notas', 'titulo']

    nome = models.SlugField(
        max_length=120,
        unique=True,
        verbose_name=_('Identificador'),
        help_text=_('Slug único da base de dados no CKAN (minúsculas, sem espaços).'),
    )
    titulo = models.CharFieldPlus(max_length=200, verbose_name=_('Título'), help_text=_('Título da base de dados.'), null=True, blank=False)
    notas = models.TextField(blank=True, verbose_name=_('Notas'), help_text=_('Descrição ou observações sobre a base de dados.'))

    organizacao = models.ForeignKeyPlus(
        'dados_abertos.Organizacao',
        related_name='datasets',
        on_delete=models.SET_NULL,
        null=True,
        blank=False,
        verbose_name=_('Organização'),
        help_text=_('Organização proprietária do conjunto de dados.'),
    )

    licenca = models.ForeignKeyPlus(
        'dados_abertos.Licenca',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Licença'),
        help_text=_('Licença sob a qual os dados são publicados.'),
    )

    tags = models.TagsFieldPlus(
        null=True, blank=True, verbose_name=_('Tags'), help_text=_('Lista de palavras-chave associadas ao conjunto de dados.')
    )

    tema = models.ForeignKeyPlus(
        'dados_abertos.Tema',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Tema'),
        help_text=_('Tema ou categoria do conjunto de dados.'),
    )

    # Metadados do DCAT-BR. Os quatro de contato e a versão são campos nativos do package no CKAN;
    # os demais sobem como ``extras``, montados por ``services.metadados.extras_dcat``.
    autor = models.CharFieldPlus(
        _('Área técnica responsável'), max_length=200, blank=True, help_text=_('Unidade do IFRN que produz os dados (DCAT-BR: creator).')
    )
    autor_email = models.EmailField(_('E-mail da área técnica'), blank=True, help_text=_('Contato da área técnica (DCAT-BR: contactPoint).'))
    mantenedor = models.CharFieldPlus(
        _('Mantenedor'), max_length=200, blank=True, help_text=_('Unidade que mantém a publicação no portal (DCAT-BR: publisher).')
    )
    mantenedor_email = models.EmailField(_('E-mail do mantenedor'), blank=True)
    versao = models.CharFieldPlus(_('Versão'), max_length=20, default='1.0', blank=True, help_text=_('Versão do conjunto de dados.'))

    cobertura_espacial = models.CharFieldPlus(_('Cobertura espacial'), max_length=20, choices=CoberturaEspacial.get_choices(), blank=True)
    valor_cobertura_espacial = models.CharFieldPlus(
        _('Local coberto'), max_length=100, blank=True, help_text=_('Ex.: RN, para cobertura estadual; Natal, para municipal.')
    )
    granularidade_espacial = models.CharFieldPlus(_('Granularidade espacial'), max_length=20, choices=GranularidadeEspacial.get_choices(), blank=True)
    cobertura_temporal_inicio = models.DateFieldPlus(_('Cobertura temporal: início'), null=True, blank=True)
    cobertura_temporal_fim = models.DateFieldPlus(
        _('Cobertura temporal: fim'), null=True, blank=True, help_text=_('Deixe vazio quando o conjunto continua sendo alimentado.')
    )
    observancia_legal = models.CharFieldPlus(
        _('Observância legal'), max_length=20, choices=ObservanciaLegal.get_choices(), default=ObservanciaLegal.PUBLICO, blank=True
    )
    ods = ArrayField(
        models.PositiveSmallIntegerField(choices=ODS.get_choices()),
        default=list,
        blank=True,
        verbose_name=_('ODS relacionados'),
        help_text=_('Objetivos de Desenvolvimento Sustentável aos quais o conjunto se relaciona.'),
    )
    dados_genero = models.BooleanField(_('Contém dados de gênero'), default=False)
    dados_raca_etnia = models.BooleanField(_('Contém dados de raça/etnia'), default=False)

    extras = models.FileInformationField(null=True, blank=True, verbose_name=_('Metadados adicionais'), help_text=_('Campos extras em formato JSON.'))

    estado = models.CharFieldPlus(
        max_length=16,
        choices=EstadoCKAN.get_choices(),
        default=EstadoCKAN.ACTIVE,
        verbose_name=_('Estado'),
        help_text=_('Estado atual da base de dados (reflete o CKAN remoto).'),
    )

    id_remoto = models.CharFieldPlus(
        max_length=80, blank=True, verbose_name=_('ID remoto'), help_text=_('Identificador único da base de dados no CKAN remoto.')
    )
    sincronizado_em = models.DateTimeFieldPlus(
        null=True, blank=True, verbose_name=_('Última sincronização'), help_text=_('Data e hora da última sincronização com o CKAN.')
    )

    data_cadastro = models.DateTimeFieldPlus(_('Data de Cadastro'), auto_now_add=True, null=True, blank=True)
    data_atualizacao = models.DateTimeFieldPlus(_('Data de Atualização'), auto_now=True, null=True, blank=True)

    class Meta:
        verbose_name = _('Base de Dados')
        verbose_name_plural = _('Bases de Dados')
        ordering = ['titulo', 'nome']

    def __str__(self):
        return self.titulo or self.nome

    def get_absolute_url(self) -> str:
        return reverse('dados_abertos:base_dados_detalhe', args=[self.pk])

    def clean(self):
        if not self.nome:
            self.nome = slugify(self.titulo)

    _CAMPOS_CONTEUDO_LAI = ('titulo', 'notas', 'tags', 'tema_id', 'licenca_id', 'organizacao_id')

    def save(self, *args, **kwargs):
        conteudo_mudou = False
        if self.pk:
            anterior = BaseDados.objects.filter(pk=self.pk).only(*self._CAMPOS_CONTEUDO_LAI).first()
            if anterior:
                conteudo_mudou = any(getattr(anterior, c) != getattr(self, c) for c in self._CAMPOS_CONTEUDO_LAI)
        super().save(*args, **kwargs)
        if conteudo_mudou:
            reabrir_lai_por_edicao(self)

    def lai_liberada_para_sync(self) -> bool:
        """True se a base pode ir ao CKAN: tem ≥1 relação PDABaseDados e TODAS estão LIBERADO."""
        relacoes = list(self.relacoes_pda.values_list('situacao_lai', flat=True))
        return bool(relacoes) and all(s == SituacaoLAI.LIBERADO for s in relacoes)

    def motivo_bloqueio_lai(self) -> str:
        """Mensagem explicando por que o sync está bloqueado pela deliberação LAI (vazio se liberado)."""
        relacoes = list(self.relacoes_pda.values_list('situacao_lai', flat=True))
        if not relacoes:
            return 'Base não vinculada a nenhum PDA — não passou pela análise do Responsável LAI.'
        if all(s == SituacaoLAI.LIBERADO for s in relacoes):
            return ''
        return 'A base possui datasets pendentes, em análise ou devolvidos pelo Responsável LAI. Só é possível sincronizar após a liberação em todos os PDAs.'
