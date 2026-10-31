import logging
import os
from datetime import date, datetime, timedelta

import feedparser
from django.apps import apps
from django.conf import settings
from django.contrib.admin.models import LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.core.files.storage import default_storage
from django.db.models import Count, Q

from djtools.signals import minhas_acoes
from djtools.storages import cache_file
from djtools.utils import get_remote_session, tl

# Configuração do logger para este módulo
logger = logging.getLogger(__name__)

FLAG_LOG_GERENCIAMENTO_GRUPO = 99


def registrar_remocao_grupo(sender, **kwargs):
    """Método chamado sempre que um usuário é removido de 'UsuarioGrupo'"""
    registrar_historico_grupo('Removido(a) do grupo', sender, **kwargs)


def registrar_adicao_grupo(sender, **kwargs):
    """Método chamado sempre que um usuário é adicionado em 'UsuarioGrupo'"""
    if kwargs['created']:
        registrar_historico_grupo('Adicionado(a) ao grupo', sender, **kwargs)


def registrar_historico_grupo(acao, sender, **kwargs):
    usuario_grupo = kwargs['instance']
    usuario = usuario_grupo.user
    grupo = usuario_grupo.group
    if all([usuario, grupo]):
        registrar_log_entry(usuario, grupo, acao)


def historico_usuario_grupo_existente(user, group, action):
    """Função que verifica se houve uma inserção ou atualização na classe InclusaoUsuarioGrupo"""
    from comum.models import HistoricoUsuarioGrupo

    qs = HistoricoUsuarioGrupo.objects.filter(usuario=user, grupo_id=group)
    if action == 'post_add':
        qs = qs.filter(operacao='I').order_by('-incluido_em')
    elif action == 'pre_remove':
        qs = qs.filter(operacao='R').order_by('-incluido_em')

    if qs.exists():
        obj = qs.first()
        return obj.is_operacao_automatica, obj.motivo
    else:
        return False, None


def registrar_inclusao_remocao_grupo(sender, **kwargs):
    from django.contrib.auth.models import Group

    from comum.models import User

    action = kwargs['action']
    instance = kwargs['instance']
    pks = kwargs['pk_set'] or []

    usuarios = []
    grupos = []

    # Identifica se o relacionamento é pelo lado do User ou do Group
    if isinstance(instance, User):
        usuarios = [instance]
        grupos = Group.objects.filter(pk__in=pks)
    elif isinstance(instance, Group):
        grupos = [instance]
        usuarios = User.objects.filter(pk__in=pks)
    else:
        return  # Tipo inesperado, ignora a execução

    if action in ('pre_clear', 'pre_remove', 'post_add'):
        acao = 'Adicionado(a) ao grupo' if action == 'post_add' else 'Removido(a) do grupo'

        for usuario in usuarios:
            if action == 'pre_remove':
                if not sender.objects.filter(user_id=usuario.id, group_id__in=[g.id for g in grupos]).exists():
                    continue
            elif action == 'pre_clear':
                grupos = Group.objects.filter(user=usuario)

            cache.delete(f'{usuario.id}_groups')

            for grupo in grupos:
                try:
                    automatico, mensagem = historico_usuario_grupo_existente(usuario, grupo, action)
                    mensagem_personalizada = None

                    if automatico:
                        mensagem_personalizada = f'Automaticamente {acao.lower()} {grupo}. {mensagem}'
                    elif mensagem:
                        mensagem_personalizada = mensagem

                    registrar_log_entry(usuario, grupo, acao, mensagem_personalizada)
                except Exception as e:
                    logger.error(f'Erro ao registrar log de inclusão/remocao de grupo: {e}')


def registrar_log_entry(usuario, grupo, acao, mensagem_personalizada=None):
    from comum.models import User

    usuario_logado = tl.get_user()
    usuario_logado = usuario_logado if usuario_logado and usuario_logado.pk and User.objects.filter(pk=usuario_logado.pk).exists() else usuario
    entry = LogEntry()
    entry.user = usuario_logado
    entry.object_id = usuario.id
    entry.content_type = ContentType.objects.get_for_model(type(usuario))
    entry.object_repr = str(usuario)
    entry.action_flag = FLAG_LOG_GERENCIAMENTO_GRUPO
    if mensagem_personalizada:
        entry.change_message = mensagem_personalizada
    else:
        entry.change_message = f'{acao} {grupo}'
    entry.save()


