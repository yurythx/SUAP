import datetime

from django.core.exceptions import ValidationError

from djtools.db import models
from djtools.utils import somar_dias, somar_dias_uteis
from edu.models import Aluno, CursoCampus, Modalidade
from rh.models import Servidor, Setor, UnidadeOrganizacional


class TipoNadaConsta(models.ModelPlus):
    descricao = models.CharFieldPlus(verbose_name='Descrição', unique=True)

    class Meta:
        verbose_name = 'Tipo de Nada Consta'
        verbose_name_plural = 'Tipos de Nada Consta'

    def __str__(self):
        return self.descricao


class ConfiguracaoNadaConsta(models.ModelPlus):
    descricao = models.CharFieldPlus(verbose_name='Descrição')
    uo = models.ForeignKeyPlus(UnidadeOrganizacional, verbose_name='Campus')
    modalidades = models.ManyToManyFieldPlus(Modalidade, verbose_name='Modalidades')
    ativo = models.BooleanField(verbose_name='Ativo', blank=True, default=True)

    class Meta:
        verbose_name = 'Configuração de Nada Consta'
        verbose_name_plural = 'Configurações de Nada Consta'

    def __str__(self):
        return self.descricao

    def is_ativo(self):
        return self.ativo and self.itemconfiguracaonadaconsta_set.exists()

    def get_absolute_url(self):
        return f'/edu/configuracaonadaconsta/{self.pk}/'

    def get_itens(self):
        return self.itemconfiguracaonadaconsta_set.all()

    def replicar(self, uos):
        modalidades = self.modalidades.all()
        for uo in uos:
            qs = ConfiguracaoNadaConsta.objects.filter(uo=uo, ativo=True, modalidades__in=modalidades)
            if not qs.exists():
                novo = ConfiguracaoNadaConsta()
                novo.descricao = f'{self.descricao} [{uo} REPLICADO de {self.uo}]'
                novo.uo = uo
                novo.save()

                for modalidade in modalidades:
                    novo.modalidades.add(modalidade)

                for item in self.get_itens():
                    novo_item = item
                    novo_item.id = None
                    novo_item.configuracao = novo
                    novo_item.save()
                    novo_item.setores_responsaveis.clear()
                    novo_item.servidores_responsaveis.clear()


