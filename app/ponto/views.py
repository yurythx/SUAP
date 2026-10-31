import csv
import ipaddress
import os
import tempfile
import time
import zipfile
from datetime import date, datetime, timedelta
from os import stat
from os.path import exists
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import connection, transaction
from django.db.models import OuterRef, Subquery, F
from django.db.models.expressions import Value
from django.db.models.functions import Coalesce
from django.http import FileResponse, HttpRequest, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404
from django.template.defaultfilters import pluralize
from django.views.decorators.csrf import csrf_exempt

from comum.models import Configuracao, PrestadorServico
from djtools import layout
from djtools.storages import cache_file
from djtools.utils import (
    agrupar_em_pares,
    datas_entre,
    date_to_string,
    djtools_max,
    djtools_min,
    extrair_periodo,
    formata_segundos,
    formata_timedelta,
    get_client_ip,
    get_date,
    get_real_sql,
    get_session_cache,
    httprr,
    permission_required,
    primeiro_dia_da_semana,
    render,
    rtr,
    str_to_dateBR,
)
from ponto import tasks
from ponto.compensacao import Contexto, PeriodoInfo
from ponto.enums import TipoFormFrequenciaTerceirizados
from ponto.exceptions import FuncionalidadeApenasFuncoesChefiaException
from ponto.forms import (
    AbonoChefiaChangeFormFactory,
    AbonoChefiaFormFactory,
    AbonoChefiaLoteFormFactory,
    AvaliacaoRevisaoAbonoChefiaChangeForm,
    DataRelatorioOcupacaoForm,
    DebitoExternoAdd,
    DebitoExternoCadastroDestinatarioAdd,
    DebitoExternoCadastroDestinatarioChange,
    DebitoExternoCadastroValidadorAdd,
    DebitoExternoCadastroValidadorChange,
    DebitoExternoCadastroValidar,
    DebitoExternoChange,
    DireitosHistoricoAbonoParcialFilterFormFactory,
    DocumentoAnexoChangeForm,
    DocumentoAnexoForm,
    FrequenciaCargoEmpregoFormFactory,
    FrequenciaDocenteFormFactory,
    FrequenciaFuncionarioFormFactory,
    FrequenciaNoturnaFormFactory,
    FrequenciasPorSetorFormFactory,
    FrequenciaTerceirizadosFormFactory,
    HorarioCompensacaoEditarObservacoesPontoForm,
    HorarioCompensacaoPeriodoForm,
    InformarCompensacaoPeriodoForm,
    LocalizarServidorForm,
    ObservacaoForm,
    RecessoDiaAddForm,
    RecessoOpcaoEscolhidaEditarChefeForm,
    RecessoOpcaoEscolhidaEditarForm,
    RecessoOpcaoEscolhidaValidarForm,
    RecessoOpcaoEscolhidaValidarLoteForm,
    RecessoPeriodoAddForm,
    RecessoPeriodoCompensacaoAddForm,
    RecessoPeriodoEscolhaForm,
    SaldoExternoDestinatarioAdd,
    SaldoExternoDestinatarioChange,
    SaldoExternoValidadorAdd,
    SaldoExternoValidadorChange,
    SaldoExternoValidar,
    SelecionarSaldosExternosForm,
    SolicitacaoAbonoParcialAvaliarFormFactory,
    SolicitacaoAbonoParcialEtapa1Form,
    SolicitacaoAbonoParcialEtapa2FormFactory,
    SolicitacaoAbonoParcialForm,
    SolicitacaoRevisaoAbonoChefiaChangeForm,
    SolicitacaoRevisaoAbonoChefiaFormFactory,
    get_compensacao_horario_add_form_v2,
    get_type_form_dias_ou_periodos_escolhidos,
    setor_raiz_por_permissao_ponto,
)
from ponto.models import (
    AbonoChefia,
    DebitoExterno,
    DebitoExternoCadastro,
    DocumentoAnexo,
    Frequencia,
    HorarioCompensacao,
    Maquina,
    MaquinaLog,
    Observacao,
    RecessoDia,
    RecessoOpcao,
    RecessoOpcaoEscolhida,
    RecessoPeriodo,
    RecessoPeriodoCompensacao,
    SaldoExterno,
    SolicitacaoAbonoParcial,
    SolicitacaoAbonoParcialGravidez,
    SolicitacaoRevisaoAbonoChefia,
)
from ponto.utils import (
    get_data_ultimo_dia_mes_corrente,
    get_relatorios_ponto_adaptados_para_relatorios_pit_rit_ponto_docente,
    get_response_xls_registros_frequencias,
    get_total_tempo_debito_pendente_mes_anterior,
    get_total_tempo_debito_pendente_mes_corrente,
    get_total_tempo_debito_pendente_semana_anterior,
    get_total_tempo_saldo_restante_mes_corrente,
    is_request_xls,
    mesmo_campus,
)
from rh.models import Funcao, Servidor, Setor
from ponto.exceptions import PontoException

TERMINAL_PONTO_FOTOS_DUMP = '/tmp/fotos.zip'


@layout.atribuidos_a_mim()
def index_atribuidos_a_mim(request):
    """Lista pendências do Ponto Eletrônico atribuídas ao servidor logado.

    Cobre recessos a analisar, frequências sem homologar e demais débitos
    específicos do servidor para o período corrente.

    Args:
        request: requisição HTTP usada para identificar o servidor logado.

    Returns:
        list[dict]: cartões de pendência; lista vazia quando o usuário não é
        servidor ou quando não há débitos.
    """
    pendencias = []

    sub_instance = request.user.get_relacionamento()
    if request.user.eh_servidor:
        # compensação de horários - acompanhamento de débitos específicos
        recessos_a_analisar = RecessoOpcaoEscolhida.get_recessos_escolhidos_aguardando_validacao_hoje(sub_instance).count()
        if recessos_a_analisar:
            pendencias.append(
                {
                    'titulo': f'Compensaç{pluralize(recessos_a_analisar, "ão Específica,ões Específicas")} de Horário',
                    'subtitulo': 'a validar',
                    'qtd': recessos_a_analisar,
                    'url': '/admin/ponto/recessoopcaoescolhida/?tab=recessos_pendentes_do_setor',
                }
            )

        qtd_saldos = SaldoExterno.get_saldos_externos_minhas_validacoes_pendentes(request.user).count()
        if qtd_saldos:
            pendencias.append(
                {
                    'titulo': 'Saldo Externo de Carga Horária',
                    'subtitulo': 'a validar',
                    'qtd': qtd_saldos,
                    'url': '/admin/ponto/saldoexterno/?tab=minhas_validacoes&situacao__exact=2',
                }
            )

        qtd_debitos = DebitoExternoCadastro.get_debitos_externos_cadastros_minhas_validacoes_pendentes(request.user).count()
        if qtd_debitos:
            pendencias.append(
                {
                    'titulo': 'Débito Externo de Carga Horária',
                    'subtitulo': 'a validar',
                    'qtd': qtd_debitos,
                    'url': '/admin/ponto/debitoexternocadastro/?tab=minhas_validacoes&situacao__exact=2',
                }
            )

        # minhas solicitações de abono parcial pendentes
        qtd_meus_abonos = SolicitacaoAbonoParcial.query_minhas_solicitacoes_pendentes(request.user).count()
        if qtd_meus_abonos:
            pendencias.append(
                {
                    'titulo': 'Meus Abonos Parciais',
                    'subtitulo': 'aguardando avaliação',
                    'qtd': qtd_meus_abonos,
                    'url': '/admin/ponto/solicitacaoabonoparcial/?tab=minhas_solicitacoes&situacao__exact=1',
                }
            )

        # solicitações de abono parcial de terceiros pendentes aguardando a minha avaliação
        qtd_abonos_terceiros = SolicitacaoAbonoParcial.query_solicitacoes_terceiros_pendentes(request.user).count()
        if qtd_abonos_terceiros:
            pendencias.append(
                {
                    'titulo': 'Abonos Parciais',
                    'subtitulo': 'a avaliar',
                    'qtd': qtd_abonos_terceiros,
                    'url': '/admin/ponto/solicitacaoabonoparcial/?tab=solicitacoes_terceiros_pendentes&situacao__exact=1',
                }
            )

        # minhas solicitações de revisão de abono de chefia pendentes
        vinculo_user = request.user.get_vinculo()
        qtd_minhas_revisoes = AbonoChefia.get_solicitacoes_revisao_abono_chefia(
            vinculo_solicitante=vinculo_user, situacao=SolicitacaoRevisaoAbonoChefia.SITUACAO_PENDENTE
        ).count()
        if qtd_minhas_revisoes:
            pendencias.append(
                {
                    'titulo': 'Minhas Revisões de Abonos de Chefia',
                    'subtitulo': 'aguardando avaliação',
                    'qtd': qtd_minhas_revisoes,
                    'url': '/admin/ponto/solicitacaorevisaoabonochefia/?tab=minhas_solicitacoes&situacao__exact=1',
                }
            )

        # solicitações de revisão de abono de chefia pendentes a avaliar
        qtd_revisoes_a_avaliar = AbonoChefia.get_solicitacoes_revisao_abono_chefia(
            vinculo_avaliador=vinculo_user, situacao=SolicitacaoRevisaoAbonoChefia.SITUACAO_PENDENTE
        ).count()
        if qtd_revisoes_a_avaliar:
            pendencias.append(
                {
                    'titulo': 'Revisões de Abonos de Chefia',
                    'subtitulo': 'a avaliar',
                    'qtd': qtd_revisoes_a_avaliar,
                    'url': '/admin/ponto/solicitacaorevisaoabonochefia/?tab=solicitacoes_terceiros_pendentes&situacao__exact=1',
                }
            )

    return pendencias


@layout.quadro('Frequências', icone='clock', pode_esconder=True)
def index_quadros_frequencias(quadro, request):
    hoje = datetime.now()

    if request.user.eh_servidor:
        # somente RH
        if request.user.has_perm('add_recessoopcao'):
            # tenta concluir opções abertas com tempo de escolha expirado
            RecessoOpcao.set_concluir_recessos_opcoes_pendentes()

            recessos_pendentes = RecessoOpcao.get_recessos_opcoes_periodo_escolha_expirado()
            if recessos_pendentes.exists():
                qtd = recessos_pendentes.count()
                quadro.add_item(
                    layout.ItemContador(
                        titulo='Opç{} de Compensação de Horário'.format(pluralize(qtd, 'ão,ões')),
                        subtitulo='Em aberto com período de escolha expirado',
                        qtd=qtd,
                        url=f'/admin/ponto/recessoopcao/?situacao__exact={RecessoOpcao.SITUACAO_ABERTO_PARA_ESCOLHA}',
                    )
                )

    if request.user.eh_servidor or (request.user.eh_prestador and not request.user.eh_usuarioexterno):
        vinculo = request.user.get_vinculo()
        # o vínculo do login decide, não a pessoa: deduplicada, a mesma pessoa pode ser servidor e prestador
        eh_prestador, eh_servidor = vinculo.eh_prestador(), vinculo.eh_servidor()
        funcionario = vinculo.relacionamento

        if eh_prestador or (eh_servidor and not funcionario.eh_aposentado):
            total_tempo_hoje = 0
            total_tempo_semana = 0
            frequencias_hoje = Frequencia.objects.none()
            for dia in datas_entre(primeiro_dia_da_semana(hoje), hoje):
                frequencias_dia = Frequencia.get_frequencias_por_data(vinculo, dia)
                if dia == hoje:
                    frequencias_hoje = frequencias_dia
                    if frequencias_hoje.exists():
                        tempo = 0
                        for par in agrupar_em_pares(frequencias_hoje.values_list('horario', flat=True)):
                            if len(par) == 2:
                                delta = par[1] - par[0]
                                segundos = delta.seconds
                            else:
                                segundos = 0
                            tempo += segundos
                        if frequencias_hoje.latest('horario').acao == 'E':
                            momento_da_entrada = frequencias_hoje.latest('horario').horario
                            momento_agora = datetime.now()
                            if momento_agora < momento_da_entrada:
                                momento_agora = datetime.now()
                            delta = momento_agora - momento_da_entrada
                            segundos = delta.seconds
                            tempo += segundos
                        total_tempo_hoje = time.strftime('%H:%M:%S', time.gmtime(tempo))
                        total_tempo_semana += tempo
                else:
                    total_tempo_semana += Frequencia.get_tempo_entre_frequencias(frequencias_dia)
            total_tempo_semana = formata_segundos(total_tempo_semana, '{h:02.0f}h ', '{m:02.0f}min ', '{s:02.0f}seg ', True)

            if frequencias_hoje or total_tempo_semana:
                if frequencias_hoje:
                    valor_hoje = ''
                    for i, f in enumerate(frequencias_hoje):
                        if i > 0:
                            valor_hoje += ' | '
                        if f.acao == 'E':
                            classe = 'true'
                        else:
                            classe = 'false'
                        valor_hoje += '{}: <span class="{}">{}</span>'.format(f.acao, classe, f.horario.strftime('%H:%M'))
                else:
                    valor_hoje = '<span class="false">Não há registro de frequências.</span>'

                quadro.add_item(layout.ItemLista(titulo='Hoje', valor=valor_hoje))
                if total_tempo_hoje:
                    quadro.add_item(layout.ItemLista(titulo='Total de Hoje', valor=total_tempo_hoje))
                if total_tempo_semana:
                    quadro.add_item(layout.ItemLista(titulo='Total da Semana', valor=total_tempo_semana))

            url_freq = '/ponto/frequencia_funcionario/'
            if eh_prestador:
                url_freq = '/ponto/frequencia_terceirizados/'
            quadro.add_item(layout.ItemAcessoRapido(titulo='Frequências', url=url_freq, icone='calendar-alt'))

            if not eh_prestador and not funcionario.eh_docente:
                eh_docente_tem_compensacoes_especificas = funcionario.eh_docente and RecessoOpcaoEscolhida.has_recessos_escolhidos(funcionario)
                if not funcionario.eh_docente or eh_docente_tem_compensacoes_especificas:
                    quadro.add_item(
                        layout.ItemAcessoRapido(titulo='Informar Compensação', url='/ponto/adicionar_compensacao_v2/', icone='exchange-alt')
                    )
                if Configuracao.get_valor_por_chave('ponto', 'subnets_ponto_online'):
                    quadro.add_item(
                        layout.ItemAcessoRapido(
                            titulo='Registrar Frequência', url='/ponto/registrar_frequencia_online/', icone=None, classe='success'
                        )
                    )

        if eh_servidor and not funcionario.eh_docente and not funcionario.eh_liberado_controle_frequencia():
            ###
            # débito da semana passada
            total_tempo_debito_pendente_semana_anterior = get_session_cache(
                request, 'total_tempo_debito_pendente_semana_anterior', get_total_tempo_debito_pendente_semana_anterior, 5 * 60
            )

            deb_semana_anterior, _ = total_tempo_debito_pendente_semana_anterior
            if deb_semana_anterior > 0:
                quadro.add_item(
                    layout.ItemLista(
                        grupo='Compensações:',
                        titulo='Débito Pendente da Semana Passada',
                        valor='<span class="{}">{}</span>'.format(
                            'false' if deb_semana_anterior > 0 else 'true',
                            formata_segundos(deb_semana_anterior, '{h:02.0f}h ', '{m:02.0f}min ', '{s:02.0f}seg ', True),
                        ),
                    )
                )

            ###
            # débito do mês passado
            total_tempo_debito_pendente_mes_anterior = get_session_cache(
                request, 'total_tempo_debito_pendente_mes_anterior', get_total_tempo_debito_pendente_mes_anterior, 5 * 60
            )

            deb_mes_anterior, deb_mes_anterior_ate_mes_atual = total_tempo_debito_pendente_mes_anterior
            if deb_mes_anterior > 0:
                css_span = 'false' if deb_mes_anterior > 0 else 'true'
                deb_span = formata_segundos(deb_mes_anterior, '{h:02.0f}h ', '{m:02.0f}min ', '{s:02.0f}seg ', True)
                quadro.add_item(
                    layout.ItemLista(
                        grupo='Compensações:', titulo='Débito Pendente do Mês Passado', valor=f'<span class="{css_span}">{deb_span}</span>'
                    )
                )

            ###
            # débito do mês corrente
            total_tempo_debito_pendente_mes_corrente = get_session_cache(
                request, 'total_tempo_debito_pendente_mes_corrente', get_total_tempo_debito_pendente_mes_corrente, 5 * 60
            )

            deb_mes_corrente = total_tempo_debito_pendente_mes_corrente
            if deb_mes_corrente > 0:
                deb_span = formata_segundos(deb_mes_corrente, '{h:02.0f}h ', '{m:02.0f}min ', '{s:02.0f}seg ', True)
                quadro.add_item(
                    layout.ItemLista(grupo='Compensações:', titulo='Débito Pendente do Mês Atual', valor=f'<span class="false">{deb_span}</span>')
                )

            ###
            # débito a ser compensado até o final do mês corrente
            css_span = '' if deb_mes_anterior == deb_mes_anterior_ate_mes_atual else 'false' if deb_mes_anterior_ate_mes_atual > 0 else 'true'
            deb_span = (
                ''
                if deb_mes_anterior == deb_mes_anterior_ate_mes_atual
                else '<strong>{}</strong>'.format(
                    formata_segundos(deb_mes_anterior_ate_mes_atual, '{h:02.0f}h ', '{m:02.0f}min ', '{s:02.0f}seg ', True)
                )
            )
            if css_span != '':
                quadro.add_item(
                    layout.ItemLista(
                        grupo='Compensações:',
                        titulo='Débito a ser compensado até {}'.format(get_data_ultimo_dia_mes_corrente().strftime('%d/%m/%Y')),
                        valor=f'<span class="{css_span}">{deb_span}</span>',
                    )
                )

            ###
            # saldo restante do mês corrente
            total_tempo_saldo_restante_mes_corrente = get_session_cache(
                request, 'total_tempo_saldo_restante_mes_corrente', get_total_tempo_saldo_restante_mes_corrente, 5 * 60
            )

            saldo_mes_atual = total_tempo_saldo_restante_mes_corrente
            if saldo_mes_atual > 0:
                saldo_span = formata_segundos(saldo_mes_atual, '{h:02.0f}h ', '{m:02.0f}min ', '{s:02.0f}seg ', True)
                quadro.add_item(
                    layout.ItemLista(grupo='Compensações:', titulo='Saldo Restante do Mês Atual', valor=f'<span class="true">{saldo_span}</span>')
                )

    return quadro


@layout.inscricao()
def index_inscricoes(request):
    inscricoes = []

    if request.user.eh_servidor:
        servidor = request.user.get_relacionamento()
        recessos_opcoes = RecessoOpcao.get_recessos_opcoes_com_dias_ou_periodos_a_escolher_hoje(servidor)
        for recesso_opcao in recessos_opcoes.get('com_dias_ou_periodos_a_escolher'):
            inscricoes.append(
                {
                    'titulo': f'<strong>{recesso_opcao}</strong>: Há dias/períodos disponíveis que você pode escolher.',
                    'url': '/ponto/escolher_dia_ou_periodo_de_recesso/',
                    'prazo': recesso_opcao.periodo_de_escolha_data_final.strftime('%d/%m/%Y'),
                }
            )
        for recesso_opcao in recessos_opcoes.get('com_dias_ou_periodos_a_editar'):
            validador_nao_definido = RecessoOpcaoEscolhida.objects.filter(
                recesso_opcao=recesso_opcao, funcionario=servidor, validador__isnull=True
            ).exists()

            inscricoes.append(
                {
                    'titulo': '<strong>{}</strong>: Você ainda pode <strong>editar</strong> os dias/períodos escolhidos.{}'.format(
                        recesso_opcao,
                        '<strong> Não é possível validar sua escolha, pois o validador não foi definido.</strong>.' if validador_nao_definido else '',
                    ),
                    'url': '/ponto/escolher_dia_ou_periodo_de_recesso/',
                    'prazo': recesso_opcao.periodo_de_escolha_data_final.strftime('%d/%m/%Y'),
                }
            )
        for recesso_opcao in recessos_opcoes.get('com_dias_ou_periodos_a_remarcar'):
            opcoes_escolhidas = RecessoOpcaoEscolhida.objects.filter(recesso_opcao=recesso_opcao, funcionario=servidor)
            for opcao_escolhida in opcoes_escolhidas:
                inscricoes.append(
                    {
                        'titulo': f'<strong>{recesso_opcao}</strong>: '
                        'Os dias/períodos que você escolheu <strong>não foram autorizados</strong>.'
                        '<strong>Remarque-os</strong> novamente.',
                        'url': f'/ponto/abrir_recesso_escolhido/{opcao_escolhida.id}/',
                        'prazo': recesso_opcao.periodo_de_escolha_data_final.strftime('%d/%m/%Y'),
                    }
                )

    return inscricoes


