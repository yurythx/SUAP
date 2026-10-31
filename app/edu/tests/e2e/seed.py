"""Replay ORM do mundo do edu: diretoria → curso → turma → matrícula → período → ENADE.

Origem: era ``edu/features/steps/given.py``, onde estas funções eram os steps ``Dado`` do
behave. Com a remoção do behave do edu, o registro (``@given('...')``) e o import do
``behave`` saíram — as funções são o que sempre importou, e continuam sendo o substrato
que as fixtures do ``conftest.py`` replicam para montar o mundo do módulo.

O parâmetro ``context`` sobreviveu à mudança: no behave era o contexto real, e nos e2e é o
``relogio`` do conftest, que implementa a interface mínima (``execute_steps``). Os nomes
``step_cadastros_feature_00N`` também: é por eles que ``conftest._replay()`` encadeia as
etapas, e são a única pista que resta de qual ``.feature`` cada bloco reproduzia.

Não há mais consumidor externo: o behave do módulo ``erros``, último a chamar
``cadastrar_aluno`` e ``step_cadastros_feature_002`` daqui, também foi removido.
"""

from django.conf import settings
from django.contrib.auth.models import Group
from datetime import datetime
from edu.models.cursos import Componente, ComponenteCurricular, Matriz, EstruturaCurso, CursoCampus, MatrizCurso
from edu.models.cadastros_gerais import (
    AreaCursoFormacaoSuperior,
    Estado,
    Pais,
    TipoComponente,
    NivelEnsino,
    Nucleo,
    NaturezaParticipacao,
    AreaCapes,
    Modalidade,
    TipoProfessorDiario,
    HorarioAulaDiario,
    HorarioAula,
    HorarioCampus,
    FormaIngresso,
    Cidade,
    SituacaoMatricula,
    SituacaoMatriculaPeriodo,
    Turno,
)
from edu.models.diretorias import Diretoria, CalendarioAcademico
from edu.models.diarios import Diario, ProfessorDiario, ConfiguracaoAvaliacao, ItemConfiguracaoAvaliacao, Aula, NotaAvaliacao
from edu.models.professores import Professor
from edu.models.turmas import Turma
from edu.models.alunos import Aluno, SequencialMatricula
from edu.models.historico import MatriculaPeriodo, MatriculaDiario
from edu.models.utils import HistoricoSituacaoMatricula, HistoricoSituacaoMatriculaPeriodo
from edu.models.procedimentos import ConfiguracaoPedidoMatricula, PedidoMatriculaDiario, PedidoMatricula


# O curso em regime de crédito da funcionalidade 011, procurado pelo nome em três lugares
# (o seed, o `_limpar_credito` do conftest e o ENADE) — por isso os literais viram nomes.
NOME_CURSO_LICENCIATURA = 'Licenciatura em Geografia'
CODIGO_CURSO_LICENCIATURA = '20101'
CPF_ALUNA_LICENCIATURA = '194.733.810-26'


def mudar_data(context, data):
    context.execute_steps(f'Quando a data do sistema for "{data}"')


def step_cadastros_pais_estado(context):
    Pais.objects.get_or_create(nome='Brasil')
    Estado.objects.get_or_create(id=24, nome='Rio Grande do Norte')


def semear_estrutura():
    """O que o seed legado do behave dava ao edu e o seed por factories não dá (#17486).

    Ano/período letivo corrente (2019.1), os anos 2018-2020 e a árvore CEN → DIAC/CEN →
    DIATI/CEN e CZN → DIAC/CZN, com as siglas de lá: os testes e a doc as citam, e o
    ``setor_livre`` do conftest precisa de setores folha sem diretoria (DIATI/CEN, DIAC/CZN).
    Idempotente.
    """
    from django.core.cache import cache

    from comum.models import Ano, Configuracao
    from djtools.e2e_fixtures import campus, setor

    # (app, chave, valor) inteiros no lookup, como o `semear_base`: não duplica a chave de outro seed.
    for chave, valor in (('ano_letivo_atual', '2019'), ('periodo_letivo_atual', '1')):
        Configuracao.objects.get_or_create(app='edu', chave=chave, valor=valor)
    cache.clear()  # `Configuracao` é lida via cache
    for ano in (2018, 2019, 2020):
        Ano.objects.get_or_create(ano=ano)
    setor('DIATI/CEN', setor('DIAC/CEN', campus('CEN', 'Campus Central')))
    setor('DIAC/CZN', campus('CZN', 'Campus Zona Norte'), 'Diretoria Acadêmica')


# (matrícula, nome, sigla do setor, grupo com escopo de setor)
# Mesmos servidores da tabela "Dado os seguintes usuários" de
# `001.EDU.configurar-diretoria.feature`. O grupo com escopo de setor corresponde ao
# cenário "Vincular ..." daquela feature; `None` significa que o servidor só entra no
# grupo global "Servidor".
SERVIDORES_001 = (
    ('100001', 'Administrador Acadêmico', 'DIAC/CEN', None),
    ('100002', 'Servidor SA', 'DIAC/CEN', 'Secretário Acadêmico'),
    ('100003', 'Servidor DG', 'DIAC/CEN', 'Diretor Geral'),
    ('100004', 'Servidor DA', 'DIAC/CEN', 'Diretor Acadêmico'),
    ('100005', 'Servidor CC', 'DIAC/CEN', 'Coordenador de Curso'),
    ('100006', 'Servidor CRA', 'DIAC/CEN', 'Coordenador de Registros Acadêmicos'),
    ('100007', 'Servidor P', 'DIAC/CEN', None),
    ('100008', 'Servidor Op Enade', 'DIAC/CEN', 'Operador ENADE'),
    ('100009', 'Servidor DARE', 'RAIZ', 'Diretor de Avaliação e Regulação do Ensino'),
)


def _criar_servidor(matricula, nome, sigla_setor):
    """Servidor staff no grupo "Servidor", lotado no setor SUAP `sigla_setor`, com senha ``SENHA_E2E``."""
    from djtools.e2e_fixtures import servidor_com_login
    from rh.models import Setor

    setor = Setor.objects.suap_ativos().get(sigla=sigla_setor)
    return servidor_com_login(matricula, setor, grupos=['Servidor'], staff=True, pessoa_fisica__nome=nome)


def _vincular_grupo_no_setor(servidor, nome_grupo, setor):
    """Coloca o servidor num grupo com escopo de setor (o que a tela de diretoria faz)."""
    from comum.models import UsuarioGrupo, UsuarioGrupoSetor

    grupo = Group.objects.get(name=nome_grupo)
    usuario_grupo = UsuarioGrupo.objects.get_or_create(group=grupo, user=servidor.get_user())[0]
    UsuarioGrupoSetor.objects.get_or_create(usuario_grupo=usuario_grupo, setor=setor)


def step_cadastros_feature_001(context):
    from rh.models import Setor

    # Sentinela na ÚLTIMA escrita do bloco (o diretor acadêmico da diretoria), não numa do
    # meio: um replay que morre pela metade não pode parecer completo na próxima execução.
    if Diretoria.objects.filter(setor__sigla='DIAC/CEN', diretor_academico__isnull=False).exists():
        return

    mudar_data(context, '10/03/2019')

    # Cenário: Cadastrar Diretoria Acadêmica / Cadastrar Diretoria Sistêmica
    diretoria = Diretoria.objects.get_or_create(setor=Setor.objects.suap_ativos().get(sigla='DIAC/CEN'))[0]
    reitoria = Diretoria.objects.get_or_create(setor=Setor.objects.suap_ativos().get(sigla='RAIZ'), tipo=Diretoria.TIPO_SISTEMICA)[0]
    setores_de_grupo = {'DIAC/CEN': diretoria.setor, 'RAIZ': reitoria.setor}

    servidores = {}
    for matricula, nome, sigla_setor, grupo in SERVIDORES_001:
        servidor = _criar_servidor(matricula, nome, sigla_setor)
        servidores[matricula] = servidor
        if grupo:
            # Cenários "Vincular <papel>": o grupo vale no setor da diretoria.
            _vincular_grupo_no_setor(servidor, grupo, setores_de_grupo[sigla_setor])

    # Administrador Acadêmico é grupo global, não tem escopo de setor.
    servidores['100001'].get_user().groups.add(Group.objects.get(name='Administrador Acadêmico'))

    diretoria.diretor_geral = servidores['100003'].get_vinculo()
    diretoria.diretor_geral_exercicio = servidores['100003'].get_vinculo()
    diretoria.diretor_academico = servidores['100004'].get_vinculo()
    diretoria.diretor_academico_exercicio = servidores['100004'].get_vinculo()
    diretoria.save()


