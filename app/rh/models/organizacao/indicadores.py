from djtools.db import models


class IndicadoresPublicos(models.ModelPlus):
    titulo = models.CharFieldPlus('Título')
    render_to = models.CharFieldPlus('Render To')
    liberar_area_publica = models.BooleanField('Liberar para Área Pública', default=False)

    class Meta:
        verbose_name = 'Indicador Público'
        verbose_name_plural = 'Indicadores Públicos'

    def __str__(self):
        return self.titulo
