from django.core.exceptions import ValidationError
from django.db.models.aggregates import Sum

from almoxarifado.models import MaterialConsumo as AMaterialConsumo
from almoxarifado.models import MaterialEstoque
from comum.models import Sala
from djtools.db import models
from patrimonio.models import Inventario
from rh.models import UnidadeOrganizacional
from siads.utils import clear_masks, get_chefe, is_empty, trim


class GrupoMaterialConsumo(models.Model):
    nome = models.CharField('Nome', max_length=1024)
    sentenca = models.CharField('Sentença processada', max_length=1024)
    unidade = models.CharField(max_length=50, default='')

    class Meta:
        verbose_name = 'Grupo de Material de Consumo'
        verbose_name_plural = 'Grupos de Material de Consumo'

    def __str__(self):
        return self.nome

    @property
    def has_invalidados(self):
        return self.materialconsumo_set.filter(validado=False).exists()


class MaterialConsumo(models.Model):
    grupo = models.ForeignKey(GrupoMaterialConsumo, on_delete=models.CASCADE)
    material = models.ForeignKey('almoxarifado.MaterialConsumo', on_delete=models.CASCADE)
    nome_original = models.CharField('Nome Original', max_length=1024)
    nome_processado = models.CharField('Nome Processado', max_length=1024, null=True)
    validado = models.BooleanField('Validado', default=False)

    def get_item_link(self):
        return f'/admin/almoxarifado/materialconsumo/{self.material.pk}/view/'

    @property
    def codigo(self):
        return self.material.codigo

    @property
    def nome(self):
        return self.grupo.nome

    @property
    def unidade_medida(self):
        return self.grupo.unidade

    def get_quantidade(self, uo):
        estoque = MaterialEstoque.objects.filter(uo=uo, material=self.material)
        estoque = estoque.aggregate(qtd=Sum('quantidade'))
        return estoque['qtd']

    def get_valor_saldo(self, uo):
        estoque = MaterialEstoque.objects.filter(uo=uo, material=self.material)
        estoque = estoque.aggregate(valor=Sum('valor_medio'))
        return estoque['valor']

    @classmethod
    def get_materiais(cls, uo):
        materiais = AMaterialConsumo.objects.com_estoque_por_uo(uo=uo)
        materiais = materiais.values_list('id', flat=True)
        return cls.objects.filter(material_id__in=materiais)


class GrupoMaterialPermanente(models.Model):
    uo = models.ForeignKeyPlus(UnidadeOrganizacional, on_delete=models.CASCADE, null=True)
    nome = models.CharField('Nome', max_length=8000)
    sentenca = models.CharField('Sentença processada', max_length=8000)

    class Meta:
        verbose_name = 'Grupo de Entrada Permanente'
        verbose_name_plural = 'Grupos de Entradas Permanente'

    def __str__(self):
        return self.nome

    @property
    def has_invalidados(self):
        return self.materialpermanente_set.filter(validado=False).exists()


class MaterialPermanente(models.Model):
    grupo = models.ForeignKey(GrupoMaterialPermanente, on_delete=models.CASCADE)
    uo = models.ForeignKeyPlus(UnidadeOrganizacional, on_delete=models.CASCADE, null=True)
    entrada = models.ForeignKey('patrimonio.EntradaPermanente', on_delete=models.CASCADE, null=True)
    nome_original = models.CharField('Nome Original', max_length=8000)
    nome_processado = models.CharField('Nome Processado', max_length=8000, null=True)
    validado = models.BooleanField('Validado', default=False)

    nr_serie = models.CharField('Nr. de Série', max_length=15, blank=True)
    marca = models.CharField('Marca do Bem', max_length=20, blank=True)
    modelo = models.CharField('Modelo do Bem', max_length=20, blank=True)
    fabricante = models.CharField('Fabricante', max_length=50, blank=True)

    class Meta:
        verbose_name = 'Entrada Permanente'
        verbose_name_plural = 'Entradas Permanente'
        permissions = (('siads_pode_ajustar_permanente', 'Pode ajustar entrada permanete - SIADS'),)

    def get_item_link(self):
        return f'/patrimonio/inventario/{self.material.pk}/'

    def get_empenho(self):
        return self.entrada.entrada.get_empenho()

    def get_empenho_numero(self):
        empenho = self.get_empenho()
        return empenho and empenho.numero

    def get_empenho_link(self):
        empenho = self.get_empenho()
        return empenho and empenho.get_absolute_url()


