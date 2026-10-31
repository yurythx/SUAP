from django.conf import settings
from django.core.files.base import ContentFile
from django.db.models import QuerySet

from djtools.db import models
from djtools.utils import get_datetime_now, send_notification

from ..carreira import Servidor


class SolicitacaoAlteracaoFoto(models.ModelPlus):
    SEARCH_FIELDS = [
        'solicitante__pessoa_fisica__nome',
    ]

    AGUARDANDO_VALIDACAO = 1
    VALIDADA = 2
    REJEITADA = 3
    SITUCAO_CHOICES = [[AGUARDANDO_VALIDACAO, 'Aguardando validação'], [VALIDADA, 'Validada'], [REJEITADA, 'Rejeitada']]
    foto = models.FileFieldPlus(
        'Foto',
        upload_to='fotos',
        null=False,
        blank=False,
        check_mimetype=False,
        filetypes=['png', 'jpg', 'jpeg'],
        max_file_size=5242880,
    )
    foto_antiga = models.FileFieldPlus(
        'Foto Antiga',
        upload_to='fotos',
        null=True,
        blank=True,
        check_mimetype=False,
        filetypes=['png', 'jpg', 'jpeg'],
        max_file_size=5242880,
    )
    descricao = models.TextField('Descrição', null=True, blank=True, help_text='Se necessário, descreva o motivo da alteração da foto.')
    solicitante = models.ForeignKey('rh.Servidor', verbose_name='Solicitante', on_delete=models.SET_NULL, null=True, blank=False)
    situacao = models.IntegerFieldPlus('Situação', choices=SITUCAO_CHOICES, null=False, blank=False, default=AGUARDANDO_VALIDACAO)
    data_interacao = models.DateTimeFieldPlus('Data da Interação', null=True, blank=True)
    responsavel_interacao = models.ForeignKey(
        'rh.Servidor',
        verbose_name='Responsável pela Interação',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='responsavel_interacao',
    )
    motivo_rejeicao = models.TextField('Motivo da Rejeição', null=True, blank=True)

    class Meta:
        verbose_name = 'Solicitação de Alteração de Foto'
        verbose_name_plural = 'Solicitações de Alteração de Foto'

    def get_absolute_url(self):
        return f'/rh/detalhe_solicitacao_alteracao_foto/{self.pk}/'

    def validar(self, responsavel_usuario):
        self.situacao = self.VALIDADA
        self.data_interacao = get_datetime_now()
        self.responsavel_interacao = responsavel_usuario.get_relacionamento()
        qs = Servidor.objects.filter(matricula=self.solicitante.matricula)
        if qs.exists():
            servidor_solicitante = qs[0]

            # pode acontecer do servidor não ter uma foto anterior, nesses casos devemos ignorar a exceção
            try:
                # salvando foto antiga para consulta
                self.foto_antiga.save(f'antiga-{servidor_solicitante.matricula}.jpg', ContentFile(servidor_solicitante.foto.read()))
            except Exception:
                pass
            self.save()

            servidor_solicitante.foto.save(f'{servidor_solicitante.matricula}.jpg', ContentFile(self.foto.read()))
            servidor_solicitante.save()

        else:
            raise Servidor.DoesNotExist('Não foi possível encontrar o solicitante.')

    def rejeitar(self, request):
        self.situacao = self.REJEITADA
        self.motivo_rejeicao = request.POST.get('motivo_rejeicao')
        self.data_interacao = get_datetime_now()
        self.responsavel_interacao = request.user.get_relacionamento()
        self.save()

        # enviando notificação
        titulo = '[SUAP] Solicitação de Alteração de Foto'
        texto = []
        texto.append('<h1>Rejeição de Alteração de Foto</h1>')
        texto.append('<p>Sua solicitação de alteração de foto foi rejeitada.</p>')
        texto.append(f'<p>Motivo: {self.motivo_rejeicao}</p>')
        texto.append(
            '<p class="more-info">Para mais informações, acesse: <a href="/admin/rh/solicitacaoalteracaofoto/">Solicitação de Alteração de Foto</a></p>'
        )
        send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, [self.solicitante.get_vinculo()])

    @staticmethod
    def get_solicitacoes_pendentes(user) -> QuerySet[SolicitacaoAlteracaoFoto]:
        if user.eh_servidor:
            return SolicitacaoAlteracaoFoto.objects.filter(
                situacao=SolicitacaoAlteracaoFoto.AGUARDANDO_VALIDACAO, solicitante=user.get_relacionamento()
            )
        return SolicitacaoAlteracaoFoto.objects.none()

    @staticmethod
    def visiveis(user) -> QuerySet[SolicitacaoAlteracaoFoto]:
        """RH sistêmico vê todas; RH do campus, as do seu campus; os demais servidores, só as próprias."""
        if user.has_perm('rh.eh_rh_sistemico'):
            return SolicitacaoAlteracaoFoto.objects.all()
        relacionamento = user.get_relacionamento()
        if user.has_perm('rh.eh_rh_campus'):
            return SolicitacaoAlteracaoFoto.objects.filter(solicitante__setor__uo=relacionamento.setor.uo)
        if user.eh_servidor:
            return SolicitacaoAlteracaoFoto.objects.filter(solicitante=relacionamento)
        return SolicitacaoAlteracaoFoto.objects.none()

    @staticmethod
    def pode_analisar(user) -> bool:
        """Tem papel de quem analisa (RH sistêmico ou do campus).

        Não olha a solicitação: o campus é garantido por ``visiveis``, de onde as views buscam a
        solicitação (fora do escopo dá 404). Combine sempre os dois.
        """
        return user.has_perm('rh.eh_rh_sistemico') or user.has_perm('rh.eh_rh_campus')

    @staticmethod
    def pode_solicitar_alteracao_foto(user):
        return user.is_superuser or user.eh_servidor

    def get_foto_antiga(self):
        if self.situacao == SolicitacaoAlteracaoFoto.VALIDADA:
            if self.foto_antiga.url:
                return self.foto_antiga.url
            else:
                return '/static/comum/img/default.jpg'
        return self.solicitante.get_foto_150x200_url()
