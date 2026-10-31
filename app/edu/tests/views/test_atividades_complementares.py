"""Testes das views e formulários de atividades complementares e de extensão.

Cobre controle de acesso e processamento de solicitações de atividades complementares,
homologação via AJAX e vinculação de atividades de extensão a diários.
"""

from __future__ import annotations

import json
import re
from inspect import unwrap
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth.models import Group
from django.template.loader import render_to_string

from comum.tests.factories import UserFactory
from edu.forms.atividades_complementares import VincularAtividadeExtensaoForm
from edu.models import Componente, ComponenteCurricular, Diario, MatriculaDiario
from edu.tests.factories import (
    AlunoFactory,
    AtividadeCurricularExtensaoFactory,
    CursoCampusFactory,
    DiarioFactory,
    MatriculaDiarioFactory,
    MatriculaPeriodoFactory,
    MatrizFactory,
    ProfessorDiarioFactory,
    ProfessorFactory,
    VinculacaoAtividadeExtensaoFactory,
)
from edu.views import atividades_complementares

# make_request: fixture definida em edu/tests/views/conftest.py


def test_solicitar_atividade_complementar_aluno_sem_permissao_redireciona_com_erro(make_request: Any) -> None:
    user = MagicMock(username='2020101001', is_authenticated=True)
    request = make_request(user=user)

    aluno = MagicMock(matricula='2020101001')
    aluno.pode_solicitar_atividade_complementar.return_value = False

    with (
        patch.object(atividades_complementares.Aluno.objects, 'filter') as mock_filter,
        patch.object(atividades_complementares, 'httprr', return_value='REDIRECT_ERRO') as mock_httprr,
    ):
        mock_filter.return_value.first.return_value = aluno
        resposta = unwrap(atividades_complementares.solicitar_atividade_complementar)(request)

    mock_filter.assert_called_once_with(matricula='2020101001')
    aluno.pode_solicitar_atividade_complementar.assert_called_once_with(user)
    mock_httprr.assert_called_once_with('..', 'Você não tem permissão para solicitar atividade complementar.', 'error')
    assert resposta == 'REDIRECT_ERRO'


def test_solicitar_atividade_complementar_busca_aluno_pela_matricula_do_usuario(make_request: Any) -> None:
    """Garante que a busca do aluno seja feita pela matrícula do usuário logado (username),

    evitando selecionar outra matrícula da mesma pessoa física quando houver múltiplos vínculos.
    """
    user = MagicMock(username='20261012090004', is_authenticated=True)
    request = make_request(user=user)

    aluno = MagicMock(matricula='20261012090004')
    aluno.pode_solicitar_atividade_complementar.return_value = False

    with (
        patch.object(atividades_complementares.Aluno.objects, 'filter') as mock_filter,
        patch.object(atividades_complementares, 'httprr', return_value='REDIRECT_ERRO'),
    ):
        mock_filter.return_value.first.return_value = aluno
        unwrap(atividades_complementares.solicitar_atividade_complementar)(request)

    mock_filter.assert_called_once_with(matricula='20261012090004')


def test_solicitar_atividade_complementar_usuario_nao_aluno_redireciona_com_erro(make_request: Any) -> None:
    """Garante que usuários sem registro de aluno (como admin_academico em testes e2e)

    sejam redirecionados com mensagem de erro amigável em vez de receberem HTTP 404.
    """
    user = MagicMock(username='100001', is_authenticated=True)
    request = make_request(user=user)

    with (
        patch.object(atividades_complementares.Aluno.objects, 'filter') as mock_filter,
        patch.object(atividades_complementares, 'httprr', return_value='REDIRECT_ERRO') as mock_httprr,
    ):
        mock_filter.return_value.first.return_value = None
        resposta = unwrap(atividades_complementares.solicitar_atividade_complementar)(request, pk=1)

    mock_filter.assert_called_once_with(matricula='100001')
    mock_httprr.assert_called_once_with('..', 'Você não tem permissão para solicitar atividade complementar.', 'error')
    assert resposta == 'REDIRECT_ERRO'


