from clipping.rss import importar_tudo
from djtools.assincrono import task
from django.core.cache import cache


@task('Importando Notícias')
def importar(task=None):
    count = importar_tudo(verbosity=0, task=task)
    cache.delete('_cache_quadro_clipping')
    if count:
        task.finalize(f'{count:d} notícias importadas. Por favor, classifique-as.', '/admin/clipping/publicacaodigital/?classificacao__isnull=True')
    else:
        task.finalize('Nenhuma notícia nova foi encontrada', '/admin/clipping/publicacaodigital/?classificacao__isnull=True')
