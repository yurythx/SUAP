import base64
import datetime
import hashlib
import html
import json
import operator
import os
from functools import cached_property, reduce
from typing import TYPE_CHECKING
from uuid import uuid4

import requests
from django.apps import apps
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.http import HttpResponse
from django.template.loader import get_template
from django.utils.html import strip_tags
import difflib
import re
from django.utils.safestring import SafeString, mark_safe
from reversion.models import Version

from comum.models import Configuracao, User
from comum.utils import get_setor, get_setor_procuradoria, get_sigla_reitoria, get_uo, tl
from djtools.storages import cache_file
from djtools.templatetags.filters import format_
from djtools.utils import get_datetime_now, merge_pdf_files, render_pdf_from_template_with_wkhtmltopdf, retira_acentos, send_notification
from documento_eletronico.status import DocumentoStatus
from rh.models import Setor, UnidadeOrganizacional

if TYPE_CHECKING:
    from documento_eletronico.models import Documento

# Recomendamos que o tamanho máximo de path (PRIVATE_ROOT_DIR) não exceda 94 caracteres
# Considerar: https://gitlab.ifrn.edu.br/cosinf/suap/-/issues/3705
PRIVATE_ROOT_DIR = 'private-media/processo_eletronico'


class EstagioProcessamentoVariavel:
    CRIACAO_DOCUMENTO = 'Criação do Documento'
    ASSINATURA_DOCUMENTO = 'Assinatura do Documento'


def get_documento_texto_tamanho_maximo_em_mb():
    return round(settings.PROCESSO_ELETRONICO_DOCUMENTO_EXTERNO_MAX_UPLOAD_SIZE / 1024.0 / 1024.0, 2)


def gerar_codigo_verificador_documento(documento, msg=None):
    msg = (
        msg
        or '<p>Este documento foi emitido pelo SUAP em {0}. Para comprovar sua autenticidade, '
        'faça a leitura do QRCode ao lado ou acesse {1} e forneça os dados abaixo:</p>'
        '<dl><dt>Código Verificador:</dt><dd>{2}</dd><dt>Código de Autenticação:</dt><dd>{3}</dd></dl>'
    )

    #
    codigo_verificador = mark_safe(
        msg.format(documento.data_criacao.strftime('%d/%m/%Y'), documento.get_url_autenticacao(), documento.id, documento.codigo_autenticacao)
    )
    return codigo_verificador


def convert_pdf_to_string_b64(pdf):
    """
    Método que converte o pdf (byte string) numa string base 64. Isso é bastante útil para a transmissão de conteúdo
    binário.

    :param pdf: byte string
    :return: String Base 64 do pdf
    """
    return base64.b64encode(pdf)


def gerar_pdf_documento_texto(documento, orientacao, user, consulta_publica_hash, leitura_para_barramento, eh_consulta_publica=False):
    """
    Retorna uma string contendo os bytes do pdf do documento, por completo, ou seja, contendo inclusive as assinaturas.
    Obs: Caso o usuário em questão não tenha permissão para ver o conteúdo do documento somente serão impressos os dados
    básicos do documento.

    :param documento: Documento do qual se quer obter os bytes do pdf.
    :param orientacao: Informar 'landscape' ou 'portrait'.
    :param user: Usuário que está tentando realizar a impressão.
    :param consulta_publica_hash hash da consulta externa
    :param leitura_para_barramento É um boleano que indica se o pdf gerado é para ser usado no barramento.
    :return string com os bytes do pdf do documento.
    """
    try:
        imprimir_somente_dados_basicos = not documento.pode_ler(
            user=user,
            consulta_publica_hash=consulta_publica_hash,
            leitura_para_barramento=leitura_para_barramento,
            eh_consulta_publica=eh_consulta_publica,
        )
    except Exception:
        imprimir_somente_dados_basicos = True

    if imprimir_somente_dados_basicos:
        from djtools.utils import generate_pdf

        file_object = HttpResponse(content_type='application/pdf')
        context = {'documento': documento, 'instituicao': Configuracao.get_valor_por_chave('comum', 'instituicao'), 'uo': get_uo(user)}
        template = 'imprimir_documento_restrito.html'

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
        template = 'imprimir_documento_pdf.html'

        # Gerando os dados para os campos verificador e autenticador
        # de documentos
        codigo_verificador = gerar_codigo_verificador_documento(documento)
        # Selo
        selo = os.path.join(settings.STATIC_ROOT, 'comum/img/selo-protocolo.png')
        selo_data = base64.b64encode(open(selo, 'rb').read()).decode('utf-8')
        selo_data = 'data:image/png;base64,' + selo_data
        # QR code
        qrcode_data = documento.qrcode_base64image

        agora = get_datetime_now()

        try:
            pdf = render_pdf_from_template_with_wkhtmltopdf(
                template,
                context=locals(),
                cmd_options={
                    'header-spacing': 3,
                    'footer-spacing': 3,
                    'orientation': orientacao,
                    'enable-local-file-access': '',
                    'page-height': '297mm',
                    'page-width': '210mm',
                },
            )
            # return HttpResponse(pdf, content_type='application/pdf')
            return pdf
        except requests.exceptions.RequestException:
            # RequestException é OSError: sem este ramo, queda do gerador viraria um OSError genérico e a task não a distinguiria.
            raise
        except OSError as e:
            raise OSError(f'Erro ao gerar o arquivo PDF: {e}')


def gerar_pdf_documento_digitalizado(documento, orientacao, user, consulta_publica_hash, leitura_para_barramento, eh_consulta_publica=False):
    def add_file_temp_dir(content):
        base_filename = f'{datetime.datetime.now()}.pdf'
        filename = os.path.join(settings.TEMP_DIR, base_filename.replace(' ', '_'))
        arquivo = open(filename, 'wb+')
        arquivo.write(content)
        arquivo.close()
        return arquivo.name

    def remove_file_temp_dir(path_file):
        try:
            os.remove(path_file)
        except FileNotFoundError:
            pass

    try:
        imprimir_somente_dados_basicos = not documento.pode_ler(
            user=user,
            consulta_publica_hash=consulta_publica_hash,
            leitura_para_barramento=leitura_para_barramento,
            eh_consulta_publica=eh_consulta_publica,
        )
    except Exception:
        imprimir_somente_dados_basicos = True
    conteudo_pdf_assinaturas = gerar_assinatura_documento_digitalizado_pdf(documento, orientacao, user, eh_consulta_publica)
    if not imprimir_somente_dados_basicos:
        # Para os casos de termo de ciência em que o documento digitalizado
        # trata-se de um html será utilizada a função de geraçã do documento texto
        if documento.arquivo.name.split('.')[-1] == 'html':
            return imprimir_pdf(documento.arquivo.open('r'), documento).content
        arquivo_digitalizado = cache_file(documento.arquivo.name)
        path_arquivo_assinatura = add_file_temp_dir(conteudo_pdf_assinaturas)
        arquivo_final = merge_pdf_files([arquivo_digitalizado, path_arquivo_assinatura])
        remove_file_temp_dir(path_arquivo_assinatura)
        remove_file_temp_dir(arquivo_digitalizado)
        return arquivo_final

    return conteudo_pdf_assinaturas