class SetorSiads(models.Model):
    TIPO_SALA = 'SALA'
    TIPO_SETOR = 'SETOR'
    TIPO_CHOICES = ((TIPO_SALA, 'Sala'), (TIPO_SETOR, 'Setor'))
    tipo = models.CharFieldPlus('Tipo', max_length=5, default=TIPO_SETOR)
    uo = models.ForeignKeyPlus(UnidadeOrganizacional)
    setor_suap = models.ForeignKeyPlus('rh.Setor', null=True)
    sala = models.ForeignKeyPlus('comum.Sala', null=True)
    chefe = models.ForeignKeyPlus('rh.Servidor', null=True)

    uorg = models.CharField('Código da UORG', max_length=100, blank=True)
    ug_vinvulada = models.CharField('Código da UG Vínculada', max_length=6, blank=False)
    nome = models.CharField('Nome da UORG', max_length=100, blank=False)
    sigla = models.CharField('Sigla da UORG', max_length=16, blank=False)
    endereco = models.CharField('Endereço da UORG', max_length=60, blank=True)
    cep = models.CharField('CEP da UORG', max_length=8, blank=True)
    ddd = models.CharField('DDD da UORG', max_length=4, blank=True)
    telefone = models.CharField('Telefone da UORG', max_length=8, blank=True)
    ramal = models.CharField('Ramal da UORG', max_length=4, blank=True)
    cpf_responsavel = models.CharField('CPF do responsável', max_length=11, blank=True)
    nome_responsavel = models.CharField('Nome do responsável', max_length=40, blank=True)
    matricula_siape = models.CharField('Matrícula do responsável', max_length=12, blank=True)
    portaria = models.CharField('Portaria de nomeação', max_length=25, blank=True)
    uorg_subordinada = models.CharField('Código da UORG Subordinada', max_length=100, blank=True)
    nome_reduzido = models.CharField('Nome reduzido', max_length=40, blank=False)
    data_criacao = models.CharField('Data da criação', max_length=8, blank=True)
    numero_doc_criacao = models.CharField('Doc. de criação', max_length=60, blank=True)
    sigla_uf = models.CharField('Sigla da UF', max_length=2, blank=False)
    municipio = models.CharField('Município', max_length=40, blank=False)
    email = models.CharField('E-mail', max_length=50, blank=True)

    exportavel = models.BooleanField('Exportável', default=True)
    ajustado = models.BooleanField('Ajustado', default=False)

    class Meta:
        verbose_name = 'Setor Siads'
        verbose_name_plural = 'Setores Siads'

    def __str__(self):
        return f'{self.uorg} - {self.sigla}'

    def save(self, *args, **kwargs):
        if self.chefe:
            self.cpf_responsavel = clear_masks(self.chefe.cpf)
            self.nome_responsavel = trim(self.chefe.nome, 40)
            self.matricula_siape = self.chefe.matricula
        super().save(*args, **kwargs)

        if self.uorg is None or self.uorg == '':
            self.uorg = str(self.id)
            super().save(*args, **kwargs)

    def clean(self):
        if not is_empty(self.ddd):
            if is_empty(self.telefone) or is_empty(self.ramal):
                raise ValidationError('O telefone e/ou ramal são obrigatórios ao preencher o ddd.')

        if self.setor_suap is None and self.sala is None:
            raise ValidationError('Deve-se escolher um setor e/ou uma sala.')

    @property
    def codigo_siorg(self):
        return self.uorg

    @classmethod
    def get_chefe_by_vinculo(cls, vinculo):
        if vinculo is not None:
            setor = cls.objects.filter(setor_suap=vinculo.setor)

            if setor.exists():
                return setor.first()

        return None

    @classmethod
    def get_setores_as_dict(cls):
        ret = {}
        for setor in cls.objects.all():
            ret[setor.setor_suap_id] = {'uorg': setor.uorg, 'chefe_id': setor.chefe_id, 'cpf_responsavel': setor.cpf_responsavel}

        return ret

    @classmethod
    def processar(cls, tipo, task=None):
        def pro_setor(uo):
            new_itens = 0
            total_itens = 0
            error_itens = []

            for setor in uo.setor_set.all():
                if setor.setor_eh_campus or setor.eh_orgao_colegiado or setor.qtd_servidores() < 1:
                    continue
                setor_siads = SetorSiads.objects.filter(setor_suap=setor)

                if not setor_siads.exists():
                    new_itens += 1
                    setor_siads = SetorSiads()
                    setor_siads.tipo = SetorSiads.TIPO_SETOR
                    setor_siads.setor_suap = setor

                    if setor.chefes.exists():
                        chefe = get_chefe(setor.chefes.order_by('funcao__codigo'))
                        setor_siads.chefe = chefe
                else:
                    total_itens += 1
                    setor_siads = setor_siads.first()
                    if setor_siads.ajustado:
                        continue

                setor_siads.uo = uo
                setor_siads.uorg = setor.codigo_siorg or ''
                setor_siads.ug_vinvulada = uo.codigo_ug
                setor_siads.nome = setor.nome
                setor_siads.sigla = setor.sigla

                if uo.municipio:
                    setor_siads.sigla_uf = uo.municipio.uf
                    setor_siads.municipio = uo.municipio.nome

                if uo.cep:
                    cep = clear_masks(uo.cep)
                    if len(cep) == 8:
                        setor_siads.cep = cep
                        setor_siads.endereco = trim(uo.endereco, 60)

                telefone = setor.setortelefone_set.exclude(numero='').exclude(ramal='')
                if telefone.exists():
                    telefone = telefone.first()
                    ramal = clear_masks(telefone.ramal)
                    telefone = clear_masks(telefone.numero)[-8:]
                    if telefone != '' and not (len(telefone) < 8):
                        setor_siads.ddd = '84'
                        setor_siads.telefone = telefone
                        setor_siads.ramal = ramal

                try:
                    setor_siads.clean()
                    setor_siads.save()
                except Exception as ex:
                    error_itens.append((setor, str(ex)))
            return new_itens, total_itens, error_itens

        def pro_sala(uo):
            new_itens = 0
            total_itens = 0
            error_itens = []

            for sala in Sala.ativas.filter(predio__uo=uo):
                setor_siads = SetorSiads.objects.filter(sala=sala)

                if not setor_siads.exists():
                    new_itens += 1
                    setor_siads = SetorSiads()
                    setor_siads.tipo = SetorSiads.TIPO_SALA
                    setor_siads.sala = sala
                else:
                    total_itens += 1
                    setor_siads = setor_siads.first()
                    if setor_siads.ajustado:
                        continue

                setor_siads.uo = uo
                setor_siads.uorg = ''
                setor_siads.ug_vinvulada = uo.codigo_ug
                setor_siads.nome = sala.nome
                setor_siads.sigla = ''

                if uo.municipio:
                    setor_siads.sigla_uf = uo.municipio.uf
                    setor_siads.municipio = uo.municipio.nome

                if uo.cep:
                    cep = clear_masks(uo.cep)
                    if len(cep) == 8:
                        setor_siads.cep = cep
                        setor_siads.endereco = trim(uo.endereco, 60)

                setor_siads.exportavel = False

                try:
                    setor_siads.clean()
                    setor_siads.save()
                except Exception as ex:
                    error_itens.append((sala, str(ex)))
            return new_itens, total_itens, error_itens

        uos = UnidadeOrganizacional.objects.filter(tipo__isnull=False)
        uos = uos.exclude(tipo_id=UnidadeOrganizacional.TIPO_CONSELHO)

        new_itens = 0
        total_itens = 0
        error_itens = []

        if task:
            task.count(uos)

        for uo in task.iterate(uos):
            if tipo == 'SETOR':
                new, total, error = pro_setor(uo)
            else:
                new, total, error = pro_sala(uo)
            new_itens += new
            total_itens += total
            error_itens += error
        return new_itens, total_itens, error_itens


