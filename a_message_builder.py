from z_config import KEYWORDS

def build_message_section(title, grouped):
    message = f"<b>{title}</b>\n\n"
    for kw in KEYWORDS:
        group = grouped[kw]
        if group:
            message += f"▪️<b>[{kw}] 관련 공시</b>\n\n"  # 🔥 제목 뒤 공백 추가
            sorted_group = sorted(group, key=lambda x: "지정예고" not in x.get("hts_pbnt_titl_cntt", ""))
            for idx, item in enumerate(sorted_group, 1):
                t = item.get("hts_pbnt_titl_cntt", "")
                message += f"{idx}. {t}\n\n"  # 🔥 항목마다 공백 한 줄 추가
    return message
