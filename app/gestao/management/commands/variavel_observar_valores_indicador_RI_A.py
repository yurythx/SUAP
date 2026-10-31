import datetime

from djtools.management.commands import BaseCommandPlus
from gestao.models import PeriodoReferencia, Variavel


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        print()
        print('- - - - -')
        print('Variáveis')
        print('- - - - -')
        print(
            'Ano de Referência: {} ({} à {})'.format(
                PeriodoReferencia.get_ano_referencia(),
                PeriodoReferencia.get_data_base().strftime('%d/%m/%Y'),
                PeriodoReferencia.get_data_limite().strftime('%d/%m/%Y'),
            )
        )
        print('Data da consulta: {}'.format(datetime.datetime.now().strftime('%d/%m/%Y - %H:%M')))
        print()

        print('Variável AI_OR')
        v = Variavel.objects.get(sigla='AI_OR')
        print(f'{v.sigla} ({v.nome}) = {v.get_valor_formatado()}')
        alunos = v.get_querysets()[0].order_by('curso_campus__diretoria__setor__uo')
        for a in alunos:
            print(f'{a.matricula};{a.pessoa_fisica.nome};{a.curso_campus.descricao};{a.ano_letivo};{a.curso_campus.diretoria.setor.uo}')
        print()
        print()

        print('Variável AM_OR')
        v = Variavel.objects.get(sigla='AM_OR')
        print(f'{v.sigla} ({v.nome}) = {v.get_valor_formatado()}')
        matriculas_periodo = v.get_querysets()[0].order_by('aluno__curso_campus__diretoria__setor__uo')
        for mp in matriculas_periodo:
            print(
                f'{mp.aluno.matricula};{mp.aluno.pessoa_fisica.nome};{mp.aluno.curso_campus.descricao};{mp.aluno.ano_letivo};{mp.aluno.curso_campus.diretoria.setor.uo}'
            )
        print()
        print()
