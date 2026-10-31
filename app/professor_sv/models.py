from datetime import datetime, timedelta

from django.contrib import admin
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.db.models import Max, Q
from django.utils.safestring import mark_safe

from comum.models import User
from comum.utils import get_sigla_reitoria
from djtools import forms
from djtools.db import models
from djtools.templatetags.filters import status
from pgd2.utils import setores_que_sou_chefe_direto_hoje
from professor_sv.utils import get_datetime_now


class ChoiceArrayField(ArrayField):
    def formfield(self, **kwargs):
        defaults = {'form_class': forms.MultipleChoiceField, 'widget': forms.CheckboxSelectMultiplePlus, 'choices': self.base_field.choices}
        defaults.update(kwargs)
        return super(ArrayField, self).formfield(**defaults)

    def to_python(self, value):
        value = super().to_python(value)
        if isinstance(value, list):
            return [self.base_field.to_python(val) for val in value]
        return value


class Perfil:
    # 1 - Substituto
    # 2 - Visitante

    SUBSTITUTO = 1
    VISITANTE = 2

    PERFIS_CHOICES = (
        (SUBSTITUTO, 'Substituto'),
        (VISITANTE, 'Visitante'),
    )

    @staticmethod
    def get_default():
        return [Perfil.SUBSTITUTO]

    @staticmethod
    def get_perfis_display(perfis):
        strs = []

        for m in Perfil.PERFIS_CHOICES:
            if m[0] in perfis:
                strs.append(m[1])

        return ' / '.join(strs)


class TempoExpiracao:
    TRINTA_DIAS = 30
    QUARENTA_E_CINCO_DIAS = 45
    NOVENTA_DIAS = 90

    DIAS_EXPIRA_CHOICES = (
        (TRINTA_DIAS, '30 dias'),
        (QUARENTA_E_CINCO_DIAS, '45 dias'),
        (NOVENTA_DIAS, '90 dias'),
    )

    @staticmethod
    def get_default():
        return 45


class Configuracao(models.ModelPlus):
    # - Cadastro único de registro único que define as configurações
    #   que devem ser observadas no cadastro das vagas

    # ================================
    # Limites
    # ================================
    qtd_docentes_efetivo_exercicio = models.PositiveIntegerField(
        verbose_name='Quantidade de docentes em efetivo exercício', help_text='Limite utilizado na alocação da vaga'
    )
    qtd_limite_professor_substituto = models.PositiveIntegerField(
        verbose_name='Quantidade limite de professor substituto', help_text='Limite utilizado na alocação da vaga'
    )
    qtd_limite_professor_visitante = models.PositiveIntegerField(
        verbose_name='Quantidade limite de professor visitante', help_text='Limite utilizado na alocação da vaga'
    )
    # Calculado por qtd_limite_professor_substituto + qtd_limite_professor_visitante
    qtd_limite_professor_substituto_visitante = models.PositiveIntegerField(
        verbose_name='Quantidade total de Substitutos e Visitantes', editable=False
    )
    percentual_limite_de_psv_sobre_ee = models.DecimalFieldPlus(
        verbose_name='% limite do total de Substitutos e Visitantes em relação aos docentes em efetivo exercício',
        help_text='EXEMPLO: a quantidade de total de Substitutos + Visitantes ocupando vagas não pode superar em 20% o total de docentes em efetivo exercício. Limite utilizado na alocação da vaga.',
    )

    # ================================
    # Vaga
    # ================================
    prefixo_vaga_substituto = models.CharFieldPlus(verbose_name='Prefixo do código de vaga de Substituto', max_length=20)
    prefixo_vaga_visitante = models.CharFieldPlus(verbose_name='Prefixo do código de vaga de Visitante', max_length=20)

    # ================================
    # Geral
    # ================================
    mov_emprest_re_campus_requer_justificativa = models.BooleanField(
        verbose_name='Toda movimentação de empréstimo de vaga da RE para um Campus requer justificativa'
    )
    mov_emprest_campus_campus_requer_justificativa = models.BooleanField(
        verbose_name='Toda movimentação de empréstimo de vaga de um Campus para um Campus requer justificativa'
    )
    #
    qtd_dias_alertar_expiracao_emprestimo_vaga = models.PositiveIntegerField(
        verbose_name='A partir de quantos dias se deve alertar sobre expiração de empréstimo de vaga',
        choices=TempoExpiracao.DIAS_EXPIRA_CHOICES,
        default=TempoExpiracao.get_default(),
    )
    qtd_dias_alertar_expiracao_contrato = models.PositiveIntegerField(
        verbose_name='A partir de quantos dias se deve alertar sobre expiração do contrato',
        choices=TempoExpiracao.DIAS_EXPIRA_CHOICES,
        default=TempoExpiracao.get_default(),
    )

    class Meta:
        verbose_name = 'Configuração'
        verbose_name_plural = 'Configurações'

    @staticmethod
    def get_configuracao():
        return Configuracao.objects.first()

    def clean(self):
        if self.qtd_limite_professor_substituto and self.qtd_docentes_efetivo_exercicio and self.percentual_limite_de_psv_sobre_ee:
            if self.qtd_limite_professor_substituto > self.qtd_docentes_efetivo_exercicio:
                raise ValidationError('A quantidade substitutos não pode ser maior que a quantidade de docentes em efetivo exercício')
            if self.qtd_limite_professor_visitante > self.qtd_docentes_efetivo_exercicio:
                raise ValidationError('A quantidade visitantes não pode ser maior que a quantidade de docentes em efetivo exercício')
            if (self.qtd_limite_professor_substituto + self.qtd_limite_professor_visitante) > self.qtd_docentes_efetivo_exercicio:
                raise ValidationError('A quantidade substitutos + visitantes não pode ser maior que a quantidade de docentes em efetivo exercício')
            if self.percentual_limite_de_psv_sobre_ee > 100:
                raise ValidationError('O percentual não pode ser maior que 100')

    @staticmethod
    def pode_iniciar_operacao_modulo():
        return Configuracao.get_configuracao() and Grupo.objects.exists() and Categoria.objects.exists()


class Categoria(models.ModelPlus):
    # Antigo GRUPO

    # Substitutos para Capacitação
    # Substitutos para outros motivos
    # (NÃO EXISTE MAIS) Visitantes ou Substitutos (vagas reversíveis)
    # Reserva PROEN/CODEPE

    titulo = models.CharFieldPlus(verbose_name='Título')
    perfis = ChoiceArrayField(
        verbose_name='Perfis',
        help_text='Perfis permitidos para as vagas relacionadas a este grupo',
        default=Perfil.get_default,
        base_field=models.PositiveIntegerField(choices=Perfil.PERFIS_CHOICES),
    )

    class Meta:
        verbose_name = 'Categoria'
        verbose_name_plural = 'Categorias'

    def __str__(self):
        return self.titulo

    @admin.display(description='Perfis')
    def get_perfis_display(self):
        return Perfil.get_perfis_display(self.perfis)

    def permite_substituto(self):
        return Perfil.SUBSTITUTO in self.perfis

    def permite_visitante(self):
        return Perfil.VISITANTE in self.perfis

    def existem_relacionados(self):
        return self.vaga_set.all().exists()

    def existem_relacionados_substituto(self):
        return self.vaga_set.filter(perfil=Perfil.SUBSTITUTO).exists()

    def existem_relacionados_visitante(self):
        return self.vaga_set.filter(perfil=Perfil.VISITANTE).exists()

    def clean(self):
        if self.id:
            if not self.permite_substituto() and self.existem_relacionados_substituto():
                raise ValidationError('Categoria não pode deixar ter o perfil Substituto por já ter vagas relacionadas com este perfil.')
            if not self.permite_visitante() and self.existem_relacionados_visitante():
                raise ValidationError('Categoria não pode deixar ter o perfil Visitante por já ter vagas relacionadas com este perfil.')


