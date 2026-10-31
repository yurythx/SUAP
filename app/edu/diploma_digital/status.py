DOCUMENTO_VALIDO = 10
REVOGADO = 14

STATUS_PADRAO = [
    [0, 'Dados de processamento instanciados'],
    [1, 'Documento preparado para geração'],
    [2, 'Documento gerado'],
    [3, 'Inicializando processamento de assinaturas'],
    [4, 'Processo de assinatura iniciado'],
    [5, 'Coletando Assinatura'],
    [6, 'Documento Assinado'],
    [7, 'Preparando processo de registro'],
    [8, 'Registro iniciado'],
    [9, 'Documento Processado'],
    [DOCUMENTO_VALIDO, 'Documento válido'],
]

STATUS_ESPECIAIS = [
    [11, 'Documento suspenso'],
    [12, 'Inicializando revogação'],
    [13, 'Revogando'],
    [REVOGADO, 'Revogado'],
]

ERRO_PREPARANDO_DOCUMENT0 = 500
ERRO_GERANDO_DOCUMENTO = 501
ERRO_INICIALIZANDO_ASSINATURA = 502
ERRO_FINALIZANDO_ASSINATURA = 503
ERRO_INICIALIZANDO_REGISTRO = 504
ERRO_FINALIZANDO_REGISTRO = 505
ERRO_REVOGANDO_DOCUMENTO = 506

STATUS_ERRO_DOCUMENTO = [
    [ERRO_PREPARANDO_DOCUMENT0, 'Erro preparando geração do documento'],
    [ERRO_GERANDO_DOCUMENTO, 'Erro gerando documento;'],
    [ERRO_INICIALIZANDO_ASSINATURA, 'Erro inicializando processamento de assinaturas'],
    [ERRO_FINALIZANDO_ASSINATURA, 'Erro finalizando processamento de assinaturas'],
    [ERRO_INICIALIZANDO_REGISTRO, 'Erro Iniciando processo de registro'],
    [ERRO_FINALIZANDO_REGISTRO, 'Erro finalizando processo de registro'],
    [ERRO_REVOGANDO_DOCUMENTO, 'Erro revogando documento'],
]

STATUS_ERRO = [[998, 'Erro de conectividade com o RAP']]
