import datetime
import logging

from django.conf import settings
from comum.models import Ano
from djtools.choices import Meses
from djtools.db import models
from djtools.utils import requests, mask_cpf
from edu.models import Aluno, Aula, Falta, FrequenciaPraticaProfissional, LogModel, MatriculaPeriodo, Professor

logger = logging.getLogger(__name__)


class RequisicaoPeDeMeia(LogModel):
    CADASTRO = 'Cadastro'
    ATUALIZACAO = 'Atualizacao'
    MOVIMENTACAO = 'Movimentacao'
    CONCLUSAO = 'Conclusao'
    FREQUENCIA = 'Frequencia'
    ATUALIZACAO_FREQUENCIA = 'Atualizar Frequencia'
    TIPO_CHOICES = [
        (CADASTRO, 'Cadastro'),
        (FREQUENCIA, 'Frequência'),
        (ATUALIZACAO_FREQUENCIA, 'Atualização de Frequência'),
        (ATUALIZACAO, 'Atualização de Cadastro'),
        (MOVIMENTACAO, 'Movimentação'),
        (CONCLUSAO, 'Conclusão'),
    ]
    aluno = models.ForeignKeyPlus('edu.Aluno', on_delete=models.CASCADE)
    tipo = models.CharField(verbose_name='Tipo', max_length=20, choices=TIPO_CHOICES)
    data = models.DateTimeFieldPlus('Data da requisição')
    registro_serializado = models.JSONField()
    json_retorno = models.JSONField(blank=True, null=True)
    processada = models.BooleanField(default=False, verbose_name='Processada')
    ano = models.ForeignKeyPlus(Ano, verbose_name='Ano', on_delete=models.CASCADE)
    mes = models.SmallIntegerField('Mês', choices=Meses.get_choices())

    extra = models.JSONField('Dados Extras', null=True)
    aulas = models.ManyToManyField(Aula)
    faltas = models.ManyToManyField(Falta)
    praticas_profissionais = models.ManyToManyField(FrequenciaPraticaProfissional)

    class Meta:
        verbose_name = 'Requisição para API do Pé de Meia'
        verbose_name_plural = 'Requisições para API do Pé de Meia'

    def __str__(self):
        return f'Requisição para {self.aluno} em {self.data}'


class LoteRequisicaoPeDeMeia(LogModel):
    requisicoes = models.ManyToManyFieldPlus('RequisicaoPeDeMeia', verbose_name='Requisições')
    data = models.DateTimeFieldPlus('Data do Lote')
    json_retorno = models.JSONField(blank=True, null=True)
    id_lote = models.CharFieldPlus('ID do Lote', null=True, blank=True)
    processada = models.BooleanField(default=False, verbose_name='Processada')
    ano = models.ForeignKeyPlus(Ano, verbose_name='Ano', on_delete=models.CASCADE)
    mes = models.SmallIntegerField('Mês', choices=Meses.get_choices())

    class Meta:
        verbose_name = 'Lote para API do Pé de Meia'
        verbose_name_plural = 'Lote de Requisições para API do Pé de Meia'

    def __str__(self):
        return f'Lote de Requisições Pé de Meia em {self.data}'


class ElegibilidadePeDeMeia(models.Model):
    aluno = models.ForeignKeyPlus('edu.Aluno', on_delete=models.CASCADE)
    elegivel = models.BooleanField(verbose_name='Elegível', null=True, blank=True)
    situacao = models.TextField(verbose_name='Situação')
    data_avaliacao_inelegibilidade = models.DateField(verbose_name='Data da Avaliação da Inelegibilidade', null=True)

    class Meta:
        verbose_name = 'Elegibilidade Pé de Meia'
        verbose_name_plural = 'Elegibilidades Pé de Meia'


