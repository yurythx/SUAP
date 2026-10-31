import logging
import sys

from avaliacao_integrada.models import Avaliacao
from djtools.management.commands import BaseCommandPlus
from rh.managers import ServidorQueryset
from rh.models import Servidor

# manage gerar_respondentes_avaliacao --gerar --avaliacao_id 23
# manage gerar_respondentes_avaliacao --avaliacao_id 23 --identificacoes 12345 98765432100 exemplo@email.com
DEFAULT_LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{levelname} {asctime} {filename}:{lineno} - {funcName}() ] {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file': {
            'class': 'logging.FileHandler',
            'formatter': 'verbose',
            'filename': 'resultado_geracao_respondentes.log',  # Arquivo de log
            'mode': 'w',  # Sobrescrever o arquivo de log a cada execução
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'DEBUG',
    },
}

# Configurar o logger
logging.basicConfig(level=logging.DEBUG)
logging.config.dictConfig(DEFAULT_LOGGING)

# Exemplo de uso
logger = logging.getLogger(__name__)


class Command(BaseCommandPlus):
    def add_arguments(self, parser):
        # exemplo de uso: --identificacoes 12345 98765432100 exemplo@email.com
        parser.add_argument('--identificacoes', nargs='+', type=str, help='identificação do público alvo, pode ser matricula, cpf, cnpj ou e-mail.')

        parser.add_argument(
            '--avaliacao_id',
            type=int,
            help='ID da avaliação que será processada',
            required=True,  # Define o argumento como obrigatório
        )

        parser.add_argument('--gerar', action='store_true', help='Gera respondentes para a avaliação')

    def verifica_respondentes_em_duplicidade(self, avaliacao):
        pass
        # publico_alvo = avaliacao.obter_publicoalvo()
        # for tipo_respondente, lista_dados in publico_alvo.items():
        #     for dados in lista_dados:

    def verifica_respondente_apto_existe(self, avaliacao, identificacoes):
        publico_alvo = avaliacao.obter_publicoalvo()

        usuario_respondente = False
        for lista_dados in publico_alvo.values():
            for dados in lista_dados:
                for identificacao in identificacoes:
                    identificacao_existe = any(identificacao == dados.get(key) for key in ['cpf', 'matricula', 'cnpj', 'email'])
                    if identificacao_existe:
                        usuario_respondente = True
                        print(f'Identificação {identificacao} consta na lista de público-alvo.')

        if not usuario_respondente:
            print('Identificação NÃO constam na lista de público-alvo.')

    def listar_servidores_sem_areas_vinculacao(self, qs_servidores: ServidorQueryset = None):
        if qs_servidores is None:
            servidores = Servidor.objects.ativos()

        qs_servidores = servidores.filter(setor__areas_vinculacao__isnull=True)

        print('*** lista de setores sem áreas de vinculação')
        setores = set()
        for s in qs_servidores.values_list('setor__id', 'setor__sigla', 'setor__nome', 'setor__uo__nome'):
            setores.add(s)

        c = 0
        for setor_id, setor_sigla, setor_nome, setor__uo__nome in setores:
            c += 1
            print(f'{setor__uo__nome};{setor_sigla} - {setor_nome};{setor_id};')
        print(f'TOTAL: {c}')
        import sys

        sys.exit()
        print('\n\n*** lista de servidores sem áreas de vinculação por setor')

        i = 0
        j = 0
        for setor_id, setor_sigla, setor_nome in qs_servidores.values_list('setor__id', 'setor__sigla', 'setor__nome'):
            i += 1
            print(f'\n[{i}] - {setor_sigla} - {setor_nome}')

            for s in qs_servidores.filter(setor_id=setor_id):
                j += 1
                print(f'\t[{j}] - {s}')

    def gerar_respondentes(self, avaliacao):
        avaliacao.gerar_respondentes(excluir=False)

    def handle(self, **options):
        avaliacao_id = options['avaliacao_id']
        avaliacao = None
        try:
            avaliacao = Avaliacao.objects.get(id=avaliacao_id)
            self.stdout.write(self.style.SUCCESS(f'Avaliação com ID {avaliacao_id} encontrada.'))
        except Avaliacao.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Avaliação com ID {avaliacao_id} não encontrada.'))
            sys.exit(1)

        # avaliacao.enviar_emails(True)
        # respondente = avaliacao.obter_respondentes('20241091160006')

        if options['gerar']:
            self.gerar_respondentes(avaliacao)

        identificacoes = options['identificacoes']
        if identificacoes:
            self.verifica_respondente_apto_existe(avaliacao, identificacoes)

        # self.listar_servidores_sem_areas_vinculacao()

        # Total de respondentes
        # Respondente.objects.filter(avaliacao=avaliacao, resposta__isnull=False).distinct().count()

        # Obter respondente pela matrícula do servidor
        # usuario_id = Servidor.objects.filter(matricula='2813328').values_list('user__id', flat=True)[0]
        # qs = Respondente.objects.filter(avaliacao=avaliacao, user_id=usuario_id)

        # Respondente.objects.filter(avaliacao=2, user__isnull=True).values('segmento__nome')

        # Obter as resposta do respondente
        # respondente = qs.first()
        # Resposta.objects.filter(respondente__id=respondente.id)

        # Obter todas as respostas de uma avaliação
        # qs = Resposta.objects.filter(respondente__avaliacao=avaliacao)

        # Listar a quantidade de respondentes por avaliação e usuário
        # qs = Respondente.objects.values('avaliacao', 'user', 'uo').annotate(quant=Count('id'))
        # qs = qs.filter(quant__gt=1).values('avaliacao', 'user', 'uo', 'segmento', 'quant').order_by('avaliacao')
        # print(qs.query)
        # print('Respondente:', qs.count())
        #
        # # Obter respondentes aptos com user nulos
        # qs = Respondente.objects.filter(user__isnull=True).values('avaliacao').annotate(quant=Count('id'))
        # qs = qs.filter(quant__gt=1).values('avaliacao', 'quant').order_by('avaliacao')
        # qs.count()

        # Listar a quantidade de resposta por indicador e respondente
        # qs = Resposta.objects
        # qs = qs.values('indicador', 'respondente', 'content_type', 'object_id').annotate(quant=Count('id'))
        # qs = qs.filter(quant__gt=1).values('indicador', 'respondente', 'content_type', 'object_id', 'quant').order_by('indicador')
        # print(qs.query)
        # for d in qs:
        #     print(d)
        # print('Resposta:', qs.count())

        # Obter os servidores de setores sem áreas de vinculação associadas.
        # qsvs = avaliacao.obter_servidores_sem_areas_vinculacao()
        # setores = set()
        # for d in qsvs:
        #     setores.add((d['setor__id'], d['setor__sigla'], d['setor__nome']))
        # print(setores)
        # print(len(setores))
