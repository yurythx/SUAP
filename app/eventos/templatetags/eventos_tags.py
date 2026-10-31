from django.template import Library

from djtools.templatetags.filters import status

register = Library()


@register.simple_tag
def atividade_confirmada_display(participante, atividade):
    return status(atividade.participantes.filter(id=participante.id).exists())


@register.simple_tag
def atividade_confirmada(participante, atividade):
    return atividade.participantes.filter(id=participante.id).exists()


@register.simple_tag
def pode_mostrar_checkbox_widget(atividade, obj, participante):
    """
    Determina se deve mostrar o checkbox para uma atividade.
    Mostra se:
    1. A atividade corresponde ao objeto (atividade.pk == obj.pk)
    2. E (tem vagas disponíveis OU o participante já está inscrito)
    """
    if atividade.pk != obj.pk:
        return False
    # Verificar se tem vagas disponíveis
    vagas_disponiveis = obj.get_qtd_vagas_disponiveis()
    tem_vagas = vagas_disponiveis is None or vagas_disponiveis > 0
    # Verificar se o participante já está inscrito
    esta_inscrito = False
    if participante and participante.pk:
        esta_inscrito = participante.atividades.filter(pk=atividade.pk).exists()
    # Mostrar se tem vagas OU já está inscrito
    return tem_vagas or esta_inscrito


@register.simple_tag
def internacionalizacao(evento, idioma):
    if not evento.internacionalizacao_set.filter(idioma=idioma).exists():
        return {'nome': evento.nome, 'apresentacao': evento.apresentacao, 'local': evento.local}
    else:
        internacionalizacao = evento.internacionalizacao_set.get(idioma=idioma)
        return {'nome': internacionalizacao.titulo, 'apresentacao': internacionalizacao.apresentacao, 'local': internacionalizacao.local}


@register.simple_tag
def lista_certificados(evento, usuario):
    minhas_participacoes = evento.participantes.filter(cpf=usuario.get_vinculo().pessoa.pessoafisica.cpf)
    retorno = []
    for participante in minhas_participacoes:
        if participante.codigo_geracao_certificado:
            if participante.tipo and participante.tipo.tipo_participacao:
                retorno.append({'tipo': participante.tipo.tipo_participacao.descricao, 'url': participante.get_url_download_certificado()})
            else:
                retorno.append({'tipo': 'Certificado', 'url': participante.get_url_download_certificado()})
    return retorno
