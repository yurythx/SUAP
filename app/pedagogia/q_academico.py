from sys import stdout

from comum.models import Configuracao
from edu.models import CursoCampus
from pedagogia.models import ItemQuestionarioMatriz, QuestionarioMatriz


class DAO:
    @staticmethod
    def get_connection():
        """Conexão com SQL Server"""
        import pymssql

        db_host = Configuracao.get_valor_por_chave('edu', 'academico_endereco_banco')
        db_user = Configuracao.get_valor_por_chave('edu', 'academico_usuario_banco')
        db_password = Configuracao.get_valor_por_chave('edu', 'academico_senha_banco')
        db_name = Configuracao.get_valor_por_chave('edu', 'academico_nome_banco_padrao')

        return pymssql.connect(
            host=db_host,
            user=db_user,
            password=db_password,
            database=db_name,
            as_dict=True,
            tds_version='7.0',
        )

    def importar_matrizes(self):
        sql = """
        SELECT
                distinct(mc.COD_MATRIZ_CURRICULAR) as cod_matriz,
                dmc.N_PERIODO as periodo,
                d.DESC_HISTORICO as disciplina,
                st.DESCRICAO as nucleo,
                dmc.CREDITOS as aulas,
                d.SIGLA_DISCIPLINA as sigla,
                mc.COD_CURSO as codigo_curso
        FROM DISCIPLINAS_MATRIZES_CURRICULARES dmc
        JOIN SITUACOES_TABELAS st ON (st.NOME_TABELA = 'DISCIPLINAS_MATRIZES_CURRICULARES' and
                                     st.NOME_COLUNA = 'NUCLEO_DISCIPLINA' and
                                      st.VALOR = dmc.NUCLEO_DISCIPLINA)
        JOIN DISCIPLINAS d ON dmc.COD_DISCIPLINA = d.COD_DISCIPLINA
        JOIN MATRIZES_CURRICULARES mc ON dmc.COD_MATRIZ_CURRICULAR = mc.COD_MATRIZ_CURRICULAR
        JOIN MATRICULAS m ON mc.COD_MATRIZ_CURRICULAR = m.COD_MATRIZ_CURRICULAR
        WHERE dmc.OPTATIVA = 0 and m.SIT_MATRICULA in (0)
        ORDER BY mc.COD_MATRIZ_CURRICULAR, dmc.N_PERIODO, d.DESC_HISTORICO
        """

        cur = DAO.get_connection().cursor()
        cur.execute(sql)
        row = cur.fetchone()
        # count = 0
        while row:
            # count+=1
            # if count > 10: break
            nucleo = ''
            nucleo_aux = len(row['sigla'].split('.')) > 1 and row['sigla'].split('.')[1] or ''
            disciplina_aux = row['disciplina'].split(' ')[0].lower()

            if nucleo_aux == 'ndp':
                nucleo = '2. Núcleo Didático Pedagógico'
            elif nucleo_aux == 'nep':
                nucleo = '3. Núcleo Epistemológico'
            elif nucleo_aux in ('nfd', 'fnd'):
                nucleo = '1. Núcleo Fundamental'
            elif disciplina_aux == 'seminário':
                nucleo = '5. Seminário Curriculares(Obrigatórias)'
            elif disciplina_aux == 'estágio':
                nucleo = '6. Prática Profissional'
            else:
                nucleo = '4. Núcleo Específico'

            curso_campus = CursoCampus.objects.get(codigo_academico=row['codigo_curso'])
            questionario_matriz, _criado = QuestionarioMatriz.objects.get_or_create(academico_matriz=row['cod_matriz'], curso_campus=curso_campus)
            ItemQuestionarioMatriz.objects.get_or_create(
                questionario_matriz=questionario_matriz,
                disciplina=row['disciplina'],
                nucleo=nucleo,
                periodo=row['periodo'],
                aulas_por_semana=row['aulas'] or 0,
            )

            row = cur.fetchone()
        cur.close()
        stdout.write('\rImportando matrizes : 100%\r\n')

    @staticmethod
    def get_matriz_aluno(matricula):
        sql = f"SELECT cod_matriz_curricular as cod_matriz FROM matriculas m WHERE m.matricula = '{matricula}'"
        cur = DAO.get_connection().cursor()
        cur.execute(sql)
        row = cur.fetchone()
        while row:
            return row['cod_matriz']
