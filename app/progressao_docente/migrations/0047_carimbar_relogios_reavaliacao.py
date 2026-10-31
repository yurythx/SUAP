import logging
from datetime import datetime

from django.db import migrations

logger = logging.getLogger(__name__)

# Valores históricos das situações; não importar dos modelos atuais.
AVALIACAO_REAVALIACAO = 3
AVALIACAO_EDITACAO_PARA_REAVALIACAO = 6


def carimbar_relogios(apps, schema_editor):
    """Dá uma data de liberação às avaliações paradas no ciclo de reavaliação.

    Até aqui a etapa de edição para reavaliação não carimbava data nenhuma e a de
    reavaliação carregava a data do recurso original. Sem isso o processo ficava parado
    indefinidamente à espera de uma manifestação que podia não vir (chamado 10625).

    Os dois casos são carimbados com o instante da migração, e não com a data real de
    entrada na etapa — que não foi registrada:

    - em EDITACAO_PARA_REAVALIACAO a data não existe, e assumi-la antiga expiraria de
      imediato processos reabertos ontem;
    - em REAVALIACAO a data existe mas é a do recurso, quase sempre já vencida, o que
      tiraria a avaliação do avaliador na primeira varredura, sem aviso.

    O backlog ganha, portanto, uma janela cheia contada do deploy. A partir daí os prazos
    valem como previsto. Só grava datas; nenhuma situação é alterada.
    """
    Avaliacao = apps.get_model('progressao_docente', 'Avaliacao')
    agora = datetime.now()

    em_edicao = Avaliacao.objects.filter(situacao=AVALIACAO_EDITACAO_PARA_REAVALIACAO).update(data_liberacao_edicao_reavaliacao=agora)
    em_reavaliacao = Avaliacao.objects.filter(situacao=AVALIACAO_REAVALIACAO).update(data_liberacao_reavaliacao=agora)
    logger.info(
        'Relógios carimbados: %d avaliação(ões) em edição para reavaliação, %d em reavaliação.',
        em_edicao,
        em_reavaliacao,
    )


def nao_faz_nada(apps, schema_editor):
    """Não há data anterior a restaurar: em edição para reavaliação ela nunca existiu e em
    reavaliação a original era justamente o valor defasado que esta migração corrige."""


class Migration(migrations.Migration):
    dependencies = [('progressao_docente', '0046_avaliacao_data_liberacao_edicao_reavaliacao_and_more')]

    operations = [migrations.RunPython(carimbar_relogios, nao_faz_nada)]
