import os
import zipfile
from datetime import datetime

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.urls import reverse
from django.utils.html import format_html

from comum.models import Configuracao, Vinculo
from comum.utils import get_setores_que_sou_chefe_hoje, get_uo
from djtools.utils import merge_pdf_files, render_pdf_from_template_with_wkhtmltopdf, send_notification
from documento_eletronico.utils import imprimir_pdf
from rh.models import Funcao, Setor

MSG_PERMISSAO_NEGADA_PROCESSO_CONSULTA_PUBLICA = (
    'Um processo só pode ser visualizado nas seguintes hipóteses: se ele for público e o seu tipo permitir ou estiver vinculado a contrato.'
)

# - - - - - - - - - - - - - - - - - - - - - - -
# Rotinas para impressão de partes do processo
# - - - - - - - - - - - - - - - - - - - - - - -


def gerar_capa_processo_pdf(processo):
    agora = get_datetime_now()
    instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao')

    # uo = get_uo(user)
    orientacao = 'portrait'

    try:
        pdf = render_pdf_from_template_with_wkhtmltopdf(
            'processo_eletronico/imprimir_capa_processo.html',
            context=locals(),
            cmd_options={'header-spacing': 3, 'footer-spacing': 3, 'orientation': orientacao, 'enable-local-file-access': ''},
        )
        # return HttpResponse(pdf, content_type='application/pdf')
        return pdf
    except OSError as e:
        raise OSError(f'Erro ao gerar o arquivo PDF: {e}')


def gerar_requerimento_processo_pdf(processo):
    requerimento = processo.get_requerimento_processo()
    if requerimento:
        pdf = imprimir_pdf(requerimento.documento.arquivo.open('r'), requerimento.documento).content
        return pdf
    return None


def gerar_minuta_pdf(minuta, orientacao, user, consulta_publica_hash, leitura_para_barramento, eh_consulta_publica):
    agora = get_datetime_now()

    imprimir_somente_dados_basicos = False
    if not eh_consulta_publica:
        imprimir_somente_dados_basicos = not minuta.pode_ler(
            user=user, consulta_publica_hash=consulta_publica_hash, leitura_para_barramento=leitura_para_barramento
        )

    if imprimir_somente_dados_basicos:
        from djtools.utils import generate_pdf

        file_object = HttpResponse(content_type='application/pdf')
        uo = minuta.documento.setor_dono and minuta.documento.setor_dono.uo or get_uo(user)
        context = {'minuta': minuta, 'documento': minuta.documento, 'instituicao': Configuracao.get_valor_por_chave('comum', 'instituicao'), 'uo': uo}
        template = 'documento_eletronico/templates/imprimir_documento_restrito.html'

        try:
            pdf_response = generate_pdf(template, file_object=file_object, context=context)
            # Se passar file_object = None, o objeto retornado vai ser um StringIO, daí o conteúdo do pdf estará disponível
            # em pdf_response.getvalue(). Caso file_object seja um HttpResponse, o objeto de retorno será um HttpResponse e
            # o conteúdo do pdf estará disponível em pdf_response.content.
            pdf = pdf_response.content
            return pdf
        except OSError as e:
            raise OSError(f'Erro ao gerar o arquivo PDF: {e}')
    else:
        try:
            context = {
                # A impressão vai ser feita com o cabecalho, corpo e rodapé existente na Minuta.
                'documento': minuta,
                'user': user,
                'agora': agora,
            }
            pdf = render_pdf_from_template_with_wkhtmltopdf(
                'documento_eletronico/templates/imprimir_documento_pdf.html',
                context=context,
                header_template='imprimir_documento_pdf_cabecalho.html',
                footer_template='imprimir_documento_pdf_rodape.html',
                cmd_options={'header-spacing': 3, 'footer-spacing': 3, 'orientation': orientacao, 'enable-local-file-access': ''},
            )
            # return HttpResponse(pdf, content_type='application/pdf')
            return pdf
        except OSError as e:
            raise OSError(f'Erro ao gerar o arquivo PDF: {e}')


def gerar_despacho_pdf(tramite, orientacao, user, eh_consulta_publica):
    agora = datetime.now()

    try:
        pdf = render_pdf_from_template_with_wkhtmltopdf(
            'imprimir_despacho_pdf.html',
            context=locals(),
            header_template='imprimir_despacho_pdf_cabecalho.html',
            footer_template='imprimir_despacho_pdf_rodape.html',
            cmd_options={'header-spacing': 3, 'footer-spacing': 3, 'orientation': orientacao, 'enable-local-file-access': ''},
        )
        # return HttpResponse(pdf, content_type='application/pdf')
        return pdf
    except OSError as e:
        raise OSError(f'Erro ao gerar o arquivo PDF: {e}')


