import datetime
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.db import transaction

from comum.models import Ano
from djtools.db import models
from djtools.utils import send_mail, send_notification
from edu.models import Aluno, CursoCampus, Modalidade, SituacaoMatricula
from rh.models import UnidadeOrganizacional


class Pesquisa(models.ModelPlus):
    titulo = models.CharFieldPlus('Título', blank=False, null=False)
    descricao = models.TextField('Descrição', blank=False, null=False)

    inicio = models.DateFieldPlus('Início', blank=True, null=True)
    fim = models.DateFieldPlus('Fim', blank=True, null=True)
    publicada = models.BooleanField('Publicada', null=True)

    # Público Alvo
    modalidade = models.ForeignKeyPlus(Modalidade, verbose_name='Público Alvo', blank=True, null=True)
    conclusao = models.ManyToManyFieldPlus(Ano, verbose_name='Ano de Conclusão', blank=False)
    uo = models.ManyToManyFieldPlus(UnidadeOrganizacional, verbose_name='Campus', blank=True)
    curso_campus = models.ForeignKeyPlus(CursoCampus, verbose_name='Curso', blank=True, null=True)

    class Meta:
        verbose_name = 'Pesquisa de Acompanhamento de Egressos'
        verbose_name_plural = 'Pesquisas de Acompanhamento de Egressos'
        permissions = (('eh_gestor_egressos_sistemico', 'Eh Gestor de Egressos Sistêmico'),)

    def __str__(self):
        return f'Pesquisa de Acompanhamento de Egressos: {self.titulo}'

    def get_absolute_url(self):
        return f'/egressos/pesquisa/{self.pk}/'

    def get_alunos_alvo(self):
        if self.modalidade:
            alunos = Aluno.objects.filter(situacao__id__in=[SituacaoMatricula.FORMADO, SituacaoMatricula.CONCLUIDO])
        else:
            alunos = Aluno.nao_fic.filter(situacao__id__in=[SituacaoMatricula.FORMADO, SituacaoMatricula.CONCLUIDO])
        if self.modalidade or self.conclusao.exists() or self.uo.exists() or self.curso_campus:
            if self.modalidade:
                alunos = alunos.filter(curso_campus__modalidade__id__in=[self.modalidade.pk])
            if self.conclusao.exists():
                alunos = alunos.filter(ano_conclusao__in=[ac.ano for ac in self.conclusao.all()])
            if self.uo.exists():
                alunos = alunos.filter(curso_campus__diretoria__setor__uo__in=self.uo.all())
            if self.curso_campus:
                alunos = alunos.filter(curso_campus=self.curso_campus)
            return alunos.select_related(
                'curso_campus', 'curso_campus__diretoria', 'curso_campus__diretoria__setor', 'pessoa_fisica', 'situacao'
            ).only('curso_campus', 'curso_campus__diretoria', 'curso_campus__diretoria__setor', 'pessoa_fisica', 'situacao', 'matricula')
        else:
            return Aluno.objects.none()

    def enviar_convites(self):
        emails = []
        vinculos = []
        for aluno in self.get_alunos_alvo():
            vinculos.append(aluno.get_vinculo())
            if aluno.email_notificacao:
                emails.append(aluno.email_notificacao)
        assunto = '[SUAP] Pesquisa para Aluno Egresso'
        mensagem = (
            '<h1>Egressos</h1>'
            '<h2>Notificação de Pesquisa para Aluno Egresso</h2>'
            '<p>Caro Egresso, solicitamos que acesse o SUAP para responder uma pesquisa para alunos egressos.</p>'
        )

        send_notification(assunto, mensagem, settings.DEFAULT_FROM_EMAIL, vinculos)
        send_mail(assunto, mensagem, settings.DEFAULT_FROM_EMAIL, [], bcc=emails, fail_silently=True)
        EmailEnviado(mensagem=f'Assunto: {assunto} <br/> Mensagem:{mensagem}', destinatarios=', '.join(emails), pesquisa=self).save()

    def reenviar_convites_alunos_nao_respondentes(self):
        emails = []
        vinculos = []
        for aluno in self.get_alunos_alvo().exclude(resposta__id__gt=0):
            vinculos.append(aluno.get_vinculo())
            if aluno.email_notificacao:
                emails.append(aluno.email_notificacao)
        assunto = '[SUAP] Pesquisa para Aluno Egresso - Reenvio'
        mensagem = (
            '<h1>Egressos</h1>'
            '<h2>Notificação de Pesquisa para Aluno Egresso - Reenvio</h2>'
            '<p>Caro Egresso, solicitamos que acesse o SUAP para responder uma pesquisa para alunos egressos.</p>'
        )

        send_notification(assunto, mensagem, settings.DEFAULT_FROM_EMAIL, vinculos)
        send_mail(assunto, mensagem, settings.DEFAULT_FROM_EMAIL, [], bcc=emails, fail_silently=True)
        EmailEnviado(mensagem=f'Assunto: {assunto} <br/> Mensagem:{mensagem}', destinatarios=', '.join(emails), pesquisa=self).save()

    def get_url_relatorio(self):
        url = '/edu/relatorio/'
        parametros = {
            'modalidade': self.modalidade.pk,
            'ano_conclusao': ';'.join([str(ano.pk) for ano in self.conclusao.all()]),
            'uo': ';'.join([str(uo.pk) for uo in self.uo.all()]),
            'curso_campus': self.curso_campus.pk,
            'situacao_matricula': [SituacaoMatricula.FORMADO, SituacaoMatricula.CONCLUIDO],
            'formatacao': 'simples',
            'quantidade_itens': 25,
            'ordenacao': 'Nome',
            'agrupamento': 'Campus',
            'exibicao': ['curso_campus.diretoria.setor.uo', 'curso_campus', 'situacao', 'email_notificacao'],
        }
        return f'{url}?{urllib.parse.urlencode(parametros, True)}'

    def get_proximo_bloco(self, aluno, bloco_atual):
        ids_categorias_direcionadas = (
            Resposta.objects.filter(pergunta__pesquisa=self, opcoes__direcionamento_categoria__id__gt=0, aluno=aluno)
            .distinct()
            .values_list('opcoes__direcionamento_categoria__id', flat=True)
        )
        categorias_direcionadas = self.categoria_set.filter(id__in=ids_categorias_direcionadas, ordem__gt=bloco_atual.ordem).order_by('ordem')
        if categorias_direcionadas.exists():
            return categorias_direcionadas[0]
        else:
            return self.get_ultimo_bloco()

    def ha_pergunta_objetiva_sem_opcoes(self):
        return self.pergunta_set.exclude(tipo=Pergunta.SUBJETIVA).filter(opcao__id=None).exists()

    def ha_pergunta_objetiva_com_opcao_subjetiva_sem_opcao_complementacao_definida(self):
        return (
            self.pergunta_set.filter(tipo=Pergunta.OBJETIVA_RESPOSTA_UNICA_COM_OPCAO_SUBJETIVA).exclude(opcao__complementacao_subjetiva=True).exists()
        )

    def perguntas_objetivas_com_opcao_subjetiva_sem_opcao_complementacao_definida(self):
        return self.pergunta_set.filter(tipo=Pergunta.OBJETIVA_RESPOSTA_UNICA_COM_OPCAO_SUBJETIVA).exclude(opcao__complementacao_subjetiva=True)

    @transaction.atomic
    def clonar_pesquisa(self, titulo, descricao):
        pesquisa_clonada = Pesquisa(titulo=titulo, descricao=descricao)
        pesquisa_clonada.save()
        for categoria in self.categoria_set.all():
            categoria_clonada = Categoria(titulo=categoria.titulo, ordem=categoria.ordem, pesquisa=pesquisa_clonada)
            categoria_clonada.save()
        for categoria in self.categoria_set.all():
            categoria_clonada = pesquisa_clonada.categoria_set.get(titulo=categoria.titulo, ordem=categoria.ordem)
            for pergunta in categoria.pergunta_set.all():
                pergunta_clonada = Pergunta(
                    conteudo=pergunta.conteudo,
                    tipo=pergunta.tipo,
                    preenchimento_obrigatorio=pergunta.preenchimento_obrigatorio,
                    categoria=categoria_clonada,
                    pesquisa=pesquisa_clonada,
                )
                pergunta_clonada.save()
                for opcao in pergunta.opcao_set.all():
                    if opcao.direcionamento_categoria:
                        opcao_clonada = Opcao(
                            conteudo=opcao.conteudo,
                            pergunta=pergunta_clonada,
                            direcionamento_categoria=pesquisa_clonada.categoria_set.get(
                                titulo=opcao.direcionamento_categoria.titulo, ordem=opcao.direcionamento_categoria.ordem
                            ),
                            complementacao_subjetiva=opcao.complementacao_subjetiva,
                        )
                    else:
                        opcao_clonada = Opcao(
                            conteudo=opcao.conteudo, pergunta=pergunta_clonada, complementacao_subjetiva=opcao.complementacao_subjetiva
                        )
                    opcao_clonada.save()
        return pesquisa_clonada

    def esta_em_periodo_de_resposta(self):
        if not self.fim:
            return True
        return self.fim >= datetime.date.today() and self.inicio <= datetime.date.today()

    def get_ultimo_bloco(self):
        return self.categoria_set.all().order_by('-ordem')[0]


