"""Aplica às bases de dados os metadados DCAT-BR de ``dados_abertos/metadados/conjuntos.json``.

O arquivo é a fonte revisável (no MR) da descrição, tags, tema, licença, cobertura e ODS de cada
conjunto publicado, e da descrição de cada recurso. As bases são localizadas pelo ``nome`` (slug no
CKAN) e os recursos pelo nome dentro da base; o que o arquivo não cita fica como está. Campo
ausente ou vazio no arquivo não apaga o valor existente; campo declarado é a verdade, e reaplicar
desfaz a edição feita no admin. Por isso o ``padrao`` só traz o que difere do default do model.

A gravação passa pelo ``save()`` dos models, e por isso **reabre a análise do LAI** das bases cuja
descrição, tags, tema ou licença mudaram e de todas cujos recursos mudaram: a nova descrição é o
que vai ao portal e precisa ser liberada antes do próximo sync. A sincronização com o CKAN não é
feita aqui.

Aplicação é manual e idempotente. Uso:
``python manage.py aplicar_metadados_conjuntos [--simular] [--arquivo caminho.json]``.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from dados_abertos.models import BaseDados, Licenca, RecursoDados, Tema

ARQUIVO_PADRAO = Path(__file__).resolve().parents[2] / 'metadados' / 'conjuntos.json'

CAMPOS_DATA = ('cobertura_temporal_inicio', 'cobertura_temporal_fim')
CAMPOS_DIRETOS = (
    'titulo',
    'notas',
    'tags',
    'versao',
    'autor',
    'autor_email',
    'mantenedor',
    'mantenedor_email',
    'cobertura_espacial',
    'valor_cobertura_espacial',
    'granularidade_espacial',
    'observancia_legal',
    'ods',
    'dados_genero',
    'dados_raca_etnia',
    *CAMPOS_DATA,
)


def _licenca(dados: dict) -> Licenca:
    """Licença do arquivo, localizada pelo código CKAN; criada ou completada se preciso."""
    licenca = Licenca.objects.filter(codigo_ckan=dados['codigo_ckan']).first()
    if licenca is None:
        licenca, _ = Licenca.objects.get_or_create(nome=dados['nome'], defaults={'descricao': dados.get('descricao', '')})
        licenca.codigo_ckan = dados['codigo_ckan']
        licenca.save()
    return licenca


def _valor(campo: str, valor):
    return datetime.date.fromisoformat(valor) if campo in CAMPOS_DATA else valor


def _aplicar_campos(base: BaseDados, conjunto: dict) -> list[str]:
    """Copia para a base os campos preenchidos no arquivo; devolve os que mudaram."""
    alterados = []
    for campo in CAMPOS_DIRETOS:
        if conjunto.get(campo) in (None, '', []):
            continue
        valor = _valor(campo, conjunto[campo])
        if getattr(base, campo) != valor:
            setattr(base, campo, valor)
            alterados.append(campo)
    if conjunto.get('tema'):
        tema, _ = Tema.objects.get_or_create(nome=conjunto['tema'])
        if base.tema_id != tema.pk:
            base.tema = tema
            alterados.append('tema')
    return alterados


def _aplicar_recursos(base: BaseDados, descricoes: dict[str, str]) -> tuple[int, list[str]]:
    """Grava a descrição de cada recurso citado; devolve quantos mudaram e os nomes não encontrados."""
    alterados = 0
    recursos = {r.nome: r for r in RecursoDados.objects.filter(dataset=base)}
    for nome, descricao in descricoes.items():
        recurso = recursos.get(nome)
        if recurso is None or recurso.descricao == descricao:
            continue
        recurso.descricao = descricao
        recurso.save()
        alterados += 1
    return alterados, sorted(set(descricoes) - set(recursos))


class Command(BaseCommand):
    help = 'Aplica às bases de dados os metadados DCAT-BR do arquivo de conjuntos (sem sincronizar com o CKAN).'

    def add_arguments(self, parser):
        parser.add_argument('--arquivo', default=str(ARQUIVO_PADRAO), help='JSON com os metadados (padrão: o versionado no app).')
        parser.add_argument('--simular', action='store_true', help='Mostra o que mudaria, sem gravar.')

    def handle(self, *args, **options):
        dados = json.loads(Path(options['arquivo']).read_text(encoding='utf-8'))
        with transaction.atomic():
            licenca = _licenca(dados['licenca'])
            for conjunto in dados['conjuntos']:
                self._aplicar(conjunto, {**dados.get('padrao', {}), **conjunto}, licenca)
            if options['simular']:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING('Simulação: nada foi gravado.'))

    def _aplicar(self, conjunto: dict, valores: dict, licenca: Licenca) -> None:
        base = BaseDados.objects.filter(nome=conjunto['nome']).first()
        if base is None:
            self.stdout.write(self.style.ERROR(f'{conjunto["nome"]}: base não encontrada, ignorada.'))
            return
        alterados = _aplicar_campos(base, valores)
        if base.licenca_id != licenca.pk:
            base.licenca = licenca
            alterados.append('licenca')
        if alterados:
            base.save()
        recursos, ausentes = _aplicar_recursos(base, conjunto.get('recursos', {}))
        if alterados or recursos:
            self.stdout.write(f'{base.nome}: campos {", ".join(alterados) or "-"}; {recursos} recurso(s) descrito(s).')
        else:
            self.stdout.write(f'{base.nome}: nada a alterar.')
        for nome in ausentes:
            self.stdout.write(self.style.WARNING(f'{base.nome}: recurso "{nome}" não encontrado.'))
