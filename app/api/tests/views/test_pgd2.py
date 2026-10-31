import json
from decimal import Decimal

import pytest

from demandas.models import AnalistaDesenvolvedor
from pgd2.models import PlanoIndividualTrabalho, RegistroAcaoPlanoIndividualTrabalho, RelatorioIndividualTrabalho

URL_ENTREGAS = '/api/pgd2/execucao-gitlab/entregas-disponiveis/'
URL_LANCAR_RIT = '/api/pgd2/execucao-gitlab/lancar-rit/'
URL_RIT_DO_MR = '/api/pgd2/execucao-gitlab/rit-do-mr/'
URL_HORAS_PIT = '/api/pgd2/execucao-gitlab/horas-pit/'


def _mapear_dev(servidor, username='dev.fulano'):
    """Cria o vínculo ``AnalistaDesenvolvedor`` para o servidor com o username GitLab informado."""
    from django.contrib.auth.models import Group

    Group.objects.get_or_create(name='Analista')
    return AnalistaDesenvolvedor.objects.create(usuario=servidor.get_user(), username_gitlab=username, ativo=True)


@pytest.fixture
def gate_rit_aberto(monkeypatch):
    monkeypatch.setattr(PlanoIndividualTrabalho, 'pode_cadastrar_entrega_rit', lambda self, *a, **k: True)


@pytest.fixture
def sem_calculo_pit(monkeypatch):
    monkeypatch.setattr(PlanoIndividualTrabalho, 'calcular_pit', lambda self: None)


def _payload(cadeia, **over):
    dados = {
        'gitlab_username': 'dev.fulano',
        'gitlab_project_id': 42,
        'gitlab_mr_iid': 7,
        'entrega_pit_id': cadeia.entrega_pit.id,
        'titulo': 'Execução do MR !7',
        'descricao': 'Trabalho entregue.',
        'tempo_executado': '4',
        'perc_executada_em_teletrabalho': '50',
        'quantidade_progresso': '100',
    }
    dados.update(over)
    return dados


def _lancar_rit(api_client, payload, user):
    return api_client.post(
        URL_LANCAR_RIT,
        data=json.dumps(payload),
        content_type='application/json',
        user=user,
        HTTP_AUTHORIZATION='Bearer fake-token',
    )


def _rit_do_mr(api_client, gitlab_project_id, gitlab_mr_iid, user):
    return api_client.get(
        f'{URL_RIT_DO_MR}?gitlab_project_id={gitlab_project_id}&gitlab_mr_iid={gitlab_mr_iid}',
        user=user,
        HTTP_AUTHORIZATION='Bearer fake-token',
    )


def test_entregas_disponiveis_ok(api_client, cadeia_rit_pgd2, gate_rit_aberto):
    _mapear_dev(cadeia_rit_pgd2.servidor)
    response = api_client.get(
        f'{URL_ENTREGAS}?gitlab_username=dev.fulano',
        user=cadeia_rit_pgd2.servidor.get_user(),
        HTTP_AUTHORIZATION='Bearer fake-token',
    )
    assert response.status_code == 200, response.content
    ids = [e['id'] for e in response.json()['entregas']]
    assert cadeia_rit_pgd2.entrega_pit.id in ids


def test_entregas_disponiveis_username_inexistente_404(api_client, cadeia_rit_pgd2):
    response = api_client.get(
        f'{URL_ENTREGAS}?gitlab_username=nao.existe',
        user=cadeia_rit_pgd2.servidor.get_user(),
        HTTP_AUTHORIZATION='Bearer fake-token',
    )
    assert response.status_code == 404, response.content


def test_lancar_rit_upsert_cria_e_atualiza(api_client, cadeia_rit_pgd2, gate_rit_aberto, sem_calculo_pit):
    _mapear_dev(cadeia_rit_pgd2.servidor)
    user = cadeia_rit_pgd2.servidor.get_user()

    r1 = _lancar_rit(api_client, _payload(cadeia_rit_pgd2), user)
    assert r1.status_code == 200, r1.content
    rid = r1.json()['rit_id']
    assert r1.json()['criado'] is True

    r2 = _lancar_rit(api_client, _payload(cadeia_rit_pgd2, titulo='Título atualizado'), user)
    assert r2.status_code == 200, r2.content
    assert r2.json()['rit_id'] == rid  # mesmo (projeto, MR) => mesmo RIT
    assert r2.json()['criado'] is False
    assert RelatorioIndividualTrabalho.objects.filter(gitlab_project_id=42, gitlab_mr_iid=7).count() == 1


