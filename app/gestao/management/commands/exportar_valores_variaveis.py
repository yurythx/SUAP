import json
import warnings

from django.core.cache import CacheKeyWarning
from django.core.management.base import BaseCommand, CommandError
from tqdm import tqdm

from gestao.models import VARIAVEIS_GRUPOS, Variavel
from rh.models import UnidadeOrganizacional

warnings.simplefilter('ignore', CacheKeyWarning)


class Command(BaseCommand):
    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument('--anomes', type=str, help='Usar no formato yyyymm')

    def get_detalhe_servidor(self, servidor):
        dservidor = {
            'matricula': servidor.matricula,
            'pessoa_fisica.nome_usual': servidor.pessoa_fisica.nome_usual,
            'pessoa_fisica.nome': servidor.pessoa_fisica.nome,
            'titulacao.nome': servidor.titulacao.nome if servidor.titulacao else '',
            'titulacao.codigo': servidor.titulacao.codigo if servidor.titulacao else '',
            'situacao.nome': servidor.situacao.nome,
            'situacao.codigo': servidor.situacao.codigo,
            'cargo_emprego.nome': servidor.cargo_emprego.nome,
            'cargo_emprego.codigo': servidor.cargo_emprego.codigo,
            'funcao.nome': servidor.funcao.nome if servidor.funcao else '',
            'funcao.codigo': servidor.funcao.codigo if servidor.funcao else '',
            'funcao_codigo': '',
            'jornada_trabalho.nome': servidor.jornada_trabalho.nome if servidor.jornada_trabalho else '',
            'jornada_trabalho.codigo': servidor.jornada_trabalho.codigo if servidor.jornada_trabalho else '',
        }
        if servidor.funcao and servidor.funcao_codigo:
            dservidor['funcao_codigo'] = f'{servidor.funcao.codigo}-{servidor.funcao_codigo}'
        if servidor.setor and servidor.setor.uo:
            dservidor.update(
                {
                    'setor.uo.sigla': servidor.setor.uo.sigla,
                    'setor.uo.nome': servidor.setor.uo.nome,
                }
            )
        if servidor.setor_exercicio and servidor.setor_exercicio.uo:
            dservidor.update(
                {
                    'setor_exercicio.uo.sigla': servidor.setor_exercicio.uo.sigla,
                    'setor_exercicio.uo.nome': servidor.setor_exercicio.uo.nome,
                }
            )
        if servidor.setor_lotacao and servidor.setor_lotacao.uo:
            dservidor.update(
                {
                    'setor_lotacao.uo.sigla': servidor.setor_lotacao.uo.sigla if servidor.setor_lotacao else '',
                    'setor_lotacao.uo.nome': servidor.setor_lotacao.uo.nome if servidor.setor_lotacao else '',
                }
            )
        if servidor.setor_lotacao and servidor.setor_lotacao.uo and servidor.setor_lotacao.uo.equivalente:
            dservidor.update(
                {
                    'setor_lotacao.uo.equivalente.sigla': servidor.setor_lotacao.uo.equivalente.sigla if servidor.setor_lotacao else '',
                    'setor_lotacao.uo.equivalente.nome': servidor.setor_lotacao.uo.equivalente.nome if servidor.setor_lotacao else '',
                }
            )

        return dservidor

    def handle(self, *args, **options):
        anomes = ''
        if options.get('anomes') is None:
            raise CommandError('Argumento mês de competência não informado. Infomrar no formato yyyymm')
        else:
            anomes = options['anomes']

        tipo = 'Rh'
        vinculo_aluno_convenio = 'AlunosTodos'

        print('Processando variáveis gerais...')
        variaveis = Variavel.objects.all().order_by('sigla')

        if tipo != 'Todas':
            for vg in VARIAVEIS_GRUPOS:
                if vg.get('grupo') == tipo:
                    subgrupo = vg.get('subgrupo')
                    if not subgrupo or subgrupo == vinculo_aluno_convenio:
                        variaveis = variaveis.filter(sigla__in=vg.get('variaveis'))
                        break

        variaveis_cache = {}
        variaveis_cache['GERAL'] = {}
        for variavel in tqdm(variaveis):
            valor = Variavel.recuperar_valor(variavel.pk, 0, True)
            valor = str(valor).replace('.', '')
            variaveis_cache['GERAL'][variavel.sigla] = int(valor)

        print('Processando variáveis por UO...')
        total_variaveis = len(variaveis_cache['GERAL'].keys())
        uos = UnidadeOrganizacional.objects.suap().all()
        for i, variavel in enumerate(variaveis.filter(sigla__in=variaveis_cache['GERAL'].keys())):
            variaveis_cache[variavel.sigla] = {}
            print(f'Processando variável {i} de {total_variaveis}')
            for uo in tqdm(uos):
                if variaveis_cache[variavel.sigla].get(uo.sigla, None) is None:
                    variaveis_cache[variavel.sigla][uo.sigla] = {}
                valor = Variavel.recuperar_valor(variavel.pk, uo.pk, True)
                valor = str(valor).replace('.', '')
                variaveis_cache[variavel.sigla][uo.sigla] = int(valor)

                variaveis_cache[variavel.sigla][uo.sigla] = {'servidores': {}, 'valor': int(float(valor))}
                qs_servidores = variavel.get_querysets(uo)[0].order_by('pessoa_fisica__nome')
                for servidor in qs_servidores:
                    dservidor = self.get_detalhe_servidor(servidor)
                    variaveis_cache[variavel.sigla][uo.sigla]['servidores'][servidor.matricula] = dservidor

        filename = f'variaveis_{anomes}.json'

        with open(filename, 'w') as fp:
            json.dump(variaveis_cache, fp, indent=4)

        print()
