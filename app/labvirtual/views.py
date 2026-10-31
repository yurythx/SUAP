from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.generic import DetailView, UpdateView
from django.views.generic.base import View
from django.views.generic.edit import FormView
from formtools.wizard.views import SessionWizardView
from requests.exceptions import SSLError

from comum.models import Vinculo
from djtools.utils import httprr

from .forms import (
    CancelarSolicitacaoLabVirtualForm,
    IndeferirSolicitacaoLabVirtualForm,
    SearchForm,
    SolicitacaoLabVirtualForm,
    SolicitacaoLabVirtualMembrosForm,
)

#
from .models import AgendamentoLabVirtual, DesktopPool, SolicitacaoLabVirtual, VDIServer


class SyncDesktopPoolsView(LoginRequiredMixin, View):
    permission_required = ('labvirtual.add_desktoppool',)
    #

    def get_success_url(self) -> str:
        app_label = DesktopPool._meta.app_label
        model_name = DesktopPool._meta.model_name
        return reverse(f'admin:{app_label}_{model_name}_changelist')

    #
    def get(self, request, *args, **kwargs):
        #
        vmware_horizon = VDIServer.get_active_endpoint()
        desktop_pools = vmware_horizon.get_desktop_pools()
        for desktop_pool in desktop_pools:
            defaults = {
                'name': desktop_pool['name'],
                'description': desktop_pool['display_name'],
                # TODO: Perguntar se o numero de máquinas no pool pode variar.
                # 'capacidade': desktop_pool['pattern_naming_settings']['number_of_spare_machines']
            }
            DesktopPool.objects.update_or_create(desktop_pool_id=desktop_pool['id'], defaults=defaults)
        #
        url = self.get_success_url()
        return httprr(url, 'Sincronização realizada com sucesso')


sync_desktop_pools_view = SyncDesktopPoolsView.as_view()


class DesktopPoolDetailView(LoginRequiredMixin, DetailView):
    model = DesktopPool
    slug_field = 'pk'
    slug_url_kwarg = 'pk'
    template_name = 'vdi/desktop_pool.html'
    permission_required = ('labvirtual.view_desktoppool',)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        object = self.get_object()
        try:
            context['desktop_pool'] = object.get_desktop_pool_info()
            context['machines'] = object.get_machines()
            context['groups'] = object.get_ad_groups()
        except SSLError:
            context['error'] = 'Erro de SSL ao tentar conectar ao servidor VDI. Verifique as configurações do servidor.'
        except Exception as e:
            context['error'] = f'Não foi possível obter informações do pool. Detalhes: {e}'
        return context


desktop_pool_detail_view = DesktopPoolDetailView.as_view()


##################################################
# Solicitacao
##################################################
class SolicitacaoAgendamentoWizardView(PermissionRequiredMixin, SessionWizardView):
    title = 'Solicitar Agendamento'
    form_list = [SolicitacaoLabVirtualForm, SolicitacaoLabVirtualMembrosForm]
    permission_required = ('labvirtual.add_solicitacaolabvirtual',)
    template_name = 'labvirtual/solicitacao/form_wizard.html'
    query_string = True

    def load_lab(self):
        lab = self.kwargs.get('laboratorio', None)
        if lab is None:
            lab = DesktopPool.objects.filter(pk=self.kwargs['pk']).first()
            self.kwargs['laboratorio'] = lab
            return lab
        return lab

    def dispatch(self, request, *args, **kwargs):
        lab = self.load_lab()
        if lab is None or not lab.pode_solicitar(request.user):
            msg = f'O usuário {request.user} não possui permissão para realizar solicitações ao laboratório {lab}'
            return httprr('..', msg, tag='error')
        #
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, form, **kwargs):
        context = super().get_context_data(form, **kwargs)
        context['title'] = 'Solitação de Laboratório Remoto'
        return context

    def get_success_url(self) -> str:
        app_label = SolicitacaoLabVirtual._meta.app_label
        model_name = SolicitacaoLabVirtual._meta.model_name
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
        cleaned_data.pop('capacidade', None)
        return SolicitacaoLabVirtual.objects.create(**cleaned_data)

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


