import datetime
import os

from django.conf import settings
from djtools.utils import send_notification

import numpy as np
from django.db import transaction
from django.db.models.aggregates import Count, Max
from django.template.defaultfilters import linebreaksbr
from django.utils.safestring import mark_safe

from comum.models import Publico, Vinculo
from djtools.db import models
from djtools.html.graficos import PieChart
from rh.models import UnidadeOrganizacional


class Enquete(models.ModelPlus):
    tag = models.CharFieldPlus('Tag', default='Responda à Enquete', help_text='Tag que será usada na tela inicial do questionário/enquete.')
    titulo = models.CharFieldPlus('Título')
    descricao = models.TextField('Descrição')
    data_inicio = models.DateTimeFieldPlus('Data de Início')
    data_fim = models.DateTimeFieldPlus('Data de Término')
    vinculos_relacionados_enquete = models.ManyToManyFieldPlus(
        'comum.Vinculo', verbose_name='Vínculos Relacionados', related_name='vinculos_relacionados_enquete', blank=True
    )
    vinculos_responsaveis = models.ManyToManyFieldPlus(
        'comum.Vinculo', related_name='vinculos_responsaveis_enquetes', verbose_name='Responsável(is)', blank=True
    )
    publicada = models.BooleanField(default=False)
    manter_enquete_inicio = models.BooleanField(
        'Manter Enquete na Tela Inicial',
        default=False,
        help_text='Se esta opção ficar desmarcada, quando um usuário responder a enquete, ela não vai mais aparecer na tela inicial para ele.',
    )
    resultado_publico = models.BooleanField(
        'Resultado Público',
        default=False,
        help_text='No resultado dessa enquete irá aparecer quem respondeu (somente para Responsáveis pela Enquete).',
    )
    instrucoes = models.FileFieldPlus(verbose_name='Anexo', upload_to='enquete/instrucoes/', null=True, blank=True)
    descricao_anexo = models.CharFieldPlus(verbose_name='Descrição do Anexo', default='Instruções da Enquete', blank=True)
    texto_orientacao = models.TextField('Texto de Orientação', blank=True)
    vinculos_publico = models.ManyToManyFieldPlus('comum.Vinculo', related_name='vinculos_publico', verbose_name='Vínculos Público', blank=True)
    publico_nao_respondente_data_notificacao = models.DateTimeFieldPlus(
        'Data/Hora da última notificação para o público não-respondente', editable=False, null=True
    )
    publico_nao_respondente_vinculo_notificador = models.ForeignKeyPlus(
        'comum.Vinculo',
        verbose_name='Vínculo notificador da última notificação para o público não-respondente',
        on_delete=models.SET_NULL,
        editable=False,
        null=True,
    )

    class Meta:
        verbose_name = 'Enquete'
        verbose_name_plural = 'Enquetes'

    def __str__(self):
        return self.titulo

    def get_absolute_url(self):
        return f'/enquete/enquete/{self.id}/'

    def save(self, *args, **kargs):
        if self.pk:
            if not self.pode_publicar() and self.publicada:
                self.publicada = False
        super().save(*args, **kargs)
        self.set_publico()

    def get_instrucoes(self):
        return os.path.basename(self.instrucoes.name)

    def get_perguntas_agrupadas_por_categoria(self):
        categorias = self.get_categorias()
        for categoria in categorias:
            categoria.perguntas = self.pergunta_set.filter(categoria=categoria).order_by('ordem')
            categoria.cabecalho = list(categoria.perguntas)
        return categorias

    def get_categorias(self):
        return self.categoria_set.order_by('ordem')

    def get_vinculos_relacionados_enquete(self):
        vinculos_relacionados_enquete = []
        for vinculo_publico in self.vinculos_relacionados_enquete.all():
            vinculos_relacionados_enquete.append(str(vinculo_publico))

        return ', '.join(vinculos_relacionados_enquete)

    def get_opcoes(self):
        return self.opcao_set.filter(opcaopergunta__isnull=True)

    def set_publico(self):
        """Apenas a enquete sabe determinar o seu público (conjunto de Vínculos)

        vínculos de self.vinculos_relacionados_enquete
        +
        vínculos a partir de self.publicocampi_set
        """
        publicos = self.vinculos_relacionados_enquete.all().distinct()
        for publico_campi in self.publicocampi_set.all():
            if publico_campi.publico.modelo_base == publico_campi.publico.BASE_SERVIDOR:
                tipo_setor = Publico.TIPO_SETOR_EXERCICIO_SIAPE
            else:
                tipo_setor = Publico.TIPO_SETOR_SUAP
            publicos |= publico_campi.publico.get_queryset_vinculo(campi=publico_campi.campi, setores=publico_campi.setores, tipo_setor=tipo_setor)
        self.vinculos_publico.set(publicos.distinct())

    def get_publico_str(self):
        """
        Descrições dos públicos dos campi, mais uma informação
        indicando que há outros vínculos relacionados.
        """
        retorno = []
        for publico_campi in self.publicocampi_set.all():
            retorno.append(f'{publico_campi}')
        if self.vinculos_relacionados_enquete.exists():
            retorno.append('Vínculos Específicos')
        return ', '.join(retorno)

    def eh_parte_publico(self, vinculo):
        return self.vinculos_publico.filter(id=vinculo.id).exists()

    def pode_responder(self, vinculo):
        return self.publicada and self.data_inicio <= datetime.datetime.today() <= self.data_fim and self.eh_parte_publico(vinculo)

    def respondeu(self, vinculo):
        return vinculo.enquete_resposta_vinculo.filter(pergunta__enquete=self).exists()

    def respondeu_todas_as_perguntas(self, vinculo):
        qtd_perguntas = self.pergunta_set.all().count()
        qtd_perguntas_respondidas = self.pergunta_set.filter(resposta__vinculo=vinculo).distinct().count()
        return qtd_perguntas_respondidas == qtd_perguntas

    def get_publico_nao_respondente(self) -> models.QuerySet[Vinculo]:
        quem_pode_responder = self.vinculos_publico.all()
        quem_respondeu = Vinculo.objects.filter(enquete_resposta_vinculo__pergunta__enquete=self)
        quem_nao_respondeu = quem_pode_responder.difference(quem_respondeu)
        return quem_nao_respondeu

    def notificou_hoje_publico_nao_respondente(self):
        return (
            self.publico_nao_respondente_data_notificacao and self.publico_nao_respondente_data_notificacao.date() == datetime.datetime.today().date()
        )

    @staticmethod
    def get_nome_publico(vinculo):
        try:
            return vinculo.pessoa.nome
        except Exception:
            return f'{vinculo}'

    def notifica_publico_nao_respondente(self, vinculo_notificador) -> int:
        publico_nao_respondente = self.get_publico_nao_respondente()

        if not publico_nao_respondente.exists():
            return 0

        link_responder_enquete = f'{settings.SITE_URL}/enquete/responder_enquete/{self.id}/'
        publico_notificado_qtd = 0

        for vinculo in publico_nao_respondente:
            send_notification(
                assunto=f'Enquete não respondida: {self.titulo}',
                mensagem=f'''
                <p>{Enquete.get_nome_publico(vinculo)},</p>
                <br/>
                <p>
                    Percebemos que você ainda não respondeu à nossa enquete <strong>{self.titulo}</strong>.
                    <br/>
                    Só queríamos lembrar que ela continua aberta e que o prazo para participar vai até <strong>{self.data_fim.strftime('%d/%m/%Y às %H:%M')}</strong>.
                    <br/>
                    <br/>
                    <a href="{link_responder_enquete}">Responda agora</a>, contamos com a sua colaboração para garantir que todos os pontos de vista sejam considerados.
                </p>
                <br/>
                <p><strong>A sua opinião é extremamente relevante para o sucesso desta iniciativa.</strong></p>
                <br/>
                <p>Obrigado pela atenção e contamos com a sua participação!</p>
                ''',
                de=settings.DEFAULT_FROM_EMAIL,
                vinculos=[vinculo],
            )
            publico_notificado_qtd += 1

        self.publico_nao_respondente_data_notificacao = datetime.datetime.now()
        self.publico_nao_respondente_vinculo_notificador = vinculo_notificador
        self.save()

        return publico_notificado_qtd

    @classmethod
    def get_abertas(cls, vinculo):
        enquetes_abertas = set()
        enquetes = Enquete.objects.filter(data_inicio__lte=datetime.datetime.today(), data_fim__gte=datetime.datetime.today(), publicada=True)
        for enquete in enquetes:
            if enquete.eh_parte_publico(vinculo):
                enquetes_abertas.add(enquete)
        return enquetes_abertas

    @property
    def estah_aberta(self):
        return self.publicada and self.data_fim >= datetime.datetime.now()

    def get_respostas_objetivas(self, vinculo):
        qs = Resposta.objects.filter(pergunta__enquete=self, pergunta__objetiva=True)
        qs = qs.filter(vinculo=vinculo)
        return qs

    def eh_responsavel(self, user):
        return user.is_superuser or self.vinculos_responsaveis.filter(id=user.get_vinculo().id).exists()

    def tem_pergunta_sem_opcao(self):
        return (
            self.pergunta_set.filter(objetiva=True, opcoes__isnull=True).exists() and not self.opcao_set.filter(opcaopergunta__isnull=True).exists()
        )

    def get_descricao(self):
        return mark_safe(linebreaksbr(self.descricao))

    def pode_publicar(self):
        retorno = False
        if self.pergunta_set.exists():
            if self.pergunta_set.filter(objetiva=True).exists():
                retorno = not self.tem_pergunta_sem_opcao()
            else:
                retorno = True
        if not self.vinculos_relacionados_enquete.exists() and not self.publicocampi_set.exists():
            retorno = False
        return retorno

    def get_participantes(self):
        return (
            Vinculo.objects.filter(enquete_resposta_vinculo__pergunta__enquete=self)
            .annotate(data_cadastro=Max('enquete_resposta_vinculo__data_cadastro'))
            .distinct()
        )

    def get_status(self):
        if self.publicada:
            hoje = datetime.datetime.now()
            if self.data_inicio > hoje:
                return mark_safe('<span class="status status-alert">Aguardando publicação</span>')
            elif self.data_fim >= hoje:
                return mark_safe('<span class="status status-success">Publicada</span>')
            else:
                return mark_safe('<span class="status status-error">Expirada</span>')
        else:
            return mark_safe('<span class="status status-error">Privada</span>')

    def get_graficos_resultado(self, participantes, task):
        graficos = []
        self.categorias = self.get_perguntas_agrupadas_por_categoria()
        for categoria in task.iterate(self.categorias):
            categoria.cabecalho = []
            respostas = []
            for pergunta in categoria.perguntas:
                pergunta.respostas = pergunta.resposta_set.filter(vinculo__in=participantes).order_by('data_cadastro', 'vinculo__pessoa__nome')
                if pergunta.objetiva:
                    opcoes = pergunta.get_opcoes()
                    pergunta.resultado_opcoes = opcoes
                    dados_grafico = []
                    dados = pergunta.respostas.order_by('opcao__id').values('opcao__id').annotate(count=Count('opcao__id'))
                    # Removendo o order_by porque estava entrando no group_by e gerando agregações incorretas
                    for opcao in opcoes:
                        dados_opcao = dados.filter(opcao__id=opcao.id).first()
                        opcao.qtd = dados_opcao and dados_opcao['count'] or 0
                        dados_grafico.append([opcao.texto, opcao.qtd])

                    grafico = PieChart(f'grafico_pergunta_{pergunta.id:d}', title=pergunta.get_html(), data=dados_grafico)
                    grafico.id = f'grafico_pergunta_{pergunta.id:d}'
                    pergunta.grafico_id = grafico.id
                    graficos.append(grafico)

                categoria.cabecalho.append(pergunta)
                pergunta.respostas_dict = pergunta.get_respostas_dict()

                for participante in participantes:
                    if participante.id in pergunta.respostas_dict:
                        respostas.append(pergunta.respostas_dict[participante.id])
                    else:
                        respostas.append('-')

            x = len(categoria.cabecalho)
            if x > 0:
                y = len(respostas) / x
                array_respostas = np.array(respostas)
                categoria.tabela = array_respostas.reshape(x, int(y)).transpose().tolist()
        return graficos

    def can_change(self, user):
        return self.eh_responsavel(user)

    @transaction.atomic()
    def clonar(self):
        publicos = list(self.publicocampi_set.all())
        categorias = list(self.categoria_set.all())
        opcoes = list(self.opcao_set.filter(opcaopergunta__isnull=True).all())
        perguntas = list(self.pergunta_set.all())
        opcoes_pergunta = list(OpcaoPergunta.objects.filter(pergunta__enquete=self))
        vinculos_relacionados_enquete = list(self.vinculos_relacionados_enquete.all())
        vinculos_responsaveis = list(self.vinculos_responsaveis.all())
        vinculos_publico = list(self.vinculos_relacionados_enquete.all())
        enquete = Enquete.objects.get(pk=self.pk)
        enquete.id = None
        enquete.publicada = False
        enquete.save()
        enquete.vinculos_relacionados_enquete.set(vinculos_relacionados_enquete)
        enquete.vinculos_responsaveis.set(vinculos_responsaveis)
        enquete.vinculos_publico.set(vinculos_publico)
        mapa_categorias = {}
        mapa_perguntas = {}
        for obj in publicos:
            campi = list(obj.campi.all())
            setores = list(obj.setores.all())
            obj.id = None
            obj.enquete = enquete
            obj.save()
            obj.campi.set(campi)
            obj.setores.set(setores)
        for obj in categorias:
            pk = obj.id
            obj.id = None
            obj.enquete = enquete
            obj.save()
            mapa_categorias[pk] = obj.id
        for obj in opcoes:
            pk = obj.id
            obj.id = None
            obj.enquete = enquete
            obj.save()
        for obj in perguntas:
            pk = obj.id
            obj.id = None
            obj.enquete = enquete
            obj.categoria_id = mapa_categorias[obj.categoria_id]
            obj.save()
            mapa_perguntas[pk] = obj.id
        for obj in opcoes_pergunta:
            obj.id = None
            obj.opcao_ptr_id = None
            obj.opcao_ptr = None
            obj.enquete = enquete
            obj.pergunta_id = mapa_perguntas[obj.pergunta_id]
            obj.save()
        enquete.save()
        return enquete


