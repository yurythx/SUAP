import datetime
import os
import tempfile
import traceback
from collections import OrderedDict
from collections.abc import Iterable
from decimal import Decimal
from threading import Thread

from tinymce.models import HTMLField
from dateutil.relativedelta import relativedelta
from django.apps import apps
from django.conf import settings
from django.contrib.auth.models import Group
from django.core.files.storage import default_storage
from django.core.validators import MaxLengthValidator
from django.db import transaction
from django.db.models import Count, Max, Q, QuerySet, Sum
from django.template.defaultfilters import pluralize
from django.utils.safestring import mark_safe

from cnpq.models import CurriculoVittaeLattes, Parametro
from comum.models import Arquivo, ObjetivoDesenvolvimentoSustentavel, Pais, SubobjetivoDesenvolvimentoSustentavel, User, Vinculo
from comum.utils import get_uo, tl
from djtools import forms
from djtools.db import models
from djtools.templatetags.filters import format_
from djtools.utils import print_, running_tests
from edu.models import Aluno, AreaCapes, AreaConcentracao, CursoCampus, Professor
from financeiro.models import NaturezaDespesa
from pesquisa import help_text
from processo_eletronico.models import Processo
from rh.models import Servidor, ServidorAfastamento, Titulacao, UnidadeOrganizacional

# Pré-avaliam projeto de qualquer campus; o Coordenador de Pesquisa só os do próprio (#17557).
GRUPOS_PRE_AVALIADORES_INSTITUCIONAIS = ['Diretor de Pesquisa', 'Pré-Avaliador Sistêmico de Projetos de Pesquisa']
# A pré-seleção e a impressão valem também para o Assessor de Pesquisa, sem as demais ações do pré-avaliador (#17570).
GRUPOS_PRE_SELECAO_INSTITUCIONAIS = [*GRUPOS_PRE_AVALIADORES_INSTITUCIONAIS, 'Assessor de Pesquisa']


def eh_planejamento(obj):
    hoje = datetime.datetime.now()
    if obj.data_cadastro is None:
        return False
    if isinstance(obj, Meta | Desembolso | ItemMemoriaCalculo):
        if hoje > obj.projeto.edital.fim_inscricoes:
            return obj.data_cadastro <= obj.projeto.edital.fim_inscricoes.date()
    elif isinstance(obj, Etapa):
        if hoje > obj.meta.projeto.edital.fim_inscricoes:
            if obj.data_cadastro <= obj.meta.projeto.edital.fim_inscricoes.date():
                return True
        else:
            return False
    return False


def get_mensagem_avaliacao(obj):
    string = ''
    if obj.dt_avaliacao and obj.justificativa_reprovacao:
        string += f'<span class="status status-error">Não Aprovado em {format_(obj.dt_avaliacao)}</span>'
        string += f'<span class="status status-error">Justificativa: {obj.justificativa_reprovacao}</span>'

    elif obj.dt_avaliacao and not obj.justificativa_reprovacao:
        string += f'<span class="status status-success">Aprovado em {format_(obj.dt_avaliacao)}</span>'

    if string:
        string += f' <p>Avaliador: {obj.avaliador}</p>'
        return string

    return ''


class EditalQueryset(QuerySet):
    def em_inscricao(self):
        agora = datetime.datetime.now()
        return self.filter(inicio_inscricoes__lte=agora, fim_inscricoes__gte=agora, autorizado=True, publicado=True)

    def em_pre_avaliacao(self):
        agora = datetime.datetime.now()
        qs = self.filter(inicio_pre_selecao__lte=agora, inicio_selecao__gt=agora) | self.filter(
            tipo_edital=Edital.PESQUISA_INOVACAO_CONTINUO, inicio_inscricoes__lte=agora, fim_inscricoes__gte=agora
        )
        return qs

    def em_avaliacao(self):
        agora = datetime.datetime.now()
        return self.filter(formato=Edital.FORMATO_COMPLETO, inicio_selecao__lte=agora, divulgacao_selecao__gte=agora) | self.filter(
            formato=Edital.FORMATO_COMPLETO, tipo_edital=Edital.PESQUISA_INOVACAO_CONTINUO, inicio_inscricoes__lte=agora, fim_inscricoes__gte=agora
        )

    def em_selecao(self):
        agora = datetime.datetime.now()
        return self.filter(formato=Edital.FORMATO_COMPLETO, inicio_selecao__lte=agora, fim_selecao__gte=agora) | self.filter(
            formato=Edital.FORMATO_COMPLETO, tipo_edital=Edital.PESQUISA_INOVACAO_CONTINUO, inicio_inscricoes__lte=agora, fim_inscricoes__gte=agora
        )

    def em_distribuicao_bolsa(self):
        agora = datetime.datetime.now()
        return self.filter(fim_selecao__lt=agora, divulgacao_selecao__gte=agora)

    def finalizados(self):
        agora = datetime.datetime.now()
        return self.filter(divulgacao_selecao__lt=agora) | self.filter(tipo_edital=Edital.PESQUISA_INOVACAO_CONTINUO, fim_inscricoes__lt=agora)

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
        return self.filter(data_avaliacao_recurso__gt=hoje, data_recurso__lt=hoje)


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

    def em_distribuicao_bolsa(self):
        return self.get_queryset().em_distribuicao_bolsa()

    def finalizados(self):
        return self.get_queryset().finalizados()

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


class ItemMemoriaCalculoManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related('despesa')


