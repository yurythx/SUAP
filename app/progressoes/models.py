import base64
import datetime
import hashlib
import logging
from datetime import timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.template.defaultfilters import pluralize

from comum import utils
from comum.models import Configuracao
from comum.utils import get_setor, tl
from djtools.db import models
from djtools.utils import periodos_sucessivos, print_, send_notification
from progressoes import assinatura
from rh.models import AfastamentoSiape, PadraoVencimento, Servidor, ServidorAfastamento, Setor, Situacao, UnidadeOrganizacional

logger = logging.getLogger(__name__)


#
# Representa o processo de progressão do servidor, desde o estado inicial até o final (aprovado ou reprovado)
#
class ProcessoProgressao(models.ModelPlus):
    TIPO_PROGRESSAO_MERITO = 1
    TIPO_ESTAGIO_PROBATORIO = 2
    TIPO_CHOICES = [[TIPO_PROGRESSAO_MERITO, 'Progressão Funcional por Mérito'], [TIPO_ESTAGIO_PROBATORIO, 'Estágio Probatório']]

    STATUS_A_INICIAR = 0
    STATUS_EM_TRAMITE = 1
    STATUS_FINALIZADO = 2
    STATUS_CHOICES = [[STATUS_A_INICIAR, 'A iniciar'], [STATUS_EM_TRAMITE, 'Em trâmite'], [STATUS_FINALIZADO, 'Finalizado']]

    SITUACAO_FINAL_NAO_FINALIZADO = 0
    SITUACAO_FINAL_APROVADO = 1
    SITUACAO_FINAL_REPROVADO = 2

    data_inicio_contagem_progressao = models.DateField('Data Início da Contagem', help_text='Início do período da contagem da progressão.')
    data_fim_contagem_progressao = models.DateField(
        'Data Final da Contagem',
        help_text='Final do período da contagem da progressão. '
        'Essa data será igual a '
        'Data início da contagem + '
        'meses de interstício + '
        'afastamentos no período da contagem (se for o caso).',
    )
    avaliado = models.ForeignKeyPlus('rh.Servidor', null=False, verbose_name='Avaliado', on_delete=models.CASCADE)
    status = models.IntegerField(
        'Status do Processo', choices=STATUS_CHOICES, default=STATUS_A_INICIAR, help_text='Indica a situação atual do processo de progressão.'
    )
    tipo = models.IntegerField('Tipo do Processo', choices=TIPO_CHOICES, default=TIPO_PROGRESSAO_MERITO)

    padrao_anterior = models.ForeignKeyPlus(
        'rh.PadraoVencimento', null=True, on_delete=models.CASCADE, related_name='padrao_anterior', verbose_name='Padrão de Vencimento Atual'
    )
    padrao_novo = models.ForeignKeyPlus(
        'rh.PadraoVencimento', null=True, on_delete=models.CASCADE, related_name='padrao_novo', verbose_name='Padrão de Vencimento Novo'
    )
    media_processo = models.DecimalField('Média do Processo', default=0, decimal_places=2, max_digits=12)

    protocolo = models.ForeignKeyPlus('protocolo.Processo', verbose_name='Protocolo', blank=True, null=True, on_delete=models.SET_NULL)
    processo_eletronico = models.ForeignKeyPlus(
        'processo_eletronico.Processo', verbose_name='Processo Eletrônico', blank=True, null=True, on_delete=models.SET_NULL
    )

    registro_a_progredir = models.ForeignKeyPlus(
        'progressoes.ServidorAProgredir', verbose_name='Registros a Progredir', on_delete=models.SET_NULL, null=True, blank=True
    )
    ids_afastamentos_utilizados = models.CharFieldPlus('Afastamentos Utilizados', max_length=5000, null=True, blank=True)
    #
    intersticio_ajustado_novo_periodo = models.BooleanField('Interstício Ajustado com Novo Período?', default=False)
    # data de finalização do processo
    data_finalizacao = models.DateTimeField('Data de Finalização', null=True, blank=True)
    #
    # Saldos (LEI Nº 15.141, DE 2 DE JUNHO DE 2025)
    # § 6º O saldo remanescente do interstício referente à progressão por mérito
    # profissional anterior a 1º de janeiro de 2025, independentemente do momento
    # em que venha a ser concedida a progressão, será considerado, uma única vez,
    # para fins de concessão da progressão por mérito subsequente." (NR)
    dias_saldo = models.PositiveIntegerField(default=0, help_text='Saldo remanescente para progressão por mérito.')
    saldo_usado = models.BooleanField('Saldo Usado?', default=False, help_text='Indica se o saldo remanescente foi usado na progressão.')
    #
    nao_permitir_recalculo_data_fim = models.BooleanField(
        'Não Permitir Recalculo da Data Fim?',
        default=False,
        help_text='Indica se o recalculo da data fim está ignorado ao finalizar o processo de progressão.',
    )

    def __str__(self):
        return f'Avaliado: {self.avaliado} - Situação: {self.get_status_display()}'

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.observacoes_list = []
        self.id_afast_interrompem_tempo_servidor_list = []
        self.ultima_progressao = []
        self.ultimo_pca = []

    def save(self, *args, **kwargs):
        if not self.id:
            # calcula data final da contagem
            self.calcular_data_de_progressao()
        super().save()
        if self.observacoes_list:
            for i in self.observacoes_list:
                obs = ObservacaoAfastamentoEfetivoExercicio()
                obs.processo = self
                obs.data_afetada = i.get('data_afetada')
                obs.qtd_dias_afastamento = i.get('qtd_dias')
                obs.save()
                obs.afastamentos.add(*i.get('lista_afastamentos'))

    # Saldo
    @property
    def tem_saldo(self):
        """
        Retorna True se houver saldo remanescente de interstício.
        O saldo é considerado válido se não foi usado e se há pelo menos um mês ou um dia de saldo.
        """
        return not self.saldo_usado and self.dias_saldo > 0

    @property
    def saldo_formatado(self):
        return f'{self.dias_saldo} di{pluralize(self.dias_saldo, "a,as")} de saldo'

    @property
    def data_fim_ajustada(self):
        """
        Retorna a data de fim ajustada com o saldo de interstício (meses e dias),
        subtraindo esse saldo da data_fim original se houver saldo disponível e não utilizado.
        Caso contrário, retorna a data_fim original.
        """
        if self.tem_saldo:
            return self.data_fim_contagem_progressao - relativedelta(days=self.dias_saldo)
        return self.data_fim_contagem_progressao

    def calculando_saldo(self):
        if self.data_inicio_contagem_progressao.year != 2023:
            return None

        if not self.registro_a_progredir or not getattr(self.avaliado, 'ativo', False):
            return None

        referencia = datetime.date(2024, 12, 31)
        inicio = self.data_inicio_contagem_progressao
        fim = inicio + relativedelta(months=18)

        if not (inicio <= referencia <= fim):
            return None

        marco_12_meses = inicio + relativedelta(months=12)
        referencia_inclusiva = referencia + timedelta(days=1)
        dias_faltando = (referencia - marco_12_meses).days + 1
        diferenca_md = relativedelta(referencia_inclusiva, marco_12_meses)

        meses = diferenca_md.months
        dias = diferenca_md.days
        meses_e_dias = f'{meses} meses e {dias} dias'

        return {
            'servidor': self.registro_a_progredir,
            'avaliado': self.avaliado,
            'data_inicio': inicio,
            'fim_intersticio': fim,
            'apos_12_meses': marco_12_meses,
            'dias_faltando_para_3112': dias_faltando,
            'meses': meses,
            'dias': dias,
            'meses_e_dias': meses_e_dias,
        }

    @classmethod
    def calcular_saldos_de_todos(cls):
        processos = cls.objects.filter(data_inicio_contagem_progressao__year=2023, registro_a_progredir__isnull=False, avaliado__ativo=True)

        resultado = []

        for processo in processos.select_related('registro_a_progredir', 'avaliado'):
            saldo = processo.calculando_saldo()
            if saldo:
                resultado.append(saldo)

        return resultado

    # Fim do saldo

    @staticmethod
    def get_configuracao():
        try:
            config = ConfiguracaoProgressao.objects.get(ativo=True)
            return config
        except Exception:
            return None

    @staticmethod
    def calcular_servidores_a_progredir(
        salvar_processos=False,
        data_referencia=None,
        matricula=None,
        atualizando=False,
        ignorar_lista_matricula=False,
        pk_relatorio=None,
        forcar_calculo=None,
    ):
        # selecionando a configuração
        config = ProcessoProgressao.get_configuracao()
        if not config:
            raise ConfiguracaoProgressao.DoesNotExist(
                'Não foi encontrada uma configuração para a progressão TAE. Cadastre uma configuração para proceguir.'
            )
        #
        if not data_referencia:
            data_referencia = datetime.date.today()
        novos_processos = []
        qs_servidores = Servidor.objects.ativos().exclude(situacao__in=[Situacao.APOSENTADOS])
        if matricula:
            qs_servidores = qs_servidores.filter(matricula=matricula)
        #
        # lista as matriculas dos servidores que estão no relatório e que o processo ainda não foi criado
        lista_matriculas_no_relatorio = []
        if not ignorar_lista_matricula:
            lista_matriculas_no_relatorio = ServidorAProgredir.objects.filter(processo_criado=False, avaliado__ativo=True).values_list(
                'avaliado__matricula', flat=True
            )
            # verificando se existe processos em andamento
            qs_pp = ServidorAProgredir.objects.filter(
                processo_criado=True,
                avaliado__ativo=True,
            ).exclude(processoprogressao__status=ProcessoProgressao.STATUS_FINALIZADO)
            if qs_pp.exists():
                for pp in qs_pp:
                    lista_matriculas_no_relatorio = list(lista_matriculas_no_relatorio)
                    lista_matriculas_no_relatorio.append(pp.avaliado.matricula)
        #
        for servidor in qs_servidores.tecnicos_administrativos().exclude(matricula__in=lista_matriculas_no_relatorio):
            calculo = ServidorAProgredir.VIA_PCA
            print_(f'Analisando {servidor}')
            existe_registro_relatorio = servidor.matricula in lista_matriculas_no_relatorio

            if data_referencia == datetime.date.today():
                datas_ultimas_progressoes = [datetime.date(1900, 1, 1)]
                setou_data = False
                #
                # 1) Primeiro: procura registros no módulo de progressões
                if 'progressoes' in settings.INSTALLED_APPS:
                    qs_progressoes = ProcessoProgressao.objects.filter(
                        tipo=ProcessoProgressao.TIPO_PROGRESSAO_MERITO,
                        avaliado=servidor,
                        status=ProcessoProgressao.STATUS_FINALIZADO,
                    ).order_by('data_fim_contagem_progressao')
                    if qs_progressoes.exists():
                        ultima_progressao = qs_progressoes.last()
                        data_inicio_progressao = ultima_progressao.data_fim_contagem_progressao + timedelta(days=1)
                        datas_ultimas_progressoes = [data_inicio_progressao]
                        setou_data = True
                        calculo = ServidorAProgredir.VIA_PROGRESSAO
                #
                # 2) Mesmo encontrando data no módulo de progressões, verifica se há PCA para verificar se existe divergência
                forcar_calculo_pca = str(forcar_calculo) == str(ServidorAProgredir.VIA_PCA)
                if not setou_data or forcar_calculo_pca:
                    for pca in servidor.pca_set.all().exclude(servidor__cargo_emprego__grupo_cargo_emprego__categoria='docente'):
                        try:
                            posicionamento_referencia = (
                                pca.posicionamentopca_set.filter(eh_capacitacao=False).order_by('-data_inicio_posicionamento_pca').first()
                            )
                            if posicionamento_referencia:
                                # atualiza a data de referência para a mais recente via pca
                                if forcar_calculo_pca or (
                                    datas_ultimas_progressoes
                                    and posicionamento_referencia.data_inicio_posicionamento_pca > datas_ultimas_progressoes[0]
                                ):
                                    datas_ultimas_progressoes = [posicionamento_referencia.data_inicio_posicionamento_pca]
                                    setou_data = True
                                    calculo = ServidorAProgredir.VIA_PCA
                        except Exception:
                            continue  # vai para o próximo PCA
                #
                # 3) Se ainda não encontrou: usa o início do exercício
                if not setou_data:
                    datas_ultimas_progressoes = [servidor.calcula_inicio_exercicio_na_instituicao]
                    setou_data = True
            else:
                datas_ultimas_progressoes = [data_referencia]

            for data_ultima_progressao in datas_ultimas_progressoes:
                processo_progressao = ProcessoProgressao()
                processo_progressao.data_inicio_contagem_progressao = data_ultima_progressao
                processo_progressao.avaliado = servidor
                # prepara o proximo padrao de vencimento (se for o caso)
                proximo_padrao = None
                try:
                    processo_progressao.calcular_data_de_progressao()
                    proximo_padrao = processo_progressao.calcular_proximo_padrao_vencimento(servidor)
                except ValidationError as ex:
                    logger.warning('Erro de validação no servidor %s: %s', servidor, ex)
                    continue
                except Exception as ex:
                    logger.error('Erro inesperado no servidor %s: %s', servidor, ex)
                    continue

                # mantendo a data de fim da contagem atualizada
                if existe_registro_relatorio:
                    qs_servidor_progredir = ServidorAProgredir.objects.filter(
                        avaliado=processo_progressao.avaliado, data_inicio_contagem=processo_progressao.data_inicio_contagem_progressao
                    )
                    dados_servidor_a_progedir = {
                        'data_fim_contagem': processo_progressao.data_fim_contagem_progressao,
                    }

                    qs_servidor_progredir.update(**dados_servidor_a_progedir)

                #
                if proximo_padrao:
                    """
                        O objetivo é avisar (listar) ao RH com antecedência máxima de X dias.
                        A data calculada para progressao deverá está no futuro distante por no máximo X dias
                        a partir de uma determinanda data.

                        Exemplo:

                                                   X dias de antecedencia
                               --------|-----------------------------------------|---------------------
                                A, B   C    D     E                         data (final)         F
                                                                             progressao

                        Nos dias A e B a data de progressao está no futuro por mais de X dias. Então não haverá
                        avisos. No dia C está a exatos X dias e nos dias D e E está a menos de X dias. Nos casos
                        dos dias C, D e E haverá avisos. Por consequência, data de progressoes no passado em
                        relação a uma certa data F também produzirá avisos.
                    """
                    # tem processo de progressão por mérito em andamento?
                    processo_existe = (
                        ProcessoProgressao.objects.filter(
                            tipo=ProcessoProgressao.TIPO_PROGRESSAO_MERITO,
                            avaliado=servidor,
                        )
                        .exclude(status=ProcessoProgressao.STATUS_FINALIZADO)
                        .exists()
                    )
                    #
                    dados_servidor_a_progedir = {
                        'avaliado': processo_progressao.avaliado,
                        'data_inicio_contagem': processo_progressao.data_inicio_contagem_progressao,
                        'data_fim_contagem': processo_progressao.data_fim_contagem_progressao,
                    }
                    """
                    1) se não existir um processo de progressão em andamento
                    2) Se o parâmetro salvar_processo for verdadeiro
                    3) Se não existir registro na listagem de servidores a progredir com processo NÃO criado
                    """
                    if not processo_existe and salvar_processos and not existe_registro_relatorio:
                        # será criado um registro no modelo ServidorAProgredir para analise antes de cadastrar o processo
                        situacao = ServidorAProgredir.SITUACAO_REGULAR
                        if (
                            data_referencia - processo_progressao.data_fim_contagem_progressao
                        ).days > config.gerar_inconsistencia_dias:  # se for maior que 2 anos
                            situacao = ServidorAProgredir.SITUACAO_INCONSISTENTE
                        #
                        dados_servidor_a_progedir = {
                            'avaliado': processo_progressao.avaliado,
                            'data_inicio_contagem': processo_progressao.data_inicio_contagem_progressao,
                            'data_fim_contagem': processo_progressao.data_fim_contagem_progressao,
                            'calculo': calculo,
                        }
                        #
                        if atualizando:
                            _relatorio = ServidorAProgredir.objects.filter(pk=pk_relatorio)
                            _relatorio.update(**dados_servidor_a_progedir)
                            _relatorio = _relatorio.first()
                            _relatorio.verificar_processos(processo_progressao.avaliado.matricula)
                        else:
                            dados_servidor_a_progedir.update({'situacao': situacao, 'processo_criado': False})
                            obj, _ = ServidorAProgredir.objects.get_or_create(**dados_servidor_a_progedir)
                            obj.verificar_processos(processo_progressao.avaliado.matricula)

                        # salva no banco o novo processo
                        print_(f'Salvando registro para {servidor}')

                    novos_processos.append(processo_progressao)
        #
        return novos_processos  # salvos ou não

    #
    # Calcula a data que o servidor deverá progredir ou adquerir a estabilidade ao completar 3 anos de efetivo exercicio
    #
    def calcular_data_de_progressao(self):
        erros = []

        # checa configuração
        config = self.get_configuracao()
        if not config:
            raise ValidationError('Não foi encontrada uma configuração para progressão TAE. Cadastre uma configuração para prosseguir.')

        # checa data início
        if not self.data_inicio_contagem_progressao:
            erros.append('Data de início da contagem de progressão não informada.')

        # checa avaliado
        if not getattr(self, 'avaliado', None):
            erros.append('Servidor avaliado não informado.')
        elif not hasattr(self.avaliado, 'dados_afastamentos_efetivo_exercicio_24_meses'):
            erros.append("Servidor avaliado não possui método 'dados_afastamentos_efetivo_exercicio_24_meses' implementado.")

        if erros:
            raise ValidationError(erros)

        # se já tem data fim, não precisa recalcular o valor inicial
        if not self.data_fim_contagem_progressao:
            if self.is_tipo_progressao_merito:
                intersticio = config.intersticio_progressao
                data = self.add_months(self.data_inicio_contagem_progressao, intersticio)
            else:
                data = self.add_months(self.data_inicio_contagem_progressao, config.intersticio_estagio_probatorio)

            # seta data padrão da contagem final (menos 1 dia)
            self.data_fim_contagem_progressao = data - timedelta(1)

        # consulta ids de afastamentos já considerados
        ids_ignorar = []
        if self.ids_afastamentos_utilizados:
            ids_ignorar = list(self.ids_afastamentos_utilizados.split(','))

        dias_afast, ids_afast = self.obtem_afastamentos_numero_dias(ids_ignorar)
        for i in ids_afast:
            self.adicionar_afastamento(i)
        dias_afastamentos = dias_afast

        dias_afast_efet, ids_afast_efet = self.obtem_dias_desconto_efetivo_exercicio(ids_ignorar)
        for i in ids_afast_efet:
            self.adicionar_afastamento(i)
        dias_afastamentos_efetivo_exercicio = dias_afast_efet

        total_dias = dias_afastamentos + dias_afastamentos_efetivo_exercicio

        # regra extra para progressão por mérito
        if self.tipo == ProcessoProgressao.TIPO_PROGRESSAO_MERITO:
            dias_afast_merito, ids_afast_merito = self.obtem_dias_afastamento_interrompe_progressao_merito(ids_ignorar)
            for i in ids_afast_merito:
                self.adicionar_afastamento(i)
            total_dias += dias_afast_merito

            # regra dos 24 meses - licença para tratamento de saúde
            dados_afast = self.avaliado.dados_afastamentos_efetivo_exercicio_24_meses(
                contar_a_partir_de=self.data_inicio_contagem_progressao, ids_ignorar=ids_ignorar
            )
            if dados_afast:
                for i in dados_afast:
                    if hasattr(i, 'pk'):
                        self.adicionar_afastamento(i.pk)
                total_dias += dados_afast.get('total_dias') or 0

        # aplica afastamentos no cálculo
        self.data_fim_contagem_progressao = self.data_fim_contagem_progressao + timedelta(days=total_dias)

        # recursivo se houver afastamento
        if total_dias > 0:
            self.calcular_data_de_progressao()

        # aplica saldo, se houver
        if self.tem_saldo:
            self.data_fim_contagem_progressao = self.data_fim_contagem_progressao - relativedelta(days=self.dias_saldo)
            self.saldo_usado = True

    #
    # APENAS AFASTAMENTOS QUE INTERROMPEM TEMPO DE SERVIÇO OU SUSPENDEM ESTÁGIO PROBATÓRIO
    def obtem_afastamentos(self):
        #
        # apenas afastamentos que interrompe tempo de serviço e que suspende estágio probatório
        #
        """
        exerc corrido = |----------------------------------------| = 18 meses
        afastamentos  =    |xxxx|       |xxxxxxxxxxx|      |xxxxxxxxxxx|
        exerc altern  = |--      -------             ------             ------|

        afastamentos considerados = começar ou terminar dentro
            data inicial >= data inicial da contagem E data inicial <= data final da contagem (versão exerc corrido)
            OU
            data final >= data inicial da contagem E data final <= data final da contagem (versão exerc corrido)
        """
        # consultando configurações
        config = self.get_configuracao()
        if not config:
            raise ConfiguracaoProgressao.DoesNotExist(
                'Não foi encontrada uma configuração para a progressão TAE. Cadastre uma configuração para proceguir.'
            )
        if not self.data_fim_contagem_progressao:
            _intersticio = config.intersticio_progressao
            data_final_contagem_exercicio_corrido = self.add_months(self.data_inicio_contagem_progressao, _intersticio)
        else:
            data_final_contagem_exercicio_corrido = self.data_fim_contagem_progressao
        #
        afastamentos_inicio_no_periodo_corrido = self.avaliado.afastamentos.filter(
            afastamento__interrompe_tempo_servico=True,
            data_inicio__gte=self.data_inicio_contagem_progressao,
            data_inicio__lte=data_final_contagem_exercicio_corrido,
        )
        #
        afastamentos_termino_no_periodo_corrido = self.avaliado.afastamentos.filter(
            afastamento__interrompe_tempo_servico=True,
            data_termino__gte=self.data_inicio_contagem_progressao,
            data_termino__lte=data_final_contagem_exercicio_corrido,
        )
        #
        afastamentos_considerados = afastamentos_inicio_no_periodo_corrido | afastamentos_termino_no_periodo_corrido

        #
        # verifica afastamentos que suspendem estágio probatório
        if self.tipo == ProcessoProgressao.TIPO_ESTAGIO_PROBATORIO:
            afastamentos_inicio_no_periodo_corrido_estagio_probatorio = self.avaliado.afastamentos.filter(
                afastamento__suspende_estagio_probatorio=True,
                data_inicio__gte=self.data_inicio_contagem_progressao,
                data_inicio__lte=data_final_contagem_exercicio_corrido,
            )
            #
            afastamentos_termino_no_periodo_corrido_estagio_probatorio = self.avaliado.afastamentos.filter(
                afastamento__suspende_estagio_probatorio=True,
                data_termino__gte=self.data_inicio_contagem_progressao,
                data_termino__lte=data_final_contagem_exercicio_corrido,
            )
            # sobrescreve a variável "afastamentos_considerados" adicionando os afastamentos que suspendem estágio probatório
            afastamentos_considerados = (
                afastamentos_inicio_no_periodo_corrido
                | afastamentos_termino_no_periodo_corrido
                | afastamentos_inicio_no_periodo_corrido_estagio_probatorio
                | afastamentos_termino_no_periodo_corrido_estagio_probatorio
            )
        #
        for a in afastamentos_considerados.distinct():
            self.id_afast_interrompem_tempo_servidor_list.append(a.id)
        return afastamentos_considerados.distinct()

    def obtem_dias_afastamento_interrompe_progressao_merito(self, ids_ignorar=None):
        #
        # os afastamentos que interrompem a progressão por mérito
        if ids_ignorar is None:
            ids_ignorar = []
        qs = self.obtem_afastamentos_interrompem_progressao_merito()
        dias = 0
        ids_afastamento = []
        if qs.exists():
            data_inicio = self.data_inicio_contagem_progressao
            data_fim = self.data_fim_contagem_progressao
            for af in qs.exclude(id__in=ids_ignorar):
                ids_afastamento.append(af.id)
                # (CASO 1)
                if data_inicio < af.data_inicio and data_fim >= af.data_inicio:
                    # basta adicionar a quantidade de dias do mandato na data fim
                    dias_afastamento = (af.data_termino - af.data_inicio).days
                    dias += dias_afastamento
                # (CASO 2)
                # 1º - com todo o PA dentro do PM
                if data_inicio >= af.data_inicio and data_fim <= af.data_termino:
                    dias_progressao = (data_fim - data_inicio).days  # a colisão aqui é a progressão toda
                    dias_restantes_afastamento = (data_fim - af.data_termino).days
                    dias += dias_progressao + dias_restantes_afastamento
                # 2° - quando apenas a data de início do PA está dentro do PM
                elif af.data_inicio <= data_inicio <= af.data_termino and data_fim > af.data_termino:
                    dias_colisao = (af.data_termino - data_inicio).days
                    dias += dias_colisao
        return dias, ids_afastamento

    def obtem_afastamentos_interrompem_progressao_merito(self):
        codigos_mandato_eletivo = AfastamentoSiape.AFASTAMENTOS_MANDATO_ELETIVO
        codigos_interesse_particular = AfastamentoSiape.AFASTAMENTOS_INTERESSE_PARTICULAR
        codigos = codigos_mandato_eletivo + codigos_interesse_particular
        qs = (
            ServidorAfastamento.objects.filter(servidor=self.avaliado, afastamento__codigo__in=codigos)
            .filter(
                Q(data_inicio__gte=self.data_inicio_contagem_progressao, data_inicio__lte=self.data_fim_contagem_progressao)
                | Q(data_termino__gte=self.data_inicio_contagem_progressao, data_termino__lte=self.data_fim_contagem_progressao)
                | Q(data_inicio__lte=self.data_inicio_contagem_progressao, data_termino__gte=self.data_fim_contagem_progressao)
            )
            .exclude(id__in=self.id_afast_interrompem_tempo_servidor_list)
        )
        return qs

    def obtem_dias_desconto_efetivo_exercicio(self, ids_ignorar=None):
        if ids_ignorar is None:
            ids_ignorar = []
        DIAS_EFETIVO_EXERCICIO = 30
        inicio = self.data_inicio_contagem_progressao
        fim = self.data_fim_contagem_progressao
        codigos_afastamento = self.obtem_afastamentos_efetivo_exercicio_30_dias(DIAS_EFETIVO_EXERCICIO)

        # só entra se o avaliado em questão tiver afastamentos que influenciem na progressão
        ids_afastamentos = []
        if codigos_afastamento:
            pv_inicio = inicio - timedelta(days=365)
            pv_fim = inicio
            delta_periodo_completo = fim - pv_inicio  # para calcular o delta, vamos andar até o fim da data fim da progressão
            calc_pv_inicio = pv_inicio
            calc_pv_fim = pv_fim
            lista_dias_afetados = []

            # selecionando todos os afastamentos dentro do período de verificação (PV)
            qs_afastamentos = self.avaliado.afastamentos.filter(
                data_termino__gte=pv_inicio, data_inicio__lte=fim, afastamento__codigo__in=codigos_afastamento, desconsiderar_regra_30_dias=False
            )

            list_afastamentos = []
            list_dias_afastamentos = []
            for afastamento in qs_afastamentos.exclude(id__in=ids_ignorar):
                ids_afastamentos.append(afastamento.id)
                dict_afastamento = {
                    'data_inicio': afastamento.data_inicio,
                    'data_termino': afastamento.data_termino,
                    'servidor_afastamento': afastamento,
                }
                d = (afastamento.data_termino - afastamento.data_inicio).days + 1
                for dia_afast in range(d):
                    list_dias_afastamentos.append(afastamento.data_inicio + timedelta(days=dia_afast))
                list_afastamentos.append(dict_afastamento)

            for num_dia in range(1, delta_periodo_completo.days + 1):  # não somar mais 1, fica só 364 dias :/
                dias = 0

                # verifica se o dia da vez tem um afastamento. em caso negativo, passa para o próximo
                check_dia = calc_pv_fim  # dia da vez

                if check_dia in list_dias_afastamentos:
                    la = []
                    for i in list_afastamentos:
                        delta = 0
                        # verificando se os dias do afastamento será integral na contagem
                        if i.get('data_inicio') >= calc_pv_inicio and i.get('data_termino') <= calc_pv_fim:
                            delta = i.get('data_termino') - i.get('data_inicio')
                            dias += delta.days + 1
                            la.append(i.get('servidor_afastamento'))
                        else:
                            # afastamentos onde nem todos os dias serão contabilizados
                            if i.get('data_inicio') < calc_pv_inicio and i.get('data_termino') >= calc_pv_inicio:
                                delta = i.get('data_termino') - calc_pv_inicio
                                dias += delta.days + 1
                                la.append(i.get('servidor_afastamento'))
                            if i.get('data_termino') > calc_pv_fim and i.get('data_inicio') <= calc_pv_fim:
                                delta = calc_pv_fim - i.get('data_inicio')
                                dias += delta.days + 1
                                la.append(i.get('servidor_afastamento'))

                    if dias > 30:
                        dict_obs = {'data_afetada': check_dia, 'qtd_dias': dias, 'lista_afastamentos': la}
                        self.observacoes_list.append(dict_obs)
                        lista_dias_afetados.append(check_dia)

                # andando com o período de verificação
                calc_pv_inicio = pv_inicio + timedelta(days=num_dia)
                calc_pv_fim = pv_fim + timedelta(days=num_dia)

            return len(lista_dias_afetados), ids_afastamentos
        return 0, ids_afastamentos

    def obtem_afastamentos_efetivo_exercicio_30_dias(self, dias_efetivo_exercicio):
        #
        # a regra de efetivo exercício considera afastamentos com a configuração de 30 dias, logo,
        # é necessário selecionar esses afastamentos
        AfastamentoSiapeEfetivoExercicio = apps.get_model('rh', 'AfastamentoSiapeEfetivoExercicio')
        config_afastamento = AfastamentoSiapeEfetivoExercicio.objects.filter(
            dias_efetivo_exercicio=dias_efetivo_exercicio, situacao=AfastamentoSiapeEfetivoExercicio.SITUACAO_ATIVO
        )
        if config_afastamento.exists():
            config_afastamento = config_afastamento[0]
            lista_codigos_afastamento = []
            for a in config_afastamento.afastamentos.all():
                if a.codigo in self.avaliado.afastamentos.values_list('afastamento__codigo', flat=True):
                    lista_codigos_afastamento.append(a.codigo)
            return lista_codigos_afastamento
        return []

    def obtem_afastamentos_numero_dias(self, ids_ignorar=None):
        if ids_ignorar is None:
            ids_ignorar = []
        afastamentos = self.obtem_afastamentos()
        #
        total_dias_afastado = 0
        id_afastamentos = []
        for afastamento in afastamentos.exclude(id__in=ids_ignorar):
            if afastamento.data_termino:
                id_afastamentos.append(afastamento.id)
                total_dias_afastado += (afastamento.data_termino - afastamento.data_inicio).days + 1
        #
        return total_dias_afastado, id_afastamentos

    @staticmethod
    def _gerar_dicionario_de_datas(inicio, fim):
        dicionario_datas = []
        data_atual = inicio

        while data_atual <= fim:
            dicionario_datas.append(data_atual.strftime('%d/%m/%Y'))
            data_atual += timedelta(days=1)

        return dicionario_datas

    #
    def _lista_dias_nao_cobertos(self):
        lista_dias_periodo_completo = self._gerar_dicionario_de_datas(self.data_inicio_contagem_progressao, self.data_fim_contagem_progressao)
        # verificando períodos das avaliações cadastradas
        for a in self.processoprogressaoperiodo_set.all():
            dias_periodo_avaliacao = self._gerar_dicionario_de_datas(a.data_inicio, a.data_fim)
            for dia in dias_periodo_avaliacao:
                if dia in lista_dias_periodo_completo:
                    lista_dias_periodo_completo.remove(dia)
        return lista_dias_periodo_completo

    def calcular_proximo_padrao_vencimento(self, servidor):
        erros = []

        # categoria obrigatória
        if not servidor.categoria:
            erros.append('Categoria do servidor não informada.')

        # cargo_classe e código obrigatórios
        if not getattr(servidor, 'cargo_classe', None) or not getattr(servidor.cargo_classe, 'codigo', None):
            erros.append('Cargo/Classe do servidor não informado.')

        # nível obrigatório
        if not servidor.nivel_padrao:
            erros.append('Nível do servidor não informado.')
        else:
            try:
                int(servidor.nivel_padrao)
            except ValueError:
                erros.append(f'Nível inválido: {servidor.nivel_padrao}')

        if erros:
            raise ValidationError(erros)

        # --- padrão anterior/atual ---
        categoria_servidor = servidor.categoria
        classe_nivel_posicao = servidor.cargo_classe.codigo + servidor.nivel_padrao
        classe = classe_nivel_posicao[0:1]
        posicao_vertical = classe_nivel_posicao[1:]

        try:
            posicao_vertical_int = int(posicao_vertical)
        except TypeError, ValueError:
            raise ValidationError(f'Posição vertical inválida: {posicao_vertical}')

        posicao_vertical_str = str(posicao_vertical_int).zfill(2)

        padrao_anterior, _ = PadraoVencimento.objects.get_or_create(
            categoria=categoria_servidor,
            classe=classe,
            posicao_vertical=posicao_vertical_str,
        )

        self.padrao_anterior = padrao_anterior

        # --- próximo padrão ---
        posicao_vertical_proxima = posicao_vertical_int + 1
        if posicao_vertical_proxima > 19:
            raise ValidationError('Servidor já está no topo da carreira.')

        posicao_vertical_proxima_str = str(posicao_vertical_proxima).zfill(2)

        padrao_novo, _ = PadraoVencimento.objects.get_or_create(
            categoria=categoria_servidor,
            classe=classe,
            posicao_vertical=posicao_vertical_proxima_str,
        )

        self.padrao_novo = padrao_novo
        return padrao_novo

    def calcular_media_processo(self, salvar=True):
        #
        # calcula a média do processo numa escala de desempenho de 0 a 100
        #

        # períodos
        periodos = self.processoprogressaoperiodo_set.all()
        periodos_somatorio_pesos = 0
        periodos_somatorio_media = 0
        for periodo in periodos:
            peso_periodo = periodo.obter_peso_periodo()
            periodos_somatorio_pesos += peso_periodo
            periodos_somatorio_media += periodo.media_periodo * peso_periodo
        #
        media = 0
        if periodos_somatorio_pesos > 0:
            media = periodos_somatorio_media / periodos_somatorio_pesos
        #
        # Arredondando a média (https://bugs.python.org/issue39124)
        media = round(Decimal(f'{media}'), 2)
        if salvar:
            self.media_processo = media
            self.save()
        #
        return media

    def obter_situacao_final_processo(self):
        # selecionando a configuração
        config = self.get_configuracao()
        if not config:
            raise ConfiguracaoProgressao.DoesNotExist(
                'Não foi encontrada uma configuração para a progressão TAE. Cadastre uma configuração para proceguir.'
            )
        #
        if self.status == ProcessoProgressao.STATUS_FINALIZADO:
            if self.media_processo >= config.media_aprovacao:
                return ProcessoProgressao.SITUACAO_FINAL_APROVADO
            else:
                return ProcessoProgressao.SITUACAO_FINAL_REPROVADO
        else:
            return ProcessoProgressao.SITUACAO_FINAL_NAO_FINALIZADO

    def obter_situacao_final_processo_as_text(self):
        situacao_final = self.obter_situacao_final_processo()
        if situacao_final == ProcessoProgressao.SITUACAO_FINAL_APROVADO:
            return 'Aprovado'
        elif situacao_final == ProcessoProgressao.SITUACAO_FINAL_REPROVADO:
            return 'Reprovado'
        elif situacao_final == ProcessoProgressao.SITUACAO_FINAL_NAO_FINALIZADO:
            return 'Não finalizado'
        else:
            return ''

    def obter_vinculos_avaliadores(self, incluir_avaliado=True):
        vinculos = []
        avaliadores_ids = []
        periodos = self.processoprogressaoperiodo_set.all()
        for periodo in periodos:
            for avaliador in periodo.obter_avaliadores(incluir_avaliado):
                if avaliador.id not in avaliadores_ids:
                    vinculos.append(avaliador)
                    avaliadores_ids.append(avaliador.id)
        return vinculos

    def obter_avaliacoes(self):
        meus_periodos_ids = ProcessoProgressaoPeriodo.objects.filter(processo_progressao=self).values_list('id', flat=True)
        return ProcessoProgressaoAvaliacao.objects.filter(periodo__in=meus_periodos_ids)

    def validar_periodos(self):
        """
        return (False, mensagens_de_erro) OU (True, "")
        """
        #
        # valida os padrões anterior e novo
        if self.padrao_anterior and self.padrao_novo and self.padrao_anterior == self.padrao_novo:
            return False, f"Os padrões de vencimento '{self.padrao_anterior}' (anterior) e '{self.padrao_novo}' (novo) devem ser diferentes."

        #
        # recalcula a data final do processo
        data_fim_contagem_progressao_anterior = self.data_fim_contagem_progressao
        data_fim_contagem_progressao_estava_errada = data_fim_contagem_progressao_anterior != self.data_fim_contagem_progressao
        if data_fim_contagem_progressao_estava_errada:
            self.save()  # salva a data final que foi recalculada

        avaliado_historico_setor_suap = self.avaliado.historico_setor_suap(
            data_inicio=self.data_inicio_contagem_progressao, data_fim=self.data_fim_contagem_progressao
        )
        avaliado_historico_setor_siape = self.avaliado.historico_setor_siape(
            data_inicio=self.data_inicio_contagem_progressao, data_fim=self.data_fim_contagem_progressao
        )
        avaliado_historico_funcao = self.avaliado.historico_funcao(
            data_inicio=self.data_inicio_contagem_progressao, data_fim=self.data_fim_contagem_progressao
        )

        #
        # cria lista com os ids dos setores
        avaliado_historico_setores_ids = set(
            list(avaliado_historico_setor_suap.values_list('setor', flat=True))
            + list(avaliado_historico_setor_siape.values_list('setor_exercicio', flat=True))
            + list(avaliado_historico_funcao.values_list('setor', flat=True))
        )

        periodos = []
        avaliadores_cadastrados = True
        avaliador_chefe_cadastrado_igual_a_1 = True
        avaliado_setores_invalidos = []
        menor_data = None
        maior_data = None
        for periodo in self.processoprogressaoperiodo_set.all():
            periodos += ((periodo.data_inicio, periodo.data_fim),)
            avaliadores_cadastrados = avaliadores_cadastrados and periodo.obter_avaliadores()
            avaliador_chefe_cadastrado_igual_a_1 = avaliador_chefe_cadastrado_igual_a_1 and len(periodo.obter_avaliadores_chefe()) == 1

            if periodo.setor.id not in avaliado_historico_setores_ids:
                avaliado_setores_invalidos.append(f"Setor '{periodo.setor}' não está no histórico de setores e funções. ")

            if not menor_data:
                menor_data = periodo.data_inicio
            if not maior_data:
                maior_data = periodo.data_fim

            if periodo.data_inicio < menor_data:
                menor_data = periodo.data_inicio
            if periodo.data_fim > maior_data:
                maior_data = periodo.data_fim
        #
        # enquadra os períodos de afastamentos
        ha_afastamentos = False
        for afastamento in self.obtem_afastamentos():
            if not menor_data:
                menor_data = afastamento.data_inicio
            if not maior_data:
                maior_data = afastamento.data_termino

            if afastamento.data_inicio < menor_data:
                menor_data = afastamento.data_inicio
            if afastamento.data_termino and afastamento.data_termino > maior_data:
                maior_data = afastamento.data_termino

            ha_afastamentos = True

        periodos_ok, periodos_mensagem = False, 'Nenhum período cadastrado.'

        if periodos:
            if not avaliadores_cadastrados:
                periodos_ok, periodos_mensagem = False, 'Nenhum avaliador foi selecionado ou há períodos sem avaliadores.'

            elif avaliadores_cadastrados and not avaliador_chefe_cadastrado_igual_a_1:
                periodos_ok, periodos_mensagem = False, 'Há períodos sem avaliador chefe selecionado ou com mais de um avaliador chefe.'

            elif avaliado_setores_invalidos:
                periodos_ok, periodos_mensagem = False, ''.join(avaliado_setores_invalidos)

            elif self.data_inicio_contagem_progressao < menor_data:
                periodos_ok, periodos_mensagem = (
                    False,
                    'Há um período não coberto: {} a {}.'.format(
                        self.data_inicio_contagem_progressao.strftime('%d/%m/%Y'), (menor_data - timedelta(1)).strftime('%d/%m/%Y')
                    ),
                )

            elif self.data_inicio_contagem_progressao > menor_data:
                periodos_ok, periodos_mensagem = (
                    False,
                    'Há um período inválido: {} a {}.'.format(
                        menor_data.strftime('%d/%m/%Y'), (self.data_inicio_contagem_progressao - timedelta(1)).strftime('%d/%m/%Y')
                    ),
                )

            elif self.data_fim_contagem_progressao > maior_data:
                periodos_ok, periodos_mensagem = (
                    False,
                    'Há um período não coberto: {} a {}.'.format(
                        (maior_data + timedelta(1)).strftime('%d/%m/%Y'), self.data_fim_contagem_progressao.strftime('%d/%m/%Y')
                    ),
                )

            elif self.data_fim_contagem_progressao < maior_data:
                periodos_ok, periodos_mensagem = (
                    False,
                    'Há um período inválido: {} a {}.'.format(
                        (self.data_fim_contagem_progressao + timedelta(1)).strftime('%d/%m/%Y'), maior_data.strftime('%d/%m/%Y')
                    ),
                )

            else:
                #
                # a última esperança de um True e nenhuma mensagem de erro (rsrs)
                periodos_ok, periodos_mensagem = periodos_sucessivos(periodos)
                periodos_mensagem = ''.join(periodos_mensagem)

                if not periodos_ok and ha_afastamentos:
                    periodos_mensagem += (
                        ' Nesse processo há períodos de afastamentos (verifique os períodos de avaliação e faça os ajustes necessários).'
                    )

        if not periodos_ok and data_fim_contagem_progressao_estava_errada:
            periodos_mensagem += (
                ' A data final da contagem foi recalculada e modificada de {} para {} '
                '(verifique os períodos de avaliação e faça os ajustes necessários).'.format(
                    data_fim_contagem_progressao_anterior.strftime('%d/%m/%Y'), self.data_fim_contagem_progressao.strftime('%d/%m/%Y')
                )
            )

        return periodos_ok, periodos_mensagem

    @staticmethod
    def obter_processos_a_iniciar():
        return ProcessoProgressao.objects.filter(status=ProcessoProgressao.STATUS_A_INICIAR)

    @staticmethod
    def obter_processos_por_avaliado(servidor_avaliado):
        return ProcessoProgressao.objects.filter(avaliado=servidor_avaliado)

    @staticmethod
    def obter_processos_por_avaliador(servidor_avaliador):
        return ProcessoProgressao.objects.filter(processoprogressaoperiodo__processoprogressaoavaliacao__avaliador=servidor_avaliador)

    @staticmethod
    def obter_processos_a_finalizar():
        return ProcessoProgressao.objects.filter(status=ProcessoProgressao.STATUS_EM_TRAMITE).exclude(
            processoprogressaoperiodo__processoprogressaoavaliacao__status_avaliacao=ProcessoProgressaoAvaliacao.STATUS_AVALIACAO_PENDENTE
        )

    @property
    def pode_finalizar(self):
        if self.status == ProcessoProgressao.STATUS_EM_TRAMITE:
            avaliacoes_processo = self.obter_avaliacoes()
            return all(not avaliacao.is_pendente for avaliacao in avaliacoes_processo)
        else:
            return False

    def finalizar_processo(self):
        #
        # analisa os periodos
        #
        dias_nao_cobertos = self._lista_dias_nao_cobertos()
        if dias_nao_cobertos:
            return False, f'Exitem dias não cobertos pelos períodos avaliativos. Dias: {dias_nao_cobertos}'
        #
        for periodo in self.processoprogressaoperiodo_set.all():
            #
            # valida a integridade e as assinaturas das avaliações do período
            #
            assinaturas_realizadas = 0
            assinaturas_requeridas = 0
            for avaliacao in periodo.processoprogressaoavaliacao_set.all():
                #
                # integridade do dados
                if not avaliacao.dados_integros:
                    return False, f"A avaliação '{avaliacao}' não está com dados íntegros e deve ser respondida novamente."
                #
                # assinaturas
                realizadas, requeridas = avaliacao.assinaturas_realizadas_requeridas()
                assinaturas_realizadas += realizadas
                assinaturas_requeridas += requeridas
            #
            if assinaturas_realizadas != assinaturas_requeridas:
                return False, f'Há {assinaturas_requeridas - assinaturas_realizadas} assinatura(s) pendente(s).'
            #
            # valida a media do periodo
            #
            media = periodo.calcular_media_periodo(salvar=False)
            media_salva = periodo.media_periodo
            if media != media_salva:
                return False, f"O período '{periodo}' está com média inválida. Acesse a opção 'Recalcular Médias'."
        #
        # valida a media do processo
        #
        media = self.calcular_media_processo(salvar=False)
        media_salva = self.media_processo
        if media != media_salva:
            return False, "O processo está com média final inválida. Acesse a opção 'Recalcular Médias'."
        #
        # recalcula a data final da contagem
        #
        data_fim_contagem_progressao_anterior = self.data_fim_contagem_progressao
        # se a opção de não permitir o recálculo da data final estiver marcada, não recalcula a data final
        if not self.nao_permitir_recalculo_data_fim:
            self.recalcular_intersticio()
        data_fim_contagem_progressao_estava_errada = data_fim_contagem_progressao_anterior != self.data_fim_contagem_progressao
        if data_fim_contagem_progressao_estava_errada:
            self.save()  # salva a data final que foi recalculada
            return (
                False,
                'A data final da contagem foi recalculada e modificada de {} para {}. '
                'Se for o caso, o trâmite do processo deve ser cancelado para que os ajustes nos '
                'períodos de avaliação sejam realizados. Em seguida, o processo deve ser colocado '
                'novamente em trâmite e, por fim, finalizado.'.format(
                    data_fim_contagem_progressao_anterior.strftime('%d/%m/%Y'), self.data_fim_contagem_progressao.strftime('%d/%m/%Y')
                ),
            )
        #
        # chegou nesse ponto, está tudo OK com as avaliações, com as médias dos períodos e do processo e com a
        # data final da contagem
        #
        self.status = ProcessoProgressao.STATUS_FINALIZADO
        self.data_finalizacao = datetime.datetime.now()
        self.save()
        #
        # verificando o registro do relatório a progredir
        if self.registro_a_progredir:
            relatorio = self.registro_a_progredir
            relatorio.situacao = ServidorAProgredir.SITUACAO_FINALIZADO
            relatorio.save()

        return True, 'O processo foi finalizado.'

    def add_months(self, sourcedate, months):
        return sourcedate + relativedelta(months=months)

    @property
    def is_a_iniciar(self):
        return self.status == ProcessoProgressao.STATUS_A_INICIAR

    @property
    def is_em_tramite(self):
        return self.status == ProcessoProgressao.STATUS_EM_TRAMITE

    @property
    def is_finalizado(self):
        return self.status == ProcessoProgressao.STATUS_FINALIZADO

    @property
    def is_aprovado(self):
        return self.obter_situacao_final_processo() == ProcessoProgressao.SITUACAO_FINAL_APROVADO

    @property
    def is_reprovado(self):
        return self.obter_situacao_final_processo() == ProcessoProgressao.SITUACAO_FINAL_REPROVADO

    @property
    def is_tipo_progressao_merito(self):
        return self.tipo == ProcessoProgressao.TIPO_PROGRESSAO_MERITO

    @property
    def is_tipo_estagio_probatorio(self):
        return self.tipo == ProcessoProgressao.TIPO_ESTAGIO_PROBATORIO

    @staticmethod
    def _get_setor_reitoria_primeiro_tramite(uo: UnidadeOrganizacional) -> Setor | None:
        # na reitoria, o setor de primeiro trâmite é o da primeira sigla cadastrada (pela ordem) que existir na unidade
        for sigla in SiglaSetorPrimeiroTramite.siglas(SiglaSetorPrimeiroTramite.TIPO_REITORIA):
            setor = uo.setor_set.filter(sigla=sigla).first()
            if setor:
                return setor
        return None

    ##
    # calcula o setor do primeiro trâmite a partir do setor do servidor avaliado
    @staticmethod
    def calcular_setor_primeiro_tramite(setor_avaliado: Setor) -> Setor:
        #
        # demanda 961 - https://suap.ifrn.edu.br/demandas/visualizar/961
        uo = setor_avaliado.uo
        setor = None
        if uo.eh_reitoria:
            setor = ProcessoProgressao._get_setor_reitoria_primeiro_tramite(uo)
        else:
            # senão, setor é cogpe, asgpe ou diape.
            for sigla in SiglaSetorPrimeiroTramite.siglas(SiglaSetorPrimeiroTramite.TIPO_CAMPUS):
                setor = uo.setor_set.filter(sigla__icontains=sigla).first()
                if setor:
                    return setor
            # se não encontrar o setor de primeiro tramite nas configurações, o trâmite será similar ao da reitoria
            # forçando uo igual RE
            reitoria = UnidadeOrganizacional.objects.suap().filter(sigla=utils.get_sigla_reitoria()).first()
            if reitoria:
                setor = ProcessoProgressao._get_setor_reitoria_primeiro_tramite(reitoria)
        # Sem a reitoria ou sem o setor configurado nela, o trâmite seria criado sem destino.
        if setor:
            return setor
        raise ValidationError(
            'Configuração de primeiro trâmite do processo inexistente ou mau configurada. Por favor '
            'entrar em contato com o administraor do sistema para realizar essa configuração'
        )

    def gerar_protocolo(self):
        from protocolo.models import Processo as ProtocoloFisico
        from protocolo.models import Tramite

        try:
            setor_primeiro_tramite = self.calcular_setor_primeiro_tramite(self.avaliado.setor)

            setor_gerador_protocolo = get_setor()
            user_gerador_protocolo = tl.get_user()

            # cria o protocolo físico
            protocolo = ProtocoloFisico()
            protocolo.assunto = f'{self.get_tipo_display()}'
            protocolo.vinculo_cadastro = user_gerador_protocolo.get_vinculo()
            protocolo.set_interessado(self.avaliado)
            protocolo.tipo = ProtocoloFisico.TIPO_REQUERIMENTO
            protocolo.numero_documento = '-'
            protocolo.palavras_chave = f'Avaliação de Desempenho, {self.get_tipo_display()}'
            protocolo.save()

            tramite = Tramite()
            tramite.processo = protocolo
            tramite.tipo_encaminhamento = Tramite.TIPO_ENCAMINHAMENTO_INTERNO
            tramite.orgao_interno_encaminhamento = setor_gerador_protocolo
            tramite.orgao_interno_recebimento = setor_primeiro_tramite
            tramite.pessoa_encaminhamento = user_gerador_protocolo.get_profile()
            tramite.data_encaminhamento = datetime.datetime.now()
            tramite.ordem = 1
            tramite.save()

            self.protocolo = protocolo
            self.save()
        except Exception as erro:
            raise Exception(f'{erro}')

    def gerar_processo_eletronico(self, avaliacoes_file):
        from processo_eletronico.models import Documento, TipoConferencia, TipoDocumento, TipoProcesso
        from processo_eletronico.models import Processo as ProcessoEletronico

        try:
            # configurações SUAP
            pk_tipo_processo = Configuracao.get_valor_por_chave('progressoes', 'processo_eletronico_tipo_processo')
            pk_tipo_documento = Configuracao.get_valor_por_chave('progressoes', 'processo_eletronico_tipo_documento')
            pk_tipo_conferencia = Configuracao.get_valor_por_chave('progressoes', 'processo_eletronico_tipo_conferencia')

            if not pk_tipo_processo:
                raise Exception('Configuração SUAP ausente: "Aplicação Progressoes > Tipo de processo (Processo Eletrônico)"')

            if not pk_tipo_documento:
                raise Exception('Configuração SUAP ausente: "Aplicação Progressoes > Tipo de documento (Processo Eletrônico)"')

            if not pk_tipo_conferencia:
                raise Exception('Configuração SUAP ausente: "Aplicação Progressoes > Tipo de conferência (Processo Eletrônico)"')

            setor_primeiro_tramite = self.calcular_setor_primeiro_tramite(self.avaliado.setor)
            tipo_processo = TipoProcesso.objects.get(pk=pk_tipo_processo)
            tipo_documento = TipoDocumento.objects.get(pk=pk_tipo_documento)
            tipo_conferencia = TipoConferencia.objects.get(pk=pk_tipo_conferencia)

            user_gerador_processo_eletronico = tl.get_user()

            processo_tramite = {'tipo_processo': tipo_processo, 'assunto': f'{self.get_tipo_display()}', 'setor_destino': setor_primeiro_tramite}

            processo_documento_avaliacoes = {
                'tipo': tipo_documento,
                'tipo_conferencia': tipo_conferencia,
                'assunto': 'Avaliação de Desempenho',
                'nivel_acesso': Documento.NIVEL_ACESSO_PUBLICO,
                'arquivo': avaliacoes_file,
            }

            self.processo_eletronico = ProcessoEletronico.cadastrar_processo(
                user=user_gerador_processo_eletronico,
                processo_tramite=processo_tramite,
                papel=user_gerador_processo_eletronico.get_relacionamento().papeis_ativos.first(),
                documentos_texto=[],
                documentos_digitalizados=[processo_documento_avaliacoes],
                interessados=[self.avaliado.get_vinculo()],
            )

            if not self.processo_eletronico:
                raise Exception('Erro ao gerar o processo eletrônico.')

            self.save()
            avaliacoes_file.close()
        except Exception as erro:
            raise Exception(f'{erro}')

    @staticmethod
    def alertar_responsaveis_processos() -> None:
        """Avisa o setor de primeiro trâmite das progressões a iniciar (comando ``alertar_responsaveis_processos``).

        Cobre os registros do relatório de servidores a progredir ainda sem processo e os processos
        a iniciar. O prazo é a data final já descontado o saldo de interstício, como no relatório.
        """
        if not Configuracao.get_valor_por_chave('progressoes', 'alertar_responsaveis_servidores_a_progredir'):
            return
        for registro in ServidorAProgredir.objects.filter(processo_criado=False, avaliado__ativo=True):
            link = f'/admin/progressoes/servidoraprogredir/?q={registro.avaliado.matricula}'
            ProcessoProgressao._alertar_responsaveis(registro, registro.data_fim_ajustada, link)
        for processo in ProcessoProgressao.obter_processos_a_iniciar():
            link = '/admin/progressoes/processoprogressao/?tab=tab_a_iniciar'
            ProcessoProgressao._alertar_responsaveis(processo, processo.data_fim_ajustada, link)

    @staticmethod
    def _alertar_responsaveis(registro: ServidorAProgredir | ProcessoProgressao, data_fim: datetime.date, link: str) -> None:
        """Notifica os servidores do setor de primeiro trâmite do avaliado conforme os dias até ``data_fim``.

        Com mais de 30 dias, avisa uma única vez (registros que têm ``notificado_45_dias``); com menos
        de 30 dias ou prazo vencido, avisa a cada execução.
        """
        dias = max((data_fim - datetime.date.today()).days, 0)
        aviso_unico = dias > 30 and not getattr(registro, 'notificado_45_dias', True)
        if not (aviso_unico or dias < 30):
            return
        try:
            setor = ProcessoProgressao.calcular_setor_primeiro_tramite(registro.avaliado.setor)
        except Exception:
            logger.warning('Progressão de %s sem setor de primeiro trâmite: alerta não enviado.', registro.avaliado, exc_info=True)
            return
        vinculos = [servidor.get_vinculo() for servidor in Servidor.objects.ativos().filter(setor=setor)]
        if not vinculos:
            return
        texto = (
            '<h1>Progressão Funcional</h1>'
            '<h2>Identificação de Processo a Iniciar</h2>'
            f'<p>O processo de progressão funcional de {registro.avaliado} foi identificado dentro do período para iniciar e necessita de sua atenção.</p>'
            f'<p><a href="{link}">Clique aqui</a> para acessar as informações do processo.</p>'
        )
        send_notification('[SUAP] Processo de Progressão a Iniciar Identificado', texto, settings.DEFAULT_FROM_EMAIL, vinculos)
        if aviso_unico:
            registro.notificado_45_dias = True
            registro.save()

    @staticmethod
    def ultima_progressao_servidor(servidor):
        return (
            ProcessoProgressao.objects.filter(
                tipo=ProcessoProgressao.TIPO_PROGRESSAO_MERITO, avaliado=servidor, status=ProcessoProgressao.STATUS_FINALIZADO
            )
            .order_by('id')
            .last()
        )

    def adicionar_afastamento(self, novo_id_afastamento):
        if self.ids_afastamentos_utilizados is None:
            self.ids_afastamentos_utilizados = str(novo_id_afastamento)
        else:
            ids_atuais = self.ids_afastamentos_utilizados.split(',')
            if str(novo_id_afastamento) not in ids_atuais:
                ids_atuais.append(str(novo_id_afastamento))
                self.ids_afastamentos_utilizados = ','.join(ids_atuais)

    def recalcular_intersticio(self):
        # remove os afastamentos do processo para recalcular do zero
        self.ids_afastamentos_utilizados = None
        # apagando a data fim da contagem para recalcular
        self.data_fim_contagem_progressao = None
        # informando que o saldo não foi usando para calcular a data de progressão
        self.saldo_usado = False
        #
        self.calcular_data_de_progressao()
        self.save()

    class Meta:
        ordering = ('-data_inicio_contagem_progressao',)
        verbose_name = 'Processo de Progressão/Estágio Probatório'
        verbose_name_plural = 'Processos de Progressão/Estágio Probatório'
        permissions = (
            ('pode_ver_todos_os_processos', 'Pode visualizar todos os processos'),
            ('pode_ver_apenas_processos_do_seu_campus', 'Pode visualizar apenas os processos do seu campus'),
        )


