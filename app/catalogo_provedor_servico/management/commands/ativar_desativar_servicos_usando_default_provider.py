from django.core.management.base import BaseCommand

from catalogo_provedor_servico.models import Servico


class Command(BaseCommand):
    def handle(self, *args, **options):
        servicos = Servico.objects.all().exclude(id_servico_portal_govbr=6176)
        for servico in servicos:
            print(f'{servico.id_servico_portal_govbr} - {servico.titulo}')
            print(f'https://catalogodigital.ifrn.edu.br/proxy/servicos/instituicao/1/servico/{servico.id_servico_portal_govbr}/solicitar/')
            print()

        param_to_execute = input('Informe o que deseja fazer? (1-ATIVAR / 2-DESATIVAR / 3-ABORTAR) ').strip()
        if param_to_execute == '1':
            servicos.update(ativo=True)
            print('Servicos ativados com sucesso.')
        elif param_to_execute == '2':
            servicos.update(ativo=False)
            print('Servicos deativados com sucesso.')
        else:
            print('Processamento abortado.')

        print('FIM')
