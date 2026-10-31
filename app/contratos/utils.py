from functools import wraps

from django.conf import settings
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.admin.options import get_content_type_for_model
from django.contrib.auth.decorators import login_required
from django.utils.encoding import force_str

from contratos.models import Contrato
from djtools.utils import dinheiro_extenso, send_notification


def por_extenso(value):
    if bool(value):
        reais, centavos = str(value).split('.')
        return f'{dinheiro_extenso(reais, centavos)}'
    else:
        return '-'


class Notificar:
    @staticmethod
    def contratos_a_serem_fiscalizados(agenda):
        texto = []
        texto.append('<h1>Contrato a ser fiscalizado</h1>')
        texto.append(f'<h2>Contrato: {agenda.contrato}</h2>')
        texto.append(f'<h3>Ação a ser realizada em {agenda.data_prevista.strftime("%d/%m/%Y")}:</h3>')
        texto.append(f'<p>{agenda.descricao}</p>')
        texto.append(
            '<p class="more-info">Para mais informações, acesse: <a href="{0!s}?tab=agenda_de_fiscalizacao">{0!s}</a></p>'.format(
                f'{settings.SITE_URL}{agenda.contrato.get_absolute_url()}'
            )
        )
        if agenda.fiscais.exists():
            fiscais = [fiscal.servidor.get_vinculo() for fiscal in agenda.fiscais.all()]
        else:
            fiscais = [fiscal.servidor.get_vinculo() for fiscal in agenda.contrato.get_fiscais_atuais()]

        send_notification('[SUAP] Contratos: Contrato a ser fiscalizado', ''.join(texto), settings.DEFAULT_FROM_EMAIL, fiscais)

    @staticmethod
    def informar_pendencias_na_medicao_ao_fiscal(medicao):
        """Enviando email, notificando Fiscal de Contrato sobre pendências em determinada medição"""
        contrato = medicao.parcela.cronograma.contrato
        titulo = '[SUAP] Contratos: Medição com pendências'
        texto = []
        texto.append('<h1>Medição de Contrato com Pendências</h1>')
        texto.append(f'<h2>Contrato: {contrato}</h2>')
        texto.append('<h3>Seguem as pendências informadas pelo Gerente do Contrato:</h3>')

        for medicao_documento in medicao.documentos_comprobatorios.filter(recebido_gerente='Pendente'):
            texto.append('<dl>')
            texto.append(f'<dt>Documento:</dt><dd>{medicao_documento.tipo_documento_comprobatorio.descricao}</dd>')
            texto.append(f'<dt>Pendência:</dt><dd>{medicao_documento.parecer_gerente}</dd>')
            texto.append('</dl>')
        texto.append(
            '<p class="more-info">Para visualizar a medição, acesse: <a href="{0}">{0}</a></p>'.format(
                f'{settings.SITE_URL}{medicao.get_update_url()}'
            )
        )
        send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, [medicao.fiscal.servidor.get_vinculo()])

    @staticmethod
    def contrato_sem_garantia_vinculada(contrato):
        titulo = '[SUAP] Contratos: Aviso - Adicione arquivo da Garantia contratual'

        categoria = f'Adicione arquivo da garantia - Contrato {contrato.numero}'
        texto = []
        texto.append(f'<h1>{categoria}</h1>')
        texto.append(
            f'<p>O contrato {contrato.numero} foi cadastrado com exigência de garantia contratual, '
            f'porém ainda não existe nenhhum arquivo de Garantia vinculado'
        )
        texto.append('<p>Acesse o Contrato e adicione os arquivos na aba Garantias</p>')
        texto.append('<h3>Dados gerais</h3>')
        texto.append('<dl>')
        texto.append(f'<dt>Contrato:</dt><dd>{contrato}</dd>')
        texto.append(f'<dt>Processo Eletrônico:</dt><dd>{contrato.processo}</dd>')
        texto.append('<dt>Data de Início:</dt><dd>{}</dd>'.format(contrato.data_inicio.strftime('%d/%m/%Y')))
        texto.append('</dl>')
        texto.append(
            '<p class="more-info">Para mais informações, acesse: <a href="{0!s}?tab=7">{0!s}</a></p>'.format(
                f'{settings.SITE_URL}{contrato.get_absolute_url()}'
            )
        )

        vinculos_fiscais_atuais = [fiscal.servidor.get_vinculo() for fiscal in contrato.get_fiscais_atuais()]

        send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, vinculos_fiscais_atuais, categoria=categoria)

    @staticmethod
    def contrato_a_expirar(contrato, dias):
        titulo = '[SUAP] Contratos: Expiração de Contrato'

        categoria = 'Expiração de Contrato'
        texto = []
        texto.append(f'<h1>{categoria}</h1>')
        texto.append(f'<h2>Contrato #{contrato.numero}</h2>')
        texto.append(f'<p>O contrato {contrato.numero} está a {dias} dias de expiração.</p>')
        texto.append(
            '<p class="more-info">Para mais informações, acesse: <a href="{0!s}">{0!s}</a></p>'.format(
                f'{settings.SITE_URL}{contrato.get_absolute_url()}'
            )
        )

        vinculos_fiscais_atuais = [fiscal.servidor.get_vinculo() for fiscal in contrato.get_fiscais_atuais()]

        send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, vinculos_fiscais_atuais, categoria=categoria)

    @staticmethod
    def contrato_sem_mao_de_obra(contrato: Contrato) -> None:
        titulo = '[SUAP] Contratos: Contrato de mão de obra sem registro'
        categoria = f'Mão de obra sem registro - Contrato {contrato.numero}'
        url_contrato = f'{settings.SITE_URL}{contrato.get_absolute_url()}?tab=maodeobra'
        texto = [
            '<h1>Contrato de mão de obra sem registro</h1>',
            f'<h2>Contrato: {contrato}</h2>',
            f'<p>Solicita-se o preenchimento das informações de "Mão de obra" referentes ao contrato {contrato.numero}, '
            'incluindo os dados obrigatórios e os respectivos anexos/documentos dos colaboradores vinculados ao contrato.</p>',
            f'<p class="more-info">Para mais informações, acesse: <a href="{url_contrato}">{url_contrato}</a></p>',
        ]
        vinculos = [fiscal.servidor.get_vinculo() for fiscal in contrato.get_fiscais_atuais()]
        send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, vinculos, categoria=categoria)

    @staticmethod
    def apostilamento_em_contrato_mao_de_obra(contrato: Contrato) -> None:
        titulo = '[SUAP] Contratos: Repactuação/apostilamento em contrato com exclusividade de mão de obra'
        categoria = f'Repactuação/apostilamento - Contrato {contrato.numero}'
        url_contrato = f'{settings.SITE_URL}{contrato.get_absolute_url()}?tab=maodeobra'
        texto = [
            '<h1>Repactuação/apostilamento em contrato com exclusividade de mão de obra</h1>',
            f'<h2>Contrato: {contrato}</h2>',
            f'<p>Alerta: Foi registrada repactuação/apostilamento em contrato com exclusividade de mão de obra. '
            f'Solicita-se a atualização das informações de "Mão de obra" referentes ao contrato {contrato.numero} '
            'com os novos valores dos postos, conforme instrumento aprovado.</p>',
            f'<p class="more-info">Para mais informações, acesse: <a href="{url_contrato}">{url_contrato}</a></p>',
        ]
        vinculos = [fiscal.servidor.get_vinculo() for fiscal in contrato.get_fiscais_atuais()]
        send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, vinculos, categoria=categoria)


def verificar_fiscal(modelo=None):
    def verificar_fiscal_part(func):
        @login_required
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            from django.shortcuts import get_object_or_404

            from djtools.utils import httprr

            if modelo:
                objeto = get_object_or_404(modelo, pk=next(iter(kwargs.values())))
                contrato = objeto.contrato
            else:
                contrato = get_object_or_404(Contrato, pk=kwargs.get('contrato_id'))
            fiscal = contrato.get_fiscal(request.user.get_relacionamento())
            if not fiscal:
                return httprr(f'/contratos/contrato/{contrato.id}/', 'Você não é fiscal desse contrato.', tag='error', close_popup=True)
            return func(request, *args, **kwargs)

        return wrapper

    return verificar_fiscal_part


def add_log_entry(request, objeto, mensagem=None):
    LogEntry.objects.log_action(
        user_id=request.user.pk,
        content_type_id=get_content_type_for_model(objeto).pk,
        object_id=objeto.pk,
        object_repr=force_str(objeto),
        action_flag=CHANGE,
        change_message=mensagem or 'Edição',
    )
