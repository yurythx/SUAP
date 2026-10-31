from django.template import Library
from django.utils.safestring import mark_safe

from centralservicos.models import AvaliaBaseConhecimento, PerguntaAvaliacaoBaseConhecimento, TarefaChamado, Chamado

register = Library()


@register.simple_tag
def obtem_grupos_por_categoria(categoria, servicos):
    ids = [s.id for s in servicos]
    grupos_servico_da_categoria = categoria.gruposervico_set.filter(servico__id__in=ids).prefetch_related('categorias')
    return grupos_servico_da_categoria.distinct()


@register.simple_tag
def obtem_servicos_por_grupo(grupo, servicos):
    ids = [s.id for s in servicos]
    servicos_do_grupo = grupo.servico_set.filter(id__in=ids).distinct()
    return servicos_do_grupo


@register.simple_tag(name='media_avaliacao_base_conhecimento')
def media_avaliacao_base_conhecimento(base_conhecimento, pergunta):
    return AvaliaBaseConhecimento.get_media_avaliacao(base_conhecimento, pergunta)


@register.simple_tag(name='minha_avaliacao_base_conhecimento', takes_context=True)
def minha_avaliacao_base_conhecimento(context, base_conhecimento, pergunta):
    request = context['request']
    try:
        avalia = AvaliaBaseConhecimento.objects.get(base_conhecimento=base_conhecimento, pergunta=pergunta, avaliado_por=request.user)
        return avalia.nota
    except AvaliaBaseConhecimento.DoesNotExist:
        return None


@register.simple_tag(name='tem_avaliacao_pendente', takes_context=True)
def tem_avaliacao_pendente(context, base_conhecimento):
    """Verifica se o usuário tem avaliacao pendente para a base de conhecimento informada"""
    request = context['request']
    perguntas = PerguntaAvaliacaoBaseConhecimento.objects.filter(area=base_conhecimento.area, ativo=True)
    for pergunta in perguntas:
        if not AvaliaBaseConhecimento.objects.filter(
            base_conhecimento=base_conhecimento, pergunta=pergunta, avaliado_por=request.user, data__gte=base_conhecimento.atualizado_em
        ).exists():
            return True
    return False


@register.simple_tag(name='pode_solicitar_correcao', takes_context=True)
def pode_solicitar_correcao(context, base_conhecimento):
    request = context['request']
    return request.user.has_perm('centralservicos.change_chamado') and not base_conhecimento.necessita_correcao


@register.inclusion_tag('avaliar_base_conhecimento.html', takes_context=True)
def avaliar_base_conhecimento(context, base_conhecimento, extra_class=''):
    request = context['request']
    avaliacoes = []
    if request.user.has_perm('centralservicos.change_chamado'):
        perguntas_avaliacao = PerguntaAvaliacaoBaseConhecimento.objects.filter(area=base_conhecimento.area, ativo=True)
        for pergunta in perguntas_avaliacao:
            try:
                avalia = AvaliaBaseConhecimento.objects.get(
                    base_conhecimento=base_conhecimento, pergunta=pergunta, avaliado_por=request.user, data__gte=base_conhecimento.atualizado_em
                )
            except AvaliaBaseConhecimento.DoesNotExist:
                avalia = AvaliaBaseConhecimento(base_conhecimento=base_conhecimento, pergunta=pergunta)

            avaliacoes.append(avalia)

    return {'avaliacoes': avaliacoes, 'extra_class': extra_class}


@register.simple_tag()
def exibe_estrelas_avaliacao(nota):
    retorno = []
    retorno.append('<ul class="stars">')
    for i in range(1, 6):
        if nota < i:
            retorno.append('<li><span class="fas fa-star disabled"></span></li>')
        else:
            retorno.append('<li><span class="fas fa-star"></span></li>')
    retorno.append('</ul>')
    return mark_safe(''.join(retorno))


@register.filter
def tarefa_chamado_situacao_status(situacao: str):
    situacao_descricao = TarefaChamado(situacao=situacao).get_situacao_display()
    status = ''
    if situacao == TarefaChamado.SITUACAO_ABERTA:
        status = 'info'
    if situacao == TarefaChamado.SITUACAO_EM_ANDAMENTO:
        status = 'alert'
    if situacao == TarefaChamado.SITUACAO_SUSPENSA:
        status = 'default'
    if situacao == TarefaChamado.SITUACAO_FINALIZADA:
        status = 'success'
    if situacao == TarefaChamado.SITUACAO_CANCELADA:
        status = 'extra4'
    return mark_safe(f'<span class="status status-{status}">{situacao_descricao}</span>')


@register.filter
def chamado_pode_reabrir(chamado: Chamado, user):
    return chamado.pode_reabrir(user)


@register.filter
def chamado_pode_fechar(chamado: Chamado, user):
    return chamado.pode_fechar(user)
