from __future__ import annotations

import base64
import io
from datetime import datetime
from types import SimpleNamespace

import pytest
from django.contrib.messages.storage.cookie import CookieStorage
from django.test import RequestFactory
from django.urls import get_resolver
from freezegun import freeze_time
from openpyxl import Workbook

from catalogo_provedor_servico.models import Servico, Solicitacao, SolicitacaoEtapa, SolicitacaoEtapaArquivo
from catalogo_provedor_servico.providers.impl.default import solicitar_visita
from catalogo_provedor_servico.providers.base import Etapa
from catalogo_provedor_servico.providers.impl.default.solicitar_visita import SolicitarVisitaServiceProvider
from comum.models import Configuracao, PrestadorServico
from comum.tests.factories import PrestadorServicoFactory, SalaFactory, UserFactory
from djtools.middleware import threadlocals
from djtools.utils import cpf_valido, mask_cpf
from portaria.models import SolicitacaoEntrada
from rh.tests.factories import PessoaFisicaFactory

CPF = '12345678909'
ID_SERVICO_GOVBR = 987654

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _relogio_antes_das_datas_dos_testes() -> object:
    """Fixa "hoje" antes das datas de 2030 usadas aqui: a etapa 2 recusa entrada no passado e o teste não pode depender do relógio."""
    # Importa ``suap/urls.py`` antes do freeze: sob ``FakeDate`` o django-ninja quebra o import de ``suap/api.py``
    # (``ConfigError: Router@'' has already been attached``; ver ``djtools.e2e_fixtures.aquecer_urlconf``).
    assert get_resolver().url_patterns
    with freeze_time('2030-02-01 08:00:00'):
        yield


class _ApiPessoaFisicaFalsa:
    """Fronteira externa (API de pessoa física): devolve os dados do cidadão sem rede."""

    ativo = True

    def get_service(self) -> _ApiPessoaFisicaFalsa:
        return self

    def get_dados_pessoais(self, cpf: str) -> tuple[bool, list[dict[str, object]]]:
        return True, [{'CPF': cpf, 'Nome': 'Visitante Teste', 'Sexo': 1, 'DataNascimento': '19900101'}]


@pytest.fixture
def fronteiras_externas(monkeypatch: pytest.MonkeyPatch) -> None:
    """Corta só o que sai do SUAP: API de pessoa física, gov.br (acompanhamento/avaliação) e notificação."""

    class _APIExterna:
        PESSOAFISICA = _ApiPessoaFisicaFalsa()

    monkeypatch.setattr(solicitar_visita, 'APIExterna', _APIExterna)
    for nome in ('registrar_acompanhamento', 'registrar_conclusao', 'obter_formulario_avaliacao'):
        monkeypatch.setattr(SolicitarVisitaServiceProvider, nome, lambda *a, **k: None)
    monkeypatch.setattr(solicitar_visita.Notificar, 'notifica_conclusao_servico_atendido', lambda *a, **k: None)


def _montar_solicitacao(provider: SolicitarVisitaServiceProvider, campus_id: int) -> Solicitacao:
    # A factory de providers resolve o serviço de visita pelo código configurado.
    Configuracao.objects.create(app='catalogo_provedor_servico', chave='codigo_solicitacao_visita', valor=str(ID_SERVICO_GOVBR))
    Configuracao.clear_cache()
    servico = Servico.objects.create(id_servico_portal_govbr=ID_SERVICO_GOVBR, icone='fa fa-user', titulo='Solicitar Visita', ativo=True)
    solicitacao = Solicitacao.objects.create(servico=servico, cpf=CPF, nome='Solicitante', numero_total_etapas=2)

    etapa_1 = provider._get_etapa_1(CPF)
    etapa_1.formulario.set_value('nome', 'Solicitante')
    etapa_1.formulario.set_value('cpf', CPF)
    etapa_1.formulario.set_value('email', 'solicitante@example.com')
    etapa_1.formulario.set_value('telefone', '(84) 99999-9999')
    SolicitacaoEtapa.update_or_create_from_etapa(etapa=etapa_1, solicitacao=solicitacao)

    etapa_2 = provider._get_etapa_2(CPF)
    etapa_2.formulario.set_value('objetivo', 'Visita técnica')
    etapa_2.formulario.set_value('campus', campus_id)
    etapa_2.formulario.set_value('data_entrada', '2030-03-01')
    etapa_2.formulario.set_value('data_saida', '2030-03-02')
    SolicitacaoEtapa.update_or_create_from_etapa(etapa=etapa_2, solicitacao=solicitacao)
    return solicitacao


