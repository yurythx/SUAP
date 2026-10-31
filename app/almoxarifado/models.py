from collections import OrderedDict
from datetime import date, datetime, timedelta
from decimal import Decimal
from math import ceil

from django.apps import apps
from django.db import transaction
from django.db.models import DecimalField, F, Max, Q, Sum
from django.db.models.aggregates import Count
from django.db.models.expressions import ExpressionWrapper
from django.shortcuts import get_object_or_404
from django.utils.safestring import mark_safe

from almoxarifado.estoque import Estocavel, Estoque
from almoxarifado.utils import OPERADOR_ALMOXARIFADO
from comum.models import Configuracao
from comum.utils import get_uo, tl
from djtools.contrib.admin.helpers import get_admin_object_url
from djtools.db import models
from djtools.templatetags.filters import format_datetime, format_money_almox, in_group
from djtools.utils import somar_dias, to_ascii, user_has_perm_or_without_request
from rh.models import Setor, UnidadeOrganizacional


def calcula_valor_medio_atual(uo, material):
    from django.db.migrations.recorder import MigrationRecorder

    data_inicio_valor_medio = Configuracao.get_valor_por_chave('almoxarifado', 'data_migracao_valor_medio')
    data = datetime.strptime(data_inicio_valor_medio, '%Y-%m-%d')
    if MigrationRecorder.Migration.objects.filter(app='almoxarifado', name='0010_ajustar_peps').exists():
        if MigrationRecorder.Migration.objects.filter(app='almoxarifado', name='0005_migrar_estoque').exists():
            data = MigrationRecorder.Migration.objects.filter(app='almoxarifado', name='0005_migrar_estoque')[0].applied

    entradas_ate_a_atual = MovimentoAlmoxEntrada.objects.filter(uo=uo, material=material).order_by('data')
    estoque = 0
    valor_medio = 0
    if entradas_ate_a_atual.exists():
        estoque = entradas_ate_a_atual[0].qtd
        valor_medio = entradas_ate_a_atual[0].valor
        registro = entradas_ate_a_atual[0]
        registro.estoque = estoque
        registro.save()

        if entradas_ate_a_atual.count() > 1:
            for x in range(entradas_ate_a_atual.count() - 1):
                saidas = MovimentoAlmoxSaida.objects.filter(
                    material=material, uo=uo, data__gte=entradas_ate_a_atual[x].data, data__lt=entradas_ate_a_atual[x + 1].data
                ).order_by('id')
                if saidas.exists():
                    for saida in saidas:
                        estoque = estoque - saida.qtd
                        if data:
                            if saida.data < data:
                                if saida.movimento_entrada:
                                    valor_entrada = MovimentoAlmoxEntrada.objects.filter(id=saida.movimento_entrada.id)
                                    if valor_entrada:
                                        saida.valor = valor_entrada[0].valor
                                else:
                                    saida.valor = saida.valor
                            else:
                                saida.valor = valor_medio

                        saida.save()

                ajusta_estoque = estoque
                if estoque < 0:
                    ajusta_estoque = 0

                valor_medio = ((estoque * valor_medio) + (entradas_ate_a_atual[x + 1].qtd * entradas_ate_a_atual[x + 1].valor)) / (
                    ajusta_estoque + entradas_ate_a_atual[x + 1].qtd
                )
                estoque = estoque + entradas_ate_a_atual[x + 1].qtd
                registro = entradas_ate_a_atual[x + 1]
                registro.estoque = estoque
                registro.save()

        ultima_entrada = entradas_ate_a_atual.latest('id')
        saidas_pos_ultima_entrada = MovimentoAlmoxSaida.objects.filter(material=material, uo=uo, data__gte=ultima_entrada.data).order_by('id')
        if saidas_pos_ultima_entrada.exists():
            for saida in saidas_pos_ultima_entrada:
                estoque = estoque - saida.qtd
                if saida.data < data:
                    if saida.movimento_entrada:
                        valor_entrada = MovimentoAlmoxEntrada.objects.filter(id=saida.movimento_entrada.id)
                        if valor_entrada:
                            saida.valor = valor_entrada[0].valor
                    else:
                        saida.valor = saida.valor
                else:
                    saida.valor = valor_medio
                saida.save()

    material_a_atualizar = MaterialEstoque.objects.get(material=material, uo=uo)
    material_a_atualizar.valor_medio = valor_medio
    material_a_atualizar.quantidade = estoque
    material_a_atualizar.save()
    return


def ajusta_entradas_de_transferencias(uo, material):
    uo = uo.id
    entradas_atualizadas = 0
    saidas_atualizadas = 0
    movimentacoes_pos_migracao = MovimentoAlmoxEntrada.objects.filter(uo=uo, tipo=MovimentoAlmoxEntradaTipo.ENTRADA(), material=material).order_by(
        'data'
    )
    if movimentacoes_pos_migracao.exists():
        for movimentacao in movimentacoes_pos_migracao:
            calcula_valor_medio_atual(uo, material)
            material_a_atualizar = MaterialEstoque.objects.get(material=movimentacao.material, uo=uo)

            mais_movimentos = MovimentoAlmoxEntrada.objects.filter(material=movimentacao.material, uo=uo, data__gt=movimentacao.data)

            if mais_movimentos.exists():
                quant_entradas = mais_movimentos.count()
                saidas_pos_tansferencias = MovimentoAlmoxSaida.objects.filter(
                    material=movimentacao.material, uo=uo, data__gt=movimentacao.data, data__lt=mais_movimentos[0].data
                )

                if saidas_pos_tansferencias.exists():
                    for saida in saidas_pos_tansferencias:
                        saida.valor = material_a_atualizar.valor_medio
                        saida.save()
                        saidas_atualizadas += 1

                if quant_entradas > 1:
                    for x in range(quant_entradas - 1):
                        if mais_movimentos[x].tipo == MovimentoAlmoxEntradaTipo.REQUISICAO_UO_MATERIAL():
                            registro = mais_movimentos[x]
                            registro.valor = mais_movimentos[x].movimento_saida.valor
                            registro.save()
                            entradas_atualizadas += 1
                            calcula_valor_medio_atual(uo, movimentacao.material)

                        saidas_pos_migracao = MovimentoAlmoxSaida.objects.filter(
                            material=movimentacao.material, uo=uo, data__gt=mais_movimentos[x].data, data__lt=mais_movimentos[x + 1].data
                        )
                        if saidas_pos_migracao.exists():
                            material_a_atualizar = MaterialEstoque.objects.get(material=movimentacao.material, uo=uo)
                            for saida in saidas_pos_migracao:
                                saida.valor = material_a_atualizar.valor_medio
                                saida.save()
                                saidas_atualizadas += 1

                        calcula_valor_medio_atual(uo, movimentacao.material)

            else:
                saidas_pos_migracao = MovimentoAlmoxSaida.objects.filter(material=movimentacao.material, uo=uo, data__gt=movimentacao.data)

                if saidas_pos_migracao.exists():
                    material_a_atualizar = MaterialEstoque.objects.get(material=movimentacao.material, uo=uo)
                    for saida in saidas_pos_migracao:
                        saida.valor = material_a_atualizar.valor_medio
                        saida.save()
                        saidas_atualizadas += 1


def atualiza_valor_medio_atual(uo, material, entrada):
    material_a_atualizar = MaterialEstoque.objects.get(material=material, uo=uo)
    valor_medio = ((material_a_atualizar.quantidade * material_a_atualizar.valor_medio) + (entrada.qtd * entrada.valor)) / (
        material_a_atualizar.quantidade + entrada.qtd
    )
    material_a_atualizar.valor_medio = valor_medio
    material_a_atualizar.quantidade = material_a_atualizar.quantidade + entrada.qtd
    material_a_atualizar.save()
    entrada.estoque = material_a_atualizar.quantidade
    entrada.save()
    return


class LicitacaoTipo(models.ModelPlus):
    nome = models.CharField(max_length=25)

    class Meta:
        db_table = 'licitacaotipo'
        verbose_name = 'Tipo de Licitação'
        verbose_name_plural = 'Tipos de Licitação'

    def __str__(self):
        return self.nome.capitalize()


class MaterialTipo(models.ModelPlus):
    nome = models.CharField(max_length=25)

    class Meta:
        db_table = 'materialtipo'

    def __str__(self):
        return self.nome.capitalize()

    @staticmethod
    def CONSUMO():
        return MaterialTipo.objects.get(nome='consumo')

    @staticmethod
    def PERMANENTE():
        return MaterialTipo.objects.get(nome='permanente')


class EntradaTipo(models.ModelPlus):
    SEARCH_FIELDS = ['nome']

    nome = models.CharField(max_length=25)

    class Meta:
        db_table = 'entradatipo'

    def __str__(self):
        verbose_names = {'compra': 'Compra', 'doacao': 'Doação'}
        return verbose_names[self.nome]

    @staticmethod
    def COMPRA():
        return EntradaTipo.objects.get(nome='compra')

    @staticmethod
    def DOACAO():
        return EntradaTipo.objects.get(nome='doacao')


