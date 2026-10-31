import datetime
import enum
from decimal import Decimal

from ninja import FilterSchema, Schema
from ninja.orm import create_schema
from pydantic import Field

from cnpq.utils import extrair_dados_curriculo_lattes
from djtools.utils import normalizar_nome_proprio
from edu.models import Falta, Aula, ItemConfiguracaoAvaliacao, MaterialAula, MaterialDiario, MatriculaDiario, Professor
from rh.models import UnidadeOrganizacional


class ResponsavelSchema(FilterSchema):
    matricula: str
    chave: str


class TokenResponsavelSchema(Schema):
    token: str


class DependenteSchema(FilterSchema):
    foto: str | None
    matricula: str
    nome: str
    chave: str


class PeriodoSchema(Schema):
    id: int
    semestre: str

    @staticmethod
    def resolve_semestre(obj):
        return f'{obj.ano_letivo}.{obj.periodo_letivo}'


class UserSchema(Schema):
    id: int
    nome: str
    email: str


class AlunoDiarioSchema(Schema):
    id: int
    nome: str = None
    matricula: str = None
    email: str = None

    @staticmethod
    def resolve_nome(obj):
        return obj.get_nome() or ''

    @staticmethod
    def resolve_matricula(obj):
        return obj.matricula or ''

    @staticmethod
    def resolve_email(obj):
        return obj.email_notificacao or ''


class AlunoSchema(Schema):
    id: int
    matricula: str = None
    nome: str = None
    turno: str = None
    curso: str = Field(None, alias='curso_campus.descricao_historico')
    campus: str = None
    situacao: str = Field(None, alias='situacao.descricao')
    cota_sistec: str | None = None
    cota_mec: str | None = None
    situacao_sistemica: str = None
    matricula_regular: bool = Field(None, alias='aluno_especial')
    linha_pesquisa: str | None = None
    curriculo_lattes: str = Field(None, alias='pessoa_fisica.lattes')

    @staticmethod
    def resolve_campus(obj):
        return str(obj.curso_campus.diretoria.setor.uo)

    @staticmethod
    def resolve_nome(obj):
        return obj.get_nome()

    @staticmethod
    def resolve_cota_sistec(obj):
        return obj.get_cota_sistec_display()

    @staticmethod
    def resolve_cota_mec(obj):
        return obj.get_cota_mec_display()

    @staticmethod
    def resolve_situacao_sistemica(obj):
        return obj.get_situacao_sistemica()[1]

    @staticmethod
    def resolve_linha_pesquisa(obj):
        if obj.linha_pesquisa:
            return obj.linha_pesquisa.descricao
        else:
            return None

    @staticmethod
    def resolve_turno(obj):
        return obj.turno.descricao if obj.turno else ''


class ProfessorSchema(Schema):
    id: int
    nome: str = None
    matricula: str = None
    email: str

    @staticmethod
    def resolve_nome(obj):
        return obj.get_nome() or ''

    @staticmethod
    def resolve_matricula(obj):
        return obj.get_matricula() or ''

    @staticmethod
    def resolve_email(obj):
        return obj.vinculo.email_notificacao or ''


class AulaSchema(Schema):
    id: int
    etapa: str
    conteudo: str
    data: str
    qtd_aulas: int
    faltas: int

    @staticmethod
    def resolve_etapa(obj):
        return str(obj.etapa) if obj.etapa else ''

    @staticmethod
    def resolve_conteudo(obj):
        return obj.conteudo or ''

    @staticmethod
    def resolve_data(obj):
        return obj.data.strftime('%d/%m/%Y') if obj.data else ''

    @staticmethod
    def resolve_qtd_aulas(obj):
        return obj.quantidade or 0

    @staticmethod
    def resolve_faltas(obj, context):
        request = context.get('request', None)
        aluno = request.aluno if request else None
        falta = Falta.objects.filter(matricula_diario__matricula_periodo__aluno=aluno, aula=obj).order_by('-id').first()
        return falta and falta.quantidade or 0


class AulaAlunoSchema(AulaSchema):
    disciplina: str

    @staticmethod
    def resolve_disciplina(obj, context):
        return (
            Aula.objects.filter(pk=obj.pk)
            .values_list('professor_diario__diario__componente_curricular__componente__descricao_historico', flat=True)
            .first()
        )


class MensagemResponsavelSchema(Schema):
    id: int
    assunto: str
    conteudo: str
    anexo: str | None
    data_envio: str

    data_leitura: str | None = None
    pergunta: str | None = None
    data_pergunta: str | None = None
    resposta: str | None = None
    data_resposta: str | None = None

    pode_interagir: bool = False

    @staticmethod
    def resolve_data_envio(obj, context):
        return obj.data_envio.strftime('%d/%m/%Y %H:%M')

    @staticmethod
    def resolve_anexo(obj, context):
        return obj.anexo.url if obj.anexo else None

    @staticmethod
    def resolve_data_leitura(obj, context):
        data_leitura = obj.get_data_leitura(context['request'].user)
        return data_leitura.strftime('%d/%m/%Y %H:%M') if data_leitura else None

    @staticmethod
    def resolve_pergunta(obj, context):
        return obj.get_pergunta(context['request'].user)

    @staticmethod
    def resolve_data_pergunta(obj, context):
        data_pergunta = obj.get_data_pergunta(context['request'].user)
        return data_pergunta.strftime('%d/%m/%Y %H:%M') if data_pergunta else None

    @staticmethod
    def resolve_resposta(obj, context):
        return obj.get_resposta(context['request'].user)

    @staticmethod
    def resolve_data_resposta(obj, context):
        data_resposta = obj.get_data_resposta(context['request'].user)
        return data_resposta.strftime('%d/%m/%Y %H:%M') if data_resposta else None


