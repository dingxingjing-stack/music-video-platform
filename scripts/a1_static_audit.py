"""Static security audit of a1_terminal.py: enumerate imports, every filesystem sink,
every output sink, every string constant carrying secret-shaped data, and assert the
absence of network/docker/R2/replace/argv paths. Reads the file only."""
import ast
import re

P = r"C:\tmp\a1_terminal.py"
src = open(P, encoding="utf-8").read()
tree = ast.parse(src)

imports = []
for n in ast.walk(tree):
    if isinstance(n, ast.Import):
        imports += [a.name for a in n.names]
    elif isinstance(n, ast.ImportFrom):
        imports.append("%s.%s" % (n.module, ",".join(a.name for a in n.names)))

calls = []
for n in ast.walk(tree):
    if isinstance(n, ast.Call):
        f = n.func
        name = ast.unparse(f) if not isinstance(f, ast.Attribute) else f.value.id + "." + f.attr if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) else ast.unparse(f)
        calls.append((n.lineno, name, ast.unparse(n)[:110]))

opens = [c for c in calls if c[1] in ("open", "os.open")]
writes = [c for c in calls if c[1] in ("os.unlink", "os.chmod", "os.chown", "os.replace", "os.rename", "os.remove", "os.mkdir", "os.symlink", "os.write", "os.fsync", "os.close", "os.open")]
printouts = [c for c in calls if c[1].startswith("sys.stdout.write") or c[1].startswith("sys.stderr.write") or c[1] in ("print",)]

print("=== 1. IMPORTS (%d) ===" % len(imports))
print("   " + ", ".join(sorted(set(imports))))
FORBIDDEN_MODS = ("socket", "ssl", "urllib", "http", "requests", "boto3", "botocore",
                  "subprocess", "asyncio", "shutil", "smtplib", "ftplib", "paramiko", "ctypes")
bad_mods = [m for m in imports if m.split(".")[0] in FORBIDDEN_MODS]
print("   network/exec-capable modules: %s" % (bad_mods or "NONE"))

print("=== 2. FILESYSTEM SINKS ===")
for ln, name, txt in opens + writes:
    print("   L%-4d %-10s %s" % (ln, name, txt))
targets = set()
for ln, name, txt in opens + writes:
    m = re.search(r"(ENV|TMP|DIR)\b", txt)
    if m:
        targets.add(m.group(1))
print("   touched path constants: %s" % sorted(targets))
print("   any write-mode open of ENV?  %s" % any("ENV" in t and re.search(r"['\"](w|a|r\+|wb|ab)['\"]", t) for _, _, t in opens))
print("   os.replace / os.rename present? %s" % any(c[1] in ("os.replace", "os.rename") for c in calls))

print("=== 3. OUTPUT SINKS (%d) — every one must be metadata only ===" % len(printouts))
secret_expr = re.compile(r"vals\[|payload|vals\.|v\[:|v\[-|\bv\b\s*(\[:|\[-)")
leaks = [c for c in printouts if secret_expr.search(c[2])]
print("   statements that interpolate a credential expression: %s" % ([str(c) for c in leaks] or "NONE"))
for ln, name, txt in printouts:
    tag = "  <-- CHECK" if secret_expr.search(txt) else ""
    if tag:
        print("   L%-4d %s%s" % (ln, txt[:100], tag))

print("=== 4. ARGV / SHELL ===")
print("   sys.argv used: %s" % ("sys.argv" in src))
print("   os.system / subprocess / eval / dynamic exec present: %s" %
      [k for k in ("os.system", "subprocess", "eval(", "exec(", "popen", "spawn") if k in src] or "NONE")
print("   os.environ written: %s" % bool(re.search(r"os\.environ\s*\[.*\]\s*=", src)))

print("=== 5. REMOTE / PRODUCTION ACTION TOKENS (case-insensitive) ===")
for tok in ("boto3", "s3", "r2.cloudflarestorage", "put_object", "head_bucket", "docker",
            "compose", "curl", "wget", "ssh", "SELECT", "INSERT", "UPDATE", "nginx",
            "systemctl", "git "):
    hits = [i for i, line in enumerate(src.splitlines(), 1) if tok.lower() in line.lower()]
    if hits:
        print("   token %-22s appears on lines %s" % (tok, hits))
