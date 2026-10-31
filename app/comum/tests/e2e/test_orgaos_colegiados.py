"""Fluxo: o calendário público das reuniões dos órgãos colegiados superiores (CODIR, CONSUP, CONSEPEX).

São os conselhos que decidem a política da instituição, e a pauta deles é de interesse de todo
servidor — por isso ``pode_consultar_calendarios`` está no grupo ``Servidor``
(``comum/permissions.yaml:437``) e não num grupo de gestão. As duas rotas são a consulta (um
calendário mensal ou anual) e o detalhamento de uma reunião.

A regressão que o arquivo pega é a do **calendário vazio**. ``ReuniaoOrgaoColegiado.query``
devolve ``qs_base.none()`` quando o formulário não traz as duas datas (``comum/models.py``,
"por padrão é restrito aos parâmetros de filtragem"), e a montagem do calendário inteira roda
dentro de um ``try/except Exception`` que transforma qualquer erro num ``form.add_error``
(``comum/views.py:4749-4758``). Quer dizer: a tela responde 200 e parece correta tanto quando o
filtro funciona quanto quando ele parou de casar. O que separa os dois é o **título da reunião
aparecendo no calendário**, e é isso que os testes afirmam — inclusive pelo contraste com a tela
sem filtro, que legitimamente não mostra nada.
"""

from __future__ import annotations

from datetime import date

import pytest

from djtools.choices import Meses
from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# Rotas como constantes de módulo: é esta string literal que o gate
# `bin/scripts/paridade_e2e.py comum --rotas` colhe (armadilha 17 da receita).
CALENDARIO_DE_REUNIOES = '/comum/orgaos_colegiados_reunioes_consultar_calendario/'
DETALHAR_REUNIAO = '/comum/orgaos_colegiados_detalhar_reuniao/{pk}/'


@pytest.mark.parametrize('formato', ['Mensal', 'Anual'], ids=['mensal', 'anual'])
def test_calendario_de_reunioes_mostra_a_reuniao_do_periodo(logado_comum, reuniao_colegiado, formato):
    """Filtrar por mês/ano tem de desenhar a reunião no calendário — nos dois formatos.

    Parametrizado porque o que se verifica é exatamente o par (formato, calendário): a view
    escolhe entre ``CalendarioMix.FORMATO_MENSAL`` e ``FORMATO_ANUAL`` e, junto, troca onde a
    legenda é desenhada (``comum/views.py:4751-4756``). São duas montagens de HTML diferentes
    sobre os mesmos dados, e só uma delas quebraria de cada vez.

    O teste primeiro confere que a tela **sem** filtro não mostra a reunião. Não é redundância: é
    o que distingue "o filtro funcionou" de "o calendário mostra tudo sempre". A consulta é por
    ``GET`` (``ReuniaoOrgaoColegiadoConsultarForm.METHOD``), então enviar o formulário é o gesto
    que monta a query string — e é por ele que o teste passa, em vez de montar a URL na mão.
    """
    hoje = date.today()

    tela = Tela(logado_comum('solicitante')).ir(CALENDARIO_DE_REUNIOES)
    tela.ver_titulo('Calendário de Reuniões de Órgãos Colegiados Superiores')
    assert reuniao_colegiado.titulo not in tela.pagina.content(), (
        'o calendário sem filtro já mostrava a reunião: o filtro por período deixou de restringir'
    )

    tela.preencher_formulario(
        [
            ('Formato', 'lista', formato),
            ('Filtrar por Mês:', 'lista', Meses.get_mes(hoje.month)),
            ('Filtrar por Ano:', 'lista', str(hoje.year)),
        ]
    )
    tela.clicar_botao('Enviar')

    tela.ver_titulo('Calendário de Reuniões de Órgãos Colegiados Superiores')
    tela.ver_texto(reuniao_colegiado.titulo)


def test_detalhar_reuniao_de_orgao_colegiado(logado_comum, reuniao_colegiado):
    """A ficha da reunião: pauta, local e horário, para quem só pode consultar.

    O papel é o ``solicitante`` — um servidor sem grupo de gestão — de propósito: a tela calcula
    quatro permissões (``change``, ``delete``, ``view_reuniaoorgaocolegiado`` e
    ``pode_consultar_calendarios``) e publica ou esconde os botões conforme elas
    (``comum/views.py:4768-4772``). Abrir com quem só consulta é o que garante que a ficha
    continua legível para o público a que ela se destina; abrir com um administrador esconderia
    uma regressão que exigisse ``change`` para ler.
    """
    tela = Tela(logado_comum('solicitante')).ir(DETALHAR_REUNIAO.format(pk=reuniao_colegiado.pk))

    tela.ver_titulo('Reunião de Órgão Colegiado Superior')
    tela.ver_texto(reuniao_colegiado.titulo)
    tela.ver_texto(reuniao_colegiado.local)
