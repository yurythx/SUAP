from __future__ import annotations

import base64
import hashlib
import logging

import pytest
from django.contrib.staticfiles import finders
from django.test import override_settings

from djtools.utils.estaticos_pdf import coletar_assets


@pytest.fixture
def raiz_estatica(tmp_path, settings):
    """Um STATICFILES_DIRS temporário, para os testes não dependerem dos apps."""
    (tmp_path / 'css').mkdir()
    (tmp_path / 'img').mkdir()
    (tmp_path / 'css' / 'estilo.css').write_bytes(b'@font-face { src: url(./fonte.ttf); }')
    (tmp_path / 'css' / 'fonte.ttf').write_bytes(b'fonte binaria')
    (tmp_path / 'img' / 'logo.png').write_bytes(b'png')
    (tmp_path / 'img' / 'copia.png').write_bytes(b'png')
    settings.STATICFILES_DIRS = [str(tmp_path)]
    # finders.get_finder é lru_cache e o FileSystemFinder lê STATICFILES_DIRS no
    # __init__: sem limpar o cache, o segundo teste em diante olharia o diretório
    # do teste anterior. Verificado empiricamente — não remova.
    finders.get_finder.cache_clear()
    yield tmp_path
    finders.get_finder.cache_clear()


class TestColetarAssets:
    def test_coleta_link_img_e_url_css_inline(self, raiz_estatica):
        html = """
            <link rel="stylesheet" href="/static/css/estilo.css?v=abc123">
            <img src="/static/img/logo.png">
            <style>body { background: url('/static/img/logo.png'); }</style>
        """
        assets = coletar_assets(html)
        assert set(assets) == {'css/estilo.css', 'css/fonte.ttf', 'img/logo.png'}

    def test_chave_descarta_query_e_fragmento(self, raiz_estatica):
        assets = coletar_assets('<img src="/static/img/logo.png?t=FB9E#x">')
        assert list(assets) == ['img/logo.png']

    def test_ref_relativa_dentro_do_css_resolve_contra_o_css(self, raiz_estatica):
        assets = coletar_assets('<link href="/static/css/estilo.css">')
        assert 'css/fonte.ttf' in assets
        conteudo = base64.b64decode(assets['css/fonte.ttf'].base64)
        assert conteudo == b'fonte binaria'

    def test_sha256_e_base64_conferem_com_o_arquivo(self, raiz_estatica):
        assets = coletar_assets('<img src="/static/img/logo.png">')
        asset = assets['img/logo.png']
        assert asset.sha256 == hashlib.sha256(b'png').hexdigest()
        assert base64.b64decode(asset.base64) == b'png'

    def test_mesmo_conteudo_em_dois_caminhos_gera_o_mesmo_hash(self, raiz_estatica):
        assets = coletar_assets('<img src="/static/img/logo.png"><img src="/static/img/copia.png">')
        assert assets['img/logo.png'].sha256 == assets['img/copia.png'].sha256

    def test_ignora_refs_externas_data_e_media(self, raiz_estatica):
        html = """
            <img src="https://exemplo.edu.br/x.png">
            <img src="data:image/png;base64,AAAA">
            <img src="/media/upload/foto.png">
        """
        assert coletar_assets(html) == {}

    def test_arquivo_inexistente_nao_levanta_e_fica_de_fora(self, raiz_estatica, caplog):
        # O conftest raiz faz logging.disable(CRITICAL) na suíte inteira; sem o
        # at_level (que reabilita via logging.disable), o warning nunca seria
        # emitido e a asserção passaria mesmo sem o logger.warning no código.
        with caplog.at_level(logging.WARNING, logger='djtools.utils.estaticos_pdf'):
            assets = coletar_assets('<img src="/static/img/nao-existe.png">')
        assert assets == {}
        assert 'img/nao-existe.png' in caplog.text

    def test_varre_todos_os_htmls_sem_duplicar(self, raiz_estatica):
        corpo = '<img src="/static/img/logo.png">'
        cabecalho = '<link href="/static/css/estilo.css">'
        rodape = '<link href="/static/css/estilo.css">'
        assets = coletar_assets(corpo, cabecalho, rodape)
        assert set(assets) == {'img/logo.png', 'css/estilo.css', 'css/fonte.ttf'}

    def test_aceita_html_vazio_ou_none(self, raiz_estatica):
        assert coletar_assets('', None) == {}

    def test_chave_nunca_escapa_da_raiz(self, raiz_estatica):
        assert coletar_assets('<img src="/static/../../etc/passwd">') == {}

    @override_settings(STATIC_ROOT='/tmp/static-root-inexistente')
    def test_sem_o_arquivo_em_lugar_nenhum_retorna_vazio(self):
        assert coletar_assets('<img src="/static/qualquer/coisa.png">') == {}

    def test_resolve_pelo_static_root_quando_o_finder_nao_acha(self, tmp_path, settings):
        # Pós-collectstatic: o arquivo só existe no STATIC_ROOT, fora dos static/ dos apps.
        (tmp_path / 'coletado.png').write_bytes(b'png coletado')
        settings.STATICFILES_DIRS = []
        settings.STATIC_ROOT = str(tmp_path)
        finders.get_finder.cache_clear()
        try:
            assets = coletar_assets('<img src="/static/coletado.png">')
            assert set(assets) == {'coletado.png'}
            assert base64.b64decode(assets['coletado.png'].base64) == b'png coletado'
        finally:
            finders.get_finder.cache_clear()


