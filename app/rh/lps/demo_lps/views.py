from collections import OrderedDict
from datetime import date

from django.shortcuts import get_object_or_404

from comum.models import Configuracao
from djtools.utils import get_qtd_dias_por_ano, permission_required, rtr
from rh.models import (
    PCA,
    Servidor,
    ServidorAfastamento,
    ServidorFuncaoHistorico,
    ServidorOcorrencia,
    ServidorSetorHistorico,
    ServidorSetorLotacaoHistorico,
    Situacao,
    Viagem,
)
from rh.views import index, rh_servidor_view_tab

"""
Substituição da view servidor em views.py
"""


@rtr()
@permission_required('rh.view_servidor')
def servidor(request, servidor_matricula):
    servidor = get_object_or_404(Servidor, matricula=servidor_matricula)
    title = str(servidor) + ' LPS'
    verificacao_propria = request.user == servidor.get_user()
    is_chefe = False

    if request.user.eh_servidor:
        is_chefe = request.user.get_relacionamento().eh_chefe_de(servidor)

    pode_ver_cpf_servidor = request.user.has_perm('rh.pode_ver_cpf_servidor') or verificacao_propria
    pode_ver_dados_pessoais_servidor = request.user.has_perm('rh.pode_ver_dados_pessoais_servidor') or verificacao_propria
    pode_ver_endereco_servidor = request.user.has_perm('rh.pode_ver_endereco_servidor') or verificacao_propria
    pode_ver_telefones_pessoais_servidor = request.user.has_perm('rh.pode_ver_telefones_pessoais_servidor') or verificacao_propria
    pode_ver_dados_bancarios_servidor = request.user.has_perm('rh.pode_ver_dados_bancarios_servidor') or verificacao_propria
    pode_ver_historico_funcional_servidor = request.user.has_perm('rh.pode_ver_historico_funcional_servidor') or verificacao_propria
    pode_ver_ocorrencias_afastamentos_servidor = (
        request.user.has_perm('rh.pode_ver_ocorrencias_afastamentos_servidor') or verificacao_propria or is_chefe
    )
    pode_ver_historico_setores_servidor = request.user.has_perm('rh.pode_ver_historico_setores_servidor') or verificacao_propria
    pode_ver_historico_funcao_servidor = request.user.has_perm('rh.pode_ver_historico_funcao_servidor') or verificacao_propria
    pode_ver_viagens_servidor = request.user.has_perm('rh.pode_ver_viagens_servidor') or verificacao_propria or is_chefe
    pode_ver_dados_funcionais_servidor = request.user.has_perm('rh.pode_ver_dados_funcionais_servidor') or verificacao_propria
    pode_ver__identificacao_unica_siape = request.user.has_perm('rh.pode_ver_identificacao_unica_siape') or verificacao_propria

    hoje = date.today()
    endereco_irregular = not (
        servidor.pessoa_fisica.pessoaendereco
        and servidor.pessoa_fisica.pessoaendereco.municipio
        and (servidor.pessoa_fisica.pessoaendereco.municipio.uf == Configuracao.get_valor_por_chave('comum', 'instituicao_estado'))
    )

    # if verificacao_propria or is_rh or pode_ver_dados_extras:
    if pode_ver_ocorrencias_afastamentos_servidor:
        servidor_ocorrencias = (
            ServidorOcorrencia.objects.filter(servidor=servidor).exclude(ocorrencia__grupo_ocorrencia__nome='AFASTAMENTO').order_by('data')
        )
        servidor_afastamentos = ServidorAfastamento.objects.filter(servidor=servidor, cancelado=False).order_by('data_inicio')

        totais_qtd_dias_por_ano = OrderedDict()
        totais_qtd_dias_ocorrencias = 0
        totais_qtd_dias_afastamentos = 0
        for ocorrencia in servidor_ocorrencias:
            if ocorrencia.data_termino:
                for ano, qtd_dias in list(get_qtd_dias_por_ano(ocorrencia.data, ocorrencia.data_termino).items()):
                    if ano not in totais_qtd_dias_por_ano:
                        totais_qtd_dias_por_ano[ano] = [0, 0]
                    totais_qtd_dias_por_ano[ano][0] += qtd_dias  # 0 = ocorrências
                    totais_qtd_dias_ocorrencias += qtd_dias
        for afastamento in servidor_afastamentos:
            if afastamento.data_termino:
                for ano, qtd_dias in list(get_qtd_dias_por_ano(afastamento.data_inicio, afastamento.data_termino).items()):
                    if ano not in totais_qtd_dias_por_ano:
                        totais_qtd_dias_por_ano[ano] = [0, 0]
                    totais_qtd_dias_por_ano[ano][1] += qtd_dias  # 1 = afastamentos
                    totais_qtd_dias_afastamentos += qtd_dias

    if pode_ver_historico_setores_servidor:
        historico_setor = ServidorSetorHistorico.objects.filter(servidor=servidor).order_by('-data_inicio_no_setor')
        historico_setor_siape = ServidorSetorLotacaoHistorico.objects.filter(servidor=servidor).order_by('-data_inicio_setor_lotacao')

    funcoes_ativas = ServidorFuncaoHistorico.objects.atuais().filter(servidor=servidor).order_by('data_inicio_funcao')
    if pode_ver_historico_funcao_servidor:
        servidor_historico_funcao = ServidorFuncaoHistorico.objects.filter(servidor=servidor).order_by('data_inicio_funcao')

    pode_gerar_cracha = servidor.pode_gerar_cracha()
    pode_gerar_carteira_funcional = servidor.pode_gerar_carteira_funcional()

    # provimentos
    if pode_ver_historico_funcional_servidor:
        pcas = PCA.montar_timeline(servidor.pca_set.all().order_by('data_entrada_pca'))
        outros_vinculos = (
            Servidor.objects.filter(pessoa_fisica__cpf=servidor.pessoa_fisica.cpf)
            .exclude(situacao__codigo__in=Situacao.situacoes_siape_estagiarios())
            .exclude(pk=servidor.pk)
        )

        servidor_tempo_servico_na_instituicao_via_pca = servidor.tempo_servico_na_instituicao_via_pca()
        servidor_tempo_servico_na_instituicao_via_pca_ficto = servidor.tempo_servico_na_instituicao_via_pca(ficto=True)

    viagens_servidor = Viagem.consolidadas.filter(servidor=servidor).order_by('-data_inicio_viagem')

    extra_tabs = []
    for _, data in rh_servidor_view_tab.send(
        sender=index, request=request, servidor=servidor, verificacao_propria=verificacao_propria, eh_chefe=is_chefe
    ):
        if data:
            extra_tabs.append(data)

    return locals()
