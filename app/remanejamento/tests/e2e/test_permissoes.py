"""Matriz de acesso do remanejamento, medida no navegador e por status HTTP.

Documentação executável do que cada papel alcança — a permissão do módulo está espalhada por
três mecanismos diferentes, e nenhum deles é o ``permissions.yaml`` sozinho:

* ``group_required`` no decorador da view (``gerenciar_edital``, ``views.py:140``);
* ``Edital.pode_editar`` (``models.py:247``), que aceita quatro grupos distintos;
* regras de **dado**, não de grupo: ``inscrever`` só abre para quem tem o cargo/área do edital
  (``models.py:220``) e o comprovante só para o dono, o coordenador ou o avaliador da
  disciplina (``models.py:1327``).

O status é afirmado com ``Tela.buscar`` (requisição pela sessão do browser, sem renderizar):
permissão se verifica por status HTTP, não por texto nem por varredura de menu. ``buscar`` não
segue redirect de propósito — sem isso, o 302 para a tela de login chegaria como 200.
"""

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

GERENCIAR = '/remanejamento/edital/{}/gerenciar/'
INSCREVER = '/remanejamento/inscrever/{}/'
INSCRICAO = '/remanejamento/inscricao/{}/'
RECURSO_EDITAL = '/remanejamento/recurso_edital/{}/'
ADMIN_EDITAL = '/admin/remanejamento/edital/'


@pytest.mark.parametrize(
    ('papel', 'esperado'),
    [
        ('coordenador', 200),  # grupo Coordenador de Remanejamento
        ('avaliador', 200),  # grupo Avaliador de Remanejamento — `pode_editar` aceita os dois
        ('candidato', 403),  # servidor comum, ainda que inscrito no edital
        ('servidor_de_fora', 403),
    ],
)
def test_acesso_ao_gerenciamento_do_edital(logado_remanejamento, edital_com_inscricoes_abertas, papel, esperado):
    """Só quem coordena ou avalia entra no gerenciamento — é a tela com todas as ações do edital."""
    resposta = Tela(logado_remanejamento(papel)).buscar(GERENCIAR.format(edital_com_inscricoes_abertas.pk))

    assert resposta.status == esperado, f'{papel} recebeu {resposta.status} no gerenciamento do edital (esperado {esperado})'


@pytest.mark.parametrize(
    ('papel', 'esperado'),
    [
        ('candidato', 200),  # cargo do edital
        ('candidata_correlata', 200),  # área correlata da vaga (`models.py:226-229`)
        ('servidor_de_fora', 403),  # cargo que não está no edital
        ('coordenador', 200),  # coordenar não impede concorrer: o cargo dele também está no edital
    ],
)
def test_acesso_ao_formulario_de_inscricao(logado_remanejamento, edital_com_inscricoes_abertas, papel, esperado):
    """Quem pode se inscrever é decidido por **dado**, não por grupo.

    A linha da ``candidata_correlata`` é a que importa: o cargo dela não é o da vaga, a área é
    — e é a área correlata cadastrada na ``VagaEdital`` que a habilita. Sem ela, o servidor de
    área vizinha recebe 403 e o edital perde candidatos legítimos, sem erro nenhum no log.
    """
    resposta = Tela(logado_remanejamento(papel)).buscar(INSCREVER.format(edital_com_inscricoes_abertas.pk))

    assert resposta.status == esperado, f'{papel} recebeu {resposta.status} na inscrição (esperado {esperado})'


@pytest.mark.parametrize(
    ('papel', 'esperado'),
    [
        ('candidato', 200),  # dono da inscrição
        ('coordenador', 200),  # coordenador do edital
        ('concorrente', 403),  # outro servidor, inclusive inscrito no mesmo edital
    ],
)
def test_acesso_ao_comprovante_de_inscricao(logado_remanejamento, servidores, edital_com_inscricoes_abertas, papel, esperado):
    """O comprovante traz dados pessoais e a chave de autenticidade: é de quem se inscreveu.

    ``concorrente`` responde 403 mesmo estando inscrito no mesmo edital — ``pode_ver``
    (``models.py:1327``) compara a inscrição, não o edital.
    """
    from remanejamento.tests.e2e.conftest import criar_inscricao

    inscricao = criar_inscricao(edital_com_inscricoes_abertas, servidores['candidato'])

    resposta = Tela(logado_remanejamento(papel)).buscar(INSCRICAO.format(inscricao.pk))

    assert resposta.status == esperado, f'{papel} recebeu {resposta.status} no comprovante (esperado {esperado})'


def test_recurso_ao_edital_fora_da_janela_e_recusado(logado_remanejamento, edital_com_inscricoes_abertas):
    """Prazo encerrado não é tela escondida: é 403.

    ``recurso_edital`` (``views.py:101``) recusa quando o servidor está fora do período de
    recurso **daquele** edital. O edital desta fixture teve a janela de recursos há vinte dias,
    então a rota tem de fechar — esconder o atalho e deixar a URL aberta seria o defeito.
    """
    resposta = Tela(logado_remanejamento('candidato')).buscar(RECURSO_EDITAL.format(edital_com_inscricoes_abertas.pk))

    assert resposta.status == 403, f'o recurso ao edital fora do prazo respondeu {resposta.status}'


@pytest.mark.parametrize(('papel', 'esperado'), [('coordenador', 200), ('candidato', 403)])
def test_acesso_ao_cadastro_de_editais_no_admin(logado_remanejamento, papel, esperado):
    """A listagem de editais exige ``remanejamento.view_edital``, que só o coordenador tem.

    É a permissão declarada no ``menu.yaml`` e concedida em ``permissions.yaml`` ao grupo
    Coordenador de Remanejamento — o grupo Servidor recebe apenas ``view_editalrecurso`` e
    ``view_inscricao``.
    """
    resposta = Tela(logado_remanejamento(papel)).buscar(ADMIN_EDITAL)

    assert resposta.status == esperado, f'{papel} recebeu {resposta.status} na listagem de editais (esperado {esperado})'
