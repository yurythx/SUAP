# rh/management/commands/sincronizar_siorg_setor.py
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from rh.models import Setor  # ajuste o import conforme seu projeto


class Command(BaseCommand):
    help = (
        'Sincroniza codigo_siorg em Setores SUAP a partir do seu correspondente SIAPE. '
        'Preferência: equivalência por codigo -> sigla igual -> sigla/UO.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--commit',
            action='store_true',
            help='Efetiva as alterações (por padrão é dry-run).',
        )
        parser.add_argument(
            '--overwrite',
            action='store_true',
            help='Sobrescreve codigo_siorg já existente no SUAP.',
        )
        parser.add_argument(
            '--include-already-set',
            action='store_true',
            help='Inclui SUAPs que já possuem codigo_siorg definido (útil com --overwrite).',
        )
        parser.add_argument(
            '--uo-id',
            type=int,
            default=None,
            help='Filtra os setores SUAP por uma UO específica (id).',
        )
        parser.add_argument(
            '--sigla',
            type=str,
            default=None,
            help='Processa apenas a(s) sigla(s) informada(s). Aceita vírgulas.',
        )
        parser.add_argument(
            '--no-uo-suffix',
            dest='no_uo_suffix',
            action='store_true',
            help='Desativa o fallback <sigla>/<sigla_da_UO> quando não houver match exato.',
        )

    # ---------- helpers ----------
    def _siape_por_equivalencia(self, suap, siape_base):
        """
        Tenta encontrar o SIAPE pelo codigo informado em equivalencia_codigo.
        Retorna o objeto Setor SIAPE ou None.
        """
        eq = (suap.equivalencia_codigo or '').strip()
        if not eq:
            return None
        return siape_base.filter(codigo=eq).only('id', 'sigla', 'codigo', 'codigo_siorg').first()

    def _siape_por_sigla(self, suap, siape_base, try_uo_suffix=True):
        """
        1) sigla__iexact
        2) se não achar e try_uo_suffix=True e houver UO.sigla, tenta '<sigla>/<UO.sigla>'
        Retorna (obj, origem) onde origem ∈ {'exato', 'uo-suffix'} ou (None, None).
        - Se houver múltiplos, retorna (None, 'ambiguo') para o chamador tratar.
        """
        candidatos = list(siape_base.filter(sigla__iexact=suap.sigla).only('id', 'sigla', 'codigo', 'codigo_siorg')[:3])
        if len(candidatos) == 1:
            return candidatos[0], 'exato'
        if len(candidatos) > 1:
            return None, 'ambiguo'

        if try_uo_suffix and suap.uo_id and getattr(suap.uo, 'sigla', None):
            uo_sigla = suap.uo.sigla.strip()
            if uo_sigla:
                composta = f'{suap.sigla}/{uo_sigla}'
                candidatos = list(siape_base.filter(sigla__iexact=composta).only('id', 'sigla', 'codigo', 'codigo_siorg')[:3])
                if len(candidatos) == 1:
                    return candidatos[0], 'uo-suffix'
                if len(candidatos) > 1:
                    return None, 'ambiguo'

        return None, None

    # ---------- handle ----------
    def handle(self, *args, **options):
        commit = options.get('commit', False)
        overwrite = options.get('overwrite', False)
        include_already_set = options.get('include_already_set', False)
        uo_id = options.get('uo_id')
        sigla_filter = options.get('sigla')
        try_uo_suffix = not options.get('no_uo_suffix', False)

        # SUAPs elegíveis
        suap_qs = Setor.objects.filter(codigo__isnull=True, excluido=False)

        if not include_already_set and not overwrite:
            suap_qs = suap_qs.filter(Q(codigo_siorg__isnull=True) | Q(codigo_siorg=''))

        if uo_id is not None:
            suap_qs = suap_qs.filter(uo_id=uo_id)

        if sigla_filter:
            siglas = [s.strip() for s in sigla_filter.split(',') if s.strip()]
            suap_qs = suap_qs.filter(sigla__in=siglas)

        total = suap_qs.count()
        if total == 0:
            self.stdout.write(self.style.WARNING('Nenhum Setor SUAP elegível encontrado.'))
            return

        self.stdout.write(f'Encontrados {total} setores SUAP para processar.')
        self.stdout.write('Modo: ' + ('COMMIT (vai gravar alterações)' if commit else 'DRY-RUN (apenas simulação)'))
        if include_already_set:
            self.stdout.write('Incluindo SUAPs com codigo_siorg já definido.')
        if overwrite:
            self.stdout.write('Overwrite ATIVADO: codigo_siorg existente no SUAP será sobrescrito.')
        self.stdout.write('Fallback UO: ' + ('ativado' if try_uo_suffix else 'desativado'))

        # Base SIAPE
        siape_base = Setor.objects.filter(codigo__isnull=False, excluido=False)

        ok, ok_equiv, ok_exato, ok_uo_suffix = 0, 0, 0, 0
        not_found, multiples, skipped, siape_sem_siorg = 0, 0, 0, 0

        ctx = transaction.atomic
        with ctx():
            sp = transaction.savepoint()

            for suap in suap_qs.iterator(chunk_size=500):
                # Se SUAP já tem codigo_siorg e não vamos sobrescrever, pula
                if suap.codigo_siorg and not overwrite:
                    skipped += 1
                    self.stdout.write(self.style.NOTICE(f'[SKIP] SUAP id={suap.id} sigla={suap.sigla} já possui codigo_siorg={suap.codigo_siorg}.'))
                    continue

                # 1) Tenta por equivalência
                siape = self._siape_por_equivalencia(suap, siape_base)
                origem = 'equivalencia' if siape else None

                # 2) Se não achou por equivalência, tenta por sigla / sigla+UO
                if not siape:
                    siape, origem = self._siape_por_sigla(suap, siape_base, try_uo_suffix=try_uo_suffix)

                    if origem == 'ambiguo':
                        multiples += 1
                        self.stdout.write(self.style.WARNING(f'[AMBÍGUO] SUAP id={suap.id} sigla={suap.sigla}: múltiplos SIAPE por sigla.'))
                        continue

                # 3) Se ainda não tem SIAPE correspondente
                if not siape:
                    not_found += 1
                    self.stdout.write(
                        self.style.WARNING(f'[NÃO ENCONTRADO] SUAP id={suap.id} sigla={suap.sigla}: sem SIAPE correspondente (equivalência/sigla).')
                    )
                    continue

                # 4) Se SIAPE não tem codigo_siorg, não há o que copiar
                siape_siorg = (siape.codigo_siorg or '').strip()
                if not siape_siorg:
                    siape_sem_siorg += 1
                    self.stdout.write(
                        f'[SIAPE SEM SIORG] SUAP id={suap.id} sigla={suap.sigla} -> SIAPE id={siape.id} sigla={siape.sigla} sem codigo_siorg.'
                    )
                    continue

                # 5) Se SUAP já tem o mesmo valor, ok=igual
                if suap.codigo_siorg == siape_siorg:
                    ok += 1
                    if origem == 'equivalencia':
                        ok_equiv += 1
                    elif origem == 'uo-suffix':
                        ok_uo_suffix += 1
                    else:
                        ok_exato += 1
                    self.stdout.write(f'[OK=igual/{origem}] SUAP id={suap.id} sigla={suap.sigla} já possui codigo_siorg={siape_siorg}.')
                    continue

                # 6) Atualiza SUAP.codigo_siorg
                suap.codigo_siorg = siape_siorg
                suap.save(update_fields=['codigo_siorg'])
                ok += 1
                if origem == 'equivalencia':
                    ok_equiv += 1
                elif origem == 'uo-suffix':
                    ok_uo_suffix += 1
                else:
                    ok_exato += 1

                self.stdout.write(
                    self.style.SUCCESS(
                        f'[OK/{origem}] SUAP id={suap.id} sigla={suap.sigla} => codigo_siorg={siape_siorg} '
                        f'(de SIAPE id={siape.id} sigla={siape.sigla}).'
                    )
                )

            if not commit:
                transaction.savepoint_rollback(sp)

        # Resumo
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'Concluído. Sucessos: {ok} (por equivalência={ok_equiv}, exato={ok_exato}, uo-suffix={ok_uo_suffix})'))
        self.stdout.write(self.style.WARNING(f'SIAPE sem SIORG: {siape_sem_siorg}'))
        self.stdout.write(self.style.WARNING(f'Não encontrados: {not_found}'))
        self.stdout.write(self.style.WARNING(f'Ambíguos: {multiples}'))
        self.stdout.write(self.style.NOTICE(f'Pulados (já tinham codigo_siorg): {skipped}'))
