# ruff: noqa: B008

import datetime
import hashlib
import time

from django.conf import settings
from django.http import Http404
from django.shortcuts import get_object_or_404
from ninja import Router
from ninja.params.models import Query
from oauth2_provider.decorators import protected_resource

from api.schemas.institucional import UserSchema, VinculoSchema
from api.schemas.rh import (
    CarteiraFuncionalSchema,
    ContrachequeFiltersSchema,
    ContrachequeSchema,
    DadosServidorResumidoSchema,
    EuSchema,
    FeriasSchema,
    FrequenciaSchema,
    HistoricoFuncionalSchema,
    MeuContrachequeDetalheSchema,
    MeuContrachequeSchema,
    OcorrenciaAfastamentoSchema,
    ServidorDetalhadoSchema,
    ServidorFiltersSchema,
    ServidorFuncaoAtivaSchema,
    ServidorIntegraSchema,
    ServidorSchema,
    SetorFiltersSchema,
    SetorSchema,
    UOSchema,
)
from comum.models import RegistroEmissaoDocumento, Vinculo
from comum.utils import get_setor
from contracheques.models import ContraCheque
from djtools.ninja.auth import TrustedAppAuth, permission_required
from djtools.ninja.exceptions import AccessDenied
from djtools.ninja.router import get
from djtools.templatetags.filters import format_
from djtools.utils import agrupar_em_pares, datas_entre, formata_segundos, primeiro_dia_da_semana
from ferias.models import Ferias
from ponto.models import Frequencia
from rh.deduplicacao.entrada import filtro_mesma_pessoa_por_passaporte
from rh.models import PCA, Servidor, ServidorAfastamento, ServidorFuncaoHistorico, ServidorOcorrencia, Setor, UnidadeOrganizacional

router = Router(tags=['Gestão de Pessoas'])
router.api_url_prefix = 'rh'


@get(
    router,
    'meus-dados/',
    response=UserSchema,
    summary='Obtem meu perfil pessoal',
    description='Obtém os dados pessoais do usuário logado.',
)
def obtem_meus_dados(request):
    """
    Obtém os dados pessoais do usuário logado.

    Args:
        request: Objeto de requisição HTTP.

    Returns:
        UserSchema: Dados pessoais do usuário.
    """
    return request.user


@get(
    router,
    'meus-vinculos/',
    response=list[VinculoSchema],
    summary='Vínculos do usuário',
    description='Obtém os vínculos do usuário autenticado.',
)
def meus_vinculos(request):
    pessoa_fisica = request.user.get_profile()
    if pessoa_fisica:
        if pessoa_fisica.cpf:
            return Vinculo.objects.filter(pessoa__pessoafisica__cpf=pessoa_fisica.cpf)
        elif pessoa_fisica.passaporte:
            # pelo par passaporte+país: o mesmo número de outro país é outra pessoa
            return Vinculo.objects.filter(filtro_mesma_pessoa_por_passaporte(pessoa_fisica, 'pessoa__pessoafisica__'))
    return Vinculo.objects.filter(user=request.user)


