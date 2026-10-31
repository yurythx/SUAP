"""Testes do espelho CSV: o gêmeo tabular de um recurso JSON."""

import datetime
import json

import pytest
from django.core.files.base import ContentFile

from dados_abertos.enums import FormatoRecurso, SituacaoLAI
from dados_abertos.models import BaseDados, PDABaseDados, PlanoDadosAbertos, RecursoDados
from dados_abertos.services import espelho_csv

REGISTROS = [{'numero': '2026/001', 'objeto': 'Manutenção'}, {'numero': '2026/002', 'objeto': 'Limpeza'}]


@pytest.fixture
def media_temporaria(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    return tmp_path


@pytest.fixture
def origem(db, media_temporaria):
    """Recurso JSON já baixado, do jeito que a rotina o deixa."""
    base = BaseDados.objects.create(nome='contratos', titulo='Contratos')
    return RecursoDados.objects.create(
        dataset=base,
        nome='Contratos vigentes',
        descricao='Contratos administrativos em vigor.',
        formato=FormatoRecurso.JSON,
        arquivo=ContentFile(json.dumps(REGISTROS).encode(), name='contratos.json'),
    )


def test_gera_o_gemeo_em_csv_com_o_mesmo_conteudo(origem):
    """O espelho é outro recurso do mesmo dataset, em CSV, com nome próprio."""
    espelho = espelho_csv.atualizar_espelho(origem)

    assert espelho.formato == FormatoRecurso.CSV
    assert espelho.nome == 'Contratos vigentes (CSV)'
    assert espelho.dataset_id == origem.dataset_id
    assert espelho.derivado_de_id == origem.pk
    assert espelho.url == '', 'o espelho não pode ter URL: a rotina o coletaria como se fosse JSON'

    espelho.arquivo.open('rb')
    linhas = espelho.arquivo.read().decode().splitlines()
    espelho.arquivo.close()
    assert linhas[0] == 'numero,objeto'
    assert linhas[1] == '2026/001,Manutenção'


def test_regravar_pela_rotina_nao_reabre_o_lai(origem):
    """A rotina re-coleta a mesma origem: regravar o espelho não é edição humana."""
    pda = PlanoDadosAbertos.objects.create(titulo='PDA', vigencia_inicio=datetime.date(2026, 1, 1), vigencia_fim=datetime.date(2026, 12, 31))
    espelho = espelho_csv.atualizar_espelho(origem)
    relacao = PDABaseDados.objects.create(pda=pda, base_dados=origem.dataset)
    PDABaseDados.objects.filter(pk=relacao.pk).update(situacao_lai=SituacaoLAI.LIBERADO)

    origem.arquivo.save('contratos.json', ContentFile(json.dumps(REGISTROS[:1]).encode()), save=False)
    espelho_csv.atualizar_espelho(origem, via_rotina=True)

    relacao.refresh_from_db()
    assert relacao.situacao_lai == SituacaoLAI.LIBERADO
    espelho.refresh_from_db()
    espelho.arquivo.open('rb')
    conteudo = espelho.arquivo.read().decode()
    espelho.arquivo.close()
    assert '2026/002' not in conteudo, 'o espelho não acompanhou a origem'


def test_json_sem_registros_recusa_explicitamente(origem):
    """Sem registros não há CSV: melhor recusar do que publicar um arquivo vazio.

    Um objeto plano (``{"total": 3}``) não serve de contraexemplo — desde a correção da leitura
    ele é um registro de uma linha. O que não tabula é não haver registro algum.
    """
    origem.arquivo.save('contratos.json', ContentFile(b'[]'), save=False)
    origem.save()

    with pytest.raises(espelho_csv.EspelhoIndisponivel):
        espelho_csv.atualizar_espelho(origem)

    assert not origem.derivados.exists()
