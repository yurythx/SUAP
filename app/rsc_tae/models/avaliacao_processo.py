import hashlib
import json

from djtools.db import models
from django.db.models.functions import Now
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from rsc_tae.enums import SituacaoAvaliacaoItem, SituacaoProcesso


class AvaliacaoProcessoRSCTae(models.ModelPlus):
    RESULTADO_CHOICES = (
        (SituacaoProcesso.DEFERIDO, 'Deferido'),
        (SituacaoProcesso.INDEFERIDO, 'Indeferido'),
    )

    RESPOSTA_PENDENTE = 1
    RESPOSTA_ACEITE = 2
    RESPOSTA_RECUSA = 3
    RESPOSTA_IMPEDIMENTO = 4

    RESPOSTA_CHOICES = (
        (RESPOSTA_PENDENTE, 'Pendente'),
        (RESPOSTA_ACEITE, 'Aceito'),
        (RESPOSTA_RECUSA, 'Recusado'),
        (RESPOSTA_IMPEDIMENTO, 'Impedimento declarado'),
    )

    processo = models.ForeignKeyPlus(
        'rsc_tae.ProcessoRSCTae',
        verbose_name=_('Processo'),
        on_delete=models.CASCADE,
        related_name='avaliacoes_por_avaliador',
    )
    avaliador_vinculo = models.ForeignKeyPlus(
        'comum.Vinculo',
        verbose_name=_('Avaliador'),
        on_delete=models.CASCADE,
        related_name='rsc_tae_avaliacoes_processo_set',
    )

    aceite = models.BooleanField(
        _('Aceite'),
        null=True,
        blank=True,
        help_text=_('Indica se o avaliador aceitou (True), recusou (False) ou ainda não respondeu (None) a avaliação.'),
    )
    resposta = models.PositiveSmallIntegerField(
        _('Resposta'),
        choices=RESPOSTA_CHOICES,
        default=RESPOSTA_PENDENTE,
        help_text=_('Resposta do avaliador ao sorteio: pendente, aceite, recusa ou impedimento/suspeição (Lei 9.784/99).'),
    )
    motivo_recusa = models.TextField(
        _('Motivo da recusa'),
        blank=True,
        help_text=_('Motivo informado pelo avaliador ao recusar a avaliação.'),
    )
    motivo_impedimento = models.TextField(
        _('Motivo do impedimento/suspeição'),
        blank=True,
        help_text=_('Declaração de impedimento ou suspeição conforme Lei nº 9.784/99. Obrigatório quando resposta=IMPEDIMENTO.'),
    )
    data_notificacao_sorteio = models.DateTimeField(
        _('Data de notificação do sorteio'),
        null=True,
        blank=True,
        help_text=_('Quando o avaliador foi notificado do sorteio. Base para o cálculo do prazo de avaliação.'),
    )
    data_limite_avaliacao = models.DateFieldPlus(
        _('Data-limite para avaliação'),
        null=True,
        blank=True,
        help_text=_('Prazo final (dias úteis a partir da notificação) para o avaliador concluir a avaliação.'),
    )
    substituido = models.BooleanField(
        _('Substituído'),
        default=False,
        help_text=_('True quando este avaliador foi substituído por outro sorteio ou removido administrativamente. Registro mantido para auditoria.'),
    )

    pontuacao_final = models.DecimalField(
        _('Pontuação final'),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('Pontuação final registrada no momento da finalização da avaliação deste avaliador.'),
    )
    resultado = models.PositiveIntegerField(
        _('Resultado'),
        choices=RESULTADO_CHOICES,
        null=True,
        blank=True,
        help_text=_('Resultado individual desta avaliação: Deferido ou Indeferido.'),
    )
    itens_validados = models.PositiveIntegerField(
        _('Itens validados'),
        null=True,
        blank=True,
        help_text=_('Quantidade de itens validados por este avaliador no momento da finalização.'),
    )
    data_finalizacao = models.DateTimeField(_('Data de finalização'), null=True, blank=True)
    finalizada = models.BooleanField(_('Finalizada'), default=False, help_text=_('Indica se a avaliação foi finalizada pelo avaliador.'))
    motivo_indeferimento = models.TextField(_('Motivo do indeferimento'), blank=True)

    # ------------------------------------------------------------------ #
    # Assinatura de integridade — gerada no momento da finalização        #
    # ------------------------------------------------------------------ #
    assinatura_hash = models.CharField(
        _('Hash da assinatura'),
        max_length=64,
        null=True,
        blank=True,
        help_text=_('SHA-256 do conteúdo serializado no momento da finalização. Permite detectar alterações posteriores nos dados avaliados.'),
    )
    assinatura_conteudo = models.TextField(
        _('Conteúdo da assinatura'),
        null=True,
        blank=True,
        help_text=_('JSON com os dados que geraram o hash: avaliador, avaliado, nível, resultado, pontuação e cada item avaliado individualmente.'),
    )

    data_cadastro = models.DateTimeField(_('Data de cadastro'), auto_now_add=True, db_default=Now())
    data_ultima_alteracao = models.DateTimeField(_('Data de última alteração'), auto_now=True, db_default=Now())

    class Meta:
        verbose_name = _('Avaliação do processo (RSC TAE)')
        verbose_name_plural = _('Avaliações do processo (RSC TAE)')
        ordering = ('-data_ultima_alteracao',)
        constraints = [
            models.UniqueConstraint(
                fields=['processo', 'avaliador_vinculo'],
                name='uq_rsc_tae_avaliacao_processo_por_avaliador',
            )
        ]

    def __str__(self):
        return f'Processo {self.processo_id} - {self.avaliador_vinculo}'

    @property
    def estah_finalizada(self):
        return self.data_finalizacao is not None

    @property
    def situacao(self):
        if self.resultado == SituacaoProcesso.DEFERIDO:
            return 'Deferido'
        elif self.resultado == SituacaoProcesso.INDEFERIDO:
            return 'Indeferido'
        else:
            return 'Pendente'

    @classmethod
    def reativar_ou_criar(cls, processo, avaliador_vinculo, data_limite, agora=None):
        """(Re)ativa a avaliação de *avaliador_vinculo* no *processo*, criando-a se não existir.

        Ponto único de (re)inclusão de avaliador (sorteio e substituição). Como há
        constraint de unicidade por (processo, avaliador_vinculo), a re-inclusão de um
        avaliador substituído anteriormente reaproveita a linha existente — e é
        obrigatório limpar o flag ``substituido``, senão a avaliação fica "fantasma"
        (invisível para contagens, média e publicação no Portal) mesmo após finalizada.
        Se a avaliação reaproveitada ainda não foi finalizada, renova também o aceite,
        a notificação e o prazo; se já foi finalizada, preserva o conteúdo assinado.
        """
        agora = agora or timezone.now()
        avaliacao, criada = cls.objects.get_or_create(
            processo=processo,
            avaliador_vinculo=avaliador_vinculo,
            defaults={
                'aceite': True,
                'resposta': cls.RESPOSTA_ACEITE,
                'data_notificacao_sorteio': agora,
                'data_limite_avaliacao': data_limite,
            },
        )
        if not criada:
            avaliacao.substituido = False
            if not avaliacao.finalizada:
                avaliacao.aceite = True
                avaliacao.resposta = cls.RESPOSTA_ACEITE
                avaliacao.data_notificacao_sorteio = agora
                avaliacao.data_limite_avaliacao = data_limite
            avaliacao.save()
        return avaliacao

    # ------------------------------------------------------------------ #
    # Assinatura de integridade                                            #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _resultado_label(resultado):
        if resultado == SituacaoProcesso.DEFERIDO:
            return 'DEFERIDO'
        if resultado == SituacaoProcesso.INDEFERIDO:
            return 'INDEFERIDO'
        return 'PENDENTE'

    @staticmethod
    def _situacao_anexo_label(situacao):
        if situacao == SituacaoAvaliacaoItem.DEFERIDO:
            return 'DEFERIDO'
        if situacao == SituacaoAvaliacaoItem.INDEFERIDO:
            return 'INDEFERIDO'
        return 'PENDENTE'

    @staticmethod
    def _calcular_hash(conteudo_dict):
        """SHA-256 do JSON canonizado (chaves ordenadas, UTF-8)."""
        payload = json.dumps(conteudo_dict, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()

    @classmethod
    def _construir_conteudo(cls, avaliacao_processo, avaliacoes_anexos):
        """
        Monta o dict canônico que representa o conteúdo assinado.

        *avaliacoes_anexos* deve ser um queryset ou lista de
        ``AvaliacaoAnexoRSCTae`` já carregados do banco.
        """
        processo = avaliacao_processo.processo
        avaliador = avaliacao_processo.avaliador_vinculo
        nivel = processo.nivel_requisitado

        return {
            'processo_id': processo.pk,
            'avaliado_vinculo_id': processo.vinculo_id,
            'avaliado_nome': str(processo.vinculo.pessoa.nome),
            'nivel_requisitado_id': nivel.pk,
            'nivel_requisitado_nome': str(nivel),
            'nivel_pontuacao_minima': str(nivel.pontuacao_minima),
            'avaliador_vinculo_id': avaliador.pk,
            'avaliador_nome': str(avaliador.pessoa.nome),
            'resultado': cls._resultado_label(avaliacao_processo.resultado),
            'pontuacao_final': str(avaliacao_processo.pontuacao_final or '0'),
            'itens_validados': avaliacao_processo.itens_validados,
            'data_finalizacao': (avaliacao_processo.data_finalizacao.isoformat() if avaliacao_processo.data_finalizacao else None),
            'avaliacoes_anexos': [
                {
                    'anexo_id': av.anexo_id,
                    'situacao': cls._situacao_anexo_label(av.situacao),
                    'pontuacao_validada': str(av.pontuacao_validada or '0'),
                    'observacao': av.observacao or '',
                }
                for av in sorted(avaliacoes_anexos, key=lambda a: a.anexo_id)
            ],
        }

    @classmethod
    def gerar_assinatura(cls, avaliacao_processo):
        """
        Gera e persiste o hash e o conteúdo de assinatura para uma
        ``AvaliacaoProcessoRSCTae`` já finalizada.

        Deve ser chamado logo após o ``update()`` que grava
        ``pontuacao_final``, ``resultado`` e ``data_finalizacao``.
        Executa ``refresh_from_db`` internamente para garantir dados
        consistentes com o banco.
        """
        from rsc_tae.models.avaliacao import AvaliacaoAnexoRSCTae

        avaliacao_processo.refresh_from_db()

        avaliacoes_anexos = list(
            AvaliacaoAnexoRSCTae.objects.filter(
                anexo__processo=avaliacao_processo.processo,
                avaliador_vinculo=avaliacao_processo.avaliador_vinculo,
            ).order_by('anexo_id')
        )

        conteudo = cls._construir_conteudo(avaliacao_processo, avaliacoes_anexos)
        conteudo_json = json.dumps(conteudo, sort_keys=True, ensure_ascii=False, default=str)
        hash_valor = hashlib.sha256(conteudo_json.encode('utf-8')).hexdigest()

        cls.objects.filter(pk=avaliacao_processo.pk).update(
            assinatura_conteudo=conteudo_json,
            assinatura_hash=hash_valor,
        )

        return conteudo_json, hash_valor

    def verificar_integridade(self):
        """
        Verifica se os dados atuais do banco correspondem ao conteúdo assinado.

        Retorna um dict com as chaves:

        ``status``:
            - ``'nao_assinado'``     — ``assinatura_hash`` não foi gravado
            - ``'hash_invalido'``    — o JSON armazenado foi adulterado (hash não bate)
            - ``'integro'``          — dados atuais idênticos ao conteúdo assinado
            - ``'alterado'``         — algum campo foi modificado após a assinatura

        ``diff`` (presente apenas em ``'alterado'``):
            Dict com as chaves alteradas, cada uma contendo
            ``{'original': ..., 'atual': ...}``.
        """
        from rsc_tae.models.avaliacao import AvaliacaoAnexoRSCTae

        if not self.assinatura_hash or not self.assinatura_conteudo:
            return {'status': 'nao_assinado'}

        # 1. Verifica integridade do próprio conteúdo armazenado
        hash_do_conteudo_armazenado = hashlib.sha256(self.assinatura_conteudo.encode('utf-8')).hexdigest()
        if hash_do_conteudo_armazenado != self.assinatura_hash:
            return {
                'status': 'hash_invalido',
                'detalhe': 'O conteúdo armazenado não corresponde ao hash registrado — possível adulteração direta no banco.',
            }

        # 2. Reconstrói o conteúdo a partir do estado atual do banco
        self.refresh_from_db()
        avaliacoes_atuais = list(
            AvaliacaoAnexoRSCTae.objects.filter(
                anexo__processo=self.processo,
                avaliador_vinculo=self.avaliador_vinculo,
            ).order_by('anexo_id')
        )
        conteudo_atual = self.__class__._construir_conteudo(self, avaliacoes_atuais)
        conteudo_original = json.loads(self.assinatura_conteudo)

        if conteudo_atual == conteudo_original:
            return {'status': 'integro'}

        # 3. Identifica as diferenças campo a campo
        diff = {}
        todas_chaves = set(conteudo_original) | set(conteudo_atual)
        for chave in todas_chaves:
            orig = conteudo_original.get(chave)
            atual = conteudo_atual.get(chave)
            if orig != atual:
                diff[chave] = {'original': orig, 'atual': atual}

        return {'status': 'alterado', 'diff': diff}