def get_setor(user=None):
    user = user or tl.get_user()
    try:
        return user.get_relacionamento().setor
    except Exception:
        pass
    try:
        return user.get_relacionamento().curso_campus.diretoria.setor
    except Exception:
        return None


def get_uo(user=None):
    from comum.models import User

    user = user or tl.get_user()
    if getattr(user, 'is_anonymous', False):
        return None
    if user and not isinstance(user, User):
        raise ValueError('Um usuário válido não foi informado. Não é possível saber a unidade organizacional (uo).')
    try:
        return user.get_relacionamento().setor.uo
    except Exception:
        pass
    try:
        return user.get_relacionamento().curso_campus.diretoria.setor.uo
    except Exception:
        pass
    return None


def get_cargo_emprego(user=None):
    user = user or tl.get_user()
    try:
        return user.get_relacionamento().cargo_emprego
    except Exception:
        return None


def get_sigla_reitoria():
    from comum.models import Configuracao

    return Configuracao.get_valor_por_chave('comum', 'reitoria_sigla') or 'RE'


def get_setor_siape(user=None):
    """Retorna o setor de exercício SIAPE"""
    user = user or tl.get_user()
    try:
        return user.get_relacionamento().setor_exercicio
    except Exception:
        return None


def get_uo_siape(user=None):
    """Retorna a UO do setor de exercício SIAPE"""
    user = user or tl.get_user()
    setor_siape = get_setor_siape(user)
    try:
        return setor_siape.uo
    except Exception:
        return None


def get_todos_setores(user=None, setores_compartilhados=True):
    # TODO: Isso não deveria ser um método da classe Funcionario?
    """
    Setores em 3 situações serão incluídos neste retorno:
     - Setor de lotação (FK setor do funcionario)
     - Setores adicionais da pessoa (``setores_adicionais``)
     - Setores compartilhados do Setor (``setores_compartilhados``)
    """
    user = user or tl.get_user()
    Setor = apps.get_model('rh', 'Setor')
    ids_setores = []
    vinculo = user.get_vinculo()
    if vinculo:
        ids_setores = list(vinculo.setores_adicionais.values_list('id', flat=True))

    setor_origem = None
    try:
        setor_origem = get_setor(user)
    except Exception:
        pass
    if setor_origem:
        ids_setores.append(setor_origem.id)
        if setores_compartilhados:
            ids_setores += list(setor_origem.setores_compartilhados.values_list('id', flat=True))

    relacionamento = user.get_relacionamento()
    if relacionamento is not None and hasattr(relacionamento, 'papeis_ativos'):
        ids_setores += list(relacionamento.papeis_ativos.values_list('setor_suap', flat=True))
    return Setor.objects.suap_ativos().filter(id__in=ids_setores)


def get_setor_cppd():
    #   PK do CPPD
    from rh.models import Setor

    return Setor.objects.suap_ativos().get(pk=709)


def get_ids_meus_setores_hoje(user=None):
    ids_setores = [get_setor(user).pk]
    Funcao = apps.get_model('rh', 'Funcao')
    if user.eh_servidor:
        ids_setores += (
            user.get_relacionamento()
            .historico_funcao(date.today(), date.today())
            .filter(funcao__codigo__in=Funcao.get_codigos_funcao_chefia())
            .values_list('setor_suap_id', flat=True)
        )
    return ids_setores


def get_meus_setores_hoje(user=None):
    Setor = apps.get_model('rh', 'Setor')
    ids = get_ids_meus_setores_hoje(user)
    if not ids:
        setores = Setor.objects.suap_ativos().none()
    else:
        setores = Setor.objects.suap_ativos().filter(id__in=ids)
    return setores


