from datetime import datetime, timedelta
from djtools.db import models
from djtools.utils import get_datetime_now


class RegimeJuridicoPCA(models.ModelPlus):
    pca = models.ForeignKeyPlus('rh.PCA', on_delete=models.CASCADE)
    regime_juridico = models.ForeignKeyPlus('rh.RegimeJuridico', null=True, on_delete=models.CASCADE)
    codigo_regime_juridico_pca = models.CharField(max_length=2)  # CO-REGIME-JURIDICO-PCA - é o mesmo dado de rh.RegimeJuridico.codigo
    data_inicio_regime_juridico_pca = models.DateFieldPlus(db_index=True)  # DA-IN-REGIME-JURIDICO-PCA
    data_fim_regime_juridico_pca = models.DateFieldPlus(db_index=True)  # DA-FIM-REGIME-JURIDICO-PCA
    valor_fator_tempo_regime_juridico_pca = models.DecimalFieldPlus()  # VA-FATOR-TEMPO-REGIME-PCA

    class Meta:
        verbose_name = 'Regime Jurídico do PCA'
        verbose_name_plural = 'Regimes Jurídicos do PCA'

    @property
    def data_fim_regime_juridico_pca_or_None(self):
        data_fim = self.data_fim_regime_juridico_pca
        if (data_fim is not None) and (data_fim.year == 2500):
            data_fim = None
        return data_fim

    def tempo_servico_interrompido(self, data_referencia=None):
        from ..afastamento import ServidorAfastamento

        if isinstance(data_referencia, datetime):
            data_referencia = data_referencia.date()
        if not data_referencia or data_referencia > self.data_fim_regime_juridico_pca:
            data_referencia = self.data_fim_regime_juridico_pca
        afastamentos = ServidorAfastamento.objects.filter(
            servidor=self.pca.servidor,
            afastamento__interrompe_tempo_servico=True,
            data_inicio__gte=self.data_inicio_regime_juridico_pca,
            data_termino__lte=data_referencia,
            cancelado=False,
        )
        total_dias_afastamentos = timedelta(0)
        for afastamento in afastamentos:
            afastamento_data_fim = afastamento.data_termino
            afastamento_data_inicio = afastamento.data_inicio
            if afastamento_data_inicio < self.data_inicio_regime_juridico_pca:
                afastamento_data_inicio = self.data_inicio_regime_juridico_pca
            if afastamento_data_fim > self.data_fim_regime_juridico_pca:
                afastamento_data_fim = self.data_fim_regime_juridico_pca
            total_dias_afastamentos += (afastamento_data_fim - afastamento_data_inicio) + timedelta(1)
        return total_dias_afastamentos

    def tempo_servico(self, ficto=False, data_referencia=None):
        data_fim = self.data_fim_regime_juridico_pca_or_None or get_datetime_now().date()
        if data_referencia:
            if data_referencia < self.data_inicio_regime_juridico_pca:
                return timedelta(0)
            elif data_referencia < data_fim:
                data_fim = data_referencia

        tempo_servico = data_fim - self.data_inicio_regime_juridico_pca + timedelta(1)
        # afastamentos durante o período do regime
        #        afastamentos = ServidorOcorrencia.objects.filter(servidor=self.pca.servidor,
        #                                                         ocorrencia__interrompe_pagamento=True,
        #                                                         data__gte=self.data_inicio_regime_juridico_pca,
        #                                                         data_termino__lte=data_fim)
        total_dias_afastamentos = self.tempo_servico_interrompido(data_fim)

        # aplica os afastamentos ao tempo calculado, NÃO considerando o fator
        tempo_servico -= timedelta(total_dias_afastamentos.days)
        if ficto:
            # aplica o fator ao tempo calculado
            # aplica os afastamentos ao tempo calculado, considerando o fator novamente
            tempo_servico = timedelta(tempo_servico.days * float(self.valor_fator_tempo_regime_juridico_pca))

        return tempo_servico

    def __str__(self):
        return '{} {} - {} à {} - {}'.format(
            self.codigo_regime_juridico_pca,
            self.regime_juridico or '',
            self.data_inicio_regime_juridico_pca,
            self.data_fim_regime_juridico_pca,
            self.valor_fator_tempo_regime_juridico_pca,
        )
