#!/usr/bin/env python3
"""A1 (IN mode): read the new Cloudflare R2 triple from a pre-staged, root-only,
READ-ONLY input file, validate it byte-strictly, and write it to the A1 staging file
as the single new plaintext object this run is allowed to create.

    IN (/run/melovar-r2pair.in)  --read-only-->  memory payload  --O_EXCL-->  TMP
    backend.env is never opened for writing; there is no os.replace/os.rename here.

Within this script's control the values never reach argv, shell history, stdin,
the process's own stdout/stderr, any file other than the staging file, or backend.env.
This script CANNOT guarantee anything about the client host: whoever created IN may have
typed it under a terminal recorder, screen capture, keylogger or host audit agent.
IN is never created, modified, chmod'ed, chowned, renamed or deleted by this script.
"""
import hashlib
import os
import re
import sys
import time

ENV = "/opt/melovar/secrets/backend.env"
TMP = "/opt/melovar/secrets/.r2pair.tmp"
DIR = "/opt/melovar/secrets"
SPEC = (("CLOUDFLARE_R2_ACCOUNT_ID", 32),
        ("CLOUDFLARE_R2_ACCESS_KEY", 32),
        ("CLOUDFLARE_R2_SECRET_KEY", 64))

# ---- A1 input file (read-only; never created or destroyed by this script) --------
IN = "/run/melovar-r2pair.in"
MOUNTS = "/proc/mounts"
IN_KEYS = ("CLOUDFLARE_R2_ACCOUNT_ID",
           "CLOUDFLARE_R2_ACCESS_KEY",
           "CLOUDFLARE_R2_SECRET_KEY")
IN_VAL_LENS = (32, 32, 64)
IN_BYTES = 206          # 58 + 58 + 90, each line KEY=value+LF, final LF required
IN_UID = 0
IN_GID = 0
IN_MODE = 0o400
IN_DIR_MODE_DENY = 0o022
IN_READ_CAP = 1 << 20   # defensive bound; a legit IN is exactly IN_BYTES

S_IFMT = 0o170000
S_IFREG = 0o100000
S_IFDIR = 0o040000
ELOOP = 40

created = False
rec = (None, None, None)          # (inode, size, sha256) of TMP, proven to be ours
env_sha_before = None


def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def parse_env(text):
    cur = {}
    for line in text.split("\n"):
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", line)
        if m:
            cur[m.group(1)] = m.group(2)
    return cur


def is_hex_len(v, n):
    return len(v) == n and re.fullmatch(r"[0-9a-f]{%d}" % n, v) is not None


def input_dir_ok(mode, uid, gid):
    """Pure predicate: the directory holding IN must be a root-owned dir that nobody
    else can write into, or path substitution defeats every other check."""
    if (mode & S_IFMT) != S_IFDIR:
        return "S0_IN_DIR_NOT_DIR"
    if uid != 0 or gid != 0:
        return "S0_IN_DIR_OWNER"
    if mode & IN_DIR_MODE_DENY:
        return "S0_IN_DIR_WRITABLE"
    return None


def input_attr_ok(mode, uid, gid, nlink):
    """Pure predicate: IN must be a single-linked, root-owned, 0400 regular file.
    nlink != 1 means a second name can change the bytes we are reading; a non-regular
    file can block, yield kernel-generated content, or be a redirection trick."""
    if (mode & S_IFMT) != S_IFREG:
        return "S0_IN_NOT_REGULAR"
    if uid != IN_UID or gid != IN_GID:
        return "S0_IN_OWNER"
    if (mode & 0o777) != IN_MODE:
        return "S0_IN_MODE"
    if nlink != 1:
        return "S0_IN_NLINK"
    return None


STAT_FIELDS = ("st_ino", "st_size", "st_nlink", "st_uid", "st_gid",
               "st_mode", "st_mtime_ns", "st_ctime_ns")


