# pyright: reportPrivateImportUsage=false, reportIncompatibleVariableOverride=false
"""Factories factory_boy de modelos do app ``edu``.

Reutilizáveis por testes de qualquer app (o dono do modelo provê a factory) — o ``saude``,
por exemplo, precisa de um aluno matriculado para abrir um atendimento.

``SituacaoMatricula`` é tabela-tipo: os ids são constantes do próprio model, e era o
``_setup_base_data`` do ``suap_data`` que os semeava. A factory faz o mesmo por linha, sob
demanda, com ``django_get_or_create`` no id.
"""

from __future__ import annotations

import datetime

import factory
from django.db import connection
from factory.django import DjangoModelFactory

from comum.tests.factories import AnoFactory, _sincronizar_sequencia
from djtools.utils import get_datetime_now
from rh.tests.factories import ArquivoUnicoFactory, PessoaFisicaFactory, ServidorFactory, SetorFactory

from edu.models import (
    Aluno,
    AlunoArquivo,
    AproveitamentoEstudo,
    AtividadeCurricularExtensao,
    AuditoriaEnsino,
    CalendarioAcademico,
    Cidade,
    Componente,
    ComponenteCurricular,
    ConfiguracaoAvaliacao,
    CursoCampus,
    Diario,
    Diretoria,
    EstruturaCurso,
    FormaIngresso,
    HorarioCampus,
    ItemConfiguracaoAvaliacao,
    MatriculaDiario,
    MatriculaPeriodo,
    Matriz,
    Minicurso,
    Modalidade,
    MonitorMinicurso,
    NivelEnsino,
    Nucleo,
    Pais,
    ProcedimentoMatricula,
    Professor,
    ProfessorDiario,
    RegistroAuditoriaEnsino,
    RegistroHistorico,
    Requerimento,
    RequerimentoAproveitamentoEstudo,
    SituacaoMatricula,
    SituacaoMatriculaPeriodo,
    SolicitacaoAproveitamentoEstudo,
    SolicitacaoAproveitamentoEstudoExterno,
    SolicitacaoAproveitamentoEstudoInterno,
    TipoAlunoArquivo,
    TipoComponente,
    TipoProfessorDiario,
    Turma,
    TurmaMinicurso,
    Turno,
    VinculacaoAtividadeExtensao,
)


class SituacaoMatriculaFactory(DjangoModelFactory):
    class Meta:
        model = SituacaoMatricula
        django_get_or_create = ('id',)

    id = SituacaoMatricula.MATRICULADO
    descricao = 'Matriculado'
    ativo = True


class AlunoFactory(DjangoModelFactory):
    """Aluno matriculado, com matrícula e pessoa física próprias."""

    class Meta:
        model = Aluno

    matricula = factory.Sequence(lambda n: f'2016014040{n:04d}')
    pessoa_fisica = factory.SubFactory(PessoaFisicaFactory)
    ano_letivo = factory.SubFactory(AnoFactory, ano=2016)
    periodo_letivo = 1
    situacao = factory.SubFactory(SituacaoMatriculaFactory)
    ano_let_prev_conclusao = factory.LazyFunction(lambda: datetime.datetime.now().year)


class DiretoriaFactory(DjangoModelFactory):
    """Diretoria de um setor com campus (``SetorFactory`` já cria a ``uo``)."""

    class Meta:
        model = Diretoria

    setor = factory.SubFactory(SetorFactory)


class CursoCampusFactory(DjangoModelFactory):
    """Curso de uma diretoria; só os campos obrigatórios (sem modalidade, matriz nem estrutura)."""

    class Meta:
        model = CursoCampus

    codigo = factory.Sequence(lambda n: f'CC{n:05d}')
    descricao = factory.Sequence(lambda n: f'CURSO TECNICO {n}')
    descricao_historico = factory.SelfAttribute('descricao')
    diretoria = factory.SubFactory(DiretoriaFactory)


class NivelEnsinoFactory(DjangoModelFactory):
    """Tabela-tipo: os ids são constantes do model, como em ``SituacaoMatricula``."""

    class Meta:
        model = NivelEnsino
        django_get_or_create = ('id',)

    id = NivelEnsino.POS_GRADUACAO
    descricao = 'Pós-Graduação'


