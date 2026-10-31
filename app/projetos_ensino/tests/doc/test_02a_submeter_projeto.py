"""Tarefa 2 (etapas 1-4) — a coordenadora cadastra o projeto, monta a equipe, caracteriza
os beneficiários e registra metas e atividades, tudo pela tela.

O teste irmão ``test_02b`` (etapas 5-6: plano de aplicação/desembolso e envio) continua a
partir do projeto criado aqui via ``estado``.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from uuid import uuid4

import pytest

from djtools.e2e_ui import Tela, anotar_tela

from . import estado
from .fabricas import criar_edital, criar_oferta, criar_recurso

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

EDITAIS_ABERTOS = '/projetos_ensino/editais_abertos/'
CAMPOS = estado.CAMPOS


def _cartao_do_edital(tela: Tela, titulo: str) -> Tela:
    """Recorte do ``div.general-box`` do edital (a listagem de editais não é tabela)."""
    escopo = f'//div[contains(@class, "general-box")][.//h4[contains(normalize-space(.), "{titulo}")]]'
    recorte = Tela(tela.pagina, tela.pagina, escopo)
    from playwright.sync_api import expect

    expect(recorte.loc('').first).to_be_visible()
    return recorte


def participacoes_ativas(projeto) -> int:
    """Nº de participações ativas do projeto (da coordenadora + membro + aluno)."""
    from projetos_ensino.models import Participacao

    return Participacao.objects.filter(projeto=projeto, ativo=True).count()


def test_submeter_projeto_partes_1_a_4(logado_doc, capturar):
    """Tarefa 2, etapas 1 a 4 — cadastro, equipe, beneficiários e metas/atividades."""
    estado.novo()  # zera o estado compartilhado antes de popular (idempotente sob --reruns)
    from projetos_ensino.models import CaracterizacaoBeneficiario, Etapa, Meta, Participacao, Projeto

    hoje = date.today()
    suf = uuid4().hex[:8]
    edital = criar_edital(f'E2E Edital Sub Doc {suf}', inicio_inscricoes=-1, fim_inscricoes=5)
    criar_oferta(edital)
    criar_recurso(edital)
    titulo = f'E2E Projeto Doc {suf}'

    tela = Tela(logado_doc('coordenador_projeto')).ir(EDITAIS_ABERTOS)
    tela.ver_titulo('Editais de Ensino e de Fluxo Contínuo com Inscrições Abertas')
    capturar(tela.pagina, 'projeto-editais-abertos')
    _cartao_do_edital(tela, edital.titulo).clicar_botao('Adicionar projeto')

    # Etapa 1 — cadastrar o projeto
    tela.ver_titulo('Adicionar projeto')
    anotar_tela('projeto-form', tela)
    tela.preencher_formulario(
        [
            ('Campus', 'lista', 'CZN'),
            ('Setor', 'lista', 'DIAC/CZN'),
            ('Título do projeto', 'texto', titulo),
            ('Carga Horária Semanal do Coordenador', 'texto', '6'),
            ('Início da Execução', 'data', (hoje + timedelta(days=15)).strftime('%d/%m/%Y')),
            ('Término da Execução', 'data', (hoje + timedelta(days=150)).strftime('%d/%m/%Y')),
            ('Carga horária total para desenvolvimento do projeto', 'texto', '400'),
            ('Eixo Temático', 'autocomplete', 'Educação'),
            ('Há parceiros externos', 'checkbox', 'marcar'),
            ('Parceiros Externos', 'texto', 'Instituição parceira'),
            ('Resumo', 'texto rico', 'Resumo do projeto'),
            ('Introdução', 'texto rico', 'Introdução do projeto'),
            ('Justificativa e Relevância', 'texto rico', 'Justificativa do projeto'),
            ('Objetivo Geral', 'texto rico', 'Objetivo geral do projeto'),
            ('Metodologia da execução do projeto', 'texto rico', 'Metodologia do projeto'),
            ('Acompanhamento e avaliação do projeto durante a execução', 'texto rico', 'Acompanhamento do projeto'),
            ('Resultados Esperados e Disseminação dos Resultados', 'texto rico', 'Resultados esperados'),
            ('Referências', 'texto rico', 'Referências do projeto'),
        ]
    )
    capturar(tela.pagina, 'projeto-formulario')
    tela.clicar_botao('Salvar')

    tela.sucesso('Projeto cadastrado com sucesso.')
    projeto = Projeto.objects.filter(titulo=titulo).first()
    assert projeto is not None, 'a UI disse que salvou, mas não persistiu'
    CAMPOS['projeto_id'] = projeto.pk
    tela.ver_titulo(f'Projeto de Ensino: {titulo}')
    anotar_tela('projeto-pagina', tela)
    capturar(tela.pagina, 'projeto-pagina')

    # Etapa 2 — montar a equipe
    tela.clicar_aba('Equipe')
    tela.ver_botao('Adicionar Servidor')
    tela.clicar_botao('Adicionar Servidor')
    popup = tela.popup()
    popup.ver_botao('Salvar')
    anotar_tela('participante-servidor-popup', popup)
    popup.preencher_formulario(
        [
            ('Bolsista', 'lista', 'Não'),
            ('Carga Horária', 'texto', '6'),
            ('Participante', 'autocomplete', 'Membro Equipe Doc'),
            ('Data de Entrada', 'data', hoje.strftime('%d/%m/%Y')),
        ]
    )
    capturar(tela.pagina, 'projeto-equipe-servidor')
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Participante adicionado com sucesso.')
    # Contagem por matrícula (não por nome): o autocomplete pode escolher outro "Membro Equipe
    # Doc" se houver homônimo — a asserção anterior (soma de duas queries) aceitava que só
    # UMA casasse. Filtrar pela matrícula única do seed é o que prova que o membro certo entrou.
    assert Participacao.objects.filter(projeto=projeto, vinculo_pessoa__user__username='158004', ativo=True).count() == 1, (
        'a UI disse que adicionou o servidor, mas não persistiu (ou entrou membro errado)'
    )

    tela.clicar_botao('Adicionar Aluno')
    popup = tela.popup()
    popup.ver_botao('Salvar')
    popup.preencher_formulario(
        [
            ('Bolsista', 'lista', 'Não'),
            ('Carga Horária', 'texto', '6'),
            ('Participante', 'autocomplete', 'Aluno Proj Doc'),
            ('Data de Entrada', 'data', hoje.strftime('%d/%m/%Y')),
        ]
    )
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Participante adicionado com sucesso.')
    assert participacoes_ativas(projeto) >= 2, 'a UI disse que adicionou o aluno, mas não persistiu'

    # Etapa 3 — caracterizar os beneficiários
    tela.clicar_aba('Caracterização dos Beneficiários')
    tela.ver_botao('Adicionar Caracterização dos Beneficiários')
    tela.clicar_botao('Adicionar Caracterização dos Beneficiários')
    popup = tela.popup()
    popup.ver_botao('Salvar')
    anotar_tela('caracterizacao-popup', popup)
    popup.preencher_formulario(
        [
            ('Tipo de beneficiário', 'autocomplete', 'Movimentos Sociais'),
            ('Quantidade Prevista de Pessoas a Atender', 'texto', '12'),
        ]
    )
    capturar(tela.pagina, 'projeto-beneficiarios')
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Caracterização do beneficiário adicionada com sucesso.')
    assert CaracterizacaoBeneficiario.objects.filter(projeto=projeto).exists()

    # Etapa 4 — metas e atividades
    tela.clicar_aba('Metas/Atividades')
    tela.ver_botao('Adicionar Meta')
    tela.clicar_botao('Adicionar Meta')
    popup = tela.popup()
    popup.ver_botao('Salvar')
    popup.preencher_formulario([('Ordem', 'texto', '1'), ('Descrição', 'textarea', 'Meta 1 do projeto')])
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Meta adicionada com sucesso.')
    meta = Meta.objects.filter(projeto=projeto).first()
    assert meta is not None

    tela.ver_botao('Adicionar Atividade')
    tela.clicar_botao('Adicionar Atividade')
    popup = tela.popup()
    popup.ver_botao('Salvar')
    anotar_tela('atividade-popup', popup)
    popup.preencher_formulario(
        [
            ('Ordem', 'texto', '1'),
            ('Descrição', 'textarea', 'Atividade 1 da meta'),
            ('Indicador Quantitativo', 'texto', 'Unidade'),
            ('Quantidade', 'texto', '4'),
            ('Indicador(es) Qualitativo(s)', 'textarea', 'Execução verificada'),
            ('Responsável', 'lista', 'Membro Equipe Doc'),
            ('Início da Execução', 'data', (hoje + timedelta(days=20)).strftime('%d/%m/%Y')),
            ('Fim da Execução', 'data', (hoje + timedelta(days=30)).strftime('%d/%m/%Y')),
        ]
    )
    capturar(tela.pagina, 'projeto-atividade')
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Atividade adicionada com sucesso.')
    assert Etapa.objects.filter(meta=meta).exists()
