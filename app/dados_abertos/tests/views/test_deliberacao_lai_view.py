"""Testes das telas do ciclo LAI: a fila de deliberação e o reenvio pelo gestor."""

import datetime

import pytest
from django.core.files.base import ContentFile
from django.urls import reverse

from dados_abertos.enums import SituacaoLAI, TipoEventoLAI
from dados_abertos.models import BaseDados, PDABaseDados, PlanoDadosAbertos
from rh.tests.factories import ServidorFactory

SENHA = '123'

CSV_EXEMPLO = 'curso,campus,total\nInformatica,NAT-CN,320\n'


def _criar_pda(titulo: str = 'PDA 2026-2027', ano: int = 2026) -> PlanoDadosAbertos:
    return PlanoDadosAbertos.objects.create(
        titulo=titulo,
        vigencia_inicio=datetime.date(ano, 1, 1),
        vigencia_fim=datetime.date(ano, 12, 31),
    )


def _criar_relacao(pda, titulo: str, situacao=SituacaoLAI.EM_ANALISE) -> PDABaseDados:
    base = BaseDados.objects.create(nome=titulo.lower().replace(' ', '-')[:120], titulo=titulo)
    recurso = base.recursos.create(nome=f'{titulo} csv', formato='CSV')
    recurso.arquivo.save('dados.csv', ContentFile(CSV_EXEMPLO.encode()), save=True)
    return PDABaseDados.objects.create(pda=pda, base_dados=base, situacao_lai=situacao)


@pytest.fixture
def cliente_lai(client, db, sync_permissions):
    """Cliente autenticado com poderes de Responsável LAI.

    O ator precisa ser superusuário — antes isso vinha do `admin` do `suap_data` — e ter
    setor com campus, senão o `UsuarioSemSetorMiddleware` o desloga.
    """
    servidor = ServidorFactory()
    usuario = servidor.get_user()
    usuario.is_superuser = True
    usuario.is_staff = True
    usuario.set_password(SENHA)
    usuario.save()
    assert client.login(username=usuario.username, password=SENHA)
    return client


@pytest.fixture
def cliente_sem_poder(client, db, sync_permissions):
    """Servidor com setor (para não cair no middleware), porém sem permissão alguma."""
    usuario = ServidorFactory().get_user()
    usuario.set_password(SENHA)
    usuario.save()
    assert client.login(username=usuario.username, password=SENHA)
    return client


# ------------------------------------------------------------------------ fila do LAI


def test_abre_no_primeiro_da_fila(cliente_lai):
    pda = _criar_pda()
    primeira = _criar_relacao(pda, 'Aaa base')
    _criar_relacao(pda, 'Zzz base')

    resposta = cliente_lai.get(reverse('dados_abertos:deliberacao_lai'), {'pda': pda.pk})

    assert resposta.status_code == 200
    assert resposta.context['detalhe'].relacao.pk == primeira.pk
    assert len(resposta.context['fila']) == 2
    assert resposta.context['posicao'] == 1


def test_abre_no_item_indicado_na_url(cliente_lai):
    pda = _criar_pda()
    _criar_relacao(pda, 'Aaa base')
    escolhida = _criar_relacao(pda, 'Zzz base')

    resposta = cliente_lai.get(reverse('dados_abertos:deliberacao_lai'), {'pda': pda.pk, 'rel': escolhida.pk})

    assert resposta.context['detalhe'].relacao.pk == escolhida.pk
    assert resposta.context['posicao'] == 2
    assert resposta.context['anterior'].pk != escolhida.pk
    assert resposta.context['proximo'] is None


def test_so_entram_na_fila_datasets_com_recurso(cliente_lai):
    """Sem recurso não há prévia — o LAI não teria o que avaliar."""
    pda = _criar_pda()
    com_recurso = _criar_relacao(pda, 'Com recurso')
    base_vazia = BaseDados.objects.create(nome='sem-recurso', titulo='Sem recurso')
    PDABaseDados.objects.create(pda=pda, base_dados=base_vazia, situacao_lai=SituacaoLAI.EM_ANALISE)

    resposta = cliente_lai.get(reverse('dados_abertos:deliberacao_lai'), {'pda': pda.pk})

    assert [item.pk for item in resposta.context['fila']] == [com_recurso.pk]


def test_parecer_e_preservado_quando_a_validacao_falha(cliente_lai):
    """Devolver sem parecer não pode custar o texto já escrito — antes o redirect o descartava."""
    pda = _criar_pda()
    relacao = _criar_relacao(pda, 'Base única')

    resposta = cliente_lai.post(
        reverse('dados_abertos:deliberacao_lai'),
        {'pda': pda.pk, 'relacao_id': relacao.pk, 'decisao': SituacaoLAI.DEVOLVIDO, 'parecer': '   '},
    )

    assert resposta.status_code == 200, 'deveria re-renderizar, não redirecionar'
    assert resposta.context['detalhe'].relacao.pk == relacao.pk
    assert resposta.context['parecer_digitado'] == '   '
    relacao.refresh_from_db()
    assert relacao.situacao_lai == SituacaoLAI.EM_ANALISE


