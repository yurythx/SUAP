from django.template import Library

from progressao_docente.forms import NotasForm

register = Library()


@register.filter(name='get_dict_value')
def get_dict_value(dictionary, key):
    try:
        return dictionary.get(key, None)
    except Exception:
        return None


@register.simple_tag(name='render_nota')
def render_nota(item, avaliacao, avaliador, avaliado_processo):
    return NotasForm.factory_field_render_nota(item, avaliacao, avaliador, avaliado_processo)


@register.filter(name='get_itens')
def get_itens(criterio, avaliacao):
    return criterio.get_itens(avaliacao)


@register.filter(name='pode_adicionar_pontuacao')
def pode_adicionar_pontuacao(criterio, avaliacao):
    return criterio.pode_adicionar_pontuacao(avaliacao)


@register.filter(name='get_qtde_itens_avaliados')
def get_qtde_itens_avaliados(criterio, avaliacao):
    return criterio.get_qtde_itens_avaliados(avaliacao)


@register.filter(name='get_pontuacao_total_avaliado')
def get_pontuacao_total_avaliado(criterio, avaliacao):
    return criterio.get_pontuacao_total_avaliado(avaliacao)


@register.filter(name='get_pontuacao_total')
def get_pontuacao_total(criterio, avaliacao):
    return criterio.get_pontuacao_total(avaliacao)


@register.filter(name='media_avaliacao_criterio')
def media_avaliacao_criterio(criterio, avaliacao):
    return criterio.media_avaliacao_criterio(avaliacao)


@register.filter(name='pontuacao_consideracao_positiva')
def pontuacao_consideracao_positiva(criterio, avaliacao):
    return criterio.get_pontuacao_consideracao_positiva(avaliacao)
