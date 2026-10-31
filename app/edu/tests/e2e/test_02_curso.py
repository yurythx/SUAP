"""Fluxo 002: configurar curso — apoio, estrutura, matriz, componente e curso.

Segundo elo: a matriz curricular é o contrato do curso (o que o aluno tem de cursar) e o
vínculo componente↔matriz é o que gera diário lá na frente.

Os nomes cadastrados aqui levam sufixo aleatório de propósito. O replay ORM do seed já
criou os cadastros com os nomes da ``.feature`` (Presencial, POS, Formação, Educação,
"Especialização e Aperfeiçoamento"), e quase todos têm descrição única — repetir o nome
exato do behave daria erro de duplicidade, não cobertura. O que se cobre é o caminho do
formulário, que é o mesmo.
"""

from uuid import uuid4

import pytest
from playwright.sync_api import expect

from djtools.e2e_fixtures import abrir_popup, escolher_autocomplete, mensagem_de_sucesso
from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

DATA = '10/03/2019'

# (nome do admin, modelo, campos extras além da descrição)
CADASTROS_DE_APOIO = [
    ('naturezaparticipacao', 'NaturezaParticipacao', []),
    ('tipocomponente', 'TipoComponente', []),
    ('nucleo', 'Nucleo', []),
    ('areacapes', 'AreaCapes', []),
    ('tipoatividadecomplementar', 'TipoAtividadeComplementar', [('Modalidades de Ensino', 'autocomplete multiplo', 'Especialização')]),
]


@pytest.fixture
def sufixo():
    """Sufixo aleatório: a suíte e2e nunca dá flush, então nome fixo colide na 2ª run."""
    return uuid4().hex[:6].upper()


@pytest.fixture
def matriz_conceito(edu_seed):
    """Matriz "[CONCEITO]" — a réplica que o replay cria e mais ninguém usa.

    Serve de alvo para os testes que ALTERAM a matriz (vincular componente): mexer na
    matriz "Especialização em Educação Profissional" mudaria a carga horária exigida do
    curso que os módulos 05→09 percorrem.
    """
    from edu.models import Matriz

    return Matriz.objects.get(descricao='Especialização em Educação Profissional [CONCEITO]')


@pytest.mark.parametrize(('nome_admin', 'modelo', 'extras'), CADASTROS_DE_APOIO)
def test_cadastro_de_apoio(logado_edu, sufixo, nome_admin, modelo, extras):
    """Os cadastros de apoio da matriz e do curso, um caso por tela.

    São formulários de descrição (mais, num caso, a modalidade de ensino), mas cada um é uma
    permissão e um menu diferentes — a regressão típica é a tela sumir do admin, não o campo
    mudar. Todos entregam a mensagem padrão do ``ModelAdminPlus``.
    """
    from django.apps import apps

    descricao = f'E2E {modelo} {sufixo}'
    registros = apps.get_model('edu', modelo).objects.filter(descricao=descricao)
    try:
        tela = Tela(logado_edu('admin_academico')).ir(f'/admin/edu/{nome_admin}/add/')
        tela.preencher('Descrição', 'texto', descricao)
        tela.preencher_formulario(extras)
        tela.clicar_botao('Salvar')

        tela.sucesso('Cadastro realizado com sucesso.')
        assert registros.exists(), f'{modelo}: a UI disse que salvou, mas não persistiu'
    finally:
        registros.delete()


