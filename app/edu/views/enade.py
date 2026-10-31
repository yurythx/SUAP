import datetime
import os

from django.conf import settings
from django.http.response import HttpResponseForbidden
from django.shortcuts import get_object_or_404

from comum.models import Configuracao
from comum.utils import get_sigla_reitoria
from djtools.templatetags.filters import format_
from djtools.utils import (
    XlsResponse,
    documento,
    httprr,
    permission_required,
    rtr,
)
from edu import perms, tasks
from edu.forms import (
    AtualizarListaConvocadosENADEForm,
    DatasIncricaoENADEForm,
    DispensaConvocacaoENADEEmLoteForm,
    DispensaConvocacaoENADEForm,
    JustificativaDispensaENADECursoCampusForm,
    LancarSituacaoAlunoENADEForm,
    ModalidadeConvocacaoENADEForm,
    RegistroConvocacaoENADEForm,
)
from edu.models import (
    Aluno,
    ConvocacaoENADE,
    CursoCampus,
    ModalidadeConvocacaoENADE,
    PossivelConcluinte,
    PossivelIntegralizado,
    RegistroConvocacaoENADE,
)
from rh.models import UnidadeOrganizacional


@rtr()
@permission_required('edu.view_convocacaoenade')
def convocacao_enade(request, pk):
    obj = get_object_or_404(ConvocacaoENADE, pk=pk)
    title = obj.descricao
    acesso_total = request.user.has_perm('edu.change_convocacaoenade')
    is_avaliacao_teorica = obj.is_avaliacao_teorica()
    pode_editar_criterios_teorica = obj.pode_editar_criterios(request.user) and is_avaliacao_teorica
    pode_editar_criterios_pratica = obj.pode_editar_criterios(request.user) and not is_avaliacao_teorica

    pk_cursos_nao_convocados = obj.get_pk_cursos_nao_convocados()

    cursos_desabilitados = CursoCampus.objects.filter(
        area_curso_formacao_superior__in=obj.areas_cursos_formacao_superior.all(),
        modalidade__in=obj.modalidades_convocadas.all(),
        processamento_enade=False,
    ).exclude(id__in=obj.cursos.all().values_list('id', flat=True))

    if acesso_total or request.user.has_group_cached('Secretário Acadêmico, Estagiário Acadêmico Sistêmico'):
        cursos = obj.cursos.all()
        cursos_nao_convocados = CursoCampus.objects.filter(pk__in=pk_cursos_nao_convocados)

    else:
        cursos = CursoCampus.locals.sob_coordenacao_de(request.user.get_vinculo())
        cursos_nao_convocados = cursos.filter(pk__in=pk_cursos_nao_convocados)
        cursos = cursos.exclude(pk__in=pk_cursos_nao_convocados)

    tabela_nao_convocados = []
    for curso_campus in cursos_nao_convocados.order_by('justificativa_dispensa_ingressante_id', 'diretoria__setor__uo'):
        total_ingressantes = obj.registroconvocacaoenade_set.filter(
            aluno__curso_campus=curso_campus, tipo_convocacao=RegistroConvocacaoENADE.TIPO_CONVOCACAO_INGRESSANTE
        ).count()
        total_concluintes = obj.registroconvocacaoenade_set.filter(
            aluno__curso_campus=curso_campus, tipo_convocacao=RegistroConvocacaoENADE.TIPO_CONVOCACAO_CONCLUINTE
        ).count()
        total_alunos = total_ingressantes + total_concluintes
        tabela_nao_convocados.append(
            {
                'curso_campus': curso_campus,
                'total_ingressantes': total_ingressantes,
                'total_concluintes': total_concluintes,
                'total_alunos': total_alunos,
            }
        )

    possui_convocacao = obj.registroconvocacaoenade_set.exists()

    if 'xls' in request.GET:
        lista_convocados = obj.registroconvocacaoenade_set.all()
        curso_id = request.GET.get('curso')
        if curso_id:
            lista_convocados = lista_convocados.filter(aluno__curso_campus_id=curso_id)
        rows = [
            [
                '#',
                'Tipo',
                'Matrícula',
                'Curso',
                'CPF',
                'Nome',
                'Data de Nascimento',
                'Sexo',
                'RG',
                'Telefone',
                'CEP',
                'UF',
                'Município',
                'Logradouro',
                'Número',
                'Complemento',
                'Bairro',
                'Ano de Conclusão do Ensino Médio',
                'Turno',
                '% CH Cumprido',
            ]
        ]
        count = 0
        for convocacao in lista_convocados.order_by('aluno__curso_campus', 'tipo_convocacao', 'aluno__pessoa_fisica__nome'):
            if convocacao.tipo_convocacao == 1:
                tipo_convocacao = 'Ingressante'
            else:
                tipo_convocacao = 'Concluinte'

            count += 1
            row = [
                count,
                format_(tipo_convocacao),
                format_(convocacao.aluno.matricula),
                format_(convocacao.aluno.curso_campus),
                format_(convocacao.aluno.pessoa_fisica.cpf),
                format_(convocacao.aluno.get_nome_social_composto()),
                format_(convocacao.aluno.pessoa_fisica.nascimento_data),
                format_(convocacao.aluno.pessoa_fisica.sexo),
                format_(convocacao.aluno.pessoa_fisica.rg),
                f'{format_(convocacao.aluno.telefone_principal)}, {format_(convocacao.aluno.telefone_secundario)}',
                format_(convocacao.aluno.cep),
                format_(convocacao.aluno.cidade and convocacao.aluno.cidade.estado or None),
                format_(convocacao.aluno.cidade),
                format_(convocacao.aluno.logradouro),
                format_(convocacao.aluno.numero),
                format_(convocacao.aluno.complemento),
                format_(convocacao.aluno.bairro),
                format_(convocacao.aluno.ano_conclusao_estudo_anterior),
                format_(convocacao.aluno.turno),
                format_(convocacao.percentual_ch_cumprida),
            ]
            rows.append(row)
        return XlsResponse(rows)
    return locals()


