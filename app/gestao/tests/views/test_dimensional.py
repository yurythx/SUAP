import pytest

from edu.models import Aluno, MatriculaPeriodo, Modalidade
from edu.tests.factories import AlunoFactory, CursoCampusFactory, MatriculaPeriodoFactory, ModalidadeFactory
from edu.utils import TabelaCampusPorModalidade
from rh.tests.factories import ServidorFactory, SetorFactory

pytestmark = pytest.mark.django_db


def _aluno_de_curso_com_modalidade() -> Aluno:
    """Aluno de um curso de campus (novo) com modalidade — o mínimo que a tabela por campus x modalidade conta."""
    return AlunoFactory(curso_campus=CursoCampusFactory(modalidade=ModalidadeFactory()))


class TestTabelaCampusPorModalidade:
    """
    Testes unitários sobre a construção da tabela bi-dimensional
    usada por gestao.views.detalhar_variavel.
    """

    def test_colunas_e_total_com_qs_alunos_vazio(self):
        # a linha TOTAL só existe com 2+ campi (djtools.crosstab: n_linhas > 1)
        _aluno_de_curso_com_modalidade()
        _aluno_de_curso_com_modalidade()
        tabela = TabelaCampusPorModalidade(qs_matriculas1=None, qs_alunos=Aluno.objects.none(), uo=None)

        # 1) Cabeçalho: CAMPUS + (todas modalidades) + TOTAL
        assert tabela.colunas[0] == 'CAMPUS'
        assert tabela.colunas[-1] == 'TOTAL'
        assert len(tabela.colunas) == 1 + Modalidade.objects.count() + 1

        # 2) Última linha é o TOTAL
        assert tabela.registros
        assert tabela.registros[-1][0] == 'TOTAL'

    def test_so_total_quando_filtrado_por_uo(self):
        aluno = _aluno_de_curso_com_modalidade()
        _aluno_de_curso_com_modalidade()  # outro campus: não entra na contagem
        uo = aluno.curso_campus.diretoria.setor.uo
        tabela = TabelaCampusPorModalidade(qs_matriculas1=None, qs_alunos=Aluno.objects.all(), uo=uo)

        # quando 'uo' é informado, a tabela mostra apenas a linha TOTAL, com os números do campus
        assert len(tabela.registros) == 1
        assert tabela.registros[0][0] == 'TOTAL'
        assert tabela.registros[0][len(tabela.colunas) - 1] == Aluno.objects.filter(curso_campus__diretoria__setor__uo=uo).count()

    def test_contagem_correta_para_um_aluno(self):
        aluno = _aluno_de_curso_com_modalidade()
        _aluno_de_curso_com_modalidade()  # segundo campus: habilita a linha TOTAL e não entra na contagem
        uo_sigla = aluno.curso_campus.diretoria.setor.uo.sigla
        modalidade_desc = aluno.curso_campus.modalidade.descricao

        tabela = TabelaCampusPorModalidade(
            qs_matriculas1=None,
            qs_alunos=Aluno.objects.filter(pk=aluno.pk),
            uo=None,
        )

        # localiza a linha do campus do aluno
        linha = next((r for r in tabela.registros if r.get(0) == uo_sigla), None)
        assert linha is not None, 'Linha do campus não encontrada na tabela.'

        # acha o índice da coluna da modalidade do aluno
        assert modalidade_desc in tabela.colunas, 'Modalidade do aluno não apareceu no cabeçalho.'
        idx_modalidade = tabela.colunas.index(modalidade_desc)

        # deve haver 1 na célula correspondente + total da linha == 1
        assert linha[idx_modalidade] == 1
        assert linha[len(tabela.colunas) - 1] == 1

        # total geral (última linha) também deve ser 1
        assert tabela.registros[-1][0] == 'TOTAL'
        assert tabela.registros[-1][len(tabela.colunas) - 1] == 1

    def test_contagem_correta_para_matricula_periodo(self):
        aluno = _aluno_de_curso_com_modalidade()
        MatriculaPeriodoFactory(aluno=aluno)
        mp_qs = MatriculaPeriodo.objects.filter(aluno=aluno)

        uo_sigla = aluno.curso_campus.diretoria.setor.uo.sigla
        modalidade_desc = aluno.curso_campus.modalidade.descricao

        tabela = TabelaCampusPorModalidade(
            qs_matriculas1=mp_qs,
            qs_alunos=None,
            uo=None,
        )

        linha = next((r for r in tabela.registros if r.get(0) == uo_sigla), None)
        assert linha is not None

        assert modalidade_desc in tabela.colunas
        idx_modalidade = tabela.colunas.index(modalidade_desc)

        assert linha[idx_modalidade] == 1
        assert linha[len(tabela.colunas) - 1] == 1
        assert tabela.registros[-1][len(tabela.colunas) - 1] == 1


class TestEstatisticaView:
    """
    Exercita a view edu/views/relatorios.py::estatistica
    focando na integração com TabelaResumoAluno.
    """

    def test_estatistica_cria_tabela_e_series(self, client, sync_permissions):
        # a view exige a permissão de ponto; superusuário a tem
        user = ServidorFactory().get_user()
        user.is_superuser = True
        user.save()
        client.force_login(user)

        # assegura que exista pelo menos 1 aluno matriculado para não ficar tudo zero
        matricula_periodo = MatriculaPeriodoFactory(aluno=_aluno_de_curso_com_modalidade())
        ano = matricula_periodo.ano_letivo.pk
        url = f'/edu/estatistica/?tab=listagem&situacao_matricula_periodo=SITUACAO_MATRICULADO&periodicidade=por_ano_letivo&apartir_do_ano={ano}'

        response = client.get(url)
        assert response.status_code == 200
        # sanity check da tela
        assert 'Estatísticas' in response.content.decode()

        # o retorno usa rtr() com locals(), então os objetos ficam no context
        tabela = response.context.get('tabela')
        series = response.context.get('series')

        assert tabela is not None, 'TabelaResumoAluno não veio no contexto.'
        assert hasattr(tabela, 'colunas'), 'Tabela sem o atributo "colunas".'
        assert hasattr(tabela, 'registros'), 'Tabela sem o atributo "registros".'
        assert isinstance(series, list)
        assert len(series) > 0, 'Series do gráfico não foi montada.'

        # confere se a soma das colunas por modalidade == total geral (linha final da tabela)
        total_linha_final = tabela.registros[-1][len(tabela.colunas) - 1]
        soma_series = sum(v for _, v in series)  # series = [[modalidade, valor], ...]
        assert soma_series == total_linha_final, 'Série do gráfico não bate com a linha de total da tabela.'
        assert total_linha_final == 1
