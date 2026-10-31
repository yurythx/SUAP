from model_utils import Choices


class Nacionalidade:
    BRASILEIRO_NATO = 1
    BRASILEIRO_NATZ = 2
    EQUIPARADO = 3
    ESTRANGEIRO = 4

    choices = Choices(
        (BRASILEIRO_NATO, 'Brasileiro Nato', 'Brasileiro Nato'),
        (BRASILEIRO_NATZ, 'Brasileiro Naturalizado', 'Brasileiro Naturalizado'),
        (EQUIPARADO, 'Equiparado', 'Equiparado'),
        (ESTRANGEIRO, 'Estrangeiro', 'Estrangeiro'),
    )


class FormaParticipacaoEvento:
    PRESENCIAL = 1
    ONLINE = 2

    choices = Choices(
        (PRESENCIAL, 'presencial', 'Presencial'),
        (ONLINE, 'online', 'Online'),
    )


class TipoSubmissao:
    TIPO_SUBMISSAO_TEXTO = 'TEX'
    TIPO_SUBMISSAO_ARQUIVO = 'ARQ'

    choices = Choices(
        (TIPO_SUBMISSAO_TEXTO, 'tex', 'Por texto'),
        (TIPO_SUBMISSAO_ARQUIVO, 'arq', 'Por arquivo'),
    )


class TipoLimitePorTexto:
    PALAVRAS = 'P'
    CARACTERES = 'C'

    choices = Choices(
        (PALAVRAS, 'P', 'palavras'),
        (CARACTERES, 'C', 'caracteres'),
    )


class ResultadoAvaliacao:
    APROVADO = 'AP'
    REPROVADO = 'RE'
    PENDENTE = 'PE'

    choices = Choices(
        (APROVADO, 'AP', 'Aprovado'),
        (REPROVADO, 'RE', 'Reprovado'),
        (PENDENTE, 'PE', 'Pendente de Avaliação'),
    )


class SituacaoConvite:
    NAO_ENVIADO = 'CNE'
    ENVIADO = 'CE'
    ACEITO = 'CA'
    RECUSADO = 'CR'

    choices = Choices(
        (NAO_ENVIADO, 'CNE', 'Convite não enviado'),
        (ENVIADO, 'CA', 'Convite enviado'),
        (ACEITO, 'CA', 'Convite aceito'),
        (RECUSADO, 'CR', 'Convite recusado'),
    )


class TipoPergunta:
    SUBJETIVA_LONGA = 'SUB_L'
    SUBJETIVA_CURTA = 'SUB_C'
    OBJETIVA = 'OBJ'
    MULTIPLA_ESCOLHA = 'MULTI'
    ESCALA = 'ESC'

    choices = Choices(
        (SUBJETIVA_LONGA, 'SUB_L', 'Subjetiva Longa'),
        (SUBJETIVA_CURTA, 'SUB_C', 'Subjetiva Curta'),
        (OBJETIVA, 'OBJ', 'Objetiva'),
        (MULTIPLA_ESCOLHA, 'MULTI', 'Múltipla-escolha'),
        (ESCALA, 'ESC', 'Escala'),
    )


class TipoQuestionario:
    INSCRICAO = 'INSC'
    AVALIACAO = 'AVAL'

    choices = Choices(
        (INSCRICAO, 'INSC', 'Inscrição'),
        (AVALIACAO, 'AVAL', 'Avaliação'),
    )


class SituacaoSubmissao:
    SUBMETIDO = 'SUB'
    EM_AVALIACAO = 'EAV'
    CORRECOES_SOLICITADAS = 'COR'
    RESSUBMETIDO = 'RES'
    AGUARDANDO_AVALIACAO_PRESENCIAL = 'AAP'
    AVALIADO = 'AVA'
    REMOVIDO_DUPLICIDADE = 'RDU'

    choices = Choices(
        (SUBMETIDO, SUBMETIDO, 'Submetido'),
        (EM_AVALIACAO, EM_AVALIACAO, 'Em avaliação'),
        (CORRECOES_SOLICITADAS, CORRECOES_SOLICITADAS, 'Correções solicitadas'),
        (RESSUBMETIDO, RESSUBMETIDO, 'Ressubmetido'),
        (AGUARDANDO_AVALIACAO_PRESENCIAL, AGUARDANDO_AVALIACAO_PRESENCIAL, 'Aguardando avaliação presencial'),
        (AVALIADO, AVALIADO, 'Avaliado'),
        (REMOVIDO_DUPLICIDADE, REMOVIDO_DUPLICIDADE, 'Removido por duplicidade'),
    )


class EtapaPeriodoSubmissao:
    SUBMISSAO = 'SUB'
    AVALIACAO = 'AVA'
    CORRECOES = 'COR'
    REAVALIACAO = 'REA'
    AVALIACAO_PRESENCIAL = 'AVP'
    RESULTADO_FINAL = 'REF'

    choices = Choices(
        (SUBMISSAO, SUBMISSAO, 'Submissão'),
        (AVALIACAO, AVALIACAO, 'Avaliação'),
        (CORRECOES, CORRECOES, 'Correções'),
        (REAVALIACAO, REAVALIACAO, 'Reavaliação'),
        (AVALIACAO_PRESENCIAL, AVALIACAO_PRESENCIAL, 'Avaliação presencial'),
        (RESULTADO_FINAL, RESULTADO_FINAL, 'Resultado final'),
    )
    avaliacoes_choices = Choices(
        (AVALIACAO, AVALIACAO, 'Avaliação'),
        (REAVALIACAO, REAVALIACAO, 'Reavaliação'),
        (AVALIACAO_PRESENCIAL, AVALIACAO_PRESENCIAL, 'Avaliação presencial'),
    )


class Recomendacao:
    ACEITAR = 1
    CORRIGIR = 0
    REJEITAR = -1

    choices = Choices(
        (CORRIGIR, CORRIGIR, 'Solicitar correções'),
        (ACEITAR, ACEITAR, 'Aceitar'),
        (REJEITAR, REJEITAR, 'Rejeitar'),
    )

    todas = [(ACEITAR, 'Aceitar'), (CORRIGIR, 'Solicitar correções'), (REJEITAR, 'Rejeitar')]
    aceita_ou_rejeitar = [(ACEITAR, 'Aceitar'), (REJEITAR, 'Rejeitar')]
