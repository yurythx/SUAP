"""Fluxo: indicação de avaliadores dos projetos pré-selecionados (feature 004) — por projeto, em lote e a manutenção das indicações.

Pré-selecionado o projeto, o Coordenador de Extensão (edital de campus) ou o Gerente Sistêmico
escolhe, entre os membros da comissão do edital, quem o avalia. É a indicação que abre o
projeto na tela do avaliador (``projetos_pre_aprovados``) e que ele aceita ou rejeita. Depois,
na mesma tela de seleção, o gestor reenvia o convite rejeitado por prazo e remove indicações.

A regressão cara é a indicação não chegar ao avaliador (a avaliação nunca acontece e o edital
não fecha) ou ser mexida por quem não gere o edital. As remoções tiram o grupo "Avaliador de
Projetos de Extensão" de quem fica sem indicação; por isso a indicação removida é sempre do
``segundo_avaliador``, que não loga, e o grupo volta no teardown (``grupos_de``).
"""

from __future__ import annotations

import datetime
import re
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from djtools.e2e_ui import Tela
from projetos.tests.e2e.conftest import PAPEIS, clicar_em, comissao, janela, outra_uo, vinculo

if TYPE_CHECKING:
    from collections.abc import Callable

    from comum.models import Vinculo
    from projetos.models import AvaliadorIndicado, Edital, Projeto

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

SELECIONAR_AVALIADORES = '/projetos/selecionar_avaliadores/{}/'
SELECIONAR_AVALIADORES_DO_PROJETO = '/projetos/selecionar_avaliadores_do_projeto/{}/'
SALVAR_AVALIADORES_DO_PROJETO = '/projetos/salvar_avaliadores_do_projeto/{}/'
REMOVER_INDICACAO = '/projetos/remover_indicacao_avaliador/{}/'
REENVIAR_CONVITE = '/projetos/reenviar_convite_avaliador/{}/'
REMOVER_REJEITADAS = '/projetos/remover_indicacoes_rejeitadas/{}/'
INDICAR_EM_LOTE = '/projetos/indicar_avaliador_em_lote/'
SALVAR_EM_LOTE = '/projetos/salvar_indicacoes_em_lote/{}/'

GRUPO_AVALIADOR = 'Avaliador de Projetos de Extensão'


@pytest.fixture
def pre_selecionado(projeto_enviado_em) -> Projeto:
    """Projeto pré-selecionado num edital de campus em seleção, com ``avaliador`` e ``segundo_avaliador`` na comissão."""
    projeto = projeto_enviado_em('selecao', pre_aprovado=True, data_pre_avaliacao=datetime.date.today())
    comissao(projeto.edital, 'avaliador', 'segundo_avaliador')
    return projeto


def indicar(projeto: Projeto, papel: str, **campos: object) -> AvaliadorIndicado:
    """Indicação já gravada (o que a tela de seleção lista), sem passar pela UI."""
    from projetos.tests.factories import AvaliadorIndicadoFactory

    return AvaliadorIndicadoFactory(projeto=projeto, vinculo=vinculo(papel), **campos)


def tela_de_selecao(tela: Tela, edital: Edital) -> Tela:
    """A tela "Indicar Avaliador" do edital, com os projetos pré-selecionados em cartões."""
    return tela.ir(SELECIONAR_AVALIADORES.format(edital.pk)).ver_titulo(f'Selecionar avaliadores dos Projetos do {edital.titulo}')


def tem_grupo(papel: str, grupo: str = GRUPO_AVALIADOR) -> bool:
    return vinculo(papel).user.groups.filter(name=grupo).exists()


