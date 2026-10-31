import pandas as pd
from django.conf import settings
from django.db import transaction

from djtools.management.commands import BaseCommandPlus
from edu.models import Cartorio, Cidade, Estado, OrgaoEmissorRg, Pais


def _read(nome):
    return pd.read_excel(f'{settings.BASE_DIR}/comum/cadastros_basicos/{nome}', header=None)


class Command(BaseCommandPlus):
    def add_arguments(self, parser):
        parser.add_argument('--paises', action='store_true', dest='paises', default=False, help='Importe apenas países')
        parser.add_argument('--estados', action='store_true', dest='estados', default=False, help='Importe apenas estados')
        parser.add_argument('--cidades', action='store_true', dest='cidades', default=False, help='Importe apenas cidades')
        parser.add_argument('--cartorios', action='store_true', dest='cartorios', default=False, help='Importe apenas cartórios')
        parser.add_argument('--emissoresrg', action='store_true', dest='emissoresrg', default=False, help='Importe apenas órgãos emissores de RG')

    @transaction.atomic
    def handle(self, *args, **options):
        verbose = options['verbosity']
        noargs = not any(options[k] for k in ('paises', 'estados', 'cidades', 'cartorios', 'emissoresrg'))

        if options['paises'] or noargs:
            self._importar_paises(verbose)
        if options['estados'] or noargs:
            self._importar_estados(verbose)
        if options['cidades'] or noargs:
            self._importar_cidades(verbose)
        if options['cartorios'] or noargs:
            self._importar_cartorios(verbose)
        if options['emissoresrg'] or noargs:
            self._importar_emissores_rg(verbose)

    def _importar_paises(self, verbose):
        if verbose:
            self.stdout.write('Importando Países')
        df = _read('paises.xls')
        existentes = set(Pais.objects.values_list('sigla', 'nome'))
        novos = []
        seen = set()
        for _i, row in df.iloc[1:].iterrows():
            sigla = row.iloc[0]
            nome = row.iloc[1].strip()
            key = (sigla, nome)
            if key in existentes or key in seen:
                continue
            seen.add(key)
            novos.append(Pais(sigla=sigla, nome=nome))
        Pais.objects.bulk_create(novos, batch_size=1000)

    def _importar_estados(self, verbose):
        if verbose:
            self.stdout.write('Importando Estados')
        df = _read('estados.xls')
        existentes = set(Estado.objects.values_list('id', flat=True))
        novos = [Estado(id=row.iloc[0], nome=row.iloc[1].strip()) for _i, row in df.iloc[1:].iterrows() if row.iloc[0] not in existentes]
        Estado.objects.bulk_create(novos, ignore_conflicts=True, batch_size=1000)

    def _importar_cidades(self, verbose):
        if verbose:
            self.stdout.write('Importando Cidades')
        df = _read('cidades.xls')
        existentes = set(Cidade.objects.values_list('id', flat=True))
        novos = []
        seen = set()
        for _i, row in df.iloc[1:].iterrows():
            cid = row.iloc[0]
            if cid in existentes or cid in seen:
                continue
            seen.add(cid)
            novos.append(
                Cidade(
                    id=cid,
                    estado_id=row.iloc[1],
                    nome=row.iloc[2].strip(),
                    cep_inicial=row.iloc[3],
                    cep_final=row.iloc[4],
                    codigo=cid,
                )
            )
        Cidade.objects.bulk_create(novos, ignore_conflicts=True, batch_size=1000)

        brasil = Pais.objects.filter(nome='Brasil').first()
        if brasil:
            Cidade.objects.filter(codigo__isnull=False, pais__isnull=True).update(pais_id=brasil.pk)

    def _importar_cartorios(self, verbose):
        if verbose:
            self.stdout.write('Importando Cartórios')
        df = _read('cartorios.xls')
        existentes = set(Cartorio.objects.values_list('id', flat=True))
        novos = []
        seen = set()
        for _i, row in df.iloc[1:].iterrows():
            cid_municipio = row.iloc[2]
            if not cid_municipio:
                continue
            pk = row.iloc[0]
            if pk in existentes or pk in seen:
                continue
            seen.add(pk)
            novos.append(Cartorio(id=pk, nome=row.iloc[1].strip(), cidade_id=cid_municipio, serventia=row.iloc[4]))
        Cartorio.objects.bulk_create(novos, ignore_conflicts=True, batch_size=1000)

    def _importar_emissores_rg(self, verbose):
        if verbose:
            self.stdout.write('Importando Órgãos Emissores de RG')
        df = _read('emissores_rg.xls')
        existentes = set(OrgaoEmissorRg.objects.values_list('id', flat=True))
        novos = []
        seen = set()
        for _i, row in df.iloc[1:].iterrows():
            pk = row.iloc[0]
            if pk in existentes or pk in seen:
                continue
            seen.add(pk)
            novos.append(OrgaoEmissorRg(id=pk, nome=row.iloc[1].strip()))
        OrgaoEmissorRg.objects.bulk_create(novos, ignore_conflicts=True, batch_size=1000)
