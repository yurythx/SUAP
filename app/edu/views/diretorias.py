from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.shortcuts import get_object_or_404
from django.utils.safestring import mark_safe

from comum.models import UsuarioGrupo, UsuarioGrupoSetor
from djtools.ui import TabelaHorario, TabelasHorario
from djtools.utils import (
    group_required,
    httprr,
    permission_required,
    rtr,
)
from edu.forms import (
    AdicionarCoordenadorForm,
    AdicionarMembroDiretoriaForm,
    AdicionarAuxiliarSecretariaDiretoriaForm,
    AdicionarEstagiarioDiretoriaForm,
    CoordenadorModalidadeForm,
    CoordenadorRegistroAcademicoForm,
    DataComemorativaForm,
    DefinirCoordenadorCursoForm,
    DefinirCoordenadoresEstagioDocente,
    ImprimirHorariosForm,
    RelatorioHorarioDiarioEspecialForm,
    RelatorioHorarioForm,
    ReplicacaoCalendarioForm,
    SabadoLetivoForm,
    VincularGrupoAtendimentoDiretoria,
)
from edu.models import (
    Aluno,
    CalendarioAcademico,
    CoordenadorModalidade,
    CoordenadorRegistroAcademico,
    CursoCampus,
    DataComemorativa,
    Diretoria,
    HorarioAulaDiario,
    HorarioCampus,
    SabadoLetivo,
)


@login_required()
@rtr()
def calendarioacademico(request, pk):
    obj = get_object_or_404(CalendarioAcademico.locals, pk=pk)
    if not Aluno.objects.filter(matricula=request.user.username).exists() and not request.user.has_perm('edu.view_calendarioacademico'):
        return httprr(request.path, 'Você não tem permissão para acessar este calendário.', 'error')
    calendario = obj.anual()
    title = str(obj)
    is_popup = request.GET.get('_popup')
    pk_remover = request.GET.get('remover_sabado_letivo')
    if pk_remover and request.user.has_perm('edu.change_calendarioacademico'):
        obj.sabadoletivo_set.filter(pk=pk_remover).delete()
        return httprr(request.path, 'Ação realizada com sucesso')
    pk_remover = request.GET.get('remover_data_comemorativa')
    if pk_remover and request.user.has_perm('edu.change_calendarioacademico'):
        obj.datacomemorativa_set.filter(pk=pk_remover).delete()
        return httprr(request.path, 'Ação realizada com sucesso')
    return locals()


@permission_required('edu.change_calendarioacademico')
@rtr()
def replicar_calendario(request, pk):
    title = 'Replicação de Calendário'
    calendario = get_object_or_404(CalendarioAcademico.locals, pk=pk)

    form = ReplicacaoCalendarioForm(data=request.POST or None)
    if form.is_valid():
        resultado = form.processar(calendario)
        return httprr(
            '..',
            mark_safe(
                'Calendário(s) replicado(s) com sucesso. <a href="/admin/edu/calendarioacademico/?id__in={}">Você deseja editá-lo(s)?</a>'.format(
                    ','.join(resultado)
                )
            ),
        )

    return locals()


