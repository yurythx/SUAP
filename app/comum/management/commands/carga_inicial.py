from django.conf import settings
from django.core.management import call_command

from comum.models import Pais
from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def add_arguments(self, parser):
        parser.add_argument('modulos', nargs='*', type=str, help='Módulos')

    def handle(self, *args, **options):
        modulos = options['modulos']
        if not modulos:
            modulos = settings.INSTALLED_APPS

        if 'comum' in modulos:
            call_command('carregar_apis')
            call_command('loaddata', 'initial_data')
            call_command('loaddata', 'comum/fixtures/configuracao_inicial.json')
            call_command('loaddata', 'comum/fixtures/initial_data_raca.json')
            call_command('loaddata', 'comum/fixtures/initial_ocupacao.json')
            call_command('loaddata', 'comum/fixtures/initial_data_FuncaoCodigo.json')
            # a fixture traz o ISO 3166-1 alfa-3 que a migration 0121 só preenche em base existente; o importador do SIAPE
            # atualiza nome e situação depois. Com países já carregados, não roda: os ids da fixture sobrescreveriam outros países.
            if not Pais.objects.exists():
                call_command('loaddata', 'comum/fixtures/paises.json')
            call_command('importar_tipo_arquivo_submissao')
            call_command('loaddata', 'comum/fixtures/objetivos_desenvolvimento_sustentavel.json')
            call_command('importar_tarefas_celery_beat')

        if 'rh' in modulos:
            call_command('loaddata', 'rh/fixtures/initial_data_areaconhecimento.json')
            call_command('loaddata', 'rh/fixtures/initial_data_grupodeficiencia.json')
            call_command('loaddata', 'rh/fixtures/initial_data_deficiencia.json')
            call_command('loaddata', 'rh/fixtures/initial_data_indicadores_publicos.json')
            call_command('loaddata', 'rh/fixtures/initial_data_instituicoes.json')

        if 'ae' in modulos:
            call_command('loaddata', 'ae/fixtures/cadastros_gerais.json')
            call_command('loaddata', 'ae/fixtures/carga_motivosolicitacao.json')
            call_command('loaddata', 'ae/fixtures/carga_tipo_programa.json')
            call_command('loaddata', 'ae/fixtures/tipo_bolsa.json')

        if 'almoxarifado' in modulos:
            call_command('carga_inicial_almoxarifado')
            call_command('importar_catmat')

        if 'arquivo' in modulos:
            call_command('importar_funcao_processo')
            call_command('importar_tipo_arquivo')

        if 'avaliacao_cursos' in modulos:
            call_command('loaddata', 'avaliacao_cursos/fixtures/segmentos.json')

        if 'documento_eletronico' in modulos:
            call_command('documento_eletronico_initial')

        if 'conectagov_pen' in modulos:
            call_command('loaddata', 'conectagov_pen/fixtures/initial_data_tipo_documento_pen.json')

        if 'contratos' in modulos:
            call_command('loaddata', 'contratos/fixtures/initial_tipodocumentocomprob.json')
            call_command('importar_dados_contratos')

        if 'demandas_externas' in modulos:
            call_command('loaddata', 'demandas_externas/fixtures/dados_iniciais_modulo.json')

        if 'edu' in modulos:
            call_command('edu_importar_sistec')
            call_command('loaddata', 'edu/fixtures/cadastros_gerais.json')
            call_command('loaddata', 'edu/fixtures/habilitacoes.json')
            call_command('loaddata', 'edu/fixtures/tipos_atividades_aprofundamento.json')
            call_command('loaddata', 'edu/fixtures/InstituicaoEnsinoSuperior.json')
            call_command('loaddata', 'edu/fixtures/cursoformacaosuperior.json')
            call_command('loaddata', 'edu/fixtures/areacursoformacaosuperior.json')
            call_command('importar_disciplinas_arquivo')
            call_command('importar_municipios_edu')

        if 'encceja' in modulos:
            call_command('loaddata', 'encceja/fixtures/dada.json')

        if 'eventos' in modulos:
            call_command('loaddata', 'eventos/fixtures/cadastros-gerais.json')

        if 'financeiro' in modulos:
            call_command('loaddata', 'financeiro/fixtures/financeiro.json')

        if 'patrimonio' in modulos:
            call_command('loaddata', 'patrimonio/fixtures/planocontas.json')

        if 'pesquisa' in modulos:
            call_command('loaddata', 'pesquisa/fixtures/propriedadeintelectual.json')
            call_command('loaddata', 'pesquisa/fixtures/despachosinpi.json')
            call_command('loaddata', 'pesquisa/fixtures/registropatente.json')
            call_command('loaddata', 'pesquisa/fixtures/publicacaopatente.json')
            call_command('loaddata', 'pesquisa/fixtures/transferenciatecnologica.json')
            call_command('loaddata', 'pesquisa/fixtures/2024_registropatente.json')
            call_command('loaddata', 'pesquisa/fixtures/2024_anuidadepatente.json')
            call_command('loaddata', 'pesquisa/fixtures/atividades_sisgen_sisbio.json')
            call_command('loaddata', 'pesquisa/fixtures/parcerias.json')

        if 'pgd' in modulos:
            call_command('pgd_importar_qta')

        if 'processo_eletronico' in modulos:
            call_command('processo_eletronico_initial')

        if 'processo_seletivo' in modulos:
            call_command('loaddata', 'processo_seletivo/fixtures/configuracao_migracao_vaga_inicial.json')

        if 'projetos' in modulos:
            call_command('loaddata', 'projetos/fixtures/projetos.json')
            call_command('loaddata', 'projetos/fixtures/atividades_sisgen_sisbio.json')

        if 'rsc' in modulos:
            call_command('loaddata', 'rsc/fixtures/initial_data_instituicoes.json')

        if 'saude' in modulos:
            call_command('loaddata', 'saude/fixtures/carga_inicial.json')
            call_command('loaddata', 'saude/fixtures/carga_inicial_nutricao.json')
            call_command('loaddata', 'saude/fixtures/carga_inicial_psicologia.json')
            call_command('loaddata', 'saude/fixtures/avaliacaosaude.json')

        if 'temp_rh2' in modulos:
            call_command('loaddata', 'temp_rh2/fixtures/initial_categoria.json')