@rtr()
@permission_required('edu.change_convocacaoenade')
def editar_justificativa_dispensa(request, pk):
    title = 'Editar justificativa de dispensa do ENADE'
    obj = CursoCampus.objects.get(pk=pk)
    form = JustificativaDispensaENADECursoCampusForm(data=request.POST or None, instance=obj)
    if form.is_valid():
        form.save()
        return httprr('.', 'Operação realizada com sucesso.', close_popup=True)
    return locals()


@rtr()
@permission_required('edu.change_convocacaoenade')
def editar_datas_inscricao_convocacaoenade(request, pk):
    obj = get_object_or_404(ConvocacaoENADE, pk=pk)
    title = f'Editar datas de inscrição ENADE {obj.ano_letivo.ano}'
    form = DatasIncricaoENADEForm(data=request.POST or None, instance=obj)
    if form.is_valid():
        form.save()
        return httprr('.', 'Operação realizada com sucesso.', close_popup=True)
    return locals()


@rtr()
@permission_required('edu.change_convocacaoenade')
def dispensar_nao_convocados(request, pk):
    obj = get_object_or_404(ConvocacaoENADE, pk=pk)
    return tasks.dispensar_nao_convocados_enade(obj)


@rtr()
@permission_required('edu.add_convocacaoenade')
def editar_modalidadeconvocacaoenade(request, pk):
    obj = ModalidadeConvocacaoENADE.objects.get(pk=pk)
    title = f'Editar critérios de convocação da modalidade {obj.modalidade.descricao}'
    form = ModalidadeConvocacaoENADEForm(data=request.POST or None, instance=obj)
    if form.is_valid():
        form.save()
        return httprr('.', 'Operação realizada com sucesso.', close_popup=True)
    return locals()


@rtr()
@permission_required('edu.change_convocacaoenade')
def habilitar_desabilitar_curso_enade(request, convocacao_enade_pk, curso_pk):
    convocacao_enade = get_object_or_404(ConvocacaoENADE, pk=convocacao_enade_pk)
    curso = get_object_or_404(CursoCampus, pk=curso_pk)
    valor = not curso.processamento_enade

    if valor is False:
        # Desabilitar
        if convocacao_enade.registroconvocacaoenade_set.filter(aluno__curso_campus_id=curso_pk, situacao__isnull=False).exists():
            return httprr(
                convocacao_enade.get_absolute_url(), 'Não é possível desabilitar um curso com aluno que possui situação lançada.', tag='error'
            )
        convocacao_enade.cursos.remove(curso)
        convocacao_enade.registroconvocacaoenade_set.filter(aluno__curso_campus_id=curso_pk).delete()
        convocacao_enade.possivelconcluinte_set.filter(aluno__curso_campus_id=curso_pk).delete()
        convocacao_enade.possivelintegralizado_set.filter(aluno__curso_campus_id=curso_pk).delete()

        mensagem = 'Operação realizada com sucesso.'
    else:
        convocacao_enade.cursos.add(curso)
        mensagem = 'Operação realizada com sucesso. É necessário reprocessar a convocação deste curso.'

    CursoCampus.objects.filter(pk=curso_pk).update(processamento_enade=valor)
    return httprr(convocacao_enade.get_absolute_url(), mensagem)


