from django.conf import settings
from django.contrib.auth.models import Group
from django.core.validators import FileExtensionValidator
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver

from comum.models import User
from comum.utils import get_uo
from djtools.db import models
from edu.decorators import registra_atualizado_por
from edu.models import Aluno
from edu.models.logs import LogModel


class ApoioEspecializado(models.ModelPlus):
    nome = models.CharFieldPlus('Nome', max_length=255)
    ocupacoes = models.ManyToManyFieldPlus('comum.Ocupacao', verbose_name='Ocupações vinculadas', blank=True)
    faz_entrevista = models.BooleanField('Faz entrevista?', default=False)
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Apoio especializado'
        verbose_name_plural = 'Apoios especializados'
        ordering = ['nome']

    def __str__(self):
        ocupacoes_list = list(self.ocupacoes.values_list('descricao', flat=True))
        if ocupacoes_list:
            return f'{self.nome} ({", ".join(ocupacoes_list)})'
        return self.nome


class SugestaoRecurso(models.ModelPlus):
    nome = models.CharFieldPlus('Nome do Recurso', max_length=255)
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Sugestão de Recurso'
        verbose_name_plural = 'Sugestões de Recursos'
        ordering = ['nome']


@registra_atualizado_por
class Acolhimento(LogModel):
    aluno = models.ForeignKeyPlus('edu.Aluno', verbose_name='Aluno', on_delete=models.CASCADE)
    data_acolhimento = models.DateFieldPlus('Data do Acolhimento')
    relatorio = models.TextField('Relatório de Acolhimento')
    cadastrado_em = models.DateTimeFieldPlus('Cadastrado em', auto_now_add=True)
    cadastrado_por = models.CurrentUserField(verbose_name='Cadastrado por', related_name='acolhimento_cadastrado_por')
    ultima_atualizacao_por = models.ForeignKeyPlus(
        User, verbose_name='Última atualização por', null=True, blank=True, related_name='acolhimento_ultima_atualizacao_por'
    )
    ultima_atualizacao_em = models.DateTimeFieldPlus(verbose_name='Última atualização em', null=True, blank=True)

    class Meta:
        verbose_name = 'Acolhimento'
        verbose_name_plural = 'Acolhimentos'
        ordering = ['-data_acolhimento']

    @classmethod
    def get_alunos_sem_acolhimento(cls, uo):
        """
        Retorna os alunos do campus que não possuem acolhimento.
        """
        acolhidos_ids = cls.objects.filter(aluno__curso_campus__diretoria__setor__uo=uo).values_list('aluno_id', flat=True)
        alunos_campus = Aluno.ativos.filter(
            (Q(deficiencias__isnull=False) | Q(outras_nees__isnull=False)),
            curso_campus__diretoria__setor__uo=uo,
        )
        return alunos_campus.exclude(id__in=acolhidos_ids).distinct()

    @staticmethod
    def get_uo_if_grupo_restrito(user):
        eh_coordenador_sistemico_napne = user.has_group_cached('Coordenador sistêmico do Napne')
        eh_membro_etep = user.has_group_cached('Membro ETEP', ignore_groups_if_superuser=False)
        eh_coordenador_napne = user.has_group_cached('Coordenador do Napne', ignore_groups_if_superuser=False)
        if not eh_coordenador_sistemico_napne and (eh_membro_etep or eh_coordenador_napne):
            return get_uo(user)
        return None

    def get_detalhes_aluno(self):
        data = []
        pf = self.aluno.pessoa_fisica
        if hasattr(pf, 'get_sexo_display') and pf.sexo:
            data.append(('Sexo', pf.get_sexo_display()))
        if hasattr(pf, 'get_genero_display') and pf.genero:
            data.append(('Gênero', pf.get_genero_display()))
        if self.aluno.raca:
            data.append(('Raça', self.aluno.raca.descricao))
        if getattr(self.aluno, 'curso_campus', None) and getattr(self.aluno.curso_campus, 'descricao', None):
            data.append(('Curso', self.aluno.curso_campus.descricao))
        return data

    def get_nees_aluno(self):
        if self.aluno.possui_nee():
            html = ''
            for deficiencia in self.aluno.deficiencias.all():
                html += f'<dt>Deficiência:</dt><dd>{deficiencia.nome}</dd>'
            if self.aluno.outras_nees.exists():
                nees = ', '.join([nee.nome for nee in self.aluno.outras_nees.all()])
                html += f'<dt>Outras necessidades especiais:</dt><dd>{nees}</dd>'
            if html:
                html = f'<dl>{html}</dl>'
        else:
            html = '-'
        return html