print("   (anything listed above must be prose/comments, never a call)")

print("=== 6. LIFETIME OF IN-MEMORY PLAINTEXT ===")
for probe in ("data, ist1, ist2 = read_input(IN)", "vals = parse_input_strict(data)",
              "del data", "del vals", "del payload", "del cur",
              "if payload != data:", "if len(payload) != IN_BYTES:"):
    print("   %-34s present=%s" % (probe, probe in src))
print("   any place that could print an exception object: %s" %
      [t for _, _, t in printouts if "str(e)" in t or "repr" in t or "exc_info" in t])

print("=== 7. PRE-EXISTING STAGING HANDLING ===")
for kw in ("os.path.exists(TMP)", "O_EXCL", "FileExistsError", "S1_TMP_PREEXISTING",
           "NO_TMP_BY_THIS_RUN", "RESIDUE_PENDING_AUTHORITY"):
    print("   %-26s present=%s" % (kw, kw in src))

print("=== 8. STOP-After-PASS ===")
tail = src.splitlines()[-22:]
print("   last executable lines of main():")
for l in tail:
    if l.strip().startswith(("sys.stdout", "raise", "if ", "del ", "return")):
        print("     " + l.strip()[:96])

print("=== 9. STRING CONSTANTS CONTAINING HEX-LIKE RUNS (would be baked-in creds) ===")
long_hex = [c.value for c in ast.walk(tree) if isinstance(c, ast.Constant)
            and isinstance(c.value, str) and re.search(r"[0-9a-f]{16,}", c.value)]
print("   count=%d %s" % (len(long_hex), long_hex or "NONE"))

print("=== 10. v4.3.8 SPECIFIC GUARANTEES ===")
funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
print("   DELETED_EMPTY_UNWRITTEN occurrences: %d (must be 0)" % src.count("DELETED_EMPTY_UNWRITTEN"))
print("   zero-byte special delete path (`st_size == 0`): %d (must be 0)" % src.count("st_size == 0"))
print("   any comparison to literal 0 inside cleanup_ours: %r" %
      [ast.unparse(x) for x in ast.walk(funcs["cleanup_ours"])
       if isinstance(x, ast.Compare) and any(isinstance(o, ast.Constant) and o.value == 0
                                            for o in x.comparators)])

co = ast.unparse(funcs["cleanup_ours"])
need = ["st.st_ino != rec[0]", "st.st_size != rec[1]", "actual != rec[2]", "os.unlink(TMP)"]
for frag in need:
    print("   cleanup_ours contains %-24s : %s" % (frag, frag in co))
print("   unlink calls in the whole file: %d, all inside cleanup_ours: %s" %
      (len([1 for x in ast.walk(tree) if isinstance(x, ast.Call)
            and getattr(x.func, "attr", "") == "unlink"]),
       all(getattr(x.func, "attr", "") != "unlink" or x.lineno >= funcs["cleanup_ours"].lineno
           and x.lineno <= funcs["cleanup_ours"].end_lineno for x in ast.walk(tree)
           if isinstance(x, ast.Call))))
guard = [n for n in tree.body if isinstance(n, ast.If)]
has_bare = any("except BaseException" in ast.unparse(n) for n in tree.body)
print("   module-level BaseException guard present: %s" % has_bare)
# AST-level: find the guard's except handler and inspect only what it emits.
guard_src = ""
for n in ast.walk(tree):
    if isinstance(n, ast.ExceptHandler) and n.type is not None and "BaseException" in ast.unparse(n.type):
        guard_src = ast.unparse(n)
print("   guard handler located: %s (statements=%d)" % (bool(guard_src), guard_src.count("sys.stdout.write")))
for bad in ("str(e", "repr(", "format_exc", "print_exc", "traceback", "payload", "vals[", "cur["):
    print("      guard references %-13s : %s" % (bad, bad in guard_src))
