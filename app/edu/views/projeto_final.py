import datetime
import json
from typing import Any

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.http.response import HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.utils import dateformat

from comum.models import Configuracao
from djtools.utils import (
    documento,
    httprr,
    rtr,
)
from edu import perms
from edu.forms import (
    EditarTituloPesquisaForm,
    LancarResultadoProjetoFinalForm,
    ParticipacaoProjetoFinalForm,
    ProjetoFinalForm,
    UploadDocumentoProjetoFinalForm,
)
from edu.models import Aluno, AtaEletronica, Professor, ProjetoFinal, SituacaoMatricula
from edu.perms import is_coorientador, is_orientador, is_proprio_aluno


@login_required()
@rtr()
def visualizar_agenda_defesas(request):
    title = 'Agenda de defesas de TCC'
    aluno = Aluno.objects.filter(matricula=request.user.username).only('curso_campus_id').first()
    projetos_finais = ProjetoFinal.objects.none()
    if aluno:
        projetos_finais = ProjetoFinal.objects.filter(
            data_defesa__gte=datetime.datetime.today(), matricula_periodo__aluno__curso_campus=aluno.curso_campus_id
        )
    return locals()


@rtr()
@login_required()
def visualizar_projeto_final(request, projetofinal_pk=None):
    obj = get_object_or_404(ProjetoFinal, pk=projetofinal_pk)
    title = f'Projeto Final: {obj.get_tipo_display()}'
    eh_aluno = request.user.eh_aluno
    pode_emitir_declaracao = perms.tem_permissao_realizar_procedimentos(request.user, obj.matricula_periodo.aluno)
    return locals()


@documento('Declaração de Orientação', validade=30, modelo='edu.professor', exibe_emissor=True)
@rtr('emitir_declaracao_de_orientacao_tcc_pdf.html')
@login_required()
def emitir_declaracao_de_orientacao_tcc_pdf(request: HttpRequest, pk: int, ano: int | None = None) -> dict | HttpResponse:
    obj = get_object_or_404(Professor, pk=pk)
    if not obj.pode_emitir_declaracao_docencia(request.user):
        return HttpResponseForbidden()
    nome_professor = obj.vinculo.pessoa.nome
    matricula_siape = obj.vinculo.relacionamento.matricula
    vinculo_usuario = request.user.get_vinculo()
    uo = None
    if vinculo_usuario and vinculo_usuario.setor:
        uo = vinculo_usuario.setor.uo
    hoje = datetime.date.today()
    projetos_finais = ProjetoFinal.objects.filter(orientador=obj).exclude(
        resultado_data__isnull=True,
        matricula_periodo__aluno__situacao__in=[SituacaoMatricula.JUBILADO, SituacaoMatricula.EVASAO, SituacaoMatricula.FALECIDO],
    )
    if ano:
        projetos_finais = projetos_finais.filter(matricula_periodo__ano_letivo__ano=ano)
    if not projetos_finais:
        return httprr(f'/edu/professor/{pk}/', 'Nenhum projeto final foi encontrado no período informado.', 'error')
    return locals()


@login_required()
@rtr()
def adicionar_projeto_final(request, aluno_pk, projetofinal_pk=None):
    title = '{} Trabalho de Conclusão de Curso / Relatório'.format(projetofinal_pk and 'Editar' or 'Adicionar')

    projeto_final = None
    if projetofinal_pk:
        projeto_final = get_object_or_404(ProjetoFinal, pk=projetofinal_pk)

    aluno = get_object_or_404(Aluno, pk=aluno_pk)

    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, aluno.curso_campus)
    if not pode_realizar_procedimentos:
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    form = ProjetoFinalForm(aluno, request.POST or None, instance=projeto_final, request=request)

    if form.is_valid():
        obj = form.save()

        if not projetofinal_pk:
            return httprr(f'/edu/aluno/{aluno.matricula}/?tab=projeto', 'TCC / Relatório adicionado com sucesso.')
        else:
            return httprr(f'/edu/aluno/{aluno.matricula}/?tab=projeto', 'TCC / Relatório atualizado com sucesso.')

    return locals()


