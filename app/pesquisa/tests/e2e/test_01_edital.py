"""Fluxo: cadastro e configuração do edital de pesquisa (modo 2).

A feature 001 é o começo da cadeia do PESQUISA: tudo o que as features 002→011 fazem depende
de existir um edital publicado com plano de oferta, fontes de recurso, critérios de avaliação
e comissão. É esta a funcionalidade que o Diretor de Pesquisa opera, e é a única do módulo em
que cinco telas diferentes têm de concordar sobre o mesmo objeto.

O que este arquivo pega: a perda de um dos campos do formulário de edital (o comportamento
`Peso da Avaliação do Coordenador` + `Peso da Avaliação do Projeto` tem de fechar 100), a aba
que some do detalhe do edital, e a quebra do encadeamento edital → plano de oferta → fonte de
recurso → critério → comissão, que é pré-requisito de todo o resto do módulo.

Os testes são **numerados e sequenciais**: `test_cadastro_do_edital` cria o edital que os
demais e todos os outros arquivos consomem.
"""

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# A data em que a feature 001 roda. Ela não tem `a data do sistema for` — os períodos do
# edital são digitados no formulário — mas o edital tem de nascer antes de 08/01/2018, que é
# quando a feature 002 submete o projeto (dentro de 01→10/01). O valor é só o piso da cadeia.
DATA = '05/01/2018'

LISTAGEM = '/admin/pesquisa/edital/'
FORMULARIO = '/admin/pesquisa/edital/add/'
COMISSOES = '/admin/pesquisa/comissaoeditalpesquisa/'

TITULO_EDITAL = 'Nome do edital'


def test_gerenciar_editais_visivel_para_o_diretor(logado_pesquisa):
    """O Diretor de Pesquisa enxerga o menu de editais e a listagem do admin.

    Cobre as duas metades do cenário de outline do behave: o item de menu ("vejo o item de
    menu", que só o menu renderizado prova — ver ``Tela.ver_item_de_menu``) e o acesso à
    listagem, que é o que o papel pode de fato operar. O behave lista só o 108001.
    """
    tela = Tela(logado_pesquisa('diretor')).ir('/')

    tela.ver_item_de_menu('Pesquisa::Editais::Gerenciar Editais')

    tela.ir(LISTAGEM)
    tela.ver_titulo('Editais')
    tela.ver_botao('Adicionar Edital')


def test_cadastro_do_edital(logado_pesquisa):
    """O Diretor cadastra o edital com os 24 campos que a feature 001 preenche.

    O edital nasce aqui e é o objeto de todo o resto da cadeia — inclusive dos outros dez
    arquivos. Os títulos e períodos são os da feature, não valores inventados: os períodos
    (inscrições 01→10/01, pré-seleção 11/01, seleção 15→17/01, divulgação 19/01) são a janela
    em que cada feature seguinte roda, e trocá-los quebra a cadeia inteira em silêncio.
    """
    from pesquisa.models import Edital

    tela = Tela(logado_pesquisa('diretor')).ir(FORMULARIO)
    tela.ver_titulo('Adicionar Edital')

    tela.preencher_formulario(
        [
            ('Título', 'Texto', TITULO_EDITAL),
            ('Descrição', 'TextArea', 'Descrição do Edital'),
            ('Tipo do Edital', 'Lista', 'Pesquisa'),
            ('Formato do Edital', 'Lista', 'Completo'),
            ('Forma de Seleção', 'Lista', 'Campus'),
            ('Edital de Campus', 'Checkbox', 'marcar'),
            ('Início das Inscrições', 'Data', '01/01/2018'),
            ('Fim das Inscrições', 'Data', '10/01/2018'),
            ('Início da Pré-Seleção', 'Data', '11/01/2018'),
            ('Início da Seleção', 'Data', '15/01/2018'),
            ('Fim da Seleção', 'Data', '17/01/2018'),
            ('Divulgação da Seleção', 'Data', '19/01/2018'),
            ('Titulações dos Avaliadores', 'FilteredSelectMultiple', 'Doutorado'),
            ('Participação de Aluno Obrigatória', 'Checkbox', 'desmarcar'),
            ('Anos de consideração das Publicações', 'Texto', '3'),
            ('Peso da Avaliação do Coordenador (%)', 'Texto', '30'),
            ('Peso da Avaliação do Projeto (%)', 'Texto', '70'),
            ('Ponto de Corte para Aprovação de Projeto (%)', 'Texto', '50'),
            ('Carga Horária do Coordenador', 'Texto', '4'),
            ('Período máximo currículo desatualizado', 'Texto', '6'),
            ('Total de Servidores', 'Texto', '5'),
            ('Total de Servidores Bolsistas', 'Texto', '3'),
            ('Total de Alunos', 'Texto', '2'),
            ('Total de Alunos Bolsistas', 'Texto', '1'),
        ]
    )
    tela.clicar_botao('Salvar')

    tela.sucesso('Edital cadastrado com sucesso.')
    edital = Edital.objects.filter(titulo=TITULO_EDITAL).first()
    assert edital is not None, 'a UI disse que salvou, mas o edital não persistiu'
    # Duas asserções de domínio que a mensagem de sucesso não cobre: os períodos são o que
    # faz a cadeia 002→011 caber, e as titulações são o `FilteredSelectMultiple` (o widget
    # que grava vazio se o clique no "Adicionar" não acontecer — `e2e_ui.py:487-492`).
    assert edital.inicio_inscricoes.strftime('%d/%m/%Y') == '01/01/2018', 'o período de inscrição não é o que a cadeia seguinte pressupõe'
    assert edital.titulacoes_avaliador.exists(), 'a UI disse que salvou, mas as titulações dos avaliadores ficaram vazias'


