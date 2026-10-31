from django.core.management.base import BaseCommand

from comum.models import APIExterna
from rh.models import Pessoa, PessoaFisica, PessoaInfoComplementar


class Command(BaseCommand):
    """
    Use: python manage.py atualizar_info_complementar_pessoas_apis_gov --apis CadUnico --vinculo aluno --ano_criacao_user 2023
    python manage.py atualizar_info_complementar_pessoas_apis_gov --apis pessoacomdeficiencia  --cpf 111.111.111-00
    Para listar APIs disponíveis: python manage.py atualizar_info_complementar_pessoas_apis_gov --listar_apis
    """

    help = 'Atualiza informações complementares dos usuários.'

    def add_arguments(self, parser):
        parser.add_argument('--vinculo', type=str, help='Vínculo dos usuários a serem atualizados.')
        parser.add_argument('--cpf', type=str, help='CPF do usuário atualizados.')
        parser.add_argument('--ano_criacao_user', type=int, help='Ano de criação dos usuários a serem atualizados.')
        parser.add_argument('--apis', type=str, nargs='+', help='APIs a serem consultadas.')
        parser.add_argument('--listar_apis', action='store_true', help='Retorna a lista de APIs disponíveis')

    def lista_apis_disponiveis(self):
        # Obtenha a lista de APIs disponíveis
        apis_disponiveis = APIExterna.objects.filter(ativo=True).values('nome')

        # Imprime a lista de APIs disponíveis
        self.stdout.write('APIs disponíveis:')
        for api in apis_disponiveis:
            self.stdout.write(api['nome'])
        raise SystemExit

    def handle(self, *args, **options):
        # Exibe as apis disponiveis caso tenha recebido o paramento --listar_apis
        if options.get('listar_apis', False):
            self.lista_apis_disponiveis()

        # Filtra as pessoas de acordo com os parâmetros opcionais
        pessoas = Pessoa.objects.filter(vinculo__ativo=True)
        if options['vinculo']:
            if options['vinculo'].lower() == 'servidor':
                pessoas = pessoas.filter(vinculo__user__eh_servidor=True)
            elif options['vinculo'].lower() == 'aluno':
                pessoas = pessoas.filter(vinculo__user__eh_aluno=True)
            elif options['vinculo'].lower() == 'prestador':
                pessoas = pessoas.filter(vinculo__user__eh_prestador=True)

        if options['cpf']:
            pessoas = PessoaFisica.objects.filter(cpf=options['cpf'])

        if options['ano_criacao_user']:
            pessoas = pessoas.filter(vinculo__user__date_joined__year=int(options['ano_criacao_user']))
        # Atualiza as informações complementares de cada pessoa
        objetos_criados_ou_atualizados = 0
        for pessoa in pessoas:
            if options['apis']:
                for api_origem in options['apis']:
                    api_origem_instance = APIExterna.objects.filter(nome=api_origem.upper()).first()
                    if api_origem_instance.ativo:
                        pessoa_info_comp = PessoaInfoComplementar.get_instance(pessoa, api_origem_instance, force=True)
                        objetos_criados_ou_atualizados += 1 if pessoa_info_comp else 0
        self.stdout.write(f'{objetos_criados_ou_atualizados} instâncias de PessoaInfoComplementar foram criadas/atualizadas')
