import hashlib
import operator
import re
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from functools import reduce

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import DecimalField, Exists, F, Max, OuterRef, Q, Sum

from almoxarifado.models import Empenho, Entrada, EntradaTipo
from comum.models import Configuracao, Sala, Vinculo
from comum.utils import get_uo, tl
from djtools.contrib.admin.helpers import get_admin_object_url
from djtools.db import models
from djtools.db.models import CurrentUserField, SearchField
from djtools.templatetags.filters import format_money_almox, in_group
from djtools.utils import calendario, send_notification, to_ascii, user_has_perm_or_without_request
from patrimonio.managers import (
    InventariosAtivosGerenciaveisManager,
    InventariosAtivosManager,
    InventariosBaixadosManager,
    InventariosDepreciaveisManager,
    InventariosPendentesManager,
)
from rh.models import Servidor, Situacao, UnidadeOrganizacional


class InventarioTipoUsoPessoal(models.ModelPlus):
    descricao = models.CharField(max_length=250, unique=True)
    requisicao_periodo_inicio = models.DateTimeField(null=True, blank=True)
    requisicao_periodo_fim = models.DateTimeField(null=True, blank=True)
    texto_requisicao = models.TextField(help_text='Texto a ser informado no questionário', blank=True)
    enviar_email_inscrito = models.BooleanField(default=False, null=True)
    enviar_email_copia = models.TextField(max_length=75, blank=True)

    class Meta:
        verbose_name = 'Inventário Tipo Uso Pessoal'
        verbose_name_plural = 'Inventários Tipo Uso Pessoal'

    def __str__(self):
        return self.descricao


class RequisicaoInventarioUsoPessoal(models.ModelPlus):
    tipo_uso_pessoal = models.ForeignKeyPlus(InventarioTipoUsoPessoal, on_delete=models.CASCADE)
    vinculo = models.ForeignKeyPlus('comum.Vinculo')
    horario = models.DateTimeField(auto_now_add=True)
    cadastrado = models.BooleanField(default=False, null=True)  # campo utilizado para controlar cadastro ao site FNDE
    indicado = models.BooleanField(default=False, null=True)  # campo utilizado para controlar indicação no site FNDE

    class Meta:
        verbose_name = 'Requisição de Tipo Uso Pessoal'
        verbose_name_plural = 'Requisições de Tipo Uso Pessoal'

    def get_uo(self):
        if self.vinculo.setor:
            return self.vinculo.setor.uo

    get_uo.short_description = 'Origem'

    @classmethod
    def tipos_uso_pessoal_permitidos(cls, user):
        # somente para servidor
        try:
            relacionamento = user.get_vinculo().relacionamento
        except Exception:
            return cls.objects.none()

        if not user.get_vinculo().eh_servidor():
            return cls.objects.none()
        else:
            servidor = relacionamento

        # é professor?
        if (
            servidor.situacao.codigo
            in (servidor.situacao.ATIVO_PERMANENTE, servidor.situacao.CONT_PROF_SUBSTITUTO, servidor.situacao.CONT_PROF_TEMPORARIO)
            and servidor.categoria == 'Docente'
        ):
            # busca tipos ainda não respondidos
            tipo_uso_pessoal = InventarioTipoUsoPessoal.objects.filter(
                requisicao_periodo_inicio__lte=datetime.now(), requisicao_periodo_fim__gte=datetime.today()
            ).exclude(id__in=cls.objects.filter(vinculo=user.get_vinculo()).values_list('tipo_uso_pessoal', flat=True))

            return tipo_uso_pessoal

        return cls.objects.none()

    def atendido(self):
        return Inventario.objects.filter(responsavel_vinculo=self.vinculo, tipo_uso_pessoal=self.tipo_uso_pessoal).exists()

    atendido.short_description = 'Atendido'
    atendido.boolean = True


class PlanoContas(models.ModelPlus):
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


class CategoriaMaterialPermanente(models.ModelPlus):
    SEARCH_FIELDS = ['codigo', 'nome']

    codigo = models.CharField('Código', max_length=10, unique=True)
    nome = models.CharField(max_length=100, unique=True)
    percentual_residual = models.FloatField(default=0.1)
    vida_util_em_anos = models.FloatField(default=10)
    plano_contas = models.ForeignKeyPlus(PlanoContas, null=True, on_delete=models.CASCADE)
    omitir = models.BooleanField(default=False)

    class Meta:
        db_table = 'categoriamaterialpermanente'
        verbose_name = 'Elemento de Despesa de Mat. Permanente'
        verbose_name_plural = 'Elementos de Despesa de Mat. Permanente'

    def __str__(self):
        return f'{self.codigo} - {self.nome}'


