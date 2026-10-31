"""Fluxo: os recursos do coordenador depois da seleção — contra as notas (ao avaliador) e contra o edital (à gestão).

Encerrada a seleção e antes da data limite de recursos, o coordenador do projeto pré-selecionado
vê o projeto em "Meus recursos" e, na tela do projeto, "Interpor Recurso":

* **Das Notas** — escolhe itens da ficha (``interpor_recurso``) e escreve o recurso de cada um
  (``itens_selecionados_para_recursos``); o avaliador daquela ficha o julga em "Avaliar recursos"
  (``avaliar_recursos`` → ``avaliar_recurso``) e, aceito, a nota do critério muda.
* **Do Edital** — uma justificativa (``enviar_recurso``) que o Coordenador de Extensão do campus
  (edital de campus) ou o Gerente Sistêmico lista em "Solicitações de recurso" e avalia
  (``avaliar_recurso_projeto``); o gerente consulta o detalhe (``recurso_projeto``).

A regressão cara é o recurso não chegar a quem julga (o coordenador perde o prazo sem saber), ou
alguém recorrer/julgar o que não é seu: toda rota recebe o id do projeto, do item ou do recurso.
O julgamento aceito muda nota e passa por ``Avaliacao.save`` (reclassifica): edital descartável.
"""

from __future__ import annotations

import datetime
import re
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import Locator, expect

from djtools.e2e_ui import Tela
from projetos.tests.e2e.conftest import avaliacao_de, clicar_em, outra_uo, vinculo

if TYPE_CHECKING:
    from projetos.models import ItemAvaliacao, Projeto, RecursoProjeto

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

PROJETO = '/projetos/projeto/{}/'
MEUS_RECURSOS = '/projetos/meus_recursos/'
INTERPOR_RECURSO = '/projetos/interpor_recurso/{}/'
ITENS_SELECIONADOS = '/projetos/itens_selecionados_para_recursos/{}/'
ENVIAR_RECURSO = '/projetos/enviar_recurso/{}/'
AVALIAR_RECURSOS = '/projetos/avaliar_recursos/'
AVALIAR_RECURSO = '/projetos/avaliar_recurso/{}/'
SOLICITACOES = '/projetos/solicitacoes_de_recurso/'
AVALIAR_RECURSO_PROJETO = '/projetos/avaliar_recurso_projeto/{}/'
RECURSO_PROJETO = '/projetos/recurso_projeto/{}/'

ENCAMINHADO = 'Recurso encaminhado para análise.'


def celula(tela: Tela, texto: str) -> Locator:
    """A célula com exatamente ``texto`` — a mesma sonda serve à presença e à ausência."""
    return tela.loc(f'//td[normalize-space(.)="{texto}"]')


def com_recurso_na_nota(item: ItemAvaliacao, texto: str = 'A nota não considerou o público atendido.') -> ItemAvaliacao:
    """O recurso do coordenador já interposto contra a nota do item (o que ``itens_selecionados_para_recursos`` grava)."""
    from projetos.models import ItemAvaliacao

    ItemAvaliacao.objects.filter(pk=item.pk).update(
        texto_recurso=texto, recurso_em=datetime.datetime.now(), recurso_por=item.avaliacao.projeto.vinculo_coordenador
    )
    item.refresh_from_db()
    return item


def recurso_do_edital(projeto: Projeto, **campos: object) -> RecursoProjeto:
    from projetos.tests.factories import RecursoProjetoFactory

    return RecursoProjetoFactory(projeto=projeto, justificativa=f'Recurso contra o edital: {projeto.titulo}', **campos)


def interpor_recurso_pelo_menu(tela: Tela, projeto: Projeto, rota: str) -> Tela:
    """Tela do projeto → "Interpor Recurso" (submenu da action-bar) → "Das Notas"/"Do Edital"."""
    tela.ir(PROJETO.format(projeto.pk)).clicar_botao('Interpor Recurso')
    return clicar_em(tela, rota.format(projeto.pk))


# ------------------------------------------------------------------ contra as notas