class MaterialConsumoSiads(models.Model):
    uo = models.ForeignKeyPlus(UnidadeOrganizacional)
    material = models.ForeignKeyPlus(MaterialConsumo)

    codigo_material = models.CharField('Código do material', max_length=100, blank=False)
    descricao = models.CharField('Descrição', max_length=300, blank=False)
    unidade_medida = models.CharField('Unidade de medida', max_length=20, blank=False)
    codigo_conta = models.CharField('Código da conta contábil', max_length=9, blank=False)
    endereco = models.CharField('Endereço', max_length=9, blank=False)
    qtd_disponivel = models.CharField('Quantidade disponível', max_length=10, blank=False)
    valor_saldo = models.CharField('Valor Saldo', max_length=18, blank=False)
    estocavel = models.BooleanField('Estocável')

    exportavel = models.BooleanField('Exportável', default=True)
    ajustado = models.BooleanField('Exportável', default=False)

    class Meta:
        verbose_name = 'Material de Consumo Siads'
        verbose_name_plural = 'Materiais de Consumo Siads'

    def __str__(self):
        return f'{self.uo} - {self.descricao}'

    def save(self, *args, **kwargs):
        if self.id is not None:
            self.ajustado = True
        super().save(*args, **kwargs)

    @property
    def quantidade(self):
        return int(self.qtd_disponivel)

    @classmethod
    def processar(cls, uo=None, task=None):
        uos = None
        if uo is not None:
            uos = UnidadeOrganizacional.objects.filter(id=uo.id)
        else:
            uos = UnidadeOrganizacional.objects.filter(tipo__isnull=False)
            uos = uos.exclude(tipo_id=UnidadeOrganizacional.TIPO_CONSELHO)

        task.count(uos)
        total = 0
        errors = []
        for uo_ in task.iterate(uos):
            for material in MaterialConsumo.get_materiais(uo=uo_):
                material_siads = MaterialConsumoSiads.objects.filter(material=material)

                if not material_siads.exists():
                    material_siads = MaterialConsumoSiads()
                    material_siads.uo = uo_
                    material_siads.material = material
                else:
                    material_siads = material_siads.first()
                    if material_siads.ajustado:
                        continue

                material_siads.codigo_material = material.codigo

                desc = material.nome.replace('\r', '').replace('\n', ' ')
                material_siads.descricao = trim(desc, 300)

                material_siads.unidade_medida = trim(material.nome, 20)

                if material.material.categoria.plano_contas:
                    material_siads.codigo_conta = trim(clear_masks(material.material.categoria.plano_contas.codigo), 9)
                else:
                    material_siads.codigo_conta = '999999999'

                material_siads.endereco = 'ZZ'
                material_siads.qtd_disponivel = material.get_quantidade(uo_)
                material_siads.valor_saldo = clear_masks(str(material.get_valor_saldo(uo_)))
                material_siads.estocavel = True

                try:
                    material_siads.save()
                except Exception:
                    errors.append(material.id)
                total += 1
        return total, errors


