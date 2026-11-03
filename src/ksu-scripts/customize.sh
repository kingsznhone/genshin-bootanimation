#!/system/bin/sh
ui_print "- 原神开机动画"
ui_print "- 重启后生效"

if command -v wm >/dev/null 2>&1; then
    REAL="$(wm size 2>/dev/null | tail -n 1 | sed 's/.*: *//')"
    if [ -n "$REAL" ] && [ "$REAL" != "__SIZE__" ]; then
        ui_print "! 当前设备 $REAL，与本模块 __SIZE__ 不一致，画面会被裁切或留边"
    fi
fi
