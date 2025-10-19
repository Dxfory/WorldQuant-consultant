"""
Zach
"""
from machine_lib import *
from config import *
import os
import re
import math
import asyncio
import aiofiles
import time
from typing import List, Tuple, Optional, Dict, Set
from collections import defaultdict, deque
from datetime import datetime
from dataclasses import dataclass

# =========================
# 环境变量（可选）
# =========================
ENABLE_EARLY_GROUP   = os.getenv("ENABLE_EARLY_GROUP", "1") == "1"
EARLY_GROUP_MAX_SEEDS= int(os.getenv("EARLY_GROUP_MAX_SEEDS", "80"))
EARLY_GROUP_KEYS     = [x.strip() for x in os.getenv("EARLY_GROUP_KEYS", "SUBINDUSTRY,MARKET").split(",") if x.strip()]

# 自适应并发
AIMD_MAX_CONCURRENCY = None  # 默认取 n_jobs
AIMD_MIN_CONCURRENCY = None  # 默认取 max(1, n_jobs//2)

# =========================
# 工具：确保 records 目录存在
# =========================
def _ensure_records():
    try:
        os.makedirs(RECORDS_PATH, exist_ok=True)
    except Exception:
        os.makedirs("records", exist_ok=True)

# =========================
# A-2 + B-7：去重 + 轻评估
# =========================
import re
_CANON_SPACES = re.compile(r"\s+")
_CANON_COMMAS = re.compile(r",\s+")
_TOKEN_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*|\(|\)|,|\d+\.?\d*")
_OP_PATTERN = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*\(")
_WINDOW_RE  = re.compile(r",\s*(\d{2,4})\s*\)")
_SAFE_LEN = 1024*8

_ROBUST_OPS = {
    "rank": 0.8, "zscore": 0.9, "normalize": 0.6, "group_neutralize": 1.0,
    "ts_mean": 0.6, "ts_median": 0.7, "ts_std_dev": 0.5, "ts_rank": 0.6,
    "winsorize": 0.7, "group_rank": 0.8, "group_zscore": 0.8,
}
_PENALIZE_OPS = {"kurtosis": 0.2, "skewness": 0.2, "entropy": 0.2, "moment": 0.2}

def _canonicalize(expr: str) -> str:
    s = expr[:_SAFE_LEN]
    s = _CANON_COMMAS.sub(",", s)
    s = _CANON_SPACES.sub(" ", s)
    return s.strip()

def _rough_depth(expr: str) -> int:
    d = m = 0
    for ch in expr:
        if ch == '(': d += 1; m = max(m, d)
        elif ch == ')': d -= 1
    return m

def _operator_count(expr: str) -> int:
    return len(_OP_PATTERN.findall(expr))

def _light_score(expr: str) -> float:
    e = expr.lower()
    score = 0.0
    for k, w in _ROBUST_OPS.items():
        if k in e: score += w
    for k, w in _PENALIZE_OPS.items():
        if k in e: score -= w
    for m in _WINDOW_RE.finditer(e):
        w = int(m.group(1))
        if 5 <= w <= 252: score += 0.15
        elif w > 756:     score -= 0.2
    depth = _rough_depth(e)
    ops   = _operator_count(e)
    score -= max(0, depth - 6) * 0.15
    score -= max(0, ops   - 12) * 0.06
    score -= max(0, len(e) - 800)/1000.0
    return score

def _shingles(expr: str, n: int=3) -> Tuple[str, ...]:
    toks = _TOKEN_RE.findall(expr.lower())[:256]
    if len(toks) < n: return tuple(toks)
    return tuple(" ".join(toks[i:i+n]) for i in range(len(toks)-n+1))

def _jaccard(a: Tuple[str,...], b: Tuple[str,...]) -> float:
    if not a or not b: return 0.0
    sa, sb = set(a), set(b)
    inter = len(sa & sb)
    return 0.0 if inter==0 else inter/float(len(sa|sb))

def _dedup_and_light_filter(exprs: List[str], keep_ratio=0.55, top_k=6000, sim_threshold=0.82) -> List[str]:
    if not exprs: return []
    # 规范化去重
    seen, uniq = set(), []
    for e in exprs:
        c = _canonicalize(e)
        if c not in seen:
            seen.add(c); uniq.append(e)
    if len(uniq) <= 64: return uniq
    # 轻评估
    scored = [(e, _light_score(e)) for e in uniq]
    scored.sort(key=lambda x: x[1], reverse=True)
    k = min(top_k, max(32, int(len(scored)*keep_ratio)))
    pool = [e for e,_ in scored[:k*2]]
    # 相似去冗
    reps, out = [], []
    for e in pool:
        sh = _shingles(_canonicalize(e),3)
        if any(_jaccard(sh,sh0)>=sim_threshold for _,sh0 in reps):
            continue
        reps.append((e,sh)); out.append(e)
        if len(out)>=k: break
    return out if out else [e for e,_ in scored[:k]]

# =========================
# B-10：轻量“早引分组”（Step-2）
# =========================
def _early_group_seed(exprs: List[str],
                      max_n: int,
                      group_keys: List[str],
                      whitelist: Optional[set]) -> List[str]:
    if not ENABLE_EARLY_GROUP or not exprs: return []
    allowed = set()
    for need in ("group_neutralize","group_rank","group_zscore"):
        if not whitelist or need in whitelist:
            allowed.add(need)
    if not allowed: return []
    seeds = exprs[:max_n]
    out = []
    for e in seeds:
        for g in group_keys:
            gk = g.strip()
            if not gk: continue
            if "group_neutralize" in allowed: out.append(f"group_neutralize({e}, {gk})")
            if "group_rank"       in allowed: out.append(f"group_rank({e}, {gk})")
            if "group_zscore"     in allowed: out.append(f"group_zscore({e}, {gk})")
    return out

# =========================
# A-3：AIMD 并发控制（统一调度）
# =========================
@dataclass
class _AIMD:
    cur: int
    lo: int
    hi: int
    ok_streak: int = 0
    def on_ok(self):
        self.ok_streak += 1
        if self.ok_streak % 3 == 0:
            self.cur = min(self.hi, self.cur + 1)
    def on_hit(self):
        self.ok_streak = 0
        self.cur = max(self.lo, max(1, int(self.cur * 0.7)))

# =========================
# 单个 pool 的提交与拉取
# =========================
async def _submit_and_fetch(session_manager: "SessionManager",
                            alpha_pool: List[str],
                            region: str, universe: str,
                            delay: int, decay: int,
                            tag_name: str, neut: str,
                            retry_max: int = 5):
    assert 1 <= len(alpha_pool) <= 10
    if time.time() - session_manager.start_time > session_manager.expiry_time:
        await session_manager.refresh_session()

    sim_list = [{
        'type': 'REGULAR',
        'settings': {
            'instrumentType': 'EQUITY',
            'region': region,
            'universe': universe,
            'delay': delay,
            'decay': decay,
            'neutralization': neut,
            'truncation': 0.08,
            'pasteurization': 'ON',
            'unitHandling': 'VERIFY',
            'nanHandling': 'ON',
            'language': 'FASTEXPR',
            'visualization': False,
        },
        'regular': expr
    } for expr in alpha_pool]

    backoff = 3
    loc = None
    for attempt in range(1, retry_max+1):
        try:
            async with session_manager.session.post(f"{brain_api_url}/simulations", json=sim_list) as resp:
                loc = resp.headers.get("Location", None)
                if loc:
                    break
                js = await resp.json()
                detail = js[0].get("detail") if isinstance(js, list) and js else js.get("detail", "")
                if "SIMULATION_LIMIT_EXCEEDED" in str(detail) or resp.status in (429, 503):
                    await asyncio.sleep(backoff); backoff = min(30, backoff*2)
                    continue
                return []
        except Exception:
            await asyncio.sleep(backoff); backoff = min(30, backoff*2)
    if not loc:
        return []

    children = []
    while True:
        try:
            async with session_manager.session.get(loc) as r:
                js = await r.json()
                ra = r.headers.get("Retry-After")
                if ra:
                    await asyncio.sleep(float(ra)); continue
                st = js.get("status")
                if st == "COMPLETE":
                    children = js.get("children", [])
                    break
                if st == "ERROR":
                    try:
                        async with session_manager.session.delete(loc) as _:
                            pass
                    except: pass
                    return []
                await asyncio.sleep(1.5)
        except Exception:
            await asyncio.sleep(3)

    out = []
    for cid in children:
        try:
            async with session_manager.session.get(f"{brain_api_url}/simulations/{cid}") as cr:
                cj = await cr.json()
                aid = cj.get("alpha")
                rexpr = cj.get("regular")
                if aid and rexpr:
                    out.append((aid, rexpr))
        except Exception:
            continue
    return out

# =========================
# 主执行：按 decay 分组 -> 生成 pools -> AIMD 异步跑
# =========================
@while_true_try_decorator
def run_task(dataset_id, region, delay, instrumentType, universe, n_jobs, tag=None):
    delay   = int(delay)
    n_jobs  = int(n_jobs)

    print(datetime.now(),f"=================您的二阶段配置信息==================")
    print(datetime.now(),f"dataset_id: {dataset_id}")
    print(datetime.now(),f"region: {region}")
    print(datetime.now(),f"delay: {delay}")
    print(datetime.now(),f"instrumentType: {instrumentType}")
    print(datetime.now(),f"universe: {universe}")
    print(datetime.now(),f"n_jobs: {n_jobs}")
    print(datetime.now(),f"=============================================")
    time.sleep(2)

    _ensure_records()

    # 生成Step1的tag（可由外部覆盖）
    step1_tag = f"{region}_{delay}_{instrumentType}_{universe}_{dataset_id}_step1"
    step2_tag = step1_tag.replace("_step1", "_step2")

    # 阈值
    if int(delay) == 1:
        sharpe_step2_th, fitness_step2_th = 1.0, 0.5
    elif int(delay) == 0:
        sharpe_step2_th, fitness_step2_th = 2.0, 1.0
    else:
        print(datetime.now(),"delay must be 0 or 1."); return

    # 拉取一阶段入围
    fo_tracker = get_alphas("2020-01-01", "2029-12-31",
                            sharpe_step2_th, fitness_step2_th,
                            100, 100,
                            region, universe, delay, instrumentType,
                            500, "track", tag=step1_tag)

    fo_layer = prune(fo_tracker['next'] + fo_tracker['decay'], dataset_id, 3)
    if not fo_layer:
        print(datetime.now(),'暂时没有满足条件的一阶段因子，请继续运行 step1.')
        return
    print(datetime.now(),f'qualified expression: {len(fo_layer)}')

    # 生成 Step-2 候选（含轻量早引分组）
    base_exprs = [expr for expr,_ in fo_layer]
    try:
        ops_whitelist = set(aval) if isinstance(aval, list) else None
    except Exception:
        ops_whitelist = None
    early_group_exprs = _early_group_seed(base_exprs, EARLY_GROUP_MAX_SEEDS, EARLY_GROUP_KEYS, ops_whitelist)

    so_alpha_list = []
    for expr, decay in fo_layer:
        so_alpha_list.append((expr, decay))
        for alpha in get_group_second_order_factory([expr], group_ops):
            so_alpha_list.append((alpha, decay))
    for expr in early_group_exprs:
        so_alpha_list.append((expr, fo_layer[0][1]))

    # 已完成去除
    completed = read_completed_alphas(f"{RECORDS_PATH}/{step2_tag}_simulated_alpha_expression.txt")
    raw = so_alpha_list
    alpha_list = [(e,d) for (e,d) in raw if e not in completed]
    if not alpha_list:
        print(datetime.now(),f"已经完成了{len(completed)}个alpha表达式，一共有{len(raw)}个alpha表达式")
        print(datetime.now(),f"{step2_tag} is done."); return

    print(datetime.now(),f"{step2_tag} progress: {len(raw)-len(alpha_list)}/{len(raw)}")

    # —— Step-2 的 A-2 + B-7 （表达式侧轻筛）——
    before = len(alpha_list)
    expr_filtered = _dedup_and_light_filter([e for e,_ in alpha_list],
                                            keep_ratio=0.55, top_k=6000, sim_threshold=0.82)
    expr_keep = set(expr_filtered)
    alpha_list = [(e,d) for (e,d) in alpha_list if e in expr_keep]
    after = len(alpha_list)
    print(datetime.now(), f"[LightFilter/Step2] before={before}, after={after}, cut={before-after}")

    # —— 按 decay 分组，构造 pool（每 10 条）——
    grouped = defaultdict(list)
    for e,d in alpha_list:
        grouped[d].append(e)

    asyncio.run(_run_all_step2(grouped, region, universe, delay, step2_tag, n_jobs))

async def _run_all_step2(grouped_exprs, region, universe, delay, step2_tag, n_jobs):
    # 会话
    session = await async_login()
    session_manager = SessionManager(session, time.time(), 3*60*60)

    # 任务池（按 decay 分组 → 每10条一个 pool）
    job_deque = deque()
    for decay, exprs in grouped_exprs.items():
        chunk = 5 if region=="GLB" else 10
        pools = [exprs[i:i+chunk] for i in range(0, len(exprs), chunk)]
        for p in pools:
            job_deque.append((p, decay))

    # AIMD 初始化
    init = int(os.getenv("AIMD_INIT", str(n_jobs)))
    lo   = int(os.getenv("AIMD_MIN_CONCURRENCY", str(max(1, n_jobs//2))))
    hi   = int(os.getenv("AIMD_MAX_CONCURRENCY", str(n_jobs)))
    aimd = _AIMD(cur=init, lo=lo, hi=hi)

    # 写文件缓冲
    out_path = f"{RECORDS_PATH}/{step2_tag}_simulated_alpha_expression.txt"
    out_buffer = []
    BUFFER_FLUSH = 200

    async def worker():
        nonlocal out_buffer
        while job_deque:
            pool, decay = job_deque.popleft()
            res = await _submit_and_fetch(session_manager, pool, region, universe, delay, decay, step2_tag, "SUBINDUSTRY")
            if not res:
                job_deque.append((pool, decay))
                aimd.on_hit()
                await asyncio.sleep(2.0)
                continue
            try:
                for aid, rexpr in res:
                    await async_set_alpha_properties(session_manager.session, aid, name=step2_tag, tags=[step2_tag])
                    out_buffer.append(rexpr)
                if len(out_buffer) >= BUFFER_FLUSH:
                    async with aiofiles.open(out_path, "a") as f:
                        await f.write("\n".join(out_buffer) + "\n")
                    out_buffer = []
                aimd.on_ok()
            except Exception:
                aimd.on_hit()
                await asyncio.sleep(1.0)

    active = set()
    async def orchestrator():
        nonlocal active
        while job_deque or active:
            while len(active) < aimd.cur and job_deque:
                t = asyncio.create_task(worker())
                active.add(t)
                t.add_done_callback(lambda x: active.discard(x))
            await asyncio.sleep(0.5)

    try:
        await orchestrator()
    finally:
        if out_buffer:
            async with aiofiles.open(out_path, "a") as f:
                await f.write("\n".join(out_buffer) + "\n")
        try:
            await session_manager.session.close()
        except Exception:
            pass

# =====================================================================
# 新增：自动发现“跑过的所有数据集”的 step1/step2 标签，并可批量补齐未跑的
# =====================================================================

_TAG_PATTERN = re.compile(r"^(?P<region>[A-Z]{3})_(?P<delay>\d+)_(?P<itype>[A-Z]+)_(?P<universe>[A-Z0-9_]+)_(?P<dataset>[^_]+)_(?P<step>step[12])$")

def _parse_tag(tag: str) -> Optional[Dict[str,str]]:
    m = _TAG_PATTERN.match(tag)
    if not m: return None
    return m.groupdict()

def _scan_tags_local(prefix: str) -> Set[str]:
    """从本地 records 扫描 *_stepX_simulated_alpha_expression.txt 推断 tag。"""
    tags = set()
    rec_dir = RECORDS_PATH if os.path.isdir(RECORDS_PATH) else "records"
    if not os.path.isdir(rec_dir): return tags
    for name in os.listdir(rec_dir):
        if not name.endswith("_simulated_alpha_expression.txt"):
            continue
        tag = name.replace("_simulated_alpha_expression.txt","")
        if tag.startswith(prefix):
            if _parse_tag(tag):
                tags.add(tag)
    return tags

def _scan_tags_platform(prefix: str) -> Set[str]:
    """尽力从平台扫描（若 machine_lib 提供 *tags* 类函数就用；否则返回空集合）。"""
    tags = set()
    try:
        s = login()
        for fn_name in ("list_tags","get_tags","tags"):
            if fn_name in globals():
                try:
                    fn = globals()[fn_name]
                    data = fn(s=s)
                    # 支持 list[str] 或 list[dict{name:...}]
                    if isinstance(data, list):
                        for it in data:
                            if isinstance(it, str) and it.startswith(prefix) and _parse_tag(it):
                                tags.add(it)
                            elif isinstance(it, dict):
                                name = it.get("name") or it.get("tag")
                                if isinstance(name,str) and name.startswith(prefix) and _parse_tag(name):
                                    tags.add(name)
                    break
                except Exception:
                    continue
        s.close()
    except Exception:
        pass
    return tags

def discover_all_step_tags(region: str, delay: int, instrumentType: str, universe: str) -> Dict[str, Dict[str, Optional[str]]]:
    """
    返回：{ dataset_id: { 'step1': tag或None, 'step2': tag或None } }
    优先平台扫描，失败则本地；两者合并。
    """
    prefix = f"{region}_{delay}_{instrumentType}_{universe}_"
    plat = _scan_tags_platform(prefix)
    local= _scan_tags_local(prefix)
    all_tags = sorted(plat | local)
    result: Dict[str, Dict[str, Optional[str]]] = defaultdict(lambda: {"step1": None, "step2": None})
    for tag in all_tags:
        meta = _parse_tag(tag)
        if not meta: continue
        ds = meta["dataset"]
        result[ds][meta["step"]] = tag
    return dict(result)

def print_tag_summary(summary: Dict[str, Dict[str, Optional[str]]]):
    if not summary:
        print(datetime.now(), "[Summary] 没有发现任何匹配的 step1/step2 标签。")
        return
    print(datetime.now(), f"[Summary] 发现数据集共 {len(summary)} 个：")
    done2, only1, none = [], [], []
    for ds, st in sorted(summary.items()):
        if st["step1"] and st["step2"]:
            done2.append(ds)
        elif st["step1"] and not st["step2"]:
            only1.append(ds)
        else:
            none.append(ds)
    print("  - 已完成 step2：", ", ".join(done2) if done2 else "无")
    print("  - 仅有 step1：  ", ", ".join(only1) if only1 else "无")
    print("  - 没有记录：    ", ", ".join(none) if none else "无")

# =====================================================================
# 命令行入口（支持 ALL/自动模式）
# =====================================================================
if __name__ == "__main__":
    # 你可以设置 dataset_id="ALL" 或直接设置环境变量 RUN_ALL=1 来自动发现并逐个跑完未跑的 step2
    dataset_id   = os.getenv("DATASET_ID") or "ALL"  # 你也可以改成默认某个具体数据集
    region       = os.getenv("REGION") or "USA"
    delay        = int(os.getenv("DELAY") or "1")
    instrumentType = os.getenv("INSTRUMENT_TYPE") or "EQUITY"
    universe     = os.getenv("UNIVERSE") or "TOP3000"
    n_jobs       = int(os.getenv("N_JOBS") or "8")
    run_all_flag = os.getenv("RUN_ALL","1") == "1" or dataset_id.upper() == "ALL"

    if not run_all_flag:
        # 常规：只跑一个数据集
        run_task(dataset_id=dataset_id, region=region, delay=delay,
                 instrumentType=instrumentType, universe=universe, n_jobs=n_jobs)
    else:
        # 自动发现 & 批量补齐
        summary = discover_all_step_tags(region, delay, instrumentType, universe)
        print_tag_summary(summary)
        # 按“只有 step1 没有 step2”的顺序跑
        targets = [ds for ds, st in summary.items() if st["step1"] and not st["step2"]]
        if not targets:
            print(datetime.now(), "[AutoRun] 没有需要补跑 step2 的数据集。")
        else:
            print(datetime.now(), f"[AutoRun] 准备补跑 {len(targets)} 个数据集的 step2：{', '.join(targets)}")
            for ds in targets:
                print(datetime.now(), f"[AutoRun] 开始 {ds} 的 step2 …")
                run_task(dataset_id=ds, region=region, delay=delay,
                         instrumentType=instrumentType, universe=universe, n_jobs=n_jobs)
                print(datetime.now(), f"[AutoRun] 结束 {ds} 的 step2。")
        print(datetime.now(), "[AutoRun] 全部处理完毕。")
