# 上下文质量对比报告：lexical vs PPR

- 项目：`examples/legacy-java-oa` · golden 查询 26 条
- rankers：lexical、ppr；预算档：4000、8000 字符
- golden：tests/fixtures/context_golden.json（sha256:5eff7fb78e2473d8）
- generated_at：2026-10-21T00:22:02+08:00
- machine：Windows-10-10.0.26200-SP0
- python：3.11.5

## 检索质量（top-40 候选池，无需组装）

| ranker | recall@5 | recall@10 | precision@5 | MRR | perfect@5 |
|---|---|---|---|---|---|
| lexical | 0.5866 | 0.7372 | 0.3769 | 0.6728 | 0.1538 |
| ppr | 0.5705 | 0.7596 | 0.3615 | 0.7143 | 0.1923 |

## 打包质量与 token 成本（assemble 真实输出）

| ranker | 预算 | tokens/包(均值) | 覆盖 needed id | tokens/needed file | 预算遗漏率 | 未检索到 | 完整包比例 |
|---|---|---|---|---|---|---|---|
| lexical | 4000 | 759.6 | 0.8675 | 274.32 | 0.0000 | 0.1325 | 0.9615 |
| lexical | 8000 | 758.6 | 0.8675 | 273.96 | 0.0000 | 0.1325 | 1.0000 |
| ppr | 4000 | 1104.7 | 0.9157 | 377.92 | 0.0241 | 0.0602 | 0.0769 |
| ppr | 8000 | 1675.2 | 0.9398 | 558.41 | 0.0000 | 0.0602 | 0.5000 |

## 指标定义
- recall@k：每条查询需要 id 中出现在前 k 的比例，再对全部查询取均值。
- precision@5：前 5 条里命中需要 id 的数量 / 5。
- MRR：第一个正确 id 排名的倒数（无命中记 0），再取均值。
- tokens：用 `tmh.context_quality.estimate_tokens` 估算的实际渲染包大小（1 个汉字 / 1 个 ASCII 词 ≈ 1 token）。
- tokens/needed file：所有查询包 tokens 总和 / 实际被包覆盖的 needed id 总数。
- 预算遗漏率：因预算被列进 `omissions` 的 needed id / needed id 总数。
## 结论（由上面真实数字直接判定）

- lexical recall@5 = 0.5866，PPR recall@5 = 0.5705，差值 -0.0161；逐题对比 3 胜 / 18 平 / 5 负。
- recall@10 差值 +0.0224，MRR 差值 +0.0415。
- 预算 4000：tokens/包变化 +45.4%，needed-id 覆盖率变化 +0.0482，tokens/needed file 变化 +37.8%。
- 预算 8000：tokens/包变化 +120.8%，needed-id 覆盖率变化 +0.0723，tokens/needed file 变化 +103.8%。
- 判定：**不启用 PPR 作为默认 ranker**，默认保持 `lexical`。原因：recall@5 增益 -0.0161 < 门槛 0.02；token 变化超过 ±25%。

## 复跑方式

```
python benchmarks/run_context_quality.py
```

报告里所有数字由本次真实运行产生（临时仓库 + `kb.build` + 真实 `assemble`），环境与 golden 指纹见 JSON 的 `environment`/`golden` 字段。
