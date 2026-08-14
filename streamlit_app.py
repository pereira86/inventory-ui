from __future__ import annotations
from datetime import datetime
import pandas as pd
import streamlit as st
from app.database import init_db
from app.services.inventory_service import *
from app.ui.styles import apply_mobile_styles
from app.ui.count_dashboard import render_count_dashboard
from app.ui.count_form import render_count_form

st.set_page_config(page_title='Minato Inventario',page_icon='📦',layout='centered')
apply_mobile_styles(); init_db()

DEFAULT_STATE={
    'page':'home','session_id':None,'selected_product_id':None,
    'selected_employee_id':None,'selected_count_type':'Weekly inventory',
    'count_nav_location_id':None,'count_parent_map':{},'admin_section':'Estrutura operacional',
    'count_run_started_at':None,'count_force_new':False,'count_excluded_session_ids':[],
    'historical_session_id':None,'historical_direct_view':False,
}
for k,v in DEFAULT_STATE.items(): st.session_state.setdefault(k,v)

COUNT_TYPE_LABELS={
    'Weekly inventory':'Semanal',
    'Biweekly inventory':'Bissemanal',
    'Monthly inventory':'Mensal',
    'Partial recount':'Recontagem parcial',
}
COUNT_TYPE_VALUES=list(COUNT_TYPE_LABELS)

def _count_type_label(value:str)->str:
    return COUNT_TYPE_LABELS.get(value,value or '')


def go(page):
    if page=='home':
        st.session_state.pop('home_counter',None)
    st.session_state.page=page
    st.rerun()


def _flash():
    message=st.session_state.pop('_flash_message',None)
    if message: st.success(message)


def _set_flash(message:str):
    st.session_state._flash_message=message


def _reset_count_navigation():
    st.session_state.session_id=None
    st.session_state.selected_product_id=None
    st.session_state.count_nav_location_id=None
    st.session_state.count_parent_map={}
    st.session_state.count_force_new=False
    st.session_state.count_excluded_session_ids=[]
    st.session_state.historical_session_id=None
    st.session_state.historical_direct_view=False
    st.session_state.pop('pending',None)


def _open_existing_session(session_id:int):
    session=get_session(session_id)
    if not session:
        st.error('Contagem não encontrada.')
        return

    employee_id=session['employee_id']
    location_id=session.get('location_id')
    historical_multi=location_id is None and session_has_location_items(session_id)
    all_locs=list_locations_for_session(session_id) if historical_multi else list_locations_for_employee(employee_id)
    st.session_state.count_parent_map={loc['id']:loc.get('parent_id') for loc in all_locs}

    st.session_state.session_id=None if historical_multi else session_id
    st.session_state.historical_session_id=session_id if historical_multi else None
    st.session_state.historical_direct_view=False
    st.session_state.selected_employee_id=employee_id
    st.session_state.selected_count_type=session['count_type']
    st.session_state.count_nav_location_id=location_id
    st.session_state.count_run_started_at=session.get('started_at')
    st.session_state.count_force_new=False
    st.session_state.count_excluded_session_ids=[]
    st.session_state.selected_product_id=None
    st.session_state.pop('pending',None)
    st.session_state.page='count'
    st.rerun()


def _recent_counts(limit:int=5):
    rows=list_sessions(limit,real_only=True,for_dashboard=True)
    if not rows: return
    st.divider(); st.subheader('Contagens recentes')
    for row in rows:
        status='Concluída' if row['status']=='completed' else 'Em andamento'
        label=(
            f"{row['employee_name']} · {_count_type_label(row['count_type'])} · {status} · "
            f"{row['counted']}/{row['total']} · início {row['started_at']}"
        )

        # Internal Streamlit navigation: no URL/query string and therefore no
        # browser tab/window is created. The tertiary button keeps the visual
        # treatment light, close to a text link.
        # Keep the shortcut and dismiss control in one compact, tablet-safe
        # row. CSS in app/ui/styles.py prevents these two columns from stacking.
        with st.container(key=f"recent_row_{row['id']}"):
            c_link,c_close=st.columns([12,1],vertical_alignment='center',gap='small')
            if c_link.button(
                label,
                key=f"recent_open_{row['id']}",
                type='tertiary',
                use_container_width=True,
            ):
                _open_existing_session(int(row['id']))

            if c_close.button(
                '×',
                key=f"recent_hide_{row['id']}",
                type='tertiary',
                help='Remover da página inicial',
                use_container_width=True,
            ):
                hide_session_from_dashboard(int(row['id']))
                st.rerun()


def _nav_home_only(key:str):
    with st.container(key=f'nav_reference_{key}'):
        if st.button('Início',use_container_width=True,key=f'home_{key}'):
            go('home')


