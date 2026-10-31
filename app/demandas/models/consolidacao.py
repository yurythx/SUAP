from datetime import datetime

from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import transaction
from django.template.defaultfilters import truncatewords
from sentry_sdk import capture_exception

from comum.utils import ferramentas_configuradas
from demandas.utils import Notificar
from djtools.db import models
from djtools.db.models import ModelPlus

from .demanda import AnalistaDesenvolvedor, HistoricoRevisao, Situacao


class DoD(ModelPlus):
    demanda = models.ForeignKeyPlus('demandas.Demanda')
    descricao = models.TextField('Descrição', null=True)
    detalhamento = models.TextField('Detalhamento', null=True)

    # atributo novo criado na demanda 1261
    # se demanda "antiga": atributo oculto no nível de formulário
    # se demanda "atual": Grupos de Usuários Relacionados (opcional)
    grupos_envolvidos = models.ManyToManyField(Group, verbose_name='Grupos de Usuários Relacionados')

    # atributo antigo cuja semântica foi alterada/ampliada na demanda 1261
    # este atributo precisa ser mantido e possui dupla responsabilidade (algo não recomendado)
    # se demanda "antiga": Grupos de Usuários Relacionados (opcional)
    # se demanda "atual": Novos Grupos de Usuários (opcional)
    envolvidos = models.TextField('Grupos de Usuários Relacionados/Novos Grupos de Usuários', null=True)

    validacao_revisao_solicitada = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Consolidação da Demanda'
        verbose_name_plural = 'Consolidações das Demandas'

        permissions = (('aprovar_dod', 'Pode aprovar demanda'), ('fechar_dod', 'Pode enviar demanda para aprovação'))

    def __str__(self):
        return truncatewords(self.descricao, 25)

    @property
    def feito(self):
        if self.descricao is None or self.descricao == '':
            return False

        if not self.especificacao_set.exists():
            return False

        return all(especificacao.atividades for especificacao in self.especificacao_set.all())

    @property
    def eh_demanda_antiga(self):
        """
        situação/conceito criado na demanda 1261.

                                30/jun/2022 23:59:59
        ------- demandas antigas ---------|--------- demandas atuais --------

        """
        demadas_abertas_ate = datetime(2022, 6, 30, 23, 59, 59)

        if self.demanda and self.demanda.aberto_em:
            return self.demanda.aberto_em <= demadas_abertas_ate

        return False

    @property
    def grupos_envolvidos_names(self):
        """
        método "confuso" devido à falta de padrão do
        conteúdo do atributo 'envolvidos'
            - grupos separados por vírgulas
            - 1 grupo por linha
        """
        names = []

        if ',' in self.envolvidos:
            # envolvidos = 'gru\n\rpo, grupo, gr\n\rupo,'
            names = list(self.envolvidos.split(','))

        if names:
            # names = ['gru\n\rpo', 'grupo', 'gr\n\rupo', '']
            names_tmp = []
            for name in names:
                names_tmp.extend(name.replace('\r', '').split('\n'))
            # names_tmp = ['gru', 'po', 'grupo', 'gr', 'upo', '']
            names = names_tmp
        else:
            names = list(self.envolvidos.replace('\r', '').split('\n'))

        names += [grupo.name for grupo in self.grupos_envolvidos.all()]

        names = [name.strip() for name in names if name.strip()]

        return sorted(set(names))

    @property
    def aceita_revisao(self) -> bool:
        """Se a consolidação aceita novas revisões de especificação.

        Só depois de aprovada (demanda em desenvolvimento ou em homologação) e enquanto a
        validação das revisões já propostas não foi pedida aos demandantes.
        """
        demanda = self.demanda
        return not self.validacao_revisao_solicitada and (demanda.em_desenvolvimento or demanda.em_homologacao)

    def get_revisoes_sem_especificacao(self):
        return self.revisaoespecificacao_set.filter(especificacao__isnull=True)

    @transaction.atomic
    def atualizar_ordens(self, ultima_especificacao_atualizada=None):
        especificacoes = self.especificacao_set.order_by('ordem')

        if ultima_especificacao_atualizada:
            ultima_especificacao_atualizada_ordem = ultima_especificacao_atualizada.ordem

            if ultima_especificacao_atualizada_ordem < 1:
                ultima_especificacao_atualizada_ordem = 1
            elif ultima_especificacao_atualizada_ordem > especificacoes.count():
                ultima_especificacao_atualizada_ordem = especificacoes.count()

            especificacoes_nova_seq = list(especificacoes.exclude(id=ultima_especificacao_atualizada.id))
            especificacoes_nova_seq.insert(ultima_especificacao_atualizada_ordem - 1, ultima_especificacao_atualizada)

            for seq, especificacao in enumerate(especificacoes_nova_seq, start=1):
                if especificacao.ordem != seq:
                    especificacao.ordem = seq
                    especificacao.save()
        else:
            for seq, especificacao in enumerate(especificacoes, start=1):
                if especificacao.ordem != seq:
                    especificacao.ordem = seq
                    especificacao.save()

    @transaction.atomic
    def solicitar_aprovacao_modificacoes(self, user):
        self.validacao_revisao_solicitada = True
        self.save()
        HistoricoRevisao.objects.create(demanda_id=self.demanda_id, usuario=user, acao=HistoricoRevisao.AVALIACAO_SOLICITADA)
        Notificar.solicitacao_aprovacao_modificacoes_especificacao(self.demanda)


