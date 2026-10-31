from datetime import datetime

from django.core.exceptions import ValidationError

from comum.models import Sala, User, Vinculo, tl
from djtools.db import models
from djtools.db.models import ModelPlus, settings
from djtools.storages import get_overwrite_storage
from djtools.thumbs import ImageWithThumbsField
from djtools.utils import mask_cpf, send_notification, unused
from portaria.managers import AcessoManager
from rh.models import UnidadeOrganizacional


class ConfiguracaoSistemaPortaria(ModelPlus):
    campus = models.OneToOneField(UnidadeOrganizacional, null=False, blank=True, verbose_name='Campus', on_delete=models.CASCADE)

    cracha_obrigatorio = models.BooleanField('O uso do crachá é obrigatório?', default=False)
    habilitar_camera = models.BooleanField('Habilitar uso da câmera?', default=True)
    habilitar_geracao_chave_wifi = models.BooleanField('Habilitar a geração de chave WI-FI?', default=True)
    senha = models.CharFieldPlus('Senha do WI-FI', max_length=30, null=True, blank=False)

    url_wifi = models.URLField(
        'URL de integração com o Sistema de Wifi',
        null=False,
        blank=True,
        help_text='Caso esse campo permaneça vazio será utilizado a configuração padrão de integração wifi',
    )
    limite_compartilhamento_chave = models.IntegerField('Limite de compartilhamento da chave do WI-FI', default=1, null=False, blank=False)

    class Meta:
        verbose_name = 'Configuração de Portaria'
        verbose_name_plural = 'Configurações de Portaria'

    def __str__(self):
        return f'Configurações do campus: {self.campus.nome}'


@unused
class Visitante(ModelPlus):
    nome = models.CharField(max_length=255, verbose_name='Nome')
    cpf = models.CharField(max_length=20, null=True, blank=False, verbose_name='CPF')
    rg = models.CharField(max_length=20, null=False, blank=True, verbose_name='RG')
    sexo = models.CharField(max_length=1, choices=[['M', 'Masculino'], ['F', 'Feminino']])
    email = models.EmailField(blank=True, verbose_name='Email')

    data_cadastro = models.DateTimeFieldPlus(null=True, blank=True, verbose_name='Data do Cadastro')
    user_cadastro = models.ForeignKeyPlus(
        User, null=True, blank=True, verbose_name='Usuário do Cadastro', on_delete=models.CASCADE, related_name='user_cadastro'
    )
    data_ultima_alteracao = models.DateTimeFieldPlus(verbose_name='Data da Última Alteração', null=True, blank=True)
    user_ultima_alteracao = models.ForeignKeyPlus(
        User, null=True, blank=True, verbose_name='Usuário da Última Alteração', on_delete=models.CASCADE, related_name='user_ultima_alteracao'
    )

    foto = ImageWithThumbsField(
        storage=get_overwrite_storage(),
        use_id_for_name=True,
        upload_to='portaria_visitante_externo',
        sizes=((75, 100), (150, 200)),
        null=True,
        blank=True,
    )

    def __str__(self):
        return self.nome

    def get_rg(self):
        return self.rg or 'Não informado'

    def get_cpf(self):
        return self.cpf or 'Não informado'

    def get_identificador(self):
        return self.cpf or self.rg

    @property
    def get_nome_rg_cpf(self):
        return f'{self.nome} (RG: {self.get_rg()} CPF: {self.get_cpf()})'

    @property
    def get_rg_cpf(self):
        return f'RG: {self.get_rg()} / CPF: {self.get_cpf()}'

    def get_foto_75x100_url(self):
        if self.foto and self.foto.url_75x100:
            return self.foto.url_75x100
        else:
            return '/static/comum/img/default.jpg'

    def get_foto_150x200_url(self):
        if self.foto and self.foto.url_150x200:
            return self.foto.url_150x200
        else:
            return '/static/comum/img/default.jpg'

    def clean(self):
        super().clean()

        user = tl.get_user()

        # Cadastro
        if not self.id:
            self.user_cadastro = user
            self.data_cadastro = datetime.today()

        # Alteracao
        if self.id:
            self.user_ultima_alteracao = user
            self.data_ultima_alteracao = datetime.today()

        # Deve cadastrar CPF ou RG
        if not self.rg and not self.cpf:
            raise ValidationError('Impossível cadastrar pessoa externa sem CPF ou RG.')

        # Valida se já existe uma Pessoa com esse mesmo CPF
        if mask_cpf(self.cpf) and (
            Visitante.objects.filter(cpf=mask_cpf(self.cpf)).exclude(cpf__isnull=True).exclude(pk=self.id).exists()
            or Vinculo.objects.filter(pessoa__pessoafisica__cpf=mask_cpf(self.cpf), ativo=True)
            .exclude(pessoa__pessoafisica__cpf__isnull=True)
            .exists()
        ):
            raise ValidationError('Já existe uma pessoa cadastrada para esse CPF.')

        # Valida se já existe uma Visitante com esse mesmo EMAIL
        if self.email and Visitante.objects.filter(email=self.email).exclude(pk=self.id).exists():
            raise ValidationError('Já existe uma pessoa cadastrada para esse EMAIL.')

    @property
    def get_vinculo_institucional_title(self):
        return 'Externo'