class PerguntaMensagemResponsavelSchema(Schema):
    pergunta: str


class FrequenciaSchema(Schema):
    total_aulas: int
    total_faltas: int
    total_abonos: int
    percentual_frequencia: int


class CalendarioAcademicoSchema(Schema):
    id: int
    descricao: str
    tipo: str
    data_inicio: str
    data_fim: str
    data_fechamento_periodo: str
    eh_calendario_referencia: bool
    qtd_etapas: int
    data_inicio_etapa_1: str
    data_fim_etapa_1: str
    data_inicio_etapa_2: str | None = None
    data_fim_etapa_2: str | None = None
    data_inicio_etapa_3: str | None = None
    data_fim_etapa_3: str | None = None
    data_inicio_etapa_4: str | None = None
    data_fim_etapa_4: str | None = None
    data_inicio_trancamento: str | None = None
    data_fim_trancamento: str | None = None
    data_inicio_certificacao: str | None = None
    data_fim_certificacao: str | None = None
    data_inicio_prova_final: str = None
    data_fim_prova_final: str = None
    data_inicio_espaco_pedagogico: str | None = None
    data_fim_espaco_pedagogico: str | None = None

    @staticmethod
    def resolve_tipo(obj):
        return obj.get_tipo_display()

    @staticmethod
    def resolve_data_inicio(obj):
        return obj.data_inicio.strftime('%d/%m/%Y') if obj.data_inicio else None

    @staticmethod
    def resolve_data_fim(obj):
        return obj.data_fim.strftime('%d/%m/%Y') if obj.data_fim else None

    @staticmethod
    def resolve_data_fechamento_periodo(obj):
        return obj.data_fechamento_periodo.strftime('%d/%m/%Y') if obj.data_fechamento_periodo else None

    @staticmethod
    def resolve_data_inicio_etapa_1(obj):
        return obj.data_inicio_etapa_1.strftime('%d/%m/%Y') if obj.data_inicio_etapa_1 else None

    @staticmethod
    def resolve_data_fim_etapa_1(obj):
        return obj.data_fim_etapa_1.strftime('%d/%m/%Y') if obj.data_fim_etapa_1 else None

    @staticmethod
    def resolve_data_inicio_etapa_2(obj):
        return obj.data_inicio_etapa_2.strftime('%d/%m/%Y') if obj.data_inicio_etapa_2 else None

    @staticmethod
    def resolve_data_fim_etapa_2(obj):
        return obj.data_fim_etapa_2.strftime('%d/%m/%Y') if obj.data_fim_etapa_2 else None

    @staticmethod
    def resolve_data_inicio_etapa_3(obj):
        return obj.data_inicio_etapa_3.strftime('%d/%m/%Y') if obj.data_inicio_etapa_3 else None

    @staticmethod
    def resolve_data_fim_etapa_3(obj):
        return obj.data_fim_etapa_3.strftime('%d/%m/%Y') if obj.data_fim_etapa_3 else None

    @staticmethod
    def resolve_data_inicio_etapa_4(obj):
        return obj.data_inicio_etapa_4.strftime('%d/%m/%Y') if obj.data_inicio_etapa_4 else None

    @staticmethod
    def resolve_data_fim_etapa_4(obj):
        return obj.data_fim_etapa_4.strftime('%d/%m/%Y') if obj.data_fim_etapa_4 else None

    @staticmethod
    def resolve_data_inicio_trancamento(obj):
        return obj.data_inicio_trancamento.strftime('%d/%m/%Y') if obj.data_inicio_trancamento else None

    @staticmethod
    def resolve_data_fim_trancamento(obj):
        return obj.data_fim_trancamento.strftime('%d/%m/%Y') if obj.data_fim_trancamento else None

    @staticmethod
    def resolve_data_inicio_certificacao(obj):
        return obj.data_inicio_certificacao.strftime('%d/%m/%Y') if obj.data_inicio_certificacao else None

    @staticmethod
    def resolve_data_fim_certificacao(obj):
        return obj.data_fim_certificacao.strftime('%d/%m/%Y') if obj.data_fim_certificacao else None

    @staticmethod
    def resolve_data_inicio_prova_final(obj):
        return obj.data_inicio_prova_final.strftime('%d/%m/%Y') if obj.data_inicio_prova_final else None

    @staticmethod
    def resolve_data_fim_prova_final(obj):
        return obj.data_fim_prova_final.strftime('%d/%m/%Y') if obj.data_fim_prova_final else None

    @staticmethod
    def resolve_data_inicio_espaco_pedagogico(obj):
        return obj.data_inicio_espaco_pedagogico.strftime('%d/%m/%Y') if obj.data_inicio_espaco_pedagogico else None

    @staticmethod
    def resolve_data_fim_espaco_pedagogico(obj):
        return obj.data_fim_espaco_pedagogico.strftime('%d/%m/%Y') if obj.data_fim_espaco_pedagogico else None


class MaterialSchema(Schema):
    id: int
    data: str
    descricao: str
    url: str | None


class TrabalhoSchema(Schema):
    id: int
    titulo: str
    data_solicitacao: str
    data_limite: str
    etapa: str
    expirado: bool
    descricao: str
    url: str | None


