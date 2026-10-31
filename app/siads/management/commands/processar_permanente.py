from django.db.models.functions import Length
from fuzzywuzzy import fuzz
from nltk.corpus import stopwords
from nltk.tokenize import RegexpTokenizer
from tqdm import tqdm

from djtools.management.commands import BaseCommandPlus
from patrimonio.models import EntradaPermanente
from rh.models import UnidadeOrganizacional
from siads.models import GrupoMaterialPermanente, MaterialPermanente


class Command(BaseCommandPlus):
    tokenizer = RegexpTokenizer(r'\w+')

    def processar_nome(self, nome):
        tokens = self.tokenizer.tokenize(nome.lower())
        words = []

        for token in tokens:
            if token not in stopwords.words('portuguese') and token not in words:
                words.append(token)

        return ' '.join(sorted(words))

    def processar_entradas(self, qs, uo):
        processados = {}

        for entrada_permanente in tqdm(qs.order_by('-text_len')):
            nome_processado = self.processar_nome(entrada_permanente.descricao)
            grupo = None

            for grp, grupo_obj in processados.items():
                if fuzz.token_set_ratio(grp, nome_processado) > 90:
                    grupo = grupo_obj
                    break

            if grupo is None:
                grupo = GrupoMaterialPermanente()
                grupo.uo = uo
                grupo.nome = entrada_permanente.descricao[0:1024]
                grupo.sentenca = nome_processado
                grupo.save()
                processados[nome_processado] = grupo

            s_entrada_permanente = MaterialPermanente()
            s_entrada_permanente.grupo = grupo
            s_entrada_permanente.entrada = entrada_permanente
            s_entrada_permanente.nome_original = entrada_permanente.descricao
            s_entrada_permanente.nome_processado = nome_processado
            s_entrada_permanente.save()

    def handle(self, *args, **options):
        uos = UnidadeOrganizacional.objects.all()

        for uo in uos:
            print(f'Processando entradas para {uo}')
            qs = EntradaPermanente.objects.filter(entrada__uo=uo).annotate(text_len=Length('descricao'))
            if qs.exists():
                self.processar_entradas(qs, uo)

        print(f'Numero de entradas: {MaterialPermanente.objects.all().count()}')
        print(f'Grupos criados:      {GrupoMaterialPermanente.objects.all().count()}')
