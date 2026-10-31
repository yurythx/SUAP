"""Fluxo: submissão de obra para publicação (modo 2).

Com o edital de publicação aberto (012), o **autor** (108012) submete a obra. É a entrada da
esteira editorial: a partir daqui a obra atravessa verificação de plágio, análise de
especialista, conselho, termos autorais, revisão, diagramação, ISBN e catalogação — os 22
cenários da feature 014.

O que este arquivo pega: os quatro uploads do formulário (foto do autor, obra completa e obra
sem identificação), os dois ``checkbox`` de declaração — que são obrigatórios e cujo texto é
longo o bastante para o recorte por rótulo importar — e a lista ``Linha Editorial``, que o
edital da 012 alimentou. O autor é o único papel do módulo que submete, e é ele que a 014
reencontra em "Minhas Submissões" nas etapas que são dele (enviar correções, enviar termos).
"""

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# A data que a feature 013 fixa: dentro da janela de submissão do edital (01→10/01/2018).
DATA = '08/01/2018'

EDITAIS_ABERTOS = '/pesquisa/editais_abertos_submissao_obra/'

TITULO_EDITAL_EDITORA = 'Edital para publicação'
TITULO_OBRA = 'título da obra'

# Os dois termos que o autor declara. O rótulo é longo de propósito no formulário; aqui ele é
# reproduzido como a feature escreve, porque é o texto que o `contains` do recorte usa.
TERMO_POLITICA = 'Declaro ter lido os seguintes documentos: Política editorial, Direitos Autorais e Autorização de publicação da obra'
TERMO_CIENTE = 'Estou ciente de que a obra acima mencionada'


def test_submissao_da_obra(logado_pesquisa):
    """O autor submete a obra no edital de publicação aberto.

    A asserção de domínio é dupla e cobre o que a mensagem de sucesso não cobre: a obra existe
    com o título que a esteira da 014 usa para localizá-la em "Submissões" (``título da obra`` é
    o texto da linha recortada em todos os 22 cenários seguintes), e os dois arquivos de obra
    foram de fato anexados — sem eles a verificação de plágio da 014 não tem o que verificar.
    """
    from pesquisa.models import Obra

    tela = Tela(logado_pesquisa('autor_obra')).ir(EDITAIS_ABERTOS)
    tela.ver_titulo('Editais Abertos para Submissão de Publicação')

    tela.linha(TITULO_EDITAL_EDITORA)
    tela.ver_botao('Submeter Publicação')
    tela.linha(TITULO_EDITAL_EDITORA).clicar_botao('Submeter Publicação')

    tela.ver_titulo(f'Submeter Publicação: {TITULO_EDITAL_EDITORA}')
    tela.preencher_formulario(
        [
            ('Tipo', 'Lista', 'Autor'),
            ('Biografia do Autor/Organizador', 'TextArea', 'Descrição da biografia do autor'),
            ('Telefone', 'Texto', '(84) 91234-5678'),
            ('Foto do Autor/Organizador', 'Arquivo', 'foto_autor.png'),
            ('Título', 'Texto', TITULO_OBRA),
            ('Resumo para Catálogo', 'TextArea', 'sinospe da obra'),
            ('Sinopse para Quarta Capa', 'TextArea', 'sinospe para a quarta capa'),
            ('Linha Editorial', 'Lista', 'Linha Editorial 01'),
            ('Área', 'Lista', 'CIÊNCIAS EXATAS E DA TERRA'),
            ('Obra Completa', 'Arquivo', 'obra_completa.docx'),
            ('Obra Sem Identificação', 'Arquivo', 'obra_completa_sem_identificacao.pdf'),
            (TERMO_POLITICA, 'checkbox', 'marcar'),
            (TERMO_CIENTE, 'checkbox', 'marcar'),
        ]
    )
    tela.clicar_botao('Salvar')

    tela.sucesso('Publicação submetida com sucesso.')
    obra = Obra.objects.filter(titulo=TITULO_OBRA).order_by('-id').first()
    assert obra is not None, 'a UI disse que submeteu, mas a obra não persistiu'
    assert obra.arquivo, 'a UI disse que submeteu, mas a obra completa não foi anexada'
    assert obra.obra_sem_identificacao_autor, 'a UI disse que submeteu, mas a obra sem identificação não foi anexada'
    assert obra.edital.titulo == TITULO_EDITAL_EDITORA, f'a UI disse que submeteu, mas a obra caiu no edital {obra.edital.titulo!r}'