class RespostaTopicoSchema(Schema):
    id: int
    comentario: str
    data: str
    usuario: str
    proprio: bool = False

    @staticmethod
    def resolve_data(obj):
        return obj.data.strftime('%d/%m/%Y %H:%M:%S') if obj.data else ''

    @staticmethod
    def resolve_usuario(obj):
        return str(obj.user) if obj.user else ''

    @staticmethod
    def resolve_proprio(obj, context):
        request = context.get('request', None)
        return obj.user == request.user if request and hasattr(request, 'user') else False


class TopicoSchema(Schema):
    id: int
    titulo: str
    descricao: str
    data: str
    etapa: str
    usuario: str
    proprio: bool = False
    respostas: list[RespostaTopicoSchema]

    @staticmethod
    def resolve_data(obj):
        return obj.data.strftime('%d/%m/%Y %H:%M:%S') if obj.data else ''

    @staticmethod
    def resolve_usuario(obj):
        return str(obj.user) if obj.user else ''

    @staticmethod
    def resolve_proprio(obj, context):
        request = context.get('request', None)
        return obj.user == request.user if request and hasattr(request, 'user') else False

    @staticmethod
    def resolve_etapa(obj):
        return str(obj.etapa) if obj.etapa else ''

    @staticmethod
    def resolve_respostas(obj):
        if hasattr(obj, 'respostadiscussao_set'):
            return obj.respostadiscussao_set.all()
        return []


class HorarioSchema(Schema):
    dia: str
    horario: str

    @staticmethod
    def resolve_dia(obj):
        # obj may be a model instance (has get_dia_semana_display) or a dict
        if hasattr(obj, 'get_dia_semana_display'):
            return obj.get_dia_semana_display()
        if isinstance(obj, dict):
            return obj.get('dia', '')
        return ''

    @staticmethod
    def resolve_horario(obj):
        # obj may be a model instance (has attribute horario_aula) or a dict
        if hasattr(obj, 'horario_aula'):
            return str(obj.horario_aula)
        if isinstance(obj, dict):
            return obj.get('horario', '')
        return ''


class LocalSchema(Schema):
    id: int
    sala: str


class SituacaoDisciplina(Schema):
    rotulo: str
    status: str


class NotaSchema(Schema):
    tipo: str
    nota: str | None


class DisciplinaSchema(Schema):
    id: int
    descricao: str | None = None
    sigla: str
    situacao: SituacaoDisciplina | None = None
    ch_total_aula: int = 0
    ch_total_relogio: int = 0
    ch_cumprida_aula: int = 0
    qtd_faltas: int = 0
    qtd_avaliacoes: int = 0
    frequencia: float = 0.0
    notas: list[NotaSchema] = []
    medias: list[NotaSchema] = []


class DiarioSchema(Schema):
    id: int
    disciplina: DisciplinaSchema = None
    professores: list[ProfessorSchema] | None = None
    horarios: list[HorarioSchema] | None = None
    local: LocalSchema | None = None
    laboratorio: LocalSchema | None = None
    ambiente_virtual: str = None

    @staticmethod
    def resolve_id(obj):
        return obj.diario.id

    @staticmethod
    def resolve_disciplina(obj):
        return obj.diario.componente_curricular.componente or None

    @staticmethod
    def resolve_professores(obj):
        return Professor.objects.filter(professordiario__diario=obj.diario).order_by('vinculo__pessoa__nome').distinct()

    @staticmethod
    def resolve_horarios(obj):
        return obj.diario.horarioauladiario_set.all().order_by('dia_semana', 'horario_aula')

    @staticmethod
    def resolve_local(obj):
        if obj.diario.local_aula:
            return {'id': obj.diario.local_aula.id, 'sala': str(obj.diario.local_aula)}
        return None

    @staticmethod
    def resolve_laboratorio(obj):
        if obj.diario.local_laboratorio:
            return {'id': obj.diario.local_laboratorio.id, 'sala': str(obj.diario.local_laboratorio)}
        return None

    @staticmethod
    def resolve_ambiente_virtual(obj):
        return obj.diario.url_ambiente_virtual or ''


class AvaliacaoSchema(Schema):
    tipo: str
    sigla: str
    forma_calculo: str
    data: str
    nota: str | None


class EtapaDisciplinaSchema(Schema):
    numero_etapa: int
    avaliacoes: list[AvaliacaoSchema] | None


class MensagemStatusEnum(enum.Enum):
    nao_lidas = 'nao-lidas'
    lidas = 'lidas'
    todas = 'todas'
    lixeira = 'lixeira'


class MensagemSchema(Schema):
    id: int
    status: MensagemStatusEnum

    remetente: UserSchema
    destinatarios: list[UserSchema]
    assunto: str
    conteudo: str
    data_envio: str

    registro_leitura: bool
    registro_exclusao: bool


class MeuPeriodoSchema(Schema):
    ano_letivo: int
    periodo_letivo: int


class MeusDadosAluno(Schema):
    ingresso: str
    email_academico: str
    email_escolar: str
    cpf: str
    periodo_referencia: int
    ira: str
    curso: str
    matriz: str
    qtd_periodos: int
    situacao: str
    data_migracao: str
    impressao_digital: bool
    emitiu_diploma: bool
    educasenso: str | None = None


class CargaHorariaSchema(Schema):
    ch_esperada: int = Field(default=0)
    ch_cumprida: int = Field(default=0)
    ch_pendente: int = Field(default=0)


