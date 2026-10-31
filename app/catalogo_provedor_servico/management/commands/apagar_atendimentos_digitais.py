from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import transaction

from catalogo_provedor_servico.models import Solicitacao
from comum.models import Configuracao

ID_GOVBR_6176_MATRICULA_EAD = int(Configuracao.get_valor_por_chave('catalogo_provedor_servico', 'codigo_matricula_ead') or 0)
ID_GOVBR_6410_MATRICULA_CURSO_NIVEL_TECNICO_IFRN = int(Configuracao.get_valor_por_chave('catalogo_provedor_servico', 'codigo_matricula_tecnico') or 0)
ID_GOVBR_6424_MATRICULA_CURSO_NIVEL_SUPERIOR_IFRN = int(
    Configuracao.get_valor_por_chave('catalogo_provedor_servico', 'codigo_matricula_superior') or 0
)
ID_GOVBR_10054_MATRICULA_POS_GRADUACAO_IFRN = int(
    Configuracao.get_valor_por_chave('catalogo_provedor_servico', 'codigo_matricula_pos_graduacao') or 0
)
ID_GOVBR_6561_MATRICULA_FIC = int(Configuracao.get_valor_por_chave('catalogo_provedor_servico', 'codigo_matricula_fic') or 0)


class Command(BaseCommand):
    """
    Este command é voltado para o ambiente de desenvolvolvimento, para que se possa realizar "n" vezes a simulação de um
    atendimento digital por completo, ou seja, desde a sua solicitação até a sua execução.

    Exemplos de chamada:
    - - - - - - - - - -
    Simular a remoção da solicitação de id 1234:
     - python manage.py apagar_atendimentos_digitais -id 1234 -s
     - python manage.py apagar_atendimentos_digitais --id 1234 --simulate

    Remover a solicitação de id 1234:
     - python manage.py apagar_atendimentos_digitais -id 1234
     - python manage.py apagar_atendimentos_digitais --id 1234

    Apagar todas as solicitacões:
     - python manage.py apagar_atendimentos_digitais

    Simular a remoção de todas as solicitações:
    - python manage.py apagar_atendimentos_digitais --s
    - python manage.py apagar_atendimentos_digitais --simulate

    """

    def add_arguments(self, parser):
        parser.add_argument(
            '-id',
            '--id',
            type=str,
            help='Id da Solicitacao (Opcional)',
        )
        parser.add_argument('-s', '--simulate', action='store_true', help='Define se deve ser apenas uma simulacao.')

    @transaction.atomic()
    def handle(self, *args, **options):
        solicitacao_id = options['id']
        simulate = options['simulate']

        self.stdout.write('<<< Command apagar_atendimentos_digitais (catalogo_provedor_servico) >>>')
        self.stdout.write('Parâmetros informados: ')
        self.stdout.write(f' - id (Solicitacao): {solicitacao_id}')
        self.stdout.write(f' - simulate: {simulate}\n')

        if simulate:
            self.stdout.write('Iniciando simulacao...\n')

        if not solicitacao_id:
            if input('Deseja realmente apagar todas as solicitacoes? (S = Sim, N = Nao)').strip().upper() != 'S':
                self.stdout.write('Processamento abortado.')
                return

        if solicitacao_id:
            solicitacoes = Solicitacao.objects.filter(id=solicitacao_id)
        else:
            solicitacoes = Solicitacao.objects.all()

        if not solicitacoes:
            self.stdout.write('Nenhuma solicitacao encontrada.')
            self.stdout.write('FIM')
            return

        for solicitacao in solicitacoes:
            self.stdout.write('- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -')
            self.stdout.write(f'Solicitacao {solicitacao.id}')
            self.stdout.write(f' - Cpf: {solicitacao.cpf}')
            self.stdout.write(f' - Nome: {solicitacao.nome}')
            self.stdout.write(f' - Serviço: {solicitacao.servico.id_servico_portal_govbr} - {solicitacao.servico.titulo}\n')

            """
            Exemplo de um dados_registros_execucao_as_json:
            [
                {
                    "app": "processo_eletronico",
                    "model": "Processo",
                    "id": 149920,
                    "operation": "CREATE",
                    "registered_on": "2020-09-21 17:13:23.797969"
                },
                {
                    "app": "documento_eletronico",
                    "model": "DocumentoDigitalizado",
                    "id": 584300,
                    "operation": "CREATE",
                    "registered_on": "2020-09-21 17:13:23.960084"
                },
                {
                    "app": "processo_eletronico",
                    "model": "DocumentoDigitalizadoProcesso",
                    "id": 580785,
                    "operation": "CREATE",
                    "registered_on": "2020-09-21 17:13:23.976396"
                },
                {
                    "app": "processo_eletronico",
                    "model": "Tramite",
                    "id": 550910,
                    "operation": "CREATE",
                    "registered_on": "2020-09-21 17:13:24.128199"
                }
            ]
            """
            dados_registros_execucao_as_json = solicitacao.get_dados_registros_execucao_as_json()
            if dados_registros_execucao_as_json:
                self.stdout.write(' - Verificando registros criados ou atualizados durante a solicitação...')
                # A execução vai ser de trás pra frente porque os últimos registros criados devem ser os primeiros
                # a serem removidos.
                for dre in dados_registros_execucao_as_json[::-1]:
                    operation = dre['operation']
                    id = dre['id']
                    app_name = dre['app']
                    model_name = dre['model']
                    Model = apps.get_model(app_name, model_name)

                    if operation == 'CREATE':
                        self.stdout.write(f'   - Removendo o {model_name} ({app_name}) de id {id}.')
                        if not simulate:
                            Model.objects.filter(id=id).delete()

                    elif operation == 'UPDATE':
                        if solicitacao.servico.id_servico_portal_govbr in [
                            ID_GOVBR_6176_MATRICULA_EAD,
                            ID_GOVBR_6424_MATRICULA_CURSO_NIVEL_SUPERIOR_IFRN,
                            ID_GOVBR_10054_MATRICULA_POS_GRADUACAO_IFRN,
                            ID_GOVBR_6410_MATRICULA_CURSO_NIVEL_TECNICO_IFRN,
                            ID_GOVBR_6561_MATRICULA_FIC,
                        ]:
                            if app_name == 'processo_seletivo' and model_name == 'CandidatoVaga':
                                self.stdout.write(
                                    f'   - Atualizando o {model_name} ({app_name}) de id {id}, permitindo assim uma nova matricula para o mesmo cidadao.'
                                )
                                if not simulate:
                                    Model.objects.filter(id=id).update(situacao=None)

            self.stdout.write('\n - Por fim, apagando a solicitacao em si e tudo que depende dela. Ex: SoliciacaoEtapa, SolicitacaoEtapaArquivo... .')
            if not simulate:
                Solicitacao.objects.filter(id=solicitacao_id).delete()
                # Solicitacao.objects.filter(id=solicitacao_id).update(status=Solicitacao.STATUS_EM_ANALISE)

            self.stdout.write('- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -\n')

        if simulate:
            self.stdout.write('ATENÇÃO: Esta foi apenas uma simulacao, portando nenhum persitencia foi realizada.\n')

        self.stdout.write('<<< FIM >>>')
