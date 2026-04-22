"""Pydantic request/response models — the wire contract for the API.

Putting these in their own package keeps ``app/api`` files focused on routing,
and lets the frontend / SDK clients import the same shapes via codegen later.
"""
