# avaliacao_integrada/query/respondente_helper.py
from __future__ import annotations

import logging

from django.contrib.auth.models import AbstractBaseUser
from django.core.cache import cache
from django.db.models import Q, QuerySet

from avaliacao_integrada.models import Indicador, Segmento, Resposta, Servidor, Aluno
from comum.models import UnidadeOrganizacional

logger = logging.getLogger(__name__)


class RespondenteHelper:
    """
    Utilitários com cache do Django (Redis) e cache local em memória do processo
    para seleção de indicadores e cálculo do percentual respondido.
    """

    CACHE_NS = 'aai:respondente_helper'
    TTL_USER_SCOPED = 24 * 60 * 60  # 24h (dados por usuário)
    TTL_BASE_INDICADORES = 60 * 60  # 1h  (base por av/seg/uo/flags/modalidades)

    # ---------------------------
    # Utilitário de montagem de chave (Redis)
    # ---------------------------
    @classmethod
    def _key(cls, name: str, *parts: object) -> str:
        rendered = ':'.join(str(p) for p in parts)
        return f'{cls.CACHE_NS}:{name}:{rendered}'

    # ---------------------------
    # Caches “por usuário” (Redis)
    # ---------------------------
    @classmethod
    def areas_vinculacao_ids_por_matricula(cls, matricula: str) -> tuple[int, ...]:
        key = cls._key('areas_vinc', matricula)

        def _compute() -> tuple[int, ...]:
            srv = Servidor.objects.select_related('setor').only('id', 'setor__id').filter(matricula=matricula).first()
            if not srv or not srv.setor_id:
                return ()
            return tuple(srv.setor.areas_vinculacao.values_list('pk', flat=True))

        return cache.get_or_set(key, _compute, timeout=cls.TTL_USER_SCOPED)

    @classmethod
    def periodo_atual_aluno_por_matricula(cls, matricula: str) -> int | None:
        key = cls._key('periodo_aluno', matricula)

        def _compute() -> int | None:
            return Aluno.ativos.filter(matricula=matricula).values_list('periodo_atual', flat=True).first()

        return cache.get_or_set(key, _compute, timeout=cls.TTL_USER_SCOPED)

    # ---------------------------
    # BASE de indicadores (Redis + cache local opcional)
    # ---------------------------
    @classmethod
    def ids_base_indicadores(
        cls,
        avaliacao_id: int,
        ano: int,
        segmento_id: int,
        uo_id: int | None,
        uo_tipo_id: int | None,
        excluir_automatico: bool,
        ignorar_opcionais: bool,
        modalidades_ids: tuple[int, ...],
        *,
        local_cache: dict[tuple, tuple[int, ...]] | None = None,
    ) -> tuple[int, ...]:
        """
        Retorna a BASE (sem filtros específicos de usuário) como uma tupla de IDs.
        1) Tenta cache local (dicionário em memória deste processo).
        2) Tenta Redis (cache do Django).
        3) Computa e armazena (Redis e local, se fornecido).
        """
        # chave imutável para o cache local (somente tuplas/ints/None)
        local_key = (
            avaliacao_id,
            ano,
            segmento_id,
            uo_id,
            uo_tipo_id,
            int(bool(excluir_automatico)),
            int(bool(ignorar_opcionais)),
            modalidades_ids,  # já vem como tupla
        )

        if local_cache is not None:
            hit = local_cache.get(local_key)
            if hit is not None:
                return hit

        # chave texto para o Redis
        mods = f'mods={",".join(map(str, modalidades_ids))}' if modalidades_ids else 'mods=none'
        redis_key = cls._key(
            'base_ids',
            avaliacao_id,
            ano,
            segmento_id,
            (uo_id if uo_id is not None else 'none'),
            (uo_tipo_id if uo_tipo_id is not None else 'none'),
            int(bool(excluir_automatico)),
            int(bool(ignorar_opcionais)),
            mods,
        )

        def _compute() -> tuple[int, ...]:
            qs: QuerySet[Indicador] = Indicador.objects.filter(em_uso=True, anos_referencia__in=[ano])

            if excluir_automatico:
                qs = qs.filter(automatico=False)
            if ignorar_opcionais:
                qs = qs.filter(obrigatorio=True)

            if uo_id is not None:
                if uo_tipo_id == UnidadeOrganizacional.TIPO_REITORIA:
                    qs = qs.filter(envolve_reitoria=True)
                elif uo_tipo_id == UnidadeOrganizacional.TIPO_CAMPUS_EAD:
                    qs = qs.filter(envolve_campus_ead=True)
                elif uo_tipo_id == UnidadeOrganizacional.TIPO_CAMPUS_NAO_PRODUTIVO:
                    qs = qs.filter(envolve_campus_nao_produtivos=True)
                elif uo_tipo_id == UnidadeOrganizacional.TIPO_CAMPUS_PRODUTIVO:
                    qs = qs.filter(envolve_campus_produtivos=True)
                qs = qs.filter(Q(uos=uo_id) | Q(uos__isnull=True))  # M2M correto
            else:
                qs = qs.filter(uos__isnull=True)

            qs = qs.filter(segmentos__id=segmento_id)

            if modalidades_ids:
                qs = qs.filter(Q(modalidades__in=modalidades_ids) | Q(modalidades__isnull=True))

            base_ids: tuple[int, ...] = tuple(qs.values_list('id', flat=True).distinct())
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f'[ids_base_indicadores] base={len(base_ids)} (key={redis_key})')
            return base_ids

        base_ids = cache.get_or_set(redis_key, _compute, timeout=cls.TTL_BASE_INDICADORES)

        if local_cache is not None:
            local_cache[local_key] = base_ids

        return base_ids

    # ---------------------------
    # API pública (aceita cache_local opcional)
    # ---------------------------
    @classmethod
    def get_indicadores(
        cls,
        avaliacao,
        segmento: Segmento,
        uo: UnidadeOrganizacional | None,
        user: AbstractBaseUser,
        *,
        excluir_automatico: bool = False,
        ignorar_opcionais: bool = False,
        cache_local: dict[tuple, tuple[int, ...]] | None = None,
    ) -> QuerySet[Indicador]:
        modalidades_ids: tuple[int, ...] = tuple(avaliacao.modalidades.values_list('id', flat=True))
        base_ids = cls.ids_base_indicadores(
            avaliacao_id=avaliacao.pk,
            ano=avaliacao.ano,
            segmento_id=segmento.pk,
            uo_id=(uo.pk if uo else None),
            uo_tipo_id=(uo.tipo_id if uo else None),
            excluir_automatico=excluir_automatico,
            ignorar_opcionais=ignorar_opcionais,
            modalidades_ids=modalidades_ids,
            local_cache=cache_local,
        )
        if not base_ids:
            return Indicador.objects.none()

        qs: QuerySet[Indicador] = Indicador.objects.filter(id__in=base_ids)

        if segmento.id in Segmento.SERVIDORES:
            areas_ids = cls.areas_vinculacao_ids_por_matricula(user.username)
            qs = qs.filter(Q(areas_vinculacao__isnull=True) | Q(areas_vinculacao__in=areas_ids))
        elif segmento.id == Segmento.ESTUDANTE:
            periodo_atual = cls.periodo_atual_aluno_por_matricula(user.username)
            if periodo_atual is None:
                qs = qs.exclude(periodo_curso__gt=0)
            else:
                qs = qs.exclude(periodo_curso__gt=periodo_atual)

        return qs.distinct()

    @classmethod
    def percentual_respondido(
        cls,
        respondente,
        *,
        excluir_automatico: bool = False,
        ignorar_opcionais: bool = False,
        cache_local: dict[tuple, tuple[int, ...]] | None = None,
    ) -> int:
        modalidades_ids: tuple[int, ...] = tuple(respondente.avaliacao.modalidades.values_list('id', flat=True))
        matricula = (respondente.user and respondente.user.username) or respondente.identificacao
        base_ids = cls.ids_base_indicadores(
            avaliacao_id=respondente.avaliacao_id,
            ano=respondente.avaliacao.ano,
            segmento_id=respondente.segmento_id,
            uo_id=(respondente.uo_id or None),
            uo_tipo_id=(respondente.uo.tipo_id if respondente.uo_id else None),
            excluir_automatico=excluir_automatico,
            ignorar_opcionais=ignorar_opcionais,
            modalidades_ids=modalidades_ids,
            local_cache=cache_local,
        )
        if not base_ids:
            return 0

        # Denominador
        if respondente.segmento_id in Segmento.SERVIDORES:
            if not matricula or matricula == '-':
                return 0
            areas_ids = cls.areas_vinculacao_ids_por_matricula(matricula)
            den = (
                Indicador.objects.filter(id__in=base_ids)
                .filter(Q(areas_vinculacao__isnull=True) | Q(areas_vinculacao__in=areas_ids))
                .values('id')
                .distinct()
                .count()
            )
        elif respondente.segmento_id == Segmento.ESTUDANTE:
            if not matricula or matricula == '-':
                return 0
            periodo_atual = cls.periodo_atual_aluno_por_matricula(matricula)
            qd = Indicador.objects.filter(id__in=base_ids)
            qd = qd.exclude(periodo_curso__gt=(periodo_atual if periodo_atual is not None else 0))
            den = qd.values('id').distinct().count()
        else:
            den = len(base_ids)

        if den <= 0:
            return 0

        # Numerador
        qs_resp = Resposta.objects.filter(respondente_id=respondente.id, valor__isnull=False).exclude(valor='')
        if excluir_automatico:
            qs_resp = qs_resp.filter(indicador__automatico=False)
        if ignorar_opcionais:
            qs_resp = qs_resp.filter(indicador__obrigatorio=True)

        num = qs_resp.count()
        pct = (num * 100) // den
        return max(0, min(100, int(pct)))
