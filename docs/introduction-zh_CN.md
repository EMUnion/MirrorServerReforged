# MirrorServerReforged

![MirrorServerReforged](https://socialify.git.ci/EMUnion/MirrorServerReforged/image?description=1&font=Inter&forks=1&issues=1&language=1&owner=1&pattern=Circuit%20Board&stargazers=1&theme=Light)

适用于MCDR 2.0+的镜像服插件，主要是有时间摸了，而且自己服务器确实需要这个东西，就写了XD

简单说一下这个插件吧~

## 初次运行

本插件在初次运行的时候会进行一定的初始化，进行的操作如下（文件夹路径可以在配置文件中进行修改）
- 在config文件夹内创建`MirrorServerReforged.json`配置文件并自动填入初始配置
- 创建`Mirror`文件夹以用于存放镜像服文件
- 在`Mirror`文件夹下创建`./server/world/`/`./world`（取决于你是否使用MCDR，默认为使用）

但这些是仅仅不够的，你还需要做以下的操作：（路径可以在配置文件中进行修改）
- 将你的服务器核心以及各种服务器依赖放入`./Mirror/server`内
- 修改你的`./Mirror/`的`config.yml`中的启动命令以及rcon相关信息
- 修改你的`./Mirror/server/server.properties`的内容，特别是要注意端口以及rcon相关内容，避免与主服务器冲突

当然，镜像服务器不一定要使用MCDR，你也可以直接配置一个正常的服务器

## 配置文件

如果需要修改插件配置，只需要修改`config`文件夹下的`MirrorServerReforged.json`即可！

```json
{
  "world":[
    "world"
  ],
  "command":"python3 -m mcdreforged",
  "rcon":{
    "enable":false,
    "host":"localhost",
    "port":25565,
    "password":"password"
  },
  "source": "./server",
  "target': './Mirror/server"
}
```

配置文件的内容说明如下：
- `world`世界列表，对于`Vanilla`类型的服务器可以不用动，但是对于`Bukkit`/`Waterfall`/`Catserver`之类的客户端，它的世界文件夹有多个，则需要逐个填入，例如`world_nether`和`world_the_end`，加上原有的`world`，就应该改成`['world','world_nether','world_the_end']`
- `command` 启动命令，对于默认的启动命令，则是在认为您使用了MCDReforged的情况下填写的，但如果是使用上面说的纯`Vanilla`或者类`Bukkit`服务端，则需要进行修改，例如改成`java -Xmx16G -Xms1G -jar server.jar nogui`
- `rcon`是rcon功能的详细配置，该功能只会被用于远程关闭服务器
    - `enable`是rcon功能的总开关，表示您是否要启用本插件的rcon来进行远程服务器的关闭，参考值为`true`和`false`，当设定为`false`时，`!!msr stop`命令将不可用
    - `host`是rcon功能的宿服务器地址，根据自身需求填写即可
    - `port`是rcon功能的宿服务器端口，根据自身需求填写即可
    - `password`是rcon功能的宿服务器的密码，根据自身需求填写即可
- `source`是你的主服务器的存档位置
- `target`是你镜像服的存档位置
- `check`是镜像服启动/关闭检测的相关参数（等待超时、检测间隔等），一般无需修改
- `idle_shutdown`是镜像服闲置自动关闭的相关参数，默认关闭
    - `enable`是闲置自动关闭的总开关，设定为`true`后镜像服会在长时间无人游玩时自动关闭（需要开启`rcon`）
    - `idle_timeout`是镜像服无人游玩多久后自动关闭，单位为秒，例如`1800`表示半小时
    - `notice_advance`是关闭前多久发出提醒，单位为秒，例如`300`表示提前5分钟
    - `countdown`是关闭前逐秒广播倒计时的秒数，默认为`10`
    - `check_interval`是距离关闭还很远时的在线人数检测间隔，单位为秒，默认为`300`（即5分钟）
    - `near_check_interval`是发出提醒后、关闭临近时的检测间隔，单位为秒，默认为`10`

## 命令列表

```
!!msr help - 显示帮助信息
!!msr sync - 同步服务器地图至镜像
!!msr reload - 重载配置文件
!!msr start - 启动镜像服务器
!!msr stop - 关闭镜像服务器（需要开启Rcon）
!!msr init - 初始化镜像服务器（仅MCDR类服务器可用）
!!msr status - 查看镜像服务器状态
```

执行`!!msr start`后，插件会在镜像服务器启动完成时广播提示；执行`!!msr stop`后，则会在镜像服务器彻底关闭后向发起指令的玩家发送提示。

开启`idle_shutdown`后，镜像服闲置超过`idle_timeout`会被自动关闭：提前`notice_advance`广播一次提醒，最后`countdown`秒逐秒广播倒计时，彻底关闭后再广播一次。在线人数的检测间隔是自适应的：距离关闭还很远时按`check_interval`粗查，发出提醒后按`near_check_interval`密查，倒数期间每秒确认一次；若倒数期间有玩家加入镜像服，本次倒计时会中止，并向主服务器与镜像服务器各广播一次提示，镜像服继续运行，等到再次闲置才会重新开始计时。
