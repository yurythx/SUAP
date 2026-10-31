import json
from importlib import import_module
from pathlib import Path

from django.db.migrations.state import ProjectState

from djtools.db.migrations.operations.loaddata import RunLoadData


def test_carga_inicial_grava_so_campos_que_existem_na_0001() -> None:
    """A 0002 roda logo após a 0001 numa instalação nova: não pode depender de colunas de migrações posteriores."""
    estado = ProjectState()
    for operacao in import_module('rsc_tae.migrations.0001_initial').Migration.operations:
        operacao.state_forwards('rsc_tae', estado)

    for operacao in import_module('rsc_tae.migrations.0002_carga_inicial').Migration.operations:
        assert isinstance(operacao, RunLoadData), 'a carga precisa usar os models históricos, não o loaddata dos models atuais'
        for registro in json.loads(Path(operacao.file_name).read_text()):
            campos_na_0001 = estado.models[tuple(registro['model'].split('.'))].fields
            assert set(registro['fields']) <= set(campos_na_0001), f'{operacao.file_name}: {set(registro["fields"]) - set(campos_na_0001)}'
