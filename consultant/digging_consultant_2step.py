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
from typing import List, Tuple, Optional
from collections import defaultdict
from datetime import datetime

# =========================
# 轻量：A-2（去重）+ B-7（轻评估）
# =========================
_CANON_SPACES = re.compile(r"\s+")
_CANON_COMMAS = re.compile(r",\s+")
_TOKEN_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*|\(|\)|,|\d+\.?\d*")
_OP_PATTERN = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*\(")
_WINDOW_RE  = re.compile(r",\s*(\d{2,4})\s*\)")
_SAFE_LEN = 1024*8

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

def _dedup_and_light_filter(exprs: List[str], keep_ratio=0.60, top_k=8000, sim_threshold=0.80) -> List[str]:
    """规范化去重 → 轻评估排序 → 3-gram Jaccard 相似去冗"""
    if not exprs: return []
    # 去重
    seen, uniq = set(), []
    for e in exprs:
        c = _canonicalize(e)
        if c not in seen:
            seen.add(c); uniq.append(e)
    if len(uniq) <= 64: return uniq
    # 打分
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
# 更稳健：safe_get_alphas（平台异常退避重试）
# =========================
def safe_get_alphas(start_date, end_date,
                    sharpe_th, fitness_th,
                    next_limit, decay_limit,
                    region, universe, delay, instrumentType,
                    page_size, mode, tag, max_retries=3):
    last_err = None
    for attempt in range(1, max_retries+1):
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
# 主流程（单数据集）
# =========================
@while_true_try_decorator
def run_task(dataset_id, region, delay, instrumentType, universe, n_jobs, tag=None):
    delay = int(delay)
    n_jobs = int(n_jobs)

    print(datetime.now(),f"=================您的二阶段配置信息==================")
    print(datetime.now(),f"dataset_id: {dataset_id}")
    print(datetime.now(),f"region: {region}")
    print(datetime.now(),f"delay: {delay}")
    print(datetime.now(),f"instrumentType: {instrumentType}")
    print(datetime.now(),f"universe: {universe}")
    print(datetime.now(),f"n_jobs: {n_jobs}")
    print(datetime.now(),f"=============================================")
    time.sleep(2)

    # 生成 step1 的 tag
    tag = f"{region}_{delay}_{instrumentType}_{universe}_{dataset_id}_step1"
    step1_tag_list = [tag]

    if len(step1_tag_list) == 0:
        print(datetime.now(),"No step1 tags found.")

    # 确保 records 目录
    try:
        os.makedirs(RECORDS_PATH, exist_ok=True)
    except Exception:
        os.makedirs("records", exist_ok=True)

    for step1_tag in step1_tag_list:
        if 'ILLIQUID' in step1_tag:
            region, delay, instrumentType, ILLIQUID_tag, universe, dataset_id, step_num = step1_tag.split('_')
            universe = f'{ILLIQUID_tag}_{universe}'
        else:
            region, delay, instrumentType, universe, dataset_id, step_num = step1_tag.split('_')

        # —— 轻放宽阈值（更容易承接 step1 结果）——
        if int(delay) == 1:
            sharpe_step2_th = 0.8   # 原 1.0
            fitness_step2_th = 0.4  # 原 0.5
        elif int(delay) == 0:
            sharpe_step2_th = 1.6   # 原 2.0
            fitness_step2_th = 0.8  # 原 1.0
        else:
            print(datetime.now(),"delay must be 0 or 1.")
            continue

        step2_tag = step1_tag.replace('_step1', '_step2')

        # —— 更稳健的获取一阶段入围 ——（退避重试 + 容错解析）
        fo_tracker = safe_get_alphas("2020-01-01", "2029-12-31",
                                     sharpe_step2_th, fitness_step2_th,
                                     100, 100,
                                     region, universe, int(delay), instrumentType,
                                     500, "track", tag=step1_tag)

        fo_layer = prune(fo_tracker['next'] + fo_tracker['decay'],
                         dataset_id, 3)

        if len(fo_layer) == 0:
            print(datetime.now(),'暂时没有满足条件的一阶段因子，请你继续运行digging_consultant_1step.py.')
            continue

        print(datetime.now(),f'qualified expression: {len(fo_layer)}')

        # ===== 生成二阶候选 =====
        so_alpha_list = []
        for expr, decay in fo_layer:
            so_alpha_list.append((expr, decay))
            # 保持原有的二阶分组扩展
            for alpha in get_group_second_order_factory([expr], group_ops):
                so_alpha_list.append((alpha, decay))

        # ===== 去掉已完成 =====
        completed_alphas = read_completed_alphas(f'{RECORDS_PATH}/{step2_tag}_simulated_alpha_expression.txt')
        raw_alpha_list = so_alpha_list
        alpha_list = [alpha_decay for alpha_decay in raw_alpha_list if alpha_decay[0] not in completed_alphas]
        if len(alpha_list) == 0:
            print(datetime.now(),f"已经完成了{len(completed_alphas)}个alpha表达式，一共有{len(raw_alpha_list)}个alpha表达式")
            print(datetime.now(),f"{step2_tag} is done.")
            continue
        print(datetime.now(),"{} progress: {}/{}".format(step2_tag, len(raw_alpha_list) - len(alpha_list), len(raw_alpha_list)))

        # ===== 关键优化：A-2 去重 + B-7 轻评估 =====
        before_cnt = len(alpha_list)
        filtered_exprs = _dedup_and_light_filter([e for e, _ in alpha_list],
                                                 keep_ratio=0.60, top_k=8000, sim_threshold=0.80)
        keep_set = set(filtered_exprs)
        alpha_list = [(e, d) for (e, d) in alpha_list if e in keep_set]
        after_cnt = len(alpha_list)
        print(datetime.now(), f"[LightFilter/Step2] before={before_cnt}, after={after_cnt}, cut={before_cnt - after_cnt}")

        # ===== 原有分组与提交（保持不变） =====
        grouped_dict = defaultdict(list)
        for alpha, decay in alpha_list:
            grouped_dict[decay].append(alpha)

        for decay in grouped_dict:
            sub_alpha_list = grouped_dict[decay]
            decay_list = [decay] * len(sub_alpha_list)
            delay_list = [int(delay)] * len(sub_alpha_list)
            region_list = [(region, universe)] * len(sub_alpha_list)

            # 中性化（保持原逻辑）
            if region in ['USA', 'EUR', 'ASI', 'CHN', 'GLB', 'AMR']:
                neut = 'SUBINDUSTRY'
            else:
                neut = 'SUBINDUSTRY'

            # 仍然调用你原来的 simulate_multiple_tasks，不改接口不改语义
            asyncio.run(simulate_multiple_tasks(sub_alpha_list, region_list, decay_list, delay_list,
                                                step2_tag, neut,
                                                [], n=n_jobs))

    print(datetime.now(),"All done. Sleep 600s..")
    time.sleep(600)
    print(datetime.now(),"Wake up.")


# =========================
# 命令行入口：支持多个数据集（逗号/空格分隔）+ 可交互输入 delay/region/universe（留空取默认）
# =========================
def _ask(prompt: str, default: str, transform=lambda x: x):
    """带默认值的输入：回车则返回默认；否则对输入做 transform"""
    s = input(f"{prompt}（回车默认 {default}）：").strip()
    return transform(s) if s else default

if __name__ == "__main__":
    ds_input = input("请输入要运行的数据集ID（可逗号/空格分隔，如 model51 或 model51,sentiment22 shortinterest43）: ").strip()
    if not ds_input:
        ds_list = ["analyst4"]   # 温和默认，防空
    else:
        parts = []
        for block in ds_input.replace(",", " ").split():
            b = block.strip()
            if b:
                parts.append(b)
        ds_list = parts or ["analyst4"]

    # === 新增：三项可交互输入，留空用默认 ===
    # 默认要求：delay=0、region=USA、universe=TOP1000
    delay_str = _ask("请输入 delay（整数）", "0")
    try:
        delay = int(delay_str)
    except Exception:
        print(f"检测到非法 delay 值：{delay_str}，回退为 0")
        delay = 0

    region   = _ask("请输入 region（如 USA/EUR/CHN 等）", "USA", lambda x: x.upper())
    universe = _ask("请输入 universe（如 TOP1000/TOP3000 等）", "TOP1000", lambda x: x.upper())

    instrumentType = "EQUITY"
    n_jobs = 8  # 保持你原来的默认

    try:
        for ds in ds_list:
            print("\n" + "="*20 + f" 开始运行 {ds} 的 Step-2 " + "="*20)
            run_task(
                dataset_id=ds,
                region=region,
                delay=delay,
                instrumentType=instrumentType,
                universe=universe,
                n_jobs=n_jobs
            )
            print("="*20 + f" 结束 {ds} 的 Step-2 " + "="*20 + "\n")
    except KeyboardInterrupt:
        print("\n⚠️ 检测到人工中断，安全退出。")