@rtr()
@permission_required('edu.change_convocacaoenade')
def atualizar_lista_convocados_enade(request, pk):
    obj = get_object_or_404(ConvocacaoENADE, pk=pk)
    title = f'Convocação ENADE {obj.ano_letivo.ano} - Atualizar lista de convocados'
    if obj.pode_processar_lista_convocados(request.user):
        form = AtualizarListaConvocadosENADEForm(data=request.GET or None, convocacao_enade=obj)
        if form.is_valid():
            return form.processar(request)
    else:
        return httprr(obj.get_absolute_url(), 'Esta convocação não pode ser reprocessada.', 'error')
    return locals()


@rtr()
@permission_required('edu.change_registroconvocacaoenade')
def lancar_situacao_enade(request, pk):
    title = 'Convocação para o ENADE'

    obj = get_object_or_404(RegistroConvocacaoENADE, pk=pk)
    form = LancarSituacaoAlunoENADEForm(data=request.POST or None, instance=obj)

    if form.is_valid():
        obj = form.save()

        if obj.situacao != RegistroConvocacaoENADE.SITUACAO_DISPENSADO and obj.justificativa_dispensa:
            obj.justificativa_dispensa = None
            obj.save()

        return httprr(f'/edu/aluno/{obj.aluno.matricula}/?tab=convocacoes_enade', 'Lançamento do ENADE realizado com sucesso.')

    return locals()


@rtr()
@permission_required('edu.change_registroconvocacaoenade')
def remover_situacao_enade(request, pk):
    obj = get_object_or_404(RegistroConvocacaoENADE, pk=pk)
    obj.remover_situacao()
    return httprr(f'/edu/aluno/{obj.aluno.matricula}/?tab=convocacoes_enade', 'Situação do ENADE removida com sucesso.')


@rtr()
@permission_required('edu.view_convocacaoenade')
def convocados_enade(request, pk, curso_campus_pk, periodo_id=None):
    obj = get_object_or_404(ConvocacaoENADE, pk=pk)
    curso_campus = get_object_or_404(CursoCampus, pk=curso_campus_pk)
    title = f'Convocados: {curso_campus.descricao_historico}'
    acesso_total = perms.pode_realizar_procedimentos_enade(request.user, curso_campus)
    lista_convocados = obj.registroconvocacaoenade_set.filter(aluno__curso_campus_id=curso_campus_pk)
    if periodo_id:
        lista_convocados = lista_convocados.filter(periodo_convocacao_regencia_id=periodo_id)
    ingressantes = lista_convocados.filter(tipo_convocacao=RegistroConvocacaoENADE.TIPO_CONVOCACAO_INGRESSANTE)
    concluintes = lista_convocados.filter(tipo_convocacao=RegistroConvocacaoENADE.TIPO_CONVOCACAO_CONCLUINTE)
    concluintes_ap = lista_convocados.filter(tipo_convocacao=RegistroConvocacaoENADE.TIPO_CONVOCACAO_CONCLUINTE_AP)

    publico_comunicador = []
    if ingressantes.exists():
        publico_comunicador.append([RegistroConvocacaoENADE.TIPO_CONVOCACAO_INGRESSANTE, 'Ingressantes'])
    if concluintes.exists():
        publico_comunicador.append([RegistroConvocacaoENADE.TIPO_CONVOCACAO_CONCLUINTE, 'Concluintes'])
    if concluintes_ap.exists():
        publico_comunicador.append([RegistroConvocacaoENADE.TIPO_CONVOCACAO_CONCLUINTE_AP, 'Concluintes AP'])
    if len(publico_comunicador) > 1:
        publico_comunicador.append(['', 'Todos os convocados'])

    dispensa_enape_em_lote = Configuracao.get_valor_por_chave('edu', 'dispensa_enape_em_lote') or None

    if acesso_total:
        convocacoes_selecionadas = request.POST.getlist('convocacoes_selecionadas')

        if 'excluir' in request.POST:
            possiveis_integralizados = lista_convocados.filter(possivel_integralizado=True, pk__in=convocacoes_selecionadas).values_list(
                'aluno_id', flat=True
            )
            PossivelIntegralizado.objects.filter(aluno_id__in=possiveis_integralizados, convocacao_enade_id=pk).update(convocado=False)

            possiveis_concluintes = lista_convocados.filter(possivel_concluinte=True, pk__in=convocacoes_selecionadas).values_list(
                'aluno_id', flat=True
            )
            PossivelConcluinte.objects.filter(aluno_id__in=possiveis_concluintes, convocacao_enade_id=pk).update(convocado=False)

            lista_convocados.filter(pk__in=convocacoes_selecionadas).delete()
            return httprr('.', 'Registros de convocação removidos com sucesso.')

        if 'xls' in request.GET:
            if convocacoes_selecionadas:
                lista_convocados = obj.registroconvocacaoenade_set.filter(pk__in=convocacoes_selecionadas)
            rows = [
                [
                    '#',
                    'Tipo',
                    'Matrícula',
                    'Curso',
                    'CPF',
                    'Nome',
                    'Data de Nascimento',
                    'Sexo',
                    'RG',
                    'Telefone',
                    'CEP',
                    'UF',
                    'Município',
                    'Logradouro',
                    'Número',
                    'Complemento',
                    'Bairro',
                    'Ano de Conclusão do Ensino Médio',
                    'Turno',
                ]
            ]
            count = 0
            for convocacao in lista_convocados.order_by('aluno__curso_campus', 'tipo_convocacao', 'aluno__pessoa_fisica__nome'):
                if convocacao.tipo_convocacao == 1:
                    tipo_convocacao = 'Ingressante'
                else:
                    tipo_convocacao = 'Concluinte'

                count += 1
                row = [
                    count,
                    format_(tipo_convocacao),
                    format_(convocacao.aluno.matricula),
                    format_(convocacao.aluno.curso_campus),
                    format_(convocacao.aluno.pessoa_fisica.cpf),
                    format_(convocacao.aluno.get_nome_social_composto()),
                    format_(convocacao.aluno.pessoa_fisica.nascimento_data),
                    format_(convocacao.aluno.pessoa_fisica.sexo),
                    format_(convocacao.aluno.pessoa_fisica.rg),
                    f'{format_(convocacao.aluno.telefone_principal)}, {format_(convocacao.aluno.telefone_secundario)}',
                    format_(convocacao.aluno.cep),
                    format_(convocacao.aluno.cidade and convocacao.aluno.cidade.estado or None),
                    format_(convocacao.aluno.cidade),
                    format_(convocacao.aluno.logradouro),
                    format_(convocacao.aluno.numero),
                    format_(convocacao.aluno.complemento),
                    format_(convocacao.aluno.bairro),
                    format_(convocacao.aluno.ano_conclusao_estudo_anterior),
                    format_(convocacao.aluno.turno),
                ]
                rows.append(row)
            return XlsResponse(rows)

    return locals()


