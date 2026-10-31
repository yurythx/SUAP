from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path

import pytest
from playwright.sync_api import Page

from auditoria.models import Paint, Relatorio, Recomendacao, Monitoramento, Manifestacao, Posicionamento
from djtools.e2e_fixtures import escolher_autocomplete, mensagem_de_sucesso
from djtools.e2e_ui import Tela, anotar_tela

pytestmark = [pytest.mark.doc, pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]


def test_01_cadastrar_paint(logado: Callable[[str], Page], capturar: Callable[[Page, str], Path], dados_auditoria: dict[str, object]) -> None:
    pagina = logado('auddoc2')
    tela = Tela(pagina).ir('/admin/auditoria/paint/')
    tela.ver_botao('Adicionar Plano Anual de Auditoria Interna (PAINT)')
    capturar(pagina, 'paint-listagem')
    tela.clicar_botao('Adicionar Plano Anual de Auditoria Interna (PAINT)')
    escolher_autocomplete(pagina, 'ano', str(date.today().year))
    tela.preencher('Início do Período de Planejamento Anual', 'data', f'01/01/{date.today().year}')
    tela.preencher('Fim do Período de Planejamento Anual', 'data', f'31/12/{date.today().year}')
    pagina.locator('#id_sincronizar_afastamentos_suap').uncheck()
    capturar(pagina, 'paint-formulario')
    tela.clicar_botao('Salvar')
    mensagem_de_sucesso(pagina, 'sucesso')
    paint = Paint.objects.get(ano=dados_auditoria['ano'])
    tela.ir(str(paint.get_absolute_url())).ver_texto(f'PAINT {date.today().year}')
    anotar_tela('paint-detalhe', tela)
    tela.clicar_botao('Sincronizar CH dos Auditores')
    mensagem_de_sucesso(pagina, 'carregada com sucesso')
    tela.ver_texto('Ana Auditora')
    capturar(pagina, 'paint-detalhe')
    tela.clicar_link('Ana Auditora')
    anotar_tela('planejamento-anual', tela)
    tela.ver_texto('Carga Horária')
    capturar(pagina, 'planejamento-anual')


def test_02_cadastrar_relatorio(logado: Callable[[str], Page], capturar: Callable[[Page, str], Path], dados_auditoria: dict[str, object]) -> None:
    pagina = logado('auddoc1')
    tela = Tela(pagina).ir('/admin/auditoria/relatorio/')
    tela.ver_botao('Adicionar Relatório')
    capturar(pagina, 'relatorio-listagem')
    tela.clicar_botao('Adicionar Relatório')
    tela.preencher('Número do relatório', 'número', '901')
    escolher_autocomplete(pagina, 'ano', str(date.today().year))
    escolher_autocomplete(pagina, 'ano_paint', str(date.today().year))
    escolher_autocomplete(pagina, 'acao', 'Avaliação de processos')
    escolher_autocomplete(pagina, 'nucleo', 'Núcleo Demonstração')
    tela.preencher('Data Inicial', 'data', f'01/01/{date.today().year}')
    tela.preencher('Data Final', 'data', date.today().strftime('%d/%m/%Y'))
    escolher_autocomplete(pagina, 'equipe', 'Ana Auditora')
    escolher_autocomplete(pagina, 'unidades_auditadas', 'ADOC')
    capturar(pagina, 'relatorio-formulario')
    tela.clicar_botao('Salvar')
    mensagem_de_sucesso(pagina, 'sucesso')
    relatorio = Relatorio.objects.get(numero=901, ano=dados_auditoria['ano'])
    tela.ir(str(relatorio.get_absolute_url())).ver_texto('Avaliação de processos')
    anotar_tela('relatorio-detalhe', tela)
    capturar(pagina, 'relatorio-detalhe')


def test_03_cadastrar_recomendacao(logado: Callable[[str], Page], capturar: Callable[[Page, str], Path]) -> None:
    pagina = logado('auddoc1')
    tela = Tela(pagina).ir('/admin/auditoria/recomendacao/add/')
    tela.ver_texto('Setores monitorados')
    escolher_autocomplete(pagina, 'relatorio', '901')
    tela.preencher('Descrição', 'textarea', 'Padronizar o registro das verificações de processos.')
    tela.preencher('Data limite', 'data', (date.today() + timedelta(days=60)).strftime('%d/%m/%Y'))
    escolher_autocomplete(pagina, 'nucleo', 'Núcleo Demonstração')
    escolher_autocomplete(pagina, 'monitor', 'Ana Auditora')
    escolher_autocomplete(pagina, 'unidades', 'ADOC')
    capturar(pagina, 'recomendacao-formulario')
    tela.clicar_botao('Salvar e visualizar')
    mensagem_de_sucesso(pagina, 'sucesso')
    recomendacao = Recomendacao.objects.get(relatorio__numero=901, monitor__user__username='auddoc1')
    tela.ir(str(recomendacao.get_absolute_url()))
    tela.ver_texto('Padronizar o registro')
    anotar_tela('recomendacao-detalhe', tela)
    capturar(pagina, 'recomendacao-detalhe')
    tela.clicar_botao('Monitorar')
    tela.esperar().ver_texto('Solicitação de providência')
    pagina.locator('input[name=unidades]').first.check()
    tela.preencher('Solicitação de providência', 'textarea', 'Apresentar os registros padronizados e as evidências de revisão.')
    tela.preencher('Prazo para atendimento', 'data', (date.today() + timedelta(days=30)).strftime('%d/%m/%Y'))
    anotar_tela('monitorar-formulario', tela)
    capturar(pagina, 'monitorar-formulario')
    tela.clicar_botao('Enviar')
    mensagem_de_sucesso(pagina, 'sucesso')
    tela.ver_status('Em monitoramento')
    capturar(pagina, 'recomendacao-monitorada')


