"""Matriz de acesso do tesouro_gerencial, medida no navegador e por status HTTP.

O módulo inteiro é de um grupo só, ``Gestor do Tesouro Gerencial``, por dois mecanismos diferentes:
``group_required`` nas três views de ``urls.py`` e as permissões de model de ``permissions.yaml`` nos dois
admins do ``menu.yaml``. A matriz afirma que o gestor entra em todas as telas e que um servidor comum —
``staff``, isto é, que entra no ``/admin/`` — recebe 403 em cada uma. Os relatórios expõem a execução
orçamentária de todos os campi, e a importação reescreve documentos em massa: tela que abrisse para
qualquer servidor seria vazamento ou porta de escrita.

``Tela.buscar`` (requisição pela sessão do browser, sem renderizar, sem seguir redirect): o 302 para o
login nunca passa por 200.
"""

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

VARIAVEIS = '/tesouro_gerencial/variaveis/'
CAMPI = '/tesouro_gerencial/campi/'
IMPORTACAO = '/tesouro_gerencial/importacao/'
TIPOS = '/admin/tesouro_gerencial/tipodocumentoempenhoespecifico/'
TIPO_ADD = '/admin/tesouro_gerencial/tipodocumentoempenhoespecifico/add/'
DOCUMENTOS = '/admin/tesouro_gerencial/documentoempenhoespecifico/'
DOCUMENTO_ADD = '/admin/tesouro_gerencial/documentoempenhoespecifico/add/'
ADMIN_DO_MODULO = '/admin/tesouro_gerencial/'

# As telas de `urls.py` e as portas do `menu.yaml` (listagem e cadastro de cada admin).
TELAS_DO_GESTOR = [VARIAVEIS, CAMPI, IMPORTACAO, TIPOS, TIPO_ADD, DOCUMENTOS, DOCUMENTO_ADD]


@pytest.mark.parametrize('url', TELAS_DO_GESTOR)
@pytest.mark.parametrize(('papel', 'esperado'), [('gestor', 200), ('servidor', 403)])
def test_telas_do_modulo_so_abrem_para_o_gestor(logado_tesouro, papel, esperado, url):
    resposta = Tela(logado_tesouro(papel)).buscar(url)

    assert resposta.status == esperado, f'{papel} recebeu {resposta.status} em {url} (esperado {esperado})'


@pytest.mark.parametrize(('papel', 'esperado'), [('gestor', 200), ('servidor', 404)])
def test_indice_do_modulo_no_admin(logado_tesouro, papel, esperado):
    """É o destino do aviso de importação atrasada na página inicial do gestor (``index_inscricoes``).

    Para quem não tem permissão em nenhum model do app o Django admin responde **404**, não 403
    (``AdminSite.app_index``): o app simplesmente não existe para esse usuário.
    """
    resposta = Tela(logado_tesouro(papel)).buscar(ADMIN_DO_MODULO)

    assert resposta.status == esperado, f'{papel} recebeu {resposta.status} no índice do módulo no admin (esperado {esperado})'
