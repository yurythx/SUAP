from argparse import ArgumentParser

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from sentry_sdk import capture_exception, capture_message

from djtools.management.commands import BaseCommandPlus
from rh.importacao_siape.armazenamento import arquivos_da_pasta
from rh.importacao_siape.execucao import (
    ImportacaoNaoIniciada,
    apagar_pasta,
    executar_importacao,
    iniciar_importacao,
    workers_configurados,
)
from rh.importacao_siape.preparacao import ArquivoExtratorInvalido, criar_importacao
from rh.models import ImportacaoSiape, SituacaoImportacaoSiape

PASTA_EXTRATOR = 'rh/arquivos_siape'


# Para que serve: é o lado noturno da importação SIAPE, disparado pelo beat às 01:07 (`rh/beat.py`).
# Roda o que o operador agendou na tela e importa os zips que chegam à pasta do extrator sem passar
# pela tela, fora do horário de uso do sistema.
class Command(BaseCommandPlus):
    help = 'Importa os zips do extrator SIAPE enviados para a pasta do extrator'

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument('--pasta', default=PASTA_EXTRATOR)
        parser.add_argument('--log', dest='log', default='DEBUG', help='Mantido por compatibilidade; sem efeito.')

    # Para que serve: define a ordem da noite: primeiro as agendadas (o operador já escolheu os
    # arquivos), depois os zips da pasta; cada zip é importado com todos os arquivos reconhecidos.
    def handle(self, *args: object, **options: object) -> None:
        self._importar_agendadas()
        pasta = options['pasta']
        zips = [nome for nome in arquivos_da_pasta(pasta) if nome.endswith('.zip')]
        if not zips:
            self.stdout.write('Nenhum arquivo do extrator para importar.')
            return
        for nome in sorted(zips):
            self._importar(f'{pasta}/{nome}', nome)

    def _importar_agendadas(self) -> None:
        """Roda antes dos zips da pasta: importações agendadas pela tela, na ordem de envio."""
        agendadas = ImportacaoSiape.objects.filter(situacao=SituacaoImportacaoSiape.AGENDADA).order_by('enviado_em')
        for importacao in agendadas:
            if not self._importar_agendada(importacao):
                break

    def _importar_agendada(self, importacao: ImportacaoSiape) -> bool:
        """Retorna False quando as agendadas restantes da noite devem ser deixadas para depois: outra
        importação já está em execução. Uma recusa por outro motivo é reportada e o laço segue.
        """
        ids = importacao.arquivos.filter(selecionado=True).values_list('pk', flat=True)
        try:
            iniciar_importacao(importacao, ids)
        except ImportacaoNaoIniciada as erro:
            return self._tratar_recusa_agendada(importacao, erro)
        self._executar_agendada(importacao)
        return True

    def _tratar_recusa_agendada(self, importacao: ImportacaoSiape, erro: ImportacaoNaoIniciada) -> bool:
        mensagem = f'Importação #{importacao.pk}: {erro}'
        self.stderr.write(mensagem)
        if ImportacaoSiape.existe_em_execucao():
            capture_message(mensagem, level='warning')
            return False
        capture_exception(erro)
        return True

    def _executar_agendada(self, importacao: ImportacaoSiape) -> None:
        try:
            executar_importacao(importacao, workers_configurados())
        except Exception as erro:
            capture_exception(erro)
            self.stderr.write(f'Importação #{importacao.pk}: falha na importação: {erro}')
        else:
            self.stdout.write(f'Importação #{importacao.pk}: {importacao.get_situacao_display().lower()}.')

    def _importar(self, caminho: str, nome: str) -> None:
        if ImportacaoSiape.existe_em_execucao():
            mensagem = f'{nome}: já existe uma importação SIAPE em execução. Aguarde o término.'
            self.stderr.write(mensagem)
            capture_message(mensagem, level='warning')
            return
        with default_storage.open(caminho, 'rb') as arquivo:
            conteudo = arquivo.read()
        try:
            importacao = criar_importacao(nome, conteudo, origem='comando')
        except ArquivoExtratorInvalido as erro:
            self._retirar_da_fila(caminho, conteudo, nome, erro)
            return
        if self._iniciar(importacao, nome):
            self._executar(importacao, caminho, nome)

    def _retirar_da_fila(self, caminho: str, conteudo: bytes, nome: str, erro: ArquivoExtratorInvalido) -> None:
        """Zip inválido (corrompido, ou ainda sendo copiado para a pasta): renomeia para `.invalido`.

        Fora do filtro `*.zip`, ele não é tentado de novo toda noite, mas continua na pasta para
        diagnóstico — ou para ser renomeado de volta, se era só uma cópia incompleta.
        """
        mensagem = f'{nome}: {erro} Preservado como {nome}.invalido.'
        self.stderr.write(mensagem)
        capture_message(mensagem, level='warning')
        default_storage.save(f'{caminho}.invalido', ContentFile(conteudo))
        default_storage.delete(caminho)

    def _iniciar(self, importacao: ImportacaoSiape, nome: str) -> bool:
        try:
            iniciar_importacao(importacao, importacao.arquivos.filter(selecionado=True).values_list('pk', flat=True))
        except ImportacaoNaoIniciada as erro:
            # a importação recém-criada nunca chegou a rodar: não deixa órfã (arquivos extraídos +
            # registro em 'identificada') para o zip ser tentado de novo na próxima chamada do beat.
            self.stderr.write(f'{nome}: {erro}')
            apagar_pasta(importacao.pasta)
            importacao.delete()
            return False
        return True

    def _executar(self, importacao: ImportacaoSiape, caminho: str, nome: str) -> None:
        try:
            executar_importacao(importacao, workers_configurados())
        except Exception as erro:
            # `executar_importacao` já grava a situação final (FALHOU) e apaga a pasta antes de
            # relançar: aqui só reporta e segue para o próximo zip, sem interromper o `for` do `handle`.
            capture_exception(erro)
            self.stderr.write(f'{nome}: falha na importação #{importacao.pk}: {erro}')
        else:
            self.stdout.write(f'{nome}: importação #{importacao.pk} {importacao.get_situacao_display().lower()}.')
        finally:
            # concluída ou com falha, o zip não fica na pasta: o resultado está na importação registrada
            default_storage.delete(caminho)