def test_coordenador_interpoe_recurso_contra_a_nota(logado_projetos, projeto_avaliado):
    """ "Meus recursos" lista o projeto; "Das Notas" → item da ficha → texto do recurso → o recurso fica no item."""
    item = projeto_avaliado()
    projeto = item.avaliacao.projeto
    tela = Tela(logado_projetos('coordenador_projeto')).ir(MEUS_RECURSOS)

    tela.ver_titulo('Projetos em período de interposição de recursos')
    expect(celula(tela, projeto.titulo)).to_have_count(1)
    interpor_recurso_pelo_menu(tela, projeto, INTERPOR_RECURSO)
    tela.ver_titulo(f'Interpor Recurso - {projeto.titulo} - {projeto.edital.titulo}').selecionar_item('Avaliador #1').clicar_botao('Continuar >>')
    expect(tela.pagina).to_have_url(re.compile(re.escape(ITENS_SELECIONADOS.format(projeto.pk))))
    tela.esperar().preencher('Interpor recurso', 'textarea', 'A nota não considerou o público atendido.').clicar_botao('Submeter recurso')

    tela.esperar().sucesso(ENCAMINHADO)
    item.refresh_from_db()
    assert item.texto_recurso == 'A nota não considerou o público atendido.', 'a UI disse que encaminhou, mas o recurso não ficou no item'
    assert (item.recurso_por, item.recurso_em is not None) == (vinculo('coordenador_projeto'), True), 'o recurso não registrou quem e quando'


def test_avaliador_aceita_o_recurso_e_muda_a_nota(logado_projetos, projeto_avaliado):
    """ "Avaliar recursos" → "Avaliar recurso": aceito, a nota do critério vira a nova e a original fica guardada."""
    item = com_recurso_na_nota(projeto_avaliado(nota=5))
    projeto = item.avaliacao.projeto
    tela = Tela(logado_projetos('avaliador')).ir(AVALIAR_RECURSOS)

    tela.ver_titulo('Lista de recursos interpostos contra as notas').linha(projeto.titulo)
    clicar_em(tela, AVALIAR_RECURSO.format(item.pk))
    tela.ver_titulo('Avaliar Recurso').ver_texto('A nota não considerou o público atendido.')
    tela.preencher('Recurso aceito', 'checkbox', 'Sim')  # "Pontuação final" só é habilitada (por JS) com o aceite marcado
    tela.preencher_formulario([('Pontuação final', 'lista', '7.0'), ('Resposta ao recurso', 'textarea', 'Recurso procedente.')])
    tela.clicar_botao('Salvar')

    tela.esperar().ver_titulo('Lista de recursos interpostos contra as notas').sucesso('Recurso avaliado com sucesso.')
    item.refresh_from_db()
    assert (item.recurso_aceito, item.pontuacao, item.pontuacao_original) == (True, Decimal(7), Decimal(5)), 'o aceite não mudou a nota'
    assert (item.recurso_avaliado_por, item.resposta_recurso) == (vinculo('avaliador'), 'Recurso procedente.'), (
        'o julgamento não registrou quem/resposta'
    )
    item.avaliacao.refresh_from_db()
    assert item.avaliacao.pontuacao == Decimal(7), 'a nota do critério mudou, mas a avaliação não foi recalculada'


@pytest.fixture
def duas_fichas_com_recurso(projeto_avaliado) -> dict[str, ItemAvaliacao]:
    """O mesmo projeto avaliado pelo ``avaliador`` e pelo ``segundo_avaliador``, com recurso contra as duas notas."""
    meu = com_recurso_na_nota(projeto_avaliado())
    return {'meu': meu, 'do outro': com_recurso_na_nota(avaliacao_de(meu.avaliacao.projeto, 'segundo_avaliador'))}


def test_avaliador_so_julga_recurso_contra_a_propria_nota(logado_projetos, duas_fichas_com_recurso):
    """A lista mostra só o recurso contra a nota dele; o do outro avaliador, pela URL, responde 403 e fica intacto."""
    meu, do_outro = duas_fichas_com_recurso['meu'], duas_fichas_com_recurso['do outro']
    tela = Tela(logado_projetos('avaliador')).ir(AVALIAR_RECURSOS)

    expect(tela.loc(f'//a[@href="{AVALIAR_RECURSO.format(meu.pk)}"]')).to_have_count(1)
    assert not tela.loc(f'//a[@href="{AVALIAR_RECURSO.format(do_outro.pk)}"]').count(), 'a lista ofereceu o recurso contra a nota de outro avaliador'
    respostas = {nome: tela.buscar(AVALIAR_RECURSO.format(item.pk)).status for nome, item in duas_fichas_com_recurso.items()}
    assert respostas == {'meu': 200, 'do outro': 403}

    do_outro.refresh_from_db()
    assert do_outro.recurso_avaliado_em is None, 'o recurso contra a nota do outro avaliador foi julgado'