def _parte_documento_processo_pdf(
    documento_processo, user, leitura_para_barramento: bool, eh_consulta_publica: bool, requerimento_documento_digitalizado
) -> dict | None:
    """Monta a parte do PDF do processo de um item de ``Processo.get_todos_documentos_processo``.

    Retorna ``None`` quando o item não entra no PDF: documento removido ou o próprio requerimento, já impresso antes.
    """
    opcoes = {'orientacao': 'portrait', 'user': user, 'eh_consulta_publica': eh_consulta_publica}
    if not hasattr(documento_processo, 'documento'):
        tramite = documento_processo
        return {'tipo_parte_processo': 'DESPACHO', 'pdf': tramite.get_pdf(**opcoes), 'objeto_fonte': tramite}

    if hasattr(documento_processo, 'eh_minuta'):
        minuta = documento_processo.minuta
        pdf = minuta.get_pdf(leitura_para_barramento=leitura_para_barramento, **opcoes)
        return {'tipo_parte_processo': 'MINUTA', 'pdf': pdf, 'objeto_fonte': minuta}

    if documento_processo in documento_processo.processo.get_documentos_removidos():
        return None

    documento = documento_processo.documento
    # Documento digitalizado tem ``documentodigitalizadoprocesso_set``; senão, trata-se de um documento texto.
    tipo_parte_processo = 'DOCUMENTO_DIGITALIZADO' if hasattr(documento, 'documentodigitalizadoprocesso_set') else 'DOCUMENTO_TEXTO'
    # O documento digitalizado só vai ser impresso caso não seja um requerimento.
    if (
        tipo_parte_processo == 'DOCUMENTO_DIGITALIZADO'
        and requerimento_documento_digitalizado
        and requerimento_documento_digitalizado.id == documento.id
    ):
        return None
    pdf = documento.get_pdf(leitura_para_barramento=leitura_para_barramento, **opcoes)
    return {'tipo_parte_processo': tipo_parte_processo, 'pdf': pdf, 'objeto_fonte': documento}


def gerar_partes_processo_pdf(processo, user, leitura_para_barramento: bool, eh_consulta_publica: bool = False, task=None) -> list[dict]:
    """
    Método que retorna uma lista com todos os PDFs que compõem o processo, já na ordem correta (data de inclusão). Cada
    item da lista é um dicionário, com três atributos:
    - tipo_parte_processo (String): CAPA, REQUERIMENTO, DESPACHO, MINUTA, DOCUMENTO_DIGITALIZADO, DOCUMENTO_TEXTO
    - pdf: byte string do PDF;
    - objeto_fonte: O objeto através do qual se obteve o PDF. Ex: Processo, Tramite, DocumentoTexto... .

    :param user: usuário que está querendo ver os PDFs que compõem o processo.
    :param processo: o processo em si
    :param leitura_para_barramento: identifica se o PDFs exibido tem como objetivo a tramitação para barramento. Se for,
     então alguma regras vão ser aplicadas para saber se o PDF deverá conter o conteúdo do documento ou apenas alguns
     dados básicos.
    """

    def new_dict_parte_processo(tipo_parte_processo, pdf, objeto_fonte):
        return {'tipo_parte_processo': tipo_parte_processo, 'pdf': pdf, 'objeto_fonte': objeto_fonte}

    partes_processo_pdf = []
    # Adicionando a capa do processo
    partes_processo_pdf.append(new_dict_parte_processo(tipo_parte_processo='CAPA', pdf=processo.get_capa_pdf(), objeto_fonte=processo))

    # Adiciona o requerimento, caso o processo tenha nascido a partir de um requerimento.
    # Obs: Como o requerimento é, na verdade, um DocumentoDigitalizado, criamos a variável "requerimento_documento_digitalizado"
    # para identiticar esse documento e evitar assim a sua impressão novamente mais abaixo. Esse ajuste se
    # faz necessário porque antes a classe Processo tinha dois métodos que retornavam os documentos que compõem o
    # processo, sendo que um retornava TODOS os documentos (Processo.listar_documentos_com_despachos), e era usado na tela
    # de processos, e outro que retornava TODOS EXCETO O REQUERIMENTO (Processo.listar_todos_documentos_processo que por
    # sua vez é invocado por Processo.get_todos_documentos_processo, usado aqui neste método). Depois de um refactory, o
    # método Processo.listar_documentos_com_despachos foi marcado como deprecated e o método Processo.listar_todos_documentos_processo
    # passou a ser utilizado em todos os locais. Mais a frente ocorreu uma alteração nesse método Processo.listar_todos_documentos_processo,
    # pois os requerimentos não estavam sendo visíveis na página do processo. Daí após o ajuste, o requerimento passou
    # a ser listado na página do processo só que gerou o problema neste método aqui, pois o requerimento passou a ser
    # impresso duas vezes no PDF do corpo do processo. Outro detalhe é que a segunda impressão está ocorrendo em branco,
    # mas aí possívelmente é algum problema com o GhostScript, que está sendo adotado como padrão de impressão.
    requerimento_documento_digitalizado = None
    if processo.has_requerimento_processo():
        requerimento_documento_digitalizado = processo.get_requerimento_processo().documento
        if requerimento_documento_digitalizado.pode_ler(user=user, eh_consulta_publica=eh_consulta_publica):
            partes_processo_pdf.append(
                new_dict_parte_processo(tipo_parte_processo='REQUERIMENTO', pdf=processo.get_requerimento_pdf(), objeto_fonte=processo)
            )

    # Obtendo todos os documentos que compôem o processo:
    # Documentos de Texto, Documentos Digitalizados, Despachos (Trâmites) e Minutas.
    documentos_processo = processo.get_todos_documentos_processo(reverse=False)
    if task:
        task.count(documentos_processo, documentos_processo)
        documentos_processo = task.iterate(documentos_processo)
    for documento_processo in documentos_processo:
        parte = _parte_documento_processo_pdf(
            documento_processo, user, leitura_para_barramento, eh_consulta_publica, requerimento_documento_digitalizado
        )
        if parte:
            partes_processo_pdf.append(parte)

    """
    # Adicionando o despacho de finalização
    if processo.esta_finalizado():
        partes_processo_pdf.append(new_dict_parte_processo(tipo_parte_processo='PAGINA_FINALIZACAO', pdf=processo.get_pagina_finalizacao_pdf(), objeto_fonte=processo))
    """

    return partes_processo_pdf


