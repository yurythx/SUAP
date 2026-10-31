"""Relatório das violações da cota de deliberações por categoria da comissão (somente leitura).

A trava da cota (``status_cota_categoria``) vale para votos novos. Este command aponta o que ficou
para trás: escopos em que uma categoria já tem mais votos do que o limite permite, e membros ativos
sem categoria definida, que a partir da trava não conseguem deliberar.

Nada é alterado aqui. A correção caso a caso continua sendo feita com ``reverter_deliberacao_item``
e ``reverter_deliberacao_final``, que apagam voto assinado e exigem decisão humana sobre qual cai.

Votos de desempate não entram na contagem (não consomem cota) e votos de quem não é mais membro
ativo da comissão ativa ficam fora, por não terem categoria a que sejam atribuíveis hoje.

Uso:
    python manage.py verificar_cota_categoria_crsc
"""

from collections import defaultdict

from django.core.management.base import BaseCommand

from rsc_tae.models import (
    CategoriaMembroComissaoRSCTae,
    DeliberacaoItemCRSCRSCTae,
    MembroComissaoRSCTae,
    VotoDeliberacaoFinalRSCTae,
)
from rsc_tae.views._helpers import categoria_por_vinculo, limite_deliberacoes_por_categoria


class Command(BaseCommand):
    help = 'Lista as violações da cota de deliberações por categoria da comissão RSC-TAE (não altera nada).'

    def handle(self, *args, **options) -> None:
        limite = limite_deliberacoes_por_categoria()
        categorias = categoria_por_vinculo()
        nomes = dict(CategoriaMembroComissaoRSCTae.objects.values_list('id', 'nome'))

        self.stdout.write(f'Limite por categoria em cada escopo: {limite}')

        achados = [
            *self._violacoes_de_item(limite, categorias, nomes),
            *self._violacoes_da_final(limite, categorias, nomes),
            *self._membros_sem_categoria(),
        ]
        if not achados:
            self.stdout.write(self.style.SUCCESS('Nenhuma violação encontrada.'))
            return

        for linha in achados:
            self.stdout.write(self.style.WARNING(linha))
        self.stdout.write(f'Total de apontamentos: {len(achados)}')

    def _contar_por_escopo(self, votos, categorias: dict, chave) -> dict:
        """``{(escopo, categoria_id): total}`` dos votos normais atribuíveis a uma categoria."""
        contagem = defaultdict(int)
        for voto in votos:
            if voto.desempate:
                continue
            categoria_id = categorias.get(voto.deliberado_por_vinculo_id)
            if categoria_id:
                contagem[(chave(voto), categoria_id)] += 1
        return contagem

    def _violacoes_de_item(self, limite: int, categorias: dict, nomes: dict) -> list[str]:
        """Anexos em que uma categoria gastou mais votos do que o limite."""
        votos = DeliberacaoItemCRSCRSCTae.objects.all().only('processo_id', 'anexo_id', 'deliberado_por_vinculo_id', 'desempate')
        contagem = self._contar_por_escopo(votos, categorias, lambda voto: (voto.processo_id, voto.anexo_id))

        linhas = []
        for (escopo, categoria_id), total in sorted(contagem.items()):
            if total <= limite:
                continue
            processo_id, anexo_id = escopo
            categoria = nomes.get(categoria_id, categoria_id)
            linhas.append(f'- processo {processo_id}, anexo {anexo_id}: categoria {categoria} com {total} votos (limite {limite}).')
        return linhas

    def _violacoes_da_final(self, limite: int, categorias: dict, nomes: dict) -> list[str]:
        """Processos em que uma categoria gastou mais votos do que o limite na deliberação final."""
        votos = VotoDeliberacaoFinalRSCTae.objects.all().only('processo_id', 'deliberado_por_vinculo_id', 'desempate')
        contagem = self._contar_por_escopo(votos, categorias, lambda voto: voto.processo_id)

        linhas = []
        for (processo_id, categoria_id), total in sorted(contagem.items()):
            if total <= limite:
                continue
            categoria = nomes.get(categoria_id, categoria_id)
            linhas.append(f'- processo {processo_id}, deliberação final: categoria {categoria} com {total} votos (limite {limite}).')
        return linhas

    def _membros_sem_categoria(self) -> list[str]:
        """Membros ativos da comissão ativa que ficaram sem categoria (cadastro legado)."""
        membros = MembroComissaoRSCTae.objects.filter(comissao__ativa=True, ativo=True, categoria__isnull=True).select_related('vinculo__pessoa')
        return [
            f'- {membro.vinculo.pessoa.nome} é membro ativo sem categoria — não consegue deliberar até o RH definir a categoria.'
            for membro in membros
        ]
