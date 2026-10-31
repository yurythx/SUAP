from decimal import Decimal

from djtools.db import models
from django.db.models.functions import Now
from django.utils.translation import gettext_lazy as _

from rsc_tae.models.rol import RolSaberCompetencia  # PAPEL_CHOICES (fonte única dos papéis)


class RolSaberCompetenciaAnexo(models.ModelPlus):
    processo = models.ForeignKeyPlus('rsc_tae.ProcessoRSCTae', verbose_name=_('Processo'), on_delete=models.CASCADE)
    rol_saber_competencia = models.ForeignKeyPlus(
        'rsc_tae.RolSaberCompetencia',
        verbose_name=_('Rol de Saber e Competência'),
        on_delete=models.CASCADE,
    )
    arquivo = models.FileFieldPlus(_('Arquivo'), upload_to='rsc_tae/rol_saber_competencia/anexos', max_length=255, filetypes=['pdf'])
    pontuacao = models.DecimalField(
        _('Pontuação do arquivo'),
        max_digits=7,
        decimal_places=2,
        default=0.00,
        help_text=_('Pontuação atribuída especificamente a este arquivo para o item.'),
    )
    nome_original = models.CharField(_('Nome original'), max_length=255, blank=True)
    descricao = models.TextField(
        _('Descrição'),
        blank=True,
        help_text=_('Descrição do documento anexado, informada pelo servidor no momento do upload.'),
    )
    cadastrado_por = models.CurrentUserField(verbose_name=_('Cadastrado por'), null=True, blank=True)

    data_inicio = models.DateFieldPlus(_('Data de início'), null=True, blank=True)
    data_fim = models.DateFieldPlus(_('Data de fim'), null=True, blank=True)

    papel = models.CharField(
        _('Papel'),
        max_length=20,
        null=True,
        blank=True,
        choices=RolSaberCompetencia.PAPEL_CHOICES,
        help_text=_('Titular ou substituto — obrigatório nos itens do Requisito V (aceita_papel). Define a taxa de pontuação do período.'),
    )

    data_cadastro = models.DateTimeField(_('Data de cadastro'), auto_now_add=True, db_default=Now())

    class Meta:
        verbose_name = _('Anexo do Rol de Saber e Competência')
        verbose_name_plural = _('Anexos do Rol de Saber e Competência')
        ordering = ('-data_cadastro',)

    def __str__(self):
        return self.nome_original or (self.arquivo.name if self.arquivo else 'Anexo')

    @property
    def nome_exibicao(self) -> str:
        """Nome do arquivo prefixado pelo ID do anexo (ex.: ``#12345 - documento.pdf``).

        Usado nas telas da CRSC para que a comissão consiga referenciar o anexo de forma
        inequívoca durante a deliberação, já que nomes de arquivo se repetem entre processos.
        """
        return f'#{self.pk} - {self}'

    @property
    def periodo_componentes(self):
        """(anos, meses, dias) do período com a data de fim inclusiva (conta o último dia).

        Decomposição de calendário via ``relativedelta``. Retorna ``(0, 0, 0)`` se as datas
        não estiverem preenchidas ou forem inválidas.
        """
        if not self.data_inicio or not self.data_fim or self.data_fim < self.data_inicio:
            return (0, 0, 0)
        from datetime import timedelta

        from dateutil.relativedelta import relativedelta

        rd = relativedelta(self.data_fim + timedelta(days=1), self.data_inicio)
        return (rd.years, rd.months, rd.days)

    @property
    def duracao_meses(self):
        """Duração do período em meses decimais (meses de calendário + dias/30).

        A conversão em anos ('ano ou fração superior a 6 meses') é aplicada a CADA
        período/documento isoladamente — ver ``unidades_pontuaveis_anexos``.
        """
        anos, meses, dias = self.periodo_componentes
        return Decimal(anos * 12 + meses) + (Decimal(dias) / Decimal(30))

    @property
    def periodo_display(self):
        anos, meses, dias = self.periodo_componentes
        partes = []
        if anos:
            partes.append('1 ano' if anos == 1 else f'{anos} anos')
        if meses:
            partes.append('1 mês' if meses == 1 else f'{meses} meses')
        if dias:
            partes.append('1 dia' if dias == 1 else f'{dias} dias')
        return ', '.join(partes) if partes else 'Informe o período'

    def calcular_pontuacao_temporal(self):
        """Unidades temporais armazenadas no anexo: a duração em meses decimais.

        Cada período/documento é convertido em anos por ``meses_para_anos_pontuaveis``
        isoladamente antes de multiplicar pela pontuação por ano (ver
        ``unidades_pontuaveis_anexos``).
        """
        return self.duracao_meses


