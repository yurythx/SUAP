import datetime
import tempfile
from collections import OrderedDict
from datetime import timedelta
from decimal import Decimal

from tinymce.models import HTMLField
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.auth.models import Group
from django.core.files.storage import default_storage
from django.core.validators import MaxLengthValidator
from django.db import transaction
from django.db.models import Count, Q, QuerySet, Sum

from comum.models import Setor, Vinculo, User
from comum.utils import tl
from djtools import forms
from djtools.db import models
from djtools.templatetags.filters import format_
from edu.models import Aluno, Componente, CursoCampus, Disciplina
from financeiro.models import NaturezaDespesa
from rh.models import Servidor, UnidadeOrganizacional
from comum.utils import get_uo


def eh_planejamento(obj):
    hoje = datetime.datetime.now()
    if obj.data_cadastro is None:
        return False
    if isinstance(obj, Meta | Desembolso | ItemMemoriaCalculo):
        if obj.projeto.edital.tipo_edital == Edital.ENSINO_CONTINUO:
            return bool(obj.projeto.data_avaliacao and obj.data_cadastro <= obj.projeto.data_avaliacao)

        else:
            if hoje > obj.projeto.edital.fim_inscricoes:
                return obj.data_cadastro <= obj.projeto.edital.fim_inscricoes
    elif isinstance(obj, Etapa):
        if obj.meta.projeto.edital.tipo_edital == Edital.ENSINO_CONTINUO:
            return bool(obj.meta.projeto.data_avaliacao and obj.data_cadastro <= obj.meta.projeto.data_avaliacao)
        else:
            if hoje > obj.meta.projeto.edital.fim_inscricoes:
                if obj.data_cadastro <= obj.meta.projeto.edital.fim_inscricoes:
                    return True
            else:
                return False
    return False


def get_mensagem_avaliacao(obj):
    string = ''

    if obj.dt_avaliacao and obj.justificativa_reprovacao:
        string += '<span class="status status-error">Não Aprovado em {}</span>'.format(obj.dt_avaliacao.strftime('%d/%m/%y'))
        string += f'<span class="status status-error">Justificativa: {obj.justificativa_reprovacao}</span>'

    elif obj.dt_avaliacao and not obj.justificativa_reprovacao:
        string += '<span class="status status-success">Aprovado em {}</span>'.format(obj.dt_avaliacao.strftime('%d/%m/%y'))

    if string:
        string += f' <p>Avaliador: {obj.avaliador}</p>'
        return string

    return ''


class EditalQueryset(QuerySet):
    def em_inscricao(self):
        hoje = datetime.datetime.now()
        return self.filter(inicio_inscricoes__lte=hoje, fim_inscricoes__gte=hoje)

    def em_pre_avaliacao(self):
        hoje = datetime.datetime.now()
        qs = self.filter(inicio_pre_selecao__lte=hoje, inicio_selecao__gt=hoje) | self.filter(
            tipo_edital=Edital.ENSINO_CONTINUO, inicio_inscricoes__lte=hoje, fim_selecao__gte=hoje
        )
        return qs

    def em_avaliacao(self):
        hoje = datetime.datetime.now()
        return self.filter(inicio_selecao__lte=hoje, divulgacao_selecao__gte=hoje)

    def em_selecao(self):
        hoje = datetime.datetime.now()
        return self.filter(inicio_selecao__lte=hoje, fim_selecao__gte=hoje)

    def em_periodo_indicar_pre_avaliador(self):
        hoje = datetime.datetime.now()
        qs = (
            self.filter(inicio_inscricoes__lte=hoje, inicio_selecao__gt=hoje)
            | self.filter(tipo_edital=Edital.ENSINO_CONTINUO, inicio_inscricoes__lte=hoje, fim_selecao__gte=hoje)
            | self.filter(inicio_inscricoes__lte=hoje, fim_inscricoes__gte=hoje)
        )
        return qs

    def em_execucao(self):
        hoje = datetime.datetime.now()
        projetos_cancelados = ProjetoCancelado.objects.filter(cancelado=True).values_list('projeto', flat=True)
        projetos_em_execucao = Projeto.objects.filter(
            pre_aprovado=True,
            aprovado=True,
            registroconclusaoprojeto__dt_avaliacao__isnull=True,
            edital__divulgacao_selecao__lt=hoje,
            inativado=False,
        ).exclude(id__in=projetos_cancelados)
        return self.filter(id__in=projetos_em_execucao.values_list('edital_id', flat=True))

    def concluidos(self):
        hoje = datetime.datetime.now()
        return self.filter(divulgacao_selecao__lt=hoje).exclude(id__in=self.em_execucao().values_list('id', flat=True))


class EditalManager(models.Manager):
    def get_queryset(self):
        qs = EditalQueryset(self.model, using=self._db)
        return qs

    def em_inscricao(self):
        return self.get_queryset().em_inscricao()

    def em_pre_avaliacao(self):
        return self.get_queryset().em_pre_avaliacao()

    def em_avaliacao(self):
        return self.get_queryset().em_avaliacao()

    def em_selecao(self):
        return self.get_queryset().em_selecao()

    def em_periodo_indicar_pre_avaliador(self):
        return self.get_queryset().em_periodo_indicar_pre_avaliador()

    def em_execucao(self):
        return self.get_queryset().em_execucao()

    def concluidos(self):
        return self.get_queryset().concluidos()


class ParticipacaoManagerAtivo(models.Manager):
    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(ativo=True)


class ParticipacaoManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related('vinculo_pessoa')


class ProjetoManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related('edital')


class ItemMemoriaCalculoManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related('despesa')


class Parametro(models.ModelPlus):
    codigo = models.CharField('Código', max_length=10)
    descricao = models.CharField('Descrição', max_length=150)
    grupo = models.CharField('Grupo', max_length=150)

    class Meta:
        verbose_name = 'Critério'
        verbose_name_plural = 'Critérios'

    def __str__(self):
        return f'{self.descricao}'

    def get_form_field(self, initial):
        return forms.DecimalField(label=f'{self.codigo} - {self.descricao}', initial=initial or 0)


class Edital(models.ModelPlus):
    SEARCH_FIELDS = ['titulo']

    ENSINO = '1'
    ENSINO_CONTINUO = '2'
    CAMPUS = '1'
    GERAL = '2'
    TEMA = '3'

    TIPO_EDITAL_ENSINO = (
        (ENSINO, 'Ensino'),
        (ENSINO_CONTINUO, 'Ensino Contínuo'),
    )

    TIPO_FORMA_SELECAO_CHOICES = (
        (CAMPUS, 'Campus'),
        (GERAL, 'Geral'),
    )

    objects = EditalManager()

    titulo = models.CharFieldPlus('Título', max_length=255)
    descricao = models.TextField('Descrição')
    tipo_edital = models.CharFieldPlus('Tipo do Edital', max_length=10, choices=TIPO_EDITAL_ENSINO)
    forma_selecao = models.CharFieldPlus('Forma de Seleção', max_length=10, choices=TIPO_FORMA_SELECAO_CHOICES, default=CAMPUS)
    campus_especifico = models.BooleanField(
        'Edital de Campus',
        default=False,
        help_text='Caso esta opção seja marcada, os projetos deste edital poderão ser avaliados por servidores do mesmo campus do projeto.',
    )
    qtd_projetos_selecionados = models.PositiveIntegerField(
        'Quantidade de projetos selecionados', null=True, default=0, help_text='Número máximo de projetos para serem selecionados.'
    )

    inicio_inscricoes = models.DateTimeFieldPlus('Início das Inscrições')
    fim_inscricoes = models.DateTimeFieldPlus('Fim das Inscrições')
    inicio_pre_selecao = models.DateTimeFieldPlus('Início da Pré-Seleção', null=True)
    inicio_selecao = models.DateTimeFieldPlus('Início da Seleção', help_text='O início da seleção é a data fim da pré-seleção', null=True)
    fim_selecao = models.DateTimeFieldPlus('Fim da Seleção', null=True)
    inicio_recurso = models.DateTimeFieldPlus('Início da Interposição de Recursos', null=True, blank=True)
    fim_recurso = models.DateTimeFieldPlus('Fim da Interposição de Recursos', null=True, blank=True)
    divulgacao_selecao = models.DateTimeFieldPlus('Divulgação da Seleção', null=True)

    exige_aluno = models.BooleanField(
        'Participação de aluno', help_text='Para submeter um projeto, é necessário pelo menos um aluno cadastrado', default=True
    )
    exige_servidor = models.BooleanField('Participação de servidor(a)', default=True)
    valor_financiado_por_projeto = models.DecimalFieldPlus('Valor Financiado por Projeto', default=Decimal('0.0'))
    exige_licoes_aprendidas = models.BooleanField(
        'Exige Lições Aprendidas',
        help_text='Marque esta opção caso seja necessário que os coordenadores dos projetos cadastrem as lições aprendidas',
        default=False,
    )
    exige_avaliacao_aluno = models.BooleanField(
        'Exige Avaliação dos Alunos',
        help_text='Marque esta opção caso seja necessário que os coordenadores dos projetos avaliem os alunos',
        default=False,
    )
    permite_indicacao_tardia_equipe = models.BooleanField(
        'Permite Cadastrar Aluno sem Identificá-lo',
        help_text='Marque esta opção para permitir que o coordenador do projeto possa registar a participação de alunos na equipe durante a submissão do projeto mas sem indicar especificamente quais alunos serão',
        default=False,
    )
    arquivo = models.PrivateFileField('Arquivo', upload_to='projetos_ensino/edital', null=True, blank=True)
    aluno_pode_submeter = models.BooleanField(
        'Aluno de graduação pode submeter',
        default=False,
        help_text='Marque esta opção para permitir que alunos de graduação possam submeter projeto.',
    )
    cadastrado_por = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Cadastrado por', null=True, blank=True, related_name='projetos_ensino_edital_cadastrado_por'
    )
    cadastrado_em = models.DateTimeFieldPlus('Cadastrado em', null=True, auto_now_add=True)
    termo_compromisso_coordenador = HTMLField(
        'Termo de Compromisso do Coordenador', help_text='Informe o termo de compromisso do coordenador do projeto.', null=True, blank=True
    )
    termo_compromisso_servidor = HTMLField(
        'Termo de Compromisso do Servidor', help_text='Informe o termo de compromisso do servidor participante do projeto.', null=True, blank=True
    )
    termo_compromisso_aluno = HTMLField(
        'Termo de Compromisso do Aluno', help_text='Informe o termo de compromisso do aluno participante do projeto.', null=True, blank=True
    )
    termo_compromisso_colaborador_voluntario = HTMLField(
        'Termo de Compromisso do Colaborador Externo',
        help_text='Informe o termo de compromisso do colaborador externo participante do projeto.',
        null=True,
        blank=True,
    )
    pode_escolher_campus_submissao = models.BooleanField(
        'Pode escolher campus de submissão',
        default=False,
        help_text='Marque esta opção para permitir que o coordenador do projeto possa vincular o projeto à qualquer campus durante a submissão.',
    )

    class Meta:
        verbose_name = 'Edital'
        verbose_name_plural = 'Editais'
        ordering = [
            '-inicio_inscricoes',
        ]

    def __str__(self):
        if self.tipo_edital == Edital.ENSINO_CONTINUO:
            return f'{self.titulo} - Edital de Fluxo {self.get_tipo_edital_display()}'
        else:
            return f'{self.titulo} - Edital de {self.get_tipo_edital_display()}'

    def classifica_projetos_extensao(self, uo=None):
        """
        Ordena os projetos em ordem decrescente pela pontuação e verifica se os qtd_selecionados projetos atingiram o ponte de corte.
        qtd_selecionados é definido no cadastro Plano de Oferta por Campus na visualização do edital
        """

        # Ordena os projetos pré-aprovados em ordem decrescente pela pontuação e em seguida em ordem crescente pela ordem de desempate do critério de avaliação
        # Com o queryset previamente ordenado, cria-se uma dicionário onde a chave é o id do projeto e para cada item desse dicionário
        # é criado outro dicionário para registrar a pontuação desse projeto e o somatório de todas as pontuações das avaliações do referido projeto.
        tad = OrderedDict()
        vqs = (
            Avaliacao.objects.filter(projeto__edital=self, projeto__pre_aprovado=True)
            .values('projeto__id', 'itemavaliacao__criterio_avaliacao')
            .annotate(criterio_sum_pontos=Sum('itemavaliacao__pontuacao'))
            .values('projeto__id', 'projeto__pontuacao', 'criterio_sum_pontos', 'itemavaliacao__criterio_avaliacao__ordem_desempate')
            .order_by('-projeto__pontuacao', 'itemavaliacao__criterio_avaliacao__ordem_desempate')
        )
        for d in vqs:
            if tad.get(d['projeto__id'], None) is None:
                tad[d['projeto__id']] = {'pontuacao': d['projeto__pontuacao'], 'criterio_sum_pontos': []}
            soma_dos_pontos = d['criterio_sum_pontos'] or 0
            tad[d['projeto__id']]['criterio_sum_pontos'].append(soma_dos_pontos)
        # Exemplo do primerio item da TAD. O Edital possui 7 critérios de avaliação da qualificação do projeto
        # Observa-se que criterio_sum_pontos registra o somatório de todos os itens de avaliação do projeto já na ordem de desempate.
        # OrderedDict([(2719,
        #               {'criterio_sum_pontos': [Decimal('50.00'), #ordem_desempate 1
        #                                        Decimal('49.50'), #ordem_desempate 2
        #                                        Decimal('20.00'), #ordem_desempate 3
        #                                        Decimal('19.50'), #ordem_desempate 4
        #                                        Decimal('17.50'), #ordem_desempate 5
        #                                        Decimal('20.00'), #ordem_desempate 6
        #                                        Decimal('19.50')], #ordem_desempate 7
        #                'pontuacao': Decimal('98.00')}),
        # Agora é preciso ordenar a TAD em ordem decrescente pela pontuação e pelo criterio_sum_pontos.
        tad = sorted(tad.items(), key=lambda x: (x[1]['pontuacao'], x[1]['criterio_sum_pontos']), reverse=True)

        # Classificando os projetos
        contador = 0
        for item in tad:
            contador += 1
            Projeto.objects.filter(id=item[0]).update(classificacao=contador)
        if self.forma_selecao == Edital.GERAL:
            qs = Projeto.objects.filter(edital=self, pontuacao__gt=0).order_by('classificacao')
            qs.update(aprovado=False)
            qtd_selecionados = self.qtd_projetos_selecionados
            for projeto in qs[0:qtd_selecionados]:
                projeto.aprovado = projeto.atingiu_ponto_de_corte()
                projeto.save()

        else:  # Edital.CAMPUS - Máx. de Projetos selecionados para a uo
            qs = Projeto.objects.filter(edital=self, uo=uo, pontuacao__gt=0).order_by('classificacao')
            qs.update(aprovado=False)

            qtd_selecionados = self.ofertaprojeto_set.get(uo=uo).qtd_selecionados
            for projeto in qs[0:qtd_selecionados]:
                projeto.aprovado = projeto.atingiu_ponto_de_corte()
                projeto.save()

    def get_elementos_despesa(self):
        return NaturezaDespesa.objects.filter(id__in=self.recurso_set.values_list('despesa_id', flat=True))

    def get_uos(self):
        return UnidadeOrganizacional.objects.filter(id__in=OfertaProjeto.objects.filter(edital=self).values_list('uo', flat=True))

    def get_oferta_por_avaliador(self) -> list[list[UnidadeOrganizacional | bool]]:
        user = tl.get_user()
        indicacoes = AvaliadorIndicado.objects.filter(vinculo=user.get_vinculo(), projeto__edital=self)
        # O campus segue listado, mas só a indicação de projeto pré-aprovado o deixa pendente:
        # a pré-seleção cancelada não apaga a indicação (#17574).
        avaliaveis = indicacoes.filter(projeto__pre_aprovado=True).values_list('projeto', flat=True)
        avalicoes_realizadas = Avaliacao.objects.filter(projeto__in=avaliaveis, vinculo=user.get_vinculo())

        lista = []
        for uo in self.get_uos().filter(id__in=indicacoes.values_list('projeto__uo', flat=True)):
            pendente = False
            if Projeto.objects.filter(id__in=avaliaveis, uo=uo).exclude(id__in=avalicoes_realizadas.values_list('projeto', flat=True)).exists():
                pendente = True
            lista.append([uo, pendente])
        return lista

    def pendente_avaliacao(self) -> bool:
        user = tl.get_user()
        indicacoes = AvaliadorIndicado.objects.filter(vinculo=user.get_vinculo(), projeto__edital=self, projeto__pre_aprovado=True).values_list(
            'projeto', flat=True
        )
        avalicoes_realizadas = Avaliacao.objects.filter(projeto__in=indicacoes, vinculo=user.get_vinculo()).values_list('projeto', flat=True)
        return Projeto.objects.filter(id__in=indicacoes).exclude(id__in=avalicoes_realizadas).exists()

    @classmethod
    def get_editais_disponiveis(self):
        """
        Retorna um lista com todos os editais abertos (dentro do período de inscrições) disponíveis.
        O termo disponíveis é usado, pois o usuário só poderá submeter um projeto por edital, isto é,
        excluir os editais no qual o usuário é participante.
        """
        user = tl.get_user()
        abertos = self.objects.em_inscricao()

        editais = []
        for edital in abertos:
            if not Participacao.objects.filter(projeto__edital__id=edital.id, projeto__pre_aprovado=True, responsavel=True, pessoa=user):
                editais.append(edital)
        return editais

    def get_form(self):
        edital = self

        class CustomForm(forms.FormPlus):
            fieldsets = (
                (
                    'titulo',
                    {
                        'fields': (
                            'item_1',
                            'item_2',
                        )
                    },
                ),
            )

            def clean(self):
                super().clean()
                for valor_parametro in self.cleaned_data.values():
                    if valor_parametro < 0:
                        raise forms.ValidationError('Os valores não podem ser negativos.')
                return self.cleaned_data

            def save(self):
                for field_name, valor_parametro in self.cleaned_data.items():
                    if not field_name.startswith('item_'):
                        continue
                    item_id = int(field_name.split('_')[-1])
                    item = ParametroEdital.objects.get_or_create(parametro_id=item_id, edital=edital)[0]
                    item.valor_parametro = valor_parametro
                    item.save()

        fieldsets = OrderedDict()
        for parametro in Parametro.objects.all().order_by('pk'):
            if not fieldsets.get(parametro.grupo):
                fieldsets[parametro.grupo] = []

            parametro_edital = ParametroEdital.objects.get_or_create(parametro=parametro, edital=edital)[0]
            field = parametro.get_form_field(initial=parametro_edital.valor_parametro)
            field_name = f'item_{parametro.pk}'
            fieldsets.get(parametro.grupo).append(field_name)
            CustomForm.base_fields[field_name] = field

        grupos = []
        for titulo, fields in fieldsets.items():
            grupos.append((titulo, {'fields': fields}))
        CustomForm.fieldsets = grupos
        return CustomForm

    def pode_divulgar_resultado(self):
        hoje = datetime.datetime.now()
        return self.divulgacao_selecao <= hoje and self.fim_selecao < hoje

    def pode_divulgar_resultado_parcial(self):
        hoje = datetime.datetime.now()
        return hoje <= self.divulgacao_selecao and self.fim_selecao < hoje

    @transaction.atomic
    def save(self):
        super().save()

    def is_periodo_inscricao(self):
        hoje = datetime.datetime.now()
        return self.inicio_inscricoes <= hoje <= self.fim_inscricoes

    def is_periodo_fim_inscricao(self):
        hoje = datetime.datetime.now()
        if self.tipo_edital == Edital.ENSINO_CONTINUO:
            return self.fim_inscricoes <= hoje
        return self.fim_inscricoes < hoje < self.inicio_pre_selecao

    def is_periodo_antes_pre_selecao(self):
        hoje = datetime.datetime.now()
        return self.inicio_inscricoes < hoje < self.inicio_pre_selecao

    def is_periodo_pre_selecao(self):
        hoje = datetime.datetime.now()
        if self.tipo_edital == Edital.ENSINO_CONTINUO:
            return self.inicio_inscricoes <= hoje < self.fim_selecao
        return self.inicio_pre_selecao <= hoje < self.inicio_selecao

    def is_periodo_selecao(self):
        hoje = datetime.datetime.now()
        if self.tipo_edital == Edital.ENSINO_CONTINUO:
            return self.inicio_selecao <= hoje < self.fim_selecao
        return self.inicio_selecao <= hoje < self.fim_selecao

    def is_periodo_selecao_e_pre_divulgacao(self):
        hoje = datetime.datetime.now()
        if self.tipo_edital == Edital.ENSINO_CONTINUO:
            return self.inicio_selecao <= hoje < self.fim_selecao
        return self.inicio_selecao <= hoje < self.divulgacao_selecao

    def is_periodo_divulgacao(self):
        hoje = datetime.datetime.now()
        return self.divulgacao_selecao <= hoje

    def is_periodo_pos_selecao(self):
        hoje = datetime.datetime.now()
        return hoje > self.fim_selecao

    def num_total_projetos_pre_aprovados(self, uo=None):
        """
        Retorna a quantidade de projetos pré-selecionados
        """
        if uo:
            return Projeto.objects.filter(edital=self, uo=uo, pre_aprovado=True).aggregate(Count('id'))['id__count']
        return Projeto.objects.filter(edital=self, pre_aprovado=True).aggregate(Count('id'))['id__count']

    def num_total_projetos_inscritos(self, uo=None):
        """
        Retorna a quantidade de projetos cadastrados no edital
        """
        if uo:
            return Projeto.objects.filter(edital=self, uo=uo).aggregate(Count('id'))['id__count']
        return Projeto.objects.filter(edital=self).aggregate(Count('id'))['id__count']

    def num_total_projetos_enviados(self, uo=None):
        """
        Retorna a quantidade de projetos que foram enviados ao edital
        """
        if uo:
            return Projeto.objects.filter(edital=self, uo=uo, data_conclusao_planejamento__isnull=False).aggregate(Count('id'))['id__count']
        return Projeto.objects.filter(edital=self, data_conclusao_planejamento__isnull=False).aggregate(Count('id'))['id__count']

    def get_ofertas_projeto(self):
        return OfertaProjeto.objects.filter(edital=self).order_by('uo')

    def get_forma_selecao(self):
        if self.forma_selecao == Edital.CAMPUS:
            return 'Por Campus'
        elif self.forma_selecao == Edital.GERAL:
            return 'Geral'

    def eh_edital_continuo(self):
        return self.tipo_edital == Edital.ENSINO_CONTINUO

    def get_criterios_de_avaliacao(self):
        return self.criterioavaliacao_set.order_by('ordem_desempate')

    def pode_submeter_projeto(self, vinculo):
        if vinculo.eh_servidor():
            return True
        elif vinculo.eh_aluno():
            from edu.models.cadastros_gerais import NivelEnsino

            return (
                self.aluno_pode_submeter
                and vinculo.relacionamento.curso_campus.modalidade
                and vinculo.relacionamento.curso_campus.modalidade.nivel_ensino.pk == NivelEnsino.GRADUACAO
            )
        return False

    def exige_termo_coordenador(self):
        return self.termo_compromisso_coordenador not in ['', None]

    def exige_termo_servidor(self):
        return self.termo_compromisso_servidor not in ['', None]

    def exige_termo_aluno(self):
        return self.termo_compromisso_aluno not in ['', None]

    def exige_termo_colaborador(self):
        return self.termo_compromisso_colaborador_voluntario not in ['', None]


