#!/usr/bin/env python

import re
import subprocess
import asyncio
import logging
import random
import os

from conf import fumu
import sys
sys.path.append('./lib')
import discord


class FumuLogHandler(logging.Handler):
    dt = None
    def emit(self, record):
        msg = self.format(record)
        if 'logexc_start' in fumu and hasattr(record.msg, 'startswith') and record.msg.startswith(fumu['logexc_start']):
            return
        if 'logexc_any' in fumu and any(exc in msg for exc in fumu['logexc_any']):
            return
        msg = discord.utils.escape_markdown(msg)
        if record.levelno == logging.DEBUG:
            msg = f"||{msg}||"
        elif record.levelno > logging.DEBUG:
            msg = f"```{msg}```"
            if 'debugger' in fumu and record.levelno > logging.INFO:
                msg = '<@'+str(fumu['debugger'])+'> '+msg
        try:
            asyncio.get_event_loop().create_task(self.dt.get_channel(fumu['debugchannel']).send(msg))
        except Exception:
            pass
        return

class Sudachi(discord.Client):
    logger = None
    vc = None
    playstep: int = 1
    playqueue: list = []
    repeats: int = 2
    _pleas: list = []

    plea_stop: bool = False
    plea_skip: bool = False

    async def fumulog(self, lvl: str, str: str):
        if lvl == 'none':
            return
        if lvl == 'warning':
            self.logger.warning(str)
        elif lvl == 'info':
            self.logger.info(str)
        elif lvl == 'info_nods':
            self.logger.info('=+= '+str)
        elif lvl == 'debug':
            self.logger.debug(str)
        return

    async def join_voice(self, message):
        if not hasattr(message.author, 'voice') or not getattr(message.author, 'voice'):
            return False
        if not hasattr(message.author.voice, 'channel') or not getattr(message.author.voice, 'channel'):
            return False
        if not self.vc:
            self.vc = await message.author.voice.channel.connect()
            return True
        await self.vc.move_to(message.author.voice.channel)
        return True

    def bgmfile(self, key1: str, key2: str, key3: str) -> str:
        return fumu['bgmprefix'] + key1 + '_' + key2 + key3 + '_hca.hca'

    def bgmlist(self, r1: str = None, r2: str = None, r3: str = None) -> list:
        if not r1:
            return [(k1, k2, v3) for k1, v1 in fumu['bgm'].items() for k2, v2 in v1.items() for v3 in v2]
        if not r2:
            return [(r1, k2, v3) for k2, v2 in fumu['bgm'].get(r1, {}).items() for v3 in v2]
        if not r3:
            return [(r1, r2, v3) for v3 in fumu['bgm'].get(r1, {}).get(r2, [])]
        if r3 in fumu['bgm'].get(r1, {}).get(r2, []):
            return [(r1, r2, r3)]
        return []

    def make_player(self, keys: tuple, repeats: int):
        bgmfile = self.bgmfile(*keys)
        return discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(subprocess.Popen((
            fumu['vgmcli'],
            "-l",
            str(repeats),
            "-p",
            bgmfile
        ), stdout = subprocess.PIPE).stdout, pipe = True, before_options = '-channel_layout stereo'))

    def init_logger(self):
        self.logger = logging.getLogger('discord')
        self.logger.setLevel(logging.DEBUG)

        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        self.logger.addHandler(ch)

        if fumu['dir']['log']:
            fh = logging.FileHandler(filename = fumu['dir']['log']+'/debug.log', encoding = 'utf-8')
            fh.setLevel(logging.DEBUG)
            fh.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
            self.logger.addHandler(fh)

        if fumu['debugchannel']:
            mh = FumuLogHandler()
            mh.setLevel(fumu.get('debuglevel', logging.DEBUG))
            mh.dt = self
            self.logger.addHandler(mh)


    async def play_hca(self, message, repeats: int = 0):
        self.plea_stop = False
        self.plea_skip = False
        if not repeats:
            repeats = self.repeats
        while self.playqueue and (keys := self.playqueue.pop(0)):
            if not self.vc:
                return
            self.vc.play(self.make_player(keys, repeats))
            while self.vc and (self.vc.is_playing() or self.vc.is_paused()):
                if self.plea_stop:
                    self.vc.stop()
                    await self.fumulog('info', f"stopping [{keys}]")
                    self.plea_stop = False
                    return
                if self.plea_skip:
                    self.vc.stop()
                    await self.fumulog('info', f"skipping [{keys}]")
                    self.plea_skip = False
                    break
                await asyncio.sleep(self.playstep)
            if self.vc:
                self.vc.stop()
            await self.fumulog('info', f"ended [{keys}]")

    async def on_error(self, *args):
        await self.fumulog('debug', args[1])
        await self.fumulog('warning', f"exception at [{args[0]}]")

    async def on_ready(self):
        self.init_logger()
        self.init_pleas()
        await self.fumulog('info_nods', f"discord.py {discord.__version__}")
        await self.fumulog('info_nods', f"{self.user.name}#{self.user.discriminator}@{self.user.id}")
        await self.change_presence(status = discord.Status.online, activity = discord.Activity(name = 'ふむむむ', type = discord.ActivityType.listening))
        await self.fumulog('info_nods', '===FUMU===')

    async def _latency(self, message, m = None):
        await message.channel.send(f"`{self.latency}`")

    async def _come(self, message, m = None):
        await self.join_voice(message)

    async def _leave(self, message, m = None):
        if self.vc:
            await self.vc.disconnect()
        self.playqueue = []
        self.vc = None

    async def _volume(self, message, m):
        if not self.vc:
            return
        vlm = min(100, int(m[0])) / 100
        self.vc.source.volume = vlm

    async def _list0(self, message, m = None):
        await message.channel.send(' | '.join(fumu['bgm'].keys()))

    async def _list1(self, message, m):
        await message.channel.send(' | '.join(fumu['bgm'].get(m[0], {}).keys()))

    async def _list2(self, message, m):
        if m[0] in fumu['bgm'] and m[1] in fumu['bgm'][m[0]]:
            await message.channel.send(' | '.join(fumu['bgm'][m[0]][m[1]]))

    async def _play(self, message, m):
        await self.join_voice(message)
        self.playqueue = self.bgmlist(*m)
        await self.play_hca(message)

    async def _repeat(self, message, m):
        await self.join_voice(message)
        self.playqueue = self.bgmlist(*m[1:])
        await self.play_hca(message, int(m[0]))

    async def _shuffle(self, message, m):
        await self.join_voice(message)
        self.playqueue = self.bgmlist(*m)
        random.shuffle(self.playqueue)
        await self.play_hca(message)

    async def _bgm(self, message, m = None):
        await self._repeat(message, ('99', '23', 'puella', '02'))

    async def _show(self, message, m = None):
        if not self.playqueue:
            return
        for i, q in enumerate(self.playqueue):
            await message.channel.send(f"`{i}. {q}`")

    async def _skip(self, message, m = None):
        self.plea_skip = True

    async def _pause(self, message, m = None):
        if not self.vc:
            return
        if self.vc.is_playing():
            self.vc.pause()

    async def _resume(self, message, m = None):
        if not self.vc:
            return
        #if self.vc.is_paused():
        self.vc.resume()

    async def _stop(self, message, m = None):
        self.plea_stop = True
        self.playqueue = []


    def init_pleas(self):
        self._pleas = [
        (name, re.compile(fr"{rexp}[\s]*"), action, delmsg)
        for name, (rexp, action, delmsg) in {
            'latency': (r'latency', self._latency, True),
            'come': (r'come', self._come, True),
            'leave': (r'leave', self._leave, True),
            'volume': (r'volume[\s]*([0-9]+)', self._volume, True,),
            'list0': (r'list', self._list0, False),
            'list1': (r'list[\s]*([\d]+)', self._list1, False),
            'list2': (r'list[\s]*([\d]+) ([^\s]+)', self._list2, False),
            'play': (r'play[\s]*([^\s]*)[\s]*([^\s]*)[\s]*([^\s]*)', self._play, False),
            'repeat': (r'repeat[\s]*([1-9][0-9]*)[\s]+([^\s]+)[\s]+([^\s]+)[\s]+([^\s]+)', self._repeat, False),
            'shuffle': (r'shuffle[\s]*([^\s]*)[\s]*([^\s]*)[\s]*([^\s]*)', self._shuffle, False),
            'bgm': (r'bgm', self._bgm, True),
            'show': (r'show', self._show, False),
            'skip': (r'skip', self._skip, True),
            'pause': (r'pause', self._pause, True),
            'resume': (r'resume', self._resume, True),
            'stop': (r'stop', self._stop, True)
        }.items()]

    async def on_message(self, message):
        if message.channel.id == fumu['debugchannel']:
            return
        if message.author.id == self.user.id:
            return
        if fumu['safeword'] in message.content:
            return
        if not message.content.startswith(fumu['callings']):
            return

        plea = message.content
        for calling in fumu['callings']:
            plea = plea.removeprefix(calling)
        plea = plea.lstrip()

        for name, rexpc, action, delmsg in self._pleas:
            if m := rexpc.fullmatch(plea):
                await self.fumulog('info', f"PLEA {name}")
                if delmsg and not isinstance(message.channel, discord.channel.DMChannel):
                    await message.delete()
                return await action(message, m.groups())

sudachi = Sudachi()

if __name__ == '__main__':
    if 'RC_SERVICE' in os.environ:
        import signal
        import aiofiles
        import yaml

        async def infodump():
            application_info = await sudachi.application_info()
            async with aiofiles.open('sudachi.pipe', 'w') as f:
                await f.write(yaml.dump({
                    'latency': sudachi.latency,
                    'app': {
                        'id': application_info.id,
                        'name': application_info.name,
                        'desc': application_info.description,
                        'owner': {
                            'id': application_info.owner.id,
                            'name': application_info.owner.name
                        },
                        'slug': application_info.slug,
                        'summary': application_info.summary,
                        'team': application_info.team
                    },
                    'user': {
                        'id': sudachi.user.id,
                        'name': sudachi.user.name,
                        'verified': sudachi.user.verified
                    }
                }, allow_unicode = True))

        asyncio.get_event_loop().add_signal_handler(signal.SIGUSR1, lambda: asyncio.ensure_future(infodump()))

    sudachi.run(fumu['token'])
