"""Fluxo: a esteira editorial da publicação da obra (modo 2).

É a feature mais longa do `pesquisa` depois da 002, e a única do módulo que é uma **esteira de
papéis**: a obra submetida na 013 atravessa verificação de plágio → análise preliminar →
conselho editorial → parecerista → termos autorais → revisão → correções → parecer da revisão →
diagramação → ISBN → ficha catalográfica → publicação → liberação → aprovação → conclusão.
Cada etapa é de um grupo diferente, sobre a mesma obra.

Duas decisões de desenho, ambas medidas:

**Cada cenário é um teste, e a ordem é a do arquivo.** São cenários sobre telas diferentes, e
unificá-los custaria o diagnóstico — uma falha na diagramação não diria nada sobre o plágio. A
ordem é garantida dentro do arquivo (a coleta preserva a ordem de definição), e é o mesmo
acoplamento que as `.feature` têm entre si.

**A data é por teste, não por arquivo.** A esteira dura janeiro e fevereiro de 2018 e o edital
da 012 tem uma janela por etapa (o plágio só acontece em 13/01, a análise preliminar em 27/01).
Por isso cada teste chama ``em_data(...)``; um arquivo por cenário perderia a ordem, que é o
que sustenta a esteira.

**Toda navegação é ancorada na rota de destino.** Os botões das etapas são links que navegam, e
``Tela.clicar_botao`` só espera *antes* do clique: o documento seguinte ainda pode estar em
``load`` quando a consulta seguinte roda. É a armadilha 15 da receita; o antídoto é o
``_rota(...)``.

A alternância histórica em ``test_emissao_do_parecer`` não reapareceu nas reproduções com a
suíte completa, banco novo e banco reusado. A sonda anterior mostrou editor TinyMCE inicializado,
valor idêntico no editor, no ``textarea`` e no ``FormData``, e a obra persistida; portanto não há
neste arquivo nem no preenchedor uma correção especulativa para ela.
**A esteira cobre os 23 cenários ativos.** Os dois que faltavam não exigiam capacidade nova
na ``Tela``: ``AvaliacaoDiagramacaoForm`` usa os rótulos exatos ``Aprovar capa`` e
``Aprovar miolo``; para o autor, ``PublicacaoObraForm`` deixa somente a data de liberação e o
mesmo botão ``Salvar`` do formulário registra o valor.

Três achados anteriores continuam sendo premissas da cadeia:

- o TinyMCE reescreve o ``textarea`` a partir do próprio modelo no submit; por isso o
  preenchedor existente passa por ``editor.setContent()`` e verifica também o ``textarea``;
- as abas de ``obra.html`` têm ``data-checked`` condicionado ao estado da obra — a aba
  "Publicação", por exemplo, só habilita quando existe ``obra.ficha_catalografica``
  (``obra.html:910``). Etapa que não grava o arquivo esperado faz a aba seguinte desaparecer;
- os formulários exigem campos omitidos pela feature: ``Avaliação``, ``Parecer``, os dois
  termos autorais, ``Obra Revisada``, ``Parecer do Revisor``, as duas diagramações, um ISBN,
  os campos de distribuição da publicação e ``Obra Concluída``.
"""

import re

import pytest
from playwright.sync_api import expect

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# Piso do arquivo: a primeira data da esteira. Cada teste avança o relógio pela sua.
DATA = '13/01/2018'

SUBMISSOES = '/admin/pesquisa/obra/'
MINHAS_SUBMISSOES = '/pesquisa/minhas_obras/'
AREAS_DE_INTERESSE = '/pesquisa/indicar_areas_conhecimento_de_interesse/'

TITULO_OBRA = 'título da obra'


def _obra():
    """A obra submetida pela feature 013 — o objeto que a esteira inteira atravessa."""
    from pesquisa.models import Obra

    obra = Obra.objects.filter(titulo=TITULO_OBRA).order_by('-id').first()
    assert obra is not None, (
        f'obra {TITULO_OBRA!r} ausente: a cadeia é sequencial, rode `pytest pesquisa/tests/e2e` inteiro (quem submete é test_13_submissao_obra.py)'
    )
    return obra


