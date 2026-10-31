import logging
import os
from datetime import datetime
from decimal import Decimal, InvalidOperation

from botocore.exceptions import BotoCoreError, ClientError
from django.contrib.auth.decorators import login_required
from django.core.exceptions import SuspiciousFileOperation
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.views.decorators.http import require_GET, require_POST

from djtools.utils import JsonResponse
from djtools.utils.http import get_client_ip

from rsc_tae.enums import SituacaoProcesso, TipoDocumentoPreliminar
from rsc_tae.forms import DocumentoPreliminarUploadForm
from rsc_tae.models import (
    DocumentoPreliminarRSCTae,
    DocumentoPreliminarRSCTaeLog,
    ProcessoRSCTae,
    RolSaberCompetencia,
    RolSaberCompetenciaAnexo,
    RolSaberCompetenciaPreenchimento,
)
from rsc_tae.models.anexo import pontos_item_anexos

from ._helpers import (
    _calcular_resumo_por_pontos,
    _montar_resumo_preenchimento,
    _validar_acesso_avaliacao,
    _validar_acesso_processo,
    _validar_acesso_processo_leitura,
    montar_contexto_memorial,
    pontos_por_requisito,
    status_requisitos_obrigatorios,
    anexos_por_item,
)
from ._permissoes import PermissoesProcesso

logger = logging.getLogger(__name__)

# Sufixo que o FileFieldPlus acrescenta ao nome antes de gravar: o hífen mais os 32 caracteres
# do `uuid4().hex`.
TAMANHO_SUFIXO_UUID = 33

# Limite de bytes de um segmento (o nome do arquivo) da chave aceito pelo storage de objetos:
# S3 e MinIO recusam com HTTP 400 (Bad Request) o que passa disso.
LIMITE_BYTES_SEGMENTO_STORAGE = 255

# Falhas de escrita no storage: o sistema de arquivos (OSError), a recusa do próprio Django ao
# nome (SuspiciousFileOperation) e as duas raízes do botocore — ClientError para as respostas
# de erro do bucket, BotoCoreError para o que nem chega a ser resposta (conexão, credencial).
ERROS_DE_STORAGE = (OSError, SuspiciousFileOperation, ClientError, BotoCoreError)