def _nav_back_home(back_to:int|None,key:str):
    with st.container(key=f'nav_reference_{key}'):
        c1,c2=st.columns(2)
        if c1.button('← Voltar',use_container_width=True,key=f'back_{key}'):
            st.session_state.count_nav_location_id=back_to
            st.session_state.selected_product_id=None
            st.session_state.session_id=None
            st.session_state.pop('pending',None)
            st.rerun()
        if c2.button('Início',use_container_width=True,key=f'home_{key}'):
            go('home')


def home():
    st.title('📦 Minato Inventario')
    st.caption('Contagem por setor e responsável.')
    _flash()
    employees=list_employees()
    if employees:
        by_employee={e['id']:e for e in employees}
        st.markdown('<div class="counter-emphasis-label">Quem está contando?</div>',unsafe_allow_html=True)
        with st.container(key='counter_emphasis'):
            selected_counter=st.selectbox(
                'Contador',[None]+list(by_employee),key='home_counter',label_visibility='collapsed',
                format_func=lambda x:'— Selecione quem está contando —' if x is None else by_employee[x]['name'],
            )
        st.caption('Selecione o contador antes de iniciar. Essa escolha define quais setores e produtos serão exibidos.')
        if st.button('▶️ Contagem',type='primary',use_container_width=True):
            if selected_counter is None:
                st.warning('É preciso selecionar um contador para entrar nas contagens.')
            else:
                _reset_count_navigation()
                st.session_state.selected_employee_id=selected_counter
                open_sessions=list_active_sessions(selected_counter)
                if open_sessions:
                    st.session_state.page='count_setup'
                    st.rerun()
                st.session_state.count_run_started_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                st.session_state.count_force_new=True
                st.session_state.count_excluded_session_ids=[]
                go('count')
    else: st.warning('Nenhum contador ativo.')
    c1,c2=st.columns(2)
    if c1.button('⚙️ Administração',use_container_width=True): go('admin')
    if c2.button('📋 Histórico',use_container_width=True): go('history')
    _recent_counts()


def count_setup():
    eid=st.session_state.selected_employee_id
    if not eid:
        go('home'); return
    employee=next((e for e in list_employees() if e['id']==eid),None)
    open_sessions=list_active_sessions(eid)
    st.header('Contagem')
    st.caption(f"Contador: {employee['name'] if employee else ''}")
    if not open_sessions:
        st.info('Não há contagem em andamento para este contador.')
        if st.button('Iniciar nova contagem',type='primary',use_container_width=True):
            _reset_count_navigation()
            st.session_state.selected_employee_id=eid
            st.session_state.count_run_started_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            st.session_state.count_force_new=True
            st.session_state.count_excluded_session_ids=[]
            go('count')
        _nav_home_only('count_setup_empty')
        return

    latest=open_sessions[0]
    st.info(
        f"Existe uma contagem em andamento: {latest.get('location_code') or ''} · "
        f"{latest.get('location_name') or ''} · {_count_type_label(latest.get('count_type') or '')} · "
        f"início {latest.get('started_at') or '—'}"
    )
    if st.button('Continuar última contagem em aberto',type='primary',use_container_width=True):
        _open_existing_session(latest['id'])
    if st.button('Iniciar uma contagem do zero',use_container_width=True):
        # Snapshot every session already in progress for this employee. During
        # this new run those IDs are ignored explicitly, avoiding timestamp/
        # timezone ambiguity while still allowing sessions created in THIS run
        # to be reopened when the employee revisits a leaf sector.
        excluded_ids=[int(s['id']) for s in open_sessions]
        _reset_count_navigation()
        st.session_state.selected_employee_id=eid
        st.session_state.count_run_started_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        st.session_state.count_force_new=True
        st.session_state.count_excluded_session_ids=excluded_ids
        go('count')

    confirm_key=f"confirm_delete_open_{latest['id']}"
    if st.session_state.get(confirm_key):
        st.warning('A última contagem em andamento será excluída permanentemente. As demais contagens permanecem intactas.')
        c1,c2=st.columns(2)
        if c1.button('Cancelar',use_container_width=True,key='cancel_delete_open_count'):
            st.session_state.pop(confirm_key,None); st.rerun()
        if c2.button('Excluir contagem em aberto',use_container_width=True,key='confirm_delete_open_count'):
            delete_session(latest['id'])
            st.session_state.pop(confirm_key,None)
            _set_flash('Contagem em andamento excluída.')
            st.rerun()
    elif st.button('Excluir a última contagem em aberto',use_container_width=True):
        st.session_state[confirm_key]=True; st.rerun()
    _nav_home_only('count_setup')


def _sector_state_label(state:str)->str:
    return {
        'not_started':'(Não iniciado)',
        'in_progress':'(Em processo)',
        'completed_clean':'(Concluído)',
        'completed_attention':'(Concluído · revisar)',
        'disabled':'(Sem itens)',
    }.get(state,'')


