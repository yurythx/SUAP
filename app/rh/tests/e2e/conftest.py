"""RH: seed por factories sobre o substrato compartilhado, papéis antes da primeira request.

Sem relógio congelado: datas futuras relativas evitam expirar inscrições e cookies.
Arquivos independentes, consumíveis novos por teste; matrícula e setor sentinelas permitem
--reuse-db. Chefia real cobre bases legais; grupos reais cobrem permissões sem superuser.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from playwright.sync_api import Page

from djtools.e2e_fixtures import *  # noqa: F403
from djtools.e2e_fixtures import campus, criar_servidores

PAPEIS = {
    'sistemico': '8899101',
    'campus': '8899102',
    'servidor': '8899103',
    'auditor': '8899104',
    'saude': '8899105',
    'scdp': '8899190',
    'avaliacao': '8899191',
    'digital': '8899192',
    'almox': '8899193',
    # superuser só onde nenhum grupo padrão concede a permissão (rh.add_funcao)
    'admin': 'admin',
}
SERVIDORES = {
    '8899101': ('Rita Gestão Sistêmica', ['Coordenador de Gestão de Pessoas Sistêmico']),
    '8899102': ('Rita Gestão Campus', ['Coordenador de Gestão de Pessoas']),
    '8899103': ('Rita Servidora Teste', ['Servidor']),
    '8899104': ('Rita Auditoria Teste', ['Auditor']),
    '8899105': ('Rita Agenda Saúde', ['Gestor de Agenda de Saúde']),
    '8899190': ('Rita Extração SCDP', ['Gerenciador de Extração SCDP']),
    '8899191': ('Rita Avaliação Institucional', ['Administrador de Avaliação Institucional']),
    '8899192': ('Rita Cadastro Digital', ['Cadastrador de Digital']),
    '8899193': ('Rita Almoxarifado Sistêmico', ['Coordenador de Almoxarifado Sistêmico']),
}

ROTAS_DISPENSADAS = {
    '/rh/tela_relatorio/': 'Task gerar_busca_servidor: exportação do relatório, não tela independente.',
    '/rh/afastamento_pacial_upload/': 'Endpoint multipart de upload JSON; sem tela independente.',
    '/rh/visualizar_documentacao_pdf/<str:arquivo_id>/': 'Download de PDF por chave criptografada; sem tela HTML.',
    '/rh/excluir_documentacao_pdf/<str:arquivo_id>/': 'Exclusão de storage via AJAX retornando JSON; sem tela HTML.',
    '/rh/arquivo_unico/<str:hash_sha512_link_id>/': 'Streaming de arquivo binário pelo storage; sem tela HTML.',
    '/rh/importacao_siape/<int:importacao_id>/progresso.json': 'Polling JSON da importação, exercitado pela tela de detalhe.',
    '/rh/importacao_siape/<int:importacao_id>/interromper/': 'Endpoint POST sem tela própria; botão exercitado no fluxo de interrupção.',
    '/rh/importar_servidor/<str:cpf>/<str:apenas_servidores_em_exercicio>/': 'GET dispara task que consulta SIAPE externo; tela inicial coberta sem consulta externa.',
    '/rh/atualizar_meus_dados_servidor/': 'GET dispara importação no SIAPE externo; sem tela de formulário.',
}


@pytest.fixture(scope='session')
def rh_seed(e2e_seed: None) -> dict[str, object]:
    from comum.models import Configuracao
    from rh.models import JornadaTrabalho, Servidor, ServidorFuncaoHistorico, Setor
    from rh.tests.factories import AvaliadorFactory, JornadaTrabalhoFactory, ServidorFuncaoChefiaFactory, SetorSiapeFactory

    setor = campus('E2ERH', 'Campus RH E2E')
    criar_servidores(setor, SERVIDORES)
    servidores = {papel: Servidor.objects.get(matricula=matricula) for papel, matricula in PAPEIS.items() if papel != 'admin'}
    jornada = JornadaTrabalho.objects.filter(nome='40 HORAS SEMANAIS').first() or JornadaTrabalhoFactory(codigo='E2ERH40', nome='40 HORAS SEMANAIS')
    Servidor.objects.filter(matricula__in=SERVIDORES).update(jornada_trabalho=jornada)
    for servidor in servidores.values():
        servidor.refresh_from_db()
    siape = Setor.objects.filter(codigo='E2ERH').first() or SetorSiapeFactory(codigo='E2ERH', sigla='RH-SIAPE', nome='Setor RH SIAPE')
    if not ServidorFuncaoHistorico.objects.filter(servidor=servidores['sistemico'], setor_suap=setor, funcao__codigo='CD').exists():
        ServidorFuncaoChefiaFactory(servidor=servidores['sistemico'], setor=siape, setor_suap=setor)
    Configuracao.objects.update_or_create(app='rh', chave='setor_rh', defaults={'valor': str(setor.pk)})
    AvaliadorFactory(vinculo=servidores['servidor'].get_vinculo(), matricula_siape=servidores['servidor'].matricula)
    return {'setor': setor, 'siape': siape, **servidores}


@pytest.fixture
def logado_rh(logado: Callable[[str], Page], rh_seed: dict[str, object]) -> Callable[[str], Page]:
    def _logado(papel: str) -> Page:
        assert papel in PAPEIS, f'papel desconhecido: {papel}'
        return logado(PAPEIS[papel])

    return _logado
