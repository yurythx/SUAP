"""Fluxo: prestação de contas do projeto em execução (aba "Prestação de contas", feature 006).

O coordenador sobe os extratos mensais do cartão pesquisador, o comprovante de GRU (devolução das
sobras) e, para o gasto APROVADO em material permanente (449052), o termo de cessão/doação do bem.
O "Relatório de Prestação de Contas" lista os gastos registrados (parcial por mês ou final) e sai
em PDF. As views de extrato e de termo de cessão não chamam ``tem_permissao``: quem barra o
estranho é ``Projeto.pode_editar_inscricao_execucao``, que pergunta se o usuário da thread gerencia
o projeto — as sondas daqui são o controle positivo disso.
"""

from __future__ import annotations

import datetime
from uuid import uuid4

import pytest
from playwright.sync_api import expect

from djtools.e2e_ui import Tela
from projetos.tests.e2e.conftest import clicar_em, natureza_material_permanente, vinculo

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

PROJETO = '/projetos/projeto/{}/'
ABA = 'Prestação de contas'
ADICIONAR_EXTRATO = '/projetos/adicionar_extrato_mensal/{}/'
EDITAR_EXTRATO = '/projetos/editar_extrato_mensal/{}/'
EXCLUIR_EXTRATO = '/projetos/excluir_extrato_mensal/{}/'
ADICIONAR_GRU = '/projetos/adicionar_comprovante_gru/{}/'
EXCLUIR_GRU = '/projetos/excluir_comprovante_gru/{}/'
ADICIONAR_TERMO_CESSAO = '/projetos/adicionar_termo_cessao/{}/'
EDITAR_TERMO_CESSAO = '/projetos/editar_termo_cessao/{}/'
EXCLUIR_TERMO_CESSAO = '/projetos/excluir_termo_cessao/{}/'
PRESTACAO = '/projetos/prestacao_contas/{}/'

GRU = 'upload/projetos/comprovantes_gru/gru-e2e.pdf'
NOTA_FISCAL = 'upload/projetos/registrogasto/comprovantes/nota-fiscal-e2e.pdf'


def test_extrato_mensal_ciclo_completo(logado_projetos, projeto_em_execucao):
    from projetos.models import ExtratoMensalProjeto

    projeto = projeto_em_execucao().projeto
    ano = str(datetime.date.today().year)
    tela = Tela(logado_projetos('coordenador_projeto')).ir(PROJETO.format(projeto.pk))

    tela.clicar_aba(ABA)
    clicar_em(tela, ADICIONAR_EXTRATO.format(projeto.pk))
    tela.ver_titulo('Adicionar Extrato Mensal').preencher_formulario(
        [('Ano', 'autocomplete', ano), ('Mês', 'lista', 'Janeiro'), ('Arquivo', 'arquivo', 'extrato.pdf')]
    )
    tela.clicar_botao('Salvar')
    tela.esperar().sucesso('Extrato cadastrado com sucesso.')
    extrato = ExtratoMensalProjeto.objects.filter(projeto=projeto).first()
    assert extrato is not None, 'a UI disse que cadastrou, mas o extrato não persistiu'
    assert (str(extrato.ano), extrato.mes, bool(extrato.arquivo)) == (ano, 1, True)

    tela.clicar_aba(ABA)
    clicar_em(tela, EDITAR_EXTRATO.format(extrato.pk))
    tela.ver_titulo('Editar Extrato Mensal').preencher('Mês', 'lista', 'Fevereiro').clicar_botao('Salvar')
    tela.esperar().sucesso('Extrato editado com sucesso.')
    extrato.refresh_from_db()
    assert extrato.mes == 2, 'a UI disse que editou, mas não persistiu'

    tela.clicar_aba(ABA)
    clicar_em(tela, EXCLUIR_EXTRATO.format(extrato.pk))  # `.icon-delete`
    tela.esperar().sucesso('Extrato removido com sucesso.')
    assert not ExtratoMensalProjeto.objects.filter(pk=extrato.pk).exists(), 'a UI disse que removeu, mas o extrato continua'


