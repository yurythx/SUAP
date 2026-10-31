from django.conf import settings
from django.core.exceptions import ValidationError
from djtools.db import models, transaction
from djtools.utils import send_notification
from edu import perms
from edu.managers import AtividadeAprofundamentoManager, AtividadeComplementarManager

from .cadastros_gerais import PERIODO_LETIVO_CHOICES
from .logs import LogModel
from .procedimentos import ProcedimentoReducaoCH


class ConfiguracaoAtividadeAprofundamento(LogModel):
    id = models.AutoField(verbose_name='Código', primary_key=True)
    descricao = models.CharFieldPlus('Descrição', width=500)
    ch_maxima_extensao = models.IntegerField('C.H Máx. de Extensão', default=0)

    class Meta:
        verbose_name = 'Configuração de ATPA'
        verbose_name_plural = 'Configurações de ATPA'

    def get_absolute_url(self):
        return f'/edu/configuracaoatividadeaprofundamento/{self.pk:d}/'

    def replicar(self, descricao):
        configuracao_replicada = ConfiguracaoAtividadeAprofundamento()
        configuracao_replicada.descricao = descricao
        configuracao_replicada.save()
        for atividade_academica in self.itemconfiguracaoatividadeaprofundamento_set.all():
            nova_atividade_academica = ItemConfiguracaoAtividadeAprofundamento()
            nova_atividade_academica.configuracao = configuracao_replicada
            nova_atividade_academica.tipo = atividade_academica.tipo
            nova_atividade_academica.carga_horaria = atividade_academica.carga_horaria
            nova_atividade_academica.obs_carga_horaria = atividade_academica.obs_carga_horaria
            nova_atividade_academica.save()
        return configuracao_replicada


class ItemConfiguracaoAtividadeAprofundamento(LogModel):
    configuracao = models.ForeignKeyPlus(ConfiguracaoAtividadeAprofundamento, verbose_name='Configuração de ATPA')
    tipo = models.ForeignKeyPlus('edu.TipoAtividadeAprofundamento')
    carga_horaria = models.IntegerField('Carga horária', blank=True, null=True)
    obs_carga_horaria = models.CharFieldPlus(
        'Observação da carga horária', help_text='Informação adicional sobre a carga horária da atividade.', blank=True, null=True
    )

    class Meta:
        verbose_name = 'Item de Configuração de ATPA'
        verbose_name_plural = 'Itens de Configuração de ATPA'


