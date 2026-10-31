import json
import logging
import os
from datetime import date

from django.conf import settings
from django.template.defaultfilters import slugify

from djtools.utils.pdf import generate_pdf

logger = logging.getLogger(__name__)


class BehavePdfDocumentationService:
    template_name = 'documentacao/pdf_app.html'

    def __init__(self, docs_path=None):
        self.docs_path = docs_path or settings.BEHAVE_AUTO_DOC_PATH

    def build_index(self, apps):
        return {'aplicacoes': apps, 'data_atualizacao': date.today().strftime('%d/%m/%Y')}

    def load_index(self):
        index_path = os.path.join(self.docs_path, 'documentacao.json')
        if not os.path.exists(index_path):
            return {}
        with open(index_path) as file:
            return json.load(file)

    def load_app_documentation(self, app_label):
        app_json_path = os.path.join(self.docs_path, app_label, 'documentacao.json')
        if not os.path.exists(app_json_path):
            raise FileNotFoundError(app_json_path)
        with open(app_json_path) as file:
            data = json.load(file)
        return data['aplicacoes'][app_label]

    def build_app_context(self, app_label):
        app_documentation = self.load_app_documentation(app_label)
        index = self.load_index()
        context = {
            'aplicacao': {
                'sigla': app_documentation['sigla'],
                'nome': app_documentation['nome'],
                'area': app_documentation['area'],
                'funcionalidades': [],
            },
            'data_atualizacao': index.get('data_atualizacao'),
        }

        for feature in app_documentation.get('funcionalidades', []):
            workflow_relpath = self._get_feature_workflow_relpath(app_label, feature)
            context['aplicacao']['funcionalidades'].append(
                {
                    'nome': feature['nome'],
                    'descricao': self._normalize_text_lines(feature.get('descricao')),
                    'workflow_relpath': workflow_relpath,
                    'cenarios': [self._build_scenario_context(app_label, scenario) for scenario in feature.get('cenarios', [])],
                }
            )

        return context

    def generate_for_apps(self, apps):
        generated_files = []
        for app_label in apps:
            try:
                generated_files.append(self.generate_for_app(app_label))
            except FileNotFoundError:
                logger.warning('[test_behave] Documentação da app %s não encontrada; PDF não gerado.', app_label)
        return generated_files

    def generate_for_app(self, app_label):
        context = self.build_app_context(app_label)
        app_folder = os.path.join(self.docs_path, app_label)
        os.makedirs(app_folder, exist_ok=True)
        output_path = os.path.join(app_folder, 'documentacao.pdf')
        with open(output_path, 'wb') as pdf_file:
            generate_pdf(self.template_name, file_object=pdf_file, context=context, base_url=self.docs_path)
        logger.info('[test_behave] PDF da documentação gerado: %s', output_path)
        return output_path

    def _build_scenario_context(self, app_label, scenario):
        return {
            'nome': scenario['nome'],
            'descricao': self._normalize_text_lines(scenario.get('descricao')),
            'passos': [self._build_step_context(app_label, step) for step in scenario.get('passos', [])],
        }

    def _build_step_context(self, app_label, step):
        image_name = step.get('imagem')
        image_relpath = None
        if image_name:
            candidate_path = os.path.join(self.docs_path, app_label, image_name)
            if os.path.exists(candidate_path):
                image_relpath = f'{app_label}/{image_name}'
        return {
            'nome': step['nome'],
            'descricao': step.get('descricao', ''),
            'imagem_relpath': image_relpath,
        }

    def _get_feature_workflow_relpath(self, app_label, feature):
        feature_slug = slugify(feature.get('nome', ''))
        relpath = f'workflow/{app_label}/{feature_slug}.png'
        full_path = os.path.join(self.docs_path, relpath)
        return relpath if os.path.exists(full_path) else None

    def _normalize_text_lines(self, values):
        if not values:
            return []
        return [value.strip() for value in values if value and value.strip()]
