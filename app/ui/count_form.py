from __future__ import annotations

from html import escape
import json
import streamlit as st

from app.services.inventory_service import (
    ensure_session_for_count,
    get_previous_quantity,
    save_count,
)
from app.validation.count_validation import (
    parse_quantity,
    validate_count,
)


def _format_quantity(value: float) -> str:
    """Formata números sem casas decimais desnecessárias."""
    if float(value).is_integer():
        return str(int(value))

    return f"{value:g}"


def _adjust_quantity(
    quantity_key: str,
    adjustment: float,
) -> None:
    """Altera a quantidade pelos botões rápidos."""
    current_raw = st.session_state.get(quantity_key)

    try:
        current_quantity = (
            float(current_raw)
            if current_raw is not None
            else 0.0
        )
    except (ValueError, TypeError):
        current_quantity = 0.0

    new_quantity = max(
        0.0,
        current_quantity + adjustment,
    )

    # st.number_input requires a numeric value in session_state.
    # Never write the formatted display string back into this widget state.
    st.session_state[quantity_key] = float(new_quantity)

    st.session_state.pop("pending", None)


def _quantity_example(unit: str) -> str:
    """Retorna um exemplo de quantidade conforme a unidade."""
    normalized_unit = str(unit).strip().upper()

    examples = {
        "KG": "Ex.: 8,5 kg",
        "QUILO": "Ex.: 8,5 kg",
        "QUILOS": "Ex.: 8,5 kg",
        "G": "Ex.: 750 g",
        "GR": "Ex.: 750 g",
        "GRAMA": "Ex.: 750 g",
        "GRAMAS": "Ex.: 750 g",
        "L": "Ex.: 4,5 L",
        "LT": "Ex.: 4,5 L",
        "LITRO": "Ex.: 4,5 L",
        "LITROS": "Ex.: 4,5 L",
        "ML": "Ex.: 500 ml",
        "UN": "Ex.: 12 un.",
        "UND": "Ex.: 12 un.",
        "UNID": "Ex.: 12 un.",
        "UNIDADE": "Ex.: 12 un.",
        "UNIDADES": "Ex.: 12 un.",
        "EA": "Ex.: 12 un.",
        "CX": "Ex.: 3 caixas",
        "CAIXA": "Ex.: 3 caixas",
        "CAIXAS": "Ex.: 3 caixas",
        "PCT": "Ex.: 6 pacotes",
        "PACOTE": "Ex.: 6 pacotes",
        "PACOTES": "Ex.: 6 pacotes",
        "BANDEJA": "Ex.: 4 bandejas",
        "BANDEJAS": "Ex.: 4 bandejas",
        "GARRAFA": "Ex.: 6 garrafas",
        "GARRAFAS": "Ex.: 6 garrafas",
        "LATA": "Ex.: 12 latas",
        "LATAS": "Ex.: 12 latas",
    }

    return examples.get(
        normalized_unit,
        f"Ex.: 12 {str(unit).strip()}",
    )


def _display_unit(unit: str) -> str:
    """Retorna a unidade em formato curto e amigável."""
    normalized_unit = str(unit).strip().upper()

    labels = {
        "KG": "kg",
        "QUILO": "kg",
        "QUILOS": "kg",
        "G": "g",
        "GR": "g",
        "GRAMA": "g",
        "GRAMAS": "g",
        "L": "L",
        "LT": "L",
        "LITRO": "L",
        "LITROS": "L",
        "ML": "ml",
        "UN": "un.",
        "UND": "un.",
        "UNID": "un.",
        "UNIDADE": "un.",
        "UNIDADES": "un.",
        "EA": "un.",
        "CX": "caixas",
        "CAIXA": "caixas",
        "CAIXAS": "caixas",
        "PCT": "pacotes",
        "PACOTE": "pacotes",
        "PACOTES": "pacotes",
        "BANDEJA": "bandejas",
        "BANDEJAS": "bandejas",
        "GARRAFA": "garrafas",
        "GARRAFAS": "garrafas",
        "LATA": "latas",
        "LATAS": "latas",
    }

    return labels.get(normalized_unit, str(unit).strip().lower())


def _clear_product_state(
    quantity_key: str,
) -> None:
    """Limpa os estados associados ao produto aberto."""
    st.session_state.pop(
        "selected_product_id",
        None,
    )
    st.session_state.pop(
        "pending",
        None,
    )
    st.session_state.pop(
        quantity_key,
        None,
    )



