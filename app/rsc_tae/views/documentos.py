"""Geração de documentos PDF para o módulo RSC-TAE.

Cada view abaixo gera um documento usado pelo processo eletrônico:

    1. requerimento_pdf            — Requerimento de RSC-TAE (servidor)
    2. formulario_pontuacao_pdf    — Formulário de Pontuação Requerida
    3. memorial_pdf                — Memorial Descritivo
    4. processo_completo_pdf       — Bundle (concatenação) de todas as peças
    5. parecer_pdf                 — Parecer Conclusivo da Comissão
    6. minuta_portaria_pdf         — Minuta de Portaria de Concessão (deferido)

Permissões: todos usam ``_validar_acesso_resumo_avaliacao`` (dono + RH + avaliadores).
Documentos formais (parecer/deliberação/portaria) checam adicionalmente a situação do processo.
"""

import datetime
import io
import logging
import os
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.formats import number_format
from django.views.decorators.http import require_GET

from djtools.utils.pdf import documento
from djtools.utils.response import httprr, rtr
from rsc_tae.enums import MotivoIndeferimento, SituacaoProcesso
from rsc_tae.models import (
    DeliberacaoCRSCRSCTae,
    MemorialDescritivoRSCTae,
    ProcessoRSCTae,
    Requisito,
    RolSaberCompetenciaAnexo,
    VotoDeliberacaoFinalRSCTae,
)

