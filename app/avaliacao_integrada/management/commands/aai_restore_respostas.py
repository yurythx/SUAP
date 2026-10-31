#
# **PayloadIO**: lida com leitura/validação/escrita/backup — sem regras de negócio.
# **IdentityResolver / IndexCache**: encapsulam a identidade (externa) e a construção de índices, isolando um ponto fácil de otimizar/trocar.
# **AAIDumper**: só exporta; pode ser testado isoladamente.
# **AAILoader**: contém as regras do restore, separadas em “respondentes” e “respostas”, com contadores e short-circuit por exists().
# **SequenceAdjuster**: único lugar que fala com metadados do Postgres.
# **AAIInspector**: imprime comparativos completos (todos os campos) por matrícula.
# **TablePrinter**: utilidade reusável para tabelas legíveis no terminal.
# **Command**: fica mínimo, só orquestra.
#
from __future__ import annotations

from logging.handlers import RotatingFileHandler

import logging

import json
import os
import re
from dataclasses import dataclass, is_dataclass, asdict
from pathlib import Path
from typing import Any
from collections.abc import Callable

from tqdm import tqdm

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from avaliacao_integrada.models import Avaliacao, Segmento, Respondente, Resposta
from comum.models import User


LOGGER_NAME = __name__
AAI_LOG_LEVEL = os.getenv('AAI_LOG_LEVEL', 'DEBUG')
AAI_LOG_PATH = Path(getattr(settings, 'BASE_DIR', '.')) / 'deploy' / 'logs' / 'aai' / 'aai_restore.log'


def _configure_module_logger(to_console: bool = False) -> logging.Logger:
    """
    Configura o logger local do módulo:
      - adiciona RotatingFileHandler (10MB, 5 backups) em deploy/logs/aai/aai_restore.log
      - define formatter verboso
      - impede propagação para o root (não aparece no console)
      - evita duplicar handlers se chamado mais de uma vez
    Se `to_console=True`, mantém console; caso contrário, remove handlers de console (se houver).
    """
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(AAI_LOG_LEVEL)

    # Formatter único
    fmt = logging.Formatter(fmt='[%(levelname)s %(asctime)s %(filename)s:%(lineno)d - %(funcName)s()] >>> """%(message)s"""')

    # Garante pasta
    AAI_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Evita duplicar o file handler (marcamos com um atributo sentinela)
    has_file = any(getattr(h, '_aai_restore_file', False) for h in logger.handlers)
    if not has_file:
        fh = RotatingFileHandler(
            filename=str(AAI_LOG_PATH),
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding='utf-8',
        )
        fh.setLevel(AAI_LOG_LEVEL)
        fh.setFormatter(fmt)
        fh._aai_restore_file = True  # sentinela
        logger.addHandler(fh)

    if not to_console:
        # Remove handlers de console já anexados a este logger (se houver)
        for h in list(logger.handlers):
            if isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler):
                logger.removeHandler(h)

    # Não propagar para o root→evita console (e outros handlers globais)
    logger.propagate = False
    return logger


# logger de módulo para usar em todo o arquivo
logger = _configure_module_logger(to_console=False)


# =========================
# Config e tipos
# =========================
AVALIACAO_ID_ALVO = 26

IndicesUser = dict[tuple[int, int, int], int]  # (avaliacao_id, segmento_id, user_id) -> respondente_id
IndicesExt = dict[tuple[int, int, str, str], int]  # (avaliacao_id, segmento_id, tipo, valor) -> respondente_id


# =========================
# Utilitários de impressão
# =========================
class TablePrinter:
    def __init__(self, stdout):
        self.stdout = stdout

    @staticmethod
    def trim(v, maxlen=40):
        s = '' if v is None else str(v)
        return s if len(s) <= maxlen else s[: maxlen - 1] + '…'

    def print_table(self, headers, rows, max_widths=None):
        if max_widths:
            trimmed_rows = []
            for row in rows:
                trimmed = []
                for i, cell in enumerate(row):
                    mw = max_widths[i] if i < len(max_widths) else None
                    trimmed.append(self.trim(cell, mw) if mw else ('' if cell is None else cell))
                trimmed_rows.append(trimmed)
            rows = trimmed_rows
        else:
            rows = [[('' if c is None else c) for c in row] for row in rows]

        widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                widths[i] = max(widths[i], len(str(cell)))

        line = ' | '.join(h.ljust(widths[i]) for i, h in enumerate(headers))
        sep = '-+-'.join('-' * widths[i] for i, _ in enumerate(headers))
        self.stdout.write(line)
        self.stdout.write(sep)
        for row in rows:
            self.stdout.write(' | '.join(str(row[i]).ljust(widths[i]) for i in range(len(headers))))
        self.stdout.write('')


# =========================
# IO do payload / backup
# =========================
class PayloadIO:
    def __init__(self, avaliacao_id: int):
        self.avaliacao_id = avaliacao_id

    def read_and_validate(self, file_path: str) -> dict:
        if not os.path.exists(file_path):
            raise CommandError(f'Arquivo não encontrado: {file_path}')
        with open(file_path, encoding='utf-8') as f:
            payload = json.load(f)
        try:
            avaliacao_id_meta = int(payload.get('meta', {}).get('avaliacao_id'))
        except Exception as exc:
            raise CommandError('Arquivo inválido: meta.avaliacao_id ausente ou não numérico.') from exc
        if avaliacao_id_meta != self.avaliacao_id:
            raise CommandError(f'Arquivo não corresponde à avaliação alvo (ID={self.avaliacao_id}).')
        return payload

    @staticmethod
    def extract_lists(payload: dict) -> tuple[list[dict], list[dict]]:
        r1 = payload.get('respondentes', [])
        r2 = payload.get('respostas', [])
        return (list(r1) if isinstance(r1, list) else []), (list(r2) if isinstance(r2, list) else [])

    def make_backup_path(self, base_dir: str | Path | None = None) -> str:
        ts = timezone.now().strftime('%Y%m%d-%H%M%S')
        root = Path(base_dir or getattr(settings, 'BASE_DIR', os.getcwd()))
        backup_dir = root / 'aai_backups'
        backup_dir.mkdir(parents=True, exist_ok=True)
        return str(backup_dir / f'aai{self.avaliacao_id}-backup-{ts}.json')


