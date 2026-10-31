"""Testes do serviço de importação de vacinas do RN+Vacina.

A chamada HTTP real (ApiRNMaisVacinaService.consultar_imunizacoes) é sempre mockada — os testes
não devem bater na rede.
"""

import importlib
from unittest.mock import MagicMock, patch

import pytest
from django.apps import apps
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management import CommandError, call_command
from requests.exceptions import RequestException

from comum.models import APIExterna
from rh.tests.factories import ServidorFactory
from saude.models import CartaoVacinal, HistoricoImportacaoRNVacina, Prontuario, Vacina
from saude.services.importacao_rnvacina import _registrar_historico, importar_vacinas_rnvacina, parse_numero_dose, resolver_vacina_por_nome_rnvacina
from saude.services.rnvacina import ApiRNMaisVacinaService

NOME_VACINA_API = 'Vacina Covid-19-inativada, Sinovac/Butantan (Coronavac)'
DADOS_API_EXEMPLO = [
    {'data_aplicacao': '2021-04-17', 'vacina': NOME_VACINA_API, 'fabricante': 'INSTITUTO BUTANTAN', 'dose': '2ª Dose'},
    {'data_aplicacao': '2021-03-26', 'vacina': NOME_VACINA_API, 'fabricante': 'INSTITUTO BUTANTAN', 'dose': '1ª Dose'},
]


@pytest.mark.parametrize(
    ('dose_str', 'esperado'),
    [
        ('1ª Dose', (1, False)),
        ('2ª Dose', (2, False)),
        ('Reforço', (1, True)),
        ('1º Reforço', (1, True)),
        ('2º Reforço', (2, True)),
        ('3ª Dose (Reforço)', (3, True)),
        ('Única', (1, False)),
        ('Valor desconhecido', (None, False)),
        ('', (None, False)),
        (None, (None, False)),
    ],
)
def test_parse_numero_dose(dose_str, esperado):
    assert parse_numero_dose(dose_str) == esperado


def test_resolver_vacina_por_nome_rnvacina_normaliza_case_e_espacos(db):
    vacina = Vacina.objects.create(nome='Covid-19', doses=2, nome_rnmaisvacina=NOME_VACINA_API)
    assert resolver_vacina_por_nome_rnvacina(f'  {NOME_VACINA_API.upper()}  ') == vacina


def test_resolver_vacina_por_nome_rnvacina_sem_correspondencia(db):
    assert resolver_vacina_por_nome_rnvacina(NOME_VACINA_API) is None


@patch('saude.services.importacao_rnvacina.ApiRNMaisVacinaService')
def test_importar_vacinas_cria_doses_novas_marcadas_como_externas(mock_service_cls, prontuario, servidor_profissional):
    Vacina.objects.create(nome='Covid-19', doses=2, eh_covid=True, nome_rnmaisvacina=NOME_VACINA_API)
    mock_service_cls.return_value.consultar_imunizacoes.return_value = DADOS_API_EXEMPLO
    vinculo = servidor_profissional.get_vinculo()

    resultado = importar_vacinas_rnvacina(prontuario, vinculo, HistoricoImportacaoRNVacina.ORIGEM_PROFISSIONAL)

    assert resultado.quantidade_importada == 2
    doses = CartaoVacinal.objects.filter(prontuario=prontuario)
    assert doses.count() == 2
    assert all(dose.externo for dose in doses)
    historico = HistoricoImportacaoRNVacina.objects.get(prontuario=prontuario)
    assert historico.sucesso is True
    assert historico.quantidade_importada == 2


@patch('saude.services.importacao_rnvacina.ApiRNMaisVacinaService')
def test_importar_vacinas_distingue_reforcos_multiplos(mock_service_cls, prontuario, servidor_profissional):
    """1º e 2º reforço vindos da importação devem virar registros distintos, não colidir."""
    Vacina.objects.create(nome='Covid-19', doses=2, nome_rnmaisvacina=NOME_VACINA_API)
    mock_service_cls.return_value.consultar_imunizacoes.return_value = [
        {'data_aplicacao': '2022-06-01', 'vacina': NOME_VACINA_API, 'fabricante': 'INSTITUTO BUTANTAN', 'dose': '1º Reforço'},
        {'data_aplicacao': '2023-01-10', 'vacina': NOME_VACINA_API, 'fabricante': 'INSTITUTO BUTANTAN', 'dose': '2º Reforço'},
    ]
    vinculo = servidor_profissional.get_vinculo()

    resultado = importar_vacinas_rnvacina(prontuario, vinculo, HistoricoImportacaoRNVacina.ORIGEM_PROFISSIONAL)

    assert resultado.quantidade_importada == 2
    reforcos = CartaoVacinal.objects.filter(prontuario=prontuario, eh_reforco=True).order_by('numero_dose')
    assert [r.numero_dose for r in reforcos] == [1, 2]
    assert reforcos[0].get_numero_dose() == 'Reforço'
    assert reforcos[1].get_numero_dose() == '2º Reforço'


