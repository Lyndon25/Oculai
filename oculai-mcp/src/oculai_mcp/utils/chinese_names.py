"""Chinese name variant generation and institution normalization.

Used for cross-source identity resolution and deep-dive search probing.
"""

from typing import Any

try:
    from pypinyin import Style, pinyin
except ImportError:
    pinyin = None  # type: ignore[assignment]
    Style = None  # type: ignore[assignment,misc]


INSTITUTION_ALIASES: dict[str, list[str]] = {
    "tsinghua": [
        "Tsinghua University",
        "清华大学",
        "THU",
        "清华",
    ],
    "peking": [
        "Peking University",
        "北京大学",
        "PKU",
        "北大",
    ],
    "sjtu": [
        "Shanghai Jiao Tong University",
        "上海交通大学",
        "SJTU",
        "上海交大",
    ],
    "zhejiang": [
        "Zhejiang University",
        "浙江大学",
        "ZJU",
        "浙大",
    ],
    "fudan": [
        "Fudan University",
        "复旦大学",
        "复旦",
    ],
    "ustc": [
        "University of Science and Technology of China",
        "中国科学技术大学",
        "USTC",
        "中科大",
    ],
    "cas": [
        "Chinese Academy of Sciences",
        "中国科学院",
        "中科院",
        "CAS",
    ],
    "buaa": [
        "Beihang University",
        "北京航空航天大学",
        "北航",
    ],
    "hit": [
        "Harbin Institute of Technology",
        "哈尔滨工业大学",
        "哈工大",
        "HIT",
    ],
    "xidian": [
        "Xidian University",
        "西安电子科技大学",
        "西电",
    ],
    "hust": [
        "Huazhong University of Science and Technology",
        "华中科技大学",
        "华科",
        "HUST",
    ],
    "bit": [
        "Beijing Institute of Technology",
        "北京理工大学",
        "北理工",
        "BIT",
    ],
    "nju": [
        "Nanjing University",
        "南京大学",
        "NJU",
        "南大",
    ],
    "tongji": [
        "Tongji University",
        "同济大学",
        "同济",
    ],
    "ruc": [
        "Renmin University of China",
        "中国人民大学",
        "人大",
        "RUC",
    ],
    "sysu": [
        "Sun Yat-sen University",
        "中山大学",
        "中大",
        "SYSU",
    ],
    "sustech": [
        "Southern University of Science and Technology",
        "南方科技大学",
        "南科大",
        "SUSTech",
    ],
    "cuhk_sz": [
        "The Chinese University of Hong Kong, Shenzhen",
        "香港中文大学（深圳）",
        "港中深",
        "CUHK-Shenzhen",
    ],
    "bytedance": [
        "ByteDance",
        "字节跳动",
        "字节",
    ],
    "alibaba": [
        "Alibaba",
        "阿里巴巴",
        "阿里",
    ],
    "tencent": [
        "Tencent",
        "腾讯",
    ],
    "baidu": [
        "Baidu",
        "百度",
    ],
    "huawei": [
        "Huawei",
        "华为",
    ],
    "meituan": [
        "Meituan",
        "美团",
    ],
    "xiaohongshu": [
        "Xiaohongshu",
        "小红书",
        "RedNote",
    ],
}


def generate_name_variants(chinese_name: str, english_name: str | None = None) -> list[str]:
    """Generate search variants for a Chinese name.

    Examples:
        - 王小明 -> ["王小明", "Wang Xiaoming", "Xiaoming Wang", "Wang X.M.", "X.M. Wang"]
        - With english_name="Jason Wang" -> also ["Jason Wang", "Jason"]

    Returns deduplicated list of variants.
    """
    variants: list[str] = [chinese_name]

    if pinyin is None:
        # Fallback when pypinyin is not available
        if english_name:
            variants.append(english_name)
        return list(dict.fromkeys(variants))

    # Generate pinyin for each character
    try:
        py_list = pinyin(chinese_name, style=Style.NORMAL, strict=False)
        pinyin_flat = [item[0] for item in py_list]
    except Exception:
        pinyin_flat = []

    if len(pinyin_flat) >= 2:
        surname = pinyin_flat[0].capitalize()
        given_names = [p.capitalize() for p in pinyin_flat[1:]]
        given_full = " ".join(given_names)
        given_initials = "".join([p[0].upper() + "." for p in pinyin_flat[1:]])

        # Wang Xiaoming
        variants.append(f"{surname} {given_full}")
        # Xiaoming Wang
        variants.append(f"{given_full} {surname}")
        # Wang X.M.
        variants.append(f"{surname} {given_initials}")
        # X.M. Wang
        variants.append(f"{given_initials} {surname}")

    if english_name:
        variants.append(english_name)
        # Also extract first name if it looks like "Given Surname"
        parts = english_name.strip().split()
        if len(parts) >= 2:
            variants.append(parts[0])  # first name only

    # Deduplicate while preserving order
    return list(dict.fromkeys(v for v in variants if v))


