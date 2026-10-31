from djtools.assincrono import task


@task('Processar Resultado de Edital de Remoção Interna')
def processar_resultado_edital(edital, task=None):
    task.iterate(20)
    edital.processar_resultado()
    task.iterate(100)
    task.finalize('Processamento de Resultado concluído com sucesso', '..')
