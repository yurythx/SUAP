import json
from datetime import datetime, timedelta

from django.db.models import Exists, F, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt

from comum.models import Configuracao, User, Vinculo
from djtools.utils import JsonResponse
from ponto.models import Frequencia, MaquinaLog
from rh.models import Biometria, BiometriaSolicitacao, PessoaFisica, Servidor
from terminais.forms import DigitalForm
from terminais.utils import get_maquina, TemplateEncoder, str2bytes


def funcionarios(request: HttpRequest) -> HttpResponse:
    maquina = get_maquina(request=request)

    if not maquina:
        return JsonResponse({'msg': 'Máquina não tem permissão para registro de frequências.'}, status=400)

    MaquinaLog.objects.create(maquina=maquina, operacao='terminais_funcionarios')

    template = Biometria.objects.filter(tipo=Biometria.TIPO_DIGITAL, terminal_novo=True, pessoa_fisica_id=OuterRef('pessoa_fisica__id'))

    operador_chaves = User.objects.filter(
        id=OuterRef('vinculos__user_id'), groups__name__in=['Operador de Chaves', 'Coordenador de Chaves Sistêmico']
    )

    operadores_cadastro = User.objects.filter(id=OuterRef('vinculos__user_id'), groups__permissions__codename='pode_cadastrar_digital')

    funcionarios = (
        Servidor.objects.select_related('setor', 'setor__uo')
        .filter(
            ativo=True,
        )
        .annotate(
            pf_id=F('id'),
            pf_username=F('matricula'),
            pf_nome=F('pessoa_fisica__nome'),
            pf_setor_sigla=F('setor__sigla'),
            pf_campus_sigla=F('setor__uo__sigla'),
            pf_tem_digital_fraca=F('pessoa_fisica__tem_digital_fraca'),
            pf_pode_bater_ponto=Value(True),
            pf_senha_ponto=Coalesce(F('pessoa_fisica__senha_ponto'), Value('')),
            pf_operador_chaves=Exists(Subquery(operador_chaves)),
            pf_operador_cadastro=Exists(Subquery(operadores_cadastro)),
            pf_template=Subquery(template.values('template')),
            pf_exportada=Value(True),
        )
        .values(
            'pf_id',
            'pf_username',
            'pf_nome',
            'pf_setor_sigla',
            'pf_campus_sigla',
            'pf_tem_digital_fraca',
            'pf_pode_bater_ponto',
            'pf_senha_ponto',
            'pf_operador_chaves',
            'pf_operador_cadastro',
            'pf_template',
            'pf_exportada',
        )
    )

    data_json = json.dumps(list(funcionarios), cls=TemplateEncoder)

    return HttpResponse(data_json, content_type='application/json')


@csrf_exempt
def digitais(request: HttpRequest) -> HttpResponse:
    maquina = get_maquina(request=request)

    if not maquina:
        return JsonResponse({'msg': 'Máquina não tem permissão para registro de frequências.'}, status=400)

    MaquinaLog.objects.create(maquina=maquina, operacao='terminais_digitais')

    form = DigitalForm(request.POST or None)

    if form.is_valid():
        biometria = Biometria.objects.filter(
            tipo=Biometria.TIPO_DIGITAL, terminal_novo=True, pessoa_fisica__vinculo__user__username=form.cleaned_data['matricula']
        ).first()

        if not biometria:
            pessoa_fisica = PessoaFisica.objects.filter(vinculo__user__username=form.cleaned_data['matricula']).first()

            if not pessoa_fisica:
                return JsonResponse({'msg': 'Pessoa Física não encontrada'}, status=400)

            biometria = Biometria(pessoa_fisica=pessoa_fisica, tipo=Biometria.TIPO_DIGITAL, terminal_novo=True)

        biometria.template = str2bytes(form.cleaned_data['template'])
        biometria.save()

        return JsonResponse({'msg': 'Sucesso'})

    return JsonResponse({'msg': 'Formulário inválido'}, status=400)


@csrf_exempt
def frequencias(request):
    maquina = get_maquina(request=request)

    if not maquina:
        return JsonResponse({'msg': 'Máquina não tem permissão para registro de frequências.'}, status=400)

    usernames_erro = []
    vinculos = {}

    try:
        frequencias = json.loads(request.body)
    except Exception:
        frequencias = None

    if not isinstance(frequencias, list):
        return JsonResponse({'msg': 'Erro no formato dos dados enviados.'}, status=400)

    for frequencia in frequencias:
        matricula = frequencia['matricula']
        horario = datetime.strptime(frequencia['frequencia'], '%Y-%m-%d %H:%M:%S')

        query = Frequencia.objects.filter(vinculo__user__username=matricula, horario=horario)

        if not query.exists():
            if matricula not in vinculos:
                vinculo = Vinculo.objects.filter(user__username=matricula).first()

                if vinculo:
                    vinculos[matricula] = vinculo
                else:
                    usernames_erro.append(matricula)
                    continue

            Frequencia.insere_frequencia(vinculos[matricula], maquina, horario, online=False)

    usernames_erro = set(usernames_erro)

    if len(usernames_erro) > 0:
        MaquinaLog.objects.create(
            maquina=maquina, operacao='terminais_frequencias', status=MaquinaLog.ERRO, mensagem=f'Erros nos usuários: {",".join(usernames_erro)}'
        )
    else:
        MaquinaLog.objects.create(maquina=maquina, operacao='terminais_frequencias')

    return JsonResponse(list(usernames_erro))