class ItemConfiguracaoNadaConsta(models.ModelPlus):
    configuracao = models.ForeignKeyPlus(ConfiguracaoNadaConsta, verbose_name='Configuração')
    tipo_nada_consta = models.ForeignKeyPlus(TipoNadaConsta, verbose_name='Tipo de Nada Consta')
    exigido_transferencia_curso = models.BooleanField(verbose_name='Transferência de Curso', blank=True, default=False)
    exigido_transferencia_intercampus = models.BooleanField(verbose_name='Transferência Intercampus', blank=True, default=False)
    exigido_transferencia_externa = models.BooleanField(verbose_name='Transferência Externa', blank=True, default=False)
    exigido_trancamento_curso = models.BooleanField(verbose_name='Trancamento de Curso', blank=True, default=False)
    exigido_cancelamento_curso = models.BooleanField(verbose_name='Cancelamento de Curso', blank=True, default=False)
    exigido_emissao_diploma = models.BooleanField(verbose_name='Emissão de Diploma', blank=True, default=False)

    prazo_para_atendimento = models.IntegerField(verbose_name='Prazo para Atendimento', default=7, help_text='Dias úteis.')
    prazo_validade = models.IntegerField(verbose_name='Prazo de Validade', default=30, help_text='Validade do nada consta em dias corridos.')
    setores_responsaveis = models.ManyToManyFieldPlus(Setor, verbose_name='Setores Responsáveis', blank=True)
    servidores_responsaveis = models.ManyToManyFieldPlus(Servidor, verbose_name='Servidores Responsáveis', blank=True)
    avaliado_coordenacao_curso = models.BooleanField(
        verbose_name='Avaliado pela Coordenação de Curso',
        blank=True,
        default=False,
        help_text='Marque esta opção caso o nada consta seja avaliado pela atual coordenação de curso.',
    )

    cursos = models.ManyToManyFieldPlus(
        CursoCampus,
        verbose_name='Cursos',
        help_text='Informe somente se o item de nada consta for exigido para um conjunto específico de cursos do campus.',
    )

    class Meta:
        verbose_name = 'Item'
        verbose_name_plural = 'Itens'

    def get_responsaveis(self):
        responsaveis = []
        for setor in self.setores_responsaveis.all():
            responsaveis.append(setor.sigla)
        for servidor in self.servidores_responsaveis.all():
            responsaveis.append(str(servidor))
        if self.avaliado_coordenacao_curso:
            responsaveis.append('Coordenação de Curso')
        return ' / '.join(responsaveis) if responsaveis else 'Não informado'

    def pode_avaliar(self, user, curso_campus=None):
        if not user or user.is_anonymous or not user.get_vinculo().eh_servidor():
            return False
        if user.has_perm('comum.is_administrador_academico'):
            return True
        ids_setores = self.setores_responsaveis.values_list('id', flat=True)
        if user.get_vinculo().setor_id in ids_setores:
            return True
        usernames = list(self.servidores_responsaveis.values_list('matricula', flat=True))
        if self.avaliado_coordenacao_curso:
            if curso_campus.coordenador:
                usernames.append(curso_campus.coordenador.user.username)
            if curso_campus.coordenador_2:
                usernames.append(curso_campus.coordenador_2.user.username)
        return user.username in usernames

    def get_exigencias(self):
        exigencias = []
        if self.exigido_transferencia_curso:
            exigencias.append('Transferência de Curso')
        if self.exigido_transferencia_intercampus:
            exigencias.append('Transferência Intercampus')
        if self.exigido_transferencia_externa:
            exigencias.append('Transferência Externa')
        if self.exigido_trancamento_curso:
            exigencias.append('Trancamento de Curso')
        if self.exigido_cancelamento_curso:
            exigencias.append('Cancelamento de Curso')
        if self.exigido_emissao_diploma:
            exigencias.append('Emissão de Diploma')
        return exigencias

    def get_nada_consta_aluno(self, aluno_id):
        return NadaConsta.objects.filter(aluno_id=aluno_id, item_configuracao_id=self.id).last()


class NadaConstaManager(models.Manager):
    def sob_responsabilidade(self, user):
        vinculo = user.get_vinculo()
        qs_coordenador = self.filter(item_configuracao__avaliado_coordenacao_curso=True, aluno__curso_campus__coordenador__user=user)
        qs_vicecoordenador = self.filter(item_configuracao__avaliado_coordenacao_curso=True, aluno__curso_campus__coordenador_2__user=user)
        qs_servidor = self.none()
        qs_setor = self.none()
        if vinculo.eh_servidor():
            qs_servidor = self.filter(item_configuracao__servidores_responsaveis=vinculo.relacionamento)
            if vinculo.setor:
                qs_setor = self.filter(item_configuracao__setores_responsaveis=vinculo.setor)

        qs = qs_coordenador | qs_vicecoordenador | qs_servidor | qs_setor
        return qs.distinct()


