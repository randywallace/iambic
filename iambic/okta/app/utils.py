from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, List

import okta.models as models
import tenacity

from iambic.config.models import OktaOrganization
from iambic.core.context import ExecutionContext
from iambic.core.logger import log
from iambic.core.models import ProposedChange, ProposedChangeType
from iambic.okta.group.utils import get_group
from iambic.okta.models import App, Assignment, Group

if TYPE_CHECKING:
    pass


async def list_app_user_assignments(
    okta_organization: OktaOrganization, app: App
) -> dict:
    client = await okta_organization.get_okta_client()
    app_user_list, _, err = await client.list_application_users(app.id)
    if err:
        log.error("Error encountered when listing app users", error=str(err))

    user_assignments = []
    for user in app_user_list:
        if user.scope == "GROUP":
            continue
        user_okta, _, err = await client.get_user(user.id)
        if err:
            log.error("Error encountered when getting user", error=str(err))
            raise Exception("Error encountered when getting user")
        user_assignments.append(user_okta.profile.login)

    return {
        "app_id": app.id,
        "user_assignments": user_assignments,
    }


@tenacity.retry(
    wait=tenacity.wait_exponential(multiplier=1, min=4, max=10),
    stop=tenacity.stop_after_attempt(10),
)
async def get_app(okta_organization: OktaOrganization, app_id: str) -> App:
    client = await okta_organization.get_okta_client()
    app_raw, _, err = await client.get_application(app_id)
    if err:
        log.error("Error encountered when getting app", error=str(err))
        raise Exception(f"Error encountered when getting app: {str(err)}")

    app = App(
        id=app_raw.id,
        idp_name=okta_organization.idp_name,
        name=app_raw.label,
        app_id=app_raw.id,
        attributes=dict(),
        extra=dict(
            okta_app_id=app_raw.id,
            created=app_raw.created,
        ),
    )

    user_assignments = await list_app_user_assignments(okta_organization, app)
    user_assignments = user_assignments.get("user_assignments", [])
    group_assignments = await list_app_group_assignments(okta_organization, app)
    group_assignments = group_assignments.get("group_assignments", [])

    for assignment in user_assignments:
        app.assignments.append(Assignment(user=assignment))
    for assignment in group_assignments:
        app.assignments.append(Assignment(group=assignment))
    return app


async def list_app_group_assignments(
    okta_organization: OktaOrganization, app: App
) -> dict:
    client = await okta_organization.get_okta_client()
    app_group_assignments, _, err = await client.list_application_group_assignments(
        app.id
    )
    if err:
        log.error(
            "Error encountered when listing app group assignments", error=str(err)
        )
        raise Exception(
            f"Error encountered when listing app group assignments: {str(err)}"
        )
    groups_assignments = []
    for assignment in app_group_assignments:
        group, resp, err = await client.get_group(assignment.id)
        if err:
            log.error(
                "Error encountered when getting group",
                group_id=assignment.id,
                error=str(err),
            )
            continue
        groups_assignments.append(group.profile.name)
    return {
        "app_id": app.id,
        "group_assignments": groups_assignments,
    }


async def list_all_apps(okta_organization: OktaOrganization) -> List[App]:
    """
    List all apps in Okta.

    Args:
    - okta_organization: An instance of the OktaOrganization class, which provides access to the Okta API.

    Returns:
    - A list of `App` instances, representing the apps in Okta.
    """

    client = await okta_organization.get_okta_client()
    log.info("Listing apps", provder="Okta", organization=okta_organization.idp_name)
    raw_apps, resp, err = await client.list_applications()
    if err:
        log.error("Error encountered when listing apps", error=str(err))
        raise Exception("Error encountered when listing apps")
    while resp.has_next():
        next_apps, resp, err = await client.list_applications()
        if err:
            log.error("Error encountered when listing apps", error=str(err))
            return []
        raw_apps.append(next_apps)
    tasks = []
    apps = []

    for app_raw in raw_apps:
        app = App(
            id=app_raw.id,
            idp_name=okta_organization.idp_name,
            name=app_raw.label,
            app_id=app_raw.id,
            attributes=dict(),
            status=app_raw.status,
            extra=dict(
                okta_app_id=app_raw.id,
                created=app_raw.created,
            ),
        )
        apps.append(app)
        tasks.append(list_app_user_assignments(okta_organization, app))
        tasks.append(list_app_group_assignments(okta_organization, app))
    app_assignments = await asyncio.gather(*tasks)
    apps_to_return = []
    for app in apps:
        assignments = [a for a in app_assignments if a["app_id"] == app.id]
        for assignment in assignments:
            for user_assignment in assignment.get("user_assignments", []):
                app.assignments.append(Assignment(user=user_assignment))
            for group_assignment in assignment.get("group_assignments", []):
                app.assignments.append(Assignment(group=group_assignment))
        apps_to_return.append(app)
    return apps_to_return