@rtr()
@permission_required('edu.view_convocacaoenade')
def possiveis_integralizados_enade(request, pk, curso_campus_pk):
    title = 'Lista de possíveis integralizados'
    obj = get_object_or_404(ConvocacaoENADE, pk=pk)
    curso_campus = get_object_or_404(CursoCampus, pk=curso_campus_pk)
    acesso_total = perms.pode_realizar_procedimentos_enade(request.user, curso_campus)
    lista_convocados = obj.possivelintegralizado_set.filter(aluno__curso_campus_id=curso_campus_pk).order_by('-convocado')

    if acesso_total:
        convocacoes_selecionadas = request.POST.getlist('convocacoes_selecionadas')

        if 'excluir' in request.POST:
            lista_convocados.filter(pk__in=convocacoes_selecionadas).filter(convocado=False).delete()
            return httprr('.', 'Possíveis integralizados removidos com sucesso.')

        if 'convocar' in request.POST:
            for convocado in lista_convocados.filter(pk__in=convocacoes_selecionadas):
                convocado.convocar()
            return httprr('.', 'Possíveis integralizados convocados com sucesso.')

        if 'xls' in request.POST:
            if convocacoes_selecionadas:
                lista_convocados = obj.registroconvocacaoenade_set.filter(pk__in=convocacoes_selecionadas)
            rows = [
                [
                    '#',
                    'Convocado',
                    'Matrícula',
                    'Curso',
                    'CPF',
                    'Nome',
                    'Data de Nascimento',
                    'Sexo',
                    'RG',
                    'Telefone',
                    'CEP',
                    'UF',
                    'Município',
                    'Logradouro',
                    'Número',
                    'Complemento',
                    'Bairro',
                    'Ano de Conclusão do Ensino Médio',
                    'Turno',
                ]
            ]
            count = 0
            for convocacao in lista_convocados.order_by('aluno__curso_campus', 'aluno__pessoa_fisica__nome'):
                if convocacao.convocado:
                    tipo_convocacao = 'Sim'
                else:
                    tipo_convocacao = 'Não'

                count += 1
                row = [
                    count,
                    format_(tipo_convocacao),
                    format_(convocacao.aluno.matricula),
                    format_(convocacao.aluno.curso_campus),
                    format_(convocacao.aluno.pessoa_fisica.cpf),
                    format_(convocacao.aluno.get_nome_social_composto()),
                    format_(convocacao.aluno.pessoa_fisica.nascimento_data),
                    format_(convocacao.aluno.pessoa_fisica.sexo),
                    format_(convocacao.aluno.pessoa_fisica.rg),
                    f'{format_(convocacao.aluno.telefone_principal)}, {format_(convocacao.aluno.telefone_secundario)}',
                    format_(convocacao.aluno.cep),
                    format_(convocacao.aluno.cidade and convocacao.aluno.cidade.estado or None),
                    format_(convocacao.aluno.cidade),
                    format_(convocacao.aluno.logradouro),
                    format_(convocacao.aluno.numero),
                    format_(convocacao.aluno.complemento),
                    format_(convocacao.aluno.bairro),
                    format_(convocacao.aluno.ano_conclusao_estudo_anterior),
                    format_(convocacao.aluno.turno),
                ]
                rows.append(row)
            return XlsResponse(rows)

    return locals()