def test_comprovante_de_gru_adicionar_e_remover(logado_projetos, projeto_em_execucao):
    projeto = projeto_em_execucao().projeto
    descricao = f'Devolução das sobras {uuid4().hex[:8]}'
    tela = Tela(logado_projetos('coordenador_projeto')).ir(PROJETO.format(projeto.pk))

    tela.clicar_aba(ABA)
    clicar_em(tela, ADICIONAR_GRU.format(projeto.pk))
    tela.ver_titulo('Adicionar Comprovante de Pagamento de GRU').preencher_formulario(
        [('Descrição', 'texto', descricao), ('Comprovante de Pagamento da GRU', 'arquivo', 'gru.pdf')]
    )
    tela.clicar_botao('Salvar')
    tela.esperar().sucesso('Comprovante cadastrado com sucesso.')
    projeto.refresh_from_db()
    assert (projeto.descricao_comprovante_gru, bool(projeto.arquivo_comprovante_gru)) == (descricao, True), 'o comprovante não persistiu'

    tela.clicar_aba(ABA)
    clicar_em(tela, EXCLUIR_GRU.format(projeto.pk))  # `.icon-delete`
    tela.esperar().sucesso('Comprovante removido com sucesso.')
    projeto.refresh_from_db()
    assert not projeto.arquivo_comprovante_gru, 'a UI disse que removeu, mas o comprovante continua'


def test_termo_de_cessao_do_bem_permanente_ciclo_completo(logado_projetos, projeto_em_execucao):
    """O link só aparece com gasto APROVADO em 449052; o termo é gravado no próprio ``RegistroGasto``."""
    from projetos.tests.factories import DesembolsoFactory, ItemMemoriaCalculoFactory, RegistroGastoFactory

    projeto = projeto_em_execucao().projeto
    desembolso = DesembolsoFactory(item=ItemMemoriaCalculoFactory(projeto=projeto, despesa=natureza_material_permanente()))
    gasto = RegistroGastoFactory(desembolso=desembolso, descricao=f'Notebook {uuid4().hex[:8]}', aprovado=True, dt_avaliacao=datetime.date.today())
    tela = Tela(logado_projetos('coordenador_projeto')).ir(PROJETO.format(projeto.pk))

    tela.clicar_aba(ABA)
    clicar_em(tela, ADICIONAR_TERMO_CESSAO.format(projeto.pk))
    tela.ver_titulo('Adicionar Termo de Cessão/Doação').preencher_formulario(
        [('Registro de Gasto', 'lista', str(gasto)), ('Arquivo', 'arquivo', 'termo.pdf'), ('Observação', 'textarea', 'Doado ao laboratório.')]
    )
    tela.clicar_botao('Enviar')
    tela.esperar().sucesso('Termo cadastrado com sucesso.')
    gasto.refresh_from_db()
    assert (bool(gasto.arquivo_termo_cessao), gasto.obs_cessao) == (True, 'Doado ao laboratório.'), 'o termo não persistiu'

    tela.clicar_aba(ABA)
    clicar_em(tela, EDITAR_TERMO_CESSAO.format(gasto.pk))
    tela.ver_titulo('Editar Termo de Cessão/Doação').preencher('Observação', 'textarea', 'Doado à biblioteca.').clicar_botao('Salvar')
    tela.esperar().sucesso('Termo de Cessão editado com sucesso.')
    gasto.refresh_from_db()
    assert gasto.obs_cessao == 'Doado à biblioteca.', 'a UI disse que editou, mas não persistiu'

    tela.clicar_aba(ABA)
    clicar_em(tela, EXCLUIR_TERMO_CESSAO.format(gasto.pk))  # `.icon-delete`
    tela.esperar().sucesso('Termo de cessão/doação removido com sucesso.')
    gasto.refresh_from_db()
    assert (bool(gasto.arquivo_termo_cessao), gasto.obs_cessao) == (False, None), 'a UI disse que removeu, mas o termo continua'


def test_relatorio_de_prestacao_de_contas(logado_projetos, projeto_em_execucao):
    """ "Visualizar > Relatório de Prestação de Contas": o tipo "Final" lista todos os gastos, e o mesmo filtro sai em PDF."""
    from projetos.tests.factories import RegistroGastoFactory

    execucao = projeto_em_execucao()
    gasto = RegistroGastoFactory(desembolso=execucao.desembolso, descricao=f'Bolsa de estudante {uuid4().hex[:8]}')
    rota = PRESTACAO.format(execucao.projeto.pk)
    tela = Tela(logado_projetos('coordenador_projeto')).ir(PROJETO.format(execucao.projeto.pk))
    expect(tela.loc(f'//a[@href="{rota}"]')).to_have_count(1)  # no submenu "Visualizar", escondido até o clique

    tela.ir(rota).ver_titulo(f'Prestação de Contas do Projeto "{execucao.projeto.titulo}"')
    tela.preencher('Tipo do Relatório', 'lista', 'Final')  # `onchange` submete o formulário
    tela.esperar().linha(gasto.descricao).ver_texto('100,00')

    pdf = tela.buscar(f'{rota}?tipo_relatorio=2&pdf=1')
    assert (pdf.status, pdf.headers.get('content-type')) == (200, 'application/pdf'), 'o relatório não saiu em PDF'


