from __future__ import annotations

import json
import operator
from collections.abc import Iterable
from functools import cached_property, reduce
from typing import TYPE_CHECKING

from django.apps import apps
from django.conf import settings
from django.db import models
from django.db.models.query_utils import Q

from documento_eletronico.status import DocumentoStatus, SolicitacaoStatus
from processo_eletronico.utils import setores_que_sou_chefe_ou_tenho_poder_de_chefe

if TYPE_CHECKING:
    from comum.models import User


class PodemClassificarManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(suficiente_para_classificar_processo=True)


class SolicitacaoAssinaturaManager(models.Manager):
    def filter_assinatura_pendente(self, vinculo):
        # Trazendo todas as solicitações para determinado vinculo.
        if not vinculo:
            return self.get_queryset().none()
        solicitacoes = self.get_queryset().filter(solicitado_id=vinculo.id, status=SolicitacaoStatus.STATUS_ESPERANDO)
        qs_filter = [Q(condicionantes__status=SolicitacaoStatus.STATUS_DEFERIDA), Q(condicionantes__isnull=True)]
        solicitacoes = solicitacoes.filter(reduce(operator.or_, qs_filter))
        return solicitacoes

    def filter_requisicao_pendente(self, user):
        return self.get_queryset().filter(solicitante_id=user.id, status=SolicitacaoStatus.STATUS_ESPERANDO)


class SolicitacaoRevisorManager(models.Manager):
    def filter_revisao_pendente(self, vinculo):
        return self.get_queryset().filter(revisor_id=vinculo.id, data_resposta__isnull=True)

    def filter_requisicao_pendente(self, user):
        return self.get_queryset().filter(solicitante_id=user.id, data_resposta__isnull=True)

    def filter_revisados(self, user):
        return self.get_queryset().filter(solicitante_id=user.id, data_resposta__isnull=False, status=SolicitacaoStatus.STATUS_DEFERIDA)