def gerar_assinatura_documento_digitalizado_pdf(documento, orientacao, user, eh_consulta_publica):
    agora = get_datetime_now()
    instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao')
    if user and not user.is_anonymous:
        uo = get_uo(user)
    msg = (
        '<p>Este documento foi armazenado no SUAP em {}. Para comprovar sua integridade, '
        'faça a leitura do QRCode ao lado ou acesse {} e forneça os dados abaixo:</p>'
        '<dl><dt>Código Verificador:</dt><dd>{}</dd><dt>Código de Autenticação:</dt><dd>{}</dd></dl>'
    )
    codigo_verificador = gerar_codigo_verificador_documento(documento, msg)

    try:
        pdf = render_pdf_from_template_with_wkhtmltopdf(
            'documento_eletronico/templates/imprimir_assinaturas_pdf.html',
            context=locals(),
            header_template='imprimir_documento_pdf_cabecalho.html',
            footer_template='imprimir_documento_pdf_rodape.html',
            cmd_options={
                'header-spacing': 3,
                'footer-spacing': 3,
                'orientation': orientacao,
                'enable-local-file-access': '',
                'page-height': '297mm',
                'page-width': '210mm',
            },
        )
        return pdf
    except requests.exceptions.RequestException:
        raise
    except OSError as e:
        raise OSError(f'Erro ao gerar o arquivo PDF: {e}')


def merge_pdfs_pdf(lista_pdf, prefixo_documento):
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

    ordem = 0
    for pdf in lista_pdf:
        ordem += 1
        add_file_temp_dir(pdf, f'{prefixo_documento}_{ordem}')

    arquivo_final = merge_pdf_files(paths_files)
    remove_files_temp_dir(paths_files)
    return arquivo_final


def imprimir_pdf(template_file, documento):
    from weasyprint import HTML

    if documento.eh_valido():
        msg = (
            """
        <footer>
            <div align="center">Este documento foi emitido pelo SUAP e validado por <strong>: """
            + format_(documento.imprimir_assinaturas())
            + """</strong></div>
        </footer>"""
        )
    else:
        msg = """
        <footer>
            <div align="center"><strong>Este documento sofreu alterações após a sua assinatura</strong></div>
        </footer>"""
    html = template_file.read()
    template_file.close()
    if isinstance(html, bytes):
        html = html.decode()
    html = html.replace('</body>', f'{msg}</body>')
    html = html.replace('/static/', 'static/')

    base_url = 'file://{}{}'.format(settings.BASE_DIR, '/deploy')

    out = HTML(string=html, base_url=base_url).write_pdf()
    return HttpResponse(out, content_type='application/pdf')


def app_processo_eletronico_estah_instalada():
    return 'processo_eletronico' in settings.INSTALLED_APPS


def solicitacoes_juntada_pendentes(documento):
    if app_processo_eletronico_estah_instalada():
        SolicitacaoJuntadaDocumento = apps.get_model('processo_eletronico', 'SolicitacaoJuntadaDocumento')
        from processo_eletronico.status import SolicitacaoJuntadaDocumentoStatus

        #
        content_type = ContentType.objects.get_for_model(documento)
        return SolicitacaoJuntadaDocumento.objects.filter(
            status=SolicitacaoJuntadaDocumentoStatus.STATUS_ESPERANDO, anexo_content_id=documento.id, anexo_content_type=content_type
        )
    return None


def existem_solicitacoes_juntada_pendentes(documento):
    solicitacoes = solicitacoes_juntada_pendentes(documento)
    return solicitacoes.exists() if solicitacoes else False


def usuario_deve_ter_acesso_a_documento_restrito_atraves_de_solicitacao_juntada_pendente(user, documento):
    """
    Este método verifica se, para o documento em questão, há uma solicitação de juntada pendente para a qual o solicitante
    (avaliador) é o usuário em questão. Se sim, a leitura do documento será permitida.

    :param user: usuário que deseja acessar o documento
    :param documento: documento restrito para o qual se deseja acesso
    :return: True caso o usuário deva ter acesso ao documento, False caso contrário.
    """
    if documento.eh_restrito and app_processo_eletronico_estah_instalada():
        SolicitacaoJuntadaDocumento = apps.get_model('processo_eletronico', 'SolicitacaoJuntadaDocumento')
        from processo_eletronico.models import Tramite
        from processo_eletronico.status import SolicitacaoJuntadaDocumentoStatus

        setores_visiveis = Tramite.get_todos_setores(user=user)

        solicitacoes_juntada_em_avaliacao_nos_meus_setores = SolicitacaoJuntadaDocumento.objects.filter(
            status=SolicitacaoJuntadaDocumentoStatus.STATUS_ESPERANDO, solicitacao_juntada__tramite__processo__setor_atual__in=setores_visiveis
        )

        if solicitacoes_juntada_em_avaliacao_nos_meus_setores.exists():
            for solicitacao_juntada_documento in solicitacoes_juntada_em_avaliacao_nos_meus_setores:
                if solicitacao_juntada_documento.documento == documento and solicitacao_juntada_documento.pode_deferir_documento(user):
                    return True

    return False


def usuario_deve_ter_acesso_a_documento_restrito_atraves_de_processo(user, documento):
    """
    Este método verifica se o usuário pode ter acesso a determinado documento restrito. De maneira resumida, caso o
    documento em questão tenha vínculo ativo com algum processo em que o usuário é interessado ou que o processo
    está atualmente em algum de seus setores, então o acesso ao documento será permitido.

    :param user: usuário que deseja acessar o documento
    :param documento: documento restrito para o qual se deseja ter acesso.
    :return: True caso o usuário deva ter acesso ao documento, False caso contrário.
    """
    vinculo = user.get_vinculo()
    if documento.eh_restrito and app_processo_eletronico_estah_instalada() and vinculo:
        processos_com_vinculo_ativo_com_documento = get_processos_vinculados_ao_documento(
            documento=documento, exibir_somente_processos_nos_quais_documento_nao_foi_removido=True
        )
        #
        if processos_com_vinculo_ativo_com_documento:
            Tramite = apps.get_model('processo_eletronico', 'Tramite')
            # Setores pelos quais o usuário pode tramitar processos.
            setores_usuario = Tramite.get_todos_setores(user)
            q_processos_em_que_usuario_eh_interessado = Q(interessados=user.get_vinculo())
            q_processos_que_transitam_atualmente_por_setores_usuario = (
                (Q(setor_criacao__in=setores_usuario) & Q(ultimo_tramite__isnull=True))
                | (Q(ultimo_tramite__remetente_setor__in=setores_usuario) & Q(ultimo_tramite__data_hora_recebimento__isnull=True))
                | (Q(ultimo_tramite__destinatario_setor__in=setores_usuario) & Q(ultimo_tramite__data_hora_recebimento__isnull=False))
            )
            # TODO: Rever isso com Hugo (segundo o Git a alteração foi feita por ele em 21/09/2019) para entender o objetivo
            # desta variável, pois 3 signitica público e não privado. Além disso, esta condicional não está tendo efeito
            # prático uma vez que a condicional principal deste método é o documento ser restrito.
            predicate_privados = Q(nivel_acesso=3) & (Q(usuario_gerador=user) | Q(tramites__destinatario_vinculo=vinculo))

            processos_que_autorizam_usuario_a_acessar_documento = processos_com_vinculo_ativo_com_documento.filter(
                q_processos_em_que_usuario_eh_interessado | q_processos_que_transitam_atualmente_por_setores_usuario | predicate_privados
            )
            if processos_que_autorizam_usuario_a_acessar_documento.exists():
                return True
    return False


