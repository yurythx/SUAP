from djtools.db import models


class PosicionamentoPCA(models.ModelPlus):
    pca = models.ForeignKeyPlus('rh.PCA', null=False, on_delete=models.CASCADE)
    codigo_pca_posicionamento = models.CharField(max_length=11, db_index=True)  # CH-PCA-POSICIONAMENTO - é o mesmo dado de rh.PCA.codigo_pca
    codigo_posicionamento_pca = models.CharField(max_length=9, null=False, db_index=True)  # CH-POSICIONAMENTO-PCA
    forma_entrada = models.ForeignKeyPlus('rh.FormaProvimentoVacancia', on_delete=models.CASCADE)  # CO-FORMA-ENTRADA-POS-PCA
    data_inicio_posicionamento_pca = models.DateFieldPlus(db_index=True)  # DA-INI-POSICIONAMENTO-PCA
    data_fim_posicionamento_pca = models.DateFieldPlus()  # DA-FIM-POSICIONAMENTO-PCA

    eh_capacitacao = models.BooleanField('É Capacitação?', default=False)

    def __str__(self):
        return f'{self.pca} - {self.codigo_posicionamento_pca} - {self.data_inicio_posicionamento_pca} à {self.data_fim_posicionamento_pca}'

    def data_fim_posicionamento_pca_or_None(self):
        data_fim = self.data_fim_posicionamento_pca
        if (data_fim is not None) and (data_fim.year == 2500):
            data_fim = None
        return data_fim

    class Meta:
        verbose_name = 'Posicionamento no PCA'
        verbose_name_plural = 'Posicionamentos no PCA'
        unique_together = ('codigo_pca_posicionamento', 'codigo_posicionamento_pca', 'forma_entrada', 'data_inicio_posicionamento_pca')
        ordering = ['-data_inicio_posicionamento_pca']