class DocumentoTextoQueryset(models.query.QuerySet):
    def get_model(self):
        return apps.get_model('documento_eletronico', 'DocumentoTexto')

    def pessoais(self):
        return self.filter(setor_dono__isnull=True)

    def impessoais(self):
        return self.filter(setor_dono__isnull=False)

    """
    Documentos Assinados pelo usuário
    """

    def assinados(self, user):
        vinculo_id = user.get_vinculo()
        return self.filter(assinaturadocumentotexto__assinatura__vinculo_id=vinculo_id)

    """
    Documentos Compartilhados com o usuário ou com os setores do usuário
    """

    def q_compartilhados(self, user, nivel_permissao=None):
        """Monta filtros ``Q`` para documentos compartilhados com ``user``.

        Combina compartilhamentos diretos por vínculo e compartilhamentos por
        setor (do qual o usuário é chefe, tem poder de chefe ou ganhou acesso
        via ``CompartilhamentoSetorPessoa``), respeitando ``nivel_permissao``
        e excluindo documentos sigilosos do caminho por setor. Cacheia os ids
        de setores no objeto ``user`` por requisição.

        Args:
            user: usuário logado cujo acesso será considerado.
            nivel_permissao: opcional; quando informado, restringe ao nível
                (``LER`` permite ler+editar; demais valores filtram pelo nível exato).

        Returns:
            list[Q]: dois objetos ``Q`` (compartilhamento por pessoa e por setor)
            prontos para uso em ``Documento.objects.filter``.
        """
        from documento_eletronico.models import CompartilhamentoSetorPessoa, NivelPermissao

        Documento = self.get_model()

        # Recupera a pessoa física
        vinculo_id = user.get_vinculo().id

        # Cache request-scoped: ids de setores/compartilhamentos só dependem do user/nivel.
        cache_attr = f'_q_compartilhados_ids_{nivel_permissao or "all"}'
        cached = getattr(user, cache_attr, None)
        if cached is None:
            meus_setores_chefe_poder_chefe = list(setores_que_sou_chefe_ou_tenho_poder_de_chefe(user).values_list('id', flat=True))
            setores_compartilhados_pessoa_qs = CompartilhamentoSetorPessoa.objects.filter(vinculo_permitido_id=vinculo_id)
            if nivel_permissao and nivel_permissao == NivelPermissao.EDITAR:
                setores_compartilhados_pessoa_qs = CompartilhamentoSetorPessoa.objects.filter(
                    vinculo_permitido_id=vinculo_id, nivel_permissao=nivel_permissao
                )
            setores_compartilhados_pessoa = list(setores_compartilhados_pessoa_qs.values_list('setor_dono_id', flat=True))
            cached = meus_setores_chefe_poder_chefe + setores_compartilhados_pessoa
            setattr(user, cache_attr, cached)
        todos_setores = cached
        # Recuperar todos os documentos compartilhados com o usuário
        if nivel_permissao and nivel_permissao == NivelPermissao.LER:
            query_documento_pessoa_compartilhada = Q(compartilhamento_pessoa_documento__vinculo_permitido_id=vinculo_id) & (
                Q(compartilhamento_pessoa_documento__nivel_permissao=NivelPermissao.LER)
                | Q(compartilhamento_pessoa_documento__nivel_permissao=NivelPermissao.EDITAR)
            )
        elif nivel_permissao:
            query_documento_pessoa_compartilhada = Q(
                compartilhamento_pessoa_documento__vinculo_permitido_id=vinculo_id, compartilhamento_pessoa_documento__nivel_permissao=nivel_permissao
            )
        else:
            query_documento_pessoa_compartilhada = Q(compartilhamento_pessoa_documento__vinculo_permitido_id=vinculo_id)

        query_setor_compartilhamento = Q(setor_dono_id__in=todos_setores)

        query_sigilo = Q(nivel_acesso=Documento.NIVEL_ACESSO_SIGILOSO)
        query_compartilhamento_documento_nao_sigiloso = Q(~query_sigilo & (query_setor_compartilhamento))
        return [query_documento_pessoa_compartilhada, query_compartilhamento_documento_nao_sigiloso]

    def compartilhados(self, user, nivel_permissao=None):
        qlist = self.q_compartilhados(user, nivel_permissao)
        queryset = reduce(operator.or_, qlist)
        return self.filter(queryset).distinct()

    def vinculados_a_mim(self, user):
        vinculo_id = user.get_vinculo().id
        return self.model.objects.filter(interessados__id=vinculo_id)

    """
    Documentos que o usuário é o dono
    """

    def q_proprios(self, user):
        query_dono = Q(usuario_criacao=user)
        # Foi retirado esse trecho pq o query compartilhados ja faz a busca nos setores que ele tem Poder de chefe
        # e o poder de chefe é adicionado toda vez que altera a função do servidor
        # Documento = self.get_model()
        # query_sigilo = Q(nivel_acesso=Documento.NIVEL_ACESSO_SIGILOSO)
        # setores = get_setores_que_sou_chefe_hoje(user)
        # query_setor_dono = Q(setor_dono__in=setores)
        # query_setor = Q(~query_sigilo & query_setor_dono)
        # return [query_dono, query_setor]
        return [query_dono]

    def proprios(self, user):
        return self.filter(reduce(operator.or_, self.q_proprios(user))).distinct()

    """
        Documentos que o usuário é o dono
    """

    def q_publicos_assinados(self):
        Documento = self.get_model()
        query_publico = Q(nivel_acesso=Documento.NIVEL_ACESSO_PUBLICO)
        query_finalizado = Q(status=DocumentoStatus.STATUS_FINALIZADO)
        query_publico_assinado = Q(query_publico & query_finalizado)
        return [query_publico_assinado]

    def publicos_assinados(self):
        return self.filter(reduce(operator.or_, self.q_publicos_assinados())).distinct()

    def q_revisao_pendente(self, user):
        query_revisao_pendente = Q(solicitacaorevisao__revisor_id=user.get_vinculo().id) & Q(solicitacaorevisao__data_resposta__isnull=True)
        return [query_revisao_pendente]

    def revisao_pendente(self, user):
        return self.filter(reduce(operator.or_, self.q_revisao_pendente(user)))

    def q_requisicao_pendente(self, user):
        query_requisicao_pendente = Q(solicitacaorevisao__solicitante_id=user.id) & Q(solicitacaorevisao__data_resposta__isnull=True)
        return [query_requisicao_pendente]

    def requisicao_pendente(self, user):
        return self.filter(reduce(operator.or_, self.q_requisicao_pendente(user)))

    def q_revisados_por(self, user):
        query_revisados = (
            Q(solicitacaorevisao__revisor_id=user.get_vinculo().id)
            & Q(solicitacaorevisao__data_resposta__isnull=False)
            & Q(solicitacaorevisao__status=SolicitacaoStatus.STATUS_DEFERIDA)
        )
        return [query_revisados]

    def revisados_por(self, user):
        return self.filter(reduce(operator.or_, self.q_revisados_por(user)))

    def q_esperando_assinatura(self, user: User) -> list[Q]:
        # Materializa os ids dos documentos pendentes (consulta indexada por solicitado_id) e filtra por literais.
        # Com JOIN ou subquery, a listagem passa de 8 relações (join_collapse_limit) e o planner de produção montava
        # um hash paralelo do documentotexto inteiro antes do semi join (#17687). Sem pendências, a lista vazia vira
        # EmptyResultSet: nenhuma consulta de documentos, e no OR do by_user() só este ramo cai.
        SolicitacaoAssinatura = apps.get_model('documento_eletronico', 'SolicitacaoAssinatura')
        solicitacoes = SolicitacaoAssinatura.objects.filter_assinatura_pendente(user.get_vinculo())
        return [Q(pk__in=list(solicitacoes.values_list('documento_id', flat=True)))]

    def esperando_assinatura(self, user):
        return self.filter(reduce(operator.or_, self.q_esperando_assinatura(user)))

    def q_assinatura_requisitada_por(self, user):
        query_assinatura_requisitada_por = Q(solicitacaoassinatura__solicitante_id=user) & Q(solicitacaoassinatura__data_resposta__isnull=True)
        return [query_assinatura_requisitada_por]

    def assinatura_requisitada_por(self, user):
        return self.filter(reduce(operator.or_, self.q_assinatura_requisitada_por(user)))

    def by_user(self, user):
        return self.filter(
            reduce(
                operator.or_,
                self.q_proprios(user)
                + self.q_compartilhados(user)
                + self.q_publicos_assinados()
                + self.q_revisao_pendente(user)
                + self.q_revisados_por(user)
                + self.q_revisao_pendente(user)
                + self.q_assinatura_requisitada_por(user)
                + self.q_esperando_assinatura(user),
            )
        ).distinct()

    def legiveis_por(self, user: User) -> DocumentoTextoQueryset:
        """Documentos de setor que ``user`` pode ler: a regra de ``DocumentoTexto.pode_ler`` expressa como filtro (#17699).

        Espelha, ramo a ramo, ``tem_permissao_ler`` para documento de setor e ``acesso_ao_documento_em_funcao_cargo``
        (``documento_eletronico/utils.py``); mudou uma, mude a outra. Só cobre documentos de setor, então aplica
        ``impessoais()``: o documento pessoal tem outra regra.

        Entra no ``COUNT`` da listagem do admin, sobre o ``documentotexto`` inteiro (incidente #17674): cada ramo é um
        filtro sobre colunas do próprio documento, com os ids do usuário materializados antes em consultas pequenas e
        indexadas. Nada de join nem de subquery na consulta dos documentos.
        """
        Documento = self.get_model()
        restrito = Q(nivel_acesso=Documento.NIVEL_ACESSO_RESTRITO)
        publico_cancelado = Q(nivel_acesso=Documento.NIVEL_ACESSO_PUBLICO, status=DocumentoStatus.STATUS_CANCELADO)
        processos = _ProcessosDoUsuario(user)
        ramos = [
            self._q_leitura_natural(user),
            _e(
                restrito,
                _ou(
                    processos.q_documentos(True, documento__nivel_acesso=Documento.NIVEL_ACESSO_RESTRITO),
                    _q_juntada_pendente(user, processos),
                    _q_restritos_sistemicos(user),
                ),
            ),
            _e(
                publico_cancelado,
                processos.q_documentos(
                    False, documento__nivel_acesso=Documento.NIVEL_ACESSO_PUBLICO, documento__status=DocumentoStatus.STATUS_CANCELADO
                ),
            ),
            _q_acesso_por_cargo(user),
        ]
        return self.impessoais().filter(_ou(*ramos) or Q(pk__in=[]))

    def _q_leitura_natural(self, user: User) -> Q | None:
        """Permissão "natural" de ``tem_permissao_ler``: autor, público finalizado, compartilhado com a pessoa ou o setor."""
        from documento_eletronico.models import CompartilhamentoDocumentoPessoa, NivelPermissao

        if not user.has_perm('documento_eletronico.view_documentotexto'):
            return None
        Documento = self.get_model()
        # O compartilhamento com a pessoa de q_compartilhados é join reverso (por isso o distinct de compartilhados()):
        # aqui vira ids materializados. O do setor já é filtro por literais.
        compartilhados_comigo = CompartilhamentoDocumentoPessoa.objects.filter(
            vinculo_permitido_id=user.get_vinculo().id, nivel_permissao__in=[NivelPermissao.LER, NivelPermissao.EDITAR]
        )
        _, q_setores_compartilhados = self.q_compartilhados(user, NivelPermissao.LER)
        return (
            Q(usuario_criacao=user)
            | Q(nivel_acesso=Documento.NIVEL_ACESSO_PUBLICO, status=DocumentoStatus.STATUS_FINALIZADO)
            | Q(pk__in=list(compartilhados_comigo.values_list('documento_id', flat=True)))
            | q_setores_compartilhados
        )

    def finalizados(self):
        return self.filter(status=DocumentoStatus.STATUS_FINALIZADO)