@get(
    router,
    'eu/',
    response=EuSchema,
    summary='Obtém meus dados pessoais',
    description='Obtém os dados pessoais do usuário logado',
)
def eu(request):
    """
    Obtém os dados pessoais do usuário logado.

    Args:
        request: Objeto de requisição HTTP.

    Returns:
        dict: Dicionário contendo os dados pessoais do usuário.
    """
    user = request.user
    relacionamento = user.get_relacionamento()
    if not relacionamento:
        return 401, {'message': 'Usuário não possui relacionamento com a instituição.'}
    if not hasattr(relacionamento, '_prefetched_objects_cache') and hasattr(relacionamento, 'pessoa_fisica'):
        relacionamento = type(relacionamento).objects.select_related('pessoa_fisica').get(pk=relacionamento.pk)

    pessoa_fisica = relacionamento.pessoa_fisica if relacionamento else None

    # foto migrou de PessoaFisica para Vinculo; relacionamento (papel) já tem get_foto_75x100_url_publica()
    # via AbstractRelacionamento (Servidor/Prestador) ou Aluno; PessoaJuridica retorna default
    foto = None
    if relacionamento and getattr(relacionamento, 'foto', None):
        foto = relacionamento.get_foto_75x100_url_publica()

    campus = str(relacionamento.campus) if relacionamento.campus else ''

    nome_social = getattr(pessoa_fisica, 'nome_social', '')
    nome_usual = getattr(pessoa_fisica, 'nome_usual', '')
    nome_registro = getattr(pessoa_fisica, 'nome_registro', '')
    # email migrou de Pessoa para Vinculo; lê do relacionamento (papel): email_pessoal ~ E-mail Principal,
    # email_notificacao ~ E-mail Secundário. PessoaJuridica/sem property retorna default via getattr.
    email_principal = getattr(relacionamento, 'email_institucional', '')
    email_secundario = getattr(relacionamento, 'email_pessoal', '')
    cpf = getattr(pessoa_fisica, 'cpf', '')
    passaporte = getattr(pessoa_fisica, 'passaporte', '') or ''
    data_nascimento = getattr(pessoa_fisica, 'nascimento_data', None)
    sexo = getattr(pessoa_fisica, 'sexo', '')

    email_classroom = getattr(relacionamento, 'email_google_classroom', '')
    email_academico = getattr(relacionamento, 'email_academico', '')

    email_preferencial = email_principal or email_secundario or user.email or email_academico or email_classroom

    data = {
        'identificacao': user.username or '',
        'nome_social': nome_social,
        'nome_usual': nome_usual,
        'nome_registro': nome_registro,
        'nome': user.get_full_name() or '',
        'primeiro_nome': user.first_name or '',
        'ultimo_nome': user.last_name or '',
        'email': email_principal,
        'email_secundario': email_secundario,
        'email_google_classroom': email_classroom,
        'email_academico': email_academico,
        'campus': campus,
        'foto': foto or '',
        'tipo_usuario': user.get_tipo(),
        'cpf': cpf,
        'passaporte': passaporte,
        'data_de_nascimento': data_nascimento,
        'sexo': sexo,
        'email_preferencial': email_preferencial,
    }
    return data


@get(
    router,
    'unidades-organizacionais/',
    response=list[UOSchema],
    summary='Obtem campi',
    description='Obtem os campus da instituição',
)
def uos(request):
    """
    Obtém os campus da instituição.

    Args:
        request: Objeto de requisição HTTP.

    Returns:
        list: Lista de objetos de unidades organizacionais.
    """
    return UnidadeOrganizacional.objects.suap().all()


@get(
    router,
    'servidores/',
    response=list[ServidorSchema],
    summary='Obtem servidores',
    description='Obtem os servidores ativos da instituição',
)
def servidores(request, filters: ServidorFiltersSchema = Query(...)):
    """
    Obtém os servidores ativos da instituição.

    Args:
        request: Objeto de requisição HTTP.
        filters: Filtros para a consulta de servidores.

    Returns:
        list: Lista de objetos de servidores.
    """
    qs = Servidor.objects.ativos().order_by('pessoa_fisica__nome')
    qs = filters.filter(qs)
    return qs


@get(
    router,
    'servidores_funcao_ativa/',
    response=list[ServidorFuncaoAtivaSchema],
    summary='Obtem servidores com função ativa',
    description='Obtem os servidores com função ativa da instituição',
)
def servidores_funcao_ativa(request, filters: ServidorFiltersSchema = Query(...)):
    """
    Obtém os servidores com função ativa da instituição.

    Args:
        request: Objeto de requisição HTTP.
        filters: Filtros para a consulta de servidores.

    Returns:
        list: Lista de objetos de servidores com função ativa.
    """
    ids = ServidorFuncaoHistorico.objects.atuais().values_list('servidor_id', flat=True)
    qs = Servidor.objects.ativos().filter(id__in=ids)
    qs = qs.select_related(
        'pessoa_fisica',
        'setor',
        'setor__uo',
        'setor_exercicio',
        'setor_exercicio__uo',
    )
    qs = qs.order_by('pessoa_fisica__nome')
    qs = filters.filter(qs)
    return qs


@get(
    router,
    'servidores/detalhado/',
    response=list[ServidorDetalhadoSchema],
    auth=TrustedAppAuth(),
    summary='Obtem dados detalhados de servidores',
    description='Obtem dados detalhados de todos os servidores da instituição',
)
def servidores_detalhado(request, filters: ServidorFiltersSchema = Query(...)):
    """
    Obtém dados detalhados de todos os servidores da instituição.

    Args:
        request: Objeto de requisição HTTP.
        filters: Filtros para a consulta de servidores.

    Returns:
        list: Lista de objetos de servidores detalhados.
    """
    qs = (
        Servidor.objects.all()
        .order_by('pessoa_fisica__nome')
        .select_related('pessoa_fisica', 'cargo_emprego', 'cargo_emprego__grupo_cargo_emprego', 'setor', 'setor__uo', 'situacao')
        .prefetch_related(
            'pessoa_fisica__pessoaendereco_set',
            'pessoa_fisica__pessoatelefone_set',
        )
    )
    qs = filters.filter(qs)
    return qs


