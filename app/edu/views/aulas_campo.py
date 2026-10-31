from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404

from djtools.utils import (
    group_required,
    httprr,
    permission_required,
    rtr,
)
from edu.forms import EnviarPlanilhaMensalSeguroAulaCampoForm, PesquisarAlunosForm
from edu.models import Aluno, AlunoAulaCampo, AulaCampo, ConfiguracaoSeguro


@login_required()
@group_required('Agendador de Aula de Campo EDU,Administrador Acadêmico,Secretário Acadêmico,Diretor Acadêmico')
@rtr()
def configuracaoseguro(request, pk):
    obj = get_object_or_404(ConfiguracaoSeguro, pk=pk)
    aulas_campo = AulaCampo.locals.filter(configuracao_seguro=obj).order_by('data_partida')
    title = 'Configuração de Seguro'

    usuario_is_administrador = request.user.has_group_cached('Administrador Acadêmico')
    eh_secretario = request.user.has_group_cached('Secretário Acadêmico')

    return locals()


@permission_required('edu.add_aulacampo')
@login_required()
@rtr()
def aulacampo(request, pk):
    obj = get_object_or_404(AulaCampo.locals, pk=pk)
    title = 'Visualização de Aula de Campo'
    usuario_is_administrador = request.user.has_group_cached('Administrador Acadêmico')

    if 'cancelar' in request.GET:
        obj.situacao = AulaCampo.SITUACAO_CANCELADA
        obj.save()
        return httprr('.', 'Aula de Campo cancelada com sucesso.')

    if 'realizada' in request.GET:
        obj.situacao = AulaCampo.SITUACAO_REALIZADA
        obj.save()
        return httprr('.', 'Aula de Campo atualizada com sucesso.')

    if 'alunos_selecionados' in request.POST:
        alunos_aulas = AlunoAulaCampo.objects.filter(aula_campo=obj, aluno__id__in=request.POST.getlist('alunos_selecionados'))

        for aluno_aluno in alunos_aulas:
            aluno_aluno.delete()

        return httprr(f'/edu/aulacampo/{obj.pk:d}/', 'Aluno(s) removido(s) com sucesso.')
    return locals()


@permission_required('edu.add_aulacampo')
@login_required()
@rtr()
def adicionar_alunos_aula_campo(request, pk):
    obj = get_object_or_404(AulaCampo.locals, pk=pk)
    title = 'Adicionar Alunos à Aula de Campo'
    usuario_is_administrador = request.user.has_group_cached('Administrador Acadêmico')
    if obj.situacao != obj.SITUACAO_AGENDADA and not usuario_is_administrador:
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')
    form = PesquisarAlunosForm(request.GET or None)

    if request.method == 'GET':
        if form.is_valid():
            alunos = form.processar()
            alunos = alunos.exclude(aulacampo=obj)

    if 'alunos_selecionados' in request.POST:
        alunos_selecionados = Aluno.objects.filter(id__in=request.POST.getlist('alunos_selecionados'))

        qtd_alunos_selecionados = alunos_selecionados.count()
        data_partida = obj.data_partida
        data_chegada = obj.data_chegada
        qtd_dias = (data_chegada - data_partida).days + 1
        gasto_previsto_aula = qtd_alunos_selecionados * qtd_dias * obj.configuracao_seguro.valor_repasse_pessoa

        # Verificando conflitos de datas para os alunos
        qs = obj.configuracao_seguro.aulacampo_set.filter(situacao=AulaCampo.SITUACAO_AGENDADA)
        qs = qs.exclude(data_chegada__lt=data_partida)
        qs = qs.exclude(data_partida__gt=data_chegada)

        if obj:
            qs = qs.exclude(pk=obj.pk)

        for aluno in alunos_selecionados:
            qs = qs.filter(alunos__matricula=aluno.matricula)

            if qs.exists():
                aulas_conflitos = qs.values_list('pk', flat=True).distinct()
                return httprr(
                    request.META.get('HTTP_REFERER', '.'),
                    f'Existe conflito de datas para o(a) aluno(a) {aluno} nas aulas de campo {aulas_conflitos}.',
                    'error',
                )

        if not obj.configuracao_seguro.possui_saldo_suficiente(gasto_previsto_aula):
            num_participantes_disponivel = obj.configuracao_seguro.get_participantes_disponiveis(qtd_dias)

            return httprr(
                request.META.get('HTTP_REFERER', '.'),
                f'Não existe saldo disponível para a quantidade de alunos selecionados. Você pode incluir até {num_participantes_disponivel:d} alunos.',
                'error',
            )
        else:
            for aluno in alunos_selecionados:
                aluno_aula = AlunoAulaCampo()
                aluno_aula.aluno = aluno
                aluno_aula.aula_campo = obj
                aluno_aula.save()

            return httprr(f'/edu/aulacampo/{obj.pk:d}/', 'Aluno(s) adicionado(s) com sucesso.')

    return locals()


@login_required()
@group_required('Administrador Acadêmico')
@rtr()
def enviar_planilha_mensal_aula_campo(request, pk):
    title = 'Enviar Planilha Mensal das Aulas de Campo à Seguradora'
    obj = get_object_or_404(ConfiguracaoSeguro, pk=pk)
    form = EnviarPlanilhaMensalSeguroAulaCampoForm(obj, data=request.POST or None)

    if form.is_valid():
        sucesso = form.processar()

        if sucesso:
            return httprr('..', 'Planilha enviada com sucesso.')
        else:
            return httprr('..', 'Atenção: Não foi possível enviar a Planilha pois não existem aulas de campos para o período selecionado.', 'error')
    return locals()