def _next_uncounted_product_id(
    items: list[dict],
    current_product_id: int,
) -> int | None:
    """Return the next uncounted product, wrapping once if needed."""
    if not items:
        return None

    current_index = next(
        (
            index
            for index, candidate in enumerate(items)
            if candidate.get("product_id") == current_product_id
        ),
        -1,
    )

    ordered = (
        items[current_index + 1:] + items[:current_index]
        if current_index >= 0
        else items
    )

    for candidate in ordered:
        if (
            candidate.get("product_id") != current_product_id
            and candidate.get("status") == "not_counted"
        ):
            return int(candidate["product_id"])

    return None


def _advance_after_save(
    items: list[dict],
    current_product_id: int,
    quantity_key: str,
) -> None:
    """Advance to the next uncounted product or return to the sector map."""
    next_product_id = _next_uncounted_product_id(
        items,
        current_product_id,
    )

    st.session_state.pop("pending", None)
    st.session_state.pop(quantity_key, None)

    # Clear transient control state before the next product is rendered.
    for transient_key in (
        "enter_save_current",
        "minus_10_current",
        "minus_1_current",
        "plus_1_current",
        "plus_10_current",
        "zero_current_product",
        "save_current_product",
    ):
        st.session_state.pop(transient_key, None)

    # Only successful/confirmed count actions request a scroll to the top.
    st.session_state["_scroll_to_top_once"] = True

    if next_product_id is None:
        st.session_state.pop("selected_product_id", None)
    else:
        st.session_state.selected_product_id = next_product_id


def _ensure_effective_session(session: dict) -> int:
    """Cria a sessão somente quando ocorre a primeira ação efetiva de contagem."""
    session_id = ensure_session_for_count(session)
    if not session.get("id"):
        st.session_state.session_id = session_id
    return session_id


