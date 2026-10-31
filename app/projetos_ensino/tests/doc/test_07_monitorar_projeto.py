"""Tarefa 7 — o monitor do projeto valida as atividades executadas e os gastos registrados
pelo coordenador (tarefa 6). Executada pelo Monitor/Coordenador de Projetos de Ensino.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from uuid import uuid4

import pytest

from djtools.e2e_ui import Tela, anotar_tela

from .fabricas import (
    criar_caracterizacao,
    criar_edital,
    criar_equipe,
    criar_memoria_e_desembolso,
    criar_meta_atividade,
    criar_oferta,
    criar_projeto,
    criar_recurso,
    criar_registro_execucao,
    criar_registro_gasto,
)

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

MONITORAMENTO = '/projetos_ensino/projetos_em_execucao/'


def test_monitorar_projeto(logado_doc, capturar):
    """Tarefa 7 — validar a atividade executada e o gasto do projeto em execução."""
    from comum.models import Vinculo
    from projetos_ensino.models import RegistroExecucaoEtapa, RegistroGasto

    hoje = date.today()
    suf = uuid4().hex[:8]
    monitor = Vinculo.objects.get(user__username='158002')
    edital = criar_edital(
        f'E2E Edital Mon Doc {suf}',
        inicio_inscricoes=-130,
        fim_inscricoes=-110,
        inicio_pre_selecao=-100,
        inicio_selecao=-90,
        fim_selecao=-80,
        divulgacao_selecao=-70,
    )
    criar_oferta(edital)
    criar_recurso(edital)
    projeto = criar_projeto(
        f'E2E Projeto Mon Doc {suf}',
        edital,
        pre_aprovado=True,
        aprovado=True,
        vinculo_monitor=monitor,
        inicio_execucao=hoje - timedelta(days=50),
        fim_execucao=hoje + timedelta(days=50),
    )
    criar_equipe(projeto)
    _meta, etapa = criar_meta_atividade(projeto)
    _item, desembolso = criar_memoria_e_desembolso(projeto)
    criar_caracterizacao(projeto, atendida=True)
    # Registros pendentes de validação (o que o monitor vai aprovar)
    criar_registro_execucao(etapa)
    criar_registro_gasto(desembolso)

    tela = Tela(logado_doc('coordenador')).ir(MONITORAMENTO)
    tela.ver_titulo('Monitoramento')
    capturar(tela.pagina, 'monitoramento-listagem')
    anotar_tela('monitoramento-listagem', tela)
    tela.linha(projeto.titulo).ver_botao('Acompanhar Validação')
    tela.linha(projeto.titulo).clicar_botao('Acompanhar Validação')

    tela.ver_titulo('Validar Execução')
    anotar_tela('monitoramento-validacao', tela)
    capturar(tela.pagina, 'monitoramento-validacao')

    # Aba Metas — aprovar a atividade
    tela.clicar_aba('Metas')
    tela.linha('Atividade 1 da meta').ver_botao('Aprovar')
    tela.linha('Atividade 1 da meta').clicar_botao('Aprovar')
    tela.sucesso('Execução de atividade validada com sucesso.')
    assert RegistroExecucaoEtapa.objects.get(etapa=etapa).aprovado, 'a UI disse que aprovou, mas não persistiu'

    # Aba Gastos — aprovar o gasto
    tela.clicar_aba('Gastos')
    capturar(tela.pagina, 'monitoramento-gastos')
    tela.linha('Exercício financeiro').ver_botao('Aprovar')
    tela.linha('Exercício financeiro').clicar_botao('Aprovar')
    tela.sucesso('Gasto validado com sucesso.')
    assert desembolso.registrogasto_set.get().aprovado, 'a UI disse que aprovou, mas não persistiu'