from ._helpers import (
    _documentos_preliminares_atuais,
    _enriquecer_anexos_memorial,
    _listar_divergencias_para_crsc,
    _montar_contexto_avaliacao,
    _montar_resumo_preenchimento,
    _validar_acesso_resumo_avaliacao,
    data_exercicio_cargo_efetiva,
    injetar_visibilidade_avaliadores,
    quantidade_deliberacoes_item,
    resumo_final_consolidado,
    status_deliberacao_final,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _motivos_indeferimento_parecer(processo: ProcessoRSCTae, resumo_final: dict) -> list[str]:
    """Constatações de indeferimento do parecer, com a redação do Decreto nº 13.048/2026.

    Usa a união distinta dos motivos consolidados na deliberação da CRSC; os valores
    dinâmicos (pontos/critérios alcançados vs. exigidos e incisos obrigatórios do art. 3º)
    são preenchidos com o consolidado final. Processos deliberados antes da existência dos
    motivos estruturados retornam lista vazia — o template mantém o fallback do texto livre.
    """
    deliberacao = DeliberacaoCRSCRSCTae.objects.filter(processo=processo).first()
    codigos = [int(m) for m in (getattr(deliberacao, 'motivos_indeferimento', None) or [])]
    if not codigos:
        return []

    nivel = processo.nivel_requisitado
    try:
        incisos = _juntar_com_e([(r.numeral_romano or r.descricao_curta) for r in nivel.requisitos_obrigatorios.order_by('numero')])
    except Exception:
        logger.exception('Erro ao obter requisitos obrigatórios do nível %s para o parecer', nivel)
        incisos = ''

    valores = {
        'sigla': nivel.ordem_romana,
        'pontos': number_format(resumo_final['total_pontos'] or Decimal('0'), decimal_pos=2),
        'itens': resumo_final['itens_validados'],
        'pontos_min': number_format(resumo_final['pontos_requeridos'] or Decimal('0'), decimal_pos=2),
        'itens_min': resumo_final['itens_requeridos'],
        'incisos': incisos,
    }
    return [MotivoIndeferimento.TEXTOS_PARECER[codigo].format(**valores) for codigo in codigos if codigo in MotivoIndeferimento.TEXTOS_PARECER]


def _juntar_com_e(itens):
    """Junta uma lista em texto no padrão 'A, B e C' (usa 'e' antes do último item)."""
    itens = [str(i) for i in itens if i]
    if not itens:
        return ''
    if len(itens) == 1:
        return itens[0]
    return ', '.join(itens[:-1]) + ' e ' + itens[-1]


def _pontuacao_final_consolidada(processo):
    """Pontuação/itens finais do processo (temporal + consolidação da CRSC) e requisitos atendidos.

    Fonte única de verdade para os documentos que declaram a DECISÃO final (parecer/deliberação):
    usa ``resumo_final_consolidado`` (que soma unidades por item, converte item temporal em anos e
    aplica as notas consolidadas das deliberações de item da CRSC).
    """
    from rsc_tae.models import RolSaberCompetencia
    from rsc_tae.views._helpers import _pontos_finais_por_item

    divergencias = _listar_divergencias_para_crsc(processo)
    resumo = resumo_final_consolidado(processo, divergencias)
    consolidado_por_anexo = {
        d['anexo'].id: d['status_deliberacao']['nota_consolidada']
        for d in divergencias
        if d['status_deliberacao']['fechado'] and d['status_deliberacao']['nota_consolidada'] is not None
    }
    pontos_por_item = _pontos_finais_por_item(processo, consolidado_por_anexo)
    itens_ok = [iid for iid, pts in pontos_por_item.items() if pts > 0]
    requisitos = {}
    for item in RolSaberCompetencia.objects.filter(id__in=itens_ok).select_related('grupo__requisito'):
        req = getattr(getattr(item, 'grupo', None), 'requisito', None)
        if req:
            requisitos[req.numero] = req.numeral_romano
    return {'resumo': resumo, 'requisitos_atendidos': [requisitos[k] for k in sorted(requisitos)]}


def _votos_finais_crsc(processo):
    """Votos da deliberação final da CRSC (um por membro; inclui o voto de desempate)."""
    return list(
        VotoDeliberacaoFinalRSCTae.objects.filter(processo=processo)
        .select_related('deliberado_por_vinculo__pessoa')
        .order_by('desempate', 'data_deliberacao')
    )


def _membros_crsc_deliberantes(processo):
    """Lista dos membros da CRSC que registraram voto na deliberação final (nome + se é desempate).

    São os responsáveis pela decisão de deferimento/indeferimento — assinam o parecer e a
    deliberação, ao contrário dos avaliadores auxiliares (que só analisam a documentação).
    """
    membros = []
    for voto in _votos_finais_crsc(processo):
        vinculo = voto.deliberado_por_vinculo
        pessoa = getattr(vinculo, 'pessoa', None)
        membros.append(
            {
                'nome': str(getattr(pessoa, 'nome', '') or vinculo or '—'),
                'desempate': bool(voto.desempate),
                'hash': voto.assinatura_hash or '',
            }
        )
    return membros


def _dados_servidor(processo):
    """Extrai dados do servidor para preenchimento de cabeçalhos/identificação.

    Retorna dict com chaves: nome, matricula, cpf, cargo, setor, lotacao_uo,
    email, telefone, endereco. Campos ausentes voltam como string vazia.
    """
    vinculo = processo.vinculo
    relacionamento = getattr(vinculo, 'relacionamento', None)
    pessoa = getattr(vinculo, 'pessoa', None)
    pessoa_fisica = getattr(pessoa, 'pessoafisica', None) if pessoa else None

    nome = getattr(pessoa, 'nome', '') or ''
    cpf = getattr(pessoa_fisica, 'cpf', '') or ''
    email = getattr(vinculo, 'email_notificacao', '')

    matricula = getattr(relacionamento, 'matricula', '') or ''
    cargo_obj = getattr(relacionamento, 'cargo_emprego', None)
    cargo = getattr(cargo_obj, 'nome', '') if cargo_obj else ''

    setor = getattr(vinculo, 'setor', None)
    setor_nome = str(setor) if setor else ''
    lotacao_uo = ''
    try:
        if setor and setor.uo:
            lotacao_uo = str(setor.uo)
    except Exception:
        logger.exception('Erro ao obter UO do setor %s', setor)

    telefone = ''
    try:
        if pessoa_fisica and hasattr(pessoa_fisica, 'telefones_pessoais'):
            telefone = pessoa_fisica.telefones_pessoais
    except Exception:
        pass

    endereco = ''
    municipio = ''
    uf = ''
    try:
        endereco_obj = getattr(pessoa_fisica, 'pessoaendereco', None) if pessoa_fisica else None
        if endereco_obj:
            partes = []
            log = getattr(endereco_obj, 'logradouro', '') or ''
            num = getattr(endereco_obj, 'numero', '') or ''
            if log:
                partes.append(log)
            if num:
                partes.append(str(num))
            endereco = ', '.join(partes)
            mun = getattr(endereco_obj, 'municipio', None)
            if mun:
                municipio = getattr(mun, 'nome', '') or ''
                uf = getattr(mun, 'uf', '') or ''
    except Exception:
        logger.exception('Erro ao montar endereço do vínculo %s', vinculo)

    return {
        'nome': nome,
        'matricula': matricula,
        'cpf': cpf,
        'cargo': cargo,
        'setor': setor_nome,
        'lotacao_uo': lotacao_uo,
        'email': email,
        'telefone': telefone,
        'endereco': endereco,
        'municipio': municipio,
        'uf': uf,
    }


def _checar_situacao_minima_para_documentos(processo):
    """Lança PermissionDenied se o processo ainda não chegou em estágio com dados completos.

    Os documentos da fase A (requerimento, formulário, memorial, consolidado) exigem
    que o servidor já tenha concluído o preenchimento — ou seja, situação ≠ 1/7.
    """
    estados_em_preenchimento = (
        SituacaoProcesso.AGUARDANDO_PREENCHIMENTO,
        SituacaoProcesso.AGUARDANDO_CORRECAO,
    )
    if processo.situacao in estados_em_preenchimento:
        raise PermissionDenied('Documento disponível somente após a conclusão do preenchimento do processo.')


# ---------------------------------------------------------------------------
# 1. Requerimento de RSC-TAE (modelo Portaria MEC nº 608/2026)
# ---------------------------------------------------------------------------

# Rótulos ainda sem origem mapeada no modelo de dados. Preenchidos manualmente
# depois; marcados como 'XXX' no documento (ver Portaria MEC nº 608/2026).
_REQUERIMENTO_PENDENTE = 'XXX'
_ROMANOS_RSC = ('I', 'II', 'III', 'IV', 'V', 'VI')


def _montar_criterios_requerimento(linhas_preenchidas: list) -> list:
    """Monta as 6 tabelas de critério (I a VI) da seção 3 da Portaria 608.

    Todos os requisitos ativos são incluídos, mesmo sem itens preenchidos
    (Subtotal zero), para reproduzir o formulário oficial na íntegra.
    """
    linhas_por_requisito: dict = {}
    for linha in linhas_preenchidas:
        requisito = getattr(linha.get('item'), 'requisito', None)
        numero = getattr(requisito, 'numero', None)
        linhas_por_requisito.setdefault(numero, []).append(linha)

    criterios = []
    for requisito in Requisito.objects.filter(ativo=True).order_by('numero'):
        linhas = linhas_por_requisito.get(requisito.numero, [])
        subtotal = sum((linha.get('pontuacao_total') or Decimal('0')) for linha in linhas)
        criterios.append(
            {
                'requisito': requisito,
                'numeral': requisito.numeral_romano,
                'descricao': requisito.descricao,
                'linhas': linhas,
                'subtotal': subtotal,
            }
        )
    return criterios


def _montar_contexto_requerimento_608(processo: ProcessoRSCTae) -> dict:
    """Reúne o contexto do requerimento no modelo padrão da Portaria 608/2026."""
    dados = _dados_servidor(processo)
    resumo = _montar_resumo_preenchimento(processo)
    nivel = processo.nivel_requisitado

    total_itens = resumo.get('total_pontos_itens') or Decimal('0')
    total_com_saldo = resumo.get('total_pontos') or Decimal('0')
    saldo_anterior = resumo.get('saldo_anterior') or Decimal('0')
    pontos_minimos = resumo.get('pontos_minimos') or Decimal('0')
    excedente = total_com_saldo - pontos_minimos if total_com_saldo > pontos_minimos else Decimal('0')

    niveis_rsc = [{'romano': romano, 'marcado': (ordem + 1) == nivel.ordem} for ordem, romano in enumerate(_ROMANOS_RSC)]

    # Seção 1 — dados buscados no cadastro do servidor (rh).
    servidor = getattr(processo.vinculo, 'relacionamento', None)
    classe = getattr(getattr(servidor, 'cargo_classe', None), 'codigo', '') or ''
    funcao_obj = getattr(servidor, 'funcao', None)

    return {
        'title': 'Requerimento de RSC-TAE',
        'processo': processo,
        'dados': dados,
        'nivel': nivel,
        # Seção 1 — Identificação do servidor.
        # Data de ingresso no cargo = a mesma validada pela comissão (data de exercício no cargo).
        'data_ingresso': data_exercicio_cargo_efetiva(processo),
        'funcao': str(funcao_obj) if funcao_obj else '',
        'nivel_classificacao': classe,
        # Seção 2 — informações do requerimento.
        'niveis_rsc': niveis_rsc,
        'pontos_minimos': pontos_minimos,
        'total_apresentada': total_itens,
        'total_com_saldo': total_com_saldo,
        'qtd_criterios': resumo.get('itens_preenchidos') or 0,
        'excedente': excedente,
        'saldo_anterior': saldo_anterior,
        'num_processo_anterior': _REQUERIMENTO_PENDENTE,
        # Seção 3 — descrição das atividades por requisito legal (Critérios I a VI).
        'criterios': _montar_criterios_requerimento(resumo['linhas_preenchidas']),
        'assinatura_hash': processo.assinatura_preenchimento_hash or '',
        'hoje': datetime.date.today(),
    }


def anexar_requerimento_ao_processo(processo) -> bool:
    """Gera o requerimento (modelo Portaria 608) e o anexa ao processo como snapshot.

    Chamado na conclusão do preenchimento. Best-effort: falhas de renderização são
    logadas e não interrompem o fluxo (o documento continua disponível sob demanda).

    Returns:
        True se o snapshot foi gerado e anexado; False em caso de falha.
    """
    from django.core.files.base import ContentFile

    from djtools.utils.pdf import generate_pdf

    try:
        contexto = _montar_contexto_requerimento_608(processo)
        buffer = generate_pdf('rsc_tae/documentos/requerimento_pdf.html', context=contexto)
        nome = f'requerimento_rsc_tae_{processo.pk}.pdf'
        processo.requerimento_arquivo.save(nome, ContentFile(buffer.getvalue()), save=False)
        ProcessoRSCTae.objects.filter(pk=processo.pk).update(requerimento_arquivo=processo.requerimento_arquivo.name)
    except Exception:
        logger.exception('Falha ao gerar/anexar o requerimento do processo %s', processo.pk)
        return False
    return True


@documento()
@rtr('rsc_tae/documentos/requerimento_pdf.html')
@login_required
@require_GET
def requerimento_pdf(request, processo_id):
    processo = get_object_or_404(ProcessoRSCTae, pk=processo_id)
    _validar_acesso_resumo_avaliacao(request, processo)
    _checar_situacao_minima_para_documentos(processo)
    return _montar_contexto_requerimento_608(processo)


# ---------------------------------------------------------------------------
# 2. Formulário de Pontuação Requerida
# ---------------------------------------------------------------------------


@documento()
@rtr('rsc_tae/documentos/formulario_pontuacao_pdf.html')
@login_required
@require_GET
def formulario_pontuacao_pdf(request, processo_id):
    title = 'Formulário de Pontuação Requerida — RSC-TAE'
    processo = get_object_or_404(ProcessoRSCTae, pk=processo_id)
    _validar_acesso_resumo_avaliacao(request, processo)
    _checar_situacao_minima_para_documentos(processo)

    dados = _dados_servidor(processo)
    resumo = _montar_resumo_preenchimento(processo)
    nivel = processo.nivel_requisitado

    return {
        'title': title,
        'processo': processo,
        'dados': dados,
        'nivel': nivel,
        'grupos_requisito': resumo['grupos_requisito'],
        'total_pontos': resumo['total_pontos'],
        'total_pontos_itens': resumo['total_pontos_itens'],
        'saldo_anterior': resumo['saldo_anterior'],
        'pontos_minimos': resumo['pontos_minimos'],
        'itens_preenchidos': resumo['itens_preenchidos'],
        'itens_minimos': resumo['itens_minimos'],
        'assinatura_hash': processo.assinatura_preenchimento_hash or '',
        'hoje': datetime.date.today(),
    }


# ---------------------------------------------------------------------------
# 3. Memorial Descritivo
# ---------------------------------------------------------------------------


@documento()
@rtr('rsc_tae/documentos/memorial_pdf.html')
@login_required
@require_GET
def memorial_pdf(request, processo_id):
    title = 'Memorial Descritivo — RSC-TAE'
    processo = get_object_or_404(ProcessoRSCTae, pk=processo_id)
    _validar_acesso_resumo_avaliacao(request, processo)

    memorial = MemorialDescritivoRSCTae.objects.filter(processo=processo).first()
    if not memorial or not (memorial.conclusao or '').strip():
        raise PermissionDenied('O memorial descritivo ainda não foi preenchido pelo servidor.')

    dados = _dados_servidor(processo)
    resumo = _montar_resumo_preenchimento(processo)
    grupos_requisito = resumo['grupos_requisito']
    _enriquecer_anexos_memorial(grupos_requisito)

    # Data fixa do documento: quando o processo entrou em "Aguardando Deliberação da CRSC"
    # (publicação do memorial no portal). Antes disso o memorial ainda é rascunho — usa a data atual.
    if processo.data_entrada_crsc:
        data_memorial = processo.data_entrada_crsc.date()
    else:
        data_memorial = datetime.date.today()

    return {
        'title': title,
        'processo': processo,
        'dados': dados,
        'nivel': processo.nivel_requisitado,
        'memorial': memorial,
        'grupos_requisito': grupos_requisito,
        'total_pontos': resumo['total_pontos'],
        'assinatura_hash': processo.assinatura_preenchimento_hash or '',
        'data_memorial': data_memorial,
    }


# ---------------------------------------------------------------------------
# 5. Parecer Conclusivo
# ---------------------------------------------------------------------------


@documento()
@rtr('rsc_tae/documentos/parecer_pdf.html')
@login_required
@require_GET
def parecer_pdf(request, processo_id):
    title = 'Parecer Conclusivo — RSC-TAE'
    processo = get_object_or_404(ProcessoRSCTae, pk=processo_id)
    _validar_acesso_resumo_avaliacao(request, processo)

    if processo.situacao not in SituacaoProcesso.FINAIS:
        raise PermissionDenied('Parecer disponível apenas para processos finalizados (deferidos ou indeferidos).')

    ctx = _montar_contexto_avaliacao(request, processo, title=title)
    injetar_visibilidade_avaliadores(request, processo, ctx)
    dados = _dados_servidor(processo)

    deferido = processo.situacao == SituacaoProcesso.DEFERIDO
    rsc_equivalente = processo.rsc_equivalente() if deferido else ''
    nivel = processo.nivel_requisitado

    # Pontuação/itens FINAIS = consolidado da CRSC (temporal + deliberações de item), não a média
    # bruta dos avaliadores auxiliares. Sobrescreve os totais do contexto para o texto do parecer.
    consolidado = _pontuacao_final_consolidada(processo)
    resumo_final = consolidado['resumo']
    ctx['total_pontos_validados'] = resumo_final['total_pontos']
    ctx['itens_validados'] = resumo_final['itens_validados']
    ctx['pontos_requeridos_nivel'] = resumo_final['pontos_requeridos']
    ctx['itens_requeridos'] = resumo_final['itens_requeridos']
    saldo_pontos = max(Decimal('0'), resumo_final['total_pontos'] - resumo_final['pontos_requeridos'])

    return {
        **ctx,
        'title': title,
        'dados': dados,
        'deferido': deferido,
        'rsc_equivalente': rsc_equivalente,
        'nivel': nivel,
        'saldo_pontos': saldo_pontos,
        'motivos_parecer': [] if deferido else _motivos_indeferimento_parecer(processo, resumo_final),
        'requisitos_atendidos_txt': _juntar_com_e(consolidado['requisitos_atendidos']),
        'numero_processo_eletronico': str(processo.processo_eletronico) if processo.processo_eletronico_id else '',
        'data_efeitos_financeiros': processo.data_finalizacao_avaliacao,
        'membros_crsc': _membros_crsc_deliberantes(processo),
        'hoje': datetime.date.today(),
    }


# ---------------------------------------------------------------------------
# 5b. Deliberação da CRSC (votos finais + deliberações por item)
# ---------------------------------------------------------------------------


@documento()
@rtr('rsc_tae/documentos/deliberacao_crsc_pdf.html')
@login_required
@require_GET
def deliberacao_crsc_pdf(request, processo_id):
    title = 'Deliberação da CRSC — RSC-TAE'
    processo = get_object_or_404(ProcessoRSCTae, pk=processo_id)
    _validar_acesso_resumo_avaliacao(request, processo)

    if processo.situacao not in SituacaoProcesso.FINAIS:
        raise PermissionDenied('Deliberação da CRSC disponível apenas para processos finalizados.')

    votos_finais = _votos_finais_crsc(processo)
    divergencias = _listar_divergencias_para_crsc(processo)
    status_final = status_deliberacao_final(votos_finais, quantidade_deliberacoes_item())
    resumo_final = resumo_final_consolidado(processo, divergencias)
    deliberacao = DeliberacaoCRSCRSCTae.objects.filter(processo=processo).select_related('deliberado_por_vinculo__pessoa').first()

    return {
        'title': title,
        'processo': processo,
        'dados': _dados_servidor(processo),
        'deferido': processo.situacao == SituacaoProcesso.DEFERIDO,
        'nivel': processo.nivel_requisitado,
        'votos_finais': votos_finais,
        'divergencias': divergencias,
        'status_final': status_final,
        'resumo_final': resumo_final,
        'deliberacao': deliberacao,
        'membros_crsc': _membros_crsc_deliberantes(processo),
        'numero_processo_eletronico': str(processo.processo_eletronico) if processo.processo_eletronico_id else '',
        'hoje': datetime.date.today(),
    }


# ---------------------------------------------------------------------------
# 6. Minuta de Portaria de Concessão (apenas deferidos)
# ---------------------------------------------------------------------------


@documento()
@rtr('rsc_tae/documentos/minuta_portaria_pdf.html')
@login_required
@require_GET
def minuta_portaria_pdf(request, processo_id):
    title = 'Minuta de Portaria de Concessão — RSC-TAE'
    processo = get_object_or_404(ProcessoRSCTae, pk=processo_id)
    _validar_acesso_resumo_avaliacao(request, processo)

    if processo.situacao != SituacaoProcesso.DEFERIDO:
        raise PermissionDenied('A minuta de portaria está disponível apenas para processos deferidos.')

    dados = _dados_servidor(processo)
    nivel = processo.nivel_requisitado
    rsc_equivalente = processo.rsc_equivalente()

    return {
        'title': title,
        'processo': processo,
        'dados': dados,
        'nivel': nivel,
        'rsc_equivalente': rsc_equivalente,
        'data_finalizacao': processo.data_finalizacao_avaliacao,
        'hoje': datetime.date.today(),
    }


# ---------------------------------------------------------------------------
# 4. Processo Completo Consolidado
# ---------------------------------------------------------------------------


def _renderizar_pdf_interno(view_func, request, processo_id):
    """Chama uma view-decorada-com-@documento e retorna bytes do PDF gerado."""
    response = view_func(request, processo_id)
    content = getattr(response, 'content', None)
    if content:
        return content
    # Se vier como HttpResponse, lê do streaming
    return b''.join(getattr(response, 'streaming_content', []))


def _imagem_para_pdf_bytes(image_bytes):
    """Converte bytes de imagem (JPG/PNG) em página PDF A4 centralizada.

    Retorna bytes do PDF, ou None se falhar.
    """
    try:
        from PIL import Image
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas
    except Exception:
        logger.exception('Dependências para conversão de imagem em PDF indisponíveis')
        return None

    try:
        img = Image.open(io.BytesIO(image_bytes))
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')

        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        page_w, page_h = A4
        margin = 36  # ~ 1,27 cm
        max_w = page_w - 2 * margin
        max_h = page_h - 2 * margin

        img_w, img_h = img.size
        ratio = min(max_w / img_w, max_h / img_h, 1)
        draw_w = img_w * ratio
        draw_h = img_h * ratio
        x = (page_w - draw_w) / 2
        y = (page_h - draw_h) / 2

        c.drawImage(ImageReader(img), x, y, width=draw_w, height=draw_h)
        c.showPage()
        c.save()
        return buffer.getvalue()
    except Exception:
        logger.exception('Falha ao converter imagem para PDF')
        return None


def _capa_anexo_pdf_bytes(titulo, subtitulo=''):
    """Gera uma página de capa (A4) com título centralizado para separar as seções de anexos."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm
        from reportlab.lib.utils import simpleSplit
        from reportlab.pdfgen import canvas
    except Exception:
        logger.exception('reportlab indisponível para gerar capa de anexo')
        return None

    try:
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        page_w, page_h = A4
        linhas = simpleSplit(titulo, 'Helvetica-Bold', 20, page_w - 4 * cm)
        y = page_h / 2 + (len(linhas) - 1) * 0.7 * cm
        c.setFont('Helvetica-Bold', 20)
        for linha in linhas:
            c.drawCentredString(page_w / 2, y, linha)
            y -= 0.95 * cm
        if subtitulo:
            c.setFont('Helvetica', 12)
            c.drawCentredString(page_w / 2, y - 0.4 * cm, subtitulo)
        c.showPage()
        c.save()
        return buffer.getvalue()
    except Exception:
        logger.exception('Falha ao gerar capa de anexo')
        return None


def _arquivo_para_pdf_bytes(arquivo_field):
    """Lê um FieldFile e retorna bytes de um PDF (convertendo imagens se necessário).

    Retorna None se o arquivo não puder ser processado.
    """
    if not arquivo_field:
        return None

    try:
        nome = getattr(arquivo_field, 'name', '') or ''
        ext = os.path.splitext(nome)[1].lower()
        with default_storage.open(nome, 'rb') as fh:
            conteudo = fh.read()
    except Exception:
        logger.exception('Erro ao abrir arquivo %s', getattr(arquivo_field, 'name', '?'))
        return None

    if ext == '.pdf':
        return conteudo
    if ext in ('.jpg', '.jpeg', '.png'):
        return _imagem_para_pdf_bytes(conteudo)
    logger.warning('Extensão não suportada para consolidação: %s', ext)
    return None


def _append_documentos_preliminares(processo, append):
    """Adiciona ao bundle o anexo dos documentos preliminares (capa + envio mais recente de cada tipo)."""
    docs = [doc for doc in _documentos_preliminares_atuais(processo).values() if doc]
    if not docs:
        return
    append(_capa_anexo_pdf_bytes('Anexo — Documentos Preliminares', 'Diploma/certificado e homologação do estágio probatório'))
    for doc in docs:
        append(_arquivo_para_pdf_bytes(doc.arquivo))


def _append_anexos_por_requisito(processo, append):
    """Adiciona os documentos comprobatórios agrupados por requisito, cada grupo com uma capa 'Anexo N - ...'."""
    anexos = (
        RolSaberCompetenciaAnexo.objects.filter(processo=processo)
        .select_related('rol_saber_competencia__grupo__requisito')
        .order_by(
            'rol_saber_competencia__grupo__requisito__numero',
            'rol_saber_competencia__grupo__numero',
            'rol_saber_competencia__numero',
            'id',
        )
    )
    requisito_atual = object()
    for anexo in anexos:
        requisito = getattr(getattr(anexo.rol_saber_competencia, 'grupo', None), 'requisito', None)
        req_id = getattr(requisito, 'pk', None)
        if req_id != requisito_atual:
            requisito_atual = req_id
            if requisito:
                append(_capa_anexo_pdf_bytes(f'Anexo {requisito.numeral_romano} - {requisito.descricao}', 'Documentos comprobatórios'))
        append(_arquivo_para_pdf_bytes(anexo.arquivo))


@login_required
@require_GET
def processo_completo_pdf(request, processo_id):
    """Concatena todas as peças do processo em um único PDF (para o processo eletrônico)."""
    processo = get_object_or_404(ProcessoRSCTae, pk=processo_id)
    _validar_acesso_resumo_avaliacao(request, processo)
    _checar_situacao_minima_para_documentos(processo)

    from pypdf import PdfReader, PdfWriter

    from rsc_tae.views.processo import relatorio_avaliacao as _relatorio_avaliacao_view

    writer = PdfWriter()

    def _append(blob):
        if not blob:
            return
        try:
            reader = PdfReader(io.BytesIO(blob))
            for page in reader.pages:
                writer.add_page(page)
        except Exception:
            logger.exception('Falha ao adicionar PDF ao bundle do processo %s', processo_id)

    # 1) Requerimento
    _append(_renderizar_pdf_interno(requerimento_pdf, request, processo_id))
    # 2) Formulário de Pontuação
    _append(_renderizar_pdf_interno(formulario_pontuacao_pdf, request, processo_id))
    # 3) Memorial Descritivo (se preenchido)
    try:
        _append(_renderizar_pdf_interno(memorial_pdf, request, processo_id))
    except PermissionDenied:
        pass  # memorial ainda não preenchido — pula
    # 4) Anexo — Documentos preliminares (capa + envio mais recente de cada tipo obrigatório)
    _append_documentos_preliminares(processo, _append)
    # 5) Anexos comprobatórios agrupados por requisito (uma capa 'Anexo N - ...' por requisito)
    _append_anexos_por_requisito(processo, _append)

    # 6) Relatório de avaliação + Deliberação da CRSC + Parecer (se processo finalizado)
    if processo.situacao in SituacaoProcesso.FINAIS:
        try:
            _append(_renderizar_pdf_interno(_relatorio_avaliacao_view, request, processo_id))
        except Exception:
            logger.exception('Falha ao adicionar relatório de avaliação ao bundle')
        try:
            _append(_renderizar_pdf_interno(deliberacao_crsc_pdf, request, processo_id))
        except Exception:
            logger.exception('Falha ao adicionar deliberação da CRSC ao bundle')
        try:
            _append(_renderizar_pdf_interno(parecer_pdf, request, processo_id))
        except Exception:
            logger.exception('Falha ao adicionar parecer ao bundle')

    out = io.BytesIO()
    writer.write(out)
    response = HttpResponse(out.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="processo_rsc_tae_{processo_id}.pdf"'
    return response


# ---------------------------------------------------------------------------
# Geração de Processo Eletrônico (integração com o módulo processo_eletronico)
# ---------------------------------------------------------------------------

# Documentos digitalizados incluídos no processo eletrônico.
# Tupla: (assunto, view geradora do PDF, restrito). restrito=True gera o documento
# com nível de acesso RESTRITO no processo eletrônico; False = PÚBLICO.
_DOCUMENTOS_PROCESSO_ELETRONICO = (
    ('Requerimento de RSC-TAE', requerimento_pdf, True),
    ('Memorial Descritivo', memorial_pdf, False),
    ('Deliberação da CRSC', deliberacao_crsc_pdf, False),
    ('Parecer Conclusivo da CRSC', parecer_pdf, False),
    ('Processo Completo', processo_completo_pdf, True),
)


def _config_processo_eletronico() -> dict:
    """Lê e valida as configurações do processo eletrônico (tipos obrigatórios + setor). ValueError se faltar."""
    from comum.models import Configuracao

    chaves_obrigatorias = {
        'tipo_processo': 'processo_eletronico_tipo_processo',
        'tipo_documento': 'processo_eletronico_tipo_documento',
        'tipo_conferencia': 'processo_eletronico_tipo_conferencia',
    }
    config = {}
    for nome, chave in chaves_obrigatorias.items():
        valor = Configuracao.get_valor_por_chave('rsc_tae', chave)
        if not valor:
            raise ValueError(f'Configuração SUAP ausente: "rsc_tae > {chave}". Defina-a em Configurações antes de gerar o processo eletrônico.')
        config[nome] = valor
    config['setor'] = Configuracao.get_valor_por_chave('rsc_tae', 'processo_eletronico_setor')
    return config


def _setor_destino_processo_eletronico(processo, config):
    """Setor do 1º trâmite: o configurado (rsc_tae > setor); se ausente, o de lotação do servidor."""
    from rh.models import Setor

    setor_pk = config.get('setor')
    if setor_pk:
        setor = Setor.objects.filter(pk=setor_pk).first()
        if setor:
            return setor
    return getattr(processo.vinculo, 'setor', None)


def _gerar_documentos_digitalizados(request, processo, config):
    """Gera os PDFs (Requerimento, Memorial, Parecer, Processo Completo) e monta os documentos digitalizados."""
    from processo_eletronico.models import Documento, TipoConferencia, TipoDocumento

    tipo_documento = TipoDocumento.objects.get(pk=config['tipo_documento'])
    tipo_conferencia = TipoConferencia.objects.get(pk=config['tipo_conferencia'])
    documentos = []
    for assunto, view_func, restrito in _DOCUMENTOS_PROCESSO_ELETRONICO:
        conteudo = _renderizar_pdf_interno(view_func, request, processo.id)
        if not conteudo:
            continue
        nivel_acesso = Documento.NIVEL_ACESSO_RESTRITO if restrito else Documento.NIVEL_ACESSO_PUBLICO
        documentos.append(
            {
                'tipo': tipo_documento,
                'tipo_conferencia': tipo_conferencia,
                'assunto': assunto,
                'nivel_acesso': nivel_acesso,
                'arquivo': ContentFile(conteudo, name=f'rsc_tae_{processo.id}_{assunto.lower().replace(" ", "_")}.pdf'),
            }
        )
    return documentos


def _gerar_e_vincular_processo_eletronico(request, processo, config):
    """Cria o processo eletrônico com os documentos e vincula ao processo RSC-TAE."""
    from processo_eletronico.models import Processo as ProcessoEletronico
    from processo_eletronico.models import TipoProcesso

    documentos = _gerar_documentos_digitalizados(request, processo, config)
    # setor_processo: onde o processo/documento nasce (define o cabeçalho — precisa ter UO) = setor do servidor.
    # setor_destino: destino do 1º trâmite (configurável; fallback = setor do servidor).
    setor_servidor = getattr(processo.vinculo, 'setor', None)
    if not setor_servidor or not getattr(setor_servidor, 'uo', None):
        raise Exception(
            'O setor de lotação do servidor não possui unidade organizacional (UO). Verifique o cadastro do servidor antes de gerar o processo eletrônico.'
        )
    setor_destino = _setor_destino_processo_eletronico(processo, config)
    relacionamento = request.user.get_relacionamento()
    processo_tramite = {
        'tipo_processo': TipoProcesso.objects.get(pk=config['tipo_processo']),
        'assunto': f'RSC-PCCTAE — {processo.vinculo}',
        'setor_destino': setor_destino,
    }
    processo_eletronico = ProcessoEletronico.cadastrar_processo(
        user=request.user,
        processo_tramite=processo_tramite,
        papel=relacionamento.papeis_ativos.first(),
        documentos_texto=[],
        documentos_digitalizados=documentos,
        interessados=[processo.vinculo],
        setor_processo=setor_servidor,
    )
    if not processo_eletronico:
        raise Exception('cadastrar_processo não retornou um processo eletrônico.')
    ProcessoRSCTae.objects.filter(pk=processo.pk).update(processo_eletronico=processo_eletronico)


def _criar_processo_eletronico_atomico(request: HttpRequest, processo: ProcessoRSCTae, config: dict) -> bool:
    """Cria e vincula o processo eletrônico sob trava da linha do processo RSC-TAE.

    Serializa pedidos concorrentes (duplo-clique / cliques repetidos): um segundo pedido
    aguarda a trava e, ao obtê-la, encontra o vínculo já criado e não gera outro. A criação
    dos documentos e do processo fica na mesma transação, evitando documentos órfãos em caso
    de falha. Retorna ``False`` se já havia processo eletrônico vinculado (nada é criado).
    """
    with transaction.atomic():
        processo_travado = ProcessoRSCTae.objects.select_for_update().get(pk=processo.pk)
        if processo_travado.processo_eletronico_id:
            return False
        _gerar_e_vincular_processo_eletronico(request, processo_travado, config)
    return True


@login_required
@require_GET
def criar_processo_eletronico(request, processo_id):
    """Gera o processo eletrônico do processo RSC-TAE finalizado (apenas RH sistêmico)."""
    processo = get_object_or_404(ProcessoRSCTae, pk=processo_id)
    changelist_url = reverse('admin:rsc_tae_processorsctae_changelist')

    if not (request.user.has_perm('rh.eh_rh_sistemico') or request.user.is_superuser):
        raise PermissionDenied('Apenas o RH sistêmico pode gerar o processo eletrônico.')
    if 'processo_eletronico' not in settings.INSTALLED_APPS:
        raise PermissionDenied('O módulo de Processo Eletrônico não está instalado.')
    if processo.situacao not in SituacaoProcesso.FINAIS:
        return httprr(changelist_url, 'O processo eletrônico só pode ser gerado para processos finalizados.', tag='error')
    if processo.processo_eletronico_id:
        return httprr(changelist_url, 'Este processo já possui um processo eletrônico vinculado.', tag='warning')

    try:
        config = _config_processo_eletronico()
    except ValueError as erro:
        return httprr(changelist_url, str(erro), tag='error')

    try:
        criado = _criar_processo_eletronico_atomico(request, processo, config)
    except Exception as erro:
        logger.exception('Erro ao gerar processo eletrônico do processo RSC-TAE %s', processo.pk)
        return httprr(changelist_url, f'Erro ao gerar o processo eletrônico: {erro}', tag='error')

    if not criado:
        return httprr(changelist_url, 'Este processo já possui um processo eletrônico vinculado.', tag='warning')
    return httprr(changelist_url, 'Processo eletrônico gerado com sucesso.', tag='success')
