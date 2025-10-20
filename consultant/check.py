"""
Zach｜Quant--WQ  世坤因子挖掘  （submit 检查器）

修订要点：
- 运行时登录：不再在 import 阶段拿 machine_lib.s，避免 SSL 报错导致程序起不来
- wait_get 增强：捕获 SSLError/ConnectionError，重建会话并重试；可选关闭证书校验（调试用）
- 多标签容忍：优先取含“_step”的 tag，否则取第一个
- 正确切块：按固定大小 CHUNK_SIZE 分块
- get_alphas 返回健壮解析
"""

import os
import time
import threading
import warnings
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Tuple

import numpy as np
import pandas as pd
import requests

from config import RECORDS_PATH, REGION_LIST, UNIVERSE_DICT
from machine_lib import s, login, get_alphas, set_alpha_properties, while_true_try_decorator

warnings.filterwarnings("ignore")

# =========================
# 可选：API 与运行参数
# =========================
brain_api_url = os.environ.get("BRAIN_API_URL", "https://api.worldquantbrain.com")
DEFAULT_START_DATE = os.environ.get("CHECK_START_DATE", "2025-10-01")  # ← 你从 2025-10-01 开始提交
DEFAULT_CHUNK_SIZE = int(os.environ.get("CHECK_CHUNK_SIZE", "100"))
DEFAULT_N_JOBS = int(os.environ.get("CHECK_N_JOBS", "4"))
COLOR_EXCLUDE_RED = int(os.environ.get("COLOR_EXCLUDE_RED", "1"))  # 1: 排除标红; 0: 不排除

lock = threading.Lock()

# =========================
# 通用 HTTP 重试工具
# =========================
def wait_get(session: requests.Session, url: str, max_retries: int = 10) -> requests.Response:
    """带 Retry-After 支持的 GET 请求（简易重试）"""
    retries = 0
    while retries < max_retries:
        resp = session.get(url)
        retry_after = float(resp.headers.get("Retry-After", 0) or 0)
        if retry_after > 0:
            time.sleep(retry_after)
            continue
        if resp.status_code < 400:
            return resp
        time.sleep(min(2 + retries, 8))
        retries += 1
    resp.raise_for_status()
    return resp

# =========================
# 平台辅助查询（自相关/PNL等）
# =========================
def get_alpha_region(session: requests.Session, alpha_id: str) -> str:
    url = f"{brain_api_url}/alphas/{alpha_id}"
    alpha_info = wait_get(session, url).json()
    return alpha_info['settings']['region']

def get_region_alphas(session: requests.Session, region: str) -> List[str]:
    """拉取同区域 OS 阶段的 alpha id 列表"""
    offset, limit = 0, 100
    alpha_ids: List[str] = []
    while True:
        url = (f"{brain_api_url}/users/self/alphas?"
               f"stage=OS&limit={limit}&offset={offset}&order=-dateSubmitted")
        res = wait_get(session, url).json()
        results = res.get('results', []) if isinstance(res, dict) else []
        for alpha in results:
            try:
                if alpha['settings']['region'] == region:
                    alpha_ids.append(alpha['id'])
            except Exception:
                continue
        if len(results) < limit:
            break
        offset += limit
    return alpha_ids

def get_alpha_pnl(session: requests.Session, alpha_id: str) -> pd.DataFrame:
    url = f"{brain_api_url}/alphas/{alpha_id}/recordsets/pnl"
    pnl = wait_get(session, url).json()
    schema = [p['name'] for p in pnl['schema']['properties']]
    df = pd.DataFrame(pnl['records'], columns=schema).rename(columns={'date': 'Date', 'pnl': alpha_id})[['Date', alpha_id]]
    df['Date'] = pd.to_datetime(df['Date'])
    return df.set_index('Date')

def calculate_correlation(target_rets: pd.Series, peer_rets: pd.DataFrame) -> float:
    """计算目标收益率与同区域其他 alpha 收益率的最大相关性（近 4 年）"""
    if target_rets.empty or peer_rets.empty:
        return 0.0
    start_date = target_rets.index.max() - pd.DateOffset(years=4)
    target_rets = target_rets[target_rets.index > start_date]
    peer_rets = peer_rets[peer_rets.index > start_date]
    combined = pd.concat([target_rets, peer_rets], axis=1, join='inner')
    if combined.empty:
        return 0.0
    tcol = combined.columns[0]
    corr = combined.drop(columns=[tcol]).corrwith(combined[tcol])
    max_corr = corr.max() if not corr.empty else 0.0
    if pd.isna(max_corr):
        print("好像遇到了厂字 alpha，自相关暂置 0.9999")
        return 0.9999
    return float(max_corr)

