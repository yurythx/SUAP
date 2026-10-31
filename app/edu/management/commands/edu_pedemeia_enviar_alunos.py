from django.apps import apps

from djtools.management.commands import BaseCommandPlus
from edu.models import Modalidade, SituacaoMatricula
from edu.models.pedemeia import RequisicaoPeDeMeia


class Command(BaseCommandPlus):
    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument('--reprocessamento', action='store_true', help='Enviar os dados dos registros que estão com erro')

    def handle(self, *args, **options):
        APIExterna = apps.get_model('comum', 'APIExterna')
        Aluno = apps.get_model('edu', 'Aluno')

        api_externa_pedemeia = APIExterna.PEDEMEIA

        if api_externa_pedemeia.ativo:
            api_service = api_externa_pedemeia.get_service()
            alunos = Aluno.objects.filter(
                matriz__isnull=False, situacao=SituacaoMatricula.MATRICULADO, curso_campus__modalidade=Modalidade.INTEGRADO
            ).select_related('curso_campus__diretoria__setor__uo')
            if options.get('reprocessamento'):
                alunos = alunos.exclude(requisicaopedemeia__tipo=RequisicaoPeDeMeia.CADASTRO, requisicaopedemeia__processada=True)
            else:
                alunos = alunos.filter(requisicaopedemeia__isnull=True)
            qtd_cadastrado = 0
            qtd_falhas = 0
            for i, aluno in enumerate(alunos):
                self.stdout.write(str(i + 1))
                cadastrado, _status_code = api_service.cadastrar_estudante(aluno)
                if cadastrado:
                    qtd_cadastrado += 1
                else:
                    qtd_falhas += 1
            self.stdout.write(f'Qtd cadastrados: {qtd_cadastrado}')
            self.stdout.write(f'Qtd falhas: {qtd_falhas}')
        else:
            self.stderr.write('API PeDeMeia está inativa.')
