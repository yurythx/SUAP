from datetime import datetime

from django.contrib import admin, messages
from comum.models import UsuarioGrupoSetor
from djtools.contrib.admin import CustomTabListFilter, ModelAdminPlus
from djtools.utils import httprr
from edu import tasks
from edu.forms import LaboratorioForm, QuestaoEducacensoForm, SolicitarAberturaExtemporaneaAdministradorForm, SolicitarAberturaExtemporaneaForm
from edu.models import (
    AberturaExtemporanea,
    AlteracaoRespostaJustificativaCensup,
    AuditoriaEnsino,
    ConfiguracaoAberturaExtemporanea,
    JustificativaCensup,
    Laboratorio,
    RespostaJustificativaCensup,
)
from edu.models.censos import QuestaoEducacenso, RegistroEducacenso


class RegistroEducacensoAdmin(ModelAdminPlus):
    list_display = 'ano_censo', 'numero_registro', 'privado', 'data_limite'
    list_display_icons = True
    list_filter = 'ano_censo', 'numero_registro', 'privado', 'data_limite'
    list_per_page = 15

    def get_action_bar(self, request):
        items = super(self.__class__, self).get_action_bar(request, True)
        if request.user.has_perm('edu.add_registroeducacenso'):
            items.append({'url': '/admin/edu/registroeducacenso/add/', 'label': 'Adicionar Questionário'})
            items.append({'url': '/edu/clonar_registroeducacenso/', 'label': 'Clonar Questionário'})
        return items


admin.site.register(RegistroEducacenso, RegistroEducacensoAdmin)


class QuestaoEducacensoAdmin(ModelAdminPlus):
    list_display_icons = True
    form = QuestaoEducacensoForm

    def response_change(self, request, obj):
        return tasks.processar_questao_educacenso(obj, False)

    def response_post_save_add(self, request, obj):
        return tasks.processar_questao_educacenso(obj, True)


admin.site.register(QuestaoEducacenso, QuestaoEducacensoAdmin)


class AuditoriaEnsinoAdmin(ModelAdminPlus):
    list_display = 'data_auditoria', 'data_resolucao_auditoria', 'campus', 'nivel_ensino', 'tipo_auditoria', 'atendente'
    list_display_icons = True
    list_filter = CustomTabListFilter, 'campus', 'nivel_ensino', 'tipo_auditoria', 'atendente', 'data_auditoria', 'data_resolucao_auditoria'
    list_per_page = 30
    export_to_xls = True
    actions = [
        'remover',
    ]
    show_count_on_tabs = True

    def has_change_permission(self, request, obj=None):
        return False

    def has_action_permission(self, request, obj=None):
        user = request.user
        return user.has_perm('comum.is_administrador_academico') or (
            user.has_perm('edu.change_auditoriaensino') and obj.is_auditoria_sistec() and user.get_vinculo() == obj.solicitante
        )

    def get_action_bar(self, request):
        items = super(self.__class__, self).get_action_bar(request, True)
        if request.user.has_perm('edu.add_auditoriaensino'):
            items.append({'url': '/edu/solicitar_auditoria/', 'label': 'Solicitar Auditoria'})
        return items

    def get_actions(self, request):
        user = request.user
        is_administrador = user.has_perm('comum.is_administrador_academico') and request.GET.get('tab', '') in [
            '',
            'tab_geracao_incompleta',
            'tab_solicitada',
        ]
        is_atendente = user.has_perm('edu.change_auditoriaensino') and request.GET.get('tab', '') in ['', 'tab_solicitada']
        return super().get_actions(request) if is_administrador or is_atendente else {}

    def remover(self, request, queryset):
        for element in queryset:
            element.delete()
        messages.success(request, 'Ação realizada com sucesso.')

    remover.short_description = 'Remover'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.has_perm('comum.is_administrador_academico'):
            uos = UsuarioGrupoSetor.objects.filter(usuario_grupo__user=request.user, usuario_grupo__group__name='Secretário Acadêmico').values_list(
                'setor__uo_id', flat=True
            )
            qs = qs.filter(campus_id__in=uos).exclude(tipo_auditoria__in=[AuditoriaEnsino.TIPO_ALUNO_SEM_SISTEC, AuditoriaEnsino.TIPO_CIDADE])
        return qs

    def get_tabs(self, request):
        return ['tab_solicitada', 'tab_gerada', 'tab_em_atendimento', 'tab_resolvida', 'tab_geracao_incompleta', 'tab_any_data']

    def tab_solicitada(self, request, queryset):
        return queryset.filter(tipo_auditoria=AuditoriaEnsino.TIPO_SISTEC, geracao_finalizada=False)

    tab_solicitada.short_description = 'Solicitadas'

    def tab_gerada(self, request, queryset):
        return queryset.filter(geracao_finalizada=True, data_ciencia_atendente__isnull=True)

    tab_gerada.short_description = 'Geradas'

    def tab_em_atendimento(self, request, queryset):
        return queryset.filter(data_ciencia_atendente__isnull=False, data_resolucao_auditoria__isnull=True)

    tab_em_atendimento.short_description = 'Em Atendimento'

    def tab_resolvida(self, request, queryset):
        return queryset.filter(data_resolucao_auditoria__isnull=False, atendente__isnull=False)

    tab_resolvida.short_description = 'Resolvidas'

    def tab_geracao_incompleta(self, request, queryset):
        return queryset.filter(geracao_finalizada=False)

    tab_geracao_incompleta.short_description = 'Geração Incompleta'


