from datetime import date

from djtools.utils import documento, httprr, rtr, permission_required
from sica.forms import ComponenteCurricularForm, EditarAlunoForm, RegistroHistoricoForm
from sica.models import ComponenteCurricular, Historico, Matriz, RegistroHistorico


@rtr()
@permission_required('sica.change_matriz')
def matriz(request, pk, ano_inicio=None, ano_fim=None):
    obj = Matriz.objects.get(pk=pk)
    title = str(obj)
    componentes_curriculares = obj.get_componentes_curriculares(ano_inicio, ano_fim)
    return locals()


@rtr()
@permission_required('sica.change_historico')
def historico(request, pk):
    obj = Historico.objects.get(pk=pk)
    tem_registro_emissao = obj.tem_registro_emissao_documento()
    title = str(obj.aluno)
    if 'reprocessar' in request.GET:
        obj.componentes_curriculares.clear()
        obj.registrohistorico_set.filter(ano__isnull=True).delete()
        return httprr(f'/sica/historico/{obj.pk}/', 'Histórico reprocessado com sucesso')

    registros_emissao = obj.aluno.get_registros_emissao_diploma()
    ano_inicio, ano_fim = obj.get_periodo_realizacao()

    pendencias = []
    if not obj.aluno.pessoa_fisica.cpf:
        pendencias.append('CPF')
    if not obj.aluno.pessoa_fisica.sexo:
        pendencias.append('Sexo')
    if not obj.aluno.data_emissao_rg or not obj.aluno.numero_rg or not obj.aluno.orgao_emissao_rg or not obj.aluno.uf_emissao_rg:
        pendencias.append('Número, data da emissão, orgão emissor ou UF do RG')
    if not obj.aluno.naturalidade:
        pendencias.append('Naturalidade')
    if not obj.aluno.nome_mae:
        pendencias.append('Nome da mãe')
    if not obj.aluno.matricula:
        pendencias.append('Matrícula')
    if not obj.matriz:
        pendencias.append('Matriz')
    if not obj.matriz.reconhecimento:
        pendencias.append('Reconhecimento do curso/matriz')

    return locals()


@rtr()
@permission_required('sica.change_historico')
def invalidar_registros_emissao(request, pk):
    obj = Historico.objects.get(pk=pk)
    obj.excluir_registros_emissao_documento()
    return httprr(f'/sica/historico/{pk}/', 'Histórico e Certificado inválidado com sucesso.')


@rtr()
@permission_required('sica.change_historico')
def atualizar_componente_curricular(request, pk):
    obj = ComponenteCurricular.objects.get(pk=pk)
    form = ComponenteCurricularForm(data=request.POST or None, instance=obj)
    if form.is_valid():
        instance = form.save()
        return httprr('..', 'Registro salvo com sucesso.')
    return locals()


@rtr()
@permission_required('sica.change_historico')
def atualizar_registro(request, pk, registro_pk=None):
    obj = Historico.objects.get(pk=pk)
    instance = registro_pk and RegistroHistorico.objects.get(pk=registro_pk) or None
    form = RegistroHistoricoForm(data=request.POST or None, instance=instance)
    if form.is_valid():
        instance = form.save(False)
        instance.historico = obj
        instance.save()
        return httprr('..', 'Registro salvo com sucesso.')
    return locals()


@documento('Histórico SICA', modelo='sica.Historico')
@permission_required('sica.change_historico')
@rtr()
def historico_sica_pdf(request, pk):
    obj = Historico.objects.get(pk=pk)
    hoje = date.today()
    registros_emissao = obj.aluno.get_registros_emissao_diploma()
    registro_emissao = registros_emissao and registros_emissao[0] or None
    return locals()


@documento('Declaração SICA', enumerar_paginas=False, modelo='sica.Historico')
@permission_required('sica.change_historico')
@rtr()
def declaracao_sica_pdf(request, pk):
    obj = Historico.objects.get(pk=pk)
    if not obj.aluno.is_concluido():
        return httprr('..', 'O aluno não está concluído.', tag='error')
    hoje = date.today()
    try:
        ano, periodo = obj.get_ultimo_periodo_letivo()
    except ValueError as e:
        return httprr(f'/sica/historico/{pk}/', str(e), 'error')
    return locals()


@permission_required('sica.change_historico')
@rtr()
def editar_aluno(request, pk):
    obj = Historico.objects.get(pk=pk)
    title = 'Aluno'
    form = EditarAlunoForm(data=request.POST or None, files=request.FILES or None, instance=obj.aluno, historico=obj)
    if form.is_valid():
        form.save()
        return httprr('..', 'Aluno atualizado com sucesso.')
    return locals()
