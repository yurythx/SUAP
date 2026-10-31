"""Fluxo: o que o INTERESSADO faz depois que o erro existe (feature 001 do behave).

São as três coisas que sustentam a conversa entre quem reportou e quem atende: achar o erro
navegando por área → módulo → listagem, comentar (e desfazer o comentário) na linha do tempo,
e anexar um arquivo. A regressão que estes testes pegam é a de permissão silenciosa: quase
tudo aqui depende de `Erro.pode_comentar` (`erros/models.py:180`), que exige o vínculo ser
interessado — se ele parar de ser, a tela some sem erro nenhum, só fica vazia.
"""

from uuid import uuid4

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

AREAS = '/erros/areas/'


def test_lista_erros_navegando_por_area_e_modulo(logado_erros, erro_aberto):
    """Percorre Erros → Área Comum → módulo Comum → listagem → o erro.

    A linha é recortada pela URL do erro (única por execução) antes de clicar em "Visualizar":
    a listagem ordena por `('-qtd_vinculos_afetados', 'data_criacao')` (`erros/admin.py:92`),
    o que coloca o registro novo por ÚLTIMO, e um clique sem recorte abriria o erro de outro
    teste.
    """
    tela = Tela(logado_erros('interessado')).ir(AREAS)
    tela.ver_titulo('Erros')

    tela.clicar_link('Comum')
    tela.ver_titulo('Área Comum')

    tela.clicar_link('Comum')
    tela.ver_titulo('Erros')

    tela.linha(erro_aberto.descricao).clicar_link('Visualizar')
    tela.ver_titulo(f'Erro {erro_aberto.pk}: {erro_aberto.modulo_afetado_display}')


def test_interessado_comenta_e_desconsidera_o_comentario(logado_erros, erro_aberto):
    """Comenta e desfaz, num teste só: desconsiderar exige o comentário que o passo anterior criou.

    Desconsiderar não apaga — `desconsiderar_comentario` (`erros/models.py:558`) só marca
    `ativo=False`, e é isso que o template risca na tela. Por isso a asserção final é sobre a
    flag, não sobre a ausência da linha.
    """
    from erros.models import HistoricoComentarioErro

    tela = Tela(logado_erros('interessado')).ir(erro_aberto.get_absolute_url())
    texto = f'Erro ao tentar acessar a página inicial do suap (e2e {uuid4().hex[:8]})'

    tela.preencher_textarea('Adicionar interação', texto)
    tela.clicar_botao('Adicionar interação')

    tela.sucesso('Comentário cadastrado com sucesso.')
    tela.ver_texto(texto)
    comentario = HistoricoComentarioErro.objects.filter(erro=erro_aberto, descricao=texto).first()
    assert comentario is not None, 'a UI disse que cadastrou, mas o comentário não persistiu'
    assert comentario.ativo

    # A engrenagem só existe na linha de um comentário que o próprio usuário pode desconsiderar,
    # e este erro tem exatamente um (os demais são automáticos, sem menu).
    tela.clicar_icone('configuração')
    tela.clicar_botao('Desconsiderar comentário')

    tela.sucesso('Comentário desconsiderado com sucesso.')
    comentario.refresh_from_db()
    assert not comentario.ativo, 'a UI disse que desconsiderou, mas o comentário continua ativo'


def test_interessado_adiciona_anexo(logado_erros, erro_aberto):
    """Anexa um arquivo pela aba Anexos e confere que ele passa a listar.

    O formulário abre num popup do fancybox: o envio vai por `salvar_no_popup`, que espera o
    desfecho antes de a asserção começar a contar timeout — `clicar_botao` seguido de
    `sucesso` é a corrida da armadilha 15.
    """
    from erros.models import AnexoErro

    tela = Tela(logado_erros('interessado')).ir(erro_aberto.get_absolute_url())
    tela.clicar_aba('Anexos')
    tela.aba('Anexos').ver_texto('Nenhum anexo cadastrado.')

    tela.clicar_botao('Adicionar anexo')
    popup = tela.popup()
    # Asserção com retry ANTES de qualquer leitura do popup: o `body` do iframe fica visível
    # ainda vazio (armadilha 14). `ver_titulo` não serviria — ele olha o documento de fora.
    popup.ver_texto(f'Adicionar anexo ao Erro {erro_aberto.pk}')

    descricao = f'Problema no quadro de Erros (e2e {uuid4().hex[:8]})'
    popup.preencher_formulario(
        [
            ('Descrição', 'texto', descricao),
            ('Arquivo', 'arquivo', 'arquivo.jpg'),
        ]
    )
    popup.salvar_no_popup('Enviar')

    tela.sucesso('Anexo adicionado com sucesso.')
    assert AnexoErro.objects.filter(erro=erro_aberto, descricao=descricao).exists(), 'a UI disse que anexou, mas não persistiu'

    tela.clicar_aba('Anexos')
    tela.aba('Anexos').linha(descricao)
