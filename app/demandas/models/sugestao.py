from django.core.exceptions import PermissionDenied
from django.core.validators import FileExtensionValidator
from django.urls import reverse

from comum.models import User
from comum.utils import tl
from demandas.utils import Notificar
from djtools.db import models
from djtools.db.models import ModelPlus


class SugestaoMelhoria(models.Model):
    SITUACAO_PENDENTE = '1'
    SITUACAO_EM_ANALISE = '2'
    SITUACAO_SUSPENSA = '3'
    SITUACAO_DEFERIDA = '4'
    SITUACAO_INDEFERIDA = '5'
    SITUACAO_CANCELADA = '6'
    SITUACAO_IMPLEMENTADA = '7'
    SITUACAO_CHOICES = [
        [SITUACAO_PENDENTE, 'Pendente'],
        [SITUACAO_EM_ANALISE, 'Em análise'],
        [SITUACAO_SUSPENSA, 'Suspensa'],
        [SITUACAO_DEFERIDA, 'Deferida'],
        [SITUACAO_IMPLEMENTADA, 'Implementada'],
        [SITUACAO_INDEFERIDA, 'Indeferida'],
        [SITUACAO_CANCELADA, 'Cancelada'],
    ]

    area_atuacao = models.ForeignKeyPlus('demandas.AreaAtuacaoDemanda', verbose_name='Área de Atuação')
    tags = models.ManyToManyField('demandas.Tag', verbose_name='Tags relacionadas')
    requisitante = models.CurrentUserField(related_name='sugestaomelhoria_requisitante', verbose_name='Requisitante')
    titulo = models.CharField('Título', max_length=250)
    descricao = models.TextField('Descrição')
    situacao = models.CharFieldPlus('Situação', choices=SITUACAO_CHOICES, default=SITUACAO_PENDENTE)
    interessados = models.ManyToManyField(User, related_name='sugestaomelhoria_interessados_set', verbose_name='Interessados')
    responsavel = models.ForeignKeyPlus(User, related_name='sugestaomelhoria_responsavel', verbose_name='Responsável', null=True)
    demanda_gerada = models.ForeignKeyPlus('demandas.Demanda', verbose_name='Demanda Gerada', null=True, on_delete=models.SET_NULL)
    votos = models.IntegerFieldPlus(verbose_name='Votos', default=0)
    cadastrado_em = models.DateTimeField('Data de Cadastro', auto_now_add=True, null=True, blank=True)
    atualizado_em = models.DateTimeField('Atualizado em', auto_now=True, null=True, blank=True)
    atualizado_por = models.ForeignKeyPlus(
        User, related_name='sugestaomelhoria_atualizado_por', verbose_name='Atualizado Por', null=True, editable=False
    )

    class Meta:
        verbose_name = 'Sugestão de Melhoria'
        verbose_name_plural = 'Sugestões de Melhorias'

    def save(self, *args, **kwarg):
        usuario = tl.get_user()
        self.atualizado_por = usuario
        situacao_nova = self.situacao
        super().save(*args, **kwarg)
        historicosituacao = self.get_ultimo_historico_situacao()
        if not historicosituacao or int(historicosituacao.situacao) != situacao_nova:
            novo_historico = HistoricoSituacaoSugestaoMelhoria()
            novo_historico.sugestao_melhoria = self
            novo_historico.usuario = usuario
            novo_historico.situacao = situacao_nova
            novo_historico.save()

    def __str__(self):
        return f'Sugestão de Melhoria #{self.pk}'

    @property
    def demandantes_area(self):
        responsavel_id = [self.area_atuacao.demandante_responsavel.id]
        demandantes_ids = self.area_atuacao.demandantes.all().values_list('pk', flat=True)
        return User.objects.filter(id__in=set(responsavel_id).union(demandantes_ids))

    @property
    def demandantes_tags(self):
        result = User.objects.none()
        for tag in self.tags.all():
            result = result | TagDemandantes.get_demandantes(tag)
        return result.distinct()

    @property
    def demandantes(self):
        demandantes_tags = self.demandantes_tags

        if demandantes_tags.exists():
            # demanda 1261:
            # Em cada Sugestão devem estar relacionados somente os demandantes relacionados ao mesmo módulo da Sugestão, além
            # do demandante responsável da área (se for o caso)
            demandantes_final = demandantes_tags
            responsavel = self.area_atuacao.demandante_responsavel

            if responsavel:
                responsavel_id = [self.area_atuacao.demandante_responsavel.id]
                demandantes_ids = demandantes_tags.values_list('id', flat=True)
                demandantes_final = User.objects.filter(id__in=set(responsavel_id).union(demandantes_ids))
        else:
            # demanda 1261:
            # Para os módulos que não tiverem nenhum demandante selecionado, todos os demandantes da área serão listados na Sugestão.
            demandantes_final = self.demandantes_area

        return demandantes_final

    def get_absolute_url(self):
        return reverse('sugestao_melhoria', kwargs={'sugestao_melhoria_id': self.id})

    def get_ultimo_historico_situacao(self):
        return self.historicosituacaosugestaomelhoria_set.first()

    @staticmethod
    def sugestoes_por_area(area_atuacao, qs_sugestoes_initial=None):
        sugestoes = qs_sugestoes_initial if qs_sugestoes_initial is not None else SugestaoMelhoria.objects.all()
        return sugestoes.filter(area_atuacao=area_atuacao)

    @staticmethod
    def sugestoes_por_tags(tags, qs_sugestoes_initial=None):
        sugestoes = qs_sugestoes_initial if qs_sugestoes_initial is not None else SugestaoMelhoria.objects.all()
        return sugestoes.filter(tags=tags)

    @staticmethod
    def sugestoes_por_situacao(situacao, qs_sugestoes_initial=None):
        sugestoes = qs_sugestoes_initial if qs_sugestoes_initial is not None else SugestaoMelhoria.objects.all()
        return sugestoes.filter(situacao=situacao)

    @staticmethod
    def sugestoes_por_papel_usuario(
        user_requisitante=None, user_interessado=None, user_demandante=None, user_responsavel=None, qs_sugestoes_initial=None
    ):
        sugestoes = qs_sugestoes_initial if qs_sugestoes_initial is not None else SugestaoMelhoria.objects.all()

        algum_papel_informado = False

        if user_requisitante:
            sugestoes = sugestoes.filter(requisitante=user_requisitante)
            algum_papel_informado = True

        if user_interessado:
            sugestoes = sugestoes.filter(interessados=user_interessado)
            algum_papel_informado = True

        if user_demandante:
            demandante_foi_vinculado_a_alguma_tag = TagDemandantes.objects.filter(demandantes=user_demandante)
            if demandante_foi_vinculado_a_alguma_tag.exists():
                sugestoes = sugestoes.filter(tags__tagdemandantes__demandantes=user_demandante)
            else:
                sugestoes = sugestoes.filter(area_atuacao__demandantes=user_demandante) | sugestoes.filter(
                    area_atuacao__demandante_responsavel=user_demandante
                )
            # o demandante não deve avaliar a própria sugestão
            sugestoes = sugestoes.exclude(requisitante=user_demandante)
            algum_papel_informado = True

        if user_responsavel:
            sugestoes = sugestoes.filter(responsavel=user_responsavel)
            algum_papel_informado = True

        return sugestoes.distinct() if algum_papel_informado else qs_sugestoes_initial

    @staticmethod
    def sugestoes_ativas(qs_sugestoes_initial=None):
        sugestoes = qs_sugestoes_initial if qs_sugestoes_initial is not None else SugestaoMelhoria.objects.all()
        return sugestoes.filter(
            situacao__in=[
                SugestaoMelhoria.SITUACAO_PENDENTE,
                SugestaoMelhoria.SITUACAO_EM_ANALISE,
                SugestaoMelhoria.SITUACAO_SUSPENSA,
            ]
        )

    @staticmethod
    def eh_usuario_ti(user):
        # TODO: Existe a função 'in_group' de 'djtools.templatetags.filters' que
        # TODO: poderia ter sido usada aqui. Porém, 'templatetags' está no escopo de
        # TODO: "consumidor do domínio", e não deve ser dependência do domínio.
        return user.groups.filter(
            name__in=[
                'Coordenador de TI sistêmico',
                'Analista',
            ]
        ).exists()

    def is_responsavel_ou_demandante(self, user):
        return self.is_responsavel(user) or user in self.demandantes

    def is_responsavel(self, user):
        return user == self.responsavel

    def eh_requisitante(self, user):
        return user == self.requisitante

    def eh_interessado(self, user):
        return user in self.interessados.all()

    def tem_responsavel(self):
        return bool(self.responsavel)

    def get_etapas(self):
        result = []
        if self.is_em_analise:
            result.append([SugestaoMelhoria.SITUACAO_DEFERIDA, 'Deferida'])
            result.append([SugestaoMelhoria.SITUACAO_IMPLEMENTADA, 'Implementada'])
            result.append([SugestaoMelhoria.SITUACAO_INDEFERIDA, 'Indeferida'])
            result.append([SugestaoMelhoria.SITUACAO_SUSPENSA, 'Suspensa'])
            result.append([SugestaoMelhoria.SITUACAO_CANCELADA, 'Cancelada'])
        elif self.is_suspensa:
            result.append([SugestaoMelhoria.SITUACAO_EM_ANALISE, 'Em análise'])
        return result

    def is_situacao_ativa(self):
        return self.situacao in [SugestaoMelhoria.SITUACAO_EM_ANALISE, SugestaoMelhoria.SITUACAO_SUSPENSA, SugestaoMelhoria.SITUACAO_PENDENTE]

    @staticmethod
    def pode_adicionar_uma_sugestao(user, area_atuacao):
        return user.has_perm('demandas.add_sugestaomelhoria') and area_atuacao.pode_abrir_sugestoes(user)

    def pode_editar_todos_dados(self, user):
        """todos os atributos"""
        return self.demanda_gerada is None and self.is_responsavel_ou_demandante(user)

    def pode_editar_dados_basicos(self, user):
        """atributos: título, descrição, interessados e tags"""
        situacao = self.situacao == SugestaoMelhoria.SITUACAO_PENDENTE
        return self.pode_editar_todos_dados(user) or (situacao and user == self.requisitante)

    @staticmethod
    def pode_salvar_sugestao(user, sugestao):
        return SugestaoMelhoria.pode_adicionar_uma_sugestao(user, sugestao.area_atuacao) and (
            sugestao.pode_editar_dados_basicos(user) or sugestao.pode_editar_todos_dados(user)
        )

    def pode_visualizar(self, user):
        return user.has_perm('demandas.view_sugestaomelhoria')

    def pode_anexar(self, user):
        return self.is_situacao_ativa() and (self.is_responsavel_ou_demandante(user) or self.eh_requisitante(user) or self.eh_interessado(user))

    def pode_gerar_demanda(self, user):
        return self.is_responsavel_ou_demandante(user) and self.demanda_gerada is None and self.is_deferida

    def gerar_demanda(self, user, nova_demanda=None):
        from .demanda import Demanda, HistoricoSituacao

        try:
            if self.pode_gerar_demanda(user):
                if not nova_demanda:
                    nova_demanda = Demanda(area=self.area_atuacao, titulo=self.titulo, descricao=self.descricao)
                    nova_demanda.save()

                    demanda_demandantes = [self.responsavel]
                    nova_demanda.demandantes.set(demanda_demandantes)

                    demanda_interessados = [self.requisitante]
                    demanda_interessados = demanda_interessados + list(self.interessados.all())
                    nova_demanda.interessados.set(demanda_interessados)

                    nova_demanda.tags.set(list(self.tags.filter(ativa=True)))

                novo_historico = HistoricoSituacao()
                novo_historico.demanda = nova_demanda
                novo_historico.usuario = user
                novo_historico.situacao = nova_demanda.situacao
                novo_historico.data_previsao = None  # TODO: ?
                novo_historico.save()

                situacao_alterada = False

                if not self.is_deferida:
                    self.situacao = SugestaoMelhoria.SITUACAO_DEFERIDA
                    situacao_alterada = True

                self.demanda_gerada = nova_demanda
                self.save()

                if situacao_alterada:
                    Notificar.nova_situacao_em_sugestao_melhoria(self, user)

                # coloca a demanda em última prioridade dentro da sua área
                Demanda.colocar_demanda_em_ultima_prioridade(nova_demanda, user)

                # notifica a abertura da nova demanda
                Notificar.demanda_aberta(nova_demanda)
            else:
                raise Exception(f'O usuário "{user.get_vinculo()}" não pode gerar a demanda para esta sugestão de melhoria.')
        except Exception:
            raise Exception('Ocorreu um erro ao gerar a demanda para esta sugestão de melhoria.')

    def eh_demanda_gerada_em_andamento(self):
        return self.demanda_gerada is not None and not self.demanda_gerada.eh_situacao_terminal()

    def pode_visualizar_demanda_gerada(self, user):
        # TODO: Sobre os interessados na sugestão de melhoria e o seu amplo escopo de escolha,
        # TODO: é possível que um User selecionado não tenha permissão de visualizar
        # TODO: uma demanda. Por exemplo, um aluno não pode visualizar uma demanda,
        # TODO: mas pode ser selecionado em uma sugestão de melhoria, que por sua vez
        # TODO: pode gerar uma demanda no final.
        # TODO: Para resolver isso aqui neste contexto, a visualização da demanda gerada
        # TODO: ficará condicionada à permissão estática "demandas.view_demanda". Na prática,
        # TODO: o botão "Ver Demanda" não estará disponível para os demais usuários, mesmo que
        # TODO: estejam entre os interessados na sugestão de melhoria (a inconsistência silenciosa vai continuar).
        return user.has_perm('demandas.view_demanda')

    def pode_excluir_demanda_gerada(self, user):
        return self.is_responsavel(user) and self.eh_demanda_gerada_em_andamento()

    def pode_votar(self):
        return self.situacao not in [
            SugestaoMelhoria.SITUACAO_DEFERIDA,
            SugestaoMelhoria.SITUACAO_IMPLEMENTADA,
            SugestaoMelhoria.SITUACAO_INDEFERIDA,
            SugestaoMelhoria.SITUACAO_CANCELADA,
        ]

    def pode_visualizar_comentario(self, user):
        return self.pode_visualizar(user)

    def pode_registrar_comentario(self, user):
        return self.pode_visualizar_comentario(user) and not (self.is_deferida or self.is_implementada or self.is_indeferida or self.is_cancelada)

    @property
    def is_pendente(self):
        return self.situacao == SugestaoMelhoria.SITUACAO_PENDENTE

    @property
    def is_em_analise(self):
        return self.situacao == SugestaoMelhoria.SITUACAO_EM_ANALISE

    @property
    def is_suspensa(self):
        return self.situacao == SugestaoMelhoria.SITUACAO_SUSPENSA

    @property
    def is_deferida(self):
        return self.situacao == SugestaoMelhoria.SITUACAO_DEFERIDA

    @property
    def is_indeferida(self):
        return self.situacao == SugestaoMelhoria.SITUACAO_INDEFERIDA

    @property
    def is_implementada(self):
        return self.situacao == SugestaoMelhoria.SITUACAO_IMPLEMENTADA

    @property
    def is_cancelada(self):
        return self.situacao == SugestaoMelhoria.SITUACAO_CANCELADA

    @property
    def qtd_votos(self):
        voto = SugestaoVoto.objects.filter(sugestao=self)
        return voto.filter(concorda=True).count() - voto.filter(concorda=False).count()

    @property
    def ja_concordou(self):
        usuario = tl.get_user()
        return SugestaoVoto.objects.filter(sugestao=self, usuario=usuario, concorda=True).exists()

    @property
    def ja_discordou(self):
        usuario = tl.get_user()
        return SugestaoVoto.objects.filter(sugestao=self, usuario=usuario, concorda=False).exists()

    def quem_concordou(self):
        return SugestaoVoto.objects.filter(sugestao=self, concorda=True)

    def quem_discordou(self):
        return SugestaoVoto.objects.filter(sugestao=self, concorda=False)

    def atribuir_responsavel(self, user):
        result = False

        if not self.pode_editar_todos_dados(user):
            raise PermissionDenied('Você não tem permissão para editar a sugestão de melhoria.')

        try:
            situacao_alterada = False

            if not self.is_em_analise:
                self.situacao = SugestaoMelhoria.SITUACAO_EM_ANALISE
                situacao_alterada = True

            self.responsavel = user
            self.save()

            if self.responsavel:
                if situacao_alterada:
                    Notificar.nova_situacao_em_sugestao_melhoria(self, user)

                result = True
            else:
                result = False

        except Exception:
            result = False

        return result