@login_required()
@rtr()
def lancar_resultado_projeto_final(request, projetofinal_pk=None):
    title = 'Lançar Resultado de TCC / Relatório'
    projeto_final = get_object_or_404(ProjetoFinal.objects, pk=projetofinal_pk)

    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, projeto_final.matricula_periodo.aluno.curso_campus)
    if not pode_realizar_procedimentos:
        if projeto_final.presidente.vinculo != request.user.get_vinculo():
            return httprr('..', 'Você não tem permissão para realizar isso.', 'error')
    if not projeto_final.pode_ser_editado():
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')
    initial = {'resultado_nota': projeto_final.nota, 'tipo_documento': (projeto_final.documento_url and 1 or 2)}

    form = LancarResultadoProjetoFinalForm(request.POST or None, files=request.FILES or None, instance=projeto_final, initial=initial)
    if form.is_valid():
        complemento = ''
        if projeto_final.pode_ser_editado():
            form.save()

            if form.tipo_ata == ProjetoFinal.TIPO_ATA_ELETRONICA:
                if projeto_final.presidente and projeto_final.presidente.vinculo == request.user.get_vinculo():
                    return httprr(
                        '/admin/edu/ataeletronica/?tab=tab_pendentes', 'Resultado registrado com sucesso. Realize a assinatura da ata eletrônica'
                    )
                complemento = 'A ata eletrônica foi gerada e as solicitações de assinatura foram enviadas para os membros da banca por e-mail.'

            return httprr(
                f'/edu/aluno/{projeto_final.matricula_periodo.aluno.matricula}/?tab=projeto', f'Resultado registrado com sucesso. {complemento}'
            )
        else:
            return httprr('..', 'Você não tem permissão para realizar isso.', 'error')
    return locals()


@login_required()
@rtr()
def upload_documento_projeto_final(request, projetofinal_pk=None):
    title = 'Informar documento final de TCC/Relatório'
    projeto_final = get_object_or_404(ProjetoFinal.objects, pk=projetofinal_pk)

    pode_realizar_procedimentos = perms.realizar_procedimentos_academicos(request.user, projeto_final.matricula_periodo.aluno.curso_campus)
    if not pode_realizar_procedimentos:
        if projeto_final.presidente.vinculo != request.user.get_vinculo():
            return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    form = UploadDocumentoProjetoFinalForm(request.POST or None, files=request.FILES or None, instance=projeto_final)
    if form.is_valid():
        form.instance.documento_cadastrado_por = request.user
        form.instance.documento_cadastrado_em = datetime.datetime.now()
        form.save()
        return httprr(f'/edu/aluno/{projeto_final.matricula_periodo.aluno.matricula}/?tab=projeto', 'Resultado registrado com sucesso.')

    return locals()


@documento('Ata de Projeto Final', exibe_emissor=True)
@login_required()
@rtr('ata_projeto_final_pdf.html')
def ata_eletronica_projeto_final_pdf(request, pk):
    obj = get_object_or_404(AtaEletronica, pk=pk)
    dados_assinatura = []
    for assinatura in obj.get_assinaturas().filter(data__isnull=False):
        dados_assinatura.append(
            {
                'nome': assinatura.vinculo.nome,
                'matricula': assinatura.vinculo.pessoa.pessoafisica.get_cpf_ou_passaporte(),
                'data': assinatura.data.strftime('%d/%m/%Y %H:%M:%S'),
                'chave': assinatura.chave,
            }
        )
    request.GET._mutable = True
    request.GET['dados_assinatura'] = json.dumps(dados_assinatura)
    request.GET._mutable = False
    return imprimir_ata_projeto_final_pdf(request, obj.projeto_final.pk)


def visualizar_ata_eletronica(request, pk):
    obj = get_object_or_404(AtaEletronica, pk=pk)
    if not obj.get_assinaturas().filter(data__isnull=True).exists():
        return HttpResponseRedirect(f'/edu/ata_eletronica_projeto_final_pdf/{obj.pk}/')
    else:
        return HttpResponseRedirect(f'/edu/ata_projeto_final_pdf/{obj.projeto_final.pk}/')


