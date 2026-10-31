"""Caracterização dos comandos ``importar_rpi*`` (importação das revistas RPI do INPI).

A rede (download do zip da revista e a página de revistas do INPI) é a única fronteira
simulada: o arquivo TXT sai de um zip montado aqui, e o que se verifica é o efeito no banco
(registros, despachos e a última RPI importada) e o retorno do comando.
"""

from __future__ import annotations

import importlib
import io
from datetime import date, datetime
import zipfile
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pytest
from bs4 import BeautifulSoup
from django.apps import apps as django_apps
from django.core.management import call_command

from comum.models import Configuracao
from pesquisa.management.commands import importar_rpi, importar_rpi_software
from pesquisa.models import PropriedadeIntelectual, PublicacaoPropriedadeIntelectual, RegistroPropriedadeIntelectual
from rh.tests.factories import ServidorFactory

CABECALHO = 'RPI 2700 de 03/01/2023\n'
IFRN_RN = 'INSTITUTO FEDERAL DE EDUCAÇÃO, CIÊNCIA E TECNOLOGIA DO RN'

# Revista com: patente do IFRN (número longo, com data, inventores e complemento), patente de
# terceiros, segundo despacho da mesma patente (outro código, número via (11), titular pelo nome
# configurado), despacho repetido e um bloco de software ((Np)/(Dl)/(Cr)).
REVISTA = (
    CABECALHO
    + '(Cd) 3.1\n(21) BR 10 2022 000001-2\n(22) 05/01/2022\n(54) PATENTE DO IFRN\n'
    + f'(71) {IFRN_RN} (BR/RN)\n(72) Fulano de Tal\n(Co) Publicação do pedido\n'
    + '(Cd) 3.2\n(21) PI0001-1\n(54) PATENTE ALHEIA\n(71) EMPRESA QUALQUER (BR/SP)\n'
    + '(Cd) 16.1\n(11) BR 10 2022 000001-2\n(54) PATENTE DO IFRN CONCEDIDA\n(71) INSTITUTO X (BR/RN)\n'
    + '(Cd) 3.1\n(21) BR 10 2022 000001-2\n(71) INSTITUTO X (BR/RN)\n'
    + '(Cd) 730\n(Np) BR 51 2022 000009-9\n(Dl) 07/02/2022\n(54) SOFTWARE DO IFRN\n'
    + f'(73) {IFRN_RN}\n(Cr) Beltrano\n'
)

# Revista anterior: a mesma patente aparece sem o IFRN como titular (despacho retroativo).
REVISTA_ANTERIOR = (
    'RPI 2699 de 27/12/2022\n'
    '(Cd) 2.1\n(21) BR 10 2022 000001-2\n(54) TITULO PROVISORIO\n(71) FULANO DE TAL (BR/RN)\n(72) Fulano\n'
    '(Cd) 2.2\n(Np) BR 51 2022 000009-9\n(71) CICLANO (BR/RN)\n(Cr) Beltrano e Ciclano\n'
)


