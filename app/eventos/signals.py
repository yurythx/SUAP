import logging
import random
import string

from django.db import transaction
from django.db.models import Model
from django.db.models.aggregates import Max, Min, Sum
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from eventos.enums import Recomendacao, ResultadoAvaliacao, SituacaoSubmissao
from eventos.models import (
    AvaliacaoSubmissao,
    CriterioAvaliacao,
    Evento,
    FluxoSubmissao,
    ItemAvaliacao,
    Modalidade,
    Participante,
    Submissao,
    TipoParticipante,
)

logger = logging.getLogger(__name__)


@receiver(post_save, sender=ItemAvaliacao, dispatch_uid='atualiza_nota_avaliacao_submissao')
def atualiza_nota_avaliacao_submissao(sender, instance, **kwargs):
    avaliacao_submissao = instance.avaliacao
    # Calcula a nota considerando todos os ItemAvaliacao associados à mesma avaliação
    total_notas = avaliacao_submissao.itemavaliacao_set.aggregate(total=Sum('nota'))['total']
    avaliacao_submissao.nota = total_notas
    avaliacao_submissao.data_hora_nota = instance.data_hora_nota
    avaliacao_submissao.save()


@receiver(post_save, sender=AvaliacaoSubmissao, dispatch_uid='atualiza_resultado_submissao')
def atualiza_resultado_submissao(sender, instance, **kwargs):
    """
    Atualiza o resultado da avaliação (Pendente, Aprovado ou Reprovado)
    e a situação da submissão após o commit da transação.
    """

    def _executar_atualizacao():
        # Recarrega a instância com os dados realmente persistidos
        instance.refresh_from_db(fields=['nota', 'recomendacao'])

        if instance.nota is not None:
            submissao = instance.versao.submissao
            media = submissao.media_notas
            if media is not None:
                if submissao.possui_avaliacao_pendente():
                    resultado_avaliacao = ResultadoAvaliacao.PENDENTE
                else:
                    atingiu_media = media >= submissao.modalidade.evento.configuracao.avaliacao_nota_aprovacao

                    algum_avaliador_rejeitou = AvaliacaoSubmissao.objects.filter(versao=instance.versao, recomendacao=Recomendacao.REJEITAR).exists()

                    resultado_avaliacao = (
                        ResultadoAvaliacao.APROVADO if atingiu_media and not algum_avaliador_rejeitou else ResultadoAvaliacao.REPROVADO
                    )

                submissao.resultado_avaliacao = resultado_avaliacao
                submissao.nota_final = media

            submissao.situacao = SituacaoSubmissao.EM_AVALIACAO if submissao.possui_avaliacao_pendente() else SituacaoSubmissao.AVALIADO

            submissao.save(update_fields=['resultado_avaliacao', 'nota_final', 'situacao'])

    # Adia a execução até o commit da transação
    transaction.on_commit(_executar_atualizacao)


@receiver(post_save, sender=Participante, dispatch_uid='atualiza_chave_acesso')
def atualiza_chave_acesso(sender, instance, created, **kwargs):
    """
    Gera uma chave de acesso única para o participante após a criação.
    Usa 'created' para executar apenas na criação e 'update_fields' para evitar loops.
    """
    if not instance.chave_acesso:
        random.seed(instance.pk)
        chave = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(10))
        instance.chave_acesso = chave
        # Usa update_fields para não disparar signals desnecessários
        instance.save(update_fields=['chave_acesso'])


@receiver(
    post_save,
    sender=TipoParticipante,
    dispatch_uid='atualizar_periodo_inscricao_evento',
)
def atualizar_periodo_inscricao_evento(sender, instance, **kwargs):
    evento = instance.evento
    tipos_com_inscricao_direta = evento.tipos_participante.filter(permite_inscricao_direta=True)
    if tipos_com_inscricao_direta.exists():
        aggregated_values = tipos_com_inscricao_direta.aggregate(
            data_inicio_inscricoes=Min('data_inicio_inscricoes'),
            data_fim_inscricoes=Max('data_fim_inscricoes'),
            hora_inicio_inscricoes=Min('hora_inicio_inscricoes'),
            hora_fim_inscricoes=Max('hora_fim_inscricoes'),
        )
    else:
        aggregated_values = {
            'data_inicio_inscricoes': None,
            'data_fim_inscricoes': None,
            'hora_inicio_inscricoes': None,
            'hora_fim_inscricoes': None,
        }

    evento.data_inicio_inscricoes = aggregated_values['data_inicio_inscricoes']
    evento.data_fim_inscricoes = aggregated_values['data_fim_inscricoes']
    evento.hora_inicio_inscricoes = aggregated_values['hora_inicio_inscricoes']
    evento.hora_fim_inscricoes = aggregated_values['hora_fim_inscricoes']
    evento.save()


@receiver(post_save, sender=Submissao, dispatch_uid='extrair_conteudo_submissao')
def extrair_conteudo_submissao(sender, instance, created, **kwargs):
    """
    Extrai automaticamente o conteúdo do arquivo da submissão após a criação.

    Este signal é executado após o commit da transação para garantir que:
    1. A submissão e sua primeira versão já estejam persistidas
    2. O arquivo já esteja salvo no storage
    3. Não cause problemas de recursão com o save()

    A extração só ocorre se:
    - A submissão foi recém-criada (created=True)
    - Ainda não tem conteúdo extraído
    """

    def _executar_extracao():
        # Recarrega a instância para garantir dados persistidos
        instance.refresh_from_db()

        # Verifica se já tem conteúdo extraído
        if instance.conteudo_extraido:
            return

        instance.extrair_conteudo_arquivo()

    # Só executa na criação da submissão
    if created:
        # Adia execução até commit para garantir que versão e arquivo existam
        transaction.on_commit(_executar_extracao)