class ObservacaoAfastamentoEfetivoExercicio(models.ModelPlus):
    processo = models.ForeignKeyPlus(ProcessoProgressao, verbose_name='Processo de Progressão', on_delete=models.CASCADE)
    data_afetada = models.DateFieldPlus('Data Afetada', null=True)
    qtd_dias_afastamento = models.IntegerFieldPlus('Quantidade de Dias de Afastamento Encontrados', default=0)
    afastamentos = models.ManyToManyFieldPlus('rh.ServidorAfastamento', verbose_name='Afastamento do Servidor', blank=True)

    class Meta:
        verbose_name = 'Observação de Afastamento de Efetivo Exercício'
        verbose_name_plural = 'Observações de Afastamentos de Efetivo Exercício'


#
# Representa um período no qual o servidor é avaliado
class ProcessoProgressaoPeriodo(models.ModelPlus):
    processo_progressao = models.ForeignKeyPlus(
        'progressoes.ProcessoProgressao', blank=True, null=False, verbose_name='Processo de Progressão', on_delete=models.CASCADE
    )
    avaliacao_modelo = models.ForeignKeyPlus(
        'progressoes.AvaliacaoModelo', blank=False, null=False, verbose_name='Modelo de Avaliação', on_delete=models.CASCADE
    )
    setor = models.ForeignKeyPlus('rh.Setor')
    data_inicio = models.DateFieldPlus('Data Inicial')
    data_fim = models.DateFieldPlus('Data Final')
    media_periodo = models.DecimalFieldPlus(default=0, decimal_places=2, max_digits=12)

    def __str__(self):
        return '{} à {} - {}'.format(self.data_inicio.strftime('%d/%m/%Y'), self.data_fim.strftime('%d/%m/%Y'), self.setor)

    @property
    def funcao_gratificada(self):
        return self.avaliacao_modelo.funcao_gratificada

    def calcular_media_periodo(self, salvar=True):
        #
        # calcula a media do período numa escala de desempenho de 0 a 10
        #

        # avaliacoes do periodo
        avaliacoes_periodo = self.processoprogressaoavaliacao_set.all()
        # totais tipos de avaliadores
        auto = 0
        chefe = 0
        equipe = 0

        equipe_qtd = 0

        for avaliacao in avaliacoes_periodo:
            if avaliacao.tipo_avaliador == ProcessoProgressaoAvaliacao.TIPO_AVALIADOR_AUTO:
                auto += avaliacao.total_pontos
            elif avaliacao.tipo_avaliador == ProcessoProgressaoAvaliacao.TIPO_AVALIADOR_EQUIPE:
                equipe += avaliacao.total_pontos
                equipe_qtd += 1
            elif avaliacao.tipo_avaliador == ProcessoProgressaoAvaliacao.TIPO_AVALIADOR_CHEFE:
                chefe += avaliacao.total_pontos

        if equipe_qtd > 0:
            media_par = equipe / equipe_qtd
        else:
            media_par = 0
        #
        if media_par == 0 and equipe_qtd == 0:
            soma_pesos = 2  # se não há avaliações de membros da equipe, soma dos pesos = 2
            if self.processo_progressao.is_tipo_estagio_probatorio:
                soma_pesos = 1  # uma única avaliação do chefe
            media = (auto * 1 + chefe * 1) / soma_pesos
        else:
            # nesse ponto, é possível que media_par = 0, pois é possível que todos os membros da equipe tenham
            # dado nota ZERO em todas as questões das avaliações e, mesmo nesse caso, a soma dos pesos deverá ser 4
            media = (auto * 1 + chefe * 1 + media_par * 2) / 4
        #
        # Arredondando a média (https://bugs.python.org/issue39124)
        media = round(Decimal(f'{media}'), 2)
        if salvar:
            self.media_periodo = media
            self.save()
        #
        self.processo_progressao.calcular_media_processo(salvar=salvar)
        #
        return media

    def obter_peso_periodo(self):
        delta = self.data_fim - self.data_inicio
        return abs(delta.days)

    def obter_avaliadores(self, incluir_avaliado=True):
        avaliadores = []
        for avaliacao in self.processoprogressaoavaliacao_set.all():
            if avaliacao.avaliador == self.processo_progressao.avaliado and not incluir_avaliado:
                continue
            if avaliacao.avaliador not in avaliadores:
                avaliadores.append(avaliacao.avaliador)
        return avaliadores

    def tem_avaliador_chefe(self):
        return self.obter_avaliadores_chefe().exists()

    def obter_avaliadores_chefe(self):
        return self.processoprogressaoavaliacao_set.filter(tipo_avaliador=ProcessoProgressaoAvaliacao.TIPO_AVALIADOR_CHEFE)

    class Meta:
        ordering = ('data_inicio',)
        verbose_name = 'Período Avaliado'
        verbose_name_plural = 'Períodos Avaliados'