def test_indicacao_de_avaliadores_do_projeto(logado_projetos, pre_selecionado):
    """O Coordenador de Extensão filtra a comissão e indica o avaliador; a indicação aparece no cartão do projeto."""
    from projetos.models import AvaliadorIndicado

    projeto = pre_selecionado
    tela = tela_de_selecao(Tela(logado_projetos('coordenador_extensao')), projeto.edital)

    tela.clicar_botao('Buscar')  # o caminho da feature: o filtro vazio mantém o projeto, e a busca entra no `?url=` da volta
    tela.esperar().cartao(projeto.titulo).clicar_botao('Selecionar avaliadores')
    tela.esperar().ver_titulo(f'Indicar Avaliadores do Projeto {projeto.titulo}')
    expect(tela.pagina).to_have_url(re.compile(re.escape(SELECIONAR_AVALIADORES_DO_PROJETO.format(projeto.pk))))
    tela.clicar_botao('Enviar')  # a lista da comissão só aparece com o filtro submetido
    expect(tela.loc(f'//form[starts-with(@action, "{SALVAR_AVALIADORES_DO_PROJETO.format(projeto.pk)}")]')).to_have_count(1)
    tela.selecionar_item('Avaliador Extensão E2E').clicar_botao('Salvar')

    tela.esperar().ver_titulo(f'Selecionar avaliadores dos Projetos do {projeto.edital.titulo}').sucesso('Avaliadores cadastrados com sucesso.')
    indicados = list(AvaliadorIndicado.objects.filter(projeto=projeto).values_list('vinculo', flat=True))
    assert indicados == [vinculo('avaliador').pk], f'a UI disse que indicou, mas os indicados são {indicados}'
    tela.cartao(projeto.titulo).ver_texto('Avaliador Extensão E2E').ver_texto('Não realizou avaliação')


def test_gerente_remove_a_ultima_indicacao_do_avaliador(logado_projetos, pre_selecionado, grupos_de):
    """A remoção apaga a indicação e, sendo a última do avaliador, tira dele o grupo de avaliador."""
    from projetos.models import AvaliadorIndicado

    grupos_de('segundo_avaliador')
    indicacao = indicar(pre_selecionado, 'segundo_avaliador')
    assert AvaliadorIndicado.objects.filter(vinculo=indicacao.vinculo).count() == 1, 'premissa: é a única indicação do avaliador'
    tela = tela_de_selecao(Tela(logado_projetos('gerente')), pre_selecionado.edital)

    clicar_em(tela.cartao(pre_selecionado.titulo), REMOVER_INDICACAO.format(indicacao.pk))
    tela.ver_titulo(f'Selecionar avaliadores dos Projetos do {pre_selecionado.edital.titulo}').sucesso('Indicação de avaliador removida com sucesso.')

    assert not AvaliadorIndicado.objects.filter(pk=indicacao.pk).exists(), 'a UI disse que removeu, mas a indicação ficou'
    assert not tem_grupo('segundo_avaliador'), 'sem indicação nenhuma, o avaliador continuou no grupo de avaliador'


def test_reenvio_do_convite_rejeitado_por_prazo(logado_projetos, pre_selecionado):
    """O convite rejeitado automaticamente volta a valer, com prazos novos contados de hoje."""
    from projetos.models import Edital

    Edital.objects.filter(pk=pre_selecionado.edital.pk).update(prazo_aceite_indicacao=3, prazo_avaliacao=7)
    indicacao = indicar(pre_selecionado, 'segundo_avaliador', rejeitado=True, rejeitado_automaticamente=True, rejeitado_em=datetime.datetime.now())
    tela = tela_de_selecao(Tela(logado_projetos('coordenador_extensao')), pre_selecionado.edital)

    tela.cartao(pre_selecionado.titulo).ver_texto('Rejeitado automaticamente')
    clicar_em(tela, REENVIAR_CONVITE.format(indicacao.pk))
    tela.ver_titulo(f'Selecionar avaliadores dos Projetos do {pre_selecionado.edital.titulo}').sucesso('Convite reenviado com sucesso.')

    indicacao.refresh_from_db()
    assert (indicacao.rejeitado, indicacao.rejeitado_automaticamente, indicacao.rejeitado_em) == (False, False, None), 'o convite não voltou a valer'
    hoje = datetime.date.today()
    prazos = (indicacao.prazo_para_aceite.date(), indicacao.prazo_para_avaliacao.date())
    assert prazos == (hoje + datetime.timedelta(days=3), hoje + datetime.timedelta(days=10)), f'prazos do convite reenviado: {prazos}'