def test_04_responder_recomendacao(logado: Callable[[str], Page], capturar: Callable[[Page, str], Path]) -> None:
    pagina = logado('auddoc3')
    monitoramento = Monitoramento.objects.get(recomendacao__relatorio__numero=901, unidade__sigla='ADOC')
    tela = Tela(pagina).ir('/auditoria/monitoramentos/').ver_texto('Recomendação')
    capturar(pagina, 'minhas-recomendacoes')
    tela.ir(str(monitoramento.get_absolute_url())).ver_botao('Adicionar manifestação')
    anotar_tela('monitoramento-gestor', tela)
    capturar(pagina, 'monitoramento-gestor')
    tela.clicar_botao('Adicionar manifestação').esperar()
    anotar_tela('manifestacao-formulario', tela)
    tela.ver_texto('Manifestação do auditado')
    tela.preencher('Tipo de manifestação', 'lista', 'Encaminhamento de Providências')
    tela.preencher('Manifestação do auditado', 'texto rico', 'Os registros foram padronizados e revisados pela unidade.')
    capturar(pagina, 'manifestacao-formulario')
    tela.clicar_botao('Salvar')
    mensagem_de_sucesso(pagina, 'Manifestação adicionada com sucesso')
    tela.ver_botao('Enviar manifestação')
    capturar(pagina, 'manifestacao-registrada')
    tela.clicar_botao('Enviar manifestação')
    mensagem_de_sucesso(pagina, 'sucesso')
    tela.ver_status('Enviada')
    capturar(pagina, 'manifestacao-enviada')


@pytest.mark.parametrize(
    ('tipo', 'classe', 'slug'), [('Financeiro', 'Economia de recursos', 'financeiro'), ('Qualitativo', 'Melhoria dos processos', 'qualitativo')]
)
def test_05_cadastrar_beneficio(
    logado: Callable[[str], Page],
    capturar: Callable[[Page, str], Path],
    tipo: str,
    classe: str,
    slug: str,
) -> None:
    pagina = logado('auddoc1')
    recomendacao = Recomendacao.objects.get(relatorio__numero=901, monitor__user__username='auddoc1')
    tela = Tela(pagina).ir(str(recomendacao.get_absolute_url())).clicar_aba('ADOC')
    tela.ver_botao('Adicionar Benefício')
    if tipo == 'Financeiro':
        capturar(pagina, 'beneficio-origem')
    tela.clicar_botao('Adicionar Benefício').esperar()
    tela.ver_texto('Nexo Causal')
    tela.preencher('Ano', 'número', str(date.today().year))
    tela.preencher('Tipo de benefício', 'lista', tipo)
    tela.preencher('Descrição do benefício', 'texto rico', f'Benefício {tipo.lower()} da padronização dos processos.')
    escolher_autocomplete(pagina, 'classe', classe)
    escolher_autocomplete(pagina, 'monitor', 'Ana Auditora')
    tela.preencher('Serviço de Auditoria', 'lista', 'Avaliação de processos')
    tela.ver_texto('Recomendação Associada')
    tela.preencher('Nexo Causal', 'texto rico', 'A adoção dos controles recomendados produziu a melhoria registrada.')
    if tipo == 'Financeiro':
        tela.preencher('Metodologia Cálculo', 'texto rico', 'Comparação entre o gasto anterior e o gasto após a implementação dos controles.')
        escolher_autocomplete(pagina, 'responsavel_calculo', 'Ana Auditora')
        tela.preencher('Valor Total do Benefício', 'número', '1000.00')
        tela.preencher('Natureza', 'lista', 'Gasto Evitado')
    else:
        escolher_autocomplete(pagina, 'unidade_afetada', 'Administração')
        escolher_autocomplete(pagina, 'alcance_estrategico', 'Melhoria da gestão')
    anotar_tela(f'beneficio-{slug}-formulario', tela)
    capturar(pagina, f'beneficio-{slug}-formulario')
    tela.clicar_botao('Salvar')
    mensagem_de_sucesso(pagina, 'sucesso')
    tela.ver_texto('A adoção dos controles recomendados')
    anotar_tela(f'beneficio-{slug}-detalhe', tela)
    capturar(pagina, f'beneficio-{slug}-detalhe')
    if tipo == 'Financeiro':
        tela.clicar_botao('Monitorar')
        mensagem_de_sucesso(pagina, 'Monitoramento iniciado')
        tela.ver_status('Em Monitoramento')
        capturar(pagina, 'beneficio-financeiro-monitorado')
        tela.clicar_aba('Detalhamento Financeiro').clicar_botao('Adicionar Parcela').esperar()
        anotar_tela('parcela-formulario', tela)
        tela.preencher('Data Prevista para Parcela', 'data', date.today().strftime('%d/%m/%Y'))
        tela.preencher('Valor Esperado da Parcela', 'número', '1000.00')
        tela.preencher('Data da Efetivação do Benefício', 'data', date.today().strftime('%d/%m/%Y'))
        tela.preencher('Valor Efetivo', 'número', '1000.00')
        tela.preencher('Observações', 'textarea', 'Economia confirmada pela comparação dos registros de gastos.')
        capturar(pagina, 'parcela-formulario')
        tela.clicar_botao('Salvar')
        mensagem_de_sucesso(pagina, 'Parcela Registrada com Sucesso')
        tela.ver_texto('Economia confirmada pela comparação')
        capturar(pagina, 'beneficio-financeiro-parcelas')
        tela.clicar_botao('Concluir')
    else:
        tela.clicar_botao('Publicar')
    mensagem_de_sucesso(pagina, 'Tarefa concluída com sucesso')
    estado = 'Concluído' if tipo == 'Financeiro' else 'Publicado'
    slug_final = 'concluido' if tipo == 'Financeiro' else 'publicado'
    anotar_tela(f'beneficio-{slug}-{slug_final}', tela)
    tela.ver_status(estado)
    capturar(pagina, f'beneficio-{slug}-{slug_final}')


