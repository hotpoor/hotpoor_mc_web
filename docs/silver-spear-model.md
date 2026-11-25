# 亮银枪 Tripo3D 模型

## Key 记录与国内接口

凭据探测：`TRIPO_API_KEY=SET`。本项目这把枪使用的是 **Tripo 国内站 Key（CN）**。
凭据仅放在本机 `/Users/xialiwei/.codex/credentials/tripo.env`，已加国内站文字注释和以下非敏感配置：

```
TRIPO_REGION=cn
TRIPO_BASE_URL=https://openapi.tripo3d.com/v3
```

国内 Key 应调用国内 `.com` 域名。不能因国际站 `.ai` 返回401就判断Key失效。
本次已用国内 `/v3/account/balance` 验证成功，密钥本身未修改，也未写入仓库或客户端。

官方资料：

- https://developers.tripo3d.com/zh/docs/introduction
- https://developers.tripo3d.com/zh/docs/files
- https://developers.tripo3d.com/zh/docs/generation-image-to-model/standard
- https://developers.tripo3d.com/zh/docs/task-query

## 生成流水线

GPT生成单枪参考图 `assets/concepts/silver_spear.png` → 国内 `POST /v3/files` 上传 →
`POST /v3/generation/image-to-model` → `GET /v3/tasks/{task_id}` 轮询 → 成功后立即下载GLB和预览图。
任务与参数见 `assets/concepts/silver_spear.tripo.json`，模型清单见 `static/models/weapons/manifest.json`。

使用 v3.1-20260211、detailed几何和贴图、PBR、align_image、smart_low_poly、10000面限制。
游戏版贴图压缩至最大1024像素，保留PBR法线。武器为静态模型，无需绑骨或模型动画；挥击仍由游戏驱动。

## 集成与验证

共用现有GLTFLoader缓存与不可变几何、贴图，第一/第三人称、拾取物和近处赵云调用同一GLB。
保留方块模型作为加载中/加载失败时的后备；NPC仍按现有距离策略延迟加载，不额外给远处部队加载高精度模型。
伤害、合成、冷却和使用次数保持v59规则。

参考检查表已读：threejs-3d-generator的 api-notes、threejs-integration、image-generator-workflows；imagegen SKILL。
国内v3端点以当日官方文档为准，技能中旧国际v2端点不适用于此Key。

## 完成记录

- 任务ID：`7ad8ef5f-51c1-4932-a001-2550d1adc94c`，国内接口认证成功，任务状态success，消耗70积分。
- 游戏文件：`static/models/weapons/silver_spear.glb`，11,580三角形，1网格/1材质/3贴图，无动画。
- 请求面数上限10000，供应商实际输出11580三角形；保持在本项目武器的轻量面数级别。
- 原始文件10,518,664字节，游戏版2,004,060字节，3张贴图均1024×1024。
- 浏览器验证GLB请求200、第一/第三人称持有、合成与挥击消耗次数，零脚本或模型加载异常。
- 模型独立展示单次绘制调用、11580三角形，贴图和几何由实例共享。
- `python silver_spear_test.py`通过，基础伤害65保持不变。

按用户反馈抬高亮银枪握持：第一人称整只持枪手臂上提0.26，第三人称上提0.12，武器继续与手相连，切换其他武器恢复原位置。