def test_solicitar_atividade_complementar_com_permissao_get_retorna_contexto(make_request: Any) -> None:
    user = MagicMock(username='2020101001', is_authenticated=True)
    request = make_request(user=user)

    aluno = MagicMock(matricula='2020101001', pk=10)
    aluno.pode_solicitar_atividade_complementar.return_value = True

    form_mock = MagicMock()
    form_mock.is_valid.return_value = False

    with (
        patch.object(atividades_complementares.Aluno.objects, 'filter') as mock_filter,
        patch.object(atividades_complementares, 'AtividadeComplementarForm', return_value=form_mock) as mock_form_cls,
    ):
        mock_filter.return_value.first.return_value = aluno
        contexto = unwrap(atividades_complementares.solicitar_atividade_complementar)(request)

    assert contexto['aluno'] == aluno
    assert contexto['form'] == form_mock
    assert 'Adicionar solicitação de atividade complementar' in contexto['title']
    mock_form_cls.assert_called_once_with(
        None,
        initial={'aluno': 10},
        files=None,
        instance=None,
        as_aluno=True,
        request=request,
    )


def test_solicitar_atividade_complementar_post_valido_processa_e_redireciona(make_request: Any) -> None:
    vinculo_mock = MagicMock()
    user = MagicMock(username='2020101001', is_authenticated=True)
    user.get_vinculo.return_value = vinculo_mock
    request = make_request(method='post', user=user)

    aluno = MagicMock(matricula='2020101001', pk=10)
    aluno.pode_solicitar_atividade_complementar.return_value = True
    aluno.get_absolute_url.return_value = '/edu/aluno/2020101001/'

    form_mock = MagicMock()
    form_mock.is_valid.return_value = True

    with (
        patch.object(atividades_complementares.Aluno.objects, 'filter') as mock_filter,
        patch.object(atividades_complementares, 'AtividadeComplementarForm', return_value=form_mock),
        patch.object(atividades_complementares, 'httprr', return_value='REDIRECT_SUCESSO') as mock_httprr,
    ):
        mock_filter.return_value.first.return_value = aluno
        resposta = unwrap(atividades_complementares.solicitar_atividade_complementar)(request)

    form_mock.processar.assert_called_once_with(vinculo_mock)
    mock_httprr.assert_called_once_with(
        '/edu/aluno/2020101001/?tab=acc',
        'Atividade complementar adicionada com sucesso. Compareça à coordenação de curso ou setor competente para validação do documento.',
        close_popup=True,
    )
    assert resposta == 'REDIRECT_SUCESSO'


def test_solicitar_atividade_complementar_edicao_busca_atividade_do_aluno(make_request: Any) -> None:
    user = MagicMock(username='2020101001', is_authenticated=True)
    request = make_request(user=user)

    aluno = MagicMock(matricula='2020101001', pk=10)
    aluno.pode_solicitar_atividade_complementar.return_value = True

    atividade_mock = MagicMock(pk=42)
    form_mock = MagicMock()
    form_mock.is_valid.return_value = False

    with (
        patch.object(atividades_complementares.Aluno.objects, 'filter') as mock_filter,
        patch.object(atividades_complementares, 'get_object_or_404', return_value=atividade_mock) as mock_get_obj,
        patch.object(atividades_complementares, 'AtividadeComplementarForm', return_value=form_mock),
    ):
        mock_filter.return_value.first.return_value = aluno
        contexto = unwrap(atividades_complementares.solicitar_atividade_complementar)(request, pk=42)

    mock_get_obj.assert_called_once_with(
        atividades_complementares.AtividadeComplementar.objects,
        pk=42,
        deferida__isnull=True,
        aluno=aluno,
    )
    assert contexto['atividade'] == atividade_mock
    assert 'Editar solicitação de atividade complementar' in contexto['title']


def test_vincular_atividade_extensao_form_help_text() -> None:
    comp = Componente(sigla='LIC.1270', descricao_historico='Componente Principal')
    cc = ComponenteCurricular(ch_extensao=15, componente=comp)
    md = MagicMock()
    md.diario.componente_curricular = cc

    assert VincularAtividadeExtensaoForm._get_help_text_matricula_diario(md) == (
        'Este componente exige <strong>15 horas</strong> de atividades de extensão.'
    )

    comp_assoc = Componente(sigla='LIC.1284', descricao_historico='Componente Associado')
    cc_assoc = ComponenteCurricular(
        tipo=ComponenteCurricular.TIPO_REGULAR,
        ch_extensao=25,
        componente=comp_assoc,
    )
    cc.componente_curricular_associado = cc_assoc

    assert VincularAtividadeExtensaoForm._get_help_text_matricula_diario(md) == (
        'Este componente exige <strong>40 horas</strong> de atividades de extensão.'
        '<br>LIC.1270 - Componente Principal: 15 horas.'
        '<br>LIC.1284 - Componente Associado: 25 horas.'
    )