class RequisitosConclusaoSchema(Schema):
    percentual_cumprida: int | float | Decimal = Field(default=0)
    regulares_obrigatorios: CargaHorariaSchema = Field(default=CargaHorariaSchema())
    regulares_optativos: CargaHorariaSchema = Field(default=CargaHorariaSchema())
    eletivos: CargaHorariaSchema = Field(default=CargaHorariaSchema())
    atividades_pratica_profissional: CargaHorariaSchema = Field(default=CargaHorariaSchema())
    seminarios: CargaHorariaSchema = Field(default=CargaHorariaSchema())
    pratica_profissional: CargaHorariaSchema = Field(default=CargaHorariaSchema())
    pratica_profissional_estagio: CargaHorariaSchema = Field(default=CargaHorariaSchema())
    extensao_componentes: CargaHorariaSchema = Field(default=CargaHorariaSchema())
    extensao_outras_atividades: CargaHorariaSchema = Field(default=CargaHorariaSchema())
    extensao_outros_componentes: CargaHorariaSchema = Field(default=CargaHorariaSchema())
    atividades_aprofundamento: CargaHorariaSchema = Field(default=CargaHorariaSchema())
    atividades_complementares: CargaHorariaSchema = Field(default=CargaHorariaSchema())
    tcc: CargaHorariaSchema = Field(default=CargaHorariaSchema())
    pratica_componente: CargaHorariaSchema = Field(default=CargaHorariaSchema())
    visita_tecnica: CargaHorariaSchema = Field(default=CargaHorariaSchema())
    totais: CargaHorariaSchema = Field(default=CargaHorariaSchema())


class MatriculaDiarioSchema(Schema):
    id: int = Field(None, alias='diario.id')
    ano_letivo: str = Field(None, alias='diario.ano_letivo.ano', coerce_numbers_to_str=True)
    periodo_letivo: str = Field(None, alias='diario.periodo_letivo', coerce_numbers_to_str=True)
    componente_curricular: str = None
    professores: list[dict] = None
    locais_de_aula: list[str] = None
    data_inicio: str = None
    data_fim: str = None
    participantes: list[dict] = None
    aulas: list[dict] = None
    materiais_de_aula: list[dict] = None

    @staticmethod
    def resolve_componente_curricular(obj):
        return str(obj.diario.componente_curricular.componente)

    @staticmethod
    def resolve_professores(obj):
        professores = []
        for professordiario in obj.diario.professordiario_set.all():
            professor = {
                'foto': professordiario.professor.get_foto_75x100_url_publica(),
                'nome': professordiario.professor.get_nome(),
                'matricula': professordiario.professor.get_matricula(),
                'email': professordiario.professor.vinculo.email_notificacao,
            }
            professores.append(professor)
        return professores

    @staticmethod
    def resolve_locais_de_aula(obj):
        locais = []
        if obj.diario.local_aula:
            locais.append(str(obj.diario.local_aula))
        if obj.diario.local_laboratorio:
            locais.append(str(obj.diario.local_laboratorio))
        return locais

    @staticmethod
    def resolve_data_inicio(obj):
        return str(obj.diario.calendario_academico.data_inicio)

    @staticmethod
    def resolve_data_fim(obj):
        return str(obj.diario.calendario_academico.data_fim)

    @staticmethod
    def resolve_participantes(obj):
        participantes = []
        for matricula_diario in obj.diario.get_matriculas_diario():
            participante = {
                'foto': matricula_diario.matricula_periodo.aluno.get_foto_75x100_url_publica(),
                'nome': matricula_diario.matricula_periodo.aluno.get_nome(),
                'matricula': matricula_diario.matricula_periodo.aluno.matricula,
                'email': matricula_diario.matricula_periodo.aluno.email_academico,
            }
            participantes.append(participante)
        return participantes

    @staticmethod
    def resolve_aulas(obj):
        aulas = []
        obj.set_faltas(obj.diario.get_aulas())

        for falta in obj.faltas:
            aula = {
                'data': falta.aula.data,
                'etapa': falta.aula.etapa,
                'quantidade': falta.aula.quantidade,
                'faltas': falta.quantidade,
                'professor': falta.aula.professor_diario.professor.vinculo.pessoa.nome,
                'conteudo': falta.aula.conteudo,
            }
            aulas.append(aula)
        return aulas

    @staticmethod
    def resolve_materiais_de_aula(obj):
        materiais = []
        for material_diario in MaterialDiario.objects.filter(professor_diario__diario=obj.diario).order_by('-data_vinculacao'):
            material = {
                'url': material_diario.material_aula.get_absolute_url(),
                'descricao': material_diario.material_aula.descricao,
                'data_vinculacao': material_diario.data_vinculacao,
            }
            materiais.append(material)
        return materiais


class MatriculaPeriodoSchema(Schema):
    id: str = Field(None, alias='diario.id', coerce_numbers_to_str=True)
    sigla: str = Field(None, alias='diario.componente_curricular.componente.sigla')
    descricao: str = Field(None, alias='diario.componente_curricular.componente.descricao_historico')
    observacao: str | None = None
    locais_de_aula: list[str] = None
    horarios_de_aula: str = None

    @staticmethod
    def resolve_observacao(obj):
        if obj.diario.is_semestral_segundo_semestre():
            return 'Esta disciplina será ofertada apenas no segundo semestre.'
        elif obj.is_cancelado():
            return obj.get_situacao_diario_boletim().get('rotulo')

    @staticmethod
    def resolve_locais_de_aula(obj):
        locais = []
        if obj.diario.local_aula:
            locais.append(str(obj.diario.local_aula))
        if obj.diario.local_laboratorio:
            locais.append(str(obj.diario.local_laboratorio))
        return locais

    @staticmethod
    def resolve_horarios_de_aula(obj):
        return obj.diario.get_horario_aulas()