# (matrícula, nome, sigla do setor, grupo)
#
# Servidores que NÃO vêm de nenhuma `.feature`: existem só para o smoke de rota
# (`edu/tests/e2e/test_15`→`test_19`) poder declarar o papel que a view de fato exige.
# Sem eles, 20 rotas que renderizam tela ficariam permanentemente em 403 — e 403 num smoke
# de rota significa "papel errado no teste", nunca "rota não navegável".
#
# Cada grupo aqui é o que `edu/permissions.yaml` diz que concentra a permissão do decorador:
# `comum.is_migrador_edu` só existe em "Migrador edu"; `comum.is_operador_de_censo` só em
# "Operador de Censo"; `edu.change_matriculadiario`/`view_log` em "edu Administrador"; as de
# acolhimento em "Coordenador do Napne".
SERVIDORES_ROTAS = (
    ('100010', 'Servidor Migrador', 'DIAC/CEN', 'Migrador edu'),
    ('100011', 'Servidor Op Censo', 'DIAC/CEN', 'Operador de Censo'),
    ('100012', 'Servidor Admin edu', 'DIAC/CEN', 'edu Administrador'),
    ('100013', 'Servidor Napne', 'DIAC/CEN', 'Coordenador do Napne'),
    ('100014', 'Servidor Pe de Meia', 'DIAC/CEN', None),
    ('100015', 'Servidor Eventos', 'DIAC/CEN', None),
    ('100016', 'Servidor Professor Grupo', 'DIAC/CEN', 'Professor'),
)

# Ambas eram ÓRFÃS quando este seed foi escrito (medido em 02/08/2026): `edu.view_operacaopedemeia`
# — exigida por `edu/views/pedemeia.py:16,27,40` e pelo item de menu `edu/menu.yaml:801` — e
# `edu.add_evento` — exigida por 6 views de `edu/views/eventos.py` e pelo `EventoAdmin`. Nenhum
# grupo de `edu/permissions.yaml` as concedia, então em produção essas telas eram inalcançáveis
# por qualquer perfil não-superusuário. As duas foram acrescentadas ao "Administrador Acadêmico":
# a do Pé de Meia junto dos outros três models do programa, que já estavam lá.
#
# A concessão direta abaixo permanece de propósito: mantém estes testes independentes daquela
# correção, para que uma reversão em `permissions.yaml` apareça como falha de produção e não
# como quebra da suíte.
PERMISSOES_DIRETAS = {'100014': ('edu.view_operacaopedemeia',), '100015': ('edu.add_evento',)}


def step_cadastros_servidores_de_rota(context):
    """Servidores dos papéis que o smoke de rota exige e as `.feature` não criavam.

    Guardado pelo último servidor da tabela, não pelo primeiro: um replay interrompido no
    meio não pode parecer completo na execução seguinte.

    O grupo tem de existir **no seed de sessão**, antes do primeiro login do usuário: o SUAP
    cacheia a permissão por processo (``has_group_cached``), então conceder grupo depois de
    o usuário já ter navegado não tem efeito visível no mesmo processo.
    """
    from django.contrib.auth.models import Permission

    from rh.models import Servidor, Setor

    if Servidor.objects.filter(matricula='100016').exists():
        return

    setor = Setor.objects.suap_ativos().get(sigla='DIAC/CEN')
    for matricula, nome, sigla_setor, grupo in SERVIDORES_ROTAS:
        servidor = _criar_servidor(matricula, nome, sigla_setor)
        if grupo:
            _vincular_grupo_no_setor(servidor, grupo, setor)
        for permissao in PERMISSOES_DIRETAS.get(matricula, ()):
            app, codename = permissao.split('.')
            servidor.get_user().user_permissions.add(Permission.objects.get(content_type__app_label=app, codename=codename))


