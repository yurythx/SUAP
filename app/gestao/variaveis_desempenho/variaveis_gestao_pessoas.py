from abc import abstractmethod

from gestao.variaveis_desempenho.variaveis_base import VariaveisDesempenho
from rh.models import Funcao, Servidor, Situacao


class VariaveisGestaoPessoaBase(VariaveisDesempenho):
    VARIAVEIS = {
        'grupo': 'Rh',
        'titulo': 'Gestão de Pessoas',
        'variaveis': [
            'A',
            'E',
            'G',
            'M',
            'D',
            'DO',
            'DOAP',
            'DOAP_20',
            'DOAP_40',
            'DOAP_DDE',
            'DOST',
            'DOC',
            'DDESF',
            'DDECF',
            'D40SF',
            'D40CF',
            'D20SF',
            'D20CF',
            'DFG',
            'DCD1',
            'DCD2',
            'DCD3',
            'DCD4',
        ],
    }
    SITUACAO_ATIVO_PERMANENTE = Situacao.ATIVO_PERMANENTE
    SITUACAO_CEDIDO_REQUISITADO = Situacao.CEDIDO_REQUISITADO
    SITUACAO_ATIVO_EM_OUTRO_ORGAO = Situacao.ATIVO_EM_OUTRO_ORGAO
    SITUACAO_CONTRATO_TEMPORARIO = Situacao.CONTRATO_TEMPORARIO
    SITUACAO_PROFESSOR_SBUSTITUTO = Situacao.CONT_PROF_SUBSTITUTO
    SITUACAO_PROFESSOR_VISITANTE = Situacao.CONTR_PROF_VISITANTE
    SITUACAO_PROFESSOR_TEMPORARIO = Situacao.CONT_PROF_TEMPORARIO

    # Conforme solicitado por Solange, considera-se cedidos as situações funcionais
    # "03 - CEDIDO/REQUISITADO" e "08 - ATIVO EM OUTRO ORGAO"'. Por isso foi incluído a
    # Variáveis afetadas: A, E, G, M, D
    SITUACOES_EFETIVOS = [SITUACAO_ATIVO_PERMANENTE, SITUACAO_CEDIDO_REQUISITADO, SITUACAO_ATIVO_EM_OUTRO_ORGAO]

    SITUACOES_TEMPORARIOS = [SITUACAO_CONTRATO_TEMPORARIO, SITUACAO_PROFESSOR_SBUSTITUTO, SITUACAO_PROFESSOR_TEMPORARIO]

    # Situação "03 - CEDIDO/REQUISITADO" foi incluida em SITUACOES_EFETIVOS
    SITUACOES_EFETIVOS_E_TEMPORARIOS = SITUACOES_EFETIVOS + SITUACOES_TEMPORARIOS

    # Inclusão situação "12 - CONTRATO TEMPORARIO" conforme solicitado por Solange.
    # Fazendo isso, a constante RH_SITUACOES_USADAS_VARIAVEIS_DOCENTES passa a ser igual a
    # Situacao.SITUACOES_EFETIVOS_E_TEMPORARIOS
    # Variáveis afetadas: DOST, DDESF, DDECF, D40SF, D40CF, D20SF, D20CF
    RH_SITUACOES_USADAS_VARIAVEIS_DOCENTES = SITUACOES_EFETIVOS_E_TEMPORARIOS

    # Desativa, foi subistituido por SITUACOES_TEMPORARIOS
    # Inclusão situação "12 - CONTRATO TEMPORARIO" conforme solicitado por Solange.
    # SITUACOES_SUBSTITUTOS_OU_TEMPORARIOS = [SITUACAO_PROFESSOR_SBUSTITUTO, SITUACAO_PROFESSOR_TEMPORARIO]

    # Inclusão situação "03 - CEDIDO/REQUISITADO" conforme solicitado por Solange.
    # Variáveis afetadas: DO
    CEDIDOS = (SITUACAO_ATIVO_EM_OUTRO_ORGAO, SITUACAO_CEDIDO_REQUISITADO)

    TITULACAO_GRADUADO_NIVEL_SUPERIOR_COMPLETO = '23'
    TITULACAO_LICENCIATURA = '35'
    TITULACAO_GRADUACAO_RSCI = '48'
    TITULACAO_APERFEICOAMENTO_NIVEL_SUPERIOR = '24'
    TITULACAO_ESPECIALIZACAO_NIVEL_SUPERIOR = '25'
    TITULACAO_POS_GRADUACAO_RSCII = '49'
    TITULACAO_MESTRADO = '26'
    TITULACAO_MESTRE_RSCIII = '50'
    TITULACAO_DOUTORADO = '27'

    JORNADA_TRABALHO_20HORAS = '20'
    JORNADA_TRABALHO_40HORAS = '40'
    JORNADA_TRABALHO_DE = '99'

    def __init__(self):
        super().__init__()
        self._variaveis = {}

        for variavel_sigla in self.VARIAVEIS['variaveis']:
            self._variaveis[variavel_sigla] = None

    @abstractmethod
    def _get_docentes_query(self):
        """
        Retorna servidores docentes (eh_docente=True) e não excuídos (excluido=False)
        """

    @abstractmethod
    def _get_servidores_situacoes_query(self, situacoes_codigo):
        pass

    @abstractmethod
    def _get_docentes_ativo_permanente_query(self, jornadas_trabalho_codigo=None):
        pass

    @abstractmethod
    def _get_docentes_titulacoes_query(self, titulacoes_codigo):
        pass

    @abstractmethod
    def _get_docentes_jornada_trabalho_query(self, jornadas_trabalho_codigo, tem_funcao=False):
        pass

    @abstractmethod
    def _get_docentes_funcao_query(self, funcao_sigla, funcoes_codigos=None):
        """
        Servidores os quais o grupo do seu cargo/emprego tenha como categoria a opção “DOCENTE”, que não estão excluídos,
        com a situação “ATIVO PERMANENTE”, "CEDIDO", "CONT.PROF.SUBSTITUTO" ou "CONT.PROF.TEMPORARIO" que têm a função "CD",
        de código [funcao_codigo].
        """

    # overriding abstract method
    def _get_variavel_query(self, sigla):
        query = {
            'A': self._get_docentes_titulacoes_query([self.TITULACAO_APERFEICOAMENTO_NIVEL_SUPERIOR]),
            'E': self._get_docentes_titulacoes_query([self.TITULACAO_ESPECIALIZACAO_NIVEL_SUPERIOR, self.TITULACAO_POS_GRADUACAO_RSCII]),
            'G': self._get_docentes_titulacoes_query(
                [self.TITULACAO_GRADUADO_NIVEL_SUPERIOR_COMPLETO, self.TITULACAO_LICENCIATURA, self.TITULACAO_GRADUACAO_RSCI]
            ),
            'M': self._get_docentes_titulacoes_query([self.TITULACAO_MESTRADO, self.TITULACAO_MESTRE_RSCIII]),
            'D': self._get_docentes_titulacoes_query([self.TITULACAO_DOUTORADO]),
            'DO': self._get_docentes_query(),
            'DOAP': self._get_docentes_ativo_permanente_query(),
            'DOAP_20': self._get_docentes_ativo_permanente_query(self.JORNADA_TRABALHO_20HORAS),
            'DOAP_40': self._get_docentes_ativo_permanente_query(self.JORNADA_TRABALHO_40HORAS),
            'DOAP_DDE': self._get_docentes_ativo_permanente_query(self.JORNADA_TRABALHO_DE),
            'DOST': self._get_servidores_situacoes_query(self.SITUACOES_TEMPORARIOS),
            'DOC': self._get_servidores_situacoes_query(self.CEDIDOS),
            'DDESF': self._get_docentes_jornada_trabalho_query(self.JORNADA_TRABALHO_DE, False),
            'DDECF': self._get_docentes_jornada_trabalho_query(self.JORNADA_TRABALHO_DE, True),
            'D40SF': self._get_docentes_jornada_trabalho_query(self.JORNADA_TRABALHO_40HORAS, False),
            'D40CF': self._get_docentes_jornada_trabalho_query(self.JORNADA_TRABALHO_40HORAS, True),
            'D20SF': self._get_docentes_jornada_trabalho_query(self.JORNADA_TRABALHO_20HORAS, False),
            'D20CF': self._get_docentes_jornada_trabalho_query(self.JORNADA_TRABALHO_20HORAS, True),
            'DFG': self._get_docentes_funcao_query(Funcao.CODIGO_FG),
            'DCD1': self._get_docentes_funcao_query(Funcao.CODIGO_CD, ['0001', '1']),
            'DCD2': self._get_docentes_funcao_query(Funcao.CODIGO_CD, ['0002', '2']),
            'DCD3': self._get_docentes_funcao_query(Funcao.CODIGO_CD, ['0003', '3']),
            'DCD4': self._get_docentes_funcao_query(Funcao.CODIGO_CD, ['0004', '4']),
        }
        return query[sigla]