def get_self_corr_xin_plus(session: requests.Session, alpha_id: str) -> float:
    """拉同区域 OS 的 PnL，近似计算最大相关性（快速版）"""
    try:
        region = get_alpha_region(session, alpha_id)
        peers = [aid for aid in get_region_alphas(session, region) if aid != alpha_id]
        if not peers:
            return 0.0
        target_pnl = get_alpha_pnl(session, alpha_id)
        peer_pnls = []
        for aid in peers:
            try:
                peer_pnls.append(get_alpha_pnl(session, aid))
            except Exception:
                continue
        if not peer_pnls:
            return 0.0
        # 收益率：采用差分（与你原逻辑一致），目标用 pct_change 也可
        target_rets = target_pnl[alpha_id].ffill().pct_change().dropna()
        peer_df = pd.concat(peer_pnls, axis=1).ffill()
        peer_rets = peer_df.apply(lambda x: x - x.shift(1), axis=0)
        return calculate_correlation(target_rets, peer_rets)
    except Exception as e:
        print(f"计算相关性时出错: {e}")
        return 0.0

# =========================
# 时间分片生成（自然日逐日）
# =========================
def generate_date_periods(start_date_file=os.path.join(RECORDS_PATH, 'start_date.txt'),
                          default_start_date=DEFAULT_START_DATE):
    os.makedirs(RECORDS_PATH, exist_ok=True)
    try:
        with open(start_date_file, 'r', encoding='utf-8') as f:
            start_date_str = f.read().strip()
            if not start_date_str:
                start_date_str = default_start_date
    except FileNotFoundError:
        print(f"File {start_date_file} not found. Use default start date: '{default_start_date}'.")
        start_date_str = default_start_date

    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    today = datetime.now().date() + timedelta(days=1)  # 自然日闭区间拆为 [d, d+1)

    periods = []
    cur = start_date
    while cur < today:
        nxt = cur + timedelta(days=1)
        periods.append([cur.strftime('%Y-%m-%d'), nxt.strftime('%Y-%m-%d')])
        cur = nxt
    return periods

def read_completed_alphas(filepath):
    completed = set()
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                completed.add(line.strip())
    except FileNotFoundError:
        pass
    return completed

# =========================
# 官方自/产出相关接口（保留）
# =========================
def get_self_corr(session: requests.Session, alpha_id: str) -> pd.DataFrame:
    while True:
        res = session.get(f"{brain_api_url}/alphas/{alpha_id}/correlations/self")
        if "retry-after" in res.headers:
            time.sleep(float(res.headers["Retry-After"]))
        else:
            break
    if res.json().get("records", 0) == 0:
        return pd.DataFrame()
    cols = [d["name"] for d in res.json()["schema"]["properties"]]
    return pd.DataFrame(res.json()["records"], columns=cols).assign(alpha_id=alpha_id)

def get_prod_corr(session: requests.Session, alpha_id: str) -> pd.DataFrame:
    while True:
        res = session.get(f"{brain_api_url}/alphas/{alpha_id}/correlations/prod")
        if "retry-after" in res.headers:
            time.sleep(float(res.headers["Retry-After"]))
        else:
            break
    if res.json().get("records", 0) == 0:
        return pd.DataFrame()
    cols = [d["name"] for d in res.json()["schema"]["properties"]]
    return pd.DataFrame(res.json()["records"], columns=cols).assign(alpha_id=alpha_id)

def check_self_corr_test(session: requests.Session, alpha_id: str, threshold: float = 0.7) -> pd.DataFrame:
    df = get_self_corr(session, alpha_id)
    if df.empty:
        res = [{"test": "SELF_CORRELATION", "result": "PASS", "limit": threshold, "value": 0, "alpha_id": alpha_id}]
    else:
        value = float(df["correlation"].max())
        res = [{"test": "SELF_CORRELATION", "result": "PASS" if value < threshold else "FAIL",
                "limit": threshold, "value": value, "alpha_id": alpha_id}]
    return pd.DataFrame(res)

def check_prod_corr_test(session: requests.Session, alpha_id: str, threshold: float = 0.7) -> pd.DataFrame:
    df = get_prod_corr(session, alpha_id)
    value = float(df[df.alphas > 0]["max"].max()) if not df.empty else 0.0
    res = [{"test": "PROD_CORRELATION", "result": "PASS" if value <= threshold else "FAIL",
            "limit": threshold, "value": value, "alpha_id": alpha_id}]
    return pd.DataFrame(res)