def _render_sector_level(employee_id:int, current_id:int|None):
    historical_id=st.session_state.get('historical_session_id')
    all_locs=list_locations_for_session(historical_id) if historical_id else list_locations_for_employee(employee_id)
    by_id={x['id']:x for x in all_locs}
    st.session_state.count_parent_map={x['id']:x.get('parent_id') for x in all_locs}
    children=[x for x in all_locs if x.get('parent_id')==current_id]
    current=by_id.get(current_id) if current_id else None
    progress=(
        get_session_location_progress_map(historical_id) if historical_id else
        get_location_progress_map(
            employee_id,st.session_state.selected_count_type,st.session_state.get('count_run_started_at'),
            resume_open=not st.session_state.get('count_force_new',False),
            exclude_session_ids=st.session_state.get('count_excluded_session_ids',[]),
        )
    )

    employee=next((e for e in list_employees() if e['id']==employee_id),None)
    if current:
        st.header(f"{current['code']} · {current['name']}")
        st.caption(f"Contador: {employee['name'] if employee else ''} · {_count_type_label(st.session_state.selected_count_type)}")
    else:
        st.header(f"Setores · {employee['name'] if employee else ''}")
        if historical_id:
            st.caption('Contagem histórica · selecione um setor para revisar ou editar os valores registrados.')
        else:
            st.caption('Selecione um setor raiz para avançar na hierarquia.')
            st.selectbox(
                'Periodicidade / tipo de contagem',
                COUNT_TYPE_VALUES,
                key='selected_count_type',
                format_func=_count_type_label,
            )
            progress=get_location_progress_map(
                employee_id,st.session_state.selected_count_type,st.session_state.get('count_run_started_at'),
                resume_open=not st.session_state.get('count_force_new',False),
                exclude_session_ids=st.session_state.get('count_excluded_session_ids',[]),
            )

    if historical_id and current_id is not None and current and current.get('employee_direct_products'):
        if st.button('Produtos diretamente neste setor',use_container_width=True,key=f'historical_direct_{current_id}'):
            st.session_state.historical_direct_view=True
            st.session_state.selected_product_id=None
            st.rerun()

    if not children:
        return False

    for loc in children:
        enabled=bool(loc.get('employee_has_products'))
        state=progress.get(loc['id'],{}).get('state','not_started') if enabled else 'disabled'
        label=f"{loc['code']} · {loc['name']}\n{_sector_state_label(state)}"
        with st.container(key=f"sector_{state}_{loc['id']}"):
            if st.button(label,key=f"nav_loc_{loc['id']}",use_container_width=True,disabled=not enabled,
                         help=None if enabled else 'Nenhum produto desta contagem neste setor ou em seus subsetores.'):
                st.session_state.count_nav_location_id=loc['id']
                st.session_state.selected_product_id=None
                st.session_state.session_id=None
                st.session_state.historical_direct_view=False
                st.rerun()

    if current_id is None:
        _nav_home_only('count_root')
    else:
        _nav_back_home(current.get('parent_id') if current else None,f'level_{current_id}')
    return True


def count_page():
    eid=st.session_state.selected_employee_id
    if not eid:
        go('home'); return

    historical_id=st.session_state.get('historical_session_id')
    if historical_id:
        historical=get_session(historical_id)
        if not historical:
            st.session_state.historical_session_id=None; go('home'); return
        current_id=st.session_state.get('count_nav_location_id')
        if current_id is None:
            st.session_state.historical_direct_view=False
            _render_sector_level(eid,None); return
        children=list_child_locations(current_id,active_only=True)
        if children and not st.session_state.get('historical_direct_view'):
            _render_sector_level(eid,current_id); return
        loc=get_location(current_id)
        items=get_session_items(historical_id,current_id)
        if not items:
            st.warning('Esta contagem histórica não possui produtos registrados neste setor.')
            _nav_back_home(loc.get('parent_id') if loc else None,f'historical_empty_{current_id}')
            return
        session=dict(historical)
        session.update({'location_id':current_id,'location_code':loc['code'] if loc else '', 'location_name':loc['name'] if loc else ''})
        if st.session_state.get('selected_product_id'):
            render_count_form(session,items)
        else:
            render_count_dashboard(session,items,go=go)
        return

    if st.session_state.session_id:
        session=get_session(st.session_state.session_id)
        if not session:
            st.session_state.session_id=None; st.rerun(); return
        items=get_session_items(session['id'])
        if st.session_state.get('selected_product_id'):
            render_count_form(session,items)
        else:
            render_count_dashboard(session,items,go=go)
        return

    current_id=st.session_state.get('count_nav_location_id')
    if current_id is None:
        _render_sector_level(eid,None)
        return

    children=list_child_locations(current_id,active_only=True)
    if children:
        _render_sector_level(eid,current_id)
        return

    active=find_active_session(
        eid,current_id,st.session_state.selected_count_type,
        st.session_state.get('count_run_started_at') if st.session_state.get('count_force_new') else None,
        exclude_session_ids=st.session_state.get('count_excluded_session_ids',[]),
    )
    if active:
        st.session_state.session_id=active['id']; st.rerun(); return

    loc=get_location(current_id)
    employee=next((e for e in list_employees() if e['id']==eid),None)
    items=list_count_items_for_location(eid,current_id)
    if not items:
        st.warning('Este setor folha não possui produtos atribuídos a este contador.')
        _nav_back_home(loc.get('parent_id') if loc else None,f'empty_leaf_{current_id}')
        return

    draft_session={
        'id':None,'employee_id':eid,'employee_name':employee['name'] if employee else '',
        'location_id':current_id,'location_code':loc['code'] if loc else '',
        'location_name':loc['name'] if loc else '', 'count_type':st.session_state.selected_count_type,
        'status':'draft','started_at':None,
    }
    if st.session_state.get('selected_product_id'):
        render_count_form(draft_session,items)
    else:
        render_count_dashboard(draft_session,items,go=go)


