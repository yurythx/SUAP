from django import forms

CODIFICACAO_ARQUIVOS_IMPORTACAO = 'latin-1'


def compara_modelo(arq, modelo_layout):
    ini = 0
    for metadado in modelo_layout['campos']:
        tipo = modelo_layout['campos'][metadado]['tipo']
        tamanho = modelo_layout['campos'][metadado]['tamanho']
        fim = ini + tamanho
        if tipo == 'N':
            if arq[ini:fim].strip().isdigit() or arq[ini:fim].strip() == '':
                pass
            else:
                raise forms.ValidationError(
                    'Layout inválido! Campo {}-"{}" igual a "{}"?'.format(metadado, modelo_layout['campos'][metadado]['nome'], arq[ini:fim])
                )

        ini = fim


def compara_arquivo_ao_modelo(cleaned_data, modelo):
    if cleaned_data:
        cleaned_data.seek(0)
        primeira_linha = None
        for linha in cleaned_data.readlines():
            primeira_linha = str(linha, CODIFICACAO_ARQUIVOS_IMPORTACAO)
            break
        cleaned_data.seek(0)
        compara_modelo(primeira_linha, modelo)
    return cleaned_data
