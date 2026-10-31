from collections import OrderedDict
from datetime import date, timedelta

from djtools.templatetags.filters import format_time_hms, hora_relogio
from edu.models import CalendarioAcademico, Professor
from pit_rit.models import PlanoIndividualTrabalho
from ponto.compensacao import Contexto
from ponto.models import AbonoChefia, Frequencia


class PontoDocente:
    def __init__(self, servidor, data_inicial, data_final, relatorio_de_ponto=None, so_semanas_inconsistentes=False):
        self.servidor = servidor
        self.data_inicial = data_inicial
        self.data_final = data_final
        self.relatorio_de_ponto = relatorio_de_ponto
        self.so_semanas_inconsistentes = so_semanas_inconsistentes

        assert self.servidor
        assert self.data_inicial
        assert self.data_final

        if self.servidor.data_inicio_exercicio_na_instituicao and self.data_inicial < self.servidor.data_inicio_exercicio_na_instituicao:
            self.data_inicial = self.servidor.data_inicio_exercicio_na_instituicao

        if not self.relatorio_de_ponto:
            self.relatorio_de_ponto = Frequencia.relatorio_ponto_pessoa(
                vinculo=self.servidor.get_vinculo(), data_ini=self.data_inicial, data_fim=self.data_final, trata_compensacoes=False
            )

        self.funcoes_no_periodo = self.servidor.get_funcoes_no_periodo(self.data_inicial, self.data_final)

        self.professor = Professor.objects.filter(vinculo__id_relacionamento=self.servidor.id, vinculo__tipo_relacionamento__model='servidor').first()
        self.jornadas, self.motivos_jornadas, self.origens_jornadas = self.servidor.get_jornadas_periodo_dict(self.data_inicial, self.data_final)
        self.uos = [setor.uo for setor in self.servidor.setor_suap_servidor_por_periodo(data_inicial=self.data_inicial, data_final=self.data_final)]

        self.contexto_compensacao = Contexto(self.servidor, self.data_inicial, self.data_final, self.relatorio_de_ponto)

        self._semanas = None

        self._ajusta_relatorio_de_ponto()

        ######################################
        # adapta a estrutura padrão do relatório da app ponto para versão ponto docente da app pit_rit
        # de modo que seja compatível com os templates da app pit_rit
        ######################################
        self.relatorio_de_ponto['semanas'] = self.get_semanas()
        self.relatorio_de_ponto['total_relogio_exigido'] = format_time_hms(self.total_relogio_exigido())
        self.relatorio_de_ponto['total_frequencia'] = format_time_hms(self.total_frequencia())
        self.relatorio_de_ponto['total_valido'] = format_time_hms(self.total_valido())
        self.relatorio_de_ponto['total_pit_hora_relogio'] = format_time_hms(self.total_pit_hora_relogio())

    def get_relatorio_de_ponto_adaptado(self):
        return self.relatorio_de_ponto

    def get_semanas(self):
        """
        retorna {semana1: _PontoDocenteSemana, semana2: _PontoDocenteSemana, ...}
        """

        if self._semanas is None:
            semanas = OrderedDict()

            semana_seq = 1
            semana_dias = OrderedDict()

            dia_atual = self.data_inicial
            while dia_atual <= self.data_final:
                for dia_relatorio in self.relatorio_de_ponto['dias']:
                    if dia_relatorio['dia'] == dia_atual:
                        semana_dias[dia_atual] = dia_relatorio
                        break

                if dia_atual.weekday() == 6:  # domingo?
                    if list(semana_dias.values()):
                        semanas[semana_seq] = _PontoDocenteSemana(ponto_docente_instance=self, dias=list(semana_dias.values()))
                        semana_seq += 1  # próxima semana
                        semana_dias = OrderedDict()

                dia_atual = dia_atual + timedelta(1)  # próximo dia

            if list(semana_dias.values()):
                semanas[semana_seq] = _PontoDocenteSemana(ponto_docente_instance=self, dias=list(semana_dias.values()))

            if self.so_semanas_inconsistentes:
                semanas_final = OrderedDict()
                semana_final_seq = 1
                for semana in list(semanas.values()):
                    if semana.is_inconsistente:
                        semanas_final[semana_final_seq] = semana
                        semana_final_seq += 1
                semanas = semanas_final

            self._semanas = semanas

        return self._semanas

    def _total(self, attr_name):
        total = 0
        for semana in list(self.get_semanas().values()):
            total += getattr(semana, attr_name)
        return total

    def total_relogio_exigido(self):
        return self._total('relogio_exigido')

    def total_frequencia(self):
        return self._total('frequencia')

    def total_pit_hora_relogio(self):
        return self._total('pit_hora_relogio')

    def total_tempo_nao_abonado(self):
        return self._total('tempo_nao_abonado')

    def total_hora_extra_nao_justificada(self):
        return self._total('hora_extra_nao_justificada')

    def total_trabalho_fds_nao_permitido(self):
        return self._total('trabalho_fds_nao_permitido')

    def total_valido(self):
        return self._total('total_valido')

    def _ajusta_relatorio_de_ponto(self):
        for dia_relatorio in self.relatorio_de_ponto['dias']:
            # remove a informação sobre saída antecipada (chamado #78328)
            if 'informacoes_saida_antecipada' in dia_relatorio:
                dia_relatorio['informacoes_saida_antecipada'] = ''

    def get_dia_relatorio_de_ponto(self, data):
        """
        return {'dia': ?, ...}
        """
        for dia_relatorio in self.relatorio_de_ponto['dias']:
            if dia_relatorio['dia'] == data:
                return dia_relatorio
        return {}

    def get_dia_funcao(self, data):
        """
        returna uma instância de rh.ServidorFuncaoHistorico ou None
        """
        return self.funcoes_no_periodo.get(data, data)

    def get_carga_horaria_exigida(self, data) -> float:
        """
        Considerar a metade da carga horária diária conforme solicitação da demanda #487:

            "... deverá ser cobrada do docente DE ou 40 um total de 20 horas relógio,
            enquanto que para o docente 20 Horas deverá ser cobrado um total de 10 horas relógio,
            de forma semanal."

        Obs: a semana (completa) considerada no texto acima tem 5 dias úteis (seg a sex)

        Esse cálculo é realizado no relatório de ponto (método ponto.Frequencia.relatorio_ponto_pessoa).

        Retorna em horas.
        """
        ch_horas = 0.0
        if self.is_dia_util(data) and self.is_dia_carga_horaria_exigivel(data):
            ch_horas = self.get_dia_relatorio_de_ponto(data).get('carga_horaria_do_dia')

        return ch_horas

    def is_dia_util(self, data):
        return self.contexto_compensacao.get_dia(data).is_dia_util[0]

    def is_dia_carga_horaria_exigivel(self, data):
        """
        chamado #78396

        ATT: nesse caso, abonos parciais sobrepõem a ação de abonos não parciais
        """
        abonos_do_dia = self.contexto_compensacao.get_dia(data).abonos_do_dia

        dia_exigivel = not abonos_do_dia
        if not dia_exigivel:
            dia_exigivel_parcial = False
            dia_exigivel_total = False

            for abono_do_dia in abonos_do_dia:
                if abono_do_dia.eh_abono_parcial:
                    if abono_do_dia.acao_abono == AbonoChefia.ABONADO_COM_COMPENSACAO:
                        dia_exigivel_parcial = True
                else:
                    if abono_do_dia.acao_abono not in [AbonoChefia.ABONADO, AbonoChefia.TRABALHO_REMOTO]:
                        dia_exigivel_total = True

            if dia_exigivel_parcial:
                dia_exigivel = True
            else:
                dia_exigivel = dia_exigivel_total

        return dia_exigivel

    def tem_frequencias_inconsistentes(self):
        return any(semana_instance.is_inconsistente for semana_instance in list(self.get_semanas().values()))

    def is_dia_inconsistente(self, data):
        return len(Frequencia.get_inconsistencias(self.servidor.get_vinculo(), data, data, self.contexto_compensacao).get(data, []))


