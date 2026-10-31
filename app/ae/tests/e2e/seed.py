"""Seed do AE: os usuários do módulo e os dados de apoio que o behave carregava em ``features/steps/given.py``.

A suíte do módulo não tem mais ``features/`` (modo 2, unidade de cobertura = rota). ``criar_usuarios``
é a tabela ``os seguintes usuários`` do behave em factories (#17486): o campus CZN, os servidores
e o aluno. ``dados_demanda_aluno_ae`` e ``dados_basicos_ae`` são o corpo dos antigos steps ``os
cadastros de tipos de demandas do aluno`` e ``os dados basicos cadastrados do ae``. Tudo é
idempotente (``get_or_create``/``update``), requisito do banco compartilhado entre os módulos e
do ``--reuse-db`` do CI.
"""

from __future__ import annotations


from ae.models import (
    CategoriaAlimentacao,
    CompanhiaDomiciliar,
    ContribuinteRendaFamiliar,
    DemandaAluno,
    EstadoCivil,
    Idioma,
    MeioTransporte,
    MotivoSolicitacaoRefeicao,
    NecessidadeEspecial,
    NivelEscolaridade,
    OfertaBolsa,
    SituacaoTrabalho,
    TipoAcessoInternet,
    TipoAreaResidencial,
    TipoEscola,
    TipoImovelResidencial,
    TipoPrograma,
    TipoServicoSaude,
)
from comum.models import Configuracao, Raca
from djtools.e2e_fixtures import aluno_com_login, campus, criar_servidores
from edu.models.alunos import Aluno
from edu.models.cadastros_gerais import Turno
from rh.models import Setor, UnidadeOrganizacional

CAMPUS = ('CZN', 'Campus Zona Norte')
MATRICULA_ALUNO = '20191101011031'
SERVIDORES = {
    '103001': ('Coord_AE Sistemico', ['Coordenador de Atividades Estudantis Sistêmico']),
    '103002': ('Assistente Social', ['Assistente Social']),
}


def criar_usuarios() -> None:
    """Cria o campus CZN, o coordenador sistêmico, a assistente social e o aluno do módulo."""
    criar_servidores(campus(*CAMPUS), SERVIDORES)
    criar_aluno()


def criar_aluno() -> Aluno:
    """Aluno matriculado num curso da diretoria do próprio campus CZN, como fazia o step do behave.

    O curso fica no setor do campus: é a ``uo`` dele que as views comparam com a instituição do
    programa (``solicitar_refeicao``, o link "Inscrever-se em: ... (CZN)"). ``solicitar_refeicao``
    exige ``email_notificacao``: o e-mail pessoal do vínculo. ``staff`` porque o aluno abre telas
    do ``/admin/ae/`` (solicitações de auxílio).
    """
    return aluno_com_login(MATRICULA_ALUNO, campus(*CAMPUS), 'Aluno AE', 'TECINFO-AE-E2E', email_pessoal='aluno_ae_secundario@gmail.com')


def dados_demanda_aluno_ae() -> None:
    """Cadastra as demandas, os idiomas e a oferta de bolsa que os fluxos exigem."""
    DemandaAluno.objects.get_or_create(id=1, nome='Almoço', descricao='Almoço', custeio='Sem custeio')
    DemandaAluno.objects.get_or_create(id=2, nome='Jantar', descricao='Jantar', custeio='Sem custeio')
    Idioma.objects.get_or_create(descricao='Inglês')
    Idioma.objects.get_or_create(descricao='Espanhol')
    uo = UnidadeOrganizacional.objects.get(sigla='CZN')
    OfertaBolsa.objects.get_or_create(
        campus=uo, setor=Setor.objects.suap_ativos().get(sigla='CZN'), turno='Manhã', descricao_funcao='Descrição do trabalho a ser realizado.'
    )


