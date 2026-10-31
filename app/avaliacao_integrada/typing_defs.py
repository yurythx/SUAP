from __future__ import annotations

from collections import OrderedDict as _OrderedDict
from typing import Any, TypedDict, NotRequired, TYPE_CHECKING

from django import forms

# Evitar import em runtime que possa causar ciclo. Se preferir usar o User real:
# from comum.models import User
if TYPE_CHECKING:
    from comum.models import User  # só para tipagem estática
else:
    User = 'User'  # forward-ref para runtime

# --------------------------------------------------------------------
# Imports só para type checking (evita import cíclico em runtime)
# --------------------------------------------------------------------
if TYPE_CHECKING:
    from avaliacao_integrada.models import (
        Avaliacao,
        Respondente,
        Segmento,
        UnidadeOrganizacional,
        Modalidade,
        CursoCampus,
        ProfessorDiario,
        Diario,
        Eixo,
        Dimensao,
        Macroprocesso,
    )


# --------------------------------------------------------------------
# TypedDict: contrato de entrada para montar_formulario
# --------------------------------------------------------------------
class DadosMontagemFormulario(TypedDict):
    """
    Estrutura mínima necessária para montar o formulário de avaliação.

    Obrigatórios:
      - avaliacao: Avaliacao corrente.
      - segmento: Segmento do respondente.
      - uo: Unidade organizacional (pode ser None, conforme o segmento).
      - user: Usuário Django relacionado ao respondente interno.
      - eh_previsualizacao: Se True, não carrega respostas prévias em initial.

    Opcionais:
      - respondente: Instância já existente (quando houver).
      - dados_usuario_externo: Dados de identificação para público externo.
    """

    avaliacao: Avaliacao
    segmento: Segmento
    uo: UnidadeOrganizacional | None
    user: User
    eh_previsualizacao: bool

    respondente: NotRequired[Respondente | None]
    dados_usuario_externo: NotRequired[dict[str, Any] | None]


# --------------------------------------------------------------------
# Tipos auxiliares para a estrutura de iteração:
# objeto (None | Modalidade | CursoCampus | ProfessorDiario | Diario)
#   -> Eixo -> Dimensao -> Macroprocesso -> list[list[forms.Field]]
# --------------------------------------------------------------------
# Chave de 1º nível (objeto-alvo das perguntas)
type ObjectKeyType = 'Modalidade' | 'CursoCampus' | 'ProfessorDiario' | 'Diario' | None

# Uma “linha” de campos (um indicador pode gerar 1+ campos)
type FieldsList = list[forms.Field]

# OrderedDict aninhado: objeto -> eixo -> dimensão -> macroprocesso -> lista de listas de fields
type IteracoesType = _OrderedDict[ObjectKeyType, _OrderedDict['Eixo', _OrderedDict['Dimensao', _OrderedDict['Macroprocesso', list[FieldsList]]]]]


# --------------------------------------------------------------------
# Tipos para fluxo com token (sociedade civil / cancelamento)
# --------------------------------------------------------------------
class DadosTokenMinimo(TypedDict, total=False):
    """
    Contrato mínimo esperado em tokens diversos do fluxo:
      - avaliacao_id: identificador da avaliação (quando aplicável)
      - respondente_id: identificador do respondente (quando aplicável)
    """

    avaliacao_id: int
    respondente_id: int


class DadosUsuarioExterno(TypedDict, total=False):
    """
    Estrutura com dados informados por público externo (sociedade civil).
    Campos opcionais porque variam conforme o segmento.
    """

    email: str | None
    matricula: str | None
    cpf: str | None
    cnpj: str | None
    tipo_respondente: int | None


class DadosSociedadeCivilToken(DadosTokenMinimo, total=False):
    """
    Dicionário retornado por Avaliacao.obter_dados(token) e enriquecido
    ao longo do fluxo de sociedade civil.
    """

    dados_usuario_externo: DadosUsuarioExterno


# --------------------------------------------------------------------
# Outros contratos utilitários
# --------------------------------------------------------------------
class ServicoAnonimo(TypedDict):
    categoria: str
    url: str
    icone: str
    titulo: str


__all__ = [
    'DadosMontagemFormulario',
    'DadosSociedadeCivilToken',
    'DadosTokenMinimo',
    'DadosUsuarioExterno',
    'FieldsList',
    'IteracoesType',
    'ObjectKeyType',
    'ServicoAnonimo',
]
