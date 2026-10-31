from datetime import datetime

import tqdm
from django.apps import apps
from django.conf import settings

from djtools.management.commands import BaseCommandPlus
from rh.importador_ws import ImportadorWs
from rh.models import Servidor

Log = apps.get_model('comum', 'log')


class Command(BaseCommandPlus):
    help = 'Atualização Servidor'

    def add_arguments(self, parser):
        parser.add_argument(
            '--completo',
            action='store_true',
            help='Roda importação/atualizacao completa do servidor levando como consideração data de inicio de exercício.',
        )
        parser.add_argument(
            '--sem-ws',
            action='store_true',
            help='Roda atualização completa do servidor sem utilizar o webservice, utilizando apenas os dados já importados.',
        )

    def handle(self, *args, **options):
        verbosity = options['verbosity']
        tem_ws = options['sem_ws'] is False
        if verbosity > 0:
            self.stdout.write('Iniciando importação WEBSERVICE {}'.format(datetime.now().strftime('%d/%m/%Y %H:%m:%S')))
        if tem_ws:
            importador = ImportadorWs()
            erros_importacao = []
            erros_atualizacao_afastamento = []
            qs = Servidor.objects.ativos().order_by('data_ultima_atualizacao_webservice')
            if verbosity > 0:
                qs = tqdm.tqdm(qs)
            for servidor in qs:
                try:
                    serv, _criado = importador.importacao_servidor(servidor.pessoa_fisica.cpf, False, False)[0]
                except Exception:
                    serv = None
                    erros_importacao.append(str(servidor))
                try:
                    importador.atualizar_ferias_afastamentos(
                        servidor.pessoa_fisica.cpf,
                        ano_inicio=servidor.data_inicio_servico_publico.year if servidor.data_inicio_servico_publico else 1900,
                    )
                except Exception:
                    erros_atualizacao_afastamento.append(str(servidor))
                if serv:
                    Servidor.objects.filter(id=serv.id).update(
                        data_posse_na_instituicao=serv.calcula_posse_na_instituicao,
                        data_posse_no_cargo=serv.calcula_posse_no_cargo,
                        data_fim_servico_na_instituicao=serv.calcula_fim_servico_na_instituicao,
                    )
            if erros_importacao:
                Log.objects.create(app='rh', titulo='Webservice Erro', texto='Erro ao importar servidores: {}'.format(','.join(erros_importacao)))
            if erros_atualizacao_afastamento:
                Log.objects.create(
                    app='rh',
                    titulo='Webservice Erro - Afastamento/Férias',
                    texto='Erro ao Afastamentos/Férias dos servidores: {}'.format(','.join(erros_atualizacao_afastamento)),
                )

        else:
            for servidor in Servidor.objects.all():
                if settings.DEBUG:
                    self.stdout.write(f'Servidor {servidor}')

                Servidor.objects.filter(id=servidor.id).update(
                    data_inicio_servico_publico=servidor.calcula_inicio_no_servico_publico,
                    data_inicio_exercicio_na_instituicao=servidor.calcula_inicio_exercicio_na_instituicao,
                    data_posse_na_instituicao=servidor.calcula_posse_na_instituicao,
                    data_posse_no_cargo=servidor.calcula_posse_no_cargo,
                    data_inicio_exercicio_no_cargo=servidor.calcula_inicio_exercicio_no_cargo,
                    data_fim_servico_na_instituicao=servidor.calcula_fim_servico_na_instituicao,
                )
        if verbosity > 0:
            self.stdout.write('Finalizada importação WEBSERVICE {}'.format(datetime.now().strftime('%d/%m/%Y %H:%m:%S')))
