from django.utils.translation import gettext_lazy as _


#
# Situações do Plano de Dados Abertos (PDA)
# -----------------------------------------------------------
class SituacaoPDA:
    RASCUNHO = 1
    EM_APROVACAO = 2
    AGUARDANDO_PUBLICACAO = 3
    PUBLICADO = 4
    EM_EXECUCAO = 5
    EM_REVISAO = 6
    ENCERRADO = 7

    LABELS = {
        RASCUNHO: 'Rascunho',
        EM_APROVACAO: 'Em aprovação',
        AGUARDANDO_PUBLICACAO: 'Aguardando publicação',
        PUBLICADO: 'Publicado',
        EM_EXECUCAO: 'Em execução',
        EM_REVISAO: 'Em revisão',
        ENCERRADO: 'Encerrado',
    }

    @classmethod
    def get_choices(cls):
        return list(cls.LABELS.items())


# Estados de objetos no CKAN (datasets, organizações)
# -----------------------------------------------------------
class EstadoCKAN:
    ACTIVE = 'active'
    DELETED = 'deleted'

    ESTADOCKAN_DICT = {
        ACTIVE: 'Ativa',
        DELETED: 'Excluída',
    }

    @classmethod
    def get_choices(cls):
        return list(cls.ESTADOCKAN_DICT.items())


# Formatos de recursos no CKAN
# -----------------------------------------------------------
class FormatoRecurso:
    CSV = 'CSV'
    JSON = 'JSON'

    FORMATO_DICT = {
        CSV: 'CSV',
        JSON: 'JSON',
    }

    @classmethod
    def get_choices(cls):
        return list(cls.FORMATO_DICT.items())


# Periodicidade de atualização
# -----------------------------------------------------------
class Periodicidade:
    DIARIA = 1
    SEMANAL = 2
    MENSAL = 3
    TRIMESTRAL = 4
    SEMESTRAL = 5
    ANUAL = 6
    EVENTUAL = 99

    LABELS = {
        DIARIA: 'Diária',
        SEMANAL: 'Semanal',
        MENSAL: 'Mensal',
        TRIMESTRAL: 'Trimestral',
        SEMESTRAL: 'Semestral',
        ANUAL: 'Anual',
        EVENTUAL: 'Eventual',
    }

    @classmethod
    def get_choices(cls):
        return list(cls.LABELS.items())


class Situacao_GrupoTrabalho:
    ATIVO = 1
    FINALIZADO = 2
    CANCELADO = 3

    LABELS = {
        ATIVO: 'Ativo',
        FINALIZADO: 'Finalizado',
        CANCELADO: 'Cancelado',
    }

    @classmethod
    def get_choices(cls):
        return list(cls.LABELS.items())


class ValorAvaliacao:
    NAO_SE_APLICA = 0
    BAIXO = 1
    MEDIO = 2
    ALTO = 3

    LABELS = {
        NAO_SE_APLICA: 'Não se aplica',
        BAIXO: 'Baixo',
        MEDIO: 'Médio',
        ALTO: 'Alto',
    }

    @classmethod
    def get_choices(cls):
        return list(cls.LABELS.items())


class NotaAvaliacaoBaseDados:
    NAO_SE_APLICA = 0
    BAIXO = 1
    MEDIO = 2
    ALTO = 3

    LABELS = {
        NAO_SE_APLICA: 'Não se aplica',
        BAIXO: 'Baixo',
        MEDIO: 'Médio',
        ALTO: 'Alto',
    }

    @classmethod
    def get_choices(cls):
        return list(cls.LABELS.items())


class TipoVersao:
    MAJOR = 1
    MINOR = 2
    PATCH = 3

    @classmethod
    def get_choices(cls):
        return [
            (cls.MAJOR, _('Major - Alteração estrutural')),
            (cls.MINOR, _('Minor - Adição/remoção relevante')),
            (cls.PATCH, _('Patch - Correção pontual')),
        ]


class SituacaoLAI:
    PENDENTE = 1
    EM_ANALISE = 2
    LIBERADO = 3
    DEVOLVIDO = 4

    LABELS = {
        PENDENTE: 'Pendente',
        EM_ANALISE: 'Em análise do LAI',
        LIBERADO: 'Liberado',
        DEVOLVIDO: 'Devolvido para ajustes',
    }

    #: Classe de status do Design System para cada situação.
    CLASSES = {
        PENDENTE: 'status-alert',
        EM_ANALISE: 'status-info',
        LIBERADO: 'status-success',
        DEVOLVIDO: 'status-error',
    }

    @classmethod
    def get_choices(cls):
        return list(cls.LABELS.items())