def test_relatorio_parcial_sem_mes_pede_o_mes(logado_projetos, projeto_em_execucao):
    """#17576: o parcial por URL sem ``mes_relatorio`` (link antigo) é erro de formulário, não 500."""
    from projetos.tests.factories import RegistroGastoFactory

    execucao = projeto_em_execucao()
    gasto = RegistroGastoFactory(desembolso=execucao.desembolso)
    rota = f'{PRESTACAO.format(execucao.projeto.pk)}?tipo_relatorio=1&ano_relatorio={gasto.ano_id}'
    tela = Tela(logado_projetos('coordenador_projeto'))

    assert tela.buscar(rota).status == 200, 'o relatório parcial sem mês não respondeu 200'
    tela.ir(rota).erro('Selecione o mês.')


@pytest.mark.parametrize(
    ('papel', 'status'),
    [('coordenador_projeto', 200), ('gerente', 200), ('coordenador_extensao', 200), ('outro_coordenador', 403), ('avaliador', 403)],
)
def test_relatorio_de_prestacao_de_contas_por_papel(logado_projetos, projeto_em_execucao, papel, status):
    """O Coordenador de Extensão aqui é também o monitor. De OUTRO campus ele também lê (grupo sem campus na view) — decisão em aberto, fora do teste."""
    from projetos.tests.factories import RegistroGastoFactory

    execucao = projeto_em_execucao()
    RegistroGastoFactory(desembolso=execucao.desembolso)
    assert Tela(logado_projetos(papel)).buscar(PRESTACAO.format(execucao.projeto.pk)).status == status


def test_estranho_nao_mexe_na_prestacao_de_contas(logado_projetos, projeto_em_execucao):
    """Coordenador de OUTRO projeto: todas as rotas da aba dão 403, e nada é apagado pelas remoções por GET."""
    from projetos.models import ExtratoMensalProjeto, Projeto
    from projetos.tests.factories import ExtratoMensalProjetoFactory, RegistroGastoFactory

    execucao = projeto_em_execucao()
    projeto = execucao.projeto
    Projeto.objects.filter(pk=projeto.pk).update(arquivo_comprovante_gru=GRU)
    extrato = ExtratoMensalProjetoFactory(projeto=projeto)
    termo = RegistroGastoFactory(desembolso=execucao.desembolso, arquivo_termo_cessao='upload/projetos/termo_cessao/termo-e2e.pdf')
    rotas = [
        ADICIONAR_EXTRATO.format(projeto.pk),
        EDITAR_EXTRATO.format(extrato.pk),
        EXCLUIR_EXTRATO.format(extrato.pk),
        ADICIONAR_GRU.format(projeto.pk),
        EXCLUIR_GRU.format(projeto.pk),
        ADICIONAR_TERMO_CESSAO.format(projeto.pk),
        EDITAR_TERMO_CESSAO.format(termo.pk),
        EXCLUIR_TERMO_CESSAO.format(termo.pk),
    ]
    tela = Tela(logado_projetos('outro_coordenador'))

    respostas = {rota: tela.buscar(rota).status for rota in rotas}
    assert respostas == dict.fromkeys(rotas, 403), f'rotas que não barraram o estranho: { {r: s for r, s in respostas.items() if s != 403} }'
    termo.refresh_from_db()
    assert ExtratoMensalProjeto.objects.filter(pk=extrato.pk).exists(), 'o extrato foi apagado por uma rota que respondeu 403'
    assert (Projeto.objects.get(pk=projeto.pk).arquivo_comprovante_gru.name, bool(termo.arquivo_termo_cessao)) == (GRU, True), (
        'o comprovante de GRU ou o termo de cessão foi apagado por uma rota que respondeu 403'
    )


