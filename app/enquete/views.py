from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Exists, OuterRef
from django.shortcuts import get_object_or_404

from comum.models import Vinculo
from djtools import layout
from djtools.utils import httprr, rtr
from enquete import tasks
from enquete.forms import BuscarPublicoForm, FiltrarRespostasForm, OpcaoForm, OpcaoPerguntaForm, PerguntaForm, ResponderEnqueteFormFactory
from enquete.models import Categoria, Enquete, Opcao, Pergunta, Resposta


@layout.quadro('Enquetes', icone='info-circle', pode_esconder=False, session_cache=8 * 3600)
def index_quadros_enquetes(quadro, request):
    for enquete_aberta in Enquete.get_abertas(request.user.get_vinculo()):
        if enquete_aberta.manter_enquete_inicio or not enquete_aberta.respondeu_todas_as_perguntas(request.user.get_vinculo()):
            quadro.add_item(
                layout.ItemNoticia(
                    url=f'/enquete/responder_enquete/{enquete_aberta.id}/',
                    titulo=f'{enquete_aberta.tag}: <strong>{enquete_aberta.titulo}</strong>.',
                    chapeu=f'Até {enquete_aberta.data_fim.strftime("%d/%m/%Y às %H:%M")}',
                )
            )

    return quadro


@rtr()
@login_required()
def enquete(request, id):
    enquete = get_object_or_404(Enquete, pk=id)
    title = f'Enquete: {enquete.titulo}'
    if not enquete.eh_responsavel(request.user):
        raise PermissionDenied
    if 'clonar' in request.GET:
        clone = enquete.clonar()
        return httprr(f'/enquete/enquete/{clone.id}/', 'Enquete clonada com sucesso.')
    hoje = datetime.now()
    categorias = enquete.get_perguntas_agrupadas_por_categoria()
    return locals()


@rtr()
@login_required()
def adicionar_opcao(request, enquete_id, pergunta_id=None):
    title = 'Adicionar Opção de Resposta'
    enquete = get_object_or_404(Enquete, pk=enquete_id)

    if not enquete.eh_responsavel(request.user):
        raise PermissionDenied

    if pergunta_id and enquete.eh_responsavel(request.user):
        pergunta = get_object_or_404(Pergunta, pk=pergunta_id)
        if not pergunta.objetiva:
            raise PermissionDenied
        form = OpcaoPerguntaForm(request.POST or None, request.FILES or None, enquete=enquete, pergunta=pergunta)
    elif enquete.eh_responsavel(request.user):
        form = OpcaoForm(request.POST or None, request.FILES or None, enquete=enquete)

    if request.method == 'POST':
        if form.is_valid():
            obj = form.save()
            return httprr(f'/enquete/enquete/{enquete.id}/', 'Opção adicionada com sucesso.')
    return locals()


@rtr()
@login_required()
def editar_opcao(request, id):
    title = 'Editar Opção'
    opcao = get_object_or_404(Opcao, pk=id)
    if not opcao.enquete.eh_responsavel(request.user):
        raise PermissionDenied

    form = OpcaoForm(request.POST or None, request.FILES or None, instance=opcao)
    if request.method == 'POST':
        if form.is_valid():
            obj = form.save()
            return httprr(f'/enquete/enquete/{opcao.enquete_id:d}/', 'Opção atualizada com sucesso.')
    return locals()


@rtr()
@login_required()
def remover_opcao(request, id):
    opcao = get_object_or_404(Opcao, pk=id)
    if not opcao.enquete.eh_responsavel(request.user):
        raise PermissionDenied

    opcao.delete()
    return httprr(f'/enquete/enquete/{opcao.enquete_id:d}/', 'Opção removida com sucesso.')


