# TensorBench 质量审计报告

**审计任务**: m14495 | **审计人**: audit2-ab | **日期**: 2026-11-11
**审计对象**: cxs503/TensorBench (main @ 9c5dee3)
**审计方法**: codebase-investigation + adversarial-review

---

## 一、资产盘点（main 分支）

### 1.1 分类清单

| 类别 | 文件 | 行数 | 说明 |
|---|---|---|---|
| **核心算法模块** | `tensorbench/runner.py` | 218 | 本地基准测试执行器：subprocess 执行、超时处理、环境采集、SHA256 校验、结果持久化 |
| **核心算法模块** | `tensorbench/cli.py` | 47 | CLI 入口：argparse 子命令 `run`，调用 runner |
| **核心算法模块** | `tensorbench/__init__.py` | 3 | 包初始化，仅 `__version__ = "0.1.0"` |
| **测试代码** | `tests/test_runner.py` | 71 | 4 个测试用例（成功/失败/超时/非法输入），全部通过 |
| **Schema** | `schemas/benchmark-result.schema.json` | 157 | JSON Schema v2020-12，定义结果记录结构 |
| **文档报告** | `README.md` | 121 | 项目章程、使命、范围、快速入门 |
| **文档报告** | `docs/ARCHITECTURE.md` | 129 | 目标架构设计（7 个逻辑组件、核心实体、信任边界） |
| **文档报告** | `docs/BENCHMARK_SPEC.md` | 114 | 基准测试规范契约（9 节） |
| **文档报告** | `LICENSE_SCOPE.md` | 37 | 许可证范围声明 |
| **示例** | `examples/hello-benchmark.json` | 25 | 冒烟测试规范（执行 `print` 命令） |
| **构建** | `pyproject.toml` | 25 | Python 包声明，`[test]` 可选依赖 |
| **合计** | 11 文件 | **947** | 不含 LICENSE (202行 boilerplate) |

### 1.2 占位实现 / Stub / TODO 扫描

```
grep -rn 'TODO|FIXME|NotImplemented|stub|STUB' tensorbench/ tests/
→ 零结果
```

**结论**: main 分支无占位实现、无 TODO 骨架、无空函数。代码量小但完整。

### 1.3 重复实现扫描

- `runner.py` 中 `_utc_now()`, `_sha256()`, `_git_revision()`, `_validate_spec()` 均为 `run_benchmark()` 内部使用的私有辅助函数，无重复。
- 无与既有模块功能重叠的实现。

### 1.4 未接入模块扫描

- `run_benchmark()` 被 `cli.py` 和 `test_runner.py` 调用 → 已接入。
- 所有私有辅助函数均在 `runner.py` 内部被调用 → 无死代码。

### 1.5 待合入 Agent 分支概览（未并入 main）

| 分支 | Commit | 新增文件 | 新增行数 | 核心内容 |
|---|---|---|---|---|
| `agent/m14429` | 3098fb2 | 95 | 8,673 | Agent 基准测试任务集（12 任务）+ 评分引擎 (`tensorbench/eval/`) + 泄漏扫描器 |
| `agent/m14430` | 7267a57 | 55 | 5,334 | 基准对比 (`compare.py`) + 发布 (`publish.py`) + 评估循环 + stencil2d5pt 参考工作负载 |
| `agent/m14428` | 9c5dee3 | 0 | 0 | 与 main 相同（无变更） |

**注意**: 以上分支均未合并到 main，不在本次 main 审计范围内，但下文「膨胀清单」会涉及对其声明的审查。

---

## 二、功能真实性审查（六问表）

### 2.1 核心功能：本地基准测试执行器 (`run_benchmark`)

| 问题 | 回答 | 证据 |
|---|---|---|
| Q1: 代码入口在哪？ | `tensorbench/cli.py:24 main()` → `tensorbench/runner.py:79 run_benchmark()` | `cli.py:9` import; `cli.py:30` 调用 |
| Q2: 是否真的执行计算？ | **是**。通过 `subprocess.run(shell=False)` 执行 argv 命令，用 `time.perf_counter()` 测量 wall time | `runner.py:115-128` subprocess 执行; `runner.py:131` duration 计算 |
| Q3: 是否接入主程序？ | **是**。CLI `tensorbench run --spec` 调用 runner；4 个 pytest 测试覆盖 runner | `cli.py:30`; `tests/test_runner.py:23,44,55,67` |
| Q4: 是否存在实际输入输出？ | **是**。输入=JSON spec dict；输出=result JSON + stdout/stderr log 文件 + SHA256 校验 | `runner.py:87-175` 完整执行流 |
| Q5: 是否有完整运行案例？ | **是**。`examples/hello-benchmark.json` 可端到端运行，产生 result.json + logs | 实际执行验证：`tensorbench run --spec examples/hello-benchmark.json --output /tmp/tb-test-runs` → exit 0 |
| Q6: 是否有独立基准验证？ | **否**。仅有冒烟测试（执行 `print` 命令），无科学基准对照、无收敛/守恒验证、无误差分析 | `examples/hello-benchmark.json` 仅验证 runner 能跑通，非科学基准 |

