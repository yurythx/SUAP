import datetime
from decimal import Decimal

from comum.models import Configuracao
from comum.utils import get_setores_que_sou_chefe_hoje
from pit_rit.utils import PontoDocente
from ponto.compensacao import Contexto
from ponto.models import Frequencia, RecessoOpcaoEscolhida
from rh.models import Funcao, Setor


def setores_que_sou_chefe_hoje(servidor):
    """Retorna setores chefiados hoje por ``servidor`` incluindo descendentes.

    Resolve as chefias diretas via ``get_setores_que_sou_chefe_hoje`` e expande
    a árvore com ``Setor.ids_subarvore`` para incluir os subsetores.

    Args:
        servidor: instância de ``Servidor`` cujas chefias serão consultadas; pode ser ``None``.

    Returns:
        QuerySet[Setor]: setores da estrutura SUAP (ativos e inativos);
        queryset vazio quando ``servidor`` é falsy.
    """
    if servidor and hasattr(servidor, 'get_user'):
        ids_chefias = list(get_setores_que_sou_chefe_hoje(servidor.get_user()).values_list('id', flat=True))
        ids_setores = Setor.ids_subarvore(ids_chefias)
        return Setor.objects.suap().filter(id__in=ids_setores)
    return Setor.objects.suap_ativos().none()


def setores_que_sou_chefe_direto_hoje(servidor):
    # Retorna apenas os que eh chefe direto (SEM descentes)
    if not servidor or not hasattr(servidor, 'eh_chefe_do_setor_hoje'):
        return Setor.objects.suap_ativos().none()
    usuario_logado = servidor
    if usuario_logado.eh_chefe_do_setor_hoje(usuario_logado.setor):
        return Setor.objects.suap_ativos().filter(
            pk__in=usuario_logado.servidorfuncaohistorico_set.atuais()
            .filter(funcao__codigo__in=Funcao.get_codigos_funcao_chefia())
            .values_list('setor_suap_id', flat=True)
            .distinct()
        )
    return Setor.objects.suap_ativos().none()


def get_datetime_now():
    try:
        from django.utils import timezone

        return timezone.now()
    except ImportError:
        from datetime import datetime

        return datetime.now()


def calcula_complexidade_ajustada(atividade, tempo_executado):
    faixas_complexidade_atividade = atividade.get_complexidades_ativo_com_tempo.order_by('tempo_execucao_remoto')

    # Tempo
    tempo_complexidades = faixas_complexidade_atividade.values_list('tempo_execucao_remoto', flat=True)

    tempo_ajustado = None
    faixa_complexidade_ajustada = None

    # Buscando o tempo e a complexidade ajustada
    i = 0
    for tc in tempo_complexidades:
        if tc >= tempo_executado:
            tempo_ajustado = tc
            break
        i += 1

    # - Se não achar tempo_ajustado para o tempo_executado é pq provavelmente o tempo_executado
    #   é maior que o tempo da maior faixa de complexidade
    #   - Nesse caso retornamos o valor da maior faixa complexidade
    if tempo_ajustado:
        faixa_complexidade_ajustada = faixas_complexidade_atividade[i]

    else:
        tempo_ajustado = tempo_complexidades.last()
        faixa_complexidade_ajustada = faixas_complexidade_atividade.last()

    return faixa_complexidade_ajustada, tempo_ajustado


def gv(v):
    v = v.get('v')
    if v:
        return Decimal(v)
    else:
        return Decimal(0)


def obter_dados_ponto_servidor(servidor, data_ini, data_fim, visualizar_futuro=False):
    # Essa rotina tende a sair do PGD
    # - Depois que o s novos cálculos de horas (obter_dados_horas_servidor) se consolidares ela sai
    return Frequencia.relatorio_ponto_pessoa(vinculo=servidor.get_vinculo(), data_ini=data_ini, data_fim=data_fim, visualizar_futuro=True)


def obter_dados_horas_ponto_servidor(servidor, data_ini, data_fim):
    # Busca dados de horas do servidor na compensacao.py
    return Contexto(servidor, data_ini, data_fim)


def obter_compensacoes_especificas_compesaveis_rit(rit):
    # Seleciona compensações específicas do servidor
    compensacoes_especificas = RecessoOpcaoEscolhida.objects.filter(
        funcionario=rit.pit.adesao.servidor, validacao=RecessoOpcaoEscolhida.VALIDACAO_AUTORIZADO
    )

    # Retira as que não sao compensáveis
    compensacoes_compensaveis = []

    # datas_rit = datas_entre(rit.get_data_inicial(), rit.get_data_final())
    data_rit_inicial, data_rit_final = rit.get_data_inicial(), rit.get_data_final()

    for ce in compensacoes_especificas:
        totais_ch = ce.totais_ch(carga_horaria_pendente=True)
        total_carga_horaria_pendente = totais_ch['total_carga_horaria_pendente']
        total_carga_horaria_pendente_por_dia = totais_ch['total_carga_horaria_pendente_por_dia']
        periodos_de_compensacao = ce.recesso_opcao.periodos_de_compensacao.all()
        for pc in periodos_de_compensacao:
            # datas_compensacao_especifica = datas_entre(pc.data_inicial, pc.data_final)
            # if set(datas_rit).issubset(set(datas_compensacao_especifica)):

            """
                rit         |--------------------------------|

                pc_1   |--------------------------------------------|
                pc_2            |--------------------------------------------|
                pc_3   |------------------------------|
                pc_4             |-----------------------|
            """

            pc_1_2_3_4 = pc.data_inicial <= data_rit_final and pc.data_final >= data_rit_inicial

            if pc_1_2_3_4:
                compensacoes_compensaveis.append((ce, pc.data_final, total_carga_horaria_pendente, total_carga_horaria_pendente_por_dia))

    return compensacoes_compensaveis


def get_ch_servidor_periodo(servidor, data_inicial, data_final):
    tempo_previsto = 0

    if servidor.eh_docente:
        pd = PontoDocente(servidor, data_inicial, data_final)
        horas = pd.total_relogio_exigido()
        if horas:
            tempo_previsto = horas / 3600
    if servidor.eh_tecnico_administrativo:
        # Tempo previsto do servidor TAE
        ths = obter_dados_horas_ponto_servidor(servidor, data_ini=data_inicial, data_fim=data_final)
        ths = ths.get_totais()

        data_rit = datetime.date(data_inicial.year, data_inicial.month, 1)
        data_atual = datetime.date(get_datetime_now().year, get_datetime_now().month, 1)

        # Calculando para meses que já passaram
        if data_rit < data_atual:
            tempo_previsto = ths.total_exigido_final + ths.total_debito_externo
        # Calculando para o mês atual
        elif data_rit == data_atual:
            tempo_previsto = (ths.total_exigido_previo - ths.total_desconsiderado_debito) + ths.total_debito_externo
        else:
            # Calculando para meses pra frente
            tempo_previsto = ths.total_exigido_previo + ths.total_debito_externo

        tempo_previsto = tempo_previsto / 3600

    return tempo_previsto


# PGD 1
# ---------------------------------


def get_data_fim_pgd1():
    data_fim_pgd1 = Configuracao.get_valor_por_chave('pgd', 'data_fim_pgd1')
    if data_fim_pgd1:
        return datetime.datetime.strptime(data_fim_pgd1, '%Y-%m-%d').date()
    return None
