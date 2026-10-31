"""Tarefas 11 a 13 — a área do aluno.

O outro lado de tudo que a secretaria e o professor lançaram: acompanhar a vida acadêmica,
emitir declaração e informar dado próprio (atividade complementar, dado bancário, cadastro).
É o único ponto do módulo que roda com vínculo de **aluno**, com menu e permissões
diferentes dos servidores.
"""

from __future__ import annotations

import pytest

from djtools.e2e_ui import Tela
from edu.tests.doc.conftest import anotar

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

DATA = '22/07/2019'
MATRICULA_ALUNO = '20191101010001'
SENHA_ALUNO = '123'


@pytest.fixture
def aluno(seed_matricula_renovada):
    """Aluno com 2019.1 fechado e 2019.2 renovado — o histórico já tem o que mostrar."""
    from edu.models import Aluno

    return Aluno.objects.get(matricula=MATRICULA_ALUNO)


def test_acompanhar_a_vida_academica(logado_edu, aluno, capturar):
    """Tarefa 11 — tela inicial, dados acadêmicos, histórico, requisitos e disciplinas."""
    page = logado_edu(MATRICULA_ALUNO, senha=SENHA_ALUNO)
    tela = Tela(page).ir('/')
    anotar('aluno-inicio', tela)
    capturar(page, 'aluno-inicio')
    tela.ver_texto('Minhas disciplinas')

    tela.ir('/edu/meus_dados_academicos/')
    anotar('aluno-dados-academicos', tela)
    capturar(page, 'aluno-dados-academicos')
    tela.ver_titulo(aluno.pessoa_fisica.nome)

    # Abas pelo nome que o aluno lê, e não pelo `?tab=`: é assim que a doc as descreve.
    for aba, texto, slug in [
        ('Dados acadêmicos', 'Matrículas em períodos', 'aluno-periodos'),
        ('Histórico', 'Componentes Curriculares', 'aluno-historico'),
        ('Requisitos de conclusão', 'Requisitos', 'aluno-requisitos'),
    ]:
        tela.ir(f'/edu/aluno/{aluno.matricula}/')
        tela.clicar_aba(aba)
        tela.esperar()
        tela.ver_texto(texto)
        capturar(page, slug)

    tela.ir('/edu/disciplinas/')
    anotar('aluno-disciplinas', tela)
    # O filtro desta tela não tem botão: o `select` submete sozinho no `change`.
    tela.preencher('Período', 'lista', '2019.2')
    tela.esperar()
    capturar(page, 'aluno-disciplinas')


def test_emitir_declaracoes(logado_edu, aluno, capturar):
    """Tarefa 12 — declarações e comprovantes saem do menu Documentos da área do aluno."""
    tela = Tela(logado_edu(MATRICULA_ALUNO, senha=SENHA_ALUNO)).ir('/edu/meus_dados_academicos/')
    tela.clicar_botao('Documentos')
    tela.esperar()
    anotar('aluno-documentos', tela)
    capturar(tela.pagina, 'aluno-documentos')

    tela.ver_texto('Histórico Parcial')
    tela.ver_texto('Comprovante de Dados Acadêmicos')


@pytest.fixture
def tipo_de_atividade_complementar(aluno):
    """Tipo ofertado à matriz do aluno — a tela só lista o que a configuração de AACC contempla."""
    from edu.models import ConfiguracaoAtividadeComplementar, ItemConfiguracaoAtividadeComplementar, Matriz, TipoAtividadeComplementar

    tipo = TipoAtividadeComplementar.objects.get_or_create(descricao='Atividade Complementar DOC')[0]
    tipo.modalidades.add(aluno.curso_campus.modalidade)
    configuracao = ConfiguracaoAtividadeComplementar.objects.get_or_create(descricao='Configuração AACC DOC')[0]
    ItemConfiguracaoAtividadeComplementar.objects.get_or_create(configuracao=configuracao, tipo=tipo, defaults={'fator_conversao': 1})
    Matriz.objects.filter(pk=aluno.matriz_id).update(configuracao_atividade_academica=configuracao)
    return tipo