@rtr()
@permission_required('edu.view_convocacaoenade')
def possiveis_concluintes_enade(request, pk, curso_campus_pk):
    title = 'Lista de possíveis concluintes'
    obj = get_object_or_404(ConvocacaoENADE, pk=pk)
    curso_campus = get_object_or_404(CursoCampus, pk=curso_campus_pk)
    acesso_total = perms.pode_realizar_procedimentos_enade(request.user, curso_campus)
    lista_convocados = obj.possivelconcluinte_set.filter(aluno__curso_campus_id=curso_campus_pk).order_by('-convocado')

    if acesso_total:
        convocacoes_selecionadas = request.POST.getlist('convocacoes_selecionadas')

        if 'excluir' in request.POST:
            lista_convocados.filter(pk__in=convocacoes_selecionadas).filter(convocado=False).delete()
            return httprr('.', 'Possíveis concluintes removidos com sucesso.')

        if 'convocar' in request.POST:
            for convocado in lista_convocados.filter(pk__in=convocacoes_selecionadas):
                convocado.convocar()
            return httprr('.', 'Possíveis concluintes convocados com sucesso.')

        if 'xls' in request.POST:
            if convocacoes_selecionadas:
                lista_convocados = obj.registroconvocacaoenade_set.filter(pk__in=convocacoes_selecionadas)
            rows = [
                [
                    '#',
                    'Convocado',
                    'Matrícula',
                    'Curso',
                    'CPF',
                    'Nome',
                    'Data de Nascimento',
                    'Sexo',
                    'RG',
                    'Telefone',
                    'CEP',
                    'UF',
                    'Município',
                    'Logradouro',
                    'Número',
                    'Complemento',
                    'Bairro',
                    'Ano de Conclusão do Ensino Médio',
                    'Turno',
                ]
            ]
            count = 0
            for convocacao in lista_convocados.order_by('aluno__curso_campus', 'aluno__pessoa_fisica__nome'):
                if convocacao.convocado:
                    tipo_convocacao = 'Sim'
                else:
                    tipo_convocacao = 'Não'

                count += 1
                row = [
                    count,
                    format_(tipo_convocacao),
                    format_(convocacao.aluno.matricula),
                    format_(convocacao.aluno.curso_campus),
                    format_(convocacao.aluno.pessoa_fisica.cpf),
                    format_(convocacao.aluno.get_nome_social_composto()),
                    format_(convocacao.aluno.pessoa_fisica.nascimento_data),
                    format_(convocacao.aluno.pessoa_fisica.sexo),
                    format_(convocacao.aluno.pessoa_fisica.rg),
                    f'{format_(convocacao.aluno.telefone_principal)}, {format_(convocacao.aluno.telefone_secundario)}',
                    format_(convocacao.aluno.cep),
                    format_(convocacao.aluno.cidade and convocacao.aluno.cidade.estado or None),
                    format_(convocacao.aluno.cidade),
                    format_(convocacao.aluno.logradouro),
                    format_(convocacao.aluno.numero),
                    format_(convocacao.aluno.complemento),
                    format_(convocacao.aluno.bairro),
                    format_(convocacao.aluno.ano_conclusao_estudo_anterior),
                    format_(convocacao.aluno.turno),
                ]
                rows.append(row)
            return XlsResponse(rows)

    return locals()


@rtr()
@permission_required('edu.add_registroconvocacaoenade')
def adicionar_aluno_avulso_enade(request, pk, curso_campus_pk):
    title = 'Adicionar Aluno Avulso'
    convocacao = get_object_or_404(ConvocacaoENADE.objects, pk=pk)
    curso_campus = get_object_or_404(CursoCampus.objects, pk=curso_campus_pk)

    form = RegistroConvocacaoENADEForm(convocacao, curso_campus, data=request.POST or None)
    if form.is_valid():
        form.save()
        return httprr('..', 'Aluno avulso cadastrado com sucesso.')

    return locals()


