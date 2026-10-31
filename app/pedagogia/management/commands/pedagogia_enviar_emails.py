from django.core.management.base import BaseCommand
from django.utils import termcolors

from pedagogia.models import QuestionarioMatriz


class Command(BaseCommand):
    def handle(self, *args, **options):
        verbose = options.get('verbosity', '0') != '0'
        for questionario in QuestionarioMatriz.objects.all():
            emails_enviados = questionario.enviar_email()
            if verbose:
                print(termcolors.make_style(fg='blue', opts=('bold',))(f'Questionário {questionario.descricao} enviou {emails_enviados} emails'))
