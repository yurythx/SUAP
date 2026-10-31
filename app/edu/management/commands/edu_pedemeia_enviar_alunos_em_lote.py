from django.apps import apps

from djtools.management.commands import BaseCommandPlus
from edu.models import Modalidade, SituacaoMatricula


class Command(BaseCommandPlus):
    def chunk_queryset(self, queryset, chunk_size=100):
        chunk = []
        for item in queryset:
            chunk.append(item)
            if len(chunk) == chunk_size:
                yield chunk
                chunk = []
        if chunk:
            yield chunk

    def handle(self, *args, **options):
        ApiExterna = apps.get_model('comum', 'APIExterna')
        Aluno = apps.get_model('edu', 'Aluno')
        RequisicaoPeDeMeia = apps.get_model('edu', 'RequisicaoPeDeMeia')

        api_externa_pedemeia = ApiExterna.PEDEMEIA

        if api_externa_pedemeia.ativo:
            api_service = api_externa_pedemeia.get_service()
            alunos = (
                Aluno.objects.filter(matriz__isnull=False, situacao=SituacaoMatricula.MATRICULADO, curso_campus__modalidade=Modalidade.INTEGRADO)
                .select_related('curso_campus__diretoria__setor__uo')
                .exclude(requisicaopedemeia__tipo=RequisicaoPeDeMeia.CADASTRO, requisicaopedemeia__processada=True)
            )
            qtd_cadastrado = 0
            qtd_falhas = 0
            # Divide o queryset em chunks
            QTD_POR_LOTE = 100
            for lote in self.chunk_queryset(alunos, chunk_size=QTD_POR_LOTE):
                sucesso, _status_code, _conteudo_resposta = api_service.cadastrar_estudantes_em_lote(lote)
                if sucesso:
                    qtd_cadastrado += 1
                else:
                    qtd_falhas += 1

            self.stdout.write(f'Qtd Lotes Enviados Em Processamento: {qtd_cadastrado}')
            self.stdout.write(f'Qtd Lotes com Falha ao Enviar: {qtd_falhas}')
        else:
            self.stderr.write('API Pé de Meia não está ativa.')
