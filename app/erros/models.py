import datetime
from datetime import timedelta, date

from django.conf import settings
from django.db.models.aggregates import Count
from sentry_sdk import capture_exception

from comum.models import Preferencia, User, Vinculo
from comum.utils import ferramentas_configuradas
from djtools.db import models
from djtools.templatetags.filters import in_group
from erros.notificacoes import Notificar
from erros.utils import (
    atualizar_label_feedback_issue_gitlab,
    comentar_erro_issue_gitlab,
    comentar_issue_gitlab,
    fechar_issue_gitlab,
    get_custom_view_name_from_url,
    reabrir_issue_gitlab,
    get_auto_modulo_afetado,
)
from djtools.utils import get_app_suap_verbose_name


class Erro(models.ModelPlus):
    SITUACAO_ABERTO = 1
    SITUACAO_EM_ANALISE = 2
    SITUACAO_RESOLVIDO = 3
    SITUACAO_AGUARDANDO_FEEDBACK = 4
    SITUACAO_CANCELADO = 5
    SITUACAO_REABERTO = 6
    SITUACAO_EM_CORRECAO = 7
    SITUACAO_UNIFICADO = 8
    SITUACAO_CHOICES = [
        [SITUACAO_ABERTO, 'Reportado'],
        [SITUACAO_EM_ANALISE, 'Em análise'],
        [SITUACAO_EM_CORRECAO, 'Em correção'],
        [SITUACAO_RESOLVIDO, 'Resolvido'],
        [SITUACAO_AGUARDANDO_FEEDBACK, 'Aguardando feedback'],
        [SITUACAO_CANCELADO, 'Cancelado'],
        [SITUACAO_REABERTO, 'Reaberto'],
        [SITUACAO_UNIFICADO, 'Unificado'],
    ]
    SITUACOES_FINAIS = [SITUACAO_RESOLVIDO, SITUACAO_CANCELADO, SITUACAO_UNIFICADO]

    FUNCIONALIDADE = 'Funcionalidade'
    MANUTENCAO = 'Manutenção'
    BUG = 'Bug'
    TIPO_CHOICES = (
        (BUG, 'Bug'),
        (FUNCIONALIDADE, 'Funcionalidade'),
        (MANUTENCAO, 'Manutenção'),
    )

    SEARCH_FIELDS = (
        'id',
        'url',
    )
    descricao = models.TextField(verbose_name='Descrição')
    url = models.TextField(verbose_name='URL com Erro')
    url_sentry = models.TextField(verbose_name='URL do Sentry', null=True, blank=True)
    sentry_issue_id = models.CharFieldPlus('Id da Issue do Sentry', null=True, blank=True)
    gitlab_issue_url = models.TextField(verbose_name='URL do Gitlab', null=True, blank=True)
    view = models.CharFieldPlus(verbose_name='View')
    modulo_afetado = models.CharFieldPlus('Módulo afetado', max_length=200, editable=False, default='')
    maquina = models.TextField(verbose_name='Máquina', null=False, blank=True)
    informante = models.ForeignKeyPlus('comum.Vinculo', null=True, related_name='informantes_erros', verbose_name='Reportado por')
    situacao = models.IntegerField(choices=SITUACAO_CHOICES, verbose_name='Situação', default=SITUACAO_ABERTO)
    data_criacao = models.DateTimeFieldPlus(auto_now_add=True, verbose_name='Data de Criação')
    data_ultima_alteracao = models.DateTimeFieldPlus(auto_now=True, verbose_name='Data da Última Alteração')
    atendente_atual = models.ForeignKeyPlus('comum.Vinculo', null=True, blank=True, related_name='atendentes_erros', verbose_name='Atendente Atual')
    qtd_vinculos_afetados = models.IntegerField('Quantidade de Usuários Afetados', null=False, blank=False, default=1)
    titulo_atualizacao = models.CharFieldPlus(verbose_name='Título', null=True)
    tipo_atualizacao = models.CharFieldPlus(choices=TIPO_CHOICES, null=True, default=BUG, verbose_name='Tipo')
    grupos_atualizacao = models.ManyToManyFieldPlus('auth.Group', verbose_name='Grupos Envolvidos')
    ip_address = models.TextField(null=False, blank=True, verbose_name='Endereço IP')
    agent = models.TextField(null=False, blank=True, verbose_name='Navegador')
    atualizacao = models.OneToOneFieldPlus('demandas.Atualizacao', null=True, blank=True, verbose_name='Atualização')

    class Meta:
        verbose_name = 'Erro'
        verbose_name_plural = 'Erros'

    def save(self, *args, **kwargs):
        self.set_modulo_afetado()
        super().save(*args, **kwargs)

    def mais_de_quinze_dias(self):
        return (datetime.datetime.now().today() - self.data_criacao) > timedelta(days=15)

    def __str__(self):
        return f'Erro {self.pk}: {self.modulo_afetado_display}'

    def get_absolute_url(self):
        return f'/erros/erro/{self.pk}/'

    def get_visualizar_erro_url(self):
        return f'{settings.SITE_URL}{self.get_absolute_url()}'

    def set_modulo_afetado(self):
        self.modulo_afetado = get_auto_modulo_afetado(self.view)

    @property
    def modulo_afetado_display(self):
        return get_app_suap_verbose_name(self.modulo_afetado)

    def criar(self):
        self.save()
        interessado = InteressadoErro()
        interessado.vinculo = self.informante
        interessado.erro = self
        preferencia = Preferencia.objects.filter(usuario=self.informante.user).first()
        interessado.tema = preferencia.tema if preferencia else Preferencia.get_tema_padrao_usuario_autenticado()
        interessado.save()

    def get_vinculos_interessados(self):
        if not hasattr(self, 'vinculos_interessados'):
            self.vinculos_interessados = Vinculo.objects.filter(pk__in=self.interessadoerro_set.filter(ativo=True).values_list('vinculo', flat=True))
        return self.vinculos_interessados

    def get_vinculos_atendentes(self):
        atendentes = [atendente.vinculo for atendente in self.get_outros_atendentes()]
        if self.atendente_atual:
            atendentes.append(self.atendente_atual)
        return atendentes

    def get_vinculos_gerentes(self):
        return list(Vinculo.objects.filter(user__usuariogrupo__group__name='Recebedor de Demandas'))

    def get_notificados(self, ignorado=None, so_atendentes=False):
        notificados = self.get_vinculos_atendentes()
        if not so_atendentes:
            notificados += self.get_vinculos_interessados()
        return [x for x in set(notificados) if x is not None and x != ignorado]

    def vinculo_eh_atendente_atual(self, vinculo):
        return self.atendente_atual == vinculo

    def vinculo_pode_ser_atendente(self, vinculo):
        return in_group(vinculo.user, 'Analista', ignore_groups_if_superuser=False)

    def vinculo_eh_interessado(self, vinculo):
        return vinculo in self.get_vinculos_interessados()

    def estah_no_fluxo(self):
        return self.situacao not in [self.SITUACAO_AGUARDANDO_FEEDBACK, self.SITUACAO_CANCELADO, self.SITUACAO_REABERTO, self.SITUACAO_UNIFICADO]

    def pode_assumir(self, vinculo):
        return (
            self.situacao not in self.SITUACOES_FINAIS and self.vinculo_pode_ser_atendente(vinculo) and not self.vinculo_eh_atendente_atual(vinculo)
        )

    def pode_sincronizar_gitlab(self, vinculo):
        return (
            self.situacao not in self.SITUACOES_FINAIS
            and ferramentas_configuradas()
            and self.vinculo_pode_ser_atendente(vinculo)
            and not self.gitlab_issue_url
            and self.sentry_issue_id
        )

    def pode_criar_issue_gitlab(self, vinculo):
        return (
            self.situacao not in self.SITUACOES_FINAIS
            and ferramentas_configuradas()
            and self.vinculo_pode_ser_atendente(vinculo)
            and not self.gitlab_issue_url
            and not self.gitlab_issue_url
        )

    def pode_devolver(self, vinculo):
        return self.situacao not in self.SITUACOES_FINAIS and self.vinculo_eh_atendente_atual(vinculo) and self.situacao not in self.SITUACOES_FINAIS

    def pode_atribuir(self, vinculo):
        return self.situacao not in self.SITUACOES_FINAIS and in_group(vinculo.user, 'Recebedor de Demandas')

    def pode_unificar(self, vinculo):
        return self.situacao not in self.SITUACOES_FINAIS and in_group(vinculo.user, 'Recebedor de Demandas')

    def pode_comentar(self, vinculo):
        return self.situacao not in self.SITUACOES_FINAIS and (self.vinculo_eh_interessado(vinculo) or self.vinculo_pode_ser_atendente(vinculo))

    def pode_comentar_nota_interna(self, vinculo):
        return self.situacao not in self.SITUACOES_FINAIS and self.vinculo_pode_ser_atendente(vinculo)

    def pode_se_interessar(self, vinculo):
        return vinculo not in self.get_vinculos_interessados() and not vinculo.eh_aluno()

    def pode_se_desinteressar(self, vinculo):
        return vinculo in self.get_vinculos_interessados() and vinculo != self.informante

    def pode_ver_comentarios(self, vinculo):
        return self.vinculo_eh_interessado(vinculo) or self.vinculo_pode_ser_atendente(vinculo)

    def pode_ver_nota_interna(self, vinculo):
        return self.vinculo_pode_ser_atendente(vinculo)

    def pode_alterar_url(self, vinculo):
        return self.situacao not in self.SITUACOES_FINAIS and (
            in_group(vinculo.user, 'Recebedor de Demandas') or self.vinculo_eh_atendente_atual(vinculo)
        )

    def pode_editar_atualizacao(self, vinculo):
        return self.vinculo_pode_ser_atendente(vinculo) and self.situacao not in self.SITUACOES_FINAIS and 'demandas' in settings.INSTALLED_APPS

    def pode_alterar_situacao(self, vinculo):
        return self.get_situacoes_disponiveis(vinculo) and self.vinculo_eh_atendente_atual(vinculo)

    def pode_cancelar_por_erro_de_abertura(self, vinculo):
        return self.situacao == self.SITUACAO_ABERTO and in_group(vinculo.user, 'Recebedor de Demandas')

    def get_situacoes_disponiveis(self, vinculo):
        eh_atendente = self.vinculo_eh_atendente_atual(vinculo)
        eh_informante = self.informante == vinculo
        if not eh_atendente and not eh_informante:
            return []
        if self.situacao in [self.SITUACAO_ABERTO, self.SITUACAO_REABERTO]:
            if eh_atendente:
                return [self.SITUACAO_EM_ANALISE, self.SITUACAO_EM_CORRECAO, self.SITUACAO_CANCELADO]
            else:
                return []
        elif self.situacao == self.SITUACAO_EM_ANALISE:
            if eh_atendente:
                return [self.SITUACAO_EM_CORRECAO, self.SITUACAO_RESOLVIDO, self.SITUACAO_AGUARDANDO_FEEDBACK, self.SITUACAO_CANCELADO]
            else:
                return []
        elif self.situacao == self.SITUACAO_EM_CORRECAO:
            if eh_atendente:
                return [self.SITUACAO_EM_ANALISE, self.SITUACAO_RESOLVIDO, self.SITUACAO_AGUARDANDO_FEEDBACK, self.SITUACAO_CANCELADO]
            else:
                return []
        elif self.situacao == self.SITUACAO_AGUARDANDO_FEEDBACK:
            if eh_atendente:
                return [self.SITUACAO_EM_ANALISE, self.SITUACAO_EM_CORRECAO, self.SITUACAO_RESOLVIDO, self.SITUACAO_CANCELADO]
            else:
                return []
        elif self.situacao in [self.SITUACAO_CANCELADO, self.SITUACAO_RESOLVIDO]:
            return [self.SITUACAO_REABERTO]

    def get_outros_atendentes(self):
        return self.atendenteerro_set.exclude(vinculo=self.atendente_atual)

    def get_outros_interessados(self):
        if not hasattr(self, 'outros_interessados'):
            self.outros_interessados = self.interessadoerro_set.exclude(vinculo=self.informante).exclude(ativo=False)
        return self.outros_interessados

    def devolver(self, vinculo):
        if self.pode_devolver(vinculo):
            self.atendente_atual = None
            self.save()
            HistoricoComentarioErro.objects.create(erro=self, descricao='devolveu o atendimento.', vinculo=vinculo, automatico=True)

    def atribuir(self, atribuinte, atribuido):
        if self.pode_atribuir(atribuinte):
            self.atendente_atual = atribuido
            self.save()
            HistoricoComentarioErro.objects.create(
                erro=self, descricao=f'habilitou {atribuido} como atendente principal.', vinculo=atribuinte, automatico=True
            )
            self.gerenciar_atendente(atribuido, mensagem_customizada='', forcar_assumir=True)
            Notificar.atribuir_erro(self, atribuinte)

    def unificar(self, vinculo, erros):
        if self.pode_unificar(vinculo):
            urls = []
            url_principal = f'<a href={self.get_absolute_url()}>#{self.pk}</a>'
            for erro in erros:
                for interessado in erro.interessadoerro_set.filter(ativo=True):
                    self.gerenciar_interessado(
                        interessado.vinculo, mensagem_customizada=f'foi adicionado como interessado por {vinculo}.', tema=interessado.tema
                    )
                HistoricoComentarioErro.objects.create(erro=self, descricao=erro.descricao, vinculo=erro.informante)
                erro.situacao = erro.SITUACAO_UNIFICADO
                erro.save()

                descricao = f'unificou este erro com o erro {url_principal}.'
                HistoricoComentarioErro.objects.create(erro=erro, descricao=descricao, vinculo=vinculo, automatico=True)
                url = f'<a href={erro.get_absolute_url()}>#{erro.pk}</a>'
                urls.append(url)

            descricao = f'unificou este erro com os erros: {" ".join(urls)}.'
            HistoricoComentarioErro.objects.create(erro=self, descricao=descricao, vinculo=vinculo, automatico=True)

    def comentar(self, vinculo, descricao, tipo, automatico=False):
        self.gerenciar_atendente(vinculo)
        comentario = HistoricoComentarioErro.objects.create(erro=self, descricao=descricao, vinculo=vinculo, tipo=tipo, automatico=automatico)
        Notificar.comentar_erro(comentario)
        if self.situacao == self.SITUACAO_AGUARDANDO_FEEDBACK and vinculo in self.get_vinculos_interessados():
            HistoricoComentarioErro.objects.create(erro=self, descricao='Situação do erro alterada para: Em análise.', automatico=True)
            self.situacao = self.SITUACAO_EM_ANALISE
            self.save()

        if self.situacao == self.SITUACAO_EM_ANALISE:
            comentario_gitlab = f'Um interessado respondeu o erro <a href="{settings.SITE_URL}{self.get_absolute_url()}">{settings.SITE_URL}{self.get_absolute_url()}</a>'
            comentar_issue_gitlab(self, comentario_gitlab)

    def anexar(self, anexado_por, descricao, arquivo):
        self.gerenciar_atendente(anexado_por)
        anexo = AnexoErro.objects.create(erro=self, descricao=descricao, anexado_por=anexado_por, arquivo=arquivo)
        descricao_comentario = f'adicionou o anexo <a href="{anexo.get_absolute_url()}">{descricao}</a>.'
        HistoricoComentarioErro.objects.create(
            erro=self, descricao=descricao_comentario, vinculo=anexado_por, tipo=HistoricoComentarioErro.TIPO_COMENTARIO, automatico=True
        )
        Notificar.adicionar_anexo(anexo)

        comentario = f'Um interessado adicionou o anexo <a href="{settings.SITE_URL}{anexo.get_absolute_url()}">{settings.SITE_URL}{anexo.get_absolute_url()}</a> ao erro <a href="{settings.SITE_URL}{self.get_absolute_url()}">{settings.SITE_URL}{self.get_absolute_url()}</a>'

        if self.situacao == self.SITUACAO_AGUARDANDO_FEEDBACK and anexado_por in self.get_vinculos_interessados():
            HistoricoComentarioErro.objects.create(erro=self, descricao='Situação do erro alterada para: Em análise.', automatico=True)
            self.situacao = self.SITUACAO_EM_ANALISE
            self.save()
            comentar_issue_gitlab(self, comentario)
        else:
            comentar_issue_gitlab(self, comentario, alter_labels=False)

    def editar_atualizacao(self, analista=None):
        from demandas.models import Atualizacao, Tag

        atualizacao = self.atualizacao or Atualizacao()
        if atualizacao and self.titulo_atualizacao and self.tipo_atualizacao and self.grupos_atualizacao.exists():
            atualizacao.descricao = self.titulo_atualizacao
            atualizacao.tipo = self.tipo_atualizacao
            atualizacao.data = datetime.datetime.now().today()
            atualizacao.save()
            self.atualizacao = atualizacao
            self.save()
            tag, _ = Tag.objects.get_or_create(nome=self.modulo_afetado_display, defaults={'sigla': self.modulo_afetado})
            atualizacao.tags.add(tag)
            atualizacao.responsaveis.clear()
            if analista is None:
                atualizacao.responsaveis.add(self.atendente_atual.user)
            else:
                atualizacao.responsaveis.add(analista)
            atualizacao.grupos.clear()
            for grupo in self.grupos_atualizacao.all():
                atualizacao.grupos.add(grupo)

    def gerenciar_situacao(self, vinculo, situacao, motivo=None, mensagem_customizada=None):
        descricao_situacao = Erro(situacao=situacao).get_situacao_display()
        descricao = mensagem_customizada
        if not mensagem_customizada:
            descricao = f'alterou a situação para: {descricao_situacao}.'
        HistoricoComentarioErro.objects.create(erro=self, descricao=descricao, vinculo=vinculo, automatico=True)
        self.situacao = situacao
        self.save()
        if motivo:
            HistoricoComentarioErro.objects.create(erro=self, descricao=motivo, vinculo=vinculo)
        try:
            if situacao == self.SITUACAO_REABERTO and self.gitlab_issue_url:
                conf = ferramentas_configuradas()
                if conf:
                    reabrir_issue_gitlab(self, conf)
            elif situacao == self.SITUACAO_CANCELADO and self.gitlab_issue_url:
                conf = ferramentas_configuradas()
                if conf:
                    fechar_issue_gitlab(self, conf)
            elif situacao == self.SITUACAO_RESOLVIDO:
                self.editar_atualizacao()
                if self.gitlab_issue_url:
                    conf = ferramentas_configuradas()
                    if conf:
                        fechar_issue_gitlab(self, conf)
            elif situacao == self.SITUACAO_AGUARDANDO_FEEDBACK:
                conf = ferramentas_configuradas()
                if conf:
                    atualizar_label_feedback_issue_gitlab(self, conf)
            elif situacao == self.SITUACAO_EM_ANALISE:
                conf = ferramentas_configuradas()
                if conf:
                    comentario_gitlab = f'Um interessado respondeu o erro <a href="{settings.SITE_URL}{self.get_absolute_url()}">{settings.SITE_URL}{self.get_absolute_url()}</a>'
                    comentar_issue_gitlab(self, comentario_gitlab)
        except Exception as e:
            capture_exception(e)

        Notificar.alterar_situacao_erro(self, vinculo, motivo)

    def gerenciar_atendente(self, vinculo, mensagem_customizada=None, forcar_assumir=False):
        if self.vinculo_pode_ser_atendente(vinculo):
            _atendente, criado = AtendenteErro.objects.get_or_create(vinculo=vinculo, erro=self)
            descricao = mensagem_customizada
            if not self.atendente_atual or (forcar_assumir and self.atendente_atual != vinculo):
                self.atendente_atual = vinculo
                self.save()
                if mensagem_customizada is None:
                    descricao = 'se habilitou como atendente principal.'
            elif criado:
                if mensagem_customizada is None:
                    descricao = 'se habilitou como atendente auxiliar.'
            if descricao:
                HistoricoComentarioErro.objects.create(erro=self, descricao=descricao, vinculo=vinculo, automatico=True)
            if self.situacao in [self.SITUACAO_REABERTO, self.SITUACAO_ABERTO]:
                self.gerenciar_situacao(vinculo, situacao=self.SITUACAO_EM_ANALISE)

    def alterar_url(self, vinculo, url, tipo, issue_id):
        url_antiga = ''
        visibilidade = HistoricoComentarioErro.VISIBILIDADE_INTERESSADOS
        if tipo == 'erro':
            url_antiga = self.url
            self.url = url
            self.view = get_custom_view_name_from_url(url)
        elif tipo == 'sentry':
            url_antiga = self.url_sentry
            self.url_sentry = url
            self.sentry_issue_id = issue_id
            visibilidade = HistoricoComentarioErro.VISIBILIDADE_ATENDENTES
        elif tipo == 'gitlab':
            url_antiga = self.gitlab_issue_url
            self.gitlab_issue_url = url
            visibilidade = HistoricoComentarioErro.VISIBILIDADE_ATENDENTES
        if not url_antiga:
            url_antiga = ''
        if url_antiga != url:
            url_antiga = url_antiga or 'vazio'
            url = url or 'vazio'
            self.save()
            descricao = f'alterou a URL do {tipo} de {url_antiga} para {url}.'
            if tipo == 'gitlab':
                conf = ferramentas_configuradas()
                comentar_erro_issue_gitlab(self, conf)
            HistoricoComentarioErro.objects.create(erro=self, descricao=descricao, vinculo=vinculo, automatico=True, visibilidade=visibilidade)

    def gerenciar_interessado(self, vinculo, habilitar=True, mensagem_customizada=None, tema=''):
        interessado, criado = InteressadoErro.objects.get_or_create(vinculo=vinculo, erro=self, defaults={'tema': tema})
        descricao = mensagem_customizada
        if criado:
            if not mensagem_customizada:
                descricao = 'se habilitou como interessado.'
        else:
            if habilitar and not interessado.ativo:
                if not mensagem_customizada:
                    descricao = 'se habilitou novamente como interessado.'
                interessado.ativo = True
                interessado.save()
            elif not habilitar and interessado.ativo:
                if not mensagem_customizada:
                    descricao = 'se desabilitou como interessado.'
                interessado.ativo = False
                interessado.save()
            else:
                descricao = None

        self.qtd_vinculos_afetados = InteressadoErro.objects.filter(erro=self, ativo=True).count()
        self.save()
        if descricao:
            HistoricoComentarioErro.objects.create(erro=self, descricao=descricao, vinculo=vinculo, automatico=True)
        return interessado

    def cancelar_automatico(self):
        HistoricoComentarioErro.objects.create(erro=self, descricao='Erro cancelado automaticamente por falta de feedback.', automatico=True)
        self.situacao = self.SITUACAO_CANCELADO
        self.save()
        conf = ferramentas_configuradas()
        if conf:
            fechar_issue_gitlab(self, conf)

    def cancelar_por_erro_de_abertura(self):
        HistoricoComentarioErro.objects.create(
            erro=self, automatico=True, descricao='Cancelado por não atender às instruções exibidas na tela de abertura deste Erro.'
        )
        self.situacao = self.SITUACAO_CANCELADO
        self.save()

    def get_temas_e_contadores_erro(self):
        return self.interessadoerro_set.filter(ativo=True).exclude(tema='').values('tema').annotate(total=Count('tema')).values_list('tema', 'total')

    @staticmethod
    def get_erros_criados(
        data_inicio: date,
        data_fim: date,
        modulos_afetados: list[str] | None = None,
        situacao=None,
    ) -> models.QuerySet[Erro]:
        data_inicio = datetime.datetime.combine(data_inicio, datetime.time(0, 0, 0))
        data_fim = datetime.datetime.combine(data_fim, datetime.time(23, 59, 59))
        erros = Erro.objects.filter(data_criacao__range=(data_inicio, data_fim))
        if modulos_afetados or modulos_afetados == []:
            erros = erros.filter(modulo_afetado__in=modulos_afetados)
        if situacao:
            erros = erros.filter(situacao=situacao)
        return erros

    @staticmethod
    def get_erros_atualizados(
        data_inicio: date,
        data_fim: date,
        modulos_afetados: list[str] | None = None,
        situacao=None,
    ) -> models.QuerySet[Erro]:
        data_inicio = datetime.datetime.combine(data_inicio, datetime.time(0, 0, 0))
        data_fim = datetime.datetime.combine(data_fim, datetime.time(23, 59, 59))
        erros = Erro.objects.filter(data_ultima_alteracao__range=(data_inicio, data_fim))
        if modulos_afetados or modulos_afetados == []:
            erros = erros.filter(modulo_afetado__in=modulos_afetados)
        if situacao:
            erros = erros.filter(situacao=situacao)
        return erros