def test_06_analisar_manifestacao(logado: Callable[[str], Page], capturar: Callable[[Page, str], Path]) -> None:
    manifestacao = Manifestacao.objects.get(monitoramento__recomendacao__relatorio__numero=901, monitoramento__unidade__sigla='ADOC')
    pagina = logado('auddoc1')
    tela = Tela(pagina).ir(str(manifestacao.get_absolute_url())).ver_botao('Receber manifestação')
    capturar(pagina, 'manifestacao-auditor')
    tela.clicar_botao('Receber manifestação')
    mensagem_de_sucesso(pagina, 'Manifestação recebida com sucesso')
    tela.ver_status('Em análise')
    tela.clicar_botao('Adicionar posicionamento').esperar()
    anotar_tela('posicionamento-formulario', tela)
    tela.preencher('Posicionamento', 'lista', 'Atendimento')
    escolher_autocomplete(pagina, 'motivacao', 'Providências atendidas')
    tela.preencher('Parecer do auditor', 'texto rico', 'Os registros apresentados comprovam o atendimento da recomendação.')
    capturar(pagina, 'posicionamento-formulario')
    tela.clicar_botao('Salvar')
    mensagem_de_sucesso(pagina, 'Posicionamento registrado com sucesso')
    tela.ver_botao('Publicar')
    capturar(pagina, 'posicionamento-registrado')
    tela.clicar_botao('Publicar')
    mensagem_de_sucesso(pagina, 'sucesso')
    tela.ver_status('Atendida')
    anotar_tela('posicionamento-publicado', tela)
    capturar(pagina, 'posicionamento-publicado')
    posicionamento = Posicionamento.objects.get(manifestacao=manifestacao)
    pagina = logado('auddoc3')
    tela = Tela(pagina).ir(str(posicionamento.get_absolute_url())).ver_texto('Os registros apresentados comprovam')
    capturar(pagina, 'posicionamento-gestor')


@pytest.mark.parametrize(
    ('rota', 'titulo', 'slug'),
    [
        ('/auditoria/monitoramento/relatorios/monitoramentos_por_unidade/', 'Recomendações por Setor', 'recomendacoes-setor'),
        ('/auditoria/relatorios/raint/', 'Resultados do monitoramento das recomendações de auditoria', 'raint'),
        ('/auditoria/relatorios/estoque/monitoramentos/', 'Estoque de Monitoramentos', 'estoque-monitoramentos'),
        ('/auditoria/relatorios/estoque/recomendacoes/', 'Estoque de Recomendações', 'estoque-recomendacoes'),
        ('/auditoria/beneficios/relatorios/financeiros/', 'Relatório Gerencial de Benefícios Financeiros', 'relatorio-financeiro'),
        ('/auditoria/beneficios/relatorios/qualitativos/', 'Relatório Gerencial de Benefícios Qualitativos', 'relatorio-qualitativo'),
        ('/auditoria/indicadores/monitoramento/painel/', 'Dashboard de Monitoramento da Recomendações', 'indicadores-monitoramento'),
        ('/auditoria/indicadores/beneficio/painel/', 'Dashboard de Benefícios', 'indicadores-beneficios'),
    ],
)
def test_10_consultar_relatorios(
    logado: Callable[[str], Page],
    capturar: Callable[[Page, str], Path],
    rota: str,
    titulo: str,
    slug: str,
) -> None:
    pagina = logado('auddoc1')
    tela = Tela(pagina).ir(rota).ver_titulo(titulo)
    anotar_tela(slug, tela)
    capturar(pagina, slug)
