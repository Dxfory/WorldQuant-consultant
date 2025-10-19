"""
鑫鑫鑫｜Quant--WQ
世坤因子挖掘

版权所有 ©️ 鑫鑫鑫
微信: xinxinjijin8

本代码仅供个人学习使用，未经授权不得复制、修改或用于商业用途。

Author: 鑫鑫鑫
"""
import time
import os

import numpy as np
import pandas as pd
from config import RECORDS_PATH, REGION_LIST, UNIVERSE_DICT
from machine_lib import s, login, get_alphas, set_alpha_properties, while_true_try_decorator
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import threading
import warnings
warnings.filterwarnings("ignore")

brain_api_url = os.environ.get("BRAIN_API_URL", "https://api.worldquantbrain.com")

import requests
from typing import Tuple, List, Dict

lock = threading.Lock()

def wait_get(session: requests.Session, url: str, max_retries: int = 10) -> requests.Response:
    """带重试机制的 GET 请求"""
    retries = 0
    while retries < max_retries:
        response = session.get(url)
        retry_after = float(response.headers.get("Retry-After", 0))
        if retry_after > 0:
            time.sleep(retry_after)
            continue
        if response.status_code < 400:
            return response
        time.sleep(2)
        retries += 1
    response.raise_for_status()  # 超过重试次数后抛出异常
    return response


def get_alpha_region(session: requests.Session, alpha_id: str) -> str:
    """获取 alpha 所属区域"""
    url = f"https://api.worldquantbrain.com/alphas/{alpha_id}"
    alpha_info = wait_get(session, url).json()
    return alpha_info['settings']['region']


def get_region_alphas(session: requests.Session, region: str) -> List[str]:
    """获取同区域所有 OS 阶段的 alpha ID"""
    offset = 0
    limit = 100
    alpha_ids = []
    while True:
        url = (f"https://api.worldquantbrain.com/users/self/alphas?"
               f"stage=OS&limit={limit}&offset={offset}&order=-dateSubmitted")
        res = wait_get(session, url).json()
        for alpha in res['results']:
            if alpha['settings']['region'] == region:
                alpha_ids.append(alpha['id'])
        if len(res['results']) < limit:
            break
        offset += limit
    return alpha_ids


def get_alpha_pnl(session: requests.Session, alpha_id: str) -> pd.DataFrame:
    """获取单个 alpha 的 PnL 数据"""
    url = f"https://api.worldquantbrain.com/alphas/{alpha_id}/recordsets/pnl"
    pnl_data = wait_get(session, url).json()
    df = pd.DataFrame(
        pnl_data['records'],
        columns=[p['name'] for p in pnl_data['schema']['properties']]
    ).rename(columns={'date': 'Date', 'pnl': alpha_id})[['Date', alpha_id]]
    df['Date'] = pd.to_datetime(df['Date'])
    return df.set_index('Date')


def calculate_correlation(
        target_rets: pd.Series,
        peer_rets: pd.DataFrame
) -> float:
    """计算目标收益率与同区域其他 alpha 收益率的最大相关性 CYX专用"""
    # 过滤时间范围（最近4年）
    start_date = target_rets.index.max() - pd.DateOffset(years=4)
    target_rets = target_rets[target_rets.index > start_date]
    peer_rets = peer_rets[peer_rets.index > start_date]

    # 对齐时间索引并计算相关性
    combined_rets = pd.concat([target_rets, peer_rets], axis=1, join='inner')
    if combined_rets.empty:
        return 0.0

    target_col = combined_rets.columns[0]
    corr_series = combined_rets.drop(target_col, axis=1).corrwith(combined_rets[target_col])
    max_corr = corr_series.max() if not corr_series.empty else 0.0

    if pd.isna(max_corr):
        print("好像遇到了厂字alpha, self corr改为0.9999")
        return 0.9999

    return max_corr


