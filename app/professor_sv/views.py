from djtools.utils import group_required, rtr
from django.core.exceptions import PermissionDenied
from django.db import transaction
from datetime import date

from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.urls import reverse

from djtools.utils import httprr, permission_required

from rh.models import UnidadeOrganizacional

from djtools import layout

from professor_sv.models import (
    Configuracao,
    Categoria,
    Perfil,
    Vaga,
    HistoricoMovimentacaoVaga,
    SolicitacaoEmprestimoVaga,
    Grupo,
    Contrato,
    ContratoPublicacaoDocumento,
    ContratoAditivoTempo,
)
from professor_sv.forms import (
    ConfiguracaoProfessorSvForm,
    VagaAddForm,
    EmprestarVagaForm,
    BuscarVagasForm,
    ContratoForm,
    ContratoPublicacaoDocumentoForm,
    ContratoAditivoForm,
    ContratoAditivo,
    ContratoAditivoTempoForm,
    ContratoFinalizarForm,
    ComSenhaIrreversivelForm,
)
from professor_sv.pendencias_alertas import get_pendencias


@layout.atribuidos_a_mim()
def index_atribuidos_a_mim(request):
    pendencias_lista = []

    if request.user.eh_servidor:
        pendencias = get_pendencias(request.user)
        if pendencias:
            for pendencia in pendencias:
                pendencias_lista.append(
                    {
                        'titulo': pendencia.get('msg'),
                        'subtitulo': pendencia.get('subtitulo'),
                        'qtd': pendencia.get('qtd'),
                        'url': pendencia.get('url'),
                    }
                )

    return pendencias_lista


@rtr()
@transaction.atomic
@group_required('Gestor Sistêmico')
def configuracao(request, cadastrar=None):
    instance = Configuracao.get_configuracao()

    title = 'Configurações'

    fields = Configuracao._meta.fields

    if cadastrar == 'cadastrar':
        if instance:
            title = 'Editar configurações'
        else:
            title = 'Cadastrar configurações'
        form = ConfiguracaoProfessorSvForm(request.POST or None, instance=instance)
        if form.is_valid():
            config = form.save(False)
            config.qtd_limite_professor_substituto_visitante = config.qtd_limite_professor_substituto + config.qtd_limite_professor_visitante
            config.save()
            form.save_m2m()
            url = reverse('configuracao')
            return httprr(url, 'Dados cadastrados com sucesso.')

    return locals()


@rtr()
@permission_required('professor_sv.add_grupo')
def seleciona_campus(request):
    title = 'Adicionar Grupo - Selecione um Campus'

    uos = UnidadeOrganizacional.objects.suap().exclude(id__in=Grupo.objects.values('uo_id')).order_by('sigla')

    return locals()


@rtr()
@permission_required('professor_sv.add_vaga')
def seleciona_categoria(request):
    if not Vaga.pode_cadastrar():
        raise PermissionDenied('As configurações, categorias e grupos devem ter sido cadastrados')

    title = 'Distribuir Vagas - Selecione uma Categoria'

    categorias = Categoria.objects.all().order_by('titulo')

    return locals()


@rtr()
@transaction.atomic
@permission_required('professor_sv.add_vaga')
def cadastrar_vaga(request, categoria_id):
    categoria = get_object_or_404(Categoria, id=categoria_id)
    if not Vaga.pode_cadastrar():
        raise PermissionDenied('As configurações, categorias e grupos devem ter sido cadastrados')

    title = f'Distribuir Vagas - {categoria}'

    url = reverse('admin:professor_sv_vaga_changelist')

    form = VagaAddForm(request.POST or None, categoria=categoria)
    if form.is_valid():
        quantidade_substituto = form.cleaned_data.get('quantidade_substituto')
        quantidade_visitante = form.cleaned_data.get('quantidade_visitante')

        if categoria.permite_substituto() and quantidade_substituto:
            Vaga.gerar_vagas(
                user=request.user,
                perfil=Perfil.SUBSTITUTO,
                categoria=categoria,
                grupo_dono=form.cleaned_data.get('grupo_dono'),
                quantidade=form.cleaned_data.get('quantidade_substituto'),
            )
        if categoria.permite_visitante() and quantidade_visitante:
            Vaga.gerar_vagas(
                user=request.user,
                perfil=Perfil.VISITANTE,
                categoria=categoria,
                grupo_dono=form.cleaned_data.get('grupo_dono'),
                quantidade=form.cleaned_data.get('quantidade_visitante'),
            )

        return httprr(url, 'Dados cadastrados com sucesso.')

    return locals()