class Especificacao(ModelPlus):
    dod = models.ForeignKeyPlus(DoD)
    nome = models.CharFieldPlus('Nome')
    atividades = models.TextField('Atividade(s)', blank=True)
    ordem = models.PositiveIntegerFieldPlus('Ordem da Especificação', default=1, min_value=1)
    gitlab_issue_url = models.TextField(verbose_name='URL do Gitlab', null=True, blank=True)

    class Meta:
        verbose_name = 'Especificação'
        verbose_name_plural = 'Especificações'
        ordering = ['ordem', 'nome']

    def __str__(self):
        return f'Especificação {self.ordem}: {self.nome}'

    def criar_issue_gitlab(self, request):
        if self.gitlab_issue_url is None:
            conf = ferramentas_configuradas()
            analista = AnalistaDesenvolvedor.objects.filter(usuario=request.user).first()
            data = {
                'title': f'Demanda {self.dod.demanda.id} - {self.nome}',
                'description': self.atividades,
                'labels': [conf['git_label_todo'], self.dod.demanda.area.area.nome],
                # 'milestone_id': 'conf['git_id_milestone_demanda']'
            }
            if analista:
                desenvolvedor = conf['git'].users.list(username=analista.username_gitlab)
                if desenvolvedor:
                    data['assignee_id'] = desenvolvedor[0].id
            try:
                issue = conf['git'].projects.get(conf['gitlab_suap_id']).issues.create(data)
            except Exception as e:
                capture_exception(e)
                return
            if issue:
                self.gitlab_issue_url = issue.web_url
                self.save()

    def vincular_issue_gitlab(self, url):
        self.gitlab_issue_url = url
        self.save()


class RevisaoEspecificacao(ModelPlus):
    dod = models.ForeignKeyPlus(DoD)
    especificacao = models.ForeignKeyPlus(Especificacao, verbose_name='Especificação', null=True, blank=True)
    nome = models.CharFieldPlus('Nome')
    atividades = models.TextField('Atividade(s)', blank=True)
    remocao_solicitada = models.BooleanField('Remoção solicitada', default=False)

    class Meta:
        verbose_name = 'Revisão da especificação'
        verbose_name_plural = 'Revisões das especificações'

    def __str__(self):
        return self.nome

    def clean(self):
        if (
            self.especificacao
            and self.nome == self.especificacao.nome
            and self.atividades == self.especificacao.atividades
            and not self.remocao_solicitada
        ):
            raise ValidationError('A revisão deve apresentar informações diferentes daquelas contidas na especificação original.')

    @transaction.atomic
    def aprovar(self, user):
        if self.remocao_solicitada:
            self.especificacao.delete()
            self.dod.atualizar_ordens()
        elif self.especificacao:
            self.especificacao.nome = self.nome
            self.especificacao.atividades = self.atividades
            self.especificacao.save()
        else:
            especificacao = Especificacao()
            especificacao.nome = self.nome
            especificacao.atividades = self.atividades
            especificacao.dod = self.dod
            especificacao.ordem = Especificacao.objects.filter(dod_id=self.dod_id).only('ordem').order_by('ordem').last().ordem + 1
            especificacao.save()

        if not RevisaoEspecificacao.objects.filter(dod_id=self.dod_id).exclude(id=self.id).exists():
            self.dod.validacao_revisao_solicitada = False
            self.dod.save()
            if self.dod.demanda.situacao != Situacao.ESTADO_EM_NEGOCIACAO:
                HistoricoRevisao.objects.create(demanda_id=self.dod.demanda_id, usuario=user, acao=HistoricoRevisao.AVALIACAO_CONCLUIDA)
        self.delete()

    @transaction.atomic
    def reprovar(self, user):
        if not RevisaoEspecificacao.objects.filter(dod_id=self.dod_id).exclude(id=self.id).exists():
            self.dod.validacao_revisao_solicitada = False
            self.dod.save()
            HistoricoRevisao.objects.create(demanda_id=self.dod.demanda_id, usuario=user, acao=HistoricoRevisao.AVALIACAO_CONCLUIDA)
        self.delete()

    def get_titulo(self):
        if self.especificacao:
            return f'Especificação {self.especificacao.ordem}: {self.nome}'
        else:
            return f'Nova especificação: {self.nome}'