def get_self_corr_xin_plus(session: requests.Session, alpha_id: str) -> float:
    """
    计算指定 alpha 与同区域其他 alpha 的最大相关性

    Args:
        session (requests.Session): 已登录的会话对象
        alpha_id (str): 目标 alpha 的唯一标识符

    Returns:
        float: 最大相关性值（范围 [-1, 1]，无数据时返回 0）
    """
    try:
        # 1. 获取目标 alpha 区域
        region = get_alpha_region(session, alpha_id)

        # 2. 获取同区域所有 alpha ID（排除自身）
        peer_ids = [aid for aid in get_region_alphas(session, region) if aid != alpha_id]
        if not peer_ids:
            return 0.0  # 无同区域其他 alpha

        # 3. 获取目标 alpha 和所有 peer 的 PnL 数据
        # 先获取目标 alpha 的 PnL
        target_pnl = get_alpha_pnl(session, alpha_id)
        # 再批量获取 peer 的 PnL
        peer_pnls = []
        for aid in peer_ids:
            try:
                peer_pnls.append(get_alpha_pnl(session, aid))
            except Exception:
                continue  # 忽略获取失败的 peer

        # 4. 合并数据并计算收益率
        # 目标收益率 = 当前 pnl - 前一日 pnl（ffill 处理缺失）
        target_rets = target_pnl[alpha_id].ffill().pct_change().dropna()  # 改用百分比变化（原代码用绝对变化，可根据需求调整）
        # 或者保持原逻辑：target_rets = target_pnl[alpha_id] - target_pnl[alpha_id].ffill().shift(1)

        peer_rets_df = pd.concat(peer_pnls, axis=1).ffill()
        peer_rets_df = peer_rets_df.apply(lambda x: x - x.ffill().shift(1), axis=0)  # 计算每个 peer 的收益率

        # 5. 计算相关性并返回最大值
        return calculate_correlation(target_rets, peer_rets_df)

    except Exception as e:
        print(f"计算相关性时出错: {str(e)}")
        return 0.0


def generate_date_periods(start_date_file='start_date.txt', default_start_date='2024-10-07'):
    try:
        with open(start_date_file, mode='r') as f:
            start_date_str = f.read().strip()
    except FileNotFoundError:
        print("File start_date.txt not found. Use default start date: '2024-10-07'.")
        start_date_str = default_start_date

    # 将输入的字符串转换为日期对象
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    today = datetime.now().date() + timedelta(days=1)   # 获取今天的日期

    periods = []

    current_date = start_date
    while current_date < today:
        next_date = current_date + timedelta(days=1)
        periods.append([current_date.strftime('%Y-%m-%d'), next_date.strftime('%Y-%m-%d')])
        current_date = next_date

    return periods


def read_completed_alphas(filepath):
    """
    从指定文件中读取已经完成的alpha表达式
    """
    completed_alphas = set()
    try:
        with open(filepath, mode='r') as f:
            for line in f:
                completed_alphas.add(line.strip())
    except FileNotFoundError:
        print(f"File {filepath} not found.")
    return completed_alphas


def get_self_corr(s, alpha_id):
    """
    Function gets alpha's self correlation
    and save result to dataframe
    """

    while True:

        result = s.get(
            brain_api_url + "/alphas/" + alpha_id + "/correlations/self"
        )
        if "retry-after" in result.headers:
            time.sleep(float(result.headers["Retry-After"]))
        else:
            break
    if result.json().get("records", 0) == 0:
        return pd.DataFrame()

    records_len = len(result.json()["records"])
    if records_len == 0:
        return pd.DataFrame()

    columns = [dct["name"] for dct in result.json()["schema"]["properties"]]
    self_corr_df = pd.DataFrame(result.json()["records"], columns=columns).assign(alpha_id=alpha_id)

    return self_corr_df


