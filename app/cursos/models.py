from datetime import date, datetime

from dateutil.relativedelta import relativedelta
from django.apps.registry import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models.aggregates import Sum
from django.db.models.query import QuerySet
from django.db.transaction import atomic
from django.template.loader import get_template
from django.utils.safestring import mark_safe

from comum.models import User
from cursos.enums import SituacaoCurso, SituacaoDetalhamentoAtividadeParticipante, SituacaoParticipante, TipoCurso
from djtools.choices import Meses
from djtools.db import models
from djtools.templatetags.filters import format_money
from djtools.utils import datas_entre, send_notification
from documento_eletronico.models import Documento, DocumentoTexto, ModeloDocumento
from ponto.models import DebitoExternoCadastro, RecessoOpcao, RecessoOpcaoEscolhida
from ponto.utils import Periodo
from protocolo.models import Processo
from rh.models import Servidor, UnidadeOrganizacional


class HorasPermitidas(models.ModelPlus):
    """
    São quantidades possíveis de serem escolhidos na ``CotaAnualServidor``. As quantidades padrão são 120 e 240 horas.
    """

    qtd_horas = models.FloatField(unique=True)
    default = models.BooleanField('Default?', default=False)

    class Meta:
        verbose_name = 'Horas Permitidas'
        verbose_name_plural = 'Horas Permitidas'

    def __str__(self):
        return str(self.qtd_horas)

    def save(self, *args, **kwargs):
        if self.default is True:
            HorasPermitidas.objects.all().update(default=False)
        super().save(*args, **kwargs)


class Atividade(models.ModelPlus):
    SEARCH_FIELDS = ['descricao']
    """
    São as atividades a serem desempenhadas por um servidor em ``HorasTrabalhadas``.
    """
    descricao = models.TextField('Descrição', unique=True)
    valor_hora = models.DecimalFieldPlus('Valor da Hora')
    ativa = models.BooleanField('Ativa?', default=True)

    class Meta:
        verbose_name = 'Atividade'
        verbose_name_plural = 'Atividades'
        ordering = ['descricao']

    def __str__(self):
        return f'{self.descricao} ({format_money(self.valor_hora)})'