def dados_basicos_ae() -> None:
    """Cadastra as tabelas de domínio (raça, escolaridade, transporte…) e o turno do aluno."""
    Configuracao.objects.get_or_create(app='comum', chave='salario_minimo', valor='954', descricao='valor do salário mínimo')

    NecessidadeEspecial.objects.get_or_create(descricao='Deficiência auditiva')
    ContribuinteRendaFamiliar.objects.get_or_create(descricao='Pai')
    ContribuinteRendaFamiliar.objects.get_or_create(descricao='Mãe')
    ContribuinteRendaFamiliar.objects.get_or_create(descricao='Parentes')
    ContribuinteRendaFamiliar.objects.get_or_create(descricao='Outros')
    ContribuinteRendaFamiliar.objects.get_or_create(descricao='O próprio aluno')
    ContribuinteRendaFamiliar.objects.get_or_create(descricao='Não informado')
    MeioTransporte.objects.get_or_create(descricao='Bicicleta')
    MeioTransporte.objects.get_or_create(descricao='Moto')
    MeioTransporte.objects.get_or_create(descricao='Transporte coletivo')
    MeioTransporte.objects.get_or_create(descricao='Automóvel')
    MeioTransporte.objects.get_or_create(descricao='Outro')
    CompanhiaDomiciliar.objects.get_or_create(descricao='Pai')
    CompanhiaDomiciliar.objects.get_or_create(descricao='Mãe')
    CompanhiaDomiciliar.objects.get_or_create(descricao='Outros')
    EstadoCivil.objects.get_or_create(descricao='Solteiro(a)')
    EstadoCivil.objects.get_or_create(descricao='Casado(a)')
    EstadoCivil.objects.get_or_create(descricao='Viúvo(a)')
    TipoServicoSaude.objects.get_or_create(descricao='Sistema Único de Saúde - SUS')
    TipoServicoSaude.objects.get_or_create(descricao='Plano de saúde particular')
    TipoServicoSaude.objects.get_or_create(descricao='Plano de saúde da empresa')
    TipoEscola.objects.get_or_create(descricao='Somente em escola pública')
    TipoEscola.objects.get_or_create(descricao='Somente em escola particular')
    TipoEscola.objects.get_or_create(descricao='Outro tipo de escola')
    NivelEscolaridade.objects.get_or_create(descricao='Ensino fundamental completo')
    NivelEscolaridade.objects.get_or_create(descricao='Ensino médio completo')
    NivelEscolaridade.objects.get_or_create(descricao='Ensino superior completo')
    SituacaoTrabalho.objects.get_or_create(descricao='Não está trabalhando')
    SituacaoTrabalho.objects.get_or_create(descricao='Autônomo')
    SituacaoTrabalho.objects.get_or_create(descricao='Nunca trabalhou')
    SituacaoTrabalho.objects.get_or_create(descricao='Trabalha com vínculo empregatício')
    TipoImovelResidencial.objects.get_or_create(descricao='Financiado')
    TipoImovelResidencial.objects.get_or_create(descricao='Alugado')
    TipoImovelResidencial.objects.get_or_create(descricao='Próprio')
    TipoImovelResidencial.objects.get_or_create(descricao='Outro')
    TipoAreaResidencial.objects.get_or_create(descricao='Urbana')
    TipoAreaResidencial.objects.get_or_create(descricao='Rural')
    TipoAcessoInternet.objects.get_or_create(descricao='Diariamente')
    TipoAcessoInternet.objects.get_or_create(descricao='Semanalmente')

    Raca.objects.get_or_create(descricao='Parda', codigo_siape=4)
    Raca.objects.get_or_create(descricao='Preta', codigo_siape=6)
    Raca.objects.get_or_create(descricao='Branca', codigo_siape=1)
    Raca.objects.get_or_create(descricao='Indígena', codigo_siape=5)
    Raca.objects.get_or_create(descricao='Amarela', codigo_siape=3)
    Raca.objects.get_or_create(descricao='Não declarado', codigo_siape=9)

    TipoPrograma.objects.filter(titulo='Alimentação Estudantil').update(sigla='ALM')
    TipoPrograma.objects.filter(titulo='Auxílio Transporte').update(sigla='PAS')
    TipoPrograma.objects.filter(titulo='Apoio à Formação Estudantil').update(sigla='TRB')
    TipoPrograma.objects.filter(titulo='Curso de Idiomas').update(sigla='IDM')
    CategoriaAlimentacao.objects.get_or_create(nome='AS', descricao='Assistência Social')
    CategoriaAlimentacao.objects.get_or_create(nome='Bolsa de extensão', descricao='Bolsa de extensão')
    CategoriaAlimentacao.objects.get_or_create(nome='Bolsa de pesquisa', descricao='Bolsa de pesquisa')
    MotivoSolicitacaoRefeicao.objects.get_or_create(descricao='Aula no turno inverso')
    turno = Turno.objects.get_or_create(descricao='Matutino')[0]
    aluno = Aluno.objects.get(matricula=MATRICULA_ALUNO)
    aluno.turno = turno
    aluno.save()


