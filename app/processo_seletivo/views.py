import datetime
from xml.dom import minidom

import pandas as pd
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404

from ae.models import Participacao
from comum.models import Configuracao, UsuarioGrupoSetor
from comum.utils import get_uo
from djtools import layout
from djtools.templatetags.filters import format_, in_group
from djtools.utils import (
    CsvResponse,
    JsonResponse,
    XlsResponse,
    httprr,
    normalizar_nome_proprio,
    permission_required,
    render_to_string,
    rtr,
    somar_dias,
)
from edu.models import CoordenadorPolo, CursoCampus, Diretoria
from processo_seletivo.forms import (
    CorrigirQuantidadeVagaRemanescenteForm,
    CriacaoClassificacaoForm,
    CriacaoVagaRemanescenteForm,
    DefinirConfiguracaoMigracaoVagaForm,
    DefinirPrecedenciaMatriculaForm,
    EditalAusentarCandidatosForm,
    EditalLiberacaoForm,
    EditarOfertaVagaCursoForm,
    ImportarEditalCSVForm,
    ImportarEditalForm,
    ImportarEditalXMLForm,
    InscricaoFiscalForm,
    ListaForm,
    MatricularAlunoProitecForm,
    MigrarVagaPoloForm,
    ParticipacaoBancaForm,
    PrecedenciaMigracaoForm,
    RealizarAcaoLote,
    VincularMatriculaForm,
)
from processo_seletivo.models import (
    Candidato,
    CandidatoVaga,
    ConfiguracaoMigracaoVaga,
    CriacaoVagaRemanescente,
    Edital,
    EditalAdesaoCampus,
    EditalPeriodoLiberacao,
    EditalPeriodoLiberacaoHistorico,
    InscricaoFiscal,
    Lista,
    NotificacaoMatricula,
    OfertaVaga,
    OfertaVagaCurso,
    PrecedenciaMigracao,
)
from rh.models import UnidadeOrganizacional

from . import tasks


@layout.inscricao()
def index_inscricoes(request):
    inscricoes = []

    for edital in EditalAdesaoCampus.editais_abertos(request.user):
        inscricoes.append(
            {'url': f'/processo_seletivo/inscricao_em_edital/{edital.pk}', 'titulo': f'Inscrição para Fiscal de Concurso para Edital: {edital}'}
        )

    return inscricoes


@rtr()
@permission_required('processo_seletivo.add_edital')
def importar_edital_xml(request, pk):
    title = 'Importar Edital - XML'
    obj = get_object_or_404(Edital, pk=pk)
    form = ImportarEditalXMLForm(data=request.POST or None, files=request.POST and request.FILES or None)
    if form.is_valid():
        return form.processar(obj)
    return locals()


@rtr()
@permission_required('processo_seletivo.add_edital')
def importar_edital_csv(request, pk):
    title = 'Importar Edital - CSV'
    obj = get_object_or_404(Edital, pk=pk)
    form = ImportarEditalCSVForm(data=request.POST or None, files=request.POST and request.FILES or None)
    if form.is_valid():
        return form.processar(obj)
    return locals()


@rtr()
@permission_required('processo_seletivo.add_edital')
def importar_edital(request):
    title = 'Importar Edital'
    form = ImportarEditalForm(request.POST or None)
    if form.is_valid():
        edital = form.editais_disponiveis_webservices[form.cleaned_data['edital']]
        return form.processar(request)
    return locals()


