from django import template

from ..forms import SelectAvaliacaoBaseForm

register = template.Library()


@register.simple_tag(name='render_select_field')
def render_select_field(base_dados, criterio_matriz, soh_texto=False):
    return SelectAvaliacaoBaseForm.factory_field_render_select(base_dados, criterio_matriz, soh_texto)


#: Dígitos da matrícula que sobrevivem no documento publicado.
MATRICULA_VISIVEL = 3


def _titular(obj):
    """O Servidor/Aluno por trás do objeto: ele mesmo, ou o relacionamento do Vínculo."""
    return getattr(obj, 'relacionamento', obj)


@register.filter(name='responsavel_publico')
def responsavel_publico(obj) -> str:
    """Identificação do responsável como ela sai no documento do PDA.

    Nome usual (o do crachá) e só os três primeiros dígitos da matrícula: o documento vai para a
    área pública, e o nome civil inteiro com a matrícula completa é mais dado pessoal do que a
    finalidade exige. Aceita tanto um ``rh.Servidor`` quanto um ``comum.Vinculo`` — as duas
    marcações do documento têm em mãos coisas diferentes.

    Cai para o ``str`` do objeto quando não há pessoa por trás, para a marcação nunca ficar vazia.
    """
    if not obj:
        return ''
    titular = _titular(obj)
    pessoa_fisica = getattr(titular, 'pessoa_fisica', None)
    nome = ((getattr(pessoa_fisica, 'nome_usual', '') or getattr(pessoa_fisica, 'nome', '')) or '').strip()
    if not nome:
        return str(obj)
    matricula = str(getattr(titular, 'matricula', '') or '')
    if not matricula:
        return nome
    return f'{nome} ({matricula[:MATRICULA_VISIVEL]}...)'
