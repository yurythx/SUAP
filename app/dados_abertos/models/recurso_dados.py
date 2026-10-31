from pathlib import Path
from urllib.parse import urlparse

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from dados_abertos.enums import FormatoRecurso
from djtools.db import models
from djtools.db.models import ModelPlus
from djtools.utils import requests


class RecursoDados(ModelPlus):
    SEARCH_FIELDS = ['nome', 'descricao']

    dataset = models.ForeignKeyPlus(
        'dados_abertos.BaseDados',
        related_name='recursos',
        on_delete=models.CASCADE,
        verbose_name=_('Base de Dados'),
        help_text=_('Base de dados à qual este recurso pertence.'),
    )

    nome = models.CharFieldPlus(max_length=200, verbose_name=_('Nome'), help_text=_('Nome do recurso (arquivo, API, etc.).'))
    descricao = models.TextField(blank=True, verbose_name=_('Descrição'), help_text=_('Descrição detalhada do recurso.'))
    formato = models.CharFieldPlus(
        max_length=10, choices=FormatoRecurso.get_choices(), verbose_name=_('Formato'), help_text=_('Formato do recurso (CSV ou JSON).')
    )

    # Uma única fonte: url (remota) OU arquivo (local)
    url = models.URLField(blank=True, verbose_name=_('URL'), help_text=_('Endereço remoto do recurso (se aplicável).'))
    arquivo = models.FileFieldPlus(
        upload_to='ckan_uploads/', blank=True, verbose_name=_('Arquivo'), help_text=_('Arquivo local enviado como recurso.')
    )

    mimetype = models.CharFieldPlus(
        max_length=100, blank=True, verbose_name=_('MIME type'), help_text=_('Tipo MIME do recurso (detectado ou informado).')
    )

    derivado_de = models.ForeignKeyPlus(
        'dados_abertos.RecursoDados',
        null=True,
        blank=True,
        related_name='derivados',
        on_delete=models.CASCADE,
        verbose_name=_('Derivado de'),
        help_text=_('Recurso de origem, quando este é um espelho gerado automaticamente em outro formato.'),
    )

    esquema = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_('Esquema'),
        help_text=_('Colunas observadas na última coleta automática. Serve para detectar mudança de estrutura do recurso.'),
    )

    id_remoto = models.CharFieldPlus(
        max_length=80, blank=True, verbose_name=_('ID remoto'), help_text=_('Identificador único do recurso no CKAN remoto.')
    )
    sincronizado_em = models.DateTimeFieldPlus(
        null=True, blank=True, verbose_name=_('Última sincronização'), help_text=_('Data e hora da última sincronização com o CKAN.')
    )

    data_cadastro = models.DateTimeFieldPlus(_('Data de Cadastro'), auto_now_add=True, null=True, blank=True)
    data_atualizacao = models.DateTimeFieldPlus(_('Data de Atualização'), auto_now=True, null=True, blank=True)

    class Meta:
        verbose_name = _('Recurso')
        verbose_name_plural = _('Recursos')
        ordering = ['nome']

    def __str__(self):
        return f'{self.nome} ({self.formato})'

    def get_absolute_url(self) -> str:
        return reverse('dados_abertos:recurso_dados_detalhe', args=[self.pk])

    # ---------- helpers para baixar e montar o arquivo ----------

    def _guess_extension_and_format(self, response, parsed_url):
        """
        Descobre a extensão e, se possível, o formato (CSV/JSON) a partir do Content-Type
        ou da própria URL.
        """
        content_type = (response.headers.get('Content-Type') or '').lower()
        ext = None
        formato_detectado = None

        if 'json' in content_type:
            ext = 'json'
            formato_detectado = FormatoRecurso.JSON
        elif 'csv' in content_type:
            ext = 'csv'
            formato_detectado = FormatoRecurso.CSV
        elif 'text/plain' in content_type and self.formato == FormatoRecurso.CSV:
            # muitos endpoints CSV vêm como text/plain
            ext = 'csv'
            formato_detectado = FormatoRecurso.CSV

        # se ainda não descobriu, tenta pela URL
        if not ext:
            url_ext = Path(parsed_url.path).suffix.lstrip('.')
            if url_ext:
                ext = url_ext.lower()

        # fallback
        if not ext:
            ext = 'txt'

        return ext, formato_detectado

    def _build_filename(self, parsed_url, ext):
        """
        Monta nome do arquivo:

        <nome_endpoint>_YYYYMMDD_HHMMSS.<ext>

        Ex: contratos_20251118_103245.json
        """
        endpoint_name = parsed_url.path.rstrip('/').split('/')[-1] or 'recurso'
        agora = timezone.now()
        timestamp = agora.strftime('%Y%m%d_%H%M%S')
        return f'{endpoint_name}_{timestamp}.{ext}'

    def nome_de_arquivo(self) -> str:
        """Nome para uma nova coleta deste recurso, no mesmo padrão do download por URL.

        Existe para que a rotina de atualização automática nomeie os arquivos como o ``save()``
        nomeia, sem duplicar a convenção nem alcançar um método privado.
        """
        extensao = 'json' if self.formato == FormatoRecurso.JSON else 'csv'
        return self._build_filename(urlparse(self.url or ''), extensao)

    def _download_and_attach_file_from_url(self):
        """
        Faz o download da URL, descobre extensão/formato, define mimetype
        e atribui ao campo `arquivo` (sem chamar save() de novo).
        """
        if not self.url:
            return

        response = requests.get(self.url, timeout=30)
        response.raise_for_status()

        parsed_url = urlparse(self.url)

        # definir mimetype
        self.mimetype = response.headers.get('Content-Type', '')

        ext, formato_detectado = self._guess_extension_and_format(response, parsed_url)

        # se detectou formato e ainda não tem formato definido, preenche
        if formato_detectado and not self.formato:
            self.formato = formato_detectado

        # se já tem formato (CSV/JSON), podemos forçar extensão compatível
        if self.formato == FormatoRecurso.JSON:
            ext = 'json'
        elif self.formato == FormatoRecurso.CSV:
            ext = 'csv'

        filename = self._build_filename(parsed_url, ext)

        content = ContentFile(response.content)
        self.arquivo.save(filename, content, save=False)

    # ---------- validação ----------

    def clean(self):
        # regra original: pelo menos uma fonte precisa existir
        if not self.url and not self.arquivo:
            raise ValidationError(_('Informe pelo menos uma fonte: URL ou arquivo.'))

        # se for manter a lógica estrita "somente uma fonte",
        #
        # if bool(self.url) == bool(self.arquivo):
        #     raise ValidationError(_('Informe exatamente uma fonte: URL OU arquivo.'))

        if self.formato not in (FormatoRecurso.CSV, FormatoRecurso.JSON):
            raise ValidationError(_('Formato de recurso inválido. Apenas CSV ou JSON.'))

    # ---------- save com integração da URL ----------

    #: Campos que representam o dado publicado. Mudança em qualquer um deles invalida a liberação
    #: do LAI; ``id_remoto``/``sincronizado_em`` ficam de fora de propósito — são o registro da
    #: publicação no CKAN, não o conteúdo, e sincronizar não é motivo para reanálise.
    _CAMPOS_CONTEUDO_LAI = ('nome', 'descricao', 'formato', 'url', 'arquivo', 'mimetype')

    def save(self, *args, **kwargs):
        """
        Ao salvar:
        - na criação, com URL e sem arquivo: baixa o conteúdo e preenche `arquivo` + `mimetype`;
        - na atualização, sempre que a URL mudar: rebaixa o conteúdo do novo endereço, substituindo
          o arquivo anterior (que veio da URL antiga);
        - com a URL inalterada: não mexe no arquivo, preservando upload manual;
        - reabre a análise do LAI apenas quando o conteúdo publicado muda (ou na criação).
        """
        criando = not self.pk
        anterior = None if criando else RecursoDados.objects.filter(pk=self.pk).only(*self._CAMPOS_CONTEUDO_LAI).first()

        baixar_da_url = False
        if self.url:
            if criando:
                # criação: só baixa quando não veio arquivo junto
                baixar_da_url = not self.arquivo
            else:
                # atualização: baixa de novo se a URL mudou
                baixar_da_url = bool(anterior and anterior.url != self.url)

        if baixar_da_url:
            self._download_and_attach_file_from_url()

        super().save(*args, **kwargs)

        if self.dataset_id and self._conteudo_mudou(criando, anterior):
            # Invalidação LAI: o dado a ser publicado mudou, a liberação anterior não vale mais.
            from dados_abertos.models.base_dados import reabrir_lai_por_edicao

            reabrir_lai_por_edicao(self.dataset)

    def _conteudo_mudou(self, criando: bool, anterior: RecursoDados | None) -> bool:
        """True quando o recurso é novo ou algum campo de conteúdo difere do que estava gravado."""
        if criando:
            return True
        if anterior is None:
            return False
        return any(getattr(anterior, campo) != getattr(self, campo) for campo in self._CAMPOS_CONTEUDO_LAI)
