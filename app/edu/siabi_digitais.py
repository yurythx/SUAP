from sys import stdout

import tqdm

from comum.models import Configuracao
from edu.models import Aluno


class DAO:
    def __init__(self):
        self.connection = None

    def get_connection(self):
        """Conexão com SQL Server"""
        import pymssql

        database_host = Configuracao.get_valor_por_chave('edu', 'siabi_endereco_banco')
        database_user = Configuracao.get_valor_por_chave('edu', 'siabi_usuario_banco')
        database_password = Configuracao.get_valor_por_chave('edu', 'siabi_senha_banco')
        database_name = Configuracao.get_valor_por_chave('edu', 'siabi_nome_banco')

        if self.connection is None:
            self.connection = pymssql.connect(
                host=database_host,
                user=database_user,
                password=database_password,
                database=database_name,
                as_dict=True,
                tds_version='7.0',
            )
        return self.connection

    def atualizar_digitais(self, verbose=0):
        stdout.write('\rImportando digitais\r\n')
        sql = """
        SELECT count(*) as c
        FROM CIR_USU_X_DIGI
        WHERE USUARIO LIKE '20%'
          AND SEQ_DIGI = 1"""
        cursor = self.get_connection().cursor()
        cursor.execute(sql)
        digitais_qtd = cursor.fetchone()['c']
        cursor.close()
        digitais_nulas_qtd = 0
        encontrados_qtd = 0
        nao_encontrados_qtd = 0
        erros_encode = 0
        contador = 1

        sql = """
        SELECT USUARIO, DIGITAL_USU
        FROM CIR_USU_X_DIGI
        WHERE USUARIO LIKE '20%'
          AND SEQ_DIGI = 1
        """
        cursor = self.get_connection().cursor()
        cursor.execute(sql)

        for row in tqdm.tqdm(cursor.fetchall()):
            alunos = Aluno.objects.filter(matricula=row['USUARIO'].strip().replace('M', ''))
            if alunos:
                encontrados_qtd += 1
                if row['DIGITAL_USU']:
                    try:
                        pessoa_fisica = alunos[0].pessoa_fisica
                        if pessoa_fisica.template is None and not pessoa_fisica.template_importado_terminal:
                            pessoa_fisica.template = row['DIGITAL_USU'].decode('latin-1').encode()
                            pessoa_fisica.save()
                    except UnicodeDecodeError:
                        print(f'<<<< Matrícula com erro de encode: {alunos[0].matricula}')
                        erros_encode += 1

                else:
                    digitais_nulas_qtd += 1
            else:
                nao_encontrados_qtd += 1

            contador += 1

        cursor.close()

        if verbose:
            stdout.write('\rImportando digitais: 100%\r\n')
            print(f'Alunos cadastrados na biblioteca: {digitais_qtd}\t')
            print(f'Alunos cadastrados sem digital..: {digitais_nulas_qtd}\t')
            print(f'Alunos encontrados no suap......: {encontrados_qtd}\t')
            print(f'Alunos nao encontrados no suap..: {nao_encontrados_qtd}\t')
            print(f'Digitais com erros de encode....: {erros_encode}\t')
