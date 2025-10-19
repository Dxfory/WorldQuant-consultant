"""
Zach
"""

# =========================
# A-2（去重） + B-7（轻评估）
# A-3（自适应并发 AIMD）
# A-6（会话复用友好化：单事件循环批次调度）
# =========================
# 用法：保持与原来一致；Step-1 生成 alpha_list 后，会先执行去重与轻评估，
# 再进入自适应批次调度（单事件循环），内部仍调用 simulate_multiple_tasks。

import os
import re
import math
import random
import time
import asyncio
from typing import List, Tuple, Optional
from datetime import datetime
from dataclasses import dataclass  # A-3 需要

# ========= 你原有的依赖（保持不变） =========
from machine_lib import *
from config import *

# ========= 可配置参数（环境变量可覆盖） =========
BATCH_SIZE        = int(os.getenv("ALPHA_BATCH_SIZE", "500"))   # 初始：每批最多发送的表达式数（A-3 将以此为上限）
SIM_MAX_RETRIES   = int(os.getenv("SIM_MAX_RETRIES", "3"))      # 单批最大重试次数
RETRY_BASE_SLEEP  = float(os.getenv("SIM_RETRY_SLEEP", "3"))    # 重试的基础等待（线性递增/仅备用）

# ========= 可选日志（没有 loguru 时回落到 print） =========
try:
    from loguru import logger
    os.makedirs("logs", exist_ok=True)
    logger.add("logs/step1_{time}.log", rotation="1 day", enqueue=True, backtrace=False, diagnose=False)
except Exception:
    class _Logger:
        def info(self, *a, **k): print(*a)
        def warning(self, *a, **k): print(*a)
        def error(self, *a, **k): print(*a)
    logger = _Logger()

# ========= 辅助：分批（备用；A-3 主要使用自适应批调度） =========
def _chunked(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i+size]

# --------------------------------------------
# A-2：规范化去重 + 相似去冗（3-gram Jaccard）
# B-7：无数据轻评估打分（启发式）
# --------------------------------------------

_CANON_SPACES = re.compile(r"\s+")
_CANON_COMMAS = re.compile(r",\s+")
_SAFE_LEN = 1024 * 8

def _canonicalize(expr: str) -> str:
    """表达式规范化，做语法等价去重的基础"""
    if not isinstance(expr, str):
        return str(expr)
    s = expr[:_SAFE_LEN]
    s = _CANON_COMMAS.sub(",", s)
    s = _CANON_SPACES.sub(" ", s)
    return s.strip()

