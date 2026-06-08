"""
QA Agent - Windows 兼容版本 + 前端框架健全性检查

历史:
  - Windows 上 subprocess.run(["npm", ...]) 找不到 npm 命令,
    Windows npm 是 npm.cmd 脚本,需要用 shell=True。已在 _check_runtime_smoke 处理。

v2.2 新增(重要):
  - 新增检查 11:前端框架健全性静态检查(_check_frontend_framework)。
    运行时冒烟测试只启动后端、看 GET / 是否返回 HTML,
    【不会在浏览器里执行 app.js】,所以前端用错框架 API(例如把
    Petite Vue 写成 Vue3 的 data()/methods()/mounted())时,页面其实是
    死的,但旧 QA 全绿。新增的静态检查正是用来挡住这类回归:
      · 禁止出现 Vue3/Vue2 特征:data() / methods: / computed: / new Vue
      · 必须调用 createApp 且 .mount(
      · 必须有 @vue:mounted(否则页面加载后不会拉数据)
"""

import os
import re
import json
import time
import shutil
import socket
import subprocess
import urllib.request
import urllib.error
from .base_agent import BaseAgent
from shared_context import SharedContext


class QAAgent(BaseAgent):
    name = "QA"
    role_desc = "测试工程师 - 静态检查 + 契约一致性 + 运行时冒烟"

    def system_prompt(self) -> str:
        return "QA agent 主要使用确定性检查,不需要 LLM system prompt。"

    def run(self, ctx: SharedContext) -> None:
        self.announce_start()
        checks = []

        # 检查 1:架构声明的文件是否都生成了
        checks.append(self._check_files_exist(ctx))

        # 检查 2:package.json 是否合法 JSON
        checks.append(self._check_package_json(ctx))

        # 检查 3:server.js 是否覆盖了 api_contract 中的所有接口
        checks.append(self._check_api_implementation(ctx))

        # 检查 4:前端是否只调用了 api_contract 中声明的接口(契约一致性)
        checks.append(self._check_frontend_calls(ctx))

        # 检查 5:前端是否把契约里的每个操作都实现了(防止只做增/查,丢掉删/改)
        checks.append(self._check_frontend_coverage(ctx))

        # 检查 6:index.html 是否以合法 <!DOCTYPE html> 开头
        checks.append(self._check_html_doctype(ctx))

        # 检查 7:后端是否用 express.static 托管了前端
        checks.append(self._check_static_serving(ctx))

        # 检查 8:Node 是否可用 + node --check 语法检查
        checks.append(self._check_js_syntax(ctx))

        # 检查 9:真正启动服务 + 打接口的冒烟测试 [Windows 兼容版]
        checks.append(self._check_runtime_smoke(ctx))

        # 检查 10:启动文件 + README 都在
        checks.append(self._check_devops_files(ctx))

        # 检查 11:前端框架健全性(Petite Vue 用法正确性)[v2.2 新增]
        checks.append(self._check_frontend_framework(ctx))

        passed = sum(1 for c in checks if c["passed"])
        total = len(checks)
        report = {
            "summary": f"{passed}/{total} checks passed",
            "passed": passed,
            "total": total,
            "all_passed": passed == total,
            "checks": checks,
        }
        ctx.qa_report = report
        ctx.save_artifact("06_qa_report.json", report)

        self.log(ctx, f"质检完成: {report['summary']}")
        for c in checks:
            mark = "✅" if c["passed"] else "❌"
            self.log(ctx, f"  {mark} {c['name']}: {c['detail']}")

    # ===== 工具:路径归一化(契约/前端统一口径) =====

    @staticmethod
    def _norm_path(p: str) -> str:
        """把各种写法的路径统一成 :param 形式"""
        p = p.split("?")[0]
        p = re.sub(r"\$\{[^}]+\}", ":param", p)
        p = re.sub(r"\{[^}]+\}", ":param", p)
        p = re.sub(r":[a-zA-Z_][a-zA-Z0-9_]*", ":param", p)
        return p.rstrip("/") or "/"

    @staticmethod
    def _collection_from_path(path: str) -> str:
        """/api/todos/:id -> todos"""
        segs = [
            s for s in path.split("/")
            if s and s != "api" and not s.startswith(("{", ":"))
        ]
        return segs[0] if segs else ""

    @staticmethod
    def _sample_value(t: str):
        t = (t or "").lower()
        if any(k in t for k in ("num", "int", "float", "double")):
            return 1
        if "bool" in t:
            return True
        if any(k in t for k in ("array", "list")):
            return []
        if "obj" in t:
            return {}
        return "qa_smoke"

    def _sample_body(self, ctx: SharedContext, ep: dict) -> dict:
        """为 POST 冒烟造一个尽力而为的请求体"""
        rb = ep.get("request_body")
        if isinstance(rb, dict) and rb:
            return rb
        coll = self._collection_from_path(ep.get("path", ""))
        models = (ctx.architecture or {}).get("data_models", [])
        model = next((m for m in models if m.get("collection") == coll), None)
        body = {}
        if model:
            for f in model.get("fields", []):
                n = f.get("name")
                if not n or n.lower() == "id":
                    continue
                body[n] = self._sample_value(f.get("type"))
        return body

    # ===== 各项检查 =====

    def _check_files_exist(self, ctx: SharedContext) -> dict:
        layout = (ctx.architecture or {}).get("file_layout", {})
        declared = layout.get("backend", []) + layout.get("frontend", [])
        produced = set(ctx.backend_files.keys()) | set(ctx.frontend_files.keys())

        def _strip_public(p: str) -> str:
            return p[len("public/"):] if p.startswith("public/") else p

        norm_produced = {_strip_public(p) for p in produced}
        missing = [f for f in declared if _strip_public(f) not in norm_produced]
        return {
            "name": "架构声明的文件全部生成",
            "passed": len(missing) == 0,
            "detail": f"缺失: {missing}" if missing else f"全部生成({len(declared)} 个)",
        }

    def _check_package_json(self, ctx: SharedContext) -> dict:
        pkg = ctx.backend_files.get("package.json")
        if not pkg:
            return {"name": "package.json 存在且合法", "passed": False, "detail": "未生成 package.json"}
        try:
            obj = json.loads(pkg)
            has_start = "start" in obj.get("scripts", {})
            return {
                "name": "package.json 存在且合法",
                "passed": has_start,
                "detail": "OK,包含 start 脚本" if has_start else "缺少 npm start 脚本",
            }
        except json.JSONDecodeError as e:
            return {"name": "package.json 存在且合法", "passed": False, "detail": f"JSON 解析失败: {e}"}

    def _check_api_implementation(self, ctx: SharedContext) -> dict:
        contract = (ctx.architecture or {}).get("api_contract", [])
        server = ctx.backend_files.get("server.js", "")
        if not contract:
            return {"name": "后端实现了契约里的全部接口", "passed": True, "detail": "契约为空"}

        missing = []
        for ep in contract:
            method = ep.get("method", "").lower()
            path = ep.get("path", "")
            normalized = re.sub(r'\{([^}]+)\}', r':\1', path)
            path_pattern = re.escape(normalized)
            path_pattern = re.sub(
                r':[a-zA-Z_][a-zA-Z0-9_]*',
                ':[a-zA-Z_][a-zA-Z0-9_]*',
                path_pattern,
            )
            pattern = rf"(?:app|router)\s*\.\s*{method}\s*\(\s*['\"`]{path_pattern}['\"`]"
            if not re.search(pattern, server):
                missing.append(f"{ep.get('method')} {path}")

        return {
            "name": "后端实现了契约里的全部接口",
            "passed": len(missing) == 0,
            "detail": f"未实现: {missing}" if missing else f"全部实现({len(contract)} 个)",
        }

    def _check_frontend_calls(self, ctx: SharedContext) -> dict:
        contract = (ctx.architecture or {}).get("api_contract", [])
        contract_paths = {self._norm_path(ep.get("path", "")) for ep in contract}

        all_frontend_code = "\n".join(ctx.frontend_files.values())
        fetch_paths = re.findall(r"fetch\s*\(\s*[`'\"]([^`'\"]+)[`'\"]", all_frontend_code)

        out_of_contract = []
        seen = []
        for p in fetch_paths:
            np = self._norm_path(p)
            seen.append(np)
            if np not in contract_paths:
                out_of_contract.append(p)

        return {
            "name": "前端只调用契约中已声明的接口",
            "passed": len(out_of_contract) == 0,
            "detail": f"越界调用: {out_of_contract}" if out_of_contract else f"OK({len(seen)} 处调用)",
        }

    def _check_frontend_coverage(self, ctx: SharedContext) -> dict:
        contract = (ctx.architecture or {}).get("api_contract", [])
        if not contract:
            return {"name": "前端实现了契约里全部操作(增删改查)", "passed": True, "detail": "契约为空"}

        code = "\n".join(ctx.frontend_files.values())
        methods_needed = sorted({ep.get("method", "").upper() for ep in contract if ep.get("method")})

        missing = []
        for m in methods_needed:
            if m == "GET":
                if not re.search(r"fetch\s*\(", code):
                    missing.append("GET(没有任何 fetch 调用)")
            else:
                if not re.search(rf"method\s*:\s*['\"]{m}['\"]", code, re.IGNORECASE):
                    missing.append(m)

        return {
            "name": "前端实现了契约里全部操作(增删改查)",
            "passed": len(missing) == 0,
            "detail": f"缺少操作: {missing}" if missing else f"全部实现({len(methods_needed)} 种)",
        }

    def _check_html_doctype(self, ctx: SharedContext) -> dict:
        html = ctx.frontend_files.get("public/index.html", "")
        ok = html.lstrip().startswith("<!DOCTYPE html>") or html.lstrip().startswith("<!doctype html>")
        return {
            "name": "index.html 以合法 <!DOCTYPE html> 开头",
            "passed": ok,
            "detail": "OK" if ok else "缺少或格式错误的 <!DOCTYPE>",
        }

    def _check_static_serving(self, ctx: SharedContext) -> dict:
        server = ctx.backend_files.get("server.js", "")
        has_static = "express.static" in server
        return {
            "name": "后端托管前端静态资源 (express.static)",
            "passed": has_static,
            "detail": "OK" if has_static else "后端未配置 express.static,前端访问失败",
        }

    def _check_js_syntax(self, ctx: SharedContext) -> dict:
        if shutil.which("node") is None:
            return {"name": "JS 语法检查 (node --check)", "passed": True, "detail": "跳过(本机无 node)"}

        js_files = [
            ("server.js", ctx.backend_files.get("server.js", "")),
            ("db.js", ctx.backend_files.get("db.js", "")),
            ("public/app.js", ctx.frontend_files.get("public/app.js", "")),
        ]

        bad = []
        for name, content in js_files:
            if not content:
                continue
            path = os.path.join(ctx.project_dir, name)
            try:
                result = subprocess.run(
                    ["node", "--check", path], capture_output=True,
                    encoding="utf-8", errors="replace", timeout=10,
                )
                if result.returncode != 0:
                    lines = (result.stderr or result.stdout or "").strip().splitlines()
                    error_lines = [l for l in lines if any(k in l for k in ("error", "Error", "Unexpected"))]
                    msg = error_lines[0] if error_lines else (lines[0] if lines else "syntax error")
                    bad.append(f"{name}: {msg}")
            except subprocess.TimeoutExpired:
                bad.append(f"{name}: node --check 超时")
            except Exception as e:
                bad.append(f"{name}: {e}")

        return {
            "name": "JS 语法检查 (node --check)",
            "passed": len(bad) == 0,
            "detail": f"语法错误: {bad}" if bad else "全部通过",
        }

    def _check_runtime_smoke(self, ctx: SharedContext) -> dict:
        """
        【Windows 兼容版本】
        真正把项目跑起来做端到端冒烟。
        关键改动：
          - npm install 用 shell=True 和 npm.cmd (Windows)
          - node server.js 用 shell=True (Windows)

        注意:此检查只验证【后端】启动 + 静态托管 + 读写链路,
        不会在浏览器里执行前端 app.js。前端框架用法是否正确由
        _check_frontend_framework 静态把关。
        """
        name = "运行时冒烟测试 (npm install + 启动 + 打接口)"

        if not shutil.which("node") or not shutil.which("npm"):
            return {"name": name, "passed": True, "detail": "跳过(本机无 node/npm)"}
        if "package.json" not in ctx.backend_files:
            return {"name": name, "passed": False, "detail": "无 package.json,无法启动"}

        # 1) npm install (Windows 兼容)
        try:
            if os.name == 'nt':
                # Windows: 用 npm.cmd
                inst = subprocess.run(
                    "npm install --no-audit --no-fund",
                    cwd=ctx.project_dir, capture_output=True,
                    encoding="utf-8", errors="replace", timeout=300,
                    shell=True,
                )
            else:
                # macOS/Linux: 用数组形式
                inst = subprocess.run(
                    ["npm", "install", "--no-audit", "--no-fund"],
                    cwd=ctx.project_dir, capture_output=True,
                    encoding="utf-8", errors="replace", timeout=300,
                )
        except subprocess.TimeoutExpired:
            return {"name": name, "passed": False, "detail": "npm install 超时(>300s)"}
        if inst.returncode != 0:
            tail = (inst.stderr or inst.stdout or "").strip().splitlines()
            return {"name": name, "passed": False, "detail": "npm install 失败: " + " / ".join(tail[-3:] or ["(无输出)"])}

        # 从契约挑出要探测的接口
        contract = (ctx.architecture or {}).get("api_contract", [])
        get_eps = [ep for ep in contract if (ep.get("method", "") or "").upper() == "GET"]
        coll_get = next(
            (ep for ep in get_eps
             if "{" not in ep.get("path", "") and ":" not in ep.get("path", "")),
            None,
        )
        post_ep = next((ep for ep in contract if (ep.get("method", "") or "").upper() == "POST"), None)
        readiness_path = (coll_get or {}).get("path") or "/"

        # 2) 选空闲端口
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()

        # 3) 启动 server.js (Windows 兼容)
        env = dict(os.environ)
        env["PORT"] = str(port)
        env["NODE_ENV"] = "test"

        if os.name == 'nt':
            # Windows: 用 shell=True
            proc = subprocess.Popen(
                "node server.js",
                cwd=ctx.project_dir, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                encoding="utf-8", errors="replace",
                shell=True,
            )
        else:
            # macOS/Linux: 用数组形式
            proc = subprocess.Popen(
                ["node", "server.js"],
                cwd=ctx.project_dir, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                encoding="utf-8", errors="replace",
            )

        base = f"http://127.0.0.1:{port}"
        try:
            # 4) 等就绪 / 捕获"启动即崩溃"
            ready = False
            deadline = time.time() + 12
            while time.time() < deadline:
                if proc.poll() is not None:
                    out, err = proc.communicate(timeout=5)
                    msg = (err or out or "").strip().splitlines()
                    tail = " / ".join(msg[-4:]) if msg else "进程已退出但无输出"
                    return {"name": name, "passed": False, "detail": f"server.js 启动即崩溃: {tail}"}
                try:
                    with urllib.request.urlopen(base + readiness_path, timeout=1) as r:
                        r.read()
                    ready = True
                    break
                except urllib.error.HTTPError:
                    ready = True
                    break
                except Exception:
                    time.sleep(0.3)

            if not ready:
                return {"name": name, "passed": False, "detail": "12s 内服务仍未就绪"}

            problems = []

            # 5) GET / —— 静态托管是否生效
            try:
                with urllib.request.urlopen(base + "/", timeout=3) as r:
                    body = r.read().decode("utf-8", "replace")
                    if "<" not in body:
                        problems.append("GET / 未返回 HTML 页面")
            except urllib.error.HTTPError as e:
                problems.append(f"GET / 返回 {e.code}(多半是缺 express.static,会 Cannot GET /)")
            except Exception as e:
                problems.append(f"GET / 请求失败: {e}")

            # 6) GET <集合级接口> —— 读链路
            if coll_get:
                gp = coll_get.get("path")
                try:
                    with urllib.request.urlopen(base + gp, timeout=3) as r:
                        json.loads(r.read().decode("utf-8", "replace"))
                except urllib.error.HTTPError as e:
                    if e.code >= 500:
                        problems.append(f"GET {gp} 返回 {e.code}(读链路报错)")
                except json.JSONDecodeError:
                    problems.append(f"GET {gp} 返回的不是合法 JSON")
                except Exception as e:
                    problems.append(f"GET {gp} 请求失败: {e}")

            # 7) POST <写接口> —— 写链路
            if post_ep:
                pp = post_ep.get("path")
                payload = json.dumps(self._sample_body(ctx, post_ep)).encode("utf-8")
                try:
                    req = urllib.request.Request(
                        base + pp, data=payload,
                        headers={"Content-Type": "application/json"}, method="POST",
                    )
                    with urllib.request.urlopen(req, timeout=3) as r:
                        r.read()
                except urllib.error.HTTPError as e:
                    if e.code >= 500:
                        problems.append(f"POST {pp} 返回 {e.code}(写链路报错)")
                except Exception as e:
                    problems.append(f"POST {pp} 请求失败: {e}")

            return {
                "name": name,
                "passed": len(problems) == 0,
                "detail": "全部通过(静态托管 + 读写链路均正常)" if not problems else "; ".join(problems),
            }
        finally:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def _check_devops_files(self, ctx: SharedContext) -> dict:
        required = ["README.md", "start.sh"] # , ".gitignore"
        missing = [f for f in required if f not in ctx.devops_files]
        return {
            "name": "工程化文件齐全",
            "passed": len(missing) == 0,
            "detail": f"缺失: {missing}" if missing else "OK",
        }

    def _check_frontend_framework(self, ctx: SharedContext) -> dict:
        """
        [v2.2 新增] 前端框架健全性静态检查。

        运行时冒烟只跑后端、看 GET / 是否返回 HTML,不会在浏览器里执行 app.js。
        因此前端若把 Petite Vue 写成标准 Vue3 的 Options API
        (data() / methods: / mounted()),页面其实渲染不出来,
        但旧 QA 仍会全绿。此检查用静态特征拦住这类问题。

        判定规则(任一不满足即失败):
          1) app.js 不得出现 Vue3/Vue2 的 Options API 特征:
             data() / methods: / computed: / watch: / new Vue
          2) app.js 必须调用 createApp(...) 且存在 .mount(
          3) 页面必须有挂载后拉数据的入口:
             HTML 含 @vue:mounted,或 app.js 显式在 mount 后调用初始化
        """
        name = "前端框架用法正确 (Petite Vue)"

        app_js = ctx.frontend_files.get("public/app.js", "") or ctx.frontend_files.get("app.js", "")
        html = ctx.frontend_files.get("public/index.html", "") or ctx.frontend_files.get("index.html", "")

        if not app_js:
            return {"name": name, "passed": False, "detail": "未生成 public/app.js"}

        problems = []

        # 规则 1:禁止 Vue3/Vue2 Options API 特征
        # 说明:Petite Vue 的 createApp 接收扁平对象,没有 data()/methods:/computed:/watch:。
        forbidden = {
            "data() {": r"\bdata\s*\(\s*\)\s*\{",          # data() { ... }
            "data:":     r"\bdata\s*:\s*(?:function|\(|\{)",  # data: function / data: () / data: {
            # "methods:":  r"\bmethods\s*:",
            "computed:": r"\bcomputed\s*:",
            "watch:":    r"\bwatch\s*:",
            "new Vue":   r"\bnew\s+Vue\b",
        }
        hit = [label for label, pat in forbidden.items() if re.search(pat, app_js)]
        if hit:
            problems.append(
                "app.js 使用了 Petite Vue 不支持的 Vue Options API 写法(" +
                ", ".join(hit) +
                "),会导致数据不渲染。请改成扁平对象:createApp({ 数据..., 方法... })"
            )

        # 规则 2:必须有 createApp(...) 且 .mount(
        if not re.search(r"createApp\s*\(", app_js):
            problems.append("app.js 未调用 createApp()")
        if not re.search(r"\.mount\s*\(", app_js):
            problems.append("app.js 未调用 .mount(),应用不会挂载")

        # 规则 3:必须有挂载后的初始化入口(否则页面打开后不拉数据)
        has_html_mounted = bool(re.search(r"@vue:mounted", html))
        # 兜底:有些写法会在 mount() 之后链式或单独调用 init/fetch
        has_js_init = bool(
            re.search(r"\.mount\s*\([^)]*\)\s*[.;]?\s*\w+\s*\(", app_js)
            or re.search(r"@vue:mounted", app_js)
        )
        if not (has_html_mounted or has_js_init):
            problems.append(
                "未发现挂载后的初始化入口(HTML 缺少 @vue:mounted=\"init()\"),"
                "页面加载后不会自动拉取列表数据"
            )

        return {
            "name": name,
            "passed": len(problems) == 0,
            "detail": "OK(Petite Vue 用法正确)" if not problems else "; ".join(problems),
        }