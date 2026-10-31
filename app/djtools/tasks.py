import smtplib

import boto3
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email
from django.core import signing
from django.utils.html import strip_tags
from sentry_sdk import capture_exception

from djtools.assincrono import task
from djtools.storages.utils import download_temporary_file
from djtools.utils import CsvResponse, XlsResponse, eval_attr, html_email_template, rgetattr, rhasattr, send_notification


def tratar_celula_relatorio(valor):
    from django.db.models.query import QuerySet

    from djtools.templatetags.filters import format_

    if isinstance(valor, bool):
        valor = valor and 'Sim' or 'Não'
    elif isinstance(valor, QuerySet):
        valor = ', '.join([str(x) for x in valor.all()])
    elif not isinstance(valor, str) and hasattr(valor, '__iter__'):
        valor = strip_tags(', '.join([format_(e, html=False) for e in valor]))
    else:
        valor = strip_tags(format_(valor, html=False))
    return valor


@task('Enviar Push Notification', method='thread')
def enviar_push_notifications(subscriptions, titulo, mensagem, url, task=None):
    for subscription in task.iterate(subscriptions):
        subscription.notify(titulo, mensagem, url=url)
    return task.finalize('Notificação enviada com sucesso')


@task('Exportar para XLS/CSV')
def table_export(stype, queryset, columns, task=None):
    task.count(queryset, queryset)
    rows = [list(columns)]
    accessors = columns.values()
    for obj in task.iterate(queryset):
        row = []
        for field in accessors:
            if rhasattr(obj, field):
                value = eval_attr(obj, field)
                if callable(value):
                    value = value()
            else:
                value = rgetattr(obj, field)
                if callable(value):
                    if type(value).__name__ == 'ManyRelatedManager':
                        value = ', '.join([str(x) for x in value.all()])
                    else:
                        value = value()
            row.append(tratar_celula_relatorio(value))
        rows.append(row)
    return XlsResponse(rows, processo=task) if stype == 'xls' else CsvResponse(rows, processo=task)


@task('Exportar para XLS/CSV Admin')
def admin_export(type, queryset, request, admin, task=None):
    queryset = queryset[0:50000]
    task.count(queryset, queryset)
    metodo = f'to_{type}'
    if callable(getattr(admin, metodo, None)):
        rows = getattr(admin, metodo)(request, queryset, task)
    else:
        rows = []
        header = []
        for field in admin.list_xls_display or admin.list_display:
            if field != 'show_list_display_icons':
                header_name = field.upper().replace('_', ' ')
                header_name = header_name.removeprefix('GET ')
                header.append(header_name)

        rows.append(header)
        for obj in task.iterate(queryset):
            obj.export_to_xls = True
            row = []
            for field in admin.list_xls_display or admin.list_display:
                if field != 'show_list_display_icons':
                    if rhasattr(obj, field):
                        value = eval_attr(obj, field)
                        if callable(value):
                            value = value()
                    else:
                        value = rgetattr(admin, field)
                        if callable(value):
                            value = value(obj)

                    row.append(tratar_celula_relatorio(value))
            rows.append(row)

    return XlsResponse(rows, processo=task) if type == 'xls' else CsvResponse(rows, processo=task)


@task('Notificar os usuários de um grupo')
def notificar_usuarios_grupo(titulo, remetente, texto, grupo, redirect_url, task=None):
    n = 0
    count = 0
    for usuario in task.iterate(grupo.user_set.all()):
        try:
            n += 1
            count += 1
            texto = '<br />'.join(texto.split('\n'))
            mensagem = []
            mensagem.append(f'<h1>{titulo}</h1>')
            mensagem.append(f'<p>{texto}</p>')
            mensagem.append('<h3>Dados gerais</h3>')
            mensagem.append('<dl>')
            mensagem.append(f'<dt>Mensagem enviada para usuários do grupo:</dt><dd>{grupo}</dd>')
            mensagem.append('</dl>')
            send_notification(titulo, ''.join(mensagem), remetente, [usuario.get_vinculo()], categoria='Mensagem para Grupo')
        except Exception:
            n -= 1
    return task.finalize(f'{n}/{count} notificações enviadas com sucesso.', url=redirect_url)


def _reenviar_para_destinatarios_validos(msg, recusados):
    """Reenvia o email somente aos destinatários aceitos pelo servidor SMTP.

    Descarta os endereços recusados (recebidos em ``SMTPRecipientsRefused``) e reenvia a
    mensagem apenas para os que restaram, de modo que um destinatário inválido não impeça a
    entrega aos demais.

    Args:
        msg: Mensagem cujo envio foi recusado.
        recusados: Mapa ``{endereço: (código, motivo)}`` dos destinatários recusados.

    Returns:
        ``True`` se havia ao menos um destinatário válido e o reenvio foi disparado; ``False``
        se todos foram recusados (nada a reenviar).
    """
    invalidos = set(recusados)
    msg.to = [e for e in msg.to if e not in invalidos]
    msg.cc = [e for e in (msg.cc or []) if e not in invalidos]
    msg.bcc = [e for e in (msg.bcc or []) if e not in invalidos]
    if not msg.recipients():
        return False
    msg.send(False)
    return True


