"""Tarefa 6 — o coordenador registra a execução do projeto: beneficiários atendidos,
execução das atividades, gastos e fotos. Executada pelo Servidor coordenador do projeto,
durante o período de execução (projeto selecionado). Como a interface das tarefas 7-10
consome os registros desta tarefa, o projeto é criado aqui por ORM (não pela tela).
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from uuid import uuid4

import pytest

from djtools.e2e_ui import Tela, anotar_tela

from .fabricas import (
    criar_edital,
    criar_equipe,
    criar_meta_atividade,
    criar_memoria_e_desembolso,
    criar_oferta,
    criar_caracterizacao,
    criar_projeto,
    criar_recurso,
)

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]


def test_registrar_execucao(logado_doc, capturar):
    """Tarefa 6 — beneficiários atendidos, execução de atividade, gasto e foto."""
    from projetos_ensino.models import (
        CaracterizacaoBeneficiario,
        Etapa,
        FotoProjeto,
        RegistroExecucaoEtapa,
        RegistroGasto,
    )

    hoje = date.today()
    suf = uuid4().hex[:8]
    edital = criar_edital(
        f'E2E Edital Exec Doc {suf}',
        inicio_inscricoes=-120,
        fim_inscricoes=-100,
        inicio_pre_selecao=-90,
        inicio_selecao=-80,
        fim_selecao=-70,
        divulgacao_selecao=-60,
    )
    criar_oferta(edital)
    criar_recurso(edital)
    projeto = criar_projeto(
        f'E2E Projeto Exec Doc {suf}',
        edital,
        pre_aprovado=True,
        aprovado=True,
        inicio_execucao=hoje - timedelta(days=40),
        fim_execucao=hoje + timedelta(days=60),
    )
    criar_equipe(projeto)
    criar_meta_atividade(projeto)
    criar_memoria_e_desembolso(projeto)
    criar_caracterizacao(projeto)
    etapa = Etapa.objects.filter(meta__projeto=projeto).first()
    desembolso = projeto.desembolso_set.first()
    caracterizacao = CaracterizacaoBeneficiario.objects.filter(projeto=projeto).first()

    tela = Tela(logado_doc('coordenador_projeto')).ir(f'/projetos_ensino/projeto/{projeto.pk}/')
    tela.ver_titulo(f'Projeto de Ensino: {projeto.titulo}')
    anotar_tela('execucao-pagina', tela)
    capturar(tela.pagina, 'execucao-pagina')

    # Etapa 1 — beneficiários atendidos (registro da quantidade efetivamente atendida)
    tela.clicar_aba('Caracterização dos Beneficiários')
    capturar(tela.pagina, 'execucao-beneficiarios')
    tela.ver_botao('Registrar')
    tela.clicar_botao('Registrar')
    popup = tela.popup()
    popup.ver_botao('Salvar')
    anotar_tela('beneficiario-atendido-popup', popup)
    popup.preencher_formulario(
        [
            ('Quantidade Atendida', 'texto', '12'),
            ('Descreva os Beneficiários do Público-Alvo', 'textarea', 'Alunos e comunidade atendidos'),
        ]
    )
    capturar(tela.pagina, 'execucao-beneficiario-atendido')
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Caracterização registrada com sucesso.')
    caracterizacao.refresh_from_db()
    assert caracterizacao.quantidade_atendida == 12, 'a UI disse que registrou, mas não persistiu'

    # Etapa 2 — execução de atividade
    tela.clicar_aba('Metas/Atividades')
    tela.ver_botao('Registrar Execução')
    tela.clicar_botao('Registrar Execução')
    popup = tela.popup()
    popup.ver_botao('Salvar')
    anotar_tela('execucao-atividade-popup', popup)
    popup.preencher_formulario(
        [
            ('Indicadores Qualitativos', 'lista', 'Atendido'),
            ('Quantidade', 'texto', '1'),
            ('Início da Execução', 'data', (hoje - timedelta(days=30)).strftime('%d/%m/%Y')),
            ('Fim da Execução', 'data', (hoje - timedelta(days=20)).strftime('%d/%m/%Y')),
            ('Descrição da Atividade Realizada', 'textarea', 'Atividade executada conforme planejado'),
            ('Arquivo', 'arquivo', 'arquivo.pdf'),
        ]
    )
    capturar(tela.pagina, 'execucao-atividade')
    popup.salvar_no_popup('Salvar')
    tela.sucesso('Execução registrada com sucesso.')
    assert RegistroExecucaoEtapa.objects.filter(etapa=etapa).exists(), 'a UI disse que registrou, mas não persistiu'

    # Etapa 3 — gastos do desembolso
    tela.clicar_aba('Plano de Desembolso')
    tela.ver_botao('Gerenciar Gasto')
    tela.clicar_botao('Gerenciar Gasto')
    tela.ver_titulo('Gastos Registrados')
    anotar_tela('execucao-gasto-form', tela)
    tela.preencher_formulario(
        [
            ('Ano', 'lista', str(hoje.year)),
            ('Mês', 'lista', '1'),
            ('Descrição', 'textarea', 'Exercício financeiro do mês'),
            ('Quantidade', 'texto', '1'),
            ('Valor Unitário (R$)', 'texto', '200,00'),
            ('Observação', 'textarea', 'Gasto executado no período'),
        ]
    )
    capturar(tela.pagina, 'execucao-gasto')
    tela.clicar_botao('Salvar')
    tela.sucesso('Gasto registrado com sucesso.')
    assert RegistroGasto.objects.filter(desembolso=desembolso).exists(), 'a UI disse que registrou o gasto, mas não persistiu'

    # Etapa 4 — fotos (o link "Adicionar Foto" navega para uma página de formulário, não popup)
    tela.ir(f'/projetos_ensino/projeto/{projeto.pk}/?tab=fotos')
    tela.ver_botao('Adicionar Foto')
    tela.clicar_botao('Adicionar Foto')
    anotar_tela('foto-form', tela)
    tela.preencher_formulario([('Legenda', 'textarea', 'Registro fotográfico da atividade'), ('Imagem', 'arquivo', 'foto_projeto.png')])
    capturar(tela.pagina, 'execucao-foto')
    tela.clicar_botao('Salvar')
    tela.sucesso('Foto adicionada com sucesso.')
    assert FotoProjeto.objects.filter(projeto=projeto).exists(), 'a UI disse que salvou a foto, mas não persistiu'
