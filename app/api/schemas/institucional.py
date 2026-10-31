import datetime

from ninja import Field, FilterSchema, Schema

from rh.enums import Nacionalidade
from suap import settings

from .ensino import AlunoSchema
from .rh import ServidorSchema


class ParticipacaoSchema(Schema):
    edital: str = Field(None, alias='projeto.edital.titulo')
    projeto: str = Field(None, alias='projeto.titulo')


class ParticipacoesProjetoSchema(Schema):
    participacoes_extensao: list[ParticipacaoSchema]
    participacoes_pesquisa: list[ParticipacaoSchema]


class ProjetoSchema(Schema):
    content_type: str
    id: int
    tipo: str
    titulo: str
    resumo: str
    dt_inicio: datetime.date
    dt_final: datetime.date
    situacao: str
    edital: int
    campus: str
    nome_coordenador: str
    email_coordenador: str


class EstatisticasCampusSchema(Schema):
    campus_id: int
    campus_sigla: str
    campus_nome: str
    alunos_ativos: int
    servidores_ativos: int


class DadosSuapEmNumerosSchema(Schema):
    content_type: str = 'institucional.suap_em_numeros'
    id: int = 1
    alunos_ativos: int = None
    servidores_ativos: int = None
    projetos_extensao_em_execucao: int = None
    projetos_pesquisa_em_execucao: int = None
    estatisticas_por_campus: list[EstatisticasCampusSchema] = Field(default_factory=list)


class SuapEmNumerosSchema(Schema):
    next: str | None = None
    previous: str | None = None
    results: DadosSuapEmNumerosSchema = None


class PrestadorSchema(Schema):
    matricula: str = None
    nome: str = Field(None, alias='pessoa_fisica.nome')
    setor_suap: str | None = None
    campus: str | None = None
    url_foto_75x100: str | None = None

    @staticmethod
    def resolve_setor_suap(obj):
        if obj.setor:
            return obj.setor.sigla
        else:
            return None

    @staticmethod
    def resolve_campus(obj):
        if obj.setor and obj.setor.uo:
            return obj.setor.uo.sigla
        else:
            if obj.setor_exercicio and obj.setor_exercicio.uo:
                return obj.setor_exercicio.uo.sigla
            return None

    @staticmethod
    def resolve_url_foto_75x100(obj):
        return obj.get_foto_75x100_url_publica()


class UserSchema(Schema):
    id: int = None
    matricula: str = Field(None, alias='username')
    nome_usual: str = None
    cpf: str = None
    rg: str = None
    filiacao: list = None
    data_nascimento: datetime.date | None = None
    naturalidade: str = None
    tipo_sanguineo: str = None
    email: str = None
    url_foto_75x100: str = None
    url_foto_150x200: str = None
    tipo_vinculo: str = None
    vinculo: dict | None = None

    @staticmethod
    def resolve_id(obj):
        return obj.get_profile().id

    @staticmethod
    def resolve_nome_usual(obj):
        return obj.get_profile().nome_usual

    @staticmethod
    def resolve_cpf(obj):
        return obj.get_profile().cpf or ''

    @staticmethod
    def resolve_rg(obj):
        return obj.get_profile().rg_display

    @staticmethod
    def resolve_data_nascimento(obj):
        return obj.get_profile().nascimento_data

    @staticmethod
    def resolve_tipo_sanguineo(obj):
        return obj.get_profile().tipo_sanguineo

    @staticmethod
    def resolve_naturalidade(obj):
        if obj.get_profile().nascimento_municipio:
            return f'{obj.get_profile().nascimento_municipio.nome}/{obj.get_profile().nascimento_municipio.uf}'
        return '-'

    @staticmethod
    def resolve_filiacao(obj):
        return [obj.get_profile().nome_mae, obj.get_profile().nome_pai]

    @staticmethod
    def resolve_url_foto_75x100(obj):
        v = obj.get_vinculo()
        return v.get_foto_75x100_url_publica() if v else None

    @staticmethod
    def resolve_url_foto_150x200(obj):
        v = obj.get_vinculo()
        return v.get_foto_150x200_url_publica() if v else None

    @staticmethod
    def resolve_tipo_vinculo(obj):
        return obj.get_vinculo().get_vinculo_institucional_title

    @staticmethod
    def resolve_vinculo(obj):
        sub_instance = obj.get_relacionamento()
        if obj.eh_servidor:
            return ServidorSchema.from_orm(sub_instance).dict()
        elif obj.eh_prestador:
            return PrestadorSchema.from_orm(sub_instance).dict()
        elif obj.eh_aluno:
            return AlunoSchema.from_orm(sub_instance).dict()
        else:
            return None


class DetalheVinculoAluno(Schema):
    modalidade: str
    nivel_ensino: str
    curso: str
    ativo: bool


class DetalheVinculoServidor(Schema):
    cargo: str
    categoria: str


class VinculoSchema(Schema):
    id: int = None
    identificador: str
    tipo: str
    campus: str | None
    estrangeiro: bool
    detalhamento: DetalheVinculoAluno | DetalheVinculoServidor | None = None

    @staticmethod
    def resolve_id(obj):
        return obj.id

    @staticmethod
    def resolve_identificador(obj):
        if obj.user:
            return obj.user.username
        return obj.relacionamento.matricula or ''

    @staticmethod
    def resolve_estrangeiro(obj):
        return obj.pessoa.pessoafisica.nacionalidade == Nacionalidade.ESTRANGEIRO

    @staticmethod
    def resolve_tipo(obj):
        if obj.eh_aluno():
            return 'aluno'
        elif obj.eh_servidor():
            return 'servidor'
        elif obj.eh_prestador():
            return 'prestador_servico'
        elif obj.eh_usuario_externo():
            return 'usuario_externo'
        elif obj.eh_pessoaexterna():
            return 'pessoa_externa'
        elif obj.eh_pessoajuridica():
            return 'pessoa_juridica'
        return 'outro'

    @staticmethod
    def resolve_campus(obj):
        if obj.eh_aluno() or obj.eh_servidor() or obj.eh_prestador():
            return obj.setor.uo.sigla if obj.setor else None
        return None

    @staticmethod
    def resolve_detalhamento(obj):
        sub_instance = obj.relacionamento
        if obj.eh_aluno():
            return DetalheVinculoAluno(
                curso=sub_instance.curso_campus.descricao_historico,
                modalidade=sub_instance.curso_campus.modalidade.descricao,
                nivel_ensino=sub_instance.curso_campus.modalidade.nivel_ensino.descricao,
                ativo=sub_instance.situacao.ativo,
            )
        elif obj.eh_servidor():
            return DetalheVinculoServidor(
                cargo=sub_instance.cargo_emprego.nome, categoria='Docente' if sub_instance.eh_docente else 'Técnico Administrativo'
            )
        elif obj.eh_prestador():
            return None
        else:
            return None


class DocumentoTextoSchema(Schema):
    identificador: str
    assunto: str = None
    status: str = None
    url_publica: str = None

    @staticmethod
    def resolve_status(obj):
        return obj.get_status_display()

    @staticmethod
    def resolve_url_publica(obj):
        return settings.SITE_URL + f'/documento_eletronico/conteudo_documento/{obj.uuid}'


class DocumentoTextoFiltersSchema(FilterSchema):
    identificador: str | None = None
    assunto: str | None = None