def review():
    review_id=st.session_state.session_id or st.session_state.get('historical_session_id')
    if not review_id:
        go('count'); return
    s=get_session(review_id)
    if not s:
        go('home'); return

    # Review is always scoped to the sector from which the user opened it.
    # Historical sessions can contain many sectors, while regular sessions
    # normally have a single location_id.
    review_location_id=st.session_state.get('count_nav_location_id') or s.get('location_id')
    items=get_session_items(review_id,review_location_id) if review_location_id else get_session_items(review_id)
    review_location=get_location(review_location_id) if review_location_id else None

    if review_location:
        st.header(f"Revisão · {review_location['code']} · {review_location['name']}")
    else:
        st.header(f"Revisão #{s['id']}")
    df=pd.DataFrame([{'Produto':i['name'],'Setor':f"{i.get('location_code') or ''} {i.get('location_name') or ''}",'Quantidade':i['quantity'],'Unidade':i['unit'],'Status':i['status'],'Observação':i['notes'] or ''} for i in items])
    st.dataframe(df,use_container_width=True,hide_index=True)
    missing=[i for i in items if i['status']=='not_counted']
    if s['status']!='completed' and not missing and st.button('Finalizar contagem',type='primary',use_container_width=True):
        complete_session(s['id']); st.rerun()
    if missing: st.warning(f'{len(missing)} item(ns) ainda não contado(s).')
    if st.button('Continuar contagem',use_container_width=True):
        st.session_state.selected_product_id=None; go('count')
    _nav_home_only('review')


def history():
    st.header('Histórico')
    _flash()
    rows=list_sessions(500,real_only=True)
    if not rows:
        st.info('Nenhuma contagem disponível no histórico.')
        _nav_home_only('history')
        return

    def session_label(row):
        status='Concluída' if row['status']=='completed' else 'Em andamento'
        return (
            f"#{row['id']} · {row['employee_name']} · {_count_type_label(row['count_type'])} · {status} · "
            f"{row.get('counted',0)}/{row.get('total',0)} · início {row.get('started_at') or '—'}"
        )

    by_id={row['id']:row for row in rows}
    selected_id=st.selectbox(
        'Selecionar contagem',
        list(by_id),
        format_func=lambda sid: session_label(by_id[sid]),
        key='history_selected_session_id',
    )
    row=by_id[selected_id]

    st.caption(
        f"Início: {row.get('started_at') or '—'} · Final: {row.get('completed_at') or '—'} · "
        f"Itens: {row.get('counted',0)}/{row.get('total',0)}"
    )

    if st.button('Abrir / editar contagem',type='primary',use_container_width=True,key=f"open_history_{selected_id}"):
        _open_existing_session(selected_id)

    employees=list_employees()
    employee_names={e['name']:e['id'] for e in employees}
    count_types=COUNT_TYPE_VALUES

    st.markdown('**Dados da contagem**')
    current_employee=row['employee_name'] if row['employee_name'] in employee_names else next(iter(employee_names),None)
    employee_options=list(employee_names)
    employee_index=employee_options.index(current_employee) if current_employee in employee_options else 0
    selected_employee=st.selectbox('Contador',employee_options,index=employee_index,key=f"history_employee_{selected_id}") if employee_options else None

    type_options=list(count_types)
    if row.get('count_type') and row['count_type'] not in type_options:
        type_options.insert(0,row['count_type'])
    type_index=type_options.index(row.get('count_type')) if row.get('count_type') in type_options else 0
    selected_type=st.selectbox('Tipo / periodicidade',type_options,index=type_index,key=f"history_type_{selected_id}")

    if st.button('Salvar dados da contagem',use_container_width=True,key=f"save_meta_{selected_id}",disabled=not selected_employee):
        try:
            update_session_metadata(selected_id,employee_names[selected_employee],selected_type)
            _set_flash(f"Contagem #{selected_id} atualizada.")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))

    st.divider()
    hide_key=f"confirm_hide_history_{selected_id}"
    delete_key=f"confirm_delete_history_{selected_id}"

    if st.session_state.get(delete_key):
        st.error('Excluir permanentemente apaga a sessão e todas as contagens de produtos vinculadas a ela. Essa ação não pode ser desfeita.')
        c1,c2=st.columns(2)
        if c1.button('Cancelar',use_container_width=True,key=f"cancel_delete_{selected_id}"):
            st.session_state.pop(delete_key,None); st.rerun()
        if c2.button('Excluir permanentemente',type='primary',use_container_width=True,key=f"confirm_delete_{selected_id}"):
            if delete_session(selected_id):
                st.session_state.pop(delete_key,None)
                st.session_state.pop('history_selected_session_id',None)
                _set_flash(f"Contagem #{selected_id} excluída permanentemente.")
                st.rerun()
            st.error('Contagem não encontrada.')
    elif st.session_state.get(hide_key):
        st.info('A contagem sairá do seletor de Histórico, mas continuará preservada no banco.')
        c1,c2=st.columns(2)
        if c1.button('Cancelar',use_container_width=True,key=f"cancel_hide_{selected_id}"):
            st.session_state.pop(hide_key,None); st.rerun()
        if c2.button('Confirmar remoção',type='primary',use_container_width=True,key=f"confirm_hide_{selected_id}"):
            if hide_session_from_history(selected_id):
                st.session_state.pop(hide_key,None)
                st.session_state.pop('history_selected_session_id',None)
                _set_flash(f"Contagem #{selected_id} removida do histórico visível. Os dados foram preservados.")
                st.rerun()
            st.error('Contagem não encontrada.')
    else:
        c1,c2=st.columns(2)
        if c1.button('Remover do histórico',use_container_width=True,key=f"hide_history_{selected_id}"):
            st.session_state[hide_key]=True; st.rerun()
        if c2.button('Excluir permanentemente',use_container_width=True,key=f"delete_history_{selected_id}"):
            st.session_state[delete_key]=True; st.rerun()

    _nav_home_only('history')


