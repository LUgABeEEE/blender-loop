# 建模工作流：把 Blender 场景当成代码

这一篇讲**几何怎么产生**。`blender-loop` 只负责调度和迭代，模型本身必须由一个可重放的脚本生成；
否则后面的评估、缓存和报告都无从谈起。

## 1. 四条原则

| 原则 | 做法 | 原因 |
|---|---|---|
| 场景即代码 | 所有几何由一个 `.py` 从零构建，不用 `.blend` 手工改 | 可 diff、可回放、可参数化 |
| 确定性 | `--factory-startup` + `read_factory_settings(use_empty=True)` | 不受用户偏好、插件、上次残留影响 |
| 无头优先 | 只用 `blender -b`，不依赖 GUI | 服务器没有显示器；批处理是常态 |
| 单位统一 | 内部一律用米，导出前显式换算 | 避免 1000 倍的灾难 |

## 2. 场景脚本骨架

评估脚本从 `--` 之后拿参数，输出物只写到调用方给的路径：

```python
import bpy, json, math, sys

argv = sys.argv[sys.argv.index("--") + 1:]
params = json.loads(argv[0])          # 参数永远是普通 JSON
out_png = argv[1]                     # 输出路径由调用方决定

bpy.ops.wm.read_factory_settings(use_empty=True)   # 空场景，无默认灯/相机
...
print("BLENDER_LOOP_RENDER_OK")       # 给外层一个成功标记
```

几条硬约定：

- **不要**在脚本里 `import numpy` 之外的第三方包——Blender 自带的解释器与你系统的不是同一个；
- **不要**在脚本里读环境变量做业务判断，参数一律显式传入；
- **不要**把中间文件写进仓库，全部写进调用方给的 `workdir`；
- 结束时打印一行固定标记，外层只把它当作辅助信号（退出码才是权威）。

## 3. 单位与坐标系

Blender 的单位默认是米，而 3D 打印、测量、切片软件通常按毫米工作。

```python
MM = 0.001                    # 1 mm in Blender units
head_width = 0.228            # 228 mm，脚本内部用米
```

- 导出 STL 时**显式**乘以 1000，并在 manifest 里写 `"units": "mm"`；
- 坐标轴：Blender 是 Z-up，glTF 导出会转成 Y-up——在 README 里写清楚，别让下游猜；
- 正交相机做剪影评估时，`ortho_scale` 决定画面覆盖的世界尺寸，它是"像素 ↔ 毫米"换算的唯一依据。

## 4. 导出约定

| 格式 | 用途 | 注意 |
|---|---|---|
| STL（binary） | 3D 打印、网格检查 | 三角面、单位 mm、Z-up |
| GLB | 预览、引擎资产 | 贴图内嵌或同目录，Y-up |
| OBJ + MTL | 传统 DCC | `.mtl` 里引用的贴图必须同目录 |
| manifest.json | 追溯 | 参数、哈希、单位、生成命令 |

命名建议：`<project>_<part>_<version>.stl`，版本不进文件名就进目录；manifest 里同时记录
**参数 JSON 的哈希**，这样"这个 STL 是哪组参数出来的"永远查得到。

## 5. 为评估而渲染

自迭代的输入是"可比较的图像"，所以渲染必须固定：

```python
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = 1
scene.cycles.use_denoising = False
scene.render.film_transparent = True          # alpha = 剪影
scene.render.image_settings.color_mode = "RGBA"
```

- **透明胶片 + alpha 通道**是最稳的剪影来源，不受材质、灯光影响；
- 固定相机、固定分辨率、固定采样数，否则分数变化里混进了渲染噪声；
- 需要"好看的效果图"时另起一次渲染，不要和评估共用一套参数。

> 无头机器上 EEVEE / Workbench 依赖图形上下文，很多容器里直接失败；**Cycles CPU** 最稳。
> 代价是慢，但 1 spp 的剪影足够快（见 [机器调优](machine-tuning.md) 的实测）。

## 6. 常见坑

1. **默认场景污染**：不调 `read_factory_settings` 时，上次保存的灯和相机会一起进来，亮度、构图全变。
2. **单位错 1000 倍**：导出 228 而不是 0.228，STL 变成 228 米。
3. **布尔后不检查**：EXACT 布尔可能产出非流形面，先跑水密/边界检查再进入下一步。
4. **依赖 GUI 的算子**：`bpy.ops.view3d.*` 一类在 `-b` 下没有上下文，会静默失败或抛异常。
5. **随机性没固定**：粒化、散布类几何要显式设 seed，否则同一组参数两次结果不同。

## 7. 检查清单

- [ ] 场景能由脚本从空场景重建
- [ ] 参数全部经 argv 传入，脚本内无硬编码路径
- [ ] 渲染参数（引擎/采样/分辨率/相机）与评估绑定
- [ ] 导出单位、坐标系、命名在 README 写明
- [ ] manifest 记录参数哈希与生成命令
- [ ] 大网格操作前后都有水密/体积检查
