"""Fluxo: os relatórios e listas de acompanhamento da Extensão — o menu "Relatórios", o Monitoramento e as listas de e-mail.

Cada relatório é afirmado pelo que ele CONTA ou LISTA de um projeto montado para ele (nunca só
"abriu"), e, quando exporta, pela planilha da tarefa (``@task``, armadilha 76). As sondas são as
que a fatia 5 mediu como recorrentes: a permissão da rota contra a do ``menu.yaml`` (aqui
coincidem em todas — o único descompasso, "Projetos", redireciona para o admin, que tem a própria
permissão) e o recorte por campus do Coordenador de Extensão, papel local — presença no próprio
campus e ausência no outro, com o mesmo seletor.

``relatorio_financeiro`` não recorta o campus do Coordenador de Extensão (o filtro "Campus" é
livre); isso cai na decisão pendente sobre o escopo desse papel e fica fora das asserções.
"""

from __future__ import annotations

import datetime
import io
from urllib.parse import urlencode

import pytest
from playwright.sync_api import expect

from djtools.e2e_ui import Tela
from projetos.tests.e2e.conftest import clicar_em, outra_uo

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

MONITORAMENTO = '/projetos/projetos_em_execucao/'
VALIDAR_EXECUCAO = '/projetos/validar_execucao_etapa/{}/'
EM_ATRASO = '/projetos/listar_projetos_em_atraso/'
TODOS_OS_PROJETOS = '/projetos/lista_todos_os_projetos/'
ESTATISTICAS = '/projetos/estatisticas/'
CARACTERIZACAO = '/projetos/relatorio_caracterizacao_beneficiarios/'
LICOES = '/projetos/relatorio_licoes_aprendidas/'
DIMENSAO = '/projetos/relatorio_dimensao_extensao/'
FINANCEIRO = '/projetos/relatorio_financeiro/'
ALUNOS_POR_PROJETOS = '/projetos/relatorio_alunos_por_projetos/'
PARECERES = '/projetos/relatorio_pareceres_emitidos/'
EMAILS_COORDENADORES = '/projetos/lista_email_coordenadores/'
EMAILS_AVALIADORES = '/projetos/lista_email_avaliadores/'
GERENCIAR_MONITORES = '/projetos/gerenciar_monitores/'
SELECIONAR_MONITOR = '/projetos/selecionar_monitor/{}/'
PROGRESSO_DA_TAREFA = '/djtools/process_progress/1/{}/'  # o arquivo que a tarefa (@task) gerou


def planilha(tela: Tela) -> list[tuple]:
    """As linhas da planilha que a exportação gerou: a tela cai em ``/djtools/process/<uuid>/``."""
    import openpyxl

    uuid = tela.esperar().pagina.url.rstrip('/').rsplit('/', 1)[-1]
    resposta = tela.buscar(PROGRESSO_DA_TAREFA.format(uuid))
    assert resposta.status == 200, f'o arquivo da exportação não veio: {resposta.status}'
    return list(openpyxl.load_workbook(io.BytesIO(resposta.body())).active.iter_rows(values_only=True))


def na_planilha(linhas: list[tuple], texto: str) -> bool:
    return any(texto in str(celula) for linha in linhas for celula in linha)


def estatistica(tela: Tela, titulo: str) -> str:
    """O número de um quadro de "Quantitativo de Projetos" (``estatisticas.html``)."""
    return tela.loc(f'//div[contains(@class, "box-item")][p[@class="title" and normalize-space(.)="{titulo}"]]/p[@class="stat"]').inner_text().strip()


# ------------------------------------------------------------------ monitoramento e atrasos


def test_monitoramento_mostra_ao_monitor_so_os_projetos_dele(logado_projetos, projeto_em_execucao):
    """O Coordenador de Extensão vê o projeto que monitora (e "Acompanhar Validação"), não o sem monitor; o gerente vê os dois."""
    monitorado = projeto_em_execucao(sufixo='monitorado').projeto
    sem_monitor = projeto_em_execucao(sufixo='sem monitor', monitor=None, edital=monitorado.edital).projeto
    acompanhar = '//a[@href="{}"]'.format

    tela = Tela(logado_projetos('coordenador_extensao')).ir(MONITORAMENTO).ver_titulo('Monitoramento')
    expect(tela.loc(acompanhar(VALIDAR_EXECUCAO.format(monitorado.pk)))).to_have_count(1)
    expect(tela.loc(acompanhar(VALIDAR_EXECUCAO.format(sem_monitor.pk)))).to_have_count(0)

    tela = Tela(logado_projetos('gerente')).ir(MONITORAMENTO)
    tela.preencher('Palavra-chave', 'texto', monitorado.edital.titulo).clicar_botao('Enviar')
    tela.esperar().linha(monitorado.titulo)
    expect(tela.loc(acompanhar(VALIDAR_EXECUCAO.format(sem_monitor.pk)))).to_have_count(1)


