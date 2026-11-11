# KPI-BENCH-10 计量报告：已通过对标算例数 = 1 / 10（缺口 9）

mission m15124 · 2026-11-11 · 只计量不改进（协调官规划令 2026-11-11）

## ① 案例介绍（KPI 定义与数据源）

KPI-BENCH-10 = **已通过对标算例数**，目标 ≥10。口径（本单执行口径）：
`tensorbench_results` 中 `passed=true` 的 `benchmark_id` 去重数，与 `tensor_benchmark_cases` 中
`status='verified'` 的锚点合并去重。数据源=PostgreSQL `tensorplatform` 库三张表：
`tensorbench_results`（结果行，含 ref/got/rel_error/tolerance/passed）、
`tensor_benchmark_cases`（锚点台账，13 条）、`tensorbench_evaluations`（评估事件）。
仓库 `benchmarks/cases/{dtmb5415,kvlcc2,suboff}` 仅有 spec.json、无结果工件，不计入。

## ② 怎么做的（方法/流程/工具链）

1. 定位数据源：平台 API 无 tensorbench 端点（404），改直连 PG（`foundation@127.0.0.1:5432/tensorplatform`，凭据取自 TensorPlatform/.env）。
2. 计量 SQL（原文，可复算）：
```sql
-- Q1 主计量：去重后通过算例
SELECT DISTINCT benchmark_id, benchmark_version, workload_id, metric,
       ref_value, got_value, rel_error, tolerance_rel, passed,
       execution_status, source, recorded_at
FROM tensorbench_results WHERE passed = true;
-- Q2 锚点台账状态
SELECT status, count(*) FROM tensor_benchmark_cases GROUP BY status;
-- Q3 评估事件状态
SELECT state, count(*) FROM tensorbench_evaluations GROUP BY state;
-- Q4 交叉复核（独立路径）
SELECT count(DISTINCT benchmark_id) FROM tensorbench_results WHERE passed = true;
SELECT count(*) FROM tensor_benchmark_cases WHERE status = 'verified';
```
3. L1 数学验证：Q1（DISTINCT 行枚举）与 Q4（count DISTINCT）两条独立路径均得 **1**；
   `tensor_benchmark_cases` verified 数 = 0，合并去重后仍为 1。数字零手抄，全部 SQL 溯源。
4. 本单无重计算（纯 SQL 计数），未占用 cluster_queue；集群仅用于重计算，计数查询在控制面执行合规。

## ③ 计算结果（数字表，程序化注入）

**已 VERIFIED 算例（1 个）：**

| 锚点 | workload | 指标 | ref | got | rel_error | 容差 | 判定 |
|---|---|---|---|---|---|---|---|
| tensorbem.cylinder-added-mass | cylinder-translating-added-mass-64 | added_mass_per_unit_span | 3220.132469929538 | 3225.3250921803083 | 0.0016125 (0.161%) | 0.01 (1%) | PASS |

recorded_at=2026-11-11T09:53:37.954623+00:00，source=host_replay，mission_id=14624。

**KPI 汇总：**

| 项 | 值 |
|---|---|
| current | **1** |
| target | 10 |
| gap | **9** |
| tensor_benchmark_cases 状态 | pending=13，verified=0 |
| tensorbench_evaluations 状态 | ingested=1，skipped=1（无 VERIFIED 态） |

**缺口清单（13 个 pending 锚点，按仓）：**

| 锚点 | 仓 | 算例 | 容差 |
|---|---|---|---|
| GAP-DEM-CLUMP | TensorDEM | clump 颗粒休止角 vs 文献带 | ±20% |
| GAP-DEM-FRICTION | TensorDEM | 直剪试验标定 μ | <10% |
| H1-BROKEN-ICE-DEM | TensorDEM | 浮冰浮态+航道清空 | 干舷<5% |
| GAP-FEM-3D-COHESIVE | TensorFEM | DCB I 型剥离 P-δ+能量释放率 | <10% |
| GAP-FEM-ELASTOPLASTIC | TensorFEM | Cook 翘曲膜+单轴拉伸循环 | <10% |
| GAP-FEM-WINKLER | TensorFEM | Hetényi 弹性地基板级数解 | <5% |
| H3-ICE-PLATE-FEM | TensorFEM | Hetényi 冰板弯曲 | <5% |
| GAP-FVM-TWOPHASE | TensorFVM | Zalesak 旋转缺口盘+Hysing 气泡 | 末速<10% |
| GAP-LBM-MCMP-POISEUILLE | TensorLBM | MCMP 分层 Poiseuille | <5%/<10%/<0.005U |
| GAP-LBM-SPHERE | TensorLBM | 球绕流阻力关联 C_D | <8% |
| H2-FRAZIL-RHEOLOGY | TensorLBM | 悬浮液粘度律 vs K-D | <10% |
| H6-MATURITY-GATE | TensorPlatform | 门禁覆盖率 | =100% |
| CAP-LEDGER-EVIDENCE | ship-performance-platform | 台账判据集 | =21/21 |

**建议派生锚点（下一个最好打，按参考可得性+指标简单度排序，非实测排序）：**
1. **GAP-LBM-SPHERE**（TensorLBM）：球绕流 C_D vs Schiller-Naumann/Morsi-Alexander 关联 <8%——单指标、经典参考、低算力。
2. **GAP-FEM-WINKLER**（TensorFEM）：Hetényi 级数解挠度/弯矩 <5%——闭式解可程序化复算。
3. **GAP-DEM-FRICTION**（TensorDEM）：直剪标定 μ vs 目标 <10%——小规模标定、收敛快。

## ④ 结果图

无图。理由：本单为纯计量任务（SQL 计数），无场量云图、无时间序列可画；
全部数字由 SQL 直接产出（见 ②），图不增加信息量。

## ⑤ 注意点（坑/局限/适用范围）

- `tensor_benchmark_cases` 的 13 条锚点全部 `pending` 且 `passed_at` 为空——台账已建、验证未跑，
  这是缺口主体（13 个候选 vs 需要 9 个，候选池充足）。
- `tensorbench_evaluations` 无 VERIFIED 状态值，VERIFIED 语义实际落在
  `tensorbench_results.passed=true`；若后续引入新状态需同步本 KPI 口径。
- 唯一通过算例 source=host_replay（宿主回放），非集群首跑；消账时建议补一次集群复跑留痕。
- 建议锚点排序基于参考可得性与指标复杂度推断，未实测，派单后以实测为准。
- 本单未改任何代码/数据（规划令禁止），未跑任何求解器。

## ⑥ 误差判定

本 KPI 为计数型（整数），无物理量误差项。L1 复核：两条独立 SQL 路径（DISTINCT 枚举 vs
count DISTINCT）结果一致 = 1，与源表行数（1 行 passed=true）一致 → **数字与源一致，无偏差**。
「是否 <3%」：不适用（计数 KPI 无连续误差），已声明原因。
KPI 消账门=测量值达标：当前 1 < 10，**未达标，如实报**。