class VariaveisGestaoPessoasSUAP(VariaveisGestaoPessoaBase):
    # overriding abstract method
    def _get_docentes_query(self):
        """
        Retorna servidores docentes (eh_docente=True) e não excuídos (excluido=False)
        """
        return Servidor.objects.docentes()

    # overriding abstract method
    def _get_servidores_situacoes_query(self, situacoes_codigo):
        qs = self._get_docentes_query()
        qs = qs.filter(situacao__codigo__in=situacoes_codigo)
        return qs

    # overriding abstract method
    def _get_docentes_ativo_permanente_query(self, jornadas_trabalho_codigo=None):
        qs = self._get_servidores_situacoes_query([self.SITUACAO_ATIVO_PERMANENTE])
        if jornadas_trabalho_codigo:
            qs = qs.filter(jornada_trabalho__codigo=jornadas_trabalho_codigo)
        return qs

    # overriding abstract method
    def _get_docentes_titulacoes_query(self, titulacoes_codigo):
        qs = self._get_servidores_situacoes_query(self.SITUACOES_EFETIVOS_E_TEMPORARIOS)
        qs = qs.filter(titulacao__codigo__in=titulacoes_codigo)
        return qs

    # overriding abstract method
    def _get_docentes_jornada_trabalho_query(self, jornadas_trabalho_codigo, tem_funcao=False):
        qs = self._get_servidores_situacoes_query(self.RH_SITUACOES_USADAS_VARIAVEIS_DOCENTES)
        qs = qs.filter(jornada_trabalho__codigo=jornadas_trabalho_codigo, funcao__isnull=not tem_funcao)
        return qs

    # overriding abstract method
    def _get_docentes_funcao_query(self, funcao_sigla, funcoes_codigos=None):
        """
        Servidores os quais o grupo do seu cargo/emprego tenha como categoria a opção “DOCENTE”, que não estão excluídos,
        com a situação “ATIVO PERMANENTE”, "CEDIDO", "CONT.PROF.SUBSTITUTO" ou "CONT.PROF.TEMPORARIO" que têm a função "CD",
        de código [funcao_codigo].
        """
        qs = self._get_servidores_situacoes_query(self.RH_SITUACOES_USADAS_VARIAVEIS_DOCENTES)
        qs = qs.filter(funcao__codigo=funcao_sigla)
        if funcoes_codigos:
            qs = qs.filter(funcao_codigo__in=funcoes_codigos)
        return qs

    # overriding abstract method
    def _get_query_uo(self, variavel_sigla, uo_sigla=None, detalhar=True):
        qs = self._get_variavel_query(variavel_sigla)

        if uo_sigla:
            if variavel_sigla in ['A', 'D', 'E', 'M', 'G', 'DO', 'DOAP', 'DOAP_20', 'DOAP_40', 'DOAP_DDE', 'DOST', 'DOC']:
                qs = qs.filter(setor_lotacao__uo__equivalente__sigla=uo_sigla)
            else:  # ['DDESF', 'DDECF', 'D40SF', 'D40CF', 'D20SF', 'D20CF', 'DFG', 'DCD1', 'DCD2', 'DCD3', 'DCD4']:
                qs = qs.filter(setor__uo__sigla=uo_sigla)
        return qs

    # overriding abstract method
    def get_variavel_detalhe(self, variavel_sigla, uo_sigla=None):
        raise NotImplementedError
        # qs = self._get_qs_uo(variavel_sigla, uo_sigla, detalhar=True)
        # return se


