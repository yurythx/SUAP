from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction
from django.db.models import Count, IntegerField, Q, QuerySet, Value
from django.utils import timezone

from ..enums import NotaAvaliacaoBaseDados
from ..models import AvaliacaoBaseDados, BaseDados, ConsultaPublica, CriterioMatriz, PlanoDadosAbertos


@dataclass(frozen=True)
class MatrizPriorizacaoData:
    pda: PlanoDadosAbertos | None
    criterios: QuerySet[CriterioMatriz]
    bases: QuerySet[BaseDados]
    consulta_publica: ConsultaPublica | None


def build_matriz_data(pda: PlanoDadosAbertos | None) -> MatrizPriorizacaoData:
    """Monta os dados necessários para renderizar a matriz."""

    criterios = CriterioMatriz.objects.filter(ativo=True)

    bases = BaseDados.objects.none()
    consulta = None

    if pda:
        consulta = ConsultaPublica.objects.filter(pda=pda).order_by('-data_inicio', '-id').first()

        bases = pda.bases_dados.all().order_by('titulo', 'nome')
        if consulta:
            bases = bases.annotate(
                votos=Count(
                    'avaliacoes',
                    filter=Q(avaliacoes__consulta_publica=consulta),
                    distinct=True,
                )
            )
        else:
            bases = bases.annotate(votos=Value(0, output_field=IntegerField()))

    return MatrizPriorizacaoData(
        pda=pda,
        criterios=criterios,
        bases=bases,
        consulta_publica=consulta,
    )


def iter_notas_from_post(post_data) -> list[tuple[int, int, int]]:
    """Extrai notas do POST.

    Espera keys no formato: nota_<base_id>_<criterio_id>
    Retorna lista de tuplas: (base_id, criterio_id, nota)
    """

    out: list[tuple[int, int, int]] = []
    for key, raw_value in post_data.items():
        if not key.startswith('nota_'):
            continue

        try:
            _, base_id_str, criterio_id_str = key.split('_', 2)
            base_id = int(base_id_str)
            criterio_id = int(criterio_id_str)
            nota = int(raw_value)
        except ValueError, TypeError:
            continue

        out.append((base_id, criterio_id, nota))

    return out


@transaction.atomic
def salvar_notas(
    *,
    bases_ids: set[int],
    criterios_ids: set[int],
    notas: list[tuple[int, int, int]],
) -> tuple[int, int]:
    """Cria/atualiza notas (AvaliacaoBaseDados).

    Retorna: (atualizados, ignorados_finalizados)
    """

    atualizados = 0
    ignorados_finalizados = 0

    for base_id, criterio_id, nota in notas:
        if base_id not in bases_ids or criterio_id not in criterios_ids:
            continue

        if nota not in NotaAvaliacaoBaseDados.LABELS:
            continue

        obj, created = AvaliacaoBaseDados.objects.get_or_create(
            base_dados_id=base_id,
            criterio_matriz_id=criterio_id,
            defaults={'nota': nota},
        )

        if not created and obj.finalizado:
            ignorados_finalizados += 1
            continue

        if created or obj.nota != nota:
            obj.nota = nota
            obj.save(update_fields=['nota', 'data_atualizacao'])
            atualizados += 1

    return atualizados, ignorados_finalizados


@transaction.atomic
def finalizar_avaliacoes(
    *,
    bases_ids: set[int],
    criterios_ids: set[int],
) -> int:
    """Finaliza as avaliações da matriz (para todas as combinações base x critério).

    - Cria registros faltantes como "Não se aplica" já finalizados
    - Marca as pendentes como finalizadas

    Retorna quantas foram finalizadas agora (pendentes → finalizadas).
    """

    existentes = set(
        AvaliacaoBaseDados.objects.filter(
            base_dados_id__in=bases_ids,
            criterio_matriz_id__in=criterios_ids,
        ).values_list('base_dados_id', 'criterio_matriz_id')
    )

    faltantes = []
    for base_id in bases_ids:
        for criterio_id in criterios_ids:
            if (base_id, criterio_id) not in existentes:
                faltantes.append(
                    AvaliacaoBaseDados(
                        base_dados_id=base_id,
                        criterio_matriz_id=criterio_id,
                        nota=NotaAvaliacaoBaseDados.NAO_SE_APLICA,
                        finalizado=True,
                    )
                )

    if faltantes:
        AvaliacaoBaseDados.objects.bulk_create(faltantes)

    qs = AvaliacaoBaseDados.objects.filter(
        base_dados_id__in=bases_ids,
        criterio_matriz_id__in=criterios_ids,
    )

    finalizadas_agora = qs.filter(finalizado=False).count()
    qs.filter(finalizado=False).update(finalizado=True, data_atualizacao=timezone.now())

    return finalizadas_agora
