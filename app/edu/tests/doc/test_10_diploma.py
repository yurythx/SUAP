"""Tarefa 14 — formar o aluno: TCC, infraestrutura de emissão e diploma.

A emissão do diploma em si exige aluno com **todos** os requisitos cumpridos (inclusive
colação de grau) — a ``.feature`` 010 do behave deixou esses passos comentados por isso, e
esta rodada também não os executa. O que ela cobre é o que existe: o registro do TCC, os
dois cadastros que habilitam a impressão (modelo de documento e livro de registros) e a
tela de emissão respondendo para o Coordenador de Registros Acadêmicos.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from djtools.e2e_ui import Tela
from edu.tests.doc.conftest import anotar, desfocar

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

DATA = '22/07/2019'
MATRICULA_ALUNO = '20191101010001'


@pytest.fixture
def sufixo():
    return uuid4().hex[:6].upper()


@pytest.fixture
def aluno_renovado(seed_matricula_renovada):
    from edu.models import Aluno

    return Aluno.objects.get(matricula=MATRICULA_ALUNO)


def test_cadastrar_tcc(logado_edu, aluno_renovado, capturar):
    """Etapa 1 — o TCC com banca e orientação; sem ele a matriz que o exige não integraliza."""
    from edu.models import ProjetoFinal

    projetos = ProjetoFinal.objects.filter(matricula_periodo__aluno=aluno_renovado, titulo='Trabalho de conclusão')
    try:
        tela = Tela(logado_edu('secretario')).ir(f'/edu/aluno/{aluno_renovado.matricula}/')
        anotar('aluno-ficha-secretaria', tela)
        capturar(tela.pagina, 'aluno-ficha-secretaria')

        tela.ir(f'/edu/adicionar_projeto_final/{aluno_renovado.pk}/')
        anotar('tcc-formulario', tela)
        tela.preencher_formulario(
            [
                ('Ano Letivo', 'lista', '2019'),
                ('Período Letivo', 'lista', '2'),
                ('Título do Trabalho', 'texto', 'Trabalho de conclusão'),
                ('Resumo do Trabalho', 'textarea', 'Resumo do trabalho de conclusão.'),
                ('Tipo de Trabalho', 'lista', 'Monografia'),
                ('Defesa Online', 'checkbox', 'marcar'),
            ]
        )
        desfocar(tela.pagina)
        tela.preencher_formulario(
            [
                ('Orientador', 'autocomplete', '100007'),
                # Presidente vem de `Professor.objects` (busca por nome); Orientador, de
                # `Vinculo.objects` (aceita matrícula).
                ('Presidente', 'autocomplete', 'Servidor P'),
            ]
        )
        capturar(tela.pagina, 'tcc-formulario')
        tela.clicar_botao('Salvar')

        tela.sucesso('TCC / Relatório adicionado com sucesso.')
        assert projetos.exists(), 'a UI disse que salvou, mas o TCC não persistiu'
    finally:
        projetos.delete()


def test_preparar_a_emissao_de_documentos(logado_edu, sufixo, capturar):
    """Etapa 2 — modelo de documento (o .docx com as marcações) e livro de registros."""
    from edu.models import ConfiguracaoLivro, ModeloDocumento

    descricao_modelo = f'Diploma DOC {sufixo}'
    descricao_livro = f'Livro DOC {sufixo}'
    modelos = ModeloDocumento.objects.filter(descricao=descricao_modelo)
    livros = ConfiguracaoLivro.objects.filter(descricao=descricao_livro)
    try:
        tela = Tela(logado_edu('admin_academico')).ir('/admin/edu/modelodocumento/')
        anotar('modelo-listagem', tela)
        tela.clicar_botao('Adicionar Modelo de Documento')
        anotar('modelo-formulario', tela)
        # Autocomplete depois do `desfocar`: a digitação do select2 vaza para o campo focado
        # antes quando o widget demora a abrir (ver `escolher`, no conftest) — aqui o campo
        # anterior seria a Descrição, que é a identidade da asserção.
        tela.preencher_formulario(
            [
                ('Descrição', 'texto', descricao_modelo),
                ('Tipo', 'lista', 'DIPLOMA/CERTIFICADO'),
                ('Template', 'arquivo', 'arquivo.docx'),
            ]
        )
        desfocar(tela.pagina)
        tela.preencher('Modalidade de Ensino', 'autocomplete', 'Especialização')
        capturar(tela.pagina, 'modelo-formulario')
        tela.clicar_botao('Salvar')
        tela.sucesso('Cadastro realizado com sucesso.')
        assert modelos.exists(), 'a UI disse que salvou, mas o modelo não persistiu'

        tela.ir('/admin/edu/configuracaolivro/add/')
        anotar('livro-formulario', tela)
        tela.preencher_formulario(
            [
                ('Descrição', 'texto', descricao_livro),
                ('Nº do Livro Atual', 'texto', '1'),
                ('Folhas por Livro', 'texto', '200'),
                ('Nº da Folha Atual', 'texto', '1'),
                ('Nº do Registro Atual', 'texto', '1'),
            ]
        )
        desfocar(tela.pagina)
        tela.preencher_formulario(
            [
                ('Campus', 'autocomplete', 'CEN'),
                ('Modalidades de Ensino', 'autocomplete multiplo', 'Especialização'),
            ]
        )
        capturar(tela.pagina, 'livro-formulario')
        tela.clicar_botao('Salvar')
        tela.sucesso('Cadastro realizado com sucesso.')
        livro = livros.get()
        assert livro.modalidades.exists(), 'livro sem modalidade não serve para emitir nada'
    finally:
        modelos.delete()
        livros.delete()


def test_emitir_diploma(logado_edu, aluno_renovado, capturar):
    """Etapa 3 — a tela de emissão, como o Coordenador de Registros Acadêmicos a encontra.

    Só até aqui: a emissão exige aluno com todos os requisitos cumpridos, que este seed não
    tem (é a mesma pendência que a ``.feature`` 010 registra com os passos comentados).
    """
    tela = Tela(logado_edu('registros_academicos'))
    resposta = tela.pagina.goto('/edu/emitir_diploma/')
    assert resposta.status == 200, 'o coordenador de registros acadêmicos não alcançou a emissão de diploma'
    tela.esperar()
    anotar('diploma-emitir', tela)
    capturar(tela.pagina, 'diploma-emitir')

    resposta = tela.pagina.goto('/admin/edu/registroemissaodiploma/')
    assert resposta.status == 200, 'a listagem de registros de emissão não abriu'
    tela.esperar()
    anotar('diploma-registros', tela)
    capturar(tela.pagina, 'diploma-registros')

    # A fronteira que a doc afirma: quem não emite diploma não passa daqui.
    assert logado_edu('professor').goto('/edu/emitir_diploma/').status == 403, 'a emissão de diploma abriu para quem não emite diploma'
