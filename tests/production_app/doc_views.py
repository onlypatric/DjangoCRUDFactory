from __future__ import annotations

from django.http import Http404, HttpRequest, HttpResponse

from .factory_docs import FACTORY_DOCS_BY_SLUG, factory_docs_index_markdown


MARKDOWN_CONTENT_TYPE = "text/markdown; charset=utf-8"


def factory_docs_index_view(request: HttpRequest) -> HttpResponse:
    del request
    return HttpResponse(
        factory_docs_index_markdown(),
        content_type=MARKDOWN_CONTENT_TYPE,
    )


def factory_docs_detail_view(request: HttpRequest, slug: str) -> HttpResponse:
    del request
    entry = FACTORY_DOCS_BY_SLUG.get(slug)
    if entry is None:
        raise Http404(f"Unknown factory doc slug: {slug}")
    return HttpResponse(
        entry.factory.render_markdown_docs(
            title=entry.title,
            base_path="/api",
        ),
        content_type=MARKDOWN_CONTENT_TYPE,
    )
