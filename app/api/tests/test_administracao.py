import datetime
from types import SimpleNamespace

import pytest

from portaria.models import Acesso, ConfiguracaoSistemaPortaria
from protocolo.models import Processo as ProtocoloProcesso


@pytest.fixture
def dados_administracao(servidor_a, campus_a) -> SimpleNamespace:
    campus = campus_a

    ConfiguracaoSistemaPortaria.objects.get_or_create(senha='1', campus=campus)
    Acesso.objects.get_or_create(
        chave_wifi='1234567890',
        data_geracao_chave_wifi=datetime.datetime.now() + datetime.timedelta(days=1),
        quantidade_dias_chave_wifi=1,
        objetivo='Acesso à internet para fins acadêmicos e administrativos.',
        local_acesso=campus,
    )
    processo, _ = ProtocoloProcesso.objects.get_or_create(
        interessado_documento=servidor_a.pessoa_fisica.cpf,
        interessado_nome=servidor_a.pessoa_fisica.nome,
        vinculo_cadastro=servidor_a.get_vinculo(),
        uo=servidor_a.setor.uo,
        setor_origem=servidor_a.setor,
        assunto='Processo de Teste',
        tipo=ProtocoloProcesso.TIPO_REQUERIMENTO,
    )
    return SimpleNamespace(servidor_a=servidor_a, processo=processo)


class TestAdministracao:
    def test_processos_fisicos(self, api_client, dados_administracao):
        user = dados_administracao.servidor_a.get_user()
        response = api_client.get('/api/administracao/meus-processos-fisicos/', user=user).json()['results']
        assert len(response) == 1
        assert response[0]['assunto'] == 'Processo de Teste'

        detalhe = api_client.get(f'/api/administracao/meu-processo-fisico/{response[0]["id"]}/', user=user).json()
        assert detalhe['assunto'] == 'Processo de Teste'
        assert detalhe['tipo_processo'] == 'Requerimento'

    def test_acessos(self, api_client, dados_administracao):
        response = api_client.get('/api/administracao/validar-visitante-portaria/1234567890/').json()
        assert response['chave_wifi'] == '1234567890'

        response = api_client.get('/api/administracao/validar-visitante-portaria/9876543210/').json()
        assert response['detail'] == 'Not Found: No Acesso matches the given query.'