def step_cadastros_feature_002(context):
    if not TipoComponente.objects.filter(descricao='POS').exists():
        from comum.models import Ano, Vinculo

        step_configurar_avaliacao_conceito(None)

        # Cenário: Cadastrar Tipo de Componente
        step_cadastro_tipo_componente(None)
        tipo = TipoComponente.objects.get_or_create(descricao='POS')[0]

        # Cenário: Cadastrar Componente
        step_cadastro_componente(None)
        diretoria = Diretoria.objects.get(setor__sigla='DIAC/CEN')
        nivel = NivelEnsino.objects.get(descricao='Pós-graduação')
        componente = {
            'descricao': 'Leitura e Produção de Textos Acadêmicos',
            'descricao_historico': 'Leitura e Produção de Textos Acadêmicos',
            'abreviatura': 'LPTA',
            'tipo': tipo,
            'diretoria': diretoria,
            'nivel_ensino': nivel,
            'ativo': True,
            'ch_hora_relogio': 45,
            'ch_hora_aula': 60,
            'ch_qtd_creditos': 3,
        }
        Componente.objects.get_or_create(**componente)

        # Cenário: Cadastrar Estrutura de Curso
        estrutura = {
            'descricao': 'Especialização e Aperfeiçoamento',
            'ativo': True,
            'tipo_avaliacao': EstruturaCurso.TIPO_AVALIACAO_SERIADO,
            'limite_reprovacao': 10,
            'criterio_avaliacao': EstruturaCurso.CRITERIO_AVALIACAO_NOTA,
            'media_aprovacao_sem_prova_final': 60,
            'media_evitar_reprovacao_direta': 20,
            'media_aprovacao_avaliacao_final': 60,
            'percentual_frequencia': 75,
            'ira': EstruturaCurso.IRA_PONDERADA_POR_CH,
            'qtd_periodos_conclusao': 4,
            'qtd_max_reprovacoes_periodo': 0,
            'qtd_max_reprovacoes_disciplina': 0,
            'qtd_trancamento_voluntario': 2,
            'exige_periodo_ingresso_integralizado': True,
            'numero_max_certificacoes': 4,
            'media_certificacao_conhecimento': 60,
        }
        estrutura = EstruturaCurso.objects.get_or_create(**estrutura)[0]

        # Cenário: Cadastrar Natureza de Participação
        natureza = NaturezaParticipacao.objects.get_or_create(descricao='Presencial')[0]

        # Cenário: Cadastrar Matriz Curricular
        ano = Ano.objects.get(ano=2019)
        matriz = {
            'descricao': 'Especialização em Educação Profissional',
            'ano_criacao': ano,
            'periodo_criacao': 1,
            'nivel_ensino': nivel,
            'natureza_participacao': natureza,
            'ativo': True,
            'data_inicio': datetime.strptime('15/03/2019', '%d/%m/%Y'),
            'qtd_periodos_letivos': 2,
            'estrutura': estrutura,
            'ch_componentes_obrigatorios': 90,
            'ch_componentes_optativos': 0,
            'ch_componentes_eletivos': 0,
            'ch_seminarios': 0,
            'ch_pratica_profissional': 0,
            'ch_componentes_tcc': 30,
            'exige_tcc': True,
            'ch_atividades_complementares': 0,
            'ch_atividades_aprofundamento': 0,
            'ch_atividades_extensao': 0,
            'ch_pratica_como_componente': 0,
            'ch_visita_tecnica': 0,
        }
        matriz = Matriz.objects.get_or_create(**matriz)[0]

        # Cenário: Cadastrar Núcleo
        nucleo = Nucleo.objects.get_or_create(descricao='Formação')[0]

        # Cenário: Vincular Componente à Matriz Curricular
        step_cadastro_componente_curricular(None)
        componente_curricular = {
            'matriz': matriz,
            'componente': Componente.objects.get(abreviatura='LPTA'),
            'periodo_letivo': 1,
            'tipo': ComponenteCurricular.TIPO_REGULAR,
            'qtd_avaliacoes': 1,
            'nucleo': nucleo,
            'ch_presencial': 45,
            'ch_pratica': 0,
        }
        ComponenteCurricular.objects.get_or_create(**componente_curricular)

        # Cenário: Cadastrar Área Capes
        areacapes = AreaCapes.objects.get_or_create(descricao='Educação')[0]

        # Cenário: Cadastrar Curso
        diretoria = Diretoria.objects.get(setor__sigla='DIAC/CEN')
        curso = {
            'descricao': 'Especialização em Educação Profissional',
            'descricao_historico': 'Especialização em Educação Profissional',
            'ano_letivo': ano,
            'periodo_letivo': 1,
            'data_inicio': datetime.strptime('15/03/2019', '%d/%m/%Y'),
            'quantidade_vagas': 10,
            'coordenador': Vinculo.objects.filter(user__username='100005').first(),
            'ativo': True,
            'codigo': '10101',
            'modalidade': Modalidade.objects.get(descricao='Especialização'),
            'area_capes': areacapes,
            'periodicidade': CursoCampus.PERIODICIDADE_SEMESTRAL,
            'diretoria': diretoria,
            'emite_diploma': True,
            'plano_ensino': True,
            'fator_esforco_curso': 1,
            'titulo_certificado_masculino': 'Especialista em Educação Profissional',
            'titulo_certificado_feminino': 'Especialista em Educação Profissional',
        }
        curso = CursoCampus.objects.get_or_create(**curso)[0]

        # Cenário: Vincular Matriz ao Curso
        matrizcurso = {
            'matriz': matriz,
            'curso_campus': curso,
        }
        MatrizCurso.objects.get_or_create(**matrizcurso)

        # Cenário: Cadastrar Estrutura de Curso, Matriz e Curso com Avaliação por Conceito
        # Estrutura de curso
        estrutura_conceito = {
            'descricao': 'Especialização com Avaliação por Conceito',
            'ativo': True,
            'tipo_avaliacao': EstruturaCurso.TIPO_AVALIACAO_SERIADO,
            'limite_reprovacao': 10,
            'criterio_avaliacao': EstruturaCurso.CRITERIO_AVALIACAO_CONCEITO,
            'conceito_minimo_aprovacao': 'C',
            'percentual_frequencia': 75,
            'ira': EstruturaCurso.IRA_PONDERADA_POR_CH,
            'qtd_periodos_conclusao': 4,
            'qtd_max_reprovacoes_periodo': 0,
            'qtd_max_reprovacoes_disciplina': 0,
            'qtd_trancamento_voluntario': 2,
            'exige_periodo_ingresso_integralizado': True,
            'numero_max_certificacoes': 4,
        }
        estrutura_conceito = EstruturaCurso.objects.get_or_create(**estrutura_conceito)[0]

        # Matriz curricular
        matriz_conceito = Matriz.objects.filter(descricao='Especialização em Educação Profissional [CONCEITO]').first()
        if matriz_conceito is None:
            matriz_conceito = Matriz.objects.get(descricao='Especialização em Educação Profissional').replicar(
                'Especialização em Educação Profissional [CONCEITO]'
            )
            matriz_conceito.estrutura = estrutura_conceito
            matriz_conceito.save()
        for componente_curricular in matriz_conceito.get_componentes_curriculares():
            componente_curricular.avaliacao_por_conceito = True
            componente_curricular.save()

        # Curso
        curso_conceito = CursoCampus.objects.filter(descricao='Especialização em Educação Profissional [CONCEITO]').first()
        if curso_conceito is None:
            curso_conceito = CursoCampus.objects.get(descricao='Especialização em Educação Profissional').replicar(
                diretoria=curso.diretoria, codigo='20202', coordenador=curso.coordenador
            )
            curso_conceito.descricao = 'Especialização em Educação Profissional [CONCEITO]'
            curso_conceito.save()

        # Vinculando matriz a curso
        MatrizCurso.objects.get_or_create(matriz=matriz_conceito, curso_campus=curso_conceito)


def diario_da_especializacao(sigla, periodo_letivo=1):
    """Diário do componente `sigla` na matriz "Especialização em Educação Profissional".

    Substitui os antigos `Diario.objects.get(pk=1)`/`pk=2`: PK fixa só é estável enquanto
    este replay for a única coisa a gerar diários no banco, o que deixou de valer quando
    a suíte e2e passou a criar turmas pela interface.

    `ano_letivo__ano=2019` não é redundante: a cadeia 01→14 inteira vive em 2019, mas o smoke
    de rota cria turma/diários de sacrifício em OUTRO ano — e as ações que ele exercita
    (`replicar_diario`, `dividir_diario`) multiplicam esses diários. Sem o filtro de ano, este
    `.get()` alcança as cópias e estoura `MultipleObjectsReturned` na segunda execução em
    `--reuse-db`. Filtrar por componente não resolve: exclui-se uma sigla, a colisão migra
    para a seguinte.
    """
    return Diario.objects.get(
        componente_curricular__componente__sigla=sigla,
        turma__matriz__descricao='Especialização em Educação Profissional',
        turma__periodo_letivo=periodo_letivo,
        turma__ano_letivo__ano=2019,
    )


def step_cadastros_feature_003(context):
    if not HorarioCampus.objects.filter(descricao='Horário Padrão [Aula 45min]', ativo=True, eh_padrao=True).exists():
        from comum.models import Ano, Sala, Vinculo
        from rh.models import UnidadeOrganizacional

        # Cenário: Cadastrar Horário do Campus
        uo = UnidadeOrganizacional.objects.suap().get(sigla='CEN')
        horariocampus = HorarioCampus.objects.get_or_create(descricao='Horário Padrão [Aula 45min]', uo=uo, ativo=True, eh_padrao=True)[0]
        turno = Turno.objects.get(descricao='Matutino')
        HorarioAula.objects.get_or_create(horario_campus=horariocampus, numero=1, turno=turno, inicio='7:00', termino='7:45')
        HorarioAula.objects.get_or_create(horario_campus=horariocampus, numero=2, turno=turno, inicio='7:50', termino='8:35')
        HorarioAula.objects.get_or_create(horario_campus=horariocampus, numero=3, turno=turno, inicio='8:40', termino='9:25')

        # Cenário: Cadastrar Tipo de Professor em Diário
        TipoProfessorDiario.objects.get_or_create(descricao='Principal')[0]

        # Cenário: Cadastrar Calendário Acadêmico
        step_cadastro_calendario_academico(None)
        ano_letivo = Ano.objects.get(ano=2019)
        diretoria = Diretoria.objects.get(setor__sigla='DIAC/CEN')
        calendario = CalendarioAcademico.objects.get_or_create(
            descricao='Calendário Acadêmico Especialização 2019.1',
            uo=uo,
            diretoria=diretoria,
            tipo=CalendarioAcademico.TIPO_SEMESTRAL,
            ano_letivo=ano_letivo,
            periodo_letivo=1,
            data_inicio=datetime.strptime('20/03/2019', '%d/%m/%Y'),
            data_fim=datetime.strptime('18/07/2019', '%d/%m/%Y'),
            data_fechamento_periodo=datetime.strptime('19/07/2019', '%d/%m/%Y'),
            qtd_etapas=CalendarioAcademico.QTD_ETAPA_1,
            data_inicio_etapa_1=datetime.strptime('20/03/2019', '%d/%m/%Y'),
            data_fim_etapa_1=datetime.strptime('18/07/2019', '%d/%m/%Y'),
        )[0]

        # Cenário: Gerar Turmas e Diário
        curso = CursoCampus.objects.get(descricao='Especialização em Educação Profissional')
        matriz = Matriz.objects.get(descricao='Especialização em Educação Profissional')
        # O filtro PRECISA amarrar a matriz: a funcionalidade 002 replica esta matriz em
        # "[CONCEITO]", e sem `matriz=matriz` as siglas casariam nas duas — gerando diários
        # duplicados, que depois fazem os `Diario.objects.get(...)` por sigla estourarem
        # `MultipleObjectsReturned`.
        componentes = ComponenteCurricular.objects.filter(componente__sigla__in=['POS.0003', 'POS.0001'], matriz=matriz)
        if not Turma.objects.filter(ano_letivo=ano_letivo, periodo_letivo=1, curso_campus=curso, matriz=matriz).exists():
            Turma.gerar_turmas(ano_letivo, 1, {1: turno}, {1: 10}, {1: 1}, curso, matriz, horariocampus, calendario, componentes, False, None, True)

        # Cenário: Configurar Diário
        step_cadastro_predio(None)
        step_cadastro_sala(None)
        step_configuracao_diario(None)
        diario = diario_da_especializacao('POS.0001')
        diario.local_aula = Sala.objects.get(nome='Sala 101')
        diario.save()
        vinculo = Vinculo.objects.get(pessoa__nome='Servidor P')
        professor = Professor.objects.get_or_create(vinculo=vinculo)[0]
        Professor.objects.update(
            titulacao='Graduado', ultima_instituicao_de_titulacao='UFRN', area_ultima_titulacao='01', ano_ultima_titulacao=Ano.objects.first()
        )
        professor.vinculo.user.groups.add(Group.objects.get(name='Professor'))
        professordiario = {
            'diario': diario,
            'professor': professor,
            'tipo': TipoProfessorDiario.objects.get(descricao='Principal'),
            'percentual_ch': 100,
            'data_inicio_etapa_1': datetime.strptime('20/03/2019', '%d/%m/%Y'),
            'data_fim_etapa_1': datetime.strptime('25/07/2019', '%d/%m/%Y'),
            'data_inicio_etapa_final': datetime.strptime('19/07/2019', '%d/%m/%Y'),
            'data_fim_etapa_final': datetime.strptime('26/07/2019', '%d/%m/%Y'),
        }
        ProfessorDiario.objects.get_or_create(**professordiario)
        step_definicao_horario_aula_diario(None, '1M1,1M2', diario.pk)


