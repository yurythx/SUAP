"""Fluxos de criação, permissões e tramitação básica do Processo Eletrônico (modo 2)."""

from uuid import uuid4
from typing import Any

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

PROCESSOS = '/admin/processo_eletronico/processo/'
PERMISSOES = '/processo_eletronico/permissoes/'
CAIXA = '/processo_eletronico/selecao_caixa_processos/'


def _sufixo() -> str:
    """Gera assuntos únicos para o banco reutilizado."""
    return uuid4().hex[:8]


def _selecionar_tipo(tela: Tela, nome: str) -> Tela:
    """Seleciona um tipo no popup padrão de escolha do SUAP."""
    tela.clicar_botao('Buscar')
    return tela.popup_ajax().selecionar_item(nome).clicar_botao('Confirmar')


def _criar_processo(tela: Tela, setor: str, assunto: str, interessado: str) -> None:
    """Executa o formulário comum de abertura de processo."""
    tela.clicar_botao('Adicionar Processo Eletrônico')
    _selecionar_tipo(tela, 'Acesso à Informação: Demanda do e-SIC')
    tela.preencher_formulario(
        [
            ('Interessados', 'autocomplete multiplo', interessado),
            ('Assunto', 'textarea', assunto),
            ('Nível de Acesso', 'lista', 'Público'),
            ('Setor de Criação', 'lista', setor),
        ]
    ).clicar_botao('Salvar').sucesso('Cadastro realizado com sucesso')


def test_operador_sem_compartilhamento_nao_ve_adicao(logado_processo_eletronico: Any) -> None:
    """Confirma que o operador sem compartilhamento não recebe a ação de criar."""
    tela = Tela(logado_processo_eletronico('operador_a')).ir(PROCESSOS).ver_titulo('Processos Eletrônicos')
    assert not tela.botao('Adicionar Processo Eletrônico').is_visible()

    from processo_eletronico.models import CompartilhamentoProcessoEletronicoSetorPessoa, Processo

    assert not CompartilhamentoProcessoEletronicoSetorPessoa.objects.filter(
        vinculo_permitido__user__username='128001', nivel_permissao=Processo.PERMISSAO_OPERAR_CRIAR_PROCESSO
    ).exists()


def test_operador_compartilhado_ve_adicao(logado_processo_eletronico: Any, operador_a_habilitado: Any) -> None:
    """Confirma que o compartilhamento habilita a abertura de processo."""
    Tela(logado_processo_eletronico('operador_a')).ir(PROCESSOS).ver_titulo('Processos Eletrônicos').ver_botao('Adicionar Processo Eletrônico')

    from processo_eletronico.models import CompartilhamentoProcessoEletronicoSetorPessoa, Processo

    assert CompartilhamentoProcessoEletronicoSetorPessoa.objects.filter(
        vinculo_permitido__user__username='128001',
        setor_dono__sigla='A1',
        nivel_permissao=Processo.PERMISSAO_OPERAR_CRIAR_PROCESSO,
    ).exists()


def test_chefe_gerencia_permissao_da_caixa(logado_processo_eletronico: Any, processo_seed: Any) -> None:
    """Concede ao operador A1 a permissão de operar e criar pela tela de permissões."""
    tela = (
        Tela(logado_processo_eletronico('chefe_a'))
        .ir(PERMISSOES)
        .ver_titulo('Permissões para Documentos e Processos Eletrônicos')
        .clicar_aba('Processos Eletrônicos')
    )
    tela.preencher(
        'Servidores/Prestadores de Serviço que podem adicionar e operar processos eletrônicos do(a) A1',
        'autocomplete multiplo',
        'Operador de Processo 1',
    ).clicar_botao('Enviar').sucesso('Operação realizada com sucesso')

    from processo_eletronico.models import CompartilhamentoProcessoEletronicoSetorPessoa, Processo

    assert CompartilhamentoProcessoEletronicoSetorPessoa.objects.filter(
        vinculo_permitido__user__username='128001',
        setor_dono__sigla='A1',
        nivel_permissao=Processo.PERMISSAO_OPERAR_CRIAR_PROCESSO,
    ).exists()


def test_chefe_b_gerencia_permissao_da_caixa(logado_processo_eletronico: Any, processo_seed: Any) -> None:
    """Concede ao operador A2 a permissão de operar e criar pela tela de permissões."""
    tela = (
        Tela(logado_processo_eletronico('chefe_b'))
        .ir(PERMISSOES)
        .ver_titulo('Permissões para Documentos e Processos Eletrônicos')
        .clicar_aba('Processos Eletrônicos')
    )
    tela.preencher(
        'Servidores/Prestadores de Serviço que podem adicionar e operar processos eletrônicos do(a) A2',
        'autocomplete multiplo',
        'Operador de Processo 2',
    ).clicar_botao('Enviar').sucesso('Operação realizada com sucesso')

    from processo_eletronico.models import CompartilhamentoProcessoEletronicoSetorPessoa, Processo

    assert CompartilhamentoProcessoEletronicoSetorPessoa.objects.filter(
        vinculo_permitido__user__username='128003',
        setor_dono__sigla='A2',
        nivel_permissao=Processo.PERMISSAO_OPERAR_CRIAR_PROCESSO,
    ).exists()


def test_criar_processo(logado_processo_eletronico: Any, operador_a_habilitado: Any) -> None:
    """Abre processo pelo formulário de processos eletrônicos."""
    tela = Tela(logado_processo_eletronico('operador_a')).ir(PROCESSOS).ver_titulo('Processos Eletrônicos')
    assunto = f'Assunto do processo E2E {_sufixo()}'
    _criar_processo(tela, 'A1', assunto, 'Operador de Processo 1')

    from processo_eletronico.models import Processo

    processo = Processo.objects.get(assunto=assunto)
    assert processo.nivel_acesso == Processo.NIVEL_ACESSO_PUBLICO
    assert processo.setor_criacao.sigla == 'A1'
    assert list(processo.interessados.values_list('pessoa__nome', flat=True)) == ['Operador de Processo 1']


def test_adicionar_processo_eletronico(logado_processo_eletronico: Any, operador_b_habilitado: Any) -> None:
    """Abre processo pelo setor A2 com o operador da segunda caixa."""
    tela = Tela(logado_processo_eletronico('operador_b')).ir(PROCESSOS).ver_titulo('Processos Eletrônicos')
    assunto = f'Assunto do processo A2 E2E {_sufixo()}'
    _criar_processo(tela, 'A2', assunto, 'Operador de Processo 1')

    from processo_eletronico.models import Processo

    processo = Processo.objects.get(assunto=assunto)
    assert processo.setor_criacao.sigla == 'A2'