@rtr()
@permission_required('edu.add_registroconvocacaoenade')
def dispensar_participacao_enade(request, matricula):
    title = 'Registrar dispensa de aluno da convocação do ENADE'
    aluno = get_object_or_404(Aluno.objects, matricula=matricula)
    url_retorno = f'/edu/aluno/{aluno.matricula}/?tab=convocacoes_enade'
    if not aluno.pode_ser_dispensado_enade() and not request.user.has_group_cached('Diretor de Avaliação e Regulação do Ensino'):
        return httprr(url_retorno, 'Este aluno não pode ser dispensado do ENADE.', 'error', close_popup=True)
    form = DispensaConvocacaoENADEForm(data=request.POST or None, aluno=aluno)
    if form.is_valid():
        registro = RegistroConvocacaoENADE()
        registro.aluno = aluno
        registro.situacao = RegistroConvocacaoENADE.SITUACAO_DISPENSADO
        registro.convocacao_enade = form.cleaned_data.get('convocacao_enade')
        registro.justificativa_dispensa = form.cleaned_data.get('justificativa_dispensa')
        registro.tipo_convocacao = form.cleaned_data.get('tipo_convocacao')
        registro.save()
        return httprr(url_retorno, 'Registro de dispensa do ENADE cadastrada com sucesso.', close_popup=True)

    return locals()


@rtr()
@permission_required('edu.add_registroconvocacaoenade')
def dispensar_participacao_enade_em_lote(request, pk, curso_campus_pk, pks):
    #
    # configuração da funcionalidade
    dispensa_enape_em_lote = Configuracao.get_valor_por_chave('edu', 'dispensa_enape_em_lote') or None
    if not dispensa_enape_em_lote:
        raise HttpResponseForbidden(
            'Esta funcionalidade não está habilitada no momento. Acesso as configurações do SUAP e habilite a dispensa ENADE em lote.'
        )
    #
    # permissão de acesso a perfil específico
    if not request.user.has_group_cached('Diretor de Avaliação e Regulação do Ensino'):
        raise HttpResponseForbidden('Apenas Diretores de Avaliação e Regulação do Ensino podem realizar a dispensa em lote do ENADE.')
    title = 'Registrar dispensa de alunos da convocação do ENADE em lote'
    obj = get_object_or_404(ConvocacaoENADE, pk=pk)
    lista_convocados = obj.registroconvocacaoenade_set.filter(aluno__curso_campus_id=curso_campus_pk)
    #
    # verificando se foi selecionando alunos de uma lista apenas (ou concluintes ou ingressantes, e não das duas listas)
    check_lista = lista_convocados.filter(pk__in=pks.split(','))
    tipo_check = None
    for check in check_lista:
        if tipo_check and tipo_check != check.tipo_convocacao:
            return httprr(
                f'/edu/convocados_enade/{pk}/{curso_campus_pk}/',
                'Não é possível selecionar alunos "Ingressantes" e "Concluintes" ao mesmo tempo. Selecione alunos de uma lista por vez.',
                tag='warning',
            )
        tipo_check = check.tipo_convocacao
    #
    form = DispensaConvocacaoENADEEmLoteForm(data=request.POST or None, selecionados=pks)
    #
    if form.is_valid():
        lista_ids = form.cleaned_data.get('selecionados').split(',')
        lista = lista_convocados.filter(pk__in=lista_ids)
        alunos_problemas = []
        #
        for i in lista:
            #
            aluno = i.aluno
            try:
                rce = RegistroConvocacaoENADE.objects.get(id=i.pk)
                rce.situacao = RegistroConvocacaoENADE.SITUACAO_DISPENSADO
                rce.justificativa_dispensa = form.cleaned_data.get('justificativa_dispensa')
                rce.save()
            except Exception:
                alunos_problemas.append(f'{aluno.pessoa_fisica.nome} ({aluno.matricula})')
        #
        if alunos_problemas:
            msg = f'Registros de dispensadas realizados, porém, encontramos problemas com os seguintes alunos: {alunos_problemas}'
            return httprr(f'/edu/convocados_enade/{pk}/{curso_campus_pk}/', msg, tag='warning')
        #
        return httprr(f'/edu/convocados_enade/{pk}/{curso_campus_pk}/', 'Registros de dispensadas realizado com sucesso.')
    #
    return locals()


@documento()
@rtr()
@permission_required('edu.view_convocacaoenade')
def imprimir_lista_convocados_enade_pdf(request, pk):
    obj = get_object_or_404(ConvocacaoENADE, pk=pk)
    sigla_reitoria = get_sigla_reitoria()
    uo = UnidadeOrganizacional.objects.suap().get(sigla=sigla_reitoria)
    lista_convocados = obj.registroconvocacaoenade_set.all()
    curso_id = request.GET.get('curso')
    if curso_id:
        lista_convocados = lista_convocados.filter(aluno__curso_campus_id=curso_id)
    ingressantes = lista_convocados.filter(tipo_convocacao=RegistroConvocacaoENADE.TIPO_CONVOCACAO_INGRESSANTE)
    concluintes = lista_convocados.filter(tipo_convocacao=RegistroConvocacaoENADE.TIPO_CONVOCACAO_CONCLUINTE)
    return locals()


