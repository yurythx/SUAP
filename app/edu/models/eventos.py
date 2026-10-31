import datetime
import hashlib

from django.conf import settings
from django.db import transaction
from djtools.db import models
from edu.managers import FiltroDiretoriaManager, FiltroUnidadeOrganizacionalManager
from edu.models.cadastros_gerais import PERIODO_LETIVO_CHOICES, SituacaoMatricula
from edu.models.logs import LogModel


class ColacaoGrau(LogModel):
    diretoria = models.ForeignKeyPlus('edu.Diretoria', on_delete=models.CASCADE)
    descricao = models.CharFieldPlus('Descrição', width=255)
    ano_letivo = models.ForeignKeyPlus('comum.Ano', verbose_name='Ano Letivo', on_delete=models.CASCADE)
    periodo_letivo = models.PositiveIntegerField(verbose_name='Período Letivo', choices=PERIODO_LETIVO_CHOICES)
    data_colacao = models.DateFieldPlus(verbose_name='Data de Colação')
    deferida = models.BooleanField(verbose_name='Deferida', default=False)

    objects = models.Manager()
    locals = FiltroDiretoriaManager('diretoria')

    class Meta:
        verbose_name = 'Colação de Grau'
        verbose_name_plural = 'Colações de Grau'

    def get_absolute_url(self):
        return f'/edu/colacao_grau/{self.pk:d}/'

    def __str__(self):
        return self.descricao

    def save(self, *args, **kwargs):
        acao = kwargs.pop('acao', None)
        super().save(*args, **kwargs)
        if self.pk:
            for participacao in self.participacaocolacaograu_set.all():
                if acao == 'cancelar':
                    participacao.aluno.situacao_id = SituacaoMatricula.MATRICULADO
                participacao.aluno.atualizar_situacao('Atualização de Colação de Grau')

    def delete(self, *args, **kwargs):
        for participacao in self.participacaocolacaograu_set.all():
            participacao.aluno.atualizar_situacao('Atualização de Colação de Grau')
        super().delete(*args, **kwargs)

    @transaction.atomic
    def cancelar_deferimento(self):
        self.deferida = False
        self.save(acao='cancelar')

    @transaction.atomic
    def deferir(self, laureados=None):
        if laureados is None:
            laureados = []
        self.deferida = True
        self.participacaocolacaograu_set.update(laureado=False)
        for participacao in laureados:
            participacao.laureado = True
            participacao.save()
        self.save()


class ParticipacaoColacaoGrau(LogModel):
    SEARCH_FIELDS = ['aluno__matricula', 'aluno__pessoa_fisica__nome']

    colacao_grau = models.ForeignKeyPlus('edu.ColacaoGrau', verbose_name='Colação de Grau', null=False)
    aluno = models.ForeignKeyPlus('edu.Aluno', null=False)
    laureado = models.BooleanField(verbose_name='Laureado', default=False)

    class Meta:
        verbose_name = 'Participação na Colação de Grau'
        verbose_name_plural = 'Participação nas Colações de Grau'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.aluno.data_colacao_grau = self.colacao_grau.data_colacao
        self.aluno.atualizar_situacao('Partitipação em Colação de Grau')

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        self.aluno.atualizar_situacao('Exclusão da Participação em Colação de Grau')

    def __str__(self):
        return str(self.aluno)


