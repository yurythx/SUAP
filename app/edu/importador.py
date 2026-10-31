from enum import Enum


class Estado(Enum):
    AC = 12
    AL = 27
    AM = 13
    AP = 16
    BA = 29
    CE = 23
    DF = 53
    ES = 32
    GO = 52
    MA = 21
    MG = 31
    MS = 50
    MT = 51
    PA = 15
    PB = 25
    PE = 26
    PI = 22
    PR = 41
    RJ = 33
    RN = 24
    RO = 11
    RR = 14
    RS = 43
    SC = 42
    SE = 28
    SP = 35
    TO = 17


class NivelEnsino(Enum):
    FUNDAMENTAL = 1
    GRADUACAO = 3
    MEDIO = 2
    POS_GRADUACAO = 4


class Modalidade(Enum):
    LICENCIATURA = 2
    ENGENHARIA = 4
    FIC = 8
    MESTRADO = 9
    ESPECIALIZACAO = 10
    INTEGRADO = 11
    INTEGRADO_EJA = 12
    SUBSEQUENTE = 13
    TECNOLOGIA = 14
    APERFEICOAMENTO = 15
    DOUTORADO = 16
    PROEJA_FIC_FUNDAMENTAL = 17


class SituacaoMatricula(Enum):
    MATRICULADO = 1
    TRANCADO = 2
    JUBILADO = 3
    TRANSFERIDO_INTERNO = 4
    CONCLUDENTE = 5
    CONCLUIDO = 6
    FALECIDO = 7
    AFASTADO = 8
    EVASAO = 9
    CANCELADO = 10
    TRANSFERIDO_EXTERNO = 11
    ESTAGIARIO_CONCLUDENTE = 12
    AGUARDANDO_COLACAO_DE_GRAU = 13
    CERTIFICADO_ENEM = 14
    AGUARDANDO_SEMINARIO = 15
    AGUARDANDO_ENADE = 16
    INTERCAMBIO = 17
    EGRESSO = 18
    FORMADO = 19
    CANCELAMENTO_COMPULSORIO = 20
    MATRICULA_VINCULO_INSTITUCIONAL = 21
    CANCELAMENTO_POR_DESLIGAMENTO = 97
    CANCELAMENTO_POR_DUPLICIDADE = 98
    TRANCADO_VOLUNTARIAMENTE = 99
    NAO_CONCLUIDO = 100
    TRANSFERIDO_SUAP = 101


class SituacaoMatriculaPeriodo(Enum):
    EM_ABERTO = 1
    MATRICULADO = 2
    TRANCADA = 3
    CANCELADA = 4
    AFASTADO = 5
    TRANSF_EXTERNA = 6
    TRANSF_INSTITUICAO = 7
    TRANSF_TURNO = 8
    TRANSF_CURSO = 9
    DEPENDENCIA = 10
    APROVADO = 11
    REPROVADO = 12
    VINDO_DE_TRANSFERENCIA = 13
    JUBILADO = 14
    EVASAO = 15
    REPROVADO_POR_FALTA = 16
    ESTAGIO_MONOGRAFIA = 17
    PERIODO_FECHADO = 18
    FECHADO_COM_PENDENCIA = 19
    APROVEITA_MODULO = 20
    MATRICULA_VINCULO_INSTITUCIONAL = 21
    CERTIFICADO_ENEM = 22
    CANCELAMENTO_COMPULSORIO = 23
    INTERCAMBIO = 24

    TRANCADA_VOLUNTARIAMENTE = 99
    TRANSFERIDO_SUAP = 100


class SituacaoMatriculaDiario(Enum):
    CURSANDO = 1
    APROVADO = 2
    REPROVADO = 3
    PROVA_FINAL = 4
    REPROVADO_POR_FALTA = 5
    TRANCADO = 6
    CANCELADO = 7
    DISPENSADO = 8
    PENDENTE = 9
    APROVADO_REPROVADO_MODULO = 10
    APROVEITAMENTO_ESTUDO = 11
    CERTIFICACAO_CONHECIMENTO = 12
    TRANSFERIDO = 13


