import socket
from urllib.parse import urlparse

from django.conf import settings
from sentry_sdk import capture_exception

from comum.utils import ferramentas_configuradas
from demandas.models import AnalistaDesenvolvedor
from djtools.utils import get_view_name_from_url, render_to_string, requests
from erros.notificacoes import Notificar


def get_hostname():
    server_alias = getattr(settings, 'SERVER_ALIAS', '')
    host_name = server_alias and f'{server_alias} - {socket.gethostname()}' or socket.gethostname()

    return host_name


def get_sentry_issue_id_from_url(url):
    try:
        try:
            issue_id = urlparse(url).path.split('/')[-2]
            return int(issue_id)
        except Exception:
            issue_id = urlparse(url).path.split('/')[-1]
            return int(issue_id)
    except Exception:
        return None


def criar_issue_gitlab(erro, conf, request):
    try:
        descricao_issue = render_to_string(
            'notificacoes/criar_issue_gitlab.html', {'erro': erro, 'request': request, 'site_url': settings.SITE_URL}
        ).replace('&amp;', '&')
        data = {
            'title': f'Erro {erro.id} - {erro.modulo_afetado_display}',
            'description': descricao_issue,
            'labels': [conf['git_label_todo'], erro.modulo_afetado],
            'milestone_id': conf['git_id_milestone_erros'],
        }
        issue = conf['git'].projects.get(conf['gitlab_suap_id']).issues.create(data)
    except Exception as e:
        capture_exception(e)
        return None
    if issue:
        from erros.models import Erro, HistoricoComentarioErro

        notificar = erro.situacao != Erro.SITUACAO_EM_ANALISE
        erro.gitlab_issue_url = issue.web_url
        erro.situacao = Erro.SITUACAO_EM_ANALISE
        erro.save()
        descricao_comentario = 'Issue criada no Gitlab.'
        HistoricoComentarioErro.objects.create(
            erro=erro, descricao=descricao_comentario, automatico=True, visibilidade=HistoricoComentarioErro.VISIBILIDADE_ATENDENTES
        )
        if notificar:
            descricao_comentario_publico = 'A situação do erro foi alterada para: Em análise.'
            HistoricoComentarioErro.objects.create(erro=erro, descricao=descricao_comentario_publico, automatico=True)
            Notificar.alterar_situacao_erro(erro, request.user.get_vinculo(), descricao_comentario_publico)
        return issue.web_url


def reabrir_issue_gitlab(erro, conf):
    if erro.gitlab_issue_url:
        gitlab_issue_id = erro.gitlab_issue_url.split('/')[-1]
        gitlab_issue = conf['git'].projects.get(conf['gitlab_suap_id']).issues.get(gitlab_issue_id)
        if gitlab_issue.state == 'closed':
            gitlab_issue.state_event = 'reopen'
            gitlab_issue.labels.append(conf['git_label_todo'])
            for label in [conf['git_label_feedback'], conf['git_label_doing'], conf['git_label_done']]:
                if label in gitlab_issue.labels:
                    gitlab_issue.labels.remove(label)
            gitlab_issue.save()


def atualizar_label_feedback_issue_gitlab(erro, conf):
    if erro.gitlab_issue_url:
        gitlab_issue_id = erro.gitlab_issue_url.split('/')[-1]
        gitlab_issue = conf['git'].projects.get(conf['gitlab_suap_id']).issues.get(gitlab_issue_id)
        gitlab_issue.labels.append(conf['git_label_feedback'])
        for label in [conf['git_label_todo'], conf['git_label_doing'], conf['git_label_done']]:
            if label in gitlab_issue.labels:
                gitlab_issue.labels.remove(label)
        gitlab_issue.save()


def comentar_issue_gitlab(erro, comment, conf=None, alter_labels=True):
    try:
        conf = conf or ferramentas_configuradas()
        if conf and erro.gitlab_issue_url:
            gitlab_issue_id = erro.gitlab_issue_url.split('/')[-1]
            gitlab_issue = conf['git'].projects.get(conf['gitlab_suap_id']).issues.get(gitlab_issue_id)
            if alter_labels:
                if gitlab_issue.assignee:
                    gitlab_issue.labels.append(conf['git_label_doing'])
                    for label in [conf['git_label_feedback'], conf['git_label_todo'], conf['git_label_done']]:
                        if label in gitlab_issue.labels:
                            gitlab_issue.labels.remove(label)
                else:
                    gitlab_issue.labels.append(conf['git_label_todo'])
                    for label in [conf['git_label_feedback'], conf['git_label_doing'], conf['git_label_done']]:
                        if label in gitlab_issue.labels:
                            gitlab_issue.labels.remove(label)
            gitlab_issue.save()

            # Apenas adiciona comentário em issue atribuída.
            if gitlab_issue.assignee:
                gitlab_issue.discussions.create({'body': comment})

    except Exception as e:
        capture_exception(e)


