from django.template import Library

register = Library()


@register.inclusion_tag('gerenciador_projetos/templates/tags/box_usuarios.html', takes_context=True)
def box_usuarios(context, titulo, usuarios):
    return locals()


@register.inclusion_tag('gerenciador_projetos/templates/tags/montar_arvore_tarefas.html', takes_context=True)
def montar_arvore_tarefas(context, tarefas):
    pode_editar_tarefas = context['pode_editar_tarefas']
    eh_membro_projeto = context['eh_membro_projeto']
    pode_registrar_evolucao = context['pode_registrar_evolucao']
    user = context['user']
    projeto = context['projeto']
    return locals()


@register.inclusion_tag('gerenciador_projetos/templates/tags/tarefas_para_dashboard.html', takes_context=True)
def tarefas_para_dashboard(context, tarefas, user, projeto=None, show_status=True, sortable=False):
    return locals()


@register.simple_tag
def get_tarefas_sem_lista_por_projeto(projeto, filtros=None):
    return projeto.tarefas_sem_lista(filtros=filtros)


@register.simple_tag
def get_tarefas_da_lista_por_projeto(lista, projeto, filtros=None):
    return lista.get_tarefas(projeto=projeto, filtros=filtros)