def step_cadastros_feature_004(context):
    if not FormaIngresso.objects.filter(descricao='Ampla Concorrência').exists():
        from comum.models import Ano, Raca
        from rh.models import PessoaFisica

        step_cadastros_pais_estado(context)

        # Cenário: Cadastrar Forma de Ingresso
        ingresso = FormaIngresso.objects.get_or_create(
            descricao='Ampla Concorrência', ativo=True, classificacao_censup=FormaIngresso.ENEM, classificacao_educacenso=4
        )[0]

        # Cenário: Cadastrar Cidade. O `codigo` (IBGE) não é decorativo: a Matrícula
        # Institucional restringe o autocomplete de Naturalidade a `codigo__isnull=False`
        # para alunos brasileiros, então sem ele a cidade some da tela.
        cidade = Cidade.objects.update_or_create(
            nome='Natal',
            defaults={'estado': Estado.objects.get(pk=24), 'pais': Pais.objects.get(nome='Brasil'), 'codigo': '2408102'},
        )[0]

        # Cenário: Efetuar Matrícula Institucional
        step_cadastro_raca(None)
        pessoa_fisica = PessoaFisica()
        pessoa_fisica.cpf = '770.625.744-49'
        pessoa_fisica.nome_registro = 'João da Silva'
        pessoa_fisica.sexo = 'M'
        pessoa_fisica.nascimento_data = datetime.strptime('10/10/1990', '%d/%m/%Y')
        pessoa_fisica.save()

        ano = Ano.objects.get(ano=2019)
        curso = CursoCampus.objects.get(descricao='Especialização em Educação Profissional')
        matriz = Matriz.objects.get(descricao='Especialização em Educação Profissional')

        aluno = cadastrar_aluno(pessoa_fisica, cidade, ano, ingresso, curso, matriz)
        definir_dados_vinculo(aluno, raca=Raca.objects.get(descricao='Parda'), email_pessoal='joao.silva@email.com')
        matricular_aluno(aluno, ano, curso, matriz)

        pessoa_fisica2 = PessoaFisica()
        pessoa_fisica2.cpf = '901.348.860-97'
        pessoa_fisica2.nome_registro = 'Pedro da Silva'
        pessoa_fisica2.sexo = 'M'
        pessoa_fisica2.nascimento_data = datetime.strptime('10/10/1990', '%d/%m/%Y')
        pessoa_fisica2.save()
        aluno2 = cadastrar_aluno(pessoa_fisica2, cidade, ano, ingresso, curso, matriz)
        definir_dados_vinculo(aluno2, raca=Raca.objects.get(descricao='Parda'), email_pessoal='pedro.silva@email.com')
        matricular_aluno(aluno2, ano, curso, matriz)

        # Cenário: Matricular em Turma
        turma = Turma.objects.get(ano_letivo=ano, periodo_letivo=1, periodo_matriz=1, curso_campus=curso, matriz=matriz)
        mp = MatriculaPeriodo.objects.filter(aluno__curso_campus=curso, ano_letivo=ano, periodo_letivo=1, periodo_matriz=1)

        turma.matricular_alunos(mp)


def step_cadastros_feature_005(context):
    if not Aula.objects.all().exists():
        # Cenário: Acessar diário
        diario = diario_da_especializacao('POS.0001')

        # Cenário: Configurar Forma de Avaliação
        configuracao = ConfiguracaoAvaliacao.objects.get(diario=diario, etapa=1)
        item_configuracao_avaliacao = ItemConfiguracaoAvaliacao.objects.get(configuracao_avaliacao=configuracao)
        item_configuracao_avaliacao.tipo = ItemConfiguracaoAvaliacao.TIPO_SEMINARIO
        item_configuracao_avaliacao.sigla = 'S1'
        item_configuracao_avaliacao.descricao = 'Avaliação final'
        item_configuracao_avaliacao.data = datetime.strptime('20/07/2019', '%d/%m/%Y')
        item_configuracao_avaliacao.save()

        # Cenário: Registrar Aula
        mudar_data(context, '21/03/2019')
        professor = Professor.objects.get(vinculo__pessoa__nome='Servidor P')
        professordiario = ProfessorDiario.objects.get(diario=diario, professor=professor)
        Aula.objects.get_or_create(
            etapa=1,
            quantidade=60,
            data=datetime.strptime('20/03/2019', '%d/%m/%Y'),
            conteudo='Apresentação da disciplina',
            professor_diario=professordiario,
        )

        # Cenário: Lançar Notas
        matricula_periodo = MatriculaPeriodo.objects.get(aluno__matricula='20191101010001', ano_letivo__ano=2019, periodo_letivo=1)
        matricula_diario = MatriculaDiario.objects.get(diario=diario, matricula_periodo=matricula_periodo)
        nota_avaliacao = NotaAvaliacao.objects.get(matricula_diario=matricula_diario, item_configuracao_avaliacao=item_configuracao_avaliacao)
        nota_avaliacao.nota = 70
        nota_avaliacao.save()
        matricula_diario.registrar_nota_etapa(1)

        # Cenário: Entregar Etapa
        mudar_data(context, '20/07/2019')
        diario.entregar_etapa(1)


def step_cadastros_feature_006(context):
    matricula_periodo = MatriculaPeriodo.objects.get(aluno__matricula='20191101010001', ano_letivo__ano=2019, periodo_letivo=1)
    if matricula_periodo.situacao.pk == SituacaoMatriculaPeriodo.MATRICULADO:
        # Registrar Aula (em posse do registro)
        diario = diario_da_especializacao('POS.0003')
        professor = Professor.objects.get(vinculo__pessoa__nome='Servidor P')
        professordiario = ProfessorDiario.objects.get(diario=diario, professor=professor)
        Aula.objects.get_or_create(
            etapa=1,
            quantidade=60,
            data=datetime.strptime('20/03/2019', '%d/%m/%Y'),
            conteudo='Apresentação da disciplina',
            professor_diario=professordiario,
        )

        # Lançar Nota (em posse do registro)
        matricula_diario = MatriculaDiario.objects.get(diario=diario, matricula_periodo=matricula_periodo)
        configuracao = ConfiguracaoAvaliacao.objects.get(diario=diario, etapa=1)
        item_configuracao_avaliacao = ItemConfiguracaoAvaliacao.objects.get(configuracao_avaliacao=configuracao)
        nota_avaliacao = NotaAvaliacao.objects.get(matricula_diario=matricula_diario, item_configuracao_avaliacao=item_configuracao_avaliacao)
        nota_avaliacao.nota = 80
        nota_avaliacao.save()
        matricula_diario.registrar_nota_etapa(1)

        # Cenário: Fechar Período
        diarios = Diario.objects.filter(turma=matricula_periodo.turma)
        for diario in diarios:
            diario.entregar_etapa(1)
            diario.entregar_etapa(5)
        matricula_periodo.fechar_periodo_letivo(False)
        for diario in diarios:
            diario.fechar()


