from decimal import Decimal

from django.core.exceptions import ValidationError

from djtools.db import models
from rh.models import UnidadeOrganizacional


# -------------------- Natureza de Despesa --------------------------------------
class CategoriaEconomicaDespesa(models.ModelPlus):
    codigo = models.CharField('Código', max_length=1)
    nome = models.CharField('Nome', max_length=100)
    descricao = models.TextField('Descrição', blank=True)

    class Meta:
        verbose_name = 'Categoria Econômica da Despesa'
        verbose_name_plural = 'Categorias Econômicas da Despesa'
        ordering = ['codigo']

    def __str__(self):
        return f'{self.codigo} - {self.nome}'


class GrupoNaturezaDespesa(models.ModelPlus):
    codigo = models.CharField('Código', max_length=1)
    nome = models.CharField('Nome', max_length=100)
    descricao = models.TextField('Descrição', blank=True)

    class Meta:
        verbose_name = 'Grupo de Natureza de Despesa'
        verbose_name_plural = 'Grupos de Naturezas de Despesa'
        ordering = ['codigo']

    def __str__(self):
        return f'{self.codigo} - {self.nome}'


class ModalidadeAplicacao(models.ModelPlus):
    codigo = models.CharField('Código', max_length=2)
    nome = models.CharField('Nome', max_length=150)
    descricao = models.TextField('Descrição', blank=True)

    class Meta:
        verbose_name = 'Modalidade da Aplicação'
        verbose_name_plural = 'Modalidades da Aplicação'
        ordering = ['codigo']

    def __str__(self):
        return f'{self.codigo} - {self.nome}'


class ElementoDespesa(models.ModelPlus):
    codigo = models.CharField('Código', max_length=2)
    nome = models.CharField('Nome', max_length=100)
    descricao = models.TextField('Descrição', blank=True)

    class Meta:
        verbose_name = 'Elemento de Despesa'
        verbose_name_plural = 'Elementos de Despesa'
        ordering = ['codigo']

    def __str__(self):
        return f'{self.codigo} - {self.nome}'


class NaturezaDespesa(models.ModelPlus):
    SEARCH_FIELDS = ['nome', 'codigo']
    VALOR_CUSTEIO = 'Custeio'
    VALOR_CAPTAL = 'Capital'
    TIPO_VALOR_CHOICES = ((VALOR_CUSTEIO, VALOR_CUSTEIO), (VALOR_CAPTAL, VALOR_CAPTAL))

    categoria_economica_despesa = models.ForeignKeyPlus(CategoriaEconomicaDespesa, verbose_name='Categoria Econômica', on_delete=models.CASCADE)
    grupo_natureza_despesa = models.ForeignKeyPlus(GrupoNaturezaDespesa, verbose_name='Grupo Natureza Despesa', on_delete=models.CASCADE)
    modalidade_aplicacao = models.ForeignKeyPlus(ModalidadeAplicacao, verbose_name='Modalidade da Aplicação', on_delete=models.CASCADE)
    elemento_despesa = models.ForeignKeyPlus(ElementoDespesa, verbose_name='Elemento da Despesa', on_delete=models.CASCADE)
    nome = models.CharField('Nome', max_length=100, blank=True)
    codigo = models.CharField('Código', max_length=6)
    tipo = models.CharField('Tipo', max_length=30, null=True, choices=TIPO_VALOR_CHOICES)

    class Meta:
        ordering = ['codigo']
        unique_together = ('categoria_economica_despesa', 'grupo_natureza_despesa', 'modalidade_aplicacao', 'elemento_despesa')
        verbose_name = 'Natureza de Despesa'
        verbose_name_plural = 'Naturezas de Despesas'

    def __str__(self):
        return f'{self.codigo} - {self.nome}'


class ClassificacaoDespesa(models.ModelPlus):
    codigo = models.CharField('Código', max_length=2, unique=True)
    nome = models.CharField('Nome', max_length=100)

    class Meta:
        verbose_name = 'Classificação de Despesa'
        verbose_name_plural = 'Classificações de Despesas'

    def __str__(self):
        return f'{self.codigo} - {self.nome}'


class SubElementoNaturezaDespesa(models.ModelPlus):
    SEARCH_FIELDS = ['codigo_subelemento', 'nome', 'codigo']
    codigo_subelemento = models.CharField('Código', max_length=2)
    natureza_despesa = models.ForeignKeyPlus(NaturezaDespesa, verbose_name='Natureza de Despesa', on_delete=models.CASCADE)
    nome = models.CharField('Nome', max_length=100)
    codigo = models.CharField('Código', max_length=8, unique=True)

    class Meta:
        verbose_name = 'Subelemento da Natureza de Despesa'
        verbose_name_plural = 'Subelementos da Natureza de Despesa'
        unique_together = ['codigo_subelemento', 'natureza_despesa']

    def __str__(self):
        return f'{self.natureza_despesa.codigo}.{self.codigo_subelemento} - {self.nome}'

    def save(self, *args, **kwargs):
        self.nome = self.nome or ''
        self.codigo = f'{self.natureza_despesa.codigo}{self.codigo_subelemento}'
        super().save(*args, **kwargs)