def gerar_processo_pdf(user, processo, leitura_para_barramento, eh_consulta_publica=False):
    """
    Método que retorna o PDF completo do processo.

    :param user: usuário que está querendo ver os PDFs que compõem o processo.
    :param processo: o processo em si
    :param leitura_para_barramento: identifica se o PDFs exibido tem como objetivo a tramitação para barramento. Se for,
     então alguma regras vão ser aplicadas para saber se o PDF deverá conter o conteúdo do documento ou apenas alguns
     dados básicos.
    """
    paths_files = []

    def add_file_temp_dir(content, nome_arquivo):
        base_filename = f'{nome_arquivo}.pdf'
        filename = os.path.join(settings.TEMP_DIR, base_filename.replace(' ', '_'))
        arquivo = open(filename, 'wb+')
        arquivo.write(content)
        arquivo.close()
        paths_files.append(arquivo.name)

    def remove_files_temp_dir(paths_files):
        for path_file in paths_files:
            os.remove(path_file)

    partes_processo_pdf = gerar_partes_processo_pdf(processo, user, leitura_para_barramento, eh_consulta_publica=eh_consulta_publica)
    ordem = 0
    agora = datetime.now()
    for parte_processo in partes_processo_pdf:
        ordem += 1
        add_file_temp_dir(parte_processo['pdf'], f'{ordem}_{processo.id}_{agora}')

    arquivo_final = merge_pdf_files(paths_files)
    remove_files_temp_dir(paths_files)
    return arquivo_final


def gerar_processo_zip(user, processo, leitura_para_barramento, eh_consulta_publica=False):
    """
    Método que retorna o PDF completo do processo.

    :param user: usuário que está querendo ver os PDFs que compõem o processo.
    :param processo: o processo em si
    :param leitura_para_barramento: identifica se o PDFs exibido tem como objetivo a tramitação para barramento. Se for,
     então alguma regras vão ser aplicadas para saber se o PDF deverá conter o conteúdo do documento ou apenas alguns
     dados básicos.
    """
    paths_files = []

    def add_file_temp_dir(content, nome_arquivo):
        base_filename = f'{nome_arquivo}.pdf'
        filename = os.path.join(settings.TEMP_DIR, base_filename.replace(' ', '_'))
        arquivo = open(filename, 'wb+')
        arquivo.write(content)
        arquivo.close()
        paths_files.append(arquivo.name)

    def remove_files_temp_dir(paths_files):
        for path_file in paths_files:
            os.remove(path_file)

    partes_processo_pdf = gerar_partes_processo_pdf(processo, user, leitura_para_barramento, eh_consulta_publica)
    ordem = 0
    agora = datetime.now()
    for parte_processo in partes_processo_pdf:
        ordem += 1
        add_file_temp_dir(parte_processo['pdf'], f'{ordem}_{processo.id}_{agora}')

    path_zip = os.path.join(settings.TEMP_DIR, str(processo.id) + '.zip')
    zip_file = zipfile.ZipFile(path_zip, 'w')

    for path in paths_files:
        zip_file.write(os.path.relpath(path), os.path.relpath(path), compress_type=zipfile.ZIP_DEFLATED)

    zip_file.close()

    remove_files_temp_dir(paths_files)
    return path_zip


def get_datetime_now():
    try:
        from django.utils import timezone

        return timezone.now()
    except ImportError:
        return datetime.now()


def get_email_interessados(processo):
    emails = []
    for interessado in processo.interessados.all():
        emails.append(interessado.email_notificacao)
    return emails


def get_todos_vinculos_processo(processo):
    interessados = processo.interessados.all()
    acompanhando_processo = processo.acompanhantes_processo.all()
    return set().union(interessados, acompanhando_processo)


