# Copyright 2026 Orhan Yiğit Durmaz
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Phone number matching. Private to this module."""

import re

MATCH_DIGITS = 10
"""Numbers are matched on their last 10 digits (area code + subscriber).

That ignores formatting and the country/trunk prefix, so ``0532 123 45 67``,
``+90 532 123 4567`` and caller ID ``905321234567`` all match.
"""


def match_key(number: str) -> str:
    """The part of a phone number used to recognise it.

    Args:
        number: A phone number in any common format.

    Returns:
        Its last 10 digits (fewer if the number is shorter).
    """
    return re.sub(r"\D", "", number)[-MATCH_DIGITS:]
