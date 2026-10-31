from datetime import date, datetime, timedelta

from dateutil.relativedelta import relativedelta
from django.db.models import Model
from django.http import HttpResponse

from comum.utils import tl
from djtools.utils import user_has_one_of_perms


def mesmo_campus(lotado: Model | None, outro: Model | None) -> bool:
    """Se ``lotado`` e ``outro`` (servidor, histórico de setor, relacionamento...) têm setor no mesmo campus.

    Sem setor (ou setor sem campus) de qualquer um dos lados não há campus para conferir: nega. Os
    dois lados podem ser ``None`` ou não ter ``setor`` (p.ex. o relacionamento de quem não tem vínculo).
    """
    setor_lotado = getattr(lotado, 'setor', None)
    setor_outro = getattr(outro, 'setor', None)
    if setor_lotado is None or setor_outro is None:
        return False
    return setor_lotado.uo_id is not None and setor_lotado.uo_id == setor_outro.uo_id


def pode_ver_frequencia(funcionario, request=None):
    """Testa se o ``current_user`` pode ver as frequências do ``funcionario``"""

    if not request:
        return False
    current_user = request.user
    if not request.user.get_vinculo().eh_funcionario():
        return False

    funcionario_logado = request.user.get_relacionamento()

    # superusuário pode tudo
    if current_user.is_superuser:
        return True

    # em qualquer caso a permissão ``pode_ver_frequencia_todos`` pode ver
    if current_user.has_perm('ponto.pode_ver_frequencia_todos'):
        return True

    # verificação própria
    if current_user.get_profile().cpf == funcionario.pessoa_fisica.cpf:
        return user_has_one_of_perms(
            current_user, ['ponto.pode_ver_frequencia_propria', 'ponto.pode_ver_frequencias_enquanto_foi_chefe', 'ponto.pode_ver_frequencia_campus']
        )

    # funcionario do campus de funcionario_logado
    if funcionario_logado.eh_do_meu_campus(funcionario):
        return current_user.has_perm('ponto.pode_ver_frequencia_campus')

    else:
        return user_has_one_of_perms(current_user, ['ponto.pode_ver_frequencias_enquanto_foi_chefe'])


def get_datas_segunda_feira_e_sexta_feira_semana_passada():
    hoje = datetime.now() - timedelta(1)

    if hoje.weekday() == 6:  # Considerando que domingo é o primeiro dia da semana
        hoje = hoje - timedelta(days=-1)  # Corrigi a data de hoje para o cálculo ficar correto.

    segunda_feira_semana_passada = hoje - timedelta(7)
    segunda_feira_semana_passada = segunda_feira_semana_passada - timedelta(segunda_feira_semana_passada.weekday())

    sexta_feira_semana_passada = segunda_feira_semana_passada + timedelta(4)

    return segunda_feira_semana_passada, sexta_feira_semana_passada


def get_datas_dia_um_e_ultimo_dia_mes_passado():
    hoje = datetime.now()

    ultimo_dia_mes_passado = datetime(year=hoje.year, month=hoje.month, day=1) - timedelta(1)
    dia_um_mes_passado = datetime(year=ultimo_dia_mes_passado.year, month=ultimo_dia_mes_passado.month, day=1)

    return dia_um_mes_passado, ultimo_dia_mes_passado


def get_data_ultimo_dia_mes_corrente():
    hoje = datetime.now()

    proximo_mes = hoje + relativedelta(months=1)
    ultimo_dia_mes_corrente = datetime(year=proximo_mes.year, month=proximo_mes.month, day=1) - timedelta(1)

    return ultimo_dia_mes_corrente


def get_total_tempo_debito_pendente_semana_anterior():
    """retorna uma lista com dois valores:
    - o débito restante/pendente em segundos da semana passada
    - o débito restante/pendente em segundos da semana passada que pode ser compensado até o final do mês corrente
    """
    from ponto.compensacao import debito_pendente

    segunda_feira_semana_passada, sexta_feira_semana_passada = get_datas_segunda_feira_e_sexta_feira_semana_passada()
    return debito_pendente(
        servidor=tl.get_vinculo().relacionamento,
        data_inicial=segunda_feira_semana_passada.date(),
        data_final=sexta_feira_semana_passada.date(),
        data_limite_compensacao=get_data_ultimo_dia_mes_corrente().date(),
    )


def get_total_tempo_debito_pendente_mes_anterior():
    """retorna uma lista com dois valores:
    - o débito restante/pendente em segundos do mês anterior
    - o débito restante/pendente em segundos do mês anterior que pode ser compensado até o final do mês corrente
    """
    from ponto.compensacao import debito_pendente

    dia_um_mes_passado, ultimo_dia_mes_passado = get_datas_dia_um_e_ultimo_dia_mes_passado()
    return debito_pendente(
        servidor=tl.get_vinculo().relacionamento,
        data_inicial=dia_um_mes_passado.date(),
        data_final=ultimo_dia_mes_passado.date(),
        data_limite_compensacao=get_data_ultimo_dia_mes_corrente().date(),
    )


