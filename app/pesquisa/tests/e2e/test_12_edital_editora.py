"""Fluxo: cadastro do edital de publicação de obras (modo 2).

Abre o subdomínio EDITORA. O edital de publicação é o documento que define **todo o
cronograma** do fluxo editorial — verificação de plágio, análise de especialista, validação do
conselho, envio dos termos, revisão, diagramação, ISBN, impressão — e é a referência de datas
que a esteira da feature 014 segue, etapa por etapa.

O que este arquivo pega: os quatro uploads (``Arquivo do Edital``, ``Manual do Autor``,
``Ficha de Avaliação para Parecerista``) e o ``FilteredSelectMultiple`` das linhas editoriais
no mesmo formulário, além do ``Texto Rico`` das instruções. É também o arquivo que cria as
duas entidades que os dois arquivos seguintes consomem: o edital e as linhas editoriais.

Os testes são **sequenciais**: o edital nasce aqui, e a feature 013 submete a obra nele.
"""

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# A feature 012 não fixa data (o cronograma é digitado no formulário), mas o edital precisa
# nascer antes de 08/01/2018 — quando a feature 013 submete a obra dentro das submissões
# (01→10/01). O valor é o piso da cadeia, como na 001.
DATA = '05/01/2018'

EDITAIS = '/admin/pesquisa/editalsubmissaoobra/'
FORMULARIO = '/admin/pesquisa/editalsubmissaoobra/add/'

TITULO_EDITAL_EDITORA = 'Edital para publicação'


def test_editais_de_publicacao_visivel_para_o_integrante(logado_pesquisa):
    """O Integrante da Editora enxerga o menu e a listagem de editais de publicação.

    O behave lista só o 108007, e as duas metades do cenário são afirmações diferentes: o item
    de menu (que só o menu renderizado prova — ver ``Tela.ver_item_de_menu``) e o acesso à
    listagem, que é o que o papel pode de fato operar.
    """
    tela = Tela(logado_pesquisa('integrante_editora')).ir('/')

    tela.ver_item_de_menu('Pesquisa::Editora::Submissões::Editais')

    tela.ir(EDITAIS)
    tela.ver_titulo('Editais para Submissão de Publicações')
    tela.ver_botao('Adicionar Edital para Submissão de Publicações')


def test_cadastro_do_edital_de_publicacao(logado_pesquisa):
    """O Integrante da Editora cadastra o edital com os 36 campos do cronograma editorial.

    As datas são as da feature, e não escolha do teste: cada etapa da esteira da 014 roda numa
    janela delas, e é o que faz a verificação de plágio acontecer em 13/01 e a diagramação em
    07/02. Trocar uma data move a etapa correspondente no tempo e faz a 014 falhar longe daqui.

    A asserção do ORM cobre o que a mensagem de sucesso não cobre: as linhas editoriais (o
    ``FilteredSelectMultiple`` grava vazio quando falta o clique no "Adicionar") e o arquivo do
    edital, sem o qual a obra da 013 não tem edital para se submeter.
    """
    from pesquisa.models import EditalSubmissaoObra

    tela = Tela(logado_pesquisa('integrante_editora')).ir(FORMULARIO)
    tela.ver_titulo('Adicionar Edital para Submissão de Publicações')

    tela.preencher_formulario(
        [
            ('Título', 'Texto', TITULO_EDITAL_EDITORA),
            ('Linhas Editoriais', 'FilteredSelectMultiple', 'Linha Editorial 01'),
            ('Arquivo do Edital', 'Arquivo', 'publicacao_edital.png'),
            ('Data de Início da Submissão', 'Data', '01/01/2018'),
            ('Data de Término da Submissão', 'Data', '10/01/2018'),
            ('Data de Início da Verificação de Plágio', 'Data', '11/01/2018'),
            ('Data de Término da Verificação de Plágio', 'Data', '15/01/2018'),
            ('Data de Início de Análise de Especialista', 'Data', '16/01/2018'),
            ('Data de Término de Análise de Especialista', 'Data', '28/01/2018'),
            ('Data de Início de Aceite', 'Data', '25/01/2018'),
            ('Data de Término de Aceite', 'Data', '28/01/2018'),
            ('Data de Início de Validação do Conselho', 'Data', '21/01/2018'),
            ('Data de Término de Validação do Conselho', 'Data', '28/01/2018'),
            ('Data de Início de Envio dos Termos', 'Data', '29/01/2018'),
            ('Data de Término de Envio dos Termos', 'Data', '31/01/2018'),
            ('Data de Início de Revisão Linguística/Textual', 'Data', '01/02/2018'),
            ('Data de Término de Revisão Linguística/Textual', 'Data', '04/02/2018'),
            ('Data de Início de Diagramação', 'Data', '05/02/2018'),
            ('Data de Término de Diagramação', 'Data', '08/02/2018'),
            ('Data de Início de Solicitação ISBN', 'Data', '09/02/2018'),
            ('Data de Término de Solicitação ISBN', 'Data', '13/02/2018'),
            ('Data de Início de Impressão de Boneco', 'Data', '10/02/2018'),
            ('Data de Término de Impressão de Boneco', 'Data', '18/02/2018'),
            ('Data de Revisão de Layout', 'Data', '19/02/2018'),
            ('Data de Início de Correção Final', 'Data', '10/02/2018'),
            ('Data de Término de Correção Final', 'Data', '23/02/2018'),
            ('Data de Início de Análise de Liberação', 'Data', '10/02/2018'),
            ('Data de Término de Análise de Liberação', 'Data', '01/03/2018'),
            ('Data de Início de Impressão', 'Data', '10/02/2018'),
            ('Data de Término de Impressão', 'Data', '05/03/2018'),
            ('Data de Lançamento', 'Data', '01/04/2018'),
            ('Local de Lançamento', 'Texto', 'Local do lançamento das obras'),
            ('Observações do Lançamento', 'Texto', 'Observações sobre o lançamento'),
            ('Instruções para Submissão de Obra', 'Texto Rico', 'Instruções'),
            ('Manual do Autor', 'Arquivo', 'manual.png'),
            ('Ficha de Avaliação para Parecerista', 'Arquivo', 'ficha_avaliacao.png'),
        ]
    )
    tela.clicar_botao('Salvar')

    tela.sucesso('Cadastro realizado com sucesso.')
    edital = EditalSubmissaoObra.objects.filter(titulo=TITULO_EDITAL_EDITORA).first()
    assert edital is not None, 'a UI disse que salvou, mas o edital de publicação não persistiu'
    assert edital.linha_editorial.exists(), 'a UI disse que salvou, mas as linhas editoriais ficaram vazias'
    assert edital.arquivo, 'a UI disse que salvou, mas o arquivo do edital não foi anexado'
    # A janela de submissão é o que a feature 013 usa para o edital aparecer em "Editais
    # Abertos": 01→10/01/2018, com a obra submetida em 08/01.
    assert edital.data_inicio_submissao.strftime('%d/%m/%Y') == '01/01/2018', (
        f'a UI disse que salvou, mas a submissão começa em {edital.data_inicio_submissao:%d/%m/%Y}'
    )
