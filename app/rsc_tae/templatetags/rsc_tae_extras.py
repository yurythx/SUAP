from decimal import Decimal

from django import template
from django.template.defaultfilters import filesizeformat

register = template.Library()


@register.filter
def tamanho_arquivo(arquivo):
    """Tamanho formatado do arquivo, ou 'arquivo indisponível' quando ele não pode ser lido no storage.

    Evita 500 quando o registro existe no banco mas o arquivo físico não está presente
    (ex.: banco réplica de produção sem a mídia sincronizada, ou arquivo removido), e informa
    o problema em vez de exibir um tamanho vazio: um anexo faltante não pode derrubar a tela
    inteira do processo.

    A captura é ampla de propósito. O tamanho vem de uma chamada de rede ao storage de objetos
    (``head_object``), e só o 404 vira ``FileNotFoundError``: qualquer outra resposta —
    a 400 das chaves inválidas, indisponibilidade, credencial vencida — sobe como o
    ``ClientError`` do botocore, que não é ``OSError`` e escapava daqui.
    """
    try:
        return filesizeformat(arquivo.size)
    except Exception:
        return 'arquivo indisponível'


@register.filter
def meses_para_anos(meses):
    """Converte meses (duração de item temporal) em anos pontuáveis ('ano ou fração > 6 meses')."""
    from rsc_tae.models.anexo import meses_para_anos_pontuaveis

    try:
        return meses_para_anos_pontuaveis(Decimal(str(meses)))
    except Exception:
        return 0


@register.simple_tag
def pontos_por_ano(pontuacao_unidade, meses):
    """Pontos de um item temporal: pontuação por ano x anos (a partir da duração em meses)."""
    from rsc_tae.models.anexo import meses_para_anos_pontuaveis

    try:
        anos = meses_para_anos_pontuaveis(Decimal(str(meses)))
        return Decimal(str(pontuacao_unidade or 0)) * anos
    except Exception:
        return 0


@register.simple_tag(takes_context=True)
def nome_avaliador(context, vinculo):
    """Exibe o nome do avaliador para membros da CRSC-TAE; anonimiza ('Avaliador N') para os demais.

    Depende de ``pode_ver_nomes_avaliadores`` (bool) e ``rotulos_avaliadores`` (dict vinculo_id -> rótulo)
    no contexto, injetados por ``injetar_visibilidade_avaliadores``.
    """
    if vinculo is None:
        return '—'
    if context.get('pode_ver_nomes_avaliadores'):
        return str(vinculo)
    rotulos = context.get('rotulos_avaliadores') or {}
    return rotulos.get(getattr(vinculo, 'id', None), 'Avaliador')