class Grupo(models.ModelPlus):
    # Antigo: Dono da vaga

    titulo = models.CharFieldPlus(verbose_name='Título')
    # UO dona da vaga
    uo = models.ForeignKeyPlus('rh.UnidadeOrganizacional', verbose_name='Campus')

    # Que vão especificamente aprovar movimentação de vaga
    setor_dg = models.ForeignKeyPlus('rh.Setor', verbose_name='Setor DG para aprovar movimentação', related_name='setores_dg', null=True, blank=True)
    setores_cogpe = models.ManyToManyFieldPlus(
        'rh.Setor', verbose_name='Setores de Gestão de Pessoas para aprovar movimentação', related_name='setores_cogpe', blank=True
    )

    # Que podem gerenciar vagas relacinadas a esse grupo
    # - Emprestar, ...
    setores_cogpe_gerenciar = models.ManyToManyFieldPlus(
        'rh.Setor', verbose_name='Setores de Gestão de Pessoas que podem gerenciar vagas deste grupo', blank=True
    )
    vinculos_pode_gerenciar_vaga = models.ManyToManyFieldPlus(
        'comum.Vinculo', verbose_name='Pessoas que podem gerenciar vagas deste grupo', blank=True
    )

    class Meta:
        verbose_name = 'Grupo'
        verbose_name_plural = 'Grupos'
        ordering = ('uo',)
        unique_together = ('uo',)

    def __str__(self):
        return self.titulo

    def user_pode_gerenciar(self, user):
        if user.has_group_cached('Gestor Sistêmico', ignore_groups_if_superuser=False):
            return True

        # Setores COGPE que podem gerenciar as vagas do grupo
        pode_pelo_setor = False
        if self.setores_cogpe_gerenciar:
            pode_pelo_setor = user.get_vinculo().setor in self.setores_cogpe_gerenciar.all()

        # Pessoas que podem gerenciar as vagas do grupo
        pode_pelo_vinculo = self.vinculos_pode_gerenciar_vaga.filter(id=user.get_vinculo().id).exists()

        return pode_pelo_vinculo or pode_pelo_setor

    @staticmethod
    def user_pode_cadastrar_contrato(user, vaga=None):
        # Se for relacionado ao grupo de permissões “Gestor Sistêmico”
        #  OU
        # Se for relacionado aos setores de gestão de pessoas da RE
        #  OU
        # Se quem pode gerencia as vagas relacionadas ao grupo da vaga

        if user.has_group_cached('Gestor Sistêmico'):
            return True

        grupo_re = Grupo.objects.filter(uo__sigla=get_sigla_reitoria()).first()
        if grupo_re:
            if grupo_re.user_pode_gerenciar(user):
                return True

        user_pode_gerenciar_grupo_de_vaga = False
        if vaga:
            if vaga.grupo_tomador:
                user_pode_gerenciar_grupo_de_vaga = vaga.grupo_tomador.user_pode_gerenciar(user)
            else:
                user_pode_gerenciar_grupo_de_vaga = vaga.grupo_dono.user_pode_gerenciar(user)
        else:
            grupos = Grupo.objects.all()
            for grupo in grupos:
                if grupo.user_pode_gerenciar(user):
                    user_pode_gerenciar_grupo_de_vaga = True
                    break

        return user_pode_gerenciar_grupo_de_vaga

    @staticmethod
    def get_grupos_user_pode_cadastrar_contrato(user):
        if user.has_group_cached('Gestor Sistêmico', ignore_groups_if_superuser=False):
            return Grupo.objects.all()

        vinculo = user.get_vinculo()
        qs = Grupo.objects.filter(Q(setores_cogpe_gerenciar__in=[vinculo.setor]) | Q(vinculos_pode_gerenciar_vaga=vinculo)).distinct()
        return qs

    def get_vagas_por_categoria(self, categoria_id=None):
        vagas = Vaga.objects.filter((Q(grupo_dono=self) & Q(grupo_tomador__isnull=True)) | (Q(grupo_tomador=self)))
        vagas = vagas.filter(ativo=True)
        if categoria_id:
            vagas = vagas.filter(categoria_id=categoria_id)
        return vagas

    def get_vagas_ocupadas_por_categoria(self, categoria_id=None, vagas_ocupadas=None):
        vagas = self.get_vagas_por_categoria(categoria_id=categoria_id)
        _vagas_ocupadas = vagas_ocupadas or Vaga.get_vagas_ocupadas()
        return vagas.filter(id__in=_vagas_ocupadas.values('id'))

    def get_vagas_desocupadas_por_categoria(self, categoria_id=None, vagas_desocupadas=None):
        vagas = self.get_vagas_por_categoria(categoria_id=categoria_id)
        _vagas_desocupadas = vagas_desocupadas or Vaga.get_vagas_desocupadas()
        return vagas.filter(id__in=_vagas_desocupadas.values('id'))


