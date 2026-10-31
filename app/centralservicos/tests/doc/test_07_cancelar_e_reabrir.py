"""Roteiro navegado de dois desfechos do acompanhamento: cancelar e reabrir.

Ambos são do solicitante e ficam na tarefa 8 da doc, junto com comentar/anexar. O chamado a
cancelar nasce por ORM (a abertura já foi documentada na tarefa 6) e o a reabrir é um chamado
resolvido pelo atendente — o único estado em que o botão **Reabrir chamado** aparece.
"""

from __future__ import annotations

import pytest
from django.utils import timezone

from djtools.e2e_ui import Tela

from .conftest import artigo, centro_local, servico, usuarios_doc

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]


def _criar_chamado(interessado, descricao: str):
    from centralservicos.models import Chamado
    from rh.models import UnidadeOrganizacional

    campus = UnidadeOrganizacional.objects.suap().get(sigla='CZN')
    chamado = Chamado(
        descricao=descricao,
        servico=servico(),
        aberto_em=timezone.now(),
        aberto_por=interessado,
        requisitante=interessado,
        interessado=interessado,
        campus=campus,
        meio_abertura=Chamado.MEIO_ABERTURA_WEB,
    )
    chamado.centro_atendimento = centro_local()
    chamado.save()
    return chamado


@pytest.fixture
def chamado_para_cancelar(doc_seed, usuarios_doc):
    from centralservicos.models import Chamado

    interessado = usuarios_doc('solicitante')
    Chamado.objects.filter(descricao__startswith='Cancelamento:').delete()
    return _criar_chamado(interessado, 'Cancelamento: chamado aberto por engano.')


@pytest.fixture
def chamado_resolvido_para_reabrir(doc_seed, usuarios_doc):
    from centralservicos.models import Chamado

    atendente = usuarios_doc('atendente')
    interessado = usuarios_doc('solicitante')
    Chamado.objects.filter(descricao__startswith='Reabertura:').delete()

    chamado = _criar_chamado(interessado, 'Reabertura: impressora voltou a falhar depois do reparo.')
    grupo = chamado.get_atendimento_atribuicao_atual().grupo_atendimento
    chamado.atribuir_atendente(grupo, atendente, atendente)
    chamado.colocar_em_atendimento(atendente)
    chamado.resolver_chamado(atendente, [artigo()], observacao='Limpeza da bandeja resolveu.')
    return chamado


def test_cancelar_e_reabrir_chamado(logado_doc, capturar, chamado_para_cancelar, chamado_resolvido_para_reabrir):
    """Cancelar um chamado aberto por engano e reabrir um resolvido que voltou a falhar."""
    tela = Tela(logado_doc('solicitante')).ir(f'/centralservicos/chamado/{chamado_para_cancelar.pk}/')
    tela.ver_titulo(f'Chamado {chamado_para_cancelar.pk}')
    tela.clicar_link('Cancelar')
    tela.ver_titulo(f'Cancelar {chamado_para_cancelar}')
    tela.preencher('Comentário', 'textarea', 'Abri o chamado no serviço errado; vou abrir no serviço correto.')
    capturar(tela.pagina, '08-cancelar-chamado')
    tela.clicar_botao('Salvar')
    tela.sucesso('Situação alterada com sucesso.')
    chamado_para_cancelar = type(chamado_para_cancelar).objects.get(pk=chamado_para_cancelar.pk)
    assert chamado_para_cancelar.estah_cancelado(), 'o chamado não foi cancelado'

    tela.ir(f'/centralservicos/chamado/{chamado_resolvido_para_reabrir.pk}/')
    tela.ver_titulo(f'Chamado {chamado_resolvido_para_reabrir.pk}')
    tela.clicar_link('Reabrir chamado')
    tela.ver_titulo('Alterar Situação para Reaberto')
    tela.preencher('Comentário', 'textarea', 'A impressora apresentou o mesmo defeito dois dias depois.')
    capturar(tela.pagina, '08-reabrir-chamado')
    tela.clicar_botao('Salvar')
    tela.sucesso('Situação alterada com sucesso.')
    chamado_resolvido_para_reabrir = type(chamado_resolvido_para_reabrir).objects.get(pk=chamado_resolvido_para_reabrir.pk)
    from centralservicos.models import StatusChamado

    assert chamado_resolvido_para_reabrir.status == StatusChamado.get_status_reaberto(), 'o chamado deveria ficar Reaberto'
    assert chamado_resolvido_para_reabrir.get_atendente_do_chamado().username == '161102', 'o atendente anterior deveria ser mantido'
