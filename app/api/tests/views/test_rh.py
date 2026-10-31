import datetime
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import Permission

from comum.models import Ano, DocumentoControleTipo
from contracheques.models import ContraCheque, ContraChequeRubrica, Rubrica, TipoRubrica
from djtools.middleware import threadlocals as tl
from ferias.models import Ferias
from rh.models import (
    AfastamentoSiape,
    GrupoOcorrencia,
    Ocorrencia,
    ServidorAfastamento,
    ServidorOcorrencia,
    Setor,
    Situacao,
    UnidadeOrganizacional,
)


@pytest.fixture
def dados_rh(servidor_a, campus_a) -> SimpleNamespace:
    tl.context.user = None
    campus = campus_a

    situacao_ativo, _ = Situacao.objects.get_or_create(codigo='01', defaults={'nome': 'Ativo'})
    servidor_a.situacao = situacao_ativo
    servidor_a.save()

    servidor_a.pessoa_fisica.sexo = 'M'
    servidor_a.pessoa_fisica.pagto_agencia = '1234'
    servidor_a.pessoa_fisica.pagto_ccor = '56789'
    servidor_a.pessoa_fisica.save()

    # Garante sexo preenchido em todas as PessoaFisica (endpoints de listagem)
    from comum.models import PessoaFisica

    PessoaFisica.objects.update(sexo='M')

    ano_2024, _ = Ano.objects.get_or_create(ano=2024)
    ferias = Ferias.objects.create(
        servidor=servidor_a,
        ano=ano_2024,
        data_inicio_periodo1=datetime.date(2024, 1, 1),
        data_fim_periodo1=datetime.date(2024, 1, 30),
        validado=1,
    )

    setor = Setor.objects.create(nome='Setor Teste', sigla='ST')
    uo = UnidadeOrganizacional.objects.create(nome='UO Teste', sigla='UOT', setor=setor)

    contracheque = ContraCheque.objects.create(servidor=servidor_a, ano=ano_2024, mes=1, bruto=5000.00, liquido=4000.00, desconto=1000.00)

    tipo_rubrica, _ = TipoRubrica.objects.get_or_create(nome='Rendimento', codigo='R')
    rubrica, _ = Rubrica.objects.get_or_create(nome='Salário Base', codigo='SB')
    ContraChequeRubrica.objects.create(contra_cheque=contracheque, rubrica=rubrica, tipo=tipo_rubrica, valor=5000.00, prazo='00')

    grupo_ocorrencia = GrupoOcorrencia.objects.create(nome='Grupo Teste')
    ocorrencia = Ocorrencia.objects.create(nome='Ocorrencia Teste', grupo_ocorrencia=grupo_ocorrencia, codigo='OC1')
    afastamento = AfastamentoSiape.objects.create(nome='Afastamento Teste', codigo='AT', tipo=1)

    ServidorOcorrencia.objects.create(
        servidor=servidor_a, ocorrencia=ocorrencia, data=datetime.date(2024, 2, 1), data_termino=datetime.date(2024, 2, 5)
    )
    ServidorAfastamento.objects.create(
        servidor=servidor_a, afastamento=afastamento, data_inicio=datetime.date(2024, 3, 1), data_termino=datetime.date(2024, 3, 10)
    )

    DocumentoControleTipo.objects.get_or_create(identificador=DocumentoControleTipo.CARTEIRA_FUNCIONAL, defaults={'descricao': 'Carteira Funcional'})

    # Permissões que o antigo setUp adicionava a cada método
    servidor_a.get_user().user_permissions.add(
        Permission.objects.get(codename='pode_ver_contracheques_detalhados', content_type__app_label='contracheques'),
        Permission.objects.get(codename='pode_sincronizar_dados', content_type__app_label='edu'),
    )

    return SimpleNamespace(
        servidor_a=servidor_a,
        campus=campus,
        ferias=ferias,
        setor=setor,
        uo=uo,
        contracheque=contracheque,
        rubrica=rubrica,
        ocorrencia=ocorrencia,
        afastamento=afastamento,
    )


