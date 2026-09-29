"""A1 (IN mode) local verification suite.  Nothing here touches ECS, the network, or
real credentials: every file is under a temp dir and every credential value is a
synthetic constant built from repeated single characters.

Coverage layers:
  A  pure predicates  : input_dir_ok / input_attr_ok / st_delta / parse_input_strict /
                       mount_fstype / perm_ok / ownership_ok / is_residue
  B  read_input       : exercised against a FakeOS (Windows has no O_DIRECTORY/
                       O_NOFOLLOW/dir_fd), so the TOCTOU sequence itself is testable
  C  end-to-end main(): real sandbox files; read_input is replaced by a plain reader
                       and input_dir_ok/input_attr_ok/perm_ok are stubbed, because
                       Windows cannot express uid/gid/mode 0400/0600. Those gates are
                       proven in layers A and B instead.
  D  TMP lifecycle    : cleanup decision table, residue propagation, fault injection,
                       write-error classification (unchanged semantics from v4.3.8b)
"""
import hashlib
import os
import shutil
import sys
import tempfile
import types

if not hasattr(os, "chown"):
    os.chown = lambda p, u, g: None          # Linux-only syscall; harness no-op

FAKE32a = "f" * 32
FAKE32b = "a" * 32
FAKE64 = "0" * 64
DEAD = "c184c8" + "0" * 22 + "08c5"
OLD_ACC = "d" * 32
OLD_SEC = "e" * 64

root = tempfile.mkdtemp(prefix="a1sim_").replace("\\", "/")
ENV = root + "/backend.env"
TMPF = root + "/.r2pair.tmp"
INF = root + "/.r2pair.in"
MNT = root + "/mounts"

with open(ENV, "w", newline="\n") as f:
    f.write("CLOUDFLARE_R2_ACCOUNT_ID=%s\nCLOUDFLARE_R2_ACCESS_KEY=%s\n"
            "CLOUDFLARE_R2_SECRET_KEY=%s\nOTHER=keep\n" % (OLD_ACC, DEAD, OLD_SEC))
with open(MNT, "w", newline="\n") as f:
    f.write("tmpfs / ext4 rw 0 0\ntmpfs %s tmpfs rw,nosuid 0 0\n" % root)

src = open(r"C:\tmp\a1_terminal.py", encoding="utf-8").read()
src = (src.replace('ENV = "/opt/melovar/secrets/backend.env"', 'ENV = %r' % ENV)
          .replace('TMP = "/opt/melovar/secrets/.r2pair.tmp"', 'TMP = %r' % TMPF)
          .replace('DIR = "/opt/melovar/secrets"', 'DIR = %r' % root)
          .replace('IN = "/run/melovar-r2pair.in"', 'IN = %r' % INF)
          .replace('MOUNTS = "/proc/mounts"', 'MOUNTS = %r' % MNT))
assert "IN_BYTES = 206" in src
mod = types.ModuleType("sim")
mod.__dict__["__name__"] = "sim"
exec(compile(src, "a1_terminal.py", "exec"), mod.__dict__)
REAL_PERM_OK = mod.perm_ok          # genuine predicate, restored for the C2 case

GOOD = ("CLOUDFLARE_R2_ACCOUNT_ID=%s\nCLOUDFLARE_R2_ACCESS_KEY=%s\n"
        "CLOUDFLARE_R2_SECRET_KEY=%s\n" % (FAKE32a, FAKE32b, FAKE64)).encode()
env0 = hashlib.sha256(open(ENV, 'rb').read()).hexdigest()

ok = True
def chk(label, cond, got=""):
    global ok
    ok = ok and bool(cond)
    print(("  PASS  " if cond else "  FAIL  ") + label + ("" if cond or not got else "  [%s]" % got))

def quiet(fn):
    out = []
    class T:
        def write(self, x):
            out.append(x)
    real = sys.stdout
    sys.stdout = T()
    try:
        try:
            fn()
            rc = 0
        except SystemExit as e:
            rc = e.code
    finally:
        sys.stdout = real
    return rc, "".join(out)

def rep(o):
    d = {}
    for line in o.strip().splitlines():
        for tok in line.split():
            if "=" in tok:
                k = tok.split("=", 1)[0]
                if k not in d:
                    d[k] = tok.split("=", 1)[1]
    return d

def reset_run():
    mod.created = False
    mod.rec = (None, None, None)
    mod.env_sha_before = None

def put_in(data):
    if os.path.exists(INF):
        os.chmod(INF, 0o600)
        os.remove(INF)
    with open(INF, "wb") as f:
        f.write(data)

def clean_tmp():
    if os.path.exists(TMPF):
        os.chmod(TMPF, 0o600)
        os.remove(TMPF)