def usuario_pode_ler_documentotexto_restrito_por_permissao_sistemica(user, documento):
    """
    Este método verifica se o usuário pode ter permissão de leitura a determinado documento restrito com base
    nos grupos do qual ele faz parte no SUAP.
    Por exemplo, Coordenadores de Estágio Sistêmicos precisam ter acesso a termos de compromisso de todos os estágios.

    :param user: usuário que deseja acessar o documento
    :param documento: documento restrito para o qual se deseja ter acesso.
    :return: True caso o usuário deva ter acesso ao documento, False caso contrário.
    """
    DocumentoTexto = apps.get_model('documento_eletronico', 'DocumentoTexto')
    if not isinstance(documento, DocumentoTexto):
        return False

    config: str | dict = Configuracao.get_valor_por_chave('documento_eletronico', 'grupossistemicos_com_perm_leitura_de_modelosdoc')
    if config:
        config = json.loads(config)
    else:
        return False

    grupos_do_usuario = list(user and user.groups.values_list('name', flat=True) or [])
    return any(grupo_permitido in grupos_do_usuario and documento.modelo.pk in ids_modelos for grupo_permitido, ids_modelos in config.items())


def eh_auditor(user):
    perfis = ['Auditor']
    return user.groups.filter(name__in=perfis).exists()


def eh_auditor_chefe(user):
    perfis = ['Auditor Sistêmico']
    return eh_auditor(user) and user.groups.filter(name__in=perfis).exists()


def eh_procurador(user):
    perfis = ['Procurador']
    return user.groups.filter(name__in=perfis).exists()


class CargoDoUsuario:
    """O que ``acesso_ao_documento_em_funcao_cargo`` consulta sobre o usuário, cada coisa no máximo uma vez.

    A listagem do admin de documentos guarda uma por página (#17722); fora dela, cada chamada usa uma nova e consulta
    o mesmo que antes, na mesma ordem: o setor só se for auditor, a procuradoria só se for procurador.
    """

    def __init__(self, user: User) -> None:
        self.user = user

    @cached_property
    def eh_auditor(self) -> bool:
        return eh_auditor(self.user)

    @cached_property
    def setor(self) -> Setor | None:
        return get_setor(self.user)

    @cached_property
    def eh_procurador(self) -> bool:
        return eh_procurador(self.user)

    @cached_property
    def setor_procuradoria(self) -> Setor | None:
        return get_setor_procuradoria()


def auditoria_deve_ter_acesso_ao_documento(user: User, documento: Documento, cargo: CargoDoUsuario | None = None) -> bool:
    cargo = cargo or CargoDoUsuario(user)
    if cargo.eh_auditor:
        eh_do_meu_setor = documento.setor_dono == cargo.setor
        return not eh_do_meu_setor
    return False


def procuradoria_deve_ter_acesso_ao_documento(user: User, documento: Documento, cargo: CargoDoUsuario | None = None) -> bool:
    cargo = cargo or CargoDoUsuario(user)
    if cargo.eh_procurador:
        eh_da_procuradoria = documento.setor_dono == cargo.setor_procuradoria
        return not eh_da_procuradoria
    return False


def acesso_ao_documento_em_funcao_cargo(user: User, documento: Documento, cargo: CargoDoUsuario | None = None) -> bool:
    status = [DocumentoStatus.STATUS_ASSINADO, DocumentoStatus.STATUS_FINALIZADO, DocumentoStatus.STATUS_CANCELADO]
    if documento.eh_documento_texto and documento.status not in status:
        return False
    #
    cargo = cargo or CargoDoUsuario(user)
    acesso_auditoria = auditoria_deve_ter_acesso_ao_documento(user, documento, cargo)
    acesso_procuradoria = procuradoria_deve_ter_acesso_ao_documento(user, documento, cargo)
    return acesso_auditoria or acesso_procuradoria


# TODO: Depois de esclarecida a dúvida com Hugo referente ao TODO no método usuario_deve_ter_acesso_a_documento_restrito_atraves_de_processo,
# acredito ser possível fazer um refactory para simplificar os dois métodos, uma vez que eles tem muitas coisas em comum.


def usuario_deve_ter_acesso_a_documento_publico_e_cancelado_atraves_de_processo(user, documento):
    """
    Este método verifica se o usuário pode ter acesso a determinado documento público e cancelado. De maneira resumida,
    caso o documento em questão tenha vínculo ativo com algum processo em que o usuário é interessado ou que o processo
    está atualmente em algum de seus setores, então o acesso ao documento será permitido.

    :param user: usuário que deseja acessar o documento
    :param documento: documento restrito para o qual se deseja ter acesso.
    :return: True caso o usuário deva ter acesso ao documento, False caso contrário.
    """

    vinculo = user.get_vinculo()

    if documento.eh_publico and documento.estah_cancelado and app_processo_eletronico_estah_instalada() and vinculo:
        processos_com_vinculo_ativo_com_documento = get_processos_vinculados_ao_documento(documento=documento)

        if processos_com_vinculo_ativo_com_documento:
            Tramite = apps.get_model('processo_eletronico', 'Tramite')

            # Setores pelos quais o usuário pode tramitar processos.
            setores_usuario = Tramite.get_todos_setores(user)

            q_processos_em_que_usuario_eh_interessado = Q(interessados=user.get_vinculo())
            q_processos_que_transitam_atualmente_por_setores_usuario = (
                (Q(setor_criacao__in=setores_usuario) & Q(ultimo_tramite__isnull=True))
                | (Q(ultimo_tramite__remetente_setor__in=setores_usuario) & Q(ultimo_tramite__data_hora_recebimento__isnull=True))
                | (Q(ultimo_tramite__destinatario_setor__in=setores_usuario) & Q(ultimo_tramite__data_hora_recebimento__isnull=False))
            )

            processos_que_autorizam_usuario_a_acessar_documento = processos_com_vinculo_ativo_com_documento.filter(
                q_processos_em_que_usuario_eh_interessado | q_processos_que_transitam_atualmente_por_setores_usuario
            )
            if processos_que_autorizam_usuario_a_acessar_documento.exists():
                return True
    return False


