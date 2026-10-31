import datetime

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.safestring import mark_safe

from comum.models import User, UsuarioGrupo, UsuarioGrupoSetor, Vinculo
from djtools.db import models
from djtools.templatetags.filters import filename
from djtools.templatetags.filters.utils import in_group
from djtools.utils import send_notification
from edu.models import LogModel, SolicitacaoUsuario
from etep import managers


class Categoria(LogModel):
    nome = models.CharFieldPlus('Tipo', unique=True, null=False, blank=False)
    descricao = models.CharFieldPlus('Descrição', null=True, blank=True)

    class Meta:
        verbose_name = 'Tipo de Acompanhamento'
        verbose_name_plural = 'Tipos de Acompanhamentos'

        ordering = ('nome',)

    def __str__(self):
        return self.nome

    def get_absolute_url(self):
        return f'/edu/visualizar/etep/categoria/{self.pk}/'


class Encaminhamento(LogModel):
    nome = models.CharFieldPlus('Tipo', unique=True, null=False, blank=False)
    descricao = models.CharFieldPlus('Descrição', null=True, blank=True)

    class Meta:
        verbose_name = 'Tipo de Encaminhamento'
        verbose_name_plural = 'Tipo de Encaminhamentos'

        ordering = ('nome',)

    def __str__(self):
        return self.nome

    def get_absolute_url(self):
        return f'/edu/visualizar/etep/encaminhamento/{self.pk}/'


class Acompanhamento(LogModel):
    EM_ACOMPANHAMENTO = 1
    ACOMPANHAMENTO_FINALIZADO = 2
    ACOMPANHAMENTO_PRIORITARIO = 3

    SITUACAO_CHOICES = [
        [EM_ACOMPANHAMENTO, 'Em acompanhamento'],
        [ACOMPANHAMENTO_FINALIZADO, 'Finalizado'],
        [ACOMPANHAMENTO_PRIORITARIO, 'Prioritário'],
    ]

    aluno = models.ForeignKeyPlus('edu.Aluno', on_delete=models.CASCADE)
    data = models.DateTimeFieldPlus(auto_now_add=True)
    usuario = models.CurrentUserField(verbose_name='Usuário')
    situacao = models.IntegerField('Situação', choices=SITUACAO_CHOICES, null=True, blank=True)

    objects = models.Manager()
    locals = managers.AcompanhamentoManager()

    class Meta:
        verbose_name = 'Acompanhamento'
        verbose_name_plural = 'Acompanhamento'
        ordering = ('-data',)

    def get_absolute_url(self):
        return f'/etep/acompanhamento/{self.id}/'

    def get_situacao(self):
        return self.situacao

    def get_situacao_display(self):
        for situacao in self.SITUACAO_CHOICES:
            if situacao[0] == self.get_situacao():
                return mark_safe(situacao[1])
        return mark_safe(self.SITUACAO_CHOICES[0][1])

    get_situacao_display.short_description = 'Situação'

    def get_categorias(self):
        return self.acompanhamentocategoria_set.values_list('categoria__nome', flat=True)

    def get_encaminhamentos(self):
        return self.acompanhamentoencaminhamento_set.values_list('encaminhamento__nome', flat=True)

    def get_interessados(self):
        return Vinculo.objects.filter(interessado__ativado=True, interessado__acompanhamento__id=self.pk)

    def get_membros_etep(self):
        # membros ETEP do campus do aluno
        uo = self.aluno.curso_campus.diretoria.setor.uo
        users = UsuarioGrupoSetor.objects.filter(setor__uo=uo, usuario_grupo__group__name='Membro ETEP').values_list(
            'usuario_grupo__user_id', flat=True
        )
        return User.objects.filter(id__in=users)

    def __str__(self):
        return f'Acompanhamento de {self.aluno.pessoa_fisica.nome}'


