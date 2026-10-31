import os
import zipfile

from django.apps import apps
from django.conf import settings
from django.core.management import CommandError

from cnpq.management.commands.cnpq_importar import Command as CnpqImportarCommand
from cnpq.orcid import get_orcid_lattes
from comum.models import Vinculo
from djtools.management.commands import BaseCommandPlus
from rh.models import Servidor


class Command(BaseCommandPlus):
    help = 'Verifica, sem alterar dados, se o XML do currículo Lattes contém ORCID.'

    def add_arguments(self, parser):
        parser.add_argument('--file', '-f', dest='file', action='store', default='', help='Arquivo ZIP ou XML do currículo Lattes.')
        parser.add_argument('--matricula', '-m', dest='matricula', action='store', default='', help='Matrícula do servidor ou aluno.')
        parser.add_argument('--identificador', '-i', dest='identificador', action='store', default='', help='Identificador CNPq do currículo Lattes.')

    def handle(self, *args, **options):
        arquivo = options.get('file')
        matricula = options.get('matricula')
        identificador = options.get('identificador')

        if not arquivo and not matricula and not identificador:
            raise CommandError('Informe --file, --matricula ou --identificador.')

        vinculo = self.get_vinculo(matricula) if matricula else None
        identificador_cnpq = identificador or self.get_identificador_cnpq(vinculo)
        curriculo_str = self.get_curriculo_str(arquivo, identificador_cnpq, vinculo)
        orcid_xml = get_orcid_lattes(curriculo_str)
        orcid_suap = self.get_orcid_suap(vinculo)

        self.stdout.write(f'Identificador CNPq: {identificador_cnpq or "-"}')
        if vinculo:
            self.stdout.write(f'Vínculo: {vinculo}')
            if orcid_suap is None:
                self.stdout.write('ORCID no SUAP: campo ainda não existe nesta versão')
            else:
                self.stdout.write(f'ORCID no SUAP: {orcid_suap or "-"}')
        self.stdout.write(f'ORCID no XML: {orcid_xml or "-"}')
        self.stdout.write(f'Ação da importação: {self.get_acao_importacao(vinculo, orcid_suap, orcid_xml)}')

    def get_vinculo(self, matricula: str) -> Vinculo:
        servidor = Servidor.objects.filter(matricula=matricula).first()
        if servidor:
            return servidor.get_vinculo()

        if 'edu' in settings.INSTALLED_APPS:
            Aluno = apps.get_model('edu', 'Aluno')
            aluno = Aluno.objects.filter(matricula=matricula).first()
            if aluno:
                return aluno.get_vinculo()

        raise CommandError(f'Nenhum servidor ou aluno encontrado para a matrícula {matricula}.')

    def get_identificador_cnpq(self, vinculo: Vinculo | None) -> str:
        if not vinculo:
            return ''
        if hasattr(vinculo, 'vinculo_curriculo_lattes'):
            return vinculo.vinculo_curriculo_lattes.numero_identificador
        return CnpqImportarCommand().get_identificador(vinculo.relacionamento.pessoa_fisica.cpf)

    def get_curriculo_str(self, arquivo: str, identificador_cnpq: str, vinculo: Vinculo | None) -> bytes:
        if arquivo:
            return self.get_curriculo_str_arquivo(arquivo, identificador_cnpq)
        if not identificador_cnpq:
            raise CommandError('Não foi possível identificar o currículo CNPq.')
        eh_servidor = vinculo.eh_servidor() if vinculo else False
        return CnpqImportarCommand().get_curriculo(identificador_cnpq, eh_servidor)

    def get_curriculo_str_arquivo(self, arquivo: str, identificador_cnpq: str) -> bytes:
        if not os.path.isfile(arquivo):
            raise CommandError(f'Arquivo {arquivo} não encontrado.')
        if arquivo.lower().endswith('.xml'):
            with open(arquivo, 'rb') as arquivo_xml:
                return arquivo_xml.read()

        with zipfile.ZipFile(arquivo, 'r') as arquivo_zip:
            nomes_xml = [nome for nome in arquivo_zip.namelist() if nome.lower().endswith('.xml')]
            if not nomes_xml:
                raise CommandError(f'Arquivo {arquivo} não contém XML.')
            nome_xml = f'{identificador_cnpq}.xml' if identificador_cnpq else ''
            if nome_xml not in nomes_xml:
                nome_xml = 'curriculo.xml' if 'curriculo.xml' in nomes_xml else nomes_xml[0]
            return arquivo_zip.read(nome_xml)

    def get_orcid_suap(self, vinculo: Vinculo | None) -> str | None:
        if not vinculo:
            return None
        pessoa_fisica = vinculo.relacionamento.pessoa_fisica
        if not hasattr(pessoa_fisica, 'orcid'):
            return None
        return pessoa_fisica.orcid

    def get_acao_importacao(self, vinculo: Vinculo | None, orcid_suap: str | None, orcid_xml: str) -> str:
        if not vinculo:
            return 'não simula atualização do SUAP porque nenhum vínculo foi informado'
        if orcid_suap is None:
            return 'não simula atualização do SUAP porque o campo ORCID ainda não existe nesta versão'
        if orcid_suap:
            return 'manteria o ORCID já cadastrado no SUAP'
        if orcid_xml:
            return 'preencheria o ORCID no SUAP'
        return 'não alteraria o ORCID'
