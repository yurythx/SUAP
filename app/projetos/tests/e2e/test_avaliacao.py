"""Fluxo: a avaliação do projeto pré-selecionado (feature 005) e o que sai dela — ficha, alteração de nota, exclusão e declaração.

O avaliador indicado (feature 004) entra por "Avaliar" (``/avaliacao/`` → campus → projeto) e dá
nota por critério e parecer; a ficha (``visualizar_ficha_avaliacao``) é o que o coordenador vê
depois da seleção e o Gerente Sistêmico a qualquer tempo. Com recurso aceito, o gerente altera a
nota de um critério e a alteração fica registrada (``ver_alteracao_ficha_avaliacao``); ele também
pode excluir uma avaliação. Por fim, o avaliador emite a declaração de avaliador do edital. A fila
de pré-seleção (``projetos_nao_avaliados``) mora aqui por ser a tela "projetos ainda não avaliados".

A regressão cara é a nota: quem não foi indicado avaliar, a ficha vazar para quem não pode vê-la,
ou a alteração/exclusão não recalcular a avaliação. Toda gravação de nota passa por
``Avaliacao.save``/``delete``, que reclassifica o edital: sempre em edital descartável.
"""

from __future__ import annotations

import datetime
import re
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import Locator, expect

from djtools.e2e_ui import Tela
from projetos.tests.e2e.conftest import clicar_em, outra_uo, vinculo

if TYPE_CHECKING:
    from projetos.models import ItemAvaliacao, Projeto

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

AVALIACAO = '/projetos/avaliacao/'
AVALIAR = '/projetos/avaliar/{}/'
PROJETO = '/projetos/projeto/{}/'
VISUALIZAR_FICHA = '/projetos/visualizar_ficha_avaliacao/{}/'
ALTERAR_FICHA = '/projetos/alterar_ficha_avaliacao/{}/'
VER_ALTERACAO = '/projetos/ver_alteracao_ficha_avaliacao/{}/'
EXCLUIR_AVALIACAO = '/projetos/excluir_avaliacao/{}/'
PROJETOS_NAO_AVALIADOS = '/projetos/projetos_nao_avaliados/{}/'
DECLARACAO = '/projetos/emitir_declaracao_avaliador/'
DECLARACAO_PDF = '/projetos/emitir_declaracao_avaliador_pdf/{}/'
CANCELAR_PRE_AVALIACAO = '/projetos/cancelar_pre_avaliacao_projeto/{}/'

CRITERIO = 'Relevância social da proposta'


def celula(tela: Tela, texto: str) -> Locator:
    """A célula com exatamente ``texto`` — a mesma sonda serve à presença e à ausência."""
    return tela.loc(f'//td[normalize-space(.)="{texto}"]')


@pytest.fixture
def indicado(projeto_enviado_em) -> Projeto:
    """Projeto pré-selecionado de edital em seleção, com um critério e o ``avaliador`` indicado (e com o aceite dado), sem avaliação."""
    from projetos.tests.factories import AvaliadorIndicadoFactory, CriterioAvaliacaoFactory

    projeto = projeto_enviado_em('selecao', pre_aprovado=True, data_pre_avaliacao=datetime.date.today())
    CriterioAvaliacaoFactory(edital=projeto.edital, descricao=CRITERIO)
    AvaliadorIndicadoFactory(projeto=projeto, vinculo=vinculo('avaliador'), aceito_em=datetime.datetime.now())
    return projeto


def com_recurso_aceito(item: ItemAvaliacao, **alteracao: object) -> ItemAvaliacao:
    """Recurso do edital aceito no projeto do item — é o que libera "Alterar Nota" na ficha; ``alteracao`` vai para o item."""
    from projetos.models import ItemAvaliacao
    from projetos.tests.factories import RecursoProjetoFactory

    RecursoProjetoFactory(projeto=item.avaliacao.projeto, aceito=True, data_avaliacao=datetime.datetime.now(), parecer='Recurso procedente')
    ItemAvaliacao.objects.filter(pk=item.pk).update(**alteracao)
    item.refresh_from_db()
    return item


