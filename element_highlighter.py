# -*- coding: utf-8 -*-
"""
element_highlighter.py — 影刀 RPA 元素高亮标注工具
==============================================
调试 RPA 流程时，把元素用彩色方框实时标出来，确认选择器是否抓对、流程跑到哪一步。

特性：
- 不侵入页面：浮层 div（position:fixed, pointer-events:none），不修改目标元素。
- 滚动跟随：scroll/resize 实时贴着元素移动。
- 先画新再淡旧：新方框先出现，旧方框随后渐隐退出。
- 布局容错：getBoundingClientRect 返回 0×0 时自动重试三次（16/60/120ms）。
- 随机配色：每次标注用高饱和随机色，区分不同批次。
- 自动标注：流程开头调 enable()，hook 影刀指令，自动标注返回的元素。

两种用法：
    1. 手动标注
       from element_highlighter import mark, clear_all
       mark(web_browser, elems)
       mark(web_browser, one_elem)

    2. 自动标注（推荐）
       from element_highlighter import enable, disable
       enable()                # 流程开头调一次，自动标注所有指令返回的元素
       ... 正常写流程 ...
       disable()               # 不想标注了就关掉

依赖：影刀 xbot 的 WebBrowser / WebElement（ChromiumElement），元素需支持 execute_javascript。
"""

import json
import random
import colorsys

GROUP_COLOR = "#17A0AD"
SINGLE_COLOR = "#2D9CDB"


def _random_color():
    """生成高饱和随机 hex 色，每次标注用不同颜色区分批次。"""
    h = random.randint(0, 359)
    s = random.randint(65, 90)
    l = random.randint(45, 60)
    r, g, b = colorsys.hls_to_rgb(h / 360, l / 100, s / 100)
    return "#{:02X}{:02X}{:02X}".format(int(r * 255), int(g * 255), int(b * 255))


_INIT_JS = """(elem) => {
    if (document.getElementById('rpa_hl_style')) return;
    var s = document.createElement('style');
    s.id = 'rpa_hl_style';
    s.textContent = '#rpa_hl_layer{position:fixed;inset:0;pointer-events:none;z-index:2147483647}'
        + '.rpa-hl-box{position:fixed;box-sizing:border-box;border:2px solid;border-radius:4px}';
    (document.head||document.documentElement).appendChild(s);
    var layer = document.getElementById('rpa_hl_layer');
    if(!layer){layer=document.createElement('div');layer.id='rpa_hl_layer';(document.body||document.documentElement).appendChild(layer);}
    window._rpaBoxes = [];
    var _onScroll = function(){
        for(var i=0;i<window._rpaBoxes.length;i++){
            var b=window._rpaBoxes[i];
            if(!b._el||!b._el.getBoundingClientRect) continue;
            var r=b._el.getBoundingClientRect();
            if(r.width===0&&r.height===0) continue;
            b.style.left=r.left+'px';b.style.top=r.top+'px';
            b.style.width=Math.max(r.width,3)+'px';b.style.height=Math.max(r.height,3)+'px';
        }
    };
    window.addEventListener('scroll',_onScroll,true);
    window.addEventListener('resize',_onScroll,true);
}"""

_REVEAL_JS = """(elem, cfgJson) => {
    var c = (typeof cfgJson === 'string') ? JSON.parse(cfgJson) : cfgJson;
    _doReveal(0);
    function _doReveal(attempt){
        var r = elem.getBoundingClientRect();
        if(r.width===0&&r.height===0){
            var delays = [16, 60, 120];
            if(attempt < delays.length){
                setTimeout(function(){_doReveal(attempt+1);}, delays[attempt]);
                return;
            }
            return;  // 三次重试后仍 0×0，放弃
        }
        var box = document.createElement('div');
        box.className='rpa-hl-box';
        box.style.left=r.left+'px'; box.style.top=r.top+'px';
        box.style.width=Math.max(r.width,3)+'px'; box.style.height=Math.max(r.height,3)+'px';
        box.style.borderColor=c.color;
        box.style.background=c.bg;
        box.style.opacity='1';
        box._el=elem;
        document.getElementById('rpa_hl_layer').appendChild(box);
        window._rpaBoxes.push(box);
        box._timer = setTimeout(function(){
            box.animate([{opacity:1},{opacity:0}],{duration:(c.fade||0.6)*1000,fill:'forwards'}).onfinish=function(){
                if(box.parentNode)box.remove();
            };
            setTimeout(function(){
                var j=window._rpaBoxes.indexOf(box);if(j>=0)window._rpaBoxes.splice(j,1);
            },(c.fade||0.6)*1000+50);
        },(c.duration||3)*1000);
    }
}"""

