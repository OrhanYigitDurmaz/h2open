# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Business modules.

Each module is a package. Files whose names start with ``_`` are private to
that module; other modules may only import its public files: ``api.py``
(functions and read models) and ``events.py`` (events it publishes).
``module.py`` holds the ``MODULE`` that ``app.main`` registers.
import-linter enforces this.
"""