def _executar(provider: SolicitarVisitaServiceProvider, solicitacao: Solicitacao, sala_id: int, monkeypatch: pytest.MonkeyPatch) -> object:
    post = {
        'data': '2030-03-01',
        'data_saida': '2030-03-02',
        'hora_entrada': '08:00',
        'hora_saida': '18:00',
        'sala': sala_id,
        'atividade': 'Visita técnica',
    }
    request = RequestFactory().post('/', post)
    request.user = UserFactory()
    request._messages = CookieStorage(request)
    # O ``httprr`` lê o request do threadlocal, que o middleware preenche numa requisição real.
    monkeypatch.setattr(threadlocals, 'get_request', lambda: request)
    return provider.executar_solicitacao(request, solicitacao)


@pytest.mark.usefixtures('fronteiras_externas')
class TestExecutarSolicitacaoSemPlanilha:
    def test_solicitacao_sem_planilha_e_atendida(self, monkeypatch: pytest.MonkeyPatch) -> None:
        sala = SalaFactory()
        provider = SolicitarVisitaServiceProvider()
        solicitacao = _montar_solicitacao(provider, sala.predio.uo_id)

        _executar(provider, solicitacao, sala.pk, monkeypatch)

        solicitacao.refresh_from_db()
        assert solicitacao.status == Solicitacao.STATUS_ATENDIDO
        assert SolicitacaoEntrada.objects.filter(sala=sala).count() == 1
        assert PrestadorServico.objects.filter(matricula=CPF).count() == 1

    def test_visitante_com_prestador_existente_nao_e_regravado(self, monkeypatch: pytest.MonkeyPatch) -> None:
        sala = SalaFactory()
        provider = SolicitarVisitaServiceProvider()
        solicitacao = _montar_solicitacao(provider, sala.predio.uo_id)
        # O banco guarda o CPF com máscara; a checagem precisa achá-lo mesmo assim.
        prestador = PrestadorServicoFactory(matricula=CPF, pessoa_fisica=PessoaFisicaFactory(cpf=mask_cpf(CPF)), ativo=True)
        antes = PrestadorServico.objects.count()

        _executar(provider, solicitacao, sala.pk, monkeypatch)

        # Sem achar o prestador, o fluxo regravava o cadastro: desativava o prestador e trocava o nome pelo da API.
        prestador.refresh_from_db()
        assert PrestadorServico.objects.count() == antes
        assert prestador.ativo is True
        assert prestador.pessoa_fisica.nome != 'Visitante Teste'


CPF_COM_ZERO = '01234567890'
TIPO_XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


def _planilha_xlsx(cpf: object) -> bytes:
    """Planilha de visitantes como o Excel a grava: a célula do CPF fica numérica quando só tem dígitos."""
    planilha = Workbook()
    aba = planilha.active
    aba.append(['CPF', 'Nome', 'Email'])
    aba.append([cpf, 'Visitante Teste', 'visitante@example.com'])
    buffer = io.BytesIO()
    planilha.save(buffer)
    return buffer.getvalue()