class Evento(LogModel):
    TIPO_EVENTO_EVENTO = 1
    TIPO_EVENTO_PALESTRA = 2
    TIPO_EVENTO_CHOICES = ((TIPO_EVENTO_EVENTO, 'Evento'), (TIPO_EVENTO_PALESTRA, 'Palestra'))
    titulo = models.CharFieldPlus('Título', null=False, blank=False, default='')
    descricao = models.TextField('Descrição', null=False, blank=False)
    tipo = models.PositiveIntegerField('Tipo do Evento', null=False, choices=TIPO_EVENTO_CHOICES)
    uo = models.ForeignKeyPlus('rh.UnidadeOrganizacional', verbose_name='Campus', on_delete=models.CASCADE)
    data = models.DateFieldPlus('Data de Realização')
    modelo_certificado_participacao = models.FileFieldPlus(
        upload_to='edu/modelo_certificado_participacao_evento/',
        null=True,
        blank=True,
        verbose_name='Modelo do Certificado de Participação',
        help_text='O arquivo de modelo deve ser uma arquivo .docx contendo as marcações #PARTICIPANTE#, #CPF#, #CAMPUS#, #CIDADE#, #UF#, #DATA#, #CODIGOVERIFICADOR#.',
    )

    modelo_certificado_palestrante = models.FileFieldPlus(
        upload_to='edu/modelo_certificado_palestrante_evento/',
        null=True,
        blank=True,
        verbose_name='Modelo do Certificado de Palestrante',
        help_text='O arquivo de modelo deve ser uma arquivo .docx contendo as marcações #PARTICIPANTE#, #CPF#, #CAMPUS#, #CIDADE#, #UF#, #DATA#, #CODIGOVERIFICADOR#.',
    )

    modelo_certificado_convidado = models.FileFieldPlus(
        upload_to='edu/modelo_certificado_convidado_evento/',
        null=True,
        blank=True,
        verbose_name='Modelo do Certificado de Convidado',
        help_text='O arquivo de modelo deve ser uma arquivo .docx contendo as marcações #PARTICIPANTE#, #CPF#, #CAMPUS#, #CIDADE#, #UF#, #DATA#, #CODIGOVERIFICADOR#.',
    )

    participantes_vinculos = models.ManyToManyField(
        'comum.Vinculo', through='edu.ParticipanteEvento', related_name='participantes_vinculos_set', blank=True
    )

    objects = models.Manager()
    locals = FiltroUnidadeOrganizacionalManager('uo')

    class Meta:
        verbose_name = 'Palestra/Evento'
        verbose_name_plural = 'Palestras/Eventos'

    def get_absolute_url(self):
        return f'/edu/evento/{self.pk:d}/'

    def __str__(self):
        return f'{self.get_tipo()}: {self.titulo}'

    def get_tipo(self):
        if self.tipo == Evento.TIPO_EVENTO_EVENTO:
            return 'Evento'
        elif self.tipo == Evento.TIPO_EVENTO_PALESTRA:
            return 'Palestra'

    def get_participantes(self):
        return self.participanteevento_set.exclude(tipo_participacao=ParticipanteEvento.PALESTRANTE).exclude(
            tipo_participacao=ParticipanteEvento.CONVIDADO
        )

    def get_palestrantes(self):
        return self.participanteevento_set.filter(tipo_participacao=ParticipanteEvento.PALESTRANTE)

    def get_convidados(self):
        return self.participanteevento_set.filter(tipo_participacao=ParticipanteEvento.CONVIDADO)


class ParticipanteEvento(LogModel):
    PARTICIPANTE = 'Participante'
    PALESTRANTE = 'Palestrante'
    CONVIDADO = 'Convidado'

    participante = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Participante', on_delete=models.CASCADE)
    evento = models.ForeignKeyPlus('edu.Evento', verbose_name='Evento', on_delete=models.CASCADE)
    token = models.CharFieldPlus(max_length=16, null=True)
    tipo_participacao = models.CharFieldPlus(verbose_name='Tipo de Participante', null=True, blank=True, default=PARTICIPANTE)

    def __str__(self):
        return f'{self.participante} - {self.evento}'

    class Meta:
        verbose_name = 'Vínculo de Participante em Evento'
        verbose_name_plural = 'Vínculos de Participante em Evento'

    def save(self, *args, **kwargs):
        self.token = hashlib.sha1(
            f'{self.evento.pk}{self.participante.pessoa.pessoafisica.cpf}{datetime.datetime.now()}{settings.SECRET_KEY}'.encode()
        ).hexdigest()[0:16]
        super().save(*args, **kwargs)

    def get_tipo_pessoa(self):
        if self.participante.eh_servidor():
            return 'Servidor'
        elif self.participante.eh_aluno():
            return 'Aluno'
        elif self.participante.eh_prestador():
            return 'Prestador de Serviço'
        else:
            return '-'