@rtr()
@permission_required('processo_seletivo.change_candidato')
def atualizar_aprovacoes_candidatos(request, pk):
    edital = get_object_or_404(Edital, pk=pk)
    redirect_url = f'/processo_seletivo/edital/{edital.pk}/'

    if not edital.webservice or not edital.webservice.url_edital:
        return httprr(redirect_url, 'O edital não possui webservice configurado.', tag='error')

    try:
        xml = edital.webservice.edital_bruto(edital.codigo)
    except Exception as exc:  # pragma: no cover - dependência externa
        return httprr(redirect_url, f'Erro ao consultar o webservice: {exc}', tag='error')

    if not xml:
        return httprr(redirect_url, 'O webservice não retornou informações para atualização.', tag='error')

    try:
        import re

        xml_sanitizado = re.sub(r'&(?!#?[0-9a-zA-Z]+;)', '&amp;', xml)
        doc = minidom.parseString(xml_sanitizado)
    except Exception as exc:
        return httprr(redirect_url, f'Erro ao processar o XML retornado: {exc}', tag='error')

    candidatos_xml = doc.getElementsByTagName('candidato')
    if not candidatos_xml:
        return httprr(redirect_url, 'Nenhum candidato foi encontrado no webservice.', tag='error')

    field_map = {
        'aprovado_heteroidentificacao': 'aprovado-heteroidentificacao',
        'aprovado_quilombola': 'aprovado-quilombola',
        'aprovado_escola_publica': 'aprovado-escola-publica',
        'aprovado_baixa_renda': 'aprovado-baixa-renda',
        'aprovado_deficiencia': 'aprovado-deficiencia',
    }

    field_labels = {
        'aprovado_heteroidentificacao': 'Heteroidentificação',
        'aprovado_quilombola': 'Quilombola',
        'aprovado_escola_publica': 'Escola pública',
        'aprovado_baixa_renda': 'Baixa renda',
        'aprovado_deficiencia': 'Deficiência',
    }

    def formatar_situacao(valor):
        if valor is True:
            return 'Aprovado'
        if valor is False:
            return 'Reprovado'
        return 'Sem avaliação'

    def extrair_booleano(node, tag):
        elementos = node.getElementsByTagName(tag)
        if not elementos:
            return None
        primeiro = elementos[0].firstChild
        if not primeiro:
            return None
        valor = primeiro.nodeValue.strip().lower()
        if valor in ('sim', 's', 'true', '1'):
            return True
        if valor in ('não', 'nao', 'n', 'false', '0'):
            return False
        return None

    dados_por_inscricao = {}
    for candidato_xml in candidatos_xml:
        inscricao_nodes = candidato_xml.getElementsByTagName('inscricao')
        if not inscricao_nodes or not inscricao_nodes[0].firstChild:
            continue
        inscricao = inscricao_nodes[0].firstChild.nodeValue
        dados_por_inscricao[inscricao] = {campo: extrair_booleano(candidato_xml, tag) for campo, tag in field_map.items()}

    if not dados_por_inscricao:
        return httprr(redirect_url, 'Nenhum dado de aprovação foi localizado para atualização.', tag='error')

    candidatos = list(Candidato.objects.filter(edital=edital, inscricao__in=dados_por_inscricao.keys()))
    inscricoes_existentes = {candidato.inscricao for candidato in candidatos}
    inscricoes_nao_encontradas = sorted(set(dados_por_inscricao.keys()) - inscricoes_existentes)

    def resumir(valores):
        return {
            'aprovados': sum(1 for valor in valores if valor is True),
            'reprovados': sum(1 for valor in valores if valor is False),
            'pendentes': sum(1 for valor in valores if valor is None),
        }

    resumo_antes = {campo: resumir([getattr(candidato, campo) for candidato in candidatos]) for campo in field_map}

    valores_depois_por_campo = {campo: [] for campo in field_map}
    transicoes_por_campo = {campo: {} for campo in field_map}
    plano = []
    campos_alterados = set()

    for candidato in candidatos:
        dados = dados_por_inscricao.get(candidato.inscricao)
        if not dados:
            for campo in field_map:
                valores_depois_por_campo[campo].append(getattr(candidato, campo))
            continue

        alteracoes = {}
        for campo in field_map:
            novo_valor = dados.get(campo)
            valor_atual = getattr(candidato, campo)
            valor_final = valor_atual if novo_valor is None else novo_valor
            valores_depois_por_campo[campo].append(valor_final)
            if novo_valor is not None and valor_final != valor_atual:
                alteracoes[campo] = valor_final
                chave_transicao = (formatar_situacao(valor_atual), formatar_situacao(valor_final))
                transicoes_por_campo[campo][chave_transicao] = transicoes_por_campo[campo].get(chave_transicao, 0) + 1
        if alteracoes:
            plano.append({'candidato': candidato, 'alteracoes': alteracoes})
            campos_alterados.update(alteracoes.keys())

    resumo_depois = {campo: resumir(valores_depois_por_campo[campo]) for campo in field_map}

    detalhes_por_candidato = []
    for item in plano:
        candidato = item['candidato']
        movimentacoes = []
        for campo, valor_novo in item['alteracoes'].items():
            valor_antes = getattr(candidato, campo)
            movimentacoes.append(
                {
                    'label': field_labels[campo],
                    'antes': formatar_situacao(valor_antes),
                    'depois': formatar_situacao(valor_novo),
                }
            )
        if movimentacoes:
            detalhes_por_candidato.append(
                {
                    'candidato': candidato,
                    'inscricao': candidato.inscricao,
                    'movimentacoes': movimentacoes,
                }
            )

    transicoes_resumo = []
    for campo in field_map:
        transicoes = []
        for (origem, destino), quantidade in sorted(transicoes_por_campo[campo].items()):
            transicoes.append({'de': origem, 'para': destino, 'quantidade': quantidade})
        transicoes_resumo.append({'label': field_labels[campo], 'transicoes': transicoes})

    if request.method == 'POST':
        if not plano:
            return httprr(redirect_url, 'Não há alterações a serem aplicadas.')

        candidatos_para_atualizar = []
        for item in plano:
            candidato = item['candidato']
            for campo, valor in item['alteracoes'].items():
                setattr(candidato, campo, valor)
            candidatos_para_atualizar.append(candidato)

        if candidatos_para_atualizar and campos_alterados:
            Candidato.objects.bulk_update(candidatos_para_atualizar, sorted(campos_alterados))

        linhas_resumo = []
        for campo in field_map:
            antes = resumo_antes[campo]
            depois = resumo_depois[campo]
            linhas_resumo.append(
                f'{field_labels[campo]}: Aprovado {antes["aprovados"]}, Reprovado {antes["reprovados"]}, Sem avaliação {antes["pendentes"]} -> '
                f'Aprovado {depois["aprovados"]}, Reprovado {depois["reprovados"]}, Sem avaliação {depois["pendentes"]}'
            )

        mensagem = f'Aprovações atualizadas para {len(plano)} candidato(s).'
        if inscricoes_nao_encontradas:
            mensagem += f' {len(inscricoes_nao_encontradas)} inscrição(ões) não foram localizadas no SUAP.'
        if linhas_resumo:
            mensagem += ' Resumo: ' + ' | '.join(linhas_resumo)

        if transicoes_resumo:
            transicoes_texto = []
            for item in transicoes_resumo:
                if not item['transicoes']:
                    continue
                descricoes = [f'{mov["de"]} -> {mov["para"]}: {mov["quantidade"]}' for mov in item['transicoes']]
                transicoes_texto.append(f'{item["label"]}: ' + ', '.join(descricoes))
            if transicoes_texto:
                mensagem += ' Movimentações previstas: ' + ' | '.join(transicoes_texto)

        return httprr(redirect_url, mensagem)

    resumo_tabela = [
        {'campo': campo, 'label': field_labels[campo], 'before': resumo_antes[campo], 'after': resumo_depois[campo]} for campo in field_map
    ]

    contexto = {
        'edital': edital,
        'resumo': resumo_tabela,
        'total_registros_xml': len(dados_por_inscricao),
        'total_candidatos_suap': len(candidatos),
        'total_alteracoes': len(plano),
        'inscricoes_nao_encontradas': inscricoes_nao_encontradas,
        'detalhes_aprovacoes': detalhes_por_candidato,
        'transicoes_aprovacoes': transicoes_resumo,
    }

    return contexto


@permission_required('processo_seletivo.view_edital')
def oferta_vaga_curso_ajax(request, pk):
    oferta_vaga_curso = OfertaVagaCurso.objects.filter(pk=pk).first()
    if not oferta_vaga_curso:
        return JsonResponse({'error': 'Oferta Vaga Curso não encontrado'})
    total_vagas = oferta_vaga_curso.get_total_vagas(True)
    total_matriculados = oferta_vaga_curso.get_total_matriculados()
    pode_convocar = oferta_vaga_curso.pode_convocar(request.user)
    pode_editar_ofertavagacurso = request.user.has_perm('processo_seletivo.change_ofertavagacurso')
    html = render_to_string('processo_seletivo/templates/oferta_vaga_curso_ajax.html', locals())
    return JsonResponse({'html': html})


