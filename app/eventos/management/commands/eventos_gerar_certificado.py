import io
import os

from django.shortcuts import get_object_or_404
from django.template.defaultfilters import slugify

from djtools.management.commands import BaseCommandPlus
from djtools.utils import gerar_documento_impressao
from eventos.models import Participante
from eventos.utils import anexar_tabela_trabalhos_aprovados


class Command(BaseCommandPlus):
    help = 'Gera certificado de participante a partir do código hash - Replica a view baixar_certificado'

    def add_arguments(self, parser):
        parser.add_argument('hash', type=str, help='Código hash do participante para geração do certificado')
        parser.add_argument('--atividade-id', type=int, default=None, help='ID da atividade específica (opcional)')
        parser.add_argument(
            '--output', type=str, default=None, help='Caminho para salvar o certificado (opcional, padrão: /tmp/certificado_HASH.pdf)'
        )

    def handle(self, *args, **options):
        codigo_geracao_certificado = options['hash']
        atividade_id = options.get('atividade_id')
        output_path = options.get('output')

        self.stdout.write(self.style.WARNING(f'Buscando participante com hash: {codigo_geracao_certificado}'))

        # Replicando a estrutura da view baixar_certificado
        if codigo_geracao_certificado:
            participante = get_object_or_404(Participante, codigo_geracao_certificado=codigo_geracao_certificado)
            atividades_participante = participante.get_atividades()  # noqa: F841 - mantido da view original
            evento = participante.evento

            self.stdout.write(self.style.SUCCESS(f'Participante encontrado: {participante.nome}'))
            self.stdout.write(f'Evento: {evento.nome}')
            self.stdout.write(f'Tipo: {participante.tipo}')
        else:
            self.stdout.write(self.style.ERROR('Código hash não informado.'))
            return

        modelo_certificado = participante.get_modelo_certificado()
        if not modelo_certificado:
            self.stdout.write(self.style.ERROR('Participante sem modelo de certificado definido.'))
            return

        self.stdout.write(self.style.WARNING('Gerando dados do certificado...'))
        dados_certificado = participante.get_dados_certificado(atividade_id=atividade_id)

        try:
            self.stdout.write(self.style.WARNING('Gerando documento de impressão...'))
            caminho_arquivo = gerar_documento_impressao(dados_certificado, io.BytesIO(modelo_certificado.read()))
            if participante.tipo.tipo_participacao.descricao == 'Autor de trabalho':
                trabalhos_aprovados = participante.get_trabalhos_aprovados()
                if trabalhos_aprovados.exists():
                    self.stdout.write(self.style.WARNING('Anexando tabela de trabalhos aprovados...'))
                    submissoes = {'submissoes': trabalhos_aprovados}
                    caminho_arquivo = anexar_tabela_trabalhos_aprovados(submissoes, caminho_arquivo)

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Erro: {e!s}'))
            return

        if not caminho_arquivo:
            aba = slugify(participante.tipo.tipo_participacao.descricao)
            self.stdout.write(self.style.ERROR(f'Documento não encontrado. (aba: {aba})'))
            return

        nome_arquivo = caminho_arquivo.split('/')[-1]
        try:
            arquivo = open(caminho_arquivo, 'rb')
        except Exception:
            aba = slugify(participante.tipo.tipo_participacao.descricao)
            self.stdout.write(self.style.ERROR(f'Modelo de certificado não encontrado. (aba: {aba})'))
            return

        # Define o caminho de saída
        if not output_path:
            output_path = f'/tmp/certificado_{codigo_geracao_certificado}_{nome_arquivo}'

        # Salva o arquivo no destino
        self.stdout.write(self.style.WARNING(f'Salvando arquivo em: {output_path}'))
        try:
            with open(output_path, 'wb') as destino:
                destino.write(arquivo.read())
            arquivo.close()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Erro ao salvar arquivo: {e!s}'))
            arquivo.close()
            os.unlink(caminho_arquivo)
            return

        # Remove o arquivo temporário
        os.unlink(caminho_arquivo)

        # Exibe informações de sucesso
        content_type = caminho_arquivo.endswith('.pdf') and 'application/pdf' or 'application/vnd.ms-word'
        tamanho = os.path.getsize(output_path)

        self.stdout.write(self.style.SUCCESS('\nCertificado gerado com sucesso!'))
        self.stdout.write(self.style.SUCCESS(f'Arquivo salvo em: {output_path}'))
        self.stdout.write(f'Nome do arquivo: {nome_arquivo}')
        self.stdout.write(f'Content-Type: {content_type}')
        self.stdout.write(f'Tamanho do arquivo: {tamanho:,} bytes')
