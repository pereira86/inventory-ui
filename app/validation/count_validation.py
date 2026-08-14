from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ValidationResult:
    is_valid: bool
    flagged: bool = False
    message: str = ""


def parse_quantity(raw: str) -> float:
    cleaned = raw.strip().replace(",", ".")
    if cleaned == "":
        raise ValueError("Informe uma quantidade ou use o botão de estoque zero.")
    value = float(cleaned)
    if value < 0:
        raise ValueError("A quantidade não pode ser negativa.")
    return value


def validate_count(
    quantity: float,
    previous: float | None,
    expected_min: float | None,
    expected_max: float | None,
) -> ValidationResult:
    messages: list[str] = []

    if expected_min is not None and quantity < expected_min:
        messages.append(
            f"Valor abaixo do mínimo esperado ({expected_min:g})."
        )

    if expected_max is not None and quantity > expected_max:
        messages.append(
            f"Valor acima do máximo esperado ({expected_max:g})."
        )

    if previous is not None and previous > 0:
        change = abs(quantity - previous) / previous

        if change >= 0.50:
            messages.append(
                f"Variação de {change:.0%} em relação à contagem anterior."
            )

    if messages:
        return ValidationResult(
            is_valid=True,
            flagged=True,
            message=" ".join(messages),
        )

    return ValidationResult(
        is_valid=True,
        flagged=False,
    )