class Curso(models.ModelPlus):
    """
    Representa tanto um curso quanto um concurso com participação do servidor.
    """

    SEARCH_FIELDS = ['descricao']

    descricao = models.TextField('Descrição')
    ano_pagamento = models.ForeignKeyPlus(
        'comum.Ano',
        on_delete=models.CASCADE,
        verbose_name='Ano Previsto da Atividade',
        help_text='Ano referente ao pagamento das horas trabalhadas neste Curso/Concurso.',
    )
    edital = models.FileFieldPlus('Edital', upload_to='cursos/editais', blank=True)
    processos = models.ManyToManyFieldPlus(Processo, blank=True, verbose_name='Processos relacionados')
    campus = models.ForeignKeyPlus(UnidadeOrganizacional, verbose_name='Campus', on_delete=models.CASCADE)
    tipo = models.PositiveIntegerField('Tipo', blank=False, choices=TipoCurso.get_choices())
    situacao = models.PositiveIntegerField(
        'Situação', null=False, blank=False, default=SituacaoCurso.NAO_INICIADO, choices=SituacaoCurso.get_choices()
    )

    data_cadastro = models.DateTimeFieldPlus('Data de Cadastro', null=True, blank=True, auto_now_add=True)
    data_inicio = models.DateTimeFieldPlus('Data de Início do Curso', null=True, blank=True)
    data_cadastrado_folha = models.DateTimeFieldPlus('Data de Finalização do Curso', null=True, blank=True)

    responsaveis = models.ManyToManyFieldPlus('rh.Servidor', blank=True, verbose_name='Responsáveis')

    participantes_detalhamento_atividade_ativado = models.BooleanField(
        'Ativar o detalhamento das atividades pelos participantes', default=True, editable=False
    )

    class Meta:
        verbose_name = 'Curso ou Concurso'
        verbose_name_plural = 'Cursos ou Concursos'
        unique_together = ('descricao', 'ano_pagamento')
        permissions = (
            ('pode_informar_cadastro_em_folha', 'Pode Informar Cadastro em Folha'),
            ('pode_gerenciar_participantes', 'Pode Gerenciar Participantes'),
            ('pode_ver_relatorio_pagamento_gecc', 'Pode Ver Relatório de Pagamento GECC'),
            ('pode_gerenciar_curso_concurso', 'Pode Gerenciar Curso/Concurso'),
            ('pode_mudar_situacao_curso_concurso', 'Pode Mudar a Situação do Curso/Concurso'),
        )

    def pode_ativar_desativar_detalhamento_atividade(self, user: User) -> bool:
        eh_rh_sistemico = user.has_group_cached('Coordenador de Gestão de Pessoas Sistêmico', ignore_groups_if_superuser=False)
        eh_curso_atende_criterio = self.situacao == SituacaoCurso.NAO_INICIADO or self.situacao == SituacaoCurso.INICIADO
        return eh_rh_sistemico and eh_curso_atende_criterio

    @atomic
    def ativar_desativar_detalhamento_atividade(self):
        self.participantes_detalhamento_atividade_ativado = not self.participantes_detalhamento_atividade_ativado
        self.save()
        participantes: QuerySet[Participante] = self.participantes
        for participante in participantes:
            participante.preparar_preenchimento_detalhamento_atividade()

    @property
    def participantes(self):
        return self.participante_set.all().order_by('servidor__pessoa_fisica__nome')

    ##################################################################
    # Verifica se o evento tem participante com pendência de pagamento
    ##################################################################
    def tem_participante_pendente(self):
        return self.participantes.filter(situacao=SituacaoParticipante.PENDENTE).exists()

    ############################################################
    # Lista participantes sem problema de pendência de pagamento
    ############################################################
    @property
    def participantes_sem_pendecia(self):
        return self.participantes.exclude(situacao=SituacaoParticipante.PENDENTE)

    ################################################
    # Lista participantes com pendência de pagamento
    ################################################
    @property
    def participantes_com_pendencia(self):
        return self.participantes.filter(situacao=SituacaoParticipante.PENDENTE)

    ####################################################################################################################
    # Lista os participantes de acordo com a situação do evento:
    # 1. se a situação do evento for "Cadastrado em Folha", mostra apenas os participantes sem pendência de pagamento
    # 2. se a situação do evento for diferente de "Cadastrado em Folha", mostra todos os participantes independente da situação
    ####################################################################################################################
    @property
    def get_participantes(self):
        retorno = self.participantes
        if self.situacao == SituacaoCurso.CADASTRADO_EM_FOLHA:
            retorno = self.participantes_sem_pendecia
        return retorno

    @property
    def tem_participante_sem_hora_trabalhada(self):
        return self.participantes.filter(situacao=SituacaoParticipante.LIBERADO, horas_trabalhada__isnull=True).exists()

    @property
    def tem_participante_aguardando_liberacao(self):
        return self.participantes.filter(situacao=SituacaoParticipante.AGUARDANDO_LIBERACAO).exists()

    def eh_responsavel(self, vinculo):
        if vinculo.eh_servidor:
            servidor = vinculo.relacionamento
            return self.responsaveis.filter(matricula=servidor.matricula).exists()
        return False

    def horas_previstas_total(self, situacoes=None):
        # participante.horas_prevista é um FloatField
        if situacoes is None:
            situacoes = [SituacaoParticipante.LIBERADO, SituacaoParticipante.AGUARDANDO_LIBERACAO]
        horas = self.participantes.filter(situacao__in=situacoes).aggregate(horas_total=Sum('horas_prevista'))
        return round(horas.get('horas_total') or 0.0, 2)

    def horas_trabalhadas_total(self, situacoes=None):
        # participante.horas_trabalhada é um FloatField
        if situacoes is None:
            situacoes = [SituacaoParticipante.LIBERADO, SituacaoParticipante.AGUARDANDO_LIBERACAO]
        horas = self.participantes.filter(situacao__in=situacoes).aggregate(horas_total=Sum('horas_trabalhada'))
        return round(horas.get('horas_total') or 0.0, 2)

    def valor_total(self, situacoes=None):
        # participante.atividade.valor_hora é um DecimalField
        if situacoes is None:
            situacoes = [SituacaoParticipante.LIBERADO, SituacaoParticipante.AGUARDANDO_LIBERACAO]
        valor_total = 0.0
        for participante in self.participantes.filter(horas_trabalhada__isnull=False, situacao__in=situacoes):
            valor_total += participante.horas_trabalhada * float(participante.atividade.valor_hora)
        return round(valor_total, 2)

    def tem_participante_problema_horas_insuficientes(self):
        for participante in self.participantes.all().exclude(situacao__in=[SituacaoParticipante.NAO_LIBERADO, SituacaoParticipante.LIBERADO]):
            if participante.problema_com_horas_insuficientes:
                return True
        return False

    def pode_excluir_curso(self):
        return self.horas_trabalhadas_total > 0

    def pode_iniciar_curso(self):
        return bool(
            not self.tem_participante_problema_horas_insuficientes()
            and self.situacao == SituacaoCurso.NAO_INICIADO
            and not self.tem_participante_aguardando_liberacao
            and not self.participantes.filter(situacao=SituacaoParticipante.NAO_LIBERADO).exists()
            and self.participantes.exists()
        )

    def pode_voltar_nao_iniciado(self):
        return bool(self.horas_trabalhadas_total <= 0 and self.situacao == SituacaoCurso.INICIADO)

    """
    Para finalizar um curso é preciso
    1 - A situação do curso está como INICIADO
    2 - Todos os participantes do curso estarem com suas horas trabalhadas cadastradas
    3 - Todos os participantes do curso estarem com o detalhamento das horas trabalhadas deferido
    """

    def pode_finalizar_curso(self, analisar_apenas_horas_trabalhadas=False) -> tuple[bool, str]:
        result, result_msg = True, ''

        # verificando a situação do curso
        if self.situacao is not SituacaoCurso.INICIADO:
            result, result_msg = False, 'Curso não iniciado.'

        # verificando horas trabalhadas e detalhamento das horas trabalhadas
        for p in self.participantes.all():
            if p.horas_trabalhada is None:
                result, result_msg = False, f'Faltando Horas Trabalhadas para {p.servidor}. '
                break

            if not analisar_apenas_horas_trabalhadas:
                if (
                    self.participantes_detalhamento_atividade_ativado
                    and p.horas_trabalhada > 0
                    and p.situacao_detalhamento != SituacaoDetalhamentoAtividadeParticipante.DEFERIDO
                ):
                    result, result_msg = False, f'Faltando Detalhamento das Horas Trabalhadas para {p.servidor}. '
                    break

        if not result:
            result_msg += 'É possível que outros participantes estejam na mesma situação. '

        return result, result_msg

    def pode_autorizar_pagamento(self):
        # verificando a situação do curso
        if self.situacao is not SituacaoCurso.FINALIZADO:
            return False
        # verificando horas trabalhadas
        return all(p.horas_trabalhada is not None for p in self.participantes.all())

    def pode_gerenciar_participante(self, usuario_logado):
        vinculo = usuario_logado.get_vinculo()
        return bool(
            self.situacao == SituacaoCurso.NAO_INICIADO
            and (usuario_logado.has_perm('cursos.pode_gerenciar_participantes') or usuario_logado.is_superuser or self.eh_responsavel(vinculo))
        )

    def pode_remover_participante(self):
        return self.situacao == SituacaoCurso.NAO_INICIADO

    def pode_visualizar_participantes(self, user):
        vinculo = user.get_vinculo()
        return (
            Participante.pode_visualizar_qualquer_participante(user)
            or user.has_perm('cursos.pode_gerenciar_participantes')
            or user.is_superuser
            or self.eh_responsavel(vinculo)
        )

    def pode_adicionar_horas_participante(self):
        return self.situacao == SituacaoCurso.INICIADO

    def pode_imprimir_listagem(self):
        return self.situacao in [SituacaoCurso.AGUARDANDO_CADASTRO_EM_FOLHA, SituacaoCurso.CADASTRADO_EM_FOLHA]

    def iniciar(self):
        if self.pode_iniciar_curso():
            self.situacao = SituacaoCurso.INICIADO
            self.data_inicio = datetime.now()
            self.save()
        else:
            raise ValidationError('Não foi possível iniciar o curso.')

    @atomic
    def finalizar(self):
        """este método na verdade seta a situação do curso para aguardando cadastro em folha"""
        pode_finalizar_curso, msg = self.pode_finalizar_curso()

        if pode_finalizar_curso:
            self.situacao = SituacaoCurso.AGUARDANDO_CADASTRO_EM_FOLHA
            self.save()
        else:
            raise ValidationError(f'Este curso não pode ser finalizado: {msg}')

    @staticmethod
    def get_cronograma_folha_valido():
        CronogramaFolha = apps.get_model('rh', 'CronogramaFolha')
        cronograma = CronogramaFolha.get_cronograma_hoje()
        return cronograma

    def informar_cadastro_em_folha_participantes(self, participantes_ids, cronograma):
        self.participantes.filter(id__in=participantes_ids).update(mes_pagamento=cronograma.mes, situacao=SituacaoParticipante.PENDENTE)

    @atomic
    def informar_execucao_pagamento_participantes(self, user_informante, participantes_ids, cronograma):
        data_registro = date(date.today().year, cronograma.mes, 1)

        self.participantes.filter(id__in=participantes_ids).update(
            mes_pagamento=cronograma.mes, situacao=SituacaoParticipante.LIBERADO, data_registro_pagamento=data_registro
        )

        if self.participantes_detalhamento_atividade_ativado:
            self.gerar_compensacao_especifica_participantes(user_informante, participantes_ids)

    @atomic
    def informar_cadastro_folha(self, request):
        cronograma = Curso.get_cronograma_folha_valido()

        if cronograma:
            participantes_ids = request.POST.getlist('add_participante')
            self.informar_cadastro_em_folha_participantes(participantes_ids, cronograma)
            self.situacao = SituacaoCurso.CADASTRADO_EM_FOLHA
            self.data_cadastrado_folha = datetime.now()
            self.save()
        else:
            raise ValidationError('Não existe cadastrado um cronograma para fechamento de folha que seja válido para os cálculos de pagamento.')

    def __str__(self):
        return self.descricao

    def get_absolute_url(self):
        return f'/cursos/curso/{self.id:d}/'

    get_absolute_url.short_description = 'Descrição'

    def save(self):
        if self.pk and self.situacao == SituacaoCurso.INICIADO and self.tem_participante_problema_horas_insuficientes():
            raise ValidationError('O curso não pode ser iniciado pois existe participantes com problemas de carga horária.')
        super().save()

    def get_situacao_html(self):
        tipo = 'alert'
        if self.situacao == SituacaoCurso.NAO_INICIADO:
            tipo = 'error'
        if self.situacao == SituacaoCurso.CADASTRADO_EM_FOLHA:
            tipo = 'success'
        return mark_safe(f'<span class="status status-{tipo}">{self.get_situacao_display()}</span>')

    def pode_informar_execucao_pagamento(self, user) -> bool:
        eh_rh_sistemico = user.has_group_cached('Coordenador de Gestão de Pessoas Sistêmico', ignore_groups_if_superuser=False)
        eh_rh_campus = user.has_group_cached('Coordenador de Gestão de Pessoas', ignore_groups_if_superuser=False)
        return eh_rh_sistemico or eh_rh_campus

    @property
    def estah_a_iniciar(self) -> bool:
        return self.situacao == SituacaoCurso.NAO_INICIADO

    @property
    def estah_concluido(self) -> bool:
        return self.situacao in SituacaoCurso.curso_concluido()

    @property
    def estah_em_andamento(self) -> bool:
        return self.situacao in SituacaoCurso.curso_em_andamento()

    @staticmethod
    def servidor_participante_tem_pendencias(servidor: Servidor) -> bool:
        return Curso.objects.filter(
            participante__servidor=servidor,
            participante__curso__situacao__in=SituacaoCurso.curso_em_andamento(),
            participante__situacao__in=SituacaoParticipante.participante_em_atividade(),
            participantes_detalhamento_atividade_ativado=True,
            participante__situacao_detalhamento__in=SituacaoDetalhamentoAtividadeParticipante.detalhamento_pendente(),
        ).exists()

    def gerar_compensacao_especifica_participantes(self, user_responsavel, participantes_ids):
        """
        Após um responsável informar a execução do pagamento em folha das
        GECCs, o sistema irá gerar, para cada participante informado, uma opção de
        compensação de CH específica.

        Esse processamento é "silencioso" nesse ponto. No caso de erros nesta etapa, haverá
        informações na página do participante sobre os eventuais problemas referentes à geração da
        compensação específica.
        """
        servidor_rh = user_responsavel.get_relacionamento()
        if isinstance(servidor_rh, Servidor):
            for _ in self.participantes.filter(id__in=participantes_ids):
                participante: Participante = _
                if participante.situacao == SituacaoParticipante.LIBERADO:
                    try:
                        participante.gerar_compensacao_especifica(servidor_responsavel=servidor_rh)
                    except Exception:
                        pass  # o RH não precisa saber sobre erros nessa etapa !!!!