@patch('saude.services.importacao_rnvacina.ApiRNMaisVacinaService')
def test_importar_vacinas_nao_colide_reforco_explicito_com_dose_reforco_ambigua(mock_service_cls, prontuario, servidor_profissional):
    """ "1º Reforço" e "3ª Dose (Reforço)" não podem cair na mesma chave e uma apagar a outra."""
    Vacina.objects.create(nome='Covid-19', doses=2, nome_rnmaisvacina=NOME_VACINA_API)
    mock_service_cls.return_value.consultar_imunizacoes.return_value = [
        {'data_aplicacao': '2022-06-01', 'vacina': NOME_VACINA_API, 'fabricante': 'INSTITUTO BUTANTAN', 'dose': '1º Reforço'},
        {'data_aplicacao': '2023-06-01', 'vacina': NOME_VACINA_API, 'fabricante': 'INSTITUTO BUTANTAN', 'dose': '3ª Dose (Reforço)'},
    ]
    vinculo = servidor_profissional.get_vinculo()

    resultado = importar_vacinas_rnvacina(prontuario, vinculo, HistoricoImportacaoRNVacina.ORIGEM_PROFISSIONAL)

    assert resultado.quantidade_importada == 2
    reforcos = CartaoVacinal.objects.filter(prontuario=prontuario, eh_reforco=True).order_by('numero_dose')
    assert [r.numero_dose for r in reforcos] == [1, 3]


@patch('saude.services.importacao_rnvacina.ApiRNMaisVacinaService')
def test_importar_vacinas_nao_duplica_dose_ja_existente(mock_service_cls, prontuario, servidor_profissional):
    vacina = Vacina.objects.create(nome='Covid-19', doses=2, nome_rnmaisvacina=NOME_VACINA_API)
    CartaoVacinal.objects.create(prontuario=prontuario, vacina=vacina, numero_dose=1, data_vacinacao='2021-03-26')
    mock_service_cls.return_value.consultar_imunizacoes.return_value = DADOS_API_EXEMPLO
    vinculo = servidor_profissional.get_vinculo()

    resultado = importar_vacinas_rnvacina(prontuario, vinculo, HistoricoImportacaoRNVacina.ORIGEM_PROFISSIONAL)

    assert resultado.quantidade_importada == 1
    assert resultado.quantidade_existentes == 1
    assert CartaoVacinal.objects.filter(prontuario=prontuario).count() == 2


@patch('saude.services.importacao_rnvacina.ApiRNMaisVacinaService')
def test_importar_vacinas_nao_duplica_dose_com_mesma_data_e_numeracao_diferente(mock_service_cls, prontuario, servidor_profissional):
    """Dose cadastrada manualmente como 1ª em 2021-04-17 é a mesma aplicação que a API chama de "2ª Dose"."""
    vacina = Vacina.objects.create(nome='Covid-19', doses=2, nome_rnmaisvacina=NOME_VACINA_API)
    CartaoVacinal.objects.create(prontuario=prontuario, vacina=vacina, numero_dose=1, data_vacinacao='2021-04-17')
    mock_service_cls.return_value.consultar_imunizacoes.return_value = [
        {'data_aplicacao': '2021-04-17', 'vacina': NOME_VACINA_API, 'fabricante': 'INSTITUTO BUTANTAN', 'dose': '2ª Dose'},
    ]
    vinculo = servidor_profissional.get_vinculo()

    resultado = importar_vacinas_rnvacina(prontuario, vinculo, HistoricoImportacaoRNVacina.ORIGEM_PROFISSIONAL)

    assert resultado.quantidade_importada == 0
    assert resultado.quantidade_existentes == 1
    assert CartaoVacinal.objects.filter(prontuario=prontuario).count() == 1