def get_processos_vinculados_ao_documento(documento, exibir_somente_processos_nos_quais_documento_nao_foi_removido=False):
    """
    Este método retorna todos os processos aos quais determinado Documento (DocumentoTexto ou DocumentoDigitalizado)
    possua vínculo. Obs: Caso o documento pertence a um processo C, e esse processo C foi anexado a um processo B, e
    B por sua vez foi anexado a A, serão retornados os processo C, B e A.

    :param documento: Documento
    :param exibir_somente_processos_nos_quais_documento_nao_foi_removido: Caso queira exibir somente os processos nos
    quais o documento possui vínculo ativo.

    :return: Caso a aplicação "Processo Eletrônico" esteja instalada e haja processos nos quais o documento possuí vínculo,
    será retornado um QuerySet de Processos. Caso contrário, None.
    """

    if app_processo_eletronico_estah_instalada():
        documentoprocesso = None
        if hasattr(documento, 'documentotextoprocesso_set'):
            documentoprocesso = documento.documentotextoprocesso_set
        elif hasattr(documento, 'documentodigitalizadoprocesso_set'):
            # IFF
            # verifica se o documentodigitalizado é anexado a um documento texto
            # se sim o mesmo adota a permissão do documento texto que tem esses arquivos anexados.
            if not documento.documentos_anexados_documento_digitalizado_anexado.all():
                documentoprocesso = documento.documentodigitalizadoprocesso_set
            else:
                documento_texto_pai = documento.documentos_anexados_documento_digitalizado_anexado.first().documento
                documentoprocesso = documento_texto_pai.documentotextoprocesso_set
            # IFF-FIM

        if documentoprocesso:
            if exibir_somente_processos_nos_quais_documento_nao_foi_removido:
                documentoprocesso = documentoprocesso.filter(data_hora_remocao__isnull=True)
            else:
                documentoprocesso = documentoprocesso.all()

            processo_ids = documentoprocesso.values_list('processo_id', flat=True)
            Processo = apps.get_model('processo_eletronico', 'Processo')
            processos = Processo.objects.filter(id__in=processo_ids)

            # Verificando se os processos aos quais o documento possui vínculo direto estão
            # anexados a outros processos.
            processos_anexadores = Processo.objects.none()
            processo_anexadores_ids = []
            for p in processos:
                processo_anexador = p.get_processo_anexador()
                # Um processo C pode estar anexado a um processo B que por sua vez pode estar
                # anexadoa um processo A. A ideia desse while é varrer toda a hiearquia de
                # processos anexadores que pode existir.
                while processo_anexador:
                    processo_anexadores_ids.append(processo_anexador.id)
                    processo_anexador = processo_anexador.get_processo_anexador()

            if processo_anexadores_ids:
                processos_anexadores = Processo.objects.filter(id__in=processo_anexadores_ids)

            return processos | processos_anexadores

    return None


def gerar_hash(conteudo, use_sha256=False):
    if use_sha256:
        return hashlib.sha256(str(conteudo).encode('utf-8')).hexdigest()
    return hashlib.sha512(str(conteudo).encode('utf-8')).hexdigest()


def file_upload_to(instance, filename):
    tipo = f'{instance.tipo}'.lower()
    setor = f'{instance.setor_dono}'.lower()
    path = f'{PRIVATE_ROOT_DIR}/{setor}/{tipo}'
    ext = filename.split('.')[-1]
    # get filename
    if instance.pk:
        filename = f'{instance.pk}.{ext}'
    else:
        # set filename as random string
        filename = f'{uuid4().hex}.{ext}'
        # return the whole path to the file
    return os.path.join(path, filename)


# Só `{{ variavel }}` e `{{ variavel|upper }}` (único filtro usado nos textos), numa mesma linha, como o lexer do Django;
# tags (`{% %}`) e comentários (`{# #}`) ficam como texto.
VARIAVEL_CKEDITOR_RE = re.compile(r'\{\{[^\S\n]*([a-zA-Z]\w*)[^\S\n]*(\|[^\S\n]*upper[^\S\n]*)?\}\}')


def processar_template_ckeditor(texto: str, variaveis: dict | None) -> SafeString:
    # O texto vem do editor: renderizá-lo com o engine de template do Django permitia executar `{% include %}`,
    # `{% load %}` etc. no servidor (#17926). Por isso só as variáveis são substituídas; a desconhecida vira '', como antes.
    # O resultado é marcado como seguro por conta dos documentos legados que foram otimizados: neles as variáveis
    # contêm html em vez de texto.
    variaveis_to_render = {}
    if variaveis:
        for key in variaveis:
            variavel = str(variaveis.get(key, ''))
            variaveis_to_render[key] = variavel
            variaveis_to_render[key + '_maiusculo'] = variavel.upper()
            variaveis_to_render[key + '_minusculo'] = variavel.lower()
            variaveis_to_render[key + '_iniciais_maiusculas'] = variavel.title()

    def substituir(match: re.Match) -> str:
        valor = variaveis_to_render.get(match.group(1), '')
        # O filtro `upper` do Django não é is_safe: a saída dele era escapada.
        return html.escape(valor.upper(), quote=True) if match.group(2) else valor

    return mark_safe(VARIAVEL_CKEDITOR_RE.sub(substituir, texto))