@registra_atualizado_por
class AcolhimentoAnexo(models.ModelPlus):
    acolhimento = models.ForeignKeyPlus('Acolhimento', on_delete=models.CASCADE, verbose_name='Acolhimento')
    cadastrado_em = models.DateTimeFieldPlus('Cadastrado em', auto_now_add=True)
    cadastrado_por = models.CurrentUserField(verbose_name='Cadastrado por', related_name='acolhimento_anexo_cadastrado_por')
    descricao = models.CharFieldPlus('Descrição', max_length=255, blank=True, null=True)
    arquivo = models.PrivateFileField(
        verbose_name='Arquivo',
        upload_to='napne/acolhimentos/anexos/',
        help_text='O formato do arquivo deve ser ".pdf"',
        null=True,
        blank=True,
        max_length=500,
        validators=[
            FileExtensionValidator(
                allowed_extensions=[
                    'pdf',
                ]
            )
        ],
    )
    if 'documento_eletronico' in settings.INSTALLED_APPS:
        documento_digital = models.ForeignKeyPlus('documento_eletronico.DocumentoTexto', verbose_name='Documento Digital', null=True, blank=True)

    class Meta:
        verbose_name = 'Anexo do Acolhimento'
        verbose_name_plural = 'Anexos dos Acolhimentos'

    def __str__(self):
        parts = []
        if self.descricao:
            parts.append(self.descricao)
        if self.arquivo:
            parts.append(f'Arquivo: {self.arquivo.name}')
        if 'documento_eletronico' in settings.INSTALLED_APPS and hasattr(self, 'documento_digital') and self.documento_digital:
            parts.append(f'Documento: {self.documento_digital}')
        return ' | '.join(parts) if parts else f'Anexo do Acolhimento #{self.pk}'


@registra_atualizado_por
class Entrevista(LogModel):
    PRECISA_APOIO = '1'
    NAO_PRECISA_APOIO = '2'
    SOLICITOU_DISPENSA = '3'

    PARECER_CHOICES = [
        (PRECISA_APOIO, 'Precisa de apoio especializado'),
        (NAO_PRECISA_APOIO, 'Não precisa de apoio especializado'),
        (SOLICITOU_DISPENSA, 'Solicitou dispensa de apoio especializado'),
    ]

    acolhimento = models.ForeignKeyPlus('Acolhimento', on_delete=models.CASCADE, verbose_name='Acolhimento')
    data_entrevista = models.DateFieldPlus('Data da Entrevista')
    anamnese = models.TextField('Anamnese')
    parecer = models.CharFieldPlus('Parecer', max_length=2, choices=PARECER_CHOICES)
    cadastrado_em = models.DateTimeFieldPlus('Cadastrado em', auto_now_add=True)
    cadastrado_por = models.CurrentUserField(verbose_name='Cadastrado por', related_name='entrevista_cadastrado_por')
    ultima_atualizacao_por = models.ForeignKeyPlus(
        User, verbose_name='Última atualização por', null=True, blank=True, related_name='entrevista_ultima_atualizacao_por'
    )
    ultima_atualizacao_em = models.DateTimeFieldPlus(verbose_name='Última atualização em', null=True, blank=True)
    sugestoes_recursos = models.ManyToManyFieldPlus('SugestaoRecurso', verbose_name='Sugestões de recursos', blank=True, related_name='entrevistas')

    class Meta:
        verbose_name = 'Entrevista'
        verbose_name_plural = 'Entrevistas'
        ordering = ['-data_entrevista']
        permissions = (('view_parecer_entrevista', 'Pode ver parecer da entrevista'),)


class ProfissionalApoioEspecializado(models.ModelPlus):
    ATIVO = '1'
    FINALIZADO = '2'

    SITUACAO_CHOICES = [
        (ATIVO, 'Ativo'),
        (FINALIZADO, 'Finalizado'),
    ]

    acolhimento = models.ForeignKeyPlus('Acolhimento', on_delete=models.CASCADE, verbose_name='Acolhimento')
    apoio_especializado = models.ForeignKeyPlus('ApoioEspecializado', on_delete=models.CASCADE, verbose_name='Apoio especializado')
    profissional = models.ForeignKeyPlus('comum.PrestadorServico', on_delete=models.CASCADE, verbose_name='Profissional')
    situacao = models.CharFieldPlus('Situação', max_length=2, choices=SITUACAO_CHOICES, default=ATIVO)

    class Meta:
        verbose_name = 'Profissional de Apoio Especializado'
        verbose_name_plural = 'Profissionais de Apoio Especializado'


@receiver(post_save, sender=ProfissionalApoioEspecializado, dispatch_uid='adiciona_grupo_apoio_especializado_napne')
def adiciona_grupo_apoio_especializado_napne(sender, instance, **kwargs):
    group, _ = Group.objects.get_or_create(name='Apoio especializado do Napne')
    user = instance.profissional.get_user()
    if user:
        user.groups.add(group)


class Acompanhamento(LogModel):
    acolhimento = models.ForeignKeyPlus('Acolhimento', on_delete=models.CASCADE, verbose_name='Acolhimento', related_name='acompanhamentos')
    profissional_apoio_especializado = models.ForeignKeyPlus(
        'ProfissionalApoioEspecializado',
        on_delete=models.CASCADE,
        verbose_name='Apoio do Acolhimento',
        null=True,
        blank=True,
        related_name='acompanhamentos',
    )
    descricao = models.TextField('Descrição')
    cadastrado_em = models.DateTimeFieldPlus('Cadastrado em', auto_now_add=True)
    cadastrado_por = models.CurrentUserField(verbose_name='Cadastrado por', related_name='acompanhamento_cadastrado_por')

    class Meta:
        verbose_name = 'Acompanhamento'
        verbose_name_plural = 'Acompanhamentos'
        ordering = ['acolhimento', '-cadastrado_em']