def _extrair_tag_select(html: str) -> str:
    match = re.search(r'<select[^>]*onchange="avaliar_atividade_extensao\([^>]*>', html)
    assert match is not None, 'Tag <select ... onchange="avaliar_atividade_extensao(...)"> não encontrada no HTML'
    return match.group(0)


def test_diario_aba_atividades_extensao_template() -> None:
    user = MagicMock(is_authenticated=True)

    class DummyVinculacao:
        pk = 10

        def __init__(self, situacao: str = '1') -> None:
            self.situacao = situacao

        def get_codigo_situacao(self) -> str:
            return self.situacao

        def __str__(self) -> str:
            return 'Atividade 1 - Projeto - 20 hora(s)'

    vinc = DummyVinculacao('1')

    aluno = SimpleNamespace(
        get_foto_75x100_url='/foto.jpg',
        get_nome='Aluno Teste',
        matricula='2020101',
        get_absolute_url=lambda: '/aluno/1/',
    )
    mp = SimpleNamespace(aluno=aluno)
    md = SimpleNamespace(
        pk=20,
        matricula_periodo=mp,
        vinculacaoatividadeextensao_set=SimpleNamespace(all=lambda: [vinc]),
        get_ch_atividade_extensao_cumprida=lambda: 20,
        habilitada=lambda: True,
        is_cursando=lambda: True,
    )
    cc = SimpleNamespace(
        get_ch_extensao_exigida=lambda: 20,
    )

    class DummyDiario:
        componente_curricular = cc
        matriculadiario_set = SimpleNamespace(all=lambda: [md])

        def __init__(self, pode: bool = False) -> None:
            self.pode = pode

        def pode_avaliar_atividade_extensao(self, u: Any) -> bool:
            return self.pode

    # 1. Usuário SEM permissão -> select deve ter disabled
    diario = DummyDiario(pode=False)
    context = {'obj': diario, 'request': SimpleNamespace(user=user)}
    html = render_to_string('diario_aba_atividades_extensao.html', context)
    select_tag = _extrair_tag_select(html)
    assert 'disabled' in select_tag
    assert 'data-situacao-anterior="1"' in select_tag
    assert '<option selected value="1">Homologada</option>' in html

    # 2. Usuário COM permissão -> select NÃO deve ter disabled
    diario = DummyDiario(pode=True)
    context = {'obj': diario, 'request': SimpleNamespace(user=user)}
    html = render_to_string('diario_aba_atividades_extensao.html', context)
    select_tag = _extrair_tag_select(html)
    assert 'disabled' not in select_tag
    assert 'data-situacao-anterior="1"' in select_tag
    assert '<option selected value="1">Homologada</option>' in html
    assert 'table-responsive' in html
    assert '<caption>Atividades de extensão dos alunos</caption>' in html
    assert 'text-center' in html
    assert 'align="center"' not in html
    assert 'visually-hidden' in html
    assert 'person borderless' in html
    assert '<th class="text-center">CH cumprida</th>' in html
    assert 'Período letivo fechado' not in html

    # 3. Estado vazio de vinculações e diário sem alunos
    md_sem_vinc = SimpleNamespace(
        pk=21,
        matricula_periodo=mp,
        vinculacaoatividadeextensao_set=SimpleNamespace(all=list),
        get_ch_atividade_extensao_cumprida=lambda: 0,
        habilitada=lambda: True,
        is_cursando=lambda: True,
    )
    diario_sem_vinc = DummyDiario(pode=True)
    diario_sem_vinc.matriculadiario_set = SimpleNamespace(all=lambda: [md_sem_vinc])
    html_sem_vinc = render_to_string('diario_aba_atividades_extensao.html', {'obj': diario_sem_vinc, 'request': SimpleNamespace(user=user)})
    assert '<span class="status status-default">Nenhuma</span>' in html_sem_vinc

    diario_vazio = DummyDiario(pode=True)
    diario_vazio.matriculadiario_set = SimpleNamespace(all=list)
    html_vazio = render_to_string('diario_aba_atividades_extensao.html', {'obj': diario_vazio, 'request': SimpleNamespace(user=user)})
    assert 'Nenhum aluno matriculado neste diário.' in html_vazio

    # 4. Aluno com período letivo fechado -> exibe indicação e desabilita select
    md_fechado = SimpleNamespace(
        pk=22,
        matricula_periodo=mp,
        vinculacaoatividadeextensao_set=SimpleNamespace(all=lambda: [vinc]),
        get_ch_atividade_extensao_cumprida=lambda: 20,
        habilitada=lambda: True,
        is_cursando=lambda: False,
    )
    diario_fechado = DummyDiario(pode=True)
    diario_fechado.matriculadiario_set = SimpleNamespace(all=lambda: [md_fechado])
    html_fechado = render_to_string('diario_aba_atividades_extensao.html', {'obj': diario_fechado, 'request': SimpleNamespace(user=user)})
    assert '<dd class="false">Período letivo fechado</dd>' in html_fechado
    select_fechado = _extrair_tag_select(html_fechado)
    assert 'disabled' in select_fechado