@patch('saude.services.importacao_rnvacina.ApiRNMaisVacinaService')
def test_importar_vacinas_nao_duplica_reforco_legado_com_mesma_data(mock_service_cls, prontuario, servidor_profissional):
    """Reforço legado (numero_dose=0, migrado para reforço 1) não pode ser duplicado por "3ª Dose (Reforço)" da mesma data."""
    vacina = Vacina.objects.create(nome='Covid-19', doses=2, nome_rnmaisvacina=NOME_VACINA_API)
    CartaoVacinal.objects.create(prontuario=prontuario, vacina=vacina, eh_reforco=True, numero_dose=1, data_vacinacao='2022-01-17')
    mock_service_cls.return_value.consultar_imunizacoes.return_value = [
        {'data_aplicacao': '2022-01-17', 'vacina': NOME_VACINA_API, 'fabricante': 'INSTITUTO BUTANTAN', 'dose': '3ª Dose (Reforço)'},
    ]
    vinculo = servidor_profissional.get_vinculo()

    resultado = importar_vacinas_rnvacina(prontuario, vinculo, HistoricoImportacaoRNVacina.ORIGEM_PROFISSIONAL)

    assert resultado.quantidade_importada == 0
    assert resultado.quantidade_existentes == 1
    assert CartaoVacinal.objects.filter(prontuario=prontuario, eh_reforco=True).count() == 1


@patch('saude.services.importacao_rnvacina.ApiRNMaisVacinaService')
def test_importar_vacinas_importa_dose_da_mesma_vacina_em_data_diferente(mock_service_cls, prontuario, servidor_profissional):
    """A deduplicação por data não pode descartar uma aplicação real em outra data."""
    vacina = Vacina.objects.create(nome='Covid-19', doses=2, nome_rnmaisvacina=NOME_VACINA_API)
    CartaoVacinal.objects.create(prontuario=prontuario, vacina=vacina, numero_dose=1, data_vacinacao='2021-03-26')
    mock_service_cls.return_value.consultar_imunizacoes.return_value = [
        {'data_aplicacao': '2022-01-17', 'vacina': NOME_VACINA_API, 'fabricante': 'INSTITUTO BUTANTAN', 'dose': 'Reforço'},
    ]
    vinculo = servidor_profissional.get_vinculo()

    resultado = importar_vacinas_rnvacina(prontuario, vinculo, HistoricoImportacaoRNVacina.ORIGEM_PROFISSIONAL)

    assert resultado.quantidade_importada == 1
    assert CartaoVacinal.objects.filter(prontuario=prontuario, vacina=vacina, data_vacinacao='2022-01-17', eh_reforco=True).exists()


@patch('saude.services.importacao_rnvacina.ApiRNMaisVacinaService')
def test_importar_vacinas_reconcilia_aprazamento_manual_pendente(mock_service_cls, prontuario, servidor_profissional):
    """Uma dose cadastrada manualmente (aprazamento, sem data de aplicação) deve ser atualizada
    pela importação em vez de gerar um registro duplicado."""
    vacina = Vacina.objects.create(nome='Covid-19', doses=2, nome_rnmaisvacina=NOME_VACINA_API)
    aprazamento_manual = CartaoVacinal.objects.create(
        prontuario=prontuario, vacina=vacina, numero_dose=1, data_prevista='2021-03-20', obs='Aprazamento manual'
    )
    mock_service_cls.return_value.consultar_imunizacoes.return_value = DADOS_API_EXEMPLO
    vinculo = servidor_profissional.get_vinculo()

    resultado = importar_vacinas_rnvacina(prontuario, vinculo, HistoricoImportacaoRNVacina.ORIGEM_PROFISSIONAL)

    assert resultado.quantidade_importada == 2
    assert resultado.quantidade_existentes == 0
    assert CartaoVacinal.objects.filter(prontuario=prontuario, vacina=vacina).count() == 2
    aprazamento_manual.refresh_from_db()
    assert aprazamento_manual.data_vacinacao.isoformat() == '2021-03-26'
    assert aprazamento_manual.externo is True


