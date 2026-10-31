"""Smoke das rotas do almoxarifado que os fluxos não declaram.

O gate ``bin/scripts/paridade_e2e.py almoxarifado --rotas`` lê **literais**: as rotas que os arquivos
de fluxo alcançam por clique não aparecem para ele. Aqui cada uma entra como URL literal, resolvida
com os objetos que as fixtures do módulo criam, e a asserção é o status esperado (``200``, ``302``
de ``httprr`` ou ``403`` de permissão) — é o piso de declaração; quem cobre comportamento são os
``test_*.py`` de fluxo.

**Não entram aqui** as rotas que mudam estado por GET sem ``require_POST`` (remoções, estornos e
recálculos): visitá-las apagaria dado compartilhado do seed. Elas estão em ``ROTAS_DISPENSADAS`` no
conftest, com o motivo, e são achados do MR.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]


@pytest.fixture
def alvos(almoxarifado_a0, requisicao_pendente, servidores_almox) -> SimpleNamespace:
    """Ids reais para o smoke: empenho do seed, requisição pendente nova e entrada do campus A0."""
    from almoxarifado.models import Empenho
    from almoxarifado.tests.factories import EntradaFactory

    uo, _setor, material = almoxarifado_a0
    requisicao, _item = requisicao_pendente
    return SimpleNamespace(
        uo_id=uo.pk,
        uo_sigla=uo.sigla,
        material_id=material.pk,
        empenho_pk=Empenho.objects.get(numero='20193012RE').pk,
        entrada_id=EntradaFactory(uo=uo).pk,
        requisicao_id=requisicao.pk,
        solicitante_id=servidores_almox['CoordDeAlmoxSiste'].get_vinculo().pk,
        elemento_despesa_id=1,
    )


# (rota, status esperado, motivo do status). O motivo fica na mensagem de falha: quando a rota
# quebra, o relatório diz qual fronteira caiu (permissão, sessão, dado ausente).
CASOS = [
    ('/almoxarifado/ajax/info_solicitante/', 403, 'exige POST com solicitante_id'),
    ('/almoxarifado/buscar_empenho/x/', 200, 'autocomplete de empenho'),
    ('/almoxarifado/buscar_fornecedor/x/', 200, 'autocomplete de fornecedor, usado em entrada_compra'),
    ('/almoxarifado/buscar_material_consumo_estoque_uo/{uo_id}/x/', 200, 'autocomplete de material com estoque na UO'),
    ('/almoxarifado/buscar_servidor/x/', 200, 'autocomplete de servidor da UO'),
    ('/almoxarifado/cancelar_requisicaosaida/user/{uo_id}/{requisicao_id}/', 200, 'tela de cancelamento da requisição'),
    ('/almoxarifado/detalhar_elemento_despesa/{elemento_despesa_id}/', 200, 'detalhamento de elemento de despesa'),
    ('/almoxarifado/devolver_item/user/{uo_id}/{requisicao_id}/', 200, 'tela de devolução de item'),
    ('/almoxarifado/empenho/{empenho_pk}/', 200, 'detalhe do empenho do seed'),
    ('/almoxarifado/entrada/{entrada_id}/', 200, 'detalhe da entrada'),
    ('/almoxarifado/entrada/{entrada_id}/adicionar_item/', 200, 'formulário de item da entrada'),
    ('/almoxarifado/entrada/{entrada_id}/cancelar_itens/', 403, 'remove itens de entrada; o papel do smoke não tem a permissão'),
    ('/almoxarifado/entrada/{entrada_id}/editar/', 200, 'edição da entrada'),
    ('/almoxarifado/entrada_compra/', 200, 'formulário de entrada por compra'),
    ('/almoxarifado/entrada_doacao/', 200, 'formulário de entrada por doação'),
    ('/almoxarifado/entrada_realizar/', 302, 'POST-only: GET cai no `httprr` de erro'),
    ('/almoxarifado/form_requisicao_usuario_pedido/', 200, 'formulário de requisição do usuário'),
    ('/almoxarifado/gerar_etiquetas/', 200, 'tela de geração de etiquetas'),
    ('/almoxarifado/material_historico/{material_id}/', 200, 'histórico do material'),
    ('/almoxarifado/relatorio/balancete_ed_detalhado_html/1/', 302, 'balancete vive no cache; id inválido devolve httprr de erro'),
    ('/almoxarifado/relatorio/balancete_ed_detalhado_pdf/1/', 302, 'idem, na versão PDF'),
    ('/almoxarifado/relatorio/balancete_material_pdf', 302, 'delega a exportação e redireciona (`httprr`) com período e UO'),
    ('/almoxarifado/relatorio/consumo_setor_html/1/', 403, 'relatório vive na sessão; id desconhecido é PermissionDenied'),
    ('/almoxarifado/relatorio/consumo_setor_pdf/1/', 403, 'idem, na versão PDF'),
    ('/almoxarifado/relatorio/nota_fornecimento_pdf/user/{requisicao_id}/', 200, 'nota de fornecimento da requisição'),
    (
        '/almoxarifado/relatorio/nota_fornecimento_pdf/{solicitante_id}/2020-01-01/2020-12-31/',
        403,
        'nota por solicitante exige vínculo com permissão',
    ),
    ('/almoxarifado/relatorio_compra/', 200, 'relatório de compra'),
    ('/almoxarifado/requisicao_detalhe/user/{requisicao_id}/', 200, 'detalhe da requisição pendente'),
    ('/almoxarifado/requisicao_usuario_pedido/', 302, 'POST-only: GET cai no `httprr` de erro'),
    ('/almoxarifado/validar/entrada/', 200, 'validação de entrada (endpoint JSON)'),
    ('/almoxarifado/validar/req_pedido/', 200, 'validação de requisição (endpoint JSON)'),
    ('/almoxarifado/validar/requisicao_responder/user/', 200, 'validação de resposta de requisição'),
]


@pytest.mark.parametrize(('rota', 'status_esperado', 'motivo'), CASOS, ids=[caso[0] for caso in CASOS])
def test_rota_responde_como_esperado(logado_almox, alvos, rota, status_esperado, motivo):
    """Cada rota declarada responde o status do contrato, com o papel de maior alcance do módulo."""
    tela = Tela(logado_almox('CoordDeAlmoxSiste'))
    url = rota.format(**vars(alvos))
    if rota == '/almoxarifado/relatorio/balancete_material_pdf':
        url += f'?dt_ini=2020-01-01&dt_fim=2020-12-31&uo={alvos.uo_id}&estoque=True'
    resposta = tela.buscar(url)
    assert resposta.status == status_esperado, f'{rota} respondeu HTTP {resposta.status} (esperado {status_esperado}: {motivo})'