class PublicoCampi(models.ModelPlus):
    enquete = models.ForeignKeyPlus(Enquete, on_delete=models.CASCADE)
    publico = models.ForeignKeyPlus(Publico, verbose_name='Público', on_delete=models.CASCADE)
    campi = models.ManyToManyFieldPlus('rh.UnidadeOrganizacional', verbose_name='Campi')
    setores = models.ManyToManyFieldPlus('rh.Setor', verbose_name='Setores')
    tipo_setor = models.CharFieldPlus(
        'Tipo de Setor do Funcionario/Servidor',
        choices=Publico.TIPO_SETOR_CHOICES,
        default=Publico.TIPO_SETOR_SUAP,
        help_text='Este setor será levado em consideração com relação aos campi escolhidos',
    )

    class Meta:
        verbose_name = 'Público Campi'
        verbose_name_plural = 'Públicos Campi'

    def __str__(self):
        siglas = []
        if self.id:  # if/else para evitar BUG de recursividade ao remover `self` pelo admin
            if self.setores.all().exists():
                for campus_sigla, campus_id in self.campi.all().values_list('sigla', 'id'):
                    campus_setores_siglas = self.setores.all().filter(uo=campus_id).values_list('sigla', flat=True)
                    nao_campus_setores_siglas = self.setores.all().exclude(uo=campus_id).values_list('sigla', flat=True)
                    sigla = f'{campus_sigla}'
                    if campus_setores_siglas:
                        sigla = f'{sigla} ({", ".join(campus_setores_siglas)})'
                    if nao_campus_setores_siglas:
                        sigla = f'{sigla} ({", ".join(nao_campus_setores_siglas)})'
                    siglas.append(sigla)
            else:
                siglas = self.campi.all().values_list('sigla', flat=True)
        return f' {self.publico} ({", ".join(siglas)})'


