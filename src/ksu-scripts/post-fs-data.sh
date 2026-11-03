#!/system/bin/sh
# 开机音总开关：AOSP 的 audioplay 看 persist.sys.bootanim.play_sound，
# MIUI 的 playBackgroundMusic 看 persist.sys.boot_audio.enabled。
# 两者都是 persist 属性，卸载时要在 uninstall.sh 里还原。
# KSU 执行 post-fs-data.sh 时不设 $MODPATH，路径必须写死。
MODDIR=/data/adb/modules/__ID__
CONF=/data/adb/genshin_bootanim/config.conf
DST=/data/system/theme/boots/bootaudio.mp3
SRC="$MODDIR/files/bootaudio.mp3"

MUTE=0
if [ -f "$CONF" ] && grep -q '^SILENT=1$' "$CONF"; then
    MUTE=1
fi

if [ "$MUTE" = "1" ]; then
    setprop persist.sys.bootanim.play_sound 0
    setprop persist.sys.boot_audio.enabled 0
else
    setprop persist.sys.bootanim.play_sound 1
    setprop persist.sys.boot_audio.enabled 1
    if [ -f "$SRC" ]; then
        mkdir -p "${DST%/*}"
        cp -f "$SRC" "$DST"
        chmod 644 "$DST"
        chown 0:0 "$DST" 2>/dev/null
        restorecon "$DST" 2>/dev/null
    fi
fi
