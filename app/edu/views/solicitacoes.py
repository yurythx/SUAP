from django.apps import apps
from django.conf import settings
from django.shortcuts import get_object_or_404

from djtools.utils import (
    httprr,
    permission_required,
    rtr,
)
from edu.forms import AtenderSolicitacaoProrrogacaoEtapaForm, RejeitarSolicitacaoUsuarioForm
from edu.models import Aluno, SolicitacaoProrrogacaoEtapa, SolicitacaoRelancamentoEtapa, SolicitacaoUsuario
from etep import perms as etep_perms


@rtr()
def rejeitar_solicitacao(request, pks):
    title = 'Rejeitar Solicitação'
    solicitacoes = SolicitacaoUsuario.objects.filter(pk__in=pks.split('_'))
    for solicitacao in solicitacoes:
        filho_verbose_name = solicitacao.sub_instance_title()
        filho = solicitacao.sub_instance()
        solicitacao = get_object_or_404(filho.__class__.locals, pk=solicitacao.pk)

        eh_acompanhamento_etep = filho_verbose_name == 'Solicitação de Acompanhamento ETEP'
        tem_permissao_realizar_procedimentos_etep = False
        if eh_acompanhamento_etep:
            if not etep_perms.tem_permissao_realizar_procedimentos_etep(request, filho.aluno):
                return httprr('..', f'Você não tem permissão para realizar isso com a solicitação #{solicitacao.pk}.', 'error')
        else:
            if not request.user.has_perm('edu.view_solicitacaorelancamentoetapa'):
                return httprr('..', f'Você não tem permissão para realizar isso com a solicitação #{solicitacao.pk}.', 'error')

    form = RejeitarSolicitacaoUsuarioForm(data=request.POST or None)

    if form.is_valid():
        for solicitacao in solicitacoes:
            solicitacao.rejeitar(request.user, request.POST['razao_indeferimento'])
        return httprr('..', 'Solicitações indeferidas com sucesso.')

    return locals()


@rtr()
@permission_required('edu.change_solicitacaoprorrogacaoetapa')
def atender_prorrogacao_etapa(request, pks):
    title = 'Atender Solicitação'
    form = AtenderSolicitacaoProrrogacaoEtapaForm(data=request.POST or None)
    if form.is_valid():
        solicitacoes = SolicitacaoProrrogacaoEtapa.objects.filter(pk__in=pks.split('_'))
        for solicitacao in solicitacoes:
            solicitacao.atender(request.user, nova_data=form.cleaned_data['data_prorrogacao'])
        return httprr('..', 'Solicitações deferidas com sucesso.')
    return locals()


@rtr()
@permission_required('edu.change_solicitacaoprorrogacaoetapa')
def atender_relancamento_etapa_prorrogando_posse(request, pks):
    title = 'Atender Solicitação'
    form = AtenderSolicitacaoProrrogacaoEtapaForm(data=request.POST or None)
    if form.is_valid():
        solicitacoes = SolicitacaoRelancamentoEtapa.objects.filter(pk__in=pks.split('_'))
        for solicitacao in solicitacoes:
            solicitacao.atender(request.user, nova_data=form.cleaned_data['data_prorrogacao'])
        return httprr('..', 'Solicitações deferidas com sucesso.')
    return locals()


@rtr()
@permission_required('edu.view_solicitacaousuario')
def solicitacaousuario(request, pk):
    obj = get_object_or_404(SolicitacaoUsuario.locals, pk=pk)

    filho_verbose_name = obj.sub_instance_title()
    filho = obj.sub_instance()
    title = f'{filho_verbose_name} {pk}'

    obj = get_object_or_404(filho.__class__.locals, pk=pk)

    eh_acompanhamento_etep = filho_verbose_name == 'Solicitação de Acompanhamento ETEP'
    eh_atividade_complementar = filho_verbose_name == 'Solicitação de Atividade Complementar'
    eh_prorrogacao_etapa = filho_verbose_name == 'Solicitação de Prorrogação de Etapa'
    eh_relacamento_e_precisa_prorrogar_posse = filho_verbose_name == 'Solicitação de Relançamento de Etapa' and filho.precisa_prorrogar_posse()

    pode_ver_etep = False
    pode_realizar_procedimento_etep = False
    if eh_acompanhamento_etep:
        pode_ver_etep = request.user.has_group_cached('Professor, Pedagogo, Administrador Acadêmico')
        setor = obj.aluno.curso_campus.diretoria.setor
        tem_permissao_realizar_procedimentos_etep = etep_perms.tem_permissao_realizar_procedimentos_etep(request, setor)
        if 'etep' in settings.INSTALLED_APPS:
            Acompanhamento = apps.get_model('etep', 'Acompanhamento')
            acompanhamento = Acompanhamento.objects.filter(aluno=obj.aluno)
        else:
            acompanhamento = []
    if not request.user.has_perm('edu.view_solicitacaorelancamentoetapa') and not pode_ver_etep:
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    aluno = Aluno.objects.filter(vinculos__user=obj.solicitante)
    if aluno:
        aluno = aluno[0]
    atender = request.GET.get('atender', False)
    if request.user.has_perm('edu.change_solicitacaousuario'):
        if 'avisar_coordenador' in request.GET and eh_atividade_complementar:
            if filho.enviar_email_coordenador():
                filho.atender(request.user)
                return httprr('..', 'Email enviado com sucesso.')
            else:
                return httprr('..', 'Falha ao tentar enviar email.')
        if atender:
            filho.atender(request.user)
            return httprr('..', 'Solicitação deferida com sucesso.')
    return locals()
