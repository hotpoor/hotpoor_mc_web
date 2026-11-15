# 方块战场 · MC Web

浏览器多人方块对抗游戏。使用 Three.js 渲染场景，Tornado 和 WebSocket 同步对局，SQLite 保存排行和战报。

## 运行

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python server.py --port=8888
```

浏览器打开 http://localhost:8888。局域网玩家可以通过服务器的局域网 IP 加端口加入。

## 操作

- `WASD` 移动，`Shift` 冲刺，空格跳跃，`V` 切换视角。
- `1` 剑，`2` 弓，`3` 龟派气功，`4` 火箭筒，`5` 连射枪，`6` 斧子，`7` 狼牙棒，`8` 重锤。
- 左键使用当前武器。弓与龟派气功按住左键蓄力，松手释放。
- `Q` 气功波，`H` 原地引导回城，`Enter` 聊天。

打碎敌方水晶会暂停其基地回血 30 秒。攻击场地炸弹可将其引爆。

## 测试

```sh
python smoke_test.py
```

测试使用临时数据库，并启动两个 WebSocket 客户端验证联机。

内置 Three.js r160 采用 MIT 许可证，许可文本见 [Three.js LICENSE](static/vendor/THREE-LICENSE.txt)。

## 云端部署

线上入口为 https://api.xialiwei.com/hotpoor/mc-web/ 。反向代理剥离
`/hotpoor/mc-web/` 前缀，并在同前缀下转发 WebSocket `ws`。
安装 `psycopg[binary]` 并在服务端设置 `MC_DATABASE_URL` 可使用 PostgreSQL。
未设置时默认使用本机 SQLite。
