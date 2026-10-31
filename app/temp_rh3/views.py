import datetime
import hashlib

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http.response import HttpResponseBadRequest
from django.shortcuts import get_object_or_404
from django_tables2.columns.base import Column
from django_tables2.columns.linkcolumn import LinkColumn
from django_tables2.utils import Accessor

from comum.models import Configuracao
from djtools import tasks
from djtools.tables import get_table
from djtools.utils import httprr, permission_required, rtr
from temp_rh3.forms import QuestionarioFiltroForm, ResponderQuestionarioAcumuloCargosForm
from temp_rh3.models import QuestionarioAcumuloCargos, TermoAcumuloCargos


@rtr()
@login_required
def responder_questionario(request, pk):
    questionario = get_object_or_404(QuestionarioAcumuloCargos, pk=pk)
    title = questionario.descricao
    info = 'As informações prestadas neste formulário serão consideradas verídicas, sujeitando-se o servidor à apuração de responsabilidade administrativa (através de PAD), civil e penal, no caso de prestar informação falsa.'

    if not request.user.eh_servidor:
        raise PermissionDenied('Só Servidores respondem o termo de acumulação de cargos.')

    servidor = request.user.get_relacionamento()
    if servidor.eh_estagiario:
        raise PermissionDenied('Estagiários não respondem o termo de acumulação de cargos.')

    if questionario not in QuestionarioAcumuloCargos.get_pendente(servidor):
        raise PermissionDenied

    hoje = datetime.date.today()
    if not questionario.data_inicio <= hoje <= questionario.data_fim:
        raise PermissionDenied('Não estamos no período para responder questionário.')

    try:
        resposta_termo_acumulo_cargos = TermoAcumuloCargos.objects.get(servidor=servidor, questionario_acumulo_cargos=questionario)
    except Exception:
        resposta_termo_acumulo_cargos = TermoAcumuloCargos(servidor=servidor, questionario_acumulo_cargos=questionario)

    form = ResponderQuestionarioAcumuloCargosForm(request.POST or None, instance=resposta_termo_acumulo_cargos)
    if form.is_valid():
        resposta_termo_acumulo_cargos.alterado_por = request.user
        resposta_termo_acumulo_cargos.alterado_em = datetime.datetime.now()
        string_hash = '{}|{}|{}|{}'.format(
            *(questionario.pk, servidor.pk, resposta_termo_acumulo_cargos.alterado_em, resposta_termo_acumulo_cargos.termo_hash).encode()
        )
        resposta_termo_acumulo_cargos.hash = hashlib.sha1(string_hash).hexdigest()
        form.save()
        return httprr('..', 'Termo de Acúmulo de Cargos salvo com sucesso.')

    return locals()


@rtr()
@permission_required('rh.pode_ver_relatorios_rh')
def resultado_questionario(request):
    form = QuestionarioFiltroForm(request.GET or None)
    title = 'Resultados dos Termos de Acúmulo de Cargos'
    questionarios_respondidos = TermoAcumuloCargos.objects.all()
    if form.is_valid():
        campus = form.cleaned_data.get('campus')
        if campus:
            questionarios_respondidos = questionarios_respondidos.filter(servidor__setor__uo=campus)
        questionario_acumulo_cargos = form.cleaned_data.get('questionario_acumulo_cargos')
        if questionario_acumulo_cargos:
            questionarios_respondidos = questionarios_respondidos.filter(questionario_acumulo_cargos=questionario_acumulo_cargos)

        nao_possui_outro_vinculo = form.cleaned_data.get('nao_possui_outro_vinculo')
        if nao_possui_outro_vinculo and int(nao_possui_outro_vinculo):
            questionarios_respondidos = questionarios_respondidos.filter(nao_possui_outro_vinculo=int(nao_possui_outro_vinculo) == 1)

        tem_outro_cargo_acumulavel = form.cleaned_data.get('tem_outro_cargo_acumulavel')
        if tem_outro_cargo_acumulavel and int(tem_outro_cargo_acumulavel):
            questionarios_respondidos = questionarios_respondidos.filter(tem_outro_cargo_acumulavel=int(tem_outro_cargo_acumulavel) == 1)

        tem_aposentadoria = form.cleaned_data.get('tem_aposentadoria')
        if tem_aposentadoria and int(tem_aposentadoria):
            questionarios_respondidos = questionarios_respondidos.filter(tem_aposentadoria=int(tem_aposentadoria) == 1)

        tem_pensao = form.cleaned_data.get('tem_pensao')
        if tem_pensao and int(tem_pensao):
            questionarios_respondidos = questionarios_respondidos.filter(tem_pensao=int(tem_pensao) == 1)

    custom_fields = {
        'link_column': LinkColumn(
            'detalhar_resposta_questionario',
            kwargs={'resposta_pk': Accessor('pk')},
            verbose_name='-',
            accessor=Accessor('pk'),
            attrs={'a': {'class': 'icon-view'}},
        ),
        'nao_possui_outro_vinculo': Column('Não Possui Outro Vínculo', accessor='nao_possui_outro_vinculo', order_by='nao_possui_outro_vinculo'),
        'tem_outro_cargo_acumulavel': Column(
            'Tem Outro Cargo Acumulável', accessor='tem_outro_cargo_acumulavel', order_by='tem_outro_cargo_acumulavel'
        ),
        'tem_aposentadoria': Column('Percebe aposentadoria', accessor='tem_aposentadoria', order_by='tem_aposentadoria'),
        'tem_pensao': Column('É beneficiário de pensão', accessor='tem_pensao', order_by='tem_pensao'),
        'tem_atuacao_gerencial': Column(
            'Tem atuação gerencial em atividade mercantil', accessor='tem_atuacao_gerencial', order_by='tem_atuacao_gerencial'
        ),
        'exerco_atividade_remunerada_privada': Column(
            'Exerce atividade remunerada privada', accessor='exerco_atividade_remunerada_privada', order_by='exerco_atividade_remunerada_privada'
        ),
    }
    fields = ('questionario_acumulo_cargos', 'servidor')
    sequence = [
        'link_column',
        'questionario_acumulo_cargos',
        'servidor',
        'nao_possui_outro_vinculo',
        'tem_outro_cargo_acumulavel',
        'tem_aposentadoria',
        'tem_pensao',
        'tem_atuacao_gerencial',
        'exerco_atividade_remunerada_privada',
    ]
    table_questionarios_respondidos = get_table(
        queryset=questionarios_respondidos, custom_fields=custom_fields, sequence=sequence, fields=fields, per_page_field=100
    )
    if request.GET.get('relatorio', None):
        return tasks.table_export(request.GET.get('relatorio', None), *table_questionarios_respondidos.get_params())
    return locals()


@rtr()
def detalhar_resposta_questionario(request, resposta_pk):
    resposta_questionario = get_object_or_404(TermoAcumuloCargos, pk=resposta_pk)
    servidor = resposta_questionario.servidor
    title = resposta_questionario
    verificacao_propria = request.user == servidor.get_user()
    is_rh = request.user.has_perm('rh.change_servidor')
    if not is_rh and not verificacao_propria:
        return HttpResponseBadRequest('Você não tem permissão de acesso!')
    instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao')
    return locals()