class ParticipantesPendentesPagamentoManager(models.Manager):
    #
    # manager que retorna apenas os participantes pendentes de pagamento
    def get_queryset(self):
        qs = super().get_queryset().filter(situacao=SituacaoParticipante.PENDENTE)
        return qs


class Participante(models.ModelPlus):
    SEARCH_FIELDS = ['servidor__pessoa_fisica__nome', 'servidor__matricula']
    VALOR_PADRAO_HORAS_TRABALHADAS = 120

    curso = models.ForeignKeyPlus(Curso, null=False, blank=False, verbose_name='Curso ou Concurso', on_delete=models.CASCADE)
    servidor = models.ForeignKeyPlus('rh.Servidor', null=False, blank=False, verbose_name='Servidor', on_delete=models.CASCADE)
    mes_pagamento = models.PositiveIntegerField('Mês de Pagamento', null=True, blank=True)
    data_registro_pagamento = models.DateFieldPlus('Data de Registro de Pagamento', null=True, blank=True)
    atividade = models.ForeignKeyPlus(Atividade, null=False, blank=False, verbose_name='Atividade', on_delete=models.CASCADE)
    atividade_mes = models.PositiveIntegerField('Mês Previsto para a Atividade', null=True, blank=True)
    horas_prevista = models.FloatField('Horas Previstas de Trabalho', null=False, blank=False)
    horas_trabalhada = models.FloatField('Horas Trabalhadas', null=True, blank=True)
    responsavel_liberacao = models.ForeignKeyPlus(
        'rh.Servidor',
        null=True,
        blank=True,
        verbose_name='Responsável pela Liberação',
        on_delete=models.CASCADE,
        related_name='responsavel_liberacao_set',
    )
    data_liberacao = models.DateTimeFieldPlus('Data da Liberação', null=True, blank=True)
    situacao = models.PositiveIntegerField(
        'Situação', null=False, blank=False, default=SituacaoParticipante.AGUARDANDO_LIBERACAO, choices=SituacaoParticipante.get_choices()
    )
    motivo_nao_liberacao = models.CharFieldPlus('Motivo do Indeferimento', max_length=500, null=True, blank=True)
    data_cadastro = models.DateTimeFieldPlus('Data de Cadastro', null=False, blank=False, auto_now_add=True)
    ano_desconto_carga_horaria = models.PositiveIntegerFieldPlus('Ano de Desconto da Carga Horária', null=True, blank=True)

    # detalhamento das atividades executadas
    horas_trabalhadas_fora_ch = models.FloatField('Horas Trabalhadas fora da CH', blank=True, default=0.0)
    horas_trabalhadas_dentro_ch = models.FloatField('Horas Trabalhadas dentro da CH', blank=True, default=0.0)
    data_inicio_atividade = models.DateFieldPlus('Data Início da Atividade', null=True, blank=True)
    data_fim_atividade = models.DateFieldPlus('Data Fim da Atividade', null=True, blank=True)
    descricao_atividade = models.TextField('Descrição da Atividade', null=True, blank=True)
    situacao_detalhamento = models.PositiveIntegerField(
        'Situação Detalhamento',
        default=SituacaoDetalhamentoAtividadeParticipante.INDEFINIDO,
        choices=SituacaoDetalhamentoAtividadeParticipante.get_choices(),
    )
    motivo_nao_deferimento_detalhamento = models.CharFieldPlus('Motivo do Indeferimento do Detalhamento', max_length=500, null=True, blank=True)
    responsavel_compensacao_especifica = models.ForeignKeyPlus(
        'rh.Servidor',
        null=True,
        blank=True,
        verbose_name='Responsável pela Geração do Débito Externo e da Compensação Específica',
        on_delete=models.CASCADE,
        related_name='responsavel_compensacao_especifica_set',
    )
    documento_eletronico = models.ForeignKeyPlus(
        'documento_eletronico.DocumentoTexto', verbose_name='Documento Eletrônico', editable=False, null=True, blank=True, on_delete=models.SET_NULL
    )

    objects = models.Manager()
    pendentes = ParticipantesPendentesPagamentoManager()

    class Meta:
        verbose_name = 'Participante'
        verbose_name_plural = 'Participantes'
        permissions = (('pode_ver_seu_relatorio', 'Pode Ver o Próprio Relatório'),)

    @property
    def debito_externo(self) -> DebitoExternoCadastro:
        return DebitoExternoCadastro.get_debitos_externos_cadastros_from_origem(self).filter(servidor=self.servidor).first()

    @property
    def compensacao_especifica(self) -> RecessoOpcaoEscolhida:
        return RecessoOpcaoEscolhida.get_compensacoes_especificas_from_origem(self).filter(funcionario=self.servidor).first()

    @property
    def estah_ativado_detalhamento_atividade(self):
        return self.curso.participantes_detalhamento_atividade_ativado is True

    def preparar_preenchimento_detalhamento_atividade(self, save=True):
        if self.estah_ativado_detalhamento_atividade and self.horas_trabalhada and self.horas_trabalhada > 0:
            ativar_ciclo_preenchimento: bool = not self.existe_detalhamento_atividade or (
                self.existe_detalhamento_atividade and self.horas_trabalhadas_fora_ch + self.horas_trabalhadas_dentro_ch != self.horas_trabalhada
            )
            if ativar_ciclo_preenchimento:
                # mantém o valor anterior já que a função de adicionar horas
                # pode ser repetida por N vezes, exigindo N detalhamentos das horas
                # ou apenas uma edição do que já se havia detalhado
                self.horas_trabalhadas_fora_ch = self.horas_trabalhadas_fora_ch or 0.0
                self.horas_trabalhadas_dentro_ch = self.horas_trabalhadas_dentro_ch or 0.0
                self.data_inicio_atividade = self.data_inicio_atividade or None
                self.data_fim_atividade = self.data_fim_atividade or None
                self.descricao_atividade = self.descricao_atividade or None
                self.situacao_detalhamento = SituacaoDetalhamentoAtividadeParticipante.AGUARDANDO_PREENCHIMENTO
                if save:
                    self.save()
                    self.notificar_preenchimento_detalhamento_atividade()
        else:
            self.horas_trabalhadas_fora_ch = 0.0
            self.horas_trabalhadas_dentro_ch = 0.0
            self.data_inicio_atividade = None
            self.data_fim_atividade = None
            self.descricao_atividade = None
            self.motivo_nao_deferimento_detalhamento = None
            self.situacao_detalhamento = SituacaoDetalhamentoAtividadeParticipante.INDEFINIDO
            if save:
                self.save()

    def pode_preencher_detalhamento_atividade(self, user) -> bool:
        user_servidor = user.get_relacionamento()
        eh_o_participante = self.servidor == user_servidor
        return eh_o_participante and self.situacao_detalhamento == SituacaoDetalhamentoAtividadeParticipante.AGUARDANDO_PREENCHIMENTO

    @property
    def existe_detalhamento_atividade(self) -> bool:
        return (
            self.horas_trabalhadas_fora_ch >= 0.0
            and self.horas_trabalhadas_dentro_ch >= 0.0
            and self.data_inicio_atividade
            and self.data_fim_atividade
            and self.descricao_atividade
        )

    def get_absolute_url(self):
        return f'/cursos/participante/{self.id}'

    def preparar_avaliacao_detalhamento_atividade(self, save=True):
        if self.estah_ativado_detalhamento_atividade:
            self.situacao_detalhamento = SituacaoDetalhamentoAtividadeParticipante.AGUARDANDO_AVALIACAO
            if save:
                self.save()
                self.notificar_avaliacao_detalhamento_atividade()
        else:
            self.situacao_detalhamento = SituacaoDetalhamentoAtividadeParticipante.INDEFINIDO
            if save:
                self.save()

    def notificar_preenchimento_detalhamento_atividade(self):
        # notifica participante

        servidor = f'{self.servidor.pessoa_fisica.nome}'
        curso = f'{self.curso}'
        curso_link = f'{settings.SITE_URL}{self.curso.get_absolute_url()}'
        atividade = f'{self.atividade.descricao}'
        detalhamento_link = f'{settings.SITE_URL}/cursos/preencher_detalhamento_atividade/{self.id}'

        destinatarios = [servidor.get_vinculo() for servidor in [self.servidor]]

        assunto = '[SUAP] GECC: Detalhamento de Horas Trabalhadas'

        mensagem = f"""
            <h1>GECC: Participação em Curso/Concurso</h1>
            <h2>Detalhamento de Horas Trabalhadas</h2>
            <p>O servidor <strong>{servidor}</strong>, participante do curso <a href="{curso_link}">{curso}</a>,
            deverá realizar o detalhamento das horas trabalhadas, referente à atividade <strong>{atividade}</strong>.</p>
            <p class="more-info">Para mais informações, acesse: <a href="{detalhamento_link}">{detalhamento_link}</a></p>
        """

        send_notification(assunto, mensagem, settings.DEFAULT_FROM_EMAIL, destinatarios)

    def notificar_avaliacao_detalhamento_atividade(self):
        # notifica chefia

        servidor = f'{self.servidor.pessoa_fisica.nome}'
        curso = f'{self.curso}'
        curso_link = f'{settings.SITE_URL}{self.curso.get_absolute_url()}'
        atividade = f'{self.atividade.descricao}'
        atividade_link = f'{settings.SITE_URL}{self.get_absolute_url()}'

        chefes = self.get_chefes()

        if len(chefes) > 1:
            chefe_imediato = ', '.join([f'{servidor.pessoa_fisica.nome}' for servidor in chefes[:-1]])
            chefe_imediato = f'{chefe_imediato} e {chefes[-1].nome}'
        else:
            chefe_imediato = ', '.join([f'{servidor.pessoa_fisica.nome}' for servidor in chefes])

        destinatarios = [servidor.get_vinculo() for servidor in chefes]

        assunto = '[SUAP] GECC: Detalhamento de Horas Trabalhadas'

        mensagem = f"""
            <h1>GECC: Participação em Curso/Concurso</h1>
            <h2>Detalhamento de Horas Trabalhadas</h2>
            <p>O servidor <strong>{servidor}</strong>, participante do curso <a href="{curso_link}">{curso}</a>,
            realizou o detalhamento das horas trabalhadas, referente à atividade <strong>{atividade}</strong>, e
            aguarda a avaliação por parte da chefia imediata, servidor{'es' if len(chefes) > 1 else ''} <strong>{chefe_imediato}</strong>.</p>
            <p class="more-info">Para realizar a avaliação, deve{'m' if len(chefes) > 1 else ''} acessar: <a href="{atividade_link}">{atividade_link}</a></p>
        """

        send_notification(assunto, mensagem, settings.DEFAULT_FROM_EMAIL, destinatarios)

    def notificar_liberacao_participante(self):
        # notifica participante e responsáveis pelo curso

        servidor = f'{self.servidor.pessoa_fisica.nome}'
        curso = f'{self.curso}'
        responsaveis = self.curso.responsaveis.all()

        assunto = '[SUAP] GECC: Participação em Curso/Concurso'

        mensagem = f"""
            <h1>GECC: Participação em Curso/Concurso</h1>
            <h2>Participação deferida pela chefia imediata</h2>
            <p>{servidor}</p>
            <p>Sua participação em <strong>{curso}</strong> foi deferida pela chefia imediata.</p>
        """

        destinatarios = [servidor.get_vinculo() for servidor in [self.servidor]]

        send_notification(assunto, mensagem, settings.DEFAULT_FROM_EMAIL, destinatarios)

        if responsaveis.exists():
            mensagem = f"""
                <h1>GECC: Participação em Curso/Concurso</h1>
                <h2>Participação em <strong>{curso}</strong> deferida pela chefia imediata</h2>
                <p>{servidor}</p>
            """

            destinatarios = [servidor.get_vinculo() for servidor in responsaveis]

            send_notification(assunto, mensagem, settings.DEFAULT_FROM_EMAIL, destinatarios)

    def get_chefes(self) -> list[Servidor]:
        servidor: Servidor = self.servidor
        hoje = date.today()
        chefes = servidor.get_chefes_no_periodo(hoje, hoje).get(hoje)
        return chefes

    @staticmethod
    def pode_visualizar_qualquer_participante(user) -> bool:
        return user.has_group_cached(
            [
                'Coordenador de Gestão de Pessoas Sistêmico',
                'Coordenador de Gestão de Pessoas, Operador de Gestão de Pessoas',
                'Operador de Cursos e Concursos',
            ]
        )

    def pode_visualizar(self, user) -> bool:
        user_servidor = user.get_relacionamento()
        eh_o_participante = self.servidor == user_servidor
        if eh_o_participante or self.curso.pode_visualizar_participantes(user):
            return True
        eh_o_chefe = user_servidor in self.get_chefes()
        return eh_o_chefe

    def pode_deferir_indeferir_detalhamento_atividade(self, user) -> bool:
        user_servidor = user.get_relacionamento()
        eh_o_chefe = user_servidor in self.get_chefes()
        return eh_o_chefe and self.is_aguardando_avaliacao_detalhamento_horas

    def deferir_detalhamento_atividade(self, save=True):
        self.situacao_detalhamento = SituacaoDetalhamentoAtividadeParticipante.DEFERIDO
        self.motivo_nao_deferimento_detalhamento = ''
        if save:
            self.save()

    def pode_gerar_documento_eletronico_detalhamento_atividade(self, user) -> bool:
        user_servidor = user.get_relacionamento()
        eh_o_participante = self.servidor == user_servidor
        participante_liberado = self.situacao == SituacaoParticipante.LIBERADO
        detalhamento_deferido = self.situacao_detalhamento == SituacaoDetalhamentoAtividadeParticipante.DEFERIDO
        return eh_o_participante and participante_liberado and detalhamento_deferido

    @atomic
    def gerar_documento_eletronico_detalhamento_atividade(self, usuario_criacao: User) -> tuple[DocumentoTexto, str]:
        """
        Deverá ser criado um modelo de documento para prestação de contas das atividades do
        GECC no módulo de documentos eletrônicos, que será automaticamente preenchido pelos dados
        contidos dentro do próprio curso ou concurso para cada um dos participantes.
        """
        if self.documento_eletronico:
            self.documento_eletronico.delete()
            self.documento_eletronico = None
            self.save()

        erros = []

        setor_dono = None  # TODO
        assunto = '?'  # TODO

        modelo_nome = 'Modelo Indefinido'  # TODO
        try:
            modelo = ModeloDocumento.objects.get(nome=modelo_nome)
        except Exception:
            modelo = None
            erros.append(f'O modelo "{modelo_nome}" não foi encontrado. ')

        try:
            template = get_template('?/?/?.html')  # TODO
            html = template.render({'?': '?'})  # TODO
        except Exception:
            html = '?'
            erros.append(f'Erro durante o processamento do modelo "{modelo_nome}". ')

        if not erros:
            try:
                documento_eletronico = DocumentoTexto.adicionar_documento_texto(
                    usuario=usuario_criacao,
                    setor_dono=setor_dono,
                    assunto=assunto,
                    modelo=modelo,
                    nivel_acesso=Documento.NIVEL_ACESSO_PUBLICO,
                    corpo=html,
                )
            except Exception:
                documento_eletronico = None
                erros.append('Erro durante a geração do documento eletrônico. ')
        else:
            documento_eletronico = None

        self.documento_eletronico = documento_eletronico
        self.save()

        return documento_eletronico, ''.join(erros)

    def indeferir_detalhamento_atividade(self, motivo: str, save=True):
        self.situacao_detalhamento = SituacaoDetalhamentoAtividadeParticipante.AGUARDANDO_PREENCHIMENTO
        self.motivo_nao_deferimento_detalhamento = motivo
        if save:
            self.save()
            self.notificar_preenchimento_detalhamento_atividade()

    def pode_notificar_detalhamento_atividade(self, user) -> bool:
        detalhamento_pendente = self.situacao_detalhamento in [
            SituacaoDetalhamentoAtividadeParticipante.AGUARDANDO_PREENCHIMENTO,
            SituacaoDetalhamentoAtividadeParticipante.AGUARDANDO_AVALIACAO,
        ]
        return self.pode_visualizar(user) and detalhamento_pendente

    def pode_gerar_compensacao_especifica(self, user) -> bool:
        user_servidor = user.get_relacionamento()
        eh_o_participante = self.servidor == user_servidor
        eh_responsavel_compensacao_especifica = self.responsavel_compensacao_especifica == user_servidor
        participante_liberado = self.situacao == SituacaoParticipante.LIBERADO
        detalhamento_deferido = self.situacao_detalhamento == SituacaoDetalhamentoAtividadeParticipante.DEFERIDO
        curso_concluido = self.curso.estah_concluido
        return (eh_o_participante or eh_responsavel_compensacao_especifica) and detalhamento_deferido and curso_concluido and participante_liberado

    @atomic
    def gerar_compensacao_especifica(self, servidor_responsavel: Servidor) -> bool:
        """
        Etapa de geração/cadastro de uma compensação específica para GECC com prazo de compensação a
        contar da data de início de execução da atividade até 1 ano após a data de conclusão desta.

        Curso
            -> Participante [CH a repor, Período]
                    -> [Débito Externo -> Dias do Período] ---------------------->  Débitos do Ponto
                                                                                           |
                    -> [Compensação Específica -> Período -> Dias do Período] <---  Débitos do Ponto
        """

        # valor do débito e prazo de compensação

        ch_a_repor_em_horas: float = self.horas_trabalhadas_dentro_ch

        if not ch_a_repor_em_horas > 0:
            return False  # não há o que compensar

        data_inicio_atividade: date = self.data_inicio_atividade
        data_fim_atividade: date = self.data_fim_atividade
        prazo_de_compensacao: list[date] = [data_inicio_atividade, data_fim_atividade + relativedelta(years=1)]

        chefe = self.get_chefes() or [None]

        # exclui as informações atuais (os objetos externos)

        # remove o débito externo
        if self.debito_externo:
            try:
                # tenta remover
                self.debito_externo.delete()
            except Exception:
                pass

        # remove a compensação específica
        # inclui a escolha/atribuição e o cadastro da opção
        # opção (RecessoOpcao) -> escolha (RecessoOpcaoEscolhida)
        if self.compensacao_especifica:
            try:
                # tenta remover
                opcao_compensacao_especifica: RecessoOpcao = self.compensacao_especifica.recesso_opcao
                escolha_compensacao_especifica: RecessoOpcaoEscolhida = self.compensacao_especifica
                escolha_compensacao_especifica.delete()
                opcao_compensacao_especifica.delete()
            except Exception:
                pass

        # reseta as informações atuais (no objeto local)
        self.responsavel_compensacao_especifica = servidor_responsavel
        self.save()

        ###
        # cria um novo débito externo

        debito_externo: DebitoExternoCadastro = DebitoExternoCadastro.cadastrar_debito_externo(
            data_cadastro=datetime.now(),
            servidor_destinatario=self.servidor,
            total_debito_em_segundos=ch_a_repor_em_horas * 3600,
            # foi o chefe imediato quem deferiu o detalhamento das atividades
            # e teve conhecimento da carga horária devida pelo participante
            servidor_cadastrador=chefe[0],
            servidor_validador=chefe[0],
            situacao=DebitoExternoCadastro.SITUACAO_VALIDADO,
            # os dias dos débitos e valores de cada um serão definidos
            # automaticamente (se possível)
            dias_debitos_auto=datas_entre(data_inicio_atividade, data_fim_atividade),
            detalhamento=f"""
                Participação em Cursos/Concursos: {self.curso} - {self.atividade.descricao}.
                Período da Atividade: {data_inicio_atividade.strftime('%d/%m/%Y')} a {data_fim_atividade.strftime('%d/%m/%Y')}""".strip(),
            model_instance_origem=self,
        )

        if debito_externo:
            ###
            # cria uma nova compensação específica

            descricao = f'{self.servidor} - Participação em Cursos/Concursos: {self.curso} - {self.atividade.descricao}'

            compensacao: list[RecessoOpcaoEscolhida] = RecessoOpcao.cadastrar_compensacao_especifica(
                descricao_compensacao=descricao,
                data_cadastro=datetime.now(),
                servidor_responsavel=servidor_responsavel,
                servidores_alvo=[self.servidor],
                dias_a_compensar=[],
                periodos_a_compensar=[Periodo(data_hora_inicio=data_inicio_atividade, data_hora_fim=data_fim_atividade)],
                periodos_compensacao=[Periodo(data_hora_inicio=prazo_de_compensacao[0], data_hora_fim=prazo_de_compensacao[1])],
                servidor_validador=chefe[0],
                situacao_validacao=RecessoOpcaoEscolhida.VALIDACAO_AUTORIZADO,
                tipo_compensacao=RecessoOpcao.TIPO_CADASTRO_EXTERNO,
                situacao_compensacao=RecessoOpcao.SITUACAO_FECHADO,
                model_instance_origem=self,
            )

            if compensacao:
                return True  # nesse ponto, débito externo e compensação específica foram gerados

        return False  # compensação específica ou débito externo não foram gerados

    def atividade_mes_display(self):
        return Meses.get_mes(self.atividade_mes)

    def mes_pagamento_display(self):
        if self.mes_pagamento:
            return Meses.get_mes(self.mes_pagamento)
        return None

    def get_ext_combo_template(self):
        return self.servidor.get_ext_combo_template()

    def __str__(self):
        return f'{self.servidor.pessoa_fisica.nome} ({self.servidor.matricula})'

    # quantidade de horas trabalhadas vezes o valor da hora da atividade

    @property
    def valor_total(self):
        # participante.atividade.valor_hora é um DecimalField
        total = 0.0
        if self.horas_trabalhada:
            total = self.horas_trabalhada * float(self.atividade.valor_hora)
        return round(total, 2)

    # horas disponíveis no ano corrente

    @property
    def horas_disponiveis_ano(self):
        ano = self.curso.ano_pagamento

        horas_total = 0

        # horas trabalhadas pelo servidor
        horas_total += self.servidor.qtd_horas_trabalhadas_gecc(ano)

        # horas previstas de trabalho em cursos/concursos que o servidor está inscrito
        qtd_horas_previstas = self.servidor.participante_set.filter(
            curso__ano_pagamento=ano,
            horas_trabalhada__isnull=True,
            curso__situacao__in=[SituacaoCurso.NAO_INICIADO, SituacaoCurso.INICIADO],
            situacao=SituacaoParticipante.LIBERADO,
        ).aggregate(horas=Sum('horas_prevista'))

        horas_total += qtd_horas_previstas.get('horas') or 0

        # hora extra cadastrada para o ano corrente
        horas_extra = CotaExtra.cota_extra_servidor_no_ano(self.servidor, ano)

        return (self.VALOR_PADRAO_HORAS_TRABALHADAS + horas_extra) - horas_total

    @property
    def horas_trabalhadas_no_ano(self):
        return self.servidor.qtd_horas_trabalhadas_gecc(ano=self.curso.ano_pagamento)

    @property
    def horas_permitidas_no_ano(self):
        ano = self.curso.ano_pagamento
        servidor = self.servidor

        cota_extra = 0
        for cota in CotaExtra.objects.filter(ano=ano, servidor=servidor):
            cota_extra += cota.horas_permitida

        return self.VALOR_PADRAO_HORAS_TRABALHADAS + cota_extra

    @property
    def problema_com_horas_insuficientes(self):
        horas_disponiveis_ano = self.horas_disponiveis_ano
        horas_prevista = self.horas_prevista or 0

        if (
            self.curso.situacao
            in [SituacaoCurso.FINALIZADO, SituacaoCurso.INICIADO, SituacaoCurso.AGUARDANDO_CADASTRO_EM_FOLHA, SituacaoCurso.CADASTRADO_EM_FOLHA]
            and self.situacao != SituacaoParticipante.NAO_LIBERADO
        ):
            # nesse caso, "horas_disponiveis_ano" já reflete o valor de "horas_trabalhada" da participação atual
            # para efeitos desse método, "devolve" para "horas_disponiveis_ano" as "horas_trabalhada" da participação atual
            horas_disponiveis_ano += self.horas_trabalhada or 0

        return horas_prevista > horas_disponiveis_ano

    def detalhamento_horas_clean_valor_inicial_situacao(self):
        # corrige uma inconsistência no valor inicial da situação do detalhamento de horas
        if self.curso.situacao == SituacaoCurso.INICIADO and self.horas_trabalhada:
            if self.situacao_detalhamento == SituacaoDetalhamentoAtividadeParticipante.INDEFINIDO:
                self.preparar_preenchimento_detalhamento_atividade()

    @property
    def problema_com_detalhamento_horas(self):
        self.detalhamento_horas_clean_valor_inicial_situacao()

        detalhamento_ok = (
            (self.curso.situacao != SituacaoCurso.INICIADO)
            or (
                self.curso.situacao == SituacaoCurso.INICIADO
                and self.horas_trabalhada
                and self.existe_detalhamento_atividade
                and self.situacao_detalhamento == SituacaoDetalhamentoAtividadeParticipante.DEFERIDO
            )
            or (not self.estah_ativado_detalhamento_atividade)
            or (
                self.horas_trabalhada is None  # não há o que se cobrar de detalhamento das horas
            )
        )

        return not detalhamento_ok

    @staticmethod
    def get_participantes_detalhamento_horas_preenchimento_pendente(user_participante) -> QuerySet[Participante]:
        participante = user_participante.get_relacionamento()

        participantes: QuerySet[Participante] = Participante.objects.filter(
            servidor=participante,
            curso__situacao=SituacaoCurso.INICIADO,
            horas_trabalhada__isnull=False,
            situacao_detalhamento__in=[
                SituacaoDetalhamentoAtividadeParticipante.INDEFINIDO,
                SituacaoDetalhamentoAtividadeParticipante.AGUARDANDO_PREENCHIMENTO,
            ],
        )

        # verifica a possível inconsistência inicial com a situação de detalhamento INDEFINIDO
        participantes_exclude_ids = []
        for participante in participantes:
            participante.detalhamento_horas_clean_valor_inicial_situacao()
            if participante.situacao_detalhamento != SituacaoDetalhamentoAtividadeParticipante.AGUARDANDO_PREENCHIMENTO:
                participantes_exclude_ids.append(participante.id)

        return participantes.exclude(id__in=participantes_exclude_ids)

    @staticmethod
    def get_participantes_detalhamento_horas_avaliacao_pendente(user_chefe) -> QuerySet[Participante]:
        chefe: Servidor = user_chefe.get_relacionamento()

        hoje = date.today()
        chefe_setores_hoje_ids = [funcao.setor_suap.id for funcao in chefe.get_funcoes_no_periodo(hoje, hoje).values() if funcao.setor_suap]

        # participantes no mesmo setor do chefe informado
        participantes_setor = Participante.objects.filter(
            servidor__setor__id__in=chefe_setores_hoje_ids,
            curso__situacao=SituacaoCurso.INICIADO,
            horas_trabalhada__isnull=False,
            situacao_detalhamento__in=[
                SituacaoDetalhamentoAtividadeParticipante.AGUARDANDO_AVALIACAO,
            ],
        )

        # participantes no setor imediatamente inferior
        participantes_setor_inferior = Participante.objects.filter(
            servidor__setor__superior__id__in=chefe_setores_hoje_ids,
            curso__situacao=SituacaoCurso.INICIADO,
            horas_trabalhada__isnull=False,
            situacao_detalhamento__in=[
                SituacaoDetalhamentoAtividadeParticipante.AGUARDANDO_AVALIACAO,
            ],
        )

        if participantes_setor_inferior.exists():
            # aqui há uma queda no desempenho

            setor_inferior = participantes_setor_inferior.first().servidor.setor
            setor_inferior_tem_chefe = setor_inferior.historico_funcao(hoje, hoje).exists()

            if setor_inferior_tem_chefe:
                # considera apenas os participantes do setor inferior com função hoje
                participantes_exclude_ids = []
                for participante in participantes_setor_inferior:
                    if not participante.servidor.get_funcoes_no_periodo(hoje, hoje):
                        participantes_exclude_ids.append(participante.id)

                participantes = (participantes_setor | participantes_setor_inferior.exclude(id__in=participantes_exclude_ids)).distinct()
            else:
                # considera todos os participantes encontrados no setor inferior
                # isso pode ser indesejável, mas temos aí um setor sem chefe, e isso é um
                # problema fora deste escopo
                participantes = (participantes_setor | participantes_setor_inferior).distinct()
        else:
            participantes = participantes_setor

        if not chefe.eh_reitor():
            participantes = participantes.exclude(
                servidor=chefe  # não é permitida a auto-avaliação
            )

        return participantes

    @staticmethod
    def get_participantes_liberacao_pendente(user_chefe) -> QuerySet[Participante]:
        chefe: Servidor = user_chefe.get_relacionamento()

        hoje = date.today()
        chefe_setores_hoje_ids = [funcao.setor_suap.id for funcao in chefe.get_funcoes_no_periodo(hoje, hoje).values() if funcao.setor_suap]

        # participantes no mesmo setor do chefe informado
        participantes_setor = Participante.objects.filter(
            servidor__setor__id__in=chefe_setores_hoje_ids, situacao=SituacaoParticipante.AGUARDANDO_LIBERACAO
        )

        # participantes no setor imediatamente inferior
        participantes_setor_inferior = Participante.objects.filter(
            servidor__setor__superior__id__in=chefe_setores_hoje_ids, situacao=SituacaoParticipante.AGUARDANDO_LIBERACAO
        )

        if participantes_setor_inferior.exists():
            # aqui há uma queda no desempenho

            setor_inferior = participantes_setor_inferior.first().servidor.setor
            setor_inferior_tem_chefe = setor_inferior.historico_funcao(hoje, hoje).exists()

            if setor_inferior_tem_chefe:
                # considera apenas os participantes do setor inferior com função hoje
                participantes_exclude_ids = []
                for participante in participantes_setor_inferior:
                    if not participante.servidor.get_funcoes_no_periodo(hoje, hoje):
                        participantes_exclude_ids.append(participante.id)

                participantes = (participantes_setor | participantes_setor_inferior.exclude(id__in=participantes_exclude_ids)).distinct()
            else:
                # considera todos os participantes encontrados no setor inferior
                # isso pode ser indesejável, mas temos aí um setor sem chefe, e isso é um
                # problema fora deste escopo
                participantes = (participantes_setor | participantes_setor_inferior).distinct()
        else:
            participantes = participantes_setor

        if not chefe.eh_reitor():
            participantes = participantes.exclude(
                servidor=chefe  # não é permitida a auto-avaliação
            )

        return participantes

    @property
    def mes_ano_pagamento(self):
        if self.data_registro_pagamento:
            return f'{self.data_registro_pagamento.month}/{self.data_registro_pagamento.year}'
        return None

    def get_situacao_html(self):
        status = ''
        status_extras: list[list[str]] = []

        if self.situacao == SituacaoParticipante.AGUARDANDO_LIBERACAO:
            status = 'pendente'

        elif self.situacao == SituacaoParticipante.LIBERADO:
            status = 'aceito'

        elif self.situacao == SituacaoParticipante.NAO_LIBERADO:
            status = 'impedido'
            status_extras.append(['impedido', self.motivo_nao_liberacao or 'Sem motivação informada'])

        elif self.situacao == SituacaoParticipante.PENDENTE:
            status = 'pendente'

        if self.problema_com_horas_insuficientes:
            status_extras.append(['impedido', 'Horas Disponíveis Insuficientes'])

        # if self.problema_com_detalhamento_horas:
        #     status_extras.append(['impedido', f'Detalhamento das Horas: {self.get_situacao_detalhamento_display()}'])

        out = [f'<span class="status status-{status}">{self.get_situacao_display()}</span>']
        out += [f'<span class="status status-{status_extra[0]}">{status_extra[1]}</span>' for status_extra in status_extras]

        return mark_safe(''.join(out))

    @property
    def is_aguardando_liberar_participacao(self):
        return self.situacao == SituacaoParticipante.AGUARDANDO_LIBERACAO

    @property
    def is_aguardando_avaliacao_detalhamento_horas(self):
        return self.situacao_detalhamento == SituacaoDetalhamentoAtividadeParticipante.AGUARDANDO_AVALIACAO

    def get_situacao_detalhamento_display_html(self):
        status = ''
        if self.situacao_detalhamento == SituacaoDetalhamentoAtividadeParticipante.INDEFINIDO:
            status = 'info'
        if self.situacao_detalhamento == SituacaoDetalhamentoAtividadeParticipante.AGUARDANDO_PREENCHIMENTO:
            status = 'alert'
        if self.situacao_detalhamento == self.is_aguardando_avaliacao_detalhamento_horas:
            status = 'alert'
        if self.situacao_detalhamento == SituacaoDetalhamentoAtividadeParticipante.DEFERIDO:
            status = 'aceito'
        return mark_safe(f'<span class="status status-{status}">{self.get_situacao_detalhamento_display()}</span>')

    def deferir_participacao(self, responsavel):
        if not self.problema_com_horas_insuficientes:
            self.data_liberacao = datetime.now()
            self.responsavel_liberacao = responsavel
            self.situacao = SituacaoParticipante.LIBERADO
            self.save()
            self.notificar_liberacao_participante()
        else:
            raise ValidationError('Carga horária insuficiente para a participação no evento/atividade.')

    def indeferir_participacao(self, motivo):
        self.data_liberacao = datetime.now()
        self.situacao = SituacaoParticipante.NAO_LIBERADO
        self.motivo_nao_liberacao = motivo
        self.save()


