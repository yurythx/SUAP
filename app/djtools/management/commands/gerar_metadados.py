from django.db import DatabaseError, transaction
from django.utils import translation

from djtools.management.commands import BaseCommandPlus
from djtools.metadados import Metadados, coletar, deduplicar, models_no_escopo
from djtools.models import MetadadoCampo, MetadadoChoice, MetadadoTabela, MetadadoTransicao

CHAVES_UNICAS = {
    'tabelas': lambda o: (o.tabela,),
    'campos': lambda o: (o.tabela, o.coluna),
    'choices': lambda o: (o.tabela, o.coluna, o.valor),
    'transicoes': lambda o: (o.tabela, o.coluna, o.nome, o.origem),
}


class Command(BaseCommandPlus):
    help = 'Recria as tabelas metadados_* (tabelas, campos, choices e transições) a partir dos models.'

    def handle(self, *args, **options) -> None:
        with translation.override('pt-br'):
            coletados, erros = self._coletar_todos()
        listas = {
            'tabelas': [c.tabela for c in coletados],
            'campos': [o for c in coletados for o in c.campos],
            'choices': [o for c in coletados for o in c.choices],
            'transicoes': [o for c in coletados for o in c.transicoes],
        }
        for nome, objetos in listas.items():
            listas[nome], avisos = deduplicar(objetos, CHAVES_UNICAS[nome])
            for aviso in avisos:
                self.stdout.write(self.style.WARNING(aviso))
        self._tentar_gravar(listas)
        self.stdout.write(
            f'Metadados: {len(listas["tabelas"])} tabelas, {len(listas["campos"])} campos, '
            f'{len(listas["choices"])} choices, {len(listas["transicoes"])} transições; {len(erros)} models com erro'
        )
        for erro in erros:
            self.stdout.write(self.style.ERROR(erro))

    def _coletar_todos(self) -> tuple[list[Metadados], list[str]]:
        coletados: list[Metadados] = []
        erros: list[str] = []
        for model in models_no_escopo():
            try:
                coletados.append(coletar(model))
            except Exception as e:
                erros.append(f'{model._meta.label}: {e}')
        return coletados, erros

    def _tentar_gravar(self, listas: dict[str, list]) -> None:
        """Grava os metadados sem abortar o `sync`: em erro de banco, o rollback preserva o conteúdo anterior."""
        try:
            self._gravar(listas)
        except DatabaseError as e:
            self.stdout.write(self.style.ERROR(f'Metadados não gravados: {e}'))

    def _gravar(self, listas: dict[str, list]) -> None:
        with transaction.atomic():
            for model, nome in (
                (MetadadoTabela, 'tabelas'),
                (MetadadoCampo, 'campos'),
                (MetadadoChoice, 'choices'),
                (MetadadoTransicao, 'transicoes'),
            ):
                # Sem `.delete()`: o receiver global de `pre_delete` (history) impede o fast-delete e dispara um sinal por linha.
                consulta = model.objects.all()
                consulta._raw_delete(consulta.db)
                model.objects.bulk_create(listas[nome], batch_size=2000)