class Edital(models.ModelPlus):
    SEARCH_FIELDS = ['titulo']

    PESQUISA_INOVACAO_CONTINUO = '3'
    PESQUISA = '1'
    INOVACAO = '2'
    CAMPUS = '1'
    GERAL = '2'
    TIPO_EDITAL_PESQUISA = ((PESQUISA, 'Pesquisa'), (INOVACAO, 'Inovação'), (PESQUISA_INOVACAO_CONTINUO, 'Pesquisa/Inovação Contínuo'))

    TIPO_FORMA_SELECAO_CHOICES = ((CAMPUS, 'Campus'), (GERAL, 'Geral'))

    FORMATO_COMPLETO = 'Completo'
    FORMATO_SIMPLIFICADO = 'Simplificado'
    FORMATO_EDITAL_CHOICES = ((FORMATO_COMPLETO, FORMATO_COMPLETO), (FORMATO_SIMPLIFICADO, FORMATO_SIMPLIFICADO))
    ATIVIDADES = 'Atividades'
    RELATORIOS = 'Relatórios'
    TIPO_MONITORAMENTO_CHOICES = ((ATIVIDADES, ATIVIDADES), (RELATORIOS, RELATORIOS))
    objects = EditalManager()

    titulo = models.CharField('Título', max_length=255)
    descricao = models.TextField('Descrição')
    tipo_edital = models.CharField('Tipo do Edital', max_length=10, choices=TIPO_EDITAL_PESQUISA)
    forma_selecao = models.CharField('Forma de Seleção', max_length=10, choices=TIPO_FORMA_SELECAO_CHOICES, default=CAMPUS)
    campus_especifico = models.BooleanField(
        'Edital de Campus',
        default=False,
        help_text='Caso esta opção seja marcada, os projetos deste edital poderão ser avaliados por servidores do mesmo campus do projeto.',
    )
    qtd_bolsa_alunos = models.PositiveIntegerField(
        'Total de Bolsas para Alunos', help_text='Número máximo de bolsas para alunos.', null=True, default=0
    )
    qtd_bolsa_servidores = models.PositiveIntegerField(
        'Total de Bolsas para Servidores', help_text='Número máximo de bolsas para servidores.', null=True, default=0
    )

    formato = models.CharFieldPlus('Formato do Edital', max_length=20, choices=FORMATO_EDITAL_CHOICES, default=FORMATO_COMPLETO)
    inicio_inscricoes = models.DateTimeFieldPlus('Início das Inscrições')
    fim_inscricoes = models.DateTimeFieldPlus('Fim das Inscrições')
    arquivo = models.OneToOneField(Arquivo, null=True, blank=True, related_name='pesquisa_edital_arquivo', on_delete=models.CASCADE)
    inicio_pre_selecao = models.DateTimeFieldPlus('Início da Pré-Seleção', null=True)
    fim_pre_selecao = models.DateTimeFieldPlus('Fim da Pré-Seleção', null=True, blank=True)
    data_recurso_pre_selecao = models.DateTimeFieldPlus('Data Limite Para Recursos da Pré-Seleção', null=True, blank=True)
    inicio_selecao = models.DateTimeFieldPlus('Início da Seleção', null=True)
    fim_selecao = models.DateTimeFieldPlus('Fim da Seleção', null=True)
    data_recurso = models.DateTimeFieldPlus('Data Limite Para Recursos', null=True, blank=True)
    data_avaliacao_recurso = models.DateTimeFieldPlus('Data Limite Para Avaliação dos Recursos', null=True, blank=True)
    divulgacao_selecao = models.DateTimeFieldPlus('Divulgação da Seleção', null=True)
    coordenador_pode_receber_bolsa = models.BooleanField('Coordenador pode receber bolsa', default=True)
    exige_grupo_pesquisa = models.BooleanField(
        'Apenas para membros de grupo de pesquisa',
        help_text='Marque esta opção se somente servidor vinculado a um grupo de pesquisa da Instituição pode submeter projeto.',
        default=True,
    )
    participa_aluno = models.BooleanField('Participa Aluno', help_text='Marque esta opção caso alunos possam participar do projeto.', default=False)
    qtd_maxima_alunos = models.PositiveIntegerField('Total de Alunos', help_text='Número máximo de alunos em cada projeto.', null=True, default=0)
    qtd_maxima_alunos_bolsistas = models.PositiveIntegerField(
        'Total de Alunos Bolsistas', help_text='Número máximo de alunos candidatos à bolsa em cada projeto.', null=True, default=0
    )
    participa_servidor = models.BooleanField(
        'Participa Servidor', help_text='Marque esta opção caso servidores possam participar do projeto.', default=False
    )
    qtd_maxima_servidores = models.PositiveIntegerField(
        'Total de Servidores', help_text='Número máximo de servidores em cada projeto.', null=True, default=0
    )
    qtd_maxima_servidores_bolsistas = models.PositiveIntegerField(
        'Total de Servidores Bolsistas', help_text='Número máximo de servidores candidatos à bolsa em cada projeto.', null=True, default=0
    )
    qtd_anos_anteriores_publicacao = models.PositiveIntegerField(
        'Anos de consideração das Publicações',
        help_text='Exemplo: Ao informar *3* anos para edital cadastrado em 2024, serão consideradas as publicações realizadas entre 2021 e 2024.',
        null=True,
        default=0,
    )
    peso_avaliacao_lattes_coordenador = models.PositiveIntegerField(
        'Peso da Avaliação do Coordenador (%)',
        help_text='Informe o peso em percentual que será usado na Avaliação do Coordenador do Projeto através do currículo Lattes',
        null=True,
        default=0,
    )
    peso_avaliacao_projeto = models.PositiveIntegerField(
        'Peso da Avaliação do Projeto (%)', help_text='Informe o peso em percentual que será usado na Avaliação do Projeto', null=True, default=0
    )
    peso_avaliacao_grupo_pesquisa = models.PositiveIntegerField(
        'Peso da Avaliação do Grupo de Pesquisa (%)',
        help_text='Informe o peso em percentual que será usado na Avaliação do Grupo de Pesquisa do projeto. A nota de avaliação será a soma das pontuações dos currículos dos servidores que fazem parte do grupo de pesquisa.',
        null=True,
        default=0,
    )
    inclusao_bolsas_ae = models.DateTimeFieldPlus('Data da geração das bolsas no AE', null=True)
    data_avaliacao_classificacao = models.DateTimeFieldPlus('Data de Avaliação da Classificação', null=True, blank=True)
    termo_compromisso_coordenador = HTMLField(
        'Termo de Compromisso do Coordenador', help_text='Informe o termo de compromisso do coordenador do projeto.', null=True, blank=True
    )
    termo_compromisso_servidor = HTMLField(
        'Termo de Compromisso do Servidor', help_text='Informe o termo de compromisso do servidor participante do projeto.', null=True, blank=True
    )
    termo_compromisso_aluno = HTMLField(
        'Termo de Compromisso do Aluno', help_text='Informe o termo de compromisso do aluno participante do projeto.', null=True, blank=True
    )
    termo_compromisso_colaborador_externo = HTMLField(
        'Termo de Compromisso do Colaborador Externo',
        help_text='Informe o termo de compromisso do colaborador externo participante do projeto.',
        null=True,
        blank=True,
    )
    termo_compromisso_colaborador_externo_en = HTMLField(
        'Termo de Compromisso do Colaborador Externo em Inglês',
        help_text='Informe o termo de compromisso, em inglês, do colaborador externo participante do projeto.',
        null=True,
        blank=True,
    )
    termo_compromisso_colaborador_externo_es = HTMLField(
        'Termo de Compromisso do Colaborador Externo em Espanhol',
        help_text='Informe o termo de compromisso, em espanhol, do colaborador externo participante do projeto.',
        null=True,
        blank=True,
    )
    termo_compromisso_colaborador_externo_fr = HTMLField(
        'Termo de Compromisso do Colaborador Externo em Francês',
        help_text='Informe o termo de compromisso, em francês, do colaborador externo participante do projeto.',
        null=True,
        blank=True,
    )
    ch_semanal_coordenador = models.PositiveIntegerField('Carga Horária do Coordenador', help_text='Carga horária semanal do coordenador.', default=4)
    nota_corte_projeto_fluxo_continuo = models.PositiveIntegerField(
        'Ponto de Corte para Aprovação de Projeto (%)',
        help_text='Informe o percentual minímo exigido da pontuação máxima para considerar um projeto aprovado.',
        null=True,
        default=0,
    )
    permite_coordenador_com_bolsa_previa = models.BooleanField(
        'Coordenador com mais de uma bolsa',
        help_text='Marque esta opção caso este edital permita que o coordenador seja bolsista mesmo que ele já receba bolsa em outro projeto em execução atualmente.',
        default=False,
    )
    cadastrado_por_vinculo = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Cadastrado por', null=True, blank=True, related_name='pesquisa_vinculo_cadastro_edital'
    )
    cadastrado_em = models.DateTimeFieldPlus('Cadastrado em', null=True)
    autorizado = models.BooleanField('Edital autorizado', default=True, null=True)
    autorizado_por_vinculo = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Autorizado por', null=True, blank=True, related_name='pesquisa_vinculo_autoriza_cadastro_edital'
    )
    autorizado_em = models.DateTimeFieldPlus('Autorizado em', null=True)
    lattes_obrigatorio = models.BooleanField(
        'Currículo Lattes Obrigatório',
        default=True,
        help_text='Marque esta opção caso apenas os alunos que informaram a URL do Currículo Lattes possam ser adicionados na equipe do projeto.',
    )
    tempo_maximo_meses_curriculo_desatualizado = models.PositiveIntegerField(
        'Período máximo currículo desatualizado',
        default=6,
        help_text='Período máximo em meses que o curriculo do Coordenador pode estar desatualizado para aceitação de projetos.',
    )
    titulacoes_avaliador = models.ManyToManyFieldPlus(
        Titulacao,
        verbose_name='Titulações dos Avaliadores',
        help_text='Selecione quais titulações serão permitidas para os avaliadores deste edital.',
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
    discente_proprio_campus = models.BooleanField(
        'Apenas Alunos do Campus do Projeto',
        default=False,
        help_text='Marque esta opção caso só seja permitida a participação de alunos do mesmo campus do projeto.',
    )
    impedir_projeto_sem_anexo = models.BooleanField(
        'Impedir Projetos sem Anexos',
        default=False,
        help_text='Marque esta opção para impedir que projetos sem anexos cadastrados avancem para a fase de pré-seleção.',
    )
    exige_anuencia = models.BooleanField(
        'Exigir Anuência da Chefia',
        default=False,
        help_text='Marque esta opção para que apenas os projetos com registro da anuência da chefia avancem para a fase de pré-seleção.',
    )
    impedir_coordenador_com_pendencia = models.BooleanField(
        'Impedir Submissão de Coordenador com Pendência',
        default=False,
        help_text='Marque esta opção para impedir que coordenadores de projetos com conclusão em atraso submetam projetos para este edital.',
    )
    imprimir_certificado = models.BooleanField(
        'Permitir Impressão do Certificado de Participação',
        help_text='Marque este campo se quiser permitir que os membros do projeto possam emitir o certificado de participação, na aba "Equipe", quando o projeto estiver concluído.',
        default=True,
    )
    permite_colaborador_externo = models.BooleanField(
        'Permite Colaborador Externo',
        help_text='Marque esta opção caso seja permitida a inclusão de colaborador externo nas equipes dos projetos',
        default=False,
    )
    exige_comissao = models.BooleanField(
        'Exigir Comissão de Avaliação',
        default=True,
        help_text='Marque esta opção para que apenas membros da comissão de avaliação do edital possam ser indicados como avaliadores dos projetos. Caso contrário, qualquer usuário registrado como avaliador e que tenha a titulação exigida pelo edital poderá ser indicado.',
    )
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
    tipo_monitoramento = models.CharField(
        'Tipo de Monitoramento dos Projetos',
        max_length=15,
        choices=TIPO_MONITORAMENTO_CHOICES,
        default=ATIVIDADES,
        help_text='Por atividades exige a validação de atividades e gastos para conclusão do projeto. Por relatórios exige o cadastro de pelo menos um relatório parcial e um final no projeto.',
    )
    pontuacao_diferenciada_maternidade = models.BooleanField(
        'Pontuação diferenciada no currículo de quem se ausentou por licença maternidade',
        default=False,
        help_text='O período considerado será de 2 anos adicionais a cada licença maternidade. Ex: se o edital considera a produção de 2019 a 2021 e houve uma licença maternidade entre 2018 e 2021, então será considerada a produção de 2017 a 2021.',
    )
    responsavel_pode_registrar_execucao = models.BooleanField(
        'Responsável pela atividade pode registrar execução',
        default=False,
        help_text='Marque esta opção para permitir que o responsável pela atividade também possa registrar a execução da mesma.',
    )
    permite_uso_cartao_pesquisador = models.BooleanField(
        'Permitir uso do cartão BB Pesquisa',
        default=False,
        help_text='Marque esta opção para permitir que o coordenador do projeto informe se tem interesse ou não no fomento através do uso do cartão BB pesquisa.',
    )
    aluno_pos_pode_submeter = models.BooleanField(
        'Aluno de pós-graduação pode submeter',
        default=False,
        help_text='Marque esta opção para permitir que alunos de pós-graduação possam submeter projeto.',
    )
    colaborador_externo_pode_submeter = models.BooleanField(
        'Pós-doutorando pode submeter', default=False, help_text='Marque esta opção para permitir que pós-doutorandos possam submeter projeto.'
    )
    utiliza_metodologia_trl = models.BooleanField(
        'Utilizar metodologia TRL',
        default=False,
        help_text='Marque esta opção para solicitar que o coordenador do projeto informe a classificação TRL do projeto.',
    )
    pode_escolher_campus_submissao = models.BooleanField(
        'Pode escolher campus de submissão',
        default=False,
        help_text='Marque esta opção para permitir que o coordenador do projeto possa vincular o projeto à qualquer campus durante a submissão.',
    )
    exigir_participacao_como_avaliador = models.BooleanField(
        'Exigir quantidade mínima de avaliações',
        default=False,
        help_text='Marque esta opção para definir a quantidade mínima de avaliações realizadas pelo coordenador do projeto em editais anteriores para poder submeter.',
    )
    quantidade_avaliacoes = models.IntegerFieldPlus(
        'Quantidade mínima de avaliações',
        null=True,
        blank=True,
        help_text='Informe a quantidade mínima de avaliações que o coordenador do projeto deve ter realizado no período informado no campo anterior.',
    )
    anos_avaliacoes_considerar = models.IntegerFieldPlus(
        'Quantidade de anos a se considerar',
        null=True,
        blank=True,
        help_text='Exemplo: Ao informar *3* anos para edital cadastrado em 2024, serão consideradas as avaliações realizadas entre 2021 e 2024.',
    )
    impedir_submissao_de_avaliador = models.BooleanField(
        'Impedir que quem submeteu possa avaliar',
        default=False,
        help_text='Marque esta opção para impedir que quem submeteu projeto neste edital possa ser indicado como avaliador de projetos deste edital.',
    )
    permitir_finalizar_sem_validacao_desembolsos = models.BooleanField(
        'Permitir finalizar o projeto sem validação dos desembolsos',
        default=False,
        help_text='Marque esta opção para permitir a finalização dos projetos mesmo com desembolsos não validados.',
    )
    submeter_pelo_campus_exercicio = models.BooleanField(
        'Submeter apenas pelo campus de exercício',
        default=False,
        help_text='Marque esta opção para que o coordenador só possa vincular o projeto ao campus de exercício.',
    )
    permite_indicacao_tardia_equipe = models.BooleanField(
        'Permite Cadastrar Aluno sem Identificá-lo',
        help_text='Marque esta opção para permitir que o coordenador do projeto possa registar a participação de alunos na equipe durante a submissão do projeto mas sem indicar especificamente quais alunos serão.',
        default=False,
    )
    permite_enviar_um_projeto = models.BooleanField(
        'Permite apenas uma submissão por coordenador',
        help_text='Marque esta opção para permitir que o coordenador só possa submeter um projeto neste edital.',
        default=False,
    )
    avaliador_ve_anexos = models.BooleanField(
        'Avaliador pode ver aba "Anexos"',
        help_text='Marque esta opção para permitir que o avaliador do projeto possa ver a aba "Anexos" durante a fase de avaliação.',
        default=False,
    )
    aviso_aos_avaliadores = HTMLField(
        'Aviso aos avaliadores',
        help_text='O conteúdo deste campo será exibido na tela do formulário de avaliação do projeto. Para não exibir nenhum aviso, deixe este campo em branco.',
        null=True,
        blank=True,
    )
    publicado = models.BooleanField(
        'Publicado?',
        default=True,
        help_text='Desmarque esta opção para ocultar este edital da lista disponível em Pesquisa -> Editais -> Editais.',
    )
    permite_afastado_submeter = models.BooleanField(
        'Permitir que servidor afastado submeta',
        help_text='Marque esta opção para permitir que servidores em afastamento possam submeter projeto.',
        default=False,
    )
    ignorar_termo_pendente = models.BooleanField(
        'Ignorar termo de compromisso pendente de aceite',
        help_text='Marque esta opção para permitir que projetos com termo de compromisso pendente de aceite possam ser pré-avaliados.',
        default=False,
    )
    exibir_aba_calculo_pontuacao = models.BooleanField(
        'Exibir a aba "Cálculo da pontuação"',
        help_text='Marque esta opção para exibir a aba "Cálculo da pontuação" na tela do projeto mesmo que o "Peso da Avaliação do Coordenador" do edital seja zero.',
        default=False,
    )

    class Meta:
        verbose_name = 'Edital'
        verbose_name_plural = 'Editais'

        permissions = (('pode_ver_config_edital', 'Pode ver configuração edital'),)

    def __str__(self):
        if self.tipo_edital == Edital.PESQUISA_INOVACAO_CONTINUO:
            return f'{self.titulo} - Edital de Fluxo {self.get_tipo_edital_display()}'
        else:
            return f'{self.titulo} - Edital de {self.get_tipo_edital_display()}'

    def tem_formato_completo(self):
        return self.formato == Edital.FORMATO_COMPLETO

    def pendente_avaliacao(self) -> bool:
        user = tl.get_user()
        indicacoes = AvaliadorIndicado.objects.filter(
            vinculo=user.get_vinculo(), projeto__edital=self, projeto__pre_aprovado=True, rejeitado=False
        ).values_list('projeto', flat=True)
        avalicoes_realizadas = Avaliacao.objects.filter(projeto__in=indicacoes, vinculo=user.get_vinculo()).values_list('projeto', flat=True)
        return Projeto.objects.filter(id__in=indicacoes).exclude(id__in=avalicoes_realizadas).exists()

    def classifica_projetos_pesquisa(self, uo=None):
        if self.forma_selecao == Edital.CAMPUS and uo is None:
            # Refaz a classificação de todos os projetos do referido edital
            projetos_pre_aprovados = Projeto.objects.filter(edital=self, pre_aprovado=True)
            uo_ids = projetos_pre_aprovados.values_list('uo', flat=True).distinct()
            uos = UnidadeOrganizacional.objects.suap().filter(id__in=uo_ids)
            for uo in uos:
                self._classifica_projetos_pesquisa(uo)
        else:
            self._classifica_projetos_pesquisa(uo)

    def _classifica_projetos_pesquisa(self, uo=None):
        if self.forma_selecao == Edital.GERAL:
            distribuicao_ja_realizada = self.data_avaliacao_classificacao is not None
        else:
            distribuicao_ja_realizada = self.bolsadisponivel_set.get(uo=uo).data_avaliacao_classificacao is not None

        if not distribuicao_ja_realizada:
            # não precisa, a pontuação total é calculada a cada avaliação e a cada atualização do currículo lattes.
            # for projeto in self.projeto_set.filter(pre_aprovado=True):
            #     projeto.atualizar_pontuacao_total()

            if self.forma_selecao == Edital.CAMPUS:
                qs = Projeto.objects.filter(edital=self, uo=uo, pre_aprovado=True).order_by('-pontuacao_total')
                try:
                    qtd_bolsa_pesquisador = self.bolsadisponivel_set.get(uo=uo).num_maximo_pesquisador
                    qtd_bolsa_ic = self.bolsadisponivel_set.get(uo=uo).num_maximo_ic
                except Exception:
                    qtd_bolsa_pesquisador = 0
                    qtd_bolsa_ic = 0
            else:
                qs = Projeto.objects.filter(edital=self, pre_aprovado=True).order_by('-pontuacao_total')
                qtd_bolsa_pesquisador = self.qtd_bolsa_servidores
                qtd_bolsa_ic = self.qtd_bolsa_alunos

            qs.update(aprovado=False)
            distribuiu_pesquisador = False
            distribuiu_ic = False
            for projeto in qs:
                # a pontuacao nos criterios de avaliacao do projeto precisam ser maior do que 50%
                if projeto.pontuacao >= 5.00:
                    participacoes = Participacao.objects.filter(projeto=projeto, vinculo=TipoVinculo.BOLSISTA)
                    participacoes.update(bolsa_concedida=False)
                    for participacao in participacoes:
                        if participacao.is_servidor():
                            if qtd_bolsa_pesquisador > 0:
                                participacao.bolsa_concedida = True
                                participacao.save()
                                distribuiu_pesquisador = True
                                qtd_bolsa_pesquisador = qtd_bolsa_pesquisador - 1
                        else:
                            if qtd_bolsa_ic > 0:
                                participacao.bolsa_concedida = True
                                participacao.save()
                                distribuiu_ic = True
                                qtd_bolsa_ic = qtd_bolsa_ic - 1
                    if distribuiu_pesquisador or distribuiu_ic:
                        projeto.aprovado = True
                        projeto.save()
                    distribuiu_pesquisador = False
                    distribuiu_ic = False

    def normalizar_pontuacao_curriculo_lattes(self, uo=None, task=None):
        projetos_pre_aprovados = Projeto.objects.filter(edital=self, pre_aprovado=True)
        if self.forma_selecao == Edital.CAMPUS:
            if uo is None:
                uos = self.get_uos_edital_pesquisa()
            else:
                uos = [uo]
            if task:
                uos = task.iterate(uos)
            for campus in uos:
                maior_pontuacao_curriculo = 0
                projetos_pre_aprovados_do_campus = projetos_pre_aprovados.filter(uo=campus)
                vqs = projetos_pre_aprovados_do_campus.aggregate(maior_pontuacao_curriculo=Max('pontuacao_curriculo'))
                if vqs:
                    maior_pontuacao_curriculo = vqs['maior_pontuacao_curriculo']
                for projeto in projetos_pre_aprovados_do_campus:
                    projeto.atualizar_pontuacao_curriculo_lattes(maior_pontuacao_curriculo)
        else:
            maior_pontuacao_curriculo = 0
            vqs = projetos_pre_aprovados.aggregate(maior_pontuacao_curriculo=Max('pontuacao_curriculo'))
            if vqs:
                maior_pontuacao_curriculo = vqs['maior_pontuacao_curriculo']
            if task:
                projetos_pre_aprovados = task.iterate(projetos_pre_aprovados)
            for projeto in projetos_pre_aprovados:
                projeto.atualizar_pontuacao_curriculo_lattes(maior_pontuacao_curriculo)

    def normalizar_pontuacao_grupo_pesquisa(self, uo=None, task=None):
        projetos_pre_aprovados = Projeto.objects.filter(edital=self, pre_aprovado=True)
        if self.forma_selecao == Edital.CAMPUS:
            if uo is None:
                uos = self.get_uos_edital_pesquisa()
            else:
                uos = [uo]
            if task:
                uos = task.iterate(uos)
            for campus in uos:
                maior_pontuacao_curriculo = 0
                projetos_pre_aprovados_do_campus = projetos_pre_aprovados.filter(uo=campus)
                vqs = projetos_pre_aprovados_do_campus.aggregate(maior_pontuacao_curriculo=Max('pontuacao_grupo_pesquisa'))
                if vqs:
                    maior_pontuacao_curriculo = vqs['maior_pontuacao_curriculo']
                for projeto in projetos_pre_aprovados_do_campus:
                    projeto.atualizar_pontuacao_grupo_pesquisa(maior_pontuacao_curriculo)
        else:
            maior_pontuacao_curriculo = 0
            vqs = projetos_pre_aprovados.aggregate(maior_pontuacao_curriculo=Max('pontuacao_grupo_pesquisa'))
            if vqs:
                maior_pontuacao_curriculo = vqs['maior_pontuacao_curriculo']
            if task:
                projetos_pre_aprovados = task.iterate(projetos_pre_aprovados)
            for projeto in projetos_pre_aprovados:
                projeto.atualizar_pontuacao_grupo_pesquisa(maior_pontuacao_curriculo)

    def get_elementos_despesa(self):
        return NaturezaDespesa.objects.filter(id__in=self.recurso_set.values_list('despesa_id', flat=True))

    def get_uos_edital_pesquisa(self):
        return UnidadeOrganizacional.objects.suap().filter(id__in=self.bolsadisponivel_set.values_list('uo', flat=True))

    def get_form(self):
        edital = self

        class CustomForm(forms.FormPlus):
            fieldsets = (('titulo', {'fields': ('item_1', 'item_2')}),)

            def clean(self):
                super().clean()
                for valor_parametro in list(self.cleaned_data.values()):
                    if valor_parametro and valor_parametro < 0:
                        raise forms.ValidationError('Os valores não podem ser negativos.')
                return self.cleaned_data

            def save(self, *args, **kwargs):
                for field_name, valor_parametro in list(self.cleaned_data.items()):
                    if not field_name.startswith('item_') and not field_name.startswith('maximo_'):
                        continue
                    nome_variavel = field_name.split('_')[0]
                    item_id = int(field_name.split('_')[-1])
                    item = ParametroEdital.objects.get_or_create(parametro_id=item_id, edital=edital)[0]
                    if nome_variavel == 'item':
                        item.valor_parametro = valor_parametro
                    else:
                        item.qtd_maxima = valor_parametro
                    item.save(args, kwargs)

        fieldsets = OrderedDict()
        for parametro in Parametro.objects.all().order_by('codigo'):
            if not fieldsets.get(parametro.grupo):
                fieldsets[parametro.grupo] = []

            parametro_edital = ParametroEdital.objects.get_or_create(parametro=parametro, edital=edital)[0]
            field = parametro.get_form_field(initial=parametro_edital.valor_parametro)
            field_name = f'item_{parametro.pk}'
            field_maximo = f'maximo_{parametro.pk}'
            fieldsets.get(parametro.grupo).append([field_name, field_maximo])
            CustomForm.base_fields[field_name] = field
            CustomForm.base_fields[field_maximo] = forms.IntegerFieldPlus(
                label='Quantidade Máxima',
                help_text='Quantidade Máxima a ser considerada. Deixe em branco se não houver limite.',
                initial=parametro_edital.qtd_maxima,
                required=False,
            )

        grupos = []
        for titulo, fields in list(fieldsets.items()):
            grupos.append((titulo, {'fields': fields}))
        CustomForm.fieldsets = grupos
        return CustomForm

    @transaction.atomic
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    def is_periodo_inscricao(self):
        agora = datetime.datetime.now()
        return self.inicio_inscricoes <= agora <= self.fim_inscricoes

    def is_periodo_fim_inscricao(self):
        agora = datetime.datetime.now()
        if self.tipo_edital == Edital.PESQUISA_INOVACAO_CONTINUO:
            return self.fim_inscricoes <= agora
        return self.inicio_pre_selecao and self.fim_inscricoes < agora < self.inicio_pre_selecao

    def is_periodo_antes_pre_selecao(self):
        if not self.tem_formato_completo():
            return False
        agora = datetime.datetime.now()
        if self.tipo_edital == Edital.PESQUISA_INOVACAO_CONTINUO:
            return self.inicio_pre_selecao and self.inicio_pre_selecao <= agora < self.fim_inscricoes
        return self.inicio_pre_selecao and self.inicio_inscricoes < agora < self.inicio_pre_selecao

    def is_periodo_pre_selecao(self):
        agora = datetime.datetime.now()
        if self.tipo_edital == Edital.PESQUISA_INOVACAO_CONTINUO:
            return self.inicio_pre_selecao and self.inicio_pre_selecao <= agora < self.fim_inscricoes
        return self.inicio_pre_selecao and self.inicio_selecao and self.inicio_pre_selecao <= agora < self.inicio_selecao

    def is_periodo_selecao(self):
        if not self.tem_formato_completo():
            return False
        agora = datetime.datetime.now()
        if self.tipo_edital == Edital.PESQUISA_INOVACAO_CONTINUO:
            return self.inicio_selecao and self.fim_inscricoes and self.inicio_selecao <= agora < self.fim_inscricoes
        return self.inicio_selecao and self.fim_selecao and self.inicio_selecao <= agora < self.fim_selecao

    def is_periodo_selecao_e_pre_divulgacao(self):
        agora = datetime.datetime.now()
        if self.tipo_edital == Edital.PESQUISA_INOVACAO_CONTINUO:
            return self.inicio_selecao and self.fim_inscricoes and self.inicio_selecao <= agora < self.fim_inscricoes
        return self.inicio_selecao and self.divulgacao_selecao and self.inicio_selecao <= agora < self.divulgacao_selecao

    def is_periodo_divulgacao(self):
        if self.tem_formato_completo():
            agora = datetime.datetime.now()
            # Deve-se editar o edital e colocar a data de divulgação igual a data de inscrição do edital.
            # if self.tipo_edital == Edital.PESQUISA_INOVACAO_CONTINUO:
            #     return self.inicio_selecao <= agora
            return self.divulgacao_selecao and self.divulgacao_selecao <= agora
        return True

    def is_periodo_pos_pre_selecao(self):
        agora = datetime.datetime.now()
        return self.inicio_pre_selecao and agora > self.inicio_pre_selecao

    def is_periodo_recurso(self):
        agora = datetime.datetime.now()
        if self.tipo_edital == Edital.PESQUISA_INOVACAO_CONTINUO:
            return self.inicio_selecao and self.fim_inscricoes and self.inicio_selecao <= agora < self.fim_inscricoes
        return self.inicio_pre_selecao <= agora <= self.data_recurso

    def is_periodo_pos_fim_selecao(self):
        agora = datetime.datetime.now()
        if self.tipo_edital == Edital.PESQUISA_INOVACAO_CONTINUO:
            return self.divulgacao_selecao and agora >= self.divulgacao_selecao
        return self.fim_selecao and self.fim_selecao <= agora

    def is_periodo_resultado_parcial(self):
        agora = datetime.datetime.now()
        if self.tipo_edital == Edital.PESQUISA_INOVACAO_CONTINUO:
            return self.inicio_selecao and self.fim_inscricoes and self.inicio_selecao <= agora < self.fim_inscricoes
        return self.data_recurso and agora <= self.data_recurso and self.data_avaliacao_classificacao

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
        return BolsaDisponivel.objects.filter(edital=self).order_by('uo')

    def get_forma_selecao(self):
        if self.forma_selecao == Edital.CAMPUS:
            return 'Por Campus'
        else:
            return 'Geral'

    def pode_divulgar_resultado_pesquisa(self):
        agora = datetime.datetime.now()
        return self.divulgacao_selecao and self.divulgacao_selecao <= agora and self.data_avaliacao_classificacao

    def eh_edital_continuo(self):
        return self.tipo_edital == Edital.PESQUISA_INOVACAO_CONTINUO

    @staticmethod
    def _redistribuir_bolsas(projetos: QuerySet, ids_bolsa_concedida: Iterable[str], participacoes_da_categoria: QuerySet) -> None:
        """Concede bolsa às participações marcadas e retira das demais da categoria (servidores ou alunos).

        Ids que não são de participação dos ``projetos`` em distribuição são ignorados (#17556).
        """
        for participacao in Participacao.objects.filter(projeto__in=projetos, id__in=ids_bolsa_concedida, bolsa_concedida=False):
            participacao.adicionar_registro_historico_equipe(HistoricoEquipe.EVENTO_CONCEDER_BOLSAR)
            Participacao.objects.filter(id=participacao.id).update(bolsa_concedida=True)

        for participacao in participacoes_da_categoria.exclude(id__in=ids_bolsa_concedida).filter(bolsa_concedida=True):
            participacao.adicionar_registro_historico_equipe(HistoricoEquipe.EVENTO_NAOCONCEDER_BOLSA)
            Participacao.objects.filter(id=participacao.id).update(bolsa_concedida=False)

    def distribuir_bolsas(
        self, ids_participacao_de_servidor_bolsa_concedida, ids_participacao_de_aluno_bolsa_concedidas, ids_projetos_aprovados, id_uo=None
    ):
        """
        Este método é responsáel por registrar as mudanças feitas oriundas da tela de distribuição de bolsas.
        A distribuição de bolsa só ocorrerar se as bolsas concedidas para pesquisador e/ou para alunos NÃO superar
        as respectivas quantidades máximas de bolsas definidadas no cadastro do edital

        :param ids_participacao_de_servidor_bolsa_concedida: lista de ids de participação que tiveram bolsas concedidas para servidores
        :param ids_participacao_de_aluno_bolsa_concedidas: lista de ids de participação que tiveram bolsas concedidas para alunos
        :param ids_projetos_aprovados: lista de ids de projetos marcados como aprovados
        :param id_uo: ID do campus que realizou a distribuição de bolsas. Pode ser vazio, para o caso de edital do tipo geral.
        :return: Retorna uma lista com dois itens do tipo boolean:
                Primeiro item: se as bolsas concedidas para servidores superar o limite máximo definido no "Plano de Oferta por Campus"
                do edital, retorna verdadeiro, caso contrário, falso.
                Setundo item: se as bolsas concedidas para alunos superar o limite máximo definido no "Plano de Oferta por Campus"
                do edital, retorna verdadeiro, caso contrário, falso.
        """
        bolsa_disponivel_campus = None
        qtd_bolsa_pesquisador = 0
        qtd_bolsa_ic = 0
        if self.forma_selecao == Edital.GERAL:
            projetos = Projeto.objects.filter(edital=self, pre_aprovado=True).order_by('-pontuacao_total')
            qtd_bolsa_pesquisador = self.qtd_bolsa_servidores
            qtd_bolsa_ic = self.qtd_bolsa_alunos
        else:
            projetos = Projeto.objects.filter(edital=self, uo_id=id_uo, pre_aprovado=True).order_by('-pontuacao_total')
            bolsa_disponivel_campus = self.get_ofertas_projeto().filter(uo_id=id_uo)[0]
            qtd_bolsa_pesquisador = bolsa_disponivel_campus.num_maximo_pesquisador
            qtd_bolsa_ic = bolsa_disponivel_campus.num_maximo_ic

        superou_cota_pesquisador = len(ids_participacao_de_servidor_bolsa_concedida) > qtd_bolsa_pesquisador
        superou_cota_ic = len(ids_participacao_de_aluno_bolsa_concedidas) > qtd_bolsa_ic

        if superou_cota_pesquisador or superou_cota_ic:
            return (superou_cota_pesquisador, superou_cota_ic)

        try:
            sid = transaction.savepoint()
            participacoes_de_alunos = Participacao.objects.filter(projeto__in=projetos, vinculo_pessoa__tipo_relacionamento__model='aluno')
            participacoes_de_servidores = Participacao.objects.filter(projeto__in=projetos).exclude(
                vinculo_pessoa__tipo_relacionamento__model='aluno'
            )
            Edital._redistribuir_bolsas(projetos, ids_participacao_de_servidor_bolsa_concedida, participacoes_de_servidores)
            Edital._redistribuir_bolsas(projetos, ids_participacao_de_aluno_bolsa_concedidas, participacoes_de_alunos)

            # desaprova todos os projetos que foram previamente aprovados na distribuíção do referido edital.
            projetos.filter(aprovado_na_distribuicao=True).update(aprovado=False, aprovado_na_distribuicao=False)
            for projeto_id in ids_projetos_aprovados:
                projeto = projetos.get(id=projeto_id)
                if not projeto.aprovado:
                    projeto.aprovado_na_distribuicao = True
                projeto.aprovado = True
                projeto.save()
                projeto.atualizar_cotas_bolsa()

            agora = datetime.datetime.now()
            if self.forma_selecao == Edital.GERAL:
                Edital.objects.filter(id=self.id).update(data_avaliacao_classificacao=agora)
            elif id_uo:
                bolsa_disponivel_campus.data_avaliacao_classificacao = agora
                bolsa_disponivel_campus.save()
                # caso todos os "Plano de Oferta por Campus" do referido edital tenham sido feita a distribuição de bolsa,
                # definir a data_avaliacao_classificacao do refereido edital para agora.
                if self.get_ofertas_projeto().filter(data_avaliacao_classificacao__isnull=False).exists():
                    Edital.objects.filter(id=self.id).update(data_avaliacao_classificacao=agora)

            transaction.savepoint_commit(sid)
        except Exception:
            transaction.savepoint_rollback(sid)

        return (superou_cota_pesquisador, superou_cota_ic)

    def tem_fonte_recurso(self):
        return Recurso.objects.filter(edital=self).exists()

    def tem_arquivo(self):
        return EditalArquivo.objects.filter(edital=self).exists()

    def arquivo_mais_recente(self):
        return EditalArquivo.objects.filter(edital=self).order_by('-data_cadastro')[0]

    def pode_atualizar_curriculo_lattes(self):
        return self.is_periodo_selecao_e_pre_divulgacao() and self.peso_avaliacao_lattes_coordenador > 0

    def pode_refazer_distribuicao_bolsas(self):
        return self.is_periodo_selecao_e_pre_divulgacao()

    def tem_pendencia_criterios_de_avaliacao(self):
        return not (not self.peso_avaliacao_projeto or self.peso_avaliacao_projeto and self.criterioavaliacao_set.exists())

    @classmethod
    def disponiveis_para_inscricoes(cls):
        editais = Edital.objects.em_inscricao()
        editais_ids_aptos = list(
            editais.filter(peso_avaliacao_projeto__gt=0, criterioavaliacao__isnull=False).values_list('id', flat=True).distinct()
        )
        editais_ids_aptos.extend(editais.filter(peso_avaliacao_projeto=0).values_list('id', flat=True).distinct())
        return Edital.objects.filter(id__in=editais_ids_aptos)

    def get_pontuacao_maxima_normalizada_edital(self):
        criterios = CriterioAvaliacao.objects.filter(edital=self)
        if criterios.exists():
            return criterios.aggregate(total=Sum('pontuacao_maxima'))['total'] / criterios.count()
        return 0

    def servidor_pode_avaliar_projeto(self, user):
        if user.eh_servidor:
            servidor = user.get_vinculo().relacionamento
            if servidor.titulacao and servidor.titulacao.codigo in self.titulacoes_avaliador.all().values_list('codigo', flat=True):
                return True
        elif AvaliadorExterno.objects.filter(vinculo=user.get_vinculo()).exists():
            avaliador_externo = AvaliadorExterno.objects.get(vinculo=user.get_vinculo())
            if avaliador_externo.titulacao.codigo in self.titulacoes_avaliador.all().values_list('codigo', flat=True):
                return True
        return False

    def get_data_limite_anuencia(self):
        if self.formato == Edital.FORMATO_SIMPLIFICADO or self.tipo_edital == Edital.PESQUISA_INOVACAO_CONTINUO:
            return self.fim_inscricoes
        else:
            return self.inicio_pre_selecao

    def tem_monitoramento_por_atividades(self):
        return self.tipo_monitoramento == Edital.ATIVIDADES

    def pode_submeter_projeto(self, vinculo):
        if vinculo.eh_servidor():
            return CurriculoVittaeLattes.objects.filter(vinculo=vinculo).exists()
        elif vinculo.eh_prestador():
            return self.colaborador_externo_pode_submeter
        elif vinculo.eh_aluno():
            return self.aluno_pos_pode_submeter and vinculo.relacionamento.curso_campus.is_pos_graduacao()
        return False

    def tem_termo_compromisso_colaborador_externo(self):
        return (
            self.termo_compromisso_colaborador_externo
            or self.termo_compromisso_colaborador_externo_en
            or self.termo_compromisso_colaborador_externo_es
            or self.termo_compromisso_colaborador_externo_fr
        )

    def pode_notificar_servidores(self):
        return self in Edital.objects.all().em_inscricao() and BolsaDisponivel.objects.filter(edital=self).exists()

    @transaction.atomic
    def clonar_edital(
        self,
        request,
        titulo,
        descricao,
        clona_anexos_edital,
        clona_anexos_projetos,
        clona_fontes_recursos,
        clona_plano_oferta_campus,
        clona_criterios_coordenador,
        clona_criterios_avaliacao,
    ):
        edital_clonado = Edital.objects.get(id=self.id)
        edital_clonado.id = None
        edital_clonado.titulo = titulo
        edital_clonado.descricao = descricao
        edital_clonado.autorizado_por = None
        edital_clonado.arquivo = None
        edital_clonado.data_avaliacao_classificacao = None
        edital_clonado.cadastrado_por_vinculo = request.user.get_vinculo()
        edital_clonado.cadastrado_em = datetime.datetime.now()
        if request.user.has_group_cached('Coordenador de Pesquisa'):
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

        if clona_fontes_recursos:
            for recurso in Recurso.objects.filter(edital=self):
                recurso.id = None
                recurso.edital = edital_clonado
                recurso.save()

        if clona_plano_oferta_campus:
            for bolsa in BolsaDisponivel.objects.filter(edital=self):
                bolsa.id = None
                bolsa.edital = edital_clonado
                bolsa.save()

        if clona_criterios_coordenador:
            for criterio in ParametroEdital.objects.filter(edital=self):
                criterio.id = None
                criterio.edital = edital_clonado
                criterio.save()

        if clona_criterios_avaliacao:
            for criterio in CriterioAvaliacao.objects.filter(edital=self):
                criterio.id = None
                criterio.edital = edital_clonado
                criterio.save()

        return edital_clonado


class ParametroEdital(models.ModelPlus):
    edital = models.ForeignKeyPlus(Edital, verbose_name='Edital', on_delete=models.CASCADE)
    parametro = models.ForeignKeyPlus('cnpq.Parametro', verbose_name='Critério', on_delete=models.CASCADE)
    valor_parametro = models.DecimalFieldPlus('Valor do Critério', default=0)
    qtd_maxima = models.IntegerFieldPlus('Quantidade Máxima', null=True, blank=True)

    class Meta:
        verbose_name = 'Critério do Edital'
        verbose_name_plural = 'Critérios do Edital'

    def __str__(self):
        return f'{self.edital}'


class CriterioAvaliacao(models.ModelPlus):
    edital = models.ForeignKeyPlus(Edital, on_delete=models.CASCADE)
    descricao = models.TextField('Descrição')
    pontuacao_maxima = models.DecimalFieldPlus('Pontuação Máxima')

    class Meta:
        verbose_name = 'Critério de Avaliação'
        verbose_name_plural = 'Critérios de Avaliação'
        ordering = ['id']

    def __str__(self):
        return self.descricao

    def get_itens_avaliacoes(self):
        return self.itemavaliacao_set.all()

    def pode_ser_removido(self):
        return not self.get_itens_avaliacoes().exists()


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
    despesa = models.ForeignKeyPlus(NaturezaDespesa, verbose_name='Despesa', related_name='pesquisa_recurso_despesa', on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Investimento'
        verbose_name_plural = 'Investimentos'
        ordering = ['despesa__nome']


class BolsaDisponivel(models.ModelPlus):
    edital = models.ForeignKeyPlus(Edital, on_delete=models.CASCADE)
    uo = models.ForeignKeyPlus(UnidadeOrganizacional, verbose_name='Campus', related_name='pesquisa_oferta_campus', on_delete=models.CASCADE)
    num_maximo_ic = models.PositiveIntegerField(
        'Bolsas de Iniciação Científica', help_text='Informe o número máximo de Bolsas de Iniciação Científica.', null=True
    )
    num_maximo_pesquisador = models.PositiveIntegerField(
        'Bolsas para Pesquisador', help_text='Informe o número máximo de Bolsas para Pesquisador.', null=True
    )
    data_avaliacao_classificacao = models.DateTimeFieldPlus('Data de Avaliação da Classificação', null=True, blank=True)


class TipoVinculo:
    BOLSISTA = 'Bolsista'
    VOLUNTARIO = 'Voluntário'
    TIPOS = ((BOLSISTA, 'Bolsista'), (VOLUNTARIO, 'Voluntário'))


class EditalAnexo(models.ModelPlus):
    SERVIDOR_DOCENTE = '1'
    ALUNO = '2'
    COORDENADOR_DOCENTE = '3'
    COORDENADOR_TECNICO_ADMINISTRATIVO = '4'
    SERVIDOR_ADMINISTRATIVO = '5'
    COLABORADOR_EXTERNO = '6'
    TIPO_MEMBRO = (
        (SERVIDOR_DOCENTE, 'Docente'),
        (SERVIDOR_ADMINISTRATIVO, 'Técnico Administrativo'),
        (ALUNO, 'Aluno'),
        (COORDENADOR_DOCENTE, 'Coordenador Docente'),
        (COORDENADOR_TECNICO_ADMINISTRATIVO, 'Coordenador Técnico Administrativo'),
        (COLABORADOR_EXTERNO, 'Colaborador Externo'),
    )
    edital = models.ForeignKeyPlus(Edital, on_delete=models.CASCADE)
    nome = models.CharField('Nome', max_length=255)
    descricao = models.TextField('Descrição', blank=True)
    tipo_membro = models.CharField('Tipo de Membro', max_length=1, choices=TIPO_MEMBRO, null=True, blank=True)
    vinculo = models.CharField('Tipo de Vínculo', max_length=20, choices=TipoVinculo.TIPOS, null=True, blank=True)
    ordem = models.PositiveIntegerField('Ordem', help_text='Informe um número inteiro maior ou igual a 1')

    class Meta:
        ordering = ['ordem']

    def __str__(self):
        return self.nome


class ProgramaPosGraduacao(models.ModelPlus):
    SEARCH_FIELDS = ['nome', 'codigo_capes']
    ACADEMICO = 'academico'
    PROFISSIONAL = 'profissional'
    MODALIDADE_CHOICES = [
        (ACADEMICO, 'Acadêmico'),
        (PROFISSIONAL, 'Profissional'),
    ]

    LATO_SENSU = 'lato_sensu'
    STRICTO_SENSU = 'stricto_sensu'
    NIVEL_CHOICES = [
        (LATO_SENSU, 'Lato Sensu'),
        (STRICTO_SENSU, 'Stricto Sensu'),
    ]

    nome = models.CharField('Nome do Programa', max_length=1000)
    ativo = models.BooleanField('Ativo', default=True)
    codigo_capes = models.CharField('Código CAPES', max_length=10, unique=True, null=True, blank=True)
    coordenador = models.ForeignKeyPlus(
        Servidor, verbose_name='Coordenador', null=True, blank=False, related_name='programaposgraduacao_avaliador', on_delete=models.CASCADE
    )
    modalidade = models.CharField('Modalidade de Programa', max_length=50, null=True, blank=True, choices=MODALIDADE_CHOICES)
    area_capes = models.ForeignKeyPlus(AreaCapes, verbose_name='Área CAPES', null=True, blank=False, on_delete=models.CASCADE)
    campus_sede = models.ForeignKeyPlus(
        UnidadeOrganizacional,
        verbose_name='Campus Sede',
        null=True,
        blank=True,
        related_name='programaposgraduacao_campus_sede',
        on_delete=models.CASCADE,
    )
    campi_oferta = models.ManyToManyFieldPlus(
        UnidadeOrganizacional, verbose_name='Campi de Oferta', related_name='programaposgraduacao_campi_oferta', blank=True
    )
    nivel = models.CharField('Nível', max_length=50, null=True, blank=False, choices=NIVEL_CHOICES)

    class Meta:
        verbose_name = 'Programa de Pós-Graduação'
        verbose_name_plural = 'Programas de Pós-Graduação'
        ordering = ['nome']

    def get_absolute_url(self):
        return f'/pesquisa/programapos/{self.pk:d}/'

    def __str__(self):
        return str(self.nome)


class AreaConcentracaoProgramaPos(models.ModelPlus):
    programa = models.ForeignKeyPlus(ProgramaPosGraduacao, verbose_name='Programa de Pós-Graduação', on_delete=models.CASCADE)
    area_concentracao = models.ForeignKeyPlus(AreaConcentracao, verbose_name='Área de Concentração', on_delete=models.CASCADE)
    data_inicio = models.DateFieldPlus('Data início')
    data_fim = models.DateFieldPlus('Data fim', null=True, blank=True)

    class Meta:
        verbose_name = 'Área de Concentração do Programa de Pós-Graduação'
        verbose_name_plural = 'Áreas de Concentração do Programa de Pós-Graduação'
        ordering = ['data_inicio']

    def __str__(self):
        return str(self.area_concentracao.descricao)


class DocenteProgramaPos(models.ModelPlus):
    TIPOVINCULO_CHOICES = [
        ('permanente', 'Permanente'),
        ('colaborador', 'Colaborador'),
    ]

    programa = models.ForeignKeyPlus(ProgramaPosGraduacao, verbose_name='Programa de Pós-Graduação', on_delete=models.CASCADE)
    docente = models.ForeignKeyPlus(Professor, verbose_name='Docente', on_delete=models.CASCADE)
    tipo_vinculo = models.CharField('Tipo de Vínculo', max_length=50, choices=TIPOVINCULO_CHOICES)
    data_inicio = models.DateFieldPlus('Data início')
    data_fim = models.DateFieldPlus('Data fim', null=True, blank=True)

    class Meta:
        verbose_name = 'Docente de Programa de Pós-Graduação'
        verbose_name_plural = 'Docentes de Programas de Pós-Graduação'
        ordering = ['data_inicio']

    def __str__(self):
        return f'{self.docente.get_nome()}-{self.programa.nome}'


class SecretarioProgramaPos(models.ModelPlus):
    programa = models.ForeignKeyPlus(ProgramaPosGraduacao, verbose_name='Programa de Pós-Graduação', on_delete=models.CASCADE)
    secretario = models.ForeignKeyPlus(Servidor, verbose_name='Secretario', on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Secretário do Programa de Pós-Graduação'
        verbose_name_plural = 'Secretários de Programa de Pós-Graduação'

    def __str__(self):
        return f'{self.secretario.nome}-{self.programa.nome}'


class CursoProgramaPos(models.ModelPlus):
    programa = models.ForeignKeyPlus(ProgramaPosGraduacao, verbose_name='Programa de Pós-Graduação', on_delete=models.CASCADE)
    curso = models.ForeignKeyPlus(CursoCampus, verbose_name='Curso', on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Curso do Programa de Pós-Graduação'
        verbose_name_plural = 'Cursos do Programa de Pós-Graduação'

    def __str__(self):
        return f'{self.curso.descricao}'


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
    PERIODO_ENCERRADO = 'Encerrado'

    STATUS_CONCLUIDO = 'Concluído'
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
    STATUS_INATIVADO = 'Inativado'

    STATUS_SIM = 'Sim'
    STATUS_NAO = 'Não'
    STATUS_EM_ESPERA = 'Em Espera'
    STATUS_AGUARDANDO_PRE_SELECAO = 'Aguardando pré-seleção'
    STATUS_AGUARDANDO_AVALIACAO = 'Aguardando avaliação'
    STATUS_PRE_SELECIONADO_EM = 'Pré-selecionado em'
    STATUS_SELECIONADO_EM = 'Selecionado em'
    STATUS_NAO_SELECIONADO_EM = 'Não selecionado em'
    STATUS_AGUARDADO_ENVIO_PROJETO = 'Aguardando o envio do projeto'
    TRL_2 = 'TRL 2'
    TRL_CHOICES = (
        ('TRL 1', 'TRL 1: princípios básicos (pesquisa básica)'),
        (TRL_2, 'TRL 2: conceito e/ou aplicação da tecnologia (pesquisa aplicada)'),
        ('TRL 3', 'TRL 3: prova de conceito (desenvolvimento experimental)'),
        ('TRL 4', 'TRL 4: validação laboratorial (desenvolvimento experimental).'),
        ('TRL 5', 'TRL 5: validação em ambiente relevante (desenvolvimento experimental)'),
        ('TRL 6', 'TRL 6: demonstração em ambientes relevantes (desenvolvimento experimental)'),
        ('TRL 7', 'TRL 7: demonstração em ambiente operacional (industrialização)'),
        ('TRL 8', 'TRL 8: sistema real desenvolvido e aprovado (industrialização)'),
        ('TRL 9', 'TRL 9: sistema operando e comprovado em todos os aspectos de sua missão operacional (produção e comercialização).'),
    )

    edital = models.ForeignKeyPlus(Edital, verbose_name='Edital')
    uo = models.ForeignKeyPlus(UnidadeOrganizacional, verbose_name='Campus', related_name='pesquisa_projeto_campus')
    titulo = models.CharField('Título do projeto', max_length=255)

    area_conhecimento = models.ForeignKeyPlus('rh.AreaConhecimento', verbose_name='Área do Conhecimento', null=True, blank=True)

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
        related_name='pesquisa_vinculo_coordenador_set',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    palavras_chaves = models.CharFieldPlus('Palavras-Chaves', null=True, help_text='Separe as palavras-chaves utilizando ponto e vírgula (;).')

    # avaliacao
    pre_aprovado = models.BooleanField('Pré-selecionado', default=False)
    data_pre_avaliacao = models.DateField('Data da Pré-seleção', null=True, blank=True)
    vinculo_autor_pre_avaliacao = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Responsável pela Pré-seleção', null=True, blank=True, related_name='pesquisa_vinculo_pre_avaliador'
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

    grupo_pesquisa = models.ForeignKeyPlus('cnpq.GrupoPesquisa', verbose_name='Grupo de Pesquisa', null=True)
    fundamentacao_teorica = HTMLField(blank=True, null=True)
    referencias_bibliograficas = HTMLField(blank=True, null=True)
    introducao = HTMLField(blank=True, null=True)
    pontuacao_curriculo = models.DecimalFieldPlus('Pontuação do Currículo do Coordenador', default=Decimal('0'), null=True, blank=True)
    pontuacao_curriculo_normalizado = models.DecimalFieldPlus(
        'Pontuação do currículo do coordenador normalizado', default=Decimal('0'), null=True, blank=True
    )
    pontuacao_grupo_pesquisa = models.DecimalFieldPlus('Pontuação do Grupo de Pesquisa', default=Decimal('0'), null=True, blank=True)
    pontuacao_grupo_pesquisa_normalizado = models.DecimalFieldPlus(
        'Pontuação do Grupo de Pesquisa normalizado', default=Decimal('0'), null=True, blank=True
    )
    pontuacao_total = models.DecimalFieldPlus('Pontuação Total do Projeto', default=Decimal('0'), null=True, blank=True)
    cota_bolsa_aluno = models.PositiveIntegerField('Cota Bolsa para Alunos', default=0, null=True)
    cota_bolsa_pesquisador = models.PositiveIntegerField('Cota Bolsa para Pesquisador', default=0, null=True)
    obs_reprovacao = models.TextField(blank=True, null=True)
    vinculo_supervisor = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Responsável pelo Monitoramento', null=True, blank=True, related_name='pesquisa_vinculo_monitor'
    )
    nome_edital_origem = models.CharFieldPlus('Nome do Edital de Origem', blank=True, null=True, max_length=500)
    valor_global_projeto = models.DecimalFieldPlus(
        'Valor Global do Projeto', default=Decimal('0.0'), help_text='Caso não tenha fomento, informe o valor 0,00.'
    )
    responsavel_anuencia = models.ForeignKeyPlus(
        Servidor, verbose_name='Responsável pela Anuência', null=True, blank=True, related_name='pesquisa_responsavel_anuencia'
    )
    anuencia = models.BooleanField('Chefia de Acordo', null=True)
    anuencia_registrada_em = models.DateTimeFieldPlus('Anuência Registrada em', null=True, blank=True)
    inativado = models.BooleanField('Inativado', default=False)
    motivo_inativacao = models.CharFieldPlus('Motivo da Inativação do Projeto', max_length=5000, null=True, blank=True)
    inativado_em = models.DateTimeFieldPlus('Inativado em', null=True, blank=True)
    inativado_por = models.ForeignKeyPlus(
        Servidor, verbose_name='Inativado por', related_name='pesquisa_projeto_inativado_por', null=True, blank=True, on_delete=models.CASCADE
    )
    ppg = models.ForeignKeyPlus(ProgramaPosGraduacao, verbose_name='Programa de Pós-Graduação Vinculado', null=True)
    parceria_externa = models.CharFieldPlus('Programa/Instituição de Parceria Externa', null=True, max_length=1000)
    auxiliar = models.ForeignKey(
        'comum.Vinculo',
        verbose_name='Membro Auxiliar do Projeto',
        related_name='pesquisa_membroauxiliar_projeto',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    tem_interesse_cartao_pesquisador = models.BooleanField(
        'Tem interesse no fomento para custeio através do cartão BB pesquisador',
        default=False,
    )
    classificacao_trl = models.CharFieldPlus('Classificação TRL', null=True, blank=True, max_length=10, choices=TRL_CHOICES)
    orientador = models.ForeignKey(
        'comum.Vinculo',
        verbose_name='Orientador do Projeto',
        related_name='pesquisa_orientador_projeto',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    coorientador = models.ForeignKey(
        'comum.Vinculo',
        verbose_name='Coorientador do Projeto',
        related_name='pesquisa_coorientador_projeto',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    autorizada_sem_fomento = models.BooleanField('Execução sem fomento autorizada', default=False)
    autorizada_sem_fomento_por = models.ForeignKey(
        'comum.Vinculo',
        verbose_name='Execução sem fomento autorizada por',
        related_name='pesquisa_autorizadasemfomento_por',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    autorizada_sem_fomento_em = models.DateTimeFieldPlus('Execução sem fomento autorizada em', null=True, blank=True)
    aceita_sem_fomento = models.BooleanField('Execução sem fomento aceita', null=True)
    avaliacao_aceite_sem_fomento_por = models.ForeignKey(
        'comum.Vinculo',
        verbose_name='Execução sem fomento avaliada por',
        related_name='pesquisa_avaliadasemfomento_por',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    avaliacao_aceite_sem_fomento_em = models.DateTimeFieldPlus('Execução sem fomento avaliada em', null=True, blank=True)

    aprovado_posteriormente = models.BooleanField('Aprovado posteriormente', default=False)
    aprovado_posteriormente_por = models.ForeignKey(
        'comum.Vinculo',
        verbose_name='Aprovado posteriormente por',
        related_name='pesquisa_aprovadoposteriormente_por',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    aprovado_posteriormente_em = models.DateTimeFieldPlus('Aprovado posteriormente em', null=True, blank=True)
    precisa_cep = models.BooleanField('Necessita de Autorização do CEP', default=False)
    num_protocolo_cep = models.CharFieldPlus('Número do Protocolo no CEP', max_length=200, null=True, blank=True)
    precisa_ceua = models.BooleanField('Necessita de Autorização do CEUA', default=False)
    num_protocolo_ceua = models.CharFieldPlus('Número do Protocolo no CEUA', max_length=200, null=True, blank=True)
    precisa_sisgen = models.BooleanField('Necessita de Autorização do SISGEN', default=False)
    num_protocolo_sisgen = models.CharFieldPlus('Número do Protocolo no SISGEN', max_length=200, null=True, blank=True)
    atividades_sisgen = models.ManyToManyFieldPlus(
        'pesquisa.AtividadeAutorizacaoSISGEN',
        related_name='pesquisa_atividades_sisgen',
        blank=True,
        verbose_name='Atividades para Autorização no SISGEN',
        help_text='Para mais informações, acesse o SISGEN e consulte a Lei 13.123/2015',
    )
    precisa_sisbio = models.BooleanField('Necessita de Autorização do SISBIO', default=False)
    num_protocolo_sisbio = models.CharFieldPlus('Número do Protocolo no SISBIO', max_length=200, null=True, blank=True)
    atividades_sisbio = models.ManyToManyFieldPlus(
        'pesquisa.AtividadeAutorizacaoSISBIO',
        related_name='pesquisa_atividades_sisbio',
        blank=True,
        verbose_name='Atividades para Autorização no SISBIO',
        help_text='Para mais informações, acesse a portaria ICMBIO Nº 748, de 19 de setembro de 2022',
    )
    objetivos_desenvolvimento_sustentavel = models.ManyToManyFieldPlus(
        ObjetivoDesenvolvimentoSustentavel,
        related_name='pesquisa_objetivos_onu',
        blank=True,
        verbose_name='Objetivos atendidos para o desenvolvimento sustentável (ODS) da ONU',
        help_text='Detalhes de cada objetivo podem ser encontrados no site: https://brasil.un.org/pt-br/sdgs',
    )
    subobjetivos_desenvolvimento_sustentavel = models.ManyToManyFieldPlus(
        SubobjetivoDesenvolvimentoSustentavel,
        related_name='pesquisa_subobjetivos_onu',
        blank=True,
        verbose_name='Subobjetivos atendidos para o desenvolvimento sustentável (ODS) da ONU',
        help_text='Detalhes de cada subobjetivo podem ser encontrados no site: https://brasil.un.org/pt-br/sdgs',
    )
    vinculado_laboratorio_multiusuario = models.BooleanField('Vinculado a um Laboratório Multiusuário', default=False)
    laboratorio_multiusuario = models.ForeignKeyPlus(
        'pesquisa.LaboratorioPesquisa', verbose_name='Laboratório Multiusuário', null=True, blank=True, on_delete=models.SET_NULL
    )

    class Meta:
        verbose_name = 'Projeto'
        verbose_name_plural = 'Projetos'

        permissions = (
            ('pode_gerenciar_edital', 'Pode gerenciar edital'),
            ('pode_avaliar_projeto', 'Pode avaliar projeto'),
            ('pode_pre_avaliar_projeto', 'Pode pre avaliar projeto'),
            ('pode_visualizar_projeto', 'Pode visualizar projeto'),
            ('pode_visualizar_projetos_em_monitoramento', 'Pode visualizar projetos em monitoramento'),
            ('pode_gerenciar_equipe_projeto', 'Pode gerenciar equipe projeto'),
            ('pode_avaliar_cancelamento_projeto', 'Pode avaliar cancelamento projeto'),
            ('pode_realizar_monitoramento_projeto', 'Pode realizar monitoramento projeto'),
            ('pode_ver_equipe_projeto', 'Pode ver equipe do projeto'),
            ('pode_interagir_com_projeto', 'Pode interagir com projeto'),
            ('tem_acesso_sistemico', 'Tem acesso sistêmico'),
            ('pode_acessar_lista_projetos', 'Pode acessar listagem de projetos'),
            ('pode_se_tornar_avaliador', 'Pode se tornar avaliador de projetos'),
        )

    def __str__(self):
        return f'Projeto de {self.edital.get_tipo_edital_display()} "{self.titulo}"'

    @transaction.atomic
    def clonar_projeto(self, edital, clona_equipe, clona_atividade, clona_memoria_calculo, clona_desembolso, data_inicio, data_fim):
        projeto_clonado = Projeto.objects.get(id=self.id)
        projeto_clonado.edital = edital
        projeto_clonado.id = None
        projeto_clonado.pre_aprovado = False
        projeto_clonado.data_pre_avaliacao = None
        projeto_clonado.vinculo_autor_pre_avaliacao = None
        projeto_clonado.aprovado = False

        projeto_clonado.data_avaliacao = None
        projeto_clonado.aprovado_na_distribuicao = False

        projeto_clonado.pontuacao = 0
        projeto_clonado.data_conclusao_planejamento = None
        projeto_clonado.data_finalizacao_conclusao = None
        projeto_clonado.data_validacao_pontuacao = None
        projeto_clonado.pontuacao_curriculo = 0
        projeto_clonado.pontuacao_curriculo_normalizado = 0
        projeto_clonado.pontuacao_grupo_pesquisa = 0
        projeto_clonado.pontuacao_grupo_pesquisa_normalizado = 0
        projeto_clonado.pontuacao_total = 0

        projeto_clonado.cota_bolsa_aluno = None
        projeto_clonado.cota_bolsa_pesquisador = None

        projeto_clonado.obs_reprovacao = None
        projeto_clonado.vinculo_supervisor = None
        projeto_clonado.nome_edital_origem = None
        projeto_clonado.valor_global_projeto = 0.0

        projeto_clonado.responsavel_anuencia = None
        projeto_clonado.anuencia = None
        projeto_clonado.anuencia_registrada_em = None
        projeto_clonado.inativado = False
        projeto_clonado.motivo_inativacao = None
        projeto_clonado.inativado_em = None
        projeto_clonado.inativado_por = None
        projeto_clonado.auxiliar = None

        projeto_clonado.inicio_execucao = data_inicio
        projeto_clonado.fim_execucao = data_fim

        p = Participacao.objects.get(projeto=self, responsavel=True)

        projeto_clonado.bolsa_coordenador = p.bolsa_concedida
        projeto_clonado.save()

        part_do_coordenador = Participacao.objects.get(projeto=projeto_clonado, responsavel=True)
        part_do_coordenador.vinculo = p.vinculo
        part_do_coordenador.bolsa_concedida = p.bolsa_concedida
        part_do_coordenador.save()

        if clona_equipe:
            for membro in Participacao.objects.filter(projeto=self, responsavel=False, ativo=True).exclude(vinculo_pessoa=None):
                vinculo = membro.vinculo
                if (membro.vinculo_pessoa.eh_aluno() and edital.qtd_maxima_alunos_bolsistas == 0) or (
                    membro.vinculo_pessoa.eh_servidor() and edital.qtd_maxima_alunos_bolsistas == 0
                ):
                    vinculo = TipoVinculo.VOLUNTARIO

                membro_clonado = Participacao(
                    projeto=projeto_clonado,
                    vinculo_pessoa=membro.vinculo_pessoa,
                    vinculo=vinculo,
                    carga_horaria=membro.carga_horaria,
                    bolsa_concedida=membro.bolsa_concedida,
                    termo_aceito_em=None,
                )
                membro_clonado.save()
                Participacao.gerar_anexos_do_participante(membro_clonado)
                if membro.vinculo_pessoa.eh_aluno():
                    membro_clonado.adicionar_registro_historico_equipe(HistoricoEquipe.EVENTO_ADICIONAR_ALUNO, data_evento=data_inicio)
                else:
                    membro_clonado.adicionar_registro_historico_equipe(HistoricoEquipe.EVENTO_ADICIONAR_SERVIDOR, data_evento=data_inicio)

        if clona_atividade:
            for meta in Meta.objects.filter(projeto=self):
                meta_clonada = Meta(projeto=projeto_clonado, ordem=meta.ordem, descricao=meta.descricao)
                meta_clonada.save()
                for etapa in Etapa.objects.filter(meta=meta):
                    etapa_clonada = Etapa(
                        meta=meta_clonada,
                        ordem=etapa.ordem,
                        descricao=etapa.descricao,
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

    def get_pontuacao(self):
        if self.edital.tipo_edital == Edital.PESQUISA_INOVACAO_CONTINUO:
            return '<span class="status status-info">Não se aplica</span>'
        else:
            if self.selecao_ja_divulgada():
                return self.pontuacao_total
            else:
                return '<span class="status status-alert">Aguardando divulgação</span>'

    def get_pre_selecionado(self, html=True, user=None):
        if self.edital.tem_formato_completo():
            if not user:
                user = tl.get_user()
            agora = datetime.datetime.now()

            if self.edital.inicio_pre_selecao and agora > self.edital.inicio_pre_selecao:
                if user.groups.filter(name__in=['Coordenador de Pesquisa', 'Pré-Avaliador Sistêmico de Projetos de Pesquisa']):
                    if self.data_conclusao_planejamento or (not self.data_conclusao_planejamento and self.data_pre_avaliacao):
                        if self.data_pre_avaliacao and self.pre_aprovado:
                            if html:
                                return f'<span class="status status-success">{Projeto.STATUS_PRE_SELECIONADO_EM} {format_(self.data_pre_avaliacao)} </span>'
                            return f'{Projeto.STATUS_PRE_SELECIONADO_EM} {format_(self.data_pre_avaliacao)}'

                        elif self.data_pre_avaliacao and not self.pre_aprovado:
                            if html:
                                return f'<span class="status status-error">{Projeto.STATUS_NAO_SELECIONADO_EM} {format_(self.data_pre_avaliacao)} </span>'
                            return f'{Projeto.STATUS_NAO_SELECIONADO_EM} {format_(self.data_pre_avaliacao)}'
                        elif self.edital.inicio_selecao and agora >= self.edital.inicio_selecao:
                            if html:
                                return '<span class="status status-info">Não foi pré-avaliado.</span>'
                            return 'Não foi pré-avaliado'
                        else:
                            if html:
                                return '<p class="alert alert-warning">Aguardando pré-avaliação.</p>'
                            return 'Aguardando pré-avaliação'
                    elif self.edital.is_periodo_inscricao():
                        if html:
                            return '<p class="alert alert-warning">Aguardando finalização da inscrição.</p>'
                        return 'Aguardando finalização da inscrição'
                    else:
                        if html:
                            return '<span class="status status-error">Projeto não enviado</span>'
                        return 'Projeto não enviado'

                if self.data_pre_avaliacao and self.pre_aprovado:
                    if html:
                        return f'<span class="status status-success">{Projeto.STATUS_SIM}</span>'
                    return f'{Projeto.STATUS_SIM}'
                elif self.edital.eh_edital_continuo():
                    if html:
                        return '<span class="status status-alert">Aguardando pré-avaliação</span>'
                    return 'Aguardando pré-avaliação'
                else:
                    if html:
                        return f'<span class="status status-rejeitado">{Projeto.STATUS_NAO}</span>'
                    return f'{Projeto.STATUS_NAO}'
            else:
                if user.groups.filter(name='Diretor de Pesquisa'):
                    if html:
                        return f'<span class="status status-alert">{Projeto.STATUS_EM_ESPERA}</span>'
                    return f'{Projeto.STATUS_EM_ESPERA}'
                else:
                    if html:
                        return f'<span class="status status-alert">{Projeto.STATUS_AGUARDANDO_PRE_SELECAO}</span>'
                    return f'{Projeto.STATUS_AGUARDANDO_PRE_SELECAO}'

        else:
            return '<span class="status status-alert">Não se aplica.</span>'

    def get_periodo(self, registro_conclusao=None):
        periodo = None
        eh_periodo_inscricao = self.edital.is_periodo_inscricao()
        registro_conclusao_projeto = registro_conclusao or self.get_registro_conclusao()
        if self.edital.tem_formato_completo():
            if self.edital.tipo_edital == Edital.PESQUISA_INOVACAO_CONTINUO:
                if self.edital.is_periodo_inscricao() and not self.data_conclusao_planejamento:
                    periodo = self.PERIODO_INSCRICAO
                elif self.data_conclusao_planejamento and not self.data_avaliacao:
                    periodo = self.PERIODO_PRE_SELECAO
                elif self.aprovado and self.edital.is_periodo_divulgacao():
                    periodo = self.PERIODO_EXECUCAO
            else:
                if (
                    registro_conclusao_projeto
                    and registro_conclusao_projeto.dt_avaliacao
                    or (not self.pre_aprovado and self.edital.inicio_selecao and self.edital.inicio_selecao < datetime.datetime.now())
                    or (not self.aprovado and self.edital.divulgacao_selecao and self.edital.divulgacao_selecao < datetime.datetime.now())
                ):
                    # se status igual STATUS_CONCLUIDO ou  STATUS_NAO_ACEITO. Não usar self.get_status() pois irá ocorrer o erro maximum recursion depth exceeded
                    periodo = self.PERIODO_ENCERRADO
                elif self.edital.is_periodo_inscricao():
                    periodo = self.PERIODO_INSCRICAO
                elif self.edital.is_periodo_fim_inscricao():
                    periodo = self.PERIODO_FIM_INSCRICAO
                elif self.edital.is_periodo_pre_selecao():
                    periodo = self.PERIODO_PRE_SELECAO
                elif self.edital.is_periodo_selecao():
                    periodo = self.PERIODO_SELECAO
                elif self.edital.is_periodo_divulgacao():
                    periodo = self.PERIODO_EXECUCAO
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
        if self.foi_cancelado():
            return self.STATUS_CANCELADO
        agora = datetime.datetime.now()
        registro_conclusao_projeto = registro_conclusao or self.get_registro_conclusao()
        periodo_edital = periodo or self.get_periodo()
        if self.edital.tipo_edital == Edital.PESQUISA_INOVACAO_CONTINUO:
            if registro_conclusao_projeto and registro_conclusao_projeto.dt_avaliacao:
                return self.STATUS_CONCLUIDO
            if self.inativado:
                return self.STATUS_INATIVADO
            if self.aprovado and periodo_edital == self.PERIODO_EXECUCAO:
                return self.STATUS_EM_EXECUCAO
            if (not self.data_conclusao_planejamento and self.data_pre_avaliacao and periodo_edital != self.PERIODO_INSCRICAO) or (
                not self.aprovado and self.data_avaliacao and self.data_pre_avaliacao
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
            if (
                not self.pre_aprovado
                and self.data_pre_avaliacao
                and ((self.edital.inicio_selecao and self.edital.inicio_selecao < agora) or not self.edital.inicio_selecao)
            ):
                return self.STATUS_NAO_ACEITO
            if (
                not self.aprovado
                and self.data_avaliacao
                and ((self.edital.divulgacao_selecao and self.edital.divulgacao_selecao < agora) or not self.edital.divulgacao_selecao)
            ):
                return self.STATUS_NAO_SELECIONADO
            if self.aprovado and ((self.edital.divulgacao_selecao and self.edital.divulgacao_selecao < agora) or not self.edital.divulgacao_selecao):
                return self.STATUS_SELECIONADO
            if self.pre_aprovado and (periodo_edital == self.PERIODO_PRE_SELECAO or periodo_edital == self.PERIODO_SELECAO):
                return self.STATUS_PRE_SELECIONADO
            if self.data_conclusao_planejamento or (not self.data_conclusao_planejamento and self.data_pre_avaliacao):
                return self.STATUS_INSCRITO
            if self.edital.is_periodo_inscricao():
                return self.STATUS_EM_INSCRICAO
            return self.STATUS_NAO_ENVIADO

    def get_selecionado(self, participacao=None, html=True, user=None):
        if self.edital.tem_formato_completo():
            if not user:
                user = tl.get_user()
            if not participacao:
                if self.edital.tipo_edital == Edital.PESQUISA_INOVACAO_CONTINUO:
                    if not self.data_pre_avaliacao:
                        if html:
                            return f'<span class="status status-alert">{Projeto.STATUS_EM_ESPERA}</span>'
                        return f'{Projeto.STATUS_EM_ESPERA}'
                    elif self.aprovado:
                        if html:
                            return f'<span class="status status-success">{Projeto.STATUS_SIM}</span>'
                        return f'{Projeto.STATUS_SIM}'
                    else:
                        if html:
                            return f'<span class="status status-rejeitado">{Projeto.STATUS_NAO}</span>'
                        return f'{Projeto.STATUS_NAO}'
                else:
                    if self.divulgacao_avaliacao_liberada():
                        if self.aprovado:
                            if html:
                                return f'<span class="status status-success">{Projeto.STATUS_SIM}</span>'
                            return f'{Projeto.STATUS_SIM}'
                        else:
                            if html:
                                return f'<span class="status status-rejeitado">{Projeto.STATUS_NAO}</span>'
                            return f'{Projeto.STATUS_NAO}'
                    else:
                        if user.groups.filter(name='Diretor de Pesquisa'):
                            if html:
                                return f'<span class="status status-alert">{Projeto.STATUS_EM_ESPERA}</span>'
                            return f'{Projeto.STATUS_EM_ESPERA}'
                        else:
                            if html:
                                return f'<span class="status status-alert">{Projeto.STATUS_AGUARDANDO_AVALIACAO}</span>'
                            return f'{Projeto.STATUS_AGUARDANDO_AVALIACAO}'
        else:
            return '<span class="status status-alert">Não se aplica.</span>'

    def divulgacao_avaliacao_liberada(self):
        if self.edital.tem_formato_completo():
            return self.edital.divulgacao_selecao and self.edital.divulgacao_selecao <= datetime.datetime.now()
        return True

    def get_visualizar_projeto_url(self):
        return f'{settings.SITE_URL}{self.get_absolute_url()}'

    def get_plano_aplicacao_como_dict(self):
        recursos = []
        total_geral = Decimal(0)
        total_propi = Decimal(0)
        total_digae = Decimal(0)
        total_campus = Decimal(0)
        for despesa in self.edital.get_elementos_despesa():
            despesa.digae = Decimal(sum(Recurso.objects.filter(despesa=despesa, edital=self.edital, origem='DIGAE').values_list('valor', flat=True)))
            total_digae += despesa.digae
            despesa.campus = Decimal(
                sum(Recurso.objects.filter(despesa=despesa, edital=self.edital, origem='CAMPUS').values_list('valor', flat=True))
            )
            total_campus += despesa.campus

            despesa.propi = Decimal(sum(Recurso.objects.filter(despesa=despesa, edital=self.edital, origem='PROPI').values_list('valor', flat=True)))
            total_propi += despesa.propi

            despesa.total = despesa.propi + despesa.digae + despesa.campus
            total_geral += despesa.total
            recursos.append(despesa)

        return {
            'recursos': recursos,
            'total_geral': total_geral,
            'total_digae': total_digae,
            'total_campus': total_campus,
            'total_propi': total_propi,
        }

    def get_cronograma_desembolso_como_lista(self):
        cronograma = []
        for despesa in self.edital.get_elementos_despesa():
            for i in range(1, 13):
                total = Decimal(0)
                for desembolso in Desembolso.objects.filter(projeto=self, despesa=despesa, mes=i):
                    total += desembolso.valor
                setattr(despesa, f'mes_{i:d}', total)
            cronograma.append(despesa)
        return cronograma

    def is_gerente_sistemico(self, user=None):
        if not user:
            user = tl.get_user()

        return user.groups.filter(name='Diretor de Pesquisa')

    def is_pode_ver_nome_avaliador(self, user=None):
        if not user:
            user = tl.get_user()

            return user.groups.filter(name__in=['Diretor de Pesquisa', 'Coordenador de Pesquisa', 'Pré-Avaliador Sistêmico de Projetos de Pesquisa'])

    def is_coordenador(self, user=None):
        if not user:
            user = tl.get_user()
        if self.is_gerente_sistemico():
            return True
        responsavel = self.vinculo_coordenador
        return bool(responsavel and user.get_vinculo() == responsavel)

    def is_gerenciador_projeto(self, user=None):
        if not user:
            user = tl.get_user()
        if self.is_gerente_sistemico():
            return True
        responsavel = self.vinculo_coordenador
        return bool(responsavel and user.get_vinculo() == responsavel or self.auxiliar and user.get_vinculo() == self.auxiliar)

    def is_avaliador(self, user=None):
        if not user:
            user = tl.get_user()
        return AvaliadorIndicado.objects.filter(rejeitado=False, projeto=self, vinculo=user.get_vinculo()).exists()

    def is_pre_avaliador(self, user: User | None = None) -> bool:
        if not user:
            user = tl.get_user()
        return user.groups.filter(name__in=GRUPOS_PRE_AVALIADORES_INSTITUCIONAIS).exists() or self.is_coordenador_pesquisa_campus_projeto(user)

    def pode_pre_selecionar(self, user: User | None = None) -> bool:
        """Pré-avaliador ou Assessor de Pesquisa: pré-seleciona e imprime o projeto (#17570).

        O Assessor não ganha o resto de `is_pre_avaliador` (devolução, documentos de membro, parecer).
        """
        if not user:
            user = tl.get_user()
        return user.groups.filter(name='Assessor de Pesquisa').exists() or self.is_pre_avaliador(user)

    def eh_supervisor(self, user=None):
        if not user:
            user = tl.get_user()
        return self.vinculo_supervisor == user.get_vinculo()

    def is_responsavel(self, user=None):
        if not user:
            user = tl.get_user()
        return Participacao.objects.filter(projeto=self, vinculo_pessoa=user.get_vinculo(), responsavel=True).exists()

    def is_coordenador_pesquisa_campus_projeto(self, user=None):
        if not user:
            user = tl.get_user()
        return user.groups.filter(name='Coordenador de Pesquisa').exists() and (get_uo(user) == self.uo)

    def get_metas(self):
        return self.meta_set.all().order_by('ordem')

    def pode_editar_gasto(self) -> bool:
        # Só a equipe lança gasto; o Coordenador de Pesquisa do campus só visualiza (#17577).
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
        return bool(self.is_responsavel(user) and status == Projeto.STATUS_EM_EXECUCAO or self.is_gerente_sistemico())

    def pode_exibir_botao_finalizar_relatorios(self):
        user = tl.get_user()
        return bool(
            (self.is_responsavel(user) or self.is_gerente_sistemico())
            and self.aprovado
            and not self.edital.tem_monitoramento_por_atividades()
            and not self.data_finalizacao_conclusao
            and self.relatorioprojeto_set.filter(tipo=RelatorioProjeto.FINAL, aprovado=True).exists()
        )

    def pode_finalizar_conclusao(self):
        user = tl.get_user()
        if (
            (self.is_responsavel(user) or self.is_gerente_sistemico())
            and self.aprovado
            and not self.edital.tem_monitoramento_por_atividades()
            and not self.data_finalizacao_conclusao
            and self.relatorioprojeto_set.filter(tipo=RelatorioProjeto.FINAL, aprovado=True).exists()
        ):
            return True
        if self.edital.tem_monitoramento_por_atividades():
            registro_conclusao = self.get_registro_conclusao()
            if self.edital.tem_formato_completo():
                if (
                    self.data_finalizacao_conclusao
                    or not registro_conclusao
                    or self.tem_registro_execucao_etapa_pendente()
                    or self.tem_registro_gasto_pendente()
                    or self.tem_registro_anexos_pendente()
                    or self.tem_registro_foto_pendente()
                    or not (self.is_responsavel(user) or self.is_gerente_sistemico())
                ):
                    return False
                return bool(registro_conclusao and not registro_conclusao.dt_avaliacao)
            else:
                return bool(
                    registro_conclusao
                    and not self.tem_registro_anexos_pendente()
                    and not self.data_finalizacao_conclusao
                    and user.get_vinculo() == self.vinculo_supervisor
                )
        return False

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
            if self.edital.tem_monitoramento_por_atividades():
                # Depois de relacionar o modelo RegistroGasto com o modelo Desembolso, usar este como planejado e não RegistroGasto
                self.total_planejado = (
                    Etapa.objects.filter(meta__projeto__id=self.pk).count() + RegistroGasto.objects.filter(item__projeto__id=self.pk).count()
                )
            else:
                self.total_planejado = RelatorioProjeto.objects.filter(projeto__id=self.pk).count()
            if self.get_registro_conclusao():
                self.total_planejado += 1
        return self.total_planejado

    total_avaliado = None

    def get_total_avaliado(self):
        if not self.total_avaliado:
            if self.edital.tem_monitoramento_por_atividades():
                self.total_avaliado = (
                    RegistroExecucaoEtapa.objects.filter(etapa__meta__projeto__id=self.pk, dt_avaliacao__isnull=False).count()
                    + RegistroGasto.objects.filter(item__projeto__id=self.pk, dt_avaliacao__isnull=False).count()
                )
            else:
                self.total_avaliado = RelatorioProjeto.objects.filter(projeto__id=self.pk, avaliado_em__isnull=False).count()
            if self.get_registro_conclusao() and self.get_registro_conclusao().dt_avaliacao:
                self.total_avaliado += 1
        return self.total_avaliado

    total_executado = None

    def get_total_executado(self):
        if not self.total_executado:
            if self.edital.tem_monitoramento_por_atividades():
                self.total_executado = (
                    RegistroExecucaoEtapa.objects.filter(etapa__meta__projeto__id=self.pk).count()
                    + RegistroGasto.objects.filter(item__projeto__id=self.pk).count()
                )
            else:
                self.total_executado = RelatorioProjeto.objects.filter(projeto__id=self.pk).count()
            if self.get_registro_conclusao():
                self.total_executado += 1
        return self.total_executado

    def get_proporcao_execucao(self):
        if self.edital.tem_monitoramento_por_atividades():
            return f'{self.get_total_executado()}/{self.get_total_planejado()}'
        else:
            return f'{self.relatorioprojeto_set.filter(tipo=RelatorioProjeto.FINAL).count()}/{1}'

    def get_proporcao_avaliacao(self):
        if self.edital.tem_monitoramento_por_atividades():
            return f'{self.get_total_avaliado()}/{self.get_total_executado()}'
        else:
            return f'{self.relatorioprojeto_set.filter(tipo=RelatorioProjeto.FINAL, avaliado_em__isnull=False).count()}/{self.relatorioprojeto_set.filter(tipo=RelatorioProjeto.FINAL).count()}'

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

    def get_participacoes_alunos_ativos(self):
        return list(self.participacao_set.filter(ativo=True, vinculo_pessoa__tipo_relacionamento__model='aluno'))

    def get_participacoes_alunos_ativos_bolsistas(self):
        return list(
            self.participacao_set.filter(
                ativo=True, bolsa_concedida=True, vinculo_pessoa__tipo_relacionamento__model='aluno', vinculo=TipoVinculo.BOLSISTA
            )
        )

    def get_participacoes_servidores_ativos(self):
        return list(self.participacao_set.filter(ativo=True, vinculo_pessoa__tipo_relacionamento__model='servidor'))

    def get_participacoes_externo_ativos(self):
        return list(self.participacao_set.filter(ativo=True, vinculo_pessoa__tipo_relacionamento__model='prestadorservico'))

    def get_registro_conclusao(self):
        qs = self.registroconclusaoprojeto_set.all()
        if qs.exists():
            return qs.select_related('avaliador')[0]
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
        if self.edital.tipo_edital == Edital.PESQUISA_INOVACAO_CONTINUO:
            return False
        desembolsos = Desembolso.objects.filter(projeto=self)
        if not desembolsos:
            return False
        for desembolso in desembolsos:
            if not RegistroGasto.objects.filter(desembolso=desembolso).exists():
                return True
        qs = RegistroGasto.objects.filter(item__projeto=self)
        if qs:
            if self.edital.permitir_finalizar_sem_validacao_desembolsos:
                return False
            return qs.filter(dt_avaliacao__isnull=True).exists()
        return True

    def tem_registro_foto_pendente(self):
        """
        Verifica se para este projeto há registro de fotos.
        """
        qs = FotoProjeto.objects.filter(projeto=self).exists()
        return not qs

    def tem_registro_anexos_pendente(self):
        """
        Verifica se para este projeto há registro de anexos.
        """
        if self.projetoanexo_set.all():
            for anexo in self.projetoanexo_set.all():
                if anexo.vinculo_membro_equipe and not anexo.arquivo:
                    if Participacao.objects.filter(vinculo_pessoa=anexo.vinculo_membro_equipe, projeto=self, ativo=True).exists():
                        return True
        return False

    def get_absolute_url(self):
        return f'/pesquisa/projeto/{self.id}/'

    def atualizar_pontuacao_curriculo_lattes(self, maior_pontuacao_curriculo=None):
        servidor = self.get_responsavel().relacionamento
        eh_servidor = self.get_responsavel().eh_servidor()
        ano_de_contabilizacao = self.edital.inicio_inscricoes.year - self.edital.qtd_anos_anteriores_publicacao
        if self.edital.pontuacao_diferenciada_maternidade and eh_servidor:
            tem_afastamento_por_gravidez = ServidorAfastamento.objects.filter(servidor=servidor, cancelado=False, afastamento__sigla='LICGESTANT')
            if tem_afastamento_por_gravidez.exists():
                ano_afastamento_maternidade = ano_de_contabilizacao - 1
                anos_para_checar = []
                ano_atual = self.edital.inicio_inscricoes.year
                while ano_atual >= ano_afastamento_maternidade:
                    anos_para_checar.append(ano_atual)
                    ano_atual -= 1
                total_afastamentos = tem_afastamento_por_gravidez.filter(
                    Q(data_inicio__year__in=anos_para_checar) | Q(data_termino__year__in=anos_para_checar)
                ).count()
                if total_afastamentos:
                    ano_de_contabilizacao = ano_de_contabilizacao - (2 * total_afastamentos)
        dic_producoes = Parametro.get_numero_producao_academica(servidor, ano_de_contabilizacao)
        for parametro in ParametroEdital.objects.filter(edital_id=self.edital).order_by('parametro__codigo'):
            parametro_projeto = ParametroProjeto.objects.filter(parametro_edital_id=parametro.id, projeto=self)
            if not parametro_projeto.exists():
                parametro_projeto = ParametroProjeto.objects.create(
                    parametro_edital_id=parametro.id, projeto=self, quantidade=dic_producoes[parametro.parametro.codigo][0]
                )
            else:
                parametro_projeto.update(quantidade=dic_producoes[parametro.parametro.codigo][0])
        self.data_validacao_pontuacao = datetime.datetime.now()
        self.pontuacao_curriculo = self.get_pontuacao_total()
        Projeto.objects.filter(id=self.id).update(
            data_validacao_pontuacao=self.data_validacao_pontuacao,
            pontuacao_curriculo=self.pontuacao_curriculo,
            pontuacao_curriculo_normalizado=self.pontuacao_curriculo_normalizado,
        )
        if maior_pontuacao_curriculo is None:
            # Normaliza todos os projetos participantes do edital deste projeto (self.edital), faz isso em segundo plano
            # edital.normalizar_pontuacao_curriculo_lattes chama esté método também, mas não ocorre limie de recursividade porque maior_pontuacao_curriculo é diferente de None
            thr = Thread(target=self.edital.normalizar_pontuacao_curriculo_lattes, args=(self.uo,))
            thr.start()
        else:
            self._normalizar_pontuacao_curriculo_lattes(maior_pontuacao_curriculo)

    def _normalizar_pontuacao_curriculo_lattes(self, maior_pontuacao_curriculo):
        if maior_pontuacao_curriculo > 0:
            self.pontuacao_curriculo_normalizado = (10 * self.pontuacao_curriculo) / maior_pontuacao_curriculo
        else:
            self.pontuacao_curriculo_normalizado = 0
        Projeto.objects.filter(id=self.id).update(pontuacao_curriculo_normalizado=self.pontuacao_curriculo_normalizado)
        self.atualizar_pontuacao_total()

    def atualizar_pontuacao_grupo_pesquisa(self, maior_pontuacao_curriculo=None):
        Projeto.objects.filter(id=self.id).update(
            pontuacao_grupo_pesquisa=self.get_pontuacao_grupo_pesquisa(),
        )
        if maior_pontuacao_curriculo is None:
            # Normaliza todos os projetos participantes do edital deste projeto (self.edital), faz isso em segundo plano
            # edital.normalizar_pontuacao_curriculo_lattes chama esté método também, mas não ocorre limie de recursividade porque maior_pontuacao_curriculo é diferente de None
            thr = Thread(target=self.edital.normalizar_pontuacao_grupo_pesquisa, args=(self.uo,))
            thr.start()
        else:
            self._normalizar_pontuacao_grupo_pesquisa(maior_pontuacao_curriculo)

    def _normalizar_pontuacao_grupo_pesquisa(self, maior_pontuacao_curriculo):
        if maior_pontuacao_curriculo > 0:
            self.pontuacao_grupo_pesquisa_normalizado = (10 * self.pontuacao_grupo_pesquisa) / maior_pontuacao_curriculo
        else:
            self.pontuacao_grupo_pesquisa_normalizado = 0
        Projeto.objects.filter(id=self.id).update(pontuacao_grupo_pesquisa_normalizado=self.pontuacao_grupo_pesquisa_normalizado)
        self.atualizar_pontuacao_total()

    def edicao_inscricao(self):
        status = self.get_status()
        return bool(self.is_gerente_sistemico() or self.is_gerenciador_projeto() and status == Projeto.STATUS_EM_INSCRICAO)

    def edicao_inscricao_execucao(self):
        status = self.get_status()
        return bool(self.is_gerenciador_projeto() and (status == Projeto.STATUS_EM_INSCRICAO or status == Projeto.STATUS_EM_EXECUCAO))

    def pode_editar_inscricao_execucao(self):
        if running_tests():
            return True
        user = tl.get_user()
        if user.groups.filter(name='Diretor de Pesquisa'):
            return True
        if user.groups.filter(name='Coordenador de Pesquisa') and self.uo == get_uo(user):
            return True
        return bool(self.edicao_inscricao_execucao() and not self.data_finalizacao_conclusao)

    def pode_anexar_arquivo_do_membro(self):
        status = self.get_status()
        return bool(
            (self.edicao_inscricao_execucao() or self.edital.is_periodo_antes_pre_selecao())
            and status != Projeto.STATUS_CONCLUIDO
            and self.is_gerenciador_projeto()
        )

    def pode_adicionar_fotos_e_anexos(self):
        status = self.get_status()
        return bool(
            self.edicao_inscricao_execucao()
            and status != Projeto.STATUS_CONCLUIDO
            and self.is_gerenciador_projeto()
            and not self.data_finalizacao_conclusao
        )

    def pode_adicionar_registro_diario_bordo(self):
        status = self.get_status()
        return bool(
            self.edicao_inscricao_execucao() and status != Projeto.STATUS_CONCLUIDO and self.eh_participante() and not self.data_finalizacao_conclusao
        )

    def pode_remover_projeto(self):
        return bool(self.get_periodo() == self.PERIODO_INSCRICAO and self.is_coordenador())

    def pode_editar_projeto(self):
        return bool(self.get_periodo() in [self.PERIODO_INSCRICAO, self.PERIODO_EXECUCAO] and self.is_gerenciador_projeto())

    def selecao_ja_divulgada(self):
        return self.edital.is_periodo_divulgacao()

    def projeto_em_avaliacao(self):
        return bool(datetime.datetime.today() >= self.edital.inicio_selecao and datetime.datetime.today() <= self.edital.divulgacao_selecao)

    def avaliador_pode_visualizar(self):
        return not (self.is_avaliador() and self.projeto_em_avaliacao())

    def avaliador_pode_visualizar_anexos(self):
        if self.edital.avaliador_ve_anexos:
            return True
        return self.avaliador_pode_visualizar()

    def pode_ser_pre_rejeitado(self):
        periodo = self.get_periodo()
        if self.pode_pre_selecionar() and periodo == Projeto.PERIODO_PRE_SELECAO and self.data_conclusao_planejamento:
            if self.data_pre_avaliacao is None:
                return True
            if self.pre_aprovado:
                return True
        return False

    def pode_ser_pre_aprovado(self):
        periodo = self.get_periodo()
        if self.pode_pre_selecionar() and periodo == Projeto.PERIODO_PRE_SELECAO and self.data_conclusao_planejamento:
            if self.data_pre_avaliacao is None:
                return True
            if not self.pre_aprovado:
                return True
        return False

    def pode_receber_pre_avaliacao(self, rejeitar: bool | None, user: User) -> bool:
        """Papel e estado em que a lista de pré-seleção oferece a ação pedida (#17570).

        `rejeitar=None` é o botão "Pré-selecionar", cuja view inverte o estado atual.
        """
        if self.edital.forma_selecao == Edital.GERAL and not user.groups.filter(name__in=GRUPOS_PRE_SELECAO_INSTITUCIONAIS).exists():
            return False  # a lista de edital geral é negada ao Coordenador de Pesquisa
        if rejeitar is None:
            return self.pode_ser_pre_aprovado() or self.pode_ser_pre_rejeitado()
        return self.pode_ser_pre_rejeitado() if rejeitar else self.pode_ser_pre_aprovado()

    def exibir_acao_pre_rejeitar(self):
        if self.pode_ser_pre_rejeitado():
            if self.edital.tipo_edital == Edital.PESQUISA_INOVACAO_CONTINUO:
                if self.data_avaliacao:
                    return ''  # edital de fluxo contínuo uma vez pré-rejeitado não poderá mais ser pré-avaliado.
                else:
                    return f'<a class="confirm btn danger" data-confirm="Deseja realmente não selecionar este projeto? Esta operação não poderá ser desfeita." href="/pesquisa/pre_rejeitar/{self.id:d}/">Não Selecionar</a>'
            return f'<a class="btn danger" href="/pesquisa/pre_rejeitar/{self.id:d}/">Não Selecionar</a>'
        return ''

    def pode_devolver_projeto(self):
        periodo = self.get_periodo()
        tem_permissao_para_devolver = self.is_gerente_sistemico() or self.is_pre_avaliador()
        if self.data_conclusao_planejamento:
            if tem_permissao_para_devolver and self.pre_aprovado is False:
                if (
                    self.edital.tipo_edital == Edital.PESQUISA_INOVACAO_CONTINUO
                    or periodo == Projeto.PERIODO_INSCRICAO
                    or not self.edital.tem_formato_completo()
                ):
                    return True

            if self.is_avaliador() and self.edital.tipo_edital == Edital.PESQUISA_INOVACAO_CONTINUO and not self.aprovado:
                return True
        return False

    def exibir_acao_pre_aprovar(self):
        if self.pode_ser_pre_aprovado():
            if self.edital.tipo_edital == Edital.PESQUISA_INOVACAO_CONTINUO:
                if self.data_avaliacao:
                    return ''  # edital de fluxo contínuo, uma vez pré-aprovado, pode ser desfeito desde que não tenha sido selecionado.
                return f'<a class="confirm btn success" data-confirm="Deseja realmente selecionar este projeto? Esta operação não poderá ser desfeita." href="/pesquisa/pre_selecionar/{self.id:d}/">Pré-selecionar </a>'
            return f'<a class="btn success" href="/pesquisa/pre_selecionar/{self.id:d}/">Pré-selecionar</a>'
        return ''

    def pode_adicionar_memoria_calculo(self):
        if self.eh_participante() and not self.is_gerenciador_projeto():
            return False

        status = self.get_status()
        return (
            self.is_gerente_sistemico()
            or self.is_coordenador_pesquisa_campus_projeto()
            or (self.is_gerenciador_projeto() and (status == Projeto.STATUS_EM_INSCRICAO or status == Projeto.STATUS_EM_EXECUCAO))
        )

    def pode_exibir_opcoes(self):
        if self.is_gerenciador_projeto() or self.is_avaliador():
            if not self.get_registro_conclusao():
                return True
        return False

    def pode_enviar_projeto(self):
        periodo = self.get_periodo()
        return bool(self.is_coordenador() and periodo == self.PERIODO_INSCRICAO and not self.data_conclusao_planejamento)

    def pode_emitir_parecer(self):
        if self.edital.tem_monitoramento_por_atividades():
            if (
                (self.is_pre_avaliador() or self.eh_supervisor())
                and self.data_finalizacao_conclusao
                and not self.registroconclusaoprojeto_set.all()[0].dt_avaliacao
            ):
                return True
        else:
            if (
                (self.is_pre_avaliador() or self.eh_supervisor())
                and self.data_finalizacao_conclusao
                and self.relatorioprojeto_set.filter(tipo=RelatorioProjeto.FINAL, aprovado=True).exists()
                and not self.registroconclusaoprojeto_set.exclude(dt_avaliacao=None).exists()
            ):
                return True

        return False

    def pode_aprovar_projeto(self):
        return self.edital.is_periodo_selecao_e_pre_divulgacao() and self.aprovado == self.aprovado_na_distribuicao

    def pode_atualizar_curriculo_lattes(self):
        return self.edital.pode_atualizar_curriculo_lattes()

    def exibir_aba_calculo_da_pontuacao(self):
        return self.edital.peso_avaliacao_lattes_coordenador > 0

    def eh_somente_leitura(self):
        if self.is_gerente_sistemico():
            return False
        if self.data_finalizacao_conclusao or self.foi_cancelado() or self.inativado:
            return True
        periodo = self.get_periodo()
        return bool(periodo != Projeto.PERIODO_EXECUCAO and self.data_conclusao_planejamento)

    def atualizar_pontuacao_total(self):
        pontuacao_clattes = self.edital.peso_avaliacao_lattes_coordenador * self.pontuacao_curriculo_normalizado
        pontuacao_projeto = 0 if self.pontuacao is None else self.pontuacao
        pontuacao_da_avaliacao = self.edital.peso_avaliacao_projeto * pontuacao_projeto
        pontuacao_grupo_pesquisa = self.edital.peso_avaliacao_grupo_pesquisa * self.pontuacao_grupo_pesquisa_normalizado

        soma_pontuacao_da_avaliacoes_e_clattes = (
            self.edital.peso_avaliacao_lattes_coordenador + self.edital.peso_avaliacao_projeto + self.edital.peso_avaliacao_grupo_pesquisa
        )
        pontuacao_total = 0
        if soma_pontuacao_da_avaliacoes_e_clattes:
            pontuacao_total = (pontuacao_clattes + pontuacao_da_avaliacao + pontuacao_grupo_pesquisa) / soma_pontuacao_da_avaliacoes_e_clattes
        self.pontuacao_total = pontuacao_total
        Projeto.objects.filter(id=self.id).update(pontuacao_total=self.pontuacao_total)

    @property
    def participacao_por_vinculo(self):
        return self.participacao_set.order_by('vinculo')

    def atualizar_cotas_bolsa(self) -> None:
        """Grava nas cotas do projeto quantas bolsas foram concedidas a pesquisadores e a alunos."""
        self.cota_bolsa_aluno = 0
        self.cota_bolsa_pesquisador = 0
        for participacao in Participacao.objects.filter(projeto=self, bolsa_concedida=True):
            if participacao.is_servidor():
                self.cota_bolsa_pesquisador += 1
            else:
                self.cota_bolsa_aluno += 1
        self.save()

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
        return self.pre_aprovado and self.edital.data_recurso and self.edital.data_recurso > agora and self.edital.is_periodo_pos_fim_selecao()

    def pode_editar_equipe_propi(self, user):
        status = self.get_status()
        if status == Projeto.STATUS_EM_INSCRICAO:
            return True
        if user.groups.filter(name='Diretor de Pesquisa'):
            return True
        return user.groups.filter(name='Coordenador de Pesquisa') and self.uo == get_uo(user)

    def pode_alterar_coordenador(self, user: User | None = None) -> bool:
        """Quem pode "Substituir Coordenador": a view ``alterar_coordenador`` e o botão da aba "Equipe".

        O Diretor de Pesquisa troca o coordenador de qualquer projeto; o Coordenador de Pesquisa, só do
        próprio campus. Em inscrição, também o coordenador do projeto e o Pré-Avaliador Sistêmico. Nunca
        fora de inscrição/execução nem em projeto somente leitura. Não usa ``pode_editar_equipe_propi``,
        que é verdadeiro para qualquer usuário em inscrição (#17573).
        """
        if not user:
            user = tl.get_user()
        eh_gestor = self.is_gerente_sistemico(user).exists() or self.is_coordenador_pesquisa_campus_projeto(user)
        eh_da_inscricao = self.get_status() == Projeto.STATUS_EM_INSCRICAO and (
            self.is_responsavel(user) or user.groups.filter(name='Pré-Avaliador Sistêmico de Projetos de Pesquisa').exists()
        )
        return bool((eh_gestor or eh_da_inscricao) and self.pode_editar_inscricao_execucao() and not self.eh_somente_leitura())

    def foi_cancelado(self):
        return ProjetoCancelado.objects.exclude(data_avaliacao=None).filter(projeto_id=self.id, cancelado=True).exists()

    def pode_cancelar_projeto(self):
        user = tl.get_user()
        status = self.get_status()
        tem_solicitacao_cancelamento = ProjetoCancelado.objects.filter(projeto=self).exists()
        projeto_esta_em_execucao = self.get_periodo() == Projeto.PERIODO_EXECUCAO
        return bool(
            (self.is_coordenador() or self.is_coordenador_pesquisa_campus_projeto(user))
            and status != Projeto.STATUS_CONCLUIDO
            and status != Projeto.STATUS_INATIVADO
            and not tem_solicitacao_cancelamento
            and projeto_esta_em_execucao
        )

    def pode_mostrar_dados_selecao(self):
        return self.edital.tipo_edital == Edital.PESQUISA

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
        agora = datetime.datetime.now().date()
        if self.get_status() != Projeto.STATUS_EM_EXECUCAO:
            return False

        if ProjetoCancelado.objects.filter(projeto=self).exists():
            return False

        return Etapa.objects.filter(meta__projeto=self, fim_execucao__lte=agora, registroexecucaoetapa__isnull=True).exists()

    def foi_selecionado_fora_do_prazo(self):
        return ProjetoCancelado.objects.filter(proximo_projeto=self).exists()

    def get_data_selecao_fora_do_prazo(self):
        return ProjetoCancelado.objects.get(proximo_projeto=self).data_avaliacao

    def get_projeto_desistencia(self):
        return ProjetoCancelado.objects.get(proximo_projeto=self).projeto.titulo

    def mensagem_restricao_adicionar_membro(self, categoria, bolsista=None, participacao=None):
        if not self.edital.tem_formato_completo():
            return None
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
                    return 'Esse edital não prevê bolsas para pesquisadores.'
                if pesquisador >= self.edital.qtd_maxima_servidores_bolsistas:
                    return 'A quantidade máxima de servidores bolsistas na equipe já foi atingida.'
            else:
                if self.edital.qtd_maxima_alunos_bolsistas == 0:
                    return 'Esse edital não prevê bolsas para alunos.'
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

    def pode_gerenciar_participacao(self):
        return self.get_status() != Projeto.STATUS_EM_INSCRICAO

    def get_equipe_projeto(self):
        return self.participacao_set.all().select_related('vinculo_pessoa').order_by('-responsavel', '-ativo')

    def pendente_avaliacao(self) -> bool:
        user = tl.get_user()
        return (
            self.pre_aprovado
            and AvaliadorIndicado.objects.filter(vinculo=user.get_vinculo(), projeto=self, rejeitado=False).exists()
            and not Avaliacao.objects.filter(projeto=self, vinculo=user.get_vinculo()).exists()
        )

    def tem_pendencias(self):
        if self.data_finalizacao_conclusao:
            return False
        if not self.edital.tem_monitoramento_por_atividades():
            return bool(not self.relatorioprojeto_set.filter(tipo=RelatorioProjeto.FINAL, aprovado=True).exists())
        return bool(
            self.tem_registro_execucao_etapa_pendente()
            or self.tem_registro_gasto_pendente()
            or self.tem_registro_foto_pendente()
            or self.tem_registro_anexos_pendente()
        )

    def tem_metas_vencendo_em(self, dias=None, envia_email=None):
        hoje = datetime.datetime.now().date()
        prazo = hoje
        if dias:
            prazo = hoje + relativedelta(days=dias)
        metas_do_projeto = Meta.objects.filter(projeto=self, etapa_set__registroexecucaoetapa__isnull=True)
        if metas_do_projeto.exists():
            for meta in metas_do_projeto:
                data_final = meta.get_data_final_meta()
                if data_final:
                    if dias and not envia_email and data_final >= hoje and data_final <= prazo or data_final == prazo:
                        return True
        return False

    def tem_data_fim_execucao_em(self, dias=None, envia_email=None):
        hoje = datetime.datetime.now().date()
        prazo = hoje
        if dias:
            prazo = hoje + relativedelta(days=dias)
        return bool(dias and not envia_email and self.fim_execucao >= hoje and self.fim_execucao <= prazo or self.fim_execucao == prazo)

    def tem_anexos_equipe(self):
        return self.projetoanexo_set.filter(descricao__isnull=True).exists()

    def tem_outros_anexos(self):
        return self.projetoanexo_set.filter(descricao__isnull=False).exists()

    def tem_atividade_todo_mes(self):
        from datetime import timedelta

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

    def get_carga_horaria_coordenador(self):
        return Participacao.objects.filter(projeto=self, responsavel=True)[0].carga_horaria

    def coordenador_eh_professor(self):
        if 'edu' in settings.INSTALLED_APPS:
            from edu.models import Professor

            if Professor.objects.filter(vinculo=self.vinculo_coordenador).exists():
                return Professor.objects.filter(vinculo=self.vinculo_coordenador)[0]
        return False

    def pendente_anuencia(self):
        return not (self.anuencia or not self.vinculo_coordenador.eh_servidor())

    def tem_atividade_ou_gasto_sem_validacao(self):
        if self.edital.tem_monitoramento_por_atividades():
            return (
                RegistroExecucaoEtapa.objects.filter(etapa__meta__projeto=self, dt_avaliacao__isnull=True).exists()
                or RegistroGasto.objects.filter(desembolso__projeto=self, dt_avaliacao__isnull=True).exists()
            )
        else:
            return RelatorioProjeto.objects.filter(projeto=self, avaliado_em__isnull=True).exists()

    def get_avaliadores_indicados(self):
        return AvaliadorIndicado.objects.filter(projeto=self).order_by('vinculo__pessoa')

    def tem_aceite_pendente(self):
        if (
            not self.edital.termo_compromisso_servidor
            and not self.edital.termo_compromisso_aluno
            and not self.edital.termo_compromisso_colaborador_externo
        ) or self.edital.ignorar_termo_pendente:
            return False
        if self.edital.termo_compromisso_servidor:
            for servidor in self.get_participacoes_servidores_ativos():
                if not servidor.termo_aceito_em and not servidor.responsavel:
                    return True

        if self.edital.termo_compromisso_aluno:
            for aluno in self.get_participacoes_alunos_ativos():
                if not aluno.termo_aceito_em:
                    return True

        if self.edital.termo_compromisso_colaborador_externo:
            for externo in self.get_participacoes_externo_ativos():
                if not externo.termo_aceito_em:
                    return True
        return False

    def tem_atividades_cadastradas(self):
        return Etapa.objects.filter(meta__projeto_id=self.id).select_related('meta').exists()

    def get_pontuacao_grupo_pesquisa(self):
        if self.grupo_pesquisa:
            total = 0
            for curriculo in CurriculoVittaeLattes.objects.filter(
                vinculo__tipo_relacionamento__model='servidor', grupos_pesquisa=self.grupo_pesquisa, vinculo__isnull=False
            ):
                obj_servidor = curriculo.vinculo.relacionamento
                if obj_servidor.ativo:
                    total_curriculo = 0
                    dic_producoes = Parametro.get_numero_producao_academica(
                        obj_servidor, self.edital.inicio_inscricoes.year - self.edital.qtd_anos_anteriores_publicacao
                    )

                    for parametro in ParametroEdital.objects.filter(edital_id=self.edital).order_by('parametro__codigo'):
                        if parametro.parametro.codigo in dic_producoes:
                            total_curriculo += (dic_producoes[parametro.parametro.codigo][0]) * parametro.valor_parametro
                    total += total_curriculo
            return total
        return 0

    def pode_aceitar_indicacao(self):
        indicacao = self.avaliadorindicado_set.filter(vinculo=tl.get_user().get_vinculo()).first()
        return indicacao and indicacao.prazo_para_aceite and not indicacao.rejeitado and not indicacao.aceito_em

    def rejeitou_indicacao(self):
        indicacao = self.avaliadorindicado_set.filter(vinculo=tl.get_user().get_vinculo()).first()
        return indicacao and indicacao.rejeitado

    def get_relatorio_final(self):
        return self.relatorioprojeto_set.filter(tipo=RelatorioProjeto.FINAL)

    def tem_participantes(self):
        return Participacao.objects.filter(projeto_id=self.id, responsavel=False).exists()

    def pode_alterar_chefia_imediata(self, user: User | None = None) -> bool:
        # Só o Diretor de Pesquisa e o Coordenador de Pesquisa do campus do projeto, em edital que exige anuência (#17578).
        if not user:
            user = tl.get_user()
        if not self.edital.exige_anuencia:
            return False
        if not (self.is_gerente_sistemico(user).exists() or self.is_coordenador_pesquisa_campus_projeto(user)):
            return False
        return self.edital.get_data_limite_anuencia() > datetime.datetime.now() and self.get_status() not in [
            self.STATUS_CANCELADO,
            self.STATUS_CONCLUIDO,
            self.STATUS_INATIVADO,
        ]

    def tem_participante_afastado(self):
        retorno = []
        for participante in self.get_participacoes_servidores_ativos():
            afastamento = participante.vinculo_pessoa.relacionamento.estah_afastado_ateh(datetime.date.today())
            if afastamento:
                retorno.append(
                    f'{participante} afastado de {afastamento.data_inicio.strftime("%d/%m/%Y")} até {afastamento.data_termino.strftime("%d/%m/%Y")}'
                )
        return ', '.join(retorno)

    def get_solicitacoes_inclusao_pendente(self):
        return SolicitacaoInclusaoEquipe.objects.filter(projeto=self, atendida=None)

    def pode_avaliar_projeto(self, vinculo: Vinculo | None) -> bool:
        return bool(
            self.pre_aprovado
            and not self.aprovado
            and self.edital.is_periodo_selecao()
            and self.data_conclusao_planejamento
            and AvaliadorIndicado.objects.filter(projeto=self, vinculo=vinculo, rejeitado=False).exists()
        )

    def get_identificador(self):
        return f'{self.id}/{self.edital.inicio_inscricoes.year}'

    def pode_reverter_finalizacao_projeto(self):
        user = tl.get_user()
        return self.data_finalizacao_conclusao and self.get_status() == Projeto.STATUS_EM_EXECUCAO and self.vinculo_supervisor == user.get_vinculo()

    def get_participacoes_colaboradores(self):
        return list(self.participacao_set.filter(ativo=True, vinculo_pessoa__tipo_relacionamento__model='prestadorservico'))

    @transaction.atomic
    def save(self, *args, **kwargs):
        if tl.get_user() is not None and not self.vinculo_coordenador:
            self.vinculo_coordenador = (self.id and Projeto.objects.get(id=self.id).vinculo_coordenador) or tl.get_user().get_vinculo()
            self.auxiliar = self.id and Projeto.objects.get(id=self.id).auxiliar
        super().save(*args, **kwargs)
        if not self.get_responsavel():
            # Entre neste bloco no momento em que está cadastrando o projeto no edital -- uma única vez.
            # Insere o próprio usuário que submeteu o projeto como coordenador do mesmo na lista de equipes (participantes)
            p = Participacao()
            p.projeto = self
            p.vinculo_pessoa = tl.get_user().get_vinculo()
            if self.bolsa_coordenador:
                p.vinculo = TipoVinculo.BOLSISTA
                p.bolsa_concedida = True
            else:
                p.vinculo = TipoVinculo.VOLUNTARIO
                p.bolsa_concedida = False
            p.responsavel = True
            p.carga_horaria = self.edital.ch_semanal_coordenador
            p.save()
            p.adicionar_registro_historico_equipe(HistoricoEquipe.EVENTO_COORDENADOR_INSERIDO)
            Participacao.gerar_anexos_do_participante(p)

            # Atualiza a pontuação do currículo lattes, este normaliza e atualiza a pontuação total do projeto.
            if self.edital.parametroedital_set.all().exists():
                self.atualizar_pontuacao_curriculo_lattes()
            if self.edital.peso_avaliacao_grupo_pesquisa:
                self.atualizar_pontuacao_grupo_pesquisa()


class AvaliadorIndicado(models.ModelPlus):
    projeto = models.ForeignKeyPlus(Projeto, on_delete=models.CASCADE)
    vinculo = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Avaliador', related_name='pesquisa_vinculo_avaliadorindicado', on_delete=models.CASCADE, null=True
    )
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

    def ja_avaliou(self):
        return bool(Avaliacao.objects.filter(vinculo=self.vinculo, projeto=self.projeto).exists())

    def qtd_indicacoes_no_edital(self):
        return AvaliadorIndicado.objects.filter(vinculo=self.vinculo, projeto__edital_id=self.projeto.edital.id).count()

    def qtd_indicacoes_editais_abertos(self):
        return AvaliadorIndicado.objects.filter(
            vinculo=self.vinculo, projeto__edital__in=Edital.objects.em_selecao().values_list('id', flat=True)
        ).count()

    def get_data_avaliacao(self):
        return self.ja_avaliou() and Avaliacao.objects.filter(vinculo=self.vinculo, projeto=self.projeto).last().data or ''


class Avaliacao(models.ModelPlus):
    projeto = models.ForeignKeyPlus(Projeto, on_delete=models.CASCADE)
    vinculo = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Avaliador', related_name='pesquisa_vinculo_avaliador', on_delete=models.CASCADE, null=True
    )
    data = models.DateTimeFieldPlus('Data', auto_now=True)
    parecer = models.TextField()
    pontuacao = models.DecimalFieldPlus('Pontuação')
    pontuacao_normalizada = models.DecimalFieldPlus('Pontuação Normalizada')

    class Meta:
        verbose_name = 'Avaliação'
        verbose_name_plural = 'Avaliações'
        unique_together = ('projeto', 'vinculo')

    def delete(self):
        qs_avaliacoes = self.projeto.avaliacao_set.exclude(id=self.id)
        self.atualiza_pontuacao_projeto(qs_avaliacoes)
        super().delete()

    def save(self, *args, **kwargs):
        self.pontuacao, self.pontuacao_normalizada = self.get_pontuacoes()
        super().save(args, kwargs)
        qs_avaliacoes = Avaliacao.objects.filter(projeto=self.projeto)
        self.atualiza_pontuacao_projeto(qs_avaliacoes)

    def get_pontuacoes(self):
        """
        return: a pontuação e pontuação normalizada
        """
        pontuacao_total = 0
        pontuacao_normalizada = 0
        itens_desta_avaliacao = self.itemavaliacao_set
        if self.pk and itens_desta_avaliacao.exists():
            for item in itens_desta_avaliacao.all():
                pontuacao_total += item.pontuacao
            pontuacao_normalizada = pontuacao_total / itens_desta_avaliacao.count()
            return pontuacao_total, pontuacao_normalizada
        return 0, 0

    def atualiza_pontuacao_projeto(self, qs_avaliacoes):
        total = Decimal('0')
        for avaliacao in qs_avaliacoes:
            total += avaliacao.pontuacao_normalizada
        self.projeto.pontuacao = total / qs_avaliacoes.count()
        self.projeto.data_avaliacao = datetime.datetime.now()
        Projeto.objects.filter(id=self.projeto.id).update(pontuacao=self.projeto.pontuacao, data_avaliacao=self.projeto.data_avaliacao)
        if self.projeto.edital.tipo_edital == Edital.PESQUISA_INOVACAO_CONTINUO:
            if qs_avaliacoes.count() == AvaliadorIndicado.objects.filter(projeto=self.projeto, rejeitado=False).count():
                if self.projeto.pontuacao >= (
                    (self.projeto.edital.nota_corte_projeto_fluxo_continuo * self.projeto.edital.get_pontuacao_maxima_normalizada_edital()) / 100
                ):
                    Projeto.objects.filter(id=self.projeto.id).update(aprovado=True)
                else:
                    Projeto.objects.filter(id=self.projeto.id).update(aprovado=False)
        self.projeto.atualizar_pontuacao_total()


class ItemAvaliacao(models.ModelPlus):
    avaliacao = models.ForeignKeyPlus(Avaliacao)
    criterio_avaliacao = models.ForeignKeyPlus(CriterioAvaliacao, verbose_name='Critério', on_delete=models.CASCADE)
    pontuacao = models.DecimalFieldPlus('Pontuação')
    parecer = models.TextField(null=True, blank=True)
    recurso = models.TextField(null=True)
    recurso_em = models.DateTimeFieldPlus('Recurso cadastrado em', null=True)
    recurso_por = models.ForeignKeyPlus(
        Vinculo, verbose_name='Recurso cadastrado por', null=True, on_delete=models.SET_NULL, related_name='recurso_cadastradopor'
    )
    pontuacao_original = models.DecimalFieldPlus('Pontuação original', null=True)
    recurso_aceito = models.BooleanField('Recurso aceito', default=False)
    recurso_avaliado_em = models.DateTimeFieldPlus('Recurso avaliado em', null=True)
    recurso_avaliado_por = models.ForeignKeyPlus(
        Vinculo, verbose_name='Recurso avaliado por', null=True, on_delete=models.SET_NULL, related_name='recurso_avaliadopor'
    )
    resposta_recurso = models.TextField('Resposta ao recurso', null=True)

    def pode_ser_avaliado(self):
        return self.recurso and self.avaliacao.projeto.edital.id in Edital.objects.all().em_avaliacao_recursos().values_list('id', flat=True)


class ItemMemoriaCalculo(models.ModelPlus):
    SEARCH_FIELD = ['descricao']
    projeto = models.ForeignKeyPlus(Projeto, on_delete=models.CASCADE)
    despesa = models.ForeignKeyPlus(NaturezaDespesa, verbose_name='Despesa', related_name='pesquisa_itemmemoria_despesa', on_delete=models.CASCADE)
    descricao = models.TextField('Descrição', max_length=2014)
    unidade_medida = models.CharField('Unidade de Medida', max_length=50)
    qtd = models.PositiveIntegerField('Quantidade')
    valor_unitario = models.DecimalFieldPlus('Valor Unitário (R$)')
    data_cadastro = models.DateFieldPlus('Data de Cadastro do Item de Mémoria de Cálculo', null=True, blank=True, default=datetime.datetime.now)

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
        if self.projeto.is_gerente_sistemico() or self.projeto.is_coordenador_pesquisa_campus_projeto():
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
        return f'{self.despesa} - {self.descricao}'


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
        qtd = self.quantidade
        if self.parametro_edital.qtd_maxima and self.parametro_edital.qtd_maxima < self.quantidade:
            qtd = self.parametro_edital.qtd_maxima
        return qtd * self.parametro_edital.valor_parametro

    def get_form_field(self, initial):
        return forms.DecimalField(
            label=f'{self.parametro_edital.parametro.codigo} - {self.parametro_edital.parametro.descricao}',
            widget=forms.TextInput(attrs={'readonly': 'True'}),
            initial=initial or 10,
        )


class Desembolso(models.ModelPlus):
    SEARCH_FIELDS = ['despesa__nome', 'despesa__codigo', 'item__descricao']
    projeto = models.ForeignKeyPlus(Projeto, verbose_name='Projeto', on_delete=models.CASCADE)
    ano = models.ForeignKeyPlus('comum.Ano', verbose_name='Ano', related_name='pesquisa_desembolso_ano', on_delete=models.CASCADE)
    mes = models.PositiveIntegerField(
        'Mês',
        choices=[[1, '1'], [2, '2'], [3, '3'], [4, '4'], [5, '5'], [6, '6'], [7, '7'], [8, '8'], [9, '9'], [10, '10'], [11, '11'], [12, '12']],
        help_text='O mês 1 indica o primeiro mês do projeto',
    )
    despesa = models.ForeignKeyPlus(NaturezaDespesa, verbose_name='Despesa', related_name='pesquisa_desembolso_despesa', on_delete=models.CASCADE)
    valor = models.DecimalFieldPlus('Valor (R$)')
    data_cadastro = models.DateFieldPlus('Data de Cadastro do Desembolso', null=True, blank=True)
    item = models.ForeignKeyPlus(ItemMemoriaCalculo, verbose_name='Mémoria de Cálculo', null=True, on_delete=models.CASCADE)

    def __str__(self):
        if self.item:
            return f'{self.item} / Ano: {self.ano} / Mês: {self.mes}'
        return f'Ano: {self.ano} / Mês: {self.mes}'

    def save(self, *args, **kwargs):
        if not self.id:
            self.data_cadastro = datetime.datetime.now()
        self.despesa = self.item.despesa
        super().save(args, kwargs)

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
        if self.projeto.is_gerente_sistemico() or self.projeto.is_coordenador_pesquisa_campus_projeto():
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
    ano = models.ForeignKeyPlus('comum.Ano', verbose_name='Ano', related_name='pesquisa_gasto_ano', on_delete=models.CASCADE)
    mes = models.PositiveIntegerField(
        'Mês', choices=[[1, '1'], [2, '2'], [3, '3'], [4, '4'], [5, '5'], [6, '6'], [7, '7'], [8, '8'], [9, '9'], [10, '10'], [11, '11'], [12, '12']]
    )
    descricao = models.TextField(
        'Descrição',
        max_length=2014,
        help_text='Altere essa informação caso o produto/serviço/bolsa adiquirido(a)/pago(a) não tenha sido o definido na memória de cálculo',
    )
    qtd = models.PositiveIntegerField('Quantidade', help_text='Informe a quantidade adquirida/paga no período (mês/ano) informado')
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
    avaliador = models.ForeignKeyPlus(Servidor, null=True, related_name='pesquisa_gasto_avaliador', on_delete=models.CASCADE)
    aprovado = models.BooleanField(default=False)
    justificativa_reprovacao = models.CharField(
        'Justificativa da Reprovação do Gasto',
        max_length=5000,
        null=True,
        blank=True,
        help_text='Informação adicional que você julgar relevante no que diz respeito à reprovação do gasto.',
    )
    desembolso = models.ForeignKeyPlus(Desembolso, null=True, on_delete=models.CASCADE)
    arquivo = models.FileFieldPlus(max_length=255, upload_to='upload/pesquisa/registrogasto/comprovantes/', null=True, blank=True)
    cotacao_precos = models.FileFieldPlus(max_length=255, upload_to='upload/pesquisa/registrogasto/comprovantes/', null=True, blank=True)
    obs_cancelamento_avaliacao = models.CharField('Motivo do Cancelamento da Avaliação', max_length=1500, null=True, blank=True)
    avaliacao_cancelada_por = models.ForeignKeyPlus(
        Servidor, null=True, related_name='pesquisa_cancelamento_avaliacao_gasto', on_delete=models.CASCADE
    )
    avaliacao_cancelada_em = models.DateTimeFieldPlus(null=True)

    def save(self, *args, **kwargs):
        self.item = self.desembolso.item
        super().save(args, kwargs)

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


class ProjetoAnexo(models.ModelPlus):
    projeto = models.ForeignKeyPlus(Projeto, on_delete=models.CASCADE)
    anexo_edital = models.ForeignKeyPlus(EditalAnexo, on_delete=models.CASCADE, null=True)
    arquivo = models.OneToOneField(Arquivo, null=True, related_name='pesquisa_anexo_arquivo', on_delete=models.CASCADE)
    vinculo_membro_equipe = models.ForeignKeyPlus(
        'comum.Vinculo', null=True, verbose_name='Participante', on_delete=models.CASCADE, related_name='pesquisa_projetoanexo_vinculo'
    )
    descricao = models.CharField('Descrição', max_length=2000, null=True, blank=True)
    desembolso = models.ForeignKeyPlus(Desembolso, null=True, on_delete=models.CASCADE)
    ano = models.ForeignKeyPlus('comum.Ano', verbose_name='Ano', related_name='pesquisa_ano_anexo', on_delete=models.CASCADE, null=True)
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
    )
    cadastrado_em = models.DateTimeFieldPlus('Cadastrado em', auto_now_add=True, null=True)

    class Meta:
        ordering = ['vinculo_membro_equipe__pessoa__nome']

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
    arquivo = models.OneToOneField(Arquivo, null=True, related_name='pesquisa_edital_anexoauxiliar', on_delete=models.CASCADE)
    ordem = models.PositiveIntegerField('Ordem', help_text='Informe um número inteiro maior ou igual a 1')

    class Meta:
        ordering = ['ordem']


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
        if self.etapa_set.all():
            inicio = self.etapa_set.all().order_by('inicio_execucao')[0].inicio_execucao.strftime('%d/%m/%y')
            fim = self.etapa_set.latest('fim_execucao').fim_execucao.strftime('%d/%m/%y')
            periodo = ' - ' + str(inicio) + ' até ' + str(fim)
        return periodo

    def get_data_final_meta(self):
        if self.etapa_set.exists():
            return self.etapa_set.latest('fim_execucao').fim_execucao
        return None

    def tem_etapas_aprovadas(self):
        return RegistroExecucaoEtapa.objects.filter(etapa__meta=self, aprovado=True).exists()

    def eh_planejamento(self):
        return eh_planejamento(self)

    def pode_editar_e_remover_meta(self):
        if self.projeto.eh_somente_leitura():
            return False
        return bool(not self.tem_etapas_aprovadas() and self.projeto.is_gerenciador_projeto() and not self.eh_planejamento())


class RegistroExecucaoEtapa(models.ModelPlus):
    ATENDIDO = '1'
    ATENDIDO_PARCIALMENTE = '2'
    NAO_ATENTIDO = '3'
    TIPO_INDICADOR_QUALITATIVO = ((ATENDIDO, 'Atendido'), (ATENDIDO_PARCIALMENTE, 'Atendido Parcialmente'), (NAO_ATENTIDO, 'Não Atendido'))
    tipo_indicador_qualitativo = models.CharField('Indicadores Qualitativos', max_length=1, choices=TIPO_INDICADOR_QUALITATIVO)
    etapa = models.OneToOneFieldPlus('pesquisa.Etapa', on_delete=models.CASCADE)
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
        validators=[MaxLengthValidator(500)],
        help_text='Descreva e coloque as informações que julgar relevantes na execução da atividade',
    )
    justificativa_reprovacao = models.CharField(
        'Justificativa da Reprovação da Atividade',
        max_length=5000,
        null=True,
        blank=True,
        help_text='Informação adicional que você julgar relevante no que diz respeito à reprovação da atividade.',
    )
    dt_avaliacao = models.DateFieldPlus(null=True)
    avaliador = models.ForeignKeyPlus(Servidor, null=True, related_name='pesquisa_execucao_avaliador', on_delete=models.CASCADE)
    aprovado = models.BooleanField(default=False)
    arquivo = models.FileFieldPlus(max_length=255, upload_to='upload/pesquisa/atividades/comprovantes/', null=True, blank=True)
    obs_cancelamento_avaliacao = models.CharField('Motivo do Cancelamento da Avaliação', max_length=1500, null=True, blank=True)
    avaliacao_cancelada_por = models.ForeignKeyPlus(
        Servidor, null=True, related_name='pesquisa_cancelamento_avaliacao_etapa', on_delete=models.CASCADE
    )
    avaliacao_cancelada_em = models.DateTimeFieldPlus(null=True)

    class Meta:
        verbose_name = 'Registro de Execução de Atividade'
        verbose_name_plural = 'Registros de Execução de Atividades'

    def get_mensagem_avaliacao(self):
        return get_mensagem_avaliacao(self)


class RegistroConclusaoProjeto(models.ModelPlus):
    projeto = models.ForeignKeyPlus(Projeto, on_delete=models.CASCADE)
    resultados_alcancados = models.TextField('Resultados Alcançados', help_text='Informações sobre os resultados obtidos pelo projeto.')
    disseminacao_resultados = models.TextField(
        'Disseminação dos Resultados', help_text='Informações de como os resultados foram e/ou serão divulgados para a sociedade.'
    )
    obs = models.TextField(
        'Observação', null=True, blank=True, help_text='Informação adicional que você julgar relevante no que diz respeito à conclusão do projeto.'
    )
    dt_avaliacao = models.DateFieldPlus(null=True)
    avaliador = models.ForeignKeyPlus(Servidor, null=True, related_name='pesquisa_conclusao_avaliador', on_delete=models.CASCADE)
    obs_avaliador = models.TextField(
        'Observação do Coordenador de Pesquisa',
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


class Participacao(models.ModelPlus):
    TIPOS_PESSOA = {'docente': 'Docente', 'tecnico_administrativo': 'Técnico Adminsitrativo', None: 'Discente'}

    SERVIDOR = '1'
    ALUNO = '2'
    TIPOCONTA_CONTACORRENTE = 'Conta Corrente'
    TIPOCONTA_POUPANCA = 'Conta Poupança'

    TIPOCONTA_CHOICES = ((TIPOCONTA_CONTACORRENTE, TIPOCONTA_CONTACORRENTE), (TIPOCONTA_POUPANCA, TIPOCONTA_POUPANCA))
    projeto = models.ForeignKeyPlus(Projeto, verbose_name='Projeto', on_delete=models.CASCADE)
    vinculo_pessoa = models.ForeignKey(
        'comum.Vinculo', verbose_name='Participante', related_name='pesquisa_vinculo_participacao', on_delete=models.CASCADE, null=True
    )
    responsavel = models.BooleanField('Coordenador', default=False)
    vinculo = models.CharField(max_length=255, choices=TipoVinculo.TIPOS)
    carga_horaria = models.PositiveIntegerField('Carga Horária', help_text='Carga horária semanal')
    ativo = models.BooleanField(default=True)
    data_inativacao = models.DateField('Data de Inativação', null=True)
    bolsa_concedida = models.BooleanField(default=False)
    bolsa_no_ae = models.ForeignKeyPlus(
        'ae.ParticipacaoBolsa', verbose_name='Bolsa no AE', related_name='bolsas', null=True, blank=True, on_delete=models.CASCADE
    )
    termo_aceito_em = models.DateTimeFieldPlus(null=True)
    instituicao = models.ForeignKeyPlus(
        'rh.Banco', verbose_name='Banco', null=True, on_delete=models.SET_NULL, related_name='pesquisa_participacao_instituicao'
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
            if not projeto.projetoanexo_set.filter(anexo_edital=anexo_edital, vinculo_membro_equipe=participacao.vinculo_pessoa).exists():
                a = ProjetoAnexo()
                a.anexo_edital = anexo_edital
                a.projeto = projeto
                a.vinculo_membro_equipe = participacao.vinculo_pessoa
                a.save()
            tipos_dos_anexos.append(anexo_edital.id)

        anexos_exigidos = ProjetoAnexo.objects.filter(projeto=projeto, vinculo_membro_equipe=participacao.vinculo_pessoa, arquivo__isnull=True)
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
            return EditalAnexo.COLABORADOR_EXTERNO

    def get_tipos_anexos(self):
        tipo_membro = self.get_tipo_vinculo_membro()

        return EditalAnexo.objects.filter(tipo_membro=tipo_membro, vinculo=self.vinculo, edital=self.projeto.edital)

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
                return (
                    ColaboradorExterno.objects.filter(prestador=self.vinculo_pessoa.id_relacionamento).first() or self.vinculo_pessoa.relacionamento
                )
        return None

    def get_nome(self):
        pessoa = self.get_participante()
        if pessoa:
            if isinstance(pessoa, Aluno):
                return Vinculo.objects.get(id_relacionamento=pessoa.id, tipo_relacionamento__model='aluno').pessoa.nome
            elif isinstance(pessoa, ColaboradorExterno):
                return pessoa.nome
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
                if participante.prestador.pessoa_fisica.cpf:
                    return participante.prestador.pessoa_fisica.cpf
                else:
                    return participante.prestador.pessoa_fisica.passaporte
        else:
            return '-'

    def get_titulacao(self):
        if self.is_servidor():
            servidor = self.vinculo_pessoa.relacionamento
            if servidor.eh_docente:
                return 'DOCENTE ({})'.format(servidor.titulacao or '-')
            if servidor.eh_tecnico_administrativo:
                return 'TÉCNICO-ADMINISTRATIVO ({})'.format(servidor.titulacao or '-')
            if servidor.eh_aposentado:
                return 'APOSENTADO ({})'.format(servidor.titulacao or '-')
            if servidor.eh_estagiario:
                return 'ESTAGIÁRIO ({})'.format(servidor.titulacao or '-')
        elif self.eh_aluno():
            return 'DISCENTE'
        else:
            return 'COLABORADOR EXTERNO'

    def __str__(self):
        return str(self.get_nome())

    def get_selecionado(self):
        if self.projeto.edital.tem_formato_completo():
            if not self.projeto.data_conclusao_planejamento and self.projeto.edital.fim_inscricoes >= datetime.datetime.now():
                return f'<span class="status status-error">{Projeto.STATUS_AGUARDADO_ENVIO_PROJETO}</span>'
            else:
                if self.projeto.divulgacao_avaliacao_liberada() and self.projeto.edital.tipo_edital != self.projeto.edital.PESQUISA_INOVACAO_CONTINUO:
                    if self.projeto.aprovado:
                        return f'<span class="status status-success">{Projeto.STATUS_SELECIONADO_EM} {format_(self.projeto.edital.divulgacao_selecao)} </span>'
                    else:
                        return f'<span class="status status-error">{Projeto.STATUS_NAO_SELECIONADO_EM} {format_(self.projeto.edital.divulgacao_selecao)} </span>'

                elif (
                    not self.projeto.data_avaliacao
                    and self.projeto.divulgacao_avaliacao_liberada()
                    and not self.projeto.pre_aprovado
                    and self.projeto.data_pre_avaliacao
                ):
                    return f'<span class="status status-error">{Projeto.STATUS_NAO_SELECIONADO}</span>'
                else:
                    if self.projeto.edital.tipo_edital == self.projeto.edital.PESQUISA_INOVACAO_CONTINUO:
                        if self.projeto.pre_aprovado:
                            return f'<span class="status status-success">{Projeto.STATUS_SELECIONADO_EM} {format_(self.projeto.data_pre_avaliacao)} </span>'
                        else:
                            return f'<span class="status status-error">{Projeto.STATUS_NAO_SELECIONADO_EM} {format_(self.projeto.data_pre_avaliacao)} </span>'
                    else:
                        return f'<span class="status status-alert">{Projeto.STATUS_AGUARDANDO_AVALIACAO}</span>'
        else:
            return '<span class="status status-alert">Não se aplica.</span>'

    def get_pre_selecionado(self):
        if self.projeto.edital.tem_formato_completo():
            if self.projeto.data_pre_avaliacao:
                if self.projeto.pre_aprovado:
                    return (
                        f'<span class="status status-success">{Projeto.STATUS_PRE_SELECIONADO_EM} {format_(self.projeto.data_pre_avaliacao)} </span>'
                    )
                else:
                    return f'<span class="status status-error">{Projeto.STATUS_NAO_SELECIONADO_EM} {format_(self.projeto.data_pre_avaliacao)} </span>'
            else:
                if not self.projeto.data_conclusao_planejamento and self.projeto.edital.fim_inscricoes >= datetime.datetime.now():
                    return f'<span class="status status-error">{Projeto.STATUS_AGUARDADO_ENVIO_PROJETO}</span>'
                else:
                    return f'<span class="status status-alert">{Projeto.STATUS_AGUARDANDO_PRE_SELECAO}</span>'
        else:
            return '<span class="status status-alert">Não se aplica.</span>'

    def get_dados_bancarios_aluno(self):
        from ae.models import DadosBancarios

        aluno = Aluno.objects.get(id=self.vinculo_pessoa.id_relacionamento)
        dados_bancarios = aluno.get_dados_bancarios().filter(banco=DadosBancarios.BANCO_BB).order_by('-id')
        if self.vinculo == TipoVinculo.BOLSISTA and self.bolsa_concedida is True:
            if dados_bancarios.exists():
                op = ' (Operação: ' + dados_bancarios[0].operacao + ') ' if dados_bancarios[0].operacao else ''
                return f'<span class="status status-info"><p>{dados_bancarios[0].banco}</p><p>Agência: {dados_bancarios[0].numero_agencia} {op}</p><p> Conta: {dados_bancarios[0].numero_conta}</p></span>'
            else:
                return '<span class="status status-error">Nenhuma conta bancária cadastrada.</span>'
        else:
            return '-'

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
            bolsa_concedida=self.bolsa_concedida,
        )

    def get_vinculo(self):
        if self.vinculo == TipoVinculo.BOLSISTA:
            return TipoVinculo.BOLSISTA
        else:
            return TipoVinculo.VOLUNTARIO

    def tem_historico_equipe(self):
        return HistoricoEquipe.objects.filter(participante=self, vinculo__isnull=False).exists()

    def pode_emitir_certificado_de_participacao(self):
        user = tl.get_user()
        status = self.projeto.get_status()
        pode_emitir = self.projeto.is_pre_avaliador() or self.projeto.is_gerenciador_projeto() or user.get_vinculo() == self.vinculo_pessoa
        return bool(
            pode_emitir
            and self.projeto.edital.imprimir_certificado
            and status == Projeto.STATUS_CONCLUIDO
            and self.tem_historico_equipe()
            and not self.projeto.inativado
        )

    def pode_emitir_declaracao_orientacao(self):
        status = self.projeto.get_status()
        return (
            self.projeto.is_gerenciador_projeto() and status in [Projeto.STATUS_CONCLUIDO, Projeto.STATUS_EM_EXECUCAO] and not self.projeto.inativado
        )

    def save(self, *args, **kwargs):
        super(self.__class__, self).save(*args, **kwargs)

        if self.responsavel:
            Projeto.objects.filter(id=self.projeto.id).update(vinculo_coordenador=self.vinculo_pessoa)
        if self.vinculo_pessoa:
            self.gerencia_bolsa_ae()

    @classmethod
    def gerar_bolsa_ae(cls, editais=None):
        """
        Gera bolsa no AE para tdas os alunos com vínculo bolsistas participantes de projetos arpovados cuja data inclusao_bolsas_ae do edital é nula

        Parâmetro editais recebe uma lista de ids dos editais
        """
        agora = datetime.datetime.now()
        if editais:
            qsedital = Edital.objects.filter(id__in=editais)
        else:
            qsedital = Edital.objects.filter(inclusao_bolsas_ae__isnull=True, divulgacao_selecao__lte=agora, data_avaliacao_classificacao__lte=agora)
        # Recupera todas as participacoes dos alunos cadastrados como bolsitas que ainda não possuem bolsa no ae
        qsparticipacoes = None
        contador_insert = 0
        contador_update = 0
        if qsedital.exists():
            edital_ids = qsedital.values_list('id', flat=True)
            qsparticipacoes = Participacao.objects.filter(
                projeto__edital__in=edital_ids,
                projeto__aprovado=True,
                ativo=True,
                vinculo=TipoVinculo.BOLSISTA,
                bolsa_concedida=True,
                # participacaobolsa__isnull = True,
                vinculo_pessoa__tipo_relacionamento__model='aluno',
            )
            print_(f'\t{qsparticipacoes.count():d} bolsas a serem processadas...')
            if qsparticipacoes and qsparticipacoes.exists():
                sid = transaction.savepoint()
                try:
                    for participacao in qsparticipacoes:
                        c1, c2 = participacao.gerencia_bolsa_ae()
                        contador_insert += c1
                        contador_update += c2
                    qsedital.update(inclusao_bolsas_ae=agora)
                    transaction.savepoint_commit(sid)
                    print_(f'\tBolsas geradas     : {contador_insert:d}')
                    print_(f'\tBolsas atualizadas : {contador_update:d}')
                except Exception:
                    transaction.savepoint_rollback(sid)
                    print_(f'\tErro, desfazendo {contador_insert:d} bolsas geradas  e {contador_update:d} bolsas atualizadas.\n\n')
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
            Existir uma bolsa previamente cadastrada no AE, participação inativa ou vínculo Voluntário
        """
        if self.is_servidor():
            return (0, 0)
        ParticipacaoBolsa = apps.get_model('ae', 'participacaobolsa')
        if ParticipacaoBolsa:
            CategoriaBolsa = apps.get_model('ae', 'categoriabolsa')
            contador_insert = 0
            contador_update = 0
            agora = datetime.datetime.now()
            editalProjeto = self.projeto.edital
            bolsa_ae = ParticipacaoBolsa.objects.none()
            if self.bolsa_no_ae:
                bolsa_ae = ParticipacaoBolsa.objects.filter(pk=self.bolsa_no_ae.id)

            eh_periodo_execucao_ou_encerrado = self.projeto.get_periodo() in (Projeto.PERIODO_EXECUCAO, Projeto.PERIODO_ENCERRADO)
            if (
                eh_periodo_execucao_ou_encerrado
                and self.ativo
                and self.vinculo == TipoVinculo.BOLSISTA
                and self.projeto.get_status() != Projeto.STATUS_CANCELADO
            ):
                if editalProjeto.divulgacao_selecao and editalProjeto.divulgacao_selecao <= agora:
                    categoria = CategoriaBolsa.objects.get(tipo_bolsa=CategoriaBolsa.TIPO_INICIACAO_CIENTIFICA)
                    try:
                        data_inicio = min(datetime.date.today(), self.projeto.fim_execucao)
                        qs_historico_equipe = HistoricoEquipe.objects.filter(participante=self)
                        if qs_historico_equipe.exists():
                            data_inicio = qs_historico_equipe.latest('id').data_movimentacao

                        aluno = Aluno.objects.get(id=self.vinculo_pessoa.id_relacionamento)

                        if not bolsa_ae.exists():
                            bolsa = ParticipacaoBolsa()
                            bolsa.aluno = aluno
                            bolsa.categoria = categoria
                            contador_insert += 1
                        else:
                            bolsa = bolsa_ae[0]
                            contador_update += 1
                        bolsa.data_inicio = data_inicio
                        bolsa.data_termino = self.projeto.fim_execucao
                        bolsa.save()
                        Participacao.objects.filter(id=self.id).update(bolsa_no_ae=bolsa)

                    except Exception:
                        raise
            else:
                if bolsa_ae.exists() and (
                    (not self.ativo or self.vinculo == TipoVinculo.VOLUNTARIO) or self.projeto.get_status() == Projeto.STATUS_CANCELADO
                ):
                    aluno_bolsista = bolsa_ae[0]
                    if not self.ativo and self.data_inativacao:
                        aluno_bolsista.data_termino = self.data_inativacao
                    else:
                        aluno_bolsista.data_termino = datetime.date.today()
                    aluno_bolsista.save()
                    contador_update += 1
            return (contador_insert, contador_update)
        return (0, 0)

    def get_historico_distribuicao_bolsa(self):
        return HistoricoEquipe.objects.filter(
            participante=self, tipo_de_evento__in=[HistoricoEquipe.EVENTO_CONCEDER_BOLSAR, HistoricoEquipe.EVENTO_NAOCONCEDER_BOLSA]
        )

    @classmethod
    def get_mensagem_aluno_nao_pode_ter_bolsa(cls, aluno, data):
        ParticipacaoBolsa = apps.get_model('ae', 'participacaobolsa')
        if ParticipacaoBolsa:
            AE_Participacao = apps.get_model('ae', 'participacao')
            aluno_tem_bolsa = ParticipacaoBolsa.objects.filter(Q(aluno=aluno) & (Q(data_termino__gt=data) | Q(data_termino__isnull=True)))
            if aluno_tem_bolsa:
                texto = ''
                if aluno_tem_bolsa[0].eh_pesquisa():
                    texto = f'(Projeto: {aluno_tem_bolsa[0].projeto_pesquisa().titulo})'
                elif aluno_tem_bolsa[0].aluno_participante_projeto:
                    texto = f'(Projeto: {aluno_tem_bolsa[0].aluno_participante_projeto.projeto.titulo})'
                if aluno_tem_bolsa[0].data_termino:
                    if aluno_tem_bolsa[0].data_termino > datetime.date.today():
                        return f'O(a) aluno(a) já possui bolsa. Só é possível a participação como voluntário. {texto}'
                else:
                    return f'O(a) aluno(a) já possui uma bolsa sem prazo final cadastrado. Apenas é possível participar como voluntário. {texto}'
            else:
                tem_bolsa_trabalho = AE_Participacao.objects.filter(
                    Q(aluno=aluno) & Q(programa__tipo='TRB') & (Q(data_termino__isnull=True) | Q(data_termino__gt=datetime.date.today()))
                ).exists()
                if tem_bolsa_trabalho:
                    return 'O aluno selecionado já possui uma bolsa de atividade profissional. Apenas é possível participar como voluntário.'
            return None
        return None

    def pode_emitir_plano_de_trabalho(self):
        user = tl.get_user()
        pode_emitir = self.projeto.is_pre_avaliador() or self.projeto.is_gerenciador_projeto() or user.get_vinculo() == self.vinculo_pessoa
        return bool(pode_emitir)

    def pode_emitir_declaracao_de_participacao(self):
        user = tl.get_user()
        status = self.projeto.get_status()
        pode_emitir = self.projeto.is_pre_avaliador() or self.projeto.is_gerenciador_projeto() or user.get_vinculo() == self.vinculo_pessoa
        return bool(pode_emitir and status in (Projeto.STATUS_EM_EXECUCAO, Projeto.STATUS_CONCLUIDO))

    def pode_remover_participacao(self):
        return bool(not self.responsavel and self.projeto.get_status() == Projeto.STATUS_EM_INSCRICAO)

    @classmethod
    def filtrar(cls, campus=None, ano_inicio=None, ano_fim=None):
        queryset = cls.objects.filter(projeto__aprovado=True)
        if campus:
            queryset = queryset.filter(projeto__uo=campus)
        if ano_inicio and ano_fim:
            queryset = queryset.filter(projeto__inicio_execucao__year__range=(ano_inicio, ano_fim))
        elif ano_inicio:
            queryset = queryset.filter(projeto__inicio_execucao__year__gte=ano_inicio)
        elif ano_fim:
            queryset = queryset.filter(projeto__inicio_execucao__year__lte=ano_fim)
        return queryset

    @classmethod
    def get_dados_quantitativos_de_participantes(cls, campus=None, ano_ini=None, ano_fim=None):
        """
        Retorna a quantidade de pessoas participando nos projetos
        :param campus:
        :param ano_ini:
        :param ano_fim:
        :return:
        """
        queryset = cls.filtrar(campus, ano_ini, ano_fim)
        dados = []
        alunos = Aluno.objects.filter(vinculos__in=queryset.values_list('vinculo_pessoa', flat=True)).distinct()
        docentes = Servidor.objects.filter(ativo=True, vinculos__id__in=queryset.values_list('vinculo_pessoa', flat=True), eh_docente=True).distinct()
        tecnicos_adm = Servidor.objects.filter(
            ativo=True, vinculos__id__in=queryset.values_list('vinculo_pessoa', flat=True), eh_tecnico_administrativo=True
        ).distinct()
        dados.append((Participacao.TIPOS_PESSOA['docente'], docentes.count()))
        dados.append((Participacao.TIPOS_PESSOA['tecnico_administrativo'], tecnicos_adm.count()))
        dados.append(('Discentes', alunos.count()))
        return dados


class FotoProjeto(models.ModelPlus):
    projeto = models.ForeignKeyPlus(Projeto, on_delete=models.CASCADE)
    legenda = models.TextField(blank=True)
    imagem = models.ImageFieldPlus(upload_to='upload/pesquisa/fotos/')

    class Meta:
        ordering = ['id']

    def save(self, *args, **kwargs):
        from PIL import Image

        super().save()
        old_name = self.imagem.name
        if self.imagem and default_storage.exists(old_name):
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
    carga_horaria = models.PositiveIntegerField('Carga Horária', help_text='Carga horária semanal', null=True, blank=True)
    tipo_de_evento = models.PositiveIntegerField(blank=True, choices=TIPOS_DE_EVENTOS)
    obs = models.CharField(max_length=1000, null=True)
    bolsa_concedida = models.BooleanField(null=True)

    class Meta:
        verbose_name = 'Histórico da Equipe'
        verbose_name_plural = 'Históricos das Equipes'

    def __str__(self):
        return f'Histórico de Participação - {self.participante}: {self.get_tipo_de_evento_display()}'

    def eh_bolsista(self):
        return self.vinculo == TipoVinculo.BOLSISTA and self.participante.bolsa_concedida is True

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
    meta = models.ForeignKeyPlus('pesquisa.Meta', verbose_name='Meta', related_name='etapa_set', on_delete=models.CASCADE)
    ordem = models.PositiveIntegerField('Ordem', help_text='Informe um número inteiro maior ou igual a 1')
    descricao = models.TextField('Descrição')
    indicadores_qualitativos = models.TextField('Resultados Esperados')
    responsavel = models.ForeignKeyPlus(
        Participacao, verbose_name='Responsável pela Atividade', related_name='pesquisa_participacao_responsavel', on_delete=models.CASCADE
    )
    integrantes = models.ManyToManyFieldPlus('pesquisa.Participacao', related_name='pesquisa_integrantes_set', blank=True)
    inicio_execucao = models.DateFieldPlus('Início da Execução', null=True)
    fim_execucao = models.DateFieldPlus('Fim da Execução', null=True)
    data_cadastro = models.DateFieldPlus('Data de Cadastro da Etapa', null=True, blank=True, default=datetime.datetime.now)

    class Meta:
        verbose_name = 'Atividade'
        verbose_name_plural = 'Atividades'

    def get_registro_execucao(self):
        qs = RegistroExecucaoEtapa.objects.filter(etapa=self).order_by('id')
        if qs:
            return qs[0]
        return None

    def get_status_execucao(self):
        qs = RegistroExecucaoEtapa.objects.filter(etapa=self)
        if qs.count():
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

    def pode_registrar_execucao(self):
        projeto = self.meta.projeto
        user = tl.get_user()
        status = projeto.get_status()
        tem_permissao_registrar_execucao = (
            projeto.is_gerenciador_projeto(user)
            or projeto.is_coordenador_pesquisa_campus_projeto(user)
            or (projeto.edital.responsavel_pode_registrar_execucao and self.responsavel.vinculo_pessoa == user.get_vinculo())
        )
        return bool(projeto.selecao_ja_divulgada() and (tem_permissao_registrar_execucao and status == Projeto.STATUS_EM_EXECUCAO))

    def get_integrantes(self):
        return ', '.join([registro.get_nome() for registro in self.integrantes.all()])


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
    operador = models.ForeignKeyPlus(
        Servidor, verbose_name='Operador', null=True, blank=True, related_name='pesquisa_historicoenvio_operado', on_delete=models.CASCADE
    )
    vinculo_operador = models.ForeignKeyPlus(
        Vinculo,
        verbose_name='Vínculo do Operador',
        null=True,
        blank=True,
        related_name='pesquisa_historicoenvio_vinculooperador',
        on_delete=models.CASCADE,
    )

    class Meta:
        verbose_name = 'Histórico do Envio de Projetos'
        verbose_name_plural = 'Históricos dos Envios de Projetos'


class ComissaoEditalPesquisa(models.ModelPlus):
    edital = models.ForeignKeyPlus(Edital, on_delete=models.CASCADE)
    uo = models.ForeignKeyPlus(
        UnidadeOrganizacional, verbose_name='Campus', null=True, blank=True, related_name='pesquisa_comissao_ano', on_delete=models.CASCADE
    )
    vinculos_membros = models.ManyToManyFieldPlus(
        'comum.Vinculo', verbose_name='Membros', blank=True, related_name='pesquisa_vinculos_membros_comissao_edital'
    )

    class Meta:
        verbose_name = 'Comissão de Avaliação'
        verbose_name_plural = 'Comissões de Avaliação'

    def __str__(self):
        if self.uo:
            return f'Comissão do {self.edital.titulo} (Campus {self.uo})'
        else:
            return f'Comissão do {self.edital.titulo}'

    def get_membros(self):
        string = ''
        for membro in self.vinculos_membros.all().order_by('pessoa__nome'):
            string = string + '<p>' + membro.pessoa.nome + '</p>'
        return string


class AvaliadorExterno(models.ModelPlus):
    nome = models.CharField('Nome', max_length=255)
    vinculo = models.OneToOneField('comum.Vinculo', related_name='pesquisa_avaliador_externo_vinculo', on_delete=models.CASCADE, null=True)
    ativo = models.BooleanField('Ativo', default=True)
    email = models.EmailField('Email')
    telefone = models.CharFieldPlus('Telefone', max_length=255, null=True, blank=True)
    titulacao = models.ForeignKeyPlus(
        'rh.Titulacao', verbose_name='Titulação', related_name='pesquisa_avaliador_instituicao', on_delete=models.CASCADE
    )
    instituicao_origem = models.ForeignKeyPlus(
        'rh.Instituicao', blank=True, null=True, verbose_name='Instituição', related_name='pesquisa_instituicao_avaliador', on_delete=models.CASCADE
    )
    lattes = models.URLField(blank=True)

    class Meta:
        verbose_name = 'Avaliador Externo'
        verbose_name_plural = 'Avaliadores Externos'

    def __str__(self):
        return str(self.nome)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        grupo = Group.objects.get(name='Avaliador Sistêmico de Projetos de Pesquisa')
        if self.ativo and grupo:
            self.vinculo.user.groups.add(grupo)
        else:
            self.vinculo.user.groups.remove(grupo)


class ProjetoCancelado(models.ModelPlus):
    projeto = models.ForeignKeyPlus(Projeto, on_delete=models.CASCADE)
    justificativa_cancelamento = models.CharField('Justificativa do Cancelamento', max_length=1000, null=True, blank=True)
    data_solicitacao = models.DateTimeFieldPlus('Data da Solicitação do Cancelamento')
    avaliador = models.ForeignKeyPlus(
        Servidor, verbose_name='Operador', null=True, blank=True, related_name='pesquisa_cancelamento_avaliador', on_delete=models.CASCADE
    )
    obs_avaliacao = models.CharField('Observação', max_length=500, null=True, blank=True)
    data_avaliacao = models.DateTimeFieldPlus('Data da Avaliação da Solicitação', null=True, blank=True)
    parecer_favoravel = models.BooleanField('Parecer Favorável', default=False)
    parecer_validacao = models.CharField('Parecer da PROPI', max_length=500, null=True, blank=True)
    data_validacao = models.DateTimeFieldPlus('Data da Validação', null=True, blank=True)
    cancelado = models.BooleanField('Cancelado', default=False)
    validador = models.ForeignKeyPlus(
        Servidor, verbose_name='Validador', null=True, blank=True, related_name='pesquisa_cancelamento_validador', on_delete=models.CASCADE
    )
    proximo_projeto = models.ForeignKeyPlus(Projeto, null=True, blank=True, related_name='proximo_projeto', on_delete=models.CASCADE)
    arquivo_comprovacao = models.FileFieldPlus(
        verbose_name='Comprovação', max_length=255, upload_to='upload/pesquisa/projeto/comprovacao_cancelamento/', null=True, blank=True
    )

    class Meta:
        verbose_name = 'Projeto Cancelado'
        verbose_name_plural = 'Projetos Cancelados'
        ordering = ['-data_solicitacao']

    def get_situacao(self):
        texto_retorno = ''
        if not self.data_avaliacao or not self.data_validacao:
            texto_retorno = '<span class="status status-alert">Não Avaliado</span>'
        elif not self.parecer_favoravel or (not self.cancelado and self.data_validacao):
            texto_retorno = '<span class="status status-error">Não Aceito</span>'
        else:
            texto_retorno = '<span class="status status-success">Aceito</span>'
        return texto_retorno

    def get_opcoes(self):
        user = tl.get_user()
        texto_retorno = '<ul class="action-bar">'
        if user.groups.filter(name='Coordenador de Pesquisa'):
            if not self.data_avaliacao:
                texto_retorno += f'<li><a href="/pesquisa/avaliar_cancelamento_projeto/{self.id}/" class="btn success">Avaliar</a></li>'
            elif not self.data_validacao:
                texto_retorno += f'<li><a class="btn primary" href="/pesquisa/avaliar_cancelamento_projeto/{self.id}/">Editar Avaliação</a></li>'
            else:
                texto_retorno += '<li>-</li>'

        else:
            if not self.data_validacao and self.parecer_favoravel:
                texto_retorno += f'<li><a href="/pesquisa/validar_cancelamento_projeto/{self.id}/" class="btn success">Validar</a></li>'
            elif self.parecer_favoravel:
                texto_retorno += f'<li><a class="btn primary" href="/pesquisa/validar_cancelamento_projeto/{self.id}/">Editar Validação</a></li>'
            else:
                texto_retorno += '<li>-</li>'

        texto_retorno += '</ul>'
        return texto_retorno


class RecursoProjeto(models.ModelPlus):
    projeto = models.ForeignKeyPlus(Projeto, on_delete=models.CASCADE)
    justificativa = models.CharField('Justificativa do Recurso', max_length=1000, null=True, blank=True)
    data_solicitacao = models.DateTimeFieldPlus('Data da Solicitação do Recurso')
    avaliador = models.ForeignKeyPlus(
        Servidor, verbose_name='Avaliador', related_name='projeto_avaliador_recurso_pesquisa', null=True, blank=True, on_delete=models.CASCADE
    )
    parecer = models.CharField('Parecer', max_length=500, null=True, blank=True)
    data_avaliacao = models.DateTimeFieldPlus('Data da Avaliação da Solicitação', null=True, blank=True)
    parecer_favoravel = models.BooleanField('Parecer Favorável', default=False)
    parecer_validacao = models.CharField('Parecer da PROPI', max_length=500, null=True, blank=True)
    aceito = models.BooleanField('Aceito', default=False)
    data_validacao = models.DateTimeFieldPlus('Data da Validação', null=True, blank=True)
    validador = models.ForeignKeyPlus(
        Servidor, verbose_name='Validador', related_name='projeto_validador_recurso_pesquisa', null=True, blank=True, on_delete=models.CASCADE
    )
    arquivo = models.PrivateFileField(verbose_name='Arquivo', upload_to='pesquisa/projetos/recursos', null=True, blank=True)

    class Meta:
        verbose_name = 'Recurso'
        verbose_name_plural = 'Recursos'
        ordering = ['-data_solicitacao']

    def get_situacao(self):
        texto_retorno = ''
        if not self.data_avaliacao or not self.data_validacao:
            texto_retorno = '<span class="status status-alert">Não Avaliado</span>'
        elif not self.parecer_favoravel or (not self.aceito and self.data_validacao):
            texto_retorno = '<span class="status status-error">Não Aceito</span>'
        else:
            texto_retorno = '<span class="status status-success">Aceito</span>'
        return texto_retorno

    def get_opcoes(self):
        user = tl.get_user()
        texto_retorno = '<ul class="action-bar">'
        if user.groups.filter(name='Coordenador de Pesquisa'):
            if not self.data_avaliacao:
                texto_retorno += f'<li><a href="/pesquisa/avaliar_recurso_projeto/{self.id}/" class="btn success">Avaliar</a></li>'
            elif not self.data_validacao:
                texto_retorno += f'<li><a class="btn" href="/pesquisa/avaliar_recurso_projeto/{self.id}/">Editar Avaliação</a></li>'
            else:
                texto_retorno += '<li>-</li>'

        else:
            if not self.data_validacao and self.parecer_favoravel:
                texto_retorno += f'<li><a href="/pesquisa/validar_recurso_projeto/{self.id}/" class="btn success">Validar</a></li>'
            elif self.parecer_favoravel:
                texto_retorno += f'<li><a class="btn" href="/pesquisa/validar_recurso_projeto/{self.id}/">Editar Validação</a></li>'
            else:
                texto_retorno += '<li>-</li>'

        texto_retorno += '</ul>'
        return texto_retorno


class EditalArquivo(models.ModelPlus):
    edital = models.ForeignKeyPlus(Edital, on_delete=models.CASCADE)
    nome = models.CharField('Nome', max_length=255)
    arquivo = models.FileFieldPlus(max_length=255, upload_to='upload/pesquisa/edital/', null=True, blank=True)
    data_cadastro = models.DateTimeFieldPlus('Data do Cadastro')
    vinculo_autor = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Autor', related_name='pesquisa_editalarquivo_vinculo', on_delete=models.CASCADE, null=True, blank=True
    )

    class Meta:
        ordering = ['-data_cadastro']


class LinhaEditorial(models.Model):
    nome = models.CharField('Nome', max_length=200, unique=True)
    ativa = models.BooleanField('Ativa', default=True)
    tipo_questionario = models.ForeignKeyPlus(
        'pesquisa.TipoQuestionarioObra', verbose_name='Tipo de Questionário', null=True, blank=True, on_delete=models.SET_NULL
    )

    class Meta:
        verbose_name = 'Linha Editorial'
        verbose_name_plural = 'Linhas Editoriais'

    def __str__(self):
        return self.nome


class EditalSubmissaoObra(models.Model):
    OBRA = 'Publicação de Obra'
    EVENTO = 'Publicação de Anais de Eventos'
    TIPO_PUBLICACAO_CHOICES = (
        (OBRA, OBRA),
        (EVENTO, EVENTO),
    )
    titulo = models.CharFieldPlus('Título', max_length=500)
    tipo = models.CharFieldPlus('Tipo de publicação', max_length=100, choices=TIPO_PUBLICACAO_CHOICES, default=OBRA)
    linha_editorial = models.ManyToManyFieldPlus(LinhaEditorial, verbose_name='Linha Editorial', blank=True)
    arquivo = models.FileFieldPlus('Arquivo do Edital', upload_to='private-media/pesquisa/editalsubmissaoobra/')
    data_inicio_submissao = models.DateTimeFieldPlus('Data de Início da Submissão')
    data_termino_submissao = models.DateTimeFieldPlus('Data de Término da Submissão')
    data_inicio_verificacao_plagio = models.DateTimeFieldPlus('Data de Início da Verificação de Plágio', null=True, blank=True)
    data_termino_verificacao_plagio = models.DateTimeFieldPlus('Data de Término da Verificação de Plágio', null=True, blank=True)
    data_inicio_analise_especialista = models.DateTimeFieldPlus('Data de Início de Análise de Especialista', null=True, blank=True)
    data_termino_analise_especialista = models.DateTimeFieldPlus('Data de Término de Análise de Especialista', null=True, blank=True)
    data_inicio_validacao_conselho = models.DateTimeFieldPlus('Data de Início de Validação do Conselho', null=True, blank=True)
    data_termino_validacao_conselho = models.DateTimeFieldPlus('Data de Término de Validação do Conselho', null=True, blank=True)
    data_inicio_aceite = models.DateTimeFieldPlus('Data de Início de Aceite')
    data_termino_aceite = models.DateTimeFieldPlus('Data de Término de Aceite')
    data_inicio_termos = models.DateTimeFieldPlus('Data de Início de Envio dos Termos', null=True, blank=True)
    data_termino_termos = models.DateTimeFieldPlus('Data de Término de Envio dos Termos', null=True, blank=True)
    data_inicio_revisao_linguistica = models.DateTimeFieldPlus('Data de Início de Revisão Linguística/Textual')
    data_termino_revisao_linguistica = models.DateTimeFieldPlus('Data de Término de Revisão Linguística/Textual')
    data_inicio_diagramacao = models.DateTimeFieldPlus('Data de Início de Diagramação')
    data_termino_diagramacao = models.DateTimeFieldPlus('Data de Término de Diagramação')
    data_inicio_solicitacao_isbn = models.DateTimeFieldPlus('Data de Início de Solicitação ISBN')
    data_termino_solicitacao_isbn = models.DateTimeFieldPlus('Data de Término de Solicitação ISBN')
    data_inicio_impressao_boneco = models.DateTimeFieldPlus('Data de Início de Impressão de Boneco')
    data_termino_impressao_boneco = models.DateTimeFieldPlus('Data de Término de Impressão de Boneco')
    data_revisao_layout = models.DateTimeFieldPlus('Data de Revisão de Layout', null=True, blank=True)
    data_inicio_correcao_final = models.DateTimeFieldPlus('Data de Início de Correção Final')
    data_termino_correcao_final = models.DateTimeFieldPlus('Data de Término de Correção Final')
    data_inicio_analise_liberacao = models.DateTimeFieldPlus('Data de Início de Análise de Liberação')
    data_termino_analise_liberacao = models.DateTimeFieldPlus('Data de Término de Análise de Liberação')
    data_inicio_impressao = models.DateTimeFieldPlus('Data de Início de Impressão')
    data_termino_impressao = models.DateTimeFieldPlus('Data de Término de Impressão')
    data_lancamento = models.DateTimeFieldPlus('Data de Lançamento', null=True, blank=True)
    local_lancamento = models.CharFieldPlus('Local de Lançamento', max_length=1000, null=True, blank=True)
    observacoes_lancamento = models.CharFieldPlus('Observações do Lançamento', max_length=1000, null=True, blank=True)
    instrucoes = HTMLField('Instruções para Submissão de Obra', null=True, blank=True)
    manual = models.FileFieldPlus('Manual do Autor', upload_to='private-media/pesquisa/editalsubmissaoobra/', null=True, blank=True)
    questionario_parecerista = models.FileFieldPlus(
        'Ficha de Avaliação para Parecerista', upload_to='private-media/pesquisa/editalsubmissaoobra/', null=True, blank=True
    )

    class Meta:
        verbose_name = 'Edital para Submissão de Publicações'
        verbose_name_plural = 'Editais para Submissão de Publicações'

    def __str__(self):
        return f'{self.titulo}'


class Obra(models.Model):
    AUTOR = 'Autor'
    ORGANIZADOR = 'Organizador'
    TIPO_AUTOR_CHOICES = ((AUTOR, AUTOR), (ORGANIZADOR, ORGANIZADOR))

    SEXO_CHOICES = (('Masculino', 'Masculino'), ('Feminino', 'Feminino'))
    ANAIS = 'Anais'
    EBOOK = 'Ebook'
    IMPRESSO = 'Impresso/Ebook'
    TIPO_SUBMISSAO_CHOICES = ((ANAIS, ANAIS), (EBOOK, EBOOK), (IMPRESSO, IMPRESSO))

    RECURSO_IMPRESSAO_CHOICES = (('Recurso próprio', 'Recurso próprio'), ('Edital', 'Edital'), ('Parceria', 'Parceria'))
    # ---------------------------
    SUBMETIDA = 'Submetida'
    AUTENTICA = 'Autêntica'
    CLASSIFICADA = 'Classificada'
    VALIDADA = 'Validada'
    ACEITA = 'Aceita'
    ASSINADA = 'Assinada'
    REVISADA = 'Revisada'
    DIAGRAMADA = 'Diagramada'
    REGISTRADA_ISBN = 'Registrada ISBN'
    CATALOGADA = 'Catalogada'
    CORRIGIDA = 'Corrigida'
    LIBERADA = 'Liberada'
    CONCLUIDA = 'Concluída'
    CANCELADA = 'Cancelada'
    REPROVADA = 'Reprovada'

    SITUACAO_OBRA_CHOICES = (
        (SUBMETIDA, SUBMETIDA),
        (AUTENTICA, AUTENTICA),
        (CLASSIFICADA, CLASSIFICADA),
        (VALIDADA, VALIDADA),
        (ACEITA, ACEITA),
        (ASSINADA, ASSINADA),
        (REVISADA, REVISADA),
        (DIAGRAMADA, DIAGRAMADA),
        (REGISTRADA_ISBN, REGISTRADA_ISBN),
        (CATALOGADA, CATALOGADA),
        (CORRIGIDA, CORRIGIDA),
        (LIBERADA, LIBERADA),
        (CONCLUIDA, CONCLUIDA),
        (CANCELADA, CANCELADA),
        (REPROVADA, REPROVADA),
    )

    FAVORAVEL = 'Favorável'
    FAVORAVEL_COM_RESSALVAS = 'Favorável com Ressalvas'
    NAO_FAVORAVEL = 'Não-Favorável'

    SITUACAO_CONSELHO_CHOICES = ((FAVORAVEL, FAVORAVEL), (FAVORAVEL_COM_RESSALVAS, FAVORAVEL_COM_RESSALVAS), (NAO_FAVORAVEL, NAO_FAVORAVEL))

    CAPA = 'Capa'
    MIOLO = 'Miolo'
    CAPA_E_MIOLO = 'Capa e Miolo'
    DIAGRAMACAO_CHOICES = ((CAPA, CAPA), (MIOLO, MIOLO), (CAPA_E_MIOLO, CAPA_E_MIOLO))

    SIM = 'Sim'
    NAO = 'Não'
    COM_RESSALVA = 'Com Ressalva'
    SITUACAO_AUTENTICIDADE_CHOICES = ((SIM, SIM), (COM_RESSALVA, COM_RESSALVA), (NAO, NAO))

    HABILITADA = 'Habilitada'
    NAO_HABILITADA = 'Não-habilitada'
    SITUACAO_ACEITE_EDITORA_CHOICES = ((HABILITADA, HABILITADA), (NAO_HABILITADA, NAO_HABILITADA))

    NAO_INICIADA = 'Não Iniciada'
    EM_ANDAMENTO = 'Em Andamento'
    SITUACAO_PUBLICACAO_CHOICES = ((NAO_INICIADA, NAO_INICIADA), (EM_ANDAMENTO, EM_ANDAMENTO), (CONCLUIDA, CONCLUIDA))
    LIBERACAO_CHOICES = ((SIM, SIM), (NAO, NAO))
    PERIODICIDADE_CHOICES = (
        ('Anual', 'Anual'),
        ('Bianual', 'Bianual'),
        ('Trianual', 'Trianual'),
        ('Outro/Especifique', 'Outro/Especifique'),
    )
    edital = models.ForeignKeyPlus(EditalSubmissaoObra, verbose_name='Edital', on_delete=models.CASCADE)
    tipo_autor = models.CharFieldPlus('Tipo', max_length=30, choices=TIPO_AUTOR_CHOICES)
    telefone = models.CharFieldPlus('Telefone', max_length=255, null=True, blank=True)
    termo_compromisso_autor_editora = models.FileFieldPlus(
        'Termo de Compromisso do Autor com a Editora', upload_to='private-media/pesquisa/arquivos_obra/', null=True, blank=True
    )
    titulo = models.CharFieldPlus('Título', max_length=1000)
    sinopse = models.CharFieldPlus('Sinopse', max_length=5000)
    sinopse_quarta_capa = models.CharFieldPlus('Sinopse para Quarta Capa', max_length=1050, null=True, blank=True)
    linha_editorial = models.ForeignKeyPlus(LinhaEditorial, verbose_name='Linha Editorial', on_delete=models.CASCADE, null=True)
    area = models.ForeignKeyPlus('rh.Areaconhecimento', verbose_name='Área', on_delete=models.CASCADE, null=True)
    nucleos_pesquisa = models.CharFieldPlus(
        'Núcleos de Pesquisa', max_length=1000, null=True, blank=True, help_text='Separe os nomes dos grupos por vírgula.'
    )
    tipo_submissao = models.CharFieldPlus('Tipo de Submissão', max_length=20, choices=TIPO_SUBMISSAO_CHOICES, null=True)
    recurso_impressao = models.CharFieldPlus(
        'Recurso para Impressão',
        max_length=20,
        choices=RECURSO_IMPRESSAO_CHOICES,
        null=True,
        blank=True,
        help_text='Se Recurso de Impressão for Próprio ou Parceria, devem ser entregues 4 exemplares da obra para a editora até Data de Término de Impressão',
    )
    arquivo = models.FileFieldPlus(
        'Obra Completa',
        max_file_size=104857600,
        upload_to='private-media/pesquisa/arquivos_obra/',
        help_text='O arquivo com a obra deve estar em formato Word. Outros formatos não serão aceitos. O arquivo Word poderá ser enviado de forma compactada (ZIP ou RAR).',
    )
    obra_sem_identificacao_autor = models.FileFieldPlus(
        'Obra Sem Identificação',
        max_file_size=104857600,
        upload_to='private-media/pesquisa/arquivos_obra/',
        help_text='O arquivo não deve ter nenhum dado que identifique a autoria e/ou organização da obra. O arquivo com a obra deve estar em formato Word. Outros formatos não serão aceitos. O arquivo Word poderá ser enviado de forma compactada (ZIP ou RAR).',
    )
    foto_autor_organizador = models.ImageFieldPlus('Foto do Autor/Organizador', null=True, upload_to='private-media/pesquisa/arquivos_obra/')
    biografia_autor_organizador = models.CharFieldPlus('Biografia do Autor/Organizador', max_length=660, null=True, blank=True)
    submetido_por_vinculo = models.ForeignKeyPlus('comum.Vinculo', related_name='pesquisa_submeteu_obra_vinculo', on_delete=models.CASCADE, null=True)
    responsavel_vinculo = models.ForeignKeyPlus(
        'comum.Vinculo', related_name='pesquisa_responsavel_obra_vinculo', null=True, blank=True, on_delete=models.CASCADE
    )
    submetido_em = models.DateTimeFieldPlus('Submetido em')
    situacao = models.CharFieldPlus('Situação', max_length=40, choices=SITUACAO_OBRA_CHOICES, default=SUBMETIDA)
    autentica = models.CharFieldPlus('Autêntica', max_length=40, choices=SITUACAO_AUTENTICIDADE_CHOICES, null=True, blank=True)
    autenticidade_verificada_por_vinculo = models.ForeignKeyPlus(
        'comum.Vinculo', related_name='pesquisa_autenticidade_verificada_vinculo', null=True, blank=True, on_delete=models.CASCADE
    )
    autenticidade_verificada_em = models.DateTimeFieldPlus('Plágio registrado em', null=True, blank=True)
    autenticidade_obs = models.CharFieldPlus('Observações', max_length=5000, null=True, blank=True)
    obra_corrigida = models.FileFieldPlus(
        'Obra Corrigida',
        upload_to='private-media/pesquisa/arquivos_obra/',
        max_file_size=104857600,
        help_text='O arquivo com a obra deve estar em formato Word. Outros formatos não serão aceitos. O arquivo Word poderá ser enviado de forma compactada (ZIP ou RAR).',
        null=True,
        blank=True,
    )
    situacao_conselho_editorial = models.CharFieldPlus(
        'Julgamento do Conselheiro Editorial', max_length=40, choices=SITUACAO_CONSELHO_CHOICES, null=True, blank=True
    )
    obs_conselho_editorial = HTMLField('Observação do Julgamento do Conselheiro Editorial', null=True, blank=True)
    julgamento_conselho_realizado_por_vinculo = models.ForeignKeyPlus(
        'comum.Vinculo', related_name='pesquisa_julgou_obra_vinculo', null=True, blank=True, on_delete=models.CASCADE
    )
    julgamento_conselho_realizado_em = models.DateTimeFieldPlus('Plágio registrado em', null=True)

    status_obra = models.CharFieldPlus('Situação da Obra', max_length=40, choices=SITUACAO_ACEITE_EDITORA_CHOICES, null=True, blank=True)
    aceita_editora_realizada_por_vinculo = models.ForeignKeyPlus(
        'comum.Vinculo', related_name='pesquisa_aceite_editora_obra_vinculo', null=True, on_delete=models.CASCADE
    )
    aceita_editora_realizada_em = models.DateTimeFieldPlus('Aceite pela editora realizada em', null=True)
    termo_autorizacao_publicacao = models.FileFieldPlus(
        'Termos de Autorização de Publicação', upload_to='private-media/pesquisa/arquivos_obra/', null=True, blank=True
    )
    termo_uso_imagem = models.FileFieldPlus(
        'Termos de Uso de Imagem, Voz e Texto', upload_to='private-media/pesquisa/arquivos_obra/', null=True, blank=True
    )
    termo_cessao_direitos_autorais = models.FileFieldPlus(
        'Termo de cessão de Direitos Autorais', upload_to='private-media/pesquisa/arquivos_obra/', null=True, blank=True
    )
    termo_nome_menor = models.FileFieldPlus(
        'Termo de Autorização para uso de Nome de Menor', upload_to='private-media/pesquisa/arquivos_obra/', null=True, blank=True
    )
    contrato_cessao_direitos = models.FileFieldPlus(
        'Contrato de Cessão e Transferência de Direitos Patrimoniais de Autor',
        upload_to='private-media/pesquisa/arquivos_obra/',
        null=True,
        blank=True,
    )
    termo_autorizacao_uso_imagem = models.FileFieldPlus(
        'Termo de Autorização para uso de Imagem e Fotografia', upload_to='private-media/pesquisa/arquivos_obra/', null=True, blank=True
    )
    termo_autorizacao_publicacao_assinado = models.CharFieldPlus(
        'Termo de Autorização de Publicação', max_length=40, choices=LIBERACAO_CHOICES, null=True, blank=True
    )
    termo_uso_imagem_assinado = models.CharFieldPlus(
        'Termo de Uso de Imagem, Voz e Texto', max_length=40, choices=LIBERACAO_CHOICES, null=True, blank=True
    )
    termo_cessao_direitos_autorais_assinado = models.CharFieldPlus(
        'Termo de cessão de Direitos Autorais', max_length=40, choices=LIBERACAO_CHOICES, null=True, blank=True
    )
    termo_nome_menor_assinado = models.CharFieldPlus(
        'Termo de Autorização para uso de Nome de Menor', max_length=40, choices=LIBERACAO_CHOICES, null=True, blank=True
    )
    contrato_cessao_direitos_assinado = models.CharFieldPlus(
        'Contrato de Cessão e Transferência de Direitos Patrimoniais de Autor', max_length=40, choices=LIBERACAO_CHOICES, null=True, blank=True
    )
    termo_autorizacao_uso_imagem_assinado = models.CharFieldPlus(
        'Termo de Autorização para uso de Imagem e Fotografia', max_length=40, choices=LIBERACAO_CHOICES, null=True, blank=True
    )
    termos_assinados_realizado_por_vinculo = models.ForeignKeyPlus(
        'comum.Vinculo', related_name='pesquisa_termo_assinado_vinculo', null=True, blank=True, on_delete=models.CASCADE
    )
    termos_assinados_realizado_em = models.DateTimeFieldPlus('Registro dos termos assinados em', null=True, blank=True)

    revisao_realizada_por_vinculo = models.ForeignKeyPlus(
        'comum.Vinculo', related_name='pesquisa_revisor_obra_vinculo', null=True, blank=True, on_delete=models.CASCADE
    )
    revisao_realizada_em = models.DateTimeFieldPlus('Revisão realizada em', null=True, blank=True)
    link_obra_revisada = models.CharFieldPlus('Link da Obra Revisada', null=True, blank=True, max_length=500)
    obs_revisor = models.CharFieldPlus('Observações do Revisor', null=True, blank=True, max_length=5000)
    arquivo_obra_revisada = models.FileFieldPlus(
        'Obra Revisada', max_file_size=104857600, null=True, blank=True, upload_to='pesquisa/obra/arquivo_revisada', max_length=255
    )
    revisada_pelo_autor = models.FileFieldPlus(
        'Obra Revisada pelo Autor', max_file_size=104857600, null=True, blank=True, upload_to='pesquisa/obra/revisada_autor', max_length=255
    )
    parecer_revisor = models.CharFieldPlus('Parecer do Revisor', null=True, blank=True, max_length=2000)
    correcoes_enviadas_em = models.DateTimeFieldPlus('Correções enviadas em', null=True, blank=True)
    versao_final_revisao = models.FileFieldPlus(
        'Versão Final da Revisão', max_file_size=104857600, null=True, blank=True, upload_to='pesquisa/obra/final', max_length=255
    )
    versao_final_revisao_em = models.DateTimeFieldPlus('Revisão Final em', null=True, blank=True)
    diagramacao_realizada_por_vinculo = models.ForeignKeyPlus(
        'comum.Vinculo', related_name='pesquisa_diagramador_vinculo', null=True, blank=True, on_delete=models.CASCADE
    )
    diagramacao_link = models.CharFieldPlus('Link da Diagramação', max_length=500, null=True, blank=True)
    justificativa_capa = models.CharFieldPlus('Justificativa', max_length=5000, null=True, blank=True)
    justificativa_miolo = models.CharFieldPlus('Justificativa', max_length=5000, null=True, blank=True)
    justificativa_capa_impresso = models.CharFieldPlus('Justificativa', max_length=5000, null=True, blank=True)
    justificativa_miolo_impresso = models.CharFieldPlus('Justificativa', max_length=5000, null=True, blank=True)
    obs_diagramador = models.CharFieldPlus('Observações do Diagramador', null=True, blank=True, max_length=5000)
    diagramacao_avaliada_em = models.DateTimeFieldPlus('Diagramação avaliada em', null=True, blank=True)
    diagramacao_concluida = models.BooleanField('Diagramação Concluída', default=False)
    diagramacao_capa_aprovada = models.CharFieldPlus('Aprovar Capa?', max_length=50, choices=LIBERACAO_CHOICES, null=True, blank=True)
    diagramacao_miolo_aprovada = models.CharFieldPlus('Aprovar Miolo', max_length=50, choices=LIBERACAO_CHOICES, null=True, blank=True)
    diagramacao_capa_aprovada_impresso = models.CharFieldPlus('Aprovar Capa?', max_length=50, choices=LIBERACAO_CHOICES, null=True, blank=True)
    diagramacao_miolo_aprovada_impresso = models.CharFieldPlus('Aprovar Miolo', max_length=50, choices=LIBERACAO_CHOICES, null=True, blank=True)
    obs_sobre_diagramacao = models.TextField('Observações do Autor/Organizador sobre a Diagramação', null=True, blank=True)
    arquivo_diagramacao_capa = models.FileFieldPlus(
        'Diagramação da Capa', max_file_size=104857600, null=True, blank=True, upload_to='pesquisa/obra/capa', max_length=255
    )
    arquivo_diagramacao_miolo = models.FileFieldPlus(
        'Diagramação do Miolo', max_file_size=104857600, null=True, blank=True, upload_to='pesquisa/obra/miolo', max_length=255
    )
    arquivo_diagramacao_capa_impresso = models.FileFieldPlus(
        'Diagramação da Capa', max_file_size=104857600, null=True, blank=True, upload_to='pesquisa/obra/capa_impresso', max_length=255
    )
    arquivo_diagramacao_miolo_impresso = models.FileFieldPlus(
        'Diagramação do Miolo', max_file_size=104857600, null=True, blank=True, upload_to='pesquisa/obra/miolo_impresso', max_length=255
    )
    arquivo_diagramacao_versao_final = models.FileFieldPlus(
        'Versão Final da Diagramação', max_file_size=104857600, null=True, blank=True, upload_to='pesquisa/obra/diagramacao_final', max_length=255
    )
    arquivo_diagramacao_versao_final_ebook = models.FileFieldPlus(
        'Versão Final(E-book)', max_file_size=104857600, null=True, blank=True, upload_to='pesquisa/obra/diagramacao_final', max_length=255
    )

    isbn = models.CharFieldPlus('ISBN', null=True, blank=True, max_length=30)
    isbn_impresso = models.CharFieldPlus('ISBN (Impresso)', null=True, blank=True, max_length=30)
    ficha_catalografica = models.FileFieldPlus('Ficha Catalográfica', null=True, blank=True, upload_to='private-media/pesquisa/arquivos_obra/')
    ficha_catalografica_impresso = models.FileFieldPlus(
        'Ficha Catalográfica (Impresso)', null=True, blank=True, upload_to='pesquisa/obra/ficha_impresso', max_length=255
    )
    situacao_publicacao = models.CharFieldPlus('Situação da Publicação', max_length=50, choices=SITUACAO_PUBLICACAO_CHOICES, default=NAO_INICIADA)
    num_copias = models.IntegerField('Número de Cópias', null=True, blank=True)
    data_envio_impressao = models.DateFieldPlus('Data de Envio para Impressão', null=True, blank=True)
    link_repositorio_virtual = models.CharFieldPlus('Link do Repositório Virtual', max_length=200, null=True, blank=True)
    data_liberacao_repositorio_virtual = models.DateFieldPlus(
        'Data de Liberação para Repositório Virtual',
        null=True,
        blank=True,
        help_text='Se não houver limite de data de liberação, informar data igual a hoje.',
    )
    bibliotecas_campi = models.CharFieldPlus('Bibliotecas dos Campi', max_length=1000, null=True, blank=True)
    acervo_fisico = models.CharFieldPlus('Acervo Físico da Editora', max_length=1000, null=True, blank=True)
    biblioteca_nacional = models.CharFieldPlus('Biblioteca Nacional', max_length=1000, null=True, blank=True)
    publicacao_autor = models.CharFieldPlus('Autor/Organizador', max_length=1000, null=True, blank=True)
    publicacao_coautor = models.CharFieldPlus('Coautor', max_length=1000, null=True, blank=True)
    aprovacao_liberacao_publicacao = models.CharFieldPlus('Aprovado', max_length=20, choices=LIBERACAO_CHOICES, null=True, blank=True)
    obs_liberacao_publicacao = models.CharFieldPlus('Parecer sobre a Liberação', max_length=5000, null=True, blank=True)

    cancelada_por_vinculo = models.ForeignKeyPlus(
        'comum.Vinculo', related_name='pesquisa_obra_cancelada_vinculo', null=True, blank=True, on_delete=models.CASCADE
    )
    cancelada_em = models.DateTimeFieldPlus('Cancelada em', null=True, blank=True)
    justificativa_cancelamento = models.TextField('Justificativa do Cancelamento', null=True)
    obra_concluida = models.FileFieldPlus(
        'Obra Concluída', max_file_size=104857600, null=True, blank=True, upload_to='pesquisa/obra/concluida', max_length=255
    )
    obra_concluida_em = models.DateFieldPlus('Obra Concluída em', null=True, blank=True)
    checklist_capa_nome_autor = models.BooleanField('Nome do Autor', default=False)
    checklist_capa_titulo = models.BooleanField('Título do Livro/Coleção ou Anais', default=False)
    checklist_capa_subtitulo = models.BooleanField('Subtítulo (quando houver)', default=False)
    checklist_capa_marca_editora = models.BooleanField('Marca da Editora', default=False)
    checklist_capa_marca_serie = models.BooleanField('Marca da Série (quando houver)', default=False)
    checklist_capa_marca_colecao = models.BooleanField('Marca da Coleção (quando houver)', default=False)
    checklist_orelha_texto_editora = models.BooleanField('Texto sobre a Editora', default=False)
    checklist_orelha_marca_editora = models.BooleanField('Marca da Editora', default=False)
    checklist_lombada_nome_autor = models.BooleanField('Nome do Autor', default=False)
    checklist_lombada_titulo = models.BooleanField('Título do Livro/Coleção ou Anais', default=False)
    checklist_lombada_marca_editora = models.BooleanField('Marca da Editora', default=False)
    checklist_quarta_capa_sinopse = models.BooleanField('Sinopse', default=False)
    checklist_quarta_capa_codigo_isbn = models.BooleanField('Código de Barras ISBN', default=False)
    checklist_quarta_capa_marca_instituicao = models.BooleanField('Marca Institucional', default=False)
    checklist_quarta_capa_abeu = models.BooleanField('Marca da ABEU', default=False)
    checklist_quarta_capa_comemorativa = models.BooleanField('Marca Comemorativa', default=False)
    checklist_orelha_verso_foto_autor = models.BooleanField('Foto do Autor (quando houver)', default=False)
    checklist_orelha_verso_nome_autor = models.BooleanField('Nome do Autor', default=False)
    checklist_orelha_verso_texto_autor = models.BooleanField('Texto sobre o Autor', default=False)
    checklist_folha_rosto_nome_autor = models.BooleanField('Nome do Autor', default=False)
    checklist_folha_rosto_titulo = models.BooleanField('Título do Livro/Coleção ou Anais', default=False)
    checklist_folha_rosto_subtitulo = models.BooleanField('Subtítulo (quando houver)', default=False)
    checklist_folha_rosto_editora = models.BooleanField('Marca da Editora', default=False)
    checklist_folha_rosto_cidade_ano = models.BooleanField('Cidade/Ano', default=False)
    checklist_ficha_tecnica_institucional = models.BooleanField('Institucional', default=False)
    checklist_ficha_tecnica_marca = models.BooleanField('Marca Institucional', default=False)
    checklist_ficha_tecnica_conselho = models.BooleanField('Conselho Editorial', default=False)
    checklist_ficha_tecnica_creditos = models.BooleanField('Créditos (rev./proj./imgs./ilus.)', default=False)
    checklist_ficha_tecnica_formato = models.BooleanField('Formato (E-book/Impresso)', default=False)
    checklist_ficha_tecnica_prefixo = models.BooleanField('Prefixo Editorial', default=False)
    checklist_ficha_tecnica_linha = models.BooleanField('Linha Editorial', default=False)
    checklist_ficha_tecnica_link = models.BooleanField('Link p/ Download', default=False)
    checklist_ficha_tecnica_marca_editora = models.BooleanField('Marca da Editora', default=False)
    checklist_ficha_tecnica_endereco = models.BooleanField('Endereço e contato da Editora', default=False)
    checklist_ficha_tecnica_edital = models.BooleanField('Texto referente ao Edital', default=False)
    checklist_ficha_catalografica_nome = models.BooleanField('Nome da Instituição', default=False)
    checklist_ficha_catalografica_titulo = models.BooleanField('Título do Livro ou Anais', default=False)
    checklist_ficha_catalografica_autores = models.BooleanField('Autores', default=False)
    checklist_ficha_catalografica_paginas = models.BooleanField('N° de Páginas', default=False)
    checklist_ficha_catalografica_ano = models.BooleanField('Ano de Publicação', default=False)
    checklist_miolo_prefacio = models.BooleanField('Prefácio', default=False)
    checklist_miolo_apresentacao = models.BooleanField('Apresentação', default=False)
    checklist_miolo_sumario = models.BooleanField('Sumário', default=False)
    checklist_miolo_sequencia = models.BooleanField('Sequência de Textos', default=False)
    checklist_miolo_num_paginas = models.BooleanField('Numeração de Páginas', default=False)
    checklist_miolo_titulos = models.BooleanField('Títulos Correntes e Seções', default=False)
    checklist_miolo_imagens = models.BooleanField('Verificação de Imagens', default=False)
    checklist_miolo_margens = models.BooleanField('Margens/alinhamentos', default=False)
    checklist_miolo_sangrias = models.BooleanField('Sangrias', default=False)
    checklist_miolo_alerta_reproducao = models.BooleanField('Alerta de Reprodução', default=False)
    checklist_pagina_final_marca = models.BooleanField('Marca da Editora', default=False)
    checklist_colofao_tipografias = models.BooleanField('Tipografias', default=False)
    checklist_colofao_papel_capa = models.BooleanField('Papel da Capa', default=False)
    checklist_colofao_papel_miolo = models.BooleanField('Papel do Miolo', default=False)
    checklist_colofao_grafica = models.BooleanField('Gráfica', default=False)
    checklist_colofao_copyright = models.BooleanField('Copyrights', default=False)
    checklist_revisao_ortografica = models.BooleanField('Ortográfica', default=False)
    checklist_revisao_linguistica = models.BooleanField('Linguística', default=False)
    checklist_revisao_normalizacao = models.BooleanField('Normalização', default=False)
    checklist_divulgacao_midias = models.BooleanField('Facebook/Instagram', default=False)
    checklist_divulgacao_convite_virtual = models.BooleanField('Convite Virtual', default=False)
    checklist_divulgacao_convite_impresso = models.BooleanField('Convite Impresso', default=False)
    checklist_divulgacao_repositorio = models.BooleanField('Repositório', default=False)
    checklist_tipo_arquivo_ebook = models.BooleanField('Versão E-book', default=False)
    checklist_tipo_arquivo_impresso = models.BooleanField('Versão Impressa', default=False)
    checklist_diagramador_capa_nome_autor = models.BooleanField('Nome do Autor', default=False)
    checklist_diagramador_capa_titulo = models.BooleanField('Título do Livro/Coleção ou Anais', default=False)
    checklist_diagramador_capa_subtitulo = models.BooleanField('Subtítulo (quando houver)', default=False)
    checklist_diagramador_capa_marca_editora = models.BooleanField('Marca da Editora', default=False)
    checklist_diagramador_capa_marca_serie = models.BooleanField('Marca da Série (quando houver)', default=False)
    checklist_diagramador_capa_marca_colecao = models.BooleanField('Marca da Coleção (quando houver)', default=False)
    checklist_diagramador_orelha_texto_editora = models.BooleanField('Texto sobre a Editora', default=False)
    checklist_diagramador_orelha_marca_editora = models.BooleanField('Marca da Editora', default=False)
    checklist_diagramador_lombada_nome_autor = models.BooleanField('Nome do Autor', default=False)
    checklist_diagramador_lombada_titulo = models.BooleanField('Título do Livro/Coleção ou Anais', default=False)
    checklist_diagramador_lombada_marca_editora = models.BooleanField('Marca da Editora', default=False)
    checklist_diagramador_quarta_capa_sinopse = models.BooleanField('Sinopse', default=False)
    checklist_diagramador_quarta_capa_codigo_isbn = models.BooleanField('Código de Barras ISBN', default=False)
    checklist_diagramador_quarta_capa_marca_instituicao = models.BooleanField('Marca Institucional', default=False)
    checklist_diagramador_quarta_capa_abeu = models.BooleanField('Marca da ABEU', default=False)
    checklist_diagramador_quarta_capa_comemorativa = models.BooleanField('Marca Comemorativa', default=False)
    checklist_diagramador_orelha_verso_foto_autor = models.BooleanField('Foto do Autor (quando houver)', default=False)
    checklist_diagramador_orelha_verso_nome_autor = models.BooleanField('Nome do Autor', default=False)
    checklist_diagramador_orelha_verso_texto_autor = models.BooleanField('Texto sobre o Autor', default=False)
    checklist_diagramador_folha_rosto_nome_autor = models.BooleanField('Nome do Autor', default=False)
    checklist_diagramador_folha_rosto_titulo = models.BooleanField('Título do Livro/Coleção ou Anais', default=False)
    checklist_diagramador_folha_rosto_subtitulo = models.BooleanField('Subtítulo (quando houver)', default=False)
    checklist_diagramador_folha_rosto_editora = models.BooleanField('Marca da Editora', default=False)
    checklist_diagramador_folha_rosto_cidade_ano = models.BooleanField('Cidade/Ano', default=False)
    checklist_diagramador_ficha_tecnica_institucional = models.BooleanField('Institucional', default=False)
    checklist_diagramador_ficha_tecnica_marca = models.BooleanField('Marca Institucional', default=False)
    checklist_diagramador_ficha_tecnica_conselho = models.BooleanField('Conselho Editorial', default=False)
    checklist_diagramador_ficha_tecnica_creditos = models.BooleanField('Créditos (rev./proj./imgs./ilus.)', default=False)
    checklist_diagramador_ficha_tecnica_formato = models.BooleanField('Formato (E-book/Impresso)', default=False)
    checklist_diagramador_ficha_tecnica_prefixo = models.BooleanField('Prefixo Editorial', default=False)
    checklist_diagramador_ficha_tecnica_linha = models.BooleanField('Linha Editorial', default=False)
    checklist_diagramador_ficha_tecnica_link = models.BooleanField('Link p/ Download', default=False)
    checklist_diagramador_ficha_tecnica_marca_editora = models.BooleanField('Marca da Editora', default=False)
    checklist_diagramador_ficha_tecnica_endereco = models.BooleanField('Endereço e contato da Editora', default=False)
    checklist_diagramador_ficha_tecnica_edital = models.BooleanField('Texto referente ao Edital', default=False)
    checklist_diagramador_ficha_catalografica_nome = models.BooleanField('Nome da Instituição', default=False)
    checklist_diagramador_ficha_catalografica_titulo = models.BooleanField('Título do Livro ou Anais', default=False)
    checklist_diagramador_ficha_catalografica_autores = models.BooleanField('Autores', default=False)
    checklist_diagramador_ficha_catalografica_paginas = models.BooleanField('N° de Páginas', default=False)
    checklist_diagramador_ficha_catalografica_ano = models.BooleanField('Ano de Publicação', default=False)
    checklist_diagramador_miolo_prefacio = models.BooleanField('Prefácio', default=False)
    checklist_diagramador_miolo_apresentacao = models.BooleanField('Apresentação', default=False)
    checklist_diagramador_miolo_sumario = models.BooleanField('Sumário', default=False)
    checklist_diagramador_miolo_sequencia = models.BooleanField('Sequência de Textos', default=False)
    checklist_diagramador_miolo_num_paginas = models.BooleanField('Numeração de Páginas', default=False)
    checklist_diagramador_miolo_titulos = models.BooleanField('Títulos Correntes e Seções', default=False)
    checklist_diagramador_miolo_imagens = models.BooleanField('Verificação de Imagens', default=False)
    checklist_diagramador_miolo_margens = models.BooleanField('Margens/alinhamentos', default=False)
    checklist_diagramador_miolo_sangrias = models.BooleanField('Sangrias', default=False)
    checklist_diagramador_pagina_final_marca = models.BooleanField('Marca da Editora', default=False)
    checklist_diagramador_colofao_tipografias = models.BooleanField('Tipografias', default=False)
    checklist_diagramador_colofao_papel_capa = models.BooleanField('Papel da Capa', default=False)
    checklist_diagramador_colofao_papel_miolo = models.BooleanField('Papel do Miolo', default=False)
    checklist_diagramador_colofao_grafica = models.BooleanField('Gráfica', default=False)
    checklist_diagramador_colofao_copyright = models.BooleanField('Copyrights', default=False)
    checklist_diagramador_divulgacao_midias = models.BooleanField('Facebook/Instagram', default=False)
    checklist_diagramador_divulgacao_convite_virtual = models.BooleanField('Convite Virtual', default=False)
    checklist_diagramador_divulgacao_convite_impresso = models.BooleanField('Convite Impresso', default=False)
    checklist_diagramador_divulgacao_repositorio = models.BooleanField('Repositório', default=False)
    checklist_diagramador_tipo_arquivo_ebook = models.BooleanField('Versão E-book', default=False)
    checklist_diagramador_tipo_arquivo_impresso = models.BooleanField('Versão Impressa', default=False)
    checklist_observacoes = models.TextField('Observações', null=True, blank=True)
    conselheiro_indicado_em = models.DateTimeFieldPlus('Conselheiro indicado em', null=True)
    revisor_indicado_em = models.DateTimeFieldPlus('Revisor indicado em', null=True)
    diagramador_indicado_em = models.DateTimeFieldPlus('Diagramador indicado em', null=True)
    diagramacao_final_em = models.DateTimeFieldPlus('Diagramação final em', null=True)
    isbn_cadastrado_em = models.DateTimeFieldPlus('ISBN cadastrado em', null=True)
    ficha_catalografica_cadastrada_em = models.DateTimeFieldPlus('Ficha catalográfica cadastrado em', null=True)

    # novos campos para publicação de anais em eventos
    nome_evento = models.CharFieldPlus('Título dos anais', null=True, blank=True, max_length=5000)
    data_evento = models.DateFieldPlus('Início do evento', null=True)
    data_fim_evento = models.DateFieldPlus('Fim do evento', null=True)
    local_evento = models.CharFieldPlus('Local do evento', null=True, max_length=5000)
    comissao_organizadora_evento = models.TextField('Nomes dos servidores da comissão organizadora', null=True)
    comissao_cientifica_evento = models.TextField('Nomes dos servidores da comissão científica', null=True)
    edicao_evento = models.CharFieldPlus('Edição do evento', null=True, max_length=500)
    periodicidade_evento = models.CharFieldPlus('Periodicidade do evento', null=True, max_length=500, choices=PERIODICIDADE_CHOICES)
    periodicidade_outro_evento = models.CharFieldPlus('Periodicidade (outro) do evento', null=True, blank=True, max_length=5000)
    issn_evento = models.CharFieldPlus('ISSN do evento', null=True, blank=True, max_length=5000)
    isbn_evento = models.CharFieldPlus('ISBN do evento', null=True, blank=True, max_length=5000)
    artigo_evento = models.FileFieldPlus(
        'Arquivo completo (PDF)',
        max_file_size=104857600,
        null=True,
        upload_to='private-media/pesquisa/arquivos_obra/',
        help_text='O arquivo com a obra deve estar em formato PDF. Outros formatos não serão aceitos.',
    )
    artigo_doc_evento = models.FileFieldPlus(
        'Arquivo completo (DOC/Word)',
        max_file_size=104857600,
        null=True,
        upload_to='private-media/pesquisa/arquivos_obra/',
        help_text='O arquivo com a obra deve estar em formato DOC/DOCX. Outros formatos não serão aceitos.',
    )
    logo_evento = models.ImageFieldPlus('Logo do Evento', null=True, blank=True, upload_to='private-media/pesquisa/arquivos_obra/')
    obs_evento = models.TextField('Observações', null=True, blank=True)

    class Meta:
        verbose_name = 'Obra'
        verbose_name_plural = 'Submissões para Publicação'

        permissions = (
            ('pode_avaliar_obra', 'Pode avaliar obra'),
            ('pode_validar_obra', 'Pode validar obra'),
            ('pode_revisar_obra', 'Pode revisar obra'),
            ('pode_diagramar_obra', 'Pode diagramar obra'),
            ('pode_gerar_ficha_catalografica', 'Pode gerar ficha catalográfica'),
        )

    def __str__(self):
        return f'{self.titulo} - {self.linha_editorial}'

    def get_avaliacao_conselho_editorial(self):
        if self.situacao_conselho_editorial == self.FAVORAVEL:
            return '<span class="status status-success">Favorável</span>'
        elif self.situacao_conselho_editorial == self.NAO_FAVORAVEL:
            return '<span class="status status-error">Não-Favorável</span>'
        elif self.situacao_conselho_editorial == self.FAVORAVEL_COM_RESSALVAS:
            return '<span class="status status-alert">Favorável com Ressalvas</span>'
        else:
            return '<span class="status status-alert">Aguardando avaliação</span>'

    def eh_ativa(self):
        return self.situacao != Obra.CANCELADA

    def eh_autentica(self):
        return self.eh_ativa() and (self.autentica in [Obra.SIM, Obra.COM_RESSALVA] or self.edital.tipo == EditalSubmissaoObra.EVENTO)

    def foi_aprovada(self):
        return self.eh_ativa() and ParecerObra.objects.filter(obra=self, situacao=ParecerObra.APROVADA).exists()

    def tem_parecer(self):
        return self.eh_ativa() and ParecerObra.objects.filter(obra=self, parecer_realizado_em__isnull=False).exists()

    def foi_validada(self):
        return self.eh_ativa() and (
            self.situacao_conselho_editorial == Obra.FAVORAVEL
            or (self.status_obra == Obra.HABILITADA and self.edital.tipo == EditalSubmissaoObra.EVENTO)
        )

    def foi_aceita(self):
        return self.eh_ativa() and self.status_obra == Obra.HABILITADA

    def tem_conselheiro_indicado(self):
        return self.eh_ativa() and self.julgamento_conselho_realizado_por_vinculo

    def tem_parecerista(self):
        return self.eh_ativa() and ParecerObra.objects.filter(obra=self).exists()

    def foi_assinada(self):
        return self.eh_ativa() and self.termo_autorizacao_publicacao_assinado == Obra.SIM and self.termo_cessao_direitos_autorais_assinado == Obra.SIM

    def foi_revisada(self):
        return self.eh_ativa() and self.parecer_revisor

    def tem_diagramacao(self):
        return self.arquivo_diagramacao_capa and self.arquivo_diagramacao_miolo

    def tem_diagramacao_avaliada(self):
        return bool(self.diagramacao_avaliada is False or self.diagramacao_avaliada is True)

    def foi_concluida(self):
        return self.situacao in [Obra.CANCELADA, Obra.CONCLUIDA]

    def pode_cadastrar_autores(self):
        hoje = datetime.datetime.now()
        return self.edital.data_inicio_submissao <= hoje <= self.edital.data_termino_submissao and self.situacao == Obra.SUBMETIDA

    def dentro_prazo_verifica_plagio(self):
        hoje = datetime.datetime.now()
        return self.edital.data_inicio_verificacao_plagio <= hoje <= self.edital.data_termino_verificacao_plagio

    def dentro_prazo_avaliar_obra(self):
        hoje = datetime.datetime.now()
        return self.edital.data_inicio_analise_especialista <= hoje <= self.edital.data_termino_analise_especialista

    def dentro_prazo_validacao(self):
        hoje = datetime.datetime.now()
        return self.edital.data_inicio_validacao_conselho <= hoje <= self.edital.data_termino_validacao_conselho

    def dentro_prazo_aceite(self):
        hoje = datetime.datetime.now()
        return self.edital.data_inicio_aceite <= hoje <= self.edital.data_termino_aceite

    def dentro_prazo_envio_termos(self):
        hoje = datetime.datetime.now()
        return self.edital.data_inicio_termos <= hoje <= self.edital.data_termino_termos

    def dentro_prazo_revisao(self):
        hoje = datetime.datetime.now()
        return self.edital.data_inicio_revisao_linguistica <= hoje <= self.edital.data_termino_revisao_linguistica

    def dentro_prazo_diagramacao(self):
        hoje = datetime.datetime.now()
        return self.edital.data_inicio_diagramacao <= hoje <= self.edital.data_termino_diagramacao

    def eh_periodo_pedido_isbn(self):
        hoje = datetime.datetime.now()
        return self.edital.data_inicio_solicitacao_isbn <= hoje <= self.edital.data_termino_solicitacao_isbn

    def get_periodicidade_evento(self):
        return self.periodicidade_outro_evento or self.periodicidade_evento

    def tem_analise_habilitada(self):
        return self.situacao_conselho_editorial or (self.status_obra == 'Habilitada' and self.edital.tipo == EditalSubmissaoObra.EVENTO)


class MembroObra(models.Model):
    AUTOR = 'Autor'
    ORGANIZADOR = 'Organizador'
    COAUTOR = 'Coautor'

    TIPO_AUTOR_CHOICES = ((AUTOR, AUTOR), (COAUTOR, COAUTOR), (ORGANIZADOR, ORGANIZADOR))

    SEXO_CHOICES = (('Masculino', 'Masculino'), ('Feminino', 'Feminino'))

    obra = models.ForeignKeyPlus(Obra, verbose_name='Obra', on_delete=models.CASCADE)
    tipo_autor = models.CharFieldPlus('Tipo', max_length=30, choices=TIPO_AUTOR_CHOICES)
    nome = models.CharFieldPlus('Nome', max_length=1000)
    endereco = models.CharFieldPlus('Endereço', max_length=1000, null=True)
    complemento = models.CharFieldPlus('Complemento', max_length=1000, null=True)
    bairro = models.CharFieldPlus('Bairro', max_length=100, null=True)
    cidade = models.ForeignKeyPlus('edu.Cidade', verbose_name='Cidade', on_delete=models.CASCADE, null=True)
    cep = models.CharFieldPlus('CEP', max_length=20, null=True)
    rg = models.CharFieldPlus('RG', max_length=15, null=True)
    rg_orgao_emissor = models.CharFieldPlus('Órgão Emissor', max_length=15, null=True)
    cpf = models.CharFieldPlus(verbose_name='CPF', max_length=15, null=True)
    sexo = models.CharFieldPlus('Sexo', max_length=20, choices=SEXO_CHOICES, null=True)
    estado_civil = models.ForeignKeyPlus(
        'comum.EstadoCivil', related_name='estado_civil_membroobra', verbose_name='Estado Civil', help_text='', on_delete=models.CASCADE, null=True
    )
    profissao = models.CharFieldPlus('Profissão', max_length=500, null=True)
    email = models.CharFieldPlus('Email', max_length=500)
    telefone = models.CharFieldPlus('Telefone', max_length=255)
    foto = models.ImageFieldPlus('Foto', null=True, upload_to='private-media/pesquisa/arquivos_obra/')
    biografia = models.CharFieldPlus('Biografia', max_length=660, null=True, blank=True)

    class Meta:
        verbose_name = 'Membro da Obra'
        verbose_name_plural = 'Membros da Obra'

    def __str__(self):
        return f'{self.nome} - {self.cpf}'


class ParecerObra(models.Model):
    EM_ANALISE = 'Em análise'

    APROVADA_RESSALVA = 'Aprovada com ressalvas'
    APROVADA = 'Aprovada'
    REPROVADA = 'Reprovada'
    SITUACAO_PARECER_AREA_CHOICES = ((APROVADA, APROVADA), (APROVADA_RESSALVA, APROVADA_RESSALVA), (REPROVADA, REPROVADA))
    obra = models.ForeignKeyPlus(Obra, related_name='parecer_obra', on_delete=models.CASCADE)
    indicado_em = models.DateTimeFieldPlus('Parecerista indicado em', null=True, blank=True)
    situacao = models.CharFieldPlus('Avaliação', max_length=40, choices=SITUACAO_PARECER_AREA_CHOICES, default=EM_ANALISE)
    nota = models.DecimalFieldPlus('Nota', null=True, blank=True)
    comentario = HTMLField('Observações Complementares', null=True, blank=True)
    arquivo_parecer_area = models.FileFieldPlus('Parecer', null=True, blank=True, upload_to='pesquisa/obra/parecer', max_length=255)
    parecer_realizado_por_vinculo = models.ForeignKeyPlus(
        'comum.Vinculo', related_name='pesquisa_parecer_obra_vinculo', on_delete=models.CASCADE, null=True
    )
    parecer_realizado_em = models.DateTimeFieldPlus('Parecer realizado em', null=True, blank=True)
    recusou_indicacao = models.BooleanField('Recusou Indicação', default=False)
    aceitou_indicacao = models.BooleanField('Aceitou Indicação', default=False)
    analise_indicacao_em = models.DateTimeFieldPlus('Avaliou a indicação em', null=True, blank=True)

    class Meta:
        verbose_name = 'Parecer da Obra'
        verbose_name_plural = 'Pareceres da Obra'

    def __str__(self):
        return f'{self.situacao} por {self.parecer_realizado_por_vinculo}'

    def get_areas_conhecimento_parecerista(self):
        if self.parecer_realizado_por_vinculo.eh_servidor():
            return self.parecer_realizado_por_vinculo.relacionamento.areas_de_conhecimento.all()
        else:
            if AreaConhecimentoParecerista.objects.filter(parecerista=self.parecer_realizado_por_vinculo.relacionamento).exists():
                return AreaConhecimentoParecerista.objects.filter(parecerista=self.parecer_realizado_por_vinculo.relacionamento)[
                    0
                ].areas_de_conhecimento.all()
        return None

    def get_historico(self):
        registros = ParecerObra.objects.filter(
            parecer_realizado_por_vinculo=self.parecer_realizado_por_vinculo, indicado_em__isnull=False, parecer_realizado_em__isnull=False
        ).only('parecer_realizado_em', 'indicado_em')
        if not registros.exists():
            return 'Nenhum parecer emitido.'
        else:
            tempo = 0
            for registro in registros:
                tempo += (registro.parecer_realizado_em - registro.indicado_em).total_seconds()
            total_registros = registros.count()
            em_minutos = int((tempo / total_registros) / 60)
            em_horas = int(em_minutos / 60)
            em_dias = int(em_horas / 24)
            if em_dias:
                return mark_safe(
                    '<strong>{}</strong> parecer{} emitido{}. Tempo médio de avaliação: <strong>{} hora{}</strong> ({} dia{})'.format(
                        total_registros,
                        pluralize(total_registros, 'es'),
                        pluralize(total_registros),
                        em_horas,
                        pluralize(em_horas),
                        em_dias,
                        pluralize(em_dias),
                    )
                )
            elif em_horas:
                return mark_safe(
                    f'<strong>{total_registros}</strong> parecer(es) emitido(s). Tempo médio de avaliação: <strong>{em_horas} hora{pluralize(em_horas)}</strong>'
                )
            else:
                return mark_safe(
                    f'<strong>{total_registros}</strong> parecer(es) emitido(s). Tempo médio de avaliação: <strong>{em_minutos} minutos</strong>'
                )

    def indicacao_foi_aceita(self):
        return not self.recusou_indicacao and self.aceitou_indicacao

    def indicacao_foi_negada(self):
        return self.recusou_indicacao


class PessoaExternaObra(models.ModelPlus):
    SEXO_CHOICES = (('Masculino', 'Masculino'), ('Feminino', 'Feminino'))

    nome = models.CharField('Nome', max_length=255)
    pessoa_fisica = models.OneToOneField('comum.PrestadorServico', related_name='pesquisa_editora_pessoa', on_delete=models.CASCADE)
    endereco = models.CharFieldPlus('Endereço', max_length=1000)
    complemento = models.CharFieldPlus('Complemento', max_length=1000, null=True, blank=True)
    bairro = models.CharFieldPlus('Bairro', max_length=100)
    cidade = models.ForeignKeyPlus('edu.Cidade', verbose_name='Cidade', on_delete=models.CASCADE)
    cep = models.CharFieldPlus('CEP', max_length=20)
    rg = models.CharFieldPlus('RG', max_length=15)
    rg_orgao_emissor = models.CharFieldPlus('Órgão Emissor', max_length=15)
    cpf = models.CharFieldPlus(verbose_name='CPF', max_length=15)
    sexo = models.CharFieldPlus('Sexo', max_length=20, choices=SEXO_CHOICES)
    estado_civil = models.ForeignKeyPlus(
        'comum.EstadoCivil', related_name='estado_civil_pessoaexterna', verbose_name='Estado Civil', help_text='', on_delete=models.CASCADE
    )
    profissao = models.CharFieldPlus('Profissão', max_length=500)
    instituicao_origem = models.ForeignKeyPlus(
        'rh.Instituicao',
        blank=True,
        null=True,
        verbose_name='Instituição',
        related_name='pesquisa_instituicao_pessoaexterna',
        on_delete=models.CASCADE,
    )
    email = models.CharFieldPlus('Email', max_length=500)
    telefone = models.CharFieldPlus('Telefone', max_length=255)
    validado_em = models.DateTimeFieldPlus('Validado em', null=True)
    validado_por = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Avaliada por', null=True, blank=True, related_name='pesquisa_validador_pessoaexterna'
    )
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Pessoa Externa'
        verbose_name_plural = 'Pessoas Externas'

    def __str__(self):
        return str(self.nome)

    def get_areas_conhecimento(self):
        if AreaConhecimentoParecerista.objects.filter(parecerista=self.pessoa_fisica).exists():
            return AreaConhecimentoParecerista.objects.filter(parecerista=self.pessoa_fisica)[0].areas_de_conhecimento.all()
        return None


class LaboratorioPesquisa(models.ModelPlus):
    TIPO_LABORATORIO_CHOICES = (
        ('Laboratório de PD&I especializado', 'Laboratório de PD&I especializado'),
        ('Laboratório maker', 'Laboratório maker'),
        ('Centro de tecnologia', 'Centro de tecnologia'),
        ('Polo de inovação', 'Polo de inovação'),
    )
    nome = models.CharField('Nome', max_length=1000)
    coordenador = models.ForeignKeyPlus('rh.Servidor', verbose_name='Coordenador', on_delete=models.CASCADE)
    uo = models.ForeignKeyPlus('rh.UnidadeOrganizacional', verbose_name='Campus', on_delete=models.CASCADE)
    tipo = models.CharFieldPlus('Tipo de laboratório multiusuário', choices=TIPO_LABORATORIO_CHOICES, null=True)
    descricao = models.CharField('Descrição', max_length=5000, null=True, blank=True)
    contato = models.CharField('Contato', max_length=5000, null=True, blank=True)
    area_pesquisa = models.ForeignKeyPlus('rh.AreaConhecimento', verbose_name='Área de Pesquisa', on_delete=models.CASCADE, null=True)
    sala = models.ForeignKeyPlus('comum.Sala', verbose_name='Sala', on_delete=models.CASCADE, null=True)
    servicos_realizados = models.CharField('Serviços Realizados', max_length=10000, null=True, blank=True)
    horario_funcionamento = models.CharField('Horário de Funcionamento', max_length=1000, null=True, blank=True)
    membros = models.ManyToManyFieldPlus('comum.Vinculo', verbose_name='Membros')
    aprovado = models.BooleanField(verbose_name='Aprovado', null=True)
    avaliado_por = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Avaliado por', null=True, blank=True, related_name='pesquisa_avaliacao_laboratoriomultiusuario'
    )
    avaliado_em = models.DateTimeFieldPlus(verbose_name='Avaliado em', null=True)
    justificativa = models.CharFieldPlus(verbose_name='Justificativa', max_length=1000, null=True, blank=True)

    class Meta:
        verbose_name = 'Laboratório Multiusuário'
        verbose_name_plural = 'Laboratórios Multiusuários'

    def __str__(self):
        return str(self.nome)

    @transaction.atomic
    def save(self, *args, **kwargs):
        pk = self.pk
        super().save(*args, **kwargs)
        if pk is None:
            self.aprovado = None
            user = tl.get_user()
            if user.groups.filter(name='Diretor de Pesquisa'):
                self.aprovado = True
            self.save()


class FotoLaboratorioPesquisa(models.ModelPlus):
    descricao = models.CharField('Descrição', max_length=1000)
    laboratorio = models.ForeignKeyPlus(LaboratorioPesquisa, verbose_name='Laboratório')
    imagem = models.ImageFieldPlus(upload_to='upload/pesquisa/fotos/')

    class Meta:
        verbose_name = 'Foto do Laboratório de Pesquisa'
        verbose_name_plural = 'Fotos do Laboratório de Pesquisa'

    def __str__(self):
        return str(self.descricao)


class EquipamentoLaboratorioPesquisa(models.ModelPlus):
    OPERACIONAL = 'Operacional'
    SITUACAO_EQUIPAMENTO_CHOICES = (
        (OPERACIONAL, OPERACIONAL),
        ('Não-Operacional', 'Não-Operacional'),
        ('Manutenção', 'Manutenção'),
        ('Desenvolvimento', 'Desenvolvimento'),
    )
    nome = models.CharFieldPlus('Nome', max_length=200, null=True)
    descricao = models.CharField('Descrição', max_length=5000)
    patrimonio = models.ForeignKeyPlus('patrimonio.Inventario', verbose_name='Inventário', on_delete=models.CASCADE, null=True)
    situacao = models.CharFieldPlus('Situação', max_length=150, choices=SITUACAO_EQUIPAMENTO_CHOICES, default=OPERACIONAL)
    laboratorio = models.ForeignKeyPlus(LaboratorioPesquisa, verbose_name='Laboratório')
    imagem = models.ImageFieldPlus(upload_to='upload/pesquisa/fotos/', null=True)

    class Meta:
        verbose_name = 'Equipamento do Laboratório de Pesquisa'
        verbose_name_plural = 'Equipamentos do Laboratório de Pesquisa'

    def __str__(self):
        return str(self.descricao)


class ServicoLaboratorioPesquisa(models.ModelPlus):
    descricao = models.CharField('Descrição', max_length=5000)
    equipamentos = models.ManyToManyFieldPlus(EquipamentoLaboratorioPesquisa, verbose_name='Equipamentos Utilizados')
    materiais_utilizados = models.CharField('Materiais Utilizados', max_length=5000, null=True)
    ativo = models.BooleanField('Ativo', default=True)
    laboratorio = models.ForeignKeyPlus(LaboratorioPesquisa, verbose_name='Laboratório')
    id_do_processo_eletronico = models.PositiveIntegerField(verbose_name='ID do Processo Eletrônico', null=True)

    class Meta:
        verbose_name = 'Serviço do Laboratório de Pesquisa'
        verbose_name_plural = 'Serviços do Laboratório de Pesquisa'

    def __str__(self):
        return str(self.descricao)


class MaterialConsumoPesquisa(models.ModelPlus):
    descricao = models.CharField('Descrição', max_length=5000)
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Material de Consumo de Pesquisa'
        verbose_name_plural = 'Materiais de Consumo de Pesquisa'

    def __str__(self):
        return str(self.descricao)


class MaterialLaboratorioPesquisa(models.ModelPlus):
    material = models.ForeignKeyPlus(MaterialConsumoPesquisa, verbose_name='Material')
    quantidade = models.CharFieldPlus('Quantidade em Estoque', max_length=100)
    valor_unitario = models.DecimalFieldPlus('Valor Unitário (R$)')
    imagem = models.ImageFieldPlus(upload_to='upload/pesquisa/fotos/', null=True)
    laboratorio = models.ForeignKeyPlus(LaboratorioPesquisa, verbose_name='Laboratório')

    class Meta:
        verbose_name = 'Material do Laboratório de Pesquisa'
        verbose_name_plural = 'Materiais do Laboratório de Pesquisa'

    def __str__(self):
        return str(self.material)


class AreaConhecimentoParecerista(models.ModelPlus):
    parecerista = models.ForeignKeyPlus('comum.PrestadorServico', verbose_name='Parecerista', on_delete=models.CASCADE)
    areas_de_conhecimento = models.ManyToManyFieldPlus('rh.AreaConhecimento', blank=True)

    class Meta:
        verbose_name = 'Área de Conhecimento do Parecerista'
        verbose_name_plural = 'Áreas de Conhecimento do Parecerista'

    def __str__(self):
        return 'Áreas de Conhecimento'


class SolicitacaoAlteracaoEquipe(models.ModelPlus):
    projeto = models.ForeignKeyPlus(Projeto, on_delete=models.CASCADE)
    descricao = models.CharFieldPlus(verbose_name='Descrição da Alteração', max_length=2000)
    cadastrada_por = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Cadastrado por', null=True, blank=True, related_name='pesquisa_cadastro_alteracaoequipe'
    )
    cadastrada_em = models.DateTimeFieldPlus(verbose_name='Cadastrado em', null=True)
    atendida = models.BooleanField(verbose_name='Atendida', null=True)
    avaliada_por = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Avaliada por', null=True, blank=True, related_name='pesquisa_avaliacao_alteracaoequipe'
    )
    avaliada_em = models.DateTimeFieldPlus(verbose_name='Avaliada em', null=True)
    justificativa = models.CharFieldPlus(verbose_name='Justificativa', max_length=1000, null=True, blank=True)

    class Meta:
        verbose_name = 'Solicitação de Alteração da Equipe'
        verbose_name_plural = 'Solicitações de Alteração da Equipe'

    def __str__(self):
        return 'Solicitação de Alteração da Equipe'

    def get_situacao(self):
        if self.atendida is None:
            return '<span class="status status-alert">Aguardando avaliação</span>'
        elif self.atendida:
            return '<span class="status status-success">Atendida</span>'
        else:
            return '<span class="status status-rejeitado">Não atendida</span>'


class RegistroFrequencia(models.ModelPlus):
    projeto = models.ForeignKeyPlus(Projeto, on_delete=models.CASCADE)
    descricao = models.CharFieldPlus(verbose_name='Descrição', max_length=2000)
    data = models.DateFieldPlus('Data')
    carga_horaria = models.PositiveIntegerField('Carga Horária', null=True, blank=True)
    cadastrada_por = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Cadastrado por', null=True, blank=True, related_name='pesquisa_cadastro_registrofrequencia'
    )
    cadastrada_em = models.DateTimeFieldPlus(verbose_name='Cadastrado em', null=True)
    atendida = models.BooleanField(verbose_name='Atendida', null=True)
    validada_por = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Avaliada por', null=True, blank=True, related_name='pesquisa_avaliacao_registrofrequencia'
    )
    validada_em = models.DateTimeFieldPlus(verbose_name='Avaliada em', null=True)

    class Meta:
        verbose_name = 'Registro de Frequência/Atividade do Projeto'
        verbose_name_plural = 'Registros de Frequência/Atividade do Projeto'

    def __str__(self):
        return 'Registro de Frequência/Atividade do Projeto'


class FinalidadeServicoLaboratorio(models.ModelPlus):
    descricao = models.CharField('Descrição', max_length=5000)
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Tipo de Finalidade do Serviço'
        verbose_name_plural = 'Tipos de Finalidade do Serviço'

    def __str__(self):
        return str(self.descricao)


class SolicitacaoServicoLaboratorio(models.ModelPlus):
    EM_ESPERA = 'Em Espera'
    DEFERIDA = 'Deferida'
    INDEFERIDA = 'Indeferida'
    ATENDIDA = 'Atendida'
    SITUACOES_CHOICES = ((EM_ESPERA, EM_ESPERA), (DEFERIDA, DEFERIDA), (INDEFERIDA, INDEFERIDA), (ATENDIDA, ATENDIDA))
    INTERNA = 'Interna'
    EXTERNA = 'Externa'
    TIPO_ENTIDADE_ATENDIDA_CHOICES = (
        (INTERNA, INTERNA),
        (EXTERNA, EXTERNA),
    )
    servico = models.ForeignKeyPlus(ServicoLaboratorioPesquisa, verbose_name='Serviço')
    tipo_entidade_atendida = models.CharFieldPlus('Tipo de entidade atendida', choices=TIPO_ENTIDADE_ATENDIDA_CHOICES, null=True)
    nome_instituicao = models.CharFieldPlus('Nome da instituição ou empreendimento atendido', null=True)
    cnpj_instituicao = models.BrCnpjField(verbose_name='CNPJ da instituição ou empreendimento atendido', null=True)
    finalidade = models.ForeignKeyPlus(FinalidadeServicoLaboratorio, verbose_name='Finalidade do Serviço')
    data = models.DateFieldPlus('Data')
    hora_inicio = models.TimeFieldPlus('Hora de Início')
    hora_termino = models.TimeFieldPlus('Hora de Término')
    descricao = models.CharField(
        'Descrição do Serviço',
        max_length=5000,
        help_text='Informe aqui as características e quantidades das amostras, materiais que serão entregues ao laboratório, etc.',
    )
    situacao = models.CharFieldPlus('Situação', max_length=100, choices=SITUACOES_CHOICES, default=EM_ESPERA)
    arquivo = models.FileFieldPlus(
        max_length=255, upload_to='upload/pesquisa/laboratorios/comprovantes/', null=True, blank=True, verbose_name='Documentos Comprobatórios'
    )
    parecer = models.CharFieldPlus(verbose_name='Retorno do Laboratório', max_length=5000, null=True)
    cadastrada_em = models.DateTimeFieldPlus('Cadastrada em', null=True)
    cadastrada_por = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Cadastrada por', null=True, blank=True, related_name='solicitante_servico_laboratorio'
    )
    avaliada_em = models.DateTimeFieldPlus('Avaliada em', null=True)
    concluida_em = models.DateTimeFieldPlus('Concluída em', null=True)
    laboratorio = models.ForeignKeyPlus(LaboratorioPesquisa, verbose_name='Laboratório')

    class Meta:
        verbose_name = 'Solicitação de Serviço no Laboratório'
        verbose_name_plural = 'Solicitações de Serviço no Laboratório'

    def __str__(self):
        return str(self.descricao)

    def pode_acompanhar(self, user):
        return self.cadastrada_por == user.get_vinculo() or user.get_relacionamento() == self.laboratorio.coordenador


class ColaboradorExterno(models.ModelPlus):
    nome = models.CharField('Nome', max_length=255)
    prestador = models.OneToOneField('comum.PrestadorServico', related_name='pesquisa_colaborador_externo', on_delete=models.CASCADE)
    ativo = models.BooleanField('Ativo', default=True)
    email = models.EmailField('Email')
    telefone = models.CharFieldPlus('Telefone', max_length=255, null=True, blank=True)
    titulacao = models.ForeignKeyPlus(
        'rh.Titulacao', verbose_name='Titulação', related_name='pesquisa_colaboradorexterno_instituicao', on_delete=models.CASCADE
    )
    instituicao_origem = models.ForeignKeyPlus(
        'rh.Instituicao',
        blank=True,
        null=True,
        verbose_name='Instituição',
        related_name='pesquisa_instituicao_colaboradorexterno',
        on_delete=models.CASCADE,
    )
    lattes = models.URLField(blank=True, null=True)
    documentacao = models.PrivateFileField(
        verbose_name='Documentação',
        upload_to='pesquisa/colaborador_externo',
        blank=True,
        null=True,
        help_text='Caso necessário, anexe os documentos comprobatórios.',
    )

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
        return '{}{}{}'.format(settings.SITE_URL, '/admin/pesquisa/colaboradorexterno/', self.id)


class RelatorioProjeto(models.ModelPlus):
    PARCIAL = 'Parcial'
    FINAL = 'Final'
    TIPO_RELATORIO_CHOICES = (
        (PARCIAL, PARCIAL),
        (FINAL, FINAL),
    )
    projeto = models.ForeignKeyPlus(Projeto, on_delete=models.CASCADE)
    tipo = models.CharFieldPlus('Tipo do Relatório', max_length=10, choices=TIPO_RELATORIO_CHOICES)
    descricao = models.CharFieldPlus('Descrição', max_length=1000)
    obs = models.TextField('Observação', null=True, blank=True, help_text='Informação adicional que você julgar relevante.')
    cadastrado_em = models.DateTimeFieldPlus('Cadastrado em', auto_now_add=True)
    avaliado_por = models.ForeignKeyPlus(Vinculo, null=True, related_name='pesquisa_avaliador_relatorio', on_delete=models.CASCADE)
    avaliado_em = models.DateTimeFieldPlus('Avaliado em', null=True)
    aprovado = models.BooleanField(default=False)
    arquivo = models.FileFieldPlus(max_length=255, upload_to='upload/pesquisa/relatorios/')
    justificativa_reprovacao = models.CharField(
        'Justificativa da Reprovação do Relatório',
        max_length=5000,
        null=True,
        blank=True,
        help_text='Informação adicional que você julgar relevante no que diz respeito à reprovação do relatório.',
    )

    class Meta:
        verbose_name = 'Relatório do Projeto'
        verbose_name_plural = 'Relatórios do Projeto'
        ordering = ['-cadastrado_em']

    def __str__(self):
        return str(self.descricao)

    def get_mensagem_avaliacao(obj):
        string = ''
        if obj.avaliado_em and obj.justificativa_reprovacao:
            string += f'<span class="status status-error">Não Aprovado em {format_(obj.avaliado_em)}</span>'
            string += f'<span class="status status-error">Justificativa: {obj.justificativa_reprovacao}</span>'

        elif obj.avaliado_em and not obj.justificativa_reprovacao:
            string += f'<span class="status status-success">Aprovado em {format_(obj.avaliado_em)}</span>'

        if string:
            string += f'<p>Avaliador: {obj.avaliado_por}</p>'
            return string

        return ''


class CursoReconhecimentoDiploma(models.ModelPlus):
    nome = models.CharFieldPlus(verbose_name='Nome')
    ativo = models.BooleanField(verbose_name='Ativo', default=True)

    class Meta:
        verbose_name = 'Curso de Reconhecimento de Diploma'
        verbose_name_plural = 'Cursos de Reconhecimentos de Diplomas'

    def __str__(self):
        return self.nome


class ReconhecimentoDiploma(models.ModelPlus):
    TIPO_CURSO_MESTRADO = 1
    TIPO_CURSO_DOUTORADO = 2
    TIPO_CURSO_CHOICES = [
        [TIPO_CURSO_MESTRADO, 'Mestrado'],
        [TIPO_CURSO_DOUTORADO, 'Doutorado'],
    ]
    vinculo_requerente = models.ForeignKeyPlus(Vinculo, verbose_name='Requerente', null=True)
    numero_registro = models.CharFieldPlus(verbose_name='Número do Registro')
    numero_etiqueta = models.PositiveIntegerFieldPlus(verbose_name='Número da Etiqueta')
    processo = models.ForeignKeyPlus(Processo, verbose_name='Processo Eletrônico')
    curso = models.CharFieldPlus(verbose_name='Nome do Curso na Instituição Estrangeira')
    instituicao_origem = models.CharFieldPlus(verbose_name='Instituição de Origem')
    pais_instituicao_origem = models.ForeignKeyPlus(Pais, verbose_name='País da Instituição de Origem')
    tipo_curso = models.IntegerField(choices=TIPO_CURSO_CHOICES, verbose_name='Tipo de Curso')
    curso_reconhecimento = models.ForeignKeyPlus(CursoReconhecimentoDiploma, verbose_name='Curso do Reconhecimento no IFRN')
    data_defesa = models.DateFieldPlus(verbose_name='Data de Defesa')
    data_registro = models.DateFieldPlus(verbose_name='Data de Registro')
    reitor = models.ForeignKeyPlus(Servidor, verbose_name='Reitor', related_name='reconhecimentodiploma_reitor')
    pro_reitor = models.ForeignKeyPlus(Servidor, verbose_name='Pró-Reitor', related_name='reconhecimentodiploma_pro_reitor')
    responsavel = models.CurrentUserField(verbose_name='Responsável')
    data_cadastro = models.DateTimeFieldPlus(auto_now=True, verbose_name='Última atualização')
    cadastrado_em = models.DateTimeFieldPlus(auto_now_add=True, verbose_name='Data de Cadastro', null=True)

    class Meta:
        verbose_name = 'Reconhecimento de Diploma'
        verbose_name_plural = 'Reconhecimentos de Diplomas'

    def __str__(self):
        return f'Registro de Diploma {self.pk} de {self.vinculo_requerente.__str__()}'


class TipoQuestionarioObra(models.ModelPlus):
    descricao = models.CharFieldPlus(verbose_name='Descrição')
    ativo = models.BooleanField(verbose_name='Ativo', default=True)

    class Meta:
        verbose_name = 'Tipo de Questionário para Avaliação de Obra'
        verbose_name_plural = 'Tipos de Questionários para Avaliação de Obra'

    def __str__(self):
        return self.descricao


class CriterioAvaliacaoObra(models.ModelPlus):
    descricao = models.CharFieldPlus(verbose_name='Descrição')
    nota = models.DecimalFieldPlus('Nota')
    ativo = models.BooleanField(verbose_name='Ativo', default=True)

    class Meta:
        verbose_name = 'Critério de Avaliação de Obra'
        verbose_name_plural = 'Critérios de Avaliação de Obra'

    def __str__(self):
        return f'{self.descricao} - {self.nota}'


class PerguntaQuestionarioObra(models.ModelPlus):
    descricao = models.TextField(verbose_name='Pergunta')
    tipo_questionario = models.ForeignKeyPlus(TipoQuestionarioObra, verbose_name='Tipo de Questionário', on_delete=models.SET_NULL, null=True)
    ordem = models.PositiveIntegerField('Ordem', help_text='Informe um número inteiro maior ou igual a 1')
    ativo = models.BooleanField(verbose_name='Ativo', default=True)

    class Meta:
        verbose_name = 'Pergunta do Questionário de Avaliação de Obra'
        verbose_name_plural = 'Perguntas do Questionário de Avaliação de Obra'

    def __str__(self):
        return self.descricao


class ItemAvaliacaoObra(models.ModelPlus):
    parecer = models.ForeignKeyPlus(ParecerObra)
    pergunta = models.ForeignKeyPlus(PerguntaQuestionarioObra, verbose_name='Pergunta', on_delete=models.CASCADE)
    nota = models.DecimalFieldPlus('Nota')
    criterio_avaliacao = models.ForeignKeyPlus(CriterioAvaliacaoObra, verbose_name='Critério de Avaliação', on_delete=models.CASCADE)
    comentarios = models.TextField('Comentários', null=True)

    class Meta:
        verbose_name = 'Item de Avaliação de Obra'
        verbose_name_plural = 'Itens de Avaliação de Obra'

    def __str__(self):
        return self.pergunta.descricao


class PropriedadeIntelectual(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição', max_length=2000)
    ativo = models.BooleanField('Ativo', default=True)
    ultima_rpi = models.CharFieldPlus('Última RPI Importada', max_length=10, null=True)

    class Meta:
        verbose_name = 'Propriedade Intelectual'
        verbose_name_plural = 'Propriedades Intelectuais'

    def __str__(self):
        return self.descricao


class Incubadora(models.ModelPlus):
    nome = models.CharFieldPlus('Nome Completo', max_length=3000)
    sigla = models.CharFieldPlus('Sigla', max_length=50)
    uo = models.ForeignKeyPlus(UnidadeOrganizacional, verbose_name='Campus', related_name='pesquisa_campus_incubadora')
    regimento_interno = models.PrivateFileField(verbose_name='Regimento Interno', upload_to='pesquisa/incubadora')
    ata_aprovacao = models.PrivateFileField(verbose_name='Ata de aprovação no colegiado acadêmico', upload_to='pesquisa/incubadora')
    coordenador = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Coordenador', related_name='pesquisa_coordenador_incubadora')
    gerente = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Gerente Executivo', related_name='pesquisa_gerente_incubadora')

    class Meta:
        verbose_name = 'Incubadora'
        verbose_name_plural = 'Incubadoras'

    def __str__(self):
        return self.nome

    def get_absolute_url(self):
        return f'/pesquisa/incubadora/{self.id}/'

    def pode_gerenciar_incubadora(self, user):
        vinculo = user.get_vinculo()
        return (
            user.has_perm('pesquisa.add_incubadora')
            or self.coordenador == vinculo
            or self.gerente == vinculo
            or (user.groups.filter(name='Coordenador de Pesquisa').exists() and (get_uo(user) == self.uo))
        )

    def pode_editar_dados_incubadora(self, user):
        return user.has_perm('pesquisa.add_incubadora') or (user.groups.filter(name='Coordenador de Pesquisa').exists() and (get_uo(user) == self.uo))

    @classmethod
    def tem_permissao_gerenciar_incubadora(cls, vinculo):
        user = vinculo.user
        return (
            user.has_perm('pesquisa.add_incubadora')
            or Incubadora.objects.filter(Q(coordenador=vinculo) | Q(gerente=vinculo)).exists()
            or (user.groups.filter(name='Coordenador de Pesquisa').exists() and (get_uo(user) == vinculo.setor.uo))
        )


class MembroIncubadora(models.ModelPlus):
    incubadora = models.ForeignKeyPlus(Incubadora, verbose_name='Incubadora')
    membro = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Membro', related_name='pesquisa_membro_incubadora')
    funcao = models.CharFieldPlus('Função', max_length=5000)

    class Meta:
        verbose_name = 'Membro da Incubadora'
        verbose_name_plural = 'Membros da Incubadora'

    def __str__(self):
        return f'{self.membro.__str__()} - {self.incubadora.__str__()}'


class DocumentoIncubadora(models.ModelPlus):
    incubadora = models.ForeignKeyPlus(Incubadora, verbose_name='Incubadora')
    descricao = models.CharFieldPlus('Descrição', max_length=2000)
    observacoes = models.TextField('Observações', null=True, blank=True)
    cadastrado_por = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Cadastrado por')
    cadastrado_em = models.DateTimeFieldPlus('Cadastrado em')
    arquivo = models.PrivateFileField(verbose_name='Arquivo', upload_to='pesquisa/incubadora')

    class Meta:
        verbose_name = 'Documento da Incubadora'
        verbose_name_plural = 'Documentos da Incubadora'

    def __str__(self):
        return f'{self.descricao} - {self.incubadora.__str__()}'


class FotoIncubadora(models.ModelPlus):
    incubadora = models.ForeignKeyPlus(Incubadora, verbose_name='Incubadora')
    descricao = models.CharFieldPlus('Descrição', max_length=2000)
    cadastrado_por = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Cadastrado por')
    cadastrado_em = models.DateTimeFieldPlus('Cadastrado em')
    arquivo = models.PrivateFileField(verbose_name='Arquivo', upload_to='pesquisa/incubadora')

    class Meta:
        verbose_name = 'Foto da Incubadora'
        verbose_name_plural = 'Fotos da Incubadora'

    def __str__(self):
        return f'{self.descricao} - {self.incubadora.__str__()}'


class EmpreendimentoIncubadora(models.ModelPlus):
    ATIVO = 'Ativo'
    GRADUADO = 'Graduado'
    DESLIGADO = 'Desligado'

    SITUACAO_CHOICES = (
        (ATIVO, ATIVO),
        (DESLIGADO, DESLIGADO),
        (GRADUADO, GRADUADO),
    )
    TIPO_INCUBACAO_CHOICES = (
        ('Residente', 'Residente'),
        ('Não-residente', 'Não-residente'),
    )
    incubadora = models.ForeignKeyPlus(Incubadora, verbose_name='Incubadora')
    razao_social = models.CharFieldPlus('Razão Social', max_length=2000)
    cnpj = models.BrCnpjField()
    situacao = models.CharFieldPlus('Situação', max_length=50, choices=SITUACAO_CHOICES)
    razao_desligamento = models.TextField('Razão do desligamento', null=True, blank=True)
    nome_fantasia = models.CharFieldPlus('Nome Fantasia', max_length=2000)
    tipo_incubacao = models.CharFieldPlus('Tipo de Incubação', max_length=50, choices=TIPO_INCUBACAO_CHOICES)
    atividade_principal = models.CharFieldPlus('Atividade Principal', max_length=2000)
    produto_explorado = models.CharFieldPlus('Produto ou serviço explorado', max_length=2000, null=True, blank=True)
    principal_pi = models.ForeignKeyPlus(PropriedadeIntelectual, verbose_name='Principal propriedade intelectual explorada', null=True)
    data_criacao = models.DateFieldPlus(verbose_name='Data de Criação')
    data_incubacao = models.DateFieldPlus(verbose_name='Data de Incubação')
    data_graduacao = models.DateFieldPlus(verbose_name='Data da Graduação')
    capital_social = models.DecimalFieldPlus(verbose_name='Capital Social', null=True, blank=True)
    qtde_funcionarios = models.IntegerFieldPlus(verbose_name='Quantidade de Funcionários', null=True, blank=True)
    site = models.CharFieldPlus('Site', max_length=2000, null=True, blank=True)
    cadastrado_por = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Cadastrado por')
    cadastrado_em = models.DateTimeFieldPlus('Cadastrado em')
    termo_juridico = models.PrivateFileField(verbose_name='Termo Jurídico', upload_to='pesquisa/incubadora')

    class Meta:
        verbose_name = 'Empreendimento da Incubadora'
        verbose_name_plural = 'Empreendimentos da Incubadora'

    def __str__(self):
        return f'{self.razao_social} - {self.incubadora.__str__()}'


class TipoTransferenciaTecnologica(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição', max_length=200)

    class Meta:
        verbose_name = 'Tipo de transferência de tecnologia'
        verbose_name_plural = 'Tipos de transferências de tecnologias'

    def __str__(self):
        return self.descricao


class TransferenciaTecnologica(models.ModelPlus):
    titulo = models.CharFieldPlus('Título da tecnologia', max_length=200)
    responsavel = models.CharFieldPlus('Responsável pela tecnologia', max_length=200)
    tipo = models.ForeignKeyPlus(TipoTransferenciaTecnologica, verbose_name='Tipo')
    empresa = models.CharFieldPlus('Nome Fantasia', max_length=2000)
    cnpj = models.BrCnpjField()
    data_finalizacao = models.DateFieldPlus('Data de finalização', null=True)
    numero_dou = models.IntegerFieldPlus('Número do DOU')
    data_dou = models.DateFieldPlus(verbose_name='Data do DOU')
    sessao_dou = models.IntegerFieldPlus('Sessão do DOU')
    pagina_dou = models.IntegerFieldPlus('Número da Página do DOU')
    anexo_pagina_dou = models.PrivateFileField(verbose_name='Página do DOU', upload_to='pesquisa/transferencias_tecnologia', null=True)
    anexo_contrato = models.PrivateFileField(verbose_name='Contrato', upload_to='pesquisa/transferencias_tecnologia', null=True, blank=True)
    anexo_processo = models.PrivateFileField(
        verbose_name='Arquivo do Processo', upload_to='pesquisa/transferencias_tecnologia', null=True, blank=True
    )
    id_processo = models.PositiveIntegerField(verbose_name='ID do Processo', null=True, blank=True)
    cancelada = models.BooleanField('Cancelada', default=False)

    class Meta:
        verbose_name = 'Licenciamento/ transferência de tecnologia'
        verbose_name_plural = 'Licenciamento/ transferência de tecnologia'

    def __str__(self):
        return f'{self.titulo} - {self.tipo}'

    def get_situacao(self):
        if self.cancelada:
            return '<span class="status status-rejeitado">Cancelada</span>'
        elif self.data_finalizacao and self.data_finalizacao > datetime.date.today():
            return '<span class="status status-alert">Em execução</span>'
        elif self.data_finalizacao:
            return '<span class="status status-success">Concluída</span>'
        return ''


class RegistroPropriedadeIntelectual(models.ModelPlus):
    titulo = models.CharFieldPlus('Título', max_length=2000, null=True, blank=True)
    numero_processo = models.CharFieldPlus('Nº do Pedido/processo', max_length=50, unique=True)
    tipo = models.ForeignKeyPlus(PropriedadeIntelectual, verbose_name='Tipo')
    primeira_rpi = models.CharFieldPlus('Nº da primeira RPI', max_length=50, null=True, blank=True)
    titulares = models.TextField('Depositantes/ Titulares', null=True, blank=True)
    inventores = models.TextField('Inventores/ criadores', null=True, blank=True)
    data = models.DateFieldPlus('Data do Depósito', null=True, blank=True)
    data_concessao = models.DateFieldPlus('Data da Concessão', null=True, blank=True)
    ativo = models.BooleanField('Ativo', default=True)
    termo_cessao = models.PrivateFileField(verbose_name='Termo de Cessão', upload_to='pesquisa/rpi/termo_cessao', null=True, blank=True)
    id_documento_termo_cessao = models.PositiveIntegerField(verbose_name='ID do Documento do Termo de Cessão', null=True)
    locarno_edicao = models.CharFieldPlus('Edição', null=True, max_length=20)
    locarno_codigo = models.CharFieldPlus('Código', null=True, max_length=20)
    locarno_descricao = models.CharFieldPlus('Descrição', null=True, max_length=500)
    situacao = models.CharFieldPlus('Situação', null=True, blank=True, max_length=2000)
    arquivado_em = models.DateTimeFieldPlus('Arquivado/Desarquivado em', null=True)
    arquivado_por = models.ForeignKeyPlus(Vinculo, verbose_name='Arquivado/Desarquivado por', null=True, on_delete=models.SET_NULL)
    motivo_arquivamento = models.TextField('Motivo do Arquivamento', null=True)
    certificado_registro = models.PrivateFileField(
        verbose_name='Certificado de Registro', upload_to='pesquisa/rpi/termo_cessao', null=True, blank=True
    )

    class Meta:
        verbose_name = 'Registro propriedade intelectual'
        verbose_name_plural = 'Registros propriedades intelectuais'

    def __str__(self):
        return f'{self.numero_processo} - {self.tipo}'

    def tem_termo_cessao(self):
        return self.id_documento_termo_cessao or self.termo_cessao

    def get_codigo(self):
        return self.numero_processo[2:4]

    def get_validade(self):
        data = None
        codigo = self.get_codigo()
        if self.data:
            if codigo == '10':
                data = self.data + relativedelta(years=20)
            elif codigo == '20':
                data = self.data + relativedelta(years=15)
            if data:
                return f'{self.data.strftime("%d/%m/%Y")} até {data.strftime("%d/%m/%Y")}'
        return 'Não informado'

    def get_data_primeiro_pagamento(self):
        if self.data:
            if self.eh_desenho_industrial():
                data_inicio = self.data + relativedelta(years=4)
                data_fim = self.data + relativedelta(years=5)
                return f'{data_inicio.strftime("%d/%m/%Y")} a {data_fim.strftime("%d/%m/%Y")}'
            else:
                data = self.data + relativedelta(years=2)
                return f'{data.strftime("%d/%m/%Y")}'
        else:
            return ''

    def get_numero_ultima_anuidade(self):
        codigo = self.get_codigo()
        if codigo == '10':
            return '20ª anuidade'
        elif codigo == '20':
            return '15ª anuidade'
        return 'Não informado'

    def get_data_ultimo_pagamento(self):
        if self.data:
            if self.eh_desenho_industrial():
                data_inicio = self.data + relativedelta(years=19)
                data_fim = self.data + relativedelta(years=20)
                return f'{data_inicio.strftime("%d/%m/%Y")} a {data_fim.strftime("%d/%m/%Y")}'
            else:
                data = None
                codigo = self.get_codigo()
                if codigo == '10':
                    data = self.data + relativedelta(years=19)
                elif codigo == '20':
                    data = self.data + relativedelta(years=14)
                if data:
                    return f'{data.strftime("%d/%m/%Y")}'
        return 'Não informado'

    def eh_patente(self):
        return self.tipo.descricao == 'Patente'

    def eh_desenho_industrial(self):
        return self.tipo.descricao == 'Desenho Industrial'

    def get_ultimo_despacho(self):
        return self.publicacaopropriedadeintelectual_set.latest('id')

    def get_anuidade_pendente(self):
        return (
            AnuidadeRegistroPropriedadeIntelectual.objects.filter(
                propriedadeintelectual=self, situacao=AnuidadeRegistroPropriedadeIntelectual.PENDENTE, inicio_ordinario__lte=datetime.date.today()
            )
            .order_by('id')
            .first()
        )


class PublicacaoPropriedadeIntelectual(models.ModelPlus):
    propriedadeintelectual = models.ForeignKeyPlus(RegistroPropriedadeIntelectual, verbose_name='Registro propriedade intelectual')
    rpi = models.CharFieldPlus('RPI', max_length=10)
    data = models.DateFieldPlus('Data do RPI', null=True)
    codigo = models.CharFieldPlus('Código', max_length=100, null=True)
    despacho = models.TextField('Despacho', null=True)
    complemento = models.TextField('Complemento', null=True)
    lida = models.BooleanField('Lida?', default=False)
    lida_por = models.ForeignKeyPlus(Vinculo, verbose_name='Lida por', null=True, on_delete=models.SET_NULL)
    lida_em = models.DateTimeFieldPlus('Lida em', null=True)

    class Meta:
        verbose_name = 'Publicação propriedade intelectual'
        verbose_name_plural = 'Publicações propriedades intelectuais'

    def __str__(self):
        return self.propriedadeintelectual

    def get_descricao_despacho(self):
        if self.propriedadeintelectual.eh_desenho_industrial():
            if DespachoINPIDI.objects.filter(codigo=self.codigo).exists():
                return DespachoINPIDI.objects.filter(codigo=self.codigo).first().descricao
            return self.despacho
        if DespachoINPI.objects.filter(codigo=self.codigo).exists():
            return DespachoINPI.objects.filter(codigo=self.codigo).first().descricao
        return '-'

    def get_detalhamento(self):
        if self.propriedadeintelectual.eh_desenho_industrial():
            if DespachoINPIDI.objects.filter(codigo=self.codigo).exists():
                return DespachoINPIDI.objects.filter(codigo=self.codigo).first().detalhamento or ''
        if DespachoINPI.objects.filter(codigo=self.codigo).exists():
            return DespachoINPI.objects.filter(codigo=self.codigo).first().detalhamento or ''
        return ''


class DespachoINPI(models.ModelPlus):
    codigo = models.CharFieldPlus('Código', max_length=10)
    descricao = models.TextField('Descrição')
    detalhamento = models.TextField('Detalhamento', null=True, blank=True)

    class Meta:
        verbose_name = 'Despacho do INPI'
        verbose_name_plural = 'Despachos do INPI'

    def __str__(self):
        return self.codigo


class DoacaoEditora(models.ModelPlus):
    destino = models.CharFieldPlus('Destino', max_length=5000)
    data = models.DateFieldPlus('Data')
    responsavel = models.CharFieldPlus('Responsável pelo recebimento', max_length=5000)
    arquivo = models.PrivateFileField(verbose_name='Arquivo', upload_to='pesquisa/editora/doacoes', null=True, blank=True)
    servidor = models.ForeignKeyPlus('rh.Servidor', verbose_name='Servidor', null=True, blank=True, related_name='pesquisa_doacao_servidor')
    aceite_em = models.DateTimeFieldPlus('Aceite em', null=True)

    class Meta:
        verbose_name = 'Doação Realizada pela Editora'
        verbose_name_plural = 'Doações Realizadas pela Editora'

    def __str__(self):
        return self.destino


class ItemDoacaoEditora(models.ModelPlus):
    doacao = models.ForeignKeyPlus(DoacaoEditora, verbose_name='Doação', on_delete=models.CASCADE)
    titulo = models.CharFieldPlus('Título', max_length=5000)
    quantidade = models.CharFieldPlus('Quantidade', max_length=5000)

    class Meta:
        verbose_name = 'Item'
        verbose_name_plural = 'Itens'

    def __str__(self):
        return self.titulo


class ServicoRegistroPropriedadeIntelectual(models.ModelPlus):
    propriedadeintelectual = models.ForeignKeyPlus(RegistroPropriedadeIntelectual, verbose_name='Registro propriedade intelectual')
    numero = models.CharFieldPlus('Número do Serviço', max_length=10)
    protocolo = models.CharFieldPlus('Número do Serviço', max_length=50)
    data = models.DateFieldPlus('Data')
    descricao = models.CharFieldPlus('Descrição do Serviço', max_length=5000)
    valor = models.CharFieldPlus('Valor', max_length=50)
    dados_pagamento = models.TextField('Dados do Pagamento', null=True)
    id_processo = models.PositiveIntegerField(verbose_name='ID do Processo Eletrônico', null=True)

    class Meta:
        verbose_name = 'Serviço da Propriedade Intelectual'
        verbose_name_plural = 'Serviço da Propriedade Intelectual'

    def __str__(self):
        return f'{self.propriedadeintelectual.numero_processo}: Serviço Nº {self.numero} (Protocolo: {self.protocolo})'


class AnuidadeRegistroPropriedadeIntelectual(models.ModelPlus):
    PAGO = 'Pago'
    PENDENTE = 'Pendente'
    TERCEIROS = 'Responsabilidade de terceiros'
    SITUACAO_CHOICES = (
        (PAGO, PAGO),
        (PENDENTE, PENDENTE),
        (TERCEIROS, TERCEIROS),
    )
    propriedadeintelectual = models.ForeignKeyPlus(RegistroPropriedadeIntelectual, verbose_name='Registro propriedade intelectual')
    anuidade = models.CharFieldPlus('Anuidade', max_length=100)
    inicio_ordinario = models.DateFieldPlus('Início do Período Ordinário', null=True)
    fim_ordinario = models.DateFieldPlus('Fim do Período Ordinário', null=True)
    inicio_extraordinario = models.DateFieldPlus('Início do Período Extraordinário', null=True)
    fim_extraordinario = models.DateFieldPlus('Fim do Período Extraordinário', null=True)
    data = models.DateFieldPlus('Data do Pagamento', null=True)
    gru = models.CharFieldPlus('GRU', max_length=100, null=True)
    valor = models.CharFieldPlus('Valor', max_length=50, null=True)
    situacao = models.CharFieldPlus('Situação', max_length=100, choices=SITUACAO_CHOICES)
    id_processo = models.PositiveIntegerField(verbose_name='ID do Processo Eletrônico', null=True)
    pagamento_informado_por = models.ForeignKeyPlus(Vinculo, verbose_name='Pagamento informado por', null=True, on_delete=models.SET_NULL)
    pagamento_informado_em = models.DateTimeFieldPlus('Pagamento informado em', null=True)
    responsavel_pagamento = models.CharFieldPlus('Responsável pelo pagamento', null=True, max_length=1000)

    class Meta:
        verbose_name = 'Anuidade da Propriedade Intelectual'
        verbose_name_plural = 'Anuidades da Propriedade Intelectual'

    def __str__(self):
        return f'{self.propriedadeintelectual.numero_processo}: {self.anuidade}'

    def get_situacao(self):
        if self.situacao == AnuidadeRegistroPropriedadeIntelectual.PAGO:
            return '<span class="status status-success">Pago</span>'
        elif self.situacao == AnuidadeRegistroPropriedadeIntelectual.TERCEIROS:
            return '<span class="status status-info">Responsabilidade de terceiros</span>'
        else:
            return '<span class="status status-alert">Pendente</span>'

    def estah_pendente(self):
        return self.situacao == AnuidadeRegistroPropriedadeIntelectual.PENDENTE


class CategoriaQuesito(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição', max_length=100, null=False, blank=False)
    ordem = models.PositiveIntegerField('Ordem', null=False, blank=False)
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Categoria do Quesito'
        verbose_name_plural = 'Categorias dos Quesitos'


class CategoriaEventoIncubadora(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição', max_length=1000)
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Categoria de Eventos da Incubadora'
        verbose_name_plural = 'Categorias de Eventos da Incubadora'

    def __str__(self):
        return self.descricao


class Quesito(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição', max_length=100, null=False, blank=False)
    ativo = models.BooleanField('Ativo', default=True)
    texto_ajuda = models.TextField('Orientações para preenchimento', null=True, blank=True)
    categoria = models.ForeignKeyPlus(CategoriaQuesito, verbose_name='Categoria')

    class Meta:
        verbose_name = 'Quesito'
        verbose_name_plural = 'Quesitos'

    def __str__(self):
        return self.descricao


class PesoQuesitoArea(models.ModelPlus):
    ACADEMICO = 'Acadêmico'
    PROFISSIONAL = 'Profissional'
    TIPO_CURSO_CHOICES = (
        (ACADEMICO, ACADEMICO),
        (PROFISSIONAL, PROFISSIONAL),
    )

    quesito = models.ForeignKeyPlus(Quesito, verbose_name='Quesito', null=False)
    areacapes = models.ForeignKeyPlus(AreaCapes, verbose_name='Área Capes', null=False)
    tipo_curso = models.CharFieldPlus('Tipo de Curso', choices=TIPO_CURSO_CHOICES, null=False, blank=False)
    peso = models.PositiveIntegerField('Peso', null=False, blank=False)
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Peso do Quesito por Área CAPES'
        verbose_name_plural = 'Pesos dos Quesitos por Área CAPES'

    def __str__(self):
        return f'Peso {self.peso} - {self.quesito.descricao}'


class AutoavaliacaoProgramaPos(models.ModelPlus):
    programa = models.ForeignKeyPlus(ProgramaPosGraduacao, verbose_name='Programa', null=False)
    ano = models.ForeignKeyPlus('comum.Ano', verbose_name='Ano', related_name='autoavaliacao_programapos_ano', on_delete=models.CASCADE)
    data_inicio = models.DateFieldPlus('Data início', null=False)
    data_fim = models.DateFieldPlus('Data fim', null=False)

    class Meta:
        verbose_name = 'Autoavaliação do Programa de Pós-Graduação'
        verbose_name_plural = 'Autoavaliações dos Programas de Pós-Graduação'

    def __str__(self):
        return f'{self.programa.nome} - {self.ano.ano}'

    def pode_responder(self, user):
        eh_coordenador = user.has_group_cached('Coordenador de Pós-Graduação') and self.programa.coordenador == user.get_relacionamento()
        estah_periodo_respostas = self.data_inicio <= datetime.datetime.now().date() <= self.data_fim
        return eh_coordenador and estah_periodo_respostas


class QuesitoAutoavaliacao(models.ModelPlus):
    autoavaliacao = models.ForeignKeyPlus(AutoavaliacaoProgramaPos, verbose_name='Autoavaliação', null=False)
    quesito = models.ForeignKeyPlus(Quesito, verbose_name='Quesito', null=False)
    ordem = models.PositiveIntegerField('Ordem', null=True, blank=False)

    # Resposta
    resposta = models.TextField('Resposta', null=True, blank=True)
    percentual = models.PositiveIntegerField('Percentual', null=True, blank=False)
    respondido_por = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Respondido por', null=True, blank=True, related_name='quesitoresposta_respondente'
    )
    respondido_em = models.DateFieldPlus('Data da Resposta', null=True)

    class Meta:
        verbose_name = 'Quesito da Autoavaliação'
        verbose_name_plural = 'Quesitos da Autoavaliação'

    def __str__(self):
        return f'{self.quesito} - Respondido: {"Sim" if bool(self.resposta) else "Não"}'


class EventoIncubadora(models.ModelPlus):
    incubadora = models.ForeignKeyPlus(Incubadora, verbose_name='Incubadora', on_delete=models.CASCADE)
    nome = models.CharFieldPlus('Nome', max_length=2000)
    descricao = models.TextField('Descrição')
    ch = models.CharFieldPlus('Carga Horária (em horas)', max_length=20)
    categoria = models.ForeignKeyPlus(CategoriaEventoIncubadora, verbose_name='Categoria do Evento', on_delete=models.CASCADE)
    data_inicio = models.DateTimeFieldPlus('Data de Início')
    data_termino = models.DateTimeFieldPlus('Data de Término')
    cadastrado_por = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Cadastrado por')
    cadastrado_em = models.DateTimeFieldPlus('Cadastrado em')

    class Meta:
        verbose_name = 'Evento da Incubadora'
        verbose_name_plural = 'Eventos da Incubadora'

    def __str__(self):
        return f'{self.nome} - {self.incubadora.__str__()}'


class ProjetoLaboratorioPesquisa(models.ModelPlus):
    TIPO_PROJETO_CHOICES = (
        ('Pesquisa', 'Pesquisa'),
        ('Extensão', 'Extensão'),
    )
    laboratorio = models.ForeignKeyPlus(LaboratorioPesquisa, verbose_name='Laboratório')
    id_do_projeto = models.IntegerFieldPlus('ID do Projeto')
    tipo = models.CharFieldPlus('Tipo do Projeto', max_length=20, choices=TIPO_PROJETO_CHOICES)
    cadastrado_por = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Cadastrado por')
    cadastrado_em = models.DateTimeFieldPlus('Cadastrado em')

    class Meta:
        verbose_name = 'Projeto Vinculado ao Laboratório de Pesquisa'
        verbose_name_plural = 'Projetos Vinculados ao Laboratório de Pesquisa'

    def __str__(self):
        return str(self.tipo)

    def get_titulo(self):
        if self.tipo == 'Pesquisa':
            return Projeto.objects.get(id=self.id_do_projeto).titulo
        else:
            from projetos.models import Projeto as ProjeExtensao

            return ProjeExtensao.objects.get(id=self.id_do_projeto).titulo

    def get_status(self):
        if self.tipo == 'Pesquisa':
            return Projeto.objects.get(id=self.id_do_projeto).get_status()
        else:
            from projetos.models import Projeto as ProjeExtensao

            return ProjeExtensao.objects.get(id=self.id_do_projeto).get_status()


class DespachoINPIDI(models.ModelPlus):
    codigo = models.CharFieldPlus('Código', max_length=10)
    descricao = models.TextField('Descrição')
    detalhamento = models.TextField('Detalhamento', null=True, blank=True)

    class Meta:
        verbose_name = 'Despacho do INPI - Desenho Industrial'
        verbose_name_plural = 'Despachos do INPI - Desenho Industrial'

    def __str__(self):
        return self.codigo


class SolicitacaoInclusaoEquipe(models.ModelPlus):
    projeto = models.ForeignKeyPlus(Projeto, on_delete=models.CASCADE)
    cadastrada_por = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Cadastrado por', null=True, blank=True, related_name='pesquisa_solicitacaoinclusao'
    )
    cadastrada_em = models.DateTimeFieldPlus(verbose_name='Cadastrado em', null=True)
    vinculo_pessoa = models.ForeignKey(
        'comum.Vinculo', verbose_name='Participante', related_name='pesquisa_vinculo_solicitacaoinclusao', on_delete=models.CASCADE
    )
    vinculo = models.CharField(max_length=255, choices=TipoVinculo.TIPOS)
    carga_horaria = models.PositiveIntegerField('Carga Horária', help_text='Carga horária semanal')
    data = models.DateFieldPlus('Data de Entrada')
    obs = models.TextField('Observações', null=True, blank=True)
    titulacao = models.CharFieldPlus('Titulação', null=True, max_length=500)
    atendida = models.BooleanField(verbose_name='Atendida', null=True)
    avaliada_por = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Avaliada por', null=True, blank=True, related_name='pesquisa_avaliacao_solicitacaoinclusao'
    )
    avaliada_em = models.DateTimeFieldPlus(verbose_name='Avaliada em', null=True)
    justificativa = models.TextField(verbose_name='Justificativa', null=True, blank=True)

    class Meta:
        verbose_name = 'Solicitação de Inclusão na Equipe'
        verbose_name_plural = 'Solicitações de Inclusão na Equipe'

    def __str__(self):
        return 'Solicitação de Inclusão na Equipe'

    def get_situacao(self):
        if self.atendida is None:
            return '<span class="status status-alert">Aguardando avaliação</span>'
        elif self.atendida:
            return '<span class="status status-success">Atendida</span>'
        else:
            return '<span class="status status-rejeitado">Não atendida</span>'


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


class EspecialidadeAssessor(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição', max_length=500)
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Especialidade do Assessor'
        verbose_name_plural = 'Especialidades do Assessor'

    def __str__(self):
        return self.descricao


class ModuloAssessoria(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição', max_length=500)
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Módulo da Assessoria'
        verbose_name_plural = 'Módulos da Assessoria'

    def __str__(self):
        return self.descricao


class IntegranteEquipeTecnica(models.ModelPlus):
    vinculo = models.ForeignKeyPlus(Vinculo, verbose_name='Assessor', on_delete=models.CASCADE)
    especialidades = models.ManyToManyFieldPlus(EspecialidadeAssessor, verbose_name='Especialidades')

    class Meta:
        verbose_name = 'Assessor'
        verbose_name_plural = 'Equipe Técnica de Assessoramento (ETA)'

    def get_especialidades(self):
        return ', '.join([descricao.__str__() for descricao in self.especialidades.all()])


class RecrutamentoAssessor(models.ModelPlus):
    MODALIDADE_CHOICES = (
        ('Presencial', 'Presencial'),
        ('Remota', 'Remota'),
    )
    vinculo = models.ForeignKeyPlus(Vinculo, verbose_name='Assessor', on_delete=models.CASCADE)
    conteudo = models.TextField('Conteúdo')
    incubadora = models.ForeignKeyPlus(Incubadora, verbose_name='Incubadora', on_delete=models.PROTECT)
    modulo = models.ForeignKeyPlus(ModuloAssessoria, verbose_name='Módulo', on_delete=models.PROTECT)
    modalidade_assessoria = models.CharFieldPlus('Modalidade da Assessoria', max_length=100, choices=MODALIDADE_CHOICES)
    carga_horaria = models.PositiveIntegerField('Carga Horária')
    recrutado_por = models.ForeignKeyPlus(Vinculo, verbose_name='Recrutado por', on_delete=models.PROTECT, related_name='recrutamento_recrutado_por')
    recrutado_em = models.DateTimeFieldPlus('Recrutado em', auto_now_add=True)
    aceito = models.BooleanField('Aceito', null=True)
    avaliado_em = models.DateTimeFieldPlus('Avaliado em', null=True)

    class Meta:
        verbose_name = 'Recrutamento do Assessor'
        verbose_name_plural = 'Recrutamentos dos Assessores'


class AssessorIncubadora(models.ModelPlus):
    MODALIDADE_CHOICES = (
        ('Presencial', 'Presencial'),
        ('Remota', 'Remota'),
    )
    vinculo = models.ForeignKeyPlus(Vinculo, verbose_name='Assessor', on_delete=models.CASCADE)
    incubadora = models.ForeignKeyPlus(Incubadora, verbose_name='Incubadora', on_delete=models.PROTECT)
    recrutamento = models.ForeignKeyPlus(RecrutamentoAssessor, verbose_name='Recrutamento', on_delete=models.PROTECT)
    data_inicio = models.DateFieldPlus('Data de início')
    data_termino = models.DateFieldPlus('Data de término', null=True)

    class Meta:
        verbose_name = 'Assessor da Incubadora'
        verbose_name_plural = 'Assessores da Incubadora'


class TipoParceria(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição', max_length=500)
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Tipo de Parceria'
        verbose_name_plural = 'Tipos de Parceria'


class SituacaoParceria(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição', max_length=500)
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Situação de Parceria'
        verbose_name_plural = 'Situações de Parceria'


class Parceria(models.ModelPlus):
    id_processo = models.PositiveIntegerField(verbose_name='ID do Processo Eletrônico', null=True)
    tipo = models.ForeignKeyPlus(TipoParceria, verbose_name='Tipo da Parceria', on_delete=models.PROTECT)
    area = models.ForeignKeyPlus('rh.AreaConhecimento', verbose_name='Área')
    titulo = models.CharFieldPlus('Título do projeto', max_length=5000)
    coordenador = models.ForeignKeyPlus(Vinculo, verbose_name='Coordenador', on_delete=models.PROTECT)
    situacao = models.ForeignKeyPlus(SituacaoParceria, verbose_name='Situação', on_delete=models.PROTECT)
    data_inicio = models.DateFieldPlus('Data de início')
    data_fim = models.DateFieldPlus('Data de fim')

    class Meta:
        verbose_name = 'Parceria'
        verbose_name_plural = 'Parcerias'

    def get_parceiros(self):
        return ' | '.join([f'{parceiro.nome} ({parceiro.cnpj})' for parceiro in self.parceiro_set.all()])

    def get_recursos(self):
        parceiros = self.parceiro_set.all()
        financeiro = parceiros.aggregate(total=Sum('recurso_financeiro'))['total'] or Decimal('0.0')
        economico = parceiros.aggregate(total=Sum('recurso_economico'))['total'] or Decimal('0.0')
        return financeiro + economico

    def get_vigencia(self):
        return f'{self.data_inicio.strftime("%d/%m/%Y")} - {self.data_fim.strftime("%d/%m/%Y")}'

    def tem_ata(self):
        return self.arquivoparceria_set.filter(tipo=ArquivoParceria.TipoArquivo.ATA).first()

    def tem_instrumento(self):
        return self.arquivoparceria_set.filter(tipo=ArquivoParceria.TipoArquivo.INSTRUMENTO_JURIDICO).first()

    def tem_plano(self):
        return self.arquivoparceria_set.filter(tipo=ArquivoParceria.TipoArquivo.PLANO_TRABALHO).first()


class Parceiro(models.ModelPlus):
    parceria = models.ForeignKeyPlus(Parceria, verbose_name='Parceria', on_delete=models.CASCADE)
    nome = models.CharFieldPlus('Parceiro', max_length=1000)
    cnpj = models.BrCnpjField(verbose_name='CNPJ')
    recurso_financeiro = models.DecimalFieldPlus('Recurso financeiro (R$)', max_digits=12, decimal_places=2, null=True, blank=True)
    recurso_economico = models.DecimalFieldPlus('Recurso econômico (R$)', max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        verbose_name = 'Parceiro'
        verbose_name_plural = 'Parceiros'


class FuncaoMembroParceria(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição', max_length=500)
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Função do Membro da Parceria'
        verbose_name_plural = 'Funções dos Membros da Parceria'


class TipoTitularidadePI(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição', max_length=500)
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Tipo de Titularidade da Propriedade Intelectual'
        verbose_name_plural = 'Tipos de Titularidades da Propriedade Intelectual'


class MembroParceria(models.ModelPlus):
    parceria = models.ForeignKeyPlus(Parceria, verbose_name='Parceria', on_delete=models.CASCADE)
    vinculo = models.ForeignKeyPlus(Vinculo, verbose_name='Membro', on_delete=models.SET_NULL, null=True, blank=True)
    nome = models.CharFieldPlus('Nome do membro', max_length=1000, null=True, blank=True)
    funcao = models.ForeignKeyPlus(FuncaoMembroParceria, verbose_name='Função', on_delete=models.PROTECT)
    instituicao = models.CharFieldPlus('Instituição', max_length=2000, null=True, blank=True)

    class Meta:
        verbose_name = 'Membro da Parceria'
        verbose_name_plural = 'Membros da Parceria'


class PiParceria(models.ModelPlus):
    parceria = models.ForeignKeyPlus(Parceria, verbose_name='Parceria', on_delete=models.CASCADE)
    titulo = models.CharFieldPlus('Título', max_length=5000)
    tipo = models.ForeignKeyPlus(PropriedadeIntelectual, verbose_name='Tipo', on_delete=models.PROTECT)
    area = models.ForeignKeyPlus('rh.AreaConhecimento', verbose_name='Área')
    valor = models.DecimalFieldPlus('Valor', max_digits=12, decimal_places=2, null=True, blank=True)
    tipo_transferencia = models.ForeignKeyPlus(
        TipoTransferenciaTecnologica, verbose_name='Tipo de transferência de tecnologia', on_delete=models.PROTECT
    )
    titularidade = models.ForeignKeyPlus(TipoTitularidadePI, verbose_name='Titularidade', on_delete=models.PROTECT)
    situacao = models.ForeignKeyPlus(SituacaoParceria, verbose_name='Situação', on_delete=models.PROTECT)

    class Meta:
        verbose_name = 'Propriedade Intelectual da Parceria'
        verbose_name_plural = 'Propriedades Intelectuais da Parceria'

    def get_divisao(self):
        return ' | '.join([f'{divisao.parceiro.nome}: {divisao.percentual_lucro}% ' for divisao in self.parceiropiparceria_set.all()])


class ParceiroPiParceria(models.ModelPlus):
    pi = models.ForeignKeyPlus(PiParceria, verbose_name='Propridade intelectual', on_delete=models.PROTECT)
    parceiro = models.ForeignKeyPlus(Parceiro)
    percentual_lucro = models.FloatField('Valor (%)')

    class Meta:
        verbose_name = 'Parceiro da Propriedade Intelectual'
        verbose_name_plural = 'Parceiros da Propriedade Intelectual'


class ArquivoParceria(models.ModelPlus):
    class TipoArquivo(models.TextChoices):
        ATA = 'ATA', 'Ata de colegiado'
        PLANO_TRABALHO = 'PLANO_TRABALHO', 'Plano de trabalho'
        INSTRUMENTO_JURIDICO = 'INSTRUMENTO_JURIDICO', 'Instrumento Jurídico'
        OUTRO = 'OUTRO', 'Outro'

    parceria = models.ForeignKeyPlus(Parceria, verbose_name='Parceria', on_delete=models.PROTECT)
    arquivo = models.FileFieldPlus(max_length=255, upload_to='upload/pesquisa/parcerias/', null=True, blank=True)
    id_documento = models.PositiveIntegerField(verbose_name='ID do Documento Eletrônico', null=True)
    tipo = models.CharFieldPlus('Tipo', choices=TipoArquivo, default=TipoArquivo.OUTRO, max_length=50)

    class Meta:
        verbose_name = 'Arquivo da Parceria'
        verbose_name_plural = 'Arquivos da Parceria'

    def get_identificador(self):
        if self.arquivo:
            return os.path.basename(self.arquivo.name)
        if 'documento_eletronico' in settings.INSTALLED_APPS:
            from documento_eletronico.models import DocumentoTexto

            return DocumentoTexto.objects.get(id=self.id_documento).identificador
        return ''


class EtapaParceria(models.ModelPlus):
    parceria = models.ForeignKeyPlus(Parceria, verbose_name='Parceria', on_delete=models.PROTECT)
    situacao = models.ForeignKeyPlus(SituacaoParceria, verbose_name='Situação', on_delete=models.PROTECT)
    data_inicio = models.DateFieldPlus('Data de início', null=True, blank=True)
    data_fim = models.DateFieldPlus('Data de fim', null=True, blank=True)

    class Meta:
        verbose_name = 'Etapa da Parceria'
        verbose_name_plural = 'Etapas da Parceria'

    def em_andamento(self):
        hoje = datetime.date.today()
        if self.data_inicio and self.data_fim:
            return self.data_inicio < hoje < self.data_fim
        elif self.data_fim and self.data_fim > hoje or self.data_inicio and self.data_inicio < hoje:
            return True
        return False


class RegistroDiarioBordo(models.ModelPlus):
    class SituacaoChoices(models.TextChoices):
        EM_EDICAO = 'Em edição', 'Em edição'
        FINALIZADO = 'Finalizado', 'Finalizado'

    projeto = models.ForeignKeyPlus(Projeto, on_delete=models.CASCADE)
    titulo = models.CharFieldPlus('Título', max_length=5000)
    conteudo = models.TextField('Conteúdo')
    situacao = models.CharFieldPlus('Situação', max_length=50, default=SituacaoChoices.EM_EDICAO)
    cadastrado_em = models.DateTimeFieldPlus('Cadastrado em', auto_now_add=True)
    atualizado_em = models.DateTimeFieldPlus('Atualizado em', auto_now=True)
    cadastrado_por = models.ForeignKeyPlus(Vinculo, related_name='pesquisa_registrodiariobordo', on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Registro do Diário de Bordo do Projeto'
        verbose_name_plural = 'Registros do Diário de Bordo do Projeto'
        ordering = ['-cadastrado_em']

    def pode_editar(self):
        return self.situacao == RegistroDiarioBordo.SituacaoChoices.EM_EDICAO

    def get_situacao(self):
        return self.situacao

    def posso_alterar(self, vinculo):
        return self.cadastrado_por == vinculo and self.projeto.pode_adicionar_registro_diario_bordo() and self.pode_editar()


class RecursoTransferencia(models.ModelPlus):
    transferencia = models.ForeignKeyPlus(TransferenciaTecnologica, verbose_name='Transferência', on_delete=models.CASCADE)
    especificacao = models.TextField('Especificação')
    valor = models.DecimalFieldPlus('Valor (R$)')
    anexo_processo = models.PrivateFileField(
        verbose_name='Arquivo do Processo', upload_to='pesquisa/transferencias_tecnologia', null=True, blank=True
    )
    id_processo = models.PositiveIntegerField(verbose_name='ID do Processo', null=True, blank=True)

    class Meta:
        verbose_name = 'Recurso recebido pela transferência tecnológica'
        verbose_name_plural = 'Recursos recebidos pela transferência tecnológica'


class DocumentoTransferencia(models.ModelPlus):
    transferencia = models.ForeignKeyPlus(TransferenciaTecnologica, verbose_name='Transferência', on_delete=models.CASCADE)
    titulo = models.CharFieldPlus('Título', max_length=2000)
    documento = models.PrivateFileField(verbose_name='Documento', upload_to='pesquisa/transferencias_tecnologia', null=True, blank=True)
    id_documento = models.PositiveIntegerField(verbose_name='ID do Documento', null=True, blank=True)

    class Meta:
        verbose_name = 'Documento da transferência tecnológica'
        verbose_name_plural = 'Documentos da transferência tecnológica'