class Vaga(models.ModelPlus):
    codigo = models.CharFieldPlus(verbose_name='Código', max_length=30, editable=False, null=True)
    perfil = models.PositiveIntegerField('Perfil', choices=Perfil.PERFIS_CHOICES)

    categoria = models.ForeignKeyPlus('professor_sv.Categoria', verbose_name='Categoria')

    # Dono
    grupo_dono = models.ForeignKeyPlus('professor_sv.Grupo', verbose_name='Grupo dono', related_name='grupos_donos')

    # Tomador (quem tomou emprestado)
    grupo_tomador = models.ForeignKeyPlus(
        'professor_sv.Grupo', verbose_name='Grupo tomador atual', related_name='grupos_tomadores', null=True, blank=True
    )
    emprestimo_ate = models.DateFieldPlus(verbose_name='Empréstimo até', null=True, blank=True)

    ativo = models.BooleanField('Ativa', default=True)

    objects = models.Manager()

    class Meta:
        verbose_name = 'Vaga'
        verbose_name_plural = 'Vagas'

    def __str__(self):
        if self.codigo:
            return f'{self.codigo} - {self.get_perfil_display()}'
        return str(self.id)

    # ----------------------------------
    # Gerenciamento da vaga
    # ----------------------------------

    def get_emprestimo_str(self):
        if self.grupo_tomador and self.emprestimo_ate:
            emprestimo_ate = self.emprestimo_ate.strftime('%d/%m/%Y')
            return f'{self.grupo_tomador} até {emprestimo_ate}'
        return self.grupo_tomador

    get_emprestimo_str.short_description = 'Tomador atual'

    def get_emprestimo_str2(self):
        if self.grupo_tomador and self.emprestimo_ate:
            emprestimo_ate = self.emprestimo_ate.strftime('%d/%m/%Y')
            return f'Emprestado por {self.grupo_dono} para {self.grupo_tomador} até {emprestimo_ate}'
        return self.grupo_tomador

    get_emprestimo_str2.short_description = 'Tomador atual'

    def get_grupo_localizacao(self):
        if self.grupo_tomador and self.emprestimo_ate:
            return self.grupo_tomador
        return self.grupo_dono

    def get_grupo_localizacao_str(self):
        if self.grupo_tomador and self.emprestimo_ate:
            return self.get_emprestimo_str2()
        return self.grupo_dono

    @staticmethod
    def pode_cadastrar():
        return Configuracao.pode_iniciar_operacao_modulo()

    def pode_excluir_vaga(self, user=None):
        if user and not user.has_group_cached('Gestor Sistêmico'):
            return False, 'Usuário deve ser gestor sistêmico das vagas'

        if SolicitacaoEmprestimoVaga.objects.filter(vaga=self).exists() or self.get_contratos().exists():
            return False, 'Não pode haver qualquer empréstimo ou contrato relacionado'

        return True, None

    def pode_desativar_vaga(self, user):
        # Apenas se a vaga estiver com o DONO
        # Apenas a CODEPE (grupo gestor)
        # Apenas se não tiver emprestada
        # Se já não tiver desativada

        if self.pode_excluir_vaga(user)[0]:
            return False, 'É permitido excluir a vaga'

        if not self.ativo:
            return False, 'Vaga deve estar ativa'

        if not user.has_group_cached('Gestor Sistêmico'):
            return False, 'Usuário deve ser gestor sistêmico das vagas'

        # Não pode se tiver solicitação não finalizada relacionada
        if self.get_solicitacoes_emprestimo_relacionadas_nao_finalizadas().exists():
            return False, 'Impossível movimentar esta vaga se tiver alguma solicitação ainda não finalizada relacionada a esta vaga'

        # Não pode estar emprestada
        if self.grupo_tomador:
            return False, 'Impossível desativar uma vaga emprestada'

        if Vaga.get_vagas_ocupadas(vaga=self).exists():
            return False, 'Impossível desativar uma vaga ocupada'

        return True, None

    def pode_ativar_vaga(self, user):
        # Apenas se a vaga estiver com o DONO
        # Apenas a CODEPE (grupo gestor)
        # Apenas se não tiver emprestada
        # Se já tiver desativada

        if self.ativo:
            return False, 'Vaga deve estar inativa'

        if not user.has_group_cached('Gestor Sistêmico'):
            return False, 'Usuário deve ser gestor sistêmico das vagas'

        # Não pode se tiver solicitação não finalizada relacionada
        if self.get_solicitacoes_emprestimo_relacionadas_nao_finalizadas().exists():
            return False, 'Impossível movimentar esta vaga se tiver alguma solicitação ainda não finalizada relacionada a esta vaga'

        # Não pode estar emprestada
        if self.grupo_tomador:
            return False, 'Impossível desativar uma vaga emprestada'

        return True, None

    @staticmethod
    def gerar_vagas(user, perfil, categoria, grupo_dono, quantidade):
        # Cadastro das vagas e histórico
        indices = list(range(quantidade))
        for _indice in indices:
            vaga = Vaga()
            vaga.perfil = perfil
            vaga.categoria = categoria
            vaga.grupo_dono = grupo_dono
            vaga.save()

            id = str(vaga.id).zfill(7)
            prefixo = None
            if perfil == Perfil.SUBSTITUTO:
                prefixo = Configuracao.get_configuracao().prefixo_vaga_substituto
            elif perfil == Perfil.VISITANTE:
                prefixo = Configuracao.get_configuracao().prefixo_vaga_visitante
            vaga.codigo = f'{prefixo.upper()}/{id}'
            vaga.save()

            hdv = HistoricoMovimentacaoVaga()
            hdv.vaga = vaga
            hdv.grupo_tomador = vaga.grupo_dono
            hdv.data_inicio = get_datetime_now()
            hdv.tipo_movimentacao = HistoricoMovimentacaoVaga.DISTRIBUICAO
            hdv.usuario_cadastro = user
            hdv.save()

    def get_historico_dono(self):
        return HistoricoMovimentacaoVaga.objects.filter(vaga=self)

    def get_solicitacoes_emprestimo_relacionadas(self):
        return SolicitacaoEmprestimoVaga.objects.filter(vaga=self, cancelada=False)

    def get_solicitacoes_emprestimo_relacionadas_nao_finalizadas(self):
        return self.get_solicitacoes_emprestimo_relacionadas().filter(finalizado=False)

    def get_solicitacoes_emprestimo_relacionadas_finalizadas(self):
        return self.get_solicitacoes_emprestimo_relacionadas().filter(finalizado=True)

    def get_solicitacoes_emprestimo_relacionadas_deferidas_finalizadas_sem_historico_dono(self):
        solicitacoes = self.get_solicitacoes_emprestimo_relacionadas_finalizadas()
        solicitacoes = solicitacoes.filter(
            setor_cogpe_parecer=SolicitacaoEmprestimoVaga.DEFERIDO, setor_dg_parecer=SolicitacaoEmprestimoVaga.DEFERIDO
        )
        ids_solicitacoes_exclude = HistoricoMovimentacaoVaga.objects.filter(vaga=self, solicitacao_emprestimo__in=solicitacoes).values(
            'solicitacao_emprestimo__id'
        )
        return solicitacoes.exclude(id__in=ids_solicitacoes_exclude)

    def get_ultimo_historico_movimentacao(self):
        emprestimos = HistoricoMovimentacaoVaga.objects.filter(vaga=self)
        return emprestimos.order_by('-id').first()

    def get_ultimo_historico_movimentacao_emprestimo(self):
        emprestimos = HistoricoMovimentacaoVaga.objects.filter(vaga=self)
        emprestimos = emprestimos.filter(tipo_movimentacao=HistoricoMovimentacaoVaga.EMPRESTIMO)
        return emprestimos.order_by('-id').first()

    def get_emprestimo_vencido(self):
        # data_fim__lt=datetime.datetime(2025, 6, 12).date()
        ultimo_historico_movimentacao = self.get_ultimo_historico_movimentacao()
        if (
            ultimo_historico_movimentacao
            and ultimo_historico_movimentacao.tipo_movimentacao == HistoricoMovimentacaoVaga.EMPRESTIMO
            and ultimo_historico_movimentacao.data_fim
            and ultimo_historico_movimentacao.data_fim < get_datetime_now().date()
        ):
            return ultimo_historico_movimentacao
        return None

    @staticmethod
    def get_vagas_emprestimos_a_vencer(qtd_dias_alerta):
        """Retorna vagas ativas cujo empréstimo vence em até ``qtd_dias_alerta`` dias.

        Garante que o histórico de movimentação está atualizado antes de
        consultar; em seguida, considera apenas o último ``HistoricoMovimentacaoVaga``
        de cada vaga (maior id) cuja movimentação é ``EMPRESTIMO`` e cuja
        ``data_fim`` está entre hoje e a data limite.

        Args:
            qtd_dias_alerta: número de dias à frente que define a janela de alerta.

        Returns:
            QuerySet[Vaga]: vagas ativas com empréstimo prestes a vencer.
        """
        Vaga.atualizar_historico_movimentacao_vagas()

        hoje = datetime.now().date()
        alerta = hoje + timedelta(days=int(qtd_dias_alerta))
        ultimos_historicos_ids = (
            HistoricoMovimentacaoVaga.objects.filter(vaga__ativo=True)
            .values('vaga')
            .annotate(ultimo_id=Max('id'))
            .values_list('ultimo_id', flat=True)
        )
        vaga_ids_a_vencer = HistoricoMovimentacaoVaga.objects.filter(
            id__in=list(ultimos_historicos_ids),
            tipo_movimentacao=HistoricoMovimentacaoVaga.EMPRESTIMO,
            data_fim__gte=hoje,
            data_fim__lte=alerta,
        ).values_list('vaga_id', flat=True)
        return Vaga.objects.filter(ativo=True, id__in=vaga_ids_a_vencer)

    def pode_emprestar_vaga_da_re(self, user):
        return bool(self.grupo_dono.uo.eh_reitoria and self.grupo_dono.user_pode_gerenciar(user))

    def pode_emprestar_vaga(self, user, tomador=None, justificativa=None):
        # CODEPE/RE
        # - Cadastrar novas vagas
        # - Emprestar vaga de um campus para RE. Sem justificativa e prazo.
        # - Emprestar vaga de RE para um campus. Sem justificativa e prazo.
        # - Emprestar vaga de RE para um campus. Com justificativa e prazo.
        # Campus
        # - Emprestar vaga do campus para outro campus. Com justificativa e prazo.

        if not self.ativo:
            return False, 'Vaga deve estar ativa'

        # Para movimentar esta vaga deve
        # - Se o user poder gerenciar vagas deste grupo
        if not self.grupo_dono.user_pode_gerenciar(user):
            return False, f'Você deve poder gerenciar vagas do(a) {self.grupo_dono}'

        # Não pode se tiver solicitação não finalizada relacionada
        if self.get_solicitacoes_emprestimo_relacionadas_nao_finalizadas().exists():
            return False, 'Impossível movimentar esta vaga se tiver alguma solicitação ainda não finalizada relacionada a esta vaga'

        # Nao pode se a vaga que quer emprestar não estiver com seu dono
        if self.grupo_tomador:
            return False, 'Impossível movimentar uma vaga emprestada'

        # Não pode emprestar para o mesmo lugar
        if self.grupo_dono == tomador:
            return False, 'Impossível emprestar para o dono'

        if tomador:
            config_config_movimentacao_emprestimo_re_campus_requer_justificativa = (
                Configuracao.get_configuracao().mov_emprest_re_campus_requer_justificativa
            )
            config_movimentacao_emprestimo_campus_campus_requer_justificativa = (
                Configuracao.get_configuracao().mov_emprest_campus_campus_requer_justificativa
            )

            # - Se esta vaga for da RE
            #   - O destino só poderá ser um campus
            #   - Deve ter justificativa se a configuração geral permitir
            if self.grupo_dono.uo.eh_reitoria:
                if tomador.uo.eh_reitoria:
                    return False, 'Uma vaga da RE só pode ser emprestada para um Campus'
                if config_config_movimentacao_emprestimo_re_campus_requer_justificativa and not justificativa:
                    return False, 'Este empréstimo deve ter justificativa'

            # - Se esta vaga for de um CAMPUS
            #   - O destino só pode ser o campus
            #   - Deve ter justificativa se a configuração geral permitir
            if not self.grupo_dono.uo.eh_reitoria:
                if tomador.uo.eh_reitoria:
                    return False, 'Uma vaga do Campus só pode ser emprestada para um Campus'
                if not tomador.uo.eh_reitoria and config_movimentacao_emprestimo_campus_campus_requer_justificativa and not justificativa:
                    return False, 'Este empréstimo deve ter justificativa'

        return True, None

    def pode_desfazer_emprestimo_vaga(self, user):
        # Dono pega de volta
        # Se não tiver desativada
        # Apenas se for o dono e for quem possa movimentar
        # Apenas se tiver emprestada
        # Apenas se não tiver solicitação de empréstimo não finalizada

        if not self.ativo:
            return False, 'Vaga deve estar ativa'

        # Para movimentar esta vaga deve
        # - Se o user poder gerenciar vagas deste grupo
        if not self.grupo_dono.user_pode_gerenciar(user):
            return False, f'Você deve poder gerenciar vagas do(a) {self.grupo_dono}'

        # Apenas se tiver emprestada
        if not self.grupo_tomador:
            return False, 'Impossível desfazer empréstimos de uma vaga que não está emprestada'

        # Não pode se tiver solicitação não finalizada relacionada
        if self.get_solicitacoes_emprestimo_relacionadas_nao_finalizadas().exists():
            return False, 'Impossível desfazer empréstimo se esta vaga tiver alguma solicitação de empréstimo ainda não finalizada'

        return True, None

    def pode_devolver_emprestimo_vaga(self, user):
        # Tomador por devolver

        # Se não tiver desativada
        # Apenas se for o tomador e for quem possa movimentar a vaga do tomador
        # Apenas se tiver emprestada
        # Apenas se não tiver solicitação de empréstimo não finalizada

        if not self.ativo:
            return False, 'Vaga deve estar ativa'

        # Apenas se tiver emprestada
        if not self.grupo_tomador:
            return False, 'Impossível devolver empréstimos de uma vaga que não está emprestada'

        if self.grupo_dono.user_pode_gerenciar(user):
            return False, 'Você deve desfazer o empréstimo'

        # Para movimentar esta vaga deve
        # - for quem possa movimentar a vaga do tomador

        if not self.grupo_tomador.user_pode_gerenciar(user):
            return False, f'Você deve poder gerenciar vagas do(a) {self.grupo_tomador}'

        # Não pode se tiver solicitação não finalizada relacionada
        if self.get_solicitacoes_emprestimo_relacionadas_nao_finalizadas().exists():
            return False, 'Impossível devolver empréstimo se esta vaga tiver alguma solicitação de empréstimo ainda não finalizada'

        return True, None

    def emprestar_vaga(self, user, vaga, tomador, justificativa, emprestimo_ate, processo):
        solicitacao = SolicitacaoEmprestimoVaga.gerar_solicitacao_emprestimo(user, vaga, tomador, justificativa, emprestimo_ate, processo)

        if user.has_group_cached('Gestor Sistêmico'):
            # Não precisa da aprovação do setor de gestão de pessoas do campus e do DG do campus
            solicitacao.finalizar_solicitacao_emprestimo_direto(user)
        else:
            # Quando a vaga for da RE
            pode_finalizar_solicitacao_emprestimo = vaga.pode_emprestar_vaga_da_re(user)
            if pode_finalizar_solicitacao_emprestimo:
                solicitacao.finalizar_solicitacao_emprestimo_direto(user)
            else:
                # Quando quem tiver cadastrando o emprestimo for o chefe da cogpe do campus dono da vaga
                if solicitacao.pode_analisar_solicitacao_como_cogpe(user.get_vinculo().relacionamento):
                    solicitacao.deferir_cogpe(user)

        self.atualizar_historico_movimentacao_vaga()

    def atualizar_historico_movimentacao_vaga(self):
        if self.ativo:
            # Busca as solicitacaoes finalizadas e atualiza o tomador
            # - So atualiza tomador se ja nao existe historico pra ela
            solicitacoes_para_gerar_historico = self.get_solicitacoes_emprestimo_relacionadas_deferidas_finalizadas_sem_historico_dono()
            hoje = get_datetime_now().date()
            if solicitacoes_para_gerar_historico:
                for solicitacao in solicitacoes_para_gerar_historico:
                    # Histórico atual
                    historico_atual = self.get_ultimo_historico_movimentacao()
                    historico_atual.data_fim = hoje
                    historico_atual.save(update_fields=['data_fim'])

                    # Histórico novo
                    historico_novo = HistoricoMovimentacaoVaga()
                    historico_novo.vaga = self
                    historico_novo.grupo_tomador = solicitacao.grupo_tomador
                    historico_novo.data_inicio = hoje
                    historico_novo.data_fim = solicitacao.emprestimo_ate
                    historico_novo.solicitacao_emprestimo = solicitacao
                    historico_novo.tipo_movimentacao = HistoricoMovimentacaoVaga.EMPRESTIMO
                    historico_novo.usuario_cadastro = solicitacao.usuario_cadastro
                    historico_novo.save()

                    # Vaga
                    self.emprestimo_ate = solicitacao.emprestimo_ate
                    self.grupo_tomador = solicitacao.grupo_tomador
                    self.save(update_fields=['grupo_tomador', 'emprestimo_ate'])

            # Devolve para o dono após o fim do emprestimo
            # - Devolve emprestimos vencidos
            emprestimo_vencido = self.get_emprestimo_vencido()
            if emprestimo_vencido:
                # Histórico atual
                emprestimo_vencido.data_fim = hoje
                emprestimo_vencido.save(update_fields=['data_fim'])

                # Histórico novo
                historico_novo = HistoricoMovimentacaoVaga()
                historico_novo.vaga = self
                historico_novo.grupo_tomador = self.grupo_dono
                historico_novo.data_inicio = hoje
                historico_novo.tipo_movimentacao = HistoricoMovimentacaoVaga.EMPRESTIMO_DEVOLUCAO
                historico_novo.save()

                # Vaga
                self.grupo_tomador = None
                self.emprestimo_ate = None
                self.save(update_fields=['grupo_tomador', 'emprestimo_ate'])

    def atualizar_historico_movimentacao_vagas():
        """Atualiza o ``HistoricoMovimentacaoVaga`` apenas para vagas que de fato precisam.

        Pré-filtra em SQL dois conjuntos: vagas com solicitação de empréstimo
        deferida e finalizada cujo histórico ainda não foi gerado, e vagas
        cujo último histórico é um empréstimo já vencido. Sobre a união
        executa ``atualizar_historico_movimentacao_vaga`` por vaga; quando
        não há nada a processar, retorna imediatamente.
        """
        # Antes: iterava TODAS as vagas ativas (N) e chamava `atualizar_historico_movimentacao_vaga`,
        # que por sua vez faz 2 SELECTs por vaga (~2N queries só pra ver que não há nada a fazer).
        # Agora: pré-filtra em SQL apenas vagas que realmente precisam de atualização (caso típico: 0).
        hoje = get_datetime_now().date()

        # Critério 1: vagas com solicitação deferida finalizada cujo histórico ainda não foi gerado.
        ids_vagas_com_solicitacao_pendente = (
            SolicitacaoEmprestimoVaga.objects.filter(
                cancelada=False,
                finalizado=True,
                setor_cogpe_parecer=SolicitacaoEmprestimoVaga.DEFERIDO,
                setor_dg_parecer=SolicitacaoEmprestimoVaga.DEFERIDO,
                vaga__ativo=True,
            )
            .exclude(id__in=HistoricoMovimentacaoVaga.objects.filter(solicitacao_emprestimo__isnull=False).values('solicitacao_emprestimo_id'))
            .values_list('vaga_id', flat=True)
            .distinct()
        )

        # Critério 2: vagas onde o último histórico é EMPRESTIMO já vencido (data_fim < hoje).
        ultimos_historicos_ids = (
            HistoricoMovimentacaoVaga.objects.filter(vaga__ativo=True)
            .values('vaga')
            .annotate(ultimo_id=Max('id'))
            .values_list('ultimo_id', flat=True)
        )
        ids_vagas_emprestimo_vencido = HistoricoMovimentacaoVaga.objects.filter(
            id__in=list(ultimos_historicos_ids),
            tipo_movimentacao=HistoricoMovimentacaoVaga.EMPRESTIMO,
            data_fim__lt=hoje,
        ).values_list('vaga_id', flat=True)

        ids_a_processar = set(ids_vagas_com_solicitacao_pendente) | set(ids_vagas_emprestimo_vencido)
        if not ids_a_processar:
            return
        for vaga in Vaga.objects.filter(id__in=ids_a_processar):
            vaga.atualizar_historico_movimentacao_vaga()

    def desfazer_emprestimo_vaga(self, user):
        # Finaliza o emprestimo atual e gera historico de devoluicao
        # - na prática a vaga volta para o dono
        # - mesmo procedimento do devolver_emprestimo_vaga
        # Pode ser feito por quem emprestou

        if self.ativo:
            emprestimo = self.get_ultimo_historico_movimentacao_emprestimo()
            if emprestimo:
                hoje = get_datetime_now().date()

                # Histórico atual
                emprestimo.data_fim = hoje
                emprestimo.save(update_fields=['data_fim'])

                # Histórico novo
                historico_novo = HistoricoMovimentacaoVaga()
                historico_novo.vaga = self
                historico_novo.grupo_tomador = self.grupo_dono
                historico_novo.data_inicio = hoje
                historico_novo.tipo_movimentacao = HistoricoMovimentacaoVaga.EMPRESTIMO_DEVOLUCAO
                historico_novo.usuario_cadastro = user
                historico_novo.save()

                # Vaga
                self.grupo_tomador = None
                self.emprestimo_ate = None
                self.save(update_fields=['grupo_tomador', 'emprestimo_ate'])

    def devolver_emprestimo_vaga(self, user):
        # Finaliza o emprestimo atual e gera historico de devoluicao
        # - na prática a vaga volta para o dono
        # - mesmo procedimento do desfazer_emprestimo_vaga
        # Pode ser feito por quem está com a vaga emprestada
        if self.ativo:
            emprestimo = self.get_ultimo_historico_movimentacao_emprestimo()

            if emprestimo:
                hoje = get_datetime_now().date()

                # Histórico atual
                emprestimo.data_fim = hoje
                emprestimo.save(update_fields=['data_fim'])

                # Histórico novo
                historico_novo = HistoricoMovimentacaoVaga()
                historico_novo.vaga = self
                historico_novo.grupo_tomador = self.grupo_dono
                historico_novo.data_inicio = hoje
                historico_novo.tipo_movimentacao = HistoricoMovimentacaoVaga.EMPRESTIMO_DEVOLUCAO
                historico_novo.usuario_cadastro = user
                historico_novo.save()

                # Vaga
                self.grupo_tomador = None
                self.emprestimo_ate = None
                self.save(update_fields=['grupo_tomador', 'emprestimo_ate'])

    def ativar_desativar_vaga(self):
        self.ativo = not self.ativo
        self.save(update_fields=['ativo'])

    # ----------------------------------
    # Contrato
    # ----------------------------------
    def estah_na_re(self):
        if self.grupo_tomador:
            return self.grupo_tomador.uo.eh_reitoria
        return self.grupo_dono.uo.eh_reitoria

    def get_contratos(self):
        return Contrato.objects.filter(vaga=self).order_by('data_inicio')

    @staticmethod
    def get_vagas_ocupadas(vaga=None):
        ids_vagas_ocupadas = Contrato.objects.ativos().values_list('vaga_id')

        if ids_vagas_ocupadas:
            vagas = Vaga.objects.filter(ativo=True)
            vagas = vagas.filter(id__in=ids_vagas_ocupadas)
            # Saber se esta vaga está ocupada
            if vaga:
                vagas = vagas.filter(id=vaga.id)
            return vagas

        return Vaga.objects.none()

    def estah_ocupada(self):
        return Contrato.objects.ativos().filter(vaga_id=self.id).exists()

    estah_ocupada.short_description = 'Ocupada?'
    estah_ocupada.boolean = True

    @staticmethod
    def get_vagas_desocupadas(vaga=None):
        ids_vagas_ocupadas = Contrato.objects.ativos().values('vaga_id')
        vagas = Vaga.objects.filter(ativo=True).exclude(id__in=ids_vagas_ocupadas)

        # Saber se esta vaga está desocupada
        if vaga:
            vagas = vagas.filter(id=vaga.id)

        return vagas

    def eh_vaga_apta_para_cadastrar_contrato(self):
        self.atualizar_historico_movimentacao_vaga()

        # Validações básicas
        # =========================
        if not self.ativo:
            return False, 'Vaga deve estar ativa'

        if self.get_emprestimo_vencido():
            return False, 'Impossível cadastrar contrato se houver empréstimo vencido'

        # Não pode se tiver solicitação não finalizada relacionada
        if self.get_solicitacoes_emprestimo_relacionadas_nao_finalizadas().exists():
            return False, 'Impossível cadastrar contrato se tiver alguma solicitação ainda não finalizada relacionada a esta vaga'

        # Se estiver disponível para novo contrato (não estiver ocupada)
        if not Vaga.get_vagas_desocupadas(vaga=self).exists():
            return False, 'Impossível cadastrar contrato se houver contrato ativo'

        # Não pode cadastrar contrato pra vaga na RE
        if self.estah_na_re():
            return False, 'Impossível cadastrar contrato para vaga da RE'

        return True, None

    def eh_vaga_apta_para_editar_contrato(self):
        self.atualizar_historico_movimentacao_vaga()

        # Validações básicas
        # =========================
        if not self.ativo:
            return False, 'Vaga deve estar ativa'

        if self.get_emprestimo_vencido():
            return False, 'Impossível cadastrar contrato se houver empréstimo vencido'

        # Não pode se tiver solicitação não finalizada relacionada
        if self.get_solicitacoes_emprestimo_relacionadas_nao_finalizadas().exists():
            return False, 'Impossível cadastrar contrato se tiver alguma solicitação ainda não finalizada relacionada a esta vaga'

        return True, None

    @staticmethod
    def get_vagas_aptas_para_novo_contrato(vaga=None):
        vagas = Vaga.get_vagas_desocupadas(vaga)

        ids_vagas_inaptas = []
        for vaga in vagas:
            if not vaga.eh_vaga_apta_para_cadastrar_contrato()[0]:
                ids_vagas_inaptas.append(vaga.id)

        return vagas.exclude(id__in=ids_vagas_inaptas)


