import html
from datetime import date

from ninja import Schema, Field
from pydantic import field_validator
from django.utils.html import strip_tags

from projetos.models import Participacao


class ProjetoOut(Schema):
    titulo: str
    equipe: list[str]
    foco_tecnologico: str | None = Field(None, alias='focotecnologico.descricao')
    campus: str = Field(..., alias='uo.sigla')
    data_inicio: date = Field(..., alias='inicio_execucao')
    data_fim: date = Field(..., alias='fim_execucao')
    area_conhecimento: str | None = Field(None, alias='area_conhecimento.descricao')
    area_tematica: str = Field(..., alias='area_tematica.descricao')
    resumo: str

    @staticmethod
    def resolve_equipe(obj):
        lista = []
        for participante in Participacao.objects.filter(projeto=obj, ativo=True).exclude(vinculo_pessoa=None):
            lista.append(participante.get_nome())
        return lista

    @field_validator('resumo')
    def strip_html_from_resumo(cls, value):
        return strip_tags(html.unescape(value))
