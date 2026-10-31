from unittest import mock

import pytest

from pgd2.api_pgd2_v2 import get_api_pgd2_v2


@pytest.mark.django_db
class GetApiPgd2V2Test:
    def test_returns_none_when_api_externa_inactive(self, settings):
        settings.DEBUG = False
        with mock.patch('pgd2.api_pgd2_v2.APIExterna') as APIExternaMock:
            APIExternaMock.PGD.ativo = False

            result = get_api_pgd2_v2()

            assert result is None

    def test_returns_service_when_api_externa_active(self, settings):
        settings.DEBUG = False
        with mock.patch('pgd2.api_pgd2_v2.APIExterna') as APIExternaMock:
            APIExternaMock.PGD.ativo = True

            result = get_api_pgd2_v2()

            assert result is not None

    def test_returns_api_pgd2_v2_when_debug(self, settings):
        settings.DEBUG = True
        result = get_api_pgd2_v2()

        assert result is not None
        assert result.__class__.__name__ == 'ApiPgd2V2'

    def test_does_not_raise_exception_when_inactive(self, settings):
        settings.DEBUG = False
        with mock.patch('pgd2.api_pgd2_v2.APIExterna') as APIExternaMock:
            APIExternaMock.PGD.ativo = False

            try:
                get_api_pgd2_v2()
            except Exception:
                raise AssertionError('get_api_pgd2_v2() raised an exception when API is inactive')

            assert True
