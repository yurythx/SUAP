import csv
import re

from djtools.management.commands import BaseCommandPlus
from rh.models import Setor


class Command(BaseCommandPlus):
    def get_setores_e_areas_vinculacao(self):
        def get_numero(s):
            r = re.findall(r'\d+', s)
            if r:
                return int(r[0])
            else:
                return None

        csv_setores = """setor_id,area_1,area_2,area_3
        2288,[13],[3],[14]
        2331,[13],[3],[14]
        2569,[13],[3],[14]
        2396,[13],[6],[3]
        2407,[13],[3],[14]
        2255,[13],[3],[14]
        2257,[13],[3],[14]
        2321,[13],[3],[14]
        2404,[13],[6],[3]
        2390,[11],[17],
        2395,[3],[13],[14]
        2383,[13],[6],[3]
        2389,[13],[3],[14]
        2398,[13],[3],[14]
        2448,[11],[17],
        2384,[13],[6],[3]
        2260,[13],[6],[3]
        2423,[13],[6],[3]
        2336,[16],[10],[5]
        2399,[13],[6],[3]
        2467,[13],[3],[14]
        2446,[13],[6],[3]
        2410,[13],[3],[14]
        2393,[13],[6],[3]
        2471,[5],[3],
        2256,[13],[3],[14]
        2297,[13],[3],[14]
        2298,[13],[3],[14]
        2316,[6],,
        2350,[13],[3],[14]
        2408,[6],,
        2409,[5],[3],[13]
        2415,[4],[3],[5]
        2469,[9],[16],
        2472,[4],[5],[3]
        2483,[13],[14],
        2507,[13],[14],[3]
        2508,[13],[3],[14]
        2556,[5],[3],[13]
        2602,[13],[3],[14]
        2388,[13],[6],[3]
        2417,[13],[6],[3]
        2391,[13],[6],[3]
        2268,[13],[6],[3]
        2351,[13],[3],[14]
        2406,[13],[3],[14]
        2590,[9],[12],[16]
        2360,[13],[6],[3]
        2263,[13],[6],[3]
        2285,[13],[3],[14]
        2340,[5],[3],[13]
        2593,[16],[4],[5]
        2599,[16],[1],[5]
        2600,[16],[1],[5]
        2601,[9],[16],[10]
        2266,[9],[12],[10]
        2272,[8],[16],[10]
        2275,[1],[16],[9]
        2318,[2],[1],[16]
        2319,[2],[1],[16]
        2320,[2],[1],[16]
        2330,[10],[16],[1]
        2439,[10],[16],[1]
        2563,[9],[16],[1]"""
        lsetores = csv_setores.split()

        reader = csv.DictReader(lsetores, delimiter=',')
        dados = {}
        areas_nnome = ['area_1', 'area_2', 'area_3']
        for row in reader:
            dados[row['setor_id']] = []
            for area_nome in areas_nnome:
                if row[area_nome]:
                    dados[row['setor_id']].append(get_numero(row[area_nome]))
        return dados

    def handle(self, **options):
        setores = self.get_setores_e_areas_vinculacao()
        for setor_id, areas in setores.items():
            try:
                setor = Setor.objects.suap_ativos().get(id=setor_id)
                print(f'Setor {setor_id}, associando áreas de vinculação>: {areas}')
                setor.areas_vinculacao.add(*areas)
            except Setor.DoesNotExist:
                print(f'Setor não encontrado: {setor_id}')
