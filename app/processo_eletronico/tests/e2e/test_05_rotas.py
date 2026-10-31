"""Smoke das rotas do Processo Eletrônico que os fluxos não declaram (modo 2).

O gate ``bin/scripts/paridade_e2e.py processo_eletronico --rotas`` lê **literais**: as rotas que os
fluxos alcançam por clique não aparecem para ele. Aqui cada uma entra como URL com o literal
presente e a asserção é o **status do contrato** — ``200`` para a tela que renderiza, ``302``
para a view que redireciona ou delega a uma task, ``403`` para a barreira de
permissão/estado e ``404`` para o ``get_object_or_404`` de um id inexistente. A mensagem de
falha carrega o motivo, então quando a rota quebra o relatório diz qual fronteira caiu.

Os ids vêm da fixture ``alvos``, que usa os processos fixos do seed, o trâmite que o
``estado_processo`` recria antes de cada teste, o ``Documento Teste`` do seed e as solicitações de
despacho/ciência criadas pelas fixtures importadas de ``test_03``.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

ALVOS = (
    'processo',
    'processo_relacionado',
    'processo_uuid',
    'tramite',
    'tramite_uuid',
    'documento',
    'setor',
    'username',
    'solicitacao_despacho',
    'solicitacao_ciencia',
    'tipo_processo',
)


def _pendencia_despacho(processo, django_db_blocker):
    """Cria uma solicitação de despacho pendente **no processo 2**.

    No processo 1 ela bloquearia ``pode_editar``/``pode_ser_encaminhado``
    (``possui_pendencias_documentais``) e derrubaria os casos de edição do smoke.
    """
    from processo_eletronico.models import SolicitacaoDespacho
    from rh.models import Setor

    with django_db_blocker.unblock():
        SolicitacaoDespacho.objects.filter(processo=processo).delete()
        return SolicitacaoDespacho.objects.create(
            processo=processo,
            despacho_corpo='Despacho criado pela massa e2e.',
            remetente_setor=Setor.objects.suap().get(sigla='A1'),
            remetente_vinculo=_vinculo('128002'),
            solicitado=_vinculo('128001'),
            destinatario_setor_tramite=Setor.objects.suap().get(sigla='A2'),
        )


def _ciencia_pendente(processo, django_db_blocker):
    """Cria uma ciência pendente no processo 1 (não conta como pendência de edição)."""
    from django.utils.timezone import now

    from processo_eletronico.models import SolicitacaoCiencia

    with django_db_blocker.unblock():
        SolicitacaoCiencia.objects.filter(processo=processo).delete()
        return SolicitacaoCiencia.objects.create(
            processo=processo,
            tramite=processo.ultimo_tramite,
            solicitante=_usuario('128002'),
            solicitado=_vinculo('128003'),
            data_limite_ciencia=now() + timedelta(days=30),
            motivo='Solicitação criada pela massa e2e.',
            tipo=SolicitacaoCiencia.TIPO_NOTIFICACAO,
        )


def _vinculo(matricula: str):
    from rh.models import Servidor

    return Servidor.objects.get(matricula=matricula).get_vinculo()


def _usuario(matricula: str):
    from rh.models import Servidor

    return Servidor.objects.get(matricula=matricula).get_user()


@pytest.fixture
def alvos(processo_seed: bool, operador_a_habilitado: None, django_db_blocker) -> dict[str, str]:
    """Ids reais para o smoke, depois do ``estado_processo`` recriar o trâmite do A2 para o A1."""
    from documento_eletronico.models import DocumentoTexto
    from processo_eletronico.models import Processo, SolicitacaoDespacho, TipoProcesso
    from documento_eletronico.status import SolicitacaoStatus
    from rh.models import Setor

    p1 = Processo.objects.get(numero_protocolo='23001.000001.2019-68')
    p2 = Processo.objects.get(numero_protocolo='23001.000002.2019-11')
    with django_db_blocker.unblock():
        # Pendências que os fluxos deixam no processo 1 impedem editar/encaminhar; o smoke as remove.
        SolicitacaoDespacho.objects.filter(processo=p1, status=SolicitacaoStatus.STATUS_ESPERANDO).delete()
    documento = DocumentoTexto.objects.get(assunto='Documento Teste')
    setor = Setor.objects.suap().get(sigla='A1')
    tipo = TipoProcesso.objects.get(nome='Acesso à Informação: Demanda do e-SIC')
    return {
        'processo': str(p1.pk),
        'processo_relacionado': str(p2.pk),
        'processo_uuid': str(p1.uuid),
        'tramite': str(p1.ultimo_tramite.pk),
        'tramite_uuid': str(p1.ultimo_tramite.uuid),
        'documento': str(documento.pk),
        'setor': str(setor.pk),
        'username': '128001',
        'solicitacao_despacho': str(_pendencia_despacho(p2, django_db_blocker).pk),
        'solicitacao_ciencia': str(_ciencia_pendente(p1, django_db_blocker).pk),
        'tipo_processo': str(tipo.pk),
    }


# (papel, rota, status esperado, motivo do status). A rota entra como literal com os
# placeholders das chaves de ``alvos``; o motivo fica na mensagem de falha.
CASOS: list[tuple[str, str, int, str]] = [
    ('admin', '/processo_eletronico/processo/{processo}/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    (
        'admin',
        '/processo_eletronico/processo/numero/23001.000001.2019-68/',
        404,
        'o seed grava o NUP formatado e a view só aceita 17/21 dígitos sem formatação: responde 404 (achado do MR).',
    ),
    ('admin', '/processo_eletronico/busca_processo/', 302, 'sem ``q`` na query, redireciona para a busca do admin com ``q=None``.'),
    ('operador_a', '/processo_eletronico/processo/editar_interessados/{processo}/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    ('admin', '/processo_eletronico/processo/registro_acoes_processo/{processo}/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    ('operador_a', '/processo_eletronico/processo/finalizar/{processo}/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    (
        'admin',
        '/processo_eletronico/processo/desfinalizar/{processo}/',
        403,
        '``pode_desfinalizar`` nega todos os papéis do smoke com o processo do seed.',
    ),
    (
        'admin',
        '/processo_eletronico/processo/documento/ver_justificativa_remocao/99999999/',
        404,
        'id inexistente no seed: ``get_object_or_404`` responde 404.',
    ),
    ('operador_a', '/processo_eletronico/anexar_processos/{processo}/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    ('operador_a', '/processo_eletronico/apensar_processos/{processo}/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    ('admin', '/processo_eletronico/processo/visualizar_minuta/99999999/', 404, 'id inexistente no seed: ``get_object_or_404`` responde 404.'),
    ('admin', '/processo_eletronico/processo/conteudo_minuta/99999999/', 404, 'id inexistente no seed: ``get_object_or_404`` responde 404.'),
    ('admin', '/processo_eletronico/processo/conteudo_minuta/{processo_uuid}/', 404, 'id inexistente no seed: ``get_object_or_404`` responde 404.'),
    ('admin', '/processo_eletronico/clonar_minuta_em_documento/99999999/', 404, 'id inexistente no seed: ``get_object_or_404`` responde 404.'),
    (
        'admin',
        '/processo_eletronico/processo/documento_digitalizado_editar/99999999/',
        404,
        'id inexistente no seed: ``get_object_or_404`` responde 404.',
    ),
    ('operador_a', '/processo_eletronico/desapensar_processo/{processo}/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    ('admin', '/processo_eletronico/desapensar_todos_processos/99999999/', 404, 'id inexistente no seed: ``get_object_or_404`` responde 404.'),
    ('admin', '/processo_eletronico/imprimir_processo/{processo}/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    ('admin', '/processo_eletronico/baixar_processo_zip/{processo}/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    (
        'admin',
        '/processo_eletronico/imprimir_processo_celery/{processo_uuid}/',
        302,
        'delega a impressão a task e redireciona para a página de processamento do djtools.',
    ),
    (
        'admin',
        '/processo_eletronico/baixar_processo_zip_celery/{processo_uuid}/',
        302,
        'delega o ZIP a task e redireciona para a página de processamento do djtools.',
    ),
    (
        'admin',
        '/processo_eletronico/tipo_processo_classificacoes_nivel_acesso_padrao/{tipo_processo}/',
        200,
        'endpoint auxiliar do tipo de processo do seed responde 200.',
    ),
    ('operador_a', '/processo_eletronico/adicionar_comentario/{processo}/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    ('operador_a', '/processo_eletronico/listar_processos_relacionado/{processo}/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    ('operador_a', '/processo_eletronico/alterar_nivel_acesso_processo/{processo}/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    (
        'operador_a',
        '/processo_eletronico/distribuicao_interna_processos_setor/{setor}/',
        200,
        'a tela responde 200 com o processo/documento do seed.',
    ),
    ('operador_a', '/processo_eletronico/dashboard_processos/{setor}/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    ('admin', '/processo_eletronico/tramite/visualizar/{tramite}/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    (
        'admin',
        '/processo_eletronico/tramite/verificar_integridade/{tramite}/',
        302,
        'sem assinatura a conferir, redireciona para a aba de documentos do processo.',
    ),
    ('operador_a', '/processo_eletronico/caixa_processos/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    ('operador_a', '/processo_eletronico/selecao_caixa_processos/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    ('operador_a', '/processo_eletronico/processo/encaminhar_sem_despacho/{processo}/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    ('operador_a', '/processo_eletronico/processo/encaminhar/{processo}/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    ('operador_a', '/processo_eletronico/processo/encaminhar_lote/{processo}/', 200, 'formulário de encaminhamento em lote para o processo do seed.'),
    ('operador_a', '/processo_eletronico/adicionar_prioridade/{processo}/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    ('operador_a', '/processo_eletronico/adicionar_rotulo/{tramite}/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    ('chefe_a', '/processo_eletronico/atribuir_processo/{tramite}/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    ('admin', '/processo_eletronico/movimentacao_interna_processo/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    (
        'admin',
        '/processo_eletronico/tramite/recibo_envio_conectagov/{tramite}/',
        404,
        'trâmite do seed não tem integração ConectaGov: ``Http404`` (era 500 — corrigido no MR).',
    ),
    (
        'admin',
        '/processo_eletronico/tramite/recibo_conclusao_conectagov/{tramite}/',
        404,
        'trâmite do seed não tem integração ConectaGov: ``Http404`` (era 500 — corrigido no MR).',
    ),
    (
        'admin',
        '/processo_eletronico/processo/encaminhar_externamente/{processo}/',
        403,
        'exige ``conectagov_pen.pode_tramitar_pelo_barramento`` e barramento disponível.',
    ),
    (
        'admin',
        '/processo_eletronico/processo/reativar_processo_encaminhado_externamente/{processo}/',
        302,
        'processo não está encaminhado externamente: redireciona de volta com erro.',
    ),
    (
        'admin',
        '/processo_eletronico/documento_texto_processo/verificar_integridade/99999999/',
        404,
        'id inexistente no seed: ``get_object_or_404`` responde 404.',
    ),
    (
        'admin',
        '/processo_eletronico/documento_texto_processo/remover_documento/99999999/',
        404,
        'id inexistente no seed: ``get_object_or_404`` responde 404.',
    ),
    ('operador_a', '/processo_eletronico/listar_documentos_adicionar/{processo}/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    (
        'admin',
        '/processo_eletronico/documento_digitalizado_processo/verificar_integridade/99999999/',
        404,
        'id inexistente no seed: ``get_object_or_404`` responde 404.',
    ),
    (
        'admin',
        '/processo_eletronico/documento_digitalizado_processo/remover_documento/99999999/',
        404,
        'id inexistente no seed: ``get_object_or_404`` responde 404.',
    ),
    (
        'operador_a',
        '/processo_eletronico/adicionar_minuta/{documento}/processo/{processo}/',
        200,
        'a tela responde 200 com o processo/documento do seed.',
    ),
    ('admin', '/processo_eletronico/remover_minuta_processo/99999999/', 404, 'id inexistente no seed: ``get_object_or_404`` responde 404.'),
    ('admin', '/processo_eletronico/imprimir_minuta_pdf/99999999/99999999/', 404, 'id inexistente no seed: ``get_object_or_404`` responde 404.'),
    ('operador_a', '/processo_eletronico/listar_minutas_adicionar/{processo}/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    (
        'admin',
        '/processo_eletronico/processo/minuta/ver_justificativa_remocao_minuta/99999999/',
        404,
        'id inexistente no seed: ``get_object_or_404`` responde 404.',
    ),
    ('operador_a', '/processo_eletronico/solicitar_ciencia/{processo}/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    (
        'admin',
        '/processo_eletronico/dar_ciencia/{processo}/',
        403,
        'exige ciência pendente para o vínculo; o seed não cria solicitação de ciência para os papéis.',
    ),
    (
        'operador_a',
        '/processo_eletronico/cancelar_solicitacao_ciencia/{solicitacao_ciencia}/',
        200,
        'ciência pendente criada pela fixture: o solicitado abre o formulário de cancelamento.',
    ),
    ('admin', '/processo_eletronico/requerimento_pdf/{processo}/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    ('operador_a', '/processo_eletronico/solicitar_despacho/{processo}/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    (
        'chefe_a',
        '/processo_eletronico/solicitar_despacho/visualizar/{solicitacao_despacho}/',
        200,
        'solicitação de despacho pendente criada pela fixture.',
    ),
    (
        'chefe_a',
        '/processo_eletronico/solicitar_despacho/editar/{solicitacao_despacho}/',
        200,
        'remetente da solicitação pendente abre o formulário de edição.',
    ),
    (
        'operador_a',
        '/processo_eletronico/solicitar_despacho/deferir/{solicitacao_despacho}/',
        200,
        'solicitado abre o formulário de deferimento da solicitação pendente.',
    ),
    (
        'operador_a',
        '/processo_eletronico/solicitar_despacho/indeferir/{solicitacao_despacho}/',
        200,
        'solicitado abre o formulário de indeferimento da solicitação pendente.',
    ),
    ('chefe_a', '/processo_eletronico/solicitar_despacho/conteudo/{solicitacao_despacho}/', 200, 'conteúdo da solicitação de despacho pendente.'),
    (
        'admin',
        '/processo_eletronico/criar_processo_documento/{documento}/',
        302,
        'redireciona para o formulário de criação de processo já com o documento do seed.',
    ),
    ('admin', '/processo_eletronico/incluir_documento_processo/{documento}/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    ('admin', '/processo_eletronico/cadastrar_requerimento/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    (
        'admin',
        '/processo_eletronico/editar_requerimento/99999999/',
        403,
        '``Requerimento.get_requerimento_by_user`` não acha o requerimento: ``PermissionDenied``.',
    ),
    (
        'admin',
        '/processo_eletronico/finalizar_requerimento/99999999/',
        403,
        '``Requerimento.get_requerimento_by_user`` não acha o requerimento: ``PermissionDenied``.',
    ),
    (
        'admin',
        '/processo_eletronico/listar_documentos_adicionar_requerimento/99999999/',
        403,
        'requerimento inexistente: a view nega antes de listar.',
    ),
    (
        'admin',
        '/processo_eletronico/documento_texto_processo_requerimento/verificar_integridade/99999999/',
        404,
        'id inexistente no seed: ``get_object_or_404`` responde 404.',
    ),
    (
        'admin',
        '/processo_eletronico/adicionar_documento_upload_requerimento/99999999/',
        403,
        'requerimento inexistente: a view nega antes de abrir o formulário.',
    ),
    (
        'admin',
        '/processo_eletronico/editar_documento_upload_requerimento/99999999/',
        404,
        'id inexistente no seed: ``get_object_or_404`` responde 404.',
    ),
    (
        'admin',
        '/processo_eletronico/visualizar_documento_requerimento_pdf/99999999/99999999/',
        404,
        'id inexistente no seed: ``get_object_or_404`` responde 404.',
    ),
    (
        'admin',
        '/processo_eletronico/gerenciar_requerimento/99999999/',
        403,
        '``Requerimento.get_requerimento_by_user`` não acha o requerimento: ``PermissionDenied``.',
    ),
    (
        'admin',
        '/processo_eletronico/gerenciar_requerimento/99999999/modo/99999999/',
        403,
        '``Requerimento.get_requerimento_by_user`` não acha o requerimento: ``PermissionDenied``.',
    ),
    ('operador_a', '/processo_eletronico/enviar_pedido_juntada/{processo}/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    ('admin', '/processo_eletronico/listar_documentos_juntar/99999999/', 404, 'id inexistente no seed: ``get_object_or_404`` responde 404.'),
    (
        'admin',
        '/processo_eletronico/solicitar_juntada_documento_interno/99999999/{documento}/',
        404,
        'id inexistente no seed: ``get_object_or_404`` responde 404.',
    ),
    (
        'admin',
        '/processo_eletronico/solicitar_juntada_documento_externo/99999999/',
        404,
        'id inexistente no seed: ``get_object_or_404`` responde 404.',
    ),
    ('admin', '/processo_eletronico/concluir_juntada_documento/99999999/', 404, 'id inexistente no seed: ``get_object_or_404`` responde 404.'),
    ('admin', '/processo_eletronico/deferir_solicitacao_juntada/99999999/', 404, 'id inexistente no seed: ``get_object_or_404`` responde 404.'),
    ('admin', '/processo_eletronico/indeferir_solicitacao_juntada/99999999/', 404, 'id inexistente no seed: ``get_object_or_404`` responde 404.'),
    (
        'admin',
        '/processo_eletronico/avaliar_solicitacao_juntada_documento/99999999/',
        404,
        'id inexistente no seed: ``get_object_or_404`` responde 404.',
    ),
    ('admin', '/processo_eletronico/cancelar_solicitacao_documento/99999999/', 404, 'id inexistente no seed: ``get_object_or_404`` responde 404.'),
    ('admin', '/processo_eletronico/processo_eletronico_manutencao/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    ('admin', '/processo_eletronico/processo_eletronico_manutencao_altera_status/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    (
        'admin',
        '/processo_eletronico/processo_eletronico_numeros/',
        200,
        'superusuário pode consultar os indicadores de processos de todos os setores.',
    ),
    ('admin', '/processo_eletronico/consulta_publica/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    ('chefe_a', '/processo_eletronico/permissoes/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    (
        'chefe_a',
        '/processo_eletronico/gerenciar_compartilhamento_processos_poder_de_chefe/',
        200,
        'a tela responde 200 com o processo/documento do seed.',
    ),
    (
        'admin',
        '/processo_eletronico/get_hipoteses_legais_by_processo_nivel_acesso/99999999/',
        200,
        'a tela responde 200 com o processo/documento do seed.',
    ),
    ('admin', '/processo_eletronico/visualizar_capa_processo/{processo}/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    ('admin', '/processo_eletronico/visualizar_requerimento_processo/{processo}/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    ('admin', '/processo_eletronico/permissoes_processos_documentos/{username}/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    ('admin', '/processo_eletronico/permissoes_processos_documentos/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    ('admin', '/processo_eletronico/permissoes_processos_documentos/nao-existe/', 404, 'username inexistente responde 404 (era 500)'),
    ('admin', '/processo_eletronico/configurar_orientacao_nivel_acesso/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    (
        'admin',
        '/processo_eletronico/solicita_alteracao_nivel_acesso/documentodigitalizado/{documento}/',
        200,
        'a tela responde 200 com o processo/documento do seed.',
    ),
    (
        'admin',
        '/processo_eletronico/solicita_alteracao_nivel_acesso/documentotexto/{documento}/',
        200,
        'a tela responde 200 com o processo/documento do seed.',
    ),
    (
        'admin',
        '/processo_eletronico/solicita_alteracao_nivel_acesso/processo/{processo}/',
        200,
        'a tela responde 200 com o processo/documento do seed.',
    ),
    (
        'admin',
        '/processo_eletronico/analisar_solicitacao_alteracao_nivel_acesso/99999999/',
        404,
        'id inexistente no seed: ``get_object_or_404`` responde 404.',
    ),
    (
        'admin',
        '/processo_eletronico/indeferir_solicitacao_alteracao_nivel_acesso/99999999/',
        404,
        'id inexistente no seed: ``get_object_or_404`` responde 404.',
    ),
    (
        'operador_b',
        '/processo_eletronico/solicitacoes_alteracao_nivel_acesso_documento/{documento}/',
        200,
        'a tela responde 200 com o processo/documento do seed.',
    ),
    (
        'admin',
        '/processo_eletronico/solicitacoes_alteracao_nivel_acesso_processo/{processo}/',
        200,
        'a tela responde 200 com o processo/documento do seed.',
    ),
    ('admin', '/processo_eletronico/visualizar_processo/{processo}/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    ('admin', '/processo_eletronico/visualizar_processo/{processo_uuid}/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    ('admin', '/processo_eletronico/visualizar_capa_processo/{processo_uuid}/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    ('admin', '/processo_eletronico/tramite/conteudo/{tramite}/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    ('admin', '/processo_eletronico/tramite/conteudo/{tramite_uuid}/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    ('operador_a', '/processo_eletronico/processo_editar_assunto/{processo}/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    ('admin', '/processo_eletronico/linha_tempo/{processo}/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    ('admin', '/processo_eletronico/rotulos/{setor}/', 200, 'a tela responde 200 com o processo/documento do seed.'),
    (
        'admin',
        '/processo_eletronico/imprimir_etiqueta/{processo}/',
        403,
        'a configuração ``habilitar_impressao_etiqueta`` está desligada: ``PermissionDenied``.',
    ),
    ('operador_a', '/processo_eletronico/documento_upload/{processo}/', 200, 'formulário de upload de documento externo no processo do seed.'),
]


@pytest.mark.parametrize(('papel', 'rota', 'status_esperado', 'motivo'), CASOS, ids=[caso[1] for caso in CASOS])
def test_rota_responde_como_esperado(
    logado_processo_eletronico: Any, alvos: dict[str, str], papel: str, rota: str, status_esperado: int, motivo: str
) -> None:
    """Cada rota responde o status do contrato, com o papel de maior alcance para ela."""
    resposta = Tela(logado_processo_eletronico(papel)).buscar(rota.format(**alvos))
    assert resposta.status == status_esperado, f'{rota} respondeu HTTP {resposta.status} (esperado {status_esperado}: {motivo})'