@rtr()
@login_required()
def adicionar_pergunta(request, enquete_id, categoria_id):
    title = 'Adicionar Pergunta'
    enquete = get_object_or_404(Enquete, pk=enquete_id)
    if not enquete.eh_responsavel(request.user):
        raise PermissionDenied

    categoria = get_object_or_404(Categoria, pk=categoria_id)
    form = PerguntaForm(request.POST or None, enquete=enquete, categoria=categoria)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            return httprr('..', 'Pergunta adicionada com sucesso.')

    return locals()


@rtr()
@login_required()
def editar_pergunta(request, id):
    title = 'Editar Pergunta'
    pergunta = get_object_or_404(Pergunta, pk=id)
    if not pergunta.enquete.eh_responsavel(request.user):
        raise PermissionDenied

    form = PerguntaForm(request.POST or None, instance=pergunta)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            return httprr('..', 'Pergunta atualizada com sucesso.')

    return locals()


@rtr()
@login_required()
def remover_pergunta(request, id):
    pergunta = get_object_or_404(Pergunta, pk=id)
    if not pergunta.enquete.eh_responsavel(request.user):
        raise PermissionDenied

    pergunta.delete()
    return httprr(f'/enquete/enquete/{pergunta.enquete_id:d}/', 'Pergunta removida com sucesso.')


@rtr()
@login_required
def ver_respostas(request, id):
    return responder_enquete(request, id, read_only=True)


@rtr()
@login_required
def ver_respostas_responsavel(request, id, vinculo_id):
    enquete = get_object_or_404(Enquete, pk=id)
    if not enquete.eh_responsavel(request.user):
        raise PermissionDenied
    vinculo = get_object_or_404(Vinculo, pk=vinculo_id)
    return responder_enquete(request, id, read_only=True, vinculo=vinculo)


@rtr()
@login_required
def responder_enquete(request, id, read_only=False, vinculo=None):
    enquete = get_object_or_404(Enquete, pk=id)
    title = enquete.titulo
    if not vinculo:
        vinculo = request.user.get_vinculo()
    if not enquete.pode_responder(vinculo) and not read_only:
        raise PermissionDenied

    Form = ResponderEnqueteFormFactory(request, enquete)
    form = Form(request.POST or None)
    if form.is_valid():
        form.save()
        messages.info(request, 'Enquete respondida com sucesso.')

    """
        enquete_dados = [
            categoria_dados = {
                nome: "Nome da categoria",
                grupos_perguntas: [ #Perguntas agrupadas em discursivas e objetivas de mesma opção
                    grupo_perguntas = {
                        objetiva: True ou False # se o grupo é de perguntas objetivas ou discursivas
                        perguntas: [] #lista de perguntas do grupo
                    }
                ]
            }
        ]
    """
    enquete_dados = []
    for categoria in enquete.get_perguntas_agrupadas_por_categoria():
        categoria_dados = {}
        categoria_dados['nome'] = categoria.texto
        categoria_dados['orientacao'] = categoria.orientacao
        grupos_perguntas = []
        opcoes_anteriores = None
        grupo_perguntas = {}
        grupo_perguntas['perguntas'] = []
        grupo_perguntas['objetiva'] = None
        for pergunta in categoria.perguntas.all():
            opcoes = pergunta.get_opcoes()
            if not opcoes_anteriores:
                opcoes_anteriores = opcoes

            if grupo_perguntas['objetiva'] != pergunta.objetiva or opcoes.exclude(id__in=opcoes_anteriores):
                if grupo_perguntas['perguntas']:
                    grupos_perguntas.append(grupo_perguntas)

                grupo_perguntas = {}
                grupo_perguntas['perguntas'] = []
                grupo_perguntas['objetiva'] = pergunta.objetiva

            pergunta.resposta = pergunta.get_resposta(vinculo)
            if not pergunta.resposta:
                pergunta.resposta = request.POST.get(f'{pergunta.id}') or ''
                if pergunta.objetiva and pergunta.resposta:
                    if pergunta.multipla_escolha:
                        pergunta.resposta = [int(resp) for resp in request.POST.getlist(f'{pergunta.id}')]
                    else:
                        pergunta.resposta = int(pergunta.resposta)

            grupo_perguntas['perguntas'].append(pergunta)
            opcoes_anteriores = opcoes

        grupos_perguntas.append(grupo_perguntas)
        categoria_dados['grupos_perguntas'] = grupos_perguntas
        enquete_dados.append(categoria_dados)

    return locals()


