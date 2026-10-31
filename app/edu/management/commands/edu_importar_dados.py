""" """

import datetime

from djtools.management.commands import BaseCommandPlus
from edu.models import HistoricoImportacao
from edu.q_academico import DAO


class Command(BaseCommandPlus):
    def add_arguments(self, parser):
        parser.add_argument('args', nargs='*', type=str)

    def handle(self, *args, **options):
        if args:
            prefixo_matricula = args[0]
        else:
            prefixo_matricula = None

        verbose = options.get('verbosity', '0') != '0'

        dao = DAO()
        dao.importar_cursos_campus(verbose)
        dao.importar_situacoes_matricula(verbose)
        dao.importar_situacoes_matricula_periodo(verbose)
        dao.importar_polos_ead(verbose)
        alunos_criados, alunos_atualizados = dao.importar_alunos(prefixo_matricula=prefixo_matricula, verbose=verbose)
        matriculas_periodo_criadas, matriculas_periodo_atualizadas = dao.importar_matriculas_periodo(
            prefixo_matricula=prefixo_matricula, verbose=verbose
        )
        dao.atualizar_historico()
        dao.atualizar_username()
        dao.atualizar_situacoes_alunos_integralizados_qacademico()

        historico = HistoricoImportacao()
        historico.data = datetime.datetime.now()
        historico.total_alunos_criados = alunos_criados
        historico.total_alunos_atualizados = alunos_atualizados
        historico.total_matriculas_periodo_criadas = matriculas_periodo_criadas
        historico.total_matriculas_periodo_atualizadas = matriculas_periodo_atualizadas
        historico.save()

        # Recria as matrículas período dos alunos importados matriculados
        # call_command('edu_corrigir_dados_alunos', *args, interactive=False, raise_exception=False)
