from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Q

from comum.utils import get_uo
from djtools import db
from djtools.utils import calendario


class Estocavel:
    def entrada(self, datas=None, uo_id=None):
        """
        `uo_id`: Se for `None`, todas as UO's serão incluídas
        `datas`:
            - Pode ser 1 ou uma lista de 2 datas
            - 1 data: retorna dados até a data
            - lista de 2 datas: retorna dados no período
        -----
        Retorno: {'qtd': 0, 'valor': Decimal('0.0')}
        """
        if datas and not isinstance(datas, list):
            datas = [datas]
        entrada_normal = self.entrada_normal(datas, uo_id)
        return {'qtd': entrada_normal['qtd'], 'valor': entrada_normal['valor']}

    def entrada_normal(self, datas=None, uo_id=None):
        from almoxarifado.models import CategoriaMaterialConsumo, MaterialConsumo

        query = [
            """SELECT sum(mov.qtd) AS qtd,
                           sum(mov.qtd*mov.valor) AS valor
                    FROM movimentoalmoxentrada mov
                    INNER JOIN materialconsumo mat ON mov.material_id = mat.id
                    INNER JOIN entrada ent on ENT.id = MOV.entrada_id
                    WHERE mov.entrada_id IS NOT NULL
                    AND ENT.tipoentrada_id = 1"""
        ]

        if isinstance(self, MaterialConsumo):
            query.append(f' and mat.id = {self.id}')
        elif isinstance(self, CategoriaMaterialConsumo):
            query.append(f' and mat.categoria_id = {self.id}')
        if datas and len(datas) == 1:
            query.append(f" and mov.data < '{calendario.somar_dias(datas[0], 1)}'")
        elif datas and len(datas) == 2:
            query.append(f" and mov.data >= '{datas[0]}' and mov.data < '{calendario.somar_dias(datas[1], 1)}'")
        if uo_id:
            query.append(f' and mov.uo_id = {uo_id}')
        result = db.get_dict(''.join(query))[0]
        result['qtd'] = result['qtd'] or 0
        result['valor'] = result['valor'] or 0
        return result

    def entrada_doacao(self, datas=None, uo_id=None):
        from almoxarifado.models import CategoriaMaterialConsumo, MaterialConsumo

        query = [
            """SELECT sum(mov.qtd) AS qtd,
                           sum(mov.qtd*mov.valor) AS valor
                    FROM movimentoalmoxentrada mov
                    INNER JOIN materialconsumo mat ON mov.material_id = mat.id
                    INNER JOIN entrada ent on ENT.id = MOV.entrada_id
                    WHERE mov.entrada_id IS NOT NULL
                      AND ENT.tipoentrada_id = 2"""
        ]

        if isinstance(self, MaterialConsumo):
            query.append(f' and mat.id = {self.id}')
        elif isinstance(self, CategoriaMaterialConsumo):
            query.append(f' and mat.categoria_id = {self.id}')
        if datas and len(datas) == 1:
            query.append(f" and mov.data < '{calendario.somar_dias(datas[0], 1)}'")
        elif datas and len(datas) == 2:
            query.append(f" and mov.data >= '{datas[0]}' and mov.data < '{calendario.somar_dias(datas[1], 1)}'")
        if uo_id:
            query.append(f' and mov.uo_id = {uo_id}')
        result = db.get_dict(''.join(query))[0]
        result['qtd'] = result['qtd'] or 0
        result['valor'] = result['valor'] or Decimal('0.0')
        return result

    def devolucao(self, datas=None, uo_id=None):
        from almoxarifado.models import CategoriaMaterialConsumo, MaterialConsumo

        query = [
            """SELECT sum(mov.qtd) AS qtd,sum(mov.qtd*mov.valor) AS valor
                    FROM movimentoalmoxentrada mov
                    INNER JOIN materialconsumo mat ON mov.material_id = mat.id
                    AND mov.tipo_id = 3"""
        ]

        if isinstance(self, MaterialConsumo):
            query.append(f' and mat.id = {self.id}')
        elif isinstance(self, CategoriaMaterialConsumo):
            query.append(f' and mat.categoria_id = {self.id}')
        if datas and len(datas) == 1:
            query.append(f" and mov.data < '{calendario.somar_dias(datas[0], 1)}'")
        elif datas and len(datas) == 2:
            query.append(f" and mov.data >= '{datas[0]}' and mov.data < '{calendario.somar_dias(datas[1], 1)}'")
        if uo_id:
            query.append(f' and mov.uo_id = {uo_id}')
        result = db.get_dict(''.join(query))[0]
        result['qtd'] = result['qtd'] or 0
        result['valor'] = result['valor'] or Decimal('0.0')
        return result

    def entrada_transferencia(self, datas=None, uo_id=None):
        from almoxarifado.models import CategoriaMaterialConsumo, MaterialConsumo

        query = [
            """SELECT sum(mov.qtd) AS qtd,
                           sum(mov.qtd*mov.valor) AS valor
                    FROM movimentoalmoxentrada mov
                    INNER JOIN materialconsumo mat ON mov.material_id = mat.id
                    WHERE mov.requisicaouomaterial_id IS NOT NULL"""
        ]
        if isinstance(self, MaterialConsumo):
            query.append(f' and mat.id = {self.id}')
        elif isinstance(self, CategoriaMaterialConsumo):
            query.append(f' and mat.categoria_id = {self.id}')
        if datas and len(datas) == 1:
            query.append(f" and mov.data < '{calendario.somar_dias(datas[0], 1)}'")
        elif datas and len(datas) == 2:
            query.append(f" and mov.data >= '{datas[0]}' and mov.data < '{calendario.somar_dias(datas[1], 1)}'")
        if uo_id:
            query.append(f' and mov.uo_id = {uo_id}')
        result = db.get_dict(''.join(query))[0]
        result['qtd'] = result['qtd'] or 0
        result['valor'] = result['valor'] or Decimal('0.0')
        return result

    def saida(self, datas=None, uo_id=None):
        """
        `uo_id`: Se for `None`, todas as UO's serão incluídas
        `datas`:
            - Pode ser 1 ou uma lista de 2 datas
            - 1 data: retorna dados até a data
            - lista de 2 datas: retorna dados no período
        -----
        Retorno: {'qtd': 0, 'valor': Decimal('0.0')}
        """
        if datas and not isinstance(datas, list):
            datas = [datas]
        saida_user = self.saida_normal(datas, uo_id)
        return {'qtd': saida_user['qtd'], 'valor': saida_user['valor']}

    def saida_normal(self, datas=None, uo_id=None):
        from almoxarifado.models import CategoriaMaterialConsumo, MaterialConsumo

        query = [
            """SELECT sum(mov.qtd) AS qtd,
                           sum(mov.qtd*mov.valor) AS valor
                    FROM movimentoalmoxsaida mov
                    INNER JOIN materialconsumo mat ON mov.material_id = mat.id
                    WHERE mov.requisicaousermaterial_id IS NOT NULL"""
        ]
        if isinstance(self, MaterialConsumo):
            query.append(f' and mat.id = {self.id}')
        elif isinstance(self, CategoriaMaterialConsumo):
            query.append(f' and mat.categoria_id = {self.id}')
        if datas and len(datas) == 1:
            query.append(f" and mov.data < '{calendario.somar_dias(datas[0], 1)}'")
        elif datas and len(datas) == 2:
            query.append(f" and mov.data >= '{datas[0]}' and mov.data < '{calendario.somar_dias(datas[1], 1)}'")
        if uo_id:
            query.append(f' and mov.uo_id = {uo_id}')
        result = db.get_dict(''.join(query))[0]
        result['qtd'] = result['qtd'] or 0
        result['valor'] = result['valor'] or Decimal('0.0')
        return result

    def saida_transferencia(self, datas=None, uo_id=None):
        from almoxarifado.models import CategoriaMaterialConsumo, MaterialConsumo

        query = [
            """SELECT sum(mov.qtd) AS qtd,
                           sum(mov.qtd*mov.valor) AS valor
                    FROM movimentoalmoxsaida mov
                    INNER JOIN materialconsumo mat ON mov.material_id = mat.id
                    WHERE mov.requisicaouomaterial_id IS NOT NULL"""
        ]
        if isinstance(self, MaterialConsumo):
            query.append(f' and mat.id = {self.id}')
        elif isinstance(self, CategoriaMaterialConsumo):
            query.append(f' and mat.categoria_id = {self.id}')
        if datas and len(datas) == 1:
            query.append(f" and mov.data < '{calendario.somar_dias(datas[0], 1)}'")
        elif datas and len(datas) == 2:
            query.append(f" and mov.data >= '{datas[0]}' and mov.data < '{calendario.somar_dias(datas[1], 1)}'")
        if uo_id:
            query.append(f' and mov.uo_id = {uo_id}')
        result = db.get_dict(''.join(query))[0]
        result['qtd'] = result['qtd'] or 0
        result['valor'] = result['valor'] or Decimal('0.0')
        return result

    def get_estoque_atual(self, uo=None):
        from almoxarifado.models import MaterialEstoque

        """
        Função mais rápida que deve ser utilizada para saber o estoque atual
        """
        uo = uo or get_uo()
        try:
            materialestoque = MaterialEstoque.objects.get(material=self, uo=uo)
        except Exception:
            materialestoque = MaterialEstoque.objects.create(material=self, uo=uo, valor_medio=0, quantidade=0)

        return materialestoque.quantidade

    def get_total_qtd_empenhada(self, uo=None):
        from almoxarifado.models import EmpenhoConsumo

        total = 0
        uo = uo or get_uo()
        if EmpenhoConsumo.objects.filter(material=self).order_by('id').exists():
            for empenho_consumo in EmpenhoConsumo.objects.filter(Q(empenho__uo=uo), material=self).order_by('id'):
                if empenho_consumo.get_qtd_pendente() > 0:
                    total += empenho_consumo.qtd_empenhada - empenho_consumo.qtd_adquirida
        return total

    def get_estoque(self, uo=None, data=None, debug=False):
        """
        `debug` True força o cálculo do estoque atual com base em todas as
        entradas e saídas.
        """
        # Recuperar o estoque atual
        if not debug and data in [None, date.today()]:
            return self.get_estoque_atual(uo)

        # Recuperar o estoque numa data específica
        entrada = self.entrada(data, uo.id)
        saida = self.saida(data, uo.id)
        return {'qtd': entrada['qtd'] - saida['qtd'], 'valor': entrada['valor'] - saida['valor']}

    def estoque(self, **kwargs):
        # XXX: DEPRECATED; usar get_estoque
        data = kwargs.get('data', date.today())

        if data and not isinstance(data, list):
            data = [data]

        uo_id = kwargs.get('uo_id')

        entrada = self.entrada(data, uo_id)
        devolucao = self.devolucao(data, uo_id)
        entrada_transferencia = self.entrada_transferencia(data, uo_id)
        entrada_doacao = self.entrada_doacao(data, uo_id)
        saida = self.saida(data, uo_id)
        saida_transferencia = self.saida_transferencia(data, uo_id)

        return {
            'qtd': entrada['qtd']
            + devolucao['qtd']
            + entrada_transferencia['qtd']
            + entrada_doacao['qtd']
            - saida['qtd']
            - saida_transferencia['qtd'],
            'valor': entrada['valor']
            + devolucao['valor']
            + entrada_transferencia['valor']
            + entrada_doacao['valor']
            - saida['valor']
            - saida_transferencia['valor'],
        }


