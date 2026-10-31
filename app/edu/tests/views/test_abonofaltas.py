"""Testes DB-free da view ``abonofaltas`` em ``edu/views/diarios.py``."""

from inspect import unwrap
from unittest.mock import MagicMock, patch

from django.template.loader import render_to_string

from edu.views import diarios


def test_abonofaltas_objeto_inexistente_tela_cheia(make_request):
    request = make_request(path='/')
    with (
        patch.object(diarios.AbonoFaltas.objects, 'filter') as mock_filter,
        patch.object(diarios, 'httprr', return_value='OBJ_INEXISTENTE') as mock_httprr,
    ):
        mock_filter.return_value.first.return_value = None
        resposta = unwrap(diarios.abonofaltas)(request, pk=999)

    mock_httprr.assert_called_once_with(
        '..',
        'Esta justificativa de falta não existe ou foi excluída.',
        'error',
        close_popup=False,
    )
    assert resposta == 'OBJ_INEXISTENTE'


def test_abonofaltas_objeto_inexistente_popup(make_request):
    request = make_request(path='/?_popup=1')
    with (
        patch.object(diarios.AbonoFaltas.objects, 'filter') as mock_filter,
        patch.object(diarios, 'httprr', return_value='FECHAR_POPUP') as mock_httprr,
    ):
        mock_filter.return_value.first.return_value = None
        resposta = unwrap(diarios.abonofaltas)(request, pk=999)

    mock_httprr.assert_called_once_with(
        '..',
        'Esta justificativa de falta não existe ou foi excluída.',
        'error',
        close_popup=True,
    )
    assert resposta == 'FECHAR_POPUP'


def test_abonofaltas_cancelar_deferimento_tela_cheia(make_request):
    user = MagicMock()
    user.has_group_cached.return_value = False
    request = make_request(path='/?cancelar_deferimento=1', user=user)

    mock_abono = MagicMock()
    mock_abono.pk = 1
    mock_abono.deferido = True

    with (
        patch.object(diarios.AbonoFaltas.objects, 'filter') as mock_filter,
        patch.object(diarios.Professor.objects, 'filter') as mock_prof_filter,
        patch.object(diarios.perms, 'realizar_procedimentos_academicos', return_value=True),
        patch.object(diarios, 'httprr', return_value='REDIRECT_ANTERIOR') as mock_httprr,
    ):
        mock_filter.return_value.first.return_value = mock_abono
        mock_prof_filter.return_value.first.return_value = None
        resposta = unwrap(diarios.abonofaltas)(request, pk=1)

    mock_abono.cancelar_deferimento.assert_called_once()
    mock_httprr.assert_called_once_with(request.path, 'Cancelamento de deferimento realizado com sucesso.')
    assert resposta == 'REDIRECT_ANTERIOR'


def test_abonofaltas_cancelar_deferimento_popup(make_request):
    user = MagicMock()
    user.has_group_cached.return_value = False
    request = make_request(path='/?cancelar_deferimento=1&_popup=1', user=user)

    mock_abono = MagicMock()
    mock_abono.pk = 1
    mock_abono.deferido = True

    with (
        patch.object(diarios.AbonoFaltas.objects, 'filter') as mock_filter,
        patch.object(diarios.Professor.objects, 'filter') as mock_prof_filter,
        patch.object(diarios.perms, 'realizar_procedimentos_academicos', return_value=True),
        patch.object(diarios, 'httprr', return_value='FECHAR_POPUP') as mock_httprr,
    ):
        mock_filter.return_value.first.return_value = mock_abono
        mock_prof_filter.return_value.first.return_value = None
        resposta = unwrap(diarios.abonofaltas)(request, pk=1)

    mock_abono.cancelar_deferimento.assert_called_once()
    mock_httprr.assert_called_once_with(request.path, 'Cancelamento de deferimento realizado com sucesso.')
    assert resposta == 'FECHAR_POPUP'