class Categoria(models.ModelPlus):
    titulo = models.CharFieldPlus('Título', blank=False, null=False)
    ordem = models.PositiveSmallIntegerField('Ordem', blank=False, null=True)
    pesquisa = models.ForeignKeyPlus(Pesquisa)

    class Meta:
        verbose_name = 'Categoria'
        verbose_name_plural = 'Categorias'
        ordering = ('pk',)

    def __str__(self):
        return f'{self.titulo}'


class Pergunta(models.ModelPlus):
    OBJETIVA_RESPOSTA_UNICA = 1
    OBJETIVA_RESPOSTAS_MULTIPLAS = 2
    SUBJETIVA = 3
    OBJETIVA_RESPOSTA_UNICA_COM_OPCAO_SUBJETIVA = 4
    TIPO_CHOICES = [
        [OBJETIVA_RESPOSTA_UNICA, 'Objetiva de resposta única'],
        [OBJETIVA_RESPOSTAS_MULTIPLAS, 'Objetiva de respostas múltiplas'],
        [SUBJETIVA, 'Subjetiva'],
        [OBJETIVA_RESPOSTA_UNICA_COM_OPCAO_SUBJETIVA, 'Objetiva de resposta única com complementação subjetiva'],
    ]
    conteudo = models.TextField('Conteúdo', blank=False, null=False)
    tipo = models.PositiveIntegerFieldPlus(choices=TIPO_CHOICES, blank=False, null=False)
    preenchimento_obrigatorio = models.BooleanField('Preenchimento Obrigatório')
    categoria = models.ForeignKeyPlus(Categoria, null=False, blank=False, verbose_name='Categoria')
    pesquisa = models.ForeignKeyPlus(Pesquisa)

    class Meta:
        verbose_name = 'Pergunta'
        verbose_name_plural = 'Pergunta'
        ordering = ('categoria__pk', 'pk')

    def eh_objetiva(self):
        return self.tipo in [
            Pergunta.OBJETIVA_RESPOSTA_UNICA,
            Pergunta.OBJETIVA_RESPOSTAS_MULTIPLAS,
            Pergunta.OBJETIVA_RESPOSTA_UNICA_COM_OPCAO_SUBJETIVA,
        ]

    def tem_opcao_complementacao_pendente(self):
        return not self.opcao_set.filter(complementacao_subjetiva=True).exists()

    def __str__(self):
        return '({}) {}'.format(self.pk, self.conteudo or '')