def test_avaliador_indicado_avalia_o_projeto(logado_projetos, indicado):
    """ "Avaliar" → edital → campus → "Avaliar": a nota do critério e o parecer viram a avaliação dele."""
    from projetos.models import Avaliacao, ItemAvaliacao

    projeto = indicado
    tela = Tela(logado_projetos('avaliador')).ir(AVALIACAO)

    tela.ver_titulo('Editais em Avaliação').linha(projeto.edital.titulo).clicar_link(projeto.uo.sigla)
    tela.esperar().ver_titulo('Seleção de Projetos').linha(projeto.titulo).clicar_botao('Avaliar')
    expect(tela.pagina).to_have_url(re.compile(re.escape(AVALIAR.format(projeto.pk))))
    tela.esperar().ver_titulo(f'Avaliação do Projeto - {projeto.titulo}').preencher_formulario(
        [(CRITERIO, 'lista', '8.0'), ('Parecer', 'textarea', 'Parecer do avaliador A')]
    )
    tela.clicar_botao('Enviar')

    tela.esperar().sucesso('Projeto avaliado com sucesso.')
    avaliacao = Avaliacao.objects.filter(projeto=projeto, vinculo=vinculo('avaliador')).first()
    assert avaliacao is not None, 'a UI disse que avaliou, mas a avaliação não persistiu'
    assert (avaliacao.parecer, avaliacao.pontuacao) == ('Parecer do avaliador A', Decimal(8)), 'parecer/nota da avaliação não são os informados'
    assert ItemAvaliacao.objects.filter(avaliacao=avaliacao, criterio_avaliacao__descricao=CRITERIO, pontuacao=Decimal(8)).exists(), (
        'a nota do critério não persistiu'
    )


def test_so_o_indicado_avalia_e_so_na_selecao(logado_projetos, indicado, projeto_enviado_em):
    """Projeto em que ele não foi indicado e edital fora da seleção: 403. O controle positivo é o projeto indicado (200)."""
    from projetos.tests.factories import AvaliadorIndicadoFactory

    sem_indicacao = projeto_enviado_em('selecao', edital=indicado.edital, sufixo='sem indicacao', pre_aprovado=True)
    fora_da_selecao = projeto_enviado_em('resultado_parcial', pre_aprovado=True)
    AvaliadorIndicadoFactory(projeto=fora_da_selecao, vinculo=vinculo('avaliador'))
    tela = Tela(logado_projetos('avaliador'))
    alvos = {'indicado': indicado, 'sem indicacao': sem_indicacao, 'fora da selecao': fora_da_selecao}

    respostas = {nome: tela.buscar(AVALIAR.format(projeto.pk)).status for nome, projeto in alvos.items()}

    assert respostas == {'indicado': 200, 'sem indicacao': 403, 'fora da selecao': 403}


def test_avaliador_que_rejeitou_a_indicacao_nao_avalia(logado_projetos, indicado):
    from projetos.models import AvaliadorIndicado

    AvaliadorIndicado.objects.filter(projeto=indicado, vinculo=vinculo('avaliador')).update(
        aceito_em=None, rejeitado=True, rejeitado_em=datetime.datetime.now()
    )
    resposta = Tela(logado_projetos('avaliador')).buscar(AVALIAR.format(indicado.pk))
    assert resposta.status == 403, f'o avaliador que rejeitou a indicação abriu a avaliação ({resposta.status})'


def test_indicacao_rejeitada_nao_deixa_edital_pendente(logado_projetos, indicado):
    """ "Editais em Avaliação": edital e campus saem do vermelho quando a única indicação foi rejeitada, mas o campus continua navegável."""
    from projetos.models import AvaliadorIndicado

    projeto = indicado
    edital = f'//td/span[contains(@class, "status-{{}}") and normalize-space(.)="{projeto.edital.titulo}"]'
    campus = f'//li/span[contains(@class, "status-{{}}")]/a[contains(normalize-space(.), "{projeto.uo.sigla}")]'
    tela = Tela(logado_projetos('avaliador')).ir(AVALIACAO).ver_titulo('Editais em Avaliação')
    expect(tela.loc(edital.format('error'))).to_have_count(1)  # controle: indicação aceita e sem avaliação é pendente
    expect(tela.loc(campus.format('error'))).to_have_count(1)

    AvaliadorIndicado.objects.filter(projeto=projeto, vinculo=vinculo('avaliador')).update(
        aceito_em=None, rejeitado=True, rejeitado_em=datetime.datetime.now()
    )
    tela.ir(AVALIACAO)

    expect(tela.loc(edital.format('success'))).to_have_count(1)
    expect(tela.loc(campus.format('success'))).to_have_count(1)


