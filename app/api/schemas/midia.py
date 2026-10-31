from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from django.conf import settings
from ninja import Schema

from djtools.utils.calendario import formatar_periodo
from eventos.enums import EtapaPeriodoSubmissao

if TYPE_CHECKING:
    from eventos.models import Evento


def formatar_horario(hora_inicio=None, hora_fim=None):
    """Formata um horário exibindo apenas as horas."""
    if not hora_inicio and not hora_fim:
        return None

    if hora_inicio and hora_fim:
        return f'{hora_inicio.strftime("%H:%M")} às {hora_fim.strftime("%H:%M")}'

    if hora_inicio:
        return hora_inicio.strftime('%H:%M')

    return hora_fim.strftime('%H:%M')


class BannerSchema(Schema):
    id: int
    titulo: str
    imagem: str
    tipo: str
    link: str | None
    data_inicio: datetime.datetime
    data_termino: datetime.datetime


class PeriodoSchema(Schema):
    """Schema para representar um período com datas de início e fim"""

    data_inicio: datetime.date | None
    data_fim: datetime.date | None


class PeriodoInscricaoTipoSchema(Schema):
    """Schema para período de inscrição por tipo de participante"""

    tipo_participacao: str
    periodo_formatado: str | None
    data_inicio: datetime.date | None
    hora_inicio: datetime.time | None
    data_fim: datetime.date | None
    hora_fim: datetime.time | None


class AtividadeEventoSchema(Schema):
    """Schema para atividades do evento"""

    id: int
    tipo: str
    descricao: str
    carga_horaria_em_segundos: int
    data: datetime.date | None
    hora: datetime.time | None
    data_fim: datetime.date | None
    hora_fim: datetime.time | None
    periodo_formatado: str | None
    limite_inscricoes: int | None
    vagas_disponiveis: int | None

    @staticmethod
    def resolve_tipo(obj):
        return obj.tipo.descricao if obj.tipo else None

    @staticmethod
    def resolve_carga_horaria_em_segundos(obj):
        return obj.ch

    @staticmethod
    def resolve_periodo_formatado(obj):
        return obj.get_periodo()

    @staticmethod
    def resolve_vagas_disponiveis(obj):
        return obj.get_qtd_vagas_disponiveis()


class ProgramacaoDiaSchema(Schema):
    """Schema para programação agrupada por dia"""

    data: datetime.date
    atividades: list[AtividadeEventoSchema]


class ModalidadeSubmissaoSchema(Schema):
    """Schema para modalidades de submissão com URLs de documentos"""

    id: int
    titulo: str
    regras_submissao: str | None
    regras_avaliacao: str | None
    template: str | None

    @staticmethod
    def resolve_titulo(obj):
        return obj.tipo.titulo if obj.tipo else None

    @staticmethod
    def resolve_regras_submissao(obj):
        return obj.regras_submissao.url if obj.regras_submissao else None

    @staticmethod
    def resolve_regras_avaliacao(obj):
        return obj.regras_avaliacao.url if obj.regras_avaliacao else None

    @staticmethod
    def resolve_template(obj):
        return obj.template.url if obj.template else None


