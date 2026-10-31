"""Lista de alunos (``lista_alunos``) e gráfico de alergias do relatório médico/enfermagem: a alergia alimentar vem também da Nutrição e Alimentação (Demanda 2301, #17627).

O formulário atual não grava mais ``alergia_alimentos`` no Processo Saúde-Doença; a alergia passou a ser declarada na
Nutrição e Alimentação, que mora na avaliação (ou no atendimento nutricional), não no atendimento médico/enfermagem
que a lista percorre. Por isso a lista consulta a nutrição mais recente do prontuário, como o prontuário já faz.
"""

from uuid import uuid4

import openpyxl
import pytest
from django.contrib.auth.models import Permission
from django.test import Client
from model_bakery import baker, random_gen

from djtools.models import Task
from djtools.storages.utils import download_temporary_file
from edu.models import Aluno, Turma
from edu.tests.factories import AlunoFactory, ModalidadeFactory, TurnoFactory
from rh.models import Servidor
from rh.tests.factories import PessoaFisicaFactory
from saude.models import Atendimento, Prontuario, SituacaoAtendimento, TipoAtendimento
from saude.tests.factories import NutricaoAlimentacaoFactory, ProcessoSaudeDoencaFactory

URL = '/saude/lista_alunos/'
COLUNA = 'Alergia à Alimentos'


@pytest.fixture
def lista(profissional: Client, servidor_profissional: Servidor):
    """Abre a lista de alunos (filtros e colunas pedidos em ``**filtros``) no campus do profissional logado."""
    servidor_profissional.get_user().user_permissions.add(Permission.objects.get(codename='view_atividadegrupo', content_type__app_label='saude'))

    def abrir(**filtros: str):
        parametros = {'campus': servidor_profissional.setor.uo_id, 'ver_nome': 'on', 'alergia_alimentos': 'on', **filtros}
        return profissional.get(URL, parametros)

    return abrir


@pytest.fixture
def aluno_atendido(servidor_profissional: Servidor):
    """Aluno com avaliação (processo saúde-doença do form atual: sem ``alergia_alimentos``) e atendimento médico que copia o processo.

    ``nutricoes`` são as fichas de nutrição da avaliação, da mais antiga para a mais recente.
    """
    user = servidor_profissional.get_user()

    def criar(*nutricoes: dict, aluno: Aluno | None = None, **processo: object) -> Atendimento:
        aluno = aluno or AlunoFactory()
        prontuario = Prontuario.get_prontuario(aluno.get_vinculo())
        avaliacao = Atendimento.abrir(TipoAtendimento.AVALIACAO_BIOMEDICA, prontuario, aluno, user)
        ProcessoSaudeDoencaFactory(atendimento=avaliacao, profissional=user, **processo)
        for nutricao in nutricoes:
            NutricaoAlimentacaoFactory(atendimento=avaliacao, profissional=user, **nutricao)
        return Atendimento.abrir(TipoAtendimento.ENFERMAGEM_MEDICO, prontuario, aluno, user)

    return criar


def _linhas_xls(resposta) -> list[tuple]:
    """Linhas (cabeçalho primeiro) do XLS gerado pela task a que a view redirecionou."""
    tarefa = Task.objects.get(uuid=resposta.url.rstrip('/').rsplit('/', 1)[-1])
    return list(openpyxl.load_workbook(download_temporary_file(tarefa.file)).active.iter_rows(values_only=True))


def _novo_atendimento(atendimento: Atendimento) -> Atendimento:
    """Fecha o atendimento médico/enfermagem e abre outro para o mesmo aluno (a ficha de saúde-doença é copiada)."""
    Atendimento.objects.filter(pk=atendimento.pk).update(situacao=SituacaoAtendimento.FECHADO)
    return Atendimento.abrir(TipoAtendimento.ENFERMAGEM_MEDICO, atendimento.prontuario, atendimento.aluno, atendimento.usuario_aberto)


def test_aluno_com_dois_atendimentos_sai_uma_vez_na_tela_e_no_xls(lista, aluno_atendido) -> None:
    primeiro = aluno_atendido(alergia_alimentos=True, que_alimentos='Leite')
    segundo = _novo_atendimento(primeiro)
    outro = aluno_atendido(alergia_alimentos=True, que_alimentos='Ovo')
    assert segundo.aluno == primeiro.aluno

    na_tela = lista(ver_matricula='on').context['atendimentos']
    _, *no_xls = _linhas_xls(lista(ver_matricula='on', xls='1'))

    assert len(na_tela) == 2
    assert [linha[1] for linha in no_xls] == [a.aluno.pessoa_fisica.nome for a in na_tela]
    assert {linha[1] for linha in no_xls} == {primeiro.aluno.pessoa_fisica.nome, outro.aluno.pessoa_fisica.nome}


def test_alunos_homonimos_saem_em_linhas_separadas(lista, aluno_atendido) -> None:
    primeiro = aluno_atendido(
        aluno=AlunoFactory(pessoa_fisica=PessoaFisicaFactory(nome='Maria da Silva')), alergia_alimentos=True, que_alimentos='Leite'
    )
    segundo = aluno_atendido(
        aluno=AlunoFactory(pessoa_fisica=PessoaFisicaFactory(nome='Maria da Silva')), alergia_alimentos=True, que_alimentos='Ovo'
    )

    na_tela = lista(ver_matricula='on').context['atendimentos']
    _, *no_xls = _linhas_xls(lista(ver_matricula='on', xls='1'))

    assert set(na_tela) == {primeiro, segundo}
    assert {linha[2] for linha in no_xls} == {primeiro.aluno.matricula, segundo.aluno.matricula}