class SolicitacaoEmprestimoVaga(models.ModelPlus):
    vaga = models.ForeignKeyPlus('professor_sv.Vaga', verbose_name='Vaga')
    grupo_tomador = models.ForeignKeyPlus('professor_sv.Grupo', verbose_name='Grupo Tomador')

    data_cadastro = models.DateTimeFieldPlus('Data de cadastro', auto_now_add=True)
    usuario_cadastro = models.CurrentUserField(editable=False)

    processo = models.ForeignKeyPlus('processo_eletronico.Processo', verbose_name='Processo Eletrônico', blank=False)

    emprestimo_ate = models.DateFieldPlus(verbose_name='Empréstimo até', null=True, blank=True)
    justificativa = models.TextField('Justificativa', null=True, blank=True)

    DEFERIDO = 1
    INDEFERIDO = 2
    TIPO_PARECER = [[DEFERIDO, 'Deferido'], [INDEFERIDO, 'Indeferido']]
    setor_cogpe = models.ForeignKeyPlus(
        'rh.Setor',
        verbose_name='Setor Gestão de Pessoas relacionado ao parecer',
        related_name='setores_coord_aprovacao_emprestimo',
        null=True,
        blank=True,
    )
    setor_cogpe_parecer = models.PositiveIntegerField('Parecer Gestão de Pessoas', choices=TIPO_PARECER, null=True, blank=True)
    setor_cogpe_parecer_usuario = models.ForeignKeyPlus(
        User, verbose_name='Usuário parecer Gestão de Pessoas', null=True, blank=True, related_name='usuarios_setor_cogpe_parecer'
    )
    setor_cogpe_parecer_data = models.DateTimeFieldPlus(null=True, blank=True)
    setor_dg = models.ForeignKeyPlus(
        'rh.Setor', verbose_name='Setor DG relacionado ao parecer', related_name='setores_dg_aprovacao_emprestimo', null=True, blank=True
    )
    setor_dg_parecer = models.PositiveIntegerField('Parecer DG', choices=TIPO_PARECER, null=True, blank=True)
    setor_dg_parecer_usuario = models.ForeignKeyPlus(
        User, verbose_name='Usuário parecer DG', null=True, blank=True, related_name='usuarios_setor_dg_parecer'
    )
    setor_dg_parecer_data = models.DateTimeFieldPlus(null=True, blank=True)

    finalizado = models.BooleanField(default=False, verbose_name='Finalizado')

    cancelada = models.BooleanField(default=False, verbose_name='Cancelada')

    class Meta:
        verbose_name = 'Solicitação de Empréstimo da Vaga'
        verbose_name_plural = 'Solicitações de Empréstimo da Vaga'

    def __str__(self):
        return self.vaga

    def grupo_dono_eh_re(self):
        return self.vaga.grupo_dono.uo.eh_reitoria

    def get_setores_cogpe_para_aprovar_emprestimo(self):
        return self.vaga.grupo_dono.setores_cogpe.all()

    def get_setores_cogpe_para_aprovar_emprestimo_display(self):
        strs = []
        for m in self.get_setores_cogpe_para_aprovar_emprestimo():
            strs.append(str(m))
        return ', '.join(strs)

    def get_setor_dg_para_aprovar_emprestimo(self):
        return self.vaga.grupo_dono.setor_dg

    @staticmethod
    def get_solicitacoes_emprestimo_nao_finalizadas():
        return SolicitacaoEmprestimoVaga.objects.filter(cancelada=False, finalizado=False)

    @staticmethod
    def get_solicitacoes_emprestimo_aprovacao_pendente(servidor):
        setores_chefe = setores_que_sou_chefe_direto_hoje(servidor)

        solicitacoes = SolicitacaoEmprestimoVaga.get_solicitacoes_emprestimo_nao_finalizadas().order_by('data_cadastro')
        query_chefe_gestao_pessoas = Q(vaga__grupo_dono__setores_cogpe__in=setores_chefe) & Q(setor_cogpe_parecer__isnull=True)
        query_chefe_dg = (
            Q(vaga__grupo_dono__setor_dg__in=setores_chefe)
            & Q(setor_dg_parecer__isnull=True)
            & Q(setor_cogpe_parecer=SolicitacaoEmprestimoVaga.DEFERIDO)
        )

        return solicitacoes.filter(Q(query_chefe_gestao_pessoas) | Q(query_chefe_dg))

    @staticmethod
    def gerar_solicitacao_emprestimo(user, vaga, grupo_tomador, justificativa, emprestimo_ate, processo):
        sol = SolicitacaoEmprestimoVaga()
        sol.vaga = vaga
        sol.grupo_tomador = grupo_tomador
        sol.justificativa = justificativa
        sol.emprestimo_ate = emprestimo_ate
        sol.processo = processo
        sol.save()

        return sol

    def pode_analisar_solicitacao_como_cogpe(self, servidor):
        if self.finalizado or self.cancelada:
            return False
        if not (self.vaga.grupo_dono.setores_cogpe.exists() and self.vaga.grupo_dono.setor_dg):
            return False
        if self.setor_cogpe_parecer:
            return False

        setores_chefe = setores_que_sou_chefe_direto_hoje(servidor)
        setores_chefe = setores_chefe.filter(id__in=self.vaga.grupo_dono.setores_cogpe.values_list('id'))

        return setores_chefe.exists()

    def pode_analisar_solicitacao_como_dg(self, servidor):
        if self.finalizado or self.cancelada:
            return False
        if not (self.vaga.grupo_dono.setores_cogpe.all().exists() and self.vaga.grupo_dono.setor_dg):
            return False
        if not (self.setor_cogpe_parecer and self.setor_cogpe_parecer == self.DEFERIDO):
            return False
        if self.setor_dg_parecer:
            return False

        setores_chefe = setores_que_sou_chefe_direto_hoje(servidor)
        return self.vaga.grupo_dono.setor_dg in setores_chefe

    def pode_cancelar_solicitacao(self, user):
        # A vaga estiver ativa
        # Quem puder gerenciar o grupo dono relacionado a vaga
        # Se a solicitação não tiver finalizada e não tiver parecer de Gestão de Pessoas e DG

        if self.cancelada:
            return False

        if not self.vaga.ativo:
            return False

        if self.setor_cogpe_parecer or self.setor_dg_parecer or self.finalizado:
            return False

        return self.vaga.grupo_dono.user_pode_gerenciar(user)

    def deferir_cogpe(self, user):
        self.setor_cogpe = user.get_vinculo().setor
        self.setor_cogpe_parecer = self.DEFERIDO
        self.setor_cogpe_parecer_usuario = user
        self.setor_cogpe_parecer_data = get_datetime_now()
        self.save(update_fields=['setor_cogpe', 'setor_cogpe_parecer', 'setor_cogpe_parecer_usuario', 'setor_cogpe_parecer_data'])

    def deferir(self, user):
        if self.pode_analisar_solicitacao_como_cogpe(user.get_relacionamento()):
            self.deferir_cogpe(user)
            return True

        if self.pode_analisar_solicitacao_como_dg(user.get_relacionamento()):
            self.setor_dg = user.get_vinculo().setor
            self.setor_dg_parecer = self.DEFERIDO
            self.setor_dg_parecer_usuario = user
            self.setor_dg_parecer_data = get_datetime_now()
            self.save(update_fields=['setor_dg', 'setor_dg_parecer', 'setor_dg_parecer_usuario', 'setor_dg_parecer_data'])
            self.finalizar_solicitacao_emprestimo()
            self.vaga.atualizar_historico_movimentacao_vaga()
            return True
        return False

    def indeferir(self, user):
        if self.pode_analisar_solicitacao_como_cogpe(user.get_relacionamento()):
            self.setor_cogpe_parecer = self.INDEFERIDO
            self.setor_cogpe_parecer_usuario = user
            self.setor_cogpe_parecer_data = get_datetime_now()
            self.save(update_fields=['setor_cogpe_parecer', 'setor_cogpe_parecer_usuario', 'setor_cogpe_parecer_data'])
            self.finalizar_solicitacao_emprestimo()
            return True
        if self.pode_analisar_solicitacao_como_dg(user.get_relacionamento()):
            self.setor_dg_parecer = self.INDEFERIDO
            self.setor_dg_parecer_usuario = user
            self.setor_dg_parecer_data = get_datetime_now()
            self.save(update_fields=['setor_dg_parecer', 'setor_dg_parecer_usuario', 'setor_dg_parecer_data'])
            self.finalizar_solicitacao_emprestimo()
            return True
        return False

    def finalizar_solicitacao_emprestimo(self):
        self.finalizado = True
        self.save(update_fields=['finalizado'])

    def finalizar_solicitacao_emprestimo_direto(self, user):
        self.setor_cogpe = user.get_vinculo().setor
        self.setor_cogpe_parecer = self.DEFERIDO
        self.setor_cogpe_parecer_usuario = user
        self.setor_cogpe_parecer_data = get_datetime_now()

        self.setor_dg = user.get_vinculo().setor
        self.setor_dg_parecer = self.DEFERIDO
        self.setor_dg_parecer_usuario = user
        self.setor_dg_parecer_data = get_datetime_now()

        self.finalizado = True

        self.save(
            update_fields=[
                'setor_cogpe',
                'setor_cogpe_parecer',
                'setor_cogpe_parecer_usuario',
                'setor_cogpe_parecer_data',
                'setor_dg',
                'setor_dg_parecer',
                'setor_dg_parecer_usuario',
                'setor_dg_parecer_data',
                'finalizado',
            ]
        )