def test_cadastra_configuracao_de_aacc(logado_edu, sufixo):
    """Configuração de AACC = o teto de atividades complementares que a matriz aceita.

    Tem duas etapas e a própria mensagem do SUAP diz isso ("Adicione os tipos de atividades
    complementares"): a configuração nasce vazia e só serve depois de receber os tipos, cada
    um com seu fator de conversão.
    """
    from edu.models import ConfiguracaoAtividadeComplementar, TipoAtividadeComplementar

    descricao = f'Configuração E2E {sufixo}'
    configuracoes = ConfiguracaoAtividadeComplementar.objects.filter(descricao=descricao)
    # O replay ORM do seed não cria tipo de atividade complementar (a `.feature` 002 o cria
    # pela tela, e o replay só reproduz o que os fluxos seguintes precisam), então o tipo
    # vem por ORM — quem cobre o cadastro dele pela interface é `test_cadastro_de_apoio`.
    tipo = TipoAtividadeComplementar.objects.get_or_create(descricao=f'Atividade E2E {sufixo}')[0]
    try:
        tela = Tela(logado_edu('admin_academico')).ir('/admin/edu/configuracaoatividadecomplementar/add/')
        tela.preencher('Descrição', 'texto', descricao)
        tela.clicar_botao('Salvar')
        tela.sucesso('Configuração cadastrada com sucesso.')

        configuracao = configuracoes.get()
        tela.ir(f'/edu/configuracaoatividadecomplementar/{configuracao.pk}/')
        # A aba precisa ser clicada: o painel dela nasce oculto e o botão dentro dele é
        # invisível para o Playwright até a aba virar a ativa.
        tela.clicar_aba('Atividades Acadêmicas')
        tela.clicar_botao('Adicionar Tipo de Atividade Complementar')
        popup = tela.popup()
        popup.preencher('Tipo', 'lista', tipo.descricao)
        popup.preencher('Fator de conversão (Peso)', 'texto', '1')
        popup.salvar_no_popup('Salvar')

        tela.sucesso('Atividade acadêmica cadastrada com sucesso.')
        assert configuracao.itemconfiguracaoatividadecomplementar_set.exists(), 'configuração sem tipo de atividade não limita nada'
    finally:
        configuracoes.delete()
        TipoAtividadeComplementar.objects.filter(pk=tipo.pk).delete()


def test_cadastra_estrutura_de_curso(logado_edu, sufixo):
    """A estrutura de curso é o regulamento: o que aprova, o que reprova, o que retém.

    Transcreve a tabela da funcionalidade 002 (regime seriado, critério nota). É o
    formulário mais longo do módulo e o que define ``Diario.get_situacao`` lá na frente.
    """
    from edu.models import EstruturaCurso

    descricao = f'Especialização E2E {sufixo}'
    estruturas = EstruturaCurso.objects.filter(descricao=descricao)
    try:
        tela = Tela(logado_edu('admin_academico')).ir('/admin/edu/estruturacurso/add/')
        tela.preencher_formulario(
            [
                ('Descrição', 'texto', descricao),
                ('Está Ativa', 'checkbox', 'marcar'),
                ('Tipo de Avaliação', 'radio', 'Seriado'),
                ('Número máximo de reprovações para aprovação por dependência', 'texto', '10'),
                ('Critério de Avaliação', 'radio', 'Nota'),
                ('Média para passar sem prova final', 'texto', '60'),
                ('Média para não reprovar direto', 'texto', '20'),
                ('Média para aprovação após avaliação final', 'texto', '60'),
                ('Percentual Mínimo de Frequência', 'texto', '75'),
                ('Forma de Cálculo', 'radio', 'Média dos componentes pela carga horária dos componentes'),
                ('Número Máximo de Matrículas em Períodos', 'texto', '4'),
                ('Número Máximo de Reprovações no Mesmo Período', 'texto', '0'),
                ('Número Máximo de Reprovações na Mesma Disciplina', 'texto', '0'),
                ('Número máximo de trancamentos voluntários', 'texto', '2'),
                ('Exige integralização do período de ingresso', 'checkbox', 'marcar'),
                ('Número Máximo de Certificações por Período', 'texto', '4'),
                ('Média para Certificação', 'texto', '60'),
            ]
        )
        tela.clicar_botao('Salvar')

        tela.sucesso('Cadastro realizado com sucesso.')
        estrutura = estruturas.get()
        assert estrutura.criterio_avaliacao == EstruturaCurso.CRITERIO_AVALIACAO_NOTA, 'critério de avaliação não gravado'
    finally:
        estruturas.delete()


