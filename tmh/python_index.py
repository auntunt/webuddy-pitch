"""Bounded Python AST facts. Never import or execute the project being inspected.

HTTP handler entries describe an entire dispatcher method, not an inferred URL.
Calls require one lexical/import target; dynamic dispatch and SQL remain unknown.
"""
from __future__ import annotations

import ast
import builtins
from pathlib import PurePosixPath


FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)
SCOPES = FUNCTIONS + (ast.ClassDef, ast.Lambda)
SQL_METHODS = {'execute', 'executemany', 'executescript'}
HTTP_METHODS = {'GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS', 'TRACE', 'CONNECT'}


def _own(nodes):
    """Walk a body's statements without treating nested declarations as executed calls."""
    for node in nodes:
        yield node
        if not isinstance(node, SCOPES):
            yield from _own(ast.iter_child_nodes(node))


def _names(target):
    return [n.id for n in ast.walk(target) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)]


def _module(rp):
    name = str(PurePosixPath(rp).with_suffix('')).replace('/', '.')
    return name.removesuffix('.__init__') if name.endswith('.__init__') else name


def parse(rp: str, text: str | None) -> dict:
    """JSON-serializable classes/endpoints/diagnostics for one repository-relative file."""
    result = {'classes': [], 'endpoints': [], 'diagnostics': []}
    try:
        if text is None:
            raise ValueError('源文件不可读取或超出读取限制')
        tree = ast.parse(text, filename=rp)
    except (SyntaxError, ValueError, RecursionError) as error:
        result['diagnostics'].append({'status': 'unknown', 'kind': 'parse', 'file': rp,
                                      'line': getattr(error, 'lineno', 0) or 0, 'message': str(error)})
        return result
    module = _module(rp)
    owners, scopes, methods = {}, {}, []

    def owner(qual, kind, node):
        key = 'py:' + rp + ('::' + qual if qual else '')
        if key not in owners:
            owners[key] = {'name': key, 'fqn': key, 'kind': kind, 'file': rp,
                           'line': getattr(node, 'lineno', 1), 'bases': [], 'head': '', 'annos': '',
                           'fields': {}, 'methods': {}, 'lang': 'python', 'comment': ast.get_docstring(node) or '',
                           'python_module': module, 'python_qualname': qual}
        return owners[key]

    def collect(node, qual, parent, kind):
        scope = {'node': node, 'qual': qual, 'parent': parent, 'kind': kind, 'symbols': {}, 'self': None}
        scopes[id(node)] = scope
        own = owner(qual, kind, node)
        def bind(name, value):
            scope['symbols'].setdefault(name, []).append(value)
        if isinstance(node, FUNCTIONS):
            args = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
            args += [a for a in (node.args.vararg, node.args.kwarg) if a]
            for arg in args:
                bind(arg.arg, ('unknown', '参数'))
            if parent and parent['kind'] == 'class' and node.args.args:
                scope['self'] = node.args.args[0].arg
        for child in _own(node.body):
            if isinstance(child, FUNCTIONS):
                childqual = (qual + '.' if qual else '') + child.name
                key = own['name'] + '.' + child.name
                bind(child.name, ('function', key))
                source = ast.get_source_segment(text, child) or ''
                params = {a.arg: '' for a in [*child.args.posonlyargs, *child.args.args, *child.args.kwonlyargs]}
                method = {'name': child.name, 'class': own['name'], 'file': rp, 'line': child.lineno,
                          'end_line': child.end_lineno, 'body_line': child.lineno, 'body': source, 'masked': '',
                          'params': params, 'annos': '', 'comment': ast.get_docstring(child) or '',
                          'python_calls': [], 'python_sql': [], 'python_unresolved': [], 'lang': 'python',
                          'python_export': module + '.' + childqual}
                method['python_callable'] = not child.decorator_list and not (
                    isinstance(node, ast.ClassDef) and node.decorator_list)
                own['methods'].setdefault(child.name, []).append(method)
                childscope = collect(child, childqual, scope, 'scope')
                methods.append((method, childscope))
            elif isinstance(child, ast.ClassDef):
                childqual = (qual + '.' if qual else '') + child.name
                childscope = collect(child, childqual, scope, 'class')
                bind(child.name, ('class', owner(childqual, 'class', child)['name']))
                childscope['bases'] = child.bases
            elif isinstance(child, ast.Import):
                for alias in child.names:
                    bind(alias.asname or alias.name.split('.')[0], ('import', alias.name if alias.asname else alias.name.split('.')[0]))
            elif isinstance(child, ast.ImportFrom):
                prefix = child.module or ''
                if child.level:
                    package = module.split('.') if rp.endswith('/__init__.py') else module.split('.')[:-1]
                    package = package[:max(0, len(package) - child.level + 1)]
                    prefix = '.'.join(package + ([prefix] if prefix else []))
                for alias in child.names:
                    bind(alias.asname or alias.name, ('import', (prefix + '.' if prefix else '') + alias.name))
            elif isinstance(child, ast.Name) and isinstance(child.ctx, (ast.Store, ast.Del)):
                bind(child.id, ('unknown', '局部赋值/删除'))
        return scope

    root = collect(tree, '', None, 'module')

    def lookup(scope, name):
        current = scope
        while current:
            values = current['symbols'].get(name)
            if values:
                return values[0] if len(values) == 1 else ('unknown', '同名绑定不唯一')
            current = current['parent']
            # A class namespace is not a lexical enclosing scope of a method.
            if current and current['kind'] == 'class':
                current = current['parent']
        return ('builtin', name) if name in vars(builtins) else ('unknown', '目标不在可证明的词法作用域')

    replaced = {}

    def target(scope, expr):
        if isinstance(expr, ast.Name):
            return lookup(scope, expr.id)
        if isinstance(expr, ast.Attribute):
            if isinstance(expr.value, ast.Name) and expr.value.id == scope.get('self'):
                # Rebinding the receiver or assigning that method name is dynamic.
                if len(scope['symbols'].get(expr.value.id, [])) != 1:
                    return ('unknown', '实例接收者被重新绑定')
                cls = scope['parent']
                key = owners['py:' + rp + '::' + cls['qual']]['name']
                if expr.attr in replaced.get(key, set()) or '*' in replaced.get(key, set()):
                    return ('unknown', '实例或类的方法被动态替换')
                if any(isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Store) and
                       isinstance(n.value, ast.Name) and n.value.id == expr.value.id and n.attr == expr.attr
                       for n in _own(scope['node'].body)):
                    return ('unknown', '实例方法被动态赋值')
                values = cls['symbols'].get(expr.attr, [])
                return values[0] if len(values) == 1 and values[0][0] == 'function' else ('unknown', '实例方法未在此类中唯一声明')
            kind, value = target(scope, expr.value)
            if kind == 'import':
                return ('import', value + '.' + expr.attr)
            if kind == 'class':
                members = owners.get(value, {}).get('methods', {}).get(expr.attr, [])
                if len(members) == 1 and expr.attr not in replaced.get(value, set()) and '*' not in replaced.get(value, set()):
                    return ('function', value + '.' + expr.attr)
            return ('unknown', '动态属性或外部接收者')
        return ('unknown', '动态调用表达式')

    for scope in scopes.values():
        for n in _own(scope['node'].body):
            if isinstance(n, ast.Attribute) and isinstance(n.ctx, (ast.Store, ast.Del)):
                if isinstance(n.value, ast.Name) and n.value.id == scope.get('self'):
                    key = 'py:' + rp + '::' + scope['parent']['qual']
                    replaced.setdefault(key, set()).add(n.attr)
                else:
                    kind, key = target(scope, n.value)
                    if kind == 'class':
                        replaced.setdefault(key, set()).add(n.attr)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'setattr' and n.args:
                if isinstance(n.args[0], ast.Name) and n.args[0].id == scope.get('self'):
                    replaced.setdefault('py:' + rp + '::' + scope['parent']['qual'], set()).add('*')
                else:
                    kind, key = target(scope, n.args[0])
                    if kind == 'class':
                        replaced.setdefault(key, set()).add('*')
    registrations = {}
    for scope in scopes.values():
        for call in (n for n in _own(scope['node'].body) if isinstance(n, ast.Call)):
            if target(scope, call.func) not in [('import', 'http.server.HTTPServer'), ('import', 'http.server.ThreadingHTTPServer')]:
                continue
            handler = call.args[1] if len(call.args) > 1 else next((k.value for k in call.keywords if k.arg == 'RequestHandlerClass'), None)
            kind, value = target(scope, handler)
            if kind == 'class':
                registrations.setdefault(value, []).append({'file': rp, 'line': call.lineno,
                                                            'call': ast.get_source_segment(text, call.func)})
    for method, scope in methods:
        nodes = list(_own(scope['node'].body))
        dbdefs = {}
        # Only direct sqlite3.connect (including explicit import aliases) establishes a DB receiver.
        def connection(expr):
            return isinstance(expr, ast.Call) and target(scope, expr.func) == ('import', 'sqlite3.connect')
        for n in nodes:
            if isinstance(n, ast.With):
                for item in n.items:
                    if connection(item.context_expr) and isinstance(item.optional_vars, ast.Name):
                        name = item.optional_vars.id
                        dbdefs[name] = dbdefs.get(name, 0) + 1
            elif isinstance(n, ast.Assign) and connection(n.value):
                for t in n.targets:
                    for name in _names(t):
                        dbdefs[name] = dbdefs.get(name, 0) + 1
        # Ambiguous aliases must not be treated as known SQLite receivers.
        dbnames = {name for name, count in dbdefs.items() if len(scope['symbols'].get(name, [])) == count}
        for n in nodes:
            if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Attribute):
                fn = n.value.func
                if fn.attr == 'cursor' and isinstance(fn.value, ast.Name) and fn.value.id in dbnames:
                    for t in n.targets:
                        dbnames.update(name for name in _names(t) if len(scope['symbols'].get(name, [])) == 1)
        for call in (n for n in nodes if isinstance(n, ast.Call)):
            expression = ast.get_source_segment(text, call.func) or type(call.func).__name__
            record = {'call': expression, 'file': rp, 'line': call.lineno}
            is_sql = (isinstance(call.func, ast.Attribute) and call.func.attr in SQL_METHODS and
                      isinstance(call.func.value, ast.Name) and call.func.value.id in dbnames)
            if is_sql:
                literal = call.args[0] if call.args else None
                if isinstance(literal, ast.Constant) and isinstance(literal.value, str):
                    method['python_sql'].append({'sql': literal.value, 'file': rp, 'line': call.lineno})
                else:
                    method['python_unresolved'].append(dict(record, why='动态 SQL 未解析；不能据此断言没有数据影响'))
                continue
            kind, value = target(scope, call.func)
            if kind in ('function', 'import'):
                method['python_calls'].append(dict(record, **({'target': value} if kind == 'function' else {'import_target': value})))
            elif kind not in ('builtin', 'class'):
                method['python_unresolved'].append(dict(record, why='未解析调用：' + value))
        # BaseHTTPRequestHandler dispatch is a method-wide relation, never a URL claim.
        cls = scope['parent']
        if cls and cls['kind'] == 'class' and method['name'].startswith('do_') and method['name'][3:] in HTTP_METHODS:
            known_base = any(target(cls['parent'], b) == ('import', 'http.server.BaseHTTPRequestHandler') for b in cls.get('bases', []))
            if known_base and method['class'] in registrations and (not method['python_callable'] or
                    method['name'] in replaced.get(method['class'], set()) or '*' in replaced.get(method['class'], set())):
                result['diagnostics'].append({'status': 'unknown', 'kind': 'entry', 'file': rp, 'line': method['line'],
                    'message': '注册类或其 HTTP 方法被装饰或动态替换，不能证明原方法是请求入口'})
            elif known_base and method['class'] in registrations and len(owners[method['class']]['methods'][method['name']]) == 1:
                key = method['class'] + '.' + method['name']
                owners[method['class']]['layer'] = 'entry'
                result['endpoints'].append({'method': method['name'][3:], 'path': '<dispatcher:' + key + '>',
                    'handler': key, 'stack': 'python-http.server', 'scope': 'dispatcher', 'url': None,
                    'file': rp, 'line': method['line'], 'end_line': method['end_line'],
                    'registration': registrations[method['class']],
                    'limitations': '整段 dispatcher 方法的静态关系；具体 URL 与分支条件未解析，不能当作具体请求路径。'
                                   '不执行项目代码，不推断跨模块动态改写；外部和动态调用另列为未解析。'})
    result['classes'] = [c for c in owners.values() if c['methods'] or c['kind'] != 'scope']
    return result


def link(classes: dict) -> None:
    """Resolve only exact repository import targets. External calls remain explicit unknown."""
    exports = {}
    keys = {}
    for group in classes.values():
        for cls in group:
            if cls.get('lang') != 'python':
                continue
            for methods in cls['methods'].values():
                for method in methods:
                    exports.setdefault(method['python_export'], []).append(cls['name'] + '.' + method['name'])
                    keys.setdefault(cls['name'] + '.' + method['name'], []).append(method)
    for methods in keys.values():
        for method in methods:
            resolved = []
            for call in method['python_calls']:
                candidates = exports.get(call.get('import_target'), []) if 'import_target' in call else [call['target']]
                if (len(candidates) == 1 and len(keys.get(candidates[0], [])) == 1 and
                        keys[candidates[0]][0].get('python_callable', True)):
                    resolved.append(dict(call, target=candidates[0]))
                else:
                    method['python_unresolved'].append({k: call[k] for k in ('call', 'file', 'line')} | {
                        'why': '外部/动态调用或同名目标不唯一，未展开'})
            method['python_calls'] = resolved
