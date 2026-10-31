from behave import given
from django.apps.registry import apps

Aluno = apps.get_model('edu', 'Aluno')
Matriz = apps.get_model('sica', 'Matriz')
Historico = apps.get_model('sica', 'Historico')
Componente = apps.get_model('sica', 'Componente')
ComponenteCurricular = apps.get_model('sica', 'ComponenteCurricular')


@given('os dados básicos do sica')
def step_dados_basicos_sica(context):
    aluno = Aluno.objects.get(matricula='20101101011031')
    matriz = Matriz.objects.get(codigo='32')
    comp = Componente.objects.get(codigo='125')

    componente = ComponenteCurricular.objects.create(matriz=matriz, componente=comp, periodo=2)
    historico = Historico.objects.create(aluno=aluno, matriz=matriz)
    historico.componentes_curriculares.add(componente)