def _ou(*qs: Q | None) -> Q | None:
    """OR dos ramos presentes; ``None`` é o ramo que não vale para o usuário (``Q()`` vazio seria "tudo")."""
    presentes = [q for q in qs if q is not None]
    return reduce(operator.or_, presentes) if presentes else None


def _e(condicao: Q, ramo: Q | None) -> Q | None:
    return None if ramo is None else condicao & ramo


def _pks(ids: Iterable[int]) -> Q | None:
    ids = list(ids)
    return Q(pk__in=ids) if ids else None


class _ProcessosDoUsuario:
    """Acesso a documento pelos processos (``usuario_deve_ter_acesso_a_documento_*_atraves_de_processo``).

    O documento é legível se está num processo que autoriza o usuário (é interessado, o processo transita num setor
    dele ou, só para o restrito, é privado dele) ou num processo anexado, direta ou indiretamente, a um desses.
    Cada critério é uma consulta indexada separada: o OR com joins varreria a tabela de processos.
    """

    def __init__(self, user: User) -> None:
        self.user = user
        self.vinculo = user.get_vinculo()
        self.instalado = 'processo_eletronico' in settings.INSTALLED_APPS and bool(self.vinculo)

    @cached_property
    def setores(self) -> list[int]:
        Tramite = apps.get_model('processo_eletronico', 'Tramite')
        return list(Tramite.get_todos_setores(self.user).values_list('pk', flat=True))

    @cached_property
    def _autorizadores(self) -> set[int]:
        """Processos em que o usuário é interessado ou que transitam nos setores dele (restrito e público cancelado)."""
        Processo = apps.get_model('processo_eletronico', 'Processo')
        consultas = [Processo.interessados.through.objects.filter(vinculo_id=self.vinculo.pk).values_list('processo_id', flat=True)]
        if self.setores:
            consultas += [
                Processo.objects.filter(setor_criacao__in=self.setores, ultimo_tramite__isnull=True).values_list('pk', flat=True),
                Processo.objects.filter(
                    ultimo_tramite__remetente_setor__in=self.setores, ultimo_tramite__data_hora_recebimento__isnull=True
                ).values_list('pk', flat=True),
                Processo.objects.filter(
                    ultimo_tramite__destinatario_setor__in=self.setores, ultimo_tramite__data_hora_recebimento__isnull=False
                ).values_list('pk', flat=True),
            ]
        return {pk for consulta in consultas for pk in consulta}

    def _privados(self) -> set[int]:
        """predicate_privados, só do restrito: processo privado gerado pelo usuário ou tramitado para ele."""
        Processo = apps.get_model('processo_eletronico', 'Processo')
        privados = Processo.objects.filter(nivel_acesso=Processo.NIVEL_ACESSO_PRIVADO)
        return set(privados.filter(usuario_gerador=self.user).values_list('pk', flat=True)) | set(
            privados.filter(tramites__destinatario_vinculo=self.vinculo).values_list('pk', flat=True)
        )

    @staticmethod
    def _com_anexados(processos: set[int]) -> set[int]:
        # get_processos_vinculados_ao_documento sobe a cadeia de anexadores a partir do processo do documento; aqui
        # desce dos processos que autorizam aos anexados, rodada a rodada.
        Anexacao = apps.get_model('processo_eletronico', 'Anexacao')
        fronteira = set(processos)
        while fronteira:
            anexados = set(Anexacao.objects.filter(processo_anexador_id__in=fronteira).values_list('processo_anexado_id', flat=True))
            fronteira = anexados - processos
            processos |= fronteira
        return processos

    def q_documentos(self, restrito: bool, **documento: object) -> Q | None:
        return _pks(self.documentos(restrito, **documento))

    def documentos(self, restrito: bool, **documento: object) -> list[int]:
        """Ids dos documentos legíveis pelos processos. Restrito: vínculo ativo com o processo. Público cancelado:
        qualquer vínculo, sem o privado.

        ``documento`` (lookups ``documento__*``/``documento_id__in``) restringe, já na consulta dos vínculos, aos
        documentos do ramo ou da página da listagem (#17722): a lista de ids que vai para o ``COUNT`` não carrega os
        demais documentos dos processos. O join com o documento parte dos vínculos dos poucos processos, pela chave primária.
        """
        if not self.instalado:
            return []
        processos = self._autorizadores | self._privados() if restrito else self._autorizadores
        if not processos:
            return []
        DocumentoTextoProcesso = apps.get_model('processo_eletronico', 'DocumentoTextoProcesso')
        vinculos = DocumentoTextoProcesso.objects.filter(processo_id__in=self._com_anexados(set(processos)))
        if restrito:
            vinculos = vinculos.filter(data_hora_remocao__isnull=True)
        return list(vinculos.filter(**documento).values_list('documento_id', flat=True).distinct())


