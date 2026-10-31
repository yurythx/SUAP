"""Importa organograma e servidores de um órgão que não é a prefeitura.

A sigla da instituição precisa estar definida antes das pessoas, porque a senha
inicial usa essa sigla. Não aponta para o banco da prefeitura.

    python manage.py importar_orgao unidades.csv usuarios.csv --sigla SIGLA --nome "Nome do órgão" --uf MT --municipio "Cidade" --dominio exemplo.gov.br
"""

from __future__ import annotations

import os

from django.core.management.base import CommandError

from rh.importacao_prefeitura import LIMITE_SIGLA
from rh.management.commands.importar_prefeitura import Command as ImportarPrefeitura

BANCO_DA_PREFEITURA = '192.168.110.30'


class Command(ImportarPrefeitura):
    help = 'Importa organograma e servidores de outro órgão. Pode ser executado de novo sem duplicar.'
    recusa_orgao_coder = False

    def add_arguments(self, parser) -> None:
        parser.add_argument('unidades', help='CSV de unidades, no mesmo formato da prefeitura.')
        parser.add_argument('usuarios', help='CSV de usuários, no mesmo formato da prefeitura.')
        parser.add_argument('--sigla', required=True, help='Sigla da raiz. Vira a sigla da instituição.')
        parser.add_argument('--nome', required=True, help='Nome do órgão e da unidade raiz.')
        parser.add_argument('--uf', required=True, help='UF, com duas letras.')
        parser.add_argument('--municipio', required=True, help='Município da unidade raiz.')
        parser.add_argument('--dominio', required=True, help='Domínio de e-mail institucional, sem @.')

    def handle(self, *args, **options) -> None:
        if os.environ.get('DATABASE_HOST', '').strip() == BANCO_DA_PREFEITURA:
            raise CommandError('DATABASE_HOST aponta para o banco da prefeitura. Use a instância deste órgão.')
        options['sigla'] = options['sigla'].strip().upper()
        options['nome'] = options['nome'].strip()
        options['uf'] = options['uf'].strip().upper()
        options['municipio'] = options['municipio'].strip()
        options['dominio'] = options['dominio'].strip().lower()
        self._validar_identidade(options)
        super().handle(*args, **options)

    def _validar_identidade(self, options: dict[str, str]) -> None:
        if options['sigla'] == 'PMR':
            raise CommandError('A sigla PMR é a prefeitura. Este comando não grava nela.')
        self._exigir_sigla(options['sigla'])
        self._exigir_nome(options['nome'])
        if len(options['uf']) != 2 or not options['municipio']:
            raise CommandError('Informe a UF com duas letras e o município.')
        if not options['dominio'] or ' ' in options['dominio']:
            raise CommandError('Informe o domínio institucional, sem espaços.')

    def _exigir_sigla(self, sigla: str) -> None:
        if not sigla or len(sigla) > LIMITE_SIGLA:
            raise CommandError(f'A sigla da raiz precisa ter de 1 a {LIMITE_SIGLA} caracteres.')

    def _exigir_nome(self, nome: str) -> None:
        if not nome or len(nome) > 100:
            raise CommandError('O nome da raiz precisa ter de 1 a 100 caracteres.')
