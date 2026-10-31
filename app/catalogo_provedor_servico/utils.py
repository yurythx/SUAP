from __future__ import annotations

import datetime
import json
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.core import signing
from django.db.models.query import QuerySet
from django.http import HttpRequest

# TODO: Usado para remover tags html nas mensagens utilizadas pelo Notifica, na próxima versão da plataforma vai permitir usar tags HTML
from django.utils.html import strip_tags

from comum.models import APIExterna, Configuracao
from djtools.utils import documento, rtr, running_tests, send_mail

from .providers.factory import SERVICE_PROVIDER_FACTORY_MODULE_NAME

if TYPE_CHECKING:
    from edu.models import Aluno


def format_data(valor):
    if valor:
        data = str(valor).split('-')

        ano = None
        mes = None
        dia = None

        if len(data[0]) == 4:
            ano = int(data[0])
            mes = data[1]
            dia = data[2]
        elif len(data[0]) == 2:
            ano = int(data[2])
            mes = data[1]
            dia = data[0]

        if ano is not None:
            if mes.startswith('0'):
                mes = int(mes[1:])
            else:
                mes = int(mes)

            if dia.startswith('0'):
                dia = int(dia[1:])
            else:
                dia = int(dia)

            return datetime.datetime(ano, mes, dia).date()
    return None


def obter_choices_por_funcao(choices_resource_id, filters):
    try:
        klass_name, method_name = signing.loads(choices_resource_id).split('.')
        module = __import__(SERVICE_PROVIDER_FACTORY_MODULE_NAME, fromlist=[klass_name])
        klass = getattr(module, klass_name)
        func = getattr(klass, method_name)
    except Exception as e:
        if settings.DEBUG and not running_tests():
            raise e
        return []

    try:
        if isinstance(filters, str):
            filters = json.loads(filters)
    except Exception as e:
        if settings.DEBUG:
            raise e
        filters = None
    if filters is None:
        result = func()
    else:
        result = func(filters)
    return result


def reload_choices(campos):
    try:
        for field in campos:
            if 'choices_resource_id' in field:
                choices = obter_choices_por_funcao(field['choices_resource_id'], field['filters'])
                if isinstance(choices, QuerySet):
                    value = field.get('value')
                    if value:
                        obj = choices.filter(pk=value).first()
                        field['choices'] = {obj.pk: str(obj)}
                else:
                    field['choices'] = choices
    except Exception as e:
        if settings.DEBUG:
            raise e
    return campos


def anonimizar_dados_email(dados):
    dados_anon = [dict(f) for f in dados] if dados else []
    for field in dados_anon:
        val = field.get('value')
        name = (field.get('name') or '').lower()
        label = (field.get('label') or '').lower()

        if not val:
            field['value'] = ' '
            continue

        mask = '********'
        if 'cpf' in name or 'cpf' in label or 'telefone' in name or 'telefone' in label or 'tel' in name or 'email' in name or 'email' in label:
            field['value'] = (mask + val[7:]) if len(val) > 7 else mask

    return dados_anon


