from __future__ import annotations

from copy import deepcopy
from typing import Any

from django import forms
from django.conf import settings
from tinymce.widgets import TinyMCE

# Chaves cujo valor vazio não deve sobrescrever silenciosamente o config herdado.
_CHAVES_NAO_VAZIAS = ('plugins', 'toolbar')


def _get_tinymce_config(config_name: str | None = None, mce_attrs: dict[str, Any] | None = None) -> dict[str, Any]:
    default_config = deepcopy(getattr(settings, 'TINYMCE_DEFAULT_CONFIG', {}))
    configs = getattr(settings, 'TINYMCE_CONFIGS', {})
    selected_config = deepcopy(configs.get(config_name or 'default', {}))
    widget_attrs = deepcopy(mce_attrs or {})

    # Evita que um valor vazio (ex.: plugins='' ou []) zere o config herdado.
    for chave in _CHAVES_NAO_VAZIAS:
        if chave in widget_attrs and not widget_attrs[chave]:
            del widget_attrs[chave]

    config = {**default_config, **selected_config, **widget_attrs}
    # O widget já define o alvo do editor por campo.
    config.pop('selector', None)
    return config


class TinyMCEFormField(forms.CharField):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        config_name = kwargs.pop('config', None)
        mce_attrs = kwargs.pop('mce_attrs', None)
        kwargs.setdefault('widget', TinyMCE(mce_attrs=_get_tinymce_config(config_name, mce_attrs)))
        super().__init__(*args, **kwargs)
