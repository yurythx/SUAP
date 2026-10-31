import logging
from collections import defaultdict

from django.db import migrations

logger = logging.getLogger(__name__)

# Valores históricos das situações; não importar dos modelos atuais.
AVALIACAO_AGUARDANDO_PREENCHIMENTO = 1
AVALIACAO_EM_AVALIACAO = 2
AVALIACAO_REAVALIACAO = 3
AVALIACAO_AGUARDANDO_CIENCIA_RESULTADO = 4
AVALIACAO_CONCLUIDA = 5
AVALIACAO_EDITACAO_PARA_REAVALIACAO = 6

PROGRESSAO_A_INICIAR = 1
PROGRESSAO_AGUARDANDO_PREENCHIMENTO = 2
PROGRESSAO_EM_AVALIACAO = 3
PROGRESSAO_REAVALIACAO = 5
PROGRESSAO_AGUARDANDO_CIENCIA_RESULTADO = 6
PROGRESSAO_CIENTE_RESULTADO = 7
PROGRESSAO_FINALIZADO = 8

# Mesma precedência de progressao_docente.models: da etapa mais atrasada para a mais adiantada.
ETAPAS_DA_MAIS_ATRASADA = (
    AVALIACAO_AGUARDANDO_PREENCHIMENTO,
    AVALIACAO_EDITACAO_PARA_REAVALIACAO,
    AVALIACAO_EM_AVALIACAO,
    AVALIACAO_REAVALIACAO,
    AVALIACAO_AGUARDANDO_CIENCIA_RESULTADO,
    AVALIACAO_CONCLUIDA,
)

SITUACAO_POR_ETAPA = {
    AVALIACAO_AGUARDANDO_PREENCHIMENTO: PROGRESSAO_AGUARDANDO_PREENCHIMENTO,
    AVALIACAO_EDITACAO_PARA_REAVALIACAO: PROGRESSAO_REAVALIACAO,
    AVALIACAO_EM_AVALIACAO: PROGRESSAO_EM_AVALIACAO,
    AVALIACAO_REAVALIACAO: PROGRESSAO_REAVALIACAO,
    AVALIACAO_AGUARDANDO_CIENCIA_RESULTADO: PROGRESSAO_AGUARDANDO_CIENCIA_RESULTADO,
    AVALIACAO_CONCLUIDA: PROGRESSAO_CIENTE_RESULTADO,
}


def ressincronizar(apps, schema_editor):
    """Recalcula a situação dos processos cujo estado ficou defasado das suas avaliações.

    A cascata de `if`s que mantinha esse campo não tinha ramo para AGUARDANDO_PREENCHIMENTO:
    um processo com uma avaliação concluída e outra aguardando preenchimento não casava com
    nenhuma condição e conservava a situação anterior. Isso deixava o avaliado sem ação
    disponível enquanto o avaliador via uma etapa que já tinha sido cumprida.

    Só recalcula; nada é apagado. Ficam intocados os processos A_INICIAR (as avaliações já
    existem, mas a CPPD ainda não liberou o processo), os FINALIZADO (estado terminal) e os
    que não têm avaliações.
    """
    ProgressaoDocente = apps.get_model('progressao_docente', 'ProgressaoDocente')
    Avaliacao = apps.get_model('progressao_docente', 'Avaliacao')

    fora_do_fluxo = (PROGRESSAO_A_INICIAR, PROGRESSAO_FINALIZADO)
    elegiveis = ProgressaoDocente.objects.exclude(situacao__in=fora_do_fluxo)

    # uma única leitura das avaliações, em vez de uma consulta por processo dentro do laço
    situacoes_por_processo = defaultdict(set)
    for progressao_id, situacao in Avaliacao.objects.filter(progressao__in=elegiveis).values_list('progressao_id', 'situacao'):
        situacoes_por_processo[progressao_id].add(situacao)

    alterados = 0
    for progressao_id, situacao_atual in elegiveis.values_list('id', 'situacao').iterator(chunk_size=500):
        situacoes = situacoes_por_processo.get(progressao_id)
        if not situacoes:
            continue
        derivada = next((SITUACAO_POR_ETAPA[etapa] for etapa in ETAPAS_DA_MAIS_ATRASADA if etapa in situacoes), None)
        if derivada is not None and derivada != situacao_atual:
            ProgressaoDocente.objects.filter(pk=progressao_id).update(situacao=derivada)
            alterados += 1
    logger.info('Situação ressincronizada em %d processo(s) de progressão docente.', alterados)


def nao_faz_nada(apps, schema_editor):
    """A situação anterior era o próprio valor defasado; não há o que restaurar."""


class Migration(migrations.Migration):
    dependencies = [('progressao_docente', '0044_merge_20260616_1309')]

    operations = [migrations.RunPython(ressincronizar, nao_faz_nada)]
