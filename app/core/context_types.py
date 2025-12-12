"""Typed context helpers for template rendering.

Provides TypedDict definitions and helper functions for building
consistent template context dictionaries across routers.
"""

from collections.abc import Sequence
from typing import TypedDict

from app.core.form_fields import FormField


class ListViewContext(TypedDict, total=False):
    """Context for list view templates (pages/shared.html view='list')."""

    items: Sequence[object]
    meta: dict[str, object]
    page_title: str
    create_url: str
    create_text: str
    create_color: str
    show_create: bool
    empty_message: str
    grid_cols: str
    resource_type: str


class FormViewContext(TypedDict, total=False):
    """Context for form view templates (pages/shared.html view='form')."""

    view: str
    resource_type: str
    resource: object
    form_action: str
    back_url: str
    form_title: str
    page_title: str
    submit_text: str
    submit_color: str
    show_warning: bool
    warning_title: str
    warning_message: str
    warning_action_url: str
    warning_action_text: str
    form_fields: list[FormField]


def list_view_context(
    items: Sequence[object],
    page_title: str,
    *,
    meta: dict[str, object] | None = None,
    create_url: str = "",
    create_text: str = "Create",
    create_color: str = "brand",
    show_create: bool = True,
    empty_message: str = "No items found",
    grid_cols: str = "grid-cols-1 md:grid-cols-2 lg:grid-cols-3",
    resource_type: str = "",
) -> ListViewContext:
    """Build a consistent list view context dictionary.

    Args:
        items: List of items to display
        page_title: Title for the page
        meta: Pagination metadata (page, total, per_page, total_pages)
        create_url: URL for the create action button
        create_text: Text for the create action button
        create_color: Tailwind color for the create button
        show_create: Whether to show the create button
        empty_message: Message to show when items list is empty
        grid_cols: Tailwind grid column classes
        resource_type: Type of resource (for template logic)

    Returns:
        ListViewContext dictionary ready for template rendering
    """
    return {
        "items": items,
        "meta": meta or {},
        "page_title": page_title,
        "create_url": create_url,
        "create_text": create_text,
        "create_color": create_color,
        "show_create": show_create,
        "empty_message": empty_message,
        "grid_cols": grid_cols,
        "resource_type": resource_type,
    }


def form_view_context(
    resource_type: str,
    form_action: str,
    back_url: str,
    form_title: str,
    page_title: str,
    form_fields: list[FormField],
    *,
    resource: object | None = None,
    submit_text: str = "Submit",
    submit_color: str = "brand",
    show_warning: bool = False,
    warning_title: str = "",
    warning_message: str = "",
    warning_action_url: str = "",
    warning_action_text: str = "",
) -> FormViewContext:
    """Build a consistent form view context dictionary.

    Args:
        resource_type: Type of resource being created/edited
        form_action: URL to submit the form to
        back_url: URL for the back button
        form_title: Title displayed on the form
        page_title: Page title (for breadcrumbs/back text)
        form_fields: List of field definitions for the form
        resource: Existing resource (for edit forms)
        submit_text: Text for the submit button
        submit_color: Tailwind color for the submit button
        show_warning: Whether to show a warning instead of the form
        warning_title: Title for the warning box
        warning_message: Message for the warning box
        warning_action_url: URL for the warning action button
        warning_action_text: Text for the warning action button

    Returns:
        FormViewContext dictionary ready for template rendering
    """
    return {
        "view": "form",
        "resource_type": resource_type,
        "resource": resource,
        "form_action": form_action,
        "back_url": back_url,
        "form_title": form_title,
        "page_title": page_title,
        "submit_text": submit_text,
        "submit_color": submit_color,
        "show_warning": show_warning,
        "warning_title": warning_title,
        "warning_message": warning_message,
        "warning_action_url": warning_action_url,
        "warning_action_text": warning_action_text,
        "form_fields": form_fields,
    }