ItemConfiguracaoAvaliacaoSchemaBase = create_schema(ItemConfiguracaoAvaliacao, exclude=['configuracao_avaliacao'])


class ItemConfiguracaoAvaliacaoSchema(ItemConfiguracaoAvaliacaoSchemaBase):
    diario: str = None
    tipo: str = None
    etapa: str | None = Field(None, alias='configuracao_avaliacao.etapa', coerce_numbers_to_str=True)

    @staticmethod
    def resolve_diario(obj):
        return str(obj.configuracao_avaliacao.diario)

    @staticmethod
    def resolve_tipo(obj):
        return obj.get_tipo_display()


class NotaBoletimSchema(Schema):
    nota: int | None = None
    faltas: int | None = None


class BoletimSchema(Schema):
    codigo_diario: str = Field(None, alias='diario.id', coerce_numbers_to_str=True)
    disciplina: str = None
    segundo_semestre: bool = False
    carga_horaria: int = None
    carga_horaria_cumprida: int = None
    numero_faltas: int = None
    percentual_carga_horaria_frequentada: float = None
    situacao: str = None
    quantidade_avaliacoes: int = Field(None, alias='diario.componente_curricular.qtd_avaliacoes')
    nota_etapa_1: NotaBoletimSchema = None
    nota_etapa_2: NotaBoletimSchema = None
    nota_etapa_3: NotaBoletimSchema = None
    nota_etapa_4: NotaBoletimSchema = None
    media_disciplina: int | None = None
    nota_avaliacao_final: NotaBoletimSchema = None
    media_final_disciplina: str | None = None

    @staticmethod
    def resolve_disciplina(obj):
        return f'{obj.diario.componente_curricular.componente.sigla} - {obj.diario.componente_curricular.componente.descricao_historico}'

    @staticmethod
    def resolve_segundo_semestre(obj):
        return obj.diario.is_semestral_segundo_semestre()

    @staticmethod
    def resolve_carga_horaria(obj):
        return obj.diario.get_carga_horaria()

    @staticmethod
    def resolve_carga_horaria_cumprida(obj):
        return obj.diario.get_carga_horaria_cumprida()

    @staticmethod
    def resolve_numero_faltas(obj):
        return obj.get_numero_faltas()

    @staticmethod
    def resolve_percentual_carga_horaria_frequentada(obj):
        return obj.get_percentual_carga_horaria_frequentada()

    @staticmethod
    def resolve_situacao(obj):
        return obj.get_situacao_diario_boletim().get('rotulo')

    @staticmethod
    def resolve_nota_etapa_1(obj):
        dict = {'nota': obj.get_nota_boletim(1), 'faltas': obj.get_numero_faltas_primeira_etapa()}
        return dict

    @staticmethod
    def resolve_nota_etapa_2(obj):
        dict = {'nota': obj.get_nota_boletim(2), 'faltas': obj.get_numero_faltas_segunda_etapa()}
        return dict

    @staticmethod
    def resolve_nota_etapa_3(obj):
        dict = {'nota': obj.get_nota_boletim(3), 'faltas': obj.get_numero_faltas_terceira_etapa()}
        return dict

    @staticmethod
    def resolve_nota_etapa_4(obj):
        dict = {'nota': obj.get_nota_boletim(4), 'faltas': obj.get_numero_faltas_quarta_etapa()}
        return dict

    @staticmethod
    def resolve_media_disciplina(obj):
        return obj.get_media_disciplina_boletim()

    @staticmethod
    def resolve_nota_avaliacao_final(obj):
        dict = {'nota': obj.get_nota_boletim(5), 'faltas': 0}
        return dict

    @staticmethod
    def resolve_media_final_disciplina(obj):
        if obj.get_media_final_disciplina_boletim():
            return str(obj.get_media_final_disciplina_boletim())
        else:
            return None


class ProfessorDiarioSchema(Schema):
    foto: str
    nome: str
    nome_usual: str | None = None
    matricula: str
    email: str


class ParticipanteDiarioSchema(Schema):
    foto: str
    nome: str
    nome_social: str | None = None
    matricula: str
    email: str


class AulaDiarioSchema(Schema):
    data: datetime.date
    etapa: int
    quantidade: int
    professor: str
    conteudo: str


class MaterialDeAulaDiarioSchema(Schema):
    url: str
    descricao: str
    data_vinculacao: datetime.date


