import pytest

from pnp.models import MatriculaPNP
from pnp.tasks import gravar_matriculas, gravar_vinculos

from .test_matching_matriculas import CODIGO_ESTRUTURA, campus, criar_aluno, criar_curso, linha


@pytest.mark.django_db
def test_gravar_matriculas_e_idempotente_e_atualiza_os_dados_brutos():
    gravar_matriculas([linha(), linha(matricula='999')])

    gravar_matriculas([linha(nome='NOME CORRIGIDO')])

    assert MatriculaPNP.objects.count() == 2
    assert MatriculaPNP.objects.get(matricula='123231971').nome == 'NOME CORRIGIDO'


@pytest.mark.django_db
def test_gravar_vinculos_nao_desfaz_vinculo_ja_existente(campus):
    curso = criar_curso(campus, 'Técnico em Alimentos')
    aluno = criar_aluno('AALIYAH HADASSAH', '711.225.514-79', '20211014040001', curso)
    outro = criar_aluno('OUTRA PESSOA', '733.733.733-79', '20211014040002', curso)
    gravar_matriculas([linha()])
    gravar_vinculos({'123231971': (aluno.id, None)})

    vinculados = gravar_vinculos({'123231971': (outro.id, None)})

    assert MatriculaPNP.objects.get().aluno == aluno
    assert vinculados == 0, 'só conta o que passou a ter vínculo nesta chamada'


@pytest.mark.django_db
def test_gravar_vinculos_preenche_o_que_ainda_esta_em_branco(campus):
    from pnp.models import EstruturaPNP

    curso = criar_curso(campus, 'Técnico em Alimentos')
    aluno = criar_aluno('AALIYAH HADASSAH', '711.225.514-79', '20211014040001', curso)
    estrutura = EstruturaPNP.objects.get(codigo=CODIGO_ESTRUTURA)
    gravar_matriculas([linha()])

    assert gravar_vinculos({'123231971': (aluno.id, estrutura.id)}) == 1

    registro = MatriculaPNP.objects.get()
    assert (registro.aluno, registro.estrutura) == (aluno, estrutura)