@rtr()
@permission_required('processo_seletivo.view_edital')
def edital(request, pk):
    obj = get_object_or_404(Edital, pk=pk)
    if request.GET.get('processar_matriculas_proitec') and obj.possui_curso_proitec():
        return tasks.processar_matriculas_proitec(obj)

    conf = obj.configuracao_migracao_vagas
    pks_uos_edital = OfertaVagaCurso.locals.filter(edital=obj).values_list('curso_campus__diretoria__setor__uo', flat=True)
    polos = OfertaVagaCurso.locals.filter(edital=obj).exclude(campus_polo='').values_list('campus_polo', flat=True).distinct()
    is_administrador = in_group(request.user, 'Administrador Acadêmico,Operador de Editais de Ensino')
    is_operador_censo = request.user.has_perm('comum.is_operador_de_censo')
    uos = UnidadeOrganizacional.objects.suap().filter(pk__in=pks_uos_edital)
    if not is_administrador and not is_operador_censo:
        groups_user = request.user.get_groups('processo_seletivo.view_edital').values_list('name', flat=True)
        uos_pk = UsuarioGrupoSetor.objects.filter(usuario_grupo__user=request.user, usuario_grupo__group__name__in=groups_user).values_list(
            'setor__uo', flat=True
        )
        uos = uos.filter(pk__in=uos_pk)
    configuracao_chamada_id = request.GET.get('del_configuracao_chamada_id')
    candidato = request.GET.get('candidato')
    uo_selecionada = int(request.GET.get('uo_selecionada') or uos.count() == 1 and uos.first().pk or 0)
    polo_selecionado = request.GET.get('polo_selecionado') or polos.count() == 1 and polos.first() or ''
    xls_candidatos = request.GET.get('xls_candidatos')
    pk_diretorias = (
        Diretoria.objects.values_list('pk', flat=True) if is_administrador or is_operador_censo else Diretoria.locals.values_list('pk', flat=True)
    )
    ofertas_vagas_curso_resumo = []
    candidatos = obj.candidato_set.all().order_by('nome')
    qs_ofertavagacurso = obj.ofertavagacurso_set.all()
    pks_polos = None
    if request.user.has_group_cached('Coordenador de Polo EAD', ignore_groups_if_superuser=False):
        polos = CoordenadorPolo.objects.filter(vinculo=request.user.get_vinculo()).values_list('polo__descricao', flat=True)
        pks_polos = CandidatoVaga.objects.filter(candidato__campus_polo__in=polos).values_list('oferta_vaga__oferta_vaga_curso', flat=True).distinct()
        candidatos = candidatos.filter(campus_polo__in=polos)
        qs_ofertavagacurso = qs_ofertavagacurso.filter(campus_polo__in=polos)

    for curso_campus in CursoCampus.objects.filter(
        id__in=qs_ofertavagacurso.values_list('curso_campus_id', flat=True).distinct(), diretoria_id__in=pk_diretorias
    ).order_by('diretoria'):
        ofertas_vagas_curso_resumo.append(
            {
                'curso_campus': curso_campus,
                'qtd_inscritos': sum(obj.ofertavagacurso_set.filter(curso_campus=curso_campus).values_list('qtd_inscritos', flat=True)),
            }
        )

    pendencias = obj.get_pendencias()

    if 'enviar_notificacoes_matricula' in request.GET:
        candidato_vaga_id = request.GET['enviar_notificacoes_matricula']
        liberacao_id = request.GET['liberacao']
        if candidato_vaga_id:
            url = f'/processo_seletivo/monitorar_notificacoes_matricula/{liberacao_id}/'
        else:
            url = f'/processo_seletivo/edital/{obj.pk}/?tab=liberacao'
        total = obj.editalperiodoliberacao_set.get(pk=liberacao_id).enviar_notificacoes_matricula(candidato_vaga_id)
        return httprr(url, f'Um total de {total} de notificações de matrícula foram enviadas.')

    if 'relatorio_matricula' in request.GET:
        rows = [['COD CURSO', 'NOME CURSO', 'DIRETORIA', 'LISTA', 'QTD VAGA', 'QTD VAGA CEDIDA', 'QTD VAGA RECEBIDA', 'MAT 1º SEM', 'MAT 2º SEM']]
        qs = OfertaVagaCurso.objects.filter(edital=pk, curso_campus__diretoria__in=pk_diretorias)
        for ovc in qs:
            cc = ovc.curso_campus
            for ov in ovc.ofertavaga_set.all():
                rows.append(
                    [
                        cc.codigo,
                        cc.descricao_historico,
                        cc.diretoria.setor.sigla,
                        ov.lista.descricao,
                        ov.get_descricao_qtd_vagas(),
                        ov.get_vagas_usadas_em_migracao().count() or ' ',
                        ov.get_vagas_usadas_de_migracao().count() or '',
                        ov.candidatovaga_set.filter(aluno__periodo_letivo=1).count() or ' ',
                        ov.candidatovaga_set.filter(aluno__periodo_letivo=2).count() or ' ',
                    ]
                )

        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename=RelatorioMatricula.xlsx'

        df = pd.DataFrame(rows[1:], columns=rows[0])
        df.to_excel(response, index=False, engine='openpyxl')

        return response

    nova_chamada = request.GET.get('nova_chamada')
    if nova_chamada:
        oferta_vaga_curso = OfertaVagaCurso.objects.get(pk=nova_chamada)
        convocados = oferta_vaga_curso.realizar_nova_chamada()
        return httprr(
            f'/processo_seletivo/edital/{pk}/?tab=vagas&uo_selecionada={uo_selecionada}&polo_selecionado={polo_selecionado}',
            f'Convocação realizada com sucesso. {len(convocados)} candidato(s) convocado(s).',
        )
    cancelar_chamada = request.GET.get('cancelar_chamada')
    if cancelar_chamada:
        oferta_vaga_curso = OfertaVagaCurso.objects.get(pk=cancelar_chamada)
        oferta_vaga_curso.cancelar_ultima_chamada()
        return httprr(
            f'/processo_seletivo/edital/{pk}/?tab=vagas&uo_selecionada={uo_selecionada}&polo_selecionado={polo_selecionado}',
            'Última chamada cancelada com sucesso.',
        )

    if candidato:
        candidatos = (candidatos.filter(nome__unaccent__icontains=candidato) | candidatos.filter(cpf__icontains=candidato)).distinct()
    else:
        candidato = ''

    ofertas_vagas_curso = OfertaVagaCurso.objects.none()
    if request.GET.get('tab') == 'vagas' and uo_selecionada:
        ofertas_vagas_curso = OfertaVagaCurso.locals.filter(edital_id=obj.pk, curso_campus__diretoria__setor__uo_id=uo_selecionada).order_by(
            'curso_campus__diretoria__setor__uo__nome', 'turno', 'curso_campus__descricao'
        )

        if not obj.possui_curso_proitec():
            ofertas_vagas_curso = ofertas_vagas_curso.filter(campus_polo=polo_selecionado)

        if pks_polos:
            ofertas_vagas_curso = ofertas_vagas_curso.filter(pk__in=pks_polos)

    if request.GET.get('tab') == 'candidatos':
        if uo_selecionada:
            candidatos = (
                candidatos.filter(candidatovaga__oferta_vaga__oferta_vaga_curso__curso_campus__diretoria__setor__uo__pk=uo_selecionada)
            ).distinct()

        if not obj.possui_curso_proitec() and polo_selecionado:
            candidatos = candidatos.filter(campus_polo=polo_selecionado)

    sisu_gestao = obj.sisu and request.GET.get('sisu_gestao')
    if sisu_gestao:
        rows = []
        qs = CandidatoVaga.objects.filter(candidato__edital=pk, oferta_vaga__oferta_vaga_curso__curso_campus__diretoria__in=pk_diretorias)
        for inscricao in qs.filter(situacao=CandidatoVaga.MATRICULADO).values_list('candidato__inscricao', flat=True):
            rows.append([inscricao, 'M'])
        for inscricao in qs.filter(situacao=CandidatoVaga.AUSENTE).values_list('candidato__inscricao', flat=True):
            rows.append([inscricao, 'N'])
        for inscricao in qs.filter(situacao=CandidatoVaga.INAPTO).values_list('candidato__inscricao', flat=True):
            rows.append([inscricao, 'R'])
        for inscricao in qs.filter(situacao=CandidatoVaga.MATRICULA_CANCELADA).values_list('candidato__inscricao', flat=True):
            rows.append([inscricao, 'C'])
        return CsvResponse(rows, delimiter=';')

    lista_convocados = request.GET.get('lista_convocados')
    divulgacao = request.GET.get('divulgacao') == '1'
    if lista_convocados:
        convocados = []
        if lista_convocados == '0':
            rows = [
                [
                    'Curso',
                    'Chamada',
                    'Lista',
                    'Classificação',
                    'CPF',
                    'Nome',
                    'Telefone',
                    'E-mail',
                    'Nº Inscrição',
                    'Aprovado Heteroidentificação',
                    'Aprovado Quilombola',
                    'Aprovado Escola Pública',
                    'Aprovado Baixa Renda',
                    'Aprovado Deficiência',
                    'Situação',
                    'Matrícula',
                    'Situação da Matrícula',
                ]
            ]
            for oferta_vaga_curso in ofertas_vagas_curso:
                convocados_chamada = oferta_vaga_curso.get_numero_ultima_chamada()
                qs_convocados = CandidatoVaga.objects.filter(
                    convocacao=convocados_chamada, oferta_vaga__oferta_vaga_curso=oferta_vaga_curso
                ).order_by('oferta_vaga__oferta_vaga_curso', 'oferta_vaga', 'classificacao')
                for candidato_vaga in qs_convocados:
                    convocados.append((oferta_vaga_curso, candidato_vaga, convocados_chamada))

        else:
            rows = [
                [
                    'Curso',
                    'Chamada',
                    'Lista',
                    'Classificação',
                    'CPF',
                    'Nome',
                    'Telefone',
                    'E-mail',
                    'Nº Inscrição',
                    'Aprovado Heteroidentificação',
                    'Aprovado Quilombola',
                    'Aprovado Escola Pública',
                    'Aprovado Baixa Renda',
                    'Aprovado Deficiência',
                    'Situação',
                    'Matrícula',
                    'Situação da Matrícula',
                ]
            ]
            convocados_chamada = request.GET.get('chamada')
            qs_convocados = CandidatoVaga.objects.filter(convocacao=convocados_chamada, oferta_vaga__oferta_vaga_curso=lista_convocados).order_by(
                'oferta_vaga', 'classificacao'
            )
            for candidato_vaga in qs_convocados:
                convocados.append((candidato_vaga.oferta_vaga.oferta_vaga_curso, candidato_vaga, convocados_chamada))

        for oferta_vaga_curso, candidato_vaga, convocados_chamada in convocados:
            row = []
            if oferta_vaga_curso:
                row.append(
                    f'{oferta_vaga_curso.curso_campus.codigo} - {oferta_vaga_curso.curso_campus.descricao_historico} - {oferta_vaga_curso.turno}'
                )
            row.extend(
                (
                    convocados_chamada,
                    format_(candidato_vaga.oferta_vaga.lista),
                    format_(
                        candidato_vaga.classificacao_para_divulgacao
                        if (divulgacao and candidato_vaga.classificacao_para_divulgacao is not None)
                        else candidato_vaga.classificacao
                    ),
                    format_(candidato_vaga.candidato.cpf),
                    format_(candidato_vaga.candidato.nome),
                    format_(candidato_vaga.candidato.telefone),
                    format_(candidato_vaga.candidato.email),
                    format_(candidato_vaga.candidato.inscricao),
                    format_(candidato_vaga.candidato.aprovado_heteroidentificacao, html=False),
                    format_(candidato_vaga.candidato.aprovado_quilombola, html=False),
                    format_(candidato_vaga.candidato.aprovado_escola_publica, html=False),
                    format_(candidato_vaga.candidato.aprovado_baixa_renda, html=False),
                    format_(candidato_vaga.candidato.aprovado_deficiencia, html=False),
                )
            )
            if oferta_vaga_curso:
                aluno = candidato_vaga.get_aluno()
                row.extend(
                    (
                        candidato_vaga.get_situacao_display(),
                        format_(aluno and aluno.matricula or ''),
                        format_(aluno and aluno.situacao.descricao or ''),
                    )
                )
            rows.append(row)
        return XlsResponse(rows)

    if xls_candidatos:
        rows = [
            [
                '#',
                'Nº Inscrição',
                'CPF',
                'Nome',
                'Telefone',
                'E-mail',
                'Código do Curso',
                'Nome do Curso',
                'Diretoria',
                'Lista',
                'Classificação',
                'Aprovado',
                'Eliminado',
                'Situação',
            ]
        ]
        count = 0
        for cv in CandidatoVaga.objects.filter(candidato__in=candidatos.values_list('pk', flat=True)).order_by('candidato'):
            count += 1
            row = [
                count,
                format_(cv.candidato.inscricao),
                format_(cv.candidato.cpf),
                format_(cv.candidato.nome),
                format_(cv.candidato.telefone),
                format_(cv.candidato.email),
                format_(cv.oferta_vaga.oferta_vaga_curso.curso_campus.codigo),
                format_(cv.oferta_vaga.oferta_vaga_curso.curso_campus.descricao),
                format_(cv.oferta_vaga.oferta_vaga_curso.curso_campus.diretoria),
                format_(cv.oferta_vaga.lista),
                format_(cv.classificacao),
                format_(cv.aprovado, html=False),
                format_(cv.eliminado, html=False),
                format_(cv.get_situacao_display()),
            ]
            rows.append(row)
        return XlsResponse(rows)

    if request.GET.get('tab') == 'liberacao':
        liberacoes = EditalPeriodoLiberacao.objects.filter(edital=obj).order_by('uo__sigla')
        if uo_selecionada:
            liberacoes = liberacoes.filter(uo=uo_selecionada)

    title = str(obj)
    return locals()