# --------------------------------------------------------------------------- A
print("LAYER A: PURE PREDICATES")
for args, e in [((0o040755, 0, 0), None), ((0o040775, 0, 0), "S0_IN_DIR_WRITABLE"),
               ((0o040755, 0, 1000), "S0_IN_DIR_OWNER"), ((0o100600, 0, 0), "S0_IN_DIR_NOT_DIR"),
               ((0o040700, 0, 0), None), ((0o040077, 0, 0), "S0_IN_DIR_WRITABLE")]:
    chk("input_dir_ok%s -> %s" % (args, e), mod.input_dir_ok(*args) is e, str(mod.input_dir_ok(*args)))
for args, e in [((0o100400, 0, 0, 1), None), ((0o100600, 0, 0, 1), "S0_IN_MODE"),
               ((0o100440, 0, 0, 1), "S0_IN_MODE"), ((0o100400, 0, 1000, 1), "S0_IN_OWNER"),
               ((0o100400, 1000, 0, 1), "S0_IN_OWNER"), ((0o100400, 0, 0, 2), "S0_IN_NLINK"),
               ((0o040400, 0, 0, 1), "S0_IN_NOT_REGULAR"), ((0o020400, 0, 0, 1), "S0_IN_NOT_REGULAR"),
               ((0o100444, 0, 0, 1), "S0_IN_MODE")]:
    chk("input_attr_ok(mode=%04o,uid=%d,gid=%d,nlink=%d) -> %s" % (args[0], args[1], args[2], args[3], e),
        mod.input_attr_ok(*args) is e, str(mod.input_attr_ok(*args)))

class S:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)
base = dict(st_ino=7, st_size=206, st_nlink=1, st_uid=0, st_gid=0,
            st_mode=0o100400, st_mtime_ns=1000, st_ctime_ns=1000)
chk("st_delta(identical) == []", mod.st_delta(S(**base), S(**base)) == [])
chk("st_delta(same-size in-place write caught via mtime_ns)",
    mod.st_delta(S(**base), S(**{**base, "st_mtime_ns": 2000})) == ["st_mtime_ns"])
chk("st_delta(ctime bump caught)",
    mod.st_delta(S(**base), S(**{**base, "st_ctime_ns": 2000})) == ["st_ctime_ns"])
chk("st_delta(inode swap caught)", "st_ino" in mod.st_delta(S(**base), S(**{**base, "st_ino": 8})))
chk("st_delta(nlink change caught)", "st_nlink" in mod.st_delta(S(**base), S(**{**base, "st_nlink": 2})))
chk("st_delta(reported field set is the locked 8)",
    mod.STAT_FIELDS == ("st_ino", "st_size", "st_nlink", "st_uid", "st_gid",
                        "st_mode", "st_mtime_ns", "st_ctime_ns"))

def parse_case(label, data, expect_fail):
    reset_run()
    rc, o = quiet(lambda: mod.parse_input_strict(data))
    r = rep(o)
    if expect_fail is None:
        chk(label + " accepted", r.get("A1_RESULT") != "FAIL", r.get("PRIMARY_CODE", ""))
    else:
        chk(label + " -> " + expect_fail, r.get("PRIMARY_CODE") == expect_fail, r.get("PRIMARY_CODE", "?"))
        chk(label + " detail never contains value bytes",
            FAKE32a not in o and FAKE64 not in o and FAKE32b not in o)

print("parse_input_strict byte/format table")
parse_case("valid 206", GOOD, None)
parse_case("205 (no final LF)", GOOD[:-1], "S0_IN_FORMAT")
parse_case("207 (extra byte)", GOOD + b"x", "S0_IN_FORMAT")
parse_case("extra blank line", GOOD + b"\n", "S0_IN_FORMAT")
parse_case("CRLF present", GOOD.replace(b"\n", b"\r\n"), "S0_IN_FORMAT")
parse_case("BOM prefixed", b"\xef\xbb\xbf" + GOOD[:-3], "S0_IN_FORMAT")
parse_case("uppercase hex", GOOD.replace(FAKE32a.encode(), b"F" * 32), "S0_IN_FORMAT")
parse_case("secret length 63", GOOD.replace(FAKE64.encode(), b"0" * 63), "S0_IN_FORMAT")
parse_case("trailing space", GOOD.replace(FAKE32a.encode(), (FAKE32a + " ").encode()), "S0_IN_FORMAT")
parse_case("export prefix", GOOD.replace(b"CLOUDFLARE_R2_ACCOUNT_ID", b"export CLOUDFLARE_R2_ACCOUNT_I", 1), "S0_IN_FORMAT")
L1 = ("CLOUDFLARE_R2_ACCOUNT_ID=%s\n" % FAKE32a).encode()
L2 = ("CLOUDFLARE_R2_ACCESS_KEY=%s\n" % FAKE32b).encode()
L3 = ("CLOUDFLARE_R2_SECRET_KEY=%s\n" % FAKE64).encode()
assert len(L1) == 58 and len(L2) == 58 and len(L3) == 90
parse_case("duplicate key (L1,L1,L3 still 206)", L1 + L1 + L3, "S0_IN_FORMAT")
reset_run()
rcx, ox = quiet(lambda: mod.parse_input_strict(L1 + L1 + L3))
rx = rep(ox)
chk("   duplicate caught by positional gate; set() backstop is redundant defence",
    rx.get("DETAIL", "").startswith("key_at=1"), rx.get("DETAIL", "?"))
