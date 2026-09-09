"""Fixed media recipes shared by the engine and the native Mac helper.

Stdlib only. The release ships this exact file to the host; requests select a
recipe, never an executable, shell command, filter graph, or output filename.
"""
from __future__ import annotations

import math
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def number(value, minimum, maximum):
    if type(value) not in (int, float) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError('Invalid media recipe number.')
    return value


def validate_recipe(recipe):
    if not isinstance(recipe, dict):
        raise ValueError('Invalid media recipe.')
    kind = recipe.get('kind')
    fields = {'thumbnail': {'kind', 'width', 'seek'}, 'mp4': {'kind', 'height'},
              'hls': {'kind', 'variants', 'has_audio', 'gop', 'segment_seconds'}}
    if kind not in fields or set(recipe) != fields[kind]:
        raise ValueError('Unknown media recipe.')
    if kind == 'thumbnail':
        number(recipe['width'], 320, 3840)
        number(recipe['seek'], 0, 7 * 86400)
    elif kind == 'mp4':
        number(recipe['height'], 0, 4320)
    else:
        number(recipe['gop'], 1, 1000)
        number(recipe['segment_seconds'], .1, 10)
        if type(recipe['has_audio']) is not bool or not isinstance(recipe['variants'], list) or not 1 <= len(recipe['variants']) <= 4:
            raise ValueError('Invalid video variants.')
        for variant in recipe['variants']:
            if not isinstance(variant, dict) or set(variant) != {'height', 'bitrate', 'maxrate', 'bufsize', 'audio_bitrate'}:
                raise ValueError('Invalid video variant.')
            number(variant['height'], 2, 4320)
            for key in ('bitrate', 'maxrate', 'bufsize', 'audio_bitrate'):
                if not isinstance(variant[key], str) or not re.fullmatch(r'[1-9][0-9]{0,5}k', variant[key]):
                    raise ValueError('Invalid video bitrate.')
    return recipe


def hardware_devices():
    if sys.platform == 'darwin':
        try:
            name = subprocess.check_output(['sysctl', '-n', 'machdep.cpu.brand_string'], text=True, timeout=3).strip()
        except (OSError, subprocess.SubprocessError):
            name = 'Apple Silicon'
        return [{'id': 'videotoolbox', 'name': name, 'encoder': 'h264_videotoolbox'}]
    devices = []
    for path in sorted(Path('/dev/dri').glob('renderD*')):
        if not re.fullmatch(r'renderD[0-9]+', path.name):
            continue
        device_path = Path('/sys/class/drm') / path.name / 'device'
        try:
            vendor = (device_path / 'vendor').read_text().strip()
        except OSError:
            continue
        if vendor not in {'0x1002', '0x8086'}:
            continue
        name = 'AMD Radeon' if vendor == '0x1002' else 'Intel graphics'
        try:
            name = subprocess.check_output(['lspci', '-s', device_path.resolve().name], text=True, timeout=3).strip().split(': ', 1)[-1]
        except (OSError, subprocess.SubprocessError):
            pass
        devices.append({'id': f'vaapi:{path.name}', 'name': name, 'encoder': 'h264_vaapi'})
    try:
        rows = subprocess.check_output(['nvidia-smi', '--query-gpu=index,name', '--format=csv,noheader'], text=True, timeout=3)
        for row in rows.splitlines():
            index, name = row.split(',', 1)
            if re.fullmatch(r'[0-9]{1,2}', index.strip()):
                devices.append({'id': f'nvenc:{index.strip()}', 'name': name.strip(), 'encoder': 'h264_nvenc'})
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return devices


def device_options(device):
    identity = device['id'] if device else 'cpu'
    if identity == 'videotoolbox':
        return [], 'h264_videotoolbox'
    if re.fullmatch(r'vaapi:renderD[0-9]+', identity):
        return ['-vaapi_device', '/dev/dri/' + identity.split(':')[1]], 'h264_vaapi'
    if re.fullmatch(r'nvenc:[0-9]{1,2}', identity):
        return [], 'h264_nvenc'
    if identity == 'cpu':
        return [], 'libx264'
    raise ValueError('Invalid processing device.')


