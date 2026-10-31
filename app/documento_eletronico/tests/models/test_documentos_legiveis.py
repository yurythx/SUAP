"""``DocumentoTexto.objects.legiveis_por(user)`` é a regra de ``pode_ler`` como filtro (#17699).

Caracterização: um documento de setor para cada ramo de ``tem_permissao_ler`` e de
``acesso_ao_documento_em_funcao_cargo``, e usuários de papéis diferentes; para cada um, o
filtro devolve exatamente os documentos em que ``pode_ler`` diz sim.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from django.contrib.auth.models import Group
from django.core.cache import cache

from comum.models import Configuracao, User
from djtools.middleware import threadlocals as tl
from djtools.utils import get_datetime_now
from documento_eletronico.models import (
    CompartilhamentoDocumentoPessoa,
    CompartilhamentoSetorPessoa,
    Documento,
    DocumentoTexto,
    NivelPermissao,
    SolicitacaoAssinatura,
)
from documento_eletronico.status import DocumentoStatus, SolicitacaoStatus
from documento_eletronico.tests.factories import DocumentoTextoFactory, ModeloDocumentoFactory, SolicitacaoAssinaturaFactory
from edu.tests.factories import AlunoFactory
from processo_eletronico.models import Anexacao, DocumentoTextoProcesso, Processo, SolicitacaoJuntada, SolicitacaoJuntadaDocumento
from processo_eletronico.status import ProcessoStatus, SolicitacaoJuntadaStatus
from processo_eletronico.tests.factories import CompartilhamentoPoderChefeFactory, ProcessoFactory, TramiteFactory
from rh.models import Setor
from rh.tests.factories import ServidorFactory, SetorFactory

pytestmark = pytest.mark.django_db

PUBLICO, RESTRITO, SIGILOSO = Documento.NIVEL_ACESSO_PUBLICO, Documento.NIVEL_ACESSO_RESTRITO, Documento.NIVEL_ACESSO_SIGILOSO
RASCUNHO, FINALIZADO, CANCELADO = DocumentoStatus.STATUS_RASCUNHO, DocumentoStatus.STATUS_FINALIZADO, DocumentoStatus.STATUS_CANCELADO


def _servidor(setor: Setor, *grupos: str) -> User:
    user = ServidorFactory(setor=setor).get_user()
    for grupo in grupos:
        Group.objects.get_or_create(name=grupo)[0].user_set.add(user)
    return user


def _processo(setor: Setor, autor: User, interessado: User | None = None, nivel: int = Processo.NIVEL_ACESSO_PUBLICO) -> Processo:
    # Todo processo salvo de novo exige um interessado (sinal do NUP 17).
    processo = ProcessoFactory(setor_criacao=setor, usuario_gerador=autor, nivel_acesso=nivel)
    processo.interessados.add((interessado or autor).get_vinculo())
    return processo


def _no_processo(processo: Processo, documento: DocumentoTexto, *, removido: bool = False) -> None:
    vinculo = DocumentoTextoProcesso.objects.create(processo=processo, documento=documento)
    if removido:
        DocumentoTextoProcesso.objects.filter(pk=vinculo.pk).update(data_hora_remocao=get_datetime_now())


def _juntada_pendente(processo: Processo, documento: DocumentoTexto, solicitado: User) -> None:
    """Juntada concluída pelo solicitado e esperando a avaliação de quem tem o processo no setor."""
    tramite = TramiteFactory(processo=processo, remetente_setor=processo.setor_criacao, destinatario_setor=processo.setor_criacao)
    solicitacao = SolicitacaoJuntada.objects.create(
        tramite=tramite, solicitado=solicitado.get_vinculo(), data_limite=get_datetime_now() + timedelta(days=5)
    )
    SolicitacaoJuntada.objects.filter(pk=solicitacao.pk).update(status=SolicitacaoJuntadaStatus.STATUS_CONCLUIDO)
    SolicitacaoJuntadaDocumento.objects.create(solicitacao_juntada=solicitacao, anexo_content_object=documento)
    Processo.objects.filter(pk=processo.pk).update(
        status=ProcessoStatus.STATUS_EM_HOMOLOGACAO, setor_atual=processo.setor_criacao, ultimo_tramite=None
    )


def test_legiveis_por_espelha_pode_ler_em_cada_ramo(sync_permissions: None) -> None:
    meu_setor = SetorFactory(codigo_siorg=str(Processo.CODIGO_SIORG))
    outro_setor = SetorFactory(codigo_siorg=str(Processo.CODIGO_SIORG))
    autor = _servidor(outro_setor)
    tl.context.user = autor  # CurrentUserField dos compartilhamentos, vínculos com processo e juntadas.

    comum = _servidor(meu_setor)
    chefe = _servidor(meu_setor)
    CompartilhamentoPoderChefeFactory(setor_dono=meu_setor, vinculo_permitido=chefe.get_vinculo())
    colaborador = _servidor(meu_setor)
    CompartilhamentoSetorPessoa.objects.create(setor_dono=outro_setor, vinculo_permitido=colaborador.get_vinculo())
    auditor = _servidor(meu_setor, 'Auditor')
    procurador = _servidor(meu_setor, 'Procurador')
    sistemico = _servidor(meu_setor, 'Sistêmico de Leitura')
    aluno = AlunoFactory().get_user()
    superusuario = _servidor(meu_setor)
    User.objects.filter(pk=superusuario.pk).update(is_superuser=True)
    superusuario.refresh_from_db()

    modelo_sistemico = ModeloDocumentoFactory()
    Configuracao.objects.create(app='rh', chave='setor_procuradoria', valor=str(outro_setor.pk))
    Configuracao.objects.create(
        app='documento_eletronico',
        chave='grupossistemicos_com_perm_leitura_de_modelosdoc',
        valor=json.dumps({'Sistêmico de Leitura': [modelo_sistemico.pk]}),
    )

    def doc(nivel: int, status: int = FINALIZADO, setor: Setor = outro_setor, **kwargs: object) -> DocumentoTexto:
        return DocumentoTextoFactory(usuario_criacao=autor, setor_dono=setor, nivel_acesso=nivel, status=status, **kwargs)

    docs = {
        'publico_rascunho': doc(PUBLICO, RASCUNHO),
        'publico_finalizado': doc(PUBLICO),
        'publico_cancelado': doc(PUBLICO, CANCELADO),
        'publico_cancelado_no_processo': doc(PUBLICO, CANCELADO),
        'restrito': doc(RESTRITO),
        'restrito_rascunho': doc(RESTRITO, RASCUNHO),
        'restrito_no_processo': doc(RESTRITO),
        'restrito_removido_do_processo': doc(RESTRITO),
        'restrito_no_processo_anexado': doc(RESTRITO),
        'restrito_processo_do_aluno': doc(RESTRITO),
        'restrito_processo_privado': doc(RESTRITO),
        'restrito_juntada_pendente': doc(RESTRITO),
        'restrito_sistemico': doc(RESTRITO, modelo=modelo_sistemico),
        'restrito_compartilhado_edicao': doc(RESTRITO),
        'restrito_interessado': doc(RESTRITO),
        'restrito_assinatura_solicitada': doc(RESTRITO, DocumentoStatus.STATUS_AGUARDANDO_ASSINATURA),
        'sigiloso': doc(SIGILOSO),
        'sigiloso_compartilhado': doc(SIGILOSO),
        'restrito_do_meu_setor': doc(RESTRITO, setor=meu_setor),
        'restrito_rascunho_do_meu_setor': doc(RESTRITO, RASCUNHO, setor=meu_setor),
        'sigiloso_do_meu_setor': doc(SIGILOSO, setor=meu_setor),
        'restrito_do_aluno': DocumentoTextoFactory(usuario_criacao=aluno, setor_dono=outro_setor, nivel_acesso=RESTRITO),
    }
    pessoal = DocumentoTextoFactory(usuario_criacao=comum, nivel_acesso=PUBLICO, status=FINALIZADO)

    # Processo que está no meu setor (criado lá, sem trâmite), outro anexado a ele e um em que o aluno é interessado.
    no_meu_setor = _processo(meu_setor, autor)
    anexado = _processo(outro_setor, autor)
    Anexacao.objects.create(processo_anexador=no_meu_setor, processo_anexado=anexado, justificativa_criacao='Teste')
    _no_processo(no_meu_setor, docs['restrito_no_processo'])
    _no_processo(no_meu_setor, docs['restrito_removido_do_processo'], removido=True)
    _no_processo(no_meu_setor, docs['publico_cancelado_no_processo'], removido=True)
    _no_processo(anexado, docs['restrito_no_processo_anexado'])
    do_aluno = _processo(outro_setor, autor, interessado=aluno)
    _no_processo(do_aluno, docs['restrito_processo_do_aluno'])
    # Processo privado gerado pelo servidor comum, num setor que não é o dele e sem ele como interessado.
    _no_processo(_processo(outro_setor, comum, interessado=autor, nivel=Processo.NIVEL_ACESSO_PRIVADO), docs['restrito_processo_privado'])
    _juntada_pendente(_processo(meu_setor, autor), docs['restrito_juntada_pendente'], autor)

    for documento, nivel in (('sigiloso_compartilhado', NivelPermissao.LER), ('restrito_compartilhado_edicao', NivelPermissao.EDITAR)):
        CompartilhamentoDocumentoPessoa.objects.create(documento=docs[documento], vinculo_permitido=comum.get_vinculo(), nivel_permissao=nivel)
    docs['restrito_interessado'].interessados.add(comum.get_vinculo())
    SolicitacaoAssinaturaFactory(
        documento=docs['restrito_assinatura_solicitada'], solicitante=autor, solicitado=comum.get_vinculo(), status=SolicitacaoStatus.STATUS_ESPERANDO
    )
    assert SolicitacaoAssinatura.objects.filter(solicitado=comum.get_vinculo()).exists()
    tl.context.user = None
    # Setores de trâmite (get_todos_setores) e configurações ficam em cache; aqui o cenário já está completo.
    cache.clear()

    usuarios = {
        'autor': autor,
        'comum': comum,
        'chefe': chefe,
        'colaborador': colaborador,
        'auditor': auditor,
        'procurador': procurador,
        'sistemico': sistemico,
        'aluno': aluno,
        'superusuario': superusuario,
    }
    legiveis = {}
    for papel, user in usuarios.items():
        filtrados = set(DocumentoTexto.objects.legiveis_por(user))
        esperados = {d for d in [*docs.values(), pessoal] if d.pode_ler(user) and d.setor_dono_id}
        assert filtrados == esperados, (
            f'{papel}: só no filtro {sorted(_nomes(docs, filtrados - esperados))}, só no pode_ler {sorted(_nomes(docs, esperados - filtrados))}'
        )
        legiveis[papel] = _nomes(docs, filtrados)

    # O cenário exercita cada ramo: as âncoras abaixo falham se um deles deixar de ser coberto.
    assert pessoal not in DocumentoTexto.objects.legiveis_por(comum)  # pessoal tem outra regra; a listagem é de setor
    assert legiveis['comum'] >= {'publico_finalizado', 'sigiloso_compartilhado', 'restrito_compartilhado_edicao', 'restrito_processo_privado'}
    assert not legiveis['comum'] & {'restrito', 'sigiloso', 'restrito_do_meu_setor', 'restrito_interessado', 'restrito_assinatura_solicitada'}
    assert legiveis['chefe'] >= {
        'restrito_do_meu_setor',
        'restrito_rascunho_do_meu_setor',
        'restrito_no_processo',
        'restrito_no_processo_anexado',
        'restrito_juntada_pendente',
    }
    assert not legiveis['chefe'] & {'sigiloso_do_meu_setor', 'restrito_removido_do_processo', 'publico_cancelado', 'restrito'}
    assert 'publico_cancelado_no_processo' in legiveis['chefe']
    assert legiveis['colaborador'] >= {'restrito', 'restrito_rascunho', 'publico_rascunho'}
    assert 'sigiloso' not in legiveis['colaborador']
    assert legiveis['auditor'] >= {'restrito', 'sigiloso', 'publico_cancelado'}
    assert not legiveis['auditor'] & {'restrito_rascunho', 'restrito_do_meu_setor'}
    assert legiveis['procurador'] >= {'restrito_do_meu_setor', 'sigiloso_do_meu_setor'}
    assert 'restrito' not in legiveis['procurador']
    assert 'restrito_sistemico' in legiveis['sistemico']
    # Sem a permissão view_documentotexto (o grupo de aluno só vem no login), o aluno não lê nem o que criou: só o
    # que o processo libera.
    assert legiveis['aluno'] == {'restrito_processo_do_aluno'}
    assert 'sigiloso' not in legiveis['superusuario']
    assert legiveis['autor'] == set(docs) - {'restrito_do_aluno'}


def _nomes(docs: dict[str, DocumentoTexto], documentos: set[DocumentoTexto]) -> set[str]:
    return {nome for nome, documento in docs.items() if documento in documentos}
