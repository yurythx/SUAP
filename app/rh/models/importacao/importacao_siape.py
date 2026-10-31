from datetime import timedelta

from djtools.db import models


class SituacaoImportacaoSiape(models.TextChoices):
    IDENTIFICADA = 'identificada', 'Identificada'
    AGENDADA = 'agendada', 'Agendada para a execução noturna'
    EXECUTANDO = 'executando', 'Em execução'
    CONCLUIDA = 'concluida', 'Concluída'
    CONCLUIDA_COM_FALHAS = 'concluida_com_falhas', 'Concluída com falhas'
    FALHOU = 'falhou', 'Falhou'


class SituacaoArquivoSiape(models.TextChoices):
    PENDENTE = 'pendente', 'Pendente'
    AGUARDANDO = 'aguardando', 'Aguardando dependências'
    EXECUTANDO = 'executando', 'Em execução'
    CONCLUIDO = 'concluido', 'Concluído'
    FALHOU = 'falhou', 'Falhou'
    PULADO = 'pulado', 'Pulado'
    IGNORADO = 'ignorado', 'Não será importado'


CLASSE_STATUS_ARQUIVO = {
    SituacaoArquivoSiape.CONCLUIDO: 'status-success',
    SituacaoArquivoSiape.FALHOU: 'status-error',
    SituacaoArquivoSiape.PULADO: 'status-alert',
    SituacaoArquivoSiape.EXECUTANDO: 'status-info',
    SituacaoArquivoSiape.IGNORADO: 'disabled',
}

CLASSE_STATUS_IMPORTACAO = {
    SituacaoImportacaoSiape.CONCLUIDA: 'status-success',
    SituacaoImportacaoSiape.CONCLUIDA_COM_FALHAS: 'status-alert',
    SituacaoImportacaoSiape.FALHOU: 'status-error',
    SituacaoImportacaoSiape.EXECUTANDO: 'status-info',
    SituacaoImportacaoSiape.IDENTIFICADA: 'status-default',
    SituacaoImportacaoSiape.AGENDADA: 'status-default',
}

# situações de onde a seleção pode ser gravada/regravada: recém-identificada ou já agendada
# (o usuário pode ajustar a seleção antes de reagendar ou executar). Única fonte: usada tanto
# por `ImportacaoSiapeArquivo.pode_ser_selecionado` quanto por `rh.importacao_siape.execucao`.
SITUACOES_SELECIONAVEIS = (SituacaoImportacaoSiape.IDENTIFICADA, SituacaoImportacaoSiape.AGENDADA)


class ImportacaoSiape(models.ModelPlus):
    arquivo = models.CharFieldPlus(verbose_name='Arquivo', max_length=255)
    pasta = models.CharFieldPlus(verbose_name='Pasta', max_length=255, default='')
    origem = models.CharFieldPlus(verbose_name='Origem', max_length=20, choices=[('tela', 'Tela'), ('comando', 'Comando agendado')])
    enviado_por = models.ForeignKeyPlus('comum.User', verbose_name='Enviado por', null=True, on_delete=models.SET_NULL)
    enviado_em = models.DateTimeFieldPlus(verbose_name='Enviado em', auto_now_add=True)
    situacao = models.CharFieldPlus(
        verbose_name='Situação', max_length=30, choices=SituacaoImportacaoSiape.choices, default=SituacaoImportacaoSiape.IDENTIFICADA
    )
    inicio = models.DateTimeFieldPlus(verbose_name='Início', null=True)
    fim = models.DateTimeFieldPlus(verbose_name='Fim', null=True)

    class History:
        disabled = True

    class Meta:
        verbose_name = 'Importação SIAPE'
        verbose_name_plural = 'Importações SIAPE'
        ordering = ['-id']

    def __str__(self) -> str:
        return f'Importação SIAPE #{self.pk} ({self.arquivo})'

    def get_absolute_url(self) -> str:
        return f'/rh/importacao_siape/{self.pk}/'

    @property
    def em_execucao(self) -> bool:
        return self.situacao == SituacaoImportacaoSiape.EXECUTANDO

    @property
    def agendada(self) -> bool:
        return self.situacao == SituacaoImportacaoSiape.AGENDADA

    @property
    def duracao(self) -> str:
        if not (self.inicio and self.fim):
            return ''
        return str(timedelta(seconds=int((self.fim - self.inicio).total_seconds())))

    @property
    def classe_status(self) -> str:
        return CLASSE_STATUS_IMPORTACAO.get(self.situacao, 'status-default')

    @classmethod
    def existe_em_execucao(cls) -> bool:
        return cls.objects.filter(situacao=SituacaoImportacaoSiape.EXECUTANDO).exists()