@patch('saude.services.importacao_rnvacina.ApiRNMaisVacinaService')
def test_importar_vacinas_cadastra_automaticamente_vacina_sem_mapeamento(mock_service_cls, prontuario, servidor_profissional):
    mock_service_cls.return_value.consultar_imunizacoes.return_value = DADOS_API_EXEMPLO
    vinculo = servidor_profissional.get_vinculo()

    resultado = importar_vacinas_rnvacina(prontuario, vinculo, HistoricoImportacaoRNVacina.ORIGEM_PROFISSIONAL)

    assert resultado.quantidade_importada == 2
    assert resultado.nomes_vacinas_cadastradas == [NOME_VACINA_API]
    vacina_criada = Vacina.objects.get(nome_rnmaisvacina=NOME_VACINA_API)
    assert vacina_criada.nome == NOME_VACINA_API
    assert vacina_criada.doses == 1
    assert CartaoVacinal.objects.filter(prontuario=prontuario, vacina=vacina_criada).count() == 2


@patch('saude.services.importacao_rnvacina.ApiRNMaisVacinaService')
def test_importar_vacinas_reaproveita_vacina_cadastrada_automaticamente_em_importacao_anterior(mock_service_cls, prontuario, servidor_profissional):
    mock_service_cls.return_value.consultar_imunizacoes.return_value = DADOS_API_EXEMPLO
    vinculo = servidor_profissional.get_vinculo()
    importar_vacinas_rnvacina(prontuario, vinculo, HistoricoImportacaoRNVacina.ORIGEM_PROFISSIONAL)
    assert Vacina.objects.filter(nome_rnmaisvacina=NOME_VACINA_API).count() == 1

    outro_prontuario = Prontuario.objects.create(vinculo=ServidorFactory().get_vinculo())
    resultado = importar_vacinas_rnvacina(outro_prontuario, vinculo, HistoricoImportacaoRNVacina.ORIGEM_PROFISSIONAL)

    assert resultado.nomes_vacinas_cadastradas == []
    assert Vacina.objects.filter(nome_rnmaisvacina=NOME_VACINA_API).count() == 1


@patch('saude.services.importacao_rnvacina.ApiRNMaisVacinaService')
def test_importar_vacinas_ignora_item_com_dose_nao_reconhecida(mock_service_cls, prontuario, servidor_profissional):
    mock_service_cls.return_value.consultar_imunizacoes.return_value = [
        {'data_aplicacao': '2021-04-17', 'vacina': NOME_VACINA_API, 'fabricante': 'INSTITUTO BUTANTAN', 'dose': 'Dose não identificada'}
    ]
    vinculo = servidor_profissional.get_vinculo()

    resultado = importar_vacinas_rnvacina(prontuario, vinculo, HistoricoImportacaoRNVacina.ORIGEM_PROFISSIONAL)

    assert resultado.quantidade_importada == 0
    assert resultado.quantidade_nao_mapeadas == 1
    assert resultado.nomes_nao_mapeados == [NOME_VACINA_API]
    assert not Vacina.objects.filter(nome_rnmaisvacina=NOME_VACINA_API).exists()
    assert not CartaoVacinal.objects.filter(prontuario=prontuario).exists()


@patch('saude.services.importacao_rnvacina.ApiRNMaisVacinaService')
def test_importar_vacinas_permite_mais_de_uma_importacao_no_mesmo_dia(mock_service_cls, prontuario, servidor_profissional):
    mock_service_cls.return_value.consultar_imunizacoes.return_value = []
    vinculo = servidor_profissional.get_vinculo()

    importar_vacinas_rnvacina(prontuario, vinculo, HistoricoImportacaoRNVacina.ORIGEM_PROFISSIONAL)
    importar_vacinas_rnvacina(prontuario, vinculo, HistoricoImportacaoRNVacina.ORIGEM_PROFISSIONAL)

    assert mock_service_cls.return_value.consultar_imunizacoes.call_count == 2
    assert HistoricoImportacaoRNVacina.objects.filter(prontuario=prontuario).count() == 2


@patch('saude.services.importacao_rnvacina.ApiRNMaisVacinaService')
def test_view_importacao_profissional_importa_e_exibe_resultado(mock_service_cls, profissional, prontuario):
    Vacina.objects.create(nome='Covid-19', doses=2, nome_rnmaisvacina=NOME_VACINA_API)
    mock_service_cls.return_value.consultar_imunizacoes.return_value = DADOS_API_EXEMPLO

    response = profissional.get(f'/saude/importar_vacinas_rnvacina_profissional/{prontuario.id}/', follow=True)

    assert response.status_code == 200
    assert HistoricoImportacaoRNVacina.objects.filter(prontuario=prontuario, origem=HistoricoImportacaoRNVacina.ORIGEM_PROFISSIONAL).exists()