@documento()
@login_required()
@rtr()
def ata_projeto_final_pdf(request, projetofinal_pk):
    return imprimir_ata_projeto_final_pdf(request, projetofinal_pk)


def imprimir_ata_projeto_final_pdf(request: HttpRequest, projetofinal_pk: int) -> dict[str, Any]:
    title = 'Lançar Resultado de Trabalho de Conclusão de Curso'
    obj = get_object_or_404(ProjetoFinal.objects, pk=projetofinal_pk)
    ata_eletronica = obj.get_ata_eletronica()
    artigo_aluno = obj.matricula_periodo.aluno.pessoa_fisica.sexo == 'F' and 'a' or 'o'
    artigo_presidente = obj.presidente and obj.presidente.vinculo and obj.presidente.vinculo.pessoa.pessoafisica.sexo == 'F' and 'a' or 'o'
    artigo_tipo = obj.tipo in ('Monografia', 'Dissertação', 'Tese') and 'da' or 'do'
    uo = obj.matricula_periodo.aluno.curso_campus.diretoria.setor.uo
    hoje = dateformat.format(datetime.date.today(), r'd \d\e F \d\e Y')
    instituicao = Configuracao.get_valor_por_chave_str('comum', 'instituicao').upper()
    lista_professores = []
    lista_assinaturas = set()
    coorienadores = obj.coorientadores_vinculos.all().values_list('pessoa__nome', flat=True)
    if obj.presidente:
        professor = obj.get_titulo_participante('presidente')
        lista_professores.append(professor)
        lista_assinaturas.add(professor[2])
    if obj.examinador_interno:
        professor = obj.get_titulo_participante('examinador_interno')
        lista_professores.append(professor)
        lista_assinaturas.add(professor[2])
    if obj.examinador_externo:
        professor = obj.get_titulo_participante('examinador_externo')
        lista_professores.append(professor)
        lista_assinaturas.add(professor[2])
    if obj.terceiro_examinador:
        professor = obj.get_titulo_participante('terceiro_examinador')
        lista_professores.append(professor)
        lista_assinaturas.add(professor[2])
    if obj.suplente_interno:
        professor = obj.get_titulo_participante('suplente_interno')
        lista_professores.append(professor)
        lista_assinaturas.add(professor[2])
    if obj.suplente_externo:
        professor = obj.get_titulo_participante('suplente_externo')
        lista_professores.append(professor)
        lista_assinaturas.add(professor[2])
    if obj.terceiro_suplente:
        professor = obj.get_titulo_participante('terceiro_suplente')
        lista_professores.append(professor)
        lista_assinaturas.add(professor[2])
    return locals()


PAPEIS_BANCA_DECLARACAO = (
    'orientador',
    'examinador_interno',
    'examinador_externo',
    'terceiro_examinador',
    'suplente_interno',
    'suplente_externo',
    'terceiro_suplente',
)


def _participante_declaracao(request: HttpRequest, obj: ProjetoFinal, participante: str) -> tuple[str, str, Any] | HttpResponse:
    """Sexo, participação e professor do ``participante`` da declaração, ou o redirect de erro."""
    if participante == 'coorientador':
        id_coorientador = request.GET.get('coorientador')
        if not id_coorientador:
            return httprr('..', 'Escolha um participante válido.', 'error')
        try:
            professor = obj.coorientadores_vinculos.get(pk=id_coorientador)
        except obj.coorientadores_vinculos.model.DoesNotExist:
            return httprr('..', 'Coorientador não encontrado para este projeto.', 'error')
        return professor.pessoa.pessoafisica.sexo, 'Coorientador', professor
    sexo, participacao, _ = obj.get_titulo_participante(participante)
    if not hasattr(obj, participante):
        return httprr('..', 'Escolha um participante válido.', 'error')
    return sexo, participacao, getattr(obj, participante)