class EstoqueException(Exception):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


class Estoque:
    @classmethod
    @transaction.atomic
    def efetuar_saida_ou_transferencia(cls, requisicao_material, qtd_a_retirar):
        from almoxarifado.models import (
            MaterialEstoque,
            MovimentoAlmoxSaida,
            MovimentoAlmoxSaidaTipo,
            RequisicaoAlmoxUOMaterial,
            RequisicaoAlmoxUserMaterial,
        )

        assert isinstance(requisicao_material, RequisicaoAlmoxUserMaterial | RequisicaoAlmoxUOMaterial)
        assert isinstance(qtd_a_retirar, int)

        material = requisicao_material.material
        uo = requisicao_material.requisicao.uo_fornecedora
        estoque = MaterialEstoque.objects.get(material=material, uo=uo)
        if qtd_a_retirar < 1 or qtd_a_retirar > estoque.quantidade:
            raise EstoqueException(
                f'Quantidade insuficiente em estoque | args: requisicao_material: {requisicao_material.id}; qtd_a_retirar: {qtd_a_retirar}'
            )

        qtd = qtd_a_retirar

        if isinstance(requisicao_material, RequisicaoAlmoxUserMaterial):
            tipo_saida = MovimentoAlmoxSaidaTipo.REQUISICAO_USER_MATERIAL()
            requisicao_user_material = requisicao_material
            requisicao_uo_material = None
        elif isinstance(requisicao_material, RequisicaoAlmoxUOMaterial):
            tipo_saida = MovimentoAlmoxSaidaTipo.REQUISICAO_UO_MATERIAL()
            requisicao_uo_material = requisicao_material
            requisicao_user_material = None

        estoque.quantidade = estoque.quantidade - qtd_a_retirar
        estoque.save()
        # Efetuar saída no almoxarifado fornecedor
        movimento_saida = MovimentoAlmoxSaida.objects.create(
            tipo=tipo_saida,
            requisicao_uo_material=requisicao_uo_material,
            requisicao_user_material=requisicao_user_material,
            qtd=qtd,
            valor=estoque.valor_medio,
            uo=requisicao_material.requisicao.uo_fornecedora,
            material=requisicao_material.material,
        )

        # Efetuar entrada no almoxarifado solicitante
        if tipo_saida.nome == 'requisicao_uo_material':
            from almoxarifado.models import MovimentoAlmoxEntrada, MovimentoAlmoxEntradaTipo

            MovimentoAlmoxEntrada(
                tipo=MovimentoAlmoxEntradaTipo.REQUISICAO_UO_MATERIAL(),
                requisicao_uo_material=requisicao_material,
                qtd=qtd,
                estoque=movimento_saida.qtd,
                valor=estoque.valor_medio,
                uo=requisicao_material.requisicao.uo_solicitante,
                movimento_saida=movimento_saida,
                material=requisicao_material.material,
            ).save()

            nova_entrada = MovimentoAlmoxEntrada.objects.filter(
                uo=requisicao_material.requisicao.uo_solicitante, material=requisicao_material.material
            ).latest('id')

            material_uo, _ = MaterialEstoque.objects.get_or_create(
                material=requisicao_material.material, uo=requisicao_material.requisicao.uo_solicitante, defaults={'valor_medio': 0, 'quantidade': 0}
            )
            from almoxarifado.models import atualiza_valor_medio_atual

            atualiza_valor_medio_atual(requisicao_material.requisicao.uo_solicitante, material_uo.material, nova_entrada)