@permission_required('edu.view_diretoria')
@rtr()
def diretoria(request, pk):
    obj = get_object_or_404(Diretoria, pk=pk)

    title = f'{obj.get_tipo_display()} - {obj!s}'
    dimensoes = []

    dimensao = {'nome': 'Direção', 'grupos': []}
    if obj.is_diretoria_sistemica():
        for name, verbose_name in (
            ('Reitor', 'Reitor'),
            ('Pró-Reitor', 'Pró-Reitores'),
            ('Diretor Acadêmico Sistêmico', 'Diretores Sistêmicos'),
            ('Diretor de Avaliação e Regulação do Ensino', 'Diretores de Avaliação e Regulação do Ensino'),
        ):
            grupo = Group.objects.get(name=name)
            dimensao['grupos'].append(
                {
                    'nome': verbose_name,
                    'membros': UsuarioGrupoSetor.objects.filter(usuario_grupo__group_id=grupo.pk, setor_id=obj.setor.pk),
                    'parametro': grupo.pk,
                    'group': grupo,
                }
            )
    else:
        for name, verbose_name in (('Diretor Geral', 'Diretor Geral'), ('Diretor Acadêmico', 'Diretor Acadêmico')):
            grupo = Group.objects.get(name=name)
            dimensao['grupos'].append(
                {
                    'nome': 'Diretor de Ensino' if obj.is_diretoria_ensino() and name == 'Diretor Acadêmico' else verbose_name,
                    'membros': UsuarioGrupoSetor.objects.filter(usuario_grupo__group_id=grupo.pk, setor_id=obj.setor.pk),
                    'parametro': grupo.pk,
                    'group': grupo,
                }
            )
    dimensoes.append(dimensao)
    tipo_diretor = ['Diretor Acadêmico', 'Diretor de Ensino']

    dimensao = {'nome': 'Coordenação Acadêmica', 'grupos': []}
    if obj.is_diretoria_sistemica():
        for name, verbose_name in (('Coordenador Acadêmico Sistêmico', 'Coordenadores Sistêmicos'),):
            grupo = Group.objects.get(name=name)
            dimensao['grupos'].append(
                {
                    'nome': verbose_name,
                    'membros': UsuarioGrupoSetor.objects.filter(usuario_grupo__group_id=grupo.pk, setor_id=obj.setor.pk),
                    'parametro': grupo.pk,
                    'group': grupo,
                }
            )
    else:
        for name, verbose_name in (('Coordenador de Curso', 'Coordenadores de Curso'),):
            grupo = Group.objects.get(name=name)
            dimensao['grupos'].append(
                {
                    'nome': verbose_name,
                    'membros': UsuarioGrupoSetor.objects.filter(usuario_grupo__group_id=grupo.pk, setor_id=obj.setor.pk),
                    'parametro': grupo.pk,
                    'group': grupo,
                }
            )
    dimensoes.append(dimensao)

    if not obj.is_diretoria_sistemica():
        dimensao = {'nome': 'Secretaria Acadêmica', 'grupos': []}
        for name, verbose_name in (
            ('Secretário Acadêmico', 'Secretários Acadêmicos'),
            ('Auxiliar de Secretaria Acadêmica', 'Auxiliares de Secretaria Acadêmica'),
            ('Apoio Acadêmico', 'Apoio Acadêmico'),
            ('Estagiário', 'Estagiários'),
        ):
            grupo = Group.objects.get(name=name)
            dimensao['grupos'].append(
                {
                    'nome': verbose_name,
                    'membros': UsuarioGrupoSetor.objects.filter(usuario_grupo__group_id=grupo.pk, setor_id=obj.setor.pk),
                    'parametro': grupo.pk,
                    'group': grupo,
                }
            )
        dimensoes.append(dimensao)

        dimensao = {'nome': 'Formatura/Diplomas', 'grupos': []}
        for name, verbose_name in (
            ('Organizador de Formatura', 'Organizadores de Formatura'),
            ('Coordenador de Registros Acadêmicos', 'Responsáveis pela Emissão do Diploma'),
        ):
            grupo = Group.objects.get(name=name)
            dimensao['grupos'].append(
                {
                    'nome': verbose_name,
                    'membros': UsuarioGrupoSetor.objects.filter(usuario_grupo__group_id=grupo.pk, setor_id=obj.setor.pk),
                    'parametro': grupo.pk,
                    'group': grupo,
                }
            )
        dimensoes.append(dimensao)

        dimensao = {'nome': 'Atividades Extensão', 'grupos': []}
        for name, verbose_name in (
            ('Coordenador de Estágio Docente', 'Coordenador de Estágio Docente'),
            ('Organizador de Minicurso', 'Organizador de Minicurso'),
        ):
            grupo = Group.objects.get(name=name)
            dimensao['grupos'].append(
                {
                    'nome': verbose_name,
                    'membros': UsuarioGrupoSetor.objects.filter(usuario_grupo__group_id=grupo.pk, setor_id=obj.setor.pk),
                    'parametro': grupo.pk,
                    'group': grupo,
                }
            )
        dimensoes.append(dimensao)

    dimensao = {'nome': 'Ensino a Distância', 'grupos': []}
    for name, verbose_name in (('Assessor EAD', 'Assessores EAD'),):
        grupo = Group.objects.get(name=name)
        dimensao['grupos'].append(
            {
                'nome': verbose_name,
                'membros': UsuarioGrupoSetor.objects.filter(usuario_grupo__group_id=grupo.pk, setor_id=obj.setor.pk),
                'parametro': grupo.pk,
                'group': grupo,
            }
        )
    dimensoes.append(dimensao)

    dimensao = {'nome': 'Outras Atividades', 'grupos': []}
    for name, verbose_name in (('Pedagogo', 'Pedagogos'),):
        grupo = Group.objects.get(name=name)
        dimensao['grupos'].append(
            {
                'nome': verbose_name,
                'membros': UsuarioGrupoSetor.objects.filter(usuario_grupo__group_id=grupo.pk, setor_id=obj.setor.pk),
                'parametro': grupo.pk,
                'group': grupo,
            }
        )
    if not obj.is_diretoria_sistemica():
        for name, verbose_name in (
            ('Bibliotecário', 'Bibliotecários'),
            ('Comissão de Horários', 'Comissão de Horários'),
            ('Coordenador de Desporto', 'Coordenadores de Atividades Desportivas'),
            ('Coordenador de Laboratório', 'Coordenadores de Laboratório'),
        ):
            grupo = Group.objects.get(name=name)
            dimensao['grupos'].append(
                {
                    'nome': verbose_name,
                    'membros': UsuarioGrupoSetor.objects.filter(usuario_grupo__group_id=grupo.pk, setor_id=obj.setor_id),
                    'parametro': grupo.pk,
                    'group': grupo,
                }
            )

    if obj.is_diretoria_sistemica():
        for name, verbose_name in (
            ('Operador ENADE', 'Operadores ENADE'),
            ('Operador de Censo', 'Operadores de Censo'),
        ):
            grupo = Group.objects.get(name=name)
            dimensao['grupos'].append(
                {
                    'nome': verbose_name,
                    'membros': UsuarioGrupoSetor.objects.filter(usuario_grupo__group_id=grupo.pk, setor_id=obj.setor.pk),
                    'parametro': grupo.pk,
                    'group': grupo,
                }
            )
    dimensoes.append(dimensao)
    is_administrador_academico = request.user.has_group_cached(['Administrador Acadêmico'])

    if request.user.has_perm('edu.delete_diretoria'):
        url = f'/edu/diretoria/{obj.pk}/'

        if 'diretor_geral_id' in request.GET:
            diretor = get_object_or_404(UsuarioGrupo, pk=request.GET['diretor_geral_id'])
            diretorias = Diretoria.objects.filter(setor__uo=obj.setor.uo)
            for diretoria in diretorias:
                diretoria.diretor_geral = diretor.user.get_vinculo()
                diretoria.diretor_geral_exercicio = diretor.user.get_vinculo()
                diretoria.save()
            return httprr(url, 'Diretor geral titular definido com sucesso.')
        if 'diretor_academico_id' in request.GET:
            o = get_object_or_404(UsuarioGrupo, pk=request.GET['diretor_academico_id'])
            obj.diretor_academico = o.user.get_vinculo()
            obj.diretor_academico_exercicio = obj.diretor_academico
            obj.save()
            return httprr(url, 'Diretor acadêmico titular definido com sucesso.')
    if (
        obj.diretor_geral
        and not UsuarioGrupoSetor.objects.filter(
            usuario_grupo__group__name='Diretor Geral', setor_id=obj.setor.pk, usuario_grupo__user_id=obj.diretor_geral.user_id
        ).exists()
    ):
        obj.diretor_geral = None
        obj.save()
    if (
        obj.diretor_academico
        and not UsuarioGrupoSetor.objects.filter(
            usuario_grupo__group__name='Diretor Acadêmico', setor_id=obj.setor.pk, usuario_grupo__user_id=obj.diretor_academico.user_id
        ).exists()
    ):
        obj.diretor_academico = None
        obj.save()
    return locals()


