import datetime

from djtools.db import models
from edu.managers import FiltroUnidadeOrganizacionalManager
from edu.models.logs import LogModel


class ConfiguracaoSeguro(LogModel):
    seguradora = models.ForeignKeyPlus('rh.PessoaJuridica')
    ativa = models.BooleanField('Ativa', default=True)
    valor_contrato = models.DecimalFieldPlus('Valor do Contrato')
    data_inicio_contrato = models.DateFieldPlus('Data de Início do Contrato')
    data_fim_contrato = models.DateFieldPlus('Data de Término do Contrato')
    valor_repasse_pessoa = models.DecimalFieldPlus('Valor do Repasse por Pessoa', decimal_places=5)
    fiscais = models.ManyToManyFieldPlus('rh.Servidor', verbose_name='Fiscais')
    email_disparo_planilha = models.CharField(
        'E-mails para Envio da Planilha', max_length=300, help_text='Os e-mails devem ser separados por vírgula'
    )

    def get_saldo_restante(self):
        return self.valor_contrato - self.get_valor_utilizacao_planejada_recurso()

    def get_saldo_executado_restante(self):
        return self.valor_contrato - self.get_valor_utilizacao_real_recurso()

    def get_saldo_planejado_restante(self):
        return self.valor_contrato - self.get_valor_utilizacao_planejada_recurso()

    def get_valor_utilizacao_real_recurso(self):
        total = 0
        aulas_campo_realizadas = self.aulacampo_set.filter(situacao=AulaCampo.SITUACAO_REALIZADA)

        for aula_campo in aulas_campo_realizadas:
            total += aula_campo.get_valor_seguro()

        return total

    def get_valor_utilizacao_planejada_recurso(self):
        total = 0
        aulas_campo_planejadas = self.aulacampo_set.exclude(situacao=AulaCampo.SITUACAO_CANCELADA)

        for aula_campo in aulas_campo_planejadas:
            total += aula_campo.get_valor_seguro()

        return total

    def get_utilizacao_real_por_mes_recurso(self):
        meses_valores = []
        qs = self.aulacampo_set.filter(situacao=AulaCampo.SITUACAO_REALIZADA)
        meses_utilizacao = qs.dates('data_partida', 'month')

        for mes_utilizacao in meses_utilizacao:
            valor = 0
            aulas_campo = qs.filter(data_partida__month=mes_utilizacao.month)

            for aula_campo in aulas_campo:
                valor += aula_campo.get_valor_seguro()
            meses_valores.append([mes_utilizacao, valor])
        return meses_valores

    def get_utilizacao_planejada_por_mes_recurso(self):
        meses_valores = []
        qs = self.aulacampo_set.exclude(situacao=AulaCampo.SITUACAO_CANCELADA)
        meses_utilizacao = qs.dates('data_partida', 'month')

        for mes_utilizacao in meses_utilizacao:
            valor = 0
            aulas_campo = qs.filter(data_partida__month=mes_utilizacao.month)

            for aula_campo in aulas_campo:
                valor += aula_campo.get_valor_seguro()
            meses_valores.append([mes_utilizacao, valor])
        return meses_valores

    # Verificação no momento da criação ou edição da aula de campo.
    def possui_saldo_suficiente(self, valor):
        return self.get_saldo_restante() >= valor

    def get_participantes_disponiveis(self, qtd_dias):
        return self.get_saldo_restante() / self.valor_repasse_pessoa / qtd_dias

    def get_porcentagem_utilizacao_real_recurso(self):
        return int(self.get_valor_utilizacao_real_recurso() * 100 / self.valor_contrato)

    def get_porcentagem_utilizacao_planejada_recurso(self):
        return int(self.get_valor_utilizacao_planejada_recurso() * 100 / self.valor_contrato)

    def get_porcentagem_periodo_executado(self):
        qtd_dias_total = self.get_qtd_dias_total()
        if qtd_dias_total == 0:
            return 0

        percentual = int(self.get_qtd_dias_executado() * 100 / qtd_dias_total)
        if percentual > 100:
            return 100
        if percentual < 0:
            return 0
        return percentual

    def get_qtd_dias_total(self):
        return (self.data_fim_contrato - self.data_inicio_contrato).days

    def get_qtd_dias_executado(self):
        return (datetime.date.today() - self.data_inicio_contrato).days

    def __str__(self):
        return '{} - Vigência: {} a {}'.format(
            self.seguradora, self.data_inicio_contrato.strftime('%d/%m/%Y'), self.data_fim_contrato.strftime('%d/%m/%Y')
        )

    def get_absolute_url(self):
        return f'/edu/configuracaoseguro/{self.pk:d}/'

    class Meta:
        verbose_name = 'Configuração de Seguro'
        verbose_name_plural = 'Configurações de Seguro'


class AulaCampo(LogModel):
    SITUACAO_AGENDADA = 1
    SITUACAO_REALIZADA = 2
    SITUACAO_CANCELADA = 3
    SITUACAO_CHOICES = [[SITUACAO_AGENDADA, 'Agendada'], [SITUACAO_REALIZADA, 'Realizada'], [SITUACAO_CANCELADA, 'Cancelada']]

    configuracao_seguro = models.ForeignKeyPlus('edu.ConfiguracaoSeguro')
    uo = models.ForeignKeyPlus('rh.UnidadeOrganizacional', verbose_name='Campus', on_delete=models.CASCADE)
    descricao = models.CharFieldPlus('Descrição')
    finalidade = models.TextField('Finalidade')
    roteiro = models.TextField('Roteiro')
    data_partida = models.DateFieldPlus('Data de Partida')
    data_chegada = models.DateFieldPlus('Data de Chegada')
    responsaveis = models.ManyToManyFieldPlus('rh.Servidor', verbose_name='Responsáveis')
    alunos = models.ManyToManyFieldPlus('edu.Aluno', through='edu.AlunoAulaCampo')
    situacao = models.IntegerField(choices=SITUACAO_CHOICES, default=SITUACAO_AGENDADA, verbose_name='Situação')

    objects = models.Manager()
    locals = FiltroUnidadeOrganizacionalManager('uo')

    def get_valor_seguro(self):
        qtd_dias = (self.data_chegada - self.data_partida).days + 1
        total = (self.responsaveis.all().count() + self.alunos.all().count()) * qtd_dias * self.configuracao_seguro.valor_repasse_pessoa

        return total

    def get_absolute_url(self):
        return f'/edu/aulacampo/{self.pk:d}/'

    def __str__(self):
        return self.descricao

    class Meta:
        verbose_name = 'Aula de Campo'
        verbose_name_plural = 'Aulas de Campo'


class AlunoAulaCampo(LogModel):
    aluno = models.ForeignKeyPlus('edu.Aluno', null=False, verbose_name='Aluno', on_delete=models.CASCADE)
    aula_campo = models.ForeignKeyPlus('edu.AulaCampo', null=False, verbose_name='Aula de Campo', on_delete=models.CASCADE)

    def __str__(self):
        return f'{self.aluno} - {self.aula_campo}'

    class Meta:
        verbose_name = 'Vínculo de Aluno em Aula de Campo'
        verbose_name_plural = 'Vínculos de Aluno em Aula de Campo'