class InteressadoErro(models.ModelPlus):
    vinculo = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Interessado')
    erro = models.ForeignKeyPlus('erros.Erro')
    tema = models.CharFieldPlus(verbose_name='Tema ao ser vinculado ao erro', null=False, blank=True, default='')
    ativo = models.BooleanField(default=True)

    class Meta:
        unique_together = ('vinculo', 'erro')

    def save(self, *args, **kwargs):
        if not self.tema:
            preferencia = Preferencia.objects.filter(usuario=self.vinculo.user).first()
            self.tema = preferencia.tema if preferencia else Preferencia.get_tema_padrao_usuario_autenticado()

        super().save(*args, **kwargs)


class AtendenteErro(models.ModelPlus):
    vinculo = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Interessado')
    erro = models.ForeignKeyPlus('erros.Erro')
    ativo = models.BooleanField(default=True)

    class Meta:
        unique_together = ('vinculo', 'erro')


class HistoricoComentarioErro(models.ModelPlus):
    TIPO_COMENTARIO = 'comentario'
    TIPO_NOTA_INTERNA = 'nota_interna'

    VISIBILIDADE_INTERESSADOS = 'interessados'
    VISIBILIDADE_ATENDENTES = 'atendentes'

    TIPO_CHOICES = ((TIPO_COMENTARIO, 'Comentário'), (TIPO_NOTA_INTERNA, 'Nota Interna'))
    VISIBILIDADE_CHOICES = ((VISIBILIDADE_INTERESSADOS, 'Interessados e Atendentes'), (VISIBILIDADE_ATENDENTES, 'Atendentes'))

    erro = models.ForeignKeyPlus('erros.Erro')
    descricao = models.TextField(verbose_name='Tipo')
    vinculo = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Atendente', null=True)
    automatico = models.BooleanField(default=False)
    ativo = models.BooleanField(default=True)
    tipo = models.CharFieldPlus(choices=TIPO_CHOICES, default=TIPO_COMENTARIO)
    data_alteracao = models.DateTimeFieldPlus(auto_now_add=True)
    visibilidade = models.CharFieldPlus(choices=VISIBILIDADE_CHOICES, default=VISIBILIDADE_INTERESSADOS)

    class Meta:
        ordering = ('-data_alteracao',)

    def pode_desconsiderar_comentario(self, vinculo):
        return self.ativo and self.erro.pode_comentar(vinculo) and vinculo == self.vinculo

    def pode_ver(self, vinculo):
        return (
            self.visibilidade == self.VISIBILIDADE_ATENDENTES
            and self.erro.vinculo_pode_ser_atendente(vinculo)
            or self.visibilidade == self.VISIBILIDADE_INTERESSADOS
        )

    def desconsiderar_comentario(self):
        self.ativo = False
        self.save()


