from datetime import datetime, timedelta

from django.db.models import Count

from ae.models import AgendamentoRefeicao, DemandaAlunoAtendida
from djtools.management.commands import BaseCommandPlus
from rh.models import UnidadeOrganizacional


class Command(BaseCommandPlus):
    def add_arguments(self, parser):
        parser.add_argument('--sigla_uo', '-uo', dest='campus', action='store', default=[], help='Sigla do Campus')

        parser.add_argument(
            '--data_inicio', '-dt_inicio', dest='data_inicio', action='store', default=[], help='Data de início da verificação. Formato: AAAA-MM-DD'
        )

        parser.add_argument(
            '--data_fim', '-dt_fim', dest='data_fim', action='store', default=[], help='Data de término da verificação. Formato: AAAA-MM-DD'
        )

        parser.add_argument('--output_file', '-output', dest='output', action='store', default=[], help='Imprimir saída em arquivo')

    def handle(self, *args, **options):
        # usar ../manage.py checa_inconsistencia_alimentacao --sigla_uo=CNAT --data_inicio=2018-01-01 --data_fim=2018-06-30
        campus = options.get('campus', False)
        data_inicio = options.get('data_inicio')
        data_fim = options.get('data_fim')
        output = options.get('output')
        if campus:
            campi = UnidadeOrganizacional.objects.suap().filter(sigla=campus)
        else:
            campi = UnidadeOrganizacional.objects.suap().all()
        mensagem = ''

        for campus in campi:
            mensagem += '\n\n'
            mensagem += f'\n\t CAMPUS: {campus}'
            mensagem_lista = ''

            registros_qtd_zero = DemandaAlunoAtendida.objects.filter(
                campus=campus, data__gte=data_inicio, data__lte=data_fim, demanda__in=[1, 2, 19], quantidade=0
            )
            mensagem += f'\n\n{registros_qtd_zero.count()} \t Registros de Atendimentos com a quantidade igual a 0'
            if registros_qtd_zero.exists():
                for registro in registros_qtd_zero:
                    mensagem += '\n{} - {} - {} - {} '.format(
                        registro.aluno.pessoa_fisica.nome, registro.aluno.matricula, registro.demanda, registro.data.strftime('%d/%m/%Y')
                    )

            # print ">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>"

            registros_qtd_mais_1 = DemandaAlunoAtendida.objects.filter(
                campus=campus, data__gte=data_inicio, data__lte=data_fim, demanda__in=[1, 2, 19], quantidade__gt=1
            )
            mensagem += f'\n\n{registros_qtd_mais_1.count()} \t Registros de Atendimentos com a quantidade maior do que 1'
            if registros_qtd_mais_1.exists():
                for registro in registros_qtd_mais_1:
                    mensagem += '\n{} - {} - {} - {} - qtd: {} '.format(
                        registro.aluno.pessoa_fisica.nome,
                        registro.aluno.matricula,
                        registro.demanda,
                        registro.data.strftime('%d/%m/%Y'),
                        registro.quantidade,
                    )

            # print ">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>"

            # outros_campi_terminal = DemandaAlunoAtendida.objects.filter(campus=campus,  data__gte=data_inicio, data__lte=data_fim, demanda__in=[1,2, 19], terminal__isnull=False).exclude(aluno__curso_campus__diretoria__setor__uo=campus)
            # if outros_campi_terminal.exists():
            #     for registro in outros_campi_terminal:
            #         print u'{} - {} - {} - {} '.format(registro.aluno.pessoa_fisica.nome, registro.aluno.matricula, registro.demanda, registro.data.strftime("%d/%m/%Y"))
            #
            # print ">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>"

            outros_campi_manualmente = DemandaAlunoAtendida.objects.filter(
                campus=campus, data__gte=data_inicio, data__lte=data_fim, demanda__in=[1, 2, 19], terminal__isnull=True
            ).exclude(aluno__curso_campus__diretoria__setor__uo=campus)
            mensagem += f'\n\n{outros_campi_manualmente.count()} \t Registros de Atendimentos para alunos de outros campi cadastrados manualmente'
            if outros_campi_manualmente.exists():
                for registro in outros_campi_manualmente:
                    if not AgendamentoRefeicao.objects.filter(cancelado=False, aluno=registro.aluno, data=registro.data).exists():
                        mensagem += '\n{} - {} - {} - {} '.format(
                            registro.aluno.pessoa_fisica.nome, registro.aluno.matricula, registro.demanda, registro.data.strftime('%d/%m/%Y')
                        )
            # print ">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>"
            data_atual = datetime.strptime(data_inicio, '%Y-%m-%d')
            data_final = datetime.strptime(data_fim, '%Y-%m-%d')
            data_final = data_final + timedelta(days=1)
            duplicados = 0

            while data_atual < data_final:
                busca = DemandaAlunoAtendida.objects.filter(
                    campus=campus,
                    data__gte=datetime(data_atual.year, data_atual.month, data_atual.day, 0, 0, 0),
                    data__lte=datetime(data_atual.year, data_atual.month, data_atual.day, 23, 59, 59),
                )
                registros = (
                    busca.filter(demanda=1)
                    .values('aluno__pessoa_fisica__nome', 'aluno__matricula')
                    .annotate(contador=Count('aluno__pessoa_fisica__nome'))
                    .filter(contador__gt=1)
                )
                if registros:
                    for item in registros:
                        duplicados = duplicados + item['contador'] - 1
                        mensagem_lista += '\n{} - {} - Almoço - {} ({}) '.format(
                            item['aluno__pessoa_fisica__nome'], item['aluno__matricula'], data_atual.strftime('%d/%m/%Y'), item['contador']
                        )

                registros = (
                    busca.filter(demanda=2)
                    .values('aluno__pessoa_fisica__nome', 'aluno__matricula')
                    .annotate(contador=Count('aluno__pessoa_fisica__nome'))
                    .filter(contador__gt=1)
                )
                if registros:
                    for item in registros:
                        duplicados = duplicados + item['contador'] - 1
                        mensagem_lista += '\n{} - {} - Jantar - {} ({})'.format(
                            item['aluno__pessoa_fisica__nome'], item['aluno__matricula'], data_atual.strftime('%d/%m/%Y'), item['contador']
                        )
                registros = (
                    busca.filter(demanda=19)
                    .values('aluno__pessoa_fisica__nome', 'aluno__matricula')
                    .annotate(contador=Count('aluno__pessoa_fisica__nome'))
                    .filter(contador__gt=1)
                )
                if registros:
                    for item in registros:
                        duplicados = duplicados + item['contador'] - 1
                        mensagem_lista += '\n{} - {} - Café - {} ({})'.format(
                            item['aluno__pessoa_fisica__nome'], item['aluno__matricula'], data_atual.strftime('%d/%m/%Y'), item['contador']
                        )

                data_atual = data_atual + timedelta(days=1)
            mensagem += f'\n\n{duplicados} \t Registros de Atendimentos Duplicados (mesmo aluno e mesmo tipo de refeição)'
            mensagem += mensagem_lista

            # mensagem += u'\n{} \t Registros de Atendimentos para alunos de outros campi via terminal'.format(outros_campi_terminal.count())

        if output:
            f = open('relatorio.txt', 'w')
            f.write(mensagem)
            f.close()
        else:
            return mensagem