def _loc_options(include_none=False, exclude_id:int|None=None):
    locs=[x for x in list_locations() if x['id']!=exclude_id]
    labels={f"{x['code']} · {x['name']}":x['id'] for x in locs}
    if include_none: return {'— raiz —':None,**labels}
    return labels


def _suffix_for_location(loc:dict)->str:
    code=str(loc.get('code') or '')
    if loc.get('parent_id') is None: return code
    return code.rsplit('.',1)[-1]


def _ancestor_path(location_id:int|None, rows:list[dict])->list[int]:
    if location_id is None: return []
    by_id={r['id']:r for r in rows}
    path=[]; current=by_id.get(location_id)
    while current:
        path.append(current['id'])
        current=by_id.get(current.get('parent_id'))
    return list(reversed(path))


def _descendants(rows:list[dict], parent_id:int)->list[dict]:
    by_parent={}
    for r in rows: by_parent.setdefault(r.get('parent_id'),[]).append(r)
    out=[]; stack=list(reversed(by_parent.get(parent_id,[])))
    while stack:
        row=stack.pop(); out.append(row)
        stack.extend(reversed(by_parent.get(row['id'],[])))
    order={r['id']:i for i,r in enumerate(rows)}
    return sorted(out,key=lambda r:order.get(r['id'],999999))


def _set_parent_selector_path(prefix:str,parent_id:int|None,rows:list[dict]):
    path=_ancestor_path(parent_id,rows)
    st.session_state[f'{prefix}_l1']=path[0] if len(path)>=1 else None
    st.session_state[f'{prefix}_l2']=path[1] if len(path)>=2 else None
    st.session_state[f'{prefix}_l3']=path[-1] if len(path)>=3 else None


def _hierarchy_parent_selector(prefix:str,rows:list[dict],exclude_id:int|None=None)->int|None:
    usable=[r for r in rows if r['id']!=exclude_id and r.get('active',1)]
    if exclude_id is not None:
        blocked={x['id'] for x in _descendants(rows,exclude_id)}|{exclude_id}
        usable=[r for r in usable if r['id'] not in blocked]
    by_id={r['id']:r for r in usable}
    blank='— em branco —'

    roots=[r for r in usable if r.get('parent_id') is None]
    l1_options=[None]+[r['id'] for r in roots]
    l1=st.selectbox('1º nível',l1_options,key=f'{prefix}_l1',format_func=lambda x:blank if x is None else f"{by_id[x]['code']} · {by_id[x]['name']}")

    seconds=[r for r in usable if l1 is not None and r.get('parent_id')==l1]
    l2_options=[None]+[r['id'] for r in seconds]
    if st.session_state.get(f'{prefix}_l2') not in l2_options: st.session_state[f'{prefix}_l2']=None
    l2=st.selectbox('2º nível',l2_options,key=f'{prefix}_l2',format_func=lambda x:blank if x is None else f"{by_id[x]['code']} · {by_id[x]['name']}",disabled=l1 is None)

    deep=_descendants(usable,l2) if l2 is not None else []
    l3_options=[None]+[r['id'] for r in deep]
    if st.session_state.get(f'{prefix}_l3') not in l3_options: st.session_state[f'{prefix}_l3']=None
    l3=st.selectbox('3º nível e mais profundos',l3_options,key=f'{prefix}_l3',format_func=lambda x:blank if x is None else f"{by_id[x]['code']} · {by_id[x]['name']}",disabled=l2 is None)
    st.caption('Deixe o próximo campo em branco quando o pai desejado já estiver selecionado. O terceiro campo reúne também níveis mais profundos.')
    return l3 if l3 is not None else l2 if l2 is not None else l1