@permission_required('edu.add_diretoria')
@rtr()
def adicionar_membro_diretoria(request, pk, grupo_pk):
    diretoria = get_object_or_404(Diretoria, pk=pk)
    grupo = Group.objects.get(pk=grupo_pk)
    if grupo.name == 'Diretor Acadêmico' and diretoria.is_diretoria_ensino():
        nome = 'Diretor de Ensino'
    else:
        nome = grupo.name
    title = f'Adicionar {nome}'
    form = AdicionarMembroDiretoriaForm(request.POST or None)
    if form.is_valid():
        form.processar(diretoria, grupo)
        return httprr('..', 'Usuário adicionado com sucesso.')
    return locals()


@permission_required('edu.add_termovinculacaousuariodiretoria')
@rtr()
def adicionar_auxiliar_secretaria(request, pk):
    diretoria = get_object_or_404(Diretoria.locals, pk=pk)
    grupo = Group.objects.get(name='Auxiliar de Secretaria Acadêmica')
    title = f'Adicionar {grupo.name}'
    form = AdicionarAuxiliarSecretariaDiretoriaForm(request.POST or None, request=request, diretoria=diretoria)
    if form.is_valid():
        form.processar(grupo)
        return httprr('..', 'Usuário adicionado com sucesso.')
    return locals()