def test_cadastra_matriz_curricular(logado_edu, sufixo):
    """A matriz declara a carga horária exigida por tipo de componente.

    O PPP é upload obrigatório na tela; reusa o ``arquivo.pdf`` que o behave já mantém em
    ``djtools/new_tests/files/``. A mensagem de sucesso é a que diz o passo seguinte
    ("vincule os componentes"), coberto por ``test_vincula_componente_a_matriz``.
    """
    from edu.models import Matriz

    descricao = f'Matriz E2E {sufixo}'
    matrizes = Matriz.objects.filter(descricao=descricao)
    try:
        tela = Tela(logado_edu('admin_academico')).ir('/admin/edu/matriz/add/')
        tela.preencher_formulario(
            [
                ('Descrição', 'texto', descricao),
                ('Ano Criação', 'autocomplete', '2019'),
                ('Período Criação', 'lista', '1'),
                ('Nível de Ensino', 'autocomplete', 'Pós-graduação'),
                ('Natureza de participação', 'autocomplete', 'Presencial'),
                ('Ativa', 'checkbox', 'marcar'),
                ('Data de início', 'data', '15/03/2019'),
                ('PPP', 'arquivo', 'arquivo.pdf'),
                ('Quantidade de Períodos Letivos', 'lista', '2'),
                ('Estrutura de curso', 'autocomplete', 'Especialização e Aperfeiçoamento'),
                # Todas as cargas horárias são obrigatórias, mesmo zeradas — é a soma delas
                # que o SUAP usa como carga horária total exigida da matriz.
                ('Componentes obrigatórios', 'texto', '90'),
                ('Componentes optativos', 'texto', '0'),
                ('Componentes eletivos', 'texto', '0'),
                ('Componentes de extensão', 'texto', '0'),
                ('Seminários', 'texto', '0'),
                ('Prática Profissional', 'texto', '0'),
                ('Trabalho de Conclusão de Curso', 'texto', '30'),
                ('Carga horária total de atividades de extensão', 'texto', '0'),
                ('Carga horária de extensão em outros componentes', 'texto', '0'),
                ('Atividades complementares', 'texto', '0'),
                ('Atividades Teórico-Práticas de Aprofundamento', 'texto', '0'),
                ('Prática como Componente Curricular', 'texto', '0'),
                ('Visita Técnica/Aula de Campo', 'texto', '0'),
                ('Exige TCC', 'checkbox', 'marcar'),
            ]
        )
        tela.clicar_botao('Salvar')

        tela.sucesso('Matriz cadastrada com sucesso.')
        assert matrizes.exists(), 'a UI disse que salvou, mas a matriz não persistiu'
    finally:
        matrizes.delete()


def test_replica_matriz_e_curso(logado_edu, matriz_conceito, sufixo):
    """Replicar é como o SUAP cria a variante de uma matriz/curso já em uso.

    É o caminho da funcionalidade 002 para a avaliação por conceito: replica a matriz,
    replica o curso e marca os componentes como "Avaliação por Conceito". A réplica com os
    nomes do behave já existe (o replay a criou, e é ela que ``test_10_conceito`` usa), então
    aqui se replica de novo com sufixo — o que se verifica é que a réplica sai com os
    componentes curriculares da origem, que é o ponto todo da função.
    """
    from edu.models import CursoCampus, Matriz

    descricao = f'Matriz Replicada E2E {sufixo}'
    codigo = f'8{uuid4().int % 10**4:04d}'
    replicas = Matriz.objects.filter(descricao=descricao)
    cursos = CursoCampus.objects.filter(codigo=codigo)
    try:
        tela = Tela(logado_edu('admin_academico')).ir(f'/edu/matriz/{matriz_conceito.pk}/replicar/')
        tela.preencher('Descrição', 'texto', descricao)
        tela.clicar_botao('Replicar Matriz')
        tela.sucesso('Matriz replicada com sucesso.')

        replica = replicas.get()
        assert replica.componentecurricular_set.count() == matriz_conceito.componentecurricular_set.count(), (
            'a réplica não trouxe os componentes curriculares da matriz de origem'
        )

        curso_origem = CursoCampus.objects.get(codigo='20202')
        tela.ir(f'/edu/cursocampus/{curso_origem.pk}/')
        tela.clicar_botao('Replicar Curso')
        popup = tela.popup()
        popup.preencher('Coordenador', 'autocomplete', '100005')
        popup.preencher('Código', 'texto', codigo)
        popup.preencher('Diretoria', 'lista', 'DIAC/CEN')
        popup.salvar_no_popup('Replicar Curso')

        tela.sucesso('Curso replicado com sucesso.')
        assert cursos.exists(), 'curso replicado não persistiu'
    finally:
        cursos.delete()
        replicas.delete()


