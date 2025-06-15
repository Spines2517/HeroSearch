import discord
from discord.ext import commands
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from discord.ui import View, Button
import asyncio
from difflib import SequenceMatcher
from pypinyin import lazy_pinyin
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

# 設定 Discord bot
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="%", intents=intents)

# Google Sheets 授權
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("herosearch-4851ae20a69c.json", scope)
client = gspread.authorize(creds)

# 開啟 Google Sheets 文件（注意大小寫與名稱）
sheet = client.open("資料庫-小刺5R自動卡").sheet1  # 或 .worksheet("工作表名稱")

# 登入提示
@bot.event
async def on_ready():
    print(f"✅ 登入成功：{bot.user}")
    print(f"✅ 已註冊指令：{bot.commands}")


def is_match(keyword: str, text: str, similarity_threshold: float = 0.6) -> bool:
    keyword = keyword.strip().lower()
    text = text.strip()
    text_lower = text.lower()

    # 方法1：直接包含
    if keyword in text_lower:
        return True

    # 方法2：拼音包含
    text_pinyin = ''.join(lazy_pinyin(text)).lower()
    keyword_pinyin = ''.join(lazy_pinyin(keyword)).lower()

    if keyword_pinyin in text_pinyin or keyword in text_pinyin:
        return True

    # 方法3：整體相似度
    full_ratio = SequenceMatcher(None, keyword, text).ratio()
    if full_ratio > similarity_threshold:
        return True

    # 方法4：拼音相似度
    pinyin_ratio = SequenceMatcher(None, keyword_pinyin, text_pinyin).ratio()
    if pinyin_ratio > similarity_threshold:
        return True

    return False


#Embed
def spell_to_embed(spell_data):
    embed = discord.Embed(
        title = spell_data.get("資料庫", spell_data.get("法術名稱", "未命名法術")),
        color = discord.Color(int("C99868", 16))
    )

    # 其他欄位加進來
    for field in ["環階", "施法時間", "時效/專注", "學派", "射程", "構材/花費"]:
        if field in spell_data:
            embed.add_field(name=field, value=spell_data[field], inline=True)

    
    # 說明內文：放進描述
    embed.description = spell_data.get("法術效果", "（無說明）")
    
    # 升環與資源可以單獨擺
    if "升環/升等" in spell_data:
        embed.add_field(name="升環/升等", value=spell_data["升環/升等"], inline=False)

    if "資源" in spell_data:
        embed.set_footer(text=f"來源：{spell_data['資源']}")

    return embed

# 將 row 格式轉換為 dict 並製作 Embed
def format_row_embed(headers, row):
    spell_data = {}
    for h, v in zip(headers, row):
        if v.strip():
            spell_data[h.strip()] = v.strip()

    embed = discord.Embed(
        title=spell_data.get("資料庫", spell_data.get("法術名稱", "未命名法術")),
        description="",  # 留空或簡短說明，因為法術說明改用欄位
        color=discord.Color(int("C99868", 16))
)

    # 先加環階等相關欄位（inline=True）
    for field in ["環階", "施法時間", "時效/專注", "學派", "射程", "構材/花費"]:
        if field in spell_data:
            embed.add_field(name=field, value=spell_data[field], inline=True)

    # 接著加「法術說明」欄位（inline=False）
    if "法術效果" in spell_data:
        embed.add_field(name="法術說明", value=spell_data["法術效果"], inline=False)

    # 最後加「升環/升等」
    if "升環/升等" in spell_data:
        embed.add_field(name="升環/升等", value=spell_data["升環/升等"], inline=False)

    # 資源放在 footer
    if "資源" in spell_data:
        embed.set_footer(text=f"來源：{spell_data['資源']}")

    return embed

    
# 搜尋指令
@bot.command()
async def 搜尋(ctx, keyword: str, column: int = 1):
    headers = sheet.row_values(1)
    col_data = sheet.col_values(column)
    results = []
    print({keyword})

    for i, cell_value in enumerate(col_data, start=1):
        if i == 1:
            continue
        if is_match(keyword, cell_value):
            row = sheet.row_values(i)
            results.append((i, row))

    if not results:
        await ctx.send(f"找不到包含『{keyword}』的資料。")
        return

    if len(results) == 1:
        i, row = results[0]
        embed = format_row_embed(headers, row)
        await ctx.send(embed=embed)
        return

    # 建立 View 並加按鈕
    view = View(timeout=10)

    selected = {"clicked": False}  # 用來記錄是否有人點按鈕

    for idx, (row_index, row) in enumerate(results):
        label = row[column - 1] or f"第{row_index}列"
        button = Button(label=label[:80], style=discord.ButtonStyle.primary)

        async def callback(interaction, row=row, label=label):
            if selected["clicked"]:
                # 防止重複點擊
                await interaction.response.defer()
                return

            selected["clicked"] = True

            embed = format_row_embed(headers, row)
            await interaction.message.edit(content=f"已選擇：{label}", embed=embed, view=None)
            view.stop()
            await interaction.response.defer()  # 確認互動回應

        button.callback = callback
        view.add_item(button)

    # 送出訊息
    message_sent = await ctx.send(f"找到 {len(results)} 筆資料，請選擇：", view=view)

    # 啟用 timeout 自動清除
    async def disable_buttons():
        await view.wait()
        if not selected["clicked"]:
            try:
                await message_sent.edit(content="⏰ 選擇超時，請重新輸入指令。", embed=None, view=None)
            except discord.NotFound:
                pass
    bot.loop.create_task(disable_buttons())
    
# 啟動機器人
bot.run(TOKEN)