def test_gerente_filtra_todos_os_recursos_pendentes(logado_projetos, duas_fichas_com_recurso):
    """Sem filtro a lista do gerente traz só os recursos contra notas DELE (nenhum); "Ver todos" + pendentes traz os dos dois avaliadores."""
    links = {nome: f'//a[@href="{AVALIAR_RECURSO.format(item.pk)}"]' for nome, item in duas_fichas_com_recurso.items()}
    tela = Tela(logado_projetos('gerente')).ir(AVALIAR_RECURSOS)

    assert not any(tela.loc(xpath).count() for xpath in links.values()), 'sem "Ver todos", a lista do gerente trouxe recurso contra nota alheia'
    tela.preencher('Ver todos os registros', 'checkbox', 'Sim').preencher('Situação', 'lista', 'Pendentes de avaliação').clicar_botao('Enviar')

    tela.esperar()
    for xpath in links.values():
        expect(tela.loc(xpath)).to_have_count(1)


def test_coordenador_nao_recorre_em_projeto_alheio(logado_projetos, projeto_avaliado):
    """As três portas do recurso, com o id do projeto do ``outro_coordenador``: 403. O controle é o próprio projeto (200)."""
    proprio = projeto_avaliado().avaliacao.projeto
    alheio = projeto_avaliado(coordenador='outro_coordenador').avaliacao.projeto
    tela = Tela(logado_projetos('coordenador_projeto'))
    rotas = (INTERPOR_RECURSO, ITENS_SELECIONADOS, ENVIAR_RECURSO)

    respostas = {
        (rota, dono): tela.buscar(rota.format(projeto.pk)).status for rota in rotas for dono, projeto in (('proprio', proprio), ('alheio', alheio))
    }

    assert respostas == {(rota, dono): 200 if dono == 'proprio' else 403 for rota, dono in respostas}


@pytest.mark.parametrize('janela', ['selecao em curso', 'prazo vencido'])
def test_fora_do_prazo_de_recurso_nao_ha_recurso(logado_projetos, projeto_avaliado, janela):
    """``pode_enviar_recurso``: antes do fim da seleção ou depois da data limite, as três portas dão 403 ao próprio coordenador."""
    from projetos.models import Edital

    projeto = projeto_avaliado(fase='selecao' if janela == 'selecao em curso' else 'resultado_parcial').avaliacao.projeto
    if janela == 'prazo vencido':
        Edital.objects.filter(pk=projeto.edital_id).update(data_recurso=datetime.datetime.now() - datetime.timedelta(days=1))
    tela = Tela(logado_projetos('coordenador_projeto'))
    rotas = (INTERPOR_RECURSO, ITENS_SELECIONADOS, ENVIAR_RECURSO)

    assert {rota: tela.buscar(rota.format(projeto.pk)).status for rota in rotas} == dict.fromkeys(rotas, 403)


def test_itens_do_recurso_so_do_proprio_projeto(logado_projetos, projeto_avaliado):
    proprio = projeto_avaliado().avaliacao.projeto
    alheio = com_recurso_na_nota(projeto_avaliado(coordenador='outro_coordenador'), texto='Recurso sigiloso do outro coordenador')
    rota = ITENS_SELECIONADOS.format(proprio.pk)
    resposta = Tela(logado_projetos('coordenador_projeto')).buscar(f'{rota}?registros={alheio.pk}')

    assert 'Recurso sigiloso do outro coordenador' not in resposta.text(), 'o recurso de projeto alheio vazou pela querystring'
    assert resposta.status == 403, f'o item de projeto alheio foi aceito na querystring ({resposta.status})'
    # id não numérico: 403, não 500 (#17553)
    assert Tela(logado_projetos('coordenador_projeto')).buscar(f'{rota}?registros=abc').status == 403


# ------------------------------------------------------------------ contra o edital


def test_coordenador_envia_recurso_contra_o_edital(logado_projetos, projeto_avaliado):
    """ "Interpor Recurso" → "Do Edital": a justificativa vira um recurso do projeto, aguardando avaliação."""
    from projetos.models import RecursoProjeto

    projeto = projeto_avaliado().avaliacao.projeto
    tela = interpor_recurso_pelo_menu(Tela(logado_projetos('coordenador_projeto')), projeto, ENVIAR_RECURSO)

    tela.ver_titulo('Enviar Recurso').preencher('Justificativa do Recurso', 'textarea', 'O resultado não observou o item 5 do edital.')
    tela.clicar_botao('Salvar')

    tela.esperar().sucesso(ENCAMINHADO)
    recurso = RecursoProjeto.objects.filter(projeto=projeto).first()
    assert recurso is not None, 'a UI disse que encaminhou, mas o recurso não persistiu'
    assert (recurso.justificativa, recurso.data_avaliacao) == ('O resultado não observou o item 5 do edital.', None)


