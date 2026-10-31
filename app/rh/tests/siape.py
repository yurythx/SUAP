"""Apoio dos testes do importador SIAPE.

Funções, não fixtures: cada teste chama o que precisa, dentro da própria transação. A carga das
tabelas acessórias passa pelo motor de `rh.importacao_siape` (o `ImportadorSIAPE().run()` antigo
foi removido, #17415), então quem a usa precisa das fixtures `importacao_serial` e
`limpar_importacoes` de `rh/tests/conftest.py`.
"""

import gzip
import os

from django.conf import settings

from rh.importador import ImportadorSIAPE


ARQUIVOS_SIAPE = os.path.join(settings.BASE_DIR, 'rh', 'tests', 'arquivos_siape_novo')


def _registro_servidor1_base():
    return {
        'GR-MATRICULA': '264350000010',
        'IT-NU-CPF': '00397340214',
        'IT-NO-SERVIDOR': 'NOME SOBRENOME DO TERCEIRO-NOME',
        'IT-CO-ESTADO-CIVIL': '01',
        'IT-CO-NACIONALIDADE': '1',
        'IT-SG-UF-NATURALIDADE-SERVIDOR': 'RN',
        'IT-CO-PAIS': '024',
        'IT-AN-CHEGADA-ESTRANGEIRO': '',
        'IT-NO-MAE': 'NOME DA MAE DO SERVIDOR',
        'IT-NU-PIS-PASEP': '12345678909',
        'IT-SG-REGIME-JURIDICO': 'EST',
        'IT-CO-SITUACAO-SERVIDOR': '01',
        'IT-CO-BANCO-PGTO-SERVIDOR': '001',
        'IT-CO-AGENCIA-BANCARIA-PGTO-SERV': '03293X',
        'IT-NU-CCOR-PGTO-SERVIDOR': '123456',
        'IT-CO-GRUPO-OCOR-AFASTAMENTO': '00',
        'IT-CO-OCOR-AFASTAMENTO': '000',
        'IT-DA-INICIO-OCOR-AFASTAMENTO': '00000000',
        'IT-DA-TERMINO-OCOR-AFASTAMENTO': '00000000',
        'IT-CO-DIPL-AFASTAMENTO': '00',
        'IT-DA-PUBL-DIPL-AFASTAMENTO': '00000000',
        'IT-NU-DIPL-AFASTAMENTO': '         ',
        'IT-CO-GRUPO-OCOR-EXCLUSAO': '00',
        'IT-CO-OCOR-EXCLUSAO': '000',
        'IT-DA-OCOR-EXCLUSAO-SERV': '00000000',
        'IT-CO-DIPL-EXCLUSAO': '00',
        'IT-DA-PUBL-DIPL-EXCLUSAO': '00000000',
        'IT-NU-DIPL-EXCLUSAO': '         ',
        'IT-CO-GRUPO-OCOR-INATIVIDADE': '00',
        'IT-CO-OCOR-INATIVIDADE': '000',
        'IT-DA-OCOR-INATIVIDADE-SERV': '00000000',
        'IT-CO-DIPL-INATIVIDADE': '00',
        'IT-DA-PUBL-DIPL-INATIVIDADE': '00000000',
        'IT-NU-DIPL-INATIVIDADE': '         ',
        'IT-CO-GRUPO-CARGO-EMPREGO': '707',
        'IT-CO-CARGO-EMPREGO': '001',
        'IT-CO-CLASSE': '0D',
        'IT-CO-PADRAO': '405',
        'IT-CO-NIVEL': '000',
        'IT-DA-OCUPACAO-CARGO-EMPREGO': '20101001',
        'IT-DA-SAIDA-CARGO-EMPREGO': '20110105',
        'IT-CO-UORG-LOTACAO-SERVIDOR': '000000000',
        'IT-DA-LOTACAO': '00000000',
        'IT-DA-EXCLUSAO-INSTITUIDOR': '00000000',
    }