#
# Representa uma avaliação/questionário
#
class AvaliacaoModelo(models.ModelPlus):
    nome = models.CharField('Descrição do Modelo', max_length=255, unique=True)
    funcao_gratificada = models.BooleanField(
        'Modelo para Servidores com Função Gratificada', default=False, help_text='Não se aplica ao estágio probatório'
    )
    itens_avaliados = models.ManyToManyField('progressoes.AvaliacaoModeloCriterio', verbose_name='Critérios Avaliados')
    tipo = models.IntegerField('Tipo do Processo', choices=ProcessoProgressao.TIPO_CHOICES, default=ProcessoProgressao.TIPO_PROGRESSAO_MERITO)

    class Meta:
        verbose_name = 'Modelo/Ficha de Avaliação'
        verbose_name_plural = 'Modelos/Fichas de Avaliação'

    def __str__(self):
        return f'{self.nome}'

    def get_absolute_url(self):
        return f'/progressoes/avaliacao_modelo_visualizar/{self.pk}/'


#
# Representa um critério (questão) que pode ser usado em um ou mais modelos/fichas de avaliação
#
class AvaliacaoModeloCriterio(models.ModelPlus):
    SEARCH_FIELDS = ['descricao_questao']

    descricao_questao = models.TextField('Descrição do Critério/Questão', unique=True)
    nota_minima = models.PositiveIntegerField('Nota Mínima', help_text='Nota mínima que pode ser dada ao critério/questão', default=0, null=True)
    nota_maxima = models.PositiveIntegerField('Nota Máxima', help_text='Nota máxima que pode ser dada ao critério/questão', default=10, null=True)
    passo_nota = models.FloatField('Intervalo entre Notas', help_text='Passo da nota', default=1.0, null=True)

    def __str__(self):
        return self.descricao_questao

    def clean(self):
        if self.id:  # editando ...
            criterio = AvaliacaoModeloCriterio.objects.get(pk=self.id)
            #
            # "lugares" onde o critério é usado (acrescentar mais lugares quando necessário)
            #
            modelos_avaliacao = AvaliacaoModelo.objects.filter(itens_avaliados__id=criterio.id)
            notas_progressoes = AvaliacaoCriterioNota.objects.filter(criterio_avaliado__id=criterio.id)
            estah_sendo_usado = modelos_avaliacao.exists() or notas_progressoes.exists()
            #
            if estah_sendo_usado and self.descricao_questao != criterio.descricao_questao:
                raise ValidationError(
                    'Não é permitida a alteração da descrição deste critério/questão, '
                    'pois o mesmo já foi selecionado/usado em algumas situações '
                    '(modelos de avaliação ou avaliações realizadas).'
                )

    class Meta:
        verbose_name = 'Critério de Avaliação'
        verbose_name_plural = 'Critérios de Avaliação'
        ordering = ('descricao_questao',)


