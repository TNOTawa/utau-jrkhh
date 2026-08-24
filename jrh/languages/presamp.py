"""presamp.ini（中文 CVVC 音源标准配置）内置模板与解析。

单一事实来源，同一份数据驱动三处：
- 交付：export-vc 把 `PRESAMP_INI_TEXT` 原样写入音源目录（与生态标准模板逐字节一致：
  VERSION 1.7、CRLF 行尾、无 BOM、无末尾换行）；
- 别名映射：`vc_vowel`/`vc_consonant` 从 [VOWEL]/[CONSONANT] 表推导「音节 → 短 ID」；
- OpenUtau 内置 zh-cvv 音素器：读取音源内 presamp.ini 的同一张表生成 VC 别名
  （源码实证：`{prevVowel} {consonant}`，空格分隔），因此三方永不漂移。

格式（官方规范《presamp.ini说明文件》，全文见仓库 presamp-spec.md）：
- [VOWEL]      v=V=CV,CV,…=vol        （vol 为保留音量参数，未启用；V 为代表 CV，未用）
- [CONSONANT]  c=CV,CV,…=flag(=len)   （flag = 交叉渐变开关：爆破音 b/p/d/t/g/k 为 1）
- [PRIORITY] / [REPLACE] / [ENDTYPE] / [ENDFLAG] 原样交付，本模块只解析 VOWEL/CONSONANT。
- 枚举外的音节（如 yo）两侧映射均为 None → 调用方按约定跳过（不生成 VC），
  与 OpenUtau 侧行为一致（其辅音侧回退为完整拼音，同样匹配不到）。

纯 stdlib；依赖 jrh.core.errors（语言包同族惯例）。
"""

from __future__ import annotations

from ..core.errors import DataError

PRESAMP_VERSION = "1.7"