def _rota(tela: Tela, trecho: str) -> Tela:
    """Espera a navegação chegar em ``trecho`` — o antídoto contra a corrida da armadilha 15.

    ``expect(...).to_have_url`` é a única âncora sem ambiguidade: um ``expect`` sobre um heading
    passa falso, porque ``get_by_role`` casa por substring e a tela de origem contém o texto; e
    ``Tela.esperar`` resolve na hora enquanto o documento antigo está em ``load``.
    """
    expect(tela.pagina).to_have_url(re.compile(trecho))
    return tela.esperar()


def _publicacao(tela: Tela) -> Tela:
    """Submissões → linha da obra → ícone de exibição → a tela ``Publicação: título da obra``.

    É o caminho que os 22 cenários da feature repetem, e o ícone é metade do que eles afirmam:
    a etapa tem de ser editada na obra certa.
    """
    tela.ir(SUBMISSOES)
    tela.ver_titulo('Submissões')
    tela.linha(TITULO_OBRA)
    tela.linha(TITULO_OBRA).clicar_icone('exibição')
    return tela.ver_titulo(f'Publicação: {TITULO_OBRA}')


def _minhas_submissoes(pagina) -> Tela:
    """O acesso do autor à própria obra: ``Minhas Submissões`` → Visualizar."""
    tela = Tela(pagina).ir(MINHAS_SUBMISSOES)
    tela.ver_titulo('Minhas Submissões')
    tela.clicar_botao('Visualizar')
    return tela.ver_titulo(f'Publicação: {TITULO_OBRA}')


def test_verificacao_antiplagio(logado_pesquisa, em_data):
    """O Integrante da Editora registra o resultado da verificação de autenticidade."""
    em_data('13/01/2018')
    tela = _publicacao(Tela(logado_pesquisa('integrante_editora')))

    tela.clicar_aba('Verificação antiplágio')
    tela.preencher('Autêntica', 'Lista', 'Sim')
    tela.clicar_botao('Salvar')

    tela.sucesso('Verificação de autenticidade realizada com sucesso.')
    obra = _obra()
    obra.refresh_from_db()
    assert obra.autenticidade_verificada_em is not None, 'a UI disse que verificou, mas a obra ficou sem data de verificação'
    assert obra.autentica == 'Sim', f'a UI disse que é autêntica, mas gravou {obra.autentica!r}'


def test_analise_preliminar(logado_pesquisa, em_data):
    """O Integrante da Editora habilita a obra para seguir na esteira.

    O campo ``Situação da Obra`` é ``Obra.status_obra``, e é ele que a etapa seguinte (a
    indicação de conselheiro) pressupõe habilitado.
    """
    em_data('27/01/2018')
    tela = _publicacao(Tela(logado_pesquisa('integrante_editora')))

    tela.clicar_aba('Análise preliminar')
    tela.preencher('Situação da Obra', 'Lista', 'Habilitada')
    tela.clicar_botao('Salvar')

    tela.sucesso('Avaliação da editora realizada com sucesso.')
    obra = _obra()
    obra.refresh_from_db()
    assert obra.status_obra == 'Habilitada', f'a UI disse que avaliou, mas a situação da obra ficou {obra.status_obra!r}'


def test_indicacao_do_conselheiro(logado_pesquisa, em_data):
    """O Integrante da Editora indica o conselheiro que julga a obra."""
    em_data('27/01/2018')
    tela = _publicacao(Tela(logado_pesquisa('integrante_editora')))

    tela.clicar_aba('Conselho editorial')
    tela.clicar_botao('Indicar Conselheiro')
    _rota(tela, '/pesquisa/indicar_conselheiro_obra/')
    tela.preencher('Usuário', 'Autocomplete Multiplo', 'Conselheiro Editora')
    tela.clicar_botao('Enviar')

    tela.sucesso('Conselheiro indicado com sucesso.')
    obra = _obra()
    obra.refresh_from_db()
    assert obra.conselheiro_indicado_em is not None, 'a UI disse que indicou, mas a obra ficou sem data de indicação de conselheiro'


