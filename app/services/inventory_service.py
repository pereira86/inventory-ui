from __future__ import annotations
from typing import Any
import re
from app.database import get_connection


def _natural_part(value: str) -> tuple:
    parts = re.split(r'(\d+)', str(value or ''))
    return tuple(int(p) if p.isdigit() else p.lower() for p in parts if p != '')


def _location_sort_key(loc: dict) -> tuple:
    return tuple(_natural_part(part) for part in str(loc.get('code') or '').split('.'))


def _sort_locations(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Depth-first tree order; siblings use natural code order (1.2 before 1.10)."""
    by_id={r['id']:r for r in rows}
    children:dict[int|None,list[dict[str,Any]]]={}
    for row in rows:
        parent=row.get('parent_id')
        if parent not in by_id:
            parent=None
        children.setdefault(parent,[]).append(row)
    for group in children.values():
        group.sort(key=lambda r:(_location_sort_key(r),_natural_part(r.get('name') or '')))
    ordered=[]; visited=set()
    def visit(parent_id:int|None):
        for row in children.get(parent_id,[]):
            if row['id'] in visited: continue
            visited.add(row['id']); ordered.append(row); visit(row['id'])
    visit(None)
    # Defensive fallback for malformed/cyclic legacy data.
    for row in sorted(rows,key=lambda r:(_location_sort_key(r),_natural_part(r.get('name') or ''))):
        if row['id'] not in visited: ordered.append(row)
    return ordered


def list_employees(active_only: bool=True) -> list[dict[str,Any]]:
    q='SELECT * FROM employees' + (' WHERE active=1' if active_only else '') + ' ORDER BY name'
    with get_connection() as c: rows=c.execute(q).fetchall()
    return [dict(r) for r in rows]


GLOBAL_COUNT_ACCESS_NAMES={'daniel','felipe'}

def employee_has_global_count_access(employee_id:int)->bool:
    with get_connection() as c:
        row=c.execute('SELECT name FROM employees WHERE id=? AND active=1',(employee_id,)).fetchone()
    name=str(row['name'] or '').strip().casefold() if row else ''
    first_name=name.split()[0] if name else ''
    return first_name in GLOBAL_COUNT_ACCESS_NAMES


def add_employee(name:str) -> int:
    name=name.strip()
    if not name: raise ValueError('Informe o nome.')
    with get_connection() as c:
        c.execute('INSERT OR IGNORE INTO employees(name,active) VALUES (?,1)',(name,))
        c.execute('UPDATE employees SET active=1 WHERE name=?',(name,))
        return int(c.execute('SELECT id FROM employees WHERE name=?',(name,)).fetchone()[0])


def list_categories() -> list[str]:
    with get_connection() as c: rows=c.execute("SELECT DISTINCT category FROM products WHERE active=1 AND TRIM(COALESCE(category,''))<>'' ORDER BY category").fetchall()
    return [r[0] for r in rows]


def list_products(search:str='') -> list[dict[str,Any]]:
    with get_connection() as c:
        if search.strip():
            s=f"%{search.strip()}%"
            rows=c.execute("SELECT * FROM products WHERE active=1 AND (name LIKE ? OR external_code LIKE ?) ORDER BY name",(s,s)).fetchall()
        else:
            rows=c.execute('SELECT * FROM products WHERE active=1 ORDER BY name').fetchall()
    return [dict(r) for r in rows]


def create_product(name:str, external_code:str, unit:str, category:str='') -> int:
    name=name.strip(); unit=unit.strip().upper()
    if not name or not unit: raise ValueError('Nome e unidade são obrigatórios.')
    with get_connection() as c:
        cur=c.execute("INSERT INTO products(external_code,name,category,storage_area,unit,active) VALUES (?,?,?,?,?,1)",(external_code.strip() or None,name,category.strip(),' ',unit))
        return int(cur.lastrowid)


def list_locations(active_only:bool=True) -> list[dict[str,Any]]:
    where='WHERE l.active=1' if active_only else ''
    with get_connection() as c:
        rows=c.execute(f'''SELECT l.*, p.code parent_code, p.name parent_name,
            (SELECT COUNT(*) FROM product_locations pl WHERE pl.location_id=l.id AND pl.active=1) product_count
            FROM storage_locations l LEFT JOIN storage_locations p ON p.id=l.parent_id {where}''').fetchall()
    return _sort_locations([dict(r) for r in rows])


def get_location(location_id:int) -> dict[str,Any]|None:
    return next((x for x in list_locations(active_only=False) if x['id']==location_id),None)


def location_label(loc:dict) -> str:
    return f"{loc['code']} · {loc['name']}"


def list_child_locations(parent_id:int|None, active_only:bool=True) -> list[dict[str,Any]]:
    return [x for x in list_locations(active_only=active_only) if x.get('parent_id')==parent_id]


def _descendant_ids_from_rows(rows:list[dict[str,Any]], location_id:int, include_self:bool=True)->list[int]:
    children:dict[int|None,list[int]]={}
    for row in rows:
        children.setdefault(row.get('parent_id'),[]).append(row['id'])
    result=[]
    stack=[location_id]
    while stack:
        current=stack.pop()
        if current!=location_id or include_self:
            result.append(current)
        stack.extend(children.get(current,[]))
    return result


def location_has_employee_products(location_id:int, employee_id:int, include_descendants:bool=True)->bool:
    rows=list_locations(active_only=True)
    ids=_descendant_ids_from_rows(rows,location_id,True) if include_descendants else [location_id]
    if not ids: return False
    marks=','.join('?' for _ in ids)
    with get_connection() as c:
        if employee_has_global_count_access(employee_id):
            r=c.execute(f'''SELECT 1 FROM product_locations pl JOIN products p ON p.id=pl.product_id
                WHERE pl.active=1 AND p.active=1 AND pl.location_id IN ({marks}) LIMIT 1''',ids).fetchone()
        else:
            r=c.execute(f'''SELECT 1 FROM product_locations pl JOIN products p ON p.id=pl.product_id
                WHERE pl.active=1 AND p.active=1 AND pl.assigned_employee_id=? AND pl.location_id IN ({marks}) LIMIT 1''',[employee_id,*ids]).fetchone()
    return bool(r)


def list_locations_for_employee(employee_id:int) -> list[dict[str,Any]]:
    # Return the complete active hierarchy annotated with availability so the UI
    # can navigate root -> child -> leaf without flattening the tree.
    rows=list_locations(active_only=True)
    for row in rows:
        row['employee_has_products']=location_has_employee_products(row['id'],employee_id,True)
        row['employee_direct_products']=location_has_employee_products(row['id'],employee_id,False)
    return rows

def list_locations_for_session(session_id:int) -> list[dict[str,Any]]:
    """Return the active hierarchy annotated from products recorded in one session."""
    rows=list_locations(active_only=True)
    by_parent={}
    for row in rows:
        by_parent.setdefault(row.get('parent_id'),[]).append(row['id'])
    with get_connection() as c:
        found=c.execute("SELECT DISTINCT pl.location_id FROM inventory_counts ic JOIN product_locations pl ON pl.id=ic.product_location_id WHERE ic.session_id=? AND ic.product_location_id IS NOT NULL",(session_id,)).fetchall()
        direct={r['location_id'] for r in found}
    def branch_has(location_id:int)->bool:
        stack=[location_id]
        while stack:
            cur=stack.pop()
            if cur in direct: return True
            stack.extend(by_parent.get(cur,[]))
        return False
    for row in rows:
        row['employee_has_products']=branch_has(row['id'])
        row['employee_direct_products']=row['id'] in direct
    return rows


def session_has_location_items(session_id:int)->bool:
    with get_connection() as c:
        r=c.execute('SELECT 1 FROM inventory_counts WHERE session_id=? AND product_location_id IS NOT NULL LIMIT 1',(session_id,)).fetchone()
    return bool(r)


def _validate_parent(location_id:int|None,parent_id:int|None)->None:
    if location_id is not None and parent_id==location_id:
        raise ValueError('Um setor não pode ser pai dele mesmo.')
    if location_id is None or parent_id is None: return
    rows=list_locations(active_only=False)
    descendants=set(_descendant_ids_from_rows(rows,location_id,include_self=False))
    if parent_id in descendants:
        raise ValueError('Um setor não pode ser movido para dentro de um de seus próprios subsetores.')


def _compose_location_code(parent_id:int|None, sublevel:str)->str:
    sublevel=str(sublevel or '').strip().strip('.')
    if not sublevel: raise ValueError('Informe o número/índice do setor.')
    if '.' in sublevel:
        raise ValueError('Informe apenas o próximo nível, sem pontos.')
    if parent_id is None:
        return sublevel
    parent=get_location(parent_id)
    if not parent: raise ValueError('Setor pai inválido.')
    return f"{parent['code']}.{sublevel}"


def create_location_from_parent(parent_id:int|None, sublevel:str, name:str)->int:
    return create_location(_compose_location_code(parent_id,sublevel),name,parent_id)


def update_location_from_parent(location_id:int,parent_id:int|None,sublevel:str,name:str,active:bool=True)->None:
    _validate_parent(location_id,parent_id)
    update_location(location_id,_compose_location_code(parent_id,sublevel),name,parent_id,active)


def create_location(code:str,name:str,parent_id:int|None=None) -> int:
    code=code.strip().rstrip('.'); name=name.strip()
    if not code or not name: raise ValueError('Código e nome são obrigatórios.')
    _validate_parent(None,parent_id)
    with get_connection() as c:
        cur=c.execute('INSERT INTO storage_locations(code,name,parent_id,display_order,active) VALUES (?,?,?,?,1)',(code,name,parent_id,0))
        return int(cur.lastrowid)


def update_location(location_id:int, code:str,name:str,parent_id:int|None,active:bool=True)->None:
    code=code.strip().rstrip('.'); name=name.strip()
    if not code or not name: raise ValueError('Código e nome são obrigatórios.')
    _validate_parent(location_id,parent_id)
    with get_connection() as c:
        current=c.execute('SELECT code FROM storage_locations WHERE id=?',(location_id,)).fetchone()
        if not current: raise ValueError('Setor não encontrado.')
        old_code=str(current['code'])
        if old_code != code:
            descendants=c.execute('SELECT id,code FROM storage_locations WHERE code LIKE ? ORDER BY LENGTH(code) ASC',(old_code+'.%',)).fetchall()
            # Change descendants first to temporary values to avoid transient UNIQUE conflicts.
            for row in descendants:
                c.execute('UPDATE storage_locations SET code=? WHERE id=?',(f"__moving__{row['id']}__{row['code']}",row['id']))
            c.execute('UPDATE storage_locations SET code=?,name=?,parent_id=?,active=? WHERE id=?',(code,name,parent_id,1 if active else 0,location_id))
            for row in descendants:
                suffix=str(row['code'])[len(old_code):]
                c.execute('UPDATE storage_locations SET code=? WHERE id=?',(code+suffix,row['id']))
        else:
            c.execute('UPDATE storage_locations SET name=?,parent_id=?,active=? WHERE id=?',(name,parent_id,1 if active else 0,location_id))


def deactivate_location(location_id:int)->None:
    with get_connection() as c:
        children=c.execute('SELECT COUNT(*) FROM storage_locations WHERE parent_id=? AND active=1',(location_id,)).fetchone()[0]
        if children:
            raise ValueError('Remova ou mova os subsetores antes de remover este setor.')
        # Removing a sector must not delete products from the master catalog.
        # Its active product links are simply disabled, leaving those products
        # available to be associated with another sector later.
        c.execute('UPDATE product_locations SET active=0,updated_at=CURRENT_TIMESTAMP WHERE location_id=? AND active=1',(location_id,))
        c.execute('UPDATE storage_locations SET active=0 WHERE id=?',(location_id,))


def list_product_locations(search:str='') -> list[dict[str,Any]]:
    params=[]; where='pl.active=1'
    if search.strip():
        where += ' AND (p.name LIKE ? OR p.external_code LIKE ? OR l.code LIKE ? OR l.name LIKE ?)'
        s=f"%{search.strip()}%"; params=[s,s,s,s]
    with get_connection() as c:
        rows=c.execute(f'''SELECT pl.id product_location_id,pl.product_id,pl.location_id,pl.assigned_employee_id,
            pl.expected_min,pl.expected_max,pl.count_order, p.external_code,p.name,p.unit,p.category,
            l.code location_code,l.name location_name,e.name counter_name
            FROM product_locations pl JOIN products p ON p.id=pl.product_id
            JOIN storage_locations l ON l.id=pl.location_id
            LEFT JOIN employees e ON e.id=pl.assigned_employee_id
            WHERE {where}''',params).fetchall()
    data=[dict(r) for r in rows]
    return sorted(data,key=lambda r:(_location_sort_key({'code':r['location_code']}),_natural_part(r['name']),r['count_order'] or 0))


def assign_product_to_location(product_id:int, location_id:int, employee_id:int|None, expected_min:float|None=None, expected_max:float|None=None)->int:
    with get_connection() as c:
        order=c.execute('SELECT COALESCE(MAX(count_order),0)+1 FROM product_locations WHERE location_id=?',(location_id,)).fetchone()[0]
        existing=c.execute('SELECT id FROM product_locations WHERE product_id=? AND location_id=?',(product_id,location_id)).fetchone()
        if existing:
            plid=int(existing[0]); c.execute('UPDATE product_locations SET assigned_employee_id=?,expected_min=?,expected_max=?,active=1,updated_at=CURRENT_TIMESTAMP WHERE id=?',(employee_id,expected_min,expected_max,plid))
        else:
            cur=c.execute('INSERT INTO product_locations(product_id,location_id,assigned_employee_id,expected_min,expected_max,count_order,active) VALUES (?,?,?,?,?,?,1)',(product_id,location_id,employee_id,expected_min,expected_max,order)); plid=int(cur.lastrowid)
        _record_assignment(c,plid,employee_id)
        return plid


def _record_assignment(c,plid,eid):
    current=c.execute('SELECT employee_id FROM product_location_assignment_history WHERE product_location_id=? AND valid_to IS NULL ORDER BY id DESC LIMIT 1',(plid,)).fetchone()
    if current and current[0]==eid: return
    c.execute('UPDATE product_location_assignment_history SET valid_to=CURRENT_TIMESTAMP WHERE product_location_id=? AND valid_to IS NULL',(plid,))
    c.execute('INSERT INTO product_location_assignment_history(product_location_id,employee_id) VALUES (?,?)',(plid,eid))


def update_product_location(plid:int, location_id:int, employee_id:int|None, expected_min:float|None, expected_max:float|None)->None:
    with get_connection() as c:
        row=c.execute('SELECT product_id,assigned_employee_id FROM product_locations WHERE id=?',(plid,)).fetchone()
        if not row: raise ValueError('Vínculo não encontrado.')
        c.execute('UPDATE product_locations SET location_id=?,assigned_employee_id=?,expected_min=?,expected_max=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(location_id,employee_id,expected_min,expected_max,plid))
        if row['assigned_employee_id']!=employee_id: _record_assignment(c,plid,employee_id)


def remove_product_location(plid:int)->None:
    with get_connection() as c: c.execute('UPDATE product_locations SET active=0,updated_at=CURRENT_TIMESTAMP WHERE id=?',(plid,))


def list_count_items_for_location(employee_id:int, location_id:int)->list[dict[str,Any]]:
    with get_connection() as c:
        if employee_has_global_count_access(employee_id):
            rows=c.execute('''SELECT pl.id product_id, pl.id product_location_id, pl.product_id master_product_id,
                NULL count_id, NULL session_id, NULL quantity, 'not_counted' status, NULL notes, NULL counted_at,
                p.external_code,p.name,p.category,p.unit,pl.count_order,pl.expected_min,pl.expected_max,
                l.code location_code,l.name location_name
                FROM product_locations pl JOIN products p ON p.id=pl.product_id
                JOIN storage_locations l ON l.id=pl.location_id
                WHERE pl.location_id=? AND pl.active=1 AND p.active=1
                ORDER BY pl.count_order,p.name''',(location_id,)).fetchall()
        else:
            rows=c.execute('''SELECT pl.id product_id, pl.id product_location_id, pl.product_id master_product_id,
                NULL count_id, NULL session_id, NULL quantity, 'not_counted' status, NULL notes, NULL counted_at,
                p.external_code,p.name,p.category,p.unit,pl.count_order,pl.expected_min,pl.expected_max,
                l.code location_code,l.name location_name
                FROM product_locations pl JOIN products p ON p.id=pl.product_id
                JOIN storage_locations l ON l.id=pl.location_id
                WHERE pl.location_id=? AND pl.assigned_employee_id=? AND pl.active=1 AND p.active=1
                ORDER BY pl.count_order,p.name''',(location_id,employee_id)).fetchall()
    return [dict(r) for r in rows]


def create_session(employee_id:int, location_id:int, count_type:str)->int:
    # This function is deliberately called only by ensure_session_for_count(),
    # which runs on the first effective count action.
    with get_connection() as c:
        loc=c.execute('SELECT code FROM storage_locations WHERE id=?',(location_id,)).fetchone()
        if not loc: raise ValueError('Setor inválido.')
        cur=c.execute("INSERT INTO inventory_sessions(employee_id,storage_area,location_id,count_type,status,started_at) VALUES (?,?,?,?, 'in_progress', CURRENT_TIMESTAMP)",(employee_id,loc['code'],location_id,count_type))
        sid=int(cur.lastrowid)
        if employee_has_global_count_access(employee_id):
            rows=c.execute('''SELECT pl.id product_location_id,pl.product_id FROM product_locations pl
                JOIN products p ON p.id=pl.product_id
                WHERE pl.location_id=? AND pl.active=1 AND p.active=1 ORDER BY pl.count_order''',(location_id,)).fetchall()
            payload=[(sid,r['product_id'],r['product_location_id'],employee_id) for r in rows]
        else:
            rows=c.execute('''SELECT pl.id product_location_id,pl.product_id,pl.assigned_employee_id FROM product_locations pl
                JOIN products p ON p.id=pl.product_id
                WHERE pl.location_id=? AND pl.assigned_employee_id=? AND pl.active=1 AND p.active=1 ORDER BY pl.count_order''',(location_id,employee_id)).fetchall()
            payload=[(sid,r['product_id'],r['product_location_id'],r['assigned_employee_id']) for r in rows]
        c.executemany('INSERT INTO inventory_counts(session_id,product_id,product_location_id,assigned_employee_id) VALUES (?,?,?,?)',payload)
        return sid


def ensure_session_for_count(session:dict)->int:
    existing=session.get('id')
    if existing: return int(existing)
    sid=create_session(int(session['employee_id']),int(session['location_id']),str(session['count_type']))
    return sid


def get_session(session_id:int)->dict[str,Any]|None:
    with get_connection() as c:
        r=c.execute('''SELECT s.*,e.name employee_name,l.code location_code,l.name location_name FROM inventory_sessions s
            JOIN employees e ON e.id=s.employee_id LEFT JOIN storage_locations l ON l.id=s.location_id WHERE s.id=?''',(session_id,)).fetchone()
    return dict(r) if r else None


def get_session_items(session_id:int, location_id:int|None=None)->list[dict[str,Any]]:
    params=[session_id]
    location_filter=''
    if location_id is not None:
        location_filter=' AND pl.location_id=?'
        params.append(location_id)
    with get_connection() as c:
        rows=c.execute(f'''SELECT c.id count_id,c.session_id,
            COALESCE(c.product_location_id,c.product_id) product_id,
            c.product_id master_product_id,c.product_location_id,c.quantity,c.status,c.notes,c.counted_at,
            p.external_code,p.name,p.category,p.unit,
            COALESCE(pl.count_order,p.count_order) count_order,
            COALESCE(pl.expected_min,p.expected_min) expected_min,
            COALESCE(pl.expected_max,p.expected_max) expected_max,
            l.code location_code,l.name location_name
            FROM inventory_counts c JOIN products p ON p.id=c.product_id
            LEFT JOIN product_locations pl ON pl.id=c.product_location_id
            LEFT JOIN storage_locations l ON l.id=pl.location_id
            WHERE c.session_id=?{location_filter}
            ORDER BY COALESCE(pl.count_order,p.count_order),p.name''',params).fetchall()
    return [dict(r) for r in rows]


def get_session_location_progress_map(session_id:int)->dict[int,dict[str,Any]]:
    """Aggregate a multi-sector historical session upward through the hierarchy."""
    locations=list_locations(active_only=True)
    by_id={r['id']:r for r in locations}
    direct={}
    with get_connection() as c:
        rows=c.execute("SELECT pl.location_id,ic.status FROM inventory_counts ic JOIN product_locations pl ON pl.id=ic.product_location_id WHERE ic.session_id=? AND ic.product_location_id IS NOT NULL",(session_id,)).fetchall()
    for r in rows:
        direct.setdefault(r['location_id'],[]).append(r['status'])
    aggregate={}
    for location_id,statuses in direct.items():
        cur=location_id
        while cur is not None and cur in by_id:
            aggregate.setdefault(cur,[]).extend(statuses)
            cur=by_id[cur].get('parent_id')
    result={}
    done={'counted','confirmed_zero','flagged'}
    for location_id,statuses in aggregate.items():
        total=len(statuses); counted=sum(st in done for st in statuses); flagged=sum(st=='flagged' for st in statuses)
        if counted==0: state='not_started'
        elif counted<total: state='in_progress'
        elif flagged: state='completed_attention'
        else: state='completed_clean'
        result[location_id]={'state':state,'total':total,'counted':counted,'flagged':flagged}
    return result


def get_previous_quantity(product_location_id:int,before_session_id:int|None)->float|None:
    with get_connection() as c:
        if before_session_id:
            r=c.execute('''SELECT c.quantity FROM inventory_counts c JOIN inventory_sessions s ON s.id=c.session_id
              WHERE c.product_location_id=? AND c.session_id<>? AND c.status IN ('counted','confirmed_zero','flagged')
              ORDER BY COALESCE(s.completed_at,s.started_at) DESC LIMIT 1''',(product_location_id,before_session_id)).fetchone()
        else:
            r=c.execute('''SELECT c.quantity FROM inventory_counts c JOIN inventory_sessions s ON s.id=c.session_id
              WHERE c.product_location_id=? AND c.status IN ('counted','confirmed_zero','flagged')
              ORDER BY COALESCE(s.completed_at,s.started_at) DESC LIMIT 1''',(product_location_id,)).fetchone()
    return float(r[0]) if r and r[0] is not None else None


def save_count(session_id:int, product_location_id:int, employee_id:int, quantity:float,status:str,notes:str='',reason:str='')->None:
    with get_connection() as c:
        c.execute('''UPDATE inventory_counts SET quantity=?,status=?,notes=?,counted_at=COALESCE(counted_at,CURRENT_TIMESTAMP),
          updated_at=CURRENT_TIMESTAMP,counted_by_employee_id=? WHERE session_id=? AND product_location_id=?''',(quantity,status,notes,employee_id,session_id,product_location_id))


def complete_session(session_id:int)->None:
    with get_connection() as c: c.execute("UPDATE inventory_sessions SET status='completed',completed_at=CURRENT_TIMESTAMP WHERE id=?",(session_id,))


def update_session_metadata(session_id:int, employee_id:int, count_type:str)->None:
    """Update the editable session metadata without recreating the count.

    The count rows remain attached to the same session.  The employee snapshot
    stored on the count rows is updated as well so subsequent edits are
    attributed consistently to the newly selected counter.
    """
    count_type=str(count_type or '').strip()
    if not count_type:
        raise ValueError('Informe o tipo de contagem.')
    with get_connection() as c:
        if not c.execute('SELECT 1 FROM employees WHERE id=? AND active=1',(employee_id,)).fetchone():
            raise ValueError('Contador inválido ou inativo.')
        if not c.execute('SELECT 1 FROM inventory_sessions WHERE id=?',(session_id,)).fetchone():
            raise ValueError('Contagem não encontrada.')
        c.execute('UPDATE inventory_sessions SET employee_id=?,count_type=? WHERE id=?',(employee_id,count_type,session_id))
        c.execute('UPDATE inventory_counts SET assigned_employee_id=? WHERE session_id=?',(employee_id,session_id))


def delete_session(session_id:int)->bool:
    with get_connection() as c:
        if not c.execute('SELECT 1 FROM inventory_sessions WHERE id=?',(session_id,)).fetchone(): return False
        c.execute('DELETE FROM inventory_counts WHERE session_id=?',(session_id,)); c.execute('DELETE FROM inventory_sessions WHERE id=?',(session_id,)); return True


def _ensure_history_visibility_column(c)->None:
    """Add non-destructive UI visibility flags to older databases on first use."""
    columns={row['name'] for row in c.execute('PRAGMA table_info(inventory_sessions)').fetchall()}
    if 'history_hidden' not in columns:
        c.execute('ALTER TABLE inventory_sessions ADD COLUMN history_hidden INTEGER NOT NULL DEFAULT 0')
    if 'dashboard_hidden' not in columns:
        c.execute('ALTER TABLE inventory_sessions ADD COLUMN dashboard_hidden INTEGER NOT NULL DEFAULT 0')


def hide_session_from_history(session_id:int)->bool:
    """Hide a session from the History selector without deleting its data."""
    with get_connection() as c:
        _ensure_history_visibility_column(c)
        if not c.execute('SELECT 1 FROM inventory_sessions WHERE id=?',(session_id,)).fetchone():
            return False
        c.execute('UPDATE inventory_sessions SET history_hidden=1 WHERE id=?',(session_id,))
        return True


def hide_session_from_dashboard(session_id:int)->bool:
    """Remove a recent-count shortcut from Home while preserving History and data."""
    with get_connection() as c:
        _ensure_history_visibility_column(c)
        if not c.execute('SELECT 1 FROM inventory_sessions WHERE id=?',(session_id,)).fetchone():
            return False
        c.execute('UPDATE inventory_sessions SET dashboard_hidden=1 WHERE id=?',(session_id,))
        return True


def list_sessions(limit:int=50, real_only:bool=False, include_hidden:bool=False, for_dashboard:bool=False)->list[dict[str,Any]]:
    having="HAVING SUM(CASE WHEN ic.status<>'not_counted' THEN 1 ELSE 0 END) > 0" if real_only else ''
    with get_connection() as c:
        _ensure_history_visibility_column(c)
        clauses=[]
        if not include_hidden:
            clauses.append('COALESCE(s.history_hidden,0)=0')
        if for_dashboard:
            clauses.append('COALESCE(s.dashboard_hidden,0)=0')
        visibility_clause=('WHERE '+' AND '.join(clauses)) if clauses else ''
        rows=c.execute(f'''SELECT s.*,e.name employee_name,l.name location_name,l.code location_code,
         SUM(CASE WHEN ic.status<>'not_counted' THEN 1 ELSE 0 END) counted,COUNT(ic.id) total
         FROM inventory_sessions s JOIN employees e ON e.id=s.employee_id
         LEFT JOIN storage_locations l ON l.id=s.location_id LEFT JOIN inventory_counts ic ON ic.session_id=s.id
         {visibility_clause}
         GROUP BY s.id {having} ORDER BY s.started_at DESC LIMIT ?''',(limit,)).fetchall()
    return [dict(r) for r in rows]


def get_location_progress_map(employee_id:int, count_type:str, since:str|None=None, resume_open:bool=True, exclude_session_ids:list[int]|None=None)->dict[int,dict[str,Any]]:
    """Aggregate current-run count state upward through the sector tree.

    Old completed sessions are ignored when ``since`` is supplied. Existing
    in-progress sessions are still included so unfinished work can be resumed.
    """
    locations=list_locations(active_only=True)
    descendants={r['id']:_descendant_ids_from_rows(locations,r['id'],True) for r in locations}

    with get_connection() as c:
        params=[employee_id,count_type]
        time_clause=''
        exclude_clause=''
        if since:
            time_clause=(" AND (s.status='in_progress' OR s.started_at>=?)" if resume_open else " AND s.started_at>=?")
            params.append(since)
        excluded=[int(x) for x in (exclude_session_ids or [])]
        if excluded:
            exclude_clause=' AND s.id NOT IN ('+','.join('?' for _ in excluded)+')'
            params.extend(excluded)
        sessions=c.execute(f"""SELECT s.id,s.location_id,s.status,s.started_at
            FROM inventory_sessions s
            WHERE s.employee_id=? AND s.count_type=?
            AND EXISTS (SELECT 1 FROM inventory_counts ic WHERE ic.session_id=s.id AND ic.status<>'not_counted')
            {time_clause} {exclude_clause}
            ORDER BY s.started_at DESC,s.id DESC""",params).fetchall()

        latest_by_location={}
        for row in sessions:
            lid=row['location_id']
            if lid is not None and lid not in latest_by_location:
                latest_by_location[lid]=row['id']

        direct={}
        for lid,sid in latest_by_location.items():
            r=c.execute("""SELECT COUNT(*) total,
                SUM(CASE WHEN status<>'not_counted' THEN 1 ELSE 0 END) counted,
                SUM(CASE WHEN status='flagged' THEN 1 ELSE 0 END) flagged
                FROM inventory_counts WHERE session_id=?""",(sid,)).fetchone()
            direct[lid]={'total':int(r['total'] or 0),'counted':int(r['counted'] or 0),'flagged':int(r['flagged'] or 0)}

        product_totals={}
        if employee_has_global_count_access(employee_id):
            rows=c.execute("""SELECT pl.location_id,COUNT(*) total
                FROM product_locations pl JOIN products p ON p.id=pl.product_id
                WHERE pl.active=1 AND p.active=1
                GROUP BY pl.location_id""").fetchall()
        else:
            rows=c.execute("""SELECT pl.location_id,COUNT(*) total
                FROM product_locations pl JOIN products p ON p.id=pl.product_id
                WHERE pl.active=1 AND p.active=1 AND pl.assigned_employee_id=?
                GROUP BY pl.location_id""",(employee_id,)).fetchall()
        for r in rows:
            product_totals[r['location_id']]=int(r['total'] or 0)

    result={}
    for loc in locations:
        ids=descendants[loc['id']]
        total=sum(product_totals.get(i,0) for i in ids)
        counted=sum(direct.get(i,{}).get('counted',0) for i in ids)
        flagged=sum(direct.get(i,{}).get('flagged',0) for i in ids)
        if total<=0:
            state='disabled'
        elif counted<=0:
            state='not_started'
        elif counted<total:
            state='in_progress'
        elif flagged>0:
            state='completed_attention'
        else:
            state='completed_clean'
        result[loc['id']]={'state':state,'total':total,'counted':counted,'flagged':flagged}
    return result

def build_manager_snapshot(*args,**kwargs):
    return {'note':'Copilot compatibility placeholder for UI v4.'}


def list_areas():
    return [location_label(x) for x in list_locations()]


def add_product(name,category,area,unit,expected_max,expected_min=None,external_code=''):
    return create_product(name,external_code,unit,category)


def seed_demo_data():
    return None


def list_active_sessions(employee_id:int, count_type:str|None=None)->list[dict[str,Any]]:
    params=[employee_id]
    type_clause=''
    if count_type:
        type_clause=' AND s.count_type=?'
        params.append(count_type)
    with get_connection() as c:
        rows=c.execute(f'''SELECT s.id FROM inventory_sessions s
            WHERE s.employee_id=? AND s.status='in_progress' {type_clause}
            AND EXISTS (SELECT 1 FROM inventory_counts ic WHERE ic.session_id=s.id AND ic.status<>'not_counted')
            ORDER BY s.started_at DESC,s.id DESC''',params).fetchall()
    return [get_session(int(r['id'])) for r in rows if get_session(int(r['id']))]


def find_active_session(employee_id:int, location_id:int, count_type:str, since:str|None=None, exclude_session_ids:list[int]|None=None)->dict[str,Any]|None:
    params=[employee_id,location_id,count_type]
    since_clause=''
    exclude_clause=''
    if since:
        since_clause=' AND s.started_at>=?'
        params.append(since)
    excluded=[int(x) for x in (exclude_session_ids or [])]
    if excluded:
        exclude_clause=' AND s.id NOT IN ('+','.join('?' for _ in excluded)+')'
        params.extend(excluded)
    with get_connection() as c:
        row=c.execute(f'''SELECT s.id FROM inventory_sessions s
            WHERE s.employee_id=? AND s.location_id=? AND s.count_type=? AND s.status='in_progress'
            {since_clause} {exclude_clause}
            AND EXISTS (SELECT 1 FROM inventory_counts ic WHERE ic.session_id=s.id AND ic.status<>'not_counted')
            ORDER BY s.started_at DESC LIMIT 1''',params).fetchone()
    return get_session(int(row['id'])) if row else None