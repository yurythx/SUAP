from django.template import Library

register = Library()


@register.simple_tag
def obtem_tipo_examinador(projeto_final, vinculo):
    """Verifica que tipo de examinador é a pessoa no Modelo Projeto Final"""
    return projeto_final.get_tipo_examinador(vinculo)


@register.simple_tag
def task_update_progress(task, counter, parent_counter=None, dados_agrupados=None):
    total_counter = counter
    for index, dados in enumerate(dados_agrupados):
        if parent_counter > index:
            total_counter += len(dados.list)
    task.update_progress(total_counter)
    return ''


@register.filter
def tem_disciplinas(turno) -> bool:
    """Retorna True se o turno possuir ao menos uma disciplina/atividade marcada em algum horário."""
    if hasattr(turno, 'tem_disciplinas') and callable(turno.tem_disciplinas):
        return turno.tem_disciplinas()
    if hasattr(turno, 'vazio') and turno.vazio is not None:
        return not turno.vazio
    for ha in getattr(turno, 'horarios_aula', []):
        for ds in getattr(ha, 'dias_semana', []):
            if isinstance(ds, dict) and ds.get('marcado'):
                return True
            if getattr(ds, 'marcado', False):
                return True
    return False
