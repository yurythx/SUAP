from django.core.exceptions import ValidationError

from djtools.db import models
from rh.models import UnidadeOrganizacional


class TipoComissaoChoices:
    CENTRAL = 'central'
    TEMATICA = 'tematica'
    LOCAL = 'local'

    CHOICES = ((CENTRAL, 'Central'), (TEMATICA, 'Temática'), (LOCAL, 'Local'))


class PDI(models.ModelPlus):
    ano = models.SmallIntegerField(unique=True)
    descricao = models.CharField('Descrição', max_length=100, null=True)
    periodo_inicial = models.DateField('Data Inicial do PDI')
    periodo_final = models.DateField('Data Final do PDI')
    periodo_sugestao_inicial = models.DateField('Data Inicial de Contribuições')
    periodo_sugestao_final = models.DateField('Data Final de Contribuições')
    periodo_sugestao_melhoria_inicial = models.DateField('Data Inicial de Proposta de Melhoria', default='2014-05-09')
    periodo_sugestao_melhoria_final = models.DateField('Data Final de Proposta de Melhoria', default='2014-05-09')
    data_final_local = models.DateField('Data Final da Comissão Local')
    data_final_tematica = models.DateField('Data Final da Comissão Temática')
    qtd_caracteres_contribuicao = models.IntegerField('Quantidade de Caracteres para Contribuição da Comunidade')
    qtd_caracteres_comissao_local = models.IntegerField('Quantidade de Caracteres para Redação Local')

    class Meta:
        verbose_name = 'PDI'
        verbose_name_plural = 'PDIs'

    def __str__(self):
        return f'{self.ano}'

    def clean(self):
        errors = {}
        if self.periodo_final <= self.periodo_inicial:
            errors['periodo_final'] = ['A data final não pode ser menor ou igual à data inicial do PDI.']

        if not self.periodo_inicial <= self.periodo_sugestao_inicial <= self.periodo_final:
            errors['periodo_sugestao_inicial'] = ['A data inicial de contribuições deve estar entre o período do PDI.']

        if not self.periodo_inicial <= self.periodo_sugestao_final <= self.periodo_final:
            errors['periodo_sugestao_final'] = ['A data final de contribuições deve estar entre o período do PDI.']

        if not self.periodo_inicial <= self.periodo_sugestao_melhoria_inicial <= self.periodo_final:
            errors['periodo_sugestao_melhoria_inicial'] = ['A data inicial de  melhoria das contribuições deve estar entre o período do PDI.']

        if not self.periodo_inicial <= self.periodo_sugestao_melhoria_final <= self.periodo_final:
            errors['periodo_sugestao_melhoria_final'] = ['A data final de  melhoria das contribuições deve estar entre o período do PDI.']

        if self.periodo_sugestao_final <= self.periodo_sugestao_inicial:
            erro = 'A data final de contribuições do PDI não pode ser menor ou igual à data inicial de contribuições do PDI.'
            if 'periodo_sugestao_final' in errors:
                errors['periodo_sugestao_final'].append(erro)
            else:
                errors['periodo_sugestao_final'] = [erro]

        if self.periodo_sugestao_melhoria_final <= self.periodo_sugestao_melhoria_inicial:
            erro = 'A data final de melhoria das contribuições do PDI não pode ser menor ou igual à data inicial de melhoria contribuições do PDI.'
            if 'periodo_sugestao_melhoria_final' in errors:
                errors['periodo_sugestao_melhoria_final'].append(erro)
            else:
                errors['periodo_sugestao_melhoria_final'] = [erro]

        if not self.periodo_inicial <= self.data_final_local <= self.periodo_final:
            errors['data_final_local'] = ['A data final da comissão local deve estar entre o período do PDI.']

        if not self.periodo_inicial <= self.data_final_tematica <= self.periodo_final:
            errors['data_final_tematica'] = ['A data final da comissão temática deve estar entre o período do PDI.']

        if self.data_final_tematica < self.data_final_local:
            erro = 'A data final da comissão temática não pode ser menor do que a data final da comissão local.'
            if 'data_final_tematica' in errors:
                errors['data_final_tematica'].append(erro)
            else:
                errors['data_final_tematica'] = [erro]

        if errors:
            raise ValidationError(errors)

    @staticmethod
    def get_atual():
        return PDI.objects.order_by('-ano').first()


class SecaoPDI(models.ModelPlus):
    pdi = models.ForeignKeyPlus(PDI, verbose_name='PDI', on_delete=models.CASCADE)
    nome = models.CharField('Nome', max_length=100)
    descricao = models.TextField('Descrição')

    class Meta:
        verbose_name = 'Eixos do PDI'
        verbose_name_plural = 'Eixos do PDI'

        ordering = ['nome']

    def __str__(self):
        return f'{self.nome}'


class ComissaoPDI(models.ModelPlus):
    pdi = models.ForeignKeyPlus(PDI, verbose_name='PDI', on_delete=models.CASCADE)
    secoes = models.ManyToManyField(SecaoPDI, verbose_name='Seção do PDI')
    nome = models.CharField('Nome', max_length=100)
    tipo = models.CharField('Tipo de Comissão', max_length=10, choices=TipoComissaoChoices.CHOICES)
    vinculos_avaliadores = models.ManyToManyField('comum.Vinculo')

    class Meta:
        verbose_name = 'Comissão do PDI'
        verbose_name_plural = 'Comissões do PDI'

        ordering = ['tipo', 'nome']

    def __str__(self):
        return f'{self.nome} {self.get_tipo_display()}'