class ParametroEdital(models.ModelPlus):
    edital = models.ForeignKeyPlus(Edital, verbose_name='Edital', on_delete=models.CASCADE)
    parametro = models.ForeignKeyPlus(Parametro, verbose_name='Critério', on_delete=models.CASCADE)
    valor_parametro = models.DecimalFieldPlus('Valor do Critério', default=0)

    class Meta:
        verbose_name = 'Critério do Edital'
        verbose_name_plural = 'Critérios do Edital'

    def __str__(self):
        return f'{self.edital}'


class CriterioAvaliacao(models.ModelPlus):
    edital = models.ForeignKeyPlus(Edital, on_delete=models.CASCADE)
    descricao = models.TextField('Descrição')
    pontuacao_maxima = models.DecimalFieldPlus('Pontuação Máxima')
    ordem_desempate = models.IntegerField(
        'Ordem para Desempate', null=True, help_text='Ordem 1 indica que o critério será o primeiro a ser considerado para desempate.'
    )

    class Meta:
        verbose_name = 'Critério de Avaliação'
        verbose_name_plural = 'Critérios de Avaliação'
        ordering = ['id']

    def __str__(self):
        return self.descricao


class OrigemRecursoEdital(models.ModelPlus):
    descricao = models.CharField('Descrição', max_length=255)
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Origem de Recurso do Edital'
        verbose_name_plural = 'Origens de Recurso do Edital'

    def __str__(self):
        return self.descricao


class Recurso(models.ModelPlus):
    edital = models.ForeignKeyPlus(Edital, on_delete=models.CASCADE)
    origem = models.CharField('Origem do recurso', max_length=255)
    valor = models.DecimalFieldPlus('Valor disponível (R$)')
    despesa = models.ForeignKeyPlus(NaturezaDespesa, verbose_name='Despesa', on_delete=models.CASCADE, related_name='projetoensino_despesa_recurso')

    class Meta:
        verbose_name = 'Investimento'
        verbose_name_plural = 'Investimentos'
        ordering = ['despesa__nome']

    def __str__(self):
        return f'{self.despesa} / {self.origem}'


class OfertaProjeto(models.ModelPlus):
    edital = models.ForeignKeyPlus(Edital, on_delete=models.CASCADE)
    uo = models.ForeignKeyPlus(UnidadeOrganizacional, verbose_name='Campus', on_delete=models.CASCADE, related_name='projetoensino_uo_oferta')
    qtd_aprovados = models.PositiveIntegerField(
        'Pré-Selecionados', help_text='Informe quantos projetos poderão ser pré-selecionados pelo coordenador do respectivo campus', null=True
    )
    qtd_selecionados = models.PositiveIntegerField('Selecionados', help_text='Informe quantos projetos serão selecionados.', null=True)

    class Meta:
        indexes = [models.Index(fields=['edital', 'uo'], name='proj_ens_ofertaprojeto_indexes')]
        verbose_name = 'Oferta de Projeto'
        verbose_name_plural = 'Ofertas de Projeto'

    def __str__(self):
        return f'Oferta: {self.edital} - {self.uo}'


class TipoVinculo:
    BOLSISTA = 'Bolsista'
    VOLUNTARIO = 'Voluntário'
    TIPOS = (
        (BOLSISTA, 'Sim'),
        (VOLUNTARIO, 'Não'),
    )


class EditalAnexo(models.ModelPlus):
    SERVIDOR_DOCENTE = '1'
    ALUNO = '2'
    COORDENADOR_DOCENTE = '3'
    COORDENADOR_TECNICO_ADMINISTRATIVO = '4'
    SERVIDOR_ADMINISTRATIVO = '5'
    COLABORADOR_VOLUNTARIO = '6'
    TIPO_MEMBRO = (
        (SERVIDOR_DOCENTE, 'Docente'),
        (SERVIDOR_ADMINISTRATIVO, 'Técnico Administrativo'),
        (ALUNO, 'Aluno'),
        (COORDENADOR_DOCENTE, 'Coordenador Docente'),
    )
    BOLSISTA = 'Bolsista'
    VOLUNTARIO = 'Voluntário'

    TIPOS_VINCULO = (
        (BOLSISTA, BOLSISTA),
        (VOLUNTARIO, VOLUNTARIO),
    )
    edital = models.ForeignKeyPlus(Edital, on_delete=models.CASCADE)
    nome = models.CharField('Nome', max_length=255)
    descricao = models.TextField('Descrição', blank=True)
    tipo_membro = models.CharField('Tipo de Membro', max_length=1, choices=TIPO_MEMBRO)
    vinculo = models.CharField('Tipo de Vínculo', max_length=20, choices=TIPOS_VINCULO)
    ordem = models.PositiveIntegerField('Ordem', help_text='Informe um número inteiro maior ou igual a 1')

    class Meta:
        ordering = ['ordem']

    def __str__(self):
        return self.nome