def frequencia_funcionario_get_contexto_relatorio_ponto_pessoa(request, form_frequencia):
    """
    Determinando a permissão para visualizar as frequências:
        - se o usuário logado é o mesmo usuário consultado
        - se o usuário logado tem a permissão "ponto.pode_ver_frequencia_todos"
            - o teste por grupo (RH Sistêmico e RH Campus é insuficiente,
              pois o grupo Auditor também pode ver as frequências de
              todos
        - se o usuário logado tem a permissão "pode_ver_frequencia_campus" e se é
          do mesmo campus do usuário consultado
        - se o usuário logado é chefe (função de chefia) do usuário consultado (no mesmo setor ou em setores descendentes)
    """

    usuario_logado = request.user.get_relacionamento()
    usuario_consultado = form_frequencia.cleaned_data['funcionario']

    # dias em que o usuário logado foi chefe do setor do usuário consultado
    dias_em_que_foi_chefe_setor = []

    # dias em que o usuário consultado estava no campus do usuário logado
    dias_em_que_estava_no_campus = []

    data_inicio = form_frequencia.cleaned_data['faixa_0']
    data_fim = form_frequencia.cleaned_data['faixa_1']

    usuario_logado_eh_usuario_consultado = usuario_consultado.pessoa_fisica.cpf == usuario_logado.pessoa_fisica.cpf
    usuario_logado_pode_ver_frequencias_todos = request.user.has_perm('ponto.pode_ver_frequencia_todos')
    usuario_logado_pode_ver_frequencias_campus = request.user.has_perm('ponto.pode_ver_frequencia_campus')
    usuario_logado_estah_campus_usuario_consultado = False
    usuario_logado_eh_chefe_usuario_consultado = False

    try:
        historicos_setores_usuario_consultado = usuario_consultado.historico_setor_suap(data_inicio, data_fim)
    except Exception:
        historicos_setores_usuario_consultado = []

    for historico_setor_usuario_consultado in historicos_setores_usuario_consultado:
        if not usuario_logado_eh_usuario_consultado and usuario_logado.setor.uo == historico_setor_usuario_consultado.setor.uo:
            usuario_logado_estah_campus_usuario_consultado = True

            data_inicio_setor = djtools_max(historico_setor_usuario_consultado.data_inicio_no_setor, data_inicio)
            data_fim_setor = djtools_min(historico_setor_usuario_consultado.data_fim_no_setor, data_fim)

            dias_em_que_estava_no_campus.extend(datas_entre(data_inicio_setor, data_fim_setor))

    try:
        funcoes_usuario_logado = usuario_logado.historico_funcao(data_inicio, data_fim).filter(
            funcao__codigo__in=Funcao.get_codigos_funcao_chefia(), setor_suap__isnull=False
        )
    except Exception:
        funcoes_usuario_logado = []

    for funcao_usuario_logado in funcoes_usuario_logado:
        for historico_setor_usuario_consultado in historicos_setores_usuario_consultado:
            usuario_logado_eh_o_chefe = (
                # não é ele mesmo
                not usuario_logado_eh_usuario_consultado
                and (
                    # usuário consultado está no mesmo setor
                    historico_setor_usuario_consultado.setor == funcao_usuario_logado.setor_suap
                    # usuário consultado está nos setores descendentes
                    or historico_setor_usuario_consultado.setor in funcao_usuario_logado.setor_suap.descendentes
                )
            )

            if usuario_logado_eh_o_chefe:
                usuario_logado_eh_chefe_usuario_consultado = True

                data_inicio_chefia = djtools_max(
                    historico_setor_usuario_consultado.data_inicio_no_setor, data_inicio, funcao_usuario_logado.data_inicio_funcao
                )
                data_fim_chefia = djtools_min(historico_setor_usuario_consultado.data_fim_no_setor, data_fim, funcao_usuario_logado.data_fim_funcao)

                dias_em_que_foi_chefe_setor.extend(datas_entre(data_inicio_chefia, data_fim_chefia))

    ##
    # o usuário logado não poderá visualizar os dias do usuário consultado
    # que estejam fora do período em que foi chefe

    if dias_em_que_foi_chefe_setor and dias_em_que_estava_no_campus:
        dias_em_que_foi_chefe_setor_min = djtools_min(*dias_em_que_foi_chefe_setor)
        dias_em_que_estava_no_campus_min = djtools_min(*dias_em_que_estava_no_campus)
        dias_em_que_estava_no_campus_max = djtools_max(*dias_em_que_estava_no_campus)

        if dias_em_que_foi_chefe_setor_min > dias_em_que_estava_no_campus_min:
            # redefine 'dias_em_que_estava_no_campus
            dias_em_que_estava_no_campus = datas_entre(dias_em_que_foi_chefe_setor_min, dias_em_que_estava_no_campus_max)

    ##

    pode_ver_frequencias = (
        usuario_logado_eh_usuario_consultado
        or usuario_logado_pode_ver_frequencias_todos
        or (usuario_logado_pode_ver_frequencias_campus and usuario_logado_estah_campus_usuario_consultado)
        or usuario_logado_eh_chefe_usuario_consultado
    )

    nao_pode_ver_frequencias_msgs = []
    if not pode_ver_frequencias:
        if not usuario_logado_eh_chefe_usuario_consultado:
            for historico_setor_usuario_consultado in historicos_setores_usuario_consultado:
                msg = f'{
                    FuncionalidadeApenasFuncoesChefiaException(usuario_logado.setor, historico_setor_usuario_consultado.setor, data_inicio, data_fim)
                }'
                nao_pode_ver_frequencias_msgs.append(msg)

    so_frequencias_em_que_era_chefe = False
    if not pode_ver_frequencias and dias_em_que_foi_chefe_setor:
        pode_ver_frequencias = True
        so_frequencias_em_que_era_chefe = True

    so_inconsistentes = form_frequencia.cleaned_data.get('so_inconsistentes', False)
    so_inconsistentes_apenas_esta_inconsistencia = None
    so_inconsistentes_situacao_abono = Frequencia.SITUACAO_INCONSISTENCIA_COM_OU_SEM_ABONO
    so_inconsistentes_situacao_debito = Frequencia.SITUACAO_INCONSISTENCIA_COM_DEBITO_COMPENSADO_OU_PENDENTE
    if so_inconsistentes:
        so_inconsistentes_apenas_esta_inconsistencia = form_frequencia.cleaned_data.get('so_inconsistentes_apenas_esta_inconsistencia', None)
        so_inconsistentes_situacao_abono = form_frequencia.cleaned_data.get(
            'so_inconsistentes_situacao_abono', Frequencia.SITUACAO_INCONSISTENCIA_COM_OU_SEM_ABONO
        )
        so_inconsistentes_situacao_debito = form_frequencia.cleaned_data.get(
            'so_inconsistentes_situacao_debito', Frequencia.SITUACAO_INCONSISTENCIA_COM_DEBITO_COMPENSADO_OU_PENDENTE
        )

    if so_inconsistentes:
        title = f'Frequências Inconsistentes do Funcionário: {usuario_consultado}'
    else:
        title = f'Frequências do Funcionário: {usuario_consultado}'

    return {
        'title': title,
        # período consultado
        'data_inicio': data_inicio,
        'data_fim': data_fim,
        # usuário logado
        'pode_ver_frequencias': pode_ver_frequencias,
        'nao_pode_ver_frequencias_msgs': nao_pode_ver_frequencias_msgs,
        'dias_em_que_foi_chefe_setor': dias_em_que_foi_chefe_setor,
        'so_frequencias_em_que_era_chefe': so_frequencias_em_que_era_chefe,
        # usuário consultado
        'servidor': usuario_consultado,
        'servidor_is_docente': usuario_consultado.eh_docente,
        'dias_em_que_estava_no_campus': dias_em_que_estava_no_campus,
        'so_inconsistentes': so_inconsistentes,
        'so_inconsistentes_apenas_esta_inconsistencia': so_inconsistentes_apenas_esta_inconsistencia,
        'so_inconsistentes_situacao_abono': so_inconsistentes_situacao_abono,
        'so_inconsistentes_situacao_debito': so_inconsistentes_situacao_debito,
    }


def frequencia_funcionario_get_relatorio_ponto_pessoa_info(
    request: HttpRequest, servidor: Servidor, data_inicio: date, data_fim: date
) -> dict[str, object] | HttpResponseForbidden:
    relacionamento_logado = request.user.get_relacionamento()

    escopo = ''

    if request.user.has_perm('ponto.pode_ver_frequencia_todos'):
        escopo = 'todos'
    elif request.user.has_perm('ponto.pode_ver_frequencia_campus') and mesmo_campus(servidor, relacionamento_logado):
        escopo = 'campus'
    elif request.user.has_perm('ponto.pode_ver_frequencias_enquanto_foi_chefe'):
        for setor in servidor.setor_suap_servidor_por_periodo(data_inicio, data_fim):
            if relacionamento_logado.eh_chefe_do_setor_periodo(setor, data_inicio, data_fim):
                escopo = 'chefe'

    if not escopo:
        return HttpResponseForbidden('Você não pode visualizar frequências desse servidor.')

    relatorio = Frequencia.relatorio_ponto_pessoa_novo(
        vinculo=servidor.get_vinculo(), servidor_logado=relacionamento_logado, data_ini=data_inicio, data_fim=data_fim, escopo=escopo
    )

    return locals()


@rtr()
@login_required
def frequencia_funcionario(request):
    title = 'Frequências por Servidor'

    if not request.user.has_perm('ponto.pode_ver_frequencia_propria') and not request.user.has_perm('ponto.pode_ver_frequencia_todos'):
        raise PermissionDenied('Usuário não pode ver frequencia própria.')

    if request.user.eh_docente and 'pit_rit' in settings.INSTALLED_APPS and Configuracao.get_valor_por_chave('pit_rit', 'ponto_docente_ativado'):
        form_class = FrequenciaDocenteFormFactory(request)
    else:
        form_class = FrequenciaFuncionarioFormFactory(request)

    form = form_class(request.GET or None)

    funcionario_logado = request.user.get_relacionamento()

    if not funcionario_logado.setor:
        raise PermissionDenied('Servidor não está associado a nenhum setor.')

    if form.is_valid():
        mostrar_texto_observacoes = form.cleaned_data.get('mostrar_texto_observacoes')

        escopo_relatorio_ponto_pessoa = frequencia_funcionario_get_contexto_relatorio_ponto_pessoa(request, form)

        pode_ver_frequencias = escopo_relatorio_ponto_pessoa['pode_ver_frequencias']
        if not pode_ver_frequencias:
            raise PermissionDenied(
                ' '.join(
                    [
                        'Você não tem permissão para visualizar a frequência deste servidor para o período informado.',
                        *escopo_relatorio_ponto_pessoa['nao_pode_ver_frequencias_msgs'],
                    ]
                )
            )

        servidor_is_docente = escopo_relatorio_ponto_pessoa['servidor_is_docente']
        if servidor_is_docente and 'pit_rit' in settings.INSTALLED_APPS and Configuracao.get_valor_por_chave('pit_rit', 'ponto_docente_ativado'):
            from pit_rit.views import frequencia_docente

            return frequencia_docente(request)

        title = escopo_relatorio_ponto_pessoa['title']
        servidor = escopo_relatorio_ponto_pessoa['servidor']
        data_inicio = escopo_relatorio_ponto_pessoa['data_inicio']
        data_fim = escopo_relatorio_ponto_pessoa['data_fim']
        dias_em_que_foi_chefe_setor = escopo_relatorio_ponto_pessoa['dias_em_que_foi_chefe_setor']
        so_frequencias_em_que_era_chefe = escopo_relatorio_ponto_pessoa['so_frequencias_em_que_era_chefe']
        dias_em_que_estava_no_campus = escopo_relatorio_ponto_pessoa['dias_em_que_estava_no_campus']
        so_inconsistentes = escopo_relatorio_ponto_pessoa['so_inconsistentes']
        so_inconsistentes_apenas_esta_inconsistencia = escopo_relatorio_ponto_pessoa['so_inconsistentes_apenas_esta_inconsistencia']
        so_inconsistentes_situacao_abono = escopo_relatorio_ponto_pessoa['so_inconsistentes_situacao_abono']
        so_inconsistentes_situacao_debito = escopo_relatorio_ponto_pessoa['so_inconsistentes_situacao_debito']

        relatorios = []

        try:
            relatorio_pessoa = Frequencia.relatorio_ponto_pessoa(
                vinculo=servidor.get_vinculo(),
                data_ini=data_inicio,
                data_fim=data_fim,
                dias_em_que_foi_chefe_setor=dias_em_que_foi_chefe_setor,
                so_frequencias_em_que_era_chefe=so_frequencias_em_que_era_chefe,
                dias_em_que_estava_no_campus=dias_em_que_estava_no_campus,
                so_inconsistentes=so_inconsistentes,
                trata_compensacoes=True,
                so_inconsistentes_apenas_esta_inconsistencia=so_inconsistentes_apenas_esta_inconsistencia,
                so_inconsistentes_situacao_abono=so_inconsistentes_situacao_abono,
                so_inconsistentes_situacao_debito=so_inconsistentes_situacao_debito,
            )
            Frequencia.relatorio_ponto_pessoa_update(relatorio_pessoa)

        except Exception as error:
            relatorio_pessoa = {}
            raise error

        # verifica se o período possui saldos produzidos de carga horária que podem ser utilizados
        if 'totais_compensacao' in relatorio_pessoa:
            ha_saldos_no_periodo = not relatorio_pessoa['totais_compensacao']['total_saldo_restante_is_zero']

        relatorios.append(relatorio_pessoa)

        hoje = datetime.date(datetime.today())
        if is_request_xls(request):
            xls = get_response_xls_registros_frequencias(relatorios)

            if xls:
                return xls
        return render('ponto/templates/relatorio_frequencia.html', locals())

    return locals()


@login_required()
def registrar_frequencia_online(request):
    subredes = Configuracao.get_valor_por_chave('ponto', 'subnets_ponto_online')
    if subredes:
        ip_valido = False
        ip = get_client_ip(request)
        for subrede in subredes.split(';'):
            ip_valido = ip_valido or ipaddress.ip_address(ip) in ipaddress.ip_network(subrede)
        if ip_valido:
            maquina = Maquina.objects.get_or_create(descricao='Ponto Online', ip='127.0.0.1', ativo=True, cliente_ponto=True)[0]
            Frequencia.insere_frequencia(request.user.get_vinculo(), maquina=maquina, ip=ip)
            return httprr('/', 'Frequência registrada com sucesso')
    return HttpResponseForbidden()


@rtr()
@login_required()
@permission_required('ponto.pode_ver_frequencia_todos, ponto.pode_ver_frequencia_campus, ponto.pode_ver_frequencias_enquanto_foi_chefe')
def ajax_frequencia_funcionario(request):
    servidor = get_object_or_404(Servidor.objects, matricula=request.GET.get('matricula', 0))
    data_inicio = datetime.strptime(request.GET.get('data_inicio', datetime.today().strftime('%d/%m/%Y')), '%d/%m/%Y').date()
    data_fim = datetime.strptime(request.GET.get('data_fim', datetime.today().strftime('%d/%m/%Y')), '%d/%m/%Y').date()
    relatorio_info = frequencia_funcionario_get_relatorio_ponto_pessoa_info(request, servidor, data_inicio, data_fim)
    if isinstance(relatorio_info, HttpResponseForbidden):
        return relatorio_info
    relatorio_info.update(locals())

    if is_request_xls(request):
        try:
            xls = get_response_xls_registros_frequencias([relatorio_info['relatorio']])

            if xls:
                return xls
        except Exception:
            pass

    return relatorio_info


@rtr()
@login_required
@permission_required('ponto.pode_ver_frequencia_todos, ponto.pode_ver_frequencia_campus, ponto.pode_ver_frequencias_enquanto_foi_chefe')
def relatorio_frequencias_setor(request):
    """Renderiza o relatório de frequências dos servidores de um setor.

    Args:
        request: Requisição HTTP contendo os parâmetros do formulário
            (setor, recursivo, faixa_0, faixa_1).

    Returns:
        dict: Variáveis de contexto para renderização do template.
    """
    permissoes = ['ponto.pode_ver_frequencia_todos', 'ponto.pode_ver_frequencia_campus', 'ponto.pode_ver_frequencias_enquanto_foi_chefe']
    title = 'Relatório de Frequências por Setor'
    FormClass = FrequenciasPorSetorFormFactory(request)
    form = FormClass(request.GET or None)
    funcionario_logado = request.user.get_relacionamento()

    if form.is_valid():
        setor = form.cleaned_data['setor']
        recursivo = form.cleaned_data['recursivo']
        faixa_0 = form.cleaned_data['faixa_0']
        faixa_1 = form.cleaned_data['faixa_1']

        title = f'Relatório de Frequências por Setor - {setor.sigla} {"e Setores descendentes" if form.cleaned_data["recursivo"] else ""}'

        servidores = setor.get_servidores_por_periodo(data_inicial=faixa_0, data_final=faixa_1, recursivo=recursivo)
        caminho_setor = setor.get_caminho_setor(setor_raiz_por_permissao_ponto(request))
        url_frequencias = 'relatorio_frequencias_setor'
        filhos = Setor.objects.suap_ativos().filter(pk__in=[s.pk for s in setor.filhos])

        if is_request_xls(request):
            return tasks.relatorio_frequencia_setor(servidores, faixa_0, faixa_1, request)

    return locals()


@rtr()
@login_required
@permission_required(
    'ponto.pode_ver_frequencia_terceirizados_todos, ponto.pode_ver_frequencia_terceirizados_campus, ponto.pode_ver_frequencia_terceirizados_setor'
)
def frequencia_terceirizados_setor(request):
    title = 'Frequências por Prestador de Serviço'

    FormClass = FrequenciaTerceirizadosFormFactory(request, TipoFormFrequenciaTerceirizados.POR_SETOR)
    form = FormClass(request.GET or None)
    if form.is_valid():
        ocupacao = form.cleaned_data['ocupacao']
        setor = form.cleaned_data['setor']
        funcionarios = Frequencia.relatorio_terceirizados(
            terceirizado=None,
            setor=form.cleaned_data['setor'],
            recursivo=form.cleaned_data['recursivo'],
            ocupacao=ocupacao,
            data_ini=form.cleaned_data['faixa_0'],
            data_fim=form.cleaned_data['faixa_1'],
        )
        data_ini = date_to_string(form.cleaned_data['faixa_0'])
        data_fim = date_to_string(form.cleaned_data['faixa_1'])

        situacao = 'Terceirizado'
        periodo = f'{data_ini} a {data_fim}'
        return render('ponto/templates/relatorio_frequencia_terceirizados.html', locals())
    else:
        return locals()


