#!/system/bin/sh
ui_print "- 原神开机动画"

# KernelSU 3.x 起自己不做挂载，模块的 system/ 要靠 metamodule 挂上去；
# 本模块还要求它能把 system/media 落到 /product/media（/system/media 是软链），
# 实测只有 Hybrid Mount 的 magic mount 能跟过去。没有 metamodule 或它被禁用就硬拦；
# 别的实现只是可能覆盖不到，软提示放行。
# 注：KSU-Next 这类自带挂载的 fork 没有 /data/adb/metamodule，要装的话删掉前面两个 abort。
META=/data/adb/metamodule
# -d 而不是 -e：软链断了（目标被删）也算没有
if [ ! -d "$META" ]; then
    ui_print "! 未检测到 metamodule（KernelSU 3.x 靠它挂载 system/）"
    # abort 之后补 exit：万一某些 fork 没提供 abort，也不能放过去
    abort "! 先装 Hybrid Mount，再装本模块"
    exit 1
fi
if [ -f "$META/disable" ]; then
    abort "! metamodule 被禁用了，在 KernelSU 管理器里启用它再装"
    exit 1
fi

if [ -x "$META/hybrid-mount" ] || [ -d /data/adb/modules/hybrid_mount ] \
    || grep -qi 'hybrid' "$META/module.prop" 2>/dev/null; then
    ui_print "- 挂载后端：Hybrid Mount"
else
    BACKEND="$(sed -n 's/^name=//p' "$META/module.prop" 2>/dev/null | head -n 1)"
    ui_print "! 挂载后端：${BACKEND:-未识别}，可能覆盖不到 /product/media"
    ui_print "! 先装来试，没效果就换 Hybrid Mount"
fi

if command -v wm >/dev/null 2>&1; then
    REAL="$(wm size 2>/dev/null | tail -n 1 | sed 's/.*: *//')"
    if [ -n "$REAL" ] && [ "$REAL" != "__SIZE__" ]; then
        ui_print "! 当前设备 $REAL，与本模块 __SIZE__ 不一致，画面会被裁切或留边"
    fi
fi