def _zip(nome: str, conteudo: str | bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as arquivo_zip:
        arquivo_zip.writestr(nome, conteudo)
    return buffer.getvalue()


def _instantaneo() -> dict[str, Any]:
    return {
        'registros': sorted(
            RegistroPropriedadeIntelectual.objects.values_list(
                'numero_processo', 'tipo__descricao', 'primeira_rpi', 'titulo', 'titulares', 'inventores', 'data'
            )
        ),
        'despachos': sorted(
            PublicacaoPropriedadeIntelectual.objects.values_list(
                'propriedadeintelectual__numero_processo', 'rpi', 'data', 'codigo', 'complemento', 'lida'
            )
        ),
        'ultima_rpi': dict(PropriedadeIntelectual.objects.values_list('descricao', 'ultima_rpi')),
    }


@pytest.fixture
def inpi(settings, tmp_path, monkeypatch) -> Callable[[dict[int, str | bytes]], list[str]]:
    """Simula o download das revistas: ``{numero: conteudo}``; as demais vêm só com o cabeçalho."""
    settings.TEMP_DIR = str(tmp_path)
    Configuracao.objects.update_or_create(app='comum', chave='instituicao', defaults={'valor': 'Instituto X'})
    Configuracao.clear_cache()
    for descricao in ('Patente', 'Software'):
        PropriedadeIntelectual.objects.get_or_create(descricao=descricao)
    baixadas: list[str] = []

    def configurar(revistas: dict[int, str | bytes]) -> list[str]:
        def get(url: str, **kwargs: Any) -> SimpleNamespace:
            baixadas.append(url)
            codigo = url.rsplit('/', 1)[-1].removesuffix('.zip')
            numero = int(codigo.lstrip('PC'))
            return SimpleNamespace(content=_zip(f'{codigo}.txt', revistas.get(numero, CABECALHO)))

        monkeypatch.setattr('djtools.utils.requests.get', get)
        return baixadas

    return configurar


def _pagina_inpi(monkeypatch: pytest.MonkeyPatch, coluna_patente: str, coluna_software: str) -> None:
    celulas = ['<td></td>'] * 7 + [
        f'<td><a href="#">pdf</a><a href="{coluna_patente}">txt</a></td>',
        f'<td><a href="#">pdf</a><a href="{coluna_software}">txt</a></td>',
    ]
    pagina = BeautifulSoup(f'<table><tr class="warning">{"".join(celulas)}</tr></table>', 'html.parser')

    class Navegador:
        def open(self, *args: Any, **kwargs: Any) -> None:
            pass

        def get_current_page(self) -> BeautifulSoup:
            return pagina

    monkeypatch.setattr('mechanicalsoup.StatefulBrowser', Navegador)


@pytest.mark.django_db
def test_importar_rpi_especifica_de_patentes(inpi) -> None:
    baixadas = inpi({2700: REVISTA})

    retorno = importar_rpi.Command().handle(numero_da_rpi=2700)

    assert retorno == 2700
    assert baixadas == ['http://revistas.inpi.gov.br/txt/P2700.zip']
    assert _instantaneo() == ESPERADO['importar_rpi']


@pytest.mark.django_db
def test_importar_rpi_especifica_de_software(inpi) -> None:
    baixadas = inpi({2700: REVISTA})

    retorno = importar_rpi_software.Command().handle(numero_da_rpi=2700)

    assert retorno == 2700
    assert baixadas == ['http://revistas.inpi.gov.br/txt/PC2700.zip']
    assert _instantaneo() == ESPERADO['importar_rpi_software']


@pytest.mark.django_db
def test_importar_rpi_mais_recente_so_uma_vez(inpi, monkeypatch) -> None:
    baixadas = inpi({2700: REVISTA})
    _pagina_inpi(monkeypatch, 'http://revistas.inpi.gov.br/txt/P2700.zip', 'http://revistas.inpi.gov.br/txt/PC2700.zip')

    assert importar_rpi.Command().handle() == '2700'
    assert importar_rpi_software.Command().handle() == '2700'
    antes = _instantaneo()
    # Mesma revista de novo: a última RPI importada já é essa, nada é baixado.
    assert importar_rpi.Command().handle() == '2700'

    assert baixadas == ['http://revistas.inpi.gov.br/txt/P2700.zip', 'http://revistas.inpi.gov.br/txt/PC2700.zip']
    assert antes == _instantaneo() == ESPERADO['mais_recente']


@pytest.mark.django_db
def test_software_mais_recente_grava_o_numero_sem_o_prefixo(inpi, monkeypatch) -> None:
    # O arquivo de software é PC<numero>.zip: o prefixo tem duas letras, não uma (#17462).
    baixadas = inpi({2700: REVISTA})
    _pagina_inpi(monkeypatch, 'http://revistas.inpi.gov.br/txt/P2700.zip', 'http://revistas.inpi.gov.br/txt/PC2700.zip')

    assert importar_rpi_software.Command().handle() == '2700'
    # Mesma revista de novo: a última RPI importada já é essa, nada é baixado.
    assert importar_rpi_software.Command().handle() == '2700'

    assert baixadas == ['http://revistas.inpi.gov.br/txt/PC2700.zip']
    assert PropriedadeIntelectual.objects.get(descricao='Software').ultima_rpi == '2700'
    software = RegistroPropriedadeIntelectual.objects.get(numero_processo='BR5120220000099')
    assert software.primeira_rpi == '2700'
    assert list(PublicacaoPropriedadeIntelectual.objects.filter(propriedadeintelectual=software).values_list('rpi', 'codigo')) == [('2700', '730')]


@pytest.mark.django_db
def test_importar_rpi_sem_acesso_ao_inpi_nao_faz_nada(inpi, monkeypatch) -> None:
    class NavegadorSemRede:
        def open(self, *args: Any, **kwargs: Any) -> None:
            raise ConnectionError

    monkeypatch.setattr('mechanicalsoup.StatefulBrowser', NavegadorSemRede)

    assert importar_rpi.Command().handle() is None
    assert importar_rpi_software.Command().handle() is None


@pytest.mark.django_db
def test_revista_em_latin1(inpi) -> None:
    inpi({2700: REVISTA.encode('ISO-8859-1', errors='replace')})

    # O de software relê o arquivo em ISO-8859-1; o de patentes não tem esse recurso.
    assert importar_rpi_software.Command().handle(numero_da_rpi=2700) == 2700
    assert RegistroPropriedadeIntelectual.objects.filter(numero_processo='BR5120220000099').exists()
    with pytest.raises(UnicodeDecodeError):
        importar_rpi.Command().handle(numero_da_rpi=2700)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ('comando', 'anterior', 'atual'),
    [('importar_rpi_antiga', 2139, 2140), ('importar_rpi_softwares_recentes', 2404, 2405), ('importar_rpi_softwares_revistas_antigas', 2139, 2140)],
)
def test_importacao_historica(inpi, comando: str, anterior: int, atual: int) -> None:
    baixadas = inpi({anterior: REVISTA_ANTERIOR, atual: REVISTA})

    call_command(comando)

    assert len(baixadas) == len(set(baixadas))
    assert _instantaneo() == ESPERADO[comando]