def _clear_name_on_rerun(key:str,flag:str):
    if st.session_state.pop(flag,False):
        st.session_state.pop(key,None)


def _render_sector_admin():
    locs=list_locations(active_only=False)

    st.subheader('Criar setor')
    _clear_name_on_rerun('new_location_name','_clear_new_location_name')
    parent_id=_hierarchy_parent_selector('new_parent',locs)
    sublevel=st.text_input('Próximo nível / índice',placeholder='Ex.: 5',key='new_location_sublevel')
    name=st.text_input('Nome do setor',key='new_location_name')
    preview=sublevel.strip().strip('.')
    if preview:
        parent=get_location(parent_id) if parent_id else None
        full=f"{parent['code']}.{preview}" if parent else preview
        st.caption(f'Código resultante: {full}')
    if st.button('Criar setor',type='primary',key='create_location_button'):
        try:
            create_location_from_parent(parent_id,sublevel,name)
            # Preserve hierarchy + index. Only the name is cleared.
            st.session_state._clear_new_location_name=True
            _set_flash('Setor criado e inserido na posição hierárquica correta.')
            st.rerun()
        except Exception as e: st.error(str(e))

    st.divider(); st.subheader('Editar setor')
    if locs:
        by_id={l['id']:l for l in locs}
        edit_id=st.selectbox('Setor a modificar',[l['id'] for l in locs],key='edit_location_id',format_func=lambda x:f"{by_id[x]['code']} · {by_id[x]['name']}")
        l=by_id[edit_id]
        if st.session_state.get('_loaded_edit_location_id')!=edit_id:
            _set_parent_selector_path('edit_parent',l.get('parent_id'),locs)
            st.session_state.edit_location_sublevel=_suffix_for_location(l)
            st.session_state.edit_location_active=bool(l['active'])
            st.session_state.pop('edit_location_name',None)
            st.session_state._loaded_edit_location_id=edit_id
            st.rerun()
        _clear_name_on_rerun('edit_location_name','_clear_edit_location_name')
        parent2=_hierarchy_parent_selector('edit_parent',locs,exclude_id=l['id'])
        nsub=st.text_input('Próximo nível / índice',key='edit_location_sublevel')
        nname=st.text_input('Novo nome (opcional)',key='edit_location_name',placeholder=f"Atual: {l['name']}")
        active=st.checkbox('Ativo',key='edit_location_active')
        st.caption('Deixe o nome em branco para manter o nome atual.')
        if st.button('Salvar alterações',key='save_location_button'):
            try:
                update_location_from_parent(l['id'],parent2,nsub,nname.strip() or l['name'],active)
                st.session_state._clear_edit_location_name=True
                _set_flash('Setor atualizado e reordenado. As seleções foram preservadas.')
                st.rerun()
            except Exception as e: st.error(str(e))

    # The hierarchy list intentionally stays at the end of the sector administration page.
    st.divider(); st.subheader('Lista de setores e subsetores')
    st.caption('Hierarquia completa em ordem natural.')
    for l in list_locations(active_only=False):
        depth=len(l['code'].split('.'))-1
        prefix=' '*depth+'↳ ' if depth else ''
        st.write(f"{prefix}**{l['code']}** · {l['name']}  · {l['product_count']} produto(s){' · inativo' if not l['active'] else ''}")