def fechar_issue_gitlab(erro, conf):
    if erro.gitlab_issue_url:
        gitlab_issue_id = erro.gitlab_issue_url.split('/')[-1]
        gitlab_issue = conf['git'].projects.get(conf['gitlab_suap_id']).issues.get(gitlab_issue_id)
        if gitlab_issue.state == 'opened':
            gitlab_issue.state_event = 'close'
            gitlab_issue.labels.append(conf['git_label_done'])
            for label in [conf['git_label_feedback'], conf['git_label_todo'], conf['git_label_doing']]:
                if label in gitlab_issue.labels:
                    gitlab_issue.labels.remove(label)
            gitlab_issue.save()


def comentar_erro_issue_gitlab(erro, conf):
    try:
        comentario = f'O erro referente a esta issue está disponível em <a href="{settings.SITE_URL}{erro.get_absolute_url()}">{settings.SITE_URL}{erro.get_absolute_url()}</a>'
        gitlab_issue_id = erro.gitlab_issue_url.split('/')[-1]
        gitlab_issue = conf['git'].projects.get(conf['gitlab_suap_id']).issues.get(gitlab_issue_id)
        gitlab_issue.discussions.create({'body': comentario})
    except Exception:
        return None


def popular_links_gitlab(erro, conf):
    from erros.models import HistoricoComentarioErro

    try:
        if erro.sentry_issue_id:
            url = f'{conf["sentry_url"]}/api/0/issues/{erro.sentry_issue_id}/'
            if not erro.gitlab_issue_url:
                issues = requests.get(
                    url,
                    headers=conf['sentry_headers'],
                    timeout=settings.REQUESTS_TIMEOUT,
                ).json()
                if issues.get('annotations'):
                    erro.gitlab_issue_url = issues.get('annotations')[0]['url']
                comentar_erro_issue_gitlab(erro, conf)
        if erro.gitlab_issue_url:
            if erro.situacao in [erro.SITUACAO_ABERTO, erro.SITUACAO_REABERTO]:
                erro.situacao = erro.SITUACAO_EM_ANALISE
                descricao = 'Erro em análise pela equipe de Desenvolvimento.'
                HistoricoComentarioErro.objects.create(erro=erro, descricao=descricao, automatico=True)
        erro.save()
        return erro.gitlab_issue_url
    except Exception as e:
        capture_exception(e)
    return erro.gitlab_issue_url


def sincronizar_ferramentas(erro, conf):
    from erros.models import HistoricoComentarioErro

    try:
        gitlab_issue_url = popular_links_gitlab(erro, conf)
        if gitlab_issue_url:
            gitlab_issue_id = gitlab_issue_url.split('/')[-1]
            gitlab_issue = conf['git'].projects.get(conf['gitlab_suap_id']).issues.get(gitlab_issue_id)
            if gitlab_issue.state == 'closed':
                usuario = None
                if gitlab_issue.assignee:
                    username = gitlab_issue.assignee.get('username', '')
                    analista = AnalistaDesenvolvedor.objects.filter(username_gitlab=username).first()
                    if analista:
                        usuario = analista.usuario
                descricao = 'SUAP atualizado com a correção deste erro.'
                HistoricoComentarioErro.objects.create(erro=erro, descricao=descricao, automatico=True)
                erro.situacao = erro.SITUACAO_RESOLVIDO
                erro.editar_atualizacao(usuario)
                erro.save()
                data = {'status': 'resolved'}
                url = f'{conf["sentry_url"]}/api/0/issues/{erro.sentry_issue_id}/'
                requests.put(
                    url,
                    headers=conf['sentry_headers'],
                    data=data,
                    timeout=settings.REQUESTS_TIMEOUT,
                )
                Notificar.alterar_situacao_erro(erro, None, descricao)
    except Exception as e:
        capture_exception(e)


def get_custom_view_name_from_url(url):
    path = urlparse(url).path
    if path.startswith('/erros/modulo/'):
        modulo = path.split('/')[-2]
        return f'{modulo}.views.nao_existe'
    return get_view_name_from_url(url)


def get_auto_modulo_afetado(erro_view: str) -> str:
    modulo_afetado = ''
    try:
        names = erro_view.split('.')
        if names[0] == 'admin':
            modulo_afetado = names[1] or 'admin'
        else:
            modulo_afetado = names[0]
    except Exception:
        modulo_afetado = 'djtools'
    return modulo_afetado
