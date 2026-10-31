from django.core.management.base import BaseCommand
from django.db.models import Q

from eventos.models import Submissao

"""
python manage.py extrair_conteudos_submissoes --evento-id 8448 --reprocessar
"""


class Command(BaseCommand):
    help = 'Extrai conteúdo textual de arquivos PDF/DOCX das submissões existentes para análise de duplicidade'

    def add_arguments(self, parser):
        parser.add_argument(
            '--evento-id',
            type=int,
            help='ID do evento para processar apenas suas submissões',
        )
        parser.add_argument(
            '--reprocessar',
            action='store_true',
            help='Reprocessa submissões que já possuem conteúdo extraído',
        )
        parser.add_argument(
            '--limite',
            type=int,
            default=100,
            help='Número máximo de submissões a processar (padrão: 100)',
        )

    def handle(self, *args, **options):
        evento_id = options.get('evento_id')
        reprocessar = options.get('reprocessar')
        limite = options.get('limite')

        self.stdout.write(self.style.NOTICE('Iniciando extração de conteúdo das submissões...'))

        # Monta o filtro base
        filtro = Q()
        if evento_id:
            filtro &= Q(modalidade__evento_id=evento_id)
            self.stdout.write(self.style.NOTICE(f'Filtrando submissões do evento ID: {evento_id}'))

        # Se não for para reprocessar, busca apenas submissões sem conteúdo extraído
        if not reprocessar:
            filtro &= Q(conteudo_extraido__isnull=True) | Q(conteudo_extraido='')

        # Busca submissões que possuem arquivo na primeira versão
        submissoes = Submissao.objects.filter(filtro).filter(versoes__numero=1, versoes__arquivo__isnull=False).distinct()[:limite]

        total = submissoes.count()
        if total == 0:
            self.stdout.write(self.style.WARNING('Nenhuma submissão encontrada para processar.'))
            return

        self.stdout.write(self.style.NOTICE(f'Total de submissões a processar: {total}'))

        sucesso = 0
        erro = 0
        sem_arquivo = 0

        for i, submissao in enumerate(submissoes, 1):
            self.stdout.write(f'[{i}/{total}] Processando submissão ID {submissao.id}: {submissao.titulo[:50]}...')

            try:
                conteudo = submissao.extrair_conteudo_arquivo()
                if conteudo:
                    sucesso += 1
                    self.stdout.write(self.style.SUCCESS(f'  [OK] Conteúdo extraído ({len(conteudo)} caracteres)'))
                else:
                    sem_arquivo += 1
                    self.stdout.write(self.style.WARNING('  [AVISO] Não foi possível extrair conteúdo'))
            except Exception as e:
                erro += 1
                self.stdout.write(self.style.ERROR(f'  [ERRO] Erro ao processar: {e!s}'))

        # Resumo
        self.stdout.write('\n' + '=' * 70)
        self.stdout.write(self.style.SUCCESS('Processamento concluído!'))
        self.stdout.write(f'Total processado: {total}')
        self.stdout.write(self.style.SUCCESS(f'Sucesso: {sucesso}'))
        self.stdout.write(self.style.WARNING(f'Sem conteúdo/arquivo: {sem_arquivo}'))
        if erro > 0:
            self.stdout.write(self.style.ERROR(f'Erros: {erro}'))
        self.stdout.write('=' * 70)
