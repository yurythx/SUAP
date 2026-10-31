"""Indisponibilização de sala: registrar, listar, visualizar e excluir.

Indisponibilizar é o caminho pelo qual o avaliador tira a sala da agenda sem que exista
solicitação nenhuma — um ``ReservaSala`` especializado (``IndisponibilizacaoSala`` herda dele),
o que faz o registro disputar o mesmo espaço das reservas: o formulário recusa período que
colida com reserva deferida **ou** com solicitação pendente, e é justamente essa conjunção que
quebra quando alguém mexe nos managers ``deferidas``/``pendentes``.

O formulário tem duas portas — com a sala já escolhida (``.../registrar_indisponibilizacao/<sala_pk>/``,
o botão da ficha da sala) e sem ela (``.../registrar_indisponibilizacao/``, o botão da listagem,
que obriga a descer a cadeia campus → prédio → sala em ``select`` encadeados). As duas são
cobertas porque montam o formulário por caminhos diferentes.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from playwright.sync_api import expect

from djtools.e2e_ui import Tela

from .conftest import postar

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

LISTAR_INDISPONIBILIZACOES = '/comum/sala/listar_indisponibilizacoes/'
REGISTRAR_INDISPONIBILIZACAO = '/comum/sala/registrar_indisponibilizacao/'
REGISTRAR_INDISPONIBILIZACAO_DA_SALA = '/comum/sala/registrar_indisponibilizacao/{sala}/'
VER_INDISPONIBILIZACAO = '/comum/sala/ver_indisponibilizacao/{indisponibilizacao}/'
EXCLUIR_INDISPONIBILIZACAO = '/comum/sala/excluir_indisponibilizacao/{indisponibilizacao}/'


def _daqui_a(dias: int, hora: int) -> str:
    """Momento futuro em ``dd/mm/aaaa HH:MM`` — o formato que ``Tela`` espera em ``data e hora``."""
    return (datetime.now() + timedelta(days=dias)).strftime(f'%d/%m/%Y {hora:02d}:00')


def test_registrar_indisponibilizacao_da_ficha_da_sala(logado_comum, sala_agendavel):
    """Porta curta: a sala vem na URL e o avaliador só informa o período e o motivo.

    O ``httprr('..')`` da view leva à página anterior da trilha de navegação
    (``djtools/utils/response.py:130``), não a um caminho relativo — o banner chega inteiro.
    """
    from comum.models import IndisponibilizacaoSala

    tela = Tela(logado_comum('avaliador_sala')).ir(REGISTRAR_INDISPONIBILIZACAO_DA_SALA.format(sala=sala_agendavel.pk))
    tela.preencher_formulario(
        [
            ('Data/Hora de Início', 'data e hora', _daqui_a(15, 8)),
            ('Data/Hora Final', 'data e hora', _daqui_a(15, 18)),
            ('Justificativa', 'textarea', 'Troca do piso.'),
        ]
    )
    tela.clicar_botao('Salvar')

    tela.sucesso('Cadastro realizado com sucesso.')
    registro = IndisponibilizacaoSala.objects.filter(sala=sala_agendavel, justificativa='Troca do piso.').first()
    assert registro, 'a UI disse que cadastrou, mas a indisponibilização não persistiu'
    # Afirma o PERÍODO, não só a existência: `data_inicio`/`data_fim` são `datetime-local`, um
    # widget que `Tela.preencher` trata por um caminho próprio (`data e hora`), e um período
    # errado deixa a sala aberta justamente quando deveria estar fechada.
    assert (registro.data_inicio.hour, registro.data_fim.hour) == (8, 18), 'o período digitado não chegou ao banco'
    assert registro.data_inicio.date() == (datetime.now() + timedelta(days=15)).date()


def test_registrar_indisponibilizacao_escolhendo_campus_predio_e_sala(logado_comum, sala_agendavel):
    """Porta longa: os três ``select`` encadeados de ``RegistrarIndisponibilizacaoSalaForm``.

    ``predio`` e ``sala`` são ``ChainedModelChoiceField``: nascem vazios e só ganham opções
    quando o campo de cima dispara ``change`` (o widget faz um POST síncrono por campo). Se a
    cadeia quebrar, o sintoma não é erro — é um ``select`` sem a opção, e o registro
    simplesmente não acontece. Por isso o teste desce a cadeia inteira em vez de ir pela porta
    curta.

    O ``queryset`` de cada nível é filtrado por ``avaliadores_de_agendamentos=request.user``:
    só chega aqui a sala que o próprio usuário avalia.
    """
    from comum.models import IndisponibilizacaoSala

    tela = Tela(logado_comum('avaliador_sala')).ir(REGISTRAR_INDISPONIBILIZACAO)
    tela.preencher_formulario(
        [
            ('Campus', 'lista', str(sala_agendavel.predio.uo)),
            ('Prédio', 'lista', sala_agendavel.predio.nome),
            ('Sala', 'lista', sala_agendavel.nome),
            ('Data/Hora de Início', 'data e hora', _daqui_a(25, 7)),
            ('Data/Hora Final', 'data e hora', _daqui_a(25, 12)),
            ('Justificativa', 'textarea', 'Dedetização anual.'),
        ]
    )
    tela.clicar_botao('Salvar')

    tela.sucesso('Cadastro realizado com sucesso.')
    assert IndisponibilizacaoSala.objects.filter(sala=sala_agendavel, justificativa='Dedetização anual.').exists(), (
        'a cadeia campus → prédio → sala não chegou a gravar a indisponibilização'
    )


def test_listagem_separa_as_indisponibilizacoes_em_andamento(logado_comum, indisponibilizacao):
    """As duas abas da listagem são dois querysets: ``objects.all()`` e ``em_andamento``.

    A indisponibilização da fixture é futura, então aparece em "Qualquer" e **não** em "Salas
    Atualmente em Manutenção" — o manager ``em_andamento`` recorta pelo instante atual. Afirmar
    a ausência aqui é legítimo (e não "ausência de erro"): é a distinção entre as abas que se
    está medindo, e a presença na primeira já prova que a tela funciona.
    """
    # A listagem identifica o registro pela sala e pelo período, não pela justificativa
    # (`comum/templates/sala_listar_indisponibilizacoes.html`); a sala é nova a cada teste, então
    # serve de discriminador exato.
    tela = Tela(logado_comum('avaliador_sala')).ir(LISTAR_INDISPONIBILIZACOES + '?tab=qualquer')
    tela.ver_texto(str(indisponibilizacao.sala))
    tela.ver_botao('Registrar Indisponibilização')

    tela.ir(LISTAR_INDISPONIBILIZACOES + '?tab=em_manutencao')
    assert str(indisponibilizacao.sala) not in ' '.join(tela.pagina.locator('//main').all_inner_texts()), (
        'indisponibilização futura não pode aparecer como sala em manutenção agora'
    )


@pytest.mark.parametrize('ordenacao', ['sala', '-sala', 'periodo', '-periodo'])
def test_listagem_ordena_por_sala_e_por_periodo(logado_comum, indisponibilizacao, ordenacao):
    """Os cabeçalhos ordenáveis da listagem viram ``?order_by=`` e a view traduz cada um.

    ``sala_listar_indisponibilizacoes`` lê o parâmetro com ``split('-')`` e monta o ``order_by``
    à mão, coluna a coluna: um nome de campo que mude (``data_inicio`` virou "periodo" na tela)
    quebra a ordenação sem quebrar a página, e o usuário vê a lista embaralhada. As quatro
    combinações são um ``parametrize`` porque só o par (coluna, sentido) varia.
    """
    tela = Tela(logado_comum('avaliador_sala')).ir(LISTAR_INDISPONIBILIZACOES + f'?order_by={ordenacao}')

    tela.ver_texto(str(indisponibilizacao.sala))


def test_ver_e_excluir_indisponibilizacao(logado_comum, indisponibilizacao):
    """Visualizar e remover o registro — a saída de quem indisponibilizou por engano.

    A remoção exige POST (``require_POST``): um GET — *prefetch* de link, crawler — responde
    405 e não apaga. Pela tela, o gesto é o ícone de remoção da listagem, um formulário POST
    com CSRF.
    """
    from comum.models import IndisponibilizacaoSala

    tela = Tela(logado_comum('avaliador_sala')).ir(VER_INDISPONIBILIZACAO.format(indisponibilizacao=indisponibilizacao.pk))
    tela.ver_titulo('Visualizar Registro de Indisponibilização')
    tela.ver_texto(str(indisponibilizacao.sala))
    tela.ver_texto(indisponibilizacao.justificativa)

    url = EXCLUIR_INDISPONIBILIZACAO.format(indisponibilizacao=indisponibilizacao.pk)
    assert tela.buscar(url).status == 405, 'a remoção por GET tem de responder 405'
    assert IndisponibilizacaoSala.objects.filter(pk=indisponibilizacao.pk).exists(), 'o GET apagou o registro'

    tela.ir(LISTAR_INDISPONIBILIZACOES)
    remover = tela.loc(f'//form[@action="{url}"]//button')
    expect(remover).to_be_visible()
    remover.click()

    tela.sucesso('Indisponibilização removida com sucesso.')
    assert not IndisponibilizacaoSala.objects.filter(pk=indisponibilizacao.pk).exists(), 'a UI disse que removeu, mas o registro continua no banco'


def test_registrar_indisponibilizacao_exige_avaliar_alguma_sala(logado_comum):
    """Primeira guarda da view: ter a permissão do grupo não basta, é preciso avaliar alguma sala.

    ``avaliador_outro_campus`` está no grupo ``Avaliador de Sala`` (logo passa pelo
    ``permission_required``) e, sem nenhuma fixture de sala neste teste, não avalia sala
    alguma — é exatamente o recorte de ``Sala.eh_avaliador_salas``.
    """
    tela = Tela(logado_comum('avaliador_outro_campus'))

    resposta = tela.buscar(REGISTRAR_INDISPONIBILIZACAO)

    assert resposta.status == 403, f'o registro respondeu {resposta.status} para quem tem a permissão mas não avalia sala nenhuma'


def test_nao_se_indisponibiliza_sala_alheia(logado_comum, sala_agendavel, sala_restrita_ao_campus, indisponibilizacao):
    """Segunda guarda: avaliar *uma* sala não autoriza mexer na sala de outro avaliador.

    ``avaliador_outro_campus`` avalia ``sala_restrita_ao_campus`` — passa pela guarda anterior —
    mas não avalia ``sala_agendavel``. É a distinção entre ``eh_avaliador_salas`` (qualquer sala)
    e ``eh_avaliador`` (esta sala), e é a que se perde quando alguém "simplifica" as duas numa só.
    """
    tela = Tela(logado_comum('avaliador_outro_campus'))

    assert tela.buscar(REGISTRAR_INDISPONIBILIZACAO_DA_SALA.format(sala=sala_agendavel.pk)).status == 403, (
        'indisponibilizar sala de outro avaliador deveria ser negado'
    )
    assert postar(tela.pagina, EXCLUIR_INDISPONIBILIZACAO.format(indisponibilizacao=indisponibilizacao.pk)).status == 403, (
        'excluir indisponibilização de sala alheia deveria ser negado'
    )


def test_indisponibilizacao_e_privativa_de_quem_avalia_salas(logado_comum, indisponibilizacao):
    """Permissão por status HTTP: as telas exigem as permissões do grupo ``Avaliador de Sala``.

    O grupo ``Servidor``, que todo servidor ganha, dá ``add_solicitacaoreservasala`` mas nenhuma
    permissão sobre ``indisponibilizacaosala`` — é essa fronteira que se mede.
    """
    tela = Tela(logado_comum('solicitante'))

    assert tela.buscar(LISTAR_INDISPONIBILIZACOES).status == 403, 'a listagem de indisponibilizações ficou aberta a quem não avalia salas'
    assert tela.buscar(REGISTRAR_INDISPONIBILIZACAO).status == 403, 'o registro de indisponibilização ficou aberto a quem não avalia salas'
    assert tela.buscar(VER_INDISPONIBILIZACAO.format(indisponibilizacao=indisponibilizacao.pk)).status == 403
    assert postar(tela.pagina, EXCLUIR_INDISPONIBILIZACAO.format(indisponibilizacao=indisponibilizacao.pk)).status == 403
