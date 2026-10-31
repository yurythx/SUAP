"""Fluxo dos relatórios, indicadores e gráficos do Saúde (modo 2).

As telas de relatório só montam o corpo depois do GET do filtro (`{% if form.is_bound %}`), e
por isso cada teste preenche o filtro e clica no botão antes de asserir. Os seis gráficos
clínicos compartilham a mesma casca (filtro, `Exportar para XLS` e o container dos gráficos),
então entram como uma matriz de rotas; os relatórios com indicadores próprios ficam nos testes
nomeados. Os downloads de XLS e os PDFs ficam dispensados.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import Page, expect

from djtools.e2e_ui import Tela

if TYPE_CHECKING:
    from saude.models import Prontuario

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

PRONTUARIO = '/saude/prontuario/{}/'
ADICIONAR_VACINA = '/saude/adicionar_vacina/{}/'
ESTATISTICA_GERAL = '/saude/estatistica_geral_atendimento/'
INDICADORES = '/saude/indicadores/'
GRAFICOS_ANTROPOMETRIA = '/saude/graficos_antropometria/'
GRAFICOS_HABITOS_VIDA = '/saude/graficos_habitos_vida/'
GRAFICOS_VACINAS = '/saude/graficos_vacinas/'
RELATORIO_CARTOES = '/saude/relatorio_cartoes_vacinais/'
RELATORIO_ODONTOLOGIA = '/saude/relatorio_atendimento_odontologia/'
RELATORIO_MEDICO = '/saude/relatorio_atendimento_medico_enfermagem/'
RELATORIO_AVALIACAO = '/saude/relatorio_avaliacao_biomedica/'

# Os seis gráficos clínicos têm a mesma casca: filtro, "Exportar para XLS" e o container
# dos gráficos Highcharts. A matriz é a documentação executável de quais existem.
GRAFICOS = [
    ('/saude/graficos_acuidade_visual/', 'Acuidade visual'),
    ('/saude/graficos_saude_doenca/', 'Processo saúde-doença'),
    ('/saude/graficos_desenvolvimento_pessoal/', 'Desenvolvimento pessoal'),
    ('/saude/graficos_exame_fisico/', 'Exame físico'),
    ('/saude/graficos_percepcao_saude_bucal/', 'Percepção de Saúde Bucal'),
]


def _aluno_e_prontuario() -> tuple[object, Prontuario]:
    """Resolve a âncora criada em ``test_01`` ou explica a dependência sequencial."""
    from edu.models import Aluno
    from saude.models import Prontuario

    aluno = Aluno.objects.get(matricula='20191101011111')
    prontuario = Prontuario.objects.filter(vinculo=aluno.get_vinculo()).first()
    assert prontuario is not None, 'prontuário ausente: a cadeia é sequencial, rode `pytest saude/tests/e2e` inteiro'
    return aluno, prontuario


def test_graficos_habitos_vida_responde_200_com_registro(logado_saude: Callable[[str], Page]) -> None:
    """A tela de Hábitos de Vida responde 200 com o registro, mesmo sem objetivo de uso da internet.

    O `HabitosDeVidaForm` não oferece o campo `objetivo_uso_internet`, então o registro nasce
    com `None`; a tela tratava o valor como texto e estourava em 500 (#17609). Agora ela
    reutiliza os gráficos do relatório de avaliação, que tratam o `None` como texto vazio.
    """
    tela = Tela(logado_saude('coordenador_sistemico'))

    resposta = tela.buscar(f'{GRAFICOS_HABITOS_VIDA}?data_inicio=&data_termino=&uo=&vinculo=')
    assert resposta.status == 200, 'a tela de Hábitos de Vida deveria responder 200 com o registro'


def _garantir_vacina_no_cartao(tela: Tela, vinculo_id: int) -> None:
    """Recria a vacina do cartão, que ``test_08`` remove ao exercitar a remoção."""
    from saude.models import CartaoVacinal, Vacina

    _aluno, prontuario = _aluno_e_prontuario()
    if CartaoVacinal.objects.filter(prontuario=prontuario, vacina__nome='Tríplice Viral').exists():
        return
    tela.ir(PRONTUARIO.format(vinculo_id)).ver_titulo('Prontuário').clicar_aba('Cartão Vacinal')
    tela.clicar_botao('Adicionar Vacina')
    expect(tela.pagina).to_have_url(re.compile(rf'{ADICIONAR_VACINA.format(prontuario.pk)}$'))
    tela.preencher('Vacina', 'Lista', 'Tríplice Viral')
    tela.clicar_botao('Adicionar').sucesso('Vacina adicionada com sucesso.')
    assert CartaoVacinal.objects.filter(prontuario=prontuario, vacina=Vacina.objects.get(nome='Tríplice Viral')).exists(), (
        'a preparação do relatório não conseguiu devolver a vacina ao cartão'
    )


@pytest.mark.parametrize(('url', 'nome'), GRAFICOS, ids=[nome for _url, nome in GRAFICOS])
def test_graficos_clinicos_renderizam_apos_o_filtro(logado_saude: Callable[[str], Page], url: str, nome: str) -> None:
    """Cada gráfico clínico responde ao filtro com a lista exportável e o container de gráficos."""
    tela = Tela(logado_saude('coordenador_sistemico'))

    tela.ir(url).ver_titulo(f'Gráficos - {nome}')
    # Sem filtro o corpo nem é montado; o submit vazio é o que liga `form.is_bound`.
    tela.clicar_botao('Enviar')
    tela.ver_botao('Exportar para XLS')
    expect(tela.loc('//div[contains(@class, "graficos-container")]').first).to_be_visible()


def test_graficos_antropometria_e_indicadores(logado_saude: Callable[[str], Page]) -> None:
    """A antropometria exporta a lista de alunos e os indicadores montam os gráficos."""
    tela = Tela(logado_saude('coordenador_sistemico'))

    tela.ir(GRAFICOS_ANTROPOMETRIA).ver_titulo('Gráficos - Antropometria')
    tela.clicar_botao('Enviar')
    tela.ver_botao('Exportar Lista dos Alunos')
    expect(tela.loc('//div[contains(@class, "graficos-container")]').first).to_be_visible()

    tela.ir(INDICADORES).ver_titulo('Indicadores')
    tela.clicar_botao('Enviar')
    expect(tela.loc('//div[contains(@class, "graficos-container")]').first).to_be_visible()


def test_estatistica_geral_por_curso(logado_saude: Callable[[str], Page]) -> None:
    """A estatística por curso monta a tabela de totais do campus selecionado."""
    tela = Tela(logado_saude('coordenador_sistemico'))

    tela.ir(ESTATISTICA_GERAL).ver_titulo('Estatísticas de Atendimentos por Curso')
    tela.preencher('Campus', 'Lista', 'CZN')
    tela.clicar_botao('Buscar')
    tela.ver_texto('Total de Alunos Ativos').ver_texto('Técnico em Informática - Saúde E2E')


def test_relatorios_de_atendimento_e_avaliacao(logado_saude: Callable[[str], Page]) -> None:
    """Os relatórios de odontologia, médico/enfermagem e avaliação respondem ao filtro."""
    tela = Tela(logado_saude('coordenador_sistemico'))

    tela.ir(RELATORIO_ODONTOLOGIA).ver_titulo('Relatório de Atendimento de Odontologia')
    tela.clicar_botao('Enviar')
    tela.ver_texto('Índices CPO-D').ver_texto('Alunos Atendidos')

    tela.ir(RELATORIO_MEDICO).ver_titulo('Relatório de Atendimento Médico/Enfermagem')
    tela.clicar_botao('Enviar')
    tela.ver_botao('Exportar Lista dos Alunos')

    tela.ir(RELATORIO_AVALIACAO).ver_titulo('Relatório - Avaliação de Saúde')
    tela.preencher('Filtrar dados', 'Lista', 'Acuidade visual')
    tela.clicar_botao('Enviar')
    tela.ver_botao('Exportar para XLS')
    expect(tela.loc('//div[contains(@class, "graficos-container")]').first).to_be_visible()


def test_relatorios_de_vacinacao(logado_saude: Callable[[str], Page]) -> None:
    """Os relatórios de vacinação listam o aluno a partir do cartão vacinal."""
    tela = Tela(logado_saude('coordenador_sistemico'))

    aluno, _prontuario = _aluno_e_prontuario()
    vinculo = aluno.get_vinculo()
    assert vinculo is not None, 'o aluno sintético não possui vínculo'
    # O botão "Adicionar Vacina" só é oferecido ao grupo médico/enfermagem, então a preparação
    # do dado é feita com o enfermeiro.
    _garantir_vacina_no_cartao(Tela(logado_saude('enfermeiro')), vinculo.pk)

    tela.ir(RELATORIO_CARTOES).ver_titulo('Relatórios de Cartões Vacinais')
    tela.preencher('Categoria', 'Lista', 'Aluno')
    tela.clicar_botao('Enviar')
    tela.ver_texto('Vacinas Cadastradas').ver_texto('Aluno Saúde')

    tela.ir(GRAFICOS_VACINAS).ver_titulo('Relatório de Vacinas dos Alunos')
    tela.preencher('Vacina', 'Lista', 'Tríplice Viral')
    tela.clicar_botao('Enviar')
    expect(tela.loc('//div[contains(@class, "graficos-container")]').first).to_be_visible()
    tela.ver_texto('Vacinas Aprazadas (Próximos 15 dias)')
