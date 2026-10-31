from __future__ import annotations

import datetime
from collections import defaultdict
from typing import Any

from django.db import transaction
from django.db.models import Q, QuerySet

from djtools.management.commands import BaseCommandPlus
from edu.models import AtividadeCurricularExtensao, MatriculaDiario, VinculacaoAtividadeExtensao


class Command(BaseCommandPlus):
    help = (
        'Identifica e corrige casos de vinculações de atividades curriculares de extensão '
        'cuja carga horária homologada excede a exigida pelo componente curricular do diário '
        '(ex.: view /edu/atividadecurricularextensao/<id>/distribuir/).'
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            '--commit',
            action='store_true',
            help='Aplica as alterações no banco de dados. Sem esta flag, executa em modo diagnóstico (dry-run).',
        )
        parser.add_argument(
            '--incluir-pendentes',
            action='store_true',
            help='Também inclui e ajusta vinculações pendentes de homologação (por padrão, avalia apenas homologadas).',
        )
        parser.add_argument(
            '--atividade',
            type=int,
            help='Filtra por ID específico de AtividadeCurricularExtensao (ex.: 3214).',
        )
        parser.add_argument(
            '--aluno',
            type=str,
            help='Filtra por matrícula do aluno.',
        )

    def _obter_queryset_vinculacoes(self, options: dict[str, Any]) -> QuerySet[VinculacaoAtividadeExtensao]:
        qs = VinculacaoAtividadeExtensao.objects.select_related(
            'atividade_extensao__matricula_periodo__aluno',
            'matricula_diario__diario__ano_letivo',
            'matricula_diario__diario__componente_curricular__componente',
            'matricula_diario__diario__componente_curricular__componente_curricular_associado__componente',
        )
        if not options.get('incluir_pendentes'):
            qs = qs.filter(homologada=True)
        else:
            qs = qs.exclude(homologada=False)

        atividade_id = options.get('atividade')
        if atividade_id:
            md_ids = VinculacaoAtividadeExtensao.objects.filter(atividade_extensao_id=atividade_id).values_list('matricula_diario_id', flat=True)
            qs = qs.filter(matricula_diario_id__in=md_ids)

        aluno_filtro = options.get('aluno')
        if aluno_filtro:
            filtro_aluno = Q(matricula_diario__matricula_periodo__aluno__matricula=aluno_filtro)
            qs = qs.filter(filtro_aluno)

        return qs

    @staticmethod
    def _ordenar_vinculacoes(vinculacoes: list[VinculacaoAtividadeExtensao]) -> list[VinculacaoAtividadeExtensao]:
        def sort_key(v: VinculacaoAtividadeExtensao) -> tuple[int, datetime.datetime, int]:
            status_order = 0 if v.homologada is True else 1
            data_homologacao = v.data_homologacao or datetime.datetime.min
            return (status_order, data_homologacao, v.id or 0)

        return sorted(vinculacoes, key=sort_key)

    @staticmethod
    def _calcular_ajustes_matricula_diario(
        vinculacoes: list[VinculacaoAtividadeExtensao],
        ch_exigida: int,
    ) -> list[dict[str, Any]]:
        ajustes: list[dict[str, Any]] = []
        saldo_restante = ch_exigida

        for v in vinculacoes:
            ch_permitida = min(v.carga_horaria, saldo_restante)
            saldo_restante -= ch_permitida

            if ch_permitida < v.carga_horaria:
                ajustes.append(
                    {
                        'vinculacao': v,
                        'ch_anterior': v.carga_horaria,
                        'ch_nova': ch_permitida,
                        'remover': ch_permitida == 0,
                    }
                )

        return ajustes

    def _imprimir_relatorio_caso(
        self,
        md: MatriculaDiario,
        ch_exigida: int,
        soma_ch: int,
        ajustes: list[dict[str, Any]],
    ) -> None:
        aluno = md.matricula_periodo.aluno
        diario = md.diario
        cc = diario.componente_curricular
        excesso = soma_ch - ch_exigida

        self.stdout.write(f'\nMatrícula Diário: {md.id} | Aluno: {aluno.matricula} - {aluno}')
        self.stdout.write(
            f'Componente: {cc.componente.sigla} - {cc.componente.descricao_historico} ({diario.ano_letivo.ano}.{diario.periodo_letivo})'
        )
        self.stdout.write(f'CH Exigida pela Disciplina: {ch_exigida}h | CH Vinculada Atual: {soma_ch}h (Excesso: {excesso}h)')
        self.stdout.write('  Vinculações afetadas:')

        for aj in ajustes:
            v: VinculacaoAtividadeExtensao = aj['vinculacao']
            atv_id = v.atividade_extensao_id
            url_distribuir = f'/edu/atividadecurricularextensao/{atv_id}/distribuir/'
            status = 'Homologada' if v.homologada is True else 'Pendente'

            if aj['remover']:
                acao = f'REMOVER (0h permitida, devolvendo {aj["ch_anterior"]}h à atividade)'
            else:
                diferenca = aj['ch_anterior'] - aj['ch_nova']
                acao = f'{aj["ch_anterior"]}h -> {aj["ch_nova"]}h (liberando {diferenca}h)'

            self.stdout.write(f'    - Vinculação #{v.id} [{status}] | Atividade #{atv_id} ({url_distribuir})')
            self.stdout.write(f'      Ação: {acao}')

    def _executar_ajustes(self, ajustes_totais: list[dict[str, Any]], commit: bool) -> set[int]:
        atividades_afetadas: set[int] = set()

        for aj in ajustes_totais:
            v: VinculacaoAtividadeExtensao = aj['vinculacao']
            atividades_afetadas.add(v.atividade_extensao_id)

            if not commit:
                continue

            if aj['remover']:
                v.delete()
            else:
                v.carga_horaria = aj['ch_nova']
                v.save()

        if commit:
            for atv in AtividadeCurricularExtensao.objects.filter(id__in=atividades_afetadas):
                atv.recalcular_carga_horaria_vinculada(commit=True)

        return atividades_afetadas

    def _imprimir_cabecalho(self, commit: bool, incluir_pendentes: bool) -> None:
        self.stdout.write('=' * 80)
        self.stdout.write('Identificação de Carga Horária Excedente em Vinculações de Extensão')
        modo_str = 'EXECUÇÃO COM COMMIT (alterações serão aplicadas)' if commit else 'DIAGNÓSTICO (dry-run, somente leitura)'
        pendentes_str = 'Homologadas e Pendentes' if incluir_pendentes else 'Apenas Homologadas'
        self.stdout.write(f'Modo: {modo_str}')
        self.stdout.write(f'Escopo: {pendentes_str}')
        self.stdout.write('=' * 80)

    def _imprimir_resumo(
        self,
        total_casos: int,
        ajustes_totais: list[dict[str, Any]],
        atividades_afetadas: set[int],
        commit: bool,
    ) -> None:
        total_remover = sum(1 for aj in ajustes_totais if aj['remover'])
        total_alterar = len(ajustes_totais) - total_remover
        horas_liberadas = sum(aj['ch_anterior'] - aj['ch_nova'] for aj in ajustes_totais)

        self.stdout.write('\n' + '-' * 80)
        self.stdout.write('Resumo:')
        self.stdout.write(f'- Matrículas em diário com excesso: {total_casos}')
        self.stdout.write(f'- Vinculações a ajustar carga horária: {total_alterar}')
        self.stdout.write(f'- Vinculações a remover (excedente integral/0h): {total_remover}')
        self.stdout.write(f'- Total de horas excedentes liberadas: {horas_liberadas}h')
        self.stdout.write(f'- Atividades de extensão afetadas: {len(atividades_afetadas)}')
        self.stdout.write('-' * 80)

        if not commit:
            self.stdout.write('\n[DRY-RUN] Nenhuma alteração foi realizada. Para aplicar, execute com --commit.\n')
        else:
            self.stdout.write('\n[SUCESSO] Todas as alterações e recálculos de saldo foram concluídos no banco de dados.\n')

    def handle(self, *args: Any, **options: Any) -> None:
        commit = bool(options.get('commit'))
        incluir_pendentes = bool(options.get('incluir_pendentes'))

        self._imprimir_cabecalho(commit, incluir_pendentes)

        qs_vinc = self._obter_queryset_vinculacoes(options)
        vinc_por_md: dict[int, list[VinculacaoAtividadeExtensao]] = defaultdict(list)
        for v in qs_vinc:
            vinc_por_md[v.matricula_diario_id].append(v)

        total_casos = 0
        ajustes_totais: list[dict[str, Any]] = []

        with transaction.atomic():
            for vinculacoes_brutas in vinc_por_md.values():
                primeira = vinculacoes_brutas[0]
                md = primeira.matricula_diario
                ch_exigida = int(md.diario.componente_curricular.get_ch_extensao_exigida() or 0)
                if ch_exigida <= 0:
                    continue

                vinculacoes_ordenadas = self._ordenar_vinculacoes(vinculacoes_brutas)
                soma_ch = sum(v.carga_horaria for v in vinculacoes_ordenadas)
                if soma_ch <= ch_exigida:
                    continue

                ajustes = self._calcular_ajustes_matricula_diario(vinculacoes_ordenadas, ch_exigida)
                if not ajustes:
                    continue

                total_casos += 1
                ajustes_totais.extend(ajustes)
                self._imprimir_relatorio_caso(md, ch_exigida, soma_ch, ajustes)

            atividades_afetadas = self._executar_ajustes(ajustes_totais, commit=commit)

            if not commit:
                # Em dry-run, se houve transação aberta, faz rollback por precaução
                transaction.set_rollback(True)

        self._imprimir_resumo(total_casos, ajustes_totais, atividades_afetadas, commit)
