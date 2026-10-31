"""Checagem do gate de validação de doc (``bin/scripts/validar_doc.py``), sem git e sem banco.

Monta módulos falsos em ``tmp_path`` e afirma o que decide se a nota de MR é útil ou vira
ruído: módulo sem doc não recebe lista de telas, tela dispensada sai da conta, módulo íntegro
**não gera nota nenhuma**, e — o caso que o ``edu`` expôs — rótulo genérico solto no texto de
uma tarefa **não** conta como cobertura.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'bin' / 'scripts'))

import validar_doc

S = validar_doc.SEPARADOR
CHAVE_PORTES = 'Comunicação Social::Cadastros::Eventos::Portes'

MENU = """\
Comunicação Social::Eventos:
  url: /admin/eventos/evento/
Comunicação Social::Cadastros::Eventos::Portes:
  url: /admin/eventos/porteevento/
Comunicação Social::Banners:
  url: /admin/eventos/banner/
"""

DOC_COMPLETA = f"""# Mod

## Tarefas

### 1. Fazer algo

No menu, acesse **Comunicação Social{S}Eventos**.

## Telas de apoio

Portes · Banners
"""

DOC_PARCIAL = f'# Mod\n\nNo menu, acesse **Comunicação Social{S}Eventos**.\n'


def _montar(raiz: Path, doc: str | None = None, conftest: str = '') -> None:
    (raiz / 'menu.yaml').write_text(MENU, encoding='utf-8')
    if doc is not None:
        (raiz / 'docs').mkdir(parents=True, exist_ok=True)
        (raiz / 'docs' / 'usuario.md').write_text(doc, encoding='utf-8')
    if conftest:
        (raiz / 'tests' / 'doc').mkdir(parents=True, exist_ok=True)
        (raiz / 'tests' / 'doc' / 'conftest.py').write_text(conftest, encoding='utf-8')


def _rodar(tmp: Path, **kwargs) -> list[str]:
    raiz = tmp / 'mod'
    raiz.mkdir(parents=True, exist_ok=True)
    _montar(raiz, **kwargs)
    anterior = Path.cwd()
    os.chdir(tmp)
    try:
        return validar_doc.relatar('mod')
    finally:
        os.chdir(anterior)


def test_modulo_sem_doc_nao_lista_telas(tmp_path: Path) -> None:
    texto = '\n'.join(_rodar(tmp_path))
    assert 'Sem documentação de usuário' in texto
    assert '3 telas' in texto
    # A lista de telas seria redundante quando a resposta já é "não existe doc".
    assert '/admin/eventos/evento/' not in texto, texto


def test_doc_completa_nao_gera_nota(tmp_path: Path) -> None:
    assert _rodar(tmp_path, doc=DOC_COMPLETA) == []


def test_tela_nao_citada_vira_achado(tmp_path: Path) -> None:
    texto = '\n'.join(_rodar(tmp_path, doc=DOC_PARCIAL))
    assert '2 de 3 telas sem menção' in texto, texto
    assert '/admin/eventos/porteevento/' in texto
    assert '/admin/eventos/banner/' in texto


def test_dispensa_com_motivo_sai_da_conta(tmp_path: Path) -> None:
    conftest = "TELAS_DISPENSADAS = {'Portes': 'tabela de apoio', 'Banners': 'sem uso hoje'}\n"
    assert _rodar(tmp_path, doc=DOC_PARCIAL, conftest=conftest) == []


def test_tarefa_exige_caminho_completo_e_nao_rotulo_solto() -> None:
    # Era o defeito que o `edu` expôs: 143 de 188 telas contadas como cobertas por substring.
    assert not validar_doc.cita(CHAVE_PORTES, 'os portes disponíveis aparecem na lista', '')
    assert validar_doc.cita(CHAVE_PORTES, f'acesse Comunicação Social{S}Cadastros{S}Eventos{S}Portes', '')


def test_secao_de_apoio_aceita_rotulo_solto() -> None:
    # Ali, listar o nome É a declaração de cobertura — decidido na anatomia (#16997).
    assert validar_doc.cita(CHAVE_PORTES, '', 'Áreas temáticas · Portes · Dimensões')
    # Fronteira de palavra continua valendo lá dentro.
    assert not validar_doc.cita(CHAVE_PORTES, '', 'Portesinho')


if __name__ == '__main__':
    import tempfile

    for nome, caso in sorted(globals().items()):
        if not nome.startswith('test_'):
            continue
        if 'tmp_path' in caso.__code__.co_varnames:
            with tempfile.TemporaryDirectory() as diretorio:
                caso(Path(diretorio))
        else:
            caso()
        sys.stdout.write(f'ok {nome}\n')