@rtr()
@permission_required('processo_seletivo.pode_liberar_periodos')
def edital_periodo_liberacao(request, edital_pk, pk=None):
    edital = get_object_or_404(Edital, pk=edital_pk)

    editar = pk is not None

    title = 'Adicionar Período'

    pks_uos_edital = OfertaVagaCurso.locals.filter(edital=edital).values_list('curso_campus__diretoria__setor__uo', flat=True)
    pks_uos_cadastradas = EditalPeriodoLiberacao.objects.filter(edital=edital).values_list('uo')

    form = None

    if not editar:
        form = EditalLiberacaoForm(request.POST or None, request=request, edital=edital, uos_edital=pks_uos_edital)
    else:
        title = 'Alterar Período'
        liberacao = get_object_or_404(EditalPeriodoLiberacao, pk=pk)
        form = EditalLiberacaoForm(request.POST or None, request=request, edital=edital, uos_edital=pks_uos_edital, instance=liberacao)

    if form.is_valid():
        form.save()
        return httprr('..', 'Período de Liberação salvo.')

    return locals()


@rtr()
@permission_required('processo_seletivo.pode_liberar_periodos')
def historico_edital_periodo_liberacao(request, edital_liberacao_periodo_pk):
    edital_liberacao_periodo = get_object_or_404(EditalPeriodoLiberacao, pk=edital_liberacao_periodo_pk)
    title = 'Histórico de Liberação de Período'
    historico_liberacoes = EditalPeriodoLiberacaoHistorico.objects.filter(periodo_liberacao=edital_liberacao_periodo)
    return locals()