def get_setores_que_sou_chefe_hoje(user=None):
    Setor = apps.get_model('rh', 'Setor')
    Funcao = apps.get_model('rh', 'Funcao')
    user = user or tl.get_user()
    if user.is_anonymous or not user.eh_servidor:
        return Setor.objects.suap_ativos().none()

    relacionamento = user.get_relacionamento()
    hoje = date.today()
    chave = f'servidor_{relacionamento.pk}_setores_que_eh_chefe_{hoje.strftime("%d/%m/%Y")}'
    setores = cache.get(f'{chave}')
    if not setores:
        setores = cache.get_or_set(
            f'{chave}',
            Setor.objects.suap_ativos().filter(
                id__in=relacionamento.historico_funcao(hoje, hoje)
                .filter(funcao__codigo__in=Funcao.get_codigos_funcao_chefia())
                .values_list('setor_suap_id', flat=True)
            ),
            86400,
        )
    return setores


def get_todos_campi(user=None):
    # TODO: Isso não deveria ser um método da classe Funcionario?
    UnidadeOrganizacional = apps.get_model('rh', 'UnidadeOrganizacional')
    todos_setores = get_todos_setores(user)
    return UnidadeOrganizacional.objects.suap().filter(id__in=todos_setores.values_list('uo', flat=True))


def get_logo_instituicao_file_path():
    from comum.models import Configuracao

    logo_nome_arquivo = Configuracao.get_valor_por_chave('comum', 'logo_instituicao')
    if not logo_nome_arquivo:
        return os.path.join(settings.BASE_DIR, 'comum/static/comum/img/logo.jpg')
    try:
        return cache_file(logo_nome_arquivo)
    except Exception:
        return ''


def get_logo_instituicao_fundo_transparente_file_path():
    from comum.models import Configuracao

    logo_nome_arquivo = Configuracao.get_valor_por_chave('comum', 'logo_instituicao_fundo_transparente')
    if not logo_nome_arquivo:
        return os.path.join(settings.BASE_DIR, 'comum/static/comum/img/logo_capa.png')
    try:
        return cache_file(logo_nome_arquivo)
    except Exception:
        return ''


def get_logo_instituicao_url():
    from comum.models import Configuracao

    logo_nome_arquivo = Configuracao.get_valor_por_chave('comum', 'logo_instituicao')
    if logo_nome_arquivo:
        return default_storage.url(logo_nome_arquivo)
    return '/static/comum/img/logo.jpg'


def get_logo_instituicao_fundo_transparente_url():
    from comum.models import Configuracao

    logo_nome_arquivo = Configuracao.get_valor_por_chave('comum', 'logo_instituicao_fundo_transparente')
    if logo_nome_arquivo:
        return default_storage.url(logo_nome_arquivo)
    return '/static/comum/img/logo_capa.png'


def get_setor_propi():
    from comum.models import Configuracao
    from rh.models import Setor

    if Configuracao.get_valor_por_chave('pesquisa', 'setor_propi'):
        return Setor.objects.suap_ativos().get(pk=Configuracao.get_valor_por_chave('pesquisa', 'setor_propi'))
    return Setor.objects.suap_ativos().get(pk=729)


def get_setor_rh():
    from comum.models import Configuracao
    from rh.models import Setor

    return Setor.objects.suap_ativos().filter(pk=Configuracao.get_valor_por_chave('rh', 'setor_rh') or 0).first()


def get_setor_procuradoria():
    from comum.models import Configuracao
    from rh.models import Setor

    return Setor.objects.suap_ativos().filter(pk=Configuracao.get_valor_por_chave('rh', 'setor_procuradoria')).first()


def get_setor_auditoria_geral():
    from comum.models import Configuracao
    from rh.models import Setor

    return Setor.objects.suap_ativos().filter(pk=Configuracao.get_valor_por_chave('rh', 'setor_auditoria_geral')).first()


def get_setor_proex():
    from comum.models import Configuracao
    from rh.models import Setor

    if Configuracao.get_valor_por_chave('projetos', 'setor_proex'):
        return Setor.objects.suap_ativos().get(pk=Configuracao.get_valor_por_chave('projetos', 'setor_proex'))
    return Setor.objects.suap_ativos().get(pk=726)


def get_setor_proen():
    from comum.models import Configuracao
    from rh.models import Setor

    ID_PROEN_IFRN = 721
    id_proen = Configuracao.get_valor_por_chave('edu', 'setor_proreitor_ensino') or ID_PROEN_IFRN
    return Setor.objects.suap_ativos().get(pk=id_proen)


