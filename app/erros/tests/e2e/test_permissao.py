"""Fluxo: as três negativas de permissão do módulo, na mesma URL que libera outro papel (modo 2).

Aqui a verificação **não** é por status HTTP, como manda o teste transversal
``tests/e2e/test_permissao.py``: nenhuma destas views levanta ``PermissionDenied``: todas
devolvem ``httprr(..., 'erro')`` (``erros/views.py:484``, ``:509``, ``:559``), isto é, um 302
idêntico ao do caminho de sucesso. O que separa os dois é a mensagem — e, sobretudo, o efeito
que **não** aconteceu no banco. Por isso cada teste ataca a mesma URL com dois papéis: um
recusado e um aceito. É o contraste que prova que a guarda existe; sozinha, a mensagem de erro
também apareceria se a URL estivesse quebrada para todo mundo.

As três guardas, e a regressão que cada uma evita:

* ``adicionar_anexo`` exige ``pode_comentar`` — interessado ou Analista (``erros/models.py:180``).
  Sem ela, qualquer usuário anexa arquivo de visibilidade pública num erro alheio;
* ``alterar_url`` exige ``vinculo_pode_ser_atendente`` (``erros/views.py:483``). A URL define a
  ``view``, que define o módulo afetado e a triagem de duplicidade: quem reporta não pode
  reescrevê-la;
* ``desconsiderar_comentario`` exige ser o **autor** (``erros/models.py:548``). Ser interessado
  não basta — senão um interessado apagaria a fala de outro da linha do tempo.
"""

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

URL_ERRO = '/erros/erro/{}/'
URL_ANEXO = '/erros/adicionar_anexo/{}/'
URL_ALTERAR_URL = '/erros/alterar_url/{}/'
URL_DESCONSIDERAR = '/erros/desconsiderar_comentario/{}/'

SEM_PERMISSAO = 'Você não tem permissão para fazer isto.'


def test_anexo_so_para_quem_comenta_no_erro(logado_erros, erro_aberto):
    """O gerente (Recebedor de Demandas, não interessado, não Analista) é recusado; o interessado entra."""
    from erros.models import AnexoErro

    negado = Tela(logado_erros('gerente')).ir(URL_ERRO.format(erro_aberto.pk))
    negado.ir(URL_ANEXO.format(erro_aberto.pk))
    negado.erro(SEM_PERMISSAO)
    assert not AnexoErro.objects.filter(erro=erro_aberto).exists(), 'a tela recusou, mas algum anexo foi parar no erro'

    permitido = Tela(logado_erros('interessado')).ir(URL_ANEXO.format(erro_aberto.pk))
    permitido.ver_titulo(f'Adicionar anexo ao Erro {erro_aberto.pk}')


def test_alterar_url_so_para_quem_atende(logado_erros, erro_em_analise):
    """O interessado que reportou não reescreve a URL do próprio erro; o atendente sim."""
    url_original = erro_em_analise.url

    negado = Tela(logado_erros('interessado')).ir(URL_ERRO.format(erro_em_analise.pk))
    negado.ir(f'{URL_ALTERAR_URL.format(erro_em_analise.pk)}?tipo=erro')
    negado.erro(SEM_PERMISSAO)
    erro_em_analise.refresh_from_db()
    assert erro_em_analise.url == url_original, 'a tela recusou, mas a URL mudou'

    permitido = Tela(logado_erros('atendente')).ir(f'{URL_ALTERAR_URL.format(erro_em_analise.pk)}?tipo=erro')
    permitido.ver_titulo(f'Alterar URL do Erro {erro_em_analise.pk}')


def test_desconsiderar_comentario_so_pelo_autor(logado_erros, vinculos_erros, erro_em_analise):
    """Interessado no erro, mas não autor do comentário: recusado, e o comentário fica ativo.

    O comentário usado é um dos automáticos que ``gerenciar_atendente`` grava em nome do
    atendente ao assumir (``erros/models.py:391``) — ou seja, de autor diferente do papel que
    tenta desconsiderar, que é exatamente a única condição que falha aqui.
    """
    from erros.models import HistoricoComentarioErro

    comentario = HistoricoComentarioErro.objects.filter(erro=erro_em_analise, vinculo=vinculos_erros['atendente']).first()
    assert comentario is not None, 'a fixture deveria ter deixado um comentário automático do atendente'

    tela = Tela(logado_erros('interessado')).ir(URL_ERRO.format(erro_em_analise.pk))
    tela.ir(URL_DESCONSIDERAR.format(comentario.pk))

    tela.erro(SEM_PERMISSAO)
    comentario.refresh_from_db()
    assert comentario.ativo, 'a tela recusou, mas o comentário de outro autor foi desconsiderado'