def test_indicacao_do_parecerista(logado_pesquisa, em_data):
    """O Conselheiro Editorial indica quem emite o parecer técnico da obra."""
    em_data('27/01/2018')
    tela = _publicacao(Tela(logado_pesquisa('conselheiro')))

    tela.clicar_aba('Análise de parecerista')
    tela.clicar_botao('Indicar Parecerista')
    _rota(tela, '/pesquisa/indicar_parecerista_obra/')
    tela.preencher('Usuário', 'Autocomplete Multiplo', 'Parecerista Obra')
    tela.clicar_botao('Enviar')

    tela.sucesso('Parecerista indicado com sucesso.')
    from pesquisa.models import ParecerObra

    assert ParecerObra.objects.filter(obra=_obra()).exists(), 'a UI disse que indicou, mas não há registro de parecer para a obra'


def test_cadastro_da_area_de_conhecimento_do_parecerista(logado_pesquisa, em_data):
    """O parecerista declara as áreas em que aceita avaliar, pelo ``checkbox popup``.

    É um dos dois únicos pontos do repo que usam o ``checkbox popup`` — o tipo que o
    levantamento de vocabulário listava como lacuna e que este MR passou a cobrir. O widget é
    um campo somente-leitura que abre um fancybox **ajax** (sem iframe) e grava por JS no input
    escondido ao "Confirmar": o gate de verdade é a espera pelo valor no input escondido, e não
    o fechamento da caixa — sem ela o formulário salva vazio e a mensagem de sucesso fica verde,
    porque o campo é ``required=False``.
    """
    em_data('27/01/2018')
    tela = Tela(logado_pesquisa('parecerista_obra')).ir(AREAS_DE_INTERESSE)
    tela.ver_titulo('Cadastrar Áreas de Conhecimento do seu Interesse')

    tela.preencher('Áreas de Conhecimento', 'checkbox popup', 'MATEMÁTICA (CIÊNCIAS EXATAS E DA TERRA)')
    tela.clicar_botao('Salvar')

    tela.sucesso('Áreas de conhecimento cadastradas com sucesso.')
    from pesquisa.models import AreaConhecimentoParecerista

    assert AreaConhecimentoParecerista.objects.filter(areas_de_conhecimento__descricao__icontains='MATEMÁTICA').exists(), (
        'a UI disse que cadastrou, mas nenhuma área de conhecimento foi gravada'
    )


def test_avaliacao_da_obra(logado_pesquisa, em_data):
    """O parecerista aceita a indicação e registra o parecer com nota, texto e arquivo.

    ``Avaliação`` não está na tabela da `.feature` e é obrigatório: o default do modelo
    (``ParecerObra.EM_ANALISE``) não é uma das opções do select, então o navegador manda a opção
    vazia e o servidor recusa. No behave não aparecia porque o formulário herdava a seleção do
    cenário anterior.

    A mensagem real é ``Parecer salvo com sucesso.`` — a da `.feature` é do **aceite**, que é um
    clique anterior e separado (``views.py:5246``).
    """
    em_data('27/01/2018')
    tela = _publicacao(Tela(logado_pesquisa('parecerista_obra')))

    tela.clicar_aba('Análise de parecerista')
    tela.clicar_botao('Aceitar Indicação')
    _rota(tela, '/pesquisa/obra/')
    tela.clicar_aba('Análise de parecerista')
    tela.clicar_botao('Avaliar Obra')
    _rota(tela, '/pesquisa/parecerista_avaliar_obra/')

    tela.preencher('Avaliação', 'Lista', 'Aprovada')
    tela.preencher('Nota', 'Lista', '10.0')
    tela.preencher(
        'Visando melhorar a qualidade literária do texto, há necessidade de acrescentar ou retirar alguma parte do texto ou promover-lhe alterações ou adequações? Explique',
        'Texto rico',
        'observações',
    )
    tela.preencher('Parecer', 'Arquivo', 'parecer.png')
    tela.clicar_botao('Salvar')

    tela.sucesso('Parecer salvo com sucesso.')
    from pesquisa.models import ParecerObra

    parecer = ParecerObra.objects.filter(obra=_obra()).order_by('-id').first()
    assert parecer is not None, 'a UI disse que avaliou, mas não há parecer registrado para a obra'
    assert parecer.parecer_realizado_em is not None, 'a UI disse que avaliou, mas o parecer ficou sem data de realização'