def meses_para_anos_pontuaveis(meses) -> int:
    """Converte a duração de UM período (meses decimais) em anos pela regra
    'por ano ou fração superior a 6 meses': anos completos + 1 ano se a fração
    restante passar estritamente de 6 meses.

    Exemplos: 8 meses -> 1; 2 anos e 6 meses -> 2; 2 anos e 6 meses e 1 dia -> 3; 2 anos e 7 meses -> 3.
    """
    meses = meses or Decimal('0')
    anos = int(meses // 12)
    if (meses - anos * 12) > 6:
        anos += 1
    return anos


def unidades_pontuaveis(item, unidades):
    """Unidades pontuáveis de UM anexo/período do item.

    Para item temporal, ``unidades`` é a duração em meses do período e o retorno é o
    número de anos pontuáveis ('ano ou fração superior a 6 meses'). Para os demais
    itens, é a própria quantidade de unidades declarada.
    """
    if getattr(item, 'item_temporal', False):
        return Decimal(meses_para_anos_pontuaveis(unidades))
    return unidades or Decimal('0')


def unidades_pontuaveis_anexos(item, unidades_anexos) -> Decimal:
    """Unidades pontuáveis do item a partir das unidades declaradas em cada anexo.

    Para item temporal, a regra 'por ano ou fração superior a seis meses' é aplicada a
    CADA período/documento isoladamente (um período de 6 meses e 1 dia já vale 1 ano) e
    os anos resultantes são somados — os períodos NÃO são somados em meses antes da
    conversão. Para os demais itens, retorna a soma das unidades declaradas.
    """
    valores = [(u or Decimal('0')) for u in unidades_anexos]
    if getattr(item, 'item_temporal', False):
        return Decimal(sum(meses_para_anos_pontuaveis(u) for u in valores))
    return sum(valores, Decimal('0'))


def taxa_por_papel(item, papel) -> Decimal:
    """Taxa por unidade do item conforme o papel do comprovante.

    Para itens com ``aceita_papel``: 'substituto' usa ``pontuacao_unidade_substituto``;
    qualquer outro papel (inclusive None) usa a taxa titular (``pontuacao_unidade``).
    Para itens sem papel, sempre a taxa única.
    """
    if getattr(item, 'aceita_papel', False) and papel == item.PAPEL_SUBSTITUTO:
        return item.pontuacao_unidade_substituto or Decimal('0')
    return item.pontuacao_unidade or Decimal('0')


def pontos_anexo(item, unidades, papel) -> Decimal:
    """Pontos pontuáveis de UM anexo: anos pontuáveis (ou unidades) multiplicados pela taxa do papel."""
    return unidades_pontuaveis(item, unidades) * taxa_por_papel(item, papel)


def pontos_item_anexos(item, anexos) -> Decimal:
    """Soma dos pontos de uma coleção de anexos, cada um com ``.pontuacao`` (unidades/meses) e ``.papel``."""
    total = Decimal('0')
    for anexo in anexos:
        unidades = getattr(anexo, 'pontuacao', None) or Decimal('0')
        total += pontos_anexo(item, unidades, getattr(anexo, 'papel', None))
    return total
