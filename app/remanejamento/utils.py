from datetime import date, timedelta


def obter_campos_alterados(objeto_anterior, objeto_atual):
    campos_alterados = []
    for campo in objeto_atual._meta.fields:
        if getattr(objeto_anterior, campo.name) != getattr(objeto_atual, campo.name):
            campos_alterados.append(f'{campo.verbose_name}')
    return ','.join(campos_alterados)


def tempo_servico_no_cargo_em_dias(inscricao, data_referencia=None):
    """
    Caso exista ajuste na data de exercício para fins de remoção interna, leva em consideração a data ajustada
    """
    if not data_referencia:
        data_referencia = date.today()
    servidor = inscricao.servidor
    if data_referencia > date.today():
        data_referencia = date.today()

    if inscricao.data_exercicio_ajustada:
        data_inicio_exercicio_ajustada = inscricao.get_data_exercicio_ajustada()
        if servidor.data_fim_servico_na_instituicao and data_referencia < servidor.data_fim_servico_na_instituicao:
            return (data_referencia - data_inicio_exercicio_ajustada).days
        return ((servidor.data_fim_servico_na_instituicao or data_referencia) - data_inicio_exercicio_ajustada + timedelta(1)).days
    elif servidor.data_inicio_exercicio_no_cargo:
        return servidor.tempo_servico_no_cargo(data_referencia).days
    else:
        return 0


def ajustar_sigla_campus_lotacao(sigla):
    siglas = {
        'CCAL': 'CAL',
        'CCNAT': 'CNAT',
        'CSGA': 'SGA',
        'CNC': 'NC',
    }
    return siglas.get(sigla, sigla)