def get_prod_corr(s, alpha_id):
    """
    Function gets alpha's prod correlation
    and save result to dataframe
    """

    while True:
        result = s.get(
            brain_api_url + "/alphas/" + alpha_id + "/correlations/prod"
        )
        if "retry-after" in result.headers:
            time.sleep(float(result.headers["Retry-After"]))
        else:
            break
    if result.json().get("records", 0) == 0:
        return pd.DataFrame()
    columns = [dct["name"] for dct in result.json()["schema"]["properties"]]
    prod_corr_df = pd.DataFrame(result.json()["records"], columns=columns).assign(alpha_id=alpha_id)

    return prod_corr_df


def check_self_corr_test(s, alpha_id, threshold: float = 0.7):
    """
    Function checks if alpha's self_corr test passed
    Saves result to dataframe
    """

    self_corr_df = get_self_corr(s, alpha_id)
    if self_corr_df.empty:
        result = [{"test": "SELF_CORRELATION", "result": "PASS", "limit": threshold, "value": 0, "alpha_id": alpha_id}]
    else:
        value = self_corr_df["correlation"].max()
        result = [
            {
                "test": "SELF_CORRELATION",
                "result": "PASS" if value < threshold else "FAIL",
                "limit": threshold,
                "value": value,
                "alpha_id": alpha_id
            }
        ]
    return pd.DataFrame(result)


def check_prod_corr_test(s, alpha_id, threshold: float = 0.7):
    """
    Function checks if alpha's prod_corr test passed
    Saves result to dataframe
    """

    prod_corr_df = get_prod_corr(s, alpha_id)
    value = prod_corr_df[prod_corr_df.alphas > 0]["max"].max()
    result = [
        {"test": "PROD_CORRELATION", "result": "PASS" if value <= threshold else "FAIL", "limit": threshold,
         "value": value, "alpha_id": alpha_id}
    ]
    return pd.DataFrame(result)


def check_alpha_by_self_prod(s, alpha, submitable_alpha_file, mode):
    alpha_id = alpha['id']
    tags = alpha['tags']
    if len(tags) > 1:
        time.sleep(1)
        raise ValueError("Only one tag is allowed.")
    tag = tags[0] if len(tags) == 1 else ''

    region = alpha['region']
    delay = alpha['delay']
    universe = alpha['universe']
    instrumentType = alpha['instrumentType']
    color = alpha['color']

    completed_file_path = os.path.join(RECORDS_PATH, f"{tag}_checked_alpha_id.txt")
    checked_alpha_id_list = read_completed_alphas(completed_file_path)

    # 去除已经检查过的alpha
    if alpha_id in checked_alpha_id_list:
        print(f'{alpha_id} has already been checked.')
        if color != 'RED':
            set_alpha_properties(s, alpha_id, color='RED')
        return

    # if alpha['color'] == 'GREEN':
    #     print(f'{alpha_id} has already been submitted.')
    #     return

    try:
        now = time.time()
        try:
            self_corr = get_self_corr_xin_plus(s, alpha_id)
            self_res = pd.DataFrame(
                [{"test": "SELF_CORRELATION", "result": "PASS" if self_corr < 0.7 else "FAIL",
                  "limit": 0.7, "value": self_corr, "alpha_id": alpha_id}])
            print(alpha_id, "xin plus self corr use:", time.time() - now)
            print(f"{alpha_id} self corr:", self_corr)
            if self_res['result'].iloc[0] == 'FAIL':
                with lock:
                    with open(completed_file_path, mode='a') as f:
                        f.write(alpha_id + '\n')
                print(f'{alpha_id} self corr test failed.')
                set_alpha_properties(s, alpha_id, color='RED')
                return
        except Exception as e:
            self_res = check_self_corr_test(s, alpha_id, 0.7)
            print(alpha_id, "self corr use:", time.time() - now)
            print(self_res)
            if self_res['result'].iloc[0] == 'FAIL':
                with lock:
                    with open(completed_file_path, mode='a') as f:
                        f.write(alpha_id + '\n')
                print(f'{alpha_id} self corr test failed.')
                set_alpha_properties(s, alpha_id, color='RED')
                return

        if mode != "PPAC":
            now = time.time()
            prod_res = check_prod_corr_test(s, alpha_id, 0.7)
            print(prod_res)
            print(alpha_id, "prod corr use:", time.time() - now)
            if prod_res['result'].iloc[0] == 'FAIL':
                with lock:
                    with open(completed_file_path, mode='a') as f:
                        f.write(alpha_id + '\n')
                print(f'{alpha_id} prod corr test failed.')
                set_alpha_properties(s, alpha_id, color='RED')
                return

        # 一路过关斩将，可以提交了
        self_corr = self_res['value'].iloc[0]
        alpha['self_corr'] = self_corr


        if mode != "PPAC":
            prod_corr = prod_res['value'].iloc[0]
            alpha['prod_corr'] = prod_corr

        alpha_df = pd.DataFrame([alpha])
        print(alpha_df)
        with lock:
            submit_df = pd.concat([pd.read_csv(submitable_alpha_file) if os.path.exists(submitable_alpha_file) else pd.DataFrame(), alpha_df], axis=0)
            submit_df.drop_duplicates(subset=['id'], keep='last', inplace=True)
            submit_df.to_csv(submitable_alpha_file, index=False)
        set_alpha_properties(s, alpha_id, color='GREEN')
        # s.post(f"https://sctapi.ftqq.com/{server_secret}.send", data={"text": f"Successfully find {alpha_id} is a submitable alpha."})
        print(f'Successfully find {alpha_id} is a submitable alpha.')
    except Exception as e:
        print(f"some error happened when checking: {e} \nAlpha: {alpha_id}")



