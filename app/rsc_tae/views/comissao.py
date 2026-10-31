from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET

from djtools.utils.response import rtr

from rsc_tae.models import AvaliacaoProcessoRSCTae, ComissaoRSCTae
from rsc_tae.views._helpers import _ids_servidores_indisponiveis, _motivo_indisponibilidade_vinculo


@rtr('rsc_tae/visualizar_comissao.html')
@login_required
@require_GET
def visualizar_comissao(request, comissao_id):
    if not (
        request.user.has_perm('rh.eh_rh_sistemico')
        or request.user.has_perm('rh.eh_rh_campus')
        or request.user.has_perm('rsc_tae.definir_avaliador_processorsctae')
    ):
        raise PermissionDenied('Permissão negada.')

    comissao = get_object_or_404(
        ComissaoRSCTae.objects.prefetch_related('membros__vinculo__pessoa', 'membros__vinculo__setor'),
        pk=comissao_id,
    )

    # Contadores de processos por avaliador — uma query agregada
    vinculo_ids = list(comissao.membros.values_list('vinculo_id', flat=True))

    total_processos_por_vinculo = {}
    total_finalizadas_por_vinculo = {}
    for ap in AvaliacaoProcessoRSCTae.objects.filter(avaliador_vinculo_id__in=vinculo_ids).values('avaliador_vinculo_id', 'finalizada'):
        vid = ap['avaliador_vinculo_id']
        total_processos_por_vinculo[vid] = total_processos_por_vinculo.get(vid, 0) + 1
        if ap['finalizada']:
            total_finalizadas_por_vinculo[vid] = total_finalizadas_por_vinculo.get(vid, 0) + 1

    # IDs de servidores indisponíveis hoje — uma query em lote para todos os membros
    ids_indisponiveis = _ids_servidores_indisponiveis()

    membros = []
    for membro in comissao.membros.all():
        vid = membro.vinculo_id
        vinculo = membro.vinculo
        setor = getattr(getattr(vinculo, 'setor', None), 'sigla', None)

        # Disponibilidade: indisponível se é servidor e está na lista de ausentes
        eh_servidor = vinculo.eh_servidor() if vinculo else False
        indisponivel = eh_servidor and (vinculo.id_relacionamento in ids_indisponiveis)
        motivo = _motivo_indisponibilidade_vinculo(vinculo) if indisponivel else ''

        membros.append(
            {
                'vinculo': vinculo,
                'setor': setor,
                'ativo': membro.ativo,
                'total_processos': total_processos_por_vinculo.get(vid, 0),
                'total_finalizadas': total_finalizadas_por_vinculo.get(vid, 0),
                'disponivel': membro.ativo and not indisponivel,
                'motivo_indisponibilidade': motivo,
            }
        )

    total_disponiveis = sum(1 for m in membros if m['disponivel'])

    return {
        'title': comissao.nome,
        'comissao': comissao,
        'membros': membros,
        'total_disponiveis': total_disponiveis,
    }
