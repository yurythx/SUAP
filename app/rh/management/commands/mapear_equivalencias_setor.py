# rh/management/commands/mapear_equivalencias_setor.py
from django.core.management.base import BaseCommand
from django.db import transaction, IntegrityError
from django.db.models import Q
from rh.models import Setor  # ajuste o import conforme seu projeto


class Command(BaseCommand):
    help = (
        'Mapeia equivalência SUAP->SIAPE por sigla: para cada Setor SUAP (codigo NULL), '
        'procura um Setor SIAPE (codigo NOT NULL) com a mesma sigla e grava em equivalencia_codigo. '
        'Se não encontrar, tenta <sigla>/<sigla_da_UO> (ex.: COINRE/RE).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--commit',
            action='store_true',
            help='Efetiva as alterações (por padrão é um dry-run).',
        )
        parser.add_argument(
            '--overwrite',
            action='store_true',
            help='Se já houver equivalencia_codigo no SUAP, sobrescreve com o valor encontrado.',
        )
        parser.add_argument(
            '--include-already-set',
            action='store_true',
            help='Inclui SUAPs que já possuem equivalência no processamento (útil com --overwrite).',
        )
        parser.add_argument(
            '--uo-id',
            type=int,
            default=None,
            help='Opcional: filtra os setores SUAP por uma UO específica (id).',
        )
        parser.add_argument(
            '--sigla',
            type=str,
            default=None,
            help='Opcional: processa apenas a(s) sigla(s) informada(s). Aceita vírgulas.',
        )
        parser.add_argument(
            '--no-uo-suffix',
            action='store_true',
            help='Desativa o fallback de tentar <sigla>/<sigla_da_UO> quando não houver match exato.',
        )

    def _buscar_candidatos_siape(self, suap, siape_base, try_uo_suffix=True):
        """
        1) Tenta match por sigla exata (case-insensitive).
        2) Se não achar e try_uo_suffix=True, tenta '<sigla>/<sigla_da_UO>'.
        Retorna (candidatos, origem), onde origem é 'exato' ou 'uo-suffix'.
        """
        # 1) Match exato pela sigla
        candidatos = list(siape_base.filter(sigla__iexact=suap.sigla).only('id', 'sigla', 'codigo')[:3])
        if candidatos:
            return candidatos, 'exato'

        # 2) Fallback: sigla + '/' + UO.sigla
        if try_uo_suffix and suap.uo_id and getattr(suap.uo, 'sigla', None):
            uo_sigla = suap.uo.sigla.strip()
            if uo_sigla:
                composta = f'{suap.sigla}/{uo_sigla}'
                candidatos = list(siape_base.filter(sigla__iexact=composta).only('id', 'sigla', 'codigo')[:3])
                if candidatos:
                    return candidatos, 'uo-suffix'

        return [], None

    def handle(self, *args, **options):
        commit = options['commit']
        overwrite = options['overwrite']
        include_already_set = options['include_already_set']
        uo_id = options['uo_id']
        sigla_filter = options['sigla']
        try_uo_suffix = not options.get('no_uo_suffix', False)

        # Base: Setores SUAP (codigo is NULL)
        suap_qs = Setor.objects.filter(codigo__isnull=True, excluido=False)

        if not include_already_set:
            suap_qs = suap_qs.filter(Q(equivalencia_codigo__isnull=True) | Q(equivalencia_codigo=''))

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
            self.stdout.write('Incluindo SUAPs que já possuem equivalência.')
        if overwrite:
            self.stdout.write('Overwrite ATIVADO: equivalências existentes serão sobrescritas.')
        if try_uo_suffix:
            self.stdout.write('Fallback por UO ativado: tentando <sigla>/<sigla_da_UO> quando necessário.')
        else:
            self.stdout.write('Fallback por UO desativado.')

        # Query base de SIAPE: codigo NOT NULL
        siape_base = Setor.objects.filter(codigo__isnull=False, excluido=False)

        ok, not_found, multiples, skipped_exists, errors = 0, 0, 0, 0, 0
        ok_exato, ok_uo_suffix = 0, 0

        # Em dry-run, também usamos transação e fazemos rollback
        ctx = transaction.atomic
        with ctx():
            savepoint = transaction.savepoint()
            for suap in suap_qs.iterator(chunk_size=500):
                if suap.equivalencia_codigo and not overwrite:
                    skipped_exists += 1
                    self.stdout.write(
                        self.style.NOTICE(f'[SKIP] SUAP id={suap.id} sigla={suap.sigla} já possui equivalência ({suap.equivalencia_codigo}).')
                    )
                    continue

                candidatos, origem = self._buscar_candidatos_siape(suap, siape_base, try_uo_suffix=try_uo_suffix)

                if len(candidatos) == 0:
                    not_found += 1
                    msg_uo = ''
                    if try_uo_suffix and suap.uo_id and getattr(suap.uo, 'sigla', None):
                        msg_uo = f' e também {suap.sigla}/{suap.uo.sigla}'
                    self.stdout.write(
                        self.style.WARNING(f'[NÃO ENCONTRADO] SUAP id={suap.id} sigla={suap.sigla}: não há SIAPE com sigla={suap.sigla}{msg_uo}.')
                    )
                    continue

                if len(candidatos) > 1:
                    multiples += 1
                    ids = ', '.join(f'{c.id}:{c.sigla}:{c.codigo}' for c in candidatos)
                    self.stdout.write(self.style.WARNING(f'[AMBÍGUO] SUAP id={suap.id} sigla={suap.sigla}: múltiplos SIAPE encontrados ({ids}).'))
                    continue

                siape = candidatos[0]
                novo_codigo = siape.codigo

                if suap.equivalencia_codigo == novo_codigo:
                    ok += 1
                    if origem == 'uo-suffix':
                        ok_uo_suffix += 1
                    else:
                        ok_exato += 1
                    self.stdout.write(f'[OK=igual] SUAP id={suap.id} sigla={suap.sigla} já aponta para {novo_codigo} ({origem or "exato"}).')
                    continue

                try:
                    with transaction.atomic():
                        suap.equivalencia_codigo = novo_codigo
                        suap.save(update_fields=['equivalencia_codigo'])
                    ok += 1
                    if origem == 'uo-suffix':
                        ok_uo_suffix += 1
                    else:
                        ok_exato += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'[OK/{origem or "exato"}] SUAP id={suap.id} sigla={suap.sigla} '
                            f'=> equivalencia_codigo={novo_codigo} (SIAPE sigla={siape.sigla})'
                        )
                    )
                except IntegrityError as ie:
                    errors += 1
                    self.stdout.write(self.style.ERROR(f'[ERRO INTEGRIDADE] SUAP id={suap.id} sigla={suap.sigla}: {ie.__class__.__name__}: {ie}'))
                except Exception as e:
                    errors += 1
                    self.stdout.write(self.style.ERROR(f'[ERRO] SUAP id={suap.id} sigla={suap.sigla}: {e.__class__.__name__}: {e}'))

            if not commit:
                transaction.savepoint_rollback(savepoint)

        # Resumo
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'Concluído. Sucessos: {ok} (exato={ok_exato}, uo-suffix={ok_uo_suffix})'))
        self.stdout.write(self.style.WARNING(f'Não encontrados: {not_found}'))
        self.stdout.write(self.style.WARNING(f'Ambíguos: {multiples}'))
        self.stdout.write(self.style.NOTICE(f'Pulados (já tinham equivalência): {skipped_exists}'))
        if errors:
            self.stdout.write(self.style.ERROR(f'Erros: {errors}'))
