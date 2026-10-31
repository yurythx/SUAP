"""Fixtures dos testes do app auditoria.

``cenario_atendimento`` monta, só com factories (substrato de ``rh.tests.factories``), o
grafo mínimo do fluxo de monitoramento e os dados de referência para o caminho feliz de
*Atendimento*. Os grupos e permissões vêm de ``sync_permissions`` (sessão).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from django.contrib.auth.models import Group

from auditoria.models import Monitoramento
from auditoria.tests import factories as f
from rh.tests.factories import ServidorFactory, SetorFactory, SetorSiapeFactory


@pytest.fixture
def cenario_atendimento(db, sync_permissions, suap_client):
    """Grafo mínimo do fluxo de monitoramento até o ponto de iniciar.

    Retorna um namespace com:

    - ``auditor`` / ``auditor_user``: servidor no grupo ``Auditor`` (logo passa em
      ``eh_auditor`` e em ``@permission_required('comum.is_auditor')``) e definido
      como monitor da recomendação (logo ``Monitoramento.pode_editar`` é verdadeiro).
    - ``gestor`` / ``gestor_user``: servidor chefe do setor monitorado.
    - ``setor``: unidade monitorada (setor SUAP).
    - ``recomendacao`` e ``monitoramento`` (este em ``REGISTRADO``).
    - ``motivacao``: ``Motivacao`` válida para o posicionamento de atendimento.
    - ``client``: cliente HTTP de teste do SUAP (``suap_client``).
    """
    setor = SetorFactory()
    gestor = ServidorFactory(setor=setor)
    auditor = ServidorFactory()

    # Gestor passa a ser chefe do setor monitorado (cadeia de chefia em rh).
    f.ServidorFuncaoChefiaFactory(servidor=gestor, setor=SetorSiapeFactory(), setor_suap=setor)

    # Auditor entra no grupo 'Auditor' (criado por sync_permissions): isso concede
    # tanto a checagem de grupo (eh_auditor) quanto a permission comum.is_auditor.
    auditor_user = auditor.get_user()
    auditor_user.groups.add(Group.objects.get(name='Auditor'))
    auditor_vinculo = auditor.get_vinculo()

    nucleo = f.NucleoAuditoriaFactory(coordenador=auditor_vinculo)
    relatorio = f.RelatorioFactory(nucleo=nucleo)
    recomendacao = f.RecomendacaoFactory(relatorio=relatorio, nucleo=nucleo, monitor=auditor_vinculo)
    # Ao adicionar a unidade, um signal m2m_changed cria o Monitoramento REGISTRADO.
    recomendacao.unidades.add(setor)
    monitoramento = Monitoramento.objects.get(recomendacao=recomendacao, unidade=setor)

    # Dados de referência para o posicionamento de atendimento.
    f.TipoPosicionamentoValidoAtendimentoFactory()
    motivacao = f.MotivacaoAtendimentoFactory()

    return SimpleNamespace(
        setor=setor,
        gestor=gestor,
        gestor_user=gestor.get_user(),
        auditor=auditor,
        auditor_user=auditor_user,
        auditor_vinculo=auditor_vinculo,
        nucleo=nucleo,
        relatorio=relatorio,
        recomendacao=recomendacao,
        monitoramento=monitoramento,
        motivacao=motivacao,
        client=suap_client,
    )
