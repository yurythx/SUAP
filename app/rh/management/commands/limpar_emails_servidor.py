from __future__ import annotations

from argparse import ArgumentParser
from collections.abc import Iterator
from typing import Any

from django.apps import apps
from django.core.management import CommandError
from django.db import transaction
from django.db.models import Q

from djtools.management.commands import BaseCommandPlus
from djtools.utils import get_ldap_conf

# Atributos do AD que espelham o e-mail institucional do servidor (ver ldap_backend/utils.py
# e LdapConf.sync_user_emails). mail=institucional; extensionAttribute9=cópia do institucional
# p/ Campus ZL/EAD (Moodle). O acadêmico (extensionAttribute4) e o google (extensionAttribute5)
# NÃO são tocados: o próprio servidor limpa esses pela tela de e-mails.
ATTRS_LDAP_INSTITUCIONAIS = ['mail', 'extensionAttribute9']
# extensionAttribute8 espelha o e-mail secundário; só limpo com --secundario.
ATTR_LDAP_SECUNDARIO = 'extensionAttribute8'


class Command(BaseCommandPlus):
    help = 'Limpa o e-mail institucional de um ou mais servidores no banco e no LDAP/AD.'

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument('matriculas', nargs='*', type=str, help='Matrícula(s) do(s) servidor(es).')
        parser.add_argument(
            '--all',
            dest='all',
            action='store_true',
            help='Em vez de matrículas, processa todos os servidores cujo e-mail institucional é de domínio não institucional.',
        )
        parser.add_argument(
            '--secundario',
            action='store_true',
            help='Também limpa o e-mail pessoal do vínculo (usado na recuperação de senha).',
        )
        parser.add_argument('--no-ldap', dest='no_ldap', action='store_true', help='Não altera o LDAP/AD.')
        parser.add_argument('--dry-run', dest='dry_run', action='store_true', help='Apenas mostra o que seria feito.')

    def handle(self, *args: Any, **options: Any) -> None:
        conf = None if options['no_ldap'] else get_ldap_conf()
        if not options['no_ldap'] and not conf:
            raise CommandError('Nenhuma configuração LDAP ativa encontrada. Use --no-ldap para limpar apenas o banco.')

        for servidor in self._servidores(options):
            self._processar(servidor, conf, options['secundario'], options['dry_run'])

    def _servidores(self, options: dict[str, Any]) -> Iterator[Any]:
        if options['all'] == bool(options['matriculas']):
            raise CommandError('Informe matrícula(s) ou --all (um ou outro).')
        return self._afetados() if options['all'] else self._por_matricula(options['matriculas'])

    def _por_matricula(self, matriculas: list[str]) -> Iterator[Any]:
        Servidor = apps.get_model('rh', 'Servidor')
        for matricula in matriculas:
            servidor = Servidor.objects.select_related('pessoa_fisica').filter(matricula=matricula).first()
            if not servidor:
                self.stderr.write(f'Servidor {matricula} não encontrado.')
                continue
            yield servidor

    def _afetados(self) -> Iterator[Any]:
        """
        Seleciona os servidores cujo e-mail institucional é de domínio de terceiros.

        É o caso do servidor cedido/redistribuído, cujo SIAPE devolve o e-mail do órgão de origem:
        o valor era importado sem validação e o cron `sync_emails` o copiava para
        `User.email`, virando o e-mail de notificação da pessoa.

        Returns:
            Servidores a limpar, ordenados por matrícula.

        Raises:
            CommandError: Se `comum.dominios_institucionais` não estiver configurado, caso em que
                não há como distinguir domínio próprio de domínio de terceiros.
        """
        Servidor = apps.get_model('rh', 'Servidor')
        Configuracao = apps.get_model('comum', 'configuracao')

        dominios = [d.strip() for d in (Configuracao.get_valor_por_chave('comum', 'dominios_institucionais') or '').split(';') if d.strip()]
        if not dominios:
            raise CommandError('A configuração comum.dominios_institucionais está vazia: não há como identificar e-mail de domínio de terceiros.')

        eh_institucional = Q()
        for dominio in dominios:
            eh_institucional |= Q(email_institucional__icontains=dominio)

        afetados = Servidor.objects.select_related('pessoa_fisica').exclude(email_institucional='').exclude(eh_institucional).order_by('matricula')
        self.stdout.write(f'{afetados.count()} servidor(es) com e-mail institucional fora de {"; ".join(dominios)}.')
        return iter(afetados)

    def _processar(self, servidor: Any, conf: Any, secundario: bool, dry_run: bool) -> None:
        self.stdout.write(f'{servidor.matricula} - {servidor.pessoa_fisica.nome}')
        if dry_run:
            self.stdout.write('  [dry-run] banco: email_institucional, User.email')
            if secundario:
                self.stdout.write('  [dry-run] banco: Vinculo.email_pessoal')
            if conf:
                attrs = ATTRS_LDAP_INSTITUCIONAIS + ([ATTR_LDAP_SECUNDARIO] if secundario else [])
                self.stdout.write(f'  [dry-run] LDAP: {", ".join(attrs)} (apenas os presentes)')
            return
        # LDAP primeiro (operação falível/remota): se o AD estiver indisponível, o banco não é tocado.
        if conf:
            self._limpar_ldap(conf, servidor, secundario)
        self._limpar_db(servidor, secundario)

    @transaction.atomic
    def _limpar_db(self, servidor: Any, secundario: bool) -> None:
        Servidor = apps.get_model('rh', 'Servidor')
        User = apps.get_model('comum', 'User')

        # Só o institucional: acadêmico e google ficam, o próprio servidor limpa esses pela tela.
        Servidor.objects.filter(pk=servidor.pk).update(email_institucional='')
        # PessoaFisica.email/email_secundario migraram para Vinculo.email_pessoal. Não há mais espelho
        # do institucional a limpar; o que sobra é o sucessor do secundário, então segue atrás de --secundario
        # (é o e-mail de recuperação de senha do servidor: zerá-lo sem pedir o trancaria fora).
        if secundario:
            servidor.vinculos.update(email_pessoal='')
        User.objects.filter(username=servidor.matricula).update(email='')
        self.stdout.write('  banco limpo.')

    def _limpar_ldap(self, conf: Any, servidor: Any, secundario: bool) -> None:
        attrs = ATTRS_LDAP_INSTITUCIONAIS + ([ATTR_LDAP_SECUNDARIO] if secundario else [])
        ldap_user = conf.get_user(servidor.username, attrs=attrs)
        if not ldap_user:
            self.stdout.write(f'  usuário {servidor.username} não encontrado no LDAP.')
            return
        # MOD_DELETE só nos atributos presentes, senão o AD lança NO_SUCH_ATTRIBUTE.
        presentes = [attr for attr in attrs if attr in ldap_user]
        if not presentes:
            self.stdout.write('  LDAP já sem e-mails.')
            return
        conf.modify(servidor.username, dict.fromkeys(presentes), mod_list=dict.fromkeys(presentes, 'delete'))
        self.stdout.write(f'  LDAP limpo: {", ".join(presentes)}.')
