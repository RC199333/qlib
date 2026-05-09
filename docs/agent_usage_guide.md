# Qlib Agent Usage Guide

Last verified: 2026-05-07

## 当前平台状态

这个 fork 现在已经可以作为本地 Alpha Research Agent 的执行底座使用。

已部署的数据：

| 数据源 | 路径 | 用途 |
| --- | --- | --- |
| China A-share | `C:\Users\rexch\.qlib\qlib_data\cn_data` | A 股 benchmark 和中文社区数据研究 |
| Qlib legacy US | `C:\Users\rexch\.qlib\qlib_data\us_data` | 复现 Qlib 官方 US 示例，数据到 `2020-11-10` |
| Recent US | `C:\Users\rexch\.qlib\qlib_data\us_data_recent` | 近期美股研究，数据到 `2026-05-07` |

已验证的主链路：

```text
provider_uri -> DataHandler -> Dataset -> Model -> SignalRecord -> SigAnaRecord -> Strategy -> Backtest -> PortAnaRecord -> MLflow artifacts
```

近期美股 baseline 已跑通：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_real_benchmark.ps1 -Region USRecent -Model Linear
```

## Qlib 有没有界面

Qlib 本身不是一个点击式 GUI 或交易终端。它更像一个量化研究引擎，主要接口是：

- `qrun`: 用 YAML 配置跑完整实验。
- Python API: 直接创建 `DataHandler`、`Dataset`、`Model`、`Strategy`、`Backtest`。
- Notebook: 适合人工探索、画图、检查数据。
- MLflow UI: 查看实验、参数、指标和 artifacts。
- Codex Agent: 你用自然语言给想法，我把它转成 Qlib 实验并执行。

如果你不想自己写代码，推荐主入口就是 **和 Agent 对话**。MLflow UI 只用来查看实验结果。

近期美股 MLflow UI:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_mlflow_ui.ps1 -TrackingUri .tmp\mlruns_us_recent -Port 5002
```

打开：

```text
http://127.0.0.1:5002
```

## 你应该怎么使用 Agent

你可以直接用自然语言发任务，例如：

```text
用 us_data_recent + sp500，测试一个 20 日动量减去 60 日波动率惩罚的因子。
回测 2024-01-02 到 2026-05-05，周频调仓，long-only top 50，和 ^GSPC 比较。
最后告诉我 IC、Rank IC、收益、回撤、换手、成本后表现，以及这个想法有什么问题。
```

更标准的 IdeaCard 模板：

```text
市场: US
数据源: us_data_recent
Universe: sp500 / nasdaq100 / etf_core / 自定义股票列表
Benchmark: ^GSPC / ^NDX / SPY / QQQ
因子想法: 描述你的直觉，不需要写公式
预测周期: 1d / 5d / 20d
调仓频率: daily / weekly / monthly
组合方式: long-only top N / long-short / rotation
约束: 最大单票权重、行业限制、成交量过滤、成本假设
报告要求: 只要 summary / 要详细 diagnostics / 要和 baseline 对比
```

## Agent 会帮你做什么

我会把你的粗略想法拆成可执行研究流程：

1. 将自然语言想法整理成 `IdeaCard`。
2. 把 `IdeaCard` 编译成 `ExperimentSpec`，明确 universe、日期、label、因子、模型、策略、成本。
3. 检查本地数据是否覆盖所需标的和日期。
4. 把想法翻译成 Qlib expression，例如 `Mean($close, 20) / Ref($close, 20) - 1` 这类公式。
5. 选择执行路径：
   - 规则型信号：直接组合因子生成 score。
   - 训练型信号：用 `LinearModel`、`LightGBM` 或后续 `CompositeSignalModel` 拟合。
6. 生成或更新 Qlib workflow config。
7. 跑 `SignalRecord`、`SigAnaRecord`、`PortAnaRecord`。
8. 做 red-team validation：
   - 数据覆盖是否足够；
   - 是否有未来函数；
   - train/valid/test 是否重叠；
   - IC 是否靠少数日期撑起来；
   - 成本后是否崩掉；
   - 回撤、换手、集中度是否合理。
9. 输出中文报告：因子定义、实验设置、指标、失败点、下一步改法。

## 你不需要自己做什么

你不需要自己写：

- Qlib YAML；
- Python factor loader；
- backtest runner；
- MLflow artifact 读取脚本；
- 数据转换命令。

你只需要告诉我：

- 你想研究什么市场；
- 你的因子直觉；
- 大概持有周期；
- 想做 long-only、long-short 还是 rotation；
- 你更关心收益、回撤、换手、稳定性还是解释性。

## 当前可以直接跑的功能

### 更新近期美股数据

```powershell
powershell -ExecutionPolicy Bypass -File scripts\update_us_recent_data.ps1 -Start 2020-01-01 -ChunkSize 40 -MaxWorkers 1 -SymbolSource current
```

这个命令会更新：

- current S&P 500；
- current NASDAQ 100；
- core ETF universe；
- `^GSPC`、`^NDX`、`^DJI` benchmarks。

### 跑近期美股 baseline

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_real_benchmark.ps1 -Region USRecent -Model Linear
```

### 查看近期美股实验

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_mlflow_ui.ps1 -TrackingUri .tmp\mlruns_us_recent -Port 5002
```

### 跑第一个财报 read-through 策略

如果已经设置 Alpha Vantage key：

```powershell
$env:ALPHAVANTAGE_API_KEY = "<your-key>"
powershell -ExecutionPolicy Bypass -File scripts\run_earnings_readthrough_alpha.ps1 -Start 2024-01-01 -End 2026-05-07 -RequestDelaySeconds 12
```

如果先用离线 earnings CSV：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_earnings_readthrough_alpha.ps1 -EventsPath path\to\events.csv -Start 2024-01-01 -End 2026-05-07
```

CSV 最少需要：

```text
symbol,reported_date,surprise_percentage
AMD,2024-01-30,15.0
AVGO,2024-02-02,10.0
NVDA,2024-02-09,0.0
```

输出位置：

```text
.tmp\alpha_lab_runs\earnings_readthrough_*
.tmp\mlruns_alpha_lab
```

## 重要边界

现在的 `us_data_recent` 是当前成分股数据，不是 point-in-time index membership。它适合用来搭 Agent、打通研究流程、快速验证想法，但如果要做严肃的历史指数成分股回测，需要接入 survivorship-bias-free 的授权数据。

Qlib 可以处理日频 OHLCV、因子表达式、模型训练、信号分析、组合回测和实验记录。它不能自动保证因子有经济意义，也不会替你解决数据供应商层面的生产级公司行为、退市、历史成分股和 fundamentals point-in-time 问题。这些需要作为 red-team 检查的一部分明确处理。