def get_total_tempo_debito_pendente_mes_corrente():
    """retorna o débito restante/pendente em segundos do mês corrente"""
    from ponto.compensacao import debito_pendente

    hoje = datetime.now()
    dia_um_mes_atual = datetime(hoje.year, hoje.month, 1)
    ultimo_dia_mes_atual = get_data_ultimo_dia_mes_corrente()
    return debito_pendente(servidor=tl.get_vinculo().relacionamento, data_inicial=dia_um_mes_atual.date(), data_final=ultimo_dia_mes_atual.date())[0]


def get_total_tempo_saldo_restante_mes_corrente():
    """retorna o saldo restante em segundos do mês corrente"""
    from ponto.compensacao import saldo_restante

    hoje = datetime.now()
    dia_um_mes_atual = datetime(hoje.year, hoje.month, 1)
    ultimo_dia_mes_atual = get_data_ultimo_dia_mes_corrente()
    return saldo_restante(servidor=tl.get_vinculo().relacionamento, data_inicial=dia_um_mes_atual.date(), data_final=ultimo_dia_mes_atual.date())


def get_relatorios_ponto_adaptados_para_relatorios_pit_rit_ponto_docente(
    relatorios_app_ponto, data_ini, data_fim, so_semanas_inconsistentes=False, task=None
):
    from pit_rit.utils import PontoDocente

    lista_relatorios_adaptados = []
    if task:
        relatorios_app_ponto = task.iterate(relatorios_app_ponto)
    for relatorio in relatorios_app_ponto:
        if relatorio['funcionario'].eh_docente:
            # adapta o relatório de ponto corrente para o relatório de ponto docente
            lista_relatorios_adaptados.append(
                PontoDocente(
                    servidor=relatorio['funcionario'],
                    data_inicial=data_ini,
                    data_final=data_fim,
                    relatorio_de_ponto=relatorio,
                    so_semanas_inconsistentes=so_semanas_inconsistentes,
                ).get_relatorio_de_ponto_adaptado()
            )
        else:
            # não adapta o relatório
            lista_relatorios_adaptados.append(relatorio)
    return lista_relatorios_adaptados


################################
# valores baseados no retorno da chamda date.weekday
DIA_DA_SEMANA_SEG = 0
DIA_DA_SEMANA_TER = 1
DIA_DA_SEMANA_QUA = 2
DIA_DA_SEMANA_QUI = 3
DIA_DA_SEMANA_SEX = 4
DIA_DA_SEMANA_SAB = 5
DIA_DA_SEMANA_DOM = 6


def is_dia_da_semana(data, dia_da_semana):
    return data.weekday() == dia_da_semana


################################
def is_request_xls(request):
    return request.GET.get('xls') or request.POST.get('xls')