class Acesso(ModelPlus):
    objetivo = models.CharField(max_length=255, verbose_name='Objetivo')
    cracha = models.CharField(max_length=5, verbose_name='Crachá', null=True, blank=True)

    local_acesso = models.ForeignKeyPlus(UnidadeOrganizacional, null=False, blank=False, verbose_name='Local de Acesso', on_delete=models.CASCADE)
    data_hora_entrada = models.DateTimeFieldPlus(null=True, blank=True, verbose_name='Data Hora de Entrada')
    data_hora_saida = models.DateTimeFieldPlus(verbose_name='Data Hora de Saída', null=True, blank=True)
    user_entrada = models.ForeignKeyPlus(
        User, null=True, verbose_name='Usuário Registro de Entrada', on_delete=models.CASCADE, related_name='user_entrada'
    )
    user_saida = models.ForeignKeyPlus(User, null=True, verbose_name='Usuário Registro de Saída', on_delete=models.CASCADE, related_name='user_saida')

    chave_wifi = models.CharField(max_length=255, verbose_name='Chave wi-fi', null=True)
    data_geracao_chave_wifi = models.DateTimeFieldPlus(verbose_name='Data Geração da Chave wi-fi', null=True)
    quantidade_dias_chave_wifi = models.PositiveIntegerFieldPlus(verbose_name='Quantidade de dias da Chave wi-fi', null=False, default=1)

    user_geracao_chave_wifi = models.ForeignKeyPlus(
        User, null=True, verbose_name='Usuário Geração da Chave wi-fi', on_delete=models.CASCADE, related_name='user_geracao_chave_wifi'
    )

    objects = AcessoManager()

    def __str__(self):
        return f'{self.data_hora_entrada}'

    def sub_instance(self):
        try:
            return AcessoInterno.objects.get(pk=self.pk)
        except Exception:
            pass

        try:
            return AcessoExterno.objects.get(pk=self.pk)
        except Exception:
            pass

        return None

    def clean(self):
        super().clean()

        # Cadastro
        if not self.id:
            self.data_hora_entrada = datetime.today()

    @property
    def senha(self):
        qs_config = ConfiguracaoSistemaPortaria.objects.filter(campus=self.local_acesso)
        if qs_config.exists():
            return qs_config.first().senha
        return None


class AcessoInterno(Acesso):
    vinculo = models.ForeignKeyPlus('comum.Vinculo', null=False, verbose_name='Vínculo')

    class Meta:
        verbose_name = 'Acesso Interno'
        verbose_name_plural = 'Acessos Internos'

    def __str__(self):
        return str(self.vinculo)

    @property
    def get_matricula(self):
        return self.vinculo.relacionamento.matricula


class AcessoExterno(Acesso):
    """Visitas/Acessos de Pessoas Externas"""

    pessoa_externa = models.ForeignKeyPlus(Visitante, null=True, verbose_name='Pessoa Externa', on_delete=models.CASCADE)
    vinculo_externo = models.ForeignKeyPlus(Vinculo, null=True, verbose_name='Visitante', on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Acesso Externo'
        verbose_name_plural = 'Acessos Externo'

    def __str__(self):
        return f'{self.vinculo_externo}'


class SolicitacaoEntrada(ModelPlus):
    """Solicitações de Entrada de Pessoas Com Vínculo"""

    data = models.DateField()
    data_saida = models.DateField(null=True)
    hora_entrada = models.TimeFieldPlus('Hora da Entrada')
    hora_saida = models.TimeFieldPlus('Hora da Saída')
    sala = models.ForeignKeyPlus(Sala, verbose_name='Sala')
    atividade = models.CharField('Atividade a ser realizada', max_length=255)
    solicitantes = models.ManyToManyField(Vinculo, verbose_name='Solicitantes')
    deferida = models.BooleanField(null=True)
    cancelada = models.BooleanField(default=False)
    data_cadastro = models.DateTimeField('Data de Cadastro', auto_now_add=True)
    usuario_cadastro = models.CurrentUserField(verbose_name='Usuário de Cadastro')

    class Meta:
        verbose_name = 'Solicitação de Entrada'
        verbose_name_plural = 'Solicitações de Entrada'
        permissions = (('pode_avaliar_solicitacoes_entrada', 'Pode avaliar Solicitações de Entrada'),)

    def __str__(self):
        return 'Solicitação para {}'.format(self.data.strftime('%d/%m/%Y'))

    def get_absolute_url(self):
        return f'/portaria/solicitacao_entrada/{self.pk}/'

    def save(self, *args, **kwargs):
        eh_cadastro = False
        if not self.pk:
            eh_cadastro = True

        super().save(*args, **kwargs)

        if eh_cadastro:
            titulo = '[SUAP] Solicitação de Entrada'
            texto = []
            texto.append('<h1>Solicitação de Entrada</h1>')
            texto.append('<dl>')
            texto.append(f'<dt>Data:</dt><dd>{self.data}</dd>')
            texto.append(f'<dt>Hora da Entrada:</dt><dd>{self.hora_entrada}</dd>')
            texto.append(f'<dt>Hora da Saída:</dt><dd>{self.hora_saida}</dd>')
            texto.append(f'<dt>Sala:</dt><dd>{self.sala}</dd>')
            texto.append(f'<dt>Atividade a ser realizada:</dt><dd>{self.atividade}</dd>')
            texto.append(f'<dt>Solicitante(s):</dt><dd>{self.get_solicitantes()}</dd>')
            texto.append('</dl>')
            texto.append(
                '<p class="more-info">Para mais informações, acesse: <a href="{0}{1}">{0}{1}</a></p>'.format(
                    settings.SITE_URL, self.get_absolute_url()
                )
            )

            for solicitante in self.solicitantes.all():
                for chefe in solicitante.relacionamento.chefes_imediatos():
                    if chefe:
                        send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, [chefe.get_vinculo()])

    def get_solicitantes(self):
        nomes_solicitantes = []
        for solicitante in self.solicitantes.all():
            nomes_solicitantes.append(str(solicitante))
        return ', '.join(nomes_solicitantes)

    def eh_solicitante(self, vinculo):
        return self.solicitantes.filter(pk=vinculo.pk).exists()

    def pode_editar(self):
        return not (self.cancelada or self.deferida is not None)
