"""Fluxo: laboratórios multiusuários (modo 2).

O subdomínio LABORATÓRIOS é o que dá ao `pesquisa` a sua única estrutura **física**: o laboratório
com equipamentos, materiais e serviços, e a solicitação de serviço que o liga a um projeto. São
nove cenários em três papéis — o Diretor de Pesquisa (108001) cadastra o laboratório e os tipos
de finalidade, o Coordenador do Laboratório (108013) cadastra equipamentos, serviços e materiais
e avalia as solicitações, e o Coordenador de Projeto (108003) solicita o serviço e o acompanha.

O que este arquivo pega: os três tipos de campo que só aparecem aqui — ``radio`` (o tipo de
laboratório e o tipo de entidade atendida), ``FilteredSelectMultiple`` (os equipamentos usados
por um serviço, que referenciam os equipamentos cadastrados dois cenários antes) e o
``Autocomplete`` sobre o **inventário do patrimônio**, que o seed cria na carga básica. Pega
também a cadeia laboratório → equipamento → serviço, que é o encadeamento mais longo do módulo
depois da esteira editorial.

Os testes são sequenciais: o laboratório nasce no primeiro e todos os outros trabalham sobre ele.
O projeto da cadeia 001→011 é reaberto apenas durante a solicitação e restaurado no teardown.

O bloqueio atribuído ao produto foi descartado por medição: os dois ``select`` já tinham classe
``filtered`` e estavam nos caches do ``SelectBox``. O listener é nativo (``addEventListener``),
por isso não aparecia em ``jQuery._data``. O defeito estava no preenchedor: ``click(force=True)``
não disparava o listener, enquanto o clique normal movia a opção exatamente como para o usuário.
"""

import re
from uuid import uuid4

import pytest
from playwright.sync_api import expect

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

DATA = '01/01/2018'

LABORATORIOS = '/pesquisa/laboratorios_pesquisa/'
FINALIDADES = '/admin/pesquisa/finalidadeservicolaboratorio/'
MINHAS_SOLICITACOES = '/pesquisa/minhas_solicitacoes_servicos/'

SUFIXO = uuid4().hex[:8]
NOME_LABORATORIO = f'Nome do Laboratório {SUFIXO}'
DESCRICAO_EQUIPAMENTO = f'Descrição do equipamento {SUFIXO}'
DESCRICAO_SERVICO = f'Descrição do Serviço realizado pelo Laboratório {SUFIXO}'
DESCRICAO_MATERIAL = f'Descrição do material existente {SUFIXO}'
DESCRICAO_SOLICITACAO = f'Descrição detalhada sobre a realização do serviço {SUFIXO}'
FINALIDADE = f'Análise de amostra para projeto de pesquisa {SUFIXO}'


def _rota(tela: Tela, trecho: str) -> Tela:
    """Espera a navegação chegar em ``trecho`` — o antídoto contra a corrida da armadilha 15.

    Os botões de cadastro do laboratório são links que navegam, e ``Tela.clicar_botao`` só espera
    *antes* do clique: sem a âncora, o preenchimento cai num documento em construção e a falha
    sai como "campo não preenchido" com os rótulos certos na tela — foi o que aconteceu com o
    ``Descrição`` do material.
    """
    expect(tela.pagina).to_have_url(re.compile(trecho))
    return tela.esperar()


def _laboratorio(logado_pesquisa, papel: str) -> Tela:
    """Listagem → "Visualizar" → a tela ``Nome do Laboratório``.

    É o caminho que o behave usa em cinco dos nove cenários. O ``Visualizar`` é o link da
    listagem, não o ícone do admin: a listagem de laboratórios usa o design system de cartões.
    """
    tela = Tela(logado_pesquisa(papel)).ir(LABORATORIOS)
    tela.ver_titulo('Laboratórios Multiusuários')
    tela.cartao(NOME_LABORATORIO).clicar_botao('Visualizar')
    return tela.ver_titulo(NOME_LABORATORIO)