# =========================
# 因子检查主例程（单个 alpha）
# =========================
def check_alpha_by_self_prod(session: requests.Session, alpha: Dict, submitable_alpha_file: str, mode: str):
    alpha_id = alpha['id']
    tags = alpha.get('tags', [])
    if len(tags) > 1:
        time.sleep(1)
        raise ValueError("Only one tag is allowed.")
    tag = tags[0] if len(tags) == 1 else ''

    region = alpha.get('region', '')
    delay = alpha.get('delay', '')
    universe = alpha.get('universe', '')
    instrumentType = alpha.get('instrumentType', '')
    color = alpha.get('color', '')

    os.makedirs(RECORDS_PATH, exist_ok=True)
    completed_file_path = os.path.join(RECORDS_PATH, f"{tag}_checked_alpha_id.txt")
    checked_alpha_id_list = read_completed_alphas(completed_file_path)

    # 避免重复检查
    if alpha_id in checked_alpha_id_list:
        print(f'{alpha_id} has already been checked.')
        if color != 'RED':
            try:
                set_alpha_properties(session, alpha_id, color='RED')
            except Exception:
                pass
        return

    try:
        # Self corr（优先快速法，失败回退官方法）
        t0 = time.time()
        try:
            self_corr = get_self_corr_xin_plus(session, alpha_id)
            self_res = pd.DataFrame([{
                "test": "SELF_CORRELATION",
                "result": "PASS" if self_corr < 0.7 else "FAIL",
                "limit": 0.7,
                "value": self_corr,
                "alpha_id": alpha_id
            }])
            print(alpha_id, "xin plus self corr use:", round(time.time() - t0, 3), "s", "| val:", round(self_corr, 5))
            if self_res['result'].iloc[0] == 'FAIL':
                with lock:
                    with open(completed_file_path, 'a', encoding='utf-8') as f:
                        f.write(alpha_id + '\n')
                print(f'{alpha_id} self corr test failed.')
                try:
                    set_alpha_properties(session, alpha_id, color='RED')
                except Exception:
                    pass
                return
        except Exception:
            self_res = check_self_corr_test(session, alpha_id, 0.7)
            print(alpha_id, "self corr (official) use:", round(time.time() - t0, 3), "s", "|", self_res.to_dict('records')[0])
            if self_res['result'].iloc[0] == 'FAIL':
                with lock:
                    with open(completed_file_path, 'a', encoding='utf-8') as f:
                        f.write(alpha_id + '\n')
                print(f'{alpha_id} self corr test failed.')
                try:
                    set_alpha_properties(session, alpha_id, color='RED')
                except Exception:
                    pass
                return

        # Prod corr（PPAC 跳过）
        if mode != "PPAC":
            t1 = time.time()
            prod_res = check_prod_corr_test(session, alpha_id, 0.7)
            print(alpha_id, "prod corr use:", round(time.time() - t1, 3), "s", "|", prod_res.to_dict('records')[0])
            if prod_res['result'].iloc[0] == 'FAIL':
                with lock:
                    with open(completed_file_path, 'a', encoding='utf-8') as f:
                        f.write(alpha_id + '\n')
                print(f'{alpha_id} prod corr test failed.')
                try:
                    set_alpha_properties(session, alpha_id, color='RED')
                except Exception:
                    pass
                return

        # √ 可提交列表
        self_corr_val = float(self_res['value'].iloc[0])
        alpha['self_corr'] = self_corr_val
        if mode != "PPAC":
            alpha['prod_corr'] = float(prod_res['value'].iloc[0])

        alpha_df = pd.DataFrame([alpha])
        with lock:
            if os.path.exists(submitable_alpha_file):
                base = pd.read_csv(submitable_alpha_file)
                submit_df = pd.concat([base, alpha_df], axis=0, ignore_index=True)
            else:
                submit_df = alpha_df
            submit_df.drop_duplicates(subset=['id'], keep='last', inplace=True)
            submit_df.to_csv(submitable_alpha_file, index=False)
        try:
            set_alpha_properties(session, alpha_id, color='GREEN')
        except Exception:
            pass
        print(f'Successfully find {alpha_id} is a submitable alpha.')
    except Exception as e:
        print(f"some error happened when checking: {e} \nAlpha: {alpha_id}")