class SolicitacaoAgendamentoDetailView(LoginRequiredMixin, DetailView):
    model = SolicitacaoLabVirtual
    slug_field = 'pk'
    slug_url_kwarg = 'pk'
    template_name = 'labvirtual/solicitacao/solicitacao_agendamento.html'
    permission_required = ('labvirtual.view_solicitacaolabvirtual',)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        solicitacao = self.get_object()
        context['calendario'] = solicitacao.programacao()
        return context


solicitacao_agendamento_detail_view = SolicitacaoAgendamentoDetailView.as_view()


class DeferirSolicitacaoAgendamentoView(LoginRequiredMixin, View):
    permission_required = ('labvirtual.pode_avaliar_solicitacao_labvirtual',)

    def get(self, request, *args, **kwargs):
        object = get_object_or_404(SolicitacaoLabVirtual, pk=kwargs['pk'])
        url = reverse('labvirtual:solicitacao_agendamento', kwargs={'pk': self.kwargs['pk']})
        try:
            with transaction.atomic():
                object.deferir()
                object.save()
            return httprr(url, 'Solicitação deferida com sucesso.')
        except ValidationError as e:
            return httprr(url, f'Não foi possível realizar o indeferimento: {e.messages[0]}', 'error')


deferir_solicitacao_agendamento_view = DeferirSolicitacaoAgendamentoView.as_view()


class IndeferirSolicitacaoAgendamentoView(LoginRequiredMixin, UpdateView):
    model = SolicitacaoLabVirtual
    form_class = IndeferirSolicitacaoLabVirtualForm
    template_name = 'labvirtual/solicitacao/indeferir_solicitacao_agendamento.html'
    permission_required = ('labvirtual.pode_avaliar_solicitacao_labvirtual',)

    def form_valid(self, form):
        try:
            form.save()
            url = reverse('labvirtual:solicitacao_agendamento', kwargs={'pk': self.kwargs['pk']})
            return httprr(url, 'Indeferimento realizado com sucesso.')
        except ValidationError as e:
            url = reverse('labvirtual:solicitacao_agendamento', kwargs={'pk': self.kwargs['pk']})
            return httprr(url, f'Não foi possível realizar o indeferimento: {e.messages[0]}', 'error')

    def get_form_kwargs(self, *args, **kwargs):
        kwargs = super().get_form_kwargs(*args, **kwargs)
        kwargs['user'] = self.request.user
        return kwargs

    def get_success_url(self):
        return reverse('labvirtual:solicitacao_agendamento', kwargs={'pk': self.kwargs['pk']})


indeferir_solicitacao_agendamento_view = IndeferirSolicitacaoAgendamentoView.as_view()


class CancelarSolicitacaoAgendamentoView(LoginRequiredMixin, UpdateView):
    model = SolicitacaoLabVirtual
    form_class = CancelarSolicitacaoLabVirtualForm
    template_name = 'labvirtual/solicitacao/indeferir_solicitacao_agendamento.html'
    permission_required = ('labvirtual.pode_avaliar_solicitacao_labvirtual', 'labvirtual.change_solicitacaolabvirtual')

    def form_valid(self, form):
        form.instance.user = self.request.user
        try:
            form.save()
            url = reverse('labvirtual:solicitacao_agendamento', kwargs={'pk': self.kwargs['pk']})
            return httprr(url, 'Cancalmento realizado com sucesso.')
        except ValidationError as e:
            url = reverse('labvirtual:solicitacao_agendamento', kwargs={'pk': self.kwargs['pk']})
            return httprr(url, f'Não foi possível realizar o cancelamento: {e.messages[0]}', 'error')

    def get_form_kwargs(self, *args, **kwargs):
        kwargs = super().get_form_kwargs(*args, **kwargs)
        kwargs['user'] = self.request.user
        return kwargs

    def get_success_url(self):
        return reverse('labvirtual:solicitacao_agendamento', kwargs={'pk': self.kwargs['pk']})


cancelar_solicitacao_agendamento_view = CancelarSolicitacaoAgendamentoView.as_view()


class AgendamentoLabVirtualDetailView(LoginRequiredMixin, DetailView):
    model = AgendamentoLabVirtual
    slug_field = 'pk'
    slug_url_kwarg = 'pk'
    template_name = 'labvirtual/agendamento/agendamento_labvirtual.html'
    permission_required = ('labvirtual.view_agendamentolabvirtual',)