class Entrada(models.ModelPlus):
    data = models.DateTimeField()
    uo = models.ForeignKeyPlus(UnidadeOrganizacional, on_delete=models.CASCADE)
    tipo_entrada = models.ForeignKeyPlus(
        'almoxarifado.EntradaTipo', db_column='tipoentrada_id', on_delete=models.CASCADE, verbose_name='Tipo de Entrada'
    )
    tipo_material = models.ForeignKeyPlus(
        'almoxarifado.MaterialTipo', db_column='tipomaterial_id', on_delete=models.CASCADE, verbose_name='Tipo de Material'
    )
    numero_nota_fiscal = models.CharField(max_length=25, null=True, blank=True, db_column='numeronotafiscal', verbose_name='Nº Nota Fiscal')
    data_nota_fiscal = models.DateField(null=True, blank=True, db_column='datanotafiscal')
    vinculo_fornecedor = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Fornecedor', null=True)
    processo = models.ForeignKeyPlus(
        'protocolo.Processo', null=True, blank=True, help_text='Processo desta instituição relativo a esta entrada de NF', on_delete=models.CASCADE
    )

    class Meta:
        db_table = 'entrada'
        permissions = (
            ('pode_ver_entrada', 'Pode buscar e visualizar entradas'),
            ('pode_ver_entrada_consumo', 'Pode ver entrada consumo'),
            ('pode_ver_entrada_permanente', 'Pode ver entrada permanente'),
            ('pode_importar_estoque_csv', 'Pode importar estoque via CSV (Migrador)'),
        )

    def __str__(self):
        return f'Entrada #{self.pk:d} (Campus: {self.uo})'

    def can_delete(self, user=None):
        # Entrada com itens removidos pela Coordenação de Patrimônio guarda o registro
        # auditável da remoção (aba "Itens Removidos") e por isso não pode ser excluída.
        if self.itens_cancelados.exists():
            return False

        for i in self.get_itens():
            if i.entrada.tipo_material == MaterialTipo.CONSUMO():
                saidas_pos_entrada = MovimentoAlmoxSaida.objects.filter(material=i.material, uo=self.uo, data__gte=self.data)

                if saidas_pos_entrada:
                    return False
            if not i.can_delete():
                return False

        return True

    @transaction.atomic
    def delete(self):
        if not self.can_delete():
            raise Exception('Os itens foram movimentados ou o usuario nao tem permissoes.')
        for i in self.get_itens():
            if i.entrada.tipo_material == MaterialTipo.CONSUMO():
                material_a_atualizar = MaterialEstoque.objects.get(material=i.material, uo=self.uo)
                quantidade_atual = material_a_atualizar.quantidade - i.qtd
                valor_medio = 0
                if quantidade_atual != 0:
                    valor_medio = (
                        (material_a_atualizar.quantidade * material_a_atualizar.valor_medio) - (i.qtd * Decimal(i.valor))
                    ) / quantidade_atual
                material_a_atualizar.valor_medio = valor_medio
                material_a_atualizar.quantidade = quantidade_atual
                material_a_atualizar.save()
            i.delete()

    def get_absolute_url(self):
        return f'/almoxarifado/entrada/{self.pk}/'

    def get_data(self):
        # TODO: retirar isso do models
        return format_datetime(self.data)

    def get_data_nota_fiscal(self):
        # TODO: retirar isso do models
        if self.data_nota_fiscal is not None:  # quando data None, o mask_date_br sugeria a data atual
            return format_datetime(self.data_nota_fiscal)

    def get_inventarios(self):
        return apps.get_model('patrimonio', 'Inventario').objects.filter(entrada_permanente__entrada=self)

    def get_empenho(self):
        if self.tipo_material == MaterialTipo.CONSUMO():
            try:
                return self.movimentoalmoxentrada_set.all()[0].empenho_consumo.empenho
            except IndexError, AttributeError:
                return None
        elif self.tipo_entrada == EntradaTipo.COMPRA():
            try:
                return self.entradapermanente_set.all()[0].get_empenho()
            except IndexError, AttributeError:
                return None

    def get_valor(self):
        # TODO: retirar isso do models
        return format_money_almox(self.get_valor_total())

    def get_valor_total(self):
        subtotais = [valor * qtd for valor, qtd in self.get_itens().values_list('valor', 'qtd')]

        return sum(subtotais)

    def pode_ver(self, user=None):
        user = user or tl.get_user()
        if self.tipo_material == MaterialTipo.PERMANENTE() and user.has_perm('almoxarifado.pode_ver_entrada_permanente'):
            return True
        return bool(self.tipo_material == MaterialTipo.CONSUMO() and user.has_perm('almoxarifado.pode_ver_entrada_consumo'))

    def get_itens(self):
        """
        Retorna os itens da entrada. Caso seja de consumo, queryset de
        `MovimentoAlmoxEntrada`, caso permanente `EntradaPermanente`.
        """
        if self.tipo_material == MaterialTipo.CONSUMO():
            return self.movimentoalmoxentrada_set.order_by('material__categoria__codigo', 'material__nome', 'id')
        elif self.tipo_material == MaterialTipo.PERMANENTE():
            return self.entradapermanente_set.order_by('categoria__codigo', 'descricao', 'id')

    def get_requisicoes_consumo(self):
        """
        Retorna queryset de RequisicaoAlmoxUser cuja movimentação foi feita via
        ``self.movimentoalmoxentrada_set``
        """
        ids = []
        for movimento_entrada in self.movimentoalmoxentrada_set.all():
            for movimento_saida in MovimentoAlmoxSaida.objects.all().filter(
                movimento_entrada=movimento_entrada, requisicao_user_material__isnull=False
            ):
                ids.append(movimento_saida.requisicao_user_material.requisicao_id)
        return RequisicaoAlmoxUser.objects.filter(pk__in=ids)

    def get_requisicoes_transferencia(self):
        """
        Retorna queryset de RequisicaoAlmoxUO cuja movimentação foi feita via
        ``self.movimentoalmoxentrada_set``
        """
        ids = []
        for movimento_entrada in self.movimentoalmoxentrada_set.all():
            for movimento_saida in MovimentoAlmoxSaida.objects.all().filter(
                movimento_entrada=movimento_entrada, requisicao_uo_material__isnull=False
            ):
                ids.append(movimento_saida.requisicao_uo_material.requisicao_id)
        return RequisicaoAlmoxUO.objects.filter(pk__in=ids)

    def get_requisicoes(self):
        return list(self.get_requisicoes_consumo()) + list(self.get_requisicoes_transferencia())

    def get_info_prazo(self):
        """
        Informa quantos dias faltam/passaram para o prazo.
        """
        # FIXME: aqui parece ter código de visualização, não de modelo
        if not self.get_empenho().data_prazo:
            return 'Informações Insuficientes'

        msgs = {
            'nao_atrasado': '<span color="green">Entregue com {} dias para o prazo final</span>',
            'atrasado': '<span color="green"><b>Entregue com atraso de {} dias</b></span>',
        }

        delta = (self.get_empenho().data_prazo - self.data.date()).days
        atraso = delta < 0 and 'atrasado' or 'nao_atrasado'
        return msgs[atraso].format(abs(delta))

    def get_elem_despesa_entrada(self):
        lista = []
        if self.tipo_material == MaterialTipo.CONSUMO():
            for entrada in (
                self.movimentoalmoxentrada_set.all()
                .values(
                    'material__categoria__codigo',
                    'material__categoria__nome',
                    'material__categoria__plano_contas',
                    'material__categoria__plano_contas__codigo',
                )
                .annotate(total_entrada=Sum(ExpressionWrapper(F('valor') * F('qtd'), output_field=DecimalField())))
            ):
                categoria = entrada['material__categoria__nome']
                planocontas = None
                if entrada['material__categoria__plano_contas'] is not None:
                    planocontas = entrada['material__categoria__plano_contas__codigo']
                codigo = entrada['material__categoria__codigo']
                valor = format_money_almox(entrada['total_entrada'])
                lista.append({'valor': valor, 'codigo': codigo, 'planocontas': planocontas, 'categoria': categoria})
            return lista
        elif self.tipo_material == MaterialTipo.PERMANENTE():
            for entrada in (
                self.entradapermanente_set.all()
                .values('categoria__codigo', 'categoria__nome', 'categoria__plano_contas', 'categoria__plano_contas__codigo')
                .annotate(total_entrada=Sum(ExpressionWrapper(F('valor') * F('qtd'), output_field=DecimalField())))
            ):
                categoria = entrada['categoria__nome']
                planocontas = None
                if entrada['categoria__plano_contas'] is not None:
                    planocontas = entrada['categoria__plano_contas__codigo']
                codigo = entrada['categoria__codigo']
                valor = format_money_almox(entrada['total_entrada'])
                lista.append({'valor': valor, 'codigo': codigo, 'planocontas': planocontas, 'categoria': categoria})
            return lista

    @staticmethod
    def total_elementos_despesas(
        uo, vinculo_fornecedor, tipo_material, tipo_entrada, empenho, processo, numero_nota_fiscal, data_inicial, data_final, descricao_material
    ):
        if tipo_material and tipo_material.nome == 'consumo':
            qs = MovimentoAlmoxEntrada.objects.filter(entrada__tipo_material__id=MaterialTipo.CONSUMO().id)

            if vinculo_fornecedor:
                qs = qs.filter(empenho_consumo__empenho__vinculo_fornecedor=vinculo_fornecedor)

            if processo:
                qs = qs.filter(empenho_consumo__empenho__processo_id=processo.id)

            if empenho:
                qs = qs.filter(empenho_consumo__empenho=empenho)

        else:
            from patrimonio.models import EntradaPermanente

            qs = EntradaPermanente.objects.filter(entrada__tipo_material__id=MaterialTipo.PERMANENTE().id)

            if numero_nota_fiscal:
                qs.filter(entrada__numero_nota_fiscal=numero_nota_fiscal)

            if vinculo_fornecedor:
                qs = qs.filter(empenho_permanente__empenho__vinculo_fornecedor=vinculo_fornecedor)

            if processo:
                qs = qs.filter(empenho_permanente__empenho__processo_id=processo.id)

            if empenho:
                qs = qs.filter(empenho_permanente__empenho=empenho)

        if uo:
            qs = qs.filter(entrada__uo_id=uo)

        if tipo_entrada:
            qs = qs.filter(entrada__tipo_entrada_id=tipo_entrada.id)

        if descricao_material:
            qs = qs.filter(entrada__entradapermanente__descricao__unaccent__icontains=descricao_material)
        qs = qs.filter(entrada__data__range=(data_inicial, data_final))
        if tipo_material and tipo_material.nome == 'consumo':
            qs = qs.values(
                codigo=F('material__categoria__codigo'),
                planocontas=F('material__categoria__plano_contas__codigo'),
                titulo=F('material__categoria__nome'),
            )
        else:
            qs = qs.values(codigo=F('categoria__codigo'), planocontas=F('categoria__plano_contas__codigo'), titulo=F('categoria__nome'))
        qs = qs.annotate(total=Sum(F('valor') * F('qtd'), output_field=models.DecimalField()))

        dados = OrderedDict()
        total = 0

        for obj in qs:
            dados[obj['codigo']] = {'codigo': obj['codigo'], 'planocontas': obj['planocontas'], 'titulo': obj['titulo'], 'total': obj['total']}
            total += obj['total']

        return dados, total

    @transaction.atomic
    def efetuar_entrada_material_consumo(self, material, qtd, valor, empenho_consumo=None):
        MaterialEstoque.objects.get(material=material, uo=self.uo)

        MovimentoAlmoxEntrada(
            tipo=MovimentoAlmoxEntradaTipo.ENTRADA(),
            entrada=self,
            empenho_consumo=empenho_consumo,
            qtd=qtd,
            estoque=qtd,
            valor=valor,
            uo=self.uo,
            material=material,
        ).save()

        nova_entrada = MovimentoAlmoxEntrada.objects.filter(uo=self.uo, material=material).latest('id')
        atualiza_valor_medio_atual(self.uo, material, nova_entrada)