@get(
    router,
    'servidores/integra/',
    response=list[ServidorIntegraSchema],
    auth=TrustedAppAuth(),
    ignore_paginate=True,
    summary='Obtem dados de servidores com escopo do integra',
    description='Obtem dados de servidores com escopo do integra',
)
@protected_resource(scopes=['integra'])
def servidores_integra(request):
    """
    Obtém dados de servidores com escopo do integra.

    Args:
        request: Objeto de requisição HTTP.

    Returns:
        list: Lista de objetos de servidores com escopo do integra.
    """
    return Servidor.objects.ativos_permanentes().select_related('pessoa_fisica', 'cargo_emprego__grupo_cargo_emprego', 'setor__uo', 'situacao')


@get(
    router,
    'setores/',
    response=list[SetorSchema],
    summary='Obtem setores',
    description='Obtem os setores da instituição',
)
def setores(request, filters: SetorFiltersSchema = Query(...)):
    """
    Obtém os setores da instituição.

    Args:
        request: Objeto de requisição HTTP.
        filters: Filtros para a consulta de setores.

    Returns:
        list: Lista de objetos de setores.
    """
    qs = Setor.objects.suap_ativos().all()
    qs = filters.filter(qs)
    qs = qs.select_related('uo').prefetch_related('setortelefone_set')
    return qs


@get(
    router,
    'meu-historico-funcional/',
    response=list[HistoricoFuncionalSchema],
    summary='Obtem meu histórico Funcional',
    description='Obtém a timeline do Histórico Funcional do Servidor logado.',
)
def obtem_historico_funcional(request):
    """
    Obtém a timeline do Histórico Funcional do Servidor logado.

    Args:
        request: Objeto de requisição HTTP.

    Returns:
        list: Lista de objetos de histórico funcional.
    """
    obj = get_object_or_404(Servidor, matricula=request.user.username)
    timeline = PCA.montar_timeline(obj.pca_set.all().order_by('data_entrada_pca'))
    servidor_tempo_servico_na_instituicao_via_pca = obj.tempo_servico_na_instituicao_via_pca()
    servidor_tempo_servico_na_instituicao_via_pca_ficto = obj.tempo_servico_na_instituicao_via_pca(ficto=True)
    lista = []

    # Tratamento necessário para converter o retorno da timeline de dict para lista.
    for k, v in list(timeline.items()):
        v.update({'data': str(k)})
        lista.append(v)

    lista.append(
        {
            'css': 'default',
            'data': str(obj.data_fim_servico_na_instituicao) if obj.data_fim_servico_na_instituicao else 'Hoje',
            'eventos': [
                {
                    'descricao': f"""<h4>Tempo de Serviço</h4>
                <dl>
                    <dt>Tempo Real:</dt>
                    <dd>{format_(servidor_tempo_servico_na_instituicao_via_pca)}</dd>
                    <dt>Tempo Ficto:</dt>
                    <dd>{format_(servidor_tempo_servico_na_instituicao_via_pca_ficto)}</dd>
                </dl>
            """,
                    'css': 'default',
                }
            ],
        }
    )

    return lista


@get(
    router,
    'minhas-ocorrencias-afastamentos/',
    response=OcorrenciaAfastamentoSchema,
    summary='Obtem meus afastamentos',
    description='Obtém a lista de ocorrências e afastamentos do Servidor logado.',
)
def obtem_ocorrencias_afastamentos_servidor(request):
    """
    Obtém a lista de ocorrências e afastamentos do Servidor logado.

    Args:
        request: Objeto de requisição HTTP.

    Returns:
        dict: Dicionário contendo as ocorrências e afastamentos.
    """
    obj = get_object_or_404(Servidor, matricula=request.user.username)

    servidor_ocorrencias = ServidorOcorrencia.objects.filter(servidor=obj).exclude(ocorrencia__grupo_ocorrencia__nome='AFASTAMENTO').order_by('data')
    servidor_afastamentos = ServidorAfastamento.objects.filter(servidor=obj, cancelado=False).order_by('data_inicio')

    dict_response = {'ocorrencias': servidor_ocorrencias, 'afastamentos': servidor_afastamentos}
    return dict_response


