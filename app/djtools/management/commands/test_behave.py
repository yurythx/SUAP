from django.conf import settings
from django.core.management.commands.test import Command as TestCommand

settings.TEST_RUNNER = 'djtools.new_tests.runner.MyBehaveTestRunner'


class Command(TestCommand):
    help = 'Executa os testes do SUAP'
