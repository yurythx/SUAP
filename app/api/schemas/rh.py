import datetime

from django.db.models import Q
from ninja import FilterSchema, Schema
from ninja.orm import create_schema
from pydantic import Field

from contracheques.models import ContraCheque, ContraChequeRubrica
from djtools.ninja.filters import filter_by_integer_or_text_fields
from djtools.utils import anonimizar_matricula
from ferias.models import InterrupcaoFerias
from rh.models import UnidadeOrganizacional

UOSchema = create_schema(
    UnidadeOrganizacional,
    fields=(
        'nome',
        'sigla',
        'endereco',
        'cep',
        'telefone',
        'fax',
    ),
)


class DadosServidorResumidoSchema(Schema):
    matricula: str
    nome: str
    campus: str | None = None
    email: str | None = None
    foto: str | None = None


class ServidorSchema(Schema):
    matricula: str = None
    nome: str = Field(None, alias='pessoa_fisica.nome')
    setor_suap: str | None
    setor_siape: str | None
    jornada_trabalho: str | None
    campus: str | None
    cargo: str | None = None
    funcao: list[str] = None
    disciplina_ingresso: str | None
    categoria: str | None
    telefones_institucionais: list[str] = None
    url_foto_75x100: str | None
    curriculo_lattes: str | None = Field(None, alias='pessoa_fisica.lattes')

    @staticmethod
    def resolve_setor_suap(obj):
        if obj.setor:
            return obj.setor.sigla
        else:
            return None

    @staticmethod
    def resolve_setor_siape(obj):
        if obj.setor_exercicio:
            return obj.setor_exercicio.sigla
        else:
            return None

    @staticmethod
    def resolve_jornada_trabalho(obj):
        if obj.jornada_trabalho:
            return obj.jornada_trabalho.nome
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
    def resolve_cargo(obj):
        if obj.cargo_emprego:
            return obj.cargo_emprego.nome
        else:
            return None

    @staticmethod
    def resolve_funcao(obj):
        hoje = datetime.datetime.now()
        historico_list = []
        for historico in obj.historico_funcao(hoje, hoje):
            historico_list.append(historico.funcao_display)
        return historico_list

    @staticmethod
    def resolve_disciplina_ingresso(obj):
        if obj.eh_docente and obj.get_vinculo().professor_set.all().exists():
            return str(obj.get_vinculo().professor_set.all()[0].disciplina)
        return '-'

    @staticmethod
    def resolve_telefones_institucionais(obj):
        return obj.telefones_institucionais.split(', ')

    @staticmethod
    def resolve_url_foto_75x100(obj):
        return obj.get_foto_75x100_url_publica()


class ServidorFuncaoAtivaSchema(Schema):
    content_type: str = 'rh.servidor_funcao_ativa'
    id: int = Field(None, alias='pessoa_fisica.pk')
    matricula: str = None
    nome: str = Field(None, alias='pessoa_fisica.nome')
    funcao: list[str] = None
    campus: str | None
    setor: str | None
    email_setor: str | None = Field(None, alias='setor.email')
    telefones_institucionais: list[str] = None
    telefone_campus: str | None = Field(None, alias='setor.uo.telefone')
    curriculo_lattes: str | None = Field(None, alias='pessoa_fisica.lattes')

    @staticmethod
    def resolve_matricula(obj):
        return anonimizar_matricula(obj.matricula)

    @staticmethod
    def resolve_funcao(obj):
        hoje = datetime.datetime.now()
        historico_list = []
        for historico in obj.historico_funcao(hoje, hoje):
            historico_list.append(historico.funcao_display)
        return historico_list

    @staticmethod
    def resolve_campus(obj):
        if obj.setor and obj.setor.uo:
            return obj.setor.uo.nome
        else:
            if obj.setor_exercicio and obj.setor_exercicio.uo:
                return obj.setor_exercicio.uo.nome
            return None

    @staticmethod
    def resolve_setor(obj):
        return f'{obj.setor.nome} ({obj.setor.sigla})' if obj.setor else None

    @staticmethod
    def resolve_telefones_institucionais(obj):
        return obj.telefones_institucionais.split(', ')


