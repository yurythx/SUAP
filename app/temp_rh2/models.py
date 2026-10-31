import datetime

from django.contrib.auth.models import Group

from comum.models import Configuracao
from djtools.db import models
from djtools.db.models import ModelPlus
from djtools.templatetags.filters.utils import in_group
from djtools.utils import get_age


class Categoria(ModelPlus):
    nome = models.CharField(max_length=20, blank=False, null=False, verbose_name='Nome')
    idade_inferior = models.PositiveIntegerField('Limite de idade inferior')
    idade_superior = models.PositiveIntegerField('Limite de idade superior')
    excluido = models.BooleanField(default=False)

    def __str__(self):
        return f'Categoria {self.nome} de {self.idade_inferior} à {self.idade_superior} anos'

    class Meta:
        verbose_name = 'Categoria'
        verbose_name_plural = 'Categorias'


class ModalidadeDesportiva(ModelPlus):
    MASCULINO = 1
    FEMININO = 2
    MISTO = 3
    NAO_APLICA = 4
    choices_sexo = ((MASCULINO, 'Masculino'), (FEMININO, 'Feminino'), (MISTO, 'Misto'), (NAO_APLICA, 'Não se aplica'))

    COLETIVO = 1
    INDIVIDUAL = 2
    choices_tipo_modalidade = ((COLETIVO, 'Coletivo'), (INDIVIDUAL, 'Individual'))
    nome = models.CharField(max_length=20, blank=False, null=False, verbose_name='Nome')
    sexo = models.PositiveIntegerField('Sexo', default=1, choices=choices_sexo, help_text='Quando o esporte for individual escolher "Não se aplica"')
    tipo = models.PositiveIntegerField('Tipo', default=1, choices=choices_tipo_modalidade)
    exige_atestado = models.BooleanField('Modalidade exige atestado médico?', default=True)

    def __str__(self):
        if self.sexo == self.NAO_APLICA:
            return f'{self.nome} - {self.get_tipo_display()}'
        return f'{self.nome} - {self.get_sexo_display()} - {self.get_tipo_display()}'

    class Meta:
        verbose_name = 'Modalidade Desportiva'
        verbose_name_plural = 'Modalidades Desportivas'
        permissions = ()


class Prova(ModelPlus):
    SEARCH_FIELDS = ('nome', 'modalidade__nome')

    nome = models.CharField(max_length=20, blank=False, null=False, verbose_name='Nome')
    ativa = models.BooleanField('Ativa?', default=True)
    modalidade = models.ForeignKeyPlus(ModalidadeDesportiva, verbose_name='Modalidade')

    def __str__(self):
        return f'{self.nome} - {self.modalidade}'

    class Meta:
        verbose_name = 'Prova'
        verbose_name_plural = 'Provas'