def test_remocao_das_indicacoes_rejeitadas_do_edital(logado_projetos, pre_selecionado, grupos_de):
    """``/remover_indicacoes_rejeitadas/`` não tem link na UI: apaga só as rejeitadas do edital; as pendentes ficam."""
    from projetos.models import AvaliadorIndicado

    grupos_de('segundo_avaliador')
    rejeitada = indicar(pre_selecionado, 'segundo_avaliador', rejeitado=True, rejeitado_em=datetime.datetime.now())
    pendente = indicar(pre_selecionado, 'avaliador')
    tela = Tela(logado_projetos('coordenador_extensao'))

    assert tela.buscar(REMOVER_REJEITADAS.format(pre_selecionado.edital.pk)).status == 302
    restantes = set(AvaliadorIndicado.objects.filter(projeto=pre_selecionado).values_list('pk', flat=True))
    assert restantes == {pendente.pk}, f'esperava só a pendente ({pendente.pk}); ficaram {restantes} (rejeitada: {rejeitada.pk})'
    assert not tem_grupo('segundo_avaliador'), 'sem indicação nenhuma, o avaliador rejeitado continuou no grupo de avaliador'
    tela_de_selecao(tela, pre_selecionado.edital).sucesso('Indicações removidas com sucesso.')


def test_indicacao_em_lote(logado_projetos, pre_selecionado, areas_tematicas_do):
    """O avaliador (com área de interesse) e o edital → os projetos pré-selecionados disponíveis → a indicação de cada marcado."""
    from projetos.models import AreaTematica, AvaliadorIndicado

    avaliador = areas_tematicas_do('avaliador')
    AreaTematica.objects.get(descricao='Cultura').vinculo.add(avaliador)  # o campo "Avaliador" só oferece quem tem área de interesse
    tela = Tela(logado_projetos('coordenador_extensao')).ir(INDICAR_EM_LOTE)

    # `Vinculo.search` guarda o nome da factory, não o renomeado pelo seed: busca-se pela matrícula (o username).
    tela.ver_titulo('Indicar avaliador em lote').preencher('Avaliador', 'autocomplete', PAPEIS['avaliador'], opcao='Avaliador Extensão E2E')
    tela.preencher('Editais', 'autocomplete multiplo', pre_selecionado.edital.titulo)
    tela.clicar_botao('Enviar')
    expect(tela.loc(f'//form[@action="{SALVAR_EM_LOTE.format(avaliador.pk)}"]')).to_have_count(1)
    tela.selecionar_item(pre_selecionado.titulo).clicar_botao('Salvar')

    tela.esperar().ver_titulo('Indicar avaliador em lote').sucesso('Avaliador cadastrado com sucesso.')
    assert AvaliadorIndicado.objects.filter(projeto=pre_selecionado, vinculo=avaliador).exists(), 'a UI disse que indicou, mas não persistiu'


