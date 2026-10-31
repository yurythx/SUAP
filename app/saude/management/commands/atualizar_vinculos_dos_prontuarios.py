import tqdm

from djtools.management.commands import BaseCommandPlus
from djtools.utils import can_hard_delete_fast
from saude.models import Atendimento, Prontuario


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        for prontuario in tqdm.tqdm(Prontuario.objects.filter(vinculo__isnull=True)):
            if Atendimento.objects.filter(prontuario=prontuario).exists():
                if Atendimento.objects.filter(prontuario=prontuario).order_by('-id')[0].prestador_servico:
                    prontuario.vinculo = Atendimento.objects.filter(prontuario=prontuario).order_by('-id')[0].prestador_servico.get_vinculo()
                elif Atendimento.objects.filter(prontuario=prontuario).order_by('-id')[0].aluno:
                    prontuario.vinculo = Atendimento.objects.filter(prontuario=prontuario).order_by('-id')[0].aluno.get_vinculo()
                elif Atendimento.objects.filter(prontuario=prontuario).order_by('-id')[0].servidor:
                    prontuario.vinculo = Atendimento.objects.filter(prontuario=prontuario).order_by('-id')[0].servidor.get_vinculo()
                else:
                    prontuario.vinculo = Atendimento.objects.filter(prontuario=prontuario).order_by('-id')[0].pessoa_externa.get_vinculo()
                prontuario.save()
            elif can_hard_delete_fast(prontuario):
                prontuario.delete()
