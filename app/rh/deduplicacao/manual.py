"""Unificação de duas PFs escolhidas à mão por um superusuário (tela ``/rh/unificar_pessoas/``).

Usa o motor do ``aplicar`` sem a premissa do plano (mesmo documento e nascimento): quem escolhe as duas PFs responde por elas.
ponytail: não limpa o cache ``User.VINCULOS``/``PESSOAS_FISICAS`` dos outros processos; o usuário da perdedora pode ver erro
até o reinício dos servidores (decisão do usuário: alcance pequeno).
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from rh.deduplicacao.aplicacao import executar_mescla, normalizar_documentos
from rh.deduplicacao.campos import campos_mesclaveis, resolver_campos
from rh.deduplicacao.plano import _campo_descartado
from rh.deduplicacao.referencias import referencias, referencias_genericas
from rh.models import DeduplicacaoPessoa as D
from rh.models import PessoaFisica


def previa(sobrevivente: int, perdedora: int) -> tuple[dict[str, Any], list[tuple[int, str, Any]]]:
    """Os campos vazios do sobrevivente que a perdedora preenche e os valores dela que serão descartados."""
    valores = {v['pk']: v for v in PessoaFisica.objects.filter(pk__in=[sobrevivente, perdedora]).values('pk', *campos_mesclaveis())}
    return resolver_campos(valores[sobrevivente], [valores[perdedora]])


@transaction.atomic
def unificar(sobrevivente: int, perdedora: int, operador: str) -> None:
    """Mescla ``perdedora`` em ``sobrevivente`` e audita em ``DeduplicacaoPessoa``; qualquer falha desfaz tudo."""
    travadas = PessoaFisica.objects.select_for_update().filter(pk__in=[sobrevivente, perdedora]).order_by('pk')
    documentos = dict(travadas.values_list('pk', 'documento_identificador'))
    _, descartes = previa(sobrevivente, perdedora)
    executar_mescla({sobrevivente: [perdedora]}, referencias(), referencias_genericas())
    normalizar_documentos([sobrevivente])  # o país herdado da perdedora pode formar a chave do passaporte
    agora = timezone.now()
    auditoria = [
        D(
            pf_id=perdedora,
            sobrevivente_id=sobrevivente,
            documento=documentos[perdedora] or '',
            acao=D.MESCLADA,
            motivo=f'unificação manual por {operador}',
        ),
        *(_campo_descartado(pk, sobrevivente, campo, valor) for pk, campo, valor in descartes),
    ]
    for linha in auditoria:
        linha.aplicado_em = agora
    D.objects.bulk_create(auditoria)
