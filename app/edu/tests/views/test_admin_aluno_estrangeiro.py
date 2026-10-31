import pytest
from django.contrib import admin
from django.test import RequestFactory

from comum.models import Pais, User
from edu.admin.alunos import AlunoAdmin, AlunoEstrangeiroListFilter
from edu.models import Aluno
from edu.tests.factories import AlunoFactory
from rh.enums import Nacionalidade
from rh.tests.factories import PessoaFisicaFactory

pytestmark = pytest.mark.django_db


def test_filtro_estrangeiro_do_aluno_usa_a_nacionalidade_da_matricula() -> None:
    """Na pessoa física do aluno a nacionalidade quase nunca está preenchida: vale a da matrícula."""
    estrangeiro, brasileiro = AlunoFactory(nacionalidade='Estrangeira'), AlunoFactory(nacionalidade='Brasileira')
    alunos = Aluno.objects.filter(pk__in=[estrangeiro.pk, brasileiro.pk])
    model_admin = AlunoAdmin(Aluno, admin.site)

    def filtrar(valor: str) -> list[int]:
        filtro = AlunoEstrangeiroListFilter(RequestFactory().get('/'), {'estrangeiro': [valor]}, Aluno, model_admin)
        return list(filtro.queryset(None, alunos).values_list('pk', flat=True))

    assert AlunoEstrangeiroListFilter in AlunoAdmin.list_filter
    assert (filtrar('sim'), filtrar('nao')) == ([estrangeiro.pk], [brasileiro.pk])


def test_dados_principais_mostram_o_documento_identificador() -> None:
    argentina = Pais.objects.create(codigo='011', nome='ARGENTINA', iso_alfa3='ARG')
    pessoa = PessoaFisicaFactory(cpf=None, passaporte='AB123456', pais_origem=argentina, nacionalidade=Nacionalidade.ESTRANGEIRO)
    aluno = AlunoFactory(pessoa_fisica=pessoa, nacionalidade='Estrangeira')
    model_admin = AlunoAdmin(Aluno, admin.site)
    model_admin.request = RequestFactory().get('/')
    model_admin.request.user = User.objects.create_superuser('admin-teste', 'admin@exemplo.com', 'x')

    html = model_admin.get_info_principal(aluno)

    assert '<dt>Documento:</dt><dd>ARG-AB123456</dd>' in html
