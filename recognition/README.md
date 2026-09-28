# dish-recognition — 菜品识别模块

「检测 + 特征检索」两段式菜品识别的本地实现。

食堂端识别确认、补拍、样本管理和新版接口见 [WORKFLOW.md](WORKFLOW.md)。

```
照片 ──► DishDetector ──► 逐框裁剪 ──► ResNet50Embedder ──► FeatureStore 余弦检索 ──► c_id 列表
         (YOLO, 可插拔)   (留 4% 边距)  (冻结, 2048 维,      (每菜多向量取最大相似度,
                                        L2 归一化)           低于阈值报 unknown)
```

**核心原则：模型权重永不更新。** 上新 = 向特征库追加向量；两道菜太像时返回
`conflicts` 警告让经办人补拍有区分度的照片，而不是用梯度下降去「掰开」特征 ——
后者会使整个特征库失效并引发灾难性遗忘。

## 为什么是这个方案

分类模型（"这张图是第几类菜"）每上一道新菜都要重训、重新部署，而食堂每周都在
换菜。检索方案把「认菜」拆成两件事：一个**永远不变**的编码器，和一个**随时可追加**
的向量库。上新变成一次前向推理 + 一次 `np.vstack`，几秒钟的事，而且不影响任何
已有菜品的识别结果 —— 这是分类方案给不了的性质。

代价是准确率上限受限于 ImageNet 特征的判别力。视觉相近的菜（番茄蛋汤 vs 紫菜
蛋汤）分不开时，正确做法依次是：换有区分度的餐具 → 补拍更多角度 → 最后才考虑
微调编码器（见下方「后续增强路线」）。

## 安装

依赖只在 [pyproject.toml](pyproject.toml) 里声明一处：

```powershell
cd recognition
pip install -e .                       # numpy/Pillow/torch/torchvision，供后端 import
pip install -e ".[yolo]"               # YOLO 检测器（ultralytics，AGPL-3.0）
```

不装 ultralytics 时仅可整图录入样本；托盘识别会明确报检测器不可用，需人工录单。
自动结算识别需要安装 `[yolo]` 并提供可用权重。

### 权重需要自己放入 `weights/yolov8n.pt` ⚠️

