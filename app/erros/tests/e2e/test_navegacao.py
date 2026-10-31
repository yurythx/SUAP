"""Fluxo: as portas de entrada do módulo que nenhuma ``.feature`` descreve (modo 2).

Três telas que só existem para *achar* erro, e que quebram calado quando a derivação de
módulo/view muda:

* ``/erros/modulos/<area_id>/`` e ``/erros/modulo/<modulo_id>/`` — o caminho "reportar erro
  do módulo X" sem estar numa página de X. A rota do módulo não abre formulário nenhum: ela
  redireciona para a abertura com a própria URL em base64 (``erros/views.py:284-286``), e
  ``get_custom_view_name_from_url`` (``erros/utils.py:199-204``) tem um ramo **só** para esse
  caminho, que troca ``/erros/modulo/comum/`` por ``comum.views.nao_existe``. Sem esse ramo o
  erro nasceria com módulo afetado ``erros`` — todo erro reportado por módulo iria para a
  fila errada, sem erro nenhum na tela.
* ``/erros/reportar_erro/`` no ramo da **triagem de duplicidade**: quando já existe erro
  aberto para a mesma view, a tela troca o formulário pela lista de similares e separa "os
  meus" de "os dos outros" (``erros/views.py:238-243``). É o que impede o mesmo erro de ser
  reportado dez vezes; se a separação regredir, o usuário volta a ver formulário e a fila
  duplica.
* ``/erros/erros_informante/<pk>/`` — a lista que o atendente usa para ver se aquele
  informante está abrindo erro em série.

Nenhum teste daqui submete formulário: a abertura de erro é de ``test_reportar_erro.py``, e
um erro deixado para trás sobre ``VIEW_ABERTURA`` mandaria aquele teste para o ramo dos
similares (ver a docstring do ``conftest``).
"""

import base64

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# `area_id` vem das chaves de `get_areas_suap()`, que são os `AREA_SUAP_*` de
# `djtools/utils/apps.py:29-41` — não o rótulo "Comum" que a tela exibe. Área errada não dá
# 404: cai em `httprr('/erros/areas', 'Área inexistente.')`, que passaria despercebido.
URL_MODULOS = '/erros/modulos/{}/'
URL_MODULO = '/erros/modulo/{}/'
URL_ERRO = '/erros/erro/{}/'
URL_ERROS_INFORMANTE = '/erros/erros_informante/{}/'
URL_REPORTAR = '/erros/reportar_erro/'

AREA_COMUM = 'comum'
MODULO_COMUM = 'comum'

# A view de `URL_ORM` (conftest), que é onde os erros de fixture moram.
PAGINA_DOS_ERROS_DE_FIXTURE = '/comum/temas/'


def _url_de_abertura(caminho: str) -> str:
    """A URL de abertura como o rodapé do SUAP a monta: o caminho atual em base64.

    Espelha ``comum/templates/admin/base.html`` — o parâmetro não é o caminho cru, e
    ``reportar_erro`` responde "URL informada é incorreta" a qualquer coisa que não decodifique
    (``erros/views.py:229-236``).
    """
    return f'{URL_REPORTAR}?url={base64.b64encode(caminho.encode()).decode()}'


def test_lista_modulos_da_area_e_abre_a_reportagem_do_modulo(logado_erros):
    """Área → módulo → "Reportar erro do módulo", que é redirect e não formulário próprio."""
    tela = Tela(logado_erros('interessado')).ir(URL_MODULOS.format(AREA_COMUM))
    tela.ver_titulo('Área Comum')
    tela.ver_texto('Comum')

    tela.ir(URL_MODULO.format(MODULO_COMUM))

    # O redirect leva à abertura já no ramo do formulário: nenhum teste desta suíte reporta
    # erro sobre `comum.views.nao_existe`, então a triagem de duplicidade não dispara aqui.
    tela.ver_titulo('Reportar Erro no SUAP')
    tela.ver_texto('Instruções para Abertura de Erro')
    assert tela.pagina.url.endswith(base64.b64encode(f'/erros/modulo/{MODULO_COMUM}/'.encode()).decode()), (
        f'a abertura deveria receber a URL do módulo em base64, veio {tela.pagina.url!r}'
    )


AVISO_MEUS = 'Confira abaixo se este erro já foi reportado por você.'
AVISO_OUTROS = 'Verifique abaixo se este erro foi reportado por outros usuários'


@pytest.mark.parametrize(
    ('papel', 'aviso', 'aviso_ausente'),
    [
        ('interessado', AVISO_MEUS, AVISO_OUTROS),
        ('atendente', AVISO_OUTROS, AVISO_MEUS),
    ],
)
def test_reportar_erro_de_view_ja_reportada_mostra_similares(logado_erros, erro_aberto, papel, aviso, aviso_ausente):
    """Com erro aberto na mesma view, a abertura vira lista de similares — e ela é por papel.

    O informante vê o erro em "os seus" (``qs_meus``) e qualquer outro o vê em "os dos outros"
    (``qs_outros``): são dois quersés recortados pelo vínculo logado (``erros/views.py:241-242``).
    Trocar um pelo outro não quebra a tela, só faz o usuário deixar de reconhecer o próprio
    erro e reportar de novo. Por isso cada papel afirma **as duas** coisas: o aviso da sua
    lista presente e o da outra ausente — só o par distingue a troca, já que os dois avisos
    podem conviver quando o usuário tem erro dos dois tipos. É o que sustenta a escolha de
    ``VIEW_SECUNDARIA`` em ``test_erro_por_chamado``: em ``VIEW_ORM`` todo erro é informado
    pelo papel ``interessado``, e é isso que torna a ausência verificável.

    A asserção **não** procura o erro da fixture na página: as duas listas são paginadas de 5
    em 5 (``erros/templates/reportar_erro.html:13`` e ``:23``) e, no banco reusado, o registro
    recém-criado é o último da fila — cai na página 2 assim que a suíte inteira roda. O botão
    "Não encontrei erro similar" é o âncora estrutural: ele só existe neste ramo.
    """
    tela = Tela(logado_erros(papel)).ir(_url_de_abertura(PAGINA_DOS_ERROS_DE_FIXTURE))

    tela.ver_titulo('Reportar Erro no SUAP')
    tela.ver_texto(aviso)
    tela.ver_botao('Não encontrei erro similar. Desejo reportar um novo erro.')
    assert aviso_ausente not in tela.pagina.locator('//main').inner_text(), (
        f'o papel {papel!r} não deveria ver a outra lista de similares: {aviso_ausente!r}'
    )


def test_atendente_lista_os_outros_erros_do_informante(logado_erros, vinculos_erros, erro_aberto, erro_em_analise):
    """Do erro para a ficha do informante: dois erros abertos pela mesma pessoa aparecem juntos.

    O atalho "+N" só é renderizado para quem atende e quando o informante é funcionário
    (``erros/templates/erro.html:190-196``), e o N é a contagem de erros **não finalizados** do
    mesmo informante (``erros/views.py:326``) — por isso a asserção é sobre a presença dos dois
    erros, e não sobre um número, que cresce com o banco reusado.
    """
    interessado = vinculos_erros['interessado']
    tela = Tela(logado_erros('atendente')).ir(URL_ERRO.format(erro_aberto.pk))
    tela.ver_botao('Visualizar +')

    tela.ir(URL_ERROS_INFORMANTE.format(interessado.pk))
    tela.ver_titulo(f'Erros reportados por: {interessado}')
    tela.ver_texto(erro_aberto.descricao)
    tela.ver_texto(erro_em_analise.descricao)
