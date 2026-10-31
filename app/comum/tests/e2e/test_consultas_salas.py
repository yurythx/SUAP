"""Consultas da família prédios/salas: ficha do prédio, ficha da sala, agenda, relatórios e máquinas.

São as telas de **leitura** do agendamento de salas — as que o usuário abre antes de decidir
reservar (quais salas existem, o que já está marcado, quanto cada sala é usada) mais as duas
telas de situação das máquinas, que vivem na mesma ``urls.py``.

A regressão que este arquivo pega é a mais barata e a mais frequente: uma dessas views quebra
quando um relacionamento do prédio/sala muda de nome ou passa a poder ser nulo, e o sintoma é
500 numa tela que ninguém exercita porque "é só listagem".
"""

from __future__ import annotations

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# Rotas como constantes de módulo: é esta string literal que o gate
# `bin/scripts/paridade_e2e.py comum --rotas` colhe (e o `{marcador}`, sem barra, casa o `[^/]+` que
# ele deriva de `<int:pk>`).
#
# Constante e NUNCA `'/rota/{x}/'.format(...)` escrito na chamada: a regra UP032 do ruff reescreve
# `str.format` literal como f-string, e uma f-string deixa no AST só o pedaço `'/rota/'` — o gate
# passa a não enxergar a rota. Medido: cinco rotas desta fatia saíram de "cobertas" para
# "descobertas" só por rodar `ruff check --fix --unsafe-fixes`. Com a constante, o `.format` incide
# sobre um nome e a regra não dispara.
#
# Query string vai concatenada, nunca embutida no literal: o padrão do gate é ancorado em `$`.
INDICADORES = '/comum/sala/indicadores/'
SALAS_DISPONIVEIS = '/comum/sala/salas_disponiveis/'
MAQUINAS = '/comum/maquinas/'
MAQUINA_DETALHES = '/comum/maquinas/detalhes/{maquina}/'
PREDIO = '/comum/predio/{predio}/'
VISUALIZAR_SALA = '/comum/sala/visualizar/{sala}/'
AGENDA_ATUAL = '/comum/sala/agenda_atual/{sala}/'
INFORMACOES_COMPLEMENTARES = '/comum/sala/informacoes_complementares/{sala}/'


def test_ficha_do_predio(logado_comum, predio_e2e):
    """O gestor de prédios abre a ficha e vê o prédio com o campus — e os botões de manutenção."""
    tela = Tela(logado_comum('gestor_predios')).ir(PREDIO.format(predio=predio_e2e.pk))

    tela.ver_titulo(str(predio_e2e))
    tela.ver_texto(predio_e2e.nome)
    tela.ver_botao('Adicionar Obra')


def test_ficha_da_sala_mostra_situacao_e_acoes_do_avaliador(logado_comum, sala_agendavel):
    """A ficha da sala distingue avaliador de solicitante — só o primeiro vê o cancelamento em lote.

    A asserção do botão não é cosmética: ``eh_avaliador`` depende de duas condições
    independentes (a permissão ``pode_avaliar_solicitacao_reserva_de_sala`` **e** estar em
    ``avaliadores_de_agendamentos``), e é essa conjunção que a tela revela.
    """
    rota = VISUALIZAR_SALA.format(sala=sala_agendavel.pk)

    tela = Tela(logado_comum('avaliador_sala')).ir(rota)
    tela.ver_titulo(str(sala_agendavel))
    tela.ver_texto('Agendável')
    tela.ver_botao('Cancelar Reservas por Período')

    outra = Tela(logado_comum('solicitante')).ir(rota)
    outra.ver_titulo(str(sala_agendavel))
    assert 'Cancelar Reservas por Período' not in outra.botoes_na_tela(), 'quem não avalia a sala não pode cancelar as reservas dela em lote'


def test_agenda_atual_da_sala(logado_comum, reserva_deferida):
    """A agenda da sala traz a reserva deferida — é o calendário que o solicitante consulta."""
    solicitacao, _reserva = reserva_deferida

    tela = Tela(logado_comum('solicitante')).ir(AGENDA_ATUAL.format(sala=solicitacao.sala.pk))

    tela.ver_texto(solicitacao.justificativa[:40])


