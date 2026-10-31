"""Roteiro navegado das tarefas do ``pnp`` — a fonte de ``pnp/docs/usuario.md``.

Um teste por tarefa da doc, na ordem em que a doc a apresenta. As asserções são as mesmas
dos e2e (botão, título, mensagem de sucesso) e existem para a rodada falhar alto quando a
tela mudou de forma: doc que descreve um passo que não existe mais é pior que doc velha.

Marcado ``e2e`` além de ``doc`` de propósito — o ``-m "not e2e"`` do ``suap_check`` precisa
excluir esta suíte, que exige o banco ``*_e2e`` e um browser.

O módulo não tem ``features/``: as tarefas foram propostas a partir do menu e das telas de
importação do admin, e os estados de domínio vêm do ``doc_seed`` no conftest.
"""

from __future__ import annotations

import pytest

from djtools.e2e_fixtures import escolher_autocomplete, mensagem_de_sucesso
from djtools.e2e_ui import Tela, anotar_tela

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

ESTRUTURAS = '/admin/pnp/estruturapnp/'
AREAS = '/admin/pnp/areatematicapnp/'
EIXOS = '/admin/pnp/eixopnp/'
SERVIDORES = '/admin/pnp/servidorpnp/'
MATRICULAS = '/admin/pnp/matriculapnp/'


