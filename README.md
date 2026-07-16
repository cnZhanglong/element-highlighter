# element_highlighter

影刀 RPA 元素高亮标注工具。

在调试 RPA 流程时，把网页上抓取到的元素用彩色方框实时标出来，确认选择器是否抓对、流程跑到哪一步。

## 特性

- **不侵入页面**：浮层 div（`position:fixed` + `pointer-events:none`），不修改目标元素
- **滚动跟随**：方框绑定到真实元素，页面或容器滚动时实时贴着元素移动
- **先画新再淡旧**：新方框先出现，旧方框随后渐隐退出
- **布局容错**：`getBoundingClientRect` 返回 0×0 时自动重试三次（16ms → 60ms → 120ms）
- **随机配色**：每次标注用高饱和随机色，区分不同批次
- **自动标注**：流程开头调 `enable()`，hook 影刀指令，自动标注返回的元素

## 安装

无需手动下载。在流程第一个「执行 Python 代码」指令里粘贴以下代码，会自动检测并下载 `element_highlighter.py` 到 `xbot_extensions` 目录：

```python
import os, sys

# 找 xbot_extensions 目录
ext_dir = None
for p in sys.path:
    c = os.path.join(p, "xbot_extensions")
    if os.path.isdir(c):
        ext_dir = c
        break

if ext_dir and ext_dir not in sys.path:
    sys.path.insert(0, ext_dir)

target = os.path.join(ext_dir or ".", "element_highlighter.py")

# 不存在就下载（容错：下载失败也不影响流程）
if not os.path.exists(target):
    try:
        import urllib.request
        urls = [
            "https://raw.githubusercontent.com/cnZhanglong/element-highlighter/main/element_highlighter.py",
            "https://ghproxy.com/https://raw.githubusercontent.com/cnZhanglong/element-highlighter/main/element_highlighter.py",
        ]
        for u in urls:
            try:
                urllib.request.urlretrieve(u, target)
                break
            except Exception:
                continue
    except Exception:
        pass

# 尝试启用自动标注（文件不存在或 import 失败都不影响流程）
try:
    from element_highlighter import enable
    enable()
except Exception:
    pass
```

> 代码已内置双地址容错：先试 GitHub，超时自动切 ghproxy 镜像。两个都连不上也不影响流程，只是没有自动标注。

## 用法

### 方式一：自动标注（推荐）

流程开头用「执行 Python 代码」指令粘贴上面的安装代码即可，之后所有返回元素的指令都会自动标注：

```
获取已打开的网页对象 → 自动捕获 web_page
获取元素对象(web)    → 自动标注
获取相似元素列表(web) → 自动标注
获取关联元素(web)    → 自动标注
点击元素(web)        → 执行前自动标注
填写输入框(web)      → 执行前自动标注
XPath跨域指令       → 自动标注
```

不想标注了：
```python
from element_highlighter import disable
disable()
```

自定义标注时长：
```python
enable(duration=5, fade=1)   # 保持5秒，渐隐1秒
```

### 方式二：手动标注

```python
from element_highlighter import mark, clear_all

mark(web_browser, elems)          # 标出一组元素
mark(web_browser, one_elem)       # 标出单个元素
mark(web_browser, elems, duration=5, fade=1)
clear_all(web_browser)            # 立即清除所有方框
```

## API

### `enable(web_page=None, duration=3.0, fade=0.6)`

流程开头调一次，hook 影刀指令，自动标注返回的元素。

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `web_page` | WebBrowser | `None` | 网页对象，不传则自动从指令返回值捕获 |
| `duration` | float | `3.0` | 方框保持显示秒数 |
| `fade` | float | `0.6` | 渐隐动画秒数 |

Hook 三个入口：
- `xbot_visual.process.run` — XPath 跨域指令（执行前用 xpath 先找元素标注；获取元素信息/属性额外执行后再标一次）
- `xbot_visual.web.element` 下的 `get_element` / `get_all_elements` / `get_associated_elements` — 系统自带获取类指令（执行前用 selector 先找元素标注 + 执行后用返回值兜底再标一次）
- `xbot_visual.web.element` 下的操作类指令 — 执行前标注 `element` 参数

多网页切换时自动从指令参数动态获取当前 `browser`。

### `disable()`

关闭自动标注，恢复原始函数。

### `mark(web_browser, elements, duration=3.0, fade=0.6)`

手动标出一个或一组元素。

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `web_browser` | WebBrowser | — | 网页对象 |
| `elements` | WebElement 或 list | — | 单个元素或元素列表 |
| `duration` | float | `3.0` | 保持秒数 |
| `fade` | float | `0.6` | 渐隐秒数 |

