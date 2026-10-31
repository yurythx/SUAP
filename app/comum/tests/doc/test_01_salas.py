"""Fatia 1 da doc de usuário do ``comum`` — prédios, salas e reservas de sala.

Cobre as duas entradas de ``Administração::Prédios e Salas`` que não são tabela de apoio e as
seis de ``Administração::Reservas de Salas``. Cada teste é o roteiro de UMA tarefa da doc, na
ordem em que ela as apresenta; as asserções existem para a rodada falhar alto quando a tela
muda de forma, e as ``anotar`` despejam rótulos/opções que a redação copia em vez de deduzir
de ``models.py``.

O relógio **não** congela nesta família (decisão 3 do conftest do e2e): toda data é relativa
ao dia da execução, senão ``SolicitacaoReservaSalaForm.clean`` recusaria o passado e as
guardas ``pode_avaliar``/``pode_cancelar``/``pode_excluir`` barrariam as transições.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from comum.tests.doc.conftest import anotar
from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# Nomes que aparecem NAS CAPTURAS da tarefa 1 (as demais tarefas usam as fixtures do conftest).
PREDIO_NOVO = 'Bloco de Laboratórios'
SALA_NOVA = 'Laboratório de Informática 2'

PREDIOS = '/admin/comum/predio/'
SALAS = '/admin/comum/sala/?ativa__exact=1'
MINHAS_SALAS = '/admin/comum/sala/?agendavel__exact=1&tab=tab_minhas_salas'
FICHA_PREDIO = '/comum/predio/{predio}/'
FICHA_SALA = '/comum/sala/visualizar/{sala}/'
SALAS_DISPONIVEIS = '/comum/sala/salas_disponiveis/'
SOLICITAR_RESERVA = '/comum/sala/solicitar_reserva/{sala}/'
VER_SOLICITACAO = '/comum/sala/ver_solicitacao/{solicitacao}/'
SOLICITACOES = '/admin/comum/solicitacaoreservasala/'
RESERVAS = '/admin/comum/reservasala/'
CANCELAR_RESERVAS_PERIODO = '/comum/sala/cancelar_reservas_periodo/{sala}/'
LISTAR_INDISPONIBILIZACOES = '/comum/sala/listar_indisponibilizacoes/'
INDICADORES = '/comum/sala/indicadores/'


def _dia(dias: int) -> str:
    """Data futura em ``dd/mm/aaaa`` — o formato dos campos de data do SUAP."""
    return (datetime.now() + timedelta(days=dias)).strftime('%d/%m/%Y')


def _momento(dias: int, hora: int) -> str:
    """Momento futuro em ``dd/mm/aaaa HH:MM``, o formato do tipo ``data e hora``."""
    return (datetime.now() + timedelta(days=dias)).strftime(f'%d/%m/%Y {hora:02d}:00')


@pytest.fixture
def cadastro_limpo(campus_e2e, django_db_blocker):
    """Apaga o prédio/sala que a tarefa 1 cria pela interface — antes e depois.

    O banco da doc é **reusado** entre as seis fatias e ``Predio`` tem ``unique_together
    ('nome', 'uo')``: sem esta limpeza a segunda execução falha no ``Salvar`` com "Prédio com
    este Nome e Campus já existe", e a captura sairia do formulário com erro. Nome fixo (e não
    ``uuid``) porque ele aparece na ilustração.
    """
    from comum.models import Predio

    with django_db_blocker.unblock():
        Predio.objects.filter(nome=PREDIO_NOVO, uo=campus_e2e).delete()
    yield
    with django_db_blocker.unblock():
        Predio.objects.filter(nome=PREDIO_NOVO, uo=campus_e2e).delete()


def test_cadastrar_predio_e_sala(logado_comum, campus_e2e, servidores_comum, cadastro_limpo, capturar):
    """Tarefa 1 — o prédio entra no sistema e ganha a primeira sala reservável.

    As duas etapas moram no admin e são a porta de tudo o mais: sem sala **ativa**,
    **agendável** e com **avaliador**, nenhuma das telas de reserva tem o que mostrar
    (``Sala.is_agendavel`` é a conjunção das três).
    """
    from comum.models import Predio, Sala

    tela = Tela(logado_comum('gestor_predios')).ir(PREDIOS)
    tela.ver_titulo('Prédios')
    anotar('predio-listagem', tela)
    capturar(tela.pagina, 'predio-listagem')

    tela.clicar_botao('Adicionar Prédio')
    tela.esperar()
    anotar('predio-formulario', tela)
    tela.preencher_formulario([('Nome', 'texto', PREDIO_NOVO), ('Campus', 'autocomplete', campus_e2e.sigla)])
    capturar(tela.pagina, 'predio-formulario')
    tela.clicar_botao('Salvar')

    tela.sucesso('Cadastro realizado com sucesso.')
    predio = Predio.objects.filter(nome=PREDIO_NOVO, uo=campus_e2e).first()
    assert predio, 'a UI disse que cadastrou, mas o prédio não persistiu'

    # De volta à listagem: o ícone de exibição da linha leva à ficha do prédio
    # (``Predio.get_absolute_url``). O ``Salvar`` do admin do SUAP não devolve a listagem.
    tela.ir(PREDIOS)
    tela.linha(PREDIO_NOVO).clicar_icone('exibição')
    tela.esperar()
    assert FICHA_PREDIO.format(predio=predio.pk) in tela.pagina.url, f'o ícone da linha não levou à ficha do prédio: {tela.pagina.url}'
    anotar('predio-ficha', tela)
    capturar(tela.pagina, 'predio-ficha')

    # Etapa 2 — a sala.
    tela.ir(SALAS)
    tela.ver_titulo('Salas')
    anotar('sala-listagem', tela)
    capturar(tela.pagina, 'sala-listagem')

    tela.clicar_botao('Adicionar Sala')
    tela.esperar()
    anotar('sala-formulario', tela)
    tela.preencher_formulario(
        [
            ('Nome', 'texto', SALA_NOVA),
            ('Prédio', 'autocomplete', PREDIO_NOVO),
            ('Capacidade da sala', 'texto', '40'),
            ('Agendável', 'checkbox', 'Marcar'),
            ('Avaliadores de Agendamento', 'autocomplete multiplo', servidores_comum['avaliador_sala'].matricula),
            ('Informações complementares', 'textarea', 'Laboratório com 20 computadores e projetor.'),
        ]
    )
    capturar(tela.pagina, 'sala-formulario')
    tela.clicar_botao('Salvar')

    tela.sucesso('Cadastro realizado com sucesso.')
    sala = Sala.objects.filter(nome=SALA_NOVA, predio=predio).first()
    assert sala, 'a UI disse que cadastrou, mas a sala não persistiu'
    # As três condições de `is_agendavel()`, que é o que a tarefa promete ao leitor.
    assert sala.ativa, 'a sala nasceu inativa'
    assert sala.agendavel, 'a sala nasceu sem ser agendável'
    assert sala.avaliadores_de_agendamentos.count() == 1, 'o avaliador escolhido no autocomplete não chegou ao banco'
    assert sala.capacidade == 40, 'a capacidade digitada não chegou ao banco'

    tela.ir(SALAS)
    tela.linha(SALA_NOVA).clicar_icone('exibição')
    tela.esperar()
    assert FICHA_SALA.format(sala=sala.pk) in tela.pagina.url, f'o ícone da linha não levou à ficha da sala: {tela.pagina.url}'
    tela.ver_texto('Agendável')
    anotar('sala-ficha', tela)
    capturar(tela.pagina, 'sala-ficha')


def test_reservar_uma_sala(logado_comum, sala_agendavel, capturar):
    """Tarefa 2 — o servidor acha a sala livre no período e pede a reserva.

    Começa pela **Listagem de Salas Disponíveis** porque é de lá que sai o botão que leva ao
    formulário, e termina na exclusão: enquanto ninguém avaliou, desistir é do solicitante.
    """
    from comum.models import SolicitacaoReservaSala

    justificativa = 'Aula de reforço de Matemática.'
    tela = Tela(logado_comum('solicitante')).ir(SALAS_DISPONIVEIS)
    anotar('salas-disponiveis-filtro', tela)
    tela.preencher_formulario(
        [
            ('Data Inicial', 'data', _dia(5)),
            ('Data Final', 'data', _dia(5)),
            ('Hora Inicial', 'hora', '08:00'),
            ('Hora Final', 'hora', '10:00'),
        ]
    )
    tela.clicar_botao('Enviar')

    tela.ver_texto(sala_agendavel.nome)
    anotar('salas-disponiveis', tela)
    capturar(tela.pagina, 'salas-disponiveis')

    tela.linha(sala_agendavel.nome).clicar_botao('Solicitar/Ver Reservas')
    tela.esperar()
    assert SOLICITAR_RESERVA.format(sala=sala_agendavel.pk) in tela.pagina.url, (
        f'o botão da linha da sala não levou ao formulário de solicitação: {tela.pagina.url}'
    )
    anotar('reserva-formulario', tela)
    tela.preencher_formulario(
        [
            ('Recorrência', 'lista', 'Evento único'),
            ('Data de Início', 'data', _dia(5)),
            ('Data de Fim', 'data', _dia(5)),
            ('Hora de Início', 'hora', '08:00'),
            ('Hora de Fim', 'hora', '10:00'),
            ('Justificativa', 'textarea', justificativa),
        ]
    )
    capturar(tela.pagina, 'reserva-formulario')
    tela.clicar_botao('Salvar')

    tela.sucesso('Solicitação realizada com sucesso.')
    solicitacao = SolicitacaoReservaSala.objects.filter(sala=sala_agendavel, justificativa=justificativa).first()
    assert solicitacao, 'a UI disse que solicitou, mas não persistiu'
    assert solicitacao.status == SolicitacaoReservaSala.STATUS_AGUARDANDO_AVALIACAO

    tela.ir(VER_SOLICITACAO.format(solicitacao=solicitacao.pk))
    tela.ver_texto('Aguardando Avaliação')
    anotar('reserva-solicitacao', tela)
    capturar(tela.pagina, 'reserva-solicitacao')

    # Desistir — o botão que a própria página oferece ao solicitante, num popup do fancybox.
    tela.clicar_botao('Cancelar Solicitação')
    popup = tela.popup()
    anotar('reserva-cancelar-solicitacao', popup)
    popup.preencher('Justificativa do Cancelamento', 'textarea', 'A atividade foi adiada.')
    capturar(tela.pagina, 'reserva-cancelar-solicitacao')
    popup.salvar_no_popup('Salvar')

    solicitacao.refresh_from_db()
    assert solicitacao.cancelada, 'a UI aceitou o cancelamento, mas a solicitação continua ativa'
    # Medido, e é o que a doc afirma: `sala_cancelar_solicitacao` (`comum/views.py:2283`) grava
    # INDEFERIDA junto do cancelamento, de modo que a solicitação desistida aparece como
    # "Indeferida" na listagem — não como "Excluída".
    assert solicitacao.status == SolicitacaoReservaSala.STATUS_INDEFERIDA, 'a solicitação cancelada não ficou com a situação Indeferida'
    tela.ir(VER_SOLICITACAO.format(solicitacao=solicitacao.pk))
    tela.ver_texto('A atividade foi adiada.')


def test_avaliar_solicitacao_de_reserva(logado_comum, solicitacao_pendente, capturar):
    """Tarefa 3 — o avaliador da sala defere (ou indefere) o pedido, e a reserva nasce.

    O deferimento é o ponto em que ``ReservaSala`` é criada (``gerar_reservas``): é a criação,
    e não a mudança de situação, que prova ao leitor que a sala ficou reservada.
    """
    from comum.models import ReservaSala, SolicitacaoReservaSala

    tela = Tela(logado_comum('avaliador_sala')).ir(SOLICITACOES)
    tela.clicar_aba('Solicitações a Avaliar')
    tela.ver_texto(solicitacao_pendente.sala.nome)
    anotar('solicitacoes-listagem', tela)
    capturar(tela.pagina, 'solicitacoes-listagem')

    tela.linha(solicitacao_pendente.sala.nome).clicar_icone('exibição')
    tela.esperar()
    tela.ver_texto('Aguardando Avaliação')
    anotar('solicitacao-ficha', tela)
    capturar(tela.pagina, 'solicitacao-ficha')

    # `class="btn success popup"`: a avaliação abre num popup do fancybox, não numa página.
    tela.clicar_botao('Avaliar Solicitação')
    popup = tela.popup()
    anotar('avaliacao-formulario', popup)
    popup.preencher_formulario([('Situação', 'lista', 'Deferida'), ('Observação', 'textarea', 'Sala livre no período solicitado.')])
    capturar(tela.pagina, 'avaliacao-formulario')
    popup.salvar_no_popup('Salvar')

    tela.sucesso('Avaliação realizada com sucesso.')
    solicitacao_pendente.refresh_from_db()
    assert solicitacao_pendente.status == SolicitacaoReservaSala.STATUS_DEFERIDA, 'a avaliação não mudou a situação da solicitação'
    assert ReservaSala.objects.filter(solicitacao=solicitacao_pendente, cancelada=False).exists(), 'deferiu sem gerar a reserva correspondente'

    tela.ir(RESERVAS)
    tela.ver_texto(solicitacao_pendente.sala.nome)
    anotar('reservas-deferidas', tela)
    capturar(tela.pagina, 'reservas-deferidas')


def test_registrar_ocorrencia_e_cancelar_a_reserva(logado_comum, reserva_deferida, capturar):
    """Tarefa 4, etapas 1 e 2 — o avaliador registra se a atividade ocorreu e cancela a reserva.

    Cancelar a última reserva ativa rebaixa a solicitação para indeferida
    (``ReservaSala.cancelar``): é o efeito colateral que a doc precisa avisar.
    """
    from comum.models import SolicitacaoReservaSala

    solicitacao, reserva = reserva_deferida
    # As duas ações moram na tabela *Reservas* da própria solicitação, e as duas abrem popup.
    tela = Tela(logado_comum('avaliador_sala')).ir(VER_SOLICITACAO.format(solicitacao=solicitacao.pk))
    tela.ver_texto('Deferida')
    anotar('reserva-quadro-reservas', tela)
    capturar(tela.pagina, 'reserva-quadro-reservas')

    tela.clicar_botao('Informar ocorrência')
    popup = tela.popup()
    anotar('reserva-ocorrencia', popup)
    popup.preencher('Atividade Ocorreu', 'lista', 'Sim')
    capturar(tela.pagina, 'reserva-ocorrencia')
    popup.salvar_no_popup('Salvar')

    tela.sucesso('Operação realizada com sucesso.')
    reserva.refresh_from_db()
    assert reserva.ocorreu is True, 'a UI aceitou a ocorrência, mas não persistiu'

    tela.clicar_botao('Cancelar Reserva')
    popup = tela.popup()
    anotar('reserva-cancelamento', popup)
    popup.preencher('Justificativa do Cancelamento', 'textarea', 'Sala interditada pela manutenção.')
    capturar(tela.pagina, 'reserva-cancelamento')
    popup.salvar_no_popup('Salvar')

    tela.sucesso('Cancelamento realizado com sucesso.')
    reserva.refresh_from_db()
    solicitacao.refresh_from_db()
    assert reserva.cancelada, 'a reserva não foi cancelada'
    assert solicitacao.status == SolicitacaoReservaSala.STATUS_INDEFERIDA, 'cancelar a única reserva deveria indeferir a solicitação'


def test_cancelar_as_reservas_da_sala_por_periodo(logado_comum, reserva_deferida, capturar):
    """Tarefa 4, etapa 3 — o cancelamento em lote, a partir da ficha da sala.

    Fixture própria (e não a continuação do teste anterior) porque o lote precisa de uma
    reserva **ativa** no intervalo; encadear os dois deixaria o filtro sem nada a cancelar e a
    asserção provaria o contrário do que a doc afirma.
    """
    solicitacao, reserva = reserva_deferida
    tela = Tela(logado_comum('avaliador_sala')).ir(FICHA_SALA.format(sala=solicitacao.sala.pk))
    tela.clicar_botao('Cancelar Reservas por Período')
    tela.esperar()
    assert CANCELAR_RESERVAS_PERIODO.format(sala=solicitacao.sala.pk) in tela.pagina.url, (
        f'o botão da ficha da sala não levou ao cancelamento em lote: {tela.pagina.url}'
    )
    anotar('reserva-cancelamento-periodo', tela)
    tela.preencher_formulario(
        [
            ('Data de Início do Cancelamento', 'data', _dia(0)),
            ('Data de Término do Cancelamento', 'data', _dia(30)),
            ('Justificativa do Cancelamento', 'textarea', 'Reforma do bloco.'),
        ]
    )
    capturar(tela.pagina, 'reserva-cancelamento-periodo')
    tela.clicar_botao('Enviar')

    tela.sucesso('Cancelamento realizado com sucesso.')
    reserva.refresh_from_db()
    assert reserva.cancelada, 'o cancelamento por período não alcançou a reserva do intervalo'


def test_indisponibilizar_uma_sala(logado_comum, sala_agendavel, capturar):
    """Tarefa 5 — tirar a sala da agenda para manutenção, sem que haja solicitação nenhuma.

    Pela porta longa (o botão da listagem), que é a do menu: ela obriga a descer a cadeia
    ``Campus → Prédio → Sala`` em ``select`` encadeados, e só oferece sala que o usuário
    avalia.
    """
    from comum.models import IndisponibilizacaoSala

    tela = Tela(logado_comum('avaliador_sala')).ir(LISTAR_INDISPONIBILIZACOES)
    tela.ver_botao('Registrar Indisponibilização')
    anotar('indisponibilizacao-listagem', tela)
    capturar(tela.pagina, 'indisponibilizacao-listagem')

    tela.clicar_botao('Registrar Indisponibilização')
    tela.esperar()
    anotar('indisponibilizacao-formulario', tela)
    tela.preencher_formulario(
        [
            ('Campus', 'lista', str(sala_agendavel.predio.uo)),
            ('Prédio', 'lista', sala_agendavel.predio.nome),
            ('Sala', 'lista', sala_agendavel.nome),
            ('Data/Hora de Início', 'data e hora', _momento(15, 8)),
            ('Data/Hora Final', 'data e hora', _momento(15, 18)),
            ('Justificativa', 'textarea', 'Troca do piso e pintura.'),
        ]
    )
    capturar(tela.pagina, 'indisponibilizacao-formulario')
    tela.clicar_botao('Salvar')

    tela.sucesso('Cadastro realizado com sucesso.')
    registro = IndisponibilizacaoSala.objects.filter(sala=sala_agendavel, justificativa='Troca do piso e pintura.').first()
    assert registro, 'a UI disse que cadastrou, mas a indisponibilização não persistiu'
    assert (registro.data_inicio.hour, registro.data_fim.hour) == (8, 18), 'o período digitado não chegou ao banco'

    # A listagem tem duas abas: "Qualquer" (todos os registros) e "Salas Atualmente em
    # Manutenção" (só o que está em curso agora) — o registro recém-criado é futuro e só
    # aparece na primeira.
    tela.ir(LISTAR_INDISPONIBILIZACOES)
    tela.clicar_aba('Qualquer')
    tela.ver_texto(str(registro.sala))
    anotar('indisponibilizacao-registrada', tela)
    capturar(tela.pagina, 'indisponibilizacao-registrada')

    # A outra aba recorta pelo instante atual: o registro é futuro e NÃO pode aparecer nela.
    tela.clicar_aba('Salas Atualmente em Manutenção')
    assert str(registro.sala) not in ' '.join(tela.pagina.locator('//main').all_inner_texts()), (
        'indisponibilização futura não pode aparecer como sala em manutenção agora'
    )

    tela.clicar_aba('Qualquer')
    # A remoção é um botão de formulário POST (não link), fora do alcance de `clicar_icone`.
    tela.linha(str(registro.sala)).loc('//button[contains(@class, "icon-delete")]').first.click()
    tela.esperar()
    tela.sucesso('Indisponibilização removida com sucesso.')
    assert not IndisponibilizacaoSala.objects.filter(pk=registro.pk).exists(), 'a UI disse que removeu, mas o registro continua no banco'


def test_consultar_os_indicadores_de_uso(logado_comum, reserva_deferida, capturar):
    """Tarefa 6 — quanto cada sala do prédio foi usada no período."""
    solicitacao, _reserva = reserva_deferida
    tela = Tela(logado_comum('avaliador_sala')).ir(INDICADORES)
    anotar('indicadores-filtro', tela)
    tela.preencher_formulario(
        [
            ('Data Inicial', 'data', _dia(0)),
            ('Data Final', 'data', _dia(30)),
            ('Campus', 'lista', str(solicitacao.sala.predio.uo)),
            ('Prédio', 'lista', solicitacao.sala.predio.nome),
        ]
    )
    tela.clicar_botao('Enviar')

    tela.ver_texto(solicitacao.sala.nome)
    anotar('indicadores', tela)
    capturar(tela.pagina, 'indicadores')


def test_minhas_salas_lista_as_que_o_avaliador_julga(logado_comum, sala_agendavel, capturar):
    """A aba ``Minhas Salas`` do menu ``Reservas de Salas`` — porta do avaliador para as suas salas.

    Entrada de menu própria (``Administração::Reservas de Salas::Salas``), com filtro já
    aplicado na URL; sem este teste a doc afirmaria o recorte da aba por leitura do admin.
    """
    tela = Tela(logado_comum('avaliador_sala')).ir(MINHAS_SALAS)
    tela.ver_texto(sala_agendavel.nome)
    anotar('minhas-salas', tela)
    capturar(tela.pagina, 'minhas-salas')