def _anexar_planilha(solicitacao: Solicitacao, conteudo: bytes) -> None:
    SolicitacaoEtapaArquivo.update_or_create_from_file_bytes(
        bytes=conteudo,
        tipo_conteudo=TIPO_XLSX,
        data_hora_upload=datetime.now(),
        nome_original='visitantes.xlsx',
        nome_exibicao='Lista de Visitantes',
        descricao='Lista de Visitantes',
        solicitacao_etapa=SolicitacaoEtapa.objects.get(solicitacao=solicitacao, numero_etapa=2),
        nome_atributo_json='lista_visitantes',
    )


def _carregar_etapa(solicitacao: Solicitacao, numero: int) -> Etapa:
    return Etapa.load_from_json(SolicitacaoEtapa.objects.get(solicitacao=solicitacao, numero_etapa=numero).get_dados_as_json())


@pytest.mark.usefixtures('fronteiras_externas')
class TestPlanilhaComCpfNumerico:
    def test_cpf_numerico_com_zero_a_esquerda_e_aceito_na_validacao(self) -> None:
        assert cpf_valido(CPF_COM_ZERO)
        provider = SolicitarVisitaServiceProvider()
        solicitacao = _montar_solicitacao(provider, SalaFactory().predio.uo_id)
        etapa_2 = _carregar_etapa(solicitacao, 2)
        etapa_2.formulario.set_value('lista_visitantes', base64.b64encode(_planilha_xlsx(int(CPF_COM_ZERO))).decode())

        assert provider._validate_dados_etapa(None, etapa_2, solicitacao) == []

    def test_cpf_numerico_invalido_continua_rejeitado(self) -> None:
        provider = SolicitarVisitaServiceProvider()
        solicitacao = _montar_solicitacao(provider, SalaFactory().predio.uo_id)
        etapa_2 = _carregar_etapa(solicitacao, 2)
        etapa_2.formulario.set_value('lista_visitantes', base64.b64encode(_planilha_xlsx(int('01234567891'))).decode())

        assert provider._validate_dados_etapa(None, etapa_2, solicitacao) == ['Os seguintes CPFs são inválidos: 1234567891']

    def test_visitante_com_cpf_numerico_e_cadastrado_com_onze_digitos(self, monkeypatch: pytest.MonkeyPatch) -> None:
        sala = SalaFactory()
        provider = SolicitarVisitaServiceProvider()
        solicitacao = _montar_solicitacao(provider, sala.predio.uo_id)
        _anexar_planilha(solicitacao, _planilha_xlsx(int(CPF_COM_ZERO)))

        _executar(provider, solicitacao, sala.pk, monkeypatch)

        solicitacao.refresh_from_db()
        assert solicitacao.status == Solicitacao.STATUS_ATENDIDO
        assert PrestadorServico.objects.filter(matricula=CPF_COM_ZERO).count() == 1


def _marcar_visita_em_grupo(solicitacao: Solicitacao, valor: bool) -> None:
    etapa_1 = _carregar_etapa(solicitacao, 1)
    etapa_1.formulario.set_value('visita_grupo', valor)
    SolicitacaoEtapa.update_or_create_from_etapa(etapa=etapa_1, solicitacao=solicitacao)


