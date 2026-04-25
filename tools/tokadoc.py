#!/usr/bin/env python3
"""tokadoc - Structured API signature extractor for Toka source files.

Usage:
    tokadoc lib/std/string.tk             # Full API
    tokadoc lib/std/string.tk --grep push # Filter by keyword
"""
import re, sys, os
from pathlib import Path

COLOR = os.isatty(1)

def c(code, s):
    return f"\033[{code}m{s}\033[0m" if COLOR else s

def extract_api(path):
    text = Path(path).read_text()
    lines = text.split('\n')
    
    # State machine
    i = 0
    sections = []  # [(kind, name, signature, doc_lines)]
    current_doc = []
    in_impl = None
    
    while i < len(lines):
        line = lines[i]
        
        # Collect doc comments before a definition
        if line.strip().startswith('///'):
            current_doc.append(line.strip()[3:].strip())
            i += 1
            continue
        
        # Pub shape definition
        m = re.match(r'^pub shape (\w+)\s*\((.*?)(?:\)|\|)', line)
        if m:
            sections.append(('shape', m.group(1), line.strip(), list(current_doc)))
            current_doc = []
            i += 1
            continue
        
        # Impl block header
        m = re.match(r'^impl (\w+(?:@\w+)?)\s*\{', line)
        if m:
            in_impl = m.group(1)
            sections.append(('impl', in_impl, line.strip(), list(current_doc)))
            current_doc = []
            i += 1
            continue
        if re.match(r'^\}\s*$', line) and in_impl:
            in_impl = None
            i += 1
            continue
        
        # Inside impl: pub fn
        if in_impl:
            m = re.match(r'^(\s+pub\s+fn\s+\w+.*?)(?:\{|$)', line)
            if m:
                sig = m.group(1).strip()
                # Multi-line signature
                full_sig = sig
                if '(' in sig and ')' not in sig:
                    j = i + 1
                    while j < len(lines):
                        full_sig += ' ' + lines[j].strip()
                        if ')' in lines[j]:
                            break
                        j += 1
                sections.append(('fn', f"{in_impl}::{full_sig.split('fn ')[1].split('(')[0].strip()}", full_sig, list(current_doc)))
                current_doc = []
                i += 1
                continue
        
        # Top-level pub fn
        m = re.match(r'^pub fn (\w+)\((.*?)\)\s*(->\s*\S+)?', line)
        if m:
            name = m.group(1)
            params = m.group(2)
            ret = m.group(3) or ''
            sig = f"pub fn {name}({params}) {ret}"
            # Multi-line
            if '(' in line and ')' not in line:
                j = i + 1
                while j < len(lines):
                    sig += ' ' + lines[j].strip()
                    if ')' in lines[j]:
                        break
                    j += 1
            sections.append(('fn', name, sig.strip(), list(current_doc)))
            current_doc = []
            i += 1
            continue
        
        # Pub alias
        m = re.match(r'^pub alias (\w+) = (.+)', line)
        if m:
            sections.append(('alias', m.group(1), line.strip(), list(current_doc)))
            current_doc = []
        
        i += 1
    
    return sections

def print_api(sections, grep=None):
    for kind, name, sig, docs in sections:
        if grep and grep.lower() not in name.lower() and grep.lower() not in sig.lower():
            continue
        
        if kind == 'shape':
            print(f"\n{c('1;34', '─── ')}{c('1;33', 'shape')} {c('1;37', name)}")
        elif kind == 'impl':
            print(f"\n{c('1;34', '─── ')}{c('1;32', 'impl')} {c('1;37', name)}")
        elif kind == 'fn':
            # Format signature nicely
            short = sig.replace('\n', ' ').replace('  ', ' ')
            print(f"  {c('1;36', 'fn')} {short}")
        elif kind == 'alias':
            print(f"  {c('1;35', 'alias')} {sig}")
        
        for d in docs:
            print(f"    {c('2', '// ' + d)}")
    
    print()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    path = sys.argv[1]
    grep = None
    if '--grep' in sys.argv:
        grep = sys.argv[sys.argv.index('--grep') + 1]
    
    if os.path.isdir(path):
        for f in sorted(Path(path).glob('*.tk')):
            print(f"\n{c('1;44;37', f' 📦 {f.name} ')}")
            sections = extract_api(str(f))
            print_api(sections, grep)
    else:
        sections = extract_api(path)
        print_api(sections, grep)