@permission_required('edu.add_termovinculacaousuariodiretoria')
@rtr()
def adicionar_estagiario_secretaria(request, pk):
    diretoria = get_object_or_404(Diretoria.locals, pk=pk)
    grupo = Group.objects.get(name='Estagiário')
    title = f'Adicionar {grupo.name}'
    form = AdicionarEstagiarioDiretoriaForm(request.POST or None, request=request, diretoria=diretoria)
    if form.is_valid():
        form.processar(grupo)
        return httprr('..', 'Usuário adicionado com sucesso.')
    return locals()


@permission_required('edu.add_termovinculacaousuariodiretoria')
@rtr()
def remover_auxiliar_secretaria(request, pk, usuario_grupo_pk):
    diretoria = get_object_or_404(Diretoria.locals, pk=pk)
    usuario_grupo = get_object_or_404(UsuarioGrupo.objects, pk=usuario_grupo_pk, group__name='Auxiliar de Secretaria Acadêmica')
    setor = usuario_grupo.setores.filter(pk=diretoria.setor_id).first()
    if setor:
        usuario_grupo.setores.remove(setor)
    if not usuario_grupo.setores.exists():
        usuario_grupo.delete()
    return httprr(f'/edu/diretoria/{pk}/?tab=secretaria-academica', 'Usuário removido com sucesso.')


@permission_required('edu.add_termovinculacaousuariodiretoria')
@rtr()
def remover_estagiario_secretaria(request, pk, usuario_grupo_pk):
    diretoria = get_object_or_404(Diretoria.locals, pk=pk)
    usuario_grupo = get_object_or_404(UsuarioGrupo.objects, pk=usuario_grupo_pk, group__name='Estagiário')
    setor = usuario_grupo.setores.filter(pk=diretoria.setor_id).first()
    if setor:
        usuario_grupo.setores.remove(setor)
    if not usuario_grupo.setores.exists():
        usuario_grupo.delete()
    return httprr(f'/edu/diretoria/{pk}/?tab=secretaria-academica', 'Usuário removido com sucesso.')


@permission_required('edu.add_diretoria')
@rtr()
def adicionar_coordenador(request, pk, usuario_grupo_id=None):
    title = 'Adicionar Coordenador'
    diretoria = get_object_or_404(Diretoria, pk=pk)
    initial = None
    usuario_grupo = None
    user = None
    if usuario_grupo_id:
        usuario_grupo = get_object_or_404(UsuarioGrupo, pk=usuario_grupo_id)
        user = usuario_grupo.user
    form = AdicionarCoordenadorForm(request.POST or None, diretoria=diretoria, tipo_coordenador=request.GET.get('tipo'), user=user)
    if form.is_valid():
        form.processar(diretoria, usuario_grupo)
        return httprr('..', 'Coordenação alterada com sucesso.')
    return locals()


@rtr()
@permission_required('edu.efetuar_matricula')
def definir_coordenador_curso(request, pk):
    title = 'Definir Coordenador'
    curso_campus = get_object_or_404(CursoCampus, pk=pk)
    form = DefinirCoordenadorCursoForm(request.POST or None, instance=curso_campus)
    if form.is_valid():
        form.processar(curso_campus)
        return httprr('..', 'Coordenador definido com sucesso.')
    return locals()


