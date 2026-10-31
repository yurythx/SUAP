"""Roteiro navegado das tarefas de configuração do ``centralservicos`` — tarefas 1 a 3 da doc.

Ordem da doc, que é ordem de dependência: a área e o gestor existem antes do catálogo; os
centros e grupos de atendimento antes do serviço (o serviço é vinculado a um centro); e o
serviço antes de tudo que abre chamado.

Cada teste é idempotente dentro da sessão: apaga os próprios registros antes de recriá-los pela
tela, porque a rodada do CI usa ``--reruns 2`` e um reteste depois de falha parcial reencontraria
os registros da tentativa anterior.
"""

from __future__ import annotations

import pytest

from djtools.e2e_ui import Tela, anotar_tela

from .conftest import (
    AREA,
    CATEGORIA,
    CENTRO_LOCAL,
    CENTRO_SISTEMICO,
    GRUPO_LOCAL,
    GRUPO_SERVICO,
    GRUPO_SISTEMICO,
    PAPEIS,
    SERVICO,
)

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

AREA_ADMIN = '/admin/comum/areaatuacao/'
GESTOR_ADMIN = '/admin/centralservicos/gestorareaservico/'
CENTRO_ADMIN = '/admin/centralservicos/centroatendimento/'
GRUPO_ADMIN = '/admin/centralservicos/grupoatendimento/'
CATEGORIA_ADMIN = '/admin/centralservicos/categoriaservico/'
GRUPO_SERVICO_ADMIN = '/admin/centralservicos/gruposervico/'
SERVICO_ADMIN = '/admin/centralservicos/servico/'

MATRICULA_GESTOR = PAPEIS['gestor']
MATRICULA_ATENDENTE = PAPEIS['atendente']
MATRICULA_RESPONSAVEL = PAPEIS['responsavel']
MATRICULA_CONTRIBUINTE = PAPEIS['contribuinte']
MATRICULA_SUPERVISOR = PAPEIS['supervisor']


def _selecionar_grupo_superior(tela: Tela, nome: str) -> None:
    """Escolhe o nó no ``TreeWidget`` do campo ``Grupo de Atendimento Superior``.

    Esse campo não é select2 como os demais do admin: ``GrupoAtendimentoAdmin.get_form`` troca o
    widget por um ``TreeWidget`` (jstree), que renderiza a árvore num ``div.tree-container`` e
    guarda a pk escolhida num ``input[type=hidden]``. Clicar no nó é o que dispara o
    ``select_node.jstree`` que preenche o input — ``preencher(..., 'autocomplete')`` não acha o
    campo.
    """
    tela.loc(f'//div[contains(@class, "tree-container")]//a[contains(normalize-space(.), "{nome}")]').first.click()


def _limpar_area(nome: str) -> None:
    """Apaga a área e tudo que pende dela — o estado de partida do teste 1.

    A Área de Atuação está no topo da cadeia (serviço, centro, categoria e artigo apontam
    para ela com ``CASCADE``), então apagá-la devolve o banco ao ponto de partida.
    """
    from comum.models import AreaAtuacao

    AreaAtuacao.objects.filter(nome=nome).delete()


# ---------------------------------------------------------------------------------------------
# Tarefa 1 — Definir a área de serviço e o gestor que responde por ela
# ---------------------------------------------------------------------------------------------


def test_cadastrar_area_e_gestor(logado_doc, capturar):
    """Tarefa 1 — o administrador da Central cria a área de atuação e nomeia o gestor.

    São duas telas de administração em apps diferentes (``comum`` e ``centralservicos``) e um
    único objetivo: dar a uma área de serviço quem responde por ela.
    """
    _limpar_area(AREA)

    tela = Tela(logado_doc('admin')).ir(AREA_ADMIN)
    tela.ver_titulo('Áreas de Atuação')
    capturar(tela.pagina, '01-area-listagem')
    tela.clicar_botao('Adicionar Área de Atuação')
    tela.ver_titulo('Adicionar Área de Atuação')
    anotar_tela('area-form', tela)
    tela.preencher_formulario(
        [
            ('Nome', 'texto', AREA),
            ('Ícone', 'texto', 'wrench'),
            ('Ativo?', 'checkbox', 'marcar'),
        ]
    )
    capturar(tela.pagina, '01-area-formulario')
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')

    tela.ir(GESTOR_ADMIN)
    tela.ver_titulo('Gestores das Áreas dos Serviços')
    capturar(tela.pagina, '01-gestor-listagem')
    tela.clicar_botao('Adicionar Gestor da Área do Serviço')
    tela.ver_titulo('Adicionar Gestor da Área do Serviço')
    anotar_tela('gestor-form', tela)
    tela.preencher_formulario(
        [
            ('Gestor', 'autocomplete', MATRICULA_GESTOR),
            ('Área do Serviço', 'autocomplete', AREA),
        ]
    )
    capturar(tela.pagina, '01-gestor-formulario')
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')

    from comum.models import AreaAtuacao
    from centralservicos.models import GestorAreaServico

    assert AreaAtuacao.objects.filter(nome=AREA).exists(), 'a UI disse que salvou, mas a área não existe'
    assert GestorAreaServico.objects.filter(gestor__username=MATRICULA_GESTOR, area__nome=AREA).exists(), (
        'a UI disse que salvou, mas o gestor não foi vinculado'
    )