def normalize_institution_name(institution: str) -> str:
    """Normalize a Chinese institution name to its canonical English form.

    Maps variants like "THU", "Tsinghua", "清华大学" -> "Tsinghua University"

    Returns the canonical name if found, otherwise returns the input unchanged.
    """
    if not institution:
        return institution

    inst_lower = institution.lower().strip()

    for canonical, aliases in INSTITUTION_ALIASES.items():
        for alias in aliases:
            if inst_lower == alias.lower():
                # Return the English canonical form (first alias)
                return aliases[0]
            # Also check if the input contains the alias as a substring
            if alias.lower() in inst_lower and len(alias) > 4:
                return aliases[0]

    return institution


def get_institution_aliases(canonical_name: str) -> list[str]:
    """Get all known aliases for a canonical institution name."""
    for key, aliases in INSTITUTION_ALIASES.items():
        if aliases[0].lower() == canonical_name.lower():
            return aliases
    return [canonical_name]


def build_search_probe(
    chinese_name: str,
    institution: str | None = None,
    english_name: str | None = None,
) -> dict[str, Any]:
    """Build a comprehensive search probe for deep-dive candidate lookup.

    Returns:
        {
            "name_variants": [...],
            "institution_canonical": "...",
            "institution_aliases": [...],
            "cross_combinations": ["Wang Xiaoming Tsinghua", ...],
        }
    """
    name_variants = generate_name_variants(chinese_name, english_name)
    inst_canonical = normalize_institution_name(institution) if institution else None
    inst_aliases = get_institution_aliases(inst_canonical) if inst_canonical else []

    cross_combinations: list[str] = []
    for nv in name_variants:
        for ia in inst_aliases:
            cross_combinations.append(f"{nv} {ia}")

    return {
        "name_variants": name_variants,
        "institution_canonical": inst_canonical,
        "institution_aliases": inst_aliases,
        "cross_combinations": list(dict.fromkeys(cross_combinations))[:20],
    }


# Generic China-affiliation keywords beyond the institution aliases above
_CHINA_KEYWORDS: list[str] = [
    "china", "chinese", "beijing", "shanghai", "shenzhen", "hangzhou",
    "guangzhou", "chengdu", "wuhan", "nanjing", "xian", "xi'an",
    "tsinghua", "peking", "zhejiang", "fudan", "sjtu", "ustc",
    "cas", "buaa", "hit", "xidian", "hust", "bit", "nju", "tongji",
    "ruc", "sysu", "sustech", "cuhk", "hkust", "cityu", "polyu",
    "bytedance", "alibaba", "tencent", "baidu", "huawei", "meituan",
    "xiaohongshu", "jd.com", "didi", "netease", "xiaomi", "oppo", "vivo",
    "中国", "北京", "上海", "深圳", "杭州", "广州", "成都", "武汉", "南京",
    "清华", "北大", "中科院", "中科大", "浙大", "复旦", "上交", "北航",
    "哈工大", "西电", "华科", "北理工", "南大", "同济", "人大", "中大",
    "字节", "阿里", "腾讯", "百度", "华为", "美团", "小米", "京东",
]


def has_china_affiliation(institution: str | None, name: str | None) -> bool:
    """Return True if the candidate shows signals of China affiliation.

    Checks:
    1. Institution contains known Chinese university/company/location keywords
    2. Name contains CJK (Chinese) characters
    """
    if name:
        # CJK Unified Ideographs range
        if any("一" <= ch <= "鿿" for ch in name):
            return True

    if institution:
        inst_lower = institution.lower()
        # Check against institution aliases (covers the full alias list)
        for aliases in INSTITUTION_ALIASES.values():
            for alias in aliases:
                if alias.lower() in inst_lower:
                    return True
        # Check generic China keywords
        for kw in _CHINA_KEYWORDS:
            if kw in inst_lower:
                return True

    return False