# Efeito no banco medido no código anterior à refatoração (caracterização).
ESPERADO: dict[str, Any] = {
    'importar_rpi': {
        'despachos': [
            ('BR1020220000012', '2700', date(2023, 1, 3), '16.1', None, False),
            ('BR1020220000012', '2700', date(2023, 1, 3), '3.1', 'Publicação do pedido', False),
        ],
        'registros': [('BR1020220000012', 'Patente', '2700', 'PATENTE DO IFRN CONCEDIDA', 'INSTITUTO X (BR/RN)', 'Fulano de Tal', date(2022, 1, 5))],
        'ultima_rpi': {'Patente': None, 'Software': None},
    },
    'importar_rpi_software': {
        'despachos': [
            ('BR1020220000012', '2700', date(2023, 1, 3), '16.1', None, False),
            ('BR1020220000012', '2700', date(2023, 1, 3), '3.1', 'Publicação do pedido', False),
            ('BR5120220000099', '2700', date(2023, 1, 3), '730', None, False),
        ],
        'registros': [
            ('BR1020220000012', 'Software', '2700', 'PATENTE DO IFRN CONCEDIDA', 'INSTITUTO X (BR/RN)', 'Fulano de Tal', date(2022, 1, 5)),
            (
                'BR5120220000099',
                'Software',
                '2700',
                'SOFTWARE DO IFRN',
                'INSTITUTO FEDERAL DE EDUCAÇÃO, CIÊNCIA E TECNOLOGIA DO RN',
                'Beltrano',
                date(2022, 2, 7),
            ),
        ],
        'ultima_rpi': {'Patente': None, 'Software': None},
    },
    # Corrigido no #17462: antes a revista de software gravava 'C2700' (e duplicava os despachos da patente).
    'mais_recente': {
        'despachos': [
            ('BR1020220000012', '2700', date(2023, 1, 3), '16.1', None, False),
            ('BR1020220000012', '2700', date(2023, 1, 3), '3.1', 'Publicação do pedido', False),
            ('BR5120220000099', '2700', date(2023, 1, 3), '730', None, False),
        ],
        'registros': [
            ('BR1020220000012', 'Patente', '2700', 'PATENTE DO IFRN CONCEDIDA', 'INSTITUTO X (BR/RN)', 'Fulano de Tal', date(2022, 1, 5)),
            (
                'BR5120220000099',
                'Software',
                '2700',
                'SOFTWARE DO IFRN',
                'INSTITUTO FEDERAL DE EDUCAÇÃO, CIÊNCIA E TECNOLOGIA DO RN',
                'Beltrano',
                date(2022, 2, 7),
            ),
        ],
        'ultima_rpi': {'Patente': '2700', 'Software': '2700'},
    },
    'importar_rpi_antiga': {
        'despachos': [
            ('BR1020220000012', '2139', date(2022, 12, 27), '2.1', None, True),
            ('BR1020220000012', '2140', date(2023, 1, 3), '3.1', 'Publicação do pedido', True),
        ],
        'registros': [('BR1020220000012', 'Patente', '2140', 'PATENTE DO IFRN CONCEDIDA', 'INSTITUTO X (BR/RN)', 'Fulano de Tal', date(2022, 1, 5))],
        'ultima_rpi': {'Patente': '2756', 'Software': None},
    },
    'importar_rpi_softwares_recentes': {
        'despachos': [
            ('BR1020220000012', '2404', date(2022, 12, 27), '2.1', None, True),
            ('BR1020220000012', '2405', date(2023, 1, 3), '16.1', None, True),
            ('BR1020220000012', '2405', date(2023, 1, 3), '3.1', 'Publicação do pedido', True),
            ('BR5120220000099', '2404', date(2022, 12, 27), '2.2', None, True),
            ('BR5120220000099', '2405', date(2023, 1, 3), '730', None, True),
        ],
        'registros': [
            ('BR1020220000012', 'Software', '2405', 'PATENTE DO IFRN CONCEDIDA', 'INSTITUTO X (BR/RN)', 'Fulano de Tal', date(2022, 1, 5)),
            (
                'BR5120220000099',
                'Software',
                '2405',
                'SOFTWARE DO IFRN',
                'INSTITUTO FEDERAL DE EDUCAÇÃO, CIÊNCIA E TECNOLOGIA DO RN',
                'Beltrano',
                date(2022, 2, 7),
            ),
        ],
        'ultima_rpi': {'Patente': None, 'Software': '2771'},
    },
    'importar_rpi_softwares_revistas_antigas': {
        'despachos': [
            ('BR5120220000099', '2139', date(2022, 12, 27), '2.2', None, True),
            ('BR5120220000099', '2140', date(2023, 1, 3), '730', None, True),
        ],
        'registros': [
            (
                'BR5120220000099',
                'Software',
                '2140',
                'SOFTWARE DO IFRN',
                'INSTITUTO FEDERAL DE EDUCAÇÃO, CIÊNCIA E TECNOLOGIA DO RN',
                'Beltrano',
                date(2022, 2, 7),
            )
        ],
        'ultima_rpi': {'Patente': None, 'Software': '2403'},
    },
}


