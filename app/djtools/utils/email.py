"""
Django, our web development framework of choice provides many useful functions,
send_mail() being one of them which we frequently use.

Though convenient, send_mail() in Django is a synchronous operation - meaning
Django will wait for the mail sending process to finish before continuing other tasks.
This is not usually that big of a deal if the mail server Django is configured to use is
located in the same site (and has low latency), but in cases where the mail server is not
located in the same cloud, this could give the impression that your website is slow,
especially in sites with relatively slow internet connectivity (like Indonesia).

Consider a really common scenario where an application automatically sends an email
verification message to a newly registered user. If configured to use a third party SMTP
server like Gmail, the email sending process takes close to half a second if our app is
located in Jakarta. This means that we are adding close a half a second of latency before
rendering a response to the user, making our app look sluggish (in reality the user
creation process itself takes less than 50ms).

So one of our engineers Gilang wrote a simple wrapper around Django's send_mail() to
perform the task asynchronously using Python's threading.

http://ui.co.id/blog/asynchronous-send_mail-in-django
"""

import hashlib
import threading

from django.conf import settings
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from django.core.mail import send_mail as django_send_mail

from djtools.utils.test import running_tests

__all__ = ['EmailThread', 'html_email_template', 'send_mail', 'send_notification']


class EmailThread(threading.Thread):
    """
    Classe que faz o envio de e-mail de forma assincrona. Ela foi baseada em:
    http://ui.co.id/blog/asynchronous-send_mail-in-django
    """

    def __init__(self, subject, body, from_email, recipient_list, fail_silently, html, attachments=None, files=None, bcc=None):
        """
        Construtor.

        Args:
            subject (string): assunto do e-mail;
            body (string): corpo d0 e-mail;
            from_email (string): e-mail do remetente;
            recipient_list (list): lista com os destinatários;
            fail_silently (bool): indica se é para silenciar erros;
            html (bool): indica que o e-mail é um **HTML**.
            attachments (list of tuples(name, content, mimetype)): lista de anexos
            files: (list of strings): paths of files to be attached
            bcc: (list of string): e-mail para destinatários com cópia de carbono
        """
        if bcc is None:
            bcc = []
        if files is None:
            files = []
        if attachments is None:
            attachments = []
        self.subject = subject
        self.body = body
        self.recipient_list = recipient_list
        self.from_email = from_email
        self.fail_silently = fail_silently
        self.html = html
        self.attachments = attachments
        self.files = files
        self.bcc = bcc
        threading.Thread.__init__(self)

    def run(self):
        """
        Método de execução por parte do Thread.
        """
        to = self.recipient_list
        if isinstance(to, str):
            to = (to,)
        msg = EmailMultiAlternatives(self.subject, self.body, self.from_email, to)
        if self.html:
            msg.attach_alternative(self.body, 'text/html')
        for name, content, mimetype in self.attachments:
            msg.attach(name, content, mimetype)
        for file_path in self.files:
            msg.attach_file(file_path)
        if self.bcc:
            msg.bcc = self.bcc
        try:
            msg.send(self.fail_silently)
        except Exception as e:
            if not self.fail_silently:
                raise e