def get_variaveis(documento_identificador, estagio_processamento_variavel=None, to_dict=True, usuario=None, setor_dono=None):
    usuario = usuario or tl.get_user()
    setor = setor_dono or get_setor(usuario)
    uo = setor and setor.uo

    sigla_reitoria = get_sigla_reitoria()

    reitoria = UnidadeOrganizacional.objects.suap().get(sigla=sigla_reitoria)

    hoje = datetime.date.today()
    meses = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']

    variaveis = (
        # TODO: Essa variável usuário logado tem que ser revista já que o processamento do documento
        # só será feito antes da assinatura balizadora.
        ('usuario_nome', usuario.get_profile().nome, 'Nome do usuário logado', EstagioProcessamentoVariavel.CRIACAO_DOCUMENTO),
        ('documento_data_emissao', format_(hoje), 'Data de emissão do documento', EstagioProcessamentoVariavel.ASSINATURA_DOCUMENTO),
        (
            'documento_data_emissao_por_extenso',
            f'{hoje.day} de {meses[hoje.month - 1]} de {hoje.year}',
            'Data de emissão do documento por extenso',
            EstagioProcessamentoVariavel.ASSINATURA_DOCUMENTO,
        ),
        (
            'documento_data_emissao_por_extenso_maiuscula',
            f'{hoje.day} de {meses[hoje.month - 1]} de {hoje.year}'.upper(),
            'Data de emissão do documento por extenso',
            EstagioProcessamentoVariavel.ASSINATURA_DOCUMENTO,
        ),
        (
            'reitor_nome',
            reitoria.get_diretor_geral()[0].pessoa_fisica.nome if reitoria.get_diretor_geral() else 'Sem Reitor',
            'Nome do reitor',
            EstagioProcessamentoVariavel.ASSINATURA_DOCUMENTO,
        ),
        ('documento_identificador', documento_identificador, 'Identificador do documento', EstagioProcessamentoVariavel.ASSINATURA_DOCUMENTO),
        (
            'instituicao_nome',
            Configuracao.get_valor_por_chave('comum', 'instituicao'),
            'Nome da instituição',
            EstagioProcessamentoVariavel.ASSINATURA_DOCUMENTO,
        ),
        (
            'instituicao_sigla',
            Configuracao.get_valor_por_chave('comum', 'instituicao_sigla'),
            'Sigla da instituição',
            EstagioProcessamentoVariavel.ASSINATURA_DOCUMENTO,
        ),
        ('instituicao_sitio_internet', settings.SITE_URL, 'Site da instituição', EstagioProcessamentoVariavel.ASSINATURA_DOCUMENTO),
    )

    if setor:
        variaveis = (
            *variaveis,
            ('setor_nome', setor.nome, 'Nome do setor do documento', EstagioProcessamentoVariavel.ASSINATURA_DOCUMENTO),
            ('setor_sigla', setor.sigla, 'Sigla do setor do documento', EstagioProcessamentoVariavel.ASSINATURA_DOCUMENTO),
            (
                'setor_chefe',
                str(setor.chefes[0]) if setor.chefes else 'Sem Chefe',
                'Chefe do setor do documento',
                EstagioProcessamentoVariavel.ASSINATURA_DOCUMENTO,
            ),
            (
                'setor_telefones',
                setor.telefones() or 'Sem Telefones cadastrados',
                'Telefones do setor',
                EstagioProcessamentoVariavel.ASSINATURA_DOCUMENTO,
            ),
            ('unidade_sigla', setor.uo.sigla, 'Sigla do campus do usuário logado', EstagioProcessamentoVariavel.ASSINATURA_DOCUMENTO),
            ('unidade_nome', setor.uo.nome, 'Nome do campus do usuário logado', EstagioProcessamentoVariavel.ASSINATURA_DOCUMENTO),
            ('unidade_cnpj', setor.uo.cnpj, 'CNPJ do campus do usuário logado', EstagioProcessamentoVariavel.ASSINATURA_DOCUMENTO),
            (
                'unidade_telefone',
                uo.setor.telefones(sem_ramal=True),
                'Telefone do campus do usuário logado',
                EstagioProcessamentoVariavel.ASSINATURA_DOCUMENTO,
            ),
            (
                'unidade_endereco',
                f'{uo.endereco}, {uo.numero}, {uo.bairro}, {uo.municipio}, CEP {uo.cep}',
                'Endereço do campus do usuário logado',
                EstagioProcessamentoVariavel.ASSINATURA_DOCUMENTO,
            ),
            (
                'unidade_diretor_nome',
                uo.get_diretor_geral()[0].pessoa_fisica.nome if uo.get_diretor_geral() else 'Sem Diretor Geral',
                'Nome do diretor do campus do usuário logado',
                EstagioProcessamentoVariavel.ASSINATURA_DOCUMENTO,
            ),
        )

    if not to_dict:
        return variaveis

    variaveis_as_dict = {}
    for chave, valor, _descricao, estagio_proc_var in variaveis:
        if estagio_processamento_variavel is None or estagio_proc_var == estagio_processamento_variavel:
            variaveis_as_dict[chave] = valor
        else:
            # Esse artifício foi usado para poder manter no template as variáveis que não façam parte do estágio de
            # processamento, caso tenha sido especificado algum.
            variaveis_as_dict[chave] = f'{{{{ {chave} }}}}'
    return variaveis_as_dict


def get_previous(obj, date=None):
    """
    objects have a revision attribute, which has two methods, 'get_next_by_date_created', and
    'get_previous_by_date_created', which you could use to traverse version history either way.
    version.revision.get_previous_by_date_created()

    Returns the latest version of an object prior to the given date.
    [...] each version has a revision attribute for the corresponding revision and can be used to do the following:
        1. get the user that made the change through the revision.user attribute
        2. get the date of the change through the revision.date_created attribute
        3. get the values of the object fields as they were in this revision using the field_dict attribute
        4. get a model instance as it was on that revision using the object_version.object attribute
            revert to that previous version of that object using the revert() method
        5. So try changing your return version.get_object() line to  return version.object_version.object!

    """
    versions = Version.objects.get_for_object(obj)
    versions = versions.filter(revision__date_created__lt=date)

    try:
        version = versions[0]
    except IndexError:
        raise Version.DoesNotExist
    else:
        return version


def revert_to_previous_instance(obj, date=None):
    previous_instance = get_previous(obj, date)
    previous_instance.revert()


def get_setores_compartilhados(user, nivel_permissao):
    from processo_eletronico.utils import setores_que_tenho_poder_de_chefe

    lista_setores_que_tenho_poder_de_chefe = Setor.objects.suap_ativos().filter(id__in=setores_que_tenho_poder_de_chefe(user))
    compartilhamento_setor_usuario = [
        Q(compartilhamentosetorpessoa__vinculo_permitido=user.get_vinculo()),
        Q(compartilhamentosetorpessoa__nivel_permissao=nivel_permissao),
    ]
    setores_compartilhados_com_usuario = Setor.objects.suap_ativos().filter(reduce(operator.and_, compartilhamento_setor_usuario))
    return (setores_compartilhados_com_usuario | lista_setores_que_tenho_poder_de_chefe).distinct()


def get_documento_url(documento):
    return f'{settings.SITE_URL}{documento.get_absolute_url()}'