@rtr()
@login_required()
def publicar_enquete(request, id):
    enquete = get_object_or_404(Enquete, pk=id)
    if not enquete.eh_responsavel(request.user) or not enquete.pode_publicar():
        raise PermissionDenied

    enquete.publicada = True
    enquete.save()
    return httprr(f'/enquete/enquete/{enquete.id:d}/', 'Enquete publicada com sucesso.')


@rtr()
@login_required()
def despublicar_enquete(request, id):
    enquete = get_object_or_404(Enquete, pk=id)
    if not enquete.eh_responsavel(request.user):
        raise PermissionDenied

    enquete.publicada = False
    enquete.save()
    return httprr(f'/enquete/enquete/{enquete.id:d}/', 'Enquete despublicada com sucesso.')


@rtr()
@login_required()
def ver_resultados(request, id):
    enquete = get_object_or_404(Enquete, pk=id)
    title = f'Resultados da Enquete: {enquete.titulo}'
    if not enquete.eh_responsavel(request.user):
        raise PermissionDenied

    form = FiltrarRespostasForm(request.GET or None, enquete=enquete)
    if form.is_valid():
        participantes = form.get_participantes()
        if form.cleaned_data.get('exportar_xls'):
            if not participantes:
                return httprr(f'/enquete/ver_resultados/{enquete.id:d}/', 'Não há participantes para exportar.', tag='error')
            return tasks.exportar_resultado_to_xls(enquete, participantes)
        else:
            return tasks.processar_respostas_enquete(request, enquete, title)

    return locals()


@rtr()
@login_required()
def ver_publico(request, enquete_id):
    enquete = get_object_or_404(Enquete, pk=enquete_id)
    title = f'Público da Enquete: {enquete.titulo}'
    eh_responsavel_enquete = enquete.eh_responsavel(request.user)
    vinculos = enquete.vinculos_publico.all().order_by('pessoa__nome')
    form = BuscarPublicoForm(request.GET or None, enquete=enquete, request=request)
    if form.is_valid():
        vinculos = form.processar()
    vinculos = vinculos.annotate(respondeu=Exists(Resposta.objects.filter(pergunta__enquete=enquete, vinculo_id=OuterRef('pk')).values('pk')))
    try:
        contador = int(request.GET.get('page', 1)) - 1
    except Exception:
        contador = 0
    return locals()


@rtr()
@login_required()
def atualizar_publico(request, enquete_id):
    enquete = get_object_or_404(Enquete, pk=enquete_id)
    if not enquete.eh_responsavel(request.user):
        raise PermissionDenied
    enquete.save()
    return httprr(f'/enquete/ver_publico/{enquete.id:d}/', f'Público da enquete {enquete} foi atualizado com sucesso.')


@rtr()
@login_required()
def notificar_nao_respondentes(request, enquete_id):
    enquete = get_object_or_404(Enquete, pk=enquete_id)
    if not enquete.eh_responsavel(request.user):
        raise PermissionDenied
    if not enquete.estah_aberta:
        return httprr(f'/enquete/enquete/{enquete.id:d}/', 'Não é possível notificar o público não-respondente desta enquete.', tag='error')
    if enquete.notifica_publico_nao_respondente(vinculo_notificador=request.user.get_vinculo()):
        return httprr(f'/enquete/enquete/{enquete.id:d}/', 'O público não-respondente foi notificado com sucesso.')
    return httprr(f'/enquete/enquete/{enquete.id:d}/', 'Não há público não-respondente nesta enquete.', tag='error')
