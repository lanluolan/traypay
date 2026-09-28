# 菜品识别与样本管理

## 食堂端操作

1. 结算页点击「拍照识别」。照片上显示区域编号：绿框为已匹配，红框为未知或相似菜待确认，灰框为人工忽略。
2. 对红框选择候选菜品或从菜单中选菜；餐具等误检可以点「忽略此区域」。漏识别的菜点「补录菜品」。每项可修改份数。
3. 核对整盘菜品、份数和合计，勾选确认后扫码。修改任一项会取消整盘确认。
4. 检测器不可用或没有检测到菜时，重拍或点击「新建人工录单」。新建/重拍会清除旧购物车；不会自动把整张托盘当一道菜。
5. 菜品库中点击「补拍 / 样本管理」。选择相册或拍照，逐张确认裁剪结果；可切换为仅含目标菜品的整图，或跳过重拍。
6. 保存补拍照片后，使用全部剩余样本重建该菜特征。可以删除错误样本，但至少保留一张；替换唯一错误样本时先补拍正确照片。

录入和补拍只更新特征库，不训练或改变 ResNet50 权重。相似冲突会显示菜名。

## HTTP 契约

所有接口均要求管理员 Bearer token。

| 接口 | 请求 / 响应 |
|---|---|
| `POST /admin/detect` | 上传 `img`；返回 `regions`、方向已校正的 `image_preview`（JPEG base64）、原图宽高、`review_token` |
| `POST /admin/checkout/manual` | 返回无检测区域的人工录单 `review_token` |
| `POST /admin/purchase` | form：`a_id`、`u_id`、`review_token`、`tray_confirmed=true`、`review` JSON 数组、`total_price` |
| `POST /cuisine/samples/preview` | 上传 `img`；返回方向已校正的 `original` 和建议 `crop`（PNG base64）；不保存样本 |
| `POST /cuisine/add` | 上传已确认的 PNG `img`（可重复）、`crops_confirmed=true`、`c_name`、`c_price` |
| `GET /cuisine/<c_id>/samples` | 返回样本 `id`、需鉴权的 `url`、`confirmed_crop` |
| `POST /cuisine/<c_id>/samples` | 上传已确认的 PNG `img`（1–20 张）、`crops_confirmed=true` |
| `GET /cuisine/<c_id>/samples/<sample_id>` | 获取样本图片 |
| `DELETE /cuisine/<c_id>/samples/<sample_id>` | 删除样本并重建该菜特征 |

每个 region 包含 `region_id`、原图像素坐标 `box=[x1,y1,x2,y2]`、`status`（`accepted` / `ambiguous` / `unknown`）、`selected` 和 `candidates`。
候选带 `c_id`、`c_name`、`c_price`、`similarity`。相似度不是正确率。

`review` 示例（对应两个检测区域，第二个被明确忽略，另补录一道菜）：

```json
[
  {"region_id": 0, "c_id": 3, "quantity": 2, "confirmed": true},
  {"region_id": 1, "c_id": null, "quantity": 0, "confirmed": true},
  {"region_id": null, "c_id": 7, "quantity": 1, "confirmed": true}
]
```

后端要求原始区域全部且仅出现一次、全部明确确认、整盘确认，以及 1–100 份有效菜品。
后端按数据库菜价重新计算；与客户端核对金额不同则返回 HTTP 409，要求重新核对。
草稿绑定收银员，15 分钟过期。它用于验证确认流程，**不是防重复扣款的幂等订单**。

检测器不可用为 HTTP 503 / code 3；没有检测框为 HTTP 200 / code 4；无效图片为 code 2。
未知或歧义菜品正常返回 code 0 和待确认区域，不能据此直接判断可扣款。

**发布要求：后端与食堂端必须一起更新。** 旧版仅提交 `cuisines` 的扣款请求会被拒绝。
顾客端接口无需变化。没有数据库 schema 变更。

## 参数与持久化

- `DISH_ACCEPT_THRESHOLD`：默认 0.60。
- `DISH_AMBIGUITY_MARGIN`：默认 0.05；最高分达标但前两名分差不足时必须人工选择。二者都需要真实场景标定。
- `MAX_CONTENT_LENGTH`：默认整次请求 24 MiB。预览最长边缩小至 1600 像素；收银显示预览最长边 1200 像素。
- 新样本保存为 `static/cuisine/<c_id>_sample_<uuid>.png`，已确认裁剪不再自动二次裁剪。旧 `<c_id>.png` / `<c_id>_<n>.png` 仍可浏览，并按原规则处理。
- 新特征快照为 `DISH_STORE_DIR/store.npz`，ID 和向量通过同一次文件替换提交；旧 `index.json` + `vectors.npy` 可读，下次写入自动迁移。
- 升级前备份完整特征目录和样本目录；旧文件在迁移后不再更新，回滚旧代码不能直接使用它们作为最新特征。
- 补拍/删除的常规异常会保留原样本和在线特征。图片、数据库和向量库仍不是跨存储事务；应一起备份，异常停机后检查一致性。
- 仍要求单个后端 worker；跨进程特征同步不在本批改动范围。

## 验证范围

识别单元测试覆盖空检测、检测器降级拒绝结算、相似候选分差和同菜多份。
后端 `tests/test_recognition_workflow.py` 使用隔离的 SQLite 与模拟特征提取，验证 HTTP 流程、样本预览和失败回滚；不替代 MySQL 并发测试。
Flutter `test/review_cart_test.dart` 覆盖未知/歧义项拦截、整盘确认、份数、金额和清空旧结果。
真实设备拍照/扫码、真实模型准确率和阈值标定需要现场验收。
