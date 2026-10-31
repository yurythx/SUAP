from django.db import connection

from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        cur = connection.cursor()
        sql = """
            select a.id as aluno_id, mp.id as matricula_periodo_id, a.data_matricula as data_matricula
            from edu_aluno a
            inner join edu_matriculaperiodo mp on mp.aluno_id = a.id
            inner join comum_ano ano on ano.id = a.ano_letivo_id
            inner join edu_cursocampus c on a.curso_campus_id = c.id
            and (select count(*) from edu_historicosituacaomatricula h where h.aluno_id = a.id) = 0
            and (select count(*) from edu_historicosituacaomatriculaperiodo h where h.matricula_periodo_id = mp.id) = 0
            and c.modalidade_id = 1
            and a.situacao_id = 1
            and mp.situacao_id = 2
            order by a.data_matricula
        """
        cur.execute(sql)
        count = 0
        for row in cur.fetchall():
            count += 1
            aluno_id, matricula_id, data = row[0], row[1], row[2]
            if str(data).startswith('2014'):
                data = '2013-12-31 00:00:00'
            sql2 = f"insert into edu_historicosituacaomatricula (aluno_id, situacao_id, data) values ({aluno_id}, 1, '{data}')"
            sql3 = f"insert into edu_historicosituacaomatriculaperiodo (matricula_periodo_id, situacao_id, data) values ({matricula_id}, 2, '{data}')"
            cur.execute(sql2)
            cur.execute(sql3)
        cur.execute('update edu_cursocampus set modalidade_id = 9 where id in (638, 561);')
        cur.close()
        connection._commit()
        # connection._rollback()
        print(count)
