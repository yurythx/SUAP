from django.db import models


def register_signals_abono_chefia():
    from ponto.models import AbonoChefia

    models.signals.post_save.connect(sender=AbonoChefia, receiver=AbonoChefia.processa_abono_chefia_salvo)