class HistoricoMovimentacaoVaga(models.ModelPlus):
    vaga = models.ForeignKeyPlus('professor_sv.Vaga', verbose_name='Vaga')
    grupo_tomador = models.ForeignKeyPlus('professor_sv.Grupo', verbose_name='Grupo Dono/Tomador')

    DISTRIBUICAO = 1
    EMPRESTIMO = 2
    EMPRESTIMO_DEVOLUCAO = 3
    REDISTRIBUICAO = 4
    TIPO_MOVIMENTACAO_CHOICES = [
        [DISTRIBUICAO, 'Distribuição'],
        [EMPRESTIMO, 'Empréstimo'],
        [EMPRESTIMO_DEVOLUCAO, 'Devolução'],
        [REDISTRIBUICAO, 'Redistribuição'],
    ]
    tipo_movimentacao = models.PositiveIntegerField('Tipo de Movimentação', choices=TIPO_MOVIMENTACAO_CHOICES, default=1)

    data_inicio = models.DateFieldPlus(verbose_name='Data Inicial')
    data_fim = models.DateFieldPlus(verbose_name='Data Final', null=True, blank=True)

    solicitacao_emprestimo = models.ForeignKeyPlus(
        'professor_sv.SolicitacaoEmprestimoVaga', verbose_name='Solicitação de Movimentação da Vaga', null=True, blank=True
    )

    usuario_cadastro = models.ForeignKeyPlus(User, verbose_name='Usuário', null=True, on_delete=models.PROTECT)
    data_cadastro = models.DateTimeFieldPlus('Data de cadastro', auto_now_add=True)

    class Meta:
        verbose_name = 'Histórico de Movimentação da Vaga'
        verbose_name_plural = 'Histórico de Movimentações da Vaga'

    def __str__(self):
        return f'{self.vaga} - {self.grupo_tomador}'


