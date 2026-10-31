from __future__ import annotations

from collections import defaultdict
from sys import stdout

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from comum.models import Configuracao
from edu.models import Aluno

# Fotos lidas do Q-Acadêmico por vez: limita a memória (binários) e as buscas de aluno (uma por lote).
LOTE = 500


class DAO:
    def __init__(self):
        self.connection = None

    def get_connection(self):
        """Conexão com SQL Server"""
        import pymssql

        if self.connection is None:
            db_host = Configuracao.get_valor_por_chave('edu', 'academico_endereco_banco')
            db_user = Configuracao.get_valor_por_chave('edu', 'academico_usuario_banco')
            db_password = Configuracao.get_valor_por_chave('edu', 'academico_senha_banco')
            db_name = Configuracao.get_valor_por_chave('edu', 'academico_nome_banco_binarios')

            self.connection = pymssql.connect(
                host=db_host,
                user=db_user,
                password=db_password,
                database=db_name,
                as_dict=True,
                tds_version='7.0',
            )
        return self.connection

    def get_fotos_qtd(self):
        sql = 'SELECT count(*) as c FROM FW_CONTEUDOS_BINARIOS WHERE tipo_conteudo_binario = 0'
        cursor = self.get_connection().cursor()
        cursor.execute(sql)
        qtd = cursor.fetchone()['c']
        cursor.close()
        return qtd

    def atualizar_fotos(self, codigo_academico_pf: int | None = None, verbose: int = 0) -> int:
        sql = """
        SELECT cod_conteudo_binario, conteudo_binario
        FROM FW_CONTEUDOS_BINARIOS
        WHERE tipo_conteudo_binario = 0
        """
        if codigo_academico_pf:
            sql += f' AND cod_conteudo_binario = {codigo_academico_pf}'
        fotos_qtd = self.get_fotos_qtd()
        percentual = 0
        contador = 1
        importados = 0

        cursor = self.get_connection().cursor()
        cursor.execute(sql)

        rows = cursor.fetchmany(LOTE)
        while rows:
            # Uma busca por lote de fotos, não uma por foto (#17799). As mesmas instâncias são
            # reusadas se o código se repetir no lote, então a 2ª foto vê a 1ª já gravada, como antes.
            alunos_por_codigo = self.get_alunos_por_codigo([row['cod_conteudo_binario'] for row in rows])
            for row in rows:
                for aluno in alunos_por_codigo.get(row['cod_conteudo_binario'], []):
                    importados += self.importar_foto(aluno, row['conteudo_binario'])

                if verbose:
                    percentual = self.exibir_progresso(contador, fotos_qtd, percentual)

                contador += 1

            rows = cursor.fetchmany(LOTE)

        cursor.close()

        return importados

    def get_alunos_por_codigo(self, codigos: list[int]) -> dict[int, list[Aluno]]:
        alunos_por_codigo = defaultdict(list)
        # Mantém a ordenação padrão do Aluno (pessoa_fisica__nome) dentro de cada código.
        for aluno in Aluno.objects.filter(codigo_academico_pf__in=set(codigos)):
            alunos_por_codigo[aluno.codigo_academico_pf].append(aluno)
        return alunos_por_codigo

    def importar_foto(self, aluno: Aluno, conteudo: bytes) -> int:
        if aluno.foto.name:
            return 0
        # update_fields: a instância foi carregada no início do lote; o save completo sobrescreveria
        # o que outro processo editasse no aluno nesse meio-tempo.
        try:
            aluno.foto.save(f'{aluno.pk}.jpg', ContentFile(conteudo), save=False)
            aluno.save(update_fields=['foto'])
            return 1
        except Exception:
            stdout.write(f'[FAIL] {aluno.matricula}\n')
            default_storage.delete(aluno.foto.name)
            aluno.foto = ''
            aluno.save(update_fields=['foto'])
            return 0

    def exibir_progresso(self, contador: int, fotos_qtd: int, percentual: str | int) -> str | int:
        percentual_atual = f'{contador / float(fotos_qtd) * 100:.0f}'
        if percentual_atual != percentual:
            percentual = percentual_atual
            stdout.write(f'Importando fotos: {percentual}%%\r')
            stdout.flush()
        return percentual