parse_case("wrong key order", ("CLOUDFLARE_R2_ACCESS_KEY=%s\nCLOUDFLARE_R2_ACCOUNT_ID=%s\n"
                               "CLOUDFLARE_R2_SECRET_KEY=%s\n" % (FAKE32b, FAKE32a, FAKE64)).encode(), "S0_IN_FORMAT")
parse_case("unknown key", GOOD.replace(b"CLOUDFLARE_R2_ACCOUNT_ID", b"CLOUDFLARE_R2_ACCOUNT_IDX", 1), "S0_IN_FORMAT")
parse_case("non-ascii byte (length preserved)", GOOD.replace(b"0" * 64, bytes([0xe9]) * 63 + b"0"), "S0_IN_FORMAT")
parse_case("empty file", b"", "S0_IN_FORMAT")
parse_case("tab inside value", GOOD.replace(FAKE32b.encode(), ("\t" + "a" * 31).encode()), "S0_IN_FORMAT")

print("mount_fstype")
chk("longest match wins (tmpfs over ext4)", mod.mount_fstype(INF) == "tmpfs")
chk("falls back to shorter mount point", mod.mount_fstype(root + "/sub/dir/x") == "tmpfs")
chk("path outside every listed mount -> '?'", mod.mount_fstype("Q:/never-mounted/x") == "?")
chk("root mount is the fallback it claims to be", mod.mount_fstype("/etc/hosts") == "ext4")
chk("unreadable mounts file -> '?'", mod.mount_fstype(INF, mounts=root + "/nope") == "?")
with open(root + "/mounts_ext4", "w", newline="\n") as f:
    f.write("dev %s ext4 rw 0 0\n" % root)
chk("ext4 is reported as ext4", mod.mount_fstype(INF, mounts=root + "/mounts_ext4") == "ext4")

# --------------------------------------------------------------------------- B
print("LAYER B: read_input AGAINST FakeOS")


class FakeStat:
    def __init__(self, node):
        self.st_ino = node["ino"]; self.st_size = len(node["data"]); self.st_nlink = node["nlink"]
        self.st_uid = node["uid"]; self.st_gid = node["gid"]; self.st_mode = node["mode"]
        self.st_mtime_ns = node["mtime_ns"]; self.st_ctime_ns = node["ctime_ns"]


class FakeOS:
    O_RDONLY = 0
    O_DIRECTORY = 0o200000
    O_NOFOLLOW = 0o400000
    O_WRONLY = 1
    O_CREAT = 0o100
    O_EXCL = 0o2000

    def __init__(self):
        self.nodes = {}
        self.fd = 100
        self.open_map = {}
        self.read_hook = None
        self.path = os.path
        self.OSError = OSError
        self.FileNotFoundError = FileNotFoundError

    def add_dir(self, name, mode=0o040755, uid=0, gid=0):
        self.nodes[name] = dict(data=b"", ino=len(self.nodes) + 1, nlink=1, uid=uid,
                                gid=gid, mode=mode, mtime_ns=1, ctime_ns=1)

    def add_file(self, name, data, mode=0o100400, uid=0, gid=0, nlink=1):
        self.nodes[name] = dict(data=data, ino=len(self.nodes) + 1, nlink=nlink, uid=uid,
                                gid=gid, mode=mode, mtime_ns=1, ctime_ns=1)

    def add_symlink(self, name):
        self.nodes[name] = dict(data=b"", ino=len(self.nodes) + 1, nlink=1, uid=0, gid=0,
                                mode=0o120777, mtime_ns=1, ctime_ns=1, symlink=True)

    def open(self, path, flags, mode=0o777, dir_fd=None):
        name = path if dir_fd is None else self.open_map[dir_fd]["name"] + "/" + path
        node = self.nodes.get(name)
        if node is None:
            raise FileNotFoundError(2, "no such file", name)
        if node.get("symlink") and flags & self.O_NOFOLLOW:
            raise OSError(40, "too many levels of symbolic links", name)
        if flags & self.O_DIRECTORY and (node["mode"] & 0o170000) != 0o040000:
            raise OSError(20, "not a directory", name)
        self.fd += 1
        self.open_map[self.fd] = dict(name=name, node=node, off=0, flags=flags)
        return self.fd

    def fstat(self, fd):
        return FakeStat(self.open_map[fd]["node"])

    def read(self, fd, n):
        e = self.open_map[fd]
        if self.read_hook:
            self.read_hook(e["node"])
        chunk = e["node"]["data"][e["off"]:e["off"] + n]
        e["off"] += len(chunk)
        return chunk

    def close(self, fd):
        self.open_map.pop(fd, None)