def get_email_pessoas_acompanhando_processo(processo):
    emails = []
    for interessado in processo.acompanhantes_processo.all():
        emails.append(interessado.email_notificacao)
    return emails


def get_processo_url(processo):
    return f'{settings.SITE_URL}{processo.get_absolute_url()}'


def get_documento_url(documento):
    return f'{settings.SITE_URL}{documento.get_absolute_url()}'


class Notificar:
    @staticmethod
    def processo_finalizado(processo, usuario_fez_acao=None, gerar_excecao_erro=False):
        titulo = '[SUAP] Processos Eletrônicos: Processo Finalizado'
        texto = []
        texto.append('<h1>Processos Eletrônicos</h1>')
        texto.append('<h2>Processo Finalizado</h2>')
        texto.append('<dl>')
        texto.append(f'<dt>Protocolo:</dt><dd>{processo.numero_protocolo_fisico}</dd>')
        texto.append(f'<dt>Assunto:</dt><dd>{processo.assunto}</dd>')
        texto.append('</dl>')
        texto.append('<h3>Outras informações</h3>')
        texto.append('<dl>')
        texto.append(f'<dt>Interessados:</dt><dd>{processo.get_interessados()}</dd>')
        texto.append('<dt>Criado em:</dt><dd>{}</dd>'.format(processo.data_hora_criacao.strftime('%d/%m/%Y %H:%M')))
        texto.append('<dt>Finalizado em:</dt><dd>{}</dd>'.format(processo.data_finalizacao.strftime('%d/%m/%Y %H:%M')))
        texto.append(f'<dt>Justificativa de Finalização:</dt><dd>{processo.observacao_finalizacao}</dd>')
        texto.append('</dl>')
        texto.append('<p class="more-info">Para mais informações, acesse: <a href="{0!s}">{0!s}</a></p>'.format(get_processo_url(processo)))
        categoria = 'Processo Eletrônico: Finalização de Processo'
        vinculos = get_todos_vinculos_processo(processo)
        try:
            if vinculos:
                vinculos.remove(usuario_fez_acao.get_vinculo()) if usuario_fez_acao and usuario_fez_acao.get_vinculo() in vinculos else None
                send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, vinculos, categoria=categoria, objeto=processo)
        except Exception as e:
            if gerar_excecao_erro:
                raise e

    @staticmethod
    def remocao_finalizacao(processo, usuario_fez_acao=None, gerar_excecao_erro=False):
        titulo = '[SUAP] Remoção de Finalização de Processo Eletrônico'
        texto = []
        texto.append('<h1>Processos Eletrônicos</h1>')
        texto.append('<h2>Processo com Finalização Removida</h2>')
        texto.append('<dl>')
        texto.append(f'<dt>Protocolo:</dt><dd>{processo.numero_protocolo_fisico}</dd>')
        texto.append(f'<dt>Assunto:</dt><dd>{processo.assunto}</dd>')
        texto.append('</dl>')
        texto.append('<h3>Outras informações</h3>')
        texto.append('<dl>')
        texto.append(f'<dt>Interessados:</dt><dd>{processo.get_interessados()}</dd>')
        texto.append('</dl>')
        texto.append('<p class="more-info">Para mais informações, acesse: <a href="{0!s}">{0!s}</a></p>'.format(get_processo_url(processo)))
        vinculos = get_todos_vinculos_processo(processo)
        categoria = 'Processo Eletrônico: Reabertura de Processo'
        try:
            if vinculos:
                vinculos.remove(usuario_fez_acao.get_vinculo()) if usuario_fez_acao and usuario_fez_acao.get_vinculo() in vinculos else None
                send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, vinculos, categoria=categoria, objeto=processo)
        except Exception as e:
            if gerar_excecao_erro:
                raise e

    @staticmethod
    def processo_arquivado(processo, usuario_fez_acao=None, gerar_excecao_erro=False):
        titulo = '[SUAP] Processo Eletrônico Arquivado'
        texto = []
        texto.append('<h1>Processos Eletrônicos</h1>')
        texto.append('<h2>Processo Arquivado</h2>')
        texto.append('<dl>')
        texto.append(f'<dt>Protocolo:</dt><dd>{processo.numero_protocolo_fisico}</dd>')
        texto.append(f'<dt>Assunto:</dt><dd>{processo.assunto}</dd>')
        texto.append('</dl>')
        texto.append('<h3>Outras informações</h3>')
        texto.append('<dl>')
        texto.append(f'<dt>Interessados:</dt><dd>{processo.get_interessados()}</dd>')
        texto.append('</dl>')
        texto.append('<p class="more-info">Para mais informações, acesse: <a href="{0!s}">{0!s}</a></p>'.format(get_processo_url(processo)))
        vinculos = get_todos_vinculos_processo(processo)
        categoria = 'Processo Eletrônico: Arquivamento de Processo'
        try:
            if vinculos:
                vinculos.remove(usuario_fez_acao.get_vinculo()) if usuario_fez_acao and usuario_fez_acao.get_vinculo() in vinculos else None
                send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, vinculos, categoria=categoria, objeto=processo)
        except Exception as e:
            if gerar_excecao_erro:
                raise e

    @staticmethod
    def processo_recebido(tramite, usuario_fez_acao=None, gerar_excecao_erro=False):
        titulo = '[SUAP] Processo Eletrônico Recebido'
        texto = []
        texto.append('<h1>Processos Eletrônicos</h1>')
        texto.append(f'<h2>Processo recebido: {tramite.destinatario_setor}</h2>')
        texto.append('<dl>')
        texto.append(f'<dt>Assunto:</dt><dd>{tramite.processo.assunto}</dd>')
        texto.append('</dl>')
        texto.append('<h3>Outras informações</h3>')
        texto.append('<dl>')
        texto.append(f'<dt>Protocolo:</dt><dd>{tramite.processo.numero_protocolo_fisico}</dd>')
        texto.append(f'<dt>Interessados:</dt><dd>{tramite.processo.get_interessados()}</dd>')
        texto.append('</dl>')
        texto.append('<p class="more-info">Para mais informações, acesse: <a href="{0!s}">{0!s}</a></p>'.format(get_processo_url(tramite.processo)))
        texto = ''.join(texto)
        vinculos = get_todos_vinculos_processo(tramite.processo)
        try:
            if vinculos:
                categoria = 'Processos Eletrônicos: Tramitação'
                vinculos.remove(usuario_fez_acao.get_vinculo()) if usuario_fez_acao and usuario_fez_acao.get_vinculo() in vinculos else None
                send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, vinculos, categoria=categoria, objeto=tramite.processo)
        except Exception as e:
            if gerar_excecao_erro:
                raise e

    @staticmethod
    def processo_encaminhado(tramite, usuario_fez_acao=None, gerar_excecao_erro=False):
        titulo = '[SUAP] Processo Eletrônico Encaminhado'
        texto = []
        texto.append('<h1>Processos Eletrônicos</h1>')
        texto.append(f'<h2>Processo Encaminhado para {tramite.destinatario_setor}</h2>')
        texto.append('<dl>')
        texto.append(f'<dt>Assunto:</dt><dd>{tramite.processo.assunto}</dd>')
        texto.append('</dl>')
        texto.append('<h3>Outras informações</h3>')
        texto.append('<dl>')
        texto.append(f'<dt>Protocolo:</dt><dd>{tramite.processo.numero_protocolo_fisico}</dd>')
        texto.append(f'<dt>Interessados:</dt><dd>{tramite.processo.get_interessados()}</dd>')
        texto.append(f'<dt>Setor de Origem:</dt><dd>{tramite.remetente_setor}</dd>')
        texto.append(f'<dt>Setor de Destino:</dt><dd>{tramite.destinatario_setor}</dd>')
        texto.append('</dl>')
        texto.append('<p class="more-info">Para mais informações, acesse: <a href="{0!s}">{0!s}</a></p>'.format(get_processo_url(tramite.processo)))
        texto = ''.join(texto)
        vinculos = get_todos_vinculos_processo(tramite.processo)
        try:
            if vinculos:
                categoria = 'Processos Eletrônicos: Tramitação'
                vinculos.remove(usuario_fez_acao.get_vinculo()) if usuario_fez_acao and usuario_fez_acao.get_vinculo() in vinculos else None
                send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, vinculos, categoria=categoria, objeto=tramite.processo)
        except Exception as e:
            if gerar_excecao_erro:
                raise e

    @staticmethod
    def solicitacao_despacho(processo, solicitado, gerar_excecao_erro=False):
        titulo = '[SUAP] Processo Eletrônico: Solicitação de Despacho'
        texto = []
        texto.append('<h1>Processos Eletrônicos</h1>')
        texto.append('<h2>Processo com Solicitação de Despacho</h2>')
        texto.append(f'<h2>Prezado(a) {solicitado.nome}, existe uma solicitacao de despacho no processo: {processo.numero_protocolo_fisico}</h2>')
        texto.append(f'<h2>Assunto: {processo.assunto}</h2>')
        texto.append('<h3>Outras informações</h3>')
        texto.append('<dl>')
        texto.append(f'<dt>Interessados:</dt><dd>{processo.get_interessados()}</dd>')
        texto.append('</dl>')
        texto.append('<p class="more-info">Para mais informações, acesse: <a href="{0!s}">{0!s}</a></p>'.format(get_processo_url(processo)))
        categoria = 'Processo Eletrônico: Solicitação de Despacho'
        try:
            send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, [solicitado], categoria=categoria, objeto=processo)
        except Exception as e:
            if gerar_excecao_erro:
                raise e

    @staticmethod
    def cancelamento_solicitacao_despacho(solicitacao_despacho, gerar_excecao_erro=False):
        titulo = '[SUAP] Processo Eletrônico: Cancelamento de Solicitação de Despacho'
        texto = []
        texto.append('<h1>Processos Eletrônicos</h1>')
        texto.append('<h2>Cancelamento de Solicitação de Despacho</h2>')
        texto.append(
            f'<h2>Prezado(a) {solicitacao_despacho.solicitado.nome}, uma solicitacao de despacho foi cancelada no processo: {solicitacao_despacho.processo.numero_protocolo_fisico}</h2>'
        )
        texto.append(f'<h2>Assunto: {solicitacao_despacho.processo.assunto}</h2>')
        texto.append('<h3>Outras informações</h3>')
        texto.append('<dl>')
        texto.append(f'<dt>Interessados:</dt><dd>{solicitacao_despacho.processo.get_interessados()}</dd>')
        texto.append('</dl>')
        texto.append(
            '<p class="more-info">Para mais informações, acesse: <a href="{0!s}">{0!s}</a></p>'.format(
                get_processo_url(solicitacao_despacho.processo)
            )
        )
        vinculos = [solicitacao_despacho.solicitado]
        categoria = 'Processo Eletrônico: Cancelamento de Solicitação de Despacho'
        try:
            send_notification(
                titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, vinculos, categoria=categoria, objeto=solicitacao_despacho.processo
            )
        except Exception as e:
            if gerar_excecao_erro:
                raise e

    @staticmethod
    def solicitacao_assinatura_com_anexacao_a_processo(solicitacao_assinatura_anexacao, gerar_excecao_erro=False):
        try:
            titulo = '[SUAP] Processo Eletrônico: Solicitação de Assinatura de Documento com Anexação a Processo'
            texto = []
            texto.append('<h1>Processos Eletrônicos</h1>')
            texto.append('<h2>Solicitação de Assinatura de Documento com Anexação a Processo</h2>')
            texto.append(
                f'<p>Prezado(a) {solicitacao_assinatura_anexacao.solicitacao_assinatura.solicitado.nome}, uma solicitacao de sua assinatura foi adicionada para o documento: {solicitacao_assinatura_anexacao.solicitacao_assinatura.documento.assunto}</p>'
            )
            texto.append('<h3>Outras informações</h3>')
            texto.append('<dl>')
            texto.append(f'<p>Assunto do Processo: {solicitacao_assinatura_anexacao.processo_para_anexar.assunto}</p>')
            texto.append(f'<p>Protocolo: {solicitacao_assinatura_anexacao.processo_para_anexar.numero_protocolo_fisico}</p>')
            texto.append(f'<p>Setor Atual: {solicitacao_assinatura_anexacao.processo_para_anexar.setor_atual.sigla}</p>')

            if solicitacao_assinatura_anexacao.destinatario_setor_tramite:
                texto.append(f'<p>Setor de Destino: {solicitacao_assinatura_anexacao.destinatario_setor_tramite.sigla}</p>')
            else:
                texto.append('<p>Setor de Destino: (não informado)</p>')

            texto.append(f'<dt>Interessados:</dt><dd>{solicitacao_assinatura_anexacao.processo_para_anexar.get_interessados()}</dd>')
            texto.append('</dl>')
            texto.append(
                '<p class="more-info">Para mais informações, acesse: <a href="{0!s}">{0!s}</a></p>'.format(
                    get_documento_url(solicitacao_assinatura_anexacao.solicitacao_assinatura.documento)
                )
            )
            vinculos = [solicitacao_assinatura_anexacao.solicitacao_assinatura.solicitado.get_vinculo()]
            categoria = 'Processo Eletrônico: Solicitação de Assinatura'
            send_notification(
                titulo,
                ''.join(texto),
                settings.DEFAULT_FROM_EMAIL,
                vinculos,
                categoria=categoria,
                objeto=solicitacao_assinatura_anexacao.processo_para_anexar,
            )
        except Exception as e:
            if gerar_excecao_erro:
                raise e

    @staticmethod
    def remover_permissao_processo_documento(user, chefes_setor, descricao_permissao, gerar_excecao_erro=False):
        titulo = '[SUAP] Processos e Documentos Eletrônicos: Atualização das permissões'
        texto = f'<h1>Atualização das permissões</h1><h2>A seguinte permissão foi excluída pelo usuário {user}.</h2><p>{descricao_permissao}.</p>'
        vinculos = [chefe.get_vinculo() for chefe in chefes_setor]
        #
        try:
            send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, vinculos)
        except Exception as e:
            if gerar_excecao_erro:
                raise e

    @staticmethod
    def processo_atribuido(tramite, gerar_excecao_erro=False):
        processo = tramite.processo
        titulo = '[SUAP] Processo Eletrônico: Atribuição Interna de Processo'
        texto = []
        texto.append('<h1>Processos Eletrônicos</h1>')
        texto.append('<h2>Processo Atribuído</h2>')
        texto.append(
            f'<h2>Prezado(a) {tramite.atribuido_para.pessoa.nome}, o processo: {processo.numero_protocolo_fisico} foi atribuído para você.</h2>'
        )
        texto.append(f'<h2>Assunto: {processo.assunto}</h2>')
        texto.append('<h3>Outras informações</h3>')
        texto.append('<dl>')
        texto.append(f'<dt>Setor Atual:</dt><dd>{processo.setor_atual.sigla}</dd>')
        texto.append(f'<dt>Atribuído por:</dt><dd>{tramite.atribuido_por.nome}</dd>')
        texto.append(f'<dt>Atribuído em:</dt><dd>{tramite.atribuido_em.strftime("%d/%m/%Y")}</dd>')
        texto.append('</dl>')
        texto.append('<p class="more-info">Para mais informações, acesse: <a href="{0!s}">{0!s}</a></p>'.format(get_processo_url(processo)))
        categoria = 'Processo Eletrônico: Atribuição de Processo'
        try:
            send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, [tramite.atribuido_para], categoria=categoria, objeto=processo)
        except Exception as e:
            if gerar_excecao_erro:
                raise e