def test_emissao_do_parecer(logado_pesquisa, em_data):
    """O Conselheiro Editorial emite o parecer do conselho sobre a obra.

    `AvaliacaoConselhoEditorialForm` exige ``situacao_conselho_editorial``, que ele **renomeia**
    para 'Parecer' (``forms.py:2675-2678``) — e a `.feature` só lista 'Observações'.
    """
    em_data('27/01/2018')
    tela = _publicacao(Tela(logado_pesquisa('conselheiro')))

    tela.clicar_aba('Conselho editorial')
    tela.clicar_botao('Emitir Parecer')
    _rota(tela, '/pesquisa/registrar_posicao_conselho_obra/')
    tela.preencher('Parecer', 'Lista', 'Favorável')
    tela.preencher('Observações', 'Texto rico', 'observações do conselheiro')
    tela.clicar_botao('Salvar')

    tela.sucesso('Parecer registrado com sucesso.')
    obra = _obra()
    obra.refresh_from_db()
    assert obra.julgamento_conselho_realizado_em is not None, 'a UI disse que registrou, mas a obra ficou sem data de julgamento do conselho'


def test_cadastro_dos_termos_de_autorizacao(logado_pesquisa, em_data):
    """O autor anexa os termos autorais na sua própria obra.

    `UploadTermosForm` exige os **dois** primeiros termos (``forms.py:2704-2734``); a `.feature`
    lista só a cessão de direitos. É também o formulário que revelou que ``_preencher_arquivo``
    precisa cobrir o input como irmão direto do rótulo (o ``{% render_form %}`` do djtools).
    """
    em_data('30/01/2018')
    tela = _minhas_submissoes(logado_pesquisa('autor_obra'))

    tela.clicar_aba('Termos de autorização')
    tela.preencher_formulario(
        [
            ('Termos de Autorização de Publicação', 'Arquivo', 'termo_publicacao.png'),
            ('Termo de cessão de Direitos Autorais', 'Arquivo', 'termo_cessao.png'),
        ]
    )
    tela.clicar_botao('Salvar')

    tela.sucesso('Envio dos termos realizado com sucesso.')
    obra = _obra()
    obra.refresh_from_db()
    assert obra.termo_cessao_direitos_autorais, 'a UI disse que enviou, mas o termo de cessão não foi anexado'
    assert obra.termo_autorizacao_publicacao, 'a UI disse que enviou, mas o termo de publicação não foi anexado'


def test_validacao_dos_termos_de_autorizacao(logado_pesquisa, em_data):
    """O Integrante da Editora valida os termos autorais da obra."""
    em_data('30/01/2018')
    tela = _publicacao(Tela(logado_pesquisa('integrante_editora')))

    tela.clicar_aba('Termos de autorização')
    tela.clicar_botao('Validar Termos de Autorização')
    _rota(tela, '/pesquisa/validar_termos/')
    tela.preencher_formulario(
        [
            ('Termo de cessão de Direitos Autorais', 'Lista', 'Sim'),
            ('Termo de Uso de Imagem, Voz e Texto', 'Lista', 'Sim'),
            ('Termo de Autorização para uso de Nome de Menor', 'Lista', 'Sim'),
            ('Contrato de Cessão e Transferência de Direitos Patrimoniais de Autor', 'Lista', 'Sim'),
            ('Termo de Autorização para uso de Imagem e Fotografia', 'Lista', 'Sim'),
        ]
    )
    tela.clicar_botao('Salvar')

    tela.sucesso('Termos validados com sucesso.')
    obra = _obra()
    obra.refresh_from_db()
    assert obra.termos_assinados_realizado_em is not None, 'a UI disse que validou, mas a obra ficou sem data de registro dos termos'
    assert obra.termo_cessao_direitos_autorais_assinado == 'Sim', (
        f'a UI disse que validou, mas o termo de cessão ficou {obra.termo_cessao_direitos_autorais_assinado!r}'
    )


