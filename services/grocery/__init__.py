"""Grocery / packaged-food label analysis.

Sibling of ``services.matcher`` for items where there is no manufacturer
portal to compare against. Modules in this package perform static checks
against the OCR'd label text — dates, ingredients, nutrition table,
marketing claims, FSSAI license — and emit ``Finding``s that the pipeline
turns into a ``GroceryAnalysis`` and mirrors into the standard notes list.
"""
