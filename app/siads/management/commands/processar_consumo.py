from django.db.models.functions import Length
from fuzzywuzzy import fuzz
from nltk.corpus import stopwords
from nltk.tokenize import RegexpTokenizer
from tqdm import tqdm

from almoxarifado.models import MaterialConsumo, UnidadeMedida
from djtools.management.commands import BaseCommandPlus
from siads.models import GrupoMaterialConsumo
from siads.models import MaterialConsumo as SMaterialConsumo


class Command(BaseCommandPlus):
    tokenizer = RegexpTokenizer(r'\w+')

    def processar_nome(self, nome):
        tokens = self.tokenizer.tokenize(nome.lower())
        words = []

        for token in tokens:
            if token not in stopwords.words('portuguese') and token not in words:
                words.append(token)

        return ' '.join(sorted(words))

    def processar_materiais(self, qs):
        processados = {}

        for material in tqdm(qs.order_by('-text_len')):
            nome_processado = self.processar_nome(material.nome)
            grupo = None

            for grp, grp_grupo in processados.items():
                if fuzz.token_set_ratio(grp, nome_processado) > 90:
                    grupo = grp_grupo
                    break

            if grupo is None:
                grupo = GrupoMaterialConsumo()
                grupo.nome = material.nome[0:250]
                grupo.sentenca = nome_processado
                grupo.unidade = material.unidade is not None and material.unidade.nome or ''
                grupo.save()
                processados[nome_processado] = grupo

            smaterial = SMaterialConsumo()
            smaterial.grupo = grupo
            smaterial.material = material
            smaterial.nome_original = material.nome
            smaterial.nome_processado = nome_processado
            smaterial.save()

    def handle(self, *args, **options):
        unidades = UnidadeMedida.objects.all()

        # Processa materiais com unidade de medida definido
        for unidade in unidades:
            print(f'Processando a unidade de medida "{unidade.nome}"')

            qs = (
                MaterialConsumo.objects.com_estoque().filter(unidade=unidade).exclude(materialconsumo__isnull=False).annotate(text_len=Length('nome'))
            )
            self.processar_materiais(qs)

        # Processa materiais sem unidade de medida definido
        qs = MaterialConsumo.objects.com_estoque().filter(unidade__isnull=True).annotate(text_len=Length('nome'))
        self.processar_materiais(qs)

        print(f'Numero de materiais: {SMaterialConsumo.objects.all().count()}')
        print(f'Grupos criados:      {GrupoMaterialConsumo.objects.all().count()}')