real_os = mod.os
for case, prep, expect in [
    ("normal read", lambda o: (o.add_dir("/run"), o.add_file("/run/x.in", GOOD)), None),
    ("missing IN", lambda o: o.add_dir("/run"), "S0_IN_ABSENT"),
    ("symlink IN", lambda o: (o.add_dir("/run"), o.add_symlink("/run/x.in")), "S0_IN_SYMLINK"),
    ("nlink=2 IN", lambda o: (o.add_dir("/run"), o.add_file("/run/x.in", GOOD, nlink=2)), "S0_IN_NLINK"),
    ("mode 0600 IN", lambda o: (o.add_dir("/run"), o.add_file("/run/x.in", GOOD, mode=0o100600)), "S0_IN_MODE"),
    ("gid!=0 IN", lambda o: (o.add_dir("/run"), o.add_file("/run/x.in", GOOD, gid=1000)), "S0_IN_OWNER"),
    ("dir group-writable", lambda o: (o.add_dir("/run", mode=0o040775), o.add_file("/run/x.in", GOOD)), "S0_IN_DIR_WRITABLE"),
    ("dir not root-owned", lambda o: (o.add_dir("/run", uid=1000), o.add_file("/run/x.in", GOOD)), "S0_IN_DIR_OWNER"),
    ("IN is a fifo", lambda o: (o.add_dir("/run"), o.add_file("/run/x.in", GOOD, mode=0o020400)), "S0_IN_NOT_REGULAR"),
]:
    fo = FakeOS()
    prep(fo)
    mod.os = fo
    reset_run()
    rc, o = quiet(lambda: mod.read_input("/run/x.in"))
    mod.os = real_os
    r = rep(o)
    if expect is None:
        got = r.get("A1_RESULT") != "FAIL"
        chk("read_input %s succeeds" % case, got, r.get("PRIMARY_CODE", ""))
    else:
        chk("read_input %s -> %s" % (case, expect), r.get("PRIMARY_CODE") == expect, r.get("PRIMARY_CODE", "?"))
    if expect and expect.startswith("S0_IN_"):
        chk("   no TMP created on %s" % case, not os.path.exists(TMPF))
        chk("   detail leaks no value bytes", FAKE32a not in o and FAKE64 not in o)

# same-size in-place modification during the read must be caught
fo = FakeOS()
fo.add_dir("/run")
fo.add_file("/run/x.in", GOOD)
def mutate(node):
    if node["data"] == GOOD:
        node["data"] = b"X" * len(GOOD)
        node["mtime_ns"] = 999
        node["ctime_ns"] = 999
fo.read_hook = mutate
mod.os = fo
reset_run()
rc, o = quiet(lambda: mod.read_input("/run/x.in"))
mod.os = real_os
r = rep(o)
chk("same-size in-place rewrite -> S0_IN_MUTATED", r.get("PRIMARY_CODE") == "S0_IN_MUTATED", r.get("PRIMARY_CODE", "?"))
chk("   mutation detail names only stat fields", "st_mtime_ns" in o and "st_ctime_ns" in o)
chk("   mutation detail leaks no value bytes", FAKE32a not in o and FAKE64 not in o)

# declared size larger than readable bytes
fo = FakeOS()
fo.add_dir("/run")
fo.add_file("/run/x.in", GOOD)
mod.os = fo
real_fstat = fo.fstat
def short_fstat(fd):
    st = real_fstat(fd)
    st.st_size = 400
    return st
fo.fstat = short_fstat
reset_run()
rc, o = quiet(lambda: mod.read_input("/run/x.in"))
mod.os = real_os
r = rep(o)
chk("read shorter than declared size -> S0_IN_READ_LEN", r.get("PRIMARY_CODE") == "S0_IN_READ_LEN", r.get("PRIMARY_CODE", "?"))

# fail closed when the platform lacks the pinning flags
class NoFollowOS(FakeOS):
    O_NOFOLLOW = None
    O_DIRECTORY = None
    def __getattribute__(self, item):
        if item in ("O_NOFOLLOW", "O_DIRECTORY"):
            raise AttributeError(item)
        return object.__getattribute__(self, item)
nfo = NoFollowOS()
nfo.add_dir("/run")
nfo.add_file("/run/x.in", GOOD)
mod.os = nfo
reset_run()
rc, o = quiet(lambda: mod.read_input("/run/x.in"))
mod.os = real_os
r = rep(o)
chk("missing O_DIRECTORY/O_NOFOLLOW -> S0_PLATFORM (fail closed)",
    r.get("PRIMARY_CODE") == "S0_PLATFORM", r.get("PRIMARY_CODE", "?"))

# --------------------------------------------------------------------------- C
print("LAYER C: END-TO-END main() IN MODE")
real_read_input = mod.read_input
def plain_reader(path):
    # Faithful stand-in for read_input on Windows: same return shape, and the same
    # absent-file -> S0_IN_ABSENT mapping (the real mapping is proven in Layer B).
    if not os.path.exists(path):
        mod.fail("S0_IN_ABSENT", "")
    with open(path, "rb") as f:
        data = f.read()
    st = os.stat(path)
    return data, st, st
