import datetime
import time
from collections import OrderedDict
from datetime import date, timedelta
from typing import TypeVar

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.models import Model, Q, Subquery
from django.db.models.functions import ExtractHour
from django.db.models.query import QuerySet
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils.safestring import mark_safe

from comum.models import Configuracao, Predio, PrestadorServico, User, Vinculo
from comum.utils import (
    tl,
)
from djtools.db import models
from djtools.db.models import ModelPlus
from djtools.html.graficos import ColumnChart
from djtools.utils import (
    agrupar_em_pares,
    datas_entre,
    djtools_max,
    djtools_min,
    existe_conflito_entre_intervalos,
    formata_segundos,
    formata_segundos_h_min_seg,
    formata_timedelta,
    get_session_cache,
    meses_entre,
    send_notification,
)
from ponto.enums import TipoLiberacao
from ponto.exceptions import PontoException
from ponto.utils import Periodo, mesmo_campus, pode_ver_frequencia, possui_horario_extra_noturno
from rh.models import (
    AfastamentoSiape,
    AlertaGestaoPessoa,
    CargaHorariaReduzida,
    Funcao,
    JornadaTrabalho,
    Servidor,
    ServidorAfastamento,
    UnidadeOrganizacional,
    Viagem,
)
from rh.utils import periodos_estah_no_pgd1_pgd2


class Frequencia(models.ModelPlus):
    INCONSISTENCIA_MENOR_JORNADA = 'INCONSISTENCIA_MENOR_JORNADA'
    INCONSISTENCIA_MAIOR_JORNADA = 'INCONSISTENCIA_MAIOR_JORNADA'
    INCONSISTENCIA_FALTA = 'INCONSISTENCIA_FALTA'
    INCONSISTENCIA_TEMPO_MAIOR_DEZ_HORAS = 'INCONSISTENCIA_TEMPO_MAIOR_DEZ_HORAS'
    INCONSISTENCIA_TRABALHO_FDS = 'INCONSISTENCIA_TRABALHO_FDS'
    INCONSISTENCIA_NUMERO_IMPAR_REGISTROS = 'INCONSISTENCIA_NUMERO_IMPAR_REGISTROS'
    INCONSISTENCIA_INTERVALO_INFERIOR_1H = 'INCONSISTENCIA_INTERVALO_INFERIOR_1H'
    INCONSISTENCIA_INTERVALO_SUPERIOR_3H = 'INCONSISTENCIA_INTERVALO_SUPERIOR_3H'
    INCONSISTENCIA_NENHUM_INTERVALO = 'INCONSISTENCIA_NENHUM_INTERVALO'
    # INCONSISTENCIA_TURNO_INSUFICIENTE = 'INCONSISTENCIA_TURNO_INSUFICIENTE'
    # INCONSISTENCIA_TURNO_EXCESSIVO = 'INCONSISTENCIA_TURNO_EXCESSIVO'
    # INCONSISTENCIA_ATRASO = 'INCONSISTENCIA_ATRASO'

    DESCRICAO_INCONSISTENCIA = {
        INCONSISTENCIA_MENOR_JORNADA: 'Tempo inferior ao expediente',
        INCONSISTENCIA_MAIOR_JORNADA: 'Tempo excedente ao expediente',
        INCONSISTENCIA_FALTA: 'Sem registro',
        INCONSISTENCIA_TEMPO_MAIOR_DEZ_HORAS: 'Tempo de trabalho superior a 10h',
        INCONSISTENCIA_TRABALHO_FDS: 'Tempo de trabalho no fim de semana',
        INCONSISTENCIA_NUMERO_IMPAR_REGISTROS: 'Número incompleto de registros de frequências',
        INCONSISTENCIA_INTERVALO_INFERIOR_1H: 'Intervalo de descanso/refeição inferior a 1 hora',
        INCONSISTENCIA_INTERVALO_SUPERIOR_3H: 'Intervalo de descanso/refeição superior a 3 horas',
        INCONSISTENCIA_NENHUM_INTERVALO: 'Ausência de intervalo',
        # INCONSISTENCIA_TURNO_INSUFICIENTE: 'Turno ininterrupto insuficiente (menor que 2h)',
        # INCONSISTENCIA_TURNO_EXCESSIVO: 'Turno ininterrupto excessivo (maior que 6h15min)',
        # INCONSISTENCIA_ATRASO: 'Atraso no horário de chegada',
        '': '',
    }

    DISPLAY_INCONSISTENCIA = {
        INCONSISTENCIA_MENOR_JORNADA: {
            'long_display': DESCRICAO_INCONSISTENCIA[INCONSISTENCIA_MENOR_JORNADA],
            'short_display': 'Duração inferior',
            'status': 'info',
            'icone': 'calendar-minus',
        },
        INCONSISTENCIA_MAIOR_JORNADA: {
            'long_display': DESCRICAO_INCONSISTENCIA[INCONSISTENCIA_MAIOR_JORNADA],
            'short_display': 'Duração excedente',
            'status': 'info',
            'icone': 'calendar-plus',
        },
        INCONSISTENCIA_FALTA: {
            'long_display': DESCRICAO_INCONSISTENCIA[INCONSISTENCIA_FALTA],
            'short_display': 'Sem registros',
            'status': 'error',
            'icone': 'times',
        },
        INCONSISTENCIA_TEMPO_MAIOR_DEZ_HORAS: {
            'long_display': DESCRICAO_INCONSISTENCIA[INCONSISTENCIA_TEMPO_MAIOR_DEZ_HORAS],
            'short_display': 'Duração maior que 10h',
            'status': 'alert',
            'icone': 'calendar-times',
        },
        INCONSISTENCIA_TRABALHO_FDS: {
            'long_display': DESCRICAO_INCONSISTENCIA[INCONSISTENCIA_TRABALHO_FDS],
            'short_display': 'Trabalho no fim de semana',
            'status': 'error',
            'icone': 'times',
        },
        INCONSISTENCIA_NUMERO_IMPAR_REGISTROS: {
            'long_display': DESCRICAO_INCONSISTENCIA[INCONSISTENCIA_NUMERO_IMPAR_REGISTROS],
            'short_display': 'Registros insuficientes',
            'status': 'error',
            'icone': 'calendar-times',
        },
        INCONSISTENCIA_INTERVALO_INFERIOR_1H: {
            'long_display': DESCRICAO_INCONSISTENCIA[INCONSISTENCIA_INTERVALO_INFERIOR_1H],
            'short_display': 'Intervalo inferior a 1h',
            'status': 'alert',
            'icone': 'times',
        },
        INCONSISTENCIA_INTERVALO_SUPERIOR_3H: {
            'long_display': DESCRICAO_INCONSISTENCIA[INCONSISTENCIA_INTERVALO_SUPERIOR_3H],
            'short_display': 'Intervalo superior a 3h',
            'status': 'alert',
            'icone': 'times',
        },
        INCONSISTENCIA_NENHUM_INTERVALO: {
            'long_display': DESCRICAO_INCONSISTENCIA[INCONSISTENCIA_NENHUM_INTERVALO],
            'short_display': 'Ausência de intervalo',
            'status': 'alert',
            'icone': 'times',
        },
        # INCONSISTENCIA_TURNO_INSUFICIENTE: dict(
        #     long_display=DESCRICAO_INCONSISTENCIA[INCONSISTENCIA_TURNO_INSUFICIENTE],
        #     short_display="Turno ininterrupto menor que 2h",
        #     status="alert",
        #     icone="times"),
        # INCONSISTENCIA_TURNO_EXCESSIVO: {
        #     'long_display': DESCRICAO_INCONSISTENCIA[INCONSISTENCIA_TURNO_EXCESSIVO],
        #     'short_display': 'Turno ininterrupto maior que 6h15min',
        #     'status': 'alert',
        #     'icone': 'times',
        # },
        # INCONSISTENCIA_ATRASO: dict(
        #     long_display=DESCRICAO_INCONSISTENCIA[INCONSISTENCIA_ATRASO],
        #     short_display="Chegada em atraso",
        #     status="error",
        #     icone="times"),
        '': {},
    }

    ###
    # situação das inconsistências
    # abono
    SITUACAO_INCONSISTENCIA_DESCONSIDERAR_ABONO = 'desconsiderar_abono'
    SITUACAO_INCONSISTENCIA_COM_ABONO = 'com_abono'
    SITUACAO_INCONSISTENCIA_SEM_ABONO = 'sem_abono'
    SITUACAO_INCONSISTENCIA_COM_OU_SEM_ABONO = 'com_ou_sem_abono'
    SITUACAO_INCONSISTENCIA_ABONO_CHOICES = [
        SITUACAO_INCONSISTENCIA_DESCONSIDERAR_ABONO,
        SITUACAO_INCONSISTENCIA_COM_ABONO,
        SITUACAO_INCONSISTENCIA_SEM_ABONO,
        SITUACAO_INCONSISTENCIA_COM_OU_SEM_ABONO,
    ]
    # débito de CH
    SITUACAO_INCONSISTENCIA_DESCONSIDERAR_DEBITO = 'desconsiderar_debito'
    SITUACAO_INCONSISTENCIA_COM_DEBITO_TODO_COMPENSADO = 'com_debito_total_compensado'
    SITUACAO_INCONSISTENCIA_COM_DEBITO_PARTE_COMPENSADO = 'com_debito_parte_compensado'
    SITUACAO_INCONSISTENCIA_COM_DEBITO_NADA_COMPENSADO = 'com_debito_nada_compensado'
    SITUACAO_INCONSISTENCIA_COM_DEBITO_PENDENTE = 'com_debito_nao_compensado'
    SITUACAO_INCONSISTENCIA_COM_DEBITO_COMPENSADO_OU_PENDENTE = 'com_debito_compensado_ou_nao'
    SITUACAO_INCONSISTENCIA_DEBITO_CHOICES = [
        SITUACAO_INCONSISTENCIA_DESCONSIDERAR_DEBITO,
        SITUACAO_INCONSISTENCIA_COM_DEBITO_TODO_COMPENSADO,
        SITUACAO_INCONSISTENCIA_COM_DEBITO_PARTE_COMPENSADO,
        SITUACAO_INCONSISTENCIA_COM_DEBITO_NADA_COMPENSADO,
        SITUACAO_INCONSISTENCIA_COM_DEBITO_PENDENTE,
        SITUACAO_INCONSISTENCIA_COM_DEBITO_COMPENSADO_OU_PENDENTE,
    ]

    vinculo = models.ForeignKeyPlus('comum.Vinculo', null=True, on_delete=models.CASCADE)
    horario = models.DateTimeField(db_index=True)
    maquina = models.ForeignKeyPlus('ponto.Maquina', on_delete=models.CASCADE)
    acao = models.CharField('Ação', max_length=1)
    online = models.BooleanField(default=True)
    ip = models.GenericIPAddressField(verbose_name='IP', null=True, blank=True)

    class History:
        disabled = True

    class Meta:
        db_table = 'frequencia'
        verbose_name = 'Frequência'
        verbose_name_plural = 'Frequências'

        unique_together = ('vinculo', 'horario')
        permissions = (
            ('pode_ver_frequencia_propria', 'Pode ver frequência própria'),
            ('pode_ver_frequencias_enquanto_foi_chefe', 'Pode ver frequência de quando foi chefe'),
            ('pode_ver_frequencia_campus', 'Pode ver frequência de campus'),
            ('pode_ver_frequencia_todos', 'Pode ver frequência de todos'),
            ('pode_ver_frequencia_estagiarios', 'Pode ver frequências de estagiários'),
            ('pode_ver_frequencia_bolsistas', 'Pode ver frequências de bolsistas'),
            ('pode_ver_frequencia_terceirizados_propria', 'Pode ver frequência própria como terceirizado'),
            ('pode_ver_frequencia_terceirizados_setor', 'Pode ver frequências de terceirizados'),
            ('pode_ver_frequencia_terceirizados_campus', 'Pode ver frequências de terceirizados'),
            ('pode_ver_frequencia_terceirizados_todos', 'Pode ver frequências de terceirizados'),
            ('pode_ver_frequencia_extra_noturna', 'Pode ver frequência extra noturna'),
            ('pode_ver_frequencia_por_cargo', 'Pode ver frequência por cargo'),
            ('eh_gerente_sistemico_ponto', 'É gerente sistêmico de ponto'),
        )

    # -------------------------------------------------
    # Aplicação das inconsistências no ponto

    class NaoAplicar:
        pass

    class AplicarAQualquerTempo:
        pass

    class AplicarAPartirDe:
        def __init__(self, data_inicio: date):
            self.data_inicio = data_inicio

    @classmethod
    def get_aplicacao_inconsistencia(cls, inconsistencia: str) -> NaoAplicar | AplicarAQualquerTempo | AplicarAPartirDe:
        # inconsistências anteriores à demanda 1547
        if inconsistencia in [
            cls.INCONSISTENCIA_MENOR_JORNADA,
            cls.INCONSISTENCIA_MAIOR_JORNADA,
            cls.INCONSISTENCIA_FALTA,
            cls.INCONSISTENCIA_TEMPO_MAIOR_DEZ_HORAS,
            cls.INCONSISTENCIA_TRABALHO_FDS,
            cls.INCONSISTENCIA_NUMERO_IMPAR_REGISTROS,
        ]:
            return Frequencia.AplicarAQualquerTempo()

        # inconsistências a partir da demanda 1547
        if inconsistencia in [
            cls.INCONSISTENCIA_INTERVALO_INFERIOR_1H,
            cls.INCONSISTENCIA_INTERVALO_SUPERIOR_3H,
            cls.INCONSISTENCIA_NENHUM_INTERVALO,
            # cls.INCONSISTENCIA_TURNO_INSUFICIENTE,
            # cls.INCONSISTENCIA_TURNO_EXCESSIVO,
            # cls.INCONSISTENCIA_ATRASO,
        ]:
            from comum.models import Configuracao

            data_inicio_aplicacao_conf = None  # aaaa-mm-dd

            if inconsistencia == cls.INCONSISTENCIA_INTERVALO_INFERIOR_1H:
                data_inicio_aplicacao_conf = Configuracao.get_valor_por_chave(app='rh', chave='inconsistencia_intervalo_inferior_1h_data_inicio')
            elif inconsistencia == cls.INCONSISTENCIA_INTERVALO_SUPERIOR_3H:
                data_inicio_aplicacao_conf = Configuracao.get_valor_por_chave(app='rh', chave='inconsistencia_intervalo_superior_3h_data_inicio')
            elif inconsistencia == cls.INCONSISTENCIA_NENHUM_INTERVALO:
                data_inicio_aplicacao_conf = Configuracao.get_valor_por_chave(app='rh', chave='inconsistencia_nenhum_intervalo_data_inicio')
            # elif inconsistencia == cls.INCONSISTENCIA_TURNO_INSUFICIENTE:
            #     data_inicio_aplicacao_conf = Configuracao.get_valor_por_chave(app="rh", chave="inconsistencia_turno_insuficiente_data_inicio")
            # elif inconsistencia == cls.INCONSISTENCIA_TURNO_EXCESSIVO:
            #     data_inicio_aplicacao_conf = Configuracao.get_valor_por_chave(app='rh', chave='inconsistencia_turno_excessivo_data_inicio')
            # elif inconsistencia == cls.INCONSISTENCIA_ATRASO:
            #     data_inicio_aplicacao_conf = Configuracao.get_valor_por_chave(app="rh", chave="inconsistencia_atraso")

            try:
                data_inicio_aplicacao = datetime.datetime.strptime(data_inicio_aplicacao_conf, '%Y-%m-%d').date()
            except Exception:
                data_inicio_aplicacao = None

            if data_inicio_aplicacao:
                return Frequencia.AplicarAPartirDe(data_inicio_aplicacao)

        return Frequencia.NaoAplicar()

    @classmethod
    def pode_aplicar_inconsistencia(cls, data: date, inconsistencia: str) -> bool:
        aplicacao_inconsistencia = cls.get_aplicacao_inconsistencia(inconsistencia)

        if isinstance(aplicacao_inconsistencia, Frequencia.AplicarAPartirDe):
            return aplicacao_inconsistencia.data_inicio <= data
        elif isinstance(aplicacao_inconsistencia, Frequencia.AplicarAQualquerTempo):
            return True

        return False

    # -------------------------------------------------

    @classmethod
    def get_horario_extra_noturno(cls, par):
        extra_segundos = 0
        extra_minutos = 0
        horario_limite = 22
        excede_horario_limite = 23
        entrada = par[0]
        saida = par[1]
        if entrada.hour <= horario_limite and saida.hour >= excede_horario_limite:
            extra_minutos = 60
        elif entrada.hour == horario_limite and saida.hour == horario_limite:
            extra_minutos = saida.minute - entrada.minute
            extra_segundos = saida.second - entrada.second
        elif saida.hour == horario_limite:
            extra_minutos = saida.minute
            extra_segundos = saida.second
        total_segundos = extra_segundos + extra_minutos * 60
        return total_segundos

    @classmethod
    def insere_frequencia(cls, vinculo, maquina, horario=None, online=True, ip=None):
        """
        Método que insere frequência para o funcionario. Usado pelo terminal.
        :param vinculo:
        :param maquina:
        :param horario:
        :param online:
        :return:
        """
        if maquina.ativo and maquina.cliente_ponto:
            horario_frequencia = horario or datetime.datetime.now()
            frequencias_dia = cls.get_frequencias_por_data(vinculo, horario_frequencia.date())

            acao_default = (frequencias_dia.count() % 2) and 'S' or 'E'

            Frequencia.objects.get_or_create(
                vinculo=vinculo, horario=horario_frequencia, defaults={'maquina': maquina, 'acao': acao_default, 'online': online, 'ip': ip}
            )

            # Nota: Organiza as frequências ajustando as ações no caso de vir uma
            # frequencia batida anteriormente a uma já importada
            reorganizar_acoes = frequencias_dia.filter(horario__gt=horario_frequencia).count()
            if reorganizar_acoes:
                for index, f in enumerate(frequencias_dia):
                    ordem = index + 1
                    if ordem % 2:
                        f.acao = 'E'
                    else:
                        f.acao = 'S'
                    f.save()

    @classmethod
    def get_frequencias_por_periodo(cls, vinculo, data_inicio, data_fim):
        """
        Recupera Frequências por Período
        :param pessoa:
        :param data_inicio:
        :param data_fim:
        :return: Frequencias do Período
        """
        return cls.objects.filter(
            vinculo=vinculo,
            horario__range=[
                datetime.datetime(data_inicio.year, data_inicio.month, data_inicio.day),
                datetime.datetime(data_fim.year, data_fim.month, data_fim.day, 23, 59, 59),
            ],
        ).order_by('horario')

    @classmethod
    def get_frequencias_por_data(cls, vinculo, data):
        return cls.get_frequencias_por_periodo(vinculo, data, data)

    @classmethod
    def get_tempo_entre_frequencias(cls, frequencias):
        """
        Recebe queryset de frequencias ou lista de horarios e retorna tempo em segundos
        :param frequencias:
        :return: tempo em segundos
        """

        tempo = 0
        if isinstance(frequencias, QuerySet) and frequencias.exists():
            lista_frequencias = agrupar_em_pares(frequencias.values_list('horario', flat=True))
        elif frequencias:
            lista_frequencias = agrupar_em_pares([freq.horario if isinstance(freq, Frequencia) else freq for freq in frequencias])
        else:
            return tempo

        for par in lista_frequencias:
            if len(par) == 2:
                delta = par[1] - par[0]
                segundos = delta.seconds
            else:
                segundos = 0
            tempo += segundos

        return tempo

    ######
    # Calcula intervalos de descanso/refeição/outro.
    # Calcula turnos trabalhados

    @classmethod
    def get_intervalos_entre_frequencias(cls, frequencias) -> list:
        """
        Recebe queryset de frequências ou uma lista de horários.
        Retorna uma lista com os intervalos (IntervaloPonto).
        """

        class IntervaloPonto:
            def __init__(self, data_hora_inicio: datetime, data_hora_fim: datetime):
                self.data_hora_inicio = data_hora_inicio
                self.data_hora_fim = data_hora_fim

            def __str__(self):
                return f'{self.data_hora_inicio.strftime("%d/%m/%Y %H:%M:%S")} a {self.data_hora_fim.strftime("%d/%m/%Y %H:%M:%S")}'

            @property
            def segundos(self):
                return (self.data_hora_fim - self.data_hora_inicio).seconds

        ###

        if isinstance(frequencias, QuerySet) and frequencias.exists():
            horarios = frequencias.values_list('horario', flat=True)
        elif frequencias:
            horarios = [freq.horario if isinstance(freq, Frequencia) else freq for freq in frequencias]
        else:
            return []

        pares_saidas_entradas = []
        horarios_count = 0
        par_saida = None
        par_entrada = None

        # horarios = [entrada, saida, entrada, saida, ...]

        for horario in horarios:
            horarios_count += 1
            if horarios_count > 1 and (horarios_count % 2 == 1):
                par_entrada = horario
            if horarios_count % 2 == 0:
                par_saida = horario
            if par_saida and par_entrada:
                pares_saidas_entradas.append([par_saida, par_entrada])
                par_saida = None
                par_entrada = None

        intervalos: list[IntervaloPonto] = []

        for par in pares_saidas_entradas:
            intervalos.append(IntervaloPonto(par[0], par[1]))

        return intervalos

    @classmethod
    def get_turnos_entre_frequencias(cls, frequencias) -> list:
        """
        Recebe queryset de frequências ou uma lista de horários.
        Retorna uma lista com os turnos trabalhados (TurnoTrabalhadoPonto).
        """

        class TurnoTrabalhadoPonto:
            def __init__(self, data_hora_inicio: datetime, data_hora_fim: datetime):
                self.data_hora_inicio = data_hora_inicio
                self.data_hora_fim = data_hora_fim

            def __str__(self):
                return f'{self.data_hora_inicio.strftime("%d/%m/%Y %H:%M:%S")} a {self.data_hora_fim.strftime("%d/%m/%Y %H:%M:%S")}'

            @property
            def segundos(self):
                return (self.data_hora_fim - self.data_hora_inicio).seconds

        ###

        if isinstance(frequencias, QuerySet) and frequencias.exists():
            horarios = frequencias.values_list('horario', flat=True)
        elif frequencias:
            horarios = [freq.horario if isinstance(freq, Frequencia) else freq for freq in frequencias]
        else:
            return []

        pares_entradas_saidas = []
        horarios_count = 0
        par_entrada = None
        par_saida = None

        # horarios = [entrada, saida, entrada, saida, ...]

        for horario in horarios:
            horarios_count += 1
            if horarios_count % 2 == 1:
                par_entrada = horario
            if horarios_count % 2 == 0:
                par_saida = horario
            if par_saida and par_entrada:
                pares_entradas_saidas.append([par_entrada, par_saida])
                par_saida = None
                par_entrada = None

        turnos: list[TurnoTrabalhadoPonto] = []

        for par in pares_entradas_saidas:
            turnos.append(TurnoTrabalhadoPonto(par[0], par[1]))

        return turnos

    ######

    @classmethod
    def relatorio_frequencias_prestador(cls, vinculo, data_ini=None, data_fim=None, sabado=True, domingo=True):
        data_ini = data_ini or date.today()
        data_fim = data_fim or date.today()
        servidores = Servidor.objects.filter(pessoa_fisica__cpf=vinculo.pessoa.pessoafisica.cpf)
        eh_servidor = servidores.exists()
        dados = OrderedDict()
        observacoes_data = []

        for dia in datas_entre(data_ini, data_fim, sabado, domingo):
            existe_conflitos = ''
            frequencias_dia_servidor = {}
            frequencias_prestador = Frequencia.get_frequencias_por_data(vinculo, dia).order_by('horario')
            tempo = 0
            if frequencias_prestador.exists():
                duracao = 0
                # Se a frequencia do prestador existe nós buscamos se existe a frequencia deste como servidor para saber se
                # Existem conflitos entre os horários"
                if eh_servidor:
                    frequencias_servidor = Frequencia.objects.none()

                    for servidor in servidores:
                        frequencias_servidor = Frequencia.get_frequencias_por_data(servidor.get_vinculo(), dia).order_by('horario')
                        frequencias_dia_servidor[servidor.matricula] = {'frequencias': frequencias_servidor}

                        #                       Verificacao dos conflitos entre as frequencias
                        if frequencias_prestador.count() % 2 == 0:
                            if frequencias_servidor.count() % 2 == 0:
                                if existe_conflito_entre_intervalos(
                                    list(frequencias_prestador.values_list('horario', flat=True))
                                    + list(frequencias_servidor.values_list('horario', flat=True))
                                ):
                                    existe_conflitos = 'Há conflitos entre frequências do servidor/prestador de serviço.'
                            else:
                                existe_conflitos = 'Frequência como servidor em aberto.'
                        else:
                            existe_conflitos = 'Existe frequência de entrada mas não de saída do prestador.'

                for par in agrupar_em_pares(frequencias_prestador.values_list('horario', flat=True)):
                    if len(par) == 2:
                        delta = par[1] - par[0]
                        segundos = delta.seconds
                    else:
                        segundos = 0
                    tempo += segundos

            observacoes = Observacao.objects.filter(vinculo=vinculo, data=dia)
            if observacoes.exists():
                observacoes_data.append(observacoes.distinct('data').get().data)

            liberacoes = Liberacao.filtrar_por_dia(vinculo=vinculo, data=dia)

            duracao = time.strftime('%H:%M:%S', time.gmtime(tempo))
            duracao_segundos = tempo

            dados[dia] = {
                'dia': dia,
                'horarios': frequencias_prestador,
                'horarios_servidor': frequencias_dia_servidor,
                'liberacoes': liberacoes,
                'observacoes': observacoes,
                'duracao': duracao,
                'duracao_segundos': duracao_segundos,
                'existe_conflitos': existe_conflitos,
            }
        datas_observacoes_extra = (
            Observacao.objects.filter(vinculo=vinculo, data__lte=data_fim, data__gte=data_ini)
            .exclude(data__in=observacoes_data)
            .values_list('data', flat=True)
            .distinct()
        )
        if datas_observacoes_extra.exists():
            for data_obs in datas_observacoes_extra:
                observacoes_extra = Observacao.objects.filter(vinculo=vinculo, data=data_obs)
                dados[data_obs] = {
                    'dia': data_obs,
                    'horarios': None,
                    'horarios_servidor': None,
                    'liberacoes': None,
                    'observacoes': observacoes_extra,
                    'duracao': time.strftime('%H:%M:%S', time.gmtime(0)),
                    'duracao_segundos': 0,
                    'existe_conflitos': None,
                }
            dados = OrderedDict(sorted(dados.items()))

        lista = list(dados.values())
        return lista

    @classmethod
    def relatorio_frequencias_setor(
        cls,
        setor,
        data_ini=None,
        data_fim=None,
        servidor_logado=None,
        so_inconsistentes=False,
        so_frequencias_em_que_era_chefe=False,
        so_inconsistentes_apenas_esta_inconsistencia=None,
        so_inconsistentes_situacao_abono=SITUACAO_INCONSISTENCIA_COM_OU_SEM_ABONO,
        so_inconsistentes_situacao_debito=SITUACAO_INCONSISTENCIA_COM_DEBITO_COMPENSADO_OU_PENDENTE,
        servidores=None,
    ):
        ####################################################################################################
        # funcionarios = setor.get_servidores(recursivo).filter(ativo=True)
        ####################################################################################################

        # apenas os funcionários que, no período selecionado, estavam no setor informado
        # (OU em seus setores descendentes)
        dias_em_que_foi_chefe_setor = []
        if servidor_logado.eh_servidor:
            for funcao_servidor in servidor_logado.historico_funcao(data_ini, data_fim).filter(
                setor_suap__isnull=False, funcao__codigo__in=Funcao.get_codigos_funcao_chefia()
            ):
                if setor in funcao_servidor.setor_suap.descendentes:
                    if funcao_servidor.data_inicio_funcao < data_ini:
                        funcao_servidor.data_inicio_funcao = data_ini
                    if not funcao_servidor.data_fim_funcao or funcao_servidor.data_fim_funcao > data_fim:
                        funcao_servidor.data_fim_funcao = data_fim
                    dias_em_que_foi_chefe_setor += datas_entre(funcao_servidor.data_inicio_funcao, funcao_servidor.data_fim_funcao)

        lista = []
        for servidor in servidores:
            dias_liberado_frequencia = servidor.get_dias_liberado_frequencia_periodo(data_ini, data_fim)
            relatorio_ponto = cls.relatorio_ponto_pessoa(
                servidor.get_vinculo(),
                data_ini,
                data_fim,
                so_inconsistentes=so_inconsistentes,
                dias_em_que_foi_chefe_setor=dias_em_que_foi_chefe_setor,
                so_frequencias_em_que_era_chefe=so_frequencias_em_que_era_chefe,
                trata_compensacoes=True,
                dias_liberado_frequencia=dias_liberado_frequencia,
                so_inconsistentes_apenas_esta_inconsistencia=so_inconsistentes_apenas_esta_inconsistencia,
                so_inconsistentes_situacao_abono=so_inconsistentes_situacao_abono,
                so_inconsistentes_situacao_debito=so_inconsistentes_situacao_debito,
            )
            cls.relatorio_ponto_pessoa_update(relatorio_ponto)
            lista.append(relatorio_ponto)

        return lista

    @classmethod
    def get_inconsistencias(cls, vinculo, data_inicio, data_fim, contexto_compensacao) -> OrderedDict[date, list]:
        """
        Retorna uma lista de inconsistências (constantes do modelo Frequencia) por data.
        Procura por período e utiliza um contexto de compensação como fonte das informações.
        """
        tolerancia_15min = Configuracao.get_valor_por_chave('ponto', 'tolerancia_15_min')

        inconsistencias = OrderedDict[date, list]()

        # turno_minimo_em_segundos = 2 * 60 * 60
        # turno_maximo_em_segundos = (6 * 60 * 60) + ((15 * 60) if tolerancia_15min else 0)

        tolerancia_15min_em_segundos = 0
        if tolerancia_15min:
            tolerancia_15min_em_segundos = 900

        intervalo_1h_em_segundos = 1 * 60 * 60
        intervalo_3h_em_segundos = 3 * 60 * 60

        data_inicio_exercicio_na_instituicao = None
        sub_instance = vinculo.relacionamento
        if isinstance(sub_instance, Servidor):
            if sub_instance.data_inicio_exercicio_na_instituicao:
                data_inicio_exercicio_na_instituicao = sub_instance.data_inicio_exercicio_na_instituicao

        ch_reduzida_processos_deferidos = OrderedDict[int, tuple[date, date]]()
        for ch_reduzida_processo_deferido in CargaHorariaReduzida.get_processos_deferidos_por_periodo(sub_instance, data_inicio, data_fim):
            ch_reduzida_processos_deferidos[ch_reduzida_processo_deferido.id] = (
                ch_reduzida_processo_deferido.data_inicio,
                ch_reduzida_processo_deferido.data_termino,
            )

        hoje = datetime.date.today()
        dias_periodo = datas_entre(data_inicio, data_fim)

        for dia in dias_periodo:
            # não há inconsistência hoje ou no futuro
            if dia >= hoje:
                inconsistencias[dia] = []
                continue

            # não há inconsistência se é anterior a data de início de exercício na instituição
            if data_inicio_exercicio_na_instituicao and dia < data_inicio_exercicio_na_instituicao:
                inconsistencias[dia] = []
                continue

            jornada_trabalho_hrs = contexto_compensacao.get_dia(dia).carga_horaria_qtd / 3600
            frequencias = contexto_compensacao.get_dia(dia).relatorio_ponto_do_dia.get('horarios', [])

            inconsistencias_dia = []
            is_fim_de_semana = dia.weekday() >= 5

            # há registro de ponto?
            if frequencias:
                # no fim de semana?
                if is_fim_de_semana:
                    inconsistencias_dia = [cls.INCONSISTENCIA_TRABALHO_FDS]

                # seg-sex?
                else:
                    tempo = cls.get_tempo_entre_frequencias(frequencias)

                    # registros ponto contabilizou ZERO ?
                    if tempo == 0:
                        inconsistencias_dia = [cls.INCONSISTENCIA_FALTA]

                    # registros ponto contabilizou trabalho superior a 10h ?
                    elif tempo >= 36000:
                        inconsistencias_dia = [cls.INCONSISTENCIA_TEMPO_MAIOR_DEZ_HORAS]

                    # CH trabalhada INFERIOR a jornada de trabalho exigida ?
                    # tolerância: 15min
                    elif tempo < (jornada_trabalho_hrs * 60 * 60 - tolerancia_15min_em_segundos):
                        inconsistencias_dia = [cls.INCONSISTENCIA_MENOR_JORNADA]

                    # CH trabalhada SUPERIOR a jornada de trabalho exigida ?
                    # tolerância: 15min
                    elif (tempo > (jornada_trabalho_hrs * 60 * 60 + tolerancia_15min_em_segundos)) and ((jornada_trabalho_hrs * 60 * 60) != 0):
                        inconsistencias_dia = [cls.INCONSISTENCIA_MAIOR_JORNADA]

                    # intervalos indevidos
                    intervalos = cls.get_intervalos_entre_frequencias(frequencias)
                    for intervalo in intervalos:
                        if intervalo.segundos < intervalo_1h_em_segundos:
                            inconsistencias_dia += [cls.INCONSISTENCIA_INTERVALO_INFERIOR_1H]
                        elif intervalo.segundos > intervalo_3h_em_segundos:
                            inconsistencias_dia += [cls.INCONSISTENCIA_INTERVALO_SUPERIOR_3H]

                    # ausência de intervalo ou turno inválido
                    if jornada_trabalho_hrs > 6:
                        if not intervalos:
                            inconsistencias_dia += [cls.INCONSISTENCIA_NENHUM_INTERVALO]
                    # turnos = cls.get_turnos_entre_frequencias(frequencias)
                    # for turno in turnos:
                    # if turno.segundos < turno_minimo_em_segundos:
                    #     inconsistencias_dia += [cls.INCONSISTENCIA_TURNO_INSUFICIENTE]
                    # if turno.segundos > turno_maximo_em_segundos:
                    #     inconsistencias_dia += [cls.INCONSISTENCIA_TURNO_EXCESSIVO]

                # chamado 114661
                is_numero_impar_de_registros = len(frequencias) % 2 == 1
                if is_numero_impar_de_registros:
                    inconsistencias_dia += [cls.INCONSISTENCIA_NUMERO_IMPAR_REGISTROS]

            # não há registro ponto seg-sex?
            elif not is_fim_de_semana:
                inconsistencias_dia = [cls.INCONSISTENCIA_FALTA]

            if inconsistencias_dia:
                if cls.existe_liberacao_inconsistencia(vinculo, dia, contexto_compensacao):
                    inconsistencias_dia = []

                for periodo in ch_reduzida_processos_deferidos.values():
                    processo_data_i, processo_data_t = periodo
                    if processo_data_i <= dia and dia <= processo_data_t:
                        if jornada_trabalho_hrs == 0:
                            inconsistencias_dia = []
                            break

            inconsistencias[dia] = [i for i in inconsistencias_dia if Frequencia.pode_aplicar_inconsistencia(dia, i)]

        return inconsistencias

    @classmethod
    def get_detalhamento_inconsistencias(cls, inconsistencias, data_inicio, data_fim, contexto_compensacao, tolerancia_15min=True):
        """
        dada uma lista de inconsistências (constantes do modelo Frequencia), obtém
        detalhes (textual) de cada uma das inconsistências em cada dia do período dado
        """

        from ponto.compensacao import formatar_segundos

        result = {}  # data -> "inconsistência" -> "detalhamento"

        tem_detalhamento = False

        # turno_minimo_em_segundos = 2 * 60 * 60
        # turno_maximo_em_segundos = (6 * 60 * 60) + ((15 * 60) if tolerancia_15min else 0)

        intervalo_1h_em_segundos = 1 * 60 * 60
        intervalo_3h_em_segundos = 3 * 60 * 60

        for dia in datas_entre(data_inicio, data_fim):
            if dia not in result:
                result[dia] = {}

            frequencias = contexto_compensacao.get_dia(dia).relatorio_ponto_do_dia.get('horarios', [])

            for inconsistencia in inconsistencias:
                if inconsistencia not in result[dia]:
                    result[dia][inconsistencia] = ''

                if inconsistencia in [cls.INCONSISTENCIA_INTERVALO_INFERIOR_1H, cls.INCONSISTENCIA_INTERVALO_SUPERIOR_3H]:
                    intervalos = cls.get_intervalos_entre_frequencias(frequencias)
                    for intervalo in intervalos:
                        if data_inicio == data_fim:
                            intervalo_display = f'{intervalo.data_hora_inicio.strftime("%H:%M:%S")} a {intervalo.data_hora_fim.strftime("%H:%M:%S")}'
                        else:
                            intervalo_display = f'{intervalo}'

                        if intervalo.segundos < intervalo_1h_em_segundos or intervalo.segundos > intervalo_3h_em_segundos:
                            result[dia][inconsistencia] += (
                                f'O intervalo "{intervalo_display}" foi de "{formatar_segundos(intervalo.segundos, True, True)}"'
                            )
                            tem_detalhamento = True

                # elif inconsistencia in [
                # cls.INCONSISTENCIA_TURNO_INSUFICIENTE,
                # cls.INCONSISTENCIA_TURNO_EXCESSIVO
                # ]:
                # turnos = cls.get_turnos_entre_frequencias(frequencias)
                # for turno in turnos:
                # if data_inicio == data_fim:
                #     turno_display = f'{turno.data_hora_inicio.strftime("%H:%M:%S")} a {turno.data_hora_fim.strftime("%H:%M:%S")}'
                # else:
                #     turno_display = f'{turno}'
                # if turno.segundos < turno_minimo_em_segundos:
                #     inconsistencias_dia += [cls.INCONSISTENCIA_TURNO_INSUFICIENTE]
                # if turno.segundos > turno_maximo_em_segundos:
                #     result[dia][inconsistencia] += f'O turno "{turno_display}" foi de "{formatar_segundos(turno.segundos, True, True)}"'
                #     tem_detalhamento = True

        if not tem_detalhamento:
            result = {}

        return result

    @classmethod
    def existe_liberacao_inconsistencia(cls, vinculo, dia, contexto_compensacao) -> bool:
        # férias?
        if 'ferias' in settings.INSTALLED_APPS:
            if contexto_compensacao.get_dia(dia).relatorio_ponto_do_dia.get('ferias', False):
                return True

        # afastamento SIAPE?
        if contexto_compensacao.get_dia(dia).relatorio_ponto_do_dia.get('afastamentos_siape', False):
            return True

        # afastamento RH?
        if contexto_compensacao.get_dia(dia).relatorio_ponto_do_dia.get('afastamentos_rh', False):
            return True

        # viagens?
        if contexto_compensacao.get_dia(dia).relatorio_ponto_do_dia.get('viagens_scdp', False):
            return True

        # liberações
        tem_liberacao_no_dia = contexto_compensacao.get_dia(dia).relatorio_ponto_do_dia.get('tem_liberacao_de_ponto_no_dia', False)
        tem_liberacao_parcial_no_dia = contexto_compensacao.get_dia(dia).relatorio_ponto_do_dia.get('tem_liberacao_parcial_de_ponto_no_dia', False)

        return tem_liberacao_no_dia and not tem_liberacao_parcial_no_dia

    @classmethod
    def tem_saida_antecipada(cls, vinculo, dia, contexto_compensacao):
        inconsistencia = cls.get_inconsistencias(
            vinculo,
            dia,
            dia,
            contexto_compensacao,
        ).get(dia, [])

        tem_saida_antecipada = cls.INCONSISTENCIA_MENOR_JORNADA in inconsistencia

        return tem_saida_antecipada

    @classmethod
    def relatorio_noturno(cls, cargo_emprego, uo, data_ini=None, data_fim=None, sabado=True, domingo=True):
        """
        Listagem de frequência extra noturna.
        """

        # Excluindo professores substitutos de pesquisa de docentes
        if cargo_emprego == 'professor_substituto_temporario':
            servidores = Servidor.objects.substitutos_ou_temporarios().filter(setor__uo=uo)
        elif cargo_emprego == 'docente':
            servidores = Servidor.objects.docentes_permanentes().filter(setor__uo=uo)
        elif cargo_emprego == 'tecnico_administrativo':
            servidores = Servidor.objects.tecnicos_administrativos().filter(setor__uo=uo)
        lista = []
        #       A partir da versao 1.6 do django substituir por objects.filter(horario__hour=23)

        frequencias_subquery = (
            Frequencia.objects.annotate(hora=ExtractHour('horario'))
            .filter(
                horario__range=[data_ini, data_fim + timedelta(1)],
                hora__gte=22,
                vinculo__tipo_relacionamento__model='servidor',
            )
            .values_list('vinculo__id_relacionamento', flat=True)
        )

        servidores = servidores.filter(id__in=Subquery(frequencias_subquery))
        for servidor in servidores:
            relatorio_ponto = cls.relatorio_ponto_pessoa(servidor.get_vinculo(), data_ini, data_fim, sabado, domingo, so_horario_extra_noturno=True)
            cls.relatorio_ponto_pessoa_update(relatorio_ponto)
            lista.append(relatorio_ponto)
        return lista

    @classmethod
    def relatorio_terceirizados(
        cls, terceirizado=None, setor=None, data_ini=None, data_fim=None, sabado=True, domingo=True, recursivo=True, ocupacao=None
    ):
        """
        Retorna uma lista de dicionários com as frequências de terceirizados da Instituição.

        """
        terceirizados = PrestadorServico.objects.filter(setor__isnull=False, ativo=True)
        if terceirizado:
            terceirizados = PrestadorServico.objects.filter(id=terceirizado.id, ativo=True)

        elif setor:
            if recursivo:
                terceirizados = terceirizados.filter(setor__in=setor.descendentes)
            else:
                terceirizados = terceirizados.filter(setor=setor)

        if ocupacao:
            terceirizados = terceirizados.filter(ocupacaoprestador__ocupacao=ocupacao)
        lista = []
        for terceirizado in terceirizados.distinct('pessoa_fisica__nome'):
            frequencias = cls.relatorio_frequencias_prestador(terceirizado.get_vinculo(), data_ini, data_fim, sabado, domingo)
            if frequencias:
                total_periodo = 0
                for frequencia in frequencias:
                    total_periodo += frequencia['duracao_segundos']
                dic_totalperiodo = formata_segundos(total_periodo)
                total_periodo = '{h}h {m}min {s}seg'.format(**dic_totalperiodo)
                dado = {'funcionario': terceirizado, 'frequencias': frequencias, 'total_periodo': total_periodo}
                lista.append(dado)

        return lista

    @classmethod
    def relatorio_cargo_emprego(cls, cargo_emprego, data_ini=None, data_fim=None, sabado=True, domingo=True, request=None, task=None):
        servidores = Servidor.objects.filter(cargo_emprego=cargo_emprego, ativo=True)
        lista = []
        if task:
            task.start_progress(servidores.count() * 2)
            servidores = task.iterate(servidores)
        for servidor in servidores:
            if not request or pode_ver_frequencia(servidor, request):
                relatorio_ponto = cls.relatorio_ponto_pessoa(servidor.get_vinculo(), data_ini, data_fim, False, False, True)
                cls.relatorio_ponto_pessoa_update(relatorio_ponto)
                if relatorio_ponto['dias']:  # tem relatório de ponto?
                    lista.append(relatorio_ponto)

        return lista

    @classmethod
    def relatorio_ponto_pessoa_novo(cls, vinculo, servidor_logado, data_ini=None, data_fim=None, escopo='chefe'):
        servidor = vinculo.relacionamento
        setores_funcionario = servidor.historico_setor_suap(data_ini, data_fim)
        dias_liberado_frequencia = servidor.get_dias_liberado_frequencia_periodo(data_ini, data_fim)
        dias_em_que_foi_chefe_setor = []
        dias_em_que_estava_no_campus = []
        for setor_funcionario in setores_funcionario:
            data_inicio_setor_referencia = djtools_max(setor_funcionario.data_inicio_no_setor, data_ini)
            data_fim_setor_referencia = djtools_min(setor_funcionario.data_fim_no_setor, data_fim)
            if servidor_logado.setor.uo == setor_funcionario.setor.uo:
                if not dias_em_que_estava_no_campus:
                    dias_em_que_estava_no_campus = datas_entre(data_inicio_setor_referencia, data_fim_setor_referencia)
                else:
                    dias_em_que_estava_no_campus += datas_entre(data_inicio_setor_referencia, data_fim_setor_referencia)
            for funcao_servidor in servidor_logado.historico_funcao(data_ini, data_fim).filter(
                setor_suap__isnull=False, funcao__codigo__in=Funcao.get_codigos_funcao_chefia()
            ):
                if setor_funcionario.setor in funcao_servidor.setor_suap.descendentes:
                    funcao_servidor.data_inicio_funcao = djtools_max(funcao_servidor.data_inicio_funcao, data_inicio_setor_referencia)
                    funcao_servidor.data_fim_funcao = djtools_max(funcao_servidor.data_fim_funcao, data_fim_setor_referencia)
                    dias_em_que_foi_chefe_setor += datas_entre(funcao_servidor.data_inicio_funcao, funcao_servidor.data_fim_funcao)
        kwargs = {}
        if escopo == 'chefe':
            kwargs['so_frequencias_em_que_era_chefe'] = True
        elif escopo == 'campus':
            kwargs['dias_em_que_estava_no_campus'] = dias_em_que_estava_no_campus

        relatorio_ponto = cls.relatorio_ponto_pessoa(
            vinculo,
            data_ini,
            data_fim,
            trata_compensacoes=True,
            dias_em_que_foi_chefe_setor=dias_em_que_foi_chefe_setor,
            dias_liberado_frequencia=dias_liberado_frequencia,
            **kwargs,
        )
        cls.relatorio_ponto_pessoa_update(relatorio_ponto)
        return relatorio_ponto

    @classmethod
    def relatorio_ponto_pessoa(
        cls,
        vinculo,
        data_ini=None,
        data_fim=None,
        sabado=True,
        domingo=True,
        so_inconsistentes=False,
        dias_em_que_foi_chefe_setor=None,
        so_horario_extra_noturno=False,
        show_grafico=True,
        so_frequencias_em_que_era_chefe=False,
        dias_em_que_estava_no_campus=None,
        trata_compensacoes=False,
        dias_liberado_frequencia=None,
        trata_inconsistencias=True,
        so_inconsistentes_apenas_esta_inconsistencia=None,
        so_inconsistentes_situacao_abono=SITUACAO_INCONSISTENCIA_COM_OU_SEM_ABONO,
        so_inconsistentes_situacao_debito=SITUACAO_INCONSISTENCIA_COM_DEBITO_COMPENSADO_OU_PENDENTE,
        visualizar_futuro=False,
        calcular_se_estah_no_pgd=True,
    ):
        if dias_liberado_frequencia is None:
            dias_liberado_frequencia = []
        if dias_em_que_estava_no_campus is None:
            dias_em_que_estava_no_campus = []
        if dias_em_que_foi_chefe_setor is None:
            dias_em_que_foi_chefe_setor = []

        relatorio_pessoa = OrderedDict()

        if vinculo.eh_aluno():
            raise ValidationError('Dados não disponíveis para vínculo de aluno.')

        data_ini = data_ini or date.today()
        data_fim = data_fim or date.today()

        funcionario = vinculo.relacionamento
        relatorio_pessoa['funcionario'] = funcionario

        data_fim_instituicao = None
        data_inicio_instituicao = None
        if vinculo.eh_servidor():
            data_inicio_instituicao = funcionario.data_inicio_exercicio_na_instituicao
            data_fim_instituicao = funcionario.data_fim_servico_na_instituicao

        dias_dict = OrderedDict[date, RelatorioPontoPessoaDiaInfo]()  # {dia: RelatorioPontoPessoaDiaInfo, dia: RelatorioPontoPessoaDiaInfo, ...}
        semanas_dict = OrderedDict()

        dias_periodo = datas_entre(data_ini, data_fim)

        for dia in dias_periodo:
            dias_dict[dia] = RelatorioPontoPessoaDiaInfo(dia=dia)

        # Se estah no PGD neste dia
        if calcular_se_estah_no_pgd:
            if vinculo.eh_servidor():
                periodos_em_pgd = periodos_estah_no_pgd1_pgd2(funcionario)
                for dia in dias_periodo:
                    for periodo in periodos_em_pgd:
                        periodo_data_inicio, periodo_data_fim = periodo
                        if periodo_data_inicio <= dia and dia <= periodo_data_fim:
                            dias_dict[dia].estah_no_pgd = 'Servidor no PGD'

        if data_fim_instituicao and data_fim_instituicao < data_fim:
            for dia in datas_entre(data_fim_instituicao, data_fim):
                if dias_dict.get(dia):
                    dias_dict[dia].excluido = f'Excluído desde o dia {data_fim_instituicao.strftime("%d/%m/%Y")}'

        if data_inicio_instituicao and data_inicio_instituicao > data_ini:
            for dia in datas_entre(data_ini, data_inicio_instituicao):
                if dias_dict.get(dia):
                    dias_dict[dia].excluido = f'Início do vinculo a partir do dia {data_inicio_instituicao.strftime("%d/%m/%Y")}'

        if vinculo.eh_servidor():
            afastamentos_siape = ServidorAfastamento.get_afastamentos(funcionario, data_ini, data_fim).exclude_afastamentos_pgd()
            afastamentos_siape = afastamentos_siape.select_related('afastamento')
            afastamentos_siape = afastamentos_siape.only('afastamento', 'data_inicio', 'data_termino')
            afastamentos_desconto_jornada = {}

            for afastamento_siape in afastamentos_siape:
                for dia in datas_entre(afastamento_siape.data_inicio, afastamento_siape.data_termino):
                    if dia in dias_periodo:
                        if (afastamento_siape.qtd_minuto_afastamento not in ['0000', None, '']) and not afastamentos_desconto_jornada.get(dia):
                            afastamentos_desconto_jornada[dia] = afastamento_siape
                            dias_dict[dia].afastamento_parcial = afastamento_siape
                        else:
                            dias_dict[dia].liberado = True
                            if not dias_dict[dia].afastamentos_siape:
                                dias_dict[dia].afastamentos_siape = [afastamento_siape.afastamento]
                            else:
                                dias_dict[dia].afastamentos_siape.append(afastamento_siape.afastamento)

            afastamentos_rh = Afastamento.buscar_afastamento_periodo(vinculo, data_ini, data_fim).select_related('tipo')

            for afastamento in afastamentos_rh:
                for dia in datas_entre(afastamento.data_ini, afastamento.data_fim):
                    if dia in dias_periodo:
                        dias_dict[dia].liberado = True
                        if not dias_dict[dia].afastamentos_rh:
                            dias_dict[dia].afastamentos_rh = [afastamento]
                        else:
                            dias_dict[dia].afastamentos_rh.append(afastamento)

            # Calculando as Viagens do SCDP
            # Verificar quais as situações que tem que ser filtradas aqui.
            for viagem_servidor in Viagem.get_viagens(vinculo.relacionamento, data_ini, data_fim).only(
                'data_inicio_viagem', 'data_fim_viagem', 'servidor', 'objetivo_viagem', 'situacao'
            ):
                for dia in datas_entre(viagem_servidor.data_inicio_viagem, viagem_servidor.data_fim_viagem):
                    if dia in dias_periodo:
                        dias_dict[dia].liberado = True
                        if not dias_dict[dia].viagens_scdp:
                            dias_dict[dia].viagens_scdp = [viagem_servidor]
                        else:
                            dias_dict[dia].viagens_scdp.append(viagem_servidor)

            if 'ferias' in settings.INSTALLED_APPS:
                from ferias.models import Ferias

                ferias_dados = Ferias.get_ferias_no_periodo(vinculo.relacionamento, data_ini, data_fim)
                ferias_dados = ferias_dados.only('pk')

                for ferias in ferias_dados:
                    for dia_ferias in list(ferias.get_dias_ferias().keys()):
                        if dia_ferias in dias_periodo:
                            dias_dict[dia_ferias].liberado = True
                            if not dias_dict[dia_ferias].ferias:
                                dias_dict[dia_ferias].ferias = 'Férias'

            for liberacao in Liberacao.filtrar_por_periodo(vinculo, data_ini, data_fim).only('tipo', 'data_inicio', 'data_fim', 'descricao'):
                if liberacao.tipo == TipoLiberacao.get_numero(TipoLiberacao.FERIADO_RECORRENTE):
                    for ano in range(data_ini.year, data_fim.year + 1):
                        liberacao.data_inicio = date(ano, liberacao.data_inicio.month, liberacao.data_inicio.day)
                        liberacao.data_fim = date(ano, liberacao.data_fim.month, liberacao.data_fim.day)
                        for dia in datas_entre(liberacao.data_inicio, liberacao.data_fim):
                            if dia in dias_periodo:
                                dias_dict[dia].liberado = True
                                if not dias_dict[dia].liberacoes:
                                    dias_dict[dia].liberacoes = [liberacao]
                                else:
                                    dias_dict[dia].liberacoes.append(liberacao)
                else:
                    if not liberacao.data_fim:
                        liberacao.data_fim = liberacao.data_inicio
                    for dia in datas_entre(liberacao.data_inicio, liberacao.data_fim):
                        if dia in dias_periodo:
                            dias_dict[dia].liberado = True
                            if not dias_dict[dia].liberacoes:
                                dias_dict[dia].liberacoes = [liberacao]
                            else:
                                dias_dict[dia].liberacoes.append(liberacao)

            for abono in AbonoChefia.objects.select_related('solicitacao_abono_parcial').filter(
                vinculo_pessoa=vinculo, data__lte=data_fim, data__gte=data_ini
            ):
                if dias_dict[abono.data].abonos_chefia:
                    dias_dict[abono.data].abonos_chefia.append(abono)
                else:
                    dias_dict[abono.data].abonos_chefia = [abono]

        for observacao in Observacao.objects.filter(vinculo=vinculo, data__lte=data_fim, data__gte=data_ini):
            if dias_dict[observacao.data].observacoes:
                dias_dict[observacao.data].observacoes.append(observacao)
            else:
                dias_dict[observacao.data].observacoes = [observacao]

        for anexo in DocumentoAnexo.objects.filter(vinculo=vinculo, data__lte=data_fim, data__gte=data_ini):
            if dias_dict[anexo.data].anexos:
                dias_dict[anexo.data].anexos.append(anexo)
            else:
                dias_dict[anexo.data].anexos = [anexo]

        for abono_parcial in SolicitacaoAbonoParcial.objects.filter(
            vinculo_pessoa=vinculo, data_aplicacao__gte=data_ini, data_aplicacao__lte=data_fim
        ):
            if dias_dict[abono_parcial.data_aplicacao].abonos_parciais:
                dias_dict[abono_parcial.data_aplicacao].abonos_parciais.append(abono_parcial)
            else:
                dias_dict[abono_parcial.data_aplicacao].abonos_parciais = [abono_parcial]

        for revisao_abono_chefia in AbonoChefia.get_solicitacoes_revisao_abono_chefia(vinculo_solicitante=vinculo).filter(
            abono_chefia_data__gte=data_ini, abono_chefia_data__lte=data_fim
        ):
            if dias_dict[revisao_abono_chefia.abono_chefia_data].revisoes_abonos_chefia:
                dias_dict[revisao_abono_chefia.abono_chefia_data].revisoes_abonos_chefia.append(revisao_abono_chefia)
            else:
                dias_dict[revisao_abono_chefia.abono_chefia_data].revisoes_abonos_chefia = [revisao_abono_chefia]

        for historico_funcao in funcionario.historico_funcao().filter(funcao__codigo__in=Funcao.get_codigos_funcao_chefia()):
            data_fim_referencia = historico_funcao.data_fim_funcao or data_fim
            for dia in datas_entre(historico_funcao.data_inicio_funcao, data_fim_referencia):
                if dia in dias_periodo:
                    dias_dict[dia].tem_funcao_chefia = True

        for frequencia in Frequencia.get_frequencias_por_periodo(vinculo, data_ini, data_fim).select_related('maquina'):
            if dias_dict[frequencia.horario.date()].horarios:
                dias_dict[frequencia.horario.date()].horarios.append(frequencia)
            else:
                dias_dict[frequencia.horario.date()].horarios = [frequencia]

            if dias_dict[frequencia.horario.date()].horarios_dia:
                dias_dict[frequencia.horario.date()].horarios_dia.append(frequencia.horario)
            else:
                dias_dict[frequencia.horario.date()].horarios_dia = [frequencia.horario]

        for dia_foi_chefe in dias_em_que_foi_chefe_setor:
            if dias_dict.get(dia_foi_chefe):
                dias_dict[dia_foi_chefe].pode_abonar_dia = True

        for dia_liberado_frequencia in dias_liberado_frequencia:
            if dias_dict.get(dia_liberado_frequencia):
                dias_dict[dia_liberado_frequencia].dia_liberado_frequencia = True

        # é liberado do controle de frequência HOJE ?
        # esta informação será anexada ao relatório de ponto para que
        # não seja recalculada durante as chamadas nos templates que consomem
        # este relatório, diminuindo o número queries
        eh_liberado_controle_frequencia = funcionario.eh_liberado_controle_frequencia()

        tempo_abonado = 0
        tempo_trabalho_remoto = 0
        tempo_abonado_para_compensacao = 0
        tempo_nao_abonado = 0
        hora_extra_nao_justificada = 0
        hora_extra_justificada = 0
        hora_extra_para_compensacao_carga_horaria = 0
        trabalho_fds_permitido_como_hora_extra = 0
        trabalho_fds_permitido_para_compensacao_carga_horaria = 0
        trabalho_fds_nao_permitido = 0
        tempo_total_horas_trabalhadas = 0
        tempo_total_carga_horaria = 0
        tempo_total_hora_extra_noturna = 0

        if vinculo.eh_servidor():
            # jornadas de trabalho do servidor
            # são instâncias de rh.JornadaTrabalho + rh.JornadaTrabalhoPersonalizada
            jornadas_servidor, motivos_jornadas, origens_jornadas = funcionario.get_jornadas_periodo_dict(data_ini, data_fim)

        tem_horarios_inferiores = 0
        tem_horarios_excedentes = 0

        semana_count = 1
        semanas_dict[semana_count] = OrderedDict()
        semanas_dict[semana_count]['ch_exigida'] = 0
        semanas_dict[semana_count]['ch_valida'] = 0
        semanas_dict[semana_count]['ch_segundos'] = 0

        for dia in datas_entre(data_ini, data_fim):
            if dia != data_ini and dia.weekday() == 0:
                semana_count += 1
                semanas_dict[semana_count] = OrderedDict()
                semanas_dict[semana_count]['ch_exigida'] = 0
                semanas_dict[semana_count]['ch_valida'] = 0
                semanas_dict[semana_count]['ch_segundos'] = 0

            dias_dict[dia].semana = semana_count

            frequencias_dia = []
            if dias_dict[dia].horarios:
                frequencias_dia = dias_dict[dia].horarios

            # Esse horarios_frequencias substitui o values_list da queryset
            horarios_frequencias_dia = dias_dict[dia].horarios_dia
            hora_extra_noturna = 0
            tempo = 0
            if frequencias_dia and horarios_frequencias_dia:
                for par in agrupar_em_pares(horarios_frequencias_dia):
                    if len(par) == 2:
                        if possui_horario_extra_noturno(par):
                            hora_extra_noturna = cls.get_horario_extra_noturno(par)
                tempo = cls.get_tempo_entre_frequencias(horarios_frequencias_dia)

            # máximo 10 horas por dia (36000 segundos)
            tempo_bruto = tempo
            if tempo > 36000:
                tempo = 36000

            ###
            # determina se o dia será ou não exibido
            mostrar_dia = True

            if so_frequencias_em_que_era_chefe or dias_em_que_estava_no_campus:
                if dia not in dias_em_que_foi_chefe_setor and dia not in dias_em_que_estava_no_campus:
                    mostrar_dia = False

            tem_acoes_ponto = any(
                [
                    frequencias_dia,
                    dias_dict[dia].observacoes,
                    dias_dict[dia].abonos_chefia,
                    dias_dict[dia].anexos,
                    dias_dict[dia].abonos_parciais,
                    dias_dict[dia].revisoes_abonos_chefia,
                ]
            )
            if not tem_acoes_ponto and (dia.weekday() >= 5 or dias_dict[dia].excluido):
                mostrar_dia = False

            if mostrar_dia and so_inconsistentes:
                if dias_dict.get(dia):
                    dias_dict[dia].tem_inconsistencia_calculo_adiado = True

            if mostrar_dia and so_horario_extra_noturno:
                if dias_dict.get(dia):
                    if not hora_extra_noturna:
                        mostrar_dia = False

            if mostrar_dia:
                semanas_dict[semana_count]['min_dia'] = (
                    min(dia, semanas_dict[semana_count]['min_dia']) if semanas_dict[semana_count].get('min_dia') else dia
                )
                semanas_dict[semana_count]['max_dia'] = (
                    max(dia, semanas_dict[semana_count]['max_dia']) if semanas_dict[semana_count].get('max_dia') else dia
                )
            else:
                dias_dict.pop(dia)
                continue  # processa o próximo dia

            ################################################################################################
            # obtém a carga horária do servidor no dia em questão
            # Para docentes é usada a regra da carga-horária / 2
            ################################################################################################

            motivo_carga_horaria_do_dia = ''
            origem_carga_horaria_do_dia = ''

            if vinculo.eh_servidor():
                try:
                    jornada_trabalho_servidor_diaria = jornadas_servidor[dia].get_jornada_trabalho_diaria()

                    # verificando se no dia existe afastamento que diminui a carga horária
                    if afastamentos_desconto_jornada.get(dia):
                        afast = afastamentos_desconto_jornada.get(dia)
                        _hora_ch_convertida = int(afast.qtd_minuto_afastamento) / 60
                        if jornada_trabalho_servidor_diaria <= _hora_ch_convertida:
                            jornada_trabalho_servidor_diaria = 0
                        else:
                            jornada_trabalho_servidor_diaria = jornada_trabalho_servidor_diaria - _hora_ch_convertida

                    motivo_carga_horaria_do_dia = motivos_jornadas[dia]

                    """
                        Trata a carga horária dos docentes.

                        Considerar a metade da carga horária diária conforme solicitação da demanda #487:

                            "... deverá ser cobrada do docente DE ou 40 um total de 20 horas relógio,
                            enquanto que para o docente 20 Horas deverá ser cobrado um total de 10 horas relógio,
                            de forma semanal."

                        Obs: a semana (completa) considerada no texto acima tem 5 dias úteis (seg a sex)
                    """
                    origem_carga_horaria_do_dia = origens_jornadas[dia]

                    if funcionario.eh_docente and origem_carga_horaria_do_dia and origem_carga_horaria_do_dia == 'Jornada do Servidor':
                        jornada_trabalho_servidor_diaria = jornada_trabalho_servidor_diaria / 2

                    dias_dict[dia].jornada_trabalho = jornadas_servidor[dia]
                except Exception:
                    jornada_trabalho_servidor_diaria = 0
                    dias_dict[dia].jornada_trabalho = None
            else:
                jornada_trabalho_servidor_diaria = 0
                dias_dict[dia].jornada_trabalho = None

            carga_horaria_do_dia_segundos = jornada_trabalho_servidor_diaria * 60 * 60
            carga_horaria_partes = formata_segundos(carga_horaria_do_dia_segundos)

            dias_dict[dia].carga_horaria_do_dia = jornada_trabalho_servidor_diaria
            dias_dict[dia].carga_horaria_do_dia_segundos = carga_horaria_do_dia_segundos
            dias_dict[dia].carga_horaria_do_dia_h = carga_horaria_partes['h']
            dias_dict[dia].carga_horaria_do_dia_m = carga_horaria_partes['m']
            dias_dict[dia].carga_horaria_do_dia_s = carga_horaria_partes['s']

            dias_dict[dia].motivo_carga_horaria_do_dia = motivo_carga_horaria_do_dia
            dias_dict[dia].origem_carga_horaria_do_dia = origem_carga_horaria_do_dia

            ################################################################################################

            duracao = time.strftime('%H:%M:%S', time.gmtime(tempo))
            duracao_bruto = time.strftime('%H:%M:%S', time.gmtime(tempo_bruto))
            duracao_segundos = tempo
            duracao_segundos_bruto = tempo_bruto

            dias_dict[dia].duracao = duracao
            dias_dict[dia].duracao_bruto = duracao_bruto
            dias_dict[dia].duracao_segundos = duracao_segundos
            dias_dict[dia].duracao_segundos_bruto = duracao_segundos_bruto

            dias_dict[dia].acao_abono_inconsistencia = None

            tem_inconsistencia_inferior = False
            tem_inconsistencia_superior = False

            if trata_inconsistencias:
                if dias_dict.get(dia):
                    dias_dict[dia].trata_inconsistencias_calculo_adiado = True

            dias_dict[dia].hora_extra_noturna = hora_extra_noturna

            if dias_dict[dia].abonos_chefia and not any(
                [
                    dias_dict[dia].liberacoes,
                    dias_dict[dia].afastamentos_rh,
                    dias_dict[dia].afastamentos_siape,
                    dias_dict[dia].ferias,
                    dias_dict[dia].viagens_scdp,
                    dias_dict[dia].dia_liberado_frequencia,
                ]
            ):
                abonos = dias_dict[dia].abonos_chefia

                if abonos:
                    tem_inconsistencia_superior = False
                    tem_inconsistencia_inferior = False

                abonos_tempo_abonado_sem_compensacao = 0
                abonos_tempo_trabalho_remoto = 0
                abonos_tempo_abonado_para_compensacao = 0
                abonos_tempo_nao_abonado = 0
                abonos_hora_extra_nao_justificada = 0
                abonos_hora_extra_justificada = 0
                abonos_hora_extra_para_compensacao_carga_horaria = 0
                abonos_trabalho_fds_permitido_para_compensacao_carga_horaria = 0
                abonos_trabalho_fds_permitido_como_hora_extra = 0
                abonos_trabalho_fds_nao_permitido = 0

                abonos_tipos = []

                duracao_diferenca_a_menor_segundos = carga_horaria_do_dia_segundos - duracao_segundos
                duracao_diferenca_a_maior_segundos = duracao_segundos - carga_horaria_do_dia_segundos
                duracao_computada_segundos = 0

                for abono in abonos:
                    abono_parcial = abono.solicitacao_abono_parcial

                    if abono.acao_abono == AbonoChefia.ABONADO:
                        if abono_parcial:
                            abonos_tempo_abonado_sem_compensacao += abono_parcial.ch_solicitada
                        else:
                            abonos_tempo_abonado_sem_compensacao += duracao_diferenca_a_menor_segundos
                        duracao_computada_segundos = max(duracao_segundos, duracao_computada_segundos)
                        abonos_tipos.append(AbonoChefia.ABONADO)

                    elif abono.acao_abono == AbonoChefia.TRABALHO_REMOTO:
                        abonos_tempo_trabalho_remoto += duracao_diferenca_a_menor_segundos
                        duracao_computada_segundos = max(carga_horaria_do_dia_segundos, duracao_computada_segundos)
                        abonos_tipos.append(AbonoChefia.TRABALHO_REMOTO)

                    elif abono.acao_abono == AbonoChefia.ABONADO_COM_COMPENSACAO:
                        if abono_parcial:
                            abonos_tempo_abonado_para_compensacao += abono_parcial.ch_solicitada
                        else:
                            abonos_tempo_abonado_para_compensacao += duracao_diferenca_a_menor_segundos
                        duracao_computada_segundos = max(duracao_segundos, duracao_computada_segundos)
                        abonos_tipos.append(AbonoChefia.ABONADO_COM_COMPENSACAO)

                    elif abono.acao_abono == AbonoChefia.NAO_ABONADO:
                        if abono_parcial:
                            abonos_tempo_nao_abonado += abono_parcial.ch_solicitada
                        else:
                            abonos_tempo_nao_abonado += duracao_diferenca_a_menor_segundos
                        duracao_computada_segundos = max(duracao_segundos, duracao_computada_segundos)
                        abonos_tipos.append(AbonoChefia.NAO_ABONADO)

                    elif abono.acao_abono == AbonoChefia.HORA_EXTRA_NAO_JUSTIFICADA:
                        abonos_hora_extra_nao_justificada += duracao_diferenca_a_maior_segundos
                        duracao_computada_segundos = max(carga_horaria_do_dia_segundos, duracao_computada_segundos)
                        abonos_tipos.append(AbonoChefia.HORA_EXTRA_NAO_JUSTIFICADA)

                    elif abono.acao_abono == AbonoChefia.HORA_EXTRA_JUSTIFICADA:
                        abonos_hora_extra_justificada += duracao_diferenca_a_maior_segundos
                        duracao_computada_segundos = max(duracao_segundos, duracao_computada_segundos)
                        abonos_tipos.append(AbonoChefia.HORA_EXTRA_JUSTIFICADA)

                    elif abono.acao_abono == AbonoChefia.HORA_EXTRA_PARA_COMPENSACAO_CARGA_HORARIA:
                        abonos_hora_extra_para_compensacao_carga_horaria += duracao_diferenca_a_maior_segundos
                        duracao_computada_segundos = max(duracao_segundos, duracao_computada_segundos)
                        abonos_tipos.append(AbonoChefia.HORA_EXTRA_PARA_COMPENSACAO_CARGA_HORARIA)

                    elif abono.acao_abono == AbonoChefia.TRABALHO_FDS_PERMITIDO_PARA_COMPENSACAO_CARGA_HORARIA:
                        abonos_trabalho_fds_permitido_para_compensacao_carga_horaria += duracao_segundos
                        duracao_computada_segundos = max(duracao_segundos, duracao_computada_segundos)
                        abonos_tipos.append(AbonoChefia.TRABALHO_FDS_PERMITIDO_PARA_COMPENSACAO_CARGA_HORARIA)

                    elif abono.acao_abono == AbonoChefia.TRABALHO_FDS_PERMITIDO_COMO_HORA_EXTRA:
                        abonos_trabalho_fds_permitido_como_hora_extra += duracao_segundos
                        duracao_computada_segundos = max(duracao_segundos, duracao_computada_segundos)
                        abonos_tipos.append(AbonoChefia.TRABALHO_FDS_PERMITIDO_COMO_HORA_EXTRA)

                    elif abono.acao_abono == AbonoChefia.TRABALHO_FDS_NAO_PERMITIDO:
                        abonos_trabalho_fds_nao_permitido += duracao_segundos
                        duracao_computada_segundos = max(0, duracao_computada_segundos)
                        abonos_tipos.append(AbonoChefia.TRABALHO_FDS_NAO_PERMITIDO)

                    duracao_computada_segundos -= abono.ch_descontada or 0

                if duracao_computada_segundos < 0:
                    duracao_computada_segundos = 0

                if duracao_computada_segundos != duracao_segundos:
                    dias_dict[dia].duracao_computada = time.strftime('%H:%M:%S', time.gmtime(duracao_computada_segundos))

                # Como um dia pode ter mais de um abono,
                # então os totais relacionados aos abonos do dia
                # não podem ultrapassar os limites do próprio dia.
                #
                # dia CH 6h                 |--------------------------|
                # duração válida CH 1h      |--|
                # abono sem cmp integral 6h |--------------------------|
                # abono sem cmp parcial  4h |-----------------|
                # total abono sem cmp 6h + 4h = 10h (um total inconsistente com os limites do dia)

                if AbonoChefia.ABONADO in abonos_tipos:
                    dias_dict[dia].tempo_abonado = min(duracao_diferenca_a_menor_segundos, abonos_tempo_abonado_sem_compensacao)

                if AbonoChefia.TRABALHO_REMOTO in abonos_tipos:
                    dias_dict[dia].tempo_trabalho_remoto = min(duracao_diferenca_a_menor_segundos, abonos_tempo_trabalho_remoto)

                if AbonoChefia.ABONADO_COM_COMPENSACAO in abonos_tipos:
                    dias_dict[dia].tempo_abonado_para_compensacao = min(duracao_diferenca_a_menor_segundos, abonos_tempo_abonado_para_compensacao)

                if AbonoChefia.NAO_ABONADO in abonos_tipos:
                    dias_dict[dia].tempo_nao_abonado = min(duracao_diferenca_a_menor_segundos, abonos_tempo_nao_abonado)

                if AbonoChefia.HORA_EXTRA_NAO_JUSTIFICADA in abonos_tipos:
                    dias_dict[dia].hora_extra_nao_justificada = min(duracao_diferenca_a_maior_segundos, abonos_hora_extra_nao_justificada)

                if AbonoChefia.HORA_EXTRA_JUSTIFICADA in abonos_tipos:
                    dias_dict[dia].hora_extra_justificada = min(duracao_diferenca_a_maior_segundos, abonos_hora_extra_justificada)

                if AbonoChefia.HORA_EXTRA_PARA_COMPENSACAO_CARGA_HORARIA in abonos_tipos:
                    dias_dict[dia].hora_extra_para_compensacao_carga_horaria = min(
                        duracao_diferenca_a_maior_segundos, abonos_hora_extra_para_compensacao_carga_horaria
                    )

                if AbonoChefia.TRABALHO_FDS_PERMITIDO_PARA_COMPENSACAO_CARGA_HORARIA in abonos_tipos:
                    dias_dict[dia].trabalho_fds_permitido_para_compensacao_carga_horaria = min(
                        duracao_segundos, abonos_trabalho_fds_permitido_para_compensacao_carga_horaria
                    )

                if AbonoChefia.TRABALHO_FDS_PERMITIDO_COMO_HORA_EXTRA in abonos_tipos:
                    dias_dict[dia].trabalho_fds_permitido_como_hora_extra = min(duracao_segundos, abonos_trabalho_fds_permitido_como_hora_extra)

                if AbonoChefia.TRABALHO_FDS_NAO_PERMITIDO in abonos_tipos:
                    dias_dict[dia].trabalho_fds_nao_permitido = min(duracao_segundos, abonos_trabalho_fds_nao_permitido)

                tempo_abonado += dias_dict[dia].tempo_abonado
                tempo_trabalho_remoto += dias_dict[dia].tempo_trabalho_remoto
                tempo_abonado_para_compensacao += dias_dict[dia].tempo_abonado_para_compensacao
                tempo_nao_abonado += dias_dict[dia].tempo_nao_abonado
                hora_extra_nao_justificada += dias_dict[dia].hora_extra_nao_justificada
                hora_extra_justificada += dias_dict[dia].hora_extra_justificada
                hora_extra_para_compensacao_carga_horaria += dias_dict[dia].hora_extra_para_compensacao_carga_horaria
                trabalho_fds_permitido_para_compensacao_carga_horaria += dias_dict[dia].trabalho_fds_permitido_para_compensacao_carga_horaria
                trabalho_fds_permitido_como_hora_extra += dias_dict[dia].trabalho_fds_permitido_como_hora_extra
                trabalho_fds_nao_permitido += dias_dict[dia].trabalho_fds_nao_permitido

            dias_dict[dia].tem_inconsistencia_inferior = tem_inconsistencia_inferior
            dias_dict[dia].tem_inconsistencia_superior = tem_inconsistencia_superior
            if tem_inconsistencia_inferior:
                tem_horarios_inferiores += 1
            if tem_inconsistencia_superior:
                tem_horarios_excedentes += 1

            if not dias_dict[dia].dia_liberado_frequencia:
                tempo_total_hora_extra_noturna += hora_extra_noturna
                dias_dict[dia].tempo_total_hora_extra_noturna = hora_extra_noturna
                tempo_total_horas_trabalhadas += tempo
                dias_dict[dia].tempo_total_horas_trabalhadas = tempo

            tem_liberacao_de_ponto_no_dia = False
            if dias_dict[dia].liberacoes:
                for liberacao in dias_dict[dia].liberacoes:
                    if liberacao.tipo != TipoLiberacao.get_numero(TipoLiberacao.EVENTO):
                        tem_liberacao_de_ponto_no_dia = True
            dias_dict[dia].tem_liberacao_de_ponto_no_dia = tem_liberacao_de_ponto_no_dia

            tem_liberacao_parcial_de_ponto_no_dia = False
            dias_dict[dia].liberacoes_parciais_ch_horaria_maxima_exigida = 0  # em horas
            dias_dict[dia].liberacoes_exceto_parciais = []
            for liberacao in dias_dict[dia].liberacoes:
                if liberacao.tipo == TipoLiberacao.get_numero(TipoLiberacao.LIBERACAO_PARCIAL):
                    tem_liberacao_parcial_de_ponto_no_dia = True
                    dias_dict[dia].liberado = False
                    dias_dict[dia].liberacoes_parciais_ch_horaria_maxima_exigida = liberacao.ch_maxima_exigida  # em horas
                else:
                    dias_dict[dia].liberacoes_exceto_parciais.append(liberacao)
            dias_dict[dia].tem_liberacao_parcial_de_ponto_no_dia = tem_liberacao_parcial_de_ponto_no_dia
            dias_dict[dia].liberacoes_parciais_ch_horaria_maxima_exigida_segundos = (
                dias_dict[dia].liberacoes_parciais_ch_horaria_maxima_exigida * 60 * 60
            )

            semanas_dict[semana_count]['ch_valida'] += (
                duracao_segundos
                - dias_dict[dia].tempo_nao_abonado
                - dias_dict[dia].hora_extra_nao_justificada
                - dias_dict[dia].trabalho_fds_nao_permitido
            )
            semanas_dict[semana_count]['ch_segundos'] += duracao_segundos_bruto

            dia_referencia = data_fim if visualizar_futuro else date.today()

            if dia.weekday() < 5 and dia <= dia_referencia:
                if not (
                    tem_liberacao_de_ponto_no_dia
                    or dias_dict[dia].ferias
                    or dias_dict[dia].afastamentos_siape
                    or dias_dict[dia].afastamentos_rh
                    or dias_dict[dia].viagens_scdp
                    or dias_dict[dia].dia_liberado_frequencia
                ):
                    tempo_total_carga_horaria += carga_horaria_do_dia_segundos
                    dias_dict[dia].tempo_total_carga_horaria = carga_horaria_do_dia_segundos
                    semanas_dict[semana_count]['ch_exigida'] += carga_horaria_do_dia_segundos

                elif tem_liberacao_parcial_de_ponto_no_dia and not (
                    dias_dict[dia].ferias
                    or dias_dict[dia].afastamentos_siape
                    or dias_dict[dia].afastamentos_rh
                    or dias_dict[dia].viagens_scdp
                    or dias_dict[dia].dia_liberado_frequencia
                ):
                    jornada_do_dia = carga_horaria_do_dia_segundos
                    liberacoes_parciais_ch_horaria_maxima_exigida = dias_dict[dia].liberacoes_parciais_ch_horaria_maxima_exigida_segundos
                    if jornada_do_dia > liberacoes_parciais_ch_horaria_maxima_exigida:
                        tempo_total_carga_horaria += liberacoes_parciais_ch_horaria_maxima_exigida
                        dias_dict[dia].tempo_total_carga_horaria = liberacoes_parciais_ch_horaria_maxima_exigida
                        semanas_dict[semana_count]['ch_exigida'] += liberacoes_parciais_ch_horaria_maxima_exigida
                    else:
                        tempo_total_carga_horaria += jornada_do_dia
                        dias_dict[dia].tempo_total_carga_horaria = jornada_do_dia
                        semanas_dict[semana_count]['ch_exigida'] += jornada_do_dia

        def relatorio_pessoa_finalizar():
            relatorio_pessoa['eh_liberado_controle_frequencia'] = eh_liberado_controle_frequencia

            dias_dict_final = OrderedDict()
            for dia, dia_info in dias_dict.items():
                dias_dict_final[dia] = dia_info.as_dict()

            relatorio_pessoa['dias'] = list(dias_dict_final.values())
            relatorio_pessoa['semanas'] = semanas_dict

            relatorio_pessoa['total_periodo'] = '{h}h {m}min {s}seg'.format(**formata_segundos(tempo_total_horas_trabalhadas))
            relatorio_pessoa['total_periodo_carga_horaria'] = '{h}h {m}min {s}seg'.format(**formata_segundos(tempo_total_carga_horaria))
            relatorio_pessoa['total_periodo_carga_horaria__em_segundos'] = tempo_total_carga_horaria

            if tempo_total_hora_extra_noturna:
                relatorio_pessoa['total_hora_extra_noturna'] = '{h}h {m}min {s}seg'.format(**formata_segundos(tempo_total_hora_extra_noturna))

            if tempo_abonado or tempo_abonado_para_compensacao or tempo_nao_abonado or tempo_trabalho_remoto:
                relatorio_pessoa['total_abonado_sem_compensacao'] = '{h}h {m}min {s}seg'.format(**formata_segundos(tempo_abonado))
                relatorio_pessoa['total_trabalho_remoto'] = '{h}h {m}min {s}seg'.format(**formata_segundos(tempo_trabalho_remoto))
                relatorio_pessoa['total_abonado_para_compensacao'] = '{h}h {m}min {s}seg'.format(**formata_segundos(tempo_abonado_para_compensacao))
                relatorio_pessoa['total_nao_abonado'] = '{h}h {m}min {s}seg'.format(**formata_segundos(tempo_nao_abonado))

            if hora_extra_nao_justificada or hora_extra_justificada or hora_extra_para_compensacao_carga_horaria:
                relatorio_pessoa['total_hora_extra_nao_justificada'] = '{h}h {m}min {s}seg'.format(**formata_segundos(hora_extra_nao_justificada))
                relatorio_pessoa['total_hora_extra_justificada'] = '{h}h {m}min {s}seg'.format(**formata_segundos(hora_extra_justificada))
                relatorio_pessoa['total_hora_extra_para_compensacao_carga_horaria'] = '{h}h {m}min {s}seg'.format(
                    **formata_segundos(hora_extra_para_compensacao_carga_horaria)
                )

            if trabalho_fds_permitido_para_compensacao_carga_horaria or trabalho_fds_permitido_como_hora_extra or trabalho_fds_nao_permitido:
                relatorio_pessoa['total_trabalho_fds_permitido_para_compensacao_carga_horaria'] = '{h}h {m}min {s}seg'.format(
                    **formata_segundos(trabalho_fds_permitido_para_compensacao_carga_horaria)
                )
                relatorio_pessoa['total_trabalho_fds_permitido_como_hora_extra'] = '{h}h {m}min {s}seg'.format(
                    **formata_segundos(trabalho_fds_permitido_como_hora_extra)
                )
                relatorio_pessoa['total_trabalho_fds_nao_permitido'] = '{h}h {m}min {s}seg'.format(**formata_segundos(trabalho_fds_nao_permitido))

            tempo_total_valido = (
                tempo_total_horas_trabalhadas
                + tempo_abonado
                + tempo_trabalho_remoto
                - trabalho_fds_nao_permitido
                - hora_extra_nao_justificada
                - tempo_nao_abonado
            )

            saldo = tempo_total_valido - tempo_total_carga_horaria
            saldo_descricao_grafico = 'Saldo'
            saldo_descricao_totais = 'Saldo de horas para o período informado. Equivale ao tempo total válido menos o total da carga horária devida.'

            relatorio_pessoa['saldo'] = ('' if saldo >= 0 else '-') + '{h}h {m}min {s}seg'.format(**formata_segundos(saldo))
            relatorio_pessoa['saldo_descricao_grafico'] = saldo_descricao_grafico
            relatorio_pessoa['saldo_descricao_totais'] = saldo_descricao_totais

            relatorio_pessoa['total_tempo_valido'] = '{h}h {m}min {s}seg'.format(**formata_segundos(tempo_total_valido))

            relatorio_pessoa['tem_horarios_inferiores'] = tem_horarios_inferiores > 0
            relatorio_pessoa['tem_horarios_excedentes'] = tem_horarios_excedentes > 0

            relatorio_pessoa['eh_chefe_periodo'] = False

            if len(dias_em_que_foi_chefe_setor) > 0:
                relatorio_pessoa['eh_chefe_periodo'] = True

            relatorio_pessoa['qtd_dias_periodo'] = (data_fim - data_ini).days + 1

        relatorio_pessoa_finalizar()

        ##################################################################################
        # trata inconsistências com cálculos adiados e inclui informações sobre
        # compensações (se for o caso)

        relatorio_pessoa['trata_compensacoes'] = trata_compensacoes

        total_debito_pendente = 0
        total_debito_pendente_grafico_descricao = ''
        total_saldo_restante = 0
        total_saldo_restante_grafico_descricao = ''

        if so_inconsistentes or trata_inconsistencias or trata_compensacoes:
            # Nesse ponto, temos um relatório de ponto já resolvido e que pode ser
            # passado para um contexto de compensação sem a necessidade de novos
            # cálculos. Os cálculos de inconsistências foram adiados acima e
            # precisarão ser feitos agora (se for o caso).

            from ponto.compensacao import Contexto, SituacaoDia, formatar_segundos

            contexto_compensacao = Contexto(
                servidor=funcionario, periodo_data_inicial=data_ini, periodo_data_final=data_fim, relatorio_de_ponto=relatorio_pessoa
            )

            inconsistencias_dos_dias = Frequencia.get_inconsistencias(vinculo, data_ini, data_fim, contexto_compensacao)
            dias_removidos: list[date] = []

            for dia, dia_info in dias_dict.items():
                calcular_tem_inconsistencia = dia_info.tem_inconsistencia_calculo_adiado
                calcular_trata_inconsistencias = dia_info.trata_inconsistencias_calculo_adiado

                mostrar_dia = True
                tem_inconsistencia_inferior = False
                tem_inconsistencia_superior = False

                if calcular_tem_inconsistencia or calcular_trata_inconsistencias:
                    inconsistencias_do_dia = inconsistencias_dos_dias.get(dia, [])

                    if calcular_tem_inconsistencia and so_inconsistentes:
                        tem_inconsistencia = False

                        if inconsistencias_do_dia:
                            tem_inconsistencia = True

                            if so_inconsistentes_apenas_esta_inconsistencia:
                                tem_inconsistencia = tem_inconsistencia and so_inconsistentes_apenas_esta_inconsistencia in inconsistencias_do_dia

                            if so_inconsistentes_situacao_abono not in cls.SITUACAO_INCONSISTENCIA_ABONO_CHOICES:
                                so_inconsistentes_situacao_abono = cls.SITUACAO_INCONSISTENCIA_COM_OU_SEM_ABONO

                            if so_inconsistentes_situacao_abono != cls.SITUACAO_INCONSISTENCIA_DESCONSIDERAR_ABONO:
                                dia_tem_abono = dia_info.abonos_chefia

                                tem_inconsistencia = tem_inconsistencia and any(
                                    [
                                        so_inconsistentes_situacao_abono == cls.SITUACAO_INCONSISTENCIA_COM_OU_SEM_ABONO,
                                        dia_tem_abono and so_inconsistentes_situacao_abono == cls.SITUACAO_INCONSISTENCIA_COM_ABONO,
                                        not dia_tem_abono and so_inconsistentes_situacao_abono == cls.SITUACAO_INCONSISTENCIA_SEM_ABONO,
                                    ]
                                )

                            if so_inconsistentes_situacao_debito not in cls.SITUACAO_INCONSISTENCIA_DEBITO_CHOICES:
                                so_inconsistentes_situacao_debito = cls.SITUACAO_INCONSISTENCIA_COM_DEBITO_COMPENSADO_OU_PENDENTE

                            if so_inconsistentes_situacao_debito != cls.SITUACAO_INCONSISTENCIA_DESCONSIDERAR_DEBITO:
                                dia_debito = contexto_compensacao.get_dia(dia)
                                dia_debito_restante = dia_debito.debito_qtd_restante
                                dia_tem_debito_pendente = dia_debito_restante > 0
                                dia_tem_debito_total = dia_debito_restante == dia_debito.debito_qtd_considerado

                                tem_inconsistencia = tem_inconsistencia and any(
                                    [
                                        so_inconsistentes_situacao_debito == cls.SITUACAO_INCONSISTENCIA_COM_DEBITO_COMPENSADO_OU_PENDENTE,
                                        dia_tem_debito_pendente
                                        and not dia_tem_debito_total
                                        and so_inconsistentes_situacao_debito == cls.SITUACAO_INCONSISTENCIA_COM_DEBITO_PARTE_COMPENSADO,
                                        dia_tem_debito_pendente
                                        and dia_tem_debito_total
                                        and so_inconsistentes_situacao_debito == cls.SITUACAO_INCONSISTENCIA_COM_DEBITO_NADA_COMPENSADO,
                                        not dia_tem_debito_pendente
                                        and so_inconsistentes_situacao_debito == cls.SITUACAO_INCONSISTENCIA_COM_DEBITO_TODO_COMPENSADO,
                                    ]
                                )
                        else:
                            tem_inconsistencia = False

                        if not tem_inconsistencia:
                            mostrar_dia = False  # o dia será removido

                    if calcular_trata_inconsistencias and trata_inconsistencias:
                        ', '.join([cls.DESCRICAO_INCONSISTENCIA[i] for i in inconsistencias_do_dia])

                        if inconsistencias_do_dia:
                            for inconsistencia_do_dia in inconsistencias_do_dia:
                                if inconsistencia_do_dia in [
                                    Frequencia.INCONSISTENCIA_MENOR_JORNADA,
                                    Frequencia.INCONSISTENCIA_FALTA,
                                    Frequencia.INCONSISTENCIA_MAIOR_JORNADA,
                                    Frequencia.INCONSISTENCIA_TEMPO_MAIOR_DEZ_HORAS,
                                    Frequencia.INCONSISTENCIA_NUMERO_IMPAR_REGISTROS,
                                    Frequencia.INCONSISTENCIA_INTERVALO_INFERIOR_1H,
                                    Frequencia.INCONSISTENCIA_INTERVALO_SUPERIOR_3H,
                                    Frequencia.INCONSISTENCIA_NENHUM_INTERVALO,
                                    # Frequencia.INCONSISTENCIA_TURNO_INSUFICIENTE,
                                    # Frequencia.INCONSISTENCIA_TURNO_EXCESSIVO,
                                    # Frequencia.INCONSISTENCIA_ATRASO,
                                ]:
                                    if inconsistencia_do_dia in [Frequencia.INCONSISTENCIA_MENOR_JORNADA, Frequencia.INCONSISTENCIA_FALTA]:
                                        tem_inconsistencia_inferior = True
                                    elif inconsistencia_do_dia in [
                                        Frequencia.INCONSISTENCIA_MAIOR_JORNADA,
                                        Frequencia.INCONSISTENCIA_TEMPO_MAIOR_DEZ_HORAS,
                                    ]:
                                        tem_inconsistencia_superior = True

                                if AbonoChefia.CHOICES_POR_INCONSISTENCIAS[inconsistencia_do_dia] == AbonoChefia.ACAO_ABONO_FALTA_CHOICES:
                                    dia_info.acao_abono_inconsistencia = 'inferior'
                                elif (
                                    AbonoChefia.CHOICES_POR_INCONSISTENCIAS[inconsistencia_do_dia]
                                    == AbonoChefia.ACAO_ABONO_TEMPO_MAIOR_DEZ_HORAS_CHOICES
                                ):
                                    dia_info.acao_abono_inconsistencia = 'excedente'

                            valores_inconsistencias = inconsistencias_do_dia
                            display_inconsistencias = [cls.DISPLAY_INCONSISTENCIA.get(i, {}) for i in inconsistencias_do_dia]
                            dia_info.informacoes_registro = valores_inconsistencias
                            dia_info.informacoes_registro_display = display_inconsistencias

                if tem_inconsistencia_inferior and not dia_info.tem_inconsistencia_inferior:
                    dia_info.tem_inconsistencia_inferior = True
                    tem_horarios_inferiores += 1
                if tem_inconsistencia_superior and not dia_info.tem_inconsistencia_superior:
                    dia_info.tem_inconsistencia_superior = True
                    tem_horarios_excedentes += 1

                if not mostrar_dia:
                    # removendo o dia

                    if dia_info.tem_inconsistencia_inferior:
                        tem_horarios_inferiores -= 1
                    if dia_info.tem_inconsistencia_superior:
                        tem_horarios_excedentes -= 1

                    # atualiza os totais
                    tempo_abonado -= dia_info.tempo_abonado
                    tempo_trabalho_remoto -= dia_info.tempo_trabalho_remoto
                    tempo_abonado_para_compensacao -= dia_info.tempo_abonado_para_compensacao
                    tempo_nao_abonado -= dia_info.tempo_nao_abonado
                    hora_extra_nao_justificada -= dia_info.hora_extra_nao_justificada
                    hora_extra_justificada -= dia_info.hora_extra_justificada
                    hora_extra_para_compensacao_carga_horaria -= dia_info.hora_extra_para_compensacao_carga_horaria
                    trabalho_fds_permitido_para_compensacao_carga_horaria -= dia_info.trabalho_fds_permitido_para_compensacao_carga_horaria
                    trabalho_fds_permitido_como_hora_extra -= dia_info.trabalho_fds_permitido_como_hora_extra
                    trabalho_fds_nao_permitido -= dia_info.trabalho_fds_nao_permitido
                    tempo_total_hora_extra_noturna -= dia_info.tempo_total_hora_extra_noturna
                    tempo_total_horas_trabalhadas -= dia_info.tempo_total_horas_trabalhadas
                    tempo_total_carga_horaria -= dia_info.tempo_total_carga_horaria

                    # atualiza informações das semanas
                    semana_count = dia_info.semana
                    semanas_dict[semana_count]['ch_exigida'] -= dia_info.tempo_total_carga_horaria
                    semanas_dict[semana_count]['ch_valida'] -= (
                        dia_info.duracao_segundos
                        - dia_info.tempo_nao_abonado
                        - dia_info.hora_extra_nao_justificada
                        - dia_info.trabalho_fds_nao_permitido
                    )
                    semanas_dict[semana_count]['ch_segundos'] -= dia_info.duracao_segundos_bruto
                    semanas_dict[semana_count]['min_dia'] = (
                        min(dia, semanas_dict[semana_count]['min_dia']) if semanas_dict[semana_count].get('min_dia') else dia
                    )
                    semanas_dict[semana_count]['max_dia'] = (
                        max(dia, semanas_dict[semana_count]['max_dia']) if semanas_dict[semana_count].get('max_dia') else dia
                    )

                    # marca o dia para remocao
                    dias_removidos.append(dia)

            # remove os dias (se for caso)
            for dia_removido in dias_removidos:
                dias_dict.pop(dia_removido)

            if trata_compensacoes:

                def before_dia(situacao_dia: SituacaoDia):
                    data = situacao_dia.dia
                    return data in dias_dict

                def complete_dia(situacao_dia: SituacaoDia):
                    data = situacao_dia.dia
                    if data in dias_dict:
                        compensacao_info = situacao_dia.compensacao_info_do_dia
                        dias_dict[data].compensacao = compensacao_info.as_dict()
                        ##
                        # redefine duração bruta, duração (válida) e o tempo total de horas trabalhadas do dia
                        ch_trabalhada_bruta = situacao_dia.carga_horaria_trabalhada_bruta_qtd
                        ch_trabalhada_final = situacao_dia.carga_horaria_trabalhada_final_qtd
                        dias_dict[data].duracao_bruto = time.strftime('%H:%M:%S', time.gmtime(ch_trabalhada_bruta))
                        dias_dict[data].duracao = time.strftime('%H:%M:%S', time.gmtime(ch_trabalhada_final))
                        dias_dict[data].tempo_total_horas_trabalhadas = ch_trabalhada_final
                        ##

                contexto_totais = contexto_compensacao.get_totais(before_dia, complete_dia)

                # atualiza os totais
                tempo_total_horas_trabalhadas = contexto_totais.total_trabalhado

                total_debito = contexto_totais.total_considerado_debito
                total_debito_reposto = contexto_totais.total_reposto_debito
                total_debito_pendente = contexto_totais.total_restante_debito
                total_saldo = contexto_totais.total_considerado_saldo
                total_saldo_utilizado = contexto_totais.total_utilizado_saldo
                total_saldo_restante = contexto_totais.total_restante_saldo
                total_debito_desconsiderado = contexto_totais.total_desconsiderado_debito
                mensagens_debito_desconsiderado = contexto_totais.mensagens_debito_desconsiderado
                dias_debito_desconsiderado = contexto_totais.dias_debito_desconsiderado
                total_saldo_desconsiderado = contexto_totais.total_desconsiderado_saldo
                mensagens_saldo_desconsiderado = contexto_totais.mensagens_saldo_desconsiderado
                dias_saldo_desconsiderado = contexto_totais.dias_saldo_desconsiderado

                if contexto_totais.total_exigido_final and contexto_totais.total_debito_externo:
                    relatorio_pessoa['total_periodo_carga_horaria_liquida'] = '{h}h {m}min {s}seg'.format(
                        **formata_segundos(contexto_totais.total_exigido_final + contexto_totais.total_debito_externo)
                    )

                relatorio_pessoa['totais_compensacao'] = {
                    'contexto': contexto_compensacao,
                    'total_debito': formatar_segundos(total_debito, True),
                    'total_debito_reposto': formatar_segundos(total_debito_reposto, True),
                    'total_debito_pendente': formatar_segundos(total_debito_pendente, True),
                    'total_saldo': formatar_segundos(total_saldo, True),
                    'total_saldo_utilizado': formatar_segundos(total_saldo_utilizado, True),
                    'total_saldo_restante': formatar_segundos(total_saldo_restante, True),
                    'total_debito_reposto_is_zero': total_debito_reposto == 0,
                    'total_debito_pendente_is_zero': total_debito_pendente == 0,
                    'total_saldo_restante_is_zero': total_saldo_restante == 0,
                    'total_debito_desconsiderado': formatar_segundos(total_debito_desconsiderado, True),
                    'total_debito_desconsiderado_motivos': mensagens_debito_desconsiderado,
                    'total_debito_desconsiderado_dias': dias_debito_desconsiderado,
                    'total_debito_desconsiderado_is_zero': total_debito_desconsiderado == 0,
                    'total_saldo_desconsiderado': formatar_segundos(total_saldo_desconsiderado, True),
                    'total_saldo_desconsiderado_motivos': mensagens_saldo_desconsiderado,
                    'total_saldo_desconsiderado_dias': dias_saldo_desconsiderado,
                    'total_saldo_desconsiderado_is_zero': total_saldo_desconsiderado == 0,
                }

                if total_debito_pendente > 0:
                    total_debito_pendente_grafico_descricao = 'Débito pendente'

                if total_saldo_restante > 0:
                    total_saldo_restante_grafico_descricao = 'Saldo restante'

            relatorio_pessoa_finalizar()

        # gráfico do relatório (se for o caso)
        if show_grafico:
            serie = []

            serie.append(
                {
                    'name': 'Carga Horária Exigida ',
                    'y': tempo_total_carga_horaria / 3600.0,
                    'y_format': formata_segundos_h_min_seg(tempo_total_carga_horaria),
                    'color': '#77a1e5',
                }
            )

            serie.append(
                {
                    'name': 'Total de Horas Trabalhadas',
                    'y': tempo_total_horas_trabalhadas / 3600.0,
                    'y_format': formata_segundos_h_min_seg(tempo_total_horas_trabalhadas),
                    'color': '#77a1e5',
                }
            )

            if tempo_abonado:
                serie.append(
                    {
                        'name': 'Total abonado sem necessidade de compensação ',
                        'y': tempo_abonado / 3600.0,
                        'y_format': formata_segundos_h_min_seg(tempo_abonado),
                        'color': '#a6c96a',
                    }
                )
            if tempo_trabalho_remoto:
                serie.append(
                    {
                        'name': 'Total Trabalho Remoto',
                        'y': tempo_trabalho_remoto / 3600.0,
                        'y_format': formata_segundos_h_min_seg(tempo_trabalho_remoto),
                        'color': '#a6c96a',
                    }
                )

            if tempo_nao_abonado:
                serie.append(
                    {
                        'name': 'Total não abonado',
                        'y': tempo_nao_abonado / 3600.0,
                        'y_format': formata_segundos_h_min_seg(tempo_nao_abonado),
                        'color': '#c42525',
                    }
                )

            if tempo_abonado_para_compensacao:
                serie.append(
                    {
                        'name': 'Total abonado para compensação',
                        'y': tempo_abonado_para_compensacao / 3600.0,
                        'y_format': formata_segundos_h_min_seg(tempo_abonado_para_compensacao),
                        'color': '#f28f43',
                    }
                )

            if hora_extra_justificada:
                serie.append(
                    {
                        'name': 'Hora extra justificada',
                        'y': hora_extra_justificada / 3600.0,
                        'y_format': formata_segundos_h_min_seg(hora_extra_justificada),
                        'color': '#a6c96a',
                    }
                )

            if hora_extra_nao_justificada:
                serie.append(
                    {
                        'name': 'Hora extra não justificada',
                        'y': hora_extra_nao_justificada / 3600.0,
                        'y_format': formata_segundos_h_min_seg(hora_extra_nao_justificada),
                        'color': '#f28f43',
                    }
                )

            if hora_extra_para_compensacao_carga_horaria:
                serie.append(
                    {
                        'name': 'Hora extra para compensação de carga horária',
                        'y': hora_extra_para_compensacao_carga_horaria / 3600.0,
                        'y_format': formata_segundos_h_min_seg(hora_extra_para_compensacao_carga_horaria),
                        'color': '#a6c96a',
                    }
                )

            if trabalho_fds_permitido_para_compensacao_carga_horaria:
                serie.append(
                    {
                        'name': 'Trabalho no fim de semana permitido para compensação de carga horária',
                        'y': trabalho_fds_permitido_para_compensacao_carga_horaria / 3600.0,
                        'y_format': formata_segundos_h_min_seg(trabalho_fds_permitido_para_compensacao_carga_horaria),
                        'color': '#77a1e5',
                    }
                )

            if trabalho_fds_permitido_como_hora_extra:
                serie.append(
                    {
                        'name': 'Trabalho no fim de semana permitido como hora extra',
                        'y': trabalho_fds_permitido_como_hora_extra / 3600.0,
                        'y_format': formata_segundos_h_min_seg(trabalho_fds_permitido_como_hora_extra),
                        'color': '#77a1e5',
                    }
                )

            if trabalho_fds_nao_permitido:
                serie.append(
                    {
                        'name': 'Trabalho no fim de semana não permitido',
                        'y': trabalho_fds_nao_permitido / 3600.0,
                        'y_format': formata_segundos_h_min_seg(trabalho_fds_nao_permitido),
                        'color': '#c42525',
                    }
                )

            # situações
            cor_barra_red = '#c42525'
            cor_barra_green = '#a6c96a'

            if total_debito_pendente > 0:
                serie.append(
                    {
                        'name': f'{total_debito_pendente_grafico_descricao}',
                        'y': total_debito_pendente * -1 / 3600.0,
                        'y_format': formata_segundos_h_min_seg(total_debito_pendente * -1),
                        'color': cor_barra_red,
                    }
                )

            if total_saldo_restante > 0:
                serie.append(
                    {
                        'name': f'{total_saldo_restante_grafico_descricao}',
                        'y': total_saldo_restante / 3600.0,
                        'y_format': formata_segundos_h_min_seg(total_saldo_restante),
                        'color': cor_barra_green,
                    }
                )

            grafico = ColumnChart(
                f'grafico_{vinculo.pessoa.pk}',
                title=f'Frequências {vinculo.pessoa.nome}',
                subtitle='Contabilização das horas no período',
                data=serie,
                minPointLength=5,
                showDataLabels=True,
                tooltip={'pointFormat': '<b>{point.y_format}</b>'},
                format='{point.y_format}',
            )
            grafico.plotOptions['column'] = {'shadow': False}

            relatorio_pessoa['grafico_frequencias'] = grafico

        return relatorio_pessoa

    PontoDiaDict = TypeVar('PontoDiaDict', bound=dict)

    @staticmethod
    def relatorio_ponto_pessoa_update(
        relatorio_ponto_pessoa: dict,  # uma saida do método Frequencia.relatorio_ponto_pessoa
    ):
        """
        Atualização de um relatório de ponto já calculado pelo método Frequencia.relatorio_ponto_pessoa.
        A atualização inclue, por exemplo, adicionar novos atributos ao relatório.
        """

        from ponto.compensacao import Contexto

        if relatorio_ponto_pessoa['dias']:
            vinculo = relatorio_ponto_pessoa['funcionario'].get_vinculo()
            data_inicio = min([dia_info['dia'] for dia_info in relatorio_ponto_pessoa['dias']])
            data_fim = max([dia_info['dia'] for dia_info in relatorio_ponto_pessoa['dias']])

            contexto_compensacao = Contexto(
                servidor=vinculo.relacionamento,
                periodo_data_inicial=data_inicio,
                periodo_data_final=data_fim,
                relatorio_de_ponto=relatorio_ponto_pessoa,
            )

            # atributo adicional no dia: "pode_solicitar_abono_parcial"
            permissao_solicitar_abono_parcial = AbonoChefia.pode_solicitar_abono_parcial(
                vinculo,
                data_inicio,
                data_fim,
                contexto_compensacao,
            )

            # atributo adicional no dia: "pode_solicitar_revisao_abono_chefia"
            permissao_solicitar_revisao_abono_chefia = AbonoChefia.pode_solicitar_revisao_abono_chefia(
                vinculo,
                data_inicio,
                data_fim,
                contexto_compensacao,
            )

            # atualiza cada dia do relatório
            for dia_info in relatorio_ponto_pessoa['dias']:
                dia_info['pode_solicitar_abono_parcial'] = permissao_solicitar_abono_parcial.get(dia_info['dia'], False)
                dia_info['pode_solicitar_revisao_abono_chefia'] = permissao_solicitar_revisao_abono_chefia.get(dia_info['dia'], False)

    @staticmethod
    def segundos_para_time(segundos=0):
        """segundos para Time"""
        if segundos >= 0:
            minutos, segundos = divmod(segundos, 60)
            horas, minutos = divmod(minutos, 60)
            #
            return datetime.time(hour=horas, minute=minutos, second=segundos)
        return datetime.time(second=0)

    @staticmethod
    def time_para_segundos(time=None):
        """Time para segundos"""
        if time:
            return time.hour * 60 * 60 + time.minute * 60 + time.second
        #
        return 0


class VersaoTerminal(models.ModelPlus):
    numero = models.CharField(max_length=5, verbose_name='Número de Versão', unique=True)

    def __str__(self):
        return self.numero


class Maquina(models.ModelPlus):
    SEARCH_FIELDS = ['descricao', 'ip']
    descricao = models.CharField(max_length=30, verbose_name='Descrição')
    ip = models.GenericIPAddressField(unique=True, verbose_name='IP')
    porta_servico = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='Porta Serviço',
        help_text='Porta do serviço disponibilizado pela máquina. Use caso seja servidor de impressão.',
    )
    ativo = models.BooleanField(
        default=None, verbose_name='Ativa', null=True, help_text='Caso seja desconhecido, a máquina ainda não foi aceita pelo administrador do SUAP.'
    )
    cliente_cadastro_impressao_digital = models.BooleanField(default=False, verbose_name='Cadastro de Impressões Digitais')
    cliente_chaves = models.BooleanField(default=False, verbose_name='Terminal de Chaves')
    cliente_ponto = models.BooleanField(default=False, verbose_name='Terminal de Ponto Eletrônico')
    cliente_refeitorio = models.BooleanField(default=False, verbose_name='Terminal de Refeitório')
    servidor_impressao = models.BooleanField(
        default=False, verbose_name='Servidor de Impressão', help_text='A máquina será utilizada para impressão de comprovantes do protocolo.'
    )
    texto_final_impressao = models.TextField(
        null=True,
        blank=True,
        help_text='Preencha esse campo caso tenha marcado a opção anterior e deseja que algum texto seja impresso ao final do comprovante. Ex: Ou ligue para  (XX) XXXX-XXX',
    )
    uo = models.ForeignKeyPlus(UnidadeOrganizacional, null=True, verbose_name='Campus', on_delete=models.CASCADE)
    observacao = models.TextField('Observação', null=True, blank=True)
    usuarios = models.ManyToManyField(
        'comum.User',
        blank=True,
        verbose_name='Usuários',
        help_text='Usuários que poderão usar os serviços da máquina. Use caso seja servidor de impressão.',
    )
    ultimo_log = models.DateTimeField(null=True, blank=True)
    predios = models.ManyToManyField(Predio, blank=True)
    versao_terminal = models.ForeignKeyPlus(VersaoTerminal, null=True, blank=True, verbose_name='Versão do Terminal', on_delete=models.CASCADE)

    class History:
        ignore_fields = ('ultimo_log',)

    class Meta:
        db_table = 'maquina'
        verbose_name = 'Máquina'
        verbose_name_plural = 'Máquinas'

    def clean(self):
        if (
            (self.cliente_refeitorio and self.cliente_ponto)
            or (self.cliente_refeitorio and self.cliente_chaves)
            or (self.cliente_refeitorio and self.cliente_cadastro_impressao_digital)
        ):
            raise ValidationError('Terminal de refeitório não pode ser configurado com módulo de cadastro/chaves/ponto.')

    def __str__(self):
        return self.descricao

    def get_atividade(self):
        ultimo_registro = self.ultimo_log
        velho = datetime.datetime.today() - timedelta(1)
        return ultimo_registro < velho

    @classmethod
    def get_maquinas_impressao(cls, user=None):
        user = user or tl.get_user()
        if not user.has_perm('protocolo.pode_imprimir_comprovante'):
            return Maquina.objects.none()
        return user.maquina_set.filter(servidor_impressao=True, ativo=True)


class MaquinaLog(models.ModelPlus):
    """
    A classe serve para guardar as últimas operações das máquinas.
    """

    SUCESSO = 0
    ERRO = 1
    ALERTA = 2

    STATUS_MAQUINA_LOG_CHOICES = [[SUCESSO, 'Sucesso'], [ERRO, 'Erro'], [ALERTA, 'Alerta']]

    maquina = models.ForeignKeyPlus(Maquina, verbose_name='Máquina', on_delete=models.CASCADE)
    status = models.PositiveIntegerFieldPlus('Status', choices=STATUS_MAQUINA_LOG_CHOICES, default=SUCESSO)
    operacao = models.CharField('Operação', max_length=255)
    mensagem = models.TextField('Mensagem', null=True, blank=True)
    horario = models.DateTimeField(auto_now=True, verbose_name='Horário')

    class History:
        disabled = True

    class Meta:
        ordering = ['maquina', 'operacao']
        verbose_name = 'Log de Máquina'
        verbose_name_plural = 'Logs de Máquinas'

    def save(self, *args, **kargs):
        super().save(*args, **kargs)
        self.maquina.ultimo_log = self.horario
        self.maquina.save()


class Liberacao(models.ModelPlus):
    uo = models.ForeignKeyPlus(
        UnidadeOrganizacional,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        verbose_name='Unidade Organizacional',
        help_text='Define onde será aplicada a liberação.',
    )
    data_inicio = models.DateFieldPlus('Data Início', db_index=True)
    data_fim = models.DateFieldPlus('Data Fim', null=True, db_index=True)
    descricao = models.TextField('Descrição', max_length=200)
    tipo = models.PositiveIntegerField('Tipo Liberação', default=0, choices=TipoLiberacao.get_choices())
    ch_maxima_exigida = models.IntegerField(
        'Carga horária máxima exigida pela instituição (em horas) ',
        default=0,
        help_text=f"Somente para o tipo '{TipoLiberacao.LIBERACAO_PARCIAL}'. É a carga "
        'horária máxima que será exigida no(s) dia(s) '
        'do período informado.',
    )

    class Meta:
        verbose_name = 'Liberação'
        verbose_name_plural = 'Liberações'

    def __str__(self):
        return self.descricao

    @classmethod
    def filtrar_por_dia(cls, vinculo, data):
        return cls.filtrar_por_periodo(vinculo, data, data)

    @classmethod
    def liberacoes_por_uo(cls, data_inicio, data_fim, uo=None):
        liberacoes = cls.objects.filter(data_inicio__lte=data_fim, data_fim__gte=data_inicio, uo__isnull=True) | cls.objects.filter(
            data_inicio__gte=data_inicio, data_inicio__lte=data_fim, uo__isnull=True
        )
        if uo:
            liberacoes = (
                liberacoes
                | cls.objects.filter(data_inicio__lte=data_fim, data_fim__gte=data_inicio, uo=uo)
                | cls.objects.filter(data_inicio__gte=data_inicio, data_inicio__lte=data_fim, uo=uo)
            )
        return liberacoes

    @classmethod
    def liberacoes_recorrentes_por_uo(cls, data_inicio, data_fim, uo=None):
        meses = meses_entre(data_inicio, data_fim)
        qs_liberacao = cls.objects.filter(tipo=TipoLiberacao.get_numero(TipoLiberacao.FERIADO_RECORRENTE))
        qs_liberacao_por_uo = cls.objects.none()
        qs_liberacao_sem_uo = (
            qs_liberacao.filter(uo__isnull=True)
            .filter(Q(data_inicio__month__in=meses) | Q(data_fim__month__in=meses))
            .filter(data_inicio__lte=data_fim)  # o início da liberação deve ser anterior ou igual a data final do período
        )
        if uo:
            qs_liberacao_por_uo = (
                qs_liberacao.filter(uo=uo)
                .filter(Q(data_inicio__month__in=meses) | Q(data_fim__month__in=meses))
                .filter(data_inicio__lte=data_fim)  # o início da liberação deve ser anterior ou igual a data final do período
            )

        qs_liberacao = qs_liberacao_sem_uo | qs_liberacao_por_uo
        if data_inicio == data_fim:
            qs_liberacao = qs_liberacao.filter(data_inicio__day=data_inicio.day)

        return qs_liberacao

    @classmethod
    def filtrar_por_periodo_por_uo(cls, data_inicio, data_fim, uo=None):
        return (cls.liberacoes_por_uo(data_inicio, data_fim, uo) | cls.liberacoes_recorrentes_por_uo(data_inicio, data_fim, uo)).distinct()

    @classmethod
    def filtrar_por_periodo(cls, vinculo, data_inicio, data_fim):
        if data_inicio > data_fim:
            return cls.objects.none()

        if isinstance(vinculo.relacionamento, Servidor):
            servidor = vinculo.relacionamento
            historico_setor = servidor.historico_setor_suap(data_inicio, data_fim)
            if historico_setor.exists():
                liberacoes = cls.objects.none()
                for setor_historico in historico_setor:
                    if setor_historico.data_inicio_no_setor <= data_inicio:
                        data_inicio_referencia = data_inicio
                    else:
                        data_inicio_referencia = setor_historico.data_inicio_no_setor

                    if not setor_historico.data_fim_no_setor or (setor_historico.data_fim_no_setor and setor_historico.data_fim_no_setor >= data_fim):
                        data_fim_referencia = data_fim
                    else:
                        data_fim_referencia = setor_historico.data_fim_no_setor
                    liberacoes = liberacoes | cls.filtrar_por_periodo_por_uo(data_inicio_referencia, data_fim_referencia, setor_historico.setor.uo)

                if not data_fim_referencia or data_fim_referencia and data_fim_referencia < data_fim:
                    if vinculo.relacionamento.setor:
                        liberacoes = liberacoes | cls.filtrar_por_periodo_por_uo(data_fim_referencia, data_fim, vinculo.relacionamento.setor.uo)
                return liberacoes
            else:
                historico_setor = servidor.historico_setor_siape(data_inicio, data_fim)
                if historico_setor.exists():
                    liberacoes = cls.objects.none()
                    for setor_hist in historico_setor:
                        uo_servidor = setor_hist.setor_exercicio.uo and setor_hist.setor_exercicio.uo.equivalente
                        if setor_hist.data_inicio_setor_lotacao and setor_hist.data_inicio_setor_lotacao <= data_inicio:
                            data_inicio_referencia = data_inicio
                        else:
                            data_inicio_referencia = setor_hist.data_inicio_setor_lotacao

                        if (
                            not setor_hist.data_fim_setor_lotacao
                            or setor_hist.data_fim_setor_lotacao
                            and setor_hist.data_fim_setor_lotacao >= data_fim
                        ):
                            data_fim_referencia = data_fim
                        else:
                            data_fim_referencia = setor_hist.data_fim_setor_lotacao
                        liberacoes = liberacoes | cls.filtrar_por_periodo_por_uo(data_inicio_referencia, data_fim_referencia, uo_servidor)

                    if not data_fim_referencia or data_fim_referencia and data_fim_referencia < data_fim:
                        if vinculo.relacionamento.setor:
                            liberacoes = liberacoes | cls.filtrar_por_periodo_por_uo(data_fim_referencia, data_fim, vinculo.relacionamento.setor.uo)
                    return liberacoes

        if vinculo.relacionamento.setor:
            return cls.filtrar_por_periodo_por_uo(data_inicio, data_fim, vinculo.relacionamento.setor.uo)
        else:
            return cls.filtrar_por_periodo_por_uo(data_inicio, data_fim)

    @classmethod
    def get_liberacoes_calendario(cls, uo, ano, mes=None):
        return cls.get_liberacoes_calendario_nao_recorrentes(uo, ano, mes) + cls.get_liberacoes_calendario_recorrentes(uo, ano, mes)

    @classmethod
    def get_liberacoes_calendario_nao_recorrentes(cls, uo, ano, mes=None):
        qs_liberacoes_campus = Liberacao.objects.filter(uo=uo).exclude(tipo=TipoLiberacao.get_numero(TipoLiberacao.FERIADO_RECORRENTE))
        qs_liberacoes = Liberacao.objects.filter(uo=None).exclude(tipo=TipoLiberacao.get_numero(TipoLiberacao.FERIADO_RECORRENTE))
        if mes:
            liberacoes_campus = qs_liberacoes_campus.filter(data_inicio__year=ano, data_inicio__month=mes) | qs_liberacoes_campus.filter(
                data_fim__year=ano, data_fim__month=mes
            )
            liberacoes = qs_liberacoes.filter(data_inicio__year=ano, data_inicio__month=mes) | qs_liberacoes.filter(
                data_fim__year=ano, data_fim__month=mes
            )
        else:
            liberacoes_campus = qs_liberacoes_campus.filter(data_inicio__year=ano) | qs_liberacoes_campus.filter(data_fim__year=ano)
            liberacoes = qs_liberacoes.filter(data_inicio__year=ano) | qs_liberacoes.filter(data_fim__year=ano)
        return list((liberacoes | liberacoes_campus).order_by('data_inicio'))

    @classmethod
    def get_liberacoes_calendario_recorrentes(cls, uo, ano, mes=None):
        feriados_recorrentes_campus = Liberacao.objects.filter(uo=uo, tipo=TipoLiberacao.get_numero(TipoLiberacao.FERIADO_RECORRENTE))
        feriados_recorrentes = Liberacao.objects.filter(uo=None, tipo=TipoLiberacao.get_numero(TipoLiberacao.FERIADO_RECORRENTE))
        liberacoes = []
        for liberacao in (feriados_recorrentes | feriados_recorrentes_campus).order_by('data_inicio'):
            data = f'{liberacao.data_inicio.day!s}-{liberacao.data_inicio.month!s}-{ano!s}'
            if liberacao.data_inicio == liberacao.data_fim or liberacao.data_fim is None:
                liberacao.data_inicio = datetime.datetime.strptime(data, '%d-%m-%Y').date()
                liberacao.data_fim = datetime.datetime.strptime(data, '%d-%m-%Y').date()
            else:
                liberacao.data_inicio = datetime.datetime.strptime(data, '%d-%m-%Y').date()
                liberacao.data_fim = datetime.datetime.strptime(data, '%d-%m-%Y').date()
            liberacoes.append(liberacao)
        return liberacoes

    def get_ch_maxima_exigida_display(self):
        if self.tipo == TipoLiberacao.get_numero(TipoLiberacao.LIBERACAO_PARCIAL):
            return f'{self.ch_maxima_exigida}'
        return 'Não aplicado.'

    def get_liberacao_css(self):
        css = 'Não aplicado.'
        if self.tipo in [0, 5]:
            css = 'extra'
        elif self.tipo == 1:
            css = 'evento'
        elif self.tipo == 2:
            css = 'recesso'
        elif self.tipo in [3, 4]:
            css = 'feriado'
        return css


class Observacao(models.ModelPlus):
    """
    Representa as observações cadastradas pelo funcionário.
    Estas NÃO sairão no relatório de frequências oficial.
    """

    vinculo = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Vínculo', editable=False, on_delete=models.CASCADE)
    data = models.DateFieldPlus(db_index=True, verbose_name='Data da Frequência')
    descricao = models.TextField(verbose_name='Observação')
    data_cadastro = models.DateTimeField(auto_now_add=True, editable=False, null=True, verbose_name='Data de Cadastro')

    class Meta:
        verbose_name = 'Observação'
        verbose_name_plural = 'Observações'

    def __str__(self):
        return 'Observação do Dia: {}'.format(self.data.strftime('%d/%m/%Y'))


class DocumentoAnexo(models.ModelPlus):
    vinculo = models.ForeignKeyPlus('comum.Vinculo', editable=False, on_delete=models.CASCADE)
    data = models.DateFieldPlus(db_index=True)
    descricao = models.TextField(max_length=200, verbose_name='Descrição')
    anexo = models.PrivateFileField(
        verbose_name='Anexo',
        upload_to='ponto/anexos',
        filetypes=['pdf', 'jpeg', 'jpg', 'png'],
        help_text='O formato do arquivo deve ser ".pdf", ".jpeg", ".jpg" ou ".png"',
    )

    class Meta:
        verbose_name = 'Anexo'
        verbose_name_plural = 'Anexos'

    def __str__(self):
        return self.descricao

    def delete(self, *args, **kwargs):
        self.anexo.delete()
        super().delete(*args, **kwargs)


class AbonoChefia(ModelPlus):
    """
    Representa se a chefia abona ou não uma anomalia no registro de ponto assim como sua justificativa/observacao
    do ponto cadastrada pelo funcionário.

    Demanda 1547 (fev/mar de 2024):
        - um dia poderá ter mais de um abono de chefia
        - um abono de chefia será parcial se estiver relacionado a uma solicitação de abono de parcial
        - os consumidores dos abonos de chefia de um dia qualquer deverão tratar a situação em que há tanto
          abonos de chefia parciais e não parciais (o padrão antigo)
        - dependendo do negócio do consumidor, um único abono não parcial poderá mudar toda a lógica conforme a
          situação ... a recíproca também é verdadeira (um abono parcial poderá sobrepor qualuer abono não parcial)
    """

    NAO_ABONADO = 0
    ABONADO_COM_COMPENSACAO = 1
    ABONADO = 2

    HORA_EXTRA_NAO_JUSTIFICADA = 3
    HORA_EXTRA_JUSTIFICADA = 4
    HORA_EXTRA_PARA_COMPENSACAO_CARGA_HORARIA = 7

    TRABALHO_FDS_NAO_PERMITIDO = 5
    TRABALHO_FDS_PERMITIDO_PARA_COMPENSACAO_CARGA_HORARIA = 6
    TRABALHO_FDS_PERMITIDO_COMO_HORA_EXTRA = 8

    TRABALHO_REMOTO = 9
    NUMERO_IMPAR_REGISTROS_NAO_PERMITIDO = 10
    INTERVALO_NAO_PERMITIDO = 11
    INTERVALO_AUSENTE = 12
    # TURNO_INVALIDO = 13
    # CHEGADA_ATRASADA = 14

    ACAO_ABONO_FALTA_CHOICES = [
        [ABONADO_COM_COMPENSACAO, 'Abonado com compensação de horário'],
        [ABONADO, 'Abonado'],
        [TRABALHO_REMOTO, 'Trabalho Remoto'],
        [NAO_ABONADO, 'Não abonado'],
    ]
    ACAO_ABONO_TEMPO_MAIOR_DEZ_HORAS_CHOICES = [  # na verdade refere-se ao tempo superior a carga horária do dia
        [
            HORA_EXTRA_PARA_COMPENSACAO_CARGA_HORARIA,  # apenas para efeitos de carga horária excedente
            'Tempo de trabalho excedente para compensação de carga-horária (até o limite de 10h de trabalho por dia)',
        ],
        [HORA_EXTRA_JUSTIFICADA, 'Hora extra justificada (até o limite de 10h de trabalho por dia)'],  # apenas para efeitos de remuneração
        [HORA_EXTRA_NAO_JUSTIFICADA, 'Hora extra não justificada'],
    ]
    ACAO_ABONO_TRABALHO_FDS_CHOICES = [
        [
            TRABALHO_FDS_PERMITIDO_PARA_COMPENSACAO_CARGA_HORARIA,  # apenas para efeitos de carga horária excedente
            'Trabalho no fim de semana autorizado para compensação de carga horária',
        ],
        [TRABALHO_FDS_PERMITIDO_COMO_HORA_EXTRA, 'Trabalho no fim de semana autorizado como hora extra'],  # apenas para efeitos de remuneração
        [TRABALHO_FDS_NAO_PERMITIDO, 'Trabalho no fim de semana não justificado/autorizado'],
    ]
    ACAO_ABONO_SAIDA_ANTECIPADA_CHOICES = [
        [ABONADO_COM_COMPENSACAO, 'Abonado com compensação de horário'],
        [ABONADO, 'Abonado'],
        [TRABALHO_REMOTO, 'Trabalho Remoto'],
        [NAO_ABONADO, 'Não abonado'],
    ]
    ACAO_NUMERO_IMPAR_REGISTROS_CHOICES = [
        [NUMERO_IMPAR_REGISTROS_NAO_PERMITIDO, Frequencia.DESCRICAO_INCONSISTENCIA[Frequencia.INCONSISTENCIA_NUMERO_IMPAR_REGISTROS]]
    ]
    ACAO_INTERVALO_NAO_PERMITIDO_CHOICES = [
        [INTERVALO_NAO_PERMITIDO, 'Intervalo de descanso/refeição inferior a 1 hora ou superior a 3 horas'],
    ]
    ACAO_INTERVALO_AUSENTE_CHOICES = [
        [INTERVALO_AUSENTE, 'Ausência de intervalo'],
    ]
    # ACAO_TURNO_INVALIDO_CHOICES = [
    #     [TURNO_INVALIDO, 'Turno ininterrupto inválido'],
    # ]
    # ACAO_CHEGADA_ATRASADA_CHOICES = [
    #     [CHEGADA_ATRASADA, Frequencia.DESCRICAO_INCONSISTENCIA[Frequencia.INCONSISTENCIA_ATRASO]],
    # ]

    # Quando for criar as outras regras de ponto lembrar de criar dict para os choices do formulario
    ACAO_ABONO_CHOICES = (
        ACAO_ABONO_FALTA_CHOICES
        + ACAO_ABONO_TEMPO_MAIOR_DEZ_HORAS_CHOICES
        + ACAO_ABONO_TRABALHO_FDS_CHOICES
        + ACAO_NUMERO_IMPAR_REGISTROS_CHOICES
        + ACAO_INTERVALO_NAO_PERMITIDO_CHOICES
        + ACAO_INTERVALO_AUSENTE_CHOICES
        # + ACAO_TURNO_INVALIDO_CHOICES
    )

    CHOICES_POR_INCONSISTENCIAS = {
        Frequencia.INCONSISTENCIA_MENOR_JORNADA: ACAO_ABONO_FALTA_CHOICES,
        Frequencia.INCONSISTENCIA_MAIOR_JORNADA: ACAO_ABONO_TEMPO_MAIOR_DEZ_HORAS_CHOICES,
        Frequencia.INCONSISTENCIA_FALTA: ACAO_ABONO_FALTA_CHOICES,
        Frequencia.INCONSISTENCIA_TEMPO_MAIOR_DEZ_HORAS: ACAO_ABONO_TEMPO_MAIOR_DEZ_HORAS_CHOICES,
        Frequencia.INCONSISTENCIA_TRABALHO_FDS: ACAO_ABONO_TRABALHO_FDS_CHOICES,
        Frequencia.INCONSISTENCIA_NUMERO_IMPAR_REGISTROS: ACAO_NUMERO_IMPAR_REGISTROS_CHOICES,
        Frequencia.INCONSISTENCIA_INTERVALO_INFERIOR_1H: ACAO_INTERVALO_NAO_PERMITIDO_CHOICES,
        Frequencia.INCONSISTENCIA_INTERVALO_SUPERIOR_3H: ACAO_INTERVALO_NAO_PERMITIDO_CHOICES,
        Frequencia.INCONSISTENCIA_NENHUM_INTERVALO: ACAO_INTERVALO_AUSENTE_CHOICES,
        # Frequencia.INCONSISTENCIA_TURNO_INSUFICIENTE: ACAO_TURNO_INVALIDO_CHOICES,
        # Frequencia.INCONSISTENCIA_TURNO_EXCESSIVO: ACAO_TURNO_INVALIDO_CHOICES,
        # Frequencia.INCONSISTENCIA_ATRASO: ACAO_CHEGADA_ATRASADA_CHOICES,
    }

    DESCRICOES_ABONO = {
        NAO_ABONADO: 'Usado para situação de falta sem motivo justificado. Esta ação impede que o servidor compense o dia em questão, ou seja, a ausência não será abonada e não pode ser compensada posteriormente.',
        ABONADO_COM_COMPENSACAO: 'Usado para atrasos, ausências justificadas (ressalvadas as concessões de que trata o art. 97 da Lei nº 8.112/1990) e saídas antecipadas que permitem compensação. Com esta ação, o servidor poderá compensar o dia ausente dentro do mês subsequente ou conforme regras específicas de compensação previstas na legislação vigente.',
        ABONADO: 'Usado para atrasos, ausências ou saídas antecipadas onde a chefia decide, com base nas justificativas do servidor (como atestados médicos ou outros documentos), que a ausência será abonada sem necessidade de compensação, ou que já foi compensada qualitativamente (como no caso de greve desde que esteja previsto em acordo).',
        TRABALHO_REMOTO: 'Usado para atrasos, ausências ou saídas antecipadas autorizados pela chefia imediata, com base nas necessidades de serviço e justificativas do servidor para que o mesmo possa executar sua atividade de forma remota.',
        HORA_EXTRA_NAO_JUSTIFICADA: 'Usado quando o servidor ultrapassa a jornada ordinária sem justificativa prévia. A chefia declara que não teve conhecimento das horas extras, que não serão compensadas nem pagas.',
        HORA_EXTRA_JUSTIFICADA: 'Usado para situações de serviço extraordinário previamente planejado com o servidor, onde a chefia aprova o pagamento, seguindo os procedimentos formais de solicitação de horas extras.',
        HORA_EXTRA_PARA_COMPENSACAO_CARGA_HORARIA: 'Usado para horas resultantes de serviço extraordinário que serão utilizadas para compensação de um débito de horas anterior ou outras compensações previstas dentro do mês.',
        TRABALHO_FDS_NAO_PERMITIDO: 'Usado quando o servidor trabalha no fim de semana sem conhecimento ou autorização da chefia. Neste caso, as horas não poderão ser compensadas nem pagas como horas extras.',
        TRABALHO_FDS_PERMITIDO_PARA_COMPENSACAO_CARGA_HORARIA: 'Usado quando o trabalho realizado no fim de semana será utilizado para compensar débitos de horas anteriores ou outros tipos de compensação específica.',
        TRABALHO_FDS_PERMITIDO_COMO_HORA_EXTRA: 'Usado para serviço extraordinário previamente planejado e autorizado no fim de semana, com processo encaminhado para pagamento de horas extras, seguindo os procedimentos formais.',
        NUMERO_IMPAR_REGISTROS_NAO_PERMITIDO: 'Usado quando ocorre um número ímpar de pontos no registro de frequências para um dia específico, sem necessidade de compensação, com a autorização da chefia.',
        INTERVALO_NAO_PERMITIDO: 'Usado quando ocorre um intervalo de descanso/refeição inferior a 1 hora ou superior a 3 horas',
        INTERVALO_AUSENTE: 'Usado quando ocorre ausência de intervalo de descanso/refeição',
        # TURNO_INVALIDO: 'Usado quando ocorre um turno ininterrupto inválido',
        # CHEGADA_ATRASADA: '?',
    }

    vinculo_pessoa = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Servidor', editable=False, on_delete=models.CASCADE)
    vinculo_chefe_imediato = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Chefe Imediato', related_name='vinculo_chefe_imediato_set', editable=False, on_delete=models.CASCADE
    )
    data = models.DateFieldPlus()
    descricao = models.TextField(max_length=200, verbose_name='Descrição', blank=True)
    acao_abono = models.PositiveIntegerField('Ação Chefe Imediato', default=NAO_ABONADO, choices=ACAO_ABONO_CHOICES)
    data_cadastro = models.DateTimeField('Data Cadastro', auto_now_add=True, editable=False, null=True)
    ultima_atualizacao = models.DateTimeField('Data Atualização', auto_now=True)
    solicitacao_abono_parcial = models.ForeignKeyPlus('ponto.SolicitacaoAbonoParcial', editable=False, null=True, on_delete=models.SET_NULL)
    ch_descontada = models.PositiveIntegerField('Carga Horária a Descontar', help_text='Em segundos.', null=True)

    class Meta:
        verbose_name = 'Abono de Chefia'
        verbose_name_plural = 'Abonos de Chefia'

    @property
    def eh_abono_parcial(self):
        return self.solicitacao_abono_parcial is not None

    @property
    def ch_abonada_parcialmente_display(self):
        """?h ?min ?seg"""
        abono_parcial = self.solicitacao_abono_parcial
        if abono_parcial:
            return abono_parcial.ch_solicitada_display
        return None

    @property
    def ch_abonada_parcialmente_display_2(self):
        """?:?:?"""
        abono_parcial = self.solicitacao_abono_parcial
        if abono_parcial:
            return abono_parcial.ch_solicitada_display_2
        return None

    @property
    def ch_descontada_display(self):
        """?h ?min ?seg"""
        from ponto.compensacao import formatar_segundos

        if self.ch_descontada:
            return formatar_segundos(self.ch_descontada, True, False)
        return None

    @property
    def ch_descontada_display_2(self):
        """[?h ][?min ][?seg]"""
        from ponto.compensacao import formatar_segundos

        if self.ch_descontada:
            return formatar_segundos(self.ch_descontada, True, True)
        return None

    def __str__(self):
        return f'Abono da Chefia para {self.data.strftime("%d/%m/%Y")}'

    def get_absolute_url(self):
        # return f'/admin/ponto/abonochefia/{self.id}/view/'
        return f'/ponto/visualizar_abono_chefia/{self.id}/'

    def can_view(self, user=None):
        user = user or tl.get_user()
        if self:
            if self.vinculo_pessoa.user == user or self.vinculo_chefe_imediato.user == user:
                return True
        return False

    def get_acao_abono_display_css(self):
        if self.acao_abono in [self.NAO_ABONADO, self.HORA_EXTRA_NAO_JUSTIFICADA, self.TRABALHO_FDS_NAO_PERMITIDO]:
            return 'error'
        elif self.acao_abono in [
            self.ABONADO,
            self.TRABALHO_REMOTO,
            self.HORA_EXTRA_JUSTIFICADA,
            self.TRABALHO_FDS_PERMITIDO_COMO_HORA_EXTRA,
            self.TRABALHO_FDS_PERMITIDO_PARA_COMPENSACAO_CARGA_HORARIA,
            self.HORA_EXTRA_PARA_COMPENSACAO_CARGA_HORARIA,
        ]:
            return 'success'
        elif self.acao_abono == self.ABONADO_COM_COMPENSACAO:
            return 'alert'
        else:
            return 'info'

    def save(self, *args, **kwargs):
        acao_foi_editada = self.id is not None
        save = super().save(*args, **kwargs)
        self.notificar(acao_editada=acao_foi_editada)
        return save

    def notificar(self, acao_editada=False):
        """
        envia e-mail apos a insercao ou as edicoes da acao do chefe imediato
        """
        pessoa = self.vinculo_pessoa.pessoa
        if self.vinculo_pessoa.email_notificacao:
            observacoes = Observacao.objects.filter(data=self.data, vinculo=self.vinculo_pessoa)
            observacoes_da_pessoa = ''
            for observacao in observacoes:
                if observacoes_da_pessoa:
                    observacoes_da_pessoa += '\n'
                observacoes_da_pessoa += f'{observacao.descricao}'
            if not observacoes_da_pessoa:
                observacoes_da_pessoa = 'Sem observações.'

            frequencias = Frequencia.get_frequencias_por_data(self.vinculo_pessoa, self.data)
            frequencias_da_pessoa = ''
            for frequencia in frequencias:
                if frequencias_da_pessoa:
                    frequencias_da_pessoa += '\n'
                frequencias_da_pessoa += '{}:{} ({})'.format(frequencia.acao, frequencia.horario.strftime('%H:%M:%S'), frequencia.maquina)
            if not frequencias_da_pessoa:
                frequencias_da_pessoa = 'Sem frequências.'

            assunto = '[SUAP] Avaliação da Frequência do Dia {}'.format(self.data.strftime('%d/%m/%Y'))
            mensagem = """<h1>Avaliação da Frequência do Dia</h1>
                <h2>{data}</h2>
                <p>Prezado(a) {nome},</p>
                <p>Comunicamos que a sua chefia imediata, {chefe}, {acao} com relação à frequência do dia {data}.</p>
                <h3>Avaliação da Chefia Imediata</h3>
                <dl>
                    <dt>{abono}:</dt><dd>{descricao}</dd>
                </dl>
                <h3>Frequência do Servidor</h3>
                <dl>
                    <dt>Data:</dt>
                    <dd>{data}</dd>
                    <dt>Registros:</dt>
                    <dd>{frequencias}</dd>
                    <dt>Observações:</dt>
                    <dd>{observacoes}</dd>
                </dl>""".format(
                data=self.data.strftime('%d/%m/%Y'),
                nome=pessoa.nome,
                chefe=self.vinculo_chefe_imediato.pessoa.nome,
                acao=(acao_editada and 'manifestou-se novamente') or 'manifestou-se',
                abono=self.get_acao_abono_display(),
                descricao=self.descricao,
                frequencias=frequencias_da_pessoa,
                observacoes=observacoes_da_pessoa,
            )
            send_notification(assunto, mensagem, settings.DEFAULT_FROM_EMAIL, [self.vinculo_pessoa], categoria='Avaliação da Frequência do Dia')

    def pode_visualizar_avaliacao(self, user_requisitante: User) -> bool:
        return self.can_view(user_requisitante)

    def pode_solicitar_revisao_avaliacao(self, user_requisitante: User) -> bool:
        return self.vinculo_pessoa.user == user_requisitante

    def pode_editar_avaliacao(self, user_requisitante: User) -> bool:
        vinculo_requisitante = user_requisitante.get_vinculo()
        servidor_requisitante = user_requisitante.get_relacionamento()
        servidor_inconsistencia = self.vinculo_pessoa.relacionamento
        setor_inconsistencia = servidor_inconsistencia.setor_suap_servidor_no_dia(self.data)

        pode_editar = servidor_requisitante != servidor_inconsistencia and (
            self.vinculo_chefe_imediato == vinculo_requisitante
            or servidor_requisitante.eh_chefe_do_setor_periodo(setor_inconsistencia, self.data, self.data)
        )

        return pode_editar

    def delete(self, *args, **kwargs):
        abono_parcial = self.solicitacao_abono_parcial
        if abono_parcial:
            # cancela avaliação
            abono_parcial.resetar_avaliacao()
        super().delete(*args, **kwargs)

    @property
    def display(self):
        display = f'Dia {self.data.strftime("%d/%m/%Y")} | Avaliado por {self.vinculo_chefe_imediato.relacionamento} em {self.ultima_atualizacao.strftime("%d/%m/%Y %H:%M:%S")} | {self.get_acao_abono_display()}{f": {self.descricao}" if self.descricao else ""}'
        if self.solicitacao_abono_parcial:
            display = f'{display} ({self.solicitacao_abono_parcial.ch_solicitada_display_2} parcial)'
        if self.ch_descontada:
            display = f'{display} ({self.ch_descontada_display_2} desconto)'
        return display

    @staticmethod
    def get_abonos_chefia(
        vinculo: Vinculo,
        data_inicio: datetime.date,
        data_fim: datetime.date,
    ) -> dict[datetime.date, list]:
        result: dict[datetime.date, list] = {}

        for data in datas_entre(data_inicio, data_fim):
            result[data] = []

        abonos = AbonoChefia.objects.filter(vinculo_pessoa=vinculo, data__gte=data_inicio, data__lte=data_fim)
        for abono in abonos:
            result[abono.data].append(abono)

        return result

    @staticmethod
    def get_solicitacoes_revisao_abono_chefia(
        vinculo_solicitante: Vinculo | None = None,
        vinculo_avaliador: Vinculo | None = None,
        situacao: int | None = None,
    ) -> models.QuerySet[SolicitacaoRevisaoAbonoChefia]:
        solicitacoes = SolicitacaoRevisaoAbonoChefia.objects.select_related(
            'vinculo_solicitante',
            'vinculo_chefe_imediato',
            'abono_chefia',
        )

        if situacao:
            solicitacoes = solicitacoes.filter(situacao=situacao)

        if vinculo_solicitante or vinculo_avaliador:
            if vinculo_solicitante:
                solicitacoes = solicitacoes.filter(vinculo_solicitante=vinculo_solicitante)

            if vinculo_avaliador:
                hoje = datetime.date.today()
                if vinculo_avaliador.eh_servidor():
                    avaliador_eh_chefe_hoje_setores_ids = vinculo_avaliador.relacionamento.historico_funcao(hoje, hoje).values_list(
                        'setor_suap__id', flat=True
                    )
                else:
                    avaliador_eh_chefe_hoje_setores_ids = []
                solicitacoes = solicitacoes.filter(
                    models.Q(vinculo_chefe_imediato=vinculo_avaliador)
                    | models.Q(abono_chefia__vinculo_chefe_imediato=vinculo_avaliador)
                    | models.Q(vinculo_solicitante__setor__id__in=avaliador_eh_chefe_hoje_setores_ids)
                    | models.Q(vinculo_solicitante__setor__superior__id__in=avaliador_eh_chefe_hoje_setores_ids)
                )
        else:
            solicitacoes = solicitacoes.none()

        return solicitacoes

    @staticmethod
    def pode_solicitar_abono_parcial(
        vinculo: Vinculo,
        data_inicio: datetime.date,
        data_fim: datetime.date,
        contexto_compensacao=None,
    ) -> dict[datetime.date, bool]:
        from ponto.compensacao import Contexto

        result: dict[datetime.date, bool] = {}

        for data in datas_entre(data_inicio, data_fim):
            result[data] = False

        if SolicitacaoAbonoParcial.solicitacao_abono_parcial_ativada():
            ponto_contexto = contexto_compensacao or Contexto(vinculo.relacionamento, data_inicio, data_fim)
            inconsistencias = Frequencia.get_inconsistencias(vinculo, data_inicio, data_fim, ponto_contexto)
            for data in datas_entre(data_inicio, data_fim):
                ponto_contexto_situacao_dia = ponto_contexto.get_dia(data, True)
                dia_com_inconsistencias = len(inconsistencias.get(data, [])) > 0
                dia_com_debito_restante = ponto_contexto_situacao_dia.debito_qtd_restante > 0
                result[data] = dia_com_inconsistencias and dia_com_debito_restante

        return result

    @staticmethod
    def pode_solicitar_revisao_abono_chefia(
        vinculo: Vinculo,
        data_inicio: datetime.date,
        data_fim: datetime.date,
        contexto_compensacao=None,
    ) -> dict[datetime.date, bool]:
        from ponto.compensacao import Contexto

        result: dict[datetime.date, bool] = {}

        for data in datas_entre(data_inicio, data_fim):
            result[data] = False

        if SolicitacaoAbonoParcial.solicitacao_abono_parcial_ativada():
            ponto_contexto = contexto_compensacao or Contexto(vinculo.relacionamento, data_inicio, data_fim)
            inconsistencias = Frequencia.get_inconsistencias(vinculo, data_inicio, data_fim, ponto_contexto)
            for data in datas_entre(data_inicio, data_fim):
                ponto_contexto_situacao_dia = ponto_contexto.get_dia(data, True)
                dia_com_inconsistencias = len(inconsistencias.get(data, [])) > 0
                dia_com_abonos = len(ponto_contexto_situacao_dia.abonos_do_dia) > 0
                result[data] = dia_com_inconsistencias and dia_com_abonos

        return result

    @staticmethod
    def adiciona_solicitacao_revisao_abono_chefia(
        vinculo_solicitante: Vinculo, abono_chefia: AbonoChefia, justificativa: str, commit: bool = True
    ) -> SolicitacaoRevisaoAbonoChefia:
        if not AbonoChefia.pode_solicitar_revisao_abono_chefia(vinculo_solicitante, abono_chefia.data, abono_chefia.data):
            raise PontoException(
                f'{vinculo_solicitante.relacionamento}: não é possível solicitar uma revisão de abono de chefia para o dia {abono_chefia.data.strftime("%d/%m/%Y")}.'
            )

        nova_solicitacao = SolicitacaoRevisaoAbonoChefia()
        nova_solicitacao.vinculo_solicitante = vinculo_solicitante
        nova_solicitacao.abono_chefia = abono_chefia
        nova_solicitacao.justificativa = justificativa

        nova_solicitacao.abono_chefia_display = abono_chefia.display
        nova_solicitacao.abono_chefia_data = abono_chefia.data

        if commit:
            nova_solicitacao.save()

        return nova_solicitacao

    @staticmethod
    def altera_solicitacao_revisao_abono_chefia(
        solicitacao: SolicitacaoRevisaoAbonoChefia, justificativa: str, commit: bool = True
    ) -> SolicitacaoRevisaoAbonoChefia:
        vinculo_solicitante = solicitacao.vinculo_solicitante
        abono_chefia = solicitacao.abono_chefia

        if abono_chefia:
            abono_chefia_data = abono_chefia.data
        else:
            abono_chefia_data = solicitacao.abono_chefia_data

        if not AbonoChefia.pode_solicitar_revisao_abono_chefia(vinculo_solicitante, abono_chefia_data, abono_chefia_data):
            raise PontoException(
                f'{vinculo_solicitante.relacionamento} não tem permissão para solicitar uma revisão de abono de chefia para o dia {abono_chefia_data.strftime("%d/%m/%Y")}.'
            )

        solicitacao.justificativa = justificativa

        if abono_chefia:
            solicitacao.abono_chefia_display = abono_chefia.display
            solicitacao.abono_chefia_data = abono_chefia.data

        if commit:
            solicitacao.save()

        return solicitacao

    @staticmethod
    def avalia_solicitacao_revisao_abono_chefia(
        solicitacao: SolicitacaoRevisaoAbonoChefia,
        vinculo_chefe_imediato: Vinculo,
        chefe_imediato_observacoes: str | None = None,
        commit: bool = True,
    ) -> SolicitacaoRevisaoAbonoChefia:
        permissoes = AbonoChefia.get_permissoes_solicitacao_revisao_abono_chefia(vinculo_chefe_imediato, solicitacao)
        if not permissoes.get('pode_avaliar') and not permissoes.get('pode_editar_avaliacao'):
            raise PontoException(
                f'{vinculo_chefe_imediato.relacionamento} não tem permissão para avaliar esta solicitação de revisão de abono de chefia.'
            )

        solicitacao.situacao = SolicitacaoRevisaoAbonoChefia.SITUACAO_AVALIADO
        solicitacao.vinculo_chefe_imediato = vinculo_chefe_imediato
        solicitacao.chefe_imediato_observacoes = chefe_imediato_observacoes

        if commit:
            solicitacao.save()

        return solicitacao

    @staticmethod
    def get_permissoes_solicitacao_revisao_abono_chefia(
        vinculo_requisitante: Vinculo,
        solicitacao: SolicitacaoRevisaoAbonoChefia,
    ) -> dict[str, bool]:
        # o requisitante é quem solicitou
        eh_quem_solicitou = solicitacao.vinculo_solicitante == vinculo_requisitante

        # chefes hoje
        hoje = datetime.date.today()
        if solicitacao.vinculo_solicitante.eh_servidor():
            quem_solicitou_chefes_hoje = solicitacao.vinculo_solicitante.relacionamento.get_chefes_no_periodo(hoje, hoje).get(hoje)
        else:
            quem_solicitou_chefes_hoje = []

        # o requisitante ...
        eh_o_chefe_imediato = (
            # é o chefe imediato da solicitação
            solicitacao.vinculo_chefe_imediato == vinculo_requisitante
            # é o chefe imediato do abono de chefia revisado
            or (solicitacao.abono_chefia and solicitacao.abono_chefia.vinculo_chefe_imediato == vinculo_requisitante)
            # é o chefe imediato hoje
            or vinculo_requisitante.relacionamento in quem_solicitou_chefes_hoje
        )

        pode_visualizar = eh_quem_solicitou or eh_o_chefe_imediato

        pode_editar = eh_quem_solicitou and solicitacao.situacao == SolicitacaoRevisaoAbonoChefia.SITUACAO_PENDENTE

        pode_avaliar = solicitacao.abono_chefia and eh_o_chefe_imediato and solicitacao.situacao == SolicitacaoRevisaoAbonoChefia.SITUACAO_PENDENTE
        pode_editar_avaliacao = (
            solicitacao.abono_chefia and eh_o_chefe_imediato and solicitacao.situacao == SolicitacaoRevisaoAbonoChefia.SITUACAO_AVALIADO
        )

        pode_remover = eh_quem_solicitou and solicitacao.situacao == SolicitacaoRevisaoAbonoChefia.SITUACAO_PENDENTE

        return {
            'requisitante_eh_quem_solicitou': eh_quem_solicitou,
            'chefes_hoje_de_quem_solicitou': quem_solicitou_chefes_hoje,
            'requisitante_eh_o_chefe_imediato': eh_o_chefe_imediato,
            'pode_visualizar': pode_visualizar,
            'pode_editar': pode_editar,
            'pode_avaliar': pode_avaliar,
            'pode_editar_avaliacao': pode_editar_avaliacao,
            'pode_remover': pode_remover,
        }

    @staticmethod
    def processa_abono_chefia_salvo(**kwargs):
        abono_chefia = kwargs.get('instance')

        # atualiza todas as solicitações pendentes de revisão de abono de chefia relacionadas
        solicitacoes = SolicitacaoRevisaoAbonoChefia.objects.filter(
            abono_chefia=abono_chefia, situacao=SolicitacaoRevisaoAbonoChefia.SITUACAO_PENDENTE
        )
        for solicitacao in solicitacoes:
            solicitacao.abono_chefia_display = abono_chefia.display
            solicitacao.abono_chefia_data = abono_chefia.data
            solicitacao.save()


class SolicitacaoAbonoParcial(ModelPlus):
    MOTIVO_CONSULTA_SAUDE = 1
    MOTIVO_ESQUECIMENTO_FREQUENCIA = 2
    MOTIVO_HORARIO_INTERVALO = 3
    MOTIVO_SIASS = 4
    MOTIVO_OUTROS = 5

    MOTIVO_CHOICES = [
        [MOTIVO_CONSULTA_SAUDE, 'Ida à consulta de saúde ou acompanhamento de dependente à consulta de saúde'],
        [MOTIVO_ESQUECIMENTO_FREQUENCIA, 'Esquecimento de registro de frequência'],
        [MOTIVO_HORARIO_INTERVALO, 'Horário de descanso/refeição'],
        [MOTIVO_SIASS, 'SIASS'],
        [MOTIVO_OUTROS, 'Outros'],
    ]

    MOTIVO_CONSULTA_SAUDE_COMO_PACIENTE = 11
    MOTIVO_CONSULTA_SAUDE_ACOMPANHAR_GRAVIDEZ = 12

    MOTIVO_CONSULTA_SAUDE_CHOICES = [
        [MOTIVO_CONSULTA_SAUDE_COMO_PACIENTE, 'Ida à consulta de saúde como paciente'],
        [MOTIVO_CONSULTA_SAUDE_ACOMPANHAR_GRAVIDEZ, 'Ida à consulta de saúde para acompanhar esposa ou companheira em período de gravidez'],
    ]

    ABONO_COM_COMPENSACAO = 1
    ABONO_SEM_COMPENSACAO = 2

    ABONO_CHOICES = [
        [ABONO_COM_COMPENSACAO, 'Abonar COM compensação de horário'],
        [ABONO_SEM_COMPENSACAO, 'Abonar SEM compensação de horário'],
    ]

    SITUACAO_PENDENTE = 1
    SITUACAO_AVALIADO = 2

    SITUACAO_CHOICES = [
        [SITUACAO_PENDENTE, 'Pendente'],
        [SITUACAO_AVALIADO, 'Avaliado'],
    ]

    data_solicitacao = models.DateTimeField(auto_now_add=True, editable=False)
    # solicitante e data de aplicação
    vinculo_pessoa = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Servidor', editable=False, on_delete=models.CASCADE)
    data_aplicacao = models.DateFieldPlus('Data da Aplicação', help_text='É a data que contém inconsistências.')
    # motivo da solicitação
    motivo = models.PositiveIntegerField('Motivo da Solicitação', default=MOTIVO_OUTROS, choices=MOTIVO_CHOICES)
    # acompanhar esposa ou companheira grávida
    acompanhamento_gravidez = models.ForeignKeyPlus(
        'ponto.SolicitacaoAbonoParcialGravidez',
        verbose_name='Gravidez de Esposa ou Companheira',
        blank=True,
        null=True,
        on_delete=models.CASCADE,
        help_text='Apenas para o motivo de ida à consulta de saúde para acompanhar esposa ou companheira durante o período de gravidez.',
    )
    acompanhamento_gravidez_qtd_consultas = models.PositiveIntegerField(
        'Qtd. de Consultas Médicas (Gravidez de Esposa ou Companheira)',
        help_text='Apenas para o motivo de ida à consulta de saúde para acompanhar esposa ou companheira durante o período de gravidez.',
        blank=True,
        null=True,
        default=0,
    )
    # detalhamento da solicitação
    descricao = models.TextField('Descrição', max_length=200)
    arquivo = models.PrivateFileField(
        'Arquivo',
        upload_to='ponto/anexos',
        filetypes=['pdf', 'jpeg', 'jpg', 'png'],
        help_text='O formato do arquivo deve ser ".pdf", ".jpeg", ".jpg" ou ".png"',
        blank=True,
        null=True,
    )
    ch_solicitada = models.PositiveIntegerField('Carga Horária a Abonar', help_text='Em segundos.')
    abono_solicitado = models.PositiveIntegerField('Abono Solicitado', default=ABONO_SEM_COMPENSACAO, choices=ABONO_CHOICES)
    # situacão e avaliação do chefe imediato
    situacao = models.PositiveIntegerField('Situação', default=SITUACAO_PENDENTE, choices=SITUACAO_CHOICES)
    vinculo_chefe_imediato = models.ForeignKeyPlus(
        'comum.Vinculo', related_name='abono_parcial_chefe_imediato_set', editable=False, null=True, on_delete=models.CASCADE
    )
    ch_solicitada_alteracoes_chefe_imediato = models.TextField(
        'Histórico de alterações da Carga Horária a Abonar realizadas pelo Chefe Imediato', editable=False, null=True
    )
    # diversos
    data_atualizacao = models.DateTimeField(auto_now=True, editable=False)
    chefes_data_aplicacao = models.ManyToManyField(
        'comum.Vinculo',
        related_name='abono_parcial_chefes_data_aplicacao_set',
        editable=False,
        blank=True,
        verbose_name='Chefes na data de aplicação.',
    )

    class Meta:
        verbose_name = 'Solicitação de Abono Parcial'
        verbose_name_plural = 'Solicitações de Abono Parcial'

    def inicializar_chefes_data_aplicacao(self, gravar=True) -> list[Vinculo]:
        servidor: Servidor = self.vinculo_pessoa.relacionamento
        chefes = servidor.get_chefes_no_periodo(
            self.data_aplicacao,
            self.data_aplicacao,
        ).get(self.data_aplicacao)
        if self.vinculo_chefe_imediato:
            servidor_avaliou = self.vinculo_chefe_imediato.relacionamento
            if servidor_avaliou not in chefes:
                chefes.append(servidor_avaliou)
        chefes_vinculos = [chefe.get_vinculo() for chefe in chefes]
        if gravar:
            self.chefes_data_aplicacao.set(chefes_vinculos)
        return chefes_vinculos

    @staticmethod
    def solicitacao_abono_parcial_ativada():
        return Configuracao.get_valor_por_chave(app='rh', chave='permite_solicitacao_abono_parcial')

    def save(self, *args, **kwargs):
        save = super().save(*args, **kwargs)
        if not self.chefes_data_aplicacao.all().exists():
            self.inicializar_chefes_data_aplicacao()
        return save

    def delete(self, *args, **kwargs):
        if self.arquivo:
            self.arquivo.delete()
        super().delete(*args, **kwargs)

    def __str__(self):
        if self.abono_solicitado in [self.ABONO_COM_COMPENSACAO, self.ABONO_SEM_COMPENSACAO]:
            abono_solicitado_display = f'| {self.get_abono_solicitado_display()}'
        else:
            abono_solicitado_display = ''
        return f'{self.data_aplicacao.strftime("%d/%m/%Y")} - {self.get_motivo_display()}: {self.ch_solicitada_display} {abono_solicitado_display} | {self.get_situacao_display()}'

    def get_absolute_url(self):
        return f'/ponto/visualizar_abono_parcial/{self.id}/'

    def set_ch_abonada_chefe_imediato(self, ch_abonada_em_segundos: int, vinculo_chefe_imediato: Vinculo):
        ch_abonada_anterior = self.ch_solicitada
        self.ch_solicitada = ch_abonada_em_segundos
        if self.ch_solicitada != ch_abonada_anterior:
            self.ch_solicitada_alteracoes_chefe_imediato = ' '.join(
                [
                    f"{vinculo_chefe_imediato.relacionamento}, em {datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}, alterou a carga horária a abonar de '{formata_segundos_h_min_seg(ch_abonada_anterior)}' para '{formata_segundos_h_min_seg(self.ch_solicitada)}'.",
                    self.ch_solicitada_alteracoes_chefe_imediato or '',
                ]
            )

    @property
    def ch_solicitada_display(self):
        """?h ?min ?seg"""
        from ponto.compensacao import formatar_segundos

        return formatar_segundos(self.ch_solicitada, True, False)

    @property
    def ch_solicitada_display_2(self):
        """?:?:?"""
        from ponto.compensacao import formatar_segundos

        return formatar_segundos(self.ch_solicitada, False, False)

    @property
    def situacao_is_avaliado(self):
        return self.situacao == SolicitacaoAbonoParcial.SITUACAO_AVALIADO

    @property
    def get_situacao_display_html(self):
        status_css = 'status-finalizado'
        if self.situacao == SolicitacaoAbonoParcial.SITUACAO_PENDENTE:
            status_css = 'status-em-tramite'
        return mark_safe(f"<span class='status {status_css} text-nowrap-normal'>{self.get_situacao_display()}</span>")

    @classmethod
    def validar(cls, obj: SolicitacaoAbonoParcial, revalidar=False) -> list[str]:
        from ponto.compensacao import Contexto, formatar_segundos

        if revalidar and obj.id is None:
            return [f'A solicitação de abono parcial "{obj}" ainda não foi salva e não pode ser validada novamente.']

        errors: list[str] = []

        servidor = obj.vinculo_pessoa.relacionamento if obj.vinculo_pessoa else None
        dia = obj.data_aplicacao or None

        if servidor and dia:
            contexto_compensacao = Contexto(servidor, dia, dia)

            if not obj.situacao_is_avaliado:
                # uma vez avaliado, o débito do dia é recalculado e não mais é o mesmo antes da avaliação

                inconsistencias = Frequencia.get_inconsistencias(obj.vinculo_pessoa, dia, dia, contexto_compensacao).get(dia, [])
                dia_debito_restante = contexto_compensacao.get_dia(dia).debito_qtd_restante

                # 1) o dia deve ter inconsistências
                if not inconsistencias:
                    errors.append(f'O dia {dia.strftime("%d/%m/%Y")} não tem inconsistências.')

                # 2) o dia deve ter débito pendente de CH
                if not dia_debito_restante:
                    errors.append(f'O dia {dia.strftime("%d/%m/%Y")} não tem débito pendente de carga horária.')

                # 3) a ch solicitada deve ser menor ou igual ao débito pendente de CH
                if obj.ch_solicitada > dia_debito_restante:
                    errors.append(
                        f'A carga horária solicitada a abonar ({formatar_segundos(obj.ch_solicitada, True)}) é maior que o débito pendente do dia {dia.strftime("%d/%m/%Y")} ({formatar_segundos(dia_debito_restante, True)}).'
                    )

                # 4) a soma (ch solicitada + ch solicitada das solicitações pendentes do mesmo dia) deve ser menor ou igual ao débito pendente de CH
                ch_solicitada_pendente = 0
                solicitacoes_pendentes = SolicitacaoAbonoParcial.query_minhas_solicitacoes_pendentes(obj.vinculo_pessoa.user).filter(
                    data_aplicacao=dia
                )
                for solicitacao_pendente in solicitacoes_pendentes:
                    if revalidar and solicitacao_pendente.id == obj.id:
                        # não processa a solicitação que está sendo revalidada
                        continue
                    ch_solicitada_pendente += solicitacao_pendente.ch_solicitada
                if solicitacoes_pendentes.exists() and ch_solicitada_pendente and (obj.ch_solicitada + ch_solicitada_pendente) > dia_debito_restante:
                    errors.append(
                        f'A carga horária solicitada a abonar ({formatar_segundos(obj.ch_solicitada, True)}), somada com a carga horária já solicitada e pendente ({formatar_segundos(ch_solicitada_pendente, True)}), é maior que o débito pendente do dia {dia.strftime("%d/%m/%Y")} ({formatar_segundos(dia_debito_restante, True)}).'
                    )

            # 5) valida solicitação 'ida à consulta de saúde'
            errors += obj.validar_ida_consulta_saude(contexto_compensacao)
        else:
            errors.append('Um abono parcial deve ter um vínculo de pessoa e uma data de aplicação.')

        return errors

    def validar_ida_consulta_saude(self, contexto_compensacao=None) -> list[str]:
        from ponto.compensacao import Contexto, formatar_segundos

        errors: list[str] = []

        # acompanhamento gravidez
        acompanhamento_gravidez = self.acompanhamento_gravidez
        acompanhamento_gravidez_qtd_consultas = self.acompanhamento_gravidez_qtd_consultas or 0

        if (acompanhamento_gravidez or acompanhamento_gravidez_qtd_consultas) and self.motivo != SolicitacaoAbonoParcial.MOTIVO_CONSULTA_SAUDE:
            errors.append(
                'Informe a gravidez e também a quantidade de consultas médicas apenas no caso de motivo de ida à consulta de saúde para acompanhar esposa ou companheira durante o período de gravidez.'
            )

        if not errors:
            if acompanhamento_gravidez and not acompanhamento_gravidez_qtd_consultas:
                errors.append('Gravidez de Esposa ou Companheira: Informe a quantidade de consultas médicas (você informou apenas a gravidez).')
            if not acompanhamento_gravidez and acompanhamento_gravidez_qtd_consultas:
                errors.append('Gravidez de Esposa ou Companheira: Informe a gravidez (você informou apenas a quantidade de consultas médicas).')

        # ida à consulta de saúde com abono SEM compensação (um direito) nos limites legais
        if (
            not errors
            and self.motivo == SolicitacaoAbonoParcial.MOTIVO_CONSULTA_SAUDE
            and self.abono_solicitado == SolicitacaoAbonoParcial.ABONO_SEM_COMPENSACAO
        ):
            """
                INSTRUÇÃO NORMATIVA SRT/MGI Nº 34, DE 17 DE NOVEMBRO DE 2023, Art. 13

                Sobre os limites anuais para abonos SEM compensação no contexto de consulta de saúde:
                    - CH do dia 8h: limite de 54 horas anuais
                    - CH do dia 6h: limite de 43 horas anuais
                    - CH do dia 4h: limite de 32 horas anuais
                    - Acompanhamento de esposa em período de gravidez: limite de até 6 consultas durante o período
            """

            acompanhamento_gravidez_informado = acompanhamento_gravidez and acompanhamento_gravidez_qtd_consultas

            servidor = self.vinculo_pessoa.relacionamento
            ano = self.data_aplicacao.year
            ch_solicitada_segundos = self.ch_solicitada

            contexto_compensacao = contexto_compensacao or Contexto(servidor, self.data_aplicacao, self.data_aplicacao)
            ch_diaria_segundos = contexto_compensacao.get_dia(self.data_aplicacao, add_se_nao_existir=True).carga_horaria_inicial_qtd
            ch_diaria_horas = ch_diaria_segundos / 3600

            limite_qtd_consultas_por_gravidez = SolicitacaoAbonoParcial.consulta_saude_limite_qtd_consultas_por_gravidez()
            limites_anuais_por_ch_diaria = SolicitacaoAbonoParcial.consulta_saude_limites_anuais_por_ch_diaria()

            historico_qtd_consultas_gravidez = 0
            if acompanhamento_gravidez_informado:
                historicos_gravidez = SolicitacaoAbonoParcial.consulta_saude_limite_qtd_consultas_por_gravidez_historico(servidor)
                for historico in historicos_gravidez:
                    # por gravidez
                    if historico.gravidez == acompanhamento_gravidez:
                        historico_qtd_consultas_gravidez = historico.qtd_consultas
                        break
                if self.situacao_is_avaliado:
                    historico_qtd_consultas_gravidez -= acompanhamento_gravidez_qtd_consultas

            historico_limites_anuais_ch_diaria_segundos = 0
            if not acompanhamento_gravidez_informado:
                historicos_limites_anuais = SolicitacaoAbonoParcial.consulta_saude_limites_anuais_por_ch_diaria_historico(servidor).values()
                for historico in historicos_limites_anuais:
                    # por ano
                    if historico.ano == ano:
                        historico_limites_anuais_ch_diaria_segundos = historico.ch_abonada_sem_compensacao
                        break
                if self.situacao_is_avaliado:
                    historico_limites_anuais_ch_diaria_segundos -= ch_solicitada_segundos

            historico_qtd_consultas_gravidez_a_testar = historico_qtd_consultas_gravidez + acompanhamento_gravidez_qtd_consultas
            historico_limites_anuais_ch_diaria_segundos_a_testar = historico_limites_anuais_ch_diaria_segundos + ch_solicitada_segundos

            if acompanhamento_gravidez_informado:
                limite_ok_gravidez = historico_qtd_consultas_gravidez_a_testar <= limite_qtd_consultas_por_gravidez

                if not limite_ok_gravidez:
                    errors.append(
                        f'O limite de {limite_qtd_consultas_por_gravidez} consultas médicas para acompanhar a gravidez "{acompanhamento_gravidez}" foi ultrapassado. Para mais informações, acesse "Acompanhamento de Histórico".'
                    )
            else:
                limite_ok_ch_diaria = (
                    (ch_diaria_horas == 8 and historico_limites_anuais_ch_diaria_segundos_a_testar <= limites_anuais_por_ch_diaria[8])
                    or (ch_diaria_horas == 6 and historico_limites_anuais_ch_diaria_segundos_a_testar <= limites_anuais_por_ch_diaria[6])
                    or (ch_diaria_horas == 4 and historico_limites_anuais_ch_diaria_segundos_a_testar <= limites_anuais_por_ch_diaria[4])
                )

                if not limite_ok_ch_diaria:
                    if ch_diaria_horas in [8, 6, 4]:
                        ch_a_solicitar_disponivel = limites_anuais_por_ch_diaria[ch_diaria_horas] - historico_limites_anuais_ch_diaria_segundos
                        errors.append(
                            f'O limite de {limites_anuais_por_ch_diaria[ch_diaria_horas] / 3600} horas em {ano} foi ultrapassado para a carga horária diária de {ch_diaria_horas}h. É possível solicitar até {formatar_segundos(ch_a_solicitar_disponivel, True)} em {ano}. Para mais informações, acesse "Acompanhamento de Histórico".'
                        )
                    else:
                        # TODO: seria necessário tratar cargas horárias diárias diferentes de 8, 6 e 4 (não há previsão legal)
                        errors.append(
                            f'{self.data_aplicacao.strftime("%d/%m/%Y")}: a carga horária de {ch_diaria_horas}h diária é inválida para fins de solicitação de abono parcial. Para mais informações, acesse "Acompanhamento de Histórico".'
                        )

        return errors

    @classmethod
    def consulta_saude_limite_qtd_consultas_por_gravidez(cls):
        return 6  # número de consultas médicas

    @classmethod
    def consulta_saude_limites_anuais_por_ch_diaria(cls):
        # {ch diária em horas: limite anual em segundos, ...}
        return {
            # 8h = 54h anuais
            8: 54 * 3600,
            # 6h = 43h anuais
            6: 43 * 3600,
            # 4h = 32h anuais
            4: 32 * 3600,
        }

    class ConsultaSaudeHistoricoGravidez:
        gravidez: SolicitacaoAbonoParcialGravidez
        qtd_consultas: int
        ch_abonada_sem_compensacao: int

        def __init__(self, gravidez: SolicitacaoAbonoParcialGravidez):
            self.gravidez = gravidez
            self.qtd_consultas = 0
            self.ch_abonada_sem_compensacao = 0

        @property
        def ch_abonada_sem_compensacao_display(self):
            from ponto.compensacao import formatar_segundos

            return formatar_segundos(self.ch_abonada_sem_compensacao, True)

    @classmethod
    def consulta_saude_limite_qtd_consultas_por_gravidez_historico(
        cls, servidor: Servidor
    ) -> list[SolicitacaoAbonoParcial.ConsultaSaudeHistoricoGravidez]:
        historico_por_gravidez: dict[SolicitacaoAbonoParcialGravidez, SolicitacaoAbonoParcial.ConsultaSaudeHistoricoGravidez] = {}

        for historico in SolicitacaoAbonoParcial.query_historicos_consulta_saude(servidor):
            if historico.solicitacao_abono_parcial.acompanhamento_gravidez:
                if historico.acao_abono == AbonoChefia.ABONADO:
                    gravidez = historico.solicitacao_abono_parcial.acompanhamento_gravidez
                    if gravidez not in historico_por_gravidez:
                        historico_por_gravidez[gravidez] = SolicitacaoAbonoParcial.ConsultaSaudeHistoricoGravidez(gravidez)
                    historico_por_gravidez[gravidez].qtd_consultas += historico.solicitacao_abono_parcial.acompanhamento_gravidez_qtd_consultas
                    historico_por_gravidez[gravidez].ch_abonada_sem_compensacao += historico.solicitacao_abono_parcial.ch_solicitada

        return historico_por_gravidez.values()

    class ConsultaSaudeHistoricoLimiteAnualCHDiaria:
        ano: int
        ch_abonada_sem_compensacao: int

        def __init__(self, ano: int):
            self.ano = ano
            self.ch_abonada_sem_compensacao = 0

        @property
        def ch_abonada_sem_compensacao_display(self):
            from ponto.compensacao import formatar_segundos

            return formatar_segundos(self.ch_abonada_sem_compensacao, True)

    @classmethod
    def consulta_saude_limites_anuais_por_ch_diaria_historico(
        cls, servidor: Servidor
    ) -> dict[int, SolicitacaoAbonoParcial.ConsultaSaudeHistoricoLimiteAnualCHDiaria]:
        historico_por_ano: dict[int, SolicitacaoAbonoParcial.ConsultaSaudeHistoricoLimiteAnualCHDiaria] = {}

        for historico in SolicitacaoAbonoParcial.query_historicos_consulta_saude(servidor):
            if not historico.solicitacao_abono_parcial.acompanhamento_gravidez:
                if historico.acao_abono == AbonoChefia.ABONADO:
                    ano = historico.solicitacao_abono_parcial.data_aplicacao.year
                    if ano not in historico_por_ano:
                        historico_por_ano[ano] = SolicitacaoAbonoParcial.ConsultaSaudeHistoricoLimiteAnualCHDiaria(ano)
                    historico_por_ano[ano].ch_abonada_sem_compensacao += historico.solicitacao_abono_parcial.ch_solicitada

        return historico_por_ano

    def pode_editar(self, user_requisitante: User) -> bool:
        requisitante_vinculo = user_requisitante.get_vinculo()
        return self.vinculo_pessoa == requisitante_vinculo and self.situacao == SolicitacaoAbonoParcial.SITUACAO_PENDENTE

    def pode_avaliar(self, user_requisitante: User) -> bool:
        chefe_vinculo = user_requisitante.get_vinculo()
        return any([self.vinculo_chefe_imediato == chefe_vinculo, chefe_vinculo in self.chefes_data_aplicacao.all()])

    def pode_remover(self, user_requisitante: User) -> bool:
        return self.pode_editar(user_requisitante)

    def pode_visualizar(self, user_requisitante: User) -> bool:
        requisitante_vinculo = user_requisitante.get_vinculo()
        return any(
            [
                self.vinculo_pessoa == requisitante_vinculo,
                self.vinculo_chefe_imediato == requisitante_vinculo,
                self.pode_avaliar(user_requisitante),
            ]
        )

    @property
    def abono_chefia(self) -> AbonoChefia:
        """retorna o abono de chefia criado após avaliação da solicitação de abono parcial"""
        if self.situacao_is_avaliado:
            return (
                AbonoChefia.objects.select_related(
                    'vinculo_pessoa',
                    'vinculo_chefe_imediato',
                    'solicitacao_abono_parcial',
                    'solicitacao_abono_parcial__vinculo_pessoa',
                    'solicitacao_abono_parcial__vinculo_chefe_imediato',
                )
                .filter(solicitacao_abono_parcial=self)
                .first()
            )
        return None

    def get_abono_chefia_display_html(self, abono_chefia: AbonoChefia):
        if abono_chefia:
            return mark_safe(
                f"<span class='status status-{abono_chefia.get_acao_abono_display_css()} text-nowrap-normal'>{abono_chefia.get_acao_abono_display()}</span>"
            )
        return '-'

    def resetar_avaliacao(self):
        self.situacao = SolicitacaoAbonoParcial.SITUACAO_PENDENTE
        self.vinculo_chefe_imediato = None
        self.save()

    ###
    # queries

    @classmethod
    def query_base(cls) -> QuerySet[SolicitacaoAbonoParcial]:
        return SolicitacaoAbonoParcial.objects.select_related('vinculo_pessoa', 'vinculo_chefe_imediato')

    @classmethod
    def query_minhas_solicitacoes(cls, user_eu: User) -> QuerySet[SolicitacaoAbonoParcial]:
        meu_vinculo = user_eu.get_vinculo()
        return cls.query_base().filter(vinculo_pessoa=meu_vinculo)

    @classmethod
    def query_solicitacoes_terceiros(cls, user_requisitante: User) -> QuerySet[SolicitacaoAbonoParcial]:
        """Escopo das solicitações:
        - `user_requisitante` foi o avaliador da solicitação;
        - `user_requisitante` foi o chefe do setor do servidor
        na data da aplicação da solicitação;
        """

        chefe_vinculo = user_requisitante.get_vinculo()

        solicitacoes = cls.query_base().filter(
            # O chefe já avaliou.
            Q(vinculo_chefe_imediato=chefe_vinculo)
            # O chefe foi chefe na data de aplicação.
            | Q(chefes_data_aplicacao=chefe_vinculo)
        )

        return solicitacoes

    @classmethod
    def query_minhas_solicitacoes_pendentes(cls, user_eu: User) -> QuerySet[SolicitacaoAbonoParcial]:
        return cls.query_minhas_solicitacoes(user_eu).filter(situacao__in=[SolicitacaoAbonoParcial.SITUACAO_PENDENTE])

    @classmethod
    def query_solicitacoes_terceiros_pendentes(cls, user_requisitante: User) -> QuerySet[SolicitacaoAbonoParcial]:
        return cls.query_solicitacoes_terceiros(user_requisitante).filter(situacao__in=[SolicitacaoAbonoParcial.SITUACAO_PENDENTE])

    @classmethod
    def query_solicitacoes_terceiros_avaliadas(cls, user_requisitante: User) -> QuerySet[SolicitacaoAbonoParcial]:
        return cls.query_solicitacoes_terceiros(user_requisitante).filter(situacao__in=[SolicitacaoAbonoParcial.SITUACAO_AVALIADO])

    @classmethod
    def query_solicitacoes_pendentes(cls, servidor: Servidor, motivo: int | None = None) -> QuerySet[SolicitacaoAbonoParcial]:
        qs_pendentes = cls.query_base().filter(vinculo_pessoa=servidor.get_vinculo(), situacao__in=[SolicitacaoAbonoParcial.SITUACAO_PENDENTE])
        if motivo:
            qs_pendentes = qs_pendentes.filter(motivo=motivo)
        return qs_pendentes

    @classmethod
    def query_historicos(cls, servidor: Servidor) -> QuerySet[AbonoChefia]:
        return AbonoChefia.objects.select_related(
            'vinculo_pessoa',
            'vinculo_chefe_imediato',
            'solicitacao_abono_parcial',
            'solicitacao_abono_parcial__vinculo_pessoa',
            'solicitacao_abono_parcial__vinculo_chefe_imediato',
            'solicitacao_abono_parcial__acompanhamento_gravidez',
        ).filter(
            solicitacao_abono_parcial__vinculo_pessoa=servidor.get_vinculo(),
        )

    @classmethod
    def query_historicos_consulta_saude(cls, servidor: Servidor) -> QuerySet[AbonoChefia]:
        return AbonoChefia.objects.select_related(
            'vinculo_pessoa',
            'vinculo_chefe_imediato',
            'solicitacao_abono_parcial',
            'solicitacao_abono_parcial__vinculo_pessoa',
            'solicitacao_abono_parcial__vinculo_chefe_imediato',
            'solicitacao_abono_parcial__acompanhamento_gravidez',
        ).filter(
            solicitacao_abono_parcial__vinculo_pessoa=servidor.get_vinculo(),
            solicitacao_abono_parcial__motivo=SolicitacaoAbonoParcial.MOTIVO_CONSULTA_SAUDE,
        )

    ###


class SolicitacaoAbonoParcialGravidez(ModelPlus):
    """
    Períodos de gravidez de esposa ou companheira para fins de aplicar
    os limites legais para quantidade de consultas médicas para acompanhar a
    grávida sem a necessidade de compensar carga horária.
    """

    vinculo_pessoa = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Servidor', editable=False, on_delete=models.CASCADE)
    nome_gravida = models.CharField('Nome da Esposa ou Companheira', max_length=255)
    descricao = models.TextField('Descrição da Gravidez', max_length=255, blank=True, null=True)
    arquivo = models.PrivateFileField(
        'Arquivo',
        upload_to='ponto/anexos',
        filetypes=['pdf', 'jpeg', 'jpg', 'png'],
        help_text='O formato do arquivo deve ser ".pdf", ".jpeg", ".jpg" ou ".png"',
        blank=True,
        null=True,
    )

    class Meta:
        verbose_name = 'Gravidez de Esposa ou Companheira'
        verbose_name_plural = 'Gravidez de Esposa ou Companheira'

    def delete(self, *args, **kwargs):
        if self.arquivo:
            self.arquivo.delete()
        super().delete(*args, **kwargs)

    def __str__(self):
        return f'{self.nome_gravida}{(": " + self.descricao) if self.descricao else ""}'

    def pode_visualizar(self, user_requisitante: User) -> bool:
        requisitante_vinculo = user_requisitante.get_vinculo()
        pode_visualizar = self.vinculo_pessoa == requisitante_vinculo
        if not pode_visualizar:
            # foi chefe validador nas solicitações de abonos parciais relacionadas ?
            chefes_vinculos_ids_nos_abonos_parciais = SolicitacaoAbonoParcial.objects.filter(
                acompanhamento_gravidez=self, vinculo_chefe_imediato__isnull=False
            ).values_list('vinculo_chefe_imediato_id', flat=True)
            pode_visualizar = requisitante_vinculo.id in chefes_vinculos_ids_nos_abonos_parciais
        if not pode_visualizar:
            # é chefe hoje no caso de haver solicitações de abonos parciais pendentes relacionadas ?
            abonos_parciais_pendentes = SolicitacaoAbonoParcial.objects.filter(
                acompanhamento_gravidez=self, situacao=SolicitacaoAbonoParcial.SITUACAO_PENDENTE
            )
            if abonos_parciais_pendentes.exists():
                hoje = datetime.date.today()
                vinculos_chefes_hoje = [
                    chefe.get_vinculo() for chefe in self.vinculo_pessoa.relacionamento.get_chefes_no_periodo(hoje, hoje).get(hoje)
                ]
                pode_visualizar = requisitante_vinculo in vinculos_chefes_hoje
        return pode_visualizar

    def get_absolute_url(self):
        return f'/ponto/visualizar_abono_parcial_gravidez/{self.id}/'


class SolicitacaoRevisaoAbonoChefia(ModelPlus):
    SITUACAO_PENDENTE = 1
    SITUACAO_AVALIADO = 2

    SITUACAO_CHOICES = [
        [SITUACAO_PENDENTE, 'Pendente'],
        [SITUACAO_AVALIADO, 'Avaliado'],
    ]

    data_solicitacao = models.DateTimeField(auto_now_add=True, editable=False)
    data_atualizacao = models.DateTimeField(auto_now=True, editable=False)

    vinculo_solicitante = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Servidor', editable=False, on_delete=models.CASCADE, related_name='revisao_abono_chefia_solicitante_set'
    )
    abono_chefia = models.ForeignKeyPlus(
        'ponto.AbonoChefia', verbose_name='Abono de chefia revisado', editable=False, on_delete=models.SET_NULL, null=True
    )
    justificativa = models.TextField('Justificativa')

    # informações replicadas aqui ref. ao abono revisado
    abono_chefia_display = models.TextField(max_length=255, verbose_name='Abono de Chefia revisado')
    abono_chefia_data = models.DateField('Data do Abono de Chefia revisado')

    # situação e avaliação
    situacao = models.PositiveIntegerField('Situação', default=SITUACAO_PENDENTE, choices=SITUACAO_CHOICES)
    vinculo_chefe_imediato = models.ForeignKeyPlus(
        'comum.Vinculo', related_name='revisao_abono_chefia_chefe_imediato_set', editable=False, null=True, on_delete=models.CASCADE
    )
    chefe_imediato_observacoes = models.TextField('Observações do Chefe Imediato', null=True, blank=True)

    class Meta:
        verbose_name = 'Solicitação de Revisão de Abono de Chefia'
        verbose_name_plural = 'Solicitações de Revisão de Abono de Chefia'

    def get_absolute_url(self):
        return f'/ponto/visualizar_revisao_abono_chefia/{self.pk}/'

    @property
    def situacao_is_avaliado(self):
        return self.situacao == SolicitacaoRevisaoAbonoChefia.SITUACAO_AVALIADO

    def get_acao_chefe_display(self):
        if not self.situacao_is_avaliado:
            return ''
        if not self.abono_chefia:
            return 'O abono foi removido.'
        if self.abono_chefia.display != self.abono_chefia_display:
            return 'O abono foi editado.'
        return 'O abono foi mantido.'

    def get_situacao_display_html(self):
        status = ''
        extra = ''
        if self.situacao == SolicitacaoRevisaoAbonoChefia.SITUACAO_PENDENTE:
            status = 'alert'
        if self.situacao == SolicitacaoRevisaoAbonoChefia.SITUACAO_AVALIADO:
            status = 'success'
            acao_chefe_display = self.get_acao_chefe_display()
            if acao_chefe_display:
                extra = f': {acao_chefe_display}'.lower()
        return mark_safe(f'<span class="status status-{status}">{self.get_situacao_display()}{extra}</span>')


class TipoAfastamento(models.ModelPlus):
    class Meta:
        verbose_name = 'Tipo de Afastamento'
        verbose_name_plural = 'Tipos de Afastamento'

    SEARCH_FIELDS = ['descricao', 'codigo']
    descricao = models.TextField(max_length=200, verbose_name='Descrição')
    # Ajustando para importar os afastamentos a partes das extracoes
    codigo = models.CharField(max_length=5, null=True, blank=True)

    def __str__(self):
        return self.descricao


class AfastamentoManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related('tipo')


class Afastamento(models.ModelPlus):
    """
    Representa os afastamentos cadastrados pelo RH.
    Estes sairão no relatório de frequências oficial.
    OBS: É possível que esteja duplicado com suap.ServidorOcorrencia do tipo
    `AFASTAMENTO`. Nesse caso, o RH deverá remover a duplicidade.
    """

    objects = AfastamentoManager()

    vinculo = models.ForeignKeyPlus('comum.Vinculo', on_delete=models.CASCADE)
    tipo = models.ForeignKeyPlus(TipoAfastamento, null=True, blank=True, on_delete=models.CASCADE)
    data_ini = models.DateFieldPlus('Data Inicial', db_index=True)
    data_fim = models.DateFieldPlus('Data Final', null=True, db_index=True)
    descricao = models.TextField('Descrição', max_length=200)

    @classmethod
    def buscar_afastamento_periodo(cls, vinculo, data_ini, data_fim):
        return cls.objects.filter(vinculo=vinculo, data_ini__lte=data_fim, data_fim__gte=data_ini)

    class Meta:
        verbose_name = 'Afastamento'
        verbose_name_plural = 'Afastamentos'

    def __str__(self):
        if self.tipo:
            return f'{self.tipo!s}: {self.descricao}'
        else:
            return self.descricao

    def get_absolute_url(self):
        return f'/admin/ponto/afastamento/{self.pk}/view/'

    @classmethod
    def buscar(cls, vinculo, data_ini, data_fim):
        return cls.objects.filter(vinculo=vinculo, data_ini__lte=data_fim, data_fim__gte=data_ini)

    @classmethod
    def buscar_afastamentos_parciais(cls, vinculo, data_ini, data_fim):
        """
        O objetivo é obter as instâncias de afastamentos que estão associadas a processos de afastamentos parciais.
        Infelizmente não há uma ligação (FK) entre Afastamento e Afastamento Parcial. Dessa forma será
        necessário usar o atributo 'tipo' de Afastamento e, baseado na descrição do tipo, determinar se o
        o afastamento é um afastamento parcial. Essa determinação deve ser feita em tempo de desenvolvimento de
        modo a 'descobrir' quais tipos de afastamentos fazem referência a afastamento parcial.

        Afastamento Parcial:
            Parecer/MP/CONJUR/FNF/Nº 1810 - 1.11/2009 e Orientação Normativa Nº 02/2016-DIGPE/IFRN

        Problema:
            O RH pode duplicar o cadastro de tipos de afastamentos que fazem referência a afastamento parcial.

        No momento (04/12/2018), há dois tipos cadastrados:
            Id 317
            Id 316
        """

        ids_tipos_afastamentos_parciais = [316, 317]  # hardcod mesmo !!!!!!!!!!!!

        return cls.objects.select_related('vinculo', 'tipo').filter(
            vinculo=vinculo, data_ini__lte=data_fim, data_fim__gte=data_ini, tipo_id__in=ids_tipos_afastamentos_parciais
        )


@receiver(post_save, sender=Afastamento)
def afastamento_post_save(sender, instance, **kwargs):
    vinculo_usuario = tl.get_user().get_vinculo() if tl.get_user() else None
    request = tl.get_request()
    if request and instance.vinculo == vinculo_usuario:
        # salva registro de alerta
        alerta = AlertaGestaoPessoa()
        alerta.tipo_acao = AlertaGestaoPessoa.ACAO_AFASTAMENTO
        alerta.vinculo_analizar = vinculo_usuario
        alerta.data_acao = datetime.datetime.now()
        alerta.registro_afetado = request.META.get('PATH_INFO')
        alerta.objeto = instance
        alerta.save()


##########################################################################################
# COMPENSAÇÃO DE HORÁRIO E RECESSOS
##########################################################################################


class HorarioCompensacao(models.Model):
    """Representa um informe de compensação de horário

    Por padrão, qualquer dia com saldo excedente pode ser usado para compensação de horário, informando o dia da
    compensação (o dia do saldo excedente), o dia compensado e a quantidade de carga horária compensada.

    Os informes de compensação poderão ser invalidados/sem efeito caso a chefia abone negativamente dias com saldos
    excedentes e dias com débitos.

    Um informe de compensação será invalidado, conforme abonos da chefia, nas seguintes situações:

    1) quando o dia da compensação (o dia do saldo excedente) receber os abonos:

        1.1) HORA EXTRA NÃO JUSTIFICADA: não considera o saldo excedente.
        1.2) HORA EXTRA JUSTIFICADA: não considera o saldo excedente, pois, nesse caso, os efeitos são apenas
        remuneratórios.
        1.3) TRABALHO FDS NÃO PERMITIDO: não considera o saldo excedente.
        1.4) TRABALHO FDS PERMITIDO COMO HORA EXTRA: não considera o saldo excedente, pois,	nesse caso, os
        efeitos são apenas remuneratórios.

    2) quando o dia compensado (o dia do débito) receber os abonos:

        2.1) NÃO ABONADO: o dia não poderá ser compensado, desconsiderando o débito.
        2.2) ABONADO: o dia não precisará ser compensado, desconsiderando o débito.
    """

    SITUACAO_VALIDO = 1
    SITUACAO_INVALIDO = 2
    SITUACAO_CHOICES = [[SITUACAO_VALIDO, 'Válido'], [SITUACAO_INVALIDO, 'Invalidado/Sem Efeito']]

    SALDO_MINIMO_EM_SEGUNDOS = 1
    DEBITO_MINIMO_EM_SEGUNDOS = 1

    funcionario = models.ForeignKeyPlus(
        'rh.Servidor', editable=False, verbose_name='Funcionário', related_name='funcionario_compensacao_horario', on_delete=models.CASCADE
    )

    data_aplicacao = models.DateFieldPlus('Data da Aplicação/Débito', help_text='Dia no qual há um débito de carga horária.')

    data_compensacao = models.DateFieldPlus('Data da Compensação/Saldo', help_text='Dia no qual há um saldo de carga horária.', null=True, blank=True)
    saldo_externo_compensacao = models.ForeignKeyPlus(
        'ponto.SaldoExterno', verbose_name='Saldo Externo Utilizado', help_text='Saldo externo utilizado nesta compensação.', null=True, blank=True
    )

    ch_compensada = models.TimeFieldPlus('Carga Horária Compensada', help_text='Formato: HH:MM.')

    chefe = models.ForeignKeyPlus(
        'rh.Servidor',
        editable=False,
        verbose_name='Chefe Imediato',
        help_text='Chefe Imediato na Data da Compensação',
        related_name='chefe_compensacao_horario',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    observacoes = models.TextField('Observações', null=True, blank=True)
    #
    # situação do informe de compensação em relação aos possíveis abonos que podem ocorrer
    abono_na_data_compensacao = models.ForeignKeyPlus(
        'ponto.AbonoChefia', null=True, blank=True, editable=False, related_name='abono_na_data_compensacao', on_delete=models.SET_NULL
    )  # exclui-se o abono, mas não o informe
    abono_na_data_aplicacao = models.ForeignKeyPlus(
        'ponto.AbonoChefia', null=True, blank=True, editable=False, related_name='abono_na_data_aplicacao', on_delete=models.SET_NULL
    )  # exclui-se o abono, mas não o informe
    situacao = models.IntegerField('Situação', choices=SITUACAO_CHOICES, default=SITUACAO_VALIDO, editable=False)

    class Meta:
        ordering = ('funcionario', '-data_aplicacao', '-data_compensacao')
        verbose_name = 'Informe de Compensação de Horário'
        verbose_name_plural = 'Informes de Compensação de Horário'
        indexes = [
            models.Index(
                fields=[
                    'funcionario',
                ],
                name='ponto_horariocompensV2_indexes',
            )
        ]

    def __str__(self):
        return 'Compensação de {} do dia {}. Carga Horária com origem em {}{}. Servidor: {}'.format(
            formata_segundos(Frequencia.time_para_segundos(self.ch_compensada), '{h}h', '{m}min', '', True),
            self.data_aplicacao.strftime('%d/%m/%Y'),
            self.data_compensacao.strftime('%d/%m/%Y') if self.data_compensacao else self.saldo_externo_compensacao,
            ' (Sábado)' if self.is_compensacao_no_sabado else '',
            self.funcionario,
        )

    @property
    def is_compensacao_no_sabado(self):
        if self.data_compensacao:
            return self.data_compensacao.weekday() == 5
        return False

    @property
    def frequencia_duracao(self):
        """duração da frequência na data da compensação em Time"""
        if self.data_compensacao:
            frequencias = Frequencia.get_frequencias_por_data(vinculo=self.funcionario.get_vinculo(), data=self.data_compensacao)
            return Frequencia.segundos_para_time(Frequencia.get_tempo_entre_frequencias(frequencias))
        return datetime.time(0, 0, 0)

    def set_chefe(self, save=True):
        # resolve o chefe imediato do funcionário na data da compensação
        self.chefe = None

        if self.data_compensacao:
            try:
                if not self.chefe:
                    servidor: Servidor = self.funcionario
                    servidor_chefe = servidor.chefes_na_data(data=self.data_compensacao)[0]
                    self.chefe = servidor_chefe
            except Exception:
                pass

        if save:
            self.save()

    def save(self, *args, **kwargs):
        self.set_chefe(save=False)
        return super().save(*args, **kwargs)

    def save_observacao_no_ponto(self, descricao_na_data_compensacao=None, descricao_na_data_aplicacao=None, commit=True):
        self.observacoes = ''

        observacoes = []

        if descricao_na_data_compensacao:
            observacoes.append(descricao_na_data_compensacao)

        if descricao_na_data_aplicacao:
            observacoes.append(descricao_na_data_aplicacao)

        if observacoes:
            self.observacoes = ' '.join(observacoes)

        if commit:
            self.save()

    def get_auto_obs_descricao_na_data_compensacao(self):
        return 'Carga horária de {} usada na compensação do dia {}'.format(
            formata_segundos(Frequencia.time_para_segundos(self.ch_compensada), '{h}h', '{m}min', '', True), self.data_aplicacao.strftime('%d/%m/%Y')
        )

    def get_auto_obs_descricao_na_data_aplicacao(self):
        if self.data_compensacao:
            return 'Carga horária de {} compensada no dia {}'.format(
                formata_segundos(Frequencia.time_para_segundos(self.ch_compensada), '{h}h', '{m}min', '', True),
                self.data_compensacao.strftime('%d/%m/%Y'),
            )
        return ''

    def get_absolute_url(self):
        return f'/ponto/abrir_compensacao_horario/{self.id}/'

    @staticmethod
    def is_dia_util(vinculo, data):
        """
        :return [True/False, ['infor extra', 'infor extra', 'infor extra', ...]]
        """
        from ponto.compensacao import SituacaoDia  # evitar import circular

        return SituacaoDia(vinculo.relacionamento, data).is_dia_util

    @staticmethod
    def inspecionar_informes_abono_chefia_salvo(sender, **kwargs):
        """
        Os informes de compensação poderão ser invalidados/sem efeito caso a chefia abone negativamente dias
        com saldos excedentes e dias com débitos.

        Um informe de compensação será invalidado, conforme abonos da chefia, nas seguintes situações:

        ATT: quando os abonos de chefia forem PARCIAIS, então NADA SERÁ FEITO NOS INFORMES DE COMPENSAÇÃO.
            - com isso, é possível que haja certas inconstências como por exemplo um dia com débito considerado
                de 3h e que já foi compensado 5h.
            - isso é possível pois o débito inicial (por ex: 5h) sofreu abonos parciais, por exemplo, de 2h sem compensação,
                e, nesse meio tempo de avaliação desses abonos, o servidor já havia compensado 5h.
            - nesse casos, é preferível que haja essa possível inconsistência que será de fácil solução por
                parte do próprio servidor que poderá remover esses informes e liberar o saldo.

        1) quando o dia da compensação (o dia do saldo excedente) receber os abonos:

            1.1) HORA EXTRA NÃO JUSTIFICADA: não considera o saldo excedente.
            1.2) HORA EXTRA JUSTIFICADA: não considera o saldo excedente, pois, nesse caso, os efeitos são apenas
            remuneratórios.
            1.3) TRABALHO FDS NÃO PERMITIDO: não considera o saldo excedente.
            1.4) TRABALHO FDS PERMITIDO COMO HORA EXTRA: não considera o saldo excedente, pois,	nesse caso, os
            efeitos são apenas remuneratórios.

        2) quando o dia compensado (o dia do débito) receber os abonos:

            2.1) NÃO ABONADO: o dia não poderá ser compensado, desconsiderando o débito.
            2.2) ABONADO: o dia não precisará ser compensado, desconsiderando o débito.

            Em ambos os casos, a carga horária compensada "voltará" para o dia do saldo excedente.
        """
        abono_chefia = kwargs.get('instance')
        if abono_chefia and not abono_chefia.eh_abono_parcial:
            informes = (
                (
                    HorarioCompensacao.objects.filter(data_compensacao=abono_chefia.data)
                    | HorarioCompensacao.objects.filter(data_aplicacao=abono_chefia.data)
                )
                .filter(funcionario=abono_chefia.vinculo_pessoa.relacionamento)
                .distinct()
            )
            for informe in informes:
                if abono_chefia.acao_abono in [
                    AbonoChefia.HORA_EXTRA_NAO_JUSTIFICADA,
                    AbonoChefia.HORA_EXTRA_JUSTIFICADA,
                    AbonoChefia.TRABALHO_FDS_NAO_PERMITIDO,
                    AbonoChefia.TRABALHO_FDS_PERMITIDO_COMO_HORA_EXTRA,
                    AbonoChefia.NAO_ABONADO,
                    AbonoChefia.ABONADO,
                    AbonoChefia.TRABALHO_REMOTO,
                ]:
                    # o abono poderá ter impacto negativo ao informe atual
                    if abono_chefia.data == informe.data_compensacao:
                        # o dia do saldo foi abonado
                        informe.abono_na_data_compensacao = abono_chefia
                    if abono_chefia.data == informe.data_aplicacao:
                        # o dia do débito foi abonado
                        informe.abono_na_data_aplicacao = abono_chefia
                    #
                    houve_impacto_negativo = informe.abono_na_data_compensacao is not None or informe.abono_na_data_aplicacao is not None
                    #
                    if houve_impacto_negativo:
                        # atualiza o informe
                        informe.situacao = HorarioCompensacao.SITUACAO_INVALIDO  # saldo totalmente liberado
                        informe.save()
                else:
                    # a ação do abono provavelmente foi alterada e isso poderá ter impacto positivo ao informe atual
                    if informe.abono_na_data_compensacao == abono_chefia:
                        # o abono deixa de afetar o informe na data da compensação
                        informe.abono_na_data_compensacao = None
                    #
                    if informe.abono_na_data_aplicacao == abono_chefia:
                        # o abono deixa de afetar o informe na data da aplicação
                        informe.abono_na_data_aplicacao = None
                    #
                    houve_impacto_positivo_na_data_compensacao = informe.abono_na_data_compensacao is None
                    houve_impacto_positivo_na_data_aplicacao = informe.abono_na_data_aplicacao is None
                    #
                    if houve_impacto_positivo_na_data_compensacao and houve_impacto_positivo_na_data_aplicacao:
                        informe.situacao = HorarioCompensacao.SITUACAO_VALIDO
                        # restaura as observações caso não tenha nenhuma das duas
                        if not informe.observacoes:
                            informe.save_observacao_no_ponto(
                                informe.get_auto_obs_descricao_na_data_compensacao(), informe.get_auto_obs_descricao_na_data_aplicacao()
                            )
                    if houve_impacto_positivo_na_data_compensacao or houve_impacto_positivo_na_data_compensacao:
                        # atualiza o informe (pode ser que a situação ainda continue inválida)
                        informe.save()

    @staticmethod
    def inspecionar_informes_abono_chefia_excluido(sender, **kwargs):
        abono_chefia = kwargs.get('instance')
        if abono_chefia:
            for informe in (
                (
                    HorarioCompensacao.objects.filter(abono_na_data_compensacao=abono_chefia)
                    | HorarioCompensacao.objects.filter(abono_na_data_aplicacao=abono_chefia)
                )
                .filter(funcionario=abono_chefia.vinculo_pessoa.relacionamento)
                .distinct()
            ):
                # atualiza o informe
                informe.abono_na_data_compensacao = None
                informe.abono_na_data_aplicacao = None
                informe.situacao = HorarioCompensacao.SITUACAO_VALIDO
                # restaura as observações caso não tenha nenhuma das duas
                if not informe.observacoes:
                    informe.save_observacao_no_ponto(
                        informe.get_auto_obs_descricao_na_data_compensacao(), informe.get_auto_obs_descricao_na_data_aplicacao()
                    )
                informe.save()
        #
        # só pra fazer uma limpeza em possíveis inconsistências ...
        for informe in HorarioCompensacao.objects.filter(
            situacao=HorarioCompensacao.SITUACAO_INVALIDO,  # inválidos
            abono_na_data_compensacao__isnull=True,
            abono_na_data_aplicacao__isnull=True,  # e sem abonos!!
            funcionario=abono_chefia.vinculo_pessoa.relacionamento,
        ):
            # atualiza o informe
            informe.situacao = HorarioCompensacao.SITUACAO_VALIDO
            # restaura as observações caso não tenha nenhuma das duas
            if not informe.observacoes:
                informe.save_observacao_no_ponto(
                    informe.get_auto_obs_descricao_na_data_compensacao(), informe.get_auto_obs_descricao_na_data_aplicacao()
                )
            informe.save()

    def get_situacao(self):  # uma outra versão do get_situacao_display
        situacao_display = self.get_situacao_display()  # padrão
        if self.situacao != HorarioCompensacao.SITUACAO_VALIDO:
            if self.abono_na_data_compensacao:
                situacao_display += '. '
                if self.abono_na_data_compensacao.acao_abono in [AbonoChefia.HORA_EXTRA_NAO_JUSTIFICADA, AbonoChefia.TRABALHO_FDS_NAO_PERMITIDO]:
                    situacao_display += 'Saldo Excedente Desconsiderado. '
                elif self.abono_na_data_compensacao.acao_abono in [
                    AbonoChefia.HORA_EXTRA_JUSTIFICADA,
                    AbonoChefia.TRABALHO_FDS_PERMITIDO_COMO_HORA_EXTRA,
                ]:
                    situacao_display += 'Saldo Excedente Desconsiderado (apenas efeitos remuneratórios). '
                situacao_display += 'Abono: {} - {} ({})'.format(
                    self.abono_na_data_compensacao.data.strftime('%d/%m/%Y'),
                    self.abono_na_data_compensacao.get_acao_abono_display(),
                    self.abono_na_data_compensacao.descricao,
                )
            #
            if self.abono_na_data_aplicacao:
                situacao_display += '. '
                if self.abono_na_data_aplicacao.acao_abono == AbonoChefia.NAO_ABONADO:
                    situacao_display += 'Débito Não Poderá ser Compensado. '
                elif self.abono_na_data_aplicacao.acao_abono in [AbonoChefia.ABONADO, AbonoChefia.TRABALHO_REMOTO]:
                    situacao_display += 'Débito Não Necessitará ser Compensado. '
                situacao_display += 'Abono: {} - {} ({})'.format(
                    self.abono_na_data_aplicacao.data.strftime('%d/%m/%Y'),
                    self.abono_na_data_aplicacao.get_acao_abono_display(),
                    self.abono_na_data_aplicacao.descricao,
                )
        return situacao_display

    @property
    def opcoes_compensacao_envolvidas(self):
        # return RecessoOpcao.objects.filter(
        #     recessoopcaoescolhida__funcionario=self.funcionario,
        #     recessoopcaoescolhida__validacao=RecessoOpcaoEscolhida.VALIDACAO_AUTORIZADO,
        #     recessoopcaoescolhida__dias_escolhidos__dia__data=self.data_aplicacao
        # )
        from ponto.compensacao import SituacaoDia

        situacao = SituacaoDia(servidor=self.funcionario, dia=self.data_aplicacao)
        return RecessoOpcao.objects.filter(recessoopcaoescolhida__in=situacao.acompanhamentos_envolvidos_contendo_o_dia_como_debito).distinct()

    @property
    def ch_compensada_em_segundos(self):
        return Frequencia.time_para_segundos(self.ch_compensada)

    def delete(self, *args, **kwargs):
        delete = super().delete(*args, **kwargs)
        if delete:
            from ponto.utils import get_total_tempo_debito_pendente_mes_anterior, get_total_tempo_debito_pendente_semana_anterior

            get_session_cache(
                tl.get_request(), 'total_tempo_debito_pendente_semana_anterior', get_total_tempo_debito_pendente_semana_anterior, 5 * 60
            )

            get_session_cache(tl.get_request(), 'total_tempo_debito_pendente_mes_anterior', get_total_tempo_debito_pendente_mes_anterior, 5 * 60)
        return delete

    @staticmethod
    def pode_visualizar_detalhamento_compensacao(
        user: User, servidor: Servidor, data_inicio: datetime.date, data_fim: datetime.date | None = None
    ) -> dict[datetime.date, bool]:
        result: dict[datetime.date, bool] = {}
        pode_ver_frequencia_todos = user.has_perm('ponto.pode_ver_frequencia_todos')
        user_relacionamento = user.get_relacionamento()
        user_eh_o_servidor = user_relacionamento == servidor

        coord_gestao_pessoas_campod_pode_ver = user.has_group_cached('Coordenador de Gestão de Pessoas') and (
            mesmo_campus(servidor, user_relacionamento)
        )

        servidor_chefes_no_periodo: dict[datetime.date, list[Servidor]] = {}
        if not user_eh_o_servidor:
            servidor_chefes_no_periodo = servidor.get_chefes_no_periodo(data_inicio=data_inicio, data_fim=data_fim)

        for dia in datas_entre(data_inicio, data_fim or datetime.date.today()):
            user_eh_o_chefe = False
            if not user_eh_o_servidor:
                user_eh_o_chefe = user_relacionamento in servidor_chefes_no_periodo.get(dia, [])
            result[dia] = pode_ver_frequencia_todos or user_eh_o_servidor or user_eh_o_chefe or coord_gestao_pessoas_campod_pode_ver

        return result


#
# "ouvindo" o pós save e o pós delete dos abonos de chefia (AbonoChefia)
abono_post_save = post_save.connect(sender=AbonoChefia, receiver=HorarioCompensacao.inspecionar_informes_abono_chefia_salvo)
abono_post_delete = post_delete.connect(sender=AbonoChefia, receiver=HorarioCompensacao.inspecionar_informes_abono_chefia_excluido)


class RecessoOpcao(models.Model):
    """Representa uma opção de compensação específica definida pelo RH"""

    SEARCH_FIELDS = ['descricao']

    class Meta:
        verbose_name = 'Opção de Compensação Específica'
        verbose_name_plural = 'Opções de Compensações Específicas'

    TIPO_PERMITE_ESCOLHA_LIVRE = 1
    TIPO_OUTRO = 2
    TIPO_CADASTRO_EXTERNO = 3
    TIPO_CHOICES = [
        [TIPO_PERMITE_ESCOLHA_LIVRE, 'Livre Escolha de Dias/Períodos'],
        [TIPO_OUTRO, 'Escolha Impositiva de Dias/Períodos'],
        [TIPO_CADASTRO_EXTERNO, 'Cadastro Externo'],  # tem a mesma função de TIPO_OUTRO ... apenas para diferenciar a origem
    ]

    SITUACAO_EM_FASE_DE_CADASTRO = 1
    SITUACAO_ABERTO_PARA_ESCOLHA = 2
    SITUACAO_FECHADO = 3
    SITUACAO_CHOICES = [
        [SITUACAO_EM_FASE_DE_CADASTRO, 'Em Fase de Cadastro'],
        [SITUACAO_ABERTO_PARA_ESCOLHA, 'Aberto para Escolha dos Dias/Períodos'],
        [SITUACAO_FECHADO, 'Concluído'],
    ]

    responsavel = models.ForeignKeyPlus('rh.Servidor', editable=False, verbose_name='Responsável pelo Cadastro', on_delete=models.CASCADE)

    tipo = models.IntegerField('Tipo', choices=TIPO_CHOICES, default=TIPO_OUTRO)
    descricao = models.TextField('Descrição')

    periodo_de_escolha_data_inicial = models.DateFieldPlus('Data de Início para o Período de Escolhas', null=True, blank=True)
    periodo_de_escolha_data_final = models.DateFieldPlus('Data de Término para o Período de Escolhas', null=True, blank=True)

    situacao = models.IntegerField('Situação', choices=SITUACAO_CHOICES, default=SITUACAO_EM_FASE_DE_CADASTRO, editable=False)

    qtde_max_dias_escolhidos = models.PositiveIntegerFieldPlus(
        'Quantidade de Dias a Escolher',
        help_text='Opcional. É o número máximo de dias que podem ser escolhidos. Refere-se ao cadastro de dias isolados.',
        min_value=0,
        default=0,
        blank=True,
    )

    qtde_max_periodos_escolhidos = models.PositiveIntegerFieldPlus(
        'Quantidade de Períodos a Escolher',
        help_text='Opcional. É o número máximo de períodos que podem ser escolhidos. Refere-se ao cadastro de períodos com início e fim determinados.',
        min_value=0,
        default=0,
        blank=True,
    )

    # Os fields 'publico_alvo_campi' e 'publico_alvo_servidores' representam os servidores afetados
    # por esta opção de compensação. O field 'publico_alvo_campi' é mais abrangente e pode envolver
    # servidores indesejados. Há situações em que servidores são automaticamente desconsiderados.
    # Para todos os efeitos, onde houver necessidade de saber os servidores de uma opção de compensação, utilize
    # o método 'get_servidores' desta classe.

    publico_alvo_campi = models.ManyToManyFieldPlus(
        'rh.UnidadeOrganizacional', verbose_name='Público alvo - Campi', blank=True, related_name='publico_alvo_campi'
    )
    publico_alvo_servidores = models.ManyToManyFieldPlus(
        'rh.Servidor', verbose_name='Público alvo - Servidores', blank=True, related_name='publico_alvo_servidores'
    )

    origem_type = models.ForeignKeyPlus(
        ContentType, verbose_name='Origem desta Opção de Compensação', null=True, blank=True, on_delete=models.SET_NULL
    )
    origem_id = models.PositiveIntegerField('Origem ID', null=True, blank=True)
    origem_object = GenericForeignKey('origem_type', 'origem_id')

    def save(self, *args, **kargs):
        # garante que não será salvo eventual valor None nos atributos
        self.qtde_max_dias_escolhidos = self.qtde_max_dias_escolhidos or 0
        self.qtde_max_periodos_escolhidos = self.qtde_max_periodos_escolhidos or 0
        super().save(*args, **kargs)

    @property
    def origem(self):
        return self.origem_object

    def get_origem_display(self):
        origem_type = self.origem_type
        origem = self.origem
        if origem_type and origem:
            return f'{origem_type.name}: {origem}'
        return None

    def get_servidores(self):
        """
        público alvo (lista de servidores) desta opção de compensação
        """
        servidores = self.publico_alvo_servidores.all()
        servidores_campi = Servidor.objects.ativos().filter(setor__uo__in=self.publico_alvo_campi.all())
        return (servidores | servidores_campi).distinct()

    @property
    def is_permite_escolha_pelos_servidores(self):
        return self.tipo == RecessoOpcao.TIPO_PERMITE_ESCOLHA_LIVRE

    @property
    def is_cadastro_externo(self):
        return self.tipo == RecessoOpcao.TIPO_CADASTRO_EXTERNO

    def __str__(self):
        return f'{self.descricao}'

    def get_absolute_url(self):
        return f'/ponto/abrir_opcao_recesso/{self.id}/'

    @property
    def is_em_fase_de_cadastro(self):
        return self.situacao == RecessoOpcao.SITUACAO_EM_FASE_DE_CADASTRO

    @property
    def is_aberto_para_escolhas_de_datas(self):
        return self.is_permite_escolha_pelos_servidores and self.situacao == RecessoOpcao.SITUACAO_ABERTO_PARA_ESCOLHA

    @property
    def is_concluido_cadastro_e_escolhas_de_datas(self):
        return self.situacao == RecessoOpcao.SITUACAO_FECHADO

    @property
    def is_no_periodo_para_escolhas_de_datas(self):
        return (
            self.is_aberto_para_escolhas_de_datas
            and self.periodo_de_escolha_data_inicial <= datetime.date.today() <= self.periodo_de_escolha_data_final
        )

    @property
    def is_definido_dias_do_recesso(self):
        return self.dias_do_recesso.all().exists()

    @property
    def is_definido_periodos_do_recesso(self):
        return self.periodos_do_recesso.all().exists()

    @property
    def is_definido_periodos_de_compensacao(self):
        return self.periodos_de_compensacao.all().exists()

    @property
    def is_definido_periodo_de_escolha(self):
        return (
            self.is_permite_escolha_pelos_servidores
            and self.periodo_de_escolha_data_inicial is not None
            and self.periodo_de_escolha_data_final is not None
        )

    def liberar_para_escolha_dos_dias_do_recesso(self):
        if not (
            self.is_publico_alvo_definido
            and (self.is_definido_dias_do_recesso or self.is_definido_periodos_do_recesso)
            and self.is_definido_periodo_de_escolha
            and self.is_definido_periodos_de_compensacao
        ):
            raise Exception(
                'Verifique se o Público Alvo, os Dias ou Períodos a Compensar, os Períodos de Compensação e o Período de Escolha foram definidos.'
            )

        if not self.is_em_fase_de_cadastro:
            raise Exception('Verifique se a Opção de Recesso está em Fase de Cadastro pelo RH.')

        hoje = datetime.date.today()
        maior_data_periodo_compensacao = self.periodos_de_compensacao.all().order_by('-data_inicial')[0].data_final
        if hoje > maior_data_periodo_compensacao:
            raise Exception('Os Períodos de Compensação estão no passado.')

        dias_do_recesso_qtd = self.dias_do_recesso.all().count()
        periodos_do_recesso_qtd = self.periodos_do_recesso.all().count()

        if self.qtde_max_dias_escolhidos and dias_do_recesso_qtd < self.qtde_max_dias_escolhidos:
            raise Exception(
                f'O número Máximo de Dias a Escolher ({self.qtde_max_dias_escolhidos}) '
                'é maior que o número de '
                f'Dias a compensar ({dias_do_recesso_qtd}).'
            )

        if not self.qtde_max_dias_escolhidos and dias_do_recesso_qtd > 0:
            raise Exception(
                f'O número Máximo de Dias a Escolher não foi definido e portanto não é possível informar os Dias a compensar ({dias_do_recesso_qtd}).'
            )

        if self.qtde_max_periodos_escolhidos and periodos_do_recesso_qtd < self.qtde_max_periodos_escolhidos:
            raise Exception(
                f'O número Máximo de Períodos a Escolher ({self.qtde_max_periodos_escolhidos}) '
                'é maior que o número de '
                f'Períodos a compensar ({periodos_do_recesso_qtd}).'
            )

        if not self.qtde_max_periodos_escolhidos and periodos_do_recesso_qtd > 0:
            raise Exception(
                'O número Máximo de Períodos a Escolher não foi definido e '
                'portanto não é possível informar os '
                f'Períodos a compensar ({periodos_do_recesso_qtd}).'
            )

        self.situacao = RecessoOpcao.SITUACAO_ABERTO_PARA_ESCOLHA
        self.save()

    def retornar_a_fase_de_cadastro(self):
        self.situacao = RecessoOpcao.SITUACAO_EM_FASE_DE_CADASTRO
        self.save()

    def pode_fechar_cadastro_e_escolha(self) -> tuple[bool, bool, str]:
        pode_fechar = False
        eh_escolha_automatica = not self.is_permite_escolha_pelos_servidores
        msg_erro = None
        if eh_escolha_automatica:
            pode_rodar_escolha_automatica = (
                self.is_publico_alvo_definido
                and (self.is_definido_dias_do_recesso or self.is_definido_periodos_do_recesso)
                and self.is_definido_periodos_de_compensacao
            )
            if not pode_rodar_escolha_automatica:
                msg_erro = 'Verifique se o Público Alvo, os Dias e os Períodos de Compensação foram definidos.'
            if pode_rodar_escolha_automatica:
                pode_fechar = True
        else:
            pode_fechar = True
        return (pode_fechar, eh_escolha_automatica, msg_erro)

    def fechar_cadastro_e_escolha(self):
        self.situacao = RecessoOpcao.SITUACAO_FECHADO
        self.save()

    def fechar_cadastro_e_escolha_automatica(self):
        try:
            self.escolher_dias_automaticamente(self.get_servidores())
        except Exception:
            raise Exception('Não foi possível concluir o cadastramento.')

    def escolher_dias_automaticamente(
        self, servidores: list[Servidor], dias_definidos_ids: list[int] | None = None, periodos_definidos_ids: list[int] | None = None
    ):
        dias_definidos_ids = dias_definidos_ids or self.dias_do_recesso.all().values_list('id', flat=True)
        periodos_definidos_ids = periodos_definidos_ids or self.periodos_do_recesso.all().values_list('id', flat=True)

        for servidor in servidores:
            acompanhamento = RecessoOpcaoEscolhida.objects.filter(funcionario=servidor, recesso_opcao=self)

            if acompanhamento.exists():
                acompanhamento = acompanhamento.first()

                # apenas reseta os dias efetivos a compensar para posterior atualização por demanda
                acompanhamento.dias_efetivos_a_compensar_reset()
                acompanhamento.save()
            else:
                acompanhamento = RecessoOpcaoEscolhida()
                acompanhamento.funcionario = servidor
                acompanhamento.recesso_opcao = self
                acompanhamento.validacao = RecessoOpcaoEscolhida.VALIDACAO_AUTORIZADO
                acompanhamento.save()

                # 1 acompanhamento ----> N dias escolhidos
                for dia_id in dias_definidos_ids:
                    dia_escolhido = RecessoDiaEscolhido()
                    dia_escolhido.recesso_opcao_escolhida = acompanhamento
                    dia_escolhido.dia_id = dia_id
                    dia_escolhido.save()

                # 1 acompanhamento ----> N periodos escolhidos
                for periodo_id in periodos_definidos_ids:
                    periodo_escolhido = RecessoPeriodoEscolhido()
                    periodo_escolhido.recesso_opcao_escolhida = acompanhamento
                    periodo_escolhido.periodo_id = periodo_id
                    periodo_escolhido.save()

                # apenas reseta os dias efetivos a compensar para posterior atualização por demanda
                acompanhamento.dias_efetivos_a_compensar_reset()
                acompanhamento.save()

    @property
    def is_publico_alvo_definido(self):
        return self.get_servidores().exists()

    def get_servidores_display(self):
        servidores = self.get_servidores()
        if servidores.count() > 5:
            lista = '{} ... +{}'.format(', '.join([str(servidor) for servidor in servidores[:5]]), servidores.count() - 5)
        else:
            lista = ', '.join([str(servidor) for servidor in servidores])
        return lista

    @staticmethod
    def get_recessos_opcoes_com_dias_ou_periodos_a_escolher_hoje(funcionario):
        """retorna um dicionário:
        {
            com_dias_ou_periodos_a_escolher: queryset [recesso_opcao, recesso_opcao, ...],
            com_dias_ou_periodos_a_editar: queryset [recesso_opcao, recesso_opcao, ...],
            com_dias_ou_periodos_a_remarcar: queryset [recesso_opcao, recesso_opcao, ...],
            com_dias_ou_periodos_que_ainda_pode_editar: queryset [recesso_opcao, recesso_opcao, ...]
        }
        """
        hoje = datetime.date.today()

        # todas as opções de recessos que estão abertas para a escolha de datas e
        # com período de escolha "caindo" hoje
        recessos_opcoes = RecessoOpcao.objects.filter(
            situacao=RecessoOpcao.SITUACAO_ABERTO_PARA_ESCOLHA, periodo_de_escolha_data_inicial__lte=hoje, periodo_de_escolha_data_final__gte=hoje
        )

        # omite as opções nas quais o servidor não pertence ao publico alvo
        for recesso_opcao in recessos_opcoes:
            if not recesso_opcao.get_servidores().filter(pk=funcionario.id).exists():
                recessos_opcoes = recessos_opcoes.exclude(id=recesso_opcao.id)

        # recessos a escolher = todos exceto os já escolhidos pelo funcionário
        recessos_a_escolher = recessos_opcoes.exclude(recessoopcaoescolhida__funcionario=funcionario)

        # recessos a editar = dentre todos, apenas os do funcionário e que estão 'aguardando'
        recessos_a_editar = recessos_opcoes.filter(
            recessoopcaoescolhida__funcionario=funcionario, recessoopcaoescolhida__validacao__in=[RecessoOpcaoEscolhida.VALIDACAO_AGUARDANDO]
        )

        # recessos a remarcar = dentre todos, apenas os do funcionário e que estão 'não-autorizados-remarcar'
        recessos_a_remarcar = recessos_opcoes.filter(
            recessoopcaoescolhida__funcionario=funcionario,
            recessoopcaoescolhida__validacao__in=[RecessoOpcaoEscolhida.VALIDACAO_NAO_AUTORIZADO_REMARCAR],
        )

        # recessos que ainda pode editar = dentre todos:
        recessos_ainda_pode_editar = recessos_opcoes.filter(
            # apenas os do funcionário informado
            recessoopcaoescolhida__funcionario=funcionario,
            # apenas diferente de "não autorizado"
            recessoopcaoescolhida__validacao__in=[
                RecessoOpcaoEscolhida.VALIDACAO_AGUARDANDO,
                RecessoOpcaoEscolhida.VALIDACAO_AUTORIZADO,
                RecessoOpcaoEscolhida.VALIDACAO_NAO_AUTORIZADO_REMARCAR,
            ],
        )

        return {
            'com_dias_ou_periodos_a_escolher': recessos_a_escolher,
            'com_dias_ou_periodos_a_editar': recessos_a_editar,
            'com_dias_ou_periodos_a_remarcar': recessos_a_remarcar,
            'com_dias_ou_periodos_que_ainda_pode_editar': recessos_ainda_pode_editar,
        }

    @staticmethod
    def get_recessos_opcoes_periodo_escolha_expirado():
        """Recessos abertos com período de escolhas expirado"""
        recessos_ids = []
        for recesso_opcao in RecessoOpcao.objects.filter(situacao=RecessoOpcao.SITUACAO_ABERTO_PARA_ESCOLHA):
            # não está no período?
            if not recesso_opcao.is_no_periodo_para_escolhas_de_datas:
                recessos_ids.append(recesso_opcao.id)
        return RecessoOpcao.objects.filter(id__in=recessos_ids)

    @staticmethod
    def set_concluir_recessos_opcoes_pendentes():
        """Recessos abertos com período de escolhas expirado são concluídos (tentativas)"""
        for recesso_opcao in RecessoOpcao.get_recessos_opcoes_periodo_escolha_expirado():
            try:
                recesso_opcao.fechar_cadastro_e_escolha()
            except Exception:
                pass

    def get_dias_escolhidos(self):
        return RecessoDiaEscolhido.objects.filter(
            recesso_opcao_escolhida__recesso_opcao=self,
            recesso_opcao_escolhida__validacao__in=[
                RecessoOpcaoEscolhida.VALIDACAO_AUTORIZADO,
                RecessoOpcaoEscolhida.VALIDACAO_NAO_AUTORIZADO,
                RecessoOpcaoEscolhida.VALIDACAO_NAO_AUTORIZADO_REMARCAR,
            ],
        )

    def get_periodos_escolhidos(self):
        return RecessoPeriodoEscolhido.objects.filter(
            recesso_opcao_escolhida__recesso_opcao=self,
            recesso_opcao_escolhida__validacao__in=[
                RecessoOpcaoEscolhida.VALIDACAO_AUTORIZADO,
                RecessoOpcaoEscolhida.VALIDACAO_NAO_AUTORIZADO,
                RecessoOpcaoEscolhida.VALIDACAO_NAO_AUTORIZADO_REMARCAR,
            ],
        )

    def pode_excluir(self) -> tuple[bool, str]:
        if self.is_permite_escolha_pelos_servidores:
            ha_escolhas = self.get_dias_escolhidos().exists() or self.get_periodos_escolhidos().exists()
            if ha_escolhas:
                return False, 'Exclusão não permitida. Há escolhas feitas por um ou mais servidores, com validação dos chefes imediatos.'
        elif self.is_cadastro_externo:
            # apenas o próprio SUAP pode excluir cadastros externos
            return False, 'Exclusão não permitida. Os cadastros externos são gerenciados pelo próprio SUAP.'
        return True, ''

    @staticmethod
    def get_opcoes_compensacoes_from_origem(model_instance_origem) -> QuerySet[RecessoOpcao]:
        return RecessoOpcao.objects.filter(origem_type=ContentType.objects.get_for_model(model_instance_origem), origem_id=model_instance_origem.id)

    @staticmethod
    def cadastrar_compensacao_especifica(
        descricao_compensacao: str,
        data_cadastro: datetime.datetime,
        servidor_responsavel: Servidor,
        servidores_alvo: list[Servidor],
        dias_a_compensar: list[datetime.date],
        periodos_a_compensar: list[Periodo],
        periodos_compensacao: list[Periodo],
        servidor_validador: Servidor = None,
        situacao_validacao: int | None = None,
        tipo_compensacao: int | None = None,
        situacao_compensacao: int | None = None,
        data_inicio_escolha: datetime.datetime | None = None,
        data_fim_escolha: datetime.datetime | None = None,
        qtd_max_dias_escolha: int = 0,
        qtd_max_periodos_escolha: int = 0,
        model_instance_origem=None,
        unique_together_with_model_instance_origem=True,  # 1 model_instance_origem ---> 0..1 opção de compensação específica
    ) -> list[RecessoOpcaoEscolhida]:
        """Permite o cadastro de uma compensação específica,
        por parte de um servidor responsável,
        para um ou mais servidores alvo, com dias e/ou períodos a compensar e
        períodos de compensação já definidos.

        Para autorização, é possível já informar
        um servidor validador e uma situação da validação,
        que, por padrão, será RecessoOpcaoEscolhida.VALIDACAO_AGUARDANDO
        (ver RecessoOpcaoEscolhida.VALIDACAO_CHOICES).

        De forma mais genérica, é possível informar o tipo e
        a situação da opção de compensação. Por padrão, o
        tipo será RecessoOpcao.TIPO_CADASTRO_EXTERNO (ver RecessoOpcao.TIPO_CHOICES) e
        a situação será RecessoOpcao.SITUACAO_FECHADO (ver RecessoOpcao.SITUACAO_CHOICES).
        Além disso, será possível informar o período de escolha (padrão nulo) e a
        quantidade máxima de dias a escolher (padrão 0 para não aplicável).
        """

        result: list[RecessoOpcaoEscolhida] = []

        if model_instance_origem and unique_together_with_model_instance_origem:
            # não haverá opções de compensações específicas duplicadas para uma mesma origem
            compensacao_opcao_anterior = RecessoOpcao.get_opcoes_compensacoes_from_origem(model_instance_origem)
            if compensacao_opcao_anterior.exists():
                compensacao_opcao_anterior.delete()

        situacao_validacao = situacao_validacao or RecessoOpcaoEscolhida.VALIDACAO_AGUARDANDO
        tipo_compensacao = tipo_compensacao or RecessoOpcao.TIPO_CADASTRO_EXTERNO
        situacao_compensacao = situacao_compensacao or RecessoOpcao.SITUACAO_FECHADO

        compensacao_opcao = RecessoOpcao(
            responsavel=servidor_responsavel,
            tipo=tipo_compensacao,
            descricao=descricao_compensacao,
            periodo_de_escolha_data_inicial=data_inicio_escolha,
            periodo_de_escolha_data_final=data_fim_escolha,
            situacao=situacao_compensacao,
            qtde_max_dias_escolhidos=qtd_max_dias_escolha,
            qtde_max_periodos_escolhidos=qtd_max_periodos_escolha,
        )
        if model_instance_origem:
            compensacao_opcao.origem_object = model_instance_origem
            compensacao_opcao.origem_id = model_instance_origem.id
        compensacao_opcao.save()

        compensacao_opcao.publico_alvo_servidores.set(servidores_alvo)

        for periodo_compensacao in periodos_compensacao:
            RecessoPeriodoCompensacao(
                recesso_opcao=compensacao_opcao,
                data_inicial=periodo_compensacao.data_hora_inicio.date(),
                data_final=periodo_compensacao.data_hora_fim.date(),
            ).save()

        dias_definidos: list[RecessoDia] = []
        for dia_a_compensar in dias_a_compensar:
            recesso_dia = RecessoDia(recesso_opcao=compensacao_opcao, data=dia_a_compensar)
            recesso_dia.save()
            dias_definidos.append(recesso_dia)

        periodos_definidos: list[RecessoPeriodo] = []
        for periodo_a_compensar in periodos_a_compensar:
            recesso_periodo = RecessoPeriodo(
                recesso_opcao=compensacao_opcao,
                data_inicio=periodo_a_compensar.data_hora_inicio.date(),
                data_fim=periodo_a_compensar.data_hora_fim.date(),
            )
            recesso_periodo.save()
            periodos_definidos.append(recesso_periodo)

        for servidor_alvo in servidores_alvo:
            compensacao_servidor = RecessoOpcaoEscolhida(
                funcionario=servidor_alvo,
                recesso_opcao=compensacao_opcao,
                data_escolha=data_cadastro,
                validacao=situacao_validacao,
                validador=servidor_validador,
            )
            compensacao_servidor.save()

            for recesso_dia in dias_definidos:
                RecessoDiaEscolhido(recesso_opcao_escolhida=compensacao_servidor, dia=recesso_dia).save()

            for recesso_periodo in periodos_definidos:
                RecessoPeriodoEscolhido(recesso_opcao_escolhida=compensacao_servidor, periodo=recesso_periodo).save()

            # apenas reseta os dias efetivos a compensar para posterior atualização por demanda
            compensacao_servidor.dias_efetivos_a_compensar_reset()
            compensacao_servidor.save()

            result.append(compensacao_servidor)

        return result


class RecessoPeriodoCompensacao(models.Model):
    """Representa um período definido pelo RH no qual será permitida a compensação"""

    class Meta:
        verbose_name = 'Período de Compensação'
        verbose_name_plural = 'Períodos de Compensação'

    recesso_opcao = models.ForeignKeyPlus('ponto.RecessoOpcao', editable=False, related_name='periodos_de_compensacao', on_delete=models.CASCADE)
    data_inicial = models.DateFieldPlus('Data Inicial')
    data_final = models.DateFieldPlus('Data Final')

    def __str__(self):
        return '{} a {}'.format(self.data_inicial.strftime('%d/%m/%Y'), self.data_final.strftime('%d/%m/%Y'))


class RecessoDia(models.Model):
    """Representa um dia definido pelo RH a compensar"""

    class Meta:
        verbose_name = 'Dia a Compensar'
        verbose_name_plural = 'Dias a Compensar'
        ordering = ('data',)
        unique_together = ('data', 'recesso_opcao')

    recesso_opcao = models.ForeignKeyPlus('ponto.RecessoOpcao', editable=False, related_name='dias_do_recesso', on_delete=models.CASCADE)
    data = models.DateFieldPlus('Dia do Recesso')

    def __str__(self):
        return f'{self.data.strftime("%d/%m/%Y")}'

    def pode_excluir(self):
        if self.recesso_opcao.is_permite_escolha_pelos_servidores:
            return not RecessoDiaEscolhido.objects.filter(
                dia=self,
                recesso_opcao_escolhida__validacao__in=[
                    RecessoOpcaoEscolhida.VALIDACAO_AUTORIZADO,
                    RecessoOpcaoEscolhida.VALIDACAO_NAO_AUTORIZADO,
                    RecessoOpcaoEscolhida.VALIDACAO_NAO_AUTORIZADO_REMARCAR,
                ],
            ).exists()
        return True


class RecessoPeriodo(models.Model):
    """Representa um período definido pelo RH a compensar.

    O motivo deste modelo foi para permitir o cadastro de uma
    compensação específica para compensar um período, evitando
    assim cadastrar individualmente cada dia a compensar
    no modelo RecessoDia. No caso de períodos longos, seria
    necessário cadastrar dia a dia do período. Com este modelo,
    isso não se faz necessário.

    RecessoPeriodo é a versão "período" do modelo RecessoDia.
    """

    recesso_opcao = models.ForeignKeyPlus('ponto.RecessoOpcao', editable=False, related_name='periodos_do_recesso', on_delete=models.CASCADE)
    data_inicio = models.DateFieldPlus('Data Início', help_text='Data início do período a compensar.')
    data_fim = models.DateFieldPlus('Data Fim', help_text='Data fim do período a compensar.')
    descricao = models.CharField(max_length=255, verbose_name='Descrição', blank=True, null=True)
    qtde_max_dias_a_escolher = models.PositiveIntegerFieldPlus(
        'Quantidade de dias a escolher',
        help_text='Número máximo de dias que podem ser escolhidos no período. Se não informado, todos os dias disponíveis do período poderão ser escolhidos.',
        min_value=0,
        default=0,
        blank=True,
    )

    # campo de texto para evitar mais um nível de join
    # valor = "dd/mm/YYYY,dd/mm/YYYY,dd/mm/YYYY,dd/mm/YYYY,..."
    dias_excluidos = models.TextField(
        'Dias excluídos/desconsiderados do período',
        help_text='Informe os dias no formato "dia/mês/ano" e separados por vírgula. Ex: "25/12/2025, 01/01/2026".',
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = 'Período a Compensar'
        verbose_name_plural = 'Períodos a Compensar'
        ordering = ('data_inicio',)

    def clean(self):
        """ATT: apenas um ModelForm chamará este clean automaticamente."""
        dias_excluidos_as_date = []
        if self.dias_excluidos:
            dias_excluidos_as_date = self.dias_excluidos_as_date()
            if not dias_excluidos_as_date:
                raise ValidationError(
                    {
                        'dias_excluidos': [
                            """Informe corretamente os Dias excluídos/desconsiderados do período.
                        Verifique se não há dias inválidos. Atenção para o formato: "dia/mês/ano, dia/mês/ano, ...".
                        """
                        ],
                    }
                )
        if self.data_inicio and self.data_fim and dias_excluidos_as_date:
            for dia_excluido in dias_excluidos_as_date:
                if not (self.data_inicio <= dia_excluido <= self.data_fim):
                    raise ValidationError(
                        {
                            'dias_excluidos': [f"""O dia {dia_excluido.strftime('%d/%m/%Y')} está fora do período informado."""],
                        }
                    )
            if self.qtde_max_dias_a_escolher:
                qtde_total_dias_no_periodo = (self.data_fim - self.data_inicio).days + 1
                qtde_dias_excluidos = len(dias_excluidos_as_date)
                if (qtde_total_dias_no_periodo - qtde_dias_excluidos) < self.qtde_max_dias_a_escolher:
                    raise ValidationError(
                        {
                            'qtde_max_dias_a_escolher': [
                                f"""A quantidade máxima de dias a escolher ({self.qtde_max_dias_a_escolher})
                            é maior que a quantidade de dias disponíveis ({qtde_total_dias_no_periodo - qtde_dias_excluidos}),
                            considerando os dias excluídos/desconsiderados ({qtde_dias_excluidos})."""
                            ],
                        }
                    )

    def dias_excluidos_as_date(self) -> list[datetime.date]:
        try:
            return sorted(
                {datetime.datetime.strptime(data_str.strip(), '%d/%m/%Y').date() for data_str in self.dias_excluidos.split(',') if data_str}
            )
        except Exception:
            return []

    def save(self, *args, **kargs):
        # garante que não será salvo eventual valor None
        self.qtde_max_dias_a_escolher = self.qtde_max_dias_a_escolher or 0
        super().save(*args, **kargs)
        # reseta os dias definidos
        self.periodos_do_recesso_dias_definidos.all().delete()

    def __str__(self):
        return f'{self.data_inicio.strftime("%d/%m/%Y")} a {self.data_fim.strftime("%d/%m/%Y")}{f" → {self.descricao}" if self.descricao else ""}'

    def pode_excluir(self):
        if self.recesso_opcao.is_permite_escolha_pelos_servidores:
            return not RecessoPeriodoEscolhido.objects.filter(
                periodo=self,
                recesso_opcao_escolhida__validacao__in=[
                    RecessoOpcaoEscolhida.VALIDACAO_AUTORIZADO,
                    RecessoOpcaoEscolhida.VALIDACAO_NAO_AUTORIZADO,
                    RecessoOpcaoEscolhida.VALIDACAO_NAO_AUTORIZADO_REMARCAR,
                ],
            ).exists()
        return True

    def get_dias_definidos(self) -> list[datetime.date]:
        # São TODOS os dias do período, excluindo os dias em 'dias_excluidos' (se for o caso)
        # Essa informação será consumida, entre outras, para
        # determinar os dias efetivos a compensar, calculado no método
        # RecessoOpcaoEscolhida.dias_efetivos_a_compensar, o qual realizará
        # o filtro necessário

        if self.periodos_do_recesso_dias_definidos.exists():
            # dias definidos gravados em RecessoPeriodoDiaDefinido
            dias_definidos: list[datetime.date] = [dia_definido.dia for dia_definido in self.periodos_do_recesso_dias_definidos.all()]
        else:
            # calcula os dias definidos
            dias_excluidos_as_date = self.dias_excluidos_as_date()
            dias_definidos: list[datetime.date] = [
                dia_periodo
                for dia_periodo in datas_entre(self.data_inicio, self.data_fim)
                if (not dias_excluidos_as_date) or (dia_periodo not in dias_excluidos_as_date)
            ]

            # grava os dias definidos em RecessoPeriodoDiaDefinido
            for dia_definido in dias_definidos:
                RecessoPeriodoDiaDefinido(recesso_periodo=self, dia=dia_definido).save()

        return dias_definidos


class RecessoPeriodoDiaDefinido(models.Model):
    """Representa os dias definidos de um dado período cadastrado pelo RH.

    Tem valor de 'cache' para o modelo 'RecessoPeriodo', além de facilitar
    consultas.

    A lista dos dias definidos de um período é provida através
    do método 'RecessoPeriodo.get_dias_definidos'.
    """

    class Meta:
        verbose_name = 'Período a compensar - Dia definido'
        verbose_name_plural = 'Períodos a compensar - Dias definidos'
        ordering = ('dia',)

    recesso_periodo = models.ForeignKeyPlus(
        'ponto.RecessoPeriodo', editable=False, related_name='periodos_do_recesso_dias_definidos', on_delete=models.CASCADE
    )
    dia = models.DateFieldPlus('Dia Individual Escolhido/Atribuído')

    def __str__(self):
        return f'{self.dia.strftime("%d/%m/%Y")}'


class RecessoOpcaoEscolhida(models.Model):
    """Representa uma opção de compensação específica escolhida (ou atribuída) por um servidor,
    quem tem o direito de compensar, com um prazo flexível, um ou mais dias/períodos (escolhidos ou atribuídos).
    """

    VALIDACAO_AGUARDANDO = 1
    VALIDACAO_AUTORIZADO = 2
    VALIDACAO_NAO_AUTORIZADO = 3
    VALIDACAO_NAO_AUTORIZADO_REMARCAR = 4
    VALIDACAO_CHOICES = [
        [VALIDACAO_AGUARDANDO, 'Aguardando'],
        [VALIDACAO_AUTORIZADO, 'Autorizado'],
        [VALIDACAO_NAO_AUTORIZADO_REMARCAR, 'Não Autorizado - Remarcar Novamente'],
        [VALIDACAO_NAO_AUTORIZADO, 'Não Autorizado'],
    ]

    class Meta:
        verbose_name = 'Compensação Específica'
        verbose_name_plural = 'Compensações Específicas'
        ordering = ('-data_escolha',)

    funcionario = models.ForeignKeyPlus(
        'rh.Servidor', editable=False, verbose_name='Servidor', related_name='funcionario_recesso', on_delete=models.CASCADE
    )
    recesso_opcao = models.ForeignKeyPlus('ponto.RecessoOpcao', editable=False, verbose_name='Opção de Compensação', on_delete=models.CASCADE)
    data_escolha = models.DateTimeField('Data/Hora da Escolha/Atribuição', auto_now_add=True)
    validacao = models.IntegerField('Validação', choices=VALIDACAO_CHOICES, default=VALIDACAO_AGUARDANDO)
    validador = models.ForeignKeyPlus(
        'rh.Servidor', verbose_name='Validador', related_name='validador_recesso', blank=True, null=True, on_delete=models.CASCADE
    )
    motivo_nao_autorizacao = models.TextField('Motivo da Não Autorização (se for o caso)', null=True, blank=True)
    data_validacao = models.DateTimeField('Data/Hora da Validação', null=True)

    dias_efetivos_a_compensar_cache = models.TextField('', null=True, blank=True, editable=False)
    pode_validar_apos_prazo = models.BooleanField('Liberado para validação após término do prazo', default=False)

    responsavel_ultima_pos_edicao = models.ForeignKeyPlus(
        'rh.Servidor',
        null=True,
        blank=True,
        editable=False,
        verbose_name='Servidor que realizou a última edição após cadastramento',
        related_name='servidor_editor_recesso',
        on_delete=models.CASCADE,
    )

    @property
    def data_escolha_display(self):
        dois_out_2025 = datetime.date(2025, 10, 2)
        if self.data_escolha.date() <= dois_out_2025:
            # até 02/10/2025 o field 'data_escolha' era apenas um 'date' e
            # não foi conveniente exibir hora, minutos e segundos para
            # datas até 02/10/2025
            return self.data_escolha.strftime('%d/%m/%Y')
        return self.data_escolha.strftime('%d/%m/%Y %H:%M:%S')

    def __str__(self):
        return f'{self.recesso_opcao}'

    @property
    def chefes(self) -> list[Servidor]:
        """chefes na data da escolha + chefes na data de hoje + validador selecionado (se for o caso)"""

        chefes = []  # instâncias de rh.Servidor

        try:
            servidor: Servidor = self.funcionario

            data_escolha = self.data_escolha.date() if self.data_escolha else None
            if data_escolha:
                chefes.extend(servidor.get_chefes_no_periodo(data_escolha, data_escolha, True)[data_escolha])

            hoje = datetime.date.today()
            chefes.extend(servidor.get_chefes_no_periodo(hoje, hoje, True)[hoje])

            if self.validador and self.validador not in chefes:
                chefes.extend([self.validador])
        except Exception:
            chefes = []

        return chefes

    def is_chefe(self, relacionamento=None, retornar_chefes=False):
        chefes = self.chefes
        if retornar_chefes:
            return relacionamento in chefes, chefes
        return relacionamento in chefes

    @staticmethod
    def pode_editar_opcoes_escolhidas(user: User) -> tuple[bool, QuerySet[RecessoOpcaoEscolhida]]:
        servidor = user.get_relacionamento()

        escopo_opcoes = RecessoOpcaoEscolhida.objects.none()

        if not user.eh_servidor:
            return False, escopo_opcoes

        eh_super_usuario = user.is_superuser
        eh_rh_sistemico = user.has_perm('rh.eh_rh_sistemico')
        eh_rh_campus = user.has_perm('rh.eh_rh_campus')
        eh_validador = RecessoOpcaoEscolhida.objects.filter(validador=servidor).exists()

        if eh_super_usuario or eh_rh_sistemico:
            escopo_opcoes = escopo_opcoes | RecessoOpcaoEscolhida.objects.all()
        if eh_rh_campus:
            servidor_campus_sigla = servidor.setor.uo.sigla
            escopo_opcoes = escopo_opcoes | RecessoOpcaoEscolhida.objects.filter(funcionario__setor__uo__sigla=servidor_campus_sigla)
        if eh_validador:
            escopo_opcoes = escopo_opcoes | RecessoOpcaoEscolhida.objects.filter(validador=servidor)

        return eh_super_usuario or eh_rh_sistemico or eh_validador, escopo_opcoes

    @property
    def is_aguardando(self):
        return self.validacao == RecessoOpcaoEscolhida.VALIDACAO_AGUARDANDO

    def get_absolute_url(self):
        return f'/ponto/abrir_recesso_escolhido/{self.id}/'

    def notifica_validacao(self):
        if not self.is_aguardando:
            assunto = f'[SUAP] Validação de {self.recesso_opcao}'
            url = f'{settings.SITE_URL}/ponto/abrir_recesso_escolhido/{self.id}/'
            mensagem = """
                <h1>Validação de Compensação Específica</h1>
                <h2>{}</h2>
                <dl>
                    <dt>Dias/Períodos escolhidos:</dt><dd>{}</dd>
                    <dt>Data da escolha:</dt><dd>{}</dd>
                    <dt>Validação:</dt><dd>{} {}</dd>
                    <dt>Validador:</dt><dd>{}</dd>
                    {}
                </dl>
                <p class="more-info">Para mais informações, acesse: <a href="{}">{}</a></p>
                """.format(
                self.recesso_opcao,
                ', '.join(
                    [str(dia_periodo_escolhido) for dia_periodo_escolhido in list(self.dias_escolhidos.all()) + list(self.periodos_escolhidos.all())]
                ),
                self.data_escolha_display,
                self.get_validacao_display(),
                f'(Motivo: {self.motivo_nao_autorizacao})'
                if self.validacao in [RecessoOpcaoEscolhida.VALIDACAO_NAO_AUTORIZADO, RecessoOpcaoEscolhida.VALIDACAO_NAO_AUTORIZADO_REMARCAR]
                else '',
                self.validador,
                f'<dt>Data da validação:</dt><dd>{self.data_validacao.strftime("%d/%m/%Y %H:%M:%S")}</dd>' if self.data_validacao else '',
                url,
                url,
            )
            send_notification(assunto, mensagem, settings.DEFAULT_FROM_EMAIL, [self.funcionario.get_vinculo()])

    @property
    def dias_efetivos_a_compensar_estah_resolvido(self):
        return self.dias_efetivos_a_compensar_cache is not None and self.dias_efetivos_a_compensar_cache != ''

    def dias_efetivos_a_compensar_reset(self):
        self.dias_efetivos_a_compensar_cache = ''

    def dias_efetivos_a_compensar(self, retornar_contexto_compensacao=False, contexto_compensacao=None, force_update=False):
        """Retorna os dias efetivos a compensar já calculados e contidos no field 'dias_efetivos_a_compensar_cache'.

        Se o field 'dias_efetivos_a_compensar_cache' estiver vazio ou se ocorrer algum erro no acesso ao seu
        conteúdo, ou ainda se 'force_update' for True, então será recalculado os dias efetivos a compensar e salvos
        novamente no field 'dias_efetivos_a_compensar_cache'.

        O uso do field 'dias_efetivos_a_compensar_cache' evita futuras consultas mais complexas no banco de dados.
        Para melhorar ainda mais o desempenho, o consumidor deste método pode usar um único objeto do tipo 'Contexto'
        e informá-lo no parâmetro 'contexto_compensacao', além de solicitar o seu retorno no parâmetro
        'retornar_contexto_compensacao'. O objeto do tipo 'Contexto' agrupa muitas consultas e assim é desejável
        não ficar repetindo as mesmas consultas para diferentes instâncias dele.

        Então, este método retorna:
            - uma lista de [date, date, date, ...]
            - ou uma lista de [[date, date, date, ...], instância do contexto]

        Se um contexto não for informado e for solicitado o seu retorno, será criado um contexto dentro
        do período dos dias efetivos a compensar.
        """

        if force_update:
            self.dias_efetivos_a_compensar_cache = ''

        from ponto.compensacao import Contexto

        subconjunto_dos_dias: list[datetime.date] = []
        contexto: Contexto = contexto_compensacao

        erro_no_cache = False

        if self.dias_efetivos_a_compensar_cache:
            try:
                subconjunto_dos_dias = [
                    datetime.datetime.strptime(data_string.strip(), '%d/%m/%Y').date()
                    for data_string in self.dias_efetivos_a_compensar_cache.split(';')
                    if data_string
                ]
            except Exception:
                erro_no_cache = True

        todos_os_dias: list[datetime.date] = []

        if erro_no_cache or not self.dias_efetivos_a_compensar_cache:
            if self.recesso_opcao.is_permite_escolha_pelos_servidores:
                # o servidor pode escolher os dias/períodos

                # escopo dos dias: apenas dias/períodos escolhidos pelo servidor;
                # se o RH alterou os dias definidos, isso não é "culpa" do servidor
                # que escolheu livremente e foi autorizado pelo chefe imediato

                for dia_escolhido in self.dias_escolhidos.all().select_related('dia'):
                    todos_os_dias += [dia_escolhido.dia.data]

                for periodo_escolhido in self.periodos_escolhidos.all().select_related('periodo'):
                    todos_os_dias += periodo_escolhido.get_dias_escolhidos()
            else:
                # o servidor NÃO pode escolher os dias/períodos (eles foram atribuídos de 'cima pra baixo')

                # escopo dos dias: dias/períodos definidos pelo RH + dias/períodos escolhidos pelo servidor

                dias_definidos: list[datetime.date] = []
                periodos_definidos_ids: list[int] = []

                dias_escolhidos: list[datetime.date] = []
                periodos_escolhidos_ids: list[int] = []
                periodos_escolhidos: list[RecessoPeriodoEscolhido] = []

                for dia_definido in self.recesso_opcao.dias_do_recesso.all():
                    dias_definidos += [dia_definido.data]

                for periodo_definido in self.recesso_opcao.periodos_do_recesso.all():
                    periodos_definidos_ids += [periodo_definido.id]

                for dia_escolhido in self.dias_escolhidos.all().select_related('dia'):
                    # o dia escolhido deve pertencer à lista dos dias definidos
                    # caso contrário, sua referência já foi excluída pelo RH, removendo
                    # também os objetos "filhos"
                    if dia_escolhido.dia.data in dias_definidos:
                        dias_escolhidos += [dia_escolhido.dia.data]

                for periodo_escolhido in self.periodos_escolhidos.all().select_related('periodo'):
                    # o período escolhido deve pertencer à lista dos períodos definidos
                    # caso contrário, sua referência já foi excluída pelo RH, removendo
                    # também os objetos "filhos"
                    if periodo_escolhido.periodo.id in periodos_definidos_ids:
                        periodos_escolhidos_ids += [periodo_escolhido.periodo.id]
                        periodos_escolhidos += [periodo_escolhido]

                ###
                # É possível que o RH tenha alterado, posteriormente, os dias/períodos definidos.
                # Nesse caso, os novos dias/períodos deverão ser escolhas automáticas pelo servidor

                novos_dias_definidos = list(set(dias_definidos) - set(dias_escolhidos))

                for novo_dia_definido in novos_dias_definidos:
                    novo_dia_definido_como_recesso_dia = RecessoDia.objects.filter(recesso_opcao=self.recesso_opcao, data=novo_dia_definido).first()

                    # atribui o dia ao servidor
                    RecessoDiaEscolhido(recesso_opcao_escolhida=self, dia=novo_dia_definido_como_recesso_dia).save()

                novos_periodos_definidos_ids = list(set(periodos_definidos_ids) - set(periodos_escolhidos_ids))
                novos_periodos_definidos: list[RecessoPeriodo] = []

                for novo_periodo_definido_id in novos_periodos_definidos_ids:
                    novo_periodo_definido_como_recesso_periodo = RecessoPeriodo.objects.filter(id=novo_periodo_definido_id).first()

                    # atribui o período ao servidor
                    RecessoPeriodoEscolhido(recesso_opcao_escolhida=self, periodo=novo_periodo_definido_como_recesso_periodo).save()

                    novos_periodos_definidos += [novo_periodo_definido_como_recesso_periodo]

                todos_os_dias = novos_dias_definidos + dias_escolhidos

                for periodo in novos_periodos_definidos:
                    todos_os_dias += periodo.get_dias_definidos()

                for periodo in periodos_escolhidos:
                    todos_os_dias += periodo.get_dias_escolhidos()

                todos_os_dias = list(set(todos_os_dias))

            if todos_os_dias:
                # realiza o 'filtro' que vai determinar APENAS os dias
                # efetivos a compensar

                if contexto:
                    for dia in todos_os_dias:
                        if contexto.get_dia(dia, add_se_nao_existir=True).is_debito:
                            subconjunto_dos_dias.append(dia)
                else:
                    contexto = Contexto(self.funcionario, min(todos_os_dias), max(todos_os_dias))

                    for dia_debito in list(contexto.dias_debitos.keys()):
                        if dia_debito in todos_os_dias:
                            subconjunto_dos_dias.append(dia_debito)

        subconjunto_dos_dias = sorted(subconjunto_dos_dias)

        if not self.dias_efetivos_a_compensar_cache:
            if subconjunto_dos_dias:
                self.dias_efetivos_a_compensar_cache = ';'.join([data.strftime('%d/%m/%Y') for data in subconjunto_dos_dias])
            else:
                self.dias_efetivos_a_compensar_cache = ';'  # cache mínimo não vazio

            self.save()

        if retornar_contexto_compensacao:
            if not contexto:
                if subconjunto_dos_dias:
                    contexto = Contexto(self.funcionario, min(subconjunto_dos_dias), max(subconjunto_dos_dias))

            return subconjunto_dos_dias, contexto

        return subconjunto_dos_dias

    def compensacoes(self):
        """retorna uma lista com as compensações (instâncias de HorarioCompensacao) já informadas para
        os dias efetivos a compensar
        """
        compensacoes = HorarioCompensacao.objects.filter(funcionario=self.funcionario, data_aplicacao__in=self.dias_efetivos_a_compensar()).order_by(
            'data_aplicacao', 'data_compensacao'
        )
        return compensacoes

    # ---------------------------------
    # para evitar import circular que ocorre no caso de
    # ponto.compensacao import SituacaoDiaOrigemDebito
    SituacaoDiaOrigemDebito = TypeVar('SituacaoDiaOrigemDebito')

    @property
    def origem_debito(self) -> tuple[SituacaoDiaOrigemDebito, Model, str]:
        from ponto.compensacao import SituacaoDiaOrigemDebito

        origem_debito: SituacaoDiaOrigemDebito = SituacaoDiaOrigemDebito.QUALQUER
        origem_debito_externo = None
        msg = ''

        # TODO: para satisfazer uma necessidade do GECC, a compensação específica gerada a partir de uma atividade
        # TODO: em cursos/concursos (mais detalhes na demanda 1369) deverá exibir apenas os valores de débitos cuja fonte
        # TODO: seja apenas os débitos externos restritos à atividade
        from cursos.models import Participante

        if isinstance(self.recesso_opcao.origem, Participante):
            participante: Participante = self.recesso_opcao.origem
            origem_debito = SituacaoDiaOrigemDebito.APENAS_DEBITOS_EXTERNOS
            origem_debito_externo = participante
            msg = f"""
                Esta compensação específica teve origem em uma atividade de Cursos/Concursos ({participante.atividade.descricao}).
                Os valores dos débitos de carga horária a seguir são restritos à atividade referida.
            """

        return (origem_debito, origem_debito_externo, msg)

    # ---------------------------------

    def totais_ch(
        self,
        carga_horaria_total=False,
        carga_horaria_debito_considerado=False,
        carga_horaria_compensada=False,
        carga_horaria_pendente=False,
        retornar_contexto_compensacao=False,
        contexto_compensacao=None,
    ):
        """
        Há uma queda de desempenho considerável durante a execução deste método. Não é possível persistir os
        totais pois são sensíveis a qualquer alteração no ponto do usuário. Tais alterações possuem
        diversas origens:
            1 - o usuário informando uma compensação
            2 - o chefe imediato abonando um dia no ponto do usuário
            3 - o RH lançando liberações, afastamentos, férias, viagens, etc que afetam o ponto apenas do usuário ou de um grupo de usuários

        Dessa forma, atributos com os totais resolvidos só serão possíveis quando o conceito de "fechamento do ponto" for
        desenvolvido de modo que uma alteração no ponto só será aplicada em períodos "em aberto". Até lá a única forma de
        obter os totais é repetindo todos os cálculos.
        """

        from ponto.compensacao import SituacaoDia

        total_carga_horaria_total = 0
        total_carga_horaria_debito_considerado = 0
        total_carga_horaria_compensada = 0
        total_carga_horaria_pendente = 0
        total_carga_horaria_pendente_por_dia = {}
        dias_a_compensar = []

        if carga_horaria_total or carga_horaria_debito_considerado or carga_horaria_compensada or carga_horaria_pendente:
            dias_a_compensar, contexto_compensacao = self.dias_efetivos_a_compensar(True, contexto_compensacao)

            for dia_a_compensar in dias_a_compensar:
                dia_situacao: SituacaoDia = contexto_compensacao.get_dia(dia_a_compensar, True)
                total_carga_horaria_pendente_por_dia[dia_situacao.dia] = 0

                origem_debito, origem_debito_externo, _ = self.origem_debito
                dia_situacao.set_origem_debito(origem_debito, origem_debito_externo)

                if carga_horaria_total:
                    total_carga_horaria_total += dia_situacao.carga_horaria_qtd

                if carga_horaria_debito_considerado:
                    total_carga_horaria_debito_considerado += dia_situacao.debito_qtd_considerado

                if carga_horaria_compensada:
                    total_carga_horaria_compensada += dia_situacao.debito_qtd_reposto

                if carga_horaria_pendente:
                    debito_qtd_restante = dia_situacao.debito_qtd_restante
                    total_carga_horaria_pendente += debito_qtd_restante
                    total_carga_horaria_pendente_por_dia[dia_situacao.dia] = debito_qtd_restante

        totais = {
            'total_carga_horaria_total': total_carga_horaria_total,
            'total_carga_horaria_debito_considerado': total_carga_horaria_debito_considerado,
            'total_carga_horaria_compensada': total_carga_horaria_compensada,
            'total_carga_horaria_pendente': total_carga_horaria_pendente,
            'dias_a_compensar': dias_a_compensar,
            'contexto_compensacao': contexto_compensacao,
            'total_carga_horaria_pendente_por_dia': total_carga_horaria_pendente_por_dia,
        }

        if retornar_contexto_compensacao:
            return totais, contexto_compensacao

        return totais

    def pode_excluir(self, relacionamento):
        usuario_eh_o_solicitante = relacionamento == self.funcionario
        recesso_opcao_escolhida_estah_aguardando_validacao = self.is_aguardando
        recesso_opcao_escolhida_com_dias_livremente_selecionados = self.recesso_opcao.is_permite_escolha_pelos_servidores
        # TODO: esse teste de compensações informadas poderia ser retirado, pois as compensações
        # TODO: são "propriedades" dos dias dos débitos, e não da opção de compensação escolhida
        # TODO: o impacto, nesse caso, é que os dias dos débitos perderiam o direito de serem compensados
        # TODO: no período de compensação flexibilizado pela compensação específica ... mas aí caberia
        # TODO: buscar os informes de compensação não permitidos e invalidá-los
        recesso_opcao_escolhida_tem_compensacoes_informadas = self.compensacoes().exists()
        return (
            usuario_eh_o_solicitante
            and recesso_opcao_escolhida_com_dias_livremente_selecionados
            and (recesso_opcao_escolhida_estah_aguardando_validacao or not recesso_opcao_escolhida_tem_compensacoes_informadas)
        )

    @staticmethod
    def get_recessos_escolhidos_aguardando_validacao_hoje(validador):
        hoje = datetime.date.today()
        queryset = RecessoOpcaoEscolhida.objects.filter(
            # funcionários que eu vou validar
            validacao=RecessoOpcaoEscolhida.VALIDACAO_AGUARDANDO,
            recesso_opcao__situacao=RecessoOpcao.SITUACAO_ABERTO_PARA_ESCOLHA,
            recesso_opcao__periodo_de_escolha_data_inicial__lte=hoje,
            recesso_opcao__periodo_de_escolha_data_final__gte=hoje,
        )
        return queryset.filter(
            Q(validador=validador)
            | Q(
                funcionario__setor_id__in=validador.historico_funcao(hoje, hoje)
                .filter(funcao__codigo__in=Funcao.get_codigos_funcao_chefia())
                .values_list('setor_suap_id', flat=True)
            )
        ).exclude(funcionario=validador)

    @staticmethod
    def has_recessos_escolhidos(servidor):
        return RecessoOpcaoEscolhida.objects.filter(funcionario=servidor, validacao=RecessoOpcaoEscolhida.VALIDACAO_AUTORIZADO).exists()

    @staticmethod
    def get_compensacoes_especificas_from_origem(model_instance_origem) -> QuerySet[RecessoOpcaoEscolhida]:
        return RecessoOpcaoEscolhida.objects.filter(
            recesso_opcao__origem_type=ContentType.objects.get_for_model(model_instance_origem), recesso_opcao__origem_id=model_instance_origem.id
        )

    def dias_efetivos_a_compensar_display_html(self):
        obj = self
        display_html = ''

        if obj.is_aguardando:  # aguardando validação do chefe ?
            display_html = '<span class="status status-alert text-nowrap-normal text-right">Aguardando autorização</span>'
        else:
            dias_efetivos_a_compensar = obj.dias_efetivos_a_compensar()

            if dias_efetivos_a_compensar:
                display_html += '<span class="text-nowrap-normal">'
                display_html += ', '.join([data.strftime('%d/%m/%Y') for data in dias_efetivos_a_compensar])
                display_html += '</span>'
            else:
                display_html = '<span class="text-nowrap-normal">Nenhum dia a exibir</span>'

        return mark_safe(display_html)

    def total_carga_horaria_pendente(self) -> int:
        obj = self
        if obj.validacao == RecessoOpcaoEscolhida.VALIDACAO_AUTORIZADO:
            total_ch_pendente = obj.totais_ch(carga_horaria_pendente=True)['total_carga_horaria_pendente']
        else:
            total_ch_pendente = 0
        return total_ch_pendente

    def total_carga_horaria_pendente_display_html(self, user_visualizador=None) -> str:
        obj = self

        pode_visualizar = (not user_visualizador) or (user_visualizador and user_visualizador.get_relacionamento() == obj.funcionario)

        display_html = ''

        if pode_visualizar:
            if obj.validacao == RecessoOpcaoEscolhida.VALIDACAO_AUTORIZADO:
                total_ch_pendente = obj.totais_ch(carga_horaria_pendente=True)['total_carga_horaria_pendente']
                status_css = 'true'
                if total_ch_pendente > 0:
                    status_css = 'false'
                total_ch_pendente_format = formata_segundos(total_ch_pendente, '{h:02.0f}h ', '{m:02.0f}min ', '{s:02.0f}seg ', True)
                display_html += f"<span class='{status_css} text-nowrap-normal'>{total_ch_pendente_format}</span>"
            else:
                display_html += "<span class='status status-alert text-nowrap-normal'>Aguardando autorização</span>"
        else:
            display_html += '-'

        return mark_safe(display_html)

    def total_carga_horaria_pendente_por_dia(self) -> dict:
        obj = self

        dias = {}
        if obj.validacao == RecessoOpcaoEscolhida.VALIDACAO_AUTORIZADO:
            dias = obj.totais_ch(carga_horaria_pendente=True)['total_carga_horaria_pendente_por_dia']

        return dias

    def total_carga_horaria_pendente_por_dia_display_html(self, user_visualizador=None) -> str:
        obj = self

        pode_visualizar = (not user_visualizador) or (user_visualizador and user_visualizador.get_relacionamento() == obj.funcionario)

        display_html = ''

        dias = []

        if pode_visualizar:
            if obj.validacao == RecessoOpcaoEscolhida.VALIDACAO_AUTORIZADO:
                total_ch_pendente_por_dia = obj.totais_ch(carga_horaria_pendente=True)['total_carga_horaria_pendente_por_dia']
                for dia, ch in total_ch_pendente_por_dia.items():
                    ds = formata_segundos(ch, '{h:02.0f}h ', '{m:02.0f}min ', '{s:02.0f}seg ', True)
                    dias.append(f'{dia.strftime("%d/%m/%Y")} ({ds})')
                if dias:
                    display_html += '<span class="text-nowrap-normal">'
                    display_html += ' | '.join(list(dias))
                    display_html += '</span>'
            else:
                display_html += "<span class='status status-alert text-nowrap-normal'>Aguardando autorização</span>"
        else:
            display_html += '-'

        return mark_safe(display_html)

    def periodo_compensacao(self):
        obj = self
        return ', '.join([str(periodo) for periodo in obj.recesso_opcao.periodos_de_compensacao.all()])


class RecessoDiaEscolhido(models.Model):
    """Representa, dentro do contexto de uma compensação específica,
    um dia a compensar escolhido/atribuído por/a um servidor/funcionário
    """

    class Meta:
        verbose_name = 'Dia Escolhido'
        verbose_name_plural = 'Dias Escolhidos'
        ordering = ('dia__data',)

    recesso_opcao_escolhida = models.ForeignKeyPlus(
        'ponto.RecessoOpcaoEscolhida', editable=False, related_name='dias_escolhidos', on_delete=models.CASCADE
    )
    dia = models.ForeignKeyPlus('ponto.RecessoDia', verbose_name='Dia Escolhido/Atribuído', on_delete=models.CASCADE)

    def __str__(self):
        return f'{self.dia}'


class RecessoPeriodoEscolhido(models.Model):
    """Representa, dentro do contexto de uma compensação específica,
    um período a compensar escolhido/atribuído por/a um servidor/funcionário.

    Vale aqui as considerações do modelo RecessoPeriodo.

    O motivo deste modelo foi para permitir a escolha/atribuição
    de uma período a compensar, evitando assim cadastrar individualmente
    cada dia escolhido/atribuído no modelo RecessoDiaEscolhido. No caso de
    períodos longos, seria necessário cadastrar todos os dias do período.
    Com este modelo, isso não se faz necessário.

    RecessoPeriodoEscolhido é a versão "período" do modelo RecessoDiaEscolhido.

    IMPORTANTE:
        O processamento dos débitos ainda será a nível de dia INDIVIDUAL. Os
        "dias efetivos compensar" ainda valem para este modelo, o qual proverá
        o escopo dos dias para RecessoOpcaoEscolhida.dias_efetivos_a_compensar_cache.
        Ver método 'get_dias_escolhidos' deste modelo.
    """

    class Meta:
        verbose_name = 'Período Escolhido'
        verbose_name_plural = 'Períodos Escolhidos'
        ordering = ('periodo__data_inicio',)

    recesso_opcao_escolhida = models.ForeignKeyPlus(
        'ponto.RecessoOpcaoEscolhida', editable=False, related_name='periodos_escolhidos', on_delete=models.CASCADE
    )
    periodo = models.ForeignKeyPlus('ponto.RecessoPeriodo', verbose_name='Período Escolhido/Atribuído', on_delete=models.CASCADE)

    @property
    def tem_dias_individuais_escolhidos(self):
        return self.periodos_escolhidos_dias_individuais.all().exists()

    def __str__(self):
        if self.tem_dias_individuais_escolhidos:
            return f'{self.periodo} (dias escolhidos: {", ".join([dia_individual.dia.strftime("%d/%m/%Y") for dia_individual in self.periodos_escolhidos_dias_individuais.all()])})'
        return f'{self.periodo}'

    def get_dias_escolhidos(self) -> list[datetime.date]:
        if self.tem_dias_individuais_escolhidos:
            return [dia_individual.dia for dia_individual in self.periodos_escolhidos_dias_individuais.all()]
        return self.periodo.get_dias_definidos()


class RecessoPeriodoEscolhidoDiaIndividual(models.Model):
    """Representa, dentro do contexto de uma compensação específica,
    um dia individual escolhido/atribuído por/a um servidor/funcionário
    dentro de um período escolhido/atribuído.

    Este modelo é utilizado para permitir que o servidor escolha/atribua
    apenas alguns dias do período, e não todo o período.

    Se TODOS os dias do período forem escolhidos, este modelo não será
    usado para armezenar esta informação (imagine um período de 100 dias),
    pois isso já estará totalmente satisfeito no nível acima (em ponto.RecessoPeriodoEscolhido).
    """

    class Meta:
        verbose_name = 'Período Escolhido - Dia Individual'
        verbose_name_plural = 'Períodos Escolhidos - Dias Individuais'
        ordering = ('dia',)

    recesso_periodo_escolhido = models.ForeignKeyPlus(
        'ponto.RecessoPeriodoEscolhido', editable=False, related_name='periodos_escolhidos_dias_individuais', on_delete=models.CASCADE
    )
    dia = models.DateFieldPlus('Dia Individual Escolhido/Atribuído')

    def __str__(self):
        return f'{self.dia.strftime("%d/%m/%Y")}'


class RecessoCompensacao(HorarioCompensacao):
    """
    TODO: Este modelo não é mais usado ... ao removê-lo, o makemigrations
    TODO: cria a migration de remoção que não funciona, mostrando o erro
    TODO: "App 'ponto' doesn't have a 'recessocompensacao' model."
    TODO: Por enquanto, o modelo ficará aqui "calado e mudo" ... rs

    Representa um informe de compensação de horário de um dia de recesso.
    Ponto de "conexão" com a implementação ref. aos informes de compensação de horário.
    """

    dia_escolhido = models.ForeignKeyPlus('ponto.RecessoDiaEscolhido', editable=False, on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Informe de Compensação de Horário de Recesso'
        verbose_name_plural = 'Informes de Compensação de Horário de Recessos'


class SaldoExterno(models.Model):
    """
    Representa um saldo externo que poderá ser utilizado na compensação de horários
    de um período específico.
    """

    SEARCH_FIELDS = ['servidor__pessoa_fisica__nome', 'servidor__matricula', 'detalhamento']

    SITUACAO_EM_FASE_DEFINICAO = 1
    SITUACAO_AGUARDANDO_VALIDACAO = 2
    SITUACAO_VALIDADO = 3
    SITUACAO_CHOICES = [
        [SITUACAO_EM_FASE_DEFINICAO, 'Em Fase de Cadastro'],
        [SITUACAO_AGUARDANDO_VALIDACAO, 'Aguardando Validação'],
        [SITUACAO_VALIDADO, 'Validado'],
    ]

    servidor = models.ForeignKeyPlus(
        'rh.Servidor', verbose_name='Servidor', help_text='Destinatário do Saldo.', related_name='servidor_saldo_externo'
    )

    data_cadastro = models.DateTimeFieldPlus('Data Cadastro', auto_now_add=True)
    servidor_cadastro = models.ForeignKeyPlus(
        'rh.Servidor',
        verbose_name='Servidor Cadastro',
        null=True,
        blank=True,
        help_text='Servidor que fez o cadastro.',
        related_name='servidor_cadastro_saldo_externo',
    )

    data_inicio = models.DateFieldPlus('Data Início', help_text='Data início do período de utilização do saldo.')
    data_fim = models.DateFieldPlus('Data Fim', help_text='Data fim do período de utilização do saldo.')
    valor_saldo = models.PositiveIntegerField('Valor do Saldo', help_text='Em segundos.')
    detalhamento = models.TextField('Detalhamento', null=True, blank=True)

    origem_type = models.ForeignKeyPlus(ContentType, verbose_name='Origem deste Saldo Externo', null=True, blank=True, on_delete=models.SET_NULL)
    origem_id = models.PositiveIntegerField('Origem ID', null=True, blank=True)
    origem_object = GenericForeignKey('origem_type', 'origem_id')

    validador = models.ForeignKeyPlus(
        'rh.Servidor',
        verbose_name='Validador',
        help_text='Responsável por validar este saldo externo de carga horária.',
        null=True,
        blank=True,
        related_name='servidor_validador_saldo_externo',
        on_delete=models.SET_NULL,
    )
    validador_observacoes = models.TextField('Observações sobre a Validação', null=True, blank=True)

    situacao = models.IntegerField('Situação', choices=SITUACAO_CHOICES, default=SITUACAO_EM_FASE_DEFINICAO)

    class Meta:
        verbose_name = 'Saldo Externo de Carga Horária'
        verbose_name_plural = 'Saldos Externos de Carga Horária'
        permissions = (('pode_add_saldo_externo_como_chefe', 'Pode adicionar um saldo externo como chefe'),)
        ordering = ('data_inicio',)

    @property
    def origem(self):
        return self.origem_object

    def get_origem_display(self):
        origem_type = self.origem_type
        origem = self.origem
        if origem_type and origem:
            return f'{origem_type.name}: {origem}'
        return None

    @staticmethod
    def pode_adicionar(user: User) -> bool:
        # TODO: adição inicialmente (mar/23) permitida apenas para chefes
        # TODO: futuramente, um servidor poderia cadastrar de ofício um
        # TODO: saldo externo e submeter para o trâmite de validação
        # return user.has_perm('ponto.add_saldoexterno')
        return SaldoExterno.pode_adicionar_como_chefe(user)

    @staticmethod
    def pode_adicionar_como_chefe(user: User) -> bool:
        servidor_user: Servidor = user.get_relacionamento()
        hoje = datetime.date.today()
        if not servidor_user:
            return False
        return (
            user.has_perm('ponto.add_saldoexterno')
            and servidor_user.tem_funcoes_no_periodo(hoje, hoje)
            or user.has_perm('ponto.pode_add_saldo_externo_como_chefe')
        )

    def pode_visualizar(self, user: User) -> bool:
        return self.eh_meu(user) or self.eh_minha_validacao(user)

    def pode_editar(self, user: User) -> bool:
        return self.pode_visualizar(user) and self.situacao in [SaldoExterno.SITUACAO_EM_FASE_DEFINICAO, SaldoExterno.SITUACAO_AGUARDANDO_VALIDACAO]

    def pode_encaminhar_para_validacao(self, user: User) -> bool:
        return self.eh_meu(user) and self.validador and self.situacao == SaldoExterno.SITUACAO_EM_FASE_DEFINICAO

    def pode_validar(self, user: User) -> bool:
        return self.eh_minha_validacao(user) and self.situacao == SaldoExterno.SITUACAO_AGUARDANDO_VALIDACAO

    def pode_cancelar_validacao(self, user: User) -> bool:
        return self.eh_minha_validacao(user) and self.situacao == SaldoExterno.SITUACAO_VALIDADO

    def pode_excluir(self, user: User) -> bool:
        return (
            self.pode_visualizar(user) and self.fui_eu_quem_cadastrou(user) and self.situacao != SaldoExterno.SITUACAO_VALIDADO
        ) or user.is_superuser

    def eh_meu(self, user: User):
        servidor_user: Servidor = user.get_relacionamento()
        return self.servidor == servidor_user

    def eh_minha_validacao(self, user: User):
        servidor_user: Servidor = user.get_relacionamento()
        return self.validador == servidor_user

    def fui_eu_quem_cadastrou(self, user: User):
        servidor_user: Servidor = user.get_relacionamento()
        return self.servidor_cadastro == servidor_user

    def get_absolute_url(self):
        return f'/ponto/visualizar_saldo_externo_ch/{self.id}/'

    def get_chefes(self) -> list[Servidor]:
        """lista dos chefes (servidores) no dia do cadastro"""
        servidor: Servidor = self.servidor
        return servidor.get_chefes_no_periodo(self.data_cadastro.date()).get(self.data_cadastro.date())

    @staticmethod
    def get_saldos_externos_meus(eu: User, qs_inicial: QuerySet[SaldoExterno] = None) -> QuerySet[SaldoExterno]:
        qs = qs_inicial or SaldoExterno.objects.all()
        servidor_eu = eu.get_relacionamento()
        qs = qs.filter(servidor=servidor_eu)
        return qs

    @staticmethod
    def get_saldos_externos_minhas_validacoes(eu_validador: User, qs_inicial: QuerySet[SaldoExterno] = None) -> QuerySet[SaldoExterno]:
        qs = qs_inicial or SaldoExterno.objects.all()
        servidor_validador = eu_validador.get_relacionamento()
        qs = qs.filter(validador=servidor_validador)
        return qs

    @staticmethod
    def get_saldos_externos_meus_pendentes(eu: User, qs_inicial: QuerySet[SaldoExterno] = None) -> QuerySet[SaldoExterno]:
        return SaldoExterno.get_saldos_externos_meus(eu, qs_inicial).filter(
            situacao__in=[
                SaldoExterno.SITUACAO_EM_FASE_DEFINICAO,
                SaldoExterno.SITUACAO_AGUARDANDO_VALIDACAO,
            ]
        )

    @staticmethod
    def get_saldos_externos_minhas_validacoes_pendentes(eu: User, qs_inicial: QuerySet[SaldoExterno] = None) -> QuerySet[SaldoExterno]:
        return SaldoExterno.get_saldos_externos_minhas_validacoes(eu, qs_inicial).filter(
            situacao__in=[
                SaldoExterno.SITUACAO_AGUARDANDO_VALIDACAO,
            ]
        )

    @staticmethod
    def get_saldos_externos_meus_validados(
        eu: User,
        utilizacao_data_inicio: date | None = None,
        utilizacao_data_fim: date | None = None,
        qs_inicial: QuerySet[SaldoExterno] = None,
    ) -> QuerySet[SaldoExterno]:
        if (utilizacao_data_inicio and not utilizacao_data_fim) or (utilizacao_data_fim and not utilizacao_data_inicio):
            raise ValueError('Informe um período.')
        qs = SaldoExterno.get_saldos_externos_meus(eu, qs_inicial).filter(
            situacao__in=[
                SaldoExterno.SITUACAO_VALIDADO,
            ]
        )
        if utilizacao_data_inicio and utilizacao_data_fim:
            qs = qs.filter(
                Q(data_inicio__gte=utilizacao_data_inicio, data_inicio__lte=utilizacao_data_fim)
                | Q(data_fim__gte=utilizacao_data_inicio, data_fim__lte=utilizacao_data_fim)
                | Q(data_inicio__lt=utilizacao_data_inicio, data_fim__gt=utilizacao_data_fim)
            )
        return qs

    @staticmethod
    def get_saldos_externos_meus_validados_e_disponiveis(
        eu: User, utilizacao_data_inicio: date | None = None, utilizacao_data_fim: date | None = None
    ) -> QuerySet[SaldoExterno]:
        # disponível = com saldo restante
        saldos_externos = SaldoExterno.get_saldos_externos_meus_validados(eu, utilizacao_data_inicio, utilizacao_data_fim)
        saldos_externos_disponiveis_ids = []
        for saldo_externo in saldos_externos:
            if saldo_externo.valor_saldo_restante:
                saldos_externos_disponiveis_ids.append(saldo_externo.id)
        return saldos_externos.filter(id__in=saldos_externos_disponiveis_ids)

    def get_periodo_saldo_display(self) -> str:
        return f'{self.data_inicio.strftime("%d/%m/%Y")} a {self.data_fim.strftime("%d/%m/%Y")}'

    def get_valor_saldo_display(self) -> str:
        return formata_timedelta(
            timedelta(seconds=self.valor_saldo),
            format_start='h',
            format_hours='{h}',
            format_minutes='{m:02}',
            format_seconds='{s:02}',
            format_sep=':',
            hide_milliseconds=True,
        )

    def pode_ser_utilizado_neste_debito(self, data_debito: datetime.date) -> bool:
        ###
        # origem em um objeto externo qualquer
        # para possíveis futuras implementações caso o objeto de origem redefina a forma
        # como este saldo saldo externo é utilizado
        TipoObjetoExternoQualquer = str
        origem = self.origem
        if isinstance(origem, TipoObjetoExternoQualquer):
            pass

        ###
        # padrão: data do débito deve pertencer ao período de utilização do saldo externo
        return self.data_inicio <= data_debito <= self.data_fim

    @property
    def compensacoes_informadas(self):
        return self.horariocompensacao_set.all()

    @property
    def valor_saldo_utilizado(self) -> int:
        # TODO: potencial gargalo de desempenho
        qtd: int = 0
        for compensacao in self.compensacoes_informadas:
            qtd += Frequencia.time_para_segundos(compensacao.ch_compensada)
        return qtd

    @property
    def valor_saldo_restante(self) -> int:
        return self.valor_saldo - self.valor_saldo_utilizado

    def get_valor_saldo_utilizado_display(self) -> str:
        valor_saldo_utilizado = self.valor_saldo_utilizado
        qtd = formata_timedelta(
            timedelta(seconds=valor_saldo_utilizado),
            format_start='h',
            format_hours='{h}',
            format_minutes='{m:02}',
            format_seconds='{s:02}',
            format_sep=':',
            hide_milliseconds=True,
        )
        percentual = ((valor_saldo_utilizado * 100) / self.valor_saldo) if self.valor_saldo else 0.0
        if percentual > 100.0:
            percentual = 100.0
        return f'{qtd} ({percentual:.0f}%)'

    def get_valor_saldo_restante_display(self) -> str:
        return formata_timedelta(
            timedelta(seconds=self.valor_saldo_restante),
            format_start='h',
            format_hours='{h}',
            format_minutes='{m:02}',
            format_seconds='{s:02}',
            format_sep=':',
            hide_milliseconds=True,
        )

    def __str__(self) -> str:
        detalhes = self.detalhamento or f'Cadastrado em {self.data_cadastro.strftime("%d/%m/%Y")}'
        return f'Saldo Externo #{self.id} de {self.get_valor_saldo_display()} ({detalhes})'

    @property
    def periodo_utilizacao_is_fim_de_semana(self):
        """compatibilizar com as restrições do relatório de frequências"""
        for dia in datas_entre(self.data_inicio, self.data_fim):
            is_fim_de_semana = dia.weekday() >= 5
            if not is_fim_de_semana:
                return False  # algum dia do período não é fim de semana
        return True

    def get_situacao_display_html(self):
        status = ''
        if self.situacao == SaldoExterno.SITUACAO_EM_FASE_DEFINICAO:
            status = 'info'
        if self.situacao == SaldoExterno.SITUACAO_AGUARDANDO_VALIDACAO:
            status = 'alert'
        if self.situacao == SaldoExterno.SITUACAO_VALIDADO:
            status = 'aceito'
        return mark_safe(f'<span class="status status-{status}">{self.get_situacao_display()}</span>')

    @staticmethod
    def get_saldos_externos_from_origem(model_instance_origem) -> QuerySet[SaldoExterno]:
        return SaldoExterno.objects.filter(origem_type=ContentType.objects.get_for_model(model_instance_origem), origem_id=model_instance_origem.id)

    @property
    def is_validado(self):
        return self.situacao == SaldoExterno.SITUACAO_VALIDADO

    @staticmethod
    def get_valores_totais(
        saldos_externos: list[SaldoExterno], valor_saldo: bool = True, valor_utilizado: bool = True, valor_restante: bool = True
    ) -> dict[str, tuple[int, str]]:
        """
        Retorna:
            {
                #                    valor  display
                'valor_saldo'       : (0, '00:00:00'),
                'valor_utilizado'   : (0, '00:00:00'),
                'valor_restante'    : (0, '00:00:00'),
            }
        """

        def get_valor_display(valor):
            return formata_timedelta(
                timedelta(seconds=valor),
                format_start='h',
                format_hours='{h}',
                format_minutes='{m:02}',
                format_seconds='{s:02}',
                format_sep=':',
                hide_milliseconds=True,
            )

        total_valor_saldo = 0
        total_valor_utilizado = 0
        total_valor_restante = 0

        for saldo_externo in saldos_externos:
            total_valor_saldo += saldo_externo.valor_saldo if valor_saldo else 0
            total_valor_utilizado += saldo_externo.valor_saldo_utilizado if valor_utilizado else 0
            total_valor_restante += saldo_externo.valor_saldo_restante if valor_restante else 0

        return {
            'valor_saldo': (total_valor_saldo, get_valor_display(total_valor_saldo)),
            'valor_utilizado': (total_valor_utilizado, get_valor_display(total_valor_utilizado)),
            'valor_restante': (total_valor_restante, get_valor_display(total_valor_restante)),
        }

    # ---------------------
    class CadastrarSaldoExternoResult:
        cadastro: SaldoExterno

        @property
        def is_realizado(self) -> bool:
            return self.cadastro is not None

        @property
        def total_saldo_em_segundos(self) -> int:
            return self.cadastro.valor_saldo if self.is_realizado else 0

        @property
        def is_validado(self) -> bool:
            return self.cadastro.situacao == SaldoExterno.SITUACAO_VALIDADO if self.is_realizado else False

        @property
        def total_distribuido_em_segundos(self) -> int:
            return self.cadastro.valor_saldo_utilizado if self.is_realizado else 0

        @property
        def is_totalmente_distribuido(self) -> bool:
            return self.cadastro.valor_saldo_restante == 0 if self.is_realizado else False

    @staticmethod
    def cadastrar_saldo_externo(
        data_cadastro: datetime.datetime,
        servidor_destinatario: Servidor,
        valor_saldo_em_segundos: int,
        data_inicio_utilizacao: datetime.date,
        data_fim_utilizacao: datetime.date,
        informar_compensacao_automaticamente: bool = False,
        servidor_cadastrador: Servidor = None,
        servidor_validador: Servidor = None,
        observacoes_servidor_validador: str = '',
        situacao: int | None = None,
        detalhamento: str = '',
        model_instance_origem=None,
        unique_together_with_model_instance_origem=True,  # 1 model_instance_origem ---> 0..1 saldo externo
    ) -> CadastrarSaldoExternoResult:
        """Permite o cadastro de um saldo externo para um servidor destinatário.
            - data_cadastro: é a data do cadastro (padrão hoje)
            - servidor_destinatario: é o servidor destinatário do saldo
            - valor_saldo_em_segundos: é o valor saldo em segundos
            - data_inicio_utilizacao e data_fim_utilizacao: é o período de utilização do saldo (onde estão os débitos?)

        É possível distribuir o saldo informado no período de utilização imediatamente, salvando os
        informes de compensação.
            - informar_compensacao_automaticamente: distribuir e salvar os informes de compensação ou não

        É possível informar os servidores cadastrador e validador. Por padrão,
        o cadastrador e o validador será o chefe imediato do servidor
        destinatário na data do cadastro.
            - servidor_cadastrador: é o servidor que está cadastrando
            - servidor_validador: é o servidor validador do saldo (DEVE SER DIFERENTE DE servidor_destinatario para não haver a auto-validação)
            - observacoes_servidor_validador: observações do servidor validador

        Também é possível informar a situação do cadastro, que por padrão entrará
        em fase de cadastro/definição (valor SaldoExterno.SITUACAO_EM_FASE_DEFINICAO).
        No caso de informar_compensacao_automaticamente = True, a situação será de saldo
        externo validado (valor SaldoExterno.SITUACAO_VALIDADO).
            - situacao: situação do cadastro do saldo (ver SaldoExterno.SITUACAO_CHOICES)

        Outros dados incluem uma descrição sobre o saldo externo em questão e sua origem.
            - detalhamento: descrição a respeito do saldo
            - model_instance_origem: instância de um model que representa a origem do saldo (NÃO DEVE SER a mesma instância do saldo para evitar a circularidade)
        """
        if model_instance_origem and unique_together_with_model_instance_origem:
            # não haverá saldos externos duplicados para uma mesma origem
            saldo_externo_anterior = SaldoExterno.get_saldos_externos_from_origem(model_instance_origem)
            if saldo_externo_anterior.exists():
                saldo_externo_anterior.delete()

        data_cadastro = data_cadastro or datetime.datetime.now()

        chefe_imediato: Servidor = None

        if not servidor_cadastrador or not servidor_validador:
            chefes = servidor_destinatario.get_chefes_no_periodo(data_cadastro.date(), data_cadastro.date()).get(data_cadastro.date())
            chefe_imediato = chefes[0] if chefes else None

        servidor_cadastrador = servidor_cadastrador or chefe_imediato
        servidor_validador = servidor_validador or chefe_imediato

        situacao = situacao or SaldoExterno.SITUACAO_EM_FASE_DEFINICAO

        if not servidor_validador and situacao == SaldoExterno.SITUACAO_VALIDADO:
            situacao = SaldoExterno.SITUACAO_EM_FASE_DEFINICAO

        if servidor_validador and informar_compensacao_automaticamente:
            situacao = SaldoExterno.SITUACAO_VALIDADO

        saldo_externo = SaldoExterno()
        saldo_externo.data_cadastro = data_cadastro
        saldo_externo.servidor = servidor_destinatario
        saldo_externo.servidor_cadastro = servidor_cadastrador
        saldo_externo.data_inicio = data_inicio_utilizacao
        saldo_externo.data_fim = data_fim_utilizacao
        saldo_externo.valor_saldo = valor_saldo_em_segundos
        saldo_externo.detalhamento = detalhamento or ''
        if model_instance_origem:
            saldo_externo.origem_object = model_instance_origem
            saldo_externo.origem_id = model_instance_origem.id
        saldo_externo.validador = servidor_validador
        saldo_externo.validador_observacoes = observacoes_servidor_validador or ''
        saldo_externo.situacao = situacao
        saldo_externo.save()

        if informar_compensacao_automaticamente and servidor_validador and situacao == SaldoExterno.SITUACAO_VALIDADO:
            from ponto import compensacao

            periodo = compensacao.get_periodo_info(
                user=servidor_destinatario.get_user(),
                periodo_data_inicio=data_inicio_utilizacao,
                periodo_data_fim=data_fim_utilizacao,
                periodo_objetivo=compensacao.PeriodoInfo.PERIODO_OBJETIVO_DEBITO,
                abrange_apenas_saldos_externos=True,
                abrange_apenas_esses_saldos_externos_ids=[saldo_externo.id],
            )

            processamento = compensacao.get_periodo_processamento_info(
                periodo,
                values=None,  # força a distribuição automática do saldo externo
            )

            processamento.salva_compensacoes()

        result: SaldoExterno.CadastrarSaldoExternoResult = SaldoExterno.CadastrarSaldoExternoResult()
        result.cadastro = saldo_externo

        return result


class DebitoExternoCadastro(models.Model):
    """
    Representa um cadastro de débito externo distribuído/detalhado em um ou mais
    dias específicos.
    """

    SITUACAO_EM_FASE_DEFINICAO = 1
    SITUACAO_AGUARDANDO_VALIDACAO = 2
    SITUACAO_VALIDADO = 3
    SITUACAO_CHOICES = [
        [SITUACAO_EM_FASE_DEFINICAO, 'Em Fase de Cadastro'],
        [SITUACAO_AGUARDANDO_VALIDACAO, 'Aguardando Validação'],
        [SITUACAO_VALIDADO, 'Validado'],
    ]

    servidor = models.ForeignKeyPlus(
        'rh.Servidor', verbose_name='Servidor', help_text='Destinatário do Débito.', related_name='servidor_debito_externo'
    )

    data_cadastro = models.DateTimeFieldPlus('Data Cadastro', auto_now_add=True)
    servidor_cadastro = models.ForeignKeyPlus(
        'rh.Servidor',
        verbose_name='Servidor Cadastro',
        null=True,
        blank=True,
        help_text='Servidor que fez o cadastro.',
        related_name='servidor_cadastro_debito_externo',
    )

    total_debito = models.PositiveIntegerField('Total do Débito', help_text='Em segundos.')
    detalhamento = models.TextField('Detalhamento', null=True, blank=True)

    origem_type = models.ForeignKeyPlus(ContentType, verbose_name='Origem deste Débito Externo', null=True, blank=True, on_delete=models.SET_NULL)
    origem_id = models.PositiveIntegerField('Origem ID', null=True, blank=True)
    origem_object = GenericForeignKey('origem_type', 'origem_id')

    validador = models.ForeignKeyPlus(
        'rh.Servidor',
        verbose_name='Validador',
        help_text='Responsável por validar este débito externo de carga horária.',
        null=True,
        blank=True,
        related_name='servidor_validador_debito_externo',
        on_delete=models.SET_NULL,
    )
    validador_observacoes = models.TextField('Observações sobre a Validação', null=True, blank=True)

    situacao = models.IntegerField('Situação', choices=SITUACAO_CHOICES, default=SITUACAO_EM_FASE_DEFINICAO)

    class Meta:
        verbose_name = 'Cadastro de Débito Externo de Carga Horária'
        verbose_name_plural = 'Cadastros de Débitos Externos de Carga Horária'
        permissions = (('pode_add_debito_externo_cadastro_como_chefe', 'Pode adicionar um cadastro de débito externo como chefe'),)
        ordering = ('data_cadastro',)

    @property
    def origem(self):
        return self.origem_object

    def get_origem_display(self):
        origem_type = self.origem_type
        origem = self.origem
        if origem_type and origem:
            return f'{origem_type.name}: {origem}'
        return None

    @staticmethod
    def pode_adicionar(user: User) -> bool:
        # TODO: adição inicialmente (mar/23) permitida apenas para chefes
        # TODO: futuramente, um servidor poderia cadastrar de ofício um
        # TODO: débito externo e submeter para o trâmite de validação
        # return user.has_perm('ponto.add_debitoexternocadastro')
        return DebitoExternoCadastro.pode_adicionar_como_chefe(user)

    @staticmethod
    def pode_adicionar_como_chefe(user: User) -> bool:
        servidor_user: Servidor = user.get_relacionamento()
        hoje = datetime.date.today()
        if not servidor_user:
            return False
        return (
            user.has_perm('ponto.add_debitoexternocadastro')
            and servidor_user.tem_funcoes_no_periodo(hoje, hoje)
            or user.has_perm('ponto.pode_add_debito_externo_cadastro_como_chefe')
        )

    def pode_visualizar(self, user: User) -> bool:
        return self.eh_meu(user) or self.eh_minha_validacao(user)

    def pode_editar(self, user: User) -> bool:
        return self.pode_visualizar(user) and self.situacao in [
            DebitoExternoCadastro.SITUACAO_EM_FASE_DEFINICAO,
            DebitoExternoCadastro.SITUACAO_AGUARDANDO_VALIDACAO,
        ]

    def pode_encaminhar_para_validacao(self, user: User) -> bool:
        return (
            self.get_dias_dos_debitos().exists()
            and self.eh_meu(user)
            and self.validador
            and self.situacao == DebitoExternoCadastro.SITUACAO_EM_FASE_DEFINICAO
        )

    def pode_validar(self, user: User) -> bool:
        return (
            self.get_dias_dos_debitos().exists()
            and self.eh_minha_validacao(user)
            and self.situacao == DebitoExternoCadastro.SITUACAO_AGUARDANDO_VALIDACAO
        )

    def pode_cancelar_validacao(self, user: User) -> bool:
        return self.eh_minha_validacao(user) and self.situacao == DebitoExternoCadastro.SITUACAO_VALIDADO

    def pode_excluir(self, user: User) -> bool:
        return (
            self.pode_visualizar(user) and self.fui_eu_quem_cadastrou(user) and self.situacao != DebitoExternoCadastro.SITUACAO_VALIDADO
        ) or user.is_superuser

    def eh_meu(self, user: User):
        servidor_user: Servidor = user.get_relacionamento()
        return self.servidor == servidor_user

    def eh_minha_validacao(self, user: User):
        servidor_user: Servidor = user.get_relacionamento()
        return self.validador == servidor_user

    def fui_eu_quem_cadastrou(self, user: User):
        servidor_user: Servidor = user.get_relacionamento()
        return self.servidor_cadastro == servidor_user

    def get_absolute_url(self):
        return f'/ponto/visualizar_debito_externo_ch_cadastro/{self.id}/'

    def get_chefes(self) -> list[Servidor]:
        """lista dos chefes (servidores) no dia do cadastro"""
        servidor: Servidor = self.servidor
        return servidor.get_chefes_no_periodo(self.data_cadastro.date()).get(self.data_cadastro.date())

    @staticmethod
    def get_debitos_externos_cadastros_meus(eu: User, qs_inicial: QuerySet[DebitoExternoCadastro] = None) -> QuerySet[DebitoExternoCadastro]:
        qs = qs_inicial or DebitoExternoCadastro.objects.all()
        servidor_eu = eu.get_relacionamento()
        qs = qs.filter(servidor=servidor_eu)
        return qs

    @staticmethod
    def get_debitos_externos_cadastros_minhas_validacoes(
        eu_validador: User, qs_inicial: QuerySet[DebitoExternoCadastro] = None
    ) -> QuerySet[DebitoExternoCadastro]:
        qs = qs_inicial or DebitoExternoCadastro.objects.all()
        servidor_validador = eu_validador.get_relacionamento()
        qs = qs.filter(validador=servidor_validador)
        return qs

    @staticmethod
    def get_debitos_externos_cadastros_meus_pendentes(
        eu: User, qs_inicial: QuerySet[DebitoExternoCadastro] = None
    ) -> QuerySet[DebitoExternoCadastro]:
        return DebitoExternoCadastro.get_debitos_externos_cadastros_meus(eu, qs_inicial).filter(
            situacao__in=[
                DebitoExternoCadastro.SITUACAO_EM_FASE_DEFINICAO,
                DebitoExternoCadastro.SITUACAO_AGUARDANDO_VALIDACAO,
            ]
        )

    @staticmethod
    def get_debitos_externos_cadastros_minhas_validacoes_pendentes(
        eu: User, qs_inicial: QuerySet[DebitoExternoCadastro] = None
    ) -> QuerySet[DebitoExternoCadastro]:
        return DebitoExternoCadastro.get_debitos_externos_cadastros_minhas_validacoes(eu, qs_inicial).filter(
            situacao__in=[
                DebitoExternoCadastro.SITUACAO_AGUARDANDO_VALIDACAO,
            ]
        )

    @staticmethod
    def get_debitos_externos_cadastros_meus_validados(
        eu: User, qs_inicial: QuerySet[DebitoExternoCadastro] = None
    ) -> QuerySet[DebitoExternoCadastro]:
        return DebitoExternoCadastro.get_debitos_externos_cadastros_meus(eu, qs_inicial).filter(
            situacao__in=[
                DebitoExternoCadastro.SITUACAO_VALIDADO,
            ]
        )

    def get_dias_dos_debitos(self) -> QuerySet[DebitoExterno]:
        return self.debitos_externos_dias.all()

    def get_total_dias_valor_debito(self) -> int:
        total = 0
        for dia_do_debito in self.get_dias_dos_debitos():
            total += dia_do_debito.valor_debito
        return total

    def get_erros(self) -> list[str]:
        msg: list[str] = []

        total_dias_valor_debito = self.get_total_dias_valor_debito()
        total_dias_valor_debito_display = formata_timedelta(
            timedelta(seconds=total_dias_valor_debito),
            format_start='h',
            format_hours='{h}',
            format_minutes='{m:02}',
            format_seconds='{s:02}',
            format_sep=':',
            hide_milliseconds=True,
        )

        if self.total_debito != total_dias_valor_debito:
            msg.append(
                f'O total de débito cadastrado ({self.get_total_debito_display()}) não confere com o total de débito informado nos dias ({total_dias_valor_debito_display}).'
            )

        return msg

    def __str__(self):
        detalhes = self.detalhamento or f'Cadastrado em {self.data_cadastro.strftime("%d/%m/%Y")}'
        return f'Débito Externo de {self.get_total_debito_display()} ({detalhes})'

    def get_total_debito_display(self) -> str:
        return formata_timedelta(
            timedelta(seconds=self.total_debito),
            format_start='h',
            format_hours='{h}',
            format_minutes='{m:02}',
            format_seconds='{s:02}',
            format_sep=':',
            hide_milliseconds=True,
        )

    @property
    def compensacoes_informadas(self):
        return HorarioCompensacao.objects.filter(
            funcionario=self.servidor, data_aplicacao__in=[dia_debito.data_debito for dia_debito in self.get_dias_dos_debitos()]
        )

    @property
    def total_debito_compensado(self) -> int:
        # TODO: potencial gargalo de desempenho
        qtd: int = 0
        for compensacao in self.compensacoes_informadas:
            qtd += Frequencia.time_para_segundos(compensacao.ch_compensada)
        return qtd

    @property
    def total_debito_restante(self) -> int:
        qtd = self.total_debito - self.total_debito_compensado
        if qtd < 0:
            # isso pode ocorrer no caso de excesso
            # nos informes de compensação (até possíveis duplicatas), os quais
            # podem/devem ser gerenciados separadamente pelo servidor
            qtd = 0
        return qtd

    def get_total_debito_compensado_display(self) -> str:
        total_debito_compensado = self.total_debito_compensado
        qtd = formata_timedelta(
            timedelta(seconds=total_debito_compensado),
            format_start='h',
            format_hours='{h}',
            format_minutes='{m:02}',
            format_seconds='{s:02}',
            format_sep=':',
            hide_milliseconds=True,
        )
        percentual = ((total_debito_compensado * 100) / self.total_debito) if self.total_debito else 0.0
        if percentual > 100.0:
            percentual = 100.0
        return f'{qtd} ({percentual:.0f}%)'

    def get_total_debito_restante_display(self) -> str:
        return formata_timedelta(
            timedelta(seconds=self.total_debito_restante),
            format_start='h',
            format_hours='{h}',
            format_minutes='{m:02}',
            format_seconds='{s:02}',
            format_sep=':',
            hide_milliseconds=True,
        )

    def get_situacao_display_html(self):
        status = ''
        if self.situacao == DebitoExternoCadastro.SITUACAO_EM_FASE_DEFINICAO:
            status = 'info'
        if self.situacao == DebitoExternoCadastro.SITUACAO_AGUARDANDO_VALIDACAO:
            status = 'alert'
        if self.situacao == DebitoExternoCadastro.SITUACAO_VALIDADO:
            status = 'aceito'
        return mark_safe(f'<span class="status status-{status}">{self.get_situacao_display()}</span>')

    @property
    def is_situacao_em_aberto(self):
        return self.situacao in [DebitoExternoCadastro.SITUACAO_EM_FASE_DEFINICAO, DebitoExternoCadastro.SITUACAO_AGUARDANDO_VALIDACAO]

    @staticmethod
    def get_debitos_externos_cadastros_from_origem(model_instance_origem) -> QuerySet[DebitoExternoCadastro]:
        return DebitoExternoCadastro.objects.filter(
            origem_type=ContentType.objects.get_for_model(model_instance_origem), origem_id=model_instance_origem.id
        )

    @property
    def is_validado(self):
        return self.situacao == DebitoExternoCadastro.SITUACAO_VALIDADO

    # ---------------------

    @staticmethod
    def cadastrar_debito_externo(
        data_cadastro: datetime.datetime,
        servidor_destinatario: Servidor,
        total_debito_em_segundos: int,
        servidor_cadastrador: Servidor = None,
        servidor_validador: Servidor = None,
        observacoes_servidor_validador: str = '',
        situacao: int | None = None,
        dias_debitos_auto: list[datetime.date] | None = None,
        dias_debitos_manual: list[datetime.date] | None = None,
        detalhamento: str = '',
        model_instance_origem=None,
        unique_together_with_model_instance_origem=True,  # 1 model_instance_origem ---> 0..1 débito externo
    ) -> DebitoExternoCadastro:
        """Permite o cadastro de um débito externo para um servidor destinatário.
            - data_cadastro: é a data do cadastro (padrão agora)
            - servidor_destinatario: é o servidor destinatário do débito
            - total_debito_em_segundos: é o total de débitos em segundos

        É possível informar os servidores cadastrador e validador. Por padrão,
        o cadastrador e o validador será o chefe imediato do servidor
        destinatário na data do cadastro.
            - servidor_cadastrador: é o servidor que está cadastrando
            - servidor_validador: é o servidor validador do débito (DEVE SER DIFERENTE DE servidor_destinatario para não haver a auto-validação)
            - observacoes_servidor_validador: observações do servidor validador

        Também é possível informar a situação do cadastro, que por padrão entrará
        em fase de cadastro/definição (valor DebitoExternoCadastro.SITUACAO_EM_FASE_DEFINICAO).
            - situacao: situação do cadastro do débito (ver DebitoExternoCadastro.SITUACAO_CHOICES)

        Sobre os dias dos débitos e seus valores de débito individuais:
            - Valores automáticos: usado em situações em que não está previsto ou não é
              desejado o 'trâmite' normal de um débito externo (cadastro/definição ->
              validação -> aplicação), ou ainda quando não se faz necessário ter conhecimento
              sobre esse trâmite.
                - dias_debitos_auto: uma lista de um ou mais dias que serão cadastrados
                e, pelos quais, o total dos débitos será distribuído automaticamente,
                forçando, caso não tenha sido informada, a situação do cadastro para
                validado (valor DebitoExternoCadastro.SITUACAO_VALIDADO).

            - Valores manuais: usado em situações que se deseja iniciar o trâmite já sabendo
              o total dos débitos e os dias dos débitos, porém estes ainda sem valores individuais
              definidos.
                - dias_debitos_manual: uma lista de um ou mais dias que serão cadastrados
                e inicializados com o valor de zero débitos para que seja editado posteriormente,
                forçando, caso não tenha sido informada, a situação do cadastro para
                fase de definição/cadastro (valor DebitoExternoCadastro.SITUACAO_EM_FASE_DEFINICAO).

            - ATT: apenas UM dos parâmetros deverá ser informado (ou dias_debitos_auto ou dias_debitos_manual).

        Outros dados incluem uma descrição sobre o débito externo em questão e sua origem.
            - detalhamento: descrição a respeito do débito
            - model_instance_origem: instância de um model que representa a origem do débito (NÃO DEVE SER a mesma instância do débito para evitar a circularidade)
        """
        if model_instance_origem and unique_together_with_model_instance_origem:
            # não haverá débitos externos duplicados para uma mesma origem
            debito_externo_anterior = DebitoExternoCadastro.get_debitos_externos_cadastros_from_origem(model_instance_origem)
            if debito_externo_anterior.exists():
                debito_externo_anterior.delete()

        data_cadastro = data_cadastro or datetime.datetime.now()

        chefe_imediato: Servidor = None

        if not servidor_cadastrador or not servidor_validador:
            chefes = servidor_destinatario.get_chefes_no_periodo(data_cadastro.date(), data_cadastro.date()).get(data_cadastro.date())
            chefe_imediato = chefes[0] if chefes else None

        servidor_cadastrador = servidor_cadastrador or chefe_imediato
        servidor_validador = servidor_validador or chefe_imediato

        situacao = situacao or DebitoExternoCadastro.SITUACAO_EM_FASE_DEFINICAO

        assert not (dias_debitos_auto and dias_debitos_manual)
        assert dias_debitos_auto or dias_debitos_manual

        if dias_debitos_auto:
            situacao = DebitoExternoCadastro.SITUACAO_VALIDADO
        elif dias_debitos_manual:
            situacao = DebitoExternoCadastro.SITUACAO_EM_FASE_DEFINICAO

        # cadastro
        cadastro = DebitoExternoCadastro()
        cadastro.data_cadastro = data_cadastro
        cadastro.servidor = servidor_destinatario
        cadastro.servidor_cadastro = servidor_cadastrador
        cadastro.total_debito = total_debito_em_segundos
        cadastro.detalhamento = detalhamento or ''
        cadastro.validador = servidor_validador
        cadastro.validador_observacoes = observacoes_servidor_validador or ''
        if model_instance_origem:
            cadastro.origem_object = model_instance_origem
            cadastro.origem_id = model_instance_origem.id
        cadastro.situacao = situacao
        cadastro.save()

        # processa os dias dos débitos

        if dias_debitos_auto:
            from ponto.compensacao import Contexto, SituacaoDia

            contexto = Contexto(servidor_destinatario, min(dias_debitos_auto), max(dias_debitos_auto))

            dias_validos: list[datetime.date] = []

            for dia in sorted(dias_debitos_auto):
                situacao_dia: SituacaoDia = contexto.get_dia(dia)

                dia_pode_haver_debito = situacao_dia.is_dia_que_pode_haver_debito

                if dia_pode_haver_debito:
                    dias_validos.append(dia)

            total_debito_restante = total_debito_em_segundos

            if dias_validos:
                dia_debito_externo: dict[datetime.date, DebitoExterno] = {}

                while total_debito_restante > 0:
                    valor_debito_do_dia = int(total_debito_restante / len(dias_validos))

                    # trata possível loop infinito:
                    # total_debito_restante = 50s, dias_validos = 60
                    # valor_debito_do_dia = int(50 / 60) = int(0,8333333333333333) = 0
                    # se valor_debito_do_dia = 0, então valor_debito_do_dia = 50s (será colocado no primeiro dia em dias_validos)
                    if valor_debito_do_dia == 0:
                        valor_debito_do_dia = total_debito_restante

                    for dia in sorted(dias_validos):
                        debito = dia_debito_externo.get(dia)

                        if not debito:
                            debito = DebitoExterno()
                            debito.cadastro = cadastro
                            debito.data_debito = dia
                            debito.valor_debito = valor_debito_do_dia
                            debito.observacoes = 'O valor do débito deste dia foi calculado automaticamente (o valor total do débito externo foi dividido em partes iguais). '
                        else:
                            debito.valor_debito += valor_debito_do_dia
                            debito.observacoes += f'Em seguida foi acrescentado {formata_segundos_h_min_seg(valor_debito_do_dia)} a mais para comportar o valor total do débito externo. '

                        debito.save()

                        dia_debito_externo[dia] = debito

                        total_debito_restante -= valor_debito_do_dia

                        if total_debito_restante == 0:
                            break

            if total_debito_restante > 0:
                # não foi possível distribuir o total de débitos através dos dias
                # os débitos externos ainda não podem ser aplicados (segue o trâmite)
                cadastro.situacao = DebitoExternoCadastro.SITUACAO_EM_FASE_DEFINICAO
                cadastro.save()

        elif dias_debitos_manual:
            # apenas cadastra os dias com valor do débito igual a zero
            for dia in sorted(dias_debitos_manual):
                debito = DebitoExterno()
                debito.cadastro = cadastro
                debito.data_debito = dia
                debito.valor_debito = 0
                debito.observacoes = ''
                debito.save()

        return cadastro


class DebitoExterno(models.Model):
    """
    Representa um débito externo atribuído a um dia específico como parte da
    distribuição/detalhamento de um cadastro de débito externo, alterando o cálculo
    da situação do dia em questão para fins de compensação de horários.

    Sobre as fontes para o cálculo do débito de um dia:

        Débito externo do Dia  <------  Dia ------> Frequência do Dia

    -------------------------

    Problemática dos débitos externos de período (à maneira de saldos externos):

                |-----------.----------| período consultado

                            |----------.----| saldo externo (período de utilização = onde estão os débitos?)

            |-a-.-----b-----.--c--| débito externo (período de aplicação = onde serão os débitos?)

            Sobre os totais de saldos e débitos do período consultado:
                - saldos: saldos "normais" do período + saldos externos que cobrem o período
                - débitos: débitos "normais" do período  + débitos externos que cobrem o período
                - os valores de saldos e débitos externos que cobrem o período seriam IMPRECISOS
                pois porções de seus períodos estariam fora do período consultado ... mesmo assim,
                seria uma informação útil e considerada correta para o usuário.

            Sobre compensar os débitos do período consultado:
                - para os débitos "normais" do período
                    - inclui os saldos "normais" que estão dentro do período de compensação do débito
                        - período de compensação: período padrão + períodos específicos (de compensações específicas)
                    - inclui os saldos externos cujo período de utilização contém o dia do débito

                - para débitos externos:
                    - inclui os saldos "normais" que estão dentro do período de compensação do débito externo
                        - TODO problemática A: o período de compensação do débito externo incluiria um período padrão
                        assim como existe a regra do mês seguinte para o débito "padrão"
                    - inclui os saldos externos cujo período (ou parte dele) contém o período (ou parte dele)
                    do débito externo
                        - TODO problemática B: o saldo externo poderia cobrir uma porção do período do débito externo
                        que está fora do período de utilização do saldo

            Sobre utilizar os saldos do período consultado:
                - para os saldos "normais" do período
                    - inclui os débitos "normais" que estão dentro do período de utilização do saldo
                        - período de utilização: apenas o período padrão
                    - inclui os débitos externos cujo período de compensação contém o saldo
                        - TODO problemática A acima

                - para os saldos externos
                    - inclui os débitos "normais" que pertencem ao período de utilização do saldo externo

                    - inclui os débitos externos cujo período (ou parte dele) contém o período (ou parte dele)
                    do saldo externo
                        - TODO problemática B acima
    """

    cadastro = models.ForeignKeyPlus('ponto.DebitoExternoCadastro', verbose_name='Cadastro', related_name='debitos_externos_dias')

    data_debito = models.DateFieldPlus('Data do Débito', help_text='Data na qual o débito externo será aplicado.')
    valor_debito = models.PositiveIntegerField('Valor do Débito', help_text='Em segundos.')
    observacoes = models.TextField('Observações Adicionais', null=True, blank=True)

    class Meta:
        verbose_name = 'Débito Externo de Carga Horária'
        verbose_name_plural = 'Débitos Externos de Carga Horária'
        ordering = ('data_debito',)

    def pode_editar(self, user: User) -> bool:
        debito_externo_cadastro: DebitoExternoCadastro = self.cadastro
        return debito_externo_cadastro.pode_editar(user)

    def pode_excluir(self, user: User) -> bool:
        return self.pode_editar(user)

    def get_chefes(self) -> list[Servidor]:
        """lista dos chefes (servidores) no dia do débito"""
        servidor: Servidor = self.servidor
        return servidor.get_chefes_no_periodo(self.data_debito).get(self.data_debito)

    def get_valor_debito_display(self) -> str:
        return formata_timedelta(
            timedelta(seconds=self.valor_debito),
            format_start='h',
            format_hours='{h}',
            format_minutes='{m:02}',
            format_seconds='{s:02}',
            format_sep=':',
            hide_milliseconds=True,
        )

    def get_valor_debito_display_2(self) -> str:
        return formata_timedelta(timedelta(seconds=self.valor_debito), 'h', '', '{h}h', '{m:02}min', '{s:02}seg')

    def __str__(self):
        return f'{self.get_valor_debito_display()} como parte de {self.cadastro}'


##########################################################################################
##########################################################################################


class RelatorioPontoPessoaDiaInfo:
    """
    Representa uma linha (um dia) do relatório de ponto calculado pelo
    método Frequencia.relatorio_ponto_pessoa, o qual calcula e popula
    todos os atributos desta classe.
    """

    dia: date

    estah_no_pgd: str  # uma mensagem
    excluido: str  # uma mensagem

    # TODO: poderia ser apenas 1 attr
    liberado: bool  # via afastamentos, viagens, férias, liberações
    dia_liberado_frequencia: bool  # via cargo de função

    afastamento_parcial: ServidorAfastamento
    afastamentos_siape: list[AfastamentoSiape]
    afastamentos_rh: list[Afastamento]
    viagens_scdp: list[Viagem]
    ferias: str  # uma mensagem

    liberacoes: list[Liberacao]
    liberacoes_exceto_parciais: list[Liberacao]
    liberacoes_parciais_ch_horaria_maxima_exigida: int  # em horas
    liberacoes_parciais_ch_horaria_maxima_exigida_segundos: int
    tem_liberacao_de_ponto_no_dia: bool
    tem_liberacao_parcial_de_ponto_no_dia: bool

    observacoes: list[Observacao]
    anexos: list[DocumentoAnexo]
    abonos_chefia: list[AbonoChefia]
    abonos_parciais: list[SolicitacaoAbonoParcial]
    revisoes_abonos_chefia: list[SolicitacaoRevisaoAbonoChefia]

    tem_funcao_chefia: bool
    pode_abonar_dia: bool

    semana: int  # a ordem da semana onde o dia se encontra dentro de um período
    jornada_trabalho: JornadaTrabalho
    horarios: list[Frequencia]
    horarios_dia: list[date]
    carga_horaria_do_dia: int  # em horas
    carga_horaria_do_dia_segundos: int
    carga_horaria_do_dia_h: int  # 0 a N
    carga_horaria_do_dia_m: int  # 0 a 59
    carga_horaria_do_dia_s: int  # 0 a 59
    motivo_carga_horaria_do_dia: str
    origem_carga_horaria_do_dia: str
    duracao: str
    duracao_bruto: str
    duracao_segundos: int
    duracao_segundos_bruto: int
    hora_extra_noturna: int

    acao_abono_inconsistencia: str
    tem_inconsistencia_inferior: bool
    tem_inconsistencia_superior: bool

    duracao_computada: str

    informacoes_registro: list[str]  # lista dos valores das constantes das inconsistências do dia
    informacoes_registro_display: list[
        dict
    ]  # lista dos objetos usados para fins de exibição das inconsistências do dia (ver Frequencia.DISPLAY_INCONSISTENCIA)

    # para fins de totais
    tempo_abonado: int
    tempo_trabalho_remoto: int
    tempo_abonado_para_compensacao: int
    tempo_nao_abonado: int
    hora_extra_nao_justificada: int
    hora_extra_justificada: int
    hora_extra_para_compensacao_carga_horaria: int
    trabalho_fds_permitido_para_compensacao_carga_horaria: int
    trabalho_fds_permitido_como_hora_extra: int
    trabalho_fds_nao_permitido: int
    tempo_total_hora_extra_noturna: int
    tempo_total_horas_trabalhadas: int
    tempo_total_carga_horaria: int

    compensacao: dict

    # atributos demandados a partir da funcionalidade de abono parcial (Demanda 1547)
    permite_solicitacao_abono_parcial: bool

    # atributos adicionais podem ser acrescentados via método ponto.models.Frequencia.relatorio_ponto_pessoa_update

    # outros
    tem_inconsistencia_calculo_adiado: bool
    trata_inconsistencias_calculo_adiado: bool
    final_dict_remove_keys: list[str]

    def __init__(self, dia: date, final_dict_remove_keys: list[str] | None = None):
        self.dia = dia

        self.estah_no_pgd = ''
        self.excluido = ''

        self.liberado = False
        self.dia_liberado_frequencia = False

        self.afastamento_parcial = None
        self.afastamentos_siape = []
        self.afastamentos_rh = []
        self.viagens_scdp = []
        self.ferias = ''

        self.liberacoes = []
        self.liberacoes_exceto_parciais = []
        self.liberacoes_parciais_ch_horaria_maxima_exigida = 0
        self.liberacoes_parciais_ch_horaria_maxima_exigida_segundos = 0
        self.tem_liberacao_de_ponto_no_dia = False
        self.tem_liberacao_parcial_de_ponto_no_dia = False

        self.observacoes = []
        self.anexos = []
        self.abonos_chefia = []
        self.abonos_parciais = []
        self.revisoes_abonos_chefia = []

        self.tem_funcao_chefia = False
        self.pode_abonar_dia = False

        self.semana = 0
        self.jornada_trabalho = None
        self.horarios = []
        self.horarios_dia = []
        self.carga_horaria_do_dia = 0
        self.carga_horaria_do_dia_segundos = 0
        self.carga_horaria_do_dia_h = 0
        self.carga_horaria_do_dia_m = 0
        self.carga_horaria_do_dia_s = 0
        self.motivo_carga_horaria_do_dia = ''
        self.origem_carga_horaria_do_dia = ''
        self.duracao = ''
        self.duracao_bruto = ''
        self.duracao_segundos = 0
        self.duracao_segundos_bruto = 0
        self.hora_extra_noturna = 0

        self.acao_abono_inconsistencia = ''
        self.tem_inconsistencia_inferior = False
        self.tem_inconsistencia_superior = False

        self.duracao_computada = ''

        self.informacoes_registro = []
        self.informacoes_registro_display = []

        # para fins de totais
        self.tempo_abonado = 0
        self.tempo_trabalho_remoto = 0
        self.tempo_abonado_para_compensacao = 0
        self.tempo_nao_abonado = 0
        self.hora_extra_nao_justificada = 0
        self.hora_extra_justificada = 0
        self.hora_extra_para_compensacao_carga_horaria = 0
        self.trabalho_fds_permitido_para_compensacao_carga_horaria = 0
        self.trabalho_fds_permitido_como_hora_extra = 0
        self.trabalho_fds_nao_permitido = 0
        self.tempo_total_hora_extra_noturna = 0
        self.tempo_total_horas_trabalhadas = 0
        self.tempo_total_carga_horaria = 0

        self.compensacao = {}

        self.permite_solicitacao_abono_parcial = SolicitacaoAbonoParcial.solicitacao_abono_parcial_ativada()

        # outros
        self.tem_inconsistencia_calculo_adiado = False
        self.trata_inconsistencias_calculo_adiado = False
        self.final_dict_remove_keys = final_dict_remove_keys or ['tem_inconsistencia_calculo_adiado', 'trata_inconsistencias_calculo_adiado']

    def as_dict(self):
        result = self.__dict__.copy()
        for key in self.final_dict_remove_keys:
            if key in result:
                del result[key]
        del result['final_dict_remove_keys']
        result.update({'carga_horaria_do_dia_display': self.carga_horaria_do_dia_display})
        return result

    @property
    def carga_horaria_do_dia_display(self):
        from ponto.compensacao import formatar_segundos

        return formatar_segundos(self.carga_horaria_do_dia_segundos, True, True)
