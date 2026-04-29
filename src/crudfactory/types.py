from __future__ import annotations

from typing import Callable, TypeVar

from django.db import models

M = TypeVar("M", bound=models.Model)
CreateDTO = TypeVar("CreateDTO")
UpdateDTO = TypeVar("UpdateDTO")
PatchDTO = TypeVar("PatchDTO")
ResponseDTO = TypeVar("ResponseDTO")

CreateHandler = Callable[[CreateDTO], M]
UpdateHandler = Callable[[M, UpdateDTO], M]
PartialUpdateHandler = Callable[[M, PatchDTO], M]
ResponseMapper = Callable[[M], ResponseDTO]

__all__: list[str] = []