_FADE_OLD_JS = """(elem, fadeSec) => {
    var boxes = window._rpaBoxes || [];
    window._rpaBoxes = [];
    var dur = (fadeSec||0.6)*1000;
    for(var i=0;i<boxes.length;i++){
        (function(b){
            if(b._timer){clearTimeout(b._timer);b._timer=null;}
            b.animate([{opacity:1},{opacity:0}],{duration:dur,fill:'forwards'}).onfinish=function(){
                if(b.parentNode)b.remove();
            };
        })(boxes[i]);
    }
}"""
_CLEARALL_JS = """(elem) => {
    var boxes=window._rpaBoxes||[];
    for(var i=boxes.length-1;i>=0;i--){if(boxes[i]._timer)clearTimeout(boxes[i]._timer);if(boxes[i].parentNode)boxes[i].remove();}
    window._rpaBoxes=[];
    window._rpaOldBoxes=[];
}"""


def _as_list(elements):
    if elements is None: return []
    if isinstance(elements, (list, tuple, set)): return [e for e in elements if e is not None]
    return [elements]


def _color_rgba(hex_color, alpha):
    h = hex_color.lstrip('#')
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _ensure_layer(anchor):
    try:
        anchor.execute_javascript(_INIT_JS)
    except Exception:
        pass


def mark(web_browser, elements, duration=3.0, fade=0.6):
    """标出元素。先画新框（getBoundingClientRect + 重试），再淡出旧框。

    :param elements: 单个 WebElement 或列表
    :param duration: 保持秒数（默认 3s）
    :param fade:     渐隐秒数（默认 0.6s）
    """
    elems = _as_list(elements)
    if not elems: return
    anchor = elems[0]
    _ensure_layer(anchor)
    color = _random_color()

    # 1) 淡旧框：清空 _rpaBoxes + animate 渐隐（IIFE 防闭包 bug）
    try:
        anchor.execute_javascript(_FADE_OLD_JS, fade)
    except Exception:
        pass

    # 2) 画新框
    for e in elems:
        cfg = {
            "color": color, "bg": _color_rgba(color, 0.40),
            "duration": duration, "fade": fade,
        }
        try:
            e.execute_javascript(_REVEAL_JS, json.dumps(cfg, ensure_ascii=False))
        except Exception:
            continue


def clear_all(web_browser=None, anchor=None):
    a = anchor or web_browser
    if a is not None:
        try:
            a.execute_javascript(_CLEARALL_JS)
        except Exception:
            pass


def main(web_page, web_elements, duration=3.0, fade=0.6):
    mark(web_page, web_elements, duration=duration, fade=fade)


# ---------- 自动标注：hook process.run ----------
_enabled = False
_orig_run = None


def _is_webelement(obj):
    """判断对象是不是 WebElement（ChromiumElement 等）。"""
    if obj is None:
        return False
    cls_name = type(obj).__name__
    return cls_name in ("ChromiumElement", "WebElement", "CefElement", "EdgeElement",
                        "FirefoxElement", "IEElement")


def _is_webbrowser(obj):
    """判断对象是不是 WebBrowser（ChromiumBrowser 等）。"""
    if obj is None:
        return False
    cls_name = type(obj).__name__
    return cls_name in ("ChromiumBrowser", "WebBrowser", "CefBrowser", "EdgeBrowser",
                        "FirefoxBrowser", "IEBrowser")


def _extract_elements(result):
    """从 process.run 的返回值里提取 WebElement。"""
    if _is_webelement(result):
        return [result]
    if isinstance(result, (list, tuple)):
        elems = [e for e in result if _is_webelement(e)]
        return elems if elems else []
    return []