class CotaExtra(models.ModelPlus):
    SEARCH_FIELDS = ['servidor__pessoa_fisica__nome', 'servidor__matricula']
    LIMITE_MAXIMO_POR_SERVIDOR = Participante.VALOR_PADRAO_HORAS_TRABALHADAS * 2  # o dobro do valor padrão

    servidor = models.ForeignKeyPlus('rh.Servidor', null=False, blank=False, verbose_name='Servidor', on_delete=models.CASCADE)
    ano = models.ForeignKeyPlus('comum.Ano', null=False, blank=False, verbose_name='Ano', on_delete=models.CASCADE)
    horas_permitida = models.FloatField('Horas Permitidas', null=False, blank=False)
    processos = models.ManyToManyFieldPlus(Processo, blank=True, verbose_name='Processos relacionados')
    data_cadastro = models.DateTimeFieldPlus('Data de Cadastro', null=False, blank=False, auto_now_add=True)

    class Meta:
        verbose_name = 'Cota Extra'
        verbose_name_plural = 'Cotas Extras'

    @classmethod
    def cota_extra_servidor_no_ano(cls, servidor, ano):
        qs_cotas = CotaExtra.objects.filter(ano=ano, servidor=servidor)
        saldo_cadastrado = 0
        for c in qs_cotas:
            saldo_cadastrado += c.horas_permitida
        return saldo_cadastrado


