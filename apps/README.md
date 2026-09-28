# apps — Flutter 客户端

| 目录 | 包名 | 角色 |
|---|---|---|
| [user/](user/) | `pay_system` | 顾客端：登录/注册、余额与充值、消费记录、付款二维码 |
| [admin/](admin/) | `admin_paysystem` | 食堂端：拍照识别菜品结算、扫码收款、营业额统计、菜品库管理 |
| [common/](common/) | `checkout_common` | 两端共享的配置与页面，通过 `path:` 依赖引入 |

## 首次运行需要两步准备

### 1. 生成平台脚手架

`android/`、`ios/` 等平台目录不在版本库里（见 ISSUES.md D7）。两个 app 各跑一次：

```powershell
cd apps/user;  flutter create --platforms=android .
cd ../admin;   flutter create --platforms=android .
```

食堂端要用相机和扫码，生成后往 `android/app/src/main/AndroidManifest.xml` 的
`<manifest>` 下补一行：

```xml
<uses-permission android:name="android.permission.CAMERA" />
```

`apps/common` 是纯 Dart 包，不需要这一步。

### 2. 放入图片资源

代码只引用三处：两端 `main.dart` 的 `img/shopping.png`、顾客端
`person/mine.dart` 的 `img/touxiang.jpg`、common 的 `img/forgetpassword.png`。
缺了不影响编译，运行时显示占位错误框。

## common —— 共享了什么，以及为什么只有这些

| 文件 | 作用 |
|---|---|
| `src/api_config.dart` | 后端地址，`--dart-define` 覆盖 |
| `src/api_client.dart` | `apiRequest` / `apiMultipart` / `sendApi` |
| `src/auth_session.dart` | 进程内 token + 401/403 处理 |
| `src/home_shell.dart` | MaterialApp + 底部导航 + 选中态 |
| `src/month_day_picker.dart` | 月/日联动下拉框 |
| `src/cost_detail_page.dart` | 单笔消费的菜品明细页 |
| `src/register_page.dart` | 注册页 |
| `src/forget_password_page.dart` | 忘记密码页（**只有界面，后端无对应接口**） |
| `src/menu_items.dart` | 设置项行 |

两个页面原先各自 `import '../main.dart'` 只为在返回时构造 `MyApp()` —— 正是这一处
依赖让两份相同的代码无法共享。改为由调用方注入：

```dart
Forget_password(loginPageBuilder: (_) => MyApp())
CostDetailPage(items: 明细, homeBuilder: (_) => Home_load(user, password))
```

`cost_detail` 看着依赖各端不同的 `User`/`Admin`，但逐字段查下来**从没读过模型的
任何东西** —— 那个字段只是被存着，好在按返回键时构造 `Home_load`。

**没有提取的部分，及原因**（不是遗漏，是不该合）：

- `models/user.dart` / `models/admin.dart` —— 实体完全不同：顾客端是
  `u_id/u_name/u_money`，食堂端是 `a_id/a_name/a_store_name/a_address`。合并是错的。
- `home/home_load.dart` —— 只剩导航项与页面列表两份配置，壳子已进 `home_shell`。
- `home_page` / `pay_page` / `mine` / `main` —— 业务本就不同。

## API 地址配置

集中在 [common/lib/src/api_config.dart](common/lib/src/api_config.dart)，
通过 `--dart-define` 覆盖，不需要改代码：

```powershell
# Android 模拟器连宿主机（10.0.2.2 = 宿主机 localhost）—— 这也是默认值
flutter run --dart-define=API_BASE=http://10.0.2.2:5000

# 真机连开发机（同一 WiFi）
flutter run --dart-define=API_BASE=http://192.168.x.x:5000

# 打生产包
flutter build apk --dart-define=API_BASE=https://api.example.com
```

默认值是模拟器路由而不是某台生产服务器：一个**貌似合理但过时**的 IP 烧进
release 包，比一个明显是本地的默认值更危险 —— 前者会安静地打到别人的机器上。