def test_pre_selecao_cancelada_nao_deixa_edital_pendente(logado_projetos, indicado):
    """#17574: o Gerente cancela a pré-avaliação; a indicação fica, mas edital e campus saem do vermelho em "Editais em Avaliação"."""
    projeto = indicado
    edital = f'//td/span[contains(@class, "status-{{}}") and normalize-space(.)="{projeto.edital.titulo}"]'
    campus = f'//li/span[contains(@class, "status-{{}}")]/a[contains(normalize-space(.), "{projeto.uo.sigla}")]'
    tela = Tela(logado_projetos('avaliador')).ir(AVALIACAO).ver_titulo('Editais em Avaliação')
    expect(tela.loc(edital.format('error'))).to_have_count(1)  # controle: indicação aceita e sem avaliação é pendente
    expect(tela.loc(campus.format('error'))).to_have_count(1)

    Tela(logado_projetos('gerente')).buscar(CANCELAR_PRE_AVALIACAO.format(projeto.pk))
    projeto.refresh_from_db()
    assert not projeto.pre_aprovado, 'premissa: o Gerente cancelou a pré-avaliação'
    tela.ir(AVALIACAO)

    expect(tela.loc(edital.format('success'))).to_have_count(1)
    expect(tela.loc(campus.format('success'))).to_have_count(1)


def test_gerente_altera_a_nota_depois_do_recurso_aceito(logado_projetos, projeto_avaliado):
    """Dados da seleção → "Ver Ficha" → "Alterar Nota": a nota original fica guardada e a avaliação é recalculada."""
    from projetos.models import Avaliacao

    item = com_recurso_aceito(projeto_avaliado(nota=5))
    projeto = item.avaliacao.projeto
    tela = Tela(logado_projetos('gerente')).ir(PROJETO.format(projeto.pk))

    tela.clicar_aba('Dados da seleção')
    clicar_em(tela, VISUALIZAR_FICHA.format(item.avaliacao.pk))
    tela.ver_titulo('Detalhamento da Avaliação do Projeto').linha(item.criterio_avaliacao.descricao).ver_texto('5,00')
    expect(tela.loc(f'//a[@href="{ALTERAR_FICHA.format(item.pk)}"]')).to_be_visible()  # popup: o formulário vai pela página inteira
    tela.ir(ALTERAR_FICHA.format(item.pk)).ver_titulo('Alterar Pontuação').preencher('Nova Pontuação', 'lista', '4.0')
    tela.clicar_botao('Salvar')

    tela.esperar().sucesso('Nota atualizada com sucesso.')
    item.refresh_from_db()
    assert (item.pontuacao_original, item.pontuacao) == (Decimal(5), Decimal(4)), 'a UI disse que alterou, mas a nota do critério não mudou'
    assert item.vinculo_responsavel_alteracao == vinculo('gerente'), 'a alteração não registrou quem a fez'
    assert Avaliacao.objects.get(pk=item.avaliacao.pk).pontuacao == Decimal(4), 'a nota do critério mudou, mas a avaliação não foi recalculada'


def test_coordenador_consulta_a_ficha_e_a_alteracao_da_nota(logado_projetos, projeto_avaliado):
    """Encerrada a seleção, o coordenador vê a ficha e, na nota alterada, quem a alterou e de quanto para quanto."""
    item = com_recurso_aceito(
        projeto_avaliado(nota=4),
        pontuacao_original=Decimal(6),
        vinculo_responsavel_alteracao=vinculo('gerente'),
        data_alteracao=datetime.datetime.now(),
    )
    projeto = item.avaliacao.projeto
    tela = Tela(logado_projetos('coordenador_projeto')).ir(PROJETO.format(projeto.pk))

    tela.clicar_aba('Dados da seleção')
    clicar_em(tela, VISUALIZAR_FICHA.format(item.avaliacao.pk))
    tela.ver_titulo('Detalhamento da Avaliação do Projeto').ver_texto('Notas com (*) foram alteradas após aceitação de recurso.')
    assert not tela.loc(f'//a[@href="{ALTERAR_FICHA.format(item.pk)}"]').count(), 'o coordenador recebeu "Alterar Nota"'
    expect(tela.loc(f'//a[@href="{VER_ALTERACAO.format(item.pk)}"]')).to_be_visible()  # o mesmo seletor acha o "Ver Alteração"

    tela.ir(VER_ALTERACAO.format(item.pk)).quadro('Alteração de Pontuação')
    tela.linha('Pontuação Original').ver_texto('6,00')
    tela.linha('Pontuação Após Recurso').ver_texto('4,00')
    tela.linha('Pontuação Alterada Por').ver_texto('Gerente Extensão E2E')