def encoder_options(device, *, index=None, quality=23):
    _, encoder = device_options(device)
    suffix = f':v:{index}' if index is not None else ':v'
    result = [f'-c{suffix}', encoder]
    if encoder == 'libx264':
        return result + [f'-preset{suffix}', 'medium' if quality == 16 else 'fast', f'-crf{suffix}', str(quality)]
    if encoder == 'h264_videotoolbox':
        return result + ['-allow_sw', '0', f'-q{suffix}', '75' if quality == 16 else '65']
    if encoder == 'h264_nvenc':
        return result + [f'-gpu{suffix}', device['id'].split(':')[1], f'-preset{suffix}', 'p4', f'-cq{suffix}', str(quality)]
    return result + [f'-qp{suffix}', str(quality)]


def thumbnail_decode_options(device):
    if not device:
        return [], ''
    identity = device['id']
    if identity == 'videotoolbox':
        options = ['-hwaccel', 'videotoolbox', '-hwaccel_output_format', 'videotoolbox_vld']
    elif identity.startswith('vaapi:'):
        options = ['-hwaccel', 'vaapi', '-hwaccel_device', '/dev/dri/' + identity.split(':')[1], '-hwaccel_output_format', 'vaapi']
    elif identity.startswith('nvenc:'):
        options = ['-hwaccel', 'cuda', '-hwaccel_device', identity.split(':')[1], '-hwaccel_output_format', 'cuda']
    else:
        raise ValueError('Invalid thumbnail device.')
    # Explicit hardware frames: unsupported input cannot silently count as GPU.
    return options, 'hwdownload,format=nv12,'


def build_command(input_path, output_path, recipe, device=None):
    validate_recipe(recipe)
    prefix, encoder = device_options(device)
    cmd = ['ffmpeg', '-hide_banner', '-nostdin', '-nostats', '-loglevel', 'error', '-y', *prefix]
    kind = recipe['kind']
    if kind == 'thumbnail':
        decode, download = thumbnail_decode_options(device)
        width = int(recipe['width'])
        return cmd + decode + ['-ss', str(recipe['seek']), '-i', str(input_path), '-frames:v', '1', '-vf',
                              f'{download}scale=ceil(iw*sar/2)*2:ih,setsar=1,scale={width}:-2', '-q:v', '2', str(output_path)]
    cmd += ['-fflags', '+genpts', '-i', str(input_path)] if kind == 'hls' else ['-i', str(input_path)]
    upload = ',format=nv12,hwupload' if encoder == 'h264_vaapi' else ''
    if kind == 'mp4':
        cmd += encoder_options(device)
        height = int(recipe['height'])
        filters = (f'scale=-2:{height}' if height else 'null') + upload
        if height or upload:
            cmd += ['-vf', filters]
        return cmd + ['-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', '-progress', 'pipe:1', '-f', 'mp4', str(output_path)]
    variants, audio = recipe['variants'], recipe['has_audio']
    segment = f"{recipe['segment_seconds']:.3f}".rstrip('0').rstrip('.')
    if len(variants) > 1:
        graph = [f"[0:v:0]split={len(variants)}" + ''.join(f'[vsplit{i}]' for i in range(len(variants)))]
        graph += [f"[vsplit{i}]scale=-2:{int(v['height'])}:flags=lanczos{upload}[vout{i}]" for i, v in enumerate(variants)]
        cmd += ['-filter_complex', ';'.join(graph)]
        for i in range(len(variants)):
            cmd += ['-map', f'[vout{i}]'] + (['-map', '0:a:0?'] if audio else [])
    else:
        cmd += ['-map', '0:v:0'] + (['-map', '0:a:0?'] if audio else [])
    for i, variant in enumerate(variants):
        cmd += encoder_options(device, index=i, quality=16)
        cmd += [f'-profile:v:{i}', 'high', f'-g:v:{i}', str(int(recipe['gop'])), f'-bf:v:{i}', '0',
                f'-force_key_frames:v:{i}', f'expr:gte(t,n_forced*{segment})', f'-b:v:{i}', variant['bitrate'],
                f'-maxrate:v:{i}', variant['maxrate'], f'-bufsize:v:{i}', variant['bufsize']]
        if encoder == 'libx264':
            cmd += [f'-pix_fmt:v:{i}', 'yuv420p', f'-sc_threshold:v:{i}', '0', f'-keyint_min:v:{i}', str(int(recipe['gop']))]
        elif encoder != 'h264_vaapi':
            cmd += [f'-pix_fmt:v:{i}', 'yuv420p']
        if len(variants) == 1:
            cmd += [f'-vf:v:{i}', f"scale=-2:{int(variant['height'])}:flags=lanczos{upload}"]
        if audio:
            cmd += [f'-c:a:{i}', 'aac', f'-b:a:{i}', variant['audio_bitrate'], f'-ac:a:{i}', '2', f'-ar:a:{i}', '48000']
    output_path = Path(output_path)
    return cmd + ['-muxdelay', '0', '-muxpreload', '0', '-avoid_negative_ts', 'make_zero', '-f', 'hls',
                  '-hls_time', segment, '-hls_playlist_type', 'vod', '-hls_flags', 'independent_segments',
                  '-master_pl_name', 'master.m3u8', '-var_stream_map', ' '.join(f'v:{i},a:{i}' if audio else f'v:{i}' for i in range(len(variants))),
                  '-hls_segment_filename', str(output_path / 'segment_%v_%03d.ts'), '-progress', 'pipe:1', str(output_path / 'variant_%v.m3u8')]


