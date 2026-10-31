#!/usr/bin/env python
# -*- coding: UTF-8 -*-

from cron import models
from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def add_arguments(self, parser):
        parser.add_argument('args', nargs='*', type=str)

    def handle(self, *args, **options):
        agendamento = models.Agendamento.objects.get(id=int(args[0]))
        agendamento.executar()