## 鉴权

后端除 `/user/login`、`/user/register`、`/admin/login`、`/healthz` 外的所有接口都要求
`Authorization: Bearer <token>`。

**新增网络请求一律用 `apiRequest` / `apiMultipart` / `sendApi` 三个函数，
不要直接写 `http.Request` / `http.MultipartRequest` / `request.send()`。**

忘了带 header 不会编译报错，只会在真机上变成一个 401，而所有调用点都只判断
`statusCode == 200` 且没有 else —— 表现就是"点了没反应"。
**图片上传尤其容易漏**：`/admin/detect`（识别菜品）和 `/cuisine/add`（上新）
都是管理员接口，用裸的 `http.MultipartRequest` 发出去必然 401，这两个功能会
整个失效。单测 [common/test/api_client_test.dart](common/test/api_client_test.dart)
锁住了这个行为。

token 在登录、注册、以及顾客端刷新余额那次重新登录时写入，**不持久化**：两端启动都是
登录页，存到磁盘既没人读也多一份凭据落地。等做自动登录时再一起加。

401 和 403 含义不同，提示语要区分：401 是「token 失效，重新登录可解决」，会触发
`AuthSession.onSessionExpired` 跳回登录页；403 是「权限不足，登录也没用」，
不跳转。两端的 `main()` 各自注册了那个回调。

> 食堂端调用 `/user/recharge` 和 `/user/query/record/detail` 时带的是**管理员
> token**，后端允许管理员操作顾客记录 —— 柜台充值和查小票都要靠这个。

## 构建

```powershell
cd apps/common   # 先跑 common，两端都 path 依赖它
flutter pub get
flutter test

cd ../user       # 或 ../admin
flutter pub get
flutter analyze
flutter run --dart-define=API_BASE=http://10.0.2.2:5000
```

`common` 是 `path:` 依赖，改动它后两端 `flutter pub get` 会自动取到新代码，无需发包。

## 依赖取舍

两端 pubspec 只留 `lib/` 里真的 import 了的包。历史上删掉的：

- **`find_dropdown`** —— 停更于 Flutter 2 时代，内部仍用已被移除的
  `TextTheme.subtitle1`、`ThemeData.errorColor`，导致 `flutter build` 失败
  （`flutter analyze` 不分析依赖源码，查不出来）。两端只用它做月份/日期选择，
  已换成内置的 `DropdownButton<String>`。

  换的时候注意一个 `DropdownButton` 特有的约束：`value` 必须存在于 `items` 中，
  否则断言失败。原来选了 31 号再切到 30 天的月份不会有事，现在会崩，所以
  [month_day_picker.dart](common/lib/src/month_day_picker.dart) 换月时一并清空了 `day`。

- **`scan`** —— 空安全前的包，是唯一阻挡 Dart 3 SDK 约束的东西，且从未被 import。

- **一批纯声明的包** —— `mqtt_client`、`flutter_screenutil`、`jhtoast`、`provider`、
  `flutter_local_notifications`、`flutter_datetime_picker`、`flutter_localizations`、
  以及两端互抄出来的交叉声明（user 声明了只有 admin 用的 `barcode_scan2`，
  admin 声明了只有 user 用的 `qr_flutter`）。

  `cupertino_icons` 保留 —— 它提供图标字体资源，按惯例不 import。

## 命名规范

`lib/` 下的目录与文件一律 `lower_case_with_underscores`（Dart effective style）。
类名里仍有 `Home_load`、`payPage`、`add_Food` 这类历史命名 —— 改名会波及所有调用点，
暂时在 `analysis_options.yaml` 里关掉了对应的 lint 而不是硬改。

## 遗留问题

见仓库根的 [../ISSUES.md](../ISSUES.md)，App 相关的是 B7（当月合计在记录超过
10 条时偏小）和 D7（平台脚手架未纳入版本库）。