# ---------------------------------------------------------------------------------------------
# Tarefa 2 — Montar a estrutura de atendimento (centros e grupos, em níveis)
# ---------------------------------------------------------------------------------------------


def test_cadastrar_estrutura_de_atendimento(logado_doc, capturar):
    """Tarefa 2 — o gestor cria os centros e os grupos de atendimento, do superior ao local.

    O grupo superior nasce primeiro porque é ele que o grupo local aponta em "Grupo de
    Atendimento Superior"; é esse vínculo que habilita Escalar/Retornar no chamado. Os dois
    grupos recebem os mesmos atendente e responsável porque é o responsável que atribui e
    encaminha.
    """
    from centralservicos.models import CentroAtendimento, GrupoAtendimento

    # Idempotência: apaga na ordem inversa das FKs (o grupo aponta para o centro e para o
    # grupo superior; o centro aponta para a área).
    GrupoAtendimento.objects.filter(nome__in=[GRUPO_LOCAL, GRUPO_SISTEMICO]).delete()
    CentroAtendimento.objects.filter(nome__in=[CENTRO_LOCAL, CENTRO_SISTEMICO], area__nome=AREA).delete()

    tela = Tela(logado_doc('gestor')).ir(CENTRO_ADMIN)
    tela.ver_titulo('Centros de Atendimento')
    capturar(tela.pagina, '02-centro-listagem')
    tela.clicar_botao('Adicionar Centro de Atendimento')
    tela.ver_titulo('Adicionar Centro de Atendimento')
    anotar_tela('centro-sistemico-form', tela)
    tela.preencher_formulario(
        [
            ('Nome', 'texto', CENTRO_SISTEMICO),
            ('Área do Serviço', 'autocomplete', AREA),
            ('Ativo?', 'checkbox', 'marcar'),
        ]
    )
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')

    tela.ir(CENTRO_ADMIN).clicar_botao('Adicionar Centro de Atendimento')
    tela.ver_titulo('Adicionar Centro de Atendimento')
    anotar_tela('centro-local-form', tela)
    tela.preencher_formulario(
        [
            ('Nome', 'texto', CENTRO_LOCAL),
            ('Centro de Atendimento Local?', 'checkbox', 'marcar'),
            ('Área do Serviço', 'autocomplete', AREA),
            ('Ativo?', 'checkbox', 'marcar'),
        ]
    )
    capturar(tela.pagina, '02-centro-formulario')
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')

    tela.ir(GRUPO_ADMIN).clicar_botao('Adicionar Grupo de Atendimento')
    tela.ver_titulo('Adicionar Grupo de Atendimento')
    anotar_tela('grupo-sistemico-form', tela)
    tela.preencher_formulario(
        [
            ('Campus', 'autocomplete', 'CZN'),
            ('Centro de Atendimento', 'autocomplete', CENTRO_SISTEMICO),
            ('Nome', 'texto', GRUPO_SISTEMICO),
            ('Responsáveis', 'autocomplete multiplo', MATRICULA_RESPONSAVEL),
            ('Atendentes Vinculados ao Grupo', 'autocomplete multiplo', f'{MATRICULA_ATENDENTE},{MATRICULA_RESPONSAVEL}'),
            ('Ativo?', 'checkbox', 'marcar'),
        ]
    )
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')

    tela.ir(GRUPO_ADMIN).clicar_botao('Adicionar Grupo de Atendimento')
    tela.ver_titulo('Adicionar Grupo de Atendimento')
    anotar_tela('grupo-local-form', tela)
    _selecionar_grupo_superior(tela, GRUPO_SISTEMICO)
    tela.preencher_formulario(
        [
            ('Campus', 'autocomplete', 'CZN'),
            ('Centro de Atendimento', 'autocomplete', CENTRO_LOCAL),
            ('Nome', 'texto', GRUPO_LOCAL),
            ('Responsáveis', 'autocomplete multiplo', MATRICULA_RESPONSAVEL),
            # O supervisor revisa os artigos e o contribuinte os escreve: os dois precisam
            # enxergar a área, e o admin da Base de Conhecimento só oferece as áreas dos
            # grupos de atendimento do usuário.
            (
                'Atendentes Vinculados ao Grupo',
                'autocomplete multiplo',
                f'{MATRICULA_ATENDENTE},{MATRICULA_RESPONSAVEL},{MATRICULA_SUPERVISOR},{MATRICULA_CONTRIBUINTE}',
            ),
            ('Ativo?', 'checkbox', 'marcar'),
        ]
    )
    capturar(tela.pagina, '02-grupo-formulario')
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')

    assert GrupoAtendimento.objects.get(nome=GRUPO_LOCAL).grupo_atendimento_superior.nome == GRUPO_SISTEMICO, (
        'a UI disse que salvou, mas o grupo local não aponta para o superior'
    )