def setores_que_sou_chefe(user):
    # Retorna apenas os que eh chefe direto (sem descentes)
    if user.eh_servidor:
        usuario_logado = user.get_relacionamento()
        return Setor.objects.suap_ativos().filter(
            pk__in=usuario_logado.servidorfuncaohistorico_set.atuais()
            .filter(funcao__codigo__in=Funcao.get_codigos_funcao_chefia())
            .values_list('setor_suap_id', flat=True)
            .distinct()
        )
    return Setor.objects.suap_ativos().none()


def setores_que_tenho_poder_de_chefe(user):
    # Retorna apenas os que o user tem poder de chefe
    vinculo_logado = user.get_vinculo()
    if 'processo_eletronico' in settings.INSTALLED_APPS:
        from processo_eletronico.models import CompartilhamentoProcessoEletronicoPoderDeChefe

        qs = CompartilhamentoProcessoEletronicoPoderDeChefe.objects.filter(vinculo_permitido=vinculo_logado)
        return Setor.objects.suap_ativos().filter(pk__in=qs.values_list('setor_dono__id', flat=True))
    return Setor.objects.suap_ativos().none()


def setores_que_sou_chefe_ou_tenho_poder_de_chefe(user):
    setores_com_poder_de_chefe = setores_que_tenho_poder_de_chefe(user)
    setores_chefiados = setores_que_sou_chefe(user)
    return (setores_chefiados | setores_com_poder_de_chefe).distinct()