class Notificar:
    @staticmethod
    def solicitacao_assinatura(solicitado, documento, gerar_excecao_erro=False):
        titulo = '[SUAP] Documento Eletrônico: Solicitação de Assinatura'
        texto = []
        texto.append('<h1>Documentos Eletrônicos</h1>')
        texto.append('<h2>Solicitação de Assinatura</h2>')
        texto.append(f'<p>Sua assinatura foi solicitada para o documento: <strong>{documento.assunto}</strong>.</p>')
        texto.append('<h3>Dados gerais</h3>')
        texto.append('<dl>')
        texto.append(f'<dt>Documento criado por:</dt><dd>{documento.usuario_criacao}</dd>')
        texto.append(f'<dt>Criado em:</dt><dd>{documento.data_criacao.strftime("%d/%m/%Y")}</dd>')
        texto.append(f'<dt>Setor:</dt><dd>{documento.setor_dono}</dd>')
        texto.append('</dl>')
        texto.append('<h3>Tutoriais</h3>')
        texto.append('<ul>')
        texto.append(
            '<li><a href="https://portal.ifrn.edu.br/institucional/tecnologia-da-informacao/tutoriais/suap/como-fazer-o-primeiro-acesso-ao-suap/">Como fazer o primeiro acesso ao Suap?</a</li>'
        )
        texto.append(
            '<li><a href="https://portal.ifrn.edu.br/institucional/tecnologia-da-informacao/tutoriais/suap/como-assinar-um-documento-eletronico/">Como assinar um Documento eletrônico?</a></li>'
        )
        texto.append('</ul>')
        texto.append('<p class="more-info">Para mais informações, acesse: <a href="{0}">{0}</a></p>'.format(get_documento_url(documento)))
        try:
            if solicitado:
                send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, [solicitado], objeto=documento)
        except Exception as e:
            if gerar_excecao_erro:
                raise e

    @staticmethod
    def remocao_solicitacao_assinatura(solicitado, documento, gerar_excecao_erro=False):
        titulo = '[SUAP] Documento Eletrônico: Remoção de Solicitação de Assinatura'
        texto = []
        texto.append('<h1>Documentos Eletrônicos</h1>')
        texto.append('<h2>Remoção da Solicitação de Assinatura</h2>')
        texto.append(f'<p>Uma solicitação de assinatura em seu nome foi removida do documento: <strong>{documento.assunto}</strong>.</p>')
        texto.append('<h3>Dados gerais</h3>')
        texto.append('<dl>')
        texto.append(f'<dt>Documento criado por:</dt><dd>{documento.usuario_criacao}</dd>')
        texto.append(f'<dt>Criado em:</dt><dd>{documento.data_criacao.strftime("%d/%m/%Y")}</dd>')
        texto.append(f'<dt>Setor:</dt><dd>{documento.setor_dono}</dd>')
        texto.append('</dl>')
        try:
            if solicitado:
                send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, [solicitado], objeto=documento)
        except Exception as e:
            if gerar_excecao_erro:
                raise e

    @staticmethod
    def solicitacao_assinatura_concluida(solicitacao, documento, gerar_excecao_erro=False):
        titulo = '[SUAP] Documento Eletrônico: Solicitação de assinatura concluída'
        texto = []
        texto.append('<h1>Documentos Eletrônicos</h1>')
        texto.append('<h2>Solicitação de assinatura concluída</h2>')
        texto.append(
            f'<p>Todas as assinaturas solicitadas para o documento <strong>{documento.assunto}</strong> foram <strong>concluídas</strong>.</p>'
        )
        texto.append('<h3>Dados gerais</h3>')
        texto.append('<dl>')
        texto.append(f'<dt>Documento criado por:</dt><dd>{documento.usuario_criacao}</dd>')
        texto.append('<dt>Criado em:</dt><dd>{}</dd>'.format(documento.data_criacao.strftime('%d/%m/%Y')))
        texto.append(f'<dt>Setor:</dt><dd>{documento.setor_dono}</dd>')
        texto.append('</dl>')
        texto.append('<p>--</p>')
        texto.append('<p>Para mais informações, acesse: <a href="{0}">{0}</a></p>'.format(get_documento_url(documento)))
        try:
            send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, [solicitacao.solicitante.get_vinculo()], objeto=documento)
        except Exception as e:
            if gerar_excecao_erro:
                raise e

    @staticmethod
    def solicitacao_assinatura_condicionantes(solicitacoes_condicionantes, documento, gerar_excecao_erro=False):
        for solicitacao in solicitacoes_condicionantes:
            titulo = '[SUAP] Documento Eletrônico: Solicitação de Assinatura'
            texto = []
            texto.append('<h1>Documentos Eletrônicos</h1>')
            texto.append('<h2>Solicitação de Assinatura de Documento</h2>')
            texto.append(f'<p>Sua assinatura foi solicitada para o documento: <strong>{documento.assunto}</strong>.</p>')
            texto.append('<h3>Dados gerais</h3>')
            texto.append('<dl>')
            texto.append(f'<dt>Documento criado por:</dt><dd>{documento.usuario_criacao}</dd>')
            texto.append(f'<dt>Criado em:</dt><dd>{documento.data_criacao.strftime("%d/%m/%Y")}</dd>')
            texto.append(f'<dt>Setor:</dt><dd>{documento.setor_dono}</dd>')
            texto.append('</dl>')
            texto.append('<h3>Tutoriais</h3>')
            texto.append('<ul>')
            texto.append(
                '<li><a href="https://portal.ifrn.edu.br/institucional/tecnologia-da-informacao/tutoriais/suap/como-fazer-o-primeiro-acesso-ao-suap/">Como fazer o primeiro acesso ao Suap?</a</li>'
            )
            texto.append(
                '<li><a href="https://portal.ifrn.edu.br/institucional/tecnologia-da-informacao/tutoriais/suap/como-assinar-um-documento-eletronico">Como assinar um Documento eletrônico?</a></li>'
            )
            texto.append('</ul>')
            texto.append('<p class="more-info">Para mais informações, acesse: <a href="{0}">{0}</a></p>'.format(get_documento_url(documento)))
            solicitado = solicitacao.solicitado
            try:
                if solicitado:
                    send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, [solicitado], objeto=documento)
            except Exception as e:
                if gerar_excecao_erro:
                    raise e

    @staticmethod
    def solicitacao_revisao(revisor, documento, gerar_excecao_erro=False):
        titulo = '[SUAP] Documento Eletrônico: Solicitação de Revisão de Documento'
        texto = []
        texto.append('<h1>Documentos Eletrônicos</h1>')
        texto.append('<h2>Solicitação de Revisão</h2>')
        texto.append(f'<p>Você foi adicionado como <strong>revisor</strong> do documento: <strong>{documento.assunto}</strong>.</p>')
        texto.append('<h3>Dados gerais</h3>')
        texto.append('<dl>')
        texto.append(f'<dt>Documento criado por:</dt><dd>{documento.usuario_criacao}</dd>')
        texto.append(f'<dt>Criado em:</dt><dd>{documento.data_criacao.strftime("%d/%m/%Y")}</dd>')
        texto.append(f'<dt>Setor:</dt><dd>{documento.setor_dono}</dd>')
        texto.append('</dl>')
        texto.append('<p class="more-info">Para mais informações, acesse: <a href="{0}">{0}</a></p>'.format(get_documento_url(documento)))
        try:
            if revisor:
                send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, [revisor], objeto=documento)
        except Exception as e:
            if gerar_excecao_erro:
                raise e

    @staticmethod
    def cancelamento_revisao(revisor, documento, gerar_excecao_erro=False):
        titulo = '[SUAP] Documento Eletrônico: Cancelamento da Solicitação de Revisão de Documento'
        texto = []
        texto.append('<h1>Documentos Eletrônicos</h1>')
        texto.append('<h2>Cancelamento da Solicitação de Revisão</h2>')
        texto.append(f'<p>Uma solicitação de revisão foi cancelada para o documento: <strong>{documento.assunto}</strong>.</p>')
        texto.append('<h3>Dados gerais</h3>')
        texto.append('<dl>')
        texto.append(f'<dt>Documento criado por:</dt><dd>{documento.usuario_criacao}</dd>')
        texto.append(f'<dt>Criado em:</dt><dd>{documento.data_criacao.strftime("%d/%m/%Y")}</dd>')
        texto.append(f'<dt>Setor:</dt><dd>{documento.setor_dono}</dd>')
        texto.append('</dl>')
        try:
            if revisor:
                send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, [revisor], objeto=documento)
        except Exception as e:
            if gerar_excecao_erro:
                raise e

    @staticmethod
    def add_compartilhamento_de_documento(obj, gerar_excecao_erro=False):
        """
        :param obj: instance of CompartilhamentoDocumentoPessoa
        :param gerar_excecao_erro:
        :return:
        """
        from .models import NivelPermissao

        titulo = '[SUAP] Documento Eletrônico: Novo Documento Compartilhado'
        texto = []
        texto.append('<h1>Documentos Eletrônicos</h1>')
        texto.append('<h2>Compartilhamento de Documento</h2>')
        texto.append(f'<p>O documento <strong>{obj.documento.assunto}</strong> foi compartilhado com você.</p>')
        texto.append('<h3>Dados gerais</h3>')
        texto.append('<dl>')
        texto.append(f'<dt>Documento criado por:</dt><dd>{obj.documento.usuario_criacao}</dd>')
        texto.append(f'<dt>Criado em:</dt><dd>{obj.documento.data_criacao.strftime("%d/%m/%Y")}</dd>')
        texto.append(f'<dt>Setor:</dt><dd>{obj.documento.setor_dono}</dd>')
        texto.append(f'<dt>Você tem permissão de:</dt><dd>{dict(NivelPermissao.CHOICES)[obj.nivel_permissao]}</dd>')
        texto.append('</dl>')
        texto.append('<p class="more-info">Para mais informações, acesse: <a href="{0}">{0}</a></p>'.format(get_documento_url(obj.documento)))
        try:
            send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, [obj.vinculo_permitido], objeto=obj.documento)
        except Exception as e:
            if gerar_excecao_erro:
                raise e

    @staticmethod
    def remove_compartilhamento_de_documento(obj, gerar_excecao_erro=False):
        """

        :param obj: instance of CompartilhamentoDocumentoPessoa
        :param gerar_excecao_erro:
        :return:
        """
        from .models import NivelPermissao

        titulo = '[SUAP] Documento Eletrônico: Remoção de Compartilhamento de Documento'
        texto = []
        texto.append('<h1>Documentos Eletrônicos</h1>')
        texto.append('<h2>Remoção de Compartilhamento de Documento</h2>')
        texto.append(
            f'<p>O compartilhamento de {dict(NivelPermissao.CHOICES)[obj.nivel_permissao]} no documento {obj.documento.assunto} foi removido para você.</p>'
        )
        texto.append('<h3>Dados gerais</h3>')
        texto.append('<dl>')
        texto.append(f'<dt>Documento criado por:</dt><dd>{obj.documento.usuario_criacao}</dd>')
        texto.append(f'<dt>Criado em:</dt><dd>{obj.documento.data_criacao.strftime("%d/%m/%Y")}</dd>')
        texto.append(f'<dt>Setor:</dt><dd>{obj.documento.setor_dono}</dd>')
        texto.append('</dl>')
        texto.append('<p class="more-info">Para mais informações, acesse: <a href="{0}">{0}</a></p>'.format(get_documento_url(obj.documento)))
        try:
            send_notification(titulo, ''.join(texto), settings.DEFAULT_FROM_EMAIL, [obj.vinculo_permitido], objecto=obj.documento)
        except Exception as e:
            if gerar_excecao_erro:
                raise e


