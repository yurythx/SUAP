from datetime import date
from django.core.exceptions import PermissionDenied
from rh.models import Funcao, Setor


class PontoException(Exception):
    pass


class FuncionalidadeApenasFuncoesChefiaException(PermissionDenied):
    """
    Hierarquia dos setores:
        ...
            setor_requisitante
                ...
                    setor_aplicacao
                        ...
    """

    def __init__(
        self,
        setor_requisitante: Setor,
        setor_aplicacao: Setor | None = None,
        data_inicio_aplicacao: date | None = None,
        data_fim_aplicacao: date | None = None,
    ):
        assert setor_requisitante is not None
        setor_aplicacao = setor_aplicacao or setor_requisitante
        data_inicio_aplicacao = data_inicio_aplicacao or date.today()
        data_fim_aplicacao = data_fim_aplicacao or data_inicio_aplicacao
        super().__init__(f"""
            Apenas uma função de chefia
            ({', '.join(Funcao.get_codigos_funcao_chefia())}),
            vigente no {f'período de {data_inicio_aplicacao.strftime("%d/%m/%Y")} a {data_fim_aplicacao.strftime("%d/%m/%Y")}' if data_inicio_aplicacao != data_fim_aplicacao else f'dia {data_inicio_aplicacao.strftime("%d/%m/%Y")}'},
            no setor {setor_requisitante}{f' e, por hierarquia, abrangendo o setor {setor_aplicacao}' if setor_requisitante != setor_aplicacao else ''},
            poderá acessar esta funcionalidade/recurso.
        """)
