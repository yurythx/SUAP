from abc import ABC, abstractmethod


class VariaveisDesempenho(ABC):
    _instance = None

    def __init__(self):
        super().__init__()
        self._variaveis = {}

    def get_variaveis(self, campi_siglas=None):
        if campi_siglas is None:
            campi_siglas = []
        dvariaveis = {}
        if campi_siglas:
            for campus_sigla in campi_siglas:
                dvariaveis[campus_sigla] = {}
                for variavel_sigla in self._variaveis:
                    uo_valor = self.get_variavel_valor_campus(variavel_sigla, campus_sigla)
                    dvariaveis[campus_sigla][variavel_sigla] = 0
                    if uo_valor:
                        dvariaveis[campus_sigla][variavel_sigla] = uo_valor[0]['doc_count']
        else:
            for variavel_sigla in self._variaveis:
                self.get_variavel_valor(variavel_sigla)
            dvariaveis = self._variaveis
        return dvariaveis

    def get_variavel_valor(self, sigla):
        qs = self._get_variavel_query(sigla)
        return qs.count()

    def get_variavel_valor_campus(self, variavel_sigla, uo_sigla=None):
        qs = self._get_query_uo(variavel_sigla, uo_sigla, detalhar=False)
        return qs.count()

    @abstractmethod
    def _get_query_uo(self, variavel_sigla, uo_sigla=None):
        pass

    @abstractmethod
    def _get_variavel_query(self, sigla):
        pass

    @abstractmethod
    def get_variavel_detalhe(self, sigla, uo_exercicio_equivalente_sigla=None):
        pass
