import tqdm

from comum.models import PrestadorServico, User
from djtools.management.commands import BaseCommandPlus
from edu.models import Aluno
from rh.models import PessoaFisica, Servidor


class Command(BaseCommandPlus):
    help = 'Revincula usuários a pessoas físicas baseado na matricula e username'

    def handle(self, *args, **options):
        cont_alunos = 0
        cont_servidores = 0
        cont_prestadores = 0
        cont_pessoas = 0
        cont_nao_encontrados = 0
        cont_discrepancias = 0
        # Usuários sem pessoa fisica
        self.stdout.write('>>>> Usuários sem pessoa física associada:')

        qs = User.objects.filter(vinculo__pessoa__isnull=True)
        qs = tqdm.tqdm(qs)
        for user in qs:
            username = user.username

            # Tentando recuperar a pessoa física pela matricula do aluno
            aluno = Aluno.objects.filter(matricula=username).first()
            if aluno:
                if aluno.matricula != aluno.get_vinculo().user.username:
                    self.stdout.write(f'Discrepância encontrada {aluno.matricula} -> {aluno.get_vinculo().user.username}')
                    cont_discrepancias += 1
                    continue
                aluno.save()
                cont_alunos += 1
                continue

            # Tentando recuperar a pessoa física pela matricula do servidor
            servidor = Servidor.objects.filter(matricula=username).first()
            if servidor:
                if servidor.matricula != servidor.get_vinculo().user.username:
                    self.stdout.write(f'Discrepância encontrada {servidor.matricula} -> {servidor.get_vinculo().user.username}')
                    cont_discrepancias += 1
                    continue
                servidor.save()
                self.stdout.write(f'Servidor encontrado pelo username: {username}')
                cont_servidores += 1
                continue

            # Tentando recuperar a pessoa física pela matricula do aluno
            prestador = PrestadorServico.objects.filter(matricula=username).first()
            if prestador:
                if prestador.matricula != prestador.get_vinculo().user.username:
                    self.stdout.write(f'Discrepância encontrada {prestador.matricula} -> {prestador.get_vinculo().user.username}')
                    cont_discrepancias += 1
                    continue
                prestador.save()
                self.stdout.write(f'Prestador encontrado pelo username: {username}')
                cont_prestadores += 1
                continue

            # Tenta recuperar a pessoa física pelo username gravado na pessoa física
            pf = PessoaFisica.objects.filter(vinculo__user__username=username).first()
            if pf:
                pf.save()
                cont_pessoas += 1
                continue

            self.stdout.write(f'Usuário não encontrado pelo username: {username}')
            cont_nao_encontrados += 1

        self.stdout.write(f'Alunos sem usuário encontrados: {cont_alunos}')
        self.stdout.write(f'Servidores sem usuário encontrados: {cont_servidores}')
        self.stdout.write(f'Prestadores sem usuário encontrados: {cont_prestadores}')
        self.stdout.write(f'Pessoas Físicas sem usuário encontrados: {cont_pessoas}')
        self.stdout.write(f'Usuários discrepantes: {cont_discrepancias}')
        self.stdout.write(f'Usuários não encontrados: {cont_nao_encontrados}')

        cont_alunos = 0
        cont_alunos_sem_vinculos = 0
        cont_servidores = 0
        cont_servidores_sem_vinculos = 0
        cont_prestadores = 0
        cont_prestadores_sem_vinculos = 0
        cont_nao_encontrados = 0

        # Usuários sem vinculo
        self.stdout.write('')
        self.stdout.write('>>>> Usuários sem vínculo associado:')
        qs = User.objects.filter(vinculo__isnull=True)
        qs = tqdm.tqdm(qs)

        for user in qs:
            username = user.username

            # Tentando recuperar a pessoa física pela matricula do aluno
            aluno = Aluno.objects.filter(matricula=username).first()
            if aluno:
                aluno.save()
                vinculo = aluno.get_vinculo()
                if vinculo:
                    cont_alunos += 1
                else:
                    self.stdout.write(f'Aluno sem vínculo: {username}')
                    cont_alunos_sem_vinculos += 1
                continue

            # Tentando recuperar a pessoa física pela matricula do servidor
            servidor = Servidor.objects.filter(matricula=username).first()
            if servidor:
                servidor.save()
                vinculo = servidor.get_vinculo()
                if vinculo:
                    self.stdout.write(f'Servidor encontrado pelo username: {username}')
                    continue
                else:
                    self.stdout.write(f'Servidor sem vínculo: {username}')
                    cont_servidores_sem_vinculos += 1

            # Tentando recuperar a pessoa física pela matricula do aluno
            prestador = PrestadorServico.objects.filter(matricula=username).first()
            if prestador:
                prestador.save()
                vinculo = prestador.get_vinculo()
                if vinculo:
                    self.stdout.write(f'Prestador encontrado pelo username: {username}')
                    continue
                else:
                    self.stdout.write(f'Prestador sem vínculo: {username}')
                    cont_prestadores_sem_vinculos += 1

            cont_nao_encontrados += 1

        self.stdout.write(f'Alunos sem vinculo encontrados: {cont_alunos}')
        self.stdout.write(f'Alunos sem vinculo não encontrados: {cont_alunos_sem_vinculos}')
        self.stdout.write(f'Servidores sem vinculo encontrados: {cont_servidores}')
        self.stdout.write(f'Servidores sem vinculo não encontrados: {cont_servidores_sem_vinculos}')
        self.stdout.write(f'Prestadores sem vinculo encontrados: {cont_prestadores}')
        self.stdout.write(f'Prestadores sem vinculo não encontrados: {cont_prestadores_sem_vinculos}')
        self.stdout.write(f'Usuários sem vinculos não encontrados: {cont_nao_encontrados}')

        # Salvando alunos que não possuem nenhum vínculo associado
        self.stdout.write('Vinculando alunos:')
        qs = Aluno.objects.filter(vinculos__isnull=True)
        for aluno in tqdm.tqdm(qs):
            aluno.save()

        # Salvando prestadores que não possuem nenhum vínculo associado
        self.stdout.write('Vinculando prestadores:')
        qs = PrestadorServico.objects.filter(vinculos__isnull=True)
        for prestador in tqdm.tqdm(qs):
            prestador.save()

        # Salvando servidores que não possuem nenhum vínculo associado
        self.stdout.write('Vinculando servidores:')
        qs = Servidor.objects.filter(vinculos__isnull=True)
        for servidor in tqdm.tqdm(qs):
            servidor.save()
