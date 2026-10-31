"""Fluxos de atividade em grupo e ação educativa (planejamento, execução e presença).

O coordenador sistêmico cadastra a meta pelo admin, cria a ação educativa vinculada a ela,
registra a execução e cancela o que não vai acontecer. O mesmo modelo (`AtividadeGrupo`) é a
atividade em grupo comum, cuja presença o aluno registra lendo o QR code da atividade — é o
único caminho em que `registrar_presenca_atividade_grupo` é oferecido ao aluno.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from playwright.sync_api import Page, expect

from djtools.e2e_ui import Tela

if TYPE_CHECKING:
    from saude.models import AtividadeGrupo

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

META_ADMIN = '/admin/saude/metaacaoeducativa/'
META_ADD = '/admin/saude/metaacaoeducativa/add/'
ATIVIDADE_ADMIN = '/admin/saude/atividadegrupo/'
ADICIONAR_ACAO = '/saude/adicionar_acao_educativa/{}/'
ADICIONAR_ACAO_SEM_META = '/saude/adicionar_acao_educativa_sem_meta/'
VISUALIZAR_ACOES = '/saude/visualizar_acoes_educativas/{}/'
VISUALIZAR_ACAO = '/saude/visualizar_acao_educativa/{}/'
REGISTRAR_EXECUCAO = '/saude/registrar_execucao_acao_educativa/{}/'
VISUALIZAR_META = '/saude/visualizar_meta_acao_educativa/{}/'
CANCELAR_ACAO = '/saude/cancelar_acao_educativa/{}/'
ATIVIDADE_EM_GRUPO = '/saude/atividade_em_grupo/{}/'
CANCELAR_ATIVIDADE = '/saude/cancelar_atividade_grupo/{}/'
REGISTRAR_PRESENCA = '/saude/registrar_presenca_atividade_grupo/{}/'

# A suíte não dá flush e o admin acumula registros entre execuções: os nomes fixos da
# feature viram nomes únicos, senão a segunda execução acha o registro da primeira.
SUFIXO = uuid4().hex[:8]
NOME_META = f'Meta E2E {SUFIXO}'
NOME_ACAO = f'Ação Educativa E2E {SUFIXO}'
NOME_INDEPENDENTE = f'Ação Independente E2E {SUFIXO}'
NOME_ATIVIDADE = f'Atividade em Grupo E2E {SUFIXO}'


def _criar_meta(tela: Tela) -> int:
    """Cadastra a meta da ação educativa pelo admin e devolve o pk."""
    from saude.models import MetaAcaoEducativa

    tela.ir(META_ADD).esperar()
    tela.preencher_formulario(
        [
            ('Ano de Referência', 'Autocomplete', '2019'),
            ('Objetivos', 'Autocomplete Multiplo', 'Novo Objetivo de Ação Educativa'),
            ('Descrição', 'TextArea', NOME_META),
            ('Tipo de Indicador', 'Lista', 'Número de Ações'),
            ('Quantidade', 'Número', '5'),
        ]
    )
    tela.clicar_botao('Salvar')
    meta = MetaAcaoEducativa.objects.filter(descricao=NOME_META).order_by('-id').first()
    assert meta is not None, 'a UI do admin não gravou a meta da ação educativa'
    return meta.pk


def _preencher_acao(tela: Tela, nome: str, turma: tuple[str, str] | None = None) -> None:
    """Preenche o formulário de ação educativa (o que resta depois dos campos removidos)."""
    dados = [
        ('Nome do Evento/Atividade', 'Texto', nome),
        ('Recurso Necessário', 'TextArea', 'Recurso E2E'),
        ('Data de Início', 'Data e hora', '22/01/2019 08:00'),
        ('Data de Término', 'Data e hora', '22/01/2019 10:00'),
        ('Solicitante', 'Texto', 'Coordenação de Saúde E2E'),
    ]
    if turma is not None:
        dados.append(('Turma', 'Autocomplete', turma[0], turma[1]))
    tela.preencher_formulario(dados)


def test_acao_educativa_cadastro_execucao_e_cancelamento(logado_saude: Callable[[str], Page]) -> None:
    """O coordenador percorre a ação educativa: cadastro, execução, cancelamento e meta."""
    tela = Tela(logado_saude('coordenador_sistemico'))

    from saude.models import AtividadeGrupo, MetaAcaoEducativa

    meta_id = _criar_meta(tela)
    meta = MetaAcaoEducativa.objects.get(pk=meta_id)

    tela.ir(META_ADMIN).ver_texto(NOME_META)
    tela.linha(NOME_META).clicar_botao('Adicionar Ação')
    expect(tela.pagina).to_have_url(re.compile(rf'{ADICIONAR_ACAO.format(meta_id)}$'))
    _preencher_acao(tela, NOME_ACAO)
    tela.clicar_botao('Salvar').sucesso('Ação cadastrada com sucesso.')
    acao = AtividadeGrupo.objects.get(meta=meta, nome_evento=NOME_ACAO)
    assert acao.uo is not None, 'a ação educativa precisa nascer vinculada ao campus de quem cadastrou'
    assert acao.tema is None, 'a ação educativa nasce sem tema — é o tema que marca a execução'

    tela.ir(VISUALIZAR_ACOES.format(meta_id)).ver_titulo('Ações Educativas').ver_texto(NOME_ACAO)
    tela.cartao(NOME_ACAO).clicar_botao('Visualizar Ação')
    expect(tela.pagina).to_have_url(re.compile(rf'{VISUALIZAR_ACAO.format(acao.pk)}$'))
    tela.ver_titulo('Visualizar Ação Educativa').ver_texto(NOME_ACAO)

    # A execução é o que preenche o tema da ação — por isso o formulário é o mesmo, com a
    # instância da ação (e com os campos que o cadastro sem meta havia removido).
    tela.ir(VISUALIZAR_ACOES.format(meta_id))
    tela.cartao(NOME_ACAO).clicar_botao('Registrar Execução')
    expect(tela.pagina).to_have_url(re.compile(rf'{REGISTRAR_EXECUCAO.format(acao.pk)}$'))
    tela.preencher_formulario(
        [
            ('Nome do Evento/Atividade', 'Texto', NOME_ACAO),
            ('Tipo', 'Autocomplete', 'Reunião'),
            ('Tema', 'Texto', 'Tema da execução E2E'),
            ('Recurso Necessário', 'TextArea', 'Recurso E2E'),
            ('Número de Participantes', 'Número', '12'),
            ('Data de Início', 'Data e hora', '22/01/2019 08:00'),
            ('Data de Término', 'Data e hora', '22/01/2019 10:00'),
            ('Responsáveis', 'Autocomplete Multiplo', '111001'),
        ]
    )
    tela.clicar_botao('Salvar').sucesso('Execução da ação registrada com sucesso.')
    acao.refresh_from_db()
    assert acao.tema == 'Tema da execução E2E', 'a UI disse que registrou a execução, mas o tema não persistiu'

    tela.ver_texto('Executada?').ver_texto('Sim')

    # Uma segunda ação, ainda sem tema, é a que oferece "Cancelar Ação": o produto só mostra
    # o botão enquanto a ação não foi executada, e o cancelamento apaga o registro.
    tela.ir(META_ADMIN)
    tela.linha(NOME_META).clicar_botao('Adicionar Ação')
    _preencher_acao(tela, NOME_INDEPENDENTE)
    tela.clicar_botao('Salvar').sucesso('Ação cadastrada com sucesso.')
    cancelavel = AtividadeGrupo.objects.get(meta=meta, nome_evento=NOME_INDEPENDENTE)

    tela.ir(VISUALIZAR_ACOES.format(meta_id))
    tela.cartao(NOME_INDEPENDENTE).clicar_botao('Cancelar Ação')
    tela.sucesso('Ação cancelada com sucesso.')
    assert not AtividadeGrupo.objects.filter(pk=cancelavel.pk).exists(), 'a UI disse que cancelou, mas a ação permanece'

    # A ação independente nasce sem meta, pelo botão do action-bar do admin.
    tela.ir(META_ADMIN)
    tela.clicar_botao('Cadastrar Ação Independente')
    expect(tela.pagina).to_have_url(re.compile(rf'{ADICIONAR_ACAO_SEM_META}$'))
    _preencher_acao(tela, f'{NOME_ATIVIDADE} sem meta')
    tela.clicar_botao('Salvar').sucesso('Ação cadastrada com sucesso.')
    independente = AtividadeGrupo.objects.get(nome_evento=f'{NOME_ATIVIDADE} sem meta', meta__isnull=True)
    assert independente.uo is not None, 'a ação independente precisa nascer vinculada ao campus de quem cadastrou'

    tela.ir(META_ADMIN)
    tela.linha(NOME_META).clicar_icone('exibição')
    expect(tela.pagina).to_have_url(re.compile(rf'{VISUALIZAR_META.format(meta_id)}$'))
    tela.ver_titulo('Visualizar Meta da Ação Educativa').ver_texto(NOME_META)


def test_atividade_em_grupo_e_presenca_do_aluno(logado_saude: Callable[[str], Page]) -> None:
    """O coordenador cancela a atividade em grupo e o aluno registra presença pelo QR code."""
    tela = Tela(logado_saude('coordenador_sistemico'))

    from saude.models import AtividadeGrupo, RegistroPresencaAtividadeGrupo

    tela.ir(META_ADMIN).esperar()
    tela.clicar_botao('Cadastrar Ação Independente')
    expect(tela.pagina).to_have_url(re.compile(rf'{ADICIONAR_ACAO_SEM_META}$'))
    # A turma é pesquisável pelo código (o rótulo do resultado é a descrição derivada).
    _preencher_acao(tela, NOME_ATIVIDADE, turma=('TECINFO-SAUDE-E2E', 'Integrado'))
    tela.clicar_botao('Salvar').sucesso('Ação cadastrada com sucesso.')
    atividade = AtividadeGrupo.objects.get(nome_evento=NOME_ATIVIDADE, meta__isnull=True)
    assert atividade.turma is not None, 'a atividade precisa da turma para o aluno registrar presença'

    # A atividade aparece no admin de atividades em grupo, e o ícone de exibição abre a tela
    # com o QR code que o aluno lê.
    tela.ir(ATIVIDADE_ADMIN).ver_texto(NOME_ATIVIDADE)
    tela.linha(NOME_ATIVIDADE).clicar_icone('exibição')
    expect(tela.pagina).to_have_url(re.compile(rf'{ATIVIDADE_EM_GRUPO.format(atividade.pk)}$'))
    # A tela não exibe o nome do evento, e sim o tema (vazio na ação independente).
    tela.ver_titulo('Atividade em Grupo').ver_texto('Coordenação de Saúde E2E').ver_texto('TECINFO-SAUDE-E2E')

    aluno = Tela(logado_saude('aluno'))
    aluno.ir(REGISTRAR_PRESENCA.format(atividade.pk))
    aluno.sucesso('Presença registrada com sucesso.')
    assert RegistroPresencaAtividadeGrupo.objects.filter(atividade=atividade, aluno__matricula='20191101011111').exists(), (
        'a UI disse que registrou a presença, mas ela não persistiu'
    )

    tela.ir(ATIVIDADE_ADMIN)
    expect(tela.linha(NOME_ATIVIDADE).botao('Cancelar Atividade')).to_have_attribute('href', CANCELAR_ATIVIDADE.format(atividade.pk))
    tela.linha(NOME_ATIVIDADE).clicar_botao('Cancelar Atividade')
    tela.sucesso('Atendimento cancelado com sucesso.')
    atividade.refresh_from_db()
    assert atividade.cancelada, 'a UI disse que cancelou, mas a atividade continua ativa'