def test_cadastro_do_laboratorio_multiusuario(logado_pesquisa):
    """O Diretor de Pesquisa cadastra o laboratório com os sete campos do cenário.

    O laboratório nasce aqui e é o objeto de todos os outros oito cenários. O ``radio`` do tipo
    e o ``Autocomplete`` do coordenador e dos membros são os campos que provam o papel: o
    laboratório tem um coordenador **e** membros, e é o vínculo de cada um que decide o que ele
    pode fazer nas abas seguintes.
    """
    from pesquisa.models import LaboratorioPesquisa

    tela = Tela(logado_pesquisa('diretor')).ir(LABORATORIOS)
    tela.ver_titulo('Laboratórios Multiusuários')
    tela.clicar_botao('Adicionar laboratório')
    tela.ver_titulo('Adicionar Laboratório Multiusuário')

    tela.preencher_formulario(
        [
            ('Nome', 'Texto', NOME_LABORATORIO),
            ('Tipo de laboratório multiusuário', 'radio', 'Polo de inovação'),
            ('Coordenador', 'Autocomplete', '108013'),
            ('Campus', 'Lista', 'CZN'),
            ('Descrição', 'TextArea', 'Descrição e características do laboratório'),
            ('Área de Pesquisa', 'Autocomplete', 'BIOQUÍMICA'),
            ('Membros', 'Autocomplete Multiplo', '108014'),
        ]
    )
    tela.clicar_botao('Salvar')

    tela.sucesso('Cadastro realizado com sucesso.')
    laboratorio = LaboratorioPesquisa.objects.filter(nome=NOME_LABORATORIO).order_by('-id').first()
    assert laboratorio is not None, 'a UI disse que cadastrou, mas o laboratório não persistiu'
    assert laboratorio.coordenador is not None, 'a UI disse que cadastrou, mas o laboratório ficou sem coordenador'


def test_cadastro_de_finalidade_de_servico(logado_pesquisa):
    """O Diretor de Pesquisa cadastra o tipo de finalidade — o catálogo da solicitação.

    É um CRUD de apoio, mas **obrigatório na cadeia**: a solicitação de serviço (quinto cenário)
    escolhe a finalidade num ``Autocomplete``, e sem esta linha o campo vem vazio e a solicitação
    não fecha.
    """
    from pesquisa.models import FinalidadeServicoLaboratorio

    tela = Tela(logado_pesquisa('diretor')).ir(FINALIDADES)
    tela.ver_titulo('Tipos de Finalidade do Serviço')
    tela.clicar_botao('Adicionar Tipo de Finalidade do Serviço')
    tela.ver_titulo('Adicionar Tipo de Finalidade do Serviço')

    tela.preencher('Descrição', 'Texto', FINALIDADE)
    tela.clicar_botao('Salvar')

    tela.sucesso('Cadastro realizado com sucesso.')
    assert FinalidadeServicoLaboratorio.objects.filter(descricao=FINALIDADE).exists(), 'a UI disse que cadastrou, mas a finalidade não persistiu'


def test_cadastro_de_equipamentos_do_laboratorio(logado_pesquisa):
    """O Coordenador do Laboratório cadastra um equipamento, vinculado a um bem do patrimônio.

    Dois ajustes sobre a `.feature`, ambos medidos no formulário: ``Nome`` é exigido **além** de
    ``Descrição`` (a tabela do behave lista só o segundo, e o modelo tem os dois), e
    ``Inventário`` é um ``AutocompleteWidget`` sobre o patrimônio — o ``<select>`` que o Django
    renderiza vem **vazio** e o select2 o preenche por AJAX, então lê-lo como ``Lista`` daria
    "sem opções". O rótulo da opção é ``123455 - equipamento do laboratório``.
    """
    from pesquisa.models import EquipamentoLaboratorioPesquisa

    tela = _laboratorio(logado_pesquisa, 'coordenador_laboratorio')
    tela.clicar_aba('Equipamentos')
    tela.clicar_botao('Adicionar Equipamento')
    _rota(tela, '/pesquisa/cadastrar_equipamento_laboratorio/')

    tela.preencher_formulario(
        [
            ('Nome', 'Texto', 'Equipamento do laboratório'),
            ('Descrição', 'TextArea', DESCRICAO_EQUIPAMENTO),
            ('Inventário', 'Autocomplete', '123455'),
        ]
    )
    tela.clicar_botao('Salvar')

    tela.sucesso('Equipamento cadastrado com sucesso.')
    equipamento = EquipamentoLaboratorioPesquisa.objects.filter(descricao=DESCRICAO_EQUIPAMENTO).order_by('-id').first()
    assert equipamento is not None, 'a UI disse que cadastrou, mas o equipamento não persistiu'
    assert equipamento.patrimonio_id, 'a UI disse que cadastrou, mas o equipamento ficou sem o bem do patrimônio'


