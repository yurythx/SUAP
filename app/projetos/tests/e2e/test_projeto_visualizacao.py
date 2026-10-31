"""Fluxo: as vistas do projeto — a tela completa, a consulta pública e a impressão.

A tela do projeto (``projeto``) é a de quem participa ou gerencia; quem não é da equipe nem tem
papel sobre o projeto é redirecionado para a consulta (``consulta_projeto``), que não mostra
equipe nem ações. A impressão (``imprimir_projeto``, com ``?html=1`` a versão em tela) é a
ficha que acompanha a submissão. A regressão que se pega é o redirecionamento deixar de
acontecer — e um estranho passar a ver a tela de gestão.
"""

import pytest

from djtools.e2e_ui import Tela
from projetos.tests.e2e.conftest import clicar_em

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

PROJETO = '/projetos/projeto/{}/'
CONSULTA_PROJETO = '/projetos/consulta_projeto/{}/'
IMPRIMIR_PROJETO = '/projetos/imprimir_projeto/{}/'


def test_impressao_do_projeto_pelo_coordenador(logado_projetos, projeto_novo):
    """ "Visualizar" → "Impressão": a ficha traz título, campus e o coordenador."""
    projeto = projeto_novo()
    tela = Tela(logado_projetos('coordenador_projeto')).ir(PROJETO.format(projeto.pk))

    tela.clicar_botao('Visualizar')  # abre o submenu da action-bar
    clicar_em(tela, f'{IMPRIMIR_PROJETO.format(projeto.pk)}?html=1')

    tela.ver_texto('IDENTIFICAÇÃO DO PROJETO').ver_texto(projeto.titulo).ver_texto('Coordenador Projeto E2E')


def test_quem_nao_e_da_equipe_cai_na_consulta(logado_projetos, projeto_novo):
    """O avaliador (servidor sem vínculo com o projeto) pede a tela do projeto e recebe a consulta, sem ações."""
    projeto = projeto_novo()
    tela = Tela(logado_projetos('avaliador'))

    resposta = tela.buscar(PROJETO.format(projeto.pk))
    assert (resposta.status, resposta.headers.get('location')) == (302, CONSULTA_PROJETO.format(projeto.pk)), 'o estranho não foi redirecionado'

    tela.ir(CONSULTA_PROJETO.format(projeto.pk)).ver_titulo(f'Projeto de Extensão: {projeto.titulo}')
    assert tela.loc('//a[normalize-space(.)="Editar Projeto"]').count() == 0, 'a consulta oferece a edição a quem não é da equipe'
    # Presença equivalente: com o mesmo seletor, a tela do coordenador oferece a edição.
    coordenador = Tela(logado_projetos('coordenador_projeto')).ir(PROJETO.format(projeto.pk))
    assert coordenador.loc('//a[normalize-space(.)="Editar Projeto"]').count() == 1, 'o seletor da ausência não acha nem a tela do coordenador'


@pytest.mark.parametrize('somente_leitura', [False, True], ids=['em_execucao', 'inativado'])
def test_gerente_so_ve_as_acoes_de_edicao_que_a_view_aceita(logado_projetos, projeto_em_execucao, somente_leitura):
    """#17559: em projeto somente leitura as views recusam o gerente (403); a tela não pode oferecer os botões.

    O caso em execução é o controle positivo: prova que o cenário renderiza cada link.
    """
    from projetos.models import Edital, Projeto
    from projetos.tests.factories import FotoProjetoFactory, ProjetoAnexoFactory

    projeto = projeto_em_execucao().projeto
    Edital.objects.filter(pk=projeto.edital_id).update(ocultar_aba_prestacao_contas=True)  # o GRU vai para o Plano de Desembolso
    anexo = ProjetoAnexoFactory(projeto=projeto, descricao=f'Anexo diverso {projeto.pk}')
    foto = FotoProjetoFactory(projeto=projeto)
    if somente_leitura:
        Projeto.objects.filter(pk=projeto.pk).update(inativado=True)
    rotas = [
        f'/projetos/memoria_calculo/{projeto.pk}/',
        f'/projetos/adicionar_desembolso/{projeto.pk}/',
        f'/projetos/adicionar_comprovante_gru/{projeto.pk}/',
        f'/projetos/adicionar_anexo_diverso_projeto/{projeto.pk}/',
        f'/projetos/excluir_outro_anexo/{anexo.pk}/',
        f'/projetos/upload_outro_anexo/{anexo.pk}/',
        f'/projetos/remover_foto/{foto.pk}/',
    ]

    tela = Tela(logado_projetos('gerente')).ir(PROJETO.format(projeto.pk))

    tela.clicar_aba('Anexos').ver_texto(anexo.descricao)  # a tela do projeto, não a consulta
    oferecidas = [rota for rota in rotas if tela.loc(f'//a[@href="{rota}"]').count()]
    assert oferecidas == ([] if somente_leitura else rotas), f'links oferecidos ao gerente: {oferecidas}'
