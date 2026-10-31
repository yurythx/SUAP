"""Ciclo de vida da reserva de sala: solicitar → avaliar → ocorrência → cancelar/excluir.

É onde mora a regra de negócio da família salas. Cada transição tem guarda própria de model
(``pode_avaliar``, ``pode_cancelar``, ``pode_excluir``, ``pode_ver``), todas combinando papel,
situação e *data futura* — e todas escritas à mão em ``comum/models.py``, sem máquina de estado
que as mantenha coerentes. A regressão que este arquivo pega é a de sempre nesse desenho: uma
guarda muda e a transição vizinha passa a ser permitida (ou negada) calada.

Todas as ações desta família redirecionam com ``httprr('..')``, e ``'..'`` **não** é resolvido
como caminho relativo: ``djtools/utils/response.py:130`` o troca por
``breadcrumbs_previous_url(request)``, a trilha de navegação da sessão. Medido — o destino é a
página anterior (ou ``/``) e o banner de sucesso chega inteiro. Por isso a asserção de UI aqui é
o banner, como manda a receita, e não uma inspeção da tela de destino.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

import pytest
from playwright.sync_api import expect

from djtools.e2e_ui import Tela

from .conftest import postar

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# Rotas como literais de módulo — é o que o gate `--rotas` colhe. O `{marcador}` não tem barra,
# então casa o `[^/]+` que o gate deriva de `<int:pk>` e o literal continua legível como rota.
SOLICITAR_RESERVA = '/comum/sala/solicitar_reserva/{sala}/'
VER_SOLICITACAO = '/comum/sala/ver_solicitacao/{solicitacao}/'
AVALIAR_SOLICITACAO = '/comum/sala/avaliar_solicitacao/{solicitacao}/'
CANCELAR_SOLICITACAO = '/comum/sala/cancelar_solicitacao/{solicitacao}/'
EXCLUIR_SOLICITACAO = '/comum/sala/excluir_solicitacao/{solicitacao}/'
CANCELAR_RESERVA = '/comum/sala/cancelar_reserva/{reserva}/'
INFORMAR_OCORRENCIA = '/comum/sala/informar_ocorrencia/{reserva}/'
CANCELAR_RESERVAS_PERIODO = '/comum/sala/cancelar_reservas_periodo/{sala}/'

# O rótulo do submit NÃO é escolha da tela: `render_form` põe "Salvar" quando o form é
# `ModelForm` e deixa o default "Enviar" quando não é (`djtools/templatetags/tags/utils.py:263-267`).
# Daí `Salvar` nas telas de solicitação/avaliação/cancelamento e `Enviar` no cancelamento por
# período, que é um `FormPlus` simples.


def _daqui_a(dias: int) -> str:
    """Data futura em ``dd/mm/aaaa``.

    Sempre à frente porque ``SolicitacaoReservaSalaForm.clean`` recusa data/hora já passada e
    as três guardas de transição exigem ``data_hora_fim`` no futuro. Relativa ao dia da
    execução, e não fixa, porque o banco de e2e é reusado: data fixa acabaria no passado.
    """
    return (datetime.now() + timedelta(days=dias)).strftime('%d/%m/%Y')


def test_solicitar_reserva_e_deferir(logado_comum, sala_agendavel):
    """O ciclo completo pela interface: o servidor pede a sala e o avaliador defere.

    Um teste só, e não quatro, porque avaliar uma solicitação que não existe não é um cenário —
    a cadeia é o que se está afirmando. O deferimento é o ponto em que ``ReservaSala`` nasce
    (``SolicitacaoReservaSalaAvaliarForm.save`` chama ``gerar_reservas``), e é essa criação, não
    a mudança de situação, que prova que a avaliação funcionou.
    """
    from comum.models import ReservaSala, SolicitacaoReservaSala

    justificativa = f'Defesa de TCC na sala {sala_agendavel.nome}'
    tela = Tela(logado_comum('solicitante')).ir(SOLICITAR_RESERVA.format(sala=sala_agendavel.pk))
    tela.preencher_formulario(
        [
            ('Recorrência', 'lista', 'Evento único'),
            ('Data de Início', 'data', _daqui_a(7)),
            ('Data de Fim', 'data', _daqui_a(7)),
            ('Hora de Início', 'hora', '14:00'),
            ('Hora de Fim', 'hora', '16:00'),
            ('Justificativa', 'textarea', justificativa),
        ]
    )
    tela.clicar_botao('Salvar')

    tela.sucesso('Solicitação realizada com sucesso.')
    solicitacao = SolicitacaoReservaSala.objects.filter(sala=sala_agendavel, justificativa=justificativa).first()
    assert solicitacao, 'a UI disse que solicitou, mas não persistiu'
    assert solicitacao.status == SolicitacaoReservaSala.STATUS_AGUARDANDO_AVALIACAO
    # Confere o valor dos campos de HORA, não só que o formulário salvou. `hora_inicio`/`hora_fim`
    # usam `RegionalTimeWidget`, `input[type=time]` sem `step=1` — o Chromium normaliza
    # `14:00:00` para `14:00` ali. Sem esta asserção, um
    # preenchedor que escrevesse no campo errado (ou em nenhum) passaria calado, porque o form
    # tem valor inicial para todos eles.
    assert (solicitacao.hora_inicio, solicitacao.hora_fim) == (time(14, 0), time(16, 0)), 'as horas digitadas não chegaram ao banco'
    assert solicitacao.data_inicio == (datetime.now() + timedelta(days=7)).date(), 'a data digitada não chegou ao banco'

    avaliador = Tela(logado_comum('avaliador_sala')).ir(VER_SOLICITACAO.format(solicitacao=solicitacao.pk))
    avaliador.ver_texto('Aguardando Avaliação')
    avaliador.ver_botao('Avaliar Solicitação')

    avaliador.ir(AVALIAR_SOLICITACAO.format(solicitacao=solicitacao.pk))
    avaliador.preencher_formulario(
        [
            ('Situação', 'lista', 'Deferida'),
            ('Observação', 'textarea', 'Sala livre no período.'),
        ]
    )
    avaliador.clicar_botao('Salvar')

    avaliador.sucesso('Avaliação realizada com sucesso.')
    solicitacao.refresh_from_db()
    assert solicitacao.status == SolicitacaoReservaSala.STATUS_DEFERIDA, 'a avaliação não mudou a situação da solicitação'
    assert ReservaSala.objects.filter(solicitacao=solicitacao, cancelada=False).exists(), 'deferiu sem gerar a reserva correspondente'

    avaliador.ir(VER_SOLICITACAO.format(solicitacao=solicitacao.pk))
    avaliador.ver_texto('Deferida')
    avaliador.ver_texto('Sala livre no período.')


def test_clonar_solicitacao_reaproveita_os_dados_da_original(logado_comum, solicitacao_pendente):
    """O ``?solicitacao=`` de ``sala_solicitar_reserva`` é um ramo próprio da view: ele copia
    recorrência, período e justificativa da solicitação de origem para o formulário novo.

    Vale o teste porque o ramo do clone é o único lugar em que o formulário nasce com
    ``initial`` vindo de outro registro — e um campo que saia dessa cópia passa despercebido: a
    tela continua abrindo, só vem vazia.
    """
    from comum.models import SolicitacaoReservaSala

    rota = SOLICITAR_RESERVA.format(sala=solicitacao_pendente.sala.pk)
    tela = Tela(logado_comum('solicitante')).ir(f'{rota}?solicitacao={solicitacao_pendente.pk}')

    assert tela.campo('Justificativa', 'textarea').first.input_value() == solicitacao_pendente.justificativa

    # Muda só a data, para não colidir com a própria solicitação de origem.
    tela.preencher_formulario([('Data de Início', 'data', _daqui_a(20)), ('Data de Fim', 'data', _daqui_a(20))])
    tela.clicar_botao('Salvar')

    tela.sucesso('Solicitação realizada com sucesso.')
    clones = SolicitacaoReservaSala.objects.filter(sala=solicitacao_pendente.sala, justificativa=solicitacao_pendente.justificativa)
    assert clones.count() == 2, 'o clone não persistiu com a justificativa da solicitação de origem'


def test_informar_ocorrencia_e_cancelar_a_reserva(logado_comum, reserva_deferida):
    """Depois de deferida, o avaliador registra se a atividade ocorreu e pode cancelar a reserva.

    As duas telas vivem na mesma linha da tabela de reservas de ``ver_solicitacao``, e o
    cancelamento tem efeito colateral no pai: ``ReservaSala.cancelar`` rebaixa a solicitação
    para indeferida quando não sobra reserva ativa — é esse encadeamento que se afirma.
    """
    from comum.models import SolicitacaoReservaSala

    solicitacao, reserva = reserva_deferida
    tela = Tela(logado_comum('avaliador_sala')).ir(INFORMAR_OCORRENCIA.format(reserva=reserva.pk))
    tela.preencher('Atividade Ocorreu', 'lista', 'Sim')
    tela.clicar_botao('Salvar')

    tela.sucesso('Operação realizada com sucesso.')
    reserva.refresh_from_db()
    assert reserva.ocorreu is True, 'a UI aceitou a ocorrência, mas não persistiu'

    tela.ir(CANCELAR_RESERVA.format(reserva=reserva.pk))
    tela.preencher('Justificativa do Cancelamento', 'textarea', 'Sala interditada pela manutenção.')
    tela.clicar_botao('Salvar')

    tela.sucesso('Cancelamento realizado com sucesso.')
    reserva.refresh_from_db()
    solicitacao.refresh_from_db()
    assert reserva.cancelada, 'a reserva não foi cancelada'
    assert solicitacao.status == SolicitacaoReservaSala.STATUS_INDEFERIDA, 'cancelar a única reserva deveria indeferir a solicitação'

    tela.ir(VER_SOLICITACAO.format(solicitacao=solicitacao.pk))
    tela.ver_texto('Cancelada')
    tela.ver_texto('Sala interditada pela manutenção.')


def test_cancelar_solicitacao_pelo_solicitante(logado_comum, reserva_deferida):
    """Quem pediu pode desistir enquanto o período não passou — e isso cancela as reservas geradas.

    ``SolicitacaoReservaSalaCancelarForm.save`` percorre ``reservasala_set`` e cancela uma a
    uma; afirmar só a solicitação deixaria passar uma reserva órfã ainda ocupando a agenda.
    """
    solicitacao, reserva = reserva_deferida
    tela = Tela(logado_comum('solicitante')).ir(CANCELAR_SOLICITACAO.format(solicitacao=solicitacao.pk))

    tela.preencher('Justificativa do Cancelamento', 'textarea', 'O evento foi adiado.')
    tela.clicar_botao('Salvar')

    tela.sucesso('Cancelamento realizado com sucesso.')
    solicitacao.refresh_from_db()
    reserva.refresh_from_db()
    assert solicitacao.cancelada, 'a UI aceitou o cancelamento, mas a solicitação continua ativa'
    assert reserva.cancelada, 'cancelar a solicitação tem de cancelar as reservas que ela gerou'

    tela.ir(VER_SOLICITACAO.format(solicitacao=solicitacao.pk))
    tela.ver_texto('O evento foi adiado.')


def test_excluir_solicitacao_ainda_nao_avaliada(logado_comum, solicitacao_pendente):
    """Excluir é a saída de quem pediu e mudou de ideia **antes** de a avaliação acontecer.

    A exclusão exige POST (``require_POST``): um GET — *prefetch* de link, crawler — responde 405
    e não toca a solicitação. Pela tela, o gesto é o ícone de remoção da listagem do admin, um
    botão que submete o ``#changelist-form`` (que já carrega o CSRF) para a rota de exclusão.
    """
    from comum.models import SolicitacaoReservaSala

    url = EXCLUIR_SOLICITACAO.format(solicitacao=solicitacao_pendente.pk)
    tela = Tela(logado_comum('solicitante'))
    assert tela.buscar(url).status == 405, 'a exclusão por GET tem de responder 405'
    solicitacao_pendente.refresh_from_db()
    assert solicitacao_pendente.status != SolicitacaoReservaSala.STATUS_EXCLUIDA, 'o GET excluiu a solicitação'

    tela.ir('/admin/comum/solicitacaoreservasala/')
    remover = tela.loc(f'//button[@formaction="{url}"]')
    expect(remover).to_be_visible()
    remover.click()

    tela.sucesso('Reserva de Sala excluída com sucesso.')
    solicitacao_pendente.refresh_from_db()
    assert solicitacao_pendente.status == SolicitacaoReservaSala.STATUS_EXCLUIDA, 'a UI disse que excluiu, mas a situação não mudou'


def test_cancelar_reservas_da_sala_por_periodo(logado_comum, reserva_deferida):
    """Cancelamento em lote: o avaliador fecha a sala num intervalo e derruba o que houver nele.

    É a única tela da família que opera sobre um conjunto de reservas em vez de uma; o filtro é
    por ``data_inicio__date__gte``/``data_fim__date__lte``, então um intervalo que não abranja
    a reserva a deixaria intacta — daí o teste afirmar a reserva cancelada, e não a mensagem.
    """
    solicitacao, reserva = reserva_deferida
    tela = Tela(logado_comum('avaliador_sala')).ir(CANCELAR_RESERVAS_PERIODO.format(sala=solicitacao.sala.pk))

    tela.preencher_formulario(
        [
            ('Data de Início do Cancelamento', 'data', _daqui_a(0)),
            ('Data de Término do Cancelamento', 'data', _daqui_a(30)),
            ('Justificativa do Cancelamento', 'textarea', 'Reforma do bloco.'),
        ]
    )
    tela.clicar_botao('Enviar')

    tela.sucesso('Cancelamento realizado com sucesso.')
    reserva.refresh_from_db()
    assert reserva.cancelada, 'o cancelamento por período não alcançou a reserva do intervalo'
    assert reserva.justificativa_cancelamento == 'Reforma do bloco.'


def test_sala_restrita_recusa_servidor_de_outro_campus(logado_comum, sala_restrita_ao_campus):
    """``restringir_agendamentos_no_campus`` compara o campus da sala com o do usuário.

    Guarda de acesso e não de conveniência: o papel aqui tem ``add_solicitacaoreservasala``
    (grupo ``Servidor``) e até avalia a sala — o que o barra é só o campus. Se a comparação
    cair numa refatoração de ``get_uo``, a sala de um campus passa a ser agendável por toda a
    instituição sem nenhum sintoma visível.
    """
    tela = Tela(logado_comum('avaliador_outro_campus'))

    resposta = tela.buscar(SOLICITAR_RESERVA.format(sala=sala_restrita_ao_campus.pk))

    assert resposta.status == 403, f'a sala restrita ao campus respondeu {resposta.status} para servidor de outro campus'


def test_sala_sem_avaliador_nao_aceita_solicitacao(logado_comum, sala_sem_avaliador):
    """RN4: sala ativa e marcada como agendável ainda **não** é agendável sem avaliador.

    A regra é a conjunção das três condições (``Sala.is_agendavel``), e é a terceira que se
    perde ao remover o último avaliador de uma sala — a tela continua acessível e o usuário
    preencheria um formulário que ninguém julgaria. A view corta antes, com mensagem própria
    que nomeia a causa.
    """
    tela = Tela(logado_comum('solicitante')).ir(SOLICITAR_RESERVA.format(sala=sala_sem_avaliador.pk))

    tela.erro('Sala não está disponível para agendamento, pois não tem avaliadores.')


# (rota, papel, por que é negado). O papel é a variável do experimento: as três rotas abaixo
# passam pelo `permission_required` do decorador — o papel TEM a permissão de model — e são
# barradas pela guarda de negócio dentro da view, que é a fronteira que interessa medir.
# `gestor_predios` e `solicitante` são ambos do grupo `Servidor`, que dá
# `view_/delete_solicitacaoreservasala`; o que os separa é o vínculo com a solicitação.
NEGADOS_NA_SOLICITACAO_PENDENTE = [
    (VER_SOLICITACAO, 'gestor_predios', '`pode_ver`: não é solicitante nem avaliador, e a solicitação ainda não foi deferida'),
    (EXCLUIR_SOLICITACAO, 'avaliador_sala', '`pode_excluir`: excluir é do solicitante (ou do superusuário), não de quem avalia'),
    (CANCELAR_SOLICITACAO, 'gestor_predios', '`pode_cancelar`: exige ser o solicitante ou avaliador da sala'),
    (AVALIAR_SOLICITACAO, 'solicitante', 'falta a permissão `pode_avaliar_solicitacao_reserva_de_sala` (grupo Avaliador de Sala)'),
]


@pytest.mark.parametrize(
    ('rota', 'papel', 'motivo'), NEGADOS_NA_SOLICITACAO_PENDENTE, ids=[caso[1] + ' ' + caso[0] for caso in NEGADOS_NA_SOLICITACAO_PENDENTE]
)
def test_transicoes_negadas_na_solicitacao_pendente(logado_comum, solicitacao_pendente, rota, papel, motivo):
    """Matriz de acesso das transições, medida no navegador por status HTTP — não por texto."""
    tela = Tela(logado_comum(papel))
    url = rota.format(solicitacao=solicitacao_pendente.pk)

    # A exclusão só aceita POST: por GET, o 405 viria antes da guarda que se quer medir.
    resposta = postar(tela.pagina, url) if rota == EXCLUIR_SOLICITACAO else tela.buscar(url)

    assert resposta.status == 403, f'{rota} respondeu {resposta.status} para {papel}; deveria negar por {motivo}'


def test_solicitacao_ja_deferida_nao_e_avaliada_de_novo(logado_comum, reserva_deferida):
    """``pode_avaliar`` exige situação "aguardando avaliação": deferir duas vezes duplicaria as reservas.

    Distinto do caso do ``solicitante`` na matriz acima: ali quem barra é o decorador de
    permissão; aqui o papel **tem** a permissão e é o avaliador da sala — quem barra é a guarda
    de situação dentro da view, que é a que pode se perder numa refatoração.
    """
    solicitacao, _reserva = reserva_deferida
    tela = Tela(logado_comum('avaliador_sala'))

    resposta = tela.buscar(AVALIAR_SOLICITACAO.format(solicitacao=solicitacao.pk))

    assert resposta.status == 403, f'a avaliação de solicitação já deferida respondeu {resposta.status}'


NEGADOS_NA_RESERVA_DEFERIDA = [
    ('reserva', INFORMAR_OCORRENCIA, 'solicitante', 'informar ocorrência é de quem avalia a sala'),
    ('reserva', CANCELAR_RESERVA, 'gestor_predios', '`ReservaSala.pode_cancelar`: exige avaliador da sala ou o próprio solicitante'),
    ('sala', CANCELAR_RESERVAS_PERIODO, 'solicitante', 'o cancelamento em lote é de quem avalia a sala'),
]


@pytest.mark.parametrize(
    ('alvo', 'rota', 'papel', 'motivo'), NEGADOS_NA_RESERVA_DEFERIDA, ids=[caso[2] + ' ' + caso[1] for caso in NEGADOS_NA_RESERVA_DEFERIDA]
)
def test_acoes_sobre_a_reserva_negadas_a_quem_nao_avalia(logado_comum, reserva_deferida, alvo, rota, papel, motivo):
    """Mesma matriz, do lado da reserva já gerada."""
    solicitacao, reserva = reserva_deferida
    pk = reserva.pk if alvo == 'reserva' else solicitacao.sala.pk
    tela = Tela(logado_comum(papel))

    resposta = tela.buscar(rota.format(reserva=pk, sala=pk))

    assert resposta.status == 403, f'{rota} respondeu {resposta.status} para {papel}; deveria negar porque {motivo}'