class ContratoQueryset(models.QuerySet):
    def ativos(self):
        datetime.now().date()
        return self.filter(concluido=False, cancelado=False)

    def a_iniciarem(self):
        hoje = datetime.now().date()
        return self.ativos().filter(data_inicio__gt=hoje)

    def em_andamento(self):
        hoje = datetime.now().date()
        return self.ativos().filter(data_inicio__lte=hoje, data_expira__gte=hoje)

    def expirados(self):
        hoje = datetime.now().date()
        return self.ativos().filter(data_expira__lt=hoje)

    def concluidos(self):
        return self.filter(concluido=True, cancelado=False)

    def cancelados(self):
        return self.filter(cancelado=True)


class ContratoManager(models.Manager):
    def get_queryset(self):
        return ContratoQueryset(self.model, using=self._db)

    def ativos(self):
        return self.get_queryset().ativos()

    def a_iniciarem(self):
        return self.get_queryset().a_iniciarem()

    def em_andamento(self):
        return self.get_queryset().em_andamento()

    def expirados(self):
        return self.get_queryset().expirados()

    def concluidos(self):
        return self.get_queryset().concluidos()

    def cancelados(self):
        return self.get_queryset().cancelados()


class Contrato(models.ModelPlus):
    """
    - Ativo: concluido=False, cancelado=False
    - A iniciar
    - Em andamento
    - Expirado
    - Concluído
    - Cancelado
    """

    SITUACAO_ATIVO = 1
    SITUACAO_A_INICIAR = 2
    SITUACAO_EM_ANDAMENTO = 3
    SITUACAO_EXPIRADO = 4
    SITUACAO_CONCLUIDO = 5
    SITUACAO_CANCELADO = 6
    SITUACAO_CHOICES = (
        (SITUACAO_ATIVO, 'Ativo'),
        (SITUACAO_A_INICIAR, 'A iniciar'),
        (SITUACAO_EM_ANDAMENTO, 'Em andamento'),
        (SITUACAO_EXPIRADO, 'Expirado'),
        (SITUACAO_CONCLUIDO, 'Encerrado'),
        (SITUACAO_CANCELADO, 'Cancelado'),
    )

    vaga = models.ForeignKeyPlus('professor_sv.Vaga', verbose_name='Vaga')

    servidor_docente = models.ForeignKeyPlus('rh.Servidor', verbose_name='Professor Substituto/Visitante', related_name='docentes_temporarios')
    servidor_docente_titular = models.ForeignKeyPlus(
        'rh.Servidor', verbose_name='Docente Efetivo', null=True, blank=True, related_name='docentes_efeitivos'
    )
    codigo_vaga_servidor_docente_titular = models.CharField(verbose_name='Código de vaga Docente Efetivo', max_length=10, null=True, blank=True)

    documento_eletronico = models.ForeignKeyPlus(
        'documento_eletronico.DocumentoTexto', verbose_name='Documento Eletrônico Contrato', related_name='contratos_docentes_temporarios'
    )
    data_inicio = models.DateFieldPlus('Data de Início')
    data_fim = models.DateFieldPlus('Data de Término')

    # Sera a data_fim no momento do cadastro
    # Depois de cadastrado será a data_fim dos aditivos de tempo
    data_expira = models.DateField('Data de Expiração', editable=False)

    concluido = models.BooleanField('Encerrado?', default=False, editable=False)
    data_conclusao = models.DateFieldPlus('Data de Conclusão', null=True, blank=True)
    justificativa_conclusao = models.TextField('Justificativa', null=True, blank=True)

    cancelado = models.BooleanField('Cancelado?', default=False, editable=False)

    objects = ContratoManager()

    class Meta:
        verbose_name = 'Contrato'
        verbose_name_plural = 'Contratos'

    def __str__(self):
        return f'{self.vaga} - {self.servidor_docente}'

    def get_situacao(self):
        if Contrato.objects.a_iniciarem().filter(id=self.id).exists():
            return self.SITUACAO_A_INICIAR
        if Contrato.objects.em_andamento().filter(id=self.id).exists():
            return self.SITUACAO_EM_ANDAMENTO
        if Contrato.objects.expirados().filter(id=self.id).exists():
            return self.SITUACAO_EXPIRADO

        if Contrato.objects.ativos().filter(id=self.id).exists():
            return self.SITUACAO_ATIVO
        if Contrato.objects.concluidos().filter(id=self.id).exists():
            return self.SITUACAO_CONCLUIDO
        if Contrato.objects.cancelados().filter(id=self.id).exists():
            return self.SITUACAO_CANCELADO

        return None

    def get_situacao_display(self):
        return mark_safe(status(self.SITUACAO_CHOICES[self.get_situacao() - 1][1]))

    get_situacao_display.short_description = 'Situação'

    def get_docente_efetivo(self):
        if self.vaga.perfil == Perfil.SUBSTITUTO:
            if self.servidor_docente_titular:
                if self.servidor_docente_titular.codigo_vaga:
                    return f'{self.servidor_docente_titular} #{self.servidor_docente_titular.codigo_vaga}'
                return f'{self.servidor_docente_titular}'
            return f'{self.codigo_vaga_servidor_docente_titular}'
        return None

    get_docente_efetivo.short_description = 'Docente Efetivo / Código de Vaga'

    def get_servidor_docente_uo(self):
        if self.servidor_docente and self.servidor_docente.setor:
            return self.servidor_docente.setor.uo
        return None

    def get_aditivo_tempo_mais_longo(self):
        return self.contratoaditivotempo_set.all().order_by('-data_fim').first()

    def get_info_aditivo(self):
        aditivo = self.get_aditivo_tempo_mais_longo()
        if aditivo:
            return f'Aditivado pelo documento {aditivo.documento_eletronico}'
        return None

    def get_qtd_dias_total(self):
        return (self.data_expira - self.data_inicio).days

    def get_qtd_dias_executado(self):
        return (datetime.now().date() - self.data_inicio).days

    def get_percentual_dias_executado(self):
        qtd_dias_total = self.get_qtd_dias_total()
        if qtd_dias_total == 0:
            return 0

        percentual = int(self.get_qtd_dias_executado() * 100 / qtd_dias_total)
        if percentual > 100:
            return 100
        if percentual < 0:
            return 0
        return percentual

    @staticmethod
    def user_pode_cadastrar_contrato(user, vaga=None):
        # Se for relacionado ao grupo de permissões “Gestor Sistêmico”
        #  OU
        # Se for relacionado aos setores de gestão de pessoas da RE
        #  OU
        # Se quem pode gerencia as vagas relacionadas ao grupo da vaga

        if user.has_group_cached('Gestor Sistêmico'):
            return True

        grupo_re = Grupo.objects.filter(uo__sigla=get_sigla_reitoria()).first()
        if grupo_re:
            if grupo_re.user_pode_gerenciar(user):
                return True

        user_pode_gerenciar_grupo_de_vaga = False
        if vaga:
            if vaga.grupo_tomador:
                user_pode_gerenciar_grupo_de_vaga = vaga.grupo_tomador.user_pode_gerenciar(user)
            else:
                user_pode_gerenciar_grupo_de_vaga = vaga.grupo_dono.user_pode_gerenciar(user)
        else:
            grupos = Grupo.objects.all()
            for grupo in grupos:
                if grupo.user_pode_gerenciar(user):
                    user_pode_gerenciar_grupo_de_vaga = True
                    break

        return user_pode_gerenciar_grupo_de_vaga

    @staticmethod
    def pode_iniciar_cadastro_contrato(vaga, user):
        # Validações básicas
        # =========================

        pode, msg = vaga.eh_vaga_apta_para_cadastrar_contrato()
        if not pode:
            return False, msg

        if not Contrato.user_pode_cadastrar_contrato(user=user, vaga=vaga):
            return False, 'Impossível cadastrar contrato se não puder gerenciar a vaga'

        # Limites
        # =========================
        adicionando_substituto = False
        adicionando_visitante = False
        if vaga.perfil == Perfil.SUBSTITUTO:
            adicionando_substituto = True
            if Contrato.estourou_limite_professor_substituto(adicionando=True):
                return False, 'Impossível cadastrar contrato por exceder o limite de Substitutos'
        if vaga.perfil == Perfil.VISITANTE:
            adicionando_visitante = True
            if Contrato.estourou_limite_professor_visitante(adicionando=True):
                return False, 'Impossível cadastrar contrato por exceder o limite de Visitantes'
        if Contrato.estourou_limite_professor_substituto_visitante_efetivo(
            adicionando_substituto=adicionando_substituto, adicionando_visitante=adicionando_visitante
        ):
            return False, 'Impossível cadastrar contrato por exceder o limite (quantidade ou o % limite) Substitutos e Visitantes'

        return True, None

    @staticmethod
    def pode_finalizar_cadastro_contrato(
        servidor_docente,
        documento_eletronico,
        vaga,
        data_fim,
        servidor_docente_titular=None,
        codigo_vaga_servidor_docente_titular=None,
        ignore_este_contrato=None,
    ):
        # - Não pode ter dois contratos ativo (“não concluido“ ou “não cancelado”)
        #   para o mesmo “Professor Substituto/Visitante”, “Documento Eletrônico Contrato”
        #   e “Docente Efetivo / Código de Vaga”
        """
        querys = []
        querys.append(Q(servidor_docente=servidor_docente))
        querys.append(Q(documento_eletronico=documento_eletronico))

        if vaga.perfil == Perfil.SUBSTITUTO:
            if servidor_docente_titular:
                querys.append(Q(servidor_docente_titular=servidor_docente_titular))
            else:
                querys.append(Q(codigo_vaga_servidor_docente_titular=codigo_vaga_servidor_docente_titular))

        outros_contratos = Contrato.objects.ativos().filter(reduce(operator.or_, querys))
        if ignore_este_contrato:
            outros_contratos = outros_contratos.exclude(id=ignore_este_contrato.id)
        if outros_contratos.exists():
            return (
                False,
                'Impossível cadastrar contrato se houver outro contrato ativo para o mesmo “Professor Substituto/Visitante”, “Documento Eletrônico Contrato” ou “Docente Efetivo / Código de Vaga”',
            )
        """
        # Rotina anterior foi desmembrada pelo WI #16324
        outros_contratos = Contrato.objects.ativos()
        if ignore_este_contrato:
            outros_contratos = outros_contratos.exclude(id=ignore_este_contrato.id)
        outros_contratos_mesmo_servidor_docente = outros_contratos.filter(servidor_docente=servidor_docente)
        outros_contratos_mesmo_documento_eletronico = outros_contratos.filter(documento_eletronico=documento_eletronico)
        outros_contratos_mesmo_docente_titular = None
        if vaga.perfil == Perfil.SUBSTITUTO:
            if servidor_docente_titular:
                outros_contratos_mesmo_docente_titular = outros_contratos.filter(servidor_docente_titular=servidor_docente_titular)
            else:
                outros_contratos_mesmo_docente_titular = outros_contratos.filter(
                    codigo_vaga_servidor_docente_titular=codigo_vaga_servidor_docente_titular
                )
        #
        if outros_contratos_mesmo_servidor_docente.exists():
            return (False, 'Impossível cadastrar contrato se houver outro contrato ativo para o mesmo “Professor Substituto/Visitante”')
        if outros_contratos_mesmo_documento_eletronico.exists():
            return (False, 'Impossível cadastrar contrato se houver outro contrato ativo para o mesmo “Documento Eletrônico Contrato”')
        if outros_contratos_mesmo_docente_titular and outros_contratos_mesmo_docente_titular.exists():
            return (False, 'Impossível cadastrar contrato se houver outro contrato ativo para o mesmo “Docente Efetivo / Código de Vaga”')

        # Retirado pelo WI #16324
        """
        # Docente vinculado deve ser o mesmo do grupo que vaga estiver localizada atualmente
        if servidor_docente.setor.uo != vaga.get_grupo_localizacao().uo:
            return (
                False,
                'Impossível cadastrar (ou editar) contrato se o “Professor Substituto/Visitante” não estiver vinculado ao mesmo campus do grupo relacionado',
            )
        """

        # Se a vaga relacionada estiver emprestada
        # - Periodo não pode exceder o do emprestimo (caso emprestimo tenha prazo)
        if vaga.grupo_tomador and vaga.emprestimo_ate and data_fim > vaga.emprestimo_ate:
            return False, 'Impossível cadastrar (ou editar) contrato se a data fim extrapolar a data fim do empréstimo da vaga'

        return True, None

    @staticmethod
    def estourou_limite_professor_substituto(adicionando=False):
        ocupadas = Vaga.get_vagas_ocupadas().filter(perfil=Perfil.SUBSTITUTO).count()
        if adicionando:
            ocupadas += 1
        limite = Configuracao.get_configuracao().qtd_limite_professor_substituto
        return ocupadas > limite

    @staticmethod
    def estourou_limite_professor_visitante(adicionando=False):
        ocupadas = Vaga.get_vagas_ocupadas().filter(perfil=Perfil.VISITANTE).count()
        if adicionando:
            ocupadas += 1
        limite = Configuracao.get_configuracao().qtd_limite_professor_visitante
        return ocupadas > limite

    @staticmethod
    def estourou_limite_professor_substituto_visitante(adicionando_substituto=False, adicionando_visitante=False):
        ocupadas_s = Vaga.get_vagas_ocupadas().filter(perfil=Perfil.SUBSTITUTO).count()
        if adicionando_substituto:
            ocupadas_s += 1

        ocupadas_v = Vaga.get_vagas_ocupadas().filter(perfil=Perfil.VISITANTE).count()
        if adicionando_visitante:
            ocupadas_v += 1

        ocupadas = ocupadas_s + ocupadas_v

        limite = Configuracao.get_configuracao().qtd_limite_professor_substituto_visitante

        return ocupadas > limite

    @staticmethod
    def estourou_limite_professor_substituto_visitante_efetivo(adicionando_substituto=None, adicionando_visitante=None):
        ocupadas_s = Vaga.get_vagas_ocupadas().filter(perfil=Perfil.SUBSTITUTO).count()
        if adicionando_substituto:
            ocupadas_s += adicionando_substituto

        ocupadas_v = Vaga.get_vagas_ocupadas().filter(perfil=Perfil.VISITANTE).count()
        if adicionando_visitante:
            ocupadas_v += adicionando_visitante

        ocupadas = ocupadas_s + ocupadas_v

        percentual_limite_de_psv_sobre_ee = Configuracao.get_configuracao().percentual_limite_de_psv_sobre_ee
        qtd_docentes_efetivo_exercicio = Configuracao.get_configuracao().qtd_docentes_efetivo_exercicio

        percentual_ocupacao = (ocupadas / qtd_docentes_efetivo_exercicio) * 100

        return percentual_ocupacao > percentual_limite_de_psv_sobre_ee

    @staticmethod
    def get_proximos_a_expirar(qtd_dias_alerta):
        hoje = datetime.now().date()
        qtd_dias_alerta = hoje + timedelta(days=int(qtd_dias_alerta))
        return Contrato.objects.ativos().filter(data_expira__gte=hoje, data_expira__lte=qtd_dias_alerta)

    def estah_com_uo_diferente_entre_docente_e_vaga(self) -> bool:
        # Docente vinculado deve ser o mesmo do grupo que vaga estiver localizada atualmente
        uo_docente = self.servidor_docente and self.servidor_docente.setor and self.servidor_docente.setor.uo
        grupo_localizacao = self.vaga.get_grupo_localizacao()
        uo_vaga = grupo_localizacao and grupo_localizacao.uo
        if uo_docente and uo_vaga:
            return uo_docente != uo_vaga
        return True  # Se o docente ou a vaga não tiver setor/uo, considerar como uo diferente para forçar validação

    def pode_gerenciar_contrato(self, user):
        # Todos da gestão e quem pode gerenciar a vaga relacionada
        if not Contrato.user_pode_cadastrar_contrato(user=user, vaga=self.vaga):
            return False, 'Impossível gerenciar contrato se não puder gerenciar a vaga relacionada'
        return True, None

    def pode_editar(self, user):
        # Qem puder gerenciar
        # Contrato ATIVO
        pode, msg = self.pode_gerenciar_contrato(user)
        if not pode:
            return False, msg

        pode, msg = self.vaga.eh_vaga_apta_para_editar_contrato()
        if not pode:
            return False, msg

        if self.get_situacao() in [self.SITUACAO_CONCLUIDO, self.SITUACAO_CANCELADO]:
            return False, 'Impossível gerenciar um contrato encerrado ou cancelado'

        # ----------
        ignore_este_contrato = self
        pode_finalizar_cadastro_contrato = Contrato.pode_finalizar_cadastro_contrato(
            servidor_docente=ignore_este_contrato.servidor_docente,
            documento_eletronico=ignore_este_contrato.documento_eletronico,
            vaga=ignore_este_contrato.vaga,
            data_fim=ignore_este_contrato.data_fim,
            servidor_docente_titular=ignore_este_contrato.servidor_docente_titular,
            codigo_vaga_servidor_docente_titular=ignore_este_contrato.codigo_vaga_servidor_docente_titular,
            ignore_este_contrato=ignore_este_contrato,
        )
        if not pode_finalizar_cadastro_contrato[0]:
            return pode_finalizar_cadastro_contrato

        """
        # Docente vinculado deve ser o mesmo do grupo que vaga estiver localizada atualmente
        if not (self.servidor_docente.setor.uo == self.vaga.get_grupo_localizacao().uo):
            return False, 'Impossível gerenciar o contrato se o “Professor Substituto/Visitante” não estiver vinculado ao mesmo campus do grupo relacionado'

        # Se a vaga relacionada estiver emprestada
        # - Periodo não pode exceder o do emprestimo (caso emprestimo tenha prazo)
        if self.vaga.grupo_tomador and self.vaga.emprestimo_ate and self.data_fim > self.vaga.emprestimo_ate:
            return False, 'Impossível gerenciar o contrato se a data fim extrapolar a data fim do empréstimo da vaga'
        """
        # ----------

        return True, None

    def pode_adicionar_publicacao_documento(self, user):
        pode, msg = self.pode_editar(user)
        if not pode:
            return False, msg
        return True, None

    def pode_remover_publicacao_documento(self, user):
        pode, msg = self.pode_editar(user)
        if not pode:
            return False, msg
        return True, None

    def pode_adicionar_aditivo(self, user):
        pode, msg = self.pode_editar(user)
        if not pode:
            return False, msg
        return True, None

    def pode_remover_aditivo(self, user):
        pode, msg = self.pode_editar(user)
        if not pode:
            return False, msg
        return True, None

    def pode_adicionar_aditivo_tempo(self, user):
        pode, msg = self.pode_editar(user)
        if not pode:
            return False, msg
        return True, None

    def pode_remover_aditivo_tempo(self, user):
        pode, msg = self.pode_editar(user)
        if not pode:
            return False, msg
        return True, None

    def pode_finalizar(self, user):
        pode, msg = self.pode_editar(user)
        if not pode:
            return False, msg

        if self.concluido:
            return False, 'Impossível remover conclusão de contrato não encerrado.'

        return True, None

    def pode_remover_finalizacao(self, user):
        pode, msg = self.pode_gerenciar_contrato(user)
        if not pode:
            return False, msg

        pode, msg = self.vaga.eh_vaga_apta_para_editar_contrato()
        if not pode:
            return False, msg

        if not self.concluido:
            return False, 'Impossível remover conclusão de contrato não encerrado.'

        return True, None

    def pode_cancelar(self, user):
        pode, msg = self.pode_editar(user)
        if not pode:
            return False, msg
        return True, None

    @staticmethod
    def concluir_contratos_expirados():
        expirados = Contrato.objects.expirados()
        for contrato in expirados:
            contrato.concluido = True
            contrato.data_conclusao = get_datetime_now()
            contrato.justificativa_conclusao = 'Encerrado por estar expirado'
            contrato.save()