class MaterialPermanenteSiads(models.Model):
    uo = models.ForeignKeyPlus(UnidadeOrganizacional)
    inventario = models.ForeignKeyPlus(Inventario, on_delete=models.DO_NOTHING)

    codigo_material = models.CharField('Código', max_length=100, blank=False)
    descricao = models.CharField('Descricao', max_length=300, blank=False)
    codigo_conta = models.CharField('Conta Contábil', max_length=9, blank=False)
    endereco = models.CharField('Localização', max_length=50, blank=False)
    uorg = models.CharField('Código da UORG', max_length=100, blank=False)
    tipo = models.CharField('Tipo', max_length=1, default='1')
    situacao = models.CharField('Situação', max_length=1, default='1')
    tipo_plaqueta = models.CharField('Tipo da Plaqueta', max_length=1, default='3')
    dt_tombamento = models.CharField('Data do Tombamento', max_length=8, blank=False)
    vlr_bem = models.CharField('Valor do Bem', max_length=18, blank=False)
    forma_aquisicao = models.CharField('Forma da Aquisição', max_length=20, blank=False)
    especificacao = models.CharField('Detalhes Específicos', max_length=209, blank=False)
    dt_devolucao = models.CharField('Data de Devolução', max_length=8)
    nr_serie = models.CharField('Nr. de Série', max_length=15)
    patrimonio = models.CharField('Patrimônio', max_length=10, blank=False)
    marca = models.CharField('Marca do Bem', max_length=20)
    modelo = models.CharField('Modelo do Bem', max_length=20)
    fabricante = models.CharField('Fabricante', max_length=50)
    garantidor = models.CharField('Responsável pela Garantia', max_length=50)
    nr_contrato = models.CharField('Número do Contrato', max_length=6)
    inicio_garantia = models.CharField('Inicio da Garantia', max_length=8)
    fim_garantia = models.CharField('Fim da Garantia', max_length=8)
    cpf_responsavel = models.CharField('Responsável', max_length=11)
    corresponsavel = models.CharField('Nome do Corresponsável', max_length=50)
    almoxarifado = models.BooleanField('Está no Almoxarifado', default=False)
    dt_reavaliacao = models.CharField('Data da Reavaliação', max_length=8)
    vlr_reavaliacao = models.CharField('Valor da Reavaliação', max_length=8)
    vida_util = models.CharField('Vida Útil em Meses', max_length=3)

    exportavel = models.BooleanField('Exportável', default=True)
    ajustado = models.BooleanField('Exportável', default=False)

    class Meta:
        verbose_name = 'Material Permanente Siads'
        verbose_name_plural = 'Materiais Permanete Siads'

    def __str__(self):
        return f'{self.uo} - {self.descricao}'

    def save(self, *args, **kwargs):
        if self.id is not None:
            self.ajustado = True
        super().save(*args, **kwargs)

    @property
    def valor(self):
        return float(self.vlr_bem)

    @classmethod
    def processar(cls, uo=None, task=None):
        uos = None
        if uo is not None:
            uos = UnidadeOrganizacional.objects.filter(id=uo.id)
            MaterialPermanenteSiads.objects.filter(uo=uo).delete()
        else:
            uos = UnidadeOrganizacional.objects.filter(tipo__isnull=False)
            uos = uos.exclude(tipo_id=UnidadeOrganizacional.TIPO_CONSELHO)
            MaterialPermanenteSiads.objects.all().delete()

        task.count(uos)
        total = 0
        errors = []
        setores_siads = SetorSiads.get_setores_as_dict()
        for uo_ in task.iterate(uos):
            materiais_permanentes = MaterialPermanente.objects.select_related('grupo').filter(uo=uo_)
            for entrada_permanente in materiais_permanentes:
                inventarios = (
                    Inventario.objects.select_related('entrada_permanente__categoria__plano_contas')
                    .select_related('sala')
                    .select_related('responsavel_vinculo__pessoa')
                    .filter(entrada_permanente_id=entrada_permanente.entrada_id)
                )
                for inventario in inventarios:
                    material_siads = MaterialPermanenteSiads.objects.filter(inventario=inventario)

                    if material_siads.exists() and material_siads.first().ajustado:
                        continue

                    material_siads = MaterialPermanenteSiads()
                    material_siads.uo = uo_
                    material_siads.inventario = inventario

                    material_siads.codigo_material = str(inventario.numero)
                    desc = entrada_permanente.grupo.nome.replace('\r', '').replace('\n', ' ')
                    material_siads.descricao = trim(desc, 300)

                    if inventario.entrada_permanente.categoria.plano_contas:
                        material_siads.codigo_conta = trim(clear_masks(inventario.entrada_permanente.categoria.plano_contas.codigo), 9)
                    else:
                        material_siads.codigo_conta = '999999999'

                    material_siads.endereco = ''
                    if inventario.sala is not None:
                        material_siads.endereco = trim(inventario.sala.nome, 50)

                    material_siads.uorg = 'SEM VINCULO'
                    if inventario.responsavel_vinculo is not None:
                        dados = setores_siads.get(inventario.responsavel_vinculo.setor_id, None)
                        if dados is not None:
                            material_siads.uorg = dados['uorg']
                        else:
                            material_siads.uorg = 'NÃO ENCONTRADO'

                    material_siads.tipo = '1'

                    if inventario.estado_conservacao == Inventario.CONSERVACAO_RECUPERAVEL:
                        material_siads.situacao = '2'
                    elif inventario.estado_conservacao in [Inventario.CONSERVACAO_IRRECUPERAVEL, Inventario.CONSERVACAO_IRREVERSIVEL]:
                        material_siads.situacao = '3'
                    elif inventario.estado_conservacao == Inventario.CONSERVACAO_OCIOSO:
                        material_siads.situacao = '4'
                    elif inventario.estado_conservacao == Inventario.CONSERVACAO_ANTIECONOMICO:
                        material_siads.situacao = '5'
                    else:
                        material_siads.situacao = '1'

                    material_siads.tipo_plaqueta = '3'
                    material_siads.dt_tombamento = '01012000'
                    material_siads.vlr_bem = clear_masks(inventario.get_valor())

                    material_siads.forma_aquisicao = 'EMPENHO'
                    material_siads.especificacao = 'SEM ESPECIFICAÇÃO'
                    material_siads.dt_devolucao = ''
                    material_siads.nr_serie = inventario.numero_serie
                    material_siads.patrimonio = inventario.numero
                    material_siads.marca = entrada_permanente.marca
                    material_siads.modelo = entrada_permanente.modelo
                    material_siads.fabricante = entrada_permanente.fabricante
                    material_siads.garantidor = ''
                    material_siads.nr_contrato = ''
                    material_siads.inicio_garantia = ''
                    material_siads.fim_garantia = ''

                    vinculo = inventario.responsavel_vinculo
                    if vinculo is not None and vinculo.setor is not None:
                        setor_dados = setores_siads.get(vinculo.setor_id, None)
                        if setor_dados is not None:
                            material_siads.cpf_responsavel = ''
                            if vinculo.id_relacionamento != setor_dados['chefe_id']:
                                material_siads.cpf_responsavel = clear_masks(vinculo.pessoa.pessoafisica.cpf)
                                material_siads.corresponsavel = vinculo.pessoa.nome
                        else:
                            material_siads.cpf_responsavel = 'SETOR SIADS'
                    else:
                        material_siads.cpf_responsavel = 'VINCULO|SETOR'

                    material_siads.almoxarifado = False
                    material_siads.dt_reavaliacao = ''
                    material_siads.vlr_reavaliacao = ''
                    material_siads.vida_util = '999'

                    try:
                        material_siads.save()
                    except Exception:
                        errors.append(inventario.id)
                    total += 1
        return total, errors
