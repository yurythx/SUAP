from djtools.assincrono import task


@task('Gerar boletim')
def gerar_boletim(boletim, somente_documentos=False, reprocessamento=False, task=None):
    lista = [boletim]
    task.count(lista)
    for boletim in task.iterate(lista):
        if boletim:
            boletim.gerar_pdf(somente_documentos=somente_documentos, reprocessamento=reprocessamento)
    task.finalize('Boletim gerado com sucesso.', '/admin/boletim_servico/boletimprogramado/')