class ContratoPublicacaoDocumento(models.ModelPlus):
    contrato = models.ForeignKeyPlus('professor_sv.Contrato', verbose_name='Contrato')
    documento_eletronico = models.ForeignKeyPlus(
        'documento_eletronico.DocumentoTexto', verbose_name='Documento Eletrônico', related_name='contratos_documentos_docentes_temporarios'
    )
    justificativa = models.TextField('Justificativa', null=True, blank=True)

    class Meta:
        verbose_name = 'Publicação do Contrato'
        verbose_name_plural = 'Publicações do Contrato'

    def __str__(self):
        return self.contrato


class ContratoAditivo(models.ModelPlus):
    contrato = models.ForeignKeyPlus('professor_sv.Contrato', verbose_name='Contrato')
    documento_eletronico = models.ForeignKeyPlus(
        'documento_eletronico.DocumentoTexto', verbose_name='Documento Eletrônico Aditivo', related_name='contratos_aditivos_docentes_temporarios'
    )
    justificativa = models.TextField('Justificativa', null=True, blank=True)

    class Meta:
        verbose_name = 'Aditivo do Contrato'
        verbose_name_plural = 'Aditivos do Contrato'

    def __str__(self):
        return self.contrato


class ContratoAditivoTempo(models.ModelPlus):
    contrato = models.ForeignKeyPlus('professor_sv.Contrato', verbose_name='Contrato')

    documento_eletronico = models.ForeignKeyPlus(
        'documento_eletronico.DocumentoTexto',
        verbose_name='Documento Eletrônico Aditivo',
        related_name='contratos_aditivos_tempo_docentes_temporarios',
    )
    data_inicio = models.DateFieldPlus('Data de Início')
    data_fim = models.DateFieldPlus('Data de Término')
    justificativa = models.TextField('Justificativa', null=True, blank=True)

    class Meta:
        verbose_name = 'Aditivo de Tempo do Contrato'
        verbose_name_plural = 'Aditivos de Tempo do Contrato'

    def __str__(self):
        return self.contrato


