"""
鑫鑫鑫｜Quant--WQ
世坤因子挖掘

版权所有 ©️ 鑫鑫鑫
微信: xinxinjijin8

本代码仅供个人学习使用，未经授权不得复制、修改或用于商业用途。

Author: 鑫鑫鑫
"""

from machine_lib import *
from config import *
import asyncio
import aiofiles
import time
from collections import defaultdict


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

    # 生成step2的tag
    tag = f"{region}_{delay}_{instrumentType}_{universe}_{dataset_id}_step2"
    step2_tag_list = [tag]

    for step2_tag in step2_tag_list:
        if 'ILLIQUID' in step2_tag:
            region, delay, instrumentType, ILLIQUID_tag, universe, dataset_id, step_num = step2_tag.split('_')
            universe = f'{ILLIQUID_tag}_{universe}'
        else:
            region, delay, instrumentType, universe, dataset_id, step_num = step2_tag.split('_')

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

        so_tracker = get_alphas("2024-10-07", "2029-12-31",
                                sharpe_step3_th, fitness_step3_th,
                                100, 100,
                                region, universe, delay, instrumentType,
                                500, "track", tag=step2_tag)

        so_layer = prune(so_tracker['next'] + so_tracker['decay'],
                         dataset_id, 3)

        th_alpha_list = []
        for expr, decay in so_layer:
            for alpha in trade_when_factory("trade_when", expr, region, delay):
                th_alpha_list.append((alpha, decay))
        print(datetime.now(),len(th_alpha_list))

        # 读取已完成的alpha表达式
        completed_alphas = read_completed_alphas(f'records/{step3_tag}_simulated_alpha_expression.txt')

        raw_alpha_list = th_alpha_list
        # 排除已完成的alpha表达式
        alpha_list = [alpha_decay for alpha_decay in raw_alpha_list if alpha_decay[0] not in completed_alphas]
        if len(alpha_list) == 0:
            print(datetime.now(),f"已经完成了{len(completed_alphas)}个alpha表达式，一共有{len(raw_alpha_list)}个alpha表达式")
            print(datetime.now(),f"{step3_tag} is done.")
            continue
        print(datetime.now(),"{}progress: {}/{}".format(step3_tag, len(raw_alpha_list) - len(alpha_list), len(raw_alpha_list)))

        grouped_dict = defaultdict(list)
        for alpha, decay in alpha_list:
            grouped_dict[decay].append(alpha)

        for decay in grouped_dict:
            alpha_list = grouped_dict[decay]
            decay_list = [decay] * len(alpha_list)
            delay_list = [delay] * len(alpha_list)
            region_list = [(region, universe)] * len(alpha_list)  # 扩展 region_list

            # USA,EUR,ASI and CHN
            if region in ['USA', 'EUR', 'ASI', 'CHN']:
                neut = 'SUBINDUSTRY'
            elif region in ['GLB']:
                neut = "SUBINDUSTRY"
            elif region in ['AMR']:
                neut = "SUBINDUSTRY"
            else:
                neut = 'SUBINDUSTRY'

            # 执行异步模拟，并控制并发数量为3
            asyncio.run(simulate_multiple_tasks(alpha_list, region_list, decay_list, delay_list,
                                                step3_tag, neut,
                                                [], n=n_jobs))

    print(datetime.now(),"All done. Sleep 600s...")
    time.sleep(600)
    print(datetime.now(),"Wake up.")