def bind_stubs(m):
    def reader(path):
        if not os.path.exists(path):
            m.fail("S0_IN_ABSENT", "")
        with open(path, "rb") as f:
            data = f.read()
        st = os.stat(path)
        return data, st, st
    m.read_input = reader
    m.input_dir_ok = lambda *a: None
    m.input_attr_ok = lambda *a: None
    m.perm_ok = lambda *a: True

bind_stubs(mod)

print("C1 happy path (perm_ok stubbed so the Linux-only 0600 gate can be passed here)")
put_in(GOOD)
clean_tmp()
n_before = len(os.listdir(root))
mod.perm_ok = lambda m, u, g: True
reset_run()
rc, o = quiet(mod.main)
r = rep(o)
chk("A1_RESULT=PASS", r.get("A1_RESULT") == "PASS", r.get("A1_RESULT", "?"))
body = open(TMPF, 'rb').read() if os.path.exists(TMPF) else b""
chk("TMP bytes == IN bytes exactly", body == GOOD)
chk("STAGING_SIZE == 206", r.get("STAGING_SIZE") == "206", r.get("STAGING_SIZE", "?"))
chk("STAGING_SHA256 == sha256(IN)", r.get("STAGING_SHA256") == hashlib.sha256(GOOD).hexdigest())
chk("STAGING_MATCHES_INPUT_BYTES=True", r.get("STAGING_MATCHES_INPUT_BYTES") == "True")
chk("INPUT_FSTYPE=tmpfs", r.get("INPUT_FSTYPE") == "tmpfs", r.get("INPUT_FSTYPE", "?"))
chk("INPUT_SIZE=206", r.get("INPUT_SIZE") == "206", r.get("INPUT_SIZE", "?"))
chk("INPUT_SHA256 reported", r.get("INPUT_SHA256") == hashlib.sha256(GOOD).hexdigest())
chk("INPUT_RETAINED line present", "INPUT_RETAINED" in o)
chk("IN still on disk and unchanged", open(INF, 'rb').read() == GOOD and os.path.exists(INF))
chk("DIR_ENTRIES grows by exactly one", r.get("DIR_ENTRIES_BEFORE") == str(n_before)
    and r.get("DIR_ENTRIES_AFTER") == str(n_before + 1),
    "%s->%s expected %s->%s" % (r.get("DIR_ENTRIES_BEFORE"), r.get("DIR_ENTRIES_AFTER"),
                               n_before, n_before + 1))
chk("ENV unchanged", hashlib.sha256(open(ENV, 'rb').read()).hexdigest() == env0)
chk("ENV_STAT_UNCHANGED=True", r.get("ENV_STAT_UNCHANGED") == "True")
chk("no value bytes in report", FAKE32a not in o and FAKE64 not in o and FAKE32b not in o)
chk("no head4/tail4 fields", "head4" not in o and "tail4" not in o)
chk("SAME_AS_CURRENT_ENV ACCESS_KEY=NO", "SAME_AS_CURRENT_ENV CLOUDFLARE_R2_ACCESS_KEY=NO" in o)
chk("PLAINTEXT_COPIES_LIVE reported", "PLAINTEXT_COPIES_LIVE" in o)
chk("STOP_HERE present", "STOP_HERE" in o)
clean_tmp()

print("C2 real 0600 gate still fires where the OS cannot express it")
mod.perm_ok = REAL_PERM_OK
reset_run()
rc, o = quiet(mod.main)
r = rep(o)
chk("Windows mode -> S1_TMP_PERM and self-cleanup", r.get("PRIMARY_CODE") == "S1_TMP_PERM", r.get("PRIMARY_CODE", "?"))
chk("no leftover after that failure", not os.path.exists(TMPF), o[-200:])
chk("IN preserved after failure", open(INF, 'rb').read() == GOOD)

print("C3 IN == TMP is refused before anything else")
mod.IN = mod.TMP
reset_run()
rc, o = quiet(mod.main)
r = rep(o)
chk("S0_IN_EQ_TMP", r.get("PRIMARY_CODE") == "S0_IN_EQ_TMP", r.get("PRIMARY_CODE", "?"))
chk("no TMP created", not os.path.exists(TMPF))
mod.IN = INF

print("C4 non-tmpfs mount is refused, with no silent fallback")
with open(MNT, "w", newline="\n") as f:
    f.write("dev %s ext4 rw 0 0\n" % root)
reset_run()
rc, o = quiet(mod.main)
r = rep(o)
chk("S0_IN_FSTYPE", r.get("PRIMARY_CODE") == "S0_IN_FSTYPE", r.get("PRIMARY_CODE", "?"))
chk("DETAIL reports the observed fstype", r.get("DETAIL") == "fstype=ext4", r.get("DETAIL", "?"))
chk("no TMP created", not os.path.exists(TMPF))
chk("IN untouched", open(INF, 'rb').read() == GOOD)
with open(MNT, "w", newline="\n") as f:
    f.write("tmpfs %s tmpfs rw,nosuid 0 0\n" % root)