class TransmissaoPeDeMeia(models.Model):
    descricao = models.CharField(verbose_name='Descrição')
    modalidades = models.ManyToManyFieldPlus('edu.Modalidade', verbose_name='Modalidades')
    ano_letivo = models.ForeignKeyPlus(Ano, verbose_name='Ano Letivo', null=True)
    periodo_letivo = models.IntegerField(verbose_name='Período Letivo', null=True)

    data_inicio_janela_transmissao = models.DateFieldPlus(verbose_name='Data de Início da Janela de Transmissão')
    data_termino_janela_transmissao = models.DateFieldPlus(verbose_name='Data de Término da Janela de Transmissão')

    data_inicio_execucao_cadastro = models.DateTimeFieldPlus(verbose_name='Data de Início da Execução dos Cadastros dos Alunos', null=True)
    requisicoes_cadastro = models.ManyToManyFieldPlus(RequisicaoPeDeMeia, verbose_name='Requisições de Cadastro', related_name='rpm_1')
    data_termino_execucao_cadastro = models.DateTimeFieldPlus(verbose_name='Data de Término da Execução dos Cadastros dos Alunos', null=True)

    data_inicio_execucao_atualizacao_cadastro = models.DateTimeFieldPlus(
        verbose_name='Data de Início da Execução da Atualização dos Alunos', null=True
    )
    requisicoes_atualizacao = models.ManyToManyFieldPlus(RequisicaoPeDeMeia, verbose_name='Requisições de Atualização', related_name='rpm_2')
    data_termino_execucao_atualizacao_cadastro = models.DateTimeFieldPlus(
        verbose_name='Data de Término da Execução da Atualização dos Alunos', null=True
    )

    data_inicio_execucao_movimentacao = models.DateTimeFieldPlus(verbose_name='Data de Início da Execução da Movimentação dos Alunos', null=True)
    requisicoes_movimentacao = models.ManyToManyFieldPlus(RequisicaoPeDeMeia, verbose_name='Requisições de Movimentação', related_name='rpm_3')
    data_termino_execucao_movimentacao = models.DateTimeFieldPlus(verbose_name='Data de Término da Execução da Movimentação dos Alunos', null=True)

    class Meta:
        verbose_name = 'Transmissão Pé de Meia'
        verbose_name_plural = 'Transmissões Pé de Meia'

    def __str__(self):
        return self.descricao

    def get_absolute_url(self):
        return f'/edu/transmissao_pedemeia/{self.pk}/'


class TransmissaoFrequenciaPeDeMeia(models.Model):
    FREQUENCIA = 'Frequencia'
    ATUALIZACAO_FREQUENCIA = 'Atualizar Frequencia'
    TIPO_CHOICES = [
        (FREQUENCIA, 'Frequência'),
        (ATUALIZACAO_FREQUENCIA, 'Atualização de Frequência'),
    ]

    transmissao = models.ForeignKeyPlus(TransmissaoPeDeMeia, on_delete=models.CASCADE)
    tipo = models.CharField(verbose_name='Tipo', choices=TIPO_CHOICES)
    ano = models.ForeignKeyPlus(Ano, verbose_name='Ano', on_delete=models.CASCADE)
    mes = models.SmallIntegerField('Mês', choices=Meses.get_choices())

    data_inicio_execucao = models.DateTimeFieldPlus(verbose_name='Data de Início da Execução', null=True)
    requisicoes = models.ManyToManyField(RequisicaoPeDeMeia, verbose_name='Requisições')
    data_termino_execucao = models.DateTimeFieldPlus(verbose_name='Data de Término da Execução', null=True)

    class Meta:
        verbose_name = 'Transmissão de Frequência Pé de Meia'
        verbose_name_plural = 'Transmissões de Frequência Pé de Meia'

    def __str__(self):
        return f'{self.get_tipo_display()} - {self.get_mes_display()}/{self.ano}'


class RelatoInconsistenciaPeDeMeia(models.Model):
    aluno = models.ForeignKeyPlus(Aluno, verbose_name='Aluno', on_delete=models.CASCADE)
    data = models.DateField(verbose_name='Data', auto_created=True)
    descricao = models.TextField(verbose_name='Descrição')
    resolvido = models.BooleanField(verbose_name='Resolvido', null=True)

    class Meta:
        verbose_name = 'Relato de Inconsistência'
        verbose_name_plural = 'Relatos de Inconsistência'


