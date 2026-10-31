from __future__ import annotations

import datetime
import tempfile
import traceback
from collections import OrderedDict
from datetime import timedelta
from decimal import Decimal

from tinymce.models import HTMLField
from dateutil.relativedelta import relativedelta
from django.apps import apps
from django.conf import settings
from django.contrib.auth.models import Group
from django.contrib.contenttypes.fields import ContentType
from django.core.files.storage import default_storage
from django.core.validators import MaxLengthValidator
from django.db import transaction
from django.db.models import Count, Q, QuerySet, Sum
from django.utils.html import format_html

from comum.models import Arquivo, ObjetivoDesenvolvimentoSustentavel, SubobjetivoDesenvolvimentoSustentavel, User, Vinculo
from comum.utils import get_uo, tl
from djtools import forms
from djtools.db import models
from djtools.templatetags.filters import format_
from djtools.utils import print_
from edu.models import Aluno, AtividadePraticaProfissional, ModalidadePraticaProfissional, SituacaoMatricula
from financeiro.models import NaturezaDespesa
from projetos import help_text
from rh.models import Servidor, Situacao, UnidadeOrganizacional, Titulacao

GRUPOS_EXTENSAO_INSTITUCIONAIS = ['Pré-Avaliador Sistêmico de Projetos de Extensão', 'Visualizador de Projetos', 'Auditor']


def campus_do_coordenador_extensao(user: User) -> UnidadeOrganizacional | None:
    """Campus a que o usuário fica restrito por ser Coordenador de Extensão, papel local (#17520).

    ``None`` quando ele não é Coordenador de Extensão ou também tem papel institucional (gerente sistêmico,
    Pré-Avaliador Sistêmico, Visualizador de Projetos, Auditor): esses enxergam todos os campi.
    """
    if not user.has_group_cached('Coordenador de Extensão'):
        return None
    if user.has_perm('projetos.pode_gerenciar_edital') or user.has_group_cached(GRUPOS_EXTENSAO_INSTITUCIONAIS):
        return None
    return get_uo(user)


def eh_planejamento(obj):
    hoje = datetime.datetime.now()
    if obj.data_cadastro is None:
        return False
    if isinstance(obj, Meta | Desembolso | ItemMemoriaCalculo):
        if obj.projeto.edital.tipo_edital == Edital.EXTENSAO_FLUXO_CONTINUO:
            return bool(obj.projeto.data_avaliacao and obj.data_cadastro <= obj.projeto.data_avaliacao)

        else:
            if hoje > obj.projeto.edital.fim_inscricoes:
                return obj.data_cadastro <= obj.projeto.edital.fim_inscricoes
    elif isinstance(obj, Etapa):
        if obj.meta.projeto.edital.tipo_edital == Edital.EXTENSAO_FLUXO_CONTINUO:
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
        return self.filter(publicado=True, inicio_inscricoes__lte=hoje, fim_inscricoes__gte=hoje, autorizado=True)

    def em_pre_avaliacao(self):
        hoje = datetime.datetime.now()
        qs = self.filter(inicio_pre_selecao__lte=hoje, inicio_selecao__gt=hoje) | self.filter(
            tipo_edital=Edital.EXTENSAO_FLUXO_CONTINUO, inicio_inscricoes__lte=hoje, fim_selecao__gte=hoje
        )
        return qs.filter(tipo_fomento=Edital.FOMENTO_INTERNO)

    def em_avaliacao(self):
        hoje = datetime.datetime.now()
        return self.filter(inicio_selecao__lte=hoje, divulgacao_selecao__gte=hoje, tipo_fomento=Edital.FOMENTO_INTERNO)

    def em_selecao(self):
        hoje = datetime.datetime.now()
        return self.filter(inicio_selecao__lte=hoje, fim_selecao__gte=hoje, tipo_fomento=Edital.FOMENTO_INTERNO)

    def em_periodo_indicar_pre_avaliador(self):
        hoje = datetime.datetime.now()
        qs = (
            self.filter(inicio_inscricoes__lte=hoje, inicio_selecao__gt=hoje)
            | self.filter(tipo_edital=Edital.EXTENSAO_FLUXO_CONTINUO, inicio_inscricoes__lte=hoje, fim_selecao__gte=hoje)
            | self.filter(tipo_fomento=Edital.FOMENTO_EXTERNO, inicio_inscricoes__lte=hoje, fim_inscricoes__gte=hoje)
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

    def em_recurso(self):
        hoje = datetime.datetime.now()
        return self.filter(inicio_pre_selecao__lt=hoje, data_recurso__gt=hoje)

    def em_avaliacao_recursos(self):
        hoje = datetime.datetime.now()
        return self.filter(divulgacao_selecao__gt=hoje, fim_selecao__lt=hoje)


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


class FocoTecnologicoManager(models.Manager):
    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(ativo=True)


class ParticipacaoManagerAtivo(models.Manager):
    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(ativo=True)


class ParticipacaoManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related('vinculo_pessoa')


class AreaConhecimentoManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related('superior')


class ItemMemoriaCalculoManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related('despesa')


class AreaTematica(models.ModelPlus):
    SEARCH_FIELDS = ['descricao']
    descricao = models.CharField('Descrição', max_length=100)
    vinculo = models.ManyToManyFieldPlus('comum.Vinculo')

    class Meta:
        verbose_name = 'Área Temática'
        verbose_name_plural = 'Áreas Temáticas'

    def __str__(self):
        return self.descricao


class Tema(models.ModelPlus):
    SEARCH_FIELDS = ['descricao', 'areatematica__descricao']
    descricao = models.TextField('Descrição', max_length=255)
    areatematica = models.ForeignKeyPlus(AreaTematica, verbose_name='Área Temática', null=True, blank=True, on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Tema'
        verbose_name_plural = 'Temas'

    def __str__(self):
        return self.descricao


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
    SEARCH_FIELDS = ['titulo', 'descricao']

    EXTENSAO_FLUXO_CONTINUO = '4'
    EXTENSAO = '1'

    TIPO_EDITAL_EXTENSAO = ((EXTENSAO, 'Extensão'), (EXTENSAO_FLUXO_CONTINUO, 'Extensão Contínuo'))
    TIPO_EDITAL_CHOICES = TIPO_EDITAL_EXTENSAO
    CAMPUS = '1'
    TEMA = '2'
    GERAL = '3'
    GRUPO = '4'
    TIPO_FORMA_SELECAO_CHOICES = ((CAMPUS, 'Campus'), (TEMA, 'Tema'), (GERAL, 'Geral'), (GRUPO, 'Grupo'))

    FOMENTO_INTERNO = 'Interno'
    FOMENTO_EXTERNO = 'Externo'

    TIPO_FOMENTO_CHOICES = ((FOMENTO_INTERNO, FOMENTO_INTERNO), (FOMENTO_EXTERNO, FOMENTO_EXTERNO))
    SEM_ANUENCIA = 'Não'
    COORD_TAES = 'Apenas de coordenadores TAES'
    TODOS_COORD = 'De todos os Coordenadores'
    TODOS_TAES = 'De todos os TAES'
    TODOS = 'De todos os servidores'
    ANUENCIA_CHOICES = (
        (SEM_ANUENCIA, SEM_ANUENCIA),
        (COORD_TAES, COORD_TAES),
        (TODOS_COORD, TODOS_COORD),
        (TODOS_TAES, TODOS_TAES),
        (TODOS, TODOS),
    )

    objects = EditalManager()

    titulo = models.CharField('Título', max_length=255)
    descricao = models.TextField('Descrição')
    tipo_fomento = models.CharFieldPlus('Tipo do Fomento', max_length=10, choices=TIPO_FOMENTO_CHOICES, default=FOMENTO_INTERNO)
    tipo_edital = models.CharField('Tipo do Edital', max_length=10, choices=TIPO_EDITAL_CHOICES)
    forma_selecao = models.CharField('Forma de Seleção', max_length=10, choices=TIPO_FORMA_SELECAO_CHOICES, default=CAMPUS)
    campus_especifico = models.BooleanField(
        'Edital de Campus',
        default=False,
        help_text='Caso esta opção seja marcada, os projetos deste edital poderão ser avaliados por servidores do mesmo campus do projeto',
    )
    qtd_projetos_selecionados = models.PositiveIntegerField(
        'Quantidade de Projetos Selecionados', help_text='Número máximo de projetos selecionados', null=True, default=1
    )
    inicio_inscricoes = models.DateTimeFieldPlus('Início das Inscrições')
    fim_inscricoes = models.DateTimeFieldPlus('Fim das Inscrições')
    arquivo = models.OneToOneField(Arquivo, null=True, blank=True, on_delete=models.CASCADE)
    inicio_pre_selecao = models.DateTimeFieldPlus('Início da Pré-Seleção', null=True)
    fim_pre_selecao = models.DateTimeFieldPlus('Fim da Pré-Seleção', null=True, blank=True)
    data_recurso_pre_selecao = models.DateTimeFieldPlus('Data Limite Para Recursos da Pré-Seleção', null=True, blank=True)
    inicio_selecao = models.DateTimeFieldPlus('Início da Seleção', null=True)
    fim_selecao = models.DateTimeFieldPlus('Fim da Seleção', null=True)
    data_recurso = models.DateTimeFieldPlus('Data Limite Para Recursos', null=True, blank=True)
    divulgacao_selecao = models.DateTimeFieldPlus('Divulgação da Seleção', null=True)
    participa_aluno = models.BooleanField('Participa Aluno', help_text='Marque esta opção caso alunos possam participar do projeto', default=False)
    participa_servidor = models.BooleanField(
        'Participa Servidor', help_text='Marque esta opção caso servidores possam participar do projeto', default=False
    )
    inclusao_bolsas_ae = models.DateTimeFieldPlus('Data da geração das bolsas no AE', null=True)
    valor_financiado_por_projeto = models.DecimalFieldPlus('Valor Financiado por Projeto', default=Decimal('0.0'))
    exige_licoes_aprendidas = models.BooleanField(
        'Exige Lições Aprendidas',
        help_text='Marque esta opção caso seja necessário que os coordenadores dos projetos cadastrem as lições aprendidas',
        default=False,
    )
    data_avaliacao_classificacao = models.DateTimeFieldPlus('Data de Avaliação da Classificação', null=True, blank=True)
    exige_avaliacao_aluno = models.BooleanField(
        'Exige Avaliações dos Alunos',
        help_text='Marque esta opção caso seja necessário que os coordenadores dos projetos avaliem os alunos',
        default=False,
    )
    ano_inicial_projeto_pendente = models.CharField(
        'Pode Submeter com Projeto Pendente a Partir do Ano?', max_length=5, null=True, blank=True, help_text=help_text.ano_inicial_projeto_pendente
    )
    temas = models.ManyToManyFieldPlus('projetos.Tema', blank=True)

    permite_colaborador_voluntario = models.BooleanField(
        'Permite Colaborador Externo',
        help_text='Marque esta opção caso seja permitida a inclusão de colaborador externo nas equipes dos projetos',
        default=False,
    )
    permite_colaborador_voluntario_artes = models.BooleanField(
        'Permite Voluntário Vinculado ao Núcleo de Arte',
        help_text='Marque esta opção caso seja permitida a inclusão de colaborador externo vinculado ao núcleo de arte nas equipes dos projetos',
        default=False,
    )
    permite_indicacao_tardia_equipe = models.BooleanField(
        'Permite Cadastrar Aluno sem Identificá-lo',
        help_text='Marque esta opção para permitir que o coordenador do projeto possa registar a participação de alunos na equipe durante a submissão do projeto mas sem indicar especificamente quais alunos serão',
        default=False,
    )
    atividade_todo_mes = models.BooleanField(
        'Atividade Todo Mês',
        default=False,
        help_text='Marque esta opção se for obrigatória a execução de pelo menos uma atividade em cada mês de duração do projeto.',
    )
    prazo_atividade = models.IntegerField(
        'Prazo Máximo de Cada Atividade (em dias)',
        null=True,
        blank=True,
        help_text='Informe o prazo máximo de duração de cada atividade. Se não há prazo máximo, deixe este campo em branco.',
    )
    exige_frequencia_aluno = models.BooleanField(
        'Exige Registro de Frequência dos Alunos Bolsistas',
        help_text='Marque esta opção caso seja necessário que todos os alunos bolsistas tenham pelo menos um registro de frequência por mês.',
        default=False,
    )
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
    exige_anuencia = models.CharFieldPlus(
        'Exigir Anuência da Chefia',
        default=SEM_ANUENCIA,
        choices=ANUENCIA_CHOICES,
        max_length=30,
        help_text='Ao exigir para coordenadores, apenas os projetos com registro da anuência da chefia poderão avançar para a fase de pré-seleção. Já os membros da equipe só poderão ser vinculados às atividades e imprimir certificados após o registro da anuência.',
    )
    colaborador_externo_bolsista = models.BooleanField('O colaborador externo pode ser bolsista?', default=False)
    sistemico_pode_submeter = models.BooleanField(
        'Gerente Sistêmico pode submeter?',
        default=False,
        help_text='Marque esta opção para permitir que os membros do grupo "Gerente Sistêmico de Extensão" possam submeter projetos neste edital.',
    )
    cadastrado_por = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Cadastrado por', null=True, blank=True, related_name='projetos_edital_cadastrado_por'
    )
    cadastrado_em = models.DateTimeFieldPlus('Cadastrado em', null=True, auto_now_add=True)
    autorizado = models.BooleanField('Edital autorizado', default=True, null=True)

    autorizado_por = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Autorizado por', null=True, blank=True, related_name='projetos_edital_autorizado_por'
    )
    autorizado_em = models.DateTimeFieldPlus('Autorizado em', null=True)
    exige_comprovante_atividade = models.BooleanField(
        'Exige comprovante de cada atividade',
        help_text='Marque esta opção caso seja obrigatório anexar um documento de comprovação em todo registro de execução de atividade.',
        default=False,
    )
    ocultar_aba_fotos = models.BooleanField(
        'Ocultar a aba "Fotos" do projeto',
        help_text='Marque esta opção para que a aba "Fotos" não seja exibida na tela de visualização do projeto.',
        default=False,
    )
    ocultar_aba_anexos = models.BooleanField(
        'Ocultar a aba "Anexos" do projeto',
        help_text='Marque esta opção para que a aba "Anexos" não seja exibida na tela de visualização do projeto.',
        default=False,
    )
    ocultar_aba_prestacao_contas = models.BooleanField(
        'Ocultar a aba "Prestação de Contas" do projeto',
        help_text='Marque esta opção para que a aba "Prestação de Contas" não seja exibida na tela de visualização do projeto.',
        default=False,
    )
    responsavel_pode_registrar_execucao = models.BooleanField(
        'Responsável pela atividade pode registrar execução',
        default=False,
        help_text='Marque esta opção para permitir que o responsável pela atividade também possa registrar a execução da mesma.',
    )
    exige_vinculacao_nepp = models.BooleanField(
        'Exigir vinculação ao NEPP',
        default=False,
        help_text='Marque esta opção para exigir que o coordenador do projeto informe a qual NEPP o projeto está vinculado.',
    )
    impedir_projeto_sem_anexo = models.BooleanField(
        'Impedir Projetos sem Anexos', default=False, help_text='Marque esta opção para impedir que projetos sem anexos cadastrados sejam submetidos.'
    )
    publicado = models.BooleanField(
        'Publicado?',
        default=True,
        help_text='Desmarque esta opção para ocultar este edital da lista disponível em Extensão -> Projetos -> Editais -> Editais.',
    )
    campi_liberados = models.ManyToManyFieldPlus(
        UnidadeOrganizacional, verbose_name='Campi que permitem coordenador de outro campus', related_name='projetos_campi_liberados', blank=True
    )
    permite_avaliacao_unica = models.BooleanField(
        'Permite Projetos com uma avaliação',
        help_text='Marque esta opção para permitir que os projetos recebam apenas uma avaliação. Por padrão, são exigidas pelo menos duas avaliações.',
        default=False,
    )
    id_documento_edital = models.PositiveIntegerField(verbose_name='ID do Documento do Edital', null=True, blank=True)
    exige_info_autorizacao_comites = models.BooleanField(
        'Exigir informações sobre autorizações dos Comitês',
        default=False,
        help_text='Marque esta opção para exigir que o coordenador do projeto informe se precisa de autorização dos Comitês (CEP, CEUA, SISGEN, SISBIO).',
    )

    exige_etapa_avaliacao = models.BooleanField(
        'Exige a etapa de avaliação',
        help_text='Marque esta opção para exigir a etapa de avaliação do projeto neste edital de fluxo contínuo.',
        default=False,
    )
    impede_com_pendencia_anuencia = models.BooleanField(
        'Impedir submeter sem a anuência da chefia',
        help_text='Marque esta opção para impedir que o projeto seja submetido se não tiver a anuência da chefia.',
        default=False,
    )
    impede_com_pendencia_termo = models.BooleanField(
        'Impedir submeter com termo de compromisso pendente de aceite',
        help_text='Marque esta opção para impedir que o projeto seja submetido se houver algum termo de compromisso pendente de aceite.',
        default=False,
    )
    exige_comissao = models.BooleanField(
        'Exigir Comissão de Avaliação',
        default=True,
        help_text='Marque esta opção para que apenas membros da comissão de avaliação do edital possam ser indicados como avaliadores dos projetos. Caso contrário, qualquer usuário registrado como avaliador poderá ser indicado como avaliador do projeto..',
    )
    limite_submissoes = models.PositiveIntegerFieldPlus(
        'Limite de submissões pelo mesmo coordenador',
        null=True,
        blank=True,
        help_text='Informe a quantidade máxima de submissões que podem ser feitas pelo mesmo coordenador. Se não houver limite, deixe este campo em branco.',
    )
    limite_aprovacoes = models.PositiveIntegerFieldPlus(
        'Limite de projetos aprovados de um mesmo coordenador',
        null=True,
        blank=True,
        help_text='Informe a quantidade máxima de projetos aprovados de um mesmo coordenador. Se não houver limite, deixe este campo em branco.',
    )
    exige_tema = models.BooleanField(
        'Exigir indicação do tema do projeto',
        default=True,
        help_text='Marque esta opção para que seja obrigatória a indicação do tema do projeto no momento da submissão. Caso contrário, apenas a área temática será solicitada.',
    )
    restringe_prof_temporario = models.BooleanField(
        'Restringir submissão por professor visitante/substituto',
        default=False,
        help_text='Marque esta opção para exigir que o projeto tenha na equipe pelo menos um servidor efetivo caso o coordenador seja um professor visitante ou substituto.',
    )
    exige_nivel_superior = models.BooleanField(
        'Exigir coordenador com nível superior',
        default=False,
        help_text='Marque esta opção para exigir que apenas coordenadores com nível superior possam submeter projetos.',
    )
    coordenador_pode_receber_bolsa = models.BooleanField('Coordenador pode receber bolsa', default=True)
    prazo_aceite_indicacao = models.IntegerField(
        'Prazo para Aceite da Indicação (em dias)',
        null=True,
        blank=True,
        help_text='Informe o prazo máximo, em dias, para que um avaliador indicado registre que aceita a indicação. Se não há prazo máximo, deixe este campo em branco.',
    )
    prazo_avaliacao = models.IntegerField(
        'Prazo para Avaliar Projeto (em dias)',
        null=True,
        blank=True,
        help_text='Informe o prazo máximo, em dias, após o registro de aceite, para que o avaliador faça a avaliação do projeto. Se não há prazo máximo, deixe este campo em branco.',
    )

    class Meta:
        verbose_name = 'Edital'
        verbose_name_plural = 'Editais'
        ordering = ['-inicio_inscricoes']

    def __str__(self):
        if self.tipo_edital == Edital.EXTENSAO_FLUXO_CONTINUO:
            return f'{self.titulo} - Edital de Fluxo {self.get_tipo_edital_display()}'
        else:
            return f'{self.titulo} - Edital de {self.get_tipo_edital_display()}'

    @classmethod
    def get_tipos_edital_extensao(self):
        return next(zip(*Edital.TIPO_EDITAL_EXTENSAO, strict=False))

    def sinaliza_aprovacao_pos_recurso(self, qs, reprovados_manualmente):
        ids_para_marcar = qs.filter(aprovado=True).order_by('-classificacao').values_list('id', flat=True)[:reprovados_manualmente]
        if ids_para_marcar:
            Projeto.objects.filter(id__in=list(ids_para_marcar)).update(aprovado_pos_recurso=True)

    def classifica_projetos_extensao(self, uo=None, grupo=None):
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
            tad[d['projeto__id']]['criterio_sum_pontos'].append(d['criterio_sum_pontos'] or 0.00)
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
        limite_aprovacoes = self.limite_aprovacoes
        dict_aprovacoes = {}
        ids_excluidos = []
        project_ids = [item[0] for item in tad]
        projetos_map = Projeto.objects.in_bulk(project_ids)

        for item in tad:
            projeto_atual = projetos_map.get(item[0])
            if not projeto_atual:
                continue

            if limite_aprovacoes:
                if str(projeto_atual.vinculo_coordenador.id) in dict_aprovacoes:
                    if dict_aprovacoes[f'{projeto_atual.vinculo_coordenador.id}'] >= limite_aprovacoes:
                        ids_excluidos.append(projeto_atual.id)
                    else:
                        dict_aprovacoes[f'{projeto_atual.vinculo_coordenador.id}'] += 1
                else:
                    dict_aprovacoes[f'{projeto_atual.vinculo_coordenador.id}'] = 1
            contador += 1
            Projeto.objects.filter(id=item[0]).update(classificacao=contador)

        if self.forma_selecao == Edital.TEMA:
            qs_base = Projeto.objects.filter(edital=self, pontuacao__gt=0).order_by('classificacao')
            qs = None
            reprovados_manualmente = qs_base.exclude(reprovacao_manual_em=None).count()
            qs_base.update(aprovado=False, aprovado_pos_recurso=False)
            qs_base = qs_base.exclude(id__in=ids_excluidos).filter(reprovacao_manual_em=None)
            ofertas = OfertaProjetoPorTema.objects.filter(edital=self)
            for oferta in ofertas:
                if oferta.tema:
                    qs = qs_base.filter(tema=oferta.tema)
                else:
                    qs = qs_base.filter(area_tematica=oferta.area_tematica)
                for projeto in qs[0 : oferta.selecionados]:
                    projeto.aprovado = projeto.atingiu_ponto_de_corte()
                    projeto.save()

        elif self.forma_selecao == Edital.GRUPO:
            qs = Projeto.objects.filter(edital=self, grupo=grupo, pontuacao__gt=0).order_by('classificacao')
            reprovados_manualmente = qs.exclude(reprovacao_manual_em=None).count()
            qs.update(aprovado=False, aprovado_pos_recurso=False)
            qs = qs.exclude(id__in=ids_excluidos).filter(reprovacao_manual_em=None)
            qtd_selecionados = grupo.selecionados
            for projeto in qs[0:qtd_selecionados]:
                projeto.aprovado = projeto.atingiu_ponto_de_corte()
                projeto.save()

        elif self.forma_selecao == Edital.GERAL:
            qs = Projeto.objects.filter(edital=self, pontuacao__gt=0).order_by('classificacao')
            reprovados_manualmente = qs.exclude(reprovacao_manual_em=None).count()
            qs.update(aprovado=False, aprovado_pos_recurso=False)
            qs = qs.exclude(id__in=ids_excluidos).filter(reprovacao_manual_em=None)
            qtd_selecionados = self.qtd_projetos_selecionados
            for projeto in qs[0:qtd_selecionados]:
                projeto.aprovado = projeto.atingiu_ponto_de_corte()
                projeto.save()

        else:  # Edital.CAMPUS - Máx. de Projetos selecionados para a uo
            qs = Projeto.objects.filter(edital=self, uo=uo, pontuacao__gt=0).order_by('classificacao')
            reprovados_manualmente = qs.exclude(reprovacao_manual_em=None).count()
            qs.update(aprovado=False, aprovado_pos_recurso=False)
            qs = qs.exclude(id__in=ids_excluidos).filter(reprovacao_manual_em=None)

            qtd_selecionados = self.ofertaprojeto_set.get(uo=uo).qtd_selecionados
            for projeto in qs[0:qtd_selecionados]:
                projeto.aprovado = projeto.atingiu_ponto_de_corte()
                projeto.save()

        if reprovados_manualmente and qs:
            self.sinaliza_aprovacao_pos_recurso(qs, reprovados_manualmente)

    def exige_termo_coordenador(self):
        return self.termo_compromisso_coordenador not in ['', None]

    def exige_termo_servidor(self):
        return self.termo_compromisso_servidor not in ['', None]

    def exige_termo_aluno(self):
        return self.termo_compromisso_aluno not in ['', None]

    def exige_termo_colaborador(self):
        return self.termo_compromisso_colaborador_voluntario not in ['', None]

    def eh_fomento_interno(self):
        return self.tipo_fomento == Edital.FOMENTO_INTERNO

    def get_elementos_despesa(self):
        return NaturezaDespesa.objects.filter(id__in=self.recurso_set.values_list('despesa_id', flat=True))

    def get_uos(self):
        return UnidadeOrganizacional.objects.suap().filter(id__in=self.ofertaprojeto_set.values_list('uo', flat=True))

    def get_oferta_por_avaliador(self) -> list[list[UnidadeOrganizacional | bool]]:
        user = tl.get_user()
        indicacoes = AvaliadorIndicado.objects.filter(vinculo=user.get_vinculo(), projeto__edital=self)
        # O campus segue listado (leva à "Indicação rejeitada"), mas só a indicação não rejeitada de projeto
        # pré-aprovado o deixa pendente: a pré-seleção cancelada não apaga a indicação (#17574).
        avaliaveis = indicacoes.filter(rejeitado=False, projeto__pre_aprovado=True).values_list('projeto', flat=True)
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
        indicacoes = AvaliadorIndicado.objects.filter(
            vinculo=user.get_vinculo(), projeto__edital=self, projeto__pre_aprovado=True, rejeitado=False
        ).values_list('projeto', flat=True)
        avalicoes_realizadas = Avaliacao.objects.filter(projeto__in=indicacoes, vinculo=user.get_vinculo()).values_list('projeto', flat=True)
        return Projeto.objects.filter(id__in=indicacoes).exclude(id__in=avalicoes_realizadas).exists()

    def get_focos_tecnologicos(self):
        ids = []
        for oferta in self.ofertaprojeto_set.all():
            for foco in oferta.focos_tecnologicos.all():
                if foco.id not in ids:
                    ids.append(foco.id)
        return FocoTecnologico.objects.filter(id__in=ids)

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
            if not Participacao.objects.filter(
                projeto__edital__id=edital.id, projeto__pre_aprovado=True, responsavel=True, vinculo_pessoa=user.get_vinculo()
            ):
                editais.append(edital)
        return editais

    def get_form(self):
        edital = self

        class CustomForm(forms.FormPlus):
            fieldsets = (('titulo', {'fields': ('item_1', 'item_2')}),)

            def clean(self):
                super().clean()
                for valor_parametro in list(self.cleaned_data.values()):
                    if valor_parametro < 0:
                        raise forms.ValidationError('Os valores não podem ser negativos.')
                return self.cleaned_data

            def save(self):
                for field_name, valor_parametro in list(self.cleaned_data.items()):
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
        for titulo, fields in list(fieldsets.items()):
            grupos.append((titulo, {'fields': fields}))
        CustomForm.fieldsets = grupos
        return CustomForm

    def pode_divulgar_resultado(self):
        hoje = datetime.datetime.now()
        return self.divulgacao_selecao <= hoje and self.fim_selecao < hoje

    def pode_divulgar_resultado_parcial(self):
        hoje = datetime.datetime.now()
        return self.divulgacao_selecao and self.fim_selecao and hoje <= self.divulgacao_selecao and self.fim_selecao < hoje

    @transaction.atomic
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    def is_periodo_inscricao(self):
        hoje = datetime.datetime.now()
        return self.inicio_inscricoes <= hoje <= self.fim_inscricoes

    def is_periodo_fim_inscricao(self):
        hoje = datetime.datetime.now()
        if self.tipo_edital == Edital.EXTENSAO_FLUXO_CONTINUO:
            return self.fim_inscricoes <= hoje
        return self.fim_inscricoes < hoje < self.inicio_pre_selecao

    def is_periodo_antes_pre_selecao(self):
        if not self.eh_fomento_interno():
            return False
        hoje = datetime.datetime.now()
        return self.inicio_inscricoes < hoje < self.inicio_pre_selecao

    def is_periodo_pre_selecao(self):
        hoje = datetime.datetime.now()
        if self.tipo_edital == Edital.EXTENSAO_FLUXO_CONTINUO:
            return self.inicio_inscricoes <= hoje < self.fim_selecao
        return self.inicio_pre_selecao <= hoje < self.inicio_selecao

    def is_periodo_selecao(self):
        if self.tipo_fomento == Edital.FOMENTO_EXTERNO:
            return False
        hoje = datetime.datetime.now()
        return self.inicio_selecao <= hoje < self.fim_selecao

    def is_periodo_selecao_e_pre_divulgacao(self):
        hoje = datetime.datetime.now()
        if self.tipo_edital == Edital.EXTENSAO_FLUXO_CONTINUO:
            return self.inicio_selecao <= hoje < self.fim_selecao
        return self.inicio_selecao <= hoje < self.divulgacao_selecao

    def is_periodo_divulgacao(self):
        hoje = datetime.datetime.now()
        return self.divulgacao_selecao and self.divulgacao_selecao <= hoje

    def is_periodo_pos_selecao(self):
        hoje = datetime.datetime.now()
        return self.fim_selecao and hoje > self.fim_selecao

    def num_total_projetos_pre_aprovados(self, uo=None):
        """
        Retorna a quantidade de projetos pré-selecionados
        """
        if uo:
            return Projeto.objects.filter(edital=self, uo=uo, pre_aprovado=True).aggregate(Count('id'))['id__count']
        return Projeto.objects.filter(edital=self, pre_aprovado=True).aggregate(Count('id'))['id__count']

    def num_total_projetos_isncritos(self, uo=None):
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

    def get_ofertas_projeto_por_tema(self):
        return OfertaProjetoPorTema.objects.filter(edital=self).order_by('area_tematica')

    def get_ofertas_projeto_por_grupo(self):
        return OfertaProjetoPorGrupo.objects.filter(edital=self).order_by('grupo')

    def get_forma_selecao(self):
        if self.forma_selecao == Edital.CAMPUS:
            return 'Por Campus'
        elif self.forma_selecao == Edital.TEMA:
            return 'Por Tema'
        elif self.forma_selecao == Edital.GERAL:
            return 'Geral'
        elif self.forma_selecao == Edital.GRUPO:
            return 'Por Grupo'

    def eh_edital_continuo(self):
        return self.tipo_edital == Edital.EXTENSAO_FLUXO_CONTINUO

    def get_criterios_de_avaliacao(self):
        return self.criterioavaliacao_set.order_by('ordem_desempate')

    def get_data_limite_anuencia(self):
        if self.tipo_fomento == Edital.FOMENTO_EXTERNO or self.tipo_edital == Edital.EXTENSAO_FLUXO_CONTINUO:
            return self.fim_inscricoes
        else:
            return self.inicio_pre_selecao

    def pode_notificar_servidores(self):
        return self in Edital.objects.all().em_inscricao() and OfertaProjeto.objects.filter(edital=self).exists()

    def atingiu_limite_submissoes(self, vinculo):
        if self.limite_submissoes:
            return (
                Projeto.objects.filter(vinculo_coordenador=vinculo, edital=self).exclude(data_conclusao_planejamento=None).count()
                >= self.limite_submissoes
            )
        return False

    def atingiu_limite_aprovacoes(self, vinculo):
        if self.limite_aprovacoes:
            return (
                Projeto.objects.filter(
                    edital=self,
                    pre_aprovado=True,
                    aprovado=True,
                    vinculo_coordenador=vinculo,
                ).count()
                >= self.limite_aprovacoes
            )
        return False

    def pode_pre_visualizar_resultado(self, user):
        return user.has_perm('projetos.pode_gerenciar_edital') and self.is_periodo_selecao()

    def pode_visualizar_resultado(self, user, periodo):
        if periodo == 1 and self.pode_divulgar_resultado():
            return True
        if periodo == 2:
            return self.pode_divulgar_resultado_parcial() or self.pode_pre_visualizar_resultado(user)
        return False

    def tem_arquivo(self):
        return EditalArquivo.objects.filter(edital=self).exists()

    def arquivo_mais_recente(self):
        return EditalArquivo.objects.filter(edital=self).order_by('-data_cadastro')[0]

    @transaction.atomic
    def clonar_edital(
        self,
        request,
        titulo,
        descricao,
        clona_anexos_edital,
        clona_anexos_projetos,
        clona_tema,
        clona_fontes_recursos,
        clona_plano_oferta_campus,
        clona_plano_oferta_tema,
        clona_criterios_avaliacao,
    ):
        edital_clonado = Edital.objects.get(id=self.id)
        edital_clonado.id = None
        edital_clonado.titulo = titulo
        edital_clonado.descricao = descricao
        edital_clonado.autorizado_por = None
        edital_clonado.arquivo = None
        edital_clonado.cadastrado_por = request.user.get_vinculo()
        edital_clonado.cadastrado_em = datetime.datetime.now()
        if request.user.has_group_cached('Coordenador de Extensão'):
            edital_clonado.autorizado = None
        edital_clonado.save()

        if clona_anexos_edital:
            for anexo in EditalAnexoAuxiliar.objects.filter(edital=self):
                anexo.id = None
                anexo.edital = edital_clonado
                anexo.arquivo = None
                anexo.save()

        if clona_anexos_projetos:
            for anexo in EditalAnexo.objects.filter(edital=self):
                anexo.id = None
                anexo.edital = edital_clonado
                anexo.save()

        if clona_tema:
            edital_clonado.temas.set(self.temas.all())

        if clona_fontes_recursos:
            for recurso in Recurso.objects.filter(edital=self):
                recurso.id = None
                recurso.edital = edital_clonado
                recurso.save()

        if clona_plano_oferta_campus:
            for oferta in OfertaProjeto.objects.filter(edital=self):
                oferta.id = None
                oferta.edital = edital_clonado
                oferta.save()

        if clona_plano_oferta_tema:
            for oferta in OfertaProjetoPorTema.objects.filter(edital=self):
                oferta.id = None
                oferta.edital = edital_clonado
                oferta.save()

        if clona_criterios_avaliacao:
            for criterio in CriterioAvaliacao.objects.filter(edital=self):
                criterio.id = None
                criterio.edital = edital_clonado
                criterio.save()

        return edital_clonado


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
    pontuacao_binaria = models.BooleanField(
        'Pontuação Binária?',
        default=False,
        help_text='Marque esta opção caso as únicas pontuações possíveis sejam 0 ou a pontuação máxima do critério.',
    )

    class Meta:
        verbose_name = 'Critério de Avaliação'
        verbose_name_plural = 'Critérios de Avaliação'
        ordering = ['id']

    def __str__(self):
        return self.descricao

    def pode_ser_removido(self):
        return not self.itemavaliacao_set.exists()


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
    despesa = models.ForeignKeyPlus(NaturezaDespesa, verbose_name='Despesa', on_delete=models.CASCADE)
    eh_vinculada_cartao_pesquisador = models.BooleanField('É vinculada ao cartão pesquisador?', default=False)

    class Meta:
        verbose_name = 'Investimento'
        verbose_name_plural = 'Investimentos'
        ordering = ['despesa__nome']

    def __str__(self):
        return f'{self.despesa} / {self.origem} '


