"""Roteiro navegado da tarefa 11 da doc: tarefas vinculadas ao chamado.

Quem cadastra o *catálogo* de tarefas é o gestor (admin); quem vincula a tarefa ao chamado é o
atendente, pela aba Tarefas do próprio chamado; e ambos acompanham pela lista administrativa de
tarefas (menu "Tarefas"). O chamado é montado pela fixture já Em Atendimento e atribuído ao
atendente — é esse o estado em que a aba Tarefas aparece com o botão de vincular.
"""

from __future__ import annotations

import pytest
from django.utils import timezone

from djtools.e2e_ui import Tela, anotar_tela

from .conftest import PAPEIS, SERVICO, TAREFA, centro_local, popup_em, servico

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

TAREFA_ADMIN = '/admin/centralservicos/tarefa/'
TAREFAS_VINCULADAS = '/admin/centralservicos/tarefachamado/?tab=tab_ativas'


@pytest.fixture
def chamado_atribuido_ao_atendente(doc_seed, usuarios_doc):
    """Chamado Em Atendimento já atribuído ao atendente — o estado em que se vincula tarefa."""
    from centralservicos.models import Chamado
    from rh.models import UnidadeOrganizacional

    atendente = usuarios_doc('atendente')
    Chamado.objects.filter(servico__nome=servico().nome, aberto_por=atendente).delete()

    campus = UnidadeOrganizacional.objects.suap().get(sigla='CZN')
    chamado = Chamado(
        descricao='Manutenção preventiva da impressora da recepção.',
        servico=servico(),
        aberto_em=timezone.now(),
        aberto_por=atendente,
        requisitante=atendente,
        interessado=atendente,
        campus=campus,
        meio_abertura=Chamado.MEIO_ABERTURA_PESSOALMENTE,
    )
    chamado.centro_atendimento = centro_local()
    chamado.save()
    grupo = chamado.get_atendimento_atribuicao_atual().grupo_atendimento
    chamado.atribuir_atendente(grupo, atendente, atendente)
    chamado.colocar_em_atendimento(atendente)
    return chamado


def test_cadastrar_e_acompanhar_tarefas(logado_doc, capturar, chamado_atribuido_ao_atendente):
    """Tarefa 11 — cadastrar a tarefa, vinculá-la ao chamado e acompanhar a lista."""
    from centralservicos.models import Tarefa, TarefaChamado, TarefaChamadoHistorico

    Tarefa.objects.filter(titulo=TAREFA).delete()

    tela = Tela(logado_doc('gestor')).ir(TAREFA_ADMIN)
    capturar(tela.pagina, '11-tarefa-listagem')
    tela.clicar_botao('Adicionar Tarefa')
    tela.ver_titulo('Adicionar Cadastro de Tarefa da Central de Serviços')
    anotar_tela('tarefa-form', tela)
    tela.preencher_formulario(
        [
            ('Serviço', 'autocomplete', SERVICO),
            ('Título', 'texto', TAREFA),
            ('Descrição', 'textarea', 'Conferir o estado da impressora antes de acionar a assistência.'),
        ]
    )
    capturar(tela.pagina, '11-tarefa-formulario')
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')
    assert Tarefa.objects.filter(titulo=TAREFA).exists(), 'a UI disse que salvou, mas a tarefa não existe'

    chamado = chamado_atribuido_ao_atendente
    tela = Tela(logado_doc('atendente')).ir(f'/centralservicos/chamado/{chamado.pk}/')
    tela.clicar_aba('Tarefas')
    tela.clicar_link('Adicionar tarefa')
    popup = popup_em(tela, 'vincular_tarefa_chamado')
    anotar_tela('vincular-tarefa-popup', popup)
    popup.preencher('Tarefa', 'autocomplete', TAREFA)
    popup.preencher('Responsável', 'autocomplete', PAPEIS['responsavel'])
    capturar(tela.pagina, '11-vincular-tarefa')
    popup.salvar_no_popup('Salvar')

    tela = Tela(logado_doc('atendente')).ir(f'/centralservicos/chamado/{chamado.pk}/')
    tela.clicar_aba('Tarefas')
    tela.ver_texto(TAREFA)
    capturar(tela.pagina, '11-tarefa-vinculada')

    # Quem altera a situação da tarefa é o responsável por ela, não quem a vinculou: o link
    # "Alterar" só é renderizado para ele (`pode_atualizar_situacao`).
    tela = Tela(logado_doc('responsavel')).ir(f'/centralservicos/chamado/{chamado.pk}/')
    tela.clicar_aba('Tarefas')
    tela.clicar_link('Alterar')
    popup = popup_em(tela, 'editar_tarefa_chamado')
    anotar_tela('editar-tarefa-popup', popup)
    popup.preencher('Situação', 'lista', 'Em Andamento')
    capturar(tela.pagina, '11-alterar-tarefa')
    popup.salvar_no_popup('Salvar')

    tarefa_chamado = TarefaChamado.objects.filter(chamado=chamado, tarefa__titulo=TAREFA).first()
    assert tarefa_chamado is not None, 'a tarefa não foi vinculada ao chamado'
    assert tarefa_chamado.situacao == TarefaChamado.SITUACAO_EM_ANDAMENTO, 'a situação não foi alterada'
    assert TarefaChamadoHistorico.objects.filter(tarefa_chamado=tarefa_chamado).count() >= 2, 'o histórico não registrou as mudanças'

    tela = Tela(logado_doc('gestor')).ir(TAREFAS_VINCULADAS)
    tela.ver_texto(TAREFA)
    capturar(tela.pagina, '11-tarefas-vinculadas')