def test_lancar_rit_sem_mr_sempre_cria_e_nao_toca_no_rit_manual(api_client, cadeia_rit_pgd2, gate_rit_aberto, sem_calculo_pit):
    _mapear_dev(cadeia_rit_pgd2.servidor)
    user = cadeia_rit_pgd2.servidor.get_user()
    manual = RelatorioIndividualTrabalho.objects.create(
        entrega_pit=cadeia_rit_pgd2.entrega_pit, titulo='Lançado à mão', descricao='', tempo_executado=1
    )

    sem_mr = _payload(cadeia_rit_pgd2, gitlab_project_id=None, gitlab_mr_iid=None, titulo='Deploy da 4.0.5')
    r1 = _lancar_rit(api_client, sem_mr, user)
    r2 = _lancar_rit(api_client, sem_mr, user)

    assert r1.status_code == 200, r1.content
    assert r2.status_code == 200, r2.content
    assert r1.json()['criado'] is True
    assert r2.json()['criado'] is True
    assert r1.json()['gitlab_mr_iid'] is None
    assert len({manual.id, r1.json()['rit_id'], r2.json()['rit_id']}) == 3
    manual.refresh_from_db()
    assert manual.titulo == 'Lançado à mão'


def test_lancar_rit_mr_sem_projeto_422(api_client, cadeia_rit_pgd2, gate_rit_aberto):
    _mapear_dev(cadeia_rit_pgd2.servidor)
    response = _lancar_rit(api_client, _payload(cadeia_rit_pgd2, gitlab_project_id=None), cadeia_rit_pgd2.servidor.get_user())
    assert response.status_code == 422, response.content


def test_lancar_rit_audit_registra_servidor_como_autor(api_client, cadeia_rit_pgd2, gate_rit_aberto, sem_calculo_pit):
    # Trava a regressão do fix do threadlocal: sob TrustedAppAuth o autor da auditoria deve ser
    # o servidor dono do RIT, e não o usuário do app OAuth nem o anônimo.
    _mapear_dev(cadeia_rit_pgd2.servidor)
    servidor_user = cadeia_rit_pgd2.servidor.get_user()

    response = _lancar_rit(api_client, _payload(cadeia_rit_pgd2), servidor_user)
    assert response.status_code == 200, response.content

    reg = RegistroAcaoPlanoIndividualTrabalho.objects.filter(pit=cadeia_rit_pgd2.pit).latest('id')
    assert reg.user == servidor_user


def test_lancar_rit_entrega_de_outro_servidor_403(api_client, cadeia_rit_pgd2, servidor_b, gate_rit_aberto):
    _mapear_dev(servidor_b, username='outro.dev')
    response = _lancar_rit(api_client, _payload(cadeia_rit_pgd2, gitlab_username='outro.dev'), servidor_b.get_user())
    assert response.status_code == 403, response.content


def test_lancar_rit_mes_enviado_403(api_client, cadeia_rit_pgd2, monkeypatch):
    # gate nega (mês já enviado): força pode_cadastrar_entrega_rit -> False
    _mapear_dev(cadeia_rit_pgd2.servidor)
    monkeypatch.setattr(PlanoIndividualTrabalho, 'pode_cadastrar_entrega_rit', lambda self, *a, **k: False)
    response = _lancar_rit(api_client, _payload(cadeia_rit_pgd2), cadeia_rit_pgd2.servidor.get_user())
    assert response.status_code == 403, response.content


