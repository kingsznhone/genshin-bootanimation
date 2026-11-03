import { useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  CssBaseline,
  Snackbar,
  Stack,
  Switch,
  ThemeProvider,
  Typography,
  createTheme,
  useMediaQuery,
} from '@mui/material';
import { exec } from 'kernelsu';

const CONF = '/data/adb/genshin_bootanim/config.conf';
const DST = '/data/system/theme/boots/bootaudio.mp3';
// 构建时 build.py 会把 __ID__ 替换成真实模块 id
const SRC = '/data/adb/modules/__ID__/files/bootaudio.mp3';

type Result = { errno?: number; stdout?: string; stderr?: string };

async function sh(cmd: string): Promise<Result> {
  try {
    return (await exec(cmd)) as Result;
  } catch (e) {
    return { errno: -1, stdout: '', stderr: String(e) };
  }
}

export default function App() {
  const dark = useMediaQuery('(prefers-color-scheme: dark)');
  const theme = createTheme({ palette: { mode: dark ? 'dark' : 'light' } });

  const [muted, setMuted] = useState(false);
  const [busy, setBusy] = useState(true);
  const [status, setStatus] = useState('读取配置…');
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    sh(`cat ${CONF} 2>/dev/null`).then((r) => {
      const out = r.stdout ?? '';
      const isMuted = /^SILENT=1$/m.test(out);
      setMuted(isMuted);
      setStatus(out.trim() ? (isMuted ? '当前：静音' : '当前：有开机音') : '当前：默认（有开机音）');
      setBusy(false);
    });
  }, []);

  async function save(next: boolean) {
    setBusy(true);
    // 总开关是系统属性：AOSP 看 play_sound，MIUI 看 boot_audio.enabled
    const apply = next
      ? 'setprop persist.sys.bootanim.play_sound 0; setprop persist.sys.boot_audio.enabled 0'
      : `mkdir -p /data/system/theme/boots; cp -f ${SRC} ${DST}; chmod 644 ${DST}; `
        + 'setprop persist.sys.bootanim.play_sound 1; setprop persist.sys.boot_audio.enabled 1';
    const res = await sh(
      `mkdir -p /data/adb/genshin_bootanim && echo SILENT=${next ? 1 : 0} > ${CONF} && ${apply}`,
    );
    const check = await sh(`cat ${CONF} 2>/dev/null`);
    const ok = (check.stdout ?? '').trim() === `SILENT=${next ? 1 : 0}`;
    setBusy(false);
    if (ok) {
      setMuted(next);
      setStatus(next ? '当前：静音' : '当前：有开机音');
      setToast(next ? '已保存：静音' : '已保存：有开机音');
    } else {
      setStatus('保存失败');
      setToast(`保存失败（errno=${res.errno ?? '?'}）${(res.stderr ?? '').slice(0, 120)}`);
    }
  }

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box sx={{ p: 2, pb: 4 }}>
        <Typography variant="h6" gutterBottom>
          原神开机动画
        </Typography>

        <Card variant="outlined">
          <CardContent>
            <Stack
              direction="row"
              spacing={2}
              sx={{ alignItems: 'center', justifyContent: 'space-between' }}
            >
              <Box>
                <Typography>开机音</Typography>
                <Typography variant="body2" color="text.secondary">
                  {status}
                </Typography>
              </Box>
              <Switch
                checked={!muted}
                disabled={busy}
                onChange={(_, on) => save(!on)}
                slotProps={{ input: { 'aria-label': '开机音' } }}
              />
            </Stack>

            <Button
              fullWidth
              sx={{ mt: 2 }}
              variant="contained"
              disabled={busy}
              onClick={() => save(muted)}
              startIcon={busy ? <CircularProgress size={16} color="inherit" /> : undefined}
            >
              保存并应用
            </Button>
          </CardContent>
        </Card>
      </Box>

      <Snackbar
        open={toast !== null}
        autoHideDuration={2500}
        onClose={() => setToast(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert severity={toast?.startsWith('保存失败') ? 'error' : 'success'} variant="filled">
          {toast}
        </Alert>
      </Snackbar>
    </ThemeProvider>
  );
}