class RegistroAcompanhamento(LogModel):
    EM_ACOMPANHAMENTO = 1
    ACOMPANHAMENTO_FINALIZADO = 2
    ACOMPANHAMENTO_PRIORITARIO = 3

    SITUACAO_CHOICES = [
        [EM_ACOMPANHAMENTO, 'Em acompanhamento'],
        [ACOMPANHAMENTO_FINALIZADO, 'Finalizado'],
        [ACOMPANHAMENTO_PRIORITARIO, 'Prioritário'],
    ]

    acompanhamento = models.ForeignKeyPlus('etep.Acompanhamento', on_delete=models.CASCADE)
    usuario = models.CurrentUserField(verbose_name='Usuário')
    descricao = models.TextField('Descrição', blank=True, null=True)
    situacao = models.IntegerField('Situação', choices=SITUACAO_CHOICES, null=True, blank=True)
    data = models.DateTimeFieldPlus(auto_now_add=True)
    anexo = models.FileFieldPlus(
        'Anexo',
        upload_to='etep/acompanhamento/',
        null=True,
        blank=True,
        help_text='Anexe um arquivo referente ao acompanhamento do aluno',
        max_file_size=5242880,
    )

    locals = managers.RegistroAcompanhamentoManager()
    objects = models.Manager()

    def todos_veem(self):
        for interessado in self.acompanhamento.get_interessados():
            if not RegistroAcompanhamentoInteressado.objects.filter(interessado__interessado=interessado, registro_acompanhamento=self).exists():
                return False
        return True

    def enviar_emails(self, vinculos, situacao=False):
        url_acompanhamento = settings.SITE_URL + self.acompanhamento.get_absolute_url()
        if situacao:
            titulo = '[SUAP] Atualização de Situação do Acompanhamento ETEP'
            texto = f"""
                O servidor {self.usuario} alterou a situação do acompanhamento do aluno {self.acompanhamento.aluno} para "{self.acompanhamento.get_situacao_display()}".
                Para mais informações acesse: <a href="{url_acompanhamento}">{url_acompanhamento}</a>
            """
        else:
            anexo = '-'
            if self.anexo:
                url_anexo = settings.SITE_URL + self.anexo.url
                anexo = f'<a href="{url_anexo}">Baixar anexo</a>'
            titulo = '[SUAP] Atualização de Acompanhamento ETEP'
            texto = """
                    <h1>ETEP</h1>
                    <h2>Atualização de Acompanhamento</h2>
                    <p>O servidor {} registrou um acompanhamento para o aluno {}.</p>
                    <dl>
                        <dt>Comentário:</dt><dd>{}</dd>
                        <dt>Anexo:</dt><dd>{}</dd>
                    </dl>
                    <p class="more-info">Para mais informações, acesse: <a href="{}">{}</a></p>
                """.format(self.usuario, self.acompanhamento.aluno, self.descricao or '-', anexo, url_acompanhamento, url_acompanhamento)
        send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, vinculos)

    def __str__(self):
        return f'Usuário {self.usuario} escreveu {self.descricao} no registro de {self.acompanhamento}'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.situacao:
            self.acompanhamento.situacao = self.situacao
            self.acompanhamento.save()


class RegistroAcompanhamentoInteressado(LogModel):
    registro_acompanhamento = models.ForeignKeyPlus('etep.RegistroAcompanhamento', on_delete=models.CASCADE)
    interessado = models.ForeignKeyPlus('etep.Interessado', on_delete=models.CASCADE)
    data_solicitacao = models.DateTimeFieldPlus(auto_now_add=True, verbose_name='Data de Solicitação de Ciência')
    data_ciencia = models.DateTimeFieldPlus(null=True, blank=True, verbose_name='Data da Ciência')
    usuario = models.CurrentUserField(verbose_name='Usuário')

    class Meta:
        unique_together = ('registro_acompanhamento', 'interessado')

    def __str__(self):
        return str(self.interessado.vinculo)


class AcompanhamentoCategoria(LogModel):
    acompanhamento = models.ForeignKeyPlus('etep.Acompanhamento')
    categoria = models.ForeignKeyPlus('etep.Categoria', verbose_name='Categoria')

    class Meta:
        unique_together = ('acompanhamento', 'categoria')


class AcompanhamentoEncaminhamento(LogModel):
    acompanhamento = models.ForeignKeyPlus('etep.Acompanhamento', on_delete=models.CASCADE)
    usuario = models.CurrentUserField(verbose_name='Usuário')
    data = models.DateTimeFieldPlus(auto_now_add=True)
    encaminhamento = models.ForeignKeyPlus('etep.Encaminhamento', verbose_name='Encaminhamento')

    def __str__(self):
        return f'Encaminhamento {self.encaminhamento} do {self.acompanhamento}'

    def enviar_emails(self, vinculos):
        url_acompanhamento = settings.SITE_URL + self.acompanhamento.get_absolute_url()
        titulo = '[SUAP] Atualização de Encaminhamentos ETEP'
        texto = f"""
                <h1>Atualização de Encaminhamentos ETEP</h1>
                <p>O servidor {self.usuario} adicionou o encaminhamento "{self.encaminhamento.nome}" para o aluno {self.acompanhamento.aluno}.</p>
                <p class="more-info">Para mais informações, acesse: <a href="{url_acompanhamento}">{url_acompanhamento}</a></p>
            """
        send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, vinculos)


