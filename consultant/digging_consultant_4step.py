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
from typing import List, Tuple, Optional, Dict
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

    print(datetime.now(),f"=================您的四阶段配置信息==================")
    print(datetime.now(),f"dataset_id: {dataset_id}")
    print(datetime.now(),f"region: {region}")
    print(datetime.now(),f"delay: {delay}")
    print(datetime.now(),f"instrumentType: {instrumentType}")
    print(datetime.now(),f"universe: {universe}")
    print(datetime.now(),f"n_jobs: {n_jobs}")
    print(datetime.now(),f"=============================================")
    time.sleep(2)

    # 生成 step3 的 tag
    tag = f"{region}_{delay}_{instrumentType}_{universe}_{dataset_id}_step3"
    step3_tag_list = [tag]

    # 确保 records 目录存在
    records_dir = RECORDS_PATH if os.path.isdir(RECORDS_PATH) else "records"
    os.makedirs(records_dir, exist_ok=True)

    for step3_tag in step3_tag_list:
        if 'ILLIQUID' in step3_tag:
            region, delay, instrumentType, ILLIQUID_tag, universe, dataset_id, step_num = step3_tag.split('_')
            universe = f'{ILLIQUID_tag}_{universe}'
        else:
            region, delay, instrumentType, universe, dataset_id, step_num = step3_tag.split('_')

        # —— 阈值：保持你原逻辑 —— #
        if int(delay) == 1:
            sharpe_step3_th = 1.5
            fitness_step3_th = 0.85
        elif int(delay) == 0:
            sharpe_step3_th = 2.75
            fitness_step3_th = 1.5
        else:
            print(datetime.now(),"delay must be 0 or 1.")
            continue

        step4_tag = step3_tag.replace('_step3', '_step4')

        # 更稳健的拉三阶段入围（退避重试 + 容错）
        to_tracker = safe_get_alphas("2024-10-07", "2029-12-31",
                                     sharpe_step3_th, fitness_step3_th,
                                     100, 100,
                                     region, universe, int(delay), instrumentType,
                                     500, "track", tag=step3_tag)

        to_layer = prune(to_tracker['next'] + to_tracker['decay'], dataset_id, 3)

        if len(to_layer) == 0:
            print(datetime.now(), f'tag: {step3_tag} 暂时没有满足条件的三阶段因子，请你继续运行digging_consultant_3step.py.')
            continue

        # ===== 模板展开（保持原调用） =====
        th_alpha_list = []
        for expr, decay in to_layer:
            for alpha in template_factory(expr, region):
                th_alpha_list.append((alpha, decay))
        print(datetime.now(), f"[Step4] template_factory 生成：{len(th_alpha_list)}")

        # ===== 去掉已完成 =====
        completed_alphas = read_completed_alphas(f'{records_dir}/{step4_tag}_simulated_alpha_expression.txt')
        raw_alpha_list = th_alpha_list
        alpha_list = [ad for ad in raw_alpha_list if ad[0] not in completed_alphas]
        if len(alpha_list) == 0:
            print(datetime.now(), f"已经完成了{len(completed_alphas)}个alpha表达式，一共有{len(raw_alpha_list)}个alpha表达式")
            print(datetime.now(), f"{step4_tag} is done.")
            continue
        print(datetime.now(), "{} progress: {}/{}".format(step4_tag, len(raw_alpha_list) - len(alpha_list), len(raw_alpha_list)))

        # ===== 关键优化：A-2 去重 + B-7 轻评估（对模板结果） =====
        before_cnt = len(alpha_list)
        filtered_exprs = _dedup_and_light_filter([e for e,_ in alpha_list],
                                                 keep_ratio=0.60, top_k=8000, sim_threshold=0.80)
        keep_set = set(filtered_exprs)
        alpha_list = [(e,d) for (e,d) in alpha_list if e in keep_set]
        after_cnt = len(alpha_list)
        print(datetime.now(), f"[LightFilter/Step4] before={before_cnt}, after={after_cnt}, cut={before_cnt - after_cnt}")

        # ===== decay 分组并提交（保持语义与接口不变） =====
        grouped_dict: Dict[int, List[str]] = defaultdict(list)
        for e, d in alpha_list:
            grouped_dict[d].append(e)

        for decay in grouped_dict:
            sub_alpha_list = grouped_dict[decay]
            decay_list = [decay] * len(sub_alpha_list)
            delay_list = [int(delay)] * len(sub_alpha_list)
            region_list = [(region, universe)] * len(sub_alpha_list)  # 扩展 region_list

            # 中性化层级（保持原逻辑）
            if region in ['USA', 'EUR', 'ASI', 'CHN']:
                neut = 'SUBINDUSTRY'
            elif region in ['GLB']:
                neut = "SUBINDUSTRY"
            elif region in ['AMR']:
                neut = "SUBINDUSTRY"
            else:
                neut = 'SUBINDUSTRY'

            asyncio.run(simulate_multiple_tasks(sub_alpha_list, region_list, decay_list, delay_list,
                                                step4_tag, neut, [], n=n_jobs))

    print(datetime.now(), "All done. Sleep 600s...")
    time.sleep(600)
    print(datetime.now(), "Wake up.")

# =========================
# 命令行入口：多数据集 + 可交互输入（留空取默认）
# 默认：delay=0, region=USA, universe=TOP1000
# =========================
def _ask(prompt: str, default: str, transform=lambda x: x):
    """带默认值的输入：回车用默认，否则做 transform 处理"""
    s = input(f"{prompt}（回车默认 {default}）：").strip()
    return transform(s) if s else default

if __name__ == "__main__":
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
            print("\n" + "="*20 + f" 开始运行 {ds} 的 Step-4 " + "="*20)
            run_task(
                dataset_id=ds,
                region=region,
                delay=delay,
                instrumentType=instrumentType,
                universe=universe,
                n_jobs=n_jobs
            )
            print("="*20 + f" 结束 {ds} 的 Step-4 " + "="*20 + "\n")
    except KeyboardInterrupt:
        print("\n⚠️ 检测到人工中断，安全退出。")