class Opcao(models.ModelPlus):
    conteudo = models.TextField('Opção de Resposta')
    pergunta = models.ForeignKeyPlus(Pergunta)
    direcionamento_categoria = models.ForeignKeyPlus(Categoria, null=True, blank=True, verbose_name='Direcionar à Categoria')
    complementacao_subjetiva = models.BooleanField('Complementação Subjetiva', default=False)

    class Meta:
        verbose_name = 'Opção de Resposta'
        verbose_name_plural = 'Opção de Resposta'
        ordering = ('pk',)

    def __str__(self):
        return self.conteudo


class Resposta(models.ModelPlus):
    aluno = models.ForeignKeyPlus(Aluno)
    pergunta = models.ForeignKeyPlus(Pergunta)
    opcoes = models.ManyToManyFieldPlus(Opcao, verbose_name='Opções Selecionadas')
    resposta_subjetiva = models.CharFieldPlus('Resposta Subjetiva', null=True)

    class Meta:
        verbose_name = 'Resposta'
        verbose_name_plural = 'Respostas'
        unique_together = ('aluno', 'pergunta')

        permissions = (('view_pesquisas_respondidas', 'Pode ver suas próprias respostas a pesquisas de egressos'),)


class EmailEnviado(models.ModelPlus):
    destinatarios = models.TextField('Destinatários')
    mensagem = models.TextField('Mensagem')
    pesquisa = models.ForeignKeyPlus(Pesquisa)

    class Meta:
        verbose_name = 'E-mail Enviado'
        verbose_name_plural = 'E-mails Enviados'
