import re

from djtools.management.commands import BaseCommandPlus
from gerenciador_projetos.enums import PrioridadeTarefa, SituacaoTarefa
from gerenciador_projetos.models import HistoricoEvolucao


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        self.corrigir_historico('Situação', SituacaoTarefa.choices, int)
        self.corrigir_historico('Prioridade', PrioridadeTarefa.choices, str)

    def corrigir_historico(self, nome_campo, choices, tipo_chave_choice):
        dict_choices = dict(choices)
        string_padrao = f'<li>Campo <b>{nome_campo}</b> alterado de '

        # Padrão para capturar os valores brutos dentro de <i></i>
        pattern = re.compile(rf'{string_padrao}<i>([^<]+)</i> para <i>([^<]+)</i>\. </li>')

        # Filtrar historicos de forma mais genérica para o campo
        historicos = HistoricoEvolucao.objects.filter(comentario__contains=string_padrao, tarefa_id=1701)
        for historico in historicos:
            match = pattern.search(historico.comentario)
            if match:
                valor_antigo_raw, valor_novo_raw = match.groups()

                # Tenta converter para o tipo esperado, usando o valor raw como fallback
                try:
                    valor_antigo_key = tipo_chave_choice(valor_antigo_raw)
                except ValueError:
                    valor_antigo_key = valor_antigo_raw

                try:
                    valor_novo_key = tipo_chave_choice(valor_novo_raw)
                except ValueError:
                    valor_novo_key = valor_novo_raw

                valor_antiga_desc = dict_choices.get(valor_antigo_key, valor_antigo_raw)
                valor_nova_desc = dict_choices.get(valor_novo_key, valor_novo_raw)

                historico.comentario = historico.comentario.replace(f'<i>{valor_antigo_raw}</i>', f'<i>{valor_antiga_desc}</i>')
                historico.comentario = historico.comentario.replace(f'<i>{valor_novo_raw}</i>', f'<i>{valor_nova_desc}</i>')
                historico.save()