@pytest.mark.django_db
def test_migracao_tira_o_prefixo_da_rpi_de_software_ja_gravada(sync_permissions) -> None:
    corrigir = importlib.import_module('pesquisa.migrations.0088_corrigir_rpi_prefixo_software').corrigir_rpi_prefixo_software
    leitor = ServidorFactory().get_vinculo()
    lida_em = datetime(2023, 1, 10, 9, 30)
    software, _ = PropriedadeIntelectual.objects.update_or_create(descricao='Software', defaults={'ultima_rpi': 'C2700'})
    patente, _ = PropriedadeIntelectual.objects.update_or_create(descricao='Patente', defaults={'ultima_rpi': '2700'})
    programa = RegistroPropriedadeIntelectual.objects.create(numero_processo='BR512022000009', tipo=software, primeira_rpi='C2700')
    invento = RegistroPropriedadeIntelectual.objects.create(numero_processo='BR102022000001', tipo=patente, primeira_rpi='2699')
    sem_gemea = PublicacaoPropriedadeIntelectual.objects.create(propriedadeintelectual=programa, rpi='C2700', codigo='730')
    com_gemea = PublicacaoPropriedadeIntelectual.objects.create(
        propriedadeintelectual=invento, rpi='C2701', codigo='3.1', lida=True, lida_por=leitor, lida_em=lida_em
    )
    gemea = PublicacaoPropriedadeIntelectual.objects.create(propriedadeintelectual=invento, rpi='2701', codigo='3.1')
    normal = PublicacaoPropriedadeIntelectual.objects.create(propriedadeintelectual=invento, rpi='2699', codigo='2.1')

    corrigir(django_apps, None)
    depois = _instantaneo()
    corrigir(django_apps, None)

    assert _instantaneo() == depois
    assert depois['ultima_rpi'] == {'Software': '2700', 'Patente': '2700'}
    assert sorted(RegistroPropriedadeIntelectual.objects.values_list('numero_processo', 'primeira_rpi')) == [
        ('BR102022000001', '2699'),
        ('BR512022000009', '2700'),
    ]
    assert not PublicacaoPropriedadeIntelectual.objects.filter(pk=com_gemea.pk).exists()
    assert sorted(PublicacaoPropriedadeIntelectual.objects.values_list('pk', 'rpi', 'codigo', 'lida', 'lida_por', 'lida_em')) == sorted(
        [
            (sem_gemea.pk, '2700', '730', False, None, None),
            (gemea.pk, '2701', '3.1', True, leitor.pk, lida_em),
            (normal.pk, '2699', '2.1', False, None, None),
        ]
    )
