"""生成生产 Web/API 部署 bundle（白名单打包）—— Phase 7 Provider 抽象阶段一配套。

用途
----
Modal 生产 Web/API 镜像将只打包 deploy_bundle/ 内的文件，不再依赖整个
backend 工作区（杜绝未提交改动 / tests / docs / scripts / POC / 实验服务被误部署）。

原理
----
1. 从 main.py 出发做 AST import 闭包分析（覆盖函数体内惰性 import，
   含 `from app.X import Y` 的子模块）。
2. 只复制闭包内的 .py 文件 + 所属包 __init__.py + 必要运行文件
   （requirements.txt / static_dist 前端构建产物）。
3. 显式白名单边界：tests/ docs/ scripts/ POC/ 独立 GPU App（*_modal.py）/
   未批准新服务（asr_client/tts_client/voice_clone_task/separation）等一律不进 bundle。

运行
----
    python scripts/build_deploy_bundle.py
    生成 backend/deploy_bundle/ 并输出 manifest.json
    之后必须运行 python scripts/predeploy_check.py 校验
"""

import ast
import json
import os
import shutil

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUNDLE = os.path.join(BACKEND, "deploy_bundle")
ENTRY = "main"

# 禁止进入生产 bundle 的目录名（路径段精确匹配）
FORBIDDEN_DIRS = ("tests", "docs", "scripts", "poc", "__pycache__", ".git",
                  "data", "results", "generated", "voice_models", "database")

# 禁止进入生产 bundle 的文件名（即使意外被闭包引用也拒绝）
FORBIDDEN_FILES = (
    "asr_client.py", "tts_client.py", "voice_clone_task.py",
    "ace_step_modal.py", "spleeter_modal.py", "musicgen_modal.py", "gpt_sovits_modal.py",
    "poc_4stem_compare.py", "poc_mdx23c_modal.py", "poc_mdx_separation.py", "poc_mega53_modal.py",
)

FORBIDDEN_EXT = (".db", ".db-wal", ".db-shm", ".wav", ".mp3", ".pyc", ".pyo", ".log")
FORBIDDEN_NAMES = (".env", ".envrc", "secrets.json", "secrets.local.json")

# 非闭包但必须随 bundle 提供的运行文件/目录
RUNTIME_FILES = ("requirements.txt", "pyproject.toml")
RUNTIME_DIRS = ("static_dist",)


def is_forbidden(rel: str) -> bool:
    parts = rel.replace("\\", "/").split("/")
    if any(p in FORBIDDEN_DIRS for p in parts[:-1]):
        return True
    base = parts[-1]
    if base in FORBIDDEN_FILES:
        return True
    if base in FORBIDDEN_NAMES:
        return True
    if any(base.endswith(e) for e in FORBIDDEN_EXT):
        return True
    return False


def closure_from(entry: str) -> set:
    """从入口模块做 AST 闭包：收集所有 `app.*` / `main.*` 依赖模块名。

    同时解析相对导入（`from .gradio_mixins import X` / `from .. import Y`），
    覆盖包内子模块依赖。
    """

    def resolve_import_from(mod: str, node: ast.ImportFrom) -> str:
        parts = mod.split(".")
        is_pkg = os.path.isdir(os.path.join(BACKEND, mod.replace(".", os.sep)))
        pkg = parts if is_pkg else parts[:-1]  # 当前模块所在包
        level = node.level or 0
        if level == 0:
            base = node.module or ""
        else:
            drop = min(level - 1, len(pkg))
            base = ".".join(pkg[: len(pkg) - drop]) + (("." + node.module) if node.module else "")
        return base

    seen = set()
    queue = [entry]

    def enqueue(mod: str) -> None:
        """入队模块及其全部祖先包（包的 __init__.py 也会被 import，其导入必须跟随）。"""
        if mod in seen or mod in queue:
            return
        queue.append(mod)
        parts = mod.split(".")
        for i in range(1, len(parts)):
            p = ".".join(parts[:i])
            if p not in seen and p not in queue:
                queue.append(p)

    while queue:
        mod = queue.pop()
        if mod in seen:
            continue
        seen.add(mod)
        fname = module_file(mod)
        if not os.path.exists(fname):
            continue
        try:
            tree = ast.parse(open(fname, encoding="utf-8").read())
        except Exception as exc:  # noqa: BLE001
            print(f"[错误] 无法解析 {fname}: {exc}")
            raise
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    top = a.name.split(".")[0]
                    if top == "app" or a.name.startswith("main"):
                        enqueue(a.name)
            elif isinstance(node, ast.ImportFrom):
                base = resolve_import_from(mod, node)
                if not base or not (base.split(".")[0] == "app" or base.startswith("main")):
                    continue
                enqueue(base)
                for a in node.names:
                    if a.name == "*":
                        continue
                    cand = f"{base}.{a.name}"
                    if cand.split(".")[0] == "app" or cand.startswith("main"):
                        enqueue(cand)
    return seen


def module_file(mod: str) -> str:
    """模块名 -> 实际文件路径（包解析为 __init__.py）。"""
    base = os.path.join(BACKEND, mod.replace(".", os.sep))
    if os.path.isdir(base):
        return os.path.join(base, "__init__.py")
    return base + ".py"


def ancestor_packages(mod: str):
    parts = mod.split(".")
    return [".".join(parts[:i]) for i in range(1, len(parts))]


def main() -> None:
    if os.path.isdir(BUNDLE):
        shutil.rmtree(BUNDLE)
    os.makedirs(BUNDLE, exist_ok=True)

    mods = closure_from(ENTRY)
    files: dict[str, str] = {}

    def add(path: str, rel: str) -> None:
        if rel in files:
            return
        if is_forbidden(rel):
            print(f"[警告] 闭包引用被禁止文件 {rel}，跳过（请人工确认依赖）")
            return
        dst = os.path.join(BUNDLE, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(path, dst)
        files[rel] = path

    for mod in sorted(mods):
        path = module_file(mod)
        if not os.path.exists(path):
            continue
        rel = os.path.relpath(path, BACKEND)
        add(path, rel)
        for pkg in ancestor_packages(mod):
            ppath = os.path.join(BACKEND, pkg.replace(".", os.sep), "__init__.py")
            if os.path.exists(ppath):
                add(ppath, os.path.relpath(ppath, BACKEND))

    for fn in RUNTIME_FILES:
        p = os.path.join(BACKEND, fn)
        if os.path.exists(p):
            add(p, fn)

    for d in RUNTIME_DIRS:
        p = os.path.join(BACKEND, d)
        if os.path.isdir(p):
            for root, dirs, fnames in os.walk(p):
                dirs[:] = [x for x in dirs if x != "__pycache__"]
                for f in fnames:
                    full = os.path.join(root, f)
                    rel = os.path.relpath(full, BACKEND)
                    if is_forbidden(rel):
                        print(f"[跳过] static_dist 内禁止文件 {rel}")
                        continue
                    add(full, rel)

    manifest = sorted(files)
    with open(os.path.join(BUNDLE, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump({"entry": ENTRY, "files": manifest}, fh, ensure_ascii=False, indent=2)

    print(f"bundle 目录: {BUNDLE}")
    print(f"文件总数: {len(manifest)}")
    for f in manifest:
        print("  ", f)
    print()
    print("[下一步] 运行: python scripts/predeploy_check.py")


if __name__ == "__main__":
    main()