# -------------------- Fonte de Recurso --------------------------------------
class GrupoFonteRecurso(models.ModelPlus):
    codigo = models.CharField('Código', max_length=1)
    nome = models.CharField('Nome', max_length=50)

    class Meta:
        verbose_name = 'Grupo de Fonte de Recurso'
        verbose_name_plural = 'Grupos de Fontes de Recursos'
        ordering = ['codigo']

    def __str__(self):
        return f'{self.codigo} - {self.nome}'


class EspecificacaoFonteRecurso(models.ModelPlus):
    codigo = models.CharField('Código', max_length=2)
    nome = models.CharField('Nome', max_length=100)

    class Meta:
        verbose_name = 'Especificação da Fonte de Recurso'
        verbose_name_plural = 'Especificações das Fontes de Recursos'
        ordering = ['codigo']

    def __str__(self):
        return f'{self.codigo} - {self.nome}'


class FonteRecurso(models.ModelPlus):
    codigo = models.CharField('Código', max_length=3)
    nome = models.CharField('Fonte do recurso', max_length=100, unique=True)
    grupo = models.ForeignKeyPlus(GrupoFonteRecurso, verbose_name='Grupo', on_delete=models.CASCADE)
    especificacao = models.ForeignKeyPlus(EspecificacaoFonteRecurso, verbose_name='Especificação', on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Fonte de Recurso'
        verbose_name_plural = 'Fontes de Recursos'
        unique_together = ('grupo', 'especificacao')

    def __str__(self):
        return f'{self.codigo} - {self.nome}'

    def save(self, *args, **kwargs):
        self.codigo = f'{self.grupo.codigo}{self.especificacao.codigo}'
        super().save(*args, **kwargs)


# -------------------- Classificação Funcional --------------------------------------
class Funcao(models.ModelPlus):
    codigo = models.CharField('Código', max_length=2)
    nome = models.CharField('Nome', max_length=200)

    class Meta:
        verbose_name = 'Função'
        verbose_name_plural = 'Funções'
        ordering = ['codigo']

    def __str__(self):
        return f'{self.codigo} - {self.nome}'


class Subfuncao(models.ModelPlus):
    codigo = models.CharField('Código', max_length=3)
    nome = models.CharField('Nome', max_length=200)

    class Meta:
        verbose_name = 'Subfunção'
        verbose_name_plural = 'Subfunções'
        ordering = ['codigo']

    def __str__(self):
        return f'{self.codigo} - {self.nome}'


# -------------------- Localização --------------------------------------
class Localizacao(models.ModelPlus):
    codigo = models.CharField('Código', max_length=4)
    nome = models.CharField('Nome', max_length=100)
    sigla = models.CharField('Sigla', max_length=2, null=True)

    class Meta:
        verbose_name = 'Localização'
        verbose_name_plural = 'Localizações'
        ordering = ['nome']

    def __str__(self):
        return f'{self.codigo} - {self.nome}'


class IdentificadorUso(models.ModelPlus):
    codigo = models.SmallIntegerField('Código')
    nome = models.CharField('Nome', max_length=200)

    class Meta:
        verbose_name = 'Identificador de Uso'
        verbose_name_plural = 'Identificadores de Uso'
        ordering = ['nome']

    def __str__(self):
        return f'{self.codigo} - {self.nome}'


class IdentificadorResultadoPrimario(models.ModelPlus):
    codigo = models.SmallIntegerField('Código')
    nome = models.CharField('Nome', max_length=200)

    class Meta:
        verbose_name = 'Identificador de Resultado Primário'
        verbose_name_plural = 'Identificadores de Resultado Primário'
        ordering = ['nome']

    def __str__(self):
        return f'{self.codigo} - {self.nome}'


class UnidadeGestora(models.ModelPlus):
    SEARCH_FIELDS = ['codigo', 'mnemonico', 'nome']
    codigo = models.CharField('Código', max_length=6, unique=True)
    mnemonico = models.CharField('Mnemônico', max_length=20, null=True)
    nome = models.CharField('Nome', max_length=50)
    municipio = models.ForeignKeyPlus('comum.Municipio', null=True, blank=True, on_delete=models.CASCADE)
    funcao = models.CharField(
        'Função', max_length=15, choices=[['', ''], ['Executora', 'Executora'], ['Credora', 'Credora'], ['Controle', 'Controle']], default=''
    )
    setor = models.ForeignKeyPlus('rh.Setor', null=True, on_delete=models.CASCADE)
    ativo = models.BooleanField(default=True)
    uo = models.ForeignKeyPlus(UnidadeOrganizacional, null=True, blank=True, on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Unidade Gestora'
        verbose_name_plural = 'Unidades Gestoras'

    def __str__(self):
        return f'{self.codigo} - {self.nome}'


class ClassificacaoInstitucional(models.ModelPlus):
    SEARCH_FIELDS = ['codigo', 'nome']
    """Referenciado como gestão, ex: 26435 = IFRN"""
    codigo = models.CharField('Código', max_length=5)
    nome = models.CharField('Nome', max_length=300)

    class Meta:
        verbose_name = 'Classificação Institucional'
        verbose_name_plural = 'Classificações Institucionais'

    def __str__(self):
        return f'{self.codigo} - {self.nome}'


class EsferaOrcamentaria(models.ModelPlus):
    codigo = models.CharField('Código', max_length=2, unique=True)
    nome = models.CharField('Nome', max_length=100, unique=True)

    class Meta:
        verbose_name = 'Esfera Orçamenária'
        verbose_name_plural = 'Esferas Orçamenárias'

    def __str__(self):
        return f'{self.codigo} - {self.nome}'


class InstrumentoLegal(models.ModelPlus):
    codigo = models.CharField('Código', max_length=2, unique=True)
    nome = models.CharField('Nome', max_length=50, unique=True)

    class Meta:
        verbose_name = 'Instrumento Legal'
        verbose_name_plural = 'Instrumentos Legais'

    def __str__(self):
        return f'{self.codigo} - {self.nome}'


class ModalidadeLicitacao(models.ModelPlus):
    codigo = models.CharField('Código', max_length=2, unique=True)
    nome = models.CharField('Nome', max_length=50, unique=True)

    class Meta:
        verbose_name = 'Modalidade de Licitação'
        verbose_name_plural = 'Modalidades de Licitação'

    def __str__(self):
        return f'{self.codigo} - {self.nome}'


class UnidadeMedida(models.ModelPlus):
    nome = models.CharField('Nome', max_length=50, unique=True)

    class Meta:
        verbose_name = 'Unidade de Medida'
        verbose_name_plural = 'Unidades de Medida'

    def __str__(self):
        return self.nome


class Programa(models.ModelPlus):
    codigo = models.CharField('Código', max_length=4)
    nome = models.CharField('Nome', max_length=100)

    class Meta:
        verbose_name = 'Programa'
        verbose_name_plural = 'Programas'
        unique_together = ('codigo', 'nome')

    def __str__(self):
        return f'{self.codigo} - {self.nome}'


class Acao(models.ModelPlus):
    SEARCH_FIELDS = ['programa__codigo', 'codigo_acao', 'nome']
    codigo_acao = models.CharField('Código', max_length=4)
    nome = models.CharField('Nome', max_length=200)
    programa = models.ForeignKeyPlus(Programa, on_delete=models.CASCADE)
    codigo = models.CharField('Código Completo', max_length=8, unique=True)

    class Meta:
        verbose_name = 'Ação'
        verbose_name_plural = 'Ações'
        unique_together = ['codigo_acao', 'programa']

    def __str__(self):
        return f'{self.programa.codigo}.{self.codigo_acao} - {self.nome}'

    def save(self, *args, **kwargs):
        self.codigo = f'{self.programa.codigo}{self.codigo_acao}'
        super().save(*args, **kwargs)


class Evento(models.ModelPlus):
    SEARCH_FIELDS = ['codigo', 'nome', 'descricao']
    """
    o atributo tipo é utilizado para identificar como aquele evento deve ser interpretado
    exemplo:
        para uma descentralização de recursos entre a reitoria e um campus, a reitoria faria uma nc para o campus
        o evento utilizado neste caso representa um débito para o emitente
        já uma anulação para uma descentralização realizada consiste em um crédito para o emitente, já que ele está
        recuperando um determinado valor
    """
    tipo_choices = [
        [0, 'Bloqueio de Saldo'],  # nem crédito nem débito
        [1, 'Crédito Orçamentário'],  # crédito para o favorecido e débito para o emitente
        [2, 'Crédito Orçamentário - Anulação'],  # débito para o favorecido e crédito para o emitente
        [3, 'Crédito Orçamentário - Devolução'],  # crédito para o favorecido e débito para o emitente
        [4, 'Dotação'],  # crédito para o favorecido e débito para o emitente
        [5, 'Dotação - Cancelamento ou Redução'],  # débito para o favorecido e crédito para o emitente
        [6, 'Empenho'],  # gasto para o emitente
        [7, 'Empenho - Anulação'],  # redução do gasto para o emitente
        [8, 'Empenho - Cancelamento'],  # redução do gasto para o emitente
        [9, 'Empenho - Estorno'],  # gasto para o emitente já que um estorno pode ser de anulação ou cancelamento
        [10, 'Empenho - Reforço'],  # gasto para o emitente
        [11, 'Apropriação de Despesas'],  # gasto com despesas - utilizado para indicar gastos das notas de sistema
        [12, 'Apropriação de Despesas - Anulação'],  # anulação dos gasto com despesas
        [99, 'Outros'],
    ]  # não identificado

    codigo = models.CharField('Código', max_length=6, unique=True)
    nome = models.CharField('Nome', max_length=50)
    descricao = models.TextField('Descrição', null=True)
    tipo = models.IntegerField(choices=tipo_choices, null=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Evento'
        verbose_name_plural = 'Eventos'

    def __str__(self):
        return f'{self.codigo} - {self.nome}'

    def get_descricao_tipo(self):
        tipo = [item for item in self.tipo_choices if self.tipo in item]
        return f'{tipo[0][1]}' if tipo else f'{self.codigo} - Não identificado'

    @staticmethod
    def list_ncs_if():
        """considera os códigos de evento que correspondem a créditos e débitos onde o emissor (responsável) é o próprio IF"""
        return [1, 2]

    @staticmethod
    def list_creditos_ncs():
        """considera quais os códigos de evento são créditos para o favorecido - utilizado para notas de crédito"""
        return [2, 3]

    @staticmethod
    def list_debitos_ncs():
        """considera quais os códigos de evento são débitos para o favorecido - utilizado para notas de crédito"""
        return [1]

    @staticmethod
    def list_creditos():
        """considera quais os códigos de evento são créditos para o favorecido - utilizado para notas de crédito e dotação"""
        return [1, 3, 4]

    @staticmethod
    def list_debitos():
        """considera quais os códigos de evento são débitos para o favorecido - utilizado para notas de crédito e dotação"""
        return [2, 5]

    @staticmethod
    def list_empenhos():
        """considera quais os códigos de evento são gastos para o empenho em oposição a quais são redução dos gastos do empenho"""
        return [6, 9, 10]

    @staticmethod
    def list_aprop_despesas():
        """considera quais os códigos de evento são utilizados na apropriação de despesas"""
        return [11]

    @staticmethod
    def list_anulacao_aprop_despesas():
        """considera quais os códigos de evento são utilizados na anulação da apropriação de despesas"""
        return [12]

    def is_credito(self):
        if self.tipo in Evento.list_creditos():
            return True
        if self.tipo in Evento.list_debitos():
            return False
        return None

    def save(self, *args, **kwargs):
        """esses evento foram reconhecidos pelas notas importadas pelo siafi"""
        e0s = {'tipo': 0, 'lista': ['200022', '200053', '200090', '201011', '201016']}
        e1s = {'tipo': 1, 'lista': ['300063', '300300', '301019']}
        e2s = {'tipo': 2, 'lista': ['300083', '300302', '306019', '301023']}
        e3s = {'tipo': 3, 'lista': ['300084', '300301', '300307']}
        e4s = {
            'tipo': 4,
            'lista': [
                '201001',
                '201002',
                '201008',
                '201021',
                '201024',
                '201029',
                '201031',
                '201040',
                '201076',
                '201104',
                '206001',
                '206008',
                '206104',
            ],
        }
        e5s = {'tipo': 5, 'lista': ['201025', '201030', '201039', '201075']}
        e6s = {'tipo': 6, 'lista': ['401091']}
        e7s = {'tipo': 7, 'lista': ['401093']}
        e8s = {'tipo': 8, 'lista': ['401095']}
        e9s = {'tipo': 9, 'lista': ['406093', '406095']}
        e10s = {'tipo': 10, 'lista': ['401092']}
        e11s = {
            'tipo': 11,
            'lista': [
                '511001',
                '511034',
                '511089',
                '511282',
                '511283',
                '511287',
                '511292',
                '511348',
                '511457',
                '511457',
                '521214',
                '521244',
                '521291',
                '521293',
                '521308',
                '521327',
                '526214',
                '611001',
            ],
        }
        e12s = {'tipo': 12, 'lista': ['516001', '516267', '516287', '516288', '516292', '516457', '526293', '526327']}

        l_eventos = [e0s, e1s, e2s, e3s, e4s, e5s, e6s, e7s, e8s, e9s, e10s, e11s, e12s]
        for eventos in l_eventos:
            if self.codigo in eventos.get('lista'):
                self.tipo = eventos.get('tipo')

        super().save(*args, **kwargs)


class ProgramaTrabalho(models.ModelPlus):
    funcao = models.ForeignKeyPlus(Funcao, verbose_name='Função', on_delete=models.CASCADE)
    subfuncao = models.ForeignKeyPlus(Subfuncao, verbose_name='Subfunção', on_delete=models.CASCADE)
    acao = models.ForeignKeyPlus(Acao, verbose_name='Ação', on_delete=models.CASCADE)
    localizacao = models.ForeignKeyPlus(Localizacao, verbose_name='Localização', on_delete=models.CASCADE)
    municipio = models.ForeignKeyPlus('comum.Municipio', verbose_name='Município', null=True, blank=True, on_delete=models.CASCADE)
    codigo = models.CharField('Código Completo', max_length=17, unique=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Programa de Trabalho'
        verbose_name_plural = 'Programas de Trabalho'

    def clean(self):
        codigo = f'{self.funcao.codigo}{self.subfuncao.codigo}{self.acao.codigo}{self.localizacao.codigo}'
        qs = ProgramaTrabalho.objects.filter(codigo=codigo)
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        if qs.exists():
            raise ValidationError('Este Programa de Trabalho já existe.')

    def __str__(self):
        return self.codigo

    def save(self, *args, **kwargs):
        self.codigo = f'{self.funcao.codigo}{self.subfuncao.codigo}{self.acao.codigo}{self.localizacao.codigo}'
        super().save(*args, **kwargs)


class ProgramaTrabalhoResumido(models.ModelPlus):
    codigo = models.CharField('Código', max_length=6, unique=True)
    classificacao_institucional = models.ForeignKeyPlus(
        ClassificacaoInstitucional, verbose_name='Classificação Institucional', null=True, on_delete=models.CASCADE
    )
    programa_trabalho = models.ForeignKeyPlus(ProgramaTrabalho, verbose_name='Programa de Trabalho', null=True, on_delete=models.CASCADE)
    resultado_primario = models.ForeignKeyPlus(IdentificadorResultadoPrimario, verbose_name='Resultado Primário', null=True, on_delete=models.CASCADE)
    tipo_credito = models.CharField('Tipo de Crédito', max_length=1, null=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Programa de Trabalho Resumido'
        verbose_name_plural = 'Programas de Trabalho Resumido'

    def __str__(self):
        return self.codigo


class PlanoInterno(models.ModelPlus):
    codigo = models.CharField(max_length=11, unique=True)
    nome = models.CharField('Nome', max_length=100, null=True)
    objetivo = models.TextField(null=True)
    orgao = models.ForeignKeyPlus(ClassificacaoInstitucional, related_name='orgao', null=True, on_delete=models.CASCADE)
    unidade_orcamentaria = models.ForeignKeyPlus(ClassificacaoInstitucional, related_name='unidade_orcamentaria', null=True, on_delete=models.CASCADE)
    programa_trabalho = models.ForeignKeyPlus(ProgramaTrabalho, null=True, on_delete=models.CASCADE)
    unidade_gestora = models.ForeignKeyPlus(UnidadeGestora, null=True, on_delete=models.CASCADE)
    esfera_orcamentaria = models.ForeignKeyPlus(EsferaOrcamentaria, null=True, on_delete=models.CASCADE)
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Plano Interno'
        verbose_name_plural = 'Planos Internos'

    def __str__(self):
        return f'{self.codigo} - {self.nome}'


class NotaCredito(models.ModelPlus):
    numero = models.CharField('Número', max_length=12)
    numero_original = models.CharField('Número Original', max_length=20, null=True)
    datahora_emissao = models.DateTimeField('Data de Emissão')
    emitente_ug = models.ForeignKeyPlus(UnidadeGestora, related_name='nc_emitente_ug', verbose_name='UG Emitente', on_delete=models.CASCADE)
    emitente_ci = models.ForeignKeyPlus(
        ClassificacaoInstitucional, related_name='nc_emitente_ci', verbose_name='Gestão Emitente', on_delete=models.CASCADE
    )
    favorecido_ug = models.ForeignKeyPlus(UnidadeGestora, related_name='nc_favorecido_ug', verbose_name='UG Favorecida', on_delete=models.CASCADE)
    favorecido_ci = models.ForeignKeyPlus(
        ClassificacaoInstitucional, related_name='nc_favorecido_ci', verbose_name='Gestão Favorecida', on_delete=models.CASCADE
    )
    observacao = models.TextField(verbose_name='Observação')
    tx_cambial = models.DecimalField(verbose_name='Taxa Cambial', max_digits=10, decimal_places=4, null=True)
    sistema_origem = models.CharField('Sistema de Origem', max_length=10, null=True)
    registro_manual = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Nota de Crédito'
        verbose_name_plural = 'Notas de Crédito'

        unique_together = ['emitente_ug', 'numero']

    def __str__(self):
        return f'{self.numero}'

    def valor_credito(self):
        valor = 0
        for item in self.notacreditoitem_set.all():
            if item.evento.tipo in Evento.list_creditos():
                valor += item.valor
        return valor

    def valor_debito(self):
        valor = 0
        for item in self.notacreditoitem_set.all():
            if item.evento.tipo in Evento.list_debitos():
                valor += item.valor
        return valor

    def valor(self):
        return self.valor_credito() - self.valor_debito()


class NotaCreditoItem(models.ModelPlus):
    nota_credito = models.ForeignKeyPlus(NotaCredito, on_delete=models.CASCADE)
    evento = models.ForeignKeyPlus(Evento, on_delete=models.CASCADE)
    esfera = models.ForeignKeyPlus(EsferaOrcamentaria, on_delete=models.CASCADE)
    ptres = models.ForeignKeyPlus(ProgramaTrabalhoResumido, on_delete=models.CASCADE)
    fonte_recurso = models.ForeignKeyPlus(FonteRecurso, on_delete=models.CASCADE)
    fonte_recurso_original = models.CharField(max_length=10)
    natureza_despesa = models.ForeignKeyPlus(NaturezaDespesa, on_delete=models.CASCADE)
    subitem = models.CharField(max_length=2, null=True)
    ugr = models.ForeignKeyPlus(UnidadeGestora, null=True, on_delete=models.CASCADE)
    plano_interno = models.ForeignKeyPlus(PlanoInterno, null=True, on_delete=models.CASCADE)
    valor = models.DecimalFieldPlus()

    class Meta:
        verbose_name = 'Item da Nota de Crédito'
        verbose_name_plural = 'Itens da Nota de Crédito'

    def __str__(self):
        return f'Item da nota {self.nota_credito.numero}'


class NotaDotacao(models.ModelPlus):
    numero = models.CharField(max_length=12)
    datahora_emissao = models.DateTimeField()
    datahora_publicacao = models.DateTimeField(null=True)
    instrumento_legal = models.ForeignKeyPlus(InstrumentoLegal, on_delete=models.CASCADE)
    num_instrumento_legal = models.CharField(max_length=6, null=True)
    nota_dotacao = models.CharField(max_length=2, null=True)
    emitente_ug = models.ForeignKeyPlus(UnidadeGestora, related_name='nd_emitente_ug', on_delete=models.CASCADE)
    emitente_ci = models.ForeignKeyPlus(ClassificacaoInstitucional, related_name='nd_emitente_ci', on_delete=models.CASCADE)
    favorecido_ug = models.ForeignKeyPlus(UnidadeGestora, related_name='nd_favorecido_ug', null=True, on_delete=models.CASCADE)
    favorecido_ci = models.ForeignKeyPlus(ClassificacaoInstitucional, related_name='nd_favorecido_ci', null=True, on_delete=models.CASCADE)
    observacao = models.TextField(verbose_name='Observação')
    tx_cambial = models.DecimalField(max_digits=10, decimal_places=4, null=True)
    detalhamento_modalidade = models.CharField(max_length=1, null=True)
    detalhamento_especie = models.CharField(max_length=1, null=True)

    class Meta:
        verbose_name = 'Nota de Dotação'
        verbose_name_plural = 'Notas de Dotação'
        unique_together = ['emitente_ug', 'numero']

    def __str__(self):
        return self.numero

    def valor(self):
        # retorna qua o valor foi detalhado pela nota de dotação (o valor de crédito é o mesmo valor de débito)
        valor = 0
        for item in self.notadotacaoitem_set.all():
            if item.evento.tipo in Evento.list_creditos():
                valor += item.valor
        return valor


class NotaDotacaoItem(models.ModelPlus):
    nota_dotacao = models.ForeignKeyPlus(NotaDotacao, on_delete=models.CASCADE)
    evento = models.ForeignKeyPlus(Evento, on_delete=models.CASCADE)
    esfera = models.ForeignKeyPlus(EsferaOrcamentaria, on_delete=models.CASCADE)
    ptres = models.ForeignKeyPlus(ProgramaTrabalhoResumido, on_delete=models.CASCADE)
    fonte_recurso = models.ForeignKeyPlus(FonteRecurso, on_delete=models.CASCADE)
    fonte_recurso_original = models.CharField(max_length=10)
    natureza_despesa = models.ForeignKeyPlus(NaturezaDespesa, on_delete=models.CASCADE)
    subitem = models.CharField(max_length=2, null=True)
    ugr = models.ForeignKeyPlus(UnidadeGestora, null=True, on_delete=models.CASCADE)
    plano_interno = models.ForeignKeyPlus(PlanoInterno, null=True, on_delete=models.CASCADE)
    idoc = models.CharField(max_length=4, null=True)
    resultado = models.CharField(max_length=1, null=True)
    tipo_credito = models.CharField(max_length=1, null=True)
    valor = models.DecimalFieldPlus()

    class Meta:
        verbose_name = 'Item da Nota de Dotação'
        verbose_name_plural = 'Itens da Nota de Dotação'


class NotaEmpenho(models.ModelPlus):
    numero = models.CharField('Número', max_length=12)
    emitente_ug = models.ForeignKeyPlus('financeiro.UnidadeGestora', on_delete=models.CASCADE, related_name='ug', verbose_name='UG Emitente')

    data_emissao = models.DateFieldPlus(verbose_name='Data de Emissão')
    vinculo_operador = models.ForeignKeyPlus('comum.Vinculo', related_name='vinculo_operador_notaempenho')
    ug_operador = models.ForeignKeyPlus('financeiro.UnidadeGestora', related_name='operador_ug', on_delete=models.CASCADE)
    codigo_terminal = models.CharField(max_length=50, blank=True, verbose_name='Código do Terminal')
    data_transacao = models.DateTimeField(verbose_name='Data da Transação')

    vinculo_favorecido = models.ForeignKeyPlus('comum.Vinculo', related_name='vinculo_favorecido_notaempenho', null=True, blank=True)
    favorecido_original = models.CharField(max_length=14, blank=True)
    observacao = models.CharField('Observação', max_length=255, blank=True)
    evento = models.ForeignKeyPlus('financeiro.Evento', on_delete=models.CASCADE)
    esfera_orcamentaria = models.ForeignKeyPlus(
        'financeiro.EsferaOrcamentaria', on_delete=models.CASCADE, verbose_name='Esfera orçamentária', null=True, blank=True
    )
    ptres = models.ForeignKeyPlus(ProgramaTrabalhoResumido, on_delete=models.CASCADE, verbose_name='PTRES', null=True, blank=True)
    fonte_recurso = models.ForeignKeyPlus('financeiro.FonteRecurso', on_delete=models.CASCADE, verbose_name='Fonte de recurso', null=True, blank=True)
    fonte_recurso_original = models.CharField(max_length=10, blank=True, verbose_name='Fonte de recurso original')
    natureza_despesa = models.ForeignKeyPlus(
        'financeiro.NaturezaDespesa', on_delete=models.CASCADE, verbose_name='Natureza de Despesa', null=True, blank=True
    )
    ugr = models.ForeignKeyPlus(
        'financeiro.UnidadeGestora', on_delete=models.CASCADE, related_name='ug_responsavel', verbose_name='UG Responsável', null=True, blank=True
    )
    plano_interno = models.ForeignKeyPlus('financeiro.PlanoInterno', on_delete=models.CASCADE, null=True, blank=True)

    tipo = models.CharField(max_length=1, blank=True, choices=[['', 'Desconhecido'], ['1', 'Ordinário'], ['3', 'Estimativa'], ['5', 'Global']])
    modalidade_licitacao = models.ForeignKeyPlus(
        'financeiro.ModalidadeLicitacao', on_delete=models.CASCADE, verbose_name='Modalidade de Licitação', null=True, blank=True
    )
    amparo_legal = models.CharField(max_length=8, blank=True)
    inciso = models.CharField(max_length=2, blank=True)
    processo = models.CharField(max_length=20, blank=True)

    origem_material = models.CharField(
        max_length=1,
        blank=True,
        choices=[['', 'Desconhecido'], ['1', 'Nacional'], ['2', 'Estrangeiro adquirido no Brasil'], ['3', 'Importação direta']],
    )
    referencia_empenho = models.ForeignKeyPlus('self', null=True, blank=True, on_delete=models.CASCADE)
    referencia_empenho_original = models.CharField(max_length=12, blank=True)
    referencia_ug = models.ForeignKeyPlus(
        'financeiro.UnidadeGestora', on_delete=models.CASCADE, related_name='ug_referencia', verbose_name='UG Referência', null=True, blank=True
    )
    referencia_dispensa = models.CharField(max_length=20, blank=True)
    valor = models.DecimalField(max_digits=15, decimal_places=2)
    registro_manual = models.BooleanField(default=False)

    class Meta:
        unique_together = ('emitente_ug', 'numero')
        verbose_name = 'Nota de Empenho'
        verbose_name_plural = 'Notas de Empenho'

    def __str__(self):
        return f'NE {self.numero} (UG {self.emitente_ug.codigo})'

    def get_absolute_url(self):
        return f'/admin/financeiro/notaempenho/{self.pk}/view/'

    def get_fonte_recurso(self):
        """procura a fonte de recurso no empenho, caso o empenho não tenha fonte de recurso (em casos de anulação, por exemplo)
        procura no empenho de referência"""
        if self.fonte_recurso:
            return self.fonte_recurso
        else:
            if self.referencia_empenho:
                return self.referencia_empenho.get_fonte_recurso()
            else:
                return None

    def get_natureza_despesa(self):
        """procura a natureza de despesa no empenho, caso o empenho não tenha natureza de despesa (em casos de anulação, por exemplo)
        procura no empenho de referência"""
        if self.natureza_despesa:
            return self.natureza_despesa
        else:
            if self.referencia_empenho:
                return self.referencia_empenho.get_natureza_despesa()
            else:
                return None

    def is_empenho(self):
        """indica se o valor está sendo empenhado ou estornado/cancelado
        um valor empenhado indica um gasto para a ug, enquanto um estorno ou cancelamento indica uma redução do gasto"""
        ids_estornos_e_cancelamentos = [7, 8]
        return self.evento.tipo not in ids_estornos_e_cancelamentos

    def get_empenho_referencia_original(self):
        if self.referencia_empenho:
            return self.referencia_empenho.get_empenho_referencia_original()
        return self

    def get_valor(self):
        return self.valor if self.is_empenho() else Decimal(f'-{self.valor}')

    def get_valor_empenho_referencia_original(self):
        empenho = self.get_empenho_referencia_original()
        return empenho.get_valor_empenhado()

    def get_valor_empenhado(self):
        """verifica em todos empenhos ligados a este qual o valor empenhado"""
        try:
            valor = self.valor if self.is_empenho() else Decimal(f'-{self.valor}')

            # é o empenho original
            emps = NotaEmpenho.objects.filter(referencia_empenho=self)
            for emp in emps:
                valor += emp.get_valor_empenhado()

            return valor
        except Exception:
            return None

    def get_itens(self):
        return NEItem.objects.filter(lista_itens__nota_empenho=self)


class NEListaItens(models.ModelPlus):
    nota_empenho = models.ForeignKeyPlus('NotaEmpenho', null=True, on_delete=models.CASCADE)
    numero = models.CharField('Número', max_length=12)
    numero_original = models.CharField('Número Original', max_length=23, null=True, unique=True)

    class Meta:
        verbose_name = 'Lista de Itens do Empenho'
        verbose_name_plural = 'Listas de Itens dos Empenhos'


class NEItem(models.ModelPlus):
    lista_itens = models.ForeignKeyPlus(NEListaItens, on_delete=models.CASCADE)
    numero = models.SmallIntegerField('Número')
    # pode ser nulo, pois é possível importar arquivos de descrições antes dos arquivos de empenhos
    subitem = models.ForeignKeyPlus(SubElementoNaturezaDespesa, null=True, on_delete=models.CASCADE)
    subitem_original = models.CharField(max_length=2)
    descricao = models.TextField('Descrição')
    quantidade = models.DecimalField('Qtd.', max_digits=15, decimal_places=5)

    # pode ser calculado, mas é interessante salvar o valor que vem no registro do empenho
    valor_total = models.DecimalField(max_digits=17, decimal_places=2)
    valor_unitario = models.DecimalField('Valor unitário', max_digits=17, decimal_places=2)

    data_transacao = models.DateTimeField(verbose_name='Data de Transação')

    class Meta:
        ordering = ['numero']
        verbose_name = 'Item da Nota de Empenho'
        verbose_name_plural = 'Itens da Nota de Empenho'

        unique_together = ('lista_itens', 'numero')

    def __str__(self):
        return f'{self.subitem} - {self.descricao} - {self.quantidade}'

    def get_quantidade_inteira(self):
        return int(self.quantidade)


class NotaSistema(models.ModelPlus):
    numero = models.CharField(max_length=12)
    data_emissao = models.DateTimeField()
    data_valorizacao = models.DateTimeField(null=True)
    datahora_transacao = models.DateTimeField(null=True)
    ug = models.ForeignKeyPlus(UnidadeGestora, on_delete=models.CASCADE)
    gestao = models.ForeignKeyPlus(ClassificacaoInstitucional, on_delete=models.CASCADE)
    titulo_credito = models.CharField(max_length=12, null=True)
    data_venc_tit_credito = models.DateTimeField(null=True)
    vinculo_favorecido = models.ForeignKeyPlus('comum.Vinculo', related_name='vinculo_favorecido_notasistema', null=True, blank=True)
    favorecido_original = models.CharField(max_length=14, blank=True)
    observacao = models.TextField()
    sistema_origem = models.CharField(max_length=10, null=True, blank=True)

    class Meta:
        verbose_name = 'Nota de Sistema'
        verbose_name_plural = 'Notas de Sistema'

        unique_together = ['ug', 'numero']

    def __str__(self):
        return f'{self.numero}'


class NotaSistemaItem(models.ModelPlus):
    nota_sistema = models.ForeignKeyPlus(NotaSistema, on_delete=models.CASCADE)
    evento = models.ForeignKeyPlus(Evento, on_delete=models.CASCADE)
    inscricao_1 = models.CharField(max_length=14, null=True)
    inscricao_2 = models.CharField(max_length=14, null=True)

    classif_desp_1 = models.ForeignKeyPlus(ClassificacaoDespesa, related_name='classificacao_despesa_1', null=True, on_delete=models.CASCADE)
    despesa_1 = models.ForeignKeyPlus(SubElementoNaturezaDespesa, related_name='despesa_1', null=True, on_delete=models.CASCADE)

    classif_desp_2 = models.ForeignKeyPlus(ClassificacaoDespesa, related_name='classificacao_despesa_2', null=True, on_delete=models.CASCADE)
    despesa_2 = models.ForeignKeyPlus(SubElementoNaturezaDespesa, related_name='despesa_2', null=True, on_delete=models.CASCADE)

    valor = models.DecimalFieldPlus()

    class Meta:
        verbose_name = 'Item da Nota de Sistema'
        verbose_name_plural = 'Itens da Nota de Sistema'


class LogImportacaoSIAFI(models.ModelPlus):
    tipo_choices = [[1, 'Notas de crédito'], [2, 'Notas de dotação'], [3, 'Notas de empenho'], [4, 'Itens de empenho']]

    tipo = models.IntegerField(choices=tipo_choices)
    data_hora = models.DateTimeField()
    nome_arquivo = models.CharField(max_length=50)
    reg_analisados = models.IntegerField()
    nao_importados = models.IntegerField()
    detalhamento = models.TextField(blank=True)


class AcaoAno(models.ModelPlus):
    SEARCH_FIELDS = ['acao__codigo']

    ano_base = models.ForeignKeyPlus('comum.Ano', verbose_name='Ano Base', on_delete=models.CASCADE)
    acao = models.ForeignKeyPlus(Acao, verbose_name='Ação', on_delete=models.CASCADE)
    valor_capital = models.DecimalFieldPlus('Valor Capital')
    valor_custeio = models.DecimalFieldPlus('Valor Custeio')
    ptres = models.ForeignKeyPlus(ProgramaTrabalhoResumido, verbose_name='PTRES', related_name='acao_ano_ptres', null=True)

    class Meta:
        verbose_name = 'Ação do Ano'
        verbose_name_plural = 'Ações do Ano'
        unique_together = ('ano_base', 'acao', 'ptres')

    def __str__(self):
        return f'{self.acao} - {self.ptres}'

    @property
    def codigo_e_ptres(self):
        return f'{self.acao.codigo_acao}.{self.ptres}'


class CategoriaApropriacao(models.ModelPlus):
    SEARCH_FIELDS = ['codigo', 'descricao']

    codigo = models.CharField('Código', max_length=2, unique=True)
    descricao = models.CharField('Descrição', max_length=100, unique=True)

    class Meta:
        verbose_name = 'Categoria de Apropriação'
        verbose_name_plural = 'Categorias de Apropriação'

    def __str__(self):
        return f'{self.codigo} - {self.descricao}'