def test_informar_atividade_complementar(logado_edu, aluno, tipo_de_atividade_complementar, capturar):
    """Tarefa 13 — o que o aluno declara entra como solicitação, não como fato consumado."""
    from edu.models import AtividadeComplementar

    atividades = AtividadeComplementar.objects.filter(aluno=aluno, descricao='Atividade declarada')
    try:
        tela = Tela(logado_edu(MATRICULA_ALUNO, senha=SENHA_ALUNO)).ir('/edu/solicitar_atividade_complementar/')
        anotar('aluno-atividade-complementar', tela)
        tela.preencher_formulario(
            [
                ('Ano Letivo', 'lista', '2019'),
                ('Período Letivo', 'lista', '1'),
                ('Tipo', 'lista', tipo_de_atividade_complementar.descricao),
                ('Atividade', 'texto', 'Atividade declarada'),
                ('Data de Início da Atividade', 'data', '01/01/2019'),
                ('Data da Conclusão da Atividade', 'data', '01/01/2019'),
                ('Carga Horária', 'texto', '10'),
                ('Anexo', 'arquivo', 'arquivo.pdf'),
            ]
        )
        capturar(tela.pagina, 'aluno-atividade-complementar')
        tela.clicar_botao('Salvar')

        tela.sucesso('Atividade complementar adicionada com sucesso.')
        assert atividades.exists(), 'a UI disse que salvou, mas a atividade não persistiu'
        capturar(tela.pagina, 'aluno-atividade-resultado')
    finally:
        atividades.delete()


def test_atualizar_dados_pessoais(logado_edu, aluno, capturar):
    """Tarefa 13, segunda metade — o aluno mantém o próprio cadastro."""
    tela = Tela(logado_edu(MATRICULA_ALUNO, senha=SENHA_ALUNO)).ir(f'/edu/atualizar_meus_dados_pessoais/{aluno.matricula}/')
    anotar('aluno-dados-pessoais', tela)
    tela.preencher('Utiliza Transporte Escolar Público', 'lista', 'Não')
    capturar(tela.pagina, 'aluno-dados-pessoais')
    tela.clicar_botao('Enviar')

    tela.sucesso('Dados Pessoais atualizados com sucesso.')
    aluno.refresh_from_db()
    assert not aluno.poder_publico_responsavel_transporte, 'a resposta "Não" deveria desligar o transporte escolar'


@pytest.fixture
def banco_cadastrado(aluno):
    """Um banco na base — sem ele o autocomplete de instituição do dado bancário é vazio."""
    from rh.models import Banco

    return Banco.objects.get_or_create(codigo='001', sigla='BB', defaults={'nome': 'Banco do Brasil'})[0]


def test_informar_dados_bancarios(logado_edu, aluno, banco_cadastrado, capturar):
    """Tarefa 13, terceira parte — o dado que a assistência estudantil usa para pagar auxílio."""
    from ae.models import DadosBancarios

    dados = DadosBancarios.objects.filter(aluno=aluno, numero_conta='12345')
    try:
        tela = Tela(logado_edu(MATRICULA_ALUNO, senha=SENHA_ALUNO)).ir(f'/ae/adicionar_dado_bancario/{aluno.pk}/')
        anotar('aluno-dado-bancario-autenticacao', tela)
        capturar(tela.pagina, 'aluno-dado-bancario-autenticacao')
        # Dado bancário é sensível: a tela pede um código antes de liberar o formulário.
        tela.preencher('Código', 'texto', '123456')
        tela.clicar_botao('Autenticar')
        anotar('aluno-dado-bancario', tela)
        tela.preencher('Banco', 'autocomplete', banco_cadastrado.nome)
        tela.preencher('Número da Agência', 'texto', '123456')
        tela.preencher('Tipo da Conta', 'lista', 'Conta Corrente')
        tela.preencher('Número da Conta', 'texto', '12345')
        capturar(tela.pagina, 'aluno-dado-bancario')
        tela.clicar_botao('Salvar')

        tela.sucesso('Dados bancários adicionado com sucesso.')
        assert dados.exists(), 'a UI disse que salvou, mas o dado bancário não persistiu'
    finally:
        dados.delete()