# =========================
# Identidade externa e índices
# =========================
class IdentityResolver:
    @staticmethod
    def only_digits(s: str | None) -> str | None:
        if not s:
            return None
        x = re.sub(r'\D+', '', str(s))
        return x or None

    def ext_identity_key(self, segmento_id: int, dados: dict | None) -> tuple[str, str] | None:
        if not dados:
            return None
        if segmento_id == Segmento.PAIS:
            v = (dados.get('matricula') or '').strip()
            return ('matricula', v) if v else None
        if segmento_id in (Segmento.ALUNO_EGRESSO, Segmento.PROFISSIONAL_PRESTADOR_SERVICO):
            v = self.only_digits(dados.get('cpf'))
            return ('cpf', v) if v else None
        if segmento_id == Segmento.EMPRESA_PRESTADORA_SERVICO:
            v = self.only_digits(dados.get('cnpj'))
            return ('cnpj', v) if v else None
        v = (dados.get('email') or '').strip()
        return ('email', v) if v else None


class IndexCache:
    def __init__(self, avaliacao_id: int, identity: IdentityResolver):
        self.avaliacao_id = avaliacao_id
        self.identity = identity

    def build_internal_index(self) -> IndicesUser:
        idx: IndicesUser = {}
        qs = (
            Respondente.objects.filter(avaliacao_id=self.avaliacao_id)
            .exclude(user_id__isnull=True)
            .only('id', 'avaliacao_id', 'segmento_id', 'user_id')
        )
        for r in qs:
            idx[(r.avaliacao_id, r.segmento_id, r.user_id)] = r.id
        return idx

    def build_external_index(self) -> IndicesExt:
        idx: IndicesExt = {}
        qs = Respondente.objects.filter(avaliacao_id=self.avaliacao_id, user_id__isnull=True).only(
            'id', 'avaliacao_id', 'segmento_id', 'dados_usuario_externo'
        )
        for r in qs:
            chave = self.identity.ext_identity_key(r.segmento_id, r.dados_usuario_externo or {})
            if chave:
                t, v = chave
                idx[(r.avaliacao_id, r.segmento_id, t, v)] = r.id
        return idx

    def refresh(self) -> tuple[IndicesUser, IndicesExt]:
        return self.build_internal_index(), self.build_external_index()


# =========================
# Ajuste de sequences
# =========================
class SequenceAdjuster:
    @staticmethod
    def adjust_if_needed():
        with connection.cursor() as cur:
            cur.execute(
                'SELECT setval(pg_get_serial_sequence(%s, %s), COALESCE(MAX(id), 1)) FROM avaliacao_integrada_respondente;',
                ['avaliacao_integrada_respondente', 'id'],
            )
            cur.execute(
                'SELECT setval(pg_get_serial_sequence(%s, %s), COALESCE(MAX(id), 1)) FROM avaliacao_integrada_resposta;',
                ['avaliacao_integrada_resposta', 'id'],
            )


# =========================
# DUMP
# =========================
class AAIDumper:
    def __init__(self, avaliacao_id: int, stdout):
        self.avaliacao_id = avaliacao_id
        self.stdout = stdout

    def dump(self, file_path: str):
        respondentes_qs = Respondente.objects.filter(avaliacao_id=self.avaliacao_id).order_by('id')
        total_respondentes = respondentes_qs.count()
        respondentes: list[dict[str, Any]] = []

        for r in tqdm(respondentes_qs.iterator(chunk_size=2000), total=total_respondentes, desc='Exportando respondentes', unit='reg'):
            respondentes.append(
                {
                    'id': r.id,
                    'avaliacao_id': r.avaliacao_id,
                    'user_id': r.user_id,
                    'uo_id': r.uo_id,
                    'segmento_id': r.segmento_id,
                    'finalizado': bool(r.finalizado),
                    'dados_usuario_externo': r.dados_usuario_externo or None,
                    'criado_em': r.criado_em.isoformat() if r.criado_em else None,
                    'atualizado_em': r.atualizado_em.isoformat() if r.atualizado_em else None,
                }
            )

        respostas_qs = Resposta.objects.filter(respondente__avaliacao_id=self.avaliacao_id).order_by('id')
        total_respostas = respostas_qs.count()
        respostas: list[dict[str, Any]] = []

        for s in tqdm(respostas_qs.iterator(chunk_size=5000), total=total_respostas, desc='Exportando respostas', unit='reg'):
            respostas.append(
                {
                    'id': s.id,
                    'indicador_id': s.indicador_id,
                    'respondente_id': s.respondente_id,
                    'variavel_id': s.variavel_id,
                    'content_type_id': s.content_type_id,
                    'object_id': s.object_id,
                    'identificador': s.identificador,
                    'valor': s.valor,
                    'nivel_escala_id': s.nivel_escala_id,
                    'criado_em': s.criado_em.isoformat() if s.criado_em else None,
                    'atualizado_em': s.atualizado_em.isoformat() if s.atualizado_em else None,
                }
            )

        payload = {
            'meta': {
                'gerado_em': timezone.now().isoformat(),
                'avaliacao_id': self.avaliacao_id,
                'versao': 1,
            },
            'respondentes': respondentes,
            'respostas': respostas,
        }

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        self.stdout.write(f'Exportação concluída. Respondentes: {len(respondentes)}; Respostas: {len(respostas)}; Arquivo: {file_path}')


# =========================
# LOAD / RESTORE
# =========================
@dataclass
class RespondenteCounts:
    insertados: int = 0
    atualizados: int = 0
    sem_mudanca: int = 0
    pulados: int = 0


@dataclass
class RespostaCounts:
    insertadas: int = 0
    atualizadas: int = 0
    iguais: int = 0
    puladas: int = 0
    nao_mapeadas: int = 0
    conflitos: int = 0