@get(
    router,
    'emitir-carteira-funcional-digital/{matricula}/',
    response=CarteiraFuncionalSchema,
    summary='Obtem carteira funcional digital',
    description='Obtém a carteira funcional de um determinado servidor',
)
def emitir_carteira_funcional_digital(request, matricula: str):
    """
    Obtém a carteira funcional de um determinado servidor.

    Args:
        request: Objeto de requisição HTTP.
        matricula (str): Matrícula do servidor.

    Returns:
        dict: Dicionário contendo os dados da carteira funcional.
    """
    if request.user.username != matricula and not request.user.has_perm('rh.pode_gerar_carteira'):
        return 403, {'message': 'Você não pode emitir carteira funcional.'}

    obj = get_object_or_404(Servidor.objects.ativos(), matricula=matricula)
    qs = RegistroEmissaoDocumento.objects.filter(tipo='Carteira Funcional Digital', modelo_pk=obj.pk, data_validade__gte=datetime.datetime.today())

    if not qs.exists():
        # Criando o Registro de Emissão da Carteira Funcional Digital
        registro_emissao = RegistroEmissaoDocumento()
        registro_emissao.tipo = 'Carteira Funcional Digital'
        registro_emissao.data_emissao = datetime.datetime.today()
        registro_emissao.codigo_verificador = hashlib.sha1(
            f'{obj.matricula}{registro_emissao.data_emissao}{settings.SECRET_KEY}'.encode()
        ).hexdigest()
        registro_emissao.data_validade = datetime.datetime.today() + datetime.timedelta(days=1)
        registro_emissao.modelo_pk = obj.pk
        registro_emissao.save()
    else:
        registro_emissao = qs[0]
    return {
        'codigo_verificador': registro_emissao.codigo_verificador,
        'data_emissao': registro_emissao.data_emissao,
        'data_validade': registro_emissao.data_validade,
    }


@get(
    router,
    'minhas-ferias/',
    response=list[FeriasSchema],
    summary='Obtem minhas férias',
    description='Obtém a lista das férias do usuário logado.',
)
def obtem_ferias(request):
    """
    Obtém a lista das férias do usuário logado.

    Args:
        request: Objeto de requisição HTTP.

    Returns:
        list: Lista de objetos de férias.
    """
    obj = get_object_or_404(Servidor, matricula=request.user.username)
    return Ferias.objects.filter(servidor=obj).order_by('ano')


@get(
    router,
    'minhas-frequencias/',
    response=FrequenciaSchema,
    summary='Obtem minhas frequências do dia',
    description='Obtém a lista das frequências no dia de hoje do usuário logado.',
)
def obtem_frequencias(request):
    """
    Obtém as frequências do dia de hoje do usuário logado.

    Args:
        request: Objeto de requisição HTTP.

    Returns:
        dict: Dicionário contendo as frequências de hoje, o tempo total de hoje e o tempo total da semana.

    Raises:
        Http404: Se nenhuma frequência for encontrada.
    """
    # Obtém o objeto Servidor com base na matrícula do usuário logado
    get_object_or_404(Servidor, matricula=request.user.username)
    vinculo = request.user.get_vinculo()
    setor = get_setor(request.user)

    if (vinculo.eh_servidor() or vinculo.eh_prestador()) and setor:
        hoje = datetime.datetime.now()
        total_tempo_semana = 0
        total_tempo_hoje = '0'
        frequencias_hoje = Frequencia.objects.none()
        dict_response = {}

        # Itera sobre os dias da semana até a data de hoje
        for dia in datas_entre(primeiro_dia_da_semana(hoje), hoje):
            frequencias_dia = Frequencia.get_frequencias_por_data(vinculo, dia)
            if dia == hoje:
                frequencias_hoje = frequencias_dia
                if frequencias_hoje.exists():
                    tempo = 0
                    # Agrupa as frequências em pares e calcula o tempo total
                    for par in agrupar_em_pares(frequencias_hoje.values_list('horario', flat=True)):
                        if len(par) == 2:
                            delta = par[1] - par[0]
                            segundos = delta.seconds
                        else:
                            segundos = 0
                        tempo += segundos
                    # Verifica se a última ação foi uma entrada e calcula o tempo desde a última entrada
                    if frequencias_hoje.latest('horario').acao == 'E':
                        momento_da_entrada = frequencias_hoje.latest('horario').horario
                        momento_agora = datetime.datetime.now()
                        if momento_agora < momento_da_entrada:
                            momento_agora = datetime.datetime.now()
                        delta = momento_agora - momento_da_entrada
                        segundos = delta.seconds
                        tempo += segundos
                    total_tempo_hoje = time.strftime('%H:%M:%S', time.gmtime(tempo))
                    total_tempo_semana += tempo
            else:
                total_tempo_semana += Frequencia.get_tempo_entre_frequencias(frequencias_dia)

        dict_response['frequencias_hoje'] = frequencias_hoje
        dict_response['total_tempo_hoje'] = total_tempo_hoje
        dict_response['total_tempo_semana'] = '{h}h {m}min {s}seg'.format(**formata_segundos(total_tempo_semana))
        return dict_response
    else:
        raise Http404('Nenhuma frequência encontrada')


