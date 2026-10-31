from djtools.db import models
from edu.models import CursoCampus


class ConfiguracaoAcessoDreamspark(models.ModelPlus):
    TIPO_LIBERACAO = 1
    TIPO_RESTRICAO = 2
    TIPO_CHOICES = [[TIPO_LIBERACAO, 'Liberação'], [TIPO_RESTRICAO, 'Restrição']]
    descricao = models.CharField(max_length=255, default='Padrão')
    cursos = models.ManyToManyFieldPlus(CursoCampus)
    tipo = models.IntegerField(default=1, verbose_name='Tipo', choices=TIPO_CHOICES)

    class Meta:
        verbose_name = 'Configuração de Acesso ao Dreamspark'
        verbose_name_plural = 'Configurações de Acesso ao Dreamspark'

    def __str__(self):
        return str(self.pk)

    @staticmethod
    def is_liberado(aluno):
        qs_restricao = ConfiguracaoAcessoDreamspark.objects.filter(tipo=ConfiguracaoAcessoDreamspark.TIPO_RESTRICAO)
        for configuracao in qs_restricao:
            for curso in configuracao.cursos.all():
                if curso.pk == aluno.curso.curso_habilitado.pk:
                    return False
        qs_liberacao = ConfiguracaoAcessoDreamspark.objects.filter(tipo=ConfiguracaoAcessoDreamspark.TIPO_LIBERACAO)
        if qs_liberacao.count():
            for configuracao in qs_liberacao:
                for curso in configuracao.cursos.all():
                    if curso.pk == aluno.curso.curso_habilitado.pk:
                        return True
            return False
        else:
            return True