class FrequenciaPeDeMeia(models.Model):
    matricula_periodo = models.ForeignKey(MatriculaPeriodo, verbose_name='Matrícula Período', on_delete=models.CASCADE)
    ano = models.ForeignKeyPlus(Ano, verbose_name='Ano', on_delete=models.CASCADE)
    mes = models.SmallIntegerField('Mês', choices=Meses.get_choices())
    qtd_horas_ofertadas = models.IntegerField('CH Ofertada')
    qtd_horas_presentes = models.IntegerField('CH Presentes')

    qtd_horas_ofertadas_sgp = models.IntegerField('CH Ofertada SGP', null=True)
    qtd_horas_presentes_sgp = models.IntegerField('CH Presentes SGP', null=True)

    data_ultima_atualizacao = models.DateTimeFieldPlus(verbose_name='Data da Última Atualização', null=True, blank=True)
    data_ultima_transmissao = models.DateTimeFieldPlus(verbose_name='Data do Última Transmissão', null=True, blank=True)

    aulas = models.ManyToManyField(Aula, verbose_name='Aulas')
    faltas = models.ManyToManyField(Falta, verbose_name='Faltas')
    praticas_profissionais = models.ManyToManyField(FrequenciaPraticaProfissional, verbose_name='Frequências de Prática Profissinal')

    class Meta:
        verbose_name = 'Frequência Pé-de-Meia'
        verbose_name_plural = 'Frequências Pé-de-Meia'

    def get_percentual_presenca(self):
        if self.qtd_horas_ofertadas:
            return int(self.qtd_horas_presentes / self.qtd_horas_ofertadas * 100.0)
        return 0

    def get_detalhamento_frequencias(self):
        dados = {
            aula: {'tipo': 'Aula', 'data': data, 'diario': diario, 'esperada': quantidade, 'presente': quantidade, 'ausente': 0}
            for aula, diario, data, quantidade in self.aulas.values_list('id', 'professor_diario__diario', 'data', 'quantidade').order_by('data')
        }
        for aula, quantidade in self.faltas.values_list('aula', 'quantidade'):
            dados[aula].update(ausente=quantidade, presente=dados[aula]['esperada'] - quantidade)
        for id, diario, mes, ano, esperada, presente in self.praticas_profissionais.values_list(
            'id', 'matricula_diario__diario', 'mes', 'matricula_diario__diario__ano_letivo__ano', 'ch_esperada', 'ch_frequentada'
        ):
            dados[f'#{id}'] = {
                'tipo': 'Prática Profissional',
                'data': f'{mes}/{ano}',
                'diario': diario,
                'esperada': esperada,
                'presente': presente,
                'ausente': esperada - presente,
            }
        totais = {'esperada': 0, 'presente': 0, 'ausente': 0}
        for chave in totais:
            for dado in dados.values():
                totais[chave] += dado[chave]
        return {'dados': dados, 'totais': totais}


class OperacaoPeDeMeiaManager(models.Manager):
    def gerar_lotes(self, operacao, dados):
        for inicio, fim in [[0, 5000], [5000, 10000], [10000, 15000], [15000, 20000]]:
            if len(dados[inicio:fim]):
                Lote.objects.create(operacao=operacao, dados=dados[inicio:fim], uuid='PENDENTE')

    def cadastrar_alunos(self, ano, mes, dados, observacao=None):
        operacao = self.create(tipo=OperacaoPeDeMeia.CADASTRO, ano=ano, mes=mes, data=datetime.datetime.now(), observacao=observacao)
        self.gerar_lotes(operacao, dados)
        return operacao

    def atualizar_alunos(self, ano, mes, dados, observacao=None):
        operacao = self.create(tipo=OperacaoPeDeMeia.ATUALIZACAO_CADASTRADO, ano=ano, mes=mes, data=datetime.datetime.now(), observacao=observacao)
        self.gerar_lotes(operacao, dados)
        return operacao

    def atualizar_matriculas(self, ano, mes, dados, observacao=None):
        operacao = self.create(tipo=OperacaoPeDeMeia.ATUALIZACAO_MATRICULA, ano=ano, mes=mes, data=datetime.datetime.now(), observacao=observacao)
        Lote.objects.create(operacao=operacao, dados=dados, uuid='PENDENTE')
        return operacao

    def movimentar_alunos(self, ano, mes, dados, observacao=None):
        operacao = self.create(tipo=OperacaoPeDeMeia.MOVIMENTACAO, ano=ano, mes=mes, data=datetime.datetime.now(), observacao=observacao)
        Lote.objects.create(operacao=operacao, dados=dados, uuid='PENDENTE')
        return operacao

    def cadastrar_frequencias(self, ano, mes, dados, observacao=None):
        operacao = self.create(tipo=OperacaoPeDeMeia.FREQUENCIA, ano=ano, mes=mes, data=datetime.datetime.now(), observacao=observacao)
        self.gerar_lotes(operacao, dados)
        return operacao

    def atualizar_frequencias(self, ano, mes, dados, observacao=None):
        operacao = self.create(tipo=OperacaoPeDeMeia.ATUALIZACAO_FREQUENCIA, ano=ano, mes=mes, data=datetime.datetime.now(), observacao=observacao)
        self.gerar_lotes(operacao, dados)
        return operacao

    def frequencias_pendentes(self, ano, mes, dados, observacao=None):
        operacao = self.create(tipo=OperacaoPeDeMeia.FREQUENCIA_PENDENTE, ano=ano, mes=mes, data=datetime.datetime.now(), observacao=observacao)
        self.gerar_lotes(operacao, dados)
        return operacao

    def concluir_alunos(self, ano, mes, dados, observacao=None):
        operacao = self.create(tipo=OperacaoPeDeMeia.CONCLUSAO, ano=ano, mes=mes, data=datetime.datetime.now(), observacao=observacao)
        self.gerar_lotes(operacao, dados)
        return operacao

    def cadastro_profissional(self, ano, mes, dados, observacao=None):
        operacao = self.create(tipo=OperacaoPeDeMeia.CADASTRO_PROFISSIONAL, ano=ano, mes=mes, data=datetime.datetime.now(), observacao=observacao)
        self.gerar_lotes(operacao, dados)
        return operacao

    def atualizacao_profissional(self, ano, mes, dados, observacao=None):
        operacao = self.create(tipo=OperacaoPeDeMeia.ATUALIZACAO_PROFISSIONAL, ano=ano, mes=mes, data=datetime.datetime.now(), observacao=observacao)
        self.gerar_lotes(operacao, dados)
        return operacao


