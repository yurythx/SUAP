"""Fluxo: os cadastros de apoio do menu — as tabelas que parametrizam todo edital.

Nenhuma delas é o processo em si, mas todas o alimentam: critério de classificação decide a
ordem do resultado, licença/afastamento decide quem se inscreve e quanto tempo conta, tempo
adicional soma dias de outro órgão, data de exercício ajustada corrige o que veio errado do
SIAPE. São nove entradas de ``remanejamento/menu.yaml``, todas telas de ``ModelAdminPlus``.

O que se afirma aqui:

* que as **nove portas do menu** abrem para o coordenador. Entrada de menu que aponta para um
  admin não registrado, ou para um model cuja permissão ninguém tem, só é descoberta em
  produção — é uma varredura barata (``Tela.buscar``, sem renderizar) contra uma classe de
  erro que ninguém testa;
* um cadastro **de verdade** no admin de tempo adicional, incluindo o cálculo de dias que o
  ``save`` faz sozinho (``models.py:1871-1876``) — é o único desses cadastros com regra.
"""

from uuid import uuid4

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# As nove entradas de `remanejamento/menu.yaml`, na ordem em que aparecem lá.
TELAS_DO_MENU = [
    '/admin/remanejamento/disciplina/',
    '/admin/remanejamento/criterioclassificacao/',
    '/admin/remanejamento/afastamentoremocaointerna/',
    '/admin/remanejamento/edital/',
    '/admin/remanejamento/inscricao/',
    '/admin/remanejamento/editalrecurso/',
    '/admin/remanejamento/servidordatainicioexercicioremocaointerna/',
    '/admin/remanejamento/inscricaocontemplada/',
    '/admin/remanejamento/servidortempoadicionalremocaointerna/',
]

TEMPO_ADICIONAL = '/admin/remanejamento/servidortempoadicionalremocaointerna/'
TEMPO_ADICIONAL_ADD = '/admin/remanejamento/servidortempoadicionalremocaointerna/add/'


@pytest.mark.parametrize('url', TELAS_DO_MENU)
def test_telas_do_menu_abrem_para_o_coordenador(logado_remanejamento, url):
    """Cada entrada do ``menu.yaml`` responde 200 para quem tem o papel que ela exige.

    ``buscar`` e não ``ir``: o que se afirma é que a view respondeu, e renderizar nove telas de
    admin custaria minutos para provar a mesma coisa. A requisição vai pela sessão do próprio
    browser, com os mesmos cookies — é a permissão real do papel que está sendo medida.
    """
    resposta = Tela(logado_remanejamento('coordenador')).buscar(url)

    assert resposta.status == 200, f'{url} respondeu {resposta.status} para o coordenador'


def test_coordenador_cadastra_tempo_adicional_de_exercicio(logado_remanejamento, servidores):
    """Cadastra tempo adicional e confere o total de dias calculado pelo próprio model.

    O campo "Total de dias" é editável no formulário, mas o ``save`` o sobrescreve com
    ``(fim - início) + 1`` (``models.py:1875-1876``): é o número que o processamento soma ao
    tempo de serviço (``models.py:334-336``). Por isso o teste grava um valor propositalmente
    **errado** e afirma o recalculado — se o ``save`` parar de calcular, o valor digitado
    passaria a valer e ninguém notaria.
    """
    from remanejamento.models import ServidorTempoAdicionalRemocaoInterna

    servidor = servidores['candidato']
    justificativa = f'Tempo de exercício em outro órgão federal (e2e {uuid4().hex[:8]}).'

    tela = Tela(logado_remanejamento('coordenador')).ir(TEMPO_ADICIONAL)
    tela.ver_titulo('Tempos Adicionais de Exercício para Remoção Interna')
    tela.ir(TEMPO_ADICIONAL_ADD)
    tela.preencher_formulario(
        [
            ('Servidor', 'autocomplete', servidor.matricula),
            ('Data de início', 'data', '01/01/2019'),
            ('Data de término', 'data', '31/01/2019'),
            ('Total de dias', 'número', '999'),
            ('Justificativa', 'textarea', justificativa),
        ]
    )
    tela.clicar_botao('Salvar')

    tela.sucesso('Cadastro realizado com sucesso')
    registro = ServidorTempoAdicionalRemocaoInterna.objects.filter(justificativa=justificativa).first()
    assert registro, 'a UI disse que salvou, mas o tempo adicional não persistiu'
    assert registro.servidor == servidor, f'o tempo adicional foi lançado para {registro.servidor}'
    assert registro.quantidade_dias == 31, f'o total de dias deveria ser recalculado para 31, veio {registro.quantidade_dias}'
