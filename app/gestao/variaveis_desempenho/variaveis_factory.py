from django.conf import settings

from gestao.variaveis_desempenho.variaveis_gestao_pessoas import VariaveisGestaoPessoasElastic, VariaveisGestaoPessoasSUAP


class VariavelFactory:
    @staticmethod
    def get_instance(sigla_grupo_variavel):
        if sigla_grupo_variavel == 'Rh':
            if settings.USE_ELASTICSEARCH:
                return VariaveisGestaoPessoasElastic()
            else:
                return VariaveisGestaoPessoasSUAP()
