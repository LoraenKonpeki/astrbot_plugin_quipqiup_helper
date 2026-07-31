# astrbot_plugin_quipqiup_helper

通过 [quipqiup](https://www.quipqiup.com/) 求解英文单表替换密码的 AstrBot 插件。

## 用法

```text
/quip GSRH RH Z HVXIVG
/quip GSRH RH Z HVXIVG --clues G=T
```

`--clues` 可选；格式为 `密文字母=明文字母`，多条映射以空格分隔。

插件依赖 quipqiup 的公开网页接口，需要服务器能访问 `https://www.quipqiup.com`。