agendamento_labvirtual_detail_view = AgendamentoLabVirtualDetailView.as_view()


class DesktopPoolKillSessions(LoginRequiredMixin, View):
    permission_required = ('labvirtual.change_agendamentolabvirtual',)

    def get(self, request, *args, **kwargs):
        try:
            Desktop_pool = get_object_or_404(DesktopPool, pk=kwargs['pk'])
            return httprr('..', f'Sessões do {Desktop_pool} finalizadas com sucesso.')
        except ValidationError as e:
            return httprr('..', f'Não foi possível finalizar as sessões d0 {Desktop_pool}: {e.messages[0]}', 'error')


desktop_pool_kill_sessions_view = DesktopPoolKillSessions.as_view()


class AgendamentoSyncView(LoginRequiredMixin, View):
    permission_required = ('labvirtual.change_agendamentolabvirtual',)

    def get(self, request, *args, **kwargs):
        object = get_object_or_404(AgendamentoLabVirtual, pk=kwargs['pk'])
        url = '..'
        try:
            with transaction.atomic():
                object.ativar()
                object.save()
            return httprr(url, f'Laboratório {object.laboratorio} liberado.')
        except ValidationError as e:
            return httprr(url, f'Não foi possível liberar o laboratório {object.laboratorio}: {e.messages[0]}', 'error')


agendamento_sync_view = AgendamentoSyncView.as_view()


class AgendamentoShutdownView(LoginRequiredMixin, View):
    permission_required = ('labvirtual.change_agendamentolabvirtual',)

    def get(self, request, *args, **kwargs):
        object = get_object_or_404(AgendamentoLabVirtual, pk=kwargs['pk'])
        url = '..'
        try:
            with transaction.atomic():
                object.inativar()
                object.save()
            return httprr(url, f'Laboratório {object.laboratorio} fechado.')
        except ValidationError as e:
            return httprr(url, f'Não foi possível encerrar o laboratório {object.laboratorio}: {e.messages[0]}', 'error')


agendamento_shutdown_view = AgendamentoShutdownView.as_view()


class ProcurarUsuarioView(LoginRequiredMixin, FormView):
    template_name = 'labvirtual/procurar_form.html'
    form_class = SearchForm
    model = None
    fields = None
    allowed_methods = ['GET', 'POST']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['object'] = get_object_or_404(SolicitacaoLabVirtual, pk=self.kwargs['solicitacao_pk'])
        return context

    def form_valid(self, form):
        solicitacao = get_object_or_404(SolicitacaoLabVirtual, pk=self.kwargs['solicitacao_pk'])
        context = self.get_context_data(form=form, object=solicitacao)
        object = form.cleaned_data['membro']
        object.is_member = solicitacao.eh_membro(object)
        context['membro'] = object
        return self.render_to_response(context)


procurar_usuario_view = ProcurarUsuarioView.as_view()


class AdicionarMembroView(LoginRequiredMixin, View):
    permission_required = ('labvirtual.change_solicitacaolabvirtual',)

    #
    def get(self, request, *args, **kwargs):
        #
        vinculo = get_object_or_404(Vinculo, id=self.kwargs['membro_pk'])
        solicitacao = get_object_or_404(SolicitacaoLabVirtual, pk=self.kwargs['pk'])
        solicitacao.adicionar_membro(vinculo)
        return httprr(solicitacao.get_absolute_url(), f'Usuário {vinculo} adicionado com sucesso.')


adicionar_membro_view = AdicionarMembroView.as_view()


class RemoverMembroView(LoginRequiredMixin, View):
    permission_required = ('labvirtual.change_solicitacaolabvirtual',)

    #
    def get(self, request, *args, **kwargs):
        #
        vinculo = get_object_or_404(Vinculo, id=self.kwargs['membro_pk'])
        solicitacao = get_object_or_404(SolicitacaoLabVirtual, pk=self.kwargs['pk'])
        solicitacao.remover_membro(vinculo)
        return httprr(solicitacao.get_absolute_url(), f'Usuário {vinculo} adicionado com sucesso.')


remover_membro_view = RemoverMembroView.as_view()