class OperacaoPeDeMeia(models.Model):
    CADASTRO = 'Cadastro'
    ATUALIZACAO_CADASTRADO = 'Atualização do Cadastro'
    MOVIMENTACAO = 'Movimentação'
    CONCLUSAO = 'Conclusão'
    FREQUENCIA = 'Frequência'
    ATUALIZACAO_FREQUENCIA = 'Atualização da Frequência'
    FREQUENCIA_PENDENTE = 'Frequência Pendente'
    ATUALIZACAO_MATRICULA = 'Atualização de Matrícula'
    CADASTRO_PROFISSIONAL = 'Cadastro de Profissional'
    ATUALIZACAO_PROFISSIONAL = 'Atualização de Profissional'
    TIPO_CHOICES = [
        (CADASTRO, CADASTRO),
        (FREQUENCIA, FREQUENCIA),
        (ATUALIZACAO_FREQUENCIA, ATUALIZACAO_FREQUENCIA),
        (FREQUENCIA_PENDENTE, FREQUENCIA_PENDENTE),
        (ATUALIZACAO_CADASTRADO, ATUALIZACAO_CADASTRADO),
        (MOVIMENTACAO, MOVIMENTACAO),
        (CONCLUSAO, CONCLUSAO),
        (CADASTRO_PROFISSIONAL, CADASTRO_PROFISSIONAL),
        (ATUALIZACAO_PROFISSIONAL, ATUALIZACAO_PROFISSIONAL),
    ]
    tipo = models.CharField(verbose_name='Tipo', choices=TIPO_CHOICES)
    ano = models.ForeignKeyPlus(Ano, verbose_name='Ano', on_delete=models.CASCADE)
    mes = models.SmallIntegerField('Mês', choices=Meses.get_choices())
    data = models.DateTimeField(verbose_name='Data', auto_created=True)
    observacao = models.TextField(verbose_name='Observação', null=True, blank=True)

    objects = OperacaoPeDeMeiaManager()

    class Meta:
        verbose_name = 'Operação Pé-de-Meia'
        verbose_name_plural = 'Operações Pé-de-Meia'

    def __str__(self):
        return f'{self.tipo} {self.ano}/{self.mes}'