class AnexoErro(models.ModelPlus):
    erro = models.ForeignKeyPlus('erros.Erro')
    descricao = models.CharFieldPlus(
        'Descrição', max_length=80, null=False, blank=False, help_text='Informe uma descrição resumida sobre o arquivo anexado'
    )
    arquivo = models.FileFieldPlus(
        max_length=255,
        upload_to='erros/anexos/',
        filetypes=['xls', 'csv', 'doc', 'pdf', 'jpg', 'png', 'xlsx', 'txt'],
        create_date_subdirectories=True,
        can_view='can_view_arquivo',
    )
    ativo = models.BooleanField(default=True)

    anexado_por = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Anexado por', null=False, blank=False)
    anexado_em = models.DateTimeFieldPlus(verbose_name='Anexado em', auto_now_add=True, null=False, blank=False)

    def can_view_arquivo(self, user):
        return user.is_authenticated

    def get_absolute_url(self):
        return self.arquivo.get_url_publica()


class RespostaFrequente(models.ModelPlus):
    atendente = models.ForeignKeyPlus(User, related_name='respostafrequente_atendente_set', verbose_name='Atendente')
    texto = models.TextField('Texto Padrão')

    def __str__(self):
        return f'{self.texto}'

    class Meta:
        ordering = ['texto']
        verbose_name = 'Resposta Frequente'
        verbose_name_plural = 'Respostas Frequentes'