def processar_template_documentos_anexados(anexos):
    template = get_template('documento_eletronico/templates/documento_eletronico/lista_anexos_do_documento.html')
    return mark_safe(template.render(anexos))


def anonimizar_identificador_unico_matricula_aluno(matricula):
    from math import ceil, floor

    qtd_anonim = round(len(matricula) / 2) - 1
    anonim_f = (qtd_anonim / 2) - 1
    anonim_i = qtd_anonim - anonim_f
    anonim_f = ceil(anonim_f)
    anonim_i = floor(anonim_i)

    return ('*' * int(anonim_i)) + matricula[int(anonim_i) : -int(anonim_f)] + ('*' * int(anonim_f))


def anonimizar_identificador_unico_matricula_servidor(matricula):
    matricula = matricula.zfill(7)
    matricula = matricula[0:3] + '*' * 4
    return matricula


"""
#=====# DO THE ACTUAL CONVERSION #=====#
echo "  Compressing PDF & embedding fonts..."
run gs $MSGOPTS \
    -dBATCH -dNOPAUSE -dNOOUTERSAVE \
    -dCompatibilityLevel=1.4 \
    -dEmbedAllFonts=true -dSubsetFonts=true \
    -dCompressFonts=true -dCompressPages=true \
    -dUseCIEColor -sColorConversionStrategy=RGB \
    -dDownsampleMonoImages=false -dDownsampleGrayImages=false -dDownsampleColorImages=false \
    -dAutoFilterColorImages=false -dAutoFilterGrayImages=false \
    -sDEVICE=pdfwrite \
    -sOutputFile=$TMPFILE $INPUT
echo "  Converting to PDF/A-1B..."
run gs $MSGOPTS \
    -dPDFA=1 -dBATCH -dNOPAUSE -dNOOUTERSAVE \
    $QUALITYOPTS \
    -dCompatibilityLevel=1.4 -dPDFACompatibilityPolicy=1 \
    -dUseCIEColor -sProcessColorModel=DeviceRGB -sColorConversionStrategy=RGB \
    -sOutputICCProfile=$ICCTMPFILE \
    -sDEVICE=pdfwrite \
    -sOutputFile=$OUTPUT $TMPFILE $PSTMPFILE
"""


