"""Teste do command que aplica às bases os metadados DCAT-BR do arquivo versionado."""

import datetime
import io
import json

import pytest
from django.core.management import call_command

from dados_abertos.models import BaseDados, RecursoDados
from dados_abertos.tests.factories import BaseDadosFactory, RecursoDadosFactory

METADADOS = {
    'licenca': {'nome': 'CC BY 4.0', 'codigo_ckan': 'cc-by'},
    'padrao': {'cobertura_espacial': 'ESTADUAL', 'valor_cobertura_espacial': 'RN'},
    'conjuntos': [
        {
            'nome': 'assistencia-estudantil',
            'notas': 'Totais anuais dos auxílios.',
            'tags': ['pnaes'],
            'tema': 'Educação',
            'cobertura_temporal_inicio': '2025-01-01',
            'ods': [4, 10],
            'recursos': {'Auxílios 2026': 'Totais de 2026.', 'Recurso inexistente': 'x'},
        },
        {'nome': 'base-que-nao-existe', 'notas': 'x'},
    ],
}


def _aplicar(tmp_path, *args):
    arquivo = tmp_path / 'conjuntos.json'
    arquivo.write_text(json.dumps(METADADOS), encoding='utf-8')
    saida = io.StringIO()
    call_command('aplicar_metadados_conjuntos', '--arquivo', str(arquivo), *args, stdout=saida)
    return saida.getvalue()


@pytest.fixture
def base(db):
    base = BaseDadosFactory(nome='assistencia-estudantil', notas='Descrição antiga.')
    RecursoDadosFactory(dataset=base, nome='Auxílios 2026')
    return base


@pytest.mark.django_db
def test_aplica_os_metadados_e_relata_o_que_nao_encontrou(base, tmp_path):
    saida = _aplicar(tmp_path)

    base = BaseDados.objects.get(pk=base.pk)
    assert (base.notas, base.tags, base.tema.nome, base.licenca.codigo_ckan) == ('Totais anuais dos auxílios.', ['pnaes'], 'Educação', 'cc-by')
    assert (base.cobertura_espacial, base.cobertura_temporal_inicio, base.ods) == ('ESTADUAL', datetime.date(2025, 1, 1), [4, 10])
    assert RecursoDados.objects.get(dataset=base).descricao == 'Totais de 2026.'
    assert 'base-que-nao-existe: base não encontrada' in saida
    assert 'recurso "Recurso inexistente" não encontrado' in saida
    # Rodar de novo não muda nada.
    assert 'assistencia-estudantil: nada a alterar.' in _aplicar(tmp_path)


@pytest.mark.django_db
def test_simulacao_nao_grava(base, tmp_path):
    _aplicar(tmp_path, '--simular')

    assert BaseDados.objects.get(pk=base.pk).notas == 'Descrição antiga.'
