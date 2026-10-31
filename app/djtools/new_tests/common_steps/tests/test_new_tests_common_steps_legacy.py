"""
Teste behave alternativo que NÃO testa o cliente web.

Define um step "when" e um step "then" para executar uma função python
que retorna uma string como resultado do teste.
"""

from behave import then, when
from hamcrest import assert_that, equal_to

MODULE_TESTS_IN_APPS = 'features.steps.tests'


class MockContext:
    application_text = ''
    feature_text = ''
    scenario_text = ''
    step_text = ''


@when('executo o teste "{test_name}"')
def step_test_run(context, test_name):
    """
    test_name: "app_name.test_function_name"

    app_name.MODULE_TESTS_IN_APPS.py
        ...
        def test_function_name():
            ...
            return "test_result"
        ...
    """

    erro = ''

    try:
        app_name = test_name.split('.')[0].strip()
        module_tests = get_module_tests(app_name)

        test_function_name = test_name.split('.')[1].strip()
        test_fn = getattr(module_tests, test_function_name)

        result = test_fn()

        set_test_result(test_name, result)
    except Exception as e:
        erro = f'{e}'

    assert_that(len(erro), equal_to(0), '{}{}'.format(get_step_id(context), f': {erro}' if erro else ''))


@then('confirmo a mensagem "{test_result}" como resultado do teste "{test_name}"')
def step_test_result(context, test_result, test_name):
    assert_that(test_result.upper(), equal_to(get_test_result(test_name).upper()), get_step_id(context))


def get_scenario_id(context):
    return f'{context.application_text}::{context.feature_text}::{context.scenario_text}'


def get_step_id(context):
    return f'{get_scenario_id(context)}::{context.step_text}'


def get_module_tests(app_name):
    from importlib import import_module

    try:
        module = import_module(f'{app_name}.{MODULE_TESTS_IN_APPS}')
    except Exception as e:
        raise e

    return module


_tests_results = {}


def set_test_result(key, value):
    _tests_results[key] = value


def get_test_result(key):
    return _tests_results.get(key, '')


def get_tests_results():
    return _tests_results