@task('Enviar emails')
def enviar_emails(titulo, mensagem, lista_emails, redirect_url, is_notification=False, bcc=None, attachments=None, files=None, task=None):
    n = 0
    count = 0
    attachments = attachments or []
    files = files or []
    erro_anexo = ''
    for email in task.iterate(lista_emails):
        try:
            validate_email(email)
        except ValidationError:
            continue

        html = html_email_template(mensagem, is_notification)
        try:
            n += 1
            count += 1
            msg = EmailMultiAlternatives(titulo, html, settings.DEFAULT_FROM_EMAIL, [email])
            msg.attach_alternative(html, 'text/html')
            for name, content, mimetype in attachments:
                msg.attach(name, content, mimetype)
            for file_path in files:
                tmp = download_temporary_file(file_path)
                msg.attach_file(tmp)
            if bcc:
                msg.bcc = bcc
            msg.send(False)
        except FileNotFoundError as e:
            # falha ao carregar anexo no email
            erro_anexo = str(e)
            n -= 1
        except smtplib.SMTPRecipientsRefused as e:
            # algum destinatário foi rejeitado pelo SMTP (dado inválido do usuário): reenvia
            # apenas aos válidos; só conta como falha se nenhum destinatário restou.
            try:
                if not _reenviar_para_destinatarios_validos(msg, e.recipients):
                    n -= 1
            except smtplib.SMTPRecipientsRefused:
                n -= 1
        except Exception as e:
            capture_exception(e)
            n -= 1
    if n > 0:
        return task.finalize(f'{n} de {count} e-mails enviados com sucesso.', url=redirect_url)
    else:
        return task.finalize(f'Falha no envio de {count} e-mails. {erro_anexo}', url=redirect_url, error=True)


@task('Enviar emails')
def enviar_emails_responsavel(pk, titulo, mensagem, emails, redirect_url, is_notification=False, bcc=None, attachments=None, files=None, task=None):
    n = 0
    count = 0
    attachments = attachments or []
    files = files or []
    erro_anexo = ''
    for email in task.iterate(emails):
        try:
            if '*' in email:
                n += 1
                continue
            validate_email(email)
        except ValidationError:
            continue

        try:
            n += 1
            count += 1
            token = signing.dumps(email)
            image = f'<img src="{settings.SITE_URL}/edu/registro_leitra_mensagem_responsavel/{pk}/?token={token}"/>'
            html = html_email_template(mensagem, is_notification, extra_html=image)
            msg = EmailMultiAlternatives(titulo, html, settings.DEFAULT_FROM_EMAIL, [email])
            msg.attach_alternative(html, 'text/html')
            for name, content, mimetype in attachments:
                msg.attach(name, content, mimetype)
            for file_path in files:
                tmp = download_temporary_file(file_path)
                msg.attach_file(tmp)
            if bcc:
                msg.bcc = bcc
            msg.send(False)
        except FileNotFoundError as e:
            # falha ao carregar anexo no email
            erro_anexo = str(e)
            n -= 1
        except smtplib.SMTPRecipientsRefused as e:
            # algum destinatário foi rejeitado pelo SMTP (dado inválido do usuário): reenvia
            # apenas aos válidos; só conta como falha se nenhum destinatário restou.
            try:
                if not _reenviar_para_destinatarios_validos(msg, e.recipients):
                    n -= 1
            except smtplib.SMTPRecipientsRefused:
                n -= 1
        except Exception as e:
            capture_exception(e)
            n -= 1
    if n > 0:
        return task.finalize(f'{n} de {count} e-mails enviados com sucesso.', url=redirect_url)
    else:
        return task.finalize(f'Falha no envio de {count} e-mails. {erro_anexo}', url=redirect_url)


@task('Restaurar arquivos de mídia')
def restaurar_arquivos_media(arquivos, task=None):
    session = boto3.Session(
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    )
    resource = session.resource(
        's3',
        use_ssl=True,
        endpoint_url=settings.AWS_S3_ENDPOINT_URL,
    )
    client = resource.meta.client
    restored = []
    not_found = []
    for arquivo in task.iterate(arquivos):
        versions = client.list_object_versions(Bucket=settings.AWS_MEDIA_BUCKET_NAME, Prefix=arquivo)
        if 'DeleteMarkers' in versions:
            for each_delmarker in versions['DeleteMarkers']:
                fileobjver = resource.ObjectVersion(settings.AWS_MEDIA_BUCKET_NAME, each_delmarker['Key'], each_delmarker['VersionId'])
                restored.append(each_delmarker['Key'])
                fileobjver.delete()
        else:
            not_found.append(arquivo)
    task.finalize(f'Arquivos recuperados: {restored}.<br> Arquivos não recuperados: {not_found}', '..')
