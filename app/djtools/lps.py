from functools import WRAPPER_ASSIGNMENTS, wraps

from django import forms
from django.conf import settings
from django.db import models
from django.forms import forms as fforms
from django.forms import models as fmodels
import logging
import traceback
import inspect
import os

logger = logging.getLogger(__name__)

# TODO: criar LPS para as URLs
# TODO: resolver provlemas de novas views


def display_load_info(app, msg, *args):
    if 'DEBUG_LPS_APP' not in os.environ or (os.environ['DEBUG_LPS_APP'] != app and os.environ['DEBUG_LPS_APP'] != 'all'):
        return
    logger.info('[LPS LOAD] ' + msg, *args)


def display_result_info(attrs, key, value, lps_path):
    app = attrs['__module__'].split('.')[0]
    if 'DEBUG_LPS_APP' not in os.environ or (os.environ['DEBUG_LPS_APP'] != app and os.environ['DEBUG_LPS_APP'] != 'all'):
        return

    if isinstance(value, int):
        logger.info('[LPS LOAD] Primeira linha da definição: %s:%s em %s.%s', lps_path, value, attrs['__module__'], attrs['__qualname__'])
    if callable(value):
        logger.info('[LPS LOAD] Nome da função: %s adicionada à %s.%s', key, attrs['__module__'], attrs['__qualname__'])


def display_debug_info(app, msg, *args):
    if 'DEBUG_LPS_APP' not in os.environ or (os.environ['DEBUG_LPS_APP'] != app and os.environ['DEBUG_LPS_APP'] != 'all'):
        return
    logger.info('[LPS ERROR] ' + msg, *args)
    logger.info('[LPS ERROR] %s', traceback.format_exc())


def set_attrs_klass(attrs, items, lps_path=None):
    for key, value in items:
        if key in ['__module__', '__doc__', '__dict__', '__weakref__']:
            continue
        attrs[key] = value
        display_result_info(attrs, key, value, lps_path)


class MetaModelPlus(models.base.ModelBase):
    def __new__(mcs, name, bases, attrs, **kwargs):
        if is_lps(attrs):
            s_m = attrs['__module__'].split('.')[0]
            parents = [b for b in bases if isinstance(b, models.base.ModelBase)]

            if parents:
                try:
                    mdl = __import__(f'{s_m}.lps.{settings.LPS}.models', fromlist=[('models')])

                    if hasattr(mdl, name):
                        display_load_info(s_m, 'Carregando %s', mdl)
                        Klass = getattr(mdl, name)
                        lps_path = os.path.abspath(inspect.getfile(Klass))
                        set_attrs_klass(attrs, Klass.__dict__.items(), lps_path)

                except SyntaxError:
                    raise SyntaxError
                except ModuleNotFoundError:
                    pass
                except ImportError, AttributeError:
                    display_debug_info(s_m, 'Erro ao carregar: %s.lps.%s.models', s_m, settings.LPS)
                except Exception:
                    pass

        return super().__new__(mcs, name, bases, attrs, **kwargs)


class MetaModelAdminPlus(forms.MediaDefiningClass):
    def __new__(mcs, name, bases, attrs):
        if is_lps(attrs):
            s_m = attrs['__module__'].split('.')
            s_m = '.'.join(s_m[:-1])

            parents = [b for b in bases if isinstance(b, forms.MediaDefiningClass)]

            if parents:
                try:
                    mdl = __import__(f'{s_m}.lps.{settings.LPS}.admin', fromlist=[('admin')])

                    if hasattr(mdl, name):
                        display_load_info(s_m, 'Carregando %s', mdl)
                        Klass = getattr(mdl, name)
                        lps_path = os.path.abspath(inspect.getfile(Klass))
                        set_attrs_klass(attrs, Klass.__dict__.items(), lps_path)

                except ModuleNotFoundError:
                    pass
                except ImportError, AttributeError:
                    display_debug_info(s_m, 'Erro ao carregar: %s.lps.%s.admin', s_m, settings.LPS)
                except Exception:
                    pass

        return super().__new__(mcs, name, bases, attrs)


class MetaFormPlus(fforms.DeclarativeFieldsMetaclass):
    def __new__(mcs, name, bases, attrs):
        if is_lps(attrs):
            s_m = attrs['__module__'].split('.')
            s_m = '.'.join(s_m[:-1])
            parents = [b for b in bases if isinstance(b, fforms.DeclarativeFieldsMetaclass)]

            if parents:
                try:
                    mdl = __import__(f'{s_m}.lps.{settings.LPS}.forms', fromlist=[('forms')])

                    if hasattr(mdl, name):
                        display_load_info(s_m, 'Carregando %s', mdl)
                        Klass = getattr(mdl, name)
                        lps_path = os.path.abspath(inspect.getfile(Klass))
                        set_attrs_klass(attrs, Klass.__dict__.items(), lps_path)

                except ModuleNotFoundError:
                    pass
                except ImportError, AttributeError:
                    display_debug_info(s_m, 'Erro ao carregar: %s.lps.%s.forms', s_m, settings.LPS)
                except Exception:
                    pass

        return super().__new__(mcs, name, bases, attrs)


class MetaModelFormPlus(fmodels.ModelFormMetaclass):
    def __new__(mcs, name, bases, attrs):
        if is_lps(attrs):
            s_m = attrs['__module__'].split('.')
            s_m = '.'.join(s_m[:-1])

            parents = [b for b in bases if isinstance(b, fmodels.ModelFormMetaclass)]

            if parents:
                try:
                    mdl = __import__(f'{s_m}.lps.{settings.LPS}.forms', fromlist=[('forms')])

                    if hasattr(mdl, name):
                        display_load_info(s_m, 'Carregando %s', mdl)
                        Klass = getattr(mdl, name)
                        lps_path = os.path.abspath(inspect.getfile(Klass))
                        set_attrs_klass(attrs, Klass.__dict__.items(), lps_path)

                except ModuleNotFoundError:
                    pass
                except ImportError, AttributeError:
                    display_debug_info(s_m, 'Erro ao carregar: %s.lps.%s.forms', s_m, settings.LPS)
                except Exception:
                    pass

        return super().__new__(mcs, name, bases, attrs)


def is_lps(attrs):
    if settings.LPS:
        module_name = attrs.get('__module__')
        if module_name and module_name.split('.')[0] in settings.INSTALLED_APPS:
            return True
    return False


def lps(func):
    @wraps(func, assigned=WRAPPER_ASSIGNMENTS)
    def inner_func(*args, **kwargs):
        running_func = func
        if settings.LPS:
            try:
                s_m = func.__module__.split('.')
                s_f = '.'.join(s_m[1:])
                s_m = s_m[:-1][0]
                mdl = __import__(f'{s_m}.lps.{settings.LPS}.{s_f}', fromlist=[func.__name__])
                running_func = getattr(mdl, func.__name__)
            except Exception:
                pass
        return running_func(*args, **kwargs)

    return inner_func
