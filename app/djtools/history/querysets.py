from functools import partial

from django.db import transaction
from django.db.models.query import QuerySet

from .constants import STATUS_UPDATED
from .serializers import process_data
from .validations import check_history_disabled

original_update = QuerySet.update
original_delete = QuerySet.delete


def update(self, **kwargs):
    skip_history = kwargs.pop('skip_history', False)
    if check_history_disabled(self.model) or skip_history:
        rows = original_update(self, **kwargs)
    else:
        ids = self.values_list('id', flat=True)
        old_objs = list(self.model._base_manager.filter(pk__in=ids).order_by('id'))
        rows = original_update(self, **kwargs)
        for new_obj, old_obj in zip(self.order_by('id'), old_objs, strict=False):
            transaction.on_commit(partial(lambda new_obj, old_obj: process_data(new_obj, old_obj, STATUS_UPDATED), new_obj, old_obj))
    return rows


update.alters_data = True

QuerySet.update = update