#
# Representa uma avaliação realizada
#
class ProcessoProgressaoAvaliacao(models.ModelPlus):
    TIPO_AVALIADOR_CHEFE = 0
    TIPO_AVALIADOR_EQUIPE = 1
    TIPO_AVALIADOR_AUTO = 2
    TIPO_AVALIADOR_CHOICES = [
        [TIPO_AVALIADOR_CHEFE, 'Chefe Imediato'],
        [TIPO_AVALIADOR_EQUIPE, 'Membro da Equipe'],
        [TIPO_AVALIADOR_AUTO, 'Auto-Avaliação'],
    ]

    STATUS_AVALIACAO_PENDENTE = 0
    STATUS_AVALIACAO_AVALIADA = 1
    STATUS_AVALIACAO_CHOICES = [[STATUS_AVALIACAO_PENDENTE, 'Pendente'], [STATUS_AVALIACAO_AVALIADA, 'Avaliada']]

    periodo = models.ForeignKeyPlus('progressoes.ProcessoProgressaoPeriodo', on_delete=models.CASCADE)

    avaliador = models.ForeignKeyPlus('comum.Vinculo', on_delete=models.CASCADE, null=True, blank=False)

    tipo_avaliador = models.IntegerField(choices=TIPO_AVALIADOR_CHOICES)
    status_avaliacao = models.IntegerField('Situação do Período', choices=STATUS_AVALIACAO_CHOICES, default=STATUS_AVALIACAO_PENDENTE)
    data_avaliacao = models.DateField('Data da Avaliação', null=True)
    total_pontos = models.FloatField(default=0.0)
    comentario_avaliador = models.TextField(blank=True)
    comentario_avaliado = models.TextField(blank=True)
    comentario_rh = models.TextField(blank=True)
    hash_string = models.TextField('String formadora do Hash', blank=True)
    hash_valor = models.CharFieldPlus('Hash', blank=True)

    assinatura_avaliador = models.TextField('Assinatura do Avaliador', blank=True, null=True, default='')
    data_assinatura_avaliador = models.DateField('Data de Assinatura do Avaliador', null=True, default=None)
    assinatura_avaliado = models.TextField('Assinatura do Avaliado', blank=True, null=True, default='')
    data_assinatura_avaliado = models.DateField('Data de Assinatura do Avaliador', null=True, default=None)

    # um período pode ter 1 ou mais avaliadores com papel de "chefe imediato", os quais podem assinar
    # as avaliações do período como "chefe imediato", por isso a necessidade de armazenar qual chefe
    # imediato assinou a avaliação para que a assinatura seja verificada no futuro
    assinatura_chefe_imediato = models.TextField('Assinatura do Chefe Imediato', blank=True, null=True, default='')
    data_assinatura_chefe_imediato = models.DateField('Data de Assinatura do Chefe Imediato', null=True, default=None)

    chefe_imediato_assinante = models.ForeignKeyPlus(
        'comum.Vinculo', null=True, blank=True, related_name='chefe_imediato_assinante_vinculo', on_delete=models.CASCADE
    )

    #
    # origem do atributo: servidor foi escolhido como avaliador de um processo e notificado via SUAP/email.
    # em seguida o RH remove esse avaliador do processo e o mesmo fica sem saber o que ocorreu. O atributo
    # será usado para verificar se há necessidade ou não de notificar o avaliador caso ele venha ser excluído
    # do processo (se numero_liberacoes > 0, notifica o avaliador, pois o mesmo já tinha conhecimento que participava
    # do processo)
    #
    numero_liberacoes = models.IntegerField(editable=False, default=0)

    def __str__(self):
        return f'Avaliador: {self.avaliador} ({self.get_tipo_avaliador_display()}) - Status: {self.get_status_avaliacao_display()}'

    def get_absolute_url(self):
        return f'/progressoes/abrir_avaliacao/{self.pk}/'

    def obter_itens_avaliados(self):
        # itens avaliados
        itens_avaliados = []

        # modelo de avaliacao
        modelo_avaliacao = self.periodo.avaliacao_modelo

        # notas salvas
        notas_salvas = AvaliacaoCriterioNota.objects.filter(avaliacao=self)

        # criterios do modelo
        for criterio in modelo_avaliacao.itens_avaliados.all():
            # procura a nota
            nota = notas_salvas.filter(criterio_avaliado=criterio)
            if nota.exists():
                criterio_nota = nota[0]
            else:
                if self.status_avaliacao == ProcessoProgressaoAvaliacao.STATUS_AVALIACAO_AVALIADA:
                    continue  # a questão não existia quando a avaliação foi respondida e não poderá fazer parte da lista

                # criterio sem nota salva
                criterio_nota = AvaliacaoCriterioNota()
                criterio_nota.criterio_avaliado = criterio
                criterio_nota.avaliacao = self
            itens_avaliados.append(criterio_nota)

        # todas as notas salvas estão na listagem?
        for nota_salva in notas_salvas:
            if nota_salva not in itens_avaliados:
                itens_avaliados.append(nota_salva)  # uma nota salva associado a um critério que não está mais no modelo
        #
        return itens_avaliados

    @property
    def processo(self):
        return self.periodo.processo_progressao

    @property
    def is_pendente(self):
        return self.status_avaliacao == self.STATUS_AVALIACAO_PENDENTE

    @property
    def is_avaliada(self):
        return self.status_avaliacao == self.STATUS_AVALIACAO_AVALIADA

    def obter_total_pontos(self):
        notas_avaliacao = AvaliacaoCriterioNota.objects.filter(avaliacao=self)
        soma = 0
        for nota in notas_avaliacao:
            soma = soma + nota.nota
        return soma

    def obter_hash_string(self):
        #
        # o avaliador tem influencia sobre os seguintes dados da avaliacao:
        #    - data de avaliacao (definida quando salva as notas da avaliação)
        #    - total de pontos (reflexo das notas que atribuiu)
        #    - seus comentários
        #
        avaliador = self.avaliador
        try:
            hash_string = '{}|{}|{}|{}|{}'.format(
                avaliador.id, avaliador.matricula, self.data_avaliacao.strftime('%d/%m/%Y'), self.total_pontos, self.comentario_avaliador
            )
            return hash_string
        except Exception:
            return ''

    @classmethod
    def obter_hash_valor(cls, hash_string):
        return hashlib.sha1(hash_string.encode('utf8')).hexdigest()

    @property
    def dados_integros(self):
        #
        # verifica se os dados informados pelo avaliador estão íntegros
        #
        hash_string = self.obter_hash_string()
        hash_valor = ProcessoProgressaoAvaliacao.obter_hash_valor(hash_string)
        return (self.hash_string == hash_string) and (self.hash_valor == hash_valor)

    #
    # realivar a avaliacao, editando as notas
    #
    def reavaliar(self):
        self.status_avaliacao = self.STATUS_AVALIACAO_PENDENTE
        self.data_avaliacao = None
        self.total_pontos = 0.0
        self.hash_string = ''
        self.hash_valor = ''
        self.assinatura_avaliado = ''
        self.assinatura_avaliador = ''
        self.assinatura_chefe_imediato = ''
        self.chefe_imediato_assinante = None
        self.data_assinatura_avaliado = None
        self.data_assinatura_avaliador = None
        self.data_assinatura_chefe_imediato = None
        self.save()

    @property
    def media_avaliacao(self):
        #
        # média da avaliação (SEMPRE calculada) numa escala de desempenho de 0 a 10
        #
        # média = (total de pontos * 100 / total de pontos possíveis)/10
        #
        try:
            total_pontos_possiveis = 0
            for criterio in self.obter_itens_avaliados():
                nota_maxima_criterio = criterio.criterio_avaliado.nota_maxima
                total_pontos_possiveis += nota_maxima_criterio
            #
            media = (self.total_pontos * 100 / total_pontos_possiveis) / 10
            media = round(media, 2)
        except Exception:
            media = 0.00
        #
        return media

    @property
    def id_encoded(self):
        # ex: "100:::101:::100:::102:::100"  id da avaliação = 100
        id_avaliacao = f'{self.id}:::{self.periodo.processo_progressao_id}:::{self.id}:::{self.avaliador_id}:::{self.id}'
        # codifica em base64
        id_avaliacao = base64.b64encode(id_avaliacao.encode('utf8')).decode('utf8')
        # url safe
        id_avaliacao = id_avaliacao.replace('+', '-')
        id_avaliacao = id_avaliacao.replace('/', '_')
        id_avaliacao = id_avaliacao.replace('=', 'aeLqsUliFL')
        #
        return id_avaliacao

    @staticmethod
    def id_decoded(id_encoded):
        try:
            id_avaliacao = id_encoded
            # url safe
            id_avaliacao = id_avaliacao.replace('-', '+')
            id_avaliacao = id_avaliacao.replace('_', '/')
            id_avaliacao = id_avaliacao.replace('aeLqsUliFL', '=')
            #
            ids_avaliacao = base64.b64decode(id_avaliacao.encode('utf8')).decode('utf8').split(':::')
            id_avaliacao_1 = ids_avaliacao[0]  # id da avaliacao na posição 1
            id_avaliacao_2 = ids_avaliacao[2]  # id da avaliacao na posição 3
            id_avaliacao_3 = ids_avaliacao[4]  # id da avaliacao na posição 5
            #
            if not (id_avaliacao_1 == id_avaliacao_2 == id_avaliacao_3):
                id_avaliacao = -1
            else:
                id_avaliacao = id_avaliacao_1
            #
            return id_avaliacao
        except Exception:
            return -1

    @property
    def assinatura_avaliado_is_pendente(self):
        return self.status_avaliacao == self.STATUS_AVALIACAO_AVALIADA and not self.assinatura_avaliado

    @property
    def assinatura_avaliador_is_pendente(self):
        return self.status_avaliacao == self.STATUS_AVALIACAO_AVALIADA and not self.assinatura_avaliador

    @property
    def assinatura_chefe_is_pendente(self):
        return self.status_avaliacao == self.STATUS_AVALIACAO_AVALIADA and not self.assinatura_chefe_imediato

    def assinaturas_realizadas_requeridas(self):
        assinaturas_realizadas = 0
        assinaturas_requeridas = 0
        #
        if self.is_avaliada:
            if self.periodo.processo_progressao.is_tipo_progressao_merito:
                assinaturas_requeridas = 3  # 3 assinaturas por avaliação
                if not self.assinatura_avaliado_is_pendente:
                    assinaturas_realizadas += 1
                if not self.assinatura_avaliador_is_pendente:
                    assinaturas_realizadas += 1
                if not self.assinatura_chefe_is_pendente:
                    assinaturas_realizadas += 1
            else:
                assinaturas_requeridas = 1  # 1 assinatura por avaliação
                if not self.assinatura_chefe_is_pendente:
                    assinaturas_realizadas += 1

        #
        return [assinaturas_realizadas, assinaturas_requeridas]  # num assinaturas realizadas/num assinaturas requeridas

    @staticmethod
    def avaliacoes_como_avaliado(avaliado):
        return ProcessoProgressaoAvaliacao.objects.all().filter(periodo__processo_progressao__avaliado=avaliado)

    @staticmethod
    def avaliacoes_como_avaliador(avaliador):
        return ProcessoProgressaoAvaliacao.objects.all().filter(avaliador=avaliador)

    @staticmethod
    def avaliacoes_como_chefe(chefe, distinct=False):
        ids_periodos_de_avaliacoes_como_chefe = (
            ProcessoProgressaoAvaliacao.objects.all()
            .filter(tipo_avaliador=ProcessoProgressaoAvaliacao.TIPO_AVALIADOR_CHEFE, avaliador=chefe)
            .values_list('periodo', flat=True)
        )
        avaliacoes_responsabilidade_chefe = ProcessoProgressaoAvaliacao.objects.filter(periodo__in=ids_periodos_de_avaliacoes_como_chefe)
        return avaliacoes_responsabilidade_chefe

    @staticmethod
    def avaliacoes_pendentes_a_avaliar(avaliador=None, qs_avaliacoes_como_avaliador=None):
        if avaliador is None and qs_avaliacoes_como_avaliador is None:
            return ValueError
        #
        if not qs_avaliacoes_como_avaliador:
            qs_avaliacoes_como_avaliador = ProcessoProgressaoAvaliacao.avaliacoes_como_avaliador(avaliador)
        #
        return qs_avaliacoes_como_avaliador.filter(status_avaliacao=ProcessoProgressaoAvaliacao.STATUS_AVALIACAO_PENDENTE)

    @staticmethod
    def avaliacoes_avaliadas(avaliador=None, qs_avaliacoes_como_avaliador=None):
        if avaliador is None and qs_avaliacoes_como_avaliador is None:
            return ValueError
        #
        if not qs_avaliacoes_como_avaliador:
            qs_avaliacoes_como_avaliador = ProcessoProgressaoAvaliacao.avaliacoes_como_avaliador(avaliador)
        #
        return qs_avaliacoes_como_avaliador.filter(status_avaliacao=ProcessoProgressaoAvaliacao.STATUS_AVALIACAO_AVALIADA)

    @staticmethod
    def avaliacoes_pendentes_a_assinar_como_avaliado(avaliado=None, qs_avaliacoes_como_avaliado=None):
        if avaliado is None and qs_avaliacoes_como_avaliado is None:
            return ValueError
        #
        if not qs_avaliacoes_como_avaliado:
            if avaliado and avaliado.eh_servidor():
                qs_avaliacoes_como_avaliado = ProcessoProgressaoAvaliacao.avaliacoes_como_avaliado(avaliado.relacionamento).filter(
                    periodo__processo_progressao__status=ProcessoProgressao.STATUS_EM_TRAMITE
                )
            else:
                qs_avaliacoes_como_avaliado = ProcessoProgressaoAvaliacao.objects.none()
        #
        return qs_avaliacoes_como_avaliado.filter(
            periodo__processo_progressao__tipo=ProcessoProgressao.TIPO_PROGRESSAO_MERITO,
            status_avaliacao=ProcessoProgressaoAvaliacao.STATUS_AVALIACAO_AVALIADA,
            assinatura_avaliado='',
        )

    @staticmethod
    def avaliacoes_pendentes_a_assinar_como_avaliador(avaliador=None, qs_avaliacoes_como_avaliador=None):
        if avaliador is None and qs_avaliacoes_como_avaliador is None:
            return ValueError
        #
        if not qs_avaliacoes_como_avaliador:
            qs_avaliacoes_como_avaliador = ProcessoProgressaoAvaliacao.avaliacoes_como_avaliador(avaliador).filter(
                periodo__processo_progressao__status=ProcessoProgressao.STATUS_EM_TRAMITE
            )
        #
        return qs_avaliacoes_como_avaliador.filter(
            periodo__processo_progressao__tipo=ProcessoProgressao.TIPO_PROGRESSAO_MERITO,
            status_avaliacao=ProcessoProgressaoAvaliacao.STATUS_AVALIACAO_AVALIADA,
            assinatura_avaliador='',
        )

    @staticmethod
    def avaliacoes_pendentes_a_assinar_como_chefe(chefe=None, qs_avaliacoes_como_chefe=None, distinct=False):
        if chefe is None and qs_avaliacoes_como_chefe is None:
            return ValueError
        #
        if not qs_avaliacoes_como_chefe:
            qs_avaliacoes_como_chefe = ProcessoProgressaoAvaliacao.avaliacoes_como_chefe(chefe, False).filter(
                periodo__processo_progressao__status=ProcessoProgressao.STATUS_EM_TRAMITE
            )
        #
        lista = qs_avaliacoes_como_chefe.filter(status_avaliacao=ProcessoProgressaoAvaliacao.STATUS_AVALIACAO_AVALIADA, assinatura_chefe_imediato='')
        if distinct:
            lista = lista.distinct()
        return lista

    @staticmethod
    def avaliacoes_assinadas_como_avaliado(avaliado=None, qs_avaliacoes_como_avaliado=None):
        if avaliado is None and qs_avaliacoes_como_avaliado is None:
            return ValueError
        #
        if not qs_avaliacoes_como_avaliado:
            qs_avaliacoes_como_avaliado = ProcessoProgressaoAvaliacao.avaliacoes_como_avaliado(avaliado)
        #
        return qs_avaliacoes_como_avaliado.filter(status_avaliacao=ProcessoProgressaoAvaliacao.STATUS_AVALIACAO_AVALIADA).exclude(
            assinatura_avaliado=''
        )

    @staticmethod
    def avaliacoes_assinadas_como_avaliador(avaliador=None, qs_avaliacoes_como_avaliador=None):
        if avaliador is None and qs_avaliacoes_como_avaliador is None:
            return ValueError
        #
        if not qs_avaliacoes_como_avaliador:
            qs_avaliacoes_como_avaliador = ProcessoProgressaoAvaliacao.avaliacoes_como_avaliador(avaliador)
        #
        return qs_avaliacoes_como_avaliador.filter(status_avaliacao=ProcessoProgressaoAvaliacao.STATUS_AVALIACAO_AVALIADA).exclude(
            assinatura_avaliador=''
        )

    @staticmethod
    def avaliacoes_assinadas_como_chefe(chefe=None, qs_avaliacoes_como_chefe=None, distinct=False):
        if chefe is None and qs_avaliacoes_como_chefe is None:
            return ValueError
        #
        if not qs_avaliacoes_como_chefe:
            qs_avaliacoes_como_chefe = ProcessoProgressaoAvaliacao.avaliacoes_como_chefe(chefe, distinct)
        #
        lista = qs_avaliacoes_como_chefe.filter(status_avaliacao=ProcessoProgressaoAvaliacao.STATUS_AVALIACAO_AVALIADA).exclude(
            assinatura_chefe_imediato=''
        )
        if distinct:
            lista = lista.distinct()
        return lista

    def get_assinatura_avaliado_as_html(self):
        if self.assinatura_avaliado:
            return assinatura.quebra_assinatura(self.assinatura_avaliado, 100, assinatura.QUEBRA_LINHA_HTML)
        else:
            return ''

    def get_assinatura_avaliador_as_html(self):
        if self.assinatura_avaliador:
            return assinatura.quebra_assinatura(self.assinatura_avaliador, 100, assinatura.QUEBRA_LINHA_HTML)
        else:
            return ''

    def get_assinatura_chefe_imediato_as_html(self):
        if self.assinatura_chefe_imediato:
            return assinatura.quebra_assinatura(self.assinatura_chefe_imediato, 100, assinatura.QUEBRA_LINHA_HTML)
        else:
            return ''

    class Meta:
        ordering = ('-status_avaliacao', 'avaliador__pessoa__nome')
        verbose_name = 'Ficha de Avaliação'
        verbose_name_plural = 'Fichas de Avaliações'


