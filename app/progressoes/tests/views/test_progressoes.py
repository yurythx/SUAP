from datetime import date

import pytest
from django.apps.registry import apps

from rh.tests.factories import ServidorFactory


Group = apps.get_model('auth', 'Group')
ProcessoProgressao = apps.get_model('progressoes', 'ProcessoProgressao')
ConfiguracaoProgressao = apps.get_model('progressoes', 'ConfiguracaoProgressao')
PadraoVencimento = apps.get_model('rh', 'PadraoVencimento')
AfastamentoSiapeEfetivoExercicio = apps.get_model('rh', 'AfastamentoSiapeEfetivoExercicio')


pytestmark = pytest.mark.django_db


@pytest.fixture
def progressoes_context(client, db, sync_permissions):
    afastamento = AfastamentoSiapeEfetivoExercicio.objects.create(dias_efetivo_exercicio=30, situacao=1)

    padrao_vencimento_e1 = PadraoVencimento.objects.create(
        categoria=PadraoVencimento.CATEGORIA_TECNICO_ADMINISTRATIVO,
        classe='E',
        posicao_vertical='01',
    )
    padrao_vencimento_e2 = PadraoVencimento.objects.create(
        categoria=PadraoVencimento.CATEGORIA_TECNICO_ADMINISTRATIVO,
        classe='E',
        posicao_vertical='02',
    )

    ConfiguracaoProgressao.objects.create(
        intersticio_progressao=12,
        intersticio_estagio_probatorio=36,
        dias_antecedencia_calcular=90,
        gerar_inconsistencia_dias=90,
        media_aprovacao=60.0,
        ativo=True,
    )

    servidor_a = ServidorFactory()
    servidor_b = ServidorFactory()
    servidor_a.get_user().groups.add(Group.objects.get(name='Coordenador de Gestão de Pessoas Sistêmico'))
    servidor_b.get_user().groups.add(Group.objects.get(name='Servidor'))

    client.force_login(servidor_a.get_user())

    return {
        'afastamento': afastamento,
        'padrao_vencimento_e1': padrao_vencimento_e1,
        'padrao_vencimento_e2': padrao_vencimento_e2,
        'servidor_a': servidor_a,
        'servidor_b': servidor_b,
        'client': client,
    }


def test_add_progressao_merito(progressoes_context):
    servidor_b = progressoes_context['servidor_b']
    client = progressoes_context['client']
    padrao_vencimento_e1 = progressoes_context['padrao_vencimento_e1']
    padrao_vencimento_e2 = progressoes_context['padrao_vencimento_e2']

    processos_merito_qtd = ProcessoProgressao.objects.filter(tipo=ProcessoProgressao.TIPO_PROGRESSAO_MERITO).count()

    response = client.post(
        '/admin/progressoes/processoprogressao/add/?tipo=1',
        {
            'avaliado': servidor_b.pk,
            'data_inicio_contagem_progressao': date(2017, 1, 9).strftime('%d/%m/%Y'),
            'padrao_anterior': padrao_vencimento_e1.pk,
            'padrao_novo': padrao_vencimento_e2.pk,
        },
    )

    assert response.status_code != 500
    assert ProcessoProgressao.objects.filter(tipo=ProcessoProgressao.TIPO_PROGRESSAO_MERITO).count() == processos_merito_qtd + 1

    processo = ProcessoProgressao(
        tipo=ProcessoProgressao.TIPO_PROGRESSAO_MERITO,
        avaliado=servidor_b,
        data_inicio_contagem_progressao=date(2017, 1, 9),
        padrao_anterior=padrao_vencimento_e1,
        padrao_novo=padrao_vencimento_e2,
    )
    processo.save()

    assert ProcessoProgressao.objects.filter(tipo=ProcessoProgressao.TIPO_PROGRESSAO_MERITO).count() == processos_merito_qtd + 2


def test_add_estagio_probatorio(progressoes_context):
    servidor_b = progressoes_context['servidor_b']
    client = progressoes_context['client']

    processos_estagio_probatorio_qtd = ProcessoProgressao.objects.filter(tipo=ProcessoProgressao.TIPO_ESTAGIO_PROBATORIO).count()

    response = client.post(
        '/admin/progressoes/processoprogressao/add/?tipo=2',
        {'avaliado': servidor_b.pk, 'data_inicio_contagem_progressao': date(2017, 1, 9).strftime('%d/%m/%Y')},
    )

    assert response.status_code != 500
    assert ProcessoProgressao.objects.filter(tipo=ProcessoProgressao.TIPO_ESTAGIO_PROBATORIO).count() == processos_estagio_probatorio_qtd + 1

    processo = ProcessoProgressao(
        tipo=ProcessoProgressao.TIPO_ESTAGIO_PROBATORIO,
        avaliado=servidor_b,
        data_inicio_contagem_progressao=date(2017, 1, 9),
    )
    processo.save()

    assert ProcessoProgressao.objects.filter(tipo=ProcessoProgressao.TIPO_ESTAGIO_PROBATORIO).count() == processos_estagio_probatorio_qtd + 2