class TipoEventoLAI:
    """Eventos da linha do tempo de um dataset no ciclo de deliberação LAI.

    Todo evento que muda ``PDABaseDados.situacao_lai`` tem um tipo aqui — é o que garante que a
    rastreabilidade não tenha buracos. ``ENVIO`` e ``REABERTURA_POR_EDICAO`` são automáticos
    (sem autor humano); os demais partem de uma ação de alguém.
    """

    ENVIO = 1
    LIBERACAO = 2
    DEVOLUCAO = 3
    REENVIO = 4
    REABERTURA_POR_EDICAO = 5

    LABELS = {
        ENVIO: 'Enviado para análise',
        LIBERACAO: 'Liberado pelo Responsável LAI',
        DEVOLUCAO: 'Devolvido para ajustes',
        REENVIO: 'Reenviado após ajustes',
        REABERTURA_POR_EDICAO: 'Reaberto por edição do conteúdo',
    }

    #: Eventos gerados pelo sistema, sem autor humano.
    AUTOMATICOS = frozenset({ENVIO, REABERTURA_POR_EDICAO})

    #: Eventos que exigem texto de quem os registra (parecer do LAI ou resposta do gestor).
    EXIGEM_TEXTO = frozenset({DEVOLUCAO, REENVIO})

    #: Classe do item na timeline do Design System.
    CLASSES = {
        ENVIO: 'info',
        LIBERACAO: 'success',
        DEVOLUCAO: 'danger',
        REENVIO: 'info',
        REABERTURA_POR_EDICAO: 'warning',
    }

    @classmethod
    def get_choices(cls):
        return list(cls.LABELS.items())


class ResultadoAtualizacao:
    """Desfecho de uma tentativa de atualização automática de uma base de dados."""

    SUCESSO = 1
    SEM_ALTERACAO = 2
    ESQUEMA_ALTERADO = 3
    BLOQUEADA_LAI = 4
    FALHA_DOWNLOAD = 5
    FALHA_CKAN = 6
    SEM_FONTE_AUTOMATICA = 7

    LABELS = {
        SUCESSO: 'Atualizada e publicada',
        SEM_ALTERACAO: 'Sem alteração no conteúdo',
        ESQUEMA_ALTERADO: 'Esquema alterado — devolvida ao LAI',
        BLOQUEADA_LAI: 'Bloqueada pela análise do LAI',
        FALHA_DOWNLOAD: 'Falha ao baixar a fonte',
        FALHA_CKAN: 'Falha ao publicar no CKAN',
        SEM_FONTE_AUTOMATICA: 'Sem fonte automática (atualização manual)',
    }

    # Desfechos que exigem ação de alguém — alimentam o farol do dashboard.
    PENDENTES = (ESQUEMA_ALTERADO, BLOQUEADA_LAI, FALHA_DOWNLOAD, FALHA_CKAN, SEM_FONTE_AUTOMATICA)

    #: Falhas técnicas, as únicas que contam na sequência de falhas consecutivas. Bloqueio do LAI
    #: e ausência de fonte automática são estados do fluxo, não defeito: interrompem a sequência.
    FALHAS = (FALHA_DOWNLOAD, FALHA_CKAN)

    #: Classe de status do Design System de cada desfecho, na tela da base de dados.
    CLASSES = {
        SUCESSO: 'status-success',
        SEM_ALTERACAO: 'status-success',
        ESQUEMA_ALTERADO: 'status-alert',
        BLOQUEADA_LAI: 'status-alert',
        FALHA_DOWNLOAD: 'status-error',
        FALHA_CKAN: 'status-error',
        SEM_FONTE_AUTOMATICA: 'status-alert',
    }

    @classmethod
    def get_choices(cls):
        return list(cls.LABELS.items())


