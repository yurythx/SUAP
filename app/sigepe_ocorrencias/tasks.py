from djtools.assincrono import task
from sigepe_ocorrencias.gerar_dados import GeracaoOcorrenciaSigepe


@task('Gerar arquivo de ocorrências sigepe')
def gerar_ocorrencias(pacote_ocorrencia, user, task=None):
    task.start_progress()

    ocorrencia = GeracaoOcorrenciaSigepe()
    ocorrencia.gerar(pacote_ocorrencia=pacote_ocorrencia, tipo_arquivo=1, user=user)

    task.finalize('Arquivo gerado.', '..')


@task('Gerar atualização do arquivo de ocorrências sigepe')
def gerar_ocorrencias_atualizacao(pacote_ocorrencia, user, task=None):
    task.start_progress()

    ocorrencia = GeracaoOcorrenciaSigepe()
    ocorrencia.gerar(pacote_ocorrencia=pacote_ocorrencia, tipo_arquivo=2, user=user)

    task.finalize('Arquivo atualizado.', '..')