### 2.2 辅助功能：JSON Schema 验证

| 问题 | 回答 | 证据 |
|---|---|---|
| Q1: 入口 | `tests/test_runner.py` 中 `jsonschema.validate()` | `test_runner.py:37-39` |
| Q2: 是否执行计算？ | **是**。对持久化结果做 schema 校验 | `test_runner.py:39` |
| Q3: 是否接入主程序？ | **仅在测试中**，runner 本身不自动校验 schema | `runner.py` 中 `validation.schema = "not_checked"` |
| Q4: 输入输出 | 输入=result JSON；输出=验证通过/异常 | `test_runner.py:37-39` |
| Q5: 运行案例 | 测试 `test_success_writes_result_and_logs` 覆盖 | `test_runner.py:21-40` |
| Q6: 独立基准验证 | **否**。仅结构校验，非科学验证 | — |

### 2.3 PR/报告声明 vs 代码实况差异

| 声明来源 | 声明内容 | 代码实况 | 差异 |
|---|---|---|---|
| README.md | "Foundation / specification stage" | 符合：runner 已实现但仅冒烟测试 | 一致 |
| README.md | "The example is only a smoke test" | 符合 | 一致 |
| ARCHITECTURE.md §5 | "Initial implementation sequence: 1-4 done, 5-7 pending" | 符合：1-4 已实现，5-7 未实现 | 一致 |
| agent/m14429 声明 | "task set and harness are in the repository; one full run...recorded" | 代码存在但未并入 main；runs/ 下有记录 | 声明属实但不在 main |
| agent/m14430 声明 | "compare.py produces the only numbers that belong in a delta" | compare.py 存在但未并入 main | 声明属实但不在 main |

---

## 三、成熟度判级（L0-L5）

### 3.1 main 分支模块判级

| 模块/范围 | 级别 | 证据 |
|---|---|---|
| `tensorbench/runner.py` (本地执行器) | **L2** | 真实算法代码：输入 JSON spec → subprocess 执行 → 输出 result.json + logs + SHA256。有 4 个测试覆盖。无科学基准对照（不满足 L4）。未接入主求解器/工作流（不满足 L3）。 |
| `tensorbench/cli.py` (CLI) | **L2** | 真实功能：解析参数 → 调用 runner → 输出 JSON。端到端可运行。 |
| `schemas/benchmark-result.schema.json` | **L1** | 数学与结构定义：JSON Schema 规范。有测试验证（`jsonschema.validate`）。非可执行算法。 |
| `docs/` (ARCHITECTURE + BENCHMARK_SPEC) | **L0** | 文档成果：架构设计与规范契约。无可执行代码。 |
| `README.md` + `LICENSE_SCOPE.md` | **L0** | 文档成果。 |
| `examples/hello-benchmark.json` | **L1** | 单元级验证：冒烟测试 spec。可运行但非科学基准。 |
| `tests/test_runner.py` | **L1** | 单元验证：4 个测试覆盖成功/失败/超时/非法输入。 |

### 3.2 L 分布统计

| 级别 | 模块数 | 占比 |
|---|---|---|
| L0 (文档) | 3 | 43% |
| L1 (数学/单元验证) | 3 | 43% |
| L2 (独立功能) | 2 | 14% |
| L3 (系统集成) | 0 | 0% |
| L4 (基准验证) | 0 | 0% |
| L5 (科研/工程成果) | 0 | 0% |

### 3.3 待合入分支模块判级（参考，非 main）

| 模块/范围 (分支) | 级别 | 证据 |
|---|---|---|
| `tensorbench/eval/scoring.py` (m14429) | **L2** | 真实评分算法：numeric/report/pr_fix 三类评分逻辑。有测试覆盖。未接入主工作流。 |
| `tensorbench/eval/session.py` (m14429) | **L2** | 真实会话执行器：遍历任务集、调用评分、记录结果。 |
| `tensorbench/eval/leakscan.py` (m14429) | **L2** | 真实泄漏扫描：检测答案字面量泄漏。有测试。 |
| `tensorbench/compare.py` (m14430) | **L2** | 真实对比逻辑：可比性检查 + delta 计算。 |
| `tensorbench/publish.py` (m14430) | **L2** | 真实发布逻辑：构建平台 payload + POST。 |
| `benchmarks/reference/stencil2d5pt/` (m14430) | **L3** | 有参考实现 + naive/optimized 对比 + 运行记录。但为参考工作负载，非生产基准。 |
| `tasks/` (m14429, 12 任务) | **L1** | 任务规范 + ground truth + reference impl。为测试夹具，非独立功能。 |
| `runs/` (m14429/m14430) | **L0** | 运行记录工件。非代码。 |

---

## 四、Top 问题