def st_delta(st1, st2):
    """Pure predicate: names of stat fields that changed across the read.
    mtime_ns/ctime_ns are included so an in-place rewrite of the SAME size is caught."""
    return [f for f in STAT_FIELDS if getattr(st1, f, None) != getattr(st2, f, None)]


def mount_fstype(path, mounts=None):
    """Longest-mount-point match in /proc/mounts; returns the filesystem type, or '?'
    when it cannot be determined. Used only to classify volatility of IN, never for
    integrity, so a '?' must fail closed rather than be assumed safe."""
    mounts = MOUNTS if mounts is None else mounts
    best_len = -1
    best_fst = "?"
    try:
        with open(mounts, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                parts = line.split()
                if len(parts) < 3:
                    continue
                mp, fst = parts[1], parts[2]
                if path == mp or path.startswith(mp.rstrip("/") + "/"):
                    if len(mp) > best_len:
                        best_len, best_fst = len(mp), fst
    except OSError:
        return "?"
    return best_fst


def parse_input_strict(data):
    """Byte-exact format gate. Never echoes value bytes: details carry only indices,
    key names from our own whitelist, and counts."""
    if len(data) != IN_BYTES:
        fail("S0_IN_FORMAT", "bytes=%d expected=%d" % (len(data), IN_BYTES))
    if data[:3] == b"\xef\xbb\xbf":
        fail("S0_IN_FORMAT", "BOM")
    if b"\r" in data:
        fail("S0_IN_FORMAT", "CR_present")
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError:
        fail("S0_IN_FORMAT", "non_ascii")
    if not text.endswith("\n"):
        fail("S0_IN_FORMAT", "missing_final_LF")
    if text.endswith("\n\n"):
        fail("S0_IN_FORMAT", "blank_line")
    parts = text.split("\n")
    if len(parts) != 4 or parts[3] != "":
        fail("S0_IN_FORMAT", "lines=%d expected=3" % (len(parts) - 1))
    keys = []
    vals = {}
    for i, ln in enumerate(parts[:3]):
        if ln == "":
            fail("S0_IN_FORMAT", "blank_line_at=%d" % i)
        if "=" not in ln:
            fail("S0_IN_FORMAT", "no_eq_at=%d" % i)
        k, v = ln.split("=", 1)
        keys.append(k)
        if k != IN_KEYS[i]:
            fail("S0_IN_FORMAT", "key_at=%d expected=%s found_len=%d" % (i, IN_KEYS[i], len(k)))
        if v != v.strip():
            fail("S0_IN_FORMAT", "whitespace_at=%d (not auto-trimmed)" % i)
        if not is_hex_len(v, IN_VAL_LENS[i]):
            fail("S0_IN_FORMAT", "value_shape_at=%d len=%d lower_hex=%s" % (
                i, len(v), bool(re.fullmatch(r"[0-9a-f]+", v))))
        vals[k] = v
    if len(set(keys)) != len(keys):
        fail("S0_IN_FORMAT", "duplicate_keys")
    if keys != list(IN_KEYS):
        fail("S0_IN_FORMAT", "key_order")
    return vals


def read_input(path):
    """Read IN exactly once, pinned to its parent-directory fd. Read-only by
    construction: no O_CREAT, no O_TRUNC, no write flag, no second pathname open."""
    dflag = getattr(os, "O_DIRECTORY", None)
    nflag = getattr(os, "O_NOFOLLOW", None)
    if dflag is None or nflag is None:
        fail("S0_PLATFORM", "O_DIRECTORY_or_O_NOFOLLOW_unavailable")

    dname = os.path.dirname(path) or "/"
    base = os.path.basename(path)

    try:
        dfd = os.open(dname, os.O_RDONLY | dflag | nflag)
    except OSError as e:
        fail("S0_IN_DIR_OPEN", str(getattr(e, "errno", "?")))
    try:
        ds = os.fstat(dfd)
        code = input_dir_ok(ds.st_mode, ds.st_uid, ds.st_gid)
        if code:
            fail(code, "dir=%s" % dname)
        try:
            fd = os.open(base, os.O_RDONLY | nflag, dir_fd=dfd)
        except FileNotFoundError:
            fail("S0_IN_ABSENT", "")
        except OSError as e:
            if getattr(e, "errno", None) == ELOOP:
                fail("S0_IN_SYMLINK", "")
            fail("S0_IN_OPEN", str(getattr(e, "errno", "?")))
        try:
            st1 = os.fstat(fd)
            code = input_attr_ok(st1.st_mode, st1.st_uid, st1.st_gid, st1.st_nlink)
            if code:
                fail(code, "")
            chunks = []
            got = 0
            while True:
                try:
                    blk = os.read(fd, 65536)
                except InterruptedError:
                    continue
                except OSError as e:
                    fail("S0_IN_READ", str(getattr(e, "errno", "?")))
                if not blk:
                    break
                got += len(blk)
                chunks.append(blk)
                if got > IN_READ_CAP:
                    fail("S0_IN_FORMAT", "oversized_gt_cap=%d" % IN_READ_CAP)
            st2 = os.fstat(fd)
            data = b"".join(chunks)
        finally:
            os.close(fd)
    finally:
        os.close(dfd)

    if got != st1.st_size:
        fail("S0_IN_READ_LEN", "read=%d fstat_size=%d" % (got, st1.st_size))
    changed = st_delta(st1, st2)
    if changed:
        fail("S0_IN_MUTATED", "changed=%s" % ",".join(changed))
    return data, st1, st2


def write_all(fd, data):
    mv = memoryview(data)
    wrote = 0
    while wrote < len(data):
        try:
            n = os.write(fd, mv[wrote:])
        except InterruptedError:
            continue
        if n is None or n <= 0:
            raise RuntimeError("short_write wrote=%d expected=%d n=%r" % (wrote, len(data), n))
        wrote += n
    if wrote != len(data):
        raise RuntimeError("short_write wrote=%d expected=%d" % (wrote, len(data)))


def perm_ok(mode, uid, gid):
    """Staging must be 0600 and owned by root:root before it is accepted."""
    return (mode & 0o777) == 0o600 and uid == 0 and gid == 0


def ownership_ok(want_inode, want_size, want_sha, st, actual_sha):
    """Triple match: inode AND size AND sha. 'Path exists' is never sufficient."""
    return (st.st_ino == want_inode and st.st_size == want_size and actual_sha == want_sha)


def cleanup_ours():
    """Delete a staging file ONLY on the strict triple: inode AND size AND SHA256.
    No special case, no exception. 'The path exists' is never a deletion basis, and a
    half-written file we probably created is still left alone and reported as residue."""
    if not created:
        return "NO_TMP_BY_THIS_RUN"
    try:
        st = os.stat(TMP)
    except FileNotFoundError:
        return "ALREADY_ABSENT"
    except OSError as e:
        return "CLEANUP_UNREADABLE:%s" % getattr(e, "errno", "?")
    if st.st_ino != rec[0]:
        return "CLEANUP_NOT_OURS:inode"
    if st.st_size != rec[1]:
        return "CLEANUP_NOT_OURS:size"
    try:
        actual = sha256_file(TMP)
    except OSError as e:
        return "CLEANUP_UNREADABLE:%s" % getattr(e, "errno", "?")
    if actual != rec[2]:
        return "CLEANUP_NOT_OURS:sha"
    try:
        os.unlink(TMP)
    except OSError as e:
        return "CLEANUP_RESIDUE:%s" % getattr(e, "errno", "?")
    return "DELETED_AND_VERIFIED" if not os.path.exists(TMP) else "CLEANUP_RESIDUE:still_present"


def is_residue(status):
    """Anything that did NOT end in a verified deletion leaves an authority problem."""
    return (status.startswith("CLEANUP_NOT_OURS")
            or status.startswith("CLEANUP_RESIDUE")
            or status.startswith("CLEANUP_UNREADABLE"))


def fail(code, detail=""):
    status = cleanup_ours()
    sys.stdout.write("A1_RESULT=FAIL\n")
    sys.stdout.write("PRIMARY_CODE=%s\n" % code)
    sys.stdout.write("DETAIL=%s\n" % detail)
    sys.stdout.write("CLEANUP_STATUS=%s\n" % status)
    if is_residue(status):
        sys.stdout.write("RESIDUE_PENDING_AUTHORITY=YES\n")
    if env_sha_before is not None:
        try:
            now = sha256_file(ENV)
        except OSError as e:
            now = "UNREADABLE:%s" % getattr(e, "errno", "?")
        sys.stdout.write("ENV_MODIFIED=%s\n" % ("NO" if now == env_sha_before else "YES_UNEXPECTED"))
        sys.stdout.write("ENV_SHA256_NOW=%s\n" % now)
        sys.stdout.write("ENV_SHA256_BASELINE=%s\n" % env_sha_before)
    else:
        sys.stdout.write("ENV_MODIFIED=NOT_MEASURED (baseline was never read)\n")
    raise SystemExit(1)


def main():
    global created, rec, env_sha_before

    # ---- S0: read-only baseline, before anything is created ---------------------
    if os.path.exists(TMP):
        try:
            st = os.stat(TMP)
            desc = "inode=%d size=%d mode=%04o uid=%d gid=%d mtime=%s" % (
                st.st_ino, st.st_size, st.st_mode & 0o777, st.st_uid, st.st_gid,
                time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime)))
        except OSError as e:
            desc = "stat_failed:%s" % getattr(e, "errno", "?")
        # Pre-existing staging is NEVER this run's object: report and stop, do not delete.
        sys.stdout.write("PREEXISTING_STAGING=%s\n" % desc)
        fail("S1_TMP_PREEXISTING", "path already exists; not created by this run")

    try:
        dir_before = len(os.listdir(DIR))
    except OSError as e:
        fail("S0_DIR", getattr(e, "errno", "?"))
    try:
        env_sha_before = sha256_file(ENV)
        est = os.stat(ENV)
    except OSError as e:
        fail("S0_ENV_READ", getattr(e, "errno", "?"))
    try:
        with open(ENV, "rb") as f:
            cur = parse_env(f.read().decode("utf-8", "replace"))
    except OSError as e:
        fail("S0_ENV_PARSE", getattr(e, "errno", "?"))

    sys.stdout.write("S0_ENV_SHA256=%s\n" % env_sha_before)
    sys.stdout.write("S0_ENV_STAT=perm=%04o owner=%d:%d size=%d inode=%d\n" % (
        est.st_mode & 0o777, est.st_uid, est.st_gid, est.st_size, est.st_ino))
    sys.stdout.write("S0_DIR_ENTRIES=%d\n" % dir_before)

    # ---- S0 IN: distinct path, volatile-storage class, then read-only ingest ----
    if os.path.realpath(IN) == os.path.realpath(TMP):
        fail("S0_IN_EQ_TMP", "IN and TMP must be different paths")
    fstype = mount_fstype(IN)
    sys.stdout.write("INPUT_PATH=%s\n" % IN)
    sys.stdout.write("INPUT_FSTYPE=%s\n" % fstype)
    if fstype != "tmpfs":
        # No silent fallback to a persistent path: that would add an unbounded-life
        # plaintext copy without anyone deciding to accept it.
        fail("S0_IN_FSTYPE", "fstype=%s" % fstype[:16])

    data, ist1, ist2 = read_input(IN)
    input_sha = sha_bytes(data)
    vals = parse_input_strict(data)
    # `data` must stay alive until the payload has been compared against it below.
    sys.stdout.write("INPUT_INODE=%d\n" % ist1.st_ino)
    sys.stdout.write("INPUT_SIZE=%d\n" % ist1.st_size)
    sys.stdout.write("INPUT_SHA256=%s\n" % input_sha)
    sys.stdout.write("INPUT_MODE=%04o INPUT_OWNER=%d:%d INPUT_NLINK=%d\n" % (
        ist1.st_mode & 0o777, ist1.st_uid, ist1.st_gid, ist1.st_nlink))
    sys.stdout.write("INPUT_RETAINED=YES (A1 never deletes IN)\n")

    # ---- refuse to stage a credential that is not actually new ------------------
    for name, _ in SPEC:
        if name in cur and cur[name] == vals[name]:
            sys.stdout.write("SAME_AS_CURRENT_ENV %s=YES\n" % name)
        else:
            sys.stdout.write("SAME_AS_CURRENT_ENV %s=NO\n" % name)
    if cur.get("CLOUDFLARE_R2_ACCESS_KEY") == vals["CLOUDFLARE_R2_ACCESS_KEY"]:
        fail("S1_NOT_NEW_KEY", "access key equals the value already deployed (known-dead)")
    # cur held every value parsed from backend.env (all 52 keys, most of them secrets).
    # It was needed only for the comparison above, so release it before anything else.
    del cur

    payload = "".join("%s=%s\n" % (k, vals[k]) for k, _ in SPEC).encode("ascii")
    expected_sha = sha_bytes(payload)
    # The payload is rebuilt from parsed values, so it must reproduce the bytes we read
    # exactly. Any difference means the parser normalized something it must not touch.
    if len(payload) != IN_BYTES:
        fail("S1_PAYLOAD_LEN", "payload=%d expected=%d" % (len(payload), IN_BYTES))
    if payload != data:
        fail("S1_PAYLOAD_NE_INPUT", "rebuilt payload differs from input bytes")
    # Drop the containers that hold the entered values. This is best-effort hygiene,
    # not a guarantee: CPython str/bytes are immutable, may be interned or copied,
    # and are not zeroed on free.
    del data
    del vals

    # ---- create staging with O_EXCL, then canonical lifecycle -------------------
    # fsync(fd) -> close(fd) -> chmod -> chown -> stat -> PERM -> SHA
    try:
        fd = os.open(TMP, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
    except FileExistsError:
        fail("S1_TMP_PREEXISTING", "O_EXCL refused: created by someone else")
    except OSError as e:
        fail("S1_OPEN", "%s" % getattr(e, "errno", "?"))

    created = True
    ts = os.fstat(fd)
    rec = (ts.st_ino, len(payload), expected_sha)
    try:
        write_all(fd, payload)
        os.fsync(fd)
    except OSError as e:
        os.close(fd)
        fail("S1_WRITE", str(getattr(e, "errno", "?")))
    except RuntimeError:
        # write_all() own short-write/incomplete detection. Fixed constant detail only:
        # no exception text, no path, no payload, no errno (it has none).
        os.close(fd)
        fail("S1_WRITE_SHORT", "write_all_short_or_incomplete")
    os.close(fd)
    del payload          # written and hashed; no longer needed (best-effort hygiene)

    try:
        os.chmod(TMP, 0o600)
        os.chown(TMP, 0, 0)
        st = os.stat(TMP)
    except OSError as e:
        fail("S1_PERM_SET", str(getattr(e, "errno", "?")))

    if not perm_ok(st.st_mode, st.st_uid, st.st_gid):
        fail("S1_TMP_PERM", "mode=%04o uid=%d gid=%d" % (st.st_mode & 0o777, st.st_uid, st.st_gid))
    if not ownership_ok(rec[0], rec[1], rec[2], st, expected_sha):
        fail("S1_TMP_OWNERSHIP", "inode/size drifted")
    if sha256_file(TMP) != expected_sha:
        fail("S1_TMP_SHA", "readback sha mismatch")

    # ---- S3: prove ENV untouched and nothing else appeared ----------------------
    try:
        env_sha_after = sha256_file(ENV)
        est2 = os.stat(ENV)
        dir_after = len(os.listdir(DIR))
    except OSError as e:
        fail("S3_VERIFY", getattr(e, "errno", "?"))
    if env_sha_after != env_sha_before:
        # Never claimed as a pass. Report loudly; do not attempt any rollback.
        fail("S3_ENV_CHANGED", "backend.env sha differs although this script never writes it")
    if dir_after != dir_before + 1:
        fail("S3_DIR_COUNT", "before=%d after=%d expected=%d" % (dir_before, dir_after, dir_before + 1))

    sys.stdout.write("A1_RESULT=PASS\n")
    sys.stdout.write("STAGING_PATH=%s\n" % TMP)
    sys.stdout.write("STAGING_INODE=%d\n" % st.st_ino)
    sys.stdout.write("STAGING_SIZE=%d\n" % st.st_size)
    sys.stdout.write("STAGING_SHA256=%s\n" % expected_sha)
    sys.stdout.write("STAGING_MATCHES_INPUT_BYTES=%s\n" % str(st.st_size == IN_BYTES))
    sys.stdout.write("STAGING_PERM=%04o\n" % (st.st_mode & 0o777))
    sys.stdout.write("STAGING_OWNER=%d:%d\n" % (st.st_uid, st.st_gid))
    sys.stdout.write("STAGING_MTIME=%s\n" % time.strftime("%Y-%m-%d %H:%M:%S %z", time.localtime(st.st_mtime)))
    sys.stdout.write("STAGING_LINES=3\n")
    # Report only shape metadata. Never any slice of a credential value.
    for name, n in SPEC:
        sys.stdout.write("VALUE %s len=%d hex_lower_only=True\n" % (name, n))
    sys.stdout.write("ENV_SHA256_UNCHANGED=%s\n" % env_sha_after)
    sys.stdout.write("ENV_STAT_UNCHANGED=%s\n" % str(
        (est.st_mode & 0o777, est.st_uid, est.st_gid, est.st_size, est.st_ino) ==
        (est2.st_mode & 0o777, est2.st_uid, est2.st_gid, est2.st_size, est2.st_ino)))
    sys.stdout.write("DIR_ENTRIES_BEFORE=%d DIR_ENTRIES_AFTER=%d\n" % (dir_before, dir_after))
    sys.stdout.write("PLAINTEXT_COPIES_LIVE=2 (IN,TMP)\n")
    sys.stdout.write("IN_OWNERSHIP_FACTS inode=%d size=%d sha256=%s\n" % (
        ist1.st_ino, ist1.st_size, input_sha))
    sys.stdout.write("CLEANUP_STATUS=NOT_REQUIRED\n")
    sys.stdout.write("DOCKER_MODIFIED=NO R2_API_CALLED=NO AI_PROVIDER_CALLED=NO "
                     "DATABASE_MODIFIED=NO DNS_MODIFIED=NO NGINX_MODIFIED=NO GIT_MODIFIED=NO\n")
    sys.stdout.write("STOP_HERE=A1_COMPLETE_DO_NOT_RUN_A2_A3_A4_A6_A7\n")
    sys.stdout.write("NEXT=STOP. A1 is complete. Do not run A2/A3/A4/A6/A7 without separate authorization.\n")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException:
        # Unexpected error. Print no traceback: exception args can carry paths or
        # argv. Still run the ownership-proven cleanup so we do not strand a staging
        # file holding plaintext credentials. Only the exception TYPE is reported.
        status = cleanup_ours()
        sys.stdout.write("A1_RESULT=FAIL\n")
        sys.stdout.write("PRIMARY_CODE=S1_UNEXPECTED\n")
        sys.stdout.write("DETAIL=exception_type_only\n")
        sys.stdout.write("EXCEPTION_CLASS=%s\n" % sys.exc_info()[0].__name__)
        sys.stdout.write("CLEANUP_STATUS=%s\n" % status)
        if is_residue(status):
            sys.stdout.write("RESIDUE_PENDING_AUTHORITY=YES\n")
        raise SystemExit(1)