class SolicitacaoAcompanhamentoCategoria(LogModel):
    solicitacao = models.ForeignKeyPlus('etep.SolicitacaoAcompanhamento')
    categoria = models.ForeignKeyPlus('etep.Categoria')

    class Meta:
        unique_together = ('solicitacao', 'categoria')


class SolicitacaoAcompanhamento(SolicitacaoUsuario):
    aluno = models.ForeignKeyPlus('edu.Aluno')
    acompanhamento = models.ForeignKeyPlus('etep.Acompanhamento', null=True)

    objects = models.Manager()
    locals = managers.SolicitacaoAcompanhamentoManager()

    class Meta:
        verbose_name = 'Solicitação de Acompanhamento'
        verbose_name_plural = 'Solicitações de Acompanhamento'
        ordering = ('data_solicitacao',)

    def save(self, *args, **kwargs):
        self.uo = self.aluno.curso_campus.diretoria.setor.uo
        return super().save(*args, **kwargs)

    def atender(self, avaliador, aluno=None):
        acompanhamento = Acompanhamento.objects.create(aluno=self.aluno)
        self.data_avaliacao = datetime.datetime.now()
        self.avaliador = avaliador
        self.atendida = True
        self.acompanhamento = acompanhamento
        self.save()
        categorias = self.solicitacaoacompanhamentocategoria_set.all().values_list('categoria__id', flat=True)
        for categoria in categorias:
            AcompanhamentoCategoria.objects.create(categoria=Categoria.objects.get(id=categoria), acompanhamento=acompanhamento)
        RegistroAcompanhamento.objects.create(acompanhamento=acompanhamento, situacao=RegistroAcompanhamento.EM_ACOMPANHAMENTO)
        Interessado.objects.create(acompanhamento=acompanhamento, vinculo=self.solicitante.get_vinculo())
        if not aluno:
            self.enviar_email(avaliador)

    def get_categorias(self):
        return self.solicitacaoacompanhamentocategoria_set.values_list('categoria__nome', flat=True)

    def rejeitar(self, avaliador, razao_indeferimento, aluno=None):
        self.data_avaliacao = datetime.datetime.now()
        self.avaliador = avaliador
        self.atendida = False
        self.razao_indeferimento = razao_indeferimento
        self.save()
        if not aluno:
            self.enviar_email(avaliador)

    def get_absolute_url(self):
        return f'/etep/solicitacao_acompanhamento/{self.pk}/'


class Interessado(LogModel):
    COORDENADOR_CURSO = 'coordenador_curso'
    PROFESSOR = 'professor'
    ETEP = 'etep'
    MULTIPROFISSIONAL = 'multiprofissional'

    FUNCAO_CHOICES = [
        [COORDENADOR_CURSO, 'Coordenador de Curso'],
        [PROFESSOR, 'Professor'],
        [ETEP, 'ETEP'],
        [MULTIPROFISSIONAL, 'Equipe Multiprofissional'],
    ]

    acompanhamento = models.ForeignKeyPlus('etep.Acompanhamento')
    vinculo = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Interessado')
    ativado = models.BooleanField(default=True)
    funcao = models.CharField(verbose_name='Função', choices=FUNCAO_CHOICES, null=True)

    objects = models.Manager()
    locals = managers.InteressadoManager()

    class Meta:
        verbose_name = 'Interessado'
        verbose_name_plural = 'Interessados'
        unique_together = (('acompanhamento', 'vinculo'),)

    def __str__(self):
        return f'{self.vinculo}'

    def eh_ativo(self):
        return self.ativado

    def responsavel(self):
        return self.registrointeressado_set.latest('id').usuario.get_profile()

    def data_inclusao(self):
        return self.registrointeressado_set.earliest('id').data

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.registrointeressado_set.exists():
            self.ativar()

    def inativar(self):
        from edu.forms import grupos

        if not self.eh_ativo():
            return
        Interessado.objects.filter(pk=self.pk).update(ativado=False)
        if Interessado.locals.ativos().filter(vinculo=self.vinculo).count() == 1:
            UsuarioGrupo.objects.filter(group=grupos()['INTERESSADO_ETEP'], user=self.vinculo.user).delete()
        RegistroInteressado.objects.create(interessado=self, adicionado=False)

    def ativar(self):
        from edu.forms import grupos

        if self.eh_ativo():
            return
        Interessado.objects.filter(pk=self.pk).update(ativado=True)
        RegistroInteressado.objects.create(interessado=self)
        UsuarioGrupo.objects.get_or_create(group=grupos()['INTERESSADO_ETEP'], user=self.vinculo.user)


