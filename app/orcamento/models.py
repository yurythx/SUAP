# -------------------------------------------------------------------------------
# IFRN - Instituto Federal de Educação, Ciência e Tecnologia
# DGTI - Diretoria de Gestão da Tecnologia da Informação
# -------------------------------------------------------------------------------
# SUAP - Sistema único de Administração Pública
# -------------------------------------------------------------------------------
# Aplicativo: Orçamento
# Descrição.: Aplicativo para controle do orçamento do instituto.
# -------------------------------------------------------------------------------
# Observações:
#      Termos utilizados no módulo:
#         - MTO: Manual Técnico do Orçamento
# -------------------------------------------------------------------------------

# -------------------------------------------------------------------------------
from djtools.db import models

# -------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# class AnoBase(models.Model):
#    """
#    Representa o ano base do orçamento e também do planejamento
#    """
#    ano = models.SmallIntegerField(max_length=4, primary_key=True)
#
#    class Meta:
#        verbose_name = u'Ano Base'
#        verbose_name_plural = u'Anos Base'
#        ordering = ['-ano']
#
#    def __str__(self):
#        return u'%s' % (self.ano)
#
# class CategoriaEconomicaDespesa(models.Model):
#    """
#    Classe que mapeia a Categoria Econômica da Despesa, que serve para classifi-
#    car a despesa em categorias. Inicialmente existem somente 2 categorias, porém,
#    está sendo criada uma classe para esse mapeamento visando o aparecimento fu-
#    turo de outras categorias.
#
#    Atualemente, MTO 2010, existem duas categorias:
#        - 3 - Despesas Correntes
#        - 4 - Despesas de Capital
#
#    Para maiores detalhes consultar MTO 2010, página 48.
#    ----------------------------------------------------------------------------
#    """
#    codigo = models.CharField(u"Código", max_length=1, primary_key=True)
#    descricao = models.CharField(u"Descrição", max_length=100)
#    especificacao = models.TextField(u"Especificação")
#
#    class Meta:
#        verbose_name = u'Categoria Econômica da Despesa'
#        verbose_name_plural = u'Categorias Econômicas da Despesa'
#        ordering = ['codigo']
#
#    def __str__(self):
#        return u'%s - %s' % (self.codigo, self.descricao)
#
# class GrupoNaturezaDespesa(models.Model):
#    """
#    Classe que mapeia um Grupo de Natureza de Despesa, que é um agregador de
#    elementos de despesa com as mesmas característica quanto ao objeto de gasto.
#
#    Atualmenete, MTO 2010, existem os seguintes grupos:
#        - 1 - Pessoal e Encargos Sociais
#        - 2 - Juros e Encargos da Dívida
#        - 3 - Outras Despesas Correntes
#        - 4 - Investimentos
#        - 5 - Inversões financeiras
#        - 6 - Amortização da Dívida
#        - 9 - Reserva de Contingência
#
#    Para maiores detalhes consultar MTO 2010, página 49.
#    ----------------------------------------------------------------------------
#    """
#    codigo = models.CharField(u"Código", max_length=1, primary_key=True)
#    descricao = models.CharField("Descrição", max_length=100)
#    especificacao = models.TextField(u"Especificação")
#
#    class Meta:
#        verbose_name = u'Grupo de Natureza de Despesa'
#        verbose_name_plural = u'Grupos de Naturezas de Despesa'
#        ordering = ['codigo']
#
#    def __str__(self):
#        return u'%s - %s' % (self.codigo, self.descricao)
#
# class ModalidadeAplicacao(models.Model):
#    """
#    Classe que modela a Modalidade da Aplicação que se destina a indicar se os
#    recursos serão aplicados mediante transferência financeira, inclusive a de-
#    corrente de descentralização orçamentária para outras esferas do governo.
#
#    A modalidade de aplicação objetiva, principalmente, eliminar a dupla contagem
#    dos recursos transferidos ou descentralizados.
#
#    Atualmente, MTO 2010, existem as segiontes modalidades:
#        -  0 - Transferências à União
#        - 30 - Transferências a Estados e ao Distrito Federal
#        - 40 - Transferências a Municípios
#        - 50 - Transferências a Instituições Privadas sem Fins Lucrativos
#        - 60 - Transferências a Instituições Privadas com Fins Lucrativos
#        - 70 - Transferências a Instituições Multigovernamentais
#        - 71 - Transferências a Consórcios Públicos
#        - 80 - Transferências ao Exterior
#        - 90 - Aplicações Diretas
#        - 91 - Aplicação Direta Decorrente de Operação entre Órgãos, Fundos e
#               Entidades Integrantes dos Orçamentos Fiscal e da Seguridade Social
#        - 99 - A Definir
#    ----------------------------------------------------------------------------
#    """
#    codigo = models.CharField(u"Código", max_length=2, primary_key=True)
#    descricao = models.CharField(u"Descrição", max_length=150)
#    especificacao = models.TextField(u"Especificação")
#
#    class Meta:
#        verbose_name = u'Modalidade da Aplicação'
#        verbose_name_plural = u'Modalidades da Aplicação'
#        ordering = ['codigo']
#
#    def __str__(self):
#        return u'%s - %s' % (self.codigo, self.descricao)
#
# class ElementoDespesa(models.Model):
#    """
#    Classe que modela um Elemento de Despesa que tem finalidade identificar os
#    objetos de gasto, tais como vencimentos e vantagens fixas, juros, diárias,
#    meteriais de consumo, serviços de terceiro prestados sob qualquer forma,
#    subvenções sociais, obras e instalações, equipamentos e material permanente,
#    auxílios, amortização e outros que a administração pública utiliza para a
#    consecução de seus fins.
#
#    A tabela com os elementos de despesas como outras informações são encotradas
#    em MTO 2010, página 52.
#    ----------------------------------------------------------------------------
#    """
#    codigo = models.CharField(u"Código", max_length=2, primary_key=True)
#    descricao = models.CharField(u"Descrição", max_length=100)
#    especificacao = models.TextField(u"Especificação")
#
#    class Meta:
#        verbose_name = u'Elemento de Despesa'
#        verbose_name_plural = u'Elementos de Despesa'
#        ordering = ['codigo']
#
#    def __str__(self):
#        return u'%s - %s' % (self.codigo, self.descricao)
#
# class NaturezaDespesa(models.Model):
#    """
#    Classe que mapeia a Natureza Despesa, que é, o conjunto de informações que
#    formam o código é conhecido como classificação por natureza de despesa e in-
#    forma a categoria econômica, o grupo a que pertence, a modalidade de aplica-
#    ção e o elemento.
#
#    Na base do Sistema de Orçamento o campo que se refere à natureza de despesa
#    contém um código composto por seis algarismos:
#       - Categoria Econômica da Despesa
#       - Grupo de Natureza de Despesa
#       - Modalidade de Aplicação
#       - Elemento de Despesa
#
#    Para maiores detalhes consultar MTO 2010, página 48.
#    ----------------------------------------------------------------------------
#    """
#    categoria_economica_despesa = models.ForeignKeyPlus(CategoriaEconomicaDespesa, verbose_name=u"Categoria Econômica", on_delete=models.CASCADE)
#    grupo_natureza_despesa = models.ForeignKeyPlus(GrupoNaturezaDespesa, verbose_name=u"Grupo Natureza Despesa", on_delete=models.CASCADE)
#    modalidade_aplicacao = models.ForeignKeyPlus(ModalidadeAplicacao, verbose_name=u"Modalidade da Aplicação", on_delete=models.CASCADE)
#    elemento_despesa = models.ForeignKeyPlus(ElementoDespesa, verbose_name=u"Elemento da Despesa", on_delete=models.CASCADE)
#    descricao = models.CharField("Fonte do recurso", max_length=100)
#    codigo_resumo = models.CharField("Código", max_length=6)
#    participa_planejamento = models.BooleanField(u"Planejamento", help_text=u"Indica se a natureza de despesa é participante do planejamento.", default=False)
#
#    class Meta:
#        unique_together = ('categoria_economica_despesa', 'grupo_natureza_despesa','modalidade_aplicacao','elemento_despesa')
#        verbose_name = u'Natureza de Despesa'
#        verbose_name_plural = u'Naturezas de Despesas'
#
#    def codigo(self):
#        return u'%s%s%s%s' % (self.categoria_economica_despesa.codigo, self.grupo_natureza_despesa.codigo, self.modalidade_aplicacao.codigo, self.elemento_despesa.codigo)
#
#    def __str__(self):
#        return u'%s - %s' %(self.codigo_resumo, self.descricao)
#
# class GrupoFonteRecurso(models.Model):
#    codigo = models.CharField(u"Código", max_length=1, primary_key=True)
#    grupo = models.CharField(u"Grupo", max_length=50)
#
#    class Meta:
#        verbose_name = u'Grupo de Fonte de Recurso'
#        verbose_name_plural = u'Grupos de Fontes de Recursos'
#        ordering = ['codigo']
#
#    def __str__(self):
#        return u'%s - %s' %(self.codigo, self.grupo)
#
# class EspecificacaoFonteRecurso(models.Model):
#    codigo = models.CharField(u"Código", max_length=2, primary_key=True)
#    especificacao = models.CharField(u"Especificação", max_length=100)
#
#    class Meta:
#        verbose_name = u'Especificação da Fonte de Recurso'
#        verbose_name_plural = u'Especificações das Fontes de Recursos'
#        ordering = ['codigo']
#
#    def __str__(self):
#        return u'%s - %s' %(self.codigo, self.especificacao)
#
# class FonteRecurso(models.Model):
#    descricao = models.CharField("Fonte do recurso", max_length=100, unique=True)
#    grupo = models.ForeignKeyPlus(GrupoFonteRecurso, verbose_name=u"Grupo", on_delete=models.CASCADE)
#    especificacao = models.ForeignKeyPlus(EspecificacaoFonteRecurso, verbose_name=u"Especificação", on_delete=models.CASCADE)
#
#    class Meta:
#        verbose_name = u'Fonte de Recurso'
#        verbose_name_plural = u'Fontes de Recursos'
#        unique_together = ('grupo','especificacao')
#
#    def __str__(self):
#        return u'%s%s - %s' %(self.grupo.codigo, self.especificacao.codigo, self.descricao)
#
#    def codigo(self):
#        return u'%s%s' %(self.grupo.codigo, self.especificacao.codigo)
#
# ------------------------------------------------------------------------------
# class Programa(models.Model):
#    """
#    Classe que mapeia o programa do orçamento, que é, o instrumento de organiza-
#    ção a atuação gorvenamental que articula um conjunto e ações que concorrem
#    para a concretização de um objetivo comum preestabelecido, mensurado por
#    indicadores instituídos no plano, visando à solução e um problema ou o aten-
#    dimento de determinada necessidade ou demanda da sociedade. (MTO 2010, pág
#    39)
#
#    O programa é também o módulo integrador entre o plano e o orçamento.
#
#    Para maiores detalhes consultar MTO 2010, página 38.
#    ----------------------------------------------------------------------------
#     """
#    ano_base = models.ForeignKeyPlus(AnoBase, verbose_name=u'Ano Base', on_delete=models.CASCADE)
#    codigo = models.CharField(u"Código", max_length=4)
#    nome = models.CharField(u"Nome", max_length=100)
#
#    class Meta:
#        verbose_name = u'Programa'
#        verbose_name_plural = u'Programas'
#        unique_together = ('ano_base','codigo')
#
#    def __str__(self):
#        return u'%s - %s' %(self.codigo, self.nome)
#
#    def get_valor_total_epf(self):
#        valor_total = Decimal('0.0')
#        for acao in self.acao_set.all():
#            valor_total += acao.get_valor_total_epf()
#        return valor_total
#
# -------------------------------------------------------------------------------
# class UnidadeMedida(models.Model):
#    """
#    Unidade de medida utilizada nas metas do orçamento e planejamento
#    """
#    descricao = models.CharField(u'Descrição', max_length=30, unique=True)
#
#    class Meta:
#        verbose_name = u'Unidade de Medida'
#        verbose_name_plural = u'Unidades de Medida'
#        ordering = ['descricao']
#
#    def __str__(self):
#        return self.descricao
#
# ------------------------------------------------------------------------------
# class Acao(models.Model):
#    programa = models.ForeignKeyPlus(Programa, on_delete=models.CASCADE)
#    codigo = models.CharField(u"Código", max_length=4, primary_key=True)
#    nome = models.CharField(u"Nome", max_length=200, unique=True)
#    unidade_medida = models.ForeignKeyPlus(UnidadeMedida, verbose_name=u'Unidade de Medida', null=True, on_delete=models.CASCADE)
#    quantidade = models.IntegerField(null=True)
#    participa_planejamento = models.BooleanField(u"Planejamento", help_text=u"Indica se o programa é participante do planejamento.", default=False)
#
#    class Meta:
#        verbose_name = u'Ação'
#        verbose_name_plural = u'Ações'
#
#    def __str__(self):
#        return u'%s - %s' %(self.codigo, self.nome)
#
#    def codigo_completo(self):
#        return u'%s.%s' %(self.programa.codigo, self.codigo)
#    codigo_completo.allow_tags = True
#    codigo_completo.short_description = 'Código Completo'
#
#    def get_valor_total_epf(self):
#        valor_total = Decimal('0.0')
#        for epf in self.estruturaprogramaticafinanceira_set.all():
#            valor_total += epf.valor
#        return valor_total
#
#    def get_valor_total_planejamento(self):
#        valor_total = Decimal('0.0')
#        for pla in self.acao_set.all():
#            valor_total += pla.valor
#        return valor_total