### P1: 无科学基准验证（L4 缺失）
- **现状**: runner 仅执行任意命令并测量 wall time，无科学正确性验证层。
- **影响**: 无法区分"快速但错误"与"慢但正确"的结果。
- **建议**: 实现 correctness validation hook（ARCHITECTURE.md §2.6 已规划）。

### P2: Schema 校验未集成到 runner
- **现状**: `validation.schema = "not_checked"` 硬编码；schema 校验仅在测试中执行。
- **影响**: 生产运行不自动校验结果结构。
- **建议**: runner 输出前自动校验 schema。

### P3: 无环境隔离
- **现状**: README 明确声明 "It is not a sandbox for untrusted benchmark code"。
- **影响**: 不能安全执行不受信任的工作负载。
- **建议**: 容器化或沙箱执行（后续增量）。

### P4: 无集群/分布式执行
- **现状**: 仅本地单进程 runner。
- **影响**: 无法扩展到大 workload。
- **建议**: ARCHITECTURE.md §5 已规划为第 7 步。

### P5: Agent 分支未并入 main
- **现状**: m14429 (8,673 行) 和 m14430 (5,334 行) 均未合并。
- **影响**: main 仍为 "Foundation stage"，大量工作未进入主干。
- **建议**: 审查后合入或关闭。

---

## 五、「曾声称为功能实为文档/测试」的膨胀清单

| 声明 | 实际性质 | 膨胀程度 |
|---|---|---|
| ARCHITECTURE.md 描述 7 个逻辑组件 | 设计文档，仅 runner 实现 | 高：6/7 组件未实现 |
| BENCHMARK_SPEC.md 9 节规范 | 契约文档，非实现 | 中：规范先于实现是合理做法 |
| README "Planned architecture" 列表 | 目标而非现状 | 低：README 已标注 "Foundation / specification stage" |
| agent/m14429 runs/ 目录 (~20 文件) | 运行记录工件，非代码 | 中：为证据记录，非功能膨胀 |
| agent/m14430 runs/stencil2d5pt/ (~30 文件) | 运行日志 + 结果 JSON | 中：为基准运行证据 |

**结论**: TensorBench main 分支无明显膨胀。文档量与代码量比例合理（~400 行文档 vs ~270 行代码），且 README 已诚实标注项目处于 "Foundation / specification stage"。

---

## 六、Verdicts 落表

```sql
INSERT INTO tensor_maturity_verdicts (repo, scope, mission_id, level, evidence, verdict_by)
VALUES
('TensorBench', 'tensorbench/runner.py', 14495, 2, '{"entry":"runner.py:79 run_benchmark","tests":"test_runner.py 4 tests passed","execution":"tensorbench run --spec examples/hello-benchmark.json exit 0","limitation":"no scientific benchmark validation, no correctness gate"}', 'audit2-ab'),

('TensorBench', 'tensorbench/cli.py', 14495, 2, '{"entry":"cli.py:24 main","calls":"runner.run_benchmark","e2e":"tensorbench run --spec ... exit 0"}', 'audit2-ab'),

('TensorBench', 'schemas/benchmark-result.schema.json', 14495, 1, '{"type":"JSON Schema v2020-12","validated_by":"test_runner.py:39 jsonschema.validate","lines":157}', 'audit2-ab'),

('TensorBench', 'docs/ARCHITECTURE.md', 14495, 0, '{"type":"design document","components_described":7,"components_implemented":1,"lines":129}', 'audit2-ab'),

('TensorBench', 'docs/BENCHMARK_SPEC.md', 14495, 0, '{"type":"specification contract","sections":9,"lines":114}', 'audit2-ab'),

('TensorBench', 'README.md', 14495, 0, '{"type":"project charter","honest_status":"Foundation / specification stage","lines":121}', 'audit2-ab'),

('TensorBench', 'examples/hello-benchmark.json', 14495, 1, '{"type":"smoke test spec","purpose":"verify runner executes","not_scientific_benchmark":true}', 'audit2-ab'),

('TensorBench', 'tests/test_runner.py', 14495, 1, '{"tests":4,"coverage":["success","failure","timeout","invalid_input"],"all_pass":true}', 'audit2-ab');
```

---

## 七、审计结论

TensorBench main 分支是一个**诚实的、最小可行的基准测试执行器基础设施**。代码无 stub/TODO/死代码，测试全部通过，CLI 端到端可运行。项目状态与 README 声明一致（Foundation stage）。

**核心发现**:
- ✅ 无伪造功能：所有代码均可执行
- ✅ 无膨胀声明：README 诚实标注项目阶段
- ⚠️ L2 为最高级别：无科学基准验证（L4 缺失）
- ⚠️ 大量 agent 工作（~14,000 行）未并入 main
- ⚠️ Schema 校验未集成到 runner 执行流

**建议优先级**: P1 (correctness gate) > P2 (schema integration) > P5 (merge agent branches) > P3/P4 (后续增量)。
