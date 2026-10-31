"""Fluxo: os cadastros do módulo (modo 2) — a cadeia área → gestor → catálogo → serviço, que é
pré-requisito de todo chamado.

Por que importa: sem área publicada, gestor vinculado e serviço ativo no catálogo, nenhum dos
fluxos do usuário final existe. A regressão que este arquivo pega é a silenciosa: tela de admin que
salva sem persistir, vínculo que não grava, serviço que nasce inativo e some da abertura de
chamado.

Granularidade (receita, seção 1): o behave descrevia uma cadeia — cada cenário herdava a área, o
grupo e o serviço do anterior. No pytest cada teste é independente, então cada etapa **sob teste**
virou um teste que exercita a tela, e as etapas que ele apenas **consome** nascem por ORM (as
fixtures do conftest). Criar a área e vinculá-la ao gestor continuam num teste só: o segundo não
faz sentido sem a área que o primeiro cria.

As asserções de "Nenhum X encontrado" do behave foram descartadas: a suíte compartilha o banco e
não dá flush (armadilha 8), então a listagem do admin nunca está vazia e a asserção daria falso
vermelho conforme o que as outras suítes deixaram.
"""

from __future__ import annotations

import pytest

from djtools.e2e_ui import Tela

from .conftest import PAPEIS, criar_contexto, nome_e2e, usuario, ver_campos

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

AREA_ADMIN = '/admin/comum/areaatuacao/'
GESTOR_ADMIN = '/admin/centralservicos/gestorareaservico/'
CATEGORIA_ADMIN = '/admin/centralservicos/categoriaservico/'
GRUPO_SERVICO_ADMIN = '/admin/centralservicos/gruposervico/'
CENTRO_ADMIN = '/admin/centralservicos/centroatendimento/'
GRUPO_ADMIN = '/admin/centralservicos/grupoatendimento/'
SERVICO_ADMIN = '/admin/centralservicos/servico/'


def test_admin_cria_area_de_atuacao_e_vincula_gestor(logado_central):
    """O admin cria a área (com o erro de campo obrigatório no caminho) e nomeia o gestor.

    O passo de obrigatoriedade é mantido porque é a única asserção que não depende do
    estado do banco — é ele que prova que a validação do formulário está de pé.
    """
    from centralservicos.models import GestorAreaServico
    from comum.models import AreaAtuacao

    nome = nome_e2e('Área')

    tela = Tela(logado_central('admin')).ir(AREA_ADMIN)
    tela.ver_titulo('Áreas de Atuação')
    tela.clicar_botao('Adicionar Área de Atuação')
    tela.ver_titulo('Adicionar Área de Atuação')
    ver_campos(tela, ['Nome', 'Ícone', 'Ativo?'])
    tela.ver_botao('Salvar')

    tela.clicar_botao('Salvar')
    tela.erro('Por favor, corrija o erro abaixo')
    tela.erro('Este campo é obrigatório')

    tela.preencher_formulario([('Nome', 'texto', nome), ('Ícone', 'texto', 'list'), ('Ativo?', 'checkbox', 'Marcar')])
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')
    assert AreaAtuacao.objects.filter(nome=nome, ativo=True).exists(), 'a UI disse que salvou, mas a área não persistiu'

    tela.ir(GESTOR_ADMIN)
    tela.ver_titulo('Gestores das Áreas dos Serviços')
    tela.clicar_botao('Adicionar Gestor da Área do Serviço')
    tela.ver_titulo('Adicionar Gestor da Área do Serviço')
    tela.preencher_formulario([('Gestor', 'autocomplete', PAPEIS['gestor']), ('Área do Serviço', 'autocomplete', nome)])
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')
    assert GestorAreaServico.objects.filter(gestor__username=PAPEIS['gestor'], area__nome=nome).exists(), (
        'a UI disse que vinculou, mas o GestorAreaServico não persistiu'
    )


def test_gestor_cadastra_categoria_de_servico(logado_central):
    """A categoria é o primeiro nível do catálogo e é o que liga o grupo de serviço a uma área."""
    from centralservicos.models import CategoriaServico

    contexto = criar_contexto(com_grupo_de_atendimento=False, com_servico=False)
    nome = nome_e2e('Categoria')

    tela = Tela(logado_central('gestor')).ir(CATEGORIA_ADMIN)
    tela.ver_titulo('Categorias de Serviço')
    tela.clicar_botao('Adicionar Categoria de Serviço')
    tela.ver_titulo('Adicionar Categoria de Serviço')
    ver_campos(tela, ['Nome', 'Área do Serviço'])
    tela.preencher_formulario([('Nome', 'texto', nome), ('Área do Serviço', 'autocomplete', contexto.area.nome)])
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')
    assert CategoriaServico.objects.filter(nome=nome, area=contexto.area).exists(), 'a UI disse que salvou, mas a categoria não persistiu'