def render_count_form(
    session: dict,
    items: list[dict],
) -> None:
    product_id = st.session_state.get(
        "selected_product_id"
    )

    item = next(
        (
            current_item
            for current_item in items
            if current_item["product_id"] == product_id
        ),
        None,
    )

    if not item:
        st.session_state.pop(
            "selected_product_id",
            None,
        )
        st.rerun()
        return

    st.markdown(
        """
        <style>
        .count-form-top-spacer {
            height: 2rem;
        }

        /* Linha com nome e quantidade. */
        .st-key-product_quantity_row {
            margin-bottom: 0.45rem !important;
        }

        .st-key-product_quantity_row
        div[data-testid="stHorizontalBlock"] {
            align-items: center !important;
            gap: 0.75rem !important;
        }

        .st-key-product_quantity_row
        div[data-testid="column"] {
            min-width: 0 !important;
        }

        /* Informações do produto. */
        .count-product-header {
            min-height: 9.5rem;

            display: flex;
            flex-direction: column;
            justify-content: center;

            padding: 0.4rem 0;
        }

        .count-product-position {
            color: #777777;
            font-size: 0.76rem;
            font-weight: 500;
            line-height: 1;

            margin-bottom: 0.5rem;
        }

        .count-product-name {
            color: #262626;
            font-size: 1.3rem;
            font-weight: 650;
            line-height: 1.18;

            margin: 0;
            overflow-wrap: anywhere;
        }

        .count-product-unit {
            color: #777777;
            font-size: 0.82rem;
            line-height: 1.2;

            margin-top: 0.65rem;
        }

        /*
        Seleciona o componente inteiro usando o aria-label
        real encontrado no HTML do Streamlit.
        */
        div[data-testid="stNumberInput"]:has(
            input[aria-label^="Quantidade atual"]
        ) {
            width: 100% !important;
            margin: 0 !important;
        }

        /*
        Esconde o espaço do label dentro apenas do campo
        de quantidade.
        */
        div[data-testid="stNumberInput"]:has(
            input[aria-label^="Quantidade atual"]
        )
        div[data-testid="stWidgetLabel"] {
            display: none !important;
        }

        /* Wrapper real encontrado no HTML desta versão do Streamlit. */
        div[data-testid="stNumberInput"]:has(
            input[aria-label^="Quantidade atual"]
        )
        div[data-testid="stNumberInput"] > div {
            width: 100% !important;

            height: 9rem !important;
            min-height: 9rem !important;
            max-height: 9rem !important;

            display: flex !important;
            align-items: center !important;
            justify-content: center !important;

            padding: 0 !important;

            background: rgba(
                220,
                220,
                220,
                0.50
            ) !important;

            border: 1px solid rgba(
                90,
                90,
                90,
                0.22
            ) !important;

            border-radius: 14px !important;
            box-shadow: none !important;
        }

        /*
        O próprio input identificado pelo aria-label.
        Esse é o elemento mostrado no HTML enviado.
        */
        input[aria-label^="Quantidade atual"] {
            width: 100% !important;

            height: 9rem !important;
            min-height: 9rem !important;
            max-height: 9rem !important;

            padding: 0 0.4rem !important;
            margin: 0 !important;

            background: transparent !important;
            border: 0 !important;
            border-radius: 14px !important;
            outline: 0 !important;

            color: #292929 !important;

            font-size: 2.8rem !important;
            font-weight: 700 !important;
            line-height: 1 !important;

            text-align: center !important;
            vertical-align: middle !important;

            font-variant-numeric: tabular-nums !important;
        }

        input[aria-label^="Quantidade atual"]::placeholder {
            color: rgba(
                55,
                55,
                55,
                0.43
            ) !important;

            opacity: 1 !important;

            font-size: 1.20rem !important;
            font-weight: 500 !important;
            text-align: center !important;
        }

        div[data-testid="stNumberInput"]:has(
            input[aria-label^="Quantidade atual"]:focus
        )
        div[data-testid="stNumberInput"] > div {
            background: rgba(
                220,
                220,
                220,
                0.68
            ) !important;

            border-color: rgba(
                70,
                70,
                70,
                0.48
            ) !important;

            box-shadow: none !important;
        }


        /* Quantity is a real numeric input so mobile opens the numeric keyboard.
           Hide the widget's native +/- stepper because the form already has
           dedicated -10/-1/+1/+10 controls below. */
        .st-key-quantity_input_box button[aria-label*="Increment"],
        .st-key-quantity_input_box button[aria-label*="Decrement"],
        .st-key-quantity_input_box button[aria-label*="increase"],
        .st-key-quantity_input_box button[aria-label*="decrease"] {
            display: none !important;
        }

        .st-key-quantity_input_box input {
            font-variant-numeric: tabular-nums !important;
        }

        /* Keep the numeric field visually clean on mobile. */
        .st-key-quantity_input_box [data-testid="InputInstructions"],
        .st-key-quantity_input_box [data-testid="stInputInstructions"],
        .st-key-quantity_input_box [class*="InputInstructions"] {
            display:none !important;
            height:0 !important;
            min-height:0 !important;
            margin:0 !important;
            padding:0 !important;
            overflow:hidden !important;
        }

        input[aria-label^="Quantidade atual"]:focus::placeholder {
            color:transparent !important;
            opacity:0 !important;
        }

        /* Technical submit used only so Enter/Go on mobile saves.
           The regular visible Salvar button remains in count_actions. */
        [class*="st-key-enter_save_current"] {
            /* Keep the submit control alive for mobile Enter/Go submission,
               but make it visually invisible and non-interactive. */
            position:absolute !important;
            width:1px !important;
            height:1px !important;
            min-width:1px !important;
            min-height:1px !important;
            margin:0 !important;
            padding:0 !important;
            opacity:0 !important;
            overflow:hidden !important;
            pointer-events:none !important;
            clip-path:inset(50%) !important;
        }

        /* Botões de ajuste abaixo do campo. */
        .st-key-quantity_controls {
            margin-top: 0.3rem !important;
        }

        .st-key-quantity_controls
        div[data-testid="stHorizontalBlock"] {
            gap: 4px !important;
        }

        .st-key-quantity_controls
        div[data-testid="column"] {
            min-width: 0 !important;
            padding: 0 !important;
        }

        .st-key-quantity_controls
        div.stButton {
            margin: 0 !important;
        }

        .st-key-quantity_controls
        div.stButton > button {
            width: 100% !important;

            min-height: 2.35rem !important;
            height: 2.35rem !important;

            padding: 0 2px !important;

            font-size: 0.8rem !important;
            font-weight: 650 !important;
            white-space: nowrap !important;
        }

        /* Observação opcional. */
        .st-key-count_notes {
            margin-top: 0.3rem !important;
        }

        .st-key-count_notes details {
            padding: 0 !important;
            border: 0 !important;
        }

        .st-key-count_notes details summary {
            color: #666666 !important;
            font-size: 0.82rem !important;
        }

        /* Botões salvar e sem estoque. */
        .st-key-count_actions {
            margin-top: 0.5rem !important;
        }

        .st-key-count_actions
        div[data-testid="stHorizontalBlock"] {
            gap: 6px !important;
        }
        /* A unidade é adicionada em uma regra dinâmica mais abaixo. */

        /* Área de validação sempre reservada: evita que os controles pulem
           quando um alerta aparece. */
        .st-key-count_validation {
            margin-top: 0.35rem !important;
            min-height: 5.4rem !important;
            height: 5.4rem !important;
            overflow: hidden !important;
        }

        .st-key-count_validation .compact-count-alert {
            box-sizing: border-box !important;
            width: 100% !important;
            min-height: 2.15rem !important;
            max-height: 2.15rem !important;
            overflow: hidden !important;
            padding: 0.32rem 0.55rem !important;
            border-radius: 8px !important;
            background: rgba(230,180,45,.14) !important;
            border: 1px solid rgba(190,145,25,.35) !important;
            color: inherit !important;
            font-size: 0.78rem !important;
            line-height: 1.15 !important;
        }

        .st-key-count_validation .compact-count-previous {
            margin: 0.15rem 0 0.2rem 0 !important;
            color: #6b6b6b !important;
            font-size: 0.70rem !important;
            line-height: 1 !important;
        }

        .st-key-count_validation button {
            min-height: 1.85rem !important;
            height: 1.85rem !important;
            padding: 0.1rem 0.35rem !important;
            font-size: 0.78rem !important;
        }

        /* Botão voltar no final. */
        .st-key-count_back {
            margin-top: 1rem !important;
            padding-top: 0.65rem !important;

            border-top: 1px solid #eeeeee;
        }

        .st-key-count_back
        div.stButton > button {
            min-height: 2.1rem !important;
            height: 2.1rem !important;

            font-size: 0.8rem !important;
        }

        @media (max-width: 640px) {
            .count-product-header {
                min-height: 8.3rem;
            }

            .count-product-name {
                font-size: 1.08rem;
            }

            div[data-testid="stNumberInput"]:has(
                input[aria-label^="Quantidade atual"]
            )
            div[data-testid="stNumberInput"] > div,
            input[aria-label^="Quantidade atual"] {
                height: 8.3rem !important;
                min-height: 8.3rem !important;
                max-height: 8.3rem !important;
            }

            input[aria-label^="Quantidade atual"] {
                font-size: 3rem !important;
            }

            input[aria-label^="Quantidade atual"]::placeholder {
                font-size: 0.72rem !important;
            }

        }
        </style>

        <div class="count-form-top-spacer"></div>
        """,
        unsafe_allow_html=True,
    )

    position = (
        item.get("count_order")
        or item["product_id"]
    )

    try:
        formatted_position = f"{int(position):02d}"
    except (TypeError, ValueError):
        formatted_position = str(position)

    product_name = escape(
        str(item["name"])
    )

    product_unit = escape(
        str(item["unit"])
    )

    quantity_placeholder = _quantity_example(
        str(item["unit"])
    )

    previous = get_previous_quantity(
        item["product_id"],
        session["id"],
    )

    quantity_key = (
        f'quantity_{session["id"]}_'
        f'{item["product_id"]}_'
        f'{item.get("status", "not_counted")}'
    )

    if quantity_key not in st.session_state:
        st.session_state[quantity_key] = (
            None
            if item["quantity"] is None
            else float(item["quantity"])
        )

    with st.container(
        key="product_quantity_row"
    ):
        product_column, quantity_column = st.columns(
            [1.1, 1],
            gap="small",
            vertical_alignment="center",
        )

        with product_column:
            st.markdown(
                (
                    '<div class="count-product-header">'
                    '<div class="count-product-position">'
                    f'Local {formatted_position}'
                    '</div>'
                    '<div class="count-product-name">'
                    f'{product_name}'
                    '</div>'
                    '<div class="count-product-unit">'
                    f'Contar em <b>{product_unit}</b>'
                    '</div>'
                    '</div>'
                ),
                unsafe_allow_html=True,
            )

        with quantity_column:
            with st.container(key="quantity_input_box"):
                unit_label = _display_unit(item["unit"])
                has_quantity = (
                    st.session_state.get(quantity_key) is not None
                )
                quantity_state_class = (
                    "has-quantity" if has_quantity else "is-empty"
                )

                st.markdown(
                    (
                        '<span class="quantity-state-marker '
                        f'{quantity_state_class}"></span>'
                    ),
                    unsafe_allow_html=True,
                )

                st.markdown(
                    f"""
                    <style>
                    /*
                    Mantém o mesmo seletor que funcionou no diagnóstico.
                    Só muda o visual e a visibilidade.
                    */
                    .st-key-quantity_input_box
                    .react-aria-TextField {{
                        position: relative !important;
                        width: 100% !important;
                        overflow: visible !important;
                    }}

                    .st-key-quantity_input_box:has(
                        .quantity-state-marker.has-quantity
                    ) .react-aria-TextField::after {{
                        content: "{unit_label}" !important;
                        position: absolute !important;
                        right: 0.9rem !important;
                        top: 50% !important;
                        transform: translateY(-50%) !important;
                        z-index: 999999 !important;
                        display: block !important;
                        color: #555555 !important;
                        background: transparent !important;
                        border: 0 !important;
                        padding: 0 !important;
                        opacity: 1 !important;
                        font-size: 1rem !important;
                        font-weight: 500 !important;
                        line-height: 1 !important;
                        white-space: nowrap !important;
                        pointer-events: none !important;
                    }}

                    .st-key-quantity_input_box:has(
                        .quantity-state-marker.is-empty
                    ) .react-aria-TextField::after {{
                        content: "" !important;
                        display: none !important;
                    }}

                    .st-key-quantity_input_box
                    input[aria-label^="Quantidade atual"] {{
                        padding-left: 0.5rem !important;
                        padding-right: 4.5rem !important;
                    }}
                    </style>
                    """,
                    unsafe_allow_html=True,
                )

                # A tiny form lets the mobile keyboard's Enter/Go/OK submit
                # the quantity using Streamlit's native form behavior.
                with st.form(
                    key="quantity_enter_form_current",
                    clear_on_submit=False,
                    enter_to_submit=True,
                ):
                    quantity_raw = st.number_input(
                        f'Quantidade atual ({item["unit"]})',
                        min_value=0.0,
                        value=None,
                        step=0.1,
                        format="%g",
                        key=quantity_key,
                        placeholder=quantity_placeholder,
                        label_visibility="collapsed",
                    )

                    enter_save_clicked = st.form_submit_button(
                        "Salvar",
                        key="enter_save_current",
                    )

            controls = st.container(
                key="quantity_controls",
                horizontal=True,
                horizontal_alignment="center",
                vertical_alignment="center",
                gap="xxsmall",
            )

            controls.button(
                "−10",
                width=64,
                key="minus_10_current",
                on_click=_adjust_quantity,
                args=(quantity_key, -10.0),
            )

            controls.button(
                "−1",
                width=64,
                key="minus_1_current",
                on_click=_adjust_quantity,
                args=(quantity_key, -1.0),
            )

            controls.button(
                "+1",
                width=64,
                key="plus_1_current",
                on_click=_adjust_quantity,
                args=(quantity_key, 1.0),
            )

            controls.button(
                "+10",
                width=64,
                key="plus_10_current",
                on_click=_adjust_quantity,
                args=(quantity_key, 10.0),
            )

    with st.container(
        key="count_notes"
    ):
        with st.expander(
            "＋ Adicionar observação",
            expanded=bool(item["notes"]),
        ):
            notes = st.text_input(
                "Observação",
                value=item["notes"] or "",
                key=(
                    f'notes_{session["id"]}_'
                    f'{item["product_id"]}'
                ),
                placeholder=(
                    "Ex.: caixa aberta ou "
                    "embalagem danificada"
                ),
                label_visibility="collapsed",
            )

    # Render the two main actions through an explicit placeholder. Before
    # advancing to another product we clear this placeholder first, preventing
    # Streamlit Cloud from leaving the old buttons visible as translucent
    # "stale" elements while the next product rerenders.
    actions_slot = st.empty()
    with actions_slot.container():
        with st.container(key="count_actions"):
            zero_column, save_column = st.columns(2)

            zero_clicked = zero_column.button(
                "Sem estoque",
                use_container_width=True,
                key="zero_current_product",
            )

            save_clicked = save_column.button(
                "Salvar",
                type="primary",
                use_container_width=True,
                key="save_current_product",
            )

    # Reserve the validation block through a placeholder as well so it can be
    # cleared atomically with the actions during a product transition.
    validation_slot = st.empty()

    # Enter/Go/OK on the numeric keyboard is equivalent to tapping Salvar.
    save_clicked = bool(save_clicked or enter_save_clicked)

    validation_error = None

    if zero_clicked:
        effective_session_id = _ensure_effective_session(session)
        save_count(
            effective_session_id,
            item["product_id"],
            session["employee_id"],
            0.0,
            "confirmed_zero",
            notes,
        )

        _advance_after_save(
            items,
            item["product_id"],
            quantity_key,
        )

        actions_slot.empty()
        validation_slot.empty()
        st.rerun()

    if save_clicked:
        try:
            if quantity_raw is None:
                raise ValueError(
                    "Informe uma quantidade ou use o botão Sem estoque."
                )
            quantity = float(quantity_raw)

            # Digitar 0 manualmente é equivalente ao botão "Sem estoque".
            if quantity == 0:
                effective_session_id = _ensure_effective_session(session)
                save_count(
                    effective_session_id,
                    item["product_id"],
                    session["employee_id"],
                    0.0,
                    "confirmed_zero",
                    notes,
                )

                _advance_after_save(
                    items,
                    item["product_id"],
                    quantity_key,
                )
                actions_slot.empty()
                validation_slot.empty()
                st.rerun()

            validation = validate_count(
                quantity,
                previous,
                item.get("expected_min"),
                item.get("expected_max"),
            )

            if validation.flagged:
                st.session_state.pending = {
                    "product_id": item["product_id"],
                    "quantity": quantity,
                    "notes": notes,
                    "message": validation.message,
                }

            else:
                effective_session_id = _ensure_effective_session(session)
                save_count(
                    effective_session_id,
                    item["product_id"],
                    session["employee_id"],
                    quantity,
                    "counted",
                    notes,
                )

                _advance_after_save(
                    items,
                    item["product_id"],
                    quantity_key,
                )

                actions_slot.empty()
                validation_slot.empty()
                st.rerun()

        except ValueError as exc:
            validation_error = str(exc)

    pending = st.session_state.get(
        "pending"
    )

    # Render this container on every product so its footprint never changes.
    # The message itself is intentionally compact; when there is no warning,
    # the reserved area stays empty and the controls below remain fixed.
    with validation_slot.container():
        with st.container(key="count_validation"):
            if (
                pending
                and pending.get("product_id") == item["product_id"]
            ):
                safe_message = escape(str(pending.get("message") or "Verifique este valor."))
                st.markdown(
                    f'<div class="compact-count-alert">{safe_message}</div>',
                    unsafe_allow_html=True,
                )

                if previous is not None:
                    st.markdown(
                        (
                            '<div class="compact-count-previous">'
                            f'Anterior: {previous:g} {escape(str(item["unit"]))}'
                            '</div>'
                        ),
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        '<div class="compact-count-previous">&nbsp;</div>',
                        unsafe_allow_html=True,
                    )

                decision_row = st.container(
                    horizontal=True,
                    horizontal_alignment="center",
                    vertical_alignment="center",
                    gap="xxsmall",
                )

                if decision_row.button(
                    "Corrigir",
                    width=112,
                    key=(
                        f"correct_{session['id']}_"
                        f"{item['product_id']}"
                    ),
                ):
                    st.session_state.pop("pending", None)
                    st.rerun()

                if decision_row.button(
                    "Confirmar",
                    type="primary",
                    width=112,
                    key=(
                        f"confirm_{session['id']}_"
                        f"{item['product_id']}"
                    ),
                ):
                    effective_session_id = _ensure_effective_session(session)
                    save_count(
                        effective_session_id,
                        item["product_id"],
                        session["employee_id"],
                        pending["quantity"],
                        "flagged",
                        pending["notes"],
                        pending["message"],
                    )

                    _advance_after_save(
                        items,
                        item["product_id"],
                        quantity_key,
                    )

                    st.rerun()

            elif validation_error:
                safe_error = escape(validation_error)
                st.markdown(
                    f'<div class="compact-count-alert">{safe_error}</div>',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    '<div class="compact-count-previous">&nbsp;</div>',
                    unsafe_allow_html=True,
                )

    with st.container(
        key="count_back"
    ):
        back_col, home_col = st.columns(2)
        if back_col.button(
            "← Voltar",
            use_container_width=True,
            key=(
                f"back_to_count_map_"
                f"{session['id']}_"
                f"{item['product_id']}"
            ),
        ):
            _clear_product_state(quantity_key)
            st.rerun()
        if home_col.button(
            "Início",
            use_container_width=True,
            key=(
                f"home_from_product_"
                f"{session['id']}_"
                f"{item['product_id']}"
            ),
        ):
            _clear_product_state(quantity_key)
            st.session_state.page = "home"
            st.rerun()
