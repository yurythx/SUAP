from __future__ import annotations

from typing import Any

from django.db import transaction
from django.db.models import Q, QuerySet

from djtools.management.commands import BaseCommandPlus
from edu.models import (
    ProcedimentoMatricula,
    Requerimento,
    RequerimentoAproveitamentoEstudo,
    SituacaoMatricula,
    SolicitacaoAproveitamentoEstudo,
)

SITUACOES_CANCELAMENTO_VINCULO = (
    SituacaoMatricula.CANCELAMENTO_COMPULSORIO,
    SituacaoMatricula.CANCELADO,
    SituacaoMatricula.CANCELAMENTO_POR_DUPLICIDADE,
    SituacaoMatricula.CANCELAMENTO_POR_DESLIGAMENTO,
    SituacaoMatricula.EVASAO,
    SituacaoMatricula.JUBILADO,
)


class Command(BaseCommandPlus):
    help = (
        'Indefere retroativamente requerimentos automatizados pendentes de alunos com vínculo cancelado '
        'e higieniza solicitações de aproveitamento de estudo que permaneceram em aberto em requerimentos já indeferidos.'
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            '--commit',
            action='store_true',
            help='Aplica as alterações no banco de dados. Sem esta flag, executa em modo diagnóstico (dry-run).',
        )
        parser.add_argument(
            '--notificar',
            action='store_true',
            help='Envia e-mails de notificação ao indeferir os requerimentos (padrão é não notificar).',
        )
        parser.add_argument(
            '--aluno',
            type=str,
            help='Filtra por matrícula do aluno.',
        )
        parser.add_argument(
            '--requerimento',
            type=int,
            help='Filtra por ID específico de Requerimento.',
        )

    @staticmethod
    def _obter_tipos_automatizados_alvo() -> list[int]:
        tipos_ignorados = (
            Requerimento.MATRICULA_QUEBRA_REQUISITO,
            Requerimento.MATRICULA_QUEBRA_CH_MAX,
        )
        return [choice[0] for choice in Requerimento.TIPO_AUTOMATIZADO_CHOICES if choice[0] not in tipos_ignorados]

    @staticmethod
    def _aplicar_filtros(
        qs: QuerySet[Any],
        options: dict[str, Any],
        campo_aluno: str = 'aluno',
        campo_req: str = 'id',
    ) -> QuerySet[Any]:
        aluno_filtro = options.get('aluno')
        if aluno_filtro:
            filtro_aluno = Q(**{f'{campo_aluno}__matricula': aluno_filtro})
            qs = qs.filter(filtro_aluno)

        req_id = options.get('requerimento')
        if req_id:
            qs = qs.filter(**{campo_req: req_id})

        return qs

    def _obter_requerimentos_pendentes(self, options: dict[str, Any]) -> QuerySet[Requerimento]:
        tipos_alvo = self._obter_tipos_automatizados_alvo()
        qs = (
            Requerimento.objects.filter(
                tipo__in=tipos_alvo,
                deferido__isnull=True,
                aluno__situacao_id__in=SITUACOES_CANCELAMENTO_VINCULO,
            )
            .exclude(situacao=Requerimento.SITUACAO_ARQUIVADO)
            .select_related('aluno', 'aluno__situacao')
            .order_by('aluno_id', 'id')
        )
        return self._aplicar_filtros(qs, options, campo_aluno='aluno', campo_req='id')

    @staticmethod
    def _obter_ultimo_procedimento(aluno_id: int) -> ProcedimentoMatricula | None:
        return (
            ProcedimentoMatricula.objects.filter(matricula_periodo__aluno_id=aluno_id)
            .select_related('matricula_periodo__ano_letivo')
            .order_by('-data', '-id')
            .first()
        )

    def _obter_requerimentos_aproveitamento_ja_indeferidos(self, options: dict[str, Any]) -> QuerySet[RequerimentoAproveitamentoEstudo]:
        req_ids = (
            SolicitacaoAproveitamentoEstudo.objects.filter(
                requerimento__tipo=Requerimento.APROVEITAMENTO_ESTUDO,
                requerimento__situacao=Requerimento.SITUACAO_ARQUIVADO,
                requerimento__deferido=False,
                situacao__in=[
                    SolicitacaoAproveitamentoEstudo.SITUACAO_CADASTRADA,
                    SolicitacaoAproveitamentoEstudo.SITUACAO_SOLICITADA,
                    SolicitacaoAproveitamentoEstudo.SITUACAO_EM_ANALISE,
                ],
            )
            .values_list('requerimento_id', flat=True)
            .distinct()
        )
        qs = RequerimentoAproveitamentoEstudo.objects.filter(id__in=req_ids).select_related('aluno').order_by('id')
        return self._aplicar_filtros(qs, options, campo_aluno='aluno', campo_req='id')

    def _processar_requerimentos_pendentes(
        self,
        qs_reqs: QuerySet[Requerimento],
        commit: bool,
        notificar: bool,
    ) -> list[dict[str, Any]]:
        casos_processados: list[dict[str, Any]] = []
        cache_ultimos_procedimentos: dict[int, ProcedimentoMatricula | None] = {}

        for req in qs_reqs:
            aluno = req.aluno
            if aluno.id not in cache_ultimos_procedimentos:
                cache_ultimos_procedimentos[aluno.id] = self._obter_ultimo_procedimento(aluno.id)

            ultimo_proc = cache_ultimos_procedimentos[aluno.id]
            if ultimo_proc is None or ultimo_proc.tipo not in ProcedimentoMatricula.TIPOS_CANCELAMENTO_VINCULO:
                continue

            mp = ultimo_proc.matricula_periodo
            obs = f'Requerimento indeferido automaticamente devido ao procedimento de {ultimo_proc.tipo} ({mp.ano_letivo}.{mp.periodo_letivo}).'

            qtd_solicitacoes = 0
            if req.tipo == Requerimento.APROVEITAMENTO_ESTUDO:
                qtd_solicitacoes = SolicitacaoAproveitamentoEstudo.objects.filter(
                    requerimento_id=req.id,
                    situacao__in=[
                        SolicitacaoAproveitamentoEstudo.SITUACAO_CADASTRADA,
                        SolicitacaoAproveitamentoEstudo.SITUACAO_SOLICITADA,
                        SolicitacaoAproveitamentoEstudo.SITUACAO_EM_ANALISE,
                    ],
                ).count()

            casos_processados.append(
                {
                    'requerimento': req,
                    'aluno': aluno,
                    'procedimento': ultimo_proc,
                    'observacao': obs,
                    'qtd_solicitacoes': qtd_solicitacoes,
                }
            )

            if commit:
                req.observacao = obs
                req.indeferir(atendente=None, notificar=notificar)

        return casos_processados

    @staticmethod
    def _processar_solicitacoes_orfas(
        qs_reqs: QuerySet[RequerimentoAproveitamentoEstudo],
        commit: bool,
    ) -> list[dict[str, Any]]:
        casos_orfaos: list[dict[str, Any]] = []

        for req in qs_reqs:
            qtd_solicitacoes = SolicitacaoAproveitamentoEstudo.objects.filter(
                requerimento_id=req.id,
                situacao__in=[
                    SolicitacaoAproveitamentoEstudo.SITUACAO_CADASTRADA,
                    SolicitacaoAproveitamentoEstudo.SITUACAO_SOLICITADA,
                    SolicitacaoAproveitamentoEstudo.SITUACAO_EM_ANALISE,
                ],
            ).count()

            casos_orfaos.append(
                {
                    'requerimento': req,
                    'aluno': req.aluno,
                    'qtd_solicitacoes': qtd_solicitacoes,
                }
            )

            if commit:
                req.indeferir_solicitacoes_aproveitamento_pendentes()

        return casos_orfaos

    def _imprimir_cabecalho(self, commit: bool, notificar: bool) -> None:
        self.stdout.write('=' * 80)
        self.stdout.write('Indeferimento Retroativo de Requerimentos de Vínculos Cancelados')
        modo_str = 'EXECUÇÃO COM COMMIT (alterações serão aplicadas)' if commit else 'DIAGNÓSTICO (dry-run, somente leitura)'
        notif_str = 'Ativada (e-mails serão enviados)' if notificar else 'Desativada (sem envio de e-mails)'
        self.stdout.write(f'Modo: {modo_str}')
        self.stdout.write(f'Notificação: {notif_str}')
        self.stdout.write('=' * 80)

    def _imprimir_relatorio_casos_pendentes(self, casos: list[dict[str, Any]]) -> None:
        if not casos:
            return

        self.stdout.write('\n[1] Requerimentos automatizados pendentes de alunos com vínculo cancelado:')
        for caso in casos:
            req: Requerimento = caso['requerimento']
            aluno = caso['aluno']
            proc: ProcedimentoMatricula = caso['procedimento']
            mp = proc.matricula_periodo
            extra_sol = f' (e {caso["qtd_solicitacoes"]} solicitações filhas)' if caso['qtd_solicitacoes'] else ''
            self.stdout.write(f'  - Requerimento #{req.id} [{req.get_tipo_display()}] | Aluno: {aluno.matricula} - {aluno}')
            self.stdout.write(f'    Vínculo: {aluno.situacao} | Último Procedimento: {proc.tipo} ({mp.ano_letivo}.{mp.periodo_letivo}){extra_sol}')

    def _imprimir_relatorio_casos_orfaos(self, casos: list[dict[str, Any]]) -> None:
        if not casos:
            return

        self.stdout.write('\n[2] Solicitações de aproveitamento órfãs em requerimentos já indeferidos:')
        for caso in casos:
            req: RequerimentoAproveitamentoEstudo = caso['requerimento']
            aluno = caso['aluno']
            self.stdout.write(f'  - Requerimento #{req.id} [Aproveitamento de Estudos] | Aluno: {aluno.matricula} - {aluno}')
            self.stdout.write(f'    Solicitações filhas pendentes a indeferir: {caso["qtd_solicitacoes"]}')

    def _imprimir_resumo(
        self,
        casos_pendentes: list[dict[str, Any]],
        casos_orfaos: list[dict[str, Any]],
        commit: bool,
    ) -> None:
        total_reqs_pendentes = len(casos_pendentes)
        alunos_pendentes = len({caso['aluno'].id for caso in casos_pendentes})
        solicitacoes_pendentes = sum(caso['qtd_solicitacoes'] for caso in casos_pendentes)

        total_reqs_orfaos = len(casos_orfaos)
        solicitacoes_orfas = sum(caso['qtd_solicitacoes'] for caso in casos_orfaos)

        self.stdout.write('\n' + '-' * 80)
        self.stdout.write('Resumo:')
        self.stdout.write(f'- Requerimentos automatizados pendentes indeferidos: {total_reqs_pendentes}')
        self.stdout.write(f'  - Alunos distintos afetados: {alunos_pendentes}')
        self.stdout.write(f'  - Solicitações filhas de aproveitamento indeferidas em cascata: {solicitacoes_pendentes}')
        self.stdout.write(f'- Requerimentos já indeferidos com solicitações órfãs higienizadas: {total_reqs_orfaos}')
        self.stdout.write(f'  - Total de solicitações órfãs indeferidas: {solicitacoes_orfas}')
        self.stdout.write('-' * 80)

        if not commit:
            self.stdout.write('\n[DRY-RUN] Nenhuma alteração foi realizada. Para aplicar, execute com --commit.\n')
        else:
            self.stdout.write('\n[SUCESSO] Todas as alterações foram concluídas com sucesso no banco de dados.\n')

    def handle(self, *args: Any, **options: Any) -> None:
        commit = bool(options.get('commit'))
        notificar = bool(options.get('notificar'))

        self._imprimir_cabecalho(commit, notificar)

        qs_pendentes = self._obter_requerimentos_pendentes(options)
        qs_orfaos = self._obter_requerimentos_aproveitamento_ja_indeferidos(options)

        with transaction.atomic():
            casos_pendentes = self._processar_requerimentos_pendentes(qs_pendentes, commit=commit, notificar=notificar)
            casos_orfaos = self._processar_solicitacoes_orfas(qs_orfaos, commit=commit)

            if not commit:
                transaction.set_rollback(True)

        self._imprimir_relatorio_casos_pendentes(casos_pendentes)
        self._imprimir_relatorio_casos_orfaos(casos_orfaos)
        self._imprimir_resumo(casos_pendentes, casos_orfaos, commit=commit)
