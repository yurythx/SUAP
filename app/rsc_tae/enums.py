class Ordem:
    UM = 1
    DOIS = 2
    TRES = 3
    QUATRO = 4
    CINCO = 5
    SEIS = 6

    LABELS = (
        (UM, 'I'),
        (DOIS, 'II'),
        (TRES, 'III'),
        (QUATRO, 'IV'),
        (CINCO, 'V'),
        (SEIS, 'VI'),
    )

    @classmethod
    def get_choices(cls):
        return list(cls.LABELS)


class SituacaoProcesso:
    AGUARDANDO_PREENCHIMENTO = 1
    # 2 = AGUARDANDO_AVALIADOR — legado, não usado no fluxo atual
    EM_ANALISE = 3
    DEFERIDO = 4
    INDEFERIDO = 5
    AGUARDANDO_VALIDACAO_DOCUMENTO_PRELIMINAR = 6
    AGUARDANDO_CORRECAO = 7
    # 8 = AGUARDANDO_ACEITE_AVALIADOR — legado, não usado no fluxo atual
    AGUARDANDO_CRSC = 9

    # Mantidos como constantes para compatibilidade com dados existentes no banco
    AGUARDANDO_AVALIADOR = 2
    AGUARDANDO_ACEITE_AVALIADOR = 8

    LABELS = (
        (AGUARDANDO_PREENCHIMENTO, 'Aguardando Preenchimento'),
        (AGUARDANDO_CORRECAO, 'Aguardando Correção'),
        (AGUARDANDO_VALIDACAO_DOCUMENTO_PRELIMINAR, 'Aguardando Validação'),
        (EM_ANALISE, 'Em Análise'),
        (AGUARDANDO_CRSC, 'Aguardando Deliberação da CRSC'),
        (DEFERIDO, 'Deferido'),
        (INDEFERIDO, 'Indeferido'),
        # Legados — exibidos apenas para processos criados antes do sorteio automático
        (AGUARDANDO_AVALIADOR, 'Aguardando Avaliador (legado)'),
        (AGUARDANDO_ACEITE_AVALIADOR, 'Aguardando Aceite do Avaliador (legado)'),
    )

    # ------------------------------------------------------------------ #
    # Grupos semânticos — substituem literais espalhados pelo código       #
    # ------------------------------------------------------------------ #

    # Estados em que o servidor pode editar o preenchimento
    EDITAVEIS_PELO_SERVIDOR = (AGUARDANDO_PREENCHIMENTO, AGUARDANDO_CORRECAO)

    # Estados em que avaliadores podem avaliar anexos
    AVALIAVEIS = (EM_ANALISE,)

    # Estados terminais (processo encerrado)
    FINAIS = (DEFERIDO, INDEFERIDO)

    # Estados em que o processo espera por OUTRA pessoa (comissão ou avaliadores) e, portanto,
    # ocupa uma posição de fila. Ficam de fora os estados em que a ação é do próprio servidor
    # (EDITAVEIS_PELO_SERVIDOR) — ali não há fila, a bola está com ele — e os FINAIS.
    # Os dois legados entram para que processos antigos também mostrem a posição.
    COM_FILA_DE_ESPERA = (
        AGUARDANDO_VALIDACAO_DOCUMENTO_PRELIMINAR,
        EM_ANALISE,
        AGUARDANDO_CRSC,
        AGUARDANDO_AVALIADOR,
        AGUARDANDO_ACEITE_AVALIADOR,
    )

    # ------------------------------------------------------------------ #
    # Mapa declarativo de transições válidas (fluxo atual)                 #
    # ------------------------------------------------------------------ #

    TRANSICOES = {
        AGUARDANDO_PREENCHIMENTO: (
            AGUARDANDO_VALIDACAO_DOCUMENTO_PRELIMINAR,
            EM_ANALISE,  # doc. preliminar já validado → sorteio automático
        ),
        AGUARDANDO_CORRECAO: (
            AGUARDANDO_VALIDACAO_DOCUMENTO_PRELIMINAR,
            EM_ANALISE,  # doc. preliminar já validado → sorteio automático
        ),
        AGUARDANDO_VALIDACAO_DOCUMENTO_PRELIMINAR: (
            EM_ANALISE,  # RH valida → sorteio automático → EM_ANALISE
            AGUARDANDO_CORRECAO,
        ),
        EM_ANALISE: (
            AGUARDANDO_CRSC,  # todos os avaliadores finalizaram → aguarda CRSC
            AGUARDANDO_CORRECAO,
        ),
        AGUARDANDO_CRSC: (
            DEFERIDO,
            INDEFERIDO,
            # Devolução ao servidor decidida já na deliberação: apaga avaliações e
            # deliberações, porque foram medidas contra um preenchimento que vai mudar.
            AGUARDANDO_CORRECAO,
        ),
        # Reversão administrativa da deliberação final (command reverter_deliberacao_final):
        # devolve um processo finalizado à deliberação da CRSC. Registrada via transicionar().
        DEFERIDO: (AGUARDANDO_CRSC,),
        INDEFERIDO: (AGUARDANDO_CRSC,),
        # Legados — mantidos para processos antigos que ainda estão nesses estados
        AGUARDANDO_AVALIADOR: (EM_ANALISE, AGUARDANDO_CORRECAO),
        AGUARDANDO_ACEITE_AVALIADOR: (EM_ANALISE, AGUARDANDO_CORRECAO),
    }

    @classmethod
    def get_choices(cls):
        return list(cls.LABELS)

    @classmethod
    def pode_transicionar(cls, de, para) -> bool:
        """Retorna True se a transição de *de* para *para* é permitida."""
        return para in cls.TRANSICOES.get(de, ())

    @classmethod
    def transicoes_validas(cls, situacao) -> tuple:
        """Retorna a tupla de situações para as quais *situacao* pode transicionar."""
        return cls.TRANSICOES.get(situacao, ())