def _parquet(destino, nome: str, colunas: tuple[str, ...], linhas: list[tuple[str, ...]]) -> str:
    """Grava um ``.parquet`` mínimo com as colunas que o formulário espera."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    schema = pa.schema([(coluna, pa.string()) for coluna in colunas])
    tabela = pa.Table.from_pylist([dict(zip(colunas, linha, strict=True)) for linha in linhas], schema=schema)
    caminho = destino / f'{nome}.parquet'
    pq.write_table(tabela, caminho)
    return str(caminho)


def _importar(tela: Tela, botao: str, arquivo: str, capturar=None, slug: str = '') -> Tela:
    """Abre a tela de importação pelo botão da listagem, envia o arquivo e confirma."""
    tela.clicar_botao(botao)
    tela.ver_texto(botao)
    tela.ver_texto('Arquivo .parquet exportado da PNP')
    if capturar:
        capturar(tela.pagina, slug)
    tela.preencher('Arquivo Parquet', 'arquivo real', arquivo)
    tela.clicar_botao('Importar')
    return tela


def test_01_importar_tabelas_de_referencia(logado_doc, doc_seed, capturar, tmp_path):
    """Tarefa 1 — importar estruturas, áreas temáticas e eixos da PNP."""
    from pnp.models import AreaTematicaPNP, EixoPNP, EstruturaPNP

    pagina = logado_doc()
    tela = Tela(pagina).ir(ESTRUTURAS)
    tela.ver_botao('Adicionar Estrutura PNP')
    tela.ver_botao('Importar Estruturas')
    tela.ver_botao('Exportar para XLS')
    anotar_tela('estruturas-listagem', tela)
    capturar(pagina, 'estruturas-listagem')

    arquivo = _parquet(
        tmp_path,
        'estruturas',
        ('codigo', 'nome'),
        [
            ('PNP1-EST-NOVO', doc_seed['unidade'].nome),
            ('PNP1-EST-SEM', 'Unidade Que Não Existe'),
        ],
    )
    tela = _importar(tela, 'Importar Estruturas', arquivo, capturar, 'estruturas-importar')
    tela.ver_texto('estrutura(s) cadastrada(s)')
    tela.ver_texto('Unidade Que Não Existe')
    capturar(pagina, 'estruturas-resultado')

    assert EstruturaPNP.objects.get(codigo='PNP1-EST-NOVO').uo == doc_seed['unidade'].uo
    assert EstruturaPNP.objects.get(codigo='PNP1-EST-SEM').uo_id is None

    tela = Tela(pagina).ir(AREAS)
    tela.ver_botao('Importar Áreas Temáticas')
    arquivo = _parquet(
        tmp_path,
        'areas',
        ('codigo', 'nome'),
        [('1.03.00.00-7', 'Física'), ('9.99.99.99-9', 'Área Inexistente')],
    )
    tela = _importar(tela, 'Importar Áreas Temáticas', arquivo)
    tela.ver_texto('área(s) temática(s) cadastrada(s)')
    capturar(pagina, 'areas-resultado')
    assert AreaTematicaPNP.objects.get(codigo='1.03.00.00-7').area is not None
    assert AreaTematicaPNP.objects.get(codigo='9.99.99.99-9').area_id is None

    tela = Tela(pagina).ir(EIXOS)
    tela.ver_botao('Importar Eixos')
    arquivo = _parquet(
        tmp_path,
        'eixos',
        ('codigo', 'nome'),
        [('19', 'Informação e Comunicação'), ('1901', 'Subeixo Sem Eixo')],
    )
    tela = _importar(tela, 'Importar Eixos', arquivo)
    tela.ver_texto('eixo(s) cadastrado(s)')
    capturar(pagina, 'eixos-resultado')
    assert EixoPNP.objects.get(codigo='19').eixo_tecnologico is not None
    assert EixoPNP.objects.get(codigo='1901').eixo_tecnologico_id is None


def test_02_importar_servidores(logado_doc, doc_seed, capturar, tmp_path):
    """Tarefa 2 — importar os servidores da PNP e vinculá-los à matrícula SIAPE."""
    from pnp.models import ServidorPNP

    pagina = logado_doc()
    tela = Tela(pagina).ir(SERVIDORES)
    tela.ver_botao('Importar Servidores')
    capturar(pagina, 'servidores-listagem')
    tela.clicar_aba('Sem servidor')
    tela.ver_texto('Servidor Sem Vínculo')
    capturar(pagina, 'servidores-pendentes')
    Tela(pagina).ir(SERVIDORES)

    arquivo = _parquet(
        tmp_path,
        'servidores',
        ('matricula', 'nome', 'cpf', 'unidade', 'codigo_estrutura'),
        [
            ('0900002', 'Servidor PNP Importado', '111.222.333-44', doc_seed['unidade'].nome, 'PNP1-EST'),
            ('0999999', 'Servidor Inexistente', '555.666.777-88', doc_seed['unidade'].nome, 'PNP1-EST'),
        ],
    )
    tela = _importar(Tela(pagina).ir(SERVIDORES), 'Importar Servidores', arquivo, capturar, 'servidores-importar')
    tela.ver_texto('servidor(es) cadastrado(s)')
    tela.ver_texto('Servidor Inexistente')
    capturar(pagina, 'servidores-resultado')

    importado = ServidorPNP.objects.get(matricula='900002')
    assert importado.servidor == doc_seed['servidor']
    assert importado.estrutura.codigo == 'PNP1-EST'
    assert ServidorPNP.objects.get(matricula='999999').servidor_id is None


def test_03_importar_matriculas(logado_doc, doc_seed, capturar, tmp_path):
    """Tarefa 3 — importar as matrículas da PNP e vinculá-las ao aluno do SUAP."""
    from pnp.models import MatriculaPNP

    pagina = logado_doc()
    tela = Tela(pagina).ir(MATRICULAS)
    tela.ver_botao('Importar Matrículas')
    capturar(pagina, 'matriculas-listagem')
    tela.clicar_aba('Sem aluno')
    tela.ver_texto('Aluno Sem Vínculo')
    capturar(pagina, 'matriculas-pendentes')

    arquivo = _parquet(
        tmp_path,
        'matriculas',
        ('matricula', 'cpf', 'nome', 'curso', 'unidade', 'codigo_estrutura'),
        [
            (
                'PNPMAT2501',
                doc_seed['aluno'].pessoa_fisica.cpf,
                'Aluno PNP Doc',
                'Técnico em Informática',
                doc_seed['unidade'].nome,
                'PNP1-EST',
            ),
            ('PNPMAT2502', '000.000.000-00', 'Aluno Inexistente', 'Técnico em Informática', doc_seed['unidade'].nome, 'PNP1-EST'),
        ],
    )
    tela = _importar(Tela(pagina).ir(MATRICULAS), 'Importar Matrículas', arquivo, capturar, 'matriculas-importar')
    tela.ver_texto('matrícula(s) importada(s)')
    tela.ver_texto('Aluno Inexistente')
    capturar(pagina, 'matriculas-resultado')

    assert MatriculaPNP.objects.get(matricula='PNPMAT2501').aluno == doc_seed['aluno']
    assert MatriculaPNP.objects.get(matricula='PNPMAT2502').aluno_id is None


def test_04_revisar_e_corrigir_vinculos(logado_doc, doc_seed, capturar):
    """Tarefa 4 — revisar as abas de pendências e informar o vínculo manualmente."""
    from pnp.models import EstruturaPNP, MatriculaPNP, ServidorPNP

    # Reabre as pendências: com --reuse-db uma rodada anterior já as corrigiu.
    EstruturaPNP.objects.filter(codigo='PNP1-SEM-UO').update(uo=None)
    ServidorPNP.objects.filter(matricula='PNPSRV1').update(servidor=None)
    MatriculaPNP.objects.filter(matricula='PNPMAT1').update(aluno=None)

    pagina = logado_doc()
    tela = Tela(pagina).ir(ESTRUTURAS)
    tela.clicar_aba('Sem unidade organizacional')
    tela.clicar_link('PNP1-SEM-UO')
    tela.ver_texto('Unidade Não Identificada')
    anotar_tela('estrutura-vinculo', tela)
    capturar(pagina, 'estrutura-vinculo')
    escolher_autocomplete(pagina, 'uo', doc_seed['unidade_pendente'].sigla)
    tela.clicar_botao('Salvar')
    mensagem_de_sucesso(pagina, 'sucesso')
    assert EstruturaPNP.objects.get(codigo='PNP1-SEM-UO').uo == doc_seed['unidade_pendente'].uo

    tela = Tela(pagina).ir(SERVIDORES)
    tela.clicar_aba('Sem servidor')
    tela.clicar_link('PNPSRV1')
    tela.ver_texto('Servidor Sem Vínculo')
    anotar_tela('servidor-editar', tela)
    capturar(pagina, 'servidor-editar')
    escolher_autocomplete(pagina, 'servidor', 'Servidor PNP Livre')
    capturar(pagina, 'servidor-vinculando')
    tela.clicar_botao('Salvar')
    mensagem_de_sucesso(pagina, 'sucesso')
    assert ServidorPNP.objects.get(matricula='PNPSRV1').servidor == doc_seed['servidor_livre']

    tela = Tela(pagina).ir(MATRICULAS)
    tela.clicar_aba('Sem aluno')
    tela.clicar_link('PNPMAT1')
    tela.ver_texto('Aluno Sem Vínculo')
    anotar_tela('matricula-vinculo', tela)
    capturar(pagina, 'matricula-vinculo')
    escolher_autocomplete(pagina, 'aluno', '2026002')
    tela.clicar_botao('Salvar')
    mensagem_de_sucesso(pagina, 'sucesso')
    assert MatriculaPNP.objects.get(matricula='PNPMAT1').aluno == doc_seed['aluno_livre']
