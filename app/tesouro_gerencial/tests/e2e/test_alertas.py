"""Fluxo: os avisos que o módulo põe na página inicial do gestor (``index_inscricoes`` e
``index_atribuidos_a_meus_grupos`` em ``tesouro_gerencial/views.py``).

O gestor não tem tela de "pendências do tesouro": quem o lembra de importar, de classificar os
empenhos específicos do ano e de atualizar os relatórios são estes avisos, carregados por AJAX nos
blocos "Fique atento!" e "Pendências coletivas" da página inicial. Se pararem de aparecer, ninguém
nota — a importação atrasa e as variáveis do ano saem erradas. O que se afirma:

* o aviso de importação, nos dois textos: nunca realizada e atrasada desde uma data;
* o aviso de tipo sem documento no ano, e que ele **leva ao cadastro já com o tipo escolhido**
  (``?tipo=`` no link) — e some quando o documento é cadastrado;
* a pendência de atualizar os relatórios, que depende do ano corrente ter nota de empenho, nota de
  crédito e resto a pagar.
"""

import datetime

import pytest
from freezegun import freeze_time
from playwright.sync_api import expect

from djtools.e2e_fixtures import aquecer_urlconf
from djtools.e2e_ui import Tela
from tesouro_gerencial.tests.e2e.conftest import ANO_REFERENCIA

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

INICIO = '/'
# O bloco "Pendências coletivas" da página inicial é este fragmento, buscado por AJAX (`comum/static/comum/js/index.js`).
PENDENCIAS_COLETIVAS = '/comum/index/minhas_pendencias_coletivas/'

FIQUE_ATENTO = 'Fique atento!'
PENDENCIA = 'Atualizar os relatório do <strong>Tesouro Gerencial.</strong>'


def test_aviso_de_importacao_nunca_realizada_e_de_importacao_atrasada(logado_tesouro):
    """O histórico é só do comando ``importar_do_tesouro`` (nenhuma tela grava nele): zerá-lo é seguro."""
    from tesouro_gerencial.models import HistoricoImportacao
    from tesouro_gerencial.tests.factories import HistoricoImportacaoFactory

    HistoricoImportacao.objects.all().delete()
    tela = Tela(logado_tesouro('gestor')).ir(INICIO)
    tela.quadro(FIQUE_ATENTO).ver_texto('Tesouro Gerencial: A importação nunca foi realizada.')

    tres_dias_atras = datetime.datetime.now() - datetime.timedelta(days=3)
    historico = HistoricoImportacaoFactory()
    HistoricoImportacao.objects.filter(pk=historico.pk).update(data=tres_dias_atras)  # `data` é auto_now_add

    tela.ir(INICIO).quadro(FIQUE_ATENTO).ver_texto(f'A importação não foi realizada desde {tres_dias_atras:%d/%m/%Y}')


def test_tipo_sem_documento_no_ano_vira_aviso_que_abre_o_cadastro(logado_tesouro, tipo_sem_documento, empenho_do_ano):
    from tesouro_gerencial.models import DocumentoEmpenhoEspecifico

    descricao = tipo_sem_documento.descricao
    tela = Tela(logado_tesouro('gestor')).ir(INICIO)
    tela.quadro(FIQUE_ATENTO).clicar_link(f'Adicionar o Documento de Empenho de {descricao}')

    tela.esperar().ver_titulo('Adicionar Documento de Empenho Específico')
    expect(tela.campo('Tipo', 'autocomplete').first).to_contain_text(descricao)  # veio do `?tipo=` do aviso
    tela.preencher('Documento empenho', 'autocomplete', empenho_do_ano.numero).clicar_botao('Salvar')

    tela.sucesso('Cadastro realizado com sucesso.')
    assert DocumentoEmpenhoEspecifico.objects.filter(documento_empenho=empenho_do_ano, tipo=tipo_sem_documento).exists(), (
        'a UI disse que salvou, mas o documento específico não persistiu'
    )
    avisos = tela.ir(INICIO).quadro(FIQUE_ATENTO)
    expect(avisos.loc(f'//a[contains(normalize-space(.), "{descricao}")]')).to_have_count(0)


def test_pendencia_de_atualizar_relatorios_so_no_ano_sem_execucao_importada(logado_tesouro):
    """O ano é o do relógio (``datetime.now().year``), então o teste o move: 2001 não tem execução nenhuma;
    ``ANO_REFERENCIA`` tem empenho, nota de crédito e resto a pagar no seed.

    Congelado só em volta de cada requisição, com ``real_asyncio`` para o laço do Playwright continuar no
    tempo real. A sessão sobrevive porque o backend de sessão é de arquivo e expira pelo ``mtime``, que o
    congelamento não toca.
    """
    tela = Tela(logado_tesouro('gestor'))
    aquecer_urlconf()  # armadilha 4: o import preguiçoso de `suap/api.py` não pode cair dentro do congelamento
    with freeze_time('2001-06-15 12:00:00', tick=True, real_asyncio=True):
        sem_execucao = tela.buscar(PENDENCIAS_COLETIVAS)
    with freeze_time(f'{ANO_REFERENCIA}-06-15 12:00:00', tick=True, real_asyncio=True):
        com_execucao = tela.buscar(PENDENCIAS_COLETIVAS)

    assert sem_execucao.status == 200, f'pendências do gestor em 2001: HTTP {sem_execucao.status}'
    assert PENDENCIA in sem_execucao.text(), 'ano sem execução importada e o gestor não foi avisado de atualizar os relatórios'
    assert com_execucao.status == 200, f'pendências do gestor em {ANO_REFERENCIA}: HTTP {com_execucao.status}'
    assert PENDENCIA not in com_execucao.text(), f'{ANO_REFERENCIA} tem empenho, nota de crédito e resto a pagar, e a pendência continuou'
