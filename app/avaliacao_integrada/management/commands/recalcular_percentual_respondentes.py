# avaliacao_integrada/management/commands/recalcular_percentual_respondentes.py
from __future__ import annotations

import os

from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.db import transaction

from avaliacao_integrada.models import Respondente
from avaliacao_integrada.respondente_helper import RespondenteHelper

# tqdm opcional, com fallback “no-op”
try:
    from tqdm import tqdm
except Exception:  # pragma: no cover

    def tqdm(iterable=None, **_kwargs):
        return iterable if iterable is not None else []


class Command(BaseCommand):
    help = 'Recalcula o campo percentual_resposta dos respondentes, com processamento em lotes e suporte a retomada por checkpoint de PK.'

    # -------------------------
    # Argumentos de CLI
    # -------------------------
    def add_arguments(self, parser):
        parser.add_argument('--apenas-pendentes', action='store_true', default=False, help='Processa somente respondentes não finalizados.')
        parser.add_argument(
            '--apenas-finalizados-com-percentual-incompleto',
            action='store_true',
            default=False,
            help='Processa somente respondentes finalizados com percentual menor que 100.',
        )
        parser.add_argument('--incluir-opcionais', action='store_true', default=False, help='Considera também indicadores opcionais no cálculo.')
        parser.add_argument('--incluir-automaticos', action='store_true', default=False, help='Considera também indicadores automáticos no cálculo.')
        parser.add_argument('--chunk-size', type=int, default=5000, help='Tamanho do lote usado em iterator()/bulk_update.')

        # Retomada
        parser.add_argument('--resume', action='store_true', default=True, help='Retoma a execução a partir do último checkpoint de PK salvo.')
        parser.add_argument(
            '--resume-key', type=str, default='', help=('Identificador do checkpoint. Se omitido, será gerado automaticamente a partir das flags.')
        )
        parser.add_argument('--reset', action='store_true', default=False, help='Limpa o checkpoint antes de iniciar (começa do início).')
        parser.add_argument(
            '--state-file',
            type=str,
            default='',
            help='Caminho de arquivo para persistir o checkpoint (opcional). Se não informado, usa cache do Django.',
        )

    # -------------------------
    # Utilidades de checkpoint
    # -------------------------
    @staticmethod
    def _make_resume_key(opts) -> str:
        """
        Gera uma chave padrão de checkpoint a partir das opções que
        definem o subconjunto de processamento. chunk-size não entra,
        pois não altera o conjunto-alvo.
        """
        base = 'recalc_percentual_respondentes'
        parts = [
            f'pendentes={int(bool(opts["apenas_pendentes"]))}',
            f'opc={int(bool(opts["incluir_opcionais"]))}',
            f'auto={int(bool(opts["incluir_automaticos"]))}',
        ]
        auto_key = f'{base}:' + ','.join(parts)
        return opts['resume_key'] or auto_key

    @staticmethod
    def _read_checkpoint_from_file(path: str) -> int:
        try:
            if not path or not os.path.exists(path):
                return 0
            with open(path, encoding='utf-8') as f:
                raw = f.read().strip()
            return int(raw) if raw else 0
        except Exception:
            return 0

    @staticmethod
    def _write_checkpoint_to_file(path: str, last_pk: int) -> None:
        if not path:
            return
        # cria diretório se necessário
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(str(int(last_pk)))

    @staticmethod
    def _clear_checkpoint_file(path: str) -> None:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass

    @staticmethod
    def _read_checkpoint_from_cache(key: str) -> int:
        return int(cache.get(key) or 0)

    @staticmethod
    def _write_checkpoint_to_cache(key: str, last_pk: int) -> None:
        # TTL opcional: None => indefinido (depende do backend)
        cache.set(key, int(last_pk), timeout=None)

    @staticmethod
    def _clear_checkpoint_cache(key: str) -> None:
        cache.delete(key)

    def _load_checkpoint(self, use_file: bool, state_file: str, cache_key: str) -> int:
        return self._read_checkpoint_from_file(state_file) if use_file else self._read_checkpoint_from_cache(cache_key)

    def _save_checkpoint(self, use_file: bool, state_file: str, cache_key: str, last_pk: int) -> None:
        if use_file:
            self._write_checkpoint_to_file(state_file, last_pk)
        else:
            self._write_checkpoint_to_cache(cache_key, last_pk)

    def _clear_checkpoint(self, use_file: bool, state_file: str, cache_key: str) -> None:
        if use_file:
            self._clear_checkpoint_file(state_file)
        else:
            self._clear_checkpoint_cache(cache_key)

    # -------------------------
    # Barra de progresso (tqdm)
    # -------------------------
    @staticmethod
    def _progress_iter(iterable, total: int | None = None, desc: str = ''):
        return tqdm(iterable, total=total, desc=desc, unit='it')

    # -------------------------
    # Processamento por lote
    # -------------------------
    def _processar_lote(self, lote: list, excluir_automatico: bool, ignorar_opcionais: bool, chunk_size: int):
        """
        Calcula percentuais do lote e retorna a lista de objetos modificados,
        prontos para persistência via bulk_update. Também garante finalizado=True
        quando pct==100.
        """
        respondentes_a_atualizar = []

        for r in self._progress_iter(lote, total=len(lote), desc='Lote'):
            # 1) curto-circuitos
            if r.finalizado and r.percentual_resposta == 100:
                continue

            alterado = False
            if r.finalizado and r.percentual_resposta != 100:
                r.percentual_resposta = 100
                alterado = True
                respondentes_a_atualizar.append(r)
                continue

            if not r.finalizado and r.percentual_resposta == 100:
                r.finalizado = True
                alterado = True
                respondentes_a_atualizar.append(r)
                continue

            # 2) cálculo só quando necessário
            # Cálculo com cache local + Redis
            pct = RespondenteHelper.percentual_respondido(
                r,
                excluir_automatico=excluir_automatico,
                ignorar_opcionais=ignorar_opcionais,
                cache_local=self._base_ids_local,  # <<<<<< cache local "quente"
            )

            if r.finalizado:
                pct = 100

            pct = max(0, min(100, int(pct)))
            if pct != r.percentual_resposta:
                r.percentual_resposta = pct
                alterado = True
            if pct == 100 and not r.finalizado:
                r.finalizado = True
                alterado = True

            if alterado:
                respondentes_a_atualizar.append(r)

        # persistência feita pelo chamador (que controla a transação e o checkpoint)
        return respondentes_a_atualizar

    # -------------------------
    # Fluxo principal
    # -------------------------
    def handle(self, *args, **opts):
        # Dicionário de cache local por execução
        self._base_ids_local: dict = {}

        # 1) Preparação do queryset
        qs = Respondente.objects.all()
        if opts['apenas_finalizados_com_percentual_incompleto']:
            qs = qs.filter(finalizado=True, percentual_resposta__lt=100)
        if opts['apenas_pendentes']:
            qs = qs.filter(finalizado=False)

        # carregar somente campos necessários e evitar N+1
        # Ordem determinística para retomar por PK
        qs = (
            qs.only('id', 'finalizado', 'percentual_resposta', 'avaliacao', 'segmento', 'uo', 'user')
            .select_related('avaliacao', 'segmento', 'uo', 'user')
            .prefetch_related('avaliacao__modalidades')  # evita N+1 para modalidades
            # ordenação “amiga do cache” (e checkpoint por pk ao final)
            .order_by('avaliacao_id', 'segmento_id', 'uo_id', 'pk')
            # chave do cache -> por último pk
        )

        # 2) Chave e backend do checkpoint
        resume_key = self._make_resume_key(opts)
        use_file = bool(opts['state_file'])
        cache_key = f'{resume_key}'
        state_file = opts['state_file']

        # 3) Reset explícito
        if opts['reset']:
            self._clear_checkpoint(use_file, state_file, cache_key)
            self.stdout.write(self.style.WARNING('Checkpoint limpo (--reset).'))

        # 4) Retomada (se habilitada)
        last_pk = 0
        if opts['resume']:
            last_pk = self._load_checkpoint(use_file, state_file, cache_key)
            if last_pk > 0:
                qs = qs.filter(pk__gt=last_pk)
                self.stdout.write(self.style.WARNING(f'Retomando a partir de pk > {last_pk} (resume-key="{resume_key}").'))
            else:
                self.stdout.write(self.style.WARNING('Nenhum checkpoint encontrado; iniciando do começo.'))

        total = qs.count()
        if total == 0:
            self.stdout.write(self.style.WARNING('Nenhum respondente a processar.'))
            return

        self.stdout.write(f'Processando {total} respondente(s)...')

        excluir_automatico = opts['incluir_automaticos']
        ignorar_opcionais = opts['incluir_opcionais']
        chunk_size = int(opts['chunk_size'])

        buffer = []
        processados = 0
        max_pk_processado = last_pk

        # 5) Iteração com checkpoint por lote
        for r in qs.iterator(chunk_size=chunk_size):
            buffer.append(r)
            if r.pk and r.pk > max_pk_processado:
                max_pk_processado = r.pk

            if len(buffer) >= chunk_size:
                with transaction.atomic():
                    modificados = self._processar_lote(buffer, excluir_automatico, ignorar_opcionais, chunk_size)
                    if modificados:
                        self.stdout.write(f'... Persistindo {len(modificados)} alteração(ões)...')
                        Respondente.objects.bulk_update(modificados, ['percentual_resposta', 'finalizado'], batch_size=chunk_size)
                processados += len(buffer)
                buffer.clear()

                # checkpoint após lote confirmado
                self._save_checkpoint(use_file, state_file, cache_key, max_pk_processado)

                # progresso textual adicional a cada ~1000
                if processados % 1000 == 0:
                    self.stdout.write(f'... {processados} processado(s); checkpoint=pk {max_pk_processado}')

        # 6) Lote final (resto)
        if buffer:
            with transaction.atomic():
                modificados = self._processar_lote(buffer, excluir_automatico, ignorar_opcionais, chunk_size)
                if modificados:
                    Respondente.objects.bulk_update(modificados, ['percentual_resposta', 'finalizado'], batch_size=chunk_size)
            processados += len(buffer)
            buffer.clear()

            # checkpoint final
            self._save_checkpoint(use_file, state_file, cache_key, max_pk_processado)

        # 7) Conclusão (limpa checkpoint para rodadas futuras “do zero”)
        self._clear_checkpoint(use_file, state_file, cache_key)
        self.stdout.write(self.style.SUCCESS(f'Concluído. Processados: {processados}. Último pk={max_pk_processado}.'))
