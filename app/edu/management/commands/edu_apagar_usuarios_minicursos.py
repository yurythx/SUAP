import datetime

import tqdm

from comum.models import User
from djtools.management.commands import BaseCommandPlus
from edu.models import Aluno, TurmaMinicurso


class Command(BaseCommandPlus):
    def add_arguments(self, parser):
        parser.add_argument('--completo', dest='completo', action='store_true', default=False, help='Todos os minicursos.')

    def handle(self, *args, **options):
        hoje = datetime.datetime.now()

        completo = options.get('completo', False)

        # Executa somente as terças ou forcando rodar completo
        if not (hoje.weekday() == '2' or completo):
            return

        qs = TurmaMinicurso.objects.filter(gerar_matricula=False)

        if not completo:
            qs = qs.filter(data_fim__year=hoje.year)

        for turma in tqdm.tqdm(qs):
            turma.save()

        User.objects.filter(username__regex=r'20[0-9]{3}[a-zA-Z]{2,4}[0-9]+').update(eh_aluno=True)
        for u in tqdm.tqdm(User.objects.filter(username__regex=r'20[0-9]{3}[a-zA-Z]{2,4}[0-9]+')):
            a = Aluno.objects.filter(matricula=u.username).first()
            if not a:
                print(f'Excluindo {u}')
                u.delete()
            elif not u.get_profile():
                a.save()
