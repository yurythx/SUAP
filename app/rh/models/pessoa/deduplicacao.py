from djtools.db import models


class DeduplicacaoPessoa(models.ModelPlus):
    """Plano, auditoria e mapa de id antigo → novo da deduplicação de PessoaFisica.

    Escrito pelo comando ``deduplicar_pessoas`` (fase ``planejar``) e pela entrada de dados
    (``divergencia_entrada``). ``pf_id``/``sobrevivente_id`` não são FK: a PF perdedora é apagada.
    """

    CPF_ANULADO = 'cpf_anulado'
    PASSAPORTE_ANULADO = 'passaporte_anulado'
    PASSAPORTE_PREENCHIDO = 'passaporte_preenchido'
    PAIS_PREENCHIDO = 'pais_preenchido'
    SINTETICO = 'sintetico'
    MESCLADA = 'mesclada'
    SEPARADA = 'separada'
    APAGADA = 'apagada'
    CAMPO_DESCARTADO = 'campo_descartado'
    DIVERGENCIA_ENTRADA = 'divergencia_entrada'
    ERRO = 'erro'
    ACAO_CHOICES = [
        [CPF_ANULADO, 'CPF anulado'],
        [PASSAPORTE_ANULADO, 'Passaporte anulado'],
        [PASSAPORTE_PREENCHIDO, 'Passaporte copiado do aluno'],
        [PAIS_PREENCHIDO, 'País de origem inferido do aluno'],
        [SINTETICO, 'Documento sintético'],
        [MESCLADA, 'Mesclada'],
        [SEPARADA, 'Separada'],
        [APAGADA, 'Apagada (sem relacionamento)'],
        [CAMPO_DESCARTADO, 'Campo descartado'],
        [DIVERGENCIA_ENTRADA, 'Divergência na entrada'],
        [ERRO, 'Erro'],
    ]

    pf_id = models.IntegerField(db_index=True)
    sobrevivente_id = models.IntegerField(null=True, db_index=True)
    documento = models.CharField(max_length=80, blank=True)
    acao = models.CharField(max_length=30, choices=ACAO_CHOICES, db_index=True)
    campo = models.CharField(max_length=100, blank=True)
    valor_original = models.TextField(blank=True)
    motivo = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    aplicado_em = models.DateTimeField(null=True, db_index=True)

    class Meta:
        verbose_name = 'Deduplicação de Pessoa'
        verbose_name_plural = 'Deduplicações de Pessoas'

    def __str__(self) -> str:
        return f'{self.acao} PF {self.pf_id}'
