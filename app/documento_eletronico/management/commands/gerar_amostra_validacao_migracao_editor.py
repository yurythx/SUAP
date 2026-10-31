"""
Gera a amostra de DocumentoTexto para validacao da migracao do editor.

Exemplos:

    python -u manage.py gerar_amostra_validacao_migracao_editor \
      --base-url-antiga https://master.suapdevs.ifrn.edu.br \
      --base-url-nova http://localhost:8000 \
      --formato csv

    python -u manage.py gerar_amostra_validacao_migracao_editor \
      --base-url-antiga https://master.suapdevs.ifrn.edu.br \
      --base-url-nova https://tinymce.suapdevs.ifrn.edu.br \
      --formato json \
      --output-file documento_eletronico/relatorio_tinymce/amostra_validacao_editor.json
"""

import csv
import json
from pathlib import Path

from django.db.models import Exists, OuterRef
from django.template.defaultfilters import filesizeformat
from django.urls import reverse

from djtools.management.commands import BaseCommandPlus
from documento_eletronico.models import DocumentoTexto, ModeloDocumento, TipoDocumentoTexto
from documento_eletronico.status import DocumentoStatus


CATEGORIAS_AMOSTRA = (
    ('finalizado_mais_antigo', DocumentoStatus.STATUS_FINALIZADO, ('data_criacao', 'id')),
    ('finalizado_mais_recente', DocumentoStatus.STATUS_FINALIZADO, ('-data_criacao', '-id')),
    ('concluido_mais_antigo', DocumentoStatus.STATUS_CONCLUIDO, ('data_criacao', 'id')),
    ('concluido_mais_recente', DocumentoStatus.STATUS_CONCLUIDO, ('-data_criacao', '-id')),
)

DEFAULT_OUTPUT_TEMPLATE = 'documento_eletronico/relatorio_tinymce/amostra_validacao_migracao_editor_documentotexto.{formato}'