def chefe_ou_com_poder_de_chefe_no_setor(user, setor):
    # Se eh chefe Direto ou Nao
    hoje = datetime.today()
    servidor = user.get_relacionamento()
    if user.eh_servidor:
        historico_funcao = servidor.historico_funcao(hoje, hoje).filter(
            funcao__codigo__in=Funcao.get_codigos_funcao_chefia(), setor_suap__isnull=False
        )
        for funcao_setor in historico_funcao:
            if setor in funcao_setor.setor_suap.descendentes:
                return True

    # Se tem poder de chefe
    return bool(setores_que_tenho_poder_de_chefe(user).filter(pk=setor.id).exists())


def iniciar_gerenciamento_compartilhamento(request):
    # ---------------------------------------
    # Validacoes e Setor escolhido
    # ---------------------------------------
    msg_erro = (
        'Acesso permitido apenas para Chefes de Setores ou pessoas que tenham Poder de Chefe de processos e '
        'documentos eletrônicos no setor. </br></br>'
        'Se você for Chefe de Setor, entre em contato com o setor de Gestão de Pessoas do seu campus para '
        'verificar o cadastro de sua função no SUAP. </br></br>'
        'Se você deseja ter poderes de chefe de processos e documentos eletrônicos em um setor entre em '
        'contato com o chefe desse setor. </br></br>'
    )
    setor = request.GET.get('setor', None)
    setores_sou_chefe = get_setores_que_sou_chefe_hoje(request.user)
    setores_poder_chefe = setores_que_tenho_poder_de_chefe(request.user)

    todos_setores = setores_sou_chefe | setores_poder_chefe

    if setor:
        setor = Setor.objects.suap_ativos().filter(pk=setor).first()
        if setor and not chefe_ou_com_poder_de_chefe_no_setor(request.user, setor):
            raise PermissionDenied(msg_erro)

    setor_escolhido = None
    setor_escolhido = setor or todos_setores.first()
    if not setor_escolhido:
        raise PermissionDenied(msg_erro)

    # Se foi passado o pametro setor e este setor nao estiver no rol de setores do setores_chefe (chefe direto ou poder de chefe)
    # Nesse caso o user deve ter acessado essa tela pela lista se setores
    # O sistema nao mostra uma lista (pills) de setores e sim apenas o setor do parametro setor

    msg_orientacao_acesso = format_html(
        '<p>Você está acessando essa tela por ser Chefe de Setor ou ter Poder de Chefe de documentos e processos eletrônicos no setor {} ou um dos seus descendentes.</p>'
        '<br />'
        '<p><strong>Caso você não visualize o setor que você deseja gerenciar permissões:</strong></p>'
        '<ul>'
        '<li>Localize o setor na <a href="/admin/rh/setor/?excluido__exact=0">consulta de setores do SUAP</a>.</li>'
        '<li>Para cada setor poderá ser disponibilizada a opção "Permissões para Documentos e Processos Eletrônicos".</li>'
        '<li>Essa opção só será exibida para o setor quando você for chefe ou tiver poder de chefe nesse setor.</li>'
        '</ul>',
        setor_escolhido,
    )

    msg_alerta_codigo_protocolo = None
    if not setor_escolhido.uo.codigo_protocolo:
        msg_alerta_codigo_protocolo = format_html(
            '<p>O campus <a href="{}">{}</a> do setor {} não está com o código do protocolo definido, o que impedirá a geração de processos eletrônicos.</p>',
            reverse('admin:rh_unidadeorganizacional_change', args=(setor_escolhido.uo.id,)),
            setor_escolhido.uo,
            setor_escolhido,
        )

    return setor_escolhido, setores_poder_chefe, setor_escolhido, msg_orientacao_acesso, msg_alerta_codigo_protocolo


