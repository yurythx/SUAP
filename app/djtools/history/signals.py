from django.db import transaction
from django.db.models.signals import post_save, pre_delete, pre_save
from django.dispatch.dispatcher import receiver

from .constants import STATUS_CREATED, STATUS_DELETED, STATUS_UPDATED, STATUS_VIEWED
from .serializers import process_data
from .validations import check_history_disabled


@receiver(pre_save)
def pre_save_signal(sender, instance, **kwargs):
    if check_history_disabled(instance):
        return
    if getattr(instance, 'pk', False):
        status = STATUS_UPDATED
        old_instance = sender.objects.filter(pk=instance.pk).first()
        transaction.on_commit(lambda: process_data(instance, old_instance, status))


@receiver(post_save)
def post_save_signal(sender, instance, created, **kwargs):
    if check_history_disabled(instance):
        return
    if created:
        transaction.on_commit(lambda: process_data(instance, None, STATUS_CREATED))


@receiver(pre_delete)
def pre_delete_signal(sender, instance, **kwargs):
    if check_history_disabled(instance):
        return
    process_data(instance, None, STATUS_DELETED)


def log_view_object(instance):
    if check_history_disabled(instance):
        return
    transaction.on_commit(lambda: process_data(instance, None, STATUS_VIEWED))