def send_notification(
    assunto,
    mensagem,
    de,
    vinculos,
    fail_silently=True,
    html=None,
    categoria=None,
    salvar_no_banco=True,
    data_permite_marcar_lida=None,
    data_permite_excluir=None,
    so_notificar=False,
    objeto=None,
    task=None,
):
    """
    Envia uma mensagem para o sistema de notificação.

    Args:
        assunto (string): assunto da notificação;
        mensagem (string): corpo da mensagem da notificação;
        de (string): e-mail do remetente;
        vinculos (list): lista contendo os vínculos dos usuários que receberam a notificação;
        fail_silently (bool): indica que os erros devem ser silenciados;
        html (string): corpo do e-mail no formato *HTML*.
        categoria (string): categoria vinculada a notificação.
        salvar_no_banco (bool): indica se o texto da mensagem será salvo no banco de dados do SUAP

    Note:
        Caso o usuário indique que tem preferência pelo recebimento das notificações por e-mail, um e-mail será enviado.
    """
    from djtools.models import PushSubscription
    from djtools.tasks import enviar_push_notifications
    from comum.models import CategoriaNotificacao, NotificacaoSistema, PreferenciaNotificacao, RegistroNotificacao

    if not categoria:
        if assunto.startswith('[SUAP] '):
            categoria = assunto[7:]
        else:
            categoria = assunto

    # Verifica se a categoria existe
    categoria_notificacao = CategoriaNotificacao.objects.filter(assunto=categoria).first()
    if categoria_notificacao:
        categoria_notificacao.ativa = True
        categoria_notificacao.save()
    else:
        categoria_notificacao = CategoriaNotificacao.objects.create(assunto=categoria)

    notificacao = None
    objeto_relacionado_str = None
    if objeto:
        str_obj = f'{objeto._meta.verbose_name} #{objeto.pk}' if hasattr(objeto, '_meta') else str(objeto)
        if len(str_obj) > 250:
            str_obj = str_obj[: 250 - 3] + '...'
        objeto_relacionado_str = str_obj

    if task:
        vinculos = task.iterate(vinculos)

    for vinculo in vinculos:
        # Verifica a preferencia do Usuario
        if not vinculo:
            continue

        cache_key = None
        if getattr(vinculo, 'pk', None) and getattr(categoria_notificacao, 'pk', None):
            cache_payload = f'{vinculo.pk}:{categoria_notificacao.pk}:{mensagem}'
            if objeto_relacionado_str is not None:
                cache_payload = f'{cache_payload}:{objeto_relacionado_str}'
            cache_key = f'send_notification:{hashlib.sha1(cache_payload.encode("utf-8")).hexdigest()}'
            # Não usar cache durante os testes rápidos para evitar inconsistências
            if not running_tests() and cache.get(cache_key):
                continue

        preferencia = PreferenciaNotificacao.objects.filter(vinculo=vinculo, categoria=categoria_notificacao).first()
        if not preferencia:
            if vinculo.user:
                from comum.models import Preferencia

                preferencia_usuario = Preferencia.objects.get_or_create(usuario=vinculo.user)[0]
                preferencia = PreferenciaNotificacao.objects.create(
                    vinculo=vinculo, categoria=categoria_notificacao, via_suap=preferencia_usuario.via_suap, via_email=preferencia_usuario.via_email
                )

        if preferencia:
            if salvar_no_banco:
                if notificacao is None:
                    notificacao_kwargs = {
                        'categoria': categoria_notificacao,
                        'mensagem': mensagem,
                    }
                    if objeto_relacionado_str is not None:
                        notificacao_kwargs['objeto_relacionado'] = objeto_relacionado_str
                    notificacao = NotificacaoSistema.objects.create(**notificacao_kwargs)

                # Registra a notificacao no SUAP
                rn = RegistroNotificacao.objects.create(notificacao=notificacao, vinculo=vinculo)
                if data_permite_marcar_lida:
                    rn.data_permite_marcar_lida = data_permite_marcar_lida
                if data_permite_excluir:
                    rn.data_permite_excluir = data_permite_excluir
                # O objetivo disso seria marcar como lidas automaticamente as notificações em que a preferencia
                # do usuário é para não receber notificações via SUAP
                if not preferencia.via_suap:
                    rn.lida = True
                rn.save()
                if cache_key and not running_tests():
                    cache.set(cache_key, True, 20)

            if preferencia.via_email:
                # Envia a notificacao por e-mail
                email = vinculo.email_notificacao
                if email and not so_notificar:
                    send_mail(assunto, mensagem, de, [email], fail_silently, html, True)
                    if cache_key and not running_tests():
                        cache.set(cache_key, True, 20)

        else:
            # caso de vínculo que não tem user
            email = vinculo.email_notificacao
            if email and not so_notificar:
                send_mail(assunto, mensagem, de, [email], fail_silently, html)
            if cache_key and not running_tests():
                cache.set(cache_key, True, 20)

    push_subscriptions = PushSubscription.objects.filter(user__is_superuser=True, user__vinculo__in=vinculos)
    if push_subscriptions.exists():
        if so_notificar:
            mensagem_push = 'Acesse a página de notificações do SUAP para mais detalhes.'
        else:
            mensagem_push = 'Acesse sua caixa de e-mail ou a página de notificações do SUAP para mais detalhes.'
        enviar_push_notifications(push_subscriptions, assunto, mensagem_push, url='/comum/notificacoes/')


def send_mail(assunto, mensagem, de, para, fail_silently=True, html=None, is_notification=False, attachments=None, files=None, bcc=None):
    """
    Envia um email para um conjunto de e-mails.

    Args:
        assunto (string): assunto do e-mail;
        mensagem (string): mensagem a enviar pelo e-mail;
        de (string): e-mail do remetente;
        para (list): lista de e-mails para quem será enviado o e-mail;
        fail_silently (bool): indica que os erros devem ser silenciados;
        html (string): corpo do e-mail no formato *HTML*.
        attachments (list of tuples(name, content, mimetype)): lista de anexos
        files: (list of strings): paths of files to be attached
    """
    from djtools.utils import running_tests

    if bcc is None:
        bcc = []
    if files is None:
        files = []
    if attachments is None:
        attachments = []
    if running_tests():
        django_send_mail(assunto, mensagem, de, para, fail_silently)
    else:
        html = html_email_template(mensagem, is_notification)
        if fail_silently:
            try:
                EmailThread(assunto, html, de, para, fail_silently, bool(html), attachments=attachments, files=files, bcc=bcc).start()
            except Exception:
                pass
        else:
            if isinstance(para, str):
                para = (para,)
            msg = EmailMultiAlternatives(assunto, html, de, para)
            msg.attach_alternative(html, 'text/html')
            for name, content, mimetype in attachments:
                msg.attach(name, content, mimetype)
            for file_path in files:
                msg.attach_file(file_path)
            if bcc:
                msg.bcc = bcc
            msg.send(fail_silently)