@while_true_try_decorator
def run_task(mode, n_jobs):
    n_jobs = int(n_jobs)
    # mode = "PPAC"  # "USER" or "CONSULTANT" or "PPAC"
    # n_jobs = 1  # 每次检查的数量
    start_date_file = os.path.join(RECORDS_PATH, 'start_date.txt')
    submitable_alpha_file = os.path.join(RECORDS_PATH, 'submitable_alpha.csv')

    # 生成一组start_date和end_date,需要是自然日
    periods = generate_date_periods(start_date_file=start_date_file, default_start_date='2025-05-05')

    for start_date, end_date in periods:
        print(start_date, end_date)
        for region in REGION_LIST:
            # for universe in UNIVERSE_DICT["instrumentType"]['EQUITY']['region'][region]:
                if mode == "USER":
                    sh_th = 1.25
                    fit_th = 1
                elif mode == "CONSULTANT":
                    sh_th = 1.58
                    fit_th = 1
                elif mode == "PPAC":
                    sh_th = 1
                    fit_th = 0.5
                need_to_check_alpha = get_alphas(start_date, end_date,
                                        sh_th, fit_th,
                                        10, 10,
                                        region=region, universe="", delay='', instrumentType='',
                                        alpha_num=9999, usage="submit", tag='', color_exclude='RED', s=s)

                if len(need_to_check_alpha['check']) == 0:
                    print(f"region: {region}", f"universe: all", "No alpha to check.")
                    continue

                print(f"看来有{len(need_to_check_alpha['check'])}个因子等着被check")

                # 将列表等分为n份
                split_sizes = np.array_split(need_to_check_alpha['check'], max(len(need_to_check_alpha)//10, 1))

                # 将结果转换为列表形式
                chunks = [list(chunk) for chunk in split_sizes]

                for chunk in chunks:
                    with ThreadPoolExecutor(max_workers=n_jobs) as executor:
                        for alpha in chunk:
                            executor.submit(check_alpha_by_self_prod, s,  alpha, submitable_alpha_file, mode)

                if end_date < str(datetime.now().date()-timedelta(days=3)):
                    with open(start_date_file, 'w') as f:
                        f.write(end_date)

        if end_date < str(datetime.now().date() - timedelta(days=5)):
            with open(start_date_file, 'w') as f:
                f.write(end_date)