@rtr()
@permission_required('edu.view_convocacaoenade')
def download_estudantes_ingressantes_avaliacao_teorica(request, convocacao_enade_pk, curso_pk):
    convocacao_enade = get_object_or_404(ConvocacaoENADE, pk=convocacao_enade_pk)
    curso = get_object_or_404(CursoCampus, pk=curso_pk)

    lista_convocados = convocacao_enade.registroconvocacaoenade_set.filter(
        aluno__curso_campus_id=curso.id, tipo_convocacao=RegistroConvocacaoENADE.TIPO_CONVOCACAO_INGRESSANTE
    ).exclude(situacao=RegistroConvocacaoENADE.SITUACAO_DISPENSADO)
    codigo_curso = curso.codigo_emec
    codigo_IES = Configuracao.get_valor_por_chave('edu', 'codigo_mec')

    ano = convocacao_enade.ano_letivo.ano
    ano = str(ano)[2:4]
    codigo_projeto = f'{ano}11101'  # 2 dígitos do ano + 1 dígito de edição do projeto + 2 dígitos do programa + 2 dígitos da etapa
    data_geracao = datetime.datetime.now().strftime('%d%m%Y')
    nome_arquivo = f'ENADE{codigo_projeto}_N92_BR_{data_geracao}_{codigo_curso}_E001.TXT'

    file_path = os.path.join(settings.TEMP_DIR, nome_arquivo)
    return tasks.download_estudantes_ingressantes_avaliacao_teorica(file_path, lista_convocados, codigo_IES, codigo_projeto, codigo_curso)


@rtr()
@permission_required('edu.view_convocacaoenade')
def download_estudantes_concluintes_avaliacao_teorica(request, convocacao_enade_pk, curso_pk):
    convocacao_enade = get_object_or_404(ConvocacaoENADE, pk=convocacao_enade_pk)
    curso = get_object_or_404(CursoCampus, pk=curso_pk)

    lista_convocados = convocacao_enade.registroconvocacaoenade_set.filter(
        aluno__curso_campus_id=curso.id, tipo_convocacao=RegistroConvocacaoENADE.TIPO_CONVOCACAO_CONCLUINTE
    ).exclude(situacao=RegistroConvocacaoENADE.SITUACAO_DISPENSADO)

    ano = str(convocacao_enade.ano_letivo.ano)[2:4]
    codigo_IES = Configuracao.get_valor_por_chave('edu', 'codigo_mec')
    codigo_projeto = f'{ano}11101'
    codigo_curso = curso.codigo_emec
    data_geracao = datetime.datetime.now().strftime('%d%m%Y')
    nome_arquivo = f'ENADE{codigo_projeto}_N99_BR_{data_geracao}_{codigo_curso}_E001.TXT'

    file_path = os.path.join(settings.TEMP_DIR, nome_arquivo)
    return tasks.download_estudantes_concluintes_avaliacao_teorica(file_path, lista_convocados, codigo_IES, codigo_projeto, codigo_curso)


@rtr()
@permission_required('edu.view_convocacaoenade')
def download_professores_orientadores_avaliacao_pratica(request, convocacao_enade_pk, curso_pk):
    convocacao_enade = get_object_or_404(ConvocacaoENADE, pk=convocacao_enade_pk)
    curso = get_object_or_404(CursoCampus, pk=curso_pk)

    lista_convocados = convocacao_enade.registroconvocacaoenade_set.filter(
        aluno__curso_campus_id=curso.id, tipo_convocacao=RegistroConvocacaoENADE.TIPO_CONVOCACAO_CONCLUINTE_AP
    ).exclude(situacao=RegistroConvocacaoENADE.SITUACAO_DISPENSADO)
    codigo_curso = curso.codigo_emec
    codigo_IES = Configuracao.get_valor_por_chave('edu', 'codigo_mec')

    ano = convocacao_enade.ano_letivo.ano
    ano = str(ano)[2:4]
    codigo_projeto = f'{ano}11101'  # 2 dígitos do ano + 1 dígito de edição do projeto + 2 dígitos do programa + 2 dígitos da etapa
    data_geracao = datetime.datetime.now().strftime('%d%m%Y')
    nome_arquivo = f'ENADE{codigo_projeto}_N99O_BR_{data_geracao}_{codigo_curso}_E001.TXT'

    file_path = os.path.join(settings.TEMP_DIR, nome_arquivo)
    return tasks.download_professores_orientadores_avaliacao_pratica(file_path, lista_convocados, codigo_IES, codigo_projeto, codigo_curso)


