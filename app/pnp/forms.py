from django.core.exceptions import ValidationError

from djtools import forms


class ImportarParquetForm(forms.FormPlus):
    """Base dos formulários de importação de arquivos Parquet exportados da PNP.

    As subclasses declaram em ``COLUNAS`` os nomes das colunas obrigatórias; as linhas
    lidas ficam disponíveis em ``self.linhas``, na mesma ordem das colunas declaradas.
    """

    SUBMIT_LABEL = 'Importar'
    COLUNAS: tuple[str, ...] = ()

    arquivo = forms.FileFieldPlus(label='Arquivo Parquet', required=True)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        colunas = '", "'.join(self.COLUNAS)
        self.fields['arquivo'].help_text = f'Arquivo .parquet exportado da PNP, com as colunas "{colunas}".'

    def clean_arquivo(self) -> object:
        arquivo = self.cleaned_data.get('arquivo')
        if not arquivo.name.lower().endswith('.parquet'):
            raise ValidationError('O formato do arquivo não é válido. Por favor, envie um arquivo no formato: .parquet.')
        # ponytail: import tardio, pyarrow é pesado e só é usado nesta importação
        import pyarrow.parquet as pq

        arquivo.seek(0)
        try:
            tabela = pq.read_table(arquivo, columns=list(self.COLUNAS))
        except Exception as e:
            raise ValidationError(f'Não foi possível ler o arquivo Parquet. Detalhe: {e}')
        if not tabela.num_rows:
            raise ValidationError('O arquivo não contém dados válidos.')
        self.processar(tabela, arquivo)
        return arquivo

    def processar(self, tabela, arquivo) -> None:
        """Materializa as linhas do arquivo em ``self.linhas``, descartando as incompletas."""
        linhas = ([str(linha[coluna]).strip() for coluna in self.COLUNAS] for linha in tabela.to_pylist())
        self.linhas = [linha for linha in linhas if all(linha)]
        if not self.linhas:
            raise ValidationError('O arquivo não contém dados válidos.')


class ImportarParquetGrandeForm(ImportarParquetForm):
    """Variante para arquivos grandes demais para trafegar como argumento da task.

    Em vez de materializar as linhas, guarda o arquivo no storage temporário e expõe o
    caminho em ``self.caminho``; a task o lê de lá.
    """

    def processar(self, tabela, arquivo) -> None:
        from djtools.storages.utils import get_temp_storage

        arquivo.seek(0)
        self.caminho = get_temp_storage().save(f'pnp/{arquivo.name}', arquivo)


class ImportarEstruturaPNPForm(ImportarParquetForm):
    COLUNAS = ('codigo', 'nome')


class ImportarAreaTematicaPNPForm(ImportarParquetForm):
    COLUNAS = ('codigo', 'nome')


class ImportarEixoPNPForm(ImportarParquetForm):
    COLUNAS = ('codigo', 'nome')


class ImportarServidorPNPForm(ImportarParquetForm):
    COLUNAS = ('matricula', 'nome', 'cpf', 'unidade', 'codigo_estrutura')


class ImportarMatriculaPNPForm(ImportarParquetGrandeForm):
    COLUNAS = ('matricula', 'cpf', 'nome', 'curso', 'unidade', 'codigo_estrutura')