class HistoricoSituacaoSugestaoMelhoria(ModelPlus):
    sugestao_melhoria = models.ForeignKeyPlus(
        SugestaoMelhoria, verbose_name='Histórico de alterações na sugestão de melhoria', on_delete=models.CASCADE
    )
    data_hora = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKeyPlus(
        User, verbose_name='Usuário', related_name='historicosituacaosugestaomelhoria_usuarios_set', on_delete=models.CASCADE
    )
    situacao = models.CharFieldPlus('Situacao', choices=SugestaoMelhoria.SITUACAO_CHOICES, null=True)

    def __str__(self):
        return f'{self.pk}: {self.sugestao_melhoria.titulo} ({self.situacao})'

    class Meta:
        ordering = ['-data_hora']
        verbose_name = 'Histórico das situações da sugestão de melhoria'
        verbose_name_plural = 'Históricos das situações das sugestões de melhoria'


class SugestaoAnexo(models.ModelPlus):
    descricao = models.CharFieldPlus(
        'Descrição', max_length=80, null=False, blank=False, help_text='Informe uma descrição resumida sobre o arquivo anexado'
    )
    sugestao = models.ForeignKeyPlus(SugestaoMelhoria, verbose_name='Sugestão de Melhoria')
    anexo = models.FileFieldPlus(
        max_length=255,
        upload_to='upload/sugestao/anexos/',
        can_view='can_view_anexo',
        validators=[FileExtensionValidator(allowed_extensions=['xlsx', 'xls', 'csv', 'docx', 'doc', 'pdf', 'jpg', 'jpeg', 'png', 'txt'])],
    )
    anexado_em = models.DateTimeField(auto_now_add=True, null=False, blank=False)
    anexado_por = models.ForeignKeyPlus(User, verbose_name='Anexado Por', null=False, blank=False)

    def can_view_anexo(self, user):
        return user.is_authenticated

    def __str__(self):
        return f'Sugestão de Melhoria {self.sugestao.id} - Anexo ({self.id}): {self.descricao}'

    class Meta:
        ordering = ['anexado_em']
        verbose_name = 'Anexo'
        verbose_name_plural = 'Anexos'


