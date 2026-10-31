import os.path
from datetime import date, datetime, timedelta

from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, F, Max, Prefetch, Q
from django.db.models.signals import m2m_changed
from django.forms.models import model_to_dict
from django.utils.html import escape

from comum.models import AreaAtuacao, User
from comum.utils import tl
from djtools.db import models
from djtools.utils import formata_nome_arquivo
from gerenciador_projetos.enums import DiaDaSemana, MesDoAno, PrioridadeTarefa, SituacaoProjeto, SituacaoTarefa, TipoRecorrencia, VisibilidadeProjeto
from gerenciador_projetos.utils import Notificar


GRUPO_MONITOR_PROJETOS = 'Monitor de Projetos'


class Projeto(models.ModelPlus):
    """areas e listas de tarefas"""

    areas = models.ManyToManyFieldPlus(AreaAtuacao, verbose_name='Áreas de Atuação')
    titulo = models.CharFieldPlus('Título')
    descricao = models.TextField('Descrição')
    projeto_pai = models.ForeignKeyPlus('gerenciador_projetos.Projeto', verbose_name='Projeto Pai', null=True, blank=True, on_delete=models.CASCADE)
    uo = models.ForeignKeyPlus('rh.UnidadeOrganizacional', verbose_name='Campus', related_name='gerenciador_projeto_campus')
    criado_em = models.DateTimeField(auto_now_add=True)
    criado_por = models.ForeignKeyPlus('comum.User', verbose_name='Criado Por', related_name='gerenciador_projeto_criado_por_set', blank=True)
    gerentes = models.ManyToManyField('comum.User', verbose_name='Gerentes', related_name='gerenciador_projeto_gerentes_set')
    interessados = models.ManyToManyField(
        'comum.User',
        verbose_name='Interessados',
        related_name='gerenciador_projeto_interessados_set',
        help_text='Interessados são usuários que possuem acesso de leitura a todas as informações do projeto.',
    )
    membros = models.ManyToManyField(
        'comum.User',
        verbose_name='Membros',
        related_name='gerenciador_projeto_membros_set',
        help_text='Membros são usuários que podem contribuir com o projeto no desenvolvimento de suas tarefas.',
    )
    visibilidade = models.CharFieldPlus('Visibilidade', default=VisibilidadeProjeto.PRIVADO, choices=VisibilidadeProjeto.choices)
    situacao = models.IntegerField('Situação', default=SituacaoProjeto.ABERTO, choices=SituacaoProjeto.choices)
    data_conclusao_estimada = models.DateFieldPlus('Data Estimada de Conclusão', null=True, blank=True)
    data_conclusao = models.DateFieldPlus('Data de Conclusão', null=True, blank=True)

    # origem = GenericForeignKey('content_type', 'object_id')

    class Meta:
        ordering = ['titulo']
        verbose_name = 'Projeto'
        verbose_name_plural = 'Projetos'

    def __str__(self):
        return self.titulo

    def get_absolute_url(self):
        return f'/gerenciador_projetos/projeto/{self.id}/'

    def save(self, *args, **kwargs):
        insert = not self.pk
        super().save(*args, **kwargs)
        if not insert and self.situacao == SituacaoProjeto.CONCLUIDO:
            for tarefa in self.tarefa_set.filter(data_conclusao__isnull=True):
                tarefa.fechar_tarefa()

    def clonar(self, user=None):
        if not user:
            user = tl.get_user()
        projeto = self

        tarefas = projeto.tarefas_raiz()
        tags = projeto.tag_set.all()
        projeto_listas = projeto.listaprojeto_set.all()
        areas = projeto.areas.all()

        projeto.id = None
        projeto.titulo = f'Cópia de {projeto.titulo}'
        projeto.criado_em = datetime.now()
        projeto.criado_por = user
        projeto.situacao = SituacaoProjeto.ABERTO
        projeto.save()

        projeto.gerentes.add(user)

        for area in areas:
            projeto.areas.add(area)

        # Clona todas as tags do projeto e armazena-as em um dicionário, onde
        # a chave é o pk da tag original e o valor é a tag correspondente clonada.
        dtags = {}
        for tag in tags:
            tagpk_ref = tag.pk
            tag.pk = None
            tag.save()
            dtags[tagpk_ref] = tag

        for projeto_lista in projeto_listas:
            projeto_lista.pk = None
            projeto_lista.projeto = projeto
            projeto_lista.save()

        for tarefa in tarefas:
            tarefa.projeto = projeto
            tarefa.clonar(user, dtags)

        return projeto

    def tarefas(self, tarefa=None):
        if tarefa:
            return self.tarefa_set.exclude(pk=tarefa.id)
        else:
            return self.tarefa_set.all()

    def tarefas_canceladas(self):
        return self.tarefa_set.filter(situacao=SituacaoTarefa.CANCELADA).order_by('prioridade')

    def tarefas_raiz(self, situacao=None, prioridade=None, tipo_ordenacao=''):
        qs = (
            Tarefa.objects_card()
            .filter(projeto=self, tarefa_pai__isnull=True)
            .prefetch_related(Prefetch('gerenciador_tarefa_pai_set', queryset=Tarefa.objects_card()))
            .exclude(situacao=SituacaoTarefa.CANCELADA)
        )
        if situacao:
            qs = qs.filter(situacao=situacao)
        ordenar_por = f'{tipo_ordenacao}prioridade'
        if prioridade:
            qs = qs.filter(prioridade=prioridade)

        return qs.order_by(ordenar_por)

    def tarefas_sem_lista(self, filtros=None):
        tarefas = Tarefa.objects_card().filter(projeto=self, lista__isnull=True)
        if filtros:
            tarefas = tarefas.filter(**filtros)
        return tarefas

    def tarefas_por_lista(self, lista, filtros=None):
        tarefas = self.tarefa_set.filter(lista=lista)
        if filtros:
            tarefas = tarefas.filter(**filtros)
        return tarefas

    def listas_do_projeto(self):
        return self.listaprojeto_set.order_by('posicao')

    def total_progresso_automatico(self) -> str:
        # A regra (média das tarefas raiz; a raiz com subtarefas vale a fração delas concluída)
        # mora em `portfolio.progresso_por_projeto`, que a calcula para N projetos numa query.
        # Import local: `portfolio` importa este módulo.
        from gerenciador_projetos.portfolio import progresso_por_projeto

        return f'{progresso_por_projeto([self])[self.pk]:.0f}'

    def tarefas_ativas(self):
        return self.tarefa_set.filter(data_conclusao__isnull=True)

    def previsao_conclusao(self):
        d = {'titulo': '', 'valor': ''}
        if self.data_conclusao:
            d = {'titulo': 'Projeto concluído em', 'valor': self.data_conclusao}
        elif self.data_conclusao_estimada:
            if date.today() > self.data_conclusao_estimada:
                retorno = date.today() - self.data_conclusao_estimada
                d = {'titulo': 'Tempo ultrapassado', 'valor': timedelta(seconds=retorno.total_seconds())}
            else:
                retorno = self.data_conclusao_estimada - date.today()
                d = {'titulo': 'Conclusão prevista', 'valor': timedelta(seconds=retorno.total_seconds())}
        return d

    def eh_gerente_projeto(self, user=None):
        if not user:
            user = tl.get_user()
        return user in self.gerentes.all()

    def eh_membro_projeto(self, user=None):
        if not user:
            user = tl.get_user()
        return user in self.membros.all()

    def eh_interessado_projeto(self, user=None):
        if not user:
            user = tl.get_user()
        return user in self.interessados.all()

    @staticmethod
    def eh_monitor_projetos(user: User) -> bool:
        """Grupo atribuído à mão (ex.: a gestão estratégica): lê os projetos públicos sem estar na equipe e sem editar."""
        return user.groups.filter(name=GRUPO_MONITOR_PROJETOS).exists()

    def pode_ver_projeto(self, user: User | None = None) -> bool:
        if not user:
            user = tl.get_user()
        if self.eh_gerente_projeto(user) or self.eh_membro_projeto(user) or self.eh_interessado_projeto(user):
            return True
        # Privado pode ter dados sensíveis (senhas de acesso, servidores): fica só com a equipe.
        return self.visibilidade == VisibilidadeProjeto.PUBLICO and self.eh_monitor_projetos(user)

    def pode_editar_projeto(self, user=None):
        if not user:
            user = tl.get_user()
        return self.eh_gerente_projeto(user) or user.is_superuser

    def pode_adicionar_comentarios(self, user=None):
        if not user:
            user = tl.get_user()
        return self.eh_gerente_projeto(user) or self.eh_membro_projeto(user) or user.is_superuser

    def pode_adicionar_tarefas(self, user: User | None = None) -> bool:
        if not user:
            user = tl.get_user()
        if self.situacao in (SituacaoProjeto.CONCLUIDO, SituacaoProjeto.CANCELADO):
            return False
        return self.eh_gerente_projeto(user) or self.eh_membro_projeto(user) or user.is_superuser

    def pode_editar_tarefas(self, user=None):
        if not user:
            user = tl.get_user()
        return self.eh_gerente_projeto(user) or self.eh_membro_projeto(user) or user.is_superuser

    def pode_adicionar_listas(self, user=None):
        if not user:
            user = tl.get_user()
        return self.eh_gerente_projeto(user) or user.is_superuser

    def pode_editar_listas(self, user=None):
        if not user:
            user = tl.get_user()
        return self.eh_gerente_projeto(user) or user.is_superuser

    def pode_editar_tags(self, user=None):
        if not user:
            user = tl.get_user()
        return self.eh_gerente_projeto(user) or user.is_superuser

    @property
    def concluido(self):
        return self.situacao == SituacaoProjeto.CONCLUIDO

    @property
    def encerrado(self) -> bool:
        """Concluído ou Cancelado: as tarefas dele ficam somente leitura (para mexer, reabre o projeto)."""
        return self.situacao in (SituacaoProjeto.CONCLUIDO, SituacaoProjeto.CANCELADO)


