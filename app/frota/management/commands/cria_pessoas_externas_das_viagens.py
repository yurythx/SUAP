import tqdm

from djtools.management.commands import BaseCommandPlus
from frota.models import Viagem, ViagemAgendamento
from rh.models import PessoaExterna

# comando que deve ser executado após a migração 0030 para gerar as pessoas externas dos passageiros e interessados sem sub_instance de pessoa fisica


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        for viagem in tqdm.tqdm(Viagem.objects.filter(passageiros__isnull=False)):
            if viagem.passageiros.count() != viagem.vinculos_passageiros.count():
                for passageiro in viagem.passageiros.all():
                    if passageiro.vinculo_set.exists():
                        viagem.vinculos_passageiros.add(passageiro.vinculo_set.first())
                    else:
                        nova_pessoa = PessoaExterna()
                        nova_pessoa.nome = passageiro.nome
                        nova_pessoa.sexo = passageiro.sexo
                        nova_pessoa.cpf = passageiro.cpf
                        nova_pessoa.nascimento_data = passageiro.nascimento_data
                        nova_pessoa.pessoa_fisica = passageiro
                        nova_pessoa.save()
                        viagem.vinculos_passageiros.add(nova_pessoa.vinculos.first())

        for viagem in tqdm.tqdm(ViagemAgendamento.objects.filter(passageiros__isnull=False)):
            if viagem.passageiros.count() != viagem.vinculos_passageiros.count():
                for passageiro in viagem.passageiros.all():
                    if passageiro.vinculo_set.exists():
                        viagem.vinculos_passageiros.add(passageiro.vinculo_set.first())
                    else:
                        nova_pessoa = PessoaExterna()
                        nova_pessoa.nome = passageiro.nome
                        nova_pessoa.sexo = passageiro.sexo
                        nova_pessoa.cpf = passageiro.cpf
                        nova_pessoa.nascimento_data = passageiro.nascimento_data
                        nova_pessoa.pessoa_fisica = passageiro
                        nova_pessoa.save()
                        viagem.vinculos_passageiros.add(nova_pessoa.vinculos.first())

        for viagem in tqdm.tqdm(ViagemAgendamento.objects.filter(interessados__isnull=False)):
            if viagem.interessados.count() != viagem.vinculos_interessados.count():
                for passageiro in viagem.interessados.all():
                    if passageiro.vinculo_set.exists():
                        viagem.vinculos_interessados.add(passageiro.vinculo_set.first())
                    else:
                        nova_pessoa = PessoaExterna()
                        nova_pessoa.nome = passageiro.nome
                        nova_pessoa.sexo = passageiro.sexo
                        nova_pessoa.cpf = passageiro.cpf
                        nova_pessoa.nascimento_data = passageiro.nascimento_data
                        nova_pessoa.pessoa_fisica = passageiro
                        nova_pessoa.save()
                        viagem.vinculos_interessados.add(nova_pessoa.vinculos.first())