@rtr()
@login_required
@permission_required(
    'ponto.pode_ver_frequencia_terceirizados_todos, ponto.pode_ver_frequencia_terceirizados_campus, ponto.pode_ver_frequencia_terceirizados_setor, ponto.pode_ver_frequencia_terceirizados_propria'
)
def frequencia_terceirizados(request):
    title = 'Frequências por Prestador de Serviço'
    FormClass = FrequenciaTerceirizadosFormFactory(request, TipoFormFrequenciaTerceirizados.POR_TERCEIRIZADO)
    form = FormClass(request.GET or None)
    if form.is_valid():
        terceirizado = form.cleaned_data['terceirizado']
        funcionarios = Frequencia.relatorio_terceirizados(
            terceirizado=terceirizado,
            setor=None,
            recursivo=form.cleaned_data.get('recursivo'),
            data_ini=form.cleaned_data['faixa_0'],
            data_fim=form.cleaned_data['faixa_1'],
        )
        data_ini = date_to_string(form.cleaned_data['faixa_0'])
        data_fim = date_to_string(form.cleaned_data['faixa_1'])

        situacao = 'Terceirizado'
        periodo = f'{data_ini} a {data_fim}'
        return render('ponto/templates/relatorio_frequencia_terceirizados.html', locals())
    else:
        return locals()


@rtr()
@login_required
@permission_required('ponto.pode_ver_frequencia_todos, ponto.pode_ver_frequencia_campus, ponto.pode_ver_frequencias_enquanto_foi_chefe')
def frequencia_cargo_emprego(request):
    title = 'Frequência de Cargo/Emprego'
    FormClass = FrequenciaCargoEmpregoFormFactory()
    form = FormClass(request.GET or None)
    relatorios_visiveis = []
    if form.is_valid():
        return tasks.relatorio_frequencia_cargo_emprego(
            form.cleaned_data['cargo_emprego'], form.cleaned_data['faixa_0'], form.cleaned_data['faixa_1'], request
        )
    return locals()


@rtr()
@permission_required('ponto.pode_ver_frequencia_extra_noturna')
def frequencia_noturna(request):
    """
    Retorna as frequências noturnas extras (22h às 23h).
    """
    FormClass = FrequenciaNoturnaFormFactory(request.user)
    title = 'Frequências Noturnas'
    form = FormClass(request.GET or None)
    if form.is_valid():
        relatorios = Frequencia.relatorio_noturno(
            cargo_emprego=form.cleaned_data['cargo_emprego'],
            uo=form.cleaned_data['uo'],
            data_ini=form.cleaned_data['faixa_0'],
            data_fim=form.cleaned_data['faixa_1'],
        )

        data_ini = date_to_string(form.cleaned_data['faixa_0'])
        data_fim = date_to_string(form.cleaned_data['faixa_1'])
        situacao = 'Horário extra noturno'
        csv_link = '/ponto/frequencia_noturna_csv/?' + urlencode(request.GET)
        periodo = f'{data_ini} a {data_fim}'

        ponto_docente_via_app_pit_rit_is_ativado = 'pit_rit' in settings.INSTALLED_APPS and Configuracao.get_valor_por_chave(
            'pit_rit', 'ponto_docente_ativado'
        )
        if ponto_docente_via_app_pit_rit_is_ativado:
            faixa_0 = form.cleaned_data['faixa_0']
            faixa_1 = form.cleaned_data['faixa_1']
            relatorios = get_relatorios_ponto_adaptados_para_relatorios_pit_rit_ponto_docente(relatorios, faixa_0, faixa_1)

        return render('ponto/templates/relatorio_frequencia.html', locals())
    return locals()


@login_required
@permission_required('ponto.pode_ver_frequencia_extra_noturna')
def frequencia_noturna_csv(request):
    cargo_emprego = request.GET['cargo_emprego']
    uo = request.GET['uo']
    data_ini = str_to_dateBR(request.GET['faixa_0'])
    data_fim = str_to_dateBR(request.GET['faixa_1'])
    extrair_periodo(data_ini, data_fim)
    relatorio_extra_noturno = Frequencia.relatorio_noturno(cargo_emprego=cargo_emprego, uo=uo, data_ini=data_ini, data_fim=data_fim)
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="relatorio.csv"'
    writer = csv.writer(response)
    for f in relatorio_extra_noturno:
        funcionario = f['funcionario']
        frequencias = f['frequencias']
        num_frequencias = len(frequencias)
        total_periodo = f['total_periodo'].replace('s', '')
        servidor = [funcionario.matricula, funcionario.nome, num_frequencias, total_periodo]
        writer.writerow(servidor)
    return response


#################################################################
# Métodos para adicionar e remover Observação e Abono de Chefia #
#################################################################
@login_required
@rtr()
@csrf_exempt
def observacao_adicionar(request, data_observacao):
    title = 'Adicionar Observação de Ponto'
    observacao = Observacao(data=data_observacao, vinculo=request.user.get_vinculo())
    tem_abono = AbonoChefia.objects.filter(data=observacao.data, vinculo_pessoa=observacao.vinculo).exists()
    form = ObservacaoForm(request.POST or None, instance=observacao)
    if form.is_valid():
        form.save()
        return httprr('..', 'Observação salva com sucesso.')
    return locals()


@login_required
@rtr()
@csrf_exempt
def observacao_editar(request, observacao_id):
    title = 'Editar Observação de Ponto'
    observacao = get_object_or_404(Observacao, id=observacao_id, vinculo=request.user.get_vinculo())
    tem_abono = AbonoChefia.objects.filter(data=observacao.data, vinculo_pessoa=observacao.vinculo).exists()
    if not tem_abono:
        form = ObservacaoForm(request.POST or None, instance=observacao)
        if form.is_valid():
            form.save()
            return httprr('..', 'Observação editada com sucesso.')
        else:
            return locals()
    else:
        raise PermissionDenied('Acesso negado.')


@login_required
@rtr()
@csrf_exempt
def observacao_remover(request, observacao_id):
    # Nota: existe o filtro por pessoa para evitar que um usuário mal intencionado
    #       remova observações de outras pessoas
    observacao = get_object_or_404(Observacao, id=observacao_id, vinculo=request.user.get_vinculo())
    tem_abono = AbonoChefia.objects.filter(data=observacao.data, vinculo_pessoa=observacao.vinculo).exists()
    if not tem_abono:
        observacao.delete()
        return httprr(request.META.get('HTTP_REFERER', '..'), 'Observação excluída com sucesso.')
    else:
        return httprr(
            request.META.get('HTTP_REFERER', '..'),
            'Não foi possível excluir a observação. Existe uma ação da chefia imediata com relação à frequência inconsistente.',
            tag='failure',
        )


@rtr()
@login_required
def adicionar_abono_inconsistencia_frequencia(request, servidor_matricula, data_falta):
    servidor_faltoso = get_object_or_404(Servidor, matricula=servidor_matricula)
    servidor = request.user.get_relacionamento()
    data_inconsistencia = data_falta
    setor = servidor_faltoso.setor_suap_servidor_no_dia(data_inconsistencia)
    setor_chefe = servidor.setor

    abonos_parciais_pendentes = SolicitacaoAbonoParcial.query_solicitacoes_pendentes(servidor_faltoso).filter(data_aplicacao=data_inconsistencia)

    if abonos_parciais_pendentes.exists():
        if abonos_parciais_pendentes.count() == 1:
            return httprr(f'/ponto/avaliar_abono_parcial/{abonos_parciais_pendentes.first().id}/')
        else:
            return httprr(
                f'/ponto/avaliar_abono_parcial_lote/?{"&".join([f"ids={abono_parcial.id}" for abono_parcial in abonos_parciais_pendentes])}'
            )

    if not setor:
        raise PermissionDenied('Servidor não está associado a nenhum setor.')

    # - verifica se foi/é chefe no setor e no período indicado
    is_chefe_de_setor = servidor.eh_chefe_do_setor_periodo(setor, data_inconsistencia, data_inconsistencia)
    if not is_chefe_de_setor:
        raise FuncionalidadeApenasFuncoesChefiaException(setor_chefe, setor, data_inconsistencia, data_inconsistencia)

    if servidor_faltoso == servidor:
        raise PermissionDenied('Servidor não pode abonar suas próprias inconsistências.')

    if servidor_faltoso.eh_liberado_controle_frequencia():
        raise PermissionDenied(
            'São dispensados do controle de frequência os ocupantes de cargos de Direção - CD, hierarquicamente iguais ou superiores a DAS 4 ou CD 3'
        )

    contexto_compensacao = Contexto(
        servidor=servidor_faltoso.get_vinculo().relacionamento, periodo_data_inicial=data_inconsistencia, periodo_data_final=data_inconsistencia
    )

    frequencias_servidor = Frequencia.get_frequencias_por_data(servidor_faltoso.get_vinculo(), data_inconsistencia)

    inconsistencias = Frequencia.get_inconsistencias(
        servidor_faltoso.get_vinculo(), data_inconsistencia, data_inconsistencia, contexto_compensacao
    ).get(data_inconsistencia, [])

    tem_saida_antecipada = Frequencia.tem_saida_antecipada(servidor_faltoso.get_vinculo(), data_inconsistencia, contexto_compensacao)

    if inconsistencias:
        tipos_inconsistencias = inconsistencias
    else:
        if tem_saida_antecipada:
            tipos_inconsistencias = [Frequencia.INCONSISTENCIA_MENOR_JORNADA]
        else:
            raise PermissionDenied('Servidor não tem inconsistências para a data passada.')

    title = 'Avaliar Frequência de Servidor'

    observacoes = Observacao.objects.filter(vinculo=servidor_faltoso.get_vinculo(), data=data_inconsistencia)
    anexos = DocumentoAnexo.objects.filter(vinculo=servidor_faltoso.get_vinculo(), data=data_inconsistencia)

    jornada_trabalho, motivos_jornadas, _ = servidor_faltoso.get_jornadas_periodo_dict(data_inconsistencia, data_inconsistencia)
    jornada_trabalho = jornada_trabalho.get(data_inconsistencia)

    informacao_registro = []
    for inconsistencia in tipos_inconsistencias:
        informacao_registro.append(Frequencia.DISPLAY_INCONSISTENCIA[inconsistencia])

    inconsistencias_detalhes = Frequencia.get_detalhamento_inconsistencias(
        tipos_inconsistencias, data_inconsistencia, data_inconsistencia, contexto_compensacao
    )

    abono = AbonoChefia(
        vinculo_pessoa=servidor_faltoso.get_vinculo(), data=data_inconsistencia, vinculo_chefe_imediato=servidor.get_vinculo(), acao_abono=None
    )
    FormClass = AbonoChefiaFormFactory(tipos_inconsistencias)
    form = FormClass(request.POST or None, instance=abono)
    descricao_abonos = form.descricao_abonos
    if form.is_valid():
        form.save()
        ancora = servidor_faltoso.matricula + data_inconsistencia.strftime('%d/%m/%Y') or ''
        return httprr(
            '..',
            'Abono de inconsistência salvo com sucesso.',
            anchor=ancora,
            close_popup=True,
            close_popup_and_force_reload=request.GET.get('_popup_success_reload') == '1',
        )

    return locals()


@rtr()
@login_required
@csrf_exempt
def adicionar_abono_inconsistencia_frequencia_lote(request):
    if 'frequencias_dias' not in request.GET:
        return httprr('..', 'Nenhum dia escolhido para avaliação.', tag='error', close_popup=True)

    title = 'Avaliar Frequência em Lote de Servidor'

    frequencias_dias = request.GET.getlist('frequencias_dias')

    ancora = None
    servidor_matricula = None
    tipos_inconsistencias = []
    dias = []

    for index, value in enumerate(frequencias_dias):
        if len(value.split('_')) < 2:
            return httprr('..', 'Entrada incorreta de dados!', tag='error', close_popup=True)
        else:
            if index == 0:
                servidor_matricula = value.split('_')[0]
                servidor_faltoso = get_object_or_404(Servidor, matricula=servidor_matricula)
                servidor = request.user.get_relacionamento()
                ancora = servidor_faltoso.matricula or ''
                if servidor_faltoso == servidor:
                    return httprr('..', 'Servidor não pode abonar suas próprias inconsistências.', tag='error', anchor=ancora, close_popup=True)
                if servidor_faltoso.eh_liberado_controle_frequencia():
                    return httprr(
                        '..',
                        'São dispensados do controle de frequência os ocupantes de cargos de Direção - CD, hierarquicamente iguais ou superiores a DAS 4 ou CD - 3',
                        tag='error',
                        anchor=ancora,
                        close_popup=True,
                    )
            elif servidor_matricula != value.split('_')[0]:
                return httprr('..', 'Erro: Há mais de um servidor na validação!', tag='error', anchor=ancora, close_popup=True)

            data_falta = value.split('_')[1]
            data_inconsistencia = datetime.strptime(data_falta, '%d%m%Y').date()
            ancora = servidor_faltoso.matricula + data_inconsistencia.strftime('%d/%m/%Y') or ''

            contexto_compensacao = Contexto(
                servidor=servidor_faltoso.get_vinculo().relacionamento,
                periodo_data_inicial=data_inconsistencia,
                periodo_data_final=data_inconsistencia,
            )

            frequencias_servidor = Frequencia.get_frequencias_por_data(servidor_faltoso.get_vinculo(), data_inconsistencia)

            inconsistencias = Frequencia.get_inconsistencias(
                servidor_faltoso.get_vinculo(), data_inconsistencia, data_inconsistencia, contexto_compensacao
            ).get(data_inconsistencia, [])

            tem_saida_antecipada = Frequencia.tem_saida_antecipada(servidor_faltoso.get_vinculo(), data_inconsistencia, contexto_compensacao)

            if not inconsistencias and not tem_saida_antecipada:
                return httprr(
                    '..',
                    'Servidor não tem inconsistências para algumas das datas marcadas. Refaça a marcação.',
                    tag='error',
                    anchor=ancora,
                    close_popup=True,
                )

            observacoes_servidor = Observacao.objects.filter(vinculo=servidor_faltoso.get_vinculo(), data=data_inconsistencia)
            anexos = DocumentoAnexo.objects.filter(vinculo=servidor_faltoso.get_vinculo(), data=data_inconsistencia)

            jornada_trabalho, motivos_jornadas, _ = servidor_faltoso.get_jornadas_periodo_dict(data_inconsistencia, data_inconsistencia)
            jornada_trabalho = jornada_trabalho.get(data_inconsistencia)

            informacao_registro = []
            for inconsistencia in inconsistencias:
                informacao_registro.append(Frequencia.DISPLAY_INCONSISTENCIA[inconsistencia])

            inconsistencias_detalhes = Frequencia.get_detalhamento_inconsistencias(
                inconsistencias, data_inconsistencia, data_inconsistencia, contexto_compensacao
            )

            dias.append(
                {
                    'data': data_inconsistencia,
                    'jornada_trabalho': jornada_trabalho,
                    'frequencias_servidor': frequencias_servidor,
                    'observacoes_servidor': observacoes_servidor,
                    'anexos': anexos,
                    'informacao_registro': informacao_registro,
                    'inconsistencias_detalhes': inconsistencias_detalhes,
                }
            )

            tipos_inconsistencias_dia = inconsistencias

            if index == 0:
                tipos_inconsistencias = tipos_inconsistencias_dia
            elif tipos_inconsistencias != tipos_inconsistencias_dia:
                return httprr(
                    '..', 'Devem ser selecionados somente dias com as mesmas inconsistências.', tag='error', anchor=ancora, close_popup=True
                )

            setor = servidor_faltoso.setor_suap_servidor_no_dia(data_inconsistencia)
            setor_chefe = servidor.setor
            if not setor:
                return httprr('..', 'Servidor não está associado a nenhum setor.', tag='error', anchor=ancora, close_popup=True)

            # - verifica se foi/é chefe no setor e no período indicado
            is_chefe_de_setor = servidor.eh_chefe_do_setor_periodo(setor, data_inconsistencia, data_inconsistencia)
            if not is_chefe_de_setor:
                return httprr('..', 'Funcionalidade acessada apenas por FGs ou CDs.', tag='error', anchor=ancora, close_popup=True)

            abonos_parciais_pendentes = SolicitacaoAbonoParcial.query_solicitacoes_pendentes(servidor_faltoso).filter(
                data_aplicacao=data_inconsistencia
            )

            if abonos_parciais_pendentes.exists():
                if abonos_parciais_pendentes.count() == 1:
                    return httprr(f'/ponto/avaliar_abono_parcial/{abonos_parciais_pendentes.first().id}/')
                else:
                    return httprr(
                        f'/ponto/avaliar_abono_parcial_lote/?{"&".join([f"ids={abono_parcial.id}" for abono_parcial in abonos_parciais_pendentes])}'
                    )

    FormClass = AbonoChefiaLoteFormFactory(tipos_inconsistencias, frequencias_dias)
    form = FormClass(request.POST or None)
    descricao_abonos = form.descricao_abonos

    if form.is_valid():
        data_anchor = datetime.today()
        ch_descontada_hms: timedelta = form.cleaned_data.get('ch_descontada_hms', timedelta(0))

        for dia in dias:
            data_anchor = dia['data']
            abono = AbonoChefia.objects.create(
                vinculo_pessoa=servidor_faltoso.get_vinculo(),
                vinculo_chefe_imediato=servidor.get_vinculo(),
                data=dia['data'],
                descricao=request.POST['descricao'],
                acao_abono=request.POST['acao_abono'],
                ch_descontada=ch_descontada_hms.total_seconds() if ch_descontada_hms else None,
            )

        ancora = servidor_faltoso.matricula + data_anchor.strftime('%d/%m/%Y') or ''

        return httprr(
            '..',
            'Abonos de inconsistência salvos com sucesso.',
            anchor=ancora,
            close_popup=True,
            close_popup_and_force_reload=request.GET.get('_popup_success_reload') == '1',
        )

    return locals()


####################################
# Funções para o terminal de ponto #
####################################


