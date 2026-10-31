from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.generic import CreateView, DetailView, UpdateView
from django.views.generic.base import View
from django.views.generic.edit import FormView
from formtools.wizard.views import SessionWizardView

from comum.models import Vinculo
from djtools.utils import httprr
from labfisico.models.solicitacao import SolicitacaoLabFisico

from .forms import (
    CancelarSolicitacaoLabFisicoForm,
    GuacamoleConnectionForm,
    IndeferirSolicitacaoLabFisicoForm,
    SolicitacaoLabFisicoForm,
    SolicitacaoLabFisicoMembrosForm,
)
from .models import AgendamentoLabFisico, GuacamoleConnection, GuacamoleConnectionGroup, programacao_laboratorio

if 'ldap_backend' in settings.INSTALLED_APPS:
    from ldap_backend.forms import SearchForm
    from ldap_backend.models import LdapUser


class GuacamoleConnectionGroupDetailView(PermissionRequiredMixin, DetailView):
    permission_required = ('labfisico.view_guacamoleconnectiongroup',)
    model = GuacamoleConnectionGroup
    slug_field = 'pk'
    slug_url_kwarg = 'pk'
    template_name = 'labfisico/lab_fisico.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        laboratorio = self.get_object()
        context['calendario'] = programacao_laboratorio(laboratorio)
        context['title'] = f'Detalhes do Laboratório {laboratorio}'
        return context


guacamole_connection_group_detail_view = GuacamoleConnectionGroupDetailView.as_view()


class GuacamoleConnectionCreateView(PermissionRequiredMixin, CreateView):
    title = 'Adicionar Cliente Guacamole'
    model = GuacamoleConnection
    form_class = GuacamoleConnectionForm
    template_name = 'labfisico/form.html'
    permission_required = ('labfisico.add_guacamoleconnection',)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['laboratorio_pk'] = self.kwargs.get('pk')
        kwargs['request'] = self.request
        return kwargs

    def get_success_url(self) -> str:
        app_label = self.model._meta.app_label
        model_name = self.model._meta.model_name
        return reverse(f'admin:{app_label}_{model_name}_changelist')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Adicionar Cliente Guacamole'
        return context


guacamole_connection_add_view = GuacamoleConnectionCreateView.as_view()

##################################################
# Solicitação e Agendamentos
##################################################


class SolicitacaoAgendamentoWizardView(PermissionRequiredMixin, SessionWizardView):
    title = 'Solicitar Agendamento'
    form_list = [SolicitacaoLabFisicoForm, SolicitacaoLabFisicoMembrosForm]
    permission_required = ('labfisico.add_solicitacaolabfisico',)
    template_name = 'solicitacao/form_wizard.html'
    query_string = True

    def load_gaucamole_connection_group(self):
        lab = self.kwargs.get('laboratorio', None)
        if lab is None:
            lab = GuacamoleConnectionGroup.objects.filter(pk=self.kwargs['pk']).first()
            self.kwargs['laboratorio'] = lab
            return lab
        return lab

    def dispatch(self, request, *args, **kwargs):
        lab = self.load_gaucamole_connection_group()
        if lab is None or not lab.pode_solicitar(request.user):
            msg = f'O usuário {request.user} não possui permissão para realizar solicitações ao laboratório {lab}'
            return httprr('..', msg, tag='error')
        #
        if not lab.is_sync_ldap():
            msg = f'O laboratório {lab} não está sincronizado com o LDAP, entre em contato com a TI'
            return httprr('..', msg, tag='error')
        #
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, form, **kwargs):
        context = super().get_context_data(form, **kwargs)
        context['title'] = 'Solitação de Laboratório Remoto'
        return context

    def get_success_url(self) -> str:
        app_label = SolicitacaoLabFisico._meta.app_label
        model_name = SolicitacaoLabFisico._meta.model_name
        return reverse(f'admin:{app_label}_{model_name}_changelist')

    def get_form_kwargs(self, step=None):
        kwargs = super().get_form_kwargs(step)
        if step is None or step == '0':
            kwargs['laboratorio_pk'] = self.kwargs['pk']
            kwargs['user'] = self.request.user
            kwargs['diario'] = self.request.GET.get('diario')
        else:
            cleaned_data = self.get_cleaned_data_for_step('0')
            kwargs['diario'] = cleaned_data.get('diario')
            kwargs['laboratorio'] = cleaned_data.get('laboratorio')
            kwargs['solicitante'] = self.request.user
        return kwargs

    def processar_lab_form(self, cleaned_data):
        return SolicitacaoLabFisico.objects.create(**cleaned_data)

    def processar_membros_form(self, cleaned_data):
        membros = list(cleaned_data['membros']) or []
        membros.extend([aluno.get_vinculo() for aluno in cleaned_data['alunos']])
        return membros

    def done(self, form_list, **kwargs):
        try:
            lab_data = form_list[0].cleaned_data
            membros_data = form_list[1].cleaned_data
            with transaction.atomic():
                solicitacao = self.processar_lab_form(lab_data)
                # Adicionando os alunos
                solicitacao.membros.set(self.processar_membros_form(membros_data))
                solicitacao.save()
                return httprr(self.get_success_url(), 'Solicitação realizada com sucesso')
        except Exception as e:
            return httprr('..', f'Não foi possível finalizar a solicitação: {e}', 'error')


