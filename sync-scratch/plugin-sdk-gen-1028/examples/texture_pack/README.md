# 本地纹理包示例

这是无运行时依赖的标准 Python wheel，纹理和插件代码一起安装。
`orca` 由宿主提供，不要把它写进 PyPI 依赖。

在本目录执行：

```sh
uv build --wheel --out-dir /absolute/path/to/plugin-wheels
```

首次构建会下载锁定的 setuptools 构建依赖；构建完成的 wheel 安装不需要联网。
在 Local Plugins 中安装生成的 `snapmaker_texture_example-1.0.0-py3-none-any.whl`，
启用后在纹理选择器选择 `Snapmaker example textures / height`。
附带的 2×2 灰度图只用于演示接口；替换 `textures/height.png` 即可提供自己的高度图。

不要把资源放在插件目录外：宿主验证资源归属，拒绝跨目录符号链接。
插件卸载后库中的条目消失；已复制到模型或预览快照中的图像仍由宿主持有。
Python `.py` 单文件安装不会附带同目录资源，因此本示例使用 wheel。

当前验收状态见上级 `VERIFICATION.md`；源码示例不代表三个平台均已完成发行验收。
