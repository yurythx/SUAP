import os
import re
from django.core.exceptions import ValidationError
from edu.models import Aluno


PADRAO_NOME_DO_ARQUIVO = r'(?<=_)[^_]+$'


def validar_nome_do_arquivo(nome_do_arquivo):
    if re.search(PADRAO_NOME_DO_ARQUIVO, nome_do_arquivo) is None:
        raise ValidationError(
            'Padrão de arquivo incorreto. O nome deve terminar com "_" seguido da matrícula do aluno (ex: Nome_do_Aluno_MATRICULA.pdf).'
        )


def validar_aluno(nome_arquivo, campus):
    matricula = os.path.splitext(re.findall(PADRAO_NOME_DO_ARQUIVO, nome_arquivo)[0])[0]
    aluno = Aluno.objects.filter(matricula=matricula).first()
    if aluno is None:
        raise ValidationError(
            f'Aluno com matrícula "{matricula}" não encontrado no SUAP. '
            f'Verifique se o nome do arquivo termina com a matrícula do aluno (ex: Nome_do_Aluno_MATRICULA.pdf), '
            f'e se ela é uma matrícula válida no SUAP.'
        )
    if aluno.campus != campus:
        raise ValidationError(f'O aluno está cadastrado no campus {aluno.campus.sigla}, mas a importação sugere campus {campus.sigla}.')

    return matricula, aluno
