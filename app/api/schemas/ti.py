import datetime

from django.utils.html import strip_tags
from ninja import Schema

from catalogo_provedor_servico.models import RegistroAvaliacaoGovBR, Solicitacao
from catalogo_provedor_servico.providers.factory import get_service_provider_factory
from comum.models import APIExterna


def serialize_obj(obj, serializer_class):
    return serializer_class.from_orm(obj).model_dump()


def serialize_list(objs, serializer_class):
    return [serialize_obj(obj, serializer_class) for obj in objs]


def get_situacao_display(etapa):
    for situacao in Solicitacao.STATUS_CHOICES:
        if situacao[0] == etapa:
            return situacao[1]
    return etapa


class ServicoSchema(Schema):
    id_servico_portal_govbr: int | None = None
    titulo: str | None = None
    descricao: str | None = None
    icone: str | None = None


class DisponibilidadeServicoSchema(Schema):
    servico: ServicoSchema | None = None
    cpf: str | None = None
    criterios_sucesso: list | None = None
    criterios_erro: list | None = None
    is_ok: bool | None = None


class SolicitacaoSchema(Schema):
    servico: int | None = None
    protocolo: int | None = None
    etapa: str | None = None
    dataEtapa: str | None = None
    situacaoEtapa: str | None = None
    dataSituacaoEtapa: str | None = None
    orgao: int | None = None
    nome_servico: str | None = None
    url_avaliacao: str | None = None

    @staticmethod
    def resolve_servico(obj):
        return obj.servico.id_servico_portal_govbr if obj.servico else None

    @staticmethod
    def resolve_protocolo(obj):
        return obj.id

    @staticmethod
    def resolve_etapa(obj):
        return get_situacao_display(obj.status)

    @staticmethod
    def resolve_dataEtapa(obj):
        return obj.data_criacao.strftime('%d/%m/%Y - %H:%M:%S')

    @staticmethod
    def resolve_situacaoEtapa(obj):
        return strip_tags(obj.status_detalhamento or '') or get_situacao_display(obj.status)

    @staticmethod
    def resolve_dataSituacaoEtapa(obj):
        return obj.data_ultima_atualizacao.strftime('%d/%m/%Y - %H:%M:%S')

    @staticmethod
    def resolve_orgao(obj):
        return obj.uo.id if obj.uo else None

    @staticmethod
    def resolve_nome_servico(obj):
        return obj.servico.titulo

    @staticmethod
    def resolve_url_avaliacao(obj):
        if obj.status == Solicitacao.STATUS_ATENDIDO:
            registro_avaliacao = RegistroAvaliacaoGovBR.objects.filter(solicitacao=obj.solicitacao).first()
            if registro_avaliacao:
                if not registro_avaliacao.url_avaliacao:
                    service_provider = get_service_provider_factory().get_service_provider(
                        id_servico_portal_govbr=obj.servico.id_servico_portal_govbr
                    )
                    service_provider.obter_formulario_avaliacao(obj.solicitacao)
                elif not registro_avaliacao.avaliado:
                    api = APIExterna.AVALIACAO_GOVBR
                    if api.ativo:
                        api.get_service().atualizar_registro_avaliacao(obj)
                elif registro_avaliacao.avaliado:
                    return 'Avaliado'
                return registro_avaliacao.url_avaliacao
        return None


class RespostaSchema(Schema):
    resposta: dict | list | None = None
    mensagem: str | None = None
    has_error: bool | None = None


class AutocompleteSchema(Schema):
    results: list | None = None
    pagination: dict | None = None


class AtualizacaoSchema(Schema):
    id: int
    descricao: str = None
    tags: list[str] = None
    grupos: list[str] = None
    data: datetime.date = None
    tipo: str = None
    demanda: str

    @staticmethod
    def resolve_grupos(obj):
        return [str(grupo) for grupo in obj.grupos.all()]

    @staticmethod
    def resolve_tags(obj):
        return [str(tag) for tag in obj.tags.all()]

    @staticmethod
    def resolve_demanda(obj):
        return str(obj.demanda)