# 与生态标准模板逐字节一致：CRLF 行尾、无 BOM、末尾无换行。
_PRESAMP_LINES = [
    "[VERSION]",
    "1.7",
    "[VOWEL]",
    "a=a=a,ba,pa,ma,fa,da,ta,na,la,ga,ka,ha,zha,cha,sha,za,ca,sa,ya,lia,jia,qia,xia,wa,gua,kua,hua,zhua,shua,dia=100",
    "ai=ai=ai,bai,pai,mai,dai,tai,nai,lai,gai,kai,hai,zhai,chai,shai,zai,cai,sai,wai,guai,kuai,huai,zhuai,chuai,shuai=100",
    "an=an=an,ban,pan,man,fan,dan,tan,nan,lan,gan,kan,han,zhan,chan,shan,ran,zan,can,san,wan,duan,tuan,nuan,luan,guan,kuan,huan,zhuan,chuan,shuan,ruan,zuan,cuan,suan=100",
    "ang=ang=ang,bang,pang,mang,fang,dang,tang,nang,lang,gang,kang,hang,zhang,chang,shang,rang,zang,cang,sang,yang,liang,jiang,qiang,xiang,wang,guang,kuang,huang,zhuang,chuang,shuang,niang=100",
    "ao=ao=ao,bao,pao,mao,dao,tao,nao,lao,gao,kao,hao,zhao,chao,shao,rao,zao,cao,sao,yao,biao,piao,miao,diao,tiao,niao,liao,jiao,qiao,xiao=100",
    "e=e=e,me,de,te,ne,le,ge,ke,he,zhe,che,she,re,ze,ce,se=100",
    "e0=e0=ye,bie,pie,mie,die,tie,nie,lie,jie,qie,xie,yue,nue,lue,jue,que,xue=100",
    "ei=ei=ei,bei,pei,mei,fei,dei,tei,nei,lei,gei,kei,hei,zhei,shei,zei,wei,dui,tui,gui,kui,hui,zhui,chui,shui,rui,zui,cui,sui=100",
    "en=en=en,ben,pen,men,fen,nen,gen,ken,hen,zhen,chen,shen,ren,zen,cen,sen,wen,dun,tun,lun,gun,kun,hun,zhun,chun,shun,run,zun,cun,sun=100",
    "en0=en0=yan,bian,pian,mian,dian,tian,nian,lian,jian,qian,xian,yuan,juan,quan,xuan=100",
    "eng=eng=beng,peng,meng,feng,deng,teng,neng,leng,geng,keng,heng,weng,zheng,cheng,sheng,reng,zeng,ceng,seng=100",
    "er=er=er=100",
    "i=i=bi,pi,mi,di,ti,ni,li,ji,qi,xi,yi=100",
    "in=in=yin,bin,pin,min,nin,lin,jin,qin,xin=100",
    "ing=ing=ying,bing,ping,ming,ding,ting,ning,ling,jing,qing,xing=100",
    "i0=i0=zi,ci,si=100",
    "ir=ir=zhi,chi,shi,ri=100",
    "o=o=bo,po,mo,fo,wo,duo,tuo,nuo,luo,guo,kuo,huo,zhuo,chuo,shuo,ruo,zuo,cuo,suo=100",
    "ong=ong=dong,tong,nong,long,gong,kong,hong,zhong,chong,rong,zong,cong,song,yong,jiong,qiong,xiong=100",
    "ou=ou=ou,pou,mou,fou,dou,tou,lou,gou,kou,hou,zhou,chou,shou,rou,zou,cou,sou,you,miu,diu,niu,liu,jiu,qiu,xiu=100",
    "u=u=bu,pu,mu,fu,du,tu,nu,lu,gu,ku,hu,zhu,chu,shu,ru,zu,cu,su,wu=100",
    "v=v=yu,nv,lv,ju,qu,xu=100",
    "vn=vn=yun,jun,qun,xun=100",
    "[CONSONANT]",
    "b=ba,bai,ban,bang,bao,biao,bie,bei,ben,bian,beng,bi,bin,bing,bo,bu=1",
    "p=pa,pai,pan,pang,pao,piao,pie,pei,pen,pian,peng,pi,pin,ping,po,pou,pu=1",
    "m=ma,mai,man,mang,mao,me,mei,men,meng,mo,mou,mu=0",
    "f=fa,fan,fang,fei,fen,feng,fo,fou,fu=0",
    "d=da,dia,dai,dan,duan,dang,dao,diao,de,die,dei,dui,dun,dian,deng,di,ding,duo,dong,dou,diu,du=1",
    "t=ta,tai,tan,tuan,tang,tao,tiao,te,tie,tei,tui,tun,tian,teng,ti,ting,tuo,tong,tou,tu=1",
    "n=na,nai,nan,nuan,nang,nao,ne,nue,nei,nen,neng,nuo,nong,nu,nv=0",
    "l=la,lai,lan,luan,lang,lao,le,lue,lei,lun,leng,luo,long,lou,lu,lv=0",
    "g=ga,gua,gai,guai,gan,guan,gang,guang,gao,ge,gei,gui,gen,gun,geng,guo,gong,gou,gu=1",
    "k=ka,kua,kai,kuai,kan,kuan,kang,kuang,kao,ke,kei,kui,ken,kun,keng,kuo,kong,kou,ku=1",
    "h=ha,hai,han,hang,hao,he,hei,hen,heng,hong,hou=0",
    "zh=zha,zhua,zhai,zhuai,zhan,zhuan,zhang,zhuang,zhao,zhe,zhei,zhui,zhen,zhun,zheng,zhi,zhuo,zhong,zhou,zhu=0",
    "ch=cha,chai,chuai,chan,chuan,chang,chuang,chao,che,chui,chen,chun,cheng,chi,chuo,chong,chou,chu=0",
    "sh=sha,shai,shan,shang,shao,she,shei,shen,sheng,shi,shou=0",
    "z=za,zai,zan,zuan,zang,zao,ze,zei,zui,zen,zun,zeng,zi,zuo,zong,zou,zu=0",
    "c=ca,cai,can,cuan,cang,cao,ce,cui,cen,cun,ceng,ci,cuo,cong,cou,cu=0",
    "s=sa,sai,san,sang,sao,se,sen,seng,si,song,sou=0",
    "y=ya,yang,yao,ye,yan,yi,yin,ying,yong,you=0",
    "ly=lia,liang,liao,lie,lian,li,lin,ling,liu=0",
    "j=jia,jiang,jiao,jie,jue,jian,juan,ji,jin,jing,jiong,jiu,ju,jun=0",
    "q=qia,qiang,qiao,qie,que,qian,quan,qi,qin,qing,qiong,qiu,qu,qun=0",
    "xy=xia,xiang,xiao,xie,xian,xi,xin,xing,xiong,xiu=0",
    "w=wa,wai,wan,wang,wei,wen,weng,wo,wu=0",
    "hw=hua,huai,huan,huang,hui,hun,huo,hu=0",
    "shw=shua,shuai,shuan,shuang,shui,shun,shuo,shu=0",
    "r=ran,ruan,rang,rao,re,rui,ren,run,reng,ri,ruo,rong,rou,ru=0",
    "sw=suan,sui,sun,suo,su=0",
    "ny=niang,niao,nie,nian,ni,nin,ning,niu=0",
    "my=miao,mie,mian,mi,min,ming,miu=0",
    "v=yu,yue,yuan,yun=0",
    "xw=xue,xuan,xu,xun=0",
    "[PRIORITY]",
    "k,g,t,d,b,p",
    "[REPLACE]",
    "a=a",
    "[ENDTYPE]",
    "%v% R",
    "[ENDFLAG]",
    "1",
]