async def update_app_assignments(
    app: App,
    new_assignments: List[Assignment],
    okta_organization: OktaOrganization,
    log_params: dict[str, str],
    context: ExecutionContext,
) -> List[ProposedChange]:
    """
    Update the assignments of a app in Okta.

    Args:
        app (App): The app to update the assignments of.
        new_assignments (List[Assignment]): The new assignments to add to the app.
        okta_organization (OktaOrganization): The Okta organization to update the app in.
        log_params (dict): Logging parameters.
        context (object): The context object containing the execution flag.

    Returns:
        List[ProposedChange]: A list of proposed changes to be applied.
    """
    client = await okta_organization.get_okta_client()
    response = []
    # TODO: Only compare user/group assignments, not expires_at
    current_user_assignments = [
        assignment.user for assignment in app.assignments if assignment.user
    ]
    desired_user_assignments = [
        assignment.user for assignment in new_assignments if assignment.user
    ]
    user_assignments_to_unassign = [
        assignment
        for assignment in current_user_assignments
        if assignment not in desired_user_assignments
    ]
    user_assignments_to_assign = [
        assignment
        for assignment in desired_user_assignments
        if assignment not in current_user_assignments
    ]

    current_group_assignments = [
        assignment.group for assignment in app.assignments if assignment.group
    ]
    desired_group_assignments = [
        assignment.group for assignment in new_assignments if assignment.group
    ]
    group_assignments_to_unassign = [
        assignment
        for assignment in current_group_assignments
        if assignment not in desired_group_assignments
    ]

    group_assignments_to_assign = [
        assignment
        for assignment in desired_group_assignments
        if assignment not in current_group_assignments
    ]

    assignments_to_unassign = bool(
        user_assignments_to_unassign or group_assignments_to_unassign
    )
    assignments_to_assign = bool(
        user_assignments_to_assign or group_assignments_to_assign
    )
    if assignments_to_unassign:
        response.append(
            ProposedChange(
                change_type=ProposedChangeType.DETACH,
                resource_id=app.id,
                resource_type=app.resource_type,
                attribute="assignments",
                change_summary={
                    "AssignmentsToUnassign": {
                        "user_assignments_to_unassign": user_assignments_to_unassign,
                        "group_assignments_to_unassign": group_assignments_to_unassign,
                    }
                },
            )
        )

    if assignments_to_assign:
        response.append(
            ProposedChange(
                change_type=ProposedChangeType.ATTACH,
                resource_id=app.id,
                resource_type=app.resource_type,
                attribute="assignments",
                change_summary={
                    "AssignmentsToAssign": {
                        "user_assignments_to_assign": user_assignments_to_assign,
                        "group_assignments_to_assign": group_assignments_to_assign,
                    }
                },
            )
        )

    if context.execute:
        for assignment in user_assignments_to_assign:
            user_okta, _, err = await client.get_user(assignment)
            if err:
                log.error("Error retrieving user", user=assignment, **log_params)
                continue
            app_user = models.AppUser({"id": user_okta.id})
            _, _, err = await client.assign_user_to_application(app.id, app_user)
            if err:
                log.error(
                    "Error assigning user to app",
                    user=assignment.user,
                    **log_params,
                )
                continue
        for assignment in group_assignments_to_assign:
            group: Group = await get_group("", assignment, okta_organization)
            if not group:
                log.error("Error retrieving group", group=assignment, **log_params)
                continue
            group_okta, _, err = await client.get_group(group.group_id)
            if err:
                log.error("Error retrieving group", group=assignment, **log_params)
                continue
            group_assignment = models.ApplicationGroupAssignment(
                {
                    "id": group_okta.id,
                }
            )
            _, _, err = await client.create_application_group_assignment(
                app.id, group_okta.id, group_assignment
            )
            if err:
                log.error(
                    "Error assigning group to app",
                    group=assignment.oup,
                    **log_params,
                )
                continue
        for assignment in user_assignments_to_unassign:
            user_okta, _, err = await client.get_user(assignment)
            if err:
                log.error("Error retrieving user", user=assignment, **log_params)
                continue
            _, err = await client.delete_application_user(app.id, user_okta.id)
            if err:
                log.error(
                    "Error unassigning user from app",
                    user=assignment.user,
                    **log_params,
                )
                continue
        for assignment in group_assignments_to_unassign:
            group: Group = await get_group("", assignment, okta_organization)
            if not group:
                log.error("Error retrieving group", group=assignment, **log_params)
                continue
            group_okta, _, err = await client.get_group(group.group_id)
            if err:
                log.error("Error retrieving group", group=assignment, **log_params)
                continue
            _, err = await client.delete_application_group_assignment(
                app.id, group_okta.id
            )
            if err:
                log.error(
                    "Error unassigning group from app",
                    group=assignment.group,
                    **log_params,
                )
                continue

    return response


async def update_app_name(
    app: App,
    new_name: str,
    okta_organization: OktaOrganization,
    log_params: dict[str, str],
    context: ExecutionContext,
):
    response: list[ProposedChange] = []
    if app.name == new_name:
        return response
    response.append(
        ProposedChange(
            change_type=ProposedChangeType.UPDATE,
            resource_type=app.resource_type,
            resource_id=app.resource_id,
            attribute="app_name",
            new_value=new_name,
        )
    )

    app_model = models.Application(
        {
            "name": new_name,
            "label": new_name,
        }
    )

    if context.execute:
        client = await okta_organization.get_okta_client()
        _, _, err = await client.update_application(app.id, app_model)
        if err:
            raise ValueError(f"Error updating Okta app: {err}")
    return response


async def maybe_delete_app(
    delete: bool,
    app: App,
    okta_organization: OktaOrganization,
    log_params: dict[str, str],
    context: ExecutionContext,
) -> List[ProposedChange]:
    """
    Delete a app in Okta.

    Args:
        app (App): The app to delete.
        okta_organization (OktaOrganization): The Okta organization to delete the group from.
        log_params (dict): Logging parameters.
        context (object): The context object containing the execution flag.

    Returns:
        List[ProposedChange]: A list of proposed changes to be applied.
    """
    response: list[ProposedChange] = []
    if not delete:
        return response
    response.append(
        ProposedChange(
            change_type=ProposedChangeType.DELETE,
            resource_id=app.id,
            resource_type=app.resource_type,
            attribute="app",
            change_summary={"app": app.name},
        )
    )
    if context.execute:
        client = await okta_organization.get_okta_client()
        _, err = await client.delete_app(app.id)
        if err:
            raise Exception("Error deleting app")
    return response
