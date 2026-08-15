from __future__ import annotations
from collections.abc import Callable
from html import escape
import streamlit as st
from app.services.inventory_service import (
    get_location,
    list_locations_for_employee,
    list_locations_for_session,
    list_count_items_for_location,
    get_session_items,
)

STATUS_ICONS={'not_counted':'⬜','counted':'🟩','flagged':'🟧','confirmed_zero':'🟥'}


def _location_sort_key(row:dict):
    """Natural hierarchical order: 2.3.4 comes before 2.4 and 10.1."""
    code=str(row.get("code") or "")
    key=[]
    for part in code.split("."):
        stripped=part.strip()
        if stripped.isdigit():
            key.append((0,int(stripped)))
        else:
            key.append((1,stripped.casefold()))
    return tuple(key)


def _adjacent_sector_ids(
    session:dict,
    location_id:int|None,
)->tuple[int|None,int|None]:
    """Previous/next countable sector in full hierarchy order."""
    if location_id is None:
        return None,None

    historical_id=st.session_state.get('historical_session_id')
    if historical_id:
        rows=list_locations_for_session(historical_id)
        has_items=lambda candidate_id: bool(
            get_session_items(historical_id,candidate_id)
        )
    else:
        rows=list_locations_for_employee(session['employee_id'])
        has_items=lambda candidate_id: bool(
            list_count_items_for_location(session['employee_id'],candidate_id)
        )

    rows=sorted(rows,key=_location_sort_key)
    ids=[int(row['id']) for row in rows]

    try:
        current_index=ids.index(int(location_id))
    except (ValueError,TypeError):
        return None,None

    previous_id=None
    index=current_index-1
    while index>=0:
        candidate_id=ids[index]
        if has_items(candidate_id):
            previous_id=candidate_id
            break
        index-=1

    next_id=None
    index=current_index+1
    while index<len(ids):
        candidate_id=ids[index]
        if has_items(candidate_id):
            next_id=candidate_id
            break
        index+=1

    return previous_id,next_id

def _go_to_sector(location_id:int,nav_slot=None)->None:
    if st.session_state.get('_sector_nav_busy'):
        return
    st.session_state._sector_nav_busy=True

    if nav_slot is not None:
        try:
            nav_slot.empty()
        except Exception:
            pass

    st.session_state.session_id=None
    st.session_state.selected_product_id=None
    st.session_state.count_nav_location_id=location_id
    st.session_state.historical_direct_view=False
    st.session_state.pop('preview_product_id',None)
    st.session_state.pop('pending',None)
    st.rerun()