# CRLF 行尾、无末尾换行（与标准模板逐字节一致）
PRESAMP_INI_TEXT = "\r\n".join(_PRESAMP_LINES)


def _blocks(text: str) -> dict[str, list[str]]:
    """按 [SECTION] 拆块，返回 {section: 行列表}（保序）。"""
    blocks: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("[") and s.endswith("]"):
            current = s[1:-1]
            if current in blocks:
                raise DataError(f"presamp.ini 模板重复 section: [{current}]")
            blocks[current] = []
            continue
        if current is None:
            raise DataError(f"presamp.ini 模板 section 前出现内容: {s!r}")
        blocks[current].append(s)
    return blocks


def load_presamp_maps(text: str = PRESAMP_INI_TEXT) -> tuple[dict[str, str], dict[str, str]]:
    """解析内置 presamp.ini → (vowel_map, consonant_map)（音节 → 短 ID）。

    条目倒数第二段 = CV 枚举列表；第一段 = 短 ID。重复枚举 ⇒ DataError（表必须自洽）。
    """
    vowel_map: dict[str, str] = {}
    consonant_map: dict[str, str] = {}
    blocks = _blocks(text)
    for name, target in (("VOWEL", vowel_map), ("CONSONANT", consonant_map)):
        for line in blocks.get(name, []):
            parts = [p.strip() for p in line.split("=")]
            if len(parts) < 3:
                raise DataError(f"presamp.ini [{name}] 条目格式错误: {line!r}")
            sid = parts[0]
            cv_list = parts[-2]
            if not sid or not cv_list:
                raise DataError(f"presamp.ini [{name}] 条目格式错误: {line!r}")
            for syllable in (t.strip() for t in cv_list.split(",")):
                if not syllable:
                    continue
                if syllable in target and target[syllable] != sid:
                    raise DataError(f"presamp.ini 音节 {syllable!r} 在 [{name}] 中重复且 ID 冲突")
                target[syllable] = sid
    return vowel_map, consonant_map


_VOWEL_MAP, _CONSONANT_MAP = load_presamp_maps()

VOWEL_IDS: tuple[str, ...] = tuple(sorted(set(_VOWEL_MAP.values())))
CONSONANT_IDS: tuple[str, ...] = tuple(sorted(set(_CONSONANT_MAP.values())))


def vowel_id_of(syllable: str) -> str | None:
    """音节 → presamp 韵母短 ID；未枚举返回 None。"""
    return _VOWEL_MAP.get(syllable)


def consonant_id_of(syllable: str) -> str | None:
    """音节 → presamp 声母短 ID；未枚举（含零声母）返回 None。"""
    return _CONSONANT_MAP.get(syllable)


def syllables_of_vowel(vowel_id: str) -> frozenset[str]:
    """韵母短 ID → 全部音节（供拼字源候选）。"""
    return frozenset(s for s, v in _VOWEL_MAP.items() if v == vowel_id)


def syllables_of_consonant(consonant_id: str) -> frozenset[str]:
    """声母短 ID → 全部音节（供拼字源候选）。"""
    return frozenset(s for s, c in _CONSONANT_MAP.items() if c == consonant_id)