@rtr()
@permission_required('processo_seletivo.pode_ausentar_candidatos')
def edital_ausentar_candidatos(request, pk):
    edital = get_object_or_404(Edital, pk=pk)

    uo_usuario = None

    if not in_group(request.user, 'Administrador Acadêmico'):
        uo_usuario = get_uo(request.user)

    if not edital.pode_ausentar(request.user, uo_usuario):
        raise PermissionDenied

    title = 'Ausentar Candidatos em Chamadas'

    form = EditalAusentarCandidatosForm(request.POST or None, edital=edital, request=request)

    if form.is_valid():
        candidatos_vaga = CandidatoVaga.objects.filter(
            candidato__edital=edital,
            convocacao=form.cleaned_data['chamada'],
            oferta_vaga__oferta_vaga_curso__curso_campus__diretoria__setor__uo=form.cleaned_data['campus'],
        ).filter(Q(situacao__isnull=True) | Q(situacao=CandidatoVaga.AUSENTE))
        for candidato_vaga in candidatos_vaga:
            candidato_vaga.registrar_ausencia()
        return httprr('.', 'Candidatos ausentados com sucesso.')
    return locals()


@rtr()
@permission_required('processo_seletivo.view_edital')
def oferta_vaga(request, pk):
    obj = get_object_or_404(OfertaVaga, pk=pk)
    title = f'{obj.oferta_vaga_curso.edital} - {obj.oferta_vaga_curso.curso_campus.descricao} ({obj.lista.descricao})'
    candidatos = obj.get_candidatos_classificados()

    return locals()


@rtr()
@permission_required('processo_seletivo.view_edital')
def visualizar_vagas(request, pk, tipo):
    oferta_vaga = get_object_or_404(OfertaVaga, pk=pk)
    title = str(oferta_vaga.lista)
    vagas = oferta_vaga.vaga_set.none()
    if tipo == 0:
        vagas = oferta_vaga.vaga_set.all()
    elif tipo == 1:
        vagas = oferta_vaga.vaga_set.filter(candidatovaga__situacao=CandidatoVaga.MATRICULADO)
    elif tipo == 2:
        vagas = oferta_vaga.get_vagas_usadas_de_migracao()
    elif tipo == 3:
        vagas = oferta_vaga.get_vagas_usadas_em_migracao()
    vagas_ordenadas = vagas.order_by('candidatovaga__convocacao', 'candidatovaga__classificacao')
    if oferta_vaga.oferta_vaga_curso.edital.configuracao_migracao_vagas_id:
        listas = oferta_vaga.oferta_vaga_curso.edital.configuracao_migracao_vagas.get_nomes_listas_ordenadas_por_restricao()
        vagas_ordenadas = []
        for descricao in listas:
            for vaga in vagas.filter(oferta_vaga__lista__descricao=descricao).order_by('id'):
                vagas_ordenadas.append(vaga)
    if 'retornar_vaga_polo' in request.GET:
        vaga = oferta_vaga.vagas_recebidas_polos.filter(pk=request.GET['retornar_vaga_polo']).first()
        if vaga:
            oferta_vaga.vagas_recebidas_polos.remove(vaga)
            return httprr('..', 'Vaga retornada com sucesso.')
    return locals()


@rtr()
@permission_required('processo_seletivo.view_edital')
def migrar_vaga_polo(request, pk):
    title = 'Migrar Vaga de Polo'
    polo_origem = request.GET['origem']
    oferta_vaga_curso = get_object_or_404(OfertaVagaCurso, pk=pk)
    polos = (
        oferta_vaga_curso.edital.ofertavagacurso_set.filter(campus_polo__isnull=False)
        .exclude(campus_polo='')
        .order_by('campus_polo')
        .values_list('campus_polo', flat=True)
        .distinct()
    )
    form = MigrarVagaPoloForm(data=request.POST or None)
    form.fields['polo_destino'].choices = [[x, x] for x in polos if x != polo_origem]
    if form.is_valid():
        form.processar(oferta_vaga_curso)
        if not form.errors:
            return httprr('..', 'Vagas migradas com sucesso.')
    return locals()