def test_monitoramento_nao_abre_para_aluno(logado_projetos, projetos_seed):
    """A permissão da rota é a do menu, ``pode_se_tornar_avaliador`` (servidores): o aluno recebe 403."""
    assert Tela(logado_projetos('aluno')).buscar(MONITORAMENTO).status == 403


def test_lista_e_exporta_os_projetos_em_atraso(logado_projetos, projeto_em_execucao):
    """ "Lista de Projetos em Atraso" → edital + "Projetos em Atraso": o de execução vencida aparece, o em dia não; e a planilha."""
    hoje = datetime.date.today()
    atrasado = projeto_em_execucao(
        sufixo='atrasado', inicio_execucao=hoje - datetime.timedelta(days=200), fim_execucao=hoje - datetime.timedelta(days=5)
    )
    em_dia = projeto_em_execucao(sufixo='em dia', edital=atrasado.projeto.edital).projeto
    tela = Tela(logado_projetos('gerente')).ir(EM_ATRASO)

    tela.ver_titulo('Lista de Projetos em Atraso')
    tela.preencher_formulario(
        [('Filtrar por Edital', 'lista', str(atrasado.projeto.edital)), ('Filtrar por Situação', 'lista', 'Projetos em Atraso')]
    )
    tela.clicar_botao('Enviar')
    tela.esperar().linha(atrasado.projeto.titulo)
    expect(tela.loc(f'//a[@href="/projetos/projeto/{em_dia.pk}/"]')).to_have_count(0)
    expect(tela.loc(f'//a[@href="/projetos/projeto/{atrasado.projeto.pk}/"]')).to_have_count(1)

    tela.clicar_botao('Exportar para XLS')
    linhas = planilha(tela)
    assert linhas[0][:4] == ('#', 'Campus', 'Edital', 'Projeto')
    assert na_planilha(linhas, atrasado.projeto.titulo), f'o projeto em atraso não saiu na planilha: {linhas}'


@pytest.mark.parametrize(
    ('papel', 'destino'),
    [('gerente', '/admin/projetos/projeto/'), ('pre_avaliador', '/admin/projetos/projeto/'), ('coordenador_projeto', 'do campus')],
)
def test_projetos_leva_ao_admin_recortado_pelo_papel(logado_projetos, projetos_seed, papel, destino):
    """ "Projetos" (menu, ``view_projeto``) é um redirecionamento: quem avalia ou pré-avalia vê todos; os demais, o próprio campus.

    O pré-avaliador aqui é o Sistêmico (decisão 42: escopo institucional). O Coordenador de Extensão cai no mesmo ramo
    (``pode_pre_avaliar_projeto``) e também vai para a lista sem recorte — mas o escopo dele está em decisão pendente: não se afirma.
    """
    esperado = f'/admin/projetos/projeto/?uo={projetos_seed.uo.pk}&tab=tab_any_data' if destino == 'do campus' else destino
    resposta = Tela(logado_projetos(papel)).buscar(TODOS_OS_PROJETOS)
    assert (resposta.status, resposta.headers.get('location')) == (302, esperado)


# ------------------------------------------------------------------------------ estatísticas


