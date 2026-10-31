"""Integração com a tela inicial do SUAP (djtools.layout).

Registra avisos/pendências RSC-TAE nos blocos "Atribuídos a mim" (servidor, avaliador,
membro da CRSC) e "Atribuídos aos meus grupos" (RH), com link de acesso rápido.
"""

import datetime
import logging
from collections import defaultdict

from django.template.defaultfilters import pluralize
from django.urls import reverse

from djtools import layout

from rsc_tae.enums import SituacaoProcesso
from rsc_tae.models import (
    AvaliacaoProcessoRSCTae,
    DeliberacaoCRSCRSCTae,
    ProcessoRSCTae,
    VotoDeliberacaoFinalRSCTae,
)


logger = logging.getLogger(__name__)

# Chave da configuração global. Precisa ser igual ao NOME do campo em
# rsc_tae.forms._ConfiguracaoRSCTaeBase — é dele que ConfiguracaoFormBase.save() deriva a chave.
CHAVE_DATA_LIMITE_LEMBRETE = 'data_limite_lembrete'

# SOMENTE ISO, que é o que o formulário de configuração grava (ConfiguracaoFormBase.save() faz
# str(date)). Aceitar dd/mm/aaaa aqui seria um convite a gravar esse formato pelo admin cru de
# Configuracao — e aí a tela de Configurações INTEIRA quebraria: ConfiguracaoFormBase.__init__
# (comum/forms.py) percorre todas as Configuracao e faz strptime(valor, '%Y-%m-%d') sem try/except
# em qualquer chave que seja DateField. Um único valor fora do ISO derruba a página de todos os
# apps, não só a seção do RSC-TAE.
_FORMATOS_DATA = ('%Y-%m-%d',)

# Linha de apoio do aviso, com a data embutida. Diz o que a data significa: um "Até <data>" solto
# seria lido como prazo para requerer o RSC, que é outra coisa — a janela do requerimento não vive
# nesta configuração.
TEXTO_VALIDADE_LEMBRETE = 'Este lembrete deixará de ser exibido após o dia {data}.'


def data_limite_lembrete():
    """Último dia de exibição do lembrete "Fique atento!", ou ``None`` quando não há data válida.

    Lê ``Configuracao(app='rsc_tae', chave='data_limite_lembrete')``, alimentada pelo campo
    homônimo do formulário de Configurações do módulo. Devolve ``None`` quando a configuração não
    existe, está em branco ou tem valor que não é data — e nos três casos o lembrete não aparece.

    Tratar valor inválido como "sem data" é deliberado: exibir para sempre esconderia o erro de
    digitação atrás de um comportamento que parece normal. O log é o que permite descobri-lo.
    """
    from comum.models import Configuracao

    valor = (Configuracao.get_valor_por_chave('rsc_tae', CHAVE_DATA_LIMITE_LEMBRETE) or '').strip()
    if not valor:
        return None

    for formato in _FORMATOS_DATA:
        try:
            return datetime.datetime.strptime(valor, formato).date()
        except ValueError:
            continue

    logger.warning(
        'RSC-TAE: configuração %s tem valor inválido (%r); o lembrete não será exibido. Use o formato ISO aaaa-mm-dd.',
        CHAVE_DATA_LIMITE_LEMBRETE,
        valor,
    )
    return None


def _vinculo(request):
    """Vínculo do usuário autenticado, ou None."""
    if not getattr(request.user, 'is_authenticated', False):
        return None
    try:
        return request.user.get_vinculo()
    except Exception:
        return None


def avisos_do_servidor(request):
    """Lógica do aviso do servidor, separada do decorador de sinal.

    ``@layout.inscricao()`` envolve a função em ``silenciar(return_on_error=[])``: qualquer exceção
    vira lista vazia, sem estourar na tela inicial. Ótimo em produção e péssimo em teste — um bug
    passaria como "o aviso não aparece". Por isso a regra vive aqui, chamável direto.

    O aviso tem três portas, e todas precisam estar abertas para ele aparecer:

    1. existe data limite cadastrada (``data_limite_lembrete``) — sem ela, nada é exibido;
    2. hoje ainda não passou dessa data (a data é o ÚLTIMO dia de exibição, inclusive);
    3. o servidor não tem nenhum processo finalizado — quem já concluiu não é mais o público do
       lembrete, mesmo que tenha aberto um novo processo depois.
    """
    if not getattr(request.user, 'eh_tecnico_administrativo', False):
        return []
    vinculo = _vinculo(request)
    if not vinculo:
        return []

    # date.today() e não timezone.localdate(): o projeto roda com USE_TZ=False, e nesse modo
    # localdate() levanta ValueError sobre datetime naive. O silenciar do decorador engoliria a
    # exceção, então o sintoma seria o aviso nunca aparecer — sem erro visível em lugar nenhum.
    data_limite = data_limite_lembrete()
    if data_limite is None or datetime.date.today() > data_limite:
        return []

    processos = ProcessoRSCTae.objects.filter(vinculo=vinculo)
    if processos.filter(situacao__in=SituacaoProcesso.FINAIS).exists():
        return []

    url = reverse('admin:rsc_tae_processorsctae_changelist')
    acao = 'Acompanhe seu processo' if processos.exists() else 'Inicie seu processo'
    return [
        {
            'titulo': f'<strong>RSC/PCCTAE:</strong> {acao}',
            'url': url,
            # 'extra' é a linha livre do componente djtools/templates/components/alertas.html.
            # O slot 'prazo' do componente não é usado: ele renderiza "Até <data>", que sozinho
            # seria lido como prazo para requerer.
            'extra': TEXTO_VALIDADE_LEMBRETE.format(data=data_limite.strftime('%d/%m/%Y')),
        }
    ]


