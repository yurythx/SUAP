import datetime

from behave import given
from django.apps.registry import apps
from progressoes.models import ConfiguracaoProgressao

ServidorSetorHistorico = apps.get_model('rh', 'ServidorSetorHistorico')
Servidor = apps.get_model('rh', 'Servidor')
Setor = apps.get_model('rh', 'Setor')
PadraoVencimento = apps.get_model('rh', 'PadraoVencimento')
AfastamentoSiapeEfetivoExercicio = apps.get_model('rh', 'AfastamentoSiapeEfetivoExercicio')


@given('os cadastros básicos de progressões')
def step_impl(context):
    servidor = Servidor.objects.get(matricula='1111111')
    data = datetime.datetime(2019, 2, 8).date()
    setor = Setor.objects.suap_ativos().get(sigla='A1')
    ServidorSetorHistorico.objects.create(servidor=servidor, setor=setor, data_inicio_no_setor=data)
    PadraoVencimento.objects.get_or_create(categoria=PadraoVencimento.CATEGORIA_TECNICO_ADMINISTRATIVO, classe='E', posicao_vertical='01')
    PadraoVencimento.objects.get_or_create(categoria=PadraoVencimento.CATEGORIA_TECNICO_ADMINISTRATIVO, classe='E', posicao_vertical='02')
    AfastamentoSiapeEfetivoExercicio.objects.get_or_create(dias_efetivo_exercicio=30, situacao=1)
    ConfiguracaoProgressao.objects.get_or_create(
        intersticio_progressao=12,
        intersticio_estagio_probatorio=36,
        dias_antecedencia_calcular=90,
        gerar_inconsistencia_dias=90,
        media_aprovacao=60.0,
        ativo=True,
    )