class SugestaoVoto(models.ModelPlus):
    sugestao = models.ForeignKeyPlus(SugestaoMelhoria, verbose_name='Sugestão de Melhoria', on_delete=models.CASCADE)
    usuario = models.CurrentUserField()
    concorda = models.BooleanField(null=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        sugestao = self.sugestao
        sugestao.votos = sugestao.qtd_votos
        sugestao.save()


class TagDemandantes(models.ModelPlus):
    """
    Modelo usado no contexto de sugestões de melhorias conforme a demanda 1261.
    Amplia o escopo de demandantes de uma sugestão de melhoria, priorizando os
    demandantes associadas à Tag da sugestão.

        Sugestão de melhoria -> Área de atuação -> Demandantes
        Sugestão de melhoria -> Tag -> Demandantes
    """

    tag = models.OneToOneFieldPlus('demandas.Tag', verbose_name='Tag')
    demandantes = models.ManyToManyField(User, verbose_name='Demandantes')

    class Meta:
        verbose_name = 'Demandante por Tag'
        verbose_name_plural = 'Demandantes por Tags'

    @staticmethod
    def save_demandantes(tag, demandantes):
        try:
            tag_demandantes = TagDemandantes.objects.filter(tag=tag)

            if tag_demandantes.exists():
                tag_demandantes = tag_demandantes.first()
            else:
                tag_demandantes = TagDemandantes(tag=tag)
                tag_demandantes.save()

            tag_demandantes.demandantes.set(demandantes)

            return True
        except Exception:
            return False

    @staticmethod
    def get_demandantes(tag):
        tag_demandantes = TagDemandantes.objects.filter(tag=tag)
        if tag_demandantes.exists():
            tag_demandantes = tag_demandantes.first()
            return tag_demandantes.demandantes.all()
        return User.objects.none()

    def __str__(self):
        return f'{self.tag}'