class TestCicloEntreCss:
    def test_import_circular_nao_entra_em_laco(self, tmp_path, settings):
        (tmp_path / 'a.css').write_bytes(b'@import "b.css";')
        (tmp_path / 'b.css').write_bytes(b'@import "a.css";')
        settings.STATICFILES_DIRS = [str(tmp_path)]
        finders.get_finder.cache_clear()
        try:
            assets = coletar_assets('<link href="/static/a.css">')
            assert set(assets) == {'a.css', 'b.css'}
        finally:
            finders.get_finder.cache_clear()

    def test_import_com_url_resolve_o_alvo(self, tmp_path, settings):
        # `@import url("x.css")` existe no repo (djtools/static/.../jquery.ui.base.css).
        (tmp_path / 'base.css').write_bytes(b'@import url("core.css");\n@import url(outro.css);')
        (tmp_path / 'core.css').write_bytes(b'p { color: red; }')
        (tmp_path / 'outro.css').write_bytes(b'p { color: blue; }')
        settings.STATICFILES_DIRS = [str(tmp_path)]
        finders.get_finder.cache_clear()
        try:
            assets = coletar_assets('<link href="/static/base.css">')
            assert set(assets) == {'base.css', 'core.css', 'outro.css'}
        finally:
            finders.get_finder.cache_clear()

    def test_ref_absoluta_dentro_do_css_vira_a_mesma_chave_do_html(self, tmp_path, settings):
        # `url(/static/...)` dentro de CSS existe no repo (djtools/static/djtools/css/anonima.css).
        (tmp_path / 'sub').mkdir()
        (tmp_path / 'sub' / 'tema.css').write_bytes(b'body { background-image: url(/static/sub/logo.svg); }')
        (tmp_path / 'sub' / 'logo.svg').write_bytes(b'<svg/>')
        settings.STATICFILES_DIRS = [str(tmp_path)]
        finders.get_finder.cache_clear()
        try:
            assets = coletar_assets('<link href="/static/sub/tema.css">')
            assert set(assets) == {'sub/tema.css', 'sub/logo.svg'}
        finally:
            finders.get_finder.cache_clear()

    def test_import_url_externo_e_ignorado(self, tmp_path, settings):
        (tmp_path / 'x.css').write_bytes(b"@import url('https://fonts.googleapis.com/css2?family=Open+Sans');")
        settings.STATICFILES_DIRS = [str(tmp_path)]
        finders.get_finder.cache_clear()
        try:
            assert set(coletar_assets('<link href="/static/x.css">')) == {'x.css'}
        finally:
            finders.get_finder.cache_clear()
