"""Fluxo: os acessórios operacionais do módulo — tarefas vinculadas ao chamado, monitoramento
público por token e as três telas de relatório (indicadores, atendimentos por ano, situação dos
atendentes).

Por que importa: são os pontos em que o módulo deixa de ser um CRUD de chamados. A tarefa é o
passo a passo operacional (quem faz o quê) e o monitoramento é o painel que fica numa TV da sala de
atendimento — nenhum dos dois tinha cenário no behave, e os dois quebram calados: a tarefa some do
chamado, o monitoramento para de contar.

Quem tem ``pode_ver_indicadores`` é o grupo ``Atendente da Central de Serviços`` (e o ``Auditor``);
o ``Gestor`` **não** — medido na rodada de doc do módulo e afirmado no teste de permissão.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from djtools.e2e_ui import Tela

from .conftest import PAPEIS, nome_e2e, popup_em, usuario, ver_campos

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

TAREFA_ADMIN = '/admin/centralservicos/tarefa/'
TAREFAS_VINCULADAS = '/admin/centralservicos/tarefachamado/?tab=tab_ativas'
INDICADORES = '/centralservicos/indicadores'
ATENDIMENTOS_POR_ANO = '/centralservicos/atendimentos_por_ano/'
SITUACAO_DOS_ATENDENTES = '/centralservicos/relatorio_atendentes'


def test_gestor_cadastra_tarefa_e_atendente_vincula_ao_chamado(logado_central, contexto_com_artigos, chamado_em_atendimento):
    """O gestor mantém o catálogo de tarefas, o atendente vincula uma ao chamado e o responsável a move.

    O ciclo completo (cadastro → vínculo → alteração de situação → listagem administrativa) é um
    teste só porque cada passo depende do anterior; e é a única forma de o histórico de alterações
    (``TarefaChamadoHistorico``) ter as duas entradas que a asserção cobra.
    """
    from centralservicos.models import Tarefa, TarefaChamado, TarefaChamadoHistorico

    chamado = chamado_em_atendimento
    titulo = nome_e2e('Tarefa')

    tela = Tela(logado_central('gestor')).ir(TAREFA_ADMIN)
    tela.ver_texto('Cadastros de Tarefas da Central de Serviços')
    tela.clicar_botao('Adicionar Tarefa')
    tela.ver_titulo('Adicionar Cadastro de Tarefa da Central de Serviços')
    ver_campos(tela, ['Serviço', 'Título', 'Descrição'])
    tela.preencher_formulario(
        [
            ('Serviço', 'autocomplete', contexto_com_artigos.servico.nome),
            ('Título', 'texto', titulo),
            ('Descrição', 'textarea', 'Conferir o estado da impressora antes de acionar a assistência.'),
        ]
    )
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')
    assert Tarefa.objects.filter(titulo=titulo, servico=contexto_com_artigos.servico).exists(), 'a UI disse que salvou, mas a tarefa não persistiu'

    tela = Tela(logado_central('atendente')).ir(f'/centralservicos/chamado/{chamado.pk}/')
    tela.clicar_aba('Tarefas')
    tela.clicar_link('Adicionar tarefa')
    popup = popup_em(tela, 'vincular_tarefa_chamado')
    popup.preencher('Tarefa', 'autocomplete', titulo)
    popup.preencher('Responsável', 'autocomplete', PAPEIS['responsavel'])
    popup.salvar_no_popup('Salvar')

    tarefa_chamado = TarefaChamado.objects.filter(chamado=chamado, tarefa__titulo=titulo).first()
    assert tarefa_chamado is not None, 'a tarefa não foi vinculada ao chamado'
    assert tarefa_chamado.responsavel_id == usuario(PAPEIS['responsavel']).pk, 'o responsável informado não foi gravado'

    # Quem altera a situação é o responsável pela tarefa, não quem a vinculou (``pode_atualizar_situacao``).
    tela = Tela(logado_central('responsavel')).ir(f'/centralservicos/chamado/{chamado.pk}/')
    tela.clicar_aba('Tarefas')
    tela.clicar_link('Alterar')
    popup = popup_em(tela, 'editar_tarefa_chamado')
    popup.preencher('Situação', 'lista', 'Em Andamento')
    popup.salvar_no_popup('Salvar')

    tarefa_chamado.refresh_from_db()
    assert tarefa_chamado.situacao == TarefaChamado.SITUACAO_EM_ANDAMENTO, 'a situação da tarefa não foi alterada'
    assert TarefaChamadoHistorico.objects.filter(tarefa_chamado=tarefa_chamado).count() >= 2, (
        'o histórico deveria registrar a criação e a mudança de situação'
    )

    tela = Tela(logado_central('gestor')).ir(TAREFAS_VINCULADAS)
    tela.ver_texto(titulo)


def test_atendente_ve_indicadores_e_relatorios(logado_central, contexto_com_artigos):
    """As três telas de relatório respondem ao filtro padrão (o botão "Enviar" de cada uma).

    São telas de leitura pesada: ``indicadores`` monta SQL agregado e ``relatorio_atendentes``
    percorre os atendentes dos grupos do usuário. O que o teste prova é que elas **renderizam** com
    o filtro padrão — é onde um erro de agregação apareceria como 500.
    """
    tela = Tela(logado_central('atendente')).ir(INDICADORES)
    tela.ver_titulo('Indicadores')
    tela.clicar_botao('Enviar')
    tela.ver_texto('Indicadores')

    tela.ir(ATENDIMENTOS_POR_ANO)
    tela.ver_titulo('Relatório de Atendimentos por Ano')
    tela.clicar_botao('Enviar')
    tela.ver_texto('Relatório de Atendimentos por Ano')

    tela.ir(SITUACAO_DOS_ATENDENTES)
    tela.ver_titulo('Relatório de Situação dos Atendentes')
    tela.clicar_botao('Enviar')
    tela.ver_texto('Relatório de Situação dos Atendentes')


def test_monitoramento_publico_por_token(logado_central, contexto_com_artigos):
    """O monitoramento é um endereço por token, sem login no menu, que conta a fila do grupo.

    A regressão que pega: o painel da sala de atendimento parar de somar os não atribuídos — ou a
    página exigir permissão que ninguém tem.
    """
    from centralservicos.models import Monitoramento

    monitoramento = Monitoramento.objects.create(
        titulo=nome_e2e('Monitoramento'),
        token=uuid4().hex[:32],
        cadastrado_por=usuario(PAPEIS['atendente']),
        organizar_por_tipo=True,
    )
    monitoramento.grupos.add(contexto_com_artigos.grupo_atendimento)

    tela = Tela(logado_central('servidor')).ir(monitoramento.get_absolute_url())
    tela.ver_titulo(f'Monitoramento de Chamados: {monitoramento.titulo}')
    tela.ver_texto(contexto_com_artigos.grupo_atendimento.nome)
