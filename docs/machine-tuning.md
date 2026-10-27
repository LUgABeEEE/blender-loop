# 机器调优：先量，再调

这一篇讲**跑得稳**。Blender 的布尔、细分、渲染都很容易把一台机器吃满；
在共享机器上，一次失控的进程会连带把别的服务一起拖死。所以顺序是：**基准 → 预算 → 限制**。

## 1. 先量

```bash
blender-loop bench --blender /path/to/blender --out out/bench
```

输出 `bench.json`（机器可读）与 `bench.html`（人看）。它测四件事：

1. 无头冷启动耗时（每次调用都有这笔固定开销）；
2. 不同分辨率/采样数下的 Cycles CPU 渲染耗时；
3. 一次 EXACT 布尔的耗时与结果规模；
4. 子进程峰值 RSS（上限是否够用的依据）。

一次实测（Ubuntu 24.04、16 核 CPU、15 GB 内存、无独显、Blender 4.2.9 LTS）：

| 项目 | 数值 |
|---|---|
| 冷启动（无场景） | 0.23 s |
| 渲染 1024² / 1 spp | 0.03 s |
| 渲染 1024² / 16 spp | 0.26 s |
| 渲染 1024² / 64 spp | 0.98 s |
| EXACT 布尔（29k 顶点） | 0.23 s |
| 子进程峰值 RSS | 454 MB |

这些数字决定了你该把预算设成多少——而不是拍脑袋。

## 2. 一次调用 = 一个进程

本项目不为每次评估保留常驻的 Blender：

```
python 主进程 ──spawn──> blender -b --factory-startup -P eval.py -- <args>
      │                        │
      └── 读回 PNG / JSON ─────┘
```

- 好处：崩溃隔离（一个坏网格不会污染下一次），状态干净，易并行（虽然默认串行）；
- 代价：每次都有冷启动（上表 0.23 s）。所以**单次评估的预算**至少要 `启动 + 渲染`。

预算换算的例子：`0.23 s（启动）+ 0.26 s（1024²/16spp）≈ 0.5 s/次`，
60 次评估约 30 秒；如果换成 64 spp，就变成 ~1.2 s/次。

## 3. 内存：给地址空间设上限

```python
BlenderConfig(binary="blender", memory_mb=8192)   # RLIMIT_AS = 8 GiB
```

- 用 `RLIMIT_AS`（地址空间）而不是 RSS：在分配阶段就失败，而不是等到系统 OOM；
- 失败形态是 Blender 自己 `bad_alloc` 退出，**不会**触发内核的全局 OOM 选择器；
- 代价：超限即失败。这时应该**拆阶段**（先切孔再导出、再单独抽壳），而不是调大上限。

> 事故记录：100 万面网格的 EXACT 布尔曾把匿名内存推到 12 GB，触发全局 OOM，
> 与 Blender 同 cgroup 的 Web 服务一起被杀。上限 + 串行之后同类事故不再出现。

## 4. 串行：一把 flock 锁

```python
BlenderConfig(lock_path=Path("out/blender.lock"))
```

- 同一时刻只允许一个 Blender，避免两个大操作叠加把内存打爆；
- 锁是**跨进程**的（POSIX `flock`），多个脚本/多个终端也生效；
- 等待有上限（默认 3600 s），超时会失败而不是无限挂起；
- 非 POSIX 平台自动退化为不加锁。

## 5. 超时：卡死比慢更危险

```python
BlenderConfig(timeout_s=900)     # 单次调用上限
```

- 卡在驱动、坏网格、无限循环时，只有超时能救你；
- 超时的结果对象里 `timed_out=True`，调用方必须显式处理（默认 `check()` 会抛错）；
- 批量跑之前先用 bench 测一次最坏情况，把超时设为它的 3–5 倍。

## 6. 引擎选择

| 引擎 | 无头可用性 | 适用 |
|---|---|---|
| CYCLES（CPU） | ✅ 稳定 | 评估渲染、效果图 |
| EEVEE | ⚠️ 需要图形上下文，容器里常失败 | 有 GPU/显示时 |
| Workbench | ⚠️ 同上 | 快速预览（本地） |

评估一律用 Cycles CPU；有 GPU 时再在评估器内部切 `device="GPU"`，不要把渲染引擎的选择散落在脚本各处。

## 7. 可观测性

每次调用返回结构化结果：

```python
result = run_script(config, script, args)
result.returncode, result.timed_out, result.duration_s
result.stdout, result.stderr        # 失败时取 stderr 末尾几行
result.check()                      # 不 ok 就抛 BlenderError（含 stderr 尾部）
```

- 把 `duration_s` 记进评估记录，报告里能看到"哪一步变慢了"；
- 失败信息带命令与 stderr 尾部，避免"只看到 rc=1"。

## 8. 调优清单

- [ ] 跑过 `bench`，把启动/渲染/布尔耗时记下来
- [ ] `memory_mb` 不超过机器的 60%，批量操作前先小样验证
- [ ] 长任务开 `lock_path`，同一机器只跑一个 Blender
- [ ] 单次超时设为实测最坏值的 3–5 倍
- [ ] 失败路径有 `check()`，不要静默继续
- [ ] 大网格先简化/代理，再进评估循环
