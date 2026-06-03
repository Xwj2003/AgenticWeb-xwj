"""
QA Agent:质量保障。这是整个系统的"刹车" —— 防 LLM 幻觉的关键。

特点:
- 大量使用确定性检查(正则、JSON 解析、文件存在性),不完全依赖 LLM 判断
- 重点检查"契约一致性":后端是否实现了所有声明的接口,前端是否只调用了已声明的接口
- 关键升级:加入"运行时冒烟测试"—— 真正 npm install + 启动 server + 打几个接口,
  这是唯一能拦住"语法正确但跑不起来"(启动即崩溃、缺 express.static 等)的手段
- 检查不通过会在报告中标红,自动修复循环会据此重跑对应 Agent
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

        # 检查 5(新增):前端是否把契约里的每个操作都实现了(防止只做增/查,丢掉删/改/标记完成)
        checks.append(self._check_frontend_coverage(ctx))

        # 检查 6(新增):index.html 是否以合法 <!DOCTYPE html> 开头
        checks.append(self._check_html_doctype(ctx))

        # 检查 7(新增):后端是否用 express.static 托管了前端(否则访问 / 会 Cannot GET /)
        checks.append(self._check_static_serving(ctx))

        # 检查 8:Node 是否可用 + node --check 语法检查
        checks.append(self._check_js_syntax(ctx))

        # 检查 9(治本兜底):真正启动服务 + 打接口的冒烟测试
        checks.append(self._check_runtime_smoke(ctx))

        # 检查 10:启动文件 + README 都在
        checks.append(self._check_devops_files(ctx))

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
        """
        把各种写法的路径统一成 :param 形式,方便前后端/契约互相比对:
        - 去掉 query string
        - ${id}(前端模板字符串) → :param
        - {id} (契约 OpenAPI 写法)→ :param
        - :id  (express 写法)    → :param
        """
        p = p.split("?")[0]
        p = re.sub(r"\$\{[^}]+\}", ":param", p)              # ${id}
        p = re.sub(r"\{[^}]+\}", ":param", p)                # {id}
        p = re.sub(r":[a-zA-Z_][a-zA-Z0-9_]*", ":param", p)  # :id
        return p.rstrip("/") or "/"

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
        """
        前端只能调用契约里声明的接口。

        ★ 修复(原版的真正 bug):原代码只把契约里的 :id 归一化成 :param,
          却没处理契约实际使用的 {id} 写法,导致所有带参接口永远被判为"越界",
          逼着 LLM 为了过检把删/改/标记完成的 fetch 全删掉 —— 这正是"功能缺失"的根因。
          现在前端与契约都统一走 _norm_path。
        """
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
        """
        新增:前端必须实现契约里的每一种操作。
        原系统只检查"有没有越界",却不检查"有没有漏做"——于是 app.js 只做增/查、
        丢掉删/改/标记完成也能全绿。这里按 HTTP 方法粒度反向核对覆盖率。
        """
        contract = (ctx.architecture or {}).get("api_contract", [])
        if not contract:
            return {"name": "前端实现了契约里全部操作(增删改查)", "passed": True, "detail": "契约为空"}

        code = "\n".join(ctx.frontend_files.values())
        methods_needed = sorted({ep.get("method", "").upper() for ep in contract if ep.get("method")})

        missing = []
        for m in methods_needed:
            if m == "GET":
                # GET 通常不写 method 字段,只要有 fetch( 即认为做了读取
                if not re.search(r"fetch\s*\(", code):
                    missing.append("GET(没有任何 fetch 调用)")
            else:
                # 非 GET 必须出现 method: 'X'(单双引号皆可)
                if not re.search(rf"method\s*:\s*['\"]{m}['\"]", code, re.IGNORECASE):
                    missing.append(m)

        return {
            "name": "前端实现了契约里全部操作(增删改查)",
            "passed": len(missing) == 0,
            "detail": f"前端缺少这些操作: {missing}(对应功能没做)" if missing else f"OK(覆盖 {methods_needed})",
        }

    def _check_html_doctype(self, ctx: SharedContext) -> dict:
        """新增:index.html 必须以合法 <!DOCTYPE html> 开头。
        拦住 `<!--DOCTYPE`(漏感叹号被当成注释)这类导致整页解析异常的低级错误。"""
        html = ctx.frontend_files.get("public/index.html") or ctx.frontend_files.get("index.html")
        if html is None:
            return {"name": "index.html 以合法 <!DOCTYPE html> 开头", "passed": False, "detail": "未生成 index.html"}
        head = html.lstrip()[:64].lower()
        ok = head.startswith("<!doctype html")
        return {
            "name": "index.html 以合法 <!DOCTYPE html> 开头",
            "passed": ok,
            "detail": "OK" if ok else f"开头不是 <!DOCTYPE html>: {html.lstrip()[:30]!r}",
        }

    def _check_static_serving(self, ctx: SharedContext) -> dict:
        """新增:server.js 必须用 express.static 托管前端,否则访问 / 直接 Cannot GET /。"""
        server = ctx.backend_files.get("server.js", "")
        ok = bool(re.search(r"express\s*\.\s*static\s*\(", server))
        return {
            "name": "后端托管前端静态资源 (express.static)",
            "passed": ok,
            "detail": "OK" if ok else "server.js 缺少 express.static(...),访问 / 会 Cannot GET /",
        }

    def _check_js_syntax(self, ctx: SharedContext) -> dict:
        """对所有 .js 文件跑 node --check(只查语法,查不出 API 误用/运行时错误)。

        ★ 修复要点:
        1. 不使用 text=True,改用 encoding='utf-8' + errors='replace',
           避免 Windows GBK 解码 node 的 UTF-8 输出时崩溃导致 stderr=None。
        2. 对 stderr/stdout 做 None 防御。
        """
        if not shutil.which("node"):
            return {
                "name": "JS 语法检查 (node --check)",
                "passed": True,
                "detail": "跳过(本机未安装 node)",
            }

        bad = []
        all_js = {**ctx.backend_files, **ctx.frontend_files}
        for path, content in all_js.items():
            if not path.endswith(".js"):
                continue
            full_path = os.path.join(ctx.project_dir, path)
            if not os.path.exists(full_path):
                continue
            try:
                proc = subprocess.run(
                    ["node", "--check", full_path],
                    capture_output=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=10,
                )
                if proc.returncode != 0:
                    stderr = (proc.stderr or "").strip()
                    stdout = (proc.stdout or "").strip()
                    raw = stderr or stdout or "syntax error (no output)"
                    lines = raw.splitlines()
                    error_lines = [
                        l for l in lines
                        if any(kw in l for kw in ("SyntaxError", "ReferenceError", "TypeError", "Error:"))
                        and not l.startswith("Node.js v")
                    ]
                    msg = error_lines[0] if error_lines else (lines[0] if lines else "syntax error")
                    bad.append(f"{path}: {msg}")
            except subprocess.TimeoutExpired:
                bad.append(f"{path}: node --check 超时")
            except Exception as e:
                bad.append(f"{path}: {e}")

        return {
            "name": "JS 语法检查 (node --check)",
            "passed": len(bad) == 0,
            "detail": f"语法错误: {bad}" if bad else "全部通过",
        }

    # ---- 冒烟测试辅助:从契约/数据模型推断要打的接口与请求体(保证对任意项目通用) ----

    @staticmethod
    def _collection_from_path(path: str) -> str:
        """/api/todos/:id -> todos ; /api/todo_items/{id} -> todo_items"""
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
        """为 POST 冒烟造一个尽力而为的请求体:优先用契约自带例子,否则按 data_model 合成。"""
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

    def _check_runtime_smoke(self, ctx: SharedContext) -> dict:
        """
        真正把项目跑起来做端到端冒烟。node --check 只能查语法,查不出
        "语法没错但一跑就崩 / 一访问就 404" 的问题。这里:
          1) npm install
          2) 启动 server.js(随机端口)
          3) GET /                          —— 验证静态托管(否则 Cannot GET /)
          4) GET <契约里第一个集合级 GET>    —— 验证读链路
          5) POST <契约里第一个 POST>        —— 验证写链路

        关键:探测哪些接口、用什么请求体,全部从 api_contract / data_models 推断,
        不写死任何具体业务路径,因此对任意项目通用。
        4xx(校验未过 / 资源不存在)视为正常应用行为,只有启动崩溃、缺静态、5xx 才判失败。
        """
        name = "运行时冒烟测试 (npm install + 启动 + 打接口)"

        if not shutil.which("node") or not shutil.which("npm"):
            return {"name": name, "passed": True, "detail": "跳过(本机无 node/npm)"}
        if "package.json" not in ctx.backend_files:
            return {"name": name, "passed": False, "detail": "无 package.json,无法启动"}

        npm = shutil.which("npm")

        # 1) npm install
        try:
            inst = subprocess.run(
                [npm, "install", "--no-audit", "--no-fund"],
                cwd=ctx.project_dir, capture_output=True,
                encoding="utf-8", errors="replace", timeout=300,
            )
        except subprocess.TimeoutExpired:
            return {"name": name, "passed": False, "detail": "npm install 超时(>300s)"}
        if inst.returncode != 0:
            tail = (inst.stderr or inst.stdout or "").strip().splitlines()
            return {"name": name, "passed": False, "detail": "npm install 失败: " + " / ".join(tail[-3:] or ["(无输出)"])}

        # 从契约挑出要探测的接口(不写死任何业务路径)
        contract = (ctx.architecture or {}).get("api_contract", [])
        get_eps = [ep for ep in contract if (ep.get("method", "") or "").upper() == "GET"]
        coll_get = next(  # 集合级 GET:路径里没有参数({x} / :x)
            (ep for ep in get_eps
             if "{" not in ep.get("path", "") and ":" not in ep.get("path", "")),
            None,
        )
        post_ep = next((ep for ep in contract if (ep.get("method", "") or "").upper() == "POST"), None)
        readiness_path = (coll_get or {}).get("path") or "/"   # 就绪探测优先集合级 GET,否则根路径

        # 2) 选空闲端口
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()

        # 3) 启动 server.js
        env = dict(os.environ)
        env["PORT"] = str(port)
        env["NODE_ENV"] = "test"
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
                    ready = True  # 有响应(哪怕 4xx/5xx)就说明服务起来了
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

            # 6) GET <集合级接口> —— 读链路(只在 5xx / 连接失败 / 非 JSON 时判失败)
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

            # 7) POST <写接口> —— 写链路(4xx 视为校验未过、可接受;5xx 才算坏)
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
        required = ["README.md", "start.sh", ".gitignore"]
        missing = [f for f in required if f not in ctx.devops_files]
        return {
            "name": "工程化文件齐全",
            "passed": len(missing) == 0,
            "detail": f"缺失: {missing}" if missing else "OK",
        }