@pytest.fixture
def fichas(projeto_avaliado) -> dict[str, ItemAvaliacao]:
    """Duas avaliações com nota alterada após a seleção: uma de projeto do CZN e uma de projeto da reitoria."""
    alterada = {'pontuacao_original': Decimal(6), 'vinculo_responsavel_alteracao': vinculo('gerente'), 'data_alteracao': datetime.datetime.now()}
    return {
        'czn': com_recurso_aceito(projeto_avaliado(), **alterada),
        'outro campus': com_recurso_aceito(projeto_avaliado(uo=outra_uo(), sufixo='outro campus'), **alterada),
    }


@pytest.mark.parametrize(
    ('papel', 'esperado'),
    [
        # Ficha: gerente sempre; coordenador do projeto e Coordenador de Extensão do campus só depois da seleção.
        # Alteração: Coordenador de Extensão do campus ou `tem_permissao` (coordenador ou gerente). Alterar: `pode_gerenciar_edital`.
        ('gerente', {'ficha': 200, 'alteracao': 200, 'alterar': 200, 'ficha outro campus': 200}),
        ('coordenador_projeto', {'ficha': 200, 'alteracao': 200, 'alterar': 403, 'ficha outro campus': 200}),
        ('coordenador_extensao', {'ficha': 200, 'alteracao': 200, 'alterar': 403, 'ficha outro campus': 403}),
        ('outro_coordenador', {'ficha': 403, 'alteracao': 403, 'alterar': 403, 'ficha outro campus': 403}),
        ('avaliador', {'ficha': 403, 'alteracao': 403, 'alterar': 403, 'ficha outro campus': 403}),
    ],
)
def test_quem_ve_e_quem_altera_a_ficha(logado_projetos, fichas, papel, esperado):
    """O projeto da reitoria também é do ``coordenador_projeto``: o Coordenador de Extensão do CZN não vê a ficha dele."""
    czn, outro = fichas['czn'], fichas['outro campus']
    rotas = {
        'ficha': VISUALIZAR_FICHA.format(czn.avaliacao.pk),
        'alteracao': VER_ALTERACAO.format(czn.pk),
        'alterar': ALTERAR_FICHA.format(czn.pk),
        'ficha outro campus': VISUALIZAR_FICHA.format(outro.avaliacao.pk),
    }
    tela = Tela(logado_projetos(papel))

    assert {nome: tela.buscar(rota).status for nome, rota in rotas.items()} == esperado


def test_gerente_exclui_a_avaliacao(logado_projetos, projeto_avaliado):
    """O ícone de excluir da aba "Dados da seleção" apaga a avaliação (e o projeto é repontuado sem ela)."""
    from projetos.models import Avaliacao

    item = projeto_avaliado()
    projeto = item.avaliacao.projeto
    tela = Tela(logado_projetos('gerente')).ir(PROJETO.format(projeto.pk))

    tela.clicar_aba('Dados da seleção')
    clicar_em(tela, EXCLUIR_AVALIACAO.format(item.avaliacao.pk))
    tela.sucesso('Avaliação removida com sucesso.')

    assert not Avaliacao.objects.filter(pk=item.avaliacao.pk).exists(), 'a UI disse que removeu, mas a avaliação ficou'