class ModalidadeFactory(DjangoModelFactory):
    """Tabela-tipo da modalidade do curso; o ``id`` é a constante (MESTRADO, FIC...)."""

    class Meta:
        model = Modalidade
        django_get_or_create = ('id',)

    id = Modalidade.MESTRADO
    descricao = 'Mestrado'
    nivel_ensino = factory.SubFactory(NivelEnsinoFactory)


class FormaIngressoFactory(DjangoModelFactory):
    """Tabela-tipo de forma de ingresso do aluno."""

    class Meta:
        model = FormaIngresso
        django_get_or_create = ('descricao',)

    descricao = 'Processo Seletivo'


class SituacaoMatriculaPeriodoFactory(DjangoModelFactory):
    """Tabela-tipo do período; id constante, como a `SituacaoMatricula`."""

    class Meta:
        model = SituacaoMatriculaPeriodo
        django_get_or_create = ('id',)

    id = SituacaoMatriculaPeriodo.MATRICULADO
    descricao = 'Matriculado'


class MatriculaPeriodoFactory(DjangoModelFactory):
    """Matrícula do aluno num período (por padrão ``Matriculado`` em 2016.1, o ano letivo do ``AlunoFactory``)."""

    class Meta:
        model = MatriculaPeriodo

    aluno = factory.SubFactory(AlunoFactory)
    ano_letivo = factory.SubFactory(AnoFactory, ano=2016)
    periodo_letivo = 1
    situacao = factory.SubFactory(SituacaoMatriculaPeriodoFactory)


def _sincronizar_sequencia(model: type) -> None:
    if connection.vendor == 'postgresql':
        tabela = model._meta.db_table
        coluna = model._meta.pk.column
        maior = model.objects.order_by('-pk').values_list('pk', flat=True).first() or 1
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT setval(pg_get_serial_sequence('{tabela}', '{coluna}'), %s, true)", [maior])


class TurnoFactory(DjangoModelFactory):
    class Meta:
        model = Turno
        django_get_or_create = ('id',)

    id = Turno.MATUTINO
    descricao = 'Matutino'


class ConfiguracaoAvaliacaoFactory(DjangoModelFactory):
    """Configuração de avaliação com um item de prova — o mínimo que os diários pedem."""

    class Meta:
        model = ConfiguracaoAvaliacao
        django_get_or_create = ('id',)

    id = 1
    forma_calculo = ConfiguracaoAvaliacao.FORMA_CALCULO_MEDIA_ARITMETICA

    @factory.post_generation
    def item(obj, create, extracted, **kwargs):
        if not create:
            return
        ItemConfiguracaoAvaliacao.objects.get_or_create(
            configuracao_avaliacao=obj,
            sigla='A1',
            defaults={'tipo': ItemConfiguracaoAvaliacao.TIPO_PROVA, 'descricao': '', 'nota_maxima': 100},
        )
        _sincronizar_sequencia(ConfiguracaoAvaliacao)
        _sincronizar_sequencia(ItemConfiguracaoAvaliacao)


class TipoAlunoArquivoFactory(DjangoModelFactory):
    class Meta:
        model = TipoAlunoArquivo
        django_get_or_create = ('nome',)

    nome = TipoAlunoArquivo.IDENTIDADE


class AlunoArquivoFactory(DjangoModelFactory):
    """Documento da pasta documental do aluno, com um PDF mínimo como conteúdo."""

    class Meta:
        model = AlunoArquivo

    arquivo_unico = factory.SubFactory(ArquivoUnicoFactory)
    aluno = factory.SubFactory(AlunoFactory)
    tipo = factory.SubFactory(TipoAlunoArquivoFactory)
    nome_original = 'documento.pdf'
    nome_exibicao = 'documento.pdf'
    descricao = 'Documento'
    data_hora_upload = factory.LazyFunction(get_datetime_now)
    tipo_origem_cadastro = AlunoArquivo.TIPO_ORIGEM_CADASTRO_MANUAL


class AuditoriaEnsinoFactory(DjangoModelFactory):
    class Meta:
        model = AuditoriaEnsino

    tipo_auditoria = AuditoriaEnsino.TIPO_ALUNO_SEM_SISTEC
    campus = factory.LazyFunction(lambda: SetorFactory().uo)