class SituacaoAvaliacaoItem:
    PENDENTE = 1
    DEFERIDO = 2
    INDEFERIDO = 3

    LABELS = (
        (PENDENTE, 'Pendente'),
        (DEFERIDO, 'Deferido'),
        (INDEFERIDO, 'Indeferido'),
    )

    @classmethod
    def get_choices(cls):
        return list(cls.LABELS)


class MotivoIndeferimento:
    """Motivos estruturados de indeferimento da deliberação final (constatações do parecer).

    Cada membro da comissão que vota pelo indeferimento marca um ou mais motivos; o parecer
    conclusivo exibe a união distinta dos motivos marcados, com a redação do Decreto nº
    13.048/2026 e os valores dinâmicos (pontos/critérios/incisos) preenchidos automaticamente.
    """

    PONTUACAO_MINIMA = 1
    CRITERIO_VINCULADO = 2
    MEMORIAL_SEM_DEMONSTRACAO = 3
    INTERSTICIO = 4
    ESTAGIO_PROBATORIO = 5

    # Rótulos curtos — exibidos nos checkboxes do formulário de voto
    LABELS = (
        (PONTUACAO_MINIMA, 'Pontuação e/ou quantidade mínima de critérios não atingida (art. 5º)'),
        (CRITERIO_VINCULADO, 'Nenhum critério específico vinculado comprovado (arts. 3º e 5º)'),
        (MEMORIAL_SEM_DEMONSTRACAO, 'Memorial não demonstra saberes/competências além das atribuições ordinárias (art. 5º, § 4º, e art. 15)'),
        (INTERSTICIO, 'Interstício de 3 anos da última concessão não cumprido (art. 11)'),
        (ESTAGIO_PROBATORIO, 'Servidor(a) em estágio probatório (art. 12)'),
    )

    # Redação do Decreto — impressa no parecer conclusivo. Placeholders preenchidos pela view.
    TEXTOS_PARECER = {
        PONTUACAO_MINIMA: (
            'o(a) servidor(a) não atingiu a pontuação mínima e/ou a quantidade mínima de critérios '
            'específicos exigidos para o RSC-PCCTAE {sigla}, conforme o art. 5º do Decreto nº 13.048/2026, '
            'tendo alcançado {pontos} pontos e {itens} critérios específicos, quando o mínimo exigido é '
            'de {pontos_min} pontos e {itens_min} critérios'
        ),
        CRITERIO_VINCULADO: (
            'não foi comprovado o atendimento de, ao menos, um critério específico vinculado aos incisos '
            '{incisos} do art. 3º do Decreto nº 13.048/2026, conforme exigido pelo art. 5º do Decreto '
            'nº 13.048/2026'
        ),
        MEMORIAL_SEM_DEMONSTRACAO: (
            'não restou demonstrado, no memorial, o desenvolvimento de saberes, competências, inovação, '
            'ampliação de responsabilidades ou obtenção de resultados institucionais relevantes, nos termos '
            'do art. 5º, § 4º, e do art. 15 do Decreto nº 13.048/2026, tratando-se de atividades inerentes '
            'ao desempenho ordinário das atribuições do cargo'
        ),
        INTERSTICIO: ('não foi cumprido o interstício de 3 (três) anos contado da última concessão, conforme o art. 11 do Decreto nº 13.048/2026'),
        ESTAGIO_PROBATORIO: ('o(a) servidor(a) encontra-se em estágio probatório, nos termos do art. 12 do Decreto nº 13.048/2026'),
    }

    # Ordem canônica de exibição no parecer (ordem das constatações no Decreto)
    ORDEM = (PONTUACAO_MINIMA, CRITERIO_VINCULADO, MEMORIAL_SEM_DEMONSTRACAO, INTERSTICIO, ESTAGIO_PROBATORIO)

    @classmethod
    def get_choices(cls):
        return list(cls.LABELS)

    @classmethod
    def consolidar(cls, listas_de_motivos) -> list[int]:
        """União distinta dos motivos de vários votos, na ordem canônica do Decreto.

        Aceita iterável de iteráveis (motivos de cada voto); ignora códigos desconhecidos.
        """
        marcados = {int(m) for lista in listas_de_motivos for m in (lista or [])}
        return [codigo for codigo in cls.ORDEM if codigo in marcados]