@pytest.mark.django_db
def test_avaliar_vinculacaoatividadeextensao_ajax_bloqueia_periodo_fechado(make_request: Any, sync_permissions: Any) -> None:
    matriz = MatrizFactory(requer_vinculacao_extensao_diarios=True)
    diario = DiarioFactory(
        componente_curricular__matriz=matriz,
        componente_curricular__ch_extensao=30,
        componente_curricular__qtd_avaliacoes=0,
    )
    professor = ProfessorFactory()
    ProfessorDiarioFactory(diario=diario, professor=professor)
    aluno = AlunoFactory(matriz=matriz, curso_campus=diario.turma.curso_campus)
    mp = MatriculaPeriodoFactory(aluno=aluno)
    md = MatriculaDiarioFactory(diario=diario, matricula_periodo=mp, situacao=MatriculaDiario.SITUACAO_APROVADO)
    vinc = VinculacaoAtividadeExtensaoFactory(matricula_diario=md, carga_horaria=20, homologada=None)

    req = make_request(user=professor.vinculo.user)
    res = unwrap(atividades_complementares.avaliar_vinculacaoatividadeextensao_ajax)(req, pk=vinc.pk, situacao='1')
    assert res.status_code == 400
    data = json.loads(res.content)
    assert 'período letivo deste aluno está fechado' in data['erro']
    assert data['situacao_anterior'] == '0'
    vinc.refresh_from_db()
    assert vinc.homologada is None


@pytest.mark.django_db
def test_avaliar_vinculacaoatividadeextensao_ajax_permissao_posse_professor(make_request: Any, sync_permissions: Any) -> None:
    matriz = MatrizFactory(requer_vinculacao_extensao_diarios=True)
    diario = DiarioFactory(
        componente_curricular__matriz=matriz,
        componente_curricular__ch_extensao=30,
        componente_curricular__qtd_avaliacoes=0,
    )
    professor = ProfessorFactory()
    ProfessorDiarioFactory(diario=diario, professor=professor)
    aluno = AlunoFactory(matriz=matriz, curso_campus=diario.turma.curso_campus)
    mp = MatriculaPeriodoFactory(aluno=aluno)
    md = MatriculaDiarioFactory(diario=diario, matricula_periodo=mp, situacao=MatriculaDiario.SITUACAO_CURSANDO)
    vinc = VinculacaoAtividadeExtensaoFactory(matricula_diario=md, carga_horaria=20, homologada=None)

    # 1. Usuário sem ser professor do diário recebe 403
    user_outro = UserFactory()
    req_outro = make_request(user=user_outro)
    res_outro = unwrap(atividades_complementares.avaliar_vinculacaoatividadeextensao_ajax)(req_outro, pk=vinc.pk, situacao='1')
    assert res_outro.status_code == 403
    data_outro = json.loads(res_outro.content)
    assert data_outro['situacao_anterior'] == '0'
    assert 'Você não tem permissão para avaliar atividades de extensão neste diário.' in data_outro['erro']
    vinc.refresh_from_db()
    assert vinc.homologada is None

    # 2. Professor do diário homologa com sucesso (200)
    prof_user = professor.vinculo.user
    req_prof = make_request(user=prof_user)
    res_prof = unwrap(atividades_complementares.avaliar_vinculacaoatividadeextensao_ajax)(req_prof, pk=vinc.pk, situacao='1')
    assert res_prof.status_code == 200
    vinc.refresh_from_db()
    assert vinc.homologada is True
    assert vinc.responsavel_homologacao == prof_user