print("   traceback module imported anywhere: %s" % bool(re.search(r"^\s*import traceback", src, re.M)))
se_lines = [i for i, l in enumerate(src.splitlines(), 1) if "str(e)" in l]
print("   str(e) usages (outside the guard) on lines %s -- all carry an errno/path, never bytes" % se_lines)
print("   RESIDUE predicate wired in both fail() and guard: %d uses of is_residue()" % src.count("is_residue(status)"))
hosts = [c.value for c in ast.walk(tree) if isinstance(c, ast.Constant) and isinstance(c.value, str)
         and re.search(r"(melovar-ecs|cloudflarestorage|aliyuncs|https?://|\d{1,3}(\.\d{1,3}){3})", c.value)]
print("   host/URL/IP literals (must be NONE -> proves no remote target): %s" % (hosts or "NONE"))
print("   ENV write-mode opens: %s | os.replace/rename: %s" %
      (any("ENV" in t and re.search(r"['\"](w|a|r\+|wb|ab)['\"]", t) for _, _, t in opens),
       any(c[1] in ("os.replace", "os.rename") for c in calls)))

print("=== 11. IN-MODE GUARANTEES ===")
funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
print("   new constants: IN=%s IN_BYTES=%s IN_KEYS=%s" % (
    "IN =" in src, bool(re.search(r"IN_BYTES = 206", src)), "IN_KEYS" in src))
print("   IN_BYTES must be 206, and 129 must not appear: 206=%s 129=%s" %
      (bool(re.search(r"IN_BYTES = 206", src)), "129" in src))
for fn in ("mount_fstype", "read_input", "parse_input_strict",
           "input_dir_ok", "input_attr_ok", "st_delta"):
    print("   function %-18s defined=%s" % (fn, fn in funcs))
print("   getpass removed: %s | getpass in imports: %s" %
      ("getpass" not in src, "getpass" in imports))
# every mutating/lookup call must target TMP or IN-as-read-only; IN must never be written
bad_in = [t for _, _, t in opens if re.search(r"\bIN\b", t)
          and re.search(r"(O_WRONLY|O_RDWR|O_CREAT|O_TRUNC|['\"]w|['\"]a)", t)]
print("   IN opened for write/create: %s" % (bad_in or "NONE"))
print("   unlink/remove calls: %s" % [t for _, n, t in calls if n in ("os.unlink", "os.remove")])
print("   chmod/chown targeting IN: %s" %
      [t for _, n, t in calls if n in ("os.chmod", "os.chown") and re.search(r"\bIN\b", t)])
ri = ast.unparse(funcs["read_input"]) if "read_input" in funcs else ""
for kw in ("O_RDONLY", "O_DIRECTORY", "O_NOFOLLOW", "dir_fd=dfd", "os.fstat(fd)",
           "S0_IN_ABSENT", "S0_IN_SYMLINK", "S0_IN_MUTATED", "S0_IN_READ_LEN",
           "S0_PLATFORM", "input_attr_ok", "input_dir_ok"):
    print("      read_input uses %-18s : %s" % (kw, kw in ri))
print("   read_input has no write syscall: %s" %
      (not re.search(r"os\.(write|unlink|chmod|chown|rename|replace|truncate|remove)\(", ri)))
print("   realpath guard: %s | tmpfs assertion gate: %s" %
      ('os.path.realpath(IN) == os.path.realpath(TMP)' in src, 'if fstype != "tmpfs"' in src))
print("   stat fields compared for mutation: %s" % (STAT if (STAT := re.search(r"STAT_FIELDS = \(([^)]*)\)", src)) else None))
codes = sorted(set(re.findall(r'fail\("(S[0-9]_[A-Z_]+)"', src)))
print("   codes passed as literals to fail(): %s" % ", ".join(codes))
# predicate-emitted codes travel through a variable, so grep the source for them too
pred_codes = ("S0_IN_NOT_REGULAR", "S0_IN_OWNER", "S0_IN_MODE", "S0_IN_NLINK",
              "S0_IN_DIR_NOT_DIR", "S0_IN_DIR_OWNER", "S0_IN_DIR_WRITABLE")
print("   predicate-emitted codes present: %s (missing: %s)" % (
    sum(1 for c in pred_codes if '"%s"' % c in src),
    [c for c in pred_codes if '"%s"' % c not in src] or "none"))
