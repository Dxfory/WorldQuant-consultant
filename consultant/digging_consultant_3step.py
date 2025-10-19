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
from typing import List, Tuple, Optional, Deque, Dict
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime

# =========================
# 可调参数（环境变量不设则用默认）
# =========================
BATCH_SIZE        = int(os.getenv("ALPHA_BATCH_SIZE", "500"))     # 单批表达式数上限（AIMD 以内）
SIM_MAX_RETRIES   = int(os.getenv("SIM_MAX_RETRIES", "3"))        # 单批最大重试
RETRY_BASE_SLEEP  = float(os.getenv("SIM_RETRY_SLEEP", "3"))      # 重试基础等待

# 轻筛旋钮（Step-3 trade_when 的表达式端）
KEEP_RATIO = float(os.getenv("ALPHA_KEEP_RATIO", "0.60"))
TOP_K      = int(os.getenv("ALPHA_TOPK", "8000"))
SIM_TH     = float(os.getenv("ALPHA_SIM_TH", "0.80"))

# AIMD 并发边界（不设则用 run_task 的 n_jobs 推导）
AIMD_MIN_ENV = os.getenv("AIMD_MIN_CONCURRENCY")
AIMD_MAX_ENV = os.getenv("AIMD_MAX_CONCURRENCY")