@rtr()
@permission_required('processo_seletivo.view_edital')
def classificados(request, pk, polo=None):
    oferta_vaga = get_object_or_404(OfertaVaga, pk=pk)
    candidatos_vagas = oferta_vaga.candidatovaga_set.all().order_by('-aprovado', 'candidato__campus_polo', 'classificacao', 'candidato__turno')
    polos = (
        candidatos_vagas.filter(candidato__campus_polo__isnull=False)
        .exclude(candidato__campus_polo='')
        .order_by('candidato__campus_polo')
        .values_list('candidato__campus_polo', flat=True)
        .distinct()
    )
    is_cota_etnica = oferta_vaga.is_cota_etnica()
    data_fim_matricula = None
    pode_convocar = oferta_vaga.oferta_vaga_curso.pode_convocar(request.user)
    pode_realizar_acao = True
    is_administrador = in_group(request.user, 'Administrador Acadêmico')

    if request.user.has_group_cached('Coordenador de Polo EAD', ignore_groups_if_superuser=False):
        polos = CoordenadorPolo.objects.filter(vinculo=request.user.get_vinculo()).values_list('polo__descricao', flat=True)
        if oferta_vaga.oferta_vaga_curso.edital.matricula_no_polo:
            pode_realizar_acao = True

    liberacao = EditalPeriodoLiberacao.objects.filter(
        edital=oferta_vaga.oferta_vaga_curso.edital, uo=oferta_vaga.oferta_vaga_curso.curso_campus.diretoria.setor.uo
    ).first()
    if liberacao:
        pode_realizar_acao = liberacao.data_limite_avaliacao and datetime.datetime.now() <= somar_dias(liberacao.data_limite_avaliacao, 30)
    else:
        pode_realizar_acao = True

    if not polo and polos:
        polo = polos[0]
    if polo:
        candidatos_vagas = candidatos_vagas.filter(candidato__campus_polo=polo)
    q = request.GET.get('q', None)
    if q:
        candidatos_vagas = candidatos_vagas.filter(candidato__cpf=q) | candidatos_vagas.filter(candidato__nome__unaccent__icontains=q)
    page = 1
    is_debug = settings.DEBUG
    if 'page' in request.GET:
        page = request.GET['page']

    if 'excluir_criacao_vaga' in request.GET:
        criacao = oferta_vaga.get_criacao_classificacao().filter(pk=request.GET['excluir_criacao_vaga']).first()
        if criacao and criacao.responsavel == request.user and criacao.pode_ser_excluida():
            criacao.candidato_vaga.delete()
            url = f'/processo_seletivo/classificados/{pk}/'
            return httprr(url, 'Exclusão realizada com sucesso.')

    permite_remanejar = Configuracao.get_valor_por_chave('processo_seletivo', 'permite_remanejar_geral') and oferta_vaga.lista.descricao not in (
        'AC',
        'Geral',
        'Ampla Concorrência',
    )
    if 'remanejamento' in request.GET and (is_debug or pode_realizar_acao):
        if permite_remanejar:
            candidato_vaga = CandidatoVaga.objects.get(pk=request.GET['remanejamento'])
            oferta_vaga_geral = oferta_vaga.oferta_vaga_curso.ofertavaga_set.get(lista__descricao__in=('AC', 'Geral', 'Ampla Concorrência'))
            candidato_vaga_geral = CandidatoVaga.objects.filter(oferta_vaga=oferta_vaga_geral, candidato=candidato_vaga.candidato).first()
            if candidato_vaga_geral is None:
                candidato_vaga.registrar_inaptidao()
                candidato_vaga_geral = CandidatoVaga()
                candidato_vaga_geral.oferta_vaga = oferta_vaga_geral
                candidato_vaga_geral.candidato = candidato_vaga.candidato
                candidato_vaga_geral.classificacao = oferta_vaga_geral.candidatovaga_set.order_by('classificacao').last().classificacao + 1
                candidato_vaga_geral.save()
                url = f'/processo_seletivo/classificados/{pk}/?page={page}#{candidato_vaga.pk}'
                if polo:
                    url = f'/processo_seletivo/classificados/{pk}/{polo}/?page={page}#{candidato_vaga.pk}'
                return httprr(url, 'Remanejamento registrado com sucesso.')

    if 'ausencia' in request.GET and (is_debug or pode_realizar_acao):
        candidato_vaga = CandidatoVaga.objects.get(pk=request.GET['ausencia'])
        candidato_vaga.registrar_ausencia()

        url = f'/processo_seletivo/classificados/{pk}/?page={page}#{candidato_vaga.pk}'
        if polo:
            url = f'/processo_seletivo/classificados/{pk}/{polo}/?page={page}#{candidato_vaga.pk}'

        return httprr(url, 'Ausência registrada com sucesso.')
    if (
        'inaptidao' in request.GET
        or 'inaptidao_hetero_identificacao' in request.GET
        or 'inaptidao_quilombola' in request.GET
        or 'inaptidao_baixa_renda' in request.GET
        or 'inaptidao_escola_publica' in request.GET
        or 'inaptidao_deficiencia' in request.GET
    ) and (is_debug or pode_realizar_acao):
        candidato_vaga = CandidatoVaga.objects.get(
            pk=request.GET.get('inaptidao')
            or request.GET.get('inaptidao_hetero_identificacao')
            or request.GET.get('inaptidao_quilombola')
            or request.GET.get('inaptidao_baixa_renda')
            or request.GET.get('inaptidao_escola_publica')
            or request.GET.get('inaptidao_deficiencia')
        )
        candidato_vaga.registrar_inaptidao(
            request.GET.get('inaptidao_hetero_identificacao'),
            request.GET.get('inaptidao_quilombola'),
            request.GET.get('inaptidao_baixa_renda'),
            request.GET.get('inaptidao_escola_publica'),
            request.GET.get('inaptidao_deficiencia'),
        )

        url = f'/processo_seletivo/classificados/{pk}/?page={page}#{candidato_vaga.pk}'
        if polo:
            url = f'/processo_seletivo/classificados/{pk}/{polo}/?page={page}#{candidato_vaga.pk}'

        return httprr(url, 'Inaptidão registrada com sucesso.')

    if 'simular' in request.GET and (is_debug or pode_realizar_acao):
        candidato_vaga = CandidatoVaga.objects.get(pk=request.GET['simular'])
        candidato_vaga.simular_matricula()
        url = f'/processo_seletivo/classificados/{pk}/?page={page}#{candidato_vaga.pk}'
        if polo:
            url = f'/processo_seletivo/classificados/{pk}/{polo}/?page={page}#{candidato_vaga.pk}'

        return httprr(url, 'Simulação de matrícula realizada com sucesso.')
    if 'desfazer' in request.GET and (is_debug or pode_realizar_acao):
        candidato_vaga = CandidatoVaga.objects.get(pk=request.GET['desfazer'])
        if request.user.is_superuser or is_debug or is_administrador or candidato_vaga.situacao in (CandidatoVaga.AUSENTE, CandidatoVaga.INAPTO):
            candidato_vaga.desfazer_procedimento()
        url = f'/processo_seletivo/classificados/{pk}/?page={page}#{candidato_vaga.pk}'
        if polo:
            url = f'/processo_seletivo/classificados/{pk}/{polo}/?page={page}#{candidato_vaga.pk}'

        return httprr(url, 'Procedimento desfeito com sucesso.')

    xls_candidatos = request.GET.get('xls_candidatos')
    if xls_candidatos:
        rows = [
            [
                'Classificação',
                'Turno',
                'CPF',
                'Nome',
                'Telefone',
                'E-mail',
                'Nº Inscrição',
                'Matriculado',
                'Situação',
                'Lista',
                'Aprovado',
                'Eliminado',
                'Convocação',
            ]
        ]
        count = 0
        for candidato_vaga in candidatos_vagas:
            row = [
                format_(candidato_vaga.classificacao),
                format_(candidato_vaga.candidato.turno),
                format_(candidato_vaga.candidato.cpf),
                normalizar_nome_proprio(format_(candidato_vaga.candidato.nome)),
                format_(candidato_vaga.candidato.telefone),
                format_(candidato_vaga.candidato.email),
                format_(candidato_vaga.candidato.inscricao),
                format_(candidato_vaga.is_matriculado() and 'Sim' or 'Não'),
                format_(candidato_vaga.get_situacao_display()),
                format_(candidato_vaga.candidato.get_lista_candidato()),
                format_(candidato_vaga.aprovado and 'Sim' or 'Não'),
                format_(candidato_vaga.eliminado and 'Sim' or 'Não'),
                format_(candidato_vaga.convocacao or ''),
            ]
            rows.append(row)
        return XlsResponse(rows)

    title = 'Candidatos Classificados na Lista'
    ultima_chamada = oferta_vaga.oferta_vaga_curso.get_numero_ultima_chamada()

    grupos_candidatos_vaga = [
        ('Aprovados', candidatos_vagas.filter(aprovado=True)),
        ('Habilitados', candidatos_vagas.filter(aprovado=False, eliminado=False)),
    ]

    return locals()