def tem_permissao_informar_erro(request):
    return all(['erros' in settings.INSTALLED_APPS, hasattr(request, 'build_absolute_uri'), request.user.is_authenticated])


def ferramentas_configuradas():
    import gitlab

    from comum.models import Configuracao

    sentry_token = Configuracao.get_valor_por_chave('comum', 'sentry_token')
    sentry_url = Configuracao.get_valor_por_chave('comum', 'sentry_url')
    gitlab_url = Configuracao.get_valor_por_chave('demandas', 'gitlab_url')
    gitlab_token = Configuracao.get_valor_por_chave('demandas', 'gitlab_token')
    gitlab_suap_id = Configuracao.get_valor_por_chave('demandas', 'gitlab_suap_id')
    if not all([sentry_token, sentry_url, gitlab_url, gitlab_token, gitlab_suap_id]):
        return None

    git = gitlab.Gitlab(gitlab_url, private_token=gitlab_token, timeout=60)
    sentry_headers = {'Authorization': f'Bearer {sentry_token}'}

    git_label_todo = Configuracao.get_valor_por_chave('erros', 'label_todo_erros_suap')
    git_label_doing = Configuracao.get_valor_por_chave('erros', 'label_doing_erros_suap')
    git_label_done = Configuracao.get_valor_por_chave('erros', 'label_done_erros_suap')
    git_label_feedback = Configuracao.get_valor_por_chave('erros', 'label_feedback_erros_suap')
    git_id_milestone_erros = Configuracao.get_valor_por_chave('erros', 'milestone_erros_suap_id')

    return {
        'sentry_url': sentry_url,
        'sentry_headers': sentry_headers,
        'gitlab_suap_id': gitlab_suap_id,
        'git': git,
        'git_label_todo': git_label_todo,
        'git_label_doing': git_label_doing,
        'git_label_done': git_label_done,
        'git_label_feedback': git_label_feedback,
        'git_id_milestone_erros': git_id_milestone_erros,
    }


def remote_logout_user(username):
    """
    Realiza o logout remoto de um usuário.

    :param username: o username do usuário que será deslogado.
    :type username: :class:`str`
    """
    from comum.models import SessionInfo, User

    user = User.objects.filter(username=username).first()
    if user:
        qs = SessionInfo.objects.filter(device__user=user, expired=False)
        for session_info in qs:
            try:
                get_remote_session(session_info.session_id).delete()
                session_info.expired = True
                session_info.save()
            except Exception:
                continue


def get_rss_links(url_file_stream_or_string):
    """
    Com base na **URL** passada, faz a leitura e retorna conteúdos *RSS*.

    Args:
        url_file_stream_or_string (string): *URL* do serviço de *RSS*.

    Returns:
        Lista contendo o conteúdo *RSS*.
    """

    feed = feedparser.parse(url_file_stream_or_string, timeout=4)
    rss_links = []
    for entry in feed['entries'][: min(5, len(feed['entries']))]:
        entry['updated'] = entry['updated'][0:19]
        entry['updated'] = entry['updated'] + 'Z'
        title = entry['title']
        try:
            updated = datetime.strptime(entry['updated'], '%Y-%m-%dT%H:%M:%SZ')
        except ValueError:
            updated = datetime.strptime(entry['published'], '%a, %d %b %Y %H:%M:%S %Z') - timedelta(hours=3)

        rss_links.append({'title': title, 'url': str(entry['links'][0]['href']), 'updated': updated})
    return rss_links