def test_estatisticas_contam_os_projetos_do_edital(logado_projetos, projeto_em_execucao):
    """Filtrado pelo edital: um projeto em execução e um concluído. O Coordenador de Extensão só conta o próprio campus."""
    from projetos.tests.factories import RegistroConclusaoProjetoFactory

    em_execucao = projeto_em_execucao(sufixo='em curso').projeto
    concluido = projeto_em_execucao(sufixo='encerrado', edital=em_execucao.edital).projeto
    RegistroConclusaoProjetoFactory(projeto=concluido)
    de_outro_campus = projeto_em_execucao(sufixo='de fora', uo=outra_uo()).projeto
    tela = Tela(logado_projetos('gerente')).ir(f'{ESTATISTICAS}?{urlencode({"edital": em_execucao.edital_id})}')

    tela.ver_titulo('Indicadores de Projetos de Extensão')
    numeros = {titulo: estatistica(tela, titulo) for titulo in ('Projetos Enviados', 'Projetos Em Execução', 'Projetos Concluídos')}
    assert numeros == {'Projetos Enviados': '2', 'Projetos Em Execução': '1', 'Projetos Concluídos': '1'}

    tela = Tela(logado_projetos('coordenador_extensao')).ir(f'{ESTATISTICAS}?{urlencode({"edital": de_outro_campus.edital_id})}')
    tela.ver_titulo('Indicadores de Projetos de Extensão - Campus CZN').ver_texto('A busca realizada não encontrou nenhum resultado.')
    tela = Tela(logado_projetos('gerente')).ir(f'{ESTATISTICAS}?{urlencode({"edital": de_outro_campus.edital_id})}')
    assert estatistica(tela, 'Projetos Em Execução') == '1'


# ------------------------------------------------------------------ relatórios com recorte de campus


def test_relatorio_de_caracterizacao_de_beneficiarios(logado_projetos, projeto_em_execucao):
    """Filtrado pelo edital, o público previsto e atendido de cada projeto, e a planilha; o Coordenador de Extensão não vê o de outro campus."""
    from projetos.models import CaracterizacaoBeneficiario

    local = projeto_em_execucao(sufixo='local')
    de_fora = projeto_em_execucao(sufixo='de fora', uo=outra_uo(), edital=local.projeto.edital).projeto
    CaracterizacaoBeneficiario.objects.filter(pk=local.caracterizacao.pk).update(quantidade=30, quantidade_atendida=25)
    edital = str(local.projeto.edital)

    tela = Tela(logado_projetos('gerente')).ir(CARACTERIZACAO).ver_titulo('Relatório de Caracterização de Beneficiários')
    tela.preencher('Filtrar por Edital', 'lista', edital).clicar_botao('Enviar')
    tela.esperar().linha(local.projeto.titulo).ver_texto('Público Interno do Instituto').ver_texto('30').ver_texto('25')
    tela.linha(de_fora.titulo)
    tela.clicar_botao('Exportar para XLS')
    assert na_planilha(planilha(tela), local.projeto.titulo), 'o projeto não saiu na planilha da caracterização'

    tela = Tela(logado_projetos('coordenador_extensao')).ir(CARACTERIZACAO)
    tela.preencher('Filtrar por Edital', 'lista', edital).clicar_botao('Enviar')
    tela.esperar().linha(local.projeto.titulo)
    expect(tela.loc(f'//tr[contains(normalize-space(.), "{de_fora.titulo}")]')).to_have_count(0)


def test_relatorio_de_licoes_aprendidas(logado_projetos, projeto_em_execucao):
    """As lições do edital, e a planilha; o Coordenador de Extensão só vê as do próprio campus."""
    from projetos.tests.factories import LicaoAprendidaFactory

    local = projeto_em_execucao(sufixo='local').projeto
    de_fora = projeto_em_execucao(sufixo='de fora', uo=outra_uo(), edital=local.edital).projeto
    licao, alheia = LicaoAprendidaFactory(projeto=local), LicaoAprendidaFactory(projeto=de_fora)

    tela = Tela(logado_projetos('gerente')).ir(LICOES).ver_titulo('Relatório de Lições Aprendidas')
    tela.preencher('Filtrar por Edital', 'lista', str(local.edital)).clicar_botao('Enviar')
    tela.esperar().linha(licao.descricao).ver_texto(local.titulo)
    tela.linha(alheia.descricao)
    tela.clicar_botao('Exportar para XLS')
    assert na_planilha(planilha(tela), licao.descricao), 'a lição não saiu na planilha'

    tela = Tela(logado_projetos('coordenador_extensao')).ir(LICOES)
    tela.preencher('Filtrar por Edital', 'lista', str(local.edital)).clicar_botao('Enviar')
    tela.esperar().linha(licao.descricao)
    expect(tela.loc(f'//tr[contains(normalize-space(.), "{alheia.descricao}")]')).to_have_count(0)