class Empenho(models.ModelPlus):
    SEARCH_FIELDS = ['numero', 'numero_pregao']

    uo = models.ForeignKeyPlus(
        UnidadeOrganizacional, null=True, blank=True, verbose_name='UG Emitente', help_text='Unidade Gestora Emitente', on_delete=models.CASCADE
    )
    numero = models.CharField('Número', max_length=14, help_text='O número deve ser único por UG Emitente')
    processo = models.ForeignKeyPlus(
        'protocolo.Processo', null=True, blank=True, help_text='Processo desta instituição relativo a este empenho', on_delete=models.CASCADE
    )
    vinculo_fornecedor = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Fornecedor', null=True)
    tipo_licitacao = models.ForeignKeyPlus(
        'almoxarifado.LicitacaoTipo', db_column='tipolicitacao_id', blank=True, null=True, verbose_name='Tipo de Licitação', on_delete=models.CASCADE
    )
    # TODO: retirar null=True desta Field:
    numero_pregao = models.CharField(max_length=50, db_column='numeropregao', blank=True, null=True, verbose_name='Nº da Licitação')
    tipo_material = models.ForeignKeyPlus(
        'almoxarifado.MaterialTipo', db_column='tipomaterial', verbose_name='Tipo de Material', on_delete=models.CASCADE
    )
    data_recebimento_empenho = models.DateField(
        db_column='datarecebimentoempenho',
        verbose_name='Data Recebimento Empenho',
        blank=True,
        null=True,
        help_text='Data que o fornecedor recebeu o empenho para efeito de cálculo do status da entrega.',
    )
    prazo = models.IntegerField(
        verbose_name='Prazo',
        blank=True,
        null=True,
        help_text='Prazo em dias, contados a partir da data de recebimento, que o fornecedor tem para concluir a entrega dos itens empenhados',
    )
    # TODO: retirar null=True desta Field:
    status = models.CharField(
        max_length=50,
        choices=[['nao_iniciado', 'Não iniciado'], ['iniciado', 'Iniciado'], ['concluido', 'Concluído']],
        null=True,
        default='nao_iniciado',
    )
    data_prazo = models.DateField(null=True)
    data_conclusao = models.DateField(null=True)
    # TODO: retirar null=True desta Field:
    observacao = models.TextField('Observação', null=True, blank=True)

    class Meta:
        db_table = 'empenho'
        unique_together = ('uo', 'numero')
        permissions = (('pode_ver_empenho_consumo', 'Pode ver empenho consumo'), ('pode_ver_empenho_permanente', 'Pode ver empenho permanente'))

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.atualizar_informacoes()

    def can_delete(self, user=None):
        return all(i.can_delete() for i in self.get_itens())

    @transaction.atomic
    def delete(self):
        if not self.can_delete():
            raise Exception('Impossível cancelar. Os itens sofreram movimentações')
        if self.get_itens():
            for i in self.get_itens():
                i.delete()
        else:
            super().delete()

    def __str__(self):
        return '{} (UG: {})'.format(self.numero, self.uo or '-')

    def get_absolute_url(self):
        return f'/almoxarifado/empenho/{self.pk}/'

    def get_entradas(self):
        entrada_ids = []
        if self.tipo_material == MaterialTipo.CONSUMO():
            for empcon in self.empenhoconsumo_set.all():
                for movalm in empcon.movimentoalmoxentrada_set.all():
                    entrada_ids.append(movalm.entrada.id)
            return Entrada.objects.filter(id__in=entrada_ids).order_by('id')
        elif self.tipo_material == MaterialTipo.PERMANENTE():
            for empper in self.empenhopermanente_set.all():
                for entper in empper.entradapermanente_set.all():
                    entrada_ids.append(entper.entrada.id)
            return Entrada.objects.filter(id__in=entrada_ids).order_by('id')

    @classmethod
    def get_sem_atraso(cls):
        """
        Retorna empenhos sem atrasos.
        """
        return cls.objects.filter(data_prazo__gt=datetime.now())

    @classmethod
    def get_atrasados_pendentes(cls):
        """
        Retorna empenhos atrasados que não foram concluídos.
        """
        return cls.objects.filter(data_prazo__lt=datetime.now(), data_conclusao=None)

    @classmethod
    def get_concluidos_com_atraso(cls):
        """
        Retorna empenhos atrasados que foram concluídos.
        """
        return cls.objects.filter(Q(data_conclusao__gt=F('data_prazo')))

    @classmethod
    def get_pendentes(cls):
        """
        Retorno empenhos pendentes (status "Iniciado" ou "Não Iniciado")
        """
        return cls.objects.filter(status__in=('nao_iniciado', 'iniciado'))

    def get_info_prazo(self):
        """
        Informa quantos dias faltam/passaram para o prazo.
        """
        # FIXME: aqui parece ter código de visualização, não de modelo
        if not self.data_prazo:
            return 'Informações insuficientes'

        msgs = {
            'pendente': {
                'nao_atrasado': '<span class="status status-alert">{} dias restantes</span>',
                'atrasado': '<span class="status status-error">Atrasado {} dias</span>',
            },
            'concluido': {
                'nao_atrasado': '<span class="status status-success">Concluído com {} dias para o prazo final</span>',
                'atrasado': '<span class="status status-alert">Concluído com atraso de {} dias</span>',
            },
        }

        delta = (self.data_prazo - (self.data_conclusao or date.today())).days
        status = self.get_validado() == 'concluido' and 'concluido' or 'pendente'
        atraso = delta < 0 and 'atrasado' or 'nao_atrasado'

        return mark_safe(msgs[status][atraso].format(abs(delta)))

    get_info_prazo.short_description = 'Nota sobre o prazo'

    def get_itens(self):
        """
        Retorna lista de itens empenhados, de acordo com o tipo de material.
        """
        if self.tipo_material == MaterialTipo.PERMANENTE():
            return self.empenhopermanente_set.order_by('descricao')
        elif self.tipo_material == MaterialTipo.CONSUMO():
            return self.empenhoconsumo_set.order_by('id')

    def get_valor_total_categoria(self):
        valor_total = 0
        if self.tipo_material == MaterialTipo.CONSUMO():
            for e in self.empenhoconsumo_set.all():
                valor_total += e.valor * e.qtd_empenhada
            return format_money_almox(valor_total)
        elif self.tipo_material == MaterialTipo.PERMANENTE():
            for e in self.empenhopermanente_set.all():
                valor_total += e.valor * e.qtd_empenhada
            return format_money_almox(valor_total)

    def _get_valores_agrupados_por_categoria(self, queryset, categoria_field_lookup, categoria_model):
        """
        Método auxiliar para agrupar valores de empenho por categoria.
        """
        # 1. Agrega valores no banco de dados
        valores_agrupados = (
            queryset.values(categoria_field_lookup)
            # output_field explícito: no permanente `qtd_empenhada` é inteira e `valor` decimal,
            # e o Django recusa expressão de tipos mistos sem o tipo do resultado.
            .annotate(total_valor=Sum(F('valor') * F('qtd_empenhada'), output_field=DecimalField()))
            .order_by(f'{categoria_field_lookup}__codigo')
        )

        # 2. Busca as categorias em uma única query
        categoria_ids = [item[categoria_field_lookup] for item in valores_agrupados]
        categorias_dict = {cat.id: cat for cat in categoria_model.objects.filter(id__in=categoria_ids)}

        # 3. Monta a lista de retorno
        return [
            {
                'valor': format_money_almox(item['total_valor']),
                'categoria': categorias_dict.get(item[categoria_field_lookup]),
            }
            for item in valores_agrupados
        ]

    def get_categoria_empenho(self):
        if self.tipo_material == MaterialTipo.CONSUMO():
            return self._get_valores_agrupados_por_categoria(
                self.empenhoconsumo_set.all(),
                'material__categoria',
                CategoriaMaterialConsumo,
            )

        elif self.tipo_material == MaterialTipo.PERMANENTE():
            # Usa agregação para calcular valores diretamente no banco
            from patrimonio.models import CategoriaMaterialPermanente

            return self._get_valores_agrupados_por_categoria(
                self.empenhopermanente_set.all(),
                'categoria',
                CategoriaMaterialPermanente,
            )
        return []

    def pode_ver(self, user=None):
        user = user or tl.get_user()
        if self.tipo_material == MaterialTipo.PERMANENTE() and user.has_perm('almoxarifado.pode_ver_empenho_permanente'):
            return True
        return bool(self.tipo_material == MaterialTipo.CONSUMO() and user.has_perm('almoxarifado.pode_ver_empenho_consumo'))

    @property
    def pendente(self):
        """
        Retorna booleano indicando se o empenho tem algum item pendente.
        """
        return bool(self.get_itens().extra(where=['qtdadquirida < qtdempenhada']).count())

    @property
    def itens_concluidos(self):
        return self.get_itens().extra(where=['qtdadquirida = qtdempenhada'])

    @property
    def itens_nao_iniciados(self):
        return self.get_itens().extra(where=['qtdadquirida = 0 and qtdempenhada > 0'])

    def get_validado(self):
        # FIXME: existem vários empenhos com qtdempenhada = 0.
        # delete from empenhoconsumo WHERE qtdempenhada = 0;
        # delete from empenhopermanente WHERE qtdempenhada = 0;
        """
        Serve apenas para verificar a veracidade da coluna status.
        Também é usado para a migração.
        """
        total_itens = self.get_itens().count()

        if self.itens_nao_iniciados.count() == total_itens:
            return 'nao_iniciado'
        elif self.itens_concluidos.count() == total_itens:
            return 'concluido'
        else:
            return 'iniciado'

    def get_data_conclusao(self):
        """
        Serve apenas para verificar a veracidade da coluna data_conclusao.
        Também é usado para a migração.
        """
        if self.pendente:
            return None
        data_conclusao = [None]
        if self.tipo_material.nome == 'consumo':
            data_conclusao = [MovimentoAlmoxEntrada.objects.filter(empenho_consumo__empenho_id=self.id).aggregate(Max('data'))['data__max']]

        elif self.tipo_material.nome == 'permanente':
            data_conclusao = [Entrada.objects.filter(entradapermanente__empenho_permanente__empenho_id=self.id).aggregate(Max('data'))['data__max']]

        conclusao = data_conclusao[0] and data_conclusao[0].date() or None
        return conclusao

    def atualizar_informacoes(self):
        """
        Atualiza os atributoss `status`, `data_conclusao` e `data_prazo`.
        """
        self.status = self.get_validado()
        self.data_conclusao = self.get_data_conclusao()
        if self.data_recebimento_empenho and self.prazo:
            try:
                self.data_prazo = self.data_recebimento_empenho + timedelta(int(self.prazo))
            except Exception:
                self.data_prazo = None
        else:
            self.data_prazo = None
        models.ModelPlus.save(self)

    def get_total_entradas(self):
        return format_money_almox(sum(i.get_valor_total() for i in self.get_entradas()))

    def get_valor_total(self):
        return format_money_almox(sum(i.valor_empenhado() for i in self.get_itens()))