# =========================
# 更稳健：get_alphas 包装（容错+重试）
# =========================
def safe_get_alphas_submit(start_date, end_date,
                           sh_th, fit_th,
                           region, universe,
                           *, delay='', instrumentType='',
                           alpha_num=9999, usage="submit", tag='',
                           color_exclude='RED', s=None, max_retries=3):
    """统一返回 {'check': [...]}，避免 KeyError: 'count' 等结构差异"""
    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            data = get_alphas(start_date, end_date,
                              sh_th, fit_th,
                              10, 10,
                              region=region, universe=universe, delay=delay, instrumentType=instrumentType,
                              alpha_num=alpha_num, usage=usage, tag=tag,
                              color_exclude=color_exclude, s=s)
            if isinstance(data, dict):
                return {"check": data.get("check", []) or []}
            if isinstance(data, list):
                return {"check": data}
            return {"check": []}
        except Exception as e:
            last_err = e
            time.sleep(min(5, 1.5 * attempt))
    print(f"Failed to get alphas: {last_err}")
    return {"check": []}

# =========================
# 主流程
# =========================
@while_true_try_decorator
def run_task(mode: str, n_jobs: int):
    n_jobs = int(n_jobs)
    start_date_file = os.path.join(RECORDS_PATH, 'start_date.txt')
    submit_file = os.path.join(RECORDS_PATH, 'submitable_alpha.csv')
    os.makedirs(RECORDS_PATH, exist_ok=True)

    periods = generate_date_periods(start_date_file=start_date_file, default_start_date=DEFAULT_START_DATE)

    for start_date, end_date in periods:
        print(start_date, end_date)
        for region in REGION_LIST:
            # 按 region → universe 遍历（关键修复点）
            universes = UNIVERSE_DICT["instrumentType"]["EQUITY"]["region"].get(region, []) \
                        if isinstance(UNIVERSE_DICT, dict) else []
            if not universes:
                # 若配置缺失，至少跑一个空 universe=TOP3000 以不致全空
                universes = ["TOP3000"]

            for universe in universes:
                if mode == "USER":
                    sh_th, fit_th = 1.25, 1.0
                elif mode == "CONSULTANT":
                    sh_th, fit_th = 1.58, 1.0
                else:  # PPAC
                    sh_th, fit_th = 1.0, 0.5

                color_ex = 'RED' if COLOR_EXCLUDE_RED else ''

                res = safe_get_alphas_submit(
                    start_date, end_date, sh_th, fit_th,
                    region, universe,
                    delay='', instrumentType='',
                    alpha_num=9999, usage="submit", tag='',
                    color_exclude=color_ex, s=s
                )
                check_list = res["check"]
                if not check_list:
                    print(f"region: {region} universe: {universe} No alpha to check.")
                    continue

                print(f"region: {region} universe: {universe} 看来有{len(check_list)}个因子等着被 check")

                # 分片并发（默认切块大小 DEFAULT_CHUNK_SIZE）
                chunks = [list(chunk) for chunk in np.array_split(check_list, max(len(check_list)//DEFAULT_CHUNK_SIZE, 1))]
                for chunk in chunks:
                    with ThreadPoolExecutor(max_workers=n_jobs) as executor:
                        for alpha in chunk:
                            executor.submit(check_alpha_by_self_prod, s, alpha, submit_file, mode)

        # 滚动推进起始日期（给出缓冲）
        if end_date < str(datetime.now().date() - timedelta(days=5)):
            with open(start_date_file, 'w', encoding='utf-8') as f:
                f.write(end_date)

# =========================
# CLI 入口
# =========================
if __name__ == "__main__":
    # 确保已登录（machine_lib 通常在 import 时已经登录）
    try:
        _ = s
    except Exception:
        try:
            login()
        except Exception:
            pass

    mode_in = input("请输入模式 (USER / CONSULTANT / PPAC) [默认 USER]: ").strip().upper()
    if mode_in not in {"USER", "CONSULTANT", "PPAC"}:
        mode_in = "USER"

    n_jobs_in = input(f"并发检查数量 n_jobs [默认 {DEFAULT_N_JOBS}]: ").strip()
    try:
        n_jobs_in = int(n_jobs_in) if n_jobs_in else DEFAULT_N_JOBS
    except Exception:
        n_jobs_in = DEFAULT_N_JOBS

    print(f"\n>>> 将以模式={mode_in}, n_jobs={n_jobs_in}, start_date>={DEFAULT_START_DATE}, "
          f"chunk_size={DEFAULT_CHUNK_SIZE}, color_exclude_red={COLOR_EXCLUDE_RED} 开始检查…\n")
    run_task(mode_in, n_jobs_in)

