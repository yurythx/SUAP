import datetime
import os

from django.db import connection

from comum.management.commands.terminal_utils import Terminal
from djtools.management.commands import BaseCommandPlus


class Command(Terminal, BaseCommandPlus):
    def __init__(self):
        Terminal.__init__(self)
        caminho_arquivo_corrente_sem_extensao = os.path.splitext(__file__)[0]
        self.log_file = f'{caminho_arquivo_corrente_sem_extensao}.log'

    def handle(self, *args, **options):
        self.log_title(f'Edu - {__name__}')

        self.add_empty_line()
        self.log(
            'O objetivo deste command eh inserir os registros de HistoricoSituacaoMatriculaPeriodo do ano de 2019\n'
            'que estao faltando,o que acabou gerando um impacto na variavel academica "AM" do mdulo de Gestao.\n'
            'Para mais detalhes, ver o Chamado 112531 (Issue 3423).'
        )

        self.add_empty_line()

        if not self.ask_yes_or_no('Deseja continuar?'):
            self.add_empty_line()
            self.log('Processamento abortado.')
            return

        self.add_empty_line()
        self.log('Inicio do processamento: {}'.format(datetime.datetime.now().strftime('%d/%m/%Y - %H:%M:%S')))

        cursor = connection.cursor()

        self.add_separator()
        self.log(
            'Criando uma coluna temporaria para marcar os registros inseridos nesta solucao. Essa coluna podera,'
            'e devera, ser removida em versoes posteriores.'
        )
        cursor.execute('ALTER TABLE edu_historicosituacaomatriculaperiodo ADD COLUMN IF NOT EXISTS temp_data VARCHAR(50) NULL;')
        cursor.execute(
            """
                            INSERT  INTO edu_historicosituacaomatriculaperiodo
                                    (matricula_periodo_id, situacao_id, data, temp_data)
                            SELECT  mp.id AS matricula_periodo_id,
                                    smp.id AS situacao_id,
                                    l.dt AS data,
                                    'Chamado_112531_Issue_3423' AS temp_data
                            FROM    edu_aluno a
                            INNER   JOIN edu_situacaomatricula sm ON sm.id = a.situacao_id
                            INNER   JOIN edu_matriculaperiodo mp ON mp.aluno_id = a.id
                            INNER   JOIN comum_ano ano ON ano.id = mp.ano_letivo_id
                            INNER   JOIN edu_situacaomatriculaperiodo smp ON smp.id = mp.situacao_id
                            INNER   JOIN edu_log l ON l.tipo = 1 /*CADASTRO*/
                                                      AND l.modelo = 'MatriculaPeriodo'
                                                      AND l.ref = mp.id
                            LEFT    JOIN edu_historicosituacaomatriculaperiodo hsmp ON hsmp.matricula_periodo_id = mp.id
                            WHERE   ano.ano = 2019
                                    AND hsmp.id IS NULL
                      """
        )
        self.log(f'Registros inseridos na tabela "edu_historicosituacaomatriculaperiodo": {cursor.cursor.rowcount}')

        self.add_empty_line()
        connection._commit()

        self.add_empty_line()
        self.log('Processamento realizado COM SUCESSO!')

        self.add_empty_line()
        self.log('Fim do processamento: {}'.format(datetime.datetime.now().strftime('%d/%m/%Y - %H:%M:%S')))
        self.save_log(self.log_file)
        self.log(f'Log da processamento salvo com sucesso em {self.log_file}', color='green', opts=('bold',))