class UnidadeMedida(models.ModelPlus):
    nome = models.CharField(max_length=50, unique=True)

    class Meta:
        db_table = 'unidademedida'
        verbose_name = 'Unidade de Medida'
        verbose_name_plural = 'Unidades de Medida'

    def __str__(self):
        return self.nome


class PlanoContasAlmox(models.ModelPlus):
    codigo = models.CharField('Código', max_length=15, unique=True)
    descricao = models.CharField('Descrição', max_length=100, unique=True)
    ativo = models.BooleanField(default=True, verbose_name='Ativo')
    data_desativacao = models.DateTimeFieldPlus('Data de Desativação', null=True, blank=True)

    class Meta:
        verbose_name = 'Plano de Contas'
        verbose_name_plural = 'Planos de Contas'

    def __str__(self):
        return f'{self.codigo} - {self.descricao}'

    def save(self, *args, **kwargs):
        if self.ativo is False:
            self.data_desativacao = datetime.now()
        super().save(*args, **kwargs)


class CategoriaMaterialConsumo(models.ModelPlus, Estocavel):
    SEARCH_FIELDS = ['nome', 'codigo']

    codigo = models.CharField('Código', max_length=10, unique=True)
    nome = models.CharField(max_length=100, unique=True)
    plano_contas = models.ForeignKeyPlus(PlanoContasAlmox, null=True, on_delete=models.CASCADE)
    omitir = models.BooleanField(default=False)

    class Meta:
        db_table = 'categoriamaterialconsumo'
        ordering = ['codigo']
        verbose_name = 'Elemento de Despesa de Mat. de Consumo'
        verbose_name_plural = 'Elementos de Despesa de Mat. de Consumo'

    def __str__(self):
        return f'{self.codigo} - {self.nome}'


class Catmat(models.ModelPlus, Estocavel):
    SEARCH_FIELDS = ['descricao', 'codigo']
    codigo = models.CharFieldPlus('Código', max_length=6, unique=True)
    descricao = models.TextField('Descrição', max_length=1000)

    class Meta:
        ordering = ['codigo']
        verbose_name = 'Código CATMAT'
        verbose_name_plural = 'Códigos CATMAT'

    def __str__(self):
        return f'{self.codigo} - {self.descricao}'


class MaterialConsumoQuery(models.QuerySet):
    def com_estoque(self):
        return self.filter(materialestoque__quantidade__gt=0)

    def com_estoque_por_uo(self, uo):
        return self.filter(materialestoque__quantidade__gt=0, materialestoque__uo=uo)

    def com_qtd_empenhada_estoque_por_uo(self, uo):
        materiais_ids = EmpenhoConsumo.objects.filter(Q(empenho__uo=uo), qtd_empenhada__gt=F('qtd_adquirida')).values_list('material__id', flat=True)
        return self.filter(Q(id__in=materiais_ids, materialestoque__uo=uo) | Q(materialestoque__quantidade__gt=0, materialestoque__uo=uo))

    def teve_estoque(self):
        return self.filter().annotate(qtd_entradas=Count('movimentoalmoxentrada__material')).filter(qtd_entradas__gt=0)

    def teve_estoque_por_uo(self, uo):
        return self.filter(movimentoalmoxentrada__uo=uo).annotate(qtd_entradas=Count('movimentoalmoxentrada__material')).filter(qtd_entradas__gt=0)


class MaterialConsumoManager(models.Manager):
    def get_queryset(self):
        return MaterialConsumoQuery(self.model, using=self._db)

    def com_estoque(self):
        return self.get_queryset().com_estoque()

    def com_estoque_por_uo(self, uo):
        return self.get_queryset().com_estoque_por_uo(uo)

    def teve_estoque(self):
        return self.get_queryset().teve_estoque()

    def teve_estoque_por_uo(self, uo):
        return self.get_queryset().teve_estoque_por_uo(uo)


