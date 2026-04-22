"""HTTP-facing service glue.

Modules here adapt the framework-agnostic packages under ``/services`` to the
shape FastAPI routes need (e.g. converting an UploadFile to bytes, mapping
domain errors to HTTPExceptions). Keep them thin — if logic grows, push it
down into ``/services/<package>`` so a CLI or worker can reuse it.
"""