class ServidorFiltersSchema(FilterSchema):
    nome: str | None = Field(None, q='pessoa_fisica__nome__icontains')
    campus: str | None = Field(None, q='setor__uo__sigla')
    matricula: str | None = None
    setor: str | None = Field(None, q='setor__sigla__icontains')
    cargo_emprego: str | None = Field(None, q='cargo_emprego__nome__icontains')


class DadosBancariosServidorSchema(Schema):
    codigo_do_banco: str | None = Field(None, alias='pagto_banco.codigo')
    nome_do_banco: str | None = Field(None, alias='pagto_banco.nome')
    agencia: str | None = Field(None, alias='pagto_agencia')
    conta: str | None = Field(None, alias='pagto_ccor')
    operacao: str

    @staticmethod
    def resolve_operacao(obj):
        return obj.pagto_ccor_tipo or ''


class ServidorDetalhadoSchema(Schema):
    matricula: str
    nome: str
    data_de_nascimento: datetime.date | None = Field(None, alias='pessoa_fisica.nascimento_data')
    cpf: str = Field(None, alias='pessoa_fisica.cpf')
    cargo: str | None = Field(None, alias='cargo_emprego.nome')
    categoria_do_cargo: str | None = Field(None, alias='cargo_emprego.grupo_cargo_emprego.categoria')
    setor: str = Field(None, alias='setor.sigla')
    campus: str = Field(None, alias='setor.uo.sigla')
    ativo: bool = False
    situacao: str = Field(None, alias='situacao.nome_siape')
    endereco: str | None = None
    email: str = Field(None, alias='email_institucional')
    email_secundario: str = Field(None, alias='email_pessoal')
    telefone: str | None = None
    foto: str | None = None
    dados_bancarios: DadosBancariosServidorSchema = None

    @staticmethod
    def resolve_endereco(obj):
        qs = obj.pessoa_fisica.pessoaendereco_set.all()
        for endereco in qs:
            return str(endereco)
        return ''

    @staticmethod
    def resolve_telefone(obj):
        return ', '.join({str(telefone) for telefone in obj.pessoa_fisica.pessoatelefone_set.all()})

    @staticmethod
    def resolve_foto(obj):
        return obj.get_foto_150x200_url_publica()

    @staticmethod
    def resolve_dados_bancarios(obj):
        return obj.pessoa_fisica


class ServidorIntegraSchema(Schema):
    cpf: str = Field(None, alias='pessoa_fisica.cpf')
    nome: str = Field(None, alias='pessoa_fisica.nome')
    siape: str = Field(None, alias='matricula')
    campusId: int = Field(None, alias='setor.uo.id')
    campusNome: str = Field(None, alias='setor.uo.nome')
    email: str = Field(None, alias='email_institucional')
    tipoUsuario: str = Field(None, alias='cargo_emprego.grupo_cargo_emprego.categoria')
    sexo: str = Field(None, alias='pessoa_fisica.sexo')
    situacao: str = Field(None, alias='situacao.nome')
    ativo: bool = Field(None, alias='ativo')


class SetorCampusSchema(Schema):
    id: int
    sigla: str
    nome: str


class SetorSchema(Schema):
    id: int = None
    superior_id: int | None = None
    nome: str = None
    sigla: str = None
    hierarquia: list[str] = None
    campus: SetorCampusSchema | None = None
    email: str | None = None
    telefones: list[str] = None
    chefes: list[str] = None
    total_servidores: int = None

    @staticmethod
    def resolve_hierarquia(obj):
        caminho = obj.get_caminho()
        caminho_str = []
        for s in caminho:
            if hasattr(s, 'unidadeorganizacional') or s == caminho[-1]:
                s_repr = str(s)
            else:
                s_repr = str(s)
            caminho_str.append(s_repr)
        return caminho_str

    @staticmethod
    def resolve_campus(obj):
        if obj.uo:
            return {'id': obj.uo.pk, 'sigla': obj.uo.sigla, 'nome': obj.uo.nome}
        return None

    @staticmethod
    def resolve_total_servidores(obj):
        return obj.get_servidores().count()

    @staticmethod
    def resolve_telefones(obj):
        telefones = []
        for telefone in obj.setortelefone_set.all():
            telefones.append(str(telefone))
        return telefones

    @staticmethod
    def resolve_chefes(obj):
        chefes = []
        for chefe in obj.chefes:
            chefes.append(chefe.nome)
        return chefes