class RegistroInteressado(LogModel):
    usuario = models.CurrentUserField(verbose_name='Usuário')
    data = models.DateTimeFieldPlus(auto_now_add=True)
    interessado = models.ForeignKeyPlus('etep.Interessado')
    adicionado = models.BooleanField(default=True)


class TipoAtividade(LogModel):
    nome = models.CharFieldPlus('Tipo', unique=True, null=False, blank=False)
    descricao = models.CharFieldPlus('Descrição', null=True, blank=True)

    class Meta:
        verbose_name = 'Tipo de Atividade'
        verbose_name_plural = 'Tipos de Atividade'
        ordering = ('nome',)

    def __str__(self):
        return self.nome

    def get_absolute_url(self):
        return f'/edu/visualizar/etep/tipoatividade/{self.pk}/'


class Atividade(LogModel):
    titulo = models.CharFieldPlus('Título', null=False, blank=False)
    descricao = models.TextField('Descrição', null=False, blank=False)
    data_inclusao = models.DateTimeFieldPlus('Data de envio', auto_now_add=True)
    data_inicio_atividade = models.DateTimeFieldPlus('Data de Início', null=False, blank=False)
    data_fim_atividade = models.DateTimeFieldPlus('Data de Fim', null=False, blank=False)
    visibilidade = models.BooleanField(
        'Visibilidade', default=False, help_text='Marque essa opção para tornar visível esta atividade para os membros ETEP de outros campus'
    )
    usuario = models.CurrentUserField(verbose_name='Autor')
    tipo = models.ForeignKeyPlus('etep.TipoAtividade', verbose_name='Tipo de Atividade', null=False, blank=False, on_delete=models.CASCADE)

    objects = models.Manager()
    locals = managers.AtividadeManager()

    def clean(self):
        if self.data_inicio_atividade and self.data_fim_atividade and self.data_inicio_atividade > self.data_fim_atividade:
            raise ValidationError('Data de início não pode ser maior que a data de fim da atividade.')

    class Meta:
        verbose_name = 'Atividade'
        verbose_name_plural = 'Atividade'

    def __str__(self):
        return f'Atividade #{self.pk} - {self.titulo}'

    def get_absolute_url(self):
        return f'/etep/atividade/{self.pk}/'

    def get_visibilidade(self):
        uo = self.usuario.get_relacionamento().setor and self.usuario.get_relacionamento().setor.uo or '-'
        if not self.visibilidade:
            status = ['error', uo]
        else:
            status = ['success', f'Compartilhada ({uo})']
        return mark_safe(f'<span class="status status-{status[0]}">{status[1]}</span>')

    get_visibilidade.short_description = 'Visibilidade'
    get_visibilidade.admin_order_field = 'visibilidade'

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def can_change(self, user):
        return (
            in_group(user, 'Administrador Acadêmico, etep Administrador')
            or self.usuario.get_relacionamento().setor
            and self.usuario.get_relacionamento().setor.uo == user.get_relacionamento().setor.uo
        )


class TipoDocumento(LogModel):
    nome = models.CharFieldPlus('Tipo', unique=True, null=False, blank=False)
    descricao = models.CharFieldPlus('Descrição', null=True, blank=True)

    class Meta:
        verbose_name = 'Tipo de Documento'
        verbose_name_plural = 'Tipos de Documento'
        ordering = ('nome',)

    def __str__(self):
        return self.nome

    def get_absolute_url(self):
        return f'/edu/visualizar/etep/tipodocumento/{self.pk}/'


class Documento(LogModel):
    arquivo = models.FileFieldPlus(
        'Anexo',
        upload_to='etep/documento/',
        null=False,
        blank=False,
        help_text='Anexe um arquivo referente documento da atividade',
        max_file_size=5242880,
    )
    tipo = models.ForeignKeyPlus('etep.TipoDocumento', verbose_name='Tipo de Documento', null=False, blank=False)
    atividade = models.ForeignKeyPlus('etep.Atividade', null=False, blank=False)

    objects = models.Manager()
    locals = managers.DocumentoManager()

    class Meta:
        verbose_name = 'Documento'
        verbose_name_plural = 'Documento'

    def __str__(self):
        return f'Documento #{self.pk} - {filename(self.arquivo)}'

    def can_change(self, user):
        return (
            in_group(user, 'Administrador Acadêmico, etep Administrador')
            or self.atividade.usuario.get_relacionamento().setor
            and self.atividade.usuario.get_relacionamento().setor.uo == user.get_relacionamento().setor.uo
        )