@pytest.fixture
def matricular_em_turma(monkeypatch: pytest.MonkeyPatch):
    """Matricula o aluno numa turma nova (sem ``TurmaFactory``: o bakery cria o grafo do edu, com os campos do SUAP registrados)."""
    monkeypatch.setattr(baker.generators, 'user_mapping', dict(baker.generators.user_mapping))
    for campo, gerador in {
        'CharFieldPlus': random_gen.gen_string,
        'ForeignKeyPlus': random_gen.gen_related,
        'DateFieldPlus': random_gen.gen_date,
        'DateTimeFieldPlus': random_gen.gen_datetime,
        'DecimalFieldPlus': random_gen.gen_decimal,
        'OneToOneFieldPlus': random_gen.gen_related,
        'SearchField': random_gen.gen_text,
    }.items():
        baker.generators.add(f'djtools.db.models.{campo}', gerador)

    def matricular(aluno: Aluno) -> Turma:
        curso = baker.make('edu.CursoCampus', modalidade=ModalidadeFactory(), descricao_historico='Curso', codigo=uuid4().hex[:8])
        turma = baker.make('edu.Turma', curso_campus=curso, turno=TurnoFactory())
        baker.make('edu.MatriculaPeriodo', aluno=aluno, turma=turma)
        return turma

    return matricular


def test_coluna_turma_do_xls_traz_a_ultima_turma_cursada_como_a_tela(lista, aluno_atendido, matricular_em_turma) -> None:
    atendimento = aluno_atendido(alergia_alimentos=True, que_alimentos='Leite')
    matricular_em_turma(atendimento.aluno)
    ultima = matricular_em_turma(atendimento.aluno)

    cabecalho, linha = _linhas_xls(lista(ver_matricula='on', ver_turma='on', xls='1'))

    assert linha[cabecalho.index('Turma')] == str(ultima)
    assert linha[cabecalho.index('Turma')] != atendimento.aluno.matricula


def test_filtro_acha_aluno_cuja_alergia_esta_so_na_nutricao(lista, aluno_atendido) -> None:
    so_na_nutricao = aluno_atendido({'tem_alergia_alimentos': True, 'alergia_alimentos_outros': 'Amendoim'})
    na_ficha_antiga = aluno_atendido(alergia_alimentos=True, que_alimentos='Leite')
    aluno_atendido({'tem_alergia_alimentos': False})
    aluno_atendido()

    resposta = lista()

    assert set(resposta.context['atendimentos']) == {so_na_nutricao, na_ficha_antiga}


def test_filtro_considera_a_nutricao_mais_recente(lista, aluno_atendido) -> None:
    deixou_de_ter = aluno_atendido({'tem_alergia_alimentos': True, 'alergia_alimentos_outros': 'Soja'}, {'tem_alergia_alimentos': False})
    passou_a_ter = aluno_atendido({'tem_alergia_alimentos': False}, {'tem_alergia_alimentos': True, 'alergia_alimentos_outros': 'Ovo'})

    resposta = lista()

    assert set(resposta.context['atendimentos']) == {passou_a_ter}
    assert deixou_de_ter not in resposta.context['atendimentos']


def test_coluna_mostra_a_alergia_da_nutricao_e_mantem_a_da_ficha_antiga(lista, aluno_atendido) -> None:
    aluno_atendido({'tem_alergia_alimentos': True, 'alergia_alimentos_outros': 'Amendoim'})
    aluno_atendido(alergia_alimentos=True, que_alimentos='Leite')

    html = lista().content.decode()

    assert COLUNA in html
    assert 'Amendoim' in html
    assert 'Leite' in html


def test_xls_traz_a_alergia_da_nutricao_e_da_ficha_antiga(lista, aluno_atendido) -> None:
    nutricao = aluno_atendido({'tem_alergia_alimentos': True, 'alergia_alimentos_outros': 'Amendoim'})
    antiga = aluno_atendido(alergia_alimentos=True, que_alimentos='Leite')

    cabecalho, *dados = _linhas_xls(lista(xls='1'))

    alergia = cabecalho.index(COLUNA)
    assert {linha[1]: linha[alergia] for linha in dados} == {
        nutricao.aluno.pessoa_fisica.nome: 'Amendoim',
        antiga.aluno.pessoa_fisica.nome: 'Leite',
    }


def test_grafico_de_alergias_do_relatorio_medico_enfermagem_conta_a_alergia_da_nutricao(
    lista, aluno_atendido, profissional: Client, servidor_profissional: Servidor
) -> None:
    """O gráfico "Alergias à Alimentos e Medicamentos" segue a mesma regra do filtro da lista de alunos."""
    aluno_atendido({'tem_alergia_alimentos': True, 'alergia_alimentos_outros': 'Amendoim'})
    aluno_atendido(alergia_alimentos=True)
    aluno_atendido({'tem_alergia_alimentos': True}, {'tem_alergia_alimentos': False})
    aluno_atendido(alergia_medicamentos=True)

    resposta = profissional.get('/saude/relatorio_atendimento_medico_enfermagem/', {'campus': servidor_profissional.setor.uo_id})

    (grafico,) = [grafico for grafico in resposta.context['pie_chart_lists'] if grafico.id == 'grafico3']
    assert dict(zip(grafico.xAxis['categories'], grafico.series[0]['data'], strict=True)) == {
        'Alunos com Alergias à Alimentos': 2,
        'Alunos com Alergias à Medicamentos': 1,
    }
