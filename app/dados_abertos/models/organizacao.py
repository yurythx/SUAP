from dados_abertos.enums import EstadoCKAN
from djtools.db import models
from djtools.db.models import ModelPlus
from django.utils.translation import gettext_lazy as _


class Organizacao(ModelPlus):
    SEARCH_FIELDS = ['titulo', 'descricao', 'nome']

    nome = models.SlugField(
        max_length=100,
        unique=True,
        verbose_name=_('Identificador'),
        help_text=_('Slug único da organização no CKAN (apenas minúsculas, sem espaços).'),
    )
    titulo = models.CharFieldPlus(max_length=200, blank=True, verbose_name=_('Título'), help_text=_('Nome de exibição da organização.'))
    descricao = models.TextField(blank=True, verbose_name=_('Descrição'), help_text=_('Descrição detalhada da organização.'))
    imagem = models.ImageFieldPlus(
        upload_to='ckan_uploads/orgs/',
        null=True,
        blank=True,
        verbose_name=_('Imagem'),
        help_text=_('Imagem da organização para upload no CKAN (opcional). Se definida, tem precedência sobre a URL.'),
    )
    url_imagem = models.URLField(
        blank=True, verbose_name=_('URL da imagem'), help_text=_('Endereço de uma imagem representativa da organização (exibida no CKAN).')
    )
    estado = models.CharFieldPlus(
        max_length=16,
        choices=EstadoCKAN.get_choices(),
        default=EstadoCKAN.ACTIVE,
        verbose_name=_('Estado'),
        help_text=_('Estado atual da organização no CKAN.'),
    )
    extras = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_('Metadados adicionais'),
        help_text=_('Campos extras em formato JSON para armazenar informações adicionais.'),
    )

    id_remoto = models.CharFieldPlus(
        max_length=80,
        blank=True,
        verbose_name=_('ID remoto'),
        help_text=_('Identificador único da organização no CKAN remoto (quando sincronizado).'),
    )
    sincronizado_em = models.DateTimeFieldPlus(
        null=True, blank=True, verbose_name=_('Última sincronização'), help_text=_('Data e hora da última sincronização com o CKAN.')
    )

    data_cadastro = models.DateTimeFieldPlus(_('Data de Cadastro'), auto_now_add=True, null=True, blank=True)
    data_atualizacao = models.DateTimeFieldPlus(_('Data de Atualização'), auto_now=True, null=True, blank=True)

    class Meta:
        verbose_name = _('Organização')
        verbose_name_plural = _('Organizações')

    def __str__(self):
        return self.titulo or self.nome
