import datetime

from djtools.db import models
from rh.models import UnidadeOrganizacional


class PeriodoDeclaracaoAcumuloCargos(models.ModelPlus):
    GERAL = 0
    TECNICO = 1
    DOCENTE = 2
    PUBLICO_CHOICES = [[GERAL, 'Geral'], [TECNICO, 'Técnicos'], [DOCENTE, 'Docentes']]

    descricao = models.CharField('Descrição', max_length=255)
    publico = models.IntegerField('Público', choices=PUBLICO_CHOICES)
    ano = models.IntegerField()
    data_inicio = models.DateField('Data de Início')
    data_fim = models.DateField('Data de Término')
    campus = models.ManyToManyFieldPlus('rh.UnidadeOrganizacional', verbose_name='Campus', blank=True)

    class Meta:
        verbose_name = 'Questionário de Acúmulo de Cargos'
        verbose_name_plural = 'Questionários de Acúmulo de Cargos'

    def __str__(self):
        return f'{self.descricao} {self.ano} - {self.get_publico_display()} - {self.get_campus()}'

    def get_campus(self):
        if self.campus.count() == UnidadeOrganizacional.objects.suap().all().count():
            return 'Todos os campus'
        return ', '.join(self.campus.values_list('sigla', flat=True))

    @staticmethod
    def periodo_aberto_para_cadastro(servidor):
        publico = [PeriodoDeclaracaoAcumuloCargos.GERAL]
        if servidor.eh_docente:
            publico.append(PeriodoDeclaracaoAcumuloCargos.DOCENTE)
        elif servidor.eh_tecnico_administrativo:
            publico.append(PeriodoDeclaracaoAcumuloCargos.TECNICO)
        else:
            return PeriodoDeclaracaoAcumuloCargos.objects.none()

        qs = PeriodoDeclaracaoAcumuloCargos.objects.filter(
            data_inicio__lte=datetime.datetime.today(), data_fim__gte=datetime.datetime.today(), publico__in=publico
        )
        return qs.filter(campus=servidor.campus)

    @staticmethod
    def pode_cadastrar_declaracao(servidor):
        if servidor:
            qs = PeriodoDeclaracaoAcumuloCargos.periodo_aberto_para_cadastro(servidor)
            if not qs.exists():
                return False  # não existe período aberto para o servidor
            return not qs.filter(declaracaoacumulacaocargo__servidor=servidor).exists()  # o servidor já tem uma declaração cadastrada no período
        return False


class DeclaracaoAcumulacaoCargo(models.ModelPlus):
    servidor = models.ForeignKeyPlus('rh.Servidor', verbose_name='Servidor', blank=False, null=False)
    periodo_declaracao_acumulo_cargo = models.ForeignKeyPlus(
        PeriodoDeclaracaoAcumuloCargos, verbose_name='Período de Declaração de Acumulação de Cargo', blank=False, null=False
    )

    nao_possui_outro_vinculo = models.BooleanField(
        'Não possuo qualquer outro vínculo ativo com a administração pública direta ou indireta nas esferas federal, estadual, distrital ou municipal, nem percebo proventos de aposentadoria, reforma ou pensão de nenhum órgão ou entidade da administração pública.',
        blank=False,
        null=False,
        default=False,
    )
    tem_outro_cargo_acumulavel = models.BooleanField(
        'Ocupo cargo público acumulável com compatibilidade de horários com o vínculo assumido com o IFRN, conforme disposto no Anexo I.',
        blank=False,
        null=False,
        default=False,
    )
    tem_aposentadoria = models.BooleanField(
        'Percebo proventos de aposentadoria devidamente acumuláveis com o cargo assumido no IFRN, conforme Anexo II.',
        blank=False,
        null=False,
        default=False,
    )
    tem_pensao = models.BooleanField(
        'Sou beneficiário de pensão, conforme informações prestadas em Anexo III.', blank=False, null=False, default=False
    )
    tem_atuacao_gerencial = models.BooleanField(
        'Tenho atuação gerencial em atividade mercantil, conforme informações prestadas em Anexo IV.', blank=False, null=False, default=False
    )
    exerco_atividade_remunerada_privada = models.BooleanField(
        'Exerço atividade remunerada privada, conforme informações prestadas em Anexo V.', blank=False, null=False, default=False
    )

    data_cadastro = models.DateTimeFieldPlus(auto_now_add=True, null=True)

    class Meta:
        ordering = ['servidor__pessoa_fisica__nome']
        verbose_name = 'Declaração de Acumulação de Cargos'
        verbose_name_plural = 'Declaração de Acumulação de Cargos'
        unique_together = ('servidor', 'periodo_declaracao_acumulo_cargo')
        permissions = (('pode_ver_declaracao', 'Pode ver Declaração'),)

    def __str__(self):
        return f'{self.servidor} - Declaração de {self.periodo_declaracao_acumulo_cargo.ano}'

    def pode_editar(self, servidor):
        return bool(self.periodo_declaracao_acumulo_cargo.periodo_aberto_para_cadastro(servidor).exists())

    def get_absolute_url(self):
        return f'/acumulocargo/ver_declaracao/{self.id}/'


