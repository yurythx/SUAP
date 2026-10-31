from django.utils.safestring import mark_safe

from comum.models import Ano
from comum.utils import tl
from djtools.db import models
from djtools.templatetags.filters import in_group


class PDP(models.ModelPlus):
    ano = models.OneToOneField(Ano, verbose_name='Ano', related_name='+', on_delete=models.PROTECT)
    descricao = models.CharFieldPlus('Descrição', unique=True)
    data_inicial = models.DateField('Data Inicial para Lançamento')
    data_final = models.DateField('Data Final para Lançamento')
    preenchimento_habilitado = models.BooleanField('Habilita formulário PDP', default=True, help_text='Habilita o módulo de preenchimento do PDP')
    manual = models.FileFieldPlus(
        verbose_name='Manual',
        blank=True,
        null=True,
        max_length=255,
        upload_to='pdp_ifrn/pdp/manuais',
        help_text='Manual com instruções de preenchimento',
    )

    class Meta:
        verbose_name = 'PDP'
        verbose_name_plural = 'PDPs'
        ordering = ['ano']

    def __str__(self):
        return self.descricao

    def unique_error_message(self, model_class, unique_check):
        if model_class is type(self) and unique_check == 'ano':
            return 'Já existe um PDP cadastrado para esse ano!'
        else:
            return super().unique_error_message(model_class, unique_check)


