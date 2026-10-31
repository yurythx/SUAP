"""Tarefa 2 — cadastrar um curso, da estrutura à matriz.

As doze "Cadastrar X" da funcionalidade 002 são etapas de um objetivo só: pôr um curso de
pé. A ordem é a do próprio SUAP — estrutura → componente → matriz → curso —, e cada save
do módulo devolve na mensagem qual é o passo seguinte ("vincule os componentes",
"vincule a(s) matriz(es)"), que é o que torna o encadeamento afirmável.

Nomes com sufixo aleatório: a suíte não dá flush e quase todo cadastro do ``edu`` tem
descrição única — repetir o nome do seed daria erro de duplicidade, não documentação.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from djtools.e2e_fixtures import abrir_popup, mensagem_de_sucesso
from djtools.e2e_ui import Tela
from edu.tests.doc.conftest import anotar, desfocar, escolher

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

DATA = '10/03/2019'


@pytest.fixture
def sufixo():
    return uuid4().hex[:6].upper()


def test_cadastrar_estrutura_de_curso(logado_edu, sufixo, capturar):
    """Etapa 1 — a estrutura é o regulamento: o que aprova, o que reprova, o que retém."""
    from edu.models import EstruturaCurso

    descricao = f'Especialização DOC {sufixo}'
    estruturas = EstruturaCurso.objects.filter(descricao=descricao)
    try:
        tela = Tela(logado_edu('admin_academico')).ir('/admin/edu/estruturacurso/?ativo__exact=1')
        tela.ver_titulo('Estruturas de Curso')
        anotar('estrutura-listagem', tela)
        tela.clicar_botao('Adicionar Estrutura de Curso')
        anotar('estrutura-formulario', tela)
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
        capturar(tela.pagina, 'estrutura-formulario')
        tela.clicar_botao('Salvar')

        tela.sucesso('Cadastro realizado com sucesso.')
        assert estruturas.exists(), 'a UI disse que salvou, mas não persistiu'
    finally:
        estruturas.delete()


def test_cadastrar_componente(logado_edu, sufixo, capturar):
    """Etapa 2 — o componente é o molde da disciplina, e a sigla dele nasce no save."""
    from edu.models import Componente

    descricao = f'Metodologia Científica {sufixo}'
    componentes = Componente.objects.filter(descricao=descricao)
    page = logado_edu('admin_academico')
    try:
        tela = Tela(page).ir('/admin/edu/componente/?ativo__exact=1')
        tela.ver_titulo('Componentes')
        anotar('componente-listagem', tela)
        capturar(page, 'componente-listagem')
        tela.clicar_botao('Adicionar Componente')
        anotar('componente-formulario', tela)

        page.fill('input[name=descricao]', descricao)
        page.fill('input[name=descricao_historico]', descricao)
        page.fill('input[name=abreviatura]', f'MC{sufixo[:4]}')
        escolher(page, 'tipo', 'POS')
        escolher(page, 'diretoria', 'DIAC/CEN')
        escolher(page, 'nivel_ensino', 'Pós-graduação')
        page.fill('input[name=ch_hora_relogio]', '45')
        page.fill('input[name=ch_hora_aula]', '60')
        page.fill('input[name=ch_qtd_creditos]', '3')
        capturar(page, 'componente-formulario')
        page.click('input[name=_save]')

        mensagem_de_sucesso(page, 'Cadastro realizado com sucesso.')
        componente = componentes.first()
        assert componente is not None, 'a UI disse que salvou, mas não persistiu'
        assert componente.sigla, 'componente sem sigla: é ela que identifica a disciplina em todas as telas'
    finally:
        componentes.delete()


def test_cadastrar_matriz_curricular(logado_edu, sufixo, capturar):
    """Etapa 3 — a matriz declara a carga horária exigida por tipo de componente."""
    from edu.models import Matriz

    descricao = f'Matriz DOC {sufixo}'
    matrizes = Matriz.objects.filter(descricao=descricao)
    try:
        tela = Tela(logado_edu('admin_academico')).ir('/admin/edu/matriz/correntes/')
        tela.ver_titulo('Matrizes Curriculares')
        anotar('matriz-listagem', tela)
        tela.clicar_botao('Adicionar Matriz')
        anotar('matriz-formulario', tela)
        # Autocompletes por último, com o foco limpo antes: a digitação do select2 vaza para o
        # campo focado anteriormente quando o widget demora a abrir (ver `escolher`, no
        # conftest) — e aqui o campo anterior seria a Descrição, que é o que a asserção usa.
        tela.preencher_formulario(
            [
                ('Descrição', 'texto', descricao),
                ('Período Criação', 'lista', '1'),
                ('Ativa', 'checkbox', 'marcar'),
                ('Data de início', 'data', '15/03/2019'),
                ('PPP', 'arquivo', 'arquivo.pdf'),
                ('Quantidade de Períodos Letivos', 'lista', '2'),
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
        desfocar(tela.pagina)
        tela.preencher_formulario(
            [
                ('Ano Criação', 'autocomplete', '2019'),
                ('Nível de Ensino', 'autocomplete', 'Pós-graduação'),
                ('Natureza de participação', 'autocomplete', 'Presencial'),
                ('Estrutura de curso', 'autocomplete', 'Especialização e Aperfeiçoamento'),
            ]
        )
        capturar(tela.pagina, 'matriz-formulario')
        tela.clicar_botao('Salvar')

        tela.sucesso('Matriz cadastrada com sucesso.')
        assert matrizes.exists(), 'a UI disse que salvou, mas a matriz não persistiu'
        anotar('matriz-ficha', tela)
        capturar(tela.pagina, 'matriz-ficha')
    finally:
        matrizes.delete()


@pytest.fixture
def matriz_conceito(edu_seed):
    """Matriz "[CONCEITO]" — a réplica que o seed cria e que nenhum outro fluxo avança."""
    from edu.models import Matriz

    return Matriz.objects.get(descricao='Especialização em Educação Profissional [CONCEITO]')


@pytest.fixture
def componente_fora_da_matriz(matriz_conceito, sufixo):
    """Componente de pós-graduação novo: o autocomplete só lista o que ainda não está na matriz."""
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


def test_vincular_componente_a_matriz(logado_edu, matriz_conceito, componente_fora_da_matriz, capturar):
    """Etapa 4 — componente + matriz = componente curricular, a unidade que vira diário."""
    from edu.models import ComponenteCurricular

    componente = componente_fora_da_matriz
    vinculos = ComponenteCurricular.objects.filter(matriz=matriz_conceito, componente=componente)
    page = logado_edu('admin_academico')
    try:
        tela = Tela(page).ir(f'/edu/matriz/{matriz_conceito.pk}/')
        anotar('matriz-ficha-abas', tela)
        # A aba precisa ser CLICADA: o painel é `ajax-rendered` e os botões dele não existem
        # no DOM enquanto ela não vira a ativa — capturar antes mostraria a aba errada.
        tela.clicar_aba('Componentes curriculares')
        tela.esperar()
        anotar('matriz-aba-componentes', tela)
        capturar(page, 'matriz-componentes')

        tela.ir(f'/edu/matriz/{matriz_conceito.pk}/vincular_componente/')
        tela.ver_titulo('Vincular Componente de Matriz')
        anotar('matriz-vincular-componente', tela)
        escolher(page, 'componente', componente.sigla)
        page.select_option('select[name=periodo_letivo]', label='1')
        page.select_option('select[name=tipo]', label='Regular')
        page.select_option('select[name=qtd_avaliacoes]', label='Uma')
        escolher(page, 'nucleo', 'Formação')
        page.fill('input[name=ch_presencial]', '30')
        page.fill('textarea[name=ementa]', 'Ementa do componente.')
        capturar(page, 'matriz-vincular-componente')
        page.click('input[type=submit][value="Vincular Componente"]')

        mensagem_de_sucesso(page, 'Componente de matriz adicionado com sucesso.')
        assert vinculos.exists(), 'a UI disse que vinculou, mas não persistiu'
    finally:
        vinculos.delete()


def test_cadastrar_curso_e_vincular_matriz(logado_edu, sufixo, capturar):
    """Etapa 5 — o curso, e a aba Matrizes que o liga ao que o aluno vai cursar."""
    from edu.models import CursoCampus, MatrizCurso

    # Código determinístico e único de verdade: o próximo livre na faixa dos 9xxxx. O
    # `uuid4() % 10**4` anterior tinha só 10.000 valores e, pior, mascarava falha — colidindo,
    # `filter(codigo=...)` acharia o curso ALHEIO e o teste passaria por engano.
    usados = [int(c) for c in CursoCampus.objects.filter(codigo__startswith='9').values_list('codigo', flat=True) if c.isdigit()]
    codigo = str(max(usados) + 1) if usados else '90001'
    descricao = f'Especialização DOC {sufixo}'
    # A identidade do teste é a DESCRIÇÃO (única por execução, via sufixo): é ela que separa
    # "não salvou" de "salvou com outro código".
    cursos = CursoCampus.objects.filter(descricao=descricao)
    page = logado_edu('admin_academico')
    try:
        tela = Tela(page).ir('/admin/edu/cursocampus/correntes/')
        tela.ver_titulo('Cursos')
        anotar('curso-listagem', tela)
        capturar(page, 'curso-listagem')
        tela.clicar_botao('Adicionar Curso')
        anotar('curso-formulario', tela)

        page.fill('input[name=descricao]', descricao)
        page.fill('input[name=descricao_historico]', descricao)
        page.fill('input[name=data_inicio]', '2019-03-15')
        escolher(page, 'ano_letivo', '2019')
        page.select_option('select[name=periodo_letivo]', label='1')
        page.fill('input[name=quantidade_vagas]', '10')
        escolher(page, 'coordenador', '100005')
        page.check('input[name=ativo]')
        page.fill('input[name=codigo]', codigo)
        escolher(page, 'modalidade', 'Especialização')
        escolher(page, 'area_capes', 'Educação')
        page.select_option('select[name=periodicidade]', label='Semestral')
        escolher(page, 'diretoria', 'DIAC/CEN')
        page.fill('input[name=titulo_certificado_masculino]', 'Especialista')
        page.fill('input[name=titulo_certificado_feminino]', 'Especialista')
        capturar(page, 'curso-formulario')
        page.click('input[name=_save]')

        # A UI confirma ANTES de o banco ser consultado: sem isto, uma recusa de validação
        # apareceria como "não persistiu" e mandaria o diagnóstico para o lugar errado.
        mensagem_de_sucesso(page, 'Curso cadastrado com sucesso.')
        curso = cursos.first()
        assert curso is not None, f'a UI disse que salvou, mas não há curso com a descrição {descricao!r}'
        assert curso.codigo == codigo, f'curso salvo com código {curso.codigo!r} em vez de {codigo!r} — tecla vazada para o campo?'

        tela.ir(f'/edu/cursocampus/{curso.pk}/?tab=matrizes')
        anotar('curso-ficha', tela)
        capturar(page, 'curso-ficha')
        popup = abrir_popup(page, 'Vincular Matriz')
        escolher(page, 'matriz', 'Especialização em Educação Profissional', escopo=popup)
        capturar(page, 'curso-vincular-matriz')
        popup.locator('input[type=submit]').first.click()

        mensagem_de_sucesso(page, 'Matriz adicionada com sucesso.')
        assert MatrizCurso.objects.filter(curso_campus=curso).exists(), 'matriz não vinculada ao curso'
    finally:
        cursos.delete()