class Command(BaseCommandPlus):
    """Gera uma amostra de ``DocumentoTexto`` para validar a migracao do editor.

    Para cada tipo de documento com documentos cadastrados, seleciona o mais
    antigo e o mais recente em cada estado (finalizado / concluido) e produz
    um arquivo CSV ou JSON com as URLs de visualizacao, PDF e edicao relativas
    e absolutas (antiga e nova).
    """

    help = 'Gera a amostra de DocumentoTexto para validacao da migracao do editor.'

    def add_arguments(self, parser):
        """Configura os argumentos de linha de comando aceitos pelo comando."""
        parser.add_argument(
            '--base-url-antiga',
            dest='base_url_antiga',
            help='URL base do ambiente antigo. Ex: https://antigo.exemplo',
        )
        parser.add_argument(
            '--base-url-nova',
            dest='base_url_nova',
            help='URL base do ambiente novo. Ex: https://novo.exemplo',
        )
        parser.add_argument(
            '--formato',
            choices=('csv', 'json'),
            default='csv',
            help='Formato do arquivo de saida. Padrao: csv.',
        )
        parser.add_argument(
            '--output-file',
            dest='output_file',
            help='Arquivo de saida. Padrao: documento_eletronico/relatorio_tinymce/amostra_validacao_migracao_editor_documentotexto.<formato>',
        )

    def handle(self, *args, **options):
        """Ponto de entrada do comando: gera a amostra e escreve o arquivo de saida."""
        base_url_antiga = self._normalize_base_url(options.get('base_url_antiga'))
        base_url_nova = self._normalize_base_url(options.get('base_url_nova'))
        formato = options['formato']
        output_file = options.get('output_file') or DEFAULT_OUTPUT_TEMPLATE.format(formato=formato)

        rows = self._build_rows(base_url_antiga=base_url_antiga, base_url_nova=base_url_nova)
        self._write_output(rows, output_file=output_file, formato=formato)

        self.stdout.write(f'{len(rows)} linha(s) geradas.')
        self.stdout.write(f'Arquivo salvo em: {output_file}')

    def _build_rows(self, base_url_antiga=None, base_url_nova=None):
        """Consulta os tipos de documento e monta a lista de linhas da amostra.

        Args:
            base_url_antiga: URL base do ambiente antigo para montar links absolutos.
            base_url_nova: URL base do ambiente novo para montar links absolutos.

        Returns:
            ``list[dict]`` com os dados serializados de cada documento da amostra.
        """
        rows = []
        self._emitir_status('Consultando tipos de documento com DocumentoTexto...')
        subquery_modelos_com_documentos = ModeloDocumento.objects.filter(tipo_documento_texto=OuterRef('pk'), documentotexto__isnull=False)
        tipos = list(
            TipoDocumentoTexto.objects.annotate(possui_documentos=Exists(subquery_modelos_com_documentos))
            .filter(possui_documentos=True)
            .order_by('nome')
        )
        total_tipos = len(tipos)
        total_passos = total_tipos * len(CATEGORIAS_AMOSTRA)
        progresso_atual = 0

        self._emitir_status(f'Iniciando geracao da amostra: {total_tipos} tipo(s) de documento e {total_passos} caso(s) no total.')

        for tipo in tipos:
            for categoria, status, ordering in CATEGORIAS_AMOSTRA:
                documento = self._get_documento(tipo=tipo, status=status, ordering=ordering)
                rows.append(self._serialize_row(tipo, categoria, status, documento, base_url_antiga, base_url_nova))
                progresso_atual += 1
                self._emitir_progresso(
                    atual=progresso_atual,
                    total=total_passos,
                    tipo_nome=tipo.nome,
                    categoria=categoria,
                    documento=documento,
                )

        return rows

    def _emitir_status(self, mensagem):
        self.stdout.write(mensagem)
        self.stdout.flush()

    def _emitir_progresso(self, atual, total, tipo_nome, categoria, documento):
        percentual = (atual / total) * 100 if total else 100
        documento_info = f'documento_id={documento.id}' if documento else 'sem_documento'
        self._emitir_status(f'[{atual}/{total} | {percentual:6.2f}%] {tipo_nome} | {categoria} | {documento_info}')

    def _get_documento(self, tipo, status, ordering):
        return (
            DocumentoTexto.objects.select_related('modelo__tipo_documento_texto', 'usuario_criacao')
            .filter(modelo__tipo_documento_texto=tipo, status=status)
            .order_by(*ordering)
            .first()
        )

    def _serialize_row(self, tipo, categoria, status, documento, base_url_antiga, base_url_nova):
        """Serializa um documento em um dicionario com todas as URLs de interesse.

        Args:
            tipo: instancia de ``TipoDocumentoTexto``.
            categoria: identificador da categoria da amostra.
            status: codigo numerico do status do documento.
            documento: instancia de ``DocumentoTexto`` ou ``None``.
            base_url_antiga: URL base do ambiente antigo.
            base_url_nova: URL base do ambiente novo.

        Returns:
            ``dict`` com campos do documento, URLs relativas e absolutas.
        """
        row = {
            'tipo_documento_id': tipo.id,
            'tipo_documento_nome': tipo.nome,
            'categoria_amostra': categoria,
            'status_id': status,
            'status_nome': self._get_status_label(status),
            'documento_encontrado': bool(documento),
            'documento_id': '',
            'documento_identificador': '',
            'documento_data_criacao': '',
            'documento_data_ultima_modificacao': '',
            'documento_tamanho_corpo_bytes': '',
            'documento_tamanho_corpo_amigavel': '',
            'username_dono': '',
            'procedimento_edicao': self._get_procedimento_edicao(status),
            'url_visualizacao_rel': '',
            'url_pdf_rel': '',
            'url_edicao_rel': '',
            'url_clonar_rel': '',
            'url_edicao_clone_rel_template': '',
            'url_retornar_para_rascunho_rel': '',
            'url_visualizacao_antiga': '',
            'url_visualizacao_nova': '',
            'url_pdf_antiga': '',
            'url_pdf_nova': '',
            'url_edicao_antiga': '',
            'url_edicao_nova': '',
            'url_clonar_antiga': '',
            'url_clonar_nova': '',
            'url_edicao_clone_antiga_template': '',
            'url_edicao_clone_nova_template': '',
            'url_retornar_para_rascunho_antiga': '',
            'url_retornar_para_rascunho_nova': '',
        }

        if not documento:
            return row

        tamanho_corpo = len(documento.corpo.encode('utf-8')) if documento.corpo else 0
        url_visualizacao_rel = reverse('visualizar_documento', kwargs={'documento_id': documento.id})
        url_pdf_rel = reverse('imprimir_previa_pdf', kwargs={'documento_id': documento.id, 'orientacao': 'carta'})
        url_clonar_rel = self._build_documento_url('clonar_documento', documento.id)
        url_retornar_rel = reverse('retornar_para_rascunho', kwargs={'documento_id': documento.id})
        url_edicao_rel = '' if status == DocumentoStatus.STATUS_FINALIZADO else reverse('editar_documento', kwargs={'documento_id': documento.id})
        url_edicao_clone_rel_template = (
            self._build_documento_url('editar_documento', '<clone_id>') if status == DocumentoStatus.STATUS_FINALIZADO else ''
        )

        row.update(
            {
                'documento_id': documento.id,
                'documento_identificador': documento.identificador,
                'documento_data_criacao': documento.data_criacao.isoformat() if documento.data_criacao else '',
                'documento_data_ultima_modificacao': (documento.data_ultima_modificacao.isoformat() if documento.data_ultima_modificacao else ''),
                'documento_tamanho_corpo_bytes': tamanho_corpo,
                'documento_tamanho_corpo_amigavel': filesizeformat(tamanho_corpo),
                'username_dono': documento.usuario_criacao.username if documento.usuario_criacao else '',
                'url_visualizacao_rel': url_visualizacao_rel,
                'url_pdf_rel': url_pdf_rel,
                'url_edicao_rel': url_edicao_rel,
                'url_clonar_rel': url_clonar_rel,
                'url_edicao_clone_rel_template': url_edicao_clone_rel_template,
                'url_retornar_para_rascunho_rel': url_retornar_rel,
                'url_visualizacao_antiga': self._join(base_url_antiga, url_visualizacao_rel),
                'url_visualizacao_nova': self._join(base_url_nova, url_visualizacao_rel),
                'url_pdf_antiga': self._join(base_url_antiga, url_pdf_rel),
                'url_pdf_nova': self._join(base_url_nova, url_pdf_rel),
                'url_edicao_antiga': self._join(base_url_antiga, url_edicao_rel),
                'url_edicao_nova': self._join(base_url_nova, url_edicao_rel),
                'url_clonar_antiga': self._join(base_url_antiga, url_clonar_rel),
                'url_clonar_nova': self._join(base_url_nova, url_clonar_rel),
                'url_edicao_clone_antiga_template': self._join(base_url_antiga, url_edicao_clone_rel_template),
                'url_edicao_clone_nova_template': self._join(base_url_nova, url_edicao_clone_rel_template),
                'url_retornar_para_rascunho_antiga': self._join(base_url_antiga, url_retornar_rel),
                'url_retornar_para_rascunho_nova': self._join(base_url_nova, url_retornar_rel),
            }
        )
        return row

    def _get_status_label(self, status):
        return dict(DocumentoStatus.STATUS_CHOICES)[status]

    def _get_procedimento_edicao(self, status):
        if status == DocumentoStatus.STATUS_CONCLUIDO:
            return 'retornar_para_rascunho -> editar_documento'
        if status == DocumentoStatus.STATUS_FINALIZADO:
            return 'clonar_documento -> abrir edicao do clone'
        return 'editar_documento'

    def _normalize_base_url(self, url):
        return url.rstrip('/') if url else ''

    def _build_documento_url(self, operacao, documento_id):
        return f'/documento_eletronico/{operacao}/{documento_id}/'

    def _join(self, base_url, relative_url):
        if not base_url or not relative_url:
            return ''
        return f'{base_url}{relative_url}'

    def _write_output(self, rows, output_file, formato):
        """Escreve a amostra em disco no formato escolhido.

        Args:
            rows: lista de dicionarios com os dados da amostra.
            output_file: caminho do arquivo de saida.
            formato: ``'csv'`` ou ``'json'``.

        Raises:
            IndexError: se ``formato`` for ``'csv'`` e ``rows`` estiver vazio.
        """
        path = Path(output_file)
        path.parent.mkdir(parents=True, exist_ok=True)

        if formato == 'json':
            path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + '\n')
            return

        fieldnames = list(rows[0].keys()) if rows else []
        with path.open('w', newline='') as fp:
            writer = csv.DictWriter(fp, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