class MaterialConsumo(models.ModelPlus, Estocavel):
    SEARCH_FIELDS = ['nome', 'codigo']

    catmat = models.ForeignKeyPlus(Catmat, verbose_name='CATMAT', on_delete=models.SET_NULL, null=True, blank=True)
    categoria = models.ForeignKeyPlus(CategoriaMaterialConsumo, verbose_name='Categoria', on_delete=models.CASCADE)
    unidade = models.ForeignKeyPlus(UnidadeMedida, null=True, blank=True, verbose_name='Unidade', on_delete=models.CASCADE)
    nome = models.TextField('Nome', max_length=1024, unique=True, help_text='Máximo de 1024 caracteres.')
    # TODO: Remover valores NULL deste campo no banco e remover argumento `null`
    observacao = models.CharField('Observação', max_length=500, null=True, blank=True)
    codigo = models.CharField('Código', max_length=6, blank=True)
    search = models.SearchField(attrs=('codigo', 'nome'))

    objects = MaterialConsumoManager()

    class Meta:
        db_table = 'materialconsumo'
        verbose_name = 'Material de Consumo'
        verbose_name_plural = 'Materiais de Consumo'

        permissions = (
            ('pode_ver_relatorios_todos', 'Pode ver todos os relatórios de qualquer campus'),
            ('pode_ver_relatorios_do_campus', 'Pode ver relatórios de seu campus'),
        )

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):
        # salva para capturar o id
        super().save(*args, **kwargs)
        for uo in UnidadeOrganizacional.objects.suap().all():
            if not MaterialEstoque.objects.filter(material=self, uo=uo).exists():
                MaterialEstoque.objects.create(material=self, uo=uo, valor_medio=0, quantidade=0)

        # preenche código com o mesmo conteúdo de id + zeros a esquerda (facilitar busca)
        self.codigo = str(self.id).zfill(6)

        # força novo save devido campo codigo (antes remove force_insert e force_update pra evitar erros com .create nos testes)
        kwargs.pop('force_insert', None)
        kwargs.pop('force_update', None)

        super().save(*args, **kwargs)

    @staticmethod
    def buscar(
        palavras='',
        com_estoque_em=None,
        teve_estoque_em=None,
        categoria_id=None,
        unidade_id=None,
        limite=None,
        autocomplete=False,
        q='',
        user=None,
        limit=None,
        as_queryset=False,
        control=None,
    ):
        """
        Retorna lista de materiais onde nome tenha todas as `palavras`, não
        importanto acentuação ou case.

        Parâmetros:
        * palavras: descrição dos materiais
        * com_estoque_em: filtra apenas materiais com estoque no campus de ID
                          ``com_estoque_em``.
        * teve_estoque_em: filtra apenas materiais que já tiveram estoque no
                           campus de ID ``teve_estoque_em``.
        """
        palavras = palavras or q
        uo = get_uo()

        def material_dic(i):
            """
            A partir de um item do resultset, monta um dicionário de
            informações sobre o material.
            """
            nome_unidade = ''
            if i.unidade:
                nome_unidade = i.unidade.nome
            material_estoque = MaterialEstoque.objects.filter(material_id=i.id, uo=uo).first()
            return {
                'id': i.id,
                'nome': i.nome,
                'unidade_medida': nome_unidade,
                'categoria_codigo': i.categoria.codigo,
                'categoria_nome': i.categoria.nome,
                'estoque': material_estoque and material_estoque.quantidade or 0,
                'cod_material': i.codigo,
            }

        lista_palavras = to_ascii(palavras).upper().replace("'", ' ').split()
        qs = MaterialConsumo.objects.all()
        for palavra in lista_palavras:
            qs = qs.filter(search__icontains=palavra)

        if com_estoque_em:
            qs = qs.filter(materialestoque__in=MaterialEstoque.objects.filter(quantidade__gt=0, uo=com_estoque_em))

        if teve_estoque_em:
            qs = qs.filter(movimentoalmoxentrada__in=MovimentoAlmoxEntrada.objects.filter(uo=teve_estoque_em))

        if categoria_id:
            qs = qs.filter(categoria_id=categoria_id)

        if unidade_id:
            qs = qs.filter(unidade_id=unidade_id)

        qs = qs.order_by('nome')
        if qs.exists():
            if not as_queryset:
                itens = [material_dic(r) for r in qs[:limite]]
            else:
                return qs

            if not autocomplete:
                return itens
            else:
                return '\n'.join(
                    '{} - {} ({}) [{}] {}|{}'.format(
                        i['cod_material'],
                        i['nome'].strip().replace('\r\n', ''),
                        i['unidade_medida'],
                        i['categoria_codigo'],
                        i['categoria_nome'],
                        i['id'],
                    )
                    for i in itens
                )
        else:
            return ''

    def get_ext_combo_template(self):
        try:
            return '{} - {} ({}) [{}] {}'.format(
                self.codigo,
                self.nome.strip().replace('\r\n', ''),
                hasattr(self.unidade, 'nome') and self.unidade.nome or '',
                hasattr(self.categoria, 'codigo') and self.categoria.codigo or '',
                hasattr(self.categoria, 'nome') and self.categoria.nome or '',
            )
        except Exception:
            return f'{self.codigo} - {self.nome}'

    @classmethod
    def get_movimentados(cls, data_fim, uo_id=None):
        """
        Retorna queryset com materiais que foram movimentados no estoque da ``uo`` até ``data_fim``.
        Este método é utilizado no relatório de balancete.
        """
        filter_args = {'data__lt': somar_dias(data_fim, 1)}
        if uo_id:
            filter_args['uo__id'] = uo_id
        return MaterialConsumo.objects.filter(movimentoalmoxentrada__data__lt=data_fim, movimentoalmoxentrada__uo_id=uo_id).distinct()


class EmpenhoConsumo(models.ModelPlus):
    empenho = models.ForeignKeyPlus('almoxarifado.Empenho', on_delete=models.CASCADE)
    material = models.ForeignKeyPlus(MaterialConsumo, on_delete=models.CASCADE)
    qtd_empenhada = models.DecimalField(max_digits=15, decimal_places=5, db_column='qtdempenhada')
    qtd_adquirida = models.DecimalField(max_digits=15, decimal_places=5, default=0, db_column='qtdadquirida')
    valor = models.DecimalField(max_digits=15, decimal_places=6)

    class Meta:
        db_table = 'empenhoconsumo'
        ordering = ['empenho', 'id']

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.empenho.atualizar_informacoes()  # força a atualização do status durante inclusão/alteração

    def get_absolute_url(self):
        return get_admin_object_url(self)

    def get_delete_url(self):
        return f'/almoxarifado/empenhoconsumo/{self.id}/remover/'

    @staticmethod
    def get_pendentes(empenho):
        lista = []
        for empenho_consumo in EmpenhoConsumo.objects.filter(empenho=empenho).order_by('id'):
            if empenho_consumo.get_qtd_pendente() > 0:
                lista.append(empenho_consumo)
        return lista

    @transaction.atomic
    def efetuar_entrada(self, entrada, qtd):
        """
        Aumenta a `qtd_adquirida` e cria MovimentoAlmoxEntrada.
        """
        if qtd > self.get_qtd_pendente():
            msg = f'A quantidade informada ({qtd}) é maior que a pendente ({self.get_qtd_pendente()}).'
            raise ValueError(msg)

        self.qtd_adquirida += qtd
        self.save()
        try:
            MaterialEstoque.objects.get(material=self.material, uo=entrada.uo)
        except Exception:
            MaterialEstoque.objects.create(material=self.material, uo=entrada.uo, valor_medio=0, quantidade=0)

        MovimentoAlmoxEntrada(
            tipo=MovimentoAlmoxEntradaTipo.ENTRADA(),
            entrada=entrada,
            empenho_consumo=self,
            qtd=qtd,
            estoque=qtd,
            valor=self.valor,
            uo=entrada.uo,
            material=self.material,
        ).save()

        nova_entrada = MovimentoAlmoxEntrada.objects.filter(uo=entrada.uo, material=self.material).latest('id')
        atualiza_valor_medio_atual(entrada.uo, self.material, nova_entrada)

    def get_qtd_adquirida(self):
        """
        Calcula a quantidade adquirida com base nas entradas na classe MovimentoAlmoxEntrada.
        Útil para verificar integridade do campo `qtd_adquirida`.
        """
        qtd_entrada = 0
        for mov in self.movimentoalmoxentrada_set.all():
            qtd_entrada += mov.qtd
        return qtd_entrada

    def atualizar_qtd_adquirida(self):
        """
        Assegura que o atributo `qtd_adquirida` seja igual ao método `get_qtd_adquirida`.
        Esta função é usada em caso de deleção de movimentação.
        """
        qtd_adquirida_atualizada = self.get_qtd_adquirida()
        if self.qtd_adquirida != qtd_adquirida_atualizada:
            self.qtd_adquirida = qtd_adquirida_atualizada
            self.save()
        self.empenho.data_conclusao = None
        self.empenho.save()
        self.empenho.atualizar_informacoes()

    def get_qtd_pendente(self):
        return self.qtd_empenhada - self.qtd_adquirida

    def get_material(self):
        return self.material

    def get_categoria(self):
        return self.material.categoria

    def valor_empenhado(self):
        return self.qtd_empenhada * self.valor

    def get_valor_empenhado(self):
        return format_money_almox(self.valor_empenhado())

    def valor_adquirido(self):
        return self.qtd_adquirida * self.valor

    def get_valor(self):
        return format_money_almox(self.valor)

    def can_delete(self, user=None):
        if user_has_perm_or_without_request('almoxarifado.delete_empenhoconsumo'):
            return not self.qtd_adquirida
        return False

    def can_change(self, user=None):
        return bool(user_has_perm_or_without_request('almoxarifado.change_empenhoconsumo'))

    @transaction.atomic
    def delete(self):
        if not self.can_delete():
            raise Exception('Impossível cancelar. O item foi adquirido.')
        models.ModelPlus.delete(self)
        if not self.empenho.get_itens().exists():
            models.ModelPlus.delete(self.empenho)