@pytest.mark.django_db
def test_avaliar_vinculacaoatividadeextensao_ajax_permissao_posse_registro(make_request: Any, sync_permissions: Any) -> None:
    matriz = MatrizFactory(requer_vinculacao_extensao_diarios=True)
    diario = DiarioFactory(
        componente_curricular__matriz=matriz,
        componente_curricular__ch_extensao=30,
        componente_curricular__qtd_avaliacoes=0,
    )
    professor = ProfessorFactory()
    ProfessorDiarioFactory(diario=diario, professor=professor)
    diario.posse_etapa_5 = Diario.POSSE_REGISTRO_ESCOLAR
    diario.save()
    assert diario.em_posse_do_registro() is True

    aluno = AlunoFactory(matriz=matriz, curso_campus=diario.turma.curso_campus)
    mp = MatriculaPeriodoFactory(aluno=aluno)
    md = MatriculaDiarioFactory(diario=diario, matricula_periodo=mp, situacao=MatriculaDiario.SITUACAO_CURSANDO)
    vinc = VinculacaoAtividadeExtensaoFactory(matricula_diario=md, carga_horaria=20, homologada=None)

    # 1. Professor do diário sem permissão de registro escolar recebe 403
    prof_user = professor.vinculo.user
    req_prof = make_request(user=prof_user)
    res_prof = unwrap(atividades_complementares.avaliar_vinculacaoatividadeextensao_ajax)(req_prof, pk=vinc.pk, situacao='1')
    assert res_prof.status_code == 403
    data_prof = json.loads(res_prof.content)
    assert data_prof['situacao_anterior'] == '0'
    assert 'Você não tem permissão para avaliar atividades de extensão neste diário.' in data_prof['erro']
    vinc.refresh_from_db()
    assert vinc.homologada is None

    # 2. Administrador acadêmico com permissão homologa com sucesso (200)
    admin_user = UserFactory()
    admin_user.groups.add(Group.objects.get(name='Administrador Acadêmico'))
    req_admin = make_request(user=admin_user)
    res_admin = unwrap(atividades_complementares.avaliar_vinculacaoatividadeextensao_ajax)(req_admin, pk=vinc.pk, situacao='1')
    assert res_admin.status_code == 200
    vinc.refresh_from_db()
    assert vinc.homologada is True
    assert vinc.responsavel_homologacao == admin_user


@pytest.mark.django_db
def test_avaliar_vinculacaoatividadeextensao_ajax_limite_carga_horaria(make_request: Any, sync_permissions: Any) -> None:
    matriz = MatrizFactory(requer_vinculacao_extensao_diarios=True)
    diario = DiarioFactory(
        componente_curricular__matriz=matriz,
        componente_curricular__ch_extensao=30,
        componente_curricular__qtd_avaliacoes=0,
    )
    professor = ProfessorFactory()
    ProfessorDiarioFactory(diario=diario, professor=professor)
    aluno = AlunoFactory(matriz=matriz, curso_campus=diario.turma.curso_campus)
    mp = MatriculaPeriodoFactory(aluno=aluno)
    md = MatriculaDiarioFactory(diario=diario, matricula_periodo=mp, situacao=MatriculaDiario.SITUACAO_CURSANDO)

    # Vinculação pré-existente de 10h já homologada
    VinculacaoAtividadeExtensaoFactory(matricula_diario=md, carga_horaria=10, homologada=True)

    # Nova vinculação de 25h que excederá a CH exigida (10 + 25 = 35 > 30)
    vinc = VinculacaoAtividadeExtensaoFactory(matricula_diario=md, carga_horaria=25, homologada=None)

    prof_user = professor.vinculo.user
    req = make_request(user=prof_user)

    # 1. Bloqueia homologação excedente com 400
    res_bloqueio = unwrap(atividades_complementares.avaliar_vinculacaoatividadeextensao_ajax)(req, pk=vinc.pk, situacao='1')
    assert res_bloqueio.status_code == 400
    data = json.loads(res_bloqueio.content)
    assert data['situacao_anterior'] == '0'
    assert 'supera a carga horária exigida pela disciplina (30h)' in data['erro']
    vinc.refresh_from_db()
    assert vinc.homologada is None

    # 2. Ajustando carga para 20h (10 + 20 = 30 <= 30), homologa com 200
    vinc.carga_horaria = 20
    vinc.save()
    res_sucesso = unwrap(atividades_complementares.avaliar_vinculacaoatividadeextensao_ajax)(req, pk=vinc.pk, situacao='1')
    assert res_sucesso.status_code == 200
    assert b'30 de 30 hora(s)' in res_sucesso.content
    vinc.refresh_from_db()
    assert vinc.homologada is True
    assert vinc.responsavel_homologacao == prof_user