class CompeticaoDesportiva(ModelPlus):
    nome = models.CharField(max_length=20, blank=False, null=False, verbose_name='Nome')
    descricao = models.TextField(blank=False, null=False, verbose_name='Descrição')
    ano = models.ForeignKeyPlus('comum.Ano', null=False, blank=False, on_delete=models.CASCADE)

    uo = models.ForeignKeyPlus(
        'rh.unidadeorganizacional',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        verbose_name='Unidade Organizacional',
        help_text='Define escopo da competição',
    )

    modalidades = models.ManyToManyField(ModalidadeDesportiva, verbose_name='Modalidades desportivas')
    categorias = models.ManyToManyField(Categoria, verbose_name='Categorias')

    max_modalidades_coletivas_por_inscricao = models.PositiveIntegerField('Quantidade Máxima de modalidades coletivas', default=2)
    max_modalidades_individuais_por_inscricao = models.PositiveIntegerField('Quantidade Máxima modalidades individuais', default=2)

    max_modalidades_por_inscricao = models.PositiveIntegerField('Quantidade Máxima modalidades Independente se individual ou coletiva', default=4)

    provas = models.ManyToManyField(Prova, verbose_name='Provas', related_name='provas_competicao', blank=True)

    data_inicio_periodo_inscricoes = models.DateFieldPlus('Data inicial do período de inscrições', null=False)
    data_fim_periodo_inscricoes = models.DateFieldPlus('Data final do período de inscrições', null=False)

    data_inicio_periodo_validacao = models.DateFieldPlus('Data inicial do período de validação', null=False)
    data_fim_periodo_validacao = models.DateFieldPlus('Data final do período de validação', null=False)

    data_inicio_confirmacao_inscritos = models.DateFieldPlus('Data inicial do período de confirmação dos inscritos', null=False)
    data_fim_confirmacao_inscritos = models.DateFieldPlus('Data final do período de confirmação dos inscritos', null=False)

    data_inicio_reajustes = models.DateFieldPlus('Data inicial do período de reajustes (pelo representante do campus)', null=False)
    data_fim_reajustes = models.DateFieldPlus('Data final do período de reajustes (pelo representante do campus)', null=False)

    data_homologacao_inscricoes = models.DateFieldPlus('Data de homologação e consolidação das inscrições', null=False)

    data_inicio_periodo1_jogos = models.DateFieldPlus('Data inicial do período 1 de jogos', null=False)
    data_fim_periodo1_jogos = models.DateFieldPlus('Data final do período 1 de jogos', null=False)

    data_inicio_periodo2_jogos = models.DateFieldPlus('Data inicial do período 2 de jogos', null=True, blank=True)
    data_fim_periodo2_jogos = models.DateFieldPlus('Data final do período 2 de jogos', null=True, blank=True)

    pode_escolher_tamanho_uniforme = models.BooleanField('Pode escolher tamanho dos uniformes?', default=True)

    class Meta:
        unique_together = ('nome', 'ano')
        verbose_name = 'Competição Desportiva'
        verbose_name_plural = 'Competições Desportivas'

        ordering = ('ano', 'nome')

    def __str__(self):
        return f' {self.nome} {self.ano.ano}'


class MaximoProvasModalidade(ModelPlus):
    MAX_PROVAS_DEFAULT = 3

    competicao_desportiva = models.ForeignKeyPlus(CompeticaoDesportiva, verbose_name='Competição desportiva')
    modalidade = models.ForeignKeyPlus(ModalidadeDesportiva, verbose_name='Modalidade')
    maximo_provas = models.PositiveIntegerField('Máximo de provas', default=MAX_PROVAS_DEFAULT)

    class Meta:
        verbose_name = 'Máximo de provas por modalidade'
        verbose_name_plural = 'Máximos de provas por modalidade'
        unique_together = ('competicao_desportiva', 'modalidade')

    def __str__(self):
        return f'{self.maximo_provas} provas de {self.modalidade} - {self.competicao_desportiva}'