@pytest.fixture
def lote_forjado(logado_projetos, areas_tematicas_do, grupos_de) -> Callable[[Projeto], Tela]:
    """``(projeto) -> Tela``: a tela de lote listando ``projeto`` ao ``avaliador``, com o form de salvar pronto para forjar.

    O alvo dos POSTs forjados é o ``segundo_avaliador`` (não loga; ``grupos_de`` devolve o grupo de
    avaliador que a gravação lhe der). Ele e o ``avaliador`` ganham a área "Cultura": sem área de
    interesse, o campo "Avaliador" não os oferece.
    """
    from projetos.models import AreaTematica

    cultura = AreaTematica.objects.get(descricao='Cultura')
    cultura.vinculo.add(areas_tematicas_do('avaliador'), areas_tematicas_do('segundo_avaliador'))
    grupos_de('segundo_avaliador')

    def _tela(projeto: Projeto) -> Tela:
        tela = Tela(logado_projetos('coordenador_extensao')).ir(INDICAR_EM_LOTE)
        tela.preencher('Avaliador', 'autocomplete', PAPEIS['avaliador'], opcao='Avaliador Extensão E2E')
        tela.preencher('Editais', 'autocomplete multiplo', projeto.edital.titulo)
        tela.clicar_botao('Enviar')
        return tela.esperar()

    return _tela


def forjar_avaliador(tela: Tela, alvo: Vinculo) -> Tela:
    """O POST forjado: o form de salvar passa a apontar para o vínculo ``alvo`` em vez do avaliador escolhido."""
    tela.loc('//form[@id="bolsas_form"]').evaluate(f'(form) => {{ form.action = "{SALVAR_EM_LOTE.format(alvo.pk)}"; }}')
    return tela


def test_lote_nao_indica_membro_da_equipe_ao_proprio_projeto(lote_forjado, pre_selecionado):
    """O membro da equipe (da comissão e com área) não vira avaliador do próprio projeto pelo lote."""
    from projetos.models import AvaliadorIndicado
    from projetos.tests.factories import ParticipacaoFactory

    membro = vinculo('segundo_avaliador')
    ParticipacaoFactory(projeto=pre_selecionado, vinculo_pessoa=membro)
    tela = forjar_avaliador(lote_forjado(pre_selecionado), membro)
    tela.selecionar_item(pre_selecionado.titulo).clicar_botao('Salvar')
    tela.esperar()

    assert not AvaliadorIndicado.objects.filter(projeto=pre_selecionado, vinculo=membro).exists(), (
        'o membro da equipe virou avaliador do próprio projeto'
    )


def test_lote_nao_indica_quem_esta_fora_da_comissao_do_edital(lote_forjado, projeto_enviado_em):
    """Em edital com comissão, o vínculo de fora dela (o form recusaria no ``clean``) não recebe a indicação."""
    from projetos.models import AvaliadorIndicado

    projeto = projeto_enviado_em('selecao', pre_aprovado=True, data_pre_avaliacao=datetime.date.today())
    comissao(projeto.edital, 'avaliador')
    de_fora = vinculo('segundo_avaliador')
    tela = forjar_avaliador(lote_forjado(projeto), de_fora)
    tela.selecionar_item(projeto.titulo).clicar_botao('Salvar')
    tela.esperar()

    assert not AvaliadorIndicado.objects.filter(projeto=projeto, vinculo=de_fora).exists(), 'quem não é da comissão do edital foi indicado'


def test_lote_recusa_avaliador_que_o_campo_nao_oferece(logado_projetos, projetos_seed):
    """O aluno não está no campo "Avaliador" da tela de lote: a gravação para ele é 404 (antes indicava e dava o grupo)."""
    resposta = Tela(logado_projetos('coordenador_extensao')).buscar(SALVAR_EM_LOTE.format(vinculo('aluno').pk))

    assert resposta.status == 404, f'respondeu {resposta.status} à gravação em lote para o vínculo de aluno'


def test_lote_ignora_registro_nao_numerico(lote_forjado, pre_selecionado):
    """``registros=abc`` no POST é ignorado: a gravação volta à tela sem indicar nada (era 500)."""
    from projetos.models import AvaliadorIndicado

    tela = lote_forjado(pre_selecionado)
    tela.linha(pre_selecionado.titulo).loc('//input[@name="registros"]').evaluate('(caixa) => { caixa.value = "abc"; }')
    tela.selecionar_item(pre_selecionado.titulo).clicar_botao('Salvar')

    tela.esperar().ver_titulo('Indicar avaliador em lote').sucesso('Avaliador cadastrado com sucesso.')
    assert not AvaliadorIndicado.objects.filter(projeto=pre_selecionado).exists(), 'o registro não numérico gerou indicação'