def get_response_xls_registros_frequencias(relatorios, filename=None):
    """
    request: HTTPRequest
    relatorios: List<relatorio_pessoa>
    relatorio_pessoa: saída do método Frequencia.relatorio_ponto_pessoa
    """
    import openpyxl
    from openpyxl.styles import Font

    xls_response = None

    filename = filename or f'Relatório de Frequências{f" - {get_nome_funcionario(relatorios[0])}" if len(relatorios) == 1 else ""}'

    xls_response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    xls_response['Content-Disposition'] = f'attachment; filename={filename}.xlsx'

    planilha = openpyxl.Workbook()
    # Remove default sheet
    default_sheet = planilha.active
    planilha.remove(default_sheet)

    font_bold = Font(bold=True)

    # Helper for background color (not fully implemented as original logic was complex)
    # But we can implement basic colors if needed.
    # The original logic was doing some color replacement which might not be needed with openpyxl's full RGB support.

    for relatorio in relatorios:
        periodo = get_periodo(relatorio)

        pagina_name = get_nome_funcionario(relatorio)[:30]  # Excel sheet name limit
        # Ensure unique sheet names if needed, though the original code handled duplicates by appending (2)
        # openpyxl handles duplicates automatically by appending numbers if we don't specify unique names?
        # No, we should handle it.

        count = 1
        original_name = pagina_name
        while pagina_name in planilha.sheetnames:
            count += 1
            pagina_name = f'{original_name[:27]}({count})'

        pagina = planilha.create_sheet(title=pagina_name)

        pagina.cell(row=1, column=1, value='Funcionário:').font = font_bold
        pagina.cell(row=1, column=2, value=get_nome_funcionario(relatorio))
        pagina.cell(row=2, column=1, value='Matrícula:').font = font_bold
        pagina.cell(row=2, column=2, value=get_matricula_funcionario(relatorio))
        pagina.cell(row=3, column=1, value='Data Início:').font = font_bold
        pagina.cell(row=3, column=2, value=periodo[0].strftime('%d/%m/%Y') if periodo[0] else '')
        pagina.cell(row=4, column=1, value='Data Fim:').font = font_bold
        pagina.cell(row=4, column=2, value=periodo[1].strftime('%d/%m/%Y') if periodo[1] else '')

        pagina.cell(row=6, column=1, value='Data').font = font_bold
        pagina.cell(row=6, column=2, value='CH').font = font_bold
        pagina.cell(row=6, column=3, value='Registros').font = font_bold
        pagina.cell(row=6, column=4, value='Duração Bruta').font = font_bold
        pagina.cell(row=6, column=5, value='Duração Válida').font = font_bold
        pagina.cell(row=6, column=6, value='Duração Final').font = font_bold

        # Column widths
        # 3600 / 256 = 14 characters approx.
        # 3600 / 256 = 14 characters approx.
        pagina.column_dimensions['A'].width = 15
        pagina.column_dimensions['B'].width = 15
        pagina.column_dimensions['C'].width = 30
        pagina.column_dimensions['D'].width = 15
        pagina.column_dimensions['E'].width = 15
        pagina.column_dimensions['F'].width = 15

        row = 7

        for frequencia_dia in relatorio['dias']:
            dia_info = get_detalhes_frequencia_dia(frequencia_dia)

            registro_1 = dia_info.registros[0] if len(dia_info.registros) >= 1 else None

            # data
            pagina.cell(row=row, column=1, value=dia_info.dia.strftime('%d/%m/%Y'))

            # ch
            pagina.cell(row=row, column=2, value=f'{dia_info.ch}h')

            # registro 1
            if registro_1:
                pagina.cell(
                    row=row,
                    column=3,
                    value=f'{registro_1.acao}: {registro_1.horario.strftime("%H:%M:%S")} ({registro_1.maquina} {f": {registro_1.ip}" if registro_1.ip else ""})',
                )
            else:
                pagina.cell(row=row, column=3, value='')

            # duração
            duracao_bruta = dia_info.duracao_bruto
            duracao_valida = dia_info.duracao
            duracao_final = dia_info.duracao_computada or duracao_valida
            pagina.cell(row=row, column=4, value=f'{duracao_bruta}')
            pagina.cell(row=row, column=5, value=f'{duracao_valida}')
            pagina.cell(row=row, column=6, value=f'{duracao_final}')

            # registros 2 em diante
            for registro in dia_info.registros[1:]:
                row += 1
                pagina.cell(row=row, column=1, value='')
                pagina.cell(row=row, column=2, value='')

                pagina.cell(
                    row=row,
                    column=3,
                    value=f'{registro.acao}: {registro.horario.strftime("%H:%M:%S")} ({registro.maquina} {f": {registro.ip}" if registro.ip else ""})',
                )

                pagina.cell(row=row, column=4, value='')
                pagina.cell(row=row, column=5, value='')
                pagina.cell(row=row, column=6, value='')

            row += 1

    planilha.save(xls_response)

    return xls_response


def get_nome_funcionario(relatorio):
    return relatorio['funcionario'].pessoa_fisica.nome


def get_matricula_funcionario(relatorio):
    try:
        return relatorio['funcionario'].matricula
    except Exception:
        return ''


def get_periodo(relatorio):
    try:
        data_inicio = get_detalhes_frequencia_dia(relatorio['dias'][0])
        data_fim = get_detalhes_frequencia_dia(relatorio['dias'][len(relatorio['dias']) - 1])
        return [data_inicio.dia, data_fim.dia]
    except Exception:
        return [None, None]


def get_detalhes_frequencia_dia(frequencia_dia):
    """
    frequencia_dia: uma "linha" de relatorio.dias
    """

    class DictAsClass:
        def __init__(self, **args):
            for attr, value in args.items():
                setattr(self, attr, value)

    return DictAsClass(
        dia=frequencia_dia.get('dia'),
        ch=frequencia_dia.get('carga_horaria_do_dia_h'),
        registros=[
            DictAsClass(acao=registro.acao, horario=registro.horario, maquina=registro.maquina, ip=registro.ip)
            for registro in frequencia_dia.get('horarios', [])
        ],
        duracao_bruto=frequencia_dia.get('duracao_bruto', ''),
        duracao=frequencia_dia.get('duracao', ''),
        duracao_computada=frequencia_dia.get('duracao_computada', ''),
    )


class Periodo:
    def __init__(self, data_hora_inicio: datetime, data_hora_fim: datetime):
        if isinstance(data_hora_inicio, date):
            data_hora_inicio = datetime(data_hora_inicio.year, data_hora_inicio.month, data_hora_inicio.day, 0, 0, 0)
        if isinstance(data_hora_fim, date):
            data_hora_fim = datetime(data_hora_fim.year, data_hora_fim.month, data_hora_fim.day, 23, 59, 59)
        self.data_hora_inicio = data_hora_inicio
        self.data_hora_fim = data_hora_fim


def possui_horario_extra_noturno(par):
    saida = par[1]
    if saida.hour >= 22:
        return True
