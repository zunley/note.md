"""Pydantic 模型。"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class LoginReq(BaseModel):
    password: str


class LoginResp(BaseModel):
    token: str
    expires_at: int


class WriteReq(BaseModel):
    path: str
    content: str
    base_hash: Optional[str] = None


class CreateReq(BaseModel):
    path: str
    type: str = "file"  # "file" | "dir"
    content: str = ""


class MoveReq(BaseModel):
    src: str
    dst: str


class ChatReq(BaseModel):
    message: str
    session_id: Optional[str] = None
    allow_write: bool = False