# =========================
# 轻筛：A-2 去重 + B-7 轻评估
# =========================
_CANON_SPACES = re.compile(r"\s+")
_CANON_COMMAS = re.compile(r",\s+")
_TOKEN_RE     = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*|\(|\)|,|\d+\.?\d*")
_OP_PATTERN   = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*\(")
_WINDOW_RE    = re.compile(r",\s*(\d{2,4})\s*\)")
_SAFE_LEN     = 1024*8

_ROBUST_OPS = {
    "rank": 0.8, "zscore": 0.9, "normalize": 0.6,
    "ts_mean": 0.6, "ts_median": 0.7, "ts_std_dev": 0.5, "ts_rank": 0.6,
    "winsorize": 0.7, "group_neutralize": 0.6, "group_rank": 0.6, "group_zscore": 0.6,
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

def _dedup_and_light_filter(exprs: List[str], keep_ratio=KEEP_RATIO, top_k=TOP_K, sim_threshold=SIM_TH) -> List[str]:
    if not exprs: return []
    # 规范化去重
    seen, uniq = set(), []
    for e in exprs:
        c = _canonicalize(e)
        if c not in seen:
            seen.add(c); uniq.append(e)
    if len(uniq) <= 64: return uniq
    # 轻评估排序
    scored = [(e, _light_score(e)) for e in uniq]
    scored.sort(key=lambda x: x[1], reverse=True)
    k = min(top_k, max(32, int(len(scored)*keep_ratio)))
    pool = [e for e,_ in scored[:k*2]]  # 扩一点供相似消解
    # 近似去冗
    reps, out = [], []
    for e in pool:
        sh = _shingles(_canonicalize(e),3)
        if any(_jaccard(sh,sh0)>=sim_threshold for _,sh0 in reps):
            continue
        reps.append((e,sh)); out.append(e)
        if len(out) >= k: break
    return out if out else [e for e,_ in scored[:k]]

# =========================
# 更稳健：safe_get_alphas（平台异常退避重试）
# =========================
def safe_get_alphas(start_date, end_date,
                    sharpe_th, fitness_th,
                    next_limit, decay_limit,
                    region, universe, delay, instrumentType,
                    page_size, mode, tag, max_retries: int = 3):
    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            data = get_alphas(start_date, end_date,
                              sharpe_th, fitness_th,
                              next_limit, decay_limit,
                              region, universe, delay, instrumentType,
                              page_size, mode, tag=tag)
            out = {"next": [], "decay": []}
            if isinstance(data, dict):
                nx = data.get("next", []) or []
                dc = data.get("decay", []) or []
                if isinstance(nx, list): out["next"] = nx
                if isinstance(dc, list): out["decay"] = dc
                return out
            return {"next": [], "decay": []}
        except Exception as e:
            last_err = e
            time.sleep(min(5, 1.5 * attempt))
            page_size = max(50, int(page_size * 0.7))
    print(datetime.now(), f"[safe_get_alphas] fallback empty due to: {last_err}")
    return {"next": [], "decay": []}

# =========================
# AIMD 并发控制（A-3）
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
# 单批提交（复用你现有 simulate_multiple_tasks）
# =========================
async def _run_one_batch(alpha_batch: List[str],
                         region: str, universe: str, delay: int, decay: int,
                         tag: str, neut: str, n_jobs: int):
    bsz = len(alpha_batch)
    region_list = [(region, universe)] * bsz
    decay_list  = [decay] * bsz
    delay_list  = [delay] * bsz
    await simulate_multiple_tasks(alpha_batch, region_list, decay_list, delay_list, tag, neut, [], n=n_jobs)

async def _run_all_batches(alpha_by_decay: Dict[int, List[str]],
                           region: str, universe: str, delay: int, tag: str,
                           n_jobs_init: int):
    # AIMD 范围
    n_min = int(AIMD_MIN_ENV) if AIMD_MIN_ENV else max(1, n_jobs_init // 2)
    n_max = int(AIMD_MAX_ENV) if AIMD_MAX_ENV else max(1, n_jobs_init)
    aimd  = _AIMD(cur=n_jobs_init, lo=n_min, hi=n_max)

    # 生成批队列
    jobs: Deque[Tuple[int, List[str]]] = deque()
    for decay, exprs in alpha_by_decay.items():
        # 按当前 BATCH_SIZE 切块
        for i in range(0, len(exprs), BATCH_SIZE):
            jobs.append((decay, exprs[i:i+BATCH_SIZE]))

    # 中性化（与你原逻辑一致）
    neut = 'SUBINDUSTRY'

    active = set()
    async def worker():
        nonlocal jobs, aimd
        while jobs:
            decay, batch = jobs.popleft()
            ok = False
            last_err = None
            for attempt in range(1, SIM_MAX_RETRIES+1):
                try:
                    await _run_one_batch(batch, region, universe, delay, decay, tag, neut, aimd.cur)
                    ok = True
                    break
                except Exception as e:
                    last_err = e
                    emsg = str(e)
                    is_rl = ("SIMULATION_LIMIT_EXCEEDED" in emsg) or ("Too Many Requests" in emsg) or ("429" in emsg)
                    if is_rl:
                        aimd.on_hit()
                        wait_s = min(30, RETRY_BASE_SLEEP*attempt)
                        print(datetime.now(), f"[Adaptive] 限流，降到 n_jobs={aimd.cur}；{wait_s:.1f}s 后重试…")
                        await asyncio.sleep(wait_s)
                    else:
                        aimd.on_hit()
                        wait_s = min(20, RETRY_BASE_SLEEP*attempt)
                        print(datetime.now(), f"[Adaptive] 异常：{e}；降到 n_jobs={aimd.cur}；{wait_s:.1f}s 后重试…")
                        await asyncio.sleep(wait_s)
            if ok:
                aimd.on_ok()

    async def orchestrator():
        nonlocal active
        while jobs or active:
            while jobs and len(active) < aimd.cur:
                t = asyncio.create_task(worker())
                active.add(t)
                t.add_done_callback(lambda x: active.discard(x))
            await asyncio.sleep(0.5)

    print(datetime.now(), f"[Adaptive] 接管批次调度：起始 n_jobs={n_jobs_init}, batch={BATCH_SIZE}")
    await orchestrator()

# =========================
# Step-3 主流程（单数据集）
# =========================
@while_true_try_decorator
def run_task(dataset_id, region, delay, instrumentType, universe, n_jobs, tag=None):
    delay = int(delay)
    n_jobs = int(n_jobs)
    print(datetime.now(),f"=================您的三阶段配置信息==================")
    print(datetime.now(),f"dataset_id: {dataset_id}")
    print(datetime.now(),f"region: {region}")
    print(datetime.now(),f"delay: {delay}")
    print(datetime.now(),f"instrumentType: {instrumentType}")
    print(datetime.now(),f"universe: {universe}")
    print(datetime.now(),f"n_jobs: {n_jobs}")
    print(datetime.now(),f"=============================================")
    time.sleep(2)

    # 生成 step2 的 tag
    tag = f"{region}_{delay}_{instrumentType}_{universe}_{dataset_id}_step2"
    step2_tag_list = [tag]

    records_dir = RECORDS_PATH if os.path.isdir(RECORDS_PATH) else "records"
    os.makedirs(records_dir, exist_ok=True)

    for step2_tag in step2_tag_list:
        if 'ILLIQUID' in step2_tag:
            region, delay, instrumentType, ILLIQUID_tag, universe, dataset_id, step_num = step2_tag.split('_')
            universe = f'{ILLIQUID_tag}_{universe}'
        else:
            region, delay, instrumentType, universe, dataset_id, step_num = step2_tag.split('_')

        # 阈值保持原逻辑
        if int(delay) == 1:
            sharpe_step3_th = 1.2
            fitness_step3_th = 0.75
        elif int(delay) == 0:
            sharpe_step3_th = 2.6
            fitness_step3_th = 1.4
        else:
            print(datetime.now(),"delay must be 0 or 1.")
            continue

        step3_tag = step2_tag.replace('_step2', '_step3')

        # 拉二阶段入围（稳健）
        so_tracker = safe_get_alphas("2024-10-07", "2029-12-31",
                                     sharpe_step3_th, fitness_step3_th,
                                     100, 100,
                                     region, universe, int(delay), instrumentType,
                                     500, "track", tag=step2_tag)

        so_layer = prune(so_tracker['next'] + so_tracker['decay'], dataset_id, 3)

        # trade_when 展开
        th_alpha_list: List[Tuple[str,int]] = []
        for expr, decay in so_layer:
            for alpha in trade_when_factory("trade_when", expr, region, delay):
                th_alpha_list.append((alpha, decay))
        print(datetime.now(), f"[Step3] trade_when 生成：{len(th_alpha_list)}")

        # 已完成过滤
        completed_alphas = read_completed_alphas(f'{records_dir}/{step3_tag}_simulated_alpha_expression.txt')
        raw_alpha_list = th_alpha_list
        alpha_list = [ad for ad in raw_alpha_list if ad[0] not in completed_alphas]
        if len(alpha_list) == 0:
            print(datetime.now(),f"已经完成了{len(completed_alphas)}个alpha表达式，一共有{len(raw_alpha_list)}个alpha表达式")
            print(datetime.now(),f"{step3_tag} is done.")
            continue
        print(datetime.now(), "{} progress: {}/{}".format(step3_tag, len(raw_alpha_list) - len(alpha_list), len(raw_alpha_list)))

        # —— A-2 + B-7 轻筛（对 trade_when 结果）——
        before_cnt = len(alpha_list)
        filtered_exprs = _dedup_and_light_filter([e for e,_ in alpha_list])
        keep_set = set(filtered_exprs)
        alpha_list = [(e,d) for (e,d) in alpha_list if e in keep_set]
        after_cnt = len(alpha_list)
        print(datetime.now(), f"[LightFilter/Step3] before={before_cnt}, after={after_cnt}, cut={before_cnt - after_cnt}")

        # decay 分组 → 生成批队列 → 单事件循环 + AIMD
        grouped: Dict[int, List[str]] = defaultdict(list)
        for e,d in alpha_list:
            grouped[d].append(e)

        asyncio.run(_run_all_batches(grouped, region, universe, int(delay), step3_tag, n_jobs))

    print(datetime.now(),"All done. Sleep 600s...")
    time.sleep(600)
    print(datetime.now(),"Wake up.")

# =========================
# 命令行入口（多数据集 + 可交互输入，留空走默认）
# 默认：delay=0，region=USA，universe=TOP1000
# =========================
def _ask(prompt: str, default: str, transform=lambda x: x):
    """带默认值的输入：回车用默认，否则做 transform 处理"""
    s = input(f"{prompt}（回车默认 {default}）：").strip()
    return transform(s) if s else default

if __name__ == "__main__":
    # 支持逗号或空格分隔：model51,sentiment22 shortinterest43
    ds_input = input("请输入要运行的数据集ID（可逗号/空格分隔，如 model51 或 model51,sentiment22 shortinterest43）: ").strip()
    if not ds_input:
        ds_list = ["analyst4"]   # 防空
    else:
        parts = []
        for block in ds_input.replace(",", " ").split():
            b = block.strip()
            if b:
                parts.append(b)
        ds_list = parts or ["analyst4"]

    # === 新增：三项可交互输入，留空用默认 ===
    delay_str = _ask("请输入 delay（整数）", "0")
    try:
        delay = int(delay_str)
    except Exception:
        print(f"检测到非法 delay 值：{delay_str}，回退为 0")
        delay = 0

    region   = _ask("请输入 region（如 USA/EUR/CHN 等）", "USA",    lambda x: x.upper())
    universe = _ask("请输入 universe（如 TOP1000/TOP3000 等）", "TOP1000", lambda x: x.upper())

    instrumentType = "EQUITY"
    n_jobs = 8  # 保持你的默认

    try:
        for ds in ds_list:
            print("\n" + "="*20 + f" 开始运行 {ds} 的 Step-3 " + "="*20)
            run_task(
                dataset_id=ds,
                region=region,
                delay=delay,
                instrumentType=instrumentType,
                universe=universe,
                n_jobs=n_jobs
            )
            print("="*20 + f" 结束 {ds} 的 Step-3 " + "="*20 + "\n")
    except KeyboardInterrupt:
        print("\n⚠️ 检测到人工中断，安全退出。")