@rtr()
@permission_required('edu.gerar_turmas')
def imprimir_horarios(request):
    title = 'Imprimir Horários'
    form = ImprimirHorariosForm(data=request.GET or None, request=request)
    if form.is_valid():
        tabelas = TabelasHorario(request=request)
        turmas = form.processar()
        for turma in turmas:
            horarios_campus = HorarioCampus.objects.filter(diario__in=turma.diario_set.all()).distinct()
            for horario_campus in horarios_campus:
                tabela = TabelaHorario(export_to_pdf=False, request=request)
                tabela.titulo = f'{turma} - {horario_campus.descricao}'
                horarios_disponiveis = horario_campus.horarioaula_set.all() or []
                for horario in horarios_disponiveis:
                    tabela.adicionar_horario(horario.turno.descricao, horario.inicio, horario.termino)
                horarios = HorarioAulaDiario.objects.filter(diario__turma=turma, diario__horario_campus=horario_campus)
                for horario in horarios:
                    laboratorio = f' Laboratório: {horario.diario.local_laboratorio};' if horario.diario.local_laboratorio else ''
                    hint = f'Componente: {horario.diario.componente_curricular.componente.descricao}; Professor(es): {horario.diario.get_nomes_professores()}; Sala: {horario.diario.local_aula};{laboratorio}'
                    tabela.adicionar_registro(horario.diario.componente_curricular.componente.sigla, horario.get_horario_formatado(), '', hint)
                tabelas.adicionar(tabela)
        return tabelas.as_pdf()
    return locals()


@rtr()
@permission_required('edu.view_horarioauladiario')
def relatorio_horario(request):
    title = 'Listagem de Horários'
    form = RelatorioHorarioForm(data=request.GET or None, user=request.user)
    if form.is_valid():
        tabelas = TabelasHorario(request=request)
        horarios = form.processar()
        tabela = TabelaHorario(export_to_pdf=True, request=request)
        tabela.filtros = horarios.filtros
        horarios_disponiveis = horarios.exists() and horarios.first().diario.horario_campus.horarioaula_set.all() or []
        for horario in horarios_disponiveis:
            tabela.adicionar_horario(horario.turno.descricao, horario.inicio, horario.termino)
        for horario in horarios:
            laboratorio = f' Laboratório: {horario.diario.local_laboratorio};' if horario.diario.local_laboratorio else ''
            hint = f'Componente: {horario.diario.componente_curricular.componente.descricao}; Professor(es): {horario.diario.get_nomes_professores()}; Sala: {horario.diario.local_aula};{laboratorio}'
            link = not request.GET.get('pdf') and f'/edu/diario/{horario.diario.pk}' or ''
            tabela.adicionar_registro(horario.diario.componente_curricular.componente.sigla, horario.get_horario_formatado(), link, hint)
        tabelas.adicionar(tabela)
        if request.GET.get('pdf'):
            return tabelas.as_pdf()

    return locals()


@rtr()
@permission_required('edu.view_horarioauladiarioespecial')
def relatorio_horario_especial(request):
    title = 'Listagem de Horários (Atividades Específicas)'
    form = RelatorioHorarioDiarioEspecialForm(data=request.GET or None, user=request.user)
    if form.is_valid():
        horarios = form.processar()
        tabelas = TabelasHorario(request=request)
        tabela = TabelaHorario(export_to_pdf=True, request=request)
        tabela.filtros = horarios.filtros
        horarios_disponiveis = horarios.exists() and horarios.first().diario_especial.horario_campus.horarioaula_set.all() or []
        for horario in horarios_disponiveis:
            tabela.adicionar_horario(horario.turno.descricao, horario.inicio, horario.termino)
        for horario in horarios:
            hint = f'Componente: {horario.diario_especial.componente.descricao}; Professor(es): {horario.diario_especial.get_nomes_professores()}; Sala: {horario.diario_especial.sala};'
            link = not request.GET.get('pdf') and f'/edu/diarioespecial/{horario.diario_especial.pk}' or ''
            tabela.adicionar_registro(horario.diario_especial.componente.sigla, horario.get_horario_formatado(), link, hint)
        tabelas.adicionar(tabela)
        if request.GET.get('pdf'):
            return tabelas.as_pdf()

    return locals()