class CondicaoAcaoAutomatica:
    """Condições que, quando satisfeitas no PDA, marcam automaticamente a ação da etapa como concluída."""

    BASES_VINCULADAS = 'bases_vinculadas'
    BASES_COM_RECURSO = 'bases_com_recurso'
    MATRIZ_FINALIZADA = 'matriz_finalizada'
    CONSULTA_PUBLICA_REALIZADA = 'consulta_publica_realizada'
    BASES_LIBERADAS_LAI = 'bases_liberadas_lai'
    BASES_SINCRONIZADAS_CKAN = 'bases_sincronizadas_ckan'
    GRUPO_TRABALHO_DEFINIDO = 'grupo_trabalho_definido'

    LABELS = {
        BASES_VINCULADAS: 'Bases vinculadas ao PDA',
        BASES_COM_RECURSO: 'Ao menos uma base com recurso',
        MATRIZ_FINALIZADA: 'Matriz de priorização finalizada',
        CONSULTA_PUBLICA_REALIZADA: 'Consulta pública cadastrada',
        BASES_LIBERADAS_LAI: 'Ao menos uma base liberada pelo LAI',
        BASES_SINCRONIZADAS_CKAN: 'Ao menos uma base sincronizada com o CKAN',
        GRUPO_TRABALHO_DEFINIDO: 'Grupo de trabalho definido',
    }

    @classmethod
    def get_choices(cls):
        return list(cls.LABELS.items())


# Metadados do conjunto de dados (DCAT-BR / Catálogo Nacional de Dados)
# -----------------------------------------------------------
# Os valores são os gravados nos ``extras`` do CKAN, com a grafia usada no formulário de
# catalogação do dados.gov.br, para que o portal federal os reconheça na federação.
class CoberturaEspacial:
    """Área geográfica coberta pelo conjunto (``dcterms:spatial``)."""

    NACIONAL = 'NACIONAL'
    REGIONAL = 'REGIONAL'
    ESTADUAL = 'ESTADUAL'
    MUNICIPAL = 'MUNICIPAL'

    LABELS = {
        NACIONAL: 'Nacional',
        REGIONAL: 'Regional',
        ESTADUAL: 'Estadual',
        MUNICIPAL: 'Municipal',
    }

    @classmethod
    def get_choices(cls):
        return list(cls.LABELS.items())


class GranularidadeEspacial:
    """Menor recorte geográfico em que os registros do conjunto podem ser agregados."""

    NACIONAL = 'NACIONAL'
    REGIONAL = 'REGIONAL'
    ESTADUAL = 'ESTADUAL'
    MUNICIPAL = 'MUNICIPAL'
    NAO_SE_APLICA = 'NAO_SE_APLICA'

    LABELS = {
        NACIONAL: 'Nacional',
        REGIONAL: 'Regional',
        ESTADUAL: 'Estadual',
        MUNICIPAL: 'Municipal (campus)',
        NAO_SE_APLICA: 'Não se aplica (dado agregado da instituição)',
    }

    @classmethod
    def get_choices(cls):
        return list(cls.LABELS.items())


class ObservanciaLegal:
    """Nível de acesso do conjunto (``dcterms:accessRights``)."""

    PUBLICO = 'PÚBLICO'
    RESTRITO = 'RESTRITO'
    PRIVADO = 'PRIVADO'

    LABELS = {
        PUBLICO: 'Público',
        RESTRITO: 'Restrito',
        PRIVADO: 'Privado',
    }

    @classmethod
    def get_choices(cls):
        return list(cls.LABELS.items())


class ODS:
    """Objetivos de Desenvolvimento Sustentável da Agenda 2030 aos quais o conjunto se relaciona."""

    LABELS = {
        1: 'Erradicação da Pobreza',
        2: 'Fome Zero e Agricultura Sustentável',
        3: 'Saúde e Bem-Estar',
        4: 'Educação de Qualidade',
        5: 'Igualdade de Gênero',
        6: 'Água Potável e Saneamento',
        7: 'Energia Limpa e Acessível',
        8: 'Trabalho Decente e Crescimento Econômico',
        9: 'Indústria, Inovação e Infraestrutura',
        10: 'Redução das Desigualdades',
        11: 'Cidades e Comunidades Sustentáveis',
        12: 'Consumo e Produção Responsáveis',
        13: 'Ação Contra a Mudança Global do Clima',
        14: 'Vida na Água',
        15: 'Vida Terrestre',
        16: 'Paz, Justiça e Instituições Eficazes',
        17: 'Parcerias e Meios de Implementação',
    }

    @classmethod
    def rotulo(cls, numero: int) -> str:
        """Número e nome do ODS; número fora da lista (o banco não valida as choices) sai cru."""
        nome = cls.LABELS.get(numero)
        return f'{numero} - {nome}' if nome else str(numero)

    @classmethod
    def get_choices(cls):
        return [(numero, cls.rotulo(numero)) for numero in cls.LABELS]