class TestValidacaoDaPlanilhaNaEtapa2:
    @pytest.mark.parametrize('sem_planilha', [None, ''])
    def test_visita_individual_sem_planilha_e_aceita(self, sem_planilha: str | None) -> None:
        provider = SolicitarVisitaServiceProvider()
        solicitacao = _montar_solicitacao(provider, SalaFactory().predio.uo_id)
        _marcar_visita_em_grupo(solicitacao, False)
        etapa_2 = _carregar_etapa(solicitacao, 2)
        etapa_2.formulario.set_value('lista_visitantes', sem_planilha)

        assert provider._validate_dados_etapa(None, etapa_2, solicitacao) == []

    def test_visita_em_grupo_sem_planilha_e_recusada(self) -> None:
        provider = SolicitarVisitaServiceProvider()
        solicitacao = _montar_solicitacao(provider, SalaFactory().predio.uo_id)
        _marcar_visita_em_grupo(solicitacao, True)
        etapa_2 = _carregar_etapa(solicitacao, 2)

        assert provider._validate_dados_etapa(None, etapa_2, solicitacao) == ['Para visita em grupo, é necessário anexar a lista de visitantes.']

    def test_visita_em_grupo_com_planilha_valida_e_aceita(self) -> None:
        provider = SolicitarVisitaServiceProvider()
        solicitacao = _montar_solicitacao(provider, SalaFactory().predio.uo_id)
        _marcar_visita_em_grupo(solicitacao, True)
        etapa_2 = _carregar_etapa(solicitacao, 2)
        etapa_2.formulario.set_value('lista_visitantes', base64.b64encode(_planilha_xlsx(int(CPF_COM_ZERO))).decode())

        assert provider._validate_dados_etapa(None, etapa_2, solicitacao) == []

    @pytest.mark.parametrize(
        ('campo', 'valor', 'erro'),
        [
            ('data_entrada', None, 'Data de Entrada é um campo obrigatório.'),
            ('data_saida', None, 'Data de Saída é um campo obrigatório.'),
            ('data_entrada', '', 'Data de Entrada é um campo obrigatório.'),
            ('data_entrada', '01/03/2030', 'Data de Entrada inválida.'),
            ('data_saida', 'amanhã', 'Data de Saída inválida.'),
        ],
    )
    def test_data_ausente_ou_invalida_vira_erro_de_campo(self, campo: str, valor: str | None, erro: str) -> None:
        provider = SolicitarVisitaServiceProvider()
        solicitacao = _montar_solicitacao(provider, SalaFactory().predio.uo_id)
        etapa_2 = _carregar_etapa(solicitacao, 2)
        etapa_2.formulario.set_value(campo, valor)

        assert provider._validate_dados_etapa(None, etapa_2, solicitacao) == [erro]

    def test_saida_anterior_a_entrada_vira_erro_de_campo(self) -> None:
        provider = SolicitarVisitaServiceProvider()
        solicitacao = _montar_solicitacao(provider, SalaFactory().predio.uo_id)
        etapa_2 = _carregar_etapa(solicitacao, 2)
        etapa_2.formulario.set_value('data_entrada', '2030-03-10')
        etapa_2.formulario.set_value('data_saida', '2030-03-09')

        assert provider._validate_dados_etapa(None, etapa_2, solicitacao) == ['A data de saída não pode ser anterior à data de entrada.']

    def test_visita_de_um_dia_com_entrada_e_saida_na_mesma_data_e_aceita(self) -> None:
        provider = SolicitarVisitaServiceProvider()
        solicitacao = _montar_solicitacao(provider, SalaFactory().predio.uo_id)
        etapa_2 = _carregar_etapa(solicitacao, 2)
        etapa_2.formulario.set_value('data_entrada', '2030-03-10')
        etapa_2.formulario.set_value('data_saida', '2030-03-10')

        assert provider._validate_dados_etapa(None, etapa_2, solicitacao) == []

    def test_saida_a_mais_de_31_dias_da_entrada_vira_erro_de_campo_junto_com_os_demais(self) -> None:
        provider = SolicitarVisitaServiceProvider()
        solicitacao = _montar_solicitacao(provider, SalaFactory().predio.uo_id)
        etapa_2 = _carregar_etapa(solicitacao, 2)
        etapa_2.formulario.set_value('data_saida', '2030-04-02')
        etapa_2.formulario.set_value('objetivo', '')

        assert provider._validate_dados_etapa(None, etapa_2, solicitacao) == [
            'Objetivo é um campo obrigatório.',
            'A data de saída deve ser no máximo 31 dias após a data de início.',
        ]

    def test_saida_a_exatos_31_dias_da_entrada_e_aceita(self) -> None:
        provider = SolicitarVisitaServiceProvider()
        solicitacao = _montar_solicitacao(provider, SalaFactory().predio.uo_id)
        etapa_2 = _carregar_etapa(solicitacao, 2)
        etapa_2.formulario.set_value('data_saida', '2030-04-01')

        assert provider._validate_dados_etapa(None, etapa_2, solicitacao) == []

    @freeze_time('2030-03-10 08:00:00')
    def test_entrada_ontem_vira_erro_de_campo(self) -> None:
        provider = SolicitarVisitaServiceProvider()
        solicitacao = _montar_solicitacao(provider, SalaFactory().predio.uo_id)
        etapa_2 = _carregar_etapa(solicitacao, 2)
        etapa_2.formulario.set_value('data_entrada', '2030-03-09')
        etapa_2.formulario.set_value('data_saida', '2030-03-10')

        assert provider._validate_dados_etapa(None, etapa_2, solicitacao) == ['A data de entrada não pode ser anterior a hoje.']

    @pytest.mark.parametrize('agora', ['2030-03-10 00:00:00', '2030-03-10 23:59:59'])
    def test_entrada_hoje_e_aceita_em_qualquer_hora_do_dia(self, agora: str) -> None:
        provider = SolicitarVisitaServiceProvider()
        solicitacao = _montar_solicitacao(provider, SalaFactory().predio.uo_id)
        etapa_2 = _carregar_etapa(solicitacao, 2)
        etapa_2.formulario.set_value('data_entrada', '2030-03-10')
        etapa_2.formulario.set_value('data_saida', '2030-03-11')

        with freeze_time(agora):
            assert provider._validate_dados_etapa(None, etapa_2, solicitacao) == []

    @pytest.mark.usefixtures('fronteiras_externas')
    def test_endpoint_visita_individual_sem_planilha_conclui_a_solicitacao(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Fronteira externa: notificação do cidadão (Notifica gov.br).
        monkeypatch.setattr(solicitar_visita.Notificar, 'solicitacao_recebida', lambda *a, **k: None)
        provider = SolicitarVisitaServiceProvider()
        solicitacao = _montar_solicitacao(provider, SalaFactory().predio.uo_id)
        # Em produção a solicitação chega à etapa 2 ainda incompleta (editável).
        Solicitacao.objects.filter(pk=solicitacao.pk).update(status=Solicitacao.STATUS_INCOMPLETO)
        request = SimpleNamespace(method='POST', data=_carregar_etapa(solicitacao, 2).json())

        status, _resposta = provider.receber_solicitacao(request, CPF)

        assert status == 201
        solicitacao.refresh_from_db()
        assert solicitacao.status == Solicitacao.STATUS_EM_ANALISE


class TestDadosEmailDePendencia:
    def test_traz_erros_da_etapa_2_sem_duplicar_os_da_etapa_1(self) -> None:
        provider = SolicitarVisitaServiceProvider()
        solicitacao = _montar_solicitacao(provider, SalaFactory().predio.uo_id)
        etapa_1 = _carregar_etapa(solicitacao, 1)
        etapa_1.formulario.set_avaliacao(name='visita_grupo', status='ERROR', status_msg='Informe se é visita em grupo')
        SolicitacaoEtapa.update_or_create_from_etapa(etapa=etapa_1, solicitacao=solicitacao)
        etapa_2 = _carregar_etapa(solicitacao, 2)
        etapa_2.formulario.set_avaliacao(name='objetivo', status='ERROR', status_msg='Objetivo insuficiente')
        SolicitacaoEtapa.update_or_create_from_etapa(etapa=etapa_2, solicitacao=solicitacao)

        dados = provider.get_dados_email(solicitacao)

        assert [campo['name'] for campo in dados if campo.get('avaliacao_status') == 'ERROR'] == ['visita_grupo', 'objetivo']
