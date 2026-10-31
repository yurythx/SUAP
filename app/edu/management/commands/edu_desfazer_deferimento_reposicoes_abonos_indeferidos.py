from __future__ import annotations

from typing import Any

from django.db import transaction
from django.db.models import QuerySet

from djtools.management.commands import BaseCommandPlus
from edu.models import SolicitacaoReposicaoAtividade


class Command(BaseCommandPlus):
    help = 'Identifica e desfaz o deferimento de solicitações de reposição de atividade cujo abono de faltas associado foi avaliado como indeferido.'

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            '--commit',
            action='store_true',
            help='Aplica as alterações no banco de dados. Sem esta flag, executa em modo diagnóstico (dry-run).',
        )
        parser.add_argument(
            '--abono',
            type=int,
            help='Filtra por ID específico de AbonoFaltas.',
        )
        parser.add_argument(
            '--aluno',
            type=str,
            help='Filtra por matrícula do aluno.',
        )

    def _obter_solicitacoes_alvo(self, options: dict[str, Any]) -> QuerySet[SolicitacaoReposicaoAtividade]:
        qs = (
            SolicitacaoReposicaoAtividade.objects.filter(
                deferida=True,
                abono_faltas__deferido=False,
            )
            .select_related(
                'abono_faltas',
                'abono_faltas__aluno',
                'abono_faltas__aluno__pessoa_fisica',
                'item_configuracao_avaliacao',
                'item_configuracao_avaliacao__configuracao_avaliacao',
                'item_configuracao_avaliacao__configuracao_avaliacao__diario',
            )
            .order_by('abono_faltas_id', 'id')
        )

        abono_id = options.get('abono')
        if abono_id:
            qs = qs.filter(abono_faltas_id=abono_id)

        aluno_matricula = options.get('aluno')
        if aluno_matricula:
            qs = qs.filter(abono_faltas__aluno__matricula=aluno_matricula)

        return qs

    def _processar_solicitacoes(
        self,
        qs_solicitacoes: QuerySet[SolicitacaoReposicaoAtividade],
        commit: bool,
    ) -> list[dict[str, Any]]:
        casos_processados: list[dict[str, Any]] = []

        for sol in qs_solicitacoes:
            abono = sol.abono_faltas
            aluno = abono.aluno
            item = sol.item_configuracao_avaliacao
            diario = item.configuracao_avaliacao.diario

            casos_processados.append(
                {
                    'solicitacao_id': sol.id,
                    'abono_id': abono.id,
                    'aluno_matricula': aluno.matricula,
                    'aluno_nome': aluno.pessoa_fisica.nome,
                    'diario': str(diario),
                    'etapa': item.configuracao_avaliacao.etapa,
                    'atividade': f'{item.sigla} - {item.get_tipo_display()}',
                    'data_reposicao': sol.data_reposicao,
                }
            )

        if commit and qs_solicitacoes.exists():
            qs_solicitacoes.update(
                deferida=None,
                data_reposicao=None,
                avaliador=None,
                observacao=None,
            )

        return casos_processados

    def _imprimir_cabecalho(self, commit: bool) -> None:
        self.stdout.write('=' * 80)
        self.stdout.write('Desfazer Deferimento de Reposições de Atividade de Abonos Indeferidos')
        modo_str = 'EXECUÇÃO COM COMMIT (alterações serão aplicadas)' if commit else 'DIAGNÓSTICO (dry-run, somente leitura)'
        self.stdout.write(f'Modo: {modo_str}')
        self.stdout.write('=' * 80)

    def _imprimir_relatorio(self, casos: list[dict[str, Any]]) -> None:
        if not casos:
            self.stdout.write('\nNenhuma solicitação de reposição deferida com abono indeferido encontrada.')
            return

        self.stdout.write('\nSolicitações de reposição identificadas:')
        for caso in casos:
            data_rep_str = caso['data_reposicao'].strftime('%d/%m/%Y') if caso['data_reposicao'] else 'Sem agendamento'
            self.stdout.write(
                f'  - Solicitação #{caso["solicitacao_id"]} | Abono #{caso["abono_id"]} | Aluno: {caso["aluno_matricula"]} - {caso["aluno_nome"]}'
            )
            self.stdout.write(f'    Diário: {caso["diario"]} ({caso["etapa"]}ª Etapa) | Atividade: {caso["atividade"]} | Reposição: {data_rep_str}')

    def _imprimir_resumo(self, casos: list[dict[str, Any]], commit: bool) -> None:
        total_solicitacoes = len(casos)
        abonos_afetados = len({caso['abono_id'] for caso in casos})
        alunos_afetados = len({caso['aluno_matricula'] for caso in casos})

        self.stdout.write('\n' + '-' * 80)
        self.stdout.write('Resumo:')
        self.stdout.write(f'- Total de solicitações afetadas: {total_solicitacoes}')
        self.stdout.write(f'- Abonos indeferidos relacionados: {abonos_afetados}')
        self.stdout.write(f'- Alunos afetados: {alunos_afetados}')
        self.stdout.write('-' * 80)

        if not commit:
            self.stdout.write('\n[DRY-RUN] Nenhuma alteração foi realizada. Para aplicar, execute com --commit.\n')
        else:
            self.stdout.write('\n[SUCESSO] Todas as alterações foram concluídas com sucesso no banco de dados.\n')

    def handle(self, *args: Any, **options: Any) -> None:
        commit = bool(options.get('commit'))

        self._imprimir_cabecalho(commit)
        qs_solicitacoes = self._obter_solicitacoes_alvo(options)

        with transaction.atomic():
            casos = self._processar_solicitacoes(qs_solicitacoes, commit=commit)
            if not commit:
                transaction.set_rollback(True)

        self._imprimir_relatorio(casos)
        self._imprimir_resumo(casos, commit=commit)
