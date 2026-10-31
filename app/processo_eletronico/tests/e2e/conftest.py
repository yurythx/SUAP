"""Infraestrutura dos e2e do Processo Eletrônico.

O módulo não tem mais ``features/``: o behave dele foi removido ao converter a suíte para o
**modo 2**, em que a unidade de cobertura é a rota — o gate é
``bin/scripts/paridade_e2e.py processo_eletronico --rotas`` — e a rastreabilidade de cada arquivo é
a sua docstring de módulo. O seed é por factories (#17486): ``semear_base()`` dá a raiz e o
``admin``; a árvore A0/A1/A2 + RE, os usuários e as chefias vêm de
``processo_eletronico/tests/e2e/seed.py``, e aqui se criam os dois processos fixos que os
fluxos consomem. Cada teste reabre esse estado para não depender de ordem nem de flush do banco
compartilhado do e2e.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from djtools.e2e_fixtures import *  # noqa: F403

PAPEIS = {
    'admin': 'admin',
    'servidor': 'ServidorB',
    'operador_a': '128001',
    'chefe_a': '128002',
    'operador_b': '128003',
    'chefe_b': '128004',
}

# Rotas que não viram teste. Cada motivo é uma condição verificável no código.
#
# Todas **mudam estado por GET** (nenhuma tem ``require_POST``): visitá-las no smoke
# apagaria/encaminharia/receberia dado que as outras suítes compartilham. Travar um teste nelas
# seria endossar o comportamento — o achado vai no MR.
ROTAS_DISPENSADAS = {
    '/processo_eletronico/processo/acompanhar/<int:processo_id>/': (
        'adiciona o usuário à lista de interesses por GET (``processo.adicionar_acompanhante_processo``), sem ``require_POST``.'
    ),
    '/processo_eletronico/processo/desacompanhar/<int:processo_id>/': (
        'remove o usuário da lista de interesses por GET (``processo.remover_acompanhante_processo``).'
    ),
    '/processo_eletronico/processo/remover_ultimo_tramite/<int:processo_id>/': (
        'remove o último trâmite do processo por GET (``processo.remover_ultimo_tramite()``).'
    ),
    '/processo_eletronico/processo/receber/<int:processo_id>/': 'recebe o processo por GET (``tramite.receber_processo``) sem ``require_POST``.',
    '/processo_eletronico/processo/receber_lote/<str:ids>/': 'recebe vários processos por GET quando a configuração ``permite_recebimento_lote`` está ligada.',
    '/processo_eletronico/adicionar_processo_relacionado/<int:processo_principal_id>/<int:processo_relacionado_id>/': (
        'cria o relacionamento entre os dois processos por GET (``adicionar_relacionamento``).'
    ),
    '/processo_eletronico/remover_relacionamento_processos/<int:processo_principal_id>/<int:processo_relacionado_id>/': (
        'remove o relacionamento entre os dois processos por GET (``remover_relacionamento``).'
    ),
    '/processo_eletronico/adicionar_documento/<int:processo_id>/<int:documento_id>/': (
        'adiciona o documento ao processo por GET (``DocumentoTextoProcesso.save()``).'
    ),
    '/processo_eletronico/adicionar_documento_requerimento/<int:requerimento_id>/<int:documento_id>/': (
        'adiciona o documento ao requerimento por GET; o seed não cria requerimentos.'
    ),
    '/processo_eletronico/atender_processo/<int:tramite_id>/': 'altera ``atendido``/``em_atendimento`` do trâmite por GET (``tramite.save()``).',
    '/processo_eletronico/cancelar_requerimento/<int:requerimento_id>/': 'cancela o requerimento por GET (``requerimento.save()``).',
    '/processo_eletronico/desconsiderar_comentario/<int:comentario_id>/': 'desconsidera o comentário por GET (``comentario.save()``).',
    '/processo_eletronico/excluir_comentario/<int:comentario_id>/': 'exclui o comentário por GET (``desconsiderar_comentario(..., excluir=True)``).',
    '/processo_eletronico/remover_documento_juntada/<int:documentojuntada_id>/': 'remove o documento da juntada por GET (``documento.delete()``).',
    '/processo_eletronico/remover_documento_requerimento/<int:documento_requerimento_id>/': 'remove o documento do requerimento por GET (``documento.delete()``).',
    '/processo_eletronico/remover_documento_upload_requerimento/<int:documento_digitalizado_requerimento_id>/': (
        'remove o upload do requerimento por GET (``documento.delete()``).'
    ),
    '/processo_eletronico/remover_permissao_processo_documento/': 'remove a permissão de processo/documento por GET (``delete()``).',
    '/processo_eletronico/solicitar_despacho/cancelar/<int:id>/': 'cancela a solicitação de despacho por GET (``indeferir_solicitacao()`` + ``save()``).',
    '/processo_eletronico/tramitedistribuicao/excluir_tramitedistribuicao/<int:tramite_distribuicao_pk>/': (
        'exclui a distribuição do trâmite por GET (``tramite_distribuicao.delete()``).'
    ),
}


def _usuario(matricula: str) -> Any:
    from rh.models import Servidor

    return Servidor.objects.get(matricula=matricula).get_user()


def _vinculo(matricula: str) -> Any:
    return _usuario(matricula).get_vinculo()


def _compartilhar_operacao(matricula: str, sigla_setor: str) -> None:
    from processo_eletronico.models import CompartilhamentoProcessoEletronicoSetorPessoa, Processo
    from rh.models import Setor

    usuario = _usuario('128002' if sigla_setor == 'A1' else '128004')
    setor = Setor.objects.suap().get(sigla=sigla_setor)
    vinculo = _vinculo(matricula)
    CompartilhamentoProcessoEletronicoSetorPessoa.objects.filter(
        setor_dono=setor,
        nivel_permissao=Processo.PERMISSAO_OPERAR_CRIAR_PROCESSO,
        vinculo_permitido=vinculo,
    ).delete()
    Processo.atualizar_compartilhamentos__pessoa(
        Processo.PERMISSAO_OPERAR_CRIAR_PROCESSO,
        usuario,
        setor,
        [vinculo],
    )


def _criar_processo(numero: str, matricula: str, sigla_setor: str, tipo: Any, interessado: Any, com_tramite: bool) -> Any:
    from processo_eletronico.models import Processo, Tramite
    from rh.models import Setor

    usuario = _usuario(matricula)
    setor = Setor.objects.suap().get(sigla=sigla_setor)
    processo = Processo.objects.filter(numero_protocolo=numero).first()
    if processo is None:
        processo = Processo.objects.create(
            tipo_processo=tipo,
            assunto=f'Processo fixo E2E {numero}',
            nivel_acesso=Processo.NIVEL_ACESSO_PUBLICO,
            setor_criacao=setor,
            usuario_gerador=usuario,
            modificado_por=usuario,
        )
        Processo.objects.filter(pk=processo.pk).update(numero_protocolo=numero, numero_protocolo_fisico=numero)
        processo.numero_protocolo = numero
        processo.numero_protocolo_fisico = numero
    Processo.objects.filter(pk=processo.pk).update(status=1, hipotese_legal=None, assunto=f'Processo fixo E2E {numero}', modificado_por=usuario)
    processo = Processo.objects.get(pk=processo.pk)
    processo.interessados.set([interessado])
    if com_tramite:
        tramite = Tramite(processo=processo)
        tramite.tramitar_processo(
            remetente_setor=Setor.objects.suap().get(sigla='A2'),
            remetente_vinculo=_vinculo('128004'),
            despacho_corpo=None,
            destinatario_vinculo=None,
            destinatario_setor=Setor.objects.suap().get(sigla='A1'),
            assinar_tramite=False,
        )
        tramite.data_hora_recebimento = datetime.now()
        tramite.recebido_por = _vinculo('128002')
        tramite.save()
    return processo


def _resetar_processos() -> None:
    from processo_eletronico.models import Processo, Tramite

    for numero, com_tramite in (
        ('23001.000001.2019-68', True),
        ('23001.000002.2019-11', False),
    ):
        processo = Processo.objects.filter(numero_protocolo=numero).first()
        if not processo:
            continue
        Processo.objects.filter(pk=processo.pk).update(ultimo_tramite=None)
        Tramite.objects.filter(processo=processo).delete()
        Processo.objects.filter(pk=processo.pk).update(status=1, nivel_acesso=Processo.NIVEL_ACESSO_PUBLICO, hipotese_legal=None)
        processo.__dict__['status'] = 1
        processo.acompanhantes_processo.clear()
        processo.interessados.set([_vinculo('128001')])
        if com_tramite:
            _criar_processo(numero, '128002', 'A1', processo.tipo_processo, _vinculo('128001'), True)


@pytest.fixture(scope='session')
def processo_seed(e2e_seed: Any) -> bool:
    """Carrega árvore, usuários, dados documentais e os processos fixos que os fluxos consomem."""
    from comum.models import Configuracao
    from documento_eletronico.models import DocumentoTexto, HipoteseLegal, TipoDocumento
    from processo_eletronico.models import CompartilhamentoProcessoEletronicoSetorPessoa, ModeloDespacho, Processo, TipoProcesso
    from processo_eletronico.tests.e2e import seed as seed_processo

    seed_processo.usuarios_processo(seed_processo.arvore_processo())
    if not DocumentoTexto.objects.filter(assunto='Documento Teste').exists():
        TipoDocumento.objects.filter(nome='Termo').delete()
        seed_processo.cadastros_documento_eletronico_basicos()
    elif not TipoDocumento.objects.filter(nome='Termo').exists():
        TipoDocumento.objects.create(nome='Termo', sigla='Termo', ativo=True)

    ModeloDespacho.objects.get_or_create(cabecalho='Cabeçalho E2E', rodape='Rodapé E2E')
    tipo, _ = TipoProcesso.objects.get_or_create(
        nome='Acesso à Informação: Demanda do e-SIC',
        defaults={
            'nivel_acesso_default': Processo.NIVEL_ACESSO_PUBLICO,
            'permite_gerar_processo_via_requerimento': True,
            'ativo': True,
        },
    )
    tipo.nivel_acesso_default = Processo.NIVEL_ACESSO_PUBLICO
    tipo.permite_gerar_processo_via_requerimento = True
    tipo.ativo = True
    tipo.save()
    hipotese_legal, _ = HipoteseLegal.objects.get_or_create(
        descricao='Informação Pessoal (Art. 31 da Lei no 12.527/2011)',
        defaults={'nivel_acesso': 'RESTRITO', 'base_legal': 'Informação Pessoal (Art. 31 da Lei no 12.527/2011)'},
    )
    tipo_documento_requerimento, _ = TipoDocumento.objects.get_or_create(nome='Requerimento', defaults={'sigla': 'REQ', 'ativo': True})
    Configuracao.objects.update_or_create(
        app='documento_eletronico', chave='tipo_documento_requerimento', defaults={'valor': tipo_documento_requerimento.pk}
    )
    Configuracao.objects.update_or_create(
        app='processo_eletronico', chave='hipotese_legal_documento_abertura_requerimento', defaults={'valor': hipotese_legal.pk}
    )
    Configuracao.objects.update_or_create(app='processo_eletronico', chave='exibir_numeracao_nup21', defaults={'valor': True})
    _criar_processo('23001.000001.2019-68', '128002', 'A1', tipo, _vinculo('128001'), True)
    _criar_processo('23001.000002.2019-11', '128004', 'A2', tipo, _vinculo('128001'), False)

    CompartilhamentoProcessoEletronicoSetorPessoa.objects.filter(
        vinculo_permitido__in=[_vinculo('128001'), _vinculo('128003')],
        nivel_permissao=Processo.PERMISSAO_OPERAR_CRIAR_PROCESSO,
    ).delete()

    return True


@pytest.fixture(autouse=True)
def estado_processo(processo_seed: Any) -> None:
    """Restaura os dois processos fixos antes de cada teste."""
    from processo_eletronico.models import CompartilhamentoProcessoEletronicoSetorPessoa, Processo

    _resetar_processos()
    CompartilhamentoProcessoEletronicoSetorPessoa.objects.filter(
        vinculo_permitido__user__username__in=['128001', '128003'],
        nivel_permissao=Processo.PERMISSAO_OPERAR_CRIAR_PROCESSO,
    ).delete()
    return


@pytest.fixture
def logado_processo_eletronico(logado: Any, processo_seed: Any) -> Any:
    """Devolve uma página autenticada pelo papel nominal dos fluxos."""

    def _logado(papel: str) -> Any:
        assert papel in PAPEIS, f'papel desconhecido: {papel}; declare em PAPEIS'
        return logado(PAPEIS[papel])

    return _logado


@pytest.fixture
def operador_a_habilitado(processo_seed: Any) -> None:
    """Habilita o operador A1 a criar e operar processos."""
    _compartilhar_operacao('128001', 'A1')


@pytest.fixture
def operador_b_habilitado(processo_seed: Any) -> None:
    """Habilita o operador A2 a criar e operar processos."""
    _compartilhar_operacao('128003', 'A2')


@pytest.fixture
def processo_a_receber(processo_seed: Any, operador_b_habilitado: Any) -> Any:
    """Prepara o processo fixo com trâmite novo destinado ao setor A2."""
    from processo_eletronico.models import Processo, Tramite
    from processo_eletronico.status import ProcessoStatus
    from rh.models import Setor

    processo = Processo.objects.get(numero_protocolo='23001.000001.2019-68')
    Processo.objects.filter(pk=processo.pk).update(ultimo_tramite=None, status=ProcessoStatus.STATUS_ATIVO)
    processo.__dict__['status'] = ProcessoStatus.STATUS_ATIVO
    tramite = Tramite(processo=processo)
    tramite.tramitar_processo(
        remetente_setor=Setor.objects.suap().get(sigla='A1'),
        remetente_vinculo=_vinculo('128002'),
        despacho_corpo=None,
        destinatario_vinculo=None,
        destinatario_setor=Setor.objects.suap().get(sigla='A2'),
        assinar_tramite=False,
    )
    return processo