def test_abonofaltas_abonar_falta_tela_cheia(make_request):
    user = MagicMock(username='prof1')
    user.has_group_cached.return_value = False
    request = make_request(path='/?abonar=10', user=user)

    mock_professor = MagicMock()
    mock_falta = MagicMock()

    mock_abono = MagicMock()
    mock_abono.pk = 1
    mock_abono.motivo_ausencia_escolar = None
    mock_abono.falta_set.filter.return_value.values_list.return_value = [10]
    mock_abono.falta_set.filter.return_value.get.return_value = mock_falta

    with (
        patch.object(diarios.AbonoFaltas.objects, 'filter') as mock_filter,
        patch.object(diarios.Professor.objects, 'filter') as mock_prof_filter,
        patch.object(diarios.Falta.objects, 'filter') as mock_falta_filter,
        patch.object(diarios.perms, 'realizar_procedimentos_academicos', return_value=False),
        patch.object(diarios, 'httprr', return_value='REDIRECT_ANTERIOR') as mock_httprr,
    ):
        mock_filter.return_value.first.return_value = mock_abono
        mock_prof_filter.return_value.first.return_value = mock_professor
        mock_falta_filter.return_value.exists.return_value = True

        resposta = unwrap(diarios.abonofaltas)(request, pk=1)

    assert mock_falta.contabilizar is False
    mock_falta.save.assert_called_once()
    mock_httprr.assert_called_once_with(request.path, 'Ação realizada com sucesso.')
    assert resposta == 'REDIRECT_ANTERIOR'


def test_abonofaltas_desabonar_falta_tela_cheia(make_request):
    user = MagicMock(username='prof1')
    user.has_group_cached.return_value = False
    request = make_request(path='/?desabonar=10', user=user)

    mock_professor = MagicMock()
    mock_falta = MagicMock()

    mock_abono = MagicMock()
    mock_abono.pk = 1
    mock_abono.motivo_ausencia_escolar = None
    mock_abono.falta_set.filter.return_value.values_list.return_value = [10]
    mock_abono.falta_set.filter.return_value.get.return_value = mock_falta

    with (
        patch.object(diarios.AbonoFaltas.objects, 'filter') as mock_filter,
        patch.object(diarios.Professor.objects, 'filter') as mock_prof_filter,
        patch.object(diarios.Falta.objects, 'filter') as mock_falta_filter,
        patch.object(diarios.perms, 'realizar_procedimentos_academicos', return_value=False),
        patch.object(diarios, 'httprr', return_value='REDIRECT_ANTERIOR') as mock_httprr,
    ):
        mock_filter.return_value.first.return_value = mock_abono
        mock_prof_filter.return_value.first.return_value = mock_professor
        mock_falta_filter.return_value.exists.return_value = True

        resposta = unwrap(diarios.abonofaltas)(request, pk=1)

    assert mock_falta.contabilizar is True
    mock_falta.save.assert_called_once()
    mock_httprr.assert_called_once_with(request.path, 'Ação realizada com sucesso.')
    assert resposta == 'REDIRECT_ANTERIOR'


def test_abonofaltas_contexto_is_popup(make_request):
    user = MagicMock(username='aluno1')
    user.has_group_cached.return_value = False
    request_popup = make_request(path='/?_popup=1', user=user)
    request_cheia = make_request(path='/', user=user)

    mock_abono = MagicMock()
    mock_abono.pk = 1
    mock_abono.aluno.matricula = 'aluno1'
    mock_abono.deferido = None

    with (
        patch.object(diarios.AbonoFaltas.objects, 'filter') as mock_filter,
        patch.object(diarios.Professor.objects, 'filter') as mock_prof_filter,
        patch.object(diarios.perms, 'realizar_procedimentos_academicos', return_value=False),
    ):
        mock_filter.return_value.first.return_value = mock_abono
        mock_prof_filter.return_value.first.return_value = None

        ctx_popup = unwrap(diarios.abonofaltas)(request_popup, pk=1)
        ctx_cheia = unwrap(diarios.abonofaltas)(request_cheia, pk=1)

    assert ctx_popup['is_popup'] is True
    assert ctx_cheia['is_popup'] is False


def test_abonofaltas_com_sobreposicao(make_request):
    user = MagicMock(username='aluno1')
    user.has_group_cached.return_value = False
    request = make_request(path='/', user=user)

    mock_abono = MagicMock()
    mock_abono.pk = 1
    mock_abono.aluno.matricula = 'aluno1'
    mock_abono.data_inicio = '2026-03-01'
    mock_abono.data_fim = '2026-03-05'

    mock_sobreposicao = MagicMock()
    mock_sobreposicao.pk = 2

    with (
        patch.object(diarios.AbonoFaltas.objects, 'filter') as mock_filter,
        patch.object(diarios.Professor.objects, 'filter') as mock_prof_filter,
        patch.object(diarios.perms, 'realizar_procedimentos_academicos', return_value=False),
    ):
        mock_filter.return_value.first.return_value = mock_abono
        mock_prof_filter.return_value.first.return_value = None

        mock_qs = mock_filter.return_value.exclude.return_value.order_by.return_value
        mock_qs.__iter__.return_value = [mock_sobreposicao]
        mock_qs.__bool__.return_value = True

        ctx = unwrap(diarios.abonofaltas)(request, pk=1)

    assert mock_filter.call_count >= 2
    filtro_kwargs = mock_filter.call_args_list[-1][1]
    assert filtro_kwargs['aluno'] == mock_abono.aluno
    assert filtro_kwargs['data_inicio__lte'] == mock_abono.data_fim
    assert filtro_kwargs['data_fim__gte'] == mock_abono.data_inicio

    assert 'sobreposicoes' in ctx
    assert list(ctx['sobreposicoes']) == [mock_sobreposicao]