@transaction.atomic
def get_dump_terminal_ponto(request):
    """
    Retorna ``dump_terminal.zip``, que é um dump que corresponde à tabela
    ``pessoa`` dos terminais de ponto eletrônico.
    """
    try:
        m = Maquina.objects.get(ip=get_client_ip(request), cliente_ponto=True, ativo=True)
    except Maquina.DoesNotExist:
        raise PermissionDenied('Máquina sem permissões')

    ARQUIVO_DUMP = '/tmp/tabela_terminal.zip'
    if _arquivo_zip_valido(ARQUIVO_DUMP) and datetime.fromtimestamp(stat(ARQUIVO_DUMP)[-1]).date() == date.today():
        # Se existe um arquivo gerado no dia, este não precisa ser criado
        pass

    else:
        # Não existe arquivo gerado no dia, então precisa ser criado
        cursor = connection.cursor()

        # The Servidor model does not have a direct 'username' field; usernames are on the related User
        # via pessoa_fisica -> vinculo -> user. Annotate the username and nome from related PessoaFisica
        qs = (
            Servidor.objects.annotate(setor_sigla=Coalesce('setor__sigla', Value('     ')))
            .filter(ativo=True, pessoa_fisica__vinculo__user__username__isnull=False)
            .exclude(pessoa_fisica__vinculo__user__username='')
            .annotate(
                username=F('pessoa_fisica__vinculo__user__username'),
                nome=F('pessoa_fisica__nome'),
                template=F('pessoa_fisica__template'),
                tem_digital_fraca=F('pessoa_fisica__tem_digital_fraca'),
            )
            .values('username', 'nome', 'template', 'tem_digital_fraca', 'setor_sigla')
        )
        query = get_real_sql(qs, remove_order_by=True)

        query = 'CREATE TEMP TABLE tabela_terminal_ponto AS ' + query
        cursor.execute(query)
        # Gerando o dump
        dump_file = open('/tmp/tabela_terminal.copy', 'wb')
        with cursor.copy('COPY tabela_terminal_ponto TO STDOUT') as copy:
            dump_file.writelines(copy)
        dump_file.close()

        # Removendo tabela temporária
        cursor.execute('DROP TABLE tabela_terminal_ponto')

        # Compactando o dump
        arquivo_dump_temporario = tempfile.NamedTemporaryFile(delete=False).name
        with zipfile.ZipFile(arquivo_dump_temporario, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.write('/tmp/tabela_terminal.copy', 'tabela_terminal.copy')
        os.replace(arquivo_dump_temporario, ARQUIVO_DUMP)

    MaquinaLog.objects.create(maquina=m, operacao='ponto_get_dump_terminal_ponto')

    response = FileResponse(open(ARQUIVO_DUMP, 'rb'), content_type='application/zip')
    response['Content-Disposition'] = 'attachment; filename=dump_terminal.zip'
    return response


def _adicionar_foto_terminal_ponto(zip_file: zipfile.ZipFile, papel: object, matricula: str) -> None:
    # papel = Servidor ou PrestadorServico; .foto roteia por AbstractRelacionamento.foto → Vinculo.foto
    foto = getattr(papel, 'foto', None)
    if not foto:
        return

    remote_filename = foto.name.replace('fotos/', 'fotos/150x200/')
    local_filename = cache_file(remote_filename)
    if not local_filename or not os.path.exists(local_filename):
        return

    zip_file.write(local_filename, f'{matricula}.jpg')
    os.unlink(local_filename)


def _arquivo_zip_valido(caminho_arquivo: str) -> bool:
    return exists(caminho_arquivo) and zipfile.is_zipfile(caminho_arquivo)


@transaction.atomic
def get_fotos_terminal_ponto(request: HttpRequest) -> HttpResponse:
    """
    Retorna ``fotos.zip``, que é um dump que vai servir para definir as fotos
    das pessoas nos terminais de ponto eletrônico.
    """
    try:
        m = Maquina.objects.get(ip=get_client_ip(request), cliente_ponto=True, ativo=True)
    except Maquina.DoesNotExist:
        raise PermissionDenied('Máquina sem permissões')

    ARQUIVO_DUMP = TERMINAL_PONTO_FOTOS_DUMP

    if _arquivo_zip_valido(ARQUIVO_DUMP) and datetime.fromtimestamp(stat(ARQUIVO_DUMP)[-1]).date() == date.today():
        # Se existe um arquivo gerado no dia, este não precisa ser criado
        pass

    else:
        arquivo_dump_temporario = tempfile.NamedTemporaryFile(delete=False).name
        with zipfile.ZipFile(arquivo_dump_temporario, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # foto migrou de PessoaFisica para Vinculo; filtra/acessa pelo papel via AbstractRelacionamento.foto
            for s in Servidor.objects.ativos().filter(vinculos__foto__isnull=False):
                _adicionar_foto_terminal_ponto(zip_file, s, s.matricula)
            for s in PrestadorServico.objects.filter(ativo=True).filter(vinculos__foto__isnull=False):
                _adicionar_foto_terminal_ponto(zip_file, s, s.matricula)
        os.replace(arquivo_dump_temporario, ARQUIVO_DUMP)

    MaquinaLog.objects.create(maquina=m, operacao='ponto_get_fotos_terminal_ponto')

    response = FileResponse(open(ARQUIVO_DUMP, 'rb'), content_type='application/zip')
    response['Content-Disposition'] = 'attachment; filename=fotos.zip'
    return response


##########################################################################################
# COMPENSAÇÃO DE HORÁRIO
##########################################################################################


@rtr()
@login_required
@permission_required('ponto.change_horariocompensacao')
def abrir_compensacao_horario(request, compensacao_horario_id):
    title = 'Informe de Compensação de Horário'

    compensacao = get_object_or_404(HorarioCompensacao, pk=compensacao_horario_id)

    usuario_logado = request.user.get_relacionamento()
    usuario_logado_is_informante = usuario_logado == compensacao.funcionario

    if compensacao.chefe:
        usuario_logado_is_chefe = usuario_logado == compensacao.chefe
    else:
        compensacao.set_chefe()
        usuario_logado_is_chefe = usuario_logado == compensacao.chefe

    if not (usuario_logado_is_informante or usuario_logado_is_chefe):
        raise PermissionDenied

    return locals()


@rtr()
@login_required
@permission_required('ponto.change_horariocompensacao')
def editar_obs_compensacao_horario(request, compensacao_horario_id):
    compensacao = get_object_or_404(HorarioCompensacao, pk=compensacao_horario_id)
    title = f'Editar Observações de {compensacao}'
    usuario_logado = request.user.get_relacionamento()
    usuario_logado_is_informante = usuario_logado == compensacao.funcionario
    if not usuario_logado_is_informante or compensacao.situacao == HorarioCompensacao.SITUACAO_INVALIDO:
        raise PermissionDenied
    #
    form = HorarioCompensacaoEditarObservacoesPontoForm(request.POST or None, instance=compensacao)
    #
    if form.is_valid() and form.save():
        return httprr(f'/ponto/abrir_compensacao_horario/{compensacao_horario_id}/', 'Observações editadas com sucesso.')
    return locals()


@rtr()
@login_required
@permission_required('ponto.add_recessoopcao')
def abrir_opcao_recesso(request, recesso_opcao_id):
    title = 'Opção de Compensação Específica'
    recesso_opcao = get_object_or_404(RecessoOpcao, pk=recesso_opcao_id)
    recesso_opcao_periodo_escolhas_aberto_e_expirado = (
        recesso_opcao.is_aberto_para_escolhas_de_datas and not recesso_opcao.is_no_periodo_para_escolhas_de_datas
    )
    recesso_opcao_com_pendencias_de_validacao_remarcacao = (
        recesso_opcao_periodo_escolhas_aberto_e_expirado
        and recesso_opcao.recessoopcaoescolhida_set.filter(
            validacao__in=[RecessoOpcaoEscolhida.VALIDACAO_AGUARDANDO, RecessoOpcaoEscolhida.VALIDACAO_NAO_AUTORIZADO_REMARCAR]
        ).exists()
    )
    return locals()


@rtr()
@login_required
@permission_required('ponto.add_recessoopcao')
def excluir_opcao_recesso(request, recesso_opcao_id):
    recesso_opcao = get_object_or_404(RecessoOpcao, pk=recesso_opcao_id)

    pode_excluir, msg = recesso_opcao.pode_excluir()

    if not pode_excluir:
        return httprr(
            f'/ponto/abrir_opcao_recesso/{recesso_opcao.id}/',
            msg,
            tag='error',
        )

    recesso_opcao.delete()

    return httprr('/admin/ponto/recessoopcao/', 'Opção de Compensação Excluída')


@rtr('adicionar_dia_de_recesso_ou_periodo_de_compensacao.html')
@login_required
@permission_required('ponto.add_recessoopcao')
def adicionar_dia_de_recesso(request, recesso_opcao_id):
    concluir = request.POST.get('concluir') == '1'

    if concluir:
        return httprr('..')

    title = 'Adicionar Dias a Compensar'

    recesso_opcao = get_object_or_404(RecessoOpcao, pk=recesso_opcao_id)

    data_unica = request.POST.get('numero_de_datas') == '1' or request.GET.get('numero_de_datas') == '1'
    data_periodo = request.POST.get('numero_de_datas') == '2' or request.GET.get('numero_de_datas') == '2'

    if not data_unica and not data_periodo:
        data_unica = True

    form = RecessoDiaAddForm(request.POST or None, recesso_opcao=recesso_opcao, is_data_unica=data_unica)

    form.SUBMIT_LABEL = 'Salvar e Continuar'

    form.EXTRA_BUTTONS = [
        {
            'type': 'button',
            'value': 'Salvar e Fechar',
            'onclick': 'salvar_e_concluir();',  # função javascript definida no template
        },
        {
            'type': 'button',
            'value': 'Fechar',
            'onclick': 'concluir();',  # função javascript definida no template
        },
    ]

    salvar_e_concluir = request.POST.get('salvar_e_concluir') == '1'

    if form.is_valid() and form.save():
        if salvar_e_concluir:
            return httprr('..')
        else:
            return httprr(
                '.',
                'Salvo com sucesso. Já adicionados: {}'.format(', '.join([str(dia_recesso) for dia_recesso in recesso_opcao.dias_do_recesso.all()])),
                get_params=f'numero_de_datas={"1" if data_unica else "2"}&_popup=1',
            )

    periodo_dias_label = 'Dias sequenciais'

    return locals()


@rtr()
@login_required
@permission_required('ponto.add_recessoopcao')
def excluir_dia_de_recesso(request, recesso_dia_id):
    recesso_dia = get_object_or_404(RecessoDia, pk=recesso_dia_id)

    dia_excluido = str(recesso_dia)
    recesso_opcao_id = recesso_dia.recesso_opcao.id

    if not recesso_dia.pode_excluir():
        return httprr(
            f'/ponto/abrir_opcao_recesso/{recesso_opcao_id}/',
            f'Exclusão não permitida. O dia {dia_excluido} foi escolhido por um ou mais servidores, com validação dos chefes imediatos.',
            tag='error',
        )

    recesso_dia.delete()

    return httprr(f'/ponto/abrir_opcao_recesso/{recesso_opcao_id}/', f'Dia {dia_excluido} removido com sucesso.')


@rtr()
@login_required
@permission_required('ponto.add_recessoopcao')
def adicionar_periodo_de_recesso(request, recesso_opcao_id):
    recesso_opcao = get_object_or_404(RecessoOpcao, pk=recesso_opcao_id)

    form = RecessoPeriodoAddForm(request.POST or None, recesso_opcao=recesso_opcao)

    form.SUBMIT_LABEL = 'Salvar'

    if form.is_valid():
        form.save()
        return httprr('..')

    title = 'Adicionar Períodos a Compensar'

    return locals()


@rtr()
@login_required
@permission_required('ponto.add_recessoopcao')
def excluir_periodo_de_recesso(request, recesso_periodo_id):
    recesso_periodo = get_object_or_404(RecessoPeriodo, pk=recesso_periodo_id)

    periodo_excluido = str(recesso_periodo)
    recesso_opcao_id = recesso_periodo.recesso_opcao.id

    if not recesso_periodo.pode_excluir():
        return httprr(
            f'/ponto/abrir_opcao_recesso/{recesso_opcao_id}/',
            f'Exclusão não permitida. O período {periodo_excluido} foi escolhido por um ou mais servidores, com validação dos chefes imediatos.',
            tag='error',
        )

    recesso_periodo.delete()

    return httprr(f'/ponto/abrir_opcao_recesso/{recesso_opcao_id}/', f'Período {periodo_excluido} removido com sucesso.')


@rtr('adicionar_dia_de_recesso_ou_periodo_de_compensacao.html')
@login_required
@permission_required('ponto.add_recessoopcao')
def adicionar_periodo_de_compensacao(request, recesso_opcao_id):
    concluir = request.POST.get('concluir') == '1'

    if concluir:
        return httprr('..')

    title = 'Adicionar Períodos de Compensação'

    recesso_opcao = get_object_or_404(RecessoOpcao, pk=recesso_opcao_id)

    data_unica = request.POST.get('numero_de_datas') == '1' or request.GET.get('numero_de_datas') == '1'
    data_periodo = request.POST.get('numero_de_datas') == '2' or request.GET.get('numero_de_datas') == '2'
    if not data_unica and not data_periodo:
        data_periodo = True

    form = RecessoPeriodoCompensacaoAddForm(request.POST or None, recesso_opcao=recesso_opcao, is_data_unica=data_unica)

    form.SUBMIT_LABEL = 'Salvar e Continuar'

    form.EXTRA_BUTTONS = [
        {
            'type': 'button',
            'value': 'Salvar e Fechar',
            'onclick': 'salvar_e_concluir();',  # função javascript definida no template
        },
        {
            'type': 'button',
            'value': 'Fechar',
            'onclick': 'concluir();',  # função javascript definida no template
        },
    ]

    salvar_e_concluir = request.POST.get('salvar_e_concluir') == '1'

    if form.is_valid() and form.save():
        if salvar_e_concluir:
            return httprr('..')
        else:
            return httprr(
                '.',
                'Salvo com sucesso. Já adicionados: {}'.format(', '.join([str(periodo) for periodo in recesso_opcao.periodos_de_compensacao.all()])),
                get_params=f'numero_de_datas={"1" if data_unica else "2"}&_popup=1',
            )

    periodo_dias_label = 'Período de dias'

    return locals()


@rtr()
@login_required
@permission_required('ponto.add_recessoopcao')
def excluir_periodo_de_compensacao(request, periodo_de_compensacao_id):
    periodo_de_compensacao = get_object_or_404(RecessoPeriodoCompensacao, pk=periodo_de_compensacao_id)
    periodo_excluido = str(periodo_de_compensacao)
    recesso_opcao_id = periodo_de_compensacao.recesso_opcao.id
    periodo_de_compensacao.delete()
    return httprr(f'/ponto/abrir_opcao_recesso/{recesso_opcao_id}/', f'Período de Compensação {periodo_excluido} removido com sucesso.')


@rtr()
@login_required
@permission_required('ponto.add_recessoopcao')
def definir_periodo_escolha_recesso(request, recesso_opcao_id):
    title = 'Definir o Período de Escolha dos Dias a Compensar'
    recesso_opcao = get_object_or_404(RecessoOpcao, pk=recesso_opcao_id)
    form = RecessoPeriodoEscolhaForm(request.POST or None, instance=recesso_opcao)
    if form.is_valid() and form.save():
        if form.instance.is_definido_periodo_de_escolha:
            return httprr('..', 'Período de Escolha definido com sucesso.')
        return httprr('..')
    return locals()


@rtr()
@login_required
@permission_required('ponto.add_recessoopcao')
def liberar_escolha_recesso(request, recesso_opcao_id):
    recesso_opcao = get_object_or_404(RecessoOpcao, pk=recesso_opcao_id)
    try:
        recesso_opcao.liberar_para_escolha_dos_dias_do_recesso()
        return httprr(f'/ponto/abrir_opcao_recesso/{recesso_opcao_id}/', 'Período de Escolha liberado com sucesso.')
    except Exception as Erro:
        return httprr(f'/ponto/abrir_opcao_recesso/{recesso_opcao_id}/', str(Erro), tag='error')


@rtr()
@login_required
@permission_required('ponto.add_recessoopcao')
def retornar_a_fase_de_cadastro(request, recesso_opcao_id):
    recesso_opcao = get_object_or_404(RecessoOpcao, pk=recesso_opcao_id)
    recesso_opcao.retornar_a_fase_de_cadastro()
    return httprr(f'/ponto/abrir_opcao_recesso/{recesso_opcao_id}/', 'Opção de Compensação Em Fase de Cadastro novamente.')


@rtr('fechar_cadastro_e_escolha_automatica.html')
@login_required
@permission_required('ponto.add_recessoopcao')
def fechar_cadastro_e_escolha(request, recesso_opcao_id):
    recesso_opcao = get_object_or_404(RecessoOpcao, pk=recesso_opcao_id)
    try:
        pode_fechar, eh_escolha_automatica, msg_erro = recesso_opcao.pode_fechar_cadastro_e_escolha()
        if msg_erro:
            raise Exception(msg_erro)
        if pode_fechar:
            if eh_escolha_automatica:
                servidores_alvo_ids = recesso_opcao.get_servidores().only('id').values_list('id', flat=True)
                servidores_alvo_count = len(servidores_alvo_ids)
                title = f'Conclusão: {recesso_opcao}'
                return locals()  # renderiza a página de feedback do processamento do público alvo
            else:
                recesso_opcao.fechar_cadastro_e_escolha()
                return httprr(f'/ponto/abrir_opcao_recesso/{recesso_opcao_id}/', 'Cadastramento concluído.')
        else:
            raise Exception('Ocorreu um erro. Tente novamente.')
    except Exception as erro:
        return httprr(f'/ponto/abrir_opcao_recesso/{recesso_opcao_id}/', str(erro), tag='error')


@login_required
@permission_required('ponto.add_recessoopcao')
@csrf_exempt
def processar_fechar_cadastro_e_escolha_automatica(request, recesso_opcao_id):
    recesso_opcao = get_object_or_404(RecessoOpcao, pk=recesso_opcao_id)

    processamento_concluido = request.POST.get('processamento_concluido', '0') == '1'

    if processamento_concluido:
        recesso_opcao.fechar_cadastro_e_escolha()
        return JsonResponse({'ok': True})

    recesso_opcao_dias_definidos_ids = recesso_opcao.dias_do_recesso.all().values_list('id', flat=True)
    recesso_opcao_periodos_definidos_ids = recesso_opcao.periodos_do_recesso.all().values_list('id', flat=True)

    servidores = Servidor.objects.filter(pk__in=list(request.POST.get('servidores_ids', '').split(',')))
    servidores = servidores.only('pessoa_fisica__nome', 'matricula')

    class ResultServidorInfo:
        servidor: str
        error: bool
        message: str

    result = {'data': []}

    for servidor in servidores:
        info = ResultServidorInfo()
        info.servidor = f'{servidor.pessoa_fisica.nome} ({servidor.matricula})'

        try:
            recesso_opcao.escolher_dias_automaticamente([servidor], recesso_opcao_dias_definidos_ids, recesso_opcao_periodos_definidos_ids)
            info.error = False
            info.message = ''
        except Exception as erro:
            info.error = True
            info.message = f'{erro}'

        result['data'].append(info.__dict__)

    response = JsonResponse(result)

    return response


@rtr()
@login_required
@permission_required('ponto.add_recessoopcaoescolhida')
def escolher_dia_ou_periodo_de_recesso(request):
    title = 'Escolher Dias/Períodos'
    try:
        form = get_type_form_dias_ou_periodos_escolhidos(request)(request.POST or None)
        if form.is_valid():
            form.save()
            return httprr('/admin/ponto/recessoopcaoescolhida/?tab=meus_recessos', 'Dias/Períodos salvos com sucesso.')
    except Exception as erro:
        return httprr('/admin/ponto/recessoopcaoescolhida/?tab=meus_recessos', str(erro), tag='error')
    return locals()


@rtr()
@login_required
@permission_required('ponto.add_recessoopcaoescolhida')
def abrir_recesso_escolhido(request, recesso_opcao_escolhida_id):
    title = 'Compensação Específica'

    recesso_opcao_escolhida = get_object_or_404(RecessoOpcaoEscolhida, pk=recesso_opcao_escolhida_id)

    if not recesso_opcao_escolhida.dias_efetivos_a_compensar_estah_resolvido:
        recesso_opcao_escolhida.dias_efetivos_a_compensar()

    relacionamento = request.user.get_relacionamento()
    usuario_logado_is_solicitante = relacionamento.pk == recesso_opcao_escolhida.funcionario.pk
    usuario_logado_is_chefe, chefes = recesso_opcao_escolhida.is_chefe(relacionamento, retornar_chefes=True)
    chefes_qtd = len(chefes)

    if not (usuario_logado_is_solicitante or usuario_logado_is_chefe):
        raise PermissionDenied

    periodos_compensacao = list(recesso_opcao_escolhida.recesso_opcao.periodos_de_compensacao.all())
    periodo_compensacao_inicio = min(periodo.data_inicial for periodo in periodos_compensacao)
    periodo_compensacao_fim = max(periodo.data_final for periodo in periodos_compensacao)

    usuario_logado_pode_validar = (
        recesso_opcao_escolhida.is_aguardando
        and usuario_logado_is_chefe
        and (recesso_opcao_escolhida.recesso_opcao.is_no_periodo_para_escolhas_de_datas or recesso_opcao_escolhida.pode_validar_apos_prazo)
    )

    usuario_logado_pode_excluir = recesso_opcao_escolhida.pode_excluir(relacionamento)

    usuario_logado_pode_cancelar_validacao = (
        usuario_logado_is_chefe
        and not recesso_opcao_escolhida.is_aguardando
        and (recesso_opcao_escolhida.recesso_opcao.is_no_periodo_para_escolhas_de_datas or recesso_opcao_escolhida.pode_validar_apos_prazo)
    )

    usuario_logado_pode_editar_dias_escolhidos = (
        usuario_logado_is_solicitante
        and recesso_opcao_escolhida.validacao
        in [
            recesso_opcao_escolhida.VALIDACAO_AGUARDANDO,
            recesso_opcao_escolhida.VALIDACAO_AUTORIZADO,
            recesso_opcao_escolhida.VALIDACAO_NAO_AUTORIZADO_REMARCAR,
        ]
        and recesso_opcao_escolhida.recesso_opcao.is_no_periodo_para_escolhas_de_datas
        and not recesso_opcao_escolhida.compensacoes().exists()
    )

    ch_totais = recesso_opcao_escolhida.totais_ch(
        carga_horaria_total=True, carga_horaria_debito_considerado=True, carga_horaria_compensada=True, carga_horaria_pendente=True
    )

    ch_total = ch_totais['total_carga_horaria_total']
    ch_total_is_zero = ch_total == 0
    ch_total = formata_segundos(ch_total, '{h:2d}h ', '{m:2d}min ', '{s:2d}seg ', True)

    ch_debito_considerado = ch_totais['total_carga_horaria_debito_considerado']
    ch_debito_considerado_is_zero = ch_debito_considerado == 0
    ch_debito_considerado = formata_segundos(ch_debito_considerado, '{h:02.0f}h ', '{m:02.0f}min ', '{s:02.0f}seg ', True)

    ch_compensada = ch_totais['total_carga_horaria_compensada']
    ch_compensada_is_zero = ch_compensada == 0
    ch_compensada = formata_segundos(ch_compensada, '{h:02.0f}h ', '{m:02.0f}min ', '{s:02.0f}seg ', True)

    ch_pendente = ch_totais['total_carga_horaria_pendente']
    ch_pendente_is_maior_zero = ch_pendente > 0
    ch_pendente_is_negativa = ch_pendente < 0  # possível problema de duplicidade em informes de compensação
    ch_pendente = formata_segundos(ch_pendente, '{h:02.0f}h ', '{m:02.0f}min ', '{s:02.0f}seg ', True)

    dias_definidos = [dia_definido.data for dia_definido in recesso_opcao_escolhida.recesso_opcao.dias_do_recesso.all()]
    dias_definidos_format = [dia_definido.strftime('%d/%m/%Y') for dia_definido in dias_definidos]
    dias_definidos_format_dmy = [dia_definido.strftime('%d%m%Y') for dia_definido in dias_definidos]
    dias_escolhidos = [dia_escolhido.dia.data for dia_escolhido in recesso_opcao_escolhida.dias_escolhidos.all()]
    dias_escolhidos_format = [dia_escolhido.strftime('%d/%m/%Y') for dia_escolhido in dias_escolhidos]

    periodos_definidos = recesso_opcao_escolhida.recesso_opcao.periodos_do_recesso.all()
    periodos_escolhidos = recesso_opcao_escolhida.periodos_escolhidos.all()

    dias_efetivos_a_compensar = ch_totais['dias_a_compensar']
    dias_efetivos_a_compensar_format = [dia_efetivo.strftime('%d/%m/%Y') for dia_efetivo in dias_efetivos_a_compensar]
    dias_efetivos_a_compensar_format_dmy = [dia_efetivo.strftime('%d%m%Y') for dia_efetivo in dias_efetivos_a_compensar]
    dias_efetivos_a_compensar_situacoes = (
        [
            dia_situacao
            for dia_situacao in list(ch_totais['contexto_compensacao'].dias_debitos.values())
            if dia_situacao.dia in dias_efetivos_a_compensar
        ]
        if ch_totais['contexto_compensacao']
        else []
    )

    meu_acompanhamento_descricao = 'Dados da {} Compensação Específica {}'.format(
        'Minha' if usuario_logado_is_solicitante else '',
        'do Servidor' if not usuario_logado_is_solicitante else '',
    )

    usuario_logado_pode_editar = recesso_opcao_escolhida in RecessoOpcaoEscolhida.pode_editar_opcoes_escolhidas(request.user)[1]

    return locals()


@login_required
@permission_required('ponto.add_recessoopcaoescolhida')
def excluir_recesso_escolhido(request, recesso_opcao_escolhida_id):
    recesso_opcao_escolhida = get_object_or_404(RecessoOpcaoEscolhida, pk=recesso_opcao_escolhida_id)
    #
    usuario_logado = request.user.get_relacionamento()
    pode_excluir = recesso_opcao_escolhida.pode_excluir(usuario_logado)
    #
    if not pode_excluir:
        raise PermissionDenied
    #
    recesso_opcao_escolhida.delete()
    #
    return httprr('/admin/ponto/recessoopcaoescolhida/', 'Informações excluídas com sucesso.')


@rtr()
@login_required
@permission_required('ponto.add_recessoopcaoescolhida')
def editar_dias_de_recesso_escolhidos(request, recesso_opcao_escolhida_id):
    title = 'Editar Dias/Períodos'
    recesso_opcao_escolhida = get_object_or_404(RecessoOpcaoEscolhida, pk=recesso_opcao_escolhida_id)
    try:
        form = get_type_form_dias_ou_periodos_escolhidos(request, recesso_opcao_escolhida.recesso_opcao)(request.POST or None)
        if form.is_valid():
            form.save()
            if RecessoOpcaoEscolhida.objects.filter(id=recesso_opcao_escolhida_id).exists():
                return httprr(f'/ponto/abrir_recesso_escolhido/{recesso_opcao_escolhida_id}/', 'Dias/Períodos salvos com sucesso.')
            return httprr('/admin/ponto/recessoopcaoescolhida/?tab=meus_recessos', 'Dias/Períodos salvos com sucesso.')
    except Exception as erro:
        return httprr(f'/ponto/abrir_recesso_escolhido/{recesso_opcao_escolhida_id}/', str(erro), tag='error')
    return locals()


@rtr()
@permission_required('ponto.add_recessoopcaoescolhida')
def validar_recesso_escolhido(request, recesso_opcao_escolhida_id):
    title = 'Validação do Chefe Imediato'
    recesso_opcao_escolhida = get_object_or_404(RecessoOpcaoEscolhida, pk=recesso_opcao_escolhida_id)

    usuario_logado = request.user.get_relacionamento()
    usuario_logado_is_chefe = recesso_opcao_escolhida.is_chefe(usuario_logado)

    pode_validar = (
        recesso_opcao_escolhida.is_aguardando
        and usuario_logado_is_chefe
        and (recesso_opcao_escolhida.recesso_opcao.is_no_periodo_para_escolhas_de_datas or recesso_opcao_escolhida.pode_validar_apos_prazo)
    )

    if not pode_validar:
        raise PermissionDenied

    form = RecessoOpcaoEscolhidaValidarForm(data=request.POST or None, instance=recesso_opcao_escolhida, request=request)

    if form.is_valid():
        form.save()
        return httprr('..', 'Validação salva com sucesso.')

    return locals()


@rtr()
@permission_required('ponto.add_recessoopcaoescolhida')
def validar_recesso_escolhido_lote(request):
    title = 'Validação em Lote do Chefe Imediato'

    recesso_opcao_escolhida_ids = request.GET.getlist('ids', [])

    recesso_opcoes_escolhidas = [
        get_object_or_404(RecessoOpcaoEscolhida, pk=recesso_opcao_escolhida_id) for recesso_opcao_escolhida_id in recesso_opcao_escolhida_ids
    ]

    usuario_logado = request.user.get_relacionamento()

    for recesso_opcao_escolhida in recesso_opcoes_escolhidas:
        usuario_logado_is_chefe = recesso_opcao_escolhida.is_chefe(usuario_logado)

        pode_validar = (
            recesso_opcao_escolhida.is_aguardando
            and usuario_logado_is_chefe
            and (recesso_opcao_escolhida.recesso_opcao.is_no_periodo_para_escolhas_de_datas or recesso_opcao_escolhida.pode_validar_apos_prazo)
        )

        if not pode_validar:
            raise PermissionDenied

    form = RecessoOpcaoEscolhidaValidarLoteForm(data=request.POST or None, recesso_opcoes_escolhidas=recesso_opcoes_escolhidas, request=request)

    if form.is_valid():
        form.save()
        return httprr('..', 'Validação salva com sucesso.')

    return locals()


@login_required
def cancelar_validacao_recesso_escolhido(request, recesso_opcao_escolhida_id):
    recesso_opcao_escolhida = get_object_or_404(RecessoOpcaoEscolhida, pk=recesso_opcao_escolhida_id)

    usuario_logado = request.user.get_relacionamento()
    usuario_logado_is_chefe = recesso_opcao_escolhida.is_chefe(usuario_logado)
    recesso_opcao_escolhida_estah_validada = not recesso_opcao_escolhida.is_aguardando

    recesso_opcao_estah_aberta_para_escolhas_hoje = recesso_opcao_escolhida.recesso_opcao.is_no_periodo_para_escolhas_de_datas

    pode_cancelar = (
        usuario_logado_is_chefe
        and recesso_opcao_escolhida_estah_validada
        and (recesso_opcao_estah_aberta_para_escolhas_hoje or recesso_opcao_escolhida.pode_validar_apos_prazo)
    )

    if not pode_cancelar:
        raise PermissionDenied

    #
    try:
        recesso_opcao_escolhida.validacao = RecessoOpcaoEscolhida.VALIDACAO_AGUARDANDO
        recesso_opcao_escolhida.motivo_nao_autorizacao = ''
        recesso_opcao_escolhida.save()
        #
        return httprr(f'/ponto/abrir_recesso_escolhido/{recesso_opcao_escolhida.id}/', 'Validação cancelada com sucesso.')
    except Exception:
        pass
    return httprr(f'/ponto/abrir_recesso_escolhido/{recesso_opcao_escolhida.id}/', 'Validação não foi cancelada.', tag='error')


@rtr()
@login_required
@permission_required('ponto.add_horariocompensacao')
def adicionar_compensacao_v2(request):
    title = 'Informar Compensação de Horário'

    hoje = datetime.today().date()
    dia_1_do_mes = date(hoje.year, hoje.month, 1)

    form_initial = {}

    # request.GET com o objetivo de inicializar o form (ainda não submeter)
    get_is_form_initial = request.GET.get('is_form_initial') == '1'

    if not request.GET:
        form_initial = {'data_inicio': dia_1_do_mes, 'data_fim': hoje, 'periodo_objetivo': PeriodoInfo.PERIODO_OBJETIVO_SALDO}

    elif get_is_form_initial:
        # ou período dos saldos
        data_inicio, _ = get_date(request.GET.get('data_inicio'), ['%d%m%Y'])
        data_fim, _ = get_date(request.GET.get('data_fim'), ['%d%m%Y'])
        periodo_objetivo_is_saldo = request.GET.get('periodo_objetivo') == '1'

        form_initial = {
            'data_inicio': data_inicio or dia_1_do_mes,
            'data_fim': data_fim or hoje,
            'periodo_objetivo': PeriodoInfo.PERIODO_OBJETIVO_SALDO if periodo_objetivo_is_saldo else PeriodoInfo.PERIODO_OBJETIVO_DEBITO,
        }

    form = InformarCompensacaoPeriodoForm(None if get_is_form_initial else (request.GET or None), initial=form_initial)

    if form.is_valid():
        form_data_inicio = form.cleaned_data.get('data_inicio')
        form_data_fim = form.cleaned_data.get('data_fim')
        form_periodo_objetivo = form.cleaned_data.get('periodo_objetivo')

        if form_periodo_objetivo == PeriodoInfo.PERIODO_OBJETIVO_SALDO:
            return httprr(
                '/ponto/informar_compensacao_v2/{}/{}/?{}'.format(
                    form_data_inicio.strftime('%d%m%Y'), form_data_fim.strftime('%d%m%Y'), f'periodo_objetivo={PeriodoInfo.PERIODO_OBJETIVO_SALDO}'
                )
            )

        elif form_periodo_objetivo == PeriodoInfo.PERIODO_OBJETIVO_DEBITO:
            return httprr(
                '/ponto/informar_compensacao_v2/{}/{}/?{}'.format(
                    form_data_inicio.strftime('%d%m%Y'), form_data_fim.strftime('%d%m%Y'), f'periodo_objetivo={PeriodoInfo.PERIODO_OBJETIVO_DEBITO}'
                )
            )

    return locals()


@rtr()
@login_required
@permission_required('ponto.add_horariocompensacao')
def informar_compensacao_v2(request, periodo_inicio, periodo_fim):
    periodo_data_inicial = periodo_inicio
    periodo_data_final = periodo_fim

    periodo_objetivo: str = request.GET.get('periodo_objetivo', None)

    if periodo_objetivo is None:
        periodo_objetivo = PeriodoInfo.PERIODO_OBJETIVO_SALDO  # padrão
    elif periodo_objetivo not in [PeriodoInfo.PERIODO_OBJETIVO_SALDO, PeriodoInfo.PERIODO_OBJETIVO_DEBITO]:
        raise PermissionDenied

    # filtros extras para débitos
    omite_debitos_de_compensacoes_especificas: bool = request.GET.get('omite_debitos_de_compensacoes_especificas', None) == '1'
    abrange_apenas_debitos_dessas_compensacoes_especificas_ids: list[int] = []
    try:
        abrange_apenas_debitos_dessas_compensacoes_especificas_ids: list[int] = [
            int(id_str) for id_str in request.GET.get('abrange_apenas_debitos_dessas_compensacoes_especificas_ids', '').split(',')
        ]
    except Exception:
        pass

    apenas_debitos_dessas_compensacoes_especificas = RecessoOpcaoEscolhida.objects.filter(
        id__in=abrange_apenas_debitos_dessas_compensacoes_especificas_ids
    )

    # filtros extras para saldos
    omite_saldos_externos: bool = request.GET.get('omite_saldos_externos', None) == '1'
    abrange_apenas_saldos_externos: bool = request.GET.get('abrange_apenas_saldos_externos', None) == '1'
    abrange_apenas_esses_saldos_externos_ids: list[int] = []
    try:
        abrange_apenas_esses_saldos_externos_ids: list[int] = [
            int(id_str) for id_str in request.GET.get('abrange_apenas_esses_saldos_externos_ids', '').split(',')
        ]
    except Exception:
        pass

    form = get_compensacao_horario_add_form_v2(
        request,
        periodo_data_inicial,
        periodo_data_final,
        periodo_objetivo,
        omite_debitos_de_compensacoes_especificas,
        abrange_apenas_debitos_dessas_compensacoes_especificas_ids,
        omite_saldos_externos,
        abrange_apenas_saldos_externos,
        abrange_apenas_esses_saldos_externos_ids,
    )(request.POST or None)

    if form.is_valid():
        compensacoes = form.save()
        datas_debitos = ','.join({compensacao.data_aplicacao.strftime('%d%m%Y') for compensacao in compensacoes})
        return httprr(
            f'/ponto/ver_frequencia/{request.user.get_relacionamento().matricula}/?datas={datas_debitos}',
            'Informes de Compensação de Horário salvos com sucesso.',
        )

    title = f'Informar Compensação de Horário - {form.periodo_objetivo_display}'

    base_url = (
        f'/ponto/informar_compensacao_v2/{periodo_inicio.strftime("%d%m%Y")}/{periodo_fim.strftime("%d%m%Y")}/?periodo_objetivo={periodo_objetivo}'
    )

    base_url_extra_params_debitos = [
        f'&{param}={value}'
        for param, value in {
            'omite_debitos_de_compensacoes_especificas': '1' if omite_debitos_de_compensacoes_especificas else None,
            'abrange_apenas_debitos_dessas_compensacoes_especificas_ids': ','.join(
                [f'{id}' for id in abrange_apenas_debitos_dessas_compensacoes_especificas_ids]
            ),
        }.items()
        if value
    ]

    base_url_extra_params_saldos = [
        f'&{param}={value}'
        for param, value in {
            'omite_saldos_externos': '1' if omite_saldos_externos else None,
            'abrange_apenas_saldos_externos': '1' if abrange_apenas_saldos_externos else None,
            'abrange_apenas_esses_saldos_externos_ids': ','.join([f'{id}' for id in abrange_apenas_esses_saldos_externos_ids]),
        }.items()
        if value
    ]

    base_url_debitos = base_url + ''.join(base_url_extra_params_debitos)
    base_url_saldos = base_url + ''.join(base_url_extra_params_saldos)
    full_url = request.get_full_path()
    outro_periodo_url = f'/ponto/adicionar_compensacao_v2/?is_form_initial=1&data_inicio={periodo_inicio.strftime("%d%m%Y")}&data_fim={periodo_fim.strftime("%d%m%Y")}&periodo_objetivo={"1" if form.periodo_envolvido_eh_dos_debitos else "2"}'

    return locals()


@rtr('informar_compensacao_v2.html')
@login_required
@permission_required('ponto.add_horariocompensacao')
def informar_compensacao_v2_recesso(request, periodo_inicio, periodo_fim):
    recesso_escolhido_id = request.GET.get('recesso_escolhido', 0)

    to_path = f'/ponto/informar_compensacao_v2/{periodo_inicio.strftime("%d%m%Y")}/{periodo_fim.strftime("%d%m%Y")}/'
    to_path += f'?periodo_objetivo={PeriodoInfo.PERIODO_OBJETIVO_SALDO}'
    to_path += f'&abrange_apenas_debitos_dessas_compensacoes_especificas_ids={recesso_escolhido_id}'

    return httprr(to_path)


@rtr()
@login_required
# @permission_required('ponto.add_horariocompensacao')
def detalhar_compensacao(request, matricula, data):
    servidor = get_object_or_404(Servidor, matricula=matricula)

    permissao = HorarioCompensacao.pode_visualizar_detalhamento_compensacao(
        user=request.user, servidor=servidor, data_inicio=data, data_fim=data
    ).get(data)

    if not permissao:
        raise PermissionDenied

    title = 'Detalhes da Compensação de Horário do Dia'

    contexto_compensacao = Contexto(servidor, data, data)

    debitos = contexto_compensacao.dias_debitos
    is_debito = data in debitos
    if is_debito:
        debito = timedelta(seconds=debitos[data].debito_qtd_considerado)
        debito_ponto = timedelta(seconds=debitos[data].debito_via_frequencias_qtd_considerado)
        debito_acompanhamentos_especificos = debitos[data].acompanhamentos_envolvidos_contendo_o_dia_como_debito
        debitos_externos = debitos[data].debitos_externos_do_dia
        debito_display = formata_timedelta(debito, 'h', '', '{h}h', '{m:02}min', '{s:02}seg')
        debito_ponto_display = formata_timedelta(debito_ponto, 'h', '', '{h}h', '{m:02}min', '{s:02}seg')
        abonos_parciais = [abono_parcial for abono_parcial in debitos[data].abonos_do_dia if abono_parcial.eh_abono_parcial]
        debito_inicial = timedelta(seconds=debitos[data].debito_qtd_inicial)
        debito_inicial_display = formata_timedelta(debito_inicial, 'h', '', '{h}h', '{m:02}min', '{s:02}seg')
        debito_desconsiderado = timedelta(seconds=debitos[data].debito_qtd_desconsiderado)
        debito_desconsiderado_display = formata_timedelta(debito_desconsiderado, 'h', '', '{h}h', '{m:02}min', '{s:02}seg')
    else:
        debito = timedelta(seconds=0)

    saldos = contexto_compensacao.dias_saldos
    is_saldo = data in saldos
    if is_saldo:
        saldo = timedelta(seconds=saldos[data].saldo_qtd_considerado)
        saldo_display = formata_timedelta(saldo, 'h', '', '{h}h', '{m:02}min', '{s:02}seg')
    else:
        saldo = timedelta(seconds=0)

    compensacoes = contexto_compensacao.get_compensacoes_informadas
    compensacoes_paga = []
    compensacoes_utilizada = []
    # total_paga = timedelta(seconds=0)
    total_paga = timedelta(seconds=contexto_compensacao.total_debito_qtd_reposto)
    # total_utilizada = timedelta(seconds=0)
    total_utilizada = timedelta(seconds=contexto_compensacao.total_saldo_qtd_utilizado)

    for compensacao in compensacoes:
        if data == compensacao.data_compensacao:
            compensacoes_utilizada.append(compensacao)
            # total_utilizada += timedelta(seconds=Frequencia.time_para_segundos(compensacao.ch_compensada))
        if data == compensacao.data_aplicacao:
            compensacoes_paga.append(compensacao)
            # total_paga += timedelta(seconds=Frequencia.time_para_segundos(compensacao.ch_compensada))

    total_paga_display = formata_timedelta(total_paga, 'h', '', '{h}h', '{m:02}min', '{s:02}seg')
    total_utilizada_display = formata_timedelta(total_utilizada, 'h', '', '{h}h', '{m:02}min', '{s:02}seg')

    # debito_restante = debito - total_paga if total_paga <= debito else timedelta(seconds=0)
    debito_restante = timedelta(seconds=contexto_compensacao.total_debito_qtd_restante)
    debito_restante_display = formata_timedelta(debito_restante, 'h', '', '{h}h', '{m:02}min', '{s:02}seg')

    # saldo_restante = saldo - total_utilizada if total_utilizada <= saldo else timedelta(seconds=0)
    saldo_restante = timedelta(seconds=contexto_compensacao.total_saldo_qtd_restante)
    saldo_restante_display = formata_timedelta(saldo_restante, 'h', '', '{h}h', '{m:02}min', '{s:02}seg')

    dia_anterior = data - timedelta(days=1)
    dia_seguinte = data + timedelta(days=1)

    is_popup = '_popup' in request.GET

    return locals()


@rtr()
@login_required
@permission_required('ponto.add_horariocompensacao')
def ver_frequencia(request, matricula):
    """
    suporte para múltiplas datas ou um único período

    mostra apenas as frequências

    /ver_frequencia/matricula/?datas=X,X,X,X
    /ver_frequencia/matricula/?periodo_data_inicio=X&periodo_data_fim=X

    formatos de X:
        ddmmyyyy
        yyyy-mm-dd
        dd/mm/yyyy

    TODO: No caso do parâmetro "datas", o ideal é que venha no request.POST para evitar
    TODO: requisições GET muito longas
    """

    title = 'Consulta Simples de Frequências'

    servidor = get_object_or_404(Servidor, matricula=matricula)

    datas: list[date] = []

    date_formats = ['%d%m%Y', '%Y-%m-%d', '%d/%m/%Y']

    datas_str = request.GET and request.GET.get('datas', '').split(',')
    for data_str in datas_str:
        if data_str:
            data, _ = get_date(data_str, date_formats)
            if data:
                datas.append(data)
            else:
                return httprr('..', 'Uma ou mais datas inválidas foram informadas.', 'error')

    periodo_data_inicio_str = request.GET and request.GET.get('periodo_data_inicio', '')
    periodo_data_fim_str = request.GET and request.GET.get('periodo_data_fim', '')
    if periodo_data_inicio_str and periodo_data_fim_str:
        data_inicio, _ = get_date(periodo_data_inicio_str, date_formats)
        if not data_inicio:
            return httprr('..', 'Uma ou mais datas inválidas foram informadas.', 'error')

        data_fim, _ = get_date(periodo_data_fim_str, date_formats)
        if not data_fim:
            return httprr('..', 'Uma ou mais datas inválidas foram informadas.', 'error')

        datas += datas_entre(data_inicio, data_fim)

    try:
        relatorio = Frequencia.relatorio_ponto_pessoa(
            vinculo=servidor.get_vinculo(), data_ini=min(datas), data_fim=max(datas), show_grafico=False, trata_compensacoes=True
        )
        Frequencia.relatorio_ponto_pessoa_update(relatorio)

        frequencias_dias = []
        for frequencia_dia in relatorio['dias']:
            if frequencia_dia['dia'] in datas:
                frequencias_dias.append(frequencia_dia)
        relatorio['dias'] = frequencias_dias

        if is_request_xls(request):
            try:
                xls = get_response_xls_registros_frequencias([relatorio], filename=title)

                if xls:
                    return xls
            except Exception:
                pass

    except Exception:
        relatorio = []

    return locals()


@rtr()
@login_required
@permission_required('ponto.add_horariocompensacao')
def remover_compensacoes(request, matricula):
    """
    suporta remoção de múltiplos informes de compensação
    """

    servidor = get_object_or_404(Servidor, matricula=matricula)

    if not request.user.get_relacionamento().matricula == matricula:
        raise PermissionDenied

    compensacoes_por_data_debito = request.GET.get('localizar_opcao') == '1'
    compensacoes_por_data_saldo = request.GET.get('localizar_opcao') == '2'
    compensacoes_em_duplicidade = request.GET.get('localizar_opcao') == '3'
    compensacoes_por_saldo_externo = request.GET.get('localizar_opcao') == '4'

    confirmando_remocao = request.POST.get('remover') == 'sim'
    senha_remocao_confere = False

    data_inicio = None
    data_fim = None
    saldos_externos_ids = None

    compensacoes = HorarioCompensacao.objects.none()

    if compensacoes_por_data_debito or compensacoes_por_data_saldo:
        title = 'Remover Compensações - Localizar por Data'

        if compensacoes_por_data_debito:
            title = f'{title} do Débito'
        else:
            title = f'{title} do Saldo'

        if confirmando_remocao:
            data_inicio = datetime.strptime(request.POST.get('data_inicio'), '%d%m%Y')
            data_fim = datetime.strptime(request.POST.get('data_fim'), '%d%m%Y')

            form = HorarioCompensacaoPeriodoForm({'data_inicio': data_inicio, 'data_fim': data_fim})
        else:
            form = HorarioCompensacaoPeriodoForm(request.POST or None)

            if form.is_valid():
                data_inicio = form.cleaned_data['data_inicio']
                data_fim = form.cleaned_data['data_fim']

        if data_inicio and data_fim:
            compensacoes = HorarioCompensacao.objects.filter(funcionario=servidor)

            if compensacoes_por_data_debito:
                compensacoes = compensacoes.filter(data_aplicacao__gte=data_inicio, data_aplicacao__lte=data_fim)
            else:
                compensacoes = compensacoes.filter(data_compensacao__gte=data_inicio, data_compensacao__lte=data_fim)

    elif compensacoes_em_duplicidade:
        title = 'Remover Compensações em Duplicidade'

        # compensações em duplicidade:
        # mesma data do débito
        # mesma data da compensação
        # mesma carga horária compensada

        compensacoes_ids = []

        compensacoes_todas = []
        for compensacao in HorarioCompensacao.objects.filter(funcionario=servidor, data_compensacao__isnull=False):
            compensacoes_todas.append(
                '{},{}{}{}'.format(
                    compensacao.id,
                    compensacao.data_aplicacao.strftime('%d/%m/%Y'),
                    compensacao.data_compensacao.strftime('%d/%m/%Y'),
                    compensacao.ch_compensada.strftime('%H:%M:%S'),
                )
            )

        while compensacoes_todas:
            compensacao_teste = compensacoes_todas[0]

            compensacoes_duplicadas_ids = []
            for compensacao in compensacoes_todas[1:]:
                if compensacao.split(',')[1] == compensacao_teste.split(',')[1]:  # compara os ids das compensações
                    compensacoes_duplicadas_ids.append(compensacao.split(',')[0])

            compensacoes_processadas_ids = [compensacao_teste.split(',')[0], *compensacoes_duplicadas_ids]

            compensacoes_todas_tmp = []
            for compensacao in compensacoes_todas:
                if compensacao.split(',')[0] not in compensacoes_processadas_ids:
                    compensacoes_todas_tmp.append(compensacao)
            compensacoes_todas = compensacoes_todas_tmp

            compensacoes_ids += compensacoes_duplicadas_ids

        compensacoes = compensacoes | HorarioCompensacao.objects.filter(id__in=compensacoes_ids)

    elif compensacoes_por_saldo_externo:
        title = 'Remover Compensações - Localizar por Saldo Externo Utilizado'

        if confirmando_remocao:
            saldos_externos_ids = request.POST.getlist('saldos_externos_ids', [])
            form = SelecionarSaldosExternosForm({'saldos_externos': saldos_externos_ids}, escopo_user_como_destinatario=True, request=request)
        else:
            form = SelecionarSaldosExternosForm(request.POST or None, escopo_user_como_destinatario=True, request=request)

            if form.is_valid():
                saldos_externos_ids = [saldo_externo.id for saldo_externo in form.cleaned_data['saldos_externos']]

        if saldos_externos_ids:
            compensacoes = HorarioCompensacao.objects.filter(funcionario=servidor, saldo_externo_compensacao__id__in=saldos_externos_ids)

    else:
        return httprr('/admin/ponto/horariocompensacao/', tag='error', message='Remover Compensações: Opção Inválida.')

    compensacoes_selecionadas_ids = []

    if confirmando_remocao:
        senha = request.POST.get('password')
        senha_remocao_confere = authenticate(request, username=servidor.matricula, password=senha) is not None

        for field in request.POST:
            try:
                selecao = field.split('selecao_')[1]  # selecao_?
                if selecao:
                    compensacoes_selecionadas_ids.append(selecao)
            except Exception:
                pass

        if senha_remocao_confere and compensacoes_selecionadas_ids:
            compensacoes.filter(id__in=compensacoes_selecionadas_ids).delete()

            return httprr('/admin/ponto/horariocompensacao/?tab=meus_informes', 'Informes de Compensação removidos com sucesso.')

    if compensacoes:
        if compensacoes_por_data_saldo:
            compensacoes = compensacoes.order_by('data_compensacao')
        else:
            compensacoes = compensacoes.order_by('data_aplicacao')

    return locals()


@rtr()
@login_required
@permission_required('ponto.add_recessoopcaoescolhida')
def editar_chefe_recesso_escolhido(request, recesso_opcao_escolhida_id):
    recesso_opcao_escolhida = get_object_or_404(RecessoOpcaoEscolhida, pk=recesso_opcao_escolhida_id)

    title = f'Editar o Chefe Imediato/Validador de {recesso_opcao_escolhida}'

    usuario_logado = request.user.get_relacionamento()
    usuario_logado_is_solicitante = usuario_logado == recesso_opcao_escolhida.funcionario
    usuario_logado_is_chefe, chefes = recesso_opcao_escolhida.is_chefe(usuario_logado, retornar_chefes=True)

    eh_possivel_editar_o_chefe = (
        (usuario_logado_is_solicitante or usuario_logado_is_chefe) and recesso_opcao_escolhida.is_aguardando and len(chefes) >= 1
    )

    if not eh_possivel_editar_o_chefe:
        return httprr(f'/ponto/abrir_recesso_escolhido/{recesso_opcao_escolhida_id}/', 'Não é possível modificar o Chefe Imediato.', 'error')

    form = RecessoOpcaoEscolhidaEditarChefeForm(request.POST or None, instance=recesso_opcao_escolhida)

    if form.is_valid():
        form.save()
        return httprr(f'/ponto/abrir_recesso_escolhido/{recesso_opcao_escolhida_id}/', 'Chefe Imediato modificado com sucesso.')

    return locals()


@rtr()
@login_required
def localizar_acompanhamentos(request):
    pode_editar, escopo = RecessoOpcaoEscolhida.pode_editar_opcoes_escolhidas(request.user)
    if not pode_editar:
        raise PermissionDenied

    title = 'Localizar Compensações Específicas'

    form = LocalizarServidorForm(request.GET or None, escopo_opcoes_escolhidas=escopo)

    acompanhamentos = escopo.none()

    if form.is_valid():
        acompanhamentos = escopo.filter(funcionario__id=form.cleaned_data['servidor'].id).order_by('-data_escolha')

    return locals()


@rtr()
@login_required
def editar_acompanhamento(request, recesso_opcao_escolhida_id):
    pode_editar, escopo = RecessoOpcaoEscolhida.pode_editar_opcoes_escolhidas(request.user)
    if not pode_editar:
        raise PermissionDenied

    acompanhamento = get_object_or_404(RecessoOpcaoEscolhida, pk=recesso_opcao_escolhida_id)

    if acompanhamento not in escopo:
        raise PermissionDenied

    dias_efetivos_a_compensar = acompanhamento.dias_efetivos_a_compensar()
    dias_efetivos_a_compensar_format = [dia_efetivo.strftime('%d/%m/%Y') for dia_efetivo in dias_efetivos_a_compensar]

    title = 'Editar Compensação Específica'

    form = RecessoOpcaoEscolhidaEditarForm(request.POST or None, instance=acompanhamento, request=request)

    if form.is_valid():
        form.save()
        return httprr(
            request.GET.get('next_url') or '/ponto/localizar_acompanhamentos/',
            f"{acompanhamento.funcionario}: Compensação Específica '{acompanhamento.recesso_opcao}' salva com sucesso.",
        )

    servidor_logado = request.user.get_relacionamento()

    return locals()


@rtr()
@login_required
@permission_required('ponto.add_horariocompensacao')
def ver_compensacao_detalhada(request):
    title = 'Relatório Detalhado da Compensação de Horários'

    servidor = request.user.get_relacionamento()

    form = HorarioCompensacaoPeriodoForm(request.GET or None)

    if form.is_valid():
        contexto = Contexto(
            servidor=servidor, periodo_data_inicial=form.cleaned_data.get('data_inicio'), periodo_data_final=form.cleaned_data.get('data_fim')
        )
        totais = contexto.get_totais()

        ha_saldos_externos_com_inconsistencias = True in [
            saldo_externo.periodo_utilizacao_is_fim_de_semana for saldo_externo in totais.saldos_externos_envolvidos
        ]

        ctx = locals()
        ctx.update(totais.as_dict())

        return render('ponto/templates/ver_compensacao_detalhada.html', ctx)

    return locals()


@rtr()
@login_required
@permission_required('ponto.add_recessoopcaoescolhida')
def atualizar_lista_dias_efetivos_a_compensar(request, recesso_opcao_escolhida_id):
    recesso_opcao_escolhida = get_object_or_404(RecessoOpcaoEscolhida, pk=recesso_opcao_escolhida_id)
    recesso_opcao_escolhida.dias_efetivos_a_compensar(force_update=True)
    return httprr(f'/ponto/abrir_recesso_escolhido/{recesso_opcao_escolhida_id}/', 'Ação executada.')


@rtr()
@login_required
def adicionar_saldo_externo_ch(request):
    if not SaldoExterno.pode_adicionar(request.user):
        raise PermissionDenied

    form = SaldoExternoDestinatarioAdd(request.POST or None, request=request)

    if form.is_valid():
        saldo_externo = form.save()
        return httprr(f'{saldo_externo.get_absolute_url()}')

    title = 'Adicionar Saldo Externo (Como Destinatário do Saldo)'

    return locals()


@rtr()
@login_required
def adicionar_saldo_externo_ch_como_chefe(request):
    if not SaldoExterno.pode_adicionar_como_chefe(request.user):
        raise PermissionDenied

    form = SaldoExternoValidadorAdd(request.POST or None, request=request, initial={'validador': request.user.get_relacionamento()})

    if form.is_valid():
        saldo_externo = form.save()
        return httprr(f'{saldo_externo.get_absolute_url()}')

    title = 'Adicionar Saldo Externo (Como Validador do Saldo)'

    return locals()


@rtr()
@login_required
def editar_saldo_externo_ch(request, saldo_externo_id):
    saldo_externo = get_object_or_404(SaldoExterno, pk=saldo_externo_id)

    FormClass = None

    if saldo_externo.pode_editar(request.user):
        if saldo_externo.eh_minha_validacao(request.user):
            FormClass = SaldoExternoValidadorChange
        elif saldo_externo.eh_meu(request.user):
            FormClass = SaldoExternoDestinatarioChange

    if not FormClass:
        raise PermissionDenied

    validador_old = saldo_externo.validador

    form = FormClass(request.POST or None, request=request, instance=saldo_externo)

    if form.is_valid():
        form.save()
        message = ['Salvo com sucesso.']
        if form.instance.validador != validador_old:
            message.append('Att: O validador foi alterado.')
        return httprr(f'{saldo_externo.get_absolute_url()}', ' '.join(message))

    title = f'Editar {saldo_externo}'

    return locals()


@rtr()
@login_required
def visualizar_saldo_externo_ch(request, saldo_externo_id):
    saldo_externo = get_object_or_404(SaldoExterno, pk=saldo_externo_id)

    if not saldo_externo.pode_visualizar(request.user):
        raise PermissionDenied

    title = 'Visualizar Saldo Externo de Carga Horária'

    pode_editar = saldo_externo.pode_editar(request.user)
    pode_encaminhar_para_validacao = saldo_externo.pode_encaminhar_para_validacao(request.user)
    pode_validar = saldo_externo.pode_validar(request.user)
    pode_cancelar_validacao = saldo_externo.pode_cancelar_validacao(request.user)
    pode_excluir = saldo_externo.pode_excluir(request.user)
    tem_compensacoes_informadas = saldo_externo.compensacoes_informadas.exists()
    pode_visualizar_utilizacao_saldo = saldo_externo.eh_meu(request.user)
    validador_eh_reitor_hoje = saldo_externo.validador.eh_reitor(date.today()) if saldo_externo.validador else False
    pode_tentar_compensar = saldo_externo.is_validado and pode_visualizar_utilizacao_saldo and saldo_externo.valor_saldo_restante > 0

    return locals()


@rtr()
@login_required
def encaminhar_validacao_saldo_externo_ch(request, saldo_externo_id):
    saldo_externo = get_object_or_404(SaldoExterno, pk=saldo_externo_id)

    if not saldo_externo.pode_encaminhar_para_validacao(request.user):
        raise PermissionDenied

    saldo_externo.situacao = SaldoExterno.SITUACAO_AGUARDANDO_VALIDACAO
    saldo_externo.save()

    return httprr(f'{saldo_externo.get_absolute_url()}')


@rtr()
@login_required
def validar_saldo_externo_ch(request, saldo_externo_id):
    saldo_externo = get_object_or_404(SaldoExterno, pk=saldo_externo_id)

    if not saldo_externo.pode_validar(request.user):
        raise PermissionDenied

    form = SaldoExternoValidar(request.POST or None, request=request, instance=saldo_externo)

    if form.is_valid():
        form.save()
        return httprr('..')

    title = f'Validar {saldo_externo}'

    return locals()


@rtr()
@login_required
def cancelar_validacao_saldo_externo_ch(request, saldo_externo_id):
    saldo_externo = get_object_or_404(SaldoExterno, pk=saldo_externo_id)

    if not saldo_externo.pode_cancelar_validacao(request.user):
        raise PermissionDenied

    saldo_externo.situacao = SaldoExterno.SITUACAO_EM_FASE_DEFINICAO
    saldo_externo.save()

    return httprr(f'{saldo_externo.get_absolute_url()}')


@rtr()
@login_required
def adicionar_debito_externo_ch_cadastro(request):
    if not DebitoExternoCadastro.pode_adicionar(request.user):
        raise PermissionDenied

    form = DebitoExternoCadastroDestinatarioAdd(request.POST or None, request=request)

    if form.is_valid():
        debito_externo_cadastro = form.save()
        return httprr(f'{debito_externo_cadastro.get_absolute_url()}')

    title = 'Adicionar Débito Externo (Como Destinatário do Débito)'

    return locals()


@rtr()
@login_required
def adicionar_debito_externo_ch_cadastro_como_chefe(request):
    if not DebitoExternoCadastro.pode_adicionar_como_chefe(request.user):
        raise PermissionDenied

    form = DebitoExternoCadastroValidadorAdd(request.POST or None, request=request, initial={'validador': request.user.get_relacionamento()})

    if form.is_valid():
        debito_externo_cadastro = form.save()
        return httprr(f'{debito_externo_cadastro.get_absolute_url()}')

    title = 'Adicionar Débito Externo (Como Validador do Débito)'

    return locals()


@rtr()
@login_required
def editar_debito_externo_ch_cadastro(request, debito_externo_cadastro_id):
    debito_externo_cadastro = get_object_or_404(DebitoExternoCadastro, pk=debito_externo_cadastro_id)

    FormClass = None

    if debito_externo_cadastro.pode_editar(request.user):
        if debito_externo_cadastro.eh_minha_validacao(request.user):
            FormClass = DebitoExternoCadastroValidadorChange
        elif debito_externo_cadastro.eh_meu(request.user):
            FormClass = DebitoExternoCadastroDestinatarioChange

    if not FormClass:
        raise PermissionDenied

    validador_old = debito_externo_cadastro.validador

    form = FormClass(request.POST or None, request=request, instance=debito_externo_cadastro)

    if form.is_valid():
        form.save()
        message = ['Salvo com sucesso.']
        if form.instance.validador != validador_old:
            message.append('Att: O validador foi alterado.')
        return httprr(f'{debito_externo_cadastro.get_absolute_url()}', ' '.join(message))

    title = f'Editar {debito_externo_cadastro}'

    return locals()


@rtr()
@login_required
def adicionar_debito_externo_ch(request, debito_externo_cadastro_id):
    debito_externo_cadastro = get_object_or_404(DebitoExternoCadastro, pk=debito_externo_cadastro_id)

    if not debito_externo_cadastro.pode_editar(request.user):
        raise PermissionDenied

    form = DebitoExternoAdd(request.POST or None, request=request, debito_externo_cadastro=debito_externo_cadastro)

    if form.is_valid():
        form.save()
        return httprr('..')

    title = 'Adicionar Dia do Débito'

    return locals()


@rtr()
@login_required
def editar_debito_externo_ch(request, debito_externo_id):
    debito_externo = get_object_or_404(DebitoExterno, pk=debito_externo_id)

    if not debito_externo.pode_editar(request.user):
        raise PermissionDenied

    form = DebitoExternoChange(request.POST or None, request=request, instance=debito_externo)

    if form.is_valid():
        form.save()
        return httprr('..')

    title = 'Editar Dia do Débito'

    return locals()


@rtr()
@login_required
def excluir_debito_externo_ch(request, debito_externo_id):
    debito_externo = get_object_or_404(DebitoExterno, pk=debito_externo_id)

    if not debito_externo.pode_excluir(request.user):
        raise PermissionDenied

    debito_externo_cadastro = debito_externo.cadastro

    debito_externo.delete()

    return httprr(f'{debito_externo_cadastro.get_absolute_url()}')


@rtr()
@login_required
def visualizar_debito_externo_ch_cadastro(request, debito_externo_cadastro_id):
    debito_externo_cadastro = get_object_or_404(DebitoExternoCadastro, pk=debito_externo_cadastro_id)

    if not debito_externo_cadastro.pode_visualizar(request.user):
        raise PermissionDenied

    title = 'Visualizar Débito Externo de Carga Horária'

    pode_editar = debito_externo_cadastro.pode_editar(request.user)
    pode_encaminhar_para_validacao = debito_externo_cadastro.pode_encaminhar_para_validacao(request.user)
    pode_validar = debito_externo_cadastro.pode_validar(request.user)
    pode_cancelar_validacao = debito_externo_cadastro.pode_cancelar_validacao(request.user)
    pode_excluir = debito_externo_cadastro.pode_excluir(request.user)
    tem_compensacoes_informadas = debito_externo_cadastro.compensacoes_informadas.exists()
    pode_visualizar_compensacao_debito = debito_externo_cadastro.eh_meu(request.user)
    validador_eh_reitor_hoje = debito_externo_cadastro.validador.eh_reitor(date.today()) if debito_externo_cadastro.validador else False
    pode_tentar_compensar = (
        debito_externo_cadastro.is_validado and pode_visualizar_compensacao_debito and debito_externo_cadastro.total_debito_restante > 0
    )
    dias_dos_debitos = debito_externo_cadastro.get_dias_dos_debitos()
    dias_dos_debitos_count = dias_dos_debitos.count()
    dias_dos_debitos_exists = dias_dos_debitos_count > 0
    dias_dos_debitos_first = dias_dos_debitos.first()
    dias_dos_debitos_last = dias_dos_debitos.last()

    return locals()


@rtr()
@login_required
def encaminhar_validacao_debito_externo_ch_cadastro(request, debito_externo_cadastro_id):
    debito_externo_cadastro = get_object_or_404(DebitoExternoCadastro, pk=debito_externo_cadastro_id)

    if not debito_externo_cadastro.pode_encaminhar_para_validacao(request.user):
        raise PermissionDenied

    debito_externo_cadastro_erros = debito_externo_cadastro.get_erros()
    if debito_externo_cadastro_erros:
        return httprr(f'{debito_externo_cadastro.get_absolute_url()}', ' '.join(debito_externo_cadastro_erros), tag='error')

    debito_externo_cadastro.situacao = DebitoExternoCadastro.SITUACAO_AGUARDANDO_VALIDACAO
    debito_externo_cadastro.save()

    return httprr(f'{debito_externo_cadastro.get_absolute_url()}')


@rtr()
@login_required
def validar_debito_externo_ch_cadastro(request, debito_externo_cadastro_id):
    debito_externo_cadastro = get_object_or_404(DebitoExternoCadastro, pk=debito_externo_cadastro_id)

    if not debito_externo_cadastro.pode_validar(request.user):
        raise PermissionDenied

    form = DebitoExternoCadastroValidar(request.POST or None, request=request, instance=debito_externo_cadastro)

    if form.is_valid():
        form.save()
        return httprr('..')

    title = f'Validar {debito_externo_cadastro}'

    return locals()


@rtr()
@login_required
def cancelar_validacao_debito_externo_ch_cadastro(request, debito_externo_cadastro_id):
    debito_externo_cadastro = get_object_or_404(DebitoExternoCadastro, pk=debito_externo_cadastro_id)

    if not debito_externo_cadastro.pode_cancelar_validacao(request.user):
        raise PermissionDenied

    debito_externo_cadastro.situacao = DebitoExternoCadastro.SITUACAO_EM_FASE_DEFINICAO
    debito_externo_cadastro.save()

    return httprr(f'{debito_externo_cadastro.get_absolute_url()}')


##########################################################################################
##########################################################################################


@rtr()
@login_required
@transaction.atomic
def documento_anexar_add(request, dia_ponto):
    title = 'Anexar Documento'

    dia_data = dia_ponto
    hoje = datetime.date(datetime.today())

    if dia_data > hoje:
        return HttpResponseForbidden('Não é possível anexar documentos em datas futuras.')

    tem_abonos_no_dia = AbonoChefia.get_abonos_chefia(request.user.get_vinculo(), dia_data, dia_data).get(dia_data, [])
    if tem_abonos_no_dia:
        return httprr(
            '..',
            'Não é possível anexar documento. Existe uma ação da chefia imediata no dia em questão.',
            tag='failure',
        )

    pessoa = request.user.get_profile()

    try:
        rel_ponto = Frequencia.relatorio_ponto_pessoa(vinculo=request.user.get_vinculo(), data_ini=dia_data, data_fim=dia_data)
    except Exception as e:
        return httprr('..', e.message, 'error')

    freq = rel_ponto['dias'][0]
    freq_keys = list(freq.keys())

    form = DocumentoAnexoForm(request.POST or None, request.FILES or None, vinculo=request.user.get_vinculo(), data=dia_data)

    if form.is_valid():
        form.save()
        return httprr('..', 'Documento anexado.')

    return locals()


@rtr()
@login_required
@transaction.atomic
def documento_anexar_change(request, pk):
    title = 'Anexar Documento'

    documento_anexo = get_object_or_404(DocumentoAnexo, pk=pk)
    pessoa = request.user.get_profile()

    if documento_anexo.vinculo != request.user.get_vinculo():
        return HttpResponseForbidden()

    tem_abonos_no_dia = AbonoChefia.get_abonos_chefia(request.user.get_vinculo(), documento_anexo.data, documento_anexo.data).get(
        documento_anexo.data, []
    )
    if tem_abonos_no_dia:
        return httprr(
            '..',
            'Não é possível editar o documento. Existe uma ação da chefia imediata no dia em questão.',
            tag='failure',
        )

    form = DocumentoAnexoChangeForm(request.POST or None, instance=documento_anexo)

    if form.is_valid():
        form.save()
        return httprr('..', 'Operação realizada.')

    return locals()


@login_required
@transaction.atomic
def documento_anexar_delete(request, pk):
    documento_anexo = get_object_or_404(DocumentoAnexo, pk=pk)

    if documento_anexo.vinculo != request.user.get_vinculo():
        return HttpResponseForbidden()

    tem_abonos_no_dia = AbonoChefia.get_abonos_chefia(request.user.get_vinculo(), documento_anexo.data, documento_anexo.data).get(
        documento_anexo.data, []
    )
    if tem_abonos_no_dia:
        return httprr(
            '..',
            'Não é possível excluir o documento. Existe uma ação da chefia imediata no dia em questão.',
            tag='failure',
        )

    documento_anexo.delete()

    return httprr(request.META.get('HTTP_REFERER', '..'), 'Observação excluída com sucesso.')


@rtr()
@login_required
@permission_required('ponto.add_horariocompensacao')
def compensacao_horario_corrigir_debitos(request):
    servidor = request.user.get_relacionamento()

    # atualiza os dias efetivos a compensar de todas as compensações específicas do servidor
    for compensacao_especifica in RecessoOpcaoEscolhida.objects.filter(funcionario=servidor):
        compensacao_especifica.dias_efetivos_a_compensar_cache = ''
        compensacao_especifica.dias_efetivos_a_compensar()

    next_url = request.GET.get('next_url') or '..'

    return httprr(next_url, 'Inconsistências corrigidas.')


@rtr('solicitar_abono_parcial.html')
@login_required
@permission_required('ponto.add_solicitacaoabonoparcial')
def solicitar_abono_parcial_etapa_1(request):
    if not SolicitacaoAbonoParcial.solicitacao_abono_parcial_ativada():
        raise PermissionDenied

    next_url = request.GET.get('next_url', None) if request.GET else None

    data_aplicacao = date.today()
    try:
        data_aplicacao_param = request.GET.get('data_aplicacao', None) if request.GET else None
        if data_aplicacao_param:
            data_aplicacao = datetime.strptime(data_aplicacao_param, '%Y-%m-%d').date()
    except Exception:
        pass

    motivo_solicitacao = None
    try:
        motivo_solicitacao_param = request.GET.get('motivo_solicitacao', None) if request.GET else None
        if motivo_solicitacao_param:
            motivo_solicitacao = int(motivo_solicitacao_param)
    except Exception:
        pass

    form = SolicitacaoAbonoParcialEtapa1Form(
        request.POST or None,
        initial={'data_aplicacao': data_aplicacao.strftime('%Y-%m-%d'), 'motivo_solicitacao': motivo_solicitacao},
        request=request,
    )

    if form.is_valid():
        data_aplicacao = form.cleaned_data.get('data_aplicacao')
        motivo_solicitacao = form.cleaned_data.get('motivo_solicitacao')
        etapa_2_url = (
            f'/ponto/solicitar_abono_parcial_etapa_2/?data_aplicacao={data_aplicacao.strftime("%Y-%m-%d")}&motivo_solicitacao={motivo_solicitacao}'
        )
        if next_url:
            etapa_2_url = f'{etapa_2_url}&next_url={next_url}'
        return httprr(etapa_2_url)

    title = 'Nova Solicitação de Abono Parcial'

    return locals()


@rtr('solicitar_abono_parcial.html')
@login_required
@permission_required('ponto.add_solicitacaoabonoparcial')
def solicitar_abono_parcial_etapa_2(request):
    if not SolicitacaoAbonoParcial.solicitacao_abono_parcial_ativada():
        raise PermissionDenied

    next_url = request.GET.get('next_url', None) if request.GET else None

    data_aplicacao = date.today()
    try:
        data_aplicacao_param = request.GET.get('data_aplicacao', None) if request.GET else None
        if data_aplicacao_param:
            data_aplicacao = datetime.strptime(data_aplicacao_param, '%Y-%m-%d').date()
    except Exception:
        pass

    motivo_solicitacao = None
    try:
        motivo_solicitacao_param = request.GET.get('motivo_solicitacao', None) if request.GET else None
        if motivo_solicitacao_param:
            motivo_solicitacao = int(motivo_solicitacao_param)
    except Exception:
        pass

    try:
        form = SolicitacaoAbonoParcialEtapa2FormFactory(motivo_solicitacao, data_aplicacao)(
            request.POST or None,
            files=request.FILES or None,
            initial={'data_aplicacao': data_aplicacao.strftime('%Y-%m-%d')},
            request=request,
        )
    except PontoException as erro:
        return httprr(
            '/ponto/solicitar_abono_parcial_etapa_1',
            f'Ocorreu um erro durante a solicitação: "{erro!s}". Tente novamente.',
            tag='error',
            close_popup=True,
        )
    except Exception:
        return httprr(
            '/ponto/solicitar_abono_parcial_etapa_1',
            'Ocorreu um erro durante a solicitação. Tente novamente.',
            tag='error',
            close_popup=True,
        )

    if form.is_valid():
        form.save()
        if not next_url:
            next_url = f'/ponto/visualizar_abono_parcial/{form.instance.id}/'
        return httprr(next_url, 'Solicitação de Abono Parcial salva com sucesso.', close_popup=True)

    title = 'Nova Solicitação de Abono Parcial'

    return locals()


@rtr()
@login_required
@permission_required('ponto.view_solicitacaoabonoparcial')
def visualizar_abono_parcial(request, abono_parcial_id):
    if not SolicitacaoAbonoParcial.solicitacao_abono_parcial_ativada():
        raise PermissionDenied

    abono_parcial = get_object_or_404(SolicitacaoAbonoParcial, pk=abono_parcial_id)

    pode_visualizar = abono_parcial.pode_visualizar(request.user)
    if not pode_visualizar:
        raise PermissionDenied('Você não tem permissão para visualizar esta solicitação de abono parcial.')

    pode_editar = abono_parcial.pode_editar(request.user)
    pode_remover = abono_parcial.pode_remover(request.user)
    pode_avaliar = abono_parcial.pode_avaliar(request.user)

    abono_parcial_vinculo_pessoa_relacionamento: Servidor = abono_parcial.vinculo_pessoa.relacionamento

    abono_chefia = abono_parcial.abono_chefia
    pode_editar_avaliacao = abono_chefia and abono_chefia.pode_editar_avaliacao(request.user)
    abono_parcial_get_abono_chefia_display_html = abono_parcial.get_abono_chefia_display_html(abono_chefia)

    eh_solicitante = abono_parcial_vinculo_pessoa_relacionamento == request.user.get_relacionamento()
    chefes = sorted(abono_parcial.chefes_data_aplicacao.all(), key=str)
    exibir_lista_chefes = eh_solicitante

    title = 'Solicitação de Abono Parcial'

    return locals()


@rtr()
@login_required
@permission_required('ponto.view_solicitacaoabonoparcial')
def inicializar_chefes_abono_parcial(request, abono_parcial_id):
    if not SolicitacaoAbonoParcial.solicitacao_abono_parcial_ativada():
        raise PermissionDenied

    abono_parcial = get_object_or_404(SolicitacaoAbonoParcial, pk=abono_parcial_id)

    pode_visualizar = abono_parcial.pode_visualizar(request.user)
    if not pode_visualizar:
        raise PermissionDenied('Você não tem permissão para visualizar esta solicitação de abono parcial.')

    abono_parcial.inicializar_chefes_data_aplicacao()

    return httprr(
        f'/ponto/visualizar_abono_parcial/{abono_parcial_id}/',
        'Solicitação de Abono Parcial atualizada.',
        close_popup=True,
    )


@rtr()
@login_required
@permission_required('ponto.add_solicitacaoabonoparcial')
def editar_abono_parcial(request, abono_parcial_id):
    if not SolicitacaoAbonoParcial.solicitacao_abono_parcial_ativada():
        raise PermissionDenied

    abono_parcial = get_object_or_404(SolicitacaoAbonoParcial, pk=abono_parcial_id)

    pode_editar = abono_parcial.pode_editar(request.user)
    if not pode_editar:
        raise PermissionDenied('Você não tem permissão para editar esta solicitação de abono parcial.')

    form = SolicitacaoAbonoParcialForm(
        request.POST or None,
        files=request.FILES or None,
        instance=abono_parcial,
        request=request,
    )

    if form.is_valid():
        form.save()
        return httprr(f'/ponto/visualizar_abono_parcial/{form.instance.id}/', 'Solicitação de Abono Parcial salva com sucesso.', close_popup=True)

    title = 'Editar Solicitação de Abono Parcial'

    return locals()


@rtr()
@login_required
@permission_required('ponto.change_solicitacaoabonoparcial')
def avaliar_abono_parcial(request, abono_parcial_id):
    if not SolicitacaoAbonoParcial.solicitacao_abono_parcial_ativada():
        raise PermissionDenied

    abono_parcial = get_object_or_404(SolicitacaoAbonoParcial, pk=abono_parcial_id)

    pode_avaliar = abono_parcial.pode_avaliar(request.user)
    if not pode_avaliar:
        raise PermissionDenied('Você não tem permissão para avaliar esta solicitação de abono parcial.')

    form = SolicitacaoAbonoParcialAvaliarFormFactory()(request.POST or None, solicitacoes=[abono_parcial], request=request)
    descricao_abonos = form.descricao_abonos

    if form.is_valid():
        save_erros = form.save()
        next_url = request.GET.get('next_url') or '..'
        if save_erros:
            return httprr(next_url, f'Erro durante a avaliação de abono parcial: {" ".join(save_erros)}', tag='error')
        else:
            return httprr(next_url, 'Abono parcial avaliado com sucesso.')

    title = 'Avaliar Frequência de Servidor com Solicitação de Abono Parcial'

    return locals()


@rtr()
@login_required
@permission_required('ponto.change_solicitacaoabonoparcial')
def avaliar_abono_parcial_lote(request):
    if not SolicitacaoAbonoParcial.solicitacao_abono_parcial_ativada():
        raise PermissionDenied

    abono_parcial_ids = list(set(request.GET.getlist('ids', [])))

    solicitacoes = []
    servidores = []
    msg_erro = []

    abonos_parciais = SolicitacaoAbonoParcial.objects.filter(id__in=abono_parcial_ids).order_by('data_aplicacao')

    for abono_parcial in abonos_parciais:
        if not abono_parcial.situacao_is_avaliado:
            solicitacoes.append(abono_parcial)
            servidores.append(abono_parcial.vinculo_pessoa)

    if not solicitacoes:
        # não há solicitações a avaliar na requisição
        return httprr('/admin/ponto/solicitacaoabonoparcial/?tab=solicitacoes_terceiros_avaliadas')

    if len(solicitacoes) == 1:
        # a solicitação deve ser avaliada individualmente
        return httprr(f'/ponto/avaliar_abono_parcial/{solicitacoes[0].id}?next_url=/ponto/visualizar_abono_parcial/{solicitacoes[0].id}')

    servidores = list(set(servidores))
    if len(servidores) > 1:
        msg_erro.append('Você deve selecionar as solicitações de um único servidor.')
        solicitacoes = []

    msg_erro = list(set(msg_erro))

    form = SolicitacaoAbonoParcialAvaliarFormFactory()(request.POST or None, solicitacoes=solicitacoes, request=request)
    descricao_abonos = form.descricao_abonos

    if form.is_valid():
        save_erros = form.save()
        if save_erros:
            return httprr('..', f'Erro durante a avaliação de abono parcial em lote: {" ".join(save_erros)}', tag='error')
        else:
            return httprr('..', 'Abono parcial em lote avaliado com sucesso.')

    title = 'Avaliar Frequência em Lote de Servidor com Solicitação de Abono Parcial'

    return locals()


def get_abono_chefia_ctx(request, abono_chefia_id, para_editar=False):
    abono = get_object_or_404(AbonoChefia, pk=abono_chefia_id)

    pode_visualizar = abono.pode_visualizar_avaliacao(request.user)
    if not pode_visualizar:
        raise PermissionDenied('Você não tem permissão para visualizar esta avaliação de frequência.')

    pode_editar = abono.pode_editar_avaliacao(request.user)
    if para_editar and not pode_editar:
        raise PermissionDenied('Você não tem permissão para editar esta avaliação de frequência.')

    pode_solicitar_revisao = abono.pode_solicitar_revisao_avaliacao(request.user)

    data_inconsistencia = abono.data
    contexto_compensacao = Contexto(
        servidor=abono.vinculo_pessoa.relacionamento, periodo_data_inicial=data_inconsistencia, periodo_data_final=data_inconsistencia
    )
    inconsistencias = Frequencia.get_inconsistencias(abono.vinculo_pessoa, data_inconsistencia, data_inconsistencia, contexto_compensacao).get(
        data_inconsistencia, []
    )

    frequencias_servidor = Frequencia.get_frequencias_por_data(abono.vinculo_pessoa, data_inconsistencia)
    observacoes = Observacao.objects.filter(vinculo=abono.vinculo_pessoa, data=data_inconsistencia)
    anexos = DocumentoAnexo.objects.filter(vinculo=abono.vinculo_pessoa, data=data_inconsistencia)

    jornadas_trabalho, _, __ = abono.vinculo_pessoa.relacionamento.get_jornadas_periodo_dict(data_inconsistencia, data_inconsistencia)
    jornada_trabalho = jornadas_trabalho.get(data_inconsistencia)

    informacao_registro = []
    for inconsistencia in inconsistencias:
        informacao_registro.append(Frequencia.DISPLAY_INCONSISTENCIA[inconsistencia])

    inconsistencias_detalhes = Frequencia.get_detalhamento_inconsistencias(
        inconsistencias, data_inconsistencia, data_inconsistencia, contexto_compensacao
    )

    return locals()


@rtr()
@login_required
def visualizar_abono_chefia(request, abono_chefia_id):
    title = 'Abono de Chefia'

    ctx = locals()
    ctx.update(get_abono_chefia_ctx(request, abono_chefia_id))

    return ctx


@rtr()
@login_required
def editar_abonos_chefia(request, servidor_matricula, data):
    servidor_inconsistencia = get_object_or_404(Servidor, matricula=servidor_matricula)
    data_inconsistencia = data

    abonos_chefia = AbonoChefia.objects.filter(vinculo_pessoa=servidor_inconsistencia.get_vinculo(), data=data_inconsistencia)

    pode_editar = any(abono.pode_editar_avaliacao(request.user) for abono in abonos_chefia)

    if not pode_editar:
        abonos_chefia = AbonoChefia.objects.none()

    title = 'Editar Avaliações de Frequência'

    return locals()


@rtr()
@login_required
def editar_abono_chefia(request, abono_chefia_id):
    abono_chefia_ctx = get_abono_chefia_ctx(request, abono_chefia_id, para_editar=True)

    form_class = AbonoChefiaChangeFormFactory(abono_chefia_ctx['inconsistencias'], abono_chefia_ctx['abono'])
    form = form_class(request.POST or None, instance=abono_chefia_ctx['abono'], request=request)
    descricao_abonos = form.descricao_abonos

    if form.is_valid():
        form.save()
        next_url = request.GET.get('next_url') or '..'
        next_msg = request.GET.get('next_msg') or 'Avaliação de frequência atualizada com sucesso.'
        close_popup = request.GET.get('close_popup') == '1' or False
        return httprr(next_url, next_msg, close_popup=close_popup)

    title = f'Editar Avaliação de Frequência {"com Solicitação de Abono Parcial" if abono_chefia_ctx["abono"].solicitacao_abono_parcial else ""}'

    ctx = locals()
    ctx.update(abono_chefia_ctx)

    return ctx


@rtr()
@login_required
def remover_abono_chefia(request, abono_chefia_id):
    abono = get_object_or_404(AbonoChefia, pk=abono_chefia_id)

    pode_editar = abono.pode_editar_avaliacao(request.user)
    if not pode_editar:
        raise PermissionDenied('Você não tem permissão para remover esta avaliação de frequência.')

    abono.delete()

    next_url = request.GET.get('next_url') or '..'
    next_msg = request.GET.get('next_msg') or 'Avaliação de frequência removida com sucesso.'
    close_popup = request.GET.get('close_popup') == '1' or False

    return httprr(next_url, next_msg, close_popup=close_popup)


@rtr()
@login_required
@permission_required('ponto.view_solicitacaoabonoparcial')
def visualizar_abono_parcial_gravidez(request, abono_parcial_gravidez_id):
    if not SolicitacaoAbonoParcial.solicitacao_abono_parcial_ativada():
        raise PermissionDenied

    abono_parcial_gravidez = get_object_or_404(SolicitacaoAbonoParcialGravidez, pk=abono_parcial_gravidez_id)

    pode_visualizar = abono_parcial_gravidez.pode_visualizar(request.user)
    if not pode_visualizar:
        raise PermissionDenied('Você não tem permissão para visualizar este cadastro de gravidez de esposa ou companheira.')

    title = 'Gravidez de Esposa ou Companheira'

    return locals()


@rtr()
@login_required
@permission_required('ponto.add_solicitacaoabonoparcial')
def meus_direitos_e_historico_abono_parcial(request):
    if not SolicitacaoAbonoParcial.solicitacao_abono_parcial_ativada():
        raise PermissionDenied

    servidor_logado = request.user.get_vinculo().relacionamento

    # usuário logado pode visualizar o histórico de um terceiro servidor que já avaliou ou está para avaliar
    usuario_logado_avaliacoes = SolicitacaoAbonoParcial.query_solicitacoes_terceiros(request.user)
    if usuario_logado_avaliacoes.exists():
        FilterFormClass = DireitosHistoricoAbonoParcialFilterFormFactory(
            Servidor.objects.filter(
                id__in=[solicitacao.vinculo_pessoa.relacionamento.id for solicitacao in usuario_logado_avaliacoes] + [servidor_logado.id]
            )
        )

        form_data = request.GET if request.GET and 'servidor' in request.GET else None
        form = FilterFormClass(form_data or {'servidor': servidor_logado.id})

        if form.is_valid():
            servidor = form.cleaned_data.get('servidor')
        else:
            servidor = None
    else:
        form = None
        servidor = servidor_logado

    historicos = SolicitacaoAbonoParcial.query_historicos(servidor) if servidor else []

    ###
    # motivo: consulta de saúde

    consulta_saude_motivo = SolicitacaoAbonoParcial.MOTIVO_CONSULTA_SAUDE
    consulta_saude_motivo_display = SolicitacaoAbonoParcial(motivo=consulta_saude_motivo).get_motivo_display()

    consulta_saude_limite_qtd_consultas_por_gravidez = SolicitacaoAbonoParcial.consulta_saude_limite_qtd_consultas_por_gravidez()

    class ConsultaSaudeLimiteAnualPorCHDiaria:
        ch_diaria: int
        ch_limite_segundos: int

        def __init__(self, ch_diaria: int, ch_limite_segundos: int):
            self.ch_diaria = ch_diaria
            self.ch_limite_segundos = ch_limite_segundos

        @property
        def ch_limite_segundos_display(self):
            return formata_segundos(self.ch_limite_segundos, '{h:02.0f}h ', '{m:02.0f}min ', '{s:02.0f}seg ', True)

    consulta_saude_limites_anuais_por_ch_diaria = [
        ConsultaSaudeLimiteAnualPorCHDiaria(ch_diaria, ch_limite_segundos)
        for ch_diaria, ch_limite_segundos in SolicitacaoAbonoParcial.consulta_saude_limites_anuais_por_ch_diaria().items()
    ]

    consulta_saude_limite_qtd_consultas_por_gravidez_historico = (
        SolicitacaoAbonoParcial.consulta_saude_limite_qtd_consultas_por_gravidez_historico(servidor) if servidor else []
    )
    consulta_saude_limites_anuais_por_ch_diaria_historico = (
        SolicitacaoAbonoParcial.consulta_saude_limites_anuais_por_ch_diaria_historico(servidor) if servidor else {}
    )

    consulta_saude_solicitacoes_pendentes = SolicitacaoAbonoParcial.query_solicitacoes_pendentes(
        servidor, SolicitacaoAbonoParcial.MOTIVO_CONSULTA_SAUDE
    ).order_by('data_aplicacao')
    consulta_saude_solicitacoes_pendentes_qtd = consulta_saude_solicitacoes_pendentes.count()

    ###

    if (servidor_logado == servidor) or not servidor:
        title = 'Abono Parcial - Meus Direitos / Meu Histórico'
    else:
        title = f'Abono Parcial - Direitos / Histórico de {servidor}'

    return locals()


@rtr()
@login_required
@permission_required('ponto.add_solicitacaoabonoparcial')
def meu_historico_detalhes_abono_parcial(request):
    if not SolicitacaoAbonoParcial.solicitacao_abono_parcial_ativada():
        raise PermissionDenied

    servidor_logado = request.user.get_vinculo().relacionamento

    # ?...&servidor=?
    servidor_id = int(request.GET.get('servidor', '0'))
    if servidor_id:
        servidor = Servidor.objects.filter(id=servidor_id).first()
    else:
        servidor = servidor_logado

    if servidor_logado != servidor:
        # confirma se o servidor logado pode ver o histórico do servidor informado
        usuario_logado_avaliacoes = SolicitacaoAbonoParcial.query_solicitacoes_terceiros(request.user)
        servidor_ok = False

        if usuario_logado_avaliacoes.exists():
            servidor_ok = servidor in [solicitacao.vinculo_pessoa.relacionamento for solicitacao in usuario_logado_avaliacoes]

        if not servidor_ok:
            raise PermissionDenied('O servidor informado é inválido.')

    historicos = SolicitacaoAbonoParcial.query_historicos(servidor)

    # ?...&motivo=?
    motivo = int(request.GET.get('motivo', '0'))
    if motivo:
        historicos = historicos.filter(solicitacao_abono_parcial__motivo=motivo)
        motivo_display = SolicitacaoAbonoParcial(motivo=motivo).get_motivo_display()

    # ?...&ano=?
    ano = int(request.GET.get('ano', '0'))
    if ano:
        historicos = historicos.filter(solicitacao_abono_parcial__data_aplicacao__year=ano)

    # ?...&gravidez_id=?
    gravidez_id = int(request.GET.get('gravidez_id', '0'))
    if gravidez_id:
        gravidez = SolicitacaoAbonoParcialGravidez.objects.filter(id=gravidez_id).first()
        historicos = historicos.filter(solicitacao_abono_parcial__acompanhamento_gravidez=gravidez)

    # ?...&hide_gravidez=1
    hide_gravidez = int(request.GET.get('hide_gravidez', '0')) == 1
    if hide_gravidez:
        gravidez = None
        historicos = historicos.exclude(solicitacao_abono_parcial__acompanhamento_gravidez__isnull=False)

    # ?...&only_abonos_sem_compensacao=1
    only_abonos_sem_compensacao = int(request.GET.get('only_abonos_sem_compensacao', '0')) == 1
    if only_abonos_sem_compensacao:
        historicos = historicos.filter(acao_abono=AbonoChefia.ABONADO)

    historicos = historicos.order_by('solicitacao_abono_parcial__data_aplicacao')

    if servidor_logado == servidor:
        title = 'Abono Parcial - Meu Histórico - Detalhes das Avaliações'
    else:
        title = f'Abono Parcial - Histórico de {servidor} - Detalhes das Avaliações'

    return locals()


@rtr()
@login_required
@permission_required('ponto.add_solicitacaorevisaoabonochefia')
def solicitar_revisao_abono_chefia(request, data):
    if not SolicitacaoAbonoParcial.solicitacao_abono_parcial_ativada():
        raise PermissionDenied

    vinculo = request.user.get_vinculo()

    if not AbonoChefia.pode_solicitar_revisao_abono_chefia(vinculo, data, data).get(data):
        raise PermissionDenied

    form = SolicitacaoRevisaoAbonoChefiaFormFactory(
        vinculo=vinculo,
        data_inicio=data,
        data_fim=data,
    )(request.POST or None)

    form.EXTRA_INFO = """
        <strong>Atenção</strong>: As solicitações de revisão de abono de chefia serão avaliadas
        pelo chefe imediato, o qual será notificado. Durante a avaliação, o chefe imediato poderá
        manter, editar ou remover o abono em questão.
    """

    if form.is_valid():
        solicitacao = form.save()
        return httprr(solicitacao.get_absolute_url(), 'Solicitação salva com sucesso.', tag='success', close_popup=True)

    title = 'Solicitar Revisão de Abono de Chefia'

    return locals()


@rtr()
@login_required
@permission_required('ponto.view_solicitacaorevisaoabonochefia')
def visualizar_revisao_abono_chefia(request, revisao_abono_chefia_id):
    if not SolicitacaoAbonoParcial.solicitacao_abono_parcial_ativada():
        raise PermissionDenied

    revisao_abono_chefia = get_object_or_404(SolicitacaoRevisaoAbonoChefia, pk=revisao_abono_chefia_id)

    permissoes = AbonoChefia.get_permissoes_solicitacao_revisao_abono_chefia(request.user.get_vinculo(), revisao_abono_chefia)

    if not permissoes.get('pode_visualizar'):
        raise PermissionDenied

    pode_editar = permissoes.get('pode_editar')
    pode_avaliar = permissoes.get('pode_avaliar')
    pode_editar_avaliacao = permissoes.get('pode_editar_avaliacao')
    pode_remover = permissoes.get('pode_remover')

    title = 'Solicitação de Revisão de Abono de Chefia'

    return locals()


@rtr()
@login_required
@permission_required('ponto.add_solicitacaorevisaoabonochefia')
def editar_revisao_abono_chefia(request, revisao_abono_chefia_id):
    if not SolicitacaoAbonoParcial.solicitacao_abono_parcial_ativada():
        raise PermissionDenied

    revisao_abono_chefia = get_object_or_404(SolicitacaoRevisaoAbonoChefia, pk=revisao_abono_chefia_id)

    permissoes = AbonoChefia.get_permissoes_solicitacao_revisao_abono_chefia(request.user.get_vinculo(), revisao_abono_chefia)

    if not permissoes.get('pode_editar'):
        raise PermissionDenied

    form = SolicitacaoRevisaoAbonoChefiaChangeForm(
        request.POST or None,
        instance=revisao_abono_chefia,
    )

    form.EXTRA_INFO = """
        <strong>Atenção</strong>: As solicitações de revisão de abono de chefia serão avaliadas
        pelo chefe imediato, o qual será notificado. Durante a avaliação, o chefe imediato poderá
        manter, editar ou remover o abono em questão.
    """

    if form.is_valid():
        solicitacao = form.save()
        return httprr(solicitacao.get_absolute_url(), 'Solicitação salva com sucesso.', tag='success', close_popup=True)

    title = f'Editar Revisão de Abono de Chefia: {revisao_abono_chefia.abono_chefia_display}'

    return locals()


@rtr()
@login_required
@permission_required('ponto.add_solicitacaorevisaoabonochefia')
def avaliar_revisao_abono_chefia(request, revisao_abono_chefia_id):
    if not SolicitacaoAbonoParcial.solicitacao_abono_parcial_ativada():
        raise PermissionDenied

    revisao_abono_chefia = get_object_or_404(SolicitacaoRevisaoAbonoChefia, pk=revisao_abono_chefia_id)

    permissoes = AbonoChefia.get_permissoes_solicitacao_revisao_abono_chefia(request.user.get_vinculo(), revisao_abono_chefia)

    if not permissoes.get('pode_avaliar') and not permissoes.get('pode_editar_avaliacao'):
        raise PermissionDenied

    form = AvaliacaoRevisaoAbonoChefiaChangeForm(
        request.POST or None,
        vinculo_chefe_imediato=request.user.get_vinculo(),
        instance=revisao_abono_chefia,
    )

    if form.is_valid():
        solicitacao = form.save()
        if form.editar_abono():
            return httprr(
                f'/ponto/editar_abono_chefia/{solicitacao.abono_chefia.id}/?next_url={solicitacao.get_absolute_url()}&next_msg=Solicitação de Revisão de Abono de Chefia avaliada com sucesso. O Abono foi atualizado.&_popup=1&close_popup=1',
                'Solicitação de Revisão de Abono de Chefia avaliada com sucesso. Proceda agora com a edição do Abono.',
            )
        elif form.remover_abono():
            return httprr(
                f'/ponto/remover_abono_chefia/{solicitacao.abono_chefia.id}/?next_url={solicitacao.get_absolute_url()}&next_msg=Solicitação de Revisão de Abono de Chefia avaliada com sucesso. O Abono foi removido.&_popup=1&close_popup=1'
            )
        else:
            return httprr(
                solicitacao.get_absolute_url(), 'Solicitação de Revisão de Abono de Chefia avaliada com sucesso.', tag='success', close_popup=True
            )

    title = f'Avaliar Revisão de Abono de Chefia: {revisao_abono_chefia.abono_chefia_display}'

    return locals()


@rtr()
@login_required
def relatorio_presenca_por_dia(request):
    title = 'Relatório de presença de servidores/prestadores em tempo real'
    data_desejada = date.today()
    form = DataRelatorioOcupacaoForm(request.POST or None)
    tipo_relacionamento = None
    if form.is_valid():
        data_desejada = form.cleaned_data.get('data')
        tipo_relacionamento = form.cleaned_data.get('tipo_relacionamento')

    # Inicializa um dicionário para armazenar a presença de servidores em cada hora para cada UO
    presenca_por_hora_por_uo = {}
    subquery_proxima_saida = (
        Frequencia.objects.filter(
            vinculo=OuterRef('vinculo'),
            horario__date=data_desejada,
            horario__gt=OuterRef('horario'),
            acao='S',  # Frequências de saída
        )
        .order_by('horario')
        .values('horario')[:1]
    )

    # Annotate para trazer o horário da próxima frequência de saída para cada frequência de entrada
    frequencias_entrada = (
        Frequencia.objects.filter(
            horario__date=data_desejada,
            acao='E',  # Frequências de entrada
        )
        .order_by('horario')
        .select_related('vinculo', 'vinculo__setor', 'vinculo__setor__uo')
        .annotate(proxima_saida=Subquery(subquery_proxima_saida))
    )
    if tipo_relacionamento:
        filters = {}
        if tipo_relacionamento in ['servidor', 'estagiario', 'docente', 'tecnico']:
            filters['vinculo__user__eh_servidor'] = True
            if tipo_relacionamento == 'docente':
                filters['vinculo__user__eh_docente'] = True
            elif tipo_relacionamento == 'tecnico':
                filters['vinculo__user__eh_tecnico_administrativo'] = True
            elif tipo_relacionamento == 'estagiario':
                # Esse filtro não é tão correto por que em algumas situações servidores principalmente quando são de carreiras
                # distintas do PCCTAE o suap nao entende como categorizar se nao disser no grupo cargo emprego.
                filters['vinculo__user__eh_tecnico_administrativo'] = False
                filters['vinculo__user__eh_docente'] = False
        elif tipo_relacionamento == 'prestador':
            filters['vinculo__user__eh_prestador'] = True
        frequencias_entrada = frequencias_entrada.filter(**filters)

    for frequencia_entrada in frequencias_entrada:
        if frequencia_entrada.proxima_saida:
            # Calcula o intervalo de tempo entre a entrada e a saída
            intervalo_tempo = frequencia_entrada.proxima_saida - frequencia_entrada.horario

            # Divide o intervalo de tempo em horas e atribui as horas aos registros para cada UO
            for i in range(intervalo_tempo.seconds // 3600 + 1):
                hora = (frequencia_entrada.horario + timedelta(hours=i)).replace(minute=0, second=0, microsecond=0)
                setor_uo = frequencia_entrada.vinculo.setor.uo.sigla if frequencia_entrada.vinculo.setor else 'Sem UO'
                presenca_por_hora_por_uo.setdefault(setor_uo, {}).setdefault(hora, 0)
                presenca_por_hora_por_uo[setor_uo][hora] += 1

    total_por_hora_por_uo = {}
    total_por_hora_instituicao = {}
    # Calcula o total de servidores presentes em cada hora para cada UO
    for setor_uo, presenca_por_hora in presenca_por_hora_por_uo.items():
        total_por_hora_por_uo[setor_uo] = sum(presenca_por_hora.values())
        # Calcula o total de servidores presentes em cada hora para toda a instituição
        for hora, presenca in presenca_por_hora.items():
            total_por_hora_instituicao[hora] = total_por_hora_instituicao.get(hora, 0) + presenca

    horas = sorted(set(total_por_hora_instituicao))

    return locals()