def render_count_dashboard(session:dict,items:list[dict],go:Callable[[str],None],**kwargs)->None:
    st.session_state.pop('_sector_nav_busy',None)
    counted=sum(i.get('status')!='not_counted' for i in items)
    total=len(items)

    st.markdown(
        """
        <style>
        .count-dashboard-summary {
            display:flex;
            align-items:center;
            justify-content:center;
            flex-wrap:nowrap;
            gap:.72rem;
            margin:.28rem 0 .42rem 0;
            color:#666;
            font-size:.68rem;
            line-height:1;
            white-space:nowrap;
        }
        .count-dashboard-summary b {
            color:#2f3136;
            font-size:.82rem;
            font-weight:750;
        }
        [class*="st-key-sector_sibling_nav"] {
            margin-bottom:.12rem !important;
        }
        [class*="st-key-product_row_"] {
            margin-top:.08rem !important;
            margin-bottom:.08rem !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div style="height:1.4rem"></div>',unsafe_allow_html=True)
    st.markdown(
        f"**{session['employee_name']}** · "
        f"{session.get('location_code','')} {session.get('location_name','')} · "
        f"**{counted}/{total}**"
    )

    if total:
        st.progress(counted/total,text=f'{counted} de {total}')

    current_sector_id=(
        st.session_state.get('count_nav_location_id')
        or session.get('location_id')
    )
    previous_sector_id,next_sector_id=_adjacent_sector_ids(session,current_sector_id)
    sector_nav_slot=st.empty()
    with sector_nav_slot.container():
        sector_nav=st.container(
            key='sector_sibling_nav',
            horizontal=True,
            horizontal_alignment='center',
            vertical_alignment='center',
            gap='xxsmall',
        )

        previous_clicked=sector_nav.button(
            '← Anterior',
            width=88,
            disabled=previous_sector_id is None,
            key=f'previous_sector_{current_sector_id}',
        )

        sector_nav.markdown(
            (
                "<div style='min-width:92px;text-align:center;"
                "font-size:.74rem;color:#666;line-height:1.9rem'>"
                f"Local <strong style='color:#222;font-size:1.06rem'>"
                f"{session.get('location_code','')}</strong></div>"
            ),
            unsafe_allow_html=True,
        )

        next_clicked=sector_nav.button(
            'Próximo →',
            width=88,
            disabled=next_sector_id is None,
            key=f'next_sector_{current_sector_id}',
        )

    if previous_clicked and previous_sector_id is not None:
        _go_to_sector(previous_sector_id,sector_nav_slot)

    if next_clicked and next_sector_id is not None:
        _go_to_sector(next_sector_id,sector_nav_slot)

    cols_per_row=3
    for start in range(0,len(items),cols_per_row):
        row=st.container(
            key=f"product_row_{start//cols_per_row}",
            horizontal=True,
            horizontal_alignment='center',
            vertical_alignment='center',
            gap='xxsmall',
        )

        for item in items[start:start+cols_per_row]:
            icon=STATUS_ICONS.get(item.get('status'),'⬜')
            pos=item.get('count_order') or item['product_id']
            label=f"{icon}\n{int(pos):02d}" if str(pos).isdigit() else f"{icon}\n{pos}"

            if row.button(
                label,
                key=f"pl_{item['product_id']}",
                help=item['name'],
                width=76,
            ):
                st.session_state.selected_product_id=item['product_id']
                st.session_state.pop('preview_product_id',None)
                st.session_state.pop('pending',None)
                st.rerun()

    missing=sum(i.get('status')=='not_counted' for i in items)
    flagged=sum(i.get('status')=='flagged' for i in items)
    zero=sum(i.get('status')=='confirmed_zero' for i in items)

    st.markdown(
        (
            '<div class="count-dashboard-summary">'
            f'<span><b>{counted}</b> contados</span>'
            f'<span><b>{missing}</b> faltando</span>'
            f'<span><b>{flagged}</b> flags</span>'
            f'<span><b>{zero}</b> zero</span>'
            '</div>'
        ),
        unsafe_allow_html=True,
    )

    if session.get('id'):
        if st.button('Revisar',use_container_width=True):
            go('review')
    else:
        st.button(
            'Revisar',
            use_container_width=True,
            disabled=True,
            help='A revisão fica disponível depois do primeiro registro de contagem.'
        )

    with st.container(key=f"nav_reference_dashboard_{session.get('location_id','draft')}"):
        c1,c2=st.columns(2)

        if c1.button(
            '← Voltar',
            use_container_width=True,
            key=f"dash_back_{session.get('location_id','draft')}"
        ):
            st.session_state.session_id=None
            st.session_state.pop('selected_product_id',None)
            current=(
                st.session_state.get('count_nav_location_id')
                or session.get('location_id')
            )

            if st.session_state.get('historical_direct_view'):
                # Leaving a "products directly in this sector" view should
                # return to that same sector, not climb the hierarchy.
                st.session_state.historical_direct_view=False
                st.session_state.count_nav_location_id=current
            else:
                # Resolve the real parent from the database at click time.
                # This avoids stale/incomplete count_parent_map state sending
                # Back directly to the hierarchy root.
                current_location=get_location(current) if current is not None else None
                st.session_state.count_nav_location_id=(
                    current_location.get('parent_id')
                    if current_location else None
                )

            st.rerun()

        if c2.button(
            'Início',
            use_container_width=True,
            key=f"dash_home_{session.get('location_id','draft')}"
        ):
            go('home')
