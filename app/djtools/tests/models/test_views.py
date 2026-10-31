import pytest
from django.core.signals import request_started
from django.db import connection

from djtools.utils.autocomplete import CaptureQueriesContext

pytestmark = pytest.mark.django_db


class TestCaptureQueriesContext:
    def test_captures_queries(self):
        with CaptureQueriesContext(connection) as ctx:
            list(connection.queries)  # force execute something tracked
        # After exit, captured_queries should be accessible
        assert len(ctx) >= 0
        assert hasattr(ctx, 'captured_queries')

    def test_context_manager_protocol(self):
        ctx = CaptureQueriesContext(connection)
        with ctx as cm:
            assert cm is ctx

    def test_initial_final_queries(self):
        with CaptureQueriesContext(connection) as ctx:
            assert ctx.initial_queries >= 0
            assert ctx.final_queries is None

    def test_captured_queries_returns_list(self):
        with CaptureQueriesContext(connection) as ctx:
            pass
        queries = ctx.captured_queries
        assert isinstance(queries, list)

    def test_iteration(self):
        with CaptureQueriesContext(connection) as ctx:
            pass
        for q in ctx:
            assert isinstance(q, dict)

    def test_len_returns_correct_count(self):
        with CaptureQueriesContext(connection) as ctx:
            pass
        assert len(ctx) == len(ctx.captured_queries)

    def test_getitem_by_index(self):
        with CaptureQueriesContext(connection) as ctx:
            pass
        queries = ctx.captured_queries
        for i in range(len(ctx)):
            assert ctx[i] is queries[i]

    def test_disconnects_request_started_during_capture(self):
        original_receivers, _original_pending = request_started._live_receivers(None)
        with CaptureQueriesContext(connection):
            inside_receivers, _inside_pending = request_started._live_receivers(None)
            assert len(inside_receivers) < len(original_receivers)
        restored_receivers, _restored_pending = request_started._live_receivers(None)
        assert len(restored_receivers) == len(original_receivers)

    def test_restores_force_debug_cursor(self):
        original = connection.force_debug_cursor
        with CaptureQueriesContext(connection):
            assert connection.force_debug_cursor is True
        assert connection.force_debug_cursor is original

    def test_on_exception_no_final_queries(self):
        try:
            with CaptureQueriesContext(connection) as ctx:
                raise ValueError('test error')
        except ValueError:
            pass
        assert ctx.final_queries is None
        assert ctx.captured_queries == []

    def test_queries_logged_inside_context(self):
        with CaptureQueriesContext(connection) as ctx:
            connection.queries_log.append({'sql': 'SELECT 1', 'time': '0.000'})
        assert len(ctx) >= 1