def _detalhe_do_edital(tela: Tela) -> Tela:
    """Listagem → linha do edital → ícone de exibição.

    É o caminho da feature (``olho para a listagem`` → ``olho a linha`` → ``clico no ícone de
    exibição``), e não ``ir('/admin/pesquisa/edital/<pk>/change/')``: o ícone é metade do que
    o cenário afirma, e é ele que garante que a ação está na linha do edital certo.
    """
    tela.ir(LISTAGEM)
    tela.linha(TITULO_EDITAL).clicar_icone('exibição')
    return tela.ver_titulo(f'{TITULO_EDITAL} - Edital de Pesquisa')


def test_plano_de_oferta_por_campus(logado_pesquisa):
    """O Diretor define a abrangência do edital: só servidores dos campi ofertados submetem.

    Sem linha no Plano de Oferta, ``Edital.pode_submeter_projeto`` recusa todo mundo — é o
    que faz a feature 002 parar antes do primeiro campo se este cadastro não acontecer.
    """
    from pesquisa.models import BolsaDisponivel

    tela = Tela(logado_pesquisa('diretor'))
    _detalhe_do_edital(tela)

    tela.clicar_aba('Plano de Oferta por Campus')
    tela.clicar_botao('Adicionar Oferta')
    tela.preencher_formulario(
        [
            ('Campi', 'FilteredSelectMultiple', 'CZN, CEN'),
            ('Bolsas de Iniciação Científica', 'Texto', '5'),
            ('Bolsas para Pesquisador', 'Texto', '3'),
        ]
    )
    tela.clicar_botao('Enviar')

    tela.sucesso('Oferta(s) adicionada(s) com sucesso.')
    # Duas asserções de domínio: o `FilteredSelectMultiple` grava vazio quando o clique no
    # "Adicionar" não acontece (`e2e_ui.py:487-492`), e o número de campi é o que define quem
    # consegue submeter projeto depois.
    campi = set(BolsaDisponivel.objects.filter(edital__titulo=TITULO_EDITAL).values_list('uo__setor__sigla', flat=True))
    assert {'CZN', 'CEN'} <= campi, f'a UI disse que salvou, mas o plano de oferta não cobriu CZN e CEN (tem {campi})'
    assert BolsaDisponivel.objects.filter(edital__titulo=TITULO_EDITAL, num_maximo_ic=5).exists(), (
        'a UI disse que salvou, mas as bolsas de IC não persistiram'
    )


def test_fontes_de_recurso_do_edital(logado_pesquisa):
    """O Diretor define o teto de gasto por rubrica — a base da memória de cálculo.

    É o valor que a feature 002 encontra como "Valor Reservado" no Plano de Aplicação; sem
    ele o coordenador não consegue cadastrar memória de cálculo nem desembolso.
    """
    from pesquisa.models import Recurso

    tela = Tela(logado_pesquisa('diretor'))
    _detalhe_do_edital(tela)

    tela.clicar_aba('Fonte de Recursos')
    tela.clicar_botao('Adicionar Recurso')

    popup = tela.popup()
    popup.preencher_formulario(
        [
            ('Origem', 'Lista', 'PROPI'),
            ('Valor disponível por projeto (R$)', 'Texto', '10.000,00'),
            ('Despesa', 'Autocomplete', 'Auxílio Financeiro a Estudantes'),
        ]
    )
    popup.salvar_no_popup('Salvar')

    tela.sucesso('Recurso adicionado com sucesso.')
    recurso = Recurso.objects.filter(edital__titulo=TITULO_EDITAL).order_by('-id').first()
    assert recurso is not None, 'a UI disse que salvou, mas a fonte de recurso não persistiu'
    assert str(recurso.valor).startswith('10000'), f'a UI disse que salvou, mas o valor do recurso gravou {recurso.valor}'