######################################
# Tratamento genérico de requisições #
######################################


class RequisicaoAlmox:
    """
    É superclasse para RequisicaoAlmoxUser e RequisicaoAlmoxUO
    """

    def user_can_delete(self, user):
        uo_user = user.get_vinculo().setor.uo
        tipo = self.tipo
        if tipo == 'uo':
            if in_group(user, 'Coordenador de Almoxarifado, Coordenador de Almoxarifado Sistêmico') and (
                uo_user == self.uo_fornecedora or uo_user == self.uo_solicitante
            ):
                return True
        if tipo == 'user':
            if in_group(user, 'Coordenador de Almoxarifado, Coordenador de Almoxarifado Sistêmico') and uo_user == self.uo_fornecedora:
                return True
        return False

    @transaction.atomic
    def delete(self, *args, **kwargs):
        if not self.user_can_delete(tl.get_user()):
            raise Exception('Sem permissoes')
        for i in self.item_set.all():
            i.delete()

    @staticmethod
    def get(tipo, pk):
        """
        Retorna a requisição de acordo com os parâmetros passados
        """
        tipos = {'user': RequisicaoAlmoxUser, 'uo': RequisicaoAlmoxUO}
        return get_object_or_404(tipos[tipo], pk=pk)

    def get_absolute_url(self):
        return f'/almoxarifado/requisicao_detalhe/{self.tipo}/{self.pk}/'

    def user_pode_responder(self, user):
        """
        A requisição não pode ter sido avaliada, deve ser pelo menos operador
        do almoxarifado e sua UO deve ser a fornecedora da requisição.
        """
        if not self.avaliada:
            if in_group(user, OPERADOR_ALMOXARIFADO):
                uo_user = user.get_vinculo().setor.uo
                if uo_user == self.uo_fornecedora:
                    return True
        else:
            return False

    def user_pode_ver(self, usuario):
        tipo = self.tipo

        if not usuario.get_vinculo().setor:
            return False

        # Restrição de visualização de requisições por usuário
        if tipo == 'user':
            if usuario.has_perm('almoxarifado.pode_ver_todas_requisicoes_usuario'):
                return True
            if usuario.has_perm('almoxarifado.pode_ver_requisicoes_usuario_do_campus'):
                uo_usuario = usuario.get_vinculo().setor.uo
                if uo_usuario == self.uo_fornecedora:
                    return True

            return False

        # Restrição de visualização de requisições por uo
        if tipo == 'uo':
            if usuario.has_perm('almoxarifado.pode_ver_todas_requisicoes_uo'):
                return True
            if usuario.has_perm('almoxarifado.pode_ver_requisicoes_uo_do_campus'):
                uo_usuario = usuario.get_vinculo().setor.uo
                if uo_usuario == self.uo_fornecedora or uo_usuario == self.uo_solicitante:
                    return True

            return False

        # Se a requisição não cair num dos casos acima
        return False

    def user_pode_devolver_item(self, user):
        if in_group(user, OPERADOR_ALMOXARIFADO):
            uo_user = user.get_vinculo().setor.uo
            if uo_user == self.uo_fornecedora:
                return True
        else:
            return False

    @classmethod
    def get_pendentes(cls, user):
        """Retorna QuerySet de requisições pendentes visíveis ao usuário.

        Subclasses (RequisicaoAlmoxUser/UO) sobrescrevem com o filtro SQL
        equivalente a `user_pode_ver`, evitando o N+1 de iterar uma a uma.
        """
        # Fallback genérico (apenas para subclasses que não sobrescrevem):
        # mantém compatibilidade com o comportamento Python-side legado.
        return [r for r in cls.objects.filter(avaliada=False) if r.user_pode_ver(user)]

    def pode_avaliar(self):
        return not self.avaliada

    @transaction.atomic
    def avaliar(self, respostas, request):
        """
        `respostas`: {<item_id>: <qtd_aceita>}
        """
        if not self.pode_avaliar():
            raise Exception('Impossível avaliar. O mês já foi fechado ou a ', 'requisição já foi avaliada.')
        # Validando itens e quantidades aceitas
        for item_id, qtd_aceita in list(respostas.items()):
            item = self.item_set.get(pk=item_id)
            if (qtd_aceita < 1) or (item.get_estoque() < qtd_aceita):
                msg = f'A quantidade solicitada ({qtd_aceita}) é maior que a disponível ({item.get_estoque()}).'
                raise ValueError(msg)
        # Efetuando retiradas
        for item_id, qtd_aceita in list(respostas.items()):
            item = self.item_set.get(pk=item_id)
            item._aceitar(qtd_aceita)

        self.vinculo_fornecedor = request.user.get_vinculo()
        self.data_avaliacao_fornecedor = datetime.now()
        self.avaliada = True
        self.save()


class RequisicaoAlmoxMaterial:
    """
    É superclasse para RequisicaoAlmoxUserMaterial e RequisicaoAlmoxUOMaterial
    """

    @transaction.atomic
    def delete(self):
        if not self.requisicao.user_can_delete(tl.get_user()):
            raise Exception('Sem permissoes')
        for movimento_saida in self.movimentoalmoxsaida_set.all():
            if movimento_saida.requisicao_uo_material:
                uo = movimento_saida.requisicao_uo_material.requisicao.uo_fornecedora
                uo_solicitante = movimento_saida.requisicao_uo_material.requisicao.uo_solicitante
                material = MaterialEstoque.objects.get(material=movimento_saida.material, uo=uo_solicitante)
                material.quantidade -= movimento_saida.qtd
                material.save()
            else:
                uo = movimento_saida.requisicao_user_material.requisicao.uo_fornecedora
            material = MaterialEstoque.objects.get(material=movimento_saida.material, uo=uo)
            material.quantidade += movimento_saida.qtd
            material.save()
            # Removendo movimento_saida
            movimento_saida.delete()  # já deleta movimento_entrada na UO solicitante
        models.ModelPlus.delete(self)

        # Se este é o único item da requisição, esta também deve ser deletada
        if not self.requisicao.item_set.exists():
            models.ModelPlus.delete(self.requisicao)

    def __str__(self):
        return str(self.id)

    def valor(self):
        return self.saida()['valor']

    def get_estoque(self):
        return self.material.get_estoque(uo=self.requisicao.uo_fornecedora)

    def _aceitar(self, quantidade_aceita):
        Estoque.efetuar_saida_ou_transferencia(self, quantidade_aceita)

    def saida(self):
        qtd, valor = 0, Decimal('0.0')
        for movimento in self.movimentoalmoxsaida_set.all():
            qtd += movimento.qtd
            valor += movimento.valor * movimento.qtd
        return {'qtd': qtd, 'valor': valor}

    def valor_unitario(self):
        return format_money_almox(self.saida()['valor'])


###############
# Requisições entre almoxarifados
###############


class RequisicaoAlmoxUO(RequisicaoAlmox, models.ModelPlus):
    uo_fornecedora = models.ForeignKeyPlus(
        UnidadeOrganizacional, on_delete=models.CASCADE, db_column='uofornecedora_id', related_name='requisicaoalmoxuofornecedora_set'
    )
    vinculo_solicitante = models.ForeignKeyPlus('comum.Vinculo', null=True)
    uo_solicitante = models.ForeignKeyPlus(
        UnidadeOrganizacional, on_delete=models.CASCADE, db_column='uosolicitante_id', related_name='requisicaoalmoxuosolicitante_set'
    )
    data = models.DateTimeField(auto_now_add=True)
    avaliada = models.BooleanField(default=False)
    data_avaliacao_fornecedor = models.DateTimeField('Avaliada em', null=True)

    class Meta:
        db_table = 'requisicaoalmoxuo'
        ordering = ['-data']
        permissions = (
            ('pode_ver_todas_requisicoes_uo', 'Pode ver todas as requisições de campi'),
            ('pode_ver_requisicoes_uo_do_campus', 'Pode ver requisições de seu campus'),
        )

    @transaction.atomic
    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)

    @property
    def tipo(self):
        return 'uo'

    @classmethod
    def get_pendentes(cls, user):
        """SQL-equivalente a `user_pode_ver` para tipo='uo' aplicado em todas as requisições não avaliadas."""
        vinculo = user.get_vinculo()
        if not vinculo or not vinculo.setor:
            return cls.objects.none()
        base = cls.objects.filter(avaliada=False)
        if user.has_perm('almoxarifado.pode_ver_todas_requisicoes_uo'):
            return base
        if user.has_perm('almoxarifado.pode_ver_requisicoes_uo_do_campus'):
            uo_user = vinculo.setor.uo
            return base.filter(Q(uo_fornecedora=uo_user) | Q(uo_solicitante=uo_user))
        return cls.objects.none()

    def get_itens_aceitos(self):
        # TODO: no método antigo tinha um ORDER BY por código da categoria, é necessário?
        return RequisicaoAlmoxUOMaterial.objects.filter(requisicao=self, movimentoalmoxsaida__isnull=False).distinct().order_by('id')

    def get_itens_devolvidos(self):
        return DevolucaoMaterial.objects.filter(requisicao_uo=self)

    def get_total(self):
        aceitos = self.get_itens_aceitos()
        total = 0
        for a in aceitos:
            total += float(a.saida()['valor'])
        return format_money_almox(total)

    def get_data(self):
        return format_datetime(self.data)