class EixoTematico(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição', max_length=200)
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Eixo Temático'
        verbose_name_plural = 'Eixos Temáticos'


class Projeto(models.ModelPlus):
    INTERNO = 'INTERNO'
    EXTERNO = 'EXTERNO'
    AMBOS = 'AMBOS'
    PUBLICO_ALVO_CHOICES = (
        (INTERNO, 'Interno'),
        (EXTERNO, 'Externo'),
        (AMBOS, 'Ambos'),
    )

    PERIODO_INSCRICAO = 'Inscrição'
    PERIODO_FIM_INSCRICAO = 'Inscrição Encerrada'
    PERIODO_PRE_SELECAO = 'Pré-Seleção'
    PERIODO_SELECAO = 'Seleção'
    PERIODO_EXECUCAO = 'Execução'
    PERIODO_RESULTADO_PARCIAL = 'Resultado Parcial'
    PERIODO_ENCERRADO = 'Encerrado'

    STATUS_CONCLUIDO = 'Concluído'
    STATUS_INATIVADO = 'Inativado'
    STATUS_EM_EXECUCAO = 'Em execução'
    STATUS_NAO_ACEITO = 'Não aceito'
    STATUS_NAO_SELECIONADO = 'Não selecionado'
    STATUS_SELECIONADO = 'Selecionado'
    STATUS_EM_SELECAO = 'Em Seleção'
    STATUS_PRE_SELECIONADO = 'Pré-selecionado'
    STATUS_INSCRITO = 'Enviado'
    STATUS_EM_INSCRICAO = 'Em edição'
    STATUS_NAO_ENVIADO = 'Não Enviado'
    STATUS_CANCELADO = 'Cancelado'
    STATUS_EM_ENCERRAMENTO = 'Em Encerramento'

    STATUS_SIM = 'Sim'
    STATUS_NAO = 'Não'
    STATUS_EM_ESPERA = 'Em Espera'
    STATUS_AGUARDANDO_PRE_SELECAO = 'Aguardando pré-seleção'
    STATUS_AGUARDANDO_AVALIACAO = 'Aguardando avaliação'
    STATUS_PRE_SELECIONADO_EM = 'Pré-selecionado em'
    STATUS_SELECIONADO_EM = 'Selecionado em'
    STATUS_NAO_SELECIONADO_EM = 'Não selecionado em'
    STATUS_AGUARDADO_ENVIO_PROJETO = 'Aguardando o envio do projeto'

    objects = ProjetoManager()

    edital = models.ForeignKeyPlus(Edital, verbose_name='Edital')
    uo = models.ForeignKeyPlus(UnidadeOrganizacional, verbose_name='Campus', related_name='projetoensino_projeto_uo')
    setor = models.ForeignKeyPlus(Setor, verbose_name='Setor')
    titulo = models.CharField('Título do projeto', max_length=255)

    eixo_tematico = models.ForeignKeyPlus(EixoTematico, verbose_name='Eixo Temático')
    inicio_execucao = models.DateFieldPlus('Início da Execução')
    fim_execucao = models.DateFieldPlus('Término da Execução')
    interdisciplinar = models.BooleanField('Projeto Interdisciplinar?', default=False)
    disciplinas = models.ManyToManyFieldPlus(Disciplina, related_name='disciplinas_set', blank=True)
    componentes = models.ManyToManyFieldPlus(Componente, related_name='componentes_set', blank=True, verbose_name='Disciplinas')
    cursos = models.ManyToManyFieldPlus(CursoCampus, related_name='cursos_set', blank=True)
    relacao_pesquisa_ext = models.BooleanField('Possui relação institucional com Pesquisa/Extensão?', default=False)
    parceiros_externos = models.BooleanField('Há parceiros externos?', default=False)
    quais_parceiros_externos = models.CharFieldPlus('Parceiros Externos', max_length=5000, null=True, blank=True)
    ch_total = models.PositiveIntegerField('Carga horária total para desenvolvimento do projeto')

    # Comum
    resumo = HTMLField('Resumo')
    introducao = HTMLField('Introdução')
    justificativa = HTMLField('Justificativa e Relevância')
    objetivo_geral = HTMLField('Objetivo Geral')
    metodologia = HTMLField('Metodologia da execução do projeto')
    acompanhamento_e_avaliacao = HTMLField('Acompanhamento e avaliação do projeto durante a execução')
    resultados_esperados = HTMLField('Resultados esperados e Disseminação dos Resultados')
    referencias = HTMLField('Referências')

    vinculo_coordenador = models.ForeignKey(
        'comum.Vinculo',
        verbose_name='Coordenador do Projeto',
        related_name='projeto_ensino_vinculo_coordenador_set',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )

    # avaliacao
    pre_aprovado = models.BooleanField('Pré-selecionado', default=False)
    data_pre_avaliacao = models.DateField('Data da Pré-seleção', null=True, blank=True)
    vinculo_autor_pre_avaliacao = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Responsável pela Pré-seleção', null=True, blank=True, related_name='projetoensino_pre_vinculo_avaliador'
    )
    aprovado = models.BooleanField('Selecionado', default=False)
    aprovado_na_distribuicao = models.BooleanField('Selecionado na distribuição de bolsas', default=False, blank=False)
    data_avaliacao = models.DateField('Data da seleção', null=True, blank=True)
    pontuacao = models.DecimalFieldPlus('Pontuação', default=Decimal('0'), null=True, blank=True)
    data_conclusao_planejamento = models.DateTimeFieldPlus(
        'Data da Conclusão do Projeto', null=True, blank=True
    )  # usado se o projeto for do tipo contínuo
    data_finalizacao_conclusao = models.DateTimeFieldPlus('Data da Finalização do Projeto', null=True, blank=True)
    data_validacao_pontuacao = models.DateTimeFieldPlus('Data da Finalização do Projeto', null=True, blank=True)

    vinculo_monitor = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Responsável pelo Monitoramento', null=True, blank=True, related_name='projetoensino_vinculo_monitor'
    )
    classificacao = models.IntegerField('Classificação', null=True)
    inativado = models.BooleanField('Inativado', default=False)
    motivo_inativacao = models.CharFieldPlus('Motivo da Inativação do Projeto', max_length=5000, null=True, blank=True)
    inativado_em = models.DateTimeFieldPlus('Inativado em', null=True, blank=True)
    inativado_por = models.ForeignKeyPlus(
        Servidor, verbose_name='Inativado por', related_name='projeto_ensino_inativado_por', null=True, blank=True, on_delete=models.CASCADE
    )

    class Meta:
        verbose_name = 'Projeto'
        verbose_name_plural = 'Projetos'

        permissions = (
            ('pode_gerenciar_edital', 'Pode gerenciar edital'),
            ('pode_avaliar_projeto', 'Pode avaliar projeto'),
            ('pode_pre_avaliar_projeto', 'Pode pre avaliar projeto'),
            ('pode_visualizar_projeto', 'Pode visualizar projeto'),
            ('pode_visualizar_relatorios_projetos_ensino', 'Pode visualizar relatórios de projetos de ensino'),
            ('pode_visualizar_projetos_em_monitoramento', 'Pode visualizar projetos em monitoramento'),
            ('pode_avaliar_cancelamento_projeto', 'Pode avaliar cancelamento projeto'),
            ('pode_registrar_consideracao_aluno', 'Pode registrar consideração sobre avaliação'),
            ('pode_interagir_com_projeto', 'Pode interagir com projeto'),
            ('pode_monitorar_projeto', 'Pode monitorar projeto'),
        )

    def __str__(self):
        return f'Projeto de {self.edital.get_tipo_edital_display()} "{self.titulo}"'

    def get_pontuacao_display(self):
        user = tl.get_user()
        if self.edital.tipo_edital == Edital.ENSINO_CONTINUO:
            return '<span class="status status-info">Não se aplica</span>'
        else:
            if self.selecao_ja_divulgada() or user.has_perm('projetos_ensino.pode_gerenciar_edital'):
                return self.pontuacao

            else:
                return '<span class="status status-alert">Aguardando divulgação</span>'

    def get_pontuacao_total_display(self):
        user = tl.get_user()
        if self.edital.tipo_edital == Edital.ENSINO_CONTINUO:
            return '<span class="status status-info">Não se aplica</span>'
        else:
            if self.selecao_ja_divulgada() or user.has_perm('projetos_ensino.pode_gerenciar_edital'):
                return self.pontuacao
            else:
                return '<span class="status status-alert">Aguardando divulgação</span>'

    def get_pre_selecionado(self, participacao=None, user=None):
        if not user:
            user = tl.get_user()
        hoje = datetime.datetime.now()
        if not participacao:
            if hoje > self.edital.inicio_pre_selecao:
                if user.has_perm('projetos_ensino.pode_pre_avaliar_projeto'):
                    if self.data_conclusao_planejamento or (not self.data_conclusao_planejamento and self.data_pre_avaliacao):
                        if self.data_pre_avaliacao and self.pre_aprovado:
                            return (
                                f'<span class="status status-success">{Projeto.STATUS_PRE_SELECIONADO_EM} {format_(self.data_pre_avaliacao)} </span>'
                            )
                        elif self.data_pre_avaliacao and not self.pre_aprovado:
                            return f'<span class="status status-error">{Projeto.STATUS_NAO_SELECIONADO_EM} {format_(self.data_pre_avaliacao)} </span>'
                        elif hoje >= self.edital.inicio_selecao:
                            return '<span class="status status-info">Não foi pré-avaliado.</span>'
                        else:
                            return '<p class="alert alert-warning">Aguardando pré-avaliação.</p>'
                    elif self.edital.is_periodo_inscricao():
                        return '<p class="alert alert-warning">Aguardando finalização da inscrição.</p>'
                    else:
                        return '<span class="status status-error">Projeto não enviado</span>'

                if self.data_pre_avaliacao and self.pre_aprovado:
                    return f'<span class="status status-success">{Projeto.STATUS_SIM}</span>'
                elif self.edital.eh_edital_continuo():
                    return '<span class="status status-alert">Aguardando pré-avaliação</span>'
                else:
                    return f'<span class="status status-rejeitado">{Projeto.STATUS_NAO}</span>'
            else:
                if user.has_perm('projetos_ensino.pode_gerenciar_edital'):
                    return f'<span class="status status-alert">{Projeto.STATUS_EM_ESPERA}</span>'
                else:
                    return f'<span class="status status-alert">{Projeto.STATUS_AGUARDANDO_PRE_SELECAO}</span>'
        else:
            if participacao.projeto.data_pre_avaliacao:
                if participacao.projeto.pre_aprovado:
                    return f'<span class="status status-success">{Projeto.STATUS_PRE_SELECIONADO_EM} {format_(participacao.projeto.data_pre_avaliacao)} </span>'
                else:
                    return f'<span class="status status-error">{Projeto.STATUS_NAO_SELECIONADO_EM} {format_(participacao.projeto.data_pre_avaliacao)} </span>'
            else:
                if not participacao.projeto.data_conclusao_planejamento and participacao.projeto.edital.fim_inscricoes >= datetime.datetime.now():
                    return f'<span class="status status-error">{Projeto.STATUS_AGUARDADO_ENVIO_PROJETO}</span>'
                elif not participacao.projeto.data_conclusao_planejamento:
                    return f'<span class="status status-error">{Projeto.STATUS_NAO_ENVIADO}</span>'
                else:
                    return f'<span class="status status-alert">{Projeto.STATUS_AGUARDANDO_PRE_SELECAO}</span>'

    def get_periodo(self):
        periodo = None
        eh_periodo_inscricao = self.edital.is_periodo_inscricao()
        registro_conclusao = self.get_registro_conclusao()
        if self.edital.tipo_edital == Edital.ENSINO_CONTINUO:
            if eh_periodo_inscricao and not self.data_conclusao_planejamento:
                periodo = self.PERIODO_INSCRICAO
            elif self.data_conclusao_planejamento and not self.data_pre_avaliacao:
                periodo = self.PERIODO_PRE_SELECAO
            elif self.aprovado:
                periodo = self.PERIODO_EXECUCAO
        else:
            if (
                registro_conclusao
                and registro_conclusao.dt_avaliacao
                or (not self.pre_aprovado and self.edital.inicio_selecao < datetime.datetime.now())
                or (not self.aprovado and self.edital.divulgacao_selecao < datetime.datetime.now())
            ):
                # se status igual STATUS_CONCLUIDO ou  STATUS_NAO_ACEITO. Não usar self.get_status() pois irá ocorrer o erro maximum recursion depth exceeded
                periodo = self.PERIODO_ENCERRADO
            elif eh_periodo_inscricao:
                periodo = self.PERIODO_INSCRICAO
            elif self.edital.is_periodo_fim_inscricao():
                periodo = self.PERIODO_FIM_INSCRICAO
            elif self.edital.is_periodo_pre_selecao():
                periodo = self.PERIODO_PRE_SELECAO
            elif self.edital.is_periodo_selecao():
                periodo = self.PERIODO_SELECAO
            elif self.edital.is_periodo_divulgacao():
                periodo = self.PERIODO_EXECUCAO
            elif self.edital.is_periodo_pos_selecao():
                periodo = self.PERIODO_RESULTADO_PARCIAL
            else:
                periodo = self.PERIODO_ENCERRADO

        return periodo

    def get_status(self):
        hoje = datetime.datetime.now()
        registro_conclusao = self.get_registro_conclusao()
        periodo = self.get_periodo()
        if self.foi_cancelado():
            return self.STATUS_CANCELADO

        if self.edital.tipo_edital == Edital.ENSINO_CONTINUO:
            if registro_conclusao and registro_conclusao.dt_avaliacao:
                return self.STATUS_CONCLUIDO
            if self.inativado:
                return self.STATUS_INATIVADO
            if self.aprovado:
                return self.STATUS_EM_EXECUCAO
            if (not self.data_conclusao_planejamento and self.data_pre_avaliacao and periodo != self.PERIODO_INSCRICAO) or (
                not self.aprovado and not self.pre_aprovado and self.data_avaliacao and self.data_pre_avaliacao
            ):
                return self.STATUS_NAO_ACEITO
            if self.data_conclusao_planejamento:
                return self.STATUS_INSCRITO
            if not self.data_conclusao_planejamento and periodo == self.PERIODO_INSCRICAO:
                return self.STATUS_EM_INSCRICAO

            return self.STATUS_NAO_ENVIADO

        else:
            if registro_conclusao and registro_conclusao.dt_avaliacao:
                return self.STATUS_CONCLUIDO
            if self.inativado:
                return self.STATUS_INATIVADO
            if self.aprovado and periodo == self.PERIODO_EXECUCAO:
                return self.STATUS_EM_EXECUCAO
            if periodo == self.PERIODO_SELECAO:
                return self.STATUS_EM_SELECAO
            if not self.pre_aprovado and self.data_pre_avaliacao and self.edital.inicio_selecao < hoje:
                return self.STATUS_NAO_ACEITO
            if not self.aprovado and self.data_avaliacao and self.edital.divulgacao_selecao < hoje:
                return self.STATUS_NAO_SELECIONADO
            if self.aprovado and self.edital.divulgacao_selecao < hoje:
                return self.STATUS_SELECIONADO
            if self.pre_aprovado and (periodo == self.PERIODO_PRE_SELECAO or periodo == self.PERIODO_SELECAO):
                return self.STATUS_PRE_SELECIONADO
            if self.data_conclusao_planejamento or (not self.data_conclusao_planejamento and self.data_pre_avaliacao):
                return self.STATUS_INSCRITO
            if self.edital.is_periodo_inscricao():
                return self.STATUS_EM_INSCRICAO
            return self.STATUS_NAO_ENVIADO

    def get_selecionado(self, participacao=None):
        user = tl.get_user()
        if not participacao:
            if self.edital.tipo_edital == Edital.ENSINO_CONTINUO:
                if not self.data_pre_avaliacao:
                    return f'<span class="status status-alert">{Projeto.STATUS_EM_ESPERA}</span>'
                elif self.aprovado:
                    return f'<span class="status status-success">{Projeto.STATUS_SIM}</span>'
                else:
                    return f'<span class="status status-rejeitado">{Projeto.STATUS_NAO}</span>'
            else:
                if self.divulgacao_avaliacao_liberada():
                    if self.aprovado:
                        return f'<span class="status status-success">{Projeto.STATUS_SIM}</span>'
                    else:
                        return f'<span class="status status-rejeitado">{Projeto.STATUS_NAO}</span>'
                else:
                    if user.groups.filter(name='Gerente Sistêmico de Projetos de Ensino'):
                        return f'<span class="status status-alert">{Projeto.STATUS_EM_ESPERA}</span>'
                    else:
                        return f'<span class="status status-alert">{Projeto.STATUS_AGUARDANDO_AVALIACAO}</span>'
        else:
            if not participacao.projeto.data_conclusao_planejamento and participacao.projeto.edital.fim_inscricoes >= datetime.datetime.now():
                return f'<span class="status status-error">{Projeto.STATUS_AGUARDADO_ENVIO_PROJETO}</span>'
            elif not participacao.projeto.data_conclusao_planejamento:
                return f'<span class="status status-error">{Projeto.STATUS_NAO_ENVIADO}</span>'
            else:
                if (
                    participacao.projeto.data_avaliacao
                    and participacao.projeto.divulgacao_avaliacao_liberada()
                    and participacao.projeto.edital.tipo_edital != participacao.projeto.edital.ENSINO_CONTINUO
                ):
                    if participacao.projeto.aprovado:
                        return f'<span class="status status-success">{Projeto.STATUS_SELECIONADO_EM} {format_(participacao.projeto.edital.divulgacao_selecao)} </span>'
                    else:
                        return f'<span class="status status-error">{Projeto.STATUS_NAO_SELECIONADO_EM} {format_(participacao.projeto.edital.divulgacao_selecao)} </span>'
                elif (
                    not participacao.projeto.data_avaliacao
                    and participacao.projeto.divulgacao_avaliacao_liberada()
                    and not self.pre_aprovado
                    and self.data_pre_avaliacao
                ):
                    return f'<span class="status status-error">{Projeto.STATUS_NAO_SELECIONADO}</span>'
                else:
                    if participacao.projeto.edital.tipo_edital == participacao.projeto.edital.ENSINO_CONTINUO:
                        if participacao.projeto.pre_aprovado:
                            return f'<span class="status status-success">{Projeto.STATUS_SELECIONADO_EM} {format_(participacao.projeto.data_pre_avaliacao)} </span>'
                        elif participacao.projeto.data_pre_avaliacao:
                            return f'<span class="status status-error">{Projeto.STATUS_NAO_SELECIONADO_EM} {format_(participacao.projeto.data_pre_avaliacao)} </span>'
                        else:
                            return f'<span class="status status-alert">{Projeto.STATUS_AGUARDANDO_AVALIACAO}</span>'
                    else:
                        return f'<span class="status status-alert">{Projeto.STATUS_AGUARDANDO_AVALIACAO}</span>'

    def divulgacao_avaliacao_liberada(self):
        return self.edital.divulgacao_selecao <= datetime.datetime.now()

    def atingiu_ponto_de_corte(self):
        total = Decimal(0)
        for criterio_avaliacao in self.edital.criterioavaliacao_set.all():
            total += criterio_avaliacao.pontuacao_maxima
        return self.pontuacao >= total / 2

    def get_plano_aplicacao_como_dict(self):
        recursos = []
        total_geral = Decimal(0)
        total_proex = Decimal(0)
        total_digae = Decimal(0)
        total_campus = Decimal(0)
        for despesa in self.edital.get_elementos_despesa():
            despesa.proex = Decimal(sum(Recurso.objects.filter(despesa=despesa, edital=self.edital, origem='PROEX').values_list('valor', flat=True)))
            total_proex += despesa.proex
            despesa.digae = Decimal(sum(Recurso.objects.filter(despesa=despesa, edital=self.edital, origem='DIGAE').values_list('valor', flat=True)))
            total_digae += despesa.digae
            despesa.campus = Decimal(
                sum(Recurso.objects.filter(despesa=despesa, edital=self.edital, origem='CAMPUS').values_list('valor', flat=True))
            )
            total_campus += despesa.campus
            despesa.total = despesa.proex + despesa.digae + despesa.campus
            total_geral += despesa.total
            recursos.append(despesa)

        return {
            'recursos': recursos,
            'total_geral': total_geral,
            'total_proex': total_proex,
            'total_digae': total_digae,
            'total_campus': total_campus,
        }

    def get_cronograma_desembolso_como_lista(self):
        cronograma = []
        for despesa in self.edital.get_elementos_despesa():
            for i in range(1, 13):
                total = Decimal(0)
                for desembolso in Desembolso.objects.filter(projeto=self, despesa=despesa, mes=i):
                    total += desembolso.valor
                setattr(despesa, f'mes_{i}', total)
            cronograma.append(despesa)
        return cronograma

    def is_gerente_sistemico(self, user=None):
        if not user:
            user = tl.get_user()
        return user.has_perm('projetos_ensino.pode_gerenciar_edital')

    def is_pode_ver_nome_avaliador(self, user=None):
        if not user:
            user = tl.get_user()
        return self.is_gerente_sistemico(user)

    def is_coordenador(self, user=None):
        if not user:
            user = tl.get_user()
        if self.is_gerente_sistemico():
            return True
        responsavel = self.get_responsavel()
        return bool(responsavel and user.get_vinculo() == responsavel)

    def is_avaliador(self, user=None):
        if not user:
            user = tl.get_user()
        return user.has_perm('projetos_ensino.pode_avaliar_projeto')

    def pode_avaliar_projeto(self, vinculo: Vinculo | None) -> bool:
        """O mesmo recorte de ``projetos_pre_aprovados``: pré-aprovado, em seleção e indicado para este projeto (#17547)."""
        return bool(
            self.pre_aprovado
            and self.edital.is_periodo_selecao()
            and self.data_conclusao_planejamento
            and AvaliadorIndicado.objects.filter(projeto=self, vinculo=vinculo).exists()
        )

    def is_pre_avaliador(self, user=None):
        if not user:
            user = tl.get_user()

        return user.has_perm('projetos_ensino.pode_monitorar_projeto')

    def is_responsavel(self, user=None):
        if not user:
            user = tl.get_user()
        return Participacao.objects.filter(projeto=self, vinculo_pessoa=user.get_vinculo(), responsavel=True).exists()

    def get_metas(self):
        return self.meta_set.all().order_by('ordem')

    def pode_editar_gasto(self):
        user = tl.get_user()
        status = self.get_status()
        return bool(self.is_responsavel(user) and status == Projeto.STATUS_EM_EXECUCAO)

    def pode_registrar_conclusao(self):
        if self.data_finalizacao_conclusao:
            return False
        registro_conclusao = self.get_registro_conclusao()
        if registro_conclusao and registro_conclusao.dt_avaliacao:
            return False
        user = tl.get_user()
        status = self.get_status()
        return bool(self.is_responsavel(user) and status == Projeto.STATUS_EM_EXECUCAO)

    def pode_finalizar_conclusao(self):
        user = tl.get_user()
        registro_conclusao = self.get_registro_conclusao()
        if (
            self.data_finalizacao_conclusao
            or not registro_conclusao
            or self.tem_registro_execucao_etapa_pendente()
            or self.tem_registro_gasto_pendente()
            or self.tem_registro_anexos_pendente()
            or self.tem_registro_foto_pendente()
            or self.tem_caracterizacao_pendente()
            or not self.is_responsavel(user)
            or (self.edital.exige_licoes_aprendidas and self.tem_registro_licoes_pendente())
            or self.tem_avaliacao_aluno_pendente()
        ):
            return False
        return bool(registro_conclusao and not registro_conclusao.dt_avaliacao)

    def tem_pendencias(self):
        if self.data_finalizacao_conclusao:
            return False

        return bool(
            self.tem_registro_execucao_etapa_pendente()
            or self.tem_registro_gasto_pendente()
            or self.tem_registro_anexos_pendente()
            or self.tem_registro_foto_pendente()
            or self.tem_caracterizacao_pendente()
            or self.edital.exige_licoes_aprendidas
            and self.tem_registro_licoes_pendente()
            or self.tem_avaliacao_aluno_pendente()
        )

    def pode_reabrir_projeto(self):
        projeto_foi_finalizado = self.data_finalizacao_conclusao is not None
        return bool(self.is_gerente_sistemico() and not self.foi_cancelado() and projeto_foi_finalizado)

    def get_cronograma_desembolso(self):
        return self.desembolso_set.all().order_by('despesa', 'ano__ano', 'mes')

    def get_responsavel(self):
        for participacao in self.participacao_set.all():
            if participacao.responsavel:
                return participacao.vinculo_pessoa
        return None

    def get_vinculo_responsavel(self):
        for participacao in self.participacao_set.all():
            if participacao.responsavel:
                return participacao.vinculo

    total_planejado = None

    def get_total_planejado(self):
        if not self.total_planejado:
            # Depois de relacionar o modelo RegistroGasto com o modelo Desembolso, usar este como planejado e não RegistroGasto
            self.total_planejado = (
                Etapa.objects.filter(meta__projeto__id=self.pk).count() + RegistroGasto.objects.filter(item__projeto__id=self.pk).count()
            )
            if self.get_registro_conclusao():
                self.total_planejado += 1
        return self.total_planejado

    total_avaliado = None

    def get_total_avaliado(self):
        if not self.total_avaliado:
            self.total_avaliado = (
                RegistroExecucaoEtapa.objects.filter(etapa__meta__projeto__id=self.pk, dt_avaliacao__isnull=False).count()
                + RegistroGasto.objects.filter(item__projeto__id=self.pk, dt_avaliacao__isnull=False).count()
            )
            registro = self.get_registro_conclusao()
            if registro and registro.dt_avaliacao:
                self.total_avaliado += 1
        return self.total_avaliado

    total_executado = None

    def get_total_executado(self):
        if not self.total_executado:
            self.total_executado = (
                RegistroExecucaoEtapa.objects.filter(etapa__meta__projeto__id=self.pk).count()
                + RegistroGasto.objects.filter(item__projeto__id=self.pk).count()
            )
            if self.get_registro_conclusao():
                self.total_executado += 1
        return self.total_executado

    def get_proporcao_execucao(self):
        return f'{self.get_total_executado()}/{self.get_total_planejado()}'

    def get_proporcao_avaliacao(self):
        return f'{self.get_total_avaliado()}/{self.get_total_executado()}'

    def get_percentual_executado(self):
        total = self.get_total_planejado()
        if total == 0:
            total = 1
        return int(self.get_total_executado() * 100 / total)

    def get_percentual_avaliado(self):
        total = self.get_total_executado()
        if total == 0:
            total = 1
        return int(self.get_total_avaliado() * 100 / total)

    def get_participacoes_alunos(self):
        return list(self.participacao_set.filter(vinculo_pessoa__tipo_relacionamento__model='aluno'))

    def get_participacoes_servidores(self):
        return list(self.participacao_set.filter(vinculo_pessoa__tipo_relacionamento__model='servidor').order_by('-responsavel'))

    def eh_participante(self, user=None):
        if not user:
            user = tl.get_user()

        return self.participacao_set.filter(vinculo_pessoa=user.get_vinculo(), ativo=True).exists()

    def pode_acessar_projeto(self, user=None):
        if not user:
            user = tl.get_user()

        return self.participacao_set.filter(vinculo_pessoa=user.get_vinculo()).exists()

    def pode_imprimir(self, user: User | None = None) -> bool:
        """Critério de acesso da view ``projeto`` mais quem as listagens do módulo já levam ao projeto.

        Como na view, o Visualizador de Projetos de Ensino vê todos os projetos; o Visualizador de Projetos
        é da Extensão e não entra. Acrescenta o Integrante da Comissão de Acompanhamento (projetos do próprio
        campus). O Coordenador de Projetos de Ensino vale nos campi adicionais.
        """
        user = user or tl.get_user()
        if (
            user.has_perm('projetos_ensino.pode_gerenciar_edital')
            or user.has_perm('projetos_ensino.pode_avaliar_projeto')
            or user.has_group_cached(['Visualizador de Projetos de Ensino', 'Coordenador de Curso'])
        ):
            return True
        if user.has_group_cached('Coordenador de Projetos de Ensino') and self.uo_id in CampusAdicional.get_campi_user(
            user, retornar_apenas_ids=True
        ):
            return True
        if user.has_group_cached('Integrante da Comissão de Acompanhamento') and self.uo == get_uo(user):
            return True
        vinculo = user.get_vinculo()
        # o coordenador (`is_responsavel`) também tem participação: coberto por `pode_acessar_projeto`
        return bool(vinculo and vinculo == self.vinculo_monitor) or self.pode_acessar_projeto(user)

    def get_participacoes_alunos_ativos(self):
        return list(self.participacao_set.filter(ativo=True, vinculo_pessoa__tipo_relacionamento__model='aluno'))

    def get_participacoes_servidores_ativos(self):
        return list(self.participacao_set.filter(ativo=True, vinculo_pessoa__tipo_relacionamento__model='servidor'))

    def get_participacoes_colaboradores(self):
        return list(self.participacao_set.filter(ativo=True, vinculo_pessoa__tipo_relacionamento__model='prestadorservico'))

    def get_registro_conclusao(self):
        qs = self.registroconclusaoprojeto_set.all()
        if qs.exists():
            return qs[0]
        else:
            return None

    def tem_registro_execucao_etapa_pendente(self):
        """
        Verifica se para este projeto há registro de execução de atividade não avaliado ou não há execucação de atividade registrada.
        """
        qs_ha_registro_atividade__nao_avaliada = RegistroExecucaoEtapa.objects.filter(etapa__meta__projeto=self, avaliador__isnull=True)
        qs_ha_atividade_sem_registro = Etapa.objects.filter(meta__projeto=self, registroexecucaoetapa__isnull=True)
        return bool(qs_ha_registro_atividade__nao_avaliada.exists() or qs_ha_atividade_sem_registro.exists())

    def tem_registro_gasto_pendente(self, nao_avaliado=False):
        """
        Verifica se para este projeto há registro de gastos não avaliado ou não há gastos registrados.
        """
        desembolsos = Desembolso.objects.filter(projeto=self)
        if not desembolsos.exists():
            return False
        for desembolso in desembolsos:
            if not RegistroGasto.objects.filter(desembolso=desembolso).exists():
                return True
        qs = RegistroGasto.objects.filter(item__projeto=self)
        if qs.exists():
            return qs.filter(dt_avaliacao__isnull=True).exists()
        return True

    def tem_registro_foto_pendente(self):
        """
        Verifica se para este projeto há registro de fotos.
        """
        return not FotoProjeto.objects.filter(projeto=self).exists()

    def tem_registro_anexos_pendente(self):
        """
        Verifica se para este projeto há registro de anexos.
        """
        if self.projetoanexo_set.exists():
            for anexo in self.projetoanexo_set.all():
                if anexo.vinculo_membro_equipe and not anexo.arquivo and anexo.anexo_edital:
                    if Participacao.objects.filter(vinculo_pessoa=anexo.vinculo_membro_equipe, projeto=self, ativo=True).exists():
                        return True
        return False

    def tem_registro_licoes_pendente(self):
        """
        Verifica se para este projeto há registro de lições aprendidas.
        """
        if not self.edital.exige_licoes_aprendidas:
            return False
        return not LicaoAprendida.objects.filter(projeto=self).exists()

    def tem_caracterizacao_pendente(self):
        """
        Verifica se para este projeto não foi informada a quantidade de beneficiários atendidas.
        """
        return bool(self.caracterizacaobeneficiario_set.filter(quantidade_atendida__isnull=True).exists())

    def tem_avaliacao_aluno_pendente(self):
        if not self.edital.exige_avaliacao_aluno:
            return False
        alunos_ativos = self.get_participacoes_alunos_ativos()
        return any(not AvaliacaoAluno.objects.filter(participacao=aluno, tipo_avaliacao=AvaliacaoAluno.FINAL).exists() for aluno in alunos_ativos)

    def get_absolute_url(self):
        return f'/projetos_ensino/projeto/{self.id}/'

    def get_visualizar_projeto_url(self):
        return f'{settings.SITE_URL}{self.get_absolute_url()}'

    def edicao_inscricao(self):
        status = self.get_status()
        return bool(self.is_gerente_sistemico() or self.is_coordenador() and status == Projeto.STATUS_EM_INSCRICAO)

    def edicao_inscricao_execucao(self):
        status = self.get_status()
        return bool(self.is_coordenador() and (status == Projeto.STATUS_EM_INSCRICAO or status == Projeto.STATUS_EM_EXECUCAO))

    def pode_editar_inscricao_execucao(self):
        return bool(self.edicao_inscricao_execucao() and not self.data_finalizacao_conclusao)

    def pode_anexar_arquivo_do_membro(self):
        return bool(
            (self.edicao_inscricao_execucao() or self.edital.is_periodo_antes_pre_selecao())
            and not self.data_finalizacao_conclusao
            and self.is_coordenador()
        )

    def pode_adicionar_fotos_e_anexos(self):
        return bool(self.edicao_inscricao_execucao() and not self.data_finalizacao_conclusao and self.is_coordenador())

    def pode_editar_e_remover_projeto(self):
        return bool(self.get_periodo() == self.PERIODO_INSCRICAO and self.is_coordenador())

    def selecao_ja_divulgada(self):
        return self.edital.divulgacao_selecao <= datetime.datetime.now()

    def pode_registrar_execucao(self):
        user = tl.get_user()
        status = self.get_status()
        return bool(self.selecao_ja_divulgada() and (self.is_responsavel(user) and status == Projeto.STATUS_EM_EXECUCAO))

    def projeto_em_avaliacao(self):
        return bool(datetime.datetime.today() >= self.edital.inicio_pre_selecao and datetime.datetime.today() <= self.edital.fim_selecao)

    def avaliador_pode_visualizar(self):
        user = tl.get_user()
        return not (AvaliadorIndicado.objects.filter(projeto=self, vinculo=user.get_vinculo()).exists() and self.projeto_em_avaliacao())

    def pode_pre_selecionar(self, user: User | None = None) -> bool:
        """Só o Coordenador de Projetos de Ensino dos campi do usuário pré-seleciona (#17579).

        O Integrante da Comissão de Acompanhamento e o Monitor têm `pode_monitorar_projeto` (`is_pre_avaliador`),
        mas não pré-selecionam: a tela não lhes oferece os botões e a view os recusa.
        """
        user = user or tl.get_user()
        return user.has_group_cached('Coordenador de Projetos de Ensino') and self.uo_id in CampusAdicional.get_campi_user(
            user, retornar_apenas_ids=True
        )

    def pode_ser_pre_rejeitado(self) -> bool:
        periodo = self.get_periodo()
        if self.pode_pre_selecionar() and periodo == Projeto.PERIODO_PRE_SELECAO and self.data_conclusao_planejamento:
            if self.data_pre_avaliacao is None:
                return True
            if self.pre_aprovado:
                return True
        return False

    def pode_ser_pre_aprovado(self) -> bool:
        periodo = self.get_periodo()
        if self.pode_pre_selecionar() and periodo == Projeto.PERIODO_PRE_SELECAO and self.data_conclusao_planejamento:
            if self.data_pre_avaliacao is None:
                return True
            if not self.pre_aprovado:
                return True
        return False

    def pode_receber_pre_avaliacao(self, rejeitar: bool | None) -> bool:
        """O que a tela de pré-seleção exige para oferecer a ação, conferido também pela view (#17579).

        `rejeitar=True` é "Não Selecionar"; `False`/`None` é "Pré-selecionar", que exige vaga na cota.
        No fluxo contínuo, `get_periodo` tira da pré-seleção o projeto já pré-avaliado.
        """
        if rejeitar:
            return self.pode_ser_pre_rejeitado()
        return self.pode_ser_pre_aprovado() and self.pode_pre_aprovar()

    def exibir_acao_pre_rejeitar(self):
        if self.pode_ser_pre_rejeitado():
            if self.edital.tipo_edital == Edital.ENSINO_CONTINUO:
                if self.data_pre_avaliacao:
                    return ''  # edital de fluxo contínuo uma vez pré-rejeitado não poderá mais ser pré-avaliado.
                else:
                    return f'<a class="confirm btn danger" data-confirm="Deseja realmente não selecionar este projeto? Esta operação não poderá ser desfeita." href="/projetos_ensino/pre_rejeitar/{self.id}/">Não Selecionar</a>'
            return f'<a class="btn danger" href="/projetos_ensino/pre_rejeitar/{self.id}/">Não Selecionar</a>'
        return ''

    def pode_devolver_projeto(self):
        existe_envio = Projeto.objects.filter(pk=self.id, data_conclusao_planejamento__isnull=False)
        periodo = self.get_periodo()
        tem_permissao_para_devolver = self.is_pre_avaliador()

        if tem_permissao_para_devolver and existe_envio.exists() and self.pre_aprovado is False:
            if self.edital.tipo_edital == Edital.ENSINO_CONTINUO and self.edital.is_periodo_inscricao() or periodo == Projeto.PERIODO_INSCRICAO:
                return True
        return False

    def exibir_acao_pre_aprovar(self):
        if self.pode_ser_pre_aprovado():
            if self.edital.tipo_edital == Edital.ENSINO_CONTINUO:
                if self.data_pre_avaliacao:
                    return ''  # edital de fluxo contínuo uma vez pré-aprovado não poderá mais ser pré-avaliado.
                return f'<a class="confirm btn success" data-confirm="Deseja realmente selecionar este projeto? Esta operação não poderá ser desfeita." href="/projetos_ensino/pre_selecionar/{self.id}/">Pré-selecionar </a>'
            return f'<a class="btn success" href="/projetos_ensino/pre_selecionar/{self.id}/">Pré-selecionar</a>'
        return ''

    def pode_adicionar_memoria_calculo(self):
        if self.eh_participante() and not self.is_coordenador():
            return False

        status = self.get_status()
        return self.is_gerente_sistemico() or (
            self.is_responsavel() and (status == Projeto.STATUS_EM_INSCRICAO or status == Projeto.STATUS_EM_EXECUCAO)
        )

    def pode_exibir_opcoes(self):
        if self.is_coordenador() or self.is_avaliador():
            if not self.get_registro_conclusao():
                return True
        return False

    def pode_enviar_projeto(self):
        periodo = self.get_periodo()

        pode_enviar = (periodo == self.PERIODO_INSCRICAO) or (periodo == self.PERIODO_EXECUCAO)
        return bool(self.is_coordenador() and pode_enviar and not self.data_conclusao_planejamento)

    def pode_emitir_parecer(self):
        return bool(self.is_pre_avaliador() and self.data_finalizacao_conclusao and not self.registroconclusaoprojeto_set.all()[0].dt_avaliacao)

    def pode_aprovar_projeto(self):
        return self.edital.is_periodo_selecao_e_pre_divulgacao() and self.aprovado == self.aprovado_na_distribuicao

    def eh_somente_leitura(self):
        if self.data_finalizacao_conclusao or self.foi_cancelado() or self.inativado:
            return True
        periodo = self.get_periodo()
        return bool(periodo != Projeto.PERIODO_EXECUCAO and self.data_conclusao_planejamento)

    @property
    def participacao_por_vinculo(self):
        return self.participacao_set.order_by('vinculo')

    def form_gerenciar_bolsas(self):
        class CustomForm(forms.FormPlus):
            fieldsets = (
                (
                    'titulo',
                    {
                        'fields': (
                            'item_1',
                            'item_2',
                            'item_3',
                        )
                    },
                ),
            )

    def get_avaliadores(self):
        return AvaliadorIndicado.objects.filter(projeto=self)

    def get_avaliacoes(self):
        return self.avaliacao_set.all()

    def get_pontuacao_total(self):
        soma = Decimal(0)
        parametros = ParametroProjeto.objects.filter(projeto=self)

        for parametro in parametros:
            soma = soma + parametro.get_pontuacao_parametro()

        return soma

    def foi_cancelado(self):
        return ProjetoCancelado.objects.filter(projeto=self, data_avaliacao__isnull=False, cancelado=True).exists()

    def pode_cancelar_projeto(self):
        user = tl.get_user()
        status = self.get_status()
        tem_solicitacao_cancelamento = ProjetoCancelado.objects.filter(projeto=self).exists()
        projeto_esta_em_execucao = self.get_periodo() == Projeto.PERIODO_EXECUCAO
        return bool(
            self.is_responsavel(user)
            and status != Projeto.STATUS_CONCLUIDO
            and status != Projeto.STATUS_INATIVADO
            and not tem_solicitacao_cancelamento
            and projeto_esta_em_execucao
        )

    def pode_mostrar_dados_selecao(self):
        # Não há editais de extensão em projetos_ensino (apenas ENSINO/ENSINO_CONTINUO);
        # a comparação herdada de pesquisa/projetos referenciava Edital.EXTENSAO (inexistente aqui),
        # levantando AttributeError. Mantém-se o método por paridade de API, retornando False.
        return False

    def get_data_historico_equipe(self):
        if datetime.date.today() > self.inicio_execucao:
            data_movimentacao = datetime.datetime.today()
        else:
            data_movimentacao = self.inicio_execucao

        return data_movimentacao

    def tem_aluno(self):
        for participacao in self.participacao_set.filter(ativo=True):
            if not participacao.vinculo_pessoa or participacao.vinculo_pessoa.eh_aluno():
                return True
        return False

    def tem_atividade_com_prazo_expirado(self):
        hoje = datetime.datetime.now().date()

        return Etapa.objects.filter(meta__projeto=self, fim_execucao__lte=hoje, registroexecucaoetapa__isnull=True).exists()

    def foi_selecionado_fora_do_prazo(self):
        return ProjetoCancelado.objects.filter(proximo_projeto=self).exists()

    def get_data_selecao_fora_do_prazo(self):
        return ProjetoCancelado.objects.get(proximo_projeto=self).data_avaliacao

    def get_projeto_desistencia(self):
        return ProjetoCancelado.objects.get(proximo_projeto=self).projeto.titulo

    def tem_pre_avaliador_na_equipe(self):
        return any(membro.pessoa.user.has_perm('projetos_ensino.pode_pre_avaliar_projeto') for membro in self.participacao_por_vinculo)

    def tem_registro_gasto_registrado(self):
        return RegistroGasto.objects.filter(desembolso__in=self.desembolso_set.all()).exists()

    def pode_pre_aprovar(self) -> bool:
        oferta = self.edital.ofertaprojeto_set.filter(uo=self.uo).first()
        if not oferta:
            return False  # sem oferta no campus não há cota: na tela, o `.get` falhava em silêncio (#17579)
        return not oferta.qtd_aprovados - self.edital.num_total_projetos_pre_aprovados(self.uo) <= 0

    def pre_avaliador_integra_equipe(self):
        if not self.autor_pre_avaliacao:
            return False

        return self.participacao_set.filter(pessoa=self.autor_pre_avaliacao).exists()

    def pode_enviar_recurso(self):
        hoje = datetime.datetime.now()
        if self.edital.inicio_recurso and self.edital.is_periodo_pos_selecao() and self.pre_aprovado:
            ja_enviou_recurso = RecursoProjeto.objects.filter(projeto=self).exists()
            return (self.edital.fim_recurso > hoje) and (self.edital.inicio_recurso < hoje) and self.is_responsavel() and not ja_enviou_recurso
        else:
            return False

    def tem_rubrica_material_permanente(self):
        return RegistroGasto.objects.filter(desembolso__projeto=self, desembolso__despesa__codigo='449052', aprovado=True).exists()

    def tem_rubrica_para_doacao(self):
        return RegistroGasto.objects.filter(
            Q(aprovado=True),
            Q(desembolso__projeto=self),
            Q(desembolso__despesa__codigo='449052'),
            Q(arquivo_termo_cessao='') | Q(arquivo_termo_cessao__isnull=True),
        ).exists()

    def pode_remover_projeto(self):
        return bool(
            self.get_periodo() == self.PERIODO_INSCRICAO
            and self.is_coordenador()
            and not self.eh_somente_leitura()
            or self.get_status() == self.STATUS_NAO_ENVIADO
            and self.is_coordenador()
        )

    def pode_editar_projeto(self):
        return bool(
            self.get_periodo() in [self.PERIODO_INSCRICAO, self.PERIODO_EXECUCAO]
            and self.is_coordenador()
            and not self.foi_cancelado()
            and not self.registroconclusaoprojeto_set.filter(dt_avaliacao__isnull=False)
            or self.get_status() in [self.STATUS_EM_INSCRICAO, self.STATUS_EM_EXECUCAO]
            and self.is_coordenador()
            and not self.foi_cancelado()
            and not self.registroconclusaoprojeto_set.filter(dt_avaliacao__isnull=False)
        )

    def tem_anexos_equipe(self):
        return self.projetoanexo_set.filter(descricao__isnull=True).exists()

    def tem_outros_anexos(self):
        return self.projetoanexo_set.filter(descricao__isnull=False).exists()

    def notas_itens_avaliacoes(self):
        vqs = (
            Avaliacao.objects.filter(projeto=self, projeto__pre_aprovado=True)
            .values('projeto__id', 'itemavaliacao__criterio_avaliacao')
            .annotate(criterio_sum_pontos=Sum('itemavaliacao__pontuacao'))
            .values('projeto__id', 'projeto__pontuacao', 'criterio_sum_pontos', 'itemavaliacao__criterio_avaliacao__ordem_desempate')
            .order_by('-projeto__pontuacao', 'itemavaliacao__criterio_avaliacao__ordem_desempate')
        )
        notas = []
        for item in vqs:
            notas.append((item['criterio_sum_pontos'], item['itemavaliacao__criterio_avaliacao__ordem_desempate']))
        return notas

    def pendente_avaliacao(self):
        user = tl.get_user()
        return not Avaliacao.objects.filter(projeto=self, vinculo=user.get_vinculo()).exists()

    def pode_ser_inativado(self):
        hoje = datetime.datetime.now().date()
        return (self.inicio_execucao + relativedelta(years=2, months=1)) <= hoje

    def pode_cancelar_pre_avaliacao(self):
        if self.data_pre_avaliacao:
            if self.edital.tipo_edital == Edital.ENSINO:
                return not self.data_avaliacao
            return True
        return False

    def tem_atividade_ou_gasto_sem_validacao(self):
        return (
            RegistroExecucaoEtapa.objects.filter(etapa__meta__projeto=self, dt_avaliacao__isnull=True).exists()
            or RegistroGasto.objects.filter(desembolso__projeto=self, dt_avaliacao__isnull=True).exists()
        )

    def get_avaliadores_indicados(self):
        return AvaliadorIndicado.objects.filter(projeto=self).order_by('vinculo__pessoa')

    def tem_frequencia_aluno_pendente(self, participacao=None, data=None):
        participantes_alunos_bolsistas = self.participacao_set.filter(
            vinculo_pessoa__tipo_relacionamento__model='aluno', vinculo=TipoVinculo.BOLSISTA
        )
        if participacao:
            participantes_alunos_bolsistas = participantes_alunos_bolsistas.filter(id=participacao.id)

        for participacao in participantes_alunos_bolsistas:
            meses_atividades = set()
            meses_projeto = set()
            data_entrada = participacao.get_data_entrada()
            data_final = data or participacao.get_data_saida()
            if data_entrada and data_final:
                dateRange = [data_entrada, data_final]
                tmpTime = dateRange[0]
                oneWeek = timedelta(weeks=1)
                tmpTime = tmpTime.replace(day=1)
                dateRange[0] = tmpTime
                dateRange[1] = dateRange[1].replace(day=1)
                lastMonth = tmpTime.month
                meses_projeto.add(f'{tmpTime.month}/{tmpTime.year}')
                while tmpTime < dateRange[1]:
                    if lastMonth != 12:
                        while tmpTime.month <= lastMonth:
                            tmpTime += oneWeek
                        tmpTime = tmpTime.replace(day=1)
                        meses_projeto.add(f'{tmpTime.month}/{tmpTime.year}')
                        lastMonth = tmpTime.month

                    else:
                        while tmpTime.month >= lastMonth:
                            tmpTime += oneWeek
                        tmpTime = tmpTime.replace(day=1)
                        meses_projeto.add(f'{tmpTime.month}/{tmpTime.year}')
                        lastMonth = tmpTime.month

                for etapa in RegistroFrequencia.objects.filter(projeto=participacao.projeto, cadastrada_por=participacao.vinculo_pessoa):
                    dateRange = [etapa.data, etapa.data]
                    tmpTime = dateRange[0]
                    oneWeek = timedelta(weeks=1)
                    tmpTime = tmpTime.replace(day=1)
                    dateRange[0] = tmpTime
                    dateRange[1] = dateRange[1].replace(day=1)
                    lastMonth = tmpTime.month
                    meses_atividades.add(f'{tmpTime.month}/{tmpTime.year}')
                    while tmpTime < dateRange[1]:
                        if lastMonth != 12:
                            while tmpTime.month <= lastMonth:
                                tmpTime += oneWeek
                            tmpTime = tmpTime.replace(day=1)
                            meses_atividades.add(f'{tmpTime.month}/{tmpTime.year}')
                            lastMonth = tmpTime.month

                        else:
                            while tmpTime.month >= lastMonth:
                                tmpTime += oneWeek
                            tmpTime = tmpTime.replace(day=1)
                            meses_atividades.add(f'{tmpTime.month}/{tmpTime.year}')
                            lastMonth = tmpTime.month
                for item in meses_projeto:
                    if item not in meses_atividades:
                        return f'{participacao.vinculo_pessoa.pessoa.nome} sem registro em {item}'
                return False
        return False

    def tem_frequencia_com_validacao_pendente(self):
        alunos = self.participacao_set.filter(vinculo_pessoa__tipo_relacionamento__model='aluno')
        return bool(
            RegistroFrequencia.objects.filter(
                projeto=self, cadastrada_por__in=alunos.values_list('vinculo_pessoa', flat=True), validada_por__isnull=True
            ).exists()
        )

    @transaction.atomic
    def clonar_projeto(
        self, edital, clona_caracterizacao, clona_equipe, clona_atividade, clona_memoria_calculo, clona_desembolso, data_inicio, data_fim
    ):
        projeto_clonado = Projeto.objects.get(id=self.id)
        projeto_clonado.edital = edital
        projeto_clonado.id = None
        projeto_clonado.pre_aprovado = False
        projeto_clonado.data_pre_avaliacao = None
        projeto_clonado.vinculo_autor_pre_avaliacao = None
        projeto_clonado.aprovado = False

        projeto_clonado.pontuacao = 0
        projeto_clonado.data_conclusao_planejamento = None
        projeto_clonado.data_finalizacao_conclusao = None
        projeto_clonado.data_validacao_pontuacao = None
        projeto_clonado.vinculo_monitor = None
        projeto_clonado.classificacao = None

        projeto_clonado.inativado = False
        projeto_clonado.motivo_inativacao = None
        projeto_clonado.inativado_em = None
        projeto_clonado.inativado_por = None

        projeto_clonado.inicio_execucao = data_inicio
        projeto_clonado.fim_execucao = data_fim

        projeto_clonado.save()
        projeto_clonado.componentes.set(self.componentes.all())
        projeto_clonado.cursos.set(self.cursos.all())

        p = Participacao.objects.get(projeto=self, responsavel=True)
        p.id = None
        p.projeto = projeto_clonado
        p.save()
        Participacao.gerar_anexos_do_participante(p)
        p.adicionar_registro_historico_equipe(HistoricoEquipe.EVENTO_COORDENADOR_INSERIDO, data_evento=data_inicio)
        if clona_caracterizacao:
            for caracterizacao in CaracterizacaoBeneficiario.objects.filter(projeto=self):
                caracterizacao_clonada = CaracterizacaoBeneficiario(
                    tipo_beneficiario=caracterizacao.tipo_beneficiario,
                    descricao_beneficiario=caracterizacao.descricao_beneficiario,
                    quantidade=caracterizacao.quantidade,
                    projeto=projeto_clonado,
                )
                caracterizacao_clonada.save()

        if clona_equipe:
            for membro in Participacao.objects.filter(projeto=self, responsavel=False, ativo=True):
                membro_clonado = Participacao(
                    projeto=projeto_clonado,
                    vinculo_pessoa=membro.vinculo_pessoa,
                    vinculo=membro.vinculo,
                    carga_horaria=membro.carga_horaria,
                    bolsa_concedida=membro.bolsa_concedida,
                )
                membro_clonado.save()
                if membro.vinculo_pessoa:
                    if membro.vinculo_pessoa.eh_aluno():
                        membro_clonado.adicionar_registro_historico_equipe(HistoricoEquipe.EVENTO_ADICIONAR_ALUNO, data_evento=data_inicio)
                    elif membro.vinculo_pessoa.eh_servidor():
                        membro_clonado.adicionar_registro_historico_equipe(HistoricoEquipe.EVENTO_ADICIONAR_SERVIDOR, data_evento=data_inicio)
                    else:
                        membro_clonado.adicionar_registro_historico_equipe(HistoricoEquipe.EVENTO_ADICIONAR_COLABORADOR, data_evento=data_inicio)
                    Participacao.gerar_anexos_do_participante(membro_clonado)

        if clona_atividade:
            for meta in Meta.objects.filter(projeto=self):
                meta_clonada = Meta(projeto=projeto_clonado, ordem=meta.ordem, descricao=meta.descricao)
                meta_clonada.save()
                for etapa in Etapa.objects.filter(meta=meta):
                    etapa_clonada = Etapa(
                        meta=meta_clonada,
                        ordem=etapa.ordem,
                        descricao=etapa.descricao,
                        unidade_medida=etapa.unidade_medida,
                        qtd=etapa.qtd,
                        indicadores_qualitativos=etapa.indicadores_qualitativos,
                        responsavel=p,
                        inicio_execucao=etapa.inicio_execucao,
                        fim_execucao=etapa.fim_execucao,
                    )
                    etapa_clonada.save()

        if clona_memoria_calculo:
            for memoria in ItemMemoriaCalculo.objects.filter(projeto=self):
                if Recurso.objects.filter(edital=edital, despesa=memoria.despesa):
                    memoria_clonada = ItemMemoriaCalculo(
                        projeto=projeto_clonado,
                        despesa=memoria.despesa,
                        descricao=memoria.descricao,
                        unidade_medida=memoria.unidade_medida,
                        qtd=memoria.qtd,
                        valor_unitario=memoria.valor_unitario,
                        origem=memoria.origem,
                    )
                    memoria_clonada.save()
                    if clona_desembolso:
                        for desembolso in Desembolso.objects.filter(item=memoria):
                            desembolso_clonado = Desembolso(
                                projeto=projeto_clonado,
                                ano=desembolso.ano,
                                mes=desembolso.mes,
                                despesa=desembolso.despesa,
                                valor=desembolso.valor,
                                data_cadastro=projeto_clonado.inicio_execucao,
                                item=memoria_clonada,
                            )
                            desembolso_clonado.save()

        return projeto_clonado

    @transaction.atomic
    def save(self, *args, **kwargs):
        if tl.get_user() is not None and not self.vinculo_coordenador:
            self.vinculo_coordenador = tl.get_user().get_vinculo()
        super().save(args, kwargs)