"""
class RegistroAcaoContrato(models.ModelPlus):
    data = models.DateTimeFieldPlus('Data', auto_now_add=True)
    user = models.CurrentUserField()

    observacao = models.TextField(null=True)
    contrato = models.ForeignKeyPlus('professor_sv.Contrato')

    TIPO_CADASTRO = 1
    TIPO_EDICAO_DADOS_GERAIS = 2
    TIPO_ADITIVO = 3
    TIPO_CANCELAMENTO = 4
    TIPO_FINALIZACAO = 5
    TIPO_CHOICES = (
        (TIPO_CADASTRO, 'Cadastrou'),
        (TIPO_EDICAO_DADOS_GERAIS, 'Editou'),
        (TIPO_ADITIVO, 'Aditivou'),
        (TIPO_CANCELAMENTO, 'Cancelou'),
        (TIPO_FINALIZACAO, 'Encerrou/Rescindiu'),
    )
    tipo = models.PositiveIntegerField(choices=TIPO_CHOICES, editable=False)

    class Meta:
        ordering = ('-data',)
        abstract = True

    def __str__(self):
        return self.observacao

    @staticmethod
    def registrar(tipo, contrato, obs=''):
        RegistroAcaoContrato.objects.create(tipo=tipo, contrato=contrato, observacao=obs)
"""
