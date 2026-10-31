from django.db.models.aggregates import Sum

from djtools.assincrono import task
from djtools.utils import XlsResponse, render_html_file
from plan_estrategico.forms import RelatorioPlanoatividadeForm
from plan_estrategico.models import AtividadeEtapa


@task('Exportar Indicadores PDI para XLS')
def indicadores_pdi_export_to_xls(lista_indicadores, task=None):
    rows = [['Indicadores']]
    row = ['Indicador', 'Unid. Administrativa', 'Valor Meta', 'Valor Meta Trimestral', 'Valor Real']
    rows.append(row)

    for resultado in task.iterate(lista_indicadores):
        row = [resultado['indicador'], resultado['uo'], resultado['valor_meta'], resultado['valor_trimestral'], resultado['valor_real']]
        rows.append(row)

    return XlsResponse(rows, processo=task)


@task('Exportar Resultados de Indicadores para XLS')
def linhadotempo_export_to_xls(lista_inds, task=None):
    rows = [['Resultado do Indicador Linha do Tempo']]
    row = ['Indicador', 'Unidade Administrativa', 'Ano', 'Meta Anual', 'Valor Alcançado']
    rows.append(row)

    for resultado in task.iterate(lista_inds):
        row = [resultado['indicador'], resultado['uo'], resultado['ano'], resultado['meta_anual'], resultado['valor_alcancado']]
        rows.append(row)

    return XlsResponse(rows, processo=task)


@task('Visualizar Plano de Atividade')
def visualizar_plano_atividade_completo(request, projetos, plano_atividade, title, task=None):
    resumoplano_form = RelatorioPlanoatividadeForm(request.GET or None, plano_atividade=plano_atividade, request=request)
    resumoplano_form.ACTION = f'/plan_estrategico/plano_concluido/{plano_atividade.id}/'
    pode_requisitar_despesa = request.user.has_group_cached(['Gestor de UA', 'Coordenador de UA'])
    plano_concluido = plano_atividade.concluido
    lista_projetos = []
    projetos_dict = {}
    for projeto_plano in projetos:
        atividades = AtividadeEtapa.objects.filter(etapa_projeto_plano_atividade__projeto_plano_atividade=projeto_plano)
        projetos_dict[projeto_plano.id] = atividades
        task.count(atividades)
    for projeto_plano in projetos:
        atividades = projetos_dict[projeto_plano.id]
        total_valor_proposto = atividades.aggregate(total=Sum('valor'))['total'] or 0
        total_valor_rateio = atividades.aggregate(total=Sum('valor_rateio'))['total'] or 0
        total_valor_reserva = atividades.aggregate(total=Sum('valor_reserva_tecnica'))['total'] or 0
        descricao = {}
        descricao['projeto_plano'] = projeto_plano
        descricao['total_valor_proposto'] = total_valor_proposto
        descricao['total_valor_rateio'] = total_valor_rateio
        descricao['total_valor_reserva'] = total_valor_reserva
        descricao['total_atividades'] = total_valor_rateio + total_valor_reserva
        descricao['atividades'] = []
        atividades = atividades.order_by(
            'unidade_gestora__setor_equivalente',
            'origem_recurso_etapa__origem_recurso_projeto__origem_recurso',
            'origem_recurso_etapa__origem_recurso_projeto__origem_recurso__gnd__codigo',
            'etapa_projeto_plano_atividade__etapa__codigo',
        )
        for atividade in task.iterate(atividades):
            atividade_dict = {}
            atividade_dict['id'] = atividade.id
            atividade_dict['nome'] = atividade.nome
            atividade_dict['atividade_complementar'] = atividade.atividade_complementar
            atividade_dict['unidade_gestora_sigla'] = atividade.unidade_gestora.setor_equivalente.sigla
            atividade_dict['origem_recurso_etapa'] = atividade.origem_recurso_etapa
            atividade_dict['plano_interno'] = atividade.plano_interno
            atividade_dict['etapa_codigo'] = atividade.etapa_projeto_plano_atividade.etapa.codigo
            atividade_dict['etapa_descricao'] = atividade.etapa_projeto_plano_atividade.etapa.descricao
            atividade_dict['plano_interno_valor_disponivel_movimentado'] = (
                atividade.plano_interno.valor_disponivel_movimentado(atividade.unidade_gestora) if atividade.plano_interno else None
            )
            atividade_dict['get_valor_disponivel_realocacao'] = atividade.get_valor_disponivel_realocacao()
            atividade_dict['get_total_empenhados_atividade'] = atividade.get_total_empenhados_atividade()
            atividade_dict['saldo_disponivel_empenho_atividade'] = atividade.saldo_disponivel_empenho_atividade()
            descricao['atividades'].append(atividade_dict)
        lista_projetos.append(descricao)
    contexto = {
        'title': title,
        'plano_atividade': plano_atividade,
        'resumoplano_form': resumoplano_form,
        'pode_requisitar_despesa': pode_requisitar_despesa,
        'plano_concluido': plano_concluido,
        'lista_projetos': lista_projetos,
    }
    return render_html_file('plan_estrategico/templates/plano_concluido_task.html', contexto, request, task)