class SecaoPDICampus(models.ModelPlus):
    secao_pdi = models.ForeignKeyPlus(SecaoPDI, verbose_name='Seção do PDI', on_delete=models.CASCADE)
    campus = models.ForeignKeyPlus(UnidadeOrganizacional, verbose_name='Campus', null=False, on_delete=models.CASCADE)
    texto = models.TextField('Redação Proposta')
    anexo = models.FileFieldPlus(upload_to='pdi/anexos/', max_length=255, blank=True)

    class Meta:
        verbose_name = 'Produção das Comissões Locais'
        verbose_name_plural = 'Produções das Comissões Locais'
        unique_together = ('secao_pdi', 'campus')

    def __str__(self):
        return f'{self.secao_pdi} {self.campus}'


class SecaoPDIInstitucional(models.ModelPlus):
    secao_pdi = models.OneToOneField(SecaoPDI, verbose_name='Seção do PDI', on_delete=models.CASCADE)
    anexo = models.FileFieldPlus(upload_to='pdi/anexos/', max_length=255, blank=True)

    class Meta:
        verbose_name = 'Produção das Comissões Temáticas'
        verbose_name_plural = 'Produções das Comissões Temáticas'

    def __str__(self):
        return f'{self.secao_pdi}'

    def get_absolute_url(self):
        return f'/pdi/exibir_redacao_tematica/{self.id}/'


class SugestaoComunidade(models.ModelPlus):
    secao_pdi = models.ForeignKeyPlus(SecaoPDI, verbose_name='Eixo do PDI', on_delete=models.CASCADE)
    campus = models.ForeignKeyPlus(UnidadeOrganizacional, verbose_name='Campus', null=False, on_delete=models.CASCADE)
    cadastrada_por = models.CurrentUserField()
    texto = models.TextField('Contribuição')
    analisada = models.BooleanField(default=False)
    anonima = models.BooleanField(
        'Publicar anonimamente?',
        default=False,
        help_text='Como anônimo, o seu nome não será exibido na lista de Contribuições da Comunidade e não permitirá edição.',
    )

    class Meta:
        verbose_name = 'Contribuição da Comunidade'
        verbose_name_plural = 'Contribuições da Comunidade'

    def __str__(self):
        return f'{self.cadastrada_por} {self.campus}'

    def save(self, *args, **kwargs):
        delete_avaliacoes = kwargs.pop('delete_avaliacoes', False)
        super().save(*args, **kwargs)
        if delete_avaliacoes:
            self.sugestaocomunidadeusuario_set.all().delete()

    def concordam(self):
        return self.sugestaocomunidadeusuario_set.filter(concorda=True)

    def discordam(self):
        return self.sugestaocomunidadeusuario_set.filter(concorda=False)

    def concordou(self, user):
        return self.sugestaocomunidadeusuario_set.filter(cadastrada_por=user, concorda=True).exists()

    def discordou(self, user):
        return self.sugestaocomunidadeusuario_set.filter(cadastrada_por=user, concorda=False).exists()


class SugestaoComunidadeUsuario(models.ModelPlus):
    sugestao = models.ForeignKeyPlus(SugestaoComunidade, verbose_name='Contribuição da Comunidade', on_delete=models.CASCADE)
    cadastrada_por = models.CurrentUserField()
    concorda = models.BooleanField(null=True)


class SugestaoConsolidacao(models.ModelPlus):
    secao_pdi = models.ForeignKeyPlus(SecaoPDI, verbose_name='Eixo do PDI', on_delete=models.CASCADE)
    campus = models.ForeignKeyPlus(UnidadeOrganizacional, verbose_name='Campus', null=False, on_delete=models.CASCADE)
    cadastrada_por = models.CurrentUserField()
    texto = models.TextField('Contribuição')
    analisada = models.BooleanField(default=False)
    anonima = models.BooleanField(
        'Publicar anonimamente?',
        default=False,
        help_text='Como anônimo, o seu nome não será exibido na lista de Contribuições da Comunidade e não permitirá edição.',
    )

    class Meta:
        verbose_name = 'Contribuição da Comunidade para a Consolidação'
        verbose_name_plural = 'Contribuições da Comunidade para a Consolidação'

    def __str__(self):
        return f'{self.cadastrada_por} {self.campus}'

    def save(self, *args, **kwargs):
        delete_avaliacoes = kwargs.pop('delete_avaliacoes', False)
        super().save(*args, **kwargs)
        if delete_avaliacoes:
            self.sugestaoconsolidacaousuario_set.all().delete()

    def concordam(self):
        return self.sugestaoconsolidacaousuario_set.filter(concorda=True)

    def discordam(self):
        return self.sugestaoconsolidacaousuario_set.filter(concorda=False)

    def concordou(self, user):
        return self.sugestaoconsolidacaousuario_set.filter(cadastrada_por=user, concorda=True).exists()

    def discordou(self, user):
        return self.sugestaoconsolidacaousuario_set.filter(cadastrada_por=user, concorda=False).exists()


class SugestaoConsolidacaoUsuario(models.ModelPlus):
    sugestao = models.ForeignKeyPlus(SugestaoConsolidacao, verbose_name='Contribuição da Comunidade Consolidação', on_delete=models.CASCADE)
    cadastrada_por = models.CurrentUserField()
    concorda = models.BooleanField(null=True)