class TipoBeneficiario(models.ModelPlus):
    descricao = models.CharFieldPlus('Tipo de beneficiário', max_length=255)
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Tipo de beneficiário'
        verbose_name_plural = 'Tipos de beneficiários'

    def __str__(self):
        return self.descricao


class CaracterizacaoBeneficiario(models.ModelPlus):
    tipo_beneficiario = models.ForeignKeyPlus(TipoBeneficiario, verbose_name='Tipo de beneficiário')
    projeto = models.ForeignKeyPlus(Projeto)
    quantidade = models.IntegerField()
    quantidade_atendida = models.IntegerField(null=True, verbose_name='Quantidade Atendida')
    descricao_beneficiario = models.CharFieldPlus('Descreva os Beneficiários do Público-Alvo', max_length=2000, null=True, blank=True)

    class Meta:
        unique_together = ('tipo_beneficiario', 'projeto')

    def __str__(self):
        return f'Caracterização do Projeto: {self.projeto}'


class AvaliadorIndicado(models.ModelPlus):
    projeto = models.ForeignKeyPlus(Projeto, on_delete=models.CASCADE)
    vinculo = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Avaliador', related_name='projetoensino_avaliadorindicado', on_delete=models.CASCADE, null=True
    )

    class Meta:
        verbose_name = 'Avaliador'
        verbose_name_plural = 'Avaliadores'

    def __str__(self):
        return f'Avaliador do Projeto: {self.projeto}'

    def ja_avaliou(self):
        return Avaliacao.objects.filter(vinculo=self.vinculo, projeto=self.projeto).exists()

    def get_avaliacao(self):
        if Avaliacao.objects.filter(vinculo=self.vinculo, projeto=self.projeto).exists():
            return Avaliacao.objects.filter(vinculo=self.vinculo, projeto=self.projeto)[0]
        return None

    def qtd_indicacoes_no_edital(self):
        return AvaliadorIndicado.objects.filter(vinculo=self.vinculo, projeto__edital=self.projeto.edital).count()

    def get_instituicao(self):
        avaliador = AvaliadorExterno.objects.filter(vinculo=self.vinculo)
        if avaliador.exists():
            return avaliador[0].instituicao_origem
        return None

    def get_email(self):
        # AvaliadorExterno tem e-mail de contato próprio; senão, delega ao resolvedor do vínculo.
        avaliador = AvaliadorExterno.objects.filter(vinculo=self.vinculo)
        if avaliador.exists():
            return avaliador[0].email
        return self.vinculo.email_notificacao

    def get_telefone(self):
        avaliador = AvaliadorExterno.objects.filter(vinculo=self.vinculo)
        if avaliador.exists():
            return avaliador[0].telefone
        elif self.vinculo.eh_servidor():
            return self.vinculo.relacionamento.pessoa_fisica.telefones
        return None

    def get_lattes(self):
        avaliador = AvaliadorExterno.objects.filter(vinculo=self.vinculo)
        if avaliador.exists():
            return avaliador[0].lattes
        elif self.vinculo.eh_servidor():
            return self.vinculo.relacionamento.lattes
        return None