class Tag(models.ModelPlus):
    COR_CHOICE = (
        ('warning', 'Amarelo'),
        ('info', 'Azul'),
        ('extra', 'Laranja'),
        ('extra2', 'Roxo'),
        ('success', 'Verde'),
        ('error', 'Vermelho'),
        ('none', 'Nenhum'),
    )

    nome = models.CharFieldPlus('Nome', help_text='Informe um nome para tag')
    cor = models.CharFieldPlus('Cor', help_text='Informe uma cor para tag', choices=COR_CHOICE, default='info')
    projeto = models.ForeignKeyPlus(Projeto, verbose_name='Projeto')

    class Meta:
        ordering = ['nome']
        verbose_name = 'Tag'
        verbose_name_plural = 'Tags'

    def __str__(self):
        return self.nome


class Lista(models.ModelPlus):
    nome = models.CharFieldPlus('Nome', help_text='Informe um nome para a lista')
    ativa = models.BooleanField('Ativa', default=True, null=False)
    criada_por = models.ForeignKeyPlus(
        'comum.User', verbose_name='Criada Por', related_name='gerenciador_projeto_criada_por_set', null=True, blank=True
    )

    class Meta:
        ordering = ['nome']
        verbose_name = 'Lista'
        verbose_name_plural = 'Listas'

    def __str__(self):
        return self.nome

    @classmethod
    def get_disponiveis(cls, usuario, projeto):
        return Lista.objects.filter(criada_por=usuario)

    def get_tarefas(self, projeto, filtros=None):
        """Retorna uma Lista de Tarefas da Lista Corrente ordenada pela posição"""
        tarefas = (
            Tarefa.objects_card()
            .filter(projeto=projeto, listatarefa__lista=self, listatarefa__data_hora_saida__isnull=True)
            .annotate(posicao=F('listatarefa__posicao'))
        )
        if filtros:
            tarefas = tarefas.filter(**filtros)
        return tarefas.order_by('posicao')