class SetorFiltersSchema(FilterSchema):
    nome: str | None = None
    sigla: str | None = None
    uo: str | None = None
    excluido: bool | None = None
    areas_vinculacao: str | None = Field(None, q='areas_vinculacao__descricao')

    def filter_uo(self, value: str | None) -> Q:
        return filter_by_integer_or_text_fields(value, integer_lookups=['uo_id'], text_lookups=['uo__sigla__iexact', 'uo__nome__iexact'])


class EventoSchema(Schema):
    descricao: str = None
    css: str = None


class HistoricoFuncionalSchema(Schema):
    eventos: list[EventoSchema]
    css: str = None
    data: str = None


class ServidorOcorrenciaSchema(Schema):
    tipo_ocorrencia: str = None
    descricao: str = Field(None, alias='ocorrencia.nome')
    data: datetime.date = None
    data_termino: datetime.date | None = None
    total_dias: int | None = None

    @staticmethod
    def resolve_tipo_ocorrencia(obj):
        if obj.subgrupo:
            return obj.subgrupo.descricao
        else:
            return obj.ocorrencia.grupo_ocorrencia.nome

    @staticmethod
    def resolve_total_dias(obj):
        if obj.data_termino:
            return (obj.data - obj.data_termino).days + 1
        else:
            return None


class ServidorAfastamentoSchema(Schema):
    tipo_afastamento: str = None
    descricao: str = Field(None, alias='afastamento.nome')
    data_inicio: datetime.date = None
    data_termino: datetime.date | None = None
    total_dias: int | None = None

    @staticmethod
    def resolve_tipo_afastamento(obj):
        return obj.afastamento.get_tipo_display()

    @staticmethod
    def resolve_total_dias(obj):
        if obj.data_termino:
            return (obj.data_termino - obj.data_inicio).days + 1
        else:
            return None


class OcorrenciaAfastamentoSchema(Schema):
    ocorrencias: list[ServidorOcorrenciaSchema]
    afastamentos: list[ServidorAfastamentoSchema]


class EuSchema(Schema):
    identificacao: str
    nome_social: str
    nome_usual: str
    nome_registro: str
    nome: str
    primeiro_nome: str
    ultimo_nome: str
    email: str
    email_secundario: str
    email_google_classroom: str
    email_academico: str
    campus: str
    foto: str
    tipo_usuario: str
    email_preferencial: str
    cpf: str | None = None
    data_de_nascimento: datetime.date | None = None
    sexo: str | None = None
    passaporte: str | None = None


class CarteiraFuncionalSchema(Schema):
    codigo_verificador: str
    data_emissao: datetime.datetime | None = None
    data_validade: datetime.datetime | None = None


InterrupcaoFeriasSchema = create_schema(
    InterrupcaoFerias,
    fields=(
        'data_interrupcao_periodo',
        'data_inicio_continuacao_periodo',
        'data_fim_continuacao_periodo',
    ),
)


class FeriasSchema(Schema):
    ano: int = Field(None, alias='ano.ano')
    data_inicio_periodo1: datetime.date | None = None
    data_fim_periodo1: datetime.date | None = None
    data_inicio_periodo2: datetime.date | None = None
    data_fim_periodo2: datetime.date | None = None
    data_inicio_periodo3: datetime.date | None = None
    data_fim_periodo3: datetime.date | None = None
    status: str = None
    interrupcoes: list[InterrupcaoFeriasSchema] = Field(None, alias='interrupcaoferias_set')

    @staticmethod
    def resolve_status(obj):
        return obj.get_status()

    @staticmethod
    def get_interrupcoes(obj):
        return InterrupcaoFeriasSchema.from_orm(obj.interrupcaoferias_set.all())