def get_temas():
    from comum.models import Preferencia

    preferencias = Preferencia.objects.filter(usuario__is_active=True).aggregate(
        tema_padrao=Count('pk', filter=Q(tema=Preferencia.PADRAO)),
        tema_dunas=Count('pk', filter=Q(tema=Preferencia.DUNAS)),
        tema_aurora=Count('pk', filter=Q(tema=Preferencia.AURORA)),
        tema_luna=Count('pk', filter=Q(tema=Preferencia.LUNA)),
        tema_govbr=Count('pk', filter=Q(tema=Preferencia.GOVBR)),
        tema_alto_contraste=Count('pk', filter=Q(tema=Preferencia.ALTO_CONSTRASTE)),
        tema_ifs=Count('pk', filter=Q(tema=Preferencia.IFS)),
        tema_modo_daltonismo=Count('pk', filter=Q(tema=Preferencia.MODO_DALTONISMO)),
    )

    tema_padrao = preferencias['tema_padrao']
    tema_dunas = preferencias['tema_dunas']
    tema_aurora = preferencias['tema_aurora']
    tema_luna = preferencias['tema_luna']
    tema_govbr = preferencias['tema_govbr']
    tema_alto_contraste = preferencias['tema_alto_contraste']
    tema_ifs = preferencias['tema_ifs']
    tema_modo_daltonismo = preferencias['tema_modo_daltonismo']

    def get_tema(tipo, descricao, qtd, *args, **kwargs):
        return {
            'slug': tipo,
            'nome': Preferencia.get_tema_description(tipo),
            'descricao': descricao,
            'qtd': qtd,
        }

    temas_gerais_dict = [
        {
            'tipo': Preferencia.AURORA,
            'descricao': 'Inspirado na suavidade das luzes do amanhecer, o tema Aurora transmite leveza, equilíbrio e tranquilidade com tons de roxo em degradê, oferecendo uma experiência visual moderna e acolhedora.',
            'qtd': tema_aurora,
        },
        {
            'tipo': Preferencia.DUNAS,
            'descricao': 'Cores harmônicas e delimitações compostas pelo uso predominante de branco, cinza e areia do deserto.',
            'qtd': tema_dunas,
        },
        {
            'tipo': Preferencia.LUNA,
            'descricao': 'Opção de tema noturno, visando o conforto da visão de quem prefere tons mais escuros.',
            'qtd': tema_luna,
        },
        {
            'tipo': Preferencia.PADRAO,
            'descricao': 'Personalizado com as cores da identidade visual do Suap.',
            'qtd': tema_padrao,
        },
    ]

    temas_gov_dict = [
        {
            'tipo': Preferencia.GOVBR,
            'descricao': 'Composto pela identidade visual do GovBr.',
            'qtd': tema_govbr,
        },
        {
            'tipo': Preferencia.IFS,
            'descricao': 'Desenvolvido com base na identidade visual dos Institutos Federais de Educação, incorporando suas cores e elementos gráficos característicos, garantindo a integração visual entre o Suap e a instituição de ensino.',
            'qtd': tema_ifs,
        },
    ]

    temas_acessibilidade_dict = [
        {
            'tipo': Preferencia.ALTO_CONSTRASTE,
            'descricao': 'Trata-se de um recurso destinado às pessoas com deficiência visual ou, especificamente, baixa visão. Conta com cores contrastadas para que textos, títulos, links e informações se tornem perceptíveis facilmente.',
            'qtd': tema_alto_contraste,
        },
        {
            'tipo': Preferencia.MODO_DALTONISMO,
            'descricao': 'Destinado a pessoas com discromatopsia (dificuldade na percepção das cores). O tema se assemelha ao Padrão, com alterações suaves que permitem uma maior facilidade na identificação das cores designadas.',
            'qtd': tema_modo_daltonismo,
        },
    ]

    temas_gerais = [get_tema(**tema) for tema in temas_gerais_dict]
    temas_gov = [get_tema(**tema) for tema in temas_gov_dict]
    temas_acessibilidade = [get_tema(**tema) for tema in temas_acessibilidade_dict]

    return {
        'temas_gerais': temas_gerais,
        'temas_gov': temas_gov,
        'temas_acessibilidade': temas_acessibilidade,
    }


def get_acoes_por_periodo(request, usuario, datahora_inicio, datahora_fim):
    dados = []
    request_user_original = request.user
    request.user = usuario
    minhas_acoes.signal.send(sender=None, request=request, data=dados, datahora_inicio=datahora_inicio, datahora_fim=datahora_fim)
    request.user = request_user_original
    if dados:
        areas = {}
        for area, categoria, objeto, descricao, url in dados:
            if area not in areas:
                areas[area] = {}
            if categoria not in areas[area]:
                areas[area][categoria] = []
            areas[area][categoria].append((objeto, descricao, url))

        return areas
    return []
