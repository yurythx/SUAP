import json
from datetime import datetime, timedelta

from django.db import IntegrityError, transaction
from django.db.models import Q, Max

from djtools.utils import normalizar_nome_proprio
from patrimonio.models import ConferenciaItem, ConferenciaItemErro, ConferenciaSala, Inventario


def set_inventarios_coletor(conferencia_id, token, dump_json):
    try:
        conferencia = ConferenciaSala.objects.get(pk=conferencia_id)
    except ConferenciaSala.DoesNotExist:
        return 'ERROR|Sala inexistente no SUAP.'

    # token confere?
    if conferencia.token != token:
        return 'ERROR|Coleta não autorizada para esta sala.'

    # Inicia tratamento do JSON
    obj = json.loads(dump_json)

    # processa campo de observação
    observacao_sala = obj.get('observacao_sala')
    if observacao_sala is None:
        return 'ERROR|Aplicativo desatualizado. Acesse o SUAP para baixar a nova versão.'
    conferencia.observacao = observacao_sala
    conferencia.save()

    # processando inventários
    inventarios_conferencia = obj.get('inventarios') or {}
    for inventario, dados in list(inventarios_conferencia.items()):
        data_hora_coleta = dados.get('dh_coleta')
        estado_conservacao = dados.get('estado_conservacao') or ''
        observacao = dados.get('observacao')

        # validando campos
        if not data_hora_coleta:
            return f'ERROR|Data de coleta não informada (inventário: {inventario}).'

        # convertendo data/hora para padrao do Python/Django
        data_hora_coleta = datetime.strptime(data_hora_coleta, '%d/%m/%Y %H:%M:%S')

        # verifica se inventário existe no SUAP
        try:
            i = Inventario.objects.get(numero=inventario)
            # grava na tabela de conferência
            try:
                with transaction.atomic():
                    conferencia_item = ConferenciaItem.objects.get_or_create(
                        conferencia=conferencia,
                        inventario=i,
                        dh_coleta=data_hora_coleta,
                    )[0]
                    conferencia_item.estado_conservacao = estado_conservacao or i.estado_conservacao
                    conferencia_item.observacao = observacao
                    conferencia_item.save()
            except IntegrityError:
                # msg = 'O item {0} ja foi gravado anteriormente'.format(inventario)
                # print(msg)
                pass
        except Inventario.DoesNotExist:
            # msg = 'O item {0} nao existe'.format(inventario)
            # print(msg)
            # grava na tabela de inventários não encontrados
            try:
                with transaction.atomic():
                    ConferenciaItemErro.objects.create(
                        conferencia=conferencia,
                        inventario=inventario,
                        dh_coleta=data_hora_coleta,
                    )
            except IntegrityError:
                # msg='O item {0} ja possui uma entrada no log de erro'.format(inventario)
                # print(msg)
                pass
        except Exception as e:
            return f'ERROR|{e}'
    #
    return 'SUCCESS|Conferência gravada com sucesso.'


def get_id_sala_por_conferencia(conferencia_id, token):
    try:
        conferencia = ConferenciaSala.objects.get(pk=conferencia_id)
    except ConferenciaSala.DoesNotExist:
        return 'ERROR|Conferência inexistente no SUAP.'

    # token confere?
    if conferencia.token != token:
        return 'ERROR|Token inválido.'

    return f'SUCCESS|{conferencia.sala.id}'


def get_inventarios_campus(conferencia_id, token, data_de_partida):
    try:
        conferencia = ConferenciaSala.objects.get(pk=conferencia_id)
    except ConferenciaSala.DoesNotExist:
        return 'ERROR|Conferência inexistente no SUAP.'

    # token confere?
    if conferencia.token != token:
        return 'ERROR|Token inválido.'

    try:
        CAMPOS_CONSULTA = (
            'numero',
            'descricao',
            'estado_conservacao',
            'responsavel_vinculo__pessoa__nome',
            'responsavel_vinculo__user__username',
            'sala__pk',
            'sala__nome',
        )

        qs_inventarios = Inventario.depreciaveis.only(*CAMPOS_CONSULTA).filter(Q(sala__isnull=True) | Q(sala__predio__uo=conferencia.sala.predio.uo))

        if data_de_partida:
            data_de_partida = datetime.strptime(data_de_partida, '%d/%m/%Y %H:%M:%S')
            qs_inventarios = (
                qs_inventarios.select_related('movimentopatrim')
                .annotate(ultima_movimentacao=Max('movimentopatrim__data', filter=Q(movimentopatrim__isnull=False)))
                .filter(Q(movimentopatrim__isnull=True) | Q(ultima_movimentacao__gte=data_de_partida))
            )

        qs_inventarios = qs_inventarios.distinct().values_list(*CAMPOS_CONSULTA)

        # inclui uma margem de 1 dia, para evitar perda de dados devido a confusões com fuso-horário.
        data_consulta = datetime.now() - timedelta(days=1)

        inventarios = {
            'dh_consulta': data_consulta.strftime('%d/%m/%Y %H:%M:%S'),
            'id_campus': conferencia.sala.predio.uo.id,
            'nome_campus': normalizar_nome_proprio(conferencia.sala.predio.uo.nome),
            'inventarios': list(qs_inventarios),
        }

        return f'SUCCESS|{json.dumps(inventarios)}'

    except Exception as e:
        return f'ERROR|{e}'


exposed = [
    [set_inventarios_coletor, 'set_inventarios_coletor'],
    [get_id_sala_por_conferencia, 'get_id_sala_por_conferencia'],
    [get_inventarios_campus, 'get_inventarios_campus'],
]