def step_cadastros_feature_008(context):
    if not ConfiguracaoPedidoMatricula.objects.filter(descricao='Renovação 2019.2').exists():
        from comum.models import Ano

        # Cenário: Gerar Turmas e Diários
        ano = Ano.objects.get(ano=2019)
        turno = Turno.objects.get(descricao='Matutino')
        curso = CursoCampus.objects.get(descricao='Especialização em Educação Profissional')
        matriz = Matriz.objects.get(descricao='Especialização em Educação Profissional')
        horariocampus = HorarioCampus.objects.get(descricao='Horário Padrão [Aula 45min]')
        calendario_academico = CalendarioAcademico.objects.get(descricao='Calendário Acadêmico Especialização 2019.2')
        componentes = ComponenteCurricular.objects.filter(componente__sigla__in=['POS.0003', 'POS.0002'], matriz=matriz)

        Turma.gerar_turmas(
            ano,
            2,
            {1: turno, 2: turno},
            {1: 10, 2: 10},
            {1: 1, 2: 1},
            curso,
            matriz,
            horariocampus,
            calendario_academico,
            componentes,
            False,
            None,
            True,
        )

        # Cenário: Configurar Renovação de Matrícula
        configuracao_pedido_matricula, _ = ConfiguracaoPedidoMatricula.get_or_create(
            descricao='Renovação 2019.2',
            ano_letivo=ano,
            periodo_letivo=2,
            data_inicio=datetime.strptime('21/07/2019', '%d/%m/%Y'),
            data_fim=datetime.strptime('21/07/2019', '%d/%m/%Y'),
        )
        diretoria = Diretoria.objects.get(setor__sigla='DIAC/CEN')
        configuracao_pedido_matricula.diretorias.add(diretoria)
        configuracao_pedido_matricula.cursos.add(curso)

        # Cenário: Realizar Pedido de Matrícula
        mudar_data(context, '21/07/2019')
        turma = Turma.objects.get(ano_letivo=ano, periodo_letivo=2, periodo_matriz=2, curso_campus=curso, matriz=matriz)
        mp = MatriculaPeriodo.objects.get(aluno__matricula='20191101010001', ano_letivo=ano, periodo_letivo=2, periodo_matriz=2)
        # `objects.get_or_create`, não o do `ModelPlus`: aquele preenche o primeiro TextField
        # nulo do modelo com um texto de rascunho, e em `PedidoMatricula` esse campo é
        # `motivo_impedimento_matricula_vinculo` — que desde 2fda1727d7 marca o pedido como já
        # processado em `ConfiguracaoPedidoMatricula.is_processado()`.
        pm = PedidoMatricula.objects.get_or_create(
            matricula_periodo_id=mp.id, configuracao_pedido_matricula_id=configuracao_pedido_matricula.id, turma_id=turma.id
        )[0]

        for diario in turma.diario_set.all():
            pedido_matricula_diario = PedidoMatriculaDiario()
            pedido_matricula_diario.diario = diario
            pedido_matricula_diario.pedido_matricula = pm
            pedido_matricula_diario.save()

        # Cenário: Processar Pedidos de Matrícula
        mudar_data(context, '22/07/2019')
        pm.matricular_na_turma()
        qs_pedido_matricula_diario = pm.pedidomatriculadiario_set.filter(diario__turma=turma)
        for pedido_matricula_diario in qs_pedido_matricula_diario:
            pedido_matricula_diario.matricular_no_diario(PedidoMatriculaDiario.MOTIVO_PERIODIZADO)


def step_matricula_aluno_credito(context):
    from comum.models import Ano, Raca
    from rh.models import PessoaFisica

    ingresso = FormaIngresso.objects.get_or_create(
        descricao='Ampla Concorrência', ativo=True, classificacao_censup=FormaIngresso.ENEM, classificacao_educacenso=4
    )[0]
    cidade = Cidade.objects.get_or_create(nome='Natal')[0]

    pessoa_fisica = PessoaFisica()
    pessoa_fisica.cpf = CPF_ALUNA_LICENCIATURA
    pessoa_fisica.nome_registro = 'Maria Pereira'
    pessoa_fisica.sexo = 'F'
    pessoa_fisica.nascimento_data = datetime.strptime('11/11/1991', '%d/%m/%Y')
    pessoa_fisica.save()

    ano = Ano.objects.get(ano=2019)
    curso = CursoCampus.objects.get(descricao=NOME_CURSO_LICENCIATURA)
    matriz = Matriz.objects.get(descricao=NOME_CURSO_LICENCIATURA)

    aluno = cadastrar_aluno(pessoa_fisica, cidade, ano, ingresso, curso, matriz)
    definir_dados_vinculo(aluno, raca=Raca.objects.get(descricao='Parda'))
    matricular_aluno(aluno, ano, curso, matriz)


def step_cadastro_banco(context):
    from rh.models import Banco

    Banco.objects.get_or_create(codigo='001', sigla='BB', nome='Banco do Brasil')


def step_cadastro_tipo_componente(context):
    componente = {
        'descricao': 'LIC',
    }
    TipoComponente.objects.get_or_create(**componente)


def step_cadastro_componente(context):
    tipo = TipoComponente.objects.filter(descricao='POS').first()
    diretoria = Diretoria.objects.filter(setor__sigla='DIAC/CEN').first()
    nivel = NivelEnsino.objects.filter(descricao='Pós-graduação').first()

    componente = {
        'descricao': 'Didática da Educação Profissional',
        'descricao_historico': 'Didática da Educação Profissional',
        'abreviatura': 'DEP',
        'tipo': tipo,
        'diretoria': diretoria,
        'nivel_ensino': nivel,
        'ativo': True,
        'ch_hora_relogio': 45,
        'ch_hora_aula': 60,
        'ch_qtd_creditos': 3,
    }
    Componente.objects.get_or_create(**componente)

    componente = {
        'descricao': 'Elaboração do Trabalho de Conclusão de Curso',
        'descricao_historico': 'Elaboração do Trabalho de Conclusão de Curso',
        'abreviatura': 'ETCC',
        'tipo': tipo,
        'diretoria': diretoria,
        'nivel_ensino': nivel,
        'ativo': True,
        'ch_hora_relogio': 30,
        'ch_hora_aula': 45,
        'ch_qtd_creditos': 0,
    }
    Componente.objects.get_or_create(**componente)

    tipo = TipoComponente.objects.filter(descricao='LIC').first()
    nivel = NivelEnsino.objects.filter(descricao='Graduação').first()

    componente = {
        'descricao': 'Matemática Aplicada à Geografia',
        'descricao_historico': 'Matemática Aplicada à Geografia',
        'abreviatura': 'MAG',
        'tipo': tipo,
        'diretoria': diretoria,
        'nivel_ensino': nivel,
        'ativo': True,
        'ch_hora_relogio': 30,
        'ch_hora_aula': 40,
        'ch_qtd_creditos': 2,
    }
    Componente.objects.get_or_create(**componente)

    componente = {
        'descricao': 'Estatística Básica',
        'descricao_historico': 'Estatística Básica',
        'abreviatura': 'EB',
        'tipo': tipo,
        'diretoria': diretoria,
        'nivel_ensino': nivel,
        'ativo': True,
        'ch_hora_relogio': 30,
        'ch_hora_aula': 40,
        'ch_qtd_creditos': 2,
    }
    Componente.objects.get_or_create(**componente)

    componente = {
        'descricao': 'Fundamentos da Educação',
        'descricao_historico': 'Fundamentos da Educação',
        'abreviatura': 'FE',
        'tipo': tipo,
        'diretoria': diretoria,
        'nivel_ensino': nivel,
        'ativo': True,
        'ch_hora_relogio': 60,
        'ch_hora_aula': 80,
        'ch_qtd_creditos': 4,
    }
    Componente.objects.get_or_create(**componente)

    componente = {
        'descricao': 'Elaboração de Material Didático em Geografia',
        'descricao_historico': 'Elaboração de Material Didático em Geografia',
        'abreviatura': 'EMDG',
        'tipo': tipo,
        'diretoria': diretoria,
        'nivel_ensino': nivel,
        'ativo': True,
        'ch_hora_relogio': 60,
        'ch_hora_aula': 80,
        'ch_qtd_creditos': 4,
    }
    Componente.objects.get_or_create(**componente)