仓库不含二进制文件。从
[ultralytics 官方 release](https://github.com/ultralytics/assets/releases)
下载 `yolov8n.pt`（COCO 预训练，约 6.2 MB）放进 `weights/`。

**核对哈希再用。** `.pt` 是 pickle 格式，`torch.load` 会执行其中的构造指令 ——
来路不明的权重等同于运行来路不明的代码。想自查的话：`.pt` 实为 zip，用
`zipfile` 解出 `data.pkl` 后 `pickletools.genops` 看 `GLOBAL` 指令，正常的只会
引用 `torch.*` / `ultralytics.*` / `collections`；出现 `os`、`subprocess`、
`builtins.eval` 之类就是恶意的。

`RecognizerConfig.detector_weights` 的默认值会自动解析到这个文件（见
[config.py](dish_recognition/config.py) 的 `_default_detector_weights`），所以
CLI、维护脚本、单测和后端用的是同一份权重，都不需要配置。

裸文件名 `"yolov8n.pt"` 作默认值不行：ultralytics 会因此在首次构建检测器时联网
下载到**当前工作目录**。容器里更糟，那个目录不是挂载卷，每次重启都要重下，
且要求结算机能访问外网。

`DISH_DETECTOR_WEIGHTS` 仍可覆盖，设为 `none` 则关闭检测器。

> 特征库与识别编排本身只用到 numpy 和 Pillow，torch/torchvision 是嵌入器才需要的
> —— 所以单测装这两个就能跑（见下方「测试」与 CI）。

## 命令行用法

```powershell
# 上新：一道菜拍 5–10 张不同角度（--strict 表示与已有菜品过于相似时报错退出）
python -m dish_recognition enroll --id 3 tomato_egg_1.jpg tomato_egg_2.jpg --strict

# 结算识别：输出每个检测框的匹配结果；dish_ids 保留重复（两份同菜计两次）
python -m dish_recognition recognize tray.jpg

# 查看 / 删除
python -m dish_recognition list
python -m dish_recognition remove --id 3
```

特征库默认存到 `./dish_feature_store/store.npz`（ID 与向量单文件原子替换；兼容读取旧 `vectors.npy` + `index.json`），
用 `--store` 指定其他位置。

## Python API

```python
from pathlib import Path
from dish_recognition import DishRecognizer, RecognizerConfig

recognizer = DishRecognizer(RecognizerConfig(store_dir=Path("dish_feature_store")))

report = recognizer.enroll("3", ["a.jpg", "b.jpg"])   # report.conflicts: 过近的已有菜品
result = recognizer.recognize("tray.jpg")
result.dish_ids()      # ['3', '3', '7'] —— 重复保留，直接可计价
result.unknown_count   # 低于阈值的框数，前端应提示人工处理
result.to_dict()       # 含每框 box / similarity / runner_up，可直接 jsonify
```

`detector` / `embedder` / `store` 都可注入，测试时用桩替身即可绕开 torch ——
见 [tests/test_recognizer.py](tests/test_recognizer.py)。

## 接入 Flask 后端

[dish_recognition/legacy_api.py](dish_recognition/legacy_api.py) 提供
`store / store_many / detect / delete` 四个函数，签名与项目早期那套百度 API 封装
一致，后端只需改 import：

```python
from dish_recognition import legacy_api as cuisine_detect
```

环境变量：`DISH_STORE_DIR`、`DISH_DETECTOR_WEIGHTS`（`none` 关闭检测器）、
`DISH_ACCEPT_THRESHOLD`。

> ⚠️ 两个接入要点：
> 1. **`detect()` 保留重复项**（同菜两份 → id 出现两次）。后端绝不能用
>    `Cuisine.c_id.in_(ids)` 去查 —— 那会把两份合成一份，少收一半钱。
> 2. **`/cuisine/add` 要收多图。** 识别精度强依赖多角度注册。

### 线程与进程约束

四个函数由 `_pipeline_lock` 串行化，可以安全地从多线程 WSGI 服务器调用
（后端跑 `gunicorn --threads 4`）。但这只覆盖**单个进程**：

**跑 2 个以上 gunicorn worker 是正确性 bug，不是调优选项。** 每个 worker 持有自己
那份特征库，`/cuisine/add` 上新的菜只进了其中一个的内存，其余继续用旧库。请求落到
哪个 worker 是随机的，症状是「上新后时灵时不灵」—— 极难诊断。要横向扩展得先做
共享特征库（按 mtime 重载或外置索引）。

## 阈值标定

| 参数 | 默认 | 含义 |
|---|---|---|
| `accept_threshold` | 0.60 | 低于此相似度的框判为 unknown（宁可让人工确认，不可错扣钱） |
| `ambiguity_margin` | 0.05 | 前两名分差不足时判为 ambiguous，人工选择；待现场标定 |
| `conflict_threshold` | 0.80 | 上新时与已有菜品相似度超过此值则警告 |
| `detector_conf` | 0.35 | YOLO 置信度下限 |

**默认值只是起点，拿它直接上线等于没标定。** 完整的采集与标定规范见
[../ROADMAP.md](../ROADMAP.md) 阶段 3 —— 那里有实测的「什么值得拍」数据表
（结论：光照几乎不用管，旋转和取景才是大头）。

## 后续增强路线（均不改本模块接口）

1. **检测器**：目前用 COCO 预训练 `yolov8n.pt` 做 class-agnostic 检测（碗/杯类
   在托盘俯拍下可用）。生产方案是自标 300–500 张托盘照片，训一个单类 "dish" 的
   YOLOv8n，把权重路径传给 `detector_weights` —— 检测器接口不变。
2. **嵌入器**：视觉相近菜品分不开时，用积累的菜品照片以 ArcFace/Triplet 损失微调
   ResNet50，微调完**永久冻结**、重算一遍特征库（`enroll --replace` 逐菜刷新）。
   注意新模型与旧特征库完全不兼容。
3. **规模**：菜品数上千后把 `FeatureStore` 的暴力矩阵乘换成 faiss，接口不变。
   目前的 O(n) 检索在几百道菜的量级下是微秒级，远不是瓶颈。

## 测试

```powershell
python -m unittest discover -s tests -v
```

| 文件 | 需要 torch？ | 覆盖 |
|---|---|---|
| `test_feature_store.py` | 否 | 归一化、多视角取最大、冲突检测、原子持久化 |
| `test_detector_fallback.py` | 否 | `default_detector()` 永不抛异常；缺 ultralytics 只 warn，坏权重要 error |
| `test_recognizer.py` | 否 | 整条管线（桩替身）：**重复项保留**、低分判 unknown、裁剪留边、上新回滚 |
| `test_embedder_smoke.py` | **是**（无则自动跳过） | 真实 ResNet50 的输出契约：形状、L2 归一化、确定性、分批一致 |
