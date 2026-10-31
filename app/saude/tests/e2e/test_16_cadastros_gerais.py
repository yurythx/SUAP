"""Cadastros gerais do Saúde: amostra representativa dos ModelAdmins da feature 0003.

Os cadastros gerais são tabelas auxiliares servidas pelo admin do SUAP — 47 ModelAdmins no
módulo. Em vez de testar cada um, este arquivo cobre a **amostra que a feature
`saude/features/0003.CadastrosGerais.feature` lista**: para cada um, a listagem abre, o botão
de adicionar leva ao formulário e o formulário renderiza os campos e o botão de salvar. Um
subconjunto representativo percorre também o ciclo completo (gravar e conferir no ORM), que é
o que prova que o `ModelAdmin` não só renderiza como persiste.

Os cadastros que a feature não lista ficam dispensados — os ModelAdmins restantes são o mesmo
`ModelAdminPlus` sobre modelos de catálogo, sem lógica própria.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from uuid import uuid4

import pytest
from playwright.sync_api import Page, expect

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# (url do admin, nome do cadastro) — a lista da feature 0003, na ordem em que ela aparece.
CADASTROS = [
    ('/admin/saude/atividadegrupo/', 'Atividade em Grupo'),
    ('/admin/saude/metaacaoeducativa/', 'Meta da Ação Educativa'),
    ('/admin/saude/atividaderegistroadministrativo/', 'Atividade de Registro Administrativo'),
    ('/admin/saude/registroadministrativo/', 'Registro Administrativo'),
    ('/admin/saude/vacina/', 'Vacina'),
    ('/admin/saude/doenca/', 'Doença'),
    ('/admin/saude/droga/', 'Droga'),
    ('/admin/saude/metodocontraceptivo/', 'Método Contraceptivo'),
    ('/admin/saude/dificuldadeoral/', 'Dificuldade Oral'),
    ('/admin/saude/procedimentoenfermagem/', 'Procedimento de Enfermagem'),
    ('/admin/saude/cid/', 'CID'),
    ('/admin/saude/motivochegadapsicologia/', 'Motivo da Chegada'),
    ('/admin/saude/procedimentoodontologia/', 'Procedimento Odontológico'),
    ('/admin/saude/queixapsicologica/', 'Queixa Psicológica'),
    ('/admin/saude/tipoatividadegrupo/', 'Tipo de Atividade em Grupo'),
    ('/admin/saude/categoriaexamelaboratorial/', 'Categoria de Exame Laboratorial'),
    ('/admin/saude/tipoexamelaboratorial/', 'Tipo de Exame Laboratorial'),
    ('/admin/saude/procedimentomultidisciplinar/', 'Procedimento Multidisciplinar'),
    ('/admin/saude/anoreferenciaacaoeducativa/', 'Ano de Referência da Ação Educativa'),
    ('/admin/saude/objetivoacaoeducativa/', 'Objetivo da Ação Educativa'),
    ('/admin/saude/avaliacaogastrointestinal/', 'Avaliação Gastrointestinal'),
    ('/admin/saude/restricaoalimentar/', 'Restrição Alimentar'),
    ('/admin/saude/diagnosticonutricional/', 'Diagnóstico Nutricional'),
    ('/admin/saude/orientacaonutricional/', 'Orientação Nutricional'),
    ('/admin/saude/receitanutricional/', 'Receita Nutricional'),
    ('/admin/saude/frequenciapraticaalimentar/', 'Frequência de Prática Alimentar'),
    ('/admin/saude/perguntamarcadornutricao/', 'Pergunta de Marcador Alimentar'),
    ('/admin/saude/opcaorespostamarcadornutricao/', 'Opção de Resposta de Marcador Alimentar'),
    ('/admin/saude/motivoatendimentonutricao/', 'Motivo do Atendimento'),
]

# (url, nome, linhas do formulário, modelo, campo, valor) — o ciclo completo de uma amostra.
# A suíte não dá flush: os nomes fixos da feature viram únicos, senão a segunda execução
# encontra o registro da primeira e o formulário recusa por duplicidade.
SUFIXO = uuid4().hex[:8]
CICLOS = [
    (
        '/admin/saude/vacina/',
        'Vacina',
        [('Nome', 'Texto', f'Vacina E2E {SUFIXO}'), ('Número de Doses', 'Texto', '2')],
        'Vacina',
        'nome',
        f'Vacina E2E {SUFIXO}',
    ),
    ('/admin/saude/doenca/', 'Doença', [('Nome', 'Texto', f'Doença E2E {SUFIXO}')], 'Doenca', 'nome', f'Doença E2E {SUFIXO}'),
    ('/admin/saude/droga/', 'Droga', [('Nome', 'Texto', f'Droga E2E {SUFIXO}')], 'Droga', 'nome', f'Droga E2E {SUFIXO}'),
    (
        '/admin/saude/dificuldadeoral/',
        'Dificuldade Oral',
        [('Dificuldade Oral', 'Texto', f'Dificuldade Oral E2E {SUFIXO}')],
        'DificuldadeOral',
        'dificuldade',
        f'Dificuldade Oral E2E {SUFIXO}',
    ),
    (
        '/admin/saude/procedimentoenfermagem/',
        'Procedimento de Enfermagem',
        [('Denominação', 'Texto', f'Procedimento Enfermagem E2E {SUFIXO}')],
        'ProcedimentoEnfermagem',
        'denominacao',
        f'Procedimento Enfermagem E2E {SUFIXO}',
    ),
    (
        '/admin/saude/cid/',
        'CID',
        [('Código', 'Texto', 'Z999'), ('Denominação', 'Texto', f'CID E2E {SUFIXO}')],
        'Cid',
        'denominacao',
        f'CID E2E {SUFIXO}',
    ),
    (
        '/admin/saude/tipoatividadegrupo/',
        'Tipo de Atividade em Grupo',
        [('Descrição', 'Texto', f'Tipo de Atividade E2E {SUFIXO}')],
        'TipoAtividadeGrupo',
        'descricao',
        f'Tipo de Atividade E2E {SUFIXO}',
    ),
    (
        '/admin/saude/categoriaexamelaboratorial/',
        'Categoria de Exame Laboratorial',
        [('Nome', 'Texto', f'Categoria de Exame E2E {SUFIXO}')],
        'CategoriaExameLaboratorial',
        'nome',
        f'Categoria de Exame E2E {SUFIXO}',
    ),
    (
        '/admin/saude/queixapsicologica/',
        'Queixa Psicológica',
        [('Descrição', 'Texto', f'Queixa E2E {SUFIXO}')],
        'QueixaPsicologica',
        'descricao',
        f'Queixa E2E {SUFIXO}',
    ),
]


# A feature 0003 só edita os procedimentos odontológicos (a tabela vem do cadastro do
# Ministério), e o admin de fato não oferece o botão de adicionar.
SEM_ADICIONAR = {'/admin/saude/procedimentoodontologia/'}


@pytest.mark.parametrize(('url', 'nome'), CADASTROS, ids=[nome for _url, nome in CADASTROS])
def test_cadastro_geral_abre_listagem_e_formulario(logado_saude: Callable[[str], Page], url: str, nome: str) -> None:
    """A listagem do cadastro abre, o botão de adicionar leva ao formulário e ele renderiza."""
    tela = Tela(logado_saude('coordenador_sistemico'))

    tela.ir(url)
    # O botão do action-bar do admin é relativo (`add/`), como `get_action_bar` o monta.
    adicionar = tela.loc('//a[@href="add/"]')
    if url in SEM_ADICIONAR:
        assert adicionar.count() == 0, f'{nome} não deveria oferecer o botão de adicionar'
        return
    expect(adicionar.first).to_be_visible()
    adicionar.first.click()
    expect(tela.pagina).to_have_url(re.compile(rf'{url}add/$'))
    tela.esperar().ver_botao('Salvar')
    assert tela.rotulos_na_tela(), f'o formulário de {nome} não renderizou nenhum campo'


@pytest.mark.parametrize(('url', 'nome', 'dados', 'modelo', 'campo', 'valor'), CICLOS, ids=[nome for _url, nome, *_ in CICLOS])
def test_cadastro_geral_grava_o_registro(
    logado_saude: Callable[[str], Page], url: str, nome: str, dados: list[tuple[str, str, str]], modelo: str, campo: str, valor: str
) -> None:
    """O ciclo completo de uma amostra: preencher, salvar pela tela e conferir no ORM."""
    tela = Tela(logado_saude('coordenador_sistemico'))

    from saude import models

    tela.ir(f'{url}add/').esperar()
    tela.preencher_formulario(dados)
    tela.clicar_botao('Salvar').sucesso('Cadastro realizado com sucesso.')
    assert getattr(models, modelo).objects.filter(**{campo: valor}).exists(), f'a UI disse que cadastrou {nome}, mas o registro não persistiu'
