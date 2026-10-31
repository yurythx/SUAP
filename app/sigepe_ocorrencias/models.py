from djtools.db import models
from comum.models import Configuracao


class PacoteOcorrenciaSigepe(models.ModelPlus):
    MES_CHOICES = (
        (1, 'Janeiro'),
        (2, 'Fevereiro'),
        (3, 'Março'),
        (4, 'Abril'),
        (5, 'Maio'),
        (6, 'Junho'),
        (7, 'Julho'),
        (8, 'Agosto'),
        (9, 'Setembro'),
        (10, 'Outubro'),
        (11, 'Novembro'),
        (12, 'Dezembro'),
    )

    ano = models.PositiveIntegerField('Ano')
    mes = models.PositiveIntegerField('Mês', choices=MES_CHOICES)

    CADASTRADO = 1
    AGUARDANDO_GERAR_ARQUIVO_ENVIO = 2
    AGUARDANDO_ARQUIVO_RETORNO = 3
    AGUARDANDO_ATUALIZACAO_ARQUIVO_ENVIO = 4
    FINALIZADO = 5
    SITUACAO_CHOICES = [
        [CADASTRADO, 'Cadastrado'],
        [AGUARDANDO_GERAR_ARQUIVO_ENVIO, 'Aguardando geração do arquivo de envio'],
        [AGUARDANDO_ARQUIVO_RETORNO, 'Aguardando arquivo de retorno'],
        [AGUARDANDO_ATUALIZACAO_ARQUIVO_ENVIO, 'Aguardando atualização do arquivo de envio'],
        [FINALIZADO, 'Finalizado'],
    ]
    situacao = models.PositiveIntegerField('Situação', default=CADASTRADO, choices=SITUACAO_CHOICES)

    arquivo_envio_nome = models.CharFieldPlus(verbose_name='Nome do arquivo', null=True, blank=True)
    arquivo_envio_arquivo = models.FileFieldPlus(
        'Arquivo de envio', upload_to='upload/sigepe_ocorrencias/arquivos_envio/', max_length=400, null=True, blank=True
    )
    arquivo_retorno_arquivo = models.FileFieldPlus(
        'Arquivo de retorno', upload_to='upload/sigepe_ocorrencias/arquivos_retorno/', max_length=400, null=True, blank=True
    )

    class Meta:
        verbose_name = 'Pacote de Ocorrências Sigepe'
        verbose_name_plural = 'Pacotes de Ocorrências Sigepe'
        unique_together = ('ano', 'mes')

    def __str__(self):
        return f'Pacote de Ocorrências Sigepe {self.mes}/{self.ano}'

    def pode_gerar_novo_arquivo_envio(self):
        return self.situacao == self.CADASTRADO

    def pode_solicitar_atualizacao_arquivo_envio(self):
        pode_pela_situacao = self.situacao == self.AGUARDANDO_ARQUIVO_RETORNO
        return pode_pela_situacao and OcorrenciaSigepe.objects.filter(pacote_ocorrencia=self).exists()

    def pode_finalizar(self):
        return self.situacao in [self.AGUARDANDO_ARQUIVO_RETORNO, self.AGUARDANDO_ATUALIZACAO_ARQUIVO_ENVIO]

    def pode_zerar(self):
        return self.situacao == self.AGUARDANDO_ARQUIVO_RETORNO

    def arquivo_estah_sendo_gerado(self):
        return self.situacao in [self.AGUARDANDO_GERAR_ARQUIVO_ENVIO, self.AGUARDANDO_ATUALIZACAO_ARQUIVO_ENVIO]

    def estah_finalizado(self):
        return self.situacao == self.FINALIZADO