class CargoPublicoAcumulavel(models.ModelPlus):
    declaracao = models.ForeignKeyPlus(DeclaracaoAcumulacaoCargo)
    orgao_lotacao = models.CharField('Orgão de Lotação', max_length=255, blank=True)
    uf = models.CharField('UF', max_length=5, blank=True)
    cargo_que_ocupa = models.CharField('Cargo/Emprego/Função que ocupa', max_length=255, blank=True)
    jornada_trabalho = models.CharField('Jornada de trabalho do cargo/emprego/função', max_length=255, blank=True)
    nivel_escolaridade = models.CharFieldPlus('Nível de escolaridade do cargo/emprego/função', max_length=255, blank=True)
    data_ingresso_orgao = models.DateFieldPlus('Data de ingresso no orgão', null=True, blank=True)
    situacao = models.CharFieldPlus('Situação', max_length=255, blank=True, help_text='Quadro ou Tabela: Permanente, Temporário, Comissionado, etc.')
    remuneracao = models.CharFieldPlus('Da Remuneração', max_length=255, blank=True, help_text='Vencimentos, Salários, Proventos, etc.')
    natureza_orgao = models.CharFieldPlus(
        'Natureza do Órgão', max_length=255, blank=True, help_text='Administração Direta, Autarquia, Empresa Pública ou Sociedade de Economia Mista'
    )
    subordinacao = models.CharFieldPlus('Subordinação', max_length=255, blank=True, help_text='Ministério, Secretaria de Estado/Município')
    esfera_governo = models.CharFieldPlus('Esfera do Governo', max_length=255, blank=True, help_text='Federal, Estadual ou Municipal')
    area_atuacao_cargo = models.CharFieldPlus(
        'Área de atuação do cargo', max_length=255, blank=True, help_text='Técnica/Científica, Saúde ou Magistério'
    )

    class Meta:
        verbose_name = 'Anexo I - Informações de Cargo/Emprego/Função ocupado em outro órgão'
        verbose_name_plural = 'Anexo I - Informações de Cargo/Emprego/Função ocupado em outro órgão'

    def __str__(self):
        return f'Cargo Acumulável - {self.declaracao}'


class TemAposentadoria(models.ModelPlus):
    declaracao = models.ForeignKeyPlus(DeclaracaoAcumulacaoCargo)
    cargo_origem_aposentadoria = models.CharField('Cargo que deu origem à aposentadoria', max_length=255, blank=True)
    uf = models.CharField('UF', max_length=5, blank=True)
    fundamento_legal = models.CharField('Fundamento legal da aposentadoria', max_length=255, blank=True)
    ato_legal = models.CharField('Ato legal da aposentadoria', max_length=255, blank=True)
    jornada_trabalho = models.CharFieldPlus('Jornada de trabalho do cargo que exerceu', max_length=255, blank=True)
    nivel_escolaridade = models.CharFieldPlus('Nível de escolaridade do cargo/emprego/função', max_length=255, blank=True)
    data_vigencia = models.DateFieldPlus('Data de vigência da aposentadoria', null=True, blank=True)
    area_atuacao_cargo = models.CharFieldPlus(
        'Área de atuação do cargo', max_length=255, blank=True, help_text='Técnica/Científica, Saúde ou Magistério'
    )
    natureza_orgao = models.CharFieldPlus(
        'Natureza do Órgão', max_length=255, blank=True, help_text='Administração Direta, Autarquia, Empresa Pública ou Sociedade de Economia Mista'
    )
    subordinacao = models.CharFieldPlus('Subordinação', max_length=255, blank=True, help_text='Ministério, Secretaria de Estado/Município')
    esfera_governo = models.CharFieldPlus('Esfera do Governo', max_length=255, blank=True, help_text='Federal, Estadual ou Municipal')

    class Meta:
        verbose_name = 'Anexo II - Informações de Aposentadoria em outro órgão'
        verbose_name_plural = 'Anexo II - Informações de Aposentadoria em outro órgão'

    def __str__(self):
        return f'Tem Aposentadoria - {self.declaracao}'