### `clear_all(web_browser=None, anchor=None)`

立即清除页面上所有高亮方框。

### `main(web_page, web_elements, duration=3.0, fade=0.6)`

影刀「调用模块」入口。

## 自动标注覆盖的指令

### 系统自带 — 获取类（执行前 + 执行后双保险）

执行前用 selector 先找元素标注，执行后用返回值兜底再标一次。

| 指令 | hook 入口 | 标注时机 |
|------|-----------|---------|
| 获取元素对象(web) | `web.element.get_element` | 执行前 + 执行后 |
| 获取相似元素列表(web) | `web.element.get_all_elements` | 执行前 + 执行后 |
| 获取关联元素(web) | `web.element.get_associated_elements` | 执行前 + 执行后 |

### 系统自带 — 操作类（执行前标注 element 参数）

支持 WebElement 和 Selector 两种参数类型（Selector 会自动用 `browser.find()` 解析）。

| 指令 | hook 入口 | 标注时机 |
|------|-----------|---------|
| 点击元素(web) | `web.element.click` | 执行前 |
| 填写输入框(web) | `web.element.input` | 执行前 |
| 填写密码框(web) | `web.element.input_password` | 执行前 |
| 设置下拉框(web) | `web.element.select` | 执行前 |
| 设置复选框(web) | `web.element.check` | 执行前 |
| 设置元素值(web) | `web.element.set_value` | 执行前 |
| 设置元素属性(web) | `web.element.set_attribute` | 执行前 |
| 悬停元素(web) | `web.element.hover` | 执行前 |
| 拖拽元素(web) | `web.element.drag_to` | 执行前 |
| 等待元素(web) | `web.element.wait` | 执行前 + 执行后兜底 |
| 获取元素信息(web) | `web.element.get_details` | 执行前 |
| 获取元素位置(web) | `web.element.get_bounding` | 执行前 |
| 元素截图(web) | `web.element.screenshot` | 执行前 |
| 上传文件(web) | `web.element.upload` | 执行前 |
| 下载文件(web) | `web.element.download` | 执行前 |

### XPath 跨域 — 获取类（执行前 + 执行后双保险）

执行前用 xpath 先找元素标注，执行后用 xpath 再标一次。

| 指令 | hook 入口 | 标注时机 |
|------|-----------|---------|
| 获取元素对象-XPath跨域 | `process.run` | 执行前 + 执行后 |
| 获取相似元素列表-XPath跨域 | `process.run` | 执行前 + 执行后 |

### XPath 跨域 — 操作类（执行前用 xpath 先找元素标注）

| 指令 | hook 入口 | 标注时机 |
|------|-----------|---------|
| 点击元素-XPath跨域 | `process.run` | 执行前 |
| 填写输入框-XPath跨域 | `process.run` | 执行前 |
| 等待元素-XPath跨域 | `process.run` | 执行前 |
| 获取元素信息-XPath跨域 | `process.run` | 执行前 + 执行后 |
| 获取元素属性-XPath跨域 | `process.run` | 执行前 + 执行后 |

## 技术细节

- **浮层架构**：往 `document.body` 注入 `position:fixed; pointer-events:none; z-index:2147483647` 的容器，方框是其中的子 div
- **坐标获取**：`getBoundingClientRect()`（视口坐标）+ `position:fixed`，滚动时由 scroll 事件实时更新
- **渐隐**：Web Animations API（`element.animate()`），不依赖 CSS transition
- **防闭包**：旧框渐隐的 `onfinish` 用 IIFE 锁定每次迭代的元素引用
- **自毁定时器**：每个方框 `setTimeout(duration)` 自毁，被新标注取代时 `clearTimeout` 取消
- **Hook 机制**：`enable()` 同时 patch `xbot_visual.process.run` 和 `xbot_visual.web.element` 下的函数；`disable()` 恢复
- **双保险标注**：所有指令统一执行前先找元素标注；获取类指令（获取元素对象/相似元素列表/元素信息/属性）额外执行后再标一次兜底
- **Selector 支持**：系统自带指令的 `element` 参数可能是 Selector 对象（不是 WebElement），用 `browser.find(selector)` 自动解析后再标注
- **跨域指令参数兼容**：`iframe_instance` / `iframe对象` / `IFrame对象` 三种参数名，`xpath` / `Xpath` / `XPath` 三种大小写都兼容

## 配色

每次标注用高饱和随机色（HSL 65-90% 饱和度、45-60% 亮度），区分不同批次。

## 依赖

- 影刀 xbot 的 `WebBrowser` / `WebElement`（`ChromiumElement`），元素需支持 `execute_javascript`
- Python 3.7+