def usuario_pode_cadastrar_retorno_programado(user, setor):
    # Retorna apenas os que o user pode cadastrar retorno programado
    vinculo_logado = user.get_vinculo()
    if 'processo_eletronico' in settings.INSTALLED_APPS:
        from processo_eletronico.models import CompartilhamentoProcessoEletronicoSetorPessoa, Processo

        return CompartilhamentoProcessoEletronicoSetorPessoa.objects.filter(
            setor_dono=setor, vinculo_permitido=vinculo_logado, nivel_permissao=Processo.PERMISSAO_RETORNO_PROGRAMADO
        ).exists()


def search_fields_para_solicitacao_alteracao_nivel_acesso(tipo_obj):
    from documento_eletronico.models import DocumentoDigitalizado, DocumentoTexto
    from processo_eletronico.models import Processo

    # 1 - documento_texto
    tupla = ()
    prefixo = ''
    if tipo_obj == 1:
        tupla = [*DocumentoTexto.SEARCH_FIELDS, 'assunto', 'id']
        prefixo = 'documento_texto_'
    # 2 documento_digitalizado
    elif tipo_obj == 2:
        tupla = DocumentoDigitalizado.SEARCH_FIELDS
        prefixo = 'documento_digitalizado_'
    # 3 processo
    elif tipo_obj == 3:
        tupla = Processo.SEARCH_FIELDS
        prefixo = 'processo_'

    lista = list(tupla)
    i = 0

    while i < len(lista):
        lista[i] = f'{prefixo}_{lista[i]}'
        i += 1

    return tuple(lista)


