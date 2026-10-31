"""Ninguém cria PessoaFisica fora do obter_ou_criar (spec da deduplicação, seção 3)."""

import re
from pathlib import Path

from django.apps import apps

RAIZ = Path(__file__).resolve().parents[3]
PADRAO = re.compile(
    r'PessoaFisica(\.objects)?\.(create|get_or_create|update_or_create|bulk_create)\('
    r'|PessoaFisica\(\s*\)|PessoaFisica\(\s*\w+\s*='
    r'|pessoa_?fisica\.(pk|id)\s*=\s*None'  # clonagem por pk=None (minicurso, transferência, intercâmbio)
)
PERMITIDOS = {
    'rh/deduplicacao/entrada.py',  # o próprio obter_ou_criar
    'rh/deduplicacao/aplicacao.py',  # instâncias só para bulk_update da higiene
    'edu/forms/matriculas.py',  # PessoaFisica() só para calcular a idade nos clean_* (não salva)
    'comum/webservice.py',  # PF fictícia pk=-1 do superusuário no terminal (não salva)
}


def _arquivos_dos_apps() -> set[Path]:
    arquivos = set()
    for config in apps.get_app_configs():
        base = Path(config.path)
        if RAIZ in base.parents:
            arquivos.update(base.rglob('*.py'))
    return arquivos


def test_pessoa_fisica_so_e_criada_por_obter_ou_criar() -> None:
    ofensores = []
    arquivos = sorted(_arquivos_dos_apps())
    assert arquivos  # caminho resolvido errado (symlink) passaria sem varrer nada
    for arquivo in arquivos:
        relativo = arquivo.relative_to(RAIZ).as_posix()
        if '/migrations/' in relativo or '/tests/' in relativo or '/features/' in relativo or 'new_tests' in relativo or relativo in PERMITIDOS:
            continue
        for numero, linha in enumerate(arquivo.read_text(errors='ignore').splitlines(), 1):
            if PADRAO.search(linha):
                ofensores.append(f'{relativo}:{numero}: {linha.strip()}')
    assert not ofensores, '\n'.join(ofensores)
