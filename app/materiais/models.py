from datetime import datetime, timedelta
from decimal import Decimal

from django.apps import apps
from django.conf import settings
from django.db.models.functions import MD5

from almoxarifado.estoque import Estocavel
from djtools.db import models
from djtools.utils import send_notification, tl
from financeiro.models import SubElementoNaturezaDespesa
from materiais.managers import MateriaisAtivosManager
from rh.models import PessoaJuridica


class UnidadeMedida(models.ModelPlus):
    descricao = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.descricao

    class Meta:
        verbose_name = 'Unidade de Medida'
        verbose_name_plural = 'Unidades de Medida'


class Categoria(models.ModelPlus, Estocavel):
    sub_elemento_nd = models.ForeignKeyPlus(SubElementoNaturezaDespesa, on_delete=models.CASCADE, verbose_name='Subelemento')
    descricao = models.CharField('Descrição', max_length=255)
    codigo = models.CharField('Código', max_length=20)
    codigo_completo = models.CharField(max_length=20, unique=True, editable=False)
    validade = models.IntegerField(help_text='Em número de dias', null=True)

    def __str__(self):
        return f'{self.descricao} - {self.codigo_completo}'

    class Meta:
        verbose_name = 'Categoria'
        verbose_name_plural = 'Categorias'
        unique_together = (('sub_elemento_nd', 'descricao'), ('sub_elemento_nd', 'codigo'))
        permissions = (
            ('add_categoriamaterialconsumo', 'Can add categoria de material de consumo'),
            ('change_categoriamaterialconsumo', 'Can change categoria de material de consumo'),
        )

    def save(self, *args, **kwargs):
        self.codigo_completo = f'{self.sub_elemento_nd.codigo}.{self.codigo}'
        super().save(*args, **kwargs)


class CategoriaDescritor(models.ModelPlus):
    categoria = models.ForeignKeyPlus(Categoria, on_delete=models.CASCADE)
    descricao = models.CharField(max_length=255)
    ordem = models.PositiveIntegerField()
    obrigatorio = models.BooleanField(default=True, help_text='Indica se o descritor é obrigatório para os materiais')

    class Meta:
        ordering = ['categoria', 'ordem']
        unique_together = (('categoria', 'ordem'),)

    def save(self, *args, **kwargs):
        if not self.ordem:
            try:
                self.ordem = CategoriaDescritor.objects.latest('ordem').ordem + 1
            except CategoriaDescritor.DoesNotExist:
                self.ordem = 1
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.categoria!s} - {self.descricao}'


class MaterialTag(models.ModelPlus):
    descricao = models.CharField('Descrição', max_length=255)

    class Meta:
        verbose_name = 'Tag'
        verbose_name_plural = 'Tags de Materiais'

    def __str__(self):
        return self.descricao


