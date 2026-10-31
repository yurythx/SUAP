"""Testes DB-free de quem pode efetuar inscrição pelo servidor.

O botão "Efetuar Inscrição" (``InscricaoAdmin.get_action_bar``) e a view ``inscricao_identificacao``
exigem ``Inscricao.PERMS_EFETUAR_INSCRICAO`` juntas: só o Assistente Social efetua inscrição;
o Coordenador Sistêmico e o Auditor apenas consultam. Chama-se ``__wrapped__`` do ``@rtr`` —
a camada ``@permission_required`` — com o corpo mockado.
"""

from unittest.mock import MagicMock, patch

import pytest
from django.contrib.admin import AdminSite
from django.core.exceptions import PermissionDenied

from ae import views
from ae.admin import InscricaoAdmin
from ae.models import Inscricao

# permissões de ae.inscricao de cada grupo (ae/permissions.yaml)
GRUPOS = {
    'Assistente Social': {'ae.add_inscricao', 'ae.pode_ver_motivo_solicitacao'},
    'Coordenador de Atividades Estudantis Sistêmico': {'ae.add_inscricao', 'ae.pode_ver_relatorio_inscricao_todos'},
    'Auditor': {'ae.pode_ver_motivo_solicitacao', 'ae.pode_ver_relatorio_inscricao_todos'},
}
PODE_EFETUAR = {'Assistente Social': True, 'Coordenador de Atividades Estudantis Sistêmico': False, 'Auditor': False}


def _request(rf, grupo):
    perms = GRUPOS[grupo]
    request = rf.get('/ae/inscricao_identificacao/')
    request.user = MagicMock(is_authenticated=True)
    request.user.has_perm.side_effect = perms.__contains__
    request.user.has_perms.side_effect = lambda lista: set(lista) <= perms
    return request


@pytest.mark.parametrize('grupo', GRUPOS)
def test_botao_efetuar_inscricao(rf, grupo):
    barra = InscricaoAdmin(Inscricao, AdminSite()).get_action_bar(_request(rf, grupo))
    assert any(item['label'] == 'Efetuar Inscrição' for item in barra) is PODE_EFETUAR[grupo]


@pytest.mark.parametrize('grupo', [g for g, pode in PODE_EFETUAR.items() if pode])
def test_quem_ve_o_botao_acessa_identificacao(rf, grupo):
    with patch.object(views, 'Programa'), patch.object(views, 'InscricaoFormFactory'), patch.object(views, 'get_uo'):
        contexto = views.inscricao_identificacao.__wrapped__(_request(rf, grupo))
    assert contexto['title'] == 'Efetuar Inscrição em Programa'


@pytest.mark.parametrize('grupo', [g for g, pode in PODE_EFETUAR.items() if not pode])
def test_quem_nao_ve_o_botao_nao_acessa_identificacao(rf, grupo):
    with pytest.raises(PermissionDenied):
        views.inscricao_identificacao.__wrapped__(_request(rf, grupo))