#
# Representa uma nota dada em uma avaliacao
#
class AvaliacaoCriterioNota(models.ModelPlus):
    avaliacao = models.ForeignKeyPlus('progressoes.ProcessoProgressaoAvaliacao', on_delete=models.CASCADE)
    criterio_avaliado = models.ForeignKeyPlus('progressoes.AvaliacaoModeloCriterio', on_delete=models.CASCADE)
    nota = models.FloatField()

    def __str__(self):
        return f'{self.criterio_avaliado} ({self.nota})'

    class Meta:
        verbose_name = 'Nota'
        verbose_name_plural = 'Notas'


class ServidorAProgredir(models.ModelPlus):
    SEARCH_FIELDS = ['avaliado__pessoa_fisica__nome']

    VIA_PCA = 1
    VIA_PROGRESSAO = 2
    TIPO_CALCULO_CHOICES = (
        (
            VIA_PCA,
            'Via PCA',
        ),
        (VIA_PROGRESSAO, 'Via Progressão'),
    )

    SITUACAO_REGULAR = 1
    SITUACAO_INCONSISTENTE = 2
    SITUACAO_FINALIZADO = 3
    SITUACAO_CHOICES = (
        (SITUACAO_REGULAR, 'Situação Regular'),
        (SITUACAO_INCONSISTENTE, 'Situação Inconsistente'),
        (SITUACAO_FINALIZADO, 'Finalizado'),
    )

    avaliado = models.ForeignKeyPlus('rh.Servidor', on_delete=models.CASCADE)
    data_inicio_contagem = models.DateFieldPlus('Data de Início da Contagem', null=False, blank=False)
    data_fim_contagem = models.DateFieldPlus('Data de Fim da Contagem', null=False, blank=False)
    calculo = models.IntegerFieldPlus('Cálculo', choices=TIPO_CALCULO_CHOICES, default=VIA_PCA)
    situacao = models.IntegerFieldPlus('Situação', choices=SITUACAO_CHOICES, default=SITUACAO_REGULAR)
    data_inicio_contagem_manual = models.DateFieldPlus('Data de Início da Contagem Manual', null=True, blank=True)
    processo_criado = models.BooleanField('Processo Criado?', default=False)
    notificado_45_dias = models.BooleanField('Notificação de 45 dias enviada?', default=False)
    saldo_dias = models.IntegerFieldPlus('Saldo de Dias', default=0, null=False, blank=False, help_text='Saldo de dias para progressão')

    class Meta:
        verbose_name = 'Servidor a Progredir'
        verbose_name_plural = 'Servidores a Progredir'
        permissions = (('pode_ver_relatorio_progressao', 'Pode Ver o Relatório de Progressões'),)

    def __str__(self):
        return f'{self.avaliado} ({self.data_inicio_contagem} a {self.data_fim_contagem})'

    def get_absolute_url(self):
        return f'/progressoes/servidoraprogredir/{self.id}/'

    def tem_saldo_dias(self):
        """
        Verifica se o servidor tem saldo de dias para progressão.
        Retorna True se o saldo for maior que zero, caso contrário, False.
        """
        return self.saldo_dias > 0

    @property
    def data_fim_ajustada(self) -> datetime.date:
        """Data de fim da contagem antecipada pelo saldo de interstício, quando houver."""
        if self.tem_saldo_dias():
            return self.data_fim_contagem - datetime.timedelta(days=self.saldo_dias)
        return self.data_fim_contagem

    def get_dias_restantes(self, checar_novo_periodo: bool = False) -> int:
        hoje = datetime.date.today()
        dias = (self.data_fim_ajustada - hoje).days
        # if checar_novo_periodo:
        #     dias = ((self.data_fim_contagem - relativedelta(months=6)) - hoje).days
        if dias > 0:
            return dias
        return 0

    @property
    def data_fim_contagem_normal(self):
        config = ProcessoProgressao.get_configuracao()
        if not config:
            raise ConfiguracaoProgressao.DoesNotExist(
                'Não foi encontrada uma configuração para a progressão TAE. Cadastre uma configuração para proceguir.'
            )
        _intersticio = config.intersticio_progressao
        return self.data_inicio_contagem + relativedelta(months=_intersticio)

    #
    # Cálculo de saldo das progressões
    @staticmethod
    def _calculando_saldo(processo):
        if processo.data_inicio_contagem_progressao.year != 2023:
            return None

        if not processo.registro_a_progredir or not getattr(processo.avaliado, 'ativo', False):
            return None

        referencia = datetime.date(2024, 12, 31)
        inicio = processo.data_inicio_contagem_progressao
        fim = inicio + relativedelta(months=18)

        if not (inicio <= referencia <= fim):
            return None

        marco_12_meses = inicio + relativedelta(months=12)
        dias_faltando = (referencia - marco_12_meses).days + 1

        return dias_faltando

    #
    @staticmethod
    def verificar_processos(matricula=None):
        servidores_distintos = ServidorAProgredir.objects.order_by('avaliado__matricula').distinct('avaliado__matricula')
        if matricula:
            servidores_distintos = servidores_distintos.filter(avaliado__matricula=matricula)
        for s in servidores_distintos:
            #
            # verificando o registro mais recente com processo não criado
            novo = ServidorAProgredir.objects.filter(avaliado=s.avaliado, processo_criado=False).order_by('data_inicio_contagem').first()
            #
            # verificando o registro mais recente com processo criado
            anterior = ServidorAProgredir.objects.filter(avaliado=s.avaliado, processo_criado=True).order_by('-data_inicio_contagem').first()
            #
            # se houver ambos os registros, calcula o saldo
            if anterior and novo:
                processo = ProcessoProgressao.objects.filter(registro_a_progredir=anterior).first()
                if processo:
                    dias_saldo = ServidorAProgredir._calculando_saldo(processo)
                    if dias_saldo is not None:
                        novo.saldo_dias = dias_saldo
                        novo.save()

    # - fim cálculo de saldo das progressões