class _PontoDocenteSemana:
    def __init__(self, ponto_docente_instance, dias):
        self.ponto_docente = ponto_docente_instance
        self.dias = dias  # [dia_do_relatorio_ponto, dia_do_relatorio_ponto, dia_do_relatorio_ponto, ...]

        assert self.ponto_docente
        assert self.dias

        # totais da semana
        # calcula uma única vez nos métodos correspondentes
        self._relogio_exigido = None
        self._frequencia = None
        self._pit_hora_relogio = None
        self._tempo_nao_abonado = None
        self._hora_extra_nao_justificada = None
        self._trabalho_fds_nao_permitido = None

    @property
    def data_inicial(self):
        dias = [_['dia'] for _ in self.dias]
        if dias:
            return min(dias)
        return None

    @property
    def data_final(self):
        dias = [_['dia'] for _ in self.dias]
        if dias:
            return max(dias)
        return None

    @property
    def calendarios_academicos(self):
        return (
            (
                CalendarioAcademico.objects.filter(data_inicio__lte=self.data_inicial, data_fim__gte=self.data_inicial)
                | CalendarioAcademico.objects.filter(data_inicio__lte=self.data_final, data_fim__gte=self.data_final)
            )
            .filter(uo__in=self.ponto_docente.uos)
            .distinct()
        )

    @property
    def planos_individuais_trabalho(self):
        calendarios_academicos = self.calendarios_academicos

        return PlanoIndividualTrabalho.objects.filter(
            professor__vinculo=self.ponto_docente.servidor.get_vinculo(),
            ano_letivo__ano__in=[calendario.ano_letivo.ano for calendario in calendarios_academicos],
            periodo_letivo__in=[calendario.periodo_letivo for calendario in calendarios_academicos],
        ).distinct()

    @property
    def relogio_exigido(self):
        """
        frequência exigida
        retorna em segundos
        """
        if self._relogio_exigido is None:
            ch_horas = 0
            for dia in self.dias:
                ch_horas += self.ponto_docente.get_carga_horaria_exigida(dia['dia'])
            self._relogio_exigido = ch_horas * 60 * 60
        return self._relogio_exigido

    @property
    def frequencia(self):
        """
        frequência dada (ponto batido!)
        retorna em segundos
        """
        if self._frequencia is None:
            ch_segundos = 0
            for dia in self.dias:
                ch_segundos += dia['duracao_segundos']
            self._frequencia = ch_segundos
        return self._frequencia

    @property
    def pit_hora_relogio(self):
        """
        h/r total do(s) PIT(s) envolvido(s)
        retorna em segundos
        """
        if self._pit_hora_relogio is None:
            ch_horas_aula = 0
            for pit in self.planos_individuais_trabalho:
                ch_horas_aula += pit.get_ch_semanal_total()
            ch_horas_relogio = hora_relogio(ch_horas_aula)
            self._pit_hora_relogio = ch_horas_relogio * 60 * 60
        return self._pit_hora_relogio

    @property
    def tempo_nao_abonado(self):
        """
        retorna em segundos
        """
        if self._tempo_nao_abonado is None:
            ch_segundos = 0
            for dia in self.dias:
                abono = dia.get('abono_chefia')
                if abono and abono.acao_abono == AbonoChefia.NAO_ABONADO:
                    ch_segundos += dia['duracao_segundos']
            self._tempo_nao_abonado = ch_segundos
        return self._tempo_nao_abonado

    @property
    def hora_extra_nao_justificada(self):
        """
        retorna em segundos
        """
        if self._hora_extra_nao_justificada is None:
            ch_segundos = 0
            for dia in self.dias:
                abono = dia.get('abono_chefia')
                if abono and abono.acao_abono == AbonoChefia.HORA_EXTRA_NAO_JUSTIFICADA:
                    ch_segundos += dia['duracao_segundos']
            self._hora_extra_nao_justificada = ch_segundos
        return self._hora_extra_nao_justificada

    @property
    def trabalho_fds_nao_permitido(self):
        """
        retorna em segundos
        """
        if self._trabalho_fds_nao_permitido is None:
            ch_segundos = 0
            for dia in self.dias:
                abono = dia.get('abono_chefia')
                if abono and abono.acao_abono == AbonoChefia.TRABALHO_FDS_NAO_PERMITIDO:
                    ch_segundos += dia['duracao_segundos']
            self._trabalho_fds_nao_permitido = ch_segundos
        return self._trabalho_fds_nao_permitido

    @property
    def total_valido(self):
        """
        frequência - tempo não abonado - hora extra não justificada - trabalho fds não permitido
        retorna em segundos
        """
        total = self.frequencia - self.tempo_nao_abonado - self.hora_extra_nao_justificada - self.trabalho_fds_nao_permitido
        return total

    @property
    def is_inconsistente(self):
        semana_ja_concluida = True  # semana está no passado?
        hoje = date.today()
        for dia_relatorio in self.dias:
            if dia_relatorio['dia'] >= hoje:
                semana_ja_concluida = False

        if not semana_ja_concluida:
            return False  # semana ainda não concluída = semana ainda consistente (poderá ser inconsistente)

        # verifica a frequência da semana
        return self.frequencia < self.relogio_exigido