class OcorrenciaSigepe(models.ModelPlus):
    # https://www.gov.br/servidor/pt-br/acesso-a-informacao/gestao-de-pessoas/manual-de-procedimentos/manual-de-procedimentos-gestor-sigepe-ocorrencia-versao-9.pdf

    # Apenas quem recebe aux. transporte

    """
    - 1001-Teletrabalho integral  PGD
    Deve ser utilizada para registrar os dias de trabalho dos agentes públicos que aderiram ao
    Programa de Gestão e Desempenho na modalidade de teletrabalho integral, realizando suas
    atividades de forma remota.

    - 1002-Teletrabalho parcial  PGD
    Deve ser utilizada para registrar os dias de trabalho dos agentes públicos que aderiram ao
    Programa de Gestão e Desempenho na modalidade de teletrabalho parcial(incluindo
    teletrabalho por turno), realizando suas atividades de forma remota.

    - 1003-Teletrabalho exterior  PGD
    Deve ser utilizada para registrar os dias de trabalho dos agentes públicos que aderiram ao
    Programa de Gestão e Desempenho na modalidade de teletrabalho no exterior .

    - 1004-Efetivo deslocamento
    Deve ser utilizada por todos os agentes públicos que se deslocarem de sua residência para os
    locais de trabalho, conforme previsto na IN SRT/MGI nº 71/2025.

    - 1005- Efetivo Deslocamento  PGD
    Deve ser utilizada por todos os agentes públicos que trabalham em qualquer modalidade de
    PGD (Presencial, Teletrabalho Integral, Teletrabalho Parcial ou Exterior) e que se deslocarem
    de sua residência para os locais de trabalho, conforme previsto na IN SRT/MGI nº 71/2025.
    """

    TIPOS_OCORRENCIAS_CHOICES = (
        (1001, '1001 - Teletrabalho integral - PGD'),
        (1002, '1002 - Teletrabalho parcial - PGD'),
        (1003, '1003 - Teletrabalho exterior - PGD'),
        (1004, '1004 - Efetivo deslocamento'),
        (1005, '1005 - Efetivo Deslocamento - PGD'),
        (1006, '1006 - Dia presencial - Teletrabalho parcial - PGD'),
        (1007, '1007 - Trabalho presencial - PGD'),
    )

    pacote_ocorrencia = models.ForeignKeyPlus(PacoteOcorrenciaSigepe)

    # Tem auxilio transporte
    tem_auxilio_transporte_neste_dia = models.BooleanField(verbose_name='Auxílio transporte?', default=False)

    # Dados do arquivo
    vinculo = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Servidor', null=True)
    tipo_ocorrencia = models.IntegerFieldPlus(verbose_name='Tipo de Ocorrência', null=True, choices=TIPOS_OCORRENCIAS_CHOICES)
    diploma_legal = models.CharFieldPlus(verbose_name='Diploma Legal', null=True)
    diploma_legal_numero = models.IntegerFieldPlus(verbose_name='Número', null=True)
    diploma_legal_data_publicacao = models.DateFieldPlus(verbose_name='Data Publicação', null=True)
    tem_efeito_financeiro = models.CharFieldPlus(verbose_name='O registro da Concessão deverá gerar efeito financeiro?', null=True)
    qtd_horas = models.CharFieldPlus(verbose_name='Quantidade de Horas', null=True)
    data_inicio = models.DateFieldPlus(verbose_name='Data de Início ', null=True)
    data_fim = models.DateFieldPlus(verbose_name='Data de Fim', null=True)

    erro_envio = models.TextField(verbose_name='Detalhamento do resultado arquivo de retorno', null=True)

    class Meta:
        verbose_name = 'Ocorrência Sigepe'
        verbose_name_plural = 'Ocorrências Sigepe'

    def get_linha_formato_csv_formato_lista(self, usa_serador=True):
        linha = []

        if usa_serador:
            usa_serador = ';'
        else:
            usa_serador = ''

        instituicao_identificador = Configuracao.get_valor_por_chave('comum', 'instituicao_identificador')
        linha.append(f'{instituicao_identificador}{usa_serador}')

        if self.vinculo.relacionamento:
            linha.append(f'{self.vinculo.relacionamento.matricula}{usa_serador}')
        else:
            linha.append(f'{usa_serador}')
        if self.tipo_ocorrencia:
            linha.append(f'{self.tipo_ocorrencia}{usa_serador}')
        else:
            linha.append(f'{usa_serador}')
        if self.diploma_legal:
            linha.append(f'{self.diploma_legal}{usa_serador}')
        else:
            linha.append(f'{usa_serador}')
        if self.diploma_legal_numero:
            linha.append(f'{self.diploma_legal_numero}{usa_serador}')
        else:
            linha.append(f'{usa_serador}')
        if self.diploma_legal_data_publicacao:
            d = self.diploma_legal_data_publicacao.strftime('%d/%m/%Y')
            linha.append(f'{d}{usa_serador}')
        else:
            linha.append(f'{usa_serador}')
        if self.tem_efeito_financeiro:
            linha.append(f'{self.tem_efeito_financeiro}{usa_serador}')
        else:
            linha.append(f'{usa_serador}')
        if self.qtd_horas:
            linha.append(f'{self.qtd_horas}{usa_serador}')
        else:
            linha.append(f'{usa_serador}')
        if self.data_inicio:
            d = self.data_inicio.strftime('%d/%m/%Y')
            linha.append(f'{d}{usa_serador}')
        else:
            linha.append(f'{usa_serador}')
        if self.data_fim:
            d = self.data_fim.strftime('%d/%m/%Y')
            linha.append(f'{d}{usa_serador}')
        else:
            linha.append(f'{usa_serador}')
        return linha


class RegistroAcaoSigepeOcorrencia(models.ModelPlus):
    pacote_ocorrencia = models.ForeignKeyPlus(PacoteOcorrenciaSigepe)
    user = models.CurrentUserField(editable=False)
    data = models.DateTimeFieldPlus('Data', auto_now_add=True, editable=False)
    observacao = models.TextField(editable=False, null=True)

    def __str__(self):
        return self.observacao

    @staticmethod
    def registrar_acao(pacote_ocorrencia, observacao, user):
        ac = RegistroAcaoSigepeOcorrencia()
        ac.observacao = observacao
        ac.user = user
        ac.pacote_ocorrencia = pacote_ocorrencia
        ac.save()