class TemPensao(models.ModelPlus):
    declaracao = models.ForeignKeyPlus(DeclaracaoAcumulacaoCargo)
    tipo_pensao = models.CharField('Tipo de pensão', max_length=255, blank=True)
    fundamento_legal = models.CharField('Fundamento legal da pensão', max_length=255, blank=True)
    grau_parentesco = models.CharField('Grau de parentesco com o instituidor de pensão', max_length=255, blank=True)
    data_inicio_concessao = models.DateFieldPlus('Data de início de concessão do benefício', null=True, blank=True)
    dependencia_economica = models.CharFieldPlus(
        'Dependência econômica', max_length=255, blank=True, help_text='Certidão de casamento, nascimento, declaração de IR, etc'
    )

    class Meta:
        verbose_name = 'Anexo III - Informações sobre Pensão Civil em outro órgão'
        verbose_name_plural = 'Anexo III - Informações sobre Pensão Civil em outro órgão'

    def __str__(self):
        return f'Tem Pensão - {self.declaracao}'


class TemAtuacaoGerencial(models.ModelPlus):
    declaracao = models.ForeignKeyPlus(DeclaracaoAcumulacaoCargo)
    empresa_que_atua = models.CharFieldPlus('Empresa em que atua', max_length=255, blank=True)
    tipo_atuacao_gerencial = models.CharFieldPlus('Tipo de atuação gerencial', max_length=255, blank=True)
    tipo_sociedade_mercantil = models.CharFieldPlus('Tipo de sociedade mercantil', max_length=255, blank=True)
    descricao_atividade_exercida = models.CharFieldPlus('Descrição da atividade comercial exercida', max_length=255, blank=True)
    qual_participacao_societaria = models.CharFieldPlus('Qual a participação societária', max_length=255, blank=True)
    data_inicio_atuacao = models.DateFieldPlus('Data de início da atuação', max_length=255, blank=True, null=True)
    nao_exerco_atuacao_gerencial = models.BooleanField('NÃO exerço qualquer atuação gerencial em atividade mercantil', blank=True, default=False)
    nao_exerco_comercio = models.BooleanField('NÃO exerço comércio', blank=True, default=False)

    class Meta:
        verbose_name = 'Anexo IV - Informações sobre atuação gerencial em atividades mercantil'
        verbose_name_plural = 'Anexo IV - Informações sobre atuação gerencial em atividades mercantil'

    def __str__(self):
        return f'Tem Atuação Gerencial - {self.declaracao}'


class ExerceAtividadeRemuneradaPrivada(models.ModelPlus):
    declaracao = models.ForeignKeyPlus(DeclaracaoAcumulacaoCargo)
    nome_empresa_trabalha = models.CharFieldPlus('Nome da empresa onde trabalha/Empregador', max_length=255, blank=True)
    funcao_emprego_ocupado = models.CharFieldPlus('Função ou emprego ocupado(tipo de atividade desempenhada)', max_length=255, blank=True)
    jornada_trabalho = models.CharFieldPlus('Jornada de trabalho semanal a que está submetido', max_length=255, blank=True)
    nivel_escolaridade_funcao = models.CharFieldPlus('Nível de escolaridade da função/emprego', max_length=255, blank=True)
    data_inicio_atividade = models.DateFieldPlus('Data de início da atividade remunerada privada', max_length=255, blank=True, null=True)
    nao_exerco_atividade_remunerada = models.BooleanField('NÃO exerço qualquer atividade remunerada privada', blank=True, default=False)

    class Meta:
        verbose_name = 'Anexo V - Informações sobre atividade remunerada privada'
        verbose_name_plural = 'Anexo V - Informações sobre atividade remunerada privada'

    def __str__(self):
        return f'Exerce Atividadde Remunerada Privada - {self.declaracao}'