def check_device(device):
    result = {**device, 'encoding': False, 'thumbnails': False, 'message': 'Hardware check failed. CPU remains available.'}
    try:
        with tempfile.TemporaryDirectory(prefix='vueio-hardware-') as temporary:
            source = Path(temporary) / 'sample.mp4'
            prefix, encoder = device_options(device)
            filters = 'format=nv12,hwupload' if encoder == 'h264_vaapi' else 'format=yuv420p'
            cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-y', *prefix, '-f', 'lavfi',
                   '-i', 'color=c=black:s=320x180:r=24', '-frames:v', '8', '-vf', filters, *encoder_options(device), str(source)]
            run = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
            result['encoding'] = run.returncode == 0 and source.is_file() and source.stat().st_size > 0
            if result['encoding']:
                target = Path(temporary) / 'thumbnail.jpg'
                run = subprocess.run(build_command(source, target, {'kind': 'thumbnail', 'seek': 0, 'width': 320}, device),
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
                result['thumbnails'] = run.returncode == 0 and target.is_file() and target.stat().st_size > 0
                result['message'] = 'Hardware video encoding passed.' + (' Hardware thumbnail decoding passed.' if result['thumbnails'] else ' Thumbnails will use CPU.')
    except (OSError, subprocess.SubprocessError):
        pass
    return result


def open_beneath(root, relative, *, directory=False, create=False):
    """Walk with directory descriptors. Refuse symlinks, including race swaps."""
    parts = relative.split('/')
    if not parts or any(part in {'', '.', '..'} or '\x00' in part for part in parts):
        raise ValueError('Invalid media path.')
    descriptor = os.dup(root) if isinstance(root, int) else os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for index, part in enumerate(parts):
            last = index == len(parts) - 1
            flags = os.O_NOFOLLOW | os.O_NONBLOCK
            flags |= (os.O_WRONLY | os.O_CREAT | os.O_EXCL) if last and create else os.O_RDONLY
            if not last or directory:
                flags |= os.O_DIRECTORY
            child = os.open(part, flags, 0o600, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        info = os.fstat(descriptor)
        if not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
            raise ValueError('Not a media file or directory.')
        result, descriptor = descriptor, None
        return result
    finally:
        if descriptor is not None:
            os.close(descriptor)


class NativeMedia:
    """Mac-only jobs behind the existing authenticated host bridge.

    FFmpeg writes only in a host-private temporary directory. Completed files
    are copied through no-follow descriptors into an empty engine staging path.
    The engine still owns authorization, cancellation and atomic publication.
    """
    def __init__(self, host):
        self.host = host
        self.jobs = {}
        self.devices = None

    def check(self):
        if sys.platform != 'darwin':
            raise ValueError('Native media processing is available on Mac only.')
        self.devices = [check_device(device) for device in hardware_devices()]
        return {'devices': self.devices}

    def input_descriptor(self, raw, config):
        if not isinstance(raw, str) or len(raw) > 4096:
            raise ValueError('Invalid media path.')
        if raw.startswith('/app/data/'):
            relative = raw[len('/app/data/'):]
            if relative.split('/')[0] not in {'projects', 'comment_attachments', 'cache'}:
                raise ValueError('Not a media location.')
            return open_beneath(config['VUEIO_DATA_PATH'], relative)
        match = re.fullmatch(r'/storage/root-([0-9]{3})/(.+)', raw)
        if not match:
            raise ValueError('Not a connected media location.')
        record = self.host.home / 'storage.d' / (match[1] + '.root')
        if record.is_symlink() or record.stat().st_size > 8192:
            raise ValueError('Invalid storage record.')
        _, root, mode, marker = record.read_text().splitlines()
        if mode not in {'ro', 'rw'}:
            raise ValueError('Invalid storage mode.')
        root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            fd = open_beneath(root_fd, '.vueio-storage-id')
            try:
                if os.read(fd, 130).decode('ascii').strip() != marker:
                    raise ValueError('The original media drive is not connected.')
            finally:
                os.close(fd)
            return open_beneath(root_fd, match[2])
        finally:
            os.close(root_fd)

    def start(self, payload):
        if sys.platform != 'darwin' or not isinstance(payload, dict) or set(payload) != {'id', 'input', 'output', 'recipe'}:
            raise ValueError('Invalid native media request.')
        identity = payload['id']
        if not isinstance(identity, str) or not re.fullmatch('[a-f0-9]{32}', identity):
            raise ValueError('Invalid job identity.')
        if identity in self.jobs:
            return self.poll(identity)
        if len(self.jobs) >= 16 or sum(job['process'].poll() is None for job in self.jobs.values()) >= 4:
            raise ValueError('Native media processing is busy.')
        recipe = validate_recipe(payload['recipe'])
        if not self.devices or not self.devices[0]['encoding'] or (recipe['kind'] == 'thumbnail' and not self.devices[0]['thumbnails']):
            raise ValueError('Check the Mac hardware before using it.')
        output = payload['output']
        if not isinstance(output, str) or len(output) > 4096 or not output.startswith('/app/data/cache/'):
            raise ValueError('Invalid preview output.')
        relative = output[len('/app/data/'):]
        if not re.fullmatch(r'cache/(?:transcodes|thumbnails)/[A-Za-z0-9_.-]+', relative) or '.part' not in relative:
            raise ValueError('Only temporary previews can be written.')
        config = self.host.config()
        data_root = config['VUEIO_DATA_PATH']
        state = Path(config.get('VUEIO_STATE_PATH', ''))
        if not state.is_absolute() or Path(data_root) != state / 'app':
            raise ValueError('Native processing needs a verified Vue data folder.')
        state_fd = os.open(state, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            marker_fd = open_beneath(state_fd, '.vueio-storage-id')
            try:
                if os.read(marker_fd, 130).decode('ascii').strip() != config.get('VUEIO_STATE_ID'):
                    raise ValueError('The original Vue data drive is not connected.')
            finally:
                os.close(marker_fd)
            # Keep the verified drive open through destination selection.
            parent = relative if recipe['kind'] == 'hls' else relative.rsplit('/', 1)[0]
            output_fd = open_beneath(state_fd, 'app/' + parent, directory=True)
        finally:
            os.close(state_fd)
        input_fd = None
        work = None
        lock = None
        try:
            import fcntl
            reserve = max(256 * 1024 * 1024, int(config.get('DATA_MIN_FREE_BYTES', 20 * 1024**3)))
            if shutil.disk_usage(self.host.home).free < reserve:
                raise ValueError('Not enough free space for native processing.')
            lock = self.host.lock_file.open('a')
            fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
            input_fd = self.input_descriptor(payload['input'], config)
            work = tempfile.TemporaryDirectory(prefix='.native-media-', dir=self.host.home)
            target = Path(work.name) / ('output.jpg' if recipe['kind'] == 'thumbnail' else 'output.mp4')
            if recipe['kind'] == 'hls':
                target = Path(work.name) / 'hls'
                target.mkdir()
            cmd = build_command(f'/dev/fd/{input_fd}', target, recipe, self.devices[0])
            cmd[0] = '/opt/homebrew/bin/ffmpeg'
            input_index = cmd.index('-i')
            # Never let a playlist or concat document read unrelated host files.
            cmd[input_index:input_index] = ['-protocol_whitelist', 'file,pipe', '-format_whitelist',
                                           'mov,matroska,webm,avi,mxf,mpegvideo,mpegts,image2,jpeg_pipe,png_pipe,tiff_pipe,exr_pipe,dpx_pipe']
            log = tempfile.TemporaryFile(dir=work.name)
            process = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log, stderr=log, pass_fds=(input_fd,))
            self.jobs[identity] = dict(process=process, work=work, target=target, log=log, output_fd=output_fd,
                                       name=relative.rsplit('/', 1)[-1], lock=lock, heartbeat=time.monotonic(),
                                       reserve=reserve, finished=None, returncode=None, time_us=0)
            return {'id': identity, 'returncode': None, 'time_us': 0}
        except Exception:
            os.close(output_fd)
            if lock: lock.close()
            if work: work.cleanup()
            raise
        finally:
            if input_fd is not None: os.close(input_fd)

    def poll(self, identity):
        job = self.jobs.get(identity)
        if not job:
            raise ValueError('The native media job is no longer available.')
        job['heartbeat'] = time.monotonic()
        self.finish(job)
        if job['finished'] is None:
            # Bounded tail; the file descriptor is independent of FFmpeg's offset.
            chunk = os.pread(job['log'].fileno(), 8192, max(0, os.fstat(job['log'].fileno()).st_size - 8192)).decode(errors='replace')
            values = re.findall(r'out_time_us=([0-9]+)', chunk)
            if values: job['time_us'] = int(values[-1])
        return {'id': identity, 'returncode': job['returncode'], 'time_us': job['time_us']}

    def cancel(self, identity):
        job = self.jobs.get(identity)
        if job and job['finished'] is None:
            job['process'].terminate()
            try: job['process'].wait(timeout=2)
            except subprocess.TimeoutExpired:
                job['process'].kill()
                job['process'].wait(timeout=2)
            self.finish(job, cancelled=True)
        return {'cancelled': True}

    def finish(self, job, *, cancelled=False):
        if job['finished'] is not None or job['process'].poll() is None:
            return
        code = job['process'].returncode
        try:
            if code == 0 and not cancelled:
                target = job['target']
                files = list(target.iterdir()) if target.is_dir() else [target]
                if not files or len(files) > 100000:
                    raise ValueError('Invalid preview output.')
                for source in files:
                    name = source.name if target.is_dir() else job['name']
                    if target.is_dir() and not re.fullmatch(r'master\.m3u8|variant_[0-3]\.m3u8|segment_[0-3]_[0-9]+\.ts', name):
                        raise ValueError('Invalid preview file.')
                    space = os.fstatvfs(job['output_fd'])
                    if space.f_bavail * space.f_frsize < source.stat().st_size + job['reserve']:
                        raise ValueError('Not enough free space to finish the preview.')
                    descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o640, dir_fd=job['output_fd'])
                    with os.fdopen(descriptor, 'wb') as destination, source.open('rb') as origin:
                        shutil.copyfileobj(origin, destination, 1024 * 1024)
            elif cancelled:
                code = -15
        except (OSError, ValueError):
            code = 1
        finally:
            job['returncode'] = code
            job['finished'] = time.monotonic()
            job['log'].close()
            os.close(job['output_fd'])
            job['lock'].close()
            job['work'].cleanup()

    def reap(self):
        for identity, job in list(self.jobs.items()):
            if job['finished'] is None:
                if time.monotonic() - job['heartbeat'] > 45 or shutil.disk_usage(self.host.home).free < job['reserve']:
                    self.cancel(identity)
                else:
                    self.finish(job)
            elif time.monotonic() - job['finished'] > 60:
                del self.jobs[identity]

    def close(self):
        for identity in list(self.jobs):
            self.cancel(identity)
