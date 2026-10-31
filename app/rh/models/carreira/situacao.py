from djtools.db import models


class ServidoresCarreiraManager(models.Manager):
    """
    Servidores sem ocorrência de exclusão.

    É utiliazdo no relatório de aniversariantes (pois exclui os falecidos) e nas
    funções gerais da app `patrimonio`.
    """

    def get_queryset(self):
        return super().get_queryset().filter(codigo__in=Situacao.situacoes_servidores_de_carreira())


class Situacao(models.ModelPlus):
    SEARCH_FIELDS = ('codigo', 'nome', 'nome_siape')

    # situações SIAPE (efetivos)
    ATIVO_PERMANENTE = '01'
    CEDIDO_REQUISITADO = '03'
    ATIVO_EM_OUTRO_ORGAO = '08'

    # situações SIAPE (temporários)
    CONTRATO_TEMPORARIO = '12'
    CONT_PROF_SUBSTITUTO = '52'
    CONTR_PROF_VISITANTE = '53'
    CONT_PROF_TEMPORARIO = '54'

    # outras situações SIAPE
    ESTAGIARIO = '66'
    ESTAGIARIO_SIGEPE = '70'

    EXERC_DESCENT_CARREI = '18'
    EXERCICIO_PROVISORIO = '19'
    COLABORADOR_PCCTAE = '41'
    COLABORADOR_ICT = '42'

    EXERC_7_ART93_8112 = '44'

    REQ_DE_OUTROS_ORGAOS = '14'
    SEM_VINCULO = '05'
    NOMEADO_CARGO_COMIS = '04'

    APOSENTADOS = '02'

    INSTITUIDOR_PENSAO = '15'
    PENSIONISTA = '84'

    EXCEDENTE_A_LOTACAO = '11'
    EXERC_LEI_13681_18 = '80'

    SITUACOES_ATIVOS = [
        ATIVO_PERMANENTE,
        CEDIDO_REQUISITADO,
        ATIVO_EM_OUTRO_ORGAO,
        COLABORADOR_PCCTAE,
        CONT_PROF_SUBSTITUTO,
        CONT_PROF_TEMPORARIO,
        COLABORADOR_ICT,
        ESTAGIARIO,
        ESTAGIARIO_SIGEPE,
        EXERCICIO_PROVISORIO,
        CONTR_PROF_VISITANTE,
        EXERC_DESCENT_CARREI,
        NOMEADO_CARGO_COMIS,
        EXERC_7_ART93_8112,
        EXCEDENTE_A_LOTACAO,
        EXERC_LEI_13681_18,
    ]

    SITUACOES_EFETIVOS = [ATIVO_PERMANENTE, ATIVO_EM_OUTRO_ORGAO, EXCEDENTE_A_LOTACAO]

    SITUACOES_SUBSTITUTOS_OU_TEMPORARIOS = [CONT_PROF_SUBSTITUTO, CONT_PROF_TEMPORARIO]

    SITUACOES_TEMPORARIOS = [CONTRATO_TEMPORARIO, CONT_PROF_SUBSTITUTO, CONT_PROF_TEMPORARIO]

    SITUACOES_EFETIVOS_E_TEMPORARIOS = SITUACOES_EFETIVOS + SITUACOES_TEMPORARIOS

    SITUACOES_EM_EXERCICIO_NO_INSTITUTO = (
        ATIVO_PERMANENTE,
        CONT_PROF_SUBSTITUTO,
        CONT_PROF_TEMPORARIO,
        CONTR_PROF_VISITANTE,
        COLABORADOR_PCCTAE,
        EXERCICIO_PROVISORIO,
        COLABORADOR_ICT,
        EXERC_DESCENT_CARREI,
        EXERC_7_ART93_8112,
        NOMEADO_CARGO_COMIS,
        EXERC_LEI_13681_18,
        EXCEDENTE_A_LOTACAO,
    )

    codigo = models.CharField(max_length=10, null=True, unique=True)
    nome_siape = models.CharField(max_length=40)
    nome = models.CharField(max_length=40)
    excluido = models.BooleanField(default=False)

    objects = models.Manager()
    servidores_de_carreira = ServidoresCarreiraManager()

    class Meta:
        db_table = 'situacao'
        verbose_name = 'Situação'
        verbose_name_plural = 'Situações'
        ordering = ['nome']

    def __str__(self):
        return f'{self.nome} - {self.codigo}'

    @staticmethod
    def situacoes_usadas_no_instituto():
        from ..carreira import Servidor

        situacoes_servidores = Servidor.objects.filter(situacao__isnull=False).values_list('situacao', flat=True).order_by('situacao').distinct()
        return Situacao.objects.filter(id__in=situacoes_servidores)

    @staticmethod
    def situacoes_servidores_de_carreira():
        return (
            Situacao.ATIVO_PERMANENTE,
            Situacao.ATIVO_EM_OUTRO_ORGAO,
            Situacao.CONTRATO_TEMPORARIO,
            Situacao.CONT_PROF_SUBSTITUTO,
            Situacao.CONT_PROF_TEMPORARIO,
            Situacao.EXERC_DESCENT_CARREI,
            Situacao.EXERCICIO_PROVISORIO,
            Situacao.COLABORADOR_PCCTAE,
            Situacao.COLABORADOR_ICT,
            Situacao.EXERC_7_ART93_8112,
        )

    @staticmethod
    def situacoes_servidores_de_carreira_vinculada_ao_orgao():
        return (Situacao.ATIVO_PERMANENTE, Situacao.ATIVO_EM_OUTRO_ORGAO)

    @staticmethod
    def situacoes_carreira_em_exercicio_provisorio():
        return (Situacao.EXERCICIO_PROVISORIO, Situacao.COLABORADOR_PCCTAE, Situacao.COLABORADOR_ICT, Situacao.EXERC_7_ART93_8112)

    @staticmethod
    def situacoes_sem_vinculo_com_administracao_publica():
        return (Situacao.SEM_VINCULO, Situacao.NOMEADO_CARGO_COMIS)

    @staticmethod
    def situacoes_siape_estagiarios():
        return (Situacao.ESTAGIARIO, Situacao.ESTAGIARIO_SIGEPE)

    @property
    def is_temporaria(self):
        return self.codigo in self.SITUACOES_TEMPORARIOS
