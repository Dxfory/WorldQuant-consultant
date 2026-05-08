# WorldQuant BRAIN Alpha Research Agent

这个工程把「刷公式」改造成可复用的研究流水线：

1. **阶段一**：复现 `Alpha101 + API 工具 + 实验记录`。
2. **阶段二**：加入 `LLM 生成 + 结构去重 + 参数变体搜索 + 失败分类`。
3. **阶段三**：运行 `region × universe × decay × neutralization` 的自动实验矩阵。

## 现在能不能直接在 WorldQuant 平台跑？

可以**直接运行流水线**，但是否能调用真实 BRAIN API 取决于你是否配置了凭证：

- 未配置凭证：使用 mock 模式，仅用于本地流程联调。
- 已配置凭证：尝试调用真实 `/simulations` 接口跑平台模拟。

> 默认只做研究与筛选，不自动提交；建议始终保留人工复核后再提交。

## 环境变量

```bash
export WQ_BRAIN_USERNAME="your_username"
export WQ_BRAIN_PASSWORD="your_password"
# 可选：自定义 API 域名
export WQ_BRAIN_BASE_URL="https://api.worldquantbrain.com"
```

## 快速开始

```bash
python -m wq_alpha_agent.src.pipeline \
  --config wq_alpha_agent/configs/experiment_matrix.json \
  --seed-file wq_alpha_agent/alpha_bank/seed_101_alphas.csv
```

运行后会在 `wq_alpha_agent/experiments/` 生成：

- `registry.csv`: 每个实验组合与指标。
- `failure_log.csv`: 失败原因分类。
- `accepted_alphas.csv`: 通过阈值的候选。

## 架构

- `src/generator.py`: 候选因子生成（规则 + 可选 LLM 接口）。
- `src/mutator.py`: 参数变体生成。
- `src/duplicate_filter.py`: 结构去重。
- `src/failure_classifier.py`: 失败原因分类。
- `src/brain_api_client.py`: BRAIN API 适配层（支持 real/mock 双模式）。
- `src/pipeline.py`: 三阶段一体化编排。
