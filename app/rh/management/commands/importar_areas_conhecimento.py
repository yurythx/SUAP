from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from rh.models import AreaConhecimento


@dataclass(frozen=True)
class LinhaArea:
    is_superior: bool
    codigo: str
    descricao: str


def parse_linha(raw: str) -> LinhaArea | None:
    raw = raw.strip()
    if not raw:
        return None

    is_superior = raw.startswith('*')
    if is_superior:
        raw = raw[1:].strip()

    # suporte a separadores comuns (prioriza |)
    sep_encontrado = None
    for sep in ('|', ';', '\t'):
        if sep in raw:
            sep_encontrado = sep
            break
    if sep_encontrado is None:
        raise CommandError(f'Linha inválida (sem separador conhecido): {raw}')

    codigo, descricao = raw.split(sep_encontrado, 1)
    codigo = codigo.strip()
    descricao = descricao.strip()

    if not codigo or not descricao:
        raise CommandError(f'Linha inválida (código/descrição vazios): {raw}')

    return LinhaArea(is_superior=is_superior, codigo=codigo, descricao=descricao)


class Command(BaseCommand):
    help = (
        'Importa áreas de conhecimento a partir de rh/fixtures/grandes_areas.txt. '
        'Linhas com * são superiores; linhas seguintes herdam esse superior até o próximo *.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--update-existing',
            action='store_true',
            help='Se informado, atualiza descricao e superior quando o codigo já existir.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Não grava no banco; apenas mostra o que faria.',
        )
        parser.add_argument(
            '--debug',
            action='store_true',
            help='Mostra caminho do arquivo, tamanho e primeiras linhas.',
        )

    @transaction.atomic
    def handle(self, *args, **opts):
        update_existing = bool(opts['update_existing'])
        dry_run = bool(opts['dry_run'])
        debug = bool(opts['debug'])

        # path do app rh
        app_config = apps.get_app_config('rh')
        base_path = Path(app_config.path)
        arquivo = base_path / 'fixtures' / 'grandes_areas.txt'

        if not arquivo.exists():
            raise CommandError(f'Arquivo não encontrado: {arquivo}')

        if debug:
            self.stdout.write(f'Arquivo: {arquivo}')
            self.stdout.write(f'Tamanho (bytes): {arquivo.stat().st_size}')
            with arquivo.open('r', encoding='utf-8', errors='replace') as f:
                self.stdout.write('Primeiras linhas:')
                for _ in range(5):
                    line = f.readline()
                    if not line:
                        break
                    self.stdout.write(f'  {line.rstrip()}')

        # Correção do erro do Postgres:
        # evita que o manager aplique select_related/joins que causam OUTER JOIN com FK nullable,
        # o que quebra com FOR UPDATE usado por update_or_create.
        qs = AreaConhecimento.objects.select_related(None)

        superior_atual: AreaConhecimento | None = None
        superior_codigo_atual: str | None = None  # para dry-run mostrar sup corretamente

        criados = 0
        atualizados = 0
        ignorados = 0
        linhas_lidas = 0

        with arquivo.open('r', encoding='utf-8', errors='replace') as f:
            for i, raw in enumerate(f, start=1):
                linhas_lidas += 1
                item = parse_linha(raw)
                if item is None:
                    continue

                # Linha superior (com *)
                if item.is_superior:
                    if dry_run:
                        self.stdout.write(f'[DRY] superior {item.codigo} - {item.descricao}')
                        superior_codigo_atual = item.codigo
                        continue

                    obj, created = qs.update_or_create(
                        codigo=item.codigo,
                        defaults={'descricao': item.descricao, 'superior': None},
                    )

                    if (not update_existing) and (not created):
                        # não mexe no existente
                        ignorados += 1
                    else:
                        if created:
                            criados += 1
                        else:
                            atualizados += 1

                    superior_atual = obj
                    superior_codigo_atual = obj.codigo
                    continue

                # Linha filha
                if dry_run:
                    if superior_codigo_atual is None:
                        raise CommandError(f'Linha {i}: item filho sem superior definido antes. Código: {item.codigo}')
                    self.stdout.write(f'[DRY] filho {item.codigo} - {item.descricao} (sup={superior_codigo_atual})')
                    continue

                if superior_atual is None:
                    raise CommandError(f'Linha {i}: item filho sem superior definido antes. Código: {item.codigo}')

                obj, created = qs.update_or_create(
                    codigo=item.codigo,
                    defaults={'descricao': item.descricao, 'superior': superior_atual},
                )

                if (not update_existing) and (not created):
                    ignorados += 1
                else:
                    if created:
                        criados += 1
                    else:
                        atualizados += 1

        if dry_run:
            transaction.set_rollback(True)

        self.stdout.write(
            self.style.SUCCESS(
                f'Concluído. Linhas={linhas_lidas}, Criados={criados}, Atualizados={atualizados}, Ignorados={ignorados}, Dry-run={dry_run}'
            )
        )