def test_membro_da_equipe_nao_vira_avaliador_do_proprio_projeto(logado_projetos, pre_selecionado):
    """A lista já esconde o membro da equipe (controle); o servidor tem de recusá-lo também quando o POST o traz."""
    from projetos.models import AvaliadorIndicado
    from projetos.tests.factories import ParticipacaoFactory

    membro = vinculo('segundo_avaliador')  # da comissão, já no grupo de avaliador e não loga: a view não mexe em grupo de quem loga
    ParticipacaoFactory(projeto=pre_selecionado, vinculo_pessoa=membro)
    rota = f'{SELECIONAR_AVALIADORES_DO_PROJETO.format(pre_selecionado.pk)}?url={SELECIONAR_AVALIADORES.format(pre_selecionado.edital.pk)}'
    tela = Tela(logado_projetos('coordenador_extensao')).ir(rota)
    tela.clicar_botao('Enviar')

    tela.esperar().linha('Avaliador Extensão E2E')
    assert not tela.loc('//tr[contains(normalize-space(.), "Segundo Avaliador E2E")]').count(), 'a lista ofereceu o membro da equipe'
    # O POST forjado: o checkbox do avaliador listado passa a carregar o id do membro da equipe.
    tela.linha('Avaliador Extensão E2E').loc('//input[@name="registros"]').evaluate(f'(caixa) => {{ caixa.value = "{membro.pk}"; }}')
    tela.selecionar_item('Avaliador Extensão E2E').clicar_botao('Salvar')
    tela.esperar()

    assert not AvaliadorIndicado.objects.filter(projeto=pre_selecionado, vinculo=membro).exists(), (
        'o membro da equipe virou avaliador do próprio projeto'
    )


def test_projeto_sem_area_tematica_em_edital_com_temas_nao_lista_avaliador(logado_projetos, pre_selecionado, catalogo_do_edital):
    """Sem área temática, o filtro por área do edital com temas não casa ninguém: a busca e a gravação respondem (eram 500)."""
    from projetos.models import AvaliadorIndicado, Projeto

    Projeto.objects.filter(pk=pre_selecionado.pk).update(area_tematica=None)  # linha antiga ou editada no admin: o envio exige a área
    pre_selecionado.edital.temas.add(catalogo_do_edital.temas[0])
    volta = SELECIONAR_AVALIADORES.format(pre_selecionado.edital.pk)
    tela = Tela(logado_projetos('gerente')).ir(f'{SELECIONAR_AVALIADORES_DO_PROJETO.format(pre_selecionado.pk)}?url={volta}')
    tela.clicar_botao('Enviar')

    tela.esperar().ver_texto('Nenhum avaliador encontrado para os parâmetros de busca informados.')
    assert not tela.loc('//tr[contains(normalize-space(.), "Avaliador Extensão E2E")]').count(), 'o membro da comissão fora da área foi listado'
    resposta = tela.buscar(f'{SALVAR_AVALIADORES_DO_PROJETO.format(pre_selecionado.pk)}?url={volta}')
    assert resposta.status == 302, f'a gravação respondeu {resposta.status}'
    assert not AvaliadorIndicado.objects.filter(projeto=pre_selecionado).exists()