def enable(web_page=None, duration=3.0, fade=0.6):
    """在流程开头调一次，hook process.run，自动标注所有指令返回的元素。

    web_page 可以不传——流程里第一个"获取已打开的网页对象"指令的返回值
    会被自动捕获作为 web_page。

    :param web_page: 影刀网页对象（可选，不传则自动从指令返回值获取）
    :param duration: 方框保持秒数（默认 3s）
    :param fade:     渐隐秒数（默认 0.6s）
    """
    global _enabled, _orig_run
    if _enabled:
        return
    try:
        import xbot_visual.process as _p
    except Exception:
        return
    _orig_run = _p.run
    _browser_ref = [web_page]

    def _hooked(**kw):
        # 执行前：跨域点击/填写指令从 inputs 里拿 xpath + browser，先找元素标注
        _pre_mark_cross_domain(kw, _browser_ref, duration, fade)
        result = _orig_run(**kw)
        try:
            # 每次指令动态拿当前 browser（支持多网页切换）：
            #   ① 指令参数里的 browser（最准——当前指令操作哪个网页就是哪个）
            #   ② 返回值是 WebBrowser（"获取已打开的网页对象"指令）→ 更新缓存
            #   ③ 元素自己作 anchor（兜底）
            current_browser = kw.get("browser") or _browser_ref[0]
            if _is_webbrowser(result):
                _browser_ref[0] = result
                if current_browser is None:
                    current_browser = result
            elif isinstance(result, (list, tuple)):
                for r in result:
                    if _is_webbrowser(r):
                        _browser_ref[0] = r
                        if current_browser is None:
                            current_browser = r
                        break
            # 从 inputs 里拿 iframe_instance 更新 browser 缓存
            inputs = kw.get("inputs") or {}
            if isinstance(inputs, dict):
                iframe_inst = inputs.get("iframe_instance") or inputs.get("iframe对象")
                if _is_webbrowser(iframe_inst):
                    _browser_ref[0] = iframe_inst
                    if current_browser is None:
                        current_browser = iframe_inst
            elems = _extract_elements(result)
            if elems:
                mark(current_browser or elems[0], elems, duration=duration, fade=fade)
            # 获取元素信息/属性-XPath跨域：执行后用 xpath 再找元素标注
            post = kw.pop("_rpa_post_mark", None)
            if post:
                try:
                    elem = post["browser"].find_by_xpath(post["xpath"], timeout=2)
                    if _is_webelement(elem):
                        mark(post["browser"], [elem], duration=post["duration"], fade=post["fade"])
                except Exception:
                    pass
        except Exception:
            pass
        return result

    _p.run = _hooked

    # 同时 hook xbot_visual.web.element 下的函数（系统自带指令走这条路，不走 process.run）
    _hook_web_element(duration, fade)

    _enabled = True


# 保存 web.element 的原始函数
_web_elem_origs = {}


def _resolve_and_mark(browser, elem, duration, fade):
    """把 element 参数解析成 WebElement 并标注。

    支持：WebElement 直接标；Selector 用 browser.find() 解析后标；字符串 xpath 用 find_by_xpath 找。
    """
    if elem is None:
        return
    # 已经是 WebElement
    if _is_webelement(elem):
        mark(browser or elem, [elem], duration=duration, fade=fade)
        return
    # Selector 对象：用 browser.find 解析
    if browser is not None:
        cls_name = type(elem).__name__
        if cls_name in ("Selector", "TableSelector") or isinstance(elem, str):
            try:
                resolved = browser.find(elem)
                if _is_webelement(resolved):
                    mark(browser, [resolved], duration=duration, fade=fade)
            except Exception:
                pass


