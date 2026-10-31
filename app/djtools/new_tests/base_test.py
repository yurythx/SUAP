import json
from collections import OrderedDict

from django.utils.text import slugify
from playwright._impl._errors import TimeoutError
from playwright.sync_api import expect

from djtools.new_tests.utils import log, wait_for_ajax
from djtools.utils import retirar_preposicoes_nome


class Passo:
    def __init__(self, nome, imagem, descricao=''):
        self.nome = nome[0].upper() + nome[1:]
        self.descricao = descricao
        self.imagem = imagem.split('/')[-1]

    def default(self, o):
        return


class Cenario:
    def __init__(self, nome, descricao, funcionalidade, workflow=None):
        self.nome = nome
        self.descricao = descricao
        self.passos = []
        self.workflows = OrderedDict()
        if workflow:
            self.add_workflow(workflow)

    def add_passo(self, passo):
        self.passos.append(passo)

    def add_workflow(self, workflow):
        self.workflows[workflow[0]] = workflow[1]


class Funcionalidade:
    def __init__(self, nome, descricao, app_name, workflows=None):
        if workflows is None:
            workflows = OrderedDict()
        self.nome = nome
        self.descricao = descricao
        self.app_name = app_name
        self.cenarios = OrderedDict()
        self.workflows = workflows

    def add_cenario(self, cenario):
        self.cenarios[slugify(cenario.nome.strip())] = cenario

    def get_cenario(self, cenario):
        return self.cenarios[slugify(cenario.strip())]

    def has_cenario(self, cenario):
        return cenario.strip() in self.cenarios

    def add_workflow(self, workflow):
        self.workflows[workflow[0]] = workflow[1]


class Aplicacao:
    def __init__(self, sigla, nome, area):
        self.sigla = sigla
        self.nome = nome
        self.area = area
        self.funcionalidades = OrderedDict()

    def add_funcionalidade(self, funcionalidade):
        self.funcionalidades[funcionalidade.nome] = funcionalidade

    def get_funcionalidade(self, funcionalidade):
        return self.funcionalidades[funcionalidade]

    def has_funcionalidade(self, funcionalidade):
        return funcionalidade.strip() in self.funcionalidades


class Documentacao:
    def __init__(self):
        self.aplicacoes = OrderedDict()

    def add_aplicacao(self, aplicacao):
        self.aplicacoes[aplicacao.sigla.strip()] = aplicacao

    def get_aplicacao(self, aplicacao):
        return self.aplicacoes[aplicacao.strip()]

    def has_aplicacao(self, aplicacao):
        return aplicacao.strip() in self.aplicacoes

    def toJSON(self, app):
        my_json = OrderedDict()

        my_json['aplicacoes'] = OrderedDict()
        for a in self.aplicacoes.values():
            if app == a.sigla:
                aplicacao = OrderedDict()
                aplicacao['sigla'] = a.sigla
                aplicacao['nome'] = a.nome
                aplicacao['area'] = a.area
                aplicacao['funcionalidades'] = []
                aplicacao['workflows'] = OrderedDict()

                for k_f, f in list(a.funcionalidades.items()):
                    funcionalidade = OrderedDict()
                    funcionalidade['chave'] = k_f
                    funcionalidade['nome'] = f.nome
                    funcionalidade['descricao'] = list(f.descricao)
                    funcionalidade['app_name'] = f.app_name
                    funcionalidade['cenarios'] = []
                    if f.workflows:
                        aplicacao['workflows'].update(f.workflows)

                    for k_c, c in list(f.cenarios.items()):
                        cenario = OrderedDict()
                        cenario['chave'] = k_c
                        cenario['nome'] = c.nome
                        cenario['descricao'] = list(c.descricao)
                        cenario['passos'] = []
                        if f.workflows:
                            aplicacao['workflows'].update(c.workflows)

                        for p in c.passos:
                            passo = OrderedDict()
                            passo['nome'] = p.nome
                            passo['imagem'] = p.imagem
                            passo['descricao'] = p.descricao
                            cenario['passos'].append(passo)

                        funcionalidade['cenarios'].append(cenario)
                    aplicacao['funcionalidades'].append(funcionalidade)
                my_json['aplicacoes'][a.sigla] = aplicacao

        return json.dumps(my_json)