class MeuDiarioSchema(Schema):
    id: int = None
    ano_letivo: int = Field(None, alias='ano_letivo.ano')
    periodo_letivo: int = None
    componente_curricular: str = None
    professores: list[ProfessorDiarioSchema] = None
    locais_de_aula: list[str] = None
    data_inicio: datetime.date = Field(None, alias='calendario_academico.data_inicio')
    data_fim: datetime.date = Field(None, alias='calendario_academico.data_fim')
    participantes: list[ParticipanteDiarioSchema] | None = None
    aulas: list[AulaDiarioSchema] = None
    materiais_de_aula: list[MaterialDeAulaDiarioSchema] = None
    horarios: list[HorarioSchema] = None

    @staticmethod
    def resolve_componente_curricular(obj):
        return str(obj.componente_curricular.componente)

    @staticmethod
    def resolve_professores(obj):
        professores = []
        for professordiario in obj.professordiario_set.all():
            professor = {
                'foto': professordiario.professor.get_foto_75x100_url_publica(),
                'nome': professordiario.professor.get_nome(),
                'nome_usual': professordiario.professor.get_nome_usual(),
                'matricula': professordiario.professor.get_matricula(),
                'email': professordiario.professor.vinculo.email_notificacao,
            }
            professores.append(professor)
        return professores

    @staticmethod
    def resolve_locais_de_aula(obj):
        locais = []
        if obj.local_aula:
            locais.append(str(obj.local_aula))
        if obj.local_laboratorio:
            locais.append(str(obj.local_laboratorio))
        return locais

    @staticmethod
    def resolve_participantes(obj):
        participantes = []
        for matricula_diario in obj.get_matriculas_diario():
            participante = {
                'foto': matricula_diario.matricula_periodo.aluno.get_foto_75x100_url_publica(),
                'nome': matricula_diario.matricula_periodo.aluno.get_nome(),
                'nome_social': matricula_diario.matricula_periodo.aluno.pessoa_fisica.nome_social,
                'matricula': matricula_diario.matricula_periodo.aluno.matricula,
                'email': matricula_diario.matricula_periodo.aluno.email_academico,
            }
            participantes.append(participante)
        return participantes

    @staticmethod
    def resolve_aulas(obj):
        aulas = []
        for aula in obj.get_aulas():
            aula = {
                'data': aula.data,
                'etapa': aula.etapa,
                'quantidade': aula.quantidade,
                'professor': aula.professor_diario.professor.vinculo.pessoa.nome,
                'conteudo': aula.conteudo,
            }
            aulas.append(aula)
        return aulas

    @staticmethod
    def resolve_materiais_de_aula(obj):
        materiais = []
        for material_diario in MaterialDiario.objects.filter(professor_diario__diario=obj).order_by('-data_vinculacao'):
            material = {
                'url': material_diario.material_aula.get_absolute_url(),
                'descricao': material_diario.material_aula.descricao,
                'data_vinculacao': material_diario.data_vinculacao,
            }
            materiais.append(material)
        return materiais

    @staticmethod
    def resolve_horarios(obj):
        horarios = []
        for horario_diario in obj.horarioauladiario_set.all():
            horario = {
                'dia': horario_diario.get_dia_semana_display(),
                'horario': str(horario_diario.horario_aula),
            }
            horarios.append(horario)
        return horarios


class CursoSiabiSchema(Schema):
    id: int
    descricao: str
    modalidade: str


class DiretoriaSiabiSchema(Schema):
    id: int
    descricao: str


class PoloSiabiSchema(Schema):
    id: int
    descricao: str


class CampusSiabiSchema(Schema):
    id: int
    descricao: str


class AlunoSiabiSchema(Schema):
    id: int
    matricula: str
    nome: str
    logradouro: str
    numero: str
    complemento: str
    cep: str
    bairro: str
    cidade: str
    telefone_principal: str
    telefone_secundario: str
    email_academico: str
    email_pessoal: str
    curso: CursoSiabiSchema | str
    diretoria: PoloSiabiSchema | str
    polo: PoloSiabiSchema | str
    campus: CampusSiabiSchema | str
    foto: str
    sexo: str | None = None
    rg: str | None = None
    data_nascimento: str | None = None
    situacao: str
    lattes: str


class DadosSiabiSchema(Schema):
    aluno: AlunoSiabiSchema


class SiabiInput(Schema):
    matricula: str | None = None
    ano_conclusao: str | None = None
    codigo_curso: str | None = None


class DadosCursoSiabiSchema(Schema):
    id: int
    codigo: str
    descricao: str
    sigla_campus: str | None = Field(None, alias='diretoria.setor.uo.sigla')
    modalidade: str | None = Field(None, alias='modalidade.descricao')


class ComponenteCurricularSiabiSchema(Schema):
    id: int
    descricao: str | None = Field(None, alias='componente.descricao')
    descricao_historico: str | None = Field(None, alias='componente.descricao_historico')
    sigla: str | None = Field(None, alias='componente.sigla')
    periodo: int | None = None
    tipo: int | None = None
    optativo: bool
    qtd_avaliacoes: int | None = None


class DadosMatrizSiabiSchema(Schema):
    id: int
    descricao: str
    natureza_participacao: str | None = Field(None, alias='natureza_participacao.descricao')
    componentes_curriculares: list[ComponenteCurricularSiabiSchema] | None = None

    @staticmethod
    def resolve_componentes_curriculares(obj):
        return obj.componentecurricular_set.all()


class DadosMatrizCursoSiabiSchema(Schema):
    matriz: int = Field(None, alias='matriz_id')
    curso: int = Field(None, alias='curso_campus_id')


class CursosEADInput(Schema):
    id_campus: int
    ano_letivo: int
    periodo_letivo: int


class CursosEADSchema(Schema):
    id: int
    codigo: str
    nome: str = Field(None, alias='descricao_historico')
    descricao: str


class TurmasEADInput(Schema):
    id_curso: int
    ano_letivo: int
    periodo_letivo: int