class RegistroAuditoriaEnsinoFactory(DjangoModelFactory):
    """Linha da auditoria: ``registro`` são os itens separados por ``;``, começando pela matrícula."""

    class Meta:
        model = RegistroAuditoriaEnsino

    auditoria_ensino = factory.SubFactory(AuditoriaEnsinoFactory)
    registro = factory.Sequence(lambda n: f'2026{n:06d};000.000.000-00')


class PaisFactory(DjangoModelFactory):
    class Meta:
        model = Pais
        django_get_or_create = ('sigla', 'nome')

    sigla = 'ARG'
    nome = 'Argentina'


class CidadeFactory(DjangoModelFactory):
    class Meta:
        model = Cidade

    nome = factory.Sequence(lambda n: f'Cidade {n}')


class MinicursoFactory(CursoCampusFactory):
    class Meta:
        model = Minicurso

    codigo = factory.Sequence(lambda n: f'MC{n:05d}')
    descricao = factory.Sequence(lambda n: f'MINICURSO {n}')
    # Minicurso.save() força modalidade FIC-, que só a migration cria: sem o schema migrado, a FK quebra no commit.
    modalidade = factory.SubFactory(
        ModalidadeFactory,
        id=Modalidade.FIC_MENOS,
        descricao='FIC-',
        nivel_ensino=factory.SubFactory(NivelEnsinoFactory, id=NivelEnsino.FUNDAMENTAL, descricao='Fundamental'),
    )
    ch_total = 20
    tipo_hora_aula = 60


class TurmaMinicursoFactory(DjangoModelFactory):
    class Meta:
        model = TurmaMinicurso

    descricao = factory.Sequence(lambda n: f'Turma Minicurso {n}')
    minicurso = factory.SubFactory(MinicursoFactory)
    ano_letivo = factory.SubFactory(AnoFactory, ano=2025)
    periodo_letivo = 1
    data_inicio = datetime.date(2025, 3, 1)
    data_fim = datetime.date(2025, 3, 31)


class MonitorMinicursoFactory(DjangoModelFactory):
    class Meta:
        model = MonitorMinicurso

    aluno = factory.SubFactory(AlunoFactory)
    turma_minicurso = factory.SubFactory(TurmaMinicursoFactory)
    carga_horaria = 20


class ProcedimentoMatriculaFactory(DjangoModelFactory):
    class Meta:
        model = ProcedimentoMatricula

    tipo = ProcedimentoMatricula.CANCELAMENTO_VOLUNTARIO
    situacao_matricula_anterior = factory.SubFactory(SituacaoMatriculaFactory)
    matricula_periodo = factory.SubFactory(MatriculaPeriodoFactory)
    motivo = 'Cancelamento solicitado pelo aluno'
    data = factory.LazyFunction(datetime.date.today)


class RequerimentoFactory(DjangoModelFactory):
    class Meta:
        model = Requerimento

    aluno = factory.SubFactory(AlunoFactory)
    tipo = Requerimento.TRANCAMENTO_MATRICULA
    data = factory.LazyFunction(datetime.date.today)
    situacao = Requerimento.SITUACAO_EM_ANDAMENTO
    deferido = None


class RequerimentoAproveitamentoEstudoFactory(RequerimentoFactory):
    class Meta:
        model = RequerimentoAproveitamentoEstudo

    tipo = Requerimento.APROVEITAMENTO_ESTUDO
    interno = True


class ProfessorFactory(DjangoModelFactory):
    class Meta:
        model = Professor

    vinculo = factory.LazyAttribute(lambda o: ServidorFactory().get_vinculo())


class EstruturaCursoFactory(DjangoModelFactory):
    class Meta:
        model = EstruturaCurso
        django_get_or_create = ('descricao',)

    descricao = 'Estrutura Padrão'
    tipo_avaliacao = EstruturaCurso.TIPO_AVALIACAO_CREDITO
    criterio_avaliacao = EstruturaCurso.CRITERIO_AVALIACAO_NOTA
    media_aprovacao_sem_prova_final = 60
    media_evitar_reprovacao_direta = 20
    media_aprovacao_avaliacao_final = 60