class AtividadeAprofundamento(LogModel):
    aluno = models.ForeignKeyPlus('edu.Aluno', verbose_name='Aluno', null=False, blank=True)

    tipo = models.ForeignKeyPlus('edu.TipoAtividadeAprofundamento', verbose_name='Tipo', on_delete=models.CASCADE)
    ano_letivo = models.ForeignKeyPlus('comum.Ano', verbose_name='Ano Letivo', null=False, blank=False, on_delete=models.CASCADE)
    periodo_letivo = models.PositiveIntegerField('Período Letivo', choices=PERIODO_LETIVO_CHOICES, null=False, blank=False)

    descricao = models.CharFieldPlus('Atividade', null=False, blank=False, help_text='Nome da atividade com até 100 caracteres.')
    data_atividade = models.DateFieldPlus('Data da Atividade', null=False, blank=False)
    carga_horaria = models.IntegerField('Carga Horária', null=False, blank=False)
    informacoes_complementares = models.TextField('Informações Complementares', null=True, blank=True)
    documento = models.FileFieldPlus(
        'Anexo',
        upload_to='edu/atividade_complementar/',
        null=True,
        blank=False,
        check_mimetype=False,
        help_text='Neste campo você pode anexar um certificado ou comprovante, por exemplo. Tipos de arquivos aceitados: pdf, png ou jpg. Tamanho Máximo: 5Mb',
        filetypes=['pdf', 'png', 'jpg'],
        max_file_size=5242880,
    )
    deferida = models.BooleanField(verbose_name='Deferida', null=True)
    razao_indeferimento = models.TextField(null=True, verbose_name='Razão do Indeferimento', blank=True)

    class Meta:
        verbose_name = 'Atividade Teórico-Prática de Aprofundamento'
        verbose_name_plural = 'Atividades Teórico-Práticas de Aprofundamento'

    objects = models.Manager()
    locals = AtividadeAprofundamentoManager()

    def get_absolute_url(self):
        return f'/edu/atividadeaprofundamento/{self.pk}/'

    def enviar_email_coordenador(self):
        vinculo = self.aluno.curso_campus.coordenador
        if not vinculo:
            return False

        titulo = '[SUAP] Solicitação de Atividade de Aprofundamento'
        texto = (
            '<h1>Ensino</h1>'
            '<h2>Solicitação de Atividade de Aprofundamento</h2>'
            f'<p>O aluno {self.aluno} solicitou o deferimento de uma atividade de aprofundamento.</p>'
            f'<p>Acesse {settings.SITE_URL}/edu/aluno/{self.aluno.matricula}/?tab=atividades_aprofundamento para deferir ou indeferir a solicitação.</p>'
        )

        return send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [vinculo], fail_silently=True)

    def can_change(self, user):
        result = False
        if user.username == self.aluno.matricula:
            result = self.deferida is None
        else:
            result = perms.realizar_procedimentos_academicos(user, self.aluno.curso_campus)
        return result

    def can_delete(self, user):
        return user.has_perm('edu.delete_atividadeaprofundamento') and perms.realizar_procedimentos_academicos(user, self.aluno.curso_campus)

    @transaction.atomic()
    def delete(self, *args, **kwargs):
        is_deferida = self.deferida
        motivo = kwargs.pop('motivo', None)
        vinculo = kwargs.pop('vinculo', None)
        if is_deferida:
            ch_cumprida_anterior = self.aluno.get_ch_cumprida()
            ano_letivo = self.ano_letivo
            periodo_letivo = self.periodo_letivo
            atividade = self.tipo
            ch_anterior_atividade = self.carga_horaria
        super().delete(*args, **kwargs)
        if is_deferida:
            self.aluno.atualizar_situacao('Exclusão de atividade de aprofundamento')
            ch_cumprida_nova = self.aluno.get_ch_cumprida()
            if ch_cumprida_nova < ch_cumprida_anterior:
                pr = ProcedimentoReducaoCH()
                pr.matricula_periodo = self.aluno.get_matricula_periodo(ano_letivo=ano_letivo, periodo_letivo=periodo_letivo)
                pr.tipo_procedimento = ProcedimentoReducaoCH.ATIVIDADE_APROFUNDAMENTO
                pr.motivo = motivo
                pr.informacao_complementar = f'Exclusão da atividade de aprofundamento <strong>{atividade}</strong> ({ch_anterior_atividade}h).'
                pr.vinculo = vinculo
                pr.ch_nova = ch_cumprida_nova
                pr.ch_anterior = ch_cumprida_anterior
                pr.save()

    @transaction.atomic()
    def desfazer_avaliacao(self, motivo, vinculo):
        is_deferida = self.deferida
        if is_deferida:
            ch_cumprida_anterior = self.aluno.get_ch_cumprida()
        self.deferida = None
        self.razao_indeferimento = None
        self.save()

        if is_deferida:
            pr = ProcedimentoReducaoCH()
            pr.matricula_periodo = self.aluno.get_matricula_periodo(ano_letivo=self.ano_letivo, periodo_letivo=self.periodo_letivo)
            pr.tipo_procedimento = ProcedimentoReducaoCH.ATIVIDADE_APROFUNDAMENTO
            pr.motivo = motivo
            pr.informacao_complementar = (
                f'Cancelamento do deferimento da atividade de aprofundamento: <strong>{self.tipo}</strong> ({self.carga_horaria}h).'
            )
            pr.vinculo = vinculo
            pr.ch_nova = self.aluno.get_ch_cumprida()
            pr.ch_anterior = ch_cumprida_anterior
            pr.save()


