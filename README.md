# Smart Checkout Platform

基于图像识别的智慧食堂结算平台。顾客把托盘推到结算台，摄像头拍一张照片，
系统认出盘里有哪几道菜、各几份，算出总价，扫顾客付款码扣款。

## 目录结构

```
project2/
├── recognition/            # 菜品识别模块：检测 + 特征检索（dish_recognition 包）
│   ├── dish_recognition/   #   config / detector / embedder / feature_store
│   │                       #   / recognizer / legacy_api / cli
│   ├── weights/            #   固化的 YOLOv8n 权重（需自行放入，见下）
│   └── tests/              #   单元测试（无 torch 也可运行）
├── backend/                # Flask 结算服务
│   ├── payment/            #   create_app 工厂 + config + models + auth + views
│   ├── tests/              #   auth 单测（可进 CI）+ 接口集成测试（需 MySQL）
│   ├── manage.py           #   开发入口；生产由 gunicorn 跑 manage:app
│   ├── .env.example        #   环境变量模板
│   └── Dockerfile          #   从仓库根构建：docker build -f backend/Dockerfile .
├── apps/                   # Flutter 客户端
│   ├── user/               #   顾客端（包名 pay_system）
│   ├── admin/              #   食堂端（包名 admin_paysystem）
│   └── common/             #   两端共享包 checkout_common（path 依赖）
├── .github/workflows/      # CI：识别单测 + 后端单测 + 三个 Flutter 包 analyze
├── ISSUES.md               # 遗留问题清单（发现即记，解决即删）
└── ROADMAP.md              # 运行与部署工作清单
```

## 识别方案一句话

冻结的 ResNet50 把检测框内的菜品图编码成 2048 维向量，与特征库做余弦检索；
上新 = 追加向量（**模型权重永不更新**），两道菜过于相似时向经办人报冲突，
让人去补拍有区分度的照片，而不是用梯度下降去"掰开"特征 —— 后者会让整个特征库
失效。设计缘由见 [recognition/README.md](recognition/README.md)。

## 快速开始

### 1. 补齐两份二进制资产

仓库不含二进制文件，跑起来前需要自己放入：

| 路径 | 内容 | 来源 |
|---|---|---|
| `recognition/weights/yolov8n.pt` | COCO 预训练检测器权重，约 6.2 MB | [ultralytics 官方 release](https://github.com/ultralytics/assets/releases) |
| `apps/*/img/*.png`、`apps/common/img/forgetpassword.png` | 界面图标与插图 | 自备 |

`yolov8n.pt` **务必从 ultralytics 官方渠道下载**并核对哈希。`.pt` 是 pickle
格式，加载即执行其中的构造指令 —— 来路不明的权重文件等同于运行来路不明的代码。

代码里引用到的图片只有三处：两端 `main.dart` 的 `img/shopping.png`、
顾客端 `person/mine.dart` 的 `img/touxiang.jpg`、common 的
`img/forgetpassword.png`。缺了不会编译失败，运行时会显示占位错误框。

### 2. 生成 Flutter 平台脚手架

`android/`、`ios/` 等平台目录不在仓库里（它们是可再生成的模板）。在每个
app 目录下执行一次：

```powershell
cd apps/user     # 再对 apps/admin 做一遍
flutter create --platforms=android .
```

`apps/common` 是纯 Dart 包，不需要这一步。

### 3. 后端

```powershell
cd backend
pip install -e "../recognition[yolo]"
pip install -r requirements.txt
copy .env.example .env          # 填数据库账号、生成 SECRET_KEY
flask --app manage init-db      # 建表 + 创建食堂端账号（密码只打印一次）
$env:APP_ENV="dev"; python manage.py
```

详见 [backend/README.md](backend/README.md)。

### 4. App

```powershell
cd apps/admin                   # 或 apps/user
flutter pub get
flutter run --dart-define=API_BASE=http://10.0.2.2:5000
```

详见 [apps/README.md](apps/README.md)。

### 5. 识别模块单独使用

```powershell
cd recognition
python -m dish_recognition enroll --id 3 菜品照片1.jpg 菜品照片2.jpg
python -m dish_recognition recognize 托盘.jpg
```

## 上线前必读

识别与人工确认流程见 [recognition/WORKFLOW.md](recognition/WORKFLOW.md)。后端与食堂端需同时更新。
上线前还需要检查：

1. **检测失败必须人工录单或重拍**。结算不再使用整图兜底；未知/相似菜需确认，
   所有菜品和份数还需整盘核对。监控 `/healthz` 的检测器状态，及时恢复自动识别。
2. **阈值必须用真实照片标定**（ROADMAP 阶段 4）。默认的 0.60 只是起点，
   拿它直接上线等于没标定。
3. **gunicorn 只能开 1 个 worker**。特征库是进程内单例，多 worker 会让新上的菜
   时灵时不灵。详见 [backend/Dockerfile](backend/Dockerfile) 的注释。