def test_view_importacao_profissional_requer_grupo_saude(suap_client, sync_permissions, prontuario):
    # servidor sem grupo de saúde: é o que deve levar ao 403.
    suap_client.login(user=ServidorFactory().get_user())

    response = suap_client.get(f'/saude/importar_vacinas_rnvacina_profissional/{prontuario.id}/')

    assert response.status_code == 403


@patch('saude.services.importacao_rnvacina.ApiRNMaisVacinaService')
def test_view_importacao_autoatendimento_importa_proprio_vinculo(mock_service_cls, db, suap_client, sync_permissions):
    servidor = ServidorFactory()
    user = servidor.get_user()
    user.groups.add(Group.objects.get(name='Aluno'))
    suap_client.login(user=user)
    mock_service_cls.return_value.consultar_imunizacoes.return_value = []

    response = suap_client.get('/saude/importar_vacinas_rnvacina_autoatendimento/', follow=True)

    assert response.status_code == 200
    prontuario_servidor = Prontuario.get_prontuario(servidor.get_vinculo())
    assert HistoricoImportacaoRNVacina.objects.filter(
        prontuario=prontuario_servidor, origem=HistoricoImportacaoRNVacina.ORIGEM_AUTOATENDIMENTO
    ).exists()


def test_importador_antigo_desativado():
    with pytest.raises(CommandError):
        call_command('importar_dados_rnmaisvacina')


def test_importador_lote_antigo_desativado():
    with pytest.raises(CommandError):
        call_command('importar_passaportes_vacinais')


def test_importador_pendentes_antigo_desativado():
    with pytest.raises(CommandError):
        call_command('atualiza_passaportes_vacinais_pendentes')


@patch('saude.services.rnvacina.requests.post')
@patch('saude.services.rnvacina.requests.get')
def test_consultar_imunizacoes_reautentica_apos_401(mock_get, mock_post, db):
    APIExterna.objects.update_or_create(
        nome='RNMAISVACINA',
        defaults={
            'ativo': True,
            'tipo_autenticacao': APIExterna.CPF_AUTH,
            'url_base': 'https://rnmaisvacina.lais.ufrn.br/api/v1/',
            'url_token': 'https://rnmaisvacina.lais.ufrn.br/api/v1/token/',
            'client_id': 'usuario_teste',
            'secret': 'senha_teste',
        },
    )
    mock_post.return_value = MagicMock(ok=True, json=lambda: {'access': 'token'})
    resposta_401 = MagicMock(ok=False, status_code=401, text='não autorizado')
    resposta_200 = MagicMock(ok=True, status_code=200, json=lambda: {'status': 'sucesso', 'dados': []})
    mock_get.side_effect = [resposta_401, resposta_200]

    resultado = ApiRNMaisVacinaService().consultar_imunizacoes('07371666496')

    assert resultado == []
    assert mock_get.call_count == 2
    assert mock_post.call_count == 2


@patch('saude.services.rnvacina.requests.post')
@patch('saude.services.rnvacina.requests.get')
def test_consultar_imunizacoes_reautentica_apos_403(mock_get, mock_post, db):
    """O RN+Vacina sinaliza token expirado/invalidado com 403 (não só 401): visto em produção,
    a mesma consulta falhando com 403 e depois funcionando normalmente para o mesmo CPF."""
    cache.clear()  # evita reaproveitar o token cacheado por um teste anterior (mesma cache_name)
    APIExterna.objects.update_or_create(
        nome='RNMAISVACINA',
        defaults={
            'ativo': True,
            'tipo_autenticacao': APIExterna.CPF_AUTH,
            'url_base': 'https://rnmaisvacina.lais.ufrn.br/api/v1/',
            'url_token': 'https://rnmaisvacina.lais.ufrn.br/api/v1/token/',
            'client_id': 'usuario_teste',
            'secret': 'senha_teste',
        },
    )
    mock_post.return_value = MagicMock(ok=True, json=lambda: {'access': 'token'})
    resposta_403 = MagicMock(ok=False, status_code=403, text='{"detail":"Você não tem permissão para executar essa ação."}')
    resposta_200 = MagicMock(ok=True, status_code=200, json=lambda: {'status': 'sucesso', 'dados': []})
    mock_get.side_effect = [resposta_403, resposta_200]

    resultado = ApiRNMaisVacinaService().consultar_imunizacoes('07371666496')

    assert resultado == []
    assert mock_get.call_count == 2
    assert mock_post.call_count == 2