def _render_catalog_admin():
    locs=list_locations(active_only=True)
    employees=list_employees(False)
    products=list_products()
    emp_opts={'— sem contador —':None,**{e['name']:e['id'] for e in employees}}

    st.subheader('Adicionar / remover setores')
    if st.session_state.pop('_clear_catalog_section_fields',False):
        st.session_state.pop('catalog_section_name',None)
        st.session_state.pop('catalog_section_sublevel',None)

    selected_location_id=_hierarchy_parent_selector('catalog_section_location',locs)
    sublevel=st.text_input('Próximo nível / índice',placeholder='Ex.: 3',key='catalog_section_sublevel')
    section_name=st.text_input('Nome do setor / subseção',key='catalog_section_name')
    section_feedback=st.session_state.get('_catalog_section_feedback')
    if section_feedback:
        st.caption(section_feedback)

    c_add,c_remove=st.columns(2)
    if c_add.button('Adicionar',type='primary',use_container_width=True,key='catalog_section_add_button'):
        try:
            new_id=create_location_from_parent(selected_location_id,sublevel,section_name)
            created=get_location(new_id)
            if created:
                st.session_state._catalog_section_feedback=f"{created['code']} · {created['name']} foi adicionado com sucesso."
            else:
                st.session_state._catalog_section_feedback='Setor adicionado com sucesso.'
            st.session_state._clear_catalog_section_fields=True
            st.rerun()
        except Exception as exc: st.error(str(exc))

    remove_disabled=selected_location_id is None
    if c_remove.button('Remover',use_container_width=True,key='catalog_section_remove_button',disabled=remove_disabled):
        try:
            remove_loc=get_location(selected_location_id)
            if not remove_loc:
                raise ValueError('Selecione o setor ou subseção a remover.')
            removed_label=f"{remove_loc['code']} · {remove_loc['name']}"
            deactivate_location(selected_location_id)
            st.session_state._catalog_section_feedback=f'{removed_label} foi removido com sucesso. Produtos que pertenciam diretamente a esse setor permaneceram no cadastro mestre, sem setor.'
            st.session_state._clear_catalog_section_fields=True
            st.rerun()
        except Exception as exc: st.error(str(exc))
    if selected_location_id is not None:
        selected=get_location(selected_location_id)
        if selected:
            st.caption(f"Selecionado: {selected['code']} · {selected['name']}. Para adicionar, ele será o pai; para remover, ele próprio será removido.")
    else:
        st.caption('Em branco cria um setor raiz. Para remover, selecione o setor desejado na hierarquia acima.')

    st.divider(); st.subheader('Selecionar produtos em setor')
    product_location_id=_hierarchy_parent_selector('catalog_product_location',locs)
    if product_location_id is None:
        st.caption('Selecione um setor para adicionar ou remover produtos.')
        return

    selected_loc=get_location(product_location_id)
    if selected_loc:
        st.caption(f"Setor selecionado: {selected_loc['code']} · {selected_loc['name']}")

    current_assignments=[r for r in list_product_locations() if r['location_id']==product_location_id]
    assigned_product_ids={r['product_id'] for r in current_assignments}
    product_feedback=st.session_state.get('_catalog_product_feedback')
    if product_feedback:
        st.caption(product_feedback)

    add_col,remove_col=st.columns(2,gap='large')

    with add_col:
        st.markdown('#### Adicionar produto ao setor')
        search=st.text_input('Buscar produto por nome ou código',key='catalog_product_add_search',placeholder='Digite parte do nome ou código')
        needle=search.strip().casefold()
        add_candidates=[]
        for product in products:
            haystack=f"{product.get('name','')} {product.get('external_code') or ''}".casefold()
            if product['id'] not in assigned_product_ids and (not needle or needle in haystack):
                add_candidates.append(product)
        if add_candidates:
            by_product={p['id']:p for p in add_candidates}
            product_id=st.selectbox(
                'Produto para adicionar',
                [p['id'] for p in add_candidates],
                key='catalog_product_add_choice',
                format_func=lambda x:f"{by_product[x]['name']} · {by_product[x].get('external_code') or 'sem código'}"
            )
            employee_label=st.selectbox('Contador',list(emp_opts),key='catalog_product_employee')
            c1,c2=st.columns(2)
            mn=c1.number_input('Mínimo',min_value=0.0,value=0.0,key='catalog_product_min')
            mx=c2.number_input('Máximo',min_value=0.0,value=0.0,key='catalog_product_max')
            if st.button('Adicionar ao setor',type='primary',use_container_width=True,key='catalog_product_add_button'):
                try:
                    assign_product_to_location(product_id,product_location_id,emp_opts[employee_label],mn or None,mx or None)
                    product=by_product[product_id]
                    st.session_state._catalog_product_feedback=(
                        f"{selected_loc['code']} · {selected_loc['name']} · {product['name']} foi adicionado com sucesso."
                        if selected_loc else 'Produto associado com sucesso.'
                    )
                    st.session_state.pop('catalog_product_add_search',None)
                    st.rerun()
                except Exception as exc: st.error(str(exc))
        elif search.strip():
            st.caption('Nenhum produto disponível corresponde à busca.')
        elif len(assigned_product_ids)==len(products) and products:
            st.caption('Todos os produtos do cadastro mestre já estão associados a este setor.')
        else:
            st.caption('Nenhum produto disponível no cadastro mestre.')

    with remove_col:
        st.markdown('#### Remover produto do setor')
        if current_assignments:
            by_assignment={r['product_location_id']:r for r in current_assignments}
            remove_id=st.selectbox(
                'Produtos deste setor',
                [r['product_location_id'] for r in current_assignments],
                key='catalog_product_remove_choice',
                format_func=lambda x:f"{by_assignment[x]['name']} · {by_assignment[x].get('external_code') or 'sem código'}"
            )
            selected_assignment=by_assignment[remove_id]
            st.caption(f"{len(current_assignments)} produto(s) associado(s) a este setor.")
            if st.button('Remover do setor',use_container_width=True,key='catalog_product_remove_button'):
                try:
                    remove_product_location(remove_id)
                    st.session_state._catalog_product_feedback=f"{selected_assignment['location_code']} · {selected_assignment['location_name']} · {selected_assignment['name']} foi removido com sucesso."
                    st.rerun()
                except Exception as exc: st.error(str(exc))
        else:
            st.caption('Este setor ainda não possui produtos associados.')