# 轻评估：算子出现情况（启发式）
_OP_PATTERN = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*\(")
_ROBUST_OPS = {
    "rank": 0.8, "zscore": 0.9, "normalize": 0.6, "group_neutralize": 1.0,
    "ts_mean": 0.6, "ts_median": 0.7, "ts_std_dev": 0.5, "ts_rank": 0.6,
    "winsorize": 0.7, "ts_decay_exp_window": 0.4, "ts_regression": 0.4,
}
_PENALIZE_OPS = {
    "kurtosis": 0.2, "skewness": 0.2, "entropy": 0.2, "moment": 0.2
}
# 注意：这是启发式窗口提取，对多参数算子只是近似扫描
_WINDOW_RE = re.compile(r",\s*(\d{2,4})\s*\)")

def _rough_depth(expr: str) -> int:
    d = m = 0
    for ch in expr:
        if ch == '(':
            d += 1
            if d > m: m = d
        elif ch == ')':
            d -= 1
    return m

def _operator_count(expr: str) -> int:
    return len(_OP_PATTERN.findall(expr))

def _light_score(expr: str) -> float:
    """
    无数据的先验打分（启发式）：
    + 稳健算子加分；+ 适度窗口（5~252）加分；
    - 过深嵌套/算子过多/超长窗口轻微减分；
    - 极长表达式轻微减分。
    """
    e = expr.lower()
    score = 0.0

    for k, w in _ROBUST_OPS.items():
        if k in e:
            score += w
    for k, w in _PENALIZE_OPS.items():
        if k in e:
            score -= w

    for m in _WINDOW_RE.finditer(e):
        w = int(m.group(1))
        if 5 <= w <= 252:
            score += 0.15
        elif w > 756:
            score -= 0.2

    depth = _rough_depth(e)
    ops = _operator_count(e)
    score -= max(0, depth - 6) * 0.15
    score -= max(0, ops - 12) * 0.06
    score -= max(0, len(e) - 800) / 1000.0
    return score

_TOKEN_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*|\(|\)|,|\d+\.?\d*")

def _shingles(expr: str, n: int = 3) -> Tuple[str, ...]:
    toks = _TOKEN_RE.findall(expr.lower())[:256]
    if len(toks) < n:
        return tuple(toks)
    return tuple(" ".join(toks[i:i+n]) for i in range(len(toks)-n+1))

def _jaccard(a: Tuple[str, ...], b: Tuple[str, ...]) -> float:
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    inter = len(sa & sb)
    if inter == 0:
        return 0.0
    return inter / float(len(sa | sb))

def _dedup_and_light_filter(alpha_list: List[str],
                            keep_ratio: float = 0.35,
                            top_k: int = 2000,
                            sim_threshold: float = 0.82) -> List[str]:
    """A-2 + B-7 主流程：先规范化去重；轻评估排序；相似去冗；保留 top-k/比例"""
    if not alpha_list:
        return []

    # a) 规范化去重
    seen = set()
    uniq: List[str] = []
    for e in alpha_list:
        c = _canonicalize(e)
        if c not in seen:
            seen.add(c)
            uniq.append(e)
    if len(uniq) <= 64:
        return uniq

    # b) 轻评估打分
    scored = [(e, _light_score(e)) for e in uniq]
    scored.sort(key=lambda x: x[1], reverse=True)

    # c) 先按比例预筛，再做相似去冗（3-gram Jaccard）
    k = min(top_k, max(16, int(len(scored) * keep_ratio)))
    pool = [e for e, _ in scored[:k * 2]]  # 给相似消解留冗余

    selected: List[str] = []
    reps: List[Tuple[str, Tuple[str, ...]]] = []
    for e in pool:
        sh = _shingles(_canonicalize(e), 3)
        dup_like = False
        for _, sh0 in reps:
            if _jaccard(sh, sh0) >= sim_threshold:
                dup_like = True
                break
        if not dup_like:
            reps.append((e, sh))
            selected.append(e)
        if len(selected) >= k:
            break

    return selected if selected else [e for e, _ in scored[:k]]

# --------------------------------------------
# A-3：自适应并发（AIMD）
# A-6：单事件循环跑完整批次（有利于连接/会话复用）
# --------------------------------------------

@dataclass
class _AdaptiveParams:
    n_jobs: int
    batch_size: int

class AdaptiveRateController:
    """AIMD 调度器：根据成功/限流/异常自适应 n_jobs 与批大小。
    - 成功：每 3 个批次稳定成功，n_jobs += 1, batch += 50（均不超过上限）
    - 限流/异常：n_jobs = max(floor(n_jobs*0.7), n_min)，batch = max(floor(batch*0.7), b_min)
    """
    def __init__(self, n_init:int, n_min:int, n_max:int, b_init:int, b_min:int, b_max:int):
        self.n_min, self.n_max = n_min, n_max
        self.b_min, self.b_max = b_min, b_max
        self.params = _AdaptiveParams(n_init, b_init)
        self._stable_ok = 0

    @property
    def n_jobs(self):
        return self.params.n_jobs

    @property
    def batch_size(self):
        return self.params.batch_size

    def _clamp(self):
        self.params.n_jobs   = max(self.n_min, min(self.n_max, self.params.n_jobs))
        self.params.batch_size = max(self.b_min, min(self.b_max, self.params.batch_size))

    def on_success(self):
        self._stable_ok += 1
        if self._stable_ok % 3 == 0:  # 每 3 个批次才小步上调
            self.params.n_jobs += 1
            self.params.batch_size += 50
            self._clamp()

    def on_rate_limit(self, retry_after: Optional[float] = None):
        # 乘性减小
        self.params.n_jobs = int(self.params.n_jobs * 0.7) or self.n_min
        self.params.batch_size = int(self.params.batch_size * 0.7) or self.b_min
        self._stable_ok = 0
        self._clamp()

    def on_other_error(self):
        # 与限流同样处理
        self.on_rate_limit(None)

async def _simulate_one_batch_async(alpha_batch, region, universe, delay, tag, neut, n_jobs):
    """单批异步模拟：内部仍调用 simulate_multiple_tasks（接口与语义不变）"""
    bsz = len(alpha_batch)
    region_list = [(region, universe)] * bsz
    # 若需完全可复现，可改为固定 0：decay_list = [0] * bsz
    decay_list  = [random.randint(0, 10) for _ in range(bsz)]
    delay_list  = [delay] * bsz
    await simulate_multiple_tasks(alpha_batch, region_list, decay_list, delay_list, tag, neut, [], n=n_jobs)

async def _run_all_batches_async(alpha_list, region, universe, delay, tag, neut,
                                 n_init:int, n_min:int, n_max:int,
                                 b_init:int, b_min:int, b_max:int,
                                 max_retries:int = 3):
    """单事件循环内依次运行所有批次；内部自适应调度并发与批量。"""
    ctrl = AdaptiveRateController(n_init, n_min, n_max, b_init, b_min, b_max)

    i = 0
    total = len(alpha_list)
    batch_id = 0

    while i < total:
        # 动态批大小
        bsz = min(ctrl.batch_size, total - i)
        alpha_batch = alpha_list[i:i+bsz]
        batch_id += 1
        print(datetime.now(), f"[Adaptive] 开始批次 #{batch_id} bsz={bsz} n_jobs={ctrl.n_jobs} 进度 {i}/{total}")

        ok = False
        last_err = None
        for attempt in range(1, max_retries+1):
            try:
                await _simulate_one_batch_async(alpha_batch, region, universe, delay, tag, neut, ctrl.n_jobs)
                ok = True
                break
            except Exception as e:
                last_err = e
                emsg = str(e)
                # 识别常见限流关键字（根据 machine_lib 抛出的字符串或 HTTP 文本）
                is_rl = ("SIMULATION_LIMIT_EXCEEDED" in emsg) or ("Too Many Requests" in emsg) or ("429" in emsg)
                if is_rl:
                    ctrl.on_rate_limit(None)
                    wait_s = min(30, 3*attempt)
                    print(datetime.now(), f"[Adaptive] 限流，第{attempt}次重试，降到 n_jobs={ctrl.n_jobs} batch={ctrl.batch_size}；等待 {wait_s}s…")
                    await asyncio.sleep(wait_s)
                else:
                    ctrl.on_other_error()
                    wait_s = min(15, 2*attempt)
                    print(datetime.now(), f"[Adaptive] 异常：{e}；第{attempt}次重试，n_jobs={ctrl.n_jobs} batch={ctrl.batch_size}；等待 {wait_s}s…")
                    await asyncio.sleep(wait_s)

        if ok:
            ctrl.on_success()
            i += bsz
            print(datetime.now(), f"[Adaptive] 完成批次 #{batch_id}，累计完成 {i}/{total}，下次将尝试 n_jobs={ctrl.n_jobs} batch={ctrl.batch_size}")
        else:
            print(datetime.now(), f"[Adaptive] 批次 #{batch_id} 在重试后仍失败（最后错误：{last_err}），跳过该批次…")
            i += bsz  # 跳过该批防止卡住

def run_all_batches_with_adaptive_control(alpha_list, region, universe, delay, tag, neut,
                                          n_init:int, b_init:int):
    """单事件循环跑完整个 Step-1 的所有批次，内置 AIMD 控制。
    - n_jobs 的范围：[max(1, floor(n_init*0.5)) , n_init]
    - batch 的范围：[max(100, floor(b_init*0.5)) , b_init]
    """
    n_min, n_max = max(1, int(n_init*0.5)), max(1, int(n_init))
    b_min, b_max = max(100, int(b_init*0.5)), max(100, int(b_init))

    asyncio.run(_run_all_batches_async(
        alpha_list, region, universe, delay, tag, neut,
        n_init=n_init, n_min=n_min, n_max=n_max,
        b_init=b_init, b_min=b_min, b_max=b_max,
        max_retries=SIM_MAX_RETRIES,
    ))

# ========= 入口：Step-1 主任务（保持你的签名与打印） =========
@while_true_try_decorator
def run_task(dataset_id, region, delay, instrumentType, universe, n_jobs, tag=None):
    delay = int(delay)
    n_jobs = int(n_jobs)

    print(datetime.now(), f"=================您的配置信息==================")
    print(datetime.now(), f"dataset_id: {dataset_id}")
    print(datetime.now(), f"region: {region}")
    print(datetime.now(), f"delay: {delay}")
    print(datetime.now(), f"instrumentType: {instrumentType}")
    print(datetime.now(), f"universe: {universe}")
    print(datetime.now(), f"n_jobs: {n_jobs}")
    print(datetime.now(), f"=============================================")
    time.sleep(2)

    # === 登录 & 拉字段（保持原逻辑）===
    s = login()
    group = get_datafields(s=s, dataset_id=dataset_id, region=region, delay=delay, universe=universe)
    s.close()

    if len(group) == 0:
        print(datetime.now(), f"No data fields found for dataset_id: {dataset_id}, region: {region}, delay: {delay}, universe: {universe}")
        return

    # === tag & 已完成读取（保持原逻辑）===
    if tag is None:
        tag = f"{region}_{delay}_{instrumentType}_{universe}_{dataset_id}_step1"
    completed_file_path = os.path.join(RECORDS_PATH, f"{tag}_simulated_alpha_expression.txt")
    completed_alphas = read_completed_alphas(completed_file_path)

    print(datetime.now(), f"Processing dataset_id: {dataset_id}")

    # === 因子工厂（保持原逻辑）===
    pc_fields = process_datafields(group, "matrix") + process_datafields(group, "vector")
    raw_alpha_list = first_order_factory(first_order_factory(pc_fields, ts_ops + basic_ops), ts_ops + basic_ops)

    # 过滤已完成（保持原逻辑）
    alpha_list = [alpha for alpha in raw_alpha_list if alpha not in completed_alphas]
    if len(alpha_list) <= 1:
        print(datetime.now(), f"{tag} is already completed")
        return
    print(datetime.now(), f"{dataset_id} progress: {len(raw_alpha_list) - len(alpha_list)}/{len(raw_alpha_list)}")

    # === 随机打散（保持原逻辑）===
    random.shuffle(alpha_list)

    # === 关键新增：A-2 去重 + B-7 轻评估（实际生效处）===
    before_cnt = len(alpha_list)
    alpha_list = _dedup_and_light_filter(alpha_list, keep_ratio=0.35, top_k=2000, sim_threshold=0.82)
    after_cnt = len(alpha_list)
    print(datetime.now(), f"[LightFilter] before={before_cnt}, after={after_cnt}, cut={before_cnt - after_cnt}")

    # === 中性化设置（保持原逻辑）===
    if region in ['USA', 'EUR', 'ASI', 'CHN', 'GLB', 'AMR']:
        neut = 'SUBINDUSTRY'
    else:
        neut = 'SUBINDUSTRY'

    # === A-3 + A-6：自适应并发 + 单事件循环（替代原 for-batch 循环）===
    print(datetime.now(), f"[Adaptive] 接管批次调度：起始 n_jobs={n_jobs}, batch={BATCH_SIZE}")
    run_all_batches_with_adaptive_control(
        alpha_list, region, universe, delay, tag, neut,
        n_init=n_jobs, b_init=BATCH_SIZE
    )

    print(datetime.now(), "All tasks completed. Sleeping for 10 seconds...")
    time.sleep(10)
    print(datetime.now(), "Wake up.")

# ========= 命令行入口（支持多个数据集 + 可输入 delay/region/universe，留空用默认） =========
def _ask(prompt: str, default: str, transform=lambda x: x):
    """带默认值的输入：回车则返回默认；否则对输入做 transform"""
    s = input(f"{prompt}（回车默认 {default}）：").strip()
    return transform(s) if s else default

if __name__ == '__main__':
    # 支持逗号或空格分隔多个：例如 model51,sentiment22  shortinterest43
    ds_input = input("请输入要运行的数据集ID（可逗号/空格分隔，如 model51 或 model51,sentiment22 shortinterest43）: ").strip()
    if not ds_input:
        ds_list = ["analyst4"]  # 默认值（防空）
    else:
        parts = []
        for block in ds_input.replace(",", " ").split():
            if block.strip():
                parts.append(block.strip())
        ds_list = parts or ["analyst4"]

    # === 新增：三项可交互输入，默认 delay=0 / region=USA / universe=TOP1000 ===
    # region/universe 统一转大写，避免大小写导致的匹配问题
    delay_str = _ask("请输入 delay（整数）", "0")
    try:
        delay = int(delay_str)
    except Exception:
        print(f"检测到非法 delay 值：{delay_str}，回退为 0")
        delay = 0

    region = _ask("请输入 region（如 USA/EUR/CHN 等）", "USA", lambda x: x.upper())
    universe = _ask("请输入 universe（如 TOP1000/TOP3000 等）", "TOP1000", lambda x: x.upper())

    instrumentType = "EQUITY"
    n_jobs = 3  # 如网络不稳建议先用 2~3，再逐步升

    try:
        for dataset_id in ds_list:
            print("\n" + "="*20 + f" 开始运行 {dataset_id} 的 Step-1 " + "="*20)
            run_task(dataset_id, region, delay, instrumentType, universe, n_jobs)
            print("="*20 + f" 结束 {dataset_id} 的 Step-1 " + "="*20 + "\n")
    except KeyboardInterrupt:
        print("\n⚠️ 检测到人工中断，安全退出。")