@rtr()
@permission_required('rh.eh_servidor')
def gerenciar_vaga(request, vaga_id):
    vaga = get_object_or_404(Vaga, id=vaga_id)
    vaga.atualizar_historico_movimentacao_vaga()

    title = f'Gerenciar Vaga - {vaga}'

    historico_dono_vaga = HistoricoMovimentacaoVaga.objects.filter(vaga=vaga).order_by('-id')
    solicitacoes_emprestimo = SolicitacaoEmprestimoVaga.objects.filter(vaga=vaga).order_by('-id')
    contratos = vaga.get_contratos()

    pode_emprestar_vaga = vaga.pode_emprestar_vaga(request.user)
    pode_desfazer_emprestimo_vaga = vaga.pode_desfazer_emprestimo_vaga(request.user)
    pode_devolver_emprestimo_vaga = vaga.pode_devolver_emprestimo_vaga(request.user)

    pode_desativar_vaga = vaga.pode_desativar_vaga(request.user)
    pode_ativar_vaga = vaga.pode_ativar_vaga(request.user)
    pode_excluir_vaga = vaga.pode_excluir_vaga(request.user)

    pode_iniciar_cadastro_contrato = Contrato.pode_iniciar_cadastro_contrato(vaga=vaga, user=request.user)
    eh_vaga_apta_para_cadastrar_contrato = vaga.eh_vaga_apta_para_cadastrar_contrato()[0]

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def emprestar_vaga(request, vaga_id):
    vaga = get_object_or_404(Vaga, pk=vaga_id)
    pode, msg = vaga.pode_emprestar_vaga(request.user)
    if not pode:
        raise PermissionDenied(msg)

    vaga.atualizar_historico_movimentacao_vaga()

    title = f'Emprestar vaga - {vaga}'
    url = f'{reverse("gerenciar_vaga", args=[vaga_id])}'

    form = EmprestarVagaForm(request.POST or None, user=request.user, vaga=vaga)
    if form.is_valid():
        vaga.emprestar_vaga(
            user=request.user,
            vaga=vaga,
            tomador=form.cleaned_data.get('tomador'),
            justificativa=form.cleaned_data.get('justificativa'),
            emprestimo_ate=form.cleaned_data.get('emprestimo_ate'),
            processo=form.cleaned_data.get('processo'),
        )

        return httprr(url, 'Dados cadastrados com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def desfazer_emprestimo_vaga(request, vaga_id):
    vaga = get_object_or_404(Vaga, pk=vaga_id)
    pode, msg = vaga.pode_desfazer_emprestimo_vaga(request.user)
    if not pode:
        raise PermissionDenied(msg)

    url = f'{reverse("gerenciar_vaga", args=[vaga_id])}'

    vaga.desfazer_emprestimo_vaga(request.user)

    return httprr(url, 'Empréstimo desfeito com sucesso.')


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def devolver_emprestimo_vaga(request, vaga_id):
    vaga = get_object_or_404(Vaga, pk=vaga_id)
    pode, msg = vaga.pode_devolver_emprestimo_vaga(request.user)
    if not pode:
        raise PermissionDenied(msg)

    url = f'{reverse("gerenciar_vaga", args=[vaga_id])}'

    vaga.devolver_emprestimo_vaga(request.user)

    return httprr(url, 'Empréstimo devolvido com sucesso.')


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def ativar_vaga(request, vaga_id):
    vaga = get_object_or_404(Vaga, pk=vaga_id)
    pode, msg = vaga.pode_ativar_vaga(request.user)
    if not pode:
        raise PermissionDenied(msg)

    url = f'{reverse("gerenciar_vaga", args=[vaga_id])}'

    vaga.ativar_desativar_vaga()

    return httprr(url, 'Vaga ativada com sucesso.')


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def desativar_vaga(request, vaga_id):
    vaga = get_object_or_404(Vaga, pk=vaga_id)
    pode, msg = vaga.pode_desativar_vaga(request.user)
    if not pode:
        raise PermissionDenied(msg)

    url = f'{reverse("gerenciar_vaga", args=[vaga_id])}'

    vaga.ativar_desativar_vaga()

    return httprr(url, 'Vaga desativada com sucesso.')


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def cancelar_solicitacao_emprestimo(request, sol_emp_id):
    sol_emp = get_object_or_404(SolicitacaoEmprestimoVaga, pk=sol_emp_id)
    if not sol_emp.pode_cancelar_solicitacao(request.user):
        raise PermissionDenied

    url = f'{reverse("gerenciar_vaga", args=[sol_emp.vaga.id])}'

    sol_emp.cancelada = True
    sol_emp.save()

    return httprr(url, 'Empréstimo cancelado com sucesso.')


@rtr()
@transaction.atomic
@permission_required('rh.chefe')
def aprovar_solicitacao_emprestimo(request):
    title = 'Avaliar Empréstimo de Vaga'

    solicitacoes = SolicitacaoEmprestimoVaga.get_solicitacoes_emprestimo_aprovacao_pendente(request.user.get_relacionamento())
    url = f'{reverse("aprovar_solicitacao_emprestimo")}'

    analisar_solicitacao = request.GET.get('s', None)
    parecer = request.GET.get('p', None)
    if analisar_solicitacao and parecer:
        realizada = False
        solicitacao = get_object_or_404(SolicitacaoEmprestimoVaga, id=analisar_solicitacao)
        if parecer == '1':
            realizada = solicitacao.deferir(request.user)
        elif parecer == '2':
            realizada = solicitacao.indeferir(request.user)
        if realizada:
            return httprr(url, 'Deferimento/Indeferimento realizado com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('professor_sv.add_vaga')
def remover_vaga(request, vaga_id):
    vaga = get_object_or_404(Vaga, id=vaga_id)
    if not vaga.pode_excluir_vaga(request.user):
        raise PermissionDenied

    vaga.delete()
    url = reverse('admin:professor_sv_vaga_changelist')

    return httprr(url, 'Vaga removida com sucesso.')


@rtr()
@permission_required('rh.eh_servidor')
def seleciona_vaga_para_contrato(request):
    if not Contrato.user_pode_cadastrar_contrato(user=request.user):
        raise PermissionDenied

    vagas_aptas = Vaga.get_vagas_aptas_para_novo_contrato().order_by('codigo')
    grupos_pode_cadastrar = Grupo.get_grupos_user_pode_cadastrar_contrato(user=request.user)
    vagas_aptas = vagas_aptas.filter(grupo_dono__in=grupos_pode_cadastrar)

    title = 'Cadastrar Contrato - Selecione uma Vaga'

    if vagas_aptas:
        form = BuscarVagasForm(request.GET or None, request=request, grupos_pode_cadastrar=grupos_pode_cadastrar)
        if form.is_valid():
            grupo = form.cleaned_data.get('grupo')
            tipo = form.cleaned_data.get('tipo')
            if tipo == '2':
                vagas_aptas = vagas_aptas.filter(grupo_dono=grupo)
            elif tipo == '3':
                vagas_aptas = vagas_aptas.filter(grupo_tomador=grupo)
            else:
                vagas_aptas = vagas_aptas.filter(Q(grupo_dono=grupo) | Q(grupo_tomador=grupo))

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def cadastrar_contrato(request, vaga_id):
    vaga = get_object_or_404(Vaga, id=vaga_id)

    title = f'Cadastrar Contrato - Vaga {vaga}'

    pode, msg_erro = Contrato.pode_iniciar_cadastro_contrato(vaga=vaga, user=request.user)
    if pode:
        url = reverse('admin:professor_sv_contrato_changelist')

        form = ContratoForm(request.POST or None, vaga=vaga)
        if form.is_valid():
            contrato = form.save(False)
            contrato.vaga = vaga
            contrato.data_expira = contrato.data_fim
            contrato.save()
            return httprr(url, 'Dados cadastrados com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def editar_contrato(request, contrato_id):
    contrato = get_object_or_404(Contrato, id=contrato_id)
    pode, msg = contrato.pode_editar(user=request.user)
    if not pode:
        raise PermissionDenied(msg)

    title = f'Editar Contrato - {contrato}'

    url = reverse('admin:professor_sv_contrato_changelist')

    form = ContratoForm(request.POST or None, instance=contrato)
    if form.is_valid():
        contrato = form.save(False)
        contrato.vaga = contrato.vaga
        contrato.data_expira = contrato.data_fim
        contrato.save()
        return httprr(url, 'Dados cadastrados com sucesso.')

    return locals()


@rtr()
@permission_required('rh.eh_servidor')
def gerenciar_contrato(request, contrato_id):
    contrato = get_object_or_404(Contrato, id=contrato_id)

    title = f'Gerenciar Contrato - {contrato}'

    vaga = contrato.vaga

    pode_editar = contrato.pode_editar(user=request.user)
    msg_motivo_nao_pode_editar = None
    if contrato.pode_gerenciar_contrato(user=request.user)[0]:
        msg_motivo_nao_pode_editar = pode_editar[1]

    pode_adicionar_publicacao_documento = contrato.pode_adicionar_publicacao_documento(user=request.user)
    pode_remover_publicacao_documento = contrato.pode_remover_publicacao_documento(user=request.user)

    pode_adicionar_aditivo = contrato.pode_adicionar_aditivo(user=request.user)
    pode_remover_aditivo = contrato.pode_remover_aditivo(user=request.user)

    pode_adicionar_aditivo_tempo = contrato.pode_adicionar_aditivo_tempo(user=request.user)
    pode_remover_aditivo_tempo = contrato.pode_remover_aditivo_tempo(user=request.user)

    pode_finalizar = contrato.pode_finalizar(user=request.user)
    pode_remover_finalizacao = contrato.pode_remover_finalizacao(user=request.user)

    pode_cancelar = contrato.pode_cancelar(user=request.user)

    aditivos_tempo = contrato.contratoaditivotempo_set.all().order_by('-data_inicio')
    aditivos = contrato.contratoaditivo_set.all().order_by('-id')
    publicacoes = contrato.contratopublicacaodocumento_set.all().order_by('-id')

    estah_afastado_ou_de_ferias = None
    if contrato.servidor_docente_titular:
        estah_afastado_ou_de_ferias = contrato.servidor_docente_titular.estah_afastado_ou_de_ferias_ateh(date.today())

    estah_com_uo_diferente_entre_docente_e_vaga = contrato.estah_com_uo_diferente_entre_docente_e_vaga()

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def cadastrar_publicacao_contrato(request, contrato_id):
    contrato = get_object_or_404(Contrato, id=contrato_id)
    pode, msg = contrato.pode_adicionar_publicacao_documento(user=request.user)
    if not pode:
        raise PermissionDenied(msg)

    title = f'Adicionar Documento ao Contrato - {contrato}'

    url = f'{reverse("gerenciar_contrato", args=[contrato_id])}'

    form = ContratoPublicacaoDocumentoForm(request.POST or None)
    if form.is_valid():
        form.instance.contrato = contrato
        form.save()
        return httprr(url, 'Dados cadastrados com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def remover_publicacao_contrato(request, contrato_publicacao_id):
    publicacao = get_object_or_404(ContratoPublicacaoDocumento, id=contrato_publicacao_id)
    pode, msg = publicacao.contrato.pode_remover_publicacao_documento(user=request.user)
    if not pode:
        raise PermissionDenied(msg)

    url = f'{reverse("gerenciar_contrato", args=[publicacao.contrato.id])}'

    publicacao.delete()

    return httprr(url, 'Documento removido com sucesso.')


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def cadastrar_aditivo_contrato(request, contrato_id):
    contrato = get_object_or_404(Contrato, id=contrato_id)
    pode, msg = contrato.pode_adicionar_aditivo(user=request.user)
    if not pode:
        raise PermissionDenied(msg)

    title = f'Adicionar Aditivo ao Contrato - {contrato}'

    url = f'{reverse("gerenciar_contrato", args=[contrato_id])}'

    form = ContratoAditivoForm(request.POST or None)
    if form.is_valid():
        form.instance.contrato = contrato
        form.save()
        return httprr(url, 'Dados cadastrados com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def remover_aditivo_contrato(request, contrato_aditivo_id):
    aditivo = get_object_or_404(ContratoAditivo, id=contrato_aditivo_id)
    pode, msg = aditivo.contrato.pode_remover_aditivo(user=request.user)
    if not pode:
        raise PermissionDenied(msg)

    url = f'{reverse("gerenciar_contrato", args=[aditivo.contrato.id])}'

    aditivo.delete()

    return httprr(url, 'Aditivo removido com sucesso.')


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def cadastrar_aditivo_tempo_contrato(request, contrato_id):
    contrato = get_object_or_404(Contrato, id=contrato_id)
    pode, msg = contrato.pode_adicionar_aditivo_tempo(user=request.user)
    if not pode:
        raise PermissionDenied(msg)

    title = f'Adicionar Aditivo de Tempo ao Contrato - {contrato}'

    url = f'{reverse("gerenciar_contrato", args=[contrato_id])}'

    form = ContratoAditivoTempoForm(request.POST or None, contrato=contrato)
    if form.is_valid():
        form.instance.contrato = contrato
        aditivo_tempo = form.save()

        # Data expira do contrato fica sendo de acordo com esse aditivo
        contrato.data_expira = aditivo_tempo.data_fim
        contrato.save()

        return httprr(url, 'Dados cadastrados com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def remover_aditivo_tempo_contrato(request, contrato_aditivo_tempo_id):
    aditivo = get_object_or_404(ContratoAditivoTempo, id=contrato_aditivo_tempo_id)
    pode, msg = aditivo.contrato.pode_remover_aditivo(user=request.user)
    if not pode:
        raise PermissionDenied(msg)

    contrato = aditivo.contrato

    url = f'{reverse("gerenciar_contrato", args=[contrato.id])}'

    aditivo.delete()

    # Atualiza data expira do contrato de acordo com a data fim do aditivo de tempo com data fim mais distante
    # Se não houver aditivos de tempo a data expira do contrato fica sendo a data fim original
    aditivo_tempo_mais_longo = contrato.get_aditivo_tempo_mais_longo()
    if aditivo_tempo_mais_longo:
        contrato.data_expira = aditivo_tempo_mais_longo.data_fim
    else:
        contrato.data_expira = contrato.data_fim
    contrato.save()

    return httprr(url, 'Aditivo removido com sucesso.')


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def finalizar_contrato(request, contrato_id):
    contrato = get_object_or_404(Contrato, id=contrato_id)
    pode, msg = contrato.pode_finalizar(user=request.user)
    if not pode:
        raise PermissionDenied(msg)

    url = f'{reverse("gerenciar_contrato", args=[contrato.id])}'

    title = f'Encerrar Contrato - {contrato}'

    form = ContratoFinalizarForm(request.POST or None, contrato=contrato)
    if form.is_valid():
        contrato.concluido = True
        contrato.data_conclusao = form.cleaned_data.get('data_conclusao')
        contrato.justificativa_conclusao = form.cleaned_data.get('justificativa')
        contrato.save()
        return httprr(url, 'Encerrado com sucesso.')

    return locals()


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def remover_finalizacao_contrato(request, contrato_id):
    contrato = get_object_or_404(Contrato, id=contrato_id)
    pode, msg = contrato.pode_remover_finalizacao(user=request.user)
    if not pode:
        raise PermissionDenied(msg)

    url = f'{reverse("gerenciar_contrato", args=[contrato.id])}'

    contrato.concluido = False
    contrato.data_conclusao = None
    contrato.justificativa_conclusao = None
    contrato.save()

    return httprr(url, 'Conclusão cancelada com sucesso.')


@rtr()
@transaction.atomic
@permission_required('rh.eh_servidor')
def cancelar_contrato(request, contrato_id):
    contrato = get_object_or_404(Contrato, id=contrato_id)
    pode, msg = contrato.pode_cancelar(user=request.user)
    if not pode:
        raise PermissionDenied(msg)

    url = f'{reverse("gerenciar_contrato", args=[contrato.id])}'
    title = f'Cancelar Contrato - {contrato}'

    form = ComSenhaIrreversivelForm(request.POST or None)
    if form.is_valid():
        contrato.cancelado = True
        contrato.save()
        return httprr(url, 'Cancelamento realizado com sucesso.')

    return locals()


@rtr()
@permission_required('rh.eh_servidor')
def quadro_vagas(request):
    Vaga.atualizar_historico_movimentacao_vagas()

    title = 'Quadro de Vagas'

    grupos = Grupo.objects.all().order_by('uo__sigla')
    categorias = Categoria.objects.all().order_by('titulo')

    vagas_ocupadas = Vaga.get_vagas_ocupadas()
    vagas_desocupadas = Vaga.get_vagas_desocupadas()

    lista_quadro = []
    for grupo in grupos:
        dados = {}
        dados['grupo'] = grupo.titulo

        vagas_por_categoria = []
        for c in categorias:
            vagas_por_categoria.append(
                {
                    'total': grupo.get_vagas_por_categoria(categoria_id=c.id).count(),
                    'ocupadas': grupo.get_vagas_ocupadas_por_categoria(categoria_id=c.id, vagas_ocupadas=vagas_ocupadas).count(),
                    'desocupadas': grupo.get_vagas_desocupadas_por_categoria(categoria_id=c.id, vagas_desocupadas=vagas_desocupadas).count(),
                }
            )

        dados['vagas_por_categoria'] = vagas_por_categoria

        dados['total_geral'] = grupo.get_vagas_por_categoria().count()
        dados['ocupadas_geral'] = grupo.get_vagas_ocupadas_por_categoria(vagas_ocupadas=vagas_ocupadas).count()
        dados['desocupadas_geral'] = grupo.get_vagas_desocupadas_por_categoria(vagas_desocupadas=vagas_desocupadas).count()

        lista_quadro.append(dados)

    return locals()


@rtr()
@permission_required('rh.eh_servidor')
def quadro_limites(request):
    Vaga.atualizar_historico_movimentacao_vagas()

    title = 'Quadro de Limites de Vagas'

    limites = Configuracao.get_configuracao()
    vagas_ocupadas = Vaga.get_vagas_ocupadas()

    qtd_vagas_ocupadas_substituto = vagas_ocupadas.filter(perfil=Perfil.SUBSTITUTO).count()
    qtd_vagas_ocupadas_visitante = vagas_ocupadas.filter(perfil=Perfil.VISITANTE).count()
    qtd_vagas_ocupadas_substituto_visitante = qtd_vagas_ocupadas_substituto + qtd_vagas_ocupadas_visitante

    perc_vagas_ocupadas_substituto_visitante = 0
    if qtd_vagas_ocupadas_substituto_visitante > 0:
        perc_vagas_ocupadas_substituto_visitante = (
            qtd_vagas_ocupadas_substituto_visitante / Configuracao.get_configuracao().qtd_docentes_efetivo_exercicio
        ) * 100

    return locals()
