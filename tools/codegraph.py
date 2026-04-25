#!/usr/bin/env python3
"""codegraph — 调用图 / 依赖图 工具

扫描所有 .tk 文件，输出：
  - 每个文件导入了什么
  - 每个文件定义了哪些 pub 函数/shape
  - 每个函数调用了哪些函数
  - 交互式查询：某个函数被谁调用 / 调用了谁

Usage:
  codegraph /path/to/project               # 扫全项目
  codegraph /path/to/project --grep parse   # 过滤含 parse 的节点
  codegraph /path/to/project --file net.tk  # 只看某个文件
  codegraph /path/to/project --callees parse_query   # 谁调用了 parse_query
  codegraph /path/to/project --callers parse_query    # parse_query 调用了谁
"""
import re, sys, os, json
from pathlib import Path
from collections import defaultdict

COLOR = os.isatty(1)
def c(code, s): return f"\033[{code}m{s}\033[0m" if COLOR else s

def find_tk_files(root):
    root = Path(root)
    files = []
    for f in sorted(root.rglob("*.tk")):
        parts = f.relative_to(root).parts
        if any(p.startswith('.') or p in ('target', 'build', 'node_modules') for p in parts):
            continue
        files.append(f)
    return files

def parse_file(path):
    text = path.read_text(errors='replace')
    lines = text.split('\n')

    info = {
        'path': str(path),
        'imports': [],
        'shapes': [],
        'pub_fns': [],
        'priv_fns': [],
        'fn_calls': defaultdict(set),
        'main': None,
    }

    current_fn = None
    current_fn_body_start = None

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        m = re.match(r'^import\s+(\S+?)(?:::(\S+))?', stripped)
        if m:
            module = m.group(1)
            symbol = m.group(2) or '*'
            info['imports'].append((module, symbol))

        m = re.match(r'^pub\s+shape\s+(\w+)', stripped)
        if m:
            info['shapes'].append((m.group(1), i))

        is_pub = stripped.startswith('pub ')
        m = re.match(r'^(?:pub\s+)?fn\s+(\w+)', stripped)
        if m:
            name = m.group(1)
            j = i - 1
            sig_lines = [line]
            while j < len(lines):
                sig_lines.append(lines[j])
                if '{' in lines[j] or lines[j].strip() == '' or j > i + 5:
                    break
                j += 1
            signature = ' '.join(l.strip() for l in sig_lines if l.strip())

            fn_entry = (name, i, signature)
            if is_pub:
                info['pub_fns'].append(fn_entry)
            else:
                info['priv_fns'].append(fn_entry)

            if name == 'main' and is_pub:
                info['main'] = i

            current_fn = name
            current_fn_body_start = i

        if current_fn and stripped and not stripped.startswith('//'):
            if i > current_fn_body_start:
                for m in re.finditer(r'(?<![.\w])(\w+)\s*\(', stripped):
                    callee = m.group(1)
                    if callee not in ('if', 'while', 'for', 'match', 'return', 'else',
                                       'true', 'false', 'let', 'auto', 'var', 'mut',
                                       'import', 'pub', 'fn', 'shape', 'impl', 'alias'):
                        info['fn_calls'][current_fn].add(callee)

                for m in re.finditer(r'(\w+)::(\w+)\s*\(', stripped):
                    info['fn_calls'][current_fn].add("{}::{}".format(m.group(1), m.group(2)))

    return info

def build_graph(files):
    graph = {
        'files': {},
        'all_fns': {},
        'all_shapes': {},
        'import_graph': defaultdict(list),
        'call_graph': defaultdict(set),
        'reverse_call_graph': defaultdict(set),
        'file_fns': defaultdict(list),
    }

    for info in files:
        fpath = info['path']
        graph['files'][fpath] = info

        for module, symbol in info['imports']:
            graph['import_graph'][fpath].append((module, symbol))

        for name, line, sig in info['pub_fns']:
            graph['all_fns'][name] = (fpath, line, sig, True)
            graph['file_fns'][fpath].append((name, line, sig, True))

        for name, line, sig in info['priv_fns']:
            if name not in graph['all_fns']:
                graph['all_fns'][name] = (fpath, line, sig, False)
            graph['file_fns'][fpath].append((name, line, sig, False))

        for name, line in info['shapes']:
            graph['all_shapes'][name] = (fpath, line)

        for caller, callees in info['fn_calls'].items():
            for callee in callees:
                graph['call_graph'][caller].add(callee)
                graph['reverse_call_graph'][callee].add(caller)

    return graph

