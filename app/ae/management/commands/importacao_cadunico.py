import datetime

import sentry_sdk
from django.conf import settings
from django.contrib.auth.models import Group

from ae.models import ImportacaoCadunico
from comum.models import APIExterna
from djtools.management.commands import BaseCommandPlus
from djtools.tasks import notificar_usuarios_grupo
from edu.models import Aluno
from rh.models import PessoaInfoComplementar


class Command(BaseCommandPlus):
    help = 'Importa dados do CadÚnico'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=None, help='Quantidade máxima de registros a importar.')

    def handle(self, *args, **options):
        limit = options['limit']
        qtde_cadunico = 0
        qtde_nao_cadunico = 0
        qtd_erros = 0

        try:
            importacoes_pendentes = ImportacaoCadunico.objects.filter(data_importacao=datetime.datetime.now().date(), execucao_concluida=False)
            if importacoes_pendentes.exists():
                api_externa = APIExterna.CADUNICO
                if not api_externa.ativo:
                    self.stdout.write(self.style.ERROR('A API do CadÚnico está desabilitada.'))
                    return
                for importacao in importacoes_pendentes:
                    alunos_ativos_com_cpf = Aluno.ativos.filter(pessoa_fisica__cpf__isnull=False)
                    alunos_para_importar = alunos_ativos_com_cpf if not limit else alunos_ativos_com_cpf[:limit]
                    if not importacao.atualizar_todos_alunos:
                        ids_pessoas_info_complementar_importadas = PessoaInfoComplementar.objects.filter(
                            api_origem=api_externa, informacoes__pessoaCadastrada=False
                        ).values_list('pessoa__id', flat=True)
                        alunos_para_importar = alunos_para_importar.exclude(pessoa_fisica__id__in=ids_pessoas_info_complementar_importadas)
                    self.stdout.write(self.style.WARNING(f'Importando {alunos_para_importar.count()} alunos...'))
                    for aluno in alunos_para_importar:
                        tem_cadunico = False
                        info_cadunico = PessoaInfoComplementar.get_instance(aluno.pessoa_fisica, api_externa, force=True)
                        if info_cadunico and info_cadunico.informacoes.get('cadastroAtualizado'):
                            tem_cadunico = True
                        if info_cadunico:
                            if tem_cadunico:
                                qtde_cadunico += 1
                            elif info_cadunico.informacoes.get('pessoaCadastrada') is False:
                                qtde_nao_cadunico += 1
                        else:
                            qtd_erros += 1
                    importacao.qtde_alunos_cadunico = qtde_cadunico
                    importacao.qtde_alunos_nao_cadunico = qtde_nao_cadunico
                    importacao.execucao_concluida = True
                    importacao.save()
                    # Enviar e-mail de notificação
                    grupo_sistemicos_ae = Group.objects.filter(name='Coordenador de Atividades Estudantis Sistêmico').first()
                    titulo = '[SUAP] Serviço Social: Importação de dados do CadÚnico'
                    texto = (
                        '<h1>Serviço Social</h1>'
                        '<h2>Importação de Dados do CadÚnico</h2>'
                        f'<p>A importação realizada em {importacao.data_importacao.strftime("%d/%m/%Y")} foi executada.</p>'
                        f'<p>Quantidade de Alunos com CadÚnico importados: {importacao.qtde_alunos_cadunico}</p>'
                        f'<p>Quantidade de Alunos que não possui CadÚnico importados: {importacao.qtde_alunos_nao_cadunico}</p>'
                    )
                    notificar_usuarios_grupo(titulo, settings.DEFAULT_FROM_EMAIL, texto, grupo_sistemicos_ae)

                    self.stdout.write(self.style.SUCCESS('Importação concluída e notificação enviada.'))
                    self.stdout.write(
                        self.style.SUCCESS(f'Importados {qtde_cadunico} alunos com CadÚnico e {qtde_nao_cadunico} alunos sem CadÚnico.')
                    )
                    self.stdout.write(self.style.ERROR(f'{qtd_erros} erros na importação e alunos.'))
            else:
                self.stdout.write(self.style.ERROR('Nenhuma importação pendente encontrada.'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Ocorreu um erro: {e}'))
            if hasattr(e, 'response') and e.response:
                self.stdout.write(self.style.ERROR(f'Resposta do servidor: {e.response.text}'))
            sentry_sdk.capture_exception(e)
