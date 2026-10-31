import datetime
import os

from django.conf import settings

from djtools.utils import mask_numbers, to_ascii
from edu.models import Modalidade

MODALIDADES = (
    Modalidade.INTEGRADO_EJA,
    Modalidade.FIC_INTEGRADO_EJA,
    Modalidade.INTEGRADO,
    Modalidade.SUBSEQUENTE,
    Modalidade.CONCOMITANTE,
    Modalidade.LICENCIATURA,
    Modalidade.LICENCIATURA_DUPLA_HABILITACAO,
    Modalidade.APERFEICOAMENTO,
    Modalidade.ENGENHARIA,
    Modalidade.BACHARELADO,
    Modalidade.MESTRADO,
    Modalidade.ESPECIALIZACAO,
    Modalidade.DOUTORADO,
    Modalidade.TECNOLOGIA,
)


class Exportador:
    def __init__(self, matriculas_periodo, task=None):
        hoje = datetime.date.today()
        rows = []
        lista = []
        self.append(lista, '0', 1)  # TipoRegistro
        self.append(lista, hoje.strftime('%d%m%Y'), 8)  # Data_Geracao_Arquivo
        self.append(lista, '10877412000168', 14)  # Cgc
        self.append(lista, 'INSTITUTO FEDERAL DO RIO GRANDE DO NORTE', 50)  # Nome
        self.append(lista, ' ', 316)  # Brancos
        self.append(lista, 1, 10, '0', False)  # NumerodeSequencial
        rows.append(''.join(lista))
        i = 2
        if task:
            matriculas_periodo = task.iterate(matriculas_periodo)
        for matricula_periodo in matriculas_periodo:
            lista = []
            self.append(lista, 1, 1)  # Tipo_Registro
            self.append(lista, matricula_periodo.aluno.pessoa_fisica.nome, 50)  # Nome
            self.append(lista, matricula_periodo.aluno.matricula, 20)  # Matricula
            self.append(lista, matricula_periodo.aluno.pessoa_fisica.nascimento_data.strftime('%d%m%Y'), 8)  # DataNascimento
            self.append(lista, matricula_periodo.aluno.logradouro, 50)  # Endereco
            self.append(lista, matricula_periodo.aluno.numero, 5)  # NumeroEndereco
            self.append(lista, matricula_periodo.aluno.complemento, 20)  # Complemento
            self.append(lista, matricula_periodo.aluno.bairro, 30)  # Bairro
            self.append(lista, matricula_periodo.aluno.cidade, 30)  # Cidade
            self.append(lista, matricula_periodo.aluno.cep, 8, clear=True)  # Cep
            self.append(lista, matricula_periodo.aluno.telefone_principal, 20, clear=True)  # Telefones
            rg = matricula_periodo.aluno.numero_rg and mask_numbers(matricula_periodo.aluno.numero_rg, 'utf8') or ''
            self.append(lista, rg, 10)  # Rg
            email = matricula_periodo.aluno.email_notificacao or matricula_periodo.aluno.email_academico
            self.append(lista, email, 50)  # Email
            self.append(lista, matricula_periodo.aluno.nome_mae, 50)  # NomeMae
            nome_curso = matricula_periodo.aluno.curso_campus.descricao_historico
            # Técnico de Nível Médio em Informática ---> Técnico em Informática
            nome_curso = nome_curso.replace(' de Nivel Médio', '').replace(' de Nível Médio', '')
            if matricula_periodo.aluno.curso_campus.modalidade_id in [Modalidade.INTEGRADO_EJA, Modalidade.FIC_INTEGRADO_EJA]:
                codigo_curso = '01'  # Eja
                codigo_nivel_ensino = '3'
            elif matricula_periodo.aluno.curso_campus.modalidade_id in [Modalidade.INTEGRADO, Modalidade.SUBSEQUENTE, Modalidade.CONCOMITANTE]:
                codigo_curso = '04'  # Secundarista
                codigo_nivel_ensino = '3'
            elif matricula_periodo.aluno.curso_campus.modalidade_id in [
                Modalidade.LICENCIATURA,
                Modalidade.LICENCIATURA_DUPLA_HABILITACAO,
                Modalidade.ENGENHARIA,
                Modalidade.BACHARELADO,
                Modalidade.MESTRADO,
                Modalidade.ESPECIALIZACAO,
                Modalidade.DOUTORADO,
            ]:
                codigo_curso = '05'  # Superior
                codigo_nivel_ensino = '4'
            elif matricula_periodo.aluno.curso_campus.modalidade_id == Modalidade.TECNOLOGIA:
                codigo_curso = '07'  # Tecnologia
                codigo_nivel_ensino = '4'
            self.append(lista, codigo_curso, 2)  # Curso
            self.append(lista, codigo_nivel_ensino, 1)  # Nível
            self.append(lista, matricula_periodo.periodo_matriz, 2, '0')  # SeriePeriodo
            self.append(lista, ' ', 23)  # SeriePeriodo_outros
            turno = '-'
            if matricula_periodo.aluno.turno_id in [3, 5, 6]:
                turno = 'M'
            elif matricula_periodo.aluno.turno_id == 2:
                turno = 'T'
            elif matricula_periodo.aluno.turno_id == 1:
                turno = 'N'
            self.append(lista, turno, 3)  # Turno
            self.append(lista, '487   ', 6, left=False)  # CodigoEscola
            self.append(lista, '  ', 10)  # RU
            self.append(lista, matricula_periodo.aluno.pessoa_fisica.cpf, 11, clear=True)  # CPF
            self.append(lista, i, 10, '0', False)  # Numero_do_Registro
            self.append(lista, nome_curso, 30, clear=True)  # Nome do Curso
            i += 1
            rows.append(''.join(lista))
        lista = []
        self.append(lista, 9, 1)  # TipoRegistro
        self.append(lista, ' ', 387)  # Brancos
        self.append(lista, 1, 10, '0', False)  # NumerodeSequencial
        rows.append(''.join(lista))
        caminho = os.path.join(settings.TEMP_DIR, 'sttu_{}.txt'.format(task and task.id or ''))
        with open(caminho, 'w') as f:
            f.write('\r\n'.join(rows))
        if task:
            task.finalize('Relatório gerado com sucesso', '/edu/relatorio_sttu/', file_path=caminho)

    def append(self, lista, value, width, fillchar=' ', left=True, clear=False):
        value = value or ''
        value = to_ascii(value).upper()
        if clear:
            value = value.replace('-', '').replace('.', '').replace('/', '').replace('(', '').replace(')', '')
        if left:
            value = value.ljust(width, str(fillchar))
        else:
            value = value.rjust(width, str(fillchar))
        lista.append(value[0:width])