class MatrizFactory(DjangoModelFactory):
    class Meta:
        model = Matriz

    descricao = factory.Sequence(lambda n: f'Matriz Padrão Teste {n}')
    estrutura = factory.SubFactory(EstruturaCursoFactory)
    ano_criacao = factory.SubFactory(AnoFactory, ano=2025)
    data_inicio = datetime.date(2025, 1, 1)
    qtd_periodos_letivos = 2
    ch_componentes_obrigatorios = 100
    ch_componentes_optativos = 0
    ch_componentes_eletivos = 0
    ch_seminarios = 0
    ch_pratica_profissional = 0
    ch_atividades_complementares = 0
    ch_atividades_aprofundamento = 0
    ch_componentes_tcc = 0
    ch_pratica_como_componente = 0
    ch_visita_tecnica = 0


class TipoComponenteFactory(DjangoModelFactory):
    class Meta:
        model = TipoComponente
        django_get_or_create = ('descricao',)

    descricao = 'Disciplina'


class NucleoFactory(DjangoModelFactory):
    class Meta:
        model = Nucleo
        django_get_or_create = ('descricao',)

    descricao = 'Núcleo Comum'


class ComponenteFactory(DjangoModelFactory):
    class Meta:
        model = Componente

    descricao = 'Componente Teste'
    descricao_historico = 'Componente Teste'
    sigla = factory.Sequence(lambda n: f'TEST.{n:04d}')
    tipo = factory.SubFactory(TipoComponenteFactory)
    diretoria = factory.SubFactory(DiretoriaFactory)
    nivel_ensino = factory.SubFactory(NivelEnsinoFactory)
    ch_hora_relogio = 60
    ch_hora_aula = 60
    ch_qtd_creditos = 4


class ComponenteCurricularFactory(DjangoModelFactory):
    class Meta:
        model = ComponenteCurricular

    matriz = factory.SubFactory(MatrizFactory)
    componente = factory.SubFactory(ComponenteFactory)
    nucleo = factory.SubFactory(NucleoFactory)
    periodo_letivo = 1
    tipo = ComponenteCurricular.TIPO_REGULAR
    qtd_avaliacoes = 2
    ch_presencial = 60
    ch_pratica = 0


class SolicitacaoAproveitamentoEstudoFactory(DjangoModelFactory):
    class Meta:
        model = SolicitacaoAproveitamentoEstudo

    requerimento = factory.SubFactory(RequerimentoAproveitamentoEstudoFactory)
    componente_curricular = factory.SubFactory(ComponenteCurricularFactory)
    ementa = 'ementa_teste.pdf'
    situacao = SolicitacaoAproveitamentoEstudo.SITUACAO_EM_ANALISE
    avaliador = None
    parecer = None


class HorarioCampusFactory(DjangoModelFactory):
    class Meta:
        model = HorarioCampus

    descricao = factory.Sequence(lambda n: f'Horário Campus {n}')
    uo = factory.LazyFunction(lambda: SetorFactory().uo)


class CalendarioAcademicoFactory(DjangoModelFactory):
    class Meta:
        model = CalendarioAcademico

    descricao = factory.Sequence(lambda n: f'Calendário {n}')
    tipo = CalendarioAcademico.TIPO_SEMESTRAL
    ano_letivo = factory.SubFactory(AnoFactory, ano=2025)
    periodo_letivo = 1
    data_inicio = datetime.date(2025, 2, 1)
    data_fim = datetime.date(2025, 6, 30)
    data_fechamento_periodo = datetime.date(2025, 7, 5)
    qtd_etapas = CalendarioAcademico.QTD_ETAPA_2
    data_inicio_etapa_1 = datetime.date(2025, 2, 1)
    data_fim_etapa_1 = datetime.date(2025, 4, 15)


class TurmaFactory(DjangoModelFactory):
    class Meta:
        model = Turma

    codigo = factory.Sequence(lambda n: f'2025.1.T{n:04d}')
    descricao = factory.Sequence(lambda n: f'Turma {n}')
    ano_letivo = factory.SubFactory(AnoFactory, ano=2025)
    periodo_letivo = 1
    periodo_matriz = 1
    turno = factory.SubFactory(TurnoFactory)
    curso_campus = factory.SubFactory(CursoCampusFactory, modalidade=factory.SubFactory(ModalidadeFactory))
    matriz = factory.SubFactory(MatrizFactory)


