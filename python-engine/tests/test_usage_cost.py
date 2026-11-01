from app.chat.providers import ANTHROPIC_PRICING, OPENROUTER_PRICING, estimate_cost


def test_known_model_cost_is_estimated():
    cost = estimate_cost(ANTHROPIC_PRICING, "claude-sonnet-5-5", 1_000, 500)
    assert cost is not None
    assert abs(cost - (1_000 * 2.0e-6 + 500 * 10.0e-6)) < 1e-12


def test_free_model_costs_zero_and_unknown_model_is_unknown():
    assert estimate_cost(OPENROUTER_PRICING, "google/gemma-4-31b-it:free", 10, 10) == 0.0
    assert estimate_cost(ANTHROPIC_PRICING, "modelo-sem-preco", 10, 10) is None
