"""
Comando que extrai os curriculos lattes
"""

from django.conf import settings

from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        sql1 = """

            delete from edu_historicosituacaomatriculaperiodo;
            delete from edu_historicosituacaomatricula;
            delete from edu_matriculaperiodo;
            delete from edu_aluno;
            delete from edu_situacaomatriculaperiodo;
            delete from edu_situacaomatricula;
            delete from edu_cursocampus;
            delete from edu_diretoria;
            delete from edu_modalidade;


            insert into edu_diretoria
            select i.id, uo.setor_id, i.codigo_academico from academico_instituicao i inner join unidadeorganizacional uo on i.uo_id = uo.id order by i.id;

            insert into edu_modalidade
            select * from academico_gruponivelensino order by id;


            insert into edu_cursocampus (id, descricao, descricao_historico, periodicidade, diretoria_id, codigo_academico, ativo, codigo, modalidade_id, exige_enade, exige_colacao_grau, emite_diploma)
            select cc.id as id, cc.nome as descricao, cc.nome as descricao, 3 as periodicidade, (select id from edu_diretoria where codigo_academico = i.codigo_academico) as diretoria_id, cc.codigo_academico as codigo_academico, False as ativo, cc.id as codigo, cc.grupo_nivel_ensino_id as modalidade_id, False as exige_enade, False as exige_colacao_grau, False as emite_diploma
            from academico_curso cc inner join academico_instituicao i on cc.instituicao_id = i.id;


            insert into edu_situacaomatricula (id, codigo_academico, descricao, ativo) (select *from academico_situacaomatricula);

            insert into edu_situacaomatriculaperiodo (id, codigo_academico, descricao) (select *from academico_situacaomatriculaperiodo);

            insert into comum_ano (ano) (select distinct(ano_letivo_inicial) from academico_aluno where ano_letivo_inicial not in (select ano from comum_ano));
            insert into comum_ano (ano) (select distinct(ano_letivo) from academico_matriculaperiodo where ano_letivo not in (select ano from comum_ano));

            insert into edu_aluno (id, pessoa_fisica_id, matricula, codigo_academico, ano_letivo_id, periodo_letivo, situacao_id, curso_campus_id, data_matricula, ira, dt_conclusao_curso, ano_let_prev_conclusao, renda_per_capita, codigo_academico_pf, pai_falecido, mae_falecida)
            select a.id, a.pessoa_fisica_id, a.matricula, a.codigo_academico, (select id from comum_ano where ano = a.ano_letivo_inicial) as ano_letivo_id, periodo_letivo_inicial as periodo_letivo, situacao_id, (select id from edu_cursocampus cc where cc.codigo_academico = c.codigo_academico ) as curso_campus_id, data_matricula, indice_rendimento, dt_conclusao_curso, ano_let_prev_conclusao, renda_per_capita, codigo_academico_pf as codigo_academico_pf, 'f', 'f' from academico_aluno a inner join academico_curso c on a.curso_id = c.id ORDER BY a.id;

            insert into edu_matriculaperiodo
            select id, aluno_id, (select id from comum_ano where ano = ano_letivo) as ano_letivo_id, periodo_letivo, periodo as periodo_matriz, null as turma_id, situacao_id from academico_matriculaperiodo ORDER BY id;

            insert into edu_historicosituacaomatricula (select *from academico_historicosituacaomatricula order by id);

            insert into edu_historicosituacaomatriculaperiodo (select *from academico_historicosituacaomatriculaperiodo order by id);

            SELECT setval('edu_diretoria_id_seq', (SELECT MAX(id) FROM edu_diretoria));
            SELECT setval('edu_modalidade_id_seq', (SELECT MAX(id) FROM edu_modalidade));
            SELECT setval('edu_cursocampus_id_seq', (SELECT MAX(id) FROM edu_cursocampus));
            SELECT setval('edu_diretoria_id_seq', (SELECT MAX(id) FROM edu_diretoria));
            SELECT setval('edu_situacaomatricula_id_seq', (SELECT MAX(id) FROM edu_situacaomatricula));
            SELECT setval('edu_situacaomatriculaperiodo_id_seq', (SELECT MAX(id) FROM edu_situacaomatriculaperiodo));
            SELECT setval('edu_aluno_id_seq', (SELECT MAX(id) FROM edu_aluno));
            SELECT setval('edu_matriculaperiodo_id_seq', (SELECT MAX(id) FROM edu_matriculaperiodo));
            SELECT setval('edu_historicosituacaomatricula_id_seq', (SELECT MAX(id) FROM edu_historicosituacaomatricula));
            SELECT setval('edu_historicosituacaomatriculaperiodo_id_seq', (SELECT MAX(id) FROM edu_historicosituacaomatriculaperiodo));

        """
        sql2 = """
            ALTER TABLE "academico_historicosituacaomatricula" DROP CONSTRAINT "academico_historicosituacaomatricula_aluno_id_fkey";
            ALTER TABLE "academico_matriculaperiodo" DROP CONSTRAINT "academico_matriculaperiodo_aluno_id_fkey";
        """
        if 'ae' in settings.INSTALLED_APPS:
            sql2 += """
            ALTER TABLE "ae_agendamentorefeicao" DROP CONSTRAINT "ae_agendamentorefeicao_aluno_id_fkey";
            ALTER TABLE "ae_caracterizacao" DROP CONSTRAINT "ae_caracterizacao_aluno_id_fkey";
            ALTER TABLE "ae_dadosfincanceiros" DROP CONSTRAINT "ae_dadosfincanceiros_aluno_id_fkey";
            ALTER TABLE "ae_demandaalunoatendida" DROP CONSTRAINT "ae_demandaalunoatendida_aluno_id_fkey";
            ALTER TABLE "ae_historicorendafamiliar" DROP CONSTRAINT "ae_historicorendafamiliar_aluno_id_fkey";
            ALTER TABLE "ae_inscricao" DROP CONSTRAINT "ae_inscricao_aluno_id_fkey";
            ALTER TABLE "ae_inscricaocaracterizacao" DROP CONSTRAINT "ae_inscricaocaracterizacao_aluno_id_fkey";
            ALTER TABLE "ae_participacao" DROP CONSTRAINT "ae_participacao_aluno_id_fkey";
            ALTER TABLE "ae_participacaobolsa" DROP CONSTRAINT "ae_participacaobolsa_aluno_id_fkey";
        """
        if 'microsoft' in settings.INSTALLED_APPS:
            sql2 += """
            ALTER TABLE "microsoft_registrocriacaoconta" DROP CONSTRAINT "microsoft_registrocriacaoconta_aluno_id_fkey";
            ALTER TABLE "microsoft_configuracaoacessodreamspark_areas" DROP CONSTRAINT "microsoft_configuracaoacessodreamspark_areas_areacurso_id_fkey";
        """
        if 'ae' in settings.INSTALLED_APPS:
            sql2 += """
            ALTER TABLE "ae_agendamentorefeicao" ADD CONSTRAINT "ae_agendamentorefeicao_aluno_id_fkey" FOREIGN KEY (aluno_id) REFERENCES edu_aluno(id) DEFERRABLE INITIALLY DEFERRED;
            ALTER TABLE "ae_caracterizacao" ADD CONSTRAINT "ae_caracterizacao_aluno_id_fkey" FOREIGN KEY (aluno_id) REFERENCES edu_aluno(id) DEFERRABLE INITIALLY DEFERRED;
            ALTER TABLE "ae_dadosfincanceiros" ADD CONSTRAINT "ae_dadosfincanceiros_aluno_id_fkey" FOREIGN KEY (aluno_id) REFERENCES edu_aluno(id) DEFERRABLE INITIALLY DEFERRED;
            ALTER TABLE "ae_demandaalunoatendida" ADD CONSTRAINT "ae_demandaalunoatendida_aluno_id_fkey" FOREIGN KEY (aluno_id) REFERENCES edu_aluno(id) DEFERRABLE INITIALLY DEFERRED;
            ALTER TABLE "ae_historicorendafamiliar" ADD CONSTRAINT "ae_historicorendafamiliar_aluno_id_fkey" FOREIGN KEY (aluno_id) REFERENCES edu_aluno(id) DEFERRABLE INITIALLY DEFERRED;
            ALTER TABLE "ae_inscricao" ADD CONSTRAINT "ae_inscricao_aluno_id_fkey" FOREIGN KEY (aluno_id) REFERENCES edu_aluno(id) DEFERRABLE INITIALLY DEFERRED;
            ALTER TABLE "ae_inscricaocaracterizacao" ADD CONSTRAINT "ae_inscricaocaracterizacao_aluno_id_fkey" FOREIGN KEY (aluno_id) REFERENCES edu_aluno(id) DEFERRABLE INITIALLY DEFERRED;

            ALTER TABLE "ae_participacao" ADD CONSTRAINT "ae_participacao_aluno_id_fkey" FOREIGN KEY (aluno_id) REFERENCES edu_aluno(id) DEFERRABLE INITIALLY DEFERRED;
            ALTER TABLE "ae_participacaobolsa" ADD CONSTRAINT "ae_participacaobolsa_aluno_id_fkey" FOREIGN KEY (aluno_id) REFERENCES edu_aluno(id) DEFERRABLE INITIALLY DEFERRED;
        """
        if 'microsoft' in settings.INSTALLED_APPS:
            sql2 += """
            ALTER TABLE "microsoft_registrocriacaoconta" ADD CONSTRAINT "microsoft_registrocriacaoconta_aluno_id_fkey" FOREIGN KEY (aluno_id) REFERENCES edu_aluno(id) DEFERRABLE INITIALLY DEFERRED;
            ALTER TABLE "microsoft_configuracaoacessodreamspark_cursos" DROP CONSTRAINT "microsoft_configuracaoacessodreamspark__cursohabilitado_id_fkey";
            ALTER TABLE microsoft_configuracaoacessodreamspark_cursos rename column "cursohabilitado_id" to "cursocampus_id";
            ALTER TABLE "microsoft_configuracaoacessodreamspark_cursos" ADD CONSTRAINT "microsoft_configuracaoacessodreamspark__cursocampus_id_fkey" FOREIGN KEY (cursocampus_id) REFERENCES edu_cursocampus(id) DEFERRABLE INITIALLY DEFERRED;
        """

        sql3 = """
            DROP TABLE academico_atuacaodocente;
            DROP TABLE academico_atuacaodisciplina;
            DROP TABLE academico_atuacaodisciplinagrupo;
            DROP TABLE academico_atuacaoeixo;
            DROP TABLE academico_historicosituacaomatriculaperiodo;
            DROP TABLE academico_historicosituacaomatricula;
            DROP TABLE academico_matriculaperiodo;
            DROP TABLE academico_turma;
            DROP TABLE academico_aluno;
            DROP TABLE academico_situacaomatriculaperiodo;
            DROP TABLE academico_situacaomatricula;
            DROP TABLE academico_curso;
            DROP TABLE academico_cursohabilitado;
            DROP TABLE academico_nivelensino;
            DROP TABLE academico_gruponivelensino;
            DROP TABLE academico_areacurso;
            DROP TABLE academico_instituicao;
        """
        from django.db import connection

        cur = connection.cursor()
        cur.execute(sql1)
        connection._commit()
        cur = connection.cursor()
        cur.execute(sql2)
        connection._commit()
        cur.execute(sql3)
        connection._commit()
