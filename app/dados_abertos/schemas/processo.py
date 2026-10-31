from ninja import Schema

from processo_eletronico.models import Processo


class ProcessoSchema(Schema):
    numero: str | None
    interessado: str
    assunto: str
    data_cadastro: str
    campus_origem: str
    situacao: str
    tramites: str

    @staticmethod
    def resolve_numero(obj: Processo) -> str | None:
        return obj.numero_protocolo_fisico

    @staticmethod
    def resolve_interessado(obj):
        return ', '.join(obj.interessados.values_list('pessoa__nome', flat=True))

    @staticmethod
    def resolve_assunto(obj):
        return obj.assunto

    @staticmethod
    def resolve_data_cadastro(obj):
        return obj.data_hora_criacao.strftime('%d/%m/%Y %H:%M')

    @staticmethod
    def resolve_campus_origem(obj):
        return obj.setor_criacao.uo.sigla

    @staticmethod
    def resolve_valor_executado(obj):
        return obj.valor_executado

    @staticmethod
    def resolve_situacao(obj):
        return obj.get_status_display()

    @staticmethod
    def resolve_tramites(obj):
        return ', '.join(obj.tramites.values_list('destinatario_setor__sigla', flat=True))