class Categoria(models.ModelPlus):
    enquete = models.ForeignKeyPlus(Enquete, on_delete=models.CASCADE)
    texto = models.TextField()
    orientacao = models.TextField('Orientação da Categoria', blank=True, help_text='Texto de orientação da Categoria da Enquete')
    ordem = models.IntegerField()

    class Meta:
        verbose_name = 'Categoria de Enquete'
        verbose_name_plural = 'Categorias de Enquete'

    def __str__(self):
        return self.texto

    def get_html(self):
        return mark_safe(linebreaksbr(self.texto))

    @transaction.atomic
    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        self.enquete.save()  # para despublicar se for o caso


class Pergunta(models.ModelPlus):
    TABELA = 'tabela'
    LISTA = 'lista'
    GALERIA = 'galeria'
    TIPO_LAYOUT = ((TABELA, 'Tabela'), (LISTA, 'Lista'), (GALERIA, 'Galeria'))

    enquete = models.ForeignKeyPlus(Enquete, on_delete=models.CASCADE)
    categoria = models.ForeignKeyPlus(Categoria, on_delete=models.CASCADE)
    layout = models.CharFieldPlus(
        verbose_name='Layout das Respostas', blank=True, choices=TIPO_LAYOUT, default=LISTA, help_text='Válido somente para perguntas objetivas'
    )
    texto = models.TextField(verbose_name='Título da Pergunta')
    numerico = models.BooleanField(
        'Campo Numérico',
        blank=True,
        default=False,
        help_text='Marque este campo caso a resposta deva ser apenas numérica, em caso de pergunta subjetiva.',
    )
    objetiva = models.BooleanField(default=True)
    multipla_escolha = models.BooleanField(verbose_name='Múltipla Escolha', default=False)
    ordem = models.IntegerField()
    obrigatoria = models.BooleanField(verbose_name='Obrigatória', default=False)

    class Meta:
        verbose_name = 'Pergunta'
        verbose_name_plural = 'Perguntas'
        ordering = ('ordem', 'id')

    def __str__(self):
        return self.texto

    def get_resposta(self, vinculo):
        respostas = self.resposta_set.filter(vinculo=vinculo)
        if not respostas.exists():
            return None

        if self.objetiva:
            if self.multipla_escolha:
                return list(respostas.values_list('opcao_id', flat=True))
            else:
                return respostas[0].opcao_id
        else:
            return respostas[0].resposta

    def salvar_resposta(self, vinculo, resposta_atual):
        uo = vinculo.setor.uo

        respostas = self.resposta_set.filter(vinculo=vinculo)
        if respostas.exists():
            if self.multipla_escolha:
                respostas_atuais = respostas.filter(opcao__in=resposta_atual)
                respostas_excluidas = respostas.exclude(opcao__in=resposta_atual)
                respostas_excluidas.delete()
                novas_respostas = resposta_atual.exclude(id__in=respostas_atuais.values_list('opcao', flat=True))
                for opcao in novas_respostas:
                    resposta = Resposta()
                    resposta.pergunta = self
                    resposta.resposta = ''
                    resposta.vinculo = vinculo
                    resposta.uo = uo
                    resposta.opcao = opcao
                    resposta.data_ultima_resposta = datetime.datetime.now()
                    resposta.save()
            else:
                if self.objetiva:
                    resposta = respostas[0]
                    resposta.opcao = resposta_atual
                else:
                    resposta = respostas[0]
                    resposta.resposta = resposta_atual

                resposta.data_ultima_resposta = datetime.datetime.now()
                resposta.uo = uo
                resposta.save()
        else:
            if self.multipla_escolha:
                for opcao in resposta_atual:
                    resposta = Resposta()
                    resposta.pergunta = self
                    resposta.resposta = ''
                    resposta.vinculo = vinculo
                    resposta.uo = uo
                    resposta.opcao = opcao
                    resposta.data_ultima_resposta = datetime.datetime.now()
                    resposta.save()
            else:
                resposta = Resposta()
                resposta.pergunta = self
                resposta.resposta = ''
                resposta.vinculo = vinculo
                resposta.uo = uo
                if self.objetiva:
                    resposta.opcao = resposta_atual
                else:
                    resposta.resposta = resposta_atual
                resposta.data_ultima_resposta = datetime.datetime.now()
                resposta.save()

    def get_html(self):
        return mark_safe(linebreaksbr(self.texto))

    def get_opcoes(self):
        opcoes = OpcaoPergunta.objects.filter(pergunta=self)
        if opcoes.exists():
            opcoes = opcoes.order_by('ordem')
        elif self.enquete.opcao_set.exists():
            opcoes = self.enquete.opcao_set.filter(opcaopergunta__isnull=True)
        return opcoes

    def get_respostas_dict(self):
        ret_dict = {}

        for resposta in self.resposta_set.all().order_by('data_cadastro'):
            ret_dict[resposta.vinculo_id] = resposta

        return ret_dict

    @transaction.atomic
    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        self.enquete.save()  # para despublicar se for o caso


