from jwcrypto import jwk
import logging
import json
from django.conf import settings
from reportlab.pdfgen import canvas
from djtools.management.commands import BaseCommandPlus
from comum.services.icp_edu import ApiICPEDUService
from djtools.utils.icpedu import signer
from comum.models import User, Configuracao


logger = logging.getLogger(__name__)


class Command(BaseCommandPlus):
    """
    Usage: python manage.py edu_configure_api --username XXXXX --url https://hmg.assina.icpedu.rnp.br --test
    """

    def check(self, *args, **kwargs):
        pass

    def check_migrations(self, *args, **kwargs):
        pass

    def add_arguments(self, parser):
        parser.add_argument('--url', type=str, help='URL base da API ICPEDU', required=True)
        parser.add_argument('--username', type=str, help='Usuário', required=True)
        parser.add_argument('--test', action='store_true', help='Testar assinatura')

    def handle(self, *args, **options):
        url = options['url']
        username = options['username']
        test = options['test']

        logger.info(f'URL: {url}')
        logger.info(f'USERNAME: {username}')

        service = ApiICPEDUService()
        user = User.objects.filter(username=username).first()
        if user is None:
            logger.info('Usuário não encontrado')
            return
        if user.get_profile() is None:
            logger.info('Usuário não possui pessoa física associada')
            return
        if service.api_externa.url_base == url:
            logger.info(f'API is already configured with URL {url}!')
        else:
            # Generate RSA key pair
            key = jwk.JWK.generate(kty='RSA', size=2048)

            # Set Key ID
            key.update(kid='suap')

            # Export private JWK
            private_jwk = key.export(private_key=True)

            # Export public JWK
            public_jwk = key.export(private_key=False)

            self.stdout.write('\nPRIVATE KEY:')
            private_jwk_string = json.dumps(json.loads(private_jwk), indent=2)
            self.stdout.write(f'\n{private_jwk_string}')

            self.stdout.write('\n\nPUBLIC KEY:')
            public_jwk_string = json.dumps(json.loads(public_jwk), indent=2)
            self.stdout.write(f'\n{public_jwk_string}')

            service.api_externa.nome = 'ICPEDU'
            service.api_externa.url_base = url
            service.api_externa.tipo_autenticacao = service.api_externa.CLIENT_CREDENTIALS_AUTH
            service.api_externa.client_id = public_jwk_string
            service.api_externa.secret = private_jwk_string
            service.api_externa.headers = {'ISS': settings.SITE_URL}
            service.api_externa.usuario_responsavel = user
            service.api_externa.service_path = 'comum.services.ApiICPEDUService'
            service.api_externa.save()

            self.stdout.write(
                f'\n\n\nAPI configurada. Envie um e-mail para a RNP informando a ISS "{settings.SITE_URL}" e URL "{settings.SITE_URL}/comum/jwk/"\n\n\n'
            )

        if test:
            file_path = '/tmp/test.pdf'
            pdf = canvas.Canvas(file_path)
            pdf.drawString(500, 750, 'Hello World')
            pdf.save()

            signer.assinar_arquivo_pdf(
                file_path, user.get_profile(), 'Anexo', x=50, y=50, page=1, bgcolor='#DDD', titulo='Analista de TI', codigo_autenticacao='123456'
            )

            self.stdout.write(f'\n\n\nValide a assinatura do arquivo {file_path} através do endereço https://verificador.rnp.br/result\n\n\n')

        qs = Configuracao.objects.filter(app='edu', chave='utilizar_api_icpedu')
        if qs.exists():
            qs.update(valor='True')
        else:
            Configuracao.objects.get_or_create(app='edu', chave='utilizar_api_icpedu', valor='True', descricao='')