def get_nivel_acesso_documento(nivel_acesso):
    """Função que altera o nível de acesso dos documentos do suap para de nível de acesso da classe Processo onde:
    que é 1 - publico, 2 - restrito e 3 - privado/sigiloso"""
    if nivel_acesso == 3:
        return 1
    elif nivel_acesso == 1:
        return 3
    else:
        return 2


def _grupos_do_user(user):
    # Memoiza os nomes dos grupos no próprio user: a listagem chama isto por linha
    # (via pode_ver_informacoes_basicas), mas o acesso depende só do user, não do processo.
    cache_attr = '_nomes_grupos_cache'
    nomes = getattr(user, cache_attr, None)
    if nomes is None:
        nomes = set(user.groups.values_list('name', flat=True))
        setattr(user, cache_attr, nomes)
    return nomes


def auditoria_deve_ter_acesso_ao_processo(user, processo):
    return 'Auditor' in _grupos_do_user(user)


def procuradoria_deve_ter_acesso_ao_processo(user, processo):
    return 'Procurador' in _grupos_do_user(user)


def acesso_ao_processo_em_funcao_cargo(user, processo):
    acesso_auditoria = auditoria_deve_ter_acesso_ao_processo(user, processo)
    acesso_procuradoria = procuradoria_deve_ter_acesso_ao_processo(user, processo)
    return acesso_auditoria or acesso_procuradoria


def pode_receber_processo_privado(vinculo: Vinculo):
    from comum.models import Configuracao

    pks = Configuracao.get_valor_por_chave('processo_eletronico', 'blacklist') or ()
    return str(vinculo.pk) not in pks


def formatar_numero_protocolo_fisico(numero_sem_formatacao):
    """
    Exemplo:
    - 17 dígitos: 23421004953202477 -> 23421.004953.2024-77
    - 21 dígitos: 010704400000331202510 -> 0107044.00000331/2025-10
    """
    if len(numero_sem_formatacao) == 17:
        return f'{numero_sem_formatacao[:5]}.{numero_sem_formatacao[5:11]}.{numero_sem_formatacao[11:15]}-{numero_sem_formatacao[15:]}'
    elif len(numero_sem_formatacao) == 21:
        return f'{numero_sem_formatacao[:7]}.{numero_sem_formatacao[7:15]}/{numero_sem_formatacao[15:19]}-{numero_sem_formatacao[19:]}'
    else:
        return numero_sem_formatacao
