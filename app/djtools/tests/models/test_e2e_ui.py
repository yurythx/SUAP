"""Checagem da resolução de tipo de campo da camada ``Tela``, sem browser e sem banco.

O que se afirma aqui é o contrato que um gerador de testes depende: a coluna ``Tipo`` das
``.feature`` é capitalizada (``Texto`` aparece 595 vezes, ``TextArea``, ``Numero`` sem acento)
e as chaves de ``_PREENCHEDORES`` são minúsculas. Sem a normalização, transcrever a coluna
literalmente — que é o que o subagente `e2e-tester` faz — quebra em todas elas.
"""

from __future__ import annotations

import pytest

from djtools.e2e_ui import Tela


@pytest.fixture
def tela_espia(monkeypatch) -> tuple[Tela, list]:
    """Uma ``Tela`` sem página, com os preenchedores trocados por um gravador de chamadas."""
    chamadas: list = []

    def gravar(nome_do_tipo):
        def preenchedor(self, nome, tipo, valor, opcao=None):
            chamadas.append((nome_do_tipo, nome, tipo, valor, opcao))

        return preenchedor

    monkeypatch.setattr(Tela, '_PREENCHEDORES', {chave: gravar(chave) for chave in Tela._PREENCHEDORES})
    return Tela(pagina=None), chamadas  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ('escrito', 'resolvido'),
    [
        ('Texto', 'texto'),
        ('TEXTO', 'texto'),
        (' texto ', 'texto'),
        ('TextArea', 'textarea'),
        ('Autocomplete Multiplo', 'autocomplete multiplo'),
        ('Numero', 'número'),
        ('número', 'número'),
        ('FilteredSelectMultiple', 'filteredselectmultiple'),
        ('Texto Rico', 'texto rico'),
    ],
)
def test_tipo_da_feature_resolve_para_a_chave_do_preenchedor(tela_espia, escrito, resolvido):
    tela, chamadas = tela_espia
    tela.preencher('Campo', escrito, 'valor')
    assert chamadas[0][0] == resolvido, f'{escrito!r} devia resolver para {resolvido!r}'


def test_tipo_desconhecido_falha_alto_e_lista_os_conhecidos(tela_espia):
    tela, _ = tela_espia
    with pytest.raises(AssertionError, match='tipo de campo não suportado'):
        tela.preencher('Campo', 'captcha', 'x')


def test_opcao_chega_ao_preenchedor_de_autocomplete(tela_espia):
    tela, chamadas = tela_espia
    tela.preencher('Curso', 'Autocomplete', '20101', opcao='Licenciatura em Geografia')
    assert chamadas[0][4] == 'Licenciatura em Geografia'


def test_formulario_aceita_linha_de_tres_e_de_quatro(tela_espia):
    tela, chamadas = tela_espia
    tela.preencher_formulario(
        [
            ('Nome', 'Texto', 'E2E'),
            ('Curso', 'Autocomplete', '20101', 'Licenciatura em Geografia'),
        ]
    )
    assert [c[0] for c in chamadas] == ['texto', 'autocomplete']
    assert chamadas[0][4] is None
    assert chamadas[1][4] == 'Licenciatura em Geografia'


def test_formulario_recusa_linha_de_tamanho_errado(tela_espia):
    tela, _ = tela_espia
    with pytest.raises(AssertionError, match='3 ou 4 elementos'):
        tela.preencher_formulario([('Nome', 'Texto')])


class _LocatorQueNavegou:
    """Locator cuja leitura estoura como o Playwright estoura durante uma navegação."""

    def all_inner_texts(self):
        from playwright.sync_api import Error

        raise Error('Execution context was destroyed, most likely because of a navigation')


class _PaginaQueNavegou:
    """Página cujo conteúdo é ilegível: é o estado em que a asserção falhou."""

    url = 'http://localhost/edu/diretoria/1/'

    def locator(self, _seletor):
        return _LocatorQueNavegou()

    def get_by_role(self, _papel, **_kwargs):
        return _LocatorQueNavegou()


def test_diagnostico_nao_levanta_quando_a_pagina_esta_navegando():
    """O coletor de evidência não pode substituir a falha que ele descreve.

    Sem isto, toda falha de timing chega ao relatório como
    `Error: Execution context was destroyed` — o erro interno do Playwright no lugar da
    asserção real. Foi o que escondeu a flake de `test_01_diretoria` (#16990).
    """
    tela = Tela(pagina=_PaginaQueNavegou())  # type: ignore[arg-type]

    diagnostico = tela.diagnostico()

    assert 'indisponível' in diagnostico, diagnostico
    assert tela.pagina.url in diagnostico, 'a URL deve sobreviver mesmo sem conseguir ler o DOM'
    assert tela.erros_na_tela() == ['<indisponível: Error>']
    assert tela.rotulos_na_tela() == ['<indisponível: Error>']