class Lote(models.Model):
    uuid = models.CharField(verbose_name='UUID')
    operacao = models.ForeignKeyPlus(OperacaoPeDeMeia, verbose_name='Operação', on_delete=models.CASCADE)
    dados = models.JSONField(verbose_name='Dados')
    sucesso = models.BooleanField(verbose_name='Sucesso', null=True)
    erros = models.JSONField(verbose_name='Erros', null=True, blank=True)

    class Meta:
        verbose_name = 'Lote Pé-de-Meia'
        verbose_name_plural = 'Lotes Pé-de-Meia'

    def __str__(self):
        return self.uuid

    def get_tabela(self, dados):
        colunas = []
        linhas = []
        if dados:
            tamanhos = set()
            for dado in dados:
                tamanho = len(dado)
                if tamanho not in tamanhos:
                    tamanhos.add(tamanho)
                    colunas.extend(dado.keys())
            for dado in dados:
                linha = []
                for key in colunas:
                    linha.append(dado.get(key))
                linhas.append(linha)
        return {'colunas': colunas, 'linhas': linhas}

    def get_dados(self):
        return self.get_tabela(self.dados)

    def get_erros(self):
        return self.get_tabela(self.erros)

    def ao_cadastrar_aluno(self, output):
        dados = [
            (obj['itens']['co_matricula_rede'], obj['itens']['id_sgp_estudante'], obj['itens']['id_sgp_matricula'])
            for obj in output['objetos_processados']
        ]
        for matricula, codigo_sgp_aluno, codigo_sgp in dados:
            MatriculaPeriodo.objects.filter(aluno__matricula=matricula, ano_letivo=self.operacao.ano, codigo_sgp__isnull=True).update(
                codigo_sgp=codigo_sgp, situacao_pedemeia=MatriculaPeriodo.SITUACAO_PEDEMEIA_EM_ANDAMENTO
            )
            Aluno.objects.filter(matricula=matricula, matriculaperiodo__codigo_sgp=codigo_sgp, codigo_sgp__isnull=True).update(
                codigo_sgp=codigo_sgp_aluno
            )

    def ao_atualizar_aluno(self, output):
        pass

    def ao_atualizar_matricula(self, output):
        pass

    def ao_movimentar_aluno(self, output):
        for codigo_sgp, situacao_pedemeia in {
            obj['itens']['id_sgp_matricula']: obj['itens']['estudante_matricula_situacao'] for obj in output['objetos_processados']
        }.items():
            MatriculaPeriodo.objects.filter(codigo_sgp=codigo_sgp, situacao_pedemeia=0).update(situacao_pedemeia=situacao_pedemeia)

    def ao_concluir_aluno(self, output):
        pass

    def ao_enviar_frequencias(self, output):
        agora = datetime.datetime.now()
        dados = [
            (obj['itens']['id_sgp_matricula'], obj['itens']['hl_ofertada_periodo'], obj['itens']['hl_presente_estudante_periodo'])
            for obj in output['objetos_processados']
        ]
        for codigo_sgp, hl_ofertada_periodo, hl_presente_estudante_periodo in dados:
            logger.info(codigo_sgp, hl_ofertada_periodo, hl_presente_estudante_periodo)
            FrequenciaPeDeMeia.objects.filter(matricula_periodo__codigo_sgp=codigo_sgp, ano=self.operacao.ano, mes=self.operacao.mes).update(
                qtd_horas_ofertadas_sgp=hl_ofertada_periodo, qtd_horas_presentes_sgp=hl_presente_estudante_periodo, data_ultima_transmissao=agora
            )

    def ao_cadastrar_profissional(self, output):
        dados = [(obj['itens']['id_sgp_profissional'], obj['itens']['profissional_cpf']) for obj in output['objetos_processados']]
        for codigo_sgp, cpf in dados:
            cpf = mask_cpf(cpf)
            Professor.objects.filter(vinculo__pessoa__pessoafisica__cpf=cpf, codigo_sgp__isnull=True).update(codigo_sgp=codigo_sgp)

    def get_callback(self):
        return {
            OperacaoPeDeMeia.CADASTRO: self.ao_cadastrar_aluno,
            OperacaoPeDeMeia.ATUALIZACAO_CADASTRADO: self.ao_atualizar_aluno,
            OperacaoPeDeMeia.ATUALIZACAO_MATRICULA: self.ao_atualizar_matricula,
            OperacaoPeDeMeia.MOVIMENTACAO: self.ao_movimentar_aluno,
            OperacaoPeDeMeia.CONCLUSAO: self.ao_concluir_aluno,
            OperacaoPeDeMeia.FREQUENCIA: self.ao_enviar_frequencias,
            OperacaoPeDeMeia.ATUALIZACAO_FREQUENCIA: self.ao_enviar_frequencias,
            OperacaoPeDeMeia.FREQUENCIA_PENDENTE: self.ao_enviar_frequencias,
            OperacaoPeDeMeia.CADASTRO_PROFISSIONAL: self.ao_cadastrar_profissional,
            OperacaoPeDeMeia.ATUALIZACAO_PROFISSIONAL: self.ao_cadastrar_profissional,
        }[self.operacao.tipo]

    def sincronizar(self):
        if self.uuid == 'PENDENTE':
            self.transmitir()
        else:
            self.consultar()

    def transmitir(self):
        from edu import pedemeia2

        headers = pedemeia2.get_headers()
        if self.operacao.tipo == OperacaoPeDeMeia.CADASTRO:
            url = pedemeia2.get_url('/api/v2/estudantes/sem-turma/cadastro/lote')
            dados = {'estudantes': self.dados}
            response = requests.post(url, json=dados, headers=headers, timeout=settings.REQUESTS_TIMEOUT)
        elif self.operacao.tipo == OperacaoPeDeMeia.ATUALIZACAO_CADASTRADO:
            url = pedemeia2.get_url('/api/v2/estudantes/edicao/lote')
            dados = {'estudantes': self.dados}
            response = requests.put(url, json=dados, headers=headers, timeout=settings.REQUESTS_TIMEOUT)
        elif self.operacao.tipo == OperacaoPeDeMeia.ATUALIZACAO_MATRICULA:
            url = pedemeia2.get_url('')
            response = requests.put(url, json=dados, headers=headers, timeout=settings.REQUESTS_TIMEOUT)
        elif self.operacao.tipo == OperacaoPeDeMeia.MOVIMENTACAO or self.operacao.tipo == OperacaoPeDeMeia.CONCLUSAO:
            url = pedemeia2.get_url('/api/v2/matriculas/movimentacao/lote')
            dados = {'matriculas': self.dados}
            response = requests.put(url, json=dados, headers=headers, timeout=settings.REQUESTS_TIMEOUT)
        elif self.operacao.tipo == OperacaoPeDeMeia.FREQUENCIA:
            url = pedemeia2.get_url(f'/api/v2/frequencia-mensal-matricula/{self.operacao.ano}/{self.operacao.mes}/lote')
            dados = {'frequencias': self.dados}
            response = requests.post(url, json=dados, headers=headers, timeout=settings.REQUESTS_TIMEOUT)
        elif self.operacao.tipo == OperacaoPeDeMeia.ATUALIZACAO_FREQUENCIA:
            url = pedemeia2.get_url(f'/api/v2/frequencia-mensal-matricula/{self.operacao.ano}/{self.operacao.mes}/lote')
            dados = {'frequencias': self.dados}
            response = requests.put(url, json=dados, headers=headers, timeout=settings.REQUESTS_TIMEOUT)
        elif self.operacao.tipo == OperacaoPeDeMeia.FREQUENCIA_PENDENTE:
            url = pedemeia2.get_url(f'/api/v2/frequencia-mensal-matricula/{self.operacao.ano}/{self.operacao.mes}/lote')
            dados = {'frequencias': self.dados}
            response = requests.post(url, json=dados, headers=headers, timeout=settings.REQUESTS_TIMEOUT)
        elif self.operacao.tipo == OperacaoPeDeMeia.CADASTRO_PROFISSIONAL:
            url = pedemeia2.get_url('/api/v2/profissionais/lote')
            dados = {'profissionais': self.dados}
            response = requests.post(url, json=dados, headers=headers, timeout=settings.REQUESTS_TIMEOUT)
        elif self.operacao.tipo == OperacaoPeDeMeia.ATUALIZACAO_PROFISSIONAL:
            url = pedemeia2.get_url('/api/v2/profissionais/lote')
            dados = {'profissionais': self.dados}
            response = requests.put(url, json=dados, headers=headers, timeout=settings.REQUESTS_TIMEOUT)
        output = response.json()
        logger.info(output)
        if response.ok:
            self.uuid = output['lote_id']
            self.erros = None
            self.save()
        else:
            self.erros = output['error']['details']['errors']
            self.save()

    def consultar(self):
        from edu import pedemeia2

        headers = pedemeia2.get_headers()
        url = pedemeia2.get_url(f'/api/v2/lotes/{self.uuid}')
        response = requests.get(url, headers=headers)
        output = response.json()
        logger.info(output)

        if output['status_id'] in (6, 31):
            url = pedemeia2.get_url(f'/api/v2/lotes/{self.uuid}/erros')
            response2 = requests.get(url, headers=headers)
            output2 = response2.json()
            logger.info(output2)
            self.erros = output2.get('erros')
            self.sucesso = False
            self.save()

        if output['status_id'] in (3, 31):
            url = pedemeia2.get_url(f'/api/v2/lotes/{self.uuid}?objetos_processados=true&limit_objetos=5000')
            response = requests.get(url, headers=headers)
            output = response.json()
            self.get_callback()(output)
            self.sucesso = True
            self.save()
