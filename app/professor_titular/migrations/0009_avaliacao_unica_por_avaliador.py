from django.db import migrations

# Status EM_AVALIACAO de Avaliacao (valor histórico; não importar do modelo atual).
EM_AVALIACAO = 0


def _tem_trabalho_do_avaliador(AvaliacaoItem, avaliacao):
    """Indica se a avaliação carrega qualquer resultado do avaliador.

    Uma avaliação só é descartável quando nenhum item foi tocado: sem quantidade
    validada, sem data de referência e sem justificativa.
    """
    itens = AvaliacaoItem.objects.filter(avaliacao=avaliacao)
    if itens.filter(qtd_itens_validado__isnull=False).exists():
        return True
    if itens.filter(data_referencia__isnull=False).exists():
        return True
    return itens.exclude(justificativa__isnull=True).exclude(justificativa='').exists()


def _eh_descartavel(AvaliacaoItem, avaliacao):
    """Uma avaliação vazia, criada por engano, que pode ser removida sem perda."""
    if avaliacao.status != EM_AVALIACAO:
        return False
    if avaliacao.pontuacao_final_individual is not None or avaliacao.data_finalizacao is not None:
        return False
    if avaliacao.avaliacao_paga or avaliacao.data_pagamento is not None:
        return False
    if avaliacao.tipo_desistencia is not None or (avaliacao.motivo_desistencia or '').strip():
        return False
    if (avaliacao.motivo_indeferimento or '').strip():
        return False
    return not _tem_trabalho_do_avaliador(AvaliacaoItem, avaliacao)


def remover_avaliacoes_duplicadas(apps, schema_editor):
    """Remove as avaliações duplicadas vazias antes de impor o unique_together.

    Uma corrida em `avaliar_processo` (consultar-para-depois-criar) permitiu que o mesmo
    avaliador ficasse com duas avaliações no mesmo processo. Em todos os casos observados,
    exatamente uma das linhas está intocada — é essa que sai. Se algum par tiver duas linhas
    com trabalho do avaliador, a migração falha em vez de escolher por conta própria.
    """
    Avaliacao = apps.get_model('professor_titular', 'Avaliacao')
    AvaliacaoItem = apps.get_model('professor_titular', 'AvaliacaoItem')

    pares = Avaliacao.objects.values_list('processo_id', 'avaliador_id').distinct()
    ambiguos = []
    for processo_id, avaliador_id in pares:
        avaliacoes = list(Avaliacao.objects.filter(processo_id=processo_id, avaliador_id=avaliador_id).order_by('id'))
        if len(avaliacoes) < 2:
            continue

        descartaveis = [a for a in avaliacoes if _eh_descartavel(AvaliacaoItem, a)]
        # Preserva ao menos uma linha, mesmo que todas estejam vazias.
        if len(descartaveis) == len(avaliacoes):
            descartaveis = descartaveis[1:]

        if len(avaliacoes) - len(descartaveis) > 1:
            ambiguos.append((processo_id, avaliador_id, [a.id for a in avaliacoes]))
            continue

        for avaliacao in descartaveis:
            AvaliacaoItem.objects.filter(avaliacao=avaliacao).delete()
            avaliacao.delete()

    if ambiguos:
        detalhes = '; '.join(f'processo {p}, avaliador {a}, avaliações {ids}' for p, a, ids in ambiguos)
        raise RuntimeError(
            'Há avaliações duplicadas com trabalho do avaliador em mais de uma linha e a '
            f'escolha não pode ser automática. Resolva manualmente e rode a migração de novo: {detalhes}'
        )


def nao_faz_nada(apps, schema_editor):
    """As avaliações removidas não são recriáveis; a reversão só solta a constraint."""


class Migration(migrations.Migration):
    dependencies = [('professor_titular', '0008_auto_20250521_2235')]

    operations = [
        migrations.RunPython(remover_avaliacoes_duplicadas, nao_faz_nada),
        migrations.RunSQL(
            'SET CONSTRAINTS ALL IMMEDIATE',
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AlterUniqueTogether(
            name='avaliacao',
            unique_together={('processo', 'avaliador')},
        ),
    ]