class UnidadeMedida(models.ModelPlus):
    nome = models.CharField('Nome', max_length=50, unique=True)

    class Meta:
        verbose_name = 'Unidade de Medida'
        verbose_name_plural = 'Unidades de Medida'

        ordering = ['nome']

    def __str__(self):
        return self.nome


# ------------------------------------------------------------------------------
class EstruturaProgramaticaFinanceira(models.ModelPlus):
    ano_base = models.ForeignKeyPlus('comum.Ano', verbose_name='Ano Base', on_delete=models.CASCADE)
    programa_trabalho = models.ForeignKeyPlus('financeiro.ProgramaTrabalho', verbose_name='Programa de Trabalho', on_delete=models.CASCADE)
    unidade_medida = models.ForeignKeyPlus('orcamento.UnidadeMedida', verbose_name='Unidade de Medida', null=True, on_delete=models.CASCADE)
    quantidade = models.IntegerField(null=True)

    class Meta:
        verbose_name = 'Estrutura Programática Financeira'
        verbose_name_plural = 'Estruturas Programáticas Financeira'

        unique_together = ('ano_base', 'programa_trabalho')

    def __str__(self):
        return f'{self.ano_base.ano}-{self.programa_trabalho.acao}'

    def get_saldo(self):
        saldo = self.valor
        for _co in self.creditoorcamentario_set.all():
            # a linha a seguir apresenta um erro
            # saldo -= epf_unidade.valor
            pass
        return saldo


class Credito(models.ModelPlus):
    """representação de um registro de crédito orçamentário realizado identificado no qdd"""

    epf = models.ForeignKeyPlus(EstruturaProgramaticaFinanceira, on_delete=models.CASCADE)
    natureza_despesa = models.ForeignKeyPlus('financeiro.NaturezaDespesa', on_delete=models.CASCADE)
    fonte_recurso = models.ForeignKeyPlus('financeiro.FonteRecurso', on_delete=models.CASCADE)
    valor = models.DecimalFieldPlus()

    class Meta:
        verbose_name = 'Crédito Orçamentário'
        verbose_name_plural = 'Créditos Orçamentários'

        unique_together = ('epf', 'natureza_despesa', 'fonte_recurso')