@rtr()
@permission_required('edu.view_convocacaoenade')
def download_professores_supervisores_avaliacao_pratica(request, convocacao_enade_pk, curso_pk):
    convocacao_enade = get_object_or_404(ConvocacaoENADE, pk=convocacao_enade_pk)
    curso = get_object_or_404(CursoCampus, pk=curso_pk)

    lista_convocados = convocacao_enade.registroconvocacaoenade_set.filter(
        aluno__curso_campus_id=curso.id, tipo_convocacao=RegistroConvocacaoENADE.TIPO_CONVOCACAO_CONCLUINTE_AP
    ).exclude(situacao=RegistroConvocacaoENADE.SITUACAO_DISPENSADO)
    codigo_curso = curso.codigo_emec
    codigo_IES = Configuracao.get_valor_por_chave('edu', 'codigo_mec')

    ano = convocacao_enade.ano_letivo.ano
    ano = str(ano)[2:4]
    codigo_projeto = f'{ano}11101'  # 2 dígitos do ano + 1 dígito de edição do projeto + 2 dígitos do programa + 2 dígitos da etapa
    data_geracao = datetime.datetime.now().strftime('%d%m%Y')
    nome_arquivo = f'ENADE{codigo_projeto}_N99S_BR_{data_geracao}_{codigo_curso}_E001.TXT'
    file_path = os.path.join(settings.TEMP_DIR, nome_arquivo)
    return tasks.download_professores_supervisores_avaliacao_pratica(file_path, lista_convocados, codigo_IES, codigo_projeto, codigo_curso)


@rtr()
@permission_required('edu.view_convocacaoenade')
def download_estudantes_habilitados_avaliacao_pratica(request, convocacao_enade_pk, curso_pk):
    convocacao_enade = get_object_or_404(ConvocacaoENADE, pk=convocacao_enade_pk)
    curso = get_object_or_404(CursoCampus, pk=curso_pk)

    lista_convocados = convocacao_enade.registroconvocacaoenade_set.filter(
        aluno__curso_campus_id=curso.id, tipo_convocacao=RegistroConvocacaoENADE.TIPO_CONVOCACAO_CONCLUINTE_AP
    ).exclude(situacao=RegistroConvocacaoENADE.SITUACAO_DISPENSADO)
    codigo_curso = curso.codigo_emec
    codigo_IES = Configuracao.get_valor_por_chave('edu', 'codigo_mec')

    ano = convocacao_enade.ano_letivo.ano
    ano = str(ano)[2:4]
    codigo_projeto = f'{ano}11101'  # 2 dígitos do ano + 1 dígito de edição do projeto + 2 dígitos do programa + 2 dígitos da etapa
    data_geracao = datetime.datetime.now().strftime('%d%m%Y')
    nome_arquivo = f'ENADE{codigo_projeto}_N99AP_BR_{data_geracao}_{codigo_curso}_E001.TXT'
    file_path = os.path.join(settings.TEMP_DIR, nome_arquivo)
    return tasks.download_estudantes_habilitados_avaliacao_pratica(file_path, lista_convocados, codigo_IES, codigo_projeto, codigo_curso)


@rtr()
@permission_required('edu.view_convocacaoenade')
def convocados_enade_irregular(request, convocacao_id, diretoria_id, somente_coordenacoes):
    title = 'Concluintes convocados e não integralizados no período'
    hoje = datetime.datetime.today()
    alunos_por_modalidade = []
    for modalidade in (
        ModalidadeConvocacaoENADE.objects.filter(convocacao_enade_id=convocacao_id, data_limite_integralizacao_concluinte__lt=hoje)
        .select_related('modalidade')
        .only('percentual_minimo_concluintes', 'modalidade_id', 'modalidade__descricao')
    ):
        percentual_minimo_concluintes = modalidade.percentual_minimo_concluintes
        qs_registro = RegistroConvocacaoENADE.objects.filter(
            possivel_integralizado=True,
            situacao__isnull=True,
            convocacao_enade_id=convocacao_id,
            aluno__curso_campus__diretoria_id=diretoria_id,
            aluno__curso_campus__modalidade_id=modalidade.modalidade_id,
            percentual_ch_cumprida__lt=percentual_minimo_concluintes,
        )
        if somente_coordenacoes:
            qs_registro = qs_registro.filter(aluno__curso_campus__coordenador__user_id=request.user.id) | qs_registro.filter(
                aluno__curso_campus__coordenador_2__user_id=request.user.id
            )
        if qs_registro.exists():
            alunos_por_modalidade.append([modalidade, qs_registro])

    return locals()
