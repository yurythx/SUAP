"""
Centraliza todas as verificações de acesso e permissão para ProcessoRSCTae.

Uso básico (views):
    perms = PermissoesProcesso(request, processo)
    if perms.pode_avaliar:
        ...

Uso no admin (com dados já carregados via prefetch, sem queries extras):
    perms = PermissoesProcesso(request, processo).com_dados_avaliador(
        eh_avaliador=True,
        finalizada=False,
    )
"""

import logging
from functools import cached_property

from rsc_tae.enums import SituacaoDocumentoPreliminar, SituacaoProcesso, TipoDocumentoPreliminar
from rsc_tae.models import AvaliacaoProcessoRSCTae, DocumentoPreliminarRSCTae

logger = logging.getLogger(__name__)


class PermissoesProcesso:
    """
    Calcula as permissões de ação sobre um ProcessoRSCTae para o usuário da
    request. Cada propriedade é avaliada no máximo uma vez (cached_property).

    Para contextos onde os dados do avaliador já foram carregados via prefetch
    (ex.: lista do admin), use com_dados_avaliador() para evitar queries extras.
    """

    def __init__(self, request, processo):
        self._request = request
        self._processo = processo

    # ------------------------------------------------------------------ #
    # Identidade do usuário                                                #
    # ------------------------------------------------------------------ #

    @cached_property
    def _user(self):
        return self._request.user

    @cached_property
    def vinculo_usuario(self):
        try:
            return self._user.get_vinculo()
        except Exception:
            logger.exception('Não foi possível obter o vínculo do usuário %s', self._user)
            return None

    @cached_property
    def eh_dono(self):
        return bool(self.vinculo_usuario and self._processo.vinculo_id == self.vinculo_usuario.id)

    @cached_property
    def eh_rh_sistemico(self):
        return bool(getattr(self._user, 'has_perm', lambda *_: False)('rh.eh_rh_sistemico'))

    @cached_property
    def eh_rh_campus(self):
        return bool(getattr(self._user, 'has_perm', lambda *_: False)('rh.eh_rh_campus'))

    @cached_property
    def eh_avaliador_designado(self):
        if not self.vinculo_usuario:
            return False
        if not self._user.has_perm('rsc_tae.avaliar_processorsctae'):
            return False
        try:
            if self._processo.avaliadores.filter(id=self.vinculo_usuario.id).exists():
                return True
        except Exception:
            logger.exception('Erro ao verificar avaliadores do processo %s', self._processo.pk)
        # Fallback para processos legados (avaliador único)
        return int(getattr(self._processo, 'avaliador_atual_id', 0) or 0) == int(self.vinculo_usuario.id)

    # ------------------------------------------------------------------ #
    # Dados carregados sob demanda (um único hit por instância)            #
    # ------------------------------------------------------------------ #

    @cached_property
    def _avaliacao_processo(self):
        """AvaliacaoProcessoRSCTae do usuário atual, ou None."""
        if not self.vinculo_usuario or not self.eh_avaliador_designado:
            return None
        try:
            return (
                AvaliacaoProcessoRSCTae.objects.filter(processo=self._processo, avaliador_vinculo=self.vinculo_usuario)
                .only('finalizada', 'resposta', 'substituido')
                .first()
            )
        except Exception:
            logger.exception(
                'Erro ao buscar AvaliacaoProcessoRSCTae do processo %s para %s',
                self._processo.pk,
                self.vinculo_usuario,
            )
            return None

    @cached_property
    def avaliacao_finalizada(self):
        return bool(getattr(self._avaliacao_processo, 'finalizada', False))

    @cached_property
    def documento_preliminar_validado(self):
        try:
            docs = [
                DocumentoPreliminarRSCTae.objects.filter(processo=self._processo, tipo=tipo)
                .select_related('avaliacao')
                .order_by('-data_cadastro')
                .first()
                for tipo, _label in TipoDocumentoPreliminar.get_choices()
            ]
        except Exception:
            logger.exception('Erro ao buscar documentos preliminares do processo %s', self._processo.pk)
            return False
        return bool(docs) and all(getattr(getattr(doc, 'avaliacao', None), 'situacao', None) == SituacaoDocumentoPreliminar.VALIDADO for doc in docs)

    # ------------------------------------------------------------------ #
    # Injeção de dados já carregados (prefetch / admin)                    #
    # ------------------------------------------------------------------ #

    def com_dados_avaliador(self, *, eh_avaliador, finalizada):
        """
        Pre-popula os campos do avaliador com dados já obtidos via prefetch,
        evitando queries adicionais. Retorna self para uso em cadeia.

        Exemplo (admin):
            perms = PermissoesProcesso(request, obj).com_dados_avaliador(
                eh_avaliador=eh_avaliador,
                finalizada=avaliacao_ja_finalizada,
            )
        """
        self.__dict__['eh_avaliador_designado'] = bool(eh_avaliador)
        self.__dict__['avaliacao_finalizada'] = bool(finalizada)
        return self

    # ------------------------------------------------------------------ #
    # Permissões de ação                                                   #
    # ------------------------------------------------------------------ #

    @cached_property
    def pode_editar_preenchimento(self):
        return self.eh_dono and self._processo.situacao in SituacaoProcesso.EDITAVEIS_PELO_SERVIDOR

    @cached_property
    def pode_concluir_preenchimento(self):
        return self.pode_editar_preenchimento

    @cached_property
    def pode_alterar_nivel(self):
        """O dono pode alterar o nível pretendido enquanto o processo está em preenchimento/correção.

        Antes da (re)assinatura da conclusão a alteração é segura: ao reconcluir, a assinatura e o
        requerimento protocolado são regenerados e passam a cobrir o novo nível.
        """
        return self.eh_dono and self._processo.situacao in SituacaoProcesso.EDITAVEIS_PELO_SERVIDOR

    @cached_property
    def pode_editar_documento_preliminar(self):
        return self.eh_dono and self._processo.situacao in SituacaoProcesso.EDITAVEIS_PELO_SERVIDOR

    @cached_property
    def pode_validar_documento_preliminar(self):
        """A validação do processo é ato da comissão — a sistêmica (RH) não valida."""
        return (
            not self.eh_dono
            and self.eh_membro_crsc_ativo
            and self._processo.situacao
            in (
                SituacaoProcesso.AGUARDANDO_VALIDACAO_DOCUMENTO_PRELIMINAR,
                SituacaoProcesso.AGUARDANDO_AVALIADOR,  # fallback p/ processos antigos
            )
            and not self.documento_preliminar_validado
        )

    @cached_property
    def pode_definir_avaliador(self):
        return (
            self._user.has_perm('rsc_tae.definir_avaliador_processorsctae')
            and self._processo.situacao == SituacaoProcesso.AGUARDANDO_AVALIADOR
            and self.documento_preliminar_validado
        )

    @cached_property
    def pode_avaliar(self):
        if not self._user.has_perm('rsc_tae.avaliar_processorsctae'):
            return False
        if not self.eh_avaliador_designado or self.avaliacao_finalizada:
            return False
        return self._processo.situacao == SituacaoProcesso.EM_ANALISE

    @cached_property
    def pode_recusar_ou_impedir(self):
        """True quando o avaliador pode recusar ou declarar impedimento/suspeição."""
        if not self._user.has_perm('rsc_tae.avaliar_processorsctae'):
            return False
        if not self.eh_avaliador_designado or self.avaliacao_finalizada:
            return False
        if self._processo.situacao != SituacaoProcesso.EM_ANALISE:
            return False
        ap = self._avaliacao_processo
        if not ap:
            return False
        return not ap.substituido

    @cached_property
    def eh_membro_crsc_ativo(self):
        """True se o usuário é membro ATIVO da comissão ativa (habilitado a ações/privilégios da CRSC)."""
        from ._helpers import eh_membro_crsc_ativo

        return eh_membro_crsc_ativo(self.vinculo_usuario)

    @cached_property
    def pode_ver_devolucao_crsc(self) -> bool:
        """True quando a devolução para correção deve **aparecer** ao usuário na deliberação.

        Visível a todo membro ativo da comissão, mesmo a quem não pode executá-la: a ação
        existe e a comissão precisa saber disso ao decidir entre deliberar e devolver. Quem
        executa é decidido em `pode_devolver_para_correcao_crsc`.

        Returns:
            `True` se o usuário é membro ativo da CRSC, não é o avaliado e o processo está
            em deliberação.
        """
        return bool(self.eh_membro_crsc_ativo and not self.eh_dono and self._processo.situacao == SituacaoProcesso.AGUARDANDO_CRSC)

    @cached_property
    def pode_devolver_para_correcao_crsc(self) -> bool:
        """True quando o usuário pode **executar** a devolução para correção na deliberação.

        A devolução apaga avaliações e deliberações de todo o colegiado, então é ato privativo
        do presidente — o mesmo critério do voto de desempate.

        Returns:
            `True` se o usuário vê a ação e é presidente da comissão ativa.
        """
        return bool(self.pode_ver_devolucao_crsc and self.eh_presidente_comissao)

    @cached_property
    def pode_deliberar_crsc(self):
        """True quando o usuário é membro ATIVO da CRSC-TAE e pode deliberar o processo."""
        if not self.eh_membro_crsc_ativo:
            return False
        if self._processo.situacao != SituacaoProcesso.AGUARDANDO_CRSC:
            return False
        try:
            from rsc_tae.models import DeliberacaoCRSCRSCTae

            return not DeliberacaoCRSCRSCTae.objects.filter(processo=self._processo).exists()
        except Exception:
            logger.exception('Erro ao verificar deliberação CRSC do processo %s', self._processo.pk)
            return False

    @cached_property
    def pode_ver_resumo_avaliacao(self):
        if self.eh_dono or self.eh_rh_sistemico:
            return True
        if self.eh_membro_crsc_ativo:
            return True
        return self._user.has_perm('rsc_tae.avaliar_processorsctae') and self.eh_avaliador_designado

    @cached_property
    def pode_ver_deliberacao(self):
        """Quem pode ler o relato da deliberação — e só depois que o processo fecha.

        Mesma plateia do resumo da avaliação (dono, RH sistêmico, membro da CRSC e avaliador
        designado), restrita aos estados finais: enquanto a comissão delibera, expor as notas
        e justificativas em formação abriria espaço para pressão sobre quem ainda vai votar.
        É o mesmo critério que já tranca o parecer e o PDF da deliberação.
        """
        return self._processo.situacao in SituacaoProcesso.FINAIS and self.pode_ver_resumo_avaliacao

    @cached_property
    def pode_ver_nomes_avaliadores(self):
        """Quem pode ver os nomes dos avaliadores.

        Membros da CRSC-TAE sempre; os demais (avaliado, RH, avaliadores) apenas quando o processo
        já está finalizado. Durante o andamento os nomes ficam anônimos, evitando que o avaliado
        tente coagir avaliadores.
        """
        if self._processo.situacao in SituacaoProcesso.FINAIS:
            return True
        return bool(getattr(self._user, 'is_superuser', False)) or self.eh_membro_crsc_ativo

    @cached_property
    def eh_presidente_comissao(self):
        """True se o usuário é presidente da comissão ativa.

        O presidente registra o voto de desempate quando os membros empatam a deliberação de um
        item ou do processo. A disponibilidade da ação depende também de haver empate pendente
        (verificado na view com o status da deliberação).
        """
        from ._helpers import eh_presidente

        return eh_presidente(self.vinculo_usuario)
