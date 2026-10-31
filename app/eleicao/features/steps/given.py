from behave import given

from comum.models import Publico


@given('os usuarios das Eleições')
def step_impl(context):
    context.execute_steps(
        """
    Dado os seguintes usuários
       | Nome                  | Matrícula         | Setor | Lotação | Email           | CPF            | Senha | Grupo                 |
       | Criador de Eleição    | CriadorEleicao    | DIAC/CEN    | DIAC/CEN      | d01@ifrn.edu.br | 547.115.806-89 | abcd  | Criador de Eleição    |
       | Coordenador de Edital | CoordenadorEdital | DIAC/CEN    | DIAC/CEN      | d02@ifrn.edu.br | 647.115.806-89 | abcd  | Coordenador de Edital |
       | Candidato             | Candidato         | DIAC/CZN    | DIAC/CZN      | d03@ifrn.edu.br | 735.785.191-54 | abcd  | Servidor              |
       | Eleitor 1             | Eleitor1          | DIAC/CZN    | DIAC/CZN      | d04@ifrn.edu.br | 824.587.211-33 | abcd  | Aluno                 |
       | Eleitor 2             | Eleitor2          | DIAC/CZN    | DIAC/CZN      | d05@ifrn.edu.br | 583.596.500-12 | abcd  | Servidor              |
       | Eleitor 3             | Eleitor3          | DIAC/CZN    | DIAC/CZN      | d06@ifrn.edu.br | 227.216.860-46 | abcd  | Servidor              |
"""
    )


@given('um Público cadastrado')
def step_publico_cadastrado(context):
    Publico.objects.get_or_create(nome='Todos do sistema', qs_filter='', modelo_base=Publico.BASE_SERVIDOR)
