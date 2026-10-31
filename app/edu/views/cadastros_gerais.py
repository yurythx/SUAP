import io
import tempfile

import qrcode
from django.apps import apps
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from django.utils.safestring import mark_safe

from comum.models import Ano, Configuracao, UsuarioGrupoSetor
from djtools.utils import (
    PDFResponse,
    gerar_documento_impressao,
    group_required,
    httprr,
    permission_required,
    rtr,
)
from edu import utils
from edu.forms import MonitoramentoEntregaDiariosForm, MonitoramentoFechamentoPeriodoForm, ReplicacaoHorarioCampusForm, VincularProfessorNCEForm
from edu.models import (
    CursoCampus,
    Diretoria,
    HorarioAula,
    HorarioCampus,
    Matriz,
    ModeloDocumento,
    NucleoCentralEstruturante,
    PeriodoLetivoAtualSecretario,
    Professor,
    SolicitacaoCertificadoENEM,
    TipoComponente,
)


@permission_required('edu.view_horariocampus')
@rtr()
def horariocampus(request, pk):
    obj = get_object_or_404(HorarioCampus.locals, pk=pk)
    horarios_aula = HorarioAula.objects.filter(horario_campus=obj.pk)
    title = str(obj)
    return locals()


@permission_required('edu.add_horariocampus')
@rtr()
def replicar_horariocampus(request, pk):
    title = 'Replicação de Horário'
    horario_campus = get_object_or_404(HorarioCampus.locals, pk=pk)
    form = ReplicacaoHorarioCampusForm(data=request.POST or None)
    if request.POST and form.is_valid():
        try:
            resultado = form.processar(horario_campus)
            return httprr(
                '..', mark_safe(f'Horário replicado com sucesso. <a href="/admin/edu/horariocampus/{resultado.pk}/">Você deseja editá-lo?</a>')
            )
        except ValidationError as e:
            return httprr('..', f'Não foi possível replicar o horário: {e.messages[0]}', 'error')
    return locals()


@permission_required('edu.add_tipocomponente')
@rtr()
def tipo_componente(request, pk):
    title = 'Tipo de Componente'
    obj = get_object_or_404(TipoComponente, pk=pk)
    componentes = obj.componente_set.all()
    return locals()


@permission_required('edu.view_nucleocentralestruturante')
@rtr()
def nucleocentralestruturante(request, pk):
    obj = get_object_or_404(NucleoCentralEstruturante, pk=pk)
    title = obj.descricao
    if 'del' in request.GET and request.user.has_perm('edu.change_professor'):
        professor = Professor.objects.get(pk=request.GET['del'])
        obj.professor_set.remove(professor)
        obj.save()
        return httprr(f'/edu/nucleocentralestruturante/{pk}/', 'Professor removido com sucesso.')
    return locals()


@permission_required('edu.change_professor')
@rtr()
def vincular_professor_nce(request, pk):
    obj = get_object_or_404(NucleoCentralEstruturante, pk=pk)
    form = VincularProfessorNCEForm(request.POST or None, request=request, nce=obj)
    if form.is_valid():
        form.processar()
        return httprr(f'/edu/nucleocentralestruturante/{pk}/', 'Professor(es) adicionado(s) com sucesso.', close_popup=True)
    return locals()


@login_required()
@rtr()
def visualizar(request, app, modelo, pk):
    if not request.user.has_perm(f'{app}.view_{modelo}'):
        return httprr('..', 'Você não tem permissão para realizar isso.', 'error')

    classe = apps.get_model(app, modelo)
    objeto = get_object_or_404(classe, pk=pk)
    metadata = utils.metadata(objeto)
    title = objeto
    return locals()