class TurmasEADSchema(Schema):
    id: int
    codigo: str


class DiariosEADInput(Schema):
    id_turma: int


class DiariosEADSchema(Schema):
    id: int
    situacao: str = Field('', alias='get_situacao_display')
    descricao: str = Field('', alias='componente_curricular.componente.descricao')
    descricao_historico: str = Field('', alias='componente_curricular.componente.descricao_historico')
    sigla: str = Field('', alias='componente_curricular.componente.sigla')


class ProfessoresEADInput(Schema):
    id_diario: int


class ProfessoresEADSchema(Schema):
    id: int = Field(None, alias='professor.id')
    nome: str
    email: str = Field('', alias='professor.vinculo.relacionamento.email_institucional')
    email_secundario: str = Field('', alias='professor.vinculo.email_notificacao')
    tipo: str = Field('', alias='tipo.descricao')
    login: str = Field('', alias='professor.vinculo.user.username')
    status: str

    @staticmethod
    def resolve_nome(obj):
        return normalizar_nome_proprio(obj.professor.vinculo.pessoa.nome) or ''

    @staticmethod
    def resolve_status(obj):
        return obj.professor.vinculo.user.is_active and 'ativo' or 'inativo'


class AlunosEADInput(Schema):
    id_diario: int


class AlunoPoloEADSchema(Schema):
    id: int | None = None
    descricao: str | None = None


class AlunosEADSchema(Schema):
    id: int = Field(None, alias='matricula_periodo.aluno.id')
    matricula: str = Field(None, alias='matricula_periodo.aluno.matricula')
    nome: str
    email: str = Field(None, alias='matricula_periodo.aluno.email_academico')
    email_secundario: str = Field(None, alias='matricula_periodo.aluno.email_pessoal')
    situacao: str = Field(None, alias='matricula_periodo.aluno.situacao.descricao')
    polo: AlunoPoloEADSchema = Field({}, alias='matricula_periodo.aluno.polo')

    @staticmethod
    def resolve_nome(obj):
        return normalizar_nome_proprio(obj.matricula_periodo.aluno.pessoa_fisica.nome) or ''


class PolosEADSchema(Schema):
    id: int
    descricao: str


class CampusEADSchema(Schema):
    id: int
    descricao: str = Field(None, alias='nome')
    sigla: str


class ComponenteCurricularEADInput(Schema):
    id_curso: int


class ComponenteCurricularEADSchema(Schema):
    id: int
    descricao: str = Field(None, alias='componente.descricao')
    descricao_historico: str = Field(None, alias='componente.descricao_historico')
    sigla: str = Field(None, alias='componente.sigla')
    periodo: int | None = Field(None, alias='periodo_letivo')
    tipo: int
    optativo: bool
    qtd_avaliacoes: int


class DiarioAlunoEADSchema(Schema):
    id: int = Field(None, alias='diario_id')
    turma: str = Field(None, alias='diario.turma.codigo')
    componente: str = Field(None, alias='diario.componente_curricular.componente.sigla')
    cancelado: bool

    @staticmethod
    def resolve_cancelado(obj):
        return obj.situacao in (MatriculaDiario.SITUACAO_CANCELADO, MatriculaDiario.SITUACAO_TRANSFERIDO)


class DiariosAlunoEADSchema(Schema):
    matricula: str
    diarios: list[DiarioAlunoEADSchema]


class AlunoMeuDiarioEADSchema(Schema):
    matricula: str = Field(None, alias='matricula_periodo.aluno.matricula')
    nome: str = Field(None, alias='matricula_periodo.aluno.pessoa_fisica.nome_registro')
    nome_social: str = Field(None, alias='matricula_periodo.aluno.pessoa_fisica.nome_social')
    email: str = Field(None, alias='matricula_periodo.aluno.email_academico')
    identificador: int = Field(None, alias='id')


class MeuDiarioEADSChema(Schema):
    nome: str
    ano: int = Field(None, alias='ano_letivo.ano')
    periodo: int = Field(None, alias='periodo_letivo')
    identificador: int = Field(None, alias='id')
    alunos: list[AlunoMeuDiarioEADSchema] | None = None

    @staticmethod
    def resolve_nome(obj):
        return obj.get_descricao_resumida()

    @staticmethod
    def resolve_alunos(obj):
        if hasattr(obj, 'exibir_alunos'):
            return obj.matriculadiario_set.select_related('matricula_periodo__aluno__pessoa_fisica').all()
        return None


class DadosAlunoMatriculadoSchema(Schema):
    nome: str
    matricula: str
    curso: str
    campus: str
    periodo_atual: str
    nascimento: str
    cpf: str
    foto_base64: str
    mime_type: str


def _get_campus_professor(obj: Professor) -> UnidadeOrganizacional | None:
    if hasattr(obj, 'get_uo') and obj.get_uo():
        return obj.get_uo()
    if obj.vinculo and obj.vinculo.setor and obj.vinculo.setor.uo:
        return obj.vinculo.setor.uo
    return None


def _serializar_material_portal(material: MaterialAula) -> dict:
    return {
        'id': material.id,
        'descricao': material.descricao or 'Material sem descrição',
        'url': material.get_url_portal() or '',
        'data_cadastro_formatada': material.data_cadastro.strftime('%d/%m/%Y %H:%M:%S') if material.data_cadastro else '',
    }