@pytest.mark.parametrize('papel', ['coordenador_extensao', 'coordenador_projeto'])
def test_so_o_gerente_exclui_avaliacao(logado_projetos, projeto_avaliado, papel):
    """``excluir_avaliacao`` apaga por GET: quem não é gerente recebe 403 e a avaliação fica."""
    from projetos.models import Avaliacao

    item = projeto_avaliado()
    resposta = Tela(logado_projetos(papel)).buscar(EXCLUIR_AVALIACAO.format(item.avaliacao.pk))

    assert resposta.status == 403
    assert Avaliacao.objects.filter(pk=item.avaliacao.pk).exists(), 'a avaliação foi apagada por quem recebeu 403'


def test_fila_da_pre_selecao_do_coordenador_de_extensao_e_do_proprio_campus(logado_projetos, projeto_enviado_em):
    """``projetos_nao_avaliados``: o Coordenador de Extensão só vê o projeto do campus dele; o Gerente vê os dois."""
    alheio = projeto_enviado_em('pre_selecao', uo=outra_uo(), sufixo='alheio')
    proprio = projeto_enviado_em('pre_selecao', edital=alheio.edital, sufixo='proprio')
    rota = PROJETOS_NAO_AVALIADOS.format(alheio.edital.pk)

    coordenador = Tela(logado_projetos('coordenador_extensao')).ir(rota).ver_titulo(f'Pré-Seleção de Projetos - {alheio.edital.titulo}')
    expect(celula(coordenador, proprio.titulo)).to_have_count(1)
    assert not celula(coordenador, alheio.titulo).count(), 'a fila do Coordenador de Extensão mostrou projeto de outro campus'

    gerente = Tela(logado_projetos('gerente')).ir(rota)
    expect(celula(gerente, alheio.titulo)).to_have_count(1)
    expect(celula(gerente, proprio.titulo)).to_have_count(1)


@pytest.mark.parametrize(('papel', 'na_janela'), [('coordenador_extensao', 200), ('coordenador_projeto', 403)])
def test_fila_da_pre_selecao_por_papel_e_janela(logado_projetos, projetos_seed, papel, na_janela):
    """Na janela, só quem pré-avalia abre a fila; o edital em seleção já saiu dela (403 até para o Coordenador de Extensão)."""
    tela = Tela(logado_projetos(papel))
    rotas = {fase: PROJETOS_NAO_AVALIADOS.format(projetos_seed.editais[fase].pk) for fase in ('pre_selecao', 'selecao')}

    assert {fase: tela.buscar(rota).status for fase, rota in rotas.items()} == {'pre_selecao': na_janela, 'selecao': 403}


def test_avaliador_emite_a_declaracao_do_edital_que_avaliou(logado_projetos, projeto_avaliado):
    """ "Declarações" lista o edital avaliado; a declaração (HTML sob teste, ver armadilha 20) traz o avaliador e o projeto."""
    item = projeto_avaliado()
    projeto = item.avaliacao.projeto
    tela = Tela(logado_projetos('avaliador')).ir(DECLARACAO)

    tela.ver_titulo('Declarações').linha(projeto.edital.titulo)
    clicar_em(tela, DECLARACAO_PDF.format(projeto.edital.pk))

    tela.ver_texto('DECLARAÇÃO DE AVALIADOR DE PROJETOS DE EXTENSÃO').ver_texto('Avaliador Extensão E2E').ver_texto(projeto.titulo)


def test_quem_nao_avaliou_nao_emite_declaracao_do_edital(logado_projetos, projeto_avaliado):
    item = projeto_avaliado()
    resposta = Tela(logado_projetos('coordenador_projeto')).buscar(DECLARACAO_PDF.format(item.avaliacao.projeto.edital.pk))

    assert 'Coordenador Projeto E2E</b>' not in resposta.text(), 'quem não avaliou recebeu a declaração de que avaliou projetos do edital'
    assert resposta.status == 403, f'quem não avaliou recebeu {resposta.status} na declaração de avaliador'


@pytest.mark.parametrize(('papel', 'status'), [('avaliador', 200), ('coordenador_projeto', 200), ('aluno', 403)])
def test_telas_do_avaliador_por_papel(logado_projetos, projetos_seed, papel, status):
    """``pode_se_tornar_avaliador`` (Servidor, Prestador, Externo): o servidor abre (vazias), o aluno não."""
    tela = Tela(logado_projetos(papel))
    rotas = (AVALIACAO, DECLARACAO)

    assert {rota: tela.buscar(rota).status for rota in rotas} == dict.fromkeys(rotas, status)