@rtr()
@permission_required('processo_seletivo.view_edital')
def candidato(request, pk):
    obj = get_object_or_404(Candidato, pk=pk)
    title = str(obj)
    return locals()


@login_required()
@rtr()
@permission_required('processo_seletivo.pode_matricular_proitec')
def matricular_alunos_proitec(request, pk, ano, periodo):
    edital = get_object_or_404(Edital, pk=pk)
    title = f'Matricular Alunos Proitec - {edital.descricao}'

    form = MatricularAlunoProitecForm(edital=edital, data=request.POST or None, initial={'ano': ano, 'periodo': periodo})

    if form.is_valid():
        return form.processar(request)

    return locals()


@rtr()
@permission_required('processo_seletivo.change_lista')
def definir_forma_ingresso(request, pk):
    lista = get_object_or_404(Lista, pk=pk)
    title = 'Forma de Ingresso'
    form = ListaForm(data=request.POST or None, request=request, instance=lista)
    if form.is_valid():
        obj = form.save()
        return httprr('..', 'Forma de ingresso definida com sucesso.')
    return locals()


@rtr()
@permission_required('processo_seletivo.pode_liberar_periodos')
def participacao_banca(request, pk):
    candidato = get_object_or_404(Candidato, pk=pk)
    title = f'Participação em Banca - {candidato}'
    form = ParticipacaoBancaForm(data=request.POST or None, instance=candidato)
    if form.is_valid():
        form.save()
        return httprr('..', 'Participação em banca definida com sucesso.')
    return locals()


@rtr()
@permission_required('processo_seletivo.pode_liberar_periodos')
def monitorar_notificacoes_matricula(request, pk):
    title = 'Monitoramento de Notificações de Matrícula'
    obj = get_object_or_404(EditalPeriodoLiberacao.objects, pk=pk)
    return locals()


@rtr()
def visualizar_notificacao_matricula(request, token):
    obj = get_object_or_404(NotificacaoMatricula.objects, token=token)
    if obj.data_leitura is None:
        obj.data_leitura = datetime.datetime.now()
        obj.save()
    return locals()


@rtr()
@login_required()
def inscricao_em_edital(request, edital_id):
    edital = get_object_or_404(EditalAdesaoCampus, pk=edital_id)
    pode_efetuar_inscricao, msg = InscricaoFiscal.pode_efetuar_inscricao(request.user, edital)
    if not pode_efetuar_inscricao:
        return httprr('/', message=f'A sua incrição foi indeferida, pois {msg}', tag='error')
    title = f'Formulário de Inscrição para o edital {edital}'
    form = InscricaoFiscalForm(request.POST or None, user=request.user, edital=edital)
    vinculo = request.user.get_vinculo()
    if form.is_valid():
        form.save()
        return httprr('/', msg)
    return locals()


@permission_required('processo_seletivo.change_inscricaofiscal')
def inscricao_em_edital_xls(request):
    #
    rows = [
        [
            ' Edital',
            'Tipo',
            'Nome',
            'Mátricula',
            'CPF',
            'Nascimento',
            'Banco',
            'Tipo de conta',
            'Agência',
            'Conta',
            'Operação',
            'PIS/PASEP',
            'Telefones',
            'Participou de outros processos?',
            'Início na instituição',
            'Período/ano atual',
            'Renda per Capita',
            'Ensino Fundamental',
            'Ensino Médio',
            'Participação em programas socias',
            'Participação na assistência estudantil',
            'Curso',
            'IRA',
            'Idade no dia da prova',
        ]
    ]
    queryset = InscricaoFiscal.objects.all()
    filters = {}
    for key, value in list(request.GET.items()):
        if key not in ('ot', 'o', 'all'):
            filters[str(key)] = str(value)
    if filters:
        queryset = queryset.filter(**filters)

    inscricoes = list(queryset.select_related('fiscal').order_by('-id')[0:1000])
    hoje = datetime.date.today()
    alunos_ids = [i.fiscal.id_relacionamento for i in inscricoes if i.fiscal.eh_aluno()]
    alunos_participantes_ids = set(
        Participacao.objects.filter(aluno_id__in=alunos_ids, data_inicio__lte=hoje)
        .filter(Q(data_termino__isnull=True) | Q(data_termino__gte=hoje))
        .values_list('aluno_id', flat=True)
    )

    for inscricao in inscricoes:
        inicio_na_instituicao, ira, renda_per_capita = '-', '-', '-'
        periodo_atual, escola_ensino_fundamental, escola_ensino_medio = '-', '-', '-'
        eh_participante = False
        eh_beneficiario = False
        curso = '-'
        if inscricao.fiscal.eh_funcionario():
            inicio_na_instituicao = inscricao.fiscal.relacionamento.data_inicio_exercicio_na_instituicao.strftime('%d/%m/%Y')
        if inscricao.fiscal.eh_aluno():
            aluno = inscricao.fiscal.relacionamento
            curso = aluno.curso_campus
            ira = aluno.get_ira()
            eh_participante = aluno.id in alunos_participantes_ids
            if hasattr(aluno, 'caracterizacao'):
                renda_per_capita = aluno.caracterizacao.renda_per_capita
                eh_beneficiario = aluno.caracterizacao.beneficiario_programa_social.all().exists()
                periodo_atual = aluno.periodo_atual
                escola_ensino_fundamental = '%s' % (aluno.caracterizacao.escola_ensino_fundamental or '-')
                escola_ensino_medio = '%s' % (aluno.caracterizacao.escola_ensino_medio or '-')
        #
        rows.append(
            [
                inscricao.edital,
                inscricao.tipo,
                inscricao.fiscal.pessoa.pessoafisica.nome,
                inscricao.matricula,
                inscricao.fiscal.pessoa.pessoafisica.cpf,
                inscricao.fiscal.pessoa.pessoafisica.nascimento_data.strftime('%d/%m/%Y'),
                inscricao.banco,
                inscricao.tipo_conta,
                inscricao.numero_agencia,
                inscricao.numero_conta,
                inscricao.operacao,
                inscricao.fiscal.pessoa.pessoafisica.pis_pasep,
                inscricao.telefones,
                inscricao.outros_processos,
                # Apenas para servidores
                inicio_na_instituicao,
                # Apenas para alunos
                periodo_atual,
                renda_per_capita,
                escola_ensino_fundamental,
                escola_ensino_medio,
                eh_beneficiario,
                eh_participante,
                curso,
                ira,
                inscricao.idade_no_dia_prova(),
            ]
        )
    return XlsResponse(rows)


