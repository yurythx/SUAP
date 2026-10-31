import html
from datetime import date

from ninja import Schema, Field
from pydantic import field_validator
from django.utils.html import strip_tags

from pesquisa.models import Participacao


class EmpresaIncubadaOut(Schema):
    cnpj: str
    razao_social: str
    area_atuacao: str | None = Field(None, alias='principal_pi.descricao')
    data_inicio: date = Field(..., alias='data_incubacao')
    data_fim: str
    campus_vinculacao: str = Field(..., alias='incubadora.uo.nome')
    total_empregados: int | None = Field(None, alias='qtde_funcionarios')

    @staticmethod
    def resolve_data_fim(obj):
        return 'não se aplica'


class ProjetoOut(Schema):
    titulo: str
    campus: str = Field(..., alias='uo.sigla')
    data_inicio: date = Field(..., alias='inicio_execucao')
    data_fim: date = Field(..., alias='fim_execucao')
    area_conhecimento: str = Field(..., alias='area_conhecimento.descricao')
    resumo: str
    justificativa: str
    equipe: list[str]

    @staticmethod
    def resolve_equipe(obj):
        lista = []
        for participante in Participacao.objects.filter(projeto=obj, ativo=True).exclude(vinculo_pessoa=None):
            lista.append(participante.get_nome())
        return lista

    @field_validator('resumo')
    def strip_html_from_resumo(cls, value):
        return strip_tags(html.unescape(value))

    @field_validator('justificativa')
    def strip_html_from_justificativa(cls, value):
        return strip_tags(html.unescape(value))
