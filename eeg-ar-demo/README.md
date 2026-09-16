# EchoMind EEG × AR 联动演示版

双击 **EchoMind_EEG_AR_Demo.exe**。程序会打开两个独立窗口：原生 EEG Monitor 和 EchoMind AR 网页应用。Windows 电脑无需另外安装 Python、Node 或脑波设备；使用本机 Edge 或 Chrome 打开 AR 窗口。

## 30 秒演示方法

1. 将鼠标停在 AR 中的 **Look here to activate** 上约 1.6 秒，观察 EEG 窗口中的 Attention 上升后进入主界面。
2. 移到 **I’m thirsty** 中央卡片。监测窗口同步显示目标、虚拟波形、8 个频段、注意力及确认进度。
3. 稍作停留进入请求确认面板，再停留或点击 **Send request**，看到本地演示确认反馈。
4. 在 EEG 窗口勾选 **Low attention · block confirmation**，返回 AR 选择卡片：注意力约 41–44，继续停留或点击也不会确认。
5. 取消勾选，移出卡片后重新停留，即可恢复正常确认。**Reset demo** 会回到 AR 初始界面并清空本轮记录。

点击是一个候选意图，也需满足相同的注意力和停留条件；点击后请保持在目标上。移开、切换目标、窗口失焦或连接中断会取消尚未完成的意图。导航箭头、Care/Family 模块切换、关闭及返回等导航仍可直接操作。

## 演示数值

| 参数 | 默认值 | 含义 |
|---|---:|---|
| Baseline | 32 | 未聚焦时的虚拟注意力 |
| Focus | 90 | 持续聚焦后的虚拟注意力 |
| Threshold | 75 | 允许确认的注意力门槛 |
| Dwell | 1600 ms | 连续停留时间 |

在 EEG 窗口展开 **Demo parameters**，修改数值并点 **Apply**。范围要求 `0 ≤ Baseline < Threshold ≤ Focus ≤ 100`，Dwell 为 500–10000 ms。数值修改会清除正在累积的意图；只在本次运行有效。Reset 保留当前参数和模式，重启恢复默认值。

**Attention 是人为设定的 0–100 演示指数，不是概率或真实测量。** 波形、频段、信号质量、放松值均由脚本生成。可以用鼠标模拟注视，也可以接入眼动软件的真实相机注视位置；两种模式的 EEG 辅助确认都仍是模拟数据，不读取真实脑电。护理请求、家人回复都是本地界面反馈。

## 真实相机眼动联动

1. 在眼动软件中使用 **Live camera**，连接一台能同时拍到双眼的相机，分别框选 **Eye A / Eye B**，完成 **9-point calibration**。
2. 启用眼动软件中的 **Link camera to AR**，点击 **Open EchoMind AR**。网页左下角选择 **Camera gaze**（通过 `?input=camera` 打开的页面会自动选择）。
3. 将网页放在刚才校准的同一台显示器上，点击 **Start fullscreen gaze**。真实注视位置以绿色光圈显示，标注 **CAMERA GAZE · EEG SIMULATED**。
4. 注视 **Look here to activate**，保持眼位稳定。网页把注视目标交给原有 EEG 演示流程，达到注意力门槛和停留时间后才会确认；不会直接模拟点击。
5. 双眼丢失、停止采集、校准重置、切换窗口或退出全屏都会暂停注视操作。按 **Esc** 退出全屏。切换 **Mouse demo** 可恢复原有鼠标演示；两种输入不会同时操作控件。

真实相机数据必须先校准。普通窗口模式暂停真实眼动，因为校准对应的是整块显示器，不能直接缩放成网页窗口坐标。移动相机或明显改变头部位置后请重新校准。联动仅传输本机注视坐标、追踪状态和质量数值，**不传输相机视频或眼部图像**。眼动是真实采集，EEG 波形、注意力指数和确认辅助仍为模拟；实际定位精度需用你的相机画面验证。

## 窗口与文件

- 网页内的 EEG 注意力浮窗：拖动标题栏移动位置，拖动右下角调整大小，点击右上角 **−** 隐藏；点击右下角 **EEG ↗** 恢复。位置、大小及隐藏状态会在同一浏览器中记住。聚焦标题栏或缩放角后，也可用方向键微调（Shift 加快）。浮窗不占用顶部布局空间，隐藏后联动继续运行。
- EEG 窗口可自由调整大小，AR 是独立应用窗口，可在副屏展示。右键 AR 仍可切换背景、返回主页和导出画面。
- 关闭 AR 后可点 **Open AR window** 重新打开。退出 EEG 窗口会停止本地联动；AR 窗口可单独关闭。
- 程序仅监听本机 `127.0.0.1`；默认端口 8765，被占用时自动选空闲端口。AR 资源已打包，不依赖在线网站。
- Edge/Chrome 为此演示使用单独的本机浏览器资料目录 `%LOCALAPPDATA%/EchoMind EEG Demo`。
- 原 TGAM EEG Monitor、原桌面离线 AR HTML、已发布网站均未覆盖。这是两者的专门联动副本。

## 源码与验证

`launch_demo.py`：双窗口启动；`monitor_demo.py`：独立监测窗口；`demo_engine.py`：共同的模拟状态；`demo_server.py`：本机通信；`web/src/`：基于原网页的联动版本。

源码启动：`python launch_demo.py`（要求 Python 自带 Tkinter，已附 `web/dist`）。

检查：`python -m unittest discover -s tests -v` 和 `node --test tests/*.test.mjs`。

修改网页后，在 `web` 目录运行 Vite build。重新打包：安装 PyInstaller 后，在本目录执行 `python -m PyInstaller --noconfirm EchoMind_EEG_AR_Demo.spec`。

## Mouse-linked eye demo

The separate EchoMind Eye Demo can follow this AR window's mouse position. When its linked-demo mode is connected, the AR page shows a green gaze ring at the exact mouse position and a **MOUSE-LINKED DEMO** label. These positions are simulated by the mouse; they are not camera measurements. The overlay does not intercept clicks or reserve layout space. Leaving the page hides it, and closing the eye demo removes it after its connection expires.

The local endpoint is `GET /api/pointer?viewer=eye-demo`. It returns normalized viewport coordinates (`x`, `y`), `active`, `seq`, `age_ms`, `consumer_connected`, `simulated: true`, and `source: "mouse"`. Read it continuously in linked mode only; the viewer connection expires after one second. The page sends position updates at up to 25 Hz and stationary heartbeats every 0.5 seconds; positions expire after 1.5 seconds without a heartbeat. Pointer transport is independent of EEG attention and cannot confirm an intent.