def _agrupar_materiais_por_disciplina(professor: Professor) -> list[dict]:
    vinculos = (
        MaterialDiario.objects.filter(
            material_aula__professor=professor,
            material_aula__exibir_no_portal=True,
        )
        .select_related('material_aula', 'professor_diario__diario__componente_curricular__componente')
        .order_by('professor_diario__diario__componente_curricular__componente__sigla', '-material_aula__data_cadastro')
    )

    grupos: dict[int | None, dict] = {}
    ids_categorizados = set()

    for vinculo in vinculos:
        material = vinculo.material_aula
        ids_categorizados.add(material.id)
        componente = vinculo.professor_diario.diario.componente_curricular.componente
        grupo = grupos.setdefault(componente.id, {'disciplina': componente.descricao, 'sigla': componente.sigla, 'materiais': {}})
        grupo['materiais'][material.id] = _serializar_material_portal(material)

    materiais_sem_disciplina = professor.materialaula_set.filter(exibir_no_portal=True).exclude(id__in=ids_categorizados)
    if materiais_sem_disciplina.exists():
        grupos[None] = {
            'disciplina': None,
            'sigla': None,
            'materiais': {material.id: _serializar_material_portal(material) for material in materiais_sem_disciplina},
        }

    return [{'disciplina': g['disciplina'], 'sigla': g['sigla'], 'materiais': list(g['materiais'].values())} for g in grupos.values()]


class DadosProfessorPortalInstitucionalSchema(Schema):
    content_type: str = 'ensino.professor'
    id: int = Field(alias='id')
    nome: str | None = None
    nome_usual: str | None = None
    slug: str | None = None
    data_publicacao_formatada: str | None = None
    foto_url: str | None = None
    foto_url_publica: str | None = None
    email_institucional: str | None = None
    modo_exibicao: str | None = None
    lattes: dict | None = None
    disciplina: str | None = None
    campus_id: int | None = None
    campus_sigla: str | None = None
    campus_nome: str | None = None
    materiais_aula: list[dict] = []
    instagram_url: str | None = Field(None, alias='config_dados_docentes.instagram_url')
    facebook_url: str | None = Field(None, alias='config_dados_docentes.facebook_url')
    youtube_url: str | None = Field(None, alias='config_dados_docentes.youtube_url')
    linkedin_url: str | None = Field(None, alias='config_dados_docentes.linkedin_url')
    spotify_url: str | None = Field(None, alias='config_dados_docentes.spotify_url')

    @staticmethod
    def resolve_nome(obj):
        return obj.get_nome() or ''

    @staticmethod
    def resolve_nome_usual(obj):
        return obj.get_nome_usual() or ''

    @staticmethod
    def resolve_slug(obj):
        return obj.get_slug_from_email()

    @staticmethod
    def resolve_data_publicacao_formatada(obj):
        if obj.config_dados_docentes and obj.config_dados_docentes.datahora_publicacao:
            return obj.config_dados_docentes.datahora_publicacao.strftime('%d/%m/%Y %H:%M:%S')
        return None

    @staticmethod
    def resolve_foto_url(obj):
        if obj.config_dados_docentes and obj.config_dados_docentes.is_exibicao_completa and obj.config_dados_docentes.exibir_foto:
            return obj.get_foto_75x100_url()
        return None

    @staticmethod
    def resolve_foto_url_publica(obj):
        if obj.config_dados_docentes and obj.config_dados_docentes.is_exibicao_completa and obj.config_dados_docentes.exibir_foto:
            return obj.get_foto_75x100_url_publica()
        return None

    @staticmethod
    def resolve_email_institucional(obj):
        if obj.config_dados_docentes and obj.config_dados_docentes.is_exibicao_completa and obj.config_dados_docentes.exibir_email:
            return obj.email_institucional_docente
        return None

    @staticmethod
    def resolve_modo_exibicao(obj: Professor) -> str | None:
        config = getattr(obj, 'config_dados_docentes', None)
        return config.modo_exibicao if config else None

    @staticmethod
    def resolve_lattes(obj):
        if obj.config_dados_docentes and obj.config_dados_docentes.is_exibicao_completa and obj.config_dados_docentes.exibir_lattes:
            # Tentar acessar currículo lattes através do vínculo
            if (
                obj.vinculo
                and hasattr(obj.vinculo, 'relacionamento')
                and obj.vinculo.relacionamento
                and hasattr(obj.vinculo, 'vinculo_curriculo_lattes')
            ):
                curriculo = obj.vinculo.vinculo_curriculo_lattes
                if curriculo:
                    dados = extrair_dados_curriculo_lattes(curriculo)
                    return dados
        return None

    @staticmethod
    def resolve_disciplina(obj):
        if hasattr(obj, 'disciplina') and obj.disciplina:
            return str(obj.disciplina)
        return None

    @staticmethod
    def resolve_campus_id(obj: Professor) -> int | None:
        campus = _get_campus_professor(obj)
        return campus.pk if campus else None

    @staticmethod
    def resolve_campus_sigla(obj: Professor) -> str | None:
        campus = _get_campus_professor(obj)
        return campus.sigla if campus else None

    @staticmethod
    def resolve_campus_nome(obj: Professor) -> str | None:
        campus = _get_campus_professor(obj)
        return campus.nome if campus else None

    @staticmethod
    def resolve_materiais_aula(obj):
        if obj.config_dados_docentes and obj.config_dados_docentes.is_exibicao_completa and hasattr(obj, 'materialaula_set'):
            return _agrupar_materiais_por_disciplina(obj)
        return []
