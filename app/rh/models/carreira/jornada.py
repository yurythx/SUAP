from djtools.db import models


class JornadaTrabalhoPCA(models.ModelPlus):
    pca = models.ForeignKeyPlus('rh.PCA', on_delete=models.CASCADE)
    qtde_jornada_trabalho_pca = models.CharField(max_length=2)  # QT-JORNADA-TRABALHO-PCA
    data_inicio_jornada_trabalho_pca = models.DateFieldPlus()  # DA-INI-JORNADA-TRABALHO-PCA
    data_fim_jornada_trabalho_pca = models.DateFieldPlus()  # DA-FIM-JORNADA-TRABALHO-PCA

    class Meta:
        verbose_name = 'Jornada de Trabalho do PCA'
        verbose_name_plural = 'Jornadas de Trabalho do PCA'

    def __str__(self):
        return f'{self.pca} - {self.qtde_jornada_trabalho_pca} - {self.data_inicio_jornada_trabalho_pca} à {self.data_fim_jornada_trabalho_pca}'

    def get_absolute_url(self):
        return f'/admin/rh/jornadatrabalhopca/{self.pk}/view/'