def test_cadastra_componente(logado_edu, sufixo):
    """Componente é o molde da disciplina: carga horária, nível e diretoria."""
    from edu.models import Componente

    descricao = f'Metodologia Científica {sufixo}'
    page = logado_edu('admin_academico')
    try:
        page.goto('/admin/edu/componente/add/')
        page.fill('input[name=descricao]', descricao)
        page.fill('input[name=descricao_historico]', descricao)
        page.fill('input[name=abreviatura]', f'MC{sufixo[:4]}')
        escolher_autocomplete(page, 'tipo', 'POS')
        escolher_autocomplete(page, 'diretoria', 'DIAC/CEN')
        escolher_autocomplete(page, 'nivel_ensino', 'Pós-graduação')
        page.fill('input[name=ch_hora_relogio]', '45')
        page.fill('input[name=ch_hora_aula]', '60')
        page.fill('input[name=ch_qtd_creditos]', '3')
        page.click('input[name=_save]')

        mensagem_de_sucesso(page, 'Cadastro realizado com sucesso.')
        componente = Componente.objects.filter(descricao=descricao).first()
        assert componente is not None, 'a UI disse que salvou, mas não persistiu'
        assert componente.sigla, 'a sigla (POS.000N) é gerada no save e é o que identifica o componente nas telas'
    finally:
        # Sem flush entre runs, o componente sobraria e entraria nos autocompletes dos
        # outros testes (que buscam por nível de ensino, não por nome exato).
        Componente.objects.filter(descricao=descricao).delete()


@pytest.fixture
def componente_fora_da_matriz(matriz_conceito, sufixo):
    """Componente de pós-graduação NOVO, para ter o que vincular à matriz.

    Criado por ORM porque o autocomplete de ``vincular_componente`` só lista componentes
    do mesmo nível de ensino da matriz, e os três componentes de pós do replay já estão
    todos vinculados a ela.
    """
    from edu.models import Componente, ComponenteCurricular, Diretoria, NivelEnsino, TipoComponente

    componente = Componente.objects.create(
        descricao=f'Seminário de Pesquisa {sufixo}',
        descricao_historico=f'Seminário de Pesquisa {sufixo}',
        abreviatura=f'SP{sufixo[:4]}',
        tipo=TipoComponente.objects.get(descricao='POS'),
        diretoria=Diretoria.objects.get(setor__sigla='DIAC/CEN'),
        nivel_ensino=NivelEnsino.objects.get(descricao='Pós-graduação'),
        ativo=True,
        ch_hora_relogio=30,
        ch_hora_aula=40,
        ch_qtd_creditos=2,
    )
    yield componente
    ComponenteCurricular.objects.filter(componente=componente).delete()
    componente.delete()


