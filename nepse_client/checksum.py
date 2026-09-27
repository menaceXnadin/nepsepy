"""Request checksums the public frontend attaches to certain POST bodies.

Observed from the shipped website code (main bundle, utils service +
page components) and verified against live traffic:

  base   = DUMMY[market_id] + market_id + 2 * day_of_month
  signed = base + salts[j] * day - salts[j - 1]

where ``market_id`` is ``/api/nots/nepse-data/market-open`` -> ``id``,
``day`` is the current day of month, and ``salts`` is
``[salt1..salt5]`` from ``/api/authenticate/prove``.

Which body each endpoint takes (all verified in UI traffic):
  raw base ......... POST nots/security/{id}, nots/market/graphdata/{id},
                     nots/market/graphdata/daily/{id}
  variant A (5,3:1)  POST nots/graph/index/{id},
                     POST nots/graph/index?indexCode=&startDate=&endDate=
  variant B (5,1:3)  POST nots/nepse-data/today-price[?page=],
                     POST nots/nepse-data/todays-price/[?businessDate=]
  variant C (4,1:3)  POST nots/nepse-data/floorsheet[?page=]

``(threshold, hi:lo)`` means ``j = hi if base % 10 < threshold else lo``.

This mirrors the browser; it does not decrypt, forge, or bypass anything:
the server validates the value and rejects wrong ones.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

# utilsService.dummyData from the shipped frontend (100 entries).
DUMMY = [
    147, 117, 239, 143, 157, 312, 161, 612, 512, 804,
    411, 527, 170, 511, 421, 667, 764, 621, 301, 106,
    133, 793, 411, 511, 312, 423, 344, 346, 653, 758,
    342, 222, 236, 811, 711, 611, 122, 447, 128, 199,
    183, 135, 489, 703, 800, 745, 152, 863, 134, 211,
    142, 564, 375, 793, 212, 153, 138, 153, 648, 611,
    151, 649, 318, 143, 117, 756, 119, 141, 717, 113,
    112, 146, 162, 660, 693, 261, 362, 354, 251, 641,
    157, 178, 631, 192, 734, 445, 192, 883, 187, 122,
    591, 731, 852, 384, 565, 596, 451, 772, 624, 691,
]

# Nepal time: frontend uses the browser's local day-of-month (GMT+0545
# formatting is used across its date filters).
_NPT = timezone(timedelta(hours=5, minutes=45))


def current_day() -> int:
    """Current day of month in Nepal time, like the site's ``new Date``."""
    return datetime.now(_NPT).day


def base(market_id: int, day: int) -> int:
    """Unsigned base shared by every signed POST body."""
    return DUMMY[market_id] + market_id + 2 * day


def sign(value: int, salts: tuple, day: int,
         threshold: int, hi: int, lo: int) -> int:
    """Salt-mixed checksum: ``value + salts[j]*day - salts[j-1]``."""
    j = hi if value % 10 < threshold else lo
    return value + salts[j] * day - salts[j - 1]


def variant_a(value: int, salts: tuple, day: int) -> int:
    """Index-graph family: threshold 5, order 3:1."""
    return sign(value, salts, day, 5, 3, 1)


def variant_b(value: int, salts: tuple, day: int) -> int:
    """Today-price family: threshold 5, order 1:3."""
    return sign(value, salts, day, 5, 1, 3)


def variant_c(value: int, salts: tuple, day: int) -> int:
    """Floorsheet family: threshold 4, order 1:3."""
    return sign(value, salts, day, 4, 1, 3)