INPUT_TYPES = {
    'texto': 'input',
    'senha': 'password',
    'data': 'input',
    'datahora': 'input',
    'hora': 'input',
    'valor': 'input',
    'numero': 'input',
    'arquivo': 'file',
    'arquivo real': 'file',
    'checkbox': 'input',
    'checkbox multiplo': 'multiplecheckbox',
    'checkbox popup': 'multiplecheckbox',
    'textarea': 'textarea',
    'lista': 'select',
    'arvore': 'arvore',
    'radio': 'radio',
    'busca': 'busca',
    'autocomplete': 'autocomplete',
    'autocomplete multiplo': 'autocomplete multiplo',
    'filteredselectmultiple': 'filteredselectmultiple',
    'captcha': 'captcha',
    'texto rico': 'iframe',
}


class XPathConstructor:
    MSG_ERROR = 0
    MSG_INFO = 1
    MSG_SUCESS = 2
    MSG_ALERT = 3

    def __init__(self, behave_context):
        self.behave_context = behave_context
        self.contexto = ''
        self.xpath = ''
        self.page = behave_context.page

    def get(self, nth=0):
        log(self)
        result = self.page.locator(self.xpath).nth(nth)
        expect(result).to_be_visible()
        return result

    def get_first_visible(self):
        log(self)
        wait_for_ajax(self.behave_context, timeout=10)
        result = self.page.locator(self.xpath).all()
        for r in result:
            if r.is_visible():
                expect(r).to_be_visible()
                return r
        expect(result[0]).to_be_visible()
        return result[0]

    def get_all(self):
        log(self)
        wait_for_ajax(self.behave_context, timeout=10)
        result = self.page.locator(self.xpath).all()
        return result

    def is_in_dom(self, timeout=2000):
        """Diz se o elemento existe no DOM, esperando no máximo `timeout` ms por ele.

        O padrão baixo é proposital: há chamadas em que a resposta esperada é NEGATIVA
        (`then.py:step_ver_mensagem` afirma ausência; `when.py` detecta se um inline é
        tabular), e subir o padrão faria cada uma delas pagar o timeout inteiro. Quem afirma
        presença — e portanto só perde tempo quando algo está errado — passa um valor maior.
        """
        log(self)
        try:
            self.page.locator(self.xpath).first.wait_for(state='attached', timeout=timeout)
            return True
        except TimeoutError:
            return False

    def reset(self):
        self.xpath = ''
        return self

    def find_item_menu(self, items):
        self.xpath += f'//nav/descendant::a[ancestor::ul[contains(@class, "_main_menu")] and @title="{items[0]}"]'
        for item in items[1:]:
            self.xpath += f'/following-sibling::ul/child::*/a[@title="{item}"]'

    def find_filters(self):
        self.xpath = f'{self.contexto}//div[contains(@class, "search-and-filters")]'

    def find_box(self, box_name):
        box_modulo = f'//div[contains(@class, "modulo") and div//h3[contains(normalize-space(.), "{box_name}")]]'
        box_box = f'//div[contains(@class, "accordion") and h2[contains(normalize-space(.), "{box_name}")]]'
        box_alertas = f'//div[contains(@class, "modulo") and h3[contains(normalize-space(.), "{box_name}")]]'
        box_fieldset = f'//fieldset[contains(@class, "module") and h2[contains(normalize-space(.), "{box_name}")]]'
        self.xpath = f'({box_modulo}|{box_box}|{box_alertas}|{box_fieldset})'

    def find_box_info(self, box_name, informacao):
        self.xpath = f'//div[contains(@class, "extra-info") and contains(normalize-space(.), "{informacao}")]/ancestor::div[contains(@class, "general-box") and div//h4[contains(normalize-space(.), "{box_name}")]]'

    # Form elements methods --------------------------------------------------------------------------------------------

    def find_menu_input(self):
        self.xpath += f'{self.contexto}//input[@id="__filterinput__"]'

    def find_user(self):
        self.xpath = '//div[@id="user-tools"]/a/span'

    def find_form_input(self, label_name, type_input, value_input=None):
        find_label = label_name
        value = ''
        if value_input is not None:
            value = f' and ancestor::*/label[contains(normalize-space(.), "{value_input}")]'
        if label_name[-1] not in [':', '?', '.', '!']:
            find_label = f'{label_name}:'
        if INPUT_TYPES[type_input] == 'select':
            self.xpath += f'{self.contexto}//{INPUT_TYPES[type_input]}[ancestor::*/label[normalize-space(text())="{find_label}"]]'
        elif type_input == 'checkbox':
            self.xpath += f'{self.contexto}//{INPUT_TYPES[type_input]}[following-sibling::label[contains(normalize-space(.),"{find_label[:-1]}")] or preceding-sibling::label[contains(normalize-space(.), "{find_label[:-1]}")]]'
        elif INPUT_TYPES[type_input] == 'textarea':
            self.xpath += f'{self.contexto}//{INPUT_TYPES[type_input]}[ancestor::*/label[normalize-space(text())="{find_label}"]]'
        elif INPUT_TYPES[type_input] == 'autocomplete multiplo':
            self.xpath += f'{self.contexto}//input[ancestor::*/label[normalize-space(text())="{find_label}"] and @type="text"]|//span[ancestor::*/label[normalize-space(text())="{find_label}"]]'
        elif INPUT_TYPES[type_input] == 'filteredselectmultiple':
            self.xpath += f'{self.contexto}//select[ancestor::*/label[normalize-space(text())="{find_label}"]]'
        elif INPUT_TYPES[type_input] == 'autocomplete':
            self.xpath += f'{self.contexto}//span[ancestor::*/label[normalize-space(text())="{find_label}"]]'
        elif INPUT_TYPES[type_input] == 'busca':
            self.xpath += f'{self.contexto}//a[contains(@class, "btn") and preceding-sibling::label[contains(normalize-space(.), "{find_label}")]]'
        elif type_input == 'radio':
            self.xpath += f'{self.contexto}//input[ancestor::*/label[contains(normalize-space(.), "{find_label}")]{value} and @type="radio"]'
        elif INPUT_TYPES[type_input] == 'multiplecheckbox':
            self.xpath += f'{self.contexto}//input[ancestor::*/label[normalize-space(text())="{find_label}"]{value}]'
        elif INPUT_TYPES[type_input] == 'file':
            self.xpath = f'{self.contexto}//label[contains(normalize-space(.), "{label_name}")]/following-sibling::div/input[@type="file"]'
        elif INPUT_TYPES[type_input] == 'password':
            self.xpath = f'{self.contexto}//label[contains(normalize-space(.), "{label_name}")]/following-sibling::div/input[@type="password"]'
        elif INPUT_TYPES[type_input] == 'captcha':
            self.xpath = f'//label[normalize-space(text())="{find_label}"]'
        elif INPUT_TYPES[type_input] == 'iframe':
            self.xpath = f'{self.contexto}//label[contains(normalize-space(.), "{label_name}")]/following-sibling::div//iframe'
        else:
            self.xpath += f'{self.contexto}//{INPUT_TYPES[type_input]}[preceding-sibling::label[normalize-space(text())="{find_label}"]]'
            # xpath do filtro do admin
            self.xpath += f'|//div[contains(@class, "search-and-filters")]//input[ancestor::div[contains(@class, "filter")]//label[normalize-space(text())="{find_label}"]]'

    def find_forminline_input(self, type_input):
        self.xpath += f'{self.contexto}'
        if INPUT_TYPES[type_input] == 'select':
            self.xpath = "//select[not(contains(@name, '__prefix__'))]"
        else:
            self.xpath += f"//{INPUT_TYPES[type_input]}[not(contains(@name, '__prefix__')) and not(@type='hidden')]"

    def find_form_select_option(self, value):
        self.xpath += f'//option[contains(normalize-space(.), "{value}")]'

    def find_form_arvore(self, value):
        self.xpath += f'//a[contains(@class, "jstree-anchor") and text()="{value}"]'

    def find_form_inline_select(self, line, column):
        coluna = retirar_preposicoes_nome(column).replace(' ', '_')
        self.xpath += f'//select[contains(@name, "-{line}-{coluna}")]'

    def find_form_inline_input(self, line, column):
        self.xpath += f'//input[contains(@name, "-{line}-{column}")]'

    def find_form_inline_checkbox(self, line, column):
        coluna = retirar_preposicoes_nome(column).replace(' ', '_')
        self.xpath += f'//input[contains(@name, "-{line}-{coluna}")]'

    def find_submit_button(self, button_name):
        self.xpath += f'{self.contexto}//input[@type="submit" and @value="{button_name}"]'

    def find_submit_button_nonstandard(self, button_name):
        self.xpath += f'{self.contexto}//input[@type="button" and @value="{button_name}"]'

    def find_submit_button_action(self, button_name):
        self.xpath += f'{self.contexto}//button[@type="submit" and @value="{button_name}"]'

    def find_filter_button(self, button_name):
        self.xpath += f'{self.contexto}//button[@type="submit" and contains(., "{button_name}")]'

    def find_just_button(self, button_name):
        self.xpath += f'{self.contexto}//button[contains(., "{button_name}")]'

    def find_just_button_by_class(self, class_name):
        self.xpath += f'{self.contexto}//button[contains(@class, "{class_name}")]'

    def find_input_error(self, label_name, error_text):
        base_xpath = (
            f'{self.contexto}//label[contains(normalize-space(.), "{label_name}") and ancestor::*//li[contains(normalize-space(.), "{error_text}")]]'
        )
        self.xpath += base_xpath
        return self

    # HTML specific elements -------------------------------------------------------------------------------------------

    def find_html_table(self, class_name=None, id_name=None):
        self.xpath += f'{self.contexto}//table'

        filters = []

        if class_name is not None:
            filters.append(f'contains(@class, "{class_name}")')

        if id_name is not None:
            filters.append(f'@id="{id_name}"')

        if len(filters) > 0:
            self.xpath += '[{}]'.format(' and '.join(filters))

    def find_html_tr(self, text=None, class_name=None):
        self.xpath += f'{self.contexto}//tr'

        filters = []

        if text is not None:
            filters.append(f'descendant-or-self::*[contains(normalize-space(.), "{text}")]')

        if class_name is not None:
            filters.append(f'contains(@class, "{class_name}")')

        if len(filters) > 0:
            self.xpath += '[{}]'.format(' and '.join(filters))

    def find_div_text(self, texto):
        self.xpath += f'{self.contexto}//div[contains(text(), "{texto}")]'

    # Other methods ----------------------------------------------------------------------------------------------------
    def find_button(self, button_name):
        self.find_submit_button(button_name)
        self.xpath += '|'
        self.find_link_button(button_name)
        self.xpath += '|'
        self.find_submit_button_nonstandard(button_name)
        self.xpath += '|'
        self.find_filter_button(button_name)
        self.xpath += '|'
        self.find_just_button(button_name)

    def find_link_button(self, button_name):
        # Find links on action bar
        self.xpath += f'{self.contexto}//a[contains(normalize-space(.), "{button_name}") and ancestor::ul[contains(@class, "action-bar")]]'
        self.xpath += f'|{self.contexto}//a[contains(normalize-space(.), "{button_name}") and contains(@class, "btn")]'
        self.xpath += f'|{self.contexto}//a[contains(@title, "{button_name}") and contains(@class, "btn")]'
        self.xpath += f'|{self.contexto}//a[contains(normalize-space(.), "{button_name}") and ancestor::ul[contains(@class, "pills")]]'

    def find_button_action(self, button_name):
        self.find_submit_button_action(button_name)
        self.xpath += '|'
        self.find_link_button_action(button_name)

    def find_link_button_action(self, button_name):
        # Find links on div actions
        self.xpath += f'{self.contexto}//button[contains(normalize-space(.), "{button_name}") and ancestor::div[contains(@class, "actions")]]'

    def find_link(self, value):
        # https://stackoverflow.com/questions/34593753/testing-text-nodes-vs-string-values-in-xpath?answertab=votes#tab-top
        self.xpath += f'{self.contexto}//a[contains(., "{value}")]'

    def find_link_h4(self, value):
        self.xpath += f'{self.contexto}//a[descendant::h4[text()="{value}"]]'

    def find_custom_checkbox(self, value):
        self.xpath += f'{self.contexto}//h4[descendant::*[normalize-space(text())="{value}"]]/parent::*/preceding-sibling::*//label'
        self.xpath += '|'
        self.xpath += f'{self.contexto}//h4[normalize-space(text())="{value}"]/parent::*/preceding-sibling::*//label'

    def find_html_element(self, element, class_name=None, id_name=None, text=None):
        xfilter = []

        if class_name is not None:
            xfilter.append(f'contains(@class, "{class_name}")')

        if id_name is not None:
            xfilter.append(f'@id="{id_name}"')

        if text is not None:
            xfilter.append(f'contains(normalize-space(.), "{text}")')

        self.xpath += f'{self.contexto}//{element}'

        if len(xfilter) > 0:
            self.xpath += '[{}]'.format(' and '.join(xfilter))

    def find_item_autocomplete(self, autocomplete, item):
        filter_img = f'//li[contains(@title, "{item}")]//parent::button[ancestor::*/label[contains(., "{autocomplete}")]]'

        self.xpath += f'{self.contexto}{filter_img}'

    def find_message(self, type, text):
        class_name = 'info'
        if type == self.MSG_SUCESS:
            class_name = 'success'
        elif type == self.MSG_INFO:
            class_name = 'info'
        elif type == self.MSG_ERROR:
            class_name = 'errornote'
        elif type == self.MSG_ALERT:
            class_name = 'warning'
        self.xpath += f'{self.contexto}//p[contains(@class, {class_name}) and contains(normalize-space(.), "{text}")]'

    def find_tab(self, name):
        self.xpath += f'{self.contexto}//*[contains(@class, "nav-link") and contains(normalize-space(.), "{name}") and ancestor::*[contains(@class, "nav-tabs")]]'

    def find_tab_content(self, name):
        self.xpath += f'{self.contexto}//div[contains(@data-title, "{name}") and contains(@class, "tab-pane") and not(contains(@class, "d-none"))]'

    def find_stat(self, name):
        self.xpath += f'{self.contexto}//p[@class="description" and contains(normalize-space(string()), "{name}") and ancestor::*[contains(@class, "flex-container boxes infos")]]'
        self.xpath += '|'
        self.xpath += f'{self.contexto}//p[@class="description" and contains(normalize-space(string()), "{name}") and ancestor::*[contains(@class, "total-container")]]'

    def find_textarea(self, name):
        self.xpath += f'//h4[contains(normalize-space(.),"{name}")]/parent::*//textarea'

    def find_stat_value(self, name, value):
        self.xpath += f'{self.contexto}//p[@class="description" and contains(normalize-space(string()), "{name}") and ancestor::*[contains(@class, "flex-container boxes infos")]]/preceding-sibling::p[contains(@class, "stat") and contains(normalize-space(string()), "{value}")]'
        self.xpath += '|'
        self.xpath += f'{self.contexto}//p[@class="description" and contains(normalize-space(string()), "{name}") and ancestor::*[contains(@class, "total-container")]]/preceding-sibling::p[contains(@class, "total") and contains(normalize-space(string()), "{value}")]'

    def find_form_filteredselectmultiple_add(self, label_name):
        find_label = label_name
        if label_name[-1] != ':':
            find_label = f'{label_name}:'
        self.xpath += f'{self.contexto}//button[ancestor::*/label[normalize-space(text())="{find_label}"] and contains(@class, "selector-add")]'

    def find_form_filteredselectmultiple_remove(self, label_name):
        find_label = label_name
        if label_name[-1] != ':':
            find_label = f'{label_name}:'
        self.xpath += f'{self.contexto}//button[ancestor::*/label[normalize-space(text())="{find_label}"] and contains(@class, "selector-remove")]'

    def find_checkbox(self, label_name):
        self.xpath += f'{self.contexto}//input[ancestor::tr[contains(normalize-space(.), "{label_name}")]]'

    def find_inline_input(self, input_name):
        self.xpath += f'{self.contexto}//input[@type="text" and @name="{input_name}"]'

    def find_inline_select2(self, campo, idx_inline=1):
        """
        Monta o xpath para o select2/autocomplete de um campo em um inline Django Admin.
        """
        # Busca todos os inlines (exceto o empty-form)
        inlines_xpath = "//div[contains(@class, 'inline-related') and not(contains(@class, 'empty-form'))]"
        # Seleciona o inline pelo índice
        inline_xpath = f'({inlines_xpath})[{idx_inline}]'
        # Seleciona o campo pelo nome
        campo_xpath = f"{inline_xpath}//div[contains(@class, 'form-row') and contains(@class, 'field-{campo.lower().replace(' ', '_')}')]"
        # Busca o select do select2/autocomplete
        self.xpath = f"{campo_xpath}//select[contains(@class, 'js-example-data-ajax')]"
        return self