def fmt_file_block(path):
    return "\033[1;44;37m \U0001f4c4 {} \033[0m".format(path)

def fmt_heading(s):
    return "\033[1;44;37m {} \033[0m".format(s)

def fmt_dim(s):
    return "\033[2m{}\033[0m".format(s)

def fmt_green(s):
    return "\033[1;32m{}\033[0m".format(s)

def fmt_yellow(s):
    return "\033[1;33m{}\033[0m".format(s)

def fmt_cyan(s):
    return "\033[1;36m{}\033[0m".format(s)

def fmt_white(s):
    return "\033[1;37m{}\033[0m".format(s)

def print_file_summary(graph, filepath):
    info = graph['files'].get(filepath)
    if not info:
        print("  \u274c File not found: {}".format(filepath))
        return

    print("\n{}".format(fmt_file_block(filepath)))

    if info['imports']:
        print("\n  {}".format(fmt_yellow('imports')))
        for module, symbol in info['imports'][:15]:
            s = "  {} {}".format(fmt_dim('\u2514\u2500'), module)
            if symbol != '*':
                s += "::{}".format(symbol)
            print(s)
        remaining = len(info['imports']) - 15
        if remaining > 0:
            print("  {} ... and {} more".format(fmt_dim('\u2514\u2500'), remaining))

    if info['shapes']:
        print("\n  {}".format(fmt_yellow('shapes')))
        for name, line in info['shapes']:
            print("  {} {}  {}".format(fmt_dim('\u2514\u2500'), fmt_white(name), fmt_dim(":{}".format(line))))

    all_fns = info['pub_fns'] + info['priv_fns']
    if all_fns:
        pub_count = len(info['pub_fns'])
        priv_count = len(info['priv_fns'])
        print("\n  {} ({} pub, {} priv)".format(fmt_yellow('functions'), pub_count, priv_count))
        pub_set = set(info['pub_fns'])
        for name, line, sig in all_fns[:20]:
            if (name, line, sig) in pub_set:
                mark = fmt_cyan('pub')
            else:
                mark = fmt_dim('fn')
            print("  {} {} {}  {}".format(fmt_dim('\u2514\u2500'), mark, fmt_white(name), fmt_dim(":{}".format(line))))
            callees = graph['call_graph'].get(name, set())
            if callees:
                callee_list = sorted(callees)[:5]
                for callee in callee_list:
                    print("       {} {}".format(fmt_dim('\u2192'), callee))
                remaining = len(callees) - 5
                if remaining > 0:
                    print("       {} ... +{} more".format(fmt_dim('\u2192'), remaining))
        remaining = len(all_fns) - 20
        if remaining > 0:
            print("  {} ... and {} more functions".format(fmt_dim('\u2514\u2500'), remaining))

    if info['main']:
        print("\n  {} entry: main() at line {}".format(fmt_green('\u2605'), info['main']))

def print_callers(graph, fn_name, depth=0, max_depth=3, visited=None):
    if visited is None:
        visited = set()
    if depth > max_depth or fn_name in visited:
        return
    visited.add(fn_name)

    callers = graph['reverse_call_graph'].get(fn_name, set())
    if not callers:
        return

    prefix = "  " * depth
    for caller in sorted(callers)[:8]:
        fn_info = graph['all_fns'].get(caller)
        loc = ""
        if fn_info:
            loc = " ({})".format(fn_info[0])
        print("{}{} {}{}".format(prefix, fmt_dim('\u2514\u2500'), fmt_cyan(caller), fmt_dim(loc)))
        print_callers(graph, caller, depth + 1, max_depth, visited)

def print_callees(graph, fn_name, depth=0, max_depth=3, visited=None):
    if visited is None:
        visited = set()
    if depth > max_depth or fn_name in visited:
        return
    visited.add(fn_name)

    callees = graph['call_graph'].get(fn_name, set())
    if not callees:
        return

    prefix = "  " * depth
    for callee in sorted(callees)[:8]:
        fn_info = graph['all_fns'].get(callee)
        loc = ""
        if fn_info:
            loc = " ({})".format(fn_info[0])
        print("{}{} {}{}".format(prefix, fmt_dim('\u2514\u2500'), fmt_cyan(callee), fmt_dim(loc)))
        print_callees(graph, callee, depth + 1, max_depth, visited)