def test_indicacao_do_revisor(logado_pesquisa, em_data):
    """O Integrante da Editora indica o revisor linguístico da obra."""
    em_data('03/02/2018')
    tela = _publicacao(Tela(logado_pesquisa('integrante_editora')))

    tela.clicar_aba('Preparação, edição e revisão')
    tela.clicar_botao('Indicar Revisor')
    _rota(tela, '/pesquisa/indicar_revisor_obra/')
    tela.preencher('Usuário', 'Autocomplete Multiplo', 'Revisor Editora')
    tela.clicar_botao('Enviar')

    tela.sucesso('Revisor indicado com sucesso.')
    obra = _obra()
    obra.refresh_from_db()
    assert obra.revisor_indicado_em is not None, 'a UI disse que indicou, mas a obra ficou sem data de indicação de revisor'


def test_revisao_da_obra(logado_pesquisa, em_data):
    """O revisor envia a obra revisada e as suas observações.

    `RevisarObraForm` exige ``arquivo_obra_revisada``, que a `.feature` não lista — o campo é
    obrigatório porque sem o arquivo revisado não há o que o autor corrigir depois.
    """
    em_data('03/02/2018')
    tela = _publicacao(Tela(logado_pesquisa('revisor')))

    tela.clicar_aba('Preparação, edição e revisão')
    tela.clicar_botao('Revisar Obra')
    _rota(tela, '/pesquisa/revisar_obra/')
    tela.preencher_formulario(
        [
            ('Obra Revisada', 'Arquivo', 'obra_revisada.docx'),
            ('Link da Obra Revisada', 'Texto', 'link_da_obra'),
            ('Observações do Revisor', 'TextArea', 'observacoes do revisor'),
        ]
    )
    tela.clicar_botao('Salvar')

    tela.sucesso('Revisão salva com sucesso.')
    obra = _obra()
    obra.refresh_from_db()
    assert obra.link_obra_revisada == 'link_da_obra', f'a UI disse que salvou, mas o link gravou {obra.link_obra_revisada!r}'
    assert obra.revisao_realizada_em is not None, 'a UI disse que salvou, mas a obra ficou sem data de revisão'


def test_envio_das_correcoes_apos_a_revisao(logado_pesquisa, em_data):
    """O autor envia a obra corrigida depois da revisão, declarando ciência."""
    em_data('03/02/2018')
    tela = _minhas_submissoes(logado_pesquisa('autor_obra'))

    tela.clicar_aba('Preparação, edição e revisão')
    tela.clicar_botao('Enviar Correção')
    _rota(tela, '/pesquisa/enviar_arquivo_corrigido/')
    # `RevisarAutorForm` exige `revisada_pelo_autor` (a obra corrigida) além do termo de ciência;
    # a `.feature` só preenche o termo.
    tela.preencher_formulario(
        [
            ('Obra Revisada pelo Autor', 'Arquivo', 'obra_corrigida.docx'),
            ('Estou CIENTE de que', 'checkbox', 'marcar'),
        ]
    )
    tela.clicar_botao('Salvar')

    tela.sucesso('Correções enviadas com sucesso.')
    obra = _obra()
    obra.refresh_from_db()
    assert obra.correcoes_enviadas_em is not None, 'a UI disse que enviou, mas a obra ficou sem data de correções enviadas'