@layout.inscricao()
def index_servidor(request):
    """Aviso RSC/PCCTAE do servidor TAE no box "Fique atento!".

    Usa ``inscricao`` (e não ``atribuidos_a_mim``) para dar mais destaque ao aviso.
    """
    return avisos_do_servidor(request)


@layout.atribuidos_a_mim()
def index_avaliador(request):
    """Pendência do avaliador: processos em análise designados a ele e ainda não finalizados."""
    if not request.user.has_perm('rsc_tae.avaliar_processorsctae'):
        return []
    vinculo = _vinculo(request)
    if not vinculo:
        return []

    finalizadas = AvaliacaoProcessoRSCTae.objects.filter(avaliador_vinculo=vinculo, finalizada=True).values('processo_id')
    qtd = ProcessoRSCTae.objects.filter(avaliadores=vinculo, situacao=SituacaoProcesso.EM_ANALISE).exclude(pk__in=finalizadas).distinct().count()
    if not qtd:
        return []
    return [
        {
            'titulo': 'RSC/PCCTAE',
            'subtitulo': f'avaliaç{pluralize(qtd, "ão,ões")} a realizar',
            'qtd': qtd,
            'url': reverse('rsc_tae:minhas_avaliacoes'),
        }
    ]


def _processos_com_cota_esgotada(processos_ids, vinculo) -> set[int]:
    """Processos, entre os informados, em que a cota da categoria do membro já fechou na final.

    Args:
        processos_ids: Identificadores dos processos candidatos a pendência.
        vinculo: Vínculo do membro da comissão.

    Returns:
        Os ids em que o membro está impedido de votar por cota (todos, se ele está sem categoria).
    """
    from rsc_tae.views._helpers import categoria_por_vinculo, limite_deliberacoes_por_categoria, votos_que_consomem_cota

    categorias = categoria_por_vinculo()
    categoria_id = categorias.get(vinculo.id)
    if not categoria_id:
        return set(processos_ids)

    limite = limite_deliberacoes_por_categoria()
    por_processo = defaultdict(list)
    for voto in VotoDeliberacaoFinalRSCTae.objects.filter(processo_id__in=processos_ids):
        por_processo[voto.processo_id].append(voto)

    return {
        processo_id
        for processo_id, votos in por_processo.items()
        if len(votos_que_consomem_cota(votos, vinculo.id, categoria_id, categorias)) >= limite
    }


@layout.atribuidos_a_mim()
def index_membro_crsc(request):
    """Pendência do membro da CRSC: processos aguardando deliberação em que ele ainda não votou."""
    from rsc_tae.views._helpers import eh_membro_crsc_ativo

    vinculo = _vinculo(request)
    if not eh_membro_crsc_ativo(vinculo):
        return []

    ja_deliberados = DeliberacaoCRSCRSCTae.objects.values('processo_id')
    ja_votei = VotoDeliberacaoFinalRSCTae.objects.filter(deliberado_por_vinculo=vinculo, desempate=False).values('processo_id')
    pendentes = list(
        ProcessoRSCTae.objects.filter(situacao=SituacaoProcesso.AGUARDANDO_CRSC)
        .exclude(pk__in=ja_deliberados)
        .exclude(pk__in=ja_votei)
        .values_list('pk', flat=True)
    )
    # Processo em que a categoria do membro já gastou a cota não é pendência dele: a trava recusaria
    # o voto, e cobrar o que não pode ser feito só empurra o membro para a tela em vão.
    qtd = len(set(pendentes) - _processos_com_cota_esgotada(pendentes, vinculo))
    if not qtd:
        return []
    return [
        {
            'titulo': 'RSC/PCCTAE',
            'subtitulo': f'deliberaç{pluralize(qtd, "ão,ões")} pendente{pluralize(qtd)}',
            'qtd': qtd,
            'url': '/admin/rsc_tae/processorsctae/?tab=tab_aguardando_crsc',
        }
    ]


@layout.atribuidos_a_meus_grupos()
def index_validacao(request):
    """Pendência de validação: documentos preliminares aguardando validação.

    Aparece para quem valida — RH sistêmico e membros ATIVOS da CRSC (que também detêm a permissão
    ``rsc_tae.definir_avaliador_processorsctae``).
    """
    from rsc_tae.views._helpers import eh_membro_crsc_ativo

    eh_sistemico = request.user.has_perm('rh.eh_rh_sistemico')
    membro = eh_membro_crsc_ativo(_vinculo(request))
    if not (eh_sistemico or membro):
        return []

    qs = ProcessoRSCTae.objects.filter(situacao=SituacaoProcesso.AGUARDANDO_VALIDACAO_DOCUMENTO_PRELIMINAR)

    qtd = qs.count()
    if not qtd:
        return []
    return [
        {
            'titulo': 'RSC/PCCTAE',
            'subtitulo': f'documento{pluralize(qtd)} a validar',
            'qtd': qtd,
            'url': '/admin/rsc_tae/processorsctae/?tab=tab_aguardando_validacao',
        }
    ]