def gerar_html_diff_simples(original_html: str, retificado_html: str) -> str:
    """
    Gera comparação (diff) entre dois documentos HTML em nível de parágrafo.

    Compara cada parágrafo do documento e classifica as mudanças como:
    - Adição: Parágrafo novo que não existia no original
    - Remoção: Parágrafo que foi removido do original
    - Alteração: Parágrafo que teve seu conteúdo modificado

    Args:
        original_html: HTML do documento original
        retificado_html: HTML do documento retificado

    Returns:
        HTML do documento retificado com marcações de mudanças e JSON embutido
        contendo todas as alterações detectadas
    """
    import json
    from html import unescape as html_unescape, escape
    from django.utils.safestring import mark_safe
    from django.utils.html import strip_tags

    # Valida entradas
    if not original_html or not retificado_html:
        return mark_safe(retificado_html or original_html or '')

    # =========================================================================
    # FUNÇÕES AUXILIARES
    # =========================================================================

    def limpar_paragrafo(texto):
        """
        Remove whitespace múltiplo e espaços não-quebrantes.
        Normaliza o texto para comparação consistente.
        """
        return re.sub(r'[\s\xa0]+', ' ', texto).strip()

    def html_para_texto_com_quebras(html):
        """
        Converte HTML para texto preservando estrutura de parágrafos.

        Importante: Converte <br> e </p> em quebras de linha ANTES de remover tags,
        pois strip_tags() remove as tags sem preservar a estrutura.
        """
        # Substitui <br>, <br/>, <br type="_moz"> por \n
        html = re.sub(r'<br\s*/?>', '\n', html, flags=re.IGNORECASE)
        # Substitui </p> por \n para separar parágrafos
        html = re.sub(r'</p>', '\n', html, flags=re.IGNORECASE)
        # Remove outras tags HTML
        text = strip_tags(html)
        # Desconverte entidades HTML (&nbsp; → espaço, etc)
        text = html_unescape(text)
        return text.strip()

    # =========================================================================
    # PREPARAÇÃO DOS DADOS
    # =========================================================================

    # Converte HTML para texto preservando estrutura de parágrafos
    original_text = html_para_texto_com_quebras(original_html)
    retificado_text = html_para_texto_com_quebras(retificado_html)

    # Se forem idênticos, retorna sem marcações
    if original_text == retificado_text:
        return mark_safe(retificado_html)

    # Divide em parágrafos
    original_paras = original_text.split('\n')
    retificado_paras = retificado_text.split('\n')

    # =========================================================================
    # ANÁLISE DE DIFERENÇAS
    # =========================================================================

    # Compara parágrafos usando difflib
    para_sm = difflib.SequenceMatcher(None, original_paras, retificado_paras)

    # Lista de todas as mudanças detectadas
    changes_list = []
    # Mapeia índice do parágrafo retificado para mudança detectada
    para_changes = {}

    # Processa os opcodes do diff
    opcodes = para_sm.get_opcodes()

    for op_idx, (op, i1, i2, j1, j2) in enumerate(opcodes):
        if op == 'equal':
            # Parágrafos iguais - sem mudanças
            for j in range(j1, j2):
                para_changes[j] = None

        elif op == 'replace':
            # Parágrafos substituídos - detecta tipo de mudança
            for j_idx in range(j1, j2):
                i_idx = i1 + (j_idx - j1) if i1 + (j_idx - j1) < i2 else i2 - 1

                antes_para = original_paras[i_idx] if i_idx < len(original_paras) else ''
                depois_para = retificado_paras[j_idx]

                antes_limpo = limpar_paragrafo(antes_para)
                depois_limpo = limpar_paragrafo(depois_para)

                # Classifica a mudança baseado no conteúdo
                if not antes_limpo and depois_limpo:
                    # Apenas adição
                    tipo = 'adicao'
                    change_data = {'tipo': tipo, 'texto': depois_limpo}
                elif antes_limpo and not depois_limpo:
                    # Apenas remoção
                    tipo = 'remocao'
                    change_data = {'tipo': tipo, 'texto': antes_limpo}
                elif antes_limpo and depois_limpo and antes_limpo != depois_limpo:
                    # Alteração
                    tipo = 'alteracao'
                    change_data = {'tipo': tipo, 'antes': antes_limpo, 'depois': depois_limpo}
                else:
                    continue

                changes_list.append(change_data)
                para_changes[j_idx] = len(changes_list) - 1

        elif op == 'insert':
            # Parágrafos adicionados
            # Verifica se o próximo opcode é delete - se for, são alterações alinhadas
            next_delete = False
            if op_idx + 1 < len(opcodes):
                next_op = opcodes[op_idx + 1]
                if next_op[0] == 'delete':
                    next_delete = True

            for j_idx in range(j1, j2):
                depois_para = retificado_paras[j_idx]
                depois_limpo = limpar_paragrafo(depois_para)

                if depois_limpo:  # Ignora parágrafos vazios
                    # Se houver delete próximo, será tratado como alteração
                    if not next_delete:
                        change_data = {'tipo': 'adicao', 'texto': depois_limpo}
                        changes_list.append(change_data)
                        para_changes[j_idx] = len(changes_list) - 1

        elif op == 'delete':
            # Parágrafos removidos
            # Verifica se o opcode anterior foi insert - se foi, já foi tratado como alteração
            if op_idx == 0 or opcodes[op_idx - 1][0] != 'insert':
                # Remoção genuína (não foi tratada como alteração no insert anterior)
                for i_idx in range(i1, i2):
                    antes_para = original_paras[i_idx]
                    antes_limpo = limpar_paragrafo(antes_para)

                    if antes_limpo:
                        change_data = {'tipo': 'remocao', 'texto': antes_limpo}
                        changes_list.append(change_data)

    # Filtra mudanças muito óbvias/placeholders
    changes_consolidated = []
    seen_changes = set()

    for change in changes_list:
        if change['tipo'] == 'alteracao':
            antes = change['antes']
            depois = change['depois']

            if len(antes) < 1 or len(depois) < 1:
                continue
            if antes == depois:
                continue
            if not any(c.isalnum() for c in antes) or not any(c.isalnum() for c in depois):
                continue

            change_key = f'{change["tipo"]}:{antes}:{depois}'
        else:
            texto = change['texto']

            if len(texto) < 1:
                continue
            if not any(c.isalnum() for c in texto):
                continue

            change_key = f'{change["tipo"]}:{texto}'

        if change_key not in seen_changes:
            seen_changes.add(change_key)
            changes_consolidated.append(change)

    # Reconstrói o texto retificado com marcações
    result_parts = []

    for j_idx, para in enumerate(retificado_paras):
        if j_idx in para_changes and para_changes[j_idx] is not None:
            # Parágrafo foi modificado - marca o texto modificado
            change_idx = para_changes[j_idx]
            change_data = changes_list[change_idx]
            tipo = change_data['tipo']

            if tipo == 'alteracao':
                change_data['antes']
                change_data['depois']

                # Marca o parágrafo inteiro com classe de alteração
                # (será processado pelo JS/CSS no template)
                para_escaped = escape(para)
                para_html = f'<span class="diff-alteration" data-change-idx="{change_idx}">{para_escaped}</span>'
            elif tipo == 'adicao':
                para_escaped = escape(para)
                para_html = f'<span class="diff-addition" data-change-idx="{change_idx}">{para_escaped}</span>'
            elif tipo == 'remocao':
                para_escaped = escape(para)
                para_html = f'<span class="diff-removal" data-change-idx="{change_idx}">{para_escaped}</span>'
            else:
                para_html = escape(para)

            result_parts.append(para_html)
        else:
            # Parágrafo não foi modificado
            result_parts.append(escape(para))

    # Reconstrói o texto consolidado com HTML de marcações
    '\n'.join(result_parts)

    # Serializa as mudanças consolidadas
    changes_json = json.dumps(changes_consolidated, ensure_ascii=False)

    # Não tenta substituir no HTML - apenas adiciona dados JSON
    # O template será responsável por fazer o highlighting interativo
    result_with_data = retificado_html + f'<div id="document-changes-data" data-changes=\'{changes_json}\' style="display: none;"></div>'

    return mark_safe(result_with_data)


def indexar_documento_texto(pk, corpo):
    from documento_eletronico.models import DocumentoTexto

    corpo_indexado = (
        retira_acentos(html.unescape(strip_tags(corpo))).lower().replace('  ', ' ').replace('\r', '').replace('\n', ' ').replace('\t', ' ')
    )
    DocumentoTexto.objects.filter(pk=pk).update(corpo_indexado=corpo_indexado)
