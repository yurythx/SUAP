import json
import os
import re
import shutil
import sys
import time
from collections import OrderedDict
from html import unescape
from html.parser import HTMLParser

import graphviz
from behave import register_type
from behave.model_core import Status as StepStatus
from behave.model_type import Status
from django.apps import apps
from django.conf import settings
from django.core.management import call_command
from django.utils.text import slugify
from playwright.sync_api import sync_playwright

from djtools.new_tests.base_test import Aplicacao, Cenario, Documentacao, Funcionalidade, Passo, XPathConstructor
from djtools.new_tests.reuse_successful_scenarios import (
    load_reuse_state,
    mark_scenario_success,
    maybe_skip_reused_scenario,
    print_reuse_summary,
)
from djtools.new_tests.utils import eh_para_documentar, habilitar_inspecao_js
from djtools.utils import get_postgres_uri


class _MarkerHTMLParser(HTMLParser):
    _block_tags = {
        'p',
        'div',
        'li',
        'tr',
        'h1',
        'h2',
        'h3',
        'h4',
        'h5',
        'h6',
        'section',
        'header',
        'footer',
        'article',
        'br',
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._current = None
        self._buffer = []
        self._skip_depth = 0
        self._marker_depth = 0
        self.markers = []

    def handle_starttag(self, tag, attrs):
        if tag in {'script', 'style'}:
            self._skip_depth += 1
            return
        attr_map = dict(attrs)
        class_value = attr_map.get('class', '') or ''
        role_value = attr_map.get('role', '') or ''
        classes = [c.strip() for c in class_value.split() if c.strip()]
        marker_type = None
        if any(c == 'alert' or c.startswith('alert-') for c in classes):
            marker_type = 'ALERT'
        elif 'status' in classes or role_value == 'status' or any(c.startswith('status-') for c in classes):
            marker_type = 'STATUS'
        if marker_type:
            marker = f'[{marker_type} {" ".join(classes)}]'.strip()
            self._current = {'marker': marker, 'lines': []}
            self._buffer = []
            self._marker_depth = 1
            if tag in self._block_tags:
                self._flush_line()
            return
        if self._current:
            self._marker_depth += 1
        if self._current and tag in self._block_tags:
            self._flush_line()

    def handle_endtag(self, tag):
        if self._skip_depth:
            if tag in {'script', 'style'}:
                self._skip_depth -= 1
            return
        if self._current and tag in self._block_tags:
            self._flush_line()
        if self._current:
            self._marker_depth -= 1
            if self._marker_depth <= 0:
                self._finalize_current()

    def handle_data(self, data):
        if self._skip_depth or not self._current:
            return
        text = data.strip()
        if text:
            self._buffer.append(text)

    def _flush_line(self):
        if not self._current:
            return
        if self._buffer:
            line = ' '.join(self._buffer).strip()
            if line:
                self._current['lines'].append(line)
        self._buffer = []

    def _finalize_current(self):
        self._flush_line()
        if self._current:
            self.markers.append((self._current['marker'], self._current['lines']))
        self._current = None
        self._buffer = []


def _extract_markers_from_html(html):
    parser = _MarkerHTMLParser()
    try:
        parser.feed(html or '')
        if parser._current:
            parser._finalize_current()
    except Exception:
        return []
    return parser.markers


def _save_resume_state(context, scenario):
    os.makedirs(context.artifact_path, exist_ok=True)
    resume_file = os.path.join(context.artifact_path, 'last_failed_step.json')
    payload = {
        'feature': scenario.feature.filename,
        'scenario': scenario.name,
        'step': context.step_text,
    }
    with open(resume_file, mode='w') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def get_dependencias(context):
    if settings.BEHAVE_AUTO_DOC:
        for tag in context.tags:
            if 'after_scenario' in tag:
                return tag.split('.')[1]
    return []


def add_documentation_step(context, image_name):
    applicaction = context.documentacao.get_aplicacao(context.application_text)
    feature = applicaction.get_funcionalidade(context.feature_text)
    scenario = feature.get_cenario(context.scenario_text)
    step_text = context.step_text.replace('::', ' :: ')
    scenario.add_passo(Passo(nome=step_text, imagem=image_name, descricao=context.step_description or ''))


def _write_page_dumps(context, project_path, tmp):
    destiny_text_file = os.path.join(project_path, f'page_text{tmp}.txt')
    destiny_html_file = os.path.join(project_path, f'page_html{tmp}.html')
    try:
        page = context.page or context.main_page
        page_html = page.content()

        with open(destiny_html_file, mode='w') as f:
            f.write(page_html)

        formatted_html = page_html
        formatted_html = re.sub(
            r'(?i)<([a-z0-9]+)\b[^>]*class="([^"]*\balert\b[^"]*)"[^>]*>',
            lambda m: f'\n[ALERT {m.group(2).strip()}]\n',
            formatted_html,
        )
        formatted_html = re.sub(
            r'(?i)<([a-z0-9]+)\b[^>]*class=\'([^\']*\balert\b[^\']*)\'[^>]*>',
            lambda m: f'\n[ALERT {m.group(2).strip()}]\n',
            formatted_html,
        )
        formatted_html = re.sub(
            r'(?i)<([a-z0-9]+)\b[^>]*class="([^"]*\b(alert-|status-)?(success|error|warning|danger|info)\b[^"]*)"[^>]*>',
            lambda m: f'\n[STATUS {m.group(2).strip()}]\n',
            formatted_html,
        )
        formatted_html = re.sub(
            r'(?i)<([a-z0-9]+)\b[^>]*class=\'([^\']*\b(alert-|status-)?(success|error|warning|danger|info)\b[^\']*)\'[^>]*>',
            lambda m: f'\n[STATUS {m.group(2).strip()}]\n',
            formatted_html,
        )
        formatted_html = re.sub(r'(?i)<br\s*/?>', '\n', formatted_html)
        formatted_html = re.sub(r'(?i)</(p|div|li|tr|h[1-6]|section|header|footer|article)>', '\n', formatted_html)
        formatted_html = re.sub(r'(?i)<(p|div|li|tr|h[1-6]|section|header|footer|article)\b[^>]*>', '\n', formatted_html)
        formatted_html = re.sub(r'(?i)<(script|style)[^>]*>.*?</\\1>', ' ', formatted_html, flags=re.DOTALL)
        text_content = re.sub(r'<[^>]+>', ' ', formatted_html)
        text_content = unescape(text_content)
        text_content = re.sub(r'[ \t]+\n', '\n', text_content)
        text_content = re.sub(r'\n{3,}', '\n\n', text_content)
        text_content = re.sub(r'[ \t]{2,}', ' ', text_content).strip()

        with open(destiny_text_file, mode='w') as f:
            f.write(f'URL: {page.url}\\n\\n')
            f.write(f'{text_content}\\n')

        context._last_markers = {
            'page': _extract_markers_from_html(page_html),
        }
    except Exception as exc:
        sys.stderr.write(f'\n[WARN] Falha ao gerar page_text: {exc}\n')
        sys.stderr.flush()
    return destiny_text_file, destiny_html_file


def _detect_page_situation(page):
    """Analisa a página atual e retorna uma descrição legível do estado detectado.

    Retorna uma tupla ``(situation, detail)`` onde:
    - ``situation``: chave curta (``'login'``, ``'error_page'``, ``'ok'``).
    - ``detail``: mensagem descritiva para exibir no log.
    """
    try:
        url = page.url or ''
    except Exception:
        return 'unknown', 'Não foi possível obter a URL da página.'

    url_lower = url.lower()

    # --- Tela de login ---
    if '/accounts/login' in url_lower or '/comum/login' in url_lower or url_lower.rstrip('/').endswith('/login'):
        return 'login', (
            'A página atual é a TELA DE LOGIN. O usuário não está autenticado.\n'
            '  Possíveis causas:\n'
            '    - O cenário não possui os steps "Dado acesso a página "/"" e '
            '"Quando realizo o login com o usuário "..." e senha "...""\n'
            '    - A sessão expirou ou o usuário foi deslogado (ex.: sem setor SUAP)\n'
            '    - A feature é separada e não herda login de outra feature'
        )

    # --- Página de erro ---
    if '/500' in url_lower or '/404' in url_lower:
        return 'error_page', f'A página atual é uma página de ERRO ({url}).'

    # --- Logout ---
    if '/logout' in url_lower:
        return 'login', (
            'A página atual é a de LOGOUT. O usuário foi deslogado.\n  Verifique se houve logout automático (ex.: mensagem "sem setor SUAP").'
        )

    return 'ok', ''


def _restore_login_if_needed(context):
    """Restaura sessão de login quando um cenário anterior foi pulado pelo reuso.

    Quando ``--reuse-successful-scenarios`` pula um cenário que continha o step
    de login, os cenários seguintes ficam sem sessão autenticada.  Esta função
    detecta essa situação e executa o login automaticamente usando as
    credenciais armazenadas no cenário pulado.

    Fluxo:
        1. Verifica se há credenciais de login de um cenário pulado
           (``context._last_skipped_login``).
        2. Verifica se o browser está em uma página anônima (login/logout).
        3. Se ambas as condições forem verdadeiras, executa os steps de
           acesso e login via ``context.execute_steps()``.

    Args:
        context: Contexto Behave com possível ``_last_skipped_login`` definido.
    """
    login_info = getattr(context, '_last_skipped_login', None)
    if not login_info:
        return

    try:
        active_page = context.page or context.main_page
        situation, _ = _detect_page_situation(active_page)
    except Exception:
        return

    if situation != 'login':
        return

    usuario = login_info.get('usuario', '')
    senha = login_info.get('senha', '')
    if not usuario or not senha:
        return

    sys.stderr.write(f'[REUSE] Sessão não autenticada detectada. Restaurando login com usuário "{usuario}" (credenciais do cenário pulado).\n')
    sys.stderr.flush()

    try:
        context.execute_steps(f'Dado acesso a página "/"\nQuando realizo o login com o usuário "{usuario}" e senha "{senha}"')
    except Exception as exc:
        sys.stderr.write(f'[WARN] Falha ao restaurar login automaticamente: {exc}\n')
        sys.stderr.flush()


def _write_failure_artifacts(context, scenario):
    if getattr(context, '_artifacts_written', False):
        return
    project_path = context.artifact_path
    os.makedirs(project_path, exist_ok=True)
    tmp = str(time.time())
    destiny_print = os.path.join(project_path, f'screen{tmp}.png')
    context.main_page.screenshot(path=destiny_print, full_page=True)
    origin_log_file = context.log_file
    destiny_log_file = os.path.join(project_path, f'debug{tmp}.log')
    shutil.copy(origin_log_file, destiny_log_file)
    destiny_text_file, destiny_html_file = _write_page_dumps(context, project_path, tmp)
    os.chmod(destiny_print, 0o644)
    os.chmod(destiny_log_file, 0o644)
    if os.path.exists(destiny_text_file):
        os.chmod(destiny_text_file, 0o644)
    if os.path.exists(destiny_html_file):
        os.chmod(destiny_html_file, 0o644)

    # --- Obter URL e situação da página ---
    try:
        active_page = context.page or context.main_page
    except Exception:
        active_page = context.main_page
    try:
        current_url = active_page.url or '(URL não disponível)'
    except Exception:
        current_url = '(URL não disponível)'

    situation, situation_detail = _detect_page_situation(active_page)

    # --- Bloco principal de falha ---
    lines = []
    lines.append('')
    lines.append('')
    lines.append(f'Falha ao executar o cenário: {scenario.name}')
    lines.append(f'  URL atual: {current_url}')
    lines.append('  Artifacts:')
    lines.append(f'    screenshot : {destiny_print}')
    lines.append(f'    debug_log  : {destiny_log_file}')
    if os.path.exists(destiny_text_file):
        lines.append(f'    page_text  : {destiny_text_file}')
    if os.path.exists(destiny_html_file):
        lines.append(f'    page_html  : {destiny_html_file}')
    lines.append('')

    # --- Diagnóstico de situação ---
    if situation == 'login':
        lines.append('[DIAGNÓSTICO] SESSÃO NÃO AUTENTICADA')
        lines.append(f'  {situation_detail}')
        lines.append('')
    elif situation == 'error_page':
        lines.append('[DIAGNÓSTICO] PÁGINA DE ERRO')
        lines.append(f'  {situation_detail}')
        lines.append('')

    lines.append(f'Falha ao executar o step: {context.step_text}')

    sys.stderr.write('\n'.join(lines))

    # --- PAGE_MARKERS ---
    if getattr(context, '_last_markers', None):
        try:
            page_blocks = context._last_markers.get('page', [])

            def _emit_marker_blocks(title, blocks):
                marker_lines = []
                marker_lines.append('')
                marker_lines.append(title)
                if blocks:
                    for marker, content_lines in blocks:
                        marker_lines.append(marker)
                        for line in content_lines:
                            marker_lines.append(f'  {line}')
                else:
                    if situation == 'login':
                        marker_lines.append(
                            '  (Nenhum alerta encontrado — a página é a tela de login. O cenário provavelmente precisa de um step de login.)'
                        )
                    elif situation == 'error_page':
                        marker_lines.append(f'  (Nenhum alerta encontrado — a página é de erro: {current_url})')
                    else:
                        marker_lines.append(f'  (Nenhum alerta/status encontrado na página: {current_url})')
                marker_lines.append(title.replace('[', '[END_').replace(']', ']'))
                marker_lines.append('')
                return marker_lines

            marker_lines = []
            marker_lines.extend(_emit_marker_blocks('[PAGE_MARKERS]', page_blocks))
            sys.stderr.write('\n'.join(marker_lines))
        except Exception as exc:
            sys.stderr.write(f'\n[WARN] Falha ao imprimir page_text: {exc}\n')
    sys.stderr.flush()
    context._artifacts_written = True


# ----------------------------------------------------------------------------------------------------------------------
# Funções ligadas ao behave --------------------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------------------------------------------
def before_all(context):
    os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = 'true'
    playwright = sync_playwright().start()
    context.window_width, context.window_height = map(int, settings.BEHAVE_WINDOW_SIZE.split(','))

    context.browser_context = playwright.chromium.launch_persistent_context(
        user_data_dir='/dev/shm/playwright_profile',
        headless=settings.BEHAVE_CHROME_HEADLESS,
        args=[
            '--no-sandbox',
            '--disable-gpu',
            '--disable-extensions',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--no-first-run',
            '--no-zygote',
            '--disable-renderer-backgrounding',
            '--disable-background-timer-throttling',
        ],
        viewport={'width': context.window_width, 'height': context.window_height},
        slow_mo=0,
    )

    context.page = context.browser_context.new_page()
    context.page.on('dialog', lambda dialog: dialog.accept())
    habilitar_inspecao_js(context)
    context.main_page = context.page

    context.popup = []
    context.xpath = XPathConstructor(context)

    project_path = os.environ.get('CI_PROJECT_DIR', '/tmp')
    project_path = os.path.join(project_path, 'artifacts')
    context.artifact_path = project_path
    os.makedirs(project_path, exist_ok=True)
    try:
        if os.path.isdir(project_path):
            for name in os.listdir(project_path):
                if name.startswith('page_text') and name.endswith('.txt'):
                    os.remove(os.path.join(project_path, name))
    except Exception as exc:
        sys.stderr.write(f'[WARN] Falha ao limpar page_text antigos: {exc}\n')
        sys.stderr.flush()
    load_reuse_state(context)

    context.log_file = os.path.join(settings.BASE_DIR, 'deploy/logs/debug.log')
    with open(context.log_file, 'w'):
        pass

    if settings.BEHAVE_AUTO_DOC:
        context.documentacao = Documentacao()
        shutil.rmtree(settings.BEHAVE_AUTO_DOC_PATH, ignore_errors=True, onexc=None)
        os.makedirs(settings.BEHAVE_AUTO_DOC_PATH, exist_ok=True)


def after_all(context):
    context.browser_context.close()
    context.browser_context = None
    context.popup = None
    context.xpath = None
    print_reuse_summary(context)

    if settings.BEHAVE_AUTO_DOC:
        try:
            for aplicacao in context.documentacao.aplicacoes:
                documentacao_json = context.documentacao.toJSON(aplicacao)
                folder = f'{settings.BEHAVE_AUTO_DOC_PATH}/{aplicacao}'
                os.makedirs(folder, exist_ok=True)
                json_file = f'{folder}/documentacao.json'
                with open(json_file, mode='w') as f:
                    f.write(documentacao_json)
        except Exception as exception:
            sys.stderr.write(str(exception))
            sys.stderr.flush()
    if getattr(settings, 'BEHAVE_AUTO_MOCK', False):
        call_command('migrate', fake=True)
        os.system('pg_dump {} > {}/suap_mock.sql'.format(get_postgres_uri(), settings.BEHAVE_AUTO_MOCK_PATH or '.'))


def before_feature(context, feature):
    app_label = feature.filename.split('/')[0]
    # Limpa credenciais de login de feature anterior (after_feature faz logout)
    context._last_skipped_login = None
    context._last_login = None
    if settings.BEHAVE_AUTO_DOC:
        workflow = graphviz.Digraph(format='png')
        workflow.attr(rankdir='LR')
        context.workflow = workflow
        feature.has_flow = False
        if not context.documentacao.has_aplicacao(app_label):
            app_config = apps.get_app_config(app_label)
            context.documentacao.add_aplicacao(Aplicacao(sigla=app_label, nome=app_config.verbose_name, area=app_config.area))
        aplicacao = context.documentacao.get_aplicacao(app_label)
        bpmns = OrderedDict()
        if os.path.isfile(f'{app_label}/workflows/{slugify(feature.name)}.bpmn'):
            bpmns[f'{app_label}::{feature.name}'] = f'{slugify(feature.name)}.bpmn'
        aplicacao.add_funcionalidade(
            Funcionalidade(feature.name, descricao=feature.description, app_name=feature.filename.split('/')[0], workflows=bpmns)
        )
    context.application_text = app_label
    folder = f'{settings.BEHAVE_AUTO_DOC_PATH}/{app_label}'
    os.makedirs(folder, exist_ok=True)
    context.feature_text = feature.name


def after_feature(context, feature):
    context.execute_steps('Dado acesso a página "/comum/logout/"')
    context.execute_steps('Quando retorna a data do sistema')
    if settings.BEHAVE_AUTO_DOC and feature.has_flow:
        app_label = feature.filename.split('/')[0]
        feature_name = slugify(feature.name)
        workflow = context.workflow
        workflow.render(f'{settings.BEHAVE_AUTO_DOC_PATH}/workflow/{app_label}/{feature_name}')


def before_scenario(context, scenario):
    if eh_para_documentar(context):
        app_label = scenario.feature.filename.split('/')[0]
        workflow = None
        if os.path.isfile(f'{app_label}/workflows/{slugify(scenario.name)}.bpmn'):
            nome = f'{app_label}::{scenario.feature.name}::{scenario.name}'
            workflow = (nome, f'{slugify(scenario.name)}.bpmn')
        context.workflow.node(str(scenario.feature.scenarios.index(scenario)), scenario.name, shape='box')
        for dependencia in get_dependencias(context):
            scenario.feature.has_flow = True
            context.workflow.edge(dependencia, str(scenario.feature.scenarios.index(scenario)))
        feature = context.documentacao.get_aplicacao(context.application_text).get_funcionalidade(context.feature_text)
        feature.add_cenario(Cenario(nome=scenario.name, descricao=scenario.description, funcionalidade=feature.nome, workflow=workflow))
    context.scenario_text = scenario.name
    context._current_scenario = scenario
    context._artifacts_written = False
    if maybe_skip_reused_scenario(context, scenario):
        return
    # Restaura sessão de login se um cenário anterior foi pulado e continha
    # credenciais de login. Sem isso, cenários subsequentes falham com
    # "sessão não autenticada" quando o cenário de login é reutilizado.
    _restore_login_if_needed(context)


def after_scenario(context, scenario):
    if scenario.status == Status.passed:
        mark_scenario_success(context, scenario)
    if scenario.status in [Status.error, Status.failed, Status.hook_error]:
        _save_resume_state(context, scenario)
        _write_failure_artifacts(context, scenario)
        if getattr(settings, 'BEHAVE_DEBUG_ON_ERROR', False):
            debugger = __import__('ipdb')
            debugger.set_trace()

    context.xpath.contexto = ''
    if context.popup:
        context.page = context.popup[0]
        context.popup = []
        context.xpath.page = context.page


def before_step(context, step):
    context.step_text = step.name
    context.step_description = step.text


def after_step(context, step):
    if step.status in [StepStatus.failed, StepStatus.error]:
        scenario = getattr(context, '_current_scenario', None)
        if scenario is None:
            return
        _save_resume_state(context, scenario)
        _write_failure_artifacts(context, scenario)


def parse_optional(text):
    return text.strip()


parse_optional.pattern = r'\s?\w*\s?'
register_type(optional=parse_optional)