def step_cadastro_componente_curricular(context):
    matriz = Matriz.objects.get(descricao='Especialização em Educação Profissional')
    nucleo = Nucleo.objects.get(descricao='Formação')

    componente_curricular = {
        'matriz': matriz,
        'componente': Componente.objects.get(abreviatura='DEP'),
        'periodo_letivo': 1,
        'tipo': ComponenteCurricular.TIPO_REGULAR,
        'qtd_avaliacoes': 1,
        'nucleo': nucleo,
        'ch_presencial': 45,
        'ch_pratica': 0,
        'tipo_modulo': 1,
    }
    ComponenteCurricular.objects.get_or_create(**componente_curricular)

    componente_curricular = {
        'matriz': matriz,
        'componente': Componente.objects.get(abreviatura='ETCC'),
        'periodo_letivo': 2,
        'tipo': ComponenteCurricular.TIPO_TRABALHO_CONCLUSAO_CURSO,
        'qtd_avaliacoes': 1,
        'nucleo': nucleo,
        'ch_presencial': 30,
        'ch_pratica': 0,
        'tipo_modulo': 2,
    }
    ComponenteCurricular.objects.get_or_create(**componente_curricular)

    matriz = Matriz.objects.filter(descricao='Licenciatura em Geografia')
    if matriz.exists():
        matriz = matriz[0]

        componente_curricular = {
            'matriz': matriz,
            'componente': Componente.objects.get(abreviatura='EB'),
            'periodo_letivo': 2,
            'tipo': ComponenteCurricular.TIPO_REGULAR,
            'qtd_avaliacoes': 2,
            'nucleo': nucleo,
            'ch_presencial': 30,
            'ch_pratica': 0,
        }
        ComponenteCurricular.objects.get_or_create(**componente_curricular)

        componente_curricular = {
            'matriz': matriz,
            'componente': Componente.objects.get(abreviatura='FE'),
            'periodo_letivo': 2,
            'tipo': ComponenteCurricular.TIPO_REGULAR,
            'qtd_avaliacoes': 2,
            'nucleo': nucleo,
            'ch_presencial': 60,
            'ch_pratica': 0,
        }
        ComponenteCurricular.objects.get_or_create(**componente_curricular)

        componente_curricular = {
            'matriz': matriz,
            'componente': Componente.objects.get(abreviatura='EMDG'),
            'optativo': True,
            'tipo': ComponenteCurricular.TIPO_REGULAR,
            'qtd_avaliacoes': 2,
            'nucleo': nucleo,
            'ch_presencial': 60,
            'ch_pratica': 0,
        }
        ComponenteCurricular.objects.get_or_create(**componente_curricular)


def step_cadastro_turno(context):
    Turno.objects.get_or_create(id='2', descricao='Vespertino')
    Turno.objects.get_or_create(id='3', descricao='Matutino')
    Turno.objects.get_or_create(id='5', descricao='EAD')
    Turno.objects.get_or_create(id='6', descricao='Diurno')


def step_cadastro_calendario_academico(context):
    from comum.models import Ano
    from rh.models import UnidadeOrganizacional

    uo = UnidadeOrganizacional.objects.suap().get(sigla='CEN')
    diretoria = Diretoria.objects.get(setor__sigla='DIAC/CEN')
    ano_letivo = Ano.objects.get(ano=2019)
    calendario_academico = {
        'descricao': 'Calendário Acadêmico Especialização 2019.2',
        'uo': uo,
        'diretoria': diretoria,
        'tipo': CalendarioAcademico.TIPO_SEMESTRAL,
        'ano_letivo': ano_letivo,
        'periodo_letivo': 2,
        'data_inicio': datetime.strptime('22/07/2019', '%d/%m/%Y'),
        'data_fim': datetime.strptime('29/12/2019', '%d/%m/%Y'),
        'data_fechamento_periodo': datetime.strptime('30/12/2019', '%d/%m/%Y'),
        'qtd_etapas': CalendarioAcademico.QTD_ETAPA_1,
        'data_inicio_etapa_1': datetime.strptime('22/07/2019', '%d/%m/%Y'),
        'data_fim_etapa_1': datetime.strptime('29/12/2019', '%d/%m/%Y'),
    }
    CalendarioAcademico.objects.get_or_create(**calendario_academico)

    calendario_academico = {
        'descricao': 'Calendário Acadêmico Licenciatura 2019.2',
        'uo': uo,
        'diretoria': diretoria,
        'tipo': CalendarioAcademico.TIPO_SEMESTRAL,
        'ano_letivo': ano_letivo,
        'periodo_letivo': 2,
        'data_inicio_espaco_pedagogico': datetime.strptime('22/07/2019', '%d/%m/%Y'),
        'data_fim_espaco_pedagogico': datetime.strptime('26/07/2019', '%d/%m/%Y'),
        'data_inicio': datetime.strptime('29/07/2019', '%d/%m/%Y'),
        'data_fim': datetime.strptime('13/12/2019', '%d/%m/%Y'),
        'data_inicio_trancamento': datetime.strptime('29/07/2019', '%d/%m/%Y'),
        'data_fim_trancamento': datetime.strptime('02/10/2019', '%d/%m/%Y'),
        'data_inicio_certificacao': datetime.strptime('11/07/2019', '%d/%m/%Y'),
        'data_fim_certificacao': datetime.strptime('15/07/2019', '%d/%m/%Y'),
        'data_inicio_prova_final': datetime.strptime('16/12/2019', '%d/%m/%Y'),
        'data_fim_prova_final': datetime.strptime('20/12/2019', '%d/%m/%Y'),
        'data_fechamento_periodo': datetime.strptime('31/12/2019', '%d/%m/%Y'),
        'qtd_etapas': CalendarioAcademico.QTD_ETAPA_2,
        'data_inicio_etapa_1': datetime.strptime('29/07/2019', '%d/%m/%Y'),
        'data_fim_etapa_1': datetime.strptime('29/09/2019', '%d/%m/%Y'),
        'data_inicio_etapa_2': datetime.strptime('30/09/2019', '%d/%m/%Y'),
        'data_fim_etapa_2': datetime.strptime('13/12/2019', '%d/%m/%Y'),
    }
    CalendarioAcademico.objects.get_or_create(**calendario_academico)


def step_cadastro_predio(context):
    from comum.models import Predio
    from rh.models import UnidadeOrganizacional

    uo = UnidadeOrganizacional.objects.suap().get(sigla='CEN')
    Predio.objects.get_or_create(nome='Bloco A', uo=uo, ativo=True)


def step_cadastro_sala(context):
    from comum.models import Predio, Sala

    predio = Predio.objects.get(nome='Bloco A')
    Sala.objects.get_or_create(nome='Sala 101', predio=predio, ativa=True)