def test_relatorio_de_dimensao_da_extensao(logado_projetos, projeto_em_execucao):
    """Por ano de início da execução, submetidos e aprovados por edital; para o Coordenador de Extensão, só o campus dele conta."""
    hoje = datetime.date.today()
    inicio = {'inicio_execucao': hoje - datetime.timedelta(days=10), 'fim_execucao': hoje + datetime.timedelta(days=300)}
    local = projeto_em_execucao(sufixo='local', **inicio).projeto
    projeto_em_execucao(sufixo='de fora', uo=outra_uo(), edital=local.edital, **inicio)
    ano = str(local.inicio_execucao.year)
    contagem = f'//tr[td[contains(normalize-space(.), "{local.edital.titulo}")]]/td[position() > 1]'

    tela = Tela(logado_projetos('gerente')).ir(DIMENSAO)
    tela.preencher('Ano de Início', 'lista', ano).clicar_botao('Enviar')
    expect(tela.esperar().loc(contagem).first).to_be_visible()
    assert tela.loc(contagem).all_inner_texts()[:2] == ['2', '2'], 'o gerente deveria contar os dois projetos submetidos e aprovados'

    tela = Tela(logado_projetos('coordenador_extensao')).ir(DIMENSAO)
    tela.preencher('Ano de Início', 'lista', ano).clicar_botao('Enviar')
    expect(tela.esperar().loc(contagem).first).to_be_visible()
    assert tela.loc(contagem).all_inner_texts()[:2] == ['1', '1'], 'o Coordenador de Extensão deveria contar só o projeto do CZN'


def test_relatorio_financeiro(logado_projetos, projeto_em_execucao, catalogo_do_edital):
    """Edital + fonte de recurso: cada projeto aprovado com o valor previsto nela, e a planilha."""
    from financeiro.models import NaturezaDespesa
    from projetos.tests.factories import RecursoFactory

    projeto = projeto_em_execucao().projeto
    recurso = RecursoFactory(edital=projeto.edital, despesa=NaturezaDespesa.objects.get(codigo='339018'))
    tela = Tela(logado_projetos('gerente')).ir(f'{FINANCEIRO}?{urlencode({"edital": projeto.edital_id, "recurso": recurso.pk})}')

    # O valor vem de um `FloatField` e o `format_money` o mostra com uma casa ("1.000,0"): afirme só o prefixo.
    tela.ver_titulo('Relatório Financeiro')
    Tela(tela.pagina, escopo='//table[caption[normalize-space(.)="Lista dos projetos"]]').linha(projeto.titulo).ver_texto('1.000,')
    tela.clicar_botao('Exportar para XLS')
    assert na_planilha(planilha(tela), projeto.titulo), 'o projeto não saiu na planilha do relatório financeiro'


# ---------------------------------------------------------------------- relatórios do gerente


def test_relatorio_de_projetos_executados_por_alunos_matriculados(logado_projetos, projeto_em_execucao, projetos_seed):
    """Por ano do edital: a linha do CZN conta os projetos aprovados — o mesmo número que o ORM."""
    from projetos.models import Projeto

    projeto = projeto_em_execucao().projeto
    ano = projeto.edital.inicio_inscricoes.year
    tela = Tela(logado_projetos('gerente')).ir(ALUNOS_POR_PROJETOS).ver_titulo('Relatório - Projetos executados x Alunos matriculados')
    tela.preencher('Ano', 'lista', str(ano)).clicar_botao('Enviar')

    esperado = Projeto.objects.filter(uo=projetos_seed.uo, edital__inicio_inscricoes__year=ano, pre_aprovado=True, aprovado=True).count()
    celula = tela.esperar().loc('//tr[td[1][normalize-space(.)="CZN"]]/td[2]')
    expect(celula).to_have_text(str(esperado))


def test_relatorio_de_pareceres_emitidos_exporta_os_pareceres(logado_projetos, projeto_avaliado):
    """Filtrado pelo edital, a planilha traz o projeto e o parecer do avaliador."""
    item = projeto_avaliado()
    projeto = item.avaliacao.projeto
    tela = Tela(logado_projetos('gerente')).ir(PARECERES).ver_titulo('Relatório de Pareceres Emitidos')

    tela.preencher('Edital', 'lista', str(projeto.edital)).clicar_botao('Enviar')
    linhas = planilha(tela)
    assert linhas[1][:5] == ('#', 'Campus', 'Edital', 'Projeto', 'Parecer 1')
    assert [linha[3:5] for linha in linhas[2:]] == [(projeto.titulo, 'Parecer de avaliador')]