def test_emissao_do_parecer_sobre_a_revisao_do_autor(logado_pesquisa, em_data):
    """O revisor emite o parecer final sobre a revisão do autor, com a versão final anexada.

    `EmitirParecerRevisaoObraForm` exige ``parecer_revisor`` **e** ``versao_final_revisao``; a
    `.feature` só lista a versão final.
    """
    em_data('03/02/2018')
    tela = _publicacao(Tela(logado_pesquisa('revisor')))

    tela.clicar_aba('Preparação, edição e revisão')
    tela.clicar_botao('Emitir Parecer')
    _rota(tela, '/pesquisa/revisor_emitir_parecer/')
    tela.preencher('Parecer do Revisor', 'TextArea', 'parecer do revisor')
    tela.preencher('Versão Final da Revisão', 'Arquivo', 'versao_final_da_revisao.png')
    tela.clicar_botao('Salvar')

    tela.sucesso('Parecer salvo com sucesso.')
    obra = _obra()
    obra.refresh_from_db()
    assert obra.versao_final_revisao, 'a UI disse que salvou, mas a versão final da revisão não foi anexada'


def test_indicacao_do_diagramador(logado_pesquisa, em_data):
    """O Integrante da Editora indica o diagramador da obra."""
    em_data('06/02/2018')
    tela = _publicacao(Tela(logado_pesquisa('integrante_editora')))

    tela.clicar_aba('Projeto gráfico e diagramação')
    tela.clicar_botao('Indicar Diagramador')
    _rota(tela, '/pesquisa/indicar_diagramador_obra/')
    tela.preencher('Usuário', 'Autocomplete Multiplo', 'Diagramador Editora')
    tela.clicar_botao('Enviar')

    tela.sucesso('Diagramador indicado com sucesso.')
    obra = _obra()
    obra.refresh_from_db()
    assert obra.diagramador_indicado_em is not None, 'a UI disse que indicou, mas a obra ficou sem data de indicação de diagramador'


def test_diagramacao_da_obra(logado_pesquisa, em_data):
    """O diagramador anexa a diagramação da capa e do miolo.

    `CadastrarDiagramacaoObraForm` marca **capa e miolo** como obrigatórios e **renomeia** os dois
    para 'Diagramação da capa' e 'Diagramação do miolo' (`forms.py`); a `.feature` lista só o
    miolo, e com a caixa do rótulo diferente da que o formulário usa.
    """
    em_data('07/02/2018')
    tela = _publicacao(Tela(logado_pesquisa('diagramador')))

    tela.clicar_aba('Projeto gráfico e diagramação')
    tela.clicar_botao('Cadastrar Diagramação')
    _rota(tela, '/pesquisa/cadastrar_diagramacao/')
    tela.preencher_formulario(
        [
            ('Diagramação da capa', 'Arquivo', 'diagramacao_capa.png'),
            ('Diagramação do miolo', 'Arquivo', 'diagramacao_miolo.png'),
        ]
    )
    tela.clicar_botao('Salvar')

    tela.sucesso('Diagramação cadastrada com sucesso.')
    obra = _obra()
    obra.refresh_from_db()
    assert obra.arquivo_diagramacao_miolo, 'a UI disse que cadastrou, mas o arquivo da diagramação do miolo não foi anexado'
    assert obra.arquivo_diagramacao_capa, 'a UI disse que cadastrou, mas o arquivo da diagramação da capa não foi anexado'


def test_avaliacao_da_diagramacao(logado_pesquisa, em_data):
    """O autor aprova a capa e o miolo diagramados antes do pedido de ISBN."""
    em_data('07/02/2018')
    tela = _minhas_submissoes(logado_pesquisa('autor_obra'))

    tela.clicar_aba('Projeto gráfico e diagramação')
    tela.clicar_botao('Avaliar Diagramação')
    _rota(tela, '/pesquisa/avaliar_diagramacao/')
    tela.preencher('Aprovar capa', 'Lista', 'Sim')
    tela.preencher('Aprovar miolo', 'Lista', 'Sim')
    tela.clicar_botao('Salvar')

    tela.sucesso('Diagramação avaliada com sucesso.')
    obra = _obra()
    obra.refresh_from_db()
    assert obra.diagramacao_avaliada_em is not None, 'a UI disse que avaliou, mas a obra ficou sem a data da avaliação da diagramação'
    assert obra.diagramacao_capa_aprovada == 'Sim', f'a UI disse que aprovou a capa, mas gravou {obra.diagramacao_capa_aprovada!r}'
    assert obra.diagramacao_miolo_aprovada == 'Sim', f'a UI disse que aprovou o miolo, mas gravou {obra.diagramacao_miolo_aprovada!r}'


