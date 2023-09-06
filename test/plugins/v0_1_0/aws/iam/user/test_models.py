from __future__ import annotations

import pytest
from pydantic import ValidationError

from iambic.core.template_generation import merge_model
from iambic.plugins.v0_1_0.aws.iam.user.models import Credentials, Group, UserProperties


def test_merge_group(aws_accounts):
    existing_group = Group(
        group_name="foo",
        expires_at="tomorrow",
    )
    new_group = Group(group_name="foo")
    merged_group: Group = merge_model(new_group, existing_group, aws_accounts)
    assert existing_group.expires_at != new_group.expires_at
    assert merged_group.expires_at == existing_group.expires_at


def test_merge_user_properties(aws_accounts):
    existing_groups = [
        {
            "group_name": "bar",
            "expires_at": "tomorrow",
        }
    ]
    existing_properties = UserProperties(
        user_name="foo",
        groups=existing_groups,
    )
    new_groups = [
        {
            "group_name": "baz",
        },
        {
            "group_name": "bar",
        },
    ]
    new_properties = UserProperties(
        user_name="foo",
        groups=new_groups,
    )
    merged_properties: UserProperties = merge_model(
        new_properties, existing_properties, aws_accounts
    )
    assert merged_properties.groups[0].group_name == "bar"
    assert (
        merged_properties.groups[0].expires_at
        == existing_properties.groups[0].expires_at
    )
    assert merged_properties.groups[1].group_name == "baz"


def test_access_keys_sorting_with_none():
    access_keys = None
    credentials = Credentials(
        access_keys=access_keys,
    )
    # because 123 is before ABC
    assert credentials.access_keys is None


def test_access_keys_sorting():
    access_keys = [
        {
            "id": "ABC",
            "enabled": True,
            "last_used": "Never",
        },
        {
            "id": "123",
            "enabled": True,
            "last_used": "Never",
        },
    ]
    credentials = Credentials(
        access_keys=access_keys,
    )
    # because 123 is before ABC
    assert credentials.access_keys[0].id == "123"
    assert credentials.access_keys[1].id == "ABC"


def test_credentials_sorting():
    credentials = [
        {"included_accounts": ["account_b"]},
        {"included_accounts": ["account_a"]},
    ]
    properties = UserProperties(
        user_name="foo",
        credentials=credentials,
    )

    # because account_a is before account_b
    assert properties.credentials[0].included_accounts[0] == "account_a"
    assert properties.credentials[1].included_accounts[0] == "account_b"


def test_credentials_sorting_with_single_credential():
    credential = {"included_accounts": ["account_a"]}
    properties = UserProperties(
        user_name="foo",
        credentials=credential,
    )

    # because account_a is before account_b
    assert properties.credentials.included_accounts[0] == "account_a"


def test_credentials_sorting_with_no_credential():
    properties = UserProperties(
        user_name="foo",
        credentials=None,
    )

    # because account_a is before account_b
    assert properties.credentials is None


def test_user_properties_sorting():
    groups = [
        {
            "group_name": "baz",
        },
        {
            "group_name": "bar",
        },
    ]
    properties = UserProperties(
        user_name="foo",
        groups=groups,
    )
    assert properties.groups[0].group_name == "bar"
    assert properties.groups[1].group_name == "baz"


def test_user_properties_tags_too_many_tags():
    tags_1 = [
        {"key": "apple", "value": "red"},
    ] * 51
    with pytest.raises(ValidationError):
        assert UserProperties(user_name="foo", tags=tags_1)


def test_user_properties_tags_max_tags():
    tags_1 = [
        {"key": "apple", "value": "red"},
    ] * 50
    assert UserProperties(user_name="foo", tags=tags_1)


def test_user_path_validation():
    path = [
        {"included_accounts": ["account_1", "account_2"], "path": "/engineering"},
        {"included_accounts": ["account_3"], "path": "/finance"},
    ]
    properties_1 = UserProperties(user_name="foo", path=path)
    path_1 = properties_1.path
    path_2 = list(reversed(properties_1.path))
    assert path_1 != path_2  # because we reverse the list
    properties_1.path = path_2
    assert (
        properties_1.path == path_2
    )  # double check the list is reversed because validation doesn't happen after creation
    properties_1.validate_model_afterward()
    assert properties_1.path == path_1


def test_user_permissions_boundary_validation():
    permissions_boundary = [
        {
            "included_accounts": ["account_1", "account_2"],
            "policy_arn": "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy",
        },
        {
            "included_accounts": ["account_3"],
            "policy_arn": "arn:aws:iam::aws:policy/AmazonEKSServicePolicy",
        },
    ]
    properties_1 = UserProperties(
        user_name="foo", permissions_boundary=permissions_boundary
    )
    permissions_boundary_models_1 = properties_1.permissions_boundary
    permissions_boundary_models_2 = list(reversed(properties_1.permissions_boundary))
    assert (
        permissions_boundary_models_1 != permissions_boundary_models_2
    )  # because we reverse the list
    properties_1.permissions_boundary = permissions_boundary_models_2
    assert (
        properties_1.permissions_boundary == permissions_boundary_models_2
    )  # double check the list is reversed because validation doesn't happen after creation
    properties_1.validate_model_afterward()
    assert properties_1.permissions_boundary == permissions_boundary_models_1