class RequisicaoAlmoxUOMaterial(RequisicaoAlmoxMaterial, models.ModelPlus):
    requisicao = models.ForeignKeyPlus(RequisicaoAlmoxUO, related_name='item_set', on_delete=models.CASCADE)
    material = models.ForeignKeyPlus(MaterialConsumo, on_delete=models.CASCADE)
    qtd = models.IntegerField()

    class Meta:
        db_table = 'requisicaoalmoxuomaterial'

    @transaction.atomic
    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)


###############
# Requisições para pessoas
###############


class RequisicaoAlmoxUser(RequisicaoAlmox, models.ModelPlus):
    """
    Requisição feita por um servidor para o almoxarifado.
    `setor_solicitante` está redundante porque o servidor pode mudar de setor.
    """

    uo_fornecedora = models.ForeignKeyPlus(UnidadeOrganizacional, db_column='uofornecedora_id', on_delete=models.CASCADE)
    vinculo_solicitante = models.ForeignKeyPlus('comum.Vinculo', null=True, related_name='requisicaoalmoxuser_vinculo_solicitante')
    setor_solicitante = models.ForeignKeyPlus(Setor, db_column='setorsolicitante_id', on_delete=models.CASCADE)
    data = models.DateTimeField(auto_now_add=True)
    avaliada = models.BooleanField(default=False)
    observacoes = models.CharFieldPlus('Observações', null=True, blank=True)
    vinculo_fornecedor = models.ForeignKeyPlus('comum.Vinculo', null=True, related_name='requisicaoalmoxuser_vinculo_fornecedor')
    data_avaliacao_fornecedor = models.DateTimeField('Avaliada em', null=True)
    motivo_cancelamento = models.CharFieldPlus('Motivo do cancelamento', null=True, blank=True)

    class Meta:
        db_table = 'requisicaoalmoxuser'
        ordering = ['-data']
        permissions = (
            ('pode_ver_todas_requisicoes_usuario', 'Pode ver todas as requisições de pessoas'),
            ('pode_ver_requisicoes_usuario_do_campus', 'Pode ver requisições de pessoas de seu campus'),
        )

    @property
    def tipo(self):
        return 'user'

    @classmethod
    def get_pendentes(cls, user):
        """SQL-equivalente a `user_pode_ver` para tipo='user' aplicado em todas as requisições não avaliadas."""
        vinculo = user.get_vinculo()
        if not vinculo or not vinculo.setor:
            return cls.objects.none()
        base = cls.objects.filter(avaliada=False)
        if user.has_perm('almoxarifado.pode_ver_todas_requisicoes_usuario'):
            return base
        if user.has_perm('almoxarifado.pode_ver_requisicoes_usuario_do_campus'):
            return base.filter(uo_fornecedora=vinculo.setor.uo)
        return cls.objects.none()

    def get_itens_aceitos(self):
        return RequisicaoAlmoxUserMaterial.objects.filter(requisicao=self, movimentoalmoxsaida__isnull=False).distinct().order_by('id')

    def get_itens_devolvidos(self):
        return DevolucaoMaterial.objects.filter(requisicao_user=self)

    def pode_ser_cancelada(self):
        hoje = date.today()
        return self.data.year == hoje.year and self.data.month == hoje.month

    def get_total(self):
        aceitos = self.get_itens_aceitos()
        total = 0
        for a in aceitos:
            total += float(a.saida()['valor'])
        return format_money_almox(total)

    def get_data(self):
        return format_datetime(self.data)


class RequisicaoAlmoxUserMaterial(RequisicaoAlmoxMaterial, models.ModelPlus):
    requisicao = models.ForeignKeyPlus(RequisicaoAlmoxUser, related_name='item_set', on_delete=models.CASCADE)
    material = models.ForeignKeyPlus(MaterialConsumo, on_delete=models.CASCADE)
    qtd = models.IntegerField()

    class Meta:
        db_table = 'requisicaoalmoxusermaterial'


class MovimentoAlmoxEntradaTipo(models.ModelPlus):
    nome = models.CharField(max_length=25)

    class Meta:
        db_table = 'movimentoalmoxentradatipo'

    @staticmethod
    def ENTRADA():
        return MovimentoAlmoxEntradaTipo.objects.get(nome='entrada')

    @staticmethod
    def REQUISICAO_UO_MATERIAL():
        return MovimentoAlmoxEntradaTipo.objects.get(nome='requisicao_uo_material')

    @staticmethod
    def DEVOLUCAO():
        return MovimentoAlmoxEntradaTipo.objects.get(nome='devolucao')

    def __str__(self):
        if self.nome == 'devolucao':
            return 'Devolução'
        else:
            return self.nome == 'entrada' and 'Entrada' or 'Transferência entre Unidades'


class MovimentoAlmoxEntrada(models.ModelPlus):
    """
    Representa adição em estoque. O ``tipo`` pode ser um dos dois:
    1) entrada: originada de ``Entrada`` (entrada de nota fiscal); neste caso os
    campos ``empenho_consumo`` e ``entrada`` são preenchidos, enquanto
    ``requisicao_uo_material`` e ``movimento_saida`` são nulos;
    2) transferência entre UO's: originada de ``RequisicaoUOMaterial``; neste
    caso a ``requisicao_uo_material`` é preenchida e o ``empenho_consumo`` é
    nulo;
    """

    tipo = models.ForeignKeyPlus(MovimentoAlmoxEntradaTipo, on_delete=models.CASCADE)
    data = models.DateTimeField(auto_now_add=True)
    empenho_consumo = models.ForeignKeyPlus(EmpenhoConsumo, on_delete=models.CASCADE, db_column='empenhoconsumo_id', null=True)
    entrada = models.ForeignKeyPlus(Entrada, blank=True, null=True, on_delete=models.CASCADE)
    requisicao_uo_material = models.ForeignKeyPlus(
        RequisicaoAlmoxUOMaterial, on_delete=models.CASCADE, db_column='requisicaouomaterial_id', null=True
    )
    qtd = models.DecimalField(max_digits=15, decimal_places=5)
    estoque = models.DecimalField(max_digits=15, decimal_places=5)
    valor = models.DecimalField(max_digits=15, decimal_places=6)
    uo = models.ForeignKeyPlus(UnidadeOrganizacional, null=True, on_delete=models.CASCADE)
    material = models.ForeignKeyPlus(MaterialConsumo, null=True, on_delete=models.CASCADE)
    movimento_saida = models.ForeignKeyPlus(
        'MovimentoAlmoxSaida',
        null=True,
        on_delete=models.CASCADE,
        blank=True,
        help_text='Preenchido caso tipo seja "requisicao_uo_material" e representa a saída que originou esta entrada.',
    )

    class Meta:
        db_table = 'movimentoalmoxentrada'

    def __str__(self):
        return str(self.id)

    def can_delete(self, user=None):
        """
        Refere-se somente às movimentações do tipo ``entrada``.

        Condições de estorno:
        1. Usuário ser gerente do almoxarifado
        2. UO do usuário ser igual à UO da entrada
        3. A quantidade entrada ser igual à de estoque para o item
        """
        # if self.tipo.nome != 'entrada':
        #    raise Exception('Esta função deve ser usada para cancelar entradas provenientes de Notas Fiscais.')
        if tl.get_request():
            user = tl.get_user()
            grupos_permitidos = ['Coordenador de Almoxarifado', 'Coordenador de Almoxarifado Sistêmico']
            if not in_group(user, grupos_permitidos) or (self.uo != user.get_vinculo().setor.uo):
                return False
        saidas_pos_entrada = MovimentoAlmoxSaida.objects.filter(material=self.material, uo=self.uo, data__gte=self.data)
        return not saidas_pos_entrada

    @transaction.atomic
    def delete(self):
        """
        Refere-se somente à movimentações provenientes de Notas Fiscais.

        Cancela a entrada e atualiza a ``qtd_adquirida`` do empenho relacionado.
        Caso este seja o único movimento da entrada relacionada, esta também
        será removida.
        """
        if not self.can_delete():
            raise Exception('Impossível cancelar.')
        models.ModelPlus.delete(self)
        if self.empenho_consumo:
            self.empenho_consumo.atualizar_qtd_adquirida()

        if not self.entrada.movimentoalmoxentrada_set.exists():
            models.ModelPlus.delete(self.entrada)

    def get_origem(self):
        return self.tipo.nome == 'entrada' and self.entrada or self.tipo.nome == 'devolucao' or self.requisicao_uo_material.requisicao

    def get_valor_unitario(self):
        return format_money_almox(self.valor)

    def get_valor(self):
        return format_money_almox(self.qtd * self.valor)

    def get_categoria(self):
        if self.entrada.tipo_entrada == EntradaTipo.DOACAO():
            return self.material.categoria
        elif self.tipo == MovimentoAlmoxEntradaTipo.ENTRADA():
            if self.empenho_consumo_id:
                return self.empenho_consumo.material.categoria
            return self.material.categoria
        elif self.tipo == MovimentoAlmoxEntradaTipo.REQUISICAO_UO_MATERIAL():
            return self.requisicao_uo_material.material.categoria

    def get_material(self):
        if self.entrada.tipo_entrada == EntradaTipo.DOACAO():
            return self.material
        elif self.tipo == MovimentoAlmoxEntradaTipo.ENTRADA():
            if self.empenho_consumo_id:
                return self.empenho_consumo.material
            return self.material
        elif self.tipo == MovimentoAlmoxEntradaTipo.REQUISICAO_UO_MATERIAL():
            return self.requisicao_uo_material.material


