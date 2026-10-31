"""Ações que mudam o estado do objeto no GET, sobre objetos de sacrifício.

Estavam dispensadas com motivo de harness ("corromperia a cadeia"). O motivo era verdadeiro e
a solução é ter objeto próprio: um aluno criado só para ser evadido, um registro de convocação
ENADE só para ter a situação removida, e o minicurso do smoke — que é um ``CursoCampus`` — para
o toggle de processamento ENADE, que grava no **curso**, não na convocação.

O aluno vem de ``seed.cadastrar_aluno``/``seed.matricular_aluno``, os mesmos passos da cadeia:
reimplementá-los aqui criaria uma segunda verdade sobre "o que é um aluno matriculado".
"""

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

DESCARTAVEIS = (
    '/edu/evadir_aluno/{aluno_evasao}/',
    '/edu/remover_situacao_enade/{registro_enade_descartavel}/',
    # O toggle escreve em `curso.processamento_enade` (`edu/views/enade.py:200`): o curso é que
    # precisa ser descartável, não a convocação.
    '/edu/habilitar_desabilitar_curso_enade/{convocacao_enade}/{minicurso}/',
)


def test_acoes_sobre_objeto_descartavel_abrem(abrir_rotas):
    abrir_rotas('admin_academico', DESCARTAVEIS)


# Ações que gravam no diário. O alvo é a turma de 2018 criada por
# `seed_rotas.criar_diario_descartavel` — nenhum diário da cadeia é tocado.
# `encerrar` vem antes de `remover`: a segunda apaga a suspensão, e a fábrica a recria na
# execução seguinte.
DIARIO = (
    '/edu/gerar_configuracoes_avaliacao/{diario_descartavel}/',
    '/edu/dividir_diario/{diario_descartavel}/',
    '/edu/dividir_diario_reprovados_dependentes/{diario_descartavel}/',
    '/edu/replicar_diario/{diario_descartavel}/',
    '/edu/transferir_posse_diario/{diario_descartavel}/{etapa}/{um}/',
    '/edu/encerrar_suspensao_diario/{suspensao_diario}/',
    '/edu/remover_suspensao_diario/{suspensao_diario}/',
)


def test_acoes_de_diario_abrem(abrir_rotas):
    abrir_rotas('admin_academico', DIARIO)
