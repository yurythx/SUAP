import tqdm

from ae.models import DemandaAlunoAtendida
from djtools.management.commands import BaseCommandPlus
from rh.models import PessoaExterna

# comando que deve ser executado após a migração 0082 para gerar as pessoas externas de DemandaAlunoAtendida


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        for registro in tqdm.tqdm(DemandaAlunoAtendida.objects.filter(responsavel__isnull=False, responsavel_vinculo__isnull=True)):
            if registro.responsavel.vinculo_set.exists():
                registro.responsavel_vinculo = registro.responsavel.vinculo_set.first()
                registro.save()
            else:
                nova_pessoa = PessoaExterna()
                nova_pessoa.nome = registro.responsavel.nome
                nova_pessoa.sexo = registro.responsavel.sexo
                nova_pessoa.cpf = registro.responsavel.cpf
                nova_pessoa.nascimento_data = registro.responsavel.nascimento_data
                nova_pessoa.pessoa_fisica = registro.responsavel
                nova_pessoa.save()
                registro.responsavel_vinculo = nova_pessoa.vinculos.first()
                registro.save()