class _FakeAbonosManager:
    def __init__(self, items):
        self.all = items
        self._items = items

    def __bool__(self):
        return bool(self._items)


class _FakeAbono:
    def __init__(self, id=42, deferido=True):
        self.id = id
        self.data_inicio = '01/03/2026'
        self.data_fim = '05/03/2026'
        self.data_solicitacao = '01/03/2026'
        self.deferido = deferido
        self.motivo_ausencia_escolar_id = None
        self.justificativa = ''

    def get_status(self):
        if self.deferido is None:
            return 'Aguardando avaliação'
        if not self.deferido:
            return 'Indeferida'
        return 'Deferida'


def _criar_contexto_abonos(**kwargs):
    contexto = {
        'abonos': _FakeAbonosManager([_FakeAbono(id=42)]),
        'is_proprio_aluno': False,
        'tem_permissao_realizar_procedimentos': False,
        'perms': {},
    }
    contexto.update(kwargs)
    if 'pode_visualizar_abono_falta' not in kwargs:
        has_perm_view = bool(contexto.get('perms', {}).get('edu', {}).get('view_abonofaltas', False))
        contexto['pode_visualizar_abono_falta'] = contexto['is_proprio_aluno'] or contexto['tem_permissao_realizar_procedimentos'] or has_perm_view
    return contexto


def test_aluno_justificativas_falta_exibe_botao_visualizar_quando_proprio_aluno():
    contexto = _criar_contexto_abonos(is_proprio_aluno=True)
    html = render_to_string('tabs/aluno_justificativas_falta.html', contexto)
    assert '<th class="no-print">Ações</th>' in html
    assert '/edu/abonofaltas/42/' in html


def test_aluno_justificativas_falta_exibe_botao_visualizar_quando_tem_permissao_procedimentos():
    contexto = _criar_contexto_abonos(tem_permissao_realizar_procedimentos=True)
    html = render_to_string('tabs/aluno_justificativas_falta.html', contexto)
    assert '<th class="no-print">Ações</th>' in html
    assert '/edu/abonofaltas/42/' in html


def test_aluno_justificativas_falta_exibe_botao_visualizar_quando_tem_perm_view_abonofaltas():
    contexto = _criar_contexto_abonos(perms={'edu': {'view_abonofaltas': True}})
    html = render_to_string('tabs/aluno_justificativas_falta.html', contexto)
    assert '<th class="no-print">Ações</th>' in html
    assert '/edu/abonofaltas/42/' in html


def test_aluno_justificativas_falta_oculta_botao_visualizar_quando_sem_permissao():
    contexto = _criar_contexto_abonos(
        is_proprio_aluno=False,
        tem_permissao_realizar_procedimentos=False,
        perms={'edu': {'view_abonofaltas': False}},
    )
    html = render_to_string('tabs/aluno_justificativas_falta.html', contexto)
    assert '<th class="no-print">Ações</th>' not in html
    assert '/edu/abonofaltas/42/' not in html


def test_avaliar_abono_faltas_notificacao_quando_abono_a_criterio_do_docente(make_request):
    user = MagicMock()
    request = make_request(method='post', path='/', user=user, data={'deferido': True})
    mock_abono = MagicMock()
    mock_abono.abono_a_criterio_do_docente.return_value = True
    mock_abono.aluno.curso_campus = MagicMock()
    mock_abono.aluno.get_vinculo.return_value = 'aluno@ifrn.edu.br'

    mock_form = MagicMock()
    mock_form.is_valid.return_value = True
    mock_form.processar.return_value = mock_abono

    with (
        patch.object(diarios, 'get_object_or_404', return_value=mock_abono),
        patch.object(diarios.perms, 'realizar_procedimentos_academicos', return_value=True),
        patch.object(diarios, 'AvaliarAbonoFaltasForm', return_value=mock_form),
        patch.object(diarios, 'send_notification') as mock_send,
        patch.object(diarios, 'httprr', return_value='REDIRECT_SUCESSO'),
    ):
        unwrap(diarios.avaliar_abono_faltas)(request, pk=1)

    assert mock_send.call_count == 1
    args, _kwargs = mock_send.call_args
    assert 'a avaliação e o abono das faltas devem ser realizados pelo professor' in args[1]


