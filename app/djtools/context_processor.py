import os
import socket
from datetime import datetime

from django.conf import settings
from django.templatetags.static import static

from djtools.menu import get_menu_json_as_html
from djtools.utils import running_tests
from suap import nomenclatura


def suap_context_processor(request):
    """Popula o contexto de template com dados globais do SUAP.

    Args:
        request: objeto ``HttpRequest`` da view em processamento.

    Returns:
        ``dict`` com variáveis de template como menu, tema, notificações,
        nome da instituição e configuração do TinyMCE.
    """
    from comum.models import Configuracao, Preferencia, RegistroNotificacao

    if request.user is None:
        return {}

    if not request.session.get('menu_as_html', ''):  # O usuário acabou de logar
        request.session['menu_as_html'] = get_menu_json_as_html(request.user)

    display_email = None
    if settings.DEBUG:
        emails_file_path = 'deploy/emails.json'
        display_email = os.path.exists(emails_file_path)

    notificacoes_nao_lidas = 0
    try:
        nome_instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao')

        if request.user.is_authenticated:
            notificacoes_nao_lidas = RegistroNotificacao.contar_nao_lidas(request.user)
    except Exception:
        nome_instituicao = ''

    if (not request.session.get('theme')) and request.user.is_authenticated:
        try:
            preferencia = Preferencia.objects.filter(usuario=request.user).first()
            if preferencia:
                request.session['theme'] = preferencia.tema or Preferencia.get_tema_padrao_usuario_autenticado()
            else:
                request.session['theme'] = Preferencia.get_tema_padrao_usuario_autenticado()
        except Exception:
            request.session['theme'] = Preferencia.get_tema_padrao_usuario_autenticado()

    if not request.session.get('usuario_logado_eh_aluno') and request.user.is_authenticated:
        try:
            request.session['usuario_logado_eh_aluno'] = request.user.get_vinculo() and request.user.get_vinculo().eh_aluno()
        except Exception:
            request.session['usuario_logado_eh_aluno'] = True

    server_alias = getattr(settings, 'SERVER_ALIAS', '')
    host_name = server_alias and f'{server_alias} - {socket.gethostname()}' or socket.gethostname()

    paths_ignorar_botao_reportar_erro = [
        '/erros',
        '/admin/erros',
        '/djtools/view_task',
        '/djtools/process',
    ]
    deve_exibir_botao_reportar_erro = not any(request.path.startswith(p) for p in paths_ignorar_botao_reportar_erro) and request.user.is_authenticated

    tinymce_default = {}
    try:
        tinymce_default = dict(getattr(settings, 'TINYMCE_DEFAULT_CONFIG', {}))
        # Se usa pt_BR mas não setou language_url, gera via static()
        if tinymce_default.get('language') == 'pt_BR' and 'language_url' not in tinymce_default:
            tinymce_default['language_url'] = static('tinymce/langs/pt_BR.js')
        # Nunca envie funções no context (setup, images_upload_handler, etc.)
        tinymce_default.pop('setup', None)
        tinymce_default.pop('images_upload_handler', None)
    except Exception:
        tinymce_default = {}

    ctx = {
        'super_template': request.user.is_authenticated and 'admin/base.html' or 'admin/base_anonima.html',
        'debug': settings.DEBUG,
        'local': settings.SUAP_ENVIRONMENT == 'dev' and settings.DEBUG,
        'server_alias': server_alias,
        'suap_version': getattr(settings, 'SUAP_VERSION', '0.0.1'),
        'now': datetime.now(),
        'usuario_logado_eh_aluno': request.session.get('usuario_logado_eh_aluno', True),
        'menu_as_html': request.session.get('menu_as_html', ''),
        'menu_item_id': request.session.get('menu_item_id', ''),
        'nome_instituicao': nome_instituicao,
        'host_name': host_name,
        'extra_css': settings.EXTRA_CSS,
        'extra_js': settings.EXTRA_JS,
        'eh_para_documentar': settings.BEHAVE_AUTO_DOC,
        'display_email': display_email,
        'is_popup': request.GET.get('_popup'),
        'theme': request.session.get('theme', Preferencia.PADRAO),
        'anonymous_theme': Preferencia.get_tema_padrao_usuario_anonimo(),
        'nomenclatura': nomenclatura,
        'notificacoes_nao_lidas': notificacoes_nao_lidas,
        'public_index_url': settings.PUBLIC_INDEX_URL or '/',
        'exibir_botao_reportar_erro': deve_exibir_botao_reportar_erro,
        'TINYMCE_DEFAULT_CONFIG': tinymce_default,
        'test_mode': running_tests(),
        'use_pwa': getattr(settings, 'USE_PWA', False),
        'use_sentry': getattr(settings, 'USE_SENTRY', False),
        'sentry_js': getattr(settings, 'SENTRY_JS', None),
        'sentry_environment': getattr(settings, 'SENTRY_ENVIRONMENT', 'production'),
    }

    return ctx