class AAILoader:
    def __init__(self, avaliacao_id: int, identity: IdentityResolver, indices: IndexCache, stdout):
        self.avaliacao_id = avaliacao_id
        self.identity = identity
        self.indices = indices
        self.stdout = stdout

    # ====== helpers p/ arquivos de resultado (no diretório do comando) ======

    def _cmd_dir(self) -> Path:
        """Diretório onde este comando (módulo) está definido."""
        return Path(__file__).resolve().parent

    def _today_tag(self) -> str:
        """AAAAMMDD baseado no fuso configurado do Django."""
        return timezone.now().strftime('%Y%m%d')

    def _find_today_stage_file(self, stage: str) -> Path | None:
        """
        Procura o arquivo mais recente de HOJE para um stage ("respondentes" | "respostas"),
        com padrão: <stage>_result-YYYYmmdd-*.json
        """
        base = self._cmd_dir()
        pattern = f'{stage}_result-{self._today_tag()}*.json'
        files = sorted(base.glob(pattern))
        return files[-1] if files else None

    def _write_stage_result(self, stage: str, payload: dict) -> Path:
        """
        Grava um arquivo JSON <stage>_result-YYYYmmdd-HHMMSS.json de forma atômica.
        """
        out_dir = self._cmd_dir()
        out_dir.mkdir(parents=True, exist_ok=True)

        ts = timezone.now().strftime('%Y%m%d-%H%M%S')
        out_path = out_dir / f'{stage}_result-{ts}.json'
        tmp_path = out_path.with_suffix('.json.tmp')

        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, out_path)

        logger.info('Arquivo de resultado salvo: %s', out_path)
        return out_path

    def _read_json(self, path: Path) -> dict:
        with open(path, encoding='utf-8') as f:
            return json.load(f)

    def _write_respondentes_result(self, counts: RespondenteCounts, respondentes_map_id: dict[int, int], total_items: int) -> Path:
        payload = {
            'meta': {
                'avaliacao_id': self.avaliacao_id,
                'generated_at': timezone.now().isoformat(),
                'total_items': total_items,
            },
            'counts': {
                'insertados': counts.insertados,
                'atualizados': counts.atualizados,
                'sem_mudanca': counts.sem_mudanca,
                'pulados': counts.pulados,
            },
            'map_old_to_new': {str(k): v for k, v in respondentes_map_id.items()},
        }
        return self._write_stage_result('respondentes', payload)

    def _write_respostas_result(self, counts: RespostaCounts, total_items: int) -> Path:
        payload = {
            'meta': {
                'avaliacao_id': self.avaliacao_id,
                'generated_at': timezone.now().isoformat(),
                'total_items': total_items,
            },
            'counts': {
                'insertadas': counts.insertadas,
                'atualizadas': counts.atualizadas,
                'iguais': counts.iguais,
                'puladas': counts.puladas,
                'nao_mapeadas': counts.nao_mapeadas,
                'conflitos': counts.conflitos,
            },
        }
        return self._write_stage_result('respostas', payload)

    def _read_respondentes_result(self, path: Path) -> tuple[RespondenteCounts, dict[int, int]]:
        data = self._read_json(path)
        c = data.get('counts', {}) or {}
        # constrói os dataclasses a partir do JSON
        rc = RespondenteCounts(
            insertados=int(c.get('insertados', 0)),
            atualizados=int(c.get('atualizados', 0)),
            sem_mudanca=int(c.get('sem_mudanca', 0)),
            pulados=int(c.get('pulados', 0)),
        )
        raw_map = data.get('map_old_to_new', {}) or {}
        # chaves de mapa vêm como string no JSON
        m: dict[int, int] = {int(k): (None if v is None else int(v)) for k, v in raw_map.items()}
        return m, rc

    def _read_respostas_result(self, path: Path) -> RespostaCounts:
        data = self._read_json(path)
        c = data.get('counts', {}) or {}
        return RespostaCounts(
            insertadas=int(c.get('insertadas', 0)),
            atualizadas=int(c.get('atualizadas', 0)),
            iguais=int(c.get('iguais', 0)),
            puladas=int(c.get('puladas', 0)),
            nao_mapeadas=int(c.get('nao_mapeadas', 0)),
            conflitos=int(c.get('conflitos', 0)),
        )

    def load(
        self,
        payload: dict,
        stage_callback: Callable[[str, object], None] | None = None,
    ) -> tuple[RespondenteCounts, RespostaCounts]:
        """
        Executa o restore em duas transações:
          1) Respondentes (atomic)
          2) Respostas   (atomic)

        Se já existirem arquivos de resultado **de hoje** para ambos os stages
        (respondentes e respostas) no diretório do comando, PULA o processamento
        e retorna os contadores lidos desses arquivos.

        Chama stage_callback(stage, counts) ao final de cada etapa (inclusive
        quando a etapa é recuperada do cache/arquivo).
        """
        # Tenta recuperar resultados de HOJE (cache em arquivo)
        r_file = self._find_today_stage_file('respondentes')
        a_file = self._find_today_stage_file('respostas')

        if r_file:
            logger.info(f'Resultados de respondentes encontrados para hoje. Pulando processamento. r_file={r_file.name}')
            respondentes_map_id, r_counts = self._read_respondentes_result(r_file)
        else:
            # Extrai listas do JSON (processamento normal)
            data_respondentes = payload.get('respondentes') or []

            # -------- Etapa 1: Respondentes (TRANSação 1) --------
            with transaction.atomic():
                existentes_por_user, existentes_ext = self.indices.refresh()
                respondentes_map_id, r_counts = self._process_respondentes(
                    data_respondentes,
                    existentes_por_user,
                    existentes_ext,
                )

            # persiste resultado da etapa 1 no diretório do comando
            try:
                self._write_respondentes_result(
                    counts=r_counts,
                    respondentes_map_id=respondentes_map_id,
                    total_items=len(data_respondentes),
                )
            except Exception:
                logger.exception('Falha ao gravar resultado de respondentes (cache de arquivo).')

        if stage_callback:
            stage_callback('respondentes', r_counts)

        if a_file:
            logger.info(f'Resultados de respostas encontrados para hoje. Pulando processamento. r_file={a_file.name}')
            a_counts = self._read_respostas_result(a_file)
        else:
            data_respostas = payload.get('respostas') or []
            # -------- Etapa 2: Respostas (TRANSação 2) -----------
            with transaction.atomic():
                a_counts = self._process_respostas(
                    data_respostas,
                    respondentes_map_id,
                )

            # persiste resultado da etapa 2 no diretório do comando
            try:
                self._write_respostas_result(
                    counts=a_counts,
                    total_items=len(data_respostas),
                )
            except Exception:
                logger.exception('Falha ao gravar resultado de respostas (cache de arquivo).')

        if stage_callback:
            stage_callback('respostas', a_counts)

        return r_counts, a_counts

    # ---------- respondentes ----------
    def _respondente_is_identical(self, rid: int, update_kwargs: dict, user_id: str | None = None) -> bool:
        base_filter = {
            'id': rid,
            'avaliacao_id': self.avaliacao_id,
            'finalizado': update_kwargs.get('finalizado'),
            'uo_id': update_kwargs.get('uo_id'),
            'segmento_id': update_kwargs.get('segmento_id'),
            'user_id': user_id,
        }
        if update_kwargs.get('dados_usuario_externo') is None:
            base_filter['dados_usuario_externo__isnull'] = True
        return Respondente.objects.filter(**base_filter).exists()

    def _process_respondentes(
        self,
        data_respondentes: list[dict],
        existentes_por_user: IndicesUser,
        existentes_ext: IndicesExt,
    ) -> tuple[dict[int, int], RespondenteCounts]:
        """
        Processa a lista de respondentes vinda do JSON e:
          • mapeia cada PK do arquivo (old_id) para a PK real no BD (new_id),
          • atualiza registros existentes quando identificados por chaves internas/externas,
          • cria registros quando necessário, tentando preservar a PK do arquivo.

        Estratégia de identificação:
          A) Respondente **interno** (possui `user_id`):
             - chave de busca: (avaliacao_id, segmento_id, user_id)
             - se existir no BD, **atualiza** campos mutáveis e mapeia old_id -> target_id.
          B) Respondente **externo** (sem `user_id`):
             - chave de busca: (avaliacao_id, segmento_id, tipo, valor) onde
               `tipo`/`valor` vêm de `IdentityResolver.ext_identity_key` (matricula/cpf/cnpj/email).
             - se existir no BD, **atualiza** campos mutáveis e mapeia old_id -> target_id.
          C) Caso não exista:
             - tenta **criar** preservando a PK do arquivo (old_id); se já estiver em uso,
               cria sem id (deixa o BD gerar) e mapeia old_id -> new_id.

        Contadores (em `RespondenteCounts`):
          - insertados: criados novos
          - atualizados: encontrados e atualizados
          - sem_mudanca: encontrados e já idênticos (nenhum UPDATE emitido)
          - pulados: identificação feita, mas UPDATE não encontrou a linha (caso raro)→não cria

        Retorna:
          (old_to_new, counts)
            • old_to_new: dict[old_id -> new_id ou None] (None quando “pulado”)
            • counts: métricas agregadas do processamento

        Observações:
          - O método assume ser executado **dentro** de uma transação atômica
            (a orquestração faz isso), garantindo consistência por etapa.
          - Usamos `exists()`/filtros exatos antes de `update()` para evitar updates
            desnecessários (otimização).
          - Não forçamos `atualizado_em` via `.update()` (campos `auto_now` não disparam
            com `update()`); preservamos o controle do app sobre esse timestamp.
        """
        respondentes_map: dict[int, int] = {}
        counts = RespondenteCounts()

        total = len(data_respondentes)
        logger.info('> Iniciando processamento de respondentes: total=%d, avaliacao_id=%s', total, self.avaliacao_id)

        for drespondente in tqdm(data_respondentes, total=total, desc='Processando respondentes', unit='reg'):
            # Sanidade do item
            if not drespondente:
                logger.debug('Item ignorado: payload vazio.')
                continue

            if drespondente.get('avaliacao_id') != self.avaliacao_id:
                logger.debug(
                    'Item ignorado: avaliacao_id=%s (esperado %s). id=%s', drespondente.get('avaliacao_id'), self.avaliacao_id, drespondente.get('id')
                )
                continue

            if 'id' not in drespondente:
                logger.warning("Item ignorado: sem PK no arquivo (campo 'id'). Payload=%r", drespondente)
                continue

            old_id = int(drespondente['id'])
            user_id = drespondente.get('user_id')
            segmento_id = drespondente.get('segmento_id')
            dados_usuario_externo = drespondente.get('dados_usuario_externo', None)
            finalizado = bool(drespondente.get('finalizado', False))

            # parse de criado_em (se presente)
            raw_criado = drespondente.get('criado_em')
            criado_em = parse_datetime(raw_criado) if raw_criado else None

            logger.debug(
                'Respondente(arquivo) old_id=%s user_id=%s segmento_id=%s uo_id=%s finalizado=%s',
                old_id,
                user_id,
                segmento_id,
                drespondente.get('uo_id'),
                finalizado,
            )

            # Payload mutável
            update_kwargs = {
                'finalizado': finalizado,
                'dados_usuario_externo': dados_usuario_externo,
                'uo_id': drespondente.get('uo_id'),
                'segmento_id': segmento_id,
                'criado_em': criado_em,
                # preservar criado_em do JSON (se definido)
            }

            # --- A) Interno: chave (avaliacao, segmento, user) -------------------
            key_user = (self.avaliacao_id, segmento_id, user_id) if user_id is not None else None
            if key_user and key_user in existentes_por_user:
                target_id = existentes_por_user[key_user]
                respondentes_map[old_id] = target_id
                logger.debug('Match interno encontrado: key=%s→target_id=%s (old_id=%s)', key_user, target_id, old_id)

                # Evita UPDATE se já está idêntico
                if self._respondente_is_identical(target_id, update_kwargs, user_id):
                    counts.sem_mudanca += 1
                    logger.debug('Sem mudança (idêntico): target_id=%s', target_id)
                else:
                    # Atualiza somente os respondentes que não enviaram as respostas (finalizado=False)
                    updated = Respondente.objects.filter(id=target_id, avaliacao_id=self.avaliacao_id, finalizado=False).update(**update_kwargs)
                    if updated:
                        counts.atualizados += 1
                        logger.info('Atualizado respondente target_id=%s (old_id=%s)', target_id, old_id)
                    else:
                        # Respondente mudou para finalizado=True ou foi apagado
                        respondentes_map[old_id] = None
                        counts.pulados += 1
                        logger.warning(
                            'UPDATE não realizado, PULADO. Respondente mudou '
                            'para finalizado=True ou foi apagado(pulado): '
                            'target_id=%s old_id=%s key=%s',
                            target_id,
                            old_id,
                            key_user,
                        )
                continue

            # --- B) Externo: identidade por segmento (matrícula/cpf/cnpj/email) ---
            if user_id is None:
                chave = self.identity.ext_identity_key(int(segmento_id) if segmento_id is not None else 0, dados_usuario_externo)
                logger.debug('Chave externa derivada para old_id=%s: %r', old_id, chave)

                if chave:
                    t, v = chave
                    key_ext = (self.avaliacao_id, int(segmento_id), t, v)
                    if key_ext in existentes_ext:
                        target_id = existentes_ext[key_ext]
                        respondentes_map[old_id] = target_id
                        logger.debug('Match externo encontrado: key=%s→target_id=%s (old_id=%s)', key_ext, target_id, old_id)

                        if self._respondente_is_identical(target_id, update_kwargs):
                            counts.sem_mudanca += 1
                            logger.debug('Sem mudança (idêntico): target_id=%s', target_id)
                        else:
                            updated = Respondente.objects.filter(id=target_id, avaliacao_id=self.avaliacao_id).update(**update_kwargs)
                            if updated:
                                counts.atualizados += 1
                                logger.info('Atualizado respondente externo target_id=%s (old_id=%s)', target_id, old_id)
                            else:
                                respondentes_map[old_id] = None
                                counts.pulados += 1
                                logger.warning('UPDATE não encontrou a linha (pulado): target_id=%s old_id=%s key=%s', target_id, old_id, key_ext)
                        continue
                    else:
                        logger.debug('Nenhum match externo para key=%s', key_ext if 'key_ext' in locals() else chave)

            # --- C) Criar (tentar preservar PK do arquivo) -----------------------
            pk_em_uso = Respondente.objects.filter(id=old_id).exists()
            if not pk_em_uso:
                # Tenta criar com a mesma PK do arquivo
                logger.debug('Criando respondente preservando PK do arquivo: old_id=%s', old_id)
                obj = Respondente(
                    id=old_id,
                    avaliacao_id=self.avaliacao_id,
                    user_id=user_id,
                    uo_id=drespondente.get('uo_id'),
                    segmento_id=segmento_id,
                    finalizado=finalizado,
                    dados_usuario_externo=dados_usuario_externo,
                )
                obj.save(force_insert=True)
                new_id = old_id
                logger.info('Criado respondente com PK preservada: id=%s (old_id=%s)', new_id, old_id)
            else:
                # PK já em uso→deixa o BD gerar a PK
                logger.debug('PK %s já em uso. Criando respondente com PK gerada pelo BD.', old_id)
                obj = Respondente(
                    avaliacao_id=self.avaliacao_id,
                    user_id=user_id,
                    uo_id=drespondente.get('uo_id'),
                    segmento_id=segmento_id,
                    finalizado=finalizado,
                    dados_usuario_externo=dados_usuario_externo,
                )
                obj.save(force_insert=True)
                new_id = obj.id
                logger.info('Criado respondente com nova PK: new_id=%s (old_id=%s)', new_id, old_id)

            respondentes_map[old_id] = new_id
            counts.insertados += 1

        logger.info(
            'Processamento de respondentes concluído: inseridos=%d, atualizados=%d, sem_mudanca=%d, pulados=%d',
            counts.insertados,
            counts.atualizados,
            counts.sem_mudanca,
            counts.pulados,
        )
        return respondentes_map, counts

    # ---------- respostas ----------
    def _snapshot_respondentes_com_resposta(self) -> set[int]:
        """
        Retorna um *snapshot* (conjunto) dos IDs de respondentes que já possuem
        **ao menos uma** resposta ANTES da etapa de restauração das respostas.
        """
        qs = Resposta.objects.filter(respondente__avaliacao_id=self.avaliacao_id).values_list('respondente_id', flat=True).distinct()
        return set(qs)

    def _process_respostas(
        self,
        data_respostas: list[dict],
        respondentes_map_id: dict[int, int],
    ) -> RespostaCounts:
        total = len(data_respostas)
        counts = RespostaCounts()

        logger.info('> Iniciando processamento de respostas (total=%d).', total)

        snapshot_respondentes_ids = self._snapshot_respondentes_com_resposta()
        logger.debug(f'Obitido snapshot de quem já tinha respostas antes do restore, total={len(snapshot_respondentes_ids)}')

        for _idx, dresposta in enumerate(
            tqdm(data_respostas, total=total, desc='Inserindo/atualizando respostas (item a item)', unit='reg'),
            start=1,
        ):
            if not dresposta:
                logger.warning('f[rid={rid}] ignorada: payload vazio/None.')
                continue

            rid = dresposta.get('id')

            respondente_old_id = dresposta.get('respondente_id')
            if respondente_old_id is None:
                logger.warning(
                    f"[rid={rid}] ignorada: resposta sem 'respondente_id'. Payload={dresposta}",
                )
                continue

            respondente_new_id = respondentes_map_id.get(int(respondente_old_id))
            if not respondente_new_id:
                counts.nao_mapeadas += 1
                logger.warning(f'[rid={rid}] ignorada: respondente_id do arquivo {respondente_old_id} não mapeado. Payload={dresposta}')
                continue

            # Campos comuns a update/insert
            indicador_id = dresposta['indicador_id']
            identificador = dresposta.get('identificador').replace(f'::{respondente_old_id}::', f'::{respondente_new_id}::')
            valor = dresposta.get('valor') or ''
            nivel = dresposta.get('nivel_escala_id')
            criado_em = parse_datetime(dresposta.get('criado_em')) if dresposta.get('criado_em') else None

            update_kwargs = {
                'indicador_id': indicador_id,
                'respondente_id': respondente_new_id,
                'variavel_id': dresposta.get('variavel_id'),
                'content_type_id': dresposta.get('content_type_id'),
                'object_id': dresposta.get('object_id'),
                'identificador': identificador,
                'valor': valor,
                'nivel_escala_id': nivel,
                'criado_em': criado_em,
            }
            filtro_base = {
                'respondente_id': respondente_new_id,
                'indicador_id': indicador_id,
                'variavel_id': dresposta.get('variavel_id'),
                'content_type_id': dresposta.get('content_type_id'),
                'object_id': dresposta.get('object_id'),
                'identificador': identificador,
            }

            qsresposta = Resposta.objects.filter(**filtro_base)
            if qsresposta.exists():
                resposta = qsresposta.first()
                # Se a resposta já está idêntica, não atualiza
                if resposta.valor == valor and resposta.nivel_escala_id == nivel:
                    logger.debug(f'[rid={rid}] Sem mudança, resposta identica. filtro: {filtro_base}. valor={valor}, nivel_escala_id={nivel}.')
                    counts.iguais += 1
                    continue

                # Se existir a respotta, mas não tiver valor nem nível de escala,
                # atualiza para evitar inconsistências
                if not resposta.valor and not resposta.nivel_escala_id:
                    updated = qsresposta.update(**update_kwargs)
                    if updated:
                        counts.atualizadas += updated
                        logger.info(f'[rid={rid}] **ATUALIZAÇÃO**: id {rid}→{resposta.id}. filtro_base={filtro_base}, update_kwargs={update_kwargs}')
                        continue

                # Se a resposta já existe, mas não está idêntica, mantem o registro atual
                counts.puladas += 1
                logger.warning(
                    f'[rid={rid}] Resposta id {rid}→{resposta.id} já '
                    f'existe, mas não está idêntica (Mantida a atual): '
                    f'filtro aplicado={filtro_base}. Dados: '
                    f'criado_em={criado_em}→{resposta.criado_em}, '
                    f'valor={valor}→{resposta.valor}, respondente map='
                    f'{respondente_old_id}→{respondente_new_id}'
                )
                continue
            else:
                if respondente_new_id in snapshot_respondentes_ids:
                    # Resposta não encontrada dentre as respostas do respondente,
                    logger.warning(
                        f'[rid={rid}] Resposta id={rid}→{resposta.id} com '
                        f'indicador {indicador_id} não encontrada dentre as '
                        f'respostas do respondente. Será criada uma nova.'
                    )

                Resposta.objects.create(
                    id=dresposta['id'],  # preservar PK do arquivo
                    **update_kwargs,
                )
                counts.insertadas += 1
                logger.info(
                    f'[rid={rid}] **INSERÇÃO**: resposta com PK preservada. '
                    f'Resposta não encontrada para o filtro: {filtro_base}. '
                    f'respondente map={respondente_old_id}→{respondente_new_id} '
                )
                continue

            raise ValueError('Código não deve chegar aqui. Verifique a lógica.')

        # FIM
        logger.info(
            'Finalizado processamento de respostas. insertadas=%d, atualizadas=%d, iguais=%d, puladas=%d, nao_mapeadas=%d, conflitos=%d',
            counts.insertadas,
            counts.atualizadas,
            counts.iguais,
            counts.puladas,
            counts.nao_mapeadas,
            counts.conflitos,
        )
        return counts


