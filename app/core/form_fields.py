"""Centralized form field definitions."""

from typing import TypedDict


class FormField(TypedDict, total=False):
    """Definition for a form field."""

    name: str
    label: str
    type: str
    placeholder: str
    required: bool
    value: str
    rows: int
    options: list[tuple[str, str]]
    selected_value: str | None


OPPORTUNITY_FIELDS: list[FormField] = [
    {
        "name": "title",
        "label": "Title",
        "type": "text",
        "placeholder": "e.g., Community Garden Helper",
        "required": True,
        "value": "",
    },
    {
        "name": "description",
        "label": "Description",
        "type": "textarea",
        "placeholder": "Describe the volunteering opportunity...",
        "required": True,
        "value": "",
        "rows": 6,
    },
    {
        "name": "location",
        "label": "Location (Optional)",
        "type": "text",
        "placeholder": "e.g., Central Station",
        "required": False,
        "value": "",
    },
    {
        "name": "organization_id",
        "label": "Organization",
        "type": "select",
        "placeholder": "Select an organization",
        "required": True,
        "options": [],
        "selected_value": None,
    },
]


ORGANIZATION_FIELDS: list[FormField] = [
    {
        "name": "name",
        "label": "Organization Name",
        "type": "text",
        "placeholder": "Enter organization display name",
        "required": True,
        "value": "",
    },
    {
        "name": "username",
        "label": "Username (Profile URL)",
        "type": "text",
        "placeholder": "my-organization",
        "required": True,
        "value": "",
    },
    {
        "name": "description",
        "label": "Description",
        "type": "textarea",
        "placeholder": "Describe your organization, its mission, and goals",
        "required": False,
        "value": "",
        "rows": 6,
    },
]


ORGANIZATION_EDIT_FIELDS: list[FormField] = [
    {
        "name": "name",
        "label": "Organization Name",
        "type": "text",
        "placeholder": "Enter organization name",
        "required": True,
        "value": "",
    },
    {
        "name": "description",
        "label": "Description",
        "type": "textarea",
        "placeholder": "Describe your organization, its mission, and goals",
        "required": False,
        "value": "",
        "rows": 6,
    },
]


def with_values(fields: list[FormField], values: dict[str, str]) -> list[FormField]:
    """Create a copy of fields with values filled in from a dict.

    Args:
        fields: List of field definitions
        values: Dict mapping field names to values

    Returns:
        New list of fields with values populated
    """
    return [{**field, "value": values.get(field["name"], field.get("value", ""))} for field in fields]


def with_select_options(
    fields: list[FormField],
    field_name: str,
    options: list[tuple[str, str]],
    selected_value: str | None = None,
) -> list[FormField]:
    """Add select options to a specific field.

    Args:
        fields: List of field definitions
        field_name: Name of the field to add options to
        options: List of (value, label) tuples
        selected_value: Currently selected value

    Returns:
        New list of fields with options added
    """
    result: list[FormField] = []
    for field in fields:
        if field["name"] == field_name:
            new_field: FormField = {**field, "options": options, "selected_value": selected_value}
            result.append(new_field)
        else:
            result.append(FormField(**field))
    return result