class DiarioFactory(DjangoModelFactory):
    class Meta:
        model = Diario

    turma = factory.SubFactory(TurmaFactory)
    componente_curricular = factory.SubFactory(ComponenteCurricularFactory, qtd_avaliacoes=0)
    percentual_minimo_ch = 75
    ano_letivo = factory.SelfAttribute('turma.ano_letivo')
    periodo_letivo = 1
    horario_campus = factory.SubFactory(HorarioCampusFactory)
    turno = factory.SelfAttribute('turma.turno')
    estrutura_curso = factory.SelfAttribute('componente_curricular.matriz.estrutura')
    calendario_academico = factory.SubFactory(CalendarioAcademicoFactory, ano_letivo=factory.SelfAttribute('..ano_letivo'))


class MatriculaDiarioFactory(DjangoModelFactory):
    class Meta:
        model = MatriculaDiario

    matricula_periodo = factory.SubFactory(MatriculaPeriodoFactory)
    diario = factory.SubFactory(DiarioFactory)
    situacao = MatriculaDiario.SITUACAO_APROVADO


class SolicitacaoAproveitamentoEstudoInternoFactory(SolicitacaoAproveitamentoEstudoFactory):
    class Meta:
        model = SolicitacaoAproveitamentoEstudoInterno

    diario_1 = factory.SubFactory(DiarioFactory)
    ementa_1 = 'ementa_1_teste.pdf'


class SolicitacaoAproveitamentoEstudoExternoFactory(SolicitacaoAproveitamentoEstudoFactory):
    class Meta:
        model = SolicitacaoAproveitamentoEstudoExterno

    requerimento = factory.SubFactory(RequerimentoAproveitamentoEstudoFactory, interno=False)
    ano_letivo_1 = factory.SubFactory(AnoFactory, ano=2025)
    periodo_letivo_1 = 1
    nome_1 = 'Disciplina Externa'
    nota_1 = 80
    frequencia_1 = 90
    ementa_1 = 'ementa_1_teste.pdf'


class TipoProfessorDiarioFactory(DjangoModelFactory):
    class Meta:
        model = TipoProfessorDiario
        django_get_or_create = ('descricao',)

    descricao = 'Principal'


class ProfessorDiarioFactory(DjangoModelFactory):
    class Meta:
        model = ProfessorDiario

    diario = factory.SubFactory(DiarioFactory)
    professor = factory.SubFactory(ProfessorFactory)
    tipo = factory.SubFactory(TipoProfessorDiarioFactory)


class AtividadeCurricularExtensaoFactory(DjangoModelFactory):
    class Meta:
        model = AtividadeCurricularExtensao

    matricula_periodo = factory.SubFactory(
        MatriculaPeriodoFactory,
        aluno=factory.SubFactory(
            AlunoFactory,
            curso_campus=factory.SubFactory(CursoCampusFactory),
            matriz=factory.SubFactory(MatrizFactory),
        ),
    )
    descricao = factory.Sequence(lambda n: f'Atividade Curricular de Extensão {n}')
    carga_horaria = 30
    concluida = True
    aprovada = True
    requer_distribuicao_ch = True


class VinculacaoAtividadeExtensaoFactory(DjangoModelFactory):
    class Meta:
        model = VinculacaoAtividadeExtensao

    matricula_diario = factory.SubFactory(MatriculaDiarioFactory)
    atividade_extensao = factory.SubFactory(
        AtividadeCurricularExtensaoFactory,
        matricula_periodo=factory.SelfAttribute('..matricula_diario.matricula_periodo'),
    )
    carga_horaria = 20
    homologada = None


class AproveitamentoEstudoFactory(DjangoModelFactory):
    class Meta:
        model = AproveitamentoEstudo

    matricula_periodo = factory.SubFactory(MatriculaPeriodoFactory)
    componente_curricular = factory.SubFactory(ComponenteCurricularFactory)
    data = factory.LazyFunction(datetime.date.today)
    nota = 80


class RegistroHistoricoFactory(DjangoModelFactory):
    class Meta:
        model = RegistroHistorico

    matricula_periodo = factory.SubFactory(MatriculaPeriodoFactory)
    componente = factory.SubFactory(ComponenteFactory)
    situacao = MatriculaDiario.SITUACAO_APROVADO
