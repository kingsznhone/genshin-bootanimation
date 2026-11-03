#!/system/bin/sh
# 模块没了就别继续压着系统开关
setprop persist.sys.bootanim.play_sound 1
setprop persist.sys.boot_audio.enabled 1

# 只删我们自己放过去的那份，别误删用户的主题铃声
DST=/data/system/theme/boots/bootaudio.mp3
if [ -f "$DST" ] && [ "$(md5sum "$DST" 2>/dev/null | cut -d' ' -f1)" = "__MD5__" ]; then
    rm -f "$DST"
fi