def test_informacoes_complementares_da_sala(logado_comum, sala_agendavel):
    """Endpoint de texto puro consumido por AJAX pela tela de solicitação: devolve o campo da sala.

    Sem tela própria (``HttpResponse`` cru), então a asserção é sobre o corpo da resposta — e
    ``buscar`` não segue redirect, o que garante que 200 aqui é a view e não a tela de login.
    """
    tela = Tela(logado_comum('solicitante'))

    resposta = tela.buscar(INFORMACOES_COMPLEMENTARES.format(sala=sala_agendavel.pk))

    assert resposta.status == 200, f'a view respondeu HTTP {resposta.status}'
    assert sala_agendavel.informacoes_complementares in resposta.text(), 'o endereço devolveu algo que não são as informações complementares da sala'


def test_listagem_de_salas_disponiveis_filtra_por_periodo(logado_comum, sala_agendavel):
    """A consulta por data/hora acha a sala agendável do campus — e o botão de reservar dela."""
    from datetime import datetime, timedelta

    dia = (datetime.now() + timedelta(days=5)).strftime('%d/%m/%Y')
    tela = Tela(logado_comum('solicitante')).ir(SALAS_DISPONIVEIS)

    tela.preencher_formulario(
        [
            ('Data Inicial', 'data', dia),
            ('Data Final', 'data', dia),
            ('Hora Inicial', 'hora', '08:00'),
            ('Hora Final', 'hora', '10:00'),
        ]
    )
    tela.clicar_botao('Enviar')

    tela.ver_texto(sala_agendavel.nome)


def test_indicadores_de_uso_das_salas(logado_comum, reserva_deferida):
    """Os indicadores do período somam as reservas da sala: o avaliador vê a sala no resultado."""
    from datetime import datetime, timedelta

    solicitacao, _reserva = reserva_deferida
    hoje = datetime.now()
    tela = Tela(logado_comum('avaliador_sala')).ir(INDICADORES)

    # O prédio é um `select` encadeado no campus: preenchê-lo exercita o filtro adicional da
    # view (`agendaveis.filter(predio=predio)`), que é onde o relatório costuma vazar sala de
    # outro prédio do mesmo campus.
    tela.preencher_formulario(
        [
            ('Data Inicial', 'data', hoje.strftime('%d/%m/%Y')),
            ('Data Final', 'data', (hoje + timedelta(days=30)).strftime('%d/%m/%Y')),
            ('Campus', 'lista', str(solicitacao.sala.predio.uo)),
            ('Prédio', 'lista', solicitacao.sala.predio.nome),
        ]
    )
    tela.clicar_botao('Enviar')

    tela.ver_texto(solicitacao.sala.nome)


def test_situacao_das_maquinas_e_detalhe(logado_comum, maquina_e2e, maquina_com_log):
    """As duas telas de máquina exigem ``is_superuser`` — não grupo. Cobre o par listagem → detalhe.

    A listagem monta **dois** relatórios, "com registro de atividade" e "sem registro", a partir
    de dois querysets separados por ``ultimo_log__isnull``; com uma máquina só, metade da view
    nunca roda. Daí as duas fixtures.
    """
    tela = Tela(logado_comum('admin')).ir(MAQUINAS)
    # A listagem identifica a máquina pelo IP, não pela descrição (`comum/templates/maquinas.html`).
    tela.ver_texto(maquina_e2e.ip)
    tela.ver_texto(maquina_com_log.ip)
    tela.ver_texto(str(maquina_e2e.uo))

    tela.ir(MAQUINA_DETALHES.format(maquina=maquina_e2e.pk))
    tela.ver_texto('Dados da Máquina')
    tela.ver_texto(maquina_e2e.ip)


def test_maquinas_negadas_a_quem_nao_e_superusuario(logado_comum, maquina_e2e):
    """Permissão se verifica por status HTTP: a view levanta ``PermissionDenied`` fora do superusuário."""
    tela = Tela(logado_comum('avaliador_sala'))

    assert tela.buscar(MAQUINAS).status == 403, 'a situação das máquinas ficou aberta a quem não é superusuário'
    assert tela.buscar(MAQUINA_DETALHES.format(maquina=maquina_e2e.pk)).status == 403, 'o detalhe da máquina ficou aberto a quem não é superusuário'
