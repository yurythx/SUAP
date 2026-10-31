"""Testes da rotina de atualização automática das bases de dados abertos."""

import datetime
import json

import pytest
from django.core.files.base import ContentFile
from django.utils import timezone

from dados_abertos.enums import FormatoRecurso, Periodicidade, ResultadoAtualizacao, SituacaoLAI
from dados_abertos.models import BaseDados, PDABaseDados, PlanoDadosAbertos, RecursoDados
from dados_abertos.services import atualizacao_service
from dados_abertos.services.coleta import Coletado

CONTEUDO_ORIGINAL = json.dumps([{'numero': 1, 'objeto': 'Obra'}]).encode()
CONTEUDO_NOVO = json.dumps([{'numero': 1, 'objeto': 'Obra'}, {'numero': 2, 'objeto': 'Reforma'}]).encode()
CONTEUDO_OUTRO_ESQUEMA = json.dumps([{'numero': 1, 'objeto': 'Obra', 'cpf_gestor': '000'}]).encode()


@pytest.fixture
def media_temporaria(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    return tmp_path


@pytest.fixture
def cenario(db, media_temporaria):
    """Base liberada pelo LAI, com um recurso de URL sincronizado há 40 dias e frequência mensal."""
    pda = PlanoDadosAbertos.objects.create(
        titulo='PDA 2026-2027',
        vigencia_inicio=datetime.date(2026, 1, 1),
        vigencia_fim=datetime.date(2027, 12, 31),
    )
    base = BaseDados.objects.create(nome='contratos', titulo='Contratos', id_remoto='abc')
    recurso = RecursoDados.objects.create(
        dataset=base,
        nome='Contratos',
        formato=FormatoRecurso.JSON,
        url='https://suap.br/api/contrato/contratos/?ano=2026',
        arquivo=ContentFile(CONTEUDO_ORIGINAL, name='contratos.json'),
        esquema=['numero', 'objeto'],
    )
    rel = PDABaseDados.objects.create(pda=pda, base_dados=base, frequencia_atualizacao=Periodicidade.MENSAL)

    antigo = timezone.now() - datetime.timedelta(days=40)
    BaseDados.objects.filter(pk=base.pk).update(sincronizado_em=antigo)
    # `data_atualizacao` ANTES do `sincronizado_em`: é assim que fica um recurso de fato publicado,
    # porque o sync carimba `sincronizado_em` por último. Retroceder só o sync deixaria o recurso
    # eternamente "alterado após a última publicação" — estado que o sistema real não produz.
    RecursoDados.objects.filter(pk=recurso.pk).update(sincronizado_em=antigo, data_atualizacao=antigo - datetime.timedelta(minutes=1))
    # Depois de criar o recurso: o save() do RecursoDados reabre a análise do LAI.
    PDABaseDados.objects.filter(pk=rel.pk).update(situacao_lai=SituacaoLAI.LIBERADO)

    return {'pda': pda, 'base': base, 'recurso': recurso, 'rel': rel}


class ServicoCKANFake:
    base_url = 'https://ckan.br'
    api_key = 'chave'


def _simular(monkeypatch, conteudo: bytes, *, publicacoes: list | None = None):
    """Instala um CKAN e uma coleta falsos; registra em ``publicacoes`` o que subiria."""
    monkeypatch.setattr(atualizacao_service, 'get_ckan_service', ServicoCKANFake)
    monkeypatch.setattr(
        atualizacao_service.coleta,
        'baixar',
        lambda url, **kwargs: Coletado(conteudo=conteudo, content_type='application/json', paginas=1),
    )
    registro = publicacoes if publicacoes is not None else []
    monkeypatch.setattr(atualizacao_service, 'sync_dataset_with_ckan', lambda qs, *a, **kw: (registro.append('dataset'), (1, 0))[1])
    monkeypatch.setattr(atualizacao_service, 'sync_resource_with_ckan', lambda qs, *a, **kw: (registro.append('recurso'), (1, 0))[1])
    return registro


@pytest.mark.django_db
def test_conteudo_novo_com_mesmo_esquema_publica_sem_reabrir_o_lai(cenario, monkeypatch):
    """Dado novo com as mesmas colunas é o caso corrente: sobe ao CKAN e o LAI não é incomodado."""
    publicacoes = _simular(monkeypatch, CONTEUDO_NOVO)

    atualizacao_service.executar()

    cenario['rel'].refresh_from_db()
    assert cenario['rel'].situacao_lai == SituacaoLAI.LIBERADO
    assert publicacoes == ['dataset', 'recurso']
    assert cenario['base'].atualizacoes.first().resultado == ResultadoAtualizacao.SUCESSO


@pytest.mark.django_db
def test_esquema_alterado_reabre_o_lai_e_nao_publica(cenario, monkeypatch):
    """Coluna nova pode trazer dado pessoal: o arquivo fica local e a base volta para análise."""
    publicacoes = _simular(monkeypatch, CONTEUDO_OUTRO_ESQUEMA)

    atualizacao_service.executar()

    cenario['rel'].refresh_from_db()
    assert cenario['rel'].situacao_lai == SituacaoLAI.EM_ANALISE
    assert publicacoes == []
    assert cenario['base'].atualizacoes.first().resultado == ResultadoAtualizacao.ESQUEMA_ALTERADO
    cenario['recurso'].refresh_from_db()
    assert cenario['recurso'].esquema == ['numero', 'objeto', 'cpf_gestor']


@pytest.mark.django_db
def test_conteudo_identico_apenas_confirma_a_verificacao(cenario, monkeypatch):
    """Sem mudança não há o que publicar, mas a periodicidade foi cumprida e o relógio anda."""
    publicacoes = _simular(monkeypatch, CONTEUDO_ORIGINAL)

    atualizacao_service.executar()

    assert publicacoes == []
    assert cenario['base'].atualizacoes.first().resultado == ResultadoAtualizacao.SEM_ALTERACAO
    cenario['base'].refresh_from_db()
    assert (timezone.now() - cenario['base'].sincronizado_em).days == 0


@pytest.mark.django_db
def test_base_bloqueada_pelo_lai_nao_e_baixada(cenario, monkeypatch):
    """Sem liberação do LAI nada é coletado — o bloqueio vem antes de qualquer requisição."""
    PDABaseDados.objects.filter(pk=cenario['rel'].pk).update(situacao_lai=SituacaoLAI.EM_ANALISE)
    baixou = []
    _simular(monkeypatch, CONTEUDO_NOVO)
    monkeypatch.setattr(atualizacao_service.coleta, 'baixar', lambda url, **kw: baixou.append(url))

    atualizacao_service.executar()

    assert baixou == []
    assert cenario['base'].atualizacoes.first().resultado == ResultadoAtualizacao.BLOQUEADA_LAI


@pytest.mark.django_db
def test_base_so_com_upload_manual_vira_pendencia(cenario, monkeypatch):
    """Recurso sem URL não tem como ser atualizado sozinho: fica registrado para cobrança."""
    RecursoDados.objects.filter(pk=cenario['recurso'].pk).update(url='')
    _simular(monkeypatch, CONTEUDO_NOVO)

    atualizacao_service.executar()

    assert cenario['base'].atualizacoes.first().resultado == ResultadoAtualizacao.SEM_FONTE_AUTOMATICA


@pytest.mark.django_db
def test_base_dentro_do_prazo_nao_e_selecionada(cenario, monkeypatch):
    """A rotina só age no que venceu; sincronizada ontem, com frequência mensal, está em dia."""
    ontem = timezone.now() - datetime.timedelta(days=1)
    BaseDados.objects.filter(pk=cenario['base'].pk).update(sincronizado_em=ontem)
    RecursoDados.objects.filter(pk=cenario['recurso'].pk).update(sincronizado_em=ontem)
    _simular(monkeypatch, CONTEUDO_NOVO)

    atualizacao_service.executar()

    assert not cenario['base'].atualizacoes.exists()


@pytest.mark.django_db
def test_base_nunca_sincronizada_nao_e_selecionada(cenario, monkeypatch):
    """A primeira publicação é ato deliberado do gestor; a rotina mantém o que já está no ar."""
    BaseDados.objects.filter(pk=cenario['base'].pk).update(sincronizado_em=None)
    RecursoDados.objects.filter(pk=cenario['recurso'].pk).update(sincronizado_em=None)
    _simular(monkeypatch, CONTEUDO_NOVO)

    atualizacao_service.executar()

    assert not cenario['base'].atualizacoes.exists()


@pytest.mark.django_db
def test_frequencia_mais_estrita_vence(cenario, monkeypatch):
    """Base em dois PDAs: vale o menor intervalo, para não descumprir a promessa mais forte."""
    RecursoDados.objects.filter(pk=cenario['recurso'].pk).update(sincronizado_em=timezone.now() - datetime.timedelta(days=10))
    BaseDados.objects.filter(pk=cenario['base'].pk).update(sincronizado_em=timezone.now() - datetime.timedelta(days=10))
    outro_pda = PlanoDadosAbertos.objects.create(
        titulo='PDA 2028',
        vigencia_inicio=datetime.date(2028, 1, 1),
        vigencia_fim=datetime.date(2029, 12, 31),
    )
    rel = PDABaseDados.objects.create(pda=outro_pda, base_dados=cenario['base'], frequencia_atualizacao=Periodicidade.SEMANAL)
    PDABaseDados.objects.filter(pk=rel.pk).update(situacao_lai=SituacaoLAI.LIBERADO)
    _simular(monkeypatch, CONTEUDO_NOVO)

    atualizacao_service.executar()

    # Mensal (30d) não venceria em 10 dias; semanal (7d) sim.
    assert cenario['base'].atualizacoes.exists()


@pytest.mark.django_db
def test_o_command_executa_a_rotina(cenario, monkeypatch, capsys):
    """O agendamento do Celery Beat chama o command; ele delega ao service e resume o que aconteceu."""
    from django.core.management import call_command

    _simular(monkeypatch, CONTEUDO_NOVO)

    call_command('atualizar_bases_dados_abertos')

    assert 'Publicadas: 1' in capsys.readouterr().out
    assert cenario['base'].atualizacoes.first().resultado == ResultadoAtualizacao.SUCESSO


@pytest.mark.django_db
def test_falhas_consecutivas_conta_so_a_sequencia_atual(cenario):
    """O contador mede a sequência em curso, não o total histórico de falhas da base."""
    from dados_abertos.models import AtualizacaoBaseDados
    from dados_abertos.services import dashboard_service

    base = cenario['base']
    for resultado in (
        ResultadoAtualizacao.FALHA_DOWNLOAD,
        ResultadoAtualizacao.SUCESSO,
        ResultadoAtualizacao.FALHA_DOWNLOAD,
        ResultadoAtualizacao.FALHA_CKAN,
    ):
        AtualizacaoBaseDados.objects.create(base_dados=base, resultado=resultado)

    assert dashboard_service.falhas_consecutivas([base.pk]) == {base.pk: 2}


@pytest.mark.django_db
def test_bloqueio_do_lai_interrompe_a_sequencia(cenario):
    """Bloqueio do LAI não é falha técnica: quebra a sequência em vez de somar a ela."""
    from dados_abertos.models import AtualizacaoBaseDados
    from dados_abertos.services import dashboard_service

    base = cenario['base']
    for resultado in (
        ResultadoAtualizacao.FALHA_DOWNLOAD,
        ResultadoAtualizacao.BLOQUEADA_LAI,
        ResultadoAtualizacao.FALHA_CKAN,
    ):
        AtualizacaoBaseDados.objects.create(base_dados=base, resultado=resultado)

    assert dashboard_service.falhas_consecutivas([base.pk]) == {base.pk: 1}


@pytest.mark.django_db
def test_base_sem_falha_recente_nao_entra_no_contador(cenario):
    """Última execução bem-sucedida zera a contagem — nada a cobrar."""
    from dados_abertos.models import AtualizacaoBaseDados
    from dados_abertos.services import dashboard_service

    base = cenario['base']
    AtualizacaoBaseDados.objects.create(base_dados=base, resultado=ResultadoAtualizacao.FALHA_DOWNLOAD)
    AtualizacaoBaseDados.objects.create(base_dados=base, resultado=ResultadoAtualizacao.SUCESSO)

    assert dashboard_service.falhas_consecutivas([base.pk]) == {}


def test_a_rotina_regrava_o_espelho_csv_junto_do_original(cenario, monkeypatch):
    """O espelho acompanha a origem — é o que o diferencia de uma cópia feita uma vez só."""
    from dados_abertos.services import espelho_csv

    espelho = espelho_csv.atualizar_espelho(cenario['recurso'])
    PDABaseDados.objects.filter(pk=cenario['rel'].pk).update(situacao_lai=SituacaoLAI.LIBERADO)
    _simular(monkeypatch, CONTEUDO_NOVO)

    desfecho = atualizacao_service.atualizar_base(cenario['base'], ServicoCKANFake())

    assert desfecho.resultado == ResultadoAtualizacao.SUCESSO
    espelho.refresh_from_db()
    espelho.arquivo.open('rb')
    conteudo = espelho.arquivo.read().decode()
    espelho.arquivo.close()
    assert 'Reforma' in conteudo, 'o espelho ficou com o conteúdo antigo'
    cenario['rel'].refresh_from_db()
    assert cenario['rel'].situacao_lai == SituacaoLAI.LIBERADO, 'regravar o espelho não é edição humana'


def test_publicacao_pendente_do_esquema_alterado_sai_na_rodada_seguinte(cenario, monkeypatch):
    """Depois do ESQUEMA_ALTERADO o conteúdo novo fica local; a rodada pós-liberação tem de publicá-lo.

    Sem isto a coleta seguinte traz o mesmo conteúdo que já está gravado, vira SEM_ALTERACAO e
    `_confirmar_verificacao` anda o relógio da periodicidade — com o CKAN exibindo a versão antiga
    para sempre, e a base se declarando em dia.
    """
    _simular(monkeypatch, CONTEUDO_OUTRO_ESQUEMA)
    primeiro = atualizacao_service.atualizar_base(cenario['base'], ServicoCKANFake())
    assert primeiro.resultado == ResultadoAtualizacao.ESQUEMA_ALTERADO

    # O LAI analisou o esquema novo e liberou.
    PDABaseDados.objects.filter(pk=cenario['rel'].pk).update(situacao_lai=SituacaoLAI.LIBERADO)
    publicacoes = []
    _simular(monkeypatch, CONTEUDO_OUTRO_ESQUEMA, publicacoes=publicacoes)

    segundo = atualizacao_service.atualizar_base(cenario['base'], ServicoCKANFake())

    assert segundo.resultado == ResultadoAtualizacao.SUCESSO, f'ficou em {segundo.resultado}: {segundo.detalhe}'
    assert 'recurso' in publicacoes, 'o conteúdo que ficou devendo não subiu ao CKAN'