class Material(models.ModelPlus, Estocavel):
    SEARCH_FIELDS = ['id', 'descricao', 'especificacao']

    categoria = models.ForeignKeyPlus(Categoria, on_delete=models.CASCADE)
    codigo_catmat = models.CharField('Código CATMAT', max_length=20)
    descricao = models.CharField('Descrição', max_length=255)
    especificacao = models.TextField('Especificação')
    unidade_medida = models.ForeignKeyPlus(UnidadeMedida, on_delete=models.CASCADE, verbose_name='Unidade de Medida')
    tags = models.ManyToManyField(MaterialTag)
    valor_medio = models.DecimalFieldPlus(default=0, editable=False)
    ativo = models.BooleanField(default=True)

    objects = models.Manager()
    ativos = MateriaisAtivosManager()

    class Meta:
        ordering = ['id']
        permissions = (('add_materialconsumo', 'Can add de material de consumo'), ('change_materialconsumo', 'Can change de material de consumo'))
        verbose_name = 'Material'
        verbose_name_plural = 'Materiais'
        constraints = [
            # md5 da especificacao: o TextField longo estoura o limite de 2704 bytes da entrada de btree.
            models.UniqueConstraint(
                models.F('categoria'),
                models.F('descricao'),
                MD5('especificacao'),
                models.F('unidade_medida'),
                name='materiais_material_unico',
                violation_error_message='Já existe material com esta categoria, descrição, especificação e unidade de medida.',
            ),
        ]

    def __str__(self):
        return f'#{self.pk} | {self.categoria.codigo_completo} | {self.descricao}'

    def get_ext_combo_template(self):
        descritores = []
        for d in self.materialdescritor_set.all():
            descritores.append(f'{d.categoria_descritor.descricao}: {d.descricao}')
        template = """
        <b class="false">ID: {}</b> | {} |  Categoria: <span style="color: #333">{} | CatMat: {}</span><br/>
        <span style="color: #666">{}</span><br/>
        <span style="text-decoration: underline; font-weight: bold;">Unidade: {}</span><br/>
        <i>{}</i><br/>
        <b class="azul">Tags: {}</b><br/>
        <b class="true">Valor médio: {}</b>
        """.format(
            self.pk,
            self.descricao,
            self.categoria,
            self.codigo_catmat,
            self.especificacao,
            str(self.unidade_medida),
            ' | '.join(descritores),
            ', '.join(self.tags.values_list('descricao', flat=True)),
            self.valor_medio,
        )
        return template

    @staticmethod
    def get_dt_search_fields():
        return ['id', 'descricao', 'especificacao']

    @classmethod
    def get_sem_cotacao(cls):
        ids_com_cotacao = set(MaterialCotacao.objects.values_list('material', flat=True).order_by('material'))
        return cls.objects.exclude(id__in=ids_com_cotacao)

    def get_valor_medio(self):
        valores = self.materialcotacao_set.filter(ativo=True).values_list('valor', flat=True)
        if valores:
            valor_medio = float(sum(valores)) / len(valores)
            return Decimal(f'{valor_medio:.2f}')
        else:
            return Decimal('0.00')

    def atualizar_valor_medio(self):
        Material.objects.filter(pk=self.pk).update(valor_medio=self.get_valor_medio())
        ProcessoCompraCampusMaterial = apps.get_model('compras', 'ProcessoCompraCampusMaterial')
        for i in ProcessoCompraCampusMaterial.objects.filter(material=self):
            i.atualizar_valores()


class MaterialDescritor(models.ModelPlus):
    material = models.ForeignKeyPlus(Material, on_delete=models.CASCADE)
    categoria_descritor = models.ForeignKeyPlus(CategoriaDescritor, on_delete=models.CASCADE)
    descricao = models.TextField()

    class Meta:
        unique_together = ('material', 'categoria_descritor')


class MaterialCotacao(models.ModelPlus):
    material = models.ForeignKeyPlus(Material, on_delete=models.CASCADE)
    fornecedor = models.ForeignKeyPlus(PessoaJuridica, null=True, blank=True, verbose_name='Fornecedor', on_delete=models.CASCADE)
    valor = models.DecimalFieldPlus()
    data = models.DateTimeFieldPlus(default=datetime.now)
    site = models.TextField('Site', blank=True)
    uasg = models.CharField('UASG', max_length=200, blank=True)
    numero_pregao = models.CharField('Nº de Pregão', max_length=50, blank=True)
    numero_item = models.CharField('Nº do Item', max_length=50, blank=True)
    arquivo = models.FileFieldPlus(upload_to='materiais/cotacao/', null=True, blank=True)
    ativo = models.BooleanField(default=True)
    data_validade = models.DateFieldPlus(null=True, blank=True)

    class Meta:
        ordering = ['material', 'valor']
        verbose_name = 'Cotação de material'
        verbose_name_plural = 'Cotações de material'

    def save(self, *args, **kwargs):
        """
        Atualiza o campo ``valor_medio`` do material.
        """
        if not self.pk:
            validade = self.material.categoria.validade or 180
            self.data_validade = self.data + timedelta(int(validade))

        super().save(*args, **kwargs)
        self.material.atualizar_valor_medio()

    def delete(self):
        super().delete()
        self.material.atualizar_valor_medio()

    def pode_editar(self):
        from compras.models import ProcessoMaterialCotacao

        cotacao = ProcessoMaterialCotacao.objects.filter(cotacao=self).exists()
        return not cotacao


