from __future__ import annotations

import os
from typing import Any

from django.core.management.base import CommandError

from djtools.management.commands import BaseCommandPlus
import edu.migracao
from edu.migracao import (
    ConsoleProgressHandler,
    ResultadoMigracao,
)

MAPA_IMPORTADORES: dict[str, tuple[str, str, str]] = {
    'matrizes': ('Matrizes Curriculares', 'ImportadorMatrizes', 'matrizes.csv'),
    'componentes': ('Componentes Curriculares', 'ImportadorComponentes', 'componentes.csv'),
    'cursos': ('Cursos e Vínculos com Matrizes', 'ImportadorCursos', 'cursos.csv'),
    'alunos': ('Alunos e Pessoas Físicas', 'ImportadorAlunos', 'alunos.csv'),
    'historicos': ('Históricos Escolares', 'ImportadorHistoricoAluno', 'historicos.csv'),
    'procedimentos': ('Procedimentos de Matrícula', 'ImportadorProcedimentoMatricula', 'procedimentos.csv'),
    'equivalencias': ('Equivalências', 'ImportadorEquivalencia', 'equivalencias.csv'),
    'inicializar_periodo': ('Inicialização de Período Letivo', 'ImportadorInicializarPeriodoLetivo', 'inicializar_periodo.csv'),
}

ORDEM_EXECUCAO_COMPLETA = [
    'matrizes',
    'componentes',
    'cursos',
    'alunos',
    'historicos',
    'procedimentos',
    'equivalencias',
    'inicializar_periodo',
]


class Command(BaseCommandPlus):
    help = 'Executa a migração ou validação de dados acadêmicos via arquivo CSV.'

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            'etapa',
            choices=[*MAPA_IMPORTADORES.keys(), 'all'],
            help='Etapa de migração a ser executada ou "all" para executar todas em sequência.',
        )
        parser.add_argument(
            'arquivo',
            nargs='?',
            default=None,
            help='Caminho para o arquivo CSV da etapa (obrigatório se não usar --diretorio).',
        )
        parser.add_argument(
            '--apenas-validar',
            action='store_true',
            dest='apenas_validar',
            default=False,
            help='Executa somente a validação dos dados sem persistir no banco.',
        )
        parser.add_argument(
            '--ignorar-obrigatorios',
            action='store_true',
            dest='ignorar_obrigatorios',
            default=False,
            help='Ignora a obrigatoriedade de campos opcionais durante a validação.',
        )
        parser.add_argument(
            '--diretorio',
            dest='diretorio',
            default=None,
            help='Diretório contendo os arquivos CSV das etapas (obrigatório para etapa "all").',
        )

    def _resolver_arquivo(self, etapa: str, arquivo: str | None, diretorio: str | None) -> str:
        if arquivo and os.path.exists(arquivo):
            return arquivo
        if diretorio and os.path.isdir(diretorio):
            padrao = MAPA_IMPORTADORES[etapa][2]
            candidato = os.path.join(diretorio, padrao)
            if os.path.exists(candidato):
                return candidato
        raise CommandError(
            f'Arquivo CSV para a etapa "{etapa}" não foi encontrado. '
            f'Especifique o caminho do arquivo ou use --diretorio com arquivos nomeados adequadamente.'
        )

    def _executar_etapa(
        self,
        etapa: str,
        caminho_arquivo: str,
        apenas_validar: bool,
        ignorar_obrigatorios: bool,
    ) -> ResultadoMigracao:
        nome_etapa, class_name, _ = MAPA_IMPORTADORES[etapa]
        self.stdout.write(self.style.MIGRATE_HEADING(f'=== Etapa: {nome_etapa} ({caminho_arquivo}) ==='))

        handler = ConsoleProgressHandler(stdout=self.stdout, stderr=self.stderr, style=self.style)
        importador_cls = getattr(edu.migracao, class_name)
        importador = importador_cls(
            caminho_arquivo,
            apenas_validar=apenas_validar,
            ignorar_obrigatorios=ignorar_obrigatorios,
            progress=handler,
        )
        return importador.run()

    def handle(self, *args: Any, **options: Any) -> None:
        etapa: str = options['etapa']
        arquivo: str | None = options.get('arquivo')
        diretorio: str | None = options.get('diretorio')
        apenas_validar: bool = options.get('apenas_validar', False)
        ignorar_obrigatorios: bool = options.get('ignorar_obrigatorios', False)

        if etapa == 'all':
            if not diretorio:
                raise CommandError('A opção --diretorio é obrigatória quando a etapa "all" for selecionada.')
            etapas_para_rodar = ORDEM_EXECUCAO_COMPLETA
        else:
            etapas_para_rodar = [etapa]

        erros_etapas: list[str] = []
        for e in etapas_para_rodar:
            caminho = self._resolver_arquivo(e, arquivo if etapa != 'all' else None, diretorio)
            resultado = self._executar_etapa(e, caminho, apenas_validar, ignorar_obrigatorios)
            if not resultado.sucesso:
                erros_etapas.append(f'Etapa {e}: {resultado.mensagem}')
                if not apenas_validar:
                    self.stderr.write(self.style.ERROR(f'Interrompendo pipeline na etapa "{e}" devido a erros.'))
                    break

        if erros_etapas:
            raise CommandError(f'Ocorreram erros na migração: {"; ".join(erros_etapas)}')

        self.stdout.write(self.style.SUCCESS('Operação de migração concluída com sucesso!'))
