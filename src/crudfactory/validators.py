from __future__ import annotations

import datetime as dt
from dataclasses import Field
from decimal import Decimal
from typing import Any, Callable, Iterable, TypeAlias

from django.core.exceptions import ValidationError
from django.core.validators import (
    MaxLengthValidator,
    MaxValueValidator,
    MinLengthValidator,
    MinValueValidator,
    RegexValidator,
)

REGEX_METADATA_KEY = "crudfactory_regex"
REGEX_MESSAGE_METADATA_KEY = "crudfactory_regex_message"
MIN_VALUE_METADATA_KEY = "crudfactory_min_value"
MAX_VALUE_METADATA_KEY = "crudfactory_max_value"
MIN_LENGTH_METADATA_KEY = "crudfactory_min_length"
MAX_LENGTH_METADATA_KEY = "crudfactory_max_length"
CHOICES_METADATA_KEY = "crudfactory_choices"

ComparableValue = int | float | Decimal | dt.date | dt.datetime

__all__ = ["choices", "length", "range_", "regex"]


class ChoicesValidator:
    """Validator that accepts only values present in a finite choice set."""

    def __init__(self, values: tuple[object, ...]) -> None:
        self.values = values

    def __call__(self, value: object) -> None:
        if value in self.values:
            return
        allowed = ", ".join(str(value) for value in self.values)
        msg = f"Value must be one of: {allowed}."
        raise ValidationError(msg)


Validator: TypeAlias = Callable[[Any], None]


def regex(pattern: str, message: str | None = None) -> dict[str, object]:
    """Return dataclass metadata for regex validation on string input fields.

    Usage:
        name: str = field(metadata=regex(r"^[A-Za-z0-9_-]+$"))
    """
    metadata: dict[str, object] = {REGEX_METADATA_KEY: pattern}
    if message is not None:
        metadata[REGEX_MESSAGE_METADATA_KEY] = message
    return metadata


def range_(
    *,
    min: ComparableValue | None = None,
    max: ComparableValue | None = None,
) -> dict[str, object]:
    """Return metadata for numeric/date/datetime range validation.

    Examples:
        age: int = field(metadata=range_(min=18, max=120))
        price: Decimal = field(metadata=range_(min=Decimal("0")))
        starts_on: date = field(metadata=range_(min=date(2026, 1, 1)))
    """
    metadata: dict[str, object] = {}
    if min is not None:
        metadata[MIN_VALUE_METADATA_KEY] = min
    if max is not None:
        metadata[MAX_VALUE_METADATA_KEY] = max
    if not metadata:
        msg = "range_ requires at least one of min or max."
        raise ValueError(msg)
    return metadata


def length(
    *,
    min: int | None = None,
    max: int | None = None,
) -> dict[str, object]:
    """Return metadata for string/list length validation.

    Examples:
        name: str = field(metadata=length(min=2, max=80))
        tags: list[str] = field(metadata=length(max=10))
    """
    metadata: dict[str, object] = {}
    if min is not None:
        metadata[MIN_LENGTH_METADATA_KEY] = min
    if max is not None:
        metadata[MAX_LENGTH_METADATA_KEY] = max
    if not metadata:
        msg = "length requires at least one of min or max."
        raise ValueError(msg)
    return metadata


def choices(values: Iterable[object]) -> dict[str, object]:
    """Return metadata that restricts a field to a finite set of values.

    Examples:
        status: str = field(metadata=choices(["draft", "published"]))
        priority: int = field(metadata=choices([1, 2, 3]))
    """
    values_tuple = tuple(values)
    if not values_tuple:
        msg = "choices requires at least one allowed value."
        raise ValueError(msg)
    return {CHOICES_METADATA_KEY: values_tuple}