def test_cadastro_do_isbn_da_obra(logado_pesquisa, em_data):
    """O Integrante da Editora cadastra o ISBN da obra.

    `CadastrarISBNObraForm.clean` exige **pelo menos um** dos dois ISBNs, e a `.feature` só manda
    clicar em Salvar — sem valor, o formulário devolve "Informe pelo menos um ISBN.".
    """
    em_data('10/02/2018')
    tela = _publicacao(Tela(logado_pesquisa('integrante_editora')))

    tela.clicar_aba('Cadastro ISBN')
    tela.clicar_botao('Cadastrar ISBN')
    _rota(tela, '/pesquisa/cadastrar_isbn/')
    # `CadastrarISBNObraForm` renomeia o campo para 'ISBN (digital)' (`forms.py`), e é esse o
    # rótulo que o recorte por texto encontra.
    tela.preencher('ISBN (digital)', 'Texto', '978-85-0000-000-0')
    tela.clicar_botao('Salvar')

    tela.sucesso('ISBN cadastrado com sucesso.')
    obra = _obra()
    obra.refresh_from_db()
    assert obra.isbn_cadastrado_em is not None, 'a UI disse que cadastrou, mas a obra ficou sem data de cadastro de ISBN'
    assert obra.isbn == '978-85-0000-000-0', f'a UI disse que cadastrou, mas o ISBN gravou {obra.isbn!r}'


def test_cadastro_da_ficha_catalografica_da_obra(logado_pesquisa, em_data):
    """O Bibliotecário da Pesquisa cadastra a ficha catalográfica."""
    em_data('10/02/2018')
    tela = _publicacao(Tela(logado_pesquisa('bibliotecario')))

    tela.clicar_aba('Ficha catalográfica')
    tela.clicar_botao('Cadastrar Ficha Catalográfica')
    _rota(tela, '/pesquisa/cadastrar_ficha_catalografica/')
    # `FichaCatalograficaForm` exige o arquivo, e — mais importante — é `obra.ficha_catalografica`
    # que **habilita a aba "Publicação"** (`obra.html:910`: `data-checked` da aba é
    # `{% if obra.ficha_catalografica %}`). Sem o arquivo, as três etapas seguintes não têm aba.
    tela.preencher('Ficha Catalográfica', 'Arquivo', 'ficha_catalografica.png')
    tela.clicar_botao('Salvar')

    tela.sucesso('Ficha catalográfica cadastrada com sucesso.')
    obra = _obra()
    obra.refresh_from_db()
    assert obra.ficha_catalografica_cadastrada_em is not None, 'a UI disse que cadastrou, mas a obra ficou sem data de cadastro da ficha'


def test_registro_da_publicacao(logado_pesquisa, em_data):
    """O Integrante da Editora registra os dados de impressão e o repositório virtual.

    `PublicacaoObraForm` monta os campos conforme quem está logado: para quem **não** é o autor da
    submissão ele exige a situação da publicação, o número de cópias, a data de envio, o link do
    repositório, as bibliotecas, o acervo, a Biblioteca Nacional e os créditos de autoria. A
    `.feature` lista três.
    """
    em_data('10/02/2018')
    tela = _publicacao(Tela(logado_pesquisa('integrante_editora')))

    tela.clicar_aba('Publicação')
    tela.preencher_formulario(
        [
            # `situacao_publicacao` tem `default=NAO_INICIADA` no modelo, então o select já vem
            # preenchido — não é preciso (nem encontrável) preenchê-lo por rótulo.
            ('Número de Cópias', 'Texto', '100'),
            ('Data de Envio para Impressão', 'Data', '05/05/2018'),
            ('Link do Repositório Virtual', 'Texto', 'http://www.link_repositorio.com.br'),
            ('Bibliotecas dos Campi', 'Texto', 'CZN'),
            ('Acervo Físico da Editora', 'Texto', 'Sim'),
            ('Biblioteca Nacional', 'Texto', 'Sim'),
            ('Autor/Organizador', 'Texto', 'Autor Obra'),
            ('Coautor', 'Texto', 'Nenhum'),
        ]
    )
    tela.clicar_botao('Salvar')

    tela.sucesso('Dados da publicação registrados com sucesso.')
    obra = _obra()
    obra.refresh_from_db()
    assert obra.num_copias == 100, f'a UI disse que registrou, mas o número de cópias gravou {obra.num_copias!r}'
    assert obra.link_repositorio_virtual == 'http://www.link_repositorio.com.br', (
        f'a UI disse que registrou, mas o link do repositório gravou {obra.link_repositorio_virtual!r}'
    )