class FocoTecnologico(models.ModelPlus):
    descricao = models.CharField('Descrição', max_length=255)
    ativo = models.BooleanField('Ativo', default=True)
    campi = models.ManyToManyFieldPlus(
        UnidadeOrganizacional,
        verbose_name='Campi',
        blank=True,
        help_text='Informe os campi aos quais este foco tecnológico se relaciona. Esse campo é opcional e meramente informativo.',
    )

    ativos = FocoTecnologicoManager()
    objects = models.Manager()

    class Meta:
        verbose_name = 'Foco Tecnológico'
        verbose_name_plural = 'Focos Tecnológicos'

    def __str__(self):
        return self.descricao


class OfertaProjeto(models.ModelPlus):
    edital = models.ForeignKeyPlus(Edital, on_delete=models.CASCADE)
    uo = models.ForeignKeyPlus(UnidadeOrganizacional, verbose_name='Campus', on_delete=models.CASCADE)
    qtd_aprovados = models.PositiveIntegerField(
        'Pré-Selecionados', help_text='Informe quantos projetos poderão ser pré-selecionados pelo coordenador do respectivo campus', null=True
    )
    qtd_selecionados = models.PositiveIntegerField('Selecionados', help_text='Informe quantos projetos serão selecionados.', null=True)

    class Meta:
        indexes = [models.Index(fields=['edital', 'uo'], name='projetos_ofertaprojeto_indexes')]
        verbose_name = 'Oferta de Projeto'
        verbose_name_plural = 'Ofertas de Projeto'

    def __str__(self):
        return f'Oferta: {self.edital} - {self.uo}'

    @property
    def focos_tecnologicos(self):
        return FocoTecnologico.ativos.filter(campi=self.uo)


class TipoVinculo:
    BOLSISTA = 'Bolsista'
    VOLUNTARIO = 'Voluntário'
    TIPOS = ((VOLUNTARIO, 'Não'), (BOLSISTA, 'Sim'))


class EditalAnexo(models.ModelPlus):
    SERVIDOR_DOCENTE = '1'
    ALUNO = '2'
    COORDENADOR_DOCENTE = '3'
    COORDENADOR_TECNICO_ADMINISTRATIVO = '4'
    SERVIDOR_ADMINISTRATIVO = '5'
    COLABORADOR_VOLUNTARIO = '6'
    COORDENADOR_DOCENTE_VISITANTE = '7'
    SERVIDOR_DOCENTE_VISITANTE = '8'

    TIPO_MEMBRO = (
        (SERVIDOR_DOCENTE, 'Docente'),
        (SERVIDOR_ADMINISTRATIVO, 'Técnico Administrativo'),
        (ALUNO, 'Aluno'),
        (COORDENADOR_DOCENTE, 'Coordenador Docente'),
        (COORDENADOR_TECNICO_ADMINISTRATIVO, 'Coordenador Técnico Administrativo'),
        (COLABORADOR_VOLUNTARIO, 'Colaborador Externo'),
        (COORDENADOR_DOCENTE_VISITANTE, 'Coordenador(a) Professor(a) Visitante'),
        (SERVIDOR_DOCENTE_VISITANTE, 'Professor(a) Visitante'),
    )
    BOLSISTA = 'Bolsista'
    VOLUNTARIO = 'Voluntário'

    TIPOS_VINCULO = ((BOLSISTA, BOLSISTA), (VOLUNTARIO, VOLUNTARIO))
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


class AreaConhecimento(models.ModelPlus):
    superior = models.ForeignKeyPlus('projetos.AreaConhecimento', null=True, verbose_name='Superior')
    codigo = models.CharField('Código', max_length=8, unique=True)
    descricao = models.CharField('Descrição', max_length=255)

    objects = AreaConhecimentoManager()

    class Meta:
        verbose_name = 'Área do Conhecimento'
        verbose_name_plural = 'Áreas de Conhecimento'

    def __str__(self):
        if self.superior:
            return f'{self.descricao} ({self.superior!s})'
        else:
            return f'{self.descricao}'


