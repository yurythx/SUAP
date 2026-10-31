from collections import OrderedDict
from datetime import date, timedelta

from django.db.models import Exists, OuterRef, Prefetch

from djtools.db import models
from djtools.templatetags.filters import format_daterange
from djtools.utils import contar_dias_uteis, datas_entre, intervalo_intersecao


class Ferias(models.ModelPlus):
    """
    Representa as férias do Servidor
    """

    PENDENTE = 0
    VALIDADO = 1
    INVALIDADO = 2
    VALIDACAO_CHOICES = [[PENDENTE, 'Pendente'], [VALIDADO, 'Validado'], [INVALIDADO, 'Invalidado']]

    GRATIFICACAO_NATALINA_CHOICES = [[0, 'Sem Adiantamento'], [1, 'Período 1'], [2, 'Período 2'], [3, 'Período 3']]

    SETENTA_PORCENTO_CHOICES = [
        [0, 'Sem Adiantamento'],
        [1, 'Período 1'],
        [2, 'Período 2'],
        [3, 'Período 3'],
        [4, 'Períodos 1 e 2'],
        [5, 'Períodos 1 e 3'],
        [6, 'Períodos 2 e 3'],
        [7, 'Períodos 1, 2 e 3'],
    ]

    servidor = models.ForeignKeyPlus('rh.Servidor', null=False, blank=False, on_delete=models.CASCADE)
    ano = models.ForeignKeyPlus('comum.Ano', null=False, blank=False, on_delete=models.CASCADE)
    """
    @TODO: Retirar essas datas quando todos usarem o webservice
    """
    data_inicio_periodo1 = models.DateFieldPlus('Data de Início do Período 1', null=True, blank=True, db_index=True)
    data_fim_periodo1 = models.DateFieldPlus('Data de Fim do Período 1', null=True, blank=True, db_index=True)
    data_inicio_periodo2 = models.DateFieldPlus('Data de Início do Período 2', null=True, blank=True, db_index=True)
    data_fim_periodo2 = models.DateFieldPlus('Data de Fim do Período 2', null=True, blank=True, db_index=True)
    data_inicio_periodo3 = models.DateFieldPlus('Data de Início do Período 3', null=True, blank=True, db_index=True)
    data_fim_periodo3 = models.DateFieldPlus('Data de Fim do Período 3', null=True, blank=True, db_index=True)

    quitacao = models.PositiveIntegerField(null=True)

    criado_em = models.DateTimeFieldPlus(null=True)
    criado_por = models.ForeignKeyPlus('comum.User', related_name='criado_por', null=True, blank=True, editable=False, on_delete=models.CASCADE)
    observacao_criacao = models.TextField('Observação', blank=True)

    validado_em = models.DateTimeFieldPlus(null=True)
    validado_por = models.ForeignKeyPlus('comum.User', related_name='validado_por', null=True, blank=True, editable=False, on_delete=models.CASCADE)
    observacao_validacao = models.TextField('Observação Chefia', blank=True)

    cadastrado_em = models.DateTimeFieldPlus(null=True)

    gratificacao_natalina = models.PositiveIntegerField('Gratificação Natalina', default=0, choices=GRATIFICACAO_NATALINA_CHOICES)
    setenta_porcento = models.PositiveIntegerField(
        'Setenta Porcento',
        default=0,
        choices=SETENTA_PORCENTO_CHOICES,
        help_text='Adiantamento de 70% do salário, proporcional à parcela de férias (desconto integral após 02 meses do recebimento): Caso deseje esta opção, fazer a solicitação no campo acima, especificando em qual ou quais parcelas deseja o adiantamento.',
    )

    validado = models.PositiveIntegerField('Validado', default=0, choices=VALIDACAO_CHOICES)
    cadastrado = models.BooleanField(default=False)
    atualiza_pelo_extrator = models.BooleanField('Atualiza pelo Extrator?', default=True)

    class Meta:
        unique_together = ('servidor', 'ano')
        ordering = ('servidor__pessoa_fisica__nome', '-ano')
        verbose_name = 'Férias'
        verbose_name_plural = 'Férias'

        permissions = (
            ('pode_ver_listagem_ferias', 'Pode ver a listagem de férias'),
            ('pode_validar_ferias', 'Pode validar férias'),
            ('pode_ver_calendario_ferias_setor', 'Pode ver calendário de férias'),
            ('pode_gerar_arquivo_batch_ferias', 'Pode gerar arquivo batch de férias'),
        )

    def __str__(self):
        return f'{self.servidor.pessoa_fisica.nome} (Mat.: {self.servidor.matricula}) - Férias de {self.ano}'

    def get_absolute_url(self):
        return f'/ferias/{self.ano}/{self.servidor.matricula}/'

    # TODO: Retirar metodo quando quando nao usar mais extrator para férias
    def dias_ferias_periodo1(self):
        if self.data_inicio_periodo1:
            return (self.get_fim_periodo1() - self.data_inicio_periodo1).days + 1
        return 0

    # TODO: Retirar metodo quando quando nao usar mais extrator para férias
    def dias_ferias_periodo2(self):
        if self.data_inicio_periodo2:
            return (self.get_fim_periodo2() - self.data_inicio_periodo2).days + 1
        return 0

    # TODO: Retirar metodo quando quando nao usar mais extrator para férias
    def dias_ferias_periodo3(self):
        if self.data_inicio_periodo3:
            return (self.get_fim_periodo3() - self.data_inicio_periodo3).days + 1
        return 0

    # TODO: Retirar metodo quando quando nao usar mais extrator para férias
    def get_situacao_periodo1(self):
        hoje = date.today()
        if self.data_inicio_periodo1 and self.data_inicio_periodo1 > hoje:
            return 'PROGRAMADA'
        elif self.data_inicio_periodo1 and self.data_inicio_periodo1 <= hoje and self.data_fim_periodo1 >= hoje:
            return 'EM EXECUÇÃO'
        elif self.data_fim_periodo1 and self.data_fim_periodo1 < hoje:
            if self.get_interrupcoes_ferias_periodo_1():
                return 'INTERROMPIDA'
            return 'ENCERRADA'

    # TODO: Retirar metodo quando quando nao usar mais extrator para férias
    def get_situacao_periodo2(self):
        hoje = date.today()
        if self.data_inicio_periodo2 > hoje:
            return 'PROGRAMADA'
        elif self.data_inicio_periodo2 <= hoje and self.data_fim_periodo2 >= hoje:
            return 'EM EXECUÇÃO'
        elif self.data_fim_periodo2 < hoje:
            if self.get_interrupcoes_ferias_periodo_2():
                return 'INTERROMPIDA'
            return 'ENCERRADA'

    # TODO: Retirar metodo quando quando nao usar mais extrator para férias
    def get_situacao_periodo3(self):
        hoje = date.today()
        if self.data_inicio_periodo3 > hoje:
            return 'PROGRAMADA'
        elif self.data_inicio_periodo3 <= hoje and self.data_fim_periodo3 >= hoje:
            return 'EM EXECUÇÃO'
        elif self.data_fim_periodo3 < hoje:
            if self.get_interrupcoes_ferias_periodo_3():
                return 'INTERROMPIDA'
            return 'ENCERRADA'

    # TODO: Retirar metodo quando quando nao usar mais extrator para férias
    def get_fim_periodo1(self):
        if self.data_inicio_periodo1 and self.data_fim_periodo1:
            if self.get_interrupcoes_ferias_periodo_1():
                return self.get_interrupcoes_ferias_periodo_1()[0].data_interrupcao_periodo - timedelta(days=1)
            return self.data_fim_periodo1
        return ' - '

    # TODO: Retirar metodo quando quando nao usar mais extrator para férias
    def get_fim_periodo2(self):
        if self.data_inicio_periodo2 and self.data_fim_periodo2:
            if self.get_interrupcoes_ferias_periodo_2():
                return self.get_interrupcoes_ferias_periodo_2()[0].data_interrupcao_periodo - timedelta(days=1)
            return self.data_fim_periodo2
        return ' - '

    # TODO: Retirar metodo quando quando nao usar mais extrator para férias
    def get_fim_periodo3(self):
        if self.data_inicio_periodo3 and self.data_fim_periodo3:
            if self.get_interrupcoes_ferias_periodo_3():
                return self.get_interrupcoes_ferias_periodo_3()[0].data_interrupcao_periodo - timedelta(days=1)
            return self.data_fim_periodo3
        return ' - '

    # TODO: Retirar metodo quando quando nao usar mais extrator para férias
    def get_interrupcoes_ferias_periodo_1(self):
        interrupcoes_periodo = []
        inicio = self.data_inicio_periodo1
        fim = self.data_fim_periodo1

        if inicio and fim:
            for interrupcao in self.interrupcaoferias_set.all().order_by('data_interrupcao_periodo'):
                if inicio <= interrupcao.data_interrupcao_periodo <= fim:
                    interrupcoes_periodo.append(interrupcao)
                    inicio = interrupcao.data_inicio_continuacao_periodo
                    fim = interrupcao.data_fim_continuacao_periodo
        return interrupcoes_periodo

    # TODO: Retirar metodo quando quando nao usar mais extrator para férias
    def get_interrupcoes_ferias_periodo_2(self):
        interrupcoes_periodo = []
        inicio = self.data_inicio_periodo2
        fim = self.data_fim_periodo2

        if inicio and fim:
            if self.interrupcaoferias_set.all().exists():
                for interrupcao in self.interrupcaoferias_set.all().order_by('data_interrupcao_periodo'):
                    if inicio <= interrupcao.data_interrupcao_periodo <= fim:
                        interrupcoes_periodo.append(interrupcao)
                        inicio = interrupcao.data_inicio_continuacao_periodo
                        fim = interrupcao.data_fim_continuacao_periodo
        return interrupcoes_periodo

    # TODO: Retirar metodo quando quando nao usar mais extrator para férias
    def get_interrupcoes_ferias_periodo_3(self):
        interrupcoes_periodo = []
        inicio = self.data_inicio_periodo3
        fim = self.data_fim_periodo3

        if inicio and fim:
            if self.interrupcaoferias_set.all().exists():
                for interrupcao in self.interrupcaoferias_set.all().order_by('data_interrupcao_periodo'):
                    if inicio <= interrupcao.data_interrupcao_periodo <= fim:
                        interrupcoes_periodo.append(interrupcao)
                        inicio = interrupcao.data_inicio_continuacao_periodo
                        fim = interrupcao.data_fim_continuacao_periodo
        return interrupcoes_periodo

    def get_status(self):
        if self.cadastrado:
            return 'Cadastrado no Siape'

        elif self.validado == 0:
            return 'Aguardando validação da chefia'

        elif self.validado == 1:
            return 'Validado pela chefia'

        elif self.validado == 2:
            return 'Invalidado pela chefia'

        return ' - '

    """
        Método que retorna os dias de férias dos períodos configurados (3 períodos por padrão)
        Este método calcula de forma correta as interrupções de interrupção
        """

    def get_dias_ferias(self):
        dias_dict = OrderedDict()
        for parcela in self.parcelaferias_set.all():
            for dia in datas_entre(parcela.data_inicio, parcela.data_fim):
                dias_dict[dia] = dia
        if not dias_dict:
            periodos = 3
            for ra in range(1, periodos + 1):
                inicio = getattr(self, f'data_inicio_periodo{ra}', None)
                fim = getattr(self, f'data_fim_periodo{ra}', None)

                # dias de férias do primeiro período
                if inicio and fim:
                    for dia in datas_entre(inicio, fim):
                        dias_dict[dia] = {'dia': dia}

                    # verificando as interrupções
                    for i in self.interrupcaoferias_set.all():
                        if inicio <= i.data_interrupcao_periodo <= fim:
                            for r in datas_entre(i.data_interrupcao_periodo, fim):
                                # removendo dias interrompidos
                                del dias_dict[r]
                            # adicionando o novo período da continuação da interrupção
                            for a in datas_entre(i.data_inicio_continuacao_periodo, i.data_fim_continuacao_periodo):
                                dias_dict[a] = {'dia': a}
                            inicio = i.data_inicio_continuacao_periodo
                            fim = i.data_fim_continuacao_periodo

        return dias_dict

    @classmethod
    def pessoa_estava_de_ferias_no_dia(cls, servidor, dia):
        return dia in list(cls.get_dias_pessoa_estava_de_ferias_periodo(servidor, dia, dia).keys())

    @classmethod
    def pessoa_estava_de_ferias_periodo(self, servidor, data_ini, data_fim):
        return self.get_dias_pessoa_estava_de_ferias_periodo(servidor, data_ini, data_fim)

    @classmethod
    def get_ferias_no_periodo(self, servidor, data_ini, data_fim):
        # A implementação do método anterior foi retirada devido a uma ação judicial.
        """
        parcela         |------------------------------------|

        período 1  |------------------------------------------------|
        período 2  |-----------------------------------|
        período 3           |---------------------------------------------|
        período 4             |--------------------------|

        parcela no período?
            parcela.data_inicio <= data_fim and parcela.data_fim >= data_ini
        """

        ferias_com_parcela_no_intervalo = (
            Ferias.objects.filter(servidor=servidor)
            .annotate(
                tem_parcela_no_intervalo=Exists(
                    ParcelaFerias.objects.filter(ferias=OuterRef('pk'), data_inicio__lte=data_fim, data_fim__gte=data_ini)
                )
            )
            .filter(tem_parcela_no_intervalo=True)
        )

        return ferias_com_parcela_no_intervalo

    @classmethod
    def get_dias_pessoa_estava_de_ferias_periodo(self, servidor, data_ini, data_fim):
        ferias = {}
        ferias_qs = (
            self.get_ferias_no_periodo(servidor, data_ini, data_fim)
            .select_related('servidor', 'ano')
            .prefetch_related(Prefetch('parcelaferias_set', queryset=ParcelaFerias.objects.all().only('data_inicio', 'data_fim')))
        )
        for fe in ferias_qs:
            for dia_ferias in list(fe.get_dias_ferias().keys()):
                atual = ferias.get(dia_ferias, [])
                atual.append(str(fe))
                ferias[dia_ferias] = atual

        return ferias

    @classmethod
    def get_periodos_pessoa_estava_de_ferias(self, servidor, data_ini, data_fim):
        dias = sorted(Ferias.get_dias_pessoa_estava_de_ferias_periodo(servidor, data_ini, data_fim).items())
        if not dias:
            return []

        intervalos = []

        periodo_inicial = None
        periodo_final = None
        data_anterior = None
        primeiro = True
        for data, ferias in dias:
            if data_ini <= data <= data_fim:
                legenda = ''
                for obj in ferias:
                    legenda += len(obj.split(' - ')) == 2 and obj.split(' - ')[1] or obj

                if primeiro:
                    primeiro = False
                    data_anterior = data
                    periodo_inicial = data
                    periodo_final = data
                    continue

                if data != data_anterior + timedelta(days=1):  # fechou o período, precisamos iniciar um novo período, atualizando o periodo_inicial
                    intervalos.append((periodo_inicial, periodo_final, legenda))
                    periodo_inicial = data
                    periodo_final = data
                else:
                    # continua no mesmo período, devemos atualizar o periodo_final
                    periodo_final = data

                data_anterior = data

        # inserindo o último
        if periodo_inicial and periodo_final:
            t = (periodo_inicial, periodo_final, legenda)
            if t not in intervalos:
                intervalos.append((periodo_inicial, periodo_final, legenda))

        return intervalos