class InscricaoCompeticaoDesportiva(ModelPlus):
    PP = 1
    P = 2
    M = 3
    G = 4
    GG = 5
    XG = 6
    choices_tamanhos = ((PP, 'PP'), (P, 'P'), (M, 'M'), (G, 'G'), (GG, 'GG'), (XG, 'XG'))

    choices_situacoes = ((1, 'Inscrição em Análise'), (2, 'Validada'), (3, 'Homologada'), (4, 'Rejeitada'))

    competicao_desportiva = models.ForeignKeyPlus(
        'temp_rh2.CompeticaoDesportiva', verbose_name='Competição', null=False, on_delete=models.CASCADE, blank=False
    )
    servidor = models.ForeignKeyPlus('rh.Servidor', null=False, blank=False, on_delete=models.CASCADE)
    uo = models.ForeignKeyPlus('rh.UnidadeOrganizacional', null=False, blank=False, verbose_name='Campus Inscrito', on_delete=models.CASCADE)
    categoria = models.ForeignKeyPlus('temp_rh2.Categoria', verbose_name='Categoria', null=True, blank=False)

    modalidades = models.ManyToManyField(ModalidadeDesportiva, verbose_name='Modalidades')
    provas = models.ManyToManyField(Prova, verbose_name='Provas', related_name='provas_inscricao', blank=True)

    preferencia_camisa = models.PositiveIntegerField(
        'Tamanho da camisa', default=3, null=True, choices=choices_tamanhos, help_text='Tamanho da camisa/uniforme'
    )
    preferencia_short = models.PositiveIntegerField(
        'Tamanho do short', default=3, null=True, choices=choices_tamanhos, help_text='Tamanho da short/uniforme'
    )
    situacao = models.PositiveIntegerField('Situação', default=1, choices=choices_situacoes, help_text='Situação')
    termo_pcd = models.BooleanField(
        'Sou servidor com deficiência',
        blank=False,
        default=False,
        null=False,
        help_text='Estou ciente que irei competir na categoria paradesportiva nas modalidades e provas em que esta categoria estiver disponível.',
    )

    termo_aceitacao_exame = models.BooleanField(
        'Termo de aceitação para entrega do atestado médico',
        blank=False,
        default=False,
        null=False,
        help_text='Estou ciente de que a participação nos jogos está condicionada a entrega de Atestado Médico comprovando a capacidade física competitiva para salvaguardar minha integridade física. A entrega do atestado é obrigatória para todas as modalidades, exceto para o xadrez.',
    )
    termo_recebimento_hospedagem = models.BooleanField(
        'Desejo receber hospedagem',
        blank=False,
        default=False,
        null=False,
        help_text='Estou ciente de que a desistência de participação poderá acarretar à devolução dos valores referentes a hospedagem, salvo por motivo devidamente justificado ao respectivo representante do campus/polo até a data limite de homologação das inscrições.',
    )
    validado_em = models.DateTimeFieldPlus(null=True, blank=True)
    validado_por = models.ForeignKeyPlus(
        'comum.User', related_name='inscricao_desportiva_validada_por', null=True, on_delete=models.CASCADE, blank=True, editable=False
    )
    homologado_em = models.DateTimeFieldPlus(null=True, blank=True)
    homologado_por = models.ForeignKeyPlus(
        'comum.User', related_name='inscricao_desportiva_homologada_por', null=True, on_delete=models.CASCADE, blank=True, editable=False
    )

    rejeitado_em = models.DateTimeFieldPlus(null=True, blank=True)
    rejeitado_por = models.ForeignKeyPlus(
        'comum.User', related_name='inscricao_desportiva_rejeitada_por', null=True, on_delete=models.CASCADE, blank=True, editable=False
    )
    observacao_rejeicao = models.TextField(blank=True, verbose_name='Observação da Rejeição')

    atestado_medico = models.FileFieldPlus(
        'Atestado Médico',
        upload_to='temp_rh2/atividade_complementar/',
        null=True,
        blank=True,
        check_mimetype=False,
        help_text='Neste campo você deve anexar o atestado médico para a participação nos jogos. O atestado é obrigatório para todos os participantes, exceto os inscritos somente em tênis de mesa e/ou xadrez. Tipos de arquivos aceitos: PDF, PNG ou JPG. Tamanho Máximo: 5Mb',
        filetypes=['pdf', 'png', 'jpg'],
        max_file_size=5242880,
    )

    class Meta:
        unique_together = ('servidor', 'competicao_desportiva')
        verbose_name = 'Inscrição na Competição Desportiva'
        verbose_name_plural = 'Inscrições na Competições Desportivas'

        permissions = (('pode_validar_inscricaocompeticaodesportiva', 'Pode validar inscrição competição desportiva'),)

    def __str__(self):
        return f'Inscrição {self.servidor} pelo campus - {self.uo} - {self.competicao_desportiva}'

    def get_absolute_url(self):
        return f'/temp_rh2/competicao_desportiva/inscricao/{self.competicao_desportiva.pk}/{self.pk}/'

    @property
    def calcular_categoria(self):
        data_nascimento = self.servidor.pessoa_fisica.nascimento_data
        if data_nascimento:
            idade_fim_do_ano = get_age(self.servidor.pessoa_fisica.nascimento_data, datetime.date(self.competicao_desportiva.ano.ano, 12, 31))
            return self.competicao_desportiva.categorias.filter(idade_inferior__lte=idade_fim_do_ano, idade_superior__gte=idade_fim_do_ano).first()
        return None

    def save(self, *args, **kargs):
        if not self.categoria:
            self.categoria = self.calcular_categoria
        super().save(*args, **kargs)

    def get_todas_provas_modalidades(self, modalidades=None):
        if modalidades:
            provas_todos = self.provas.filter(modalidade__in=modalidades)
            demais_modalidades = self.modalidades.filter(pk__in=modalidades, prova__isnull=True)
        else:
            provas_todos = self.provas.all()
            demais_modalidades = self.modalidades.filter(prova__isnull=True)

        return list(provas_todos) + list(demais_modalidades)

    def get_todas_modalidades_provas_dict(self):
        return {modalidade: list(self.provas.filter(modalidade=modalidade)) for modalidade in self.modalidades.all()}

    @classmethod
    def pode_ver_atestado_medico(cls, user):
        grupos = Configuracao.get_valor_por_chave('temp_rh2', 'grupos_podem_ver_atestado_medico')
        if grupos:
            grupos = Group.objects.filter(pk__in=[int(grupo) for grupo in grupos.split(',')])
            return in_group(user, grupos)
        else:
            return True


