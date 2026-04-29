from __future__ import annotations

from rest_framework.pagination import PageNumberPagination

__all__ = ["page_number_pagination"]


def page_number_pagination(
    *,
    page_size: int = 20,
    page_query_param: str = "page",
    page_size_query_param: str | None = "page_size",
    max_page_size: int | None = 100,
) -> type[PageNumberPagination]:
    """Return a small DRF PageNumberPagination class for one CRUDFactory.

    CRUDFactory accepts normal DRF pagination classes through `pagination_class`.
    This helper only removes the boilerplate for the common case:

        factory = CRUDFactory(
            ...,
            pagination_class=page_number_pagination(page_size=10),
        )
    """
    validate_positive_integer("page_size", page_size)
    if max_page_size is not None:
        validate_positive_integer("max_page_size", max_page_size)

    page_size_value = page_size
    page_query_param_value = page_query_param
    page_size_query_param_value = page_size_query_param
    max_page_size_value = max_page_size

    class CRUDFactoryPageNumberPagination(PageNumberPagination):
        page_size = page_size_value
        page_query_param = page_query_param_value
        page_size_query_param = page_size_query_param_value
        max_page_size = max_page_size_value

    CRUDFactoryPageNumberPagination.__name__ = (
        f"CRUDFactoryPageNumberPagination{page_size}"
    )
    CRUDFactoryPageNumberPagination.__qualname__ = CRUDFactoryPageNumberPagination.__name__
    return CRUDFactoryPageNumberPagination


def validate_positive_integer(name: str, value: int) -> None:
    """Raise when a pagination integer setting is not usable."""
    if value < 1:
        msg = f"{name} must be greater than or equal to 1."
        raise ValueError(msg)