class ConfiguracaoProgressao(models.ModelPlus):
    intersticio_progressao = models.IntegerFieldPlus('Interstício da Progressão TAE', default=0, null=False, blank=False, help_text='Em meses')
    intersticio_estagio_probatorio = models.IntegerFieldPlus(
        'Interstício do Estágio Probatório', default=0, null=False, blank=False, help_text='Em meses'
    )
    dias_antecedencia_calcular = models.IntegerFieldPlus('Dias de Antecedência para Calcular Nova Progressão', default=0, null=False, blank=False)
    gerar_inconsistencia_dias = models.IntegerFieldPlus('Gerar Inconsistência Dias', default=0, null=False, blank=False)
    media_aprovacao = models.DecimalFieldPlus('Média para Aprovação', decimal_places=1, max_digits=3, null=False, blank=False)
    ativo = models.BooleanField('Ativo', default=True)
    data_cadastro = models.DateTimeField('Data de Cadastro', auto_now_add=True, editable=False)
    data_ultima_atualizacao = models.DateTimeFieldPlus('Data de Última Atualização', auto_now=True, editable=False)

    class Meta:
        verbose_name = 'Configuração da Progressão'
        verbose_name_plural = 'Configurações da Progressão'

    def __str__(self):
        return f'Interstício Progressão: {self.intersticio_progressao} | Interstício Estágio Probatório: {self.intersticio_estagio_probatorio}'

    def save(self, *args, **kwargs):
        # manter apenas um registro ativo
        if self.ativo:
            ConfiguracaoProgressao.objects.all().update(ativo=False)
        return super().save(*args, **kwargs)


