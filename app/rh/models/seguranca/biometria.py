import datetime
import random

from django.apps.registry import apps
from django.conf import settings

from djtools.db import models
from djtools.utils import get_datetime_now, send_mail


class Biometria(models.ModelPlus):
    TIPO_DIGITAL = 'Digital'
    TIPO_FACIAL = 'Facial'
    TIPO_CHOICES = (
        (TIPO_DIGITAL, TIPO_DIGITAL),
        (TIPO_FACIAL, TIPO_FACIAL),
    )

    tipo = models.CharField(max_length=15, choices=TIPO_CHOICES, default=TIPO_DIGITAL)
    pessoa_fisica = models.ForeignKeyPlus(
        'rh.PessoaFisica',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='biometrias',
        verbose_name='Biometria',
    )
    terminal_novo = models.BooleanField('Importada do novo terminal', default=False)
    template = models.BinaryField(null=True, blank=True, editable=False)
    data_cadastro = models.DateFieldPlus(auto_now_add=True)

    class Meta:
        verbose_name = 'Biometria'
        verbose_name_plural = 'Biometrias'

    def __str__(self):
        return f'[{self.tipo}] {self.pessoa_fisica}'


class BiometriaSolicitacao(models.ModelPlus):
    pessoa_fisica = models.ForeignKeyPlus(
        'rh.PessoaFisica',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='solicitacoes_biometria',
        verbose_name='Solicitação Biometria',
    )
    codigo_verificacao = models.CharField('Código de Verificação', max_length=10, null=False)
    cancelada = models.BooleanField('Cancelada', default=False)
    utilizado = models.BooleanField('Utilizado', default=False)
    data_uso = models.DateTimeFieldPlus('Data do Uso', null=True)
    data_cadastro = models.DateTimeFieldPlus(auto_now_add=True)

    class Meta:
        verbose_name = 'Solicitação - Biometria'
        verbose_name_plural = 'Solicitações - Biometria'

    def __str__(self):
        return f'{self.pessoa_fisica}'

    def save(self, *args, **kwargs):
        if self.pk is None:
            self.codigo_verificacao = self.gerar_codigo()
        super().save(*args, **kwargs)

    @property
    def data_expiracao(self):
        Configuracao = apps.get_model('comum', 'configuracao')
        expiracao = Configuracao.get_valor_por_chave(app='comum', chave='biometria_expiracao')
        data_base = self.data_cadastro + datetime.timedelta(days=int(expiracao))
        return data_base

    @property
    def expirado(self):
        return self.cancelada or self.data_expiracao < get_datetime_now()

    @property
    def ativo(self):
        return not (self.expirado or self.utilizado)

    def gerar_codigo(self):
        numeros = []
        for _ in range(6):
            numeros.append(str(random.randint(0, 9)))

        codigo = ''.join(numeros)

        if codigo == '999999':
            return self.gerar_codigo()

        return codigo

    def verificar_codigo(self, codigo):
        if self.expirado:
            return False
        return self.codigo_verificacao == codigo

    def enviar_email(self, email: str | None = None) -> bool:
        """Envia o código de verificação para o email informado.

        Args:
            email: Endereço de destino (resolvido pelo caller via vínculo do dono da biometria).
                   Se None ou vazio, o envio é suprimido.

        Returns:
            True se o email foi enviado, False caso contrário.
        """
        if not email:
            return False
        assunto = 'Solicitação de autocadastro'
        conteudo = f"""
            Caro(a) usuário, você solicitou o autocadastro de biometria, agora, você deve realizá-lo em um terminal de ponto.

            Utilize o código {self.codigo_verificacao} quando solicitado.
        """
        if self.ativo:
            send_mail(assunto, conteudo, settings.DEFAULT_FROM_EMAIL, [email], fail_silently=True)
            return True
        return False