class ParcelaFerias(models.ModelPlus):
    ferias = models.ForeignKeyPlus('ferias.Ferias', null=False, blank=False, on_delete=models.CASCADE)
    numero_parcela = models.CharFieldPlus('Número da Parcela')
    data_inicio = models.DateFieldPlus('Data de Início Parcela', db_index=True)
    data_fim = models.DateFieldPlus('Data de Fim Parcela', db_index=True)

    setenta_porcento = models.BooleanField(
        'Adiantamento de Setenta Porcento?',
        default=False,
        help_text='Adiantamento de 70% do salário, proporcional à parcela de férias (desconto integral após 02 '
        'meses do recebimento): Caso deseje esta opção, fazer a solicitação no campo acima, especificando '
        'em qual ou quais parcelas deseja o adiantamento.',
    )
    adiantamento_gratificacao_natalina = models.BooleanField('Adiantamento de Gratificação Natalina?', default=False)
    continuacao_interrupcao = models.BooleanField('É a continuação de uma interrupção de férias?', default=False)
    parcela_interrompida = models.BooleanField('A parcela foi interrompida?', default=False)

    class Meta:
        ordering = ('ferias', 'numero_parcela')
        verbose_name = 'Parcela de Férias'
        verbose_name_plural = 'Parcelas de Férias'
        unique_together = ('ferias', 'numero_parcela')

    def __str__(self):
        return f'Parcela {self.numero_parcela} de Férias {self.ferias.ano} - {self.ferias.servidor}'

    @property
    def dias(self):
        return (self.data_fim - self.data_inicio).days + 1

    @property
    def servidor(self):
        return self.ferias.servidor

    @property
    def jornada_trabalho_diaria(self):
        return self.servidor.jornada_trabalho.get_jornada_trabalho_diaria()

    def dias_uteis(self, data_inicio=None, data_terminio=None):
        if data_inicio and data_terminio:
            (data_inicio, data_terminio) = intervalo_intersecao(data_inicio, data_terminio, self.data_inicio, self.data_fim)
            return contar_dias_uteis(data_inicio, data_terminio)
        return contar_dias_uteis(self.data_inicio, self.data_fim, self.servidor.setor_exercicio.uo)

    def ch_intervalo(self, data_inicial=None, data_final=None):
        dias_uteis = self.dias_uteis(data_inicial, data_final)
        return self.jornada_trabalho_diaria * dias_uteis

    @property
    def situacao(self):
        hoje = date.today()
        if self.data_inicio > hoje:
            return 'PROGRAMADA'
        elif self.data_inicio <= hoje and self.data_fim >= hoje:
            return 'EM EXECUÇÃO'
        elif self.data_fim < hoje and self.parcela_interrompida:
            return 'INTERROMPIDA'
        return 'ENCERRADA'

    def duracao_em_horas(self):
        if self.ferias.servidor.jornada_trabalho:
            return self.dias_uteis() * self.ferias.servidor.jornada_trabalho.get_jornada_trabalho_diaria()
        return 0