class SiglaSetorPrimeiroTramite(models.ModelPlus):
    """Sigla de setor de primeiro trâmite do processo de progressão, por tipo de unidade e com precedência.

    Reitoria casa a sigla exata; campus casa por ``icontains`` (uma sigla atende todos os campi).
    """

    TIPO_REITORIA = 'reitoria'
    TIPO_CAMPUS = 'campus'
    TIPO_CHOICES = [[TIPO_REITORIA, 'Reitoria'], [TIPO_CAMPUS, 'Campus']]

    tipo = models.CharFieldPlus('Tipo', max_length=10, choices=TIPO_CHOICES)
    sigla = models.CharFieldPlus(
        'Sigla', max_length=50, help_text='Reitoria: sigla exata do setor. Campus: parte da sigla, buscada nos setores do campus do avaliado.'
    )
    ordem = models.PositiveIntegerFieldPlus('Ordem', default=1, help_text='Precedência: as siglas de menor ordem são testadas primeiro.')

    class Meta:
        verbose_name = 'Sigla de Setor de Primeiro Trâmite'
        verbose_name_plural = 'Siglas de Setores de Primeiro Trâmite'
        ordering = ('tipo', 'ordem', 'pk')
        unique_together = ('tipo', 'sigla')
        constraints = [
            models.UniqueConstraint(
                fields=['tipo', 'ordem'],
                name='progressoes_sigla_primeiro_tramite_ordem_unica',
                violation_error_message='Já existe uma sigla deste tipo com esta ordem.',
            )
        ]

    def __str__(self) -> str:
        return f'{self.get_tipo_display()}: {self.sigla}'

    def save(self, *args, **kwargs) -> None:
        self.sigla = self.sigla.strip()
        super().save(*args, **kwargs)

    @classmethod
    def siglas(cls, tipo: str) -> list[str]:
        """Siglas do ``tipo`` pela ordem de precedência, sem as vazias (que casariam qualquer setor no ``icontains``)."""
        return [sigla for sigla in cls.objects.filter(tipo=tipo).order_by('ordem', 'pk').values_list('sigla', flat=True) if sigla.strip()]