def _q_juntada_pendente(user: User, processos: _ProcessosDoUsuario) -> Q | None:
    return _pks(juntadas_pendentes_deferiveis(user, processos))


def juntadas_pendentes_deferiveis(user: User, processos: _ProcessosDoUsuario, **juntada: object) -> list[int]:
    """Ids dos documentos de ``usuario_deve_ter_acesso_a_documento_restrito_atraves_de_solicitacao_juntada_pendente``,
    com a mesma regra ``pode_deferir_documento`` sobre as poucas juntadas pendentes nos setores do usuário.

    ``juntada`` (lookups de ``SolicitacaoJuntadaDocumento``) restringe aos documentos da página da listagem (#17722).
    """
    if not processos.instalado or not processos.setores:
        return []
    from django.contrib.contenttypes.models import ContentType

    from processo_eletronico.status import ProcessoStatus, SolicitacaoJuntadaDocumentoStatus, SolicitacaoJuntadaStatus

    SolicitacaoJuntadaDocumento = apps.get_model('processo_eletronico', 'SolicitacaoJuntadaDocumento')
    # Status da juntada e do processo são parte exata do pode_deferir_documento: filtrados aqui, sobra pouco para o Python.
    pendentes = SolicitacaoJuntadaDocumento.objects.filter(
        status=SolicitacaoJuntadaDocumentoStatus.STATUS_ESPERANDO,
        solicitacao_juntada__status=SolicitacaoJuntadaStatus.STATUS_CONCLUIDO,
        solicitacao_juntada__tramite__processo__status=ProcessoStatus.STATUS_EM_HOMOLOGACAO,
        solicitacao_juntada__tramite__processo__setor_atual__in=processos.setores,
        anexo_content_type=ContentType.objects.get_for_model(apps.get_model('documento_eletronico', 'DocumentoTexto')),
        **juntada,
    ).select_related('solicitacao_juntada__tramite__processo')
    return [juntada.anexo_content_id for juntada in pendentes if juntada.pode_deferir_documento(user)]