class Opcao(models.ModelPlus):
    texto = models.TextField()
    enquete = models.ForeignKeyPlus(Enquete, on_delete=models.CASCADE)
    ordem = models.IntegerField()
    imagem = models.ImageFieldPlus(upload_to='enquete/opcao/imagem', blank=True)
    documento = models.FileFieldPlus(upload_to='enquete/opcao/documento', filetypes=['pdf'], blank=True)

    class Meta:
        verbose_name_plural = 'Opção de Enquete'
        verbose_name = 'Opções de Enquete'
        ordering = ('ordem',)

    def __str__(self):
        return self.texto

    def get_html(self):
        return mark_safe(linebreaksbr(self.texto))

    @transaction.atomic
    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        self.enquete.save()  # para despublicar se for o caso


class OpcaoPergunta(Opcao):
    pergunta = models.ForeignKeyPlus(Pergunta, related_name='opcoes', on_delete=models.CASCADE)

    class Meta:
        verbose_name_plural = 'Opção de Resposta'
        verbose_name = 'Opções de Resposta'
        ordering = ('ordem',)

    def get_html(self):
        return mark_safe(linebreaksbr(self.texto))


class Resposta(models.ModelPlus):
    referencia = models.CharField(max_length=255, null=True, blank=True)
    pergunta = models.ForeignKeyPlus(Pergunta, on_delete=models.CASCADE)
    uo = models.ForeignKeyPlus(UnidadeOrganizacional, related_name='enquete_resposta_uo_set', null=True, on_delete=models.CASCADE)
    resposta = models.TextField(help_text='Resposta')
    opcao = models.ForeignKeyPlus(Opcao, null=True, help_text='Resposta Objetiva', on_delete=models.CASCADE)
    vinculo = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Vínculo', related_name='enquete_resposta_vinculo', null=True)
    data_cadastro = models.DateTimeField('Data', auto_now_add=True)
    data_ultima_resposta = models.DateTimeField('Data da última resposta', null=True)

    class Meta:
        verbose_name = 'Resposta'
        verbose_name_plural = 'Respostas'

    def __str__(self):
        return str(self.opcao) if self.opcao else self.resposta

    def get_resposta(self):
        return mark_safe(linebreaksbr(self.resposta))