class Avaliacao(models.ModelPlus):
    projeto = models.ForeignKeyPlus(Projeto, on_delete=models.CASCADE)
    vinculo = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Avaliador', on_delete=models.CASCADE, null=True, related_name='projetoensino_vinculo_avaliador'
    )
    data = models.DateTimeFieldPlus('Data', auto_now=True)
    parecer = models.TextField()
    pontuacao = models.DecimalFieldPlus('Pontuação')

    class Meta:
        verbose_name = 'Avaliação'
        verbose_name_plural = 'Avaliações'
        unique_together = ('projeto', 'vinculo')

    def __str__(self):
        return f'Avaliação do Projeto: {self.projeto}'

    def delete(self):
        qs_avaliacoes = self.projeto.avaliacao_set.exclude(id=self.id)
        self.atualiza_pontuacao_projeto(qs_avaliacoes)
        super().delete()

    def save(self):
        self.pontuacao = Decimal('0')
        if self.pk:
            for item in self.itemavaliacao_set.all():
                self.pontuacao += item.pontuacao
        super().save()
        qs_avaliacoes = Avaliacao.objects.filter(projeto=self.projeto)
        self.atualiza_pontuacao_projeto(qs_avaliacoes)

    def atualiza_pontuacao_projeto(self, qs_avaliacoes):
        # atualizar pontuação do projeto caso haja mais de uma avaliação
        # projetos avaliados por um único avaliador continuarão com nota 0 (zero)
        self.pontua_projetos_extensao(qs_avaliacoes)

    def pontua_projetos_extensao(self, qs_avaliacoes):
        if qs_avaliacoes.count() > 1:
            total = Decimal('0')
            for avaliacao in qs_avaliacoes:
                total += avaliacao.pontuacao
            self.projeto.pontuacao = total / qs_avaliacoes.count()
        else:
            self.projeto.pontuacao = 0
            self.projeto.aprovado = False
        self.projeto.data_avaliacao = datetime.datetime.now()
        self.projeto.save()
        self.projeto.edital.classifica_projetos_extensao(self.projeto.uo)

    def tem_nota_alterada(self):
        return ItemAvaliacao.objects.filter(avaliacao=self, pontuacao_original__isnull=False).exists()