@rtr()
@permission_required('edu.change_diretoria')
def adicionar_coordenador_registro_academico(request, pk_diretoria, pk_membro=None):
    diretoria = Diretoria.objects.get(pk=pk_diretoria)
    coordenador = None

    if pk_membro:
        usuario_grupo = get_object_or_404(UsuarioGrupo, pk=pk_membro)
        servidor = usuario_grupo.user.get_vinculo().relacionamento
        qs_coordenador = CoordenadorRegistroAcademico.objects.filter(diretoria=diretoria, servidor=servidor)

        if qs_coordenador.exists():
            coordenador = qs_coordenador.first()

    title = 'Gerenciar responsável pela emissão do diploma'
    form = CoordenadorRegistroAcademicoForm(data=request.POST or None, instance=coordenador, diretoria=diretoria)
    if form.is_valid():
        coordenador = form.save(False)
        coordenador.diretoria = diretoria
        coordenador.save()
        return httprr('..', 'Responsável pela Emissão do Diploma cadastrado/atualizado com sucesso.')
    return locals()


@rtr()
@permission_required('edu.change_diretoria')
def remover_coordenador_registro_academico(request, pk_diretoria, pk_membro):
    diretoria = Diretoria.objects.get(pk=pk_diretoria)
    diretoria.remover_cra(pk_membro)
    return httprr(f'/edu/diretoria/{diretoria.pk}/?tab=3', 'Responsável pela Emissão do Diploma removido com sucesso')


@rtr()
@permission_required('edu.change_diretoria')
def adicionar_coordenador_modalidade(request, pk_diretoria, pk_coordenador):
    diretoria = Diretoria.objects.get(pk=pk_diretoria)
    coordenador = int(pk_coordenador) and CoordenadorModalidade.objects.get(pk=pk_coordenador) or None
    title = 'Adicionar Coordenador de Modalidade de Ensino'
    form = CoordenadorModalidadeForm(data=request.POST or None, instance=coordenador, diretoria=diretoria)
    if form.is_valid():
        coordenador = form.save(False)
        coordenador.diretoria = diretoria
        coordenador.save()
        coordenador.modalidades.set(form.cleaned_data.get('modalidades'))
        coordenador.save()
        return httprr('..', 'Coordenador de registro acadêmico cadastrado/atualizado com sucesso.')
    return locals()


@rtr()
@permission_required('edu.change_calendarioacademico')
def adicionar_sabado_letivo(request, pk, pki=None):
    title = 'Sábado Letivo'
    obj = get_object_or_404(CalendarioAcademico, pk=pk)
    instance = SabadoLetivo.objects.filter(pk=pki).first() or SabadoLetivo()
    form = SabadoLetivoForm(data=request.POST or None, request=request, instance=instance, calendario_academico=obj)
    if form.is_valid():
        form.save()
        return httprr('..', 'Ação realizada com sucesso.')
    return locals()


@rtr()
@permission_required('edu.change_calendarioacademico')
def adicionar_data_comemorativa(request, pk, pki=None):
    title = 'Data Comemorativa'
    obj = get_object_or_404(CalendarioAcademico, pk=pk)
    instance = DataComemorativa.objects.filter(pk=pki).first() or DataComemorativa()
    form = DataComemorativaForm(data=request.POST or None, request=request, instance=instance, calendario_academico=obj)
    if form.is_valid():
        form.instance.calendario_academico = obj
        form.save()
        return httprr('..', 'Ação realizada com sucesso.')
    return locals()


@rtr()
@group_required('Administrador Acadêmico,Diretor Acadêmico,Secretário Acadêmico,Coordenador de Curso')
def definir_coordenador_estagio_docente(request, pk):
    title = 'Definir Coordenadores de Estágio Docente'
    curso_campus = get_object_or_404(CursoCampus, pk=pk)
    form = DefinirCoordenadoresEstagioDocente(request.POST or None, instance=curso_campus)
    if form.is_valid():
        form.save()
        return httprr('..', 'Coordenadores de Estágio Docente definidos com sucesso.')
    return locals()


@rtr()
@group_required('Administrador Acadêmico')
def vincular_grupo_atendimento_diretoria(request, pk):
    obj = get_object_or_404(Diretoria, pk=pk)
    title = 'Vincular Grupo de Atendimento'
    form = VincularGrupoAtendimentoDiretoria(data=request.POST or None, instance=obj)
    if form.is_valid():
        form.save()
        return httprr('..', 'Grupo de atendimento vinculado com sucesso.')
    return locals()
