"""Tarefas 8, 9 e 10 — o fim do ciclo: o coordenador registra a conclusão, finaliza o
projeto e o monitor valida a conclusão. Usam um único projeto em execução plenamente
cumprida (execução e gastos aprovados), criado por ORM na tarefa 8 e reaproveitado pelas
tarefas 9 e 10 via estado.
"""

from __future__ import annotations

import sys
from uuid import uuid4

import pytest

from djtools.e2e_ui import Tela, anotar_tela

from . import estado
from .fabricas import (
    criar_caracterizacao,
    criar_edital,
    criar_equipe,
    criar_foto,
    criar_memoria_e_desembolso,
    criar_meta_atividade,
    criar_oferta,
    criar_projeto,
    criar_recurso,
    criar_registro_conclusao,
    criar_registro_execucao,
    criar_registro_gasto,
)

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

CAMPOS = estado.CAMPOS


def test_registrar_conclusao(logado_doc, capturar):
    """Tarefa 8 — o coordenador registra a conclusão de um projeto bem executado."""
    from datetime import date, timedelta

    from comum.models import Vinculo
    from projetos_ensino.models import Projeto

    estado.novo()  # zera o estado compartilhado antes de popular (idempotente sob --reruns)

    hoje = date.today()
    monitor = Vinculo.objects.get(user__username='158002')
    suf = uuid4().hex[:8]
    edital = criar_edital(
        f'E2E Edital Conc Doc {suf}',
        inicio_inscricoes=-140,
        fim_inscricoes=-120,
        inicio_pre_selecao=-110,
        inicio_selecao=-100,
        fim_selecao=-90,
        divulgacao_selecao=-80,
    )
    criar_oferta(edital)
    criar_recurso(edital)
    projeto = criar_projeto(
        f'E2E Projeto Conc Doc {suf}',
        edital,
        pre_aprovado=True,
        aprovado=True,
        vinculo_monitor=monitor,
        inicio_execucao=hoje - timedelta(days=60),
        fim_execucao=hoje - timedelta(days=1),
    )
    criar_equipe(projeto)
    _meta, etapa = criar_meta_atividade(projeto)
    _item, desembolso = criar_memoria_e_desembolso(projeto)
    criar_caracterizacao(projeto, atendida=True)
    criar_registro_execucao(etapa, aprovado=True)
    criar_registro_gasto(desembolso, aprovado=True)
    criar_foto(projeto)
    CAMPOS['projeto_id'] = projeto.pk
    CAMPOS['etapa_registro_id'] = etapa.pk

    tela = Tela(logado_doc('coordenador_projeto')).ir(f'/projetos_ensino/projeto/{projeto.pk}/?tab=conclusao')
    tela.ver_titulo(f'Projeto de Ensino: {projeto.titulo}')
    anotar_tela('conclusao-tab', tela)
    capturar(tela.pagina, 'conclusao-tab')
    tela.ver_botao('Registrar Conclusão')
    tela.clicar_botao('Registrar Conclusão')

    popup = tela.popup()
    popup.ver_botao('Salvar')
    anotar_tela('conclusao-popup', popup)
    popup.preencher_formulario(
        [
            ('Resultados Alcançados', 'textarea', 'Resultados alcançados'),
            ('Disseminação dos Resultados', 'textarea', 'Disseminação dos resultados'),
            ('Observação', 'textarea', 'Conclusão registrada após a execução completa'),
        ]
    )
    capturar(tela.pagina, 'conclusao-formulario')
    popup.salvar_no_popup('Salvar')

    tela.sucesso('Conclusão do projeto registrada com sucesso.')
    assert Projeto.objects.get(pk=projeto.pk).get_registro_conclusao() is not None, 'a UI disse que registrou, mas não persistiu'


def test_finalizar_projeto(logado_doc, capturar):
    """Tarefa 9 — o coordenador finaliza o projeto concluído (sem pendências)."""
    from projetos_ensino.models import Projeto

    projeto = Projeto.objects.get(pk=estado.pega('projeto_id', 'test_registrar_conclusao'))

    tela = Tela(logado_doc('coordenador_projeto')).ir(f'/projetos_ensino/projeto/{projeto.pk}/?tab=conclusao')
    tela.ver_botao('Finalizar Projeto')
    tela.clicar_botao('Finalizar Projeto')

    tela.sucesso('Conclusão finalizada com sucesso.')
    projeto.refresh_from_db()
    assert projeto.data_finalizacao_conclusao is not None, 'a UI disse que finalizou, mas não persistiu'
    anotar_tela('finalizacao-pagina', tela)
    capturar(tela.pagina, 'finalizacao-pagina')


def test_validar_conclusao(logado_doc, capturar):
    """Tarefa 10 — o monitor emite o parecer final sobre a conclusão do projeto."""
    from projetos_ensino.models import Projeto, RegistroConclusaoProjeto

    projeto = Projeto.objects.get(pk=estado.pega('projeto_id', 'test_registrar_conclusao'))
    registro = projeto.get_registro_conclusao()

    tela = Tela(logado_doc('coordenador')).ir('/projetos_ensino/projetos_em_execucao/')
    tela.ver_titulo('Monitoramento')
    capturar(tela.pagina, 'validar-conclusao-listagem')
    tela.linha(projeto.titulo).ver_botao('Acompanhar Validação')
    tela.linha(projeto.titulo).clicar_botao('Acompanhar Validação')

    tela.ver_titulo('Validar Execução')
    tela.clicar_aba('Conclusão do Projeto')
    anotar_tela('validar-conclusao-tab', tela)
    capturar(tela.pagina, 'validar-conclusao-tab')
    tela.ver_botao('Emitir Parecer')
    tela.clicar_botao('Emitir Parecer')

    popup = tela.popup()
    popup.ver_botao('Enviar')
    anotar_tela('validar-conclusao-popup', popup)
    popup.preencher_formulario([('Aprovado', 'checkbox', 'marcar'), ('Observação', 'textarea', 'Conclusão aprovada pelo monitor')])
    capturar(tela.pagina, 'validar-conclusao-formulario')
    popup.salvar_no_popup('Enviar')

    tela.sucesso('Conclusão do projeto registrada com sucesso.')
    registro.refresh_from_db()
    assert registro.aprovado, 'a UI disse que aprovou, mas não persistiu'
    assert Projeto.objects.get(pk=projeto.pk).get_status() == Projeto.STATUS_CONCLUIDO, 'projeto deveria estar concluído'