def test_coordenador_de_extensao_avalia_o_recurso_do_campus(logado_projetos, projeto_avaliado):
    """ "Solicitações de recurso" (edital de campus, projeto do CZN) → "Avaliar": o parecer e o aceite ficam no recurso."""
    recurso = recurso_do_edital(projeto_avaliado().avaliacao.projeto)
    tela = Tela(logado_projetos('coordenador_extensao')).ir(SOLICITACOES)

    tela.ver_titulo('Projetos com solicitações de recurso contra o edital').linha(recurso.justificativa)
    clicar_em(tela, AVALIAR_RECURSO_PROJETO.format(recurso.pk))
    tela.ver_titulo('Avaliar Recurso').preencher('Parecer do Avaliador', 'textarea', 'Recurso procedente.')
    tela.preencher('Aceitar Recurso', 'checkbox', 'Sim').clicar_botao('Salvar')

    tela.esperar().sucesso('Recurso avaliado com sucesso.')
    recurso.refresh_from_db()
    assert (recurso.aceito, recurso.parecer) == (True, 'Recurso procedente.'), 'a UI disse que avaliou, mas o parecer não persistiu'
    assert recurso.avaliador == vinculo('coordenador_extensao').relacionamento, 'o recurso não registrou quem avaliou'


def test_gerente_consulta_o_recurso(logado_projetos, projeto_avaliado):
    """O detalhe (popup, aberto pela URL) traz edital, projeto, justificativa e situação."""
    projeto = projeto_avaliado().avaliacao.projeto
    recurso = recurso_do_edital(projeto)
    tela = Tela(logado_projetos('gerente')).ir(SOLICITACOES)

    tela.linha(recurso.justificativa)
    expect(tela.loc(f'//a[@href="{RECURSO_PROJETO.format(recurso.pk)}"]').first).to_be_attached()
    tela.ir(RECURSO_PROJETO.format(recurso.pk)).quadro('Dados do Recurso')
    tela.linha('Recurso do Coordenador do Projeto').ver_texto(recurso.justificativa)
    tela.linha('Projeto').ver_texto(projeto.titulo)
    tela.linha('Situação').ver_texto('Aguardando avaliação')


def test_coordenador_de_extensao_nao_ve_nem_avalia_recurso_de_outro_campus(logado_projetos, projeto_avaliado):
    """O recurso de projeto da reitoria não entra na lista dele e, pela URL, dá 403 — o do CZN é o controle (200)."""
    do_campus = recurso_do_edital(projeto_avaliado().avaliacao.projeto)
    de_outro_campus = recurso_do_edital(projeto_avaliado(uo=outra_uo(), sufixo='outro campus').avaliacao.projeto)
    tela = Tela(logado_projetos('coordenador_extensao')).ir(SOLICITACOES)

    expect(celula(tela, do_campus.justificativa)).to_have_count(1)
    assert not celula(tela, de_outro_campus.justificativa).count(), 'a lista mostrou recurso de projeto de outro campus'
    respostas = {nome: tela.buscar(AVALIAR_RECURSO_PROJETO.format(r.pk)).status for nome, r in (('campus', do_campus), ('outro', de_outro_campus))}
    assert respostas == {'campus': 200, 'outro': 403}


def test_coordenador_de_extensao_abre_o_recurso_que_a_lista_oferece(logado_projetos, projeto_avaliado):
    recurso = recurso_do_edital(projeto_avaliado().avaliacao.projeto)
    tela = Tela(logado_projetos('coordenador_extensao')).ir(SOLICITACOES)

    expect(tela.loc(f'//a[@href="{RECURSO_PROJETO.format(recurso.pk)}"]').first).to_be_attached()
    assert tela.buscar(RECURSO_PROJETO.format(recurso.pk)).status == 200, 'o detalhe que a lista oferece ao Coordenador de Extensão deu 403'


@pytest.mark.parametrize(
    ('papel', 'esperado'),
    [
        ('gerente', {SOLICITACOES: 200, AVALIAR_RECURSOS: 200, MEUS_RECURSOS: 200}),
        ('coordenador_extensao', {SOLICITACOES: 200, AVALIAR_RECURSOS: 200, MEUS_RECURSOS: 200}),
        ('coordenador_projeto', {SOLICITACOES: 403, AVALIAR_RECURSOS: 200, MEUS_RECURSOS: 200}),
        ('aluno', {SOLICITACOES: 403, AVALIAR_RECURSOS: 403, MEUS_RECURSOS: 200}),
    ],
)
def test_telas_de_recurso_por_papel(logado_projetos, projetos_seed, papel, esperado):
    """Solicitações: ``pode_avaliar_cancelamento_projeto``; avaliar recursos: ``pode_se_tornar_avaliador``; meus recursos: ``pode_interagir_com_projeto``."""
    tela = Tela(logado_projetos(papel))

    assert {rota: tela.buscar(rota).status for rota in esperado} == esperado
