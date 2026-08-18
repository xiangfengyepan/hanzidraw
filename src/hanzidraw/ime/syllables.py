"""The legal toneless-pinyin syllable inventory and input normalisation.

``ü`` is written ``v`` everywhere, matching the Keychron firmware's convention,
so ``lü`` -> ``lv`` and ``xüe`` -> ``xve``.
"""

from __future__ import annotations

import re
import unicodedata

_SYLLABLE_LIST = """
a ai an ang ao
ba bai ban bang bao bei ben beng bi bian biao bie bin bing bo bu
ca cai can cang cao ce cei cen ceng ci cong cou cu cuan cui cun cuo
cha chai chan chang chao che chen cheng chi chong chou chu chua chuai
chuan chuang chui chun chuo
da dai dan dang dao de dei den deng di dia dian diao die ding diu dong
dou du duan dui dun duo
e ei en eng er
fa fan fang fei fen feng fiao fo fou fu
ga gai gan gang gao ge gei gen geng gong gou gu gua guai guan guang gui
gun guo
ha hai han hang hao he hei hen heng hong hou hu hua huai huan huang hui
hun huo hm hng
ji jia jian jiang jiao jie jin jing jiong jiu ju juan jue jun
ka kai kan kang kao ke kei ken keng kong kou ku kua kuai kuan kuang kui
kun kuo
la lai lan lang lao le lei leng li lia lian liang liao lie lin ling liu
lo long lou lu luan lun luo lv lve
ma mai man mang mao me mei men meng mi mian miao mie min ming miu mo mou
mu m
na nai nan nang nao ne nei nen neng ni nian niang niao nie nin ning niu
nong nou nu nuan nun nuo nv nve n ng
o ou
pa pai pan pang pao pei pen peng pi pian piao pie pin ping po pou pu
qi qia qian qiang qiao qie qin qing qiong qiu qu quan que qun
ran rang rao re ren reng ri rong rou ru rua ruan rui run ruo
sa sai san sang sao se sen seng si song sou su suan sui sun suo
sha shai shan shang shao she shei shen sheng shi shou shu shua shuai
shuan shuang shui shun shuo
ta tai tan tang tao te tei teng ti tian tiao tie ting tong tou tu tuan
tui tun tuo
wa wai wan wang wei wen weng wo wu
xi xia xian xiang xiao xie xin xing xiong xiu xu xuan xue xun
ya yan yang yao ye yi yin ying yo yong you yu yuan yue yun
za zai zan zang zao ze zei zen zeng zi zong zou zu zuan zui zun zuo
zha zhai zhan zhang zhao zhe zhei zhen zheng zhi zhong zhou zhu zhua
zhuai zhuan zhuang zhui zhun zhuo
"""

SYLLABLES: frozenset[str] = frozenset(_SYLLABLE_LIST.split())
MAX_SYLLABLE_LEN: int = max(len(s) for s in SYLLABLES)
_PREFIXES: frozenset[str] = frozenset(s[:i] for s in SYLLABLES for i in range(1, len(s) + 1))

_SEPARATORS = re.compile(r"[\s/,;·]+")
_NON_LETTER = re.compile(r"[^a-z]")


def normalise_pinyin(raw: str) -> str:
    """Fold one reading to the canonical form: lowercase, toneless, ``ü`` -> ``v``."""
    s = unicodedata.normalize("NFD", raw.strip().lower())
    s = s.replace("u:", "v")
    out: list[str] = []
    i = 0
    while i < len(s):
        ch = s[i]
        nxt = s[i + 1] if i + 1 < len(s) else ""
        if ch == "u" and nxt == "̈":  # u + combining diaeresis == ü
            out.append("v")
            i += 2
            continue
        if unicodedata.combining(ch):  # any other tone mark
            i += 1
            continue
        out.append(ch)
        i += 1
    return _NON_LETTER.sub("", "".join(out))


def split_readings(raw: str) -> tuple[str, ...]:
    """Split a source's reading field into normalised readings, dropping empties."""
    parts = (normalise_pinyin(p) for p in _SEPARATORS.split(raw or ""))
    return tuple(p for p in parts if p)


def is_syllable(s: str) -> bool:
    return s in SYLLABLES


def is_syllable_prefix(s: str) -> bool:
    return bool(s) and s in _PREFIXES