@rtr()
@permission_required('processo_seletivo.view_edital')
def configuracaomigracaovaga(request, pk):
    conf = get_object_or_404(ConfiguracaoMigracaoVaga, pk=pk)
    title = str(conf)
    if 'replicar' in request.GET:
        precedencias = conf.precedenciamigracao_set.all()
        configuracao = conf
        configuracao.descricao = ''
        configuracao.pk = None
        configuracao.save()
        for precedencia in precedencias:
            precedencia.configuracao = configuracao
            precedencia.pk = None
            precedencia.save()

        return httprr(f'/admin/processo_seletivo/configuracaomigracaovaga/{configuracao.pk}/', 'Replicação realizada com sucesso')
    precedencias = conf.get_precedencias()
    return locals()


@rtr()
@permission_required('processo_seletivo.add_configuracaomigracaovaga')
def definir_configuracao_migracao_vaga(request, pk):
    title = 'Definir Configuração de Migração de Vagas'
    obj = get_object_or_404(Edital, pk=pk)
    form = DefinirConfiguracaoMigracaoVagaForm(data=request.POST or None, request=request, instance=obj)
    if form.is_valid():
        form.save()
        return httprr('..', 'Configuração de migração de vagas definida com sucesso.')
    return locals()


@rtr()
@permission_required('processo_seletivo.add_configuracaomigracaovaga')
def definir_precedencia_matricula(request, pk):
    title = 'Definir Precedência de Matrícula'
    obj = get_object_or_404(ConfiguracaoMigracaoVaga, pk=pk)
    form = DefinirPrecedenciaMatriculaForm(data=request.POST or None, request=request, instance=obj)
    if form.is_valid():
        form.save()
        return httprr('..', 'Precedência de matrícula definida com sucesso.')
    return locals()


@rtr()
@permission_required('processo_seletivo.add_configuracaomigracaovaga')
def definir_precedencia(request, pk):
    title = 'Definir Precedência de Migração de Vagas'
    obj = get_object_or_404(ConfiguracaoMigracaoVaga, pk=pk)
    form = PrecedenciaMigracaoForm(data=request.POST or None, request=request, configuracao=obj)
    if form.is_valid():
        form.save()
        return httprr('..', 'Precedência de migração de vaga definida com sucesso.')
    return locals()


@rtr()
@permission_required('processo_seletivo.add_configuracaomigracaovaga')
def editar_precedencia(request, pk, lista_origem):
    obj = get_object_or_404(ConfiguracaoMigracaoVaga, pk=pk)
    form = PrecedenciaMigracaoForm(data=request.POST or None, request=request, configuracao=obj, lista_origem=lista_origem)
    if form.is_valid():
        form.save()
        return httprr('..', 'Precedência de migração de vaga editada com sucesso.')
    return locals()


@rtr()
@permission_required('processo_seletivo.add_configuracaomigracaovaga')
def remover_precedencia(request, pk, lista_origem):
    PrecedenciaMigracao.objects.filter(configuracao__pk=pk, origem__nome=lista_origem).delete()
    return httprr(f'/processo_seletivo/configuracaomigracaovaga/{pk}/', 'Precedência de migração de vaga removida com sucesso.')


@rtr()
@permission_required('processo_seletivo.view_edital')
def realizar_acao_lote(request, pk):
    oferta_vaga = get_object_or_404(OfertaVaga, pk=pk)
    title = 'Realizar Ação em Lote'
    form = RealizarAcaoLote(data=request.POST or None, request=request, oferta_vaga=oferta_vaga)
    if form.is_valid():
        form.processar()
        return httprr('..', 'Ação realizada com sucesso.')
    return locals()


@rtr()
@permission_required('processo_seletivo.change_candidatovaga')
def vincular_vaga(request, pk):
    candidato_vaga = get_object_or_404(CandidatoVaga, pk=pk)
    candidato_vaga.vincular_vaga()
    return httprr('..', 'Ação realizada com sucesso.')


@rtr()
@permission_required('processo_seletivo.change_candidatovaga')
def vincular_matricula(request, pk):
    candidato_vaga = get_object_or_404(CandidatoVaga, pk=pk)
    title = 'Vincular Candidato à Matrícula de Aluno'
    form = VincularMatriculaForm(candidato_vaga=candidato_vaga, data=request.POST or None)
    if form.is_valid():
        form.processar()
        return httprr('..', 'Vinculação realizada com sucesso.')
    return locals()


@rtr()
@permission_required('processo_seletivo.change_ofertavagacurso')
def editar_oferta_vaga_curso(request, pk):
    title = 'Editar Oferta Vaga'
    obj = get_object_or_404(OfertaVagaCurso, pk=pk)
    form = EditarOfertaVagaCursoForm(request=request, instance=obj, data=request.POST or None)
    if form.is_valid():
        form.save()
        return httprr('..', 'Oferta vaga atualizada com sucesso')
    return locals()


@rtr()
@permission_required('processo_seletivo.view_edital')
def criar_vaga_remanescente(request, pk):
    title = 'Criar Vaga Remanescente'
    obj = get_object_or_404(OfertaVaga, pk=pk)
    if not obj.oferta_vaga_curso.edital.permite_adicionar_vagas_extras:
        return httprr('/', 'Não é possível realizar essa ação.', tag='error')
    form = CriacaoVagaRemanescenteForm(request=request, data=request.POST or None)
    if form.is_valid():
        form.instance.oferta_vaga = obj
        form.save()
        return httprr('..', 'Vaga criada com sucesso.')
    return locals()


@rtr()
@permission_required('processo_seletivo.view_edital')
def adicionar_candidato_classificacao(request, pk):
    title = 'Adicionar Candidato à Classificação'
    obj = get_object_or_404(OfertaVaga, pk=pk)
    if not obj.oferta_vaga_curso.edital.permite_adicionar_candidato_classificacao:
        return httprr('/', 'Não é possível realizar essa ação.', tag='error')
    form = CriacaoClassificacaoForm(obj, request=request, data=request.POST or None)
    if form.is_valid():
        form.save()
        return httprr('..', 'Candidato adicionado com sucesso.')
    return locals()


@rtr()
@permission_required('processo_seletivo.view_edital')
def corrigir_vagas_remanescentes(request, pk):
    title = 'Corrigir Quantidade de Vagas Remanescentes'
    criacao_vaga_remanescente = get_object_or_404(CriacaoVagaRemanescente, pk=pk)
    form = CorrigirQuantidadeVagaRemanescenteForm(request=request, data=request.POST or None)
    if form.is_valid():
        form.instance.criacao_vaga_remanescente = criacao_vaga_remanescente
        try:
            form.save()
        except Exception as e:
            return httprr('..', str(e), 'error', close_popup=True)
        return httprr('..', 'Quantidade de vagas atualizada com sucesso.', close_popup=True)
    return locals()


@rtr()
@permission_required('processo_seletivo.view_edital')
def historico_ajuste_vaga_remanescente(request, pk):
    title = 'Histórico de Ajustes na Quantidade de Vagas Remanescentes'
    criacao_vaga_remanescente = get_object_or_404(CriacaoVagaRemanescente, pk=pk)
    return locals()