def validators_from_field(dataclass_field: Field[Any]) -> list[Validator]:
    """Return every runtime validator declared in one dataclass field."""
    validators: list[Validator] = []
    append_if_present(validators, regex_validator_from_field(dataclass_field))
    validators.extend(range_validators_from_field(dataclass_field))
    validators.extend(length_validators_from_field(dataclass_field))
    append_if_present(validators, choices_validator_from_field(dataclass_field))
    return validators


def regex_validator_from_field(dataclass_field: Field[Any]) -> RegexValidator | None:
    """Return a Django RegexValidator declared on a dataclass field."""
    pattern = dataclass_field.metadata.get(REGEX_METADATA_KEY)
    if pattern is None:
        return None
    if not isinstance(pattern, str) or not pattern:
        msg = f"Invalid regex metadata on field {dataclass_field.name!r}."
        raise TypeError(msg)

    message = dataclass_field.metadata.get(REGEX_MESSAGE_METADATA_KEY)
    if message is not None and not isinstance(message, str):
        msg = f"Invalid regex message metadata on field {dataclass_field.name!r}."
        raise TypeError(msg)

    if message is None:
        return RegexValidator(regex=pattern)
    return RegexValidator(regex=pattern, message=message)


def range_validators_from_field(dataclass_field: Field[Any]) -> list[Validator]:
    """Return min/max value validators declared on a dataclass field."""
    validators: list[Validator] = []
    if MIN_VALUE_METADATA_KEY in dataclass_field.metadata:
        validators.append(MinValueValidator(dataclass_field.metadata[MIN_VALUE_METADATA_KEY]))
    if MAX_VALUE_METADATA_KEY in dataclass_field.metadata:
        validators.append(MaxValueValidator(dataclass_field.metadata[MAX_VALUE_METADATA_KEY]))
    return validators


def length_validators_from_field(dataclass_field: Field[Any]) -> list[Validator]:
    """Return min/max length validators declared on a dataclass field."""
    validators: list[Validator] = []
    if MIN_LENGTH_METADATA_KEY in dataclass_field.metadata:
        validators.append(MinLengthValidator(dataclass_field.metadata[MIN_LENGTH_METADATA_KEY]))
    if MAX_LENGTH_METADATA_KEY in dataclass_field.metadata:
        validators.append(MaxLengthValidator(dataclass_field.metadata[MAX_LENGTH_METADATA_KEY]))
    return validators


def choices_validator_from_field(dataclass_field: Field[Any]) -> ChoicesValidator | None:
    """Return a choices validator declared on a dataclass field."""
    values = dataclass_field.metadata.get(CHOICES_METADATA_KEY)
    if values is None:
        return None
    if not isinstance(values, tuple) or not values:
        msg = f"Invalid choices metadata on field {dataclass_field.name!r}."
        raise TypeError(msg)
    return ChoicesValidator(values)


def append_if_present(validators: list[Validator], validator: Validator | None) -> None:
    """Append a validator only when metadata produced one."""
    if validator is not None:
        validators.append(validator)


def field_has_regex_validator(dataclass_field: Field[Any]) -> bool:
    """Return True when a dataclass field declares regex metadata."""
    return REGEX_METADATA_KEY in dataclass_field.metadata


def field_has_range_validator(dataclass_field: Field[Any]) -> bool:
    """Return True when a dataclass field declares min/max value metadata."""
    return (
        MIN_VALUE_METADATA_KEY in dataclass_field.metadata
        or MAX_VALUE_METADATA_KEY in dataclass_field.metadata
    )


def field_has_length_validator(dataclass_field: Field[Any]) -> bool:
    """Return True when a dataclass field declares min/max length metadata."""
    return (
        MIN_LENGTH_METADATA_KEY in dataclass_field.metadata
        or MAX_LENGTH_METADATA_KEY in dataclass_field.metadata
    )


def field_has_choices_validator(dataclass_field: Field[Any]) -> bool:
    """Return True when a dataclass field declares choices metadata."""
    return CHOICES_METADATA_KEY in dataclass_field.metadata