def html_email_template(mensagem, is_notification=False, extra_html=''):
    mensagem = mensagem.replace('\n', '<br>')
    """
    Obtem o **HTML** padrão para mensagens via e-mail.

    Args:
        mensagem (string): texo da mensagem.

    Returns:
         String contendo o **HTML** da mensagem.
    """
    body = f"""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
        <html xmlns="http://www.w3.org/1999/xhtml">
        <head>
        <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
        <meta content="width=device-width, initial-scale=1" name="viewport" />
        <meta name="x-apple-disable-message-reformatting" />
        <meta name="format-detection" content="telephone=no" />
        <title>Notificação do SUAP</title>
        <style>
            body {{  margin: 0; width: 100% }}
            dd {{ margin: 0; padding: 0 0 15px }}
            dt {{ font-weight: bold }}
            h1 {{ color: #666; font-size: 12pt; font-weight: 300; margin-bottom: 0 }}
            h2 {{ color: #444; font-size: 14pt; margin-top: 5px }}
            h2 ~ p {{ color: #444 }}
            h3 {{ border-bottom: 2px solid #666; color: #444; font-size: 12pt; padding-bottom: 5px; padding-top: 20px }}
            img {{ border: 0; margin: 15px 0; width: 140px }}
            table {{ border-collapse: collapse; clear:both; font-family: Arial; font-size: 14px; margin: 0 auto; max-width: 800px }}
            .wrapper {{ background-color: #F2F2F2; background-image: url(https://suap.ifrn.edu.br/static/comum/img/email/email_bg.png); background-repeat: no-repeat; background-position: 2rem center; background-size: 100% auto; display: inline-block; overflow: hidden; padding: 20px 0; width: 100% }}
            .header {{ overflow: hidden }}
            .content {{ background: #fff; border-radius: 8px 8px 0 0; line-height: 20px; padding: 50px }}
            .content .more-info {{ color: #666; margin-top: 60px; position: relative }}
            .content .more-info::before {{ content: "_______"; position: absolute; top: -35px }}
            .content .featured-info {{ background-color:#CCEFFF; border-radius: 5px; font-size: 10pt; padding: 10px }}
            .content .dados-gerais {{ background:#FCFCFC; border:1px dashed #CCCCCC; border-radius:10px; margin:20px 0; padding:20px }}
            .content .dados-gerais h3 {{ padding-top:0 }}
            .sender {{ background: #fff; border-radius: 0 0 8px 8px; border-top: 0 none; line-height: 14px; padding: 0 50px 50px; text-align: right }}
            .sender a {{ color: #75ad0a; padding: 5px 0 0; text-align: right; text-decoration: none }}
            .footer {{ background: #F2F2F2 }}
            .footer td {{ padding: 20px 0 }}
            .footer p {{ color: #666; font-size: 9pt; line-height: 18px; margin: 0; padding: 1px 0 0 }}
            @media screen and (max-width: 800px) {{
                table {{ width: calc(100% - 40px) }}
                .content {{ padding: 20px }}
                .sender {{ padding: 0 20px 20px }}
            }}
        </style>
        </head>
        <body>
            <div class="wrapper">
                <table>
                    <tr>
                        <td valign="top" class="header">
                            <img src="https://suap.ifrn.edu.br/static/comum/img/email/email_logo.png" />
                        </td>
                    </tr>
                    <tr>
                        <td valign="top" class="content">
                            {mensagem}
                        </td>
                    </tr>
                     <tr>
                        <td valign="top" class="sender">
                            <p><a href="{settings.SITE_URL}">{settings.SITE_URL.split('//', 1)[1]}</a></p>
                        </td>
                    </tr>
                    <tr class="footer">
                        <td valign="top">"""

    if is_notification:
        body += f"""
        <p><strong>Dúvidas?</strong> Entre em contato com o Setor responsável por esta notificação.</p>
        <p>Este e-mail é enviado de forma automática pelo Suap. Favor, não respondê-lo.</p>
        <p>Caso você não deseje mais receber esse tipo de notificação por e-mail, <a href="{settings.SITE_URL}/admin/comum/preferencianotificacao/">gerencie as suas Preferências de Notificações</a>.</p>
        <p>As preferências também podem ser acessadas pelo menu "Tec. da Informação :: Usuários :: Notificações" no Suap.</p>"""

    footer = f"""</td>
                </tr>
            </table>
        </div>
    {extra_html}
    </body>
    </html>"""

    return f'{body}{footer}'
