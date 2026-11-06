"""Odds conversions, no-vig probabilities, and expected value."""


def american_to_decimal(american: float) -> float:
    if american == 0:
        raise ValueError("American odds cannot be 0")
    return 1 + american / 100 if american > 0 else 1 + 100 / abs(american)


def implied_prob(american: float) -> float:
    return 1 / american_to_decimal(american)


def prob_to_american(p: float) -> int:
    if not 0 < p < 1:
        raise ValueError("probability must be between 0 and 1")
    if p >= 0.5:
        return round(-100 * p / (1 - p))
    return round(100 * (1 - p) / p)


def no_vig(price_a: float, price_b: float) -> tuple[float, float]:
    """Remove the bookmaker margin from a two-way market (multiplicative method)."""
    pa, pb = implied_prob(price_a), implied_prob(price_b)
    total = pa + pb
    return pa / total, pb / total


def hold(price_a: float, price_b: float) -> float:
    """Bookmaker margin of a two-way market, e.g. 0.0476 for -110/-110."""
    return implied_prob(price_a) + implied_prob(price_b) - 1


def expected_value(p_win: float, american: float) -> float:
    """EV per 1 unit staked (ignores pushes)."""
    return p_win * american_to_decimal(american) - 1