class ItemAvaliacao(models.ModelPlus):
    avaliacao = models.ForeignKeyPlus(Avaliacao)
    criterio_avaliacao = models.ForeignKeyPlus(
        CriterioAvaliacao, verbose_name='Critério', on_delete=models.CASCADE, related_name='projetoensino_criterio'
    )
    pontuacao = models.DecimalFieldPlus('Pontuação')
    pontuacao_original = models.DecimalFieldPlus('Pontuação Original', null=True, blank=True)
    vinculo_responsavel_alteracao = models.ForeignKey(
        'comum.Vinculo',
        related_name='projetoensino_vinculo_responsavel_alteracao_nota',
        verbose_name='Responsável pela Alteração',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    data_alteracao = models.DateTimeFieldPlus('Data da Alteração', null=True, blank=True)
    recurso = models.ForeignKeyPlus(
        'projetos_ensino.RecursoProjeto',
        verbose_name='Recurso que Motivou a Alteração',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='projetoensino_recurso',
    )

    def __str__(self):
        return f'Item da Avaliação: {self.avaliacao}'


class ItemMemoriaCalculo(models.ModelPlus):
    projeto = models.ForeignKeyPlus(Projeto, on_delete=models.CASCADE)
    despesa = models.ForeignKeyPlus(NaturezaDespesa, verbose_name='Despesa', on_delete=models.CASCADE, related_name='projetoensino_item_despesa')
    descricao = models.TextField('Descrição', max_length=2014)
    unidade_medida = models.CharField('Unidade de Medida', max_length=50)
    qtd = models.PositiveIntegerField('Quantidade')
    valor_unitario = models.DecimalFieldPlus('Valor Unitário (R$)')
    data_cadastro = models.DateFieldPlus('Data de Cadastro do Item de Mémoria de Cálculo', null=True, blank=True, default=datetime.datetime.now)
    origem = models.CharField('Origem do recurso', max_length=255, null=True, blank=True)
    objects = ItemMemoriaCalculoManager()

    class Meta:
        verbose_name = 'Item de Memória de Cálculo'
        verbose_name_plural = 'Itens de Memória de Cálculo'

    def get_subtotal(self):
        return self.qtd * self.valor_unitario

    def get_total_executado(self):
        total = Decimal('0.0')
        registros = RegistroGasto.objects.filter(desembolso__item=self)
        for registro in registros:
            total += registro.get_subtotal()
        return total

    def get_registros_gastos(self):
        return self.registrogasto_set.all().order_by('ano').order_by('mes')

    def pode_editar_e_remover_memoria_calculo(self):
        if self.projeto.is_gerente_sistemico():
            return True
        gastos_registrados = RegistroGasto.objects.filter(desembolso__item=self, avaliador__isnull=False).exists()
        if gastos_registrados:
            return False
        status = self.projeto.get_status()
        if self.projeto.is_responsavel() and (status == Projeto.STATUS_EM_INSCRICAO or status == Projeto.STATUS_EM_EXECUCAO):
            if not self.projeto.get_registro_conclusao() and not eh_planejamento(self):
                return True
        return False

    def eh_planejamento(self):
        return eh_planejamento(self)

    def tem_desembolso_registrado(self):
        status = self.projeto.get_status()
        if status != Projeto.STATUS_EM_INSCRICAO:
            return True
        return self.desembolso_set.exists()

    def __str__(self):
        return f'{self.despesa} / {self.origem} - {self.descricao}'


class ParametroProjeto(models.ModelPlus):
    projeto = models.ForeignKeyPlus(Projeto, on_delete=models.CASCADE)
    parametro_edital = models.ForeignKeyPlus(ParametroEdital, on_delete=models.CASCADE)
    quantidade = models.PositiveIntegerField('Quantidade', default=0)

    class Meta:
        verbose_name = 'Critério do Projeto'
        verbose_name_plural = 'Critérios do Projeto'
        ordering = ['parametro_edital__parametro__id']

    def __str__(self):
        return f'{self.projeto}'

    def get_pontuacao_parametro(self):
        return self.quantidade * self.parametro_edital.valor_parametro

    def get_form_field(self, initial):
        return forms.DecimalField(
            label=f'{self.parametro_edital.parametro.codigo} - {self.parametro_edital.parametro.descricao}',
            widget=forms.TextInput(attrs={'readonly': 'True'}),
            initial=initial or 10,
        )


class Desembolso(models.ModelPlus):
    SEARCH_FIELDS = ['despesa__nome', 'despesa__codigo', 'item__descricao']
    projeto = models.ForeignKeyPlus(Projeto, verbose_name='Projeto', on_delete=models.CASCADE)
    ano = models.ForeignKeyPlus('comum.Ano', verbose_name='Ano', on_delete=models.CASCADE, related_name='projetoensino_desembolso_ano')
    mes = models.PositiveIntegerField(
        'Mês',
        choices=[[1, '1'], [2, '2'], [3, '3'], [4, '4'], [5, '5'], [6, '6'], [7, '7'], [8, '8'], [9, '9'], [10, '10'], [11, '11'], [12, '12']],
        help_text='O mês 1 indica o primeiro mês do projeto',
    )
    despesa = models.ForeignKeyPlus(
        NaturezaDespesa, verbose_name='Despesa', on_delete=models.CASCADE, related_name='projetoensino_desembolso_despesa'
    )
    valor = models.DecimalFieldPlus('Valor (R$)')
    data_cadastro = models.DateFieldPlus('Data de Cadastro do Desembolso', null=True, blank=True)
    item = models.ForeignKeyPlus(ItemMemoriaCalculo, verbose_name='Mémoria de Cálculo', null=True, on_delete=models.CASCADE)

    def __str__(self):
        return f'Desembolso do Projeto: {self.projeto}'

    def save(self):
        if not self.id:
            self.data_cadastro = datetime.datetime.now()
        self.despesa = self.item.despesa
        super().save()

    class Meta:
        verbose_name = 'Desembolso'
        verbose_name_plural = 'Desembolsos'

    def get_valor_executado(self):
        total = Decimal(0)
        for registro in RegistroGasto.objects.filter(item__projeto__id=self.projeto.pk, desembolso=self):
            total += registro.get_subtotal()
        return total

    def get_valor_disponivel(self):
        return self.valor - self.get_valor_executado()

    def eh_planejamento(self):
        return eh_planejamento(self)

    def pode_editar_e_remover_desembolso(self):
        if self.projeto.is_gerente_sistemico():
            return True
        gastos_registrados = RegistroGasto.objects.filter(desembolso=self, avaliador__isnull=False).exists()
        if gastos_registrados:
            return False
        return bool(self.projeto.pode_editar_inscricao_execucao() and not self.eh_planejamento())

    def get_registros_gastos(self):
        return self.registrogasto_set.all().order_by('ano').order_by('mes')

    def tem_gasto_registrado(self):
        status = self.projeto.get_status()
        if status != Projeto.STATUS_EM_EXECUCAO:
            return True
        return self.registrogasto_set.exists()


class RegistroGasto(models.ModelPlus):
    item = models.ForeignKeyPlus(ItemMemoriaCalculo, on_delete=models.CASCADE)
    ano = models.ForeignKeyPlus('comum.Ano', verbose_name='Ano', on_delete=models.CASCADE, related_name='projetoensino_ano_gasto')
    mes = models.PositiveIntegerField(
        'Mês', choices=[[1, '1'], [2, '2'], [3, '3'], [4, '4'], [5, '5'], [6, '6'], [7, '7'], [8, '8'], [9, '9'], [10, '10'], [11, '11'], [12, '12']]
    )
    descricao = models.TextField(
        'Descrição',
        max_length=2014,
        help_text='Altere essa informação caso o produto/serviço/bolsa adiquirido(a)/pago(a) não tenha sido o definido na memória de cálculo',
    )
    qtd = models.PositiveIntegerField('Quantidade', help_text='Informe o número de ? adiquirido(a)/pago(a) no período (mês/ano) informado')
    valor_unitario = models.DecimalFieldPlus(
        'Valor Unitário (R$)',
        help_text='Altere essa informação caso o valor do produto/serviço/bolsa adiquirido(a)/pago(a) no período (mês/ano) informado não tenha sido igual ao definido na memória de cálculo',
    )
    observacao = models.TextField(
        'Observação',
        help_text='Insira alguma informação adicional referente à aquisição/pagamento do produto/serviço/bolsa caso ache necessário.',
        null=True,
        blank=True,
    )
    dt_avaliacao = models.DateFieldPlus(null=True)
    avaliador = models.ForeignKeyPlus(Servidor, null=True, on_delete=models.CASCADE, related_name='projetoensino_avaliador_gasto')
    aprovado = models.BooleanField(default=False)
    justificativa_reprovacao = models.CharField(
        'Justificativa da Reprovação do Gasto',
        max_length=250,
        null=True,
        blank=True,
        help_text='Informação adicional que você julgar relevante no que diz respeito à reprovação do gasto.',
    )
    desembolso = models.ForeignKeyPlus(Desembolso, null=True, on_delete=models.CASCADE)
    arquivo = models.PrivateFileField(max_length=255, upload_to='projetos_ensino/registrogasto/comprovantes/', null=True, blank=True)
    data_cadastro = models.DateFieldPlus(null=True)
    cotacao_precos = models.PrivateFileField(max_length=255, upload_to='projetos_ensino/registrogasto/comprovantes/', null=True, blank=True)
    arquivo_termo_cessao = models.PrivateFileField(max_length=255, upload_to='projetos_ensino/termo_cessao/', null=True, blank=True)
    obs_cessao = models.TextField('Observação', null=True, blank=True)

    def save(self):
        self.item = self.desembolso.item
        super().save()

    def get_subtotal(self):
        return self.qtd * self.valor_unitario

    def get_status(self):
        if self.dt_avaliacao:
            if self.aprovado:
                return 1
            else:
                return 3
        else:
            return 2

    def get_mensagem_avaliacao(self):
        return get_mensagem_avaliacao(self)

    def pode_editar_remover_registro_gasto(self):
        if self.desembolso.projeto.is_gerente_sistemico():
            return True
        return bool(not self.dt_avaliacao and self.desembolso.projeto.is_coordenador())

    def __str__(self):
        return f'{self.descricao} - (Mês: {self.mes} / Ano: {self.ano})'


class ProjetoAnexo(models.ModelPlus):
    projeto = models.ForeignKeyPlus(Projeto, on_delete=models.CASCADE)
    anexo_edital = models.ForeignKeyPlus(EditalAnexo, null=True, on_delete=models.CASCADE, related_name='projetoensino_anexo_projeto')
    arquivo = models.PrivateFileField(max_length=255, upload_to='projetos_ensino/projetoanexo/', null=True, blank=True)
    vinculo_membro_equipe = models.ForeignKeyPlus(
        'comum.Vinculo', null=True, verbose_name='Participante', on_delete=models.CASCADE, related_name='projetoensino_membro_anexo'
    )
    descricao = models.CharField('Descrição', max_length=255, null=True)
    cadastrado_em = models.DateTimeFieldPlus('Cadastrado em', auto_now_add=True, null=True)
    participacao = models.ForeignKeyPlus(
        'projetos_ensino.Participacao',
        null=True,
        verbose_name='Participação',
        on_delete=models.SET_NULL,
        related_name='projetoensino_participacao_projetoanexo',
    )

    class Meta:
        ordering = ['vinculo_membro_equipe__pessoa__nome']

    def __str__(self):
        return f'Anexo do Projeto: {self.projeto}'

    def get_nome(self):
        if self.vinculo_membro_equipe:
            return self.vinculo_membro_equipe.pessoa.nome
        elif self.participacao:
            return self.participacao.get_nome()
        return None


class EditalAnexoAuxiliar(models.ModelPlus):
    edital = models.ForeignKeyPlus(Edital, on_delete=models.CASCADE)
    nome = models.CharField('Nome', max_length=255)
    descricao = models.TextField('Descrição', blank=True)
    arquivo = models.PrivateFileField(max_length=255, upload_to='projetos_ensino/editalanexo/', null=True, blank=True)
    ordem = models.PositiveIntegerField('Ordem', help_text='Informe um número inteiro maior ou igual a 1')

    class Meta:
        ordering = ['ordem']

    def __str__(self):
        return f'{self.nome}: {self.descricao}'


class Meta(models.ModelPlus):
    projeto = models.ForeignKeyPlus(Projeto, verbose_name='Projeto', on_delete=models.CASCADE)
    ordem = models.PositiveIntegerField('Ordem', help_text='Informe um número inteiro maior ou igual a 1')
    descricao = models.TextField('Descrição')
    data_cadastro = models.DateFieldPlus('Data de Cadastro da Meta', null=True, blank=True, default=datetime.datetime.now)

    class Meta:
        verbose_name = 'Meta'
        verbose_name_plural = 'Metas'

    def __str__(self):
        return f'Meta {self.ordem} - {self.descricao}'

    def get_etapas(self):
        return self.etapa_set.all().order_by('ordem')

    def get_periodo_meta(self):
        periodo = ''
        if self.etapa_set.exists():
            inicio = self.etapa_set.all().order_by('inicio_execucao')[0].inicio_execucao.strftime('%d/%m/%y')
            fim = self.etapa_set.latest('fim_execucao').fim_execucao.strftime('%d/%m/%y')
            periodo = ' - ' + str(inicio) + ' até ' + str(fim)
        return periodo

    def tem_etapas_aprovadas(self):
        return RegistroExecucaoEtapa.objects.filter(etapa__meta=self, aprovado=True).exists()

    def eh_planejamento(self):
        return eh_planejamento(self)

    def pode_editar_e_remover_meta(self):
        if self.projeto.eh_somente_leitura():
            return False
        return bool(not self.tem_etapas_aprovadas() and self.projeto.is_coordenador() and not self.eh_planejamento())


class RegistroExecucaoEtapa(models.ModelPlus):
    ATENDIDO = '1'
    ATENDIDO_PARCIALMENTE = '2'
    NAO_ATENTIDO = '3'
    TIPO_INDICADOR_QUALITATIVO = (
        (ATENDIDO, 'Atendido'),
        (ATENDIDO_PARCIALMENTE, 'Atendido Parcialmente'),
        (NAO_ATENTIDO, 'Não Atendido'),
    )
    tipo_indicador_qualitativo = models.CharField('Indicadores Qualitativos', max_length=1, choices=TIPO_INDICADOR_QUALITATIVO)
    etapa = models.ForeignKeyPlus('projetos_ensino.Etapa', on_delete=models.CASCADE)
    qtd = models.IntegerField(
        'Quantidade', help_text='Informe uma quantidade diferente da planejada caso a quantidade planejada não tenha sido alcançada'
    )
    inicio_execucao = models.DateFieldPlus(
        'Início da Execução', help_text='Informe uma data diferente da planejada caso o início da execução tenha sido adiantado/atrasado'
    )
    fim_execucao = models.DateFieldPlus(
        'Fim da Execução', help_text='Informe uma data diferente da planejada caso o término da execução tenha sido adiantado/atrasado'
    )
    info_ind_qualitativo = models.TextField(
        'Indicadores Qualitativos',
        help_text='Informações sobre os resultados obitidos acerca dos indicadores qualitativos definidos para a atividade: ?',
    )
    obs = models.TextField(
        'Descrição da Atividade Realizada',
        null=True,
        blank=True,
        validators=[MaxLengthValidator(5000)],
        help_text='Descreva e coloque as informações que julgar relevantes na execução da atividade',
    )
    justificativa_reprovacao = models.TextField(
        'Justificativa da Reprovação da Atividade',
        null=True,
        blank=True,
        help_text='Informação adicional que você julgar relevante no que diz respeito à reprovação da atividade.',
    )
    dt_avaliacao = models.DateFieldPlus(null=True)
    avaliador = models.ForeignKeyPlus(Servidor, null=True, on_delete=models.CASCADE, related_name='projetoensino_avaliador_etapa')
    aprovado = models.BooleanField(default=False)
    data_cadastro_execucao = models.DateFieldPlus(null=True)
    arquivo = models.PrivateFileField(max_length=255, upload_to='projetos_ensino/atividades/comprovantes/', null=True, blank=True)

    class Meta:
        verbose_name = 'Registro de Execução de Atividade'
        verbose_name_plural = 'Registros de Execução de Atividades'

    def __str__(self):
        return f'Registro de Execução da Etapa: {self.etapa}'

    def get_mensagem_avaliacao(self):
        return get_mensagem_avaliacao(self)


class RegistroConclusaoProjeto(models.ModelPlus):
    projeto = models.ForeignKeyPlus(Projeto, on_delete=models.CASCADE)
    resultados_alcancados = models.TextField(
        'Resultados Alcançados', help_text='Informações sobre os resultados obtidos pelo projeto.', null=True, blank=True
    )
    disseminacao_resultados = models.TextField(
        'Disseminação dos Resultados',
        help_text='Informações de como os resultados foram e/ou serão divulgados para a sociedade.',
        null=True,
        blank=True,
    )
    obs = models.TextField(
        'Observação', null=True, blank=True, help_text='Informação adicional que você julgar relevante no que diz respeito à conclusão do projeto.'
    )
    dt_avaliacao = models.DateFieldPlus(null=True)
    avaliador = models.ForeignKeyPlus(Servidor, null=True, on_delete=models.CASCADE, related_name='projetoensino_avaliador_registro')
    obs_avaliador = models.TextField(
        'Observação do Avaliador',
        null=True,
        blank=True,
        help_text='Informação adicional que você julgar relevante no que diz respeito à validação do projeto.',
    )
    aprovado = models.BooleanField(default=False)

    def get_status(self):
        if self.dt_avaliacao:
            if self.aprovado:
                return 1
            else:
                return 3
        else:
            return 2

    def __str__(self):
        return f'Registro de Conclusão do Projeto: {self.projeto}'


class Participacao(models.ModelPlus):
    SERVIDOR = '1'
    ALUNO = '2'
    TIPOCONTA_CONTACORRENTE = 'Conta Corrente'
    TIPOCONTA_POUPANCA = 'Conta Poupança'

    TIPOCONTA_CHOICES = ((TIPOCONTA_CONTACORRENTE, TIPOCONTA_CONTACORRENTE), (TIPOCONTA_POUPANCA, TIPOCONTA_POUPANCA))
    projeto = models.ForeignKeyPlus(Projeto, verbose_name='Projeto', on_delete=models.CASCADE)

    vinculo_pessoa = models.ForeignKey(
        'comum.Vinculo', verbose_name='Participante', related_name='projetos_ensino_vinculo_membro', on_delete=models.CASCADE, null=True
    )
    responsavel = models.BooleanField('Coordenador', default=False)
    vinculo = models.CharField(max_length=255, choices=TipoVinculo.TIPOS)
    carga_horaria = models.PositiveIntegerField('Carga Horária', help_text='Carga horária semanal')
    ativo = models.BooleanField(default=True)
    data_inativacao = models.DateField('Data de Inativação', null=True)
    bolsa_concedida = models.BooleanField(default=False)
    orientador = models.ForeignKeyPlus(
        'projetos_ensino.Participacao', verbose_name='Orientador do Aluno', null=True, blank=True, on_delete=models.SET_NULL
    )
    termo_aceito_em = models.DateTimeFieldPlus(null=True)
    instituicao = models.ForeignKeyPlus(
        'rh.Banco', verbose_name='Banco', null=True, on_delete=models.SET_NULL, related_name='projetosensino_participacao_banco'
    )
    numero_agencia = models.CharField('Número da Agência', max_length=50, null=True, help_text='Ex: 3293-X')
    tipo_conta = models.CharField('Tipo da Conta', max_length=50, choices=TIPOCONTA_CHOICES, null=True)
    numero_conta = models.CharField('Número da Conta', max_length=50, null=True, help_text='Ex: 23384-6')
    operacao = models.CharField('Operação', max_length=50, null=True, blank=True)
    objects = ParticipacaoManager()
    ativos = ParticipacaoManagerAtivo()

    class Meta:
        verbose_name = 'Participação'
        verbose_name_plural = 'Participações'

    @classmethod
    def gerar_anexos_do_participante(cls, participacao):
        tipos_dos_anexos = []
        projeto = participacao.projeto
        for anexo_edital in participacao.get_tipos_anexos():
            if not projeto.projetoanexo_set.filter(anexo_edital=anexo_edital, vinculo_membro_equipe=participacao.vinculo_pessoa):
                a = ProjetoAnexo()
                a.anexo_edital = anexo_edital
                a.projeto = projeto
                a.vinculo_membro_equipe = participacao.vinculo_pessoa
                a.participacao = participacao
                a.save()
            tipos_dos_anexos.append(anexo_edital.id)

        anexos_exigidos = ProjetoAnexo.objects.filter(
            projeto=projeto, vinculo_membro_equipe=participacao.vinculo_pessoa, anexo_edital__isnull=False, arquivo__isnull=True
        )
        if anexos_exigidos.exists():
            for anexo in anexos_exigidos:
                if anexo.anexo_edital.id not in tipos_dos_anexos:
                    anexo.delete()

    def get_tipo_vinculo_membro(self):
        if self.vinculo_pessoa and self.vinculo_pessoa.eh_servidor():
            servidor = Servidor.objects.get(id=self.vinculo_pessoa.id_relacionamento)
            if self.responsavel:
                if servidor.eh_docente:
                    return EditalAnexo.COORDENADOR_DOCENTE
                else:
                    return EditalAnexo.COORDENADOR_TECNICO_ADMINISTRATIVO
            else:
                if servidor.eh_docente:
                    return EditalAnexo.SERVIDOR_DOCENTE
                else:
                    return EditalAnexo.SERVIDOR_ADMINISTRATIVO
        elif not self.vinculo_pessoa or self.vinculo_pessoa.eh_aluno():
            return EditalAnexo.ALUNO
        else:
            return EditalAnexo.COLABORADOR_VOLUNTARIO

    def eh_docente(self):
        if self.is_servidor():
            servidor = Servidor.objects.get(vinculos=self.vinculo_pessoa)
            return servidor.eh_docente
        return False

    def get_tipos_anexos(self):
        tipo_membro = self.get_tipo_vinculo_membro()

        return EditalAnexo.objects.filter(tipo_membro=tipo_membro, vinculo=self.vinculo, edital=self.projeto.edital)

    def tem_tipos_anexos(self):
        tipo_membro = self.get_tipo_vinculo_membro()

        return EditalAnexo.objects.filter(tipo_membro=tipo_membro, vinculo=self.vinculo, edital=self.projeto.edital).exists()

    def is_servidor(self):
        if self.vinculo_pessoa:
            return self.vinculo_pessoa.eh_servidor()
        return False

    def eh_aluno(self):
        if self.vinculo_pessoa:
            return self.vinculo_pessoa.eh_aluno()
        return True

    def get_participante(self):
        if self.vinculo_pessoa:
            if self.vinculo_pessoa.eh_servidor():
                return Servidor.objects.get(id=self.vinculo_pessoa.id_relacionamento)
            elif self.vinculo_pessoa.eh_aluno():
                return Aluno.objects.get(id=self.vinculo_pessoa.id_relacionamento)
            else:
                if ColaboradorExterno.objects.filter(prestador=self.vinculo_pessoa.id_relacionamento).exists():
                    return ColaboradorExterno.objects.get(prestador=self.vinculo_pessoa.id_relacionamento)
        return None

    def get_nome(self):
        pessoa = self.get_participante()
        if pessoa:
            if isinstance(pessoa, Aluno):
                return Vinculo.objects.get(id_relacionamento=pessoa.id, tipo_relacionamento__model='aluno').pessoa.nome
            elif isinstance(pessoa, ColaboradorExterno):
                return pessoa.prestador.get_vinculo().pessoa.nome
            else:
                return pessoa.get_vinculo().pessoa.nome
        else:
            if self.vinculo_pessoa and self.vinculo_pessoa.eh_prestador():
                return self.vinculo_pessoa.pessoa.nome
            contador = 0
            if Participacao.objects.filter(projeto=self.projeto, vinculo=self.vinculo, vinculo_pessoa__isnull=True).exists():
                for integrante in Participacao.objects.filter(projeto=self.projeto, vinculo=self.vinculo, vinculo_pessoa__isnull=True).order_by('id'):
                    contador += 1
                    if self.id == integrante.id:
                        identificador = contador
            else:
                identificador = 1
            return f'Aluno {self.vinculo} {identificador}'

    def get_identificador(self):
        participante = self.get_participante()
        if participante:
            if hasattr(participante, 'matricula'):
                return participante.matricula
            else:
                return participante.prestador.pessoa_fisica.cpf or self.vinculo_pessoa.relacionamento.pessoa_fisica.passaporte
        else:
            if self.vinculo_pessoa and self.vinculo_pessoa.eh_prestador():
                return self.vinculo_pessoa.relacionamento.pessoa_fisica.cpf or self.vinculo_pessoa.relacionamento.pessoa_fisica.passaporte
            return '-'

    def get_titulacao(self):
        if self.vinculo_pessoa and self.vinculo_pessoa.eh_servidor():
            servidor = Servidor.objects.get(id=self.vinculo_pessoa.id_relacionamento)
            if servidor.eh_docente:
                return 'DOCENTE ({})'.format(servidor.titulacao or '-')
            if servidor.eh_tecnico_administrativo:
                return 'TÉCNICO-ADMINISTRATIVO ({})'.format(servidor.titulacao or '-')
            if servidor.eh_aposentado:
                return 'APOSENTADO ({})'.format(servidor.titulacao or '-')
            if servidor.eh_estagiario:
                return 'ESTAGIÁRIO ({})'.format(servidor.titulacao or '-')
        elif not self.vinculo_pessoa or self.vinculo_pessoa.eh_aluno():
            return 'DISCENTE'
        else:
            return 'COLABORADOR VOLUNTÁRIO'

    def __str__(self):
        return self.get_nome()

    def get_selecionado(self):
        return self.projeto.get_selecionado(participacao=self)

    def get_pre_selecionado(self):
        return self.projeto.get_pre_selecionado(participacao=self)

    def adicionar_registro_historico_equipe(self, tipo_de_evento, descricao=None, data_evento=None, obs=None):
        if self.responsavel:
            categoria = HistoricoEquipe.COORDENADOR
        else:
            categoria = HistoricoEquipe.MEMBRO

        if data_evento:
            data_do_historico = data_evento
        else:
            data_do_historico = self.projeto.get_data_historico_equipe()

        historicos = HistoricoEquipe.objects.filter(projeto=self.projeto, participante=self).order_by('-id')
        if historicos:
            ultimo_historico = historicos[0]
            ultimo_historico.data_movimentacao_saida = data_do_historico
            ultimo_historico.save()

        HistoricoEquipe.objects.create(
            projeto=self.projeto,
            participante=self,
            movimentacao=descricao,
            data_movimentacao=data_do_historico,
            tipo_de_evento=tipo_de_evento,
            categoria=categoria,
            carga_horaria=self.carga_horaria,
            vinculo=self.get_vinculo(),
            obs=obs,
        )

    def get_vinculo(self):
        if self.vinculo == TipoVinculo.BOLSISTA:
            return TipoVinculo.BOLSISTA
        else:
            return TipoVinculo.VOLUNTARIO

    def pode_remover_participacao(self):
        return bool(
            self.projeto.is_coordenador()
            and not self.responsavel
            and self.projeto.get_status() in [Projeto.STATUS_EM_INSCRICAO, Projeto.STATUS_EM_EXECUCAO]
        )

    def get_inicio_orientacao_atual(self):
        if HistoricoOrientacaoProjeto.objects.filter(orientado=self, data_termino__isnull=True).exists():
            return HistoricoOrientacaoProjeto.objects.filter(orientado=self, data_termino__isnull=True)[0].data_inicio
        return None

    def pode_ver_avaliacoes(self) -> bool:
        """Coordenador do projeto, monitor, orientador ou o próprio aluno avaliado."""
        user = tl.get_user()
        vinculo = user.get_vinculo()
        return bool(
            self.projeto.is_coordenador(user)
            or (vinculo == self.projeto.vinculo_monitor)
            or (self.orientador and self.orientador.vinculo_pessoa == vinculo)
            or (self.vinculo_pessoa and self.vinculo_pessoa == vinculo)
        )

    def pode_fazer_avaliacoes(self):
        user = tl.get_user()
        return self.projeto.is_coordenador(user) or (self.orientador and self.orientador.vinculo_pessoa == user.get_vinculo())

    def get_data_entrada(self):
        movimentacao = HistoricoEquipe.objects.filter(participante=self).order_by('id')
        if movimentacao.exists():
            if self.projeto.inicio_execucao > movimentacao[0].data_movimentacao:
                return self.projeto.inicio_execucao
            else:
                return movimentacao[0].data_movimentacao
        return None

    def get_data_saida(self, apenas_bolsista=None):
        movimentacao = (
            HistoricoEquipe.objects.filter(participante=self).order_by('-id').exclude(tipo_de_evento=HistoricoEquipe.EVENTO_INATIVAR_PARTICIPANTE)
        )
        if apenas_bolsista:
            movimentacao = movimentacao.filter(vinculo=TipoVinculo.BOLSISTA)
        if movimentacao.exists():
            if not movimentacao[0].data_movimentacao_saida:
                return self.projeto.fim_execucao
            if movimentacao[0].data_movimentacao_saida > self.projeto.fim_execucao:
                return self.projeto.fim_execucao
            else:
                return movimentacao[0].data_movimentacao_saida
        return None

    def save(self):
        super(self.__class__, self).save()

        if self.responsavel:
            Projeto.objects.filter(id=self.projeto.id).update(vinculo_coordenador=self.vinculo_pessoa)

    def get_historico_distribuicao_bolsa(self):
        return HistoricoEquipe.objects.filter(
            participante=self, tipo_de_evento__in=[HistoricoEquipe.EVENTO_CONCEDER_BOLSAR, HistoricoEquipe.EVENTO_NAOCONCEDER_BOLSA]
        )

    def tem_historico_equipe(self):
        movimentacao = HistoricoEquipe.objects.filter(participante=self, vinculo__isnull=False)
        return bool(movimentacao.exists())

    def pode_emitir_plano_de_trabalho(self):
        user = tl.get_user()
        pode_emitir = (
            self.projeto.is_pre_avaliador() or self.projeto.is_coordenador() or (self.vinculo_pessoa and user.get_vinculo() == self.vinculo_pessoa)
        )
        return bool(pode_emitir)

    def pode_emitir_certificado_de_participacao(self):
        user = tl.get_user()
        status = self.projeto.get_status()
        pode_emitir = self.vinculo_pessoa and (
            self.projeto.is_pre_avaliador() or self.projeto.is_coordenador() or (self.vinculo_pessoa and user.get_vinculo() == self.vinculo_pessoa)
        )
        return bool(
            pode_emitir
            and (status == Projeto.STATUS_CONCLUIDO or self.ativo is False)
            and self.tem_historico_equipe()
            and self.projeto.aprovado is True
            and not self.projeto.inativado
        )

    def pode_emitir_declaracao_orientacao(self) -> bool:
        user = tl.get_user()
        status = self.projeto.get_status()
        return (
            (self.projeto.is_pre_avaliador() or self.projeto.is_coordenador() or user.get_vinculo() == self.vinculo_pessoa)
            and (status in [Projeto.STATUS_EM_EXECUCAO, Projeto.STATUS_CONCLUIDO] or self.ativo is False)
            and HistoricoOrientacaoProjeto.objects.filter(projeto=self.projeto, orientador=self).exists()
            and not self.projeto.inativado
        )

    def pode_emitir_declaracao_de_participacao(self):
        user = tl.get_user()
        status = self.projeto.get_status()
        pode_emitir = self.vinculo_pessoa and (
            self.projeto.is_pre_avaliador() or self.projeto.is_coordenador() or (user.get_vinculo() == self.vinculo_pessoa)
        )
        return bool(pode_emitir and status in [Projeto.STATUS_EM_EXECUCAO, Projeto.STATUS_CONCLUIDO])


class FotoProjeto(models.ModelPlus):
    projeto = models.ForeignKeyPlus(Projeto, on_delete=models.CASCADE)
    legenda = models.TextField(blank=True)
    imagem = models.PrivateFileField(upload_to='projetos_ensino/fotos/')

    def __str__(self):
        return f'Foto do Projeto: {self.projeto} '

    def save(self):
        from PIL import Image

        super().save()
        if self.imagem and default_storage.exists(self.imagem.name):
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
            with self.imagem.open('rb') as f:
                tmp.write(f.read())
            tmp.close()
            im = Image.open(tmp.name)
            width, height = im.size
            size = (400, 300)
            if height > width:
                size = (300, 400)
            im.thumbnail(size, Image.Resampling.LANCZOS)
            fh = default_storage.open(self.imagem.name, 'wb')
            im.save(fh, 'png')
            fh.close()


class HistoricoEquipe(models.ModelPlus):
    COORDENADOR = '1'
    MEMBRO = '2'
    CATEGORIA = (
        (COORDENADOR, 'Coordenador'),
        (MEMBRO, 'Membro'),
    )
    MOVIMENTACAO_MEMBRO = 'Membro do projeto'
    MOVIMENTACAO_COORDENADOR = 'Coordenador do projeto'

    EVENTO_COORDENADOR_SUBSTITUIDO = 1
    EVENTO_ADICIONAR_ALUNO = 2
    EVENTO_ADICIONAR_SERVIDOR = 3
    EVENTO_ATIVAR_PARTICIPANTE = 4
    EVENTO_INATIVAR_PARTICIPANTE = 5
    EVENTO_EXCLUIR_PARTICIPANTE = 6
    EVENTO_CONCEDER_BOLSAR = 7
    EVENTO_NAOCONCEDER_BOLSA = 8
    EVENTO_EDICAO_ALUNO = 9
    EVENTO_EDICAO_SERVIDOR = 10
    EVENTO_COORDENADOR_DESISTITUIDO = 11
    EVENTO_COORDENADOR_INSERIDO = 12
    EVENTO_ADICIONAR_COLABORADOR = 13
    EVENTO_EDICAO_COLABORADOR = 14

    TIPOS_DE_EVENTOS = (
        (EVENTO_COORDENADOR_DESISTITUIDO, 'Saiu da coordenação do projeto'),
        (EVENTO_COORDENADOR_INSERIDO, 'Tornou-se coordenador do projeto'),
        (EVENTO_COORDENADOR_SUBSTITUIDO, 'Assumiu a coordenação do projeto'),
        (EVENTO_ADICIONAR_ALUNO, 'Aluno inserido'),
        (EVENTO_ADICIONAR_SERVIDOR, 'Servidor inserido'),
        (EVENTO_ADICIONAR_COLABORADOR, 'Colaborador Voluntário inserido'),
        (EVENTO_ATIVAR_PARTICIPANTE, 'Participante ativado'),
        (EVENTO_INATIVAR_PARTICIPANTE, 'Participante inativado'),
        (EVENTO_EXCLUIR_PARTICIPANTE, 'Participante excluído'),
        (EVENTO_CONCEDER_BOLSAR, 'Bolsa concedida durante a distribuição de bolsas'),
        (EVENTO_NAOCONCEDER_BOLSA, 'Bolsas não concedida durante a distribuição de bolsas'),
        (EVENTO_EDICAO_ALUNO, 'Aluno alterado'),
        (EVENTO_EDICAO_SERVIDOR, 'Servidor alterado'),
        (EVENTO_EDICAO_COLABORADOR, 'Colaborador Voluntário alterado'),
    )
    projeto = models.ForeignKeyPlus(Projeto, on_delete=models.CASCADE)
    participante = models.ForeignKeyPlus(Participacao, on_delete=models.CASCADE)
    movimentacao = models.CharField(max_length=50, null=True)
    data_movimentacao = models.DateFieldPlus()
    data_movimentacao_saida = models.DateFieldPlus(null=True, blank=True)
    categoria = models.CharField(max_length=5, null=True, blank=True, choices=CATEGORIA)
    vinculo = models.CharField(max_length=25, null=True, blank=True, choices=TipoVinculo.TIPOS)
    tipo_de_evento = models.PositiveIntegerField(blank=True, choices=TIPOS_DE_EVENTOS)
    carga_horaria = models.PositiveIntegerField('Carga Horária', help_text='Carga horária semanal', null=True, blank=True)
    obs = models.CharField(max_length=1000, null=True)

    class Meta:
        verbose_name = 'Histórico da Equipe'
        verbose_name_plural = 'Históricos das Equipes'

    def __str__(self):
        return str(self.projeto)

    def eh_bolsista(self):
        return self.vinculo == TipoVinculo.BOLSISTA

    def get_movimentacao_descricao(self):
        if self.movimentacao and self.tipo_de_evento != 0:
            return f'{self.get_tipo_de_evento_display()} - {self.movimentacao}'
        elif self.movimentacao:
            return self.movimentacao
        return self.get_tipo_de_evento_display()

    def get_data_inativacao(self):
        if self.movimentacao == 'Incluído' and self.participante.data_inativacao:
            from django.utils import dateformat

            return ' <span class="false">(Inativado em {})</span>'.format(dateformat.format(self.participante.data_inativacao, 'd/m/Y'))
        else:
            return ''

    def get_carga_horaria_total(self):
        if self.participante.projeto.inicio_execucao > self.data_movimentacao:
            data_inicio = self.participante.projeto.inicio_execucao
        else:
            data_inicio = self.data_movimentacao

        if not self.data_movimentacao_saida:
            data_fim = self.participante.projeto.fim_execucao
        else:
            if self.participante.projeto.fim_execucao < self.data_movimentacao_saida:
                data_fim = self.participante.projeto.fim_execucao
            else:
                data_fim = self.data_movimentacao_saida

        dias_totais = (data_fim - data_inicio).days
        ch_diaria = Decimal(float(self.carga_horaria) / float(7))
        return int(dias_totais * ch_diaria)

    def get_vinculo(self):
        return self.get_categoria_display()


class Etapa(models.ModelPlus):
    meta = models.ForeignKeyPlus('projetos_ensino.Meta', verbose_name='Meta', on_delete=models.CASCADE)
    ordem = models.PositiveIntegerField('Ordem', help_text='Informe um número inteiro maior ou igual a 1')
    descricao = models.TextField('Descrição')
    unidade_medida = models.CharField('Unidade de Medida', max_length=255)  # pode mudar para FK
    qtd = models.PositiveIntegerField('Quantidade')
    indicadores_qualitativos = models.TextField('Indicador(es) Qualitativo(s)')
    responsavel = models.ForeignKeyPlus(
        Participacao, verbose_name='Responsável pela Atividade', related_name='participacao_projeto_ensino_responsavel', on_delete=models.CASCADE
    )
    integrantes = models.ManyToManyFieldPlus('projetos_ensino.Participacao', related_name='integrantes_set', blank=True)
    inicio_execucao = models.DateFieldPlus('Início da Execução', null=True)
    fim_execucao = models.DateFieldPlus('Fim da Execução', null=True)
    data_cadastro = models.DateFieldPlus('Data de Cadastro da Etapa', null=True, blank=True, default=datetime.datetime.now)

    class Meta:
        verbose_name = 'Atividade'
        verbose_name_plural = 'Atividades'

    def __str__(self):
        return f'Etapa {self.ordem} - {self.descricao} / Meta: {self.meta.ordem}'

    def get_registro_execucao(self):
        qs = RegistroExecucaoEtapa.objects.filter(etapa=self).order_by('id')
        if qs:
            return qs[0]
        return None

    def get_status_execucao(self):
        qs = RegistroExecucaoEtapa.objects.filter(etapa=self)
        if qs.exists():
            registro_execucao = qs[0]
            if registro_execucao.dt_avaliacao:
                if registro_execucao.aprovado:
                    return 1  # aprovado
                else:
                    return 3  # reprovado
            else:
                return 2  # aguardando validação
        else:
            return 4  # apto para ser avaliado

    def eh_planejamento(self):
        return eh_planejamento(self)

    def pode_editar_e_remover_atividade(self):
        qs_registro = RegistroExecucaoEtapa.objects.filter(etapa=self).order_by('id')
        if qs_registro:
            registro = qs_registro[0]

            if (
                not registro.dt_avaliacao
                and self.meta.projeto.edicao_inscricao_execucao()
                and not self.eh_planejamento()
                and not self.meta.projeto.get_registro_conclusao()
            ):
                return True
        return bool(self.meta.projeto.edicao_inscricao_execucao() and not self.eh_planejamento() and not self.meta.projeto.get_registro_conclusao())

    def clean(self):
        if self.inicio_execucao and self.fim_execucao and (self.inicio_execucao > self.fim_execucao):
            raise forms.ValidationError('A data do fim da execução deve ser maior que a data de início.')


class ProjetoHistoricoDeEnvio(models.ModelPlus):
    ENVIADO = 'E'
    DEVOLVIDO = 'D'
    REBAERTO = 'R'
    FINALIZADO = 'F'
    TIPO_SITUACAO = (
        (ENVIADO, 'Enviado'),
        (DEVOLVIDO, 'Devolvido'),
        (REBAERTO, 'Reaberto'),
        (FINALIZADO, 'Finalizado'),
    )
    projeto = models.ForeignKeyPlus(Projeto, on_delete=models.CASCADE, related_name='projetoensino_historicoenvio')
    parecer_devolucao = models.TextField('Parecer sobre a devolução do projeto')
    data_operacao = models.DateTimeFieldPlus('Data de realização da Operação', null=True, blank=True)
    situacao = models.CharField('Situação', max_length=1, choices=TIPO_SITUACAO, null=True, blank=True)
    operador = models.ForeignKeyPlus(
        Servidor, verbose_name='Operador', null=True, blank=True, on_delete=models.CASCADE, related_name='projetoensino_historico'
    )
    vinculo_operador = models.ForeignKeyPlus(
        Vinculo,
        verbose_name='Vínculo do Operador',
        null=True,
        blank=True,
        related_name='projetoensino_historicoenvio_vinculooperador',
        on_delete=models.CASCADE,
    )

    class Meta:
        verbose_name = 'Histórico do Envio de Projetos'
        verbose_name_plural = 'Históricos dos Envios de Projetos'

    def __str__(self):
        return f'Histórico do Projeto: {self.projeto}'


class AreaLicaoAprendida(models.ModelPlus):
    descricao = models.CharField('Descrição', max_length=100, unique=True)

    class Meta:
        verbose_name = 'Área de Lição Aprendida'
        verbose_name_plural = 'Áreas de Lições Aprendidas'

    def __str__(self):
        return str(self.descricao)


class LicaoAprendida(models.ModelPlus):
    projeto = models.ForeignKeyPlus(Projeto, on_delete=models.CASCADE)
    area_licao_aprendida = models.ForeignKeyPlus(AreaLicaoAprendida, verbose_name='Área', on_delete=models.CASCADE)
    descricao = models.TextField(
        'Descrição',
        help_text='As lições aprendidas visam garantir que as melhorias implantadas ao longo da execução de um projeto possam ser, também, implementadas como padrão nos próximos a serem desenvolvidos, como forma de evitar que erros ou equívocos se repitam em quaisquer atividades.',
    )

    class Meta:
        verbose_name = 'Lição Aprendida'
        verbose_name_plural = 'Lições Aprendidas'

    def __str__(self):
        return str(self.descricao)


class ProjetoCancelado(models.ModelPlus):
    projeto = models.ForeignKeyPlus(Projeto, on_delete=models.CASCADE)
    justificativa_cancelamento = models.CharField('Justificativa do Cancelamento', max_length=1000, null=True, blank=True)
    data_solicitacao = models.DateTimeFieldPlus('Data da Solicitação do Cancelamento')
    avaliador = models.ForeignKeyPlus(
        Servidor, verbose_name='Operador', null=True, blank=True, on_delete=models.CASCADE, related_name='projetoensino_avaliador_projetocancelado'
    )
    obs_avaliacao = models.CharField('Observação', max_length=500, null=True, blank=True)
    data_avaliacao = models.DateTimeFieldPlus('Data da Avaliação da Solicitação', null=True, blank=True)
    cancelado = models.BooleanField('Cancelado', default=False)
    proximo_projeto = models.ForeignKeyPlus(Projeto, null=True, blank=True, related_name='projetoensino_proximo_projeto', on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Projeto Cancelado'
        verbose_name_plural = 'Projetos Cancelados'
        ordering = ['-data_solicitacao']

    def __str__(self):
        return f'Cancelamento do Projeto: {self.projeto}'

    def get_situacao(self):
        if not self.data_avaliacao:
            texto_retorno = '<span class="status status-alert">Não avaliado</span>'
        elif not self.cancelado:
            texto_retorno = '<span class="status status-error">Não aceito</span>'
        else:
            texto_retorno = '<span class="status status-success">Aceito</span>'
        return texto_retorno


class ComissaoEdital(models.ModelPlus):
    edital = models.ForeignKeyPlus(Edital, on_delete=models.CASCADE)
    vinculos_membros = models.ManyToManyFieldPlus(
        'comum.Vinculo', verbose_name='Membros', blank=True, related_name='vinculos_membros_comissao_edital_ensino'
    )

    class Meta:
        verbose_name = 'Comissão de Avaliação'
        verbose_name_plural = 'Comissões de Avaliação'

    def __str__(self):
        return f'Comissão do {self.edital.titulo}'

    def get_membros(self):
        string = ''
        for membro in self.vinculos_membros.all():
            string = string + '<p>' + membro.pessoa.nome + '</p>'

        return string


class RecursoProjeto(models.ModelPlus):
    projeto = models.OneToOneField(Projeto, on_delete=models.CASCADE)
    justificativa = models.CharField('Justificativa do Recurso', max_length=1000, null=True, blank=True)
    data_solicitacao = models.DateTimeFieldPlus('Data da Solicitação do Recurso')
    avaliador = models.ForeignKeyPlus(
        Servidor, verbose_name='Avaliador', related_name='projetoensino_avaliador_recurso', null=True, blank=True, on_delete=models.CASCADE
    )
    parecer = models.CharField('Parecer', max_length=5000, null=True, blank=True)
    data_avaliacao = models.DateTimeFieldPlus('Data da Avaliação da Solicitação', null=True, blank=True)
    aceito = models.BooleanField('Aceito', default=False)

    class Meta:
        verbose_name = 'Recurso'
        verbose_name_plural = 'Recursos'
        ordering = ['-data_solicitacao']

    def get_situacao(self):
        if not self.data_avaliacao:
            texto_retorno = '<span class="status status-alert">Não avaliado</span>'
        elif not self.aceito:
            texto_retorno = '<span class="status status-error">Não aceito</span>'
        else:
            texto_retorno = '<span class="status status-success">Aceito</span>'
        return texto_retorno

    def get_opcoes(self):
        if self.projeto.edital.divulgacao_selecao >= datetime.datetime.now():
            texto_retorno = '<ul class="action-bar">'
            if not self.data_avaliacao:
                texto_retorno += f'<li><a href="/projetos_ensino/avaliar_recurso_projeto/{self.id}/" class="success">Avaliar</a></li>'
            else:
                texto_retorno += f'<li><a href="/projetos_ensino/avaliar_recurso_projeto/{self.id}/"  class="primary">Editar Avaliação</a></li>'

            texto_retorno += '</ul>'
            return texto_retorno
        return ''

    def __str__(self):
        return f'Recurso #{self.id}'


class CriterioAvaliacaoAluno(models.ModelPlus):
    nome = models.CharFieldPlus('Nome do Critério', max_length=255)
    descricao_criterio = models.CharFieldPlus('Descrição do Critério', max_length=5000)
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        ordering = ['nome']
        verbose_name = 'Critério de Avaliação do Aluno'
        verbose_name_plural = 'Critérios de Avaliação do Aluno'

    def __str__(self):
        return 'Critério de Avaliação'


class AvaliacaoAluno(models.ModelPlus):
    PARCIAL = 'Parcial'
    FINAL = 'Final'

    TIPOAVALIACAO_CHOICES = (
        (PARCIAL, PARCIAL),
        (FINAL, FINAL),
    )
    participacao = models.ForeignKeyPlus(
        'projetos_ensino.Participacao', related_name='projetos_avaliacaoaluno_participante_ensino', on_delete=models.CASCADE
    )
    tipo_avaliacao = models.CharFieldPlus('Tipo de Avaliação', max_length=20, choices=TIPOAVALIACAO_CHOICES)
    data_avaliacao = models.DateTimeFieldPlus('Realizada em', null=True, blank=True)
    data_validacao = models.DateTimeFieldPlus('Validada pelo aluno em', null=True, blank=True)
    consideracoes_coordenador = models.CharFieldPlus('Considerações do Avaliador', max_length=5000, null=True, blank=True)
    consideracoes_aluno = models.CharFieldPlus('Considerações do Aluno', max_length=5000, null=True, blank=True)
    vinculo_avaliado_por = models.ForeignKey(
        'comum.Vinculo', related_name='projetoensino_avaliador_avaliacao_aluno', on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        verbose_name = 'Avaliação do Aluno'
        verbose_name_plural = 'Avaliações dos Alunos'

    def __str__(self):
        return f'Avaliação do Aluno: {self.participacao}'


class ItemAvaliacaoAluno(models.ModelPlus):
    RUIM = 'Ruim'
    REGULAR = 'Regular'
    BOM = 'Bom'
    EXCELENTE = 'Excelente'
    NAO_APLICA = 'Não se Aplica'
    PONTUACAOAVALIACAO_CHOICES = (
        (NAO_APLICA, NAO_APLICA),
        (EXCELENTE, EXCELENTE),
        (BOM, BOM),
        (REGULAR, REGULAR),
        (RUIM, RUIM),
    )
    criterio = models.ForeignKeyPlus(
        'projetos_ensino.CriterioAvaliacaoAluno', related_name='projetos_ensino_criterioavaliacaoaluno', on_delete=models.CASCADE
    )
    avaliacao = models.ForeignKeyPlus('projetos_ensino.AvaliacaoAluno', related_name='projetos_ensino_avaliacaoaluno', on_delete=models.CASCADE)
    pontuacao = models.CharFieldPlus('Pontuação', max_length=20, choices=PONTUACAOAVALIACAO_CHOICES)

    class Meta:
        ordering = ['criterio__nome']
        verbose_name = 'Item de Avaliação do Aluno'
        verbose_name_plural = 'Itens de Avaliação dos Alunos'

    def __str__(self):
        return f'Item da Avaliação: {self.avaliacao}'


class HistoricoAlteracaoPeriodoProjeto(models.ModelPlus):
    projeto = models.ForeignKeyPlus('projetos_ensino.Projeto', related_name='projetoensino_historicodata', on_delete=models.CASCADE)
    inicio_execucao = models.DateFieldPlus('Início da Execução')
    fim_execucao = models.DateFieldPlus('Término da Execução')
    justificativa = models.CharFieldPlus('Justificativa', max_length=5000)
    vinculo_registrado_por = models.ForeignKey(
        'comum.Vinculo', related_name='projetoensino_vinculo_registradopor_historicodata', on_delete=models.CASCADE, null=True
    )
    registrado_em = models.DateTimeFieldPlus('Registrado em', auto_now_add=True)

    class Meta:
        ordering = ['-registrado_em']
        verbose_name = 'Registro de Alteração de Período de Execução'
        verbose_name_plural = 'Registros de Alterações de Períodos de Execução'

    def __str__(self):
        return f'Alteração do Projeto: {self.projeto}'


class HistoricoOrientacaoProjeto(models.ModelPlus):
    projeto = models.ForeignKeyPlus(Projeto, on_delete=models.CASCADE)
    orientado = models.ForeignKeyPlus(Participacao, on_delete=models.CASCADE, related_name='projetoensino_orientado_projeto')
    orientador = models.ForeignKeyPlus(Participacao, on_delete=models.CASCADE, related_name='projetoensino_orientador_projeto')
    data_inicio = models.DateFieldPlus()
    data_termino = models.DateFieldPlus(null=True, blank=True)

    class Meta:
        verbose_name = 'Histórico de Orientação do Projeto'
        verbose_name_plural = 'Históricos de Orientações do Projeto'

    def __str__(self):
        return str(self.projeto)


class ComissaoAcompanhamento(models.ModelPlus):
    uo = models.OneToOneField(UnidadeOrganizacional, on_delete=models.CASCADE, verbose_name='Campus')
    coordenador = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Coordenador', on_delete=models.CASCADE)
    membros = models.ManyToManyFieldPlus('comum.Vinculo', verbose_name='Membros', blank=True, related_name='membros_comissao_acompanhamento')

    class Meta:
        verbose_name = 'Comissão de Acompanhamento'
        verbose_name_plural = 'Comissões de Acompanhamento'

    def __str__(self):
        return f'Comissão de Acompanhamento - Campus {self.uo}'

    def get_membros(self):
        string = ''
        for membro in self.membros.all():
            string = string + '<p>' + membro.pessoa.nome + '</p>'

        return string


class ColaboradorExterno(models.ModelPlus):
    nome = models.CharField('Nome', max_length=255)
    prestador = models.OneToOneField('comum.PrestadorServico', related_name='projetos_ensino_colaborador_externo', on_delete=models.CASCADE)
    ativo = models.BooleanField('Ativo', default=True)
    email = models.EmailField('Email')
    telefone = models.CharFieldPlus('Telefone', max_length=255, null=True, blank=True)
    titulacao = models.ForeignKeyPlus(
        'rh.Titulacao', verbose_name='Titulação', related_name='projetos_ensino_colaborador_instituicao', on_delete=models.CASCADE
    )
    instituicao_origem = models.ForeignKeyPlus(
        'rh.Instituicao',
        blank=True,
        null=True,
        verbose_name='Instituição',
        related_name='projetos_ensino_instituicao_colaborador',
        on_delete=models.CASCADE,
    )
    lattes = models.URLField(blank=True, null=True)
    documentacao = models.PrivateFileField(verbose_name='Documentação', upload_to='projetos_ensino/colaborador_externo', null=True, blank=True)

    EXT_COMBO_RELATED = {
        'select_related': ['prestador__pessoa_fisica', 'prestador__setor'],
        'prefetch_related': [],
    }

    class Meta:
        verbose_name = 'Colaborador Externo'
        verbose_name_plural = 'Colaboradores Externos'
        ordering = ['nome']

    def __str__(self):
        return str(self.nome)

    def get_absolute_url(self):
        return '{}{}{}'.format(settings.SITE_URL, '/admin/projetos_ensino/colaboradorexterno/', self.id)


class RegistroFrequencia(models.ModelPlus):
    projeto = models.ForeignKeyPlus(Projeto, on_delete=models.CASCADE)
    descricao = models.CharFieldPlus(verbose_name='Descrição', max_length=2000)
    data = models.DateFieldPlus('Data')
    carga_horaria = models.PositiveIntegerField('Carga Horária', null=True, blank=True)
    cadastrada_por = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Cadastrado por', null=True, blank=True, related_name='projetos_ensino_cadastro_registrofrequencia'
    )
    cadastrada_em = models.DateTimeFieldPlus(verbose_name='Cadastrado em', null=True)
    atendida = models.BooleanField(verbose_name='Atendida', null=True)
    validada_por = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Avaliada por', null=True, blank=True, related_name='projetos_ensino_avaliacao_registrofrequencia'
    )
    validada_em = models.DateTimeFieldPlus(verbose_name='Avaliada em', null=True)

    class Meta:
        verbose_name = 'Registro de Frequência/Atividade do Projeto'
        verbose_name_plural = 'Registros de Frequência/Atividade do Projeto'

    def __str__(self):
        return 'Registro de Frequência/Atividade do Projeto'


class AvaliadorExterno(models.ModelPlus):
    nome = models.CharField('Nome', max_length=255)
    vinculo = models.OneToOneField('comum.Vinculo', related_name='proj_ensino_avaliador_externo_vinculo', on_delete=models.CASCADE, null=True)
    ativo = models.BooleanField('Ativo', default=True)
    email = models.EmailField('Email')
    telefone = models.CharFieldPlus('Telefone', max_length=255, null=True, blank=True)
    titulacao = models.ForeignKeyPlus(
        'rh.Titulacao', verbose_name='Titulação', related_name='proj_ensino_avaliador_instituicao', on_delete=models.CASCADE
    )
    instituicao_origem = models.ForeignKeyPlus(
        'rh.Instituicao',
        blank=True,
        null=True,
        verbose_name='Instituição',
        related_name='proj_ensino_instituicao_avaliador',
        on_delete=models.CASCADE,
    )
    lattes = models.URLField(blank=True)

    class Meta:
        verbose_name = 'Avaliador Externo'
        verbose_name_plural = 'Avaliadores Externos'

    def __str__(self):
        return str(self.nome)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        grupo = Group.objects.get(name='Avaliador de Projetos de Ensino')
        if self.ativo and grupo:
            self.vinculo.user.groups.add(grupo)
        else:
            self.vinculo.user.groups.remove(grupo)


class CampusAdicional(models.ModelPlus):
    usuario = models.ForeignKeyPlus(User, verbose_name='Usuário', editable=False)
    campus = models.ManyToManyFieldPlus('rh.UnidadeOrganizacional', verbose_name='Campi adicioniais', blank=True)

    class Meta:
        verbose_name = 'Campus adicional'
        verbose_name_plural = 'Campi adicionais'

    def __str__(self):
        return str(self.usuario)

    @staticmethod
    def sincronizar_campi_adicionais():
        # Demanda 2051
        # - Apenas para o grupo "Coordenador de Projetos de Ensino"
        group = Group.objects.get(name='Coordenador de Projetos de Ensino')
        usuarios = group.user_set.all()

        CampusAdicional.objects.exclude(usuario__in=usuarios).delete()

        for usuario in usuarios:
            _uo_adicional, _ = CampusAdicional.objects.get_or_create(usuario=usuario)

    @staticmethod
    def get_campi_user(user, retornar_apenas_ids=False):
        uo = get_uo(user)
        campus_adicional = CampusAdicional.objects.filter(usuario=user).first()
        ids_uos = []

        if campus_adicional:
            ids_uos = list(campus_adicional.campus.values_list('id', flat=True))

        if uo and uo.id not in ids_uos:
            ids_uos.append(uo.id)

        if retornar_apenas_ids:
            return ids_uos

        return UnidadeOrganizacional.objects.uo().filter(id__in=ids_uos)

    def get_campi(self):
        # Campus do usuário + campi adicionais
        uos = [get_uo(self.usuario)]
        uos_adicionais = self.campus.all()
        for uo in uos_adicionais:
            if uo not in uos:
                uos.append(uo)
        return uos
