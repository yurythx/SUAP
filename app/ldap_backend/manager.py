import operator
from functools import reduce

from django.db.models import Q

from djtools.db import models


class LdapQuerySet(models.QuerySet):
    def filter_by_query(self, query, search_fields):
        predicates = []
        for field in search_fields:
            predicate = (f'{field}__contains', query)
            predicates.append(Q(predicate))
        return self.filter(reduce(operator.or_, predicates))

    def filter_by_filterstr(self, filterstr):
        predicates = [tuple(filter.split('=')) for filter in filterstr.split(';')]
        q_list = [Q(item) for item in predicates]
        return self.filter(reduce(operator.or_, q_list))


class LdapUserManager(models.Manager):
    def get_queryset(self):
        return LdapQuerySet(self.model, using=self._db)

    def filter_by_query(self, query, search_fields=None):
        search_fields = search_fields or self.model.default_search_fields
        return self.get_queryset().filter_by_query(query, search_fields)

    def filter_by_filtestr(self, filterstr):
        return self.get_queryset().filter_by_filterstr(filterstr)
