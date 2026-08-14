from __future__ import annotations
from collections.abc import Callable
import streamlit as st

STATUS_ICONS={'not_counted':'⬜','counted':'🟩','flagged':'🟧','confirmed_zero':'🟥'}


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

    # Compact 3-per-row product grid for mobile/tablet.
    # Fixed button width avoids Streamlit stretching each product across the screen.
    cols_per_row=3
    for start in range(0,len(items),cols_per_row):
        row=st.container(
            key=f"product_row_{start//cols_per_row}",
            horizontal=True,
            horizontal_alignment='left',
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
                st.session_state.pop('pending',None)
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
            current=st.session_state.get('count_nav_location_id')

            if st.session_state.get('historical_direct_view'):
                st.session_state.historical_direct_view=False
            else:
                parent_map=st.session_state.get('count_parent_map',{})
                st.session_state.count_nav_location_id=parent_map.get(current)

            st.rerun()

        if c2.button(
            'Início',
            use_container_width=True,
            key=f"dash_home_{session.get('location_id','draft')}"
        ):
            go('home')