@pytest.mark.parametrize('rota', [ALUNOS_POR_PROJETOS, PARECERES, EMAILS_AVALIADORES])
def test_relatorios_do_gerente_negados_ao_coordenador_de_extensao(logado_projetos, projetos_seed, rota):
    """Mesma permissão do menu (``pode_gerenciar_edital``/``pode_visualizar_avaliadores_externos``), que o Coordenador de Extensão não tem."""
    assert Tela(logado_projetos('coordenador_extensao')).buscar(rota).status == 403


@pytest.mark.parametrize('rota', [ESTATISTICAS, CARACTERIZACAO, LICOES, DIMENSAO, FINANCEIRO, EM_ATRASO, EMAILS_COORDENADORES])
def test_relatorios_de_extensao_negados_ao_servidor_sem_papel(logado_projetos, projetos_seed, rota):
    """``pode_visualizar_relatorios_extensao``, a permissão do menu "Relatórios": o coordenador de projeto não abre."""
    assert Tela(logado_projetos('coordenador_projeto')).buscar(rota).status == 403


# --------------------------------------------------------------------------- listas de e-mail


def test_lista_de_emails_dos_coordenadores(logado_projetos, projeto_em_execucao, email_pessoal_de):
    """Edital + "Projetos em Execução": o e-mail de cada coordenador; o Coordenador de Extensão não recebe o do projeto de outro campus."""
    local = projeto_em_execucao(sufixo='local').projeto
    projeto_em_execucao(sufixo='de fora', coordenador='outro_coordenador', uo=outra_uo(), edital=local.edital)
    email_local, email_de_fora = email_pessoal_de('coordenador_projeto'), email_pessoal_de('outro_coordenador')
    filtro = [('Filtrar por Edital', 'lista', str(local.edital)), ('Filtrar por Situação', 'lista', 'Projetos em Execução')]
    com_email = '//*[contains(text(), "{}")]'.format

    tela = Tela(logado_projetos('gerente')).ir(EMAILS_COORDENADORES).ver_titulo('Lista de Emails dos Coordenadores')
    tela.preencher_formulario(filtro).clicar_botao('Enviar')
    tela.esperar().ver_texto(email_local)
    expect(tela.loc(com_email(email_de_fora)).first).to_be_visible()

    tela = Tela(logado_projetos('coordenador_extensao')).ir(EMAILS_COORDENADORES)
    tela.preencher_formulario(filtro).clicar_botao('Enviar')
    tela.esperar().ver_texto(email_local)
    expect(tela.loc(com_email(email_de_fora))).to_have_count(0)


def test_lista_de_emails_dos_avaliadores_internos(logado_projetos, areas_tematicas_do, email_pessoal_de):
    """Quem indicou área temática de interesse (é avaliador interno) sai na lista, com o e-mail de notificação."""
    from projetos.models import AreaTematica

    areas_tematicas_do('avaliador').areatematica_set.add(AreaTematica.objects.get(descricao='Cultura'))
    email = email_pessoal_de('avaliador')

    tela = Tela(logado_projetos('gerente')).ir(EMAILS_AVALIADORES).ver_titulo('Lista de Emails dos Avaliadores')
    tela.ver_texto('Emails dos Avaliadores Internos').ver_texto(email)


# ------------------------------------------------------------------------------ monitores


def test_gerenciar_monitores_lista_os_editais(logado_projetos, projeto_em_execucao):
    """ "Gerenciar Monitores" (Coordenador de Extensão): filtrado pelo ano, cada edital leva à seleção de monitores dele."""
    edital = projeto_em_execucao().projeto.edital
    tela = Tela(logado_projetos('coordenador_extensao')).ir(GERENCIAR_MONITORES).ver_titulo('Gerenciar Monitores')

    tela.preencher('Ano', 'lista', str(edital.inicio_inscricoes.year)).clicar_botao('Enviar')
    tela.esperar().linha(edital.titulo)
    clicar_em(tela, SELECIONAR_MONITOR.format(edital.pk))
    tela.ver_titulo(f'Selecionar Monitores - {edital.titulo}')


def test_gerenciar_monitores_e_do_papel_de_extensao(logado_projetos, projetos_seed):
    assert Tela(logado_projetos('coordenador_projeto')).buscar(GERENCIAR_MONITORES).status == 403
