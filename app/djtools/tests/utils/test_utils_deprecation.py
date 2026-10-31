import warnings

from djtools.utils.deprecation import deprecated, unused
import pytest


class TestUnused:
    def test_unused_returns_same_function(self):
        def foo():
            return 42

        decorated = unused(foo)
        assert decorated is foo
        assert foo() == 42


class TestDeprecated:
    def test_missing_reason_raises_typeerror(self):
        with pytest.raises(TypeError):
            deprecated()

    def test_missing_expire_date_raises_typeerror(self):
        with pytest.raises(TypeError):
            deprecated(reason='Use bar instead')

    def test_decorated_function_emits_warning(self):
        @deprecated(reason='Use bar instead', expire_date='2099-12-31')
        def foo():
            return 42

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter('always')
            result = foo()

        assert result == 42
        assert len(w) >= 1
        messages = [str(x.message) for x in w]
        assert any('Use bar instead' in m for m in messages)

    def test_decorated_class_emits_warning(self):
        @deprecated(reason='Use Bar instead', expire_date='2099-12-31')
        class Foo:
            pass

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter('always')
            Foo()

        assert len(w) >= 1
        messages = [str(x.message) for x in w]
        assert any('Call to deprecated class' in m for m in messages)

    def test_expired_date_emits_critical_warning(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter('always')

            @deprecated(reason='Use bar instead', expire_date='2000-01-01')
            def foo():
                return 42

            result = foo()

        assert result == 42
        assert len(w) >= 1
        messages = [str(x.message) for x in w]
        assert any('CRITICO' in m or 'deveria' in m for m in messages)

    def test_default_action_filter_always(self):
        @deprecated(reason='Replaced by new_func', expire_date='2099-12-31')
        def foo():
            return 42

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter('always')
            foo()

        deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert len(deprecation_warnings) >= 1

    def test_reason_in_warning_message(self):
        @deprecated(reason='Use bar instead', expire_date='2099-12-31')
        def foo():
            return 42

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter('always')
            foo()

        messages = [str(x.message) for x in w]
        assert any('Use bar instead' in m for m in messages)

    def test_expire_date_shown_in_warning(self):
        @deprecated(reason='Use bar', expire_date='2099-12-31')
        def foo():
            return 42

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter('always')
            foo()

        messages = [str(x.message) for x in w]
        assert any('2099-12-31' in m for m in messages)