def test_criterios_de_avaliacao_do_edital(logado_pesquisa):
    """O Diretor define os critérios que os avaliadores pontuam na feature 005.

    O formulário de avaliação da feature 005 é montado a partir destes critérios — sem
    nenhum, o avaliador não tem o que pontuar e o fluxo de seleção não fecha.
    """
    from pesquisa.models import CriterioAvaliacao

    tela = Tela(logado_pesquisa('diretor'))
    _detalhe_do_edital(tela)

    tela.clicar_aba('Critérios de Avaliação da Qualificação do Projeto')
    tela.clicar_botao('Adicionar Critério de Avaliação')

    popup = tela.popup()
    popup.preencher_formulario(
        [
            ('Descrição', 'TextArea', 'Descrição do Critério 1'),
            ('Pontuação Máxima', 'Texto', '10,00'),
        ]
    )
    popup.salvar_no_popup('Salvar')

    tela.sucesso('Critério de avaliação adicionado com sucesso.')
    assert CriterioAvaliacao.objects.filter(edital__titulo=TITULO_EDITAL, descricao='Descrição do Critério 1').exists(), (
        'a UI disse que salvou, mas o critério de avaliação não persistiu'
    )


# O rótulo do edital como o SUAP monta nas listas de escolha: ``<título> - <tipo>``.
ROTULO_EDITAL = 'Nome do edital - Edital de Pesquisa'


def test_comissao_de_avaliacao_do_edital(logado_pesquisa):
    """O Diretor nomeia a comissão — o conjunto de onde a feature 004 tira os avaliadores.

    A comissão é o funil da seleção: a feature 004 só consegue indicar avaliador para o
    projeto porque ele está na comissão do edital.
    """
    from pesquisa.models import ComissaoEditalPesquisa

    tela = Tela(logado_pesquisa('diretor')).ir(COMISSOES)
    tela.ver_titulo('Comissões de Avaliação')
    tela.clicar_botao('Adicionar Comissão de Avaliação')
    tela.clicar_botao('Por Indicação de Nomes')

    tela.preencher_formulario(
        [
            ('Filtrar por Edital', 'Lista', ROTULO_EDITAL),
            ('Campus', 'Lista', 'CZN'),
            ('Membro', 'Autocomplete Multiplo', 'Avaliador1 Pesquisa'),
        ]
    )
    tela.clicar_botao('Salvar')

    tela.sucesso('Cadastro realizado com sucesso.')
    assert ComissaoEditalPesquisa.objects.filter(edital__titulo=TITULO_EDITAL).exists(), (
        'a UI disse que salvou, mas a comissão de avaliação não persistiu'
    )


def test_edicao_da_comissao_de_avaliacao(logado_pesquisa):
    """O Diretor acrescenta mais um membro à comissão já cadastrada.

    É o único cenário da feature 001 que edita em vez de criar, e o que prova que o segundo
    avaliador (108006) entra na comissão — sem ele a feature 005 não teria a segunda
    avaliação do projeto.
    """
    from pesquisa.models import ComissaoEditalPesquisa

    tela = Tela(logado_pesquisa('diretor')).ir(COMISSOES)
    tela.ver_titulo('Comissões de Avaliação')
    tela.linha(ROTULO_EDITAL).clicar_icone('edição')
    tela.ver_titulo('Editar Comissão do Nome do edital')

    tela.preencher_formulario(
        [
            ('Filtrar por Edital', 'Lista', ROTULO_EDITAL),
            ('Membro', 'Autocomplete Multiplo', 'Avaliador2 Pesquisa'),
        ]
    )
    tela.clicar_botao('Salvar')

    tela.sucesso('Atualização realizada com sucesso.')
    comissao = ComissaoEditalPesquisa.objects.filter(edital__titulo=TITULO_EDITAL).order_by('id').first()
    assert comissao is not None, 'a UI disse que atualizou, mas não há comissão'
    # A comissão guarda `comum.Vinculo`, não `Servidor` — a asserção tem de entrar pelo
    # vínculo, senão passaria com o M2M vazio por comparar a coisa errada.
    from rh.models import Servidor

    vinculo = Servidor.objects.get(matricula='108006').get_vinculo()
    assert comissao.vinculos_membros.filter(pk=vinculo.pk).exists(), 'a UI disse que atualizou, mas o segundo avaliador não entrou na comissão'