# =========================
# Inspeção por matrícula
# =========================
class AAIInspector:
    def __init__(self, avaliacao_id: int, stdout):
        self.avaliacao_id = avaliacao_id
        self.stdout = stdout
        self.printer = TablePrinter(stdout)

    def inspect_by_matricula(self, file_path: str, limit: int, matricula: str):
        if not os.path.exists(file_path):
            raise CommandError(f'Arquivo não encontrado: {file_path}')

        with open(file_path, encoding='utf-8') as f:
            payload = json.load(f)

        try:
            meta_id = int(payload.get('meta', {}).get('avaliacao_id'))
        except Exception:
            raise CommandError('Arquivo inválido: meta.avaliacao_id ausente ou não numérico.')
        if meta_id != self.avaliacao_id:
            raise CommandError(f'Arquivo não corresponde à avaliação alvo (ID={self.avaliacao_id}).')

        file_resp_all = list(payload.get('respondentes', []) or [])
        file_ans_all = list(payload.get('respostas', []) or [])

        user = User.objects.filter(username=matricula).only('id', 'username').first()
        if not user:
            raise CommandError(f"Usuário com username (matrícula) '{matricula}' não encontrado.")

        self.stdout.write(f'Matrícula: {matricula}  |  user_id: {user.id}')
        self.stdout.write(f'Avaliação alvo: {self.avaliacao_id}\n')

        file_resp_rows = [r for r in file_resp_all if r and r.get('avaliacao_id') == self.avaliacao_id and r.get('user_id') == user.id]
        file_resp_ids = [r.get('id') for r in file_resp_rows if 'id' in r]
        file_ans_rows = [s for s in file_ans_all if s and s.get('respondente_id') in file_resp_ids]

        db_resp_rows = list(
            Respondente.objects.filter(avaliacao_id=self.avaliacao_id, user_id=user.id)
            .values('id', 'avaliacao_id', 'user_id', 'uo_id', 'segmento_id', 'finalizado', 'dados_usuario_externo', 'criado_em', 'atualizado_em')
            .order_by('id')
        )
        db_resp_ids = [r['id'] for r in db_resp_rows]
        db_ans_rows = list(
            Resposta.objects.filter(respondente_id__in=db_resp_ids)
            .values(
                'id',
                'respondente_id',
                'indicador_id',
                'variavel_id',
                'content_type_id',
                'object_id',
                'identificador',
                'valor',
                'nivel_escala_id',
                'criado_em',
                'atualizado_em',
            )
            .order_by('id')
        )

        # Resumo
        self.printer.print_table(
            headers=['Origem', 'Respondentes (IDs)', 'Qtde Respostas'],
            rows=[
                ['ARQUIVO', ', '.join(map(str, file_resp_ids)) or '—', len(file_ans_rows)],
                ['BANCO', ', '.join(map(str, db_resp_ids)) or '—', len(db_ans_rows)],
            ],
            max_widths=[10, 80, 16],
        )

        # Respondentes (Arquivo)
        self.stdout.write('Respondentes no ARQUIVO')
        rows = []
        for r in sorted(file_resp_rows, key=lambda x: x.get('id', 0)):
            deu_str = json.dumps(r.get('dados_usuario_externo'), ensure_ascii=False) if r.get('dados_usuario_externo') is not None else None
            rows.append(
                [
                    r.get('id'),
                    r.get('avaliacao_id'),
                    r.get('user_id'),
                    r.get('uo_id'),
                    r.get('segmento_id'),
                    bool(r.get('finalizado')),
                    self.printer.trim(deu_str, 80),
                    r.get('criado_em'),
                    r.get('atualizado_em'),
                ]
            )
        self.printer.print_table(
            headers=['id', 'avaliacao_id', 'user_id', 'uo_id', 'segmento_id', 'finalizado', 'dados_usuario_externo', 'criado_em', 'atualizado_em'],
            rows=rows,
            max_widths=[12, 12, 10, 10, 12, 11, 80, 24, 24],
        )

        # Respondentes (Banco)
        self.stdout.write('Respondentes no BANCO')
        rows = []
        for r in db_resp_rows:
            deu_str = json.dumps(r.get('dados_usuario_externo'), ensure_ascii=False) if r.get('dados_usuario_externo') is not None else None
            rows.append(
                [
                    r.get('id'),
                    r.get('avaliacao_id'),
                    r.get('user_id'),
                    r.get('uo_id'),
                    r.get('segmento_id'),
                    bool(r.get('finalizado')),
                    self.printer.trim(deu_str, 80),
                    r.get('criado_em') and r['criado_em'].isoformat(),
                    r.get('atualizado_em') and r['atualizado_em'].isoformat(),
                ]
            )
        self.printer.print_table(
            headers=['id', 'avaliacao_id', 'user_id', 'uo_id', 'segmento_id', 'finalizado', 'dados_usuario_externo', 'criado_em', 'atualizado_em'],
            rows=rows,
            max_widths=[12, 12, 10, 10, 12, 11, 80, 24, 24],
        )

        # Respostas (Arquivo)
        self.stdout.write(f'Respostas no ARQUIVO (máx {limit})')
        rows = []
        for s in file_ans_rows[:limit] if limit else file_ans_rows:
            rows.append(
                [
                    s.get('id'),
                    s.get('respondente_id'),
                    s.get('indicador_id'),
                    s.get('variavel_id'),
                    s.get('content_type_id'),
                    s.get('object_id'),
                    self.printer.trim(s.get('identificador'), 32),
                    self.printer.trim(s.get('valor'), 40),
                    s.get('nivel_escala_id'),
                    s.get('criado_em'),
                    s.get('atualizado_em'),
                ]
            )
        self.printer.print_table(
            headers=[
                'id',
                'respondente_id',
                'indicador_id',
                'variavel_id',
                'content_type_id',
                'object_id',
                'identificador',
                'valor',
                'nivel_escala_id',
                'criado_em',
                'atualizado_em',
            ],
            rows=rows,
            max_widths=[12, 16, 14, 12, 16, 12, 32, 40, 16, 24, 24],
        )
        if limit and len(file_ans_rows) > limit:
            self.stdout.write(f'... e mais {len(file_ans_rows) - limit} respostas no arquivo.\n')

        # Respostas (Banco)
        self.stdout.write(f'Respostas no BANCO (máx {limit})')
        rows = []
        for s in db_ans_rows[:limit] if limit else db_ans_rows:
            rows.append(
                [
                    s.get('id'),
                    s.get('respondente_id'),
                    s.get('indicador_id'),
                    s.get('variavel_id'),
                    s.get('content_type_id'),
                    s.get('object_id'),
                    self.printer.trim(s.get('identificador'), 32),
                    self.printer.trim(s.get('valor'), 40),
                    s.get('nivel_escala_id'),
                    s.get('criado_em') and s['criado_em'].isoformat(),
                    s.get('atualizado_em') and s['atualizado_em'].isoformat(),
                ]
            )
        self.printer.print_table(
            headers=[
                'id',
                'respondente_id',
                'indicador_id',
                'variavel_id',
                'content_type_id',
                'object_id',
                'identificador',
                'valor',
                'nivel_escala_id',
                'criado_em',
                'atualizado_em',
            ],
            rows=rows,
            max_widths=[12, 16, 14, 12, 16, 12, 32, 40, 16, 24, 24],
        )
        if limit and len(db_ans_rows) > limit:
            self.stdout.write(f'... e mais {len(db_ans_rows) - limit} respostas no banco.\n')

        self.stdout.write('Inspeção concluída.')


