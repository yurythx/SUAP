import datetime

from djtools.management.commands import BaseCommandPlus
from edu.models import Aluno, Convenio


class Command(BaseCommandPlus):
    def mostrar_dados_alunos(self, alunos):
        if alunos:
            print('    Matrícula;Nome;CursoCampus;AnoLetivo;Campus')
            for a in alunos:
                print(f'    {a.matricula};{a.pessoa_fisica.nome};{a.curso_campus.descricao};{a.ano_letivo};{a.curso_campus.diretoria.setor.uo}')

    def handle(self, *args, **options):
        title = 'Gestão / Edu - Comando para atribuir e remover convênio de alunos de determinados cursos'
        print()
        print('- ' * len(title))
        print(title)
        print('- ' * len(title))

        executar_command = input('Informe o que deseja fazer? (SIMULAR/EXECUTAR/ABORTAR) ').strip().upper()

        executar_simulacao = executar_command == 'SIMULAR'
        executar_pra_valer = executar_command == 'EXECUTAR'
        if not executar_simulacao and not executar_pra_valer:
            print()
            print('Processamento abortado.')
            return

        exibir_dados_alunos = input('Deseja ver os dados dos alunos afetados pela rotina? (SIM/NAO) ').strip().upper()
        exibir_dados_alunos = exibir_dados_alunos == 'SIM'

        print()
        print('Início do processamento: {}'.format(datetime.datetime.now().strftime('%d/%m/%Y - %H:%M:%S')))
        print()

        print('Listagem dos alunos dos cursos campus que terão convênio atribuído, caso não o tenham atualmente:')
        print(
            '- Curso Campus de descrição que contém "PRONATEC (Convênio "PRONATEC");\n'
            '- Curso Campus de descrição que contém "Mulheres Mil" para o ano letivo anterior a 2014 (Convênio "Mulheres Mil");\n'
            '- Curso Campus de descrição que contém "Mulheres Mil" para o ano letivo 2014 (Convênio "Mulheres Mil / PRONATEC");\n'
            '- Curso Campus de descrição que contém "Mulheres Mil" para o ano letivo 2015 do campos de Caicó (Convênio "Mulheres Mil / PRONATEC");\n'
            '- Curso Campus de descrição que contém "(UAB)" (Convênio UAB);\n'
            '- Curso Campus de descrição que contém "(ETEC)" (Convênio ETEC);\n'
        )
        convenio = Convenio.objects.get_or_create(descricao='PRONATEC')[0]
        q = Aluno.objects.filter(convenio__isnull=True, curso_campus__descricao__unaccent__icontains='PRONATEC')
        print(f'Alunos "PRONATEC" ajustados: {q.count():d}')
        if exibir_dados_alunos:
            self.mostrar_dados_alunos(q)
        if executar_pra_valer:
            q.update(convenio=convenio)

        convenio = Convenio.objects.get_or_create(descricao='Mulheres Mil')[0]
        q = Aluno.objects.filter(ano_letivo__ano__lt=2014, convenio__isnull=True, curso_campus__descricao__unaccent__icontains='mulheres mil')
        print(f'Alunos "Mulheres Mil" (ano letivo < 2014) ajustados: {q.count():d}')
        if exibir_dados_alunos:
            self.mostrar_dados_alunos(q)
        if executar_pra_valer:
            q.update(convenio=convenio)

        # Chamado 40358 - Após conversar com professor Alessandro, foi passada a informação de que de 2015 à 2017 os
        # alunos do curso "mulheres mil" não tiverem convênio, por isso a rotina foi ajustada para não atribuir convênio
        # a esses alunos.
        convenio = Convenio.objects.get_or_create(descricao='Mulheres Mil / PRONATEC')[0]
        q = Aluno.objects.filter(ano_letivo__ano=2014, convenio__isnull=True, curso_campus__descricao__unaccent__icontains='mulheres mil')
        print(f'Alunos "Mulheres Mil / PRONATEC" (ano letivo = 2014) ajustados: {q.count():d}')
        if exibir_dados_alunos:
            self.mostrar_dados_alunos(q)
        if executar_pra_valer:
            q.update(convenio=convenio)

        convenio = Convenio.objects.get_or_create(descricao='Mulheres Mil / PRONATEC')[0]
        q = Aluno.objects.filter(
            ano_letivo__ano=2015,
            convenio__isnull=True,
            curso_campus__descricao__unaccent__icontains='mulheres mil',
            curso_campus__diretoria__setor__uo__sigla='CA',
        )
        print(f'Alunos "Mulheres Mil / PRONATEC" (ano letivo = 2015, campus CA) ajustados: {q.count():d}')
        if exibir_dados_alunos:
            self.mostrar_dados_alunos(q)
        if executar_pra_valer:
            q.update(convenio=convenio)

        convenio = Convenio.objects.get_or_create(descricao='UAB')[0]
        q = Aluno.objects.filter(convenio__isnull=True, curso_campus__descricao__unaccent__icontains='(uab)')
        print(f'Alunos "UAB" ajustados: {q.count():d}')
        if exibir_dados_alunos:
            self.mostrar_dados_alunos(q)
        if executar_pra_valer:
            q.update(convenio=convenio)

        convenio = Convenio.objects.get_or_create(descricao='ETEC')[0]
        q = Aluno.objects.filter(convenio__isnull=True, curso_campus__descricao__unaccent__icontains='(etec)')
        print(f'Alunos "ETEC" ajustados: {q.count():d}')
        if exibir_dados_alunos:
            self.mostrar_dados_alunos(q)
        if executar_pra_valer:
            q.update(convenio=convenio)

        print()
        print()
        print(
            'Listagem dos alunos dos cursos campus que terão o convênio removido, caso o tenham atualmente:\n'
            '- Curso Campus de descrição que contém "Mulheres Mil" para os anos letivos 2015, exceto os do campus Caicó (Convênio "Mulheres Mil / PRONATEC");\n'
            '- Curso Campus de descrição que contém "Mulheres Mil" para o ano letivo 2016 e 2017 (Convênio "Mulheres Mil / PRONATEC");\n'
        )
        q = Aluno.objects.filter(
            ano_letivo__ano__in=[2015], convenio__isnull=False, curso_campus__descricao__unaccent__icontains='mulheres mil'
        ).exclude(curso_campus__diretoria__setor__uo__sigla='CA')
        print(f'Alunos "Mulheres Mil / PRONATEC" (ano letivo = 2015, todos os alunos exceto os do campus CA) ajustados: {q.count():d}')
        if exibir_dados_alunos:
            self.mostrar_dados_alunos(q)
        if executar_pra_valer:
            q.update(convenio=None)

        q = Aluno.objects.filter(
            ano_letivo__ano__in=[2016, 2017], convenio__isnull=False, curso_campus__descricao__unaccent__icontains='mulheres mil'
        )
        print(f'Alunos "Mulheres Mil / PRONATEC" (ano letivo = 2016, 2017) ajustados: {q.count():d}')
        if exibir_dados_alunos:
            self.mostrar_dados_alunos(q)
        if executar_pra_valer:
            q.update(convenio=None)

        print()
        print('Processamento concluído com sucesso.')
        if not executar_pra_valer:
            print(
                'OBS: Este processamento foi apenas uma SIMULAÇÃO. Nada foi gravado no banco de dados. Para executar '
                'algo em definitivo, realize novamente o processamento e escolha a opção "EXECUTAR".'
            )

        print()
        print('Fim do processamento: {}'.format(datetime.datetime.now().strftime('%d/%m/%Y - %H:%M:%S')))