class NadaConsta(models.ModelPlus):
    tipo = models.ForeignKeyPlus(TipoNadaConsta, verbose_name='Tipo')
    aluno = models.ForeignKeyPlus(Aluno, verbose_name='Aluno')
    valido = models.BooleanField(verbose_name='Válido', default=True)
    quitado = models.BooleanField(verbose_name='Quitado', null=True)
    data_solicitacao = models.DateTimeField(verbose_name='Data da Solicitação', null=True)
    data_avaliacao = models.DateTimeField(verbose_name='Data da Avaliação', null=True)
    prazo_avaliacao = models.DateField(verbose_name='Prazo para Avaliação', null=True)
    resposavel_avaliacao = models.ForeignKeyPlus('comum.User', verbose_name='Responsável pela Avaliação', null=True)
    justificativa_avaliacao = models.TextField(verbose_name='Justiticativa da Avaliação', null=True, blank=True)
    item_configuracao = models.ForeignKeyPlus(ItemConfiguracaoNadaConsta, verbose_name='Item de Configuração', null=True, on_delete=models.SET_NULL)
    data_validade = models.DateField(verbose_name='Data de Validade', null=True)
    data_revogacao = models.DateTimeField(verbose_name='Data da Revogação', null=True, blank=True)
    resposavel_revogacao = models.ForeignKeyPlus(
        'comum.User', verbose_name='Responsável pela Revogação', null=True, blank=True, related_name='nada_consta_revogados'
    )
    justificativa_revogacao = models.TextField(verbose_name='Justiticativa da Revogação', null=True, blank=True)
    justificativa_solicitacao = models.TextField(verbose_name='Justificativa da Solicitação', null=True, blank=False)

    objects = NadaConstaManager()

    class Meta:
        verbose_name = 'Registro de Nada Consta'
        verbose_name_plural = 'Registros de Nada Consta'

    def revogar(self, user):
        if self.pode_revogar(user):
            self.data_revogacao = datetime.datetime.now()
            self.resposavel_revogacao = user
            self.valido = False
            self.save()
            self.aluno.checar_registros_nada_consta()
        else:
            raise ValidationError('Você não tem permissão para revogar este nada consta.')

    def solicitar(self, justificativa=None):
        self.data_solicitacao = datetime.datetime.now()
        if justificativa:
            self.justificativa_solicitacao = justificativa
        if self.item_configuracao:
            prazo_atendimento = self.item_configuracao.prazo_para_atendimento
        else:
            prazo_atendimento = 7
        self.prazo_avaliacao = somar_dias_uteis(self.data_solicitacao, prazo_atendimento, self.aluno.curso_campus.diretoria.setor.uo)
        self.save()

    def avaliar(self, user):
        self.data_avaliacao = datetime.datetime.now()
        self.resposavel_avaliacao = user
        self.data_validade = somar_dias(self.data_avaliacao, self.item_configuracao.prazo_validade)
        self.save()
        self.aluno.checar_registros_nada_consta()

    def pode_avaliar(self, user):
        return (
            self.quitado is None
            and self.data_solicitacao is not None
            and self.item_configuracao
            and self.item_configuracao.pode_avaliar(user, self.aluno.curso_campus)
        )

    def pode_revogar(self, user):
        return (
            self.valido and self.quitado is not None and self.item_configuracao and self.item_configuracao.pode_avaliar(user, self.aluno.curso_campus)
        )

    def pode_gerar_declaracao(self):
        return self.valido and self.quitado

    def pode_solicitar(self):
        return self.valido and self.data_solicitacao is None

    def is_avaliacao_no_prazo(self):
        if self.prazo_avaliacao is None:
            self.atualizar_prazo_avaliacao()
        return datetime.date.today() <= self.prazo_avaliacao

    def is_expirado(self):
        if self.data_avaliacao and self.data_validade is None:
            self.data_validade = somar_dias(self.data_avaliacao.date(), self.item_configuracao.prazo_validade)
            self.save()
        return self.data_avaliacao and datetime.date.today() > self.data_validade

    def atualizar_prazo_avaliacao(self):
        self.prazo_avaliacao = somar_dias_uteis(
            self.data_solicitacao, self.item_configuracao.prazo_para_atendimento, self.aluno.curso_campus.diretoria.setor.uo
        )
        self.save()

    def get_situacao(self):
        if self.valido and self.data_solicitacao is None:
            return 'Não solicitado'
        if self.valido and self.data_solicitacao and self.data_avaliacao is None:
            return 'Solicitado'
        if self.valido and self.quitado and self.data_validade:
            return f'Quite (válido até {self.data_validade.strftime("%d/%m/%Y")})'
        if self.valido and not self.quitado and self.data_avaliacao:
            return 'Não quite'