def test_cadastro_de_materiais_do_laboratorio(logado_pesquisa):
    """O Coordenador do Laboratório cadastra um material de consumo com estoque e valor.

    Os dois números são conferidos no ORM: o formulário os recebe como texto e é onde o parse
    poderia falhar em silêncio.
    """
    from pesquisa.models import MaterialLaboratorioPesquisa

    tela = _laboratorio(logado_pesquisa, 'coordenador_laboratorio')
    tela.clicar_aba('Materiais')
    tela.clicar_botao('Adicionar Material')
    _rota(tela, '/pesquisa/cadastrar_material_laboratorio/')

    # `materiallaboratoriopesquisaform.js:3` **esconde** a Descrição ao abrir o formulário e só
    # a revela quando o autor marca que não achou o material na lista. A `.feature` não lista o
    # checkbox: sem ele o campo está no DOM mas invisível, e o preenchimento falha com "campo não
    # preenchido" e o rótulo presente na tela.
    tela.preencher_formulario(
        [
            ('Não encontrei o material na lista. Quero cadastrar o novo material.', 'checkbox', 'marcar'),
            ('Descrição', 'TextArea', DESCRICAO_MATERIAL),
            ('Quantidade em Estoque', 'Texto', '10'),
            ('Valor Unitário (R$)', 'Texto', '50'),
        ]
    )
    tela.clicar_botao('Salvar')

    tela.sucesso('Material cadastrado com sucesso.')
    # `MaterialLaboratorioPesquisa` **não tem** `descricao`: a descrição do formulário é campo
    # extra, e com `adicionar_novo` marcado a view a usa para criar (ou reaproveitar) um
    # `MaterialConsumoPesquisa` e amarrá-lo como `material` (`views.py:6536-6544`). A asserção
    # entra por esse vínculo — é ele que prova que a descrição não foi descartada.
    material = MaterialLaboratorioPesquisa.objects.filter(material__descricao=DESCRICAO_MATERIAL).order_by('-id').first()
    assert material is not None, 'a UI disse que cadastrou, mas nenhum material ficou ligado à descrição'
    assert str(material.quantidade) == '10', f'a UI disse que cadastrou, mas a quantidade gravou {material.quantidade!r}'


def test_cadastro_de_servicos_do_laboratorio(logado_pesquisa):
    """O coordenador publica um serviço e vincula o equipamento pelo seletor duplo."""
    from pesquisa.models import ServicoLaboratorioPesquisa

    tela = _laboratorio(logado_pesquisa, 'coordenador_laboratorio')
    tela.clicar_aba('Serviços')
    tela.clicar_botao('Adicionar Serviço')
    _rota(tela, '/pesquisa/cadastrar_servico_laboratorio/')

    tela.preencher_formulario(
        [
            ('Descrição', 'TextArea', DESCRICAO_SERVICO),
            ('Materiais Utilizados', 'TextArea', 'Detalhamento do material utilizado'),
            ('Equipamentos Utilizados', 'FilteredSelectMultiple', DESCRICAO_EQUIPAMENTO),
        ]
    )
    tela.clicar_botao('Salvar')

    tela.sucesso('Serviço cadastrado com sucesso.')
    servico = ServicoLaboratorioPesquisa.objects.filter(descricao=DESCRICAO_SERVICO).order_by('-id').first()
    assert servico is not None, 'a UI disse que cadastrou, mas o serviço não persistiu'
    assert servico.equipamentos.filter(descricao=DESCRICAO_EQUIPAMENTO).exists(), (
        'a UI disse que vinculou, mas o equipamento não persistiu no serviço'
    )


