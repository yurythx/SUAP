import datetime
from collections.abc import Iterable
from typing import Any

from django.conf import settings
from django.db.models import Q, QuerySet
from sentry_sdk import capture_exception

from comum.models import CategoriaNotificacao, Configuracao, PreferenciaNotificacao, SenhaExposta, User
from djtools.assincrono import task
from djtools.utils import send_mail, send_notification
from ldap_backend.models import LdapConf

# Atributos do AD que podem guardar o e-mail vazado, usados quando ele não casa com nenhum usuário do SUAP.
ATRIBUTOS_BUSCA_AD = ('sAMAccountName', 'mail', 'extensionAttribute8', 'extensionAttribute9', 'extensionAttribute4', 'extensionAttribute5')


def buscar_usuarios(username: str, ldap_conf: LdapConf | None) -> tuple[QuerySet, list[str]]:
    """Busca os usuários correspondentes ao e-mail/username vazado.

    Sem correspondência no SUAP, procura o valor nos atributos do AD (``ATRIBUTOS_BUSCA_AD``).
    Retorna os usuários do SUAP e as matrículas que só existem no AD — essas não têm o que
    notificar nem registrar, mas ainda assim precisam ter a senha expirada.
    """
    users = User.objects.filter(
        Q(username__iexact=username)
        | Q(vinculo__email_pessoal__iexact=username)
        | Q(vinculo__pessoa__pessoafisica__aluno_set__email_academico__iexact=username)
        | Q(vinculo__pessoa__pessoafisica__aluno_set__email_google_classroom__iexact=username)
        | Q(vinculo__pessoa__pessoafisica__servidor_set__email_institucional__iexact=username)
        | Q(vinculo__pessoa__pessoafisica__servidor_set__email_academico__iexact=username)
        | Q(vinculo__pessoa__pessoafisica__servidor_set__email_google_classroom__iexact=username)
    ).distinct()
    if users or not ldap_conf:
        return users, []
    # ponytail: um bind no AD por e-mail não encontrado; reusar a conexão se o dump crescer.
    usernames_ad = ldap_conf.get_usernames_from_attributes(ATRIBUTOS_BUSCA_AD, username)
    users = User.objects.filter(username__in=usernames_ad)
    return users, sorted(set(usernames_ad) - set(users.values_list('username', flat=True)))


def expirar_no_ad(username: str, usernames_ad: list[str], ldap_conf: LdapConf, usuarios_expirados: list[str]) -> str:
    """Expira no AD as contas sem usuário no SUAP e devolve as linhas do relatório."""
    linhas = ''
    for username_ad in usernames_ad:
        ldap_conf.force_user_reset_password(username_ad)
        if username_ad not in usuarios_expirados:
            usuarios_expirados.append(username_ad)
            linhas += f'<tr><td>{username}</td><td>{username_ad} (somente no AD)</td></tr>'
    return linhas


def dados_notificacao(user: User, vinculo: Any) -> tuple[str, str, bool]:
    """Retorna o nome, o e-mail de notificação e se o usuário deve ser notificado por e-mail."""
    if user.get_profile():
        return user.get_profile().nome, vinculo.email_notificacao if vinculo else '', vinculo.ativo and user.is_active
    return user.get_full_name(), user.email, False


def notificar_senha_exposta(
    user: User, vinculo: Any, nome_pessoa: str, email: str, notificar: bool, usuarios_expirados: list[str], contexto: dict
) -> None:
    """Notifica o usuário (via SUAP e, quando cabível, por e-mail) sobre a senha expirada."""
    # Sem sigla configurada, texto neutro em vez de "junto ao None" (#17472).
    sigla_instituicao = Configuracao.get_valor_por_chave_str('comum', 'instituicao_sigla')
    junto_a_instituicao = f' junto ao {sigla_instituicao}' if sigla_instituicao else ''
    da_instituicao = f' do {sigla_instituicao}' if sigla_instituicao else ''
    try:
        if user.username not in usuarios_expirados:
            titulo_notificacao = '[SUAP] Alerta de senha exposta'
            mensagem_notificacao = f'''
            <p>Olá {nome_pessoa},</p>
            <p>Recebemos um reporte de incidente de quebra de senha no qual um ou mais dos seus endereços de e-mail estavam incluídos. Por questões de segurança, foi solicitada a alteração da sua senha pelo Suap. A antiga senha expirada está acessível em: <a href="{contexto['url_senhas_expostas']}">{contexto['url_senhas_expostas']}</a>. </p>
            '''
            send_notification(
                titulo_notificacao,
                mensagem_notificacao,
                settings.DEFAULT_FROM_EMAIL,
                [vinculo],
                contexto['categoria'],
                data_permite_excluir=contexto['expire_date'],
                data_permite_marcar_lida=contexto['expire_date'],
            )
            if notificar and email:
                titulo = '[SUAP] Senha expirada'
                mensagem = f'''
                            <h1>Assunto: Aviso Importante - Ação Necessária para sua Conta{junto_a_instituicao}</h1>
                            <p>Olá {nome_pessoa},</p>
                            <p>Esperamos que você esteja bem. Estamos entrando em contato para fornecer informações
                            importantes sobre as suas contas de e-mail, acesso ao SUAP e acesso as máquinas institucionais{da_instituicao}.
                            </p>
                            <p>A senha do seu usuário de matrícula "{user.username}" foi expirada, para conseguir acessar o SUAP novamente você precisará redefinir sua senha em: <a href="{contexto['url_redefinir_senha']}">{contexto['url_redefinir_senha']}</a>.</p>
                            <p>Atenciosamente,</p>
                            '''
                send_mail(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [email])
        usuarios_expirados.append(user.username)
    except Exception as e:
        if settings.DEBUG:
            raise e
        capture_exception(e)


