# ruff: noqa: RUF001, PLE2515
import re

from djtools.management.commands import BaseCommandPlus
from edu.models import AtividadeComplementar, Componente, TipoAtividadeComplementar

pattern = '^[!-ÿ]{1}[ -ÿ]{0,}[!-ÿ]{1}|[!-ÿ]{1}$'


def replace_invalid_characters(s):
    for k, v in {
        'ç': 'ç',
        'ã': 'ã',
        'í': 'í',
        'ê': 'ê',
        'é': 'é',
        'á': 'á',
        '’': "'",
        'à': 'à',
        'ó': 'ó',
        '\t': ' ',
        '\n': ' ',
        'â': 'â',
        'ô': 'ô',
        '-': '-',
        ':': '-',
        'ﬁ': 'fi',
        '􀀿t': 'tit',
        'É': 'É',
        '': '',
        'ú': 'ú',
        '•': '-',
        '​': ' ',
        '􀀿': 'tiv',
        'ĩ': 'í',
        '‐': '-',
        'õ': 'õ',
        'ś': 's',
        ' ́': '',
        'Â': 'Â',
        '…': '...',
        '\x02': '',
        '\x1f': '',
    }.items():
        s = s.replace(k, v)
    return s


class Command(BaseCommandPlus):
    def add_arguments(self, parser):
        parser.add_argument('--commit', action='store_true', help='Realiza as alterações')

    def handle(self, *args, **options):
        commit = options.get('commit')
        for c in Componente.objects.all():
            r1 = re.findall(pattern, c.descricao)
            if len(r1) != 1:
                descricao = replace_invalid_characters(c.descricao)
                self.stdout.write('{}\n{}\n{}\n'.format(c.pk, c.descricao.replace('\n', ''), descricao))
                Componente.objects.filter(pk=c.pk).update(descricao=descricao) if commit else None
            r2 = re.findall(pattern, c.descricao_historico)
            if len(r2) != 1:
                descricao_historico = replace_invalid_characters(c.descricao_historico)
                self.stdout.write('{}\n{}\n{}\n'.format(c.pk, c.descricao_historico.replace('\n', ''), descricao_historico))
                Componente.objects.filter(pk=c.pk).update(descricao_historico=descricao_historico) if commit else None

        for a in AtividadeComplementar.objects.all():
            r3 = re.findall(pattern, a.descricao)
            if len(r3) != 1:
                descricao = replace_invalid_characters(a.descricao.replace('\n', '').replace('\r', ''))
                self.stdout.write('{}\n{}\n{}\n'.format(a.pk, a.descricao.replace('\n', '').replace('\r', ''), descricao))
                AtividadeComplementar.objects.filter(pk=a.pk).update(descricao=descricao) if commit else None

        for a in TipoAtividadeComplementar.objects.all():
            r4 = re.findall(pattern, a.descricao)
            if len(r4) != 1:
                descricao = replace_invalid_characters(a.descricao.replace('\n', '').replace('\r', ''))
                self.stdout.write('{}\n{}\n{}\n'.format(a.pk, a.descricao.replace('\n', '').replace('\r', ''), descricao))
                TipoAtividadeComplementar.objects.filter(pk=a.pk).update(descricao=descricao) if commit else None