def _registro_servidor2_base():
    return {
        'GR-MATRICULA': '264350000010',
        'IT-DA-NASCIMENTO': '19820729',
        'IT-CO-SEXO': 'F',
        'IT-QT-DEPENDENTE-IR': '2',
        'IT-NU-CARTEIRA-TRABALHO': '00123456789',
        'IT-NU-SERIE-CARTEIRA-TRABALHO': '01234',
        'IT-SG-UF-CTRA-SERVIDOR': 'RN',
        'IT-DA-PRIMEIRO-EMPREGO': '20000908',
        'IT-DA-CADASTRAMENTO-SERVIDOR': '20051011',
        'IT-CO-NIVEL-ESCOLARIDADE': '13',
        'IT-CO-GRUPO-OCOR-INGR-ORGAO': '00',
        'IT-CO-OCOR-INGR-ORGAO': '000',
        'IT-DA-OCOR-INGR-ORGAO-SERV': '00000000',
        'IT-CO-DIPL-INGR-ORGAO': '00',
        'IT-DA-PUBL-DIPL-INGR-ORGAO': '00000000',
        'IT-NU-DIPL-INGR-ORGAO': '         ',
        'IT-CO-GRUPO-OCOR-INGR-SPUB': '00',
        'IT-CO-OCOR-INGR-SPUB': '000',
        'IT-DA-OCOR-INGR-SPUB-SERV': '00000000',
        'IT-CO-DIPL-INGR-SPUB': '00',
        'IT-DA-PUBL-DIPL-INGR-SPUB': '00000000',
        'IT-NU-DIPL-INGR-SPUB': '         ',
        # Datas de função iguais (zeradas) -> sem entrada/saída de função a processar
        'IT-SG-FUNCAO': '   ',
        'IT-CO-NIVEL-FUNCAO': '0000',
        'IT-IN-OPCAO-FUNCAO': ' ',
        'IT-DA-INGRESSO-FUNCAO': '00000000',
        'IT-DA-SAIDA-FUNCAO': '00000000',
        'IT-CO-UORG-FUNCAO': '000000000',
        'IT-SG-NOVA-FUNCAO': '   ',
        'IT-CO-NIVEL-NOVA-FUNCAO': '0000',
        'IT-IN-OPCAO-NOVA-FUNCAO': ' ',
        'IT-DA-INGRESSO-NOVA-FUNCAO': '00000000',
        'IT-DA-SAIDA-NOVA-FUNCAO': '00000000',
        'IT-CO-UORG-NOVA-FUNCAO': '000000000',
        'IT-CO-ATIVIDADE-FUNCAO': '0000',
        'IT-CO-ATIVIDADE-NOVA-FUNCAO': '0000',
        'IT-CO-JORNADA-TRABALHO': '40',
    }


def _registro_servidor3_base():
    return {
        'GR-MATRICULA': '264350000010',
        'IT-CO-VAGA': '0000000',
        'IT-NU-MATRICULA-ANTERIOR': '0000000',
        'IT-CO-REGISTRO-GERAL': '1234567       ',
        'IT-SG-ORGAO-EXPEDIDOR-IDEN': 'SSP  ',
        'IT-DA-EXPEDICAO-IDEN': '20100101',
        'IT-SG-UF-IDEN': 'RN',
        'IT-DA-OBITO': '00000000',
        'IT-NU-TITULO-ELEITOR': '0001234567890',
        'IT-IN-OPERADOR-RAIOX': '0',
        'IT-CO-GRUPO-OCOR-INGR-SPUB-POSSE': '00',
        'IT-CO-OCOR-INGR-SPUB-POSSE': '000',
        'IT-DA-OCOR-INGR-SPUB-POSSE': '00000000',
        'IT-CO-DIPL-INGR-SPUB-POSSE': '00',
        'IT-DA-PUBL-DIPL-INGR-SPUB-POSSE': '00000000',
        'IT-NU-DIPL-INGR-SPUB-POSSE': '         ',
        'IT-CO-UORG-EXERCICIO-SERV': '000000000',
        'IT-CO-TITULACAO-FORMACAO-RH': '25',
    }


def executar_importacao():
    """Importa o zip de teste inteiro (todo arquivo reconhecido) pelo motor, em série."""
    from rh.importacao_siape.execucao import executar_importacao as executar
    from rh.importacao_siape.execucao import iniciar_importacao
    from rh.importacao_siape.preparacao import criar_importacao

    importacao = criar_importacao('extracao.zip', zip_do_extrator(), origem='tela')
    iniciar_importacao(importacao, importacao.arquivos.filter(selecionado=True).values_list('pk', flat=True))
    return executar(importacao, workers=1)


def importador_com_tabelas():
    """Importador novo, com as tabelas acessórias já carregadas por uma importação completa."""
    executar_importacao()
    return ImportadorSIAPE()


def registro_servidor1(**overrides):
    """Registro do layout servidor1; sobrescreva só os campos do cenário."""
    return {**_registro_servidor1_base(), **overrides}


def registro_servidor2(**overrides):
    return {**_registro_servidor2_base(), **overrides}


def registro_servidor3(**overrides):
    return {**_registro_servidor3_base(), **overrides}


def zip_do_extrator() -> bytes:
    """Zip no formato do extrator: pares NOME.REF.gz/NOME.TXT.gz, em UTF-8."""
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as zip_:
        for nome in sorted(os.listdir(ARQUIVOS_SIAPE)):
            if nome.endswith(('.TXT', '.REF')):
                with open(os.path.join(ARQUIVOS_SIAPE, nome), encoding='latin-1') as fh:
                    zip_.writestr(f'{nome}.gz', gzip.compress(fh.read().encode('utf-8')))
    return buffer.getvalue()