def test_cadastro_da_data_de_liberacao_para_repositorio_virtual(logado_pesquisa, em_data):
    """O autor informa quando a publicação poderá ser liberada no repositório."""
    from datetime import date

    em_data('11/02/2018')
    tela = _minhas_submissoes(logado_pesquisa('autor_obra'))

    tela.clicar_aba('Publicação')
    tela.preencher('Data de Liberação para Repositório Virtual', 'Data', '05/05/2018')
    tela.clicar_botao('Salvar')

    tela.sucesso('Dados da publicação registrados com sucesso.')
    obra = _obra()
    obra.refresh_from_db()
    assert obra.data_liberacao_repositorio_virtual == date(2018, 5, 5), (
        f'a UI disse que registrou a liberação, mas gravou {obra.data_liberacao_repositorio_virtual!r}'
    )


def test_finalizacao_dos_dados_sobre_a_publicacao(logado_pesquisa, em_data):
    """O Integrante da Editora encerra a coleta de dados da publicação."""
    em_data('12/02/2018')
    tela = _publicacao(Tela(logado_pesquisa('integrante_editora')))

    tela.clicar_aba('Publicação')
    tela.clicar_botao('Salvar')

    tela.sucesso('Dados da publicação registrados com sucesso.')
    obra = _obra()
    obra.refresh_from_db()
    assert obra.situacao_publicacao, 'a UI disse que finalizou, mas a situação da publicação ficou vazia'


def test_aprovacao_da_publicacao(logado_pesquisa, em_data):
    """O Conselheiro Editorial aprova a liberação da publicação.

    `AnaliseLiberacaoForm` exige ``aprovacao_liberacao_publicacao`` **e** ``obs_liberacao_publicacao``
    (``forms.py:2681-2691``); a `.feature` só preenche as observações.
    """
    em_data('13/02/2018')
    tela = _publicacao(Tela(logado_pesquisa('conselheiro')))

    tela.clicar_aba('Conselho editorial')
    tela.preencher('Aprovado', 'Lista', 'Sim')
    tela.preencher('Observações', 'TextArea', 'observacoes do conselheiro')
    tela.clicar_botao('Salvar')

    tela.sucesso('Análise da liberação da obra realizada com sucesso.')
    obra = _obra()
    obra.refresh_from_db()
    assert obra.aprovacao_liberacao_publicacao, 'a UI disse que aprovou, mas a obra ficou sem o registro da aprovação'


def test_conclusao_da_publicacao_da_obra(logado_pesquisa, em_data):
    """O Integrante da Editora conclui a publicação — o fim da esteira.

    `ConclusaoObraForm` exige ``obra_concluida``, o PDF final; a `.feature` só manda salvar. A
    asserção é ``obra_concluida_em``, o carimbo que fecha o fluxo.
    """
    em_data('14/02/2018')
    tela = _publicacao(Tela(logado_pesquisa('integrante_editora')))

    tela.clicar_aba('Conclusão')
    tela.clicar_botao('Concluir Obra')
    _rota(tela, '/pesquisa/concluir_obra/')
    tela.preencher('Obra Concluída', 'Arquivo', 'obra_concluida.pdf')
    tela.clicar_botao('Salvar')

    tela.sucesso('Obra concluída com sucesso.')
    obra = _obra()
    obra.refresh_from_db()
    assert obra.obra_concluida_em is not None, 'a UI disse que concluiu, mas a obra ficou sem data de conclusão'