def contexto_painel_controle(request):
    title = 'Painel de Controle'
    periodo_letivo_atual = PeriodoLetivoAtualSecretario.get_instance(request)
    diretorias = Diretoria.locals.all()
    diretoria_ids = '%3B'.join(str(x) for x in diretorias.values_list('id', flat=True))
    diretorias_com_pendencia = []
    ano_letivo = None
    user = request.user
    if Ano.objects.filter(ano=periodo_letivo_atual.ano).exists():
        ano_letivo = Ano.objects.get(ano=periodo_letivo_atual.ano)
        cleaned_data = {'ano_letivo': ano_letivo, 'periodo_letivo': periodo_letivo_atual.periodo, 'diretorias': diretorias}
        matriculas_periodos, graficos1 = MonitoramentoFechamentoPeriodoForm(request.GET or None, request=request).processar(cleaned_data)
        professores_diario, graficos2 = MonitoramentoEntregaDiariosForm(request.GET or None, request=request).processar(
            com_grafico=False, cleaned_data=cleaned_data
        )

        for diretoria in diretorias:
            is_coordenador_curso = UsuarioGrupoSetor.objects.filter(
                usuario_grupo__user=user, setor_id=diretoria.setor_id, usuario_grupo__group__name='Coordenador de Curso'
            ).exists()
            outros_grupos = [
                'Coordenador de Curso',
                'Coordenador de Modalidade Acadêmica',
                'Secretário Acadêmico',
                'Diretor Acadêmico',
                'Diretor Geral',
            ]
            is_outros = UsuarioGrupoSetor.objects.filter(
                usuario_grupo__user=user, setor_id=diretoria.setor_id, usuario_grupo__group__name__in=outros_grupos
            ).exists()

            if is_coordenador_curso:
                import copy

                diretoria2 = copy.copy(diretoria)
                diretoria2.pendencias = diretoria.get_pendencias(periodo_letivo_atual.ano, periodo_letivo_atual.periodo, request.user, True)
                if diretoria2.pendencias:
                    diretoria2.title = f'Pendências da {diretoria2} sob minha coordenação'
                    diretorias_com_pendencia.append(diretoria2)

            if is_outros or user.has_perm('comum.is_administrador_academico') or user.has_perm('comum.is_procurador_institucional'):
                diretoria.pendencias = diretoria.get_pendencias(periodo_letivo_atual.ano, periodo_letivo_atual.periodo, request.user, False)
                if diretoria.pendencias:
                    diretoria.title = f'Pendências da {diretoria}'
                    diretorias_com_pendencia.append(diretoria)

    painel = []
    box_matriz = []
    if request.user.has_perm('edu.add_matriz'):
        contador = Matriz.objects.vazias().count()
        if contador:
            box_matriz.append(('Vazias', '/admin/edu/matriz/?tab=tab_vazias', f'{contador}'))
        contador = Matriz.objects.incompletas().count()
        if contador:
            box_matriz.append(('Incompletas', '/admin/edu/matriz/?tab=tab_incompletas', f'{contador}'))
        if box_matriz:
            painel.append(('Matrizes com Pendência', box_matriz, 'matriz'))

    box_acesso_rapido = []
    box_acesso_rapido.append(('Aluno', '/edu/redirecionar_aluno/', 0, 'popup'))
    box_acesso_rapido.append(('Diário', '/edu/redirecionar_diario/', 0, 'popup'))
    box_acesso_rapido.append(('Matriz', '/edu/redirecionar_matriz/', 0, 'popup'))
    box_acesso_rapido.append(('Calendário Acadêmico', '/edu/redirecionar_calendario/', 0, 'popup'))
    painel.append(('Acesso Rápido', box_acesso_rapido, 'busca'))

    box_relatorio = []
    box_relatorio.append(('Listagem de Alunos', '/edu/relatorio/', 0))
    box_relatorio.append(('Listagem de Professores', '/edu/relatorio_professor/', 0))
    box_relatorio.append(('Listagem de Diários', '/edu/relatorio_diario/', 0))
    box_relatorio.append(('Relatório de Faltas', '/edu/relatorio_faltas/', 0))
    if Configuracao.get_valor_por_chave('edu', 'relatorio_inconsistencia_descentralizado'):
        box_relatorio.append(('Relatório de Inconsistências', '/edu/inconsistencias/', 0))
    if ano_letivo:
        box_relatorio.append(
            (
                'Estatísticas',
                f'/edu/estatistica/?situacao_matricula_periodo=4&agrupar=Curso&apartir_do_ano={ano_letivo.pk}&curso_campus=&ano_periodo=por_periodo_letivo',
                0,
            )
        )
    painel.append(('Relatórios e Estatísticas', box_relatorio, 'protocolo'))

    box_documento_aluno = []
    box_documento_aluno.append(('Imprimir Histórico Final', '/edu/imprimir_historico/final/', 0, 'popup'))
    box_documento_aluno.append(('Imprimir Histórico Final em Lote', '/edu/imprimir_historico_em_lote/', 0))
    box_documento_aluno.append(('Imprimir Boletim', '/edu/imprimir_boletim_aluno/', 0, 'popup'))

    painel.append(('Emissão de Documentos', box_documento_aluno, 'edu'))

    if request.user.has_perm('edu.add_diretoria'):
        box_diretoria = []
        contador = Diretoria.locals.sem_diretores().count()
        if contador:
            box_diretoria.append(('Sem diretores', '/admin/edu/diretoria/?tab=tab_sem_diretores', f'{contador}'))
        contador = Diretoria.locals.sem_secretarios().count()
        if contador:
            box_diretoria.append(('Sem secretários', '/admin/edu/diretoria/?tab=tab_sem_secretarios', f'{contador}'))
        contador = Diretoria.locals.sem_coordenadores().count()
        if contador:
            box_diretoria.append(('Sem coordenadores', '/admin/edu/diretoria/?tab=tab_sem_coordenadores', f'{contador}'))
        contador = Diretoria.locals.sem_pedagogos().count()
        if contador:
            box_diretoria.append(('Sem pedagogos', '/admin/edu/diretoria/?tab=tab_sem_pedagogos', f'{contador}'))
        if box_diretoria:
            painel.append(('Diretoria', box_diretoria, 'departamento'))

    box_processamento_periodo = []
    box_processamento_periodo.append(('Efetuar Matrícula Direta', '/edu/efetuar_matricula/', 0))
    box_processamento_periodo.append(('Fechar Período', '/edu/fechar_periodo_letivo/', 0))
    if request.user.has_group_cached('Administrador Acadêmico'):
        box_processamento_periodo.append(('Abrir Período', '/edu/abrir_periodo_letivo/', 0))
    painel.append(('Procedimentos', box_processamento_periodo, 'protocolo'))

    if request.user.has_perm('edu.change_solicitacaocertificadoenem'):
        box_certificado_enem = []
        contador = SolicitacaoCertificadoENEM.objects.filter(data_avaliacao__isnull=True).count()
        if contador:
            box_certificado_enem.append(('Solicitações Pendentes', '/admin/edu/solicitacaocertificadoenem/?tab=tab_pendentes', contador))
            painel.append(('Certificado ENEM', box_certificado_enem, 'protocolo'))

    if request.user.has_perm('edu.add_cursocampus'):
        box_cursos = []
        contador = CursoCampus.locals.sem_coordenadores().count()
        if contador:
            box_cursos.append(('Sem Coordenadores', '/admin/edu/cursocampus/?tab=tab_sem_coordenadores', f'{contador}'))
        contador = CursoCampus.locals.nao_vinculados_diretoria().count()
        if contador:
            box_cursos.append(('Não-Vinculados à Diretoria', '/admin/edu/cursocampus/?tab=nao_vinculados_diretoria', f'{contador}'))
        if box_cursos:
            painel.append(('Cursos com Pendência', box_cursos, 'curso'))

    return locals()