def montar_texto_expirados(simular: bool, forcar_expiracao: bool, usuarios_expirados: list[str], usuarios_expirados_msg: str) -> str:
    """Monta o trecho do relatório final referente às senhas expiradas."""
    if simular:
        return 'Esta execução foi simulada, nenhuma senha foi expirada.'
    if not usuarios_expirados:
        return 'Nenhuma senha foi expirada.'
    return f"""
        Os seguintes usuários tiveram suas senhas {forcar_expiracao and '<strong>forçadamente</strong>' or ''} expiradas: <br>
        <div class="table-responsive">
        <table>
        <thead><tr>
        <th>Critério da busca</th>
        <th>Matrícula expirada</th>
        </tr></thead>
        <tbody>
        {usuarios_expirados_msg}
        </tbody>
        </table>
        </div>
        <br>
        """


@task('Expirando senhas em lote')
def expirar_senhas_em_lote(usuarios: Iterable[tuple[str, str, str]], simular: bool = True, forcar_expiracao: bool = False, task=None) -> None:
    usuarios_nao_encontrados = []
    usuarios_encontrados = []
    usuarios_expirados = []
    usuarios_expirados_msg = ''

    # dias_forcar_troca_senha = 180
    # data_vencimento = datetime.date.today() - datetime.timedelta(days=dias_forcar_troca_senha)
    url_redefinir_senha = f'{settings.SITE_URL}/comum/solicitar_trocar_senha/'
    url_senhas_expostas = f'{settings.SITE_URL}/admin/comum/senhaexposta/'
    ldap_conf = LdapConf.get_active()
    expire_date = datetime.datetime.now() + datetime.timedelta(days=3)
    categoria = 'Alerta de senha exposta'

    categoria_notificacao, _ = CategoriaNotificacao.objects.update_or_create(assunto=categoria, defaults={'forcar_habilitacao': True})
    contexto = {
        'url_redefinir_senha': url_redefinir_senha,
        'url_senhas_expostas': url_senhas_expostas,
        'categoria': categoria,
        'expire_date': expire_date,
    }

    for usuario in task.iterate(usuarios):
        username, senha, formato = usuario
        username = username.lower()
        users, usernames_somente_ad = buscar_usuarios(username, ldap_conf)
        if users or usernames_somente_ad:
            usuarios_encontrados.append(username)
        else:
            usuarios_nao_encontrados.append(username)
        if usernames_somente_ad and not simular:
            usuarios_expirados_msg += expirar_no_ad(username, usernames_somente_ad, ldap_conf, usuarios_expirados)
        for user in users:
            vinculo = user.get_vinculo()
            PreferenciaNotificacao.objects.get_or_create(
                vinculo=vinculo, categoria=categoria_notificacao, defaults={'via_suap': True, 'via_email': False}
            )
            senha_ja_expirada = SenhaExposta.objects.filter(usuario=user, senha=senha).exists()
            nome_pessoa, email, notificar = dados_notificacao(user, vinculo)
            if not simular:
                SenhaExposta.objects.get_or_create(
                    usuario=user,
                    email=username,
                    senha=senha,
                    defaults={
                        'formato_senha': formato,
                    },
                )
                if (not user.forcar_troca_senha and not senha_ja_expirada) or forcar_expiracao:
                    # if (user.data_ultima_alteracao_senha < data_vencimento and not user.forcar_troca_senha and not senha_ja_expirada) or forcar_expiracao:
                    usuarios_expirados_msg += f'<tr><td>{username}</td><td>{user.username}</td></tr>'
                    user.forcar_troca_senha = True
                    user.data_solicitacao_forcar_troca_senha = datetime.datetime.now()
                    user.save()
                    ldap_conf.force_user_reset_password(user.username)
                    notificar_senha_exposta(user, vinculo, nome_pessoa, email, notificar, usuarios_expirados, contexto)
    texto_expirados = montar_texto_expirados(simular, forcar_expiracao, usuarios_expirados, usuarios_expirados_msg)
    msg = f"""
        Os seguintes usuários foram encontrados: <br>
        <ul><li>{'</li><li>'.join(usuarios_encontrados)}</li></ul> <br>
        Os seguintes usuários não foram encontrados: <br>
        <ul><li>{'</li><li>'.join(usuarios_nao_encontrados)}</li></ul> <br>
        {texto_expirados}
        """
    task.finalize(msg, '..')
