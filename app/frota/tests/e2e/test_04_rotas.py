"""Smoke de rota do frota (modo 2: a unidade é a tela).

Abre em lote as telas de leitura e de formulário — as que renderizam sem mudar estado — com
`Tela.buscar` (GET sem renderizar). As ações, os relatórios em PDF/planilha e os formulários de
objeto que a cadeia não cria ficam em `ROTAS_DISPENSADAS`, no conftest, com o motivo.

Os alvos (`viatura`, `agendamento`, `viagem`) são resolvidos do que a cadeia `test_01`→`test_03`
criou. A falha lista **todas** as rotas quebradas de uma vez.
"""

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# Sem parâmetro: listagens e estatísticas que renderizam tela.
ROTAS_SEM_PARAMETRO = [
    '/frota/viagens/',
    '/frota/viagem_retroativa/',
    '/frota/controle_revisoes_viaturas/',
    '/frota/estatisticas_viaturas/',
    '/frota/estatisticas_deslocamento/',
    '/frota/viagens_por_viatura/',
    '/frota/estatistica_viagens_por_campus_setor/',
    '/frota/ver_calendario_agendamento/',
]

# Com parâmetro: detalhe e formulários sobre os objetos da cadeia.
ROTAS_COM_ALVO = [
    '/frota/viatura/{viatura}/',
    '/frota/agendamento/{agendamento}/',
    '/frota/viagem/{viagem}/',
    '/frota/ver_passageiros_viagem/{viagem}/',
    '/frota/ver_ordens_abastecimento_viagem/{viagem}/',
    '/frota/visualizar_multas/{viagem}/',
    '/frota/cadastrar_multa/{viagem}/',
    '/frota/ordem_abastecimento/{viagem}/',
    '/frota/ver_solicitacoes_edicao/{agendamento}/',
    '/frota/editar_proxima_revisao_viatura/{viatura}/',
]


def _alvos():
    from frota.models import Viagem, ViagemAgendamento, Viatura

    viatura = Viatura.objects.order_by('id').first()
    agendamento = ViagemAgendamento.objects.order_by('id').first()
    viagem = Viagem.objects.order_by('id').first()
    assert viatura is not None, 'cadeia não rodou: rode `pytest frota/tests/e2e` inteiro'
    assert agendamento is not None
    assert viagem is not None
    return {'viatura': viatura.pk, 'agendamento': agendamento.pk, 'viagem': viagem.pk}


def _abrir(tela, rotas, alvos):
    falhas = []
    for rota in rotas:
        url = rota.format_map(alvos)
        try:
            resposta = tela.buscar(url)
        except Exception as erro:
            falhas.append(f'{url} -> {type(erro).__name__}: {str(erro).splitlines()[0]}')
            continue
        if resposta.status == 200:
            continue
        if resposta.status in (301, 302):
            destino = resposta.headers.get('location', '')
            if 'login' in destino:
                falhas.append(f'{url} -> redirect para o login ({destino})')
            continue
        falhas.append(f'{url} -> HTTP {resposta.status}')
    return falhas


def test_rotas_abrem(logado_frota):
    """O Coordenador Sistêmico abre as telas de leitura e de formulário do módulo."""
    alvos = _alvos()
    tela = Tela(logado_frota('coord_sistemico'))
    falhas = _abrir(tela, ROTAS_SEM_PARAMETRO, {}) + _abrir(tela, ROTAS_COM_ALVO, alvos)
    assert not falhas, f'{len(falhas)} de {len(ROTAS_SEM_PARAMETRO) + len(ROTAS_COM_ALVO)} rotas não abriram:\n  ' + '\n  '.join(falhas)