print("C5 malformed IN through the full pipeline")
for label, data, code in [
        ("205 bytes", GOOD[:-1], "S0_IN_FORMAT"),
        ("207 bytes", GOOD + b"z", "S0_IN_FORMAT"),
        ("uppercase", GOOD.replace(FAKE32a.encode(), b"F" * 32), "S0_IN_FORMAT"),
        ("wrong order", ("CLOUDFLARE_R2_ACCESS_KEY=%s\nCLOUDFLARE_R2_ACCOUNT_ID=%s\n"
                         "CLOUDFLARE_R2_SECRET_KEY=%s\n" % (FAKE32b, FAKE32a, FAKE64)).encode(), "S0_IN_FORMAT"),
        ("export prefix", GOOD.replace(b"CLOUDFLARE_R2_ACCOUNT_ID", b"export CLOUDFLARE_R2_ACCOUNT_I", 1), "S0_IN_FORMAT"),
        ("CR line endings", GOOD.replace(b"\n", b"\r\n"), "S0_IN_FORMAT")]:
    put_in(data)
    reset_run()
    rc, o = quiet(mod.main)
    r = rep(o)
    chk("main %s -> %s" % (label, code), r.get("PRIMARY_CODE") == code, r.get("PRIMARY_CODE", "?"))
    chk("   no TMP created for %s" % label, not os.path.exists(TMPF))
    chk("   no value bytes in output", FAKE32a not in o and FAKE64 not in o and "f" * 8 not in o)
    chk("   ENV untouched", hashlib.sha256(open(ENV, 'rb').read()).hexdigest() == env0)
    clean_tmp()

print("C6 absent IN")
if os.path.exists(INF):
    os.remove(INF)
reset_run()
rc, o = quiet(mod.main)
mod_perm = None
r = rep(o)
chk("absent IN stops A1 with an S0_IN_* code",
    r.get("PRIMARY_CODE", "").startswith("S0_IN"), r.get("PRIMARY_CODE", "?"))
chk("no TMP created", not os.path.exists(TMPF))
put_in(GOOD)

print("C7 the new-vs-current gate survives the IN port")
put_in(("CLOUDFLARE_R2_ACCOUNT_ID=%s\nCLOUDFLARE_R2_ACCESS_KEY=%s\nCLOUDFLARE_R2_SECRET_KEY=%s\n"
        % (FAKE32a, DEAD, FAKE64)).encode())
reset_run()
rc, o = quiet(mod.main)
r = rep(o)
chk("S1_NOT_NEW_KEY when ACCESS_KEY equals deployed value",
    r.get("PRIMARY_CODE") == "S1_NOT_NEW_KEY", r.get("PRIMARY_CODE", "?"))
chk("no TMP created", not os.path.exists(TMPF))
put_in(GOOD)

# --------------------------------------------------------------------------- D
print("LAYER D: TMP LIFECYCLE INVARIANTS (unchanged semantics)")
mod.perm_ok = lambda m, u, g: True
real_cleanup = mod.cleanup_ours
LIVE = GOOD
gs_len = len(LIVE)
gs_sha = hashlib.sha256(LIVE).hexdigest()

def cleanup_case(label, created_flag, want_inode, size_state, expect):
    clean_tmp()
    mod.created = created_flag
    if size_state is not None:
        with open(TMPF, "wb") as f:
            f.write(size_state)
        ino = os.stat(TMPF).st_ino if want_inode is None else want_inode
        mod.rec = (ino, gs_len, gs_sha)
    else:
        mod.rec = (0, gs_len, gs_sha)
    got = mod.cleanup_ours()
    chk(label + " -> " + expect, got == expect, got)

cleanup_case("not created this run", False, None, LIVE, "NO_TMP_BY_THIS_RUN")
clean_tmp()
cleanup_case("absent file", True, None, None, "ALREADY_ABSENT")
with open(TMPF, "wb") as f:
    f.write(LIVE)
mod.created = True
mod.rec = (os.stat(TMPF).st_ino + 999999, gs_len, gs_sha)
chk("inode mismatch -> CLEANUP_NOT_OURS:inode", mod.cleanup_ours() == "CLEANUP_NOT_OURS:inode")
chk("   foreign content preserved", os.path.exists(TMPF))
mod.rec = (os.stat(TMPF).st_ino, gs_len + 1, gs_sha)
chk("size mismatch (using len+1, no magic constant) -> CLEANUP_NOT_OURS:size",
    mod.cleanup_ours() == "CLEANUP_NOT_OURS:size")
mod.rec = (os.stat(TMPF).st_ino, gs_len, "0" * 64)
chk("sha mismatch -> CLEANUP_NOT_OURS:sha", mod.cleanup_ours() == "CLEANUP_NOT_OURS:sha")
chk("   content preserved on sha mismatch", open(TMPF, 'rb').read() == LIVE)
os.remove(TMPF)
with open(TMPF, "wb") as f:
    f.write(b"")