@csrf_exempt
def frequencias_dia(request: HttpRequest, username: str) -> HttpResponse:
    maquina = get_maquina(request=request)

    if not maquina:
        return JsonResponse({'msg': 'Máquina não tem permissão para registro de frequências.'}, status=400)

    MaquinaLog.objects.create(maquina=maquina, operacao='terminais_frequencias_dia')

    today = datetime.today().date()

    frequencias = Frequencia.objects.filter(
        vinculo__user__username=username,
        horario__date=today,
    )

    lst_frequencias = []

    for frequencia in frequencias:
        lst_frequencias.append(
            {
                'horario': frequencia.horario.strftime('%Y-%m-%d %H:%M:%S'),
                'terminal': maquina.descricao,
            }
        )

    return JsonResponse(lst_frequencias)


@csrf_exempt
def ocorrencias(request: HttpRequest, username: str) -> HttpResponse:
    maquina = get_maquina(request=request)

    if not maquina:
        return JsonResponse({'msg': 'Máquina não tem permissão para registro de frequências.'}, status=400)

    MaquinaLog.objects.create(maquina=maquina, operacao='terminais_ocorrencias')

    experacao = Configuracao.get_valor_por_chave(app='comum', chave='biometria_expiracao')
    data_base = datetime.today() - timedelta(days=int(experacao))

    solicitacao = (
        BiometriaSolicitacao.objects.filter(
            pessoa_fisica__vinculo__user__username=username, data_cadastro__gte=data_base, utilizado=False, cancelada=False
        )
        .order_by('-id')
        .first()
    )

    if solicitacao:
        return JsonResponse(
            {
                'codigo': solicitacao.codigo_verificacao,
                'expiracao': solicitacao.data_expiracao.strftime('%Y-%m-%d %H:%M:%S'),
            }
        )

    return JsonResponse(
        {'msg': 'Nenhuma solicitacao encontrada'},
        status=400,
    )


@csrf_exempt
def solicitar_autocadastro(request: HttpRequest, username: str) -> HttpResponse:
    maquina = get_maquina(request=request)

    if not maquina:
        return JsonResponse({'msg': 'Máquina não tem permissão para solicitação de autocadastros.'}, status=400)

    MaquinaLog.objects.create(maquina=maquina, operacao='terminais_solicitar_autocadastro')

    vinculo_dono = get_object_or_404(Vinculo, user__username=username)
    pessoa_fisica = vinculo_dono.pessoa.pessoafisica

    if pessoa_fisica:
        solicitacao = BiometriaSolicitacao.objects.filter(pessoa_fisica=pessoa_fisica).order_by('-id').first()

        if not solicitacao or solicitacao.expirado:
            solicitacao = BiometriaSolicitacao()
            solicitacao.pessoa_fisica = pessoa_fisica
            solicitacao.save()

        solicitacao.enviar_email(email=vinculo_dono.email_notificacao)

        return JsonResponse({'msg': 'Sucesso.'}, status=200)

    return JsonResponse({'msg': 'Usuário não encontrado.'}, status=404)


def confirmar_autocadastro(request: HttpRequest, username: str) -> HttpResponse:
    maquina = get_maquina(request=request)

    if not maquina:
        return JsonResponse({'msg': 'Máquina não tem permissão para confirmação de autocadastros.'}, status=400)

    MaquinaLog.objects.create(maquina=maquina, operacao='terminais_confirmar_autocadastro')

    pessoa_fisica = get_object_or_404(Vinculo, user__username=username).pessoa.pessoafisica

    if pessoa_fisica:
        solicitacoes = BiometriaSolicitacao.objects.filter(pessoa_fisica=pessoa_fisica, cancelada=False).order_by('-id')

        for solicitacao in solicitacoes:
            if solicitacao.expirado:
                continue

            solicitacao.utilizado = True
            solicitacao.data_uso = datetime.now()
            solicitacao.save()

        return JsonResponse({'msg': 'Sucesso.'}, status=200)

    return JsonResponse({'msg': 'Usuário não encontrado.'}, status=404)


def cancelar_autocadastro(request: HttpRequest, username: str, code: str) -> HttpResponse:
    maquina = get_maquina(request=request)

    if not maquina:
        return JsonResponse({'msg': 'Máquina não tem permissão para cancelamento de autocadastros.'}, status=400)

    MaquinaLog.objects.create(maquina=maquina, operacao='terminais_cancelar_autocadastro')

    pessoa_fisica = get_object_or_404(Vinculo, user__username=username).pessoa.pessoafisica

    if pessoa_fisica:
        solicitacoes = BiometriaSolicitacao.objects.filter(pessoa_fisica=pessoa_fisica, codigo_verificacao=code)
        for solicitacao in solicitacoes:
            if solicitacao.ativo:
                solicitacao.cancelada = True
                solicitacao.save()

        return JsonResponse({'msg': 'Sucesso.'}, status=200)

    return JsonResponse({'msg': 'Usuário não encontrado.'}, status=404)


def whoami(request: HttpRequest) -> HttpResponse:
    maquina = get_maquina(request=request)

    if not maquina:
        return JsonResponse({'msg': 'Máquina não tem permissão para realizar a operação.'}, status=400)

    MaquinaLog.objects.create(maquina=maquina, operacao='terminais_whoami')

    return JsonResponse({'nome': maquina.descricao, 'campus': str(maquina.uo)}, status=200)