def step_configuracao_diario(context):
    from comum.models import Sala, Vinculo

    diario = diario_da_especializacao('POS.0003')
    diario.local_aula = Sala.objects.get(nome='Sala 101')
    diario.save()
    vinculo = Vinculo.objects.get(pessoa__nome='Servidor P')
    professor = Professor.objects.get_or_create(vinculo=vinculo)[0]
    professor.vinculo.user.groups.add(Group.objects.get(name='Professor'))
    professordiario = {
        'diario': diario,
        'professor': professor,
        'tipo': TipoProfessorDiario.objects.get(descricao='Principal'),
        'percentual_ch': 100,
        'data_inicio_etapa_1': datetime.strptime('20/03/2019', '%d/%m/%Y'),
        'data_fim_etapa_1': datetime.strptime('25/07/2019', '%d/%m/%Y'),
        'data_inicio_etapa_final': datetime.strptime('19/07/2019', '%d/%m/%Y'),
        'data_fim_etapa_final': datetime.strptime('26/07/2019', '%d/%m/%Y'),
    }
    ProfessorDiario.objects.get_or_create(**professordiario)
    step_definicao_horario_aula_diario(None, '2M1,2M2', diario.pk)


def step_definicao_horario_aula_diario(context, horarios, diario):
    diario = Diario.objects.get(pk=diario)

    horarios = horarios.split(',')
    for horario in horarios:
        turno = horario[1] == 'N' and 1 or horario[1] == 'V' and 2 or horario[1] == 'M' and 3 or horario[1] == 'E' and 5 or horario[1] == 'D' and 6
        horario_aula = HorarioAula.objects.get(turno=Turno.objects.get(pk=turno), numero=horario[2], horario_campus=diario.horario_campus)
        HorarioAulaDiario.objects.get_or_create(diario=diario, dia_semana=horario[0], horario_aula=horario_aula)


def step_cadastro_raca(context):
    from comum.models import Raca

    Raca.objects.get_or_create(descricao='Parda', codigo_siape=4)
    Raca.objects.get_or_create(descricao='Preta', codigo_siape=6)
    Raca.objects.get_or_create(descricao='Branca', codigo_siape=1)
    Raca.objects.get_or_create(descricao='Indígena', codigo_siape=5)
    Raca.objects.get_or_create(descricao='Amarela', codigo_siape=3)
    Raca.objects.get_or_create(descricao='Não declarado', codigo_siape=9)


def cadastrar_aluno(pessoa_fisica, cidade, ano, ingresso, curso, matriz):
    from comum.models import User

    aluno = Aluno()
    aluno.periodo_atual = 1
    aluno.pessoa_fisica = pessoa_fisica
    aluno.estado_civil = 'Solteiro'
    aluno.nome_mae = 'Maria da Silva'
    aluno.logradouro = 'Rua abcd'
    aluno.numero = '123'
    aluno.bairro = 'qwer'
    aluno.cidade = cidade
    aluno.tipo_zona_residencial = '1'
    aluno.nacionalidade = 'Brasileira'
    aluno.naturalidade = cidade
    aluno.ano_letivo = ano
    aluno.periodo_letivo = 1
    aluno.turno = Turno.objects.get(descricao='Matutino')
    aluno.forma_ingresso = ingresso
    aluno.curso_campus = curso
    aluno.matriz = matriz
    aluno.situacao = SituacaoMatricula.objects.get(pk=SituacaoMatricula.MATRICULADO)
    aluno.ano_let_prev_conclusao = 2020
    prefixo = f'{aluno.ano_letivo}{aluno.periodo_letivo}{aluno.curso_campus.codigo}'
    aluno.matricula = SequencialMatricula.proximo_numero(prefixo)
    user = User.objects.get_or_create(username=aluno.matricula, eh_aluno=True)[0]
    user.set_password('123')
    user.is_staff = True
    user.groups.add(Group.objects.get(name='Aluno'))
    user.save()
    aluno.save(sync_user=False)

    return aluno


def definir_dados_vinculo(aluno, **campos):
    """Grava no vínculo do aluno campos que antes moravam em `PessoaFisica` (raça, e-mail pessoal).

    `cadastrar_aluno` salva com `sync_user=False`, que pula justamente o trecho de
    `Aluno.save()` que cria o Vínculo — logo ele ainda não existe aqui. O save() extra o
    materializa; sem isso os campos se perdiam em silêncio e o aluno chegava aos testes sem
    e-mail pessoal (o 2FA de dado bancário, que exige esse e-mail, barrava a tela).
    """
    if aluno.get_vinculo() is None:
        aluno.save()
    vinculo = aluno.get_vinculo()
    for campo, valor in campos.items():
        setattr(vinculo, campo, valor)
    vinculo.save(update_fields=list(campos))
    return vinculo


def matricular_aluno(aluno, ano, curso, matriz):
    hsm = HistoricoSituacaoMatricula()
    hsm.aluno = aluno
    hsm.situacao = aluno.situacao
    hsm.data = datetime.now()
    hsm.save()

    matricula_periodo = MatriculaPeriodo()
    matricula_periodo.aluno = aluno
    matricula_periodo.ano_letivo = aluno.ano_letivo
    matricula_periodo.periodo_letivo = aluno.periodo_letivo
    matricula_periodo.periodo_matriz = 1
    matricula_periodo.situacao = SituacaoMatriculaPeriodo.objects.get(pk=SituacaoMatriculaPeriodo.MATRICULADO)
    matricula_periodo.save()

    hsmp = HistoricoSituacaoMatriculaPeriodo()
    hsmp.matricula_periodo = matricula_periodo
    hsmp.situacao = matricula_periodo.situacao
    hsmp.data = aluno.data_matricula
    hsmp.save()


def step_configurar_avaliacao_conceito(context):
    settings.REPRESENTACAO_CONCEITUAL = {'A': 100, 'B': 80, 'C': 60, 'D': 0}


def step_cadastro_turma_diario_conceito(context):
    from comum.models import Ano, Raca, Sala, Vinculo
    from rh.models import PessoaFisica, UnidadeOrganizacional

    # Turma
    uo = UnidadeOrganizacional.objects.suap().get(sigla='CEN')
    turno = Turno.objects.get(descricao='Matutino')
    ano_letivo = Ano.objects.get(ano=2019)
    horariocampus = HorarioCampus.objects.get(descricao='Horário Padrão [Aula 45min]', uo=uo, ativo=True, eh_padrao=True)
    calendario = CalendarioAcademico.objects.get(
        descricao='Calendário Acadêmico Especialização 2019.1',
        ano_letivo=ano_letivo,
        periodo_letivo=1,
    )

    curso = CursoCampus.objects.get(descricao='Especialização em Educação Profissional [CONCEITO]')
    matriz = Matriz.objects.get(descricao='Especialização em Educação Profissional [CONCEITO]')
    componentes = ComponenteCurricular.objects.filter(componente__sigla__in=['POS.0003', 'POS.0001'], matriz=matriz)
    if not Turma.objects.filter(ano_letivo=ano_letivo, periodo_letivo=1, curso_campus=curso, matriz=matriz).exists():
        Turma.gerar_turmas(ano_letivo, 1, {1: turno}, {1: 10}, {1: 1}, curso, matriz, horariocampus, calendario, componentes, False, None, True)

    # Diário
    diario = Diario.objects.get(componente_curricular__componente__sigla='POS.0001', turma__matriz_id=matriz.id, turma__curso_campus_id=curso.id)
    diario.local_aula = Sala.objects.get(nome='Sala 101')
    diario.save()
    vinculo = Vinculo.objects.get(pessoa__nome='Servidor P')
    professor = Professor.objects.get(vinculo=vinculo)
    professordiario = {
        'diario': diario,
        'professor': professor,
        'tipo': TipoProfessorDiario.objects.get(descricao='Principal'),
        'percentual_ch': 100,
        'data_inicio_etapa_1': datetime.strptime('20/03/2019', '%d/%m/%Y'),
        'data_fim_etapa_1': datetime.strptime('25/07/2019', '%d/%m/%Y'),
        'data_inicio_etapa_final': datetime.strptime('19/07/2019', '%d/%m/%Y'),
        'data_fim_etapa_final': datetime.strptime('26/07/2019', '%d/%m/%Y'),
    }
    ProfessorDiario.objects.get_or_create(**professordiario)
    step_definicao_horario_aula_diario(None, '2M1,2M2', diario.pk)

    ingresso = FormaIngresso.objects.get(
        descricao='Ampla Concorrência', ativo=True, classificacao_censup=FormaIngresso.ENEM, classificacao_educacenso=4
    )
    cidade = Cidade.objects.get(nome='Natal')

    # Efetuar matrícula institucional
    pessoa_fisica = PessoaFisica()
    pessoa_fisica.cpf = '001.001.001-71'
    pessoa_fisica.nome_registro = 'Ana da Silva'
    pessoa_fisica.sexo = 'F'
    pessoa_fisica.nascimento_data = datetime.strptime('10/10/1990', '%d/%m/%Y')
    pessoa_fisica.save()

    aluno = cadastrar_aluno(pessoa_fisica, cidade, ano_letivo, ingresso, curso, matriz)
    definir_dados_vinculo(aluno, raca=Raca.objects.get(descricao='Parda'), email_pessoal='ana.silva@email.com')
    matricular_aluno(aluno, ano_letivo, curso, matriz)

    pessoa_fisica2 = PessoaFisica()
    pessoa_fisica2.cpf = '002.002.002-32'
    pessoa_fisica2.nome_registro = 'Maria da Silva'
    pessoa_fisica2.sexo = 'F'
    pessoa_fisica2.nascimento_data = datetime.strptime('10/10/1990', '%d/%m/%Y')
    pessoa_fisica2.save()
    aluno2 = cadastrar_aluno(pessoa_fisica2, cidade, ano_letivo, ingresso, curso, matriz)
    definir_dados_vinculo(aluno2, raca=Raca.objects.get(descricao='Parda'), email_pessoal='maria.silva@email.com')
    matricular_aluno(aluno2, ano_letivo, curso, matriz)

    # Cenário: Matricular em Turma
    turma = Turma.objects.get(ano_letivo=ano_letivo, periodo_letivo=1, periodo_matriz=1, curso_campus=curso, matriz=matriz)
    mp = MatriculaPeriodo.objects.filter(aluno__curso_campus=curso, ano_letivo=ano_letivo, periodo_letivo=1, periodo_matriz=1)

    turma.matricular_alunos(mp)