@pytest.mark.django_db
def test_avaliar_vinculacaoatividadeextensao_ajax_situacoes_nao_homologada_e_invalida(make_request: Any, sync_permissions: Any) -> None:
    matriz = MatrizFactory(requer_vinculacao_extensao_diarios=True)
    diario = DiarioFactory(
        componente_curricular__matriz=matriz,
        componente_curricular__ch_extensao=30,
        componente_curricular__qtd_avaliacoes=0,
    )
    professor = ProfessorFactory()
    ProfessorDiarioFactory(diario=diario, professor=professor)
    aluno = AlunoFactory(matriz=matriz, curso_campus=diario.turma.curso_campus)
    mp = MatriculaPeriodoFactory(aluno=aluno)
    md = MatriculaDiarioFactory(diario=diario, matricula_periodo=mp, situacao=MatriculaDiario.SITUACAO_CURSANDO)
    vinc = VinculacaoAtividadeExtensaoFactory(matricula_diario=md, carga_horaria=25, homologada=True)

    prof_user = professor.vinculo.user
    req = make_request(user=prof_user)

    # 1. Marcar como não homologada (situacao='2')
    res_reprova = unwrap(atividades_complementares.avaliar_vinculacaoatividadeextensao_ajax)(req, pk=vinc.pk, situacao='2')
    assert res_reprova.status_code == 200
    vinc.refresh_from_db()
    assert vinc.homologada is False
    assert vinc.responsavel_homologacao == prof_user

    # 2. Voltar para pendente (situacao='0')
    res_pendente = unwrap(atividades_complementares.avaliar_vinculacaoatividadeextensao_ajax)(req, pk=vinc.pk, situacao='0')
    assert res_pendente.status_code == 200
    vinc.refresh_from_db()
    assert vinc.homologada is None
    assert vinc.responsavel_homologacao is None

    # 3. Situação inválida retorna 400
    res_invalida = unwrap(atividades_complementares.avaliar_vinculacaoatividadeextensao_ajax)(req, pk=vinc.pk, situacao='99')
    assert res_invalida.status_code == 400
    data_invalida = json.loads(res_invalida.content)
    assert 'Situação de homologação inválida.' in data_invalida['erro']


@pytest.mark.django_db
def test_avaliar_vinculacaoatividadeextensao_ajax_permite_quando_ch_requerida_zero(make_request: Any, sync_permissions: Any) -> None:
    matriz = MatrizFactory(requer_vinculacao_extensao_diarios=True)
    diario = DiarioFactory(
        componente_curricular__matriz=matriz,
        componente_curricular__ch_extensao=0,
        componente_curricular__qtd_avaliacoes=0,
    )
    professor = ProfessorFactory()
    ProfessorDiarioFactory(diario=diario, professor=professor)
    aluno = AlunoFactory(matriz=matriz, curso_campus=diario.turma.curso_campus)
    mp = MatriculaPeriodoFactory(aluno=aluno)
    md = MatriculaDiarioFactory(diario=diario, matricula_periodo=mp, situacao=MatriculaDiario.SITUACAO_CURSANDO)
    vinc = VinculacaoAtividadeExtensaoFactory(matricula_diario=md, carga_horaria=25, homologada=None)

    prof_user = professor.vinculo.user
    req = make_request(user=prof_user)
    res = unwrap(atividades_complementares.avaliar_vinculacaoatividadeextensao_ajax)(req, pk=vinc.pk, situacao='1')
    assert res.status_code == 200
    vinc.refresh_from_db()
    assert vinc.homologada is True


