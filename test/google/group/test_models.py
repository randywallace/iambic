from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from iambic.google.group.models import get_group_template

VALUE_UNDER_TEST = {
    "members": [
        {
            "kind": "admin#directory#member",
            "etag": '"FOO"',
            "id": "123",
            "email": "admin@example.com",
            "role": "OWNER",
            "type": "USER",
            "status": "ACTIVE",
        },
        {
            "kind": "admin#directory#member",
            "etag": '"BAR"',
            "id": "456",
            "email": "unverifable@external.com",
            "role": "MEMBER",
            "type": "USER",
        },
    ]
}

TEST_GOOGLE_GROUP = {
    "email": "example-google-group@example.com",
    "name": "Example Google Group",
    "description": "Google Group under test",
}


@pytest.fixture
def google_group_service():
    mock = MagicMock()
    mock.members = MagicMock()
    mock.members().list = MagicMock()
    mock.members().list().execute = MagicMock(return_value=VALUE_UNDER_TEST)
    return mock


@pytest.mark.asyncio
async def test_get_group_template(google_group_service):
    template = await get_group_template(
        google_group_service, TEST_GOOGLE_GROUP, "example-com"
    )
    assert len(template.properties.members) == len(VALUE_UNDER_TEST["members"])