class ImportacaoSiapeArquivo(models.ModelPlus):
    importacao = models.ForeignKeyPlus(ImportacaoSiape, verbose_name='Importação', related_name='arquivos', on_delete=models.CASCADE)
    nome_ref = models.CharFieldPlus(verbose_name='Arquivo de referência', max_length=255)
    nome_txt = models.CharFieldPlus(verbose_name='Arquivo de dados', max_length=255)
    layout = models.CharFieldPlus(verbose_name='Layout', max_length=100, null=True, blank=True)
    diagnostico = models.TextField(verbose_name='Diagnóstico', blank=True, default='')
    selecionado = models.BooleanField(verbose_name='Selecionado', default=False)
    total_linhas = models.PositiveIntegerFieldPlus(verbose_name='Linhas', default=0)
    processadas = models.PositiveIntegerFieldPlus(verbose_name='Processadas', default=0)
    falhas = models.PositiveIntegerFieldPlus(verbose_name='Falhas', default=0)
    avisos = models.PositiveIntegerFieldPlus(verbose_name='Avisos', default=0)
    situacao = models.CharFieldPlus(
        verbose_name='Situação', max_length=20, choices=SituacaoArquivoSiape.choices, default=SituacaoArquivoSiape.PENDENTE
    )
    motivo = models.TextField(verbose_name='Motivo', blank=True, default='')
    inicio = models.DateTimeFieldPlus(verbose_name='Início', null=True)
    fim = models.DateTimeFieldPlus(verbose_name='Fim', null=True)

    class History:
        disabled = True

    class Meta:
        verbose_name = 'Arquivo da Importação SIAPE'
        verbose_name_plural = 'Arquivos da Importação SIAPE'
        ordering = ['id']

    def __str__(self) -> str:
        return f'{self.layout or "não reconhecido"} ({self.nome_txt.rsplit("/", 1)[-1]})'

    @property
    def percentual(self) -> int:
        if self.situacao == SituacaoArquivoSiape.CONCLUIDO:
            return 100
        return min(99, self.processadas * 100 // self.total_linhas) if self.total_linhas else 0

    @property
    def classe_status(self) -> str:
        return CLASSE_STATUS_ARQUIVO.get(self.situacao, 'status-default')

    @property
    def pode_ser_selecionado(self) -> bool:
        from rh.importacao_siape.layouts import LAYOUTS

        layout = LAYOUTS.get(self.layout or '')
        return bool(layout and layout.ativo) and self.importacao.situacao in SITUACOES_SELECIONAVEIS


class ImportacaoSiapeOcorrencia(models.ModelPlus):
    arquivo = models.ForeignKeyPlus(ImportacaoSiapeArquivo, verbose_name='Arquivo', related_name='ocorrencias', on_delete=models.CASCADE)
    nivel = models.CharFieldPlus(verbose_name='Nível', max_length=10)
    linha = models.PositiveIntegerFieldPlus(verbose_name='Linha', null=True)
    mensagem = models.TextField(verbose_name='Mensagem')
    criada_em = models.DateTimeFieldPlus(verbose_name='Registrada em', auto_now_add=True)

    class History:
        disabled = True

    class Meta:
        verbose_name = 'Ocorrência da Importação SIAPE'
        verbose_name_plural = 'Ocorrências da Importação SIAPE'
        ordering = ['id']


class ImportacaoSiapeLote(models.ModelPlus):
    arquivo = models.ForeignKeyPlus(ImportacaoSiapeArquivo, verbose_name='Arquivo', related_name='lotes', on_delete=models.CASCADE)
    numero = models.PositiveIntegerFieldPlus(verbose_name='Número')
    total_linhas = models.PositiveIntegerFieldPlus(verbose_name='Linhas', default=0)
    processadas = models.PositiveIntegerFieldPlus(verbose_name='Processadas', default=0)
    falhas = models.PositiveIntegerFieldPlus(verbose_name='Falhas', default=0)
    avisos = models.PositiveIntegerFieldPlus(verbose_name='Avisos', default=0)
    situacao = models.CharFieldPlus(
        verbose_name='Situação', max_length=20, choices=SituacaoArquivoSiape.choices, default=SituacaoArquivoSiape.AGUARDANDO
    )
    worker = models.CharFieldPlus(verbose_name='Worker', max_length=60, blank=True, default='')
    motivo = models.TextField(verbose_name='Motivo', blank=True, default='')
    inicio = models.DateTimeFieldPlus(verbose_name='Início', null=True)
    fim = models.DateTimeFieldPlus(verbose_name='Fim', null=True)

    class History:
        disabled = True

    class Meta:
        verbose_name = 'Lote da Importação SIAPE'
        verbose_name_plural = 'Lotes da Importação SIAPE'
        ordering = ['arquivo', 'numero']

    def __str__(self) -> str:
        return f'Lote {self.numero} de {self.arquivo}'

    @property
    def percentual(self) -> int:
        if self.situacao == SituacaoArquivoSiape.CONCLUIDO:
            return 100
        return min(99, self.processadas * 100 // self.total_linhas) if self.total_linhas else 0

    @property
    def classe_status(self) -> str:
        return CLASSE_STATUS_ARQUIVO.get(self.situacao, 'status-default')
