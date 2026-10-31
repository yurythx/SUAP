from django.db import transaction
from django.shortcuts import get_object_or_404

from djtools.utils import httprr, permission_required, rtr

from ..models import Paint, PlanejamentoAnual, PlanejamentoMensal
from ..papeis import get_auditores_ativos
from ..utils import get_ch_prevista_auditor_ano


def calcular_planejamento_de_auditor(*, paint, auditor, user_vinculo):
    ano = paint.ano.ano
    ch_por_mes = get_ch_prevista_auditor_ano(auditor, ano)
    total_prevista = sum(ch_por_mes.values())

    with transaction.atomic():
        planejamento_anual, _ = PlanejamentoAnual.objects.update_or_create(
            auditor=auditor,
            paint=paint,
            defaults={
                'carga_horaria_prevista': total_prevista,
                'carga_horaria_homologada': 0,
                'atualizado_por': user_vinculo,
            },
        )

        for mes, ch_mes in ch_por_mes.items():
            PlanejamentoMensal.objects.update_or_create(
                planejamento_anual=planejamento_anual,
                mes=mes,
                defaults={
                    'carga_horaria_prevista': ch_mes,
                    'carga_horaria_homologada': 0,
                    'atualizado_por': user_vinculo,
                },
            )

        # Importa férias/afastamentos (homologados) do SUAP para AfastamentoPlanejado
        planejamento_anual.importar_afastamentos_suap()


@permission_required('comum.is_auditor')
def carregar_ch_auditores(request, paint_id):
    paint = get_object_or_404(Paint, pk=paint_id)
    url_target = paint.get_absolute_url()
    vinculos_auditores = get_auditores_ativos()
    total_planejados = 0
    erros = []
    for vinculo in vinculos_auditores:
        auditor = vinculo.relacionamento
        try:
            calcular_planejamento_de_auditor(paint=paint, auditor=auditor, user_vinculo=request.user.get_vinculo())
            total_planejados += 1
        except Exception as e:
            erros.append((auditor, str(e)))
    # Mensagem de feedback
    if erros:
        msg = f'CH dos Auditores carregada com erros! {total_planejados} auditores atualizados. Erros: ' + '; '.join(
            f'{auditor}: {erro}' for auditor, erro in erros
        )
        return httprr(url_target, msg, tag='error')
    if total_planejados == 0:
        msg = 'Nenhum auditor encontrado para carregar CH.'
        return httprr(url_target, msg, tag='warning')

    # Redirecionar com mensagem de sucesso
    msg = f'CH dos Auditores carregada com sucesso! {total_planejados} auditores atualizados.'
    return httprr(url_target, msg)


@rtr('auditoria/templates/paint/paint.html')
@permission_required('comum.is_auditor')
def visualizar_paint(request, paint_id):
    paint: Paint = get_object_or_404(Paint, pk=paint_id)
    title = f'PAINT {paint.ano}'
    return locals()