class MovimentoAlmoxSaidaTipo(models.ModelPlus):
    nome = models.CharField(max_length=25)

    class Meta:
        db_table = 'movimentoalmoxsaidatipo'

    @staticmethod
    def REQUISICAO_USER_MATERIAL():
        return MovimentoAlmoxSaidaTipo.objects.get(nome='requisicao_user_material')

    @staticmethod
    def REQUISICAO_UO_MATERIAL():
        return MovimentoAlmoxSaidaTipo.objects.get(nome='requisicao_uo_material')

    def __str__(self):
        return self.nome == 'requisicao_user_material' and 'Saída para Servidor' or 'Transferência entre Unidades'


class MovimentoAlmoxSaida(models.ModelPlus):
    """
    Representa retirada em estoque. Pode ser originado de duas formas:
        1) requisição de uma pessoa e
        2) transferência entre UO's.

    ``movimento_entrada``: de onde o movimento retirou o material.
    """

    tipo = models.ForeignKeyPlus(MovimentoAlmoxSaidaTipo, on_delete=models.CASCADE)
    data = models.DateTimeField(auto_now_add=True)
    requisicao_user_material = models.ForeignKeyPlus(
        RequisicaoAlmoxUserMaterial, null=True, on_delete=models.CASCADE, db_column='requisicaousermaterial_id'
    )
    requisicao_uo_material = models.ForeignKeyPlus(
        RequisicaoAlmoxUOMaterial, null=True, on_delete=models.CASCADE, db_column='requisicaouomaterial_id'
    )
    qtd = models.DecimalField(max_digits=15, decimal_places=5)
    valor = models.DecimalField(max_digits=15, decimal_places=6)
    uo = models.ForeignKeyPlus(UnidadeOrganizacional, null=True, on_delete=models.CASCADE)
    material = models.ForeignKeyPlus(MaterialConsumo, null=True, on_delete=models.CASCADE)
    movimento_entrada = models.ForeignKeyPlus(MovimentoAlmoxEntrada, null=True, blank=True, on_delete=models.CASCADE)

    class Meta:
        db_table = 'movimentoalmoxsaida'

    def __str__(self):
        return str(self.id)

    def get_origem(self):
        return self.tipo.nome == 'requisicao_user_material' and self.requisicao_user_material.requisicao or self.requisicao_uo_material.requisicao

    @staticmethod
    def get_saidas_setor(data_inicio, data_fim, setor_id=None, uo_fornecedora_id=None):
        """
        Retorna todas as saídas realizadas para um determinado setor no período informado.
        """

        qs = MovimentoAlmoxSaida.objects.filter(
            data__range=(data_inicio, somar_dias(data_fim, 1)), requisicao_user_material__isnull=False
        ).select_related('requisicao_user_material', 'material')
        if setor_id:
            qs = qs.filter(requisicao_user_material__requisicao__setor_solicitante__id=setor_id)
        if uo_fornecedora_id:
            qs = qs.filter(requisicao_user_material__requisicao__uo_fornecedora__id=uo_fornecedora_id)

        return qs

    @classmethod
    def get_consumo_setor(cls, data_inicio, data_fim, setor_id=None, uo_fornecedora_id=None):
        materiais = {}
        for saida in cls.get_saidas_setor(data_inicio, data_fim, setor_id, uo_fornecedora_id):
            material = saida.requisicao_user_material.material
            if material in materiais:
                materiais[material]['qtd'] += saida.qtd
                materiais[material]['valor'] += saida.qtd * saida.valor
            else:
                materiais[material] = {'qtd': saida.qtd, 'valor': saida.qtd * saida.valor}
        return materiais


class ConfiguracaoEstoque(models.ModelPlus):
    uo = models.ForeignKeyPlus(UnidadeOrganizacional, on_delete=models.CASCADE)
    material = models.ForeignKeyPlus(MaterialConsumo, on_delete=models.CASCADE)
    tempo_aquisicao = models.PositiveIntegerField(verbose_name='Tempo de Aquisição')
    intervalo_aquisicao = models.PositiveIntegerField(verbose_name='Intervalo de Aquisição')

    def get_tempo_aquisicao(self):
        return self.tempo_aquisicao

    def get_intervalo_aquisicao(self):
        return self.intervalo_aquisicao

    def get_consumo_anual(self):
        hoje = datetime.today()
        um_ano_atras = hoje + timedelta(days=-365)
        datas = [um_ano_atras, hoje]
        total = self.material.saida(datas, self.uo.id)
        return total['qtd']

    def get_consumo_medio_mensal(self):
        return ceil(float(self.get_consumo_anual()) / 12)

    def get_estoque_minimo(self):
        f = self.get_intervalo_aquisicao() * 1
        return ceil(self.get_consumo_medio_mensal() * f)

    def get_estoque_maximo(self):
        return ceil(self.get_estoque_minimo() + self.get_ponto_pedido())

    def get_ponto_pedido(self):
        return ceil(self.get_estoque_minimo() + self.get_consumo_medio_mensal() + self.get_tempo_aquisicao())

    def get_qtd_ressuprimir(self):
        return ceil(self.get_consumo_medio_mensal() + self.get_intervalo_aquisicao())

    def get_maior_valor_adquirido(self):
        return MovimentoAlmoxEntrada.objects.filter(material=self.material).aggregate(valor_max=Max('valor')) or 0

    @classmethod
    def get_materiais_criticos(cls):
        uo = get_uo()
        configuracoes = list(cls.objects.filter(uo=uo).select_related('material'))
        if not configuracoes:
            return []
        material_ids = [c.material_id for c in configuracoes]
        estoque_por_material = {me.material_id: me for me in MaterialEstoque.objects.filter(material_id__in=material_ids, uo=uo)}
        materiais_criticos = []
        for r in configuracoes:
            estoque_atual = estoque_por_material.get(r.material_id)
            if estoque_atual is None:
                # preserva comportamento antigo: MaterialEstoque.objects.get(...) lançaria DoesNotExist
                estoque_atual = MaterialEstoque.objects.get(material=r.material, uo=r.uo)
            if estoque_atual.quantidade <= r.get_estoque_minimo():
                materiais_criticos.append(r)
        return materiais_criticos

    def calcular_previsao_estoque(self):
        self.intervalo_aquisicao = self.get_intervalo_aquisicao()
        self.tempo_aquisicao = self.get_tempo_aquisicao()
        self.estoque_minimo = self.get_estoque_minimo()
        self.estoque_maximo = self.get_estoque_maximo()
        self.consumo_medio_mensal = self.get_consumo_medio_mensal()
        self.maior_valor_adquirido = self.get_maior_valor_adquirido()
        self.qtd_ressuprimir = self.get_qtd_ressuprimir()
        self.ponto_pedido = self.get_ponto_pedido()

        estoque_atual = self.material.get_estoque_atual(self.uo)
        self.esta_em_estado_de_compra = estoque_atual > self.estoque_minimo and estoque_atual <= self.ponto_pedido
        self.esta_em_ponto_critico = estoque_atual <= self.estoque_minimo
        self.esta_em_estoque_normal = estoque_atual > self.ponto_pedido and estoque_atual < self.estoque_maximo
        self.esta_em_estoque_maximo = estoque_atual >= self.estoque_maximo
        self.qtd_ressuprimir_atual = self.estoque_maximo - estoque_atual
        if self.qtd_ressuprimir_atual < 0:
            self.qtd_ressuprimir_atual = 0


class MaterialEstoque(models.ModelPlus):
    uo = models.ForeignKeyPlus(UnidadeOrganizacional, on_delete=models.CASCADE)
    material = models.ForeignKeyPlus(MaterialConsumo, on_delete=models.CASCADE)
    valor_medio = models.DecimalField(max_digits=15, decimal_places=6)
    quantidade = models.DecimalField(max_digits=15, decimal_places=5, verbose_name='Estoque')

    def __str__(self):
        return str(self.id)

    def save(self, *args, **kargs):
        super().save(*args, **kargs)


class DevolucaoMaterial(models.ModelPlus):
    material = models.ForeignKeyPlus(MaterialConsumo, on_delete=models.CASCADE)
    quantidade = models.DecimalField(max_digits=15, decimal_places=5, verbose_name='Qtd a ser devolvida')
    uo = models.ForeignKeyPlus(UnidadeOrganizacional, on_delete=models.CASCADE)
    processo = models.CharFieldPlus('Número do Processo', max_length=255, blank=True, null=True)
    requisicao_user = models.ForeignKeyPlus(RequisicaoAlmoxUser, null=True, on_delete=models.CASCADE)
    requisicao_uo = models.ForeignKeyPlus(RequisicaoAlmoxUO, null=True, on_delete=models.CASCADE)

    def __str__(self):
        return str(self.id)