class Notificar:
    @staticmethod
    def get_sigla_instituicao():
        return Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')

    @staticmethod
    def solicitacao_correcao_de_dados(solicitacao, dados_email, gerar_excecao_erro=False):
        from .models import TemplateNotificaGovBR

        dados_email_anonimizado = anonimizar_dados_email(dados_email)

        fields_com_error = []
        titulo = f'[SUAP] Balcão Digital do {Notificar.get_sigla_instituicao()} - {solicitacao.get_status_display()}'
        texto = []
        texto.append(f'<h1>Balcão Digital do {Notificar.get_sigla_instituicao()}</h1>\n')
        texto.append(f'<h2>Serviço: {solicitacao.servico.titulo}</h2>\n')
        texto.append('<dl>')
        if dados_email_anonimizado:
            for field in dados_email_anonimizado:
                if field['avaliacao_status'] == 'ERROR':
                    if field not in fields_com_error:
                        fields_com_error.append(field)
                    else:
                        continue
                if field not in fields_com_error:
                    texto.append('<dt>{}</dt>: <dd>{}</dd>\n'.format(field['label'], field['value']))
        texto.append('</dl>')
        texto.append('\n<h3>Mensagem:</h3>')
        texto.append('\n<p>Prezado(a),</p>')
        texto.append(f'\n<p>Sua solicitação está "{solicitacao.status_detalhamento}"</p>\n')
        if fields_com_error:
            texto.append('<p>Segue a lista de campos que necessitam correção:</p>\n')
            for field_erro in fields_com_error:
                texto.append('<dt>Campo: {}</dt><dd> - Problema: {}</dd>\n'.format(field_erro['label'], field_erro['avaliacao_status_msg']))
        url = (
            Configuracao.get_valor_por_chave('catalogo_provedor_servico', 'url_catalogo_digital')
            and Configuracao.get_valor_por_chave('catalogo_provedor_servico', 'url_catalogo_digital').format(
                solicitacao.servico.id_servico_portal_govbr
            )
            or ''
        )
        texto.append(
            f'<p>Acesse o Balcão Digital do {Notificar.get_sigla_instituicao()} em {url} e realize as correções para dar continuidade a sua solicitação.</p>'
        )
        conteudo = ''.join(texto)

        mensagem_texto_sms = f'[{Notificar.get_sigla_instituicao()}] Existem dados para corrigir referente a solicitação com número de protocolo #{solicitacao.id}! Acesse {url}'
        variaveis = {'sigla': Notificar.get_sigla_instituicao(), 'id_servico_govbr': solicitacao.id}
        service = APIExterna.NOTIFICA_GOVBR.get_service()

        service.notificar_cidadao_via_notifica_govbr(
            solicitacao,
            mensagem_email=strip_tags(conteudo),
            mensagem_sms=mensagem_texto_sms,
            mensagem_app_govbr=None,
            assunto=titulo,
            dados_email=dados_email,
            tipo_notificacao=TemplateNotificaGovBR.CORRECAO_DADOS,
            variaveis=variaveis,
        )

    @staticmethod
    def solicitacao_nao_atendida(solicitacao, dados_email, gerar_excecao_erro=False):
        from .models import TemplateNotificaGovBR

        dados_email_anonimizado = anonimizar_dados_email(dados_email)

        titulo = f'[SUAP] Balcão Digital do {Notificar.get_sigla_instituicao()} - {solicitacao.get_status_display()}'
        texto = []
        texto.append(f'<h1>Balcão Digital do {Notificar.get_sigla_instituicao()}</h1>\n')
        texto.append(f'<h2>Serviço: {solicitacao.servico.titulo}</h2>\n')
        texto.append('<dl>')
        if dados_email_anonimizado:
            for field in dados_email_anonimizado:
                texto.append('<dt>{}</dt>: <dd>{}</dd>\n'.format(field['label'], field['value']))
        texto.append('<h3>Mensagem:</h3>')
        texto.append('<p>\nPrezado(a),</p>')
        texto.append(
            f'<p>\nSua solicitação com número de protocolo #{solicitacao.id} não foi aceita. Motivo informado: {solicitacao.status_detalhamento}</p>'
        )
        conteudo = ''.join(texto)
        mensagem_texto_sms = f'[{Notificar.get_sigla_instituicao()}]Sua solicitação com número de protocolo  {solicitacao.id} não foi aceita. Motivo {solicitacao.status_detalhamento}'
        variaveis = {
            'sigla_instituicao': Notificar.get_sigla_instituicao(),
            'solicitacao_id': solicitacao.id,
            'solicitacao_status_detalhamento': solicitacao.status_detalhamento,
        }
        service = APIExterna.NOTIFICA_GOVBR.get_service()

        service.notificar_cidadao_via_notifica_govbr(
            solicitacao,
            mensagem_email=strip_tags(conteudo),
            mensagem_sms=mensagem_texto_sms,
            mensagem_app_govbr=None,
            assunto=titulo,
            dados_email=dados_email,
            tipo_notificacao=TemplateNotificaGovBR.NAO_ATENDIDA,
            variaveis=variaveis,
        )

    @staticmethod
    def solicitacao_recebida(solicitacao, dados_email, gerar_excecao_erro=False):
        from .models import TemplateNotificaGovBR

        dados_email_anonimizado = anonimizar_dados_email(dados_email)

        titulo = f'[SUAP] Balcão Digital do {Notificar.get_sigla_instituicao()} - {solicitacao.get_status_display()}'
        texto = []
        texto.append(f'<h1>Balcão Digital do {Notificar.get_sigla_instituicao()}</h1>\n')
        texto.append(f'<h2>Serviço: {solicitacao.servico.titulo}</h2>\n')
        texto.append('<dl>')
        if dados_email_anonimizado:
            for field in dados_email_anonimizado:
                texto.append('<dt>{}</dt>: <dd>{}</dd>\n'.format(field['label'], field['value']))
        texto.append('</dl>')
        texto.append('<h3>Mensagem:</h3>\n')
        texto.append('<p>Prezado(a),</p>\n')
        texto.append(f'<p>Sua solicitação com número de protocolo #{solicitacao.id} foi recebida e está "{solicitacao.get_status_display()}".</p>')
        conteudo = ''.join(texto)
        mensagem_texto_sms = f'[{Notificar.get_sigla_instituicao()}]\nSua solicitação  com número de protocolo {solicitacao.id} para o serviço {solicitacao.servico.titulo} foi recebida e está {solicitacao.get_status_display()}'
        variaveis = {
            'sigla_instituicao': Notificar.get_sigla_instituicao(),
            'solicitacao_id': solicitacao.id,
            'solicitacao_status_display': solicitacao.get_status_display(),
        }
        service = APIExterna.NOTIFICA_GOVBR.get_service()

        service.notificar_cidadao_via_notifica_govbr(
            solicitacao,
            mensagem_email=strip_tags(conteudo),
            mensagem_sms=mensagem_texto_sms,
            mensagem_app_govbr=None,
            assunto=titulo,
            dados_email=dados_email,
            tipo_notificacao=TemplateNotificaGovBR.SOLICITACAO_RECEBIDA,
            variaveis=variaveis,
        )

    @staticmethod
    def solicitacao_dados_corrigidos(solicitacao, dados_email, gerar_excecao_erro=False):
        from .models import TemplateNotificaGovBR

        dados_email_anonimizado = anonimizar_dados_email(dados_email)

        titulo = f'[SUAP] Balcão Digital do {Notificar.get_sigla_instituicao()} - {solicitacao.get_status_display()}'
        texto = []
        texto.append(f'<h1>Balcão Digital do {Notificar.get_sigla_instituicao()}</h1>\n')
        texto.append(f'<h2>Serviço: {solicitacao.servico.titulo}</h2>\n')
        if dados_email_anonimizado:
            fields_list = []
            for field in dados_email_anonimizado:
                if field['label'] not in fields_list and field['avaliacao_status'] != 'ERROR':
                    texto.append('<dt>{}</dt>: <dd>{}</dd>\n'.format(field['label'], field['value']))
                    fields_list.append(field['label'])
        texto.append('\n<h3>Mensagem:</h3>')
        texto.append('\n<p>Prezado(a),</p>')
        texto.append(f'\n<p>As correções realizadas na solicitação com número de protocolo #{solicitacao.id} foram recebidas com sucesso.</p>')
        conteudo = ''.join(texto)
        mensagem_texto_sms = f'[{Notificar.get_sigla_instituicao()}]\nAs correções realizadas na solicitação com número de protocolo {solicitacao.id} do serviço {solicitacao.servico.titulo} foram recebidas com sucesso.'
        variaveis = {'sigla_instituicao': Notificar.get_sigla_instituicao(), 'solicitacao_id': solicitacao.id}
        service = APIExterna.NOTIFICA_GOVBR.get_service()

        service.notificar_cidadao_via_notifica_govbr(
            solicitacao,
            mensagem_email=strip_tags(conteudo),
            mensagem_sms=mensagem_texto_sms,
            mensagem_app_govbr=None,
            assunto=titulo,
            dados_email=dados_email,
            tipo_notificacao=TemplateNotificaGovBR.DADOS_CORRIGIDOS,
            variaveis=variaveis,
        )

    @staticmethod
    def notifica_conclusao_servico_atendido(solicitacao, dados_email, mensagem=None, url_avaliacao=None, gerar_excecao_erro=False):
        from .models import TemplateNotificaGovBR

        dados_email_anonimizado = anonimizar_dados_email(dados_email)

        titulo = f'[SUAP] Balcão Digital do {Notificar.get_sigla_instituicao()} - {solicitacao.get_status_display()}'
        texto = []
        texto.append(f'<h1>Balcão Digital do {Notificar.get_sigla_instituicao()}</h1>\n')
        texto.append(f'<h2>Serviço: {solicitacao.servico.titulo}</h2>\n')
        if dados_email_anonimizado:
            for field in dados_email_anonimizado:
                texto.append('<dt>{}</dt>: <dd>{}</dd>\n'.format(field['label'], field['value']))
        texto.append('\n<h3>Mensagem:</h3>')
        texto.append('\n<p>Prezado(a),</p>')
        texto.append(f'\n<p>A sua solicitação para o serviço {solicitacao.servico.titulo} foi atendida.</p>\n')
        if mensagem:
            texto.append(f'<p>{mensagem}.</p>')
        if url_avaliacao:
            texto.append(f'\nAvalie este serviço clicando em {url_avaliacao}')
        conteudo = ''.join(texto)
        mensagem_texto_sms = f'[{Notificar.get_sigla_instituicao()}] A sua solicitação com número de protocolo {solicitacao.id} para o serviço {solicitacao.servico.titulo} foi atendida. '
        if 'Protocolar documentos' in solicitacao.servico.titulo:
            link_consulta_publica = 'Acompanhe o processo em https://suap.ifrn.edu.br/processo_eletronico/consulta_publica/'
            mensagem_texto_sms += link_consulta_publica
        variaveis = {'sigla_instituicao': Notificar.get_sigla_instituicao(), 'solicitacao_id': solicitacao.id}
        service = APIExterna.NOTIFICA_GOVBR.get_service()

        service.notificar_cidadao_via_notifica_govbr(
            solicitacao,
            mensagem_email=strip_tags(conteudo),
            mensagem_sms=mensagem_texto_sms,
            mensagem_app_govbr=None,
            assunto=titulo,
            dados_email=dados_email,
            tipo_notificacao=TemplateNotificaGovBR.CONCLUSAO_SOLICITACAO,
            variaveis=variaveis,
        )
        if solicitacao.get_registroavaliacao_govbr():
            solicitacao.get_registroavaliacao_govbr().registrar_notificacao()

    @staticmethod
    def envia_comprovante_matricula(request, dados_email, aluno=None, email_solicitante=None):
        if dados_email:
            for field in dados_email:
                if field['name'] == 'email_pessoal':
                    email_solicitante = field['value']

        comprovante_matricula_response = comprovante_matricula_pdf(request, aluno)

        if email_solicitante:
            send_mail(
                assunto='[SUAP] Comprovante de Matrícula',
                mensagem='Caro aluno(a), segue em anexo seu comprovante de matrícula.',
                de=settings.DEFAULT_FROM_EMAIL,
                para=[email_solicitante],
                fail_silently=True,
                attachments=[('Comprovante.pdf', comprovante_matricula_response.content, 'application/pdf')],
            )

    @staticmethod
    def envia_certificados_encceja(
        solicitacao,
        cpf,
        email_solicitante,
        url_avaliacao=None,
    ):
        from encceja.models import Solicitacao as SolicitacaoEncceja

        if email_solicitante:
            attachments = []
            for solicitacaoencceja in SolicitacaoEncceja.objects.filter(cpf=cpf):
                if solicitacaoencceja.pode_certificar():
                    certificado = solicitacaoencceja.imprimir_certificacao(com_timbre=True)
                    if certificado:
                        attachments.append((f'{solicitacaoencceja!s}.pdf', certificado.content, 'application/pdf'))
            assunto = '[SUAP] Solicitação Certificado do ENCCEJA'
            texto = f"""
            Caro cidadão, segue em anexo seu(s) certificado(s) do encceja referente a solicitação com número de protocolo #{solicitacao.id}.
            """
            if url_avaliacao:
                texto += f'\nAvalie este serviço clicando em {url_avaliacao}'
            send_mail(
                assunto=assunto, mensagem=texto, de=settings.DEFAULT_FROM_EMAIL, para=[email_solicitante], fail_silently=True, attachments=attachments
            )
            if solicitacao.get_registroavaliacao_govbr():
                solicitacao.get_registroavaliacao_govbr().registrar_notificacao()


@documento(enumerar_paginas=False)
@rtr('edu/templates/comprovante_matricula_pdf.html')
def comprovante_matricula_pdf(request: HttpRequest, aluno: Aluno) -> dict[str, Any]:
    hoje = datetime.date.today()
    is_matricula_online = True
    instituicao = Configuracao.get_valor_por_chave_str('comum', 'instituicao').upper()

    uo = aluno.curso_campus.diretoria.setor.uo
    return locals()