def _render_products_admin():
    all_products=list_products()
    units=sorted({(p.get('unit') or '').strip() for p in all_products if (p.get('unit') or '').strip()},key=str.casefold)
    categories=sorted({(p.get('category') or '').strip() for p in all_products if (p.get('category') or '').strip()},key=str.casefold)
    locs=list_locations(active_only=True)

    st.subheader('Cadastrar produto')
    with st.form('new_product'):
        code=st.text_input('Código do novo produto')
        name=st.text_input('Nome do novo produto')
        unit_options=['— selecione —']+units
        category_options=['— selecione —']+categories
        unit=st.selectbox('Unidade',unit_options,help='Somente unidades já cadastradas podem ser usadas neste campo.')
        category=st.selectbox('Categoria',category_options,help='Somente categorias já cadastradas podem ser usadas neste campo.')
        location_options=[None]+[l['id'] for l in locs]
        by_loc={l['id']:l for l in locs}
        location_id=st.selectbox(
            'Adicionar a um setor (opcional)',location_options,
            format_func=lambda x:'— deixar em branco —' if x is None else f"{by_loc[x]['code']} · {by_loc[x]['name']}"
        )
        create=st.form_submit_button('Cadastrar produto')
    if create:
        try:
            if unit=='— selecione —':
                raise ValueError('Selecione uma unidade já cadastrada.')
            selected_category='' if category=='— selecione —' else category
            product_id=create_product(name,code,unit,selected_category)
            if location_id is not None:
                assign_product_to_location(product_id,location_id,None,None,None)
                loc=get_location(location_id)
                _set_flash(f"Produto cadastrado e adicionado a {loc['code']} · {loc['name']}.")
            else:
                _set_flash('Produto cadastrado sem setor.')
            st.rerun()
        except Exception as e: st.error(str(e))

    st.divider(); st.subheader('Lista de produtos')
    q=st.text_input('Buscar no cadastro mestre',key='master_search')
    products=list_products(q)
    if products:
        # Show the current active sector assignment(s) directly in the master
        # product list. A product may be linked to more than one sector, so the
        # sectors are combined into a single readable column.
        assignments=list_product_locations()
        sectors_by_product={}
        counters_by_product={}
        for row in assignments:
            sectors_by_product.setdefault(row['product_id'],[]).append(
                f"{row['location_code']} · {row['location_name']}"
            )
            counter=(row.get('counter_name') or '').strip() or 'Sem contador'
            counters_by_product.setdefault(row['product_id'],[]).append(counter)
        table_rows=[]
        for product in products:
            row=dict(product)
            row['sector']='; '.join(sectors_by_product.get(product['id'],[])) or 'Sem setor'
            counters=[]
            for counter in counters_by_product.get(product['id'],[]):
                if counter not in counters: counters.append(counter)
            row['counter']='; '.join(counters) or 'Sem contador'
            table_rows.append(row)
        df=pd.DataFrame(table_rows)[['external_code','name','unit','sector','counter']]
        df=df.rename(columns={
            'external_code':'Código','name':'Produto','unit':'Unidade',
            'sector':'Setor','counter':'Contador'
        })
        st.dataframe(df,use_container_width=True,hide_index=True)
    else:
        st.caption('Nenhum produto encontrado.')
    st.caption('Produtos sem setor permanecem disponíveis no cadastro mestre e não aparecem em contagens.')


def admin():
    st.header('⚙️ Administração do estoque')
    _flash()
    sections=['Estrutura operacional','Cadastro de produtos','Layout de setores']
    # Keep the operational catalog as the default working view. The old full
    # sector-management screen is retained only as a read-oriented layout view
    # at the end, since create/remove operations now live in the catalog.
    if st.session_state.get('admin_section')=='Produtos':
        st.session_state.admin_section='Cadastro de produtos'
    if st.session_state.get('admin_section') not in sections:
        st.session_state.admin_section='Estrutura operacional'
    section=st.radio('Seção',sections,horizontal=True,key='admin_section',label_visibility='collapsed')
    if section=='Estrutura operacional': _render_catalog_admin()
    elif section=='Cadastro de produtos': _render_products_admin()
    else:
        st.subheader('Layout de setores')
        locs=list_locations(active_only=False)
        if locs:
            df=pd.DataFrame([{
                'Código':x.get('code',''),'Setor / subseção':x.get('name',''),
                'Status':'Ativo' if x.get('active') else 'Inativo'
            } for x in locs])
            st.dataframe(df,use_container_width=True,hide_index=True)
        else:
            st.caption('Nenhum setor cadastrado.')
    _nav_home_only('admin')


pages={'home':home,'count_setup':count_setup,'count':count_page,'review':review,'history':history,'admin':admin}
pages.get(st.session_state.page,home)()