class AtividadeComplementar(LogModel):
    aluno = models.ForeignKeyPlus('edu.Aluno', verbose_name='Aluno', null=False, blank=True)

    tipo = models.ForeignKeyPlus('edu.TipoAtividadeComplementar', verbose_name='Tipo', on_delete=models.CASCADE)
    ano_letivo = models.ForeignKeyPlus('comum.Ano', verbose_name='Ano Letivo', null=False, blank=False, on_delete=models.CASCADE)
    periodo_letivo = models.PositiveIntegerField('Período Letivo', choices=PERIODO_LETIVO_CHOICES, null=False, blank=False)

    descricao = models.CharFieldPlus(
        'Atividade', null=False, blank=False, help_text='Nome da atividade com até 100 caracteres.', validate_caracter=True
    )
    data_atividade = models.DateFieldPlus('Data de Início da Atividade', null=False, blank=False)
    data_conclusao_atividade = models.DateFieldPlus('Data da Conclusão da Atividade', null=True, blank=False)
    carga_horaria = models.IntegerField('Carga Horária', null=False, blank=False)
    informacoes_complementares = models.TextField('Informações Complementares', null=True, blank=True)
    documento = models.FileFieldPlus(
        'Anexo',
        upload_to='edu/atividade_complementar/',
        null=True,
        blank=True,
        check_mimetype=False,
        help_text='Neste campo você pode anexar um certificado ou comprovante, por exemplo. Tipos de arquivos aceitados: pdf, png ou jpg. Tamanho Máximo: 5Mb',
        filetypes=['pdf', 'png', 'jpg'],
        max_file_size=5242880,
    )
    data_deferimento_atividade = models.DateFieldPlus('Data de Deferimento da Atividade', null=True, blank=False)
    deferida = models.BooleanField(verbose_name='Deferida', null=True)
    razao_indeferimento = models.TextField(null=True, verbose_name='Razão do Indeferimento', blank=True)

    class Meta:
        verbose_name = 'Atividade Complementar'
        verbose_name_plural = 'Atividades Complementares'

    objects = models.Manager()
    locals = AtividadeComplementarManager()

    def is_curricular(self):
        return ItemConfiguracaoAtividadeComplementar.objects.filter(configuracao__matriz=self.aluno.matriz, tipo=self.tipo).exists()

    def ano_periodo_letivo(self):
        return f'{self.ano_letivo.ano}.{self.periodo_letivo}'

    def clean(self):
        if self.descricao and self.deferida and len(self.descricao) > 100:
            raise ValidationError('O nome da atividade deve ter até 100 caracteres.')
        if self.deferida is not None and not self.deferida and not self.razao_indeferimento:
            raise ValidationError('Por favor, informe a razão do indeferimento')

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.pk or self.is_curricular():
            self.aluno.atualizar_situacao('Lançamento de Atividade Complementar')

    @transaction.atomic()
    def delete(self, *args, **kwargs):
        is_curricular_deferida = self.is_curricular() and self.deferida
        motivo = kwargs.pop('motivo', None)
        vinculo = kwargs.pop('vinculo', None)
        if is_curricular_deferida:
            ch_cumprida_anterior = self.aluno.get_ch_cumprida()
            ano_letivo = self.ano_letivo
            periodo_letivo = self.periodo_letivo
            atividade = self.tipo
            ch_anterior_atividade = self.carga_horaria
        super().delete(*args, **kwargs)
        if self.pk or self.is_curricular():
            self.aluno.atualizar_situacao('Exclusão de Atividade Complementar')
            if is_curricular_deferida:
                ch_cumprida_nova = self.aluno.get_ch_cumprida()
                pr = ProcedimentoReducaoCH()
                pr.matricula_periodo = self.aluno.get_matricula_periodo(ano_letivo=ano_letivo, periodo_letivo=periodo_letivo)
                pr.tipo_procedimento = ProcedimentoReducaoCH.ATIVIDADE_COMPLEMENTAR
                pr.motivo = motivo
                pr.informacao_complementar = f'Exclusão da atividade complementar <strong>{atividade}</strong> ({ch_anterior_atividade}h).'
                pr.vinculo = vinculo
                pr.ch_nova = ch_cumprida_nova
                pr.ch_anterior = ch_cumprida_anterior
                pr.save()

    @transaction.atomic()
    def desfazer_avaliacao(self, motivo, vinculo):
        is_curricular_deferida = self.deferida and self.is_curricular()
        if is_curricular_deferida:
            ch_cumprida_anterior = self.aluno.get_ch_cumprida()
        self.deferida = None
        self.data_deferimento_atividade = None
        self.razao_indeferimento = None
        self.save()

        if is_curricular_deferida:
            pr = ProcedimentoReducaoCH()
            pr.matricula_periodo = self.aluno.get_matricula_periodo(ano_letivo=self.ano_letivo, periodo_letivo=self.periodo_letivo)
            pr.tipo_procedimento = ProcedimentoReducaoCH.ATIVIDADE_COMPLEMENTAR
            pr.motivo = motivo
            pr.informacao_complementar = (
                f'Cancelamento do deferimento da atividade complementar: <strong>{self.tipo}</strong> ({self.carga_horaria}h).'
            )
            pr.vinculo = vinculo
            pr.ch_nova = self.aluno.get_ch_cumprida()
            pr.ch_anterior = ch_cumprida_anterior
            pr.save()

    def enviar_email_coordenador(self):
        vinculo = self.aluno.curso_campus.coordenador
        if not vinculo:
            return False

        titulo = '[SUAP] Solicitação de Atividade Complementar'
        texto = (
            '<h1>Ensino</h1>'
            '<h2>Solicitação de Atividade Complementar</h2>'
            f'<p>O aluno {self.aluno} solicitou o deferimento de uma atividade acadêmica.</p>'
            f'<p>Acesse {settings.SITE_URL}/edu/aluno/{self.aluno.matricula}/?tab=acc para deferir ou indeferir a solicitação.</p>'
        )

        return send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [vinculo], fail_silently=True)

    def get_absolute_url(self):
        return f'/edu/atividadecomplementar/{self.pk}/'

    def get_data_conclusao_atividade(self):
        return self.data_conclusao_atividade or self.data_atividade

    def get_data_deferimento_atividade(self):
        return self.data_deferimento_atividade or self.data_atividade


