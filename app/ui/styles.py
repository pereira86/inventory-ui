import streamlit as st


def apply_mobile_styles() -> None:
    st.markdown(
        """
        <style>
        .block-container {max-width: 760px; padding-top: 1.5rem; padding-bottom: 3rem;}
        div[data-testid="stNumberInput"] input, div[data-testid="stTextInput"] input {font-size: 1.3rem;}
        .product-card {border: 1px solid rgba(128,128,128,.25); border-radius: 14px; padding: 1rem; margin: .5rem 0 1rem 0;}
        .muted {opacity:.7; font-size:.9rem;}
        .counter-emphasis-label {font-weight:700; font-size:1.05rem; margin:.45rem 0 .25rem 0;}

        [class*="st-key-counter_emphasis"] {
            border:1px solid rgba(49,51,63,.28);
            border-radius:12px;
            padding:.55rem .65rem .15rem .65rem;
            background:rgba(128,128,128,.06);
        }

        button[kind="primary"],
        div[data-testid="stButton"] button[kind="primary"] {
            background:#6B7280 !important;
            border-color:#6B7280 !important;
            color:#FFFFFF !important;
        }
        button[kind="primary"]:hover,
        div[data-testid="stButton"] button[kind="primary"]:hover {
            background:#5F6672 !important;
            border-color:#5F6672 !important;
            color:#FFFFFF !important;
        }

        div[data-baseweb="select"] > div:focus-within,
        div[data-testid="stTextInput"] > div > div:focus-within,
        div[data-testid="stNumberInput"] > div > div:focus-within,
        textarea:focus {
            border-color:#6B7280 !important;
            box-shadow:0 0 0 1px #6B7280 !important;
        }

        [class*="st-key-nav_reference_"] button {
            background:rgba(120,120,120,.10) !important;
            border-color:rgba(100,100,100,.28) !important;
            color:inherit !important;
        }
        [class*="st-key-sector_not_started_"] button {
            background:rgba(128,128,128,.06) !important;
            border-color:rgba(128,128,128,.22) !important;
        }
        [class*="st-key-sector_in_progress_"] button {
            background:rgba(230,180,45,.14) !important;
            border-color:rgba(190,145,25,.35) !important;
        }
        [class*="st-key-sector_completed_clean_"] button {
            background:rgba(55,160,85,.14) !important;
            border-color:rgba(55,145,80,.32) !important;
        }
        [class*="st-key-sector_completed_attention_"] button {
            background:rgba(220,125,55,.14) !important;
            border-color:rgba(205,105,40,.34) !important;
        }
        [class*="st-key-sector_disabled_"] {opacity:.58;}

        [class*="st-key-product_grid"] div[data-testid="stHorizontalBlock"] {
            display:flex !important;
            flex-direction:row !important;
            flex-wrap:nowrap !important;
            align-items:stretch !important;
            gap:.45rem !important;
        }
        [class*="st-key-product_grid"] div[data-testid="stColumn"],
        [class*="st-key-product_grid"] div[data-testid="column"] {
            flex:1 1 0 !important;
            width:calc(33.333% - .30rem) !important;
            min-width:0 !important;
        }
        [class*="st-key-product_grid"] button {
            width:100% !important;
            min-height:4.1rem !important;
            padding:.45rem .25rem !important;
        }

        [class*="st-key-recent_row_"] div[data-testid="stHorizontalBlock"] {
            display:flex !important;
            flex-direction:row !important;
            flex-wrap:nowrap !important;
            align-items:center !important;
            gap:.15rem !important;
        }
        [class*="st-key-recent_row_"] div[data-testid="stColumn"]:first-child,
        [class*="st-key-recent_row_"] div[data-testid="column"]:first-child {
            flex:1 1 auto !important;
            min-width:0 !important;
            width:auto !important;
        }
        [class*="st-key-recent_row_"] div[data-testid="stColumn"]:last-child,
        [class*="st-key-recent_row_"] div[data-testid="column"]:last-child {
            flex:0 0 2.2rem !important;
            width:2.2rem !important;
            min-width:2.2rem !important;
        }
        [class*="st-key-recent_row_"] button[kind="tertiary"] {
            padding:.15rem .2rem !important;
            min-height:2rem !important;
        }
        [class*="st-key-recent_row_"] div[data-testid="stColumn"]:first-child button[kind="tertiary"],
        [class*="st-key-recent_row_"] div[data-testid="column"]:first-child button[kind="tertiary"] {
            justify-content:flex-start !important;
            text-align:left !important;
            white-space:normal !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