@rtr()
@group_required(
    'Coordenador de Curso,Coordenador de Modalidade Acadêmica,Secretário Acadêmico,Administrador Acadêmico,Diretor Acadêmico,Diretor Geral, Procurador Institucional'
)
def painel_controle(request):
    return contexto_painel_controle(request)


@permission_required('edu.view_modelodocumento')
@rtr()
def modelo_documento(request, pk):
    obj = get_object_or_404(ModeloDocumento, pk=pk)
    title = obj.descricao
    url_suap = settings.SITE_URL
    if 'preview' in request.GET:
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
            qr_code_path = temp_file.name
        img = qrcode.make(url_suap)
        img.save(qr_code_path)
        dicionario = {
            '#CHGERAL#': '50',
            '#CHESPECIAL#': '10',
            '#CHESTAGIO#': '10',
            '#CH_AULA#': '10',
            '#EMPRESAESTAGIO#': '10',
            '#LEI#': 'Lei 01/1900',
            '#NOMECAMPUS#': 'Campus Central',
            '#ALUNO#': 'João Maria da Silva',
            '#NOME#': 'João Maria da Silva',
            '#NOMESOCIAL#': 'João Maria da Silva',
            '#NOMEREGISTRO#': 'João Maria da Silva',
            '#CREDENCIAMENTO#': '0001/1900',
            '#RECREDENCIAMENTO#': '0002/1900',
            '#COLACAO#': '01/01/1900',
            '#COLACAOEXTENSO#': '01 de Janeiro de 1900',
            '#NACIONALIDADE#': 'Brasileira',
            '#NATURALIDADE#': 'Natal/RN',
            '#DATANASCIMENTO#': '01/01/1900',
            '#TIPODOC#': 'CPF',
            '#NUMERODOC#': '111.111.111-11',
            '#CPF#': '111.111.111-11',
            '#PASSAPORTE#': '',
            '#RG#': '11.111',
            '#UFRG#': 'RN',
            '#EMISSORRG#': 'ITEP',
            '#DATARG#': '01/01/1900',
            '#CURSO#': 'Informática Básica',
            '#CURSOEMEC#': '1111111',
            '#NUMEROSERIE#': '1',
            '#AREACAPES#': 'CIÊNCIAS EXATAS E DA TERRA',
            '#HABILITACAOPEDAGOGICA#': 'Sistemas',
            '#AREACONCENTRACAO#': 'Tecnologia',
            '#PROGRAMA#': 'Programa Básico',
            '#INICIO#': '01/01/1900',
            '#INICIOEXTENSO#': '01 de Janeiro de 1900',
            '#INICIOLETIVO#': '01/01/1900',
            '#FIM#': '01/01/1900',
            '#FIMEXTENSO#': '01 de Janeiro de 1900',
            '#TITULO#': 'Técnico em Informática',
            '#CHTOTAL#': '50',
            '#CIDADE#': 'Natal',
            '#UF#': 'RN',
            '#DATA#': '01/01/1900',
            '#COORDENADOR#': 'Pedro da Silva',
            '#AREA#': 'Tecnologia',
            '#EIXOTECNOLOGICO#': 'Informação e Comunicação',
            '#MODALIDADE#': 'Tecnólogo',
            '#TITULOCOORDENADOR#': 'coordenador',
            '#OREITOR#': 'Mauro Silva',
            '#REITOR#': 'Maria de Fática',
            '#TITULOREITOR#': 'reitora',
            '#EMEXERCICIO#': '',
            '#DIRETORGERAL#': 'Manoel Bandeira',
            '#TITULODIRETORGERAL#': 'diretor geral',
            '#DIRETORACADEMICO#': 'Roberto Carlos',
            '#TITULODIRETORACADEMICO#': 'diretor acadêmico',
            '#DISCIPLINAS#': 'Programação',
            '#PROFESSORES#': 'Maria Emília',
            '#TITULACOES#': 'Doutora',
            '#NOTAS#': '100',
            '#CH#': '50',
            '#REGISTRO#': '123',
            '#LIVRO#': '1',
            '#FOLHA#': '1',
            '#DATAEXPEDICAO#': '01/01/1900',
            '#PROCESSO#': '123.456.789',
            '#CODIGOVERIFICADOR#': 'abcdef',
            '#NASCIDO#': 'nascido',
            '#PORTADOR#': '',
            '#DIPLOMADO#': 'João Maria da Silva',
            '#AUTORIZACAO#': '123456/1900',
            '#RECONHECIMENTO#': '123456/1900',
            '#DIATCC#': '01/01/1900',
            '#MESTCC#': 'janeiro',
            '#ANOTCC#': '1900',
            '#TIPOTCC#': 'trabalho de concluão de curso',
            '#TEMATCC#': 'Algorítmos na prática',
            '#ORIENTADOR#': 'Joaqui Barbosa',
            '#TITULACAOORIENTADOR#': 'Doutor',
            '#CHTCC#': '10',
            '#NOTATCC#': '100',
            '#VIA#': '1',
            '#SERVIDORREGISTROESCOLAR#': 'Juliana Mendes',
            '#PORTARIAREGISTROESCOLAR#': '123/1900',
            '#NOMEPAI#': 'Joaqui da Silva',
            '#NOMEMAE#': 'Ruth Oliveira da Silva',
            '#ANOCONCLUSAOFIC#': '1900',
            '#OBSINTEGRALIZACAO#': 'Observação',
            '#AUTENTICACAOSISTEC#': '123-456-789',
            '#HABILITACAO#': 'Sistemas',
            '#COORDENADORREGISTROESCOLAR#': 'Flávio de Sá',
        }
        dicionario['#URLXML#'] = url_suap
        dicionario['#CODIGOVALIDACAO#'] = 'abcdef'
        dicionario['#URLVALIDACAO#'] = url_suap
        caminho_arquivo = gerar_documento_impressao(dicionario, io.BytesIO(obj.template.read()), pdfa=True, imagem_path=qr_code_path)
        return PDFResponse(open(caminho_arquivo, 'rb').read())
    return locals()
