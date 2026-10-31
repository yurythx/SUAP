import pytest

from comum.models import Configuracao


@pytest.fixture(autouse=True)
def clear_configuracao_cache():
    Configuracao.clear_cache()


@pytest.mark.django_db
class TestConfiguracaoGetValorPorChave:
    def test_retorna_valor_quando_existe(self):
        Configuracao.objects.create(app='test', chave='foo', valor='bar')
        assert Configuracao.get_valor_por_chave('test', 'foo') == 'bar'

    def test_retorna_none_quando_nao_existe(self):
        assert Configuracao.get_valor_por_chave('test', 'inexistente') is None


@pytest.mark.django_db
class TestConfiguracaoGetValorPorChaveStr:
    def test_chave_ausente_devolve_string_vazia(self):
        assert Configuracao.get_valor_por_chave_str('test', 'inexistente') == ''

    def test_chave_ausente_devolve_padrao(self):
        assert Configuracao.get_valor_por_chave_str('test', 'inexistente', padrao='IFRN') == 'IFRN'

    def test_chave_presente_devolve_valor(self):
        Configuracao.objects.create(app='test', chave='foo', valor='bar')
        assert Configuracao.get_valor_por_chave_str('test', 'foo', padrao='IFRN') == 'bar'

    def test_valor_vazio_devolve_padrao(self):
        Configuracao.objects.create(app='test', chave='foo', valor='')
        assert Configuracao.get_valor_por_chave_str('test', 'foo', padrao='IFRN') == 'IFRN'


class TestConfiguracaoEhEmailInstitucional:
    @pytest.fixture(autouse=True)
    def _dominios_institucionais(self, monkeypatch):
        monkeypatch.setattr(
            Configuracao,
            'get_valor_por_chave',
            lambda app, chave: '@ifrn.edu.br;@escolar.ifrn.edu.br' if (app, chave) == ('comum', 'dominios_institucionais') else None,
        )

    @pytest.mark.parametrize(
        ('email', 'expected'),
        [
            ('user@ifrn.edu.br', True),
            ('user@escolar.ifrn.edu.br', True),
            ('user@gmail.com', False),
            (None, False),
            ('', False),
        ],
    )
    def test_identifica_email_institucional(self, email, expected):
        assert Configuracao.eh_email_institucional(email) is expected


class TestConfiguracaoEmailInstitucionalPermitido:
    def _configurar_dominios(self, monkeypatch, valor):
        monkeypatch.setattr(
            Configuracao,
            'get_valor_por_chave',
            lambda app, chave: valor if (app, chave) == ('comum', 'dominios_institucionais') else None,
        )

    @pytest.mark.parametrize(
        ('email', 'expected'),
        [
            ('user@ifrn.edu.br', True),
            ('user@escolar.ifrn.edu.br', True),
            # Servidor cedido/redistribuído: SIAPE traz o e-mail do órgão de origem.
            ('user@ifpb.edu.br', False),
            ('user@gmail.com', False),
        ],
    )
    def test_barra_dominio_de_terceiros_quando_ha_dominios_configurados(self, monkeypatch, email, expected):
        self._configurar_dominios(monkeypatch, '@ifrn.edu.br;@escolar.ifrn.edu.br')
        assert Configuracao.email_institucional_permitido(email) is expected

    def test_pedaco_vazio_na_lista_de_dominios_nao_libera_terceiros(self, monkeypatch):
        # '@ifrn.edu.br;' tem um pedaço vazio, e '' está contido em qualquer e-mail.
        self._configurar_dominios(monkeypatch, '@ifrn.edu.br;')
        assert Configuracao.email_institucional_permitido('user@ifpb.edu.br') is False
        assert Configuracao.email_institucional_permitido('user@ifrn.edu.br') is True

    @pytest.mark.parametrize('email', ['user@ifpb.edu.br', 'user@gmail.com', ''])
    def test_aceita_qualquer_email_quando_nao_ha_dominios_configurados(self, monkeypatch, email):
        self._configurar_dominios(monkeypatch, None)
        assert Configuracao.email_institucional_permitido(email) is True


@pytest.mark.django_db
class TestConfiguracaoClearCache:
    def test_clear_cache_invalida_cache(self):
        Configuracao.objects.create(app='test', chave='foo', valor='bar')
        assert Configuracao.get_valor_por_chave('test', 'foo') == 'bar'
        Configuracao.objects.filter(app='test', chave='foo').update(valor='baz')
        assert Configuracao.get_valor_por_chave('test', 'foo') == 'bar'
        Configuracao.clear_cache()
        assert Configuracao.get_valor_por_chave('test', 'foo') == 'baz'

    def test_save_invalida_cache(self):
        cfg = Configuracao.objects.create(app='test', chave='foo', valor='bar')
        assert Configuracao.get_valor_por_chave('test', 'foo') == 'bar'
        cfg.valor = 'baz'
        cfg.save()
        assert Configuracao.get_valor_por_chave('test', 'foo') == 'baz'