class SituacaoDocumentoPreliminar:
    PENDENTE = 1
    VALIDADO = 2
    CORRECAO_SOLICITADA = 3

    LABELS = (
        (PENDENTE, 'Pendente'),
        (VALIDADO, 'Validado'),
        (CORRECAO_SOLICITADA, 'Correção solicitada'),
    )

    @classmethod
    def get_choices(cls):
        return list(cls.LABELS)


class TipoDocumentoPreliminar:
    DIPLOMA_CERTIFICADO = 1
    HOMOLOGACAO_ESTAGIO_PROBATORIO = 2

    LABELS = (
        (DIPLOMA_CERTIFICADO, 'Diploma/certificado'),
        (HOMOLOGACAO_ESTAGIO_PROBATORIO, 'Homologação do estágio probatório'),
    )

    @classmethod
    def get_choices(cls):
        return list(cls.LABELS)


class AreaCorrecao:
    """Áreas do processo que o RH pode apontar como necessitando correção.

    As áreas de documento (DIPLOMA/HOMOLOGACAO) usam os mesmos valores de
    TipoDocumentoPreliminar, então a conversão área -> tipo de documento é direta.
    """

    DIPLOMA_CERTIFICADO = 1
    HOMOLOGACAO_ESTAGIO_PROBATORIO = 2
    FORMULARIO = 3
    MEMORIAL = 4

    LABELS = (
        (DIPLOMA_CERTIFICADO, 'Diploma/certificado'),
        (HOMOLOGACAO_ESTAGIO_PROBATORIO, 'Homologação do estágio probatório'),
        (FORMULARIO, 'Formulário de pontuação'),
        (MEMORIAL, 'Memorial descritivo'),
    )

    # Áreas que correspondem a um documento preliminar (mesmo valor em TipoDocumentoPreliminar).
    AREAS_DOCUMENTO = (DIPLOMA_CERTIFICADO, HOMOLOGACAO_ESTAGIO_PROBATORIO)

    @classmethod
    def get_choices(cls):
        return list(cls.LABELS)