@get(
    router,
    'servidor-resumido/',
    response=DadosServidorResumidoSchema,
    summary='Obtém dados resumidos de servidor especifico.',
    description='Obtém dados resumidos de servidor especifico.',
)
@permission_required('edu.pode_sincronizar_dados')
def dados_servidor(request, matricula: str | None = None):
    matricula = matricula or request.user.username
    servidor = Servidor.objects.filter(matricula=matricula).first()
    if not servidor:
        return 404, {'message': f'Servidor não encontrado com a matrícula {matricula}'}
    return {
        'matricula': servidor.matricula,
        'nome': servidor.pessoa_fisica.nome,
        'campus': servidor.setor.uo.sigla,
        'email': servidor.email_institucional,
        'foto': servidor.get_foto_150x200_url_publica(),
    }


@get(
    router,
    'meus-contracheques/',
    response=list[MeuContrachequeSchema],
    summary='Obtém meus contracheques',
    description='Obtém a lista dos meses com contracheques disponíveis para o usuário logado.',
)
def meus_contracheques(request):
    """
    Obtém a lista dos meses com contracheques disponíveis para o usuário logado.

    Args:
        request: Objeto de requisição HTTP.

    Returns:
        list: Lista de objetos de contracheques.
    """
    obj = get_object_or_404(Servidor, matricula=request.user.username)
    return ContraCheque.objects.ativos().fita_espelho().filter(servidor=obj).order_by('-ano__ano', '-mes').select_related('ano')


@get(
    router,
    'meu-contracheque/{ano}/{mes}/',
    response=MeuContrachequeDetalheSchema,
    summary='Obtém meu contracheque detalhado',
    description='Obtém o detalhamento de um determinado contracheque do usuário logado.',
)
def obtem_detalhes_contracheque(request, ano: int, mes: int):
    """
    Obtém o detalhamento de um determinado contracheque do usuário logado.

    Args:
        request: Objeto de requisição HTTP.
        ano (int): Ano do contracheque.
        mes (int): Mês do contracheque.

    Returns:
        MeuContrachequeDetalheSchema: Detalhamento do contracheque.
    """
    obj = get_object_or_404(Servidor, matricula=request.user.username)
    contracheque = get_object_or_404(
        ContraCheque, servidor=obj, ano__ano=ano, mes=mes, excluido=False, tipo_importacao=ContraCheque.IMPORTACAO_FITA_ESPELHO
    )

    if contracheque.pode_ver(request):
        return contracheque
    else:
        return Http404('Você não tem permissão para visualizar este contracheque.')


@get(
    router,
    'contracheques/',
    response=list[ContrachequeSchema],
    summary='Obtém todos os contracheques',
    description='Obtém a lista dos meses com contracheques disponíveis para o usuário logado.',
)
def obtem_contracheques(request, filters: ContrachequeFiltersSchema = Query(...)):
    """
    Obtém todos os contracheques disponíveis para o usuário logado.

    Args:
        request: Objeto de requisição HTTP.

    Returns:
        list: Lista de objetos Contracheque.
    """
    if not request.user.has_perm('contracheques.pode_ver_contracheques_detalhados'):
        raise AccessDenied('Você não tem permissão para visualizar contracheques detalhados.')

    qs = (
        ContraCheque.objects.ativos()
        .fita_espelho()
        .filter(
            pensionista__isnull=True,
        )
        .prefetch_related(
            'contrachequerubrica_set',
            'contrachequerubrica_set__tipo',
            'contrachequerubrica_set__rubrica',
            'servidor__pessoa_fisica__pessoaendereco_set',
            'servidor__pessoa_fisica__pessoatelefone_set',
            'servidor__pessoa_fisica__pessoaendereco_set__municipio',
        )
        .select_related(
            'servidor',
            'servidor__pessoa_fisica',
            'servidor__cargo_emprego',
            'servidor__cargo_emprego__grupo_cargo_emprego',
            'servidor__setor__uo',
            'servidor__situacao',
            'servidor__pessoa_fisica__pagto_banco',
            'ano',
        )
    )
    qs = filters.filter(qs)
    return qs