def _q_restritos_sistemicos(user: User) -> Q | None:
    modelos = modelos_sistemicos(user)
    return Q(modelo_id__in=modelos) if modelos else None


def modelos_sistemicos(user: User) -> set[int]:
    """``usuario_pode_ler_documentotexto_restrito_por_permissao_sistemica``: modelos liberados aos grupos do usuário."""
    from comum.models import Configuracao

    config = Configuracao.get_valor_por_chave('documento_eletronico', 'grupossistemicos_com_perm_leitura_de_modelosdoc')
    if not config:
        return set()
    grupos = set(user.groups.values_list('name', flat=True))
    # Só inteiros: o pode_ler compara modelo.pk com a lista, e um '5' em texto não casa lá (no SQL casaria).
    return {pk for grupo, ids_modelos in json.loads(config).items() if grupo in grupos for pk in ids_modelos if isinstance(pk, int)}


def _q_acesso_por_cargo(user: User) -> Q | None:
    """``acesso_ao_documento_em_funcao_cargo``: auditor fora do próprio setor, procurador fora da procuradoria."""
    from comum.utils import get_setor, get_setor_procuradoria
    from documento_eletronico.utils import eh_auditor, eh_procurador

    setores_excluidos = []
    if eh_auditor(user):
        setores_excluidos.append(get_setor(user))
    if eh_procurador(user):
        setores_excluidos.append(get_setor_procuradoria())
    if not setores_excluidos:
        return None
    # Um setor None (sem setor/procuradoria configurada) não exclui nada: no pode_ler, setor_dono == None é falso.
    acesso = _ou(*(~Q(setor_dono_id=setor.pk) if setor else Q(pk__isnull=False) for setor in setores_excluidos))
    status = [DocumentoStatus.STATUS_ASSINADO, DocumentoStatus.STATUS_FINALIZADO, DocumentoStatus.STATUS_CANCELADO]
    return Q(status__in=status) & acesso