solicitar_agendamento_view = SolicitacaoAgendamentoWizardView.as_view()


class SolicitacaoAgendamentoDetailView(PermissionRequiredMixin, DetailView):
    model = SolicitacaoLabFisico
    slug_field = 'pk'
    slug_url_kwarg = 'pk'
    template_name = 'solicitacao/solicitacao_agendamento.html'
    permission_required = ('labfisico.view_solicitacaolabfisico',)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        solicitacao = self.get_object()
        context['calendario'] = solicitacao.programacao()
        context['title'] = f'Solicitação de Agandamento do Laboratório {solicitacao.laboratorio}'
        context['pode_avaliar'] = solicitacao.pode_avaliar(self.request.user)
        return context


solicitacao_agendamento_detail_view = SolicitacaoAgendamentoDetailView.as_view()


class DeferirSolicitacaoAgendamentoView(PermissionRequiredMixin, View):
    permission_required = ('labfisico.pode_avaliar_solicitacao_labfisico',)

    def get(self, request, *args, **kwargs):
        object = get_object_or_404(SolicitacaoLabFisico, pk=kwargs['pk'])
        url = reverse('labfisico:solicitacao_agendamento', kwargs={'pk': self.kwargs['pk']})
        try:
            if object.pode_deferir():
                with transaction.atomic():
                    object.deferir()
                    object.save()
                return httprr(url, 'Solicitação deferida com sucesso.')
            else:
                return httprr(url, f'O Laboratório {object.laboratorio} está inativo.', 'error')
        except ValidationError as e:
            return httprr(url, f'Não foi possível realizar o indeferimento: {e}', 'error')


deferir_solicitacao_agendamento_view = DeferirSolicitacaoAgendamentoView.as_view()


class IndeferirSolicitacaoAgendamentoView(PermissionRequiredMixin, UpdateView):
    model = SolicitacaoLabFisico
    form_class = IndeferirSolicitacaoLabFisicoForm
    template_name = 'solicitacao/indeferir_solicitacao_agendamento.html'
    permission_required = ('labfisico.pode_avaliar_solicitacao_labfisico',)

    def form_valid(self, form):
        try:
            form.save()
            url = reverse('labfisico:solicitacao_agendamento', kwargs={'pk': self.kwargs['pk']})
            return httprr(url, 'Indeferimento realizado com sucesso.')
        except ValidationError as e:
            url = reverse('labfisico:solicitacao_agendamento', kwargs={'pk': self.kwargs['pk']})
            return httprr(url, f'Não foi possível realizar o indeferimento: {e}', 'error')

    def get_form_kwargs(self, *args, **kwargs):
        kwargs = super().get_form_kwargs(*args, **kwargs)
        kwargs['user'] = self.request.user
        return kwargs

    def get_success_url(self):
        return reverse('labfisico:solicitacao_agendamento', kwargs={'pk': self.kwargs['pk']})


indeferir_solicitacao_agendamento_view = IndeferirSolicitacaoAgendamentoView.as_view()


class CancelarSolicitacaoAgendamentoView(PermissionRequiredMixin, UpdateView):
    model = SolicitacaoLabFisico
    form_class = CancelarSolicitacaoLabFisicoForm
    template_name = 'solicitacao/indeferir_solicitacao_agendamento.html'
    permission_required = ('labfisico.pode_avaliar_solicitacao_labfisico', 'labfisico.change_solicitacaolabfisico')

    def form_valid(self, form):
        form.instance.user = self.request.user
        try:
            form.save()
            url = reverse('labfisico:solicitacao_agendamento', kwargs={'pk': self.kwargs['pk']})
            return httprr(url, 'Cancalmento realizado com sucesso.')
        except ValidationError as e:
            url = reverse('labfisico:solicitacao_agendamento', kwargs={'pk': self.kwargs['pk']})
            return httprr(url, f'Não foi possível realizar o cancelamento: {e}', 'error')

    def get_form_kwargs(self, *args, **kwargs):
        kwargs = super().get_form_kwargs(*args, **kwargs)
        kwargs['user'] = self.request.user
        return kwargs

    def get_success_url(self):
        return reverse('labfisico:solicitacao_agendamento', kwargs={'pk': self.kwargs['pk']})


cancelar_solicitacao_agendamento_view = CancelarSolicitacaoAgendamentoView.as_view()


class AgendamentoLabFisicoDetailView(PermissionRequiredMixin, DetailView):
    model = AgendamentoLabFisico
    slug_field = 'pk'
    slug_url_kwarg = 'pk'
    template_name = 'agendamento/agendamento_labfisico.html'
    permission_required = ('labfisico.view_agendamentolabfisico',)


agendamento_labfisico_detail_view = AgendamentoLabFisicoDetailView.as_view()


