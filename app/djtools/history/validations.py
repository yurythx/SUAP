from django.conf import settings

from djtools.utils import get_qualified_model_name

from .constants import IGNORED_MODELS


def validate_history():
    from django.apps import apps

    KNOWN_FIELDS = ['blank_fields', 'encrypt_fields', 'ignore_fields', 'disabled']

    for model in apps.get_models():
        history = getattr(model, 'History', None)
        if history:
            for k in history.__dict__:
                if not k.startswith('__') and k not in KNOWN_FIELDS:
                    raise Exception(f'The field "{k}" in History of "{get_qualified_model_name(model)}" is unknown')


validate_history()


def check_history_disabled(instance):
    return not settings.USE_HISTORY or get_qualified_model_name(instance) in IGNORED_MODELS or getattr(instance, '__skip_history', False)