def test_gestor_cadastra_grupo_de_servico(logado_central):
    """O grupo de serviço agrupa os serviços na vitrine; sem categoria ele não aparece para ninguém."""
    from centralservicos.models import GrupoServico

    contexto = criar_contexto(com_grupo_de_atendimento=False, com_servico=False)
    nome = nome_e2e('Grupo de Serviço')

    tela = Tela(logado_central('gestor')).ir(GRUPO_SERVICO_ADMIN)
    tela.ver_titulo('Grupos de Serviço')
    tela.clicar_botao('Adicionar Grupo de Serviço')
    tela.ver_titulo('Adicionar Grupo de Serviço')
    ver_campos(tela, ['Nome', 'Detalhamento', 'Categorias', 'Ícone'])
    tela.preencher_formulario(
        [
            ('Nome', 'texto', nome),
            ('Detalhamento', 'textarea', 'Serviço de impressão e digitalização de documentos.'),
            ('Categorias', 'autocomplete multiplo', contexto.categoria.nome),
            ('Ícone', 'texto', 'list'),
        ]
    )
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')
    grupo = GrupoServico.objects.filter(nome=nome).first()
    assert grupo is not None, 'a UI disse que salvou, mas o grupo de serviço não persistiu'
    assert grupo.categorias.filter(pk=contexto.categoria.pk).exists(), 'a categoria informada não foi vinculada ao grupo'


def test_gestor_cadastra_centro_de_atendimento(logado_central):
    """O centro é o que o solicitante escolhe na abertura e o que decide o grupo de primeiro nível."""
    from centralservicos.models import CentroAtendimento

    contexto = criar_contexto(com_grupo_de_atendimento=False, com_servico=False)
    nome = nome_e2e('Centro Local')

    tela = Tela(logado_central('gestor')).ir(CENTRO_ADMIN)
    tela.ver_titulo('Centros de Atendimento')
    tela.clicar_botao('Adicionar Centro de Atendimento')
    tela.ver_titulo('Adicionar Centro de Atendimento')
    ver_campos(tela, ['Nome', 'Centro de Atendimento Local?', 'Área do Serviço', 'Ativo?'])
    tela.preencher_formulario(
        [
            ('Nome', 'texto', nome),
            ('Centro de Atendimento Local?', 'checkbox', 'Marcar'),
            ('Área do Serviço', 'autocomplete', contexto.area.nome),
            # A feature não lista o Ativo? na tabela dela, mas o formulário do admin o tem
            # desmarcado por padrão: sem marcar, o centro nasce inativo e não roteia chamado.
            ('Ativo?', 'checkbox', 'Marcar'),
        ]
    )
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')
    assert CentroAtendimento.objects.filter(nome=nome, area=contexto.area, eh_local=True, ativo=True).exists(), (
        'a UI disse que salvou, mas o centro não persistiu como local e ativo'
    )


def test_gestor_cadastra_grupo_de_atendimento(logado_central):
    """O grupo de atendimento é quem recebe o chamado; ele exige centro, campus e ao menos um atendente.

    É o grupo **raiz** da área (sem grupo superior) porque é o que ``get_grupo_primeiro_nivel``
    procura ao rotear a abertura — e é essa a razão de o teste não poder rodar sobre uma área que
    já tenha um raiz. Daí o contexto sem grupo.
    """
    from centralservicos.models import GrupoAtendimento

    contexto = criar_contexto(com_grupo_de_atendimento=False, com_servico=False)
    nome = nome_e2e('Grupo de Atendimento')

    tela = Tela(logado_central('gestor')).ir(GRUPO_ADMIN)
    tela.ver_titulo('Grupos de Atendimento')
    tela.clicar_botao('Adicionar Grupo de Atendimento')
    tela.ver_titulo('Adicionar Grupo de Atendimento')
    ver_campos(tela, ['Campus', 'Centro de Atendimento', 'Nome', 'Responsáveis', 'Atendentes Vinculados ao Grupo'])
    tela.preencher_formulario(
        [
            ('Campus', 'autocomplete', 'CZN'),
            ('Centro de Atendimento', 'autocomplete', contexto.centro.nome),
            ('Nome', 'texto', nome),
            ('Responsáveis', 'autocomplete multiplo', PAPEIS['responsavel']),
            ('Atendentes Vinculados ao Grupo', 'autocomplete multiplo', PAPEIS['atendente']),
            ('Ativo?', 'checkbox', 'Marcar'),
        ]
    )
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')

    grupo = GrupoAtendimento.objects.filter(nome=nome).first()
    assert grupo is not None, 'a UI disse que salvou, mas o grupo de atendimento não persistiu'
    assert grupo.campus.sigla == 'CZN', 'o campus informado não foi gravado'
    assert grupo.atendentes.filter(username=PAPEIS['atendente']).exists(), 'o atendente informado não foi vinculado'
    assert grupo.responsaveis.filter(username=PAPEIS['responsavel']).exists(), 'o responsável informado não foi vinculado'


