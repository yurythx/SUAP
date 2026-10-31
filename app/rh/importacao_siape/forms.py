"""Formulário de upload do zip do extrator SIAPE, usado pela tela `views.importacao_siape_lista`."""

from __future__ import annotations

from django.core.files.uploadedfile import UploadedFile

from djtools import forms


# Para que serve: barra na própria tela um arquivo que claramente não é o zip do extrator (ex.: o
# `.TXT` avulso), com mensagem de campo, antes de ler o conteúdo. A validação do conteúdo do zip
# fica em `preparacao.criar_importacao`.
class ImportacaoSiapeUploadForm(forms.FormPlus):
    """Formulário de upload do zip do extrator SIAPE: exige um único campo de arquivo `.zip`."""

    arquivo = forms.FileFieldPlus(label='Arquivo do extrator (.zip)', required=True)

    def clean_arquivo(self) -> UploadedFile:
        """Valida que o arquivo enviado tem extensão `.zip`.

        Raises:
            forms.ValidationError: se o nome do arquivo não terminar em `.zip`.
        """
        arquivo = self.cleaned_data['arquivo']
        if not arquivo.name.lower().endswith('.zip'):
            raise forms.ValidationError('Envie o arquivo compactado (.zip) gerado pelo extrator SIAPE.')
        return arquivo