class EnfoqueDesenvolvimento(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição', unique=True)

    def __str__(self):
        return self.descricao

    class Meta:
        verbose_name = 'Enfoque de Desenvolvimento'
        verbose_name_plural = 'Enfoques de Desenvolvimento'
        ordering = ('descricao',)


class AreaTematica(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição', unique=True)

    def __str__(self):
        return self.descricao

    class Meta:
        verbose_name = 'Área Temática'
        verbose_name_plural = 'Áreas Temáticas'
        ordering = ('descricao',)


class Necessidade(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição', max_length=500)
    area_tematica = models.ForeignKeyPlus(AreaTematica, verbose_name='Área Temática', on_delete=models.CASCADE)

    def __str__(self):
        return self.descricao

    class Meta:
        verbose_name = 'Necessidade'
        verbose_name_plural = 'Necessidades'
        ordering = ('descricao',)


class CompetenciaAssociada(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição', unique=True)
    ativa = models.BooleanField(verbose_name='Ativa?', default=True)

    def __str__(self):
        return self.descricao

    class Meta:
        verbose_name = 'Competência Associada'
        verbose_name_plural = 'Competências Associadas'
        ordering = ('descricao',)


class PublicoAlvo(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição', unique=True)

    def __str__(self):
        return self.descricao

    class Meta:
        verbose_name = 'Público-Alvo'
        verbose_name_plural = 'Públicos-Alvo'


class TipoAprendizagem(models.ModelPlus):
    nome = models.CharFieldPlus('Nome', unique=True)
    descricao = models.CharFieldPlus('Descrição', max_length=500)

    def __str__(self):
        return self.nome

    class Meta:
        verbose_name = 'Tipo de Aprendizagem'
        verbose_name_plural = 'Tipos de Aprendizagem'
        ordering = ('nome',)


class EspecificacaoTipoAprendizagem(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição')
    tipo_aprendizagem = models.ForeignKeyPlus(TipoAprendizagem, verbose_name='Tipo de Aprendizagem', on_delete=models.CASCADE)

    def __str__(self):
        return self.descricao

    class Meta:
        verbose_name = 'Especificação de Tipo de Aprendizagem'
        verbose_name_plural = 'Especificações de Tipo de Aprendizagem'
        ordering = ('descricao',)


class Resposta(models.ModelPlus):
    TIPO_MODALIDADE = (
        ('presencial', 'Presencial'),
        ('adistancia', 'À distância'),
        ('hibrido', 'Híbrido'),
        ('indefinido', 'Não definido'),
    )

    TIPO_SIM_NAO = (
        ('sim', 'Sim'),
        ('nao', 'Não'),
    )

    pdp = models.ForeignKeyPlus(PDP, verbose_name='PDP', on_delete=models.CASCADE)
    servidor = models.ForeignKey('rh.Servidor', on_delete=models.CASCADE, related_name='+')
    campus = models.ForeignKey('rh.UnidadeOrganizacional', on_delete=models.CASCADE, related_name='+')
    data_cadastro = models.DateTimeField('Cadastrada Em', auto_now_add=True)
    #
    enfoque_desenvolvimento = models.ForeignKeyPlus(
        EnfoqueDesenvolvimento,
        verbose_name='Enfoque do Desenvolvimento',
        help_text='Qual a área que melhor identifica a temática relacionada a essa necessidade de desenvolvimento? (Macros)',
        on_delete=models.CASCADE,
    )
    enfoque_outros = models.CharFieldPlus(
        verbose_name='Descreva quais são as outras necessidades de desenvolvimento não especificadas', null=True, blank=True
    )
    area_tematica = models.ForeignKeyPlus(
        AreaTematica,
        verbose_name='Área Temática',
        on_delete=models.CASCADE,
    )
    necessidade = models.ForeignKeyPlus(
        Necessidade, verbose_name='Necessidade', help_text='Que necessidade de desenvolvimento o Campus/Reitoria possui?', on_delete=models.CASCADE
    )
    justificativa_necessidade = models.TextField(
        verbose_name='Que resultado essa ação de desenvolvimento trará?',
        max_length=200,
        help_text='<strong>OBS 1: </strong> indique os resultados organizacionais a serem alcançados; '
        '<strong>OBS 2: </strong> indique comportamento e/ou resultados pessoais que os servidores conseguirão apresentar com a realização da ação de desenvolvimento;',
    )
    competencia_associada = models.ManyToManyField(
        CompetenciaAssociada, verbose_name='Competências Associadas', help_text='Essa necessidade está associada a quais competências?'
    )
    acao_transversal = models.CharFieldPlus(
        verbose_name='Ação Transversal',
        help_text='Essa necessidade de desenvolvimento é transversal, ou seja, comum a múltiplas unidades do IFRN?',
        choices=TIPO_SIM_NAO,
        max_length=3,
    )
    publico_alvo = models.ForeignKeyPlus(
        PublicoAlvo,
        verbose_name='Público-Alvo',
        help_text='Qual o público-alvo da ação de desenvolvimento para essa necessidade?',
        on_delete=models.CASCADE,
    )

    #
    # setor_beneficiado = models.ForeignKeyPlus('rh.Setor', verbose_name='Setor Beneficiado', help_text='Qual unidade funcional do IFRN será beneficiada pela ação de desenvolvimento para essa necessidade?', on_delete=models.CASCADE, related_name='setor_beneficiado')
    #
    setor_beneficiado = models.ManyToManyField(
        'rh.Setor',
        verbose_name='Setor Beneficiado',
        help_text='Qual unidade funcional do IFRN será beneficiada pela ação de desenvolvimento para essa necessidade?',
        related_name='setor_beneficiado',
    )

    qtd_pessoas_beneficiadas = models.PositiveSmallIntegerField(
        verbose_name='Qtd de Pessoas Beneficidas',
        help_text='Quantos servidores serão beneficiados pela ação de desenvolvimento para essa necessidade?',
    )
    tipo_aprendizagem = models.ForeignKeyPlus(
        TipoAprendizagem,
        verbose_name='Tipo de Aprendizagem',
        on_delete=models.CASCADE,
        help_text='A ação de desenvolvimento para essa necessidade deve preferencialmente ser ofertada em qual tipo de aprendizagem?',
    )
    especificacao_tipo_aprendizagem = models.ForeignKeyPlus(
        EspecificacaoTipoAprendizagem,
        verbose_name='Especificação de Tipo de Aprendizagem',
        on_delete=models.CASCADE,
        help_text='De acordo com a resposta anterior, qual opção melhor caracteriza o subtipo de aprendizagem?',
    )

    modalidade = models.CharFieldPlus('Modalidade', choices=TIPO_MODALIDADE, max_length=15)
    #
    titulo_necessidade = models.CharFieldPlus(
        'Título previsto da ação de desenvolvimento',
        help_text='Em caso de já possuir uma opção em consideração qual seria o título previsto da ação de desenvolvimento para essa necessidade?',
        max_length=400,
        null=True,
        blank=True,
    )

    ano_termino_acao = models.PositiveSmallIntegerField(
        'Término da Ação',
        help_text='Em caso de já possuir uma opção em consideração, qual o término previsto da ação de desenvolvimento para essa necessidade?',
        null=True,
        blank=True,
    )
    onus_inscricao = models.CharFieldPlus(
        'A ação de desenvolvimento pode ser ofertada de modo gratuito? Sim ou não', choices=TIPO_SIM_NAO, max_length=3
    )
    valor_onus_inscricao = models.DecimalFieldPlus(
        'Se não gratuita, qual o custo total previsto da ação de desenvolvimento para essa necessidade?', null=True, blank=True
    )
    atendida_pelo_cfs = models.CharFieldPlus(
        'Pode ser atendida pelo CFS?',
        choices=TIPO_SIM_NAO,
        max_length=3,
        help_text='A ação de desenvolvimento para essa necessidade pode ser ofertada pelo Centro de Formação de Servidores?',
    )

    def __str__(self):
        return f'{self.servidor} - {self.pdp}'

    class Meta:
        verbose_name = 'Resposta do Questionário PDP (Plano de Desenvolvimento de Pessoas)'
        verbose_name_plural = 'Respostas do Questionários PDP (Plano de Desenvolvimento de Pessoas)'
        ordering = ('servidor',)
        permissions = (
            ('pode_deferir_respostas_pdp', 'Pode deferir respostas do PDP'),
            ('pode_aprovar_respostas_pdp', 'Pode aprovar respostas do PDP'),
            ('pode_homologar_respostas_pdp', 'Pode homologar respostas do PDP'),
        )

    def save(self, *args, **kwargs):
        novo = False
        if not self.pk:
            novo = True
            self.servidor = tl.get_user().get_relacionamento()
            self.campus = self.servidor.setor.uo

        super().save(*args, **kwargs)
        if novo:
            novo_historico = HistoricoStatusResposta()
            novo_historico.resposta = self
            novo_historico.status = 'pendente'
            novo_historico.usuario = tl.get_user()
            novo_historico.save()

    def get_absolute_url(self):
        return f'/pdp_ifrn/resposta/{self.id:d}/'

    def pode_editar(self):
        user = tl.get_user()
        if self.get_ultimo_status == 'pendente':
            if (
                in_group(user, ['Coordenador de PDP Sistêmico'])
                or user.is_superuser
                or user.has_perm('pdp_ifrn.change_resposta')
                and self.servidor == user.get_relacionamento()
            ):
                return True
        return False

    def setor_servidor(self):
        return self.servidor.setor

    setor_servidor.short_description = 'Setor do Servidor'

    def funcao_servidor(self):
        return self.servidor.get_funcao()

    funcao_servidor.short_description = 'Função do Servidor'

    @property
    def get_ultimo_status_descricao(self):
        historico = self.get_latest_historico_status()
        return historico.get_status_display() if historico else None

    @property
    def get_ultimo_status(self):
        historico = self.get_latest_historico_status()
        return historico.status if historico else None

    @property
    def get_data_ultimo_status(self):
        historico = self.get_latest_historico_status()
        return historico.data if historico else None

    @property
    def get_usuario_ultimo_status(self):
        historico = self.get_latest_historico_status()
        return historico.usuario if historico else None

    def get_latest_historico_status(self):
        historico = HistoricoStatusResposta.objects.filter(resposta=self).latest('id')
        return historico or None

    @property
    def status_formatado(self):
        if self.get_ultimo_status == 'pendente':
            return mark_safe('<span class="status status-alert">Pendente</span>')
        elif self.get_ultimo_status == 'deferida':
            return mark_safe('<span class="status status-ativa">Deferida pela Comissão Local</span>')
        elif self.get_ultimo_status == 'indeferida':
            return mark_safe('<span class="status status-inativa">Indeferida pela Comissão Local</span>')

        # elif self.get_ultimo_status == 'aprovada':
        #    return mark_safe('<span class="status status-ativa">Aprovada pela Autoridade Máxima da Unidade</span>')
        elif self.get_ultimo_status == 'aprovada':
            return mark_safe('<span class="status status-ativa">Aprovada pela comissão sistêmica</span>')

        elif self.get_ultimo_status == 'reprovada':
            return mark_safe('<span class="status status-inativa">Reprovada pela Autoridade Máxima da Unidade</span>')

        # elif self.get_ultimo_status == 'homologada':
        #    return mark_safe('<span class="status status-ativa">Homologada pelo Dirigente Máximo</span>')
        elif self.get_ultimo_status == 'homologada':
            return mark_safe('<span class="status status-ativa">Homologada pelo Reitor</span>')

        elif self.get_ultimo_status == 'rejeitada':
            return mark_safe('<span class="status status-inativa">Rejeitada pelo Dirigente Máximo/C.Central</span>')

    @property
    def status_descricao(self):
        if self.get_ultimo_status == 'pendente':
            return 'Pendente'
        elif self.get_ultimo_status == 'deferida':
            return 'Deferida pela Comissão Local'
        elif self.get_ultimo_status == 'indeferida':
            return 'Indeferida pela Comissão Local'

        # elif self.get_ultimo_status == 'aprovada':
        #    return mark_safe('<span class="status status-ativa">Aprovada pela Autoridade Máxima da Unidade</span>')
        elif self.get_ultimo_status == 'aprovada':
            return 'Aprovada pela comissão sistêmica'

        elif self.get_ultimo_status == 'reprovada':
            return 'Reprovada pela Autoridade Máxima da Unidade'

        # elif self.get_ultimo_status == 'homologada':
        #    return mark_safe('<span class="status status-ativa">Homologada pelo Dirigente Máximo</span>')
        elif self.get_ultimo_status == 'homologada':
            return 'Homologada pelo Reitor'

        elif self.get_ultimo_status == 'rejeitada':
            return 'Rejeitada pelo Dirigente Máximo/C.Central'

    def setores_beneficiados_str(self):
        if self.setor_beneficiado:
            str = ''
            for s in self.setor_beneficiado.all():
                str += f'{s}, '
            return str[:-2]
        return '-'


class HistoricoStatusResposta(models.ModelPlus):
    # STATUS_RESPOSTA = (
    #    ('pendente', 'Pendente'),
    #    ('deferida', 'Deferida pela Comissão Local do Campus/Reitoria'),
    #    ('indeferida', 'Indeferida pela Comissão Local do Campus/Reitoria'),
    #    ('aprovada', 'Aprovada pelo Dirigente Máximo do Campus/Reitoria'),
    #    ('reprovada', 'Reprovada pelo Dirigente Máximo do Campus/Reitoria'),
    #    ('homologada', 'Homologada pelo Reitor'),
    #    ('rejeitada', 'Rejeitada pelo Reitor'),
    # )

    STATUS_RESPOSTA = (
        ('pendente', 'Pendente'),
        ('deferida', 'Deferida pela Comissão Local'),
        ('indeferida', 'Indeferida pela Comissão Local'),
        ('aprovada', 'Aprovada pela Comissão Sistêmica'),
        ('reprovada', 'Reprovada pelo Dirigente Máximo do Campus/Reitoria'),
        ('homologada', 'Homologada pelo Reitor'),
        ('rejeitada', 'Não Homologada pelo Reitor'),
    )

    resposta = models.ForeignKey(Resposta, on_delete=models.CASCADE, related_name='historico_status')
    data = models.DateTimeField(auto_now_add=True)
    usuario = models.CurrentUserField()
    status = models.CharFieldPlus('Situação', default=STATUS_RESPOSTA, max_length=10)
    justificativa = models.CharFieldPlus('Justificativa', null=True, blank=True)

    class Meta:
        verbose_name = 'Situação de Resposta do Questionário PDP'
        verbose_name_plural = 'Situações de Resposta do Questionário PDP'
        ordering = ('-data',)