@pytest.fixture
def indicacao_de_outro_campus(edital_novo, projeto_enviado_em) -> AvaliadorIndicado:
    """Indicação REJEITADA do ``segundo_avaliador`` num projeto de outro campus, em edital sem oferta nem autor no CZN.

    É o alvo das sondas de acesso do Coordenador de Extensão do CZN, que não gere esse edital
    (``tem_permissao_acesso_edital`` e ``selecionar_avaliadores`` o barram).
    """
    from projetos.models import OfertaProjeto

    edital = edital_novo(cadastrado_por=None, campus_especifico=True, **janela('selecao'))
    OfertaProjeto.objects.filter(edital=edital).update(uo=outra_uo())
    projeto = projeto_enviado_em('selecao', edital=edital, uo=outra_uo(), pre_aprovado=True, data_pre_avaliacao=datetime.date.today())
    return indicar(projeto, 'segundo_avaliador', rejeitado=True, rejeitado_automaticamente=True, rejeitado_em=datetime.datetime.now())


def test_coordenador_de_extensao_nao_gere_edital_de_outro_campus(logado_projetos, indicacao_de_outro_campus):
    """Controle das sondas abaixo: a tela de seleção e a de indicar do edital alheio já respondem 403 a ele."""
    projeto = indicacao_de_outro_campus.projeto
    tela = Tela(logado_projetos('coordenador_extensao'))

    assert tela.buscar(SELECIONAR_AVALIADORES.format(projeto.edital.pk)).status == 403
    rota = f'{SELECIONAR_AVALIADORES_DO_PROJETO.format(projeto.pk)}?url={SELECIONAR_AVALIADORES.format(projeto.edital.pk)}'
    assert tela.buscar(rota).status == 403


def test_coordenador_de_extensao_nao_reenvia_convite_de_outro_campus(logado_projetos, indicacao_de_outro_campus):
    indicacao = indicacao_de_outro_campus
    resposta = Tela(logado_projetos('coordenador_extensao')).buscar(REENVIAR_CONVITE.format(indicacao.pk))

    indicacao.refresh_from_db()
    assert indicacao.rejeitado, 'a indicação rejeitada de projeto de outro campus foi reativada'
    assert resposta.status == 403, f'respondeu {resposta.status} ao reenvio de convite de outro campus'


def test_coordenador_de_extensao_nao_remove_rejeitadas_de_outro_campus(logado_projetos, indicacao_de_outro_campus, grupos_de):
    from projetos.models import AvaliadorIndicado

    grupos_de('segundo_avaliador')
    indicacao = indicacao_de_outro_campus
    resposta = Tela(logado_projetos('coordenador_extensao')).buscar(REMOVER_REJEITADAS.format(indicacao.projeto.edital.pk))

    assert AvaliadorIndicado.objects.filter(pk=indicacao.pk).exists(), 'a indicação rejeitada de edital de outro campus foi apagada'
    assert resposta.status == 403, f'respondeu {resposta.status} à limpeza de edital de outro campus'


@pytest.mark.parametrize(
    ('papel', 'status'),
    [('gerente', 200), ('coordenador_extensao', 200), ('coordenador_projeto', 403), ('avaliador', 403), ('pre_avaliador', 403)],
)
def test_indicacao_de_avaliadores_por_papel(logado_projetos, projetos_seed, papel, status):
    """``change_projeto``: só o Gerente e o Coordenador de Extensão indicam (tela de seleção e lote)."""
    edital = projetos_seed.editais['selecao']
    tela = Tela(logado_projetos(papel))
    rotas = (SELECIONAR_AVALIADORES.format(edital.pk), INDICAR_EM_LOTE)

    assert {rota: tela.buscar(rota).status for rota in rotas} == dict.fromkeys(rotas, status)


def test_tela_de_selecao_lista_o_pre_selecionado_do_seed(logado_projetos, projetos_seed):
    """O projeto pré-selecionado aparece em cartão com o botão de indicar, sem indicação ainda."""
    projeto = projetos_seed.projetos['pre_selecionado']
    tela = tela_de_selecao(Tela(logado_projetos('coordenador_extensao')), projetos_seed.editais['selecao'])

    tela.cartao(projeto.titulo).ver_botao('Selecionar avaliadores')
