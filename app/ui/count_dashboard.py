from __future__ import annotations
from collections.abc import Callable
from html import escape
import streamlit as st
from app.services.inventory_service import get_location, list_child_locations

STATUS_ICONS={'not_counted':'⬜','counted':'🟩','flagged':'🟧','confirmed_zero':'🟥'}


def _adjacent_sector_ids(location_id:int|None)->tuple[int|None,int|None]:
    if location_id is None:
        return None,None
    current=get_location(location_id)
    if not current:
        return None,None
    siblings=list_child_locations(current.get('parent_id'),active_only=True)
    ids=[int(row['id']) for row in siblings]
    try:
        index=ids.index(int(location_id))
    except (ValueError,TypeError):
        return None,None
    previous_id=ids[index-1] if index>0 else None
    next_id=ids[index+1] if index+1<len(ids) else None
    return previous_id,next_id


def _go_to_sector(location_id:int)->None:
    st.session_state.session_id=None
    st.session_state.selected_product_id=None
    st.session_state.count_nav_location_id=location_id
    st.session_state.historical_direct_view=False
    st.session_state.pop('preview_product_id',None)
    st.session_state.pop('pending',None)
    st.rerun()


def render_count_dashboard(session:dict,items:list[dict],go:Callable[[str],None],**kwargs)->None:
    counted=sum(i.get('status')!='not_counted' for i in items)
    total=len(items)

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
    previous_sector_id,next_sector_id=_adjacent_sector_ids(current_sector_id)
    sector_nav=st.container(
        key='sector_sibling_nav',
        horizontal=True,
        horizontal_alignment='right',
        vertical_alignment='center',
        gap='xxsmall',
    )
    if sector_nav.button(
        '← Setor anterior',
        width=112,
        disabled=previous_sector_id is None,
        key=f'previous_sector_{current_sector_id}',
    ) and previous_sector_id is not None:
        _go_to_sector(previous_sector_id)
    if sector_nav.button(
        'Próximo setor →',
        width=112,
        disabled=next_sector_id is None,
        key=f'next_sector_{current_sector_id}',
    ) and next_sector_id is not None:
        _go_to_sector(next_sector_id)

    # Two-tap product selection for touch devices:
    # first tap previews the product name, second tap opens it.
    preview_id=st.session_state.get('preview_product_id')
    current_ids={i['product_id'] for i in items}
    if preview_id not in current_ids:
        preview_id=None
        st.session_state.pop('preview_product_id',None)

    preview_item=next((i for i in items if i['product_id']==preview_id),None)
    preview_text=(
        f"<strong>{escape(preview_item['name'])}</strong> "
        f"<span style=\"font-weight:400;\">(clique novamente para selecionar)</span>"
        if preview_item else "&nbsp;"
    )
    st.markdown(
        f'<div class="product-preview-slot">{preview_text}</div>',
        unsafe_allow_html=True,
    )

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
                if st.session_state.get('preview_product_id')==item['product_id']:
                    st.session_state.selected_product_id=item['product_id']
                    st.session_state.pop('preview_product_id',None)
                    st.session_state.pop('pending',None)
                else:
                    st.session_state.preview_product_id=item['product_id']
                st.rerun()

    m1,m2,m3,m4=st.columns(4)
    m1.metric('Contados',counted)
    m2.metric('Faltando',sum(i.get('status')=='not_counted' for i in items))
    m3.metric('Flags',sum(i.get('status')=='flagged' for i in items))
    m4.metric('Zero',sum(i.get('status')=='confirmed_zero' for i in items))

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
