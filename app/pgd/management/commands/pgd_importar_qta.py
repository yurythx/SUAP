import csv
import os

import tqdm
from django.conf import settings
from django.db import transaction
from django.utils import termcolors

from djtools.management.commands import BaseCommandPlus
from pgd.models import (
    Atividade,
    AtividadeEntrega,
    FaixaComplexidade,
    ServicoAtividade,
    SubtematicaAtividade,
    TematicaAtividade,
)

COMPLEXIDADES = ('I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII')


def bold(s):
    return termcolors.make_style(opts=('bold',))(s)


class Command(BaseCommandPlus):
    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(bold('Importando QTA\n------------------------'))

        path_arquivo = os.path.join(settings.BASE_DIR, 'pgd/management/commands/QTA_formato_importacao.csv')
        with open(path_arquivo) as arquivo_csv:
            dados = list(csv.DictReader(arquivo_csv, delimiter='#'))
        self.stdout.write(bold('>>> Dados carregados OK'))

        resumo = []
        resumo.append(self._criar_tematicas(dados))
        resumo.append(self._criar_subtematicas(dados))
        resumo.append(self._criar_servicos(dados))
        self._criar_faixas()
        resumo.append(self._criar_atividades(dados))

        self.stdout.write(bold('RESUMO'))
        for r in resumo:
            self.stdout.write(r)

    def _criar_tematicas(self, dados):
        self.stdout.write(bold('>>> Criando as temáticas'))
        criado = repetido = 0
        existentes = set(TematicaAtividade.objects.values_list('titulo', flat=True))
        novos = []
        seen = set()
        for dado in dados:
            tematica = (dado.get('tematica') or '').strip()
            if not tematica:
                continue
            if tematica in existentes or tematica in seen:
                repetido += 1
                continue
            seen.add(tematica)
            novos.append(TematicaAtividade(titulo=tematica))
            criado += 1
        TematicaAtividade.objects.bulk_create(novos)
        self.stdout.write(bold('>>> Criando as temáticas OK'))
        return f'>>> Resumo das temáticas. Criado: {criado}. Repetido (não criado): {repetido}'

    def _criar_subtematicas(self, dados):
        self.stdout.write(bold('>>> Criando as subtemáticas'))
        tematica_por_titulo = {t.titulo: t for t in TematicaAtividade.objects.all()}
        criado = repetido = 0
        existentes = set(SubtematicaAtividade.objects.values_list('tematica_id', 'titulo'))
        novos = []
        seen = set()
        for dado in dados:
            tematica = (dado.get('tematica') or '').strip()
            subtematica = (dado.get('subtematica') or '').strip()
            if not (tematica and subtematica):
                continue
            t = tematica_por_titulo.get(tematica)
            if t is None:
                repetido += 1
                continue
            key = (t.id, subtematica)
            if key in existentes or key in seen:
                repetido += 1
                continue
            seen.add(key)
            novos.append(SubtematicaAtividade(tematica=t, titulo=subtematica))
            criado += 1
        SubtematicaAtividade.objects.bulk_create(novos)
        self.stdout.write(bold('>>> Criando as subtemáticas OK'))
        return f'>>> Resumo das subtemáticas. Criado: {criado}. Repetido (não criado): {repetido}'

    def _criar_servicos(self, dados):
        self.stdout.write(bold('>>> Criando os servicos'))
        sub_por_chave = {(s.tematica_id, s.titulo): s for s in SubtematicaAtividade.objects.select_related('tematica').all()}
        tematica_id_por_titulo = {t.titulo: t.id for t in TematicaAtividade.objects.all()}
        criado = repetido = 0
        existentes = set(ServicoAtividade.objects.values_list('subtematica_id', 'titulo'))
        novos = []
        seen = set()
        for dado in dados:
            tematica = (dado.get('tematica') or '').strip()
            subtematica = (dado.get('subtematica') or '').strip()
            servico = (dado.get('servico') or '').strip()
            if not (tematica and subtematica and servico):
                continue
            t_id = tematica_id_por_titulo.get(tematica)
            sub = sub_por_chave.get((t_id, subtematica)) if t_id else None
            if sub is None:
                repetido += 1
                continue
            key = (sub.id, servico)
            if key in existentes or key in seen:
                repetido += 1
                continue
            seen.add(key)
            novos.append(ServicoAtividade(subtematica=sub, titulo=servico))
            criado += 1
        ServicoAtividade.objects.bulk_create(novos)
        self.stdout.write(bold('>>> Criando os servicos OK'))
        return f'>>> Resumo dos servicos. Criado: {criado}. Repetido (não criado): {repetido}'

    def _criar_faixas(self):
        existentes = set(FaixaComplexidade.objects.values_list('complexidade', flat=True))
        novas = [FaixaComplexidade(complexidade=c) for c in COMPLEXIDADES if c not in existentes]
        if novas:
            FaixaComplexidade.objects.bulk_create(novas)

    def _criar_atividades(self, dados):
        self.stdout.write(bold('>>> Criando as atividades'))
        tematica_por_titulo = {t.titulo: t for t in TematicaAtividade.objects.all()}
        sub_por_chave = {(s.tematica_id, s.titulo): s for s in SubtematicaAtividade.objects.all()}
        servico_por_chave = {(s.subtematica_id, s.titulo): s for s in ServicoAtividade.objects.all()}
        criado = repetido = 0

        for dado in tqdm.tqdm(dados):
            tematica = (dado.get('tematica') or '').strip()
            atividade = (dado.get('atividade') or '').strip()
            if not (tematica and atividade):
                repetido += 1
                continue

            t = tematica_por_titulo.get(tematica)
            if t is None:
                repetido += 1
                continue

            subtematica_txt = (dado.get('subtematica') or '').strip()
            servico_txt = (dado.get('servico') or '').strip()
            sub = sub_por_chave.get((t.id, subtematica_txt)) if subtematica_txt else None
            servico = servico_por_chave.get((sub.id, servico_txt)) if (sub and servico_txt) else None

            if servico:
                obj, created = Atividade.objects.get_or_create(tematica=t, subtematica=sub, servico=servico, titulo=atividade)
            elif sub:
                obj, created = Atividade.objects.get_or_create(tematica=t, subtematica=sub, titulo=atividade)
            else:
                obj, created = Atividade.objects.get_or_create(tematica=t, titulo=atividade)

            if not created:
                repetido += 1
                continue
            criado += 1

            # ComplexidadeAtividade já é criada por Atividade.save() para cada FaixaComplexidade.
            entregas_raw = dado.get('entregas')
            if entregas_raw:
                AtividadeEntrega.objects.bulk_create([AtividadeEntrega(atividade=obj, titulo=e.replace('#', ' ')) for e in entregas_raw.split(';')])
                obj.ativo = True
                obj.save()

        return f'>>> Resumo das atividades. Criado: {criado}. Repetido (não criado): {repetido}'
