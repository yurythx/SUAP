from unittest.mock import Mock

import pytest

from djtools.utils.test import ignore_request_for_tests


@pytest.mark.parametrize(
    ('path', 'expected'),
    [
        ('/static/css/app.css', True),
        ('/admin/jsi18n/', True),
        ('/media/uploads/file.pdf', True),
        ('/some/path/script.js', True),
        ('/some/path/style.css', True),
        ('/admin/djtools/task/', False),
    ],
)
def test_ignore_request_for_tests(path, expected):
    request = Mock(path=path)
    assert ignore_request_for_tests(request) is expected