class DocumentoTextoManager(models.Manager):
    def get_queryset(self):
        return DocumentoTextoQueryset(self.model, using=self._db).defer('cabecalho', 'rodape', 'corpo', 'corpo_indexado')

    def pessoais(self):
        # setor_dono = Documento vinculado a setor (padrao)
        # - aquele que não é um documento pessoal
        return self.get_queryset().pessoais()

    def impessoais(self):
        # setor_dono = Documento vinculado a setor (padrao)
        # - aquele que não é um documento pessoal
        return self.get_queryset().impessoais()

    def assinados(self, user):
        return self.get_queryset().assinados(user)

    def compartilhados(self, user, nivel_permissao=None):
        return self.get_queryset().compartilhados(user, nivel_permissao)

    def by_user(self, user):
        return self.get_queryset().by_user(user)

    def proprios(self, user):
        return self.get_queryset().proprios(user)

    def legiveis_por(self, user: User) -> DocumentoTextoQueryset:
        return self.get_queryset().legiveis_por(user)

    def finalizados(self):
        return self.get_queryset().finalizados()

    def publicos_assinados(self):
        return self.get_queryset().publicos_assinados()

    def revisao_pendente(self, user):
        return self.get_queryset().revisao_pendente(user)

    def requisicao_pendente(self, user):
        return self.get_queryset().requisicao_pendente(user)

    def revisados_por(self, user):
        return self.get_queryset().revisados_por(user)

    def esperando_assinatura(self, user):
        return self.get_queryset().esperando_assinatura(user)

    def assinatura_requisitada_por(self, user):
        return self.get_queryset().assinatura_requisitada_por(user)

    def vinculados_a_mim(self, user):
        return self.get_queryset().vinculados_a_mim(user)