def print_graph_summary(graph, grep=None):
    files = graph['files']
    all_fns = graph['all_fns']
    all_shapes = graph['all_shapes']

    pub_count = sum(1 for v in all_fns.values() if v[3])
    priv_count = sum(1 for v in all_fns.values() if not v[3])

    print("\n{}".format(fmt_heading(' \U0001f4ca Project Summary ')))
    print("  Files:    {}".format(len(files)))
    print("  Shapes:   {}".format(len(all_shapes)))
    print("  Pub fns:  {}".format(pub_count))
    print("  Priv fns: {}".format(priv_count))
    print("  Total:    {} functions".format(len(all_fns)))

    entries_found = False
    for path, info in files.items():
        if info.get('main'):
            if not entries_found:
                print("\n  {}".format(fmt_yellow('Entry points')))
                entries_found = True
            print("    {} {}  (main at line {})".format(fmt_green('\u2605'), path, info['main']))

    print("\n  {}".format(fmt_yellow('Files')))
    for fpath in sorted(files.keys()):
        info = files[fpath]
        short = os.path.relpath(fpath)
        fn_count = len(info['pub_fns']) + len(info['priv_fns'])
        shape_count = len(info['shapes'])
        import_count = len(info['imports'])
        main_mark = ""
        if info['main']:
            main_mark = " {}".format(fmt_green('\u2605'))

        if grep:
            if grep.lower() not in short.lower():
                continue

        print("  {} {}{}  {}".format(
            fmt_dim('\u2514\u2500'), short, main_mark,
            fmt_dim("({}f / {}s / {}i)".format(fn_count, shape_count, import_count))
        ))

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    root = sys.argv[1]
    grep = None
    file_filter = None
    show_callers = None
    show_callees = None
    json_out = False

    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == '--grep' and i + 1 < len(args):
            grep = args[i + 1]; i += 2
        elif args[i] == '--file' and i + 1 < len(args):
            file_filter = args[i + 1]; i += 2
        elif args[i] == '--callers' and i + 1 < len(args):
            show_callers = args[i + 1]; i += 2
        elif args[i] == '--callees' and i + 1 < len(args):
            show_callees = args[i + 1]; i += 2
        elif args[i] == '--json':
            json_out = True; i += 1
        else:
            i += 1

    print("\U0001f50d Scanning: {}".format(root))
    tk_files = find_tk_files(root)
    print("   Found {} .tk files".format(len(tk_files)))

    parsed = [parse_file(f) for f in tk_files]
    graph = build_graph(parsed)

    if json_out:
        json_graph = {
            'files': list(graph['files'].keys()),
            'functions': {k: {'file': v[0], 'line': v[1], 'sig': v[2], 'pub': v[3]}
                         for k, v in graph['all_fns'].items()},
            'shapes': {k: {'file': v[0], 'line': v[1]} for k, v in graph['all_shapes'].items()},
            'call_graph': {k: list(v) for k, v in graph['call_graph'].items()},
        }
        print(json.dumps(json_graph, indent=2, ensure_ascii=False))
        return

    if show_callers:
        fn_name = show_callers
        fn_info = graph['all_fns'].get(fn_name)
        if fn_info:
            print("\n{}".format(fmt_heading(' \U0001f50d Callers of {} '.format(fn_name))))
            print("   Defined in: {}:{}".format(fn_info[0], fn_info[1]))
            print("   Signature:  {}".format(fn_info[2]))
            print()
            callers = graph['reverse_call_graph'].get(fn_name, set())
            if callers:
                print("   {} caller(s):".format(len(callers)))
                print_callers(graph, fn_name, max_depth=2)
            else:
                print("   {}".format(fmt_dim('(no callers \u2014 possibly dead code or entry point)')))
        else:
            print("   \u274c Function '{}' not found in graph".format(fn_name))
        return

    if show_callees:
        fn_name = show_callees
        fn_info = graph['all_fns'].get(fn_name)
        if fn_info:
            print("\n{}".format(fmt_heading(' \U0001f50d {} calls \u2192 '.format(fn_name))))
            print("   Defined in: {}:{}".format(fn_info[0], fn_info[1]))
            print("   Signature:  {}".format(fn_info[2]))
            print()
            callees = graph['call_graph'].get(fn_name, set())
            if callees:
                print("   Calls {} function(s):".format(len(callees)))
                print_callees(graph, fn_name, max_depth=2)
            else:
                print("   {}".format(fmt_dim('(leaf function \u2014 no calls)')))
        else:
            print("   \u274c Function '{}' not found in graph".format(fn_name))
        return

    if file_filter:
        for fpath in graph['files']:
            if file_filter in fpath:
                print_file_summary(graph, fpath)
                return
        print("   \u274c No file matching '{}'".format(file_filter))
        return

    print_graph_summary(graph, grep)

if __name__ == '__main__':
    main()