class ResultadoModalidade(ModelPlus):
    competicao_desportiva = models.ForeignKeyPlus(
        'temp_rh2.CompeticaoDesportiva', verbose_name='Competição', null=False, on_delete=models.CASCADE, blank=False
    )
    modalidade_desportiva = models.ForeignKeyPlus(
        'temp_rh2.ModalidadeDesportiva', verbose_name='Modalidade Desportiva', on_delete=models.CASCADE, blank=False
    )
    categoria = models.ForeignKeyPlus('temp_rh2.Categoria', verbose_name='Categoria', null=True, blank=True)

    def __str__(self):
        return f'Resultado da modalidade {self.modalidade_desportiva} - {self.competicao_desportiva.nome}'

    class Meta:
        verbose_name = 'Resultado da modalidade da competição'
        verbose_name_plural = 'Resultados da modalidades das competições'
        unique_together = (
            'competicao_desportiva',
            'modalidade_desportiva',
            'categoria',
        )


class ClassificacaoModalidade(ModelPlus):
    resultado = models.ForeignKeyPlus('temp_rh2.ResultadoModalidade', null=False, on_delete=models.CASCADE)
    classificacao = models.PositiveIntegerField('Classificação')
    inscricoes = models.ManyToManyField('temp_rh2.InscricaoCompeticaoDesportiva')
    prova = models.ForeignKeyPlus('temp_rh2.Prova', null=True, blank=True, on_delete=models.CASCADE)
    equipe = models.CharFieldPlus('Equipe', blank=True, help_text='Preencha esse campo apenas a equipe for formada por um Polo. ex: Polo V')

    class Meta:
        verbose_name = 'Classificação na modalidade'
        verbose_name_plural = 'Classificações nas modalidades'
        unique_together = (
            'resultado',
            'classificacao',
            'prova',
        )

    def __str__(self):
        return f'{self.classificacao}º lugar em {self.resultado.modalidade_desportiva} nos {self.resultado.competicao_desportiva.nome} - {self.get_campus_ou_polo()}'

    def get_campus_ou_polo(self):
        inscricao = self.inscricoes.first()
        if self.resultado.modalidade_desportiva.tipo == ModalidadeDesportiva.INDIVIDUAL:
            return f'{inscricao.servidor}' if inscricao else self.equipe
        else:
            return self.equipe or self.inscricoes.first().uo or ''