@patch('saude.services.rnvacina.requests.post')
@patch('saude.services.rnvacina.requests.get')
def test_consultar_imunizacoes_renova_via_refresh_token_sem_logar_de_novo(mock_get, mock_post, db):
    """Com um refresh token em cache, a renovação do access token deve usar /token/refresh/ em vez
    de repetir o login usuário/senha — login completo repetido é o suspeito de invalidar sessões
    concorrentes no RN+Vacina (ver cpf_auth_token)."""
    cache.clear()
    APIExterna.objects.update_or_create(
        nome='RNMAISVACINA',
        defaults={
            'ativo': True,
            'tipo_autenticacao': APIExterna.CPF_AUTH,
            'url_base': 'https://rnmaisvacina.lais.ufrn.br/api/v1/',
            'url_token': 'https://rnmaisvacina.lais.ufrn.br/api/v1/token/',
            'client_id': 'usuario_teste',
            'secret': 'senha_teste',
        },
    )
    servico = ApiRNMaisVacinaService()
    cache.set(servico.refresh_cache_name, 'refresh-existente', 3600)
    mock_post.return_value = MagicMock(ok=True, json=lambda: {'access': 'token-renovado'})
    mock_get.return_value = MagicMock(ok=True, status_code=200, json=lambda: {'status': 'sucesso', 'dados': []})

    resultado = servico.consultar_imunizacoes('07371666496')

    assert resultado == []
    mock_post.assert_called_once()
    assert mock_post.call_args.args[0] == 'https://rnmaisvacina.lais.ufrn.br/api/v1/token/refresh/'
    assert cache.get(servico.cache_name) == 'token-renovado'


@patch('saude.services.rnvacina.requests.post')
@patch('saude.services.rnvacina.requests.get')
def test_consultar_imunizacoes_usa_verbosity_false_por_padrao(mock_get, mock_post, db):
    """verbosity=True vazaria a senha (POST {'password': ...}) e os dados de saúde da resposta
    para o log (djtools.utils.requests) — o padrão precisa ser False."""
    APIExterna.objects.update_or_create(
        nome='RNMAISVACINA',
        defaults={
            'ativo': True,
            'tipo_autenticacao': APIExterna.CPF_AUTH,
            'url_base': 'https://rnmaisvacina.lais.ufrn.br/api/v1/',
            'url_token': 'https://rnmaisvacina.lais.ufrn.br/api/v1/token/',
            'client_id': 'usuario_teste',
            'secret': 'senha_teste',
        },
    )
    mock_post.return_value = MagicMock(ok=True, json=lambda: {'access': 'token'})
    mock_get.return_value = MagicMock(ok=True, status_code=200, json=lambda: {'status': 'sucesso', 'dados': []})
    # O token fica em cache (chave por nome da API) e persiste entre testes no mesmo processo;
    # sem limpar, um teste anterior que já autenticou faria o POST de token nem ser chamado aqui.
    cache.clear()

    ApiRNMaisVacinaService().consultar_imunizacoes('07371666496')

    assert mock_post.call_args.kwargs['verbosity'] is False
    assert mock_get.call_args.kwargs['verbosity'] is False


def test_migration_0037_reversao_nao_zera_reforcos_criados_depois(prontuario):
    """A reversa da migration 0037 deve mexer só nos registros que o forward tocou
    (eh_reforco=True, numero_dose=1), sem zerar um 2º reforço criado depois dela."""
    vacina = Vacina.objects.create(nome='Covid-19 (teste migration)', doses=2)
    primeiro_reforco = CartaoVacinal.objects.create(prontuario=prontuario, vacina=vacina, eh_reforco=True, numero_dose=1)
    segundo_reforco = CartaoVacinal.objects.create(prontuario=prontuario, vacina=vacina, eh_reforco=True, numero_dose=2)

    modulo = importlib.import_module('saude.migrations.0037_adiciona_eh_reforco_cartaovacinal')
    modulo.reverter_reforcos_legados(apps, None)

    primeiro_reforco.refresh_from_db()
    segundo_reforco.refresh_from_db()
    assert primeiro_reforco.numero_dose == 0
    assert segundo_reforco.numero_dose == 2


