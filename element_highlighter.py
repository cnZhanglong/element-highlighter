# -*- coding: utf-8 -*-
"""
element_highlighter.py — 影刀 RPA 元素高亮标注工具
==============================================
浮层 div，不侵入页面。getBoundingClientRect 拿视口坐标（position:fixed 需要），
带重试机制防布局未完成。

时序：标旧 → 画新 → 淡旧。

调用：
    from element_highlighter import mark, clear_all
    mark(web_browser, elems)
    mark(web_browser, one_elem)
    mark(web_browser, elems, duration=5, fade=1)
"""

import json
import random

# 版本标记：random-color-test（临时测试随机配色，确认效果后改回固定色）
GROUP_COLOR = "#17A0AD"
SINGLE_COLOR = "#2D9CDB"


def _random_color():
    """生成高饱和随机 hex 色（避开太暗/太浅）。"""
    h = random.randint(0, 359)
    s = random.randint(65, 90)
    l = random.randint(45, 60)
    import colorsys
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
    color = _random_color()  # 测试用随机色，确认效果后改回 SINGLE/GROUP_COLOR

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


if __name__ == "__main__":
    print("element_highlighter: mark() / main() 调用。")