# Manager usado por entidades que possuem um atributo booleando de nome "ativo".
# Ex: TipoDocumento, ModeloDocumemto.
class AtivosManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(ativo=True)


class ModeloDocumentoManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().defer('corpo_padrao')


class ModeloDocumentoAtivoManager(ModeloDocumentoManager):
    def get_queryset(self):
        return super().get_queryset().filter(ativo=True)


class AtivosDocumentosPessoaisManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(ativo=True, permite_documentos_pessoais=True)


class DocumentoTextoPessoalQueryset(DocumentoTextoQueryset):
    def get_model(self):
        return apps.get_model('documento_eletronico', 'DocumentoTextoPessoal')

    def q_compartilhados(self, user, nivel_permissao=None):
        from documento_eletronico.models import NivelPermissao

        vinculo = user.get_vinculo()

        # Recuperar os documentos compartilhados com o usuário, respeitando o nível de permissão pedido:
        # LER casa com compartilhamentos de LER ou EDITAR (quem edita também lê); um nível explícito
        # diferente (ex: EDITAR) exige igualdade exata; sem nível, retorna qualquer compartilhamento.
        if nivel_permissao == NivelPermissao.LER:
            query_documento_pessoa_compartilhada = Q(compartilhamento_pessoa_documento__vinculo_permitido_id=vinculo.id) & (
                Q(compartilhamento_pessoa_documento__nivel_permissao=NivelPermissao.LER)
                | Q(compartilhamento_pessoa_documento__nivel_permissao=NivelPermissao.EDITAR)
            )
        elif nivel_permissao:
            query_documento_pessoa_compartilhada = Q(
                compartilhamento_pessoa_documento__vinculo_permitido_id=vinculo.id,
                compartilhamento_pessoa_documento__nivel_permissao=nivel_permissao,
            )
        else:
            query_documento_pessoa_compartilhada = Q(compartilhamento_pessoa_documento__vinculo_permitido_id=vinculo.id)

        return [query_documento_pessoa_compartilhada]

    def compartilhados(self, user, nivel_permissao=None):
        qs = self.model.objects.none()
        for lookups in self.q_compartilhados(user, nivel_permissao):
            qs = qs | self.filter(lookups)
        return qs.distinct()

    def q_proprios(self, user):
        return [Q(usuario_criacao=user)]


class DocumentoTextoPessoalManager(DocumentoTextoManager):
    def get_queryset(self):
        qs = DocumentoTextoPessoalQueryset(self.model, using=self._db)

        # setor_dono = Documento vinculado a setor (padrao)
        qs = qs.filter(setor_dono__isnull=True)
        return qs


class DocumentoDigitalizadoManager(models.Manager):
    def pessoal(self):
        return super().get_queryset().filter(setor_dono__isnull=False, anexo_simples=False)

    def impessoal(self):
        return super().get_queryset().filter(setor_dono__isnull=True, anexo_simples=False)

    def anexos(self):
        return super().get_queryset().filter(setor_dono__isnull=True, anexo_simples=True)


class DocumentoDigitalizadoPessoalManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(setor_dono__isnull=True, anexo_simples=False)


class DocumentoDigitalizadoAnexoManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(setor_dono__isnull=True, anexo_simples=True)


class AssinaturaDocumentoTextoManager(models.Manager):
    def pessoais(self):
        return self.filter(documento__setor_dono__isnull=True)

    def impessoais(self):
        return self.filter(documento__setor_dono__isnull=False)