mod.created = True
mod.rec = (os.stat(TMPF).st_ino, gs_len, gs_sha)
chk("size=0 (nothing written yet) is NOT deleted", mod.cleanup_ours() == "CLEANUP_NOT_OURS:size")
chk("   half-written file preserved", os.path.exists(TMPF))
os.remove(TMPF)
with open(TMPF, "wb") as f:
    f.write(LIVE)
mod.created = True
mod.rec = (os.stat(TMPF).st_ino, gs_len, gs_sha)
chk("full triple match -> DELETED_AND_VERIFIED", mod.cleanup_ours() == "DELETED_AND_VERIFIED")
chk("   file gone", not os.path.exists(TMPF))

print("IN can never be deleted by cleanup_ours")
clean_tmp()
put_in(GOOD)
mod.created = True
mod.rec = (os.stat(INF).st_ino, len(GOOD), hashlib.sha256(GOOD).hexdigest())
st = mod.cleanup_ours()
chk("even if rec is filled with IN's facts, IN survives", os.path.exists(INF) and open(INF, 'rb').read() == GOOD)
chk("   and cleanup reports no TMP (it looks only at TMP)", st in ("ALREADY_ABSENT",), st)
chk("   source contains no unlink(IN)", "os.unlink(IN)" not in src and "os.remove(IN)" not in src)

print("is_residue truth table")
for st_val, e in [("CLEANUP_NOT_OURS:inode", True), ("CLEANUP_NOT_OURS:size", True),
                  ("CLEANUP_NOT_OURS:sha", True), ("CLEANUP_RESIDUE:13", True),
                  ("CLEANUP_UNREADABLE:2", True), ("DELETED_AND_VERIFIED", False),
                  ("NO_TMP_BY_THIS_RUN", False), ("ALREADY_ABSENT", False)]:
    chk("is_residue(%s) == %s" % (st_val, e), mod.is_residue(st_val) is e)

print("residue propagation through fail()")
mod.created = True
with open(TMPF, "wb") as f:
    f.write(b"")
mod.rec = (os.stat(TMPF).st_ino, gs_len, gs_sha)
rc, o = quiet(lambda: mod.fail("S1_WRITE", "28"))
r = rep(o)
chk("fail() reports CLEANUP_NOT_OURS:size", r.get("CLEANUP_STATUS") == "CLEANUP_NOT_OURS:size", r.get("CLEANUP_STATUS", "?"))
chk("fail() sets RESIDUE_PENDING_AUTHORITY=YES", r.get("RESIDUE_PENDING_AUTHORITY") == "YES")
chk("fail() detail is errno only", r.get("DETAIL") == "28", r.get("DETAIL", "?"))
chk("ENV_MODIFIED measured, not asserted", r.get("ENV_MODIFIED") == "NO", r.get("ENV_MODIFIED", "?"))
clean_tmp()
with open(TMPF, "wb") as f:
    f.write(LIVE)
mod.created = True
mod.rec = (os.stat(TMPF).st_ino, gs_len, gs_sha)
rc, o = quiet(lambda: mod.fail("S1_TMP_SHA", "readback sha mismatch"))
r = rep(o)
chk("fail() deletes when triple matches", r.get("CLEANUP_STATUS") == "DELETED_AND_VERIFIED", r.get("CLEANUP_STATUS", "?"))
chk("no residue flag on verified deletion", "RESIDUE_PENDING_AUTHORITY" not in o)

print("write-error classification")
WRITE_LINE = "        write_all(fd, payload)"
def run_variant(old, new):
    v = src.replace(WRITE_LINE, old, 1).replace(old, new, 1)
    assert new in v and WRITE_LINE not in v
    mm = types.ModuleType("vv")
    mm.__dict__["__name__"] = "not_main"        # exec must NOT auto-run main()
    exec(compile(v, "variant.py", "exec"), mm.__dict__)
    bind_stubs(mm)                              # stubs before any execution
    put_in(GOOD)
    clean_tmp()
    rc2, out = quiet(mm.main)
    return rep(out), out


DEL_LINE = "    del payload          # written and hashed; no longer needed (best-effort hygiene)"
r_rt, o_rt = run_variant(WRITE_LINE, "        raise RuntimeError('leak_probe ' + repr(payload))")
chk("RuntimeError during write -> PRIMARY_CODE=S1_WRITE_SHORT",
    r_rt.get("PRIMARY_CODE") == "S1_WRITE_SHORT", r_rt.get("PRIMARY_CODE", "?"))
chk("   DETAIL is the fixed constant",
    r_rt.get("DETAIL") == "write_all_short_or_incomplete", r_rt.get("DETAIL", "?"))
chk("   no exception text or payload in output",
    "leak_probe" not in o_rt and FAKE32a not in o_rt and FAKE64 not in o_rt)
chk("   no TMP left behind (strict triple refused a half-written file)",
    r_rt.get("CLEANUP_STATUS") in ("CLEANUP_NOT_OURS:size", "DELETED_AND_VERIFIED"),
    r_rt.get("CLEANUP_STATUS", "?"))
