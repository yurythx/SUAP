"""Régua única da periodicidade de atualização das bases de dados abertos.

O farol do dashboard e a rotina de atualização automática precisam concordar sobre o que é uma
base "atrasada". Manter o cálculo aqui evita duas verdades sobre a mesma promessa feita ao cidadão.

**A unidade de medida muda conforme quem pergunta, e isso é deliberado.** Uma base pode estar em
mais de um PDA, com frequências diferentes:

* A **rotina** (``atualizacao_service.bases_vencidas``) mede a *base*, que é um artefato único no
  CKAN e só pode ter uma cadência — por isso usa ``intervalo_mais_estrito`` entre todos os PDAs:
  vence a promessa mais curta.
* O **farol do dashboard** e a **pendência pessoal** medem a *relação*, isto é, a promessa daquele
  PDA e do responsável por ela. Aplicar a mais estrita ali cobraria o responsável do PDA anual por
  um prazo que só o PDA mensal assumiu.

Consequência esperada: uma base em PDA anual pode aparecer "em dia" enquanto a rotina a atualiza
todo mês por causa de outro PDA. Não é divergência de régua — são perguntas diferentes.
"""

from __future__ import annotations

import datetime
from collections.abc import Iterable

from dados_abertos.enums import Periodicidade

INTERVALOS_EM_DIAS = {
    Periodicidade.DIARIA: 1,
    Periodicidade.SEMANAL: 7,
    Periodicidade.MENSAL: 30,
    Periodicidade.TRIMESTRAL: 90,
    Periodicidade.SEMESTRAL: 180,
    Periodicidade.ANUAL: 365,
}


def intervalo_em_dias(frequencia: int | None) -> int | None:
    """Intervalo correspondente à frequência, ou ``None`` quando ela não cobra nada.

    ``EVENTUAL`` devolve ``None`` de propósito: é a declaração de que não há periodicidade
    prometida, e não uma periodicidade muito longa.
    """
    return INTERVALOS_EM_DIAS.get(frequencia) if frequencia else None


def frequencia_mais_estrita(frequencias: Iterable[int | None]) -> int | None:
    """Frequência de menor intervalo entre as informadas, ou ``None`` se nenhuma cobra atualização.

    A mesma base pode estar em vários PDAs com frequências diferentes; vale a mais exigente, para
    que nenhuma das promessas publicadas seja descumprida. É também a cadência que o portal anuncia
    (``metadados.periodicidade``), para que anúncio e cobrança não divirjam.
    """
    com_intervalo = {f: dias for f in frequencias if (dias := intervalo_em_dias(f))}
    return min(com_intervalo, key=com_intervalo.__getitem__) if com_intervalo else None


def intervalo_mais_estrito(frequencias: Iterable[int | None]) -> int | None:
    """Menor intervalo entre as frequências informadas, ou ``None`` se nenhuma cobra atualização."""
    return intervalo_em_dias(frequencia_mais_estrita(frequencias))


def proxima_atualizacao(ultima_sincronizacao, intervalo: int | None) -> datetime.date | None:
    """Data em que a próxima atualização passa a ser devida.

    Args:
        ultima_sincronizacao: ``datetime`` da última sincronização, ou ``None`` se nunca houve.
        intervalo: Intervalo em dias, como devolvido por :func:`intervalo_em_dias`.

    Returns:
        datetime.date | None: ``None`` quando não há intervalo ou nunca se sincronizou.
    """
    from django.utils import timezone

    if not intervalo or not ultima_sincronizacao:
        return None
    if timezone.is_aware(ultima_sincronizacao):
        ultima_data = timezone.localtime(ultima_sincronizacao).date()
    else:
        ultima_data = ultima_sincronizacao.date()
    return ultima_data + datetime.timedelta(days=intervalo)