class InterrupcaoFerias(models.ModelPlus):
    ferias = models.ForeignKeyPlus('ferias.Ferias', null=False, blank=False, on_delete=models.CASCADE)
    data_interrupcao_periodo = models.DateFieldPlus('Data de Interrupção do Período', null=True)
    data_inicio_continuacao_periodo = models.DateFieldPlus('Data de Início da Continuação', null=True)
    data_fim_continuacao_periodo = models.DateFieldPlus('Data Fim da Continuação', null=True)

    class Meta:
        verbose_name = 'Interrução de Férias'
        verbose_name_plural = 'Interrupções de Férias'
        unique_together = ('ferias', 'data_interrupcao_periodo')
        ordering = ('ferias', 'data_interrupcao_periodo')

    def __str__(self):
        return f'Interrupção de Férias {self.ferias.ano} - {self.ferias.servidor}'

    def tem_interrupcao_da_continuidade(self):
        for i in InterrupcaoFerias.objects.filter(ferias=self.ferias):
            if self.data_inicio_continuacao_periodo <= i.data_interrupcao_periodo <= self.data_fim_continuacao_periodo:
                return True
        return False

    def get_data_fim(self):
        for i in InterrupcaoFerias.objects.filter(ferias=self.ferias):
            if self.data_inicio_continuacao_periodo <= i.data_interrupcao_periodo <= self.data_fim_continuacao_periodo:
                return i.data_interrupcao_periodo - timedelta(days=1)
        return self.data_fim_continuacao_periodo

    def dias_ferias(self):
        return (self.get_data_fim() - self.data_inicio_continuacao_periodo).days + 1

    def get_periodo_continuacao_ferias(self):
        if self.data_inicio_continuacao_periodo and self.data_fim_continuacao_periodo:
            return format_daterange(self.data_inicio_continuacao_periodo, self.data_fim_continuacao_periodo)
        return ' - '

    def get_situacao(self):
        hoje = date.today()
        if self.data_inicio_continuacao_periodo > hoje:
            return 'PROGRAMADA'
        elif self.data_inicio_continuacao_periodo <= hoje and self.data_fim_continuacao_periodo >= hoje:
            return 'EM EXECUÇÃO'
        elif self.data_fim_continuacao_periodo < hoje:
            if self.tem_interrupcao_da_continuidade():
                return 'INTERROMPIDA'
            return 'ENCERRADA'