def test_avaliar_abono_faltas_notificacao_padrao_quando_com_previsao_normativa(make_request):
    user = MagicMock()
    request = make_request(method='post', path='/', user=user, data={'deferido': True})
    mock_abono = MagicMock()
    mock_abono.abono_a_criterio_do_docente.return_value = False
    mock_abono.aluno.curso_campus = MagicMock()
    mock_abono.aluno.get_vinculo.return_value = 'aluno@ifrn.edu.br'

    mock_form = MagicMock()
    mock_form.is_valid.return_value = True
    mock_form.processar.return_value = mock_abono

    with (
        patch.object(diarios, 'get_object_or_404', return_value=mock_abono),
        patch.object(diarios.perms, 'realizar_procedimentos_academicos', return_value=True),
        patch.object(diarios, 'AvaliarAbonoFaltasForm', return_value=mock_form),
        patch.object(diarios, 'send_notification') as mock_send,
        patch.object(diarios, 'httprr', return_value='REDIRECT_SUCESSO'),
    ):
        unwrap(diarios.avaliar_abono_faltas)(request, pk=1)

    assert mock_send.call_count == 1
    args, _kwargs = mock_send.call_args
    assert args[1] == 'Sua justificativa de falta foi avaliada. Acesse o SUAP para obter mais detalhes.'


def test_admin_abono_faltas_tabs_inclui_sem_abono_docente():
    from edu.admin.procedimentos import AbonoFaltasAdmin

    admin = AbonoFaltasAdmin(diarios.AbonoFaltas, None)
    tabs = admin.get_tabs(MagicMock())
    assert 'tab_sem_abono_docente' in tabs
    assert 'tab_sem_meu_abono_docente' in tabs


def test_abono_falta_manager_sem_abono_docente_filtros():
    from edu.managers import AbonoFaltaManager

    manager = AbonoFaltaManager()
    mock_qs = MagicMock()
    user = MagicMock()

    manager.sem_abono_docente(queryset=mock_qs, user=user)
    mock_qs.filter.assert_called_once()
    filtros = mock_qs.filter.call_args[0][0]
    assert 'motivo_ausencia_escolar__possui_previsao_normativa' in str(filtros)
    assert 'falta__contabilizar' in str(filtros)
    mock_qs.filter.return_value.distinct.assert_called_once()


def test_abonofaltas_solicitacoes_bloqueadas_para_docente_quando_abono_indeferido(make_request):
    user = MagicMock()
    user.has_group_cached.side_effect = lambda g: g == 'Professor'
    request = make_request(path='/', user=user)

    mock_abono = MagicMock()
    mock_abono.pk = 1
    mock_abono.deferido = False
    mock_abono.aluno.matricula = 'aluno1'
    mock_abono.data_inicio = None
    mock_abono.data_fim = None
    mock_abono.motivo_ausencia_escolar = None

    with (
        patch.object(diarios.AbonoFaltas.objects, 'filter') as mock_filter,
        patch.object(diarios.Professor.objects, 'filter') as mock_prof_filter,
        patch.object(diarios.perms, 'realizar_procedimentos_academicos', return_value=True),
        patch.object(diarios.SolicitacaoReposicaoAtividade.objects, 'filter') as mock_sol_filter,
    ):
        mock_filter.return_value.first.return_value = mock_abono
        mock_prof_filter.return_value.first.return_value = None

        ctx = unwrap(diarios.abonofaltas)(request, pk=1)

    assert ctx['ids_solicitacoes'] == []
    mock_sol_filter.assert_not_called()


def test_avaliar_solicitacao_reposicao_atividade_403_quando_abono_nao_deferido(make_request):
    from edu.views import procedimentos

    user = MagicMock()
    request = make_request(path='/', user=user)

    mock_solicitacao = MagicMock()
    mock_solicitacao.abono_faltas.deferido = False

    with patch.object(procedimentos, 'get_object_or_404', return_value=mock_solicitacao):
        resposta = unwrap(procedimentos.avaliar_solicitacao_reposicao_atividade)(request, pk=10)

    assert resposta.status_code == 403