def _configurar_api_token_simples():
    # TOKEN_AUTH não exige POST de autenticação (get_token retorna o secret direto), então basta
    # mockar o GET para testar shape/erro da resposta de imunizações.
    return APIExterna.objects.update_or_create(
        nome='RNMAISVACINA',
        defaults={
            'ativo': True,
            'tipo_autenticacao': APIExterna.TOKEN_AUTH,
            'url_base': 'https://rnmaisvacina.lais.ufrn.br/api/v1/',
            'secret': 'token-fixo',
        },
    )[0]


def test_consultar_imunizacoes_recusa_quando_api_externa_inativa(db):
    api_externa = _configurar_api_token_simples()
    api_externa.ativo = False
    api_externa.save(update_fields=['ativo'])

    with pytest.raises(ValidationError):
        ApiRNMaisVacinaService().consultar_imunizacoes('07371666496')


@patch('saude.services.rnvacina.requests.get')
def test_consultar_imunizacoes_recusa_payload_que_nao_e_dict(mock_get, db):
    _configurar_api_token_simples()
    mock_get.return_value = MagicMock(ok=True, status_code=200, json=lambda: ['lista', 'nao', 'dict'])

    with pytest.raises(ValidationError):
        ApiRNMaisVacinaService().consultar_imunizacoes('07371666496')


@patch('saude.services.rnvacina.requests.get')
def test_consultar_imunizacoes_recusa_dados_que_nao_e_lista(mock_get, db):
    _configurar_api_token_simples()
    mock_get.return_value = MagicMock(ok=True, status_code=200, json=lambda: {'status': 'sucesso', 'dados': {'nao': 'lista'}})

    with pytest.raises(ValidationError):
        ApiRNMaisVacinaService().consultar_imunizacoes('07371666496')


@patch('saude.services.rnvacina.requests.get')
def test_consultar_imunizacoes_traduz_erro_de_rede_em_validation_error(mock_get, db):
    _configurar_api_token_simples()
    mock_get.side_effect = RequestException('falha de conexão')

    with pytest.raises(ValidationError):
        ApiRNMaisVacinaService().consultar_imunizacoes('07371666496')


@patch('saude.services.rnvacina.requests.get')
def test_consultar_imunizacoes_traduz_json_invalido_em_validation_error(mock_get, db):
    _configurar_api_token_simples()
    mock_get.return_value = MagicMock(ok=True, status_code=200, json=MagicMock(side_effect=ValueError('resposta não é JSON')))

    with pytest.raises(ValidationError):
        ApiRNMaisVacinaService().consultar_imunizacoes('07371666496')


def test_registrar_historico_trunca_mensagem_maior_que_max_length(prontuario, servidor_profissional):
    vinculo = servidor_profissional.get_vinculo()
    tamanho_maximo = HistoricoImportacaoRNVacina._meta.get_field('mensagem').max_length
    mensagem_longa = 'x' * (tamanho_maximo + 100)

    _registrar_historico(prontuario, vinculo, HistoricoImportacaoRNVacina.ORIGEM_PROFISSIONAL, True, 0, mensagem_longa)

    historico = HistoricoImportacaoRNVacina.objects.get(prontuario=prontuario)
    assert len(historico.mensagem) == tamanho_maximo
    assert historico.mensagem.endswith('…')


def test_view_importacao_profissional_sem_vinculo_nao_estoura_integrity_error(profissional, prontuario):
    with patch('comum.models.User.get_vinculo', return_value=None):
        response = profissional.get(f'/saude/importar_vacinas_rnvacina_profissional/{prontuario.id}/')

    assert response.status_code == 302
    assert not HistoricoImportacaoRNVacina.objects.filter(prontuario=prontuario).exists()


def test_view_importacao_autoatendimento_sem_vinculo_nao_estoura_integrity_error(db, suap_client, sync_permissions):
    user = ServidorFactory().get_user()
    user.groups.add(Group.objects.get(name='Aluno'))
    suap_client.login(user=user)

    with patch('comum.models.User.get_vinculo', return_value=None):
        response = suap_client.get('/saude/importar_vacinas_rnvacina_autoatendimento/')

    assert response.status_code == 302
    assert not HistoricoImportacaoRNVacina.objects.exists()
