from django.shortcuts import get_object_or_404

from djtools.utils import httprr, permission_required, rtr

from ..forms import ComentarioForm
from ..models import Comentario, Recomendacao


@rtr('auditoria/templates/posicionamento/form.html')
@permission_required('comum.is_auditor')
def adicionar_comentario_recomendacao(request, recomendacao_id):
    recomendacao: Recomendacao = get_object_or_404(Recomendacao, id=recomendacao_id)
    if not recomendacao.pode_editar(request.user):
        return httprr('..', 'Você não tem permissão para realizar essa ação.', tag='error')
    #
    form = ComentarioForm(request.POST or None, object=recomendacao, request=request)
    if form.is_valid():
        form.save()
        return httprr('..', 'Comentário Adicionado com sucesso')
    #
    return locals()


@rtr()
@permission_required('comum.is_auditor')
def desconsiderar_comentario(request, comentario_id):
    comentario: Comentario = get_object_or_404(Comentario, id=comentario_id)
    if not comentario.pode_editar(request.user):
        return httprr('..', 'Você não tem permissão para realizar essa ação.', tag='error')
    #
    comentario.desconsiderar()
    comentario.save()
    return httprr('..', 'Comentário desconsiderado com sucesso')


@rtr()
@permission_required('comum.is_auditor')
def excluir_comentario(request, comentario_id):
    comentario: Comentario = get_object_or_404(Comentario, id=comentario_id)
    if not comentario.pode_excluir(request.user):
        return httprr('..', 'Você não tem permissão para realizar essa ação.', tag='error')
    #
    comentario.delete()
    return httprr('..', 'Comentário removido com sucesso')