class Requisicao(models.ModelPlus):
    REQUERIMENTO_HELP_TEXT = """Informe aqui a DESCRIÇÃO e o código CATMAT.<br/>
    De preferência, pesquisar através do
    <a href="http://www.comprasnet.gov.br/">COMPRASNET</a>
    uma descrição equivalente ao material sugerido, informando junto à descrição
    o código CATMAT correspondente.
    """
    RESPOSTA_HELP_TEXT = """Observações sobre a avaliação desta requisição"""

    STATUS_AGUARDANDO_AVALIACAO = 1
    STATUS_DEFERIDO = 2
    STATUS_INDEFERIDO_MATERIAL_EXISTENTE = 3
    STATUS_INDEFERIDO_OUTROS = 4

    status = models.IntegerField(
        default=1,
        choices=[
            [STATUS_AGUARDANDO_AVALIACAO, 'Aguardando Avaliação'],
            [STATUS_DEFERIDO, 'Deferido (o material foi cadastrado)'],
            [STATUS_INDEFERIDO_MATERIAL_EXISTENTE, 'Indeferido (o material já existe no catálogo)'],
            [STATUS_INDEFERIDO_OUTROS, 'Indeferido (outros motivos)'],
        ],
    )

    cadastrada_em = models.DateTimeField(auto_now_add=True)
    usuario_solicitante = models.CurrentUserField(related_name='materiais_requisicoessolicitadas_set')
    requerimento = models.TextField(help_text=REQUERIMENTO_HELP_TEXT)

    respondida_em = models.DateTimeField(null=True, blank=True, editable=False)
    usuario_resposta = models.ForeignKeyPlus(
        'comum.User', null=True, blank=True, on_delete=models.CASCADE, related_name='materiais_requisicoesrespondidas_set'
    )
    resposta = models.TextField(help_text=RESPOSTA_HELP_TEXT, blank=True)
    material = models.ForeignKeyPlus(
        Material, null=True, blank=True, on_delete=models.CASCADE, help_text='Informe aqui o material referente à resposta'
    )

    class Meta:
        verbose_name = 'Requisição'
        verbose_name_plural = 'Requisições'

    @classmethod
    def get_pendentes(cls):
        return cls.objects.filter(status=cls.STATUS_AGUARDANDO_AVALIACAO)

    def pode_avaliar(self):
        return self.status == self.STATUS_AGUARDANDO_AVALIACAO and tl.get_user().has_perm('materiais.add_material')

    def pode_remover_pendente(self):
        return self.status == self.STATUS_AGUARDANDO_AVALIACAO and self.usuario_solicitante == tl.get_user()

    def avaliar(self, status, resposta, material=None, enviar_email_para_solicitante=True):
        # Validação
        if status == self.STATUS_AGUARDANDO_AVALIACAO:
            raise Exception('O status deve ser modificado')
        elif status == self.STATUS_INDEFERIDO_OUTROS and material:
            raise Exception('O material nao pode ser informado com o status informado')
        elif status != self.STATUS_INDEFERIDO_OUTROS and not material:
            raise Exception('O material deve ser informado')

        # Alterando informações
        self.respondida_em = datetime.now()
        self.usuario_resposta = tl.get_user()
        self.status = status
        self.resposta = resposta
        self.material = material
        self.save()

        if enviar_email_para_solicitante:
            self.enviar_email_apos_avaliacao()

    def enviar_email_apos_avaliacao(self):
        subject = f'[SUAP] Catálogo de Materiais: Requisição #{self.pk} respondida'
        message = [f'<h1>Catálogo de Materiais</h1><h2>Requisição #{self.pk} foi respondida</h2>']
        message.append(f'<dl><dt>Solicitação:</dt><dd>{self.requerimento}</dd>')
        message.append(f'<dt>Resposta:</dt><dd>{self.resposta}</dd></dl>')
        message = ''.join(message)

        send_notification(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [self.usuario_solicitante.get_vinculo()],
            categoria='Catálogo de Materiais: Requisição Respondida',
        )