def test_rit_do_mr_ok(api_client, cadeia_rit_pgd2):
    rit = RelatorioIndividualTrabalho.objects.create(
        entrega_pit=cadeia_rit_pgd2.entrega_pit,
        titulo='Execução do MR !7',
        descricao='Trabalho entregue.',
        tempo_executado=3,
        gitlab_project_id=42,
        gitlab_mr_iid=7,
    )
    response = _rit_do_mr(api_client, 42, 7, cadeia_rit_pgd2.servidor.get_user())
    assert response.status_code == 200, response.content
    dados = response.json()
    assert dados['rit_id'] == rit.id
    assert dados['situacao_rit'] == cadeia_rit_pgd2.pit.situacao_rit
    assert dados['entrega_titulo'] == cadeia_rit_pgd2.entrega_pit.titulo
    assert str(dados['tempo_executado']) in ('3', '3.0', '3.00')


def test_rit_do_mr_inexistente_404(api_client, cadeia_rit_pgd2):
    response = _rit_do_mr(api_client, 99, 1, cadeia_rit_pgd2.servidor.get_user())
    assert response.status_code == 404, response.content


def _horas_pit(api_client, gitlab_username, user):
    return api_client.get(f'{URL_HORAS_PIT}?gitlab_username={gitlab_username}', user=user, HTTP_AUTHORIZATION='Bearer fake-token')


def test_horas_pit_mostra_previsto_executado_e_o_que_falta(api_client, cadeia_rit_pgd2, gate_rit_aberto):
    _mapear_dev(cadeia_rit_pgd2.servidor)
    PlanoIndividualTrabalho.objects.filter(pk=cadeia_rit_pgd2.pit.pk).update(tempo_previsto=Decimal('24'), tempo_executado_total=Decimal('15.45'))

    response = _horas_pit(api_client, 'dev.fulano', cadeia_rit_pgd2.servidor.get_user())

    assert response.status_code == 200, response.content
    pits = {p['pit_id']: p for p in response.json()['pits']}
    pit = pits[cadeia_rit_pgd2.pit.id]
    assert Decimal(str(pit['tempo_previsto'])) == Decimal('24')
    assert Decimal(str(pit['tempo_executado_total'])) == Decimal('15.45')
    assert Decimal(str(pit['tempo_restante'])) == Decimal('8.55')
    assert pit['periodo_titulo'] == cadeia_rit_pgd2.pit.periodo_pit_rit.titulo


def test_horas_pit_informa_o_percentual_de_teletrabalho_do_pit(api_client, cadeia_rit_pgd2, gate_rit_aberto):
    # A skill usa este valor como padrão do perc_executada_em_teletrabalho do RIT.
    _mapear_dev(cadeia_rit_pgd2.servidor)
    PlanoIndividualTrabalho.objects.filter(pk=cadeia_rit_pgd2.pit.pk).update(percentual_teletrabalho=60)

    response = _horas_pit(api_client, 'dev.fulano', cadeia_rit_pgd2.servidor.get_user())

    assert Decimal(str(response.json()['pits'][0]['percentual_teletrabalho'])) == Decimal('60')


def test_horas_pit_nao_fica_negativo_quando_passa_da_meta(api_client, cadeia_rit_pgd2, gate_rit_aberto):
    _mapear_dev(cadeia_rit_pgd2.servidor)
    PlanoIndividualTrabalho.objects.filter(pk=cadeia_rit_pgd2.pit.pk).update(tempo_previsto=Decimal('24'), tempo_executado_total=Decimal('30'))

    response = _horas_pit(api_client, 'dev.fulano', cadeia_rit_pgd2.servidor.get_user())

    pit = response.json()['pits'][0]
    assert Decimal(str(pit['tempo_restante'])) == Decimal('0')


def test_horas_pit_ignora_pit_fechado_para_rit(api_client, cadeia_rit_pgd2, monkeypatch):
    _mapear_dev(cadeia_rit_pgd2.servidor)
    monkeypatch.setattr(PlanoIndividualTrabalho, 'pode_cadastrar_entrega_rit', lambda self, *a, **k: False)

    response = _horas_pit(api_client, 'dev.fulano', cadeia_rit_pgd2.servidor.get_user())

    assert response.status_code == 200, response.content
    assert response.json()['pits'] == []


def test_horas_pit_username_inexistente_404(api_client, cadeia_rit_pgd2):
    response = _horas_pit(api_client, 'nao.existe', cadeia_rit_pgd2.servidor.get_user())
    assert response.status_code == 404, response.content
    assert 'nao.existe' in response.json()['message']
