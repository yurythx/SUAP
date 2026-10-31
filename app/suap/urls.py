import os

from django.conf import settings
from django.conf.urls import include
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views
from django.urls import path
from django.views.i18n import set_language
from django.views.static import serve

from comum import views as comum_views
from comum import webservice
from djtools import views as djtools_views
from djtools.utils import running_tests

admin.autodiscover()

handler403 = 'comum.views.permission_denied'
handler404 = 'comum.views.page_not_found'
handler500 = 'comum.views.handler500'

urlpatterns = [
    path('', comum_views.index),
    path('service-worker.js', comum_views.service_worker),
    path('push-web-notification.js', comum_views.push_web_notification),
    path('docs/<str:path>', comum_views.docs, {'tipo': 'tecnica'}),
    path('manuais/<str:path>', comum_views.docs, {'tipo': 'usuario'}),
    path('robots.txt', comum_views.robots),
    path('sentry/debug/', comum_views.trigger_error),
    path('i18n/', include('django.conf.urls.i18n')),
    path('i18n/setlang/', set_language, name='set_language'),
]

urlpatterns += [path('apagar_chave_sessao/<str:chave>/', djtools_views.apagar_chave_sessao)]

urlpatterns += [
    path('json/<str:app_name>/<str:class_name>/', djtools_views.json_view),
    path('chained_select/<str:app_name>/<str:class_name>/', djtools_views.chained_select_view),
]

urlpatterns += [
    path('webservice/', webservice.rpc_handler),
]


# Include de cada app instalada
for app in settings.INSTALLED_APPS:
    if not app.startswith('django.'):
        if settings.LPS:
            if os.path.exists(os.path.join(settings.BASE_DIR, f'{app}/lps/{settings.LPS}/urls.py')):
                urlpatterns += [path(f'{app}/', include(f'{app}.lps.{settings.LPS}.urls'))]
        if os.path.exists(os.path.join(settings.BASE_DIR, f'{app}/urls.py')):
            urlpatterns += [path(f'{app}/', include(f'{app}.urls'))]

urlpatterns += [
    path('accounts/logout/', views.logout_then_login),
    path('accounts/login/', comum_views.login),
    path('admin/login/', comum_views.login),
    path('admin/', admin.site.urls),
    path('o/', include('oauth2_provider.urls', namespace='oauth2_provider')),
    path('ht/', comum_views.healthcheck),
]

# Adiciona a API
if 'api' in settings.INSTALLED_APPS:
    from .api import api

    urlpatterns += [
        path('api/', api.urls, name='api'),
    ]


if 'documento_eletronico' in settings.INSTALLED_APPS:
    from documento_eletronico.views import autenticar_documento as autenticar_documento_eletronico
    from documento_eletronico.views import verificar_documento_externo

    urlpatterns += [path('autenticar-documento/', autenticar_documento_eletronico), path('verificar-documento-externo/', verificar_documento_externo)]

# Isso só funciona em modo DEBUG. Em produção deve haver um mapeamento para STATIC_URL.
if running_tests() or settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    urlpatterns += [path('media/<path:path>', serve, {'document_root': settings.MEDIA_ROOT})]
    urlpatterns += [path('static/<path:path>', serve, {'document_root': settings.STATIC_ROOT})]

if settings.DEBUG or running_tests():
    if 'debug_toolbar' in settings.INSTALLED_APPS:
        import debug_toolbar

        urlpatterns += [path('__debug__/', include(debug_toolbar.urls))]
    if 'silk' in settings.INSTALLED_APPS:
        urlpatterns += [path('silk/', include('silk.urls', namespace='silk'))]