chk("   residue authority declared when undeletable",
    (r_rt.get("CLEANUP_STATUS") == "DELETED_AND_VERIFIED") or r_rt.get("RESIDUE_PENDING_AUTHORITY") == "YES")
chk("   IN preserved on the short-write path", open(INF, 'rb').read() == GOOD)
chk("   ENV untouched on the short-write path",
    hashlib.sha256(open(ENV, 'rb').read()).hexdigest() == env0)
clean_tmp()

r_os, o_os = run_variant(WRITE_LINE, "        raise OSError(28, 'leak_probe ' + repr(payload))")
chk("OSError during write -> PRIMARY_CODE=S1_WRITE", r_os.get("PRIMARY_CODE") == "S1_WRITE", r_os.get("PRIMARY_CODE", "?"))
chk("   DETAIL is errno only", r_os.get("DETAIL") == "28", r_os.get("DETAIL", "?"))
chk("   no exception text or payload in output", "leak_probe" not in o_os and FAKE32a not in o_os)
chk("   no path in DETAIL", "r2pair" not in r_os.get("DETAIL", ""), r_os.get("DETAIL", "?"))
clean_tmp()

print("BaseException guard still cleans up a fully written, triple-matched staging")
guard_src = src.replace("import hashlib", "import hashlib\nRAISER = lambda p: (_ for _ in ()).throw(ValueError('leak_probe ' + repr(p)))\n", 1)
guard_src = guard_src.replace(DEL_LINE, "    RAISER(payload); " + DEL_LINE, 1)
NL = chr(10)
ANCHOR = 'if __name__ == "__main__":' + NL + '    try:' + NL + '        main()'
PRELUDE = chr(10).join([
    'if __name__ == "__main__":',
    '    input_dir_ok = lambda *a: None',
    '    input_attr_ok = lambda *a: None',
    '    perm_ok = lambda *a: True',
    '    def read_input(path):',
    '        _d = open(path, "rb").read()',
    '        _s = os.stat(path)',
    '        return _d, _s, _s',
    '    try:',
    '        main()',
])
assert ANCHOR in guard_src, "guard anchor not found"
guard_src = guard_src.replace(ANCHOR, PRELUDE, 1)
assert "RAISER(payload)" in guard_src
gmod = types.ModuleType("g")
gmod.__dict__["__name__"] = "__main__"
rcg, og = quiet(lambda: exec(compile(guard_src, "guard.py", "exec"), gmod.__dict__))
rg = rep(og)
chk("guard fired: PRIMARY_CODE=S1_UNEXPECTED", rg.get("PRIMARY_CODE") == "S1_UNEXPECTED", rg.get("PRIMARY_CODE", "?"))
chk("only the exception class is reported", rg.get("EXCEPTION_CLASS") == "ValueError", rg.get("EXCEPTION_CLASS", "?"))
chk("no payload/exception text leaked", "leak_probe" not in og and FAKE32a not in og and FAKE64 not in og)
chk("staging removed via strict triple", rg.get("CLEANUP_STATUS") == "DELETED_AND_VERIFIED", rg.get("CLEANUP_STATUS", "?"))
chk("no residue", not os.path.exists(TMPF))
chk("IN survived the crash", open(INF, 'rb').read() == GOOD)
chk("ENV untouched by the crash path", hashlib.sha256(open(ENV, 'rb').read()).hexdigest() == env0)

mod.read_input = real_read_input
clean_tmp()
if os.path.exists(INF):
    os.remove(INF)

print("\nSTATIC ASSERTIONS")
for k, want in [("getpass", 0), ("sys.argv", 0), ("os.unlink(IN)", 0), ("os.remove(IN)", 0),
                ("os.replace(", 0), ("os.rename(", 0), ("str(e)", 0), ("DELETED_EMPTY_UNWRITTEN", 0),
                ("st_size == 0", 0)]:
    chk("source %r count == %d" % (k, want), src.count(k) == want, str(src.count(k)))
chk("IN_BYTES constant is 206", "IN_BYTES = 206" in src)
chk("no 129 constant anywhere", "129" not in src)
for banned in ("socket", "ssl", "urllib", "http", "requests", "boto3", "botocore", "subprocess",
               "shutil", "tempfile", "eval(", "exec(", "os.system", "popen"):
    chk("no %r in source" % banned, banned not in src)
chk("backend.env only opened read-only", src.count('"rb"') == 2 and 'open(ENV, "rb")' in src)
chk("single unlink site, inside cleanup_ours", src.count("os.unlink") == 1)
chk("IN never chmod/chown'd", "chmod(IN" not in src and "chown(IN" not in src)
chk("O_EXCL still the only TMP create", src.count("os.O_EXCL") == 1)
chk("strict triple gates present", all(x in src for x in ["st.st_ino != rec[0]", "st.st_size != rec[1]", "actual != rec[2]"]))

shutil.rmtree(root.replace("/", "\\"), ignore_errors=True)
print("\nSUITE: " + ("ALL CHECKS PASS" if ok else "*** SOME CHECKS FAILED ***"))
sys.exit(0 if ok else 1)