@pytest.mark.parametrize('matricula', [PAPEIS['gestor'], PAPEIS['supervisor']])
def test_gestor_adiciona_atendente_ao_grupo(logado_central, contexto, matricula):
    """Os dois exemplos do antigo esquema do behave (104002 e 104004), num ``parametrize``.

    O que se verifica é exatamente o par (grupo, matrícula): a edição do grupo acrescenta o
    atendente sem perder os que já estavam lá. O passo "clico no link Editar" do behave é
    substituído pela URL de edição direta: a listagem do admin é paginada e o banco compartilhado
    tem grupos de outras suítes, então achar a linha do teste por texto seria dependente de página.
    """
    from centralservicos.models import GrupoAtendimento

    grupo = contexto.grupo_atendimento
    assert not grupo.atendentes.filter(username=matricula).exists(), 'pré-condição: o atendente ainda não está no grupo'

    tela = Tela(logado_central('gestor')).ir(f'{GRUPO_ADMIN}{grupo.pk}/change/')
    tela.ver_titulo(f'Editar {grupo.nome}')
    tela.preencher('Atendentes Vinculados ao Grupo', 'autocomplete multiplo', matricula)
    tela.clicar_botao('Salvar')
    tela.sucesso('Atualização realizada com sucesso.')

    atualizado = GrupoAtendimento.objects.get(pk=grupo.pk)
    assert atualizado.atendentes.filter(username=matricula).exists(), 'a UI disse que salvar, mas o atendente não entrou no grupo'
    assert atualizado.atendentes.filter(username=PAPEIS['atendente']).exists(), 'a edição removeu os atendentes que já estavam no grupo'
    # Efeito colateral de domínio que o cenário não menciona: entrar como atendente/responsável de um
    # grupo concede o grupo Django ``Atendente da Central de Serviços`` (signal
    # ``_sincronizar_grupo_atendente``, ``models.py:736``). É o que dá as permissões de atendimento a
    # quem é vinculado pela tela — e é por isso que o gestor deixa de ser "só gestor" depois do
    # esquema.
    assert usuario(matricula).groups.filter(name='Atendente da Central de Serviços').exists(), (
        'vincular o servidor ao grupo de atendimento deveria conceder o grupo Django de atendente'
    )


def test_gestor_cadastra_servico(logado_central):
    """O serviço amarra grupo de serviço, área, centros e SLA — é a porta do chamado.

    Dois campos entram além da tabela do behave, e o motivo é o próprio formulário do admin:
    ``SLA utilizado`` (sem ele o manual é ignorado no cálculo) e ``Ativo?`` (sem ele o serviço nasce
    inativo e o fluxo seguinte não o enxerga).
    """
    from centralservicos.models import Servico

    contexto = criar_contexto(com_grupo_de_atendimento=False, com_servico=False)
    nome = nome_e2e('Serviço')

    tela = Tela(logado_central('gestor')).ir(SERVICO_ADMIN)
    tela.ver_titulo('Serviços')
    tela.clicar_botao('Adicionar Serviço')
    tela.ver_titulo('Adicionar Serviço')
    ver_campos(
        tela,
        [
            'Nome',
            'Tipo',
            'Área do Serviço',
            'Centros de Atendimento',
            'Grupo de Serviço',
            'Informações para preenchimento do chamado',
            'SLA manual (em horas)',
        ],
    )
    tela.preencher_formulario(
        [
            ('Nome', 'texto', nome),
            ('Tipo', 'lista', 'Incidente'),
            ('Área do Serviço', 'lista', contexto.area.nome),
            ('Centros de Atendimento', 'autocomplete multiplo', contexto.centro.nome),
            ('Grupo de Serviço', 'autocomplete', contexto.grupo_servico.nome),
            ('Informações para preenchimento do chamado', 'textarea', 'Por favor, informar o número do equipamento impresso na etiqueta.'),
            ('SLA utilizado', 'lista', 'Usar o SLA manual'),
            ('SLA manual (em horas)', 'texto', '12'),
            ('Ativo?', 'checkbox', 'Marcar'),
        ]
    )
    tela.clicar_botao('Salvar')
    tela.sucesso('Cadastro realizado com sucesso.')

    servico = Servico.objects.filter(nome=nome).first()
    assert servico is not None, 'a UI disse que salvou, mas o serviço não persistiu'
    assert servico.ativo, 'o serviço nasceu inativo'
    assert servico.centros_atendimento.filter(pk=contexto.centro.pk).exists(), 'o centro informado não foi vinculado ao serviço'
    assert servico.sla_manual == 12, 'o SLA manual informado não foi gravado'