admin.site.register(AuditoriaEnsino, AuditoriaEnsinoAdmin)


class AberturaExtemporaneaAdmin(ModelAdminPlus):
    list_display = 'diretoria', 'situacao', 'solicitante', 'data_inicio', 'data_fim'
    list_display_icons = True
    list_filter = CustomTabListFilter, 'diretoria', 'situacao', 'solicitante', 'data_inicio', 'data_fim'
    list_per_page = 15
    actions = ['deferir', 'indeferir']

    def has_change_permission(self, request, obj=None):
        if obj and obj.situacao == AberturaExtemporanea.SOLICITADA:
            return request.user.has_perm('comum.is_administrador_academico') or request.user.get_vinculo() == obj.solicitante
        return False

    def has_delete_permission(self, request, obj=None):
        return self.has_change_permission(request, obj)

    def get_form(self, request, obj=None, **kwargs):
        if obj and obj.diretoria is None:
            self.change_form = SolicitarAberturaExtemporaneaAdministradorForm
        else:
            self.change_form = SolicitarAberturaExtemporaneaForm
        return super().get_form(request, obj, **kwargs)

    def get_action_bar(self, request):
        items = super(self.__class__, self).get_action_bar(request, True)
        if request.user.has_perm('edu.add_aberturaextemporanea'):
            items.append({'url': '/edu/solicitar_abertura_extemporanea/', 'label': 'Solicitar Abertura Extemporânea', 'css_class': 'success'})
        if request.user.has_perm('comum.is_administrador_academico'):
            items.append(
                {
                    'url': '/edu/solicitar_abertura_extemporanea_administrador/',
                    'label': 'Solicitar Abertura Extemporânea (Múltiplos campi)',
                    'css_class': 'success',
                }
            )
        if request.user.has_perm('comum.is_reitor'):
            if request.session.get('sessao_assinatura_eletronica'):
                items.append({'url': '/edu/finalizar_sessao_assinatura_eletronica/', 'label': 'Finalizar Sessão de Assinatura'})
            else:
                items.append({'url': '/edu/iniciar_sessao_assinatura_eletronica/', 'label': 'Iniciar Sessão de Assinatura'})
        return items

    def get_actions(self, request):
        actions = super().get_actions(request)
        if request.GET.get('tab') != 'tab_solicitada' or not request.session.get('sessao_assinatura_eletronica'):
            actions.pop('deferir')
            actions.pop('indeferir')
        return actions

    get_actions.short_description = 'Opções'

    def deferir(self, request, queryset):
        id_certificado, senha_certificado = request.session.get('sessao_assinatura_eletronica', (None, None))
        if not id_certificado or not senha_certificado:
            return httprr('..', 'Sessão de assinatura expirada. Por favor inicie a sessão de assinaturas novamente.')
        for obj in queryset:
            obj.deferir(request.user, id_certificado, senha_certificado)

        messages.success(request, 'Ação realizada com sucesso.')

    deferir.short_description = 'Deferir'

    def indeferir(self, request, queryset):
        for obj in queryset:
            obj.indeferir(request.user)

        messages.success(request, 'Ação realizada com sucesso.')

    indeferir.short_description = 'Indeferir'

    def get_tabs(self, request):
        return ['tab_any_data', 'tab_solicitada', 'tab_deferida', 'tab_iniciada']

    def tab_solicitada(self, request, queryset):
        return queryset.filter(situacao=AberturaExtemporanea.SOLICITADA)

    tab_solicitada.short_description = 'Solicitadas'

    def tab_deferida(self, request, queryset):
        return queryset.filter(situacao=AberturaExtemporanea.DEFERIDA)

    tab_deferida.short_description = 'Deferidas'

    def tab_iniciada(self, request, queryset):
        return queryset.filter(situacao=AberturaExtemporanea.INICIADA)

    tab_iniciada.short_description = 'Iniciadas'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        hoje = datetime.today()
        qs.filter(data_fim__lt=hoje).update(situacao=AberturaExtemporanea.FINALIZADA)
        return qs