# TODO REMOVER A CLASSE COTAANUALSERVIDOR
class CotaAnualServidor(models.ModelPlus):
    """
    Representa a quantidade máxima de horas a serem trabalhadas por um servidor num ano.
    """

    vinculo = models.ForeignKeyPlus('comum.Vinculo')
    ano_pagamento = models.ForeignKeyPlus('comum.Ano', on_delete=models.CASCADE)
    horas_permitidas = models.ForeignKeyPlus(HorasPermitidas, on_delete=models.CASCADE)
    observacao = models.TextField('Observação', blank=True)

    class Meta:
        verbose_name = 'Cota anual do servidor'
        verbose_name_plural = 'Cotas anuais de servidores'
        unique_together = ('vinculo', 'ano_pagamento')

    def __str__(self):
        return f'{self.vinculo.pessoa.nome} / {self.ano_pagamento!s}'

    def matricula(self):
        return self.vinculo.relacionamento.matricula

    matricula.short_description = 'Matrícula'


# TODO REMOVER A CLASSE HORASTRABALHADAS
class HorasTrabalhadas(models.ModelPlus):
    """
    Representa a discriminação das horas trabalhadas num curso ou concurso por um servidor.
    """

    curso = models.ForeignKeyPlus(Curso, on_delete=models.CASCADE)
    cota_anual_servidor = models.ForeignKeyPlus(CotaAnualServidor, editable=False, on_delete=models.CASCADE)
    mes_pagamento = models.PositiveIntegerField('Mês de Pagamento', choices=Meses.get_choices())
    atividade = models.ForeignKeyPlus(Atividade, on_delete=models.CASCADE)
    atividade_valor_hora = models.DecimalFieldPlus(
        editable=False, help_text='Replicado devido a possibilidade de mudança no valor da hora da atividade relacionada.'
    )
    qtd_horas = models.FloatField()

    class Meta:
        ordering = ('mes_pagamento', 'cota_anual_servidor__vinculo__pessoa__nome')
        verbose_name = 'Horas Trabalhadas'
        verbose_name_plural = 'Horas Trabalhadas'
        unique_together = ('curso', 'cota_anual_servidor', 'mes_pagamento', 'atividade', 'atividade_valor_hora')