def _hook_web_element(duration, fade):
    """hook xbot_visual.web.element 下的函数。"""
    try:
        import xbot_visual.web.element as _we
    except Exception:
        return
    # 返回元素的：执行后标注返回值
    _get_targets = [
        "get_element",           # 获取元素对象(web)
        "get_all_elements",      # 获取相似元素列表(web)
        "get_associated_elements",  # 获取关联元素(web)
    ]
    for name in _get_targets:
        orig = getattr(_we, name, None)
        if orig is None or name in _web_elem_origs:
            continue
        _web_elem_origs[name] = orig

        def make_wrapper(fn_name, fn):
            def wrapped(**kw):
                result = fn(**kw)
                try:
                    browser = kw.get("browser")
                    elems = _extract_elements(result)
                    if elems:
                        mark(browser or elems[0], elems, duration=duration, fade=fade)
                except Exception:
                    pass
                return result
            return wrapped

        setattr(_we, name, make_wrapper(name, orig))

    # 操作元素的：执行前标注 element 参数（element 是 WebElement 才标，selector 跳过）
    _action_targets = [
        "click",           # 点击元素(web)
        "input",           # 填写输入框(web)
        "input_password",  # 填写密码框(web)
        "select",          # 设置下拉框(web)
        "check",           # 设置复选框(web)
        "set_value",       # 设置元素值(web)
        "set_attribute",   # 设置元素属性(web)
        "hover",           # 悬停元素(web)
        "drag_to",         # 拖拽元素(web)
        "wait",            # 等待元素(web)
        "get_details",     # 获取元素信息/获取元素属性(web)
        "get_bounding",    # 获取元素位置(web)
        "screenshot",      # 元素截图(web)
        "upload",          # 上传文件(web)
        "download",        # 下载文件(web)
    ]
    for name in _action_targets:
        orig = getattr(_we, name, None)
        if orig is None or name in _web_elem_origs:
            continue
        _web_elem_origs[name] = orig

        def make_pre_wrapper(fn_name, fn):
            def wrapped(**kw):
                # 执行前标注
                try:
                    browser = kw.get("browser")
                    elem = kw.get("element")
                    _resolve_and_mark(browser, elem, duration, fade)
                except Exception:
                    pass
                result = fn(**kw)
                # wait 指令兜底：执行后元素已出现，再标一次
                if fn_name == "wait":
                    try:
                        elem = kw.get("element")
                        browser = kw.get("browser")
                        _resolve_and_mark(browser, elem, duration, fade)
                    except Exception:
                        pass
                return result
            return wrapped

        setattr(_we, name, make_pre_wrapper(name, orig))


def _pre_mark_cross_domain(kw, browser_ref, duration, fade):
    """跨域指令执行前/后，从 inputs 里拿 xpath + browser 找元素标注。

    覆盖：点击、填写、等待（执行前标）；获取元素信息/属性（执行后标，用返回值）。
    """
    try:
        process_name = kw.get("process") or ""
        # 执行前标注的：点击、填写、等待
        _pre_actions = ["click_by_xpath", "input_by_xpath", "wait_by_xpath"]
        # 执行后标注的：获取元素信息(process2) / 获取元素属性(process3)
        _post_actions = ["get_elem_info", ".process2", ".process3"]
        if not any(a in process_name for a in _pre_actions + _post_actions):
            return
        inputs = kw.get("inputs") or {}
        if not isinstance(inputs, dict):
            return
        # browser 可能在 iframe_instance 或 iframe对象 或 IFrame对象
        browser = (inputs.get("iframe_instance") or inputs.get("iframe对象")
                   or inputs.get("IFrame对象") or browser_ref[0])
        if not _is_webbrowser(browser):
            return
        # xpath 可能是 xpath / Xpath / XPath
        xpath = inputs.get("xpath") or inputs.get("Xpath") or inputs.get("XPath") or ""
        if not xpath:
            return
        # 执行前标注：点击、填写、等待
        if any(a in process_name for a in _pre_actions):
            try:
                elem = browser.find_by_xpath(xpath, timeout=2)
                if _is_webelement(elem):
                    mark(browser, [elem], duration=duration, fade=fade)
            except Exception:
                pass
        # 执行后标注：获取元素信息/属性
        if any(a in process_name for a in _post_actions):
            kw["_rpa_post_mark"] = {"browser": browser, "xpath": xpath, "duration": duration, "fade": fade}
    except Exception:
        pass


def _unhook_web_element():
    """恢复 web.element 的原始函数。"""
    try:
        import xbot_visual.web.element as _we
    except Exception:
        return
    for name, orig in _web_elem_origs.items():
        setattr(_we, name, orig)
    _web_elem_origs.clear()


def disable():
    """关闭自动标注，恢复原始 process.run 和 web.element。"""
    global _enabled, _orig_run
    if not _enabled:
        return
    try:
        import xbot_visual.process as _p
        _p.run = _orig_run
    except Exception:
        pass
    _unhook_web_element()
    _enabled = False
    _orig_run = None


if __name__ == "__main__":
    print("element_highlighter: mark() / main() / enable() 调用。")