admin.site.register(AberturaExtemporanea, AberturaExtemporaneaAdmin)


class ConfiguracaoAberturaExtemporaneaAdmin(ModelAdminPlus):
    list_display = (
        'tipo_modelo',
        'ativo',
    )
    list_display_icons = True


admin.site.register(ConfiguracaoAberturaExtemporanea, ConfiguracaoAberturaExtemporaneaAdmin)


class JustificativaCensupAdmin(ModelAdminPlus):
    list_display = (
        'ano_letivo',
        'arquivo',
    )
    list_display_icons = True


admin.site.register(JustificativaCensup, JustificativaCensupAdmin)


class RespostaJustificativaCensupAdmin(ModelAdminPlus):
    list_filter = (
        CustomTabListFilter,
        'aluno__curso_campus__diretoria__setor__uo',
        'aluno__curso_campus__diretoria',
        'aluno__curso_campus',
        'justificativa_censup',
    )
    list_display = 'aluno', 'justificativa_censup', 'resposta'
    list_display_icons = True

    def get_action_bar(self, request):
        items = super(self.__class__, self).get_action_bar(request, True)
        if request.user.has_perm('edu.add_justificativacensup'):
            items.append({'url': '/admin/edu/justificativacensup/add/', 'label': 'Importar Justificativa CENSUP', 'css_class': 'success'})
            items.append({'url': '/admin/edu/justificativacensup/', 'label': 'Listar Importações'})
        return items

    def has_change_permission(self, request, obj=None):
        return request.user.has_perm('edu.add_justificativacensup')

    def get_tabs(self, request):
        return ['tab_sem_resposta', 'tab_respondida', 'tab_any_data']

    def tab_sem_resposta(self, request, queryset):
        return queryset.filter(resposta__isnull=True)

    tab_sem_resposta.short_description = 'Sem Resposta'

    def tab_respondida(self, request, queryset):
        return queryset.filter(resposta__isnull=False)

    tab_respondida.short_description = 'Respondidas'


admin.site.register(RespostaJustificativaCensup, RespostaJustificativaCensupAdmin)


class AlteracaoRespostaJustificativaCensupAdmin(ModelAdminPlus):
    list_display = 'deferido', 'solicitante', 'data_solicitacao'
    list_display_icons = True
    list_filter = 'deferido', 'resposta_justificativa_censup__justificativa_censup'

    def get_action_bar(self, request):
        return super(self.__class__, self).get_action_bar(request, True)

    def has_change_permission(self, request, obj=None):
        return False


admin.site.register(AlteracaoRespostaJustificativaCensup, AlteracaoRespostaJustificativaCensupAdmin)


class LaboratorioAdmin(ModelAdminPlus):
    list_display = 'nome', 'descricao', 'ativo', 'sala__predio__uo'
    list_display_icons = True
    list_filter = 'ativo', 'sala__predio__uo'
    search_fields = ('nome',)
    form = LaboratorioForm

    def get_queryset(self, request):
        if request.user.has_perm('comum.is_administrador_academico'):
            return self.model.objects.all()
        return self.model.locals.all()


admin.site.register(Laboratorio, LaboratorioAdmin)