class TipoAtividade(models.ModelPlus):
    nome = models.CharFieldPlus('Nome')

    class Meta:
        ordering = ['nome']
        verbose_name = 'Tipo de Atividade'
        verbose_name_plural = 'Tipos de Atividade'

    def __str__(self):
        return self.nome


class ItemChecklist(models.ModelPlus):
    tarefa = models.ForeignKey('gerenciador_projetos.Tarefa', related_name='itens_checklist', on_delete=models.CASCADE)
    descricao = models.CharField(max_length=255, verbose_name='Descrição')
    concluido = models.BooleanField(default=False, verbose_name='Concluído')
    posicao = models.PositiveSmallIntegerField('Posição', default=0)

    class Meta:
        ordering = ['posicao']
        verbose_name = 'Item do Checklist'
        verbose_name_plural = 'Itens do Checklist'

    def __str__(self) -> str:
        return self.descricao


class Tarefa(models.ModelPlus):
    titulo = models.CharFieldPlus('Título')
    descricao = models.TextField('Descrição', null=True, blank=True)
    projeto = models.ForeignKeyPlus(Projeto, verbose_name='Projeto')
    tipo_atividade = models.ForeignKeyPlus(TipoAtividade, null=True, verbose_name='Tipo de Atividade')
    criado_por = models.ForeignKeyPlus('comum.User')
    atribuido_a = models.ManyToManyFieldPlus('comum.User', verbose_name='Atribuído a', related_name='gerenciador_tarefa_atribuido_a_set')
    atribuido_por = models.ForeignKeyPlus('comum.User', verbose_name='Atribuído por', null=True, related_name='gerenciador_tarefa_atribuido_por_set')
    prioridade = models.CharFieldPlus('Prioridade', max_length=10, default=PrioridadeTarefa.MEDIA, choices=PrioridadeTarefa.choices)
    aberto_em = models.DateTimeField('Aberto Em', auto_now_add=True)
    data_inicio = models.DateFieldPlus('Data de Início', null=True, blank=True)
    data_conclusao_estimada = models.DateFieldPlus('Data Estimada de Conclusão', null=True, blank=True)
    data_conclusao = models.DateFieldPlus('Data de Conclusão', null=True, blank=True)
    situacao = models.IntegerField('Situação', default=SituacaoTarefa.ABERTA, choices=SituacaoTarefa.choices)
    observadores = models.ManyToManyField(
        'comum.User',
        related_name='gerenciador_tarefa_observadores_set',
        verbose_name='Observadores',
        help_text='Vincule a esta tarefa usuários que podem ter interesse em acompanhar o andamento da mesma.',
    )
    tarefa_pai = models.ForeignKey(
        'gerenciador_projetos.Tarefa',
        verbose_name='Tarefa Pai',
        related_name='gerenciador_tarefa_pai_set',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    lista = models.ForeignKeyPlus(Lista, verbose_name='Lista', null=True, blank=True, on_delete=models.SET_NULL)
    tags = models.ManyToManyFieldPlus(
        Tag,
        related_name='gerenciador_projetos_tags_set',
        verbose_name='Tags',
        blank=True,
        help_text='Vincule tags nesta tarefa para facilitar a identificação da mesma.',
    )
    percentual_executado = models.PositiveSmallIntegerField('Percentual executado', null=True, blank=True, default=0)
    uo = models.ForeignKeyPlus('rh.UnidadeOrganizacional', verbose_name='Campus', null=True, blank=True, on_delete=models.SET_NULL)

    # origem = GenericForeignKey('content_type', 'object_id')

    PROGRESSOS_RAPIDOS: tuple[int, ...] = (0, 25, 50, 75, 100)

    class Meta:
        ordering = ['data_inicio', 'data_conclusao', 'pk']
        verbose_name = 'Tarefa'
        verbose_name_plural = 'Tarefas'

    def __str__(self):
        return self.titulo

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__initial = self._dict

    def get_absolute_url(self):
        return f'/gerenciador_projetos/tarefa/{self.id}/'

    def get_situacao_tarefa_css(self):
        match self.situacao:
            case SituacaoTarefa.ABERTA:
                return 'info'
            case SituacaoTarefa.EM_ANDAMENTO:
                return 'warning'
            case SituacaoTarefa.CONCLUIDA:
                return 'success'
            case SituacaoTarefa.SUSPENSA:
                return 'extra'
            case SituacaoTarefa.CANCELADA:
                return 'error'
            case SituacaoTarefa.EM_ANALISE:
                return 'warning'
        return ''

    @classmethod
    def objects_card(cls):
        return (
            cls.objects.select_related('projeto', 'lista', 'uo')
            .prefetch_related('tags', 'atribuido_a', 'observadores')
            .annotate(
                qtd_tags=Count('tags', distinct=True),
                qtd_atribuido_a=Count('atribuido_a', distinct=True),
                qtd_observadores=Count('observadores', distinct=True),
                qtd_subtarefas=Count('gerenciador_tarefa_pai_set', distinct=True),
                qtd_subtarefas_concluidas=Count(
                    'gerenciador_tarefa_pai_set',
                    filter=Q(gerenciador_tarefa_pai_set__data_conclusao__isnull=False),
                    distinct=True,
                ),
                qtd_historicoevolucao=Count(
                    'historicoevolucao',
                    filter=~Q(historicoevolucao__comentario__exact=''),
                    distinct=True,
                ),
                qtd_anexos=Count(
                    'historicoevolucao',
                    filter=Q(historicoevolucao__anexo__isnull=False) & ~Q(historicoevolucao__anexo=''),
                    distinct=True,
                ),
            )
        )

    def get_historicoevolucao(self):
        return self.historicoevolucao_set.exclude(comentario__exact='').order_by('-data_hora')

    def get_anexos(self):
        return self.historicoevolucao_set.exclude(anexo='').order_by('-data_hora')

    def get_subtarefas(self):
        return self.gerenciador_tarefa_pai_set.all()

    def get_subtarefas_nao_concluidas(self):
        return self.gerenciador_tarefa_pai_set.exclude(data_conclusao__isnull=False)

    def get_subtarefas_concluidas(self):
        return self.gerenciador_tarefa_pai_set.exclude(data_conclusao__isnull=True)

    def total_progresso_automatico_numero(self):
        quantidade_tarefas = self.get_subtarefas().count()
        percentual = 0
        if quantidade_tarefas:
            # Possui subtarefas
            # - Contabiliza considerando apenas as subtarefas
            percentual = 100 - (self.get_subtarefas_nao_concluidas().count() * 100) / (quantidade_tarefas)
        else:
            # Nao possui subtarefas
            # - Contabiliza considerando apenas ela mesma
            if self.situacao == SituacaoTarefa.CONCLUIDA:
                percentual = 100
        return percentual

    def get_listaatual(self):
        return self.listatarefa_set.get(data_hora_saida__isnull=True)

    def mover_para_lista(self, lista: Lista | None, usuario: User) -> None:
        """Move a tarefa para a lista informada, atualizando o campo `lista` denormalizado
        e encerrando/criando os registros de histórico em `ListaTarefa` usados pelo dashboard
        (kanban). Passar `None` apenas remove a tarefa de sua lista atual."""
        ListaTarefa.objects.filter(tarefa=self, data_hora_saida__isnull=True).update(data_hora_saida=datetime.now())
        if lista is not None:
            maior_posicao = ListaTarefa.objects.filter(lista=lista, tarefa=self).aggregate(m=Max('posicao'))['m'] or 0
            ListaTarefa.objects.create(lista=lista, tarefa=self, posicao=maior_posicao + 1, registrado_por=usuario)
        self.lista = lista
        self.save()

    def atualizar_atribuicoes(self, users: list[User], usuario_que_alterou: User) -> None:
        """Substitui o conjunto de atribuídos da tarefa. Notificação e histórico
        precisam ser explícitos porque `atribuido_a` é M2M e não entra no diff do
        `save()`."""
        atribuidos_anteriores = list(self.atribuido_a.all())
        self.atribuido_por = usuario_que_alterou
        self.save(registrar_historico=False)
        self.atribuido_a.set(users)
        self._registrar_historico_atribuicoes(atribuidos_anteriores, users, usuario_que_alterou)

    def _registrar_historico_atribuicoes(self, anteriores: list[User], atuais: list[User], usuario_que_alterou: User) -> None:
        anteriores_por_id = {usuario.pk: usuario for usuario in anteriores}
        atuais_por_id = {usuario.pk: usuario for usuario in atuais}
        adicionados = [atuais_por_id[pk] for pk in sorted(atuais_por_id.keys() - anteriores_por_id.keys())]
        removidos = [anteriores_por_id[pk] for pk in sorted(anteriores_por_id.keys() - atuais_por_id.keys())]
        if not adicionados and not removidos:
            return
        comentario = f'Atribuições alteradas por {escape(usuario_que_alterou)}.'
        if adicionados:
            comentario += f'\nAtribuídos adicionados: {self._formatar_usuarios_historico(adicionados)}.'
        if removidos:
            comentario += f'\nAtribuídos removidos: {self._formatar_usuarios_historico(removidos)}.'
        HistoricoEvolucao.objects.create(tarefa=self, registrado_por=usuario_que_alterou, mensagem_automatica=True, comentario=comentario)

    @staticmethod
    def _formatar_usuarios_historico(usuarios: list[User]) -> str:
        return ', '.join(escape(usuario) for usuario in usuarios)

    @property
    def encerrada(self) -> bool:
        """Concluída ou Cancelada, pela situação (`concluida` olha só a data de conclusão)."""
        return self.situacao in (SituacaoTarefa.CONCLUIDA, SituacaoTarefa.CANCELADA)

    @property
    def bloqueada_para_novas_acoes(self) -> bool:
        """Somente leitura: tarefa Concluída, Cancelada ou Suspensa, ou de projeto encerrado.

        Bloqueia editar, subtarefa, evolução, comentário, anexo, link, checklist, progresso,
        atribuições, recorrência e campus. Continuam valendo ver, observar, clonar e excluir
        (estes dois, fora de projeto encerrado), além das saídas `pode_alterar_situacao`
        (Suspensa retoma) e `pode_reabrir` (encerrada volta a Aberta).
        """
        return self.situacao == SituacaoTarefa.SUSPENSA or self.encerrada or self.projeto.encerrado

    @property
    def pode_alterar_situacao(self) -> bool:
        return not self.encerrada and not self.projeto.encerrado

    @property
    def pode_reabrir(self) -> bool:
        return self.encerrada and not self.projeto.encerrado

    def get_situacoes_disponiveis(self) -> list[tuple[int, str]]:
        """Situações para as quais esta tarefa pode ser movida, exibidas no menu
        "Alterar situação" — todas exceto a situação atual."""
        return [(codigo, rotulo) for codigo, rotulo in SituacaoTarefa.choices if codigo != self.situacao]

    def atribuir_para(self, users: User | list[User] | None = None) -> Tarefa:
        """Atribui a tarefa a um ou mais usuários. A notificação de quem foi
        recém-adicionado é disparada pelo signal `m2m_changed` de `atribuido_a`
        (`gerenciador_projetos/signals.py`), não aqui."""
        tarefa = self
        tarefa.atribuido_a.add(users)
        tarefa.save()
        return tarefa

    @transaction.atomic()
    def reabrir(self, usuario: User) -> None:
        if self.projeto.encerrado:
            raise ValidationError('Não é possível reabrir tarefa em um projeto concluído ou cancelado.')
        elif not self.encerrada:
            raise ValidationError('A tarefa não está concluída nem cancelada para ser reaberta.')
        else:
            # Cria o histórico da Reabertura

            historico = HistoricoEvolucao()
            historico.tarefa = self
            anterior = (
                f'Data da conclusão anterior era {self.data_conclusao.strftime("%d/%m/%Y")}.'
                if self.data_conclusao
                else f'Situação anterior: {self.get_situacao_display()}.'
            )
            historico.comentario = f'Tarefa reaberta por {usuario.get_vinculo().pessoa.nome}. {anterior}'
            historico.registrado_por = usuario
            historico.mensagem_automatica = True
            historico.save()

            self.data_conclusao = None
            self.percentual_executado = 0
            self.situacao = SituacaoTarefa.ABERTA
            self.save()

            HistoricoEvolucao.objects.create(tarefa=self, registrado_por=tl.get_user(), mensagem_automatica=True, comentario='Tarefa reaberta')

    def clonar(self, user=None, dtags=None, manter_atendentes=False, manter_checklist=False):
        """
        :param user: usuário logado
        :param dtags: dicionário onde a chave é o pk da TAG anterior e o valor é o pk da nova TAG
        :param manter_atendentes: boolean informando se deve manter os atendentes da tarefa original na nova tarefa
        :param manter_checklist: boolean informando se deve manter o checklist da tarefa original na nova tarefa
        :return:
        """
        tarefa = self
        tags = tarefa.tags.all()
        subtarefas = list(self.get_subtarefas())  # Força o carregamento de subtarefas
        atribuido_a = list(tarefa.atribuido_a.all())  # Força o carregamento dos atendentes
        itens_checklist = list(tarefa.itens_checklist.all())  # Força o carregamento dos itens

        tarefa.data_inicio = datetime.now()
        tarefa.aberto_em = datetime.now()
        tarefa.data_conclusao = None
        tarefa.data_conclusao_estimada = None
        tarefa.id = None
        # Este método pode ser executado a partir do comando gp_tarefas_recorrentes ou a partir da funcionalidade clonar Projeto.
        # Quando o usário for informado, significa que o método foi executado a partir da funcionalidade clonar Projeto
        if user:
            tarefa.criado_por = user
            tarefa.data_inicio = None
            tarefa.lista = None

        tarefa.save()

        if manter_atendentes and len(atribuido_a) > 0:
            tarefa.atribuido_a.set(atribuido_a)
            tarefa.atribuido_por = user

        if manter_checklist and len(itens_checklist) > 0:
            for item in itens_checklist:
                ItemChecklist.objects.create(tarefa=tarefa, descricao=item.descricao)

        # Nova tarefa (tarefa clonada) referencia a nova tag correspondente.
        if dtags:
            for tag in tags:
                tarefa.tags.add(dtags[tag.pk])

        for subtarefa in subtarefas:
            subtarefa.projeto = tarefa.projeto
            subtarefa.tarefa_pai = tarefa

            # if manter_atendentes and tarefa.atribuido_a.exists():
            #     subtarefa.atribuido_a.set(tarefa.atribuido_a)
            #     subtarefa.atribuido_por = user
            #
            # if manter_checklist and subtarefa.itens_checklist.exists():
            #     for item in subtarefa.itens_checklist.all():
            #         ItemChecklist.objects.create(tarefa=subtarefa, descricao=item.descricao)

            subtarefa.clonar(user, dtags, manter_atendentes, manter_checklist)
        return tarefa

    @property
    def _dict(self):
        return model_to_dict(self, fields=[field.name for field in self._meta.fields])

    @property
    def diff(self):
        d1 = self.__initial
        d2 = self._dict
        diffs = [(k, (v, d2[k])) for k, v in list(d1.items()) if v != d2[k]]
        return dict(diffs)

    @property
    def diff_verbose(self):
        choices_map = {
            'prioridade': PrioridadeTarefa.choices,
            'situacao': SituacaoTarefa.choices,
        }
        retorno = ['<ul>']
        for str_field in self.changed_fields:
            field = Tarefa._meta.get_field(str_field)
            field_diff = self.get_field_diff(str_field)
            if field.is_relation:
                model = Tarefa._meta.get_field(str_field).related_model
                obj_antigo = 'vazio' if not field_diff[0] else model.objects.get(pk=field_diff[0])
                obj_novo = 'vazio' if not field_diff[1] else model.objects.get(pk=field_diff[1])
                retorno.append(f'<li>Campo <b>{field.verbose_name}</b> alterado de <i>{obj_antigo}</i> para <i>{obj_novo}</i>. </li>')
            elif isinstance(field, models.DateField):
                data0 = 'vazio' if not field_diff[0] else field_diff[0].strftime('%d/%m/%Y')
                data1 = 'vazio' if not field_diff[1] else field_diff[1].strftime('%d/%m/%Y')
                retorno.append(f'<li>Campo <b>{field.verbose_name}</b> alterado de <i>{data0}</i> para <i>{data1}</i>. </li>')
            elif field.attname in choices_map:
                field_choices = dict(choices_map.get(field.attname, []))
                verbose_field_diff_0 = field_choices.get(field_diff[0])
                verbose_field_diff_1 = field_choices.get(field_diff[1])
                retorno.append(
                    f'<li>Campo <b>{field.verbose_name}</b> alterado de <i>{verbose_field_diff_0}</i> para <i>{verbose_field_diff_1}</i>. </li>'
                )
            else:
                retorno.append(f'<li>Campo <b>{field.verbose_name}</b> alterado de <i>{field_diff[0]}</i> para <i>{field_diff[1]}</i>. </li>')
        retorno.append('</ul>')
        return ''.join(retorno)

    @property
    def has_changed(self):
        return bool(self.diff)

    @property
    def changed_fields(self):
        return list(self.diff.keys())

    @property
    def concluida(self):
        hoje = date.today()
        return self.data_conclusao and self.data_conclusao <= hoje

    @property
    def data_estimada_ultrapassada(self) -> bool:
        return bool(self.data_conclusao_estimada and not self.data_conclusao and self.data_conclusao_estimada < date.today())

    def get_field_diff(self, field_name):
        """
        Returns a diff for field if it's changed and None otherwise.
        """
        return self.diff.get(field_name, 'vazio')

    def fechar_tarefa(self, data=None):
        """Marca a tarefa como concluída. Não registra histórico manualmente: `save()`
        já cria uma entrada automática com o diff dos campos alterados (situação, data de
        conclusão, percentual executado), então um create aqui duplicaria a entrada."""
        if not data:
            data = date.today()
        self.data_conclusao = data
        self.percentual_executado = 100
        self.situacao = SituacaoTarefa.CONCLUIDA
        self.save()

    def alterar_progresso(self, percentual: int) -> None:
        """Atualiza o percentual executado da tarefa. Ao atingir 100%, delega a
        `fechar_tarefa()` para também concluir a tarefa (situação e data de conclusão)."""
        self.percentual_executado = percentual
        if percentual == 100:
            self.fechar_tarefa()
        else:
            if 0 < percentual < 100:
                self.situacao = SituacaoTarefa.EM_ANDAMENTO
            self.save()

    def save(self, *args: object, registrar_historico: bool = True, **kwargs: object) -> None:
        insert = not self.pk
        if not insert and self.get_field_diff('data_conclusao') != 'vazio' and self.data_conclusao:
            self.percentual_executado = 100
            self.situacao = SituacaoTarefa.CONCLUIDA
            for tarefa in self.get_subtarefas_nao_concluidas():
                tarefa.fechar_tarefa()

        # Captura o diff da situação depois da regra acima (que pode alterá-la
        # automaticamente ao concluir a tarefa) e antes de `self.__initial` ser
        # atualizado ao final, para refletir a mudança efetiva desta gravação.
        diff_situacao = None if insert else self.get_field_diff('situacao')

        super().save(*args, **kwargs)
        if insert:
            HistoricoEvolucao.objects.create(tarefa=self, registrado_por=tl.get_user(), mensagem_automatica=True, comentario='Tarefa criada')

        if not insert and self.has_changed and registrar_historico:
            HistoricoEvolucao.objects.create(tarefa=self, registrado_por=tl.get_user(), mensagem_automatica=True, comentario=self.diff_verbose)

        if diff_situacao not in (None, 'vazio'):
            situacao_anterior_label = dict(SituacaoTarefa.choices)[diff_situacao[0]]
            Notificar.situacao_tarefa_alterada(self, situacao_anterior_label, self.get_situacao_display(), tl.get_user())

        self.__initial = self._dict


def anexos_da_tarefa_path(instance, filename):
    filename = formata_nome_arquivo(filename)
    return f'gerenciador_projeto/projeto/{instance.tarefa.projeto.id}/tarefa_{instance.tarefa.id}/{filename}'


class HistoricoEvolucao(models.ModelPlus):
    tarefa = models.ForeignKeyPlus(Tarefa, verbose_name='Tarefa')
    comentario = models.TextField('Comentário', null=True, blank=True)
    data_hora = models.DateTimeField(auto_now_add=True)
    registrado_por = models.ForeignKeyPlus(
        'comum.User', verbose_name='Registrado Por', related_name='gerenciador_historico_evolucao_registrado_por_set', null=True, blank=False
    )
    anexo = models.PrivateFileField(
        verbose_name='Anexo',
        upload_to=anexos_da_tarefa_path,
        filetypes=['pdf', 'jpeg', 'jpg', 'png'],
        help_text='O formato do arquivo deve ser ".pdf", ".jpeg", ".jpg" ou ".png"',
        null=True,
        blank=True,
    )
    historicoevolucao_pai = models.ForeignKey(
        'gerenciador_projetos.HistoricoEvolucao',
        verbose_name='Histórico de Evolução Pai',
        related_name='gerenciador_historicoevolucao_pai_set',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    data_conclusao = models.DateFieldPlus(
        'Data de Conclusão', null=True, blank=True, help_text='Ao concluir esta tarefa, todas as suas subtarefas também serão concluídas'
    )
    mensagem_automatica = models.BooleanField('Mensagem Automática?', default=False)
    percentual_executado = models.PositiveSmallIntegerField('Percentual executado', null=True, blank=True)

    def __str__(self):
        return f'Histórico de Evolução (Tarefa #{self.tarefa.id}) - {self.comentario}'

    class Meta:
        ordering = ['tarefa', 'data_hora']
        verbose_name = 'Histórico de Evolução'
        verbose_name_plural = 'Histórico de Evolução'

    def nomeanexo(self):
        return os.path.basename(self.anexo.name)

    def clean(self):
        if not self.comentario and not self.anexo and not self.data_conclusao:
            raise ValidationError('É necessário informar pelo menos um dos campos para registrar a evolução.')

        if self.tarefa.bloqueada_para_novas_acoes:
            raise ValidationError('Não é possível registrar histórico em tarefa concluída, cancelada, suspensa ou de projeto encerrado.')

    def save(self, *args: object, **kwargs: object) -> None:
        if not self.comentario and self.anexo:
            self.comentario = 'Arquivo anexado.'
        super().save(*args, **kwargs)
        if self.mensagem_automatica is False and self.data_conclusao:
            self.tarefa.fechar_tarefa(self.data_conclusao)
        elif self.percentual_executado is not None:
            self.tarefa.alterar_progresso(self.percentual_executado)


class LinkTarefa(models.ModelPlus):
    tarefa = models.ForeignKeyPlus(Tarefa, verbose_name='Tarefa', related_name='links')
    titulo = models.CharFieldPlus('Título')
    url = models.URLField('URL', max_length=500)
    criado_por = models.ForeignKeyPlus('comum.User', verbose_name='Criado Por', related_name='gerenciador_link_tarefa_criado_por_set')
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-criado_em']
        verbose_name = 'Link da Tarefa'
        verbose_name_plural = 'Links da Tarefa'

    def __str__(self) -> str:
        return self.titulo

    def pode_editar(self, user: User | None = None) -> bool:
        """Verdadeiro quando o usuário pode editar ou remover este link: gerente do
        projeto da tarefa, atribuído à tarefa, ou superusuário."""
        if not user:
            user = tl.get_user()
        tarefa = self.tarefa
        return tarefa.projeto.eh_gerente_projeto(user) or tarefa.atribuido_a.filter(pk=user.pk).exists() or user.is_superuser


class ListaTarefa(models.ModelPlus):
    lista = models.ForeignKeyPlus(Lista, verbose_name='Lista')
    tarefa = models.ForeignKeyPlus(Tarefa, verbose_name='Tarefa')
    posicao = models.PositiveSmallIntegerField('Posição')
    registrado_por = models.ForeignKeyPlus('comum.User', verbose_name='Registrado Por', related_name='gerenciador_lista_tarefa_registrado_por_set')
    data_hora_entrada = models.DateTimeField(auto_now_add=True)
    data_hora_saida = models.DateTimeField('Data/Hora Saída', null=True, help_text='Informa a data/hora que a tarefa foi removida desta lista.')

    class Meta:
        ordering = ['lista', 'posicao']
        verbose_name = 'Lista de Tarefas'
        verbose_name_plural = 'Listas de Tarefas'

    def __str__(self):
        return f'{self.lista.nome} - ({self.posicao}) {self.tarefa.titulo}'


class ListaProjeto(models.ModelPlus):
    lista = models.ForeignKeyPlus(Lista, verbose_name='Lista')
    projeto = models.ForeignKeyPlus(Projeto, verbose_name='Projeto')
    posicao = models.PositiveSmallIntegerField('Posição')

    class Meta:
        ordering = ['lista', 'posicao']
        verbose_name = 'Lista de Tarefas Por Projeto'
        verbose_name_plural = 'Listas de Tarefas Por Projeto'

    def __str__(self):
        return f'{self.lista.nome} - ({self.posicao}) {self.projeto.titulo}'


class RecorrenciaTarefa(models.ModelPlus):
    tarefa = models.ForeignKeyPlus(Tarefa, verbose_name='Tarefa')
    tipo_recorrencia = models.IntegerField('Tipo de Recorrência', choices=TipoRecorrencia.choices)
    dia_da_semana = models.PositiveSmallIntegerField('Dia da Semana', null=True, blank=True, choices=DiaDaSemana.choices)
    dia_do_mes = models.PositiveSmallIntegerField('Dia do Mês', null=True, blank=True)
    mes_do_ano = models.PositiveSmallIntegerField('Mês do Ano', null=True, blank=True, choices=MesDoAno.choices)
    data_fim = models.DateFieldPlus('Data Final', null=True, blank=True)

    class Meta:
        ordering = ['tarefa', 'tipo_recorrencia']
        verbose_name = 'Recorrência da Tarefa'
        verbose_name_plural = 'Recorrências da Tarefa'

    def __str__(self):
        inicio = f'{self.get_tipo_recorrencia_display()}'
        fim = ''
        if self.tipo_recorrencia == TipoRecorrencia.SEMANALMENTE:
            fim = f', todas as {self.get_dia_da_semana_display()}'
        elif self.tipo_recorrencia == TipoRecorrencia.MENSALMENTE:
            fim = f', dia {self.dia_do_mes} de cada mês'
        elif self.tipo_recorrencia == TipoRecorrencia.ANUALMENTE:
            fim = f', na data {self.dia_do_mes}/{self.mes_do_ano}'

        return inicio + fim


""" signals """


def adiciona_permissao_apos_salvar_gerentes(sender, **kwargs):
    group = Group.objects.get(name='Gerente de Projeto')
    usuarios_sem_permissao = User.objects.filter(gerenciador_projeto_gerentes_set__isnull=False).exclude(groups=group)
    for user in usuarios_sem_permissao:
        user.groups.add(group)


m2m_changed.connect(adiciona_permissao_apos_salvar_gerentes, sender=Projeto.gerentes.through)


def adiciona_permissao_apos_salvar_membros(sender, **kwargs):
    group = Group.objects.get(name='Membro de Projeto')
    usuarios_sem_permissao = User.objects.filter(gerenciador_projeto_membros_set__isnull=False).exclude(groups=group)
    for user in usuarios_sem_permissao:
        user.groups.add(group)


m2m_changed.connect(adiciona_permissao_apos_salvar_membros, sender=Projeto.membros.through)


def adiciona_permissao_apos_salvar_interessados(sender, **kwargs):
    group = Group.objects.get(name='Interessado do Projeto')
    usuarios_sem_permissao = User.objects.filter(gerenciador_projeto_interessados_set__isnull=False).exclude(groups=group)
    for user in usuarios_sem_permissao:
        user.groups.add(group)


m2m_changed.connect(adiciona_permissao_apos_salvar_interessados, sender=Projeto.interessados.through)
