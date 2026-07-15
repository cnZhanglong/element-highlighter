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

把 `element_highlighter.py` 放到影刀项目的 `xbot_extensions` 目录下（或任意可 import 的路径）。

## 用法

### 方式一：自动标注（推荐）

流程开头调一次 `enable()`，之后所有返回元素的指令都会自动标注：

```python
from element_highlighter import enable
enable()          # web_page 不用传，自动从指令捕获

# 之后正常拖可视化指令，元素自动标注：
# 获取已打开的网页对象 → 自动捕获 web_page
# 获取元素对象(web)    → 自动标注
# 获取相似元素列表(web) → 自动标注
# 获取关联元素(web)    → 自动标注
# XPath跨域指令       → 自动标注
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

Hook 两个入口：
- `xbot_visual.process.run` — XPath 跨域自定义指令
- `xbot_visual.web.element` 下的 `get_element` / `get_all_elements` / `get_associated_elements` — 系统自带指令

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

| 指令 | hook 入口 |
|------|-----------|
| 获取元素对象(web) | `web.element.get_element` |
| 获取相似元素列表(web) | `web.element.get_all_elements` |
| 获取关联元素(web) | `web.element.get_associated_elements` |
| 获取元素对象-XPath跨域 | `process.run` |
| 获取相似元素列表-XPath跨域 | `process.run` |
| 点击元素-XPath跨域 | `process.run` |
| 填写输入框-XPath跨域 | `process.run` |
| 等待元素-XPath跨域 | `process.run` |
| 获取元素信息-XPath跨域 | `process.run` |
| 获取元素属性-XPath跨域 | `process.run` |

## 技术细节

- **浮层架构**：往 `document.body` 注入 `position:fixed; pointer-events:none; z-index:2147483647` 的容器，方框是其中的子 div
- **坐标获取**：`getBoundingClientRect()`（视口坐标）+ `position:fixed`，滚动时由 scroll 事件实时更新
- **渐隐**：Web Animations API（`element.animate()`），不依赖 CSS transition
- **防闭包**：旧框渐隐的 `onfinish` 用 IIFE 锁定每次迭代的元素引用
- **自毁定时器**：每个方框 `setTimeout(duration)` 自毁，被新标注取代时 `clearTimeout` 取消
- **Hook 机制**：`enable()` 同时 patch `xbot_visual.process.run` 和 `xbot_visual.web.element` 下的函数；`disable()` 恢复

## 配色

每次标注用高饱和随机色（HSL 65-90% 饱和度、45-60% 亮度），区分不同批次。

## 依赖

- 影刀 xbot 的 `WebBrowser` / `WebElement`（`ChromiumElement`），元素需支持 `execute_javascript`
- Python 3.7+