def _membros_banca_declaracao(obj: ProjetoFinal) -> list[tuple[str, str, Any]]:
    """Membros da banca listados na declaração: (sexo, participação, vínculo/professor)."""
    lista_professores = []
    if obj.presidente and obj.orientador != obj.presidente:
        lista_professores.append(obj.get_titulo_participante('presidente'))
    lista_professores += [obj.get_titulo_participante(papel) for papel in PAPEIS_BANCA_DECLARACAO if getattr(obj, papel)]
    pks = [item[2].pk for item in lista_professores]
    for coorientador in obj.coorientadores_vinculos.exclude(pk__in=pks):
        sexo = coorientador.pessoa.pessoafisica.sexo or 'M'
        lista_professores.append(('M', 'Coorientador', coorientador) if sexo == 'M' else ('F', 'Coorientadora', coorientador))
    return lista_professores


def _pode_emitir_declaracao(request: HttpRequest, aluno: Aluno) -> bool:
    return (
        perms.tem_permissao_realizar_procedimentos(request.user, aluno)
        or perms.is_orientador(request, aluno)
        or perms.is_coorientador(request, aluno)
        or perms.is_examinador(request, aluno)
        or perms.is_presidente(request, aluno)
    )


@login_required()
@documento('Declaração de Participação em Projeto Final', False, validade=30, enumerar_paginas=False, modelo='edu.projetofinal', exibe_emissor=True)
@rtr()
def declaracao_participacao_projeto_final_pdf(request: HttpRequest, pk: int, participante: str) -> dict[str, Any] | HttpResponse:
    title = 'Gerar Declaração de Participação em Projeto Final'
    obj = get_object_or_404(ProjetoFinal.objects, pk=pk)
    escolhido = _participante_declaracao(request, obj, participante)
    if isinstance(escolhido, HttpResponse):
        return escolhido
    sexo, participacao, professor = escolhido
    vinculo = hasattr(professor, 'vinculo') and professor.vinculo or professor
    artigo_professor = sexo == 'F' and 'a' or 'o'
    artigo_aluno = obj.matricula_periodo.aluno.pessoa_fisica.sexo == 'F' and 'a' or 'o'
    lista_professores = _membros_banca_declaracao(obj)
    if not _pode_emitir_declaracao(request, obj.matricula_periodo.aluno):
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    uo = obj.matricula_periodo.aluno.curso_campus.diretoria.setor.uo
    hoje = dateformat.format(datetime.date.today(), r'd \d\e F \d\e Y')
    instituicao = Configuracao.get_valor_por_chave_str('comum', 'instituicao').upper()
    return locals()


@login_required()
@rtr()
def declaracao_participacao_projeto_final(request, projetofinal_pk):
    title = 'Gerar Declaração de Participação em Projeto Final'
    obj = get_object_or_404(ProjetoFinal.objects, pk=projetofinal_pk)

    if not perms.tem_permissao_realizar_procedimentos(request.user, obj.matricula_periodo.aluno) and not perms.is_orientador(
        request, obj.matricula_periodo.aluno
    ):
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    form = ParticipacaoProjetoFinalForm(projeto_final=obj)

    participante = request.GET.get('participante')
    if participante:
        if participante.startswith('coorientador_'):
            vinculo = participante.split('_')[-1]
            return HttpResponseRedirect(f'/edu/declaracao_participacao_projeto_final_pdf/{projetofinal_pk}/coorientador/?coorientador={vinculo}')
        else:
            return HttpResponseRedirect(f'/edu/declaracao_participacao_projeto_final_pdf/{projetofinal_pk}/{participante}/')
    return locals()


@rtr()
@login_required()
def editar_titulo_pesquisa(request, pk):
    title = 'Editar Título do Projeto de Pesquisa'
    aluno = Aluno.locals.filter(pk=pk).first()
    if not aluno.eh_aluno_nivel_pos_graduacao() and not (
        perms.pode_editar_orientadores_pos(request, aluno)
        or is_proprio_aluno(request, aluno)
        or is_orientador(request, aluno)
        or is_coorientador(request, aluno)
    ):
        raise PermissionDenied
    form = EditarTituloPesquisaForm(request.POST or None, instance=aluno)
    if form.is_valid():
        form.save()
        return httprr('..', 'Título do Projeto de Pesquisa atualizado com sucesso.')
    return locals()
