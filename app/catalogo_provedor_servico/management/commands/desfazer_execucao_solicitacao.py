from django.apps import apps
from django.contrib.admin.utils import NestedObjects
from django.core.management.base import BaseCommand
from django.db import transaction
import sys

from catalogo_provedor_servico.models import Solicitacao
from catalogo_provedor_servico.providers.impl.ifrn.codes import (
    ID_GOVBR_6176_MATRICULA_EAD,
    ID_GOVBR_6410_MATRICULA_CURSO_NIVEL_TECNICO_IFRN,
    ID_GOVBR_6424_MATRICULA_CURSO_NIVEL_SUPERIOR_IFRN,
    ID_GOVBR_10054_MATRICULA_POS_GRADUACAO_IFRN,
)


class Command(BaseCommand):
    """
    Este command é voltado para desfazer a execução de uma solicitação, ou seja, voltar o seu status para EM_ANALISE.
    Para exemplificar, se uma solicitação de matrícula foi executada, ao desfazer a execução do atendimento, a matrícula
    do aluno é excluída e a solicitação volta para o status "Em Análise". Desta forma, o avaliador poderá executar novamente
    a solicitação.

    Exemplos de chamada:
    - - - - - - - - - -
    Simular o desfazer de execução da solicitação de id 1234:
     - python manage.py desfazer_execucao_solicitacao -id 1234 -s
     - python manage.py desfazer_execucao_solicitacao --id 1234 --simulate

     Executar de fato o desfazer de execução da solicitação de id 1234:
     - python manage.py desfazer_execucao_solicitacao -id 1234
     - python manage.py desfazer_execucao_solicitacao --id 1234
    """

    def add_arguments(self, parser):
        parser.add_argument(
            '-id',
            '--id',
            type=str,
            help='Id da Solicitacao',
        )
        parser.add_argument('-s', '--simulate', action='store_true', help='Define se deve ser apenas uma simulacao.')

    @transaction.atomic()
    def handle(self, *args, **options):
        solicitacao_id = options['id']
        simulate = options['simulate']

        self.stdout.write('<<< Command desfazer_execucao_solicitacao (catalogo_provedor_servico) >>>')
        self.stdout.write('Parâmetros informados: ')
        self.stdout.write(
            f' - id (Solicitacao): {solicitacao_id}',
        )
        self.stdout.write(f' - simulate: {simulate}\n')

        if not solicitacao_id:
            self.stdout.write('Id da solicitacao nao informado. Processamento abortado.')
            self.stdout.write('FIM')
            return

        solicitacoes = Solicitacao.objects.filter(id=solicitacao_id)

        if not solicitacoes:
            self.stdout.write('Nenhuma solicitacao encontrada.')
            self.stdout.write('FIM')
            return

        if solicitacoes.count() > 1:
            self.stdout.write('Mais de um registro encontrado. Processamento abortado.')
            self.stdout.write('FIM')
            return

        for solicitacao in solicitacoes:
            self.stdout.write('- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -')
            self.stdout.write(f'Solicitacao {solicitacao.id}')
            self.stdout.write(f' - Cpf: {solicitacao.cpf}')
            self.stdout.write(f' - Nome: {solicitacao.nome}')
            self.stdout.write(f' - Serviço: {solicitacao.servico.id_servico_portal_govbr} - {solicitacao.servico.titulo}\n')

            if simulate:
                self.stdout.write('Iniciando simulacao...\n')
            elif input('Deseja realmente continuar? (S = Sim, N = Nao) ').strip().upper() != 'S':
                self.stdout.write('Processamento abortado.')
                self.stdout.write('FIM')
                return

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
                        qs_delete = Model.objects.filter(id=id)
                        collector = NestedObjects('default')
                        collector.collect(qs_delete)
                        display_collected_objects(collector, indent='     ', writer=self.stdout.write)
                        if not simulate:
                            self.stdout.write(str(qs_delete.delete()))

                    elif operation == 'UPDATE':
                        if solicitacao.servico.id_servico_portal_govbr in [
                            ID_GOVBR_6176_MATRICULA_EAD,
                            ID_GOVBR_6424_MATRICULA_CURSO_NIVEL_SUPERIOR_IFRN,
                            ID_GOVBR_10054_MATRICULA_POS_GRADUACAO_IFRN,
                            ID_GOVBR_6410_MATRICULA_CURSO_NIVEL_TECNICO_IFRN,
                        ]:
                            if app_name == 'processo_seletivo' and model_name == 'CandidatoVaga':
                                self.stdout.write(
                                    f'   - Atualizando o {model_name} ({app_name}) de id {id}, permitindo assim uma nova matricula para o mesmo cidadao.'
                                )
                                if not simulate:
                                    self.stdout.write(str(Model.objects.filter(id=id).update(situacao=None)))

            self.stdout.write('\n - Por fim, voltando a solicitacao para o status EM_ANALISE.')
            if not simulate:
                self.stdout.write(
                    str(
                        Solicitacao.objects.filter(id=solicitacao_id).update(
                            status=Solicitacao.STATUS_EM_ANALISE, status_detalhamento='Em análise', dados_registros_execucao=''
                        )
                    )
                )

            self.stdout.write('- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -\n')

        if simulate:
            self.stdout.write('ATENÇÃO: Esta foi apenas uma simulacao, portanto nenhum persitencia foi realizada.\n')

        self.stdout.write('<<< FIM >>>')


def display_collected_objects(collector, indent='', writer=None):
    def _default_writer(message: str):
        sys.stdout.write(str(message) + '\n')

    write_fn = writer or _default_writer

    def recurse_collected_objects(objs, level=0, indent=''):
        indent += ' ' * (level * 4)  # Incrementa o nível de indentação para sub-objetos

        if not isinstance(objs, list | tuple):
            # Se o objeto não for uma lista ou tupla, ele é um objeto do Django
            # Obtém o nome do modelo e da aplicação
            app_label = objs._meta.app_label
            model_name = objs._meta.model_name
            write_fn(f'{indent}- {app_label}.{model_name} (ID: {objs.pk})')
            # write_fn(f"{indent}- {objs}\n")
        else:
            # Se for uma lista ou tupla, itera sobre os itens
            for obj in objs:
                recurse_collected_objects(obj, level + 1, indent)

    # Inicia a recursão com os objetos coletados
    for obj in collector.nested():
        recurse_collected_objects(obj, 0, indent)


# Exemplo de uso:
# Assumindo que 'collector' é um objeto NestedObjects que já coletou alguns objetos
# display_collected_objects(collector)

# Isso imprimirá os objetos coletados, incluindo os objetos principais e os relacionados,
# com indentação para refletir a estrutura aninhada. Além disso, incluirá o nome da aplicação e do modelo para cada objeto.
