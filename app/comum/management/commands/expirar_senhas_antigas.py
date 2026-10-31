import datetime

import tqdm
from django.conf import settings
from sentry_sdk import capture_exception

from comum.models import Configuracao, Log, User
from djtools.management.commands import BaseCommandPlus
from djtools.utils import get_ldap_conf, send_mail


class Command(BaseCommandPlus):
    def add_arguments(self, parser):
        parser.add_argument('args', nargs='*', type=str)
        parser.add_argument(
            '--qtd', action='store', dest='qtd', default=0, type=int, help='Informe a quantidade de usuários que você quer expirar no AD.'
        )

    def handle(self, *args, **options):
        verbosity = int(options['verbosity']) > 0
        hoje = datetime.datetime.today()
        sigla_instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')
        prazo_expiracao_senha = int(Configuracao.get_valor_por_chave('comum', 'prazo_expiracao_senha'))

        if not prazo_expiracao_senha:
            if verbosity:
                self.stderr.write('Nenhum prazo de expiração de senha definido.')
            return

        prazo = hoje - datetime.timedelta(days=prazo_expiracao_senha)
        qtd = options['qtd']

        qs = User.objects.filter(data_ultima_alteracao_senha__lte=prazo, forcar_troca_senha=False).order_by('data_ultima_alteracao_senha')
        total = qtd or qs.count()
        qs = qs[:total]

        if verbosity:
            self.stdout.write(f'Expirando senha de {total} usuários no suap')
            qs = tqdm.tqdm(qs)

        for user in qs:
            user.forcar_troca_senha = True
            user.data_solicitacao_forcar_troca_senha = datetime.datetime.now()
            user.save()
            try:
                if user.get_profile():
                    nome_pessoa = user.get_profile().nome
                    vinculo_user = user.get_vinculo()
                    email = vinculo_user.email_notificacao if vinculo_user else ''
                    notificar = bool(vinculo_user and vinculo_user.ativo) and user.is_active
                else:
                    nome_pessoa = user.get_full_name()
                    email = user.email
                    notificar = False

                if notificar and email:
                    url_redefinir_senha = f'{settings.SITE_URL}/comum/solicitar_trocar_senha/'

                    titulo = '[SUAP] Senha expirada automaticamente'
                    mensagem = f"""
                                <h1>Assunto: Aviso Importante - Ação Necessária para sua Conta junto ao {sigla_instituicao}</h1>
                                <p>Olá {nome_pessoa},</p>
                                <p>Esperamos que você esteja bem. Estamos entrando em contato para fornecer informações
                                importantes sobre a suas contas de e-mail, acesso ao SUAP e acesso as máquinas institucionais do {sigla_instituicao}.
                                </p>
                                <p>Sua senha foi expirada automaticamente pois não era atualizada a mais de {prazo_expiracao_senha} dias, para conseguir acessar o SUAP novamente você precisará redefinir sua senha em: <a href="{url_redefinir_senha}">{url_redefinir_senha}</a>.</p>
                                <p>Atenciosamente,</p>
                                """
                    send_mail(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [email])
            except Exception as e:
                if settings.DEBUG:
                    raise e
                capture_exception(e)
        conf = get_ldap_conf()
        if conf:
            if verbosity:
                self.stdout.write('Expirando senha no AD')
            for user in qs:
                conf.force_user_reset_password(user.username)
        msg = f'{total} usuários tiveram suas senhas expiradas.'
        Log.objects.create(titulo='Command Expirar Senhas Antigas', texto=msg, app='comum')