class TestRH:
    def test_meus_dados(self, api_client, dados_rh):
        user = dados_rh.servidor_a.get_user()
        response = api_client.get('/api/rh/meus-dados/', user=user)
        assert response.status_code == 200, f'Status: {response.status_code}, Content: {response.content}'
        assert response.json()['matricula'] == user.username

    def test_eu(self, api_client, dados_rh):
        response = api_client.get('/api/rh/eu/', user=dados_rh.servidor_a.get_user())
        assert response.status_code == 200, f'Status: {response.status_code}, Content: {response.content}'
        data = response.json()
        assert data['identificacao'] == dados_rh.servidor_a.matricula
        assert data['nome'] == dados_rh.servidor_a.pessoa_fisica.nome

    def test_servidores(self, api_client, dados_rh):
        response = api_client.get('/api/rh/servidores/', user=dados_rh.servidor_a.get_user())
        assert response.status_code == 200, f'Status: {response.status_code}, Content: {response.content}'
        matriculas = [s['matricula'] for s in response.json()['results']]
        assert dados_rh.servidor_a.matricula in matriculas

    def test_minhas_ferias(self, api_client, dados_rh):
        response = api_client.get('/api/rh/minhas-ferias/', user=dados_rh.servidor_a.get_user())
        assert response.status_code == 200, f'Status: {response.status_code}, Content: {response.content}'
        items = response.json()['results']
        assert len(items) == 1
        assert dados_rh.ferias.ano.ano in [f['ano'] for f in items]

    def test_uos(self, api_client, dados_rh):
        response = api_client.get('/api/rh/unidades-organizacionais/', user=dados_rh.servidor_a.get_user())
        assert response.status_code == 200, f'Status: {response.status_code}, Content: {response.content}'
        items = response.json()['results']
        assert len(items) >= 1
        assert dados_rh.uo.sigla in [uo['sigla'] for uo in items]

    def test_servidores_detalhado(self, api_client, dados_rh):
        response = api_client.get('/api/rh/servidores/detalhado/', user=dados_rh.servidor_a.get_user(), HTTP_AUTHORIZATION='Bearer fake-token')
        assert response.status_code == 200, f'Status: {response.status_code}, Content: {response.content}'
        matriculas = [s['matricula'] for s in response.json()['results']]
        assert dados_rh.servidor_a.matricula in matriculas

    def test_servidores_integra(self, api_client, dados_rh):
        response = api_client.get('/api/rh/servidores/integra/', user=dados_rh.servidor_a.get_user(), HTTP_AUTHORIZATION='Bearer fake-token')
        assert response.status_code == 200, f'Status: {response.status_code}, Content: {response.content}'
        cpfs = [s['cpf'] for s in response.json()]
        assert dados_rh.servidor_a.pessoa_fisica.cpf in cpfs

    def test_setores(self, api_client, dados_rh):
        response = api_client.get('/api/rh/setores/', user=dados_rh.servidor_a.get_user())
        assert response.status_code == 200, f'Status: {response.status_code}, Content: {response.content}'
        items = response.json()['results']
        assert dados_rh.setor.sigla in [s['sigla'] for s in items]
        dados_rh.setor.refresh_from_db()
        row = next(s for s in items if s['id'] == dados_rh.setor.pk)
        assert row['campus'] == {'id': dados_rh.uo.pk, 'sigla': dados_rh.uo.sigla, 'nome': dados_rh.uo.nome}

    def test_historico_funcional(self, api_client, dados_rh):
        response = api_client.get('/api/rh/meu-historico-funcional/', user=dados_rh.servidor_a.get_user())
        assert response.status_code == 200, f'Status: {response.status_code}, Content: {response.content}'

    def test_ocorrencias_afastamentos(self, api_client, dados_rh):
        response = api_client.get('/api/rh/minhas-ocorrencias-afastamentos/', user=dados_rh.servidor_a.get_user())
        assert response.status_code == 200, f'Status: {response.status_code}, Content: {response.content}'
        data = response.json()
        assert 'ocorrencias' in data
        assert 'afastamentos' in data
        assert dados_rh.ocorrencia.nome in [o['descricao'] for o in data['ocorrencias']]
        assert dados_rh.afastamento.nome in [a['descricao'] for a in data['afastamentos']]

    def test_carteira_funcional(self, api_client, dados_rh):
        response = api_client.get(f'/api/rh/emitir-carteira-funcional-digital/{dados_rh.servidor_a.matricula}/', user=dados_rh.servidor_a.get_user())
        # Pode retornar 400/404 se faltarem condições (foto, tipo sanguíneo); só garantimos que não estoura 500
        assert response.status_code != 500, f'Status: {response.status_code}, Content: {response.content}'

    def test_frequencias(self, api_client, dados_rh):
        response = api_client.get('/api/rh/minhas-frequencias/', user=dados_rh.servidor_a.get_user())
        assert response.status_code == 200, f'Status: {response.status_code}, Content: {response.content}'
        data = response.json()
        assert 'frequencias_hoje' in data
        assert 'total_tempo_hoje' in data
        assert 'total_tempo_semana' in data

    def test_servidor_resumido(self, api_client, dados_rh):
        response = api_client.get('/api/rh/servidor-resumido/', user=dados_rh.servidor_a.get_user())
        assert response.status_code == 200, f'Status: {response.status_code}, Content: {response.content}'
        data = response.json()
        assert data['matricula'] == dados_rh.servidor_a.matricula
        assert data['nome'] == dados_rh.servidor_a.pessoa_fisica.nome

    def test_meus_contracheques(self, api_client, dados_rh):
        response = api_client.get('/api/rh/meus-contracheques/', user=dados_rh.servidor_a.get_user())
        assert response.status_code == 200, f'Status: {response.status_code}, Content: {response.content}'
        items = response.json()['results']
        assert len(items) >= 1
        assert dados_rh.contracheque.ano.ano in [c['ano'] for c in items]

    def test_meu_contracheque_detalhe(self, api_client, dados_rh):
        cc = dados_rh.contracheque
        response = api_client.get(f'/api/rh/meu-contracheque/{cc.ano.ano}/{cc.mes}/', user=dados_rh.servidor_a.get_user())
        assert response.status_code == 200, f'Status: {response.status_code}, Content: {response.content}'
        data = response.json()
        assert data['ano'] == cc.ano.ano
        assert data['mes'] == cc.mes
        assert 'rendimentos' in data
        assert 'descontos' in data
        assert len(data['rendimentos']) >= 1
        assert data['rendimentos'][0]['descricao'] == dados_rh.rubrica.nome

    def test_contracheques_list(self, api_client, dados_rh):
        cc = dados_rh.contracheque
        response = api_client.get(f'/api/rh/contracheques/?ano={cc.ano.ano}&mes={cc.mes}', user=dados_rh.servidor_a.get_user())
        assert response.status_code == 200, f'Status: {response.status_code}, Content: {response.content}'
        items = response.json()['results']
        assert len(items) >= 1
        assert dados_rh.servidor_a.matricula in [c['matricula'] for c in items]


@pytest.mark.django_db
def test_meus_vinculos_do_estrangeiro_sao_os_do_par_passaporte_pais(api_client) -> None:
    """O mesmo número de passaporte de outro país é outra pessoa: os vínculos dela não aparecem."""
    from comum.models import Pais, Vinculo
    from comum.tests.factories import PrestadorServicoFactory
    from rh.enums import Nacionalidade
    from rh.tests.factories import PessoaFisicaFactory

    def estrangeiro(pais: Pais) -> Vinculo:
        pessoa = PessoaFisicaFactory(cpf=None, passaporte='AB123456', pais_origem=pais, nacionalidade=Nacionalidade.ESTRANGEIRO)
        return PrestadorServicoFactory(pessoa_fisica=pessoa).get_vinculo()

    argentino = estrangeiro(Pais.objects.create(codigo='011', nome='ARGENTINA', iso_alfa3='ARG'))
    estrangeiro(Pais.objects.create(codigo='158', nome='CHILE', iso_alfa3='CHL'))

    response = api_client.get('/api/rh/meus-vinculos/', user=argentino.user)

    assert response.status_code == 200
    assert [vinculo['id'] for vinculo in response.json()['results']] == [argentino.pk]