class GuacamoleConnectionGroupKillSessions(PermissionRequiredMixin, View):
    permission_required = ('labfisico.change_agendamentolabfisico',)

    def get(self, request, *args, **kwargs):
        try:
            url = '..'
            connection_group = get_object_or_404(GuacamoleConnectionGroup, pk=kwargs['pk'])
            connection_group.kill_sessions()
            return httprr(url, f'Sessões do {connection_group} finalizadas com sucesso.')
        except ValidationError as e:
            return httprr(url, f'Não foi possível finalizar as sessões do {connection_group}: {e}', 'error')


guacamole_connection_group_kill_sessions_view = GuacamoleConnectionGroupKillSessions.as_view()


class GuacamoleConnectionKillSessions(PermissionRequiredMixin, View):
    permission_required = ('labfisico.change_agendamentolabfisico',)

    def get(self, request, *args, **kwargs):
        try:
            url = '..'
            connection = get_object_or_404(GuacamoleConnection, pk=kwargs['pk'])
            connection.kill_sessions()
            return httprr(url, f'Sessões do {connection} finalizadas com sucesso.')
        except ValidationError as e:
            return httprr(url, f'Não foi possível finalizar as sessões do {connection}: {e}', 'error')


guacamole_connection_kill_sessions_view = GuacamoleConnectionKillSessions.as_view()


class AgendamentoSyncView(PermissionRequiredMixin, View):
    permission_required = ('labfisico.change_agendamentolabfisico',)

    def get(self, request, *args, **kwargs):
        object = get_object_or_404(AgendamentoLabFisico, pk=kwargs['pk'])
        url = '..'
        try:
            with transaction.atomic():
                object.ativar()
                object.save()
            return httprr(url, f'Laboratório {object.laboratorio} liberado.')
        except ValidationError as e:
            return httprr(url, f'Não foi possível liberar o laboratório {object.laboratorio}: {e}', 'error')


agendamento_sync_view = AgendamentoSyncView.as_view()


class AgendamentoShutdownView(PermissionRequiredMixin, View):
    permission_required = ('labfisico.change_agendamentolabfisico',)

    def get(self, request, *args, **kwargs):
        object = get_object_or_404(AgendamentoLabFisico, pk=kwargs['pk'])
        url = '..'
        try:
            with transaction.atomic():
                object.inativar()
                object.save()
            return httprr(url, f'Sessõs do laboratório {object.laboratorio} encerradas.')
        except ValidationError as e:
            return httprr(url, f'Não foi possível encerrar o laboratório {object.laboratorio}: {e}', 'error')


agendamento_shutdown_view = AgendamentoShutdownView.as_view()


class ProcurarUsuarioView(LoginRequiredMixin, FormView):
    template_name = 'procurar_form.html'
    if 'ldap_backend' in settings.INSTALLED_APPS:
        form_class = SearchForm
    model = None
    fields = None
    allowed_methods = ['GET', 'POST']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        solicitacao = get_object_or_404(SolicitacaoLabFisico, pk=self.kwargs['pk'])
        context['group'] = solicitacao.get_ldap_group()
        return context

    def form_valid(self, form):
        solicitacao = get_object_or_404(SolicitacaoLabFisico, pk=self.kwargs['pk'])
        group = solicitacao.get_ldap_group()
        users_list = form.search()
        for object in users_list:
            object.is_member = solicitacao.eh_membro(object)
        #
        return self.render_to_response(self.get_context_data(form=form, users_list=users_list, group=group.cn, object=solicitacao))


procurar_usuario_view = ProcurarUsuarioView.as_view()


class AdicionarMembroView(PermissionRequiredMixin, View):
    permission_required = ('labfisico.change_solicitacaolabfisico',)

    #
    def get(self, request, *args, **kwargs):
        #
        ldap_user = get_object_or_404(LdapUser, uid=self.kwargs['uid'])
        solicitacao = get_object_or_404(SolicitacaoLabFisico, pk=self.kwargs['pk'])
        url = solicitacao.get_absolute_url()
        try:
            with transaction.atomic():
                solicitacao.adicionar_membro(ldap_user.sAMAccountName)
                msg = 'Usuário adicionado com sucesso.'
                return httprr(url, msg)
        except Exception as e:
            return httprr(url, f'Não foi possível adicionar o usuário: {e}', 'error')


adicionar_membro_view = AdicionarMembroView.as_view()


class RemoverMembroView(PermissionRequiredMixin, View):
    permission_required = ('labfisico.change_solicitacaolabfisico',)
    #

    def get(self, request, *args, **kwargs):
        #
        solicitacao = get_object_or_404(SolicitacaoLabFisico, pk=self.kwargs['pk'])
        vinculo = get_object_or_404(Vinculo, id=self.kwargs['id'])
        url = solicitacao.get_absolute_url()
        try:
            with transaction.atomic():
                solicitacao.remover_membro(vinculo)
                msg = f'Usuário {vinculo.user.username} removido com sucesso.'
                return httprr(url, msg)
        except Exception as e:
            return httprr(url, f'Não foi possível remover o usuário: {e}', 'error')


remover_membro_view = RemoverMembroView.as_view()