@pytest.mark.django_db
def test_vincular_atividade_extensao_form_clean_bloqueia_excesso_por_componente_db(sync_permissions: Any) -> None:
    atividade = AtividadeCurricularExtensaoFactory(carga_horaria=50)
    mp = atividade.matricula_periodo
    diario = DiarioFactory(
        componente_curricular__ch_extensao=30,
        componente_curricular__qtd_avaliacoes=0,
    )
    md = MatriculaDiarioFactory(matricula_periodo=mp, diario=diario, situacao=MatriculaDiario.SITUACAO_CURSANDO)

    outra_atividade = AtividadeCurricularExtensaoFactory(matricula_periodo=mp, carga_horaria=50)
    vinc_outra = VinculacaoAtividadeExtensaoFactory(matricula_diario=md, atividade_extensao=outra_atividade, carga_horaria=10, homologada=None)

    # 1. Vinculação pendente (homologada=None) NÃO bloqueia nova distribuição
    form_pendente = VincularAtividadeExtensaoForm(atividade, data={f'{md.pk}': 25})
    assert form_pendente.is_valid() is True

    # 2. Vinculação homologada (homologada=True): 10h (outras) + 25h = 35h > 30h exigidas -> Erro no campo
    vinc_outra.homologada = True
    vinc_outra.save()

    form_invalido = VincularAtividadeExtensaoForm(atividade, data={f'{md.pk}': 25})
    assert form_invalido.is_valid() is False
    assert f'{md.pk}' in form_invalido.errors
    assert 'não pode exceder a carga horária exigida pela disciplina (30h)' in form_invalido.errors[f'{md.pk}'][0]

    # 3. 10h (homologada) + 20h = 30h <= 30h exigidas -> Válido
    form_valido = VincularAtividadeExtensaoForm(atividade, data={f'{md.pk}': 20})
    assert form_valido.is_valid() is True
    assert form_valido.cleaned_data[f'{md.pk}'] == 20

    # 4. Vinculação rejeitada (homologada=False) NÃO bloqueia nova distribuição
    vinc_outra.homologada = False
    vinc_outra.save()
    form_rejeitada = VincularAtividadeExtensaoForm(atividade, data={f'{md.pk}': 25})
    assert form_rejeitada.is_valid() is True


@pytest.mark.django_db
def test_distribuir_atividadecurricularextensao_permissao(make_request: Any, sync_permissions: Any) -> None:
    from django.contrib.auth.models import Group
    from comum.tests.factories import UserFactory
    from edu.tests.factories import AlunoFactory, AtividadeCurricularExtensaoFactory, CursoCampusFactory, MatrizFactory

    matriz = MatrizFactory(requer_vinculacao_extensao_diarios=True)
    curso_campus = CursoCampusFactory()
    aluno = AlunoFactory(matriz=matriz, curso_campus=curso_campus)
    aluno_user = UserFactory(username=aluno.matricula)
    atividade = AtividadeCurricularExtensaoFactory(matricula_periodo__aluno=aluno)

    # 1. Outro aluno tentando acessar a distribuição de outro -> Bloqueado com redirecionamento
    outro_aluno = AlunoFactory()
    outro_aluno_user = UserFactory(username=outro_aluno.matricula)
    req_outro = make_request(user=outro_aluno_user)
    res_outro = unwrap(atividades_complementares.distribuir_atividadecurricularextensao)(req_outro, pk=atividade.pk)
    assert res_outro.status_code == 302

    # 2. Usuário comum sem permissão -> Bloqueado com redirecionamento
    user_comum = UserFactory()
    req_comum = make_request(user=user_comum)
    res_comum = unwrap(atividades_complementares.distribuir_atividadecurricularextensao)(req_comum, pk=atividade.pk)
    assert res_comum.status_code == 302

    # 3. O próprio aluno acessando -> Autorizado (retorna dicionário locals())
    req_aluno = make_request(user=aluno_user)
    res_aluno = unwrap(atividades_complementares.distribuir_atividadecurricularextensao)(req_aluno, pk=atividade.pk)
    assert isinstance(res_aluno, dict)
    assert res_aluno['obj'] == atividade

    # 4. Administrador acadêmico acessando -> Autorizado
    admin_user = UserFactory()
    admin_user.groups.add(Group.objects.get(name='Administrador Acadêmico'))
    req_admin = make_request(user=admin_user)
    res_admin = unwrap(atividades_complementares.distribuir_atividadecurricularextensao)(req_admin, pk=atividade.pk)
    assert isinstance(res_admin, dict)
    assert res_admin['obj'] == atividade
