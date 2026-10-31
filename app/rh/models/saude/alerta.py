from django.apps import apps
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

from djtools.db import models
from djtools.utils import send_notification

from ..organizacao import Setor


class AlertaGestaoPessoa(models.ModelPlus):
    ACAO_JORNADA_TRABALHO_PCA = 1
    ACAO_AFASTAMENTO = 2
    ACAO_AFASTAMENTO_SIAPE = 3
    ACAO_HISTORICO_FUNCAO = 4

    TIPO_ACAO = (
        (ACAO_JORNADA_TRABALHO_PCA, 'Jornada de Trabalho PCA'),
        (ACAO_AFASTAMENTO, 'Afastamentos'),
        (ACAO_AFASTAMENTO_SIAPE, 'Afastamentos SIAPE'),
        (ACAO_HISTORICO_FUNCAO, 'Histórico de Função'),
    )

    vinculo_analizar = models.ForeignKeyPlus(to='comum.Vinculo', verbose_name='Vínculo a Analizar', on_delete=models.SET_NULL, null=True)
    tipo_acao = models.IntegerFieldPlus(verbose_name='Tipo da Ação', choices=TIPO_ACAO)
    data_acao = models.DateTimeFieldPlus(verbose_name='Data da Ação')
    registro_afetado = models.TextField(verbose_name='Registro Afetado')
    content_type = models.ForeignKeyPlus(ContentType, verbose_name='Content Type', null=True, blank=True, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField(verbose_name='', null=True, blank=True)
    objeto = GenericForeignKey('content_type', 'object_id')

    class Meta:
        verbose_name = 'Alerta para Gestão de Pessoas'
        verbose_name_plural = 'Alertas para Gestão de Pessoas'

    def __str__(self):
        return f'{self.vinculo_analizar} - [{self.get_tipo_acao_display()}])'

    def get_absolute_url(self):
        return f'/rh/alertagestaopessoa/{self.pk}/ver/'

    def save(self, *args, **kwargs):
        save = super().save(*args, **kwargs)
        Configuracao = apps.get_model('comum', 'configuracao')
        setor_rh_pk = Configuracao.get_valor_por_chave('rh', 'setor_rh')
        setor = Setor.objects.suap_ativos().filter(pk=setor_rh_pk or 0).first()
        vinculos = []
        if setor:
            for i in setor.chefes:
                vinculos.append(i.get_vinculo())

            # notificando digpe
            titulo = '[SUAP] ALERTA DE LANÇAMENTO EM BENEFÍCIO PRÓPRIO'
            texto = []
            texto.append('<h1>Um lançamento em benefício próprio foi identificado</h1>')
            texto.append(
                f'<p class="more-info">Para mais informações, acesse: <a href="{settings.SITE_URL}/{self.get_absolute_url()}">Alerta de lançamento.</a></p>'
            )
            send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, vinculos)

        return save


class AlertaGestaoPessoaVisualizacao(models.ModelPlus):
    alerta_visualizado = models.ForeignKeyPlus(to='rh.AlertaGestaoPessoa', verbose_name='Alerta Visualizado', on_delete=models.SET_NULL, null=True)
    vinculo = models.ForeignKeyPlus(to='comum.Vinculo', verbose_name='Vínculo que Visualizou', on_delete=models.SET_NULL, null=True)
    data_visualizacao = models.DateTimeFieldPlus(auto_now_add=True)

    class Meta:
        verbose_name = 'Visualização de Alerta'
        verbose_name_plural = 'Visualização de Alertas'
