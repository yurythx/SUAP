from django.db.models import Q
from djtools.utils.query import and_group, or_group


class TestOrGroup:
    def test_or_group_with_single_condition(self):
        result = or_group([Q(a=1)])
        assert result == Q(False) & Q(a=1)

    def test_or_group_with_multiple_conditions(self):
        result = or_group([Q(a=1), Q(b=2)])
        assert result == Q(False) & Q(a=1) & Q(b=2)


class TestAndGroup:
    def test_and_group_with_single_condition(self):
        result = and_group([Q(a=1)])
        assert result == Q(a=1) | Q(False)

    def test_and_group_with_multiple_conditions(self):
        result = and_group([Q(a=1), Q(b=2)])
        assert result == (Q(a=1) & Q(b=2)) | Q(False)

    def test_and_group_empty(self):
        result = and_group([])
        assert result == Q() | Q(False)