class Projeto(models.ModelPlus):
    INTERNO = 'INTERNO'
    EXTERNO = 'EXTERNO'
    AMBOS = 'AMBOS'
    PUBLICO_ALVO_CHOICES = ((INTERNO, 'Interno'), (EXTERNO, 'Externo'), (AMBOS, 'Ambos'))

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
    STATUS_NAO_PRE_SELECIONADO_EM = 'Não pré-selecionado em'
    STATUS_SELECIONADO_EM = 'Selecionado em'
    STATUS_NAO_SELECIONADO_EM = 'Não selecionado em'
    STATUS_AGUARDADO_ENVIO_PROJETO = 'Aguardando o envio do projeto'

    edital = models.ForeignKeyPlus(Edital, verbose_name='Edital')
    uo = models.ForeignKeyPlus(UnidadeOrganizacional, verbose_name='Campus')
    titulo = models.CharField('Título do projeto', max_length=255)

    # PROEX
    area_conhecimento = models.ForeignKeyPlus(AreaConhecimento, verbose_name='Área do Conhecimento', null=True, blank=True)
    area_tematica = models.ForeignKeyPlus(AreaTematica, verbose_name='Área Temática', null=True, blank=True)
    tema = models.ForeignKeyPlus(Tema, verbose_name='Tema', null=True, blank=True)
    publico_alvo = models.CharField('Público Alvo', max_length=255, null=True, blank=True, choices=PUBLICO_ALVO_CHOICES)

    # Comum
    justificativa = HTMLField('Justificativa', help_text=help_text.justificativa)
    resumo = HTMLField('Resumo', help_text=help_text.resumo)
    objetivo_geral = HTMLField('Objetivo Geral', help_text=help_text.objetivo_geral)
    metodologia = HTMLField('Metodologia da execução do projeto', help_text=help_text.metodologia)
    acompanhamento_e_avaliacao = HTMLField('Acompanhamento e avaliação do projeto durante a execução', help_text=help_text.acompanhamento)
    resultados_esperados = HTMLField('Disseminação dos Resultados', help_text=help_text.disseminacao_resultados)

    inicio_execucao = models.DateFieldPlus('Início da Execução')
    fim_execucao = models.DateFieldPlus('Término da Execução')
    vinculo_coordenador = models.ForeignKey(
        'comum.Vinculo',
        verbose_name='Coordenador do Projeto',
        related_name='projeto_vinculo_coordenador_set',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    possui_cunho_social = models.BooleanField(
        'Possui Cunho Social',
        default=False,
        help_text='Projetos de ações inclusivas e de tecnologias sociais, preferencialmente, para populações e comunidades em situação de risco, incluindo serviços tecnológicos e projetos de extensão.',
    )

    # avaliacao
    pre_aprovado = models.BooleanField('Pré-selecionado', default=False)
    data_pre_avaliacao = models.DateField('Data da Pré-seleção', null=True, blank=True)
    vinculo_autor_pre_avaliacao = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Responsável pela Pré-seleção', null=True, blank=True, related_name='pre_vinculo_avaliador'
    )
    aprovado = models.BooleanField('Selecionado', default=False)
    aprovado_na_distribuicao = models.BooleanField('Selecionado na distribuição de bolsas', default=False, blank=False)
    data_avaliacao = models.DateField('Data da seleção', null=True, blank=True)
    vinculo_autor_avaliacao = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Responsável pela Seleção', null=True, blank=True, related_name='vinculo_aprovador'
    )
    pontuacao = models.DecimalFieldPlus('Pontuação', default=Decimal('0'), null=True, blank=True)
    pontuacao_parcial = models.DecimalFieldPlus('Pontuação parcial', default=Decimal('0'), null=True, blank=True)
    data_conclusao_planejamento = models.DateTimeFieldPlus(
        'Data da Conclusão do Projeto', null=True, blank=True
    )  # usado se o projeto for do tipo contínuo
    data_finalizacao_conclusao = models.DateTimeFieldPlus('Data da Finalização do Projeto', null=True, blank=True)
    data_validacao_pontuacao = models.DateTimeFieldPlus('Data da Finalização do Projeto', null=True, blank=True)
    vinculo_monitor = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Responsável pelo Monitoramento', null=True, blank=True, related_name='vinculo_monitor'
    )
    classificacao = models.IntegerField('Classificação', null=True)
    nome_edital_externo = models.CharFieldPlus('Nome do Edital Externo', blank=True, null=True, max_length=500)
    valor_fomento_projeto_externo = models.DecimalFieldPlus(
        'Valor do Fomento do Projeto', default=Decimal('0.0'), help_text='Caso não tenha fomento, informe o valor 0,00.'
    )
    descricao_comprovante_gru = models.CharFieldPlus('Descrição', blank=True, null=True, max_length=5000)
    arquivo_comprovante_gru = models.FileFieldPlus(
        'Comprovante de Pagamento da GRU', max_length=1000, upload_to='upload/projetos/comprovantas_gru/', null=True, blank=True
    )
    inativado = models.BooleanField('Inativado', default=False)
    motivo_inativacao = models.CharFieldPlus('Motivo da Inativação do Projeto', max_length=5000, null=True, blank=True)
    inativado_em = models.DateTimeFieldPlus('Inativado em', null=True, blank=True)
    inativado_por = models.ForeignKeyPlus(
        Servidor, verbose_name='Inativado por', related_name='projeto_inativado_por', null=True, blank=True, on_delete=models.CASCADE
    )
    focotecnologico = models.ForeignKeyPlus(
        FocoTecnologico,
        verbose_name='Foco Tecnológico',
        help_text='O foco tecnológico do projeto deve coincidir com um dos focos tecnológicos de seu respectivo campus. Em caso de dúvida, consultar o Edital',
        null=True,
    )
    fundamentacaoteorica = HTMLField(blank=True)
    referenciasbibliograficas = HTMLField(blank=True)
    nucleo_extensao = models.ForeignKeyPlus(
        'projetos.NucleoExtensao', verbose_name='Núcleo de Extensão e Prática Profissional', null=True, blank=True
    )
    possui_acoes_empreendedorismo = models.BooleanField(
        verbose_name='Contempla Ações de Empreendedorismo, Cooperativismo ou Economia Solidária Criativa', null=True
    )
    responsavel_anuencia = models.ForeignKeyPlus(
        Servidor, verbose_name='Responsável pela Anuência', null=True, blank=True, related_name='projetos_responsavel_anuencia'
    )
    anuencia = models.BooleanField('Chefia de Acordo', null=True)
    anuencia_registrada_em = models.DateTimeFieldPlus('Anuência Registrada em', null=True, blank=True)
    possui_cooperacao_internacional = models.BooleanField('Possui acordo de cooperação internacional vigente', default=False)
    tem_interesse_cartao_pesquisador = models.BooleanField(
        'Tem interesse no fomento para custeio através do cartão BB pesquisador',
        default=False,
    )
    termo_parceria_adesao = models.PrivateFileField(
        'Termo de parceria/adesão', max_length=255, upload_to='projetos/termos_parcerias/', null=True, blank=True
    )
    auxiliar = models.ForeignKey(
        'comum.Vinculo',
        verbose_name='Membro Auxiliar do Projeto',
        related_name='projetos_membroauxiliar_projeto',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    atividade_integracao_curricular = models.BooleanField('É uma atividade de integração curricular da extensão', null=True)
    autorizada_sem_fomento = models.BooleanField('Execução sem fomento autorizada', default=False)
    autorizada_sem_fomento_por = models.ForeignKey(
        'comum.Vinculo',
        verbose_name='Execução sem fomento autorizada por',
        related_name='projetos_autorizadasemfomento_por',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    autorizada_sem_fomento_em = models.DateTimeFieldPlus('Execução sem fomento autorizada em', null=True, blank=True)
    aceita_sem_fomento = models.BooleanField('Execução sem fomento aceita', null=True)
    avaliacao_aceite_sem_fomento_por = models.ForeignKey(
        'comum.Vinculo',
        verbose_name='Execução sem fomento avaliada por',
        related_name='projetos_avaliadasemfomento_por',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    avaliacao_aceite_sem_fomento_em = models.DateTimeFieldPlus('Execução sem fomento avaliada em', null=True, blank=True)
    fomento_autorizado_por = models.ForeignKey(
        'comum.Vinculo',
        verbose_name='Fomento autorizado por',
        related_name='projetos_fomentoautorizado_por',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    fomento_autorizado_em = models.DateTimeFieldPlus('Fomento autorizado em', null=True, blank=True)
    precisa_cep = models.BooleanField('Necessita de Autorização do CEP', default=False)
    num_protocolo_cep = models.CharFieldPlus('Número do Protocolo no CEP', max_length=200, null=True, blank=True)
    precisa_ceua = models.BooleanField('Necessita de Autorização do CEUA', default=False)
    num_protocolo_ceua = models.CharFieldPlus('Número do Protocolo no CEUA', max_length=200, null=True, blank=True)
    precisa_sisgen = models.BooleanField('Necessita de Autorização do SISGEN', default=False)
    num_protocolo_sisgen = models.CharFieldPlus('Número do Protocolo no SISGEN', max_length=200, null=True, blank=True)
    atividades_sisgen = models.ManyToManyFieldPlus(
        'projetos.AtividadeAutorizacaoSISGEN',
        related_name='projetos_atividades_sisgen',
        blank=True,
        verbose_name='Atividades para Autorização no SISGEN',
        help_text='Para mais informações, acesse o SISGEN e consulte a Lei 13.123/2015',
    )
    precisa_sisbio = models.BooleanField('Necessita de Autorização do SISBIO', default=False)
    num_protocolo_sisbio = models.CharFieldPlus('Número do Protocolo no SISBIO', max_length=200, null=True, blank=True)
    atividades_sisbio = models.ManyToManyFieldPlus(
        'projetos.AtividadeAutorizacaoSISBIO',
        related_name='projetos_atividades_sisbio',
        blank=True,
        verbose_name='Atividades para Autorização no SISBIO',
        help_text='Para mais informações, acesse a portaria ICMBIO Nº 748, de 19 de setembro de 2022',
    )
    objetivos_desenvolvimento_sustentavel = models.ManyToManyFieldPlus(
        ObjetivoDesenvolvimentoSustentavel,
        related_name='projetos_objetivos_onu',
        blank=True,
        verbose_name='Objetivos atendidos para o desenvolvimento sustentável (ODS) da ONU',
        help_text='Detalhes de cada objetivo podem ser encontrados no site: https://brasil.un.org/pt-br/sdgs',
    )
    subobjetivos_desenvolvimento_sustentavel = models.ManyToManyFieldPlus(
        SubobjetivoDesenvolvimentoSustentavel,
        related_name='projetos_subobjetivos_onu',
        blank=True,
        verbose_name='Subobjetivos atendidos para o desenvolvimento sustentável (ODS) da ONU',
        help_text='Detalhes de cada subobjetivo podem ser encontrados no site: https://brasil.un.org/pt-br/sdgs',
    )
    grupo = models.ForeignKeyPlus('projetos.OfertaProjetoPorGrupo', null=True, on_delete=models.PROTECT)
    cancelado = models.BooleanField('Cancelado', default=False)
    concluido = models.BooleanField('Concluído', default=False)
    justificativa_reprovacao_manual = models.TextField('Justificativa para a reprovação', null=True)
    reprovacao_manual_em = models.DateTimeFieldPlus('Reprovação manual em', null=True, blank=True)
    reprovacao_manual_por = models.ForeignKey(
        'comum.Vinculo',
        verbose_name='Reprovação manual por',
        related_name='projetos_reprovacaomanual_por',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    aprovado_pos_recurso = models.BooleanField('Aprovado pós recurso', default=False)
    preve_atividades_internacionalizacao = models.BooleanField(
        'Prevê atividades de internacionalização, inclusive participação em eventos internacionais', null=True
    )
    motivo_finalizacao_sistemica = models.CharFieldPlus('Motivo da finalização sistêmica do projeto', max_length=10000, null=True, blank=True)
    finalizacao_sistemica_em = models.DateTimeFieldPlus('Finalização sistêmica em', null=True, blank=True)
    finalizacao_sistemica_por = models.ForeignKeyPlus(
        Servidor,
        verbose_name='Finalização sistêmica por',
        related_name='projeto_finalizacaosistemica_por',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )

    class Meta:
        verbose_name = 'Projeto'
        verbose_name_plural = 'Projetos'

        permissions = (
            ('pode_gerenciar_edital', 'Pode gerenciar edital'),
            ('pode_avaliar_projeto', 'Pode avaliar projeto'),
            ('pode_pre_avaliar_projeto', 'Pode pre avaliar projeto'),
            ('pode_visualizar_projeto', 'Pode visualizar projeto'),
            ('pode_visualizar_relatorios_extensao', 'Pode visualizar relatórios de extensão'),
            ('pode_visualizar_projetos_em_monitoramento', 'Pode visualizar projetos em monitoramento'),
            ('pode_avaliar_cancelamento_projeto', 'Pode avaliar cancelamento projeto'),
            ('pode_visualizar_avaliadores_externos', 'Pode visualizar avaliadores externos'),
            ('pode_registrar_consideracao_aluno', 'Pode registrar consideração sobre avaliação'),
            ('pode_interagir_com_projeto', 'Pode interagir com projeto'),
            ('pode_submeter_projeto', 'Pode submeter projeto'),
            ('pode_se_tornar_avaliador', 'Pode se tornar avaliador de projetos'),
        )

    def __str__(self):
        return f'Projeto de {self.edital.get_tipo_edital_display()} "{self.titulo}"'

    def eh_fomento_interno(self):
        return self.edital.tipo_fomento == Edital.FOMENTO_INTERNO

    def get_pontuacao_display(self):
        user = tl.get_user()
        if self.edital.tipo_edital == Edital.EXTENSAO_FLUXO_CONTINUO:
            return '<span class="status status-info">Não se aplica</span>'
        else:
            if self.selecao_ja_divulgada() or user.groups.filter(name='Gerente Sistêmico de Extensão'):
                return self.pontuacao

            else:
                return '<span class="status status-alert">Aguardando divulgação</span>'

    def get_pontuacao_total_display(self):
        user = tl.get_user()
        if self.edital.tipo_edital == Edital.EXTENSAO_FLUXO_CONTINUO:
            return '<span class="status status-info">Não se aplica</span>'
        else:
            if self.selecao_ja_divulgada() or user.groups.filter(name='Gerente Sistêmico de Extensão'):
                return self.pontuacao
            else:
                return '<span class="status status-alert">Aguardando divulgação</span>'

    def get_pre_selecionado(self, participacao=None, user=None):
        if self.eh_fomento_interno():
            if not user:
                user = tl.get_user()
            hoje = datetime.datetime.now()
            if not participacao:
                if hoje > self.edital.inicio_pre_selecao:
                    if user.groups.filter(
                        name__in=['Gerente Sistêmico de Extensão', 'Coordenador de Extensão', 'Pré-Avaliador Sistêmico de Projetos de Extensão']
                    ):
                        if self.data_conclusao_planejamento or (not self.data_conclusao_planejamento and self.data_pre_avaliacao):
                            if self.data_pre_avaliacao and self.pre_aprovado:
                                return f'<span class="status status-success">{Projeto.STATUS_PRE_SELECIONADO_EM} {format_(self.data_pre_avaliacao)} </span>'
                            elif self.data_pre_avaliacao and not self.pre_aprovado:
                                return f'<span class="status status-error">{Projeto.STATUS_NAO_PRE_SELECIONADO_EM} {format_(self.data_pre_avaliacao)} </span>'
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
                    return f'<span class="status status-alert">{Projeto.STATUS_AGUARDANDO_PRE_SELECAO}</span>'
            else:
                if participacao.projeto.data_pre_avaliacao:
                    if participacao.projeto.pre_aprovado:
                        return f'<span class="status status-success">{Projeto.STATUS_PRE_SELECIONADO_EM} {format_(participacao.projeto.data_pre_avaliacao)} </span>'
                    else:
                        return f'<span class="status status-error">{Projeto.STATUS_NAO_PRE_SELECIONADO_EM} {format_(participacao.projeto.data_pre_avaliacao)} </span>'
                else:
                    if not participacao.projeto.data_conclusao_planejamento and participacao.projeto.edital.fim_inscricoes >= hoje:
                        return f'<span class="status status-error">{Projeto.STATUS_AGUARDADO_ENVIO_PROJETO}</span>'
                    elif not participacao.projeto.data_conclusao_planejamento:
                        return f'<span class="status status-error">{Projeto.STATUS_NAO_ENVIADO}</span>'
                    elif hoje >= self.edital.inicio_selecao:
                        return '<span class="status status-info">Não foi pré-avaliado.</span>'
                    else:
                        return f'<span class="status status-alert">{Projeto.STATUS_AGUARDANDO_PRE_SELECAO}</span>'

        else:
            return '<span class="status status-alert">Não se aplica.</span>'

    def get_periodo(self, registro_conclusao=None):
        periodo = None
        eh_periodo_inscricao = self.edital.is_periodo_inscricao()
        registro_conclusao_projeto = registro_conclusao or self.get_registro_conclusao()
        if self.eh_fomento_interno():
            if self.edital.tipo_edital == Edital.EXTENSAO_FLUXO_CONTINUO:
                if eh_periodo_inscricao and not self.data_conclusao_planejamento:
                    periodo = self.PERIODO_INSCRICAO
                elif self.data_conclusao_planejamento and not self.data_pre_avaliacao:
                    periodo = self.PERIODO_PRE_SELECAO
                elif self.aprovado:
                    periodo = self.PERIODO_EXECUCAO
            else:
                if (
                    registro_conclusao_projeto
                    and registro_conclusao_projeto.dt_avaliacao
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
        else:
            if eh_periodo_inscricao and not self.data_conclusao_planejamento:
                periodo = self.PERIODO_INSCRICAO
            elif registro_conclusao_projeto and registro_conclusao_projeto.dt_avaliacao:
                periodo = self.PERIODO_ENCERRADO
            else:
                periodo = self.PERIODO_EXECUCAO

        return periodo

    def get_status(self, periodo=None, registro_conclusao=None):
        hoje = datetime.datetime.now()
        registro_conclusao_projeto = registro_conclusao or self.get_registro_conclusao()
        periodo_edital = periodo or self.get_periodo()
        if self.foi_cancelado():
            return self.STATUS_CANCELADO

        if self.eh_fomento_interno():
            if self.edital.tipo_edital == Edital.EXTENSAO_FLUXO_CONTINUO:
                if registro_conclusao_projeto and registro_conclusao_projeto.dt_avaliacao:
                    return self.STATUS_CONCLUIDO
                if self.inativado:
                    return self.STATUS_INATIVADO
                if self.aprovado:
                    return self.STATUS_EM_EXECUCAO
                if (not self.data_conclusao_planejamento and self.data_pre_avaliacao and periodo_edital != self.PERIODO_INSCRICAO) or (
                    not self.aprovado and not self.pre_aprovado and self.data_avaliacao and self.data_pre_avaliacao
                ):
                    return self.STATUS_NAO_ACEITO
                if self.data_conclusao_planejamento:
                    return self.STATUS_INSCRITO
                if not self.data_conclusao_planejamento and periodo_edital == self.PERIODO_INSCRICAO:
                    return self.STATUS_EM_INSCRICAO

                return self.STATUS_NAO_ENVIADO

            else:
                if registro_conclusao_projeto and registro_conclusao_projeto.dt_avaliacao:
                    return self.STATUS_CONCLUIDO
                if self.inativado:
                    return self.STATUS_INATIVADO
                if self.aprovado and periodo_edital == self.PERIODO_EXECUCAO:
                    return self.STATUS_EM_EXECUCAO
                if periodo_edital == self.PERIODO_SELECAO:
                    return self.STATUS_EM_SELECAO
                if not self.pre_aprovado and self.data_pre_avaliacao and self.edital.inicio_selecao < hoje:
                    return self.STATUS_NAO_ACEITO
                if not self.aprovado and self.data_avaliacao and self.edital.divulgacao_selecao < hoje:
                    return self.STATUS_NAO_SELECIONADO
                if self.aprovado and self.edital.divulgacao_selecao < hoje:
                    return self.STATUS_SELECIONADO
                if self.pre_aprovado and (periodo_edital == self.PERIODO_PRE_SELECAO or periodo_edital == self.PERIODO_SELECAO):
                    return self.STATUS_PRE_SELECIONADO
                if self.data_conclusao_planejamento or (not self.data_conclusao_planejamento and self.data_pre_avaliacao):
                    return self.STATUS_INSCRITO
                if self.edital.is_periodo_inscricao():
                    return self.STATUS_EM_INSCRICAO
                return self.STATUS_NAO_ENVIADO
        else:
            if self.inativado:
                return self.STATUS_INATIVADO
            if not self.data_conclusao_planejamento:
                return self.STATUS_EM_INSCRICAO
            elif self.data_conclusao_planejamento and not self.aprovado and not self.vinculo_autor_avaliacao:
                return self.STATUS_INSCRITO
            elif self.data_conclusao_planejamento and not self.aprovado and self.vinculo_autor_avaliacao:
                return self.STATUS_NAO_ACEITO
            elif self.aprovado and not self.data_finalizacao_conclusao:
                return self.STATUS_EM_EXECUCAO
            elif registro_conclusao_projeto and self.data_finalizacao_conclusao:
                return self.STATUS_CONCLUIDO

        return None

    def get_selecionado(self, participacao=None):
        if self.eh_fomento_interno():
            user = tl.get_user()
            if not participacao:
                if self.edital.tipo_edital == Edital.EXTENSAO_FLUXO_CONTINUO:
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
                        if user.groups.filter(name='Gerente Sistêmico de Extensão'):
                            return f'<span class="status status-alert">{Projeto.STATUS_EM_ESPERA}</span>'
                        else:
                            return f'<span class="status status-alert">{Projeto.STATUS_AGUARDANDO_AVALIACAO}</span>'
            else:
                if not participacao.projeto.data_conclusao_planejamento and participacao.projeto.edital.fim_inscricoes >= datetime.datetime.now():
                    return f'<span class="status status-error">{Projeto.STATUS_AGUARDADO_ENVIO_PROJETO}</span>'
                elif not participacao.projeto.data_conclusao_planejamento:
                    return f'<span class="status status-error">{Projeto.STATUS_NAO_ENVIADO}</span>'
                elif (
                    participacao.projeto.data_conclusao_planejamento
                    and not participacao.projeto.data_pre_avaliacao
                    and participacao.projeto.edital.inicio_selecao < datetime.datetime.now()
                ):
                    return f'<span class="status status-error">{Projeto.STATUS_NAO_SELECIONADO}</span>'
                else:
                    if (
                        participacao.projeto.data_avaliacao
                        and participacao.projeto.divulgacao_avaliacao_liberada()
                        and participacao.projeto.edital.tipo_edital != participacao.projeto.edital.EXTENSAO_FLUXO_CONTINUO
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
                        if participacao.projeto.edital.tipo_edital == participacao.projeto.edital.EXTENSAO_FLUXO_CONTINUO:
                            if participacao.projeto.pre_aprovado:
                                return f'<span class="status status-success">{Projeto.STATUS_SELECIONADO_EM} {format_(participacao.projeto.data_pre_avaliacao)} </span>'
                            elif participacao.projeto.data_pre_avaliacao:
                                return f'<span class="status status-error">{Projeto.STATUS_NAO_SELECIONADO_EM} {format_(participacao.projeto.data_pre_avaliacao)} </span>'
                            else:
                                return f'<span class="status status-alert">{Projeto.STATUS_AGUARDANDO_AVALIACAO}</span>'
                        else:
                            return f'<span class="status status-alert">{Projeto.STATUS_AGUARDANDO_AVALIACAO}</span>'

        else:
            return '<span class="status status-alert">Não se aplica.</span>'

    def divulgacao_avaliacao_liberada(self):
        if self.eh_fomento_interno():
            return self.edital.divulgacao_selecao <= datetime.datetime.now()
        return True

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
        return user.has_perm('projetos.pode_gerenciar_edital')

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

    def is_gerenciador_projeto(self, user=None):
        if not user:
            user = tl.get_user()
        if self.is_gerente_sistemico():
            return True
        responsavel = self.vinculo_coordenador
        return bool(responsavel and user.get_vinculo() == responsavel or self.auxiliar and user.get_vinculo() == self.auxiliar)

    def pode_acessar_monitoramento(self, user: User | None = None) -> bool:
        """Quem ``validar_execucao_etapa`` aceita: o monitor que não participa do projeto, o Gerente Sistêmico ou o coordenador."""
        if not user:
            user = tl.get_user()
        eh_monitor = self.vinculo_monitor == user.get_vinculo() and not self.eh_participante(user)
        return eh_monitor or user.has_group_cached('Gerente Sistêmico de Extensão') or self.is_responsavel(user)

    def pode_ver_prestacao_contas(self, user: User | None = None) -> bool:
        """Quem ``prestacao_contas`` aceita: coordenador, auxiliar, gerente, monitor, Visualizador e Coordenador de Extensão do campus."""
        if not user:
            user = tl.get_user()
        vinculo = user.get_vinculo()
        return (
            self.is_responsavel(user)
            or self.is_gerente_sistemico(user)
            or user.has_group_cached('Visualizador de Projetos')
            or self.is_coordenador_extensao_do_campus(user)
            or vinculo == self.vinculo_monitor
            or bool(self.auxiliar and self.auxiliar == vinculo)
        )

    def is_avaliador(self, user=None):
        if not user:
            user = tl.get_user()
        return user.groups.filter(name='Avaliador de Projetos de Extensão').exists()

    def is_avaliador_do_projeto(self, user=None):
        if not user:
            user = tl.get_user()
        return AvaliadorIndicado.objects.filter(projeto=self, vinculo=user.get_vinculo()).exists()

    def is_pre_avaliador(self, user: User | None = None) -> bool:
        """Pré-Avaliador Sistêmico (todos os campi) ou Coordenador de Extensão do campus do projeto (#17520)."""
        if not user:
            user = tl.get_user()
        return user.has_group_cached('Pré-Avaliador Sistêmico de Projetos de Extensão') or self.is_coordenador_extensao_do_campus(user)

    def is_coordenador_extensao_do_campus(self, user: User) -> bool:
        """O Coordenador de Extensão é papel local: só responde pelos projetos do próprio campus (#17520)."""
        return user.has_group_cached('Coordenador de Extensão') and self.uo_id == getattr(get_uo(user), 'id', None)

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

    def pode_registrar_conclusao(self, user=None, status=None):
        if self.data_finalizacao_conclusao:
            return False
        registro_conclusao = self.get_registro_conclusao()
        if registro_conclusao and registro_conclusao.dt_avaliacao:
            return False
        usuario = user or tl.get_user()
        status_projeto = status or self.get_status()
        return bool(status_projeto == Projeto.STATUS_EM_EXECUCAO and self.is_responsavel(usuario))

    def tem_participantes(self):
        return Participacao.objects.filter(projeto_id=self.id, responsavel=False).exists()

    def pode_finalizar_conclusao(self, registro_conclusao=None):
        user = tl.get_user()
        registro_conclusao_projeto = registro_conclusao or self.get_registro_conclusao()
        if self.eh_fomento_interno():
            if (
                self.data_finalizacao_conclusao
                or not registro_conclusao_projeto
                or self.tem_registro_execucao_etapa_pendente()
                or self.tem_registro_gasto_pendente()
                or self.tem_registro_anexos_pendente()
                or self.tem_registro_foto_pendente()
                or self.tem_caracterizacao_pendente()
                or not (self.is_responsavel(user) or self.is_gerente_sistemico(user))
                or (self.edital.exige_licoes_aprendidas and self.tem_registro_licoes_pendente())
                or self.tem_avaliacao_aluno_pendente()
            ):
                return False
            return bool(registro_conclusao_projeto and not registro_conclusao_projeto.dt_avaliacao)
        else:
            return bool(
                registro_conclusao_projeto
                and not self.data_finalizacao_conclusao
                and not self.tem_registro_anexos_pendente()
                and user.get_vinculo() == self.vinculo_monitor
                and not (self.edital.exige_licoes_aprendidas and self.tem_registro_licoes_pendente())
                and not self.tem_avaliacao_aluno_pendente()
            )

    def tem_pendencias(self):
        if self.data_finalizacao_conclusao:
            return False

        if self.eh_fomento_interno():
            return bool(
                self.tem_registro_execucao_etapa_pendente()
                or self.tem_registro_gasto_pendente()
                or self.tem_registro_anexos_pendente()
                or self.tem_registro_foto_pendente()
                or self.tem_caracterizacao_pendente()
                or self.edital.exige_licoes_aprendidas
                and self.tem_registro_licoes_pendente()
                or self.tem_avaliacao_aluno_pendente()
                or self.tem_frequencia_aluno_pendente()
                or self.tem_frequencia_com_validacao_pendente()
            )
        else:
            return bool(
                self.tem_registro_anexos_pendente()
                or self.edital.exige_licoes_aprendidas
                and self.tem_registro_licoes_pendente()
                or self.data_finalizacao_conclusao
                or self.tem_avaliacao_aluno_pendente()
                or self.tem_frequencia_aluno_pendente()
                or self.tem_frequencia_com_validacao_pendente()
            )

    def pode_reabrir_projeto(self, user=None):
        projeto_foi_finalizado = self.data_finalizacao_conclusao is not None
        return bool(self.is_gerente_sistemico(user) and not self.foi_cancelado() and projeto_foi_finalizado)

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
        """Mesmo critério de acesso da view ``projeto``: quem não passa nele só vê a consulta pública."""
        user = user or tl.get_user()
        if user.has_perm('projetos.pode_gerenciar_edital') or user.has_group_cached(['Visualizador de Projetos', 'Coordenador de Curso']):
            return True
        if self.is_coordenador_extensao_do_campus(user):
            return True
        if user.has_group_cached('Visualizador de Projetos do Campus') and self.uo == get_uo(user):
            return True
        vinculo = user.get_vinculo()
        # o coordenador (`is_responsavel`) também tem participação: coberto por `pode_acessar_projeto`
        if (vinculo and vinculo == self.vinculo_monitor) or self.pode_acessar_projeto(user):
            return True
        if self.is_avaliador_do_projeto(user) and self.projeto_em_avaliacao():
            return True
        return bool(user.eh_servidor and self.participacao_set.filter(responsavel_anuencia=user.get_relacionamento()).exists())

    def get_participacoes_alunos_ativos(self):
        return list(self.participacao_set.filter(ativo=True, vinculo_pessoa__tipo_relacionamento__model='aluno'))

    def get_participacoes_alunos_ativos_bolsistas(self):
        return list(
            self.participacao_set.filter(ativo=True, vinculo_pessoa__tipo_relacionamento__model='aluno', vinculo=TipoVinculo.BOLSISTA),
        )

    def get_participacoes_servidores_ativos(self):
        return list(self.participacao_set.filter(ativo=True, vinculo_pessoa__tipo_relacionamento__model='servidor'))

    def tem_servidores_efetivos_ativos(self):
        efetivos_ids = set(Servidor.objects.efetivos().values_list('id', flat=True))
        for part in self.participacao_set.filter(ativo=True, vinculo_pessoa__tipo_relacionamento__model='servidor'):
            if part.vinculo_pessoa.relacionamento.id in efetivos_ids:
                return True
        return False

    def get_participacoes_colaboradores(self):
        return list(self.participacao_set.filter(ativo=True, vinculo_pessoa__tipo_relacionamento__model='prestadorservico'))

    def get_ids_participacoes_com_anuencia(self):
        return [participacao.id for participacao in self.participacao_set.all() if participacao.anuencia or not participacao.exige_anuencia()]

    def get_ids_participacoes_sem_termo(self):
        return [
            participacao.id
            for participacao in self.participacao_set.all()
            if (
                (participacao.is_servidor() and self.edital.exige_termo_servidor() and not participacao.responsavel)
                or (participacao.eh_aluno() and self.edital.exige_termo_aluno())
                or (
                    not participacao.is_servidor()
                    and not participacao.eh_aluno()
                    and self.edital.exige_termo_colaborador()
                    and not participacao.responsavel
                )
            )
            and not participacao.termo_aceito_em
        ]

    def get_registro_conclusao(self):
        return self.registroconclusaoprojeto_set.all().first()

    def tem_registro_execucao_etapa_pendente(self):
        """
        Verifica se para este projeto há registro de execução de atividade não avaliado ou não há execucação de atividade registrada.
        """
        qs_ha_registro_atividade__nao_avaliada = RegistroExecucaoEtapa.objects.filter(etapa__meta__projeto_id=self.id, avaliador__isnull=True)
        qs_ha_atividade_sem_registro = Etapa.objects.filter(meta__projeto_id=self.id, registroexecucaoetapa__isnull=True)
        return bool(qs_ha_registro_atividade__nao_avaliada.exists() or qs_ha_atividade_sem_registro.exists())

    def tem_registro_gasto_pendente(self, nao_avaliado=False):
        """
        Verifica se para este projeto há registro de gastos não avaliado ou não há gastos registrados.
        """
        desembolsos = Desembolso.objects.filter(projeto=self)
        if not desembolsos.exists():
            return False
        if self.autorizada_sem_fomento and not self.fomento_autorizado_em:
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
        if self.edital.ocultar_aba_fotos:
            return False
        if self.eh_fomento_interno():
            return not FotoProjeto.objects.filter(projeto=self).exists()
        return False

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
        return not LicaoAprendida.objects.filter(projeto_id=self.id).exists()

    def tem_caracterizacao_pendente(self):
        """
        Verifica se para este projeto não foi informada a quantidade de beneficiários atendidas.
        """
        return bool(self.caracterizacaobeneficiario_set.filter(quantidade_atendida__isnull=True).exists())

    def tem_avaliacao_aluno_pendente(self):
        if not self.edital.exige_avaliacao_aluno:
            return False
        alunos_ativos = self.get_participacoes_alunos_ativos()
        for aluno in alunos_ativos:
            if (
                not aluno.atividade_integracao_curricular
                and not AvaliacaoAluno.objects.filter(participacao=aluno, tipo_avaliacao=AvaliacaoAluno.FINAL).exists()
            ):
                return True
        return False

    def tem_frequencia_aluno_pendente(self, participacao=None, data=None):
        if not self.edital.exige_frequencia_aluno:
            return False
        participantes_alunos_bolsistas = self.participacao_set.filter(
            vinculo_pessoa__tipo_relacionamento__model='aluno', vinculo=TipoVinculo.BOLSISTA
        )
        if participacao:
            participantes_alunos_bolsistas = participantes_alunos_bolsistas.filter(id=participacao.id)

        for participacao in participantes_alunos_bolsistas:
            meses_atividades = set()
            meses_projeto = set()
            data_entrada = participacao.get_data_entrada(apenas_bolsista=True)
            data_final = data or participacao.get_data_saida(apenas_bolsista=True)
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
        if not self.edital.exige_frequencia_aluno:
            return False
        alunos = self.participacao_set.filter(vinculo_pessoa__tipo_relacionamento__model='aluno')
        return bool(
            RegistroFrequencia.objects.filter(
                projeto=self, cadastrada_por__in=alunos.values_list('vinculo_pessoa', flat=True), validada_por__isnull=True
            ).exists()
        )

    def get_absolute_url(self):
        return f'/projetos/projeto/{self.id}/'

    def get_visualizar_projeto_url(self):
        return f'{settings.SITE_URL}{self.get_absolute_url()}'

    def edicao_inscricao(self):
        status = self.get_status()
        return bool(self.is_gerente_sistemico() or self.is_gerenciador_projeto() and status == Projeto.STATUS_EM_INSCRICAO)

    def edicao_inscricao_execucao(self):
        status = self.get_status()
        return bool(self.is_gerenciador_projeto() and (status == Projeto.STATUS_EM_INSCRICAO or status == Projeto.STATUS_EM_EXECUCAO))

    def pode_editar_inscricao_execucao(self):
        return bool(self.edicao_inscricao_execucao() and not self.data_finalizacao_conclusao)

    def pode_anexar_arquivo_do_membro(self):
        return bool(
            (self.edicao_inscricao_execucao() or self.edital.is_periodo_antes_pre_selecao())
            and not self.data_finalizacao_conclusao
            and self.is_gerenciador_projeto()
        )

    def pode_adicionar_fotos_e_anexos(self):
        return bool(self.edicao_inscricao_execucao() and not self.data_finalizacao_conclusao and self.is_gerenciador_projeto())

    def pode_editar_e_remover_projeto(self):
        return bool(self.get_periodo() == self.PERIODO_INSCRICAO and self.is_gerenciador_projeto())

    def selecao_ja_divulgada(self):
        return self.edital.divulgacao_selecao <= datetime.datetime.now()

    def pode_registrar_execucao(self, status=None):
        if self.eh_fomento_interno():
            user = tl.get_user()
            status_projeto = status or self.get_status()
            if (status_projeto == Projeto.STATUS_EM_EXECUCAO and self.is_gerenciador_projeto(user)) and self.selecao_ja_divulgada():
                return True
        return False

    def projeto_em_avaliacao(self):
        return bool(datetime.datetime.today() >= self.edital.inicio_pre_selecao and datetime.datetime.today() <= self.edital.divulgacao_selecao)

    def avaliador_pode_visualizar(self):
        user = tl.get_user()
        if AvaliadorIndicado.objects.filter(projeto=self, vinculo=user.get_vinculo()).exists() and self.projeto_em_avaliacao():
            return False
        if not self.edital.is_periodo_selecao():
            return True
        if self.edital.tipo_edital == Edital.EXTENSAO_FLUXO_CONTINUO:
            return True
        return user.has_perm('projetos.pode_gerenciar_edital') or self.vinculo_coordenador == user.get_vinculo() or self.pode_acessar_projeto(user)

    def pode_ser_pre_rejeitado(self) -> bool:
        """Botão "Não Selecionar". Com critérios de pré-seleção, rejeitar é responder "Não" na ficha de "Pré-avaliar" (#17579)."""
        if self.edital.criteriopreselecao_set.exists():
            return False
        periodo = self.get_periodo()
        if self.is_pre_avaliador() and periodo == Projeto.PERIODO_PRE_SELECAO and self.data_conclusao_planejamento:
            if self.data_pre_avaliacao is None:
                return True
            if self.pre_aprovado:
                return True
        return False

    def pode_ser_pre_aprovado(self):
        periodo = self.get_periodo()
        if self.is_pre_avaliador() and periodo == Projeto.PERIODO_PRE_SELECAO and self.data_conclusao_planejamento:
            if self.data_pre_avaliacao is None:
                return True
            if not self.pre_aprovado:
                return True
            if self.edital.criteriopreselecao_set.exists():
                return True
        return False

    def pode_receber_pre_avaliacao(self, rejeitar: bool | None) -> bool:
        """O que a tela de pré-seleção exige para oferecer a ação, conferido também pela view (#17579).

        `rejeitar=True` é "Não Selecionar"; `False`/`None` é "Pré-selecionar"/"Pré-avaliar", que exige vaga na cota.
        No fluxo contínuo, `get_periodo` tira da pré-seleção o projeto já pré-avaliado.
        """
        if rejeitar:
            return self.pode_ser_pre_rejeitado()
        return self.pode_ser_pre_aprovado() and self.pode_pre_aprovar()

    def exibir_acao_pre_rejeitar(self):
        if self.pode_ser_pre_rejeitado():
            if self.edital.tipo_edital == Edital.EXTENSAO_FLUXO_CONTINUO:
                if self.data_pre_avaliacao:
                    return ''  # edital de fluxo contínuo uma vez pré-rejeitado não poderá mais ser pré-avaliado.
                else:
                    return f'<a class="confirm btn danger" data-confirm="Deseja realmente não selecionar este projeto? Esta operação não poderá ser desfeita." href="/projetos/pre_rejeitar/{self.id}/">Não Selecionar</a>'
            return f'<a class="btn danger" href="/projetos/pre_rejeitar/{self.id}/">Não Selecionar</a>'
        return ''

    def pode_devolver_projeto(self):
        periodo = self.get_periodo()
        tem_permissao_para_devolver = self.is_pre_avaliador()
        if self.data_conclusao_planejamento:
            if tem_permissao_para_devolver and self.pre_aprovado is False:
                if (
                    self.edital.tipo_edital == Edital.EXTENSAO_FLUXO_CONTINUO
                    and self.edital.is_periodo_inscricao()
                    or periodo == Projeto.PERIODO_INSCRICAO
                ):
                    return True
            if self.is_avaliador_do_projeto() and self.edital.tipo_edital == Edital.EXTENSAO_FLUXO_CONTINUO and not self.aprovado:
                return True
        return False

    def exibir_acao_pre_aprovar(self):
        if self.pode_ser_pre_aprovado():
            if self.edital.criteriopreselecao_set.exists():
                return f'<a class="btn success" href="/projetos/pre_selecionar/{self.id}/">Pré-avaliar</a>'
            if self.edital.tipo_edital == Edital.EXTENSAO_FLUXO_CONTINUO:
                if self.data_pre_avaliacao:
                    return ''  # edital de fluxo contínuo uma vez pré-aprovado não poderá mais ser pré-avaliado.
                return f'<a class="confirm btn success" data-confirm="Deseja realmente selecionar este projeto? Esta operação não poderá ser desfeita." href="/projetos/pre_selecionar/{self.id}/">Pré-selecionar </a>'
            return f'<a class="btn success" href="/projetos/pre_selecionar/{self.id}/">Pré-selecionar</a>'
        return ''

    def pode_exibir_opcoes(self):
        if self.is_gerenciador_projeto() or self.is_avaliador():
            if not self.get_registro_conclusao():
                return True
        return False

    def pode_enviar_projeto(self, periodo=None):
        periodo_do_projeto = periodo or self.get_periodo()
        return bool(self.is_coordenador() and (periodo_do_projeto == self.PERIODO_INSCRICAO) and not self.data_conclusao_planejamento)

    def pode_emitir_parecer(self):
        return bool(self.is_pre_avaliador() and self.data_finalizacao_conclusao and not self.registroconclusaoprojeto_set.all()[0].dt_avaliacao)

    def pode_aprovar_projeto(self):
        return self.edital.is_periodo_selecao_e_pre_divulgacao() and self.aprovado == self.aprovado_na_distribuicao

    def eh_somente_leitura(self, periodo=None):
        if self.data_finalizacao_conclusao or self.foi_cancelado() or self.inativado:
            return True
        periodo_edital = periodo or self.get_periodo()
        return bool(periodo_edital != Projeto.PERIODO_EXECUCAO and self.data_conclusao_planejamento)

    @property
    def participacao_por_vinculo(self):
        return self.participacao_set.order_by('vinculo')

    def form_gerenciar_bolsas(self):
        class CustomForm(forms.FormPlus):
            fieldsets = (('titulo', {'fields': ('item_1', 'item_2', 'item_3')}),)

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
        return (
            ProjetoCancelado.objects.filter(projeto=self, data_avaliacao__isnull=False, cancelado=True)
            .filter(
                Q(projeto__data_conclusao_planejamento__isnull=False)
                | Q(projeto__data_conclusao_planejamento__isnull=True, projeto__data_pre_avaliacao__isnull=False)
            )
            .exists()
        )

    def pode_cancelar_projeto(self, user=None, status=None, periodo=None):
        usuario = user or tl.get_user()
        status_projeto = status or self.get_status()
        periodo_projeto = periodo or self.get_periodo()
        tem_solicitacao_cancelamento = ProjetoCancelado.objects.filter(projeto_id=self.id).exists()
        projeto_esta_em_execucao = periodo_projeto == Projeto.PERIODO_EXECUCAO
        return bool(
            self.is_responsavel(usuario)
            and status_projeto != Projeto.STATUS_CONCLUIDO
            and status_projeto != Projeto.STATUS_INATIVADO
            and not tem_solicitacao_cancelamento
            and projeto_esta_em_execucao
        )

    def pode_mostrar_dados_selecao(self):
        return self.edital.tipo_edital == Edital.EXTENSAO

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

    def mensagem_restricao_adicionar_membro(self, categoria, bolsista=None, participacao=None):
        pesquisador = 0
        if bolsista:
            if participacao:
                participantes = Participacao.ativos.filter(projeto=self, vinculo=TipoVinculo.BOLSISTA).exclude(id=participacao.id)
            else:
                participantes = Participacao.ativos.filter(projeto=self, vinculo=TipoVinculo.BOLSISTA)
        else:
            participantes = Participacao.ativos.filter(projeto=self)

        if participantes:
            for participante in participantes:
                if categoria == Participacao.SERVIDOR:
                    if participante.is_servidor():
                        pesquisador += 1
                else:
                    if not participante.is_servidor():
                        pesquisador += 1
        if bolsista:
            if categoria == Participacao.SERVIDOR:
                if self.edital.qtd_maxima_servidores_bolsistas == 0:
                    return 'Esse edital não prever bolsas para pesquisadores.'
                if pesquisador >= self.edital.qtd_maxima_servidores_bolsistas:
                    return 'A quantidade máxima de servidores bolsistas na equipe já foi atingida.'
            else:
                if self.edital.qtd_maxima_alunos_bolsistas == 0:
                    return 'Esse edital não prever bolsas para alunos.'
                if pesquisador >= self.edital.qtd_maxima_alunos_bolsistas:
                    return 'A quantidade máxima de alunos bolsistas na equipe já foi atingida.'

        else:
            if categoria == Participacao.SERVIDOR:
                if pesquisador >= self.edital.qtd_maxima_servidores:
                    return 'A quantidade máxima de pesquisadores na equipe foi atingida.'
            else:
                if pesquisador >= self.edital.qtd_maxima_alunos:
                    return 'A quantidade máxima de alunos na equipe foi atingida.'
        return None

    def tem_pre_avaliador_na_equipe(self):
        return any(membro.vinculo_pessoa.user.groups.filter(name='Coordenador de Extensão') for membro in self.participacao_por_vinculo)

    def tem_registro_gasto_registrado(self):
        return RegistroGasto.objects.filter(desembolso__in=self.desembolso_set.all()).exists()

    def pode_pre_aprovar(self):
        if self.grupo:
            return self.grupo.qtd_disponivel() > 0
        oferta = self.edital.ofertaprojeto_set.filter(uo=self.uo).first()
        if not oferta:
            return False  # sem oferta no campus não há cota: na tela, o `.get` falhava em silêncio (#17579)
        return oferta.qtd_aprovados and not oferta.qtd_aprovados - self.edital.num_total_projetos_pre_aprovados(self.uo) <= 0

    def pre_avaliador_integra_equipe(self):
        if not self.vinculo_autor_pre_avaliacao:
            return False

        return self.participacao_set.filter(vinculo_pessoa=self.vinculo_autor_pre_avaliacao).exists()

    def pode_enviar_recurso(self):
        if not self.is_responsavel():
            return False
        agora = datetime.datetime.now()
        if (
            not self.pre_aprovado
            and self.edital.fim_pre_selecao
            and self.edital.data_recurso_pre_selecao
            and self.edital.fim_pre_selecao < agora < self.edital.data_recurso_pre_selecao
        ):
            return True
        if self.edital.data_recurso and self.pre_aprovado and self.edital.is_periodo_pos_selecao():
            return self.edital.data_recurso > agora
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

    def pode_remover_projeto(self, user=None, status=None, periodo=None):
        periodo_projeto = periodo or self.get_periodo()
        status_projeto = status or self.get_status()
        eh_o_coordenador = self.is_coordenador(user)
        return bool(
            periodo_projeto == self.PERIODO_INSCRICAO
            and eh_o_coordenador
            and not self.eh_somente_leitura(periodo)
            or status_projeto == self.STATUS_NAO_ENVIADO
            and eh_o_coordenador
            or status_projeto in (self.STATUS_NAO_ENVIADO, self.STATUS_EM_INSCRICAO)
            and eh_o_coordenador
            and not self.eh_fomento_interno()
        )

    def pode_editar_projeto(self, status=None, periodo=None, eh_interno=None):
        status_projeto = status or self.get_status()
        periodo_projeto = periodo or self.get_periodo()
        eh_fomento_interno = eh_interno or self.eh_fomento_interno()
        foi_cancelado = self.foi_cancelado()
        eh_gerenciador = self.is_gerenciador_projeto()
        ja_concluiu = self.registroconclusaoprojeto_set.filter(dt_avaliacao__isnull=False).exists()
        return bool(
            eh_fomento_interno
            and periodo_projeto in [self.PERIODO_INSCRICAO, self.PERIODO_EXECUCAO]
            and eh_gerenciador
            and not foi_cancelado
            and not ja_concluiu
            or not eh_fomento_interno
            and status_projeto in [self.STATUS_EM_INSCRICAO, self.STATUS_EM_EXECUCAO]
            and eh_gerenciador
            and not foi_cancelado
            and not ja_concluiu
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
        return self.pode_avaliar_projeto(user.get_vinculo()) and not Avaliacao.objects.filter(projeto=self, vinculo=user.get_vinculo()).exists()

    def aberto_ha_2_anos(self):
        hoje = datetime.datetime.now().date()
        return (self.inicio_execucao + relativedelta(years=2)) <= hoje

    def pode_ser_inativado(self):
        hoje = datetime.datetime.now().date()
        return (self.inicio_execucao + relativedelta(years=2, months=1)) <= hoje

    def pode_cancelar_pre_avaliacao(self):
        if self.data_pre_avaliacao:
            if self.edital.tipo_edital == Edital.EXTENSAO:
                return not self.data_avaliacao
            return True
        return False

    def tem_atividade_todo_mes(self):
        meses_atividades = set()
        meses_projeto = set()

        dateRange = [self.inicio_execucao, self.fim_execucao]
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

        for etapa in Etapa.objects.filter(meta__projeto=self):
            dateRange = [etapa.inicio_execucao, etapa.fim_execucao]
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
        return all(item in meses_atividades for item in meses_projeto)

    def tem_atividade_ou_gasto_sem_validacao(self):
        return (
            RegistroExecucaoEtapa.objects.filter(etapa__meta__projeto=self, dt_avaliacao__isnull=True).exists()
            or RegistroGasto.objects.filter(desembolso__projeto=self, dt_avaliacao__isnull=True).exists()
        )

    def get_avaliadores_indicados(self):
        return AvaliadorIndicado.objects.filter(projeto=self).order_by('vinculo__pessoa')

    def get_participacoes_externo_ativos(self):
        return list(self.participacao_set.filter(ativo=True, vinculo_pessoa__tipo_relacionamento__model='prestadorservico'))

    def tem_aceite_pendente(self):
        if not self.edital.exige_termo_servidor() and not self.edital.exige_termo_aluno():
            return False
        if self.edital.exige_termo_servidor():
            for servidor in self.get_participacoes_servidores_ativos():
                if not servidor.termo_aceito_em and not servidor.responsavel:
                    return True

        if self.edital.exige_termo_aluno():
            for aluno in self.get_participacoes_alunos_ativos():
                if not aluno.termo_aceito_em:
                    return True

        return False

    def pendente_anuencia(self):
        return not self.anuencia

    def get_carga_horaria_coordenador(self):
        return Participacao.objects.filter(projeto=self, responsavel=True)[0].carga_horaria

    def tem_anuencia_pendente(self):
        if self.edital.exige_anuencia:
            if self.edital.exige_anuencia == Edital.COORD_TAES:
                if self.vinculo_coordenador.eh_servidor() and self.vinculo_coordenador.relacionamento.eh_tecnico_administrativo:
                    return not Participacao.objects.filter(projeto=self, responsavel=True, anuencia=True).exists()
                return False
            elif self.edital.exige_anuencia == Edital.TODOS_COORD:
                return not Participacao.objects.filter(projeto=self, responsavel=True, anuencia=True).exists()
            elif self.edital.exige_anuencia == Edital.TODOS_TAES:
                for participacao in Participacao.objects.filter(projeto=self):
                    if (
                        participacao.vinculo_pessoa
                        and participacao.vinculo_pessoa.eh_servidor()
                        and participacao.vinculo_pessoa.relacionamento.eh_tecnico_administrativo
                        and not participacao.anuencia
                    ):
                        return True
            elif self.edital.exige_anuencia == Edital.TODOS:
                for participacao in Participacao.objects.filter(projeto=self):
                    if participacao.vinculo_pessoa and participacao.vinculo_pessoa.eh_servidor() and not participacao.anuencia:
                        return True
        return False

    def pode_reprovar_manualmente(self, user):
        return not self.reprovacao_manual_em and self.is_gerente_sistemico(user) and self.edital.pode_divulgar_resultado_parcial()

    def pode_reverter_reprovacao(self, user):
        return self.reprovacao_manual_em and self.is_gerente_sistemico(user) and self.edital.pode_divulgar_resultado_parcial()

    def pode_ver_reprovacao_manual(self, user):
        return self.reprovacao_manual_em and (self.is_gerente_sistemico(user) or self.edital.is_periodo_divulgacao())

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

        projeto_clonado.data_avaliacao = None
        projeto_clonado.vinculo_autor_avaliacao = None
        projeto_clonado.pontuacao = 0
        projeto_clonado.data_conclusao_planejamento = None
        projeto_clonado.data_finalizacao_conclusao = None
        projeto_clonado.data_validacao_pontuacao = None
        projeto_clonado.vinculo_monitor = None
        projeto_clonado.classificacao = None

        projeto_clonado.descricao_comprovante_gru = None
        projeto_clonado.arquivo_comprovante_gru = None
        projeto_clonado.inativado = False
        projeto_clonado.motivo_inativacao = None
        projeto_clonado.inativado_em = None
        projeto_clonado.inativado_por = None
        projeto_clonado.auxiliar = None
        projeto_clonado.grupo = None

        projeto_clonado.inicio_execucao = data_inicio
        projeto_clonado.fim_execucao = data_fim

        projeto_clonado.save()

        p = Participacao.objects.get(projeto=self, responsavel=True)
        p.id = None
        p.projeto = projeto_clonado
        p.termo_aceito_em = None
        p.responsavel_anuencia = None
        p.anuencia = None
        p.anuencia_registrada_em = None
        if edital.termo_compromisso_coordenador:
            p.termo_aceito_em = datetime.datetime.now()
        if p.exige_anuencia():
            servidor = p.vinculo_pessoa.relacionamento
            chefes = servidor.chefes_na_data(datetime.datetime.now().date())
            if chefes:
                p.responsavel_anuencia = chefes[0]
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
            for membro in Participacao.objects.filter(projeto=self, responsavel=False, ativo=True).exclude(vinculo_pessoa=None):
                membro_clonado = Participacao(
                    projeto=projeto_clonado,
                    vinculo_pessoa=membro.vinculo_pessoa,
                    vinculo=membro.vinculo,
                    carga_horaria=membro.carga_horaria,
                    bolsa_concedida=membro.bolsa_concedida,
                    termo_aceito_em=None,
                    responsavel_anuencia=None,
                    anuencia=None,
                    anuencia_registrada_em=None,
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

        historico = ProjetoHistoricoDeEnvio()
        historico.projeto = projeto_clonado
        historico.parecer_devolucao = 'Projeto clonado. Situação: em edição.'
        historico.data_operacao = datetime.datetime.now()
        historico.operador = p.vinculo_pessoa.relacionamento
        historico.save()
        return projeto_clonado

    def get_identificador(self):
        return f'{self.id}/{self.edital.inicio_inscricoes.year}'

    def pode_avaliar_projeto(self, vinculo: Vinculo | None) -> bool:
        return bool(
            self.pre_aprovado
            and self.edital.is_periodo_selecao()
            and self.data_conclusao_planejamento
            and AvaliadorIndicado.objects.filter(projeto=self, vinculo=vinculo, rejeitado=False).exists()
        )

    def pode_aceitar_indicacao(self):
        indicacao = self.avaliadorindicado_set.filter(vinculo=tl.get_user().get_vinculo()).first()
        return indicacao and indicacao.prazo_para_aceite and not indicacao.rejeitado and not indicacao.aceito_em

    def rejeitou_indicacao(self):
        indicacao = self.avaliadorindicado_set.filter(vinculo=tl.get_user().get_vinculo()).first()
        return indicacao and indicacao.rejeitado

    @classmethod
    def pendencias_editais_anteriores(cls, vinculo, edital):
        participacoes = Participacao.objects.filter(responsavel=True, vinculo_pessoa=vinculo).values_list('projeto', flat=True)
        hoje = datetime.datetime.now().date()
        projetos_pendentes = Projeto.objects.filter(
            id__in=participacoes,
            pre_aprovado=True,
            aprovado=True,
            inativado=False,
            registroconclusaoprojeto__dt_avaliacao__isnull=True,
            fim_execucao__lt=hoje,
        )
        if edital.ano_inicial_projeto_pendente:
            projetos_pendentes = projetos_pendentes.filter(
                inicio_execucao__year__lt=edital.ano_inicial_projeto_pendente,
            )

        cancelados = ProjetoCancelado.objects.filter(cancelado=True, data_avaliacao__isnull=False).values_list('projeto', flat=True)
        return projetos_pendentes.exclude(id__in=cancelados).exclude(edital__tipo_fomento=Edital.FOMENTO_EXTERNO)

    @transaction.atomic
    def save(self, *args, **kwargs):
        if tl.get_user() is not None and not self.vinculo_coordenador:
            self.vinculo_coordenador = (self.id and Projeto.objects.get(id=self.id).vinculo_coordenador) or tl.get_user().get_vinculo()
            self.auxiliar = self.id and Projeto.objects.get(id=self.id).auxiliar
        super().save(*args, **kwargs)

    @transaction.atomic
    def concluir(self):
        self.concluido = True
        self.save()
        for participacao in self.participacao_set.filter(ativo=True):
            participacao.save(encerrar=True)


class TipoBeneficiario(models.ModelPlus):
    descricao = models.CharFieldPlus('Tipo de Beneficiário', max_length=255)
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Tipo de Beneficiário'
        verbose_name_plural = 'Tipos de Beneficiários'

    def __str__(self):
        return self.descricao


class CaracterizacaoBeneficiario(models.ModelPlus):
    tipo_beneficiario = models.ForeignKeyPlus(TipoBeneficiario, verbose_name='Tipo de Beneficiário')
    projeto = models.ForeignKeyPlus(Projeto)
    quantidade = models.IntegerField()
    quantidade_atendida = models.IntegerField(null=True, verbose_name='Quantidade Atendida')
    descricao_beneficiario = models.CharFieldPlus('Descreva os Beneficiários do Público-Alvo', max_length=2000, null=True, blank=True)

    class Meta:
        unique_together = ('tipo_beneficiario', 'projeto')

    def __str__(self):
        return f'Caracterização do Projeto: {self.projeto} '


class ProjetoExtensao(Projeto):
    foco_tecnologico = models.ForeignKeyPlus(
        FocoTecnologico,
        verbose_name='Foco Tecnológico',
        help_text='O foco tecnológico do projeto deve coincidir com um dos focos tecnológicos de seu respectivo campus. Em caso de dúvida, consultar o Edital',
    )
    fundamentacao_teorica = HTMLField(blank=True)
    referencias_bibliograficas = HTMLField(blank=True)

    class Meta:
        verbose_name = 'Projeto de Extensão'
        verbose_name_plural = 'Projetos de Extensão'

    def __str__(self):
        return str(self.titulo)


class AvaliadorIndicado(models.ModelPlus):
    projeto = models.ForeignKeyPlus(Projeto, on_delete=models.CASCADE)
    vinculo = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Avaliador', on_delete=models.CASCADE, null=True)
    rejeitado = models.BooleanField('Indicação Rejeitada pelo Avaliador', default=False)
    rejeitado_em = models.DateTimeFieldPlus('Rejeitado em', null=True)
    rejeitado_automaticamente = models.BooleanField('Rejeitado Automaticamente', default=False)
    aceito_em = models.DateTimeFieldPlus('Aceito em', null=True)
    prazo_para_aceite = models.DateTimeFieldPlus('Prazo para Aceite', null=True)
    prazo_para_avaliacao = models.DateTimeFieldPlus('Prazo para Avaliação', null=True)
    convidado_em = models.DateTimeFieldPlus('Convidado em', null=True)

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

    def get_areas_tematicas(self):
        return AreaTematica.objects.filter(vinculo=self.vinculo)

    def qtd_indicacoes_no_edital(self):
        return AvaliadorIndicado.objects.filter(vinculo=self.vinculo, projeto__edital=self.projeto.edital).count()


class Avaliacao(models.ModelPlus):
    projeto = models.ForeignKeyPlus(Projeto, on_delete=models.CASCADE)
    vinculo = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Avaliador', on_delete=models.CASCADE, null=True)
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
        if qs_avaliacoes.count() > 1 or self.projeto.edital.permite_avaliacao_unica:
            total = Decimal('0')
            for avaliacao in qs_avaliacoes:
                total += avaliacao.pontuacao
            self.projeto.pontuacao = total / qs_avaliacoes.count()
            if datetime.datetime.now() < self.projeto.edital.fim_selecao:
                self.projeto.pontuacao_parcial = self.projeto.pontuacao
        else:
            self.projeto.pontuacao = 0
            self.projeto.pontuacao_parcial = 0
            self.projeto.aprovado = False
        self.projeto.data_avaliacao = datetime.datetime.now()
        self.projeto.save()
        self.projeto.edital.classifica_projetos_extensao(self.projeto.uo, self.projeto.grupo)

    def tem_nota_alterada(self):
        return ItemAvaliacao.objects.filter(avaliacao=self, pontuacao_original__isnull=False).exists()


class ItemAvaliacao(models.ModelPlus):
    avaliacao = models.ForeignKeyPlus(Avaliacao)
    criterio_avaliacao = models.ForeignKeyPlus(CriterioAvaliacao, verbose_name='Critério', on_delete=models.CASCADE)
    pontuacao = models.DecimalFieldPlus('Pontuação')
    pontuacao_original = models.DecimalFieldPlus('Pontuação Original', null=True, blank=True)
    vinculo_responsavel_alteracao = models.ForeignKey(
        'comum.Vinculo',
        related_name='vinculo_responsavel_alteracao_nota',
        verbose_name='Responsável pela Alteração',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    data_alteracao = models.DateTimeFieldPlus('Data da Alteração', null=True, blank=True)
    recurso = models.ForeignKeyPlus(
        'projetos.RecursoProjeto', verbose_name='Recurso que Motivou a Alteração', null=True, blank=True, on_delete=models.CASCADE
    )

    texto_recurso = models.TextField(null=True)
    recurso_em = models.DateTimeFieldPlus('Recurso cadastrado em', null=True)
    recurso_por = models.ForeignKeyPlus(
        Vinculo, verbose_name='Recurso cadastrado por', null=True, on_delete=models.SET_NULL, related_name='recurso_extensao_cadastradopor'
    )
    recurso_aceito = models.BooleanField('Recurso aceito', default=False)
    recurso_avaliado_em = models.DateTimeFieldPlus('Recurso avaliado em', null=True)
    recurso_avaliado_por = models.ForeignKeyPlus(
        Vinculo, verbose_name='Recurso avaliado por', null=True, on_delete=models.SET_NULL, related_name='recurso_extensao_avaliadopor'
    )
    resposta_recurso = models.TextField('Resposta ao recurso', null=True)

    def pode_ser_avaliado(self):
        return self.texto_recurso and self.avaliacao.projeto.edital.id in Edital.objects.all().em_avaliacao_recursos().values_list('id', flat=True)

    def __str__(self):
        return f'Item da Avaliação: {self.avaliacao}'

    def get_id_avaliador(self):
        avaliacoes = Avaliacao.objects.filter(projeto=self.avaliacao.projeto).order_by('id').values_list('vinculo', flat=True)
        return list(avaliacoes).index(self.avaliacao.vinculo.id) + 1


class ItemMemoriaCalculo(models.ModelPlus):
    projeto = models.ForeignKeyPlus(Projeto, on_delete=models.CASCADE)
    despesa = models.ForeignKeyPlus(NaturezaDespesa, verbose_name='Despesa', on_delete=models.CASCADE)
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
        if self.projeto.is_gerenciador_projeto() and (status == Projeto.STATUS_EM_INSCRICAO or status == Projeto.STATUS_EM_EXECUCAO):
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
    ano = models.ForeignKeyPlus('comum.Ano', verbose_name='Ano', on_delete=models.CASCADE)
    mes = models.PositiveIntegerField(
        'Mês',
        choices=[[1, '1'], [2, '2'], [3, '3'], [4, '4'], [5, '5'], [6, '6'], [7, '7'], [8, '8'], [9, '9'], [10, '10'], [11, '11'], [12, '12']],
        help_text='O mês 1 indica o primeiro mês do projeto',
    )
    despesa = models.ForeignKeyPlus(NaturezaDespesa, verbose_name='Despesa', on_delete=models.CASCADE)
    valor = models.DecimalFieldPlus('Valor (R$)')
    data_cadastro = models.DateFieldPlus('Data de Cadastro do Desembolso', null=True, blank=True)
    item = models.ForeignKeyPlus(ItemMemoriaCalculo, verbose_name='Mémoria de Cálculo', null=True, on_delete=models.CASCADE)

    def __str__(self):
        if self.item:
            return f'{self.item} / Ano: {self.ano} / Mês: {self.mes}'
        return f'Ano: {self.ano} / Mês: {self.mes}'

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

    def foi_cancelado(self):
        return self.registrogasto_set.filter(valor_unitario=0).first()


class RegistroGasto(models.ModelPlus):
    item = models.ForeignKeyPlus(ItemMemoriaCalculo, on_delete=models.CASCADE)
    ano = models.ForeignKeyPlus('comum.Ano', verbose_name='Ano', on_delete=models.CASCADE)
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
    avaliador = models.ForeignKeyPlus(Servidor, null=True, on_delete=models.CASCADE)
    aprovado = models.BooleanField(default=False)
    justificativa_reprovacao = models.TextField(
        'Justificativa da Reprovação do Gasto',
        null=True,
        blank=True,
        help_text='Informação adicional que você julgar relevante no que diz respeito à reprovação do gasto.',
    )
    desembolso = models.ForeignKeyPlus(Desembolso, null=True, on_delete=models.CASCADE)
    arquivo = models.FileFieldPlus(max_length=255, upload_to='upload/projetos/registrogasto/comprovantes/', null=True, blank=True)
    data_cadastro = models.DateFieldPlus(null=True)
    cotacao_precos = models.FileFieldPlus(max_length=255, upload_to='upload/projetos/registrogasto/comprovantes/', null=True, blank=True)
    arquivo_termo_cessao = models.FileFieldPlus(max_length=255, upload_to='upload/projetos/termo_cessao/', null=True, blank=True)
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
        if self.desembolso.projeto.is_gerenciador_projeto():
            return not self.dt_avaliacao or not self.aprovado
        return False

    def __str__(self):
        return f'{self.descricao} - (Mês: {self.mes} / Ano: {self.ano})'


class ProjetoAnexo(models.ModelPlus):
    projeto = models.ForeignKeyPlus(Projeto, on_delete=models.CASCADE)
    anexo_edital = models.ForeignKeyPlus(EditalAnexo, null=True, on_delete=models.CASCADE)
    arquivo = models.OneToOneField(Arquivo, null=True, on_delete=models.CASCADE)
    vinculo_membro_equipe = models.ForeignKeyPlus('comum.Vinculo', null=True, verbose_name='Participante', on_delete=models.CASCADE)
    descricao = models.CharField('Descrição', max_length=255, null=True)
    cadastrado_em = models.DateTimeFieldPlus('Cadastrado em', auto_now_add=True, null=True)
    participacao = models.ForeignKeyPlus('projetos.Participacao', null=True, verbose_name='Participação', on_delete=models.SET_NULL)
    desembolso = models.ForeignKeyPlus(Desembolso, null=True, blank=True, on_delete=models.CASCADE)
    ano = models.ForeignKeyPlus('comum.Ano', verbose_name='Ano', related_name='projetos_ano_anexo', on_delete=models.CASCADE, null=True, blank=True)
    mes = models.IntegerField(
        'Mês',
        choices=[
            [0, '-------------'],
            [1, 'Janeiro'],
            [2, 'Fevereiro'],
            [3, 'Março'],
            [4, 'Abril'],
            [5, 'Maio'],
            [6, 'Junho'],
            [7, 'Julho'],
            [8, 'Agosto'],
            [9, 'Setembro'],
            [10, 'Outubro'],
            [11, 'Novembro'],
            [12, 'Dezembro'],
        ],
        default=0,
        blank=True,
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

    def get_participacao(self):
        if self.vinculo_membro_equipe and Participacao.objects.filter(projeto=self.projeto, vinculo_pessoa=self.vinculo_membro_equipe).exists():
            return Participacao.objects.filter(projeto=self.projeto, vinculo_pessoa=self.vinculo_membro_equipe)[0]
        return None

    def get_mes(self):
        JANEIRO = 1
        FEVEREIRO = 2
        MARCO = 3
        ABRIL = 4
        MAIO = 5
        JUNHO = 6
        JULHO = 7
        AGOSTO = 8
        SETEMBRO = 9
        OUTUBRO = 10
        NOVEMBRO = 11
        DEZEMBRO = 12
        Meses_CHOICES = [
            [JANEIRO, 'Janeiro'],
            [FEVEREIRO, 'Fevereiro'],
            [MARCO, 'Março'],
            [ABRIL, 'Abril'],
            [MAIO, 'Maio'],
            [JUNHO, 'Junho'],
            [JULHO, 'Julho'],
            [AGOSTO, 'Agosto'],
            [SETEMBRO, 'Setembro'],
            [OUTUBRO, 'Outubro'],
            [NOVEMBRO, 'Novembro'],
            [DEZEMBRO, 'Dezembro'],
        ]

        return dict(Meses_CHOICES)[self.mes]


class EditalAnexoAuxiliar(models.ModelPlus):
    edital = models.ForeignKeyPlus(Edital, on_delete=models.CASCADE)
    nome = models.CharField('Nome', max_length=255)
    descricao = models.TextField('Descrição', blank=True)
    arquivo = models.OneToOneField(Arquivo, null=True, on_delete=models.CASCADE)
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
        return self.etapa_set.all().select_related('responsavel').order_by('ordem')

    def get_periodo_meta(self):
        periodo = ''
        if self.etapa_set.exists():
            inicio = self.etapa_set.all().order_by('inicio_execucao')[0].inicio_execucao.strftime('%d/%m/%y')
            fim = self.etapa_set.latest('fim_execucao').fim_execucao.strftime('%d/%m/%y')
            periodo = ' - ' + str(inicio) + ' até ' + str(fim)
        return periodo

    def tem_etapas_aprovadas(self):
        return RegistroExecucaoEtapa.objects.filter(etapa__meta_id=self.id, aprovado=True).exists()

    def eh_planejamento(self):
        return eh_planejamento(self)

    def pode_editar_e_remover_meta(self):
        return bool(self.projeto.is_gerenciador_projeto() and not self.tem_etapas_aprovadas() and not self.eh_planejamento())


class RegistroExecucaoEtapa(models.ModelPlus):
    ATENDIDO = '1'
    ATENDIDO_PARCIALMENTE = '2'
    NAO_ATENTIDO = '3'
    TIPO_INDICADOR_QUALITATIVO = ((ATENDIDO, 'Atendido'), (ATENDIDO_PARCIALMENTE, 'Atendido Parcialmente'), (NAO_ATENTIDO, 'Não Atendido'))
    tipo_indicador_qualitativo = models.CharField('Indicadores Qualitativos', max_length=1, choices=TIPO_INDICADOR_QUALITATIVO)
    etapa = models.OneToOneFieldPlus('projetos.Etapa', on_delete=models.CASCADE)
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
    avaliador = models.ForeignKeyPlus(Servidor, null=True, on_delete=models.CASCADE)
    aprovado = models.BooleanField(default=False)
    data_cadastro_execucao = models.DateFieldPlus(null=True)
    arquivo = models.FileFieldPlus(max_length=255, upload_to='upload/projetos/atividades/comprovantes/', null=True, blank=True)

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
    avaliador = models.ForeignKeyPlus(Servidor, null=True, on_delete=models.CASCADE)
    obs_avaliador = models.TextField(
        'Observação do Coordenador de Extensão',
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
    class NivelEnsino(models.TextChoices):
        TECNICO = 'Técnico', 'Técnico'
        SUPERIOR = 'Superior', 'Superior'

    SERVIDOR = '1'
    ALUNO = '2'

    TIPOCONTA_CONTACORRENTE = 'Conta Corrente'
    TIPOCONTA_POUPANCA = 'Conta Poupança'

    TIPOCONTA_CHOICES = ((TIPOCONTA_CONTACORRENTE, TIPOCONTA_CONTACORRENTE), (TIPOCONTA_POUPANCA, TIPOCONTA_POUPANCA))

    projeto = models.ForeignKeyPlus(Projeto, verbose_name='Projeto', on_delete=models.CASCADE)
    vinculo_pessoa = models.ForeignKey(
        'comum.Vinculo', verbose_name='Participante', related_name='projetos_vinculo_extensao', on_delete=models.CASCADE, null=True
    )
    responsavel = models.BooleanField('Coordenador', default=False)
    vinculo = models.CharField(max_length=255, choices=TipoVinculo.TIPOS)
    carga_horaria = models.PositiveIntegerField('Carga Horária', help_text='Carga horária semanal')
    ativo = models.BooleanField(default=True)
    data_inativacao = models.DateField('Data de Inativação', null=True)
    bolsa_concedida = models.BooleanField(default=False)
    orientador = models.ForeignKeyPlus('projetos.Participacao', verbose_name='Orientador do Aluno', null=True, blank=True, on_delete=models.SET_NULL)
    ch_extensao = models.IntegerField(
        verbose_name='Carga Horária de Extensão', null=True, help_text='Carga horária total destinada a atividade curricular de extensão', blank=True
    )
    termo_aceito_em = models.DateTimeFieldPlus(null=True)
    responsavel_anuencia = models.ForeignKeyPlus(
        Servidor, verbose_name='Responsável pela Anuência', null=True, blank=True, related_name='part_projeto_responsavel_anuencia'
    )
    anuencia = models.BooleanField('Chefia de Acordo', null=True)
    anuencia_registrada_em = models.DateTimeFieldPlus('Anuência Registrada em', null=True, blank=True)
    instituicao = models.ForeignKeyPlus('rh.Banco', verbose_name='Banco', null=True, on_delete=models.SET_NULL)
    numero_agencia = models.CharField('Número da Agência', max_length=50, null=True, help_text='Ex: 3293-X')
    tipo_conta = models.CharField('Tipo da Conta', max_length=50, choices=TIPOCONTA_CHOICES, null=True)
    numero_conta = models.CharField('Número da Conta', max_length=50, null=True, help_text='Ex: 23384-6')
    operacao = models.CharField('Operação', max_length=50, null=True, blank=True)
    atividade_integracao_curricular = models.BooleanField('É participante de atividades da integração curricular da extensão', default=False)
    nivel_ensino = models.CharFieldPlus('Nível de ensino', max_length=50, null=True, blank=True, choices=NivelEnsino.choices)
    obs = models.TextField('Observações', null=True, blank=True)
    objects = ParticipacaoManager()
    ativos = ParticipacaoManagerAtivo()

    class Meta:
        verbose_name = 'Participação em Projeto de Extensão'
        verbose_name_plural = 'Participações em Projetos de Extensão'
        ordering = ['-responsavel', 'id']

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

        anexos_repetidos = ProjetoAnexo.objects.filter(
            projeto=projeto, vinculo_membro_equipe=participacao.vinculo_pessoa, anexo_edital__isnull=False, arquivo__isnull=True
        )
        if anexos_repetidos.exists():
            for anexo in anexos_repetidos:
                if anexo.anexo_edital.id in ProjetoAnexo.objects.filter(
                    projeto=projeto, vinculo_membro_equipe=participacao.vinculo_pessoa, anexo_edital__isnull=False, arquivo__isnull=False
                ).values_list('anexo_edital', flat=True):
                    anexo.delete()

    def get_tipo_vinculo_membro(self):
        if self.vinculo_pessoa and self.vinculo_pessoa.eh_servidor():
            servidor = Servidor.objects.get(id=self.vinculo_pessoa.id_relacionamento)
            if self.responsavel:
                if servidor.eh_docente:
                    if servidor.situacao.codigo == Situacao.CONTR_PROF_VISITANTE:
                        return EditalAnexo.COORDENADOR_DOCENTE_VISITANTE
                    else:
                        return EditalAnexo.COORDENADOR_DOCENTE
                else:
                    return EditalAnexo.COORDENADOR_TECNICO_ADMINISTRATIVO
            else:
                if servidor.eh_docente:
                    if servidor.situacao.codigo == Situacao.CONTR_PROF_VISITANTE:
                        return EditalAnexo.SERVIDOR_DOCENTE_VISITANTE
                    else:
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
                if ColaboradorVoluntario.objects.filter(prestador=self.vinculo_pessoa.id_relacionamento).exists():
                    return ColaboradorVoluntario.objects.get(prestador=self.vinculo_pessoa.id_relacionamento)
        return None

    def get_nome(self):
        pessoa = self.get_participante()
        if pessoa:
            if isinstance(pessoa, Aluno):
                return Vinculo.objects.get(id_relacionamento=pessoa.id, tipo_relacionamento__model='aluno').pessoa.nome
            elif isinstance(pessoa, ColaboradorVoluntario):
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
            return 'COLABORADOR EXTERNO'

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

        historicos = HistoricoEquipe.objects.filter(ativo=True, projeto=self.projeto, participante=self).order_by('-id')
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
            bolsa_concedida=self.bolsa_concedida,
        )

    def get_vinculo(self):
        if self.vinculo == TipoVinculo.BOLSISTA:
            return TipoVinculo.BOLSISTA
        else:
            return TipoVinculo.VOLUNTARIO

    def pode_remover_participacao(self):
        return bool(
            self.projeto.is_gerenciador_projeto()
            and not self.responsavel
            and self.projeto.get_status() in [Projeto.STATUS_EM_INSCRICAO, Projeto.STATUS_EM_EXECUCAO]
        )

    def get_inicio_orientacao_atual(self):
        if HistoricoOrientacaoProjeto.objects.filter(orientado=self, data_termino__isnull=True).exists():
            return HistoricoOrientacaoProjeto.objects.filter(orientado=self, data_termino__isnull=True)[0].data_inicio
        return None

    def pode_ver_avaliacoes(self) -> bool:
        """Gerenciador do projeto, monitor, orientador ou o próprio aluno avaliado."""
        user = tl.get_user()
        vinculo = user.get_vinculo()
        return bool(
            self.projeto.is_gerenciador_projeto(user)
            or (vinculo == self.projeto.vinculo_monitor)
            or (self.orientador and self.orientador.vinculo_pessoa == vinculo)
            or (self.vinculo_pessoa and self.vinculo_pessoa == vinculo)
        )

    def pode_fazer_avaliacoes(self):
        user = tl.get_user()
        return self.projeto.is_coordenador(user) or (self.orientador and self.orientador.vinculo_pessoa == user.get_vinculo())

    def get_data_entrada(self, apenas_bolsista=None):
        movimentacao = HistoricoEquipe.objects.filter(ativo=True, participante=self).order_by('id')
        if apenas_bolsista:
            movimentacao = movimentacao.filter(vinculo=TipoVinculo.BOLSISTA)
        if movimentacao.exists():
            if self.projeto.inicio_execucao > movimentacao[0].data_movimentacao:
                return self.projeto.inicio_execucao
            else:
                return movimentacao[0].data_movimentacao
        return None

    def get_data_saida(self, apenas_bolsista=None):
        movimentacao = (
            HistoricoEquipe.objects.filter(ativo=True, participante=self)
            .order_by('-id')
            .exclude(tipo_de_evento=HistoricoEquipe.EVENTO_INATIVAR_PARTICIPANTE)
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

    def tem_nivel_superior(self):
        servidor = self.vinculo_pessoa.relacionamento
        if servidor.titulacao and servidor.titulacao.codigo in Titulacao.CODIGOS_NIVEL_SUPERIOR:
            return True
        return bool(
            servidor.nivel_escolaridade
            and servidor.nivel_escolaridade.nome in ['DOUTORADO', 'ENSINO SUPERIOR', 'MESTRADO', 'POS-GRADUACAO LATO SENSO']
        )

    @transaction.atomic
    def save(self, *args, **kwargs):
        reativar = kwargs.pop('reativar', False)
        encerrar = kwargs.pop('encerrar', False)
        novo_cadastro = self.pk is None
        super().save(*args, **kwargs)

        if self.responsavel:
            Projeto.objects.filter(id=self.projeto.id).update(vinculo_coordenador=self.vinculo_pessoa)
        self.gerencia_bolsa_ae()
        if self.vinculo_pessoa and self.vinculo_pessoa.eh_aluno():
            self.gerar_atividade_curricular_extensao(reativar)
            self.gerenciar_atividade_pratica_profissional(novo_cadastro, encerrar, reativar)

    def gerenciar_atividade_pratica_profissional(self, novo_cadastro, encerrar, reativar):

        if AtividadePraticaProfissional.pode_registrar(
            self.vinculo_pessoa.relacionamento, ModalidadePraticaProfissional.MODALIDADE_PRATICA_PROJETO_EXTENSAO
        ):
            if novo_cadastro:
                self.gerar_atividade_pratica_profissional(concluir=False)
            elif reativar:
                AtividadePraticaProfissional.desfazer_conclusao(self.id, type(self))
            elif encerrar:
                atividade = AtividadePraticaProfissional.get(self.id, type(self))
                if atividade:
                    AtividadePraticaProfissional.registrar_conclusao(atividade, self.get_ch_total())
                else:
                    self.gerar_atividade_pratica_profissional(concluir=True)

    def gerar_atividade_curricular_extensao(self, reativar=False):
        aluno = self.get_aluno_extensao()
        if aluno:
            AtividadeCurricularExtensao = apps.get_model('edu', 'AtividadeCurricularExtensao')
            ch = self.get_ch_extensao()
            if reativar:
                content = ContentType.objects.get_for_model(type(self))
                ace = AtividadeCurricularExtensao.objects.filter(tipo_referencia=content, id_referencia=self.id).first()
                if ace:
                    ch = ace.carga_horaria_vinculada
            else:
                ch = ch * 100 if settings.COMPONENTE_CH_DECIMAL else ch
            concluido = self.projeto.get_status() == Projeto.STATUS_CONCLUIDO or not self.ativo
            aprovado = None if concluido else False
            AtividadeCurricularExtensao.registrar(aluno, type(self), self.pk, ch, self.projeto.titulo, concluido, aprovado)

    def gerar_atividade_pratica_profissional(self, concluir=False):
        aluno = self.vinculo_pessoa.relacionamento
        mp_id = aluno.get_ultima_matricula_periodo(excluir_em_aberto=True).id
        if concluir:
            AtividadePraticaProfissional.registrar_inicio_e_conclusao(
                ModalidadePraticaProfissional.MODALIDADE_PRATICA_PROJETO_EXTENSAO,
                self.id,
                type(self),
                mp_id,
                self.get_ch_total(),
                f'/projetos/projeto/{self.projeto_id}/',
                self.projeto.titulo,
            )
        else:
            AtividadePraticaProfissional.registrar_inicio(
                ModalidadePraticaProfissional.MODALIDADE_PRATICA_PROJETO_EXTENSAO,
                self.id,
                type(self),
                mp_id,
                f'/projetos/projeto/{self.projeto_id}/',
                self.projeto.titulo,
            )

    def get_ch_extensao(self):
        if self.ch_extensao:
            return self.ch_extensao
        return sum([h.get_carga_horaria_total() for h in self.historicoequipe_set.all()])

    def get_aluno_extensao(self) -> Aluno | None:
        if self.vinculo_pessoa and self.vinculo_pessoa.eh_aluno():
            return Aluno.objects.filter(
                pk=self.vinculo_pessoa.id_relacionamento,
                matriz__ch_atividades_extensao__gt=0,
                situacao__in=(SituacaoMatricula.MATRICULADO, SituacaoMatricula.MATRICULA_VINCULO_INSTITUCIONAL),
            ).first()
        return None

    def is_aluno_extensao(self):
        return self.get_aluno_extensao() is not None

    def get_ch_total(self):
        total = 0
        for vinculo in HistoricoEquipe.objects.filter(participante=self, projeto=self.projeto, ativo=True).filter(
            Q(data_movimentacao_saida=None) | Q(data_movimentacao_saida__gte=self.projeto.inicio_execucao)
        ):
            total += vinculo.get_carga_horaria_total(declaracao=True)
        return total

    @transaction.atomic
    def delete(self, *args, **kwargs):
        aluno = self.get_aluno_extensao()
        if aluno:
            AtividadeCurricularExtensao = apps.get_model('edu', 'AtividadeCurricularExtensao')
            AtividadeCurricularExtensao.registrar(aluno, type(self), self.pk, 0, None)
        AtividadePraticaProfissional.remover_registro(self.id, type(self))
        super().delete(*args, **kwargs)

    @classmethod
    def gerar_bolsa_ae(cls, editais=None):
        """
        Gera bolsa no AE para tdas os alunos com vínculo bolsistas participantes de projetos arpovados cuja data inclusao_bolsas_ae do edital é nula

        Parâmetro editais recebe uma lista de ids dos editais
        """
        hoje = datetime.datetime.now()
        if editais:
            qsedital = Edital.objects.filter(id__in=editais)
        else:
            qsedital = Edital.objects.filter(inclusao_bolsas_ae__isnull=True, divulgacao_selecao__lte=hoje)
        # Recupera todas as participacoes dos alunos cadastrados como bolsitas que ainda não possuem bolsa no ae
        qsparticipacoes = None
        contador_insert = 0
        contador_update = 0
        if qsedital.exists():
            qsparticipacoes = Participacao.objects.filter(
                projeto__aprovado=True,
                ativo=True,
                vinculo=TipoVinculo.BOLSISTA,
                bolsa_concedida=True,
                # participacaobolsa__isnull = True,
                vinculo_pessoa__tipo_relacionamento__model='aluno',
            )
            print_(f'\t{qsparticipacoes.count()} bolsas a serem processadas...')
            if qsparticipacoes and qsparticipacoes.exists():
                sid = transaction.savepoint()
                try:
                    for participacao in qsparticipacoes:
                        c1, c2 = participacao.gerencia_bolsa_ae()
                        contador_insert += c1
                        contador_update += c2
                    qsedital.update(inclusao_bolsas_ae=hoje)
                    transaction.savepoint_commit(sid)
                    print_(f'\tBolsas geradas     : {contador_insert}')
                    print_(f'\tBolsas atualizadas : {contador_update}')
                except Exception:
                    transaction.savepoint_rollback(sid)
                    print_(f'\tErro, desfazendo {contador_insert} bolsas geradas  e {contador_update} bolsas atualizadas.\n\n')
                    print_(traceback.format_exc())
        else:
            print_('\tNenhum edital a atualizar.')

    def exclui_participacao_em_bolsa(self):
        """
        Deleta uma Participação em Bolsa do aluno.
        """
        ParticipacaoBolsa = apps.get_model('ae', 'participacaobolsa')
        if ParticipacaoBolsa:
            try:
                aluno_bolsista = ParticipacaoBolsa.objects.get(aluno_participante_projeto=self)
                aluno_bolsista.delete()
            except ParticipacaoBolsa.DoesNotExist:
                pass

    def gerencia_bolsa_ae(self):
        """
        Objetivo é gerenciar as participações que geram bolsas no AE, isto é, cadastrando uma nova bolsa e/ou encerrando.
        Regra para cadastro de novas bolsas:
            Deve ser aluno, a participação ser ativa e o vínculo ser do tipo Bolsita.
        Regra para encerrar uma bolsa:
            Existir uma bolsa previamente cadastrada no AE e ter participação inativa ou vínculo Voluntário ou projeto ser cancelado
        """
        if self.is_servidor():
            return (0, 0)
        if not self.projeto.eh_fomento_interno():
            return (0, 0)
        if not self.vinculo_pessoa:
            return (0, 0)
        ParticipacaoBolsa = apps.get_model('ae', 'participacaobolsa')
        if ParticipacaoBolsa:
            CategoriaBolsa = apps.get_model('ae', 'categoriabolsa')
            contador_insert = 0
            contador_update = 0
            hoje = datetime.datetime.now()
            editalProjeto = self.projeto.edital
            bolsa_ae = ParticipacaoBolsa.objects.filter(aluno_participante_projeto=self)

            eh_periodo_execucao_ou_encerrado = self.projeto.get_periodo() in (Projeto.PERIODO_EXECUCAO, Projeto.PERIODO_ENCERRADO)
            # Estamos considerando gerar bolsas no AE para projetos encerrados para poder gerar bolsas para os projetos antigos, visto que essa funcionalidade não existia na época.
            eh_cancelado = self.projeto.get_status() == Projeto.STATUS_CANCELADO
            if (
                self.projeto.aprovado
                and not eh_cancelado
                and eh_periodo_execucao_ou_encerrado
                and self.ativo
                and self.vinculo == TipoVinculo.BOLSISTA
            ):
                if editalProjeto.divulgacao_selecao <= hoje:
                    categoria = CategoriaBolsa.objects.get(tipo_bolsa=CategoriaBolsa.TIPO_EXTENSAO)

                    try:
                        data_inicio = min(datetime.date.today(), self.projeto.fim_execucao)
                        qs_historico_equipe = HistoricoEquipe.objects.filter(ativo=True, participante=self)
                        if qs_historico_equipe.exists():
                            data_inicio = qs_historico_equipe.latest('id').data_movimentacao

                        aluno = self.vinculo_pessoa.relacionamento

                        if not bolsa_ae.exists():
                            bolsa = ParticipacaoBolsa()
                            bolsa.aluno = aluno
                            bolsa.categoria = categoria
                            bolsa.aluno_participante_projeto = self
                            contador_insert += 1
                        else:
                            bolsa = bolsa_ae[0]
                            contador_update += 1
                        bolsa.data_inicio = data_inicio
                        bolsa.data_termino = self.projeto.fim_execucao
                        bolsa.save()
                    except Exception:
                        raise
            else:
                if bolsa_ae.exists() and (eh_cancelado or not self.ativo or self.vinculo == TipoVinculo.VOLUNTARIO):
                    aluno_bolsista = bolsa_ae[0]
                    if not self.ativo and self.data_inativacao:
                        aluno_bolsista.data_termino = self.data_inativacao
                    else:
                        if HistoricoEquipe.objects.filter(participante=self, projeto=self.projeto, vinculo=TipoVinculo.BOLSISTA).exists():
                            data_final_como_bolsista = (
                                HistoricoEquipe.objects.filter(participante=self, projeto=self.projeto, vinculo=TipoVinculo.BOLSISTA)
                                .order_by('-id')[0]
                                .data_movimentacao_saida
                            )
                        else:
                            data_final_como_bolsista = datetime.date.today()
                        aluno_bolsista.data_termino = data_final_como_bolsista
                    aluno_bolsista.save()
                    contador_update += 1
            return (contador_insert, contador_update)
        return (0, 0)

    def get_historico_distribuicao_bolsa(self):
        return HistoricoEquipe.objects.filter(
            ativo=True, participante=self, tipo_de_evento__in=[HistoricoEquipe.EVENTO_CONCEDER_BOLSAR, HistoricoEquipe.EVENTO_NAOCONCEDER_BOLSA]
        )

    @classmethod
    def get_mensagem_aluno_nao_pode_ter_bolsa(cls, aluno):
        ParticipacaoBolsa = apps.get_model('ae', 'participacaobolsa')
        if ParticipacaoBolsa:
            AE_Participacao = apps.get_model('ae', 'participacao')
            aluno_tem_bolsa = ParticipacaoBolsa.objects.filter(
                Q(aluno=aluno) & (Q(data_termino__gte=datetime.date.today()) | Q(data_termino__isnull=True))
            )
            if aluno_tem_bolsa:
                if aluno_tem_bolsa[0].data_termino:
                    if aluno_tem_bolsa[0].data_termino > datetime.date.today():
                        return 'O aluno já possui bolsa ativa, apenas é possível participar como voluntário.'
                else:
                    return 'O aluno selecionado já possui uma bolsa sem prazo final cadastrado. Apenas é possível participar como voluntário.'
            else:
                tem_bolsa_trabalho = AE_Participacao.objects.filter(
                    Q(aluno=aluno) & Q(programa__tipo='TRB') & (Q(data_termino__isnull=True) | Q(data_termino__gte=datetime.date.today()))
                ).exists()
                if tem_bolsa_trabalho:
                    return 'O aluno selecionado já possui uma bolsa de atividade profissional. Apenas é possível participar como voluntário.'
            return None
        return None

    def tem_historico_equipe(self):
        movimentacao = HistoricoEquipe.objects.filter(ativo=True, participante=self, vinculo__isnull=False)
        return bool(movimentacao.exists())

    def pode_emitir_plano_de_trabalho(self) -> bool:
        user = tl.get_user()
        pode_emitir = (
            self.projeto.is_pre_avaliador()
            or self.projeto.is_gerenciador_projeto()
            or (self.vinculo_pessoa and user.get_vinculo() == self.vinculo_pessoa)
        )
        return bool(pode_emitir)

    def pode_emitir_certificado_de_participacao_extensao(self):
        user = tl.get_user()
        status = self.projeto.get_status()
        if self.exige_anuencia() and not self.anuencia:
            return False
        pode_emitir = self.vinculo_pessoa and (
            self.projeto.is_pre_avaliador()
            or self.projeto.is_gerenciador_projeto()
            or (self.vinculo_pessoa and user.get_vinculo() == self.vinculo_pessoa)
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
            (self.projeto.is_pre_avaliador() or self.projeto.is_gerenciador_projeto() or user.get_vinculo() == self.vinculo_pessoa)
            and (status == Projeto.STATUS_EM_EXECUCAO or status == Projeto.STATUS_CONCLUIDO or self.ativo is False)
            and HistoricoOrientacaoProjeto.objects.filter(projeto=self.projeto, orientador=self).exists()
            and not self.projeto.inativado
        )

    def pode_emitir_declaracao_de_participacao(self):
        user = tl.get_user()
        status = self.projeto.get_status()
        if self.exige_anuencia() and not self.anuencia:
            return False
        pode_emitir = self.vinculo_pessoa and (
            self.projeto.is_pre_avaliador() or self.projeto.is_gerenciador_projeto() or (user.get_vinculo() == self.vinculo_pessoa)
        )
        return bool(pode_emitir and status in (Projeto.STATUS_EM_EXECUCAO, Projeto.STATUS_CONCLUIDO) and self.ativo)

    def exige_anuencia(self):
        if self.vinculo_pessoa and self.vinculo_pessoa.eh_servidor():
            if (
                self.projeto.edital.exige_anuencia == Edital.TODOS
                or self.projeto.edital.exige_anuencia == Edital.TODOS_COORD
                and self.responsavel
                or self.projeto.edital.exige_anuencia == Edital.TODOS_TAES
                and self.vinculo_pessoa.relacionamento.eh_tecnico_administrativo
                or self.projeto.edital.exige_anuencia == Edital.COORD_TAES
                and self.responsavel
                and self.vinculo_pessoa.relacionamento.eh_tecnico_administrativo
            ):
                return True

        return False


class FotoProjeto(models.ModelPlus):
    projeto = models.ForeignKeyPlus(Projeto, on_delete=models.CASCADE)
    legenda = models.TextField(blank=True)
    imagem = models.ImageFieldPlus(upload_to='upload/projetos/fotos/')

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
    CATEGORIA = ((COORDENADOR, 'Coordenador'), (MEMBRO, 'Membro'))
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
        (EVENTO_ADICIONAR_COLABORADOR, 'Colaborador Externo inserido'),
        (EVENTO_ATIVAR_PARTICIPANTE, 'Participante ativado'),
        (EVENTO_INATIVAR_PARTICIPANTE, 'Participante inativado'),
        (EVENTO_EXCLUIR_PARTICIPANTE, 'Participante excluído'),
        (EVENTO_CONCEDER_BOLSAR, 'Bolsa concedida durante a distribuição de bolsas'),
        (EVENTO_NAOCONCEDER_BOLSA, 'Bolsas não concedida durante a distribuição de bolsas'),
        (EVENTO_EDICAO_ALUNO, 'Aluno alterado'),
        (EVENTO_EDICAO_SERVIDOR, 'Servidor alterado'),
        (EVENTO_EDICAO_COLABORADOR, 'Colaborador Externo alterado'),
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
    ativo = models.BooleanField('Ativo', default=True)
    bolsa_concedida = models.BooleanField(null=True)

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

    def get_carga_horaria_total(self, declaracao=None):
        if self.participante.projeto.inicio_execucao > self.data_movimentacao:
            data_inicio = self.participante.projeto.inicio_execucao
        else:
            data_inicio = self.data_movimentacao

        if not self.data_movimentacao_saida:
            if declaracao:
                hoje = datetime.date.today()
                if hoje < self.participante.projeto.fim_execucao:
                    data_fim = hoje
                else:
                    data_fim = self.participante.projeto.fim_execucao
            else:
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
    meta = models.ForeignKeyPlus('projetos.Meta', verbose_name='Meta', on_delete=models.CASCADE)
    ordem = models.PositiveIntegerField('Ordem', help_text='Informe um número inteiro maior ou igual a 1')
    descricao = models.TextField('Descrição')
    unidade_medida = models.CharField('Unidade de Medida', max_length=255)  # pode mudar para FK
    qtd = models.PositiveIntegerField('Quantidade')
    indicadores_qualitativos = models.TextField('Indicador(es) Qualitativo(s)')
    responsavel = models.ForeignKeyPlus(
        Participacao, verbose_name='Responsável pela Atividade', related_name='participacao_responsavel', on_delete=models.CASCADE
    )
    integrantes = models.ManyToManyFieldPlus('projetos.Participacao', related_name='integrantes_set', blank=True)
    inicio_execucao = models.DateFieldPlus('Início da Execução', null=True)
    fim_execucao = models.DateFieldPlus('Fim da Execução', null=True)
    data_cadastro = models.DateFieldPlus('Data de Cadastro da Etapa', null=True, blank=True, default=datetime.datetime.now)
    forma_comprovacao = models.CharFieldPlus(
        'Forma de Comprovação',
        null=True,
        max_length=2000,
        help_text='Exemplos de forma de comprovação: atas de reuniões, lista de frequência, fotos, entre outros. Caso não seja necessária a comprovação, preencha com "não se aplica". Atenção: os registros de atividades realizadas em ambiente externo à instituição precisam de comprovação.',
    )

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

    def pode_registrar_execucao(self):
        projeto = self.meta.projeto
        user = tl.get_user()
        status = projeto.get_status()
        tem_permissao_registrar_execucao = projeto.is_gerenciador_projeto(user) or (
            projeto.edital.responsavel_pode_registrar_execucao and self.responsavel.vinculo_pessoa == user.get_vinculo()
        )
        return bool(projeto.selecao_ja_divulgada() and (tem_permissao_registrar_execucao and status == Projeto.STATUS_EM_EXECUCAO))


class ProjetoHistoricoDeEnvio(models.ModelPlus):
    ENVIADO = 'E'
    DEVOLVIDO = 'D'
    REBAERTO = 'R'
    FINALIZADO = 'F'
    TIPO_SITUACAO = ((ENVIADO, 'Enviado'), (DEVOLVIDO, 'Devolvido'), (REBAERTO, 'Reaberto'), (FINALIZADO, 'Finalizado'))
    projeto = models.ForeignKeyPlus(Projeto, on_delete=models.CASCADE)
    parecer_devolucao = models.TextField('Parecer sobre a devolução do projeto')
    data_operacao = models.DateTimeFieldPlus('Data de realização da Operação', null=True, blank=True)
    situacao = models.CharField('Situação', max_length=1, choices=TIPO_SITUACAO, null=True, blank=True)
    operador = models.ForeignKeyPlus(Servidor, verbose_name='Operador', null=True, blank=True, on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Histórico do Envio de Projetos'
        verbose_name_plural = 'Históricos dos Envios de Projetos'

    def __str__(self):
        return f'Histórico do Projeto: {self.projeto} '


class OfertaProjetoPorTema(models.ModelPlus):
    edital = models.ForeignKeyPlus(Edital, on_delete=models.CASCADE)
    area_tematica = models.ForeignKeyPlus(AreaTematica, verbose_name='Área Temática', on_delete=models.CASCADE)
    tema = models.ForeignKeyPlus(Tema, verbose_name='Tema', null=True, blank=True, on_delete=models.CASCADE)
    selecionados = models.PositiveIntegerField('Selecionados', help_text='Informe quantos projetos serão selecionados.')

    class Meta:
        verbose_name = 'Oferta de Projeto por Tema'
        verbose_name_plural = 'Ofertas de Projeto por Tema'

    def __str__(self):
        return f'Oferta do Edital: {self.edital}'


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
    avaliador = models.ForeignKeyPlus(Servidor, verbose_name='Operador', null=True, blank=True, on_delete=models.CASCADE)
    obs_avaliacao = models.CharField('Observação', max_length=500, null=True, blank=True)
    data_avaliacao = models.DateTimeFieldPlus('Data da Avaliação da Solicitação', null=True, blank=True)
    cancelado = models.BooleanField('Cancelado', default=False)
    proximo_projeto = models.ForeignKeyPlus(Projeto, null=True, blank=True, related_name='proximo_projeto', on_delete=models.CASCADE)

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
        'comum.Vinculo', verbose_name='Membros', blank=True, related_name='vinculos_membros_comissao_edital'
    )

    class Meta:
        verbose_name = 'Comissão de Avaliação'
        verbose_name_plural = 'Comissões de Avaliação'

    def __str__(self):
        return f'Comissão do {self.edital.titulo}'

    def get_membros(self):
        string = ''
        for membro in self.vinculos_membros.all().order_by('pessoa__nome'):
            string = string + '<p>' + membro.pessoa.nome + '</p>'

        return string


class RecursoProjeto(models.ModelPlus):
    projeto = models.ForeignKeyPlus(Projeto, on_delete=models.CASCADE)
    justificativa = models.CharField('Justificativa do Recurso', max_length=1000, null=True, blank=True)
    data_solicitacao = models.DateTimeFieldPlus('Data da Solicitação do Recurso')
    avaliador = models.ForeignKeyPlus(
        Servidor, verbose_name='Avaliador', related_name='projeto_avaliador_recurso', null=True, blank=True, on_delete=models.CASCADE
    )
    parecer = models.CharField('Parecer', max_length=5000, null=True, blank=True)
    data_avaliacao = models.DateTimeFieldPlus('Data da Avaliação da Solicitação', null=True, blank=True)
    aceito = models.BooleanField('Aceito', default=False)
    arquivo = models.PrivateFileField(verbose_name='Arquivo', upload_to='projetos/recursos', null=True, blank=True)

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
                texto_retorno += f'<li><a href="/projetos/avaliar_recurso_projeto/{self.id}/" class="btn success">Avaliar</a></li>'
            else:
                texto_retorno += f'<li><a href="/projetos/avaliar_recurso_projeto/{self.id}/"  class="btn primary">Editar Avaliação</a></li>'

            texto_retorno += '</ul>'
            return texto_retorno
        return ''

    def __str__(self):
        return f'Recurso #{self.id} - {self.projeto.titulo}'


class ExtratoMensalProjeto(models.ModelPlus):
    ano = models.ForeignKeyPlus('comum.Ano', verbose_name='Ano', on_delete=models.CASCADE)
    mes = models.PositiveIntegerField(
        'Mês',
        choices=[
            [1, 'Janeiro'],
            [2, 'Fevereiro'],
            [3, 'Março'],
            [4, 'Abril'],
            [5, 'Maio'],
            [6, 'Junho'],
            [7, 'Julho'],
            [8, 'Agosto'],
            [9, 'Setembro'],
            [10, 'Outubro'],
            [11, 'Novembro'],
            [12, 'Dezembro'],
        ],
    )
    projeto = models.ForeignKeyPlus(Projeto, on_delete=models.CASCADE)
    arquivo = models.FileFieldPlus(max_length=255, upload_to='upload/projetos/extratos_mensais/')

    def __str__(self):
        return f'Extrato Mensal do Projeto: {self.projeto}'


class AvaliadorExterno(models.ModelPlus):
    nome = models.CharField('Nome', max_length=255)
    vinculo = models.OneToOneField('comum.Vinculo', related_name='projetos_avaliador_externo_vinculo', on_delete=models.CASCADE, null=True)
    ativo = models.BooleanField('Ativo', default=True)
    email = models.EmailField('Email')
    telefone = models.CharFieldPlus('Telefone', max_length=255, null=True, blank=True)
    titulacao = models.ForeignKeyPlus(
        'rh.Titulacao', verbose_name='Titulação', related_name='projetos_avaliador_instituicao', on_delete=models.CASCADE
    )
    instituicao_origem = models.ForeignKeyPlus(
        'rh.Instituicao', blank=True, null=True, verbose_name='Instituição', related_name='projetos_instituicao_avaliador', on_delete=models.CASCADE
    )
    lattes = models.URLField(blank=True)

    class Meta:
        verbose_name = 'Avaliador Externo'
        verbose_name_plural = 'Avaliadores Externos'
        ordering = ['nome']

    def __str__(self):
        return str(self.nome)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        grupo = Group.objects.get(name='Avaliador Sistêmico de Projetos de Extensão')
        if self.ativo and grupo:
            self.vinculo.user.groups.add(grupo)
        else:
            self.vinculo.user.groups.remove(grupo)


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

    TIPOAVALIACAO_CHOICES = ((PARCIAL, PARCIAL), (FINAL, FINAL))
    participacao = models.ForeignKeyPlus('projetos.Participacao', related_name='projetos_avaliacaoaluno_participante', on_delete=models.CASCADE)
    tipo_avaliacao = models.CharFieldPlus('Tipo de Avaliação', max_length=20, choices=TIPOAVALIACAO_CHOICES)
    data_avaliacao = models.DateTimeFieldPlus('Realizada em', null=True, blank=True)
    data_validacao = models.DateTimeFieldPlus('Validada pelo aluno em', null=True, blank=True)
    consideracoes_coordenador = models.CharFieldPlus('Considerações do Avaliador', max_length=5000, null=True, blank=True)
    consideracoes_aluno = models.CharFieldPlus('Considerações do Aluno', max_length=5000, null=True, blank=True)
    vinculo_avaliado_por = models.ForeignKey(
        'comum.Vinculo', related_name='vinculo_avaliador_avaliacao_aluno', on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        verbose_name = 'Avaliação do Aluno'
        verbose_name_plural = 'Avaliações dos Alunos'

    def __str__(self):
        return f'Avaliação do Aluno: {self.participacao} '


class ItemAvaliacaoAluno(models.ModelPlus):
    RUIM = 'Ruim'
    REGULAR = 'Regular'
    BOM = 'Bom'
    EXCELENTE = 'Excelente'
    NAO_APLICA = 'Não se Aplica'
    PONTUACAOAVALIACAO_CHOICES = ((NAO_APLICA, NAO_APLICA), (EXCELENTE, EXCELENTE), (BOM, BOM), (REGULAR, REGULAR), (RUIM, RUIM))
    criterio = models.ForeignKeyPlus('projetos.CriterioAvaliacaoAluno', related_name='projetos_criterioavaliacaoaluno', on_delete=models.CASCADE)
    avaliacao = models.ForeignKeyPlus('projetos.AvaliacaoAluno', related_name='projetos_avaliacaoaluno', on_delete=models.CASCADE)
    pontuacao = models.CharFieldPlus('Pontuação', max_length=20, choices=PONTUACAOAVALIACAO_CHOICES)

    class Meta:
        ordering = ['criterio__nome']
        verbose_name = 'Item de Avaliação do Aluno'
        verbose_name_plural = 'Itens de Avaliação dos Alunos'

    def __str__(self):
        return f'Item da Avaliação: {self.avaliacao} '


class HistoricoAlteracaoPeriodoProjeto(models.ModelPlus):
    projeto = models.ForeignKeyPlus('projetos.Projeto', related_name='projetos_historicodata', on_delete=models.CASCADE)
    inicio_execucao = models.DateFieldPlus('Início da Execução')
    fim_execucao = models.DateFieldPlus('Término da Execução')
    justificativa = models.CharFieldPlus('Justificativa', max_length=5000)
    vinculo_registrado_por = models.ForeignKey(
        'comum.Vinculo', related_name='projetos_vinculo_registradopor_historicodata', on_delete=models.CASCADE, null=True
    )
    registrado_em = models.DateTimeFieldPlus('Registrado em', auto_now_add=True)
    novo_inicio_execucao = models.DateFieldPlus('Novo Início da Execução', null=True)
    novo_fim_execucao = models.DateFieldPlus('Novo Término da Execução', null=True)
    aceito = models.BooleanField('Aceito', null=True)
    validado_por = models.ForeignKey('comum.Vinculo', related_name='projetos_historicodata_validadopor', on_delete=models.CASCADE, null=True)
    validado_em = models.DateTimeFieldPlus('Validado em', null=True)
    justificativa_validacao = models.CharFieldPlus('Justificativa', max_length=5000, null=True)

    class Meta:
        ordering = ['-registrado_em']
        verbose_name = 'Registro de Alteração de Período de Execução'
        verbose_name_plural = 'Registros de Alterações de Períodos de Execução'

    def __str__(self):
        return f'Alteração do Projeto: {self.projeto} '


class ObjetivoVisitaTecnica(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição', max_length=1000)
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Objetivo da Visita Técnica'
        verbose_name_plural = 'Objetivos das Visitas Técnicas'

    def __str__(self):
        return self.descricao


class VisitaTecnica(models.ModelPlus):
    campus = models.ForeignKeyPlus('rh.UnidadeOrganizacional', on_delete=models.CASCADE)
    data = models.DateFieldPlus('Data')
    instituicao_visitada = models.CharFieldPlus('Instituição Visitada', max_length=100)
    municipio = models.ForeignKeyPlus('comum.Municipio', verbose_name='Município', null=True, on_delete=models.CASCADE)
    logradouro = models.CharFieldPlus('Logradouro', null=True, blank=True)
    numero = models.CharField('Número', max_length=50, null=True, blank=True)
    complemento = models.CharFieldPlus('Complemento', null=True, blank=True)
    bairro = models.CharFieldPlus('Bairro', null=True, blank=True)
    cep = models.CharField('CEP', max_length=9, null=True, blank=True)
    objetivos = models.ManyToManyFieldPlus('projetos.ObjetivoVisitaTecnica')
    participantes = models.ManyToManyFieldPlus('rh.Servidor')
    encaminhamentos = models.CharFieldPlus('Encaminhamentos', max_length=5000)
    nome_contato = models.CharFieldPlus('Nome do Contato', max_length=150)
    telefone_contato = models.CharFieldPlus('Telefone do Contato', max_length=20)
    email_contato = models.CharFieldPlus('Email do Contato', max_length=100)
    cnpj = models.BrCnpjField(null=True, blank=True)
    deseja_parceria = models.BooleanField('Deseja parceria', null=True)

    class Meta:
        verbose_name = 'Visita Técnica'
        verbose_name_plural = 'Visitas Técnicas'

    def __str__(self):
        return f'Visita Técnica: {self.instituicao_visitada} - {format_(self.data)}'

    def get_deseja_parceria(self):
        if self.deseja_parceria is None:
            return 'Não informado'
        elif self.deseja_parceria:
            return 'Sim'
        return 'Não'

    def get_participantes(self):
        retorno = '<ul>'
        for participante in self.participantes.all():
            retorno += '<li>' + str(participante) + '</li>'
        retorno += '</ul>'
        return retorno


class HistoricoOrientacaoProjeto(models.ModelPlus):
    projeto = models.ForeignKeyPlus(Projeto, on_delete=models.CASCADE)
    orientado = models.ForeignKeyPlus(Participacao, on_delete=models.CASCADE, related_name='orientado_projeto')
    orientador = models.ForeignKeyPlus(Participacao, on_delete=models.CASCADE, related_name='orientador_projeto')
    data_inicio = models.DateFieldPlus()
    data_termino = models.DateFieldPlus(null=True, blank=True)

    class Meta:
        verbose_name = 'Histórico de Orientação do Projeto'
        verbose_name_plural = 'Históricos de Orientações do Projeto'

    def __str__(self):
        return str(self.projeto)


class ColaboradorVoluntario(models.ModelPlus):
    nome = models.CharField('Nome', max_length=255)
    prestador = models.OneToOneField('comum.PrestadorServico', related_name='projetos_colaborador_voluntario', on_delete=models.CASCADE)
    ativo = models.BooleanField('Ativo', default=True)
    email = models.EmailField('Email')
    telefone = models.CharFieldPlus('Telefone', max_length=255, null=True, blank=True)
    titulacao = models.ForeignKeyPlus(
        'rh.Titulacao', verbose_name='Titulação', related_name='projetos_colaborador_instituicao', on_delete=models.CASCADE
    )
    instituicao_origem = models.ForeignKeyPlus(
        'rh.Instituicao', blank=True, null=True, verbose_name='Instituição', related_name='projetos_instituicao_colaborador', on_delete=models.CASCADE
    )
    lattes = models.URLField(blank=True, null=True)
    documentacao = models.PrivateFileField(verbose_name='Documentação', upload_to='projetos/colaborador_voluntario', null=True, blank=True)
    eh_aposentado = models.BooleanField('É Servidor Aposentado', default=False)
    eh_vinculado_nucleo_arte = models.BooleanField('É Vinculado ao Núcleo de Arte', default=False)

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
        return '{}{}{}'.format(settings.SITE_URL, '/admin/projetos/colaboradorvoluntario/', self.id)


class NucleoExtensao(models.ModelPlus):
    nome = models.CharField('Nome', max_length=500)
    area_atuacao = models.CharField('Área de Atuação', max_length=5000)
    uo = models.ForeignKeyPlus(UnidadeOrganizacional, verbose_name='Campus', on_delete=models.CASCADE)
    coordenador = models.ForeignKeyPlus(Vinculo, verbose_name='Coordenador', null=True, on_delete=models.SET_NULL)
    descricao_atividades = models.TextField('Descrição das atividades', null=True)
    contato = models.CharFieldPlus('Contato', null=True, blank=True)
    horario_funcionamento = models.CharFieldPlus('Horário de funcionamento', null=True, blank=True)
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Núcleo de Extensão e Prática Profissional'
        verbose_name_plural = 'Núcleos de Extensão e Prática Profissional'
        ordering = ['nome']

    def __unicode__(self):
        return str(self.nome)


class RegistroFrequencia(models.ModelPlus):
    projeto = models.ForeignKeyPlus(Projeto, on_delete=models.CASCADE)
    descricao = models.CharFieldPlus(verbose_name='Descrição', max_length=2000)
    data = models.DateFieldPlus('Data')
    carga_horaria = models.PositiveIntegerField('Carga Horária', null=True, blank=True)
    cadastrada_por = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Cadastrado por', null=True, blank=True, related_name='projetos_cadastro_registrofrequencia'
    )
    cadastrada_em = models.DateTimeFieldPlus(verbose_name='Cadastrado em', null=True)
    atendida = models.BooleanField(verbose_name='Atendida', null=True)
    validada_por = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Avaliada por', null=True, blank=True, related_name='projetos_avaliacao_registrofrequencia'
    )
    validada_em = models.DateTimeFieldPlus(verbose_name='Avaliada em', null=True)

    class Meta:
        verbose_name = 'Registro de Frequência/Atividade do Projeto'
        verbose_name_plural = 'Registros de Frequência/Atividade do Projeto'

    def __str__(self):
        return 'Registro de Frequência/Atividade do Projeto'


class TermoParceriaAdesao(models.ModelPlus):
    projeto = models.ForeignKeyPlus(Projeto, on_delete=models.CASCADE)
    descricao = models.CharFieldPlus(verbose_name='Descrição', max_length=2000)
    arquivo = models.PrivateFileField('Termo de parceria/adesão', max_length=255, upload_to='projetos/termos_parcerias/')

    class Meta:
        verbose_name = 'Termo de Parceria/Adesão do Projeto'
        verbose_name_plural = 'Termos de Parceria/Adesão do Projeto'

    def __str__(self):
        return 'Termo de Parceria/Adesão do Projeto'


class MembroNEPP(models.ModelPlus):
    membro = models.ForeignKeyPlus(Vinculo, verbose_name='Membro', on_delete=models.CASCADE)
    nepp = models.ForeignKeyPlus(NucleoExtensao, verbose_name='NEPP', on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Membro do NEPP'
        verbose_name_plural = 'Membros do NEPP'

    def __str__(self):
        return str(self.membro)


class FotoNEPP(models.ModelPlus):
    descricao = models.CharField('Descrição', max_length=1000)
    nepp = models.ForeignKeyPlus(NucleoExtensao, verbose_name='NEPP', on_delete=models.CASCADE)
    imagem = models.ImageFieldPlus(upload_to='upload/projetos/nepp/fotos/')

    class Meta:
        verbose_name = 'Foto do NEPP'
        verbose_name_plural = 'Fotos do NEPP'

    def __str__(self):
        return str(self.descricao)


class AtividadeAutorizacaoSISBIO(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição', max_length=500)
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Atividade para Autorização no SISBIO'
        verbose_name_plural = 'Atividades para Autorização no SISBIO'


class AtividadeAutorizacaoSISGEN(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição', max_length=500)
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Atividade para Autorização no SISGEN'
        verbose_name_plural = 'Atividades para Autorização no SISGEN'


class OcorrenciaProjeto(models.ModelPlus):
    projeto = models.ForeignKeyPlus(Projeto, on_delete=models.CASCADE)
    ocorrencia = HTMLField('Ocorrência')
    anexo = models.FileFieldPlus('Anexo', upload_to='upload/projetos/ocorrencias/', null=True, blank=True)
    cadastrada_por = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Cadastrada por', null=True, blank=True, related_name='projetos_ocorrencia_cadastradapor'
    )
    cadastrada_em = models.DateTimeFieldPlus(verbose_name='Cadastrada em', auto_now_add=True)
    atualizada_em = models.DateTimeFieldPlus(verbose_name='Atualizada em', auto_now=True)

    class Meta:
        verbose_name = 'Ocorrência do Projeto'
        verbose_name_plural = 'Ocorrências dos Projetos'

    def __str__(self):
        return f'Ocorrência do Projeto {self.projeto.__str__()}: {self.ocorrencia}'


class HistoricoInteresseCusteioProjeto(models.ModelPlus):
    projeto = models.ForeignKeyPlus('projetos.Projeto', on_delete=models.CASCADE)
    tinha_interesse = models.BooleanFieldPlus('Tinha interesse?')
    tem_interesse = models.BooleanFieldPlus('Tem interesse?')
    justificativa = models.TextField('Justificativa')
    cadastrado_por = models.ForeignKey('comum.Vinculo', related_name='projetos_interessefomento_por', on_delete=models.CASCADE)
    cadastrado_em = models.DateTimeFieldPlus('Cadastrado em', auto_now_add=True)
    aceito = models.BooleanField('Aceito', null=True)
    avaliado_por = models.ForeignKey('comum.Vinculo', related_name='projetos_interessefomento_avaliadopor', on_delete=models.CASCADE, null=True)
    avaliado_em = models.DateTimeFieldPlus('Avaliado em', null=True)
    justificativa_avaliacao = models.CharFieldPlus('Justificativa', max_length=5000, null=True)

    class Meta:
        ordering = ['-cadastrado_em']
        verbose_name = 'Alteração no Interesse por Custeio'
        verbose_name_plural = 'Alterações no Interesse por Custeio'

    def __str__(self):
        return f'Alteração do Projeto: {self.projeto}'

    @property
    def get_status_display(self):
        if self.aceito is True:
            return format_html('<span class="status status-success">Sim</span>')
        elif self.aceito is False:
            return format_html('<span class="status status-error">Não</span>')
        return format_html('<span class="status status-alert">Aguardando Avaliação</span>')


class OfertaProjetoPorGrupo(models.ModelPlus):
    edital = models.ForeignKeyPlus(Edital, on_delete=models.CASCADE)
    grupo = models.CharFieldPlus('Grupo', max_length=5000)
    pre_selecionados = models.PositiveIntegerField(
        'Pré-Selecionados', help_text='Informe quantos projetos deste grupo poderão ser pré-selecionados', null=True
    )
    selecionados = models.PositiveIntegerField('Selecionados', help_text='Informe quantos projetos deste grupo poderão ser selecionados.', null=True)

    class Meta:
        indexes = [models.Index(fields=['edital', 'grupo'], name='projetos_ofertagrupo_indexes')]
        verbose_name = 'Oferta de Projeto por Grupo'
        verbose_name_plural = 'Ofertas de Projeto por Grupo'

    def __str__(self):
        return self.grupo

    def qtd_inscritos(self):
        return Projeto.objects.filter(grupo=self).count()

    def qtd_enviados(self):
        return Projeto.objects.filter(grupo=self).exclude(data_conclusao_planejamento=None).count()

    def qtd_pre_selecionados(self):
        return Projeto.objects.filter(grupo=self, pre_aprovado=True).count()

    def qtd_disponivel(self):
        return self.pre_selecionados - self.qtd_pre_selecionados()

    def qtd_selecionados(self):
        return Projeto.objects.filter(grupo=self, pre_aprovado=True, aprovado=True).count()

    def qtd_disponivel_selecao(self):
        return self.selecionados - self.qtd_selecionados()


class EditalArquivo(models.ModelPlus):
    edital = models.ForeignKeyPlus(Edital, on_delete=models.CASCADE)
    arquivo = models.FileFieldPlus(max_length=255, upload_to='upload/projetos/edital/', null=True, blank=True)
    id_documento_edital = models.PositiveIntegerField(verbose_name='ID do Documento do Edital', null=True, blank=True)
    data_cadastro = models.DateTimeFieldPlus('Data do Cadastro')
    vinculo_autor = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Autor', related_name='projetos_editalarquivo_vinculo', on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        ordering = ['-data_cadastro']


class CriterioPreSelecao(models.ModelPlus):
    edital = models.ForeignKeyPlus(Edital, verbose_name='Edital', on_delete=models.CASCADE)
    descricao = models.CharFieldPlus('Descrição', max_length=5000)
    texto_ajuda = models.TextField('Texto de ajuda', null=True, blank=True)

    class Meta:
        verbose_name = 'Critério para Pré-seleção'
        verbose_name_plural = 'Critérios para Pré-seleção'

    def __str__(self):
        return self.descricao


class PreSelecao(models.ModelPlus):
    projeto = models.ForeignKeyPlus(Projeto, verbose_name='Projeto', on_delete=models.PROTECT)
    avaliador = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Avaliador', on_delete=models.CASCADE)
    data = models.DateTimeFieldPlus('Data', auto_now=True)
    parecer = models.TextField('Parecer', null=True, blank=True)

    class Meta:
        verbose_name = 'Pré-seleção'
        verbose_name_plural = 'Pré-seleções'
        unique_together = ('projeto', 'avaliador')

    def __str__(self):
        return f'Pré-seleção do projeto: {self.projeto}'


class ItemPreSelecao(models.ModelPlus):
    criterio = models.ForeignKeyPlus(CriterioPreSelecao, verbose_name='Critério', on_delete=models.PROTECT)
    avaliacao = models.ForeignKeyPlus(PreSelecao, verbose_name='Pré-seleção', on_delete=models.PROTECT)
    aprovado = models.BooleanFieldPlus('Aprovado', null=True)

    class Meta:
        verbose_name = 'Item da Pré-seleção'
        verbose_name_plural = 'Itens da Pré-seleção'

    def __str__(self):
        return f'Item da Pré-seleção: {self.criterio.__str__()}'


class Comunicador(models.ModelPlus):
    AVALIADORES = 'Aval'
    COEX = 'COEX'
    PERSONALIZADO = 'Pers'
    DESTINARIOS = (
        (AVALIADORES, 'Avaliadores de projetos'),
        (COEX, 'Coordenadores de extensão'),
        (PERSONALIZADO, 'Informar manualmente'),
    )
    titulo = models.CharFieldPlus('Título', max_length=5000)
    conteudo = models.TextField('Conteúdo')
    destinatarios = models.TextField('Destinatários')
    cadastrado_por = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Cadastrado por', related_name='projetos_comunicador_cadastrado_por')
    cadastrado_em = models.DateTimeFieldPlus('Cadastrado em', auto_now_add=True)

    class Meta:
        verbose_name = 'Mensagem'
        verbose_name_plural = 'Mensagens'

    def __str__(self):
        return f'Mensagem enviada - {self.titulo}'


class ArquivoInativacaoProjeto(models.ModelPlus):
    projeto = models.ForeignKeyPlus(Projeto, on_delete=models.CASCADE)
    descricao = models.CharFieldPlus('Descrição', max_length=10000)
    arquivo = models.PrivateFileField('Arquivo', max_length=255, upload_to='projetos/inativacoes/')
    cadastrado_em = models.DateTimeFieldPlus(verbose_name='Cadastrada em', auto_now_add=True)

    class Meta:
        verbose_name = 'Arquivo de Inativação do Projeto'
        verbose_name_plural = 'Arquivos de Inativações dos Projetos'

    def __str__(self):
        return f'Arquivo de Inativação do Projeto {self.projeto.__str__()}: {self.descricao}'


class ArquivoFinalizacaoProjeto(models.ModelPlus):
    projeto = models.ForeignKeyPlus(Projeto, on_delete=models.CASCADE)
    descricao = models.CharFieldPlus('Descrição', max_length=10000)
    arquivo = models.PrivateFileField('Arquivo', max_length=255, upload_to='projetos/finalizacoes_sistemicas/')

    cadastrado_em = models.DateTimeFieldPlus(verbose_name='Cadastrada em', auto_now_add=True)

    class Meta:
        verbose_name = 'Arquivo de Finalização do Projeto'
        verbose_name_plural = 'Arquivos de Finalizações dos Projetos'

    def __str__(self):
        return f'Arquivo de finalização do projeto {self.projeto.__str__()}: {self.descricao}'