# ============================================================
# Signals para recalcular flags de configuração do evento
# ============================================================


def _recalcular_flags_evento(evento_id: int | None) -> None:
    """
    Recalcula os flags de configuração do evento informado, se ele ainda existir.

    Busca pelo id (sem acessar o descritor da FK) porque os receivers de post_delete
    rodam em `on_commit`: quando o próprio Evento é excluído, os filhos são apagados
    em cascata e o descritor levantaria `Evento.DoesNotExist` fora do stack do delete.

    Args:
        evento_id: Id do evento a recalcular; `None` ou inexistente é no-op.
    """
    evento = Evento.objects.filter(pk=evento_id).first()
    if evento:
        evento.recalcular_flags_configuracao()


@receiver(post_save, sender=Modalidade, dispatch_uid='recalcular_flags_modalidade_save')
def recalcular_flags_modalidade_save(sender, instance, **kwargs):
    """
    Recalcula os flags de configuração quando uma modalidade é criada/atualizada.
    """

    def _executar_recalculo():
        if hasattr(instance, 'evento') and instance.evento:
            instance.evento.recalcular_flags_configuracao()

    transaction.on_commit(_executar_recalculo)


@receiver(post_save, sender=CriterioAvaliacao, dispatch_uid='recalcular_flags_criterio_save')
def recalcular_flags_criterio_save(sender, instance, **kwargs):
    """
    Recalcula os flags de configuração quando um critério de avaliação é criado/atualizado.
    """

    def _executar_recalculo():
        if hasattr(instance, 'modalidade') and instance.modalidade and hasattr(instance.modalidade, 'evento'):
            instance.modalidade.evento.recalcular_flags_configuracao()

    transaction.on_commit(_executar_recalculo)


@receiver(post_save, sender=TipoParticipante, dispatch_uid='recalcular_flags_tipo_participante_save')
def recalcular_flags_tipo_participante_save(sender, instance, **kwargs):
    """
    Recalcula os flags de configuração quando um tipo participante é criado/atualizado.
    Só recalcula se for do tipo avaliador.
    """
    from eventos.models import TIPO_PARTICIPACAO_AVALIADOR

    def _executar_recalculo():
        if hasattr(instance, 'evento') and instance.evento:
            # Só recalcula se for tipo avaliador ou se foi removido
            if hasattr(instance, 'tipo_participacao') and instance.tipo_participacao:
                if instance.tipo_participacao.descricao == TIPO_PARTICIPACAO_AVALIADOR:
                    instance.evento.recalcular_flags_configuracao()

    transaction.on_commit(_executar_recalculo)


@receiver(post_save, sender=FluxoSubmissao, dispatch_uid='recalcular_flags_fluxo_save')
def recalcular_flags_fluxo_save(sender, instance, **kwargs):
    """
    Recalcula os flags de configuração quando um fluxo de submissão é criado/atualizado.
    Só recalcula se for etapa de avaliação.
    """
    from eventos.enums import EtapaPeriodoSubmissao

    def _executar_recalculo():
        if hasattr(instance, 'evento') and instance.evento:
            # Só recalcula se for etapa de avaliação
            etapas_avaliacao = [choice[0] for choice in EtapaPeriodoSubmissao.avaliacoes_choices]
            if hasattr(instance, 'etapa') and instance.etapa in etapas_avaliacao:
                instance.evento.recalcular_flags_configuracao()

    transaction.on_commit(_executar_recalculo)


@receiver(post_delete, sender=Modalidade, dispatch_uid='recalcular_flags_modalidade_delete')
def recalcular_flags_modalidade_delete(sender: type[Model], instance: Model, **kwargs: object) -> None:
    """
    Recalcula os flags de configuração quando uma modalidade é deletada.
    """
    transaction.on_commit(lambda: _recalcular_flags_evento(instance.evento_id))


@receiver(post_delete, sender=CriterioAvaliacao, dispatch_uid='recalcular_flags_criterio_delete')
def recalcular_flags_criterio_delete(sender: type[Model], instance: Model, **kwargs: object) -> None:
    """
    Recalcula os flags de configuração quando um critério de avaliação é deletado.
    """

    def _executar_recalculo() -> None:
        evento_id = Modalidade.objects.filter(pk=instance.modalidade_id).values_list('evento_id', flat=True).first()
        _recalcular_flags_evento(evento_id)

    transaction.on_commit(_executar_recalculo)


@receiver(post_delete, sender=TipoParticipante, dispatch_uid='recalcular_flags_tipo_participante_delete')
def recalcular_flags_tipo_participante_delete(sender: type[Model], instance: Model, **kwargs: object) -> None:
    """
    Recalcula os flags de configuração quando um tipo participante é deletado.
    Sempre recalcula pois pode ter sido um avaliador.
    """
    transaction.on_commit(lambda: _recalcular_flags_evento(instance.evento_id))


@receiver(post_delete, sender=FluxoSubmissao, dispatch_uid='recalcular_flags_fluxo_delete')
def recalcular_flags_fluxo_delete(sender: type[Model], instance: Model, **kwargs: object) -> None:
    """
    Recalcula os flags de configuração quando um fluxo de submissão é deletado.
    Sempre recalcula pois pode ter sido uma etapa de avaliação.
    """
    transaction.on_commit(lambda: _recalcular_flags_evento(instance.evento_id))