def test_relatorio_oferecido_ao_auxiliar_abre(logado_projetos, projeto_em_execucao):
    from projetos.tests.factories import ParticipacaoFactory, RegistroGastoFactory

    execucao = projeto_em_execucao(auxiliar=vinculo('outro_coordenador'))
    ParticipacaoFactory(projeto=execucao.projeto, vinculo_pessoa=vinculo('outro_coordenador'))
    RegistroGastoFactory(desembolso=execucao.desembolso)
    rota = PRESTACAO.format(execucao.projeto.pk)
    tela = Tela(logado_projetos('outro_coordenador')).ir(PROJETO.format(execucao.projeto.pk))

    tela.clicar_aba(ABA)  # o auxiliar gerencia a aba: "Adicionar Extrato Mensal" é dele
    expect(tela.loc(f'//a[@href="{ADICIONAR_EXTRATO.format(execucao.projeto.pk)}"]')).to_have_count(1)
    oferecido = tela.loc(f'//a[@href="{rota}"]').count() > 0
    status = tela.buscar(rota).status
    assert not oferecido or status == 200, f'a tela oferece o relatório de prestação de contas ao auxiliar, e a rota responde {status}'


def test_cadastrar_comprovante_do_gasto_aprovado_abre(logado_projetos, projeto_em_execucao):
    from projetos.tests.factories import RegistroGastoFactory

    execucao = projeto_em_execucao()
    gasto = RegistroGastoFactory(desembolso=execucao.desembolso, aprovado=True, dt_avaliacao=datetime.date.today())
    tela = Tela(logado_projetos('coordenador_projeto')).ir(PRESTACAO.format(execucao.projeto.pk))

    tela.preencher('Tipo do Relatório', 'lista', 'Final').esperar().linha(gasto.descricao).ver_texto('Cadastrar')
    rota = f'/projetos/registro_gasto/{execucao.desembolso.pk}/?editar_registro_id={gasto.pk}'
    oferecido = tela.loc(f'//a[@href="{rota}"]').count() > 0
    status = tela.buscar(rota).status
    assert not oferecido or status == 200, f'o relatório oferece "Cadastrar" o comprovante do gasto aprovado, e a rota responde {status}'


def _cadastrar_que_nao_abre(tela: Tela) -> dict[str, int]:
    """Os "Cadastrar" de comprovante/cotação do relatório (``registro_gasto``) que não respondem 200."""
    rotas = [link.get_attribute('href') for link in tela.loc('//a[contains(@href, "editar_registro_id=")]').all()]
    return {rota: status for rota in rotas if (status := tela.buscar(rota).status) != 200}


def test_cadastrar_cotacao_do_gasto_aprovado_com_nota_fiscal_nao_e_oferecido(logado_projetos, projeto_em_execucao):
    """#17567: gasto aprovado COM nota fiscal não é editável nem "só comprovante" — ``registro_gasto`` redireciona (302)."""
    from projetos.tests.factories import RegistroGastoFactory

    execucao = projeto_em_execucao()
    gasto = RegistroGastoFactory(desembolso=execucao.desembolso, aprovado=True, dt_avaliacao=datetime.date.today(), arquivo=NOTA_FISCAL)
    tela = Tela(logado_projetos('coordenador_projeto')).ir(PRESTACAO.format(execucao.projeto.pk))

    tela.preencher('Tipo do Relatório', 'lista', 'Final').esperar().linha(gasto.descricao).ver_texto('Visualizar Arquivo')
    recusados = _cadastrar_que_nao_abre(tela)
    assert not recusados, f'o relatório oferece "Cadastrar" que registro_gasto recusa: {recusados}'


def test_cadastrar_arquivo_nao_e_oferecido_no_projeto_finalizado(logado_projetos, projeto_em_execucao):
    """#17567: fora da execução ``registro_gasto`` dá 403 ao coordenador, mas o relatório continua aberto a ele."""
    from projetos.models import Projeto
    from projetos.tests.factories import RegistroGastoFactory

    execucao = projeto_em_execucao()
    gasto = RegistroGastoFactory(desembolso=execucao.desembolso)
    Projeto.objects.filter(pk=execucao.projeto.pk).update(data_finalizacao_conclusao=datetime.datetime.now())
    tela = Tela(logado_projetos('coordenador_projeto')).ir(PRESTACAO.format(execucao.projeto.pk))

    tela.preencher('Tipo do Relatório', 'lista', 'Final').esperar().linha(gasto.descricao).ver_texto('100,00')
    recusados = _cadastrar_que_nao_abre(tela)
    assert not recusados, f'o relatório oferece "Cadastrar" que registro_gasto recusa: {recusados}'