def test_vincula_componente_a_matriz(logado_edu, matriz_conceito, componente_fora_da_matriz):
    """Componente + matriz = componente curricular, a unidade que vira diário."""
    from edu.models import ComponenteCurricular

    componente = componente_fora_da_matriz
    page = logado_edu('admin_academico')
    try:
        page.goto(f'/edu/matriz/{matriz_conceito.pk}/vincular_componente/')
        expect(page.get_by_role('heading', name='Vincular Componente de Matriz')).to_be_visible()

        escolher_autocomplete(page, 'componente', componente.sigla)
        page.select_option('select[name=periodo_letivo]', label='1')
        page.select_option('select[name=tipo]', label='Regular')
        page.select_option('select[name=qtd_avaliacoes]', label='Uma')
        escolher_autocomplete(page, 'nucleo', 'Formação')
        page.fill('input[name=ch_presencial]', '30')
        # Obrigatória porque há curso vinculado a esta matriz com "Exige Plano de Ensino".
        page.fill('textarea[name=ementa]', 'Ementa do componente de e2e.')
        page.click('input[type=submit][value="Vincular Componente"]')

        mensagem_de_sucesso(page, 'Componente de matriz adicionado com sucesso.')
        assert ComponenteCurricular.objects.filter(matriz=matriz_conceito, componente=componente).exists()
    finally:
        ComponenteCurricular.objects.filter(matriz=matriz_conceito, componente=componente).delete()


def test_cadastra_curso_e_vincula_matriz(logado_edu, sufixo):
    """Cria o curso e, na aba Matrizes, vincula a matriz — os dois passos são separados.

    O SUAP avisa isso na própria mensagem do primeiro save ("vincule a(s) matriz(es)"):
    curso sem matriz não gera turma.
    """
    from edu.models import CursoCampus

    codigo = f'9{uuid4().int % 10**4:04d}'
    descricao = f'Especialização E2E {sufixo}'
    page = logado_edu('admin_academico')
    try:
        _cadastrar_curso_e_matriz(page, codigo, descricao)
    finally:
        # Curso residual apareceria no autocomplete "Matriz/Curso" da matrícula direta
        # (módulo 04), que busca por "Espec" — dois candidatos tornariam aquele teste
        # dependente da ordem de execução.
        CursoCampus.objects.filter(codigo=codigo).delete()


def _cadastrar_curso_e_matriz(page, codigo: str, descricao: str) -> None:
    from edu.models import CursoCampus, MatrizCurso

    page.goto('/admin/edu/cursocampus/add/')
    page.fill('input[name=descricao]', descricao)
    page.fill('input[name=descricao_historico]', descricao)
    # `input[type=date]` só aceita ISO; o formato brasileiro é rejeitado com "Malformed value".
    page.fill('input[name=data_inicio]', '2019-03-15')
    escolher_autocomplete(page, 'ano_letivo', '2019')
    page.select_option('select[name=periodo_letivo]', label='1')
    page.fill('input[name=quantidade_vagas]', '10')
    escolher_autocomplete(page, 'coordenador', '100005')
    page.check('input[name=ativo]')
    page.fill('input[name=codigo]', codigo)
    escolher_autocomplete(page, 'modalidade', 'Especialização')
    escolher_autocomplete(page, 'area_capes', 'Educação')
    page.select_option('select[name=periodicidade]', label='Semestral')
    escolher_autocomplete(page, 'diretoria', 'DIAC/CEN')
    page.fill('input[name=titulo_certificado_masculino]', 'Especialista')
    page.fill('input[name=titulo_certificado_feminino]', 'Especialista')
    page.click('input[name=_save]')

    mensagem_de_sucesso(page, 'Curso cadastrado com sucesso.')
    curso = CursoCampus.objects.filter(codigo=codigo).first()
    assert curso is not None, 'a UI disse que salvou, mas não persistiu'

    page.goto(f'/edu/cursocampus/{curso.pk}/?tab=matrizes')
    popup = abrir_popup(page, 'Vincular Matriz')
    escolher_autocomplete(page, 'matriz', 'Especialização em Educação Profissional', escopo=popup)
    popup.locator('input[type=submit]').first.click()

    mensagem_de_sucesso(page, 'Matriz adicionada com sucesso.')
    assert MatrizCurso.objects.filter(curso_campus=curso).exists(), 'matriz não vinculada ao curso'


def test_professor_nao_cadastra_curso(logado_edu):
    page = logado_edu('professor')
    assert page.goto('/admin/edu/cursocampus/add/').status == 403
