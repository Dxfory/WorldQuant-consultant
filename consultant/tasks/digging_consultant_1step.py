"""
鑫鑫鑫｜Quant--WQ
世坤因子挖掘

版权所有 ©️ 鑫鑫鑫
微信: xinxinjijin8

本代码仅供个人学习使用，未经授权不得复制、修改或用于商业用途。

Author: 鑫鑫鑫
"""
import random
from datetime import datetime

from machine_lib import *
from config import *

@while_true_try_decorator
def run_task(dataset_id, region, delay, instrumentType, universe, n_jobs, tag=None):
    delay = int(delay)
    n_jobs = int(n_jobs)

    print(datetime.now(),f"=================您的配置信息==================")
    print(datetime.now(),f"dataset_id: {dataset_id}")
    print(datetime.now(),f"region: {region}")
    print(datetime.now(),f"delay: {delay}")
    print(datetime.now(),f"instrumentType: {instrumentType}")
    print(datetime.now(),f"universe: {universe}")
    print(datetime.now(),f"n_jobs: {n_jobs}")
    print(datetime.now(),f"=============================================")
    time.sleep(2)

    s = login()
    group = get_datafields(s=s, dataset_id=dataset_id, region=region, delay=delay, universe=universe)
    s.close()

    if len(group) == 0:
        print(datetime.now(),
            f"No data fields found for dataset_id: {dataset_id}, region: {region}, delay: {delay}, universe: {universe}")
        return

    if tag is None:
        tag = f"{region}_{delay}_{instrumentType}_{universe}_{dataset_id}_step1"
    completed_file_path = os.path.join(RECORDS_PATH, f"{tag}_simulated_alpha_expression.txt")
    completed_alphas = read_completed_alphas(completed_file_path)

    print(datetime.now(),f"Processing dataset_id: {dataset_id}")
    pc_fields = process_datafields(group, "matrix") + process_datafields(group, "vector")

    raw_alpha_list = first_order_factory(first_order_factory(pc_fields, ts_ops + basic_ops), ts_ops + basic_ops)

    alpha_list = [alpha for alpha in raw_alpha_list if alpha not in completed_alphas]

    if len(alpha_list) <= 1:
        print(datetime.now(),f"{tag} is already completed")
        return

    print(datetime.now(),f"{dataset_id} progress: {len(raw_alpha_list) - len(alpha_list)}/{len(raw_alpha_list)}")

    # 随机打乱alpha_list
    random.shuffle(alpha_list)

    # if len(alpha_list) > 1000:
    #     # 只跑1000个随机，防止和别人冲撞
    #     alpha_list = alpha_list[:1000]

    region_list = [(region, universe)] * len(alpha_list)  # 扩展 region_list
    decay_list = [random.randint(0, 10) for _ in range(len(alpha_list))]  # 扩展 decay_list
    delay_list = [delay] * len(alpha_list)  # 扩展 decay_list

    # USA,EUR,ASI and CHN
    if region in ['USA', 'EUR', 'ASI', 'CHN']:
        neut = 'SUBINDUSTRY'  # 自己选 SUBINDUSTRY，INDUSTRY，SECTOR，MARKET，COUNTRY，FAST，SLOW等等
    elif region in ['GLB']:
        neut = "SUBINDUSTRY"
    elif region in ['AMR']:
        neut = "SUBINDUSTRY"
    else:
        neut = 'SUBINDUSTRY'

    # 执行异步模拟，并控制并发数量为n_jobs
    asyncio.run(simulate_multiple_tasks(alpha_list, region_list, decay_list, delay_list,
                                         tag, neut,
                                         [], n=n_jobs))

    print(datetime.now(),"All tasks completed. Sleeping for 10 seconds...")
    time.sleep(10)
    print(datetime.now(),"Wake up.")

if __name__ == '__main__':
    dataset_id, region, delay, instrumentType, universe, n_jobs = (
        "analyst4",
        "USA",
        1,
        "EQUITY",
        "TOP3000",
        3
    )
    run_task(dataset_id, region, delay, instrumentType, universe, n_jobs)