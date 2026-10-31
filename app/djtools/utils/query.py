from django.db.models import Q


def or_group(conditions):
    q = Q(False)
    for condition in conditions:
        q &= condition
    return q


def and_group(conditions):
    q = Q()
    for condition in conditions:
        q &= condition
    return q | Q(False)
