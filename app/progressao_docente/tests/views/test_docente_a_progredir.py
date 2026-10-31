"""Tela de detalhe do "Docente a Progredir" com afastamentos que estendem o interstício."""

from datetime import date

import pytest
from django.contrib.auth.models import Permission

from progressao_docente.tests.factories import DocenteAProgredirFactory
from rh.tests.factories import AfastamentoSiapeEfetivoExercicioFactory, AfastamentoSiapeFactory, ServidorAfastamentoFactory

pytestmark = pytest.mark.django_db


def test_dias_da_regra_dos_30_dias_saem_agrupados_em_periodo(client, sync_permissions):
    relatorio = DocenteAProgredirFactory(data_inicio_contagem=date(2024, 6, 11), data_fim_contagem=date(2026, 6, 15))
    licenca = AfastamentoSiapeFactory(nome='Lic. por Motivo de Doença em Pessoa da Família')
    AfastamentoSiapeEfetivoExercicioFactory(dias_efetivo_exercicio=30, afastamentos=[licenca])
    # 35 dias seguidos: do 31º ao 35º dia (31/07 a 04/08) a licença passa de 30 dias no ano
    ServidorAfastamentoFactory(servidor=relatorio.avaliado, afastamento=licenca, data_inicio=date(2024, 7, 1), data_termino=date(2024, 8, 4))
    usuario = relatorio.avaliado.get_user()
    usuario.user_permissions.add(Permission.objects.get(content_type__app_label='progressao_docente', codename='change_progressaodocente'))
    client.force_login(usuario)

    conteudo = client.get(f'/progressao_docente/docenteaprogredir/{relatorio.pk}/').content.decode()

    assert '31/07/2024 a 04/08/2024' in conteudo
    assert '01/07/2024 a 04/08/2024 <small>(35 dias)</small>' in conteudo


def test_regra_dos_24_meses_soma_os_dias_como_o_calculo(client, sync_permissions):
    relatorio = DocenteAProgredirFactory(data_inicio_contagem=date(2024, 1, 1), data_fim_contagem=date(2025, 12, 31))
    licenca = AfastamentoSiapeFactory(nome='Lic. Tratamento de Saúde')
    AfastamentoSiapeEfetivoExercicioFactory(dias_efetivo_exercicio=730, afastamentos=[licenca])
    # os 730 dias se esgotam em 31/12/2023: passam do limite 01 a 10/01/2024 e os 2 dias do registro sobreposto
    ServidorAfastamentoFactory(servidor=relatorio.avaliado, afastamento=licenca, data_inicio=date(2022, 1, 1), data_termino=date(2024, 1, 10))
    ServidorAfastamentoFactory(servidor=relatorio.avaliado, afastamento=licenca, data_inicio=date(2024, 1, 5), data_termino=date(2024, 1, 6))
    usuario = relatorio.avaliado.get_user()
    usuario.user_permissions.add(Permission.objects.get(content_type__app_label='progressao_docente', codename='change_progressaodocente'))
    client.force_login(usuario)

    conteudo = client.get(f'/progressao_docente/docenteaprogredir/{relatorio.pk}/').content.decode()

    assert '01/01/2024 a 10/01/2024 <small>(10 dias)</small>' in conteudo
    assert 'data-tab="24-meses" data-counter="12"' in conteudo