# ---------------------------------------------------------------------------------------------
# Tarefa 3 — Cadastrar um serviço no catálogo
# ---------------------------------------------------------------------------------------------


def test_cadastrar_servico(logado_doc, capturar):
    """Tarefa 3 — o gestor cria a categoria, o grupo de serviço e o serviço.

    Três telas, um objetivo: publicar no catálogo o serviço que o solicitante escolhe ao abrir
    o chamado. O serviço é vinculado aos dois centros (o local e o sistêmico) porque a
    reclassificação documentada na tarefa 9 troca o centro do chamado.
    """
    from centralservicos.models import CategoriaServico, GrupoServico, Servico

    # Idempotência: apaga o serviço e o grupo de serviço (a categoria é FK do grupo; a ordem
    # inversa evita deixar grupo órfão).
    Servico.objects.filter(nome=SERVICO).delete()
    GrupoServico.objects.filter(nome=GRUPO_SERVICO).delete()
    CategoriaServico.objects.filter(nome=CATEGORIA).delete()

    tela = Tela(logado_doc('gestor')).ir(CATEGORIA_ADMIN)
    tela.ver_titulo('Categorias de Serviço')
    capturar(tela.pagina, '03-categoria-listagem')
    tela.clicar_botao('Adicionar Categoria de Serviço')
    tela.ver_titulo('Adicionar Categoria de Serviço')
    anotar_tela('categoria-form', tela)
    tela.preencher_formulario([('Nome', 'texto', CATEGORIA), ('Área do Serviço', 'autocomplete', AREA)])
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')

    tela.ir(GRUPO_SERVICO_ADMIN).clicar_botao('Adicionar Grupo de Serviço')
    tela.ver_titulo('Adicionar Grupo de Serviço')
    anotar_tela('grupo-servico-form', tela)
    tela.preencher_formulario(
        [
            ('Nome', 'texto', GRUPO_SERVICO),
            ('Detalhamento', 'textarea', 'Serviço de impressão e digitalização de documentos.'),
            ('Categorias', 'autocomplete multiplo', CATEGORIA),
            ('Ícone', 'texto', 'print'),
        ]
    )
    capturar(tela.pagina, '03-grupo-servico-formulario')
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')

    tela.ir(SERVICO_ADMIN).clicar_botao('Adicionar Serviço')
    tela.ver_titulo('Adicionar Serviço')
    anotar_tela('servico-form', tela)
    tela.preencher_formulario(
        [
            ('Nome', 'texto', SERVICO),
            ('Tipo', 'lista', 'Incidente'),
            ('Área do Serviço', 'lista', AREA),
            ('Grupo de Serviço', 'autocomplete', GRUPO_SERVICO),
            # Os dois centros entram no serviço: a abertura escolhe um deles e a
            # reclassificação troca para o outro.
            ('Centros de Atendimento', 'autocomplete multiplo', f'{CENTRO_LOCAL},{CENTRO_SISTEMICO}'),
            ('SLA utilizado', 'lista', 'Usar o SLA manual'),
            ('SLA manual (em horas)', 'texto', '12'),
            ('Informações para preenchimento do chamado', 'textarea', 'Informe o número do equipamento, impresso na etiqueta.'),
            ('Permite anexos?', 'checkbox', 'marcar'),
            ('Deve solicitar local de atendimento?', 'checkbox', 'marcar'),
            ('Ativo?', 'checkbox', 'marcar'),
        ]
    )
    capturar(tela.pagina, '03-servico-formulario')
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')

    servico = Servico.objects.filter(nome=SERVICO).first()
    assert servico is not None, 'a UI disse que salvou, mas o serviço não existe'
    assert servico.centros_atendimento.count() == 2, 'o serviço deveria atender nos dois centros'
    assert servico.sla_manual == 12, 'o SLA manual informado não foi gravado'
