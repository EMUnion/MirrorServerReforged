# MirrorServerReforged

![MirrorServerReforged](https://socialify.git.ci/EMUnion/MirrorServerReforged/image?description=1&font=Inter&forks=1&issues=1&language=1&owner=1&pattern=Circuit%20Board&stargazers=1&theme=Light)

适用于MCDR 2.0+的镜像服插件，主要是有时间摸了，而且自己服务器确实需要这个东西，就写了XD

简单说一下这个插件吧~

## 初次运行

本插件在初次运行的时候会进行一定的初始化，进行的操作如下
- 在config文件夹内创建`MirrorServerReforged.json`配置文件并自动填入初始配置
- 创建`Mirror`文件夹以用于存放镜像服文件
- 在`Mirror`文件夹下创建`./server/world/`/`./world`（取决于你是否使用MCDR，默认为使用）

但这些是仅仅不够的，你还需要做以下的操作：
- 将你的服务器核心以及各种服务器依赖放入`./Mirror/server`内
- 修改你的`./Mirror/`的`config.yml`中的启动命令以及rcon相关信息
- 修改你的`./Mirror/server/server.properties`的内容，特别是要注意端口以及rcon相关内容，避免与主服务器冲突

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
  }
}
```

配置文件的内容说明如下：
- `world`世界列表，对于`Vanilla`类型的服务器可以不用动，但是对于`Bukkit`/`Waterfall`/`Catserver`之类的客户端，它的世界文件夹有多个，则需要诸葛填入，例如`world_nether`和`world_the_end`
- `command` 启动命令，对于默认的启动命令，则是在认为您使用了MCDReforged的情况下填写的，但如果是使用上面说的纯`Vanilla`或者类`Bukkit`客户端，则需要进行修改，例如改成`java -Xmx16G -Xms1G -jar server.jar nogui`
- `rcon`是rcon功能的详细配置，该功能只会被用于远程关闭服务器
    - `enable`是rcon功能的总开关，表示您是否要启用本插件的rcon来进行远程服务器的关闭，参考值为`true`和`false`，当设定为`false`时，`!!msr stop`命令将不可用
    - `host`是rcon功能的宿服务器地址，根据自身需求填写即可
    - `port`是rcon功能的宿服务器端口，根据自身需求填写即可
    - `password`是rcon功能的宿服务器的密码，根据自身需求填写即可

## 命令列表

```
!!msr help - §6显示帮助信息
!!msr sync - §6同步服务器地图至镜像
!!msr reload - §6重载配置文件
!!msr start - §6启动镜像服务器
!!msr stop - §6关闭镜像服务器（需要开启Rcon）
!!msr init - §6初始化镜像服务器（仅MCDR类服务器可用）
!!msr status - §6查看镜像服务器状态
```