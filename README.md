# element_highlighter

影刀 RPA 元素高亮标注工具。

在调试 RPA 流程时，把网页上抓取到的元素用彩色方框实时标出来，确认选择器是否抓对、流程跑到哪一步。

## 特性

- **不侵入页面**：仅在页面上叠加浮层 div（`position:fixed` + `pointer-events:none`），不修改目标元素任何属性
- **滚动跟随**：方框绑定到真实元素，页面或容器滚动时实时贴着元素移动
- **先画新再淡旧**：连续标注时新方框先出现，旧方框随后平滑渐隐退出，无瞬断
- **布局容错**：`getBoundingClientRect` 返回 0×0 时自动重试三次（16ms → 60ms → 120ms），避免刚触发的元素还没完成布局就被跳过
- **自动配色**：单元素和一组元素自动取不同默认色，也支持随机配色

## 安装

把 `element_highlighter.py` 放到影刀项目的 `xbot_extensions` 目录下（或任意可 import 的路径）。

## 快速开始

```python
from element_highlighter import mark, clear_all

# 标出一组元素（多个）
mark(web_browser, elems)

# 标出单个元素
mark(web_browser, one_elem)

# 自定义保持时长和渐隐时长
mark(web_browser, elems, duration=5, fade=1)
```

## API

### `mark(web_browser, elements, duration=3.0, fade=0.6)`

标出一个或一组元素。自动判断单/组。

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `web_browser` | WebBrowser | — | 影刀网页对象（用于初始化注入） |
| `elements` | WebElement 或 list | — | 单个元素或元素列表 |
| `duration` | float | `3.0` | 方框保持显示的秒数，之后开始渐隐 |
| `fade` | float | `0.6` | 渐隐动画时长（秒） |

**时序**：① 淡旧框（`animate` 渐隐，清空追踪数组）→ ② 画新框（`getBoundingClientRect` + 重试）。新框瞬间出现，旧框在其身后渐隐退出。

### `clear_all(web_browser=None, anchor=None)`

立即清除页面上所有高亮方框。

```python
clear_all(web_browser)
```

### `main(web_page, web_elements, duration=3.0, fade=0.6)`

影刀"调用模块"入口，参数与 `mark` 一致。

## 在影刀流程中使用

### 方式一：Python 脚本中 import

```python
from element_highlighter import mark

# 获取元素后立即标注
elems = web_page.find_all_by_xpath("//div[@class='item']")
mark(web_page, elems)
```

### 方式二：影刀"调用模块"

在影刀流程中添加"调用 Python 模块"指令：

- 模块文件：`element_highlighter.py`
- 函数名：`main`
- 参数：
  - `web_page`：网页对象变量
  - `web_elements`：元素对象或元素列表变量
  - `duration`：保持秒数（可选，默认 3）
  - `fade`：渐隐秒数（可选，默认 0.6）

## 连续标注效果

在 RPA 流程中连续调用 `mark()`，每次新方框出现时旧方框会平滑淡出：

```
mark(browser, elems_A)   # 画 A 组方框
# ... RPA 操作 ...
mark(browser, elems_B)   # B 组出现，A 组渐隐淡出
# ... RPA 操作 ...
mark(browser, elems_C)   # C 组出现，B 组渐隐淡出
```

屏幕上始终只有"当前这组"方框，不会越堆越多。

## 技术细节

- **浮层架构**：往 `document.body` 注入一个 `position:fixed; pointer-events:none; z-index:2147483647` 的容器 div，每个方框是其中的子 div
- **坐标获取**：用 `getBoundingClientRect()`（视口坐标）配合 `position:fixed`，滚动时由 scroll 事件监听器实时更新位置
- **渐隐机制**：Web Animations API（`element.animate()`），不依赖 CSS transition
- **防闭包 bug**：旧框渐隐的 `onfinish` 回调用 IIFE 锁定每次迭代的元素引用
- **自毁定时器**：每个方框创建时设 `setTimeout(duration秒)` 自毁，被新 mark 调用取代时 `clearTimeout` 取消

## 默认配色

| 场景 | 颜色 | 色值 |
|------|------|------|
| 一组元素 | 蓝绿 | `#17A0AD` |
| 单个元素 | 蓝 | `#2D9CDB` |

> 当前版本（`random-color-test`）使用随机高饱和配色用于测试，确认效果后改回固定色即可。

## 依赖

- 影刀 xbot 的 `WebBrowser` / `WebElement`（`ChromiumElement`），元素需支持 `execute_javascript`
- Python 3.7+