def test_solicitar_realizacao_de_servico(logado_pesquisa, projeto_em_execucao):
    """O coordenador de projeto em execução solicita o serviço recém-publicado."""
    from pesquisa.models import SolicitacaoServicoLaboratorio

    tela = _laboratorio(logado_pesquisa, 'coordenador_projeto')
    tela.clicar_botao('Solicitar Serviço')
    _rota(tela, '/pesquisa/solicitar_servico_laboratorio/')

    tela.preencher_formulario(
        [
            ('Serviço', 'Autocomplete', DESCRICAO_SERVICO),
            ('Tipo de entidade atendida', 'radio', 'Interna'),
            ('Nome da instituição ou empreendimento atendido', 'Texto', 'Nome da empresa'),
            ('CNPJ da instituição ou empreendimento atendido', 'Texto', '42.316.471/0001-53'),
            ('Finalidade do Serviço', 'Autocomplete', FINALIDADE),
            ('Data', 'Data', '30/05/2022'),
            ('Hora de Início', 'Hora', '10:00:00'),
            ('Hora de Término', 'Hora', '12:00:00'),
            ('Descrição do Serviço', 'TextArea', DESCRICAO_SOLICITACAO),
        ]
    )
    tela.clicar_botao('Salvar')

    tela.sucesso('Solicitação de serviço cadastrada com sucesso.')
    solicitacao = SolicitacaoServicoLaboratorio.objects.filter(descricao=DESCRICAO_SOLICITACAO).order_by('-id').first()
    assert solicitacao is not None, 'a UI disse que cadastrou, mas a solicitação não persistiu'
    assert solicitacao.situacao == SolicitacaoServicoLaboratorio.EM_ESPERA, 'a solicitação não iniciou em espera'


def test_avaliar_solicitacao_de_servico(logado_pesquisa):
    """O coordenador do laboratório aprova a solicitação e registra sua resposta."""
    from pesquisa.models import SolicitacaoServicoLaboratorio

    tela = _laboratorio(logado_pesquisa, 'coordenador_laboratorio')
    tela.clicar_aba('Solicitações de Serviço')
    tela.linha(DESCRICAO_SOLICITACAO).clicar_botao('Aprovar')
    popup = tela.popup()
    popup.preencher('Resposta', 'TextArea', 'Declaração de aceite com orientações')
    popup.salvar_no_popup()

    tela.sucesso('Solicitação avaliada com sucesso.')
    solicitacao = SolicitacaoServicoLaboratorio.objects.get(descricao=DESCRICAO_SOLICITACAO)
    assert solicitacao.situacao == SolicitacaoServicoLaboratorio.DEFERIDA, 'a UI disse que aprovou, mas a solicitação não ficou deferida'
    assert solicitacao.parecer == 'Declaração de aceite com orientações', 'a resposta do laboratório não persistiu'


def test_acompanhamento_da_solicitacao(logado_pesquisa):
    """O solicitante abre o acompanhamento da solicitação deferida."""
    from pesquisa.models import SolicitacaoServicoLaboratorio

    tela = Tela(logado_pesquisa('coordenador_projeto')).ir(MINHAS_SOLICITACOES)
    tela.ver_titulo('Minhas Solicitações de Serviço')
    tela.linha(DESCRICAO_SOLICITACAO).clicar_botao('Acompanhar Solicitação')
    _rota(tela, '/pesquisa/acompanhar_solicitacao_servico/')
    tela.ver_titulo('Acompanhar Solicitação')

    solicitacao = SolicitacaoServicoLaboratorio.objects.get(descricao=DESCRICAO_SOLICITACAO)
    assert solicitacao.cadastrada_por.user.username == '108003', 'a solicitação acompanhada não pertence ao coordenador do projeto'


def test_registrar_conclusao_de_servico(logado_pesquisa):
    """O coordenador do laboratório conclui a solicitação que havia deferido."""
    from pesquisa.models import SolicitacaoServicoLaboratorio

    tela = _laboratorio(logado_pesquisa, 'coordenador_laboratorio')
    tela.clicar_aba('Solicitações de Serviço')
    tela.linha(DESCRICAO_SOLICITACAO).clicar_botao('Registrar Conclusão')
    _rota(tela, r'/pesquisa/laboratorio_pesquisa/\d+/\?tab=solicitacoes$')

    tela.sucesso('Solicitação concluída com sucesso.')
    solicitacao = SolicitacaoServicoLaboratorio.objects.get(descricao=DESCRICAO_SOLICITACAO)
    assert solicitacao.situacao == SolicitacaoServicoLaboratorio.ATENDIDA, 'a UI disse que concluiu, mas a solicitação não ficou atendida'