def criar_caracterizacao(aluno) -> None:
    """Cria/atualiza a caracterização socioeconômica mínima que as telas do AE exigem.

    Era o helper privado ``_criar_caracterizacao`` do conftest; mora aqui porque o smoke de
    rotas também precisa dele (a fixture pública continua sendo ``caracterizacao_pronta``).
    Idempotente: reusa a caracterização existente do aluno, se houver.
    """
    from ae.models import (
        Caracterizacao,
        CompanhiaDomiciliar,
        ContribuinteRendaFamiliar,
        EstadoCivil,
        MeioTransporte,
        NivelEscolaridade,
        SituacaoTrabalho,
        TipoAcessoInternet,
        TipoAreaResidencial,
        TipoEscola,
        TipoImovelResidencial,
        TipoServicoSaude,
    )
    from comum.models import Raca

    comuns = {
        'raca': Raca.objects.get(descricao='Parda'),
        'estado_civil': EstadoCivil.objects.get(descricao='Solteiro(a)'),
        'ensino_fundamental_conclusao': 2017,
        'escola_ensino_fundamental': TipoEscola.objects.get(descricao='Somente em escola pública'),
        'nome_escola_ensino_fundamental': 'Escola pública',
        'escola_ensino_medio': TipoEscola.objects.get(descricao='Somente em escola pública'),
        'nome_escola_ensino_medio': 'Escola pública',
        'trabalho_situacao': SituacaoTrabalho.objects.get(descricao='Não está trabalhando'),
        'responsavel_financeir_trabalho_situacao': SituacaoTrabalho.objects.get(descricao='Autônomo'),
        'responsavel_financeiro': ContribuinteRendaFamiliar.objects.get(descricao='Pai'),
        'responsavel_financeiro_nivel_escolaridade': NivelEscolaridade.objects.get(descricao='Ensino médio completo'),
        'pai_nivel_escolaridade': NivelEscolaridade.objects.get(descricao='Ensino médio completo'),
        'mae_nivel_escolaridade': NivelEscolaridade.objects.get(descricao='Ensino médio completo'),
        'renda_bruta_familiar': 2500,
        'companhia_domiciliar': CompanhiaDomiciliar.objects.get(descricao='Pai'),
        'qtd_pessoas_domicilio': 1,
        'tipo_imovel_residencial': TipoImovelResidencial.objects.get(descricao='Financiado'),
        'tipo_area_residencial': TipoAreaResidencial.objects.get(descricao='Urbana'),
        'tipo_servico_saude': TipoServicoSaude.objects.get(descricao='Sistema Único de Saúde - SUS'),
        'frequencia_acesso_internet': TipoAcessoInternet.objects.get(descricao='Diariamente'),
        'quantidade_computadores': 1,
        'quantidade_notebooks': 1,
        'quantidade_netbooks': 0,
        'quantidade_smartphones': 1,
        'aluno_exclusivo_rede_publica': True,
        'possui_necessidade_especial': False,
        'possui_conhecimento_idiomas': False,
        'possui_conhecimento_informatica': True,
        'ficou_tempo_sem_estudar': False,
    }
    caracterizacao = Caracterizacao.objects.filter(aluno=aluno).first()
    if caracterizacao is None:
        caracterizacao = Caracterizacao(aluno=aluno, **comuns)
    else:
        for campo, valor in comuns.items():
            setattr(caracterizacao, campo, valor)
    caracterizacao.informado_por = None
    caracterizacao.save()
    caracterizacao.meio_transporte_utilizado.set(MeioTransporte.objects.filter(descricao__in=['Bicicleta', 'Moto']))
    caracterizacao.contribuintes_renda_familiar.set(ContribuinteRendaFamiliar.objects.filter(descricao__in=['Pai', 'Mãe']))
