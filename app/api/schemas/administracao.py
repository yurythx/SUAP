import datetime

from ninja import FilterSchema, Schema
from pydantic import ConfigDict, Field

from djtools.utils import anonimizar_cpf
from portaria.models import ConfiguracaoSistemaPortaria
from protocolo.models import Processo


class ProcessoSchema(Schema):
    id: int
    numero_processo: str
    interessado: str = Field(None, alias='interessado_nome')
    assunto: str = None
    data_cadastro: datetime.datetime = None
    campus: str = Field(None, alias='uo.sigla')
    situacao: str = None
    tramites: list[str] = None

    @staticmethod
    def resolve_situacao(obj):
        return obj.get_status_display()

    @staticmethod
    def resolve_tramites(obj):
        setores_tramites = []
        for tramite in obj.tramite_set.all():
            setores_tramites.append(str(tramite.orgao_encaminhamento))

        return setores_tramites


class TramiteProcessoSchema(Schema):
    ordem: int = None
    data_encaminhamento: datetime.datetime = None
    vinculo_encaminhamento: str = Field(None, alias='vinculo_encaminhamento.pessoa.nome')
    observacao_encaminhamento: str = None
    vinculo_recebimento: str = Field(None, alias='vinculo_recebimento.pessoa.nome')
    orgao_encaminhamento: str = None
    orgao_recebimento: str = None
    data_recebimento: datetime.datetime = None
    observacao_recebimento: str = None
    situacao: str = None

    @staticmethod
    def resolve_orgao_encaminhamento(obj):
        return str(obj.orgao_encaminhamento)

    @staticmethod
    def resolve_orgao_recebimento(obj):
        return str(obj.orgao_recebimento)

    @staticmethod
    def resolve_situacao(obj):
        if obj.recebido:
            return 'Recebido'
        else:
            return 'Aguardando recebimento'


class ProcessoDetalheSchema(Schema):
    id: int
    numero_processo: str
    interessado: str = Field(None, alias='interessado_nome')
    assunto: str = None
    data_cadastro: datetime.datetime = None
    campus: str = Field(None, alias='uo.sigla')
    operador: str = Field(None, alias='vinculo_cadastro.pessoa.nome')
    tipo_processo: str = None
    situacao: str = None
    orgao_responsavel: str = None
    numero_documento: str | None = None
    palavras_chave: str | None = None
    tramites: list[dict] = None

    @staticmethod
    def resolve_situacao(obj):
        return obj.get_status_display()

    @staticmethod
    def resolve_tramites(obj):
        tramites = []
        for tramite in obj.tramite_set.all():
            tramites.append(TramiteProcessoSchema.from_orm(tramite).dict())

        if obj.status in [Processo.STATUS_FINALIZADO, Processo.STATUS_ARQUIVADO]:
            tramites.append(
                {
                    'ordem': obj.tramite_set.count() + 1,
                    'setor': str(obj.tramite_set.order_by('-ordem')[0].orgao_interno_recebimento),
                    'data_finalizacao': obj.data_finalizacao,
                    'pessoa_finalizacao': obj.vinculo_finalizacao.pessoa.nome,
                    'observacao_finalizacao': obj.observacao_finalizacao,
                    'situacao': obj.get_status_display(),
                }
            )
        return tramites

    @staticmethod
    def resolve_tipo_processo(obj):
        return obj.get_tipo_display()

    @staticmethod
    def resolve_orgao_responsavel(obj):
        return str(obj.get_orgao_responsavel_atual())


class ProcessoFiltersSchema(FilterSchema):
    assunto: str | None = None
    status: int | None = None
    uo: str | None = Field(None, q=['uo__sigla', 'uo__nome'])
    data_cadastro: datetime.date | None = Field(None, q=['data_cadastro__date'])


def to_camel(string: str) -> str:
    return 'Simultaneous-Use' if string == 'simultaneous_use' else string


class AcessoSchema(Schema):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)
    chave_wifi: str = None
    expiration: str = None
    simultaneous_use: int = None

    @staticmethod
    def resolve_expiration(obj):
        expiration_date = obj.data_geracao_chave_wifi + datetime.timedelta(obj.quantidade_dias_chave_wifi)
        return expiration_date.isoformat()

    @staticmethod
    def resolve_simultaneous_use(obj):
        conf = ConfiguracaoSistemaPortaria.objects.get(campus=obj.local_acesso)
        return conf.limite_compartilhamento_chave


class MaoDeObraSchema(Schema):
    content_type: str = 'contratos.mao_de_obra'
    id: int | None = Field(None, alias='pk')
    pessoa_id: int | None = Field(None, alias='prestador_servico.pessoa_fisica.pk')
    nome: str | None = Field(None, alias='prestador_servico.pessoa_fisica.nome')
    cpf: str | None
    ocupacao: str | None
    setor: str | None
    campus: str | None = Field(None, alias='campus.nome')

    @staticmethod
    def resolve_ocupacao(obj):
        return ', '.join([op.ocupacao.descricao for op in obj.prestador_servico.ocupacaoprestador_set.all() if op.ocupacao])

    @staticmethod
    def resolve_cpf(obj):
        return anonimizar_cpf(obj.prestador_servico.pessoa_fisica.cpf)

    @staticmethod
    def resolve_setor(obj):
        return f'{obj.prestador_servico.setor.nome} ({obj.prestador_servico.setor.sigla})' if obj.prestador_servico.setor else None


class MaoDeObraFiltersSchema(FilterSchema):
    nome: str | None = Field(None, q='prestador_servico__pessoa_fisica__nome__icontains')
    campus: str | None = Field(None, q='campus__nome__icontains')
    setor: str | None = Field(None, q='prestador_servico__setor__sigla__icontains')