def _parse_date(value):
    """Parse a date from dd/mm/yyyy or yyyy-mm-dd format."""
    raw = (value or '').strip()
    if not raw:
        return None
    for fmt in ('%d/%m/%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _detectar_mimetype(arquivo):
    """Detecta o mimetype do arquivo via python-magic; cai para o content_type do upload."""
    try:
        import magic

        arquivo.seek(0)
        mime = magic.from_buffer(arquivo.read(2048), mime=True)
        arquivo.seek(0)
        return mime
    except Exception:
        return getattr(arquivo, 'content_type', '') or ''


def _extrair_papel(request, item):
    """Extrai e valida o ``papel`` do comprovante enviado no POST.

    Só é considerado quando ``item.aceita_papel``; caso contrário retorna ``(None, None)``.
    O papel é opcional no upload/edição (é preenchido junto com a descrição): ausente ou vazio
    vira ``None``. Retorna ``(papel, erro)`` — ``erro`` é a mensagem quando o valor enviado não
    é 'titular' nem 'substituto'. A obrigatoriedade é cobrada apenas na conclusão do preenchimento.
    """
    if not getattr(item, 'aceita_papel', False):
        return None, None
    raw = (request.POST.get('papel') or '').strip()
    if raw == '':
        return None, None
    if raw not in (RolSaberCompetencia.PAPEL_TITULAR, RolSaberCompetencia.PAPEL_SUBSTITUTO):
        return None, 'Papel inválido.'
    return raw, None


def _aplicar_papel_edicao(request, item, anexo):
    """Atualiza o ``papel`` do anexo na edição, apenas quando o campo é enviado.

    Preserva o valor atual se ``papel`` não vier no POST (a edição pode salvar só a pontuação/período).
    Retorna a mensagem de erro em caso de valor inválido, ou ``None`` em sucesso.
    """
    if not (getattr(item, 'aceita_papel', False) and 'papel' in request.POST):
        return None
    papel, erro = _extrair_papel(request, item)
    if erro:
        return erro
    RolSaberCompetenciaAnexo.objects.filter(pk=anexo.pk).update(papel=papel)
    anexo.papel = papel
    return None


def _parse_pontuacao_manual(request):
    """Lê e valida a pontuação manual do POST (itens não temporais). Retorna ``(Decimal, erro)``."""
    raw = (request.POST.get('pontuacao') or '').strip().replace(',', '.')
    if raw == '':
        return Decimal('0'), None
    try:
        pontuacao = Decimal(raw)
    except InvalidOperation:
        return None, 'Pontuação inválida.'
    if pontuacao < 0:
        return None, 'Pontuação deve ser maior ou igual a zero.'
    return pontuacao, None


def _erro_arquivo_nao_pdf(arquivo):
    """Valida que o upload é PDF (extensão + mimetype). Retorna a mensagem de erro ou None."""
    nome = (getattr(arquivo, 'name', '') or '').lower()
    if not nome.endswith('.pdf'):
        return 'Formato inválido. Envie o documento em PDF.'
    if _detectar_mimetype(arquivo) not in ('application/pdf', 'application/x-pdf'):
        return 'O arquivo enviado não é um PDF válido.'
    return None


def _encurtar_nome_enviado(nome):
    """Encurta o nome do arquivo enviado até a chave final caber no campo e no storage.

    O ``FileFieldPlus`` acrescenta ``-<uuid>`` ao nome e o Django só o encurta DEPOIS de
    perguntar ao storage se ele já existe (``Storage.get_available_name`` → ``head_object``).
    Um nome longo — e os anexos aqui são portarias com nome extenso — chega inteiro ao bucket
    e volta como ``ClientError: 400 Bad Request``, abortando o upload antes de qualquer
    truncamento. Cortar antes de gravar evita a ida ao storage com uma chave inválida.

    O orçamento sai do próprio campo, não de números fixos: o que sobra é o ``max_length`` (ou
    o limite do storage, o que for menor) menos o diretório, o sufixo e a extensão. O corte é
    feito em caracteres e depois em bytes, porque o limite do storage é em bytes e cada acento
    ocupa dois. O nome de exibição não se perde: ``nome_original`` guarda o que foi enviado.
    """
    campo = RolSaberCompetenciaAnexo._meta.get_field('arquivo')
    raiz, extensao = os.path.splitext(os.path.basename(nome))
    reservado = TAMANHO_SUFIXO_UUID + len(extensao)
    limite_caracteres = max(campo.max_length - len(f'{campo.upload_to}/') - reservado, 1)
    limite_bytes = max(LIMITE_BYTES_SEGMENTO_STORAGE - reservado, 1)

    raiz = raiz[:limite_caracteres]
    # Fatiar os bytes pode partir um caractere multibyte ao meio; `ignore` descarta o pedaço.
    raiz = raiz.encode('utf-8')[:limite_bytes].decode('utf-8', 'ignore')
    return f'{raiz}{extensao}'


def _gravar_anexo(request, processo, item, arquivo, nome_original, descricao, papel, pontuacao):
    """Cria o anexo do item e sobe o arquivo para o storage.

    Em item temporal a pontuação vem do período informado; nos demais, da pontuação que o
    servidor digitou (``pontuacao``).
    """
    dados = {
        'processo': processo,
        'rol_saber_competencia': item,
        'arquivo': arquivo,
        'nome_original': nome_original,
        'descricao': descricao,
        'papel': papel,
    }
    if not item.item_temporal:
        return RolSaberCompetenciaAnexo.objects.create(pontuacao=pontuacao, **dados)

    anexo = RolSaberCompetenciaAnexo(
        data_inicio=_parse_date(request.POST.get('data_inicio')),
        data_fim=_parse_date(request.POST.get('data_fim')),
        **dados,
    )
    anexo.pontuacao = anexo.calcular_pontuacao_temporal()
    anexo.save()
    return anexo


@login_required
@require_GET
def resumo_preenchimento(request, processo_id):
    processo = get_object_or_404(ProcessoRSCTae, pk=processo_id)
    _validar_acesso_processo_leitura(request, processo)

    ctx = _montar_resumo_preenchimento(processo)
    html = render_to_string('rsc_tae/partials/resumo_preenchimento.html', ctx, request=request)
    return JsonResponse({'ok': True, 'html': html})


@login_required
@require_GET
def memorial_descritivo(request, processo_id):
    processo = get_object_or_404(ProcessoRSCTae, pk=processo_id)
    _validar_acesso_processo_leitura(request, processo)

    ctx = montar_contexto_memorial(request, processo)
    html = render_to_string('rsc_tae/partials/memorial_descritivo.html', ctx, request=request)
    return JsonResponse({'ok': True, 'html': html})


@login_required
@require_POST
def salvar_quantidade_item(request, processo_id, item_id):
    processo = get_object_or_404(ProcessoRSCTae, pk=processo_id)

    vinculo = _validar_acesso_processo(request, processo)

    if not PermissoesProcesso(request, processo).pode_editar_preenchimento:
        return JsonResponse({'ok': False, 'msg': 'Não é possível alterar o preenchimento após concluir.'}, status=403)

    item = get_object_or_404(RolSaberCompetencia.objects.select_related('grupo__requisito'), pk=item_id, ativo=True)

    raw_value = (request.POST.get('quantidade') or '').strip()
    if raw_value == '':
        quantidade = 0
    else:
        try:
            quantidade = int(raw_value)
        except ValueError:
            return JsonResponse({'ok': False, 'msg': 'Quantidade inválida.'}, status=400)
        if quantidade < 0:
            return JsonResponse({'ok': False, 'msg': 'Quantidade deve ser maior ou igual a zero.'}, status=400)

    with transaction.atomic():
        # select_for_update() bloqueia a linha existente antes de atualizar,
        # evitando race condition em requisições simultâneas do mesmo servidor.
        try:
            obj = RolSaberCompetenciaPreenchimento.objects.select_for_update().get(vinculo=vinculo, rol_saber_competencia=item)
            obj.quantidade = quantidade
            obj.save(update_fields=['quantidade'])
        except RolSaberCompetenciaPreenchimento.DoesNotExist:
            try:
                RolSaberCompetenciaPreenchimento.objects.create(vinculo=vinculo, rol_saber_competencia=item, quantidade=quantidade)
            except IntegrityError:
                # Outra requisição criou o registro simultaneamente; atualiza agora.
                RolSaberCompetenciaPreenchimento.objects.filter(vinculo=vinculo, rol_saber_competencia=item).update(quantidade=quantidade)

    itens = RolSaberCompetencia.objects.filter(ativo=True).select_related('grupo__requisito').order_by('numero')
    preenchimentos = RolSaberCompetenciaPreenchimento.objects.filter(vinculo=processo.vinculo, rol_saber_competencia__in=itens)
    preenchimento_por_item_id = {p.rol_saber_competencia_id: p for p in preenchimentos}
    anexos_por_item_id = anexos_por_item(processo, itens)
    resumo = _calcular_resumo_por_pontos(processo, itens, preenchimento_por_item_id, anexos_por_item_id)

    pontuacao_total = (item.pontuacao_unidade or Decimal('0')) * Decimal(quantidade)

    return JsonResponse(
        {
            'ok': True,
            'item_id': item.id,
            'quantidade': quantidade,
            'pontuacao_total': str(pontuacao_total),
            'resumo': {
                'total_pontos': str(resumo['total_pontos']),
                'pontos_minimos': str(resumo['pontos_minimos']),
                'pontos_percent': resumo['pontos_percent'],
                'itens_preenchidos': resumo['itens_preenchidos'],
                'itens_minimos': resumo['itens_minimos'],
                'itens_percent': resumo['itens_percent'],
                'requisito_obrigatorio': status_requisitos_obrigatorios(processo),
                'pontos_por_requisito': pontos_por_requisito(processo),
            },
        }
    )


@login_required
@require_GET
def listar_anexos_item(request, processo_id, item_id):
    processo = get_object_or_404(ProcessoRSCTae, pk=processo_id)
    _validar_acesso_processo(request, processo)
    item = get_object_or_404(RolSaberCompetencia.objects.select_related('grupo__requisito'), pk=item_id, ativo=True)

    anexos = RolSaberCompetenciaAnexo.objects.filter(processo=processo, rol_saber_competencia=item).order_by('-data_cadastro')
    data = []
    for a in anexos:
        item_data = {
            'id': a.id,
            'nome': a.nome_original or (a.arquivo.name if a.arquivo else ''),
            'url': a.arquivo.url if a.arquivo else '',
            'pontuacao': str(getattr(a, 'pontuacao', None) or Decimal('0')),
            'descricao': a.descricao or '',
        }
        if item.item_temporal:
            item_data['data_inicio'] = a.data_inicio.strftime('%Y-%m-%d') if a.data_inicio else ''
            item_data['data_fim'] = a.data_fim.strftime('%Y-%m-%d') if a.data_fim else ''
            item_data['periodo_display'] = a.periodo_display
        if item.aceita_papel:
            item_data['papel'] = a.papel or ''
        data.append(item_data)

    anexos_do_item = anexos
    pontuacao_total_item = pontos_item_anexos(item, anexos_do_item)

    itens = RolSaberCompetencia.objects.filter(ativo=True).select_related('grupo__requisito').order_by('numero')
    preenchimentos = RolSaberCompetenciaPreenchimento.objects.filter(vinculo=processo.vinculo, rol_saber_competencia__in=itens)
    preenchimento_por_item_id = {p.rol_saber_competencia_id: p for p in preenchimentos}
    anexos_por_item_id = anexos_por_item(processo, itens)
    resumo = _calcular_resumo_por_pontos(processo, itens, preenchimento_por_item_id, anexos_por_item_id)

    return JsonResponse(
        {
            'ok': True,
            'item_temporal': bool(item.item_temporal),
            'aceita_papel': bool(item.aceita_papel),
            'anexos': data,
            'pontuacao_total_item': str(pontuacao_total_item),
            'resumo': {
                'total_pontos': str(resumo['total_pontos']),
                'pontos_minimos': str(resumo['pontos_minimos']),
                'pontos_percent': resumo['pontos_percent'],
                'itens_preenchidos': resumo['itens_preenchidos'],
                'itens_minimos': resumo['itens_minimos'],
                'itens_percent': resumo['itens_percent'],
                'requisito_obrigatorio': status_requisitos_obrigatorios(processo),
                'pontos_por_requisito': pontos_por_requisito(processo),
            },
        }
    )


@login_required
@require_POST
def upload_anexo_item(request, processo_id, item_id):
    processo = get_object_or_404(ProcessoRSCTae, pk=processo_id)
    _validar_acesso_processo(request, processo)

    if not PermissoesProcesso(request, processo).pode_editar_preenchimento:
        return JsonResponse({'ok': False, 'msg': 'Não é possível adicionar anexos após concluir o preenchimento.'}, status=403)

    item = get_object_or_404(RolSaberCompetencia.objects.select_related('grupo__requisito'), pk=item_id, ativo=True)

    arquivo = request.FILES.get('arquivo')
    if not arquivo:
        return JsonResponse({'ok': False, 'msg': 'Nenhum arquivo enviado.'}, status=400)

    erro_pdf = _erro_arquivo_nao_pdf(arquivo)
    if erro_pdf:
        return JsonResponse({'ok': False, 'msg': erro_pdf}, status=400)

    # Descrição é opcional no upload (o arquivo sobe na hora); passa a ser
    # preenchida no card "Documentos anexados" e é exigida apenas na conclusão.
    descricao = (request.POST.get('descricao') or '').strip()

    # Papel (titular/substituto) é opcional no upload; só capturado em itens do Requisito V.
    papel, erro_papel = _extrair_papel(request, item)
    if erro_papel:
        return JsonResponse({'ok': False, 'msg': erro_papel}, status=400)

    pontuacao = None
    if not item.item_temporal:
        pontuacao, erro_pontuacao = _parse_pontuacao_manual(request)
        if erro_pontuacao:
            return JsonResponse({'ok': False, 'msg': erro_pontuacao}, status=400)

    # O nome de exibição é o que o servidor enviou; o do storage é a versão encurtada.
    campo_nome_original = RolSaberCompetenciaAnexo._meta.get_field('nome_original')
    nome_original = (getattr(arquivo, 'name', '') or '')[: campo_nome_original.max_length]
    arquivo.name = _encurtar_nome_enviado(nome_original)

    try:
        anexo = _gravar_anexo(request, processo, item, arquivo, nome_original, descricao, papel, pontuacao)
    except ERROS_DE_STORAGE:
        # Sem este tratamento a falha vira um 500 sem mensagem no AJAX e arrasta os handlers de
        # signal da requisição para TransactionManagementError. Só as falhas de escrita são
        # absorvidas: erro de domínio ou bug de programação continua subindo, para não virar
        # "não foi possível armazenar o arquivo" e esconder a causa real.
        logger.exception('Falha ao gravar o anexo do item %s no processo %s.', item.pk, processo.pk)
        return JsonResponse(
            {'ok': False, 'msg': 'Não foi possível armazenar o arquivo. Tente novamente em alguns instantes.'},
            status=502,
        )

    anexos_do_item = RolSaberCompetenciaAnexo.objects.filter(processo=processo, rol_saber_competencia=item)
    pontuacao_total_item = pontos_item_anexos(item, anexos_do_item)

    itens = RolSaberCompetencia.objects.filter(ativo=True).select_related('grupo__requisito').order_by('numero')
    preenchimentos = RolSaberCompetenciaPreenchimento.objects.filter(vinculo=processo.vinculo, rol_saber_competencia__in=itens)
    preenchimento_por_item_id = {p.rol_saber_competencia_id: p for p in preenchimentos}
    anexos_por_item_id = anexos_por_item(processo, itens)
    resumo = _calcular_resumo_por_pontos(processo, itens, preenchimento_por_item_id, anexos_por_item_id)

    anexo_data = {
        'id': anexo.id,
        'nome': anexo.nome_original or (anexo.arquivo.name if anexo.arquivo else ''),
        'url': anexo.arquivo.url if anexo.arquivo else '',
        'pontuacao': str(anexo.pontuacao or Decimal('0')),
        'descricao': anexo.descricao or '',
    }
    if item.item_temporal:
        anexo_data['data_inicio'] = anexo.data_inicio.strftime('%Y-%m-%d') if anexo.data_inicio else ''
        anexo_data['data_fim'] = anexo.data_fim.strftime('%Y-%m-%d') if anexo.data_fim else ''
        anexo_data['periodo_display'] = anexo.periodo_display
    if item.aceita_papel:
        anexo_data['papel'] = anexo.papel or ''

    return JsonResponse(
        {
            'ok': True,
            'item_temporal': bool(item.item_temporal),
            'anexo': anexo_data,
            'pontuacao_total_item': str(pontuacao_total_item),
            'resumo': {
                'total_pontos': str(resumo['total_pontos']),
                'pontos_minimos': str(resumo['pontos_minimos']),
                'pontos_percent': resumo['pontos_percent'],
                'itens_preenchidos': resumo['itens_preenchidos'],
                'itens_minimos': resumo['itens_minimos'],
                'itens_percent': resumo['itens_percent'],
                'requisito_obrigatorio': status_requisitos_obrigatorios(processo),
                'pontos_por_requisito': pontos_por_requisito(processo),
            },
        }
    )


@login_required
@require_POST
def salvar_pontuacao_anexo(request, processo_id, anexo_id):
    processo = get_object_or_404(ProcessoRSCTae, pk=processo_id)
    _validar_acesso_processo(request, processo)

    if not PermissoesProcesso(request, processo).pode_editar_preenchimento:
        return JsonResponse({'ok': False, 'msg': 'Não é possível alterar pontuações após concluir o preenchimento.'}, status=403)

    anexo = get_object_or_404(RolSaberCompetenciaAnexo, pk=anexo_id, processo=processo)
    item_id = anexo.rol_saber_competencia_id
    item = get_object_or_404(RolSaberCompetencia.objects.select_related('grupo__requisito'), pk=item_id, ativo=True)

    erro_papel = _aplicar_papel_edicao(request, item, anexo)
    if erro_papel:
        return JsonResponse({'ok': False, 'msg': erro_papel}, status=400)

    if item.item_temporal:
        data_inicio = _parse_date(request.POST.get('data_inicio'))
        data_fim = _parse_date(request.POST.get('data_fim'))
        anexo.data_inicio = data_inicio
        anexo.data_fim = data_fim
        anexo.pontuacao = anexo.calcular_pontuacao_temporal()
        anexo.save(update_fields=['data_inicio', 'data_fim', 'pontuacao'])
        pontuacao = anexo.pontuacao
    else:
        raw = (request.POST.get('pontuacao') or '').strip().replace(',', '.')
        if raw == '':
            pontuacao = Decimal('0')
        else:
            try:
                pontuacao = Decimal(raw)
            except InvalidOperation:
                return JsonResponse({'ok': False, 'msg': 'Pontuação inválida.'}, status=400)
            if pontuacao < 0:
                return JsonResponse({'ok': False, 'msg': 'Pontuação deve ser maior ou igual a zero.'}, status=400)

        RolSaberCompetenciaAnexo.objects.filter(pk=anexo.pk).update(pontuacao=pontuacao)

    anexos_do_item = RolSaberCompetenciaAnexo.objects.filter(processo=processo, rol_saber_competencia=item)
    pontuacao_total_item = pontos_item_anexos(item, anexos_do_item)

    itens = RolSaberCompetencia.objects.filter(ativo=True).select_related('grupo__requisito').order_by('numero')
    preenchimentos = RolSaberCompetenciaPreenchimento.objects.filter(vinculo=processo.vinculo, rol_saber_competencia__in=itens)
    preenchimento_por_item_id = {p.rol_saber_competencia_id: p for p in preenchimentos}
    anexos_por_item_id = anexos_por_item(processo, itens)
    resumo = _calcular_resumo_por_pontos(processo, itens, preenchimento_por_item_id, anexos_por_item_id)

    response_data = {
        'ok': True,
        'anexo_id': anexo.id,
        'pontuacao': str(pontuacao),
        'item_id': item_id,
        'pontuacao_total_item': str(pontuacao_total_item),
        'resumo': {
            'total_pontos': str(resumo['total_pontos']),
            'pontos_minimos': str(resumo['pontos_minimos']),
            'pontos_percent': resumo['pontos_percent'],
            'itens_preenchidos': resumo['itens_preenchidos'],
            'itens_minimos': resumo['itens_minimos'],
            'itens_percent': resumo['itens_percent'],
            'requisito_obrigatorio': status_requisitos_obrigatorios(processo),
            'pontos_por_requisito': pontos_por_requisito(processo),
        },
    }
    if item.item_temporal:
        response_data['periodo_display'] = anexo.periodo_display
    if item.aceita_papel:
        response_data['papel'] = anexo.papel or ''

    return JsonResponse(response_data)


@login_required
@require_POST
def salvar_descricao_anexo(request, processo_id, anexo_id):
    processo = get_object_or_404(ProcessoRSCTae, pk=processo_id)
    _validar_acesso_processo(request, processo)

    if not PermissoesProcesso(request, processo).pode_editar_preenchimento:
        return JsonResponse({'ok': False, 'msg': 'Não é possível alterar a descrição após concluir o preenchimento.'}, status=403)

    anexo = get_object_or_404(RolSaberCompetenciaAnexo, pk=anexo_id, processo=processo)

    descricao = (request.POST.get('descricao') or '').strip()
    if not descricao:
        return JsonResponse({'ok': False, 'msg': 'A descrição do documento é obrigatória.'}, status=400)

    RolSaberCompetenciaAnexo.objects.filter(pk=anexo.pk).update(descricao=descricao)
    return JsonResponse({'ok': True, 'anexo_id': anexo.id, 'descricao': descricao})


@login_required
@require_POST
def salvar_memorial(request, processo_id):
    """Autosave da introdução e/ou conclusão do memorial descritivo (só campos enviados)."""
    from rsc_tae.models import MemorialDescritivoRSCTae

    processo = get_object_or_404(ProcessoRSCTae, pk=processo_id)
    _validar_acesso_processo(request, processo)

    if not PermissoesProcesso(request, processo).pode_editar_preenchimento:
        return JsonResponse({'ok': False, 'msg': 'Não é possível alterar o memorial após concluir o preenchimento.'}, status=403)

    defaults = {}
    if 'introducao' in request.POST:
        defaults['introducao'] = (request.POST.get('introducao') or '').strip()
    if 'conclusao' in request.POST:
        defaults['conclusao'] = (request.POST.get('conclusao') or '').strip()
    if not defaults:
        return JsonResponse({'ok': False, 'msg': 'Nada a salvar.'}, status=400)

    MemorialDescritivoRSCTae.objects.update_or_create(processo=processo, defaults=defaults)
    return JsonResponse({'ok': True})


@login_required
@require_POST
def excluir_anexo_item(request, processo_id, anexo_id):
    processo = get_object_or_404(ProcessoRSCTae, pk=processo_id)
    _validar_acesso_processo(request, processo)

    if not PermissoesProcesso(request, processo).pode_editar_preenchimento:
        return JsonResponse({'ok': False, 'msg': 'Não é possível excluir anexos após concluir o preenchimento.'}, status=403)

    anexo = get_object_or_404(RolSaberCompetenciaAnexo, pk=anexo_id, processo=processo)
    item_id = anexo.rol_saber_competencia_id

    if getattr(anexo, 'arquivo', None):
        try:
            anexo.arquivo.delete(save=False)
        except Exception:
            logger.exception('Erro ao excluir arquivo do anexo %s (processo %s)', anexo.pk, processo_id)
            return JsonResponse({'ok': False, 'msg': 'Não foi possível remover o arquivo do anexo.'}, status=500)

    anexo.delete()

    item = get_object_or_404(RolSaberCompetencia.objects.select_related('grupo__requisito'), pk=item_id, ativo=True)
    anexos_do_item = RolSaberCompetenciaAnexo.objects.filter(processo=processo, rol_saber_competencia=item)
    pontuacao_total_item = pontos_item_anexos(item, anexos_do_item)

    itens = RolSaberCompetencia.objects.filter(ativo=True).select_related('grupo__requisito').order_by('numero')
    preenchimentos = RolSaberCompetenciaPreenchimento.objects.filter(vinculo=processo.vinculo, rol_saber_competencia__in=itens)
    preenchimento_por_item_id = {p.rol_saber_competencia_id: p for p in preenchimentos}
    anexos_por_item_id = anexos_por_item(processo, itens)
    resumo = _calcular_resumo_por_pontos(processo, itens, preenchimento_por_item_id, anexos_por_item_id)

    return JsonResponse(
        {
            'ok': True,
            'pontuacao_total_item': str(pontuacao_total_item),
            'resumo': {
                'total_pontos': str(resumo['total_pontos']),
                'pontos_minimos': str(resumo['pontos_minimos']),
                'pontos_percent': resumo['pontos_percent'],
                'itens_preenchidos': resumo['itens_preenchidos'],
                'itens_minimos': resumo['itens_minimos'],
                'itens_percent': resumo['itens_percent'],
                'requisito_obrigatorio': status_requisitos_obrigatorios(processo),
                'pontos_por_requisito': pontos_por_requisito(processo),
            },
        }
    )


@login_required
@require_POST
def upload_documento_preliminar(request, processo_id, tipo):
    """Envia apenas o arquivo do documento preliminar — a data é preenchida depois, via autosave."""
    processo = get_object_or_404(ProcessoRSCTae, pk=processo_id)
    vinculo = _validar_acesso_processo(request, processo)

    if tipo not in dict(TipoDocumentoPreliminar.get_choices()):
        return JsonResponse({'ok': False, 'msg': 'Tipo de documento preliminar inválido.'}, status=400)

    if processo.situacao not in SituacaoProcesso.EDITAVEIS_PELO_SERVIDOR:
        return JsonResponse({'ok': False, 'msg': 'Não é possível enviar documento preliminar nesta situação do processo.'}, status=403)

    form = DocumentoPreliminarUploadForm(request.POST, request.FILES, tipo=tipo)
    if not form.is_valid():
        return JsonResponse({'ok': False, 'msg': 'Não foi possível enviar o arquivo. Verifique o formato.'}, status=400)

    arquivo = form.cleaned_data['arquivo']
    documento = DocumentoPreliminarRSCTae.objects.create(
        processo=processo,
        tipo=tipo,
        arquivo=arquivo,
        nome_original=getattr(arquivo, 'name', '') or '',
        cadastrado_por_vinculo=vinculo,
    )

    DocumentoPreliminarRSCTaeLog.objects.create(
        processo=processo,
        documento=documento,
        acao=DocumentoPreliminarRSCTaeLog.ACAO_ENVIO,
        executado_por_vinculo=vinculo,
        ip=get_client_ip(request),
        user_agent=(request.META.get('HTTP_USER_AGENT') or '')[:255],
        observacao=f'Documento preliminar enviado: {documento.nome_original}',
    )

    return JsonResponse(
        {
            'ok': True,
            'documento': {
                'id': documento.id,
                'nome': documento.nome_original,
                'url': documento.arquivo.url if documento.arquivo else '',
                'data_obtencao_titulacao': '',
                'situacao_display': 'Pendente',
            },
        }
    )


@login_required
@require_POST
def salvar_data_documento_preliminar(request, processo_id, documento_id):
    processo = get_object_or_404(ProcessoRSCTae, pk=processo_id)
    _validar_acesso_processo(request, processo)

    if processo.situacao not in SituacaoProcesso.EDITAVEIS_PELO_SERVIDOR:
        return JsonResponse({'ok': False, 'msg': 'Não é possível alterar a data nesta situação do processo.'}, status=403)

    documento = get_object_or_404(DocumentoPreliminarRSCTae, pk=documento_id, processo=processo)
    data = _parse_date(request.POST.get('data_obtencao_titulacao'))

    DocumentoPreliminarRSCTae.objects.filter(pk=documento.pk).update(data_obtencao_titulacao=data)
    return JsonResponse(
        {
            'ok': True,
            'documento_id': documento.id,
            'data_obtencao_titulacao': data.strftime('%Y-%m-%d') if data else '',
        }
    )


@login_required
@require_POST
def avaliacao_salvar_pontuacao_anexo(request, processo_id, anexo_id):
    # Mantém endpoint usado na tela de avaliar (ajuste da pontuação do anexo durante avaliação)
    processo = get_object_or_404(ProcessoRSCTae, pk=processo_id)
    _validar_acesso_avaliacao(request, processo)

    anexo = get_object_or_404(RolSaberCompetenciaAnexo, pk=anexo_id, processo=processo)

    raw = (request.POST.get('pontuacao') or '').strip().replace(',', '.')
    if raw == '':
        pontuacao = Decimal('0')
    else:
        try:
            pontuacao = Decimal(raw)
        except InvalidOperation:
            return JsonResponse({'ok': False, 'msg': 'Pontuação inválida.'}, status=400)
        if pontuacao < 0:
            return JsonResponse({'ok': False, 'msg': 'Pontuação deve ser maior ou igual a zero.'}, status=400)

    RolSaberCompetenciaAnexo.objects.filter(pk=anexo.pk).update(pontuacao=pontuacao)

    item_id = anexo.rol_saber_competencia_id
    item = get_object_or_404(RolSaberCompetencia.objects.select_related('grupo__requisito'), pk=item_id, ativo=True)
    anexos_do_item = RolSaberCompetenciaAnexo.objects.filter(processo=processo, rol_saber_competencia=item)
    pontuacao_total_item = pontos_item_anexos(item, anexos_do_item)

    return JsonResponse(
        {
            'ok': True,
            'anexo_id': anexo.id,
            'pontuacao': str(pontuacao),
            'item_id': item_id,
            'pontuacao_total_item': str(pontuacao_total_item),
        }
    )
