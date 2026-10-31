#!/usr/bin/env python
# -*- coding: UTF-8 -*-

from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options):
        print('Agendamento ok')