class EventoSchema(Schema):
    content_type: str = 'eventos.evento'
    id: int
    nome: str
    apresentacao: str
    carga_horaria_em_segundos: int | None
    imagem: str | None
    local: str
    localizacao: str | None
    periodo_formatado: str
    horario_formatado: str | None
    data_inicio: datetime.date
    hora_inicio: datetime.time
    data_fim: datetime.date | None
    hora_fim: datetime.time | None
    campus: str | None
    campus_id: int | None
    campus_sigla: str | None
    campus_nome: str | None
    link_suap: str
    estah_em_periodo_inscricao: bool | None
    estah_em_periodo_submissao: bool | None
    link_submissao: str | None
    situacao: str | None
    modalidades: list[ModalidadeSubmissaoSchema] = []
    # Novos campos adicionados
    site: str | None
    periodos_inscricoes: list[PeriodoInscricaoTipoSchema]
    periodo_submissao_formatado: str | None
    periodo_submissao: PeriodoSchema | None
    periodo_avaliacao_formatado: str | None
    periodo_avaliacao: PeriodoSchema | None
    programacao: list[ProgramacaoDiaSchema]

    @staticmethod
    def resolve_carga_horaria_em_segundos(obj):
        return obj.carga_horaria

    @staticmethod
    def resolve_imagem(obj):
        return obj.imagem.url if obj.imagem else None

    @staticmethod
    def resolve_localizacao(obj):
        return obj.classificacao.descricao if obj.classificacao else None

    @staticmethod
    def resolve_periodo_formatado(obj):
        return obj.get_periodo_evento()

    @staticmethod
    def resolve_horario_formatado(obj):
        return formatar_horario(obj.hora_inicio, obj.hora_fim)

    @staticmethod
    def resolve_campus(obj: Evento) -> str | None:
        return obj.campus.sigla if obj.campus else None

    @staticmethod
    def resolve_campus_id(obj: Evento) -> int | None:
        return obj.campus_id

    @staticmethod
    def resolve_campus_sigla(obj: Evento) -> str | None:
        return obj.campus.sigla if obj.campus else None

    @staticmethod
    def resolve_campus_nome(obj: Evento) -> str | None:
        return obj.campus.nome if obj.campus else None

    @staticmethod
    def resolve_link_suap(obj: Evento) -> str:
        return f'{settings.SITE_URL}{obj.get_url_inscricao()}'

    @staticmethod
    def resolve_estah_em_periodo_inscricao(obj):
        return obj.estah_em_periodo_inscricao()

    @staticmethod
    def resolve_estah_em_periodo_submissao(obj):
        return obj.estah_em_periodo_submissao()

    @staticmethod
    def resolve_link_submissao(obj):
        if obj.estah_em_periodo_submissao():
            return f'{settings.SITE_URL}{obj.get_url_submissao()}'
        return None

    @staticmethod
    def resolve_situacao(obj):
        return obj.get_situacao_por_periodo()

    @staticmethod
    def resolve_periodos_inscricoes(obj):
        """Retorna os períodos de inscrição por tipo de participante com datas normalizadas"""
        tipos_com_inscricao_direta = [tipo for tipo in obj.tipos_participante.all() if tipo.permite_inscricao_direta]

        periodos = []
        for tipo in tipos_com_inscricao_direta:
            periodo_formatado = formatar_periodo(
                data_inicio=tipo.data_inicio_inscricoes,
                data_fim=tipo.data_fim_inscricoes,
                hora_inicio=tipo.hora_inicio_inscricoes,
                hora_fim=tipo.hora_fim_inscricoes,
                data_inicio_fallback=obj.data_inicio,
                data_fim_fallback=obj.data_fim,
            )

            periodos.append(
                {
                    'tipo_participacao': tipo.tipo_participacao.descricao,
                    'periodo_formatado': periodo_formatado,
                    'data_inicio': tipo.data_inicio_inscricoes,
                    'hora_inicio': tipo.hora_inicio_inscricoes,
                    'data_fim': tipo.data_fim_inscricoes,
                    'hora_fim': tipo.hora_fim_inscricoes,
                }
            )

        return periodos

    @staticmethod
    def resolve_periodo_submissao_formatado(obj):
        """Retorna o período de submissão formatado"""
        return obj.get_periodo_submissao_formatado()

    @staticmethod
    def resolve_periodo_submissao(obj):
        """Retorna o período de submissão normalizado com data de início e fim"""
        return obj.get_periodo_por_etapa(EtapaPeriodoSubmissao.SUBMISSAO)

    @staticmethod
    def resolve_periodo_avaliacao_formatado(obj):
        """Retorna o período de avaliação formatado"""
        return obj.get_periodo_avaliacao_formatado()

    @staticmethod
    def resolve_periodo_avaliacao(obj):
        """Retorna o período de avaliação normalizado com data de início e fim"""
        return obj.get_periodo_por_etapa(EtapaPeriodoSubmissao.AVALIACAO)

    @staticmethod
    def resolve_programacao(obj):
        """Retorna a programação do evento agrupada por dia"""
        programacao = obj.get_programacao()
        resultado = []
        for dia, atividades in programacao:
            resultado.append({'data': dia, 'atividades': list(atividades)})
        return resultado

    @staticmethod
    def resolve_modalidades(obj):
        """Retorna as modalidades de submissão do evento"""
        return obj.modalidade_set.all()
