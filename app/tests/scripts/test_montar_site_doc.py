"""Checagem do montador do site de doc (``bin/scripts/montar_site_doc.py``), sem mkdocs.

O caso que motiva o teste: a linha ``**Quem pode:**`` **não** é uma lista limpa. O subagente
escreve prosa ("A e B."), e o papel às vezes vem de autorização por dado, que não é grupo
nenhum. A primeira versão quebrava só em vírgula e criou o perfil fantasma
"Comunicador Social e Coordenador de Comunicação Sistêmico." na página transversal.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'bin' / 'scripts'))

import montar_site_doc as montar

CONHECIDOS = {'Servidor', 'Comunicador Social', 'Coordenador de Comunicação', 'Coordenador de Comunicação Sistêmico'}

DOC = """# Eventos

## Tarefas

### 1. Cadastrar um evento

**Quem pode:** Servidor

### 2. Registrar um atendimento

**Quem pode:** Comunicador Social e Coordenador de Comunicação Sistêmico.

### 3. Consultar tudo

**Quem pode:** qualquer perfil com permissão de consultar evento

### 4. Avaliar

**Quem pode:** membro de grupo avaliador da dimensão
"""


def test_prosa_com_e_e_ponto_final_vira_dois_perfis() -> None:
    achados = montar.perfis_citados('Comunicador Social e Coordenador de Comunicação Sistêmico.', CONHECIDOS)
    assert achados == ['Comunicador Social', 'Coordenador de Comunicação Sistêmico'], achados


def test_nome_prefixado_nao_leva_credito_do_nome_maior() -> None:
    # "Coordenador de Comunicação" é prefixo de "... Sistêmico": só o maior conta.
    assert montar.perfis_citados('Coordenador de Comunicação Sistêmico', CONHECIDOS) == ['Coordenador de Comunicação Sistêmico']
    # E quando os dois são realmente citados, os dois entram.
    achados = montar.perfis_citados('Coordenador de Comunicação e Coordenador de Comunicação Sistêmico', CONHECIDOS)
    assert achados == ['Coordenador de Comunicação', 'Coordenador de Comunicação Sistêmico'], achados


def test_frase_generica_nao_gera_perfil() -> None:
    assert montar.perfis_citados('qualquer perfil com permissão de consultar evento', CONHECIDOS) == []


def test_autorizacao_por_dado_nao_gera_perfil() -> None:
    # `Evento.pode_avaliar` casa com Dimensao.grupos_avaliadores_locais: não é grupo nomeado.
    assert montar.perfis_citados('membro de grupo avaliador da dimensão', CONHECIDOS) == []


def test_mapa_de_tarefas_liga_perfil_ao_modulo() -> None:
    mapa = montar.tarefas_por_perfil(DOC, 'eventos', CONHECIDOS)
    assert mapa['Servidor'] == ['eventos: Cadastrar um evento']
    assert mapa['Comunicador Social'] == ['eventos: Registrar um atendimento']
    assert 'qualquer perfil com permissão de consultar evento' not in mapa
    assert len(mapa) == 3, mapa  # Servidor, Comunicador Social, Coordenador de Comunicação Sistêmico


def test_slug_de_area_perde_acento_e_espaco() -> None:
    assert montar.ascii_slug('Gestão de Pessoas') == 'gestao-de-pessoas'
    assert montar.ascii_slug('Tecnologia da Informação') == 'tecnologia-da-informacao'


def test_index_gera_dados_do_card_sem_html() -> None:
    with tempfile.TemporaryDirectory() as temporario:
        raiz = Path(temporario)
        documento = raiz / 'meu_modulo.md'
        documento.write_text('# Meu Módulo\n', encoding='utf-8')
        destino_original = montar.DESTINO
        montar.DESTINO = raiz
        try:
            montar.escrever_index([('Pesquisa & Inovação', 'meu_modulo', documento)])
        finally:
            montar.DESTINO = destino_original
        index = (raiz / 'index.md').read_text(encoding='utf-8')
        dados = json.loads(index.removeprefix('---\n').removesuffix('\n---\n'))
        assert dados['areas'] == [
            {
                'nome': 'Pesquisa & Inovação',
                'icone': 'P',
                'titulos': 'Meu Módulo',
                'url': 'pesquisa-inovacao/meu_modulo/',
            }
        ]
        assert '<' not in index


if __name__ == '__main__':
    for nome, caso in sorted(globals().items()):
        if nome.startswith('test_'):
            caso()
            sys.stdout.write(f'ok {nome}\n')