# =========================
# SummaryReporter
# =========================


class SummaryReporter:
    """
    Imprime resumos parciais (por etapa) e o final.
    Aceita tanto dict quanto dataclass (RespondenteCounts/RespostaCounts).
    """

    def __init__(self, stdout: Any, style: Any) -> None:
        self.stdout = stdout
        self.style = style

    # ---------- utilidades internas ----------

    def _norm(self, counts: Any) -> dict[str, Any]:
        """
        Converte dataclass/objeto em dict de forma segura.
        """
        if isinstance(counts, dict):
            return counts
        if is_dataclass(counts):
            return asdict(counts)
        # fallback: atributos públicos não-callable
        out: dict[str, Any] = {}
        for name in dir(counts):
            if name.startswith('_'):
                continue
            val = getattr(counts, name, None)
            if callable(val):
                continue
            out[name] = val
        return out

    def _n(self, counts: Any, *keys: str) -> int:
        """
        Lê um inteiro do dict normalizado, aceitando aliases de chave.
        """
        c = self._norm(counts)
        for k in keys:
            if k in c:
                try:
                    return int(c[k] or 0)
                except Exception:
                    return 0
        return 0

    # ---------- API chamada pelo loader ----------

    def stage_callback(self, stage: str, counts: Any) -> None:
        """
        Pode ser passada diretamente para AAILoader.load(stage_callback=...).
        """
        if stage == 'respondentes':
            self.print_respondentes_summary(counts)
        elif stage == 'respostas':
            self.print_respostas_summary(counts)

    # ---------- impressões de resumo ----------

    def print_respondentes_summary(self, counts: Any) -> None:
        insertados = self._n(counts, 'insertados', 'insertados_respondentes')
        atualizados = self._n(counts, 'atualizados', 'atualizados_respondentes')
        sem_mudanca = self._n(counts, 'sem_mudanca', 'sem_mudanca_respondentes', 'iguais')
        pulados = self._n(counts, 'pulados', 'pulados_respondentes')

        self.stdout.write(self.style.SUCCESS('Resumo — Respondentes'))
        self.stdout.write(f'- Inseridos: {insertados}')
        self.stdout.write(f'- Atualizados: {atualizados}')
        self.stdout.write(f'- Sem mudança (iguais): {sem_mudanca}')
        self.stdout.write(f'- Pulados: {pulados}\n')

    def print_respostas_summary(self, counts: Any) -> None:
        insertadas = self._n(counts, 'insertadas', 'insertadas_respostas')
        atualizadas = self._n(counts, 'atualizadas', 'atualizadas_respostas')
        iguais = self._n(counts, 'iguais', 'iguais_respostas')
        puladas = self._n(counts, 'puladas', 'puladas_respostas')
        nao_mapeadas = self._n(counts, 'nao_mapeadas', 'nao_mapeadas_respostas')
        conflitos = self._n(counts, 'conflitos', 'conflitos_respostas')

        self.stdout.write(self.style.SUCCESS('Resumo — Respostas'))
        self.stdout.write(f'- Inseridas: {insertadas}')
        self.stdout.write(f'- Atualizadas: {atualizadas}')
        self.stdout.write(f'- Já idênticas (sem update): {iguais}')
        self.stdout.write(f'- Puladas: {puladas}')
        self.stdout.write(f'- Não mapeadas: {nao_mapeadas}')
        self.stdout.write(f'- Em conflito: {conflitos}\n')

    def print_overall_summary(self, r_counts: Any, a_counts: Any) -> None:
        """
        Imprime um resumo final (agregado) reaproveitando os resumos parciais.
        """
        self.stdout.write(self.style.SUCCESS('Restauração concluída (resumo final).'))
        self.print_respondentes_summary(r_counts)
        self.print_respostas_summary(a_counts)


