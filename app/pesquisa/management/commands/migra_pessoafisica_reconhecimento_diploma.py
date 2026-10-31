import tqdm

from djtools.management.commands import BaseCommandPlus
from pesquisa.models import ReconhecimentoDiploma
from rh.models import PessoaExterna


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        for registro in tqdm.tqdm(ReconhecimentoDiploma.objects.all()):
            if registro.requerente.get_vinculo():
                registro.vinculo_requerente = registro.requerente.get_vinculo()
            else:
                pf_dict = registro.requerente.__dict__.copy()
                pf_dict['matricula'] = registro.requerente.documento_identificador
                pf_dict['pessoa_fisica_id'] = registro.requerente.id

                pf_dict.pop('_state')
                pf_dict.pop('id')
                pf_dict.pop('eh_aluno')
                pf_dict.pop('eh_prestador')
                pf_dict.pop('eh_servidor')
                pf_dict.pop('documento_identificador')
                pf_dict.pop('user_id')
                pf_dict.pop('search_fields_optimized')
                pf_dict.pop('pessoa_ptr_id')
                pf_dict.pop('uuid')
                pf_dict.pop('passaporte')
                pf_dict.pop('genero')
                relacionamento = PessoaExterna.objects.create(**pf_dict)
                registro.vinculo_requerente = relacionamento.get_vinculo()
            registro.cadastrado_em = registro.data_cadastro
            registro.save()