class DAO:
    def importar_cursos_campus(self):
        """
        Importa os cursos do sistema legado para o Suap. Caso o curso já exista, ele deve ser atualizado.
        Classe e atributos a serem preenchidos:
            - CursoCampus
                codigo_academico
                descricao
                descricao_historico
                ativo
                codigo
                modalidade
                data_inicio
                exige_enade
        :return: nada
        """
        raise NotImplementedError('Método não-implementado')

    def importar_polos_ead(self):
        """
        Importa os cursos do sistema legado para o Suap. Caso o polo já exista, ele deve ser atualizado.
        Classe e atributos a serem preenchidos:
            - Polo
                codigo_academico
                descricao
                sigla
        :return: nada
        """
        raise NotImplementedError('Método não-implementado')

    def importar_alunos(self, prefixo_matricula=None, forcar_importacao=False):
        """
        Importa os alunos do sistema legado para o Suap. A importação pode ser total ou parcial baseada em um prefixo da matrícula do aluno.
        Por padrão, apenas alunos que ainda não foram migrados para o Suap, ou seja, alunos cuja matriz ainda não foi definida, deve ser atualizado.
        Classe e atributos a serem preenchidos:
            - Pessoa Física
                nome
                cpf
                nascimento_data
                sexo
                rg
                rg_uf
                rg_orgao
                rg_data
            - Aluno
                pessoa_fisica
                situacao
                curso_campus
                codigo_academico
                codigo_academico_pf
                matricula
                data_matricula
                dt_conclusao_curso
                periodo_atual
                ano_letivo
                periodo_letivo
                ira
                ano_let_prev_conclusao
                renda_per_capita
                numero_rg
                uf_emissao_rg
                orgao_emissao_rg
                data_emissao_rg
                turno
                forma_ingresso
                nome_mae
                nome_pai
                pai_falecido
                mae_falecida
                logradouro
                numero
                complemento
                cep
                telefone_principal
                telefone_secundario
                numero_titulo_eleitor
                zona_titulo_eleitor
                secao
                data_emissao_titulo_eleitor
                numero_carteira_reservista
                regiao_carteira_reservista
                serie_carteira_reservista
                ano_carteira_reservista
                numero_certidao
                folha_certidao
                livro_certidao
                data_emissao_certidao
                matricula_certidao
                nacionalidade
                polo
                data_expedicao_diploma
                alterado_em
        :param prefixo_matricula: prefixo que deve constar na matrícula do aluno. Ex: 20171
        :param forcar_importacao: flag indicado que alunos já migrados (com o campus matriz já definido) deve ser atualizado novamente
        :return: nada
        """
        raise NotImplementedError('Método não-implementado')

    def importar_matriculas_periodo(self, prefixo_matricula=None, forcar_importacao=False):
        """
        Importa os registros de matrícula em período dos alunos do sistema legado para o Suap. A importação pode ser total ou parcial baseada em um prefixo da matrícula do aluno.
        Por padrão, apenas registros de alunos que ainda não foram migrados para o Suap, ou seja, alunos cuja matriz ainda não foi definida, devem ser atualizados.
        Classe e atributos a serem preenchidos:
            - Pessoa Física
        :param prefixo_matricula: prefixo que deve constar na matrícula do aluno. Ex: 20171
        :param forcar_importacao: flag indicado que os registros de alunos já migrados (com o campus matriz já definido) deve ser atualizado novamente
        :return:
        """
        raise NotImplementedError('Método não-implementado')

    def importar_historico_resumo(
        self, matriculas, matriz_id, ano_letivo, periodo_letivo, processo=None, validacao=True, ignorar_ultimo_periodo=False
    ):
        """
        Importa os registros de notas/frequências das discipinas cursadas no sistema legado para o Suap.
            - MatriculaDiarioResumida
                media_final_disciplina (inteiro de 0 a 100)
                frequencia  (inteiro de 0 a 100)
                situacao (deve ser mapeada para uma constante na enumeração SituacaoMatriculaDiario, exceto CURSANDO, PROVA_FINAL)
                equivalencia_componente (chave primária da instância da classe EquivalenciaComponenteQAcademico que deve ser criada pela função para possibiliar o mapeamento da disciplina no sistema legado com o Suap.
                matricula_periodo (chave primária do registro de matrícula em período no Suap)
                cod_professor (chave primária do professor no sistema legado)
                nome_professor (nome do professor que lecionou a disciplina no sistema legado)
                titularidade_professor (titulação do professor que lecionou a disciplina no sistema legado)
                cod_diario_pauta (chave primária do diário no sistema legado)
                conceito (representação conceitual caso a disciplina seja avaliada por conceito no sistema legado)
        :param matriculas: lista contendo as matrículas do aluno cujo histórico deve ser importado.
        :param matriz_id: a matriz dos alunos
        :param ano_letivo: ano letivo
        :param periodo_letivo: período letivo
        :param processo: instancia de Task
        :param validacao: flag indicado se a importação deve ser efetivada ou se consistem apenas de um processo de validação
        :param ignorar_ultimo_periodo:  flag indicado que os registros do último período em que o aluno está matriculado deve ser ignorado
        :return: se a flag "validacao" for igual a True, a função deve retornar uma lista de tuplas contendo dois items em cada tupla.
        O primeiro item deve ser uma instância de Aluno e a segunda uma lista contendo strings informado erros de validação.
        """
        raise NotImplementedError('Método não-implementado')