class EmpenhoPermanente(models.ModelPlus):
    empenho = models.ForeignKeyPlus(Empenho, on_delete=models.CASCADE)
    categoria = models.ForeignKeyPlus(CategoriaMaterialPermanente, on_delete=models.CASCADE)
    descricao = models.TextField('Descrição')
    qtd_empenhada = models.PositiveIntegerField(
        'Qtd. Empenhada',
        db_column='qtdempenhada',
        help_text='O material permanente é contado por unidade tombada; portanto, a quantidade é sempre um número inteiro.',
    )
    qtd_adquirida = models.PositiveIntegerField('Quantidade de itens adquirida', default=0, db_column='qtdadquirida')
    valor = models.DecimalField(max_digits=15, decimal_places=6)

    class Meta:
        db_table = 'empenhopermanente'
        verbose_name = 'Empenho Permanente'
        verbose_name_plural = 'Empenhos Permanentes'

        ordering = ['empenho', 'id']
        permissions = (('change_empenhopermanente_movimentados', 'Pode alterar empenhopermanente mov'),)

    def __str__(self):
        return f'Empenho Permanente {self.pk}'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.entradapermanente_set.update(categoria=self.categoria, descricao=self.descricao, valor=self.valor)

        self.empenho.atualizar_informacoes()  # força a atualização do status durante inclusão/alteração

    def can_delete(self, user=None):
        if user_has_perm_or_without_request('patrimonio.delete_empenhopermanente'):
            return not self.qtd_adquirida
        return False

    def can_change(self, user=None):
        return user_has_perm_or_without_request('patrimonio.change_empenhopermanente')

    def delete(self):
        """
        Simplesmente remove o item do empenho. Caso ele seja o único item do
        empenho, este também será removido.
        """
        if not self.can_delete():
            raise Exception('Impossível cancelar. O item foi adquirido.')
        models.Model.delete(self)
        if not self.empenho.get_itens().exists():
            models.Model.delete(self.empenho)

    def get_absolute_url(self):
        return get_admin_object_url(self)

    def get_delete_url(self):
        return f'/almoxarifado/empenhopermanente/{self.id}/remover/'

    @staticmethod
    def get_pendentes(empenho):
        lista = []
        for empenho_permanente in EmpenhoPermanente.objects.filter(empenho=empenho).order_by('id'):
            if empenho_permanente.get_qtd_pendente() > 0:
                lista.append(empenho_permanente)
        return lista

    def get_qtd_adquirida(self):
        """
        Calcula a quantidade adquirida com base nas entradas na classe EntradaPermanente.
        """
        qtd_adquirida = 0
        for entrada_permanente in self.entradapermanente_set.all():
            qtd_adquirida += entrada_permanente.qtd
        return qtd_adquirida

    def atualizar_qtd_adquirida(self):
        """
        Assegura que o atributo `qtd_adquirida` seja igual ao método `get_qtd_adquirida`.
        Esta função é usada em caso de cancelamento de movimentação.
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
        return self.descricao

    def get_categoria(self):
        return self.categoria

    def valor_adquirido(self):
        return self.qtd_adquirida * self.valor

    def get_valor(self):
        return format_money_almox(self.valor)

    def valor_empenhado(self):
        return self.qtd_empenhada * self.valor

    def get_valor_empenhado(self):
        return format_money_almox(self.valor_empenhado())


class EntradaPermanente(models.ModelPlus):
    entrada = models.ForeignKeyPlus(Entrada, on_delete=models.CASCADE)
    categoria = models.ForeignKeyPlus(CategoriaMaterialPermanente, on_delete=models.CASCADE)
    descricao = models.TextField('Descrição')
    qtd = models.PositiveIntegerField('Quantidade', help_text='Cada unidade gera um tombamento; portanto, a quantidade é sempre um número inteiro.')
    valor = models.DecimalField(max_digits=15, decimal_places=6)
    empenho_permanente = models.ForeignKeyPlus(
        EmpenhoPermanente, null=True, on_delete=models.CASCADE, help_text='Vazio caso seja entrada do tipo doação.'
    )

    class Meta:
        db_table = 'entradapermanente'
        verbose_name = 'Entrada Permanente'
        verbose_name_plural = 'Entradas Permanentes'

    @transaction.atomic
    def save(self, *args, **kwargs):
        """
        Salva o ``self`` e cria os inventários (caso ``self`` esteja sendo criado).
        """
        user = kwargs.pop('user', None)
        novo = not self.pk
        super().save(*args, **kwargs)
        if novo:
            proximo_numero = Inventario.get_proximo_numero()
            status_pendente = InventarioStatus.PENDENTE()
            for numero in range(proximo_numero, proximo_numero + self.qtd):
                inventario = Inventario(
                    numero=numero, entrada_permanente=self, status=status_pendente, valor=self.valor, estado_conservacao=Inventario.CONSERVACAO_BOM
                )
                inventario.save(user=user)
                Inventario.efetuar_pendencia(inventarios=inventario, entrada_permanente=self)

    def can_delete(self, user=None):
        """
        Condições de estorno:
        1. Usuário ser gerente do almoxarifado ou gerente do patrimônio.
        2. UO do usuário ser igual à UO da entrada
        3. Todos os inventários gerados estão pendentes.
        """
        if tl.get_request():
            grupos_permitidos = [
                'Coordenador de Patrimônio',
                'Coordenador de Patrimônio Sistêmico',
                'Coordenador de Almoxarifado',
                'Coordenador de Almoxarifado Sistêmico',
            ]
            if (not in_group(tl.get_user(), grupos_permitidos)) or (self.entrada.uo != get_uo()):
                return False
        return not self.inventario_set.exclude(status=InventarioStatus.PENDENTE()).exists()

    def delete(self):
        """
        Remove self e invoca self.empenho_permanente.atualizar_qtd_adquirida().
        Caso self.entrada não tenha mais itens, self.entrada será removida.
        """
        if not self.can_delete():
            raise Exception('Impossível cancelar. O movimento já teve saídas', ' ou o usuário logado não tem permissões.')
        entrada = self.entrada
        models.Model.delete(self)  # Já remove os inventários relacionados
        if self.empenho_permanente:
            # Caso a entrada tenha sido gerada por um empenho, este deverá ser
            # atualizado.
            self.empenho_permanente.atualizar_qtd_adquirida()
        # A entrada só é descartada quando fica realmente vazia: se houver itens cancelados,
        # ela é o que sustenta a aba "Itens Removidos" e precisa sobreviver.
        if not entrada.entradapermanente_set.exists() and not entrada.itens_cancelados.exists():
            models.Model.delete(entrada)

    @classmethod
    def cancelaveis(cls, entrada) -> models.QuerySet[EntradaPermanente]:
        """
        Itens da entrada que ainda podem ser cancelados pelo coordenador de patrimônio.

        Espelha :meth:`get_impedimentos_cancelamento` em uma única consulta, para responder
        "esta entrada ainda tem algo a remover?" sem percorrer item a item.

        Args:
            entrada: Entrada de material permanente cujos itens serão filtrados.

        Returns:
            QuerySet dos itens sem inventário baixado.
        """
        return cls.objects.filter(entrada=entrada).exclude(inventario__status=InventarioStatus.BAIXADO())

    def get_impedimentos_cancelamento(self) -> list[str]:
        """
        Motivos que impedem o cancelamento deste item pelo coordenador de patrimônio.

        Diferente de :meth:`can_delete` (estorno, que exige inventários pendentes), o
        cancelamento aceita itens já movimentados — a carga contábil, as transferências e
        demais movimentações são removidas junto. Só é barrado o inventário baixado, que não
        dá para desfazer com segurança.

        Returns:
            Lista de motivos; vazia quando o item pode ser cancelado.
        """
        impedimentos = []
        if self.inventario_set.filter(status=InventarioStatus.BAIXADO()).exists():
            impedimentos.append('possui inventário baixado')
        return impedimentos

    def pode_cancelar(self) -> bool:
        """Indica se o item pode ser cancelado pelo coordenador de patrimônio."""
        return not self.get_impedimentos_cancelamento()

    @transaction.atomic
    def cancelar(self, justificativa: str) -> ItemEntradaCancelado:
        """
        Cancela o item, guardando um registro auditável do que foi removido.

        Remove os inventários gerados e, em cascata, toda a sua movimentação (carga
        contábil, transferências, cautelas, reavaliações, conferências) e atualiza o
        empenho de origem. A entrada é preservada, para que o registro do cancelamento
        continue visível na aba "Itens Removidos".

        Args:
            justificativa: Motivo informado pelo coordenador de patrimônio.

        Returns:
            O registro de auditoria criado.

        Raises:
            ValidationError: Se o item possuir impedimentos de cancelamento.
        """
        impedimentos = self.get_impedimentos_cancelamento()
        if impedimentos:
            raise ValidationError('Não é possível cancelar o item "{}": {}.'.format(self.descricao, '; '.join(impedimentos)))

        numeros = self.inventario_set.order_by('numero').values_list('numero', flat=True)
        registro = ItemEntradaCancelado.objects.create(
            entrada=self.entrada,
            categoria=self.categoria,
            descricao=self.descricao,
            qtd=self.qtd,
            valor=self.valor,
            empenho_permanente=self.empenho_permanente,
            numeros_inventario=', '.join(str(numero) for numero in numeros),
            justificativa=justificativa,
        )
        empenho_permanente = self.empenho_permanente
        models.Model.delete(self)  # a cascata remove os inventários e sua movimentação
        if empenho_permanente:
            empenho_permanente.atualizar_qtd_adquirida()
        return registro

    def get_empenho(self):
        if self.empenho_permanente:
            return self.empenho_permanente.empenho

    def get_valor_unitario(self):
        return format_money_almox(self.valor)

    def get_valor(self):
        return format_money_almox(self.qtd * self.valor)

    def get_categoria(self):
        return self.categoria

    def get_material(self):
        return self.descricao


class ItemEntradaCancelado(models.ModelPlus):
    """Registro auditável de um item de entrada permanente cancelado pelo coordenador de patrimônio."""

    entrada = models.ForeignKeyPlus(Entrada, on_delete=models.CASCADE, related_name='itens_cancelados')
    categoria = models.ForeignKeyPlus(CategoriaMaterialPermanente, null=True, on_delete=models.SET_NULL)
    descricao = models.TextField('Descrição')
    qtd = models.DecimalField('Quantidade', max_digits=15, decimal_places=5)
    valor = models.DecimalField('Valor Unitário', max_digits=15, decimal_places=6)
    empenho_permanente = models.ForeignKeyPlus(EmpenhoPermanente, null=True, blank=True, on_delete=models.SET_NULL)
    numeros_inventario = models.TextField('Inventários Removidos', blank=True)
    justificativa = models.TextField('Justificativa')
    cancelado_por = CurrentUserField(on_delete=models.SET_NULL)
    cancelado_em = models.DateTimeField('Cancelado em', auto_now_add=True)

    class Meta:
        verbose_name = 'Item de Entrada Cancelado'
        verbose_name_plural = 'Itens de Entrada Cancelados'
        ordering = ['-cancelado_em']

    def __str__(self):
        return f'{self.descricao} ({self.entrada})'

    def get_valor_total(self) -> Decimal:
        return self.qtd * self.valor

    def get_valor_unitario(self) -> str:
        return format_money_almox(self.valor)

    def get_valor(self) -> str:
        return format_money_almox(self.get_valor_total())


class InventarioStatus(models.ModelPlus):
    nome = models.CharField(max_length=20)

    class Meta:
        db_table = 'inventariostatus'
        ordering = ['nome']

    def __str__(self):
        return self.nome.capitalize()

    @staticmethod
    def PENDENTE():
        return InventarioStatus.objects.get(nome='pendente')

    @staticmethod
    def ATIVO():
        return InventarioStatus.objects.get(nome='ativo')

    @staticmethod
    def BAIXADO():
        return InventarioStatus.objects.get(nome='baixado')


class InventarioRotulo(models.ModelPlus):
    nome = models.CharField(max_length=100, null=False, verbose_name='Nome')
    descricao = models.TextField(max_length=500, null=True, verbose_name='Descrição')
    unidade_organizacional = models.ForeignKeyPlus(
        UnidadeOrganizacional, db_column='unidadeorganizacional_id', editable=False, default=get_uo, on_delete=models.CASCADE
    )

    objects = models.Manager()

    class Meta:
        db_table = 'inventariorotulo'
        verbose_name = 'Rótulo'
        verbose_name_plural = 'Rótulos'

        ordering = ['nome']

    def __str__(self):
        return self.nome


class InventarioCategoria(models.ModelPlus):
    nome = models.CharField(max_length=100)

    class Meta:
        verbose_name = 'Categoria de Inventário'
        verbose_name_plural = 'Categorias de Inventários'

    def __str__(self):
        return self.nome


class Inventario(models.ModelPlus):
    SEARCH_FIELDS = ['campo_busca']
    CONSERVACAO_NAO_APLICADA = ''
    CONSERVACAO_BOM = 'bom'
    CONSERVACAO_OCIOSO = 'ocioso'
    CONSERVACAO_RECUPERAVEL = 'recuperavel'
    CONSERVACAO_ANTIECONOMICO = 'antieconomico'
    CONSERVACAO_IRRECUPERAVEL = 'irrecuperavel'
    CONSERVACAO_IRREVERSIVEL = 'irreversivel'
    CHOICES_CONSERVACAO = (
        (CONSERVACAO_NAO_APLICADA, 'Não aplicar'),
        (CONSERVACAO_BOM, 'Bom'),
        (CONSERVACAO_OCIOSO, 'Ocioso'),
        (CONSERVACAO_RECUPERAVEL, 'Recuperável'),
        (CONSERVACAO_ANTIECONOMICO, 'Antieconômico'),
        (CONSERVACAO_IRREVERSIVEL, 'Irreversível'),
    )
    numero = models.IntegerField('Número', unique=True)
    status = models.ForeignKeyPlus(InventarioStatus, on_delete=models.CASCADE)
    rotulos = models.ManyToManyField(InventarioRotulo, blank=True)
    numero_serie = models.CharField(max_length=50, blank=True, db_column='numeroserie')
    entrada_permanente = models.ForeignKeyPlus(EntradaPermanente, db_column='entradapermanente_id', on_delete=models.CASCADE)
    campo_busca = SearchField(attrs=['numero', 'get_descricao'])
    sala = models.ForeignKeyPlus(Sala, null=True, blank=True, on_delete=models.CASCADE)
    categoria = models.ForeignKeyPlus(InventarioCategoria, null=True, blank=True, on_delete=models.CASCADE)
    estado_conservacao = models.CharField('Estado de conservação', max_length=30, blank=True, choices=CHOICES_CONSERVACAO)
    responsavel_vinculo = models.ForeignKeyPlus('comum.Vinculo', null=True, blank=True)
    carga_contabil = models.OneToOneField(
        'patrimonio.InventarioCargaContabil', null=True, blank=True, related_name='inventario_atual', on_delete=models.CASCADE
    )  # redundante
    tipo_uso_pessoal = models.ForeignKeyPlus(InventarioTipoUsoPessoal, null=True, blank=True, on_delete=models.CASCADE)
    valor = models.DecimalField(max_digits=15, decimal_places=6, null=True)
    descricao = models.TextField('Descrição', null=True, blank=True)
    observacao = models.TextField('Observação', null=True, blank=True)

    # Managers
    objects = models.Manager()
    pendentes = InventariosPendentesManager()
    ativos = InventariosAtivosManager()
    baixados = InventariosBaixadosManager()
    ativos_gerenciaveis = InventariosAtivosGerenciaveisManager()
    depreciaveis = InventariosDepreciaveisManager()

    class Meta:
        db_table = 'inventario'
        ordering = ['numero']
        verbose_name = 'Inventário'
        verbose_name_plural = 'Inventários'

        permissions = (
            # PERMISSÕES PARA BUSCAR E VER DETALHES DE INVENTÁRIOS
            ('ver_inventarios', 'Pode buscar e visualizar inventários'),
            ('pode_ver_propria_carga', 'Pode ver a própria carga'),
            # PERMISSÕES PARA EDITAR INVENTÁRIOS
            ('editar_do_meu_campus', 'Pode editar inventários do seu campus'),
            ('editar_todos', 'Pode editar todos os inventários'),
            # PERMISSÕES PARA VISUALIZAÇÃO DE RELATÓRIOS
            ('pode_ver_relatorios', 'Pode ver todos os relatórios'),
            # PERMISSÕES PARA ALTERAR MANUALMENTE A CARGA CONTABIL DOS INVENTÁRIOS
            ('pode_alterar_carga_contabil', 'Pode alterar a carga contábil'),
            ('pode_alterar_carga_contabil_todos', 'Pode alterar a carga contábil de todos'),
            ('pode_alterar_carga_contabil_do_campus', 'Pode alterar a carga contábil do campus'),
            # MIGRAÇÃO DE ACERVO POR PLANILHA
            ('pode_migrar_inventario', 'Pode migrar inventários por planilha'),
        )

    ##
    # demanda 709
    # situação do inventário
    SITUACAO_REQUISICAO_STATUS_AGUARDANDO_APROVACAO_SERVIDOR_DESTINO = 1  # mesmo valor de Requisicao
    SITUACAO_REQUISICAO_STATUS_DEFERIDA_AGUARDANDO_INFORMACAO_PA_ORIGEM = 4  # mesmo valor de Requisicao
    SITUACAO_REQUISICAO_STATUS_DEFERIDA_AGUARDANDO_INFORMACAO_PA_DESTINO = 6  # mesmo valor de Requisicao
    SITUACAO_MOVIMENTOPATRIM_TIPO_PENDENCIA = 'pendência'  # mesmo valor de MovimentoPatrimTipo.nome
    SITUACAO_MOVIMENTOPATRIM_TIPO_BAIXA = 'baixa'  # mesmo valor de MovimentoPatrimTipo.nome

    def __str__(self):
        return f'{self.numero!s} - {self.get_descricao()}'

    def delete(self, *args, **kwargs):
        cache.delete('inventarios_inconsistente_ids')
        super().delete(*args, **kwargs)

    @transaction.atomic()
    def save(self, *args, **kwargs):
        if kwargs.pop('limpar_cache', True):
            cache.delete('inventarios_inconsistente_ids')
        user = kwargs.pop('user', None)
        novo = not self.pk
        super().save(*args, **kwargs)
        if novo:
            uo = None
            if self.entrada_permanente.entrada.tipo_entrada == EntradaTipo.COMPRA():
                uo = self.entrada_permanente.empenho_permanente.empenho.uo

            if not uo:
                uo = self.entrada_permanente.entrada.uo

            carga_contabil = InventarioCargaContabil.objects.create(
                usuario=user, inventario=self, campus=uo, tipo=InventarioCargaContabil.TIPO_MANUAL
            )
            self.descricao = self.entrada_permanente.descricao
            self.carga_contabil = carga_contabil
            self.save()

    @property
    def situacao(self):
        situacao = None

        ultimo_movimento = self.get_ultimo_movimento_patrimonio()
        ultima_requisicao = self.get_ultima_requisicao()

        if ultimo_movimento and ultimo_movimento.tipo in [MovimentoPatrimTipo.PENDENCIA(), MovimentoPatrimTipo.BAIXA()]:
            #
            situacao = ultimo_movimento.tipo.nome
            #

        elif ultima_requisicao and ultima_requisicao.status in [
            Inventario.SITUACAO_REQUISICAO_STATUS_AGUARDANDO_APROVACAO_SERVIDOR_DESTINO,
            Inventario.SITUACAO_REQUISICAO_STATUS_DEFERIDA_AGUARDANDO_INFORMACAO_PA_ORIGEM,
            Inventario.SITUACAO_REQUISICAO_STATUS_DEFERIDA_AGUARDANDO_INFORMACAO_PA_DESTINO,
        ]:
            #
            situacao = ultima_requisicao.status
            #

        return situacao

    def get_situacao_display(self):
        return Inventario.get_situacao_display_from_situacao(self.situacao)

    @staticmethod
    def get_situacao_display_from_situacao(situacao):
        situacao_display = '-'
        if situacao:
            if situacao in [
                Inventario.SITUACAO_REQUISICAO_STATUS_AGUARDANDO_APROVACAO_SERVIDOR_DESTINO,
                Inventario.SITUACAO_REQUISICAO_STATUS_DEFERIDA_AGUARDANDO_INFORMACAO_PA_ORIGEM,
                Inventario.SITUACAO_REQUISICAO_STATUS_DEFERIDA_AGUARDANDO_INFORMACAO_PA_DESTINO,
            ]:
                requisicao_fake = Requisicao(status=situacao)
                try:
                    situacao_display = requisicao_fake.get_status_display()
                except Exception:
                    situacao_display = '?'

            elif situacao in [Inventario.SITUACAO_MOVIMENTOPATRIM_TIPO_PENDENCIA, Inventario.SITUACAO_MOVIMENTOPATRIM_TIPO_BAIXA]:
                try:
                    if situacao == Inventario.SITUACAO_MOVIMENTOPATRIM_TIPO_PENDENCIA:
                        situacao_display = MovimentoPatrimTipo.PENDENCIA().nome
                    else:
                        situacao_display = MovimentoPatrimTipo.BAIXA().nome
                except Exception:
                    situacao_display = '?'
        return situacao_display

    def get_ultimo_movimento_patrimonio(self):
        return MovimentoPatrim.objects.filter(inventario__id=self.id).order_by('-id').first()

    def get_ultima_requisicao(self):
        requisicao_item = RequisicaoItem.objects.filter(inventario__id=self.id)
        if requisicao_item.exists():
            requisicao = requisicao_item.order_by('-id').first().requisicao
        else:
            requisicao = None
        return requisicao

    def user_pode_editar(self):
        """Testa se o usuário autenticado pode editar o inventário"""
        user = tl.get_user()
        if user.has_perm('patrimonio.editar_todos'):
            return True
        return user.has_perm('patrimonio.editar_do_meu_campus') and self.eh_do_meu_campus()

    def eh_do_meu_campus(self):
        """
        Testa se o campus do usuário autenticado é igual ao do responsável do
        inventário
        """
        return self.responsavel_vinculo and self.responsavel_vinculo.setor and self.responsavel_vinculo.setor.uo == get_uo()

    def _get_responsavel(self):
        """É o valor calculado da coluna ``responsavel``"""
        return Vinculo.objects.filter(
            id__in=MovimentoPatrim.objects.filter(
                id__in=list(MovimentoPatrim.objects.filter(inventario_id=self.pk).aggregate(max=Max('id')).values())
            ).values('vinculo_id')
        ).first()

    @staticmethod
    def get_proximo_numero():
        """próximo número disponível para tombamento"""
        if Inventario.objects.exists():
            return next(iter(Inventario.objects.aggregate(max=Max('numero')).values())) + 1
        return 1

    @staticmethod
    def set_cache_carga_contabil_inconsistente():
        if cache.get('inventarios_inconsistente_ids') is None:
            inventarios_ids = Inventario.objects.exclude(carga_contabil__campus=F('responsavel_vinculo__setor__uo')).values_list('id', flat=True)
            cache.set('inventarios_inconsistente_ids', list(inventarios_ids), None)

    @classmethod
    def get_carga_contabil_inconsistentes(cls, user):
        if user.has_perm('patrimonio.pode_alterar_carga_contabil_do_campus'):
            user_uo = get_uo(user)
            responsavel_uo = Vinculo.objects.filter(id=OuterRef('responsavel_vinculo_id'), setor__uo_id=user_uo.id)
            cargacontabil_uo = InventarioCargaContabil.objects.filter(id=OuterRef('carga_contabil_id'), campus_id__isnull=False).exclude(
                campus_id=user_uo.id
            )
            return (
                Inventario.objects.annotate(
                    responsavel_uo=Exists(responsavel_uo.values('id')), cargacontabil_uo=Exists(cargacontabil_uo.values('id'))
                )
                .filter(responsavel_uo=True, cargacontabil_uo=True)
                .order_by()
            )
        return cls.objects.none()

    @classmethod
    def get_carga_contabil_inconsistentes_campus(cls, user):
        Inventario.set_cache_carga_contabil_inconsistente()
        if user.has_perm('patrimonio.pode_alterar_carga_contabil_do_campus'):
            return cls.objects.filter(id__in=cache.get('inventarios_inconsistente_ids'), carga_contabil__campus=get_uo(user)).exclude(
                status=InventarioStatus.BAIXADO()
            )

        return cls.objects.none()

    @classmethod
    def get_pendentes(cls, uo=None):
        inventarios = cls.objects.filter(responsavel_vinculo=None, status__nome='pendente')
        if uo:
            requisicoes = Requisicao.get_qs_aguardando().filter(itens__inventario__id=OuterRef('id'))
            inventarios = inventarios.filter(entrada_permanente__entrada__uo_id=uo.pk)
            inventarios = inventarios.annotate(requisicoes=Exists(requisicoes)).filter(requisicoes=False)
        return inventarios

    @staticmethod
    def servidores_inativos_com_carga(uo):
        return Inventario.get_servidores_com_carga(ativo=False, tem_funcao=None, uo=uo)

    @staticmethod
    def get_servidores_com_carga(ativo, tem_funcao, uo):
        ids_servidores = (
            Inventario.objects.filter(responsavel_vinculo__isnull=False).values_list('responsavel_vinculo__id_relacionamento', flat=True).all()
        )
        servidores = Servidor.objects.filter(id__in=ids_servidores)

        if isinstance(ativo, bool):
            servidores = servidores.filter(ativo=ativo)

        if tem_funcao in (True, False):
            servidores = servidores.exclude(funcao__isnull=tem_funcao)

        if uo:
            servidores = servidores.filter(setor__uo=uo)

        return servidores

    @staticmethod
    def get_servidores_com_carga_do_meu_campus(uo):
        ids_servidores = (
            Inventario.objects.filter(responsavel_vinculo__isnull=False).values_list('responsavel_vinculo__id_relacionamento', flat=True).all()
        )
        user = tl.get_user()
        if in_group(user, ['Contador de Patrimônio Sistêmico']):
            return Servidor.objects.filter(id__in=ids_servidores)
        return Servidor.objects.filter(Q(id__in=ids_servidores), Q(setor__uo=uo) | Q(setor_exercicio__uo__equivalente=uo))

    @staticmethod
    def get_servidores_disponivel_transferencia():
        SITUACOES_DISPONIVEIS_TRANSFERENCIA_INVENTARIO = [
            Situacao.ATIVO_PERMANENTE,
            Situacao.COLABORADOR_PCCTAE,
            Situacao.EXERCICIO_PROVISORIO,
            Situacao.COLABORADOR_ICT,
            Situacao.EXERC_DESCENT_CARREI,
            Situacao.EXERC_7_ART93_8112,
            Situacao.NOMEADO_CARGO_COMIS,
            Situacao.CONT_PROF_SUBSTITUTO,
            Situacao.CONT_PROF_TEMPORARIO,
            Situacao.CONTR_PROF_VISITANTE,
            Situacao.EXERC_LEI_13681_18,
            Situacao.CEDIDO_REQUISITADO,
        ]
        return Servidor.objects.vinculados().filter(
            ativo=True, situacao__codigo__in=SITUACOES_DISPONIVEIS_TRANSFERENCIA_INVENTARIO, setor__isnull=False
        )

    @staticmethod
    def get_inventarios_carga_user(servidor, **kwargs):
        """Retorno: {'inventarios': [], 'valor_total': Decimal}"""

        if kwargs.get('tipo') == 'anual':
            return Inventario.get_inventarios_anual(servidor, kwargs['ano'])
        elif kwargs.get('tipo') == 'recebimento':
            return Inventario.get_inventarios_carga_user_periodo(servidor, kwargs['datas'])
        elif (
            kwargs.get('tipo') is None
            or kwargs.get('tipo') == 'responsabilidade'
            or kwargs.get('tipo') == 'nada_consta_desligamento'
            or kwargs.get('tipo') == 'nada_consta_remanejamento'
        ):
            return Inventario.get_inventarios_carga_user_geral(servidor)

    @staticmethod
    def get_inventarios_carga_user_geral(servidor):
        inventarios = (
            Inventario.objects.filter(responsavel_vinculo=servidor.get_vinculo())
            .exclude(entrada_permanente__categoria__codigo='93')
            .order_by('numero')
        )

        descricoes = dict(
            DescricaoInventario.objects.filter(
                id__in=DescricaoInventario.objects.values('inventario_id').annotate(max=Max('id')).values('max')
            ).values_list('inventario_id', 'descricao')
        )

        inventarios = (
            inventarios.all()
            .select_related('sala', 'entrada_permanente')
            .values(
                'numero',
                'estado_conservacao',
                'entrada_permanente__descricao',
                'entrada_permanente__valor',
                'id',
                'sala__nome',
                'sala__predio__nome',
                'sala__predio__uo__sigla',
                'responsavel_vinculo__setor__uo__setor__sigla',
                'tipo_uso_pessoal',
                'valor',
            )
            .order_by('numero')
        )

        return {'inventarios': inventarios, 'descricoes': descricoes}

    @staticmethod
    def get_inventarios_carga_user_periodo(servidor, datas):
        """
        Retorna lista de inventários que foram movimentados para o usuário no
        período e que continuam na carga deste.
        """
        movimentos = (
            MovimentoPatrim.objects.filter(vinculo=servidor.get_vinculo(), data__range=(datas[0], calendario.somar_dias(datas[1], 1)))
            .values('inventario_id')
            .annotate(max=Max('id'))
            .values('max')
        )

        inventarios = (
            Inventario.objects.filter(movimentopatrim__vinculo=servidor.get_vinculo(), movimentopatrim__in=movimentos)
            .exclude(entrada_permanente__categoria__codigo='93', entrada_permanente__categoria__omitir=True)
            .values(
                'numero',
                'estado_conservacao',
                'entrada_permanente__descricao',
                'entrada_permanente__valor',
                'id',
                'sala__nome',
                'sala__predio__nome',
                'sala__predio__uo__sigla',
                'responsavel_vinculo__setor__uo__setor__sigla',
                'valor',
            )
            .order_by('numero')
        )

        descricoes = dict(
            DescricaoInventario.objects.filter(
                id__in=DescricaoInventario.objects.values('inventario_id').annotate(max=Max('id')).values('max')
            ).values_list('inventario_id', 'descricao')
        )

        return {'inventarios': inventarios, 'descricoes': descricoes}

    @staticmethod
    def get_inventarios_anual(user, ano):
        descricoes = DescricaoInventario.objects.filter(
            id__in=DescricaoInventario.objects.values('inventario_id').annotate(max=Max('id')).values('max')
        )

        movimentos = (
            MovimentoPatrim.objects.filter(vinculo=user.get_vinculo(), data__lt=datetime(ano + 1, 1, 1))
            .values('inventario_id')
            .annotate(max=Max('id'))
            .values('max')
        )

        inventarios = (
            Inventario.objects.filter(movimentopatrim__vinculo=user.get_vinculo(), movimentopatrim__in=movimentos)
            .values(
                'numero',
                'entrada_permanente__descricao',
                'entrada_permanente__valor',
                'id',
                'estado_conservacao',
                'sala__nome',
                'sala__predio__nome',
                'sala__predio__uo__sigla',
                'valor',
            )
            .order_by('numero')
        )

        return {'inventarios': inventarios, 'descricoes': dict(descricoes.filter().values_list('inventario_id', 'descricao'))}

    @staticmethod
    @transaction.atomic
    def efetuar_pendencia(**kwargs):
        """
        info: efetua a pendência dos <inventarios>.
        <entrada_permanente>: opcional.
        """
        inventarios = kwargs.get('inventarios')
        entrada_permanente = kwargs.get('entrada_permanente')
        if not inventarios:
            if 'carga' in kwargs:
                inventarios = Inventario.get_inventarios_carga_user(kwargs['carga'])
            elif 'rotulo' in kwargs:
                inventarios = Inventario.objects.filter(rotulos=kwargs['rotulo'], status=InventarioStatus.ATIVO())
        if isinstance(inventarios, Inventario):
            inventarios = [inventarios]
        movimento_pendencia = MovimentoPatrimTipo.PENDENCIA()
        for inventario in inventarios:
            MovimentoPatrim(data=datetime.now(), inventario=inventario, tipo=movimento_pendencia, entrada_permanente=entrada_permanente).save()

    @staticmethod
    @transaction.atomic()
    def criar_requisicao(inventarios, servidor_destino, user, estado_conservacao, sala, rotulos, descricao):
        status = Requisicao.STATUS_AGUARDANDO_APROVACAO_SERVIDOR_DESTINO
        campi = set()
        for inventario in inventarios:
            campi.add(inventario.carga_contabil.campus)

        tipo = Requisicao.TIPO_DIFERENTES_CAMPI
        if servidor_destino.setor.uo in campi:
            tipo = Requisicao.TIPO_MESMO_CAMPI

        vinculo_origem = user.get_vinculo()
        requisicao = Requisicao.objects.create(
            vinculo_origem=vinculo_origem,
            vinculo_destino=servidor_destino.get_vinculo(),
            campus_origem=vinculo_origem.relacionamento.campus,
            campus_destino=servidor_destino.campus,
            status=status,
            tipo=tipo,
            descricao=descricao,
            requisitante=user.get_vinculo(),
        )

        RequisicaoHistorico.objects.create(requisicao=requisicao, status=status, alterado_em=datetime.now(), alterado_por=user)
        for inventario in inventarios:
            if estado_conservacao:
                inventario.estado_conservacao = estado_conservacao
            if sala:
                inventario.sala = sala
            if sala:
                inventario.rotulos.set(rotulos)
            if estado_conservacao or sala or rotulos:
                inventario.save()
            RequisicaoItem.objects.get_or_create(requisicao=requisicao, inventario=inventario)

    @staticmethod
    @transaction.atomic()
    def efetuar_baixa(inventarios: Inventario | list[Inventario], baixa: Baixa) -> None:
        """
        info: efetua a transferência dos <inventarios>.
        <baixa>: instância de Baixa.
        <inventarios>: opcional; <inventarios>.
        <carga>: opcional; <inventarios> que estão na <carga>.
        <rotulo>: opcional: <inventarios> que têm tal <rotulo>.
        """
        if isinstance(inventarios, Inventario):
            inventarios = [inventarios]
        for inventario in inventarios:
            if inventario.status != InventarioStatus.ATIVO():
                raise ValueError(f'O inventario nao esta ativo: {inventario.numero}')
            inventario.sala = None
            inventario.estado_conservacao = Inventario.CONSERVACAO_IRREVERSIVEL
            rotulos = inventario.rotulos.all()
            if rotulos:
                for rotulo in rotulos:
                    inventario.rotulos.remove(rotulo)
            MovimentoPatrim(data=datetime.now(), inventario=inventario, tipo=MovimentoPatrimTipo.BAIXA(), baixa=baixa).save()
            requisicoes_pendentes = Requisicao.objects.filter(
                itens__inventario=inventario, status=Requisicao.STATUS_AGUARDANDO_APROVACAO_SERVIDOR_DESTINO
            )
            for requisicao in requisicoes_pendentes:
                requisicao.itens.update(situacao=RequisicaoItem.CANCELADO)
                requisicao.status = Requisicao.STATUS_CANCELADA
                requisicao.observacao = 'Requisição foi cancelada automaticamente, pois contém inventário baixado.'
                requisicao.save()

    @transaction.atomic()
    def corrigir_carga_contabil(self, user):
        carga_contabil = InventarioCargaContabil.objects.create(
            usuario=user, inventario=self, campus=self.responsavel_vinculo.setor.uo, tipo=InventarioCargaContabil.TIPO_MANUAL
        )
        self.carga_contabil = carga_contabil
        self.save()

    @transaction.atomic()
    def efetuar_transferencia(self, user, requisicao, requisicao_item):
        MovimentoPatrim.objects.create(
            data=datetime.now(),
            inventario=self,
            tipo=MovimentoPatrimTipo.TRANSFERENCIA(),
            vinculo=requisicao.vinculo_destino,
            requisicao_item=requisicao_item,
        )

        self.status = InventarioStatus.ATIVO()
        self.responsavel_vinculo = requisicao.vinculo_destino
        if self.cargas_contabeis.latest('id').campus != requisicao.campus_destino:
            carga_contabil = InventarioCargaContabil.objects.create(
                usuario=user, inventario=self, campus=requisicao.campus_destino, tipo=InventarioCargaContabil.TIPO_REQUISICAO, requisicao=requisicao
            )
            self.carga_contabil = carga_contabil

        self.save()

    def get_descricao(self):
        return self.descricao

    get_descricao.short_description = 'Descrição'

    def get_descricao_para_pdf(self):
        """
        Função criada para resolver bug (https://gitlab.ifrn.edu.br/cosinf/suap/issues/443) em que um inventario
        tinha descrição com os caracteres "&#\n" que gerava um erro quando passar por um parser na função
        de exportar para pdf
        """
        descricao = self.get_descricao()
        descricao = re.sub('[\t\r\n]', '', descricao)
        return descricao

    def set_descricao(self, nova_descricao):
        DescricaoInventario(inventario=self, descricao=nova_descricao, data=datetime.now()).save()

    # TODO: remover método, pois pode ser acessado via status
    def get_status(self):
        return self.status.nome

    def get_valor(self):
        total = self.valor
        if not self.valor:
            total = self.entrada_permanente.valor
        total = f'{total:,}'
        total = total.replace('.', ';')
        total = total.replace(',', '.')
        total = total.replace(';', ',')
        return total

    def get_sala(self):
        return self.sala

    def get_carga_atual(self):
        # TODO: alterar as chamadas desta função para simplesmente pegar o atributo ``responsavel``;
        #       essé método só existe por questões de compatibilidade com antigas chamadas.
        # TODO: short_description deve ir para o arquivo admin.py
        return self.responsavel_vinculo

    get_carga_atual.short_description = 'Carga Atual'

    def get_uo_atual(self):
        # TODO: DEPRECATED; use coluna ``responsavel.setor.uo``
        """Retorna a UO do servidor que tem a carga de tal inventário"""
        if self.status_id == 2 and MovimentoPatrim.objects.filter(inventario=self).exists():
            return self.get_carga_atual().setor.uo
        return None

    def get_data_carga(self):
        ultima_movimentacao = self.movimentopatrim_set.all().last()
        return ultima_movimentacao.data if ultima_movimentacao else None

    def get_absolute_url(self):
        return f'/patrimonio/inventario/{self.numero}/'

    def get_ultima_conferencia(self):
        return self.conferenciaitem_set.order_by('-dh_coleta').first()


class FotoInventario(models.ModelPlus):
    inventario = models.ForeignKeyPlus(Inventario, related_name='fotos', on_delete=models.CASCADE)
    descricao = models.CharField(max_length=500)
    data = models.DateFieldPlus()
    foto = models.ImageFieldPlus(upload_to='patrimonio/inventario_fotos/')

    def delete(self, *args, **kwargs):
        self.foto.delete()
        super().delete(*args, **kwargs)


class DescricaoInventario(models.ModelPlus):
    """
    Armazena as modificações na descrição de um inventário.
    """

    inventario = models.ForeignKeyPlus(Inventario, related_name='descricoesinventario', on_delete=models.CASCADE)
    descricao = models.TextField()
    data = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'descricaoinventario'

    def save(self, *args, **kwargs):
        pk = self.pk
        super().save(*args, **kwargs)
        if pk is None:
            self.inventario.descricao = self.descricao
            self.inventario.save()
        else:
            latest_pk = DescricaoInventario.objects.filter(inventario=self.inventario).latest('data').pk
            if latest_pk == self.pk:
                self.inventario.descricao = self.descricao
                self.inventario.save()

    def delete(self, *args, **kwargs):
        pk = self.pk
        inventario = self.inventario
        super().delete(*args, **kwargs)
        latest_pk = DescricaoInventario.objects.filter(inventario=self.inventario).latest('data')
        if latest_pk.exists() and latest_pk.pk < pk:
            inventario.descricao = latest_pk.descricao
            inventario.save()


class MovimentoPatrimTipo(models.ModelPlus):
    nome = models.CharField(max_length=20, unique=True)

    class Meta:
        db_table = 'movimentopatrimtipo'

    def __str__(self):
        return self.nome

    @staticmethod
    def PENDENCIA():
        return MovimentoPatrimTipo.objects.get(nome='pendência')

    @staticmethod
    def TRANSFERENCIA():
        return MovimentoPatrimTipo.objects.get(nome='transferência')

    @staticmethod
    def BAIXA():
        return MovimentoPatrimTipo.objects.get(nome='baixa')

    @staticmethod
    def ESTORNO():
        return MovimentoPatrimTipo.objects.get(nome='estorno')


class BaixaTipo(models.ModelPlus):
    nome = models.CharField(max_length=20, unique=True)

    class Meta:
        db_table = 'baixatipo'

    def __str__(self):
        return self.nome


class Baixa(models.ModelPlus):
    tipo = models.ForeignKeyPlus(BaixaTipo, verbose_name='Tipo', on_delete=models.CASCADE)
    data = models.DateTimeField()
    numero = models.CharField('Nº da Portaria', max_length=25)
    observacao = models.CharField('Observação', max_length=250, null=True)
    uo = models.ForeignKeyPlus(UnidadeOrganizacional, verbose_name='Campus', on_delete=models.CASCADE)
    processo = models.ForeignKeyPlus(
        'protocolo.Processo', null=True, blank=True, on_delete=models.CASCADE, help_text='Processo desta instituição relativo a esta baixa'
    )

    class Meta:
        db_table = 'baixa'
        verbose_name = 'Baixa'
        verbose_name_plural = 'Baixas'

    def delete(self):
        """
        Força a chamada do método ``delete`` de cada ``movimentopatrim_set``.
        """
        for m in self.movimentopatrim_set.all():
            m.delete()
        super().delete()

    def delete_item(self, movimento_patrim_pk):
        """
        Este método foi criado para assegurar que o movimento a ser removido
        seja o último do inventário e do tipo baixa.
        """
        try:
            self.movimentopatrim_set.get(pk=movimento_patrim_pk).delete()
        except Exception:
            pass

    def __str__(self):
        return f'Baixa {self.numero}'

    def get_absolute_url(self):
        return f'/patrimonio/baixa/{self.pk}/'

    def get_data(self):
        return calendario.date_to_string(self.data)

    def get_valor(self):
        valor = sum(self.movimentopatrim_set.values_list('inventario__valor', flat=1))
        return valor

    def get_valor_inicial(self):
        valor = sum(self.movimentopatrim_set.values_list('inventario__entrada_permanente__valor', flat=1))
        return valor

    def get_total_categoria(self):
        total_categorias = []
        categorias = (
            CategoriaMaterialPermanente.objects.filter(entradapermanente__inventario__movimentopatrim__baixa=self)
            .annotate(total_contabil=Sum('entradapermanente__inventario__valor'), total_inicial=Sum('entradapermanente__valor'))
            .order_by('nome')
        )
        for categoria in categorias:
            total_categorias.append(
                {
                    'codigo': categoria.codigo,
                    'plano_contas': categoria.plano_contas.codigo,
                    'nome': categoria.nome,
                    'total_inicial': categoria.total_inicial,
                    'total_contabil': categoria.total_contabil,
                    'total_depreciacao_acumulada': categoria.total_inicial - categoria.total_contabil,
                }
            )
        return total_categorias


class Requisicao(models.ModelPlus):
    STATUS_AGUARDANDO_APROVACAO_SERVIDOR_DESTINO = 1
    STATUS_DEFERIDA = 2
    STATUS_INDEFERIDA = 3
    STATUS_DEFERIDA_AGUARDANDO_INFORMACAO_PA_ORIGEM = 4
    STATUS_CANCELADA = 5
    STATUS_DEFERIDA_AGUARDANDO_INFORMACAO_PA_DESTINO = 6
    STATUS_CHOICES = (
        (STATUS_AGUARDANDO_APROVACAO_SERVIDOR_DESTINO, 'Aguardando aprovação do servidor de destino'),
        (STATUS_DEFERIDA, 'Deferida'),
        (STATUS_INDEFERIDA, 'Indeferida'),
        (STATUS_DEFERIDA_AGUARDANDO_INFORMACAO_PA_ORIGEM, 'Aguardando informação de PA Campus Origem'),
        (STATUS_CANCELADA, 'Cancelada'),
        (STATUS_DEFERIDA_AGUARDANDO_INFORMACAO_PA_DESTINO, 'Aguardando informação de PA Campus Destino'),
    )

    TIPO_MESMO_CAMPI = 1
    TIPO_DIFERENTES_CAMPI = 2
    TIPO_CHOICES = ((TIPO_MESMO_CAMPI, 'Mesmo campus'), (TIPO_DIFERENTES_CAMPI, 'Entre diferentes campi'))
    status = models.PositiveIntegerField('Situação', choices=STATUS_CHOICES, default=STATUS_AGUARDANDO_APROVACAO_SERVIDOR_DESTINO)
    tipo = models.PositiveIntegerField(choices=TIPO_CHOICES, default=TIPO_MESMO_CAMPI)
    vinculo_origem = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Pessoa de Origem', related_name='requisicao_vinculoorigem', null=True)
    campus_origem = models.ForeignKeyPlus(
        UnidadeOrganizacional, verbose_name='Campus de Origem', related_name='requisicao_campusorigem', null=True, on_delete=models.CASCADE
    )  # Em branco caso seja a primeira carga
    vinculo_destino = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Pessoa de Destino', related_name='requisicao_vinculodestino')
    campus_destino = models.ForeignKeyPlus(
        UnidadeOrganizacional, verbose_name='Campus de Destino', related_name='requisicao_campusdestino', null=True, on_delete=models.CASCADE
    )
    observacao = models.TextField('Observação', help_text='Observação quando a requisição foi negada', blank=True)
    numero_pa_origem = models.TextField('Número da PA Campus Origem', blank=True)
    numero_pa_destino = models.TextField('Número da PA Campus Destino', blank=True)
    inv_inconsistentes = models.BooleanField(default=False, null=True)
    vinculo_coordenador = models.ForeignKeyPlus('comum.Vinculo', related_name='requisicao_coordenador', null=True)
    requisitante = models.ForeignKeyPlus('comum.Vinculo', null=True)
    descricao = models.TextField(max_length=500, null=True, verbose_name='Descrição')

    notificar_destino = True
    """
    Se o servidor de destino recebe e-mail quando a requisição é criada.

    Desligado pela migração de inventários, que cria uma requisição por servidor de uma só vez:
    o comportamento normal dispararia uma avalanche de e-mails sobre uma carga que, do ponto de
    vista do servidor, já existia. Atributo de instância, não coluna — a supressão vale para
    aquela gravação, nunca para o registro.
    """

    class Meta:
        verbose_name = 'Requisição de Transferência'
        verbose_name_plural = 'Requisições de Transferência'

        permissions = (
            ('pode_requisitar_transferencia_do_campus', 'Pode requisitar transferência do próprio campus'),
            ('pode_visualizar_requisicao_do_campus', 'Pode visualizar requisições do próprio campus'),
        )

    def get_absolute_url(self):
        return f'/patrimonio/requisicao/{self.pk}/'

    @staticmethod
    def criar_por_agrupamento(inventarios, servidor_destino, user, status, descricao, inconsistencia=False):
        responsavel_inventario = defaultdict(lambda: defaultdict(list))
        user_vinculo = user.get_vinculo()
        for inventario in inventarios:
            campus = inventario.carga_contabil.campus
            responsavel_inventario[inventario.responsavel_vinculo][campus].append(inventario)

        for vinculo, campus_dict in responsavel_inventario.items():
            for campus, inventarios_list in campus_dict.items():
                tipo_requisicao = Requisicao.TIPO_MESMO_CAMPI if campus == servidor_destino.campus else Requisicao.TIPO_DIFERENTES_CAMPI

                requisicao = Requisicao.objects.create(
                    vinculo_origem=vinculo,
                    vinculo_destino=servidor_destino.get_vinculo(),
                    campus_origem=campus,
                    campus_destino=servidor_destino.campus,
                    status=status,
                    tipo=tipo_requisicao,
                    vinculo_coordenador=user_vinculo,
                    descricao=descricao,
                    requisitante=user_vinculo,
                )
                RequisicaoHistorico.objects.create(
                    requisicao=requisicao,
                    status=status,
                    alterado_em=datetime.now(),
                    alterado_por=user,
                )
                itens_para_criar = [RequisicaoItem(requisicao=requisicao, inventario=inventario) for inventario in inventarios_list]
                RequisicaoItem.objects.bulk_create(itens_para_criar, ignore_conflicts=True)

                if inconsistencia and vinculo.relacionamento == servidor_destino:
                    RequisicaoItem.objects.filter(requisicao=requisicao, inventario__in=inventarios_list).update(situacao=RequisicaoItem.APROVADO)
                    requisicao.deferir_requisicao(user)

    @transaction.atomic()
    def save(self, *args, **kwargs):
        enviar_email = bool(not self.pk) and self.notificar_destino

        super().save(*args, **kwargs)

        if enviar_email:
            titulo = '[SUAP] Patrimônio: Envio de Requisição de Transferência'
            texto_servidor_destino = (
                '<h1>Patrimônio</h1>'
                '<h2>Envio de Requisição de Transferência</h2>'
                '<p>Uma Requisição de Transferência de Patrimônio foi enviada para sua avaliação.</p>'
                '<p class="more-info">Para mais informações, acesse: <a href="{0}{1}">{0}{1}</a></p>'.format(
                    settings.SITE_URL, self.get_absolute_url()
                )
            )
            send_notification(titulo, texto_servidor_destino, settings.DEFAULT_FROM_EMAIL, [self.vinculo_destino])

    @classmethod
    def get_qs_aguardando(cls, qs=None):
        if qs is None:
            qs = cls.objects.all()

        return qs.filter(status=cls.STATUS_AGUARDANDO_APROVACAO_SERVIDOR_DESTINO)

    @classmethod
    def restringir_queryset(cls, qs=None, user=None):
        """
        Restringe o queryset, deixando apenas as requisições visíveis ao `user`.
        """
        if qs is None:
            qs = cls.objects.all()
        vinculo = user.get_vinculo()
        retorno = qs.filter(vinculo_origem=vinculo) | qs.filter(vinculo_destino=vinculo)
        if user.has_perm('patrimonio.pode_visualizar_requisicao_do_campus'):
            campus_usuario = get_uo(user)
            retorno |= qs.filter(campus_origem=campus_usuario)
            retorno |= qs.filter(campus_destino=campus_usuario)
            retorno |= qs.filter(requisicaohistorico__alterado_por=user)

        return retorno.distinct()

    @classmethod
    def get_enviadas(cls, vinculo, qs=None):
        """Retorna queryset com as requisições cadastradas pelo `user`"""
        if qs is None:
            qs = cls.objects.all()

        return qs.filter(vinculo_origem=vinculo)

    @classmethod
    def get_recebidas(cls, vinculo, qs=None):
        """Retorna queryset com as requisições destinadas ao `user`"""
        if qs is None:
            qs = cls.objects.all()

        return qs.filter(vinculo_destino=vinculo)

    @classmethod
    def get_aguardando_aprovacao_servidor(cls, vinculo, qs=None):
        """Retorna queryset com as requisições que o `vinculo` deve aceitar.
        Esse queryset é usado no admin e também para restringir o acesso à view de aprovação do servidor de destino."""
        if qs is None:
            qs = cls.objects.all()

        return cls.get_qs_aguardando(qs.filter(vinculo_destino=vinculo))

    @classmethod
    def get_requisicoes_campus_aguardando_destino(cls, uo, qs=None):
        if qs is None:
            qs = cls.objects.all()
        return cls.get_qs_aguardando(qs.filter(campus_origem=uo))

    @classmethod
    def get_qs_aguardando_informacao_pa_origem(cls, uo, qs=None):
        if qs is None:
            qs = cls.objects.all()
        return qs.filter(status=cls.STATUS_DEFERIDA_AGUARDANDO_INFORMACAO_PA_ORIGEM, campus_origem=uo)

    @classmethod
    def get_qs_aguardando_informacao_pa_destino(cls, uo, qs=None):
        if qs is None:
            qs = cls.objects.all()
        return qs.filter(status=cls.STATUS_DEFERIDA_AGUARDANDO_INFORMACAO_PA_DESTINO, campus_destino=uo)

    def get_status(self):
        if self.status == Requisicao.STATUS_DEFERIDA:
            return f'<span class="status status-success"> {self.get_status_display()} </span>'
        elif self.status == Requisicao.STATUS_INDEFERIDA:
            return f'<span class="status status-rejeitado">{self.get_status_display()} </span>'
        elif (
            self.status == Requisicao.STATUS_AGUARDANDO_APROVACAO_SERVIDOR_DESTINO
            or self.status == Requisicao.STATUS_DEFERIDA_AGUARDANDO_INFORMACAO_PA_ORIGEM
            or self.status == Requisicao.STATUS_DEFERIDA_AGUARDANDO_INFORMACAO_PA_DESTINO
        ):
            return f'<span class="status status-alert">{self.get_status_display()} </span>'
        elif self.status == Requisicao.STATUS_CANCELADA:
            return f'<span class="status status-rejeitado">{self.get_status_display()} </span>'

    def ver_periodo_deferimento(self):
        periodo_deferimento = True
        dia_inicio_bloqueio = Configuracao.get_valor_por_chave('patrimonio', 'dia_inicio_bloqueio')
        if date.today().day >= int(dia_inicio_bloqueio) and self.tipo == Requisicao.TIPO_DIFERENTES_CAMPI:
            periodo_deferimento = False
        return periodo_deferimento

    def pode_avaliar(self):
        user = tl.get_user()
        return self.status == Requisicao.STATUS_AGUARDANDO_APROVACAO_SERVIDOR_DESTINO and self.vinculo_destino == user.get_vinculo()

    def pode_deferir(self):
        user = tl.get_user()
        inventarios = RequisicaoItem.objects.filter(requisicao=self)
        itens_aprovados = inventarios.filter(situacao=RequisicaoItem.APROVADO).exists()
        return (
            self.status == Requisicao.STATUS_AGUARDANDO_APROVACAO_SERVIDOR_DESTINO
            and self.vinculo_destino == user.get_vinculo()
            and itens_aprovados
            and self.ver_periodo_deferimento()
        )

    def pode_avaliar_inventario(self):
        user = tl.get_user()
        return self.status == Requisicao.STATUS_AGUARDANDO_APROVACAO_SERVIDOR_DESTINO and self.vinculo_destino == user.get_vinculo()

    def pode_informar_pa_origem(self):
        user = tl.get_user()
        if in_group(user, ['Contador de Patrimônio Sistêmico']):
            return True
        return (
            in_group(user, ['Contador de Patrimônio'])
            and self.campus_origem == get_uo(user)
            and self.status == Requisicao.STATUS_DEFERIDA_AGUARDANDO_INFORMACAO_PA_ORIGEM
        )

    def pode_informar_pa_destino(self):
        user = tl.get_user()
        if in_group(user, ['Contador de Patrimônio Sistêmico']):
            return True
        return (
            in_group(user, ['Contador de Patrimônio'])
            and self.campus_destino == get_uo(user)
            and self.status == Requisicao.STATUS_DEFERIDA_AGUARDANDO_INFORMACAO_PA_DESTINO
        )

    def pode_editar_pa_origem(self):
        user = tl.get_user()
        if in_group(user, ['Contador de Patrimônio Sistêmico']) and (
            self.status == Requisicao.STATUS_DEFERIDA_AGUARDANDO_INFORMACAO_PA_DESTINO or self.status == Requisicao.STATUS_DEFERIDA
        ):
            return True
        return (
            in_group(user, ['Contador de Patrimônio'])
            and self.campus_origem == get_uo(user)
            and (self.status == Requisicao.STATUS_DEFERIDA_AGUARDANDO_INFORMACAO_PA_DESTINO or self.status == Requisicao.STATUS_DEFERIDA)
        )

    def pode_editar_pa_destino(self):
        user = tl.get_user()
        if in_group(user, ['Contador de Patrimônio Sistêmico']):
            return True
        return in_group(user, ['Contador de Patrimônio']) and self.campus_destino == get_uo(user)

    def pode_gerar_termo(self):
        user = tl.get_user()
        return (
            in_group(user, ['Coordenador de Patrimônio Sistêmico', 'Coordenador de Patrimônio'])
            or self.vinculo_origem == user.get_vinculo()
            or self.vinculo_destino == user.get_vinculo()
        )

    def pode_cancelar(self):
        user = tl.get_user()
        if self.vinculo_origem == user.get_vinculo():
            return self.status == Requisicao.STATUS_AGUARDANDO_APROVACAO_SERVIDOR_DESTINO
        else:
            return (
                in_group(user, ['Coordenador de Patrimônio Sistêmico', 'Coordenador de Patrimônio'])
                and self.campus_origem == get_uo(user)
                and self.status == Requisicao.STATUS_AGUARDANDO_APROVACAO_SERVIDOR_DESTINO
            )

    @transaction.atomic()
    def cancelar_requisicao(self, user):
        inventarios = RequisicaoItem.objects.filter(requisicao=self)
        for i in inventarios:
            i.situacao = RequisicaoItem.CANCELADO
            i.save()

        self.status = Requisicao.STATUS_CANCELADA
        self.save()
        RequisicaoHistorico.objects.create(requisicao=self, status=self.status, alterado_em=datetime.now(), alterado_por=user)
        if self.vinculo_destino:
            titulo = f'[SUAP] Patrimônio: Cancelamento da Requisição de Transferência #{self.id}'
            if self.vinculo_origem == user.get_vinculo():
                texto = (
                    '<h1>Patrimônio</h1>'
                    '<h2>Cancelamento da Requisição de Transferência</h2>'
                    f'<p>A Requisição de Transferência de Patrimônio #{self.id} foi <strong>cancelada</strong> pelo servidor de origem.</p>'
                    '<p class="more-info">Para mais informações, acesse: <a href="{0}{1}">{0}{1}</a></p>'.format(
                        settings.SITE_URL, self.get_absolute_url()
                    )
                )
                send_notification(
                    titulo,
                    texto,
                    settings.DEFAULT_FROM_EMAIL,
                    [self.vinculo_destino],
                    categoria='Patrimônio: Cancelamento da Requisição de Transferência',
                )
            else:
                texto = (
                    f'<p>A Requisição de Transferência de Patrimônio #{self.id} foi <strong>cancelada</strong> pelo Coordenador do Campus Origem.</p>'
                    '<p class="more-info">Para mais informações, acesse: <a href="{0}{1}">{0}{1}</a></p>'.format(
                        settings.SITE_URL, self.get_absolute_url()
                    )
                )
                send_notification(
                    titulo,
                    texto,
                    settings.DEFAULT_FROM_EMAIL,
                    [self.vinculo_destino, self.vinculo_origem],
                    categoria='Patrimônio: Cancelamento da Requisição de Transferência',
                )

    @transaction.atomic()
    def indeferir_requisicao(self, user):
        # com a requisição indeferida nenhum item é transferido, inclusive os que já tinham sido aprovados
        self.itens.exclude(situacao=RequisicaoItem.REJEITADO).update(situacao=RequisicaoItem.REJEITADO, data_avaliacao=date.today(), avaliador=user)
        self.status = Requisicao.STATUS_INDEFERIDA
        self.save()
        RequisicaoHistorico.objects.create(requisicao=self, status=self.status, alterado_em=datetime.now(), alterado_por=user)
        if self.vinculo_origem:
            titulo = f'[SUAP] Patrimônio: Indeferimento da Requisição de Transferência #{self.id}'
            texto = (
                '<h1>Patrimônio</h1>'
                '<h2>Indeferimento da Requisição de Transferência</h2>'
                f'<p>A Requisição de Transferência de Patrimônio #{self.id} foi <strong>indeferida</strong> pelo Servidor de destino.</p>'
                '<p class="more-info">Para mais informações, acesse: <a href="{0}{1}">{0}{1}</a></p>'.format(
                    settings.SITE_URL, self.get_absolute_url()
                )
            )
            send_notification(
                titulo,
                texto,
                settings.DEFAULT_FROM_EMAIL,
                [self.vinculo_origem],
                categoria='Patrimônio: Indeferimento da Requisição de Transferência',
            )

    def deferir_requisicao(self, user, sala=None, task=None):
        itens = self.itens.all()
        if task:
            task.start_progress(100)
            task.update_progress(5)

        with transaction.atomic():
            for item in itens:
                if item.situacao == RequisicaoItem.APROVADO:
                    item.inventario.efetuar_transferencia(user, self, item)
                    if sala:
                        item.inventario.sala = sala
                        item.inventario.save()
                item.valor = item.inventario.valor
                item.save()
            if self.tipo == Requisicao.TIPO_DIFERENTES_CAMPI:
                self.status = Requisicao.STATUS_DEFERIDA_AGUARDANDO_INFORMACAO_PA_ORIGEM
            else:
                self.status = Requisicao.STATUS_DEFERIDA

            self.save()
            RequisicaoHistorico.objects.create(requisicao=self, status=self.status, alterado_em=datetime.now(), alterado_por=user)

        if task:
            task.update_progress(80)

        titulo = f'[SUAP] Patrimônio: Deferimento da Requisição de Transferência #{self.id}'
        texto = (
            '<h1>Patrimônio</h1>'
            '<h2>Deferimento da Requisição de Transferência</h2>'
            f'<p>A Requisição de Transferência de Patrimônio #{self.id} foi deferida pelo servidor {self.vinculo_destino}.</p>'
        )
        if self.tipo == Requisicao.TIPO_DIFERENTES_CAMPI:
            texto += '<p>Aguardando a informação da PA no SUAP pelo contador.</p>'
        texto += '<p class="more-info">Para mais informações, acesse: <a href="{0}{1}">{0}{1}</a></p>'.format(
            settings.SITE_URL, self.get_absolute_url()
        )

        vinculos = []
        if self.vinculo_destino.setor:
            coordenadores = Vinculo.objects.filter(user__groups__name='Coordenador de Patrimônio', setor__uo=self.campus_destino)
            vinculos.extend(coordenadores)

        if self.vinculo_origem and self.vinculo_origem.setor:
            vinculos.append(self.vinculo_origem)
            coordenadores = Vinculo.objects.filter(user__groups__name='Coordenador de Patrimônio', setor__uo=self.campus_origem)
            vinculos.extend(list(coordenadores))

        if self.tipo == Requisicao.TIPO_DIFERENTES_CAMPI:
            servidores_destino = Servidor.objects.ativos().filter(cargo_emprego__nome__unaccent__icontains='contador', setor__uo=self.campus_destino)
            for servidor in servidores_destino:
                vinculos.append(servidor.get_vinculo())
            if self.vinculo_origem:
                servidores_origem = Servidor.objects.ativos().filter(
                    cargo_emprego__nome__unaccent__icontains='contador', setor__uo=self.campus_origem
                )
                for servidor in servidores_origem:
                    vinculos.append(servidor.get_vinculo())

        send_notification(
            titulo, texto, settings.DEFAULT_FROM_EMAIL, vinculos, categoria='Patrimônio: Deferimento da Requisição de Transferência', task=task
        )

    @transaction.atomic()
    def informarpa_origem_requisicao(self, user, numero_pa_origem):
        self.status = Requisicao.STATUS_DEFERIDA_AGUARDANDO_INFORMACAO_PA_DESTINO
        self.numero_pa_origem = numero_pa_origem
        self.save()
        RequisicaoHistorico.objects.create(requisicao=self, status=self.status, alterado_em=datetime.now(), alterado_por=user)

        titulo = f'[SUAP] Patrimônio: Deferimento da Requisição de Transferência #{self.id}'
        texto = (
            '<h1>Patrimônio</h1>'
            '<h2>Deferimento da Requisição de Transferência</h2>'
            f'<p>A Requisição de Transferência de Patrimônio #{self.id} foi deferida pelo servidor {self.vinculo_destino}.</p>'
            '<p>Aguardando a informação da PA no SUAP pelo contador.</p>'
            '<p class="more-info">Para mais informações, acesse: <a href="{0}{1}">{0}{1}</a></p>'.format(settings.SITE_URL, self.get_absolute_url())
        )
        vinculos = []
        coordenadores_destino = Vinculo.objects.filter(user__groups__name='Coordenador de Patrimônio', setor__uo=self.campus_destino)
        vinculos = list(coordenadores_destino)

        vinculos.append(self.vinculo_origem)

        coordenadores_origem = Vinculo.objects.filter(user__groups__name='Coordenador de Patrimônio', setor__uo=self.campus_origem)
        vinculos.extend(list(coordenadores_origem))

        if self.tipo == Requisicao.TIPO_DIFERENTES_CAMPI:
            servidores_destino = Servidor.objects.ativos().filter(cargo_emprego__nome__unaccent__icontains='contador', setor__uo=self.campus_destino)
            for servidor in servidores_destino:
                vinculos.append(servidor.get_vinculo())
            if self.vinculo_origem:
                servidores_origem = Servidor.objects.ativos().filter(
                    cargo_emprego__nome__unaccent__icontains='contador', setor__uo=self.campus_origem
                )
                for servidor in servidores_origem:
                    vinculos.append(servidor.get_vinculo())

        send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, vinculos, categoria='Patrimônio: Deferimento da Requisição de Transferência')

    @transaction.atomic()
    def informarpa_destino_requisicao(self, user, numero_pa_destino):
        self.status = Requisicao.STATUS_DEFERIDA
        self.numero_pa_destino = numero_pa_destino
        self.save()
        RequisicaoHistorico.objects.create(requisicao=self, status=self.status, alterado_em=datetime.now(), alterado_por=user)

        titulo = f'[SUAP] Patrimônio: Deferimento da Requisição de Transferência #{self.id}'
        texto = (
            '<h1>Patrimônio</h1>'
            '<h2>Deferimento da Requisição de Transferência</h2>'
            '<p>A Requisição de Transferência de Patrimônio aguarda a informação da PA pelo contador destino.</p>'
            '<p class="more-info">Para mais informações, acesse: <a href="{0}{1}">{0}{1}</a></p>'.format(settings.SITE_URL, self.get_absolute_url())
        )
        coordenadores_destino = Vinculo.objects.filter(user__groups__name='Coordenador de Patrimônio', setor__uo=self.campus_destino)
        vinculos = list(coordenadores_destino)

        if self.vinculo_origem and self.vinculo_origem.setor:
            vinculos.append(self.vinculo_origem)
            coordenadores_origem = Vinculo.objects.filter(user__groups__name='Coordenador de Patrimônio', setor__uo=self.vinculo_origem.setor.uo)
            vinculos.extend(list(coordenadores_origem))

        if self.tipo == Requisicao.TIPO_DIFERENTES_CAMPI:
            servidores_destino = Servidor.objects.ativos().filter(cargo_emprego__nome__unaccent__icontains='contador', setor__uo=self.campus_destino)
            for servidor in servidores_destino:
                vinculos.append(servidor.get_vinculo())

            if self.vinculo_origem:
                servidores_origem = Servidor.objects.ativos().filter(
                    cargo_emprego__nome__unaccent__icontains='contador', setor__uo=self.campus_origem
                )
                for servidor in servidores_origem:
                    vinculos.append(servidor.get_vinculo())

        send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, vinculos, categoria='Patrimônio: Deferimento da Requisição de Transferência')

    def get_ultimo_historico(self):
        requisicao_historico = RequisicaoHistorico.objects.filter(requisicao__id=self.id)
        if requisicao_historico.exists():
            requisicao_historico = requisicao_historico.latest('alterado_em')
        else:
            requisicao_historico = None
        return requisicao_historico


class InventarioCargaContabil(models.ModelPlus):
    """Classe que armazenará o histórico de cargas contábeis de um inventário"""

    TIPO_REQUISICAO = 1
    TIPO_MANUAL = 2
    TIPO_CHOICES = ((TIPO_REQUISICAO, 'Requisição'), (TIPO_MANUAL, 'Manual'))
    data = models.DateField(auto_now_add=True)
    usuario = CurrentUserField(null=True)
    inventario = models.ForeignKeyPlus(Inventario, related_name='cargas_contabeis', on_delete=models.CASCADE)
    campus = models.ForeignKeyPlus(UnidadeOrganizacional, on_delete=models.CASCADE)
    tipo = models.PositiveIntegerField(choices=TIPO_CHOICES)
    requisicao = models.ForeignKeyPlus(Requisicao, null=True, on_delete=models.CASCADE)  # preenchido caso seja tipo Requisicao


class RequisicaoItem(models.ModelPlus):
    APROVADO = 1
    REJEITADO = 2
    PENDENTE = 3
    CANCELADO = 4
    SITUACAO_CHOICES = ((APROVADO, 'Aprovado'), (REJEITADO, 'Rejeitado'), (PENDENTE, 'Pendente'), (CANCELADO, 'Cancelado'))
    requisicao = models.ForeignKeyPlus(Requisicao, related_name='itens', on_delete=models.CASCADE)
    inventario = models.ForeignKeyPlus(Inventario, on_delete=models.CASCADE)
    data_avaliacao = models.DateField(auto_now_add=True, null=True)
    avaliador = CurrentUserField(null=True)
    situacao = models.PositiveIntegerField(choices=SITUACAO_CHOICES, null=True, default=PENDENTE)
    valor = models.DecimalFieldPlus(null=True, blank=True, max_digits=15, decimal_places=6)

    class Meta:
        verbose_name = 'Item de Requisição'
        verbose_name_plural = 'Itens de Requisição'

        unique_together = ('requisicao', 'inventario')


class MovimentoPatrim(models.ModelPlus):
    usuario = CurrentUserField()
    inventario = models.ForeignKeyPlus(Inventario, on_delete=models.CASCADE)
    tipo = models.ForeignKeyPlus(MovimentoPatrimTipo, on_delete=models.CASCADE)
    vinculo = models.ForeignKeyPlus('comum.Vinculo', null=True)
    entrada_permanente = models.ForeignKeyPlus(EntradaPermanente, db_column='entradapermanente_id', null=True, on_delete=models.CASCADE)
    baixa = models.ForeignKeyPlus(Baixa, null=True, on_delete=models.CASCADE)
    data = models.DateTimeField()
    requisicao_item = models.ForeignKeyPlus(RequisicaoItem, null=True, on_delete=models.CASCADE)

    class Meta:
        db_table = 'movimentopatrim'
        ordering = ['-data']

    def save(self, *args, **kwargs):
        """
        Atualiza ``resposavel`` e ``status`` do ``inventario`` de acordo com
        ``tipo``.
        """

        # Atualiza ``resposavel`` e ``status`` se este for o último movimento do
        # ``inventario``.
        movimentos_do_inventario = self.inventario.movimentopatrim_set.order_by('-id')
        ultimo_movimento_do_inventario = movimentos_do_inventario and movimentos_do_inventario[0].pk == self.pk
        if not self.pk or ultimo_movimento_do_inventario:
            if self.tipo == MovimentoPatrimTipo.PENDENCIA():
                self.inventario.status = InventarioStatus.PENDENTE()
                self.inventario.responsavel_vinculo = None
            elif self.tipo == MovimentoPatrimTipo.TRANSFERENCIA():
                self.inventario.status = InventarioStatus.ATIVO()
                self.inventario.responsavel_vinculo = self.vinculo
            elif self.tipo == MovimentoPatrimTipo.BAIXA():
                self.inventario.status = InventarioStatus.BAIXADO()
                self.inventario.responsavel_vinculo = None
            self.inventario.save()

        super().save(*args, **kwargs)

    def delete(self):
        """
        Atualiza ``resposavel`` e ``status`` do ``inventario`` de acordo com
        ``tipo``.
        """
        super().delete()
        movimentos_do_inventario = self.inventario.movimentopatrim_set.order_by('-id')
        if movimentos_do_inventario:
            movimentos_do_inventario[0].save()


class Cautela(models.ModelPlus):
    responsavel = models.CharField('Responsável', max_length=100)
    data_inicio = models.DateField(db_column='datainicio')  # Data de saída do item
    data_fim = models.DateField(db_column='datafim')  # Data de previsão de volta do item
    descricao = models.CharField('Descrição', max_length=500, blank=True)

    class Meta:
        db_table = 'cautela'
        verbose_name = 'Cautela'
        verbose_name_plural = 'Cautelas'

    def __str__(self):
        return f'{self.descricao}'

    def get_absolute_url(self):
        return f'/patrimonio/cautela/{self.pk}/'

    def em_andamento(self, data_inicio, data_fim):
        return self.data_inicio < data_fim and self.data_fim > data_inicio

    def get_data_inicio(self):
        return calendario.date_to_string(self.data_inicio)

    def get_data_fim(self):
        return calendario.date_to_string(self.data_fim)

    def get_itens(self):
        """
        Retorna lista de inventários relacionados por meio do model CautelaInventario
        """
        return self.cautelainventario_set.order_by('id')


class CautelaInventario(models.ModelPlus):
    cautela = models.ForeignKeyPlus(Cautela, on_delete=models.CASCADE)
    inventario = models.ForeignKeyPlus(Inventario, on_delete=models.CASCADE)

    class Meta:
        db_table = 'cautelainventario'

    def get_absolute_url(self):
        return get_admin_object_url(self)

    def get_delete_url(self):
        return f'/patrimonio/cautelainventario/{self.id}/remover/'


class CautelaRenovacao(models.ModelPlus):
    cautela = models.ForeignKeyPlus(Cautela, on_delete=models.CASCADE)
    data = models.DateTimeField()
    data_fim = models.DateField(db_column='datafim')

    class Meta:
        db_table = 'cautelarenovacao'


class RelatorioPatrim:
    CATEGORIAS_EXCLUIDAS = ['90', '94']  # Bens imóveis, Bens intangíveis

    @staticmethod
    def valor_entrada(datas, categoria_id=None):
        """
        1 data: período é até a data.
        2 datas: período é entre as datas.
        """
        queryset = EntradaPermanente.objects
        if RelatorioPatrim.CATEGORIAS_EXCLUIDAS:
            queryset = queryset.exclude(categoria__codigo__in=RelatorioPatrim.CATEGORIAS_EXCLUIDAS)

        if len(datas) == 1:
            queryset = queryset.filter(entrada__data__lt=calendario.somar_dias(datas[0], 1))
        elif len(datas) == 2:
            queryset = queryset.filter(entrada__data__gte=datas[0], entrada__data__lt=calendario.somar_dias(datas[1], 1))
        if categoria_id:
            queryset = queryset.filter(categoria__id=categoria_id)

        # O total é por unidade: cada item de entrada gera `qtd` tombamentos de `valor` cada.
        result = list(queryset.aggregate(total_entrada=Sum(F('valor') * F('qtd'), output_field=DecimalField())).values()).pop()
        return result or Decimal('0.0')

    @staticmethod
    def valor_saida(datas, categoria_id=None):
        predicates = [models.Q(movimentopatrim__tipo__id=MovimentoPatrimTipo.BAIXA().pk)]
        if len(datas) == 1:
            predicates.append(models.Q(movimentopatrim__data__lt=calendario.somar_dias(datas[0], 1)))
        elif len(datas) == 2:
            predicates.append(models.Q(movimentopatrim__data__gte=datas[0]))
            predicates.append(models.Q(movimentopatrim__data__lt=calendario.somar_dias(datas[1], 1)))

        if categoria_id:
            predicates.append(models.Q(movimentopatrim__entrada_permanente__categoria__id=categoria_id))
        queryset = Inventario.objects
        if RelatorioPatrim.CATEGORIAS_EXCLUIDAS:
            queryset = queryset.exclude(movimentopatrim__entrada_permanente__categoria__codigo__in=RelatorioPatrim.CATEGORIAS_EXCLUIDAS)
        result = list(queryset.filter(reduce(operator.and_, predicates)).aggregate(total_saida=Sum('entrada_permanente__valor')).values()).pop()
        return result or Decimal('0.0')

    @staticmethod
    def valor_acumulado(data_limite, categoria_id=None):
        total_entrada = RelatorioPatrim.valor_entrada([data_limite], categoria_id)
        total_saida = RelatorioPatrim.valor_saida([data_limite], categoria_id)
        total_geral = total_entrada - total_saida
        return total_geral


class InventarioReavaliacao(models.ModelPlus):
    """
    Armazena as modificações nos valores do inventário reavaliado
    Atualmente trata a depreciação.
    """

    AUTOMATICO = 1
    MANUAL_REAVALIACAO = 2
    MANUAL_AJUSTE_VALOR_RECUPERAVEL = 3

    TIPO_CHOICES = ((AUTOMATICO, 'Automático'), (MANUAL_REAVALIACAO, 'Deferida'), (MANUAL_AJUSTE_VALOR_RECUPERAVEL, 'Reavaliação Manual'))

    data_operacao = models.DateTimeField(auto_now_add=True)
    operador = CurrentUserField()
    tipo = models.PositiveIntegerField(choices=TIPO_CHOICES, default=AUTOMATICO)
    percentual_residual = models.FloatField()  # guarda o valor para histórico; para deve ser > 0 e < 1
    vida_util_em_anos = models.FloatField()  # guarda o valor para histórico;
    inventario = models.ForeignKeyPlus(Inventario, on_delete=models.CASCADE)
    data = models.DateFieldPlus()
    valor_anterior = models.DecimalFieldPlus(max_digits=15, decimal_places=6)
    valor = models.DecimalFieldPlus(max_digits=15, decimal_places=6)
    motivo = models.TextField('Motivo')

    @classmethod
    def reavaliar(cls, inventario):
        """
        - reavalia os inventários até a data de inicio da depreciação
        """
        import calendar

        DATA_LIMITE_REAVALIACAO = date(2009, 12, 31)

        def fim_proximo_mes(data):
            data_mes, data_ano = data.month, data.year
            if data_mes == 12:
                mes = 1
                ano = data_ano + 1
            else:
                mes = data_mes + 1
                ano = data_ano
            return date(ano, mes, calendar.monthrange(ano, mes)[1])

        vida_util_anos_do_inventario = inventario.entrada_permanente.categoria.vida_util_em_anos
        percentual_residual_do_inventario = inventario.entrada_permanente.categoria.percentual_residual

        valor_entrada = inventario.entrada_permanente.valor

        valor_residual = Decimal('%.2f' % (float(valor_entrada) * percentual_residual_do_inventario))
        valor_depreciavel = valor_entrada - valor_residual
        valor_depreciavel_mensal = Decimal(valor_depreciavel) / Decimal(vida_util_anos_do_inventario * 12)

        try:
            data_ultima_reavaliacao = inventario.inventarioreavaliacao_set.latest('data').data
        except Exception:
            data_ultima_reavaliacao = inventario.entrada_permanente.entrada.data.date()

        data_reavaliacao = fim_proximo_mes(data_ultima_reavaliacao)

        try:
            valor_entrada = inventario.inventarioreavaliacao_set.latest('data').valor
        except Exception:
            valor_entrada = inventario.valor

        valor_novo = valor_entrada

        while (data_reavaliacao <= DATA_LIMITE_REAVALIACAO) and (valor_novo >= valor_residual):
            valor_novo = Decimal(valor_novo) - valor_depreciavel_mensal
            valor_inv = Decimal(f'{valor_novo:.2f}')
            if valor_inv < valor_residual:
                continue
            try:
                valor_anterior = inventario.inventarioreavaliacao_set.latest('data').valor
            except Exception:
                valor_anterior = inventario.valor

            InventarioReavaliacao.objects.create(
                percentual_residual=percentual_residual_do_inventario,
                vida_util_em_anos=vida_util_anos_do_inventario,
                inventario_id=inventario.id,
                data=data_reavaliacao,
                valor=valor_novo,
                valor_anterior=valor_anterior,
            )
            data_reavaliacao = fim_proximo_mes(data_reavaliacao)

            if Decimal(f'{valor_novo:.2f}') <= 0.01:
                break
        if InventarioReavaliacao.objects.filter(inventario=inventario).exists():
            valor_novo = inventario.inventarioreavaliacao_set.latest('data').valor
            inventario.valor = valor_novo
            inventario.save()

    def get_tipo(self):
        if self.tipo == self.AUTOMATICO:
            tipo = 'Automático'
        else:
            tipo = 'Manual'
        return tipo


class InventarioValor(models.ModelPlus):
    """
    Armazena as modificações nos valores do inventário.
    Atualmente trata a depreciação.
    """

    data_operacao = models.DateTimeField(auto_now_add=True)
    operador = CurrentUserField()
    tipo = models.PositiveIntegerField(choices=((1, 'Depreciação'),), default=1)
    percentual_residual = models.FloatField()  # guarda o valor para histórico; para deve ser > 0 e < 1
    vida_util_em_anos = models.FloatField()  # guarda o valor para histórico;
    inventario = models.ForeignKeyPlus(Inventario, on_delete=models.CASCADE)
    data = models.DateFieldPlus()
    valor = models.DecimalFieldPlus(max_digits=15, decimal_places=6)
    uo = models.ForeignKeyPlus(UnidadeOrganizacional, null=True, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('tipo', 'inventario', 'data')

    class History:
        disabled = True

    @classmethod
    @transaction.atomic
    def depreciar(cls, inventario):
        """
        - Não há depreciação em fração menor que 1 mês
        """
        import calendar

        # Todo inventário deve começar a depreciar a partir de 01/01/2010,
        # não importando a sua data de entrada ou primeira movimentação
        DATA_INICIO_DEPRECIACAO = date(2010, 1, 31)

        def fim_proximo_mes(data):
            data_mes, data_ano = data.month, data.year
            if data_mes == 12:
                mes = 1
                ano = data_ano + 1
            else:
                mes = data_mes + 1
                ano = data_ano
            return date(ano, mes, calendar.monthrange(ano, mes)[1])

        conf_data_depreciacao = Configuracao.get_valor_por_chave('patrimonio', 'data_inicio_depreciacao')
        conf_data_depreciacao = datetime.strptime(conf_data_depreciacao, '%Y-%m-%d')
        if inventario.entrada_permanente.entrada.data.date() > datetime.date(conf_data_depreciacao):
            vida_util_anos_do_inventario = inventario.entrada_permanente.categoria.vida_util_em_anos
            percentual_residual_do_inventario = inventario.entrada_permanente.categoria.percentual_residual

            try:
                valor_entrada = inventario.inventarioreavaliacao_set.latest('data').valor
            except Exception:
                valor_entrada = inventario.entrada_permanente.valor

            valor_residual = Decimal('%.2f' % (float(valor_entrada) * percentual_residual_do_inventario))
            valor_depreciavel = valor_entrada - valor_residual

            reavaliados = InventarioReavaliacao.objects.filter(inventario=inventario).count()
            if reavaliados > 0:
                total_meses = vida_util_anos_do_inventario * 12 - reavaliados
                if total_meses > 0:
                    valor_depreciavel_mensal = Decimal(valor_depreciavel) / int(total_meses)
                else:
                    valor_depreciavel_mensal = Decimal(inventario.inventarioreavaliacao_set.latest('data').valor)
            else:
                valor_depreciavel_mensal = Decimal(valor_depreciavel) / Decimal(vida_util_anos_do_inventario * 12)

            hoje = date.today()
            try:
                data_ultima_depreciacao = inventario.inventariovalor_set.latest('data').data
            except InventarioValor.DoesNotExist:
                data_ultima_depreciacao = inventario.entrada_permanente.entrada.data.date()

            if data_ultima_depreciacao < DATA_INICIO_DEPRECIACAO:
                data_depreciacao = DATA_INICIO_DEPRECIACAO
            else:
                data_depreciacao = fim_proximo_mes(data_ultima_depreciacao)
            # Valor inicial ou ultima depreciação
            try:
                valor_entrada = inventario.inventariovalor_set.latest('data').valor
            except InventarioValor.DoesNotExist:
                try:
                    valor_entrada = inventario.valor
                except Exception:
                    valor_entrada = inventario.entrada_permanente.valor
            if valor_entrada is None:
                valor_entrada = Decimal(0)
            valor_novo = valor_entrada
            while (data_depreciacao < hoje) and (valor_novo > valor_residual):
                valor_novo = Decimal(valor_novo) - valor_depreciavel_mensal
                valor_inv = Decimal(f'{valor_novo:.2f}')
                if valor_inv < valor_residual:
                    break
                InventarioValor.objects.create(
                    percentual_residual=percentual_residual_do_inventario,
                    vida_util_em_anos=vida_util_anos_do_inventario,
                    inventario=inventario,
                    data=data_depreciacao,
                    valor=valor_novo,
                    uo=inventario.carga_contabil.campus,
                )

                data_depreciacao = fim_proximo_mes(data_depreciacao)

                if Decimal(f'{valor_novo:.2f}') <= 0.01:
                    break

            if InventarioValor.objects.filter(inventario=inventario).exists():
                valor_novo = inventario.inventariovalor_set.latest('data').valor
                inventario.valor = valor_novo
                inventario.__skip_history = True
                inventario.save(limpar_cache=False)


class ConferenciaSala(models.ModelPlus):
    """
    Registro do processo de conferência de bens por sala
    """

    sala = models.ForeignKeyPlus('comum.Sala', on_delete=models.CASCADE)
    observacao = models.CharFieldPlus('Observação', null=True)
    dh_criacao = models.DateTimeFieldPlus(auto_now_add=True)
    responsavel = models.ForeignKeyPlus('rh.Servidor', on_delete=models.CASCADE)
    token = models.CharField(max_length=40)

    def __str__(self):
        return self.sala.nome

    class Meta:
        verbose_name = 'Conferência de Sala'
        verbose_name_plural = 'Conferências de Sala'

    @transaction.atomic
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        # calcula hash para ser lido pelo coletor (QRCode)
        if not self.token:
            conferencia_hash = to_ascii(self.sala.nome) + str(self.dh_criacao) + to_ascii(self.responsavel.nome) + settings.SECRET_KEY
            self.token = hashlib.sha1(conferencia_hash.encode()).hexdigest()
            self.save()

    def get_absolute_url(self):
        return f'/patrimonio/conferenciasala/{self.pk}/'


class ConferenciaItem(models.ModelPlus):
    """
    Registro dos bens (Inventários) coletados durante conferência
    """

    conferencia = models.ForeignKeyPlus(ConferenciaSala, on_delete=models.CASCADE)
    dh_coleta = models.DateTimeFieldPlus()
    inventario = models.ForeignKeyPlus(Inventario, on_delete=models.CASCADE)
    estado_conservacao = models.CharField('Estado de conservação', max_length=30, blank=True, choices=Inventario.CHOICES_CONSERVACAO)
    observacao = models.CharField('Observação', max_length=255, blank=True)

    class Meta:
        verbose_name = 'Conferência de Inventário'
        verbose_name_plural = 'Conferências de Inventários'
        unique_together = ['conferencia', 'inventario']

    def __str__(self):
        return self.inventario.get_descricao()


class ConferenciaItemErro(models.ModelPlus):
    """
    Inventários que não foram encontrados no Patrimônio (erro de leitura no código de barras, etc.)
    """

    conferencia = models.ForeignKeyPlus(ConferenciaSala, on_delete=models.CASCADE)
    dh_coleta = models.DateTimeFieldPlus()
    inventario = models.IntegerField()

    class Meta:
        unique_together = ['conferencia', 'inventario']

    def __str__(self):
        return self.conferencia.token


class RequisicaoHistorico(models.ModelPlus):
    requisicao = models.ForeignKeyPlus(Requisicao, on_delete=models.CASCADE)
    status = models.PositiveIntegerField(choices=Requisicao.STATUS_CHOICES)
    alterado_em = models.DateTimeField(auto_now_add=True)
    alterado_por = models.CurrentUserField()

    class Meta:
        verbose_name = 'Histórico de Requisição'
        verbose_name_plural = 'Históricos de Requisições'

        unique_together = ('requisicao', 'status')

    def get_status(self):
        self.requisicao.status = self.status
        return self.requisicao.get_status()

    def get_status_class(self):
        status = self.status
        if status == Requisicao.STATUS_DEFERIDA:
            return 'success'
        elif status in (Requisicao.STATUS_INDEFERIDA, Requisicao.STATUS_CANCELADA):
            return 'danger'
        else:
            return 'warning'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        # demanda 709
        # altera o status da requisição associada de modo que
        # reflita, de fato, o status do último histórico
        ultimo_historico = self.requisicao.get_ultimo_historico()
        self.requisicao.status = ultimo_historico.status
        self.requisicao.save()


class HistoricoCatDepreciacao(models.ModelPlus):
    categoria = models.ForeignKeyPlus(CategoriaMaterialPermanente, on_delete=models.CASCADE)
    mes = models.IntegerField()
    ano = models.IntegerField()
    campus = models.ForeignKeyPlus(UnidadeOrganizacional, on_delete=models.CASCADE)
    valor_bruto = models.DecimalFieldPlus('Valor Bruto (R$)', null=True, blank=True, max_digits=15, decimal_places=6)
    valor_liquido = models.DecimalFieldPlus('Valor Líquido (R$)', null=True, blank=True, max_digits=15, decimal_places=6)
    valor_depreciado = models.DecimalFieldPlus('Valor Depreciável Mensal (R$)', null=True, blank=True, max_digits=15, decimal_places=6)

    class History:
        disabled = True

    class Meta:
        verbose_name = 'Histórico de Categoria de Depreciação'
        verbose_name_plural = 'Histórico de Categoria de Depreciações'
