# Examples

| 文件 | 需要 Blender | 说明 |
|---|---|---|
| `custom_evaluator.py` | 否 | 用纯 Python 目标函数演示评估器契约与报告 |
| `../blender-loop demo` | 是 | 真实的剪影闭环：渲染 → IoU → 坐标下降 |

## 写自己的评估器

评估器就是一个函数：

```python
def evaluate(params: dict[str, float], workdir: Path) -> Evaluation:
    ...
    return Evaluation(params=params, score=score, metrics={...}, artifacts=[str(png)])
```

约定：

1. 只读 `params`，只写 `workdir`；
2. 同一组参数必须得到同一个分数（确定性）；
3. 失败要抛异常，不要返回一个"合法但很差"的分数；
4. 产生的图/JSON 放进 `artifacts`，报告会自动内联。

```bash
PYTHONPATH=src python examples/custom_evaluator.py
# -> out/custom/history.json, out/custom/report.html
```
