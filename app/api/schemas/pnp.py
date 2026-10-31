import datetime

from ninja import Schema
from pydantic import Field

from rh.models import Situacao


class ServidorNaoDocenteSchema(Schema):
    """
    Schema para representar um servidor não docente.
    """

    id: int
    matricula: str
    cpf: str | None = Field(None, alias='pessoa_fisica.cpf')
    situacao: str
    # nulo quando o servidor não tem setor, o setor não tem unidade organizacional ou a
    # unidade ainda não foi vinculada a uma EstruturaPNP
    estrutura: str | None = Field(None, alias='setor.uo.estruturapnp.codigo')
    categoria_funcional: str | None = Field(None, alias='categoria')

    @staticmethod
    def resolve_situacao(obj) -> str:
        """Ativo quando o servidor tem vínculo e situação SIAPE de servidor ativo; senão, Inativo."""
        eh_ativo = obj.ativo and obj.situacao.codigo in Situacao.SITUACOES_ATIVOS
        return 'Ativo' if eh_ativo else 'Inativo'


class ServidorTerceirizadoSchema(Schema):
    """
    Schema para representar um servidor terceirizado.
    """

    id: int
    cpf: str
    estrutura: str
    situacao: str
    data_ingresso: datetime.date | None
    data_exclusao: datetime.date | None
