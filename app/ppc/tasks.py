import tempfile

from djtools.assincrono import task


@task('Gerar minuta de PPC')
def gerar_minuta_ppc(request, projeto, task=None):
    from ppc import views

    task.start_progress(total=3)
    task.update_progress(1)
    pdf = views.minuta_ppc_pdf(request, projeto)
    task.update_progress(2)
    tmp = tempfile.NamedTemporaryFile(suffix='.pdf', mode='w+b', delete=False)
    tmp.write(pdf.content)
    tmp.close()
    task.update_progress(3)
    return task.finalize('Arquivo gerado com sucesso.', '..', file_path=tmp.name)


@task('Gerar bibliografia de PPC')
def gerar_bibliografia(projeto, task=None):
    from ppc.utils import processar_bibliografia

    projeto.bibliografia_html = processar_bibliografia(projeto, funcao_iterator=task.iterate)
    projeto.save()

    task.finalize('Bibliografia processada com sucesso.', projeto.get_absolute_url('tab=bibliografia'))