class ConfiguracaoAtividadeComplementar(LogModel):
    id = models.AutoField(verbose_name='Código', primary_key=True)
    descricao = models.CharFieldPlus('Descrição', width=500)
    ch_maxima_extensao = models.IntegerField('C.H Máx. de Extensão', default=0)

    class Meta:
        verbose_name = 'Configuração de AACCs'
        verbose_name_plural = 'Configurações de AACCs'

    def get_absolute_url(self):
        return f'/edu/configuracaoatividadecomplementar/{self.pk:d}/'

    def replicar(self, descricao):
        configuracao_replicada = ConfiguracaoAtividadeComplementar()
        configuracao_replicada.descricao = descricao
        configuracao_replicada.save()
        for atividade_academica in self.itemconfiguracaoatividadecomplementar_set.all():
            nova_atividade_academica = ItemConfiguracaoAtividadeComplementar()
            nova_atividade_academica.configuracao = configuracao_replicada
            nova_atividade_academica.tipo = atividade_academica.tipo
            nova_atividade_academica.pontuacao_max_periodo = atividade_academica.pontuacao_max_periodo
            nova_atividade_academica.pontuacao_max_curso = atividade_academica.pontuacao_max_curso
            nova_atividade_academica.fator_conversao = atividade_academica.fator_conversao
            nova_atividade_academica.save()
        return configuracao_replicada


class ItemConfiguracaoAtividadeComplementar(LogModel):
    configuracao = models.ForeignKeyPlus('edu.ConfiguracaoAtividadeComplementar', verbose_name='Configuração Atividades Acadêmicas')
    tipo = models.ForeignKeyPlus('edu.TipoAtividadeComplementar')
    pontuacao_min_curso = models.IntegerField('Pontuação Mínima no Curso', null=True, blank=True)
    pontuacao_max_periodo = models.IntegerField('Pontuação Máxima no Período', null=True, blank=True)
    pontuacao_max_curso = models.IntegerField('Pontuação Máxima no Curso', null=True, blank=True)
    pontuacao_por_evento = models.IntegerField(
        'Pontuação por Registro',
        help_text='Obrigatório apenas quando o registro dessa atividade complementar não requerer a entrada da carga horário pelo secretário acadêmico. Ex: Capítulo de Livro.',
        null=True,
        blank=True,
    )
    fator_conversao = models.DecimalFieldPlus('Fator de conversão (Peso)')

    ch_min_curso = models.IntegerField('C.H. Mínima no Curso', null=True)
    ch_max_periodo = models.IntegerField('C.H. Máxima no Período', null=True)
    ch_max_curso = models.IntegerField('C.H. Máxima no Curso', null=True)
    ch_por_evento = models.IntegerField('C.H. por Evento', null=True)
    percentual_considerar = models.IntegerField('Percentual a Considerar', default=100)

    class Meta:
        verbose_name = 'Item de Configuração de AACC'
        verbose_name_plural = 'Itens de Configuração de AACC'
        unique_together = ('configuracao', 'tipo')

    def save(self, *args, **kwargs):
        self.ch_min_curso = None
        self.ch_max_periodo = None
        self.ch_max_curso = None
        self.ch_por_evento = None
        if self.pontuacao_min_curso:
            self.ch_min_curso = int(self.pontuacao_min_curso * self.fator_conversao)
        if self.pontuacao_max_periodo:
            self.ch_max_periodo = int(self.pontuacao_max_periodo * self.fator_conversao)
        if self.pontuacao_max_curso:
            self.ch_max_curso = int(self.pontuacao_max_curso * self.fator_conversao)
        if self.pontuacao_por_evento:
            self.ch_por_evento = int(self.pontuacao_por_evento * self.fator_conversao)
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.tipo}'