# =========================
# Comando (orquestrador fino)
# =========================
class Command(BaseCommand):
    help = (
        'Exporta e restaura Respondentes e Respostas da AAI (apenas avaliação ID=26). \n'
        'Uso:\n'
        '  - Dump:  manage.py aai_restore_respostas --dump --file /tmp/aai26.json\n'
        '  - Load:  manage.py aai_restore_respostas --load --file /tmp/aai26.json\n'
        '  - Inspeção por matrícula: --inspect-matricula <username> [--limit-respostas N]\n'
    )

    def add_arguments(self, parser):
        parser.add_argument('--dump', action='store_true', help='Exporta dados para o arquivo indicado por --file.')
        parser.add_argument('--load', action='store_true', help='Restaura dados a partir do arquivo indicado por --file.')
        parser.add_argument('--file', type=str, required=True, help='Caminho do JSON para exportação/restore.')
        parser.add_argument('--inspect-matricula', type=str, help='Compara JSON vs. BD por matrícula (username).')
        parser.add_argument('--limit-respostas', type=int, default=50, help='Máximo de respostas por tabela (padrão: 50).')

    # python manage.py aai_restore_respostas --inspect-matricula 1722737 --file aai26.json --limit-respostas 100

    def handle(self, *args, **opts):
        file_path = opts['file']
        do_dump = bool(opts.get('dump'))
        do_load = bool(opts.get('load') or (not opts.get('dump') and not opts.get('load')))
        inspect_matricula = opts.get('inspect_matricula')
        limit = int(opts.get('limit_respostas') or 50)

        # Sanidade: avaliação alvo existe?
        if not Avaliacao.objects.filter(pk=AVALIACAO_ID_ALVO).exists():
            raise CommandError(f'Avaliação ID={AVALIACAO_ID_ALVO} não encontrada.')

        io = PayloadIO(AVALIACAO_ID_ALVO)
        identity = IdentityResolver()
        indices = IndexCache(AVALIACAO_ID_ALVO, identity)
        dumper = AAIDumper(AVALIACAO_ID_ALVO, self.stdout)
        inspector = AAIInspector(AVALIACAO_ID_ALVO, self.stdout)
        reporter = SummaryReporter(self.stdout, self.style)

        if do_dump and do_load:
            raise CommandError('Escolha apenas um modo: --dump OU --load.')

        if inspect_matricula:
            return inspector.inspect_by_matricula(file_path=file_path, limit=limit, matricula=inspect_matricula)

        if do_dump:
            return dumper.dump(file_path)

        # LOAD (com backup prévio)
        backup_path = io.make_backup_path()
        self.stdout.write(self.style.WARNING(f'Criando backup em: {backup_path}'))
        dumper.dump(backup_path)
        self.stdout.write(self.style.SUCCESS('Backup concluído.'))

        payload = io.read_and_validate(file_path)

        # Executa o load em duas transações; o reporter imprime o resumo ao final de cada etapa
        loader = AAILoader(AVALIACAO_ID_ALVO, identity, indices, self.stdout)
        r_counts, a_counts = loader.load(payload, stage_callback=reporter.stage_callback)

        # Resumo final agregado
        reporter.print_overall_summary(r_counts, a_counts)