class FrequenciaHojeSchema(Schema):
    acao: str = None
    horario: datetime.datetime = None


class FrequenciaSchema(Schema):
    frequencias_hoje: list[FrequenciaHojeSchema]
    total_tempo_hoje: str
    total_tempo_semana: str


ContrachequeSchemaBase = create_schema(ContraCheque, fields=('ano', 'mes', 'bruto', 'liquido', 'desconto'))


class MeuContrachequeSchema(ContrachequeSchemaBase):
    ano: int = Field(None, alias='ano.ano')
    nome_mes: str = None

    @staticmethod
    def resolve_nome_mes(obj):
        return obj.get_mes_display()


class MeuContraChequeRubricaSchema(Schema):
    descricao: str = Field(None, alias='rubrica.nome')
    valor: str = Field(None, alias='valor', coerce_numbers_to_str=True)


class MeuContrachequeDetalheSchema(ContrachequeSchemaBase):
    rendimentos: list[MeuContraChequeRubricaSchema] = None
    descontos: list[MeuContraChequeRubricaSchema] = None
    ano: int = Field(None, alias='ano.ano')
    nome_mes: str = None

    @staticmethod
    def resolve_nome_mes(obj):
        return obj.get_mes_display()

    @staticmethod
    def resolve_rendimentos(obj):
        return ContraChequeRubrica.objects.filter(contra_cheque=obj, tipo__nome='Rendimento')

    @staticmethod
    def resolve_descontos(obj):
        return ContraChequeRubrica.objects.filter(contra_cheque=obj, tipo__nome='Desconto')


class RubricaSchema(Schema):
    valor: float
    prazo: str
    codigo: str = Field(None, alias='rubrica.codigo')
    nome: str = Field(None, alias='rubrica.nome')
    tipo_codigo: str = Field(None, alias='tipo.codigo')
    tipo_nome: str = Field(None, alias='tipo.nome')


class ContrachequeSchema(Schema):
    matricula: str = Field(None, alias='servidor.matricula')
    nome: str = Field(None, alias='servidor.pessoa_fisica.nome')
    cpf: str = Field(None, alias='servidor.pessoa_fisica.cpf')
    cargo: str = Field(None, alias='servidor.cargo_emprego.nome')
    categoria: str | None = Field(None, alias='servidor.cargo_emprego.grupo_cargo_emprego.categoria')
    campus: str = Field(None, alias='servidor.setor.uo.sigla')
    ativo: bool = Field(None, alias='servidor.ativo')
    situacao: str = Field(None, alias='servidor.situacao.nome_siape')
    email: str
    endereco: str
    telefones: str
    banco: str = Field(None, alias='servidor.pessoa_fisica.pagto_banco.nome')
    agencia: str = Field(None, alias='servidor.pessoa_fisica.pagto_agencia')
    conta_corrente: str = Field(None, alias='servidor.pessoa_fisica.pagto_ccor')
    valor_bruto: float
    rubricas: list[RubricaSchema] = Field(None, alias='contrachequerubrica_set')

    @staticmethod
    def resolve_email(obj):
        return obj.servidor.email_institucional or obj.servidor.email_pessoal

    @staticmethod
    def resolve_endereco(obj):
        qs = obj.servidor.pessoa_fisica.pessoaendereco_set.all()
        for endereco in qs:
            return str(endereco)
        return ''

    @staticmethod
    def resolve_telefones(obj):
        return ', '.join({str(telefone) for telefone in obj.servidor.pessoa_fisica.pessoatelefone_set.all()})

    @staticmethod
    def resolve_valor_bruto(obj):
        return obj.bruto or 0


class ContrachequeResponseSchema(Schema):
    ano: int
    mes: int
    contra_cheques: list[ContrachequeSchema]


class ContrachequeFiltersSchema(FilterSchema):
    ano: int = Field(q='ano__ano')
    mes: int