class VariaveisGestaoPessoasElastic(VariaveisGestaoPessoaBase):
    # overriding abstract method
    def _get_docentes_query(self):
        """
        Retorna servidores docentes (eh_docente=True) e não excuídos (excluido=False)
        """

    # overriding abstract method
    def _get_servidores_situacoes_query(self, situacoes_codigo):
        pass

    # overriding abstract method
    def _get_docentes_ativo_permanente_query(self, jornadas_trabalho_codigo=None):
        pass

    # overriding abstract method
    def _get_docentes_titulacoes_query(self, titulacoes_codigo):
        pass

    # overriding abstract method
    def _get_docentes_jornada_trabalho_query(self, jornadas_trabalho_codigo, tem_funcao=False):
        pass

    # overriding abstract method
    def _get_docentes_funcao_query(self, funcao_sigla, funcoes_codigos=None):
        """
        Servidores os quais o grupo do seu cargo/emprego tenha como categoria a opção “DOCENTE”, que não estão excluídos,
        com a situação “ATIVO PERMANENTE”, "CEDIDO", "CONT.PROF.SUBSTITUTO" ou "CONT.PROF.TEMPORARIO" que têm a função "CD",
        de código [funcao_codigo].
        """

    # overriding abstract method
    def _get_query_uo(self, variavel_sigla, uo_sigla=None, detalhar=True):
        pass

    # overriding abstract method
    def get_variavel_detalhe(self, variavel_sigla, uo_sigla=None):
        pass