def test_apos_deliberar_segue_para_o_proximo_da_fila(cliente_lai):
    pda = _criar_pda()
    primeira = _criar_relacao(pda, 'Aaa base')
    segunda = _criar_relacao(pda, 'Zzz base')

    resposta = cliente_lai.post(
        reverse('dados_abertos:deliberacao_lai'),
        {'pda': pda.pk, 'relacao_id': primeira.pk, 'decisao': SituacaoLAI.LIBERADO, 'parecer': 'ok'},
    )

    assert resposta.status_code == 302
    assert resposta.url.endswith(f'?pda={pda.pk}&rel={segunda.pk}')


def test_ultima_deliberacao_encerra_a_fila(cliente_lai):
    pda = _criar_pda()
    unica = _criar_relacao(pda, 'Base única')

    resposta = cliente_lai.post(
        reverse('dados_abertos:deliberacao_lai'),
        {'pda': pda.pk, 'relacao_id': unica.pk, 'decisao': SituacaoLAI.LIBERADO, 'parecer': 'ok'},
    )

    assert resposta.status_code == 302
    assert resposta.url.endswith(f'?pda={pda.pk}')


def test_sem_permissao_de_deliberar_nao_abre_a_tela(cliente_sem_poder):
    pda = _criar_pda()
    _criar_relacao(pda, 'Base única')

    resposta = cliente_sem_poder.get(reverse('dados_abertos:deliberacao_lai'), {'pda': pda.pk})

    assert resposta.status_code == 403


# --------------------------------------------------------------------- reenvio do gestor


def test_gestor_reenvia_base_devolvida(cliente_lai):
    pda = _criar_pda()
    relacao = _criar_relacao(pda, 'Base devolvida', situacao=SituacaoLAI.DEVOLVIDO)

    resposta = cliente_lai.post(
        reverse('dados_abertos:reenviar_lai', args=[pda.pk, relacao.pk]),
        {'resposta': 'Coluna CPF removida.'},
    )

    assert resposta.status_code == 302
    relacao.refresh_from_db()
    assert relacao.situacao_lai == SituacaoLAI.EM_ANALISE
    evento = relacao.eventos_lai.get()
    assert evento.tipo == TipoEventoLAI.REENVIO
    assert evento.texto == 'Coluna CPF removida.'


def test_reenvio_sem_resposta_nao_muda_a_situacao(cliente_lai):
    pda = _criar_pda()
    relacao = _criar_relacao(pda, 'Base devolvida', situacao=SituacaoLAI.DEVOLVIDO)

    cliente_lai.post(reverse('dados_abertos:reenviar_lai', args=[pda.pk, relacao.pk]), {'resposta': ''})

    relacao.refresh_from_db()
    assert relacao.situacao_lai == SituacaoLAI.DEVOLVIDO
    assert not relacao.eventos_lai.exists()


def test_nao_reenvia_base_que_nao_esta_devolvida(cliente_lai):
    pda = _criar_pda()
    relacao = _criar_relacao(pda, 'Base em análise')

    cliente_lai.post(reverse('dados_abertos:reenviar_lai', args=[pda.pk, relacao.pk]), {'resposta': 'ajustei'})

    relacao.refresh_from_db()
    assert relacao.situacao_lai == SituacaoLAI.EM_ANALISE
    assert not relacao.eventos_lai.exists()


def test_sem_permissao_de_alterar_nao_reenvia(cliente_sem_poder):
    pda = _criar_pda()
    relacao = _criar_relacao(pda, 'Base devolvida', situacao=SituacaoLAI.DEVOLVIDO)

    resposta = cliente_sem_poder.post(
        reverse('dados_abertos:reenviar_lai', args=[pda.pk, relacao.pk]),
        {'resposta': 'ajustei'},
    )

    assert resposta.status_code == 403
    relacao.refresh_from_db()
    assert relacao.situacao_lai == SituacaoLAI.DEVOLVIDO


# ------------------------------------------------------------------- dashboard do gestor


def test_dashboard_expoe_as_bases_devolvidas_com_o_parecer(cliente_lai):
    """O parecer precisa chegar a quem executa o ajuste, não só ao admin de eventos."""
    from dados_abertos.services.lai_service import registrar_deliberacao

    pda = _criar_pda()
    relacao = _criar_relacao(pda, 'Base devolvida')
    registrar_deliberacao(
        relacao_id=relacao.pk,
        decisao=SituacaoLAI.DEVOLVIDO,
        parecer='Remover a coluna CPF.',
        vinculo=None,
        ip=None,
        user_agent='',
    )

    resposta = cliente_lai.get(reverse('dados_abertos:dashboard', args=[pda.pk]))

    assert resposta.status_code == 200
    devolvidas = resposta.context['devolvidas_lai']
    assert [r.pk for r in devolvidas] == [relacao.pk]
    assert devolvidas[0].parecer_lai.texto == 'Remover a coluna CPF.'