def step_cadastro_area_curso_formacao_superior(context):
    AreaCursoFormacaoSuperior.objects.get_or_create(
        codigo_cine='0111C01',
        codigo_area_detalhada='0111',
        codigo_area_especifica='011',
        codigo_area_geral='01',
        cine='Ciência da educação',
        area_detalhada='Ciência da educação',
        area_especifica='Educação',
        area_geral='Educação',
        ativo=True,
    )


def step_cadastro_curso_licenciatura(context) -> CursoCampus:
    """Replay ORM da funcionalidade 011: curso "Licenciatura em Geografia" (código 20101).

    Os mesmos valores que ``edu/tests/e2e/test_12_credito.py`` grava pela interface — e é de
    propósito que existam dois caminhos para o mesmo dado. Nos e2e o cadastro **é** o que se
    testa, e a cadeia 12→13→14 roda numa invocação só, em ordem de arquivo. A rodada de doc
    (``edu/tests/doc``) é outra invocação, não coleta os e2e e não documenta este cadastro:
    para ela o curso é pré-condição do ENADE, e pré-condição se semeia.

    Idempotente (``get_or_create`` em tudo, aluna guardada por CPF), porque a suíte não dá
    flush e o mesmo banco é reusado entre execuções.
    """
    from comum.models import Ano, Vinculo
    from edu.models import AreaCurso, ConfiguracaoAtividadeAprofundamento
    from rh.models import PessoaFisica

    step_cadastro_area_curso_formacao_superior(context)

    estrutura = EstruturaCurso.objects.get_or_create(
        descricao='Licenciatura',
        defaults={
            'ativo': True,
            'tipo_avaliacao': EstruturaCurso.TIPO_AVALIACAO_CREDITO,
            'qtd_minima_disciplinas': 1,
            'numero_disciplinas_superior_periodo': 2,
            'qtd_max_periodos_subsequentes': 10,
            'numero_max_cancelamento_disciplina': 1,
            'criterio_avaliacao': EstruturaCurso.CRITERIO_AVALIACAO_NOTA,
            'media_aprovacao_sem_prova_final': 60,
            'media_evitar_reprovacao_direta': 20,
            'media_aprovacao_avaliacao_final': 60,
            'percentual_frequencia': 75,
            'ira': EstruturaCurso.IRA_PONDERADA_POR_CH,
            'qtd_periodos_conclusao': 16,
            'qtd_max_reprovacoes_periodo': 0,
            'qtd_max_reprovacoes_disciplina': 0,
            'qtd_trancamento_voluntario': 2,
            'exige_periodo_ingresso_integralizado': True,
            'percentual_max_aproveitamento': 50,
            'numero_max_certificacoes': 4,
            'media_certificacao_conhecimento': 60,
        },
    )[0]

    ano = Ano.objects.get(ano=2019)
    matriz = Matriz.objects.get_or_create(
        descricao=NOME_CURSO_LICENCIATURA,
        defaults={
            'ano_criacao': ano,
            'periodo_criacao': 1,
            'nivel_ensino': NivelEnsino.objects.get(descricao='Graduação'),
            'natureza_participacao': NaturezaParticipacao.objects.get_or_create(descricao='Presencial')[0],
            'ativo': True,
            'data_inicio': datetime.strptime('15/03/2019', '%d/%m/%Y'),
            'qtd_periodos_letivos': 8,
            'estrutura': estrutura,
            'ch_componentes_obrigatorios': 1920,
            'ch_componentes_optativos': 180,
            'ch_componentes_eletivos': 0,
            'ch_seminarios': 244,
            'ch_pratica_profissional': 800,
            'ch_componentes_tcc': 0,
            'exige_tcc': True,
            'ch_atividades_complementares': 0,
            'ch_atividades_aprofundamento': 200,
            'ch_atividades_extensao': 0,
            'ch_pratica_como_componente': 0,
            'ch_visita_tecnica': 0,
            'configuracao_atividade_aprofundamento': ConfiguracaoAtividadeAprofundamento.objects.get_or_create(descricao='ATPA Licenciaturas 2018')[
                0
            ],
            'periodo_minimo_estagio_obrigatorio': 1,
        },
    )[0]

    # `exige_enade` + `area_curso_formacao_superior` (o código CINE) são o que a convocação
    # filtra; sem os dois o curso simplesmente não entra na lista de convocados.
    curso = CursoCampus.objects.get_or_create(
        codigo=CODIGO_CURSO_LICENCIATURA,
        defaults={
            'descricao': NOME_CURSO_LICENCIATURA,
            'descricao_historico': NOME_CURSO_LICENCIATURA,
            'formacao_de_professores': True,
            'ano_letivo': ano,
            'periodo_letivo': 1,
            'data_inicio': datetime.strptime('15/03/2019', '%d/%m/%Y'),
            'quantidade_vagas': 10,
            'coordenador': Vinculo.objects.filter(user__username='100005').first(),
            'ativo': True,
            'modalidade': Modalidade.objects.get(descricao='Licenciatura'),
            'area_curso_formacao_superior': AreaCursoFormacaoSuperior.objects.get(codigo_cine='0111C01'),
            'area': AreaCurso.objects.get_or_create(descricao='Ciências Humanas')[0],
            'periodicidade': CursoCampus.PERIODICIDADE_SEMESTRAL,
            'diretoria': Diretoria.objects.get(setor__sigla='DIAC/CEN'),
            'exige_enade': True,
            'exige_colacao_grau': True,
            'emite_diploma': True,
            'fator_esforco_curso': 1,
            'titulo_certificado_masculino': 'Licenciado em Geografia',
            'titulo_certificado_feminino': 'Licenciada em Geografia',
        },
    )[0]
    MatrizCurso.objects.get_or_create(matriz=matriz, curso_campus=curso)

    # A aluna é o alvo da convocação; `step_matricula_aluno_credito` cria a PessoaFisica sem
    # `get_or_create`, então o guard pelo CPF é o que torna esta função re-executável.
    if not PessoaFisica.objects.filter(cpf=CPF_ALUNA_LICENCIATURA).exists():
        step_matricula_aluno_credito(context)

    